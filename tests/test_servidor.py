"""Primário e reserva em processos reais, com TCP, replicação e queda abrupta."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid

from forca.lobby import new_state
from forca.wire import receive, send

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def exchange(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.settimeout(5)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


def token(name):
    return (name + "-token-").ljust(40, "x")


def command(who, kind, request_id=None, **fields):
    return {"type": kind, "token": token(who), "request_id": request_id or str(uuid.uuid4()), **fields}


def wait_for(check, seconds=15):
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


class Processes(unittest.TestCase):
    """Sobe servidor.py em subprocessos e encerra todos ao fim de cada teste."""

    def setUp(self):
        self.processes = []

    def start(self, *arguments):
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen([sys.executable, "servidor.py", *arguments], cwd=ROOT, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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


class ReplicationTests(Processes):
    def setUp(self):
        super().setUp()
        self.game, self.sync, self.backup_game = free_port(), free_port(), free_port()
        self.primary = self.start("--port", str(self.game), "--sync-port", str(self.sync))
        wait_for(lambda: exchange(self.game, {"type": "PING"}))
        # Sem reserva sincronizado, nenhuma alteração é aceita.
        self.assertTrue(exchange(self.game, command("Ana", "ENTRAR", name="Ana")).get("retry"))
        self.backup = self.start("--modo", "reserva", "--port", str(self.backup_game),
                                 "--sync-port", str(self.sync))
        # ESTADO recebe retry até o reserva sincronizar.
        wait_for(lambda: "retry" not in exchange(self.game, {"type": "ESTADO", "token": token("x")}))

    def test_reserva_assume_com_a_partida_intacta(self):
        exchange(self.game, command("Ana", "ENTRAR", name="Ana"))
        state = exchange(self.game, command("Bruno", "ENTRAR", name="Bruno"))["state"]
        request_id = str(uuid.uuid4())
        first = exchange(self.game, command("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"]))
        self.assertTrue(first["ok"])
        exchange(self.game, command("Bruno", "ESTADO"))
        before = exchange(self.game, command("Ana", "ESTADO"))["state"]

        self.stop(self.primary)
        wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))
        exchange(self.backup_game, command("Bruno", "ESTADO"))
        after = exchange(self.backup_game, command("Ana", "ESTADO"))
        self.assertEqual(after["role"], "RESERVA_PROMOVIDO")
        self.assertEqual(after["state"], before)

        # O reenvio da jogada já confirmada não é aplicado de novo no reserva.
        again = exchange(self.backup_game, command("Ana", "JOGAR", request_id, letter="Z",
                                                   version=state["room_version"]))
        self.assertEqual(again["message"], first["message"])
        self.assertEqual(again["state"]["room_version"], before["room_version"])

        guess = exchange(self.backup_game, command("Bruno", "CHUTAR", word="XYZ", version=before["room_version"]))
        self.assertTrue(guess["ok"])
        self.assertEqual(guess["state"]["wrong_words"], ["XYZ"])

    def test_nome_unico_vale_entre_os_servidores(self):
        exchange(self.game, command("ana1", "ENTRAR", name="Ana"))
        self.stop(self.primary)
        wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))
        refused = exchange(self.backup_game, command("ana2", "ENTRAR", name="ANA"))
        self.assertEqual(refused["code"], "NOME_EM_USO")

    def test_primario_pausa_ao_perder_o_reserva(self):
        self.stop(self.backup)
        wait_for(lambda: "retry" in exchange(self.game, command("Ana", "ENTRAR", name="Ana")))
        invalid = socket.create_connection(("127.0.0.1", self.game), timeout=2)
        with invalid, invalid.makefile("rwb") as stream:
            stream.write(b"isto nao e json\n")
            stream.flush()
            self.assertFalse(receive(stream)["ok"])
        log = self.stop(self.primary)
        self.assertIn("primário pausado", log.lower())  # Por ACK ou heartbeat.
        self.assertNotIn("Traceback", log)


    def test_comando_malformado_recebe_resposta_sem_traceback(self):
        response = exchange(self.game, {"type": "JOGAR", "token": token("Ana"), "request_id": 5})
        self.assertFalse(response["ok"])
        self.assertIn("Comando inválido", response["message"])
        self.assertNotIn("Traceback", self.stop(self.primary))


class InitialSyncTests(Processes):
    def setUp(self):
        super().setUp()
        self.game, self.sync, self.backup_game = free_port(), free_port(), free_port()

    def ready(self):
        return "retry" not in exchange(self.game, {"type": "ESTADO", "token": token("x")})

    def test_chave_com_acento_e_reserva_que_some_nao_travam_o_primario(self):
        primary = self.start("--port", str(self.game), "--sync-port", str(self.sync))
        wait_for(lambda: exchange(self.game, {"type": "PING"}))
        with socket.create_connection(("127.0.0.1", self.sync), timeout=2) as intruder:
            with intruder.makefile("rwb") as stream:
                send(stream, {"key": "ç"})
                self.assertEqual(stream.readline(), b"")  # Recusado: conexão fechada.
        with socket.create_connection(("127.0.0.1", self.sync), timeout=2) as vanishing:
            with vanishing.makefile("rwb") as stream:
                send(stream, {"key": "forca-aula"})
                self.assertIn("state", receive(stream))  # Recebe a cópia e some sem ACK.
        self.start("--modo", "reserva", "--port", str(self.backup_game), "--sync-port", str(self.sync))
        wait_for(self.ready)
        log = self.stop(primary)
        self.assertIn("Sincronização inicial com o reserva falhou", log)
        self.assertNotIn("pausado", log.lower())
        self.assertNotIn("Traceback", log)

    def test_reserva_so_assume_apos_a_segunda_mensagem(self):
        listener = socket.create_server(("127.0.0.1", self.sync))
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

        backup = self.start("--modo", "reserva", "--port", str(self.backup_game),
                            "--sync-port", str(self.sync))
        fake_primary(heartbeat=False)  # Só a cópia inicial: o ACK pode não ter chegado ao primário.
        time.sleep(1.5)
        with self.assertRaises(OSError):
            exchange(self.backup_game, {"type": "PING"})
        thread = threading.Thread(target=fake_primary, args=(True,))
        thread.start()  # O reserva tenta de novo; agora recebe a segunda mensagem.
        thread.join(15)
        self.assertEqual(wait_for(lambda: exchange(self.backup_game, {"type": "PING"}))["role"],
                         "RESERVA_PROMOVIDO")
        self.assertNotIn("Traceback", self.stop(backup))


if __name__ == "__main__":
    unittest.main()
