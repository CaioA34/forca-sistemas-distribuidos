# Roadmap — Jogo da Forca Distribuído

Arquitetura de referência: [ARQUITETURA.md](ARQUITETURA.md).

Implementar em etapas pequenas; avançar quando o critério de conclusão estiver atendido.

## 1. Regras e jogo local

- [ ] Validar com o professor a interpretação de novo nó como processo por sala.
- [ ] Definir alternância dos turnos, letras repetidas, vitória, derrota e comportamento durante desconexões.
- [ ] Implementar as regras da forca em Python, separadas da interface e da rede.
- [ ] Exibir palavra parcial, turno e os dois bonequinhos no terminal.

**Concluído quando:** uma partida local completa funciona e tentativas fora da vez são rejeitadas.

## 2. Comunicação por sockets

- [ ] Criar cliente e servidor TCP e mensagens JSON delimitadas por linha.
- [ ] Tratar mensagens parciais, várias mensagens juntas, timeout e conexão encerrada.
- [ ] Conectar dois clientes e enviar o estado atualizado aos dois.

**Concluído quando:** dois terminais jogam a mesma partida e mostram o mesmo estado.

## 3. Espera e processos das salas

- [ ] Criar o gerenciador de jogadores e a fila de espera.
- [ ] Criar um processo por sala e filas locais para trocar mensagens com o gerenciador.
- [ ] Associar cada jogador à sua sala e limitar a dois participantes.

**Concluído quando:** A espera, B inicia a sala 1 com A, C cria a sala 2 e espera, e D joga com C. As partidas são independentes.

## 4. Execução com Docker

- [ ] Criar `Dockerfile`, `compose.yaml`, `.dockerignore` e `.env.example`, fixando as versões das dependências.
- [ ] Executar o gerenciador e os processos das salas em um único container por servidor.
- [ ] Publicar a porta TCP do jogo e parametrizar identificador, endereço anunciado e acesso ao Supabase; manter credenciais fora da imagem e do Git.
- [ ] Configurar encerramento dos processos das salas e reinício do container pela política do Docker.

**Concluído quando:** clientes externos ao container jogam duas partidas independentes, e encerrar o container também encerra seus processos de sala.

## 5. Persistência no Supabase

- [ ] Criar tabelas de sessões, salas/partidas, jogadas, servidores e liderança.
- [ ] Salvar entradas e jogadas antes de confirmar aos clientes; usar transações e versões para evitar conflitos.
- [ ] Adicionar token de sessão e identificador de jogada para reconexão e reenvio.
- [ ] Restringir a descoberta à leitura necessária e manter dados do jogo acessíveis apenas aos servidores.

**Concluído quando:** reiniciar o servidor permite reconstruir as salas e retomar sessões; reenviar uma jogada não duplica seu efeito.

## 6. VMs e descoberta de servidores

- [ ] Preparar uma VM em cada notebook e conectar VMs e clientes pelo Tailscale.
- [ ] Instalar Docker Engine e Compose em cada VM e executar a mesma imagem do servidor, com configurações próprias.
- [ ] Registrar automaticamente o endereço Tailscale da VM e a porta publicada do container no Supabase.
- [ ] Fazer o cliente descobrir o ativo sem uma lista fixa de IPs.

**Concluído quando:** um cliente conecta à VM de outro notebook; mudar o servidor anunciado não exige editar o cliente. Verificar também em redes diferentes.

## 7. Liderança e recuperação automática

- [ ] Implementar aquisição e renovação atômicas da autorização temporária, com horário do banco e geração crescente.
- [ ] Validar a autorização dentro de toda transação que altera o jogo.
- [ ] Fazer o reserva assumir, carregar os estados e recriar as salas.
- [ ] Fazer clientes redescobrirem o ativo e retomarem sessões com espera entre tentativas.
- [ ] Pausar alterações quando não for possível confirmar acesso ao banco ou liderança.

**Concluído quando:** desligar a VM principal durante duas partidas permite que ambas continuem no reserva, preservando turno, erros, letras e jogadores aguardando.

## 8. Validação e apresentação

- [ ] Testar queda após gravar uma jogada, mas antes de responder: o reenvio não pode aplicá-la duas vezes.
- [ ] Testar dois reservas disputando a liderança e rejeição de escritas do antigo principal.
- [ ] Testar perda de acesso ao Supabase: nenhuma ação pode ser confirmada sem gravação.
- [ ] Testar separadamente a parada do container e o desligamento da VM ativa, verificando retomada das partidas pelo reserva.
- [ ] Registrar nos logs criação de salas, mudanças de liderança e retomadas de sessão, sem expor tokens.
- [ ] Preparar a demonstração em dois notebooks e conferir os requisitos do professor.
- [ ] Criar o README com instalação, configuração e execução após a aplicação funcionar.

**Concluído quando:** a demonstração pode ser repetida seguindo o README, incluindo entrada em fila, novas salas e recuperação de falha.
