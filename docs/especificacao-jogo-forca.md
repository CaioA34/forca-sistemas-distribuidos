# Especificação do jogo da forca distribuído

Python com sockets TCP em duas máquinas físicas com VMs e Docker, jogado pelo navegador

Versão 3.0 | 30 de setembro de 2026 | Sistemas Distribuídos

## 1 Objetivo e decisões do projeto

Desenvolver um jogo da forca cliente e servidor em Python. Os jogadores são organizados automaticamente em salas de duas pessoas. O segundo jogador inicia a partida; o terceiro aguarda um quarto em outra sala, e assim sucessivamente. Várias partidas funcionam ao mesmo tempo, cada uma com seu próprio controle de turnos e seus próprios dois bonecos.

**O foco da disciplina é demonstrar distribuição real, replicação de estado, coordenação das jogadas e recuperação automática após a queda do servidor ativo.** A aplicação deve continuar uma partida já iniciada quando o computador que hospeda o servidor primário for desligado, preservando as jogadas confirmadas, as salas em espera e a identidade dos jogadores.

| Decisão | Especificação |
| --- | --- |
| Linguagem | Python 3.12 ou superior, somente biblioteca padrão |
| Comunicação | Sockets TCP com protocolo JSON delimitado por quebra de linha entre gateway e nós e entre os nós; HTTP entre navegador e gateway |
| Infraestrutura | Dois computadores físicos diferentes, cada um com uma VM Linux; gateway em container na instância Oracle |
| Virtualização | VirtualBox; a rede da VM pode ficar em NAT |
| Rede entre máquinas | Tailscale em container, com nomes fixos (forca-a, forca-b, forca-gateway) |
| Empacotamento | Dockerfile único e Docker Compose para o nó e para o gateway |
| Organização | Dois nós com papéis dinâmicos: quem atende é o primário, o outro é reserva sincronizado; um nó sozinho também atende |
| Estado | Em memória (RAM) nos dois nós; replicação síncrona feita pela aplicação |
| Concorrência | threading.Lock no nó e versão por sala |
| Cliente | Página web com os dois bonecos visíveis; cliente de terminal mantido para testes |
| Cenário de falha | Uma falha por vez, por parada do processo ou desligamento do computador |

As regras de vitória, os tempos e a interface definidos aqui são decisões do projeto. Os critérios da seção 12 são metas de aceitação; o que já foi verificado está indicado no ROADMAP.

## 2 Escopo e garantias do sistema distribuído

### 2.1 Garantia pretendida

Com os dois nós sincronizados, o sistema suporta a queda do nó que atende e continua no outro. A recuperação causa uma pausa visível de alguns segundos. O jogador não troca de endereço: o gateway passa a encaminhar para o nó que assumiu, e a página retoma a sessão.

**Nenhuma jogada que o sistema tenha confirmado ao jogador enquanto os dois nós estavam sincronizados pode desaparecer.** O primário só responde depois que o reserva confirma ter recebido o novo estado. Uma requisição cuja resposta não chegou ao navegador pode ter sido aplicada; nesse caso a página reenvia o mesmo identificador de requisição e recebe o resultado já registrado, sem executar a jogada duas vezes.

O jogo também funciona com um nó só: ele cria o jogo e atende com uma única cópia, e as jogadas desse período se perdem se ele cair antes de o outro voltar. Quando o outro nó entra, recebe a cópia completa e passa a ser reserva, sem reiniciar a partida.

### 2.2 Limites com apenas dois nós

O modelo pressupõe falha por parada: o nó indisponível realmente deixa de executar. O timeout do heartbeat é um indício de falha, não uma prova de que o outro computador desligou.

O projeto prioriza a disponibilidade: um nó sozinho atende. Se o reserva perder o contato com o primário, ele se promove após 5 segundos. Se o primário perder o contato com o reserva, ele se pausa por 7 segundos e depois segue sozinho. A diferença entre os dois tempos cobre o caso de ter falhado só a rede entre os nós: quando o primário voltaria a atender, o reserva já assumiu, e o gateway encaminha os jogadores a ele.

Ao voltar, um nó procura o outro e vira reserva de quem estiver atendendo. Se dois primários se reencontram, fica o que confirmou mais jogadas; no empate, a maior época e depois o menor nome. O outro descarta a própria cópia e vira reserva.

