"""Nós com papéis dinâmicos em processos reais, com TCP, replicação, queda abrupta e retorno."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid

import forca.wire
from forca.lobby import new_state
from forca.wire import receive, send
from servidor import BACKUP, JOINING, PRIMARY, Server

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def exchange(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.settimeout(8)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


def token(name):
    return (name + "-token-").ljust(40, "x")


def command(who, kind, request_id=None, **fields):
    return {"type": kind, "token": token(who), "request_id": request_id or str(uuid.uuid4()), **fields}


def wait_for(check, seconds=20):
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


def ping(port):
    return exchange(port, {"type": "PING"})


def serving(port):
    return ping(port)["serving"]


class Processes(unittest.TestCase):
    """Sobe nós do servidor.py em subprocessos e encerra todos ao fim de cada teste."""

    def setUp(self):
        self.processes = []
        self.ports = {name: (free_port(), free_port()) for name in ("forca-a", "forca-b")}

    def start(self, name, peer_sync=None):
        game, sync = self.ports[name]
        other = next(n for n in self.ports if n != name)
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen(
            [sys.executable, "servidor.py", "--node", name, "--host", "127.0.0.1",
             "--port", str(game), "--sync-port", str(sync),
             "--peer", f"127.0.0.1:{peer_sync or self.ports[other][1]}"],
            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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

    def game(self, name):
        return self.ports[name][0]


class ReplicationTests(Processes):
    def setUp(self):
        super().setUp()
        self.a = self.start("forca-a")
        wait_for(lambda: ping(self.game("forca-a")))
        # Sozinho, um nó nunca se declara primário: não há onde guardar a segunda cópia.
        self.assertEqual(ping(self.game("forca-a"))["role"], JOINING)
        self.assertTrue(exchange(self.game("forca-a"), command("Ana", "ENTRAR", name="Ana")).get("retry"))
        self.b = self.start("forca-b")
        wait_for(lambda: serving(self.game("forca-a")))  # Nome menor cria o jogo; o outro vira reserva.
        self.assertEqual(wait_for(lambda: ping(self.game("forca-b"))["role"] == BACKUP and "ok"), "ok")

    def start_match(self, port):
        exchange(port, command("Ana", "ENTRAR", name="Ana"))
        return exchange(port, command("Bruno", "ENTRAR", name="Bruno"))["state"]

    def snapshot(self, port):
        exchange(port, command("Bruno", "ESTADO"))
        return exchange(port, command("Ana", "ESTADO"))["state"]

    def test_reserva_assume_com_a_partida_intacta(self):
        a, b = self.game("forca-a"), self.game("forca-b")
        state = self.start_match(a)
        request_id = str(uuid.uuid4())
        first = exchange(a, command("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"]))
        self.assertTrue(first["ok"])
        before = self.snapshot(a)
        self.assertTrue(exchange(b, command("Ana", "ESTADO")).get("retry"))  # O reserva não atende.

        self.stop(self.a)
        wait_for(lambda: serving(b))
        self.assertEqual(ping(b)["epoch"], 2)
        after = self.snapshot(b)
        self.assertEqual(after, before)

        # O reenvio da jogada já confirmada não é aplicado de novo no reserva.
        again = exchange(b, command("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"]))
        self.assertEqual(again["message"], first["message"])
        self.assertEqual(again["state"]["room_version"], before["room_version"])

        guess = exchange(b, command("Bruno", "CHUTAR", word="XYZ", version=before["room_version"]))
        self.assertTrue(guess["ok"])
        self.assertEqual(guess["state"]["wrong_words"], ["XYZ"])

    def test_antigo_primario_volta_como_reserva_e_assume_depois(self):
        a, b = self.game("forca-a"), self.game("forca-b")
        state = self.start_match(a)
        exchange(a, command("Ana", "JOGAR", letter="Z", version=state["room_version"]))
        self.stop(self.a)
        wait_for(lambda: serving(b))

        # Uma jogada feita só no nó promovido, enquanto o antigo primário está fora.
        version = self.snapshot(b)["room_version"]
        self.assertTrue(exchange(b, command("Bruno", "JOGAR", letter="Q", version=version))["ok"])

        self.a = self.start("forca-a")
        self.assertEqual(wait_for(lambda: ping(a)["role"] == BACKUP and "ok"), "ok")
        self.assertTrue(serving(b))
        before = self.snapshot(b)
        self.assertEqual(before["guesses"], ["Z", "Q"])

        log = self.stop(self.b)
        wait_for(lambda: serving(a))
        self.assertEqual(ping(a)["epoch"], 3)
        self.assertEqual(self.snapshot(a), before)
        self.assertIn("Reserva forca-a sincronizado", log)
        self.assertNotIn("Traceback", log)

    def test_primario_pausa_ao_perder_o_reserva_e_volta_com_ele(self):
        a = self.game("forca-a")
        self.start_match(a)
        before = self.snapshot(a)
        self.stop(self.b)
        wait_for(lambda: "retry" in exchange(a, command("Ana", "ESTADO")))
        self.assertEqual(ping(a)["role"], PRIMARY)
        # O reserva reinicia vazio e se junta ao primário pausado, que volta a atender com o mesmo jogo.
        self.b = self.start("forca-b")
        wait_for(lambda: serving(a))
        self.assertEqual(self.snapshot(a), before)
        log = self.stop(self.a)
        self.assertIn("primário pausado", log.lower())
        self.assertNotIn("Traceback", log)

    def test_nome_unico_vale_entre_os_servidores(self):
        exchange(self.game("forca-a"), command("ana1", "ENTRAR", name="Ana"))
        self.stop(self.a)
        b = self.game("forca-b")
        wait_for(lambda: serving(b))
        refused = exchange(b, command("ana2", "ENTRAR", name="ANA"))
        self.assertEqual(refused["code"], "NOME_EM_USO")

    def test_comando_malformado_recebe_resposta_sem_traceback(self):
        a = self.game("forca-a")
        response = exchange(a, {"type": "JOGAR", "token": token("Ana"), "request_id": 5})
        self.assertFalse(response["ok"])
        self.assertIn("Comando inválido", response["message"])
        untyped = exchange(a, {"token": token("Ana"), "request_id": str(uuid.uuid4())})
        self.assertEqual(untyped["code"], "COMANDO_INVALIDO")
        invalid = socket.create_connection(("127.0.0.1", a), timeout=2)
        with invalid, invalid.makefile("rwb") as stream:
            stream.write(b"isto nao e json\n")
            stream.flush()
            self.assertFalse(receive(stream)["ok"])
        self.assertNotIn("Traceback", self.stop(self.a))


class InitialSyncTests(Processes):
    def test_chave_com_acento_e_reserva_que_some_nao_travam_o_primario(self):
        self.a, self.b = self.start("forca-a"), self.start("forca-b")
        a, sync = self.game("forca-a"), self.ports["forca-a"][1]
        wait_for(lambda: serving(a))
        self.stop(self.b)
        wait_for(lambda: not serving(a))
        with socket.create_connection(("127.0.0.1", sync), timeout=2) as intruder:
            with intruder.makefile("rwb") as stream:
                send(stream, {"key": "ç"})
                self.assertEqual(stream.readline(), b"")  # Recusado: conexão fechada.
        with socket.create_connection(("127.0.0.1", sync), timeout=2) as vanishing:
            with vanishing.makefile("rwb") as stream:
                send(stream, {"key": "forca-aula"})
                self.assertIn("state", receive(stream))  # Recebe a cópia e some sem ACK.
        self.b = self.start("forca-b")
        wait_for(lambda: serving(a))
        log = self.stop(self.a)
        self.assertIn("Sincronização inicial com o reserva falhou", log)
        self.assertNotIn("Traceback", log)

    def test_reserva_so_assume_apos_a_segunda_mensagem(self):
        listener = socket.create_server(("127.0.0.1", 0))
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

        backup = self.start("forca-b", peer_sync=listener.getsockname()[1])
        b = self.game("forca-b")
        fake_primary(heartbeat=False)  # Só a cópia inicial: o ACK pode não ter chegado ao primário.
        time.sleep(1.5)
        self.assertEqual(ping(b)["role"], JOINING)
        thread = threading.Thread(target=fake_primary, args=(True,))
        thread.start()  # O nó tenta de novo; agora recebe a segunda mensagem.
        thread.join(15)
        self.assertEqual(wait_for(lambda: serving(b) and ping(b)["role"]), PRIMARY)
        self.assertNotIn("Traceback", self.stop(backup))


class InProcessTests(unittest.TestCase):
    """Decisões do nó sem subprocessos: estado montado à mão."""

    def node(self, name, peer_sync, role, alone=False, state=None):
        server = Server(name, f"127.0.0.1:{peer_sync}", "127.0.0.1", free_port(), free_port())
        server.role, server.alone, server.state = role, alone, state
        return server

    def test_primario_pausado_cede_ao_outro_que_assumiu(self):
        # Rede entre os nós caiu: o reserva assumiu (época 2) e o antigo primário ficou pausado.
        old, promoted = new_state(), new_state()
        promoted["epoch"], promoted["revision"] = 2, 7
        b = self.node("forca-b", 0, PRIMARY, alone=True, state=promoted)
        a = self.node("forca-a", b.sync_port, PRIMARY, state=old)
        b.peer = f"127.0.0.1:{a.sync_port}"
        for server in (a, b):
            threading.Thread(target=server.run, daemon=True).start()
        wait_for(lambda: a.role == BACKUP)
        self.assertEqual(a.state["revision"], 7)
        wait_for(lambda: b.backup is not None)
        self.assertTrue(b.serving)

    def test_estado_grande_demais_recusa_o_comando_sem_pausar(self):
        server = self.node("forca-a", 0, PRIMARY, alone=True, state=new_state())
        limit = forca.wire.MAX_BYTES
        forca.wire.MAX_BYTES = 300
        self.addCleanup(setattr, forca.wire, "MAX_BYTES", limit)
        result = server.request(command("Ana", "ENTRAR", name="Ana"))
        self.assertEqual(result["code"], "ESTADO_CHEIO")
        self.assertEqual(server.state["revision"], 0)
        self.assertTrue(server.serving)

    def test_requisicao_que_espera_demais_pela_trava_nao_e_aplicada(self):
        server = self.node("forca-a", 0, PRIMARY, alone=True, state=new_state())
        with server.lock:
            result = server.request(command("Ana", "ENTRAR", name="Ana"))
        self.assertTrue(result["retry"])
        self.assertEqual(server.state["revision"], 0)


if __name__ == "__main__":
    unittest.main()
