# Especificação do jogo da forca distribuído

Python com sockets TCP em duas máquinas físicas com VMs e Docker

Versão 2.0 | 26 de setembro de 2026 | Sistemas Distribuídos

## 1 Objetivo e decisões do projeto

Desenvolver um jogo da forca cliente e servidor em Python. Os jogadores são organizados automaticamente em salas de duas pessoas. O segundo jogador inicia a partida; o terceiro aguarda um quarto em outra sala, e assim sucessivamente. Várias partidas funcionam ao mesmo tempo, cada uma com seu próprio controle de turnos e seus próprios dois bonecos.

**O foco da disciplina é demonstrar distribuição real, replicação de estado, coordenação das jogadas e recuperação automática após a queda do servidor ativo.** A aplicação deve continuar uma partida já iniciada quando o computador que hospeda o servidor primário for desligado, preservando as jogadas confirmadas, as salas em espera e a identidade dos jogadores.

| Decisão | Especificação |
| --- | --- |
| Linguagem | Python 3.12 ou superior, somente biblioteca padrão |
| Comunicação | Sockets TCP com protocolo JSON delimitado por quebra de linha |
| Infraestrutura | Dois computadores físicos diferentes, cada um com uma VM Linux |
| Virtualização | VirtualBox com rede em modo bridge |
| Empacotamento | Dockerfile e Docker Compose para o servidor |
| Organização | Um servidor primário e um reserva sincronizado |
| Estado | Em memória (RAM) nos dois servidores; replicação síncrona feita pela aplicação |
| Concorrência | threading.Lock no servidor e versão por sala |
| Cliente | Interface de terminal em Python com os dois bonecos visíveis |
| Cenário de falha | Uma falha por vez, por parada do processo ou desligamento do computador |

As regras de vitória, os tempos e a interface definidos aqui são decisões do projeto. Os critérios da seção 12 são metas de aceitação; o que já foi verificado está indicado no ROADMAP.

## 2 Escopo e garantias do sistema distribuído

### 2.1 Garantia pretendida

Com os dois servidores sincronizados, o sistema suporta a queda do primário e continua no reserva. A recuperação causa uma pausa visível de alguns segundos. As conexões TCP antigas não são transferidas: o cliente abre novas conexões com o outro endereço e retoma a sessão.

**Nenhuma jogada que o servidor tenha confirmado ao cliente enquanto os dois servidores estavam sincronizados pode desaparecer.** O primário só responde depois que o reserva confirma ter recebido o novo estado. Uma requisição cuja resposta não chegou ao cliente pode ter sido aplicada; nesse caso o cliente reenvia o mesmo identificador de requisição e recebe o resultado já registrado, sem executar a jogada duas vezes.

Após a promoção, o reserva opera com uma única cópia e deixa de ter proteção contra outra falha. Esta versão não reintegra automaticamente o servidor que volta.

### 2.2 Limites com apenas dois servidores

O modelo pressupõe falha por parada: o servidor indisponível realmente deixa de executar, e a rede entre os equipamentos vivos permanece funcional. O timeout do heartbeat é um indício de falha, não uma prova de que o outro computador desligou.

A proteção é assimétrica. Se o primário perder o contato com o reserva, ele se pausa e recusa novas alterações, pois não consegue obter a segunda cópia. Se o reserva perder o contato com o primário, ele se promove. Assim, em uma interrupção de rede entre os dois servidores, apenas o reserva continua aceitando jogadas, e o primário não confirma alterações divergentes. Em contrapartida, **a queda do reserva interrompe o jogo**: o primário pausado precisa ser reiniciado junto com um novo reserva.

Garantias fortes sob qualquer partição de rede exigiriam um terceiro participante de decisão ou um mecanismo que impeça o antigo ativo de voltar a escrever. Esses recursos ficam fora do escopo de duas máquinas deste trabalho. Por isso, o antigo primário não deve ser religado durante uma partida recuperada.

### 2.3 Condições da apresentação