Não são cobertos: jogadas confirmadas com uma cópia só quando esse nó cai antes de o outro voltar; e uma falha de rede entre os nós em que os dois recebam jogadas, caso em que as do nó que cede são descartadas. Garantias fortes exigiriam um terceiro participante de decisão (árbitro). Esse recurso fica fora do escopo deste trabalho.

### 2.3 Condições da apresentação

- As duas VMs dos nós devem estar em computadores físicos diferentes.
- As VMs, a instância Oracle e os jogadores precisam de acesso à internet: o Tailscale conecta as máquinas e o gateway é publicado em forca.ambrosias.dev. A rede local da faculdade não precisa permitir conexões diretas entre os computadores.
- Os jogadores observados devem usar um equipamento que permaneça ligado (outro computador ou celular). Desligar o computador de um jogador derruba aquele jogador, não o sistema.
- Para um teste do zero, os dois nós são parados e iniciados de novo; as abas abertas voltam à tela de nome.

## 3 Arquitetura física e lógica

### 3.1 Distribuição dos componentes

Cada computador hospeda uma VM Linux. Dentro de cada VM, o Docker executa um container tailscale e o mesmo programa servidor; não há papel fixo. O nó que atende é o primário; o outro guarda uma cópia completa do estado e responde retry aos jogadores. O gateway roda em container na instância Oracle, atrás do Nginx e da Cloudflare.

| Camada | Computador A | Computador B | Oracle |
| --- | --- | --- | --- |
| VM ou host | Linux A (VirtualBox) | Linux B (VirtualBox) | Instância Oracle |
| Containers | tailscale + servidor | tailscale + servidor | tailscale + gateway |
| Nome na rede | forca-a | forca-b | forca-gateway |
| Papel | Dinâmico | Dinâmico | Porta de entrada, sem estado |
| Dados | Estado em RAM | Cópia do estado em RAM | Nenhum |
| Portas | 5000 jogo, 5001 sincronização | 5000 jogo, 5001 sincronização | 8080, só para o Nginx local |

O navegador conhece um único endereço, https://forca.ambrosias.dev. O gateway conhece os dois nós pelo nome e descobre qual está atendendo. Não há banco central.

### 3.2 Responsabilidades

A página coleta o nome, mostra a sala, envia intenções de jogada e desenha os estados recebidos. O nó valida identidade, participação na sala, turno, versão, letra, resultado, ocupação das salas e regras de vitória. A página nunca decide sozinha se acertou ou venceu. O gateway só encaminha; não interpreta nem guarda jogadas.

O canal de sincronização transmite o estado completo após cada alteração, recebe a confirmação e troca heartbeats. VirtualBox fornece as VMs; Docker padroniza a execução dentro delas; o Tailscale dá nomes fixos às máquinas. A recuperação entre computadores é responsabilidade da aplicação; a política de reinício do container só traz o nó de volta, e ele volta como reserva.

## 4 Requisitos funcionais e formação das salas

### 4.1 Identificação e entrada

**RF01 Identificação.** O jogador informa um nome de exibição de 1 a 24 caracteres imprimíveis. A página gera um token aleatório e o salva na aba (sessionStorage) antes da primeira requisição; o `cliente.py` o salva em arquivo. O nó usa o SHA-256 do token como player_id. A identidade é o token, não o nome.

**RF01a Nomes únicos.** Dois jogadores ativos não podem ter o mesmo nome, estejam ou não na mesma sala. A comparação ignora maiúsculas e espaços nas pontas. Um ENTRAR com nome em uso é recusado com NOME_EM_USO. O nome fica reservado enquanto o jogador está ativo, inclusive desconectado, e é liberado quando ele envia SAIR. Para que um nome não fique preso por quem fechou a página e não voltou, o dono deixa de ser ativo quando passa 180 segundos sem consultar o servidor e não está em uma partida em andamento; sua sala de espera é cancelada e, se voltar, precisará entrar de novo. Durante os primeiros 180 segundos de um servidor, inclusive logo após a promoção do reserva, nenhum nome é liberado, dando tempo para todos reconectarem. No mesmo computador, o cliente trava o arquivo de sessão enquanto está aberto, de modo que um segundo cliente com o mesmo nome não reutiliza nem sobrescreve o token do primeiro.

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

