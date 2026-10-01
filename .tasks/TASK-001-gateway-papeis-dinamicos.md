# TASK-001 — Gateway web, papéis dinâmicos e implantação com Tailscale

Branch: `feat/gateway-papeis-dinamicos`. Implementação feita no Claude Code (sem Codex, a pedido).

## Estado atual (30/09/2026, fim do dia)

**Código: pronto e testado localmente. Implantação real: ainda não feita.**

Feito:

- Partes A, B, C e D abaixo implementadas.
- `python -m unittest discover -s tests` → **70 testes OK** (inclui ponta a ponta com dois nós + gateway
  em processos reais e queda do primário).
- Verificado no navegador (duas abas, dois jogadores) com `python scripts/local.py`: queda de
  `forca-a` → `forca-b` assume (época 2) → `forca-a` religado entra como RESERVA → queda de
  `forca-b` → `forca-a` assume (época 3) com todas as jogadas preservadas. Layout de celular ok.
- Documentação atualizada: README, ARCHITECTURE, ROADMAP, `docs/protocolo-etapa-1.md`,
  `docs/especificacao-jogo-forca.md` (v3.0) e novo `docs/implantacao.md`.

Verificado em 01/10/2026 no WSL (Ubuntu 26.04, Docker 29.1.3, Compose 2.40.3):

- 70 testes OK no Linux (um teste lia `/api/status` antes de o gateway atualizar; agora espera).
- Imagem constrói e roda como usuário sem privilégios; nós se acham por nome na rede do Docker.
- `deploy/local/ensaio.py` com `deploy/local/compose.yaml` (dois nós + gateway em containers):
  processo do primário morre e o Docker o reinicia → volta como RESERVA; rede do primário cortada
  (como desligar o PC) → o outro assume em ~6 s e o antigo se pausa antes (3 s); rede volta → o
  antigo cede e vira reserva; reserva cai e volta → primário pausa e retoma. Nenhuma jogada perdida.
- `docker compose config` valida `compose.yaml` e `deploy/oracle/compose.yaml`.

Ainda não verificado (falta a chave do Tailscale e `sudo`):

- O container `tailscale` e `scripts/preparar-vm.sh` nunca foram executados. Primeiro teste real
  deve confirmar:
  1. container `tailscale` sobe em modo kernel (`TS_USERSPACE=false`, `/dev/net/tun`, `NET_ADMIN`);
  2. `forca-a`/`forca-b` resolvem **dentro do container servidor** (`TS_ACCEPT_DNS`); se não,
     usar IPs `100.x` em `PEER`/`SERVIDORES` (plano B descrito em `docs/implantacao.md`);
  3. `depends_on: restart: true` funciona na versão do Compose da VM.

Próximos passos (em ordem):

1. Tailscale: criar tag `tag:forca`, regra de acesso e chave reutilizável (`docs/implantacao.md` §1).
2. VM no PC A e VM no PC B: `bash scripts/preparar-vm.sh`; conferir logs e `tailscale status`.
3. Oracle: `deploy/oracle/` + site do Nginx + registro `forca` na Cloudflare.
4. Rodar o roteiro da seção 13 da especificação com desligamento físico.
5. Pendência de decisão: a especificação antiga dizia que a demonstração deveria funcionar **sem
   internet**; a arquitetura nova (Tailscale + Oracle) **exige internet**. Confirmar com o professor.

Revisão independente (qa-critic): ver seção "Resultado da revisão" no fim deste arquivo.

Para testar localmente em outro computador: `python scripts/local.py` e abrir
http://127.0.0.1:8080 em duas abas; digitar `a` ou `b` + Enter no terminal derruba/religa o nó.

## Contexto e decisões

- Jogador usa o **navegador**; o professor não exige socket no lado do jogador.
- **Gateway HTTP sem estado** roda em container na instância Oracle (`forca.ambrosias.dev`, atrás de
  Cloudflare + Nginx). Ele traduz HTTP para o protocolo JSON-por-linha atual.