- As duas VMs servidoras devem estar em computadores físicos diferentes.
- O roteador ou switch deve continuar ligado e não depender de um dos computadores testados.
- Os clientes observados devem ficar em um equipamento que permaneça ligado. Com apenas dois computadores, os clientes rodam em terminais separados no computador do reserva.
- Antes de cada novo teste de falha, os dois servidores devem ser reiniciados e sincronizados, e os clientes abertos com nova sessão.
- A demonstração deve funcionar sem internet, com a imagem Docker construída previamente.

## 3 Arquitetura física e lógica

### 3.1 Distribuição dos componentes

Cada computador hospeda uma VM Linux. Dentro de cada VM, o Docker executa o mesmo programa servidor; o papel é definido pela variável MODO. O primário atende todas as salas; o reserva guarda uma cópia completa do estado e só abre a porta de jogadores quando é promovido.

| Camada | Computador A | Computador B |
| --- | --- | --- |
| Máquina física | Host A | Host B |
| VM | Linux A com rede em bridge | Linux B com rede em bridge |
| Container | servidor.py com MODO=primario | servidor.py com MODO=reserva |
| Papel inicial | Primário, aguardando o reserva | Reserva, conectado ao primário |
| Dados | Estado em RAM | Cópia do estado em RAM |
| Portas | 5000 jogadores, 5001 replicação | 5000 jogadores após promoção |

O cliente recebe a lista dos dois endereços pela opção --servers ou pela variável CLIENT_SERVERS. Ele tenta os endereços em rodízio até obter uma resposta válida. Não há proxy nem banco central.

### 3.2 Responsabilidades

O cliente coleta o nome, mostra a sala, envia intenções de jogada e desenha os estados recebidos. O servidor valida identidade, participação na sala, turno, versão, letra, resultado, ocupação das salas e regras de vitória. O cliente nunca decide sozinho se acertou ou venceu.

O canal de replicação transmite o estado completo após cada alteração, recebe a confirmação e troca heartbeats. VirtualBox fornece as VMs; Docker padroniza a execução dentro delas. A recuperação entre computadores é responsabilidade da aplicação, não da política de reinício do container.

## 4 Requisitos funcionais e formação das salas

### 4.1 Identificação e entrada

**RF01 Identificação.** O jogador informa um nome de exibição de 1 a 24 caracteres imprimíveis. O cliente gera um token aleatório e o salva em arquivo antes da primeira requisição; o servidor usa o SHA-256 do token como player_id. A identidade é o token, não o nome.

**RF01a Nomes únicos.** Dois jogadores ativos não podem ter o mesmo nome, estejam ou não na mesma sala. A comparação ignora maiúsculas e espaços nas pontas. Um ENTRAR com nome em uso é recusado com NOME_EM_USO. O nome fica reservado enquanto o jogador está ativo, inclusive desconectado, e é liberado quando ele envia SAIR. Para que um nome não fique preso por quem fechou o terminal e não voltou, ele também pode ser reaproveitado quando o dono passa 180 segundos sem consultar o servidor e não está em uma partida em andamento; nesse caso o antigo dono deixa de ser ativo, sua sala de espera é cancelada e, se voltar, precisará de outro nome. Durante os primeiros 180 segundos de um servidor, inclusive logo após a promoção do reserva, nenhum nome é liberado, dando tempo para todos reconectarem. No mesmo computador, o cliente trava o arquivo de sessão enquanto está aberto, de modo que um segundo cliente com o mesmo nome não reutiliza nem sobrescreve o token do primeiro.

**RF02 Distribuição automática.** Ao receber ENTRAR, o servidor procura uma sala AGUARDANDO com um único jogador conectado. Se houver, ocupa a segunda vaga e inicia a partida. Caso contrário, cria uma nova sala. Um jogador ocupa apenas uma sala não encerrada; um novo ENTRAR durante uma partida devolve a mesma sala e avisa que ela está em andamento.

