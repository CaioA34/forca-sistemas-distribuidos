"""Salas, sessões, nomes únicos e reenvios."""
import unittest
import uuid

from forca.lobby import apply, new_state, player_id, public_state

WORDS = ["SOCKET"]


def token(name):
    return (name + "-token-").ljust(40, "x")


class Lobby:
    """Estado de um servidor sem rede; todos os jogadores criados estão online."""

    def __init__(self):
        self.state = new_state()
        self.online = set()
        self.idle = set()

    def send(self, who, kind, request_id=None, **fields):
        self.online.add(player_id(token(who)))
        command = {"type": kind, "token": token(who),
                   "request_id": request_id or str(uuid.uuid4()), **fields}
        return apply(self.state, command, self.online, WORDS, self.idle)

    def enter(self, who, display=None):
        return self.send(who, "ENTRAR", name=who if display is None else display)

    def view(self, who):
        return public_state(self.state, player_id(token(who)), self.online)


class RoomTests(unittest.TestCase):
    def test_salas_sao_formadas_em_ordem(self):
        lobby = Lobby()
        messages = [lobby.enter(n)["message"] for n in ("Ana", "Bruno", "Caio", "Dani", "Edu")]
        self.assertEqual(messages, ["Você está na sala-1.", "Você está na sala-1.", "Você está na sala-2.",
                                    "Você está na sala-2.", "Você está na sala-3."])
        self.assertEqual(lobby.view("Ana")["status"], "EM_JOGO")
        self.assertEqual(lobby.view("Edu")["status"], "AGUARDANDO")
        self.assertEqual(len(lobby.view("Caio")["players"]), 2)

    def test_entrar_de_novo_mantem_a_sala(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        self.assertEqual(lobby.enter("Ana")["message"], "Você já está em uma partida na sala-1. Use /sair para desistir.")
        self.assertEqual(lobby.view("Ana")["room_version"], lobby.view("Bruno")["room_version"])

    def test_quem_espera_sozinho_continua_na_sala(self):
        lobby = Lobby()
        lobby.enter("Ana")
        self.assertEqual(lobby.enter("Ana")["message"], "Você continua aguardando na sala-1.")

    def test_dois_esperando_em_salas_separadas_se_juntam(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.online.discard(player_id(token("Ana")))  # Ana cai; Bruno não a encontra e abre outra sala.
        self.assertEqual(lobby.enter("Bruno")["message"], "Você está na sala-2.")
        self.assertEqual(lobby.enter("Ana")["message"], "Você está na sala-2.")  # Ana volta e se junta.
        view = lobby.view("Ana")
        self.assertEqual((view["room_id"], view["status"]), ("sala-2", "EM_JOGO"))
        self.assertEqual(lobby.state["world"]["rooms"]["sala-1"]["status"], "CANCELADA")

    def test_jogador_ausente_pausa_a_partida(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        lobby.online.discard(player_id(token("Bruno")))
        self.assertEqual(lobby.view("Ana")["status"], "PAUSADA")
        state = lobby.view("Ana")
        result = lobby.send("Ana", "JOGAR", letter="S", version=state["room_version"])
        self.assertEqual(result["code"], "PAUSADA")

    def test_sair_na_espera_cancela_e_na_partida_da_vitoria(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.send("Ana", "SAIR")
        lobby.enter("Bruno")
        lobby.enter("Caio")
        lobby.send("Bruno", "SAIR")
        self.assertIsNone(lobby.view("Ana"))
        view = lobby.view("Caio")
        self.assertEqual((view["status"], view["reason"]), ("ENCERRADA", "DESISTENCIA"))
        self.assertEqual(view["winner"], player_id(token("Caio")))
        self.assertEqual(view["masked_word"], "SOCKET")

    def test_chutar_pelo_lobby(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        version = lobby.view("Ana")["room_version"]
        wrong = lobby.send("Ana", "CHUTAR", word="REDE", version=version)
        self.assertTrue(wrong["ok"])
        self.assertIn("não coincide", wrong["message"])
        right = lobby.send("Bruno", "CHUTAR", word="socket", version=version + 1)
        self.assertEqual(right["message"], "Acertou a palavra!")
        view = lobby.view("Ana")
        self.assertEqual((view["status"], view["reason"]), ("ENCERRADA", "PALAVRA_COMPLETA"))
        self.assertEqual([p["errors"] for p in view["players"]], [1, 0])


class UniqueNameTests(unittest.TestCase):
    def test_nome_repetido_e_recusado_em_qualquer_sala(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        self.assertEqual(lobby.enter("ana2", "ana")["code"], "NOME_EM_USO")
        lobby.enter("Bruno")  # Sala 1 começa; a regra continua valendo para a sala 2.
        self.assertEqual(lobby.enter("ana3", "  ANA ")["code"], "NOME_EM_USO")
        self.assertIsNone(lobby.view("ana2"))
        self.assertEqual(len(lobby.view("ana1")["players"]), 2)

    def test_mesmo_jogador_pode_reentrar_com_seu_nome(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        self.assertTrue(lobby.enter("ana1", "Ana")["ok"])

    def test_sair_libera_o_nome(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.send("ana1", "SAIR")
        self.assertTrue(lobby.enter("ana2", "Ana")["ok"])
        self.assertEqual(lobby.enter("ana1", "Ana")["code"], "NOME_EM_USO")

    def test_nome_de_quem_sumiu_fora_de_partida_e_liberado(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.online.discard(player_id(token("ana1")))
        lobby.idle.add(player_id(token("ana1")))
        self.assertEqual(lobby.enter("ana2", "Ana")["message"], "Você está na sala-2.")
        self.assertIsNone(lobby.view("ana1"))
        self.assertEqual(lobby.state["world"]["rooms"]["sala-1"]["status"], "CANCELADA")
        self.assertEqual(lobby.enter("ana1", "Ana")["code"], "NOME_EM_USO")

    def test_nome_de_quem_esta_em_partida_nao_e_liberado(self):
        lobby = Lobby()
        lobby.enter("ana1", "Ana")
        lobby.enter("Bruno")
        lobby.idle.add(player_id(token("ana1")))
        self.assertEqual(lobby.enter("ana2", "Ana")["code"], "NOME_EM_USO")

    def test_nome_invalido(self):
        lobby = Lobby()
        for name in ("", "   ", "x" * 25, "Ana\n"):
            self.assertEqual(lobby.enter("p", name)["code"], "NOME_INVALIDO")


class ResendTests(unittest.TestCase):
    def test_reenvio_devolve_o_mesmo_resultado_sem_repetir(self):
        lobby = Lobby()
        lobby.enter("Ana")
        lobby.enter("Bruno")
        version = lobby.view("Ana")["room_version"]
        request_id = str(uuid.uuid4())
        first = lobby.send("Ana", "JOGAR", request_id, letter="Z", version=version)
        again = lobby.send("Ana", "JOGAR", request_id, letter="Z", version=version)
        self.assertEqual(first, again)
        self.assertEqual(lobby.view("Ana")["players"][0]["errors"], 1)
        self.assertEqual(lobby.view("Ana")["room_version"], version + 1)

    def test_mesmo_identificador_com_outro_conteudo(self):
        lobby = Lobby()
        request_id = str(uuid.uuid4())
        lobby.send("Ana", "ENTRAR", request_id, name="Ana")
        with self.assertRaises(ValueError):
            lobby.send("Ana", "ENTRAR", request_id, name="Outra")

    def test_token_e_identificador_invalidos(self):
        with self.assertRaises(ValueError):
            player_id("curto")
        for request_id in ("nao-e-uuid", 5, ["lista"]):
            with self.assertRaises(ValueError):
                Lobby().send("Ana", "ENTRAR", request_id, name="Ana")

    def test_recibos_nao_crescem_com_comandos_rejeitados(self):
        lobby = Lobby()
        lobby.enter("Ana")
        for i in range(200):
            lobby.send("Ana", "JOGAR", letter="1", version=0)
            lobby.send(f"intruso{i}", "JOGAR", letter="A", version=0)  # Nunca entrou: nada a guardar.
        self.assertEqual(len(lobby.state["receipts"]), 1)
        self.assertEqual(lobby.state["revision"], 401)


if __name__ == "__main__":
    unittest.main()
