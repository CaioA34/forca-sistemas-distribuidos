# Melhorias pendentes — Jogo da Forca Distribuído

Levantamento de duas revisões de código feitas em 27/09/2026. Nenhum item impede a demonstração; todos são melhorias para depois da versão atual. Os números foram medidos localmente, com scripts que chamam as funções do projeto.

O que já foi feito está no [ROADMAP.md](ROADMAP.md). Este arquivo lista só o que falta.

## Resumo

| # | Melhoria | Área | Prioridade |
| --- | --- | --- | --- |
| 1 | Estado cresce com partidas e jogadores até pausar o primário | Servidor | Média |
| 2 | Nomes diferentes compartilham o mesmo arquivo de sessão | Cliente | Média |
| 3 | Reintegrar o servidor que volta como novo reserva | Distribuída | Média |
| 4 | Porta ocupada gera traceback | Servidor | Baixa |
| 5 | `--servers` inválido faz o cliente tentar para sempre | Cliente | Baixa |
| 6 | Mensagem enganosa para quem perdeu o nome por inatividade | Cliente | Baixa |
| 7 | Nomes com e sem acento contam como diferentes | Regras | Baixa |
| 8 | Reagrupamento não dispara ao retomar com comando pendente | Cliente | Baixa |
| 9 | "Você continua aguardando" repetido a cada reconexão | Cliente | Baixa |
| 10 | Reenvio deduplicado ainda replica e registra no log | Distribuída | Baixa |
| 11 | Custo de cada comando e consulta cresce com o estado | Distribuída | Baixa |
| 12 | Chave de replicação com valor padrão conhecido | Segurança | Baixa |
| 13 | Container como root, sem healthcheck e sem serviço de cliente | Docker | Baixa |
| 14 | Finais de linha misturados (LF e CRLF) | Repositório | Baixa |
| 15 | Script do PDF depende de `reportlab` e das fontes do Windows | Repositório | Baixa |
| 16 | Cópias antigas do projeto fora do repositório | Organização | Baixa |
| 17 | Partes sem teste automatizado | Testes | Média |
| 18 | Integração contínua (CI) | Testes | Baixa |

## Servidor e regras

### 1. Estado cresce com partidas e jogadores até pausar o primário

**Problema:** os recibos já não crescem a cada jogada, mas salas encerradas e jogadores que saíram nunca são removidos. O primário envia o estado inteiro ao reserva a cada comando, e cada mensagem tem limite de 2 MB. Quando o estado passa disso, o envio falha e o primário pausa para sempre.

**Medição:**
- Cada partida encerrada deixa cerca de 1.600 bytes. Com umas **1.240 partidas** numa mesma execução, o limite é atingido.
- Cada jogador novo deixa cerca de 820 bytes. Um cliente modificado que entra com nomes novos em sequência atinge o limite com umas **2.400 entradas**.

**Sugestão:** remover salas encerradas ou canceladas às quais nenhum jogador está mais associado, e jogadores inativos que não aparecem em nenhuma sala, junto com os recibos deles. Opcionalmente, limitar o número de salas e jogadores e responder com um erro claro ao atingir o limite.

**Onde:** [forca/lobby.py](forca/lobby.py) (`apply`, `enter`, `claim_name`).

### 4. Porta ocupada gera traceback

**Problema:** se a porta 5000 ou 5001 já estiver em uso, o servidor termina com um traceback (`PermissionError` no Windows) em vez de uma mensagem clara.

**Sugestão:** capturar `OSError` ao abrir as portas e encerrar com "Porta 5000 em uso. Feche o outro servidor ou use --port.".