**RF02a Reagrupamento.** Se um jogador que já espera sozinho enviar ENTRAR e houver outra sala com um jogador esperando e conectado, ele é levado a essa sala, a partida começa e a sala antiga é cancelada. O cliente envia esse ENTRAR automaticamente ao reconectar enquanto espera. Assim, dois jogadores que ficaram esperando em salas separadas, porque um deles estava desconectado quando o outro chegou, não ficam presos.

**RF03 Lotação.** Uma sala com dois jogadores não recebe outro jogador.

| Ordem de entrada | Sala atribuída | Resultado |
| --- | --- | --- |
| Jogador 1 | Sala 1 | Aguarda adversário |
| Jogador 2 | Sala 1 | Inicia a partida com o jogador 1 |
| Jogador 3 | Sala 2 | Aguarda adversário |
| Jogador 4 | Sala 2 | Inicia a partida com o jogador 3 |
| Jogador 5 | Sala 3 | Aguarda adversário |

**RF04 Concorrência na entrada.** Procurar sala, ocupar a vaga e associar o jogador acontecem dentro da mesma trava do servidor. Requisições simultâneas ou repetidas não ocupam a mesma vaga nem criam duas entradas para a mesma pessoa.

**RF05 Início.** A partida começa quando o segundo jogador entra. A palavra é sorteada no servidor a partir de forca/words.txt, e o primeiro jogador que entrou recebe o primeiro turno. Ao iniciar, o servidor normaliza a lista, removendo acentos e convertendo para maiúsculas, e se recusa a iniciar, com mensagem clara, se alguma linha tiver espaços, hífens, números ou mais de 30 letras.

**RF06 Salas independentes.** Cada sala possui sua palavra, suas letras, seus erros e seu turno.

As salas assumem os estados AGUARDANDO, EM_JOGO, ENCERRADA e CANCELADA. PAUSADA é exibido quando a sala está EM_JOGO e algum participante não consultou o servidor nos últimos 5 segundos; jogadas ficam bloqueadas até a reconexão.

### 4.2 Encerramento e nova partida

Ao terminar, ambos recebem o resultado do próprio ponto de vista, como Você venceu! Bruno chegou a seis erros ou Você perdeu. Ana completou a palavra, além da palavra completa. Os códigos internos do motivo não aparecem na tela. O comando /nova no cliente envia outro ENTRAR e pode formar outro par. A sala encerrada permanece na memória e não é reutilizada.

## 5 Regras do jogo e interface

### 5.1 Regras adotadas

- Cada sala usa uma palavra compartilhada pelos dois jogadores, sorteada uma única vez.
- As palavras usam apenas A a Z, sem espaços nem hífens. Letras e chutes com acento valem como a letra sem acento (ç vale C; conexão vale CONEXAO) e minúsculas são convertidas para maiúsculas; outros caracteres são rejeitados.
- Cada jogador possui um boneco próprio e até seis erros: cabeça, tronco, braço esquerdo, braço direito, perna esquerda e perna direita.
- Na sua vez, o jogador tenta uma letra ou chuta a palavra inteira com o comando /chute.
- Uma letra correta revela todas as suas ocorrências. Uma letra incorreta acrescenta um erro apenas ao autor.
- Um chute igual à palavra encerra a partida com vitória do autor e motivo PALAVRA_COMPLETA. Um chute diferente informa que a palavra não coincide, acrescenta um erro ao autor e fica registrado na lista de chutes errados da sala.
- Cada tentativa válida, de letra ou de palavra, alterna o turno quando a partida continua.
- Letra ou palavra já tentada na sala, entrada inválida, jogada fora da vez ou com versão desatualizada é rejeitada sem alterar turno ou erros. O chute aceita de 1 a 30 letras, sem espaços, hífens ou números.
- Quem revelar a última letra ou acertar o chute vence. Se um jogador atingir seis erros, inclusive por um chute errado, o adversário vence.

### 5.2 Exibição

O cliente mostra o ID e o estado da sala, os nomes dos dois jogadores, os dois desenhos da forca lado a lado, os erros de cada um, a palavra mascarada, as letras tentadas, os chutes errados e de quem é a vez. A tela é redesenhada sempre que o estado muda. Há mensagens para aguardando adversário, sua vez, vez do adversário, jogada inválida, conexão perdida, partida pausada e partida encerrada. O papel do servidor aparece ao conectar; revisões e promoções ficam no log do servidor.

