# Implantação: Tailscale, duas VMs e o gateway na Oracle

```
navegador ──HTTPS──> Cloudflare ──> Oracle: Nginx ──> gateway (container)
                                                      │ Tailscale
                                   ┌──────────────────┴──────────────────┐
                    PC A: VM Ubuntu → forca-a  ◄── 5001 ──►  PC B: VM Ubuntu → forca-b
```

Cada máquina (as duas VMs e a Oracle) roda um container `tailscale` que a coloca na mesma rede
privada, com um nome fixo. O servidor e o gateway usam a rede desse container. Por isso:

- ninguém precisa descobrir ou digitar IP; trocar de rede (casa, faculdade, Wi-Fi, cabo) não muda nada;
- a VM pode ficar em rede NAT, sem modo bridge;
- as portas 5000 e 5001 só existem dentro da rede do Tailscale, nunca na rede local.

## 1. Tailscale (uma vez, no painel web)

1. Crie uma conta em https://login.tailscale.com (o plano pessoal gratuito basta).
2. Em **Access controls**, acrescente ao arquivo de política a tag e a regra do jogo:

   ```json
   "tagOwners": {
     "tag:forca": ["autogroup:admin"]
   },
   "grants": [
     {"src": ["tag:forca"], "dst": ["tag:forca"], "ip": ["tcp:5000", "tcp:5001"]}
   ]
   ```

   Se o arquivo ainda tiver a regra padrão que libera tudo entre todos os dispositivos, o jogo
   funciona do mesmo jeito; remova-a só se quiser isolar os dispositivos do jogo dos seus outros.
   O painel valida o arquivo ao salvar.
3. Em **DNS**, confirme que o **MagicDNS** está ligado (vem ligado em redes novas).
4. Em **Settings → Keys → Generate auth key**: marque **Reusable**, deixe **Ephemeral**
   desmarcado, escolha a tag `tag:forca` e uma validade (no máximo 90 dias). Guarde a chave
   `tskey-auth-...`: ela é um segredo, nunca vai para o Git. Envie em particular para quem
   for instalar uma VM.

Dispositivos com tag não expiram a cada 180 dias, então as VMs não precisam de novo login.

## 2. Em cada PC: VM com um nó

Requisito do trabalho: **uma VM Linux em cada um dos dois PCs**.

1. Crie uma VM Ubuntu 22.04 ou 24.04 no VirtualBox. A rede pode ficar em **NAT** (padrão).
2. Dentro da VM, obtenha o projeto (por exemplo, `git clone` do repositório) e entre na pasta.
3. Rode:

   ```bash
   bash scripts/preparar-vm.sh
   ```

   O script instala o Docker (pacotes do Ubuntu), pergunta se este PC é o nó **a** ou **b**, a
   chave do Tailscale e a chave de replicação (a mesma nos dois PCs), grava o `.env` com
   permissão só do dono e sobe os containers.

Para outra pessoa montar uma VM do zero, ela só precisa do projeto, da chave do Tailscale e da
chave de replicação. Todo o resto está em `compose.yaml` e no script.

Sem o script, o equivalente manual é:

```bash
cp .env.example .env    # edite NODE_NAME, PEER, TS_AUTHKEY e REPLICATION_KEY
sudo docker compose up -d --build
```

### Conferir

```bash
sudo docker compose exec tailscale tailscale status
```

Devem aparecer `forca-a`, `forca-b` e, depois do passo 3, `forca-gateway`.

```bash
sudo docker compose logs -f servidor
```

Um nó sozinho procura o outro por 10 s, registra `O outro nó não respondeu em 10 s: ... cria um jogo
novo` e passa a atender com uma cópia só. Assim que o outro sobe, aparece
`Reserva forca-b sincronizado... Agora há duas cópias.`

## 3. Oracle: gateway

Na instância Oracle, com o projeto clonado:

```bash
cd deploy/oracle
cp .env.example .env    # preencha TS_AUTHKEY; SERVIDORES e GATEWAY_HOST_PORT já têm padrão
sudo docker compose up -d --build
```

O gateway escuta só em `127.0.0.1:${GATEWAY_HOST_PORT}`. Para publicá-lo:

1. Na Cloudflare, crie o registro `forca` (tipo A) apontando para o IP público da Oracle, com proxy ligado.
2. Copie `deploy/oracle/nginx-forca.conf` para os sites do Nginx, ajuste o bloco de TLS ao
   padrão dos outros sites da instância, teste com `nginx -t` e recarregue.
3. Abra https://forca.ambrosias.dev e https://forca.ambrosias.dev/api/status.

## Comandos úteis na VM

Todos na pasta do projeto, dentro da VM.

