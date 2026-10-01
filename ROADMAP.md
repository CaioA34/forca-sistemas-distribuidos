# Roadmap — Jogo da Forca Distribuído

Referências: [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [especificação](docs/especificacao-jogo-forca.md) e [protocolo](docs/protocolo-etapa-1.md).

A arquitetura adotada é **dois nós com papéis dinâmicos, estado em RAM e replicação síncrona**, jogados pelo navegador através de um gateway HTTP sem estado na instância Oracle. Os nós e o gateway se encontram pelo Tailscale, com nomes fixos, porque a rede da faculdade é restrita e os IPs mudam a cada rede. Só a biblioteca padrão do Python é usada.

Legenda: `[x]` feito, `[ ]` pendente.

## 1. Regras e jogo local

- [x] Regras da forca separadas da rede e da interface (`forca/game.py`).
- [x] Turno alternado a cada tentativa válida; letra repetida, inválida ou fora da vez é rejeitada sem mudar turno ou erros.
- [x] Seis erros por jogador; vitória ao completar a palavra, derrota ao atingir seis erros.
- [x] Chute da palavra inteira (`/chute`): acerto vence com `PALAVRA_COMPLETA`; erro custa um membro e passa a vez.
- [x] Terminal com palavra parcial, letras tentadas, chutes errados, turno e os dois bonecos lado a lado (`forca/ui.py`).
- [x] `/estado` mostra só o estado; `/ajuda` (ou `/help`) mostra só os comandos.

**Concluído quando:** uma partida completa funciona e tentativas fora da vez são rejeitadas. ✔

## 2. Comunicação por sockets

- [x] Mensagens JSON delimitadas por linha, com limite de tamanho (`forca/wire.py`).
- [x] Uma conexão TCP curta por comando; o cliente consulta o estado a cada 0,5 s.
- [x] Mensagem inválida gera erro controlado sem derrubar o servidor.

**Concluído quando:** dois terminais jogam a mesma partida e mostram o mesmo estado. ✔

## 3. Salas e concorrência

- [x] Distribuição automática: A espera, B inicia a sala 1; C cria a sala 2 e espera; D joga com C.
- [x] No máximo dois jogadores por sala; salas independentes.
- [x] Trava única (`threading.Lock`) protegendo validação, aplicação e replicação; limite de 64 conexões simultâneas (`BoundedSemaphore`).
- [x] Versão da sala (`room_version`) para rejeitar jogadas baseadas em estado antigo.

**Concluído quando:** várias partidas funcionam ao mesmo tempo sem interferência. ✔

## 4. Sessões e reenvio

- [x] Token gerado e salvo pelo cliente antes da primeira requisição; `player_id` = SHA-256 do token.
- [x] Nomes únicos entre jogadores ativos de todas as salas (`NOME_EM_USO`); `/sair` libera o nome.
- [x] Trava do arquivo de sessão: dois clientes com o mesmo nome no mesmo computador não compartilham o token.
- [x] `request_id` por comando, com recibo e impressão digital para reconhecer reenvios.
- [x] Comando pendente salvo em disco no cliente e reenviado após queda.
- [x] `deployment_id` impede retomar a sessão em outra execução dos servidores.
- [x] Partida pausada enquanto um jogador está desconectado; `/sair` dá a vitória ao adversário.

**Concluído quando:** reenviar uma jogada não duplica seu efeito e o jogador volta à mesma sala. ✔

## 5. Replicação e recuperação

- [x] Primário replica o estado completo e espera ACK antes de responder.
- [x] Heartbeat a cada 0,5 s no canal de replicação (porta 5001), autenticado por chave compartilhada.
- [x] Primário pausa ao perder o reserva; não confirma nada sem a segunda cópia.
- [x] Reserva se promove ao perder o primário e passa a atender na porta de jogadores.
- [x] Clientes alternam entre os endereços configurados e retomam a sessão.
- [x] Tratar a exceção do fechamento do canal de replicação em `Server.synchronize` (a thread terminava com traceback quando o reserva caía).
- [x] Papéis dinâmicos: um nó que volta entra como reserva de quem atende; primário pausado cede ao outro que assumiu ou volta a atender quando o reserva reinicia (`epoch` conta as promoções).
- [x] Nenhum nó cria um jogo sozinho: com os dois entrando, o de nome menor cria.
- [ ] (Opcional) Terceiro nó árbitro para cobrir falha dupla.

**Concluído quando:** encerrar o primário durante duas partidas permite que ambas continuem no reserva, preservando turno, erros, letras e jogadores aguardando. ✔ em teste automatizado com processos locais (`tests/test_servidor.py`).

## 6. Docker e VMs

- [x] `Dockerfile` (Python 3.12.13 slim), `compose.yaml`, `.dockerignore` e `.env.example`.
- [x] Configuração por `NODE_NAME`, `PEER`, `REPLICATION_KEY` e `TS_AUTHKEY`; `.env` fora do Git e da imagem.
- [x] Container `tailscale` em cada VM (nomes fixos, sem IP nem bridge) e `restart: unless-stopped`, seguro com papéis dinâmicos.
- [x] Gateway em container para a Oracle (`deploy/oracle/`) e site do Nginx.
- [x] `scripts/preparar-vm.sh`: instala Docker, cria o `.env` e sobe o nó.
- [x] Container executado com usuário sem privilégios.
- [ ] Criar a tag, a regra de acesso e a chave no Tailscale (ver `docs/implantacao.md`).
- [ ] Subir as duas VMs e o gateway; confirmar que `forca-a`/`forca-b` resolvem dentro do container (plano B: IPs `100.x`).
- [ ] Publicar `forca.ambrosias.dev` no Nginx da Oracle.

**Concluído quando:** jogadores em qualquer rede abrem `forca.ambrosias.dev`, jogam, e os dois nós sincronizam pelo Tailscale.

## 7. Robustez e experiência de jogo

- [x] Chave de replicação comparada em bytes: acento na chave (ou uma chave inválida enviada por outro) não derruba mais o canal de sincronização.
- [x] Recibos limitados ao último comando de cada jogador: o estado replicado não cresce com a quantidade de jogadas nem com comandos rejeitados.
- [x] Sincronização inicial segura: o reserva só assume após a segunda mensagem, e o primário não se pausa se a cópia inicial falhar.
- [x] `words.txt` normalizado e validado ao iniciar o servidor.
- [x] Comandos malformados recebem resposta controlada; erros inesperados vão para o log sem derrubar o atendimento.
- [x] Jogadores esperando em salas separadas são reagrupados ao reconectar.
- [x] Nome de quem sumiu há 180 s e não está em partida pode ser reaproveitado.
- [x] Resultado mostrado do ponto de vista de cada jogador ("Você venceu!"/"Você perdeu."); `/nova` durante a partida explica que ela está em andamento.
- [x] Acentos aceitos em letras e chutes (`ç` → `C`, `conexão` → `CONEXAO`).
- [x] `/estado` e `/ajuda` respondem mesmo sem conexão; `/estado` avisa quando não há servidor.

- [x] Coleta do estado: partidas encerradas e jogadores que saíram são apagados; `ESTADO_CHEIO` recusa o comando em vez de pausar o nó.
- [x] Espera pela trava limitada a 2 s: uma requisição atrasada não é aplicada depois do comando seguinte.
- [x] Página web com teclado A–Z, dois bonecos, indicador do nó que atende e comando pendente salvo na aba.

- [x] Vitória por abandono: adversário fora por 30 s com o outro presente; falhas do sistema não contam.
- [x] Chaves de replicação diferentes são avisadas no log dos dois nós.
- [x] Vigia da rede: servidor e gateway se recuperam sozinhos quando o container `tailscale` reinicia.

**Concluído quando:** os cenários T20 a T36 da especificação passam. ✔

## 8. Validação e apresentação

- [x] Testes automatizados em `tests/` (regras, chute, salas, nomes únicos, cliente, reenvio e queda de processo), executados por `python -m unittest discover -s tests` ou `scripts/forca.ps1 testes`.
- [x] Documentação alinhada ao código: README, ARCHITECTURE, especificação e protocolo.
- [x] Página verificada no navegador com dois jogadores: queda de `forca-a`, retorno como reserva e queda de `forca-b`, sem perder jogadas.
- [x] Desligamento físico do PC do nó que atende e retorno como reserva, com VMs reais, Tailscale e gateway na Oracle (troca em ~4 s).
- [ ] Executar o roteiro completo da seção 13 da especificação, com várias salas, na rede da faculdade.
- [ ] Medir e registrar o tempo de recuperação e o estado das salas antes e depois da queda.
- [ ] Conferir os requisitos do professor, incluindo a interpretação de "nó".

**Concluído quando:** a demonstração pode ser repetida seguindo o README, incluindo espera, novas salas e recuperação de falha.

## 9. Em aberto por decisão

Itens conhecidos que ficaram fora desta entrega:

- Terceiro nó como árbitro, para cobrir a falha de rede entre os dois nós com ambos recebendo jogadas.
- Número de sequência por sessão no lugar do identificador do último comando (requisição atrasada após o comando seguinte). Hoje o caso é coberto pela espera limitada pela trava.
- `/api/status` é público e mostra papel e revisão dos nós.
- A porta de sincronização aceita até 8 conexões não autenticadas ao mesmo tempo; só é alcançável pela rede do Tailscale.
- O script de estatísticas da Cloudflare é bloqueado pela política de segurança da página (erro no console, sem efeito no jogo).
- Testes automatizados que faltam: dois nós se juntando no mesmo instante e reenvio de `SAIR` já aplicado.
- O PDF da especificação e os arquivos `docs/documentacao-completa-sockets.md` e `melhorias.md` descrevem a arquitetura anterior.

