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