| Para | Comando |
| --- | --- |
| Ver se os dois containers estão de pé | `sudo docker compose ps` |
| Acompanhar o log do nó | `sudo docker compose logs -f servidor` |
| Ver as últimas linhas do log do Tailscale | `sudo docker compose logs --tail 30 tailscale` |
| Ver quem está na rede do Tailscale | `sudo docker compose exec tailscale tailscale status` |
| Ver o endereço `100.x` desta VM | `sudo docker compose exec tailscale tailscale ip -4` |
| Testar se o outro nó é alcançado pelo nome | `sudo docker compose exec tailscale tailscale ping forca-b` |
| Conferir o `.env` sem mostrar as chaves | `grep -E '^NODE_NAME=' .env` e `grep -E '^PEER=' .env` |
| Atualizar para a versão mais recente | `git pull && sudo docker compose up -d --build` |
| Reiniciar o nó (ele volta como reserva do outro) | `sudo docker compose restart servidor` |
| Parar o nó | `sudo docker compose down` |
| Parar e apagar a identidade do Tailscale desta VM | `sudo docker compose down -v` |

De qualquer computador, o estado dos dois nós visto pelo gateway:

```bash
curl -s https://forca.ambrosias.dev/api/status
```

Cada nó aparece com `role` (`ENTRANDO`, `RESERVA`, `PRIMARIO` ou `FORA_DO_AR`), `serving` (se está
atendendo), `epoch` (quantas trocas de primário já houve) e `revision` (quantas alterações o jogo já
teve). Com os dois nós sincronizados, `epoch` e `revision` são iguais nos dois.

### O que o log do nó diz

| Mensagem | Significado |
| --- | --- |
| `O outro nó não respondeu em 10 s: forca-a cria um jogo novo...` | Este nó subiu sozinho e está atendendo com uma cópia só |
| `Nenhum jogo em andamento e forca-b também está entrando...` | Os dois subiram juntos; o de nome menor criou o jogo |
| `Reserva forca-b sincronizado na revisão N. Agora há duas cópias.` | O outro nó entrou como reserva |
| `Reserva de forca-a:5001 na revisão N.` | Este nó é o reserva |
| `Ligação com o reserva perdida (...): primário pausado por até 7 s.` | O reserva sumiu; o primário espera antes de seguir sozinho |
| `O outro nó não assumiu: forca-a segue atendendo sozinho...` | Passaram os 7 s; o jogo continua com uma cópia |
| `PRIMÁRIO CAIU: forca-b assumiu na revisão N (época M).` | Este nó era reserva e passou a atender |
| `Dois primários: prevalece ...` | Os nós se reencontraram atendendo; o de menos jogadas virou reserva |
| `Estado N confirmado (vitória por abandono na sala-1).` | Um jogador ficou 30 s fora e o adversário venceu |
| `REPLICATION_KEY precisa ser igual nos dois nós...` | As chaves de replicação são diferentes (ver abaixo) |
| `A rede deste processo deixou de existir...` | O container `tailscale` reiniciou; o servidor se reinicia sozinho |

## Situações comuns ao configurar as VMs

**O script não fez nenhuma pergunta e o Compose reclamou de `NODE_NAME`.**
Já existia um `.env` de uma versão anterior do projeto, e o script não sobrescreve um `.env`
existente. Guarde o antigo e rode de novo:

```bash
mv .env .env.antigo && bash scripts/preparar-vm.sh
```

**Errei uma resposta do script (nó ou chave).**
Apague o `.env` e rode o script de novo; ele volta a perguntar.

```bash
rm .env && bash scripts/preparar-vm.sh
```

**O container `tailscale` fica reiniciando e a VM não aparece em Machines.**
Quase sempre é a chave. Confira no log:

```bash
sudo docker compose logs --tail 30 tailscale
```

Causas vistas na prática: a chave colada com o prefixo repetido (`tskey-auth-tskey-auth-...`), uma
chave já revogada ou vencida, ou uma chave gerada sem a tag `tag:forca`. Corrija a linha
`TS_AUTHKEY` do `.env` (ela deve começar com um único `tskey-auth-`) e recrie os containers:

```bash
sudo docker compose up -d --force-recreate
```

**A VM entrou no Tailscale como `forca-a-1` em vez de `forca-a`.**
Já existia um dispositivo com esse nome, de uma instalação anterior. O outro nó e o gateway
procuram por `forca-a` e não a encontram. Apague os dois dispositivos (`forca-a` e `forca-a-1`) em
**Machines** no painel e recrie a identidade desta VM:

```bash
sudo docker compose down -v && sudo docker compose up -d
```

**O nó aparece `FORA_DO_AR` no `/api/status`.**
O gateway não alcança a VM. Confira, nesta ordem: se a VM está ligada, se os dois containers estão de
pé (`sudo docker compose ps`), e se a VM aparece conectada em `tailscale status`. Depois de religar o
PC, lembre que é preciso iniciar a VM no VirtualBox; o Docker dentro dela sobe sozinho.

**Os dois nós aparecem como `PRIMARIO` atendendo e não viram primário e reserva.**
Eles não estão se sincronizando. Se o log mostrar `REPLICATION_KEY precisa ser igual nos dois nós`,
as chaves de replicação são diferentes: corrija o `.env` de uma das VMs e rode
`sudo docker compose up -d`. Se não houver esse aviso, o problema é de rede entre as VMs: teste com
`sudo docker compose exec tailscale tailscale ping forca-b`.