Ao terminar, ambos recebem o resultado do próprio ponto de vista, como Você venceu! Bruno chegou a seis erros ou Você perdeu. Ana completou a palavra, além da palavra completa. Os códigos internos do motivo não aparecem na tela. O botão Nova partida envia outro ENTRAR e pode formar outro par. A sala encerrada fica na memória enquanto algum participante ainda a consulta e depois é apagada; ela nunca é reutilizada.

## 5 Regras do jogo e interface

### 5.1 Regras adotadas

- Cada sala usa uma palavra compartilhada pelos dois jogadores, sorteada uma única vez.
- As palavras usam apenas A a Z, sem espaços nem hífens. Letras e chutes com acento valem como a letra sem acento (ç vale C; conexão vale CONEXAO) e minúsculas são convertidas para maiúsculas; outros caracteres são rejeitados.
- Cada jogador possui um boneco próprio e até seis erros: cabeça, tronco, braço esquerdo, braço direito, perna esquerda e perna direita.
- Na sua vez, o jogador tenta uma letra ou chuta a palavra inteira.
- Uma letra correta revela todas as suas ocorrências. Uma letra incorreta acrescenta um erro apenas ao autor.
- Um chute igual à palavra encerra a partida com vitória do autor e motivo PALAVRA_COMPLETA. Um chute diferente informa que a palavra não coincide, acrescenta um erro ao autor e fica registrado na lista de chutes errados da sala.
- Cada tentativa válida, de letra ou de palavra, alterna o turno quando a partida continua.
- Letra ou palavra já tentada na sala, entrada inválida, jogada fora da vez ou com versão desatualizada é rejeitada sem alterar turno ou erros. O chute aceita de 1 a 30 letras, sem espaços, hífens ou números.
- Quem revelar a última letra ou acertar o chute vence. Se um jogador atingir seis erros, inclusive por um chute errado, o adversário vence.

### 5.2 Exibição

A página mostra o ID e o estado da sala, os nomes dos dois jogadores, os dois desenhos da forca lado a lado, os erros de cada um, a palavra mascarada, um teclado A–Z com as letras tentadas marcadas como acerto ou erro, os chutes errados e de quem é a vez. A tela é redesenhada sempre que o estado muda. Há mensagens para aguardando adversário, sua vez, vez do adversário, jogada inválida, reconectando, partida pausada e partida encerrada. O canto da página mostra a conexão e o nó que está atendendo; revisões e promoções ficam no log dos nós.

O teclado físico também envia letras. Enquanto um comando espera resposta, a página não aceita outro, e o comando pendente é reenviado idêntico até haver resposta, inclusive depois de recarregar a página.

### 5.3 Desconexão e desistência

Quando um cliente para de consultar, a sala aparece pausada após 5 segundos e a vaga é preservada. Uma reconexão com a mesma sessão retoma a sala original. Não há limite de tempo para escolher uma letra; o adversário pode encerrar a partida com Sair. Se os dois participantes passarem 180 segundos sem consultar, a partida é cancelada com o motivo ABANDONO.

Um jogador sozinho que envia SAIR cancela a sala. Em uma partida iniciada, SAIR caracteriza desistência e dá a vitória ao adversário. Em ambos os casos o jogador deixa de estar ativo e seu nome é liberado. Um novo jogador nunca substitui um participante ausente.

## 6 Controle de concorrência

**RF07 Exclusão mútua.** O nó usa um threading.Lock para tornar indivisível a sequência validar, aplicar, replicar e adotar o novo estado. Cada conexão é atendida por uma thread; um BoundedSemaphore limita a 64 as conexões simultâneas, e as excedentes são fechadas. Uma requisição espera no máximo 2 segundos pela trava e, depois disso, recebe retry; como o gateway lê por 10 segundos e o navegador espera 20, nenhuma requisição é aplicada depois que quem a enviou desistiu dela.

A trava é global, não por sala, e é mantida durante a replicação. Isso simplifica o raciocínio e é suficiente para a escala da demonstração, pois cada comando é curto e nenhum espera o jogador pensar. A versão da sala (room_version) enviada pelo cliente rejeita jogadas baseadas em um estado antigo.

**RF08 Autoridade do servidor.** O servidor recusa a jogada fora da vez mesmo que um cliente modificado envie a mensagem. O prompt do cliente é apenas uma conveniência.

A trava protege as threads de um processo, não os dois nós. A existência de um único nó aceitando alterações decorre do protocolo de papéis descrito na seção 8.

