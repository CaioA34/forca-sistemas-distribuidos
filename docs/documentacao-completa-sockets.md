# Jogo da Forca Distribuído

Documentação de construção e guia de estudo

Python • sockets TCP • salas • turnos • replicação • VMs • Docker

Versão do projeto: 0.2.0 | Código consultado em 27/09/2026

Este material explica a implementação existente, relaciona cada requisito ao código e mostra como demonstrar o sistema. Foi escrito para estudantes que estão aprendendo redes e sistemas distribuídos. Os exemplos acompanham o projeto forca-sistemas-distribuidos, revisão Git 1ecf320.

O foco principal é socket: como uma intenção digitada em um terminal vira bytes, chega ao servidor, modifica uma partida e aparece nos terminais dos dois jogadores. A segunda parte central é a cópia desse estado para outro computador, antes de confirmar uma jogada.

O PDF contém sumário com páginas e navegação.

# 1. O que foi construído e como estudar

O projeto é um jogo de forca para vários jogadores, organizados automaticamente em salas com no máximo duas pessoas. Cada sala tem uma palavra compartilhada, uma vez de jogar e dois contadores de erros. Cada participante possui seu próprio boneco, e os dois bonecos aparecem nos dois clientes.

Um cliente é o programa que o jogador abre no terminal. O servidor é o programa que recebe os pedidos e decide o que pode acontecer. Os terminais de Ana e Bruno não conversam diretamente entre si: ambos conversam com o servidor. A palavra secreta e as regras ficam no servidor.

Existem duas instâncias do programa servidor: o primário atende os jogadores e o reserva recebe cópias do estado. Instância significa uma execução do mesmo programa. Quando o primário cai, o reserva sincronizado assume o atendimento, e os clientes tentam seu endereço. O jogo continua depois de uma interrupção de alguns segundos, preservando o estado que foi replicado.

O projeto atual utiliza Python e sua biblioteca padrão para executar o jogo. Não utiliza Supabase, banco central, serviço de nuvem nem processo separado para cada sala. A configuração de entrega usa Docker em duas VMs, instaladas em dois computadores físicos distintos.

## 1.1 O que este documento comprova

A explicação foi construída pela leitura do código atual. A ordem dos capítulos é uma ordem didática de construção, e não uma alegação sobre a ordem histórica em que cada integrante escreveu os arquivos. Os trechos destacados são extraídos automaticamente dos arquivos reais. No apêndice há uma cópia integral do código e das configurações selecionadas, com números de linha.

Em 27/09/2026, os 50 testes automatizados do projeto foram executados neste ambiente Windows, com resultado OK em 8,382 segundos. Isso comprova os cenários cobertos pelos testes locais; não comprova desligamento físico de computador, funcionamento de uma rede específica ou execução dos containers nas duas VMs. Essa etapa continua sendo uma validação prática do grupo.

## 1.2 Caminho sugerido para aprender

1. Entenda os componentes e os seis requisitos nos capítulos 2 e 3.

2. Estude sockets, mensagens e o caminho da jogada nos capítulos 4 a 7.

3. Veja salas, turnos e bonecos nos capítulos 8 a 10.

4. Estude replicação, falhas e sessões nos capítulos 11 a 13.

5. Execute os roteiros dos capítulos 14 e 15 e consulte o código integral no apêndice.

Quando aparecer um nome como Server.request, leia como “o método request da classe Server”. Uma classe reúne dados e funções relacionados; um método é uma função definida dentro dela. Um dicionário Python associa chaves a valores, por exemplo {"errors": 2}.

# 2. Os seis requisitos e onde estão no código

| Requisito do trabalho | Implementação atual | Como demonstrar |
| --- | --- | --- |
| Utilizar socket | TCP em cliente.py e servidor.py; mensagens em forca/wire.py | Dois clientes em uma máquina acessam o IP de outra |
| Servidor resiliente | Cópia síncrona para o reserva; Server.follow promove o reserva | Desligar o computador do primário depois da sincronização |
| Múltiplas requisições e espera | Threads atendem conexões; lobby.enter distribui jogadores | Abrir cinco clientes e observar três salas |
| Máximo de dois jogadores | Busca apenas salas com uma vaga; Room.start exige dois | Ana/Bruno ficam juntos; Caio/Dani ficam em outra sala |
| Controle como semáforo | Lock serializa processamento; turn autoriza o jogador | Enviar letra fora da vez e verificar a rejeição |
| Estados e dois bonecos | Resposta inclui erros de ambos; ui.render desenha ambos | Ana erra: seu boneco muda nos dois terminais |

“Atendido no código” e “validado no ambiente de apresentação” são coisas diferentes. As regras têm testes automatizados. A recuperação de falha é testada com processos locais. A demonstração exigida pelo professor precisa usar computadores físicos diferentes, para que desligar um não desligue as duas VMs.

## 2.1 Precisão sobre o requisito de resiliência

Esta versão tolera a queda do primário, desde que o reserva já esteja sincronizado e a rede dos clientes continue funcionando. Se o reserva cair primeiro, o primário pausa para não confirmar novas alterações sem uma segunda cópia. Após assumir, o reserva trabalha sozinho. Portanto, a tolerância a falhas é limitada a esse cenário e não cobre indiscriminadamente a queda de qualquer máquina em qualquer momento.

Se o professor exigir que qualquer um dos dois servidores possa cair sem interromper o jogo, a versão atual ainda não atende integralmente a essa interpretação. É essencial apresentar a garantia real, em vez de chamar qualquer recuperação de “100% disponível”. O capítulo 12 detalha os casos.

## 2.2 Três limites que não devem ser confundidos

Dois é a quantidade máxima de jogadores por sala. Sessenta e quatro é o limite de conexões atendidas simultaneamente pelo servidor. Um é o número de pedidos que podem estar dentro da região protegida por Lock ao mesmo tempo. Esses números tratam de problemas diferentes.

O projeto pode manter várias salas. Uma sala não ganha uma porta exclusiva, uma VM própria ou um processo próprio. Todas usam o mesmo servidor e a mesma porta de jogadores. O servidor descobre a sala pelo jogador identificado no pedido.

# 3. Arquitetura e divisão dos arquivos

```text
Clientes <-> Primário <-> Reserva
              TCP          TCP
```

A figura mostra o funcionamento normal. O reserva inicia a conexão de replicação com o primário e a mantém aberta. Os clientes conhecem os dois IPs, mas o reserva só abre o atendimento de jogadores depois da promoção. As setas representam comunicação TCP; não representam memória compartilhada.

| Arquivo | Responsabilidade |
| --- | --- |
| servidor.py | Aceitar sockets, coordenar threads, proteger o estado, replicar e assumir o atendimento |
| cliente.py | Ler teclado, enviar pedidos, mostrar respostas, salvar sessão e reconectar |
| forca/wire.py | Converter dicionários em mensagens JSON e ler uma mensagem por linha |
| forca/game.py | Representar jogadores e salas; validar letras, turnos, erros e vitória |
| forca/lobby.py | Distribuir jogadores em salas, reservar nomes e reconhecer reenvios |
| forca/ui.py | Transformar o estado público em texto e desenhar as forcas |
| forca/words.txt | Lista de palavras sorteadas pelo servidor |
| Dockerfile e compose.yaml | Preparar e executar o servidor em container |
| tests/ | Testar regras, cliente, protocolo e troca de servidor |

## 3.1 Construção em camadas

Primeiro podemos entender o jogo sem rede: Room, em game.py, sabe iniciar uma partida e processar uma tentativa. Depois vem o lobby, que escolhe uma sala e associa os jogadores. Nenhum desses dois módulos abre sockets. Isso permite testar regras com chamadas de funções, sem depender de uma VM.

Em seguida, wire.py define como os dados serão transportados. servidor.py liga a comunicação às regras: recebe uma mensagem, aplica a operação e devolve uma resposta. cliente.py cuida da interação com a pessoa. Por fim, a replicação acrescenta uma segunda cópia do estado e o Docker organiza a execução.

Separar responsabilidades ajuda a aprender e a corrigir problemas. Um desenho errado pode estar em ui.py; uma letra aceita fora da vez pode estar em game.py; uma mensagem que não chega pode envolver cliente.py, servidor.py, wire.py ou a rede.

## 3.2 O que torna o sistema distribuído

Cada processo tem sua própria memória. O primário não acessa diretamente a RAM do reserva. Para que o reserva conheça uma partida, o primário precisa transformar seus dados em uma mensagem e enviá-la pela rede. As máquinas podem atrasar, perder comunicação ou desligar em momentos diferentes.

O mesmo programa pode executar em mais de um computador, mas isso sozinho não garante continuidade. A continuidade depende de cópias do estado, confirmação de recebimento, detecção de falha e reconexão dos clientes. Esses mecanismos são parte explícita do código deste projeto.

# 4. Socket explicado desde o início

Um socket é um recurso do sistema operacional que um programa usa para se comunicar. Pense nele como uma ponta de comunicação. Em uma conversa TCP há uma ponta no cliente e outra no servidor. Python oferece a biblioteca socket para pedir ao sistema operacional que crie, conecte, escute e feche essas pontas.

Um socket não é uma sala de jogo, um terminal nem o arquivo JSON da sessão. O terminal recebe o texto digitado; cliente.py decide o comando; o socket transporta os bytes desse comando. O servidor interpreta os bytes e encontra o jogador e a sala correspondentes.

## 4.1 IP, porta e conexão

O IP identifica um endereço de rede. A porta identifica o ponto de atendimento dentro daquele endereço. No exemplo 192.168.1.10:5000, o cliente procura a porta TCP 5000 da máquina com IP 192.168.1.10.

| Endereço ou porta | Significado neste projeto |
| --- | --- |
| 127.0.0.1 | A própria máquina ou ambiente de rede em que o processo está rodando |
| 0.0.0.0 no servidor | Escutar nas interfaces IPv4 locais; não é o endereço a informar ao jogador |
| IP da VM | Endereço usado por outra máquina para chegar ao servidor na VM |
| 5000 | Atendimento de jogadores, por padrão |
| 5001 | Canal de replicação do primário, por padrão |
| 5002 | Porta usada para o reserva no teste com ambos no mesmo computador |

O cliente também tem uma porta local, normalmente escolhida automaticamente pelo sistema operacional. Não é necessário reservar uma porta manual para Ana e outra para Bruno. Várias conexões podem chegar à porta 5000: elas são diferenciadas pelos endereços e portas das duas pontas.

Dentro de uma VM, 127.0.0.1 aponta para a VM. Dentro de um container, aponta para o ambiente de rede do container. Por isso, o reserva em outra VM deve receber o IP real do primário em --primario ou PRIMARY_HOST.

## 4.2 Por que TCP

TCP oferece um fluxo de bytes ordenado durante uma conexão. O sistema operacional cuida de detalhes como retransmitir segmentos perdidos. O projeto usa esse transporte para mensagens pequenas de comando e estado.

Isso não significa que TCP salva uma partida ou garante que uma jogada foi aplicada. Se o computador desligar, a conexão pode falhar. Mesmo um envio sem erro não prova que o programa remoto terminou de processar a mensagem. O protocolo do jogo precisa de respostas e, na replicação, de um ACK próprio da aplicação.

O ACK enviado em JSON pelo reserva é uma confirmação do programa: “guardei o estado desta revisão”. Ele é diferente das confirmações internas do protocolo TCP. Essa diferença explica por que o projeto espera uma mensagem explícita antes de confirmar a jogada.

## 4.3 TCP transporta bytes, não dicionários

Um dicionário Python não atravessa a rede como um objeto da memória. O projeto usa esta sequência:

```text
Dicionário Python -> texto JSON -> bytes UTF-8 -> socket TCP
socket TCP -> bytes recebidos -> leitura do JSON -> dicionário Python
```

JSON é um formato de texto para representar objetos, listas, números e outros valores. UTF-8 é uma forma de representar caracteres como bytes, incluindo letras acentuadas. Serializar é converter dados para uma representação que possa ser enviada; desserializar é reconstruir os dados a partir dela.

As referências oficiais de socket ajudam a aprofundar esses conceitos [R1, R2]. Os próximos capítulos aplicam cada um diretamente às funções do projeto.

# 5. O ciclo de vida dos sockets no código

## 5.1 O servidor cria um ponto de escuta

Trecho real: servidor.py, Server.listen, linha 98.
```python
    def listen(self, port):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, port))
        listener.listen(64)
        return listener
```

socket.socket() cria, com os padrões usados aqui, um socket IPv4 TCP. A forma explícita seria socket.socket(socket.AF_INET, socket.SOCK_STREAM). IPv4 é a família dos endereços como 192.168.1.10; SOCK_STREAM indica o transporte por fluxo usado com TCP.

setsockopt configura uma opção do socket. SO_REUSEADDR ajuda no reaproveitamento do endereço em situações de reinício, conforme as regras do sistema operacional. Não significa que se pode executar dois primários arbitrariamente na mesma porta.

bind associa o socket ao endereço local e à porta. listen o coloca em modo de escuta. O 64 em listen(64) é uma indicação de tamanho da fila de conexões aguardando aceitação pelo programa, sujeita ao sistema operacional. Essa fila não é a sala de espera do jogo.

## 5.2 accept cria a conexão de atendimento

Trecho real: servidor.py, Server.serve, linha 105.
```python
    def serve(self):
        with self.listen(self.port) as listener:
            LOG.info("Atendendo jogadores em %s:%s", self.host, self.port)
            while True:
                connection, _ = listener.accept()
                if self.slots.acquire(blocking=False):
                    threading.Thread(target=self.client, args=(connection,), daemon=True).start()
                else:
                    connection.close()
```

accept espera uma conexão e devolve um novo socket conectado. listener continua disponível para novas conexões; connection serve à conversa que acabou de chegar. O segundo valor devolvido é o endereço remoto, ignorado neste trecho pelo nome _.

Para cada conexão admitida, uma thread executa self.client. Uma thread é uma linha de execução dentro do mesmo processo. Enquanto uma espera bytes de um jogador, o laço de atendimento pode aceitar outra conexão. As threads compartilham o estado do servidor, por isso precisam da proteção explicada no capítulo 9.

O BoundedSemaphore limita a 64 os atendimentos simultâneos. acquire(blocking=False) tenta ocupar uma vaga sem esperar. Se não houver vaga, a conexão é fechada. No finally de Server.client, release devolve a vaga, inclusive em caso de erro. Não são 64 jogadores para sempre: são 64 conexões em atendimento naquele instante.

## 5.3 O cliente conecta, envia, recebe e fecha

Trecho real: cliente.py, exchange, linha 23.
```python
def exchange(address, command):
    host, port = address.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=2) as connection:
        connection.settimeout(5)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)
```

address é um texto como 192.168.1.10:5000. rsplit separa o IP da porta, e int converte a porta para número. create_connection abre a conexão, com limite de dois segundos para a tentativa de conexão. settimeout(5) define o limite usado nas operações seguintes do socket.

makefile("rwb") cria uma interface parecida com um arquivo sobre o socket: r permite ler, w permite escrever, b significa bytes. Não cria um arquivo no disco. A variável stream representa esse acesso à conexão, usado por send e receive de wire.py.

Os blocos with fecham os recursos ao terminar, também quando há exceção. Cada consulta ou comando do jogador usa uma conexão nova. O cliente não mantém uma única conexão por toda a partida.

## 5.4 O servidor trata a mensagem

Server.client configura quatro segundos de timeout, cria seu stream, lê um objeto com receive, chama Server.request e envia a resposta com send. Erros de estrutura recebem uma resposta controlada. Erros inesperados são registrados no log e geram uma mensagem genérica ao cliente. Se a conexão já estiver rompida, enviar a resposta também pode falhar.

Timeout é um limite de espera de uma operação; não é um cronômetro que garante o tempo total de recuperação. Somam-se tentativas em outros endereços, processamento, pausas e condições da rede. O cliente trata falhas de conexão tentando o próximo servidor.

# 6. Como as mensagens são separadas e interpretadas

## 6.1 O problema das mensagens partidas

TCP não preserva as fronteiras das mensagens do programa. Mesmo que o emissor envie um JSON de uma vez, o receptor pode obter seus bytes em partes. Duas mensagens seguidas também podem estar disponíveis juntas. Por isso, uma leitura simples de um bloco de bytes não equivale necessariamente a uma mensagem completa.

