# Jogo da Forca Distribuído

Trabalho de Sistemas Distribuídos: jogo da forca cliente-servidor em Python, com sockets TCP, threads e dois servidores (primário e reserva) que mantêm o estado em RAM e o replicam entre si. Usa apenas a biblioteca padrão.

## O que funciona

- O primeiro jogador espera; o segundo inicia a partida. O terceiro espera em outra sala, e assim por diante.
- Máximo de dois jogadores por sala. Uma trava no servidor serializa as alterações; o turno permite uma jogada por vez.
- Cada jogador tem seu boneco e até seis erros. Os dois bonecos aparecem nos dois terminais.
- Na sua vez, tente uma letra ou chute a palavra inteira com `/chute`. Acertar ou errar passa a vez; um chute errado custa um membro do boneco.
- Quem completa a palavra (por letras ou pelo chute) vence; quem atinge seis erros perde.
- Nomes são únicos entre todos os jogadores ativos, em qualquer sala, sem diferenciar maiúsculas.
- Quem estava esperando e reconecta procura quem esteja esperando em outra sala: ninguém fica preso sozinho.
- Letras e chutes com acento valem sem acento: `ç` conta como `C` e `conexão` como `CONEXAO`.
- O primário envia o estado ao reserva e espera confirmação (ACK) antes de responder ao jogador.
- Se o primário cair, o reserva assume. Os clientes tentam o outro endereço e retomam suas sessões.
- Reenvios da mesma tentativa não aplicam a jogada duas vezes.

## Requisitos

- Python 3.12 ou superior (servidor e cliente). Nenhum pacote externo.
- Para a demonstração em duas máquinas: VirtualBox, uma VM Ubuntu por computador, Docker Engine e o plugin Compose.

## Teste rápido no mesmo computador

Abra quatro terminais **na pasta raiz do projeto**.

Terminal 1 — primário:
```powershell
python servidor.py
```
Terminal 2 — reserva (porta diferente apenas para testar no mesmo computador):
```powershell
python servidor.py --modo reserva --port 5002
```
Terminal 3 — Ana:
```powershell
python cliente.py --name Ana --nova-sessao
```
Terminal 4 — Bruno:
```powershell
python cliente.py --name Bruno --nova-sessao
```

O primário só aceita jogadas depois de mostrar **Reserva sincronizado. Jogadas liberadas.** Por padrão o cliente tenta `127.0.0.1:5000` e depois `127.0.0.1:5002`.

No Windows, se `python` não estiver no PATH, o script abaixo procura uma instalação (`.venv`, `python`, `py -3` ou a variável `FORCA_PYTHON`):
```powershell
.\scripts\forca.ps1 servidor
.\scripts\forca.ps1 servidor --modo reserva --port 5002
.\scripts\forca.ps1 cliente --name Ana --nova-sessao
.\scripts\forca.ps1 cliente --name Bruno --nova-sessao
```

Para demonstrar a recuperação local, jogue algumas letras e encerre o primário (Ctrl+C). O reserva assume na porta 5002 e os terminais reconectam. Este teste não substitui o teste em dois computadores físicos.

## Comandos no cliente

| Entrada | Efeito |
| --- | --- |
| Uma letra + Enter | Tenta a letra na sua vez (`ç` e `ã` valem como `C` e `A`) |
| `/chute PALAVRA` | Tenta a palavra inteira na sua vez. Certo: vence. Errado: +1 erro e a vez passa |
| `/estado` | Mostra só o estado: as duas forcas, a palavra, as letras e os chutes errados. Sem conexão, avisa e mostra o último estado conhecido |
| `/ajuda` ou `/help` | Mostra só a lista de comandos |
| `/nova` | Entra em uma nova partida depois que a atual termina |
| `/sair` | Desiste da partida (ou cancela a espera), libera o nome e fecha o cliente |
| Ctrl+C | Fecha o cliente mantendo a sessão (e o nome) para retomar depois |