## 7 Estado e replicação

### 7.1 Dados replicados

| Registro | Conteúdo |
| --- | --- |
| world | deployment_id, jogadores, salas e contador de salas |
| epoch | Número de promoções desde a criação do jogo |
| Jogador | player_id, nome, sala associada e se está ativo |
| Sala | Participantes, palavra, letras, chutes errados, erros, turno, estado, versão, vencedor e motivo |
| receipts | Para cada jogador, o request_id, a impressão digital e o resultado do último comando |
| revision | Contador global de alterações |

Ao fim de cada alteração, o nó apaga jogadores inativos que nenhuma sala mostra e salas encerradas que ninguém consulta, e libera quem sumiu há 180 segundos fora de partida em andamento. O estado replicado cresce com quem está jogando, não com o histórico. Se ainda assim passar de 2 MB, o comando é recusado com ESTADO_CHEIO e o nó continua atendendo.

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

Como o cliente tem um único comando pendente por vez, o servidor guarda apenas o recibo do último comando de cada jogador, e nenhum de quem nunca entrou. Isso mantém o estado replicado pequeno. Os recibos são replicados com o estado e apagados junto com o jogador. Trata-se de efeito único por identificador, não de entrega exatamente uma vez pela rede.

## 8 Falha e recuperação

### 8.1 Papéis do nó

| Papel | Comportamento |
| --- | --- |
| ENTRANDO | Sem estado. Procura o outro nó a cada segundo, por até 10 segundos; responde retry aos jogadores |
| RESERVA | Recebeu a cópia completa; guarda cada novo estado e responde heartbeats; responde retry aos jogadores |
| PRIMARIO com reserva | Atende jogadores e replica cada alteração antes de responder |
| PRIMARIO sozinho | Atende com uma cópia só: criou o jogo sem achar o outro nó, assumiu após a queda do primário ou perdeu o reserva |
| PRIMARIO em espera | Acabou de perder o reserva. Responde retry por até 7 segundos e procura o outro nó |

Os dois nós escutam as portas 5000 e 5001 o tempo todo. O PING informa nome, papel, se atende, a época e a revisão.

### 8.2 Inicialização

Um nó que inicia fica ENTRANDO e tenta se juntar ao outro (variável PEER), apresentando a chave de replicação. Se o outro já atende, recebe a cópia completa e vira reserva. Se os dois estão ENTRANDO e se veem, o de nome menor cria o jogo, com um deployment_id novo e época 1. Se ninguém responde em 10 segundos, o nó cria o jogo e atende sozinho. Quando um reserva se junta, o primário registra no log Reserva sincronizado e passa a replicar cada jogada. Se a cópia inicial ou o ACK falharem, o primário segue como estava e espera outra tentativa. A chave é comparada em bytes UTF-8, de modo que chaves com acento funcionam e uma chave inválida não derruba o canal.

O compose.yaml usa restart unless-stopped: como um nó que volta procura o outro antes de qualquer coisa, reiniciar o container é seguro.

### 8.3 Detecção e promoção

**RD03 Heartbeat.** O primário envia um heartbeat ao reserva a cada 0,5 segundo e espera a resposta por até 3 segundos. O reserva espera mensagens do primário por até 5 segundos.

**RD04 Assunção.** O reserva só pode se promover depois de receber a segunda mensagem do primário, um heartbeat ou um novo estado, que prova que o primário recebeu o ACK da cópia inicial. A partir daí, qualquer erro ou timeout no canal faz o reserva se promover: soma 1 à época e passa a atender. Se a conexão cair antes da segunda mensagem, ele volta a ENTRANDO. Ao encerrar o processo do primário, a conexão é fechada e a promoção é imediata; ao desligar o computador, ocorre após o timeout de 5 segundos.

**RD04a Perda do reserva.** O primário que perde o reserva se pausa por 7 segundos, mais que o tempo de promoção do reserva, e procura o outro nó. Se o outro se promoveu, o primário cede e vira reserva dele. Se o outro reiniciou, ele se junta ao primário. Se nada disso acontece, o primário volta a atender sozinho.

**RD04b Dois primários.** Todo primário sem reserva continua procurando o outro nó. Se dois primários se encontram, prevalece o de maior revisão; no empate, o de maior época; no empate, o de menor nome. O outro descarta a própria cópia e vira reserva. O gateway usa a mesma ordem para escolher a quem encaminhar.

