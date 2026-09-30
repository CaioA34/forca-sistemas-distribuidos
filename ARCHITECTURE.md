# Arquitetura — Jogo da Forca Distribuído

## Objetivo

Jogo da forca com até dois jogadores por sala, várias partidas simultâneas e continuação da mesma partida quando o nó que atende cair. Usa apenas a biblioteca padrão do Python: `socket`, `threading`, `http.server`, `json`, `hashlib`, `hmac`.

## Componentes

| Componente | Responsabilidade |
| --- | --- |
| Página (`web/`) | Tela do jogo no navegador. Guarda token, `deployment` e o comando pendente na aba; reenvia o pendente até haver resposta. |
| Gateway (`gateway.py`) | HTTP para o navegador. Sem estado: descobre qual nó atende (`PING` a cada 1 s) e encaminha cada comando sem alterá-lo. |
| Nó (`servidor.py`) | Papel dinâmico: `ENTRANDO`, `RESERVA` ou `PRIMARIO`. O primário aplica as regras sob uma trava e replica cada alteração antes de responder. |
| Regras (`forca/game.py`, `forca/lobby.py`) | Partida, salas, sessões, nomes únicos, recibos e coleta do estado. Não abrem sockets. |
| Protocolo (`forca/wire.py`) | JSON UTF-8, um objeto por linha, com limite de tamanho. |
| Tailscale (container) | Rede privada entre as duas VMs e a Oracle, com nomes fixos (`forca-a`, `forca-b`, `forca-gateway`). |
| Docker Compose | Um nó por VM (`compose.yaml`) e o gateway na Oracle (`deploy/oracle/compose.yaml`). |
| VirtualBox | Uma VM Ubuntu em cada um dos dois PCs (requisito do trabalho). |

## Organização

```mermaid
flowchart LR
    N[Navegadores] -->|HTTPS forca.ambrosias.dev| G
    subgraph Oracle
        G[Nginx + gateway<br/>sem estado]
    end
    G -->|Tailscale, TCP 5000| A
    G -.->|se A não atende| B
    subgraph PC_A[VM no PC A]
        A[forca-a<br/>estado em RAM]
    end
    subgraph PC_B[VM no PC B]
        B[forca-b<br/>cópia em RAM]
    end
    A <-->|Tailscale, TCP 5001: chave, estado + ACK, heartbeat| B
```

Um único nó aceita alterações por vez. Os dois escutam as duas portas; quem não está atendendo responde `retry`, e o gateway passa ao outro. Não há banco de dados: cada nó guarda o estado em memória.

**Interpretação de nó:** os nós do sistema distribuído são os dois servidores em computadores físicos diferentes. O gateway é a porta de entrada e não guarda estado. As salas são estruturas de dados dentro do nó que atende, não processos separados.

## Papéis dinâmicos

| Papel | Atende? | Como chega a ele |
| --- | --- | --- |
| `ENTRANDO` | não | Ao iniciar, ou quando a sincronização inicial não se confirma |
| `RESERVA` | não | Um primário sem reserva aceitou este nó e enviou a cópia completa |
| `PRIMARIO` pausado | não | Os dois estavam entrando e este tem o nome menor (jogo novo), ou perdeu o reserva |
| `PRIMARIO` com reserva | sim | Um reserva se juntou a ele |
| `PRIMARIO` sozinho | sim | Era reserva e o primário caiu (promoção, `epoch` + 1) |

- **Nenhum nó se declara primário sozinho.** Um jogo novo só nasce quando os dois estão `ENTRANDO` e se veem; o de nome menor cria.
- **Quem volta vira reserva.** Um nó que reinicia fica `ENTRANDO` e se junta a quem está atendendo. Um primário pausado que encontra o outro atendendo descarta a própria cópia e vira reserva dele.
- **Primário pausado volta a atender** quando o reserva reinicia vazio e se junta a ele.
- `epoch` conta as promoções, é replicada e aparece no `PING`. O gateway prefere o nó que atende com a maior época.

Consequência para o Docker: `restart: unless-stopped` é seguro, porque um nó que volta nunca assume sozinho.

## Entrada e comunicação