```text
Mensagem enviada: {"type":"PING"}\n
Possível chegada em partes: {"ty   +   pe":"PI   +   NG"}\n
Outra possibilidade: duas linhas chegam juntas no buffer.
```

O projeto escolheu uma regra: cada objeto JSON termina com uma quebra de linha, representada por \n. Essa regra de separação é chamada enquadramento. Os textos são serializados sem indentação; quebras de linha dentro de uma string JSON são escapadas pelo serializador e não viram delimitadores extras da mensagem.

## 6.2 O envio, linha por linha

Trecho real: forca/wire.py, send, linha 7.
```python
def send(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("Estado grande demais para o limite desta demonstração.")
    stream.write(data)
    stream.flush()
```

json.dumps transforma o dicionário em texto JSON. ensure_ascii=False permite representar os caracteres diretamente no texto. encode("utf-8") transforma o texto em bytes. O b"\n" acrescenta o delimitador em bytes ao final.

Antes de escrever, o código limita o tamanho a 2.000.000 bytes, incluindo o delimitador. stream.write entrega os bytes ao stream. flush descarrega o buffer de escrita, isto é, manda adiante o que poderia estar esperando na memória local do stream. Sem essa etapa, o outro lado poderia continuar esperando uma mensagem que ainda não saiu do buffer.

O nome send aqui é uma função criada no projeto; não é uma chamada direta ao método socket.send. A comunicação continua sendo por socket: write e flush operam sobre o stream criado a partir dele.

## 6.3 A leitura, linha por linha

Trecho real: forca/wire.py, receive, linha 15.
```python
def receive(stream):
    line = stream.readline(MAX_BYTES + 1)
    if not line:
        raise ConnectionError("Conexão encerrada.")
    if len(line) > MAX_BYTES or not line.endswith(b"\n"):
        raise ValueError("Mensagem incompleta ou grande demais.")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("A mensagem deve ser um objeto JSON.")
    return message
```

readline acumula dados até encontrar a quebra de linha, o limite, o fim do fluxo ou uma falha. O limite é MAX_BYTES + 1 para detectar se a mensagem ultrapassou o permitido. O código rejeita uma linha longa demais ou que terminou sem o delimitador.

Uma leitura vazia indica que a conexão chegou ao fim sem outra mensagem. Isso gera ConnectionError. json.loads interpreta o JSON recebido; ele aceita bytes nesse uso e reconstrói os valores. O código exige um dicionário, porque o protocolo espera um objeto com campos, e não uma lista ou um número solto.

Depois de um timeout ou erro de comunicação, o programa abandona o stream e a conexão por meio dos blocos with. Não tenta continuar lendo como se o conteúdo parcial fosse uma nova mensagem válida.

## 6.4 Por que não usar somente recv(1024)

Seria possível programar o enquadramento diretamente com recv, acumulando pedaços e procurando o delimitador. Porém, chamar recv(1024) uma única vez e imediatamente interpretar o resultado como JSON falharia quando a mensagem chegasse incompleta. O projeto usa readline para simplificar esse trabalho. O tamanho 1024, sozinho, não define uma mensagem.

Essa regra é usada nos dois canais: jogador-servidor e primário-reserva. O transporte é TCP em ambos; o formato é JSON em ambos; os tipos de mensagem e a duração da conexão são diferentes.

# 7. Uma jogada completa, do teclado aos dois terminais

Considere uma partida de Ana e Bruno cuja palavra é SOCKET. A palavra é conhecida pelo servidor; os clientes veem inicialmente ______. Ana joga primeiro. Ao digitar Z e pressionar Enter, ela produz uma tentativa incorreta.

```text
Cliente -> Primário: JOGAR
Primário -> Reserva: estado
Reserva -> Primário: ACK
Primário -> Cliente: resultado
```

1. read_keyboard lê o texto e o coloca em uma Queue, uma fila segura para troca de dados entre threads do cliente.

2. O laço run retira a entrada. parse a transforma em JOGAR e inclui a versão da sala conhecida naquele momento.

3. O cliente acrescenta token, deployment e request_id. Salva o comando em pending antes de enviá-lo.

4. exchange abre um socket até o servidor e envia o JSON terminado em \n.

5. Server.client lê o comando. Server.request entra na trava, identifica Ana e cria uma cópia candidata do estado.

6. apply encontra a sala; Room.guess verifica turno, versão e letra. Como Z não está na palavra, somente o contador de Ana aumenta, e a vez passa a Bruno.

7. O primário envia o estado candidato ao reserva. O reserva o guarda e responde com o ACK da revisão.

8. O primário adota a cópia candidata e responde a Ana. Ela limpa pending e desenha a resposta.

9. Bruno faz sua próxima consulta ESTADO e recebe a mesma evolução da partida. Seu terminal desenha o novo boneco de Ana e mantém seu próprio contador.

## 7.1 Exemplo de pedido

```json
{
  "type": "JOGAR",
  "request_id": "7c9646e2-17ac-4e8b-8ed4-a6d57e979a75",
  "name": "Ana",
  "token": "token-ficticio-com-pelo-menos-32-caracteres",
  "deployment": "identificador-da-execucao",
  "letter": "Z",
  "version": 3
}
```

Este exemplo está quebrado em várias linhas apenas para leitura. Na rede, send produz uma linha. Os identificadores são ilustrativos: o cliente real usa os valores da sessão e a versão recebida do servidor. O servidor deriva a identidade do token; um campo name não permite escolher livremente quem será o autor da jogada.

## 7.2 Três resultados diferentes

ok indica o resultado da operação: uma regra violada pode retornar ok false com um code, como FORA_DA_VEZ. retry significa que aquele servidor não pode atender normalmente agora; o cliente tenta o próximo endereço e preserva o comando pendente. fatal indica que a sessão pertence a outra execução do sistema; o cliente mostra a orientação e encerra.

Uma letra errada dentro das regras retorna ok true e a mensagem Errou!. A operação foi aceita, embora a tentativa não tenha acertado a palavra. Isso evita confundir erro do jogador com erro de comunicação ou comando inválido.

## 7.3 Consultas periódicas e diferença entre telas

O cliente espera 0,5 segundo ao final do ciclo normal e depois consulta ou envia o próximo comando. Esse comportamento é chamado consulta periódica, ou polling. O intervalo real também inclui o tempo de rede e processamento. O servidor responde às consultas; não dispara espontaneamente atualizações para todos os terminais.

Portanto, os dois jogadores podem enxergar uma atualização em instantes ligeiramente diferentes. O estado vem do mesmo servidor, mas os terminais não são atualizados no mesmo microssegundo. room_version ajuda a rejeitar uma tentativa baseada em uma versão antiga.

# 8. Vários jogadores, salas e limite de duas pessoas

O servidor mantém um World, que reúne os jogadores, as salas, o identificador da execução e o número da próxima sala. Cada Room guarda seus próprios participantes, palavra, letras, erros, turno, versão e resultado. Os jogadores são relacionados à sala por room_id.

## 8.1 Algoritmo de entrada

Ao receber ENTRAR, apply valida o nome e recupera ou cria o jogador. enter procura outra sala AGUARDANDO com exatamente um participante que esteja online. Se encontrar, coloca o novo jogador nela. Se não encontrar, cria uma sala com o próximo número.

| Entrada, com todos conectados | Sala | Situação |
| --- | --- | --- |
| Ana | sala-1 | Aguarda |
| Bruno | sala-1 | A partida começa |
| Caio | sala-2 | Aguarda |
| Dani | sala-2 | A partida começa |
| Edu | sala-3 | Aguarda |

A busca não escolhe salas em andamento nem salas com dois jogadores. Além disso, Room.start exige exatamente dois participantes e status AGUARDANDO. Há, portanto, a escolha correta da vaga no lobby e uma verificação adicional ao iniciar a partida.

Trecho real: forca/game.py, Room.start, linha 58.
```python
    def start(self, word: str):
        if len(self.players) != 2 or self.status != "AGUARDANDO":
            raise GameError("SALA_INVALIDA", "A sala precisa de dois jogadores para começar.")
        if not re.fullmatch(r"[A-Z]+", word):
            raise ValueError("A palavra deve conter apenas A a Z.")
        self.word = word
        self.errors = {p: 0 for p in self.players}
        self.turn = self.players[0]
        self.status = "EM_JOGO"
```

random.choice escolhe a palavra no primário quando o segundo jogador entra. O reserva recebe a palavra já sorteada dentro do estado completo. Ele não sorteia outra palavra para a mesma partida.

## 8.2 O que é a sala de espera

Uma sala com uma pessoa permanece AGUARDANDO. Não existe um servidor separado para a espera. O cliente continua consultando o estado, e o segundo participante inicia a partida. A ordem usual de chegada forma os pares quando os jogadores permanecem conectados; desconexões podem alterar qual sala tem um participante disponível.

Se Ana estava sozinha, desconecta, e Bruno entra enquanto ela está ausente, Bruno pode abrir outra sala. Quando Ana retorna e envia ENTRAR, enter pode juntá-la à sala de Bruno e cancelar a sala antiga com motivo REAGRUPADA. O cliente tenta fazer isso automaticamente ao reconectar por uma consulta ESTADO em AGUARDANDO. O caso de retorno com comando pendente ainda tem uma limitação registrada em melhorias.md.

## 8.3 Várias salas não se misturam

As letras e os erros ficam em cada Room. Uma tentativa de Caio na sala-2 não altera a palavra da sala-1. O servidor usa o token para encontrar o jogador e sua associação à sala. O cliente não envia uma sala arbitrária para autorizar uma jogada.

Apesar dessa independência das regras, o processamento usa uma trava global: uma operação pode esperar por outra sala enquanto a replicação termina. Isso simplifica o projeto, mas limita o desempenho quando há muitas salas. Múltiplos jogadores atendidos não significam que todas as alterações acontecem ao mesmo tempo.

# 9. O servidor como semáforo: três mecanismos

O requisito “um jogador por vez” é aplicado pela combinação de uma trava de processamento e uma regra de turno. Há também um semáforo de capacidade. Compreender a diferença evita explicar o código de forma incorreta na apresentação.

| Mecanismo | O que controla | Exemplo |
| --- | --- | --- |
| threading.Lock | Uma operação por vez na região protegida do servidor | Dois ENTRAR não ocupam a mesma última vaga |
| Room.turn e check_turn | Qual participante pode jogar naquela sala | Bruno é recusado enquanto for a vez de Ana |
| BoundedSemaphore(64) | Quantas conexões estão em atendimento | A conexão excedente é fechada quando as 64 vagas estão ocupadas |

## 9.1 A região protegida por Lock

Server.request usa with self.lock. Enquanto uma thread está nesse bloco, outra thread que precise da mesma trava espera. A sequência de validar, criar uma cópia, aplicar as regras, replicar e adotar o estado fica protegida contra outra requisição processada simultaneamente.

Sem a trava, duas entradas poderiam procurar uma vaga antes de qualquer uma registrar que a ocupou. Duas jogadas poderiam validar a mesma versão e depois sobrescrever alterações. A trava faz uma operação terminar sua etapa protegida antes de outra continuar.

A thread de sincronização também usa essa trava ao trocar mensagens com o reserva. Isso impede que um heartbeat e um estado sejam escritos e suas respostas lidas de forma intercalada por threads diferentes no mesmo stream. Threads atendem conexões concorrentemente, mas o trecho crítico fica serializado, ou seja, executado em sequência. A referência da biblioteca threading está em [R3].

## 9.2 A regra que autoriza o jogador

Trecho real: forca/game.py, Room.check_turn, linha 94.
```python
    def check_turn(self, player_id: str, expected_version):
        if player_id not in self.players:
            raise GameError("NAO_PARTICIPANTE", "Você não participa desta sala.")
        if self.status != "EM_JOGO":
            raise GameError("PARTIDA_INDISPONIVEL", "A partida ainda não começou, está pausada ou terminou.")
        if self.turn != player_id:
            raise GameError("FORA_DA_VEZ", "Aguarde a sua vez.")
        if type(expected_version) is not int or expected_version != self.version:
            raise GameError("ESTADO_DESATUALIZADO", "A sala mudou. Confira o estado atual e tente novamente.")
```

As verificações seguem esta ordem: o jogador participa da sala; a partida está em andamento; é sua vez; a versão esperada é um inteiro igual à versão atual. Só depois a tentativa de letra ou palavra é avaliada.

É possível Bruno mandar bytes pela rede enquanto Ana joga. O socket não bloqueia o teclado dele por causa do turno. Quem rejeita a operação é a regra no servidor, retornando FORA_DA_VEZ. As consultas de estado continuam funcionando para ambos.

Se a tentativa é válida, acertar ou errar passa a vez, exceto quando a partida termina. Letra repetida, letra inválida, palavra repetida ou tentativa fora da vez não adicionam erro nem passam o turno. A validação local do cliente ajuda a pessoa, mas a validação decisiva é a do servidor.

## 9.3 Versão da sala e revisão global

room_version indica a versão daquela sala. O cliente a devolve em JOGAR ou CHUTAR para dizer sobre qual estado está tentando agir. Se outro evento mudou a sala, a tentativa antiga recebe ESTADO_DESATUALIZADO.

revision é o contador global usado na replicação. Pode crescer com entradas, saídas e resultados de comandos rejeitados. Não é igual ao total de letras jogadas e não deve ser confundido com room_version. O ACK do reserva confirma revision, não a versão de uma sala isolada.

# 10. Estados, erros e os dois bonecos

O servidor controla os números de erros e o resultado. O cliente recebe dados e transforma esses números em desenhos. Assim, o programa não precisa transportar uma imagem: basta transmitir o estado necessário para que ambos os clientes montem a mesma representação.

## 10.1 Estados da sala

| Estado apresentado | Significado |
| --- | --- |
| AGUARDANDO | Há uma pessoa esperando o segundo jogador |
| EM_JOGO | A partida começou e os dois participantes são considerados presentes |
| PAUSADA | A sala está em andamento, mas há participante sem presença recente |
| ENCERRADA | Houve vencedor, por palavra completa, seis erros ou desistência |
| CANCELADA | Espera cancelada, abandono de nome ou reagrupamento |

PAUSADA é calculado por public_state quando falta presença recente; não substitui o status interno EM_JOGO no objeto Room. O servidor considera online quem consultou nos últimos cinco segundos. Fechar um socket depois de uma consulta não desconecta o jogador logicamente: isso é normal, pois as conexões são curtas.

O mapa seen guarda os horários de presença no servidor que atende. Esses horários não são replicados. Depois da promoção, cada cliente volta a consultar, reconstruindo a presença. Até os dois retornarem, a partida pode aparecer pausada.

## 10.2 Erros separados

Trecho real: forca/game.py, Room.conclude, linha 104.
```python
    def conclude(self, player_id: str, hit: bool, solved: bool):
        if not hit:
            self.errors[player_id] += 1
        opponent = next(p for p in self.players if p != player_id)
        if solved:
            self.finish(player_id, "PALAVRA_COMPLETA")
        elif self.errors[player_id] >= MAX_ERRORS:
            self.finish(opponent, "SEIS_ERROS")
        else:
            self.turn = opponent
        self.version += 1
```

errors é um dicionário por identificador de jogador. Quando hit é falso, somente self.errors[player_id] aumenta. Se a palavra foi resolvida, o autor vence. Se o autor chegou a seis erros, o adversário vence. Caso contrário, o turno passa ao adversário. A versão da sala aumenta após a tentativa válida.

O estado público contém uma lista de participantes, e cada item inclui name, errors e connected. Também inclui a palavra mascarada, as letras tentadas, os chutes errados e o turno. A palavra completa não é exposta como campo secreto ao cliente durante a partida; ela aparece na palavra mostrada depois do encerramento.

## 10.3 Do contador ao desenho

Trecho real: forca/ui.py, gallows, linha 15.
```python
def gallows(errors):
    head = "O" if errors >= 1 else " "
    trunk = "|" if errors >= 2 else " "
    left = "/" if errors >= 3 else " "
    right = "\\" if errors >= 4 else " "
    leg_left = "/" if errors >= 5 else " "
    leg_right = "\\" if errors >= 6 else " "
    return ["  +-----+", "  |     |", f"  {head}     |", f" {left}{trunk}{right}    |",
            f" {leg_left} {leg_right}    |", "        |", "  ========"]
```