### 8.4 Reconexão do jogador

**RD05 Retomada automática.** O gateway consulta os dois nós a cada segundo e encaminha cada comando ao que atende com a maior época; em retry ou falha, tenta o outro. Sem nenhum nó atendendo, responde 503 e a página reenvia o mesmo comando, mantendo token e request_id. A próxima consulta devolve o estado completo e autoritativo da sala.

O deployment_id recebido na primeira resposta é salvo na sessão. Se os dois nós reiniciarem, a página recebe uma resposta fatal e volta à tela de nome, em vez de criar uma identidade nova sem perceber.

### 8.5 Retorno de um nó

**RD06 Retorno como reserva.** O nó que volta fica ENTRANDO, se junta a quem está atendendo e recebe a cópia completa, incluindo as jogadas feitas enquanto esteve fora; a redundância volta sem reiniciar as partidas.

## 9 Protocolo de comunicação

### 9.1 Transporte e enquadramento

**RT01 Sockets TCP.** O gateway e o cliente de terminal usam a porta 5000 dos nós; os nós usam a porta 5001 entre si para sincronização e heartbeat. Ambas são configuráveis. Cada mensagem é um objeto JSON UTF-8 terminado por LF, com limite de 2 MB. A leitura acumula bytes até o delimitador, tratando mensagens parciais ou agrupadas pelo TCP.

Cada comando de jogador usa uma conexão curta: conectar, enviar, receber a resposta e fechar. A página consulta o estado a cada segundo por HTTP; o gateway repassa o corpo do POST /api sem alteração. JSON inválido, excesso de tamanho ou campos inválidos produzem erro controlado sem derrubar o nó nem o gateway.

### 9.2 Mensagens

| Direção | Tipos | Finalidade |
| --- | --- | --- |
| Página para gateway | POST /api, GET /api/status | Enviar comandos; ver o papel de cada nó |
| Gateway para nó | PING | Descobrir quem atende e a época |
| Gateway para nó | ESTADO, ENTRAR, JOGAR, CHUTAR, SAIR | Presença, ocupar sala, tentar letra, chutar a palavra e desistir |
| Nó para gateway | ok, retry, fatal | Resultado, nó indisponível ou execução diferente |
| Nó que procura para o outro | key, node, role, serving | Autenticar e se apresentar |
| Primário para reserva | state, heartbeat | Replicar e monitorar |
| Reserva para primário | ack, heartbeat | Confirmar e responder |

Exemplo de comando JOGAR:

```json
{"type":"JOGAR","request_id":"uuid-da-operacao",
 "token":"segredo-do-jogador","deployment":"uuid-da-execucao",
 "letter":"A","version":8}
```

O exemplo está formatado para leitura; na rede ocupa uma linha. O autor da jogada é determinado pelo token, e não por um player_id enviado pela página. Os campos completos, o estado público e os códigos de erro estão em docs/protocolo-etapa-1.md.

### 9.3 Proteção mínima

Tokens são imprevisíveis, guardados apenas na aba do navegador e não aparecem nos logs; o gateway não registra requisições. O canal de sincronização exige uma chave compartilhada comparada em tempo constante. As portas 5000 e 5001 só existem na rede do Tailscale, cifrada; o público alcança apenas o gateway, por HTTPS. O gateway serve uma lista fixa de arquivos, limita o corpo a 8 KB e aceita só os cinco comandos de jogador. O arquivo .env real não deve ser versionado.

## 10 Docker e ambiente das VMs

### 10.1 Artefatos

**RI01 Dockerização.** O repositório contém Dockerfile, compose.yaml (nó), deploy/oracle/compose.yaml (gateway), .dockerignore e os .env.example. Como o projeto usa apenas a biblioteca padrão, não há arquivo de dependências; a versão do Python é fixada na imagem python:3.12.13-slim, e o mesmo pacote serve ao nó e ao gateway.

Cada VM executa um projeto Compose com dois serviços: tailscale, que dá à VM o nome fixo do nó, e servidor, que usa a rede do container tailscale. As portas não são publicadas na rede local. A comunicação entre as VMs usa os nomes do Tailscale, não IPs.

### 10.2 Configuração

