# Protocolo

Descreve as mensagens trocadas pela versão atual (`servidor.py`, `gateway.py`,
`web/app.js`, `cliente.py` e `forca/wire.py`).

```
navegador --HTTP /api--> gateway --TCP 5000 (JSON por linha)--> nó que atende
                                                 nó <--TCP 5001--> outro nó
```

O gateway não altera os comandos: o corpo do `POST /api` é exatamente o objeto
JSON que o nó recebe na porta 5000. `cliente.py` fala direto com a porta 5000.

## Enquadramento

- Um objeto JSON em UTF-8 por linha, terminado por `\n` (`forca/wire.py`).
- Limite de 2.000.000 bytes por mensagem, nos dois sentidos. Linha maior, sem
  `\n` final ou que não seja um objeto JSON produz erro e encerra a conexão.
- A leitura usa `makefile("rwb").readline()`, que acumula bytes até o
  delimitador; mensagens parciais ou agrupadas pelo TCP são tratadas pelo buffer.

## Canal HTTP do navegador (gateway, porta 8080)

| Método e caminho | Uso |
| --- | --- |
| `GET /`, `/app.js`, `/style.css` | Página do jogo (lista fixa de arquivos de `web/`) |
| `POST /api` | Um comando; corpo JSON até 8 KB com `type` em `ESTADO`, `ENTRAR`, `JOGAR`, `CHUTAR`, `SAIR` |
| `GET /api/status` | Papel, época e disponibilidade de cada nó, vistos pelo gateway |

- Resposta de `POST /api`: HTTP 200 com a resposta do nó, sem alteração. Sem
  nenhum nó atendendo, HTTP 503 com `{"retry": true, "message": ...}`.
- Corpo inválido: 400 (JSON inválido, não objeto, `type` fora da lista), 411
  (sem tamanho) ou 413 (grande demais).
- Roteamento: o gateway envia `PING` a cada nó a cada 1 s e tenta primeiro o nó
  que atende; entre dois atendendo, o de maior `revision` e depois o de maior `epoch`. Em `retry` ou falha, tenta o próximo. Tempos:
  1 s para conectar, 10 s para ler, e nenhuma tentativa começa depois de 6 s
  (pior caso de cerca de 17 s). Uma conexão HTTP que não envia a requisição em
  10 s é encerrada.
- O navegador espera até 20 s, mais que o pior caso do gateway, antes de
  reenviar o comando pendente. Com a espera limitada do nó pela trava (abaixo),
  uma requisição só é aplicada enquanto quem a enviou ainda espera a resposta.

O navegador guarda token, `deployment` e o comando pendente em `sessionStorage`
(uma aba é um jogador e sobrevive a recarregar a página). O `request_id` é
gerado no navegador e salvo antes do envio, como no `cliente.py`.

## Canal dos jogadores (porta 5000)

Cada comando usa **uma conexão TCP curta**: o gateway (ou o `cliente.py`)
conecta, envia um objeto, lê uma resposta e fecha. Não há conexão persistente
nem envio espontâneo do servidor; o navegador consulta o estado a cada 1 s e o
`cliente.py` a cada 0,5 s. Isso torna a troca de servidor igual a uma nova
consulta.

Os dois nós escutam a porta 5000 o tempo todo; só o nó que está atendendo
aceita comandos, os outros respondem `retry`.

Tempos do `cliente.py`: 2 s para conectar e 10 s para ler. O servidor usa 4 s
por conexão, espera no máximo 2 s pela trava (senão responde `retry`) e atende
até 64 conexões simultâneas; as excedentes são fechadas.

### Comandos

