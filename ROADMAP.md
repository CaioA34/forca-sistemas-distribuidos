# Roadmap — Jogo da Forca Distribuído

Referências: [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [especificação](docs/especificacao-jogo-forca.md), [protocolo](docs/protocolo.md) e [implantação](docs/implantacao.md).

A arquitetura adotada é **dois nós com papéis dinâmicos, estado em RAM e replicação síncrona**, jogados pelo navegador através de um gateway HTTP sem estado na instância Oracle. Os nós e o gateway se encontram pelo Tailscale, com nomes fixos, porque a rede da faculdade é restrita e os IPs mudam a cada rede. Só a biblioteca padrão do Python é usada.

## Concluído

**Jogo**
- Regras separadas da rede (`forca/game.py`): turno alternado, seis erros por jogador, chute da palavra inteira, acentos ignorados.
- Salas automáticas de dois jogadores, independentes entre si; reagrupamento de quem ficou esperando em salas separadas.
- Nomes únicos entre jogadores ativos; liberação após 180 s fora de partida.
- Vitória por abandono: adversário 30 s fora com o outro presente; falhas do sistema não contam.

**Comunicação e concorrência**
- JSON por linha sobre TCP, com limite de tamanho (`forca/wire.py`); uma conexão curta por comando.
- Trava única no nó, versão por sala e limite de conexões simultâneas.
- Um comando pendente por jogador, salvo antes do envio; reenvio reconhecido pelo recibo, inclusive depois da troca de servidor.
- Espera pela trava limitada: uma requisição só é aplicada enquanto quem a enviou ainda espera.

**Parte distribuída**
- Replicação do estado completo antes de responder, com heartbeat e chave compartilhada.
- Papéis dinâmicos: o reserva assume na queda do primário; quem volta entra como reserva.
- Um nó sozinho atende; o outro entra depois e recebe a cópia.
- Reconciliação de dois primários por revisão, época e nome.
- Coleta do estado: partidas encerradas e jogadores que saíram são apagados.

**Jogador e implantação**
- Página web (`web/`) e gateway HTTP sem estado (`gateway.py`); o jogador usa um endereço só.
- Nó em container com Tailscale em cada VM (`compose.yaml`) e gateway na Oracle (`deploy/oracle/`).
- `scripts/preparar-vm.sh` prepara uma VM; `docs/implantacao.md` traz comandos úteis e situações comuns.
- Vigia da rede: servidor e gateway se recuperam quando o container `tailscale` reinicia.

**Validação**
- Testes automatizados em `tests/` (Windows e Linux) e ensaio de falhas em containers (`deploy/local/ensaio.py`).
- Ambiente real, em 02/10/2026: gateway em https://forca.ambrosias.dev e dois nós em VMs de PCs diferentes. Com o PC do nó que atendia desligado fisicamente, o outro assumiu em cerca de 4 s; o PC religado voltou como reserva com as jogadas feitas enquanto esteve fora.

## Falta para a apresentação

- [ ] Executar o roteiro completo da seção 13 da especificação, com várias salas, na rede da faculdade.
- [ ] Medir lá o tempo de recuperação; o Tailscale pode usar servidores intermediários e demorar mais.
- [ ] Conferir os requisitos do professor, incluindo a interpretação de "nó".

## Em aberto por decisão

Itens conhecidos que ficaram fora desta entrega.

**Parte distribuída**
- Terceiro nó como árbitro, para cobrir a falha de rede entre os dois nós com ambos recebendo jogadas.
- Número de sequência por sessão no lugar do identificador do último comando. Hoje a requisição atrasada é barrada pela espera limitada pela trava.
- Cada comando replica o estado inteiro; replicar só a sala alterada reduziria o custo.
- Um reenvio já reconhecido ainda é replicado e registrado no log, embora nada mude.

**Servidor e gateway**
- Porta já ocupada encerra o servidor com traceback em vez de uma mensagem clara.
- Nomes com e sem acento ("João" e "Joao") são aceitos ao mesmo tempo, embora letras e chutes ignorem acento.
- `/api/status` é público e mostra papel e revisão dos nós.
- A porta de sincronização aceita até 8 conexões não autenticadas ao mesmo tempo; só é alcançável pela rede do Tailscale.
- Fora do Compose, a chave de replicação tem o valor padrão `forca-aula`.
- Os containers não têm verificação de saúde (`healthcheck`).
- O script de estatísticas da Cloudflare é bloqueado pela política de segurança da página (erro no console, sem efeito no jogo).

**Cliente de terminal** (`cliente.py`, mantido só para testes)
- Nomes que diferem só por símbolos compartilham o mesmo arquivo de sessão.
- `--servers` inválido faz o cliente tentar para sempre, sem mensagem.
- Quem perdeu o nome por inatividade recebe uma orientação que não explica o motivo.

**Testes e repositório**
- Faltam testes automatizados para dois nós se juntando no mesmo instante e para o reenvio de `SAIR` já aplicado.
- Não há integração contínua.
