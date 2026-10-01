"""Gateway HTTP sem estado: o navegador fala HTTP e os nós falam JSON por linha em TCP.

O gateway não guarda sessão nem jogo. Ele descobre qual nó está atendendo e encaminha cada
requisição sem alterá-la; token, request_id e comando pendente continuam sob controle do navegador.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import socket
import threading
import time

from forca.rede import watch_network
from forca.wire import receive, send

LOG = logging.getLogger("forca.gateway")
WEB = Path(__file__).parent / "web"
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
         "/style.css": ("style.css", "text/css; charset=utf-8")}
COMMANDS = {"ESTADO", "ENTRAR", "JOGAR", "CHUTAR", "SAIR"}
MAX_BODY = 8192
CONNECT, READ = 1, 10  # A leitura cobre o pior caso do nó: trava (2 s) + envio (3 s) + ACK (3 s).
IDLE = 10              # Conexão HTTP que não envia a requisição nesse tempo é encerrada.
START_LIMIT = 6        # Nenhuma tentativa começa depois disso: o pior caso fica em ~17 s e o navegador espera 20 s.
PROBE = 1


def exchange(address, command, read=READ):
    host, port = address.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=CONNECT) as connection:
        connection.settimeout(read)
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


class Gateway:
    def __init__(self, servers):
        self.servers = servers
        self.nodes = {address: None for address in servers}  # Última resposta de PING de cada nó.
        self.lock = threading.Lock()

    def probe(self, address):
        while True:
            try:
                status = exchange(address, {"type": "PING"}, read=2)
            except (OSError, ValueError):
                status = None
            with self.lock:
                if (status or {}).get("serving") != (self.nodes[address] or {}).get("serving"):
                    LOG.info("%s: %s", address, "atendendo" if (status or {}).get("serving")
                             else "fora do ar" if status is None else status.get("role"))
                self.nodes[address] = status
            time.sleep(PROBE)

    def start(self):
        for address in self.servers:
            threading.Thread(target=self.probe, args=(address,), daemon=True).start()

    def order(self):
        """Quem atende primeiro; entre dois atendendo, o de mais jogadas confirmadas e depois a maior época
        (a mesma regra pela qual os nós decidem quem cede). Os outros vêm em seguida, caso o PING atrase."""
        with self.lock:
            nodes = dict(self.nodes)

        def rank(address):
            status = nodes[address] or {}
            return (not status.get("serving"), -(status.get("revision") or 0), -(status.get("epoch") or 0))
        return sorted(self.servers, key=rank)

    def forward(self, command):
        start = time.monotonic()
        for address in self.order():
            if time.monotonic() - start > START_LIMIT:
                break
            try:
                response = exchange(address, command)
            except (OSError, ValueError):
                with self.lock:
                    self.nodes[address] = None
                continue
            if not response.get("retry"):
                return 200, response
        return 503, {"retry": True, "message": "Nenhum servidor disponível no momento. Tentando de novo."}

    def status(self):
        with self.lock:
            return {"nodes": [{"address": address, **(status or {"serving": False, "role": "FORA_DO_AR"})}
                              for address, status in self.nodes.items()]}


class Handler(BaseHTTPRequestHandler):
    gateway: Gateway
    slots = threading.BoundedSemaphore(128)
    timeout = IDLE  # Sem isto, conexões ociosas ocupariam todos os slots para sempre.
    server_version = "forca-gateway"
    sys_version = ""

    def reply(self, code, body, content_type="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def handle_one_request(self):
        if not self.slots.acquire(blocking=False):
            self.close_connection = True
            return
        try:
            super().handle_one_request()
        finally:
            self.slots.release()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self.reply(200, self.gateway.status())
        if path not in FILES:
            return self.reply(404, {"ok": False, "message": "Não encontrado."})
        name, content_type = FILES[path]
        self.reply(200, (WEB / name).read_bytes(), content_type)

    def do_POST(self):
        if self.path != "/api":
            return self.reply(404, {"ok": False, "message": "Não encontrado."})
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.reply(411, {"ok": False, "message": "Informe o tamanho da requisição."})
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"ok": False, "message": "Requisição grande demais."})
        try:
            command = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, ValueError):
            return self.reply(400, {"ok": False, "message": "JSON inválido."})
        if not isinstance(command, dict) or command.get("type") not in COMMANDS:
            return self.reply(400, {"ok": False, "message": "Comando desconhecido."})
        self.reply(*self.gateway.forward(command))

    def log_message(self, format, *args):
        pass  # Sem log por requisição: o corpo carrega o token do jogador.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("GATEWAY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("GATEWAY_PORT", "8080")))
    parser.add_argument("--servers", default=os.getenv("SERVIDORES", "127.0.0.1:5000,127.0.0.1:5002"),
                        help="Endereços de jogo dos nós, separados por vírgula (ex.: forca-a:5000,forca-b:5000).")
    parser.add_argument("--idle-timeout", type=float, default=IDLE,
                        help="Segundos até encerrar uma conexão HTTP que não envia a requisição.")
    args = parser.parse_args()
    Handler.timeout = args.idle_timeout
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    gateway = Gateway([s.strip() for s in args.servers.split(",") if s.strip()])
    gateway.start()
    watch_network(LOG)
    Handler.gateway = gateway
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    LOG.info("Gateway em http://%s:%s encaminhando para %s", args.host, args.port, ", ".join(gateway.servers))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nGateway encerrado.")


if __name__ == "__main__":
    main()
