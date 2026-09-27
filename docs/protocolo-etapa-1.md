# Protocolo TCP

Descreve as mensagens trocadas pela versão atual (`servidor.py`, `cliente.py` e
`forca/wire.py`). O nome do arquivo foi mantido por histórico; o conteúdo vale
para a versão com primário e reserva.

## Enquadramento

- Um objeto JSON em UTF-8 por linha, terminado por `\n` (`forca/wire.py`).
- Limite de 2.000.000 bytes por mensagem, nos dois sentidos. Linha maior, sem
  `\n` final ou que não seja um objeto JSON produz erro e encerra a conexão.
- A leitura usa `makefile("rwb").readline()`, que acumula bytes até o
  delimitador; mensagens parciais ou agrupadas pelo TCP são tratadas pelo buffer.

## Canal dos jogadores (porta 5000)

Cada comando usa **uma conexão TCP curta**: o cliente conecta, envia um objeto,
lê uma resposta e fecha. Não há conexão persistente nem envio espontâneo do
servidor; o cliente consulta o estado a cada 0,5 s. Isso torna a troca de
servidor igual a uma nova consulta.

Tempos do cliente: 2 s para conectar e 5 s para ler. O servidor usa 4 s por
conexão e atende até 64 conexões simultâneas; as excedentes são fechadas.

### Comandos

| `type` | Campos | Altera estado? | Efeito |
| --- | --- | --- | --- |
| `PING` | nenhum | não | Responde `{"ok": true, "role": ...}`. Não exige token. |
| `ESTADO` | `token`, `deployment` | não | Registra presença e devolve o estado da sala do jogador. |
| `ENTRAR` | `token`, `deployment`, `request_id`, `name` | sim | Cria ou reativa o jogador, reservando o nome, e o coloca em uma sala. Quem já espera sozinho é levado à sala de outro jogador que esteja esperando conectado. |
| `JOGAR` | `token`, `deployment`, `request_id`, `letter`, `version` | sim | Tenta uma letra. `version` é o `room_version` conhecido pelo cliente. |
| `CHUTAR` | `token`, `deployment`, `request_id`, `word`, `version` | sim | Tenta a palavra inteira. Certo: vence com `PALAVRA_COMPLETA`. Errado: +1 erro e a vez passa. |
| `SAIR` | `token`, `deployment`, `request_id` | sim | Desiste da partida ou cancela a espera e libera o nome. |

- `token`: segredo aleatório de 32 a 128 caracteres, gerado e salvo pelo
  cliente (`secrets.token_urlsafe(32)`). O servidor usa `player_id =
  SHA-256(token)`; o token nunca é devolvido nem registrado em log.
- `deployment`: identificador da execução, recebido na primeira resposta.
  Pode ser `null` antes disso.
- `request_id`: UUID em texto, gerado pelo cliente para cada comando que altera estado.
- `name`: 1 a 24 caracteres imprimíveis. É único entre os jogadores ativos de
  todas as salas, comparado sem diferenciar maiúsculas e sem espaços nas pontas.
  Um jogador deixa de ser ativo ao enviar `SAIR`, ou quando outro jogador pede o
  mesmo nome depois que ele ficou 180 s sem consultar o servidor fora de uma
  partida em andamento (`NAME_HOLD` em `forca/lobby.py`). Nesse caso, a sala em
  que ele esperava é cancelada.
- `letter` e `word`: acentos são removidos e o texto é convertido para
  maiúsculas antes da validação (`ç` vale `C`; `conexão` vale `CONEXAO`).
- `word`: 1 a 30 letras, sem espaços, hífens ou números.
- Campos extras são ignorados pela regra, mas fazem parte da impressão digital
  usada na deduplicação. O cliente atual envia `name` em todos os comandos.

Exemplo, em uma única linha na rede:

```json
{"type":"JOGAR","request_id":"8faf6bbb-3c3f-40d2-9d21-cb395e687b52","token":"<token>","deployment":"<uuid>","name":"Ana","letter":"A","version":3}
{"type":"CHUTAR","request_id":"0b7c1e8e-5d1f-4f0e-9a51-7f2f3f0c2a10","token":"<token>","deployment":"<uuid>","name":"Ana","word":"SOCKET","version":4}
```

### Respostas

Resposta normal (`ESTADO`, `ENTRAR`, `JOGAR`, `SAIR`):

```json
{"ok": true, "message": "Acertou!", "player_id": "<sha256>", "deployment": "<uuid>", "role": "PRIMARIO", "state": {...}}
```

- `ok: false` com `code` indica erro de regra. O estado continua incluído.
- `role` é `PRIMARIO` ou `RESERVA_PROMOVIDO`.
- `{"retry": true, "message": ...}`: o servidor não pode aceitar comandos agora
  (primário sem reserva sincronizado ou pausado). O cliente trata como falha de
  conexão e tenta o próximo endereço, mantendo o comando pendente.
- `{"fatal": true, "message": ...}`: o `deployment` enviado pertence a outra
  execução dos servidores. O cliente encerra; é preciso usar `--nova-sessao`.
- `{"ok": false, "message": "Comando inválido: ..."}`: token com tamanho
  inválido, `request_id` ausente, que não seja texto ou não seja UUID, ou
  `request_id` reutilizado com outro conteúdo.
- `{"ok": false, "message": "Erro interno do servidor."}`: falha inesperada. O
  servidor registra o traceback no log e continua atendendo.

