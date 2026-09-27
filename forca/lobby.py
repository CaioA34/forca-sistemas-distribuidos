"""Salas e sessões. Não abre sockets: o servidor replica o resultado destas regras."""
import hashlib
import random
import uuid

from .game import FINISHED, GameError, Player, Room, World

NAME_HOLD = 180  # Segundos sem consultar até o nome de quem não está em partida poder ser reaproveitado.


def player_id(token):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        raise ValueError("Token de sessão inválido.")
    return hashlib.sha256(token.encode()).hexdigest()


def new_state():
    return {"world": World(str(uuid.uuid4())).to_dict(), "receipts": {}, "revision": 0}


def public_state(state, pid, online):
    world = World.from_dict(state["world"])
    player = world.players.get(pid)
    room = world.rooms.get(player.room_id) if player else None
    result = room.public(world.players, online) if room else None
    if result and room.status == "EM_JOGO" and not set(room.players) <= online:
        result["status"] = "PAUSADA"
    return result


def claim_name(world, pid, name, idle):
    """Recusa nome em uso. Quem sumiu há NAME_HOLD segundos e não está em partida perde o nome."""
    for other in world.players.values():
        if other.id == pid or not other.active or other.name.casefold() != name.casefold():
            continue
        room = world.rooms.get(other.room_id)
        if other.id not in idle or (room and room.status == "EM_JOGO"):
            raise GameError("NOME_EM_USO", f"O nome {name} já está em uso. Escolha outro nome.")
        if room and room.status == "AGUARDANDO":
            room.finish(None, "ABANDONO")
            room.version += 1
        other.room_id, other.active = None, False


def enter(world, player, online, words):
    """Coloca o jogador em uma sala e devolve a mensagem de resposta."""
    room = world.rooms.get(player.room_id)
    if room and room.status == "EM_JOGO":
        return f"Você já está em uma partida na {room.id}. Use /sair para desistir."
    waiting = room is not None and room.status == "AGUARDANDO"
    partner = next((r for r in world.rooms.values()
                    if r is not room and r.status == "AGUARDANDO" and len(r.players) == 1
                    and r.players[0] in online), None)
    if waiting and partner is None:
        return f"Você continua aguardando na {room.id}."
    if waiting:  # Dois jogadores esperando em salas separadas: junta os dois na sala do outro.
        room.finish(None, "REAGRUPADA")
        room.version += 1
    room = partner
    if room is None:
        room = Room(f"sala-{world.next_room}")
        world.next_room += 1
        world.rooms[room.id] = room
    room.players.append(player.id)
    room.errors[player.id] = 0
    player.room_id = room.id
    if len(room.players) == 2:
        room.start(random.choice(words))
    room.version += 1
    return f"Você está na {room.id}."


def apply(state, command, online, words, idle=frozenset()):
    """Modifica uma cópia do estado. Reenvios devolvem o resultado já registrado.

    online: jogadores que consultaram nos últimos segundos.
    idle: jogadores sem consultar há NAME_HOLD segundos, cujo nome pode ser liberado.
    """
    pid = player_id(command.get("token"))
    request_id = command.get("request_id")
    if not isinstance(request_id, str):
        raise ValueError("request_id deve ser um UUID em texto.")
    request_id = str(uuid.UUID(request_id))
    fingerprint = hashlib.sha256(str(sorted(command.items())).encode()).hexdigest()
    previous = state["receipts"].get(pid)
    if previous and previous["request_id"] == request_id:
        if previous["fingerprint"] != fingerprint:
            raise ValueError("Identificador reutilizado para outro comando.")
        return previous["result"]

    world = World.from_dict(state["world"])
    kind = command.get("type")
    try:
        if kind == "ENTRAR":
            name = command.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24 or not name.isprintable():
                raise GameError("NOME_INVALIDO", "Use um nome de 1 a 24 caracteres.")
            name = name.strip()
            player = world.players.get(pid)
            if player is None or not player.active:
                # Nomes são únicos entre jogadores ativos de todas as salas, sem diferenciar maiúsculas.
                claim_name(world, pid, name, idle)
                player = world.players.setdefault(pid, Player(pid, name, pid))
                player.name, player.active = name, True
            result = {"ok": True, "message": enter(world, player, online, words)}
        elif kind in {"JOGAR", "CHUTAR"}:
            player = world.players.get(pid)
            room = world.rooms.get(player.room_id) if player else None
            if room is None:
                raise GameError("SEM_SALA", "Entre em uma sala com /nova.")
            if not set(room.players) <= online:
                raise GameError("PAUSADA", "Aguardando o outro jogador reconectar.")
            if kind == "JOGAR":
                hit = room.guess(pid, command.get("letter"), command.get("version"))
                result = {"ok": True, "message": "Acertou!" if hit else "Errou!"}
            else:
                hit = room.guess_word(pid, command.get("word"), command.get("version"))
                result = {"ok": True, "message": "Acertou a palavra!" if hit
                          else "A palavra não coincide. Você perdeu um membro e a vez passou."}
        elif kind == "SAIR":
            player = world.players.get(pid)
            if player is None or not player.active:
                raise GameError("SEM_SALA", "Você não está em nenhuma sala.")
            room = world.rooms.get(player.room_id)
            if room and room.status not in FINISHED:
                opponent = next((p for p in room.players if p != pid), None)
                room.finish(opponent, "DESISTENCIA")
                room.version += 1
            player.room_id, player.active = None, False
            result = {"ok": True, "message": "Você saiu."}
        else:
            raise GameError("COMANDO_INVALIDO", "Comando desconhecido.")
    except GameError as exc:
        result = {"ok": False, "message": str(exc), "code": exc.code}
    state["world"] = world.to_dict()
    if pid in world.players:
        # O cliente tem um único comando pendente por vez: basta o último recibo de cada jogador.
        # Comandos de quem nunca entrou não mudam nada e não ocupam espaço no estado replicado.
        state["receipts"][pid] = {"request_id": request_id, "fingerprint": fingerprint, "result": result}
    state["revision"] += 1
    return result