| Erros do jogador | Parte acrescentada |
| --- | --- |
| 1 | Cabeça |
| 2 | Tronco |
| 3 | Primeiro braço |
| 4 | Segundo braço |
| 5 | Primeira perna |
| 6 | Segunda perna; o jogador perde |

render percorre os participantes e chama gallows para cada contador. Depois usa zip para colocar as linhas dos dois desenhos lado a lado. O identificador do cliente apenas determina qual nome recebe “(você)” e a frase “Sua vez”; os dois contadores continuam visíveis nos dois lados.

```text
====================================================================
FORCA | sala-1 | EM_JOGO

Ana (você)                        Bruno
  +-----+                           +-----+
  |     |                           |     |
  O     |                                 |
  |     |                                 |
        |                                 |
        |                                 |
  ========                          ========
Erros: 2/6                        Erros: 0/6

Palavra: S _ _ _ _ _
Letras tentadas: S, Z, X
Vez de Bruno. Aguarde.
====================================================================
```

O exemplo acima foi produzido pela própria função render, com um estado didático: Ana tem dois erros e Bruno tem zero. No terminal de Bruno, os desenhos e números seriam os mesmos, mas “(você)” apareceria ao lado de Bruno. Não é uma captura de uma partida real.

# 11. Replicação: como a cópia chega à outra máquina

Replicar significa manter outra cópia dos dados. Neste projeto, ambas as cópias ficam em RAM, a memória usada pelo processo enquanto está rodando. JSON é o formato utilizado para transportar a cópia; não existe um arquivo JSON de partidas que os servidores compartilham por uma pasta de rede.

## 11.1 O que é copiado

O estado contém world, receipts e revision. world inclui jogadores, salas, palavras secretas, letras, chutes, erros, turnos, resultados e deployment_id. receipts guarda o último resultado de comando de cada jogador, usado em reenvios. revision identifica a revisão global da cópia.

Não se transfere a RAM inteira do computador. Não se copiam threads, sockets abertos, o sistema operacional nem a tela do terminal. O programa seleciona um dicionário com os dados necessários e o transmite. O reserva tem seu próprio processo Python e seus próprios recursos.

## 11.2 Conexão inicial do reserva

Server.synchronize escuta na porta 5001 do primário. Server.follow, no reserva, usa create_connection para chegar a essa porta. Portanto, nesse canal, o reserva desempenha o papel de quem inicia uma conexão, mesmo sendo chamado de servidor no projeto.

1. O reserva envia a chave compartilhada em um objeto com key.

2. O primário compara a chave com hmac.compare_digest e envia seu estado atual.

3. O reserva atribui a cópia recebida a self.state e envia ack com a revisão guardada.

4. O primário prossegue e envia uma segunda mensagem, normalmente um heartbeat.

5. Ao receber a segunda mensagem, o reserva passa a estar apto a assumir se a conexão falhar.

A segunda mensagem é importante: ela indica que o primário avançou além da espera pelo ACK inicial. Se o reserva recebesse a cópia e sumisse antes de concluir essa etapa, ele ainda não poderia se promover; o primário pode aguardar outra tentativa de sincronização inicial.

## 11.3 Cada alteração espera confirmação

Trecho real: servidor.py, Server.replicate, linha 44.
```python
    def replicate(self, candidate):
        # O reserva guarda a cópia ANTES de enviar ACK. Só então o jogador recebe sucesso.
        send(self.backup, {"state": candidate})
        ack = receive(self.backup)
        if ack.get("ack") != candidate["revision"]:
            raise ConnectionError("Confirmação de replicação inválida.")
```

A cópia candidata é enviada inteira. O reserva recebe a mensagem, guarda o estado e responde com sua revisão. Se o ACK não corresponder à revisão esperada, replicate levanta uma falha de comunicação.

```text
Primário: deepcopy do estado atual
Primário: aplica o comando na cópia candidata
Primário -> reserva: {"state": candidato}
Reserva: self.state = estado recebido
Reserva -> primário: {"ack": revisão}
Primário: self.state = candidato
Primário -> cliente: resultado e estado público
```

deepcopy cria uma cópia independente das estruturas de dados. Assim, aplicar a regra no candidato não modifica imediatamente o estado que o primário adotou. Se a replicação falhar, ele pausa em vez de confirmar um estado sem a segunda cópia.

Essa replicação é chamada síncrona porque a resposta normal ao cliente espera a confirmação do reserva. Ela acrescenta tempo à jogada, mas permite que uma resposta confirmada antes da queda esteja na cópia do reserva. Depois da promoção, essa espera é desativada, pois não existe outro reserva conectado nesta versão.

## 11.4 Heartbeat

Heartbeat é uma mensagem pequena para verificar se a comunicação continua viva. O primário envia {"heartbeat": true}, recebe a resposta correspondente e espera 0,5 segundo para repetir. Isso ajuda a detectar uma falha mesmo quando nenhum jogador está enviando uma tentativa.

O canal é persistente: a mesma conexão transporta vários estados e heartbeats. No primário há timeout de três segundos nesse canal; no reserva, cinco segundos para receber. Fechar o processo pode gerar erro rapidamente; desligar fisicamente o computador pode exigir esperar o timeout.

# 12. O que acontece quando uma máquina cai

## 12.1 Queda do primário depois da sincronização

O reserva tenta ler a próxima mensagem e encontra conexão encerrada, erro de rede ou timeout. Como já recebeu a segunda mensagem da sincronização inicial, follow sai do ciclo de acompanhamento, marca promoted como verdadeiro e chama serve. A porta de jogadores passa a ser atendida no IP do próprio reserva.

Os clientes não recebem uma conexão TCP transplantada de uma VM para a outra. A conexão antiga falha. Cada cliente tenta outro endereço da lista --servers e abre uma nova conexão. Ele apresenta a mesma identidade de sessão, e o novo servidor encontra a sala no estado replicado.

O IP do primário também não é transferido. Não há IP virtual, proxy ou balanceador neste projeto. A troca acontece porque o cliente conhece os dois endereços e tenta o próximo ao detectar erro ou retry.

## 12.2 A resposta pode se perder depois de a jogada ser aplicada

Considere que o reserva já guardou a tentativa de Ana, mas o primário cai antes de a resposta chegar ao terminal dela. Ana não sabe se a tentativa valeu. Seu cliente preservou pending e reenvia o mesmo request_id ao reserva promovido. O recibo replicado permite reconhecer que a operação já aconteceu e devolver seu resultado, sem acrescentar outro erro nem passar a vez novamente.

O jogo também pode continuar com uma operação cujo retorno ficou incerto, pois o estado já havia chegado ao reserva. Por isso, “não recebi resposta” não significa automaticamente “nada aconteceu”. Reenvio e recibo resolvem essa dúvida no fluxo normal do cliente.

## 12.3 Matriz de falhas

| Situação | Comportamento atual |
| --- | --- |
| Primário cai após sincronização | Reserva assume; clientes reconectam |
| Reserva cai | Primário se pausa; a partida não continua normalmente |
| Primário nunca sincronizou | Alterações ficam bloqueadas; reserva não assume sem estado confirmado inicialmente |
| Ambos encerram | Partidas em RAM são perdidas |
| Rede entre servidores falha | Primário deixa de confirmar alterações; reserva pode assumir por timeout |
| Cliente fecha | Após ausência de cinco segundos, a partida aparece pausada |
| Antigo primário volta | Não há reintegração automática ao novo ativo |
| Reserva promovido também cai | Não há outra cópia disponível nesta execução |

Timeout é um sinal de ausência de comunicação, não uma prova de que o outro computador desligou. Para a demonstração, o cenário esperado é a parada do primário com o reserva e a rede funcionando. O desenho evita que o primário continue confirmando alterações sem ACK, mas não implementa eleição por maioria ou gerenciamento completo de reintegração.

Não basta religar o antigo primário para recuperar redundância. O reserva promovido não inicia o atendimento de um novo canal de replicação nessa versão. Para repetir o experimento, encerrem os dois servidores e iniciem uma nova execução sincronizada; os clientes então precisam de novas sessões. As partidas da execução anterior não são restauradas.

## 12.4 VM, container e computador físico

VirtualBox executa a VM; Docker executa o processo em um container dentro dela. Nenhum deles copia automaticamente as partidas deste programa para outro computador. A réplica do jogo é criada por Server.replicate e Server.follow.

Duas VMs no mesmo notebook compartilham a falha do notebook: se ele desligar, as duas param. Para o teste do professor, cada VM deve estar em um computador físico diferente. Os clientes que serão observados precisam ficar em um equipamento que permaneça ligado, assim como o roteador ou switch.

# 13. Sessões, identidade e comandos pendentes

O arquivo sessions/ana.json é do cliente. Ele guarda token, deployment e pending. Não contém a cópia oficial das partidas e não sincroniza a VM 1 com a VM 2. A sincronização das salas acontece no canal TCP entre os servidores.

| Campo ou arquivo | Finalidade |
| --- | --- |
| token | Segredo aleatório que identifica o jogador ao servidor |
| player_id | Identificador obtido com SHA-256 do token |
| deployment | Identifica a execução dos servidores à qual a sessão pertence |
| pending | Um comando que ainda aguarda resposta definitiva |
| request_id | Identifica uma tentativa específica, inclusive em seus reenvios |
| .lock | Apoia a trava local que impede uso simultâneo do mesmo arquivo de sessão |

## 13.1 Por que só o nome não basta

O nome é uma identificação para exibição; o token diferencia a sessão. Ao fechar e reabrir com o mesmo arquivo, o cliente usa o token antigo e pode retomar a sala. --nova-sessao gera outra identidade. Portanto, usar esse parâmetro sem querer pode impedir a retomada desejada ou resultar em NOME_EM_USO enquanto o jogador antigo continua ativo.

Nomes ativos são únicos em todas as salas, ignorando maiúsculas e espaços nas pontas. /sair libera o nome. Fora de partida em andamento, outro jogador pode reaproveitar um nome cujo dono ficou 180 segundos sem consultar. A liberação é avaliada quando outro ENTRAR solicita aquele nome; não há um serviço apagando nomes exatamente no segundo 180.

Na inicialização e após a promoção, since dá uma referência de tempo para quem ainda não consultou. Isso impede que a ausência de históricos de presença no reserva promova uma liberação imediata dos nomes.

## 13.2 Como pending protege uma tentativa

Antes de enviar, o cliente grava o comando completo em pending. O arquivo é escrito primeiro em um .tmp e depois substitui o anterior. Se a rede falhar, o mesmo comando permanece disponível. Se o cliente for reaberto com a mesma sessão, ele também pode tentar esse comando novamente.

O servidor guarda apenas o recibo do último comando de cada jogador. Esse desenho acompanha o cliente oficial, que mantém uma única operação pendente por vez. Não é uma promessa de reconhecer qualquer comando antigo reenviado fora de ordem por um cliente modificado.

Para comparar um reenvio, apply verifica request_id e uma impressão digital do conteúdo. Impressão digital é um resumo calculado por hash. Mesmo identificador com conteúdo diferente gera erro, porque não representa uma repetição válida. Quando uma operação recebeu um erro definitivo e a pessoa faz outra tentativa, o cliente gera um novo identificador.

## 13.3 Fechar e desistir são ações distintas

Ctrl+C fecha o cliente e conserva a sessão para retorno. /sair envia SAIR, encerra a participação e, durante uma partida, dá vitória ao adversário. Uma desconexão não equivale automaticamente a desistência. Se os dois servidores forem reiniciados, deployment muda; o arquivo antigo não recria a partida perdida em RAM.

Existe uma limitação conhecida: nomes como Ana e A-na podem resultar no mesmo nome de arquivo local, porque só caracteres alfanuméricos são usados. A opção --session permite escolher caminhos diferentes. A correção definitiva está registrada em melhorias.md.

# 14. Como executar com Python, VMs e Docker

## 14.1 Primeiro teste: tudo no mesmo computador

Execute na raiz do projeto, onde estão servidor.py e cliente.py. Abra quatro terminais. Este roteiro valida o fluxo básico, mas não comprova resistência ao desligamento desse computador.

```text
Terminal 1:
python servidor.py

Terminal 2:
python servidor.py --modo reserva --port 5002

Terminal 3:
python cliente.py --name Ana --nova-sessao

Terminal 4:
python cliente.py --name Bruno --nova-sessao
```

Espere o log Reserva sincronizado. Jogadas liberadas. O cliente já usa por padrão 127.0.0.1:5000 e 127.0.0.1:5002. A porta 5002 evita conflito entre dois servidores de jogadores no mesmo endereço; o reserva continua conectando à porta de replicação 5001.

Em Windows, .\scripts\forca.ps1 servidor é um atalho executado a partir da raiz. Se o terminal já estiver dentro de scripts, o caminho é .\forca.ps1 servidor. No Ubuntu, use python3 quando esse for o nome do executável instalado.

## 14.2 Duas VMs em computadores distintos

Use os endereços a seguir apenas como exemplo: VM primária 192.168.1.10, VM reserva 192.168.1.20. Ambas devem estar acessíveis na mesma rede local. No VirtualBox, a configuração planejada é rede em modo Bridge: a VM participa da rede por um endereço próprio. Confirme seus endereços com ip -4 addr no Ubuntu.

Copie o projeto para cada VM. Instale Docker Engine e o plugin Compose para executar a entrega dockerizada. Confirme a instalação com docker --version e docker compose version. A instalação depende da distribuição; use as instruções oficiais correspondentes [R5]. Os clientes usam Python 3.12 ou superior e rodam fora dos containers no fluxo atual.

Na raiz de cada cópia, crie .env a partir de .env.example, por exemplo com cp .env.example .env no Linux. Ajuste os valores de acordo com a VM. A chave abaixo é ilustrativa; escolha o mesmo valor nas duas.

```text
# .env da VM 1
MODO=primario
PRIMARY_HOST=192.168.1.10
REPLICATION_KEY=chave-da-equipe

# .env da VM 2
MODO=reserva
PRIMARY_HOST=192.168.1.10
REPLICATION_KEY=chave-da-equipe
```

Execute docker compose up --build primeiro na VM primária e depois na reserva. Mantenha os logs visíveis. Os clientes devem usar os dois IPs reais:

```text
python cliente.py --name Ana --servers 192.168.1.10:5000,192.168.1.20:5000
python cliente.py --name Bruno --servers 192.168.1.10:5000,192.168.1.20:5000
```

Adicione --nova-sessao para começar uma nova identidade, inclusive depois de reiniciar os dois servidores. Para retomar uma partida da mesma execução, conserve a sessão existente e não acrescente esse parâmetro.

## 14.3 O papel do Dockerfile e do Compose

Dockerfile parte da imagem Python 3.12.13 slim, define /app como pasta de trabalho, copia o código e executa python servidor.py. Uma imagem é o pacote preparado para executar o programa; um container é uma execução dessa imagem. Não há instalação de pacotes de terceiros para o jogo.

EXPOSE 5000 5001 documenta as portas da imagem. É a seção ports do Compose que publica as portas na VM, associando 5000 a 5000 e 5001 a 5001. Publicar uma porta do container não abre automaticamente um firewall externo. No reserva, a porta 5000 só terá atendimento depois da promoção; publicar a porta não cria um servidor de jogadores antes disso.

O Compose passa MODO, PRIMARY_HOST e REPLICATION_KEY ao processo. GAME_PORT e SYNC_PORT são opções disponíveis no servidor, mas o Compose atual não as repassa e mantém o mapeamento fixo. Para mudar as portas na entrega Docker, seria necessário ajustar a configuração de ambiente e os mapeamentos de forma coerente.

restart: "no" evita reinício automático do antigo primário durante a demonstração. Reiniciar um container não restaura a RAM anterior nem o reintegra à partida recuperada. O mecanismo de continuidade é o reserva da aplicação.

## 14.4 Portas, firewall e internet

Na mesma rede local, não é necessário abrir encaminhamento de portas na internet do roteador. É necessário permitir que os dispositivos locais alcancem TCP 5000 nas duas VMs e que o reserva alcance TCP 5001 do primário. Firewalls e isolamento de dispositivos no Wi-Fi podem impedir essa comunicação.