**Onde:** [servidor.py:98](servidor.py#L98) (`listen`) e `main`.

### 7. Nomes com e sem acento contam como diferentes

**Problema:** "João" e "Joao" são aceitos ao mesmo tempo, enquanto letras e chutes ignoram acento ("ç" vale "C"). É inconsistente e confunde os jogadores na tela.

**Sugestão:** comparar nomes com `normalize(...)` de `forca/game.py` além de `casefold()`.

**Onde:** [forca/lobby.py:38](forca/lobby.py#L38) (`claim_name`).

## Cliente

### 2. Nomes diferentes compartilham o mesmo arquivo de sessão

**Problema:** o nome do arquivo de sessão mantém só letras e números do nome. "Ana", "A-na" e "ana!" viram `sessions/ana.json`; "***" e "!!!" viram `sessions/jogador.json`.
- **Ao mesmo tempo:** a trava recusa o segundo cliente com uma mensagem confusa, já que os nomes são diferentes.
- **Em sequência:** "A-na" com `--nova-sessao` sobrescreve a sessão guardada da Ana. Como o servidor aceita "A-na", o arquivo anterior não é restaurado, e a Ana perde a sessão que poderia retomar.

**Sugestão:** acrescentar ao nome do arquivo um hash curto do nome normalizado, por exemplo `ana-3f2a.json`.

**Onde:** [cliente.py:185](cliente.py#L185).

### 5. `--servers` inválido faz o cliente tentar para sempre

**Problema:** com uma porta não numérica (`127.0.0.1:abc`) ou uma vírgula sobrando, o erro é tratado como falha de conexão. O cliente fica em silêncio, tentando para sempre.

**Sugestão:** validar a lista ao iniciar e encerrar com uma mensagem mostrando o formato esperado (`IP:PORTA,IP:PORTA`).

**Onde:** [cliente.py:188](cliente.py#L188).

### 6. Mensagem enganosa para quem perdeu o nome por inatividade

**Problema:** quando o nome é reaproveitado depois de 180 s de ausência, o antigo dono, ao voltar, vê "Você não está em nenhuma sala". Com `/nova`, recebe "O nome Ana já está em uso" e o conselho "Se o nome for seu, retome sem --nova-sessao", que é justamente o que ele acabou de fazer. Nada explica que o nome expirou.

**Sugestão:** o servidor responder com um código próprio (por exemplo, `NOME_EXPIRADO`) quando quem pede o nome é o antigo dono, e o cliente mostrar uma orientação específica.

**Onde:** [forca/lobby.py:38](forca/lobby.py#L38) e [cliente.py:164](cliente.py#L164).

### 8. Reagrupamento não dispara ao retomar com comando pendente

**Problema:** se o cliente foi fechado no meio de um envio, ao retomar ele reenvia primeiro o comando pendente. O `ENTRAR` automático que junta jogadores esperando em salas separadas só é disparado quando a primeira resposta é de uma consulta de estado, então nessa reconexão ele não acontece.

**Sugestão:** disparar o reagrupamento na primeira resposta com estado `AGUARDANDO` após a reconexão, qualquer que seja o comando.

**Onde:** [cliente.py:170](cliente.py#L170).

### 9. "Você continua aguardando" repetido a cada reconexão

**Problema:** o `ENTRAR` automático do reagrupamento imprime "Você continua aguardando na sala-1." sempre que um jogador em espera reconecta. É apenas cosmético.

**Sugestão:** não imprimir a resposta desse `ENTRAR` automático quando a sala não mudou.

**Onde:** [cliente.py:170](cliente.py#L170) e [forca/lobby.py:55](forca/lobby.py#L55).

## Parte distribuída

### 3. Reintegrar o servidor que volta como novo reserva

**Problema:** depois da promoção, o reserva não abre a porta de replicação (5001). Não há como voltar a ter duas cópias sem reiniciar os dois servidores e perder as partidas.

**Sugestão:** ao ser promovido, o servidor inicia `synchronize` e, quando um novo reserva sincronizar, volta a replicar cada alteração, como um primário normal. O antigo primário seria religado em modo reserva apontando para ele. É o ganho mais visível para a apresentação, porque completa o ciclo de falha e recuperação.

**Onde:** [servidor.py:165](servidor.py#L165) (`follow`) e [servidor.py:193](servidor.py#L193).

### 10. Reenvio deduplicado ainda replica e registra no log

**Problema:** quando um reenvio é reconhecido pelo recibo, nada muda no estado, mas o servidor ainda copia o estado, envia tudo ao reserva e registra "Estado N confirmado" repetido no log. O mesmo vale para comandos rejeitados de quem nunca entrou.

**Sugestão:** fazer `apply` indicar se houve alteração e pular a replicação e o log quando não houver.

**Onde:** [servidor.py:64-74](servidor.py#L64-L74).

### 11. Custo de cada comando e consulta cresce com o estado

**Problema:** cada comando faz `deepcopy` do estado inteiro e o envia ao reserva. Cada consulta de estado, feita a cada 0,5 s por cliente, reconstrói todo o mundo com `World.from_dict`, sob a trava global. Além disso, cada cliente abre uma conexão TCP nova a cada 0,5 s. Para a demonstração está ótimo; com o estado crescendo (item 1), a latência cresce junto.

**Sugestão:** montar só a sala do jogador na consulta, e replicar apenas a sala alterada (ou um evento) em vez do estado completo. Conexões persistentes com envio do servidor reduziriam as conexões, ao custo de complicar a troca de servidor.

**Onde:** [servidor.py:64](servidor.py#L64) e [forca/lobby.py:21-22](forca/lobby.py#L21-L22).

## Segurança

### 12. Chave de replicação com valor padrão conhecido

**Problema:** `REPLICATION_KEY` tem o valor padrão `forca-aula` no código, no `compose.yaml` e no `.env.example`. Quem estiver na mesma rede e souber o padrão pode se conectar como reserva enquanto nenhum estiver ligado. Assim recebe o estado completo, inclusive as palavras secretas, e ao desconectar pausa o primário. O tráfego também não é cifrado; isso é aceitável na rede da aula, mas vale registrar.

**Sugestão:** não ter valor padrão e recusar iniciar sem uma chave definida no `.env`.

**Onde:** [servidor.py:203](servidor.py#L203), [compose.yaml](compose.yaml) e [.env.example](.env.example).

## Docker e repositório

### 13. Container como root, sem healthcheck e sem serviço de cliente

**Problema:** o container roda como root e não tem healthcheck. Clientes precisam de Python instalado na máquina.

**Sugestão:**
- criar um usuário sem privilégios no `Dockerfile`;
- adicionar um healthcheck que envie `PING`;
- opcionalmente, um serviço `cliente` no Compose com `stdin_open` e `tty`, para máquinas sem Python.

**Onde:** [Dockerfile](Dockerfile) e [compose.yaml](compose.yaml).

### 14. Finais de linha misturados

**Problema:** o Git avisa que vai converter LF para CRLF em vários arquivos, e o `.gitignore` já tem CRLF. Isso gera diffs ruidosos entre integrantes com sistemas diferentes.

**Sugestão:** adicionar um `.gitattributes` (por exemplo, `* text=auto eol=lf` e `*.ps1 text eol=crlf`).

### 15. Script do PDF depende de `reportlab` e das fontes do Windows

**Problema:** `scripts/gerar_especificacao_pdf.py` importa `reportlab`, que não está declarado no projeto, e carrega as fontes de `C:/Windows/Fonts`. Só funciona no Windows com a biblioteca instalada à mão.

**Sugestão:** declarar `reportlab` como dependência opcional no `pyproject.toml` (por exemplo, `[project.optional-dependencies] docs = ["reportlab"]`) e usar uma fonte padrão quando Arial não existir.

**Onde:** [scripts/gerar_especificacao_pdf.py:23](scripts/gerar_especificacao_pdf.py#L23).

### 16. Cópias antigas do projeto fora do repositório

**Problema:** há cópias de versões antigas ao lado do clone (pastas `Jogo Forca/` e `md/`), com arquivos de mesmo nome. Há risco de alguém editar a cópia errada.

**Sugestão:** apagar essas cópias depois de conferir que nada nelas falta no repositório.

## Testes

### 17. Partes sem teste automatizado

**Problema:** estas partes foram verificadas apenas manualmente:
- o laço do cliente (`run`): fila de comandos durante a reconexão, `ENTRAR` de reagrupamento, restauração da sessão após `NOME_EM_USO` e `/estado` sem conexão;
- a resposta `fatal` para uma sessão de outra execução (cenário T15 da especificação);
- a liberação de nomes com o tempo real do servidor (`Server.idle` e `since`), hoje testada só na camada de regras;
- a pausa do primário pelo heartbeat, sem nenhum comando em andamento;
- o limite de tamanho do estado (item 1).

**Sugestão:** testar o cliente como subprocesso, com o teclado simulado. Nesse caso, o `stdin` por pipe faz o Python mostrar "Fatal Python error" ao encerrar, porque a thread do teclado fica presa num `input()`. Isso não acontece num terminal real, mas o teste precisa encerrar o cliente sem depender da saída limpa.

### 18. Integração contínua (CI)

**Sugestão:** um workflow do GitHub Actions que rode `python -m unittest discover -s tests` a cada push e pull request, em Linux e Windows.
