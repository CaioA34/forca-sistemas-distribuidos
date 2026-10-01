"""Terminal com reconexão: a sessão identifica o jogador mesmo após a queda."""
import argparse
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
import uuid

try:
    import msvcrt
except ImportError:
    import fcntl

from forca.game import normalize
from forca.ui import HELP, render
from forca.wire import receive, send


def exchange(address, command):
    host, port = address.rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=2) as connection:
        connection.settimeout(10)  # Maior que o pior caso do servidor: trava, envio e ACK da réplica.
        with connection.makefile("rwb") as stream:
            send(stream, command)
            return receive(stream)


def read_keyboard(commands):
    while True:
        try:
            commands.put(input().strip())
        except (EOFError, KeyboardInterrupt):
            commands.put("/sair")
            return


def save(path, session):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session), encoding="utf-8")
    temporary.replace(path)


def lock(path):
    """Impede dois clientes abertos com o mesmo arquivo de sessão. O sistema libera ao encerrar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_suffix(".lock"), "a+b")
    handle.seek(0)
    try:
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def parse(action, state):
    """Converte o que foi digitado em comando para o servidor, ou em um aviso local (str)."""
    name, _, argument = action.partition(" ")
    name = name.lower()
    version = state["room_version"] if state else None
    if name == "/nova":
        return {"type": "ENTRAR"}
    if name == "/sair":
        return {"type": "SAIR"}
    if name == "/chute":
        if not argument.strip():
            return "Use /chute seguido da palavra. Exemplo: /chute SOCKET"
        return {"type": "CHUTAR", "word": argument.strip(), "version": version}
    if name.startswith("/"):
        return "Comando desconhecido. Digite /ajuda para ver os comandos."
    if len(normalize(action)) != 1:  # "ç" e "ã" contam como uma letra.
        return "Digite uma única letra, ou /chute seguido da palavra para tentar a palavra inteira."
    return {"type": "JOGAR", "letter": action, "version": version}


def run(name, servers, path, fresh=False):
    guard = lock(path)
    if guard is None:
        print(f"Já existe um cliente aberto com a sessão {path}. Use outro --name ou --session.")
        return
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    session = json.loads(previous) if previous and not fresh else {
        "token": secrets.token_urlsafe(32), "deployment": None, "pending": None}
    save(path, session)
    commands = queue.Queue()
    threading.Thread(target=read_keyboard, args=(commands,), daemon=True).start()
    state, me, last_screen, current_server = None, None, None, 0
    connected = False
    enter = session["deployment"] is None
    backlog = []  # Comandos para o servidor digitados enquanto outro ainda espera resposta.
    print("Conectando... Digite /ajuda para ver os comandos.")
    while True:
        # Comandos locais respondem na hora, mesmo sem conexão; os do servidor esperam a vez.
        while not commands.empty():
            action = commands.get()
            keyword = action.split(" ", 1)[0].lower()
            if not action:
                continue
            if keyword in {"/ajuda", "/help"}:
                print(HELP)
            elif keyword == "/estado" and not connected:
                print("Sem conexão com um servidor no momento. Tentando reconectar..."
                      + (" Último estado conhecido:" if state else ""))
                if state:
                    print(render(state, me))
            elif keyword == "/estado":
                last_screen = render(state, me)
                print(last_screen)
            else:
                parsed = parse(action, state)
                if isinstance(parsed, str):
                    print(parsed)  # Aviso local: comando desconhecido, /chute vazio etc.
                else:
                    backlog.append(action)
        if not session["pending"] and (enter or backlog):
            action = "/nova" if enter else backlog.pop(0)
            enter = False
            command = parse(action, state)  # Versão da sala atual, não a do momento em que foi digitado.
            session["pending"] = {
                **command, "request_id": str(uuid.uuid4()), "name": name,
                "token": session["token"], "deployment": session["deployment"]}
            save(path, session)  # O reenvio após uma queda mantém este identificador.
        command = session["pending"] or {"type": "ESTADO", "token": session["token"],
                                          "deployment": session["deployment"]}
        address = servers[current_server]
        try:
            response = exchange(address, command)
            if response.get("fatal"):
                print(response["message"])
                return
            if response.get("retry"):
                raise ConnectionError(response["message"])
        except (OSError, ValueError):
            if connected:
                print("Conexão perdida. Procurando outro servidor...")
            connected = False
            current_server = (current_server + 1) % len(servers)
            time.sleep(0.5)
            continue
        reconnected = not connected
        if reconnected:
            print(f"Conectado a {address} ({response.get('node', '?')}, {response.get('role', '')}).")
            connected = True
        session["deployment"] = response.get("deployment", session["deployment"])
        if session["pending"]:
            print(response.get("message", ""))
            kind = session["pending"]["type"]
            leaving = kind == "SAIR" and (response.get("ok") or response.get("code") == "SEM_SALA")
            session["pending"] = None
            save(path, session)
            if response.get("code") == "NOME_EM_USO":
                if fresh and previous:  # Devolve a sessão anterior deste nome, que ainda pode ser retomada.
                    path.write_text(previous, encoding="utf-8")
                elif fresh:
                    path.unlink()
                print("Abra o cliente com outro --name. Se o nome for seu, retome sem --nova-sessao.")
                return
            if leaving:
                return
        state, me = response.get("state"), response.get("player_id")
        if reconnected and command["type"] == "ESTADO" and state and state["status"] == "AGUARDANDO":
            enter = True  # Ao voltar, procura quem esteja esperando em outra sala.
        screen = render(state, me)
        if screen != last_screen:
            print(screen)
            last_screen = screen
        time.sleep(0.5)  # Atualiza os dois bonecos nos dois terminais.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--servers", default=os.getenv("CLIENT_SERVERS", "127.0.0.1:5000,127.0.0.1:5002"))
    parser.add_argument("--session", help="Arquivo individual de sessão deste jogador.")
    parser.add_argument("--nova-sessao", action="store_true")
    args = parser.parse_args()
    filename = "".join(c for c in args.name.casefold() if c.isalnum()) or "jogador"
    path = Path(args.session or f"sessions/{filename}.json")
    try:
        run(args.name, [s.strip() for s in args.servers.split(",")], path, args.nova_sessao)
    except KeyboardInterrupt:
        print("\nCliente fechado. A sessão foi guardada para reconexão.")


if __name__ == "__main__":
    main()
