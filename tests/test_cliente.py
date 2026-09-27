"""Enquadramento das mensagens, tela e comandos do cliente."""
import io
from pathlib import Path
import tempfile
import unittest

from cliente import lock, parse
from forca.ui import HELP, outcome, render
from forca.wire import MAX_BYTES, receive, send

STATE = {"room_id": "sala-1", "room_version": 3, "status": "EM_JOGO",
         "players": [{"player_id": "a", "name": "Ana", "errors": 1, "connected": True},
                     {"player_id": "b", "name": "Bruno", "errors": 0, "connected": True}],
         "masked_word": "S____T", "guesses": ["S", "T", "Z"], "wrong_words": ["REDE"],
         "turn": "a", "winner": None, "reason": None, "max_errors": 6}


class WireTests(unittest.TestCase):
    def test_ida_e_volta(self):
        stream = io.BytesIO()
        send(stream, {"type": "PING", "texto": "ação"})
        send(stream, {"type": "ESTADO"})
        stream.seek(0)
        self.assertEqual(receive(stream), {"type": "PING", "texto": "ação"})
        self.assertEqual(receive(stream), {"type": "ESTADO"})
        with self.assertRaises(ConnectionError):
            receive(stream)

    def test_mensagens_invalidas(self):
        for data in (b'{"sem": "quebra"}', b"[1, 2]\n", b"nao e json\n", b"x" * (MAX_BYTES + 2) + b"\n"):
            with self.assertRaises(ValueError):
                receive(io.BytesIO(data))


class ScreenTests(unittest.TestCase):
    def test_estado_nao_lista_comandos(self):
        screen = render(STATE, "a")
        for expected in ("sala-1", "Ana (você)", "Bruno", "S _ _ _ _ T", "S, T, Z", "Chutes errados: REDE",
                         "Erros: 1/6", "Sua vez!"):
            self.assertIn(expected, screen)
        for command in ("/ajuda", "/help", "/estado", "/sair"):
            self.assertNotIn(command, screen)

    def test_sem_sala(self):
        self.assertIn("não está em nenhuma sala", render(None, "a"))

    def test_resultado_do_ponto_de_vista_de_cada_jogador(self):
        def ended(winner, reason):
            return {**STATE, "status": "ENCERRADA", "turn": None, "winner": winner, "reason": reason}
        cases = [("a", "PALAVRA_COMPLETA", "a", "Você venceu! Você completou a palavra."),
                 ("a", "PALAVRA_COMPLETA", "b", "Você perdeu. Ana completou a palavra."),
                 ("b", "SEIS_ERROS", "b", "Você venceu! Ana chegou a seis erros."),
                 ("b", "SEIS_ERROS", "a", "Você perdeu. Você chegou a seis erros."),
                 ("a", "DESISTENCIA", "a", "Você venceu! Bruno desistiu.")]
        for winner, reason, viewer, expected in cases:
            self.assertEqual(outcome(ended(winner, reason), viewer), expected)
            self.assertNotIn(reason, render(ended(winner, reason), viewer))
        self.assertEqual(outcome({**STATE, "winner": None, "reason": "DESISTENCIA"}, "a"), "Partida cancelada.")

    def test_ajuda_lista_apenas_comandos(self):
        for command in ("/chute", "/estado", "/nova", "/sair", "/ajuda", "/help"):
            self.assertIn(command, HELP)
        self.assertNotIn("sala-1", HELP)
        self.assertNotIn("+-----+", HELP)


class ParseTests(unittest.TestCase):
    def test_comandos(self):
        self.assertEqual(parse("a", STATE), {"type": "JOGAR", "letter": "a", "version": 3})
        self.assertEqual(parse("ç", STATE), {"type": "JOGAR", "letter": "ç", "version": 3})
        self.assertEqual(parse("/chute socket", STATE), {"type": "CHUTAR", "word": "socket", "version": 3})
        self.assertEqual(parse("/CHUTE  rede ", STATE), {"type": "CHUTAR", "word": "rede", "version": 3})
        self.assertEqual(parse("/nova", None), {"type": "ENTRAR"})
        self.assertEqual(parse("/sair", STATE), {"type": "SAIR"})

    def test_avisos_locais(self):
        for action in ("/chute", "/chute   ", "/xyz", "ab"):
            self.assertIsInstance(parse(action, STATE), str)


class SessionLockTests(unittest.TestCase):
    def test_segundo_cliente_com_a_mesma_sessao_e_recusado(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ana.json"
            first = lock(path)
            self.assertIsNotNone(first)
            self.assertIsNone(lock(path))
            first.close()
            second = lock(path)
            self.assertIsNotNone(second)
            second.close()


if __name__ == "__main__":
    unittest.main()
