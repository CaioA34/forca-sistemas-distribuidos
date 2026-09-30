"""Sobe os dois nós e o gateway nesta máquina, para testar sem VMs: http://127.0.0.1:8080.

Digite "a" ou "b" + Enter para derrubar ou religar aquele nó e ver a troca de servidor ao vivo.
"""
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
NODES = {
    "a": ["servidor.py", "--node", "forca-a", "--host", "127.0.0.1", "--port", "5000",
          "--sync-port", "5001", "--peer", "127.0.0.1:5003"],
    "b": ["servidor.py", "--node", "forca-b", "--host", "127.0.0.1", "--port", "5002",
          "--sync-port", "5003", "--peer", "127.0.0.1:5001"],
}
GATEWAY = ["gateway.py", "--host", "127.0.0.1", "--port", os.getenv("GATEWAY_PORT", "8080"),
           "--servers", "127.0.0.1:5000,127.0.0.1:5002"]


def start(label, arguments):
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen([sys.executable, *arguments], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def relay():
        for line in process.stdout:
            print(f"[{label}] {line.decode('utf-8', 'replace').rstrip()}", flush=True)
    threading.Thread(target=relay, daemon=True).start()
    return process


def main():
    processes = {name: start(f"forca-{name}", arguments) for name, arguments in NODES.items()}
    gateway = start("gateway", GATEWAY)
    print(__doc__, flush=True)
    try:
        for line in sys.stdin:
            name = line.strip().lower()
            if name not in NODES:
                continue
            if processes[name].poll() is None:
                processes[name].kill()
                print(f"*** forca-{name} derrubado", flush=True)
            else:
                processes[name] = start(f"forca-{name}", NODES[name])
                print(f"*** forca-{name} religado", flush=True)
        gateway.wait()  # Sem teclado (stdin fechado): segue rodando até Ctrl+C.
    except KeyboardInterrupt:
        pass
    finally:
        for process in [*processes.values(), gateway]:
            process.kill()


if __name__ == "__main__":
    main()
