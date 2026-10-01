"""Vigia da rede do processo: encerra quando a rede em que ele nasceu deixa de existir.

No Compose, o servidor e o gateway usam a rede do container tailscale (network_mode: service). Se só
aquele container reinicia, este processo continua vivo dentro da rede antiga, já sem interfaces: escuta
portas que ninguém alcança. Encerrar resolve, porque a política de reinício do Docker recria o
container já ligado à rede nova.
"""
import os
import socket
import threading
import time

CHECK = 3  # Segundos entre verificações; duas seguidas sem rede encerram o processo.


def external_interfaces():
    """Interfaces além da loopback. Em uma rede órfã só resta a loopback."""
    return {name for _, name in socket.if_nameindex() if not name.lower().startswith("lo")}


def watch_network(log, check=CHECK, leave=os._exit):
    """Inicia a vigia. Não faz nada se o processo já nasceu sem interfaces externas."""
    try:
        if not external_interfaces():
            return None
    except OSError:
        return None  # Plataforma sem a consulta: segue sem vigia.

    def watch():
        missing = 0
        while True:
            time.sleep(check)
            try:
                missing = 0 if external_interfaces() else missing + 1
            except OSError:
                continue
            if missing >= 2:
                log.error("A rede deste processo deixou de existir (o container de rede reiniciou?). "
                          "Encerrando para ser reiniciado na rede nova.")
                leave(1)
                return

    thread = threading.Thread(target=watch, daemon=True, name="vigia-da-rede")
    thread.start()
    return thread