O comando /estado mostra apenas essa tela de estado, sem a lista de comandos. O comando /ajuda, ou /help, mostra apenas a lista de comandos. Comandos desconhecidos e entradas com mais de uma letra recebem um aviso local, sem ir ao servidor. /estado, /ajuda e esses avisos respondem na hora, mesmo sem conexão; sem conexão, /estado avisa e mostra o último estado conhecido. Jogadas digitadas enquanto o cliente reconecta são enviadas na ordem, com a versão mais recente da sala.

### 5.3 Desconexão e desistência

Quando um cliente para de consultar, a sala aparece pausada após 5 segundos e a vaga é preservada. Uma reconexão com a mesma sessão retoma a sala original. Não há prazo de abandono nem limite de tempo para escolher uma letra; o adversário pode encerrar a partida com /sair.

Um jogador sozinho que envia SAIR cancela a sala. Em uma partida iniciada, SAIR caracteriza desistência e dá a vitória ao adversário. Em ambos os casos o jogador deixa de estar ativo e seu nome é liberado. Um novo jogador nunca substitui um participante ausente.

## 6 Controle de concorrência

**RF07 Exclusão mútua.** O servidor usa um threading.Lock para tornar indivisível a sequência validar, aplicar, replicar e adotar o novo estado. Cada conexão é atendida por uma thread; um BoundedSemaphore limita a 64 as conexões simultâneas, e as excedentes são fechadas.

A trava é global, não por sala, e é mantida durante a replicação. Isso simplifica o raciocínio e é suficiente para a escala da demonstração, pois cada comando é curto e nenhum espera o jogador pensar. A versão da sala (room_version) enviada pelo cliente rejeita jogadas baseadas em um estado antigo.

**RF08 Autoridade do servidor.** O servidor recusa a jogada fora da vez mesmo que um cliente modificado envie a mensagem. O prompt do cliente é apenas uma conveniência.

A trava protege as threads de um processo, não os dois servidores. A existência de um único servidor aceitando alterações decorre do protocolo primário e reserva descrito na seção 8.

## 7 Estado e replicação

### 7.1 Dados replicados

| Registro | Conteúdo |
| --- | --- |
| world | deployment_id, jogadores, salas e contador de salas |
| Jogador | player_id, nome, sala associada e se está ativo |
| Sala | Participantes, palavra, letras, chutes errados, erros, turno, estado, versão, vencedor e motivo |
| receipts | Para cada jogador, o request_id, a impressão digital e o resultado do último comando |
| revision | Contador global de alterações |

Sockets, threads e presença dos jogadores não são replicados. Após a promoção, o reserva começa sem informação de presença, e as salas aparecem pausadas até os jogadores reconectarem. A palavra secreta é replicada, mas só é enviada completa aos clientes após o encerramento.

### 7.2 Sequência de uma alteração

**RD01 Replicação antes da confirmação.** Uma operação que altera dados só é confirmada ao cliente depois que o reserva guardou o novo estado. Vale para ENTRAR, JOGAR, CHUTAR e SAIR, incluindo o sorteio da palavra e a reserva do nome.

1. O primário cria uma cópia profunda do estado atual.
2. Aplica o comando à cópia, registra o recibo e incrementa a revisão.
3. Envia o estado completo ao reserva pelo canal de replicação.
4. O reserva substitui sua cópia e responde com ACK contendo a revisão.
5. O primário adota a cópia e responde ao jogador com o resultado e o estado.

Se o ACK não chegar, o primário descarta a cópia, se pausa e responde retry; o cliente tenta outro endereço com o mesmo comando. Se o primário cair depois do passo 4, a alteração existe no reserva, e o reenvio do mesmo request_id devolve o resultado registrado.

### 7.3 Idempotência

