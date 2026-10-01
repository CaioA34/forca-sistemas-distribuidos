"""Nó do jogo com papéis dinâmicos de primário e reserva, estado em RAM. Execute --help para ver as opções."""
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
from forca.wire import encode, receive, send, write

LOG = logging.getLogger("forca")
WORDS = Path(__file__).parent / "forca/words.txt"

JOINING, BACKUP, PRIMARY = "ENTRANDO", "RESERVA", "PRIMARIO"
ONLINE = 5         # Segundos sem consultar até o jogador aparecer desconectado.
LOCK_WAIT = 2      # Menor que a leitura de quem envia: nada é aplicado depois que o remetente desistiu.
HEARTBEAT = 0.5    # Intervalo entre heartbeats do primário.
PRIMARY_WAIT = 3   # O primário espera ACK e heartbeat por até 3 s...
BACKUP_WAIT = 5    # ...e o reserva espera o primário por 5 s: o primário se pausa antes de o reserva assumir.
JOIN_RETRY = 1
BOOT_WAIT = 10     # Ao iniciar, procura o outro nó por este tempo antes de criar um jogo sozinho.
SOLO_WAIT = 7      # Ao perder o reserva, espera mais que BACKUP_WAIT antes de seguir sozinho: se foi a
                   # rede que caiu, o reserva já assumiu e o gateway já mandou os jogadores para ele.


