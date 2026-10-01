# Jogo da Forca Distribuído

Trabalho de Sistemas Distribuídos: jogo da forca em Python com dois nós servidores, em computadores diferentes, que mantêm o estado em RAM e o replicam entre si. O jogador usa o navegador; um gateway HTTP sem estado encaminha cada jogada ao nó que está atendendo. Usa apenas a biblioteca padrão.

```
navegador ──HTTPS──> forca.ambrosias.dev (Oracle: Nginx + gateway)
                                 │  Tailscale
                  ┌──────────────┴──────────────┐
          PC A: VM → forca-a  ◄── réplica ──►  PC B: VM → forca-b
```

## O que funciona

- O primeiro jogador espera; o segundo inicia a partida. O terceiro espera em outra sala, e assim por diante. Várias partidas acontecem ao mesmo tempo.
- Cada jogador tem seu boneco e até seis erros. Na sua vez, tente uma letra ou chute a palavra inteira. Acertar ou errar passa a vez; um chute errado custa um membro.
- Quem completa a palavra vence; quem atinge seis erros perde.
- Se o adversário sair da partida e não voltar em 30 segundos, quem ficou vence por abandono.
- Nomes são únicos entre os jogadores ativos, sem diferenciar maiúsculas. Acentos são ignorados: `ç` conta como `C`.
- **Funciona com um nó só:** se apenas uma VM estiver ligada, ela cria o jogo e atende. Quando a outra entra, passa a guardar a segunda cópia.
- **Replicação antes de confirmar:** com os dois nós ligados, o que atende envia o estado ao outro e espera o ACK antes de responder.
- **Papéis dinâmicos:** se o primário cai, o reserva assume. Quando o antigo primário volta, ele entra como reserva de quem está atendendo. Não há primário fixo.
- **Um endereço só:** o navegador fala sempre com o gateway, que descobre sozinho qual nó está atendendo. O jogador não digita IP nenhum.
- **Sem configurar IP:** os nós e o gateway se encontram por nomes fixos do Tailscale (`forca-a`, `forca-b`), em qualquer rede.
- Reenvios da mesma jogada não a aplicam duas vezes, mesmo depois da troca de servidor.
- O estado replicado só guarda quem está jogando: partidas encerradas e jogadores que saíram são apagados.

## Requisitos

- Python 3.12 ou superior para rodar localmente. Nenhum pacote externo.
- Para a apresentação: dois computadores, cada um com uma VM Ubuntu 22.04+ (VirtualBox), Docker e uma conta gratuita no Tailscale. O gateway roda em container na instância Oracle.

## Teste rápido no mesmo computador

```powershell
python scripts/local.py
```

Isso sobe `forca-a` (portas 5000/5001), `forca-b` (5002/5003) e o gateway em http://127.0.0.1:8080. Abra o endereço em **duas abas** (cada aba é um jogador) e jogue. No terminal do `local.py`, digite `a` + Enter para derrubar ou religar o `forca-a` (ou `b` para o outro) e veja a partida continuar no outro nó.

Também dá para subir cada peça em um terminal:

```powershell
python servidor.py --node forca-a --port 5000 --sync-port 5001 --peer 127.0.0.1:5003
python servidor.py --node forca-b --port 5002 --sync-port 5003 --peer 127.0.0.1:5001
python gateway.py --servers 127.0.0.1:5000,127.0.0.1:5002
```

Para ensaiar em containers, sem Tailscale (precisa de Docker):

```bash
cd deploy/local && docker compose up -d --build && python3 ensaio.py
```

O `ensaio.py` joga pelo gateway e derruba os nós: processo que morre e é reiniciado pelo Docker, rede cortada (como desligar o PC), nó seguindo sozinho, retorno como reserva e vitória por abandono. Leva cerca de um minuto.

O cliente de terminal continua disponível para testes: `python cliente.py --name Ana --nova-sessao` (ele usa `127.0.0.1:5000,127.0.0.1:5002` por padrão).

## Na página do jogo