| `type` | Campos | Altera estado? | Efeito |
| --- | --- | --- | --- |
| `PING` | nenhum | não | Responde `{"ok": true, "node", "role", "serving", "epoch", "revision"}`. Não exige token nem a trava. |
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
  Um jogador deixa de ser ativo ao enviar `SAIR`, ou quando fica 180 s sem
  consultar o servidor fora de uma partida em andamento (`NAME_HOLD` em
  `forca/lobby.py`). Nesse caso, a sala em que ele esperava é cancelada. Uma
  partida em andamento é cancelada (`ABANDONO`, sem vencedor) quando os dois
  participantes passam 180 s sem consultar.
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
{"ok": true, "message": "Acertou!", "player_id": "<sha256>", "deployment": "<uuid>", "role": "PRIMARIO", "node": "forca-a", "state": {...}}
```

- `ok: false` com `code` indica erro de regra. O estado continua incluído.
- `node` é o nome do nó que respondeu; `role` é sempre `PRIMARIO` numa resposta
  normal.
- `{"retry": true, "message": ...}`: o nó não pode aceitar comandos agora (está
  `ENTRANDO`, é `RESERVA`, é primário na espera de até 7 s depois de perder o
  reserva, ou a trava ficou ocupada por mais de 2 s). O cliente trata como falha de conexão e tenta o
  próximo endereço, mantendo o comando pendente.
- `{"fatal": true, "message": ...}`: o `deployment` enviado pertence a outra
  execução dos servidores (os dois nós reiniciaram). O navegador volta à tela
  de nome; o `cliente.py` encerra e pede `--nova-sessao`.
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
| `reason` | `PALAVRA_COMPLETA`, `SEIS_ERROS`, `DESISTENCIA`, `ABANDONO` ou `null`. Salas canceladas internamente usam `REAGRUPADA` ou `ABANDONO` sem vencedor, mas nenhum jogador fica associado a elas |
| `max_errors` | 6 |

`PAUSADA` não é armazenado: é calculado quando a sala está `EM_JOGO` e algum
participante não consultou o servidor nos últimos 5 s.

### Vitória por abandono

`ESTADO` não altera o estado, com uma exceção: se a sala do jogador está
`EM_JOGO` e o adversário não consultou o servidor nos últimos 30 s
(`ABANDON_WAIT`), contados enquanto quem consulta esteve presente sem
interrupção, o nó encerra a partida com `winner` igual a quem ficou e `reason`
`ABANDONO`. A alteração é replicada antes da resposta, como uma jogada, e a
resposta desse `ESTADO` já traz a sala `ENCERRADA`. O jogador ausente, ao
voltar, recebe o mesmo estado.

Uma volta depois de 5 s sem consultar inicia uma nova presença, e uma promoção
ou retomada do nó zera a presença de todos: os 30 s recomeçam.

### Códigos de erro

| `code` | Situação |
| --- | --- |
| `NOME_INVALIDO` | Nome vazio, com mais de 24 caracteres ou não imprimível |
| `NOME_EM_USO` | Outro jogador ativo já usa esse nome, em qualquer sala |
| `SEM_SALA` | `JOGAR` ou `CHUTAR` sem sala associada, ou `SAIR` de quem já saiu |
| `PAUSADA` | Jogada em partida em andamento com o adversário desconectado |
| `PARTIDA_INDISPONIVEL` | Sala aguardando ou encerrada |
| `NAO_PARTICIPANTE` | Jogador fora da sala |
| `FORA_DA_VEZ` | Não é a vez do jogador |
| `ESTADO_DESATUALIZADO` | `version` diferente do `room_version` atual |
| `LETRA_INVALIDA` | Não é uma única letra, mesmo após remover o acento |
| `LETRA_REPETIDA` | Letra já tentada na sala |
| `PALAVRA_INVALIDA` | Chute vazio, com espaços, hífens, números ou mais de 30 letras |
| `PALAVRA_REPETIDA` | Palavra já chutada sem acerto na sala |
| `COMANDO_INVALIDO` | `type` desconhecido ou ausente |
| `ESTADO_CHEIO` | O estado passaria do limite de 2 MB; nada é alterado e o nó continua atendendo |

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
reserva promovido também é reconhecido. O recibo é apagado junto com o jogador
quando ele deixa de ser ativo e nenhuma sala ainda o mostra.

### Coleta do estado

Ao fim de cada comando que altera o estado, `collect` (em `forca/lobby.py`)
libera quem sumiu há 180 s fora de partida em andamento, remove jogadores
inativos que nenhuma sala mostra e remove salas encerradas ou canceladas que
nenhum jogador consulta. Assim o estado replicado depende de quantos jogam
agora, não de quantas partidas já houve.

## Canal de sincronização (porta 5001)

Não há papel fixo: os dois nós escutam 5001 e cada um conhece o outro por
`PEER` (`host:porta`). Todo nó sem reserva tenta falar com o outro a cada 1 s:
quem está `ENTRANDO`, para se juntar; quem é primário sozinho, para descobrir
se há outro primário.

1. Quem procura → outro nó: `{"key", "node", "role", "serving", "epoch",
   "revision"}`. Chave incorreta: a conexão é fechada e os dois lados
   registram no log que `REPLICATION_KEY` precisa ser igual (comparação com
   `hmac.compare_digest` sobre os bytes UTF-8, o que aceita chaves com acento).
2. O outro nó **aceita** se for `PRIMARIO` sem reserva e o visitante estiver
   `ENTRANDO`, ou se o visitante também for `PRIMARIO` e tiver menos jogadas
   confirmadas (regra abaixo). Aceitar é enviar `{"state": {...}, "node"}` com
   o estado completo (`world`, `receipts`, `revision`, `epoch`).
3. Visitante → nó: `{"ack": <revision>}`, enviado depois de guardar a cópia. O
   visitante vira `RESERVA` e descarta o que tinha. Um visitante primário
   confere a regra de novo com o estado recebido antes de ceder.
4. Logo após o ACK inicial e depois a cada 0,5 s, primário → reserva
   `{"heartbeat": true}`; o reserva responde `{"heartbeat": true}`.

Se não aceitar, o nó responde com seu `PING` e fecha.

**Início.** Um nó `ENTRANDO` procura o outro por 10 s (`BOOT_WAIT`). Se o outro
aceita, vira reserva. Se os dois estão `ENTRANDO` e se veem, o de nome menor
cria o jogo na hora. Se ninguém responde nesse tempo, o nó cria o jogo
(`deployment_id` novo, `epoch` 1) e atende sozinho.

**Entre dois primários**, prevalece o de maior `revision`; no empate, o de
maior `epoch`; no empate, o de menor nome. O outro cede e vira reserva.

O passo 2–3 se repete a cada comando que altera estado, antes da resposta ao
jogador, enquanto houver reserva. O tráfego não é cifrado pela aplicação; na
implantação ele passa pelo túnel do Tailscale.

Tempos: o primário espera 3 s por resposta do reserva; o reserva espera 5 s por
mensagem do primário; o primário que perde o reserva espera 7 s (`SOLO_WAIT`)
antes de atender sozinho.

**Quando cada lado reage à perda da conexão:**

- O reserva só pode se promover depois de receber a **segunda** mensagem do
  primário (um heartbeat ou um novo estado). Ela prova que o primário recebeu o
  ACK da cópia inicial e já o considera seu reserva. Se a conexão cair antes
  disso, ele volta a `ENTRANDO`.
- Ao se promover, o reserva soma 1 à `epoch` e passa a atender sozinho.
- Se a cópia inicial ou o seu ACK falharem, o primário segue como estava e
  registra "Sincronização inicial com o reserva falhou".
- Se o primário não recebe um ACK ou heartbeat, ele se pausa por 7 s. Nesse
  intervalo, se o outro nó se promoveu, este cede e vira reserva dele; se o
  outro reiniciou vazio, ele se junta a este. Passados os 7 s sem nenhum dos
  dois, o primário volta a atender sozinho, com uma cópia só.
