"""Regras de uma partida, sem rede."""
import unittest

from forca.game import GameError, Room, load_words, normalize


def started(word="SOCKET"):
    room = Room("sala-1", players=["ana", "bruno"])
    room.start(word)
    return room


class LetterTests(unittest.TestCase):
    def test_primeiro_a_entrar_comeca(self):
        self.assertEqual(started().turn, "ana")

    def test_fora_da_vez_nao_altera_a_sala(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess("bruno", "S", room.version)
        self.assertEqual(error.exception.code, "FORA_DA_VEZ")
        self.assertEqual((room.turn, room.guesses), ("ana", []))

    def test_versao_desatualizada(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess("ana", "S", room.version - 1)
        self.assertEqual(error.exception.code, "ESTADO_DESATUALIZADO")

    def test_letra_invalida_e_repetida_nao_passam_a_vez(self):
        room = started()
        for letter in ("", "AB", "1", "-", None):
            with self.assertRaises(GameError) as error:
                room.guess("ana", letter, room.version)
            self.assertEqual(error.exception.code, "LETRA_INVALIDA")
        room.guess("ana", "s", room.version)
        with self.assertRaises(GameError) as error:
            room.guess("bruno", "S", room.version)
        self.assertEqual(error.exception.code, "LETRA_REPETIDA")
        self.assertEqual(room.turn, "bruno")

    def test_letra_com_acento_vale_como_letra_sem_acento(self):
        room = started("CONEXAO")
        self.assertTrue(room.guess("ana", "ç", room.version))
        self.assertTrue(room.guess("bruno", "Ã", room.version))
        self.assertEqual(room.guesses, ["C", "A"])

    def test_erro_conta_so_para_o_autor_e_passa_a_vez(self):
        room = started()
        self.assertFalse(room.guess("ana", "Z", room.version))
        self.assertEqual(room.errors, {"ana": 1, "bruno": 0})
        self.assertEqual(room.turn, "bruno")

    def test_completar_a_palavra_vence(self):
        room = started("REDE")
        for player, letter in (("ana", "R"), ("bruno", "E"), ("ana", "D")):
            room.guess(player, letter, room.version)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "ana", "PALAVRA_COMPLETA"))

    def test_seis_erros_da_vitoria_ao_adversario(self):
        room = started()
        for ana, bruno in zip("ABDFGH", "IJLMNP"):
            room.guess("ana", ana, room.version)
            if room.status == "EM_JOGO":
                room.guess("bruno", bruno, room.version)
        self.assertEqual(room.errors["ana"], 6)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "bruno", "SEIS_ERROS"))


class WordGuessTests(unittest.TestCase):
    def test_chute_certo_vence_com_palavra_completa(self):
        room = started()
        self.assertTrue(room.guess_word("ana", " socket ", room.version))
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "ana", "PALAVRA_COMPLETA"))
        self.assertEqual(room.errors["ana"], 0)

    def test_chute_errado_custa_um_erro_e_passa_a_vez(self):
        room = started()
        version = room.version
        self.assertFalse(room.guess_word("ana", "SERVIDOR", version))
        self.assertEqual(room.errors, {"ana": 1, "bruno": 0})
        self.assertEqual((room.turn, room.status, room.version), ("bruno", "EM_JOGO", version + 1))
        self.assertEqual(room.wrong_words, ["SERVIDOR"])

    def test_chute_repetido_ou_invalido_nao_penaliza(self):
        room = started()
        room.guess_word("ana", "REDE", room.version)
        with self.assertRaises(GameError) as error:
            room.guess_word("bruno", "rede", room.version)
        self.assertEqual(error.exception.code, "PALAVRA_REPETIDA")
        for word in ("", "   ", "DUAS PALAVRAS", "GUARDA-CHUVA", "X" * 31, 42):
            with self.assertRaises(GameError) as error:
                room.guess_word("bruno", word, room.version)
            self.assertEqual(error.exception.code, "PALAVRA_INVALIDA")
        self.assertEqual((room.errors["bruno"], room.turn), (0, "bruno"))

    def test_chute_com_acento_acerta_palavra_sem_acento(self):
        room = started("CONEXAO")
        self.assertTrue(room.guess_word("ana", "conexão", room.version))
        self.assertEqual(room.reason, "PALAVRA_COMPLETA")

    def test_chute_fora_da_vez(self):
        room = started()
        with self.assertRaises(GameError) as error:
            room.guess_word("bruno", "SOCKET", room.version)
        self.assertEqual(error.exception.code, "FORA_DA_VEZ")

    def test_sexto_erro_em_chute_encerra(self):
        room = started()
        room.errors["ana"] = 5
        room.guess_word("ana", "REDE", room.version)
        self.assertEqual((room.status, room.winner, room.reason), ("ENCERRADA", "bruno", "SEIS_ERROS"))

    def test_estado_publico_mostra_chutes_e_esconde_palavra(self):
        from forca.game import Player
        room = started()
        room.guess_word("ana", "REDE", room.version)
        players = {p: Player(p, p.title(), p) for p in room.players}
        public = room.public(players, {"ana", "bruno"})
        self.assertEqual(public["wrong_words"], ["REDE"])
        self.assertEqual(public["masked_word"], "______")


class WordListTests(unittest.TestCase):
    def test_normaliza_acentos_e_maiusculas(self):
        self.assertEqual(normalize("Coração"), "CORACAO")
        self.assertEqual(load_words(["  socket ", "", "coração", "Conexão"]), ["SOCKET", "CORACAO", "CONEXAO"])

    def test_recusa_palavras_que_nao_sao_so_letras(self):
        for lines in (["BOA NOITE"], ["GUARDA-CHUVA"], ["SALA1"], ["X" * 31], [], ["", "  "]):
            with self.assertRaises(ValueError):
                load_words(lines)

    def test_lista_do_projeto_e_valida(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "forca" / "words.txt"
        self.assertTrue(load_words(path.read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
