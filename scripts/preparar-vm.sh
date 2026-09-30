#!/usr/bin/env bash
# Prepara uma VM Ubuntu 22.04+ para rodar um nó do jogo: instala o Docker, cria o .env e sobe os containers.
# Uso, na pasta do projeto dentro da VM:  bash scripts/preparar-vm.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    . /etc/os-release
    if [ "${ID:-}" != "ubuntu" ]; then
        echo "Instale Docker Engine e o plugin compose manualmente: https://docs.docker.com/engine/install/" >&2
        exit 1
    fi
    echo "Instalando Docker a partir dos pacotes do Ubuntu..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-v2
    sudo systemctl enable --now docker
fi

if [ ! -e /dev/net/tun ]; then
    echo "/dev/net/tun não existe nesta VM; o Tailscale precisa dele (sudo modprobe tun)." >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "Configuração deste nó (fica em .env, fora do git)."
    read -rp "Este PC é o nó a ou b? " letra
    case "$letra" in
        a|A) node=forca-a; peer=forca-b ;;
        b|B) node=forca-b; peer=forca-a ;;
        *) echo "Responda a ou b." >&2; exit 1 ;;
    esac
    read -rsp "Chave de autenticação do Tailscale (tskey-auth-...): " authkey; echo
    read -rsp "Chave de replicação (igual nos dois nós): " replication; echo
    umask 077
    cat > .env <<EOF
NODE_NAME=$node
PEER=$peer:5001
TS_AUTHKEY=$authkey
REPLICATION_KEY=$replication
EOF
    echo ".env criado para $node."
fi

sudo docker compose up -d --build
echo
sudo docker compose ps
echo
echo "Acompanhe com:  sudo docker compose logs -f servidor"
echo "Rede Tailscale: sudo docker compose exec tailscale tailscale status"