| Variável | Finalidade |
| --- | --- |
| NODE_NAME | forca-a ou forca-b; nome do nó e desempate na criação do jogo |
| PEER | host:porta de sincronização do outro nó, por exemplo forca-b:5001 |
| REPLICATION_KEY | Chave compartilhada, igual nos dois nós |
| TS_AUTHKEY | Chave de autenticação do Tailscale, com a tag tag:forca |
| SERVIDORES | No gateway: forca-a:5000,forca-b:5000 |
| GAME_PORT / SYNC_PORT | 5000 / 5001 (fora do Compose) |

### 10.3 VirtualBox e rede

Uma VM Linux por computador, com 2 vCPUs, 2 GB de RAM e 15 GB de disco, é uma configuração inicial suficiente. Usar a mesma distribuição e versões nas duas VMs facilita a reprodução.

As variáveis opcionais BOOT_WAIT e SOLO_WAIT mudam os 10 e os 7 segundos das seções 8.2 e 8.3.

A rede da VM pode ficar em NAT: o Tailscale atravessa NAT e firewalls, e usa servidores intermediários quando a conexão direta é bloqueada. Não é preciso IP fixo, modo bridge nem liberar portas na rede da faculdade.

### 10.4 Operação

Em cada VM, bash scripts/preparar-vm.sh instala o Docker, cria o .env e sobe os containers. Na Oracle, docker compose up -d --build em deploy/oracle. Para acompanhar os logs, docker compose logs -f servidor. Para encerrar, docker compose down. O passo a passo está em docs/implantacao.md.

## 11 Observabilidade e critérios de qualidade

**RN01 Logs.** O nó registra horário, portas, criação do jogo, sincronização do reserva, cada revisão confirmada com o tipo de comando, perda do reserva, cessão do papel e promoção com a revisão e a época assumidas. O gateway registra quando cada nó passa a atender ou deixa de atender. Tokens e palavras secretas não são registrados.

**RN02 Metas.** Na rede local, demonstrar pelo menos cinco clientes em três salas, confirmação de jogada perceptivelmente imediata e recuperação em até 15 segundos após desligar o primário. São metas a medir na apresentação; a integridade do estado tem prioridade sobre a velocidade.

**RN03 Isolamento.** Uma mensagem inválida ou um cliente lento não derruba o nó nem o gateway: cada conexão com o nó tem timeout de 4 segundos, as mensagens têm tamanho limitado e o número de conexões simultâneas é limitado a 64 no nó e a 128 no gateway.

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
| T10 | Nó sozinho | Procura o outro por 10 s, cria o jogo e atende; o outro entra depois como reserva |
| T11 | Desligar o computador do primário | Partidas e sala em espera retomadas no reserva |
| T12 | Queda do primário após o ACK e antes da resposta | Reenvio resolve a ação sem duplicar erro ou turno |
| T13 | Encerrar o reserva | Primário pausa por até 7 s e segue sozinho; o reserva que volta recebe as jogadas feitas sem ele |
| T14 | Cliente fecha e reabre | Volta à mesma sala; adversário vê a partida pausada |
| T15 | Sessão de outra execução | Resposta fatal; a página volta à tela de nome |
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
| T26 | Religar o antigo primário | Entra como reserva de quem atende; a partida continua |
| T27 | Derrubar o nó promovido depois do T26 | O antigo primário assume com todas as jogadas, inclusive as feitas enquanto esteve fora |
| T28 | Dois nós iniciando juntos | Só o de nome menor cria o jogo; o outro vira reserva |
| T29 | Dois primários se reencontram | Fica o de mais jogadas confirmadas (depois época, depois nome); o outro vira reserva |
| T30 | Partida pelo gateway com queda do nó que atende | Mesmo endereço, estado idêntico, reenvio sem efeito duplo |
| T31 | Muitas partidas encerradas | Estado replicado não cresce; comando que passaria de 2 MB é recusado sem pausar |
| T32 | Corpo HTTP inválido ou caminho fora da lista | 400, 404 ou 413, sem derrubar o gateway |

A pasta tests contém testes automatizados com unittest para T01 a T10, T12 (reenvio após a troca de servidor), T13, T16 a T25 e T26 a T32 (em T20 e T21, a parte que depende do teclado e da reconexão do cliente foi verificada manualmente), com os nós e o gateway em processos reais e TCP local. A página foi verificada no navegador com dois jogadores e a sequência completa: queda de forca-a, retorno como reserva e queda de forca-b. Eles são executados com python -m unittest discover -s tests.