No Windows, Test-NetConnection 192.168.1.10 -Port 5000 verifica se a porta aceita conexão. No Ubuntu, nc -vz 192.168.1.10 5001 pode ajudar, se nc estiver instalado. Esses testes verificam conexão, não validam o protocolo do jogo nem o ACK da replicação. Antes da promoção, é esperado que o reserva não atenda jogadores em 5000.

Prepare as imagens Docker antes da apresentação. Com imagens já construídas e os dispositivos na rede local, o jogo não depende de internet para comunicar clientes e servidores. Logs podem ser acompanhados com docker compose logs -f servidor; docker compose down encerra os containers e perde o estado em RAM daquela execução.

# 15. Testes e roteiro para apresentar ao professor

## 15.1 O que foi validado automaticamente

```text
python -m unittest discover -s tests -v
Resultado desta documentação: 50 testes, OK, 8,382 segundos.
Ambiente: processos locais no Windows, comunicação TCP local.
```

| Arquivo de testes | Quantidade | Exemplos cobertos |
| --- | --- | --- |
| test_game.py | 18 | Turno, letras, acentos, chutes, vitória e seis erros |
| test_lobby.py | 17 | Salas, nomes, reagrupamento, pausa e reenvio |
| test_cliente.py | 9 | JSON por linha, comandos, tela e trava de sessão |
| test_servidor.py | 6 | Processos TCP reais, replicação, promoção e sincronização inicial |

Os testes de servidor abrem portas locais escolhidas para a execução e encerram processos de teste. O teste de promoção compara o estado antes e depois de matar o primário e verifica um reenvio. Ele não representa desligamento elétrico, rede Bridge real nem falha em todas as janelas possíveis entre envio e confirmação.

O arquivo melhorias.md também identifica partes ainda sem cobertura automática completa, como o laço de teclado/reconexão do cliente, o caminho fatal de execução antiga e o limite de crescimento do estado. Ter 50 testes aprovados não significa ausência de qualquer defeito.

## 15.2 Roteiro de demonstração

1. Mostrem os dois computadores físicos, suas VMs e os containers. Expliquem qual é o primário e qual é o reserva.

2. Mostrem o log de sincronização e a lista dos dois endereços usada pelos clientes.

3. Abram Ana e Bruno: Ana espera, Bruno entra e a sala começa. Abram Caio e Dani: eles iniciam outra sala. Abram Edu: ele aguarda na terceira sala.

4. Enviem uma tentativa fora da vez. Mostrem que o servidor a rejeita e que erros e turno não são alterados por essa tentativa.

5. Façam um erro válido de Ana. Mostrem que só seu contador aumenta e que ambos os clientes desenham seu novo membro.

6. Registrem sala, palavra parcial, letras, erros, turno e versão antes da falha. Façam isso também na segunda sala.

7. Desliguem fisicamente o computador do primário. Mantenham clientes e rede no equipamento que fica ligado. Iniciem a medição do tempo.

8. Mostrem a promoção do reserva no log e a reconexão dos clientes. Confiram os dados registrados antes da queda e continuem jogando.

9. Abram um sexto jogador e verifiquem que encontra Edu esperando. Expliquem que agora há uma única cópia em execução.

10. Anotem o tempo e eventuais problemas. Para repetir, preparem uma nova execução dos dois servidores, com novas sessões.

## 15.3 Ficha de evidências para preencher

| Item | Registro do grupo |
| --- | --- |
| Data e integrantes | __________________________________ |
| IPs das VMs e computadores usados | __________________________________ |
| Reserva sincronizado antes da queda | __________________________________ |
| Salas e estados antes da queda | __________________________________ |
| Estado correspondente após a troca | __________________________________ |
| Tempo observado até retomar jogadas | __________________________________ |
| Próxima jogada aceita no reserva | __________________________________ |

Não há um resultado preenchido para o desligamento físico neste documento, porque esse teste não foi realizado durante sua geração. O objetivo de recuperação em até 15 segundos presente na especificação é uma meta a medir, não um valor garantido pelo código.

# 16. Dúvidas comuns e diagnóstico

## 16.1 “Fica aguardando primeira sincronização”

Significa que o reserva ainda não completou a etapa necessária para poder assumir. Verifiquem se o primário está executando, se PRIMARY_HOST aponta para o IP correto, se TCP 5001 está acessível e se as chaves são iguais. O primário pode estar atendendo 5000 e ainda não ter um reserva sincronizado; nesse caso, devolve retry aos comandos normais.

## 16.2 “O socket sabe quem é Ana?”

O socket conhece endereços e transporta bytes. A identidade do jogo vem do token no protocolo. Como o cliente abre conexões novas o tempo todo, usar a conexão como identidade permanente não serviria para retomar a mesma pessoa após uma queda.

## 16.3 “O JSON salva a partida?”

JSON é um formato. O projeto usa JSON tanto nas mensagens quanto no arquivo de sessão, com funções diferentes. O JSON enviado ao reserva carrega o estado das partidas; sessions guarda apenas os dados do cliente. Não há arquivo persistente de partidas no servidor. Se os dois processos perderem a RAM, os arquivos de sessão não reconstroem o jogo.

## 16.4 “Por que o reserva não atende antes da queda?”

Enquanto executa follow, o reserva está recebendo e guardando cópias. Ele só chama serve depois de perder o primário após a sincronização. Isso mantém um responsável pelo atendimento das partidas no fluxo normal.

## 16.5 “Posso usar a mesma porta nas duas máquinas?”

Sim. A combinação IP e porta é que determina o destino. 192.168.1.10:5000 e 192.168.1.20:5000 são destinos diferentes. No teste com os dois no mesmo endereço, o projeto usa 5000 e 5002 para os atendimentos de jogadores.

## 16.6 “Por que voltamos para outra sala?”

Confira se o cliente está usando o mesmo arquivo de sessão e se foi iniciado sem --nova-sessao. Confira também se houve /sair ou reinício dos dois servidores. A retomada depende do token e da execução ainda existente, não apenas do texto do nome. Jogadores esperando podem ser reagrupados em outra sala por uma regra prevista no lobby.

## 16.7 “O status passa sozinho para os clientes?”

O programa consulta automaticamente, mas o protocolo é de pedido e resposta. Cada cliente pede ESTADO periodicamente; o servidor responde com a sala. /estado, digitado pela pessoa, mostra o último estado recebido no cliente, enquanto as consultas automáticas continuam no laço normal.

## 16.8 Limites para manter o projeto compreensível

O estado inteiro é copiado e transmitido a cada comando processado. Salas encerradas e jogadores antigos ficam na memória, e a mensagem tem limite de 2 MB. Isso limita uma execução muito longa. O projeto privilegia uma demonstração pequena e legível, sem alegar capacidade para grandes quantidades de jogadores.

O tráfego não usa TLS, isto é, não tem a camada de criptografia normalmente associada a conexões seguras. A chave compartilhada protege de forma básica a entrada no canal de replicação, mas não cifra palavras ou tokens em trânsito. A documentação considera a rede local controlada da aula.

# 17. Glossário e mapa de leitura do código

| Termo | Explicação no contexto do jogo |
| --- | --- |
| Socket | Ponta de comunicação usada por um processo |
| TCP | Transporte que oferece um fluxo ordenado de bytes por conexão |
| Protocolo | Regras de formato, mensagens e respostas combinadas pelos programas |
| Buffer | Área temporária em que bytes podem aguardar escrita ou leitura |
| Serialização | Conversão de dados para uma representação transmissível |
| Thread | Linha de execução dentro de um processo |
| Região crítica | Trecho que acessa dados compartilhados e precisa de proteção |
| Lock | Trava que permite uma thread por vez no trecho protegido |
| ACK | Confirmação; aqui, mensagem de que o reserva guardou certa revisão |
| Heartbeat | Mensagem periódica para acompanhar a comunicação |
| Replicação síncrona | Atualização que espera a confirmação da outra cópia |
| Promoção | Reserva passa a atender jogadores como ativo |
| Deduplicação | Reconhecer reenvio para não repetir a operação |
| Estado público | Dados da sala que o cliente pode receber para exibir o jogo |
| Failover | Troca do atendimento para o reserva após uma falha |

## 17.1 Funções para mostrar na apresentação

Comecem por cliente.exchange e Server.listen/serve para demonstrar sockets reais. Mostrem send e receive em wire.py para explicar bytes, JSON e a quebra de linha. Em seguida, mostrem Server.request para ligar rede, regras e replicação.

Para as salas, mostrem lobby.enter e Room.start. Para “um por vez”, mostrem self.lock e Room.check_turn, deixando claro que a trava e o turno têm papéis diferentes. Para os bonecos, mostrem Room.conclude, Room.public e ui.gallows/render.

Para a queda do primário, mostrem Server.replicate, Server.attend_backup, Server.follow e o tratamento de falha no laço cliente.run. O apêndice mantém o código integral para acompanhar essa leitura sem depender de trechos isolados.

## 17.2 Exercícios de compreensão

1. Explique por que duas pessoas podem usar a porta 5000 sem compartilhar a mesma sessão.

2. Identifique onde a palavra é escondida do cliente, mas enviada ao reserva.

3. Descreva o que acontece se o ACK chega ao primário e a resposta ao jogador se perde.

4. Diferencie a fila de listen, a Queue do teclado e uma sala AGUARDANDO.

5. Explique por que duas VMs no mesmo computador não atendem ao teste de desligar esse computador.

6. Mostre o caminho de errors[player_id] até a cabeça desenhada nos dois terminais.

# 18. Referências e rastreabilidade

O código do próprio projeto é a fonte principal para todas as afirmações sobre comportamento, valores, regras e limitações. Os trechos e o apêndice foram extraídos dos arquivos da revisão 1ecf32097d7be882137d817587b803ad3b503e63. Consulte README.md, ARCHITECTURE.md, ROADMAP.md, melhorias.md e docs/protocolo-etapa-1.md para a documentação original do repositório.

As referências abaixo complementam os conceitos de biblioteca e infraestrutura. Elas não demonstram que o teste físico do grupo foi realizado. As APIs explicadas foram confrontadas com a documentação oficial durante a preparação deste guia.

R1. Python - socket, interface de programação de rede. https://docs.python.org/3/library/socket.html

R2. Python - Socket Programming HOWTO. https://docs.python.org/3/howto/sockets.html

R3. Python - threading, threads e primitivas de sincronização. https://docs.python.org/3/library/threading.html

R4. Docker - configuração de serviços no Compose. https://docs.docker.com/reference/compose-file/services/

R5. Docker - instalação do Docker Engine no Ubuntu. https://docs.docker.com/engine/install/ubuntu/

Os exemplos usam APIs presentes no Python 3.12 ou superior, conforme o projeto. Os endereços IP apresentados são exemplos. A fonte editável deste documento acompanha o PDF em docs/documentacao-completa-sockets.md.

# Apêndice A. Código integral da versão documentada

As páginas seguintes reproduzem o código do jogo, testes, scripts existentes e configurações de execução. Não incluem .env real, arquivos de sessão, dados pessoais, dependências instaladas nem arquivos internos do Git. Os números à esquerda são números de linha do arquivo original; linhas muito longas podem continuar visualmente na linha seguinte, sem alterar o conteúdo.

O script de geração da especificação anterior também aparece por fazer parte do projeto, embora não execute o jogo. Ele depende de ReportLab e fontes do Windows. O jogo e seus testes usam a biblioteca padrão. O apêndice documenta o estado atual dos arquivos e não modifica a implementação.

## forca/wire.py
SHA-256: a5ee2aa19e1b2ca5ea5a55b6bdcf022abc5eaa4a807d7ba543af5b1fcd414bb9
```
"""TCP transporta bytes: cada JSON termina com uma quebra de linha."""
import json

MAX_BYTES = 2_000_000


def send(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("Estado grande demais para o limite desta demonstração.")
    stream.write(data)
    stream.flush()


def receive(stream):
    line = stream.readline(MAX_BYTES + 1)
    if not line:
        raise ConnectionError("Conexão encerrada.")
    if len(line) > MAX_BYTES or not line.endswith(b"\n"):
        raise ValueError("Mensagem incompleta ou grande demais.")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("A mensagem deve ser um objeto JSON.")
    return message

```

## servidor.py
SHA-256: b59f64c690508377a6bdd58c60f4b5cb321ef8f0b78256e5bad16bd64910f935
```
"""Servidor ativo/reserva em RAM. Execute --help para ver as opções."""
import argparse
import copy
import hmac
import logging
import os
from pathlib import Path
import socket
import threading
import time

from forca.game import load_words
from forca.lobby import NAME_HOLD, apply, new_state, player_id, public_state
from forca.wire import receive, send

LOG = logging.getLogger("forca")
WORDS = Path(__file__).parent / "forca/words.txt"


class Server:
    def __init__(self, host="0.0.0.0", port=5000, sync_port=5001,
                 key="forca-aula", words=None):
        self.host, self.port, self.sync_port = host, port, sync_port
        self.key = key
        self.words = load_words(words or WORDS.read_text(encoding="utf-8").splitlines())
        self.state = new_state()
        self.seen = {}  # Presença local; uma conexão antiga não migra entre máquinas.
        self.since = time.monotonic()  # Início do atendimento; após a promoção, recomeça.
        self.lock = threading.Lock()  # Semáforo: validar + replicar é uma operação indivisível.
        self.backup = None
        self.promoted = False
        self.frozen = False
        self.slots = threading.BoundedSemaphore(64)

    def online(self):
        return {pid for pid, instant in self.seen.items() if time.monotonic() - instant < 5}

    def idle(self):
        """Jogadores sem consultar há NAME_HOLD segundos. Quem nunca consultou conta desde self.since."""
        now = time.monotonic()
        return {pid for pid in self.state["world"]["players"]
                if now - self.seen.get(pid, self.since) >= NAME_HOLD}

    def replicate(self, candidate):
        # O reserva guarda a cópia ANTES de enviar ACK. Só então o jogador recebe sucesso.
        send(self.backup, {"state": candidate})
        ack = receive(self.backup)
        if ack.get("ack") != candidate["revision"]:
            raise ConnectionError("Confirmação de replicação inválida.")

    def request(self, command):
        with self.lock:
            if command.get("type") == "PING":
                return {"ok": True, "role": "RESERVA_PROMOVIDO" if self.promoted else "PRIMARIO"}
            if self.frozen or (not self.promoted and self.backup is None):
                return {"retry": True, "message": "Primário aguardando reserva ou pausado."}
            pid = player_id(command.get("token"))
            deployment = command.get("deployment")
            if deployment and deployment != self.state["world"]["deployment_id"]:
                return {"fatal": True, "message": "Esta sessão pertence a outra execução. Use --nova-sessao."}
            self.seen[pid] = time.monotonic()
            result = {"ok": True}
            if command.get("type") != "ESTADO":
                candidate = copy.deepcopy(self.state)
                result = apply(candidate, command, self.online(), self.words, self.idle())
                if not self.promoted:
                    try:
                        self.replicate(candidate)
                    except (OSError, ValueError):
                        self.frozen = True
                        LOG.error("Replicação perdida: primário PAUSADO. Reinicie como reserva após o teste.")
                        return {"retry": True, "message": "Replicação interrompida. Procurando reserva."}
                self.state = candidate
                LOG.info("Estado %s confirmado (%s).", self.state["revision"], command["type"])
            return {**result, "player_id": pid,
                    "deployment": self.state["world"]["deployment_id"],
                    "state": public_state(self.state, pid, self.online()),
                    "role": "RESERVA_PROMOVIDO" if self.promoted else "PRIMARIO"}

    def client(self, connection):
        try:
            with connection:
                connection.settimeout(4)
                with connection.makefile("rwb") as stream:
                    try:
                        response = self.request(receive(stream))
                    except (ValueError, KeyError, TypeError) as exc:
                        response = {"ok": False, "message": f"Comando inválido: {exc}"}
                    except Exception:  # Um comando inesperado não pode ficar sem resposta.
                        LOG.exception("Erro inesperado ao atender um comando.")
                        response = {"ok": False, "message": "Erro interno do servidor."}
                    send(stream, response)
        except (OSError, ValueError):
            pass  # O cliente reenviará a mesma tentativa ao reconectar.
        finally:
            self.slots.release()

    def listen(self, port):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, port))
        listener.listen(64)
        return listener

    def serve(self):
        with self.listen(self.port) as listener:
            LOG.info("Atendendo jogadores em %s:%s", self.host, self.port)
            while True:
                connection, _ = listener.accept()
                if self.slots.acquire(blocking=False):
                    threading.Thread(target=self.client, args=(connection,), daemon=True).start()
                else:
                    connection.close()

    def synchronize(self):
        with self.listen(self.sync_port) as listener:
            LOG.info("Aguardando reserva na porta %s", self.sync_port)
            while True:
                connection, _ = listener.accept()
                try:
                    with connection:
                        connection.settimeout(3)
                        with connection.makefile("rwb") as stream:
                            self.attend_backup(stream)
                except (OSError, ValueError):
                    pass  # Fechar um canal rompido também falha ao descarregar o buffer.

    def attend_backup(self, stream):
        try:
            hello = receive(stream)
            # Em bytes: compare_digest recusa texto com acentos, o que derrubaria esta thread.
            if not hmac.compare_digest(str(hello.get("key", "")).encode(), self.key.encode()):
                return
            with self.lock:
                if self.frozen:
                    return
                self.backup = stream
                try:
                    self.replicate(self.state)
                except (OSError, ValueError):
                    # O reserva só assume depois da segunda mensagem (ver follow); sem ela, não há
                    # risco de dois ativos e o primário pode esperar outro reserva em vez de pausar.
                    self.backup = None
                    LOG.warning("Sincronização inicial com o reserva falhou; aguardando nova tentativa.")
                    return
            LOG.info("Reserva sincronizado. Jogadas liberadas.")
            while True:
                with self.lock:  # O primeiro heartbeat sai logo após o ACK: o reserva passa a poder assumir.
                    if self.frozen:
                        break
                    send(stream, {"heartbeat": True})
                    if receive(stream).get("heartbeat") is not True:
                        raise ConnectionError("Heartbeat inválido.")
                time.sleep(0.5)
        except (OSError, ValueError):
            with self.lock:
                if self.backup is stream:
                    self.frozen = True
                    LOG.warning("Ligação com reserva perdida; primário pausado.")
        finally:
            with self.lock:
                if self.backup is stream:
                    self.backup = None

    def follow(self, primary):
        synchronized = False
        while not synchronized:
            try:
                with socket.create_connection((primary, self.sync_port), timeout=3) as connection:
                    connection.settimeout(5)
                    with connection.makefile("rwb") as stream:
                        send(stream, {"key": self.key})
                        first = True
                        while True:
                            message = receive(stream)
                            # Só assume depois da segunda mensagem: ela prova que o primário recebeu
                            # o ACK da cópia inicial e não vai procurar outro reserva.
                            synchronized = synchronized or not first
                            first = False
                            if "state" in message:
                                self.state = message["state"]
                                send(stream, {"ack": self.state["revision"]})
                            else:
                                send(stream, {"heartbeat": True})
            except (OSError, ValueError):
                if not synchronized:
                    LOG.info("Aguardando primeira sincronização com %s...", primary)
                    time.sleep(1)
        self.promoted = True
        self.since = time.monotonic()  # Os jogadores ainda vão reconectar: ninguém perde o nome já.
        LOG.warning("PRIMÁRIO CAIU: reserva assumiu na revisão %s. Agora há apenas uma cópia.",
                    self.state["revision"])
        self.serve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modo", choices=["primario", "reserva"], default=os.getenv("MODO", "primario"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("GAME_PORT", "5000")))
    parser.add_argument("--sync-port", type=int, default=int(os.getenv("SYNC_PORT", "5001")))
    parser.add_argument("--primario", default=os.getenv("PRIMARY_HOST", "127.0.0.1"))
    parser.add_argument("--key", default=os.getenv("REPLICATION_KEY", "forca-aula"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        server = Server(args.host, args.port, args.sync_port, args.key)
    except ValueError as exc:
        raise SystemExit(f"Lista de palavras inválida ({WORDS.name}): {exc}")
    try:
        if args.modo == "reserva":
            server.follow(args.primario)
        else:
            threading.Thread(target=server.synchronize, daemon=True).start()
            server.serve()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()

```