1. O navegador gera um token aleatório (32 bytes) e o guarda em `sessionStorage`: cada aba é um jogador.
2. Envia `ENTRAR` com o nome. O comando pendente é salvo antes do envio e reenviado idêntico até haver resposta.
3. O nó recusa o nome se outro jogador ativo já o usa (`NOME_EM_USO`). Depois procura uma sala com um jogador aguardando e conectado; se não houver, cria uma.
4. Com dois jogadores, a partida começa com uma palavra sorteada no nó; o primeiro a entrar começa.
5. Ao reconectar enquanto espera, a página envia `ENTRAR` de novo; se outra sala tiver alguém esperando, os dois se juntam.

Depois disso, a página envia `ESTADO` a cada 1 s e `JOGAR`, `CHUTAR` ou `SAIR` quando o jogador age. Detalhes em [docs/protocolo-etapa-1.md](docs/protocolo-etapa-1.md).

## Partidas e estado

| Dados | Conteúdo |
| --- | --- |
| Jogadores | `player_id` (SHA-256 do token), nome, sala e se está ativo |
| Salas | Participantes, palavra, letras, chutes errados, erros por jogador, turno, estado, versão, vencedor e motivo |
| Recibos | Para cada jogador, só o último comando: `request_id`, impressão digital e resultado |
| Controle | `deployment_id` da execução, `revision` global e `epoch` |

Uma trava (`threading.Lock`) torna indivisível a sequência: copiar o estado → aplicar a regra → replicar e esperar ACK → adotar a cópia → responder. Uma requisição espera no máximo 2 s pela trava; depois disso recebe `retry`. Com os tempos do gateway (leitura de 8 s) e do navegador (20 s), uma requisição só é aplicada enquanto quem a enviou ainda espera a resposta, e uma cópia atrasada não pode ser aplicada depois do comando seguinte.

**Coleta:** ao fim de cada alteração, o nó libera quem sumiu há 180 s fora de partida em andamento, apaga jogadores inativos que nenhuma sala mostra e salas encerradas que ninguém consulta. O estado replicado depende de quantos jogam agora, não do histórico. Se mesmo assim passar de 2 MB, o comando é recusado (`ESTADO_CHEIO`) sem pausar o nó.

A consulta de estado monta só a sala do jogador, não o mundo inteiro.

## Recuperação de falhas

- **Replicação síncrona:** o primário envia o estado completo ao reserva e só responde depois do ACK com a mesma revisão.
- **Sincronização inicial:** o reserva só pode se promover depois da segunda mensagem do primário, que prova que o ACK inicial chegou. Se a cópia inicial falhar, o primário não se pausa.
- **Heartbeat:** a cada 0,5 s. O primário espera 3 s; o reserva espera 5 s. O primário se pausa antes de o reserva assumir, então nunca há dois nós confirmando jogadas.
- **Queda do primário:** o reserva detecta o fechamento da conexão (processo encerrado) ou o timeout (computador desligado) e assume com a última revisão.
- **Queda do reserva:** o primário se pausa e responde `retry`. Quando o reserva volta, se junta a ele e o jogo continua.
- **Gateway e navegador:** em `retry` ou falha, o gateway tenta o outro nó; sem nenhum, responde 503 e o navegador reenvia o mesmo comando.
- **Reenvio:** os recibos são replicados; um reenvio após a troca devolve o resultado registrado sem repetir a jogada.
- **Execuções diferentes:** se os dois nós reiniciarem, o `deployment_id` muda e o navegador volta à tela de nome (`fatal`).

## Acesso e limites

A chave de replicação é comparada com `hmac.compare_digest`. O tráfego entre os nós e o gateway passa pelo Tailscale (cifrado); o público só alcança o gateway pelo HTTPS da Cloudflare. Tokens nunca são registrados em log: o gateway não registra requisições.

O modelo supõe falha por parada, uma de cada vez. Com dois nós não há como distinguir queda de partição; a proteção vem de o primário nunca confirmar sem o reserva. Uma falha dupla (o promovido aceita jogadas e depois reinicia vazio enquanto o antigo está pausado) perde jogadas; evitá-la exige um terceiro nó como árbitro. Se os dois nós pararem, as partidas se perdem.