### 12.2 Execução dos testes de falha

Encerrar o processo testa a detecção por conexão fechada; desligar a VM ou o computador testa a detecção por timeout. T11 precisa incluir o desligamento físico solicitado pelo professor.

Para medir a preservação, registrar antes e depois a sala, a versão, as letras, os erros e o turno. Com papéis dinâmicos não é preciso reiniciar entre os testes: o nó religado volta como reserva.

## 13 Roteiro da apresentação

1. Mostrar os dois computadores, as VMs e os containers; abrir https://forca.ambrosias.dev/api/status e identificar quem atende e quem é reserva.
2. Mostrar no log do primário a mensagem Reserva sincronizado.
3. Abrir cinco abas ou celulares: os dois primeiros iniciam a sala 1, os dois seguintes a sala 2 e o quinto aguarda na sala 3.
4. Fazer acertos e erros nas duas partidas. Mostrar os dois bonecos nas duas telas e a rejeição de uma jogada fora da vez.
5. Anotar versões e turnos e mostrar no log as revisões confirmadas.
6. Desligar fisicamente o computador do nó que atende, mantendo os jogadores ligados. Cronometrar a interrupção.
7. Mostrar o aviso de reconexão, a promoção no log (época 2) e a retomada das salas 1 e 2 sem reiniciar as partidas; o canto da página passa a mostrar o outro nó.
8. Abrir um sexto jogador e mostrar que ele entra na sala 3 com quem já aguardava.
9. Religar o computador: o nó volta como reserva. Desligar agora o outro computador e mostrar que as partidas continuam, com as jogadas feitas enquanto o primeiro estava fora.

Os jogadores devem usar equipamentos que fiquem ligados. Desligar o computador de um jogador derruba aquele jogador; isso não é resolvido pela redundância dos nós.

## 14 Organização da implementação e entregáveis

### 14.1 Componentes

| Componente | Responsabilidade |
| --- | --- |
| forca/game.py | Regras puras, validação de letras e resultado |
| forca/lobby.py | Salas, vagas, sessões, entrada, saída, recibos e coleta do estado |
| forca/wire.py | Envio e leitura de JSON por linha |
| servidor.py | Nó: papéis dinâmicos, sockets, threads, trava, replicação, heartbeat e promoção |
| gateway.py | HTTP para o navegador e roteamento para o nó que atende |
| web/ | Página do jogo |
| cliente.py, forca/ui.py | Cliente de terminal para testes |
| forca/words.txt | Lista de palavras |
| compose.yaml, deploy/oracle/ | Implantação do nó e do gateway |
| tests | Regras, salas, nomes, cliente, nós e gateway com queda de processo |

### 14.2 Entrega final

A entrega contém código Python, página web, testes automatizados, Dockerfile, Compose do nó e do gateway, configuração de exemplo, lista de palavras, README, guia de implantação, descrição do protocolo e esta especificação. Falta o relatório do teste de desligamento físico, acompanhado no ROADMAP.

O projeto será considerado concluído quando os testes funcionais e de recuperação passarem no modelo admitido, a execução for reproduzível com Docker e a demonstração comprovar continuidade das partidas após o desligamento físico.

## 15 Referências técnicas

As referências sustentam os recursos de infraestrutura e biblioteca. As regras do jogo, mensagens, tempos e o protocolo primário e reserva são decisões deste projeto. Consulta em 26 de setembro de 2026.

- Python socket: interface de baixo nível para sockets TCP. https://docs.python.org/3/library/socket.html
- Python threading: threads, Lock e BoundedSemaphore. https://docs.python.org/3/library/threading.html
- Python hmac: compare_digest para comparar a chave de replicação. https://docs.python.org/3/library/hmac.html
- Python secrets: geração de tokens de sessão. https://docs.python.org/3/library/secrets.html
- Docker Compose services: serviços, portas e política de reinício. https://docs.docker.com/reference/compose-file/services/
- Oracle VirtualBox Virtual Networking: opções de rede. https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/networkingdetails.html
- Python http.server: servidor HTTP do gateway. https://docs.python.org/3/library/http.server.html
- Tailscale em Docker: parâmetros do container. https://tailscale.com/kb/1282/docker
- etcd FAQ: maioria e tolerância a falhas; justifica por que dois servidores não formam consenso. https://etcd.io/docs/v3.6/faq/