- **Dois PCs, cada um com uma VM Linux obrigatória**, cada VM roda um nó servidor em container.
- **Tailscale** em container (sidecar) em cada VM e na Oracle: nomes fixos `forca-a`, `forca-b`,
  `forca-gateway`, independentes da rede.
- `cliente.py` continua funcionando (útil para testes locais), não é mais o caminho principal.

## Parte A — correções de estado e concorrência

1. **Coleta de lixo** (`forca/lobby.py`), executada ao fim de todo `apply` que altera o estado:
   - jogador ativo, fora de partida `EM_JOGO`, sem consultar há `NAME_HOLD` s → vira inativo
     (mesmo efeito do despejo em `claim_name`: sala `AGUARDANDO` é cancelada com `ABANDONO`);
   - jogadores inativos são removidos, com seus recibos;
   - salas `ENCERRADA`/`CANCELADA` que nenhum jogador referencia são removidas.
2. **`public_state` lê só a sala do jogador** (sem `World.from_dict` do mundo inteiro).
3. `JOGAR`/`CHUTAR` em sala encerrada responde `PARTIDA_INDISPONIVEL`, não `PAUSADA`.
4. **Estado grande demais não pausa o primário**: se a cópia serializada passar de `MAX_BYTES`, o
   comando é recusado com `ESTADO_CHEIO` e nada muda.
5. **Espera pela trava limitada a 2 s** (`lock.acquire(timeout=2)`), senão `retry`. Garante que
   uma requisição só é aplicada enquanto quem a enviou ainda espera a resposta, fechando o caso de
   duplicata atrasada aplicada depois do comando seguinte.
6. `seen` (presença) descarta entradas antigas de tokens que não são jogadores.
7. Log não usa `command["type"]` (KeyError depois de confirmar).

## Parte B — papéis dinâmicos (`servidor.py`)

Não existe mais `MODO=primario|reserva`. Cada nó tem `NODE_NAME`, `PEER` (host:porta de
sincronização do outro nó), porta de jogo e de sincronização. **Os dois nós sempre escutam as duas
portas.**

Estados do nó:

| Papel | Atende jogadas? | Observação |
|---|---|---|
| `ENTRANDO` | não (`retry`) | sem estado; tenta se juntar ao `PEER` |
| `RESERVA` | não (`retry`) | recebe o estado e responde heartbeats |
| `PRIMARIO` sem reserva, pausado | não (`retry`) | início do jogo ou perdeu o reserva |
| `PRIMARIO` com reserva | sim | replica antes de confirmar |
| `PRIMARIO` sozinho após promoção | sim | como hoje, uma só cópia |

Regras:

- **Um nó que inicia nunca se declara primário sozinho.** Fica em `ENTRANDO` e tenta se juntar ao
  `PEER` a cada 1 s. Um mundo novo só é criado quando os dois nós estão em `ENTRANDO` e se veem:
  o de **nome menor** vira `PRIMARIO` (pausado) e o outro se junta a ele.
- Canal de sincronização: quem se junta envia `{"key", "node", "role", "serving"}`.
  - Nó `PRIMARIO` sem reserva aceita: se o visitante está `ENTRANDO`, ou se o próprio nó está
    atendendo (o visitante, primário pausado, cede). Aceitar = enviar o estado completo (cópia
    inicial) e seguir com heartbeats, como hoje.
  - Nos demais casos responde `{"role", "node", "serving", "epoch"}` e fecha.
- Quem recebe `state` em resposta vira `RESERVA` e descarta o que tinha. Um primário pausado só
  cede se continuar sem reserva no momento (checagem sob a trava).
- `RESERVA` que perde o canal **depois da segunda mensagem** se promove: `epoch += 1`, atende
  sozinho. Antes da segunda mensagem, volta a `ENTRANDO`.
- Primário com reserva que perde o reserva fica pausado e volta a tentar se juntar ao `PEER`:
  se o outro se promoveu, este vira reserva dele; se o outro reiniciou vazio, ele se junta a este
  e o jogo volta a ser atendido.