## cliente.py
SHA-256: ec9af9bc78f0cc3b9a7da0562f65f0716598199c11242d201985dd0060886925
```
"""Terminal com reconexão: a sessão identifica o jogador mesmo após a queda."""
import argparse
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
import uuid

try:
    import msvcrt
except ImportError:
    import fcntl

from forca.game import normalize
from forca.ui import HELP, render
from forca.wire import receive, send


def exchange(address, command):
    host, port = address.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=2) as connection:
        connection.settimeout(5)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


def read_keyboard(commands):
    while True:
        try:
            commands.put(input().strip())
        except (EOFError, KeyboardInterrupt):
            commands.put("/sair")
            return


def save(path, session):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session), encoding="utf-8")
    temporary.replace(path)


def lock(path):
    """Impede dois clientes abertos com o mesmo arquivo de sessão. O sistema libera ao encerrar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_suffix(".lock"), "a+b")
    handle.seek(0)
    try:
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def parse(action, state):
    """Converte o que foi digitado em comando para o servidor, ou em um aviso local (str)."""
    name, _, argument = action.partition(" ")
    name = name.lower()
    version = state["room_version"] if state else None
    if name == "/nova":
        return {"type": "ENTRAR"}
    if name == "/sair":
        return {"type": "SAIR"}
    if name == "/chute":
        if not argument.strip():
            return "Use /chute seguido da palavra. Exemplo: /chute SOCKET"
        return {"type": "CHUTAR", "word": argument.strip(), "version": version}
    if name.startswith("/"):
        return "Comando desconhecido. Digite /ajuda para ver os comandos."
    if len(normalize(action)) != 1:  # "ç" e "ã" contam como uma letra.
        return "Digite uma única letra, ou /chute seguido da palavra para tentar a palavra inteira."
    return {"type": "JOGAR", "letter": action, "version": version}


def run(name, servers, path, fresh=False):
    guard = lock(path)
    if guard is None:
        print(f"Já existe um cliente aberto com a sessão {path}. Use outro --name ou --session.")
        return
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    session = json.loads(previous) if previous and not fresh else {
        "token": secrets.token_urlsafe(32), "deployment": None, "pending": None}
    save(path, session)
    commands = queue.Queue()
    threading.Thread(target=read_keyboard, args=(commands,), daemon=True).start()
    state, me, last_screen, current_server = None, None, None, 0
    connected = False
    enter = session["deployment"] is None
    backlog = []  # Comandos para o servidor digitados enquanto outro ainda espera resposta.
    print("Conectando... Digite /ajuda para ver os comandos.")
    while True:
        # Comandos locais respondem na hora, mesmo sem conexão; os do servidor esperam a vez.
        while not commands.empty():
            action = commands.get()
            keyword = action.split(" ", 1)[0].lower()
            if not action:
                continue
            if keyword in {"/ajuda", "/help"}:
                print(HELP)
            elif keyword == "/estado" and not connected:
                print("Sem conexão com um servidor no momento. Tentando reconectar..."
                      + (" Último estado conhecido:" if state else ""))
                if state:
                    print(render(state, me))
            elif keyword == "/estado":
                last_screen = render(state, me)
                print(last_screen)
            else:
                parsed = parse(action, state)
                if isinstance(parsed, str):
                    print(parsed)  # Aviso local: comando desconhecido, /chute vazio etc.
                else:
                    backlog.append(action)
        if not session["pending"] and (enter or backlog):
            action = "/nova" if enter else backlog.pop(0)
            enter = False
            command = parse(action, state)  # Versão da sala atual, não a do momento em que foi digitado.
            session["pending"] = {
                **command, "request_id": str(uuid.uuid4()), "name": name,
                "token": session["token"], "deployment": session["deployment"]}
            save(path, session)  # O reenvio após uma queda mantém este identificador.
        command = session["pending"] or {"type": "ESTADO", "token": session["token"],
                                          "deployment": session["deployment"]}
        address = servers[current_server]
        try:
            response = exchange(address, command)
            if response.get("fatal"):
                print(response["message"])
                return
            if response.get("retry"):
                raise ConnectionError(response["message"])
        except (OSError, ValueError):
            if connected:
                print("Conexão perdida. Procurando outro servidor...")
            connected = False
            current_server = (current_server + 1) % len(servers)
            time.sleep(0.5)
            continue
        reconnected = not connected
        if reconnected:
            print(f"Conectado a {address} ({response.get('role', '')}).")
            connected = True
        session["deployment"] = response.get("deployment", session["deployment"])
        if session["pending"]:
            print(response.get("message", ""))
            kind = session["pending"]["type"]
            leaving = kind == "SAIR" and (response.get("ok") or response.get("code") == "SEM_SALA")
            session["pending"] = None
            save(path, session)
            if response.get("code") == "NOME_EM_USO":
                if fresh and previous:  # Devolve a sessão anterior deste nome, que ainda pode ser retomada.
                    path.write_text(previous, encoding="utf-8")
                elif fresh:
                    path.unlink()
                print("Abra o cliente com outro --name. Se o nome for seu, retome sem --nova-sessao.")
                return
            if leaving:
                return
        state, me = response.get("state"), response.get("player_id")
        if reconnected and command["type"] == "ESTADO" and state and state["status"] == "AGUARDANDO":
            enter = True  # Ao voltar, procura quem esteja esperando em outra sala.
        screen = render(state, me)
        if screen != last_screen:
            print(screen)
            last_screen = screen
        time.sleep(0.5)  # Atualiza os dois bonecos nos dois terminais.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--servers", default=os.getenv("CLIENT_SERVERS", "127.0.0.1:5000,127.0.0.1:5002"))
    parser.add_argument("--session", help="Arquivo individual de sessão deste jogador.")
    parser.add_argument("--nova-sessao", action="store_true")
    args = parser.parse_args()
    filename = "".join(c for c in args.name.casefold() if c.isalnum()) or "jogador"
    path = Path(args.session or f"sessions/{filename}.json")
    try:
        run(args.name, [s.strip() for s in args.servers.split(",")], path, args.nova_sessao)
    except KeyboardInterrupt:
        print("\nCliente fechado. A sessão foi guardada para reconexão.")


if __name__ == "__main__":
    main()

```

## forca/game.py
SHA-256: 2d8f6f4a494aa428dfd6bc88c86c70fcc4a7473ba5ec3792e88626c9f3921c0a
```
"""Regras de uma partida: independentes da rede e da replicação."""
from dataclasses import asdict, dataclass, field
import re
import unicodedata

FINISHED = {"ENCERRADA", "CANCELADA"}
MAX_ERRORS = 6
MAX_WORD = 30  # O estado inteiro é replicado a cada jogada; chutes longos não fazem sentido.


class GameError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize(text: str) -> str:
    """Maiúsculas sem acentos: 'ç' vira 'C' e 'CONEXÃO' vira 'CONEXAO'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def load_words(lines) -> list[str]:
    """Normaliza a lista de palavras e recusa, já na partida do servidor, o que não for só letras."""
    words = [normalize(line.strip()) for line in lines if line.strip()]
    invalid = [w for w in words if not re.fullmatch(rf"[A-Z]{{1,{MAX_WORD}}}", w)]
    if invalid:
        raise ValueError(f"use só letras, até {MAX_WORD} por palavra, sem espaços ou hífens: "
                         + ", ".join(invalid))
    if not words:
        raise ValueError("a lista está vazia.")
    return words


@dataclass
class Player:
    id: str
    name: str
    token_hash: str
    room_id: str | None = None
    active: bool = True  # Só jogadores ativos reservam o nome; /sair libera.


@dataclass
class Room:
    id: str
    players: list[str] = field(default_factory=list)
    word: str = ""
    guesses: list[str] = field(default_factory=list)
    wrong_words: list[str] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)
    turn: str | None = None
    status: str = "AGUARDANDO"
    version: int = 1
    winner: str | None = None
    reason: str | None = None

    def start(self, word: str):
        if len(self.players) != 2 or self.status != "AGUARDANDO":
            raise GameError("SALA_INVALIDA", "A sala precisa de dois jogadores para começar.")
        if not re.fullmatch(r"[A-Z]+", word):
            raise ValueError("A palavra deve conter apenas A a Z.")
        self.word = word
        self.errors = {p: 0 for p in self.players}
        self.turn = self.players[0]
        self.status = "EM_JOGO"

    def guess(self, player_id: str, letter, expected_version) -> bool:
        self.check_turn(player_id, expected_version)
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Z]", normalize(letter)):
            raise GameError("LETRA_INVALIDA", "Digite uma única letra de A a Z.")
        letter = normalize(letter)
        if letter in self.guesses:
            raise GameError("LETRA_REPETIDA", "Essa letra já foi tentada na sala.")
        self.guesses.append(letter)
        hit = letter in self.word
        self.conclude(player_id, hit, solved=set(self.word) <= set(self.guesses))
        return hit

    def guess_word(self, player_id: str, word, expected_version) -> bool:
        """Chute da palavra inteira: acerto vence; erro custa um membro e passa a vez."""
        self.check_turn(player_id, expected_version)
        if not isinstance(word, str) or not re.fullmatch(rf"[A-Z]{{1,{MAX_WORD}}}", normalize(word.strip())):
            raise GameError("PALAVRA_INVALIDA", f"Chute uma única palavra de até {MAX_WORD} letras, sem espaços.")
        word = normalize(word.strip())
        if word in self.wrong_words:
            raise GameError("PALAVRA_REPETIDA", "Essa palavra já foi chutada na sala.")
        hit = word == self.word
        if not hit:
            self.wrong_words.append(word)
        self.conclude(player_id, hit, solved=hit)
        return hit

    def check_turn(self, player_id: str, expected_version):
        if player_id not in self.players:
            raise GameError("NAO_PARTICIPANTE", "Você não participa desta sala.")
        if self.status != "EM_JOGO":
            raise GameError("PARTIDA_INDISPONIVEL", "A partida ainda não começou, está pausada ou terminou.")
        if self.turn != player_id:
            raise GameError("FORA_DA_VEZ", "Aguarde a sua vez.")
        if type(expected_version) is not int or expected_version != self.version:
            raise GameError("ESTADO_DESATUALIZADO", "A sala mudou. Confira o estado atual e tente novamente.")

    def conclude(self, player_id: str, hit: bool, solved: bool):
        if not hit:
            self.errors[player_id] += 1
        opponent = next(p for p in self.players if p != player_id)
        if solved:
            self.finish(player_id, "PALAVRA_COMPLETA")
        elif self.errors[player_id] >= MAX_ERRORS:
            self.finish(opponent, "SEIS_ERROS")
        else:
            self.turn = opponent
        self.version += 1

    def finish(self, winner: str | None, reason: str):
        self.status = "ENCERRADA" if winner else "CANCELADA"
        self.winner = winner
        self.reason = reason
        self.turn = None

    def public(self, players: dict[str, Player], online: set[str]) -> dict:
        return {
            "room_id": self.id, "room_version": self.version,
            "status": self.status,
            "players": [{"player_id": pid, "name": players[pid].name,
                         "errors": self.errors.get(pid, 0), "connected": pid in online}
                        for pid in self.players],
            "masked_word": "".join(c if c in self.guesses or self.status in FINISHED else "_"
                                   for c in self.word),
            "guesses": list(self.guesses), "wrong_words": list(self.wrong_words), "turn": self.turn,
            "winner": self.winner, "reason": self.reason, "max_errors": MAX_ERRORS,
        }


@dataclass
class World:
    deployment_id: str
    players: dict[str, Player] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)
    next_room: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(deployment_id=data["deployment_id"],
                   players={k: Player(**v) for k, v in data["players"].items()},
                   rooms={k: Room(**v) for k, v in data["rooms"].items()},
                   next_room=data["next_room"])


```

