"""Ensaio de falhas com os containers de deploy/local: joga pelo gateway e derruba os nós.

Uso, com `docker compose up -d --build` já feito nesta pasta:  python3 ensaio.py
"""
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid

URL = "http://127.0.0.1:8080"
NETWORK = "local_default"


def call(body):
    request = urllib.request.Request(URL + "/api", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return json.loads(error.read())
    except OSError:
        return {"retry": True}


def status():
    with urllib.request.urlopen(URL + "/api/status", timeout=5) as response:
        return {n.get("node", n["address"]): (n["role"], n["serving"], n.get("epoch"))
                for n in json.loads(response.read())["nodes"]}


def docker(*arguments):
    subprocess.run(["docker", *arguments], check=True, capture_output=True)


def crash(container):
    """Encerra o processo principal por dentro; a política de reinício do Docker o traz de volta."""
    docker("exec", container, "python", "-c", "import os, signal; os.kill(1, signal.SIGINT)")


def wait(check, what, seconds=40):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        try:
            if check():
                print(f"  ok em {time.monotonic() - start:4.1f} s: {what}")
                return
        except OSError:
            pass
        time.sleep(0.25)
    raise SystemExit(f"FALHOU: {what}\n  status: {status()}")


class Player:
    def __init__(self, name):
        self.name, self.token = name, secrets.token_urlsafe(32)

    def send(self, kind, **fields):
        body = {"type": kind, "token": self.token, "name": self.name,
                "request_id": str(uuid.uuid4()), **fields}
        while True:  # Como a página: reenvia o mesmo comando até haver resposta.
            response = call(body)
            if not response.get("retry"):
                return response
            time.sleep(0.5)

    def state(self):
        return call({"type": "ESTADO", "token": self.token})


def snapshot(ana, bruno):
    bruno.state()
    state = ana.state().get("state")
    return state and {k: state[k] for k in ("room_id", "room_version", "guesses", "masked_word", "turn")}


def play(players, letter):
    """Joga a letra com quem estiver na vez."""
    for _ in range(20):
        for p in players:
            p.state()
        state = players[0].state()["state"]
        author = next(p for p in players if p.state()["player_id"] == state["turn"])
        result = author.send("JOGAR", letter=letter, version=state["room_version"])
        if result.get("code") != "PAUSADA":  # Logo após uma retomada, a presença ainda está voltando.
            assert result["ok"], result
            return result["node"]
        time.sleep(0.3)
    raise SystemExit(f"FALHOU: partida continuou pausada: {result}")


def serving(node, epoch):
    return lambda: status().get(node) == ("PRIMARIO", True, epoch)


def main():
    wait(serving("forca-a", 1), "forca-a atendendo, forca-b reserva")
    ana, bruno = Player("Ana"), Player("Bruno")
    ana.send("ENTRAR")
    bruno.send("ENTRAR")
    players = [ana, bruno]
    print("jogada 1 atendida por", play(players, "A"))
    before = snapshot(ana, bruno)

    print("\n1) Processo do primário morre (SIGINT no PID 1) e o Docker o reinicia")
    crash("local-forca-a-1")
    wait(serving("forca-b", 2), "forca-b assumiu (época 2)")
    wait(lambda: snapshot(ana, bruno) == before, "partida idêntica no forca-b")
    wait(lambda: status().get("forca-a") == ("RESERVA", False, 2),
         "forca-a reiniciado pelo Docker voltou como RESERVA")
    print("jogada 2 atendida por", play(players, "E"))
    before = snapshot(ana, bruno)

    print("\n2) Rede do primário cortada (como desligar o PC): detecção por timeout")
    docker("network", "disconnect", NETWORK, "local-forca-b-1")
    wait(serving("forca-a", 3), "forca-a assumiu (época 3)")
    wait(lambda: snapshot(ana, bruno) == before, "partida idêntica no forca-a, com a jogada feita no forca-b")
    print("jogada 3 atendida por", play(players, "O"))
    before = snapshot(ana, bruno)

    print("\n3) Rede volta: o antigo primário, pausado e ainda com a cópia velha, cede e vira reserva")
    docker("network", "connect", "--alias", "forca-b", NETWORK, "local-forca-b-1")
    wait(lambda: status().get("forca-b") == ("RESERVA", False, 3), "forca-b virou RESERVA do forca-a")
    assert status()["forca-a"] == ("PRIMARIO", True, 3), status()
    assert snapshot(ana, bruno) == before

    print("\n4) Reserva cai e volta: primário pausa e retoma sozinho")
    crash("local-forca-b-1")
    wait(lambda: status().get("forca-b") == ("RESERVA", False, 3) and status()["forca-a"][1],
         "reserva reiniciado se juntou; forca-a atendendo")
    wait(lambda: snapshot(ana, bruno) == before, "partida idêntica")
    print("jogada 4 atendida por", play(players, "I"))
    print("\nENSAIO OK:", snapshot(ana, bruno))


if __name__ == "__main__":
    main()
