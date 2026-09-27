"""Regras de uma partida: independentes da rede e da replicação."""
from dataclasses import asdict, dataclass, field
import re
import unicodedata

FINISHED = {"ENCERRADA", "CANCELADA"}
MAX_ERRORS = 6
MAX_WORD = 30  # O estado inteiro é replicado a cada jogada; chutes longos não fazem sentido.


class GameError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize(text: str) -> str:
    """Maiúsculas sem acentos: 'ç' vira 'C' e 'CONEXÃO' vira 'CONEXAO'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def load_words(lines) -> list[str]:
    """Normaliza a lista de palavras e recusa, já na partida do servidor, o que não for só letras."""
    words = [normalize(line.strip()) for line in lines if line.strip()]
    invalid = [w for w in words if not re.fullmatch(rf"[A-Z]{{1,{MAX_WORD}}}", w)]
    if invalid:
        raise ValueError(f"use só letras, até {MAX_WORD} por palavra, sem espaços ou hífens: "
                         + ", ".join(invalid))
    if not words:
        raise ValueError("a lista está vazia.")
    return words


@dataclass
class Player:
    id: str
    name: str
    token_hash: str
    room_id: str | None = None
    active: bool = True  # Só jogadores ativos reservam o nome; /sair libera.


@dataclass
class Room:
    id: str
    players: list[str] = field(default_factory=list)
    word: str = ""
    guesses: list[str] = field(default_factory=list)
    wrong_words: list[str] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)
    turn: str | None = None
    status: str = "AGUARDANDO"
    version: int = 1
    winner: str | None = None
    reason: str | None = None

    def start(self, word: str):
        if len(self.players) != 2 or self.status != "AGUARDANDO":
            raise GameError("SALA_INVALIDA", "A sala precisa de dois jogadores para começar.")
        if not re.fullmatch(r"[A-Z]+", word):
            raise ValueError("A palavra deve conter apenas A a Z.")
        self.word = word
        self.errors = {p: 0 for p in self.players}
        self.turn = self.players[0]
        self.status = "EM_JOGO"

    def guess(self, player_id: str, letter, expected_version) -> bool:
        self.check_turn(player_id, expected_version)
        if not isinstance(letter, str) or not re.fullmatch(r"[A-Z]", normalize(letter)):
            raise GameError("LETRA_INVALIDA", "Digite uma única letra de A a Z.")
        letter = normalize(letter)
        if letter in self.guesses:
            raise GameError("LETRA_REPETIDA", "Essa letra já foi tentada na sala.")
        self.guesses.append(letter)
        hit = letter in self.word
        self.conclude(player_id, hit, solved=set(self.word) <= set(self.guesses))
        return hit

    def guess_word(self, player_id: str, word, expected_version) -> bool:
        """Chute da palavra inteira: acerto vence; erro custa um membro e passa a vez."""
        self.check_turn(player_id, expected_version)
        if not isinstance(word, str) or not re.fullmatch(rf"[A-Z]{{1,{MAX_WORD}}}", normalize(word.strip())):
            raise GameError("PALAVRA_INVALIDA", f"Chute uma única palavra de até {MAX_WORD} letras, sem espaços.")
        word = normalize(word.strip())
        if word in self.wrong_words:
            raise GameError("PALAVRA_REPETIDA", "Essa palavra já foi chutada na sala.")
        hit = word == self.word
        if not hit:
            self.wrong_words.append(word)
        self.conclude(player_id, hit, solved=hit)
        return hit

    def check_turn(self, player_id: str, expected_version):
        if player_id not in self.players:
            raise GameError("NAO_PARTICIPANTE", "Você não participa desta sala.")
        if self.status != "EM_JOGO":
            raise GameError("PARTIDA_INDISPONIVEL", "A partida ainda não começou, está pausada ou terminou.")
        if self.turn != player_id:
            raise GameError("FORA_DA_VEZ", "Aguarde a sua vez.")
        if type(expected_version) is not int or expected_version != self.version:
            raise GameError("ESTADO_DESATUALIZADO", "A sala mudou. Confira o estado atual e tente novamente.")

    def conclude(self, player_id: str, hit: bool, solved: bool):
        if not hit:
            self.errors[player_id] += 1
        opponent = next(p for p in self.players if p != player_id)
        if solved:
            self.finish(player_id, "PALAVRA_COMPLETA")
        elif self.errors[player_id] >= MAX_ERRORS:
            self.finish(opponent, "SEIS_ERROS")
        else:
            self.turn = opponent
        self.version += 1

    def finish(self, winner: str | None, reason: str):
        self.status = "ENCERRADA" if winner else "CANCELADA"
        self.winner = winner
        self.reason = reason
        self.turn = None

    def public(self, players: dict[str, Player], online: set[str]) -> dict:
        return {
            "room_id": self.id, "room_version": self.version,
            "status": self.status,
            "players": [{"player_id": pid, "name": players[pid].name,
                         "errors": self.errors.get(pid, 0), "connected": pid in online}
                        for pid in self.players],
            "masked_word": "".join(c if c in self.guesses or self.status in FINISHED else "_"
                                   for c in self.word),
            "guesses": list(self.guesses), "wrong_words": list(self.wrong_words), "turn": self.turn,
            "winner": self.winner, "reason": self.reason, "max_errors": MAX_ERRORS,
        }


@dataclass
class World:
    deployment_id: str
    players: dict[str, Player] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)
    next_room: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(deployment_id=data["deployment_id"],
                   players={k: Player(**v) for k, v in data["players"].items()},
                   rooms={k: Room(**v) for k, v in data["rooms"].items()},
                   next_room=data["next_room"])

