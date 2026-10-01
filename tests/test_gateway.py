"""Gateway HTTP: validação, roteamento para o nó que atende e troca de servidor ponta a ponta."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid

from forca.wire import receive, send
from gateway import Gateway
from tests.test_servidor import Processes, free_port, token, wait_for

ROOT = Path(__file__).resolve().parents[1]


def http(port, method, path, body=None, raw=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=25)
    try:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        connection.request(method, path, body=data, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        connection.close()


def api(port, body):
    status, _, data = http(port, "POST", "/api", body)
    return status, json.loads(data)


class FakeNode:
    """Nó falso: responde PING com o papel dado e registra os comandos recebidos."""

    def __init__(self, serving, epoch=1):
        self.serving, self.epoch, self.received = serving, epoch, []
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.address = f"127.0.0.1:{self.listener.getsockname()[1]}"
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            with connection, connection.makefile("rwb") as stream:
                message = receive(stream)
                if message["type"] == "PING":
                    send(stream, {"ok": True, "serving": self.serving, "epoch": self.epoch, "role": "X"})
                    continue
                self.received.append(message)
                send(stream, {"ok": True, "node": self.address} if self.serving
                     else {"retry": True, "message": "não atende"})

    def close(self):
        self.listener.close()


class RoutingTests(unittest.TestCase):
    def test_encaminha_ao_no_que_atende_mesmo_listado_depois(self):
        idle, active = FakeNode(False), FakeNode(True)
        self.addCleanup(idle.close)
        self.addCleanup(active.close)
        gateway = Gateway([idle.address, active.address])
        gateway.start()
        wait_for(lambda: gateway.order()[0] == active.address)
        code, response = gateway.forward({"type": "ESTADO", "token": "t"})
        self.assertEqual((code, response["node"]), (200, active.address))
        self.assertEqual(idle.received, [])  # Nem chegou a tentar quem não atende.

    def test_sem_ping_ainda_tenta_todos_e_pula_quem_pede_retry(self):
        idle, active = FakeNode(False), FakeNode(True)
        self.addCleanup(idle.close)
        self.addCleanup(active.close)
        gateway = Gateway([idle.address, active.address])  # Sem start: nenhum PING feito.
        code, response = gateway.forward({"type": "ESTADO"})
        self.assertEqual((code, response["node"]), (200, active.address))
        self.assertEqual(len(idle.received), 1)

    def test_prefere_a_maior_epoca(self):
        old, new = FakeNode(True, epoch=1), FakeNode(True, epoch=2)
        self.addCleanup(old.close)
        self.addCleanup(new.close)
        gateway = Gateway([old.address, new.address])
        gateway.start()
        wait_for(lambda: gateway.order()[0] == new.address)

    def test_nenhum_no_disponivel(self):
        gateway = Gateway([f"127.0.0.1:{free_port()}"])
        self.assertEqual(gateway.forward({"type": "ESTADO"}), (503, {
            "retry": True, "message": "Nenhum servidor disponível no momento. Tentando de novo."}))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = FakeNode(True)
        cls.port = free_port()
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        cls.process = subprocess.Popen(
            [sys.executable, "gateway.py", "--host", "127.0.0.1", "--port", str(cls.port),
             "--servers", cls.node.address], cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        wait_for(lambda: http(cls.port, "GET", "/api/status"))

    @classmethod
    def tearDownClass(cls):
        cls.process.kill()
        cls.process.communicate(timeout=10)
        cls.node.close()

    def test_arquivos_da_pagina(self):
        for path, kind in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css")):
            status, content_type, body = http(self.port, "GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(content_type.startswith(kind))
            self.assertTrue(body)

    def test_caminhos_fora_da_lista_nao_sao_servidos(self):
        for path in ("/../servidor.py", "/web/app.js", "/index.html", "/%2e%2e/servidor.py"):
            self.assertEqual(http(self.port, "GET", path)[0], 404)

    def test_validacao_do_corpo(self):
        cases = [(b"nao json", 400), (json.dumps([1]).encode(), 400),
                 (json.dumps({"type": "PING"}).encode(), 400), (b"x" * 9000, 413)]
        for raw, expected in cases:
            self.assertEqual(http(self.port, "POST", "/api", raw=raw)[0], expected)
        self.assertEqual(http(self.port, "POST", "/outro", {"type": "ESTADO"})[0], 404)

    def test_encaminha_o_comando_sem_alterar(self):
        command = {"type": "JOGAR", "token": "t", "request_id": "r", "letter": "A", "version": 3}
        self.assertEqual(api(self.port, command), (200, {"ok": True, "node": self.node.address}))
        self.assertEqual(self.node.received[-1], command)

    def test_status_dos_nos(self):
        status = json.loads(http(self.port, "GET", "/api/status")[2])
        self.assertEqual(status["nodes"][0]["address"], self.node.address)


class IdleConnectionTests(unittest.TestCase):
    def test_conexoes_ociosas_nao_derrubam_o_gateway(self):
        node = FakeNode(True)
        self.addCleanup(node.close)
        port = free_port()
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen(
            [sys.executable, "gateway.py", "--host", "127.0.0.1", "--port", str(port),
             "--servers", node.address, "--idle-timeout", "1"], cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.addCleanup(process.communicate, timeout=10)
        self.addCleanup(process.kill)
        wait_for(lambda: http(port, "GET", "/api/status"))
        idle = [socket.create_connection(("127.0.0.1", port), timeout=2) for _ in range(128)]
        for connection in idle:
            self.addCleanup(connection.close)
        half = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.addCleanup(half.close)
        half.sendall(b"POST /api HTTP/1.1\r\nContent-Length: 50\r\n\r\n{")  # Corpo que nunca termina.
        # Todos os slots estão presos; passado o tempo limite, o gateway volta a responder.
        self.assertEqual(wait_for(lambda: http(port, "GET", "/api/status")[0], seconds=10), 200)
        self.assertEqual(api(port, {"type": "ESTADO", "token": "t"})[0], 200)


class EndToEndTests(Processes):
    """Navegador simulado → gateway → dois nós reais; o primário cai no meio da partida."""

    def setUp(self):
        super().setUp()
        self.a, self.b = self.start("forca-a"), self.start("forca-b")
        self.http_port = free_port()
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        servers = ",".join(f"127.0.0.1:{self.game(n)}" for n in ("forca-a", "forca-b"))
        self.gateway = subprocess.Popen(
            [sys.executable, "gateway.py", "--host", "127.0.0.1", "--port", str(self.http_port),
             "--servers", servers], cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processes.append(self.gateway)

    def send(self, who, kind, request_id=None, **fields):
        body = {"type": kind, "token": token(who), "request_id": request_id or str(uuid.uuid4()), **fields}
        return api(self.http_port, body)[1]

    def view(self, who):
        return api(self.http_port, {"type": "ESTADO", "token": token(who)})[1]

    def test_partida_continua_pelo_mesmo_endereco_apos_a_queda(self):
        wait_for(lambda: self.view("Ana").get("ok"))
        self.assertEqual(self.send("Ana", "ENTRAR", name="Ana")["node"], "forca-a")
        state = self.send("Bruno", "ENTRAR", name="Bruno")["state"]
        request_id = str(uuid.uuid4())
        first = self.send("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"])
        self.assertTrue(first["ok"])
        self.view("Bruno")
        before = self.view("Ana")["state"]

        self.stop(self.a)
        after = wait_for(lambda: (r := self.view("Ana")).get("node") == "forca-b" and r)
        self.view("Bruno")
        after = self.view("Ana")
        self.assertEqual(after["state"], before)
        again = self.send("Ana", "JOGAR", request_id, letter="Z", version=state["room_version"])
        self.assertEqual(again["message"], first["message"])  # Reenvio pelo gateway: sem efeito duplo.
        guess = self.send("Bruno", "CHUTAR", word="XYZ", version=before["room_version"])
        self.assertTrue(guess["ok"])

        def serving():  # O status vem do PING a cada 1 s: pode atrasar em relação à troca.
            nodes = json.loads(http(self.http_port, "GET", "/api/status")[2])["nodes"]
            return [(n["node"], n["epoch"]) for n in nodes if n["serving"]]
        wait_for(lambda: serving() == [("forca-b", 2)])


if __name__ == "__main__":
    unittest.main()