**RD02 Uma requisição não produz dois efeitos.** Cada comando de alteração recebe um UUID gerado pelo cliente e salvo no arquivo de sessão antes do envio. Ao reenviar, o cliente preserva identificador e conteúdo. O servidor devolve o resultado já registrado; reutilizar o identificador do último comando com outro conteúdo é rejeitado.

Como o cliente tem um único comando pendente por vez, o servidor guarda apenas o recibo do último comando de cada jogador, e nenhum de quem nunca entrou. Isso mantém o estado replicado pequeno: antes, cada comando, até os rejeitados, acrescentava cerca de 280 bytes, e alguns milhares bastavam para ultrapassar o limite de 2 MB e pausar o primário. Os recibos são replicados com o estado. Trata-se de efeito único por identificador, não de entrega exatamente uma vez pela rede.

## 8 Falha e recuperação

### 8.1 Papéis do servidor

| Papel | Comportamento |
| --- | --- |
| Primário aguardando | Atende PING e recusa os demais comandos com retry até o reserva sincronizar |
| Primário sincronizado | Atende jogadores e replica cada alteração |
| Primário pausado | Perdeu o reserva; recusa comandos com retry até ser reiniciado |
| Reserva | Conecta ao primário, recebe o estado e responde heartbeats; não atende jogadores |
| Reserva promovido | Atende jogadores sozinho a partir da última revisão recebida |

### 8.2 Inicialização

O primário inicia com estado vazio e um novo deployment_id. O reserva conecta à porta 5001 do primário, apresenta a chave de replicação e recebe o estado completo. Só depois do ACK dessa cópia o primário registra no log a mensagem Reserva sincronizado, envia logo o primeiro heartbeat e passa a aceitar jogadas. Se a cópia inicial ou o ACK falharem, o primário não se pausa: registra a falha e espera outra tentativa do reserva. A chave de replicação é comparada em bytes UTF-8, de modo que chaves com acento funcionam e uma chave inválida não derruba o canal. O compose.yaml usa restart "no" para que um antigo primário não volte sozinho como ativo com estado vazio.

### 8.3 Detecção e promoção

**RD03 Heartbeat.** O primário envia um heartbeat ao reserva a cada 0,5 segundo e espera a resposta por até 3 segundos. O reserva espera mensagens do primário por até 5 segundos.

**RD04 Assunção.** O reserva só pode se promover depois de receber a segunda mensagem do primário, um heartbeat ou um novo estado, que prova que o primário recebeu o ACK da cópia inicial. A partir daí, qualquer erro ou timeout no canal de replicação faz o reserva se promover e abrir a porta de jogadores. Se a conexão cair antes da segunda mensagem, ele apenas tenta sincronizar de novo; assim, o primário pode deixar de se pausar quando a sincronização inicial falha sem risco de dois servidores ativos. Ao encerrar o processo do primário, a conexão é fechada e a promoção é imediata; ao desligar o computador, ocorre após o timeout de 5 segundos. Não é necessário iniciar outra VM: a VM reserva já está ligada.

Se o primário detectar a perda do reserva, ele se pausa em vez de continuar com uma cópia, como descrito na seção 2.2.

### 8.4 Reconexão do cliente

**RD05 Retomada automática.** O cliente usa timeouts de aplicação (2 segundos para conectar e 5 para ler). Em falha ou resposta retry, passa ao próximo endereço da lista após 0,5 segundo, mantendo token e comando pendente. Ao conectar, a próxima consulta devolve o estado completo e autoritativo da sala.

O deployment_id recebido na primeira resposta é salvo na sessão. Se o cliente encontrar um servidor de outra execução, recebe uma resposta fatal e encerra, em vez de criar uma identidade nova sem perceber.

### 8.5 Retorno de um servidor

Esta versão não sincroniza um servidor que volta. O antigo primário, se religado, teria estado vazio e outro deployment_id; os clientes antigos o recusariam. Para restabelecer a redundância, encerram-se ambos os servidores e inicia-se uma nova execução, com primário, reserva e clientes com nova sessão.

## 9 Protocolo de comunicação

