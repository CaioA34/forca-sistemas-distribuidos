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

O servidor usa a rede do container `tailscale`. Se só esse container reiniciar por fora do Compose
(`docker restart`, ou uma queda seguida do reinício automático), o servidor continua rodando preso
à rede antiga: o nó aparece `FORA_DO_AR` no `/api/status` e o outro segue sozinho. Para recuperar:

```bash
sudo docker compose restart servidor
```

`docker compose restart tailscale` já reinicia o servidor junto, e reiniciar a VM inteira também
não tem esse problema.

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