A verificação de `retry` ocorre antes das demais: com o primário pausado,
qualquer comando diferente de `PING` recebe `retry`.

### Estado público (`state`)

`null` quando o jogador não está em nenhuma sala. Caso contrário:

| Campo | Conteúdo |
| --- | --- |
| `room_id` | `sala-1`, `sala-2`, ... |
| `room_version` | Inteiro incrementado a cada alteração da sala |
| `status` | `AGUARDANDO`, `EM_JOGO`, `PAUSADA`, `ENCERRADA` ou `CANCELADA` |
| `players` | Lista com `player_id`, `name`, `errors` e `connected` |
| `masked_word` | Palavra com `_` nas letras ocultas; completa após o fim; vazia antes do início |
| `guesses` | Letras já tentadas na sala, em ordem |
| `wrong_words` | Palavras chutadas sem acerto, em ordem |
| `turn` | `player_id` da vez, ou `null` |
| `winner` | `player_id` do vencedor, ou `null` |
| `reason` | `PALAVRA_COMPLETA`, `SEIS_ERROS`, `DESISTENCIA` ou `null`. Salas canceladas internamente usam `REAGRUPADA` ou `ABANDONO`, mas nenhum jogador fica associado a elas |
| `max_errors` | 6 |

`PAUSADA` não é armazenado: é calculado quando a sala está `EM_JOGO` e algum
participante não consultou o servidor nos últimos 5 s.

### Códigos de erro

| `code` | Situação |
| --- | --- |
| `NOME_INVALIDO` | Nome vazio, com mais de 24 caracteres ou não imprimível |
| `NOME_EM_USO` | Outro jogador ativo já usa esse nome, em qualquer sala |
| `SEM_SALA` | `JOGAR` ou `CHUTAR` sem sala associada, ou `SAIR` de quem já saiu |
| `PAUSADA` | Jogada com o adversário desconectado |
| `PARTIDA_INDISPONIVEL` | Sala aguardando ou encerrada |
| `NAO_PARTICIPANTE` | Jogador fora da sala |
| `FORA_DA_VEZ` | Não é a vez do jogador |
| `ESTADO_DESATUALIZADO` | `version` diferente do `room_version` atual |
| `LETRA_INVALIDA` | Não é uma única letra, mesmo após remover o acento |
| `LETRA_REPETIDA` | Letra já tentada na sala |
| `PALAVRA_INVALIDA` | Chute vazio, com espaços, hífens, números ou mais de 30 letras |
| `PALAVRA_REPETIDA` | Palavra já chutada sem acerto na sala |
| `COMANDO_INVALIDO` | `type` desconhecido |

Erros de regra não alteram turno nem erros, mas, para quem já entrou, são
registrados como resultado do `request_id`.

### Reenvio e deduplicação

O servidor guarda, para cada jogador, o recibo do **último** comando que
alterou o estado: `request_id`, impressão digital SHA-256 do comando e
resultado. Basta um por jogador, porque o cliente só tem um comando pendente
por vez. Assim o estado replicado não cresce com a quantidade de jogadas.
Comandos de quem nunca entrou não mudam nada e não geram recibo. Um reenvio com
o **mesmo identificador e o mesmo conteúdo** do último comando devolve o
resultado registrado, sem aplicar a ação de novo. O cliente grava o comando pendente no arquivo de
sessão (`sessions/<nome>.json`) antes de enviá-lo e só o descarta após uma
resposta. Enquanto o cliente está aberto, o arquivo fica travado por um
`<nome>.lock` ao lado, para que um segundo cliente não use o mesmo token.
Depois de um erro definitivo (por exemplo, `ESTADO_DESATUALIZADO`), a nova
tentativa usa outro UUID.

Os recibos são replicados junto com o estado; por isso um reenvio feito ao
reserva promovido também é reconhecido.

## Canal de replicação (porta 5001)

Conexão TCP persistente aberta pelo reserva para o primário.

1. Reserva → primário: `{"key": "<REPLICATION_KEY>"}`. Chave incorreta: o
   primário fecha a conexão (comparação com `hmac.compare_digest` sobre os
   bytes UTF-8, o que aceita chaves com acento).
2. Primário → reserva: `{"state": {...}}` com o estado completo
   (`world`, `receipts`, `revision`).
3. Reserva → primário: `{"ack": <revision>}`, enviado depois de guardar a cópia.
4. Logo após o ACK inicial e depois a cada 0,5 s, primário → reserva
   `{"heartbeat": true}`; o reserva responde `{"heartbeat": true}`.

O passo 2–3 se repete a cada comando que altera estado, antes da resposta ao
jogador. O tráfego não é cifrado.

Tempos: o primário espera 3 s por resposta do reserva; o reserva espera 5 s por
mensagem do primário.

**Quando cada lado reage à perda da conexão:**

- O reserva só pode se promover depois de receber a **segunda** mensagem do
  primário (um heartbeat ou um novo estado). Ela prova que o primário recebeu o
  ACK da cópia inicial e já o considera seu reserva. Se a conexão cair antes
  disso, o reserva apenas tenta sincronizar de novo.
- Se a cópia inicial ou o seu ACK falharem, o primário não se pausa: registra
  "Sincronização inicial com o reserva falhou" e espera outra tentativa. Não há
  risco de dois ativos, porque esse reserva ainda não pode se promover.
- Depois da sincronização, se o primário não recebe um ACK ou heartbeat, ele se
  pausa; o reserva, ao perder a conexão, se promove e passa a atender na porta
  de jogadores.