### 9.1 Transporte e enquadramento

**RT01 Sockets TCP.** Clientes usam a porta 5000; os servidores usam a porta 5001 para replicação e heartbeat. Ambas são configuráveis. Cada mensagem é um objeto JSON UTF-8 terminado por LF, com limite de 2 MB. A leitura acumula bytes até o delimitador, tratando mensagens parciais ou agrupadas pelo TCP.

Cada comando de jogador usa uma conexão curta: conectar, enviar, receber a resposta e fechar. O cliente consulta o estado a cada 0,5 segundo. JSON inválido, excesso de tamanho ou campos inválidos produzem erro controlado sem derrubar o servidor.

### 9.2 Mensagens

| Direção | Tipos | Finalidade |
| --- | --- | --- |
| Cliente para servidor | PING, ESTADO | Verificar papel, registrar presença e obter a sala |
| Cliente para servidor | ENTRAR, JOGAR, CHUTAR, SAIR | Ocupar sala, tentar letra, chutar a palavra e desistir |
| Servidor para cliente | ok, retry, fatal | Resultado, servidor indisponível ou execução diferente |
| Primário para reserva | state, heartbeat | Replicar e monitorar |
| Reserva para primário | key, ack, heartbeat | Autenticar, confirmar e responder |

Exemplo de comando JOGAR:

```json
{"type":"JOGAR","request_id":"uuid-da-operacao",
 "token":"segredo-do-cliente","deployment":"uuid-da-execucao",
 "letter":"A","version":8}
```

O exemplo está formatado para leitura; na rede ocupa uma linha. O autor da jogada é determinado pelo token, e não por um player_id enviado pelo cliente. Os campos completos, o estado público e os códigos de erro estão em docs/protocolo-etapa-1.md.

### 9.3 Proteção mínima

Tokens são imprevisíveis, guardados apenas no arquivo de sessão do cliente e não aparecem nos logs. O canal de replicação exige uma chave compartilhada comparada em tempo constante. O arquivo .env real e a pasta sessions não devem ser versionados. O TCP sem TLS fica restrito à rede local da apresentação.

## 10 Docker e ambiente das VMs

### 10.1 Artefatos

**RI01 Dockerização.** O repositório contém Dockerfile, compose.yaml, .dockerignore e .env.example. Como o projeto usa apenas a biblioteca padrão, não há arquivo de dependências; a versão do Python é fixada na imagem python:3.12.13-slim.

Cada VM executa seu próprio projeto Compose com um único serviço, servidor, que publica as portas 5000 e 5001 e escreve os logs em stdout. A comunicação entre as VMs usa os IPs da rede bridge e as portas publicadas, não o nome de serviço de uma rede Docker local. Os clientes rodam com Python fora do container.

### 10.2 Configuração

| Variável | Finalidade |
| --- | --- |
| MODO | primario ou reserva |
| PRIMARY_HOST | IP da VM do primário, usado pelo reserva |
| REPLICATION_KEY | Chave compartilhada, igual nos dois servidores |
| GAME_PORT / SYNC_PORT | 5000 / 5001 (fora do Compose) |
| CLIENT_SERVERS | Lista de servidores do cliente, por exemplo 192.168.1.10:5000,192.168.1.20:5000 |

Os endereços são exemplos e devem ser substituídos pelos IPs reais da rede.

### 10.3 VirtualBox e rede

Uma VM Linux por computador, com 2 vCPUs, 2 GB de RAM e 15 GB de disco, é uma configuração inicial suficiente. Usar a mesma distribuição e versões nas duas VMs facilita a reprodução.

A placa de rede deve estar em modo bridge, para que cada VM tenha endereço acessível na rede local. Preferir conexão cabeada e IP fixo ou reserva de DHCP. Verificar isolamento entre clientes no Wi-Fi e regras de firewall. A porta 5000 das duas VMs deve ser acessível aos clientes, e a 5001 do primário deve ser acessível ao reserva.

### 10.4 Operação