| Ação | Efeito |
| --- | --- |
| Tecla de letra (ou botão A–Z) | Tenta a letra na sua vez |
| Campo "Chutar a palavra inteira" | Tenta a palavra. Certo: vence. Errado: +1 erro e a vez passa |
| Nova partida | Aparece quando a partida termina |
| Sair | Desiste da partida (pede confirmação) e libera o nome |
| Fechar a aba no meio da partida | A partida pausa; sem volta em 30 s, o adversário vence por abandono |
| Recarregar a página | Mantém a sessão da aba e reenvia a jogada pendente, se houver |

O canto superior mostra a conexão e o nó que está atendendo (`forca-a` ou `forca-b`), o que deixa a troca de servidor visível na apresentação. `GET /api/status` mostra o papel de cada nó.

## Implantação: duas VMs e a Oracle

O passo a passo completo, incluindo a conta do Tailscale, a regra de acesso e o Nginx, está em [docs/implantacao.md](docs/implantacao.md). Resumo:

1. **Tailscale (uma vez):** crie a tag `tag:forca`, a regra de acesso e uma chave de autenticação reutilizável com essa tag.
2. **Em cada VM**, na pasta do projeto: `bash scripts/preparar-vm.sh`. O script instala o Docker, pergunta se o PC é o nó `a` ou `b` e a chave, cria o `.env` e sobe os containers.
3. **Na Oracle**, em `deploy/oracle/`: copie `.env.example` para `.env`, preencha a chave e rode `docker compose up -d --build`. Ative o site `deploy/oracle/nginx-forca.conf` no Nginx.

Não é preciso descobrir IPs nem usar rede bridge: cada container `tailscale` dá à VM um nome fixo que funciona em qualquer rede, inclusive na rede restrita da faculdade.

### Configuração

| Variável | Onde | Uso | Padrão |
| --- | --- | --- | --- |
| `NODE_NAME` | VM | Nome do nó no Tailscale (`forca-a` ou `forca-b`) | `forca-a` |
| `PEER` | VM | `host:porta` de sincronização do outro nó | `127.0.0.1:5003` |
| `REPLICATION_KEY` | VM | Chave compartilhada do canal de sincronização | `forca-aula` |
| `TS_AUTHKEY` | VM e Oracle | Chave de autenticação do Tailscale | — |
| `SERVIDORES` | Oracle | Endereços de jogo dos nós | `forca-a:5000,forca-b:5000` |
| `GATEWAY_HOST_PORT` | Oracle | Porta local em que o Nginx encontra o gateway | `8080` |
| `GAME_PORT` / `SYNC_PORT` | Fora do Compose | Portas de jogo e de sincronização | `5000` / `5001` |
| `BOOT_WAIT` / `SOLO_WAIT` | VM (opcional) | Segundos procurando o outro nó ao iniciar / de pausa ao perder o reserva | `10` / `7` |
| `ABANDON_WAIT` | VM (opcional) | Segundos com o adversário fora até a vitória de quem ficou | `30` |

As mesmas opções existem na linha de comando: `python servidor.py --help` e `python gateway.py --help`.

## Limites desta versão

- Tolera **uma falha por vez**, por parada. Com os dois nós ligados, nenhuma jogada confirmada se perde na queda de um deles.
- Com um nó só, o jogo continua, mas com **uma cópia**: se esse nó cair antes de o outro voltar, as jogadas feitas nesse período se perdem.
- Ao perder o reserva, o primário pausa por até 7 s antes de seguir sozinho. A pausa existe para o caso de ter sido só a rede entre os nós: nesse tempo o reserva assume e os jogadores vão para ele.
- Se a rede entre os dois nós falhar com as duas máquinas vivas e os dois receberem jogadas, ao se reencontrarem fica o que confirmou mais jogadas e as do outro são descartadas. Evitar isso exige um terceiro nó como árbitro.
- Se os dois nós pararem, as partidas se perdem: não há persistência em disco. Os navegadores voltam à tela de nome.
- O gateway é um ponto único: se a Oracle cair, o jogo fica inacessível, embora os nós continuem com o estado.
- A troca de servidor leva alguns segundos (até 5 s sem heartbeat quando o computador é desligado). Depois dela, a partida fica pausada até os dois jogadores voltarem a consultar.
- Quem fecha a aba no meio da partida tem 30 s para voltar; depois disso o adversário, se estiver presente, vence por abandono. Os 30 s só contam enquanto quem ficou está consultando o servidor, de modo que uma queda do gateway ou uma troca de servidor não dá vitória a ninguém. Se os dois sumirem por 180 s, a partida é cancelada. Fora de partida, o nome é liberado após 180 s sem consultas.
- Chaves de replicação diferentes nos dois nós fazem cada um atender sozinho. Os dois registram no log `REPLICATION_KEY precisa ser igual nos dois nós`.