## forca/lobby.py
SHA-256: d6e905d8aa6bf534cb4d97bee8fce1faa8052e2cb5440c6b6de58d2a7df1432f
```
"""Salas e sessões. Não abre sockets: o servidor replica o resultado destas regras."""
import hashlib
import random
import uuid

from .game import FINISHED, GameError, Player, Room, World

NAME_HOLD = 180  # Segundos sem consultar até o nome de quem não está em partida poder ser reaproveitado.


def player_id(token):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise ValueError("Token de sessão inválido.")
    return hashlib.sha256(token.encode()).hexdigest()


def new_state():
    return {"world": World(str(uuid.uuid4())).to_dict(), "receipts": {}, "revision": 0}


def public_state(state, pid, online):
    world = World.from_dict(state["world"])
    player = world.players.get(pid)
    room = world.rooms.get(player.room_id) if player else None
    result = room.public(world.players, online) if room else None
    if result and room.status == "EM_JOGO" and not set(room.players) <= online:
        result["status"] = "PAUSADA"
    return result


def claim_name(world, pid, name, idle):
    """Recusa nome em uso. Quem sumiu há NAME_HOLD segundos e não está em partida perde o nome."""
    for other in world.players.values():
        if other.id == pid or not other.active or other.name.casefold() != name.casefold():
            continue
        room = world.rooms.get(other.room_id)
        if other.id not in idle or (room and room.status == "EM_JOGO"):
            raise GameError("NOME_EM_USO", f"O nome {name} já está em uso. Escolha outro nome.")
        if room and room.status == "AGUARDANDO":
            room.finish(None, "ABANDONO")
            room.version += 1
        other.room_id, other.active = None, False


def enter(world, player, online, words):
    """Coloca o jogador em uma sala e devolve a mensagem de resposta."""
    room = world.rooms.get(player.room_id)
    if room and room.status == "EM_JOGO":
        return f"Você já está em uma partida na {room.id}. Use /sair para desistir."
    waiting = room is not None and room.status == "AGUARDANDO"
    partner = next((r for r in world.rooms.values()
                    if r is not room and r.status == "AGUARDANDO" and len(r.players) == 1
                    and r.players[0] in online), None)
    if waiting and partner is None:
        return f"Você continua aguardando na {room.id}."
    if waiting:  # Dois jogadores esperando em salas separadas: junta os dois na sala do outro.
        room.finish(None, "REAGRUPADA")
        room.version += 1
    room = partner
    if room is None:
        room = Room(f"sala-{world.next_room}")
        world.next_room += 1
        world.rooms[room.id] = room
    room.players.append(player.id)
    room.errors[player.id] = 0
    player.room_id = room.id
    if len(room.players) == 2:
        room.start(random.choice(words))
    room.version += 1
    return f"Você está na {room.id}."


def apply(state, command, online, words, idle=frozenset()):
    """Modifica uma cópia do estado. Reenvios devolvem o resultado já registrado.

    online: jogadores que consultaram nos últimos segundos.
    idle: jogadores sem consultar há NAME_HOLD segundos, cujo nome pode ser liberado.
    """
    pid = player_id(command.get("token"))
    request_id = command.get("request_id")
    if not isinstance(request_id, str):
        raise ValueError("request_id deve ser um UUID em texto.")
    request_id = str(uuid.UUID(request_id))
    fingerprint = hashlib.sha256(str(sorted(command.items())).encode()).hexdigest()
    previous = state["receipts"].get(pid)
    if previous and previous["request_id"] == request_id:
        if previous["fingerprint"] != fingerprint:
            raise ValueError("Identificador reutilizado para outro comando.")
        return previous["result"]

    world = World.from_dict(state["world"])
    kind = command.get("type")
    try:
        if kind == "ENTRAR":
            name = command.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24 or not name.isprintable():
                raise GameError("NOME_INVALIDO", "Use um nome de 1 a 24 caracteres.")
            name = name.strip()
            player = world.players.get(pid)
            if player is None or not player.active:
                # Nomes são únicos entre jogadores ativos de todas as salas, sem diferenciar maiúsculas.
                claim_name(world, pid, name, idle)
                player = world.players.setdefault(pid, Player(pid, name, pid))
                player.name, player.active = name, True
            result = {"ok": True, "message": enter(world, player, online, words)}
        elif kind in {"JOGAR", "CHUTAR"}:
            player = world.players.get(pid)
            room = world.rooms.get(player.room_id) if player else None
            if room is None:
                raise GameError("SEM_SALA", "Entre em uma sala com /nova.")
            if not set(room.players) <= online:
                raise GameError("PAUSADA", "Aguardando o outro jogador reconectar.")
            if kind == "JOGAR":
                hit = room.guess(pid, command.get("letter"), command.get("version"))
                result = {"ok": True, "message": "Acertou!" if hit else "Errou!"}
            else:
                hit = room.guess_word(pid, command.get("word"), command.get("version"))
                result = {"ok": True, "message": "Acertou a palavra!" if hit
                          else "A palavra não coincide. Você perdeu um membro e a vez passou."}
        elif kind == "SAIR":
            player = world.players.get(pid)
            if player is None or not player.active:
                raise GameError("SEM_SALA", "Você não está em nenhuma sala.")
            room = world.rooms.get(player.room_id)
            if room and room.status not in FINISHED:
                opponent = next((p for p in room.players if p != pid), None)
                room.finish(opponent, "DESISTENCIA")
                room.version += 1
            player.room_id, player.active = None, False
            result = {"ok": True, "message": "Você saiu."}
        else:
            raise GameError("COMANDO_INVALIDO", "Comando desconhecido.")
    except GameError as exc:
        result = {"ok": False, "message": str(exc), "code": exc.code}
    state["world"] = world.to_dict()
    if pid in world.players:
        # O cliente tem um único comando pendente por vez: basta o último recibo de cada jogador.
        # Comandos de quem nunca entrou não mudam nada e não ocupam espaço no estado replicado.
        state["receipts"][pid] = {"request_id": request_id, "fingerprint": fingerprint, "result": result}
    state["revision"] += 1
    return result

```

## forca/ui.py
SHA-256: 8d1e6bd559a6704bc86db4670adaa542ef3f77ba79b8caf2fdc8c2c451d64878
```
"""Apresentação textual: os dois bonecos são desenhados em toda atualização."""

HELP = "\n".join([
    "Comandos:",
    "  <letra>            Tenta uma letra na sua vez",
    "  /chute <palavra>   Tenta adivinhar a palavra inteira na sua vez",
    "  /estado            Mostra a partida: forcas, palavra e letras tentadas",
    "  /nova              Entra em uma nova partida depois que a atual termina",
    "  /sair              Desiste da partida e fecha o cliente",
    "  /ajuda ou /help    Mostra esta lista",
    "  Ctrl+C             Fecha o cliente e guarda a sessão para retomar depois",
])


def gallows(errors):
    head = "O" if errors >= 1 else " "
    trunk = "|" if errors >= 2 else " "
    left = "/" if errors >= 3 else " "
    right = "\\" if errors >= 4 else " "
    leg_left = "/" if errors >= 5 else " "
    leg_right = "\\" if errors >= 6 else " "
    return ["  +-----+", "  |     |", f"  {head}     |", f" {left}{trunk}{right}    |",
            f" {leg_left} {leg_right}    |", "        |", "  ========"]


def outcome(state, player_id):
    """Resultado do ponto de vista de quem olha, sem os códigos internos do protocolo."""
    winner = state["winner"]
    if winner is None:
        return "Partida cancelada."
    names = {p["player_id"]: p["name"] for p in state["players"]}
    loser = next(pid for pid in names if pid != winner)
    if winner == player_id:
        details = {"PALAVRA_COMPLETA": "Você completou a palavra.",
                   "SEIS_ERROS": f"{names[loser]} chegou a seis erros.",
                   "DESISTENCIA": f"{names[loser]} desistiu."}
        return "Você venceu! " + details.get(state["reason"], "")
    details = {"PALAVRA_COMPLETA": f"{names[winner]} completou a palavra.",
               "SEIS_ERROS": "Você chegou a seis erros.",
               "DESISTENCIA": "Você desistiu."}
    return f"Você perdeu. {details.get(state['reason'], '')}"


def render(state, player_id):
    if not state:
        return "Você não está em nenhuma sala. Digite /nova para entrar em uma."
    players = state["players"]
    lines = ["=" * 68, f"FORCA | {state['room_id']} | {state['status']}", ""]
    labels = []
    drawings = []
    for p in players:
        labels.append(f"{p['name']}{' (você)' if p['player_id'] == player_id else ''}")
        drawings.append(gallows(p["errors"]))
    if len(players) == 1:
        labels.append("Aguardando adversário")
        drawings.append(gallows(0))
    lines.append(f"{labels[0]:<34}{labels[1]}")
    for left, right in zip(*drawings):
        lines.append(f"{left:<34}{right}")
    left_errors = players[0]["errors"]
    right_errors = players[1]["errors"] if len(players) == 2 else 0
    lines.extend([f"Erros: {left_errors}/6{' ' * 24}Erros: {right_errors}/6", ""])
    if state["masked_word"]:
        lines.append("Palavra: " + " ".join(state["masked_word"]))
    lines.append("Letras tentadas: " + (", ".join(state["guesses"]) or "nenhuma"))
    if state.get("wrong_words"):
        lines.append("Chutes errados: " + ", ".join(state["wrong_words"]))
    if state["status"] == "AGUARDANDO":
        lines.append("A partida começa quando o segundo jogador entrar.")
    elif state["status"] == "PAUSADA":
        absent = ", ".join(p["name"] for p in players if not p["connected"])
        lines.append(f"Partida pausada. Aguardando reconexão: {absent}.")
    elif state["status"] == "EM_JOGO":
        current = next(p["name"] for p in players if p["player_id"] == state["turn"])
        lines.append("Sua vez! Tente uma letra ou chute a palavra." if state["turn"] == player_id
                     else f"Vez de {current}. Aguarde.")
    else:
        lines.append(outcome(state, player_id))
        lines.append("Digite /nova para jogar novamente.")
    lines.append("=" * 68)
    return "\n".join(lines)


```

## forca/__init__.py
SHA-256: c6ab698060287c63c96e6a0b20a613a82dfa53f1e8a56e44033831958d4c0f6a
```
"""Jogo da forca distribuído por TCP: salas de dois jogadores e servidores primário e reserva com estado replicado em RAM."""

__version__ = "0.2.0"

```

## forca/words.txt
SHA-256: 087d5a483d710444d502b3fff5916ada8793f391479122206fbd611eb6223617
```
PYTHON
SOCKET
SERVIDOR
CLIENTE
REDE
PROCESSO
MEMORIA
SISTEMA
DOCKER
VIRTUAL
MENSAGEM
PACOTE
PROTOCOLO
CONEXAO
SEMAFORO
REPLICA
PARTIDA
JOGADOR
COMPUTADOR
ALGORITMO
```

## Dockerfile
SHA-256: 0fcda842a842f52fc5e79fb3874cd4a845d4626e82ed4f470825bc77c030155f
```
FROM python:3.12.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY forca ./forca
COPY servidor.py cliente.py ./
EXPOSE 5000 5001
CMD ["python", "servidor.py"]

```

## compose.yaml
SHA-256: e0b7724338aea8543aeb630a15030a73652f512f3d2f140f8525c7bc227a46a2
```
services:
  servidor:
    build: .
    environment:
      MODO: ${MODO:-primario}
      PRIMARY_HOST: ${PRIMARY_HOST:-127.0.0.1}
      REPLICATION_KEY: ${REPLICATION_KEY:-forca-aula}
    ports:
      - "5000:5000"
      - "5001:5001"
    # Um antigo primário não deve retornar automaticamente como ativo.
    restart: "no"

```

## .env.example
SHA-256: 311aba696fe5258455fecd81dc218b1f107e21429ecb22c01ca7eeadbd45cd1b
```
# VM 1: primario. VM 2: reserva.
MODO=primario
# Na VM 2, informe o IP Bridge da VM 1.
PRIMARY_HOST=XXX.XXX.X.XX
# Mesmo valor nos dois servidores; rede de aula confiável.
REPLICATION_KEY=forca-aula

```

## .dockerignore
SHA-256: 03e1c182b3e0377672aec9c64763de22e9a7216f2d14679cee26deafa7b37976
```
.git
.venv
__pycache__
**/__pycache__
*.pyc
data
sessions
tmp
output
.env

docs/
output/

```

## pyproject.toml
SHA-256: 17e50d0cd2ca11120c9666e8c3a834208abb1081a8e610dd42ea7336113c3f90
```
[project]
name = "forca-distribuida"
version = "0.2.0"
description = "Jogo da forca distribuído: salas de dois jogadores, sockets TCP e servidores primário e reserva"
requires-python = ">=3.12"
dependencies = []



```

## scripts/forca.ps1
SHA-256: 294661b9d88f665706f3d4bb38047cfc5972b6236a274ddb63f8b684949c2469
```
param(
    [Parameter(Position=0)]
    [ValidateSet('servidor', 'cliente', 'testes')]
    [string]$Modo = 'servidor',
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Opcoes
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = $env:FORCA_PYTHON
$pythonPrefix = @()
if (-not $pythonExecutable -and (Test-Path -LiteralPath (Join-Path $taskRoot '.venv/Scripts/python.exe'))) {
    $pythonExecutable = Join-Path $taskRoot '.venv/Scripts/python.exe'
}
if (-not $pythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $pythonExecutable = $pythonCommand.Source
    }
}
if (-not $pythonExecutable) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExecutable = 'py'
        $pythonPrefix = @('-3')
    } else {
        throw 'Instale Python 3.12+ ou configure FORCA_PYTHON com o caminho do executável.'
    }
}

Push-Location -LiteralPath $taskRoot
try {
    switch ($Modo) {
        'servidor' { & $pythonExecutable @pythonPrefix servidor.py @Opcoes }
        'cliente' { & $pythonExecutable @pythonPrefix cliente.py @Opcoes }
        'testes' { & $pythonExecutable @pythonPrefix -m unittest discover -s tests -v @Opcoes }
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}


```