Em cada VM: copiar .env.example para .env, ajustar MODO e PRIMARY_HOST e executar docker compose up --build, primeiro no primário e depois no reserva. Para acompanhar os logs em segundo plano, usar docker compose up -d e docker compose logs -f servidor. Para encerrar, docker compose down. Os comandos detalhados estão no README.

## 11 Observabilidade e critérios de qualidade

**RN01 Logs.** O servidor registra horário, porta atendida, sincronização do reserva, cada revisão confirmada com o tipo de comando, perda do reserva e promoção com a revisão assumida. Tokens e palavras secretas não são registrados.

**RN02 Metas.** Na rede local, demonstrar pelo menos cinco clientes em três salas, confirmação de jogada perceptivelmente imediata e recuperação em até 15 segundos após desligar o primário. São metas a medir na apresentação; a integridade do estado tem prioridade sobre a velocidade.

**RN03 Isolamento.** Uma mensagem inválida ou um cliente lento não derruba o servidor: cada conexão tem timeout de 4 segundos, as mensagens têm tamanho limitado e o número de conexões simultâneas é limitado a 64.

## 12 Plano de testes e critérios de aceitação

### 12.1 Matriz de aceitação

| ID | Teste | Critério de aprovação |
| --- | --- | --- |
| T01 | Entrar com um jogador | Sala criada e tela de espera |
| T02 | Entrar com o segundo | Mesma sala; partida iniciada nos dois clientes |
| T03 | Entrar com terceiro e quarto | Outra sala; nenhuma com mais de dois jogadores |
| T04 | Jogada fora da vez | Erro FORA_DA_VEZ; estado e turno preservados |
| T05 | Letra incorreta | Só o autor ganha um erro; ambos veem os dois bonecos |
| T06 | Acerto e letra repetida | Revelação correta; repetição rejeitada sem mudar o turno |
| T07 | Vitória, seis erros e desistência | Resultado consistente nos dois clientes |
| T08 | Reenvio do mesmo request_id | Mesmo resultado, sem nova jogada |
| T09 | JSON inválido ou mensagem grande | Erro controlado sem queda do servidor |
| T10 | Primário sem reserva | Jogadas recusadas até a sincronização |
| T11 | Desligar o computador do primário | Partidas e sala em espera retomadas no reserva |
| T12 | Queda do primário após o ACK e antes da resposta | Reenvio resolve a ação sem duplicar erro ou turno |
| T13 | Encerrar o reserva | Primário pausa e não confirma novas jogadas |
| T14 | Cliente fecha e reabre | Volta à mesma sala; adversário vê a partida pausada |
| T15 | Cliente com sessão de outra execução | Resposta fatal e orientação para usar nova sessão |
| T16 | Chute certo | Autor vence com PALAVRA_COMPLETA; palavra revelada aos dois |
| T17 | Chute errado | Aviso de que não coincide; +1 erro ao autor; vez passa; chute listado |
| T18 | Mesmo nome em outra sala ou outro computador | NOME_EM_USO; o primeiro jogador não é afetado |
| T19 | Mesmo nome no mesmo computador | Segundo cliente recusado pela trava da sessão |
| T20 | /estado e /ajuda | Estado sem lista de comandos; ajuda só com a lista; ambos respondem sem conexão |
| T21 | Dois jogadores esperando em salas separadas | Quem reconecta entra na sala do outro e a partida começa |
| T22 | Nome de quem sumiu há três minutos | Liberado fora de partida; mantido durante uma partida |
| T23 | Reserva que some na sincronização inicial | Primário não pausa e sincroniza com o próximo reserva |
| T24 | Chave com acento ou comando malformado | Resposta controlada, sem derrubar o servidor nem o canal de replicação |
| T25 | Palavra com acento, espaço ou hífen na lista | Acento normalizado; espaço ou hífen impedem o servidor de iniciar |

A pasta tests contém testes automatizados com unittest para T01 a T10, T12 (reenvio após a troca de servidor), T13 e T16 a T25 (em T20 e T21, a parte que depende do teclado e da reconexão do cliente foi verificada manualmente), com os servidores em processos reais e TCP local. Eles são executados com python -m unittest discover -s tests.