class Server:
    def __init__(self, node="forca-a", peer="127.0.0.1:5003", host="0.0.0.0", port=5000,
                 sync_port=5001, key="forca-aula", words=None, boot_wait=BOOT_WAIT, solo_wait=SOLO_WAIT):
        self.node, self.peer = node, peer
        self.boot_wait, self.solo_wait = boot_wait, solo_wait
        self.host, self.port, self.sync_port = host, port, sync_port
        self.key = key
        self.words = load_words(words or WORDS.read_text(encoding="utf-8").splitlines())
        self.role = JOINING
        self.state = None     # Só existe a partir de PRIMARIO ou RESERVA.
        self.backup = None    # Canal com o reserva sincronizado, quando há um.
        self.hold_until = 0.0  # Primário sem reserva só atende depois deste instante (ver SOLO_WAIT).
        self.held = False      # Em espera após perder o reserva; serve para avisar uma vez no log.
        self.joining_since = time.monotonic()
        self.seen = {}        # Presença local; uma conexão antiga não migra entre máquinas.
        self.since = time.monotonic()  # Início do atendimento; após a promoção, recomeça.
        self.lock = threading.Lock()   # Papel, estado e canal do reserva mudam juntos.
        self.slots = threading.BoundedSemaphore(64)
        self.sync_slots = threading.BoundedSemaphore(8)

    # Papel -------------------------------------------------------------------------------------

    @property
    def serving(self):
        """O primário atende com reserva ou sozinho; sozinho, só depois da espera de quem perdeu o reserva."""
        return self.role == PRIMARY and (self.backup is not None or time.monotonic() >= self.hold_until)

    @property
    def seeking(self):
        """Sem estado, ou primário sem reserva: procura o outro nó, para se juntar a ele ou reconciliar."""
        return self.role == JOINING or (self.role == PRIMARY and self.backup is None)

    def status(self):
        state = self.state  # Lido sem a trava: PING responde mesmo com o nó ocupado.
        return {"ok": True, "node": self.node, "role": self.role, "serving": self.serving,
                "epoch": state["epoch"] if state else None,
                "revision": state["revision"] if state else None}

    def outranks(self, revision, epoch, node):
        """Entre dois primários, fica quem confirmou mais jogadas; no empate, a maior época e o menor nome."""
        mine = (self.state["revision"], self.state["epoch"])
        theirs = (revision or 0, epoch or 0)
        return mine > theirs or (mine == theirs and self.node < str(node))

    def create(self, reason):
        """Chamado com a trava. Começa um jogo novo; este nó atende já, mesmo sem reserva."""
        self.state, self.role, self.hold_until = new_state(), PRIMARY, 0.0
        self.since, self.seen = time.monotonic(), {}
        LOG.info("%s: %s cria um jogo novo e atende sem segunda cópia até o outro nó entrar.", reason, self.node)

    # Canal dos jogadores -----------------------------------------------------------------------

    def online(self):
        now = time.monotonic()
        players = self.state["world"]["players"]
        for pid in [pid for pid, instant in self.seen.items()
                    if now - instant >= ONLINE and pid not in players]:
            del self.seen[pid]  # Tokens que nunca entraram não ocupam memória.
        return {pid for pid, instant in self.seen.items() if now - instant < ONLINE}

    def idle(self):
        """Jogadores sem consultar há NAME_HOLD segundos. Quem nunca consultou conta desde self.since."""
        now = time.monotonic()
        return {pid for pid in self.state["world"]["players"]
                if now - self.seen.get(pid, self.since) >= NAME_HOLD}

    def replicate(self, candidate, data=None):
        # O reserva guarda a cópia ANTES de enviar ACK. Só então o jogador recebe sucesso.
        write(self.backup, data or encode({"state": candidate}))
        ack = receive(self.backup)
        if ack.get("ack") != candidate["revision"]:
            raise ConnectionError("Confirmação de replicação inválida.")

    def request(self, command):
        if command.get("type") == "PING":
            return self.status()
        if not self.lock.acquire(timeout=LOCK_WAIT):
            return {"retry": True, "message": "Servidor ocupado. Tentando de novo."}
        try:
            if not self.serving:
                return {"retry": True, "message": f"O nó {self.node} não está atendendo ({self.role})."}
            self.announce_solo()
            pid = player_id(command.get("token"))
            deployment = command.get("deployment")
            if deployment and deployment != self.state["world"]["deployment_id"]:
                return {"fatal": True, "message": "Esta sessão pertence a outra execução. Entre de novo."}
            self.seen[pid] = time.monotonic()
            result = {"ok": True}
            if command.get("type") != "ESTADO":
                candidate = copy.deepcopy(self.state)
                result = apply(candidate, command, self.online(), self.words, self.idle())
                try:
                    data = encode({"state": candidate})
                except ValueError:
                    result = {"ok": False, "code": "ESTADO_CHEIO",
                              "message": "O servidor atingiu o limite de estado. Tente mais tarde."}
                else:
                    if self.backup is not None:
                        try:
                            self.replicate(candidate, data)
                        except (OSError, ValueError):
                            self.lose_backup("a replicação falhou")
                            return {"retry": True, "message": "Replicação interrompida. Procurando outro servidor."}
                    self.state = candidate
                    LOG.info("Estado %s confirmado (%s).", self.state["revision"], command.get("type"))
            return {**result, "player_id": pid, "deployment": self.state["world"]["deployment_id"],
                    "state": public_state(self.state, pid, self.online()),
                    "role": self.role, "node": self.node}
        finally:
            self.lock.release()

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

    def accept_forever(self, listener, slots, target):
        while True:
            connection, _ = listener.accept()
            if slots.acquire(blocking=False):
                threading.Thread(target=target, args=(connection,), daemon=True).start()
            else:
                connection.close()

    def serve(self):
        with self.listen(self.port) as listener:
            LOG.info("Nó %s atendendo jogadores em %s:%s", self.node, self.host, self.port)
            self.accept_forever(listener, self.slots, self.client)

    # Canal de sincronização: quem procura o outro nó conecta; quem é primário aceita -----------

    def synchronize(self):
        with self.listen(self.sync_port) as listener:
            LOG.info("Sincronização em %s:%s; outro nó em %s", self.host, self.sync_port, self.peer)
            self.accept_forever(listener, self.sync_slots, self.visitor)

    def accepts(self, hello):
        """Primário sem reserva aceita quem está entrando e também outro primário que tenha menos jogadas."""
        if self.role != PRIMARY or self.backup is not None or hello.get("node") == self.node:
            return False
        role = hello.get("role", JOINING)
        if role == PRIMARY:
            return self.outranks(hello.get("revision"), hello.get("epoch"), hello.get("node"))
        return role == JOINING

    def visitor(self, connection):
        try:
            with connection:
                connection.settimeout(PRIMARY_WAIT)
                with connection.makefile("rwb") as stream:
                    self.attend(stream)
        except (OSError, ValueError):
            pass  # Fechar um canal rompido também falha ao descarregar o buffer.
        finally:
            self.sync_slots.release()

    def attend(self, stream):
        hello = receive(stream)
        # Em bytes: compare_digest recusa texto com acentos, o que derrubaria esta thread.
        if not hmac.compare_digest(str(hello.get("key", "")).encode(), self.key.encode()):
            return
        with self.lock:
            if not self.accepts(hello):
                send(stream, self.status())
                return
            paused = not self.serving
            self.backup = stream
            try:
                self.replicate(self.state, encode({"state": self.state, "node": self.node}))
            except (OSError, ValueError):
                # Quem se junta só assume depois da segunda mensagem (ver follow); sem ela, este nó
                # segue como estava e espera outra tentativa.
                self.backup = None
                LOG.warning("Sincronização inicial com o reserva falhou; aguardando nova tentativa.")
                return
            if paused:
                # Pausado, o nó não registrou presença: quem consultou o tempo todo não pode parecer sumido.
                self.since, self.seen = time.monotonic(), {}
            self.held = False
            LOG.info("Reserva %s sincronizado na revisão %s. Agora há duas cópias.",
                     hello.get("node", "?"), self.state["revision"])
        try:
            while True:
                with self.lock:  # O primeiro heartbeat sai logo após o ACK: o reserva passa a poder assumir.
                    if self.backup is not stream:
                        break
                    send(stream, {"heartbeat": True})
                    if receive(stream).get("heartbeat") is not True:
                        raise ConnectionError("Heartbeat inválido.")
                time.sleep(HEARTBEAT)
        except (OSError, ValueError):
            with self.lock:
                if self.backup is stream:
                    self.lose_backup("o reserva parou de responder")

    def lose_backup(self, reason):
        """Chamado com a trava. Sem a segunda cópia, o primário se pausa por SOLO_WAIT e procura o outro nó."""
        self.backup, self.held = None, True
        self.hold_until = time.monotonic() + self.solo_wait
        LOG.warning("Ligação com o reserva perdida (%s): primário pausado por até %s s.", reason, self.solo_wait)

    def announce_solo(self):
        """Chamado com a trava. Avisa uma vez quando a espera termina e o nó volta a atender sozinho."""
        if self.held and self.backup is None and self.serving:
            self.held = False
            LOG.warning("O outro nó não assumiu: %s segue atendendo sozinho, sem segunda cópia.", self.node)

    def seek(self):
        """Laço de fundo: sem reserva, procura o outro nó para se juntar a ele, aceitá-lo ou reconciliar."""
        while True:
            with self.lock:
                seeking = self.seeking
                self.announce_solo()
            if seeking:
                try:
                    self.join()
                except (OSError, ValueError):  # O outro nó não está acessível.
                    with self.lock:
                        waited = time.monotonic() - self.joining_since
                        if self.role == JOINING and waited >= self.boot_wait:
                            self.create(f"O outro nó não respondeu em {self.boot_wait:g} s")
            time.sleep(JOIN_RETRY)

    def join(self):
        host, port = self.peer.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=PRIMARY_WAIT) as connection:
            connection.settimeout(BACKUP_WAIT)
            with connection.makefile("rwb") as stream:
                with self.lock:
                    send(stream, {**self.status(), "key": self.key})
                first = receive(stream)
                if "state" not in first:
                    self.consider(first)
                    return
                theirs = first["state"]
                with self.lock:
                    if not self.seeking:
                        return  # Um reserva se juntou a este nó enquanto isso: recusa fechando o canal.
                    if self.role == PRIMARY:
                        if self.outranks(theirs["revision"], theirs.get("epoch"), first.get("node", "")):
                            return  # Este nó tem mais jogadas confirmadas: é o outro que deve ceder.
                        LOG.warning("Dois primários: prevalece %s (revisão %s, época %s); %s (revisão %s, "
                                    "época %s) descarta a própria cópia e vira reserva.",
                                    self.peer, theirs["revision"], theirs.get("epoch"),
                                    self.node, self.state["revision"], self.state["epoch"])
                    self.role, self.state, self.held = BACKUP, theirs, False
                    send(stream, {"ack": self.state["revision"]})
                LOG.info("Reserva de %s na revisão %s.", self.peer, self.state["revision"])
                self.follow(stream)

    def consider(self, status):
        """O outro nó não aceitou. Se os dois estão entrando, o de nome menor cria o jogo."""
        other = status.get("node")
        with self.lock:
            if self.role != JOINING or status.get("role") != JOINING:
                return
            if other == self.node:
                LOG.error("Os dois nós se chamam %s: ajuste NODE_NAME e PEER.", self.node)
            elif self.node < str(other):
                self.create(f"Nenhum jogo em andamento e {other} também está entrando")

    def follow(self, stream):
        synchronized = False
        try:
            while True:
                message = receive(stream)
                # Só assume depois da segunda mensagem: ela prova que o primário recebeu
                # o ACK da cópia inicial e não vai procurar outro reserva.
                synchronized = True
                if "state" in message:
                    with self.lock:
                        self.state = message["state"]
                    send(stream, {"ack": message["state"]["revision"]})
                else:
                    send(stream, {"heartbeat": True})
        except (OSError, ValueError):
            pass
        with self.lock:
            if not synchronized:
                self.role, self.state, self.joining_since = JOINING, None, time.monotonic()
                LOG.info("Sincronização interrompida antes de confirmar; tentando de novo.")
                return
            self.state["epoch"] += 1
            self.role, self.hold_until = PRIMARY, 0.0
            self.since, self.seen = time.monotonic(), {}  # Os jogadores ainda vão reconectar: ninguém perde o nome já.
            LOG.warning("PRIMÁRIO CAIU: %s assumiu na revisão %s (época %s). Agora há apenas uma cópia.",
                        self.node, self.state["revision"], self.state["epoch"])

    def run(self):
        threading.Thread(target=self.synchronize, daemon=True).start()
        threading.Thread(target=self.seek, daemon=True).start()
        self.serve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=os.getenv("NODE_NAME", "forca-a"),
                        help="Nome deste nó. Com os dois entrando, o de nome menor cria o jogo.")
    parser.add_argument("--peer", default=os.getenv("PEER", "127.0.0.1:5003"),
                        help="host:porta de sincronização do outro nó (ex.: forca-b:5001).")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("GAME_PORT", "5000")))
    parser.add_argument("--sync-port", type=int, default=int(os.getenv("SYNC_PORT", "5001")))
    parser.add_argument("--key", default=os.getenv("REPLICATION_KEY", "forca-aula"))
    parser.add_argument("--boot-wait", type=float, default=float(os.getenv("BOOT_WAIT", BOOT_WAIT)),
                        help="Segundos procurando o outro nó ao iniciar, antes de criar um jogo sozinho.")
    parser.add_argument("--solo-wait", type=float, default=float(os.getenv("SOLO_WAIT", SOLO_WAIT)),
                        help="Segundos de pausa ao perder o reserva, antes de seguir sozinho.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        server = Server(args.node, args.peer, args.host, args.port, args.sync_port, args.key,
                        boot_wait=args.boot_wait, solo_wait=args.solo_wait)
    except ValueError as exc:
        raise SystemExit(f"Lista de palavras inválida ({WORDS.name}): {exc}")
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