- `epoch` fica no estado replicado; `PING` responde `{"ok", "role", "serving", "epoch", "node"}`.
- Limite documentado: falha dupla (reserva promovido aceita jogadas e depois reinicia vazio
  enquanto o antigo primário está pausado) perde jogadas. Resolver exige um terceiro nó
  (árbitro) — fora do escopo desta tarefa.

## Parte C — gateway (`gateway.py` + `web/`)

- `http.server.ThreadingHTTPServer`, stdlib apenas, porta 8080, limite de 128 requisições
  simultâneas, corpo até 8 KB.
- `GET /`, `/app.js`, `/style.css`: arquivos fixos de `web/` (sem mapear caminhos arbitrários).
- `POST /api`: objeto JSON com `type` em `ESTADO|ENTRAR|JOGAR|CHUTAR|SAIR`; encaminha para o nó
  que está atendendo e devolve a resposta do servidor. Sem nó disponível: HTTP 503 com
  `{"retry": true}`.
- `GET /api/status`: papel, epoch e disponibilidade de cada nó (para a demonstração).
- Roteamento: thread consulta `PING` em todos os nós a cada 1 s; prefere o nó que atende com maior
  `epoch`; em `retry` ou falha tenta o próximo. Tempos: conectar 1 s, ler 8 s, só inicia nova
  tentativa até 6 s após receber a requisição (pior caso ≈ 15 s).
- `SERVIDORES=forca-a:5000,forca-b:5000` (env).

Página (`web/index.html`, `app.js`, `style.css`), JS puro, sem build:

- Tela de nome → jogo. Token (`crypto.getRandomValues`), `deployment` e o **comando pendente**
  ficam em `sessionStorage` (uma aba = um jogador; sobrevive a recarregar).
- `request_id` gerado no navegador e salvo **antes** do envio; reenvio idêntico até haver resposta.
  Timeout do `fetch` 20 s (maior que o pior caso do gateway).
- Consulta `ESTADO` a cada 1 s. `ENTRAR` automático ao entrar e ao reconectar esperando (RF02a).
- `NOME_EM_USO` → volta à tela de nome com novo token. `fatal` → limpa a sessão.
- Duas forcas lado a lado, palavra, letras tentadas, chutes errados, vez, teclado A–Z na tela e
  físico, campo de chute, botões nova partida e sair, indicador de conexão e do nó que atende.
- Dados do servidor sempre com `textContent`; CSP `default-src 'self'`.

## Parte D — implantação

- `Dockerfile` único (servidor + gateway + web).
- `compose.yaml` (VM de cada PC): `tailscale` (imagem oficial, `TS_USERSPACE=false`,
  `/dev/net/tun`, `NET_ADMIN`, `TS_ACCEPT_DNS=true`, estado em volume) + `servidor` com
  `network_mode: service:tailscale`, `restart: unless-stopped`.
- `deploy/oracle/compose.yaml`: `tailscale` + `gateway`, porta `127.0.0.1:8080` para o Nginx.
- `.env.example` (VM) e `deploy/oracle/.env.example`.
- `scripts/preparar-vm.sh`: instala Docker (apt, Ubuntu/Debian), cria `.env` perguntando
  `NODE_NAME` e `TS_AUTHKEY`, sobe o compose.
- Documentação: README, ARCHITECTURE, protocolo, especificação (seções de papéis, implantação,
  testes) e política de acesso do Tailscale.

## Critérios de aceite

- Testes unitários antigos adaptados e passando; novos testes para A, B e C.
- Teste ponta a ponta com processos reais: dois nós + gateway; partida pelo `/api`; derrubar o
  primário → o outro assume com a partida intacta; religar o antigo → vira reserva; derrubar o
  atual → o antigo assume com a partida intacta.
- Nada de Docker é testado localmente (Docker indisponível nesta máquina) — declarar no relatório.