Para retomar, execute com o mesmo `--name` **sem** `--nova-sessao`. A sessão fica em `sessions/<nome em minúsculas>.json` (ou no caminho de `--session`).

Dois jogadores não podem usar o mesmo nome. No mesmo computador, um segundo cliente com o mesmo nome é recusado na hora, porque o arquivo de sessão fica travado enquanto o primeiro está aberto. Em outro computador, o servidor responde `NOME_EM_USO` e o cliente encerra sem apagar a sessão anterior. O nome é liberado com `/sair`, ou quando o dono fica três minutos sem consultar o servidor fora de uma partida em andamento; nesse caso, se ele voltar, precisará escolher outro nome.

`/estado` e `/ajuda` respondem na hora, mesmo sem conexão. Letras e chutes digitados enquanto o cliente reconecta são enviados na ordem assim que houver resposta.

O cliente consulta o estado a cada meio segundo, com uma conexão TCP curta por consulta ou comando, o que simplifica a troca de servidor. A palavra secreta só é enviada aos terminais depois do fim da partida.

## Duas máquinas com VirtualBox e Docker

1. Crie uma VM Ubuntu em cada computador físico, ambas com rede **Bridge** na mesma rede local.
2. Instale Docker Engine e o plugin Compose em cada VM e copie o projeto para ambas.
3. Descubra os IPs das VMs com `ip a`. Os exemplos usam `192.168.1.10` (VM 1) e `192.168.1.20` (VM 2); substitua pelos seus.
4. Em cada VM, copie `.env.example` para `.env`.
5. Na VM 1 configure `MODO=primario`. Na VM 2 configure `MODO=reserva` e `PRIMARY_HOST=192.168.1.10`. Use a mesma `REPLICATION_KEY` nas duas.
6. Suba primeiro a VM 1 e depois a VM 2:

```bash
docker compose up --build
```

Libere TCP 5000 das duas VMs para os clientes e TCP 5001 da VM primária para a reserva. Em redes com isolamento de dispositivos (comum em Wi-Fi), o modo Bridge pode não permitir comunicação; confirme a conectividade antes da apresentação. A chave de replicação é apenas uma proteção básica para a rede de aula; o tráfego não usa TLS.

Os clientes rodam com Python fora do Docker:
```powershell
python cliente.py --name Ana --servers 192.168.1.10:5000,192.168.1.20:5000 --nova-sessao
python cliente.py --name Bruno --servers 192.168.1.10:5000,192.168.1.20:5000 --nova-sessao
```
A lista também pode vir da variável `CLIENT_SERVERS`.

Espere a mensagem **Reserva sincronizado. Jogadas liberadas.** no log do primário. Jogue, confira o turno e desligue o computador físico do primário. Após cerca de cinco segundos sem heartbeat, o reserva abre a porta 5000 em seu próprio IP; os clientes reconectam e a partida continua. Execute os clientes no computador que ficará ligado, ou em outros dispositivos: um cliente no computador desligado também para.

### Configuração

| Variável | Uso | Padrão |
| --- | --- | --- |
| `MODO` | `primario` ou `reserva` | `primario` |
| `PRIMARY_HOST` | IP do primário, usado pelo reserva | `127.0.0.1` |
| `REPLICATION_KEY` | Chave compartilhada do canal de replicação | `forca-aula` |
| `GAME_PORT` / `SYNC_PORT` | Portas de jogadores e de replicação (fora do Compose) | `5000` / `5001` |
| `CLIENT_SERVERS` | Lista de servidores do cliente | `127.0.0.1:5000,127.0.0.1:5002` |

As mesmas opções existem na linha de comando: `python servidor.py --help` e `python cliente.py --help`.

## Limites desta versão