## Como ler o código

| Arquivo | Responsabilidade |
| --- | --- |
| `servidor.py` | Nó: papéis dinâmicos, trava, TCP, replicação, heartbeat e promoção |
| `gateway.py` | HTTP para o navegador e roteamento para o nó que atende |
| `web/` | Página do jogo (HTML, CSS e JS sem build) |
| `forca/lobby.py` | Salas, nomes únicos, sessões, reenvios e coleta do estado |
| `forca/game.py` | Regras de uma partida |
| `forca/wire.py` | JSON por linha |
| `forca/rede.py` | Vigia da rede: encerra o processo se a rede do container sumir, para o Docker reiniciá-lo |
| `cliente.py`, `forca/ui.py` | Cliente de terminal, mantido para testes |
| `compose.yaml` | Nó em uma VM: container `tailscale` + container `servidor` |
| `deploy/oracle/` | Gateway na Oracle: Compose, `.env.example` e site do Nginx |
| `scripts/local.py` | Dois nós e gateway nesta máquina |
| `scripts/preparar-vm.sh` | Prepara uma VM Ubuntu e sobe o nó |
| `tests/` | Testes automatizados (unittest) |

Leia primeiro `game.py`, depois `lobby.py` e por último `servidor.py`. Em `Server.request`, a sequência principal é: copiar o estado → aplicar a regra → replicar e esperar o ACK → adotar o estado → responder. Os papéis mudam em `Server.join` (juntar-se ao outro nó), `Server.attend` (aceitar um reserva) e `Server.follow` (acompanhar e, se o primário cair, assumir).

## Documentação

- [docs/implantacao.md](docs/implantacao.md): Tailscale, VMs e Oracle, passo a passo, com comandos úteis e as situações mais comuns na configuração das VMs.
- [docs/especificacao-jogo-forca.md](docs/especificacao-jogo-forca.md): requisitos, garantias, limites e roteiro da apresentação.
- [docs/protocolo-etapa-1.md](docs/protocolo-etapa-1.md): mensagens HTTP, de jogadores e de sincronização.
- [ARCHITECTURE.md](ARCHITECTURE.md): visão geral da arquitetura.

## Testes

```powershell
python -m unittest discover -s tests -v
```

| Arquivo | Cobre |
| --- | --- |
| `tests/test_game.py` | Turnos, letras, chute, acentos, vitória, seis erros e lista de palavras |
| `tests/test_lobby.py` | Salas, reagrupamento, nomes únicos, pausa, desistência, abandono, reenvio e coleta do estado |
| `tests/test_cliente.py` | Enquadramento JSON, tela do terminal, comandos do `cliente.py` e vigia da rede |
| `tests/test_servidor.py` | Nós em processos reais: nó sozinho, replicação, queda, retorno como reserva, dois primários, chaves diferentes, sincronização inicial e vitória por abandono |
| `tests/test_gateway.py` | Validação HTTP, roteamento pelo nó que atende e partida pelo gateway com queda do primário |

Os testes usam portas livres escolhidas na hora e levam menos de um minuto. O teste físico de desligar o computador deve ser feito no ambiente de apresentação (seção 12 da especificação).
