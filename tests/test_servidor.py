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
from forca.lobby import NAME_HOLD, apply, new_state, player_id
from forca.wire import receive, send
from servidor import BACKUP, JOINING, PRIMARY, Server

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def exchange(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.settimeout(10)
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

    def start(self, name, peer_sync=None, extra=()):
        game, sync = self.ports[name]
        other = next(n for n in self.ports if n != name)
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen(
            [sys.executable, "servidor.py", "--node", name, "--host", "127.0.0.1",
             "--port", str(game), "--sync-port", str(sync),
             "--peer", f"127.0.0.1:{peer_sync or self.ports[other][1]}",
             "--boot-wait", "3", "--solo-wait", "2", *extra],  # Esperas curtas para o teste não demorar.
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
        # Ao iniciar, o nó primeiro procura o outro; enquanto procura, não atende.
        self.assertEqual(ping(self.game("forca-a"))["role"], JOINING)
        self.assertTrue(exchange(self.game("forca-a"), command("Ana", "ENTRAR", name="Ana")).get("retry"))
        self.b = self.start("forca-b")
        wait_for(lambda: serving(self.game("forca-a")))  # Os dois entrando: o de nome menor cria o jogo.
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

    def test_primario_segue_sozinho_sem_o_reserva_e_o_aceita_de_volta(self):
        a, b = self.game("forca-a"), self.game("forca-b")
        state = self.start_match(a)
        before = self.snapshot(a)
        self.stop(self.b)
        # Pausa curta: se fosse só a rede, o reserva teria assumido nesse intervalo.
        wait_for(lambda: "retry" in exchange(a, command("Ana", "ESTADO")))
        self.assertEqual(ping(a)["role"], PRIMARY)
        wait_for(lambda: serving(a))
        self.assertEqual(self.snapshot(a), before)
        # Uma jogada confirmada com uma cópia só.
        self.assertTrue(exchange(a, command("Ana", "JOGAR", letter="Z", version=state["room_version"]))["ok"])
        after = self.snapshot(a)
        # O reserva reinicia vazio, recebe o jogo com a jogada e pode assumir.
        self.b = self.start("forca-b")
        self.assertEqual(wait_for(lambda: ping(b)["role"] == BACKUP and "ok"), "ok")
        log = self.stop(self.a)
        wait_for(lambda: serving(b))
        self.assertEqual(self.snapshot(b), after)
        self.assertIn("primário pausado", log.lower())
        self.assertIn("segue atendendo sozinho", log)
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


class LoneNodeTests(Processes):
    def test_um_no_sozinho_atende_e_o_outro_entra_como_reserva(self):
        a, b = self.game("forca-a"), self.game("forca-b")
        self.b = self.start("forca-b")  # O de nome maior, para não depender do desempate por nome.
        wait_for(lambda: ping(b))
        self.assertEqual(ping(b)["role"], JOINING)
        wait_for(lambda: serving(b))  # Ninguém respondeu: cria o jogo e atende sem segunda cópia.
        self.assertTrue(exchange(b, command("Ana", "ENTRAR", name="Ana"))["ok"])
        before = exchange(b, command("Ana", "ESTADO"))["state"]

        self.a = self.start("forca-a")
        self.assertEqual(wait_for(lambda: ping(a)["role"] == BACKUP and "ok"), "ok")
        log = self.stop(self.b)
        wait_for(lambda: serving(a))  # A cópia chegou ao outro nó: ele assume com a jogadora.
        self.assertEqual(exchange(a, command("Ana", "ESTADO"))["state"], before)
        self.assertIn("cria um jogo novo", log)
        self.assertNotIn("Traceback", log)


    def test_chaves_diferentes_avisam_no_log(self):
        a, b = self.game("forca-a"), self.game("forca-b")
        self.a = self.start("forca-a", extra=("--key", "uma-chave"))
        self.b = self.start("forca-b", extra=("--key", "outra-chave"))
        wait_for(lambda: serving(a) and serving(b))  # Sem se entender, cada um cria o próprio jogo.
        logs = self.stop(self.a) + self.stop(self.b)
        self.assertIn("REPLICATION_KEY precisa ser igual nos dois nós", logs)
        self.assertIn("apresentou uma chave de replicação diferente", logs)
        self.assertIn("fechou a conexão sem responder", logs)
        self.assertNotIn("Traceback", logs)


class InitialSyncTests(Processes):
    def test_chave_com_acento_e_reserva_que_some_nao_travam_o_primario(self):
        self.a, self.b = self.start("forca-a"), self.start("forca-b")
        a, sync = self.game("forca-a"), self.ports["forca-a"][1]
        wait_for(lambda: ping(self.game("forca-b"))["role"] == BACKUP)
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
        wait_for(lambda: ping(self.game("forca-b"))["role"] == BACKUP)
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

    def node(self, name, peer_sync, role, state=None, hold=0.0):
        server = Server(name, f"127.0.0.1:{peer_sync}", "127.0.0.1", free_port(), free_port())
        server.role, server.state, server.hold_until = role, state, hold
        return server

    def pair(self, state_a, state_b):
        """Dois primários sem reserva que acabam de voltar a se enxergar."""
        b = self.node("forca-b", 0, PRIMARY, state=state_b)
        a = self.node("forca-a", b.sync_port, PRIMARY, state=state_a)
        b.peer = f"127.0.0.1:{a.sync_port}"
        for server in (a, b):
            threading.Thread(target=server.run, daemon=True).start()
        return a, b

    def test_dois_primarios_o_que_assumiu_e_jogou_fica(self):
        # Rede entre os nós caiu: o reserva assumiu (época 2) e recebeu jogadas; o antigo ficou parado.
        old, promoted = new_state(), new_state()
        promoted["epoch"], promoted["revision"] = 2, 7
        a, b = self.pair(old, promoted)
        wait_for(lambda: a.role == BACKUP)
        self.assertEqual(a.state["revision"], 7)
        wait_for(lambda: b.backup is not None)
        self.assertTrue(b.serving)

    def test_dois_primarios_vale_quem_confirmou_mais_jogadas_nao_a_epoca(self):
        # O reserva ficou isolado de tudo e se promoveu (época 2) sem receber ninguém; o antigo
        # primário continuou atendendo os jogadores. Quem cede é o isolado.
        busy, isolated = new_state(), new_state()
        busy["revision"] = 5
        isolated["epoch"], isolated["revision"] = 2, 2
        a, b = self.pair(busy, isolated)
        wait_for(lambda: b.role == BACKUP)
        self.assertEqual((b.state["revision"], a.role), (5, PRIMARY))
        wait_for(lambda: a.backup is not None)

    def test_dois_jogos_novos_empatados_fica_o_de_nome_menor(self):
        a, b = self.pair(new_state(), new_state())
        wait_for(lambda: b.role == BACKUP)
        self.assertEqual(b.state["world"]["deployment_id"], a.state["world"]["deployment_id"])
        self.assertEqual(a.role, PRIMARY)

    def test_pausa_longa_nao_faz_quem_ficou_parecer_sumido(self):
        # Ana espera na sala-1. O primário fica pausado por mais de NAME_HOLD s (sem reserva) e,
        # pausado, não registra presença. Ao voltar a atender, Ana não pode perder a sala.
        state = new_state()
        apply(state, command("Ana", "ENTRAR", name="Ana"), {player_id(token("Ana"))}, ["SOCKET"])
        b = self.node("forca-b", 0, JOINING)
        a = self.node("forca-a", b.sync_port, PRIMARY, state=state, hold=time.monotonic() + 1000)
        a.since = time.monotonic() - 10 * NAME_HOLD
        b.peer = f"127.0.0.1:{a.sync_port}"
        for server in (a, b):
            threading.Thread(target=server.run, daemon=True).start()
        wait_for(lambda: a.serving)
        self.assertTrue(a.request(command("Bruno", "ENTRAR", name="Bruno"))["ok"])
        view = a.request({"type": "ESTADO", "token": token("Ana")})["state"]
        self.assertEqual((view["room_id"], view["status"]), ("sala-1", "AGUARDANDO"))

    def match(self, wait=0.6):
        """Primário sozinho com Ana e Bruno em partida; devolve o servidor e uma função de consulta."""
        server = self.node("forca-a", 0, PRIMARY, state=new_state())
        server.abandon_wait = wait
        for who in ("Ana", "Bruno"):
            server.request(command(who, "ESTADO"))
            self.assertTrue(server.request(command(who, "ENTRAR", name=who))["ok"])

        def view(who):
            return server.request({"type": "ESTADO", "token": token(who)})["state"]
        self.assertEqual(view("Ana")["status"], "EM_JOGO")
        return server, view

    def test_adversario_que_nao_volta_perde_por_abandono(self):
        server, view = self.match()
        revision = server.state["revision"]
        limit = time.monotonic() + 0.4
        while time.monotonic() < limit:  # Ana segue consultando; Bruno parou. Ainda dentro do prazo.
            self.assertEqual(view("Ana")["winner"], None)
            time.sleep(0.05)
        self.assertEqual(server.state["revision"], revision)
        state = wait_for(lambda: (s := view("Ana"))["status"] == "ENCERRADA" and s, seconds=3)
        self.assertEqual((state["reason"], state["winner"]), ("ABANDONO", player_id(token("Ana"))))
        self.assertEqual(server.state["revision"], revision + 1)  # Uma alteração só, como qualquer jogada.
        self.assertEqual(view("Bruno")["winner"], player_id(token("Ana")))  # Bruno volta e vê que perdeu.
        self.assertEqual(server.state["revision"], revision + 1)

    def test_quem_tambem_esteve_fora_nao_vence_ao_voltar(self):
        server, view = self.match()
        long_ago = time.monotonic() - 100  # Os dois sumiram; Ana volta primeiro.
        for who in ("Ana", "Bruno"):
            server.seen[player_id(token(who))] = server.present[player_id(token(who))] = long_ago
        self.assertEqual(view("Ana")["winner"], None)   # O prazo de Bruno começa quando Ana volta.
        self.assertEqual(view("Bruno")["winner"], None)
        time.sleep(0.2)
        view("Bruno")
        self.assertEqual(view("Ana")["status"], "EM_JOGO")

    def test_troca_de_servidor_nao_da_vitoria_a_ninguem(self):
        server, view = self.match()
        time.sleep(0.8)  # Passou do prazo sem ninguém consultar: o nó esteve fora do ar para os dois.
        server.forget_presence()  # É o que a promoção e a retomada fazem.
        self.assertEqual(view("Ana")["winner"], None)
        self.assertEqual(view("Bruno")["winner"], None)

    def test_estado_grande_demais_recusa_o_comando_sem_pausar(self):
        server = self.node("forca-a", 0, PRIMARY, state=new_state())
        limit = forca.wire.MAX_BYTES
        forca.wire.MAX_BYTES = 300
        self.addCleanup(setattr, forca.wire, "MAX_BYTES", limit)
        result = server.request(command("Ana", "ENTRAR", name="Ana"))
        self.assertEqual(result["code"], "ESTADO_CHEIO")
        self.assertEqual(server.state["revision"], 0)
        self.assertTrue(server.serving)

    def test_requisicao_que_espera_demais_pela_trava_nao_e_aplicada(self):
        server = self.node("forca-a", 0, PRIMARY, state=new_state())
        with server.lock:
            result = server.request(command("Ana", "ENTRAR", name="Ana"))
        self.assertTrue(result["retry"])
        self.assertEqual(server.state["revision"], 0)


if __name__ == "__main__":
    unittest.main()