## scripts/gerar_especificacao_pdf.py
SHA-256: 7ac6114f22093163de9e3387b42bc249c403c730e48d34556ccca230e0872d69
```
"""Gera o PDF da especificação Markdown com ReportLab."""
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted,
    KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'especificacao-jogo-forca.md'
OUTPUT = ROOT / 'output' / 'pdf' / 'especificacao-jogo-forca.pdf'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

fonts = Path('C:/Windows/Fonts')
for name, filename in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'),
                       ('Arial-Italic', 'ariali.ttf'), ('Arial-BoldItalic', 'arialbi.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold',
                              italic='Arial-Italic', boldItalic='Arial-BoldItalic')

styles = {
    'title': ParagraphStyle('Title', fontName='Arial-Bold', fontSize=23,
                            leading=28, textColor=colors.black, spaceAfter=12),
    'subtitle': ParagraphStyle('Subtitle', fontName='Arial', fontSize=12,
                               leading=17, spaceAfter=8),
    'meta': ParagraphStyle('Meta', fontName='Arial', fontSize=9,
                           leading=13, textColor=colors.HexColor('#555555'), spaceAfter=19),
    'h1': ParagraphStyle('H1', fontName='Arial-Bold', fontSize=15,
                         leading=19, spaceBefore=18, spaceAfter=9, keepWithNext=True),
    'h2': ParagraphStyle('H2', fontName='Arial-Bold', fontSize=11.7,
                         leading=16, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    'body': ParagraphStyle('Body', fontName='Arial', fontSize=10.2,
                           leading=14.3, spaceAfter=8, allowWidows=0, allowOrphans=0),
    'list': ParagraphStyle('List', fontName='Arial', fontSize=10.2,
                           leading=14.3, spaceAfter=6, leftIndent=15, firstLineIndent=0,
                           bulletIndent=0, allowWidows=0, allowOrphans=0),
    'cell': ParagraphStyle('Cell', fontName='Arial', fontSize=9.3,
                           leading=12.4, spaceAfter=0),
    'head': ParagraphStyle('Head', fontName='Arial-Bold', fontSize=9.3,
                           leading=12.4, textColor=colors.white),
    'code': ParagraphStyle('Code', fontName='Courier', fontSize=8.8,
                           leading=12, spaceBefore=5, spaceAfter=10),
}

def markup(text):
    out = escape(text)
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)
    out = re.sub(r'(https?://[^\s]+)',
                 lambda m: '<link href="' + m[1] + '" color="#244867">' + m[1] + '</link>', out)
    return out

WIDTH = A4[0] - 40*mm

def make_table(lines):
    raw = [[cell.strip() for cell in line.strip('|').split('|')] for line in lines]
    raw = [r for r in raw if not all(re.fullmatch(r'[:\- ]+', c) for c in r)]
    n = len(raw[0])
    if n == 2:
        first = max(len(row[0]) for row in raw)
        ratio = .38 if first > 25 else .30
        widths = [WIDTH*ratio, WIDTH*(1-ratio)]
    else:
        widths = [WIDTH*.10, WIDTH*.37, WIDTH*.53] if raw[0][0] == 'ID' else [WIDTH*.25, WIDTH*.29, WIDTH*.46]
    rows = [[Paragraph(markup(c), styles['head' if i == 0 else 'cell'])
             for c in row] for i, row in enumerate(raw)]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    commands = [('BACKGROUND', (0,0), (-1,0), colors.HexColor('#244867')),
                ('GRID', (0,0), (-1,-1), .45, colors.HexColor('#D9D9D9')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6)]
    for i in range(1, len(rows)):
        commands.append(('BACKGROUND', (0,i), (-1,i),
                         colors.HexColor('#F2F5F7') if i % 2 == 0 else colors.white))
    table.setStyle(TableStyle(commands))
    return table

def page_decor(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial', 8)
    canvas.setFillColor(colors.HexColor('#555555'))
    if doc.page > 1:
        canvas.drawString(20*mm, A4[1]-13*mm, 'Jogo da forca distribuído | Especificação técnica')
    canvas.drawString(20*mm, 12*mm, 'Sistemas Distribuídos | Versão 1.0')
    canvas.drawRightString(A4[0]-20*mm, 12*mm, str(doc.page))
    canvas.restoreState()

class SpecDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == 'H1':
            title = flowable.getPlainText()
            key = 'section-' + title.split(' ')[0]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, 0, False)

lines = SOURCE.read_text(encoding='utf-8').splitlines()
story = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    if not line:
        i += 1
        continue
    if line.startswith('```'):
        chunk = []
        i += 1
        while i < len(lines) and not lines[i].startswith('```'):
            chunk.append(lines[i])
            i += 1
        story.append(Preformatted('\n'.join(chunk), styles['code']))
    elif line.startswith('|'):
        block = []
        while i < len(lines) and lines[i].startswith('|'):
            block.append(lines[i])
            i += 1
        story.extend([make_table(block), Spacer(1, 9)])
        continue
    elif line.startswith('### '):
        story.append(Paragraph(markup(line[4:]), styles['h2']))
    elif line.startswith('## '):
        story.append(Paragraph(markup(line[3:]), styles['h1']))
    elif line.startswith('# '):
        story.append(Paragraph(markup(line[2:]), styles['title']))
    elif line.startswith('- '):
        story.append(Paragraph(markup(line[2:]), styles['list'], bulletText='•'))
    elif re.match(r'^\d+\. ', line):
        num, content = line.split('. ', 1)
        story.append(Paragraph(markup(content), styles['list'], bulletText=num+'.'))
    else:
        style = 'subtitle' if i == 2 else 'meta' if i == 4 else 'body'
        story.append(Paragraph(markup(line), styles[style]))
    i += 1

doc = SpecDoc(str(OUTPUT), pagesize=A4, rightMargin=20*mm,
              leftMargin=20*mm, topMargin=22*mm, bottomMargin=21*mm,
              title='Especificação do jogo da forca distribuído',
              author='Projeto de Sistemas Distribuídos',
              subject='Python, sockets, duas máquinas, VMs e Docker')
doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
print(OUTPUT)

```

## tests/test_game.py
SHA-256: f92ce61a97ef89b401240826680e693ea71e0f713f032be7dab2f9b986c8e5af
```
"""Regras de uma partida, sem rede."""
import unittest

from forca.game import GameError, Room, load_words, normalize


def started(word="SOCKET"):
    room = Room("sala-1", players=["ana", "bruno"])
    room.start(word)
    return room


class LetterTests(unittest.TestCase):
    def test_primeiro_a_entrar_comeca(self):
        self.assertEqual(started().turn, "ana")

    def test_fora_da_vez_nao_altera_a_sala(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess("bruno", "S", room.version)
        self.assertEqual(error.exception.code, "FORA_DA_VEZ")
        self.assertEqual((room.turn, room.guesses), ("ana", []))

    def test_versao_desatualizada(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess("ana", "S", room.version - 1)
        self.assertEqual(error.exception.code, "ESTADO_DESATUALIZADO")

    def test_letra_invalida_e_repetida_nao_passam_a_vez(self):
        room = started()
        for letter in ("", "AB", "1", "-", None):
            with self.assertRaises(GameError) as error:
                room.guess("ana", letter, room.version)
            self.assertEqual(error.exception.code, "LETRA_INVALIDA")
        room.guess("ana", "s", room.version)
        with self.assertRaises(GameError) as error:
            room.guess("bruno", "S", room.version)
        self.assertEqual(error.exception.code, "LETRA_REPETIDA")
        self.assertEqual(room.turn, "bruno")

    def test_letra_com_acento_vale_como_letra_sem_acento(self):
        room = started("CONEXAO")
        self.assertTrue(room.guess("ana", "ç", room.version))
        self.assertTrue(room.guess("bruno", "Ã", room.version))
        self.assertEqual(room.guesses, ["C", "A"])

    def test_erro_conta_so_para_o_autor_e_passa_a_vez(self):
        room = started()
        self.assertFalse(room.guess("ana", "Z", room.version))
        self.assertEqual(room.errors, {"ana": 1, "bruno": 0})
        self.assertEqual(room.turn, "bruno")

    def test_completar_a_palavra_vence(self):
        room = started("REDE")
        for player, letter in (("ana", "R"), ("bruno", "E"), ("ana", "D")):
            room.guess(player, letter, room.version)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "ana", "PALAVRA_COMPLETA"))

    def test_seis_erros_da_vitoria_ao_adversario(self):
        room = started()
        for ana, bruno in zip("ABDFGH", "IJLMNP"):
            room.guess("ana", ana, room.version)
            if room.status == "EM_JOGO":
                room.guess("bruno", bruno, room.version)
        self.assertEqual(room.errors["ana"], 6)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "bruno", "SEIS_ERROS"))


class WordGuessTests(unittest.TestCase):
    def test_chute_certo_vence_com_palavra_completa(self):
        room = started()
        self.assertTrue(room.guess_word("ana", " socket ", room.version))
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "ana", "PALAVRA_COMPLETA"))
        self.assertEqual(room.errors["ana"], 0)

    def test_chute_errado_custa_um_erro_e_passa_a_vez(self):
        room = started()
        version = room.version
        self.assertFalse(room.guess_word("ana", "SERVIDOR", version))
        self.assertEqual(room.errors, {"ana": 1, "bruno": 0})
        self.assertEqual((room.turn, room.status, room.version), ("bruno", "EM_JOGO", version + 1))
        self.assertEqual(room.wrong_words, ["SERVIDOR"])

    def test_chute_repetido_ou_invalido_nao_penaliza(self):
        room = started()
        room.guess_word("ana", "REDE", room.version)
        with self.assertRaises(GameError) as error:
            room.guess_word("bruno", "rede", room.version)
        self.assertEqual(error.exception.code, "PALAVRA_REPETIDA")
        for word in ("", "   ", "DUAS PALAVRAS", "GUARDA-CHUVA", "X" * 31, 42):
            with self.assertRaises(GameError) as error:
                room.guess_word("bruno", word, room.version)
            self.assertEqual(error.exception.code, "PALAVRA_INVALIDA")
        self.assertEqual((room.errors["bruno"], room.turn), (0, "bruno"))

    def test_chute_com_acento_acerta_palavra_sem_acento(self):
        room = started("CONEXAO")
        self.assertTrue(room.guess_word("ana", "conexão", room.version))
        self.assertEqual(room.reason, "PALAVRA_COMPLETA")

    def test_chute_fora_da_vez(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess_word("bruno", "SOCKET", room.version)
        self.assertEqual(error.exception.code, "FORA_DA_VEZ")

    def test_sexto_erro_em_chute_encerra(self):
        room = started()
        room.errors["ana"] = 5
        room.guess_word("ana", "REDE", room.version)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "bruno", "SEIS_ERROS"))

    def test_estado_publico_mostra_chutes_e_esconde_palavra(self):
        from forca.game import Player
        room = started()
        room.guess_word("ana", "REDE", room.version)
        players = {p: Player(p, p.title(), p) for p in room.players}
        public = room.public(players, {"ana", "bruno"})
        self.assertEqual(public["wrong_words"], ["REDE"])
        self.assertEqual(public["masked_word"], "______")


