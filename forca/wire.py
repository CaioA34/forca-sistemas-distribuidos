"""TCP transporta bytes: cada JSON termina com uma quebra de linha."""
import json

MAX_BYTES = 2_000_000


def send(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(data) > MAX_BYTES:
        raise ValueError("Estado grande demais para o limite desta demonstração.")
    stream.write(data)
    stream.flush()


def receive(stream):
    line = stream.readline(MAX_BYTES + 1)
    if not line:
        raise ConnectionError("Conexão encerrada.")
    if len(line) > MAX_BYTES or not line.endswith(b"\n"):
        raise ValueError("Mensagem incompleta ou grande demais.")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("A mensagem deve ser um objeto JSON.")
    return message