### 12.2 Execução dos testes de falha

Encerrar o processo testa a detecção por conexão fechada; desligar a VM ou o computador testa a detecção por timeout. T11 precisa incluir o desligamento físico solicitado pelo professor.

Para medir a preservação, registrar antes e depois a sala, a versão, as letras, os erros e o turno. Antes de cada novo teste de falha, reiniciar os dois servidores e abrir os clientes com nova sessão.

## 13 Roteiro da apresentação

1. Mostrar os dois computadores, as VMs e os containers; identificar o primário e o reserva.
2. Mostrar no log do primário a mensagem Reserva sincronizado e que o cliente conhece os dois endereços.
3. Abrir cinco clientes: os dois primeiros iniciam a sala 1, os dois seguintes a sala 2 e o quinto aguarda na sala 3.
4. Fazer acertos e erros nas duas partidas. Mostrar os dois bonecos em ambos os clientes e a rejeição de uma jogada fora da vez.
5. Anotar versões e turnos e mostrar no log as revisões confirmadas.
6. Desligar fisicamente o computador do primário, mantendo os clientes e a rede ligados. Cronometrar a interrupção.
7. Mostrar a mensagem de conexão perdida, a promoção do reserva no log e a retomada das salas 1 e 2 sem reiniciar as partidas.
8. Abrir um sexto cliente e mostrar que ele entra na sala 3 com o jogador que já aguardava.
9. Fazer uma nova jogada e explicar que o sistema opera agora com uma única cópia e que o antigo primário não deve ser religado nesta execução.

Com apenas dois computadores, todos os clientes ficam em terminais no computador do reserva. Desligar o computador de um jogador também derruba aquele cliente; isso não é resolvido pela redundância dos servidores.

## 14 Organização da implementação e entregáveis

### 14.1 Componentes

| Componente | Responsabilidade |
| --- | --- |
| forca/game.py | Regras puras, validação de letras e resultado |
| forca/lobby.py | Salas, vagas, sessões, entrada, saída e recibos |
| forca/wire.py | Envio e leitura de JSON por linha |
| forca/ui.py | Desenho da tela e dos dois bonecos |
| servidor.py | Sockets, threads, trava, replicação, heartbeat e promoção |
| cliente.py | Teclado, consultas, sessão, comando pendente e reconexão |
| forca/words.txt | Lista de palavras |
| tests | Regras, salas, nomes, cliente e replicação com queda de processo |

### 14.2 Entrega final

A entrega contém código Python, testes automatizados, Dockerfile, Compose, configuração de exemplo, lista de palavras, README de instalação nas duas VMs, descrição do protocolo e esta especificação. Falta o relatório do teste de desligamento físico, acompanhado no ROADMAP.

O projeto será considerado concluído quando os testes funcionais e de recuperação passarem no modelo admitido, a execução for reproduzível com Docker e a demonstração comprovar continuidade das partidas após o desligamento físico.

## 15 Referências técnicas

As referências sustentam os recursos de infraestrutura e biblioteca. As regras do jogo, mensagens, tempos e o protocolo primário e reserva são decisões deste projeto. Consulta em 26 de setembro de 2026.

- Python socket: interface de baixo nível para sockets TCP. https://docs.python.org/3/library/socket.html
- Python threading: threads, Lock e BoundedSemaphore. https://docs.python.org/3/library/threading.html
- Python hmac: compare_digest para comparar a chave de replicação. https://docs.python.org/3/library/hmac.html
- Python secrets: geração de tokens de sessão. https://docs.python.org/3/library/secrets.html
- Docker Compose services: serviços, portas e política de reinício. https://docs.docker.com/reference/compose-file/services/
- Oracle VirtualBox Virtual Networking: opções de rede e bridge. https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/networkingdetails.html
- etcd FAQ: maioria e tolerância a falhas; justifica por que dois servidores não formam consenso. https://etcd.io/docs/v3.6/faq/