class WordListTests(unittest.TestCase):
    def test_normaliza_acentos_e_maiusculas(self):
        self.assertEqual(normalize("Coração"), "CORACAO")
        self.assertEqual(load_words(["  socket ", "", "coração", "Conexão"]), ["SOCKET", "CORACAO", "CONEXAO"])

    def test_recusa_palavras_que_nao_sao_so_letras(self):
        for lines in (["BOA NOITE"], ["GUARDA-CHUVA"], ["SALA1"], ["X" * 31], [], ["", "  "]):
            with self.assertRaises(ValueError):
                load_words(lines)

    def test_lista_do_projeto_e_valida(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "forca" / "words.txt"
        self.assertTrue(load_words(path.read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()

```

## tests/test_lobby.py
SHA-256: 97816530f322eaf32b765e485c0553b30776c2eb7759cd47e68b90cab4372b0d
```
"""Salas, sessões, nomes únicos e reenvios."""
import unittest
import uuid

from forca.lobby import apply, new_state, player_id, public_state

WORDS = ["SOCKET"]


def token(name):
    return (name + "-token-").ljust(40, "x")


class Lobby:
    """Estado de um servidor sem rede; todos os jogadores criados estão online."""

    def __init__(self):
        self.state = new_state()
        self.online = set()
        self.idle = set()

    def send(self, who, kind, request_id=None, **fields):
        self.online.add(player_id(token(who)))
        command = {"type": kind, "token": token(who),
                   "request_id": request_id or str(uuid.uuid4()), **fields}
        return apply(self.state, command, self.online, WORDS, self.idle)

    def enter(self, who, display=None):
        return self.send(who, "ENTRAR", name=who if display is None else display)

    def view(self, who):
        return public_state(self.state, player_id(token(who)), self.online)


class RoomTests(unittest.TestCase):
    def test_salas_sao_formadas_em_ordem(self):
        lobby = Lobby()
        messages = [lobby.enter(n)["message"] for n in ("Ana", "Bruno", "Caio", "Dani", "Edu")]
        self.assertEqual(messages, ["Você está na sala-1.", "Você está na sala-1.", "Você está na sala-2.",
                                    "Você está na sala-2.", "Você está na sala-3."])
        self.assertEqual(lobby.view("Ana")["status"], "EM_JOGO")
        self.assertEqual(lobby.view("Edu")["status"], "AGUARDANDO")
        self.assertEqual(len(lobby.view("Caio")["players"]), 2)

    def test_entrar_de_novo_mantem_a_sala(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        self.assertEqual(lobby.enter("Ana")["message"], "Você já está em uma partida na sala-1. Use /sair para desistir.")
        self.assertEqual(lobby.view("Ana")["room_version"], lobby.view("Bruno")["room_version"])

    def test_quem_espera_sozinho_continua_na_sala(self):
        lobby = Lobby()
        lobby.enter("Ana")
        self.assertEqual(lobby.enter("Ana")["message"], "Você continua aguardando na sala-1.")

    def test_dois_esperando_em_salas_separadas_se_juntam(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.online.discard(player_id(token("Ana")))  # Ana cai; Bruno não a encontra e abre outra sala.
        self.assertEqual(lobby.enter("Bruno")["message"], "Você está na sala-2.")
        self.assertEqual(lobby.enter("Ana")["message"], "Você está na sala-2.")  # Ana volta e se junta.
        view = lobby.view("Ana")
        self.assertEqual((view["room_id"], view["status"]), ("sala-2", "EM_JOGO"))
        self.assertEqual(lobby.state["world"]["rooms"]["sala-1"]["status"], "CANCELADA")

    def test_jogador_ausente_pausa_a_partida(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        lobby.online.discard(player_id(token("Bruno")))
        self.assertEqual(lobby.view("Ana")["status"], "PAUSADA")
        state = lobby.view("Ana")
        result = lobby.send("Ana", "JOGAR", letter="S", version=state["room_version"])
        self.assertEqual(result["code"], "PAUSADA")

    def test_sair_na_espera_cancela_e_na_partida_da_vitoria(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.send("Ana", "SAIR")
        lobby.enter("Bruno")
        lobby.enter("Caio")
        lobby.send("Bruno", "SAIR")
        self.assertIsNone(lobby.view("Ana"))
        view = lobby.view("Caio")
        self.assertEqual((view["status"], view["reason"]), ("ENCERRADA", "DESISTENCIA"))
        self.assertEqual(view["winner"], player_id(token("Caio")))
        self.assertEqual(view["masked_word"], "SOCKET")

    def test_chutar_pelo_lobby(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        version = lobby.view("Ana")["room_version"]
        wrong = lobby.send("Ana", "CHUTAR", word="REDE", version=version)
        self.assertTrue(wrong["ok"])
        self.assertIn("não coincide", wrong["message"])
        right = lobby.send("Bruno", "CHUTAR", word="socket", version=version + 1)
        self.assertEqual(right["message"], "Acertou a palavra!")
        view = lobby.view("Ana")
        self.assertEqual((view["status"], view["reason"]), ("ENCERRADA", "PALAVRA_COMPLETA"))
        self.assertEqual([p["errors"] for p in view["players"]], [1, 0])


class UniqueNameTests(unittest.TestCase):
    def test_nome_repetido_e_recusado_em_qualquer_sala(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        self.assertEqual(lobby.enter("ana2", "ana")["code"], "NOME_EM_USO")
        lobby.enter("Bruno")  # Sala 1 começa; a regra continua valendo para a sala 2.
        self.assertEqual(lobby.enter("ana3", "  ANA ")["code"], "NOME_EM_USO")
        self.assertIsNone(lobby.view("ana2"))
        self.assertEqual(len(lobby.view("ana1")["players"]), 2)

    def test_mesmo_jogador_pode_reentrar_com_seu_nome(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        self.assertTrue(lobby.enter("ana1", "Ana")["ok"])

    def test_sair_libera_o_nome(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.send("ana1", "SAIR")
        self.assertTrue(lobby.enter("ana2", "Ana")["ok"])
        self.assertEqual(lobby.enter("ana1", "Ana")["code"], "NOME_EM_USO")

    def test_nome_de_quem_sumiu_fora_de_partida_e_liberado(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.online.discard(player_id(token("ana1")))
        lobby.idle.add(player_id(token("ana1")))
        self.assertEqual(lobby.enter("ana2", "Ana")["message"], "Você está na sala-2.")
        self.assertIsNone(lobby.view("ana1"))
        self.assertEqual(lobby.state["world"]["rooms"]["sala-1"]["status"], "CANCELADA")
        self.assertEqual(lobby.enter("ana1", "Ana")["code"], "NOME_EM_USO")

    def test_nome_de_quem_esta_em_partida_nao_e_liberado(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.enter("Bruno")
        lobby.idle.add(player_id(token("ana1")))
        self.assertEqual(lobby.enter("ana2", "Ana")["code"], "NOME_EM_USO")

    def test_nome_invalido(self):
        lobby = Lobby()
        for name in ("", "   ", "x" * 25, "Ana\n"):
            self.assertEqual(lobby.enter("p", name)["code"], "NOME_INVALIDO")


class ResendTests(unittest.TestCase):
    def test_reenvio_devolve_o_mesmo_resultado_sem_repetir(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        version = lobby.view("Ana")["room_version"]
        request_id = str(uuid.uuid4())
        first = lobby.send("Ana", "JOGAR", request_id, letter="Z", version=version)
        again = lobby.send("Ana", "JOGAR", request_id, letter="Z", version=version)
        self.assertEqual(first, again)
        self.assertEqual(lobby.view("Ana")["players"][0]["errors"], 1)
        self.assertEqual(lobby.view("Ana")["room_version"], version + 1)

    def test_mesmo_identificador_com_outro_conteudo(self):
        lobby = Lobby()
        request_id = str(uuid.uuid4())
        lobby.send("Ana", "ENTRAR", request_id, name="Ana")
        with self.assertRaises(ValueError):
            lobby.send("Ana", "ENTRAR", request_id, name="Outra")

    def test_token_e_identificador_invalidos(self):
        with self.assertRaises(ValueError):
            player_id("curto")
        for request_id in ("nao-e-uuid", 5, ["lista"]):
            with self.assertRaises(ValueError):
                Lobby().send("Ana", "ENTRAR", request_id, name="Ana")

    def test_recibos_nao_crescem_com_comandos_rejeitados(self):
        lobby = Lobby()
        lobby.enter("Ana")
        for i in range(200):
            lobby.send("Ana", "JOGAR", letter="1", version=0)
            lobby.send(f"intruso{i}", "JOGAR", letter="A", version=0)  # Nunca entrou: nada a guardar.
        self.assertEqual(len(lobby.state["receipts"]), 1)
        self.assertEqual(lobby.state["revision"], 401)


if __name__ == "__main__":
    unittest.main()

```

## tests/test_cliente.py
SHA-256: 32e913cfdc1ae6a8f73fdb9e64de796f0b1f936c6eddedcabc37d70b7a358ef8
```
"""Enquadramento das mensagens, tela e comandos do cliente."""
import io
from pathlib import Path
import tempfile
import unittest

from cliente import lock, parse
from forca.ui import HELP, outcome, render
from forca.wire import MAX_BYTES, receive, send

STATE = {"room_id": "sala-1", "room_version": 3, "status": "EM_JOGO",
         "players": [{"player_id": "a", "name": "Ana", "errors": 1, "connected": True},
                     {"player_id": "b", "name": "Bruno", "errors": 0, "connected": True}],
         "masked_word": "S____T", "guesses": ["S", "T", "Z"], "wrong_words": ["REDE"],
         "turn": "a", "winner": None, "reason": None, "max_errors": 6}


class WireTests(unittest.TestCase):
    def test_ida_e_volta(self):
        stream = io.BytesIO()
        send(stream, {"type": "PING", "texto": "ação"})
        send(stream, {"type": "ESTADO"})
        stream.seek(0)
        self.assertEqual(receive(stream), {"type": "PING", "texto": "ação"})
        self.assertEqual(receive(stream), {"type": "ESTADO"})
        with self.assertRaises(ConnectionError):
            receive(stream)

    def test_mensagens_invalidas(self):
        for data in (b'{"sem": "quebra"}', b"[1, 2]\n", b"nao e json\n", b"x" * (MAX_BYTES + 2) + b"\n"):
            with self.assertRaises(ValueError):
                receive(io.BytesIO(data))


class ScreenTests(unittest.TestCase):
    def test_estado_nao_lista_comandos(self):
        screen = render(STATE, "a")
        for expected in ("sala-1", "Ana (você)", "Bruno", "S _ _ _ _ T", "S, T, Z", "Chutes errados: REDE",
                         "Erros: 1/6", "Sua vez!"):
            self.assertIn(expected, screen)
        for command in ("/ajuda", "/help", "/estado", "/sair"):
            self.assertNotIn(command, screen)

    def test_sem_sala(self):
        self.assertIn("não está em nenhuma sala", render(None, "a"))

    def test_resultado_do_ponto_de_vista_de_cada_jogador(self):
        def ended(winner, reason):
            return {**STATE, "status": "ENCERRADA", "turn": None, "winner": winner, "reason": reason}
        cases = [("a", "PALAVRA_COMPLETA", "a", "Você venceu! Você completou a palavra."),
                 ("a", "PALAVRA_COMPLETA", "b", "Você perdeu. Ana completou a palavra."),
                 ("b", "SEIS_ERROS", "b", "Você venceu! Ana chegou a seis erros."),
                 ("b", "SEIS_ERROS", "a", "Você perdeu. Você chegou a seis erros."),
                 ("a", "DESISTENCIA", "a", "Você venceu! Bruno desistiu.")]
        for winner, reason, viewer, expected in cases:
            self.assertEqual(outcome(ended(winner, reason), viewer), expected)
            self.assertNotIn(reason, render(ended(winner, reason), viewer))
        self.assertEqual(outcome({**STATE, "winner": None, "reason": "DESISTENCIA"}, "a"), "Partida cancelada.")

    def test_ajuda_lista_apenas_comandos(self):
        for command in ("/chute", "/estado", "/nova", "/sair", "/ajuda", "/help"):
            self.assertIn(command, HELP)
        self.assertNotIn("sala-1", HELP)
        self.assertNotIn("+-----+", HELP)


class ParseTests(unittest.TestCase):
    def test_comandos(self):
        self.assertEqual(parse("a", STATE), {"type": "JOGAR", "letter": "a", "version": 3})
        self.assertEqual(parse("ç", STATE), {"type": "JOGAR", "letter": "ç", "version": 3})
        self.assertEqual(parse("/chute socket", STATE), {"type": "CHUTAR", "word": "socket", "version": 3})
        self.assertEqual(parse("/CHUTE  rede ", STATE), {"type": "CHUTAR", "word": "rede", "version": 3})
        self.assertEqual(parse("/nova", None), {"type": "ENTRAR"})
        self.assertEqual(parse("/sair", STATE), {"type": "SAIR"})

    def test_avisos_locais(self):
        for action in ("/chute", "/chute   ", "/xyz", "ab"):
            self.assertIsInstance(parse(action, STATE), str)


class SessionLockTests(unittest.TestCase):
    def test_segundo_cliente_com_a_mesma_sessao_e_recusado(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ana.json"
            first = lock(path)
            self.assertIsNotNone(first)
            self.assertIsNone(lock(path))
            first.close()
            second = lock(path)
            self.assertIsNotNone(second)
            second.close()


if __name__ == "__main__":
    unittest.main()

```

## tests/test_servidor.py
SHA-256: ce0091cc489ec669dbced00841e3e0378b317d7787dab96325530539b0e98cc0
```
"""Primário e reserva em processos reais, com TCP, replicação e queda abrupta."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid

from forca.lobby import new_state
from forca.wire import receive, send

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def exchange(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.settimeout(5)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


def token(name):
    return (name + "-token-").ljust(40, "x")


def command(who, kind, request_id=None, **fields):
    return {"type": kind, "token": token(who), "request_id": request_id or str(uuid.uuid4()), **fields}


def wait_for(check, seconds=15):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        try:
            result = check()
            if result:
                return result
        except OSError:
            pass
        time.sleep(0.2)
    raise AssertionError("Condição não atingida a tempo.")


class Processes(unittest.TestCase):
    """Sobe servidor.py em subprocessos e encerra todos ao fim de cada teste."""

    def setUp(self):
        self.processes = []

    def start(self, *arguments):
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen([sys.executable, "servidor.py", *arguments], cwd=ROOT, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process

    def stop(self, process):
        process.kill()
        output = process.communicate(timeout=10)[0]
        return output.decode("utf-8", "replace")

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                self.stop(process)
            else:
                process.communicate()


class ReplicationTests(Processes):
    def setUp(self):
        super().setUp()
        self.game, self.sync, self.backup_game = free_port(), free_port(), free_port()
        self.primary = self.start("--port", str(self.game), "--sync-port", str(self.sync))
        wait_for(lambda: exchange(self.game, {"type": "PING"}))
        # Sem reserva sincronizado, nenhuma alteração é aceita.
        self.assertTrue(exchange(self.game, command("Ana", "ENTRAR", name="Ana")).get("retry"))
        self.backup = self.start("--modo", "reserva", "--port", str(self.backup_game),
                                 "--sync-port", str(self.sync))
        # ESTADO recebe retry até o reserva sincronizar.
        wait_for(lambda: "retry" not in exchange(self.game, {"type": "ESTADO", "token": token("x")}))

    def test_reserva_assume_com_a_partida_intacta(self):
        exchange(self.game, command("Ana", "ENTRAR", name="Ana"))
        state = exchange(self.game, command("Bruno", "ENTRAR", name="Bruno"))["state"]
        request_id = str(uuid.uuid4())
        first = exchange(self.game, command("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"]))
        self.assertTrue(first["ok"])
        exchange(self.game, command("Bruno", "ESTADO"))
        before = exchange(self.game, command("Ana", "ESTADO"))["state"]

        self.stop(self.primary)
        wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))
        exchange(self.backup_game, command("Bruno", "ESTADO"))
        after = exchange(self.backup_game, command("Ana", "ESTADO"))
        self.assertEqual(after["role"], "RESERVA_PROMOVIDO")
        self.assertEqual(after["state"], before)

        # O reenvio da jogada já confirmada não é aplicado de novo no reserva.
        again = exchange(self.backup_game, command("Ana", "JOGAR", request_id, letter="Z",
                                                   version=state["room_version"]))
        self.assertEqual(again["message"], first["message"])
        self.assertEqual(again["state"]["room_version"], before["room_version"])

        guess = exchange(self.backup_game, command("Bruno", "CHUTAR", word="XYZ", version=before["room_version"]))
        self.assertTrue(guess["ok"])
        self.assertEqual(guess["state"]["wrong_words"], ["XYZ"])

    def test_nome_unico_vale_entre_os_servidores(self):
        exchange(self.game, command("ana1", "ENTRAR", name="Ana"))
        self.stop(self.primary)
        wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))
        refused = exchange(self.backup_game, command("ana2", "ENTRAR", name="ANA"))
        self.assertEqual(refused["code"], "NOME_EM_USO")

    def test_primario_pausa_ao_perder_o_reserva(self):
        self.stop(self.backup)
        wait_for(lambda: "retry" in exchange(self.game, command("Ana", "ENTRAR", name="Ana")))
        invalid = socket.create_connection(("127.0.0.1", self.game), timeout=2)
        with invalid, invalid.makefile("rwb") as stream:
            stream.write(b"isto nao e json\n")
            stream.flush()
            self.assertFalse(receive(stream)["ok"])
        log = self.stop(self.primary)
        self.assertIn("primário pausado", log.lower())  # Por ACK ou heartbeat.
        self.assertNotIn("Traceback", log)


    def test_comando_malformado_recebe_resposta_sem_traceback(self):
        response = exchange(self.game, {"type": "JOGAR", "token": token("Ana"), "request_id": 5})
        self.assertFalse(response["ok"])
        self.assertIn("Comando inválido", response["message"])
        self.assertNotIn("Traceback", self.stop(self.primary))


class InitialSyncTests(Processes):
    def setUp(self):
        super().setUp()
        self.game, self.sync, self.backup_game = free_port(), free_port(), free_port()

    def ready(self):
        return "retry" not in exchange(self.game, {"type": "ESTADO", "token": token("x")})

    def test_chave_com_acento_e_reserva_que_some_nao_travam_o_primario(self):
        primary = self.start("--port", str(self.game), "--sync-port", str(self.sync))
        wait_for(lambda: exchange(self.game, {"type": "PING"}))
        with socket.create_connection(("127.0.0.1", self.sync), timeout=2) as intruder:
            with intruder.makefile("rwb") as stream:
                send(stream, {"key": "ç"})
                self.assertEqual(stream.readline(), b"")  # Recusado: conexão fechada.
        with socket.create_connection(("127.0.0.1", self.sync), timeout=2) as vanishing:
            with vanishing.makefile("rwb") as stream:
                send(stream, {"key": "forca-aula"})
                self.assertIn("state", receive(stream))  # Recebe a cópia e some sem ACK.
        self.start("--modo", "reserva", "--port", str(self.backup_game), "--sync-port", str(self.sync))
        wait_for(self.ready)
        log = self.stop(primary)
        self.assertIn("Sincronização inicial com o reserva falhou", log)
        self.assertNotIn("pausado", log.lower())
        self.assertNotIn("Traceback", log)

    def test_reserva_so_assume_apos_a_segunda_mensagem(self):
        listener = socket.create_server(("127.0.0.1", self.sync))
        self.addCleanup(listener.close)
        listener.settimeout(15)

        def fake_primary(heartbeat):
            connection, _ = listener.accept()
            with connection, connection.makefile("rwb") as stream:
                receive(stream)
                send(stream, {"state": new_state()})
                receive(stream)
                if heartbeat:
                    send(stream, {"heartbeat": True})
                    receive(stream)

        backup = self.start("--modo", "reserva", "--port", str(self.backup_game),
                            "--sync-port", str(self.sync))
        fake_primary(heartbeat=False)  # Só a cópia inicial: o ACK pode não ter chegado ao primário.
        time.sleep(1.5)
        with self.assertRaises(OSError):
            exchange(self.backup_game, {"type": "PING"})
        thread = threading.Thread(target=fake_primary, args=(True,))
        thread.start()  # O reserva tenta de novo; agora recebe a segunda mensagem.
        thread.join(15)
        self.assertEqual(wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))["role"],
                         "RESERVA_PROMOVIDO")
        self.assertNotIn("Traceback", self.stop(backup))


if __name__ == "__main__":
    unittest.main()

```

## .gitignore
SHA-256: bcd4062ef0912639f38b2ae0a4f0ce6858bfc9784ec5e42092df251e9e9f1900
```
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[codz]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
#   Usually these files are written by a python script from a template
#   before PyInstaller builds the exe, so as to inject date/other infos into it.
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py.cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
#   For a library or package, you might want to ignore these files since the code is
#   intended to run in multiple environments; otherwise, check them in:
# .python-version

# pipenv
#   According to pypa/pipenv#598, it is recommended to include Pipfile.lock in version control.
#   However, in case of collaboration, if having platform-specific dependencies or dependencies
#   having no cross-platform support, pipenv may install dependencies that don't work, or not
#   install all needed dependencies.
# Pipfile.lock

# UV
#   Similar to Pipfile.lock, it is generally recommended to include uv.lock in version control.
#   This is especially recommended for binary packages to ensure reproducibility, and is more
#   commonly ignored for libraries.
# uv.lock

# poetry
#   Similar to Pipfile.lock, it is generally recommended to include poetry.lock in version control.
#   This is especially recommended for binary packages to ensure reproducibility, and is more
#   commonly ignored for libraries.
#   https://python-poetry.org/docs/basic-usage/#commit-your-poetrylock-file-to-version-control
# poetry.lock
# poetry.toml

# pdm
#   Similar to Pipfile.lock, it is generally recommended to include pdm.lock in version control.
#   pdm recommends including project-wide configuration in pdm.toml, but excluding .pdm-python.
#   https://pdm-project.org/en/latest/usage/project/#working-with-version-control
# pdm.lock
# pdm.toml
.pdm-python
.pdm-build/

# pixi
#   Similar to Pipfile.lock, it is generally recommended to include pixi.lock in version control.
# pixi.lock
#   Pixi creates a virtual environment in the .pixi directory, just like venv module creates one
#   in the .venv directory. It is recommended not to include this directory in version control.
.pixi

# PEP 582; used by e.g. github.com/David-OConnor/pyflow and github.com/pdm-project/pdm
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# Redis
*.rdb
*.aof
*.pid

# RabbitMQ
mnesia/
rabbitmq/
rabbitmq-data/

# ActiveMQ
activemq-data/

# SageMath parsed files
*.sage.py

# Environments
.env
.envrc
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# PyCharm
#   JetBrains specific template is maintained in a separate JetBrains.gitignore that can
#   be found at https://github.com/github/gitignore/blob/main/Global/JetBrains.gitignore
#   and can be added to the global gitignore or merged into this file.  For a more nuclear
#   option (not recommended) you can uncomment the following to ignore the entire idea folder.
# .idea/

# Abstra
#   Abstra is an AI-powered process automation framework.
#   Ignore directories containing user credentials, local state, and settings.
#   Learn more at https://abstra.io/docs
.abstra/

# Visual Studio Code
#   Visual Studio Code specific template is maintained in a separate VisualStudioCode.gitignore 
#   that can be found at https://github.com/github/gitignore/blob/main/Global/VisualStudioCode.gitignore
#   and can be added to the global gitignore or merged into this file. However, if you prefer, 
#   you could uncomment the following to ignore the entire vscode folder
# .vscode/
# Temporary file for partial code execution
tempCodeRunnerFile.py

# Ruff stuff:
.ruff_cache/

# PyPI configuration file
.pypirc

# Marimo
marimo/_static/
marimo/_lsp/
__marimo__/

# Streamlit
.streamlit/secrets.toml

sessions/

output/
```