- Demonstra a queda do primário com o reserva e a rede dos clientes funcionando. Não é um sistema de alta disponibilidade para produção.
- Antes da primeira sincronização, o primário não aceita alterações. Se perder o reserva, ele pausa e precisa ser reiniciado. Ou seja, a queda do **reserva** interrompe o jogo; a tolerância é para a queda do primário.
- Depois da promoção, o reserva aceita jogadas sozinho, sem proteção contra uma segunda falha. Não há reintegração automática de um servidor que volta.
- Se os dois servidores encerrarem, as partidas se perdem: não há persistência em disco no servidor. Os arquivos em `sessions` guardam só a identidade e o comando pendente do cliente.
- Para repetir a demonstração, encerre ambos os servidores, inicie de novo primário e reserva e abra os clientes com `--nova-sessao`. Não religue o antigo primário durante uma partida recuperada.
- A recuperação leva alguns segundos. Após a troca, a partida fica pausada até os dois jogadores reconectarem.
- Quem fecha o terminal sem `/sair` mantém a vaga; após cinco segundos sem consultas, a partida aparece pausada. Não há prazo de abandono: o adversário pode desistir com `/sair`. O nome fica reservado enquanto a partida estiver em andamento e, fora dela, por três minutos.
- Salas encerradas não são removidas da memória. Dos recibos, fica só o último comando de cada jogador, e comandos de quem nunca entrou não são guardados. Cada mensagem é limitada a 2 MB e a replicação envia o estado completo, o que basta para uma demonstração pequena.

## Como ler o código

| Arquivo | Responsabilidade |
| --- | --- |
| `servidor.py` | Threads, trava, TCP, replicação, heartbeat e promoção |
| `cliente.py` | Teclado, consultas, sessão e reconexão |
| `forca/lobby.py` | Entrada nas salas, nomes únicos, sessão e reconhecimento de reenvios |
| `forca/game.py` | Regras de uma partida |
| `forca/wire.py` | Envio e leitura de JSON por linha |
| `forca/ui.py` | Desenho dos dois bonecos |
| `forca/words.txt` | Lista de palavras, uma por linha. Acentos e minúsculas são normalizados; o servidor não inicia se houver espaços, hífens ou números |
| `tests/` | Testes automatizados (unittest) |
| `scripts/forca.ps1` | Atalho para servidor, cliente e testes no Windows |

Leia primeiro `game.py`, depois `lobby.py` e por último `servidor.py`. Em `Server.request`, a sequência principal é: criar cópia → aplicar regra → replicar e esperar ACK → adotar estado → responder. O reserva recebe a cópia em `Server.follow`; se a conexão cai depois da primeira sincronização, ele assume.

## Documentação

- [docs/especificacao-jogo-forca.md](docs/especificacao-jogo-forca.md): requisitos, garantias, limites e roteiro da apresentação.
- [docs/protocolo-etapa-1.md](docs/protocolo-etapa-1.md): mensagens dos canais de jogadores e de replicação.
- [ROADMAP.md](ROADMAP.md): o que foi feito e o que falta.
- `scripts/gerar_especificacao_pdf.py` gera o PDF da especificação em `output/pdf/` (requer `reportlab` e as fontes Arial do Windows).

## Testes

```powershell
python -m unittest discover -s tests -v
# Ou:
.\scripts\forca.ps1 testes
```

| Arquivo | Cobre |
| --- | --- |
| `tests/test_game.py` | Turnos, letras, chute da palavra, acentos, vitória, seis erros e validação da lista de palavras |
| `tests/test_lobby.py` | Formação e reagrupamento das salas, nomes únicos e sua liberação, pausa, desistência, reenvio e tamanho dos recibos |
| `tests/test_cliente.py` | Enquadramento JSON, tela de `/estado`, resultado para vencedor e perdedor, lista de `/ajuda`, comandos e trava da sessão |
| `tests/test_servidor.py` | Primário e reserva em processos reais: replicação, queda abrupta, reenvio após a troca, pausa do primário, sincronização inicial, chave com acento e comando malformado |

Os testes de servidor usam portas livres escolhidas na hora e levam poucos segundos. O teste físico de desligar o computador deve ser feito no ambiente de apresentação (seção 12 da especificação).