## Resultado da revisão (qa-critic, 30/09/2026)

**Veredito: aprovado com ressalvas.** 70 testes OK; fuzz de 3000 sequências no lobby sem exceção;
não foi encontrada intercalação que deixe dois nós confirmando jogadas.

Corrigir amanhã (detalhes e critérios em `.tasks/TASK-001-qa.md`):

1. **Média — `servidor.py`**: primário pausado por mais de 180 s não atualiza `seen`; ao voltar a
   atender, a primeira jogada trata como inativos jogadores que consultaram o tempo todo (sala de
   espera cancelada). Correção provável: reiniciar `since`/`seen` quando o nó volta a atender em
   `attend`, ou registrar presença mesmo quando responde `retry`.
2. **Média — `gateway.py`**: Handler sem timeout de socket; 128 conexões ociosas esgotam os slots e
   o gateway para de responder. Correção: `timeout` no Handler (ex.: 10 s).
3. Baixa: margem zero entre o pior caso do nó (2 s de trava + 3 s de envio + 3 s de ACK = 8 s) e
   a leitura de 8 s do gateway; subir `READ` do gateway para 10 s (e o `TIMEOUT` do navegador
   continua maior).
4. Baixas: `/api/status` público expõe papéis dos nós (aceitável para a demo); `run()` do app.js
   para o polling se `render` lançar exceção (envolver em try/finally); 8 conexões não autenticadas
   na porta 5001 atrasam o join (só alcançável dentro do Tailscale).
5. Testes faltando: join simultâneo, pausa longa + retomada, duplicata atrasada após o comando seguinte.

### Correções do QA aplicadas (01/10/2026)

- **Item 1 (servidor):** ao voltar a atender depois de pausado, o nó reinicia `since` e `seen`
  (`Server.attend`). Teste: `test_pausa_longa_nao_faz_quem_ficou_parecer_sumido` (falha sem a correção).
  Efeito colateral esperado: a partida aparece pausada até os dois jogadores consultarem de novo (≤ 1 s).
- **Item 2 (gateway):** `Handler.timeout` de 10 s (`--idle-timeout`). Teste:
  `test_conexoes_ociosas_nao_derrubam_o_gateway` (128 conexões ociosas + corpo incompleto).
- **Item 3:** leitura do gateway e do `cliente.py` subiu de 8 s para 10 s (pior caso do nó é 8 s).
- **Item 4 (parcial):** `run()` do `app.js` reagenda a consulta mesmo se a tela lançar erro.
- 72 testes OK no Windows e no WSL; `deploy/local/ensaio.py` OK duas vezes após as correções.

Continuam em aberto: `/api/status` público; limite de 8 conexões não autenticadas na porta 5001;
testes de join simultâneo e de duplicata atrasada.

### Tailscale verificado no WSL (01/10/2026)

Os três projetos Compose reais (forca-a, forca-b e o gateway de `deploy/oracle`) subiram no mesmo WSL
com a chave real:

- container `tailscale` sobe em modo kernel (`tailscale0`) e autentica com a chave com tag;
- `forca-a`/`forca-b` **resolvem dentro do container servidor** (`TS_ACCEPT_DNS` funciona; plano B
  de IPs não foi necessário);
- nós sincronizam e o gateway roteia pela rede do Tailscale;
- ensaio de falhas pelo Tailscale OK: processo morto e reiniciado, "PC" desligado (troca em ~6 s)
  e religado como reserva, sem perder jogadas;
- `depends_on: restart: true` funciona com `docker compose restart tailscale`.

Limite encontrado: reinício do container `tailscale` por fora do Compose deixa o servidor preso à
rede antiga (documentado em `docs/implantacao.md`).

Falta: `scripts/preparar-vm.sh` (precisa de sudo), VMs reais em dois PCs, Oracle/Nginx/Cloudflare
e o teste de desligamento físico. Os dispositivos de teste devem ser apagados do painel do Tailscale
antes de subir as VMs reais.