**O nó fica em `ENTRANDO` por alguns segundos ao subir.**
É o esperado: ele procura o outro por até 10 s antes de decidir se vira reserva ou se cria o jogo.

**A página mostra "Reconectando…" por alguns segundos.**
Acontece durante a troca de servidor: até 5 s quando um PC é desligado, e até 7 s quando o reserva
some e o primário espera antes de seguir sozinho. Se durar mais que isso, veja o `/api/status`.

**As abas abertas voltaram para a tela de nome.**
Os dois nós pararam ao mesmo tempo e o jogo recomeçou do zero (o estado fica só na memória). Para
evitar, nunca deixe os dois fora do ar juntos: ao atualizar, faça uma VM de cada vez.

**`permission denied` ao rodar `docker`.**
Use `sudo`, ou coloque seu usuário no grupo `docker` e entre de novo na sessão:

```bash
sudo usermod -aG docker $USER
```

**O script falha com `$'\r': command not found`.**
O projeto foi copiado de um Windows com fim de linha CRLF. Prefira `git clone` dentro da VM. Para
corrigir a cópia atual:

```bash
sed -i 's/\r$//' scripts/preparar-vm.sh .env.example compose.yaml
```

**`/dev/net/tun não existe nesta VM`.**
O Tailscale precisa desse dispositivo. Carregue o módulo e rode o script de novo:

```bash
sudo modprobe tun
```

**Quero recomeçar o jogo do zero.**
Pare os dois nós e suba de novo. O primeiro que subir cria um jogo novo depois de 10 s.

```bash
sudo docker compose down
```

```bash
sudo docker compose up -d
```

## Se os nomes não resolverem dentro do container

O `compose.yaml` liga `TS_ACCEPT_DNS` para que `forca-a` e `forca-b` resolvam dentro do container.
Confira, em uma VM:

```bash
sudo docker compose exec servidor python -c "import socket; print(socket.gethostbyname('forca-b'))"
```

Se falhar, use os endereços `100.x.y.z` do Tailscale no lugar dos nomes. Veja o endereço de cada
máquina com `sudo docker compose exec tailscale tailscale ip -4` e troque `PEER` (nas VMs) e
`SERVIDORES` (na Oracle). Esses endereços não mudam enquanto o volume `tailscale-state` existir.

## Se o container tailscale reiniciar sozinho

O servidor e o gateway usam a rede do container `tailscale`. Se só esse container reiniciar
(`docker restart`, ou uma queda seguida do reinício automático), a rede antiga deixa de existir.
O processo percebe isso em poucos segundos, registra `A rede deste processo deixou de existir` e se
encerra; o Docker o reinicia já na rede nova. O nó volta em cerca de 5 a 10 s, como reserva de quem
estiver atendendo, sem nenhum comando.

## Se os dois nós atenderem ao mesmo tempo sem se enxergar

Confira a chave de replicação. Com chaves diferentes os nós não se sincronizam e cada um cria o
próprio jogo. Os dois registram no log:

```
REPLICATION_KEY precisa ser igual nos dois nós; sem isso eles não se sincronizam.
```

Corrija o `.env` de um deles e rode `sudo docker compose up -d`.

## Ensaiar tudo em uma máquina só

Com Docker e o `.env` preenchido, os três projetos sobem na mesma máquina (verificado no WSL):

```bash
docker compose -p forca-a up -d --build
NODE_NAME=forca-b PEER=forca-a:5001 docker compose -p forca-b up -d
(cd deploy/oracle && docker compose --env-file ../../.env -p forca-gateway up -d)
```

O jogo fica em http://127.0.0.1:8080. Ao terminar, `docker compose -p <projeto> down -v` em cada um
e **apague os três dispositivos em Machines no painel do Tailscale**, senão as VMs reais entrarão
como `forca-a-1`, `forca-b-1` e `forca-gateway-1`.

## Reinstalar uma VM

O Tailscale não aceita dois dispositivos com o mesmo nome: uma VM nova chamada `forca-a`, com o
dispositivo antigo ainda cadastrado, vira `forca-a-1`, e o outro nó deixa de encontrá-la. Antes
de reinstalar, apague o dispositivo antigo em **Machines** no painel.

## Durante a apresentação

- O canto da página mostra qual nó está atendendo. `/api/status` mostra papel e época dos dois.
- Desligue o PC do nó que está atendendo. Em até ~5 s o outro assume (época +1) e a página continua.
- Religue o PC: o container volta sozinho (`restart: unless-stopped`) e entra como **reserva** de
  quem está atendendo. Para mostrar o ciclo completo, desligue agora o outro PC.
- Para começar do zero, pare os dois nós (`sudo docker compose down` nas duas VMs) e suba de novo.
  As abas abertas voltam à tela de nome.
