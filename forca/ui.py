"""Apresentação textual: os dois bonecos são desenhados em toda atualização."""

HELP = "\n".join([
    "Comandos:",
    "  <letra>            Tenta uma letra na sua vez",
    "  /chute <palavra>   Tenta adivinhar a palavra inteira na sua vez",
    "  /estado            Mostra a partida: forcas, palavra e letras tentadas",
    "  /nova              Entra em uma nova partida depois que a atual termina",
    "  /sair              Desiste da partida e fecha o cliente",
    "  /ajuda ou /help    Mostra esta lista",
    "  Ctrl+C             Fecha o cliente e guarda a sessão para retomar depois",
])


def gallows(errors):
    head = "O" if errors >= 1 else " "
    trunk = "|" if errors >= 2 else " "
    left = "/" if errors >= 3 else " "
    right = "\\" if errors >= 4 else " "
    leg_left = "/" if errors >= 5 else " "
    leg_right = "\\" if errors >= 6 else " "
    return ["  +-----+", "  |     |", f"  {head}     |", f" {left}{trunk}{right}    |",
            f" {leg_left} {leg_right}    |", "        |", "  ========"]


def outcome(state, player_id):
    """Resultado do ponto de vista de quem olha, sem os códigos internos do protocolo."""
    winner = state["winner"]
    if winner is None:
        return "Partida cancelada."
    names = {p["player_id"]: p["name"] for p in state["players"]}
    loser = next(pid for pid in names if pid != winner)
    if winner == player_id:
        details = {"PALAVRA_COMPLETA": "Você completou a palavra.",
                   "SEIS_ERROS": f"{names[loser]} chegou a seis erros.",
                   "DESISTENCIA": f"{names[loser]} desistiu."}
        return "Você venceu! " + details.get(state["reason"], "")
    details = {"PALAVRA_COMPLETA": f"{names[winner]} completou a palavra.",
               "SEIS_ERROS": "Você chegou a seis erros.",
               "DESISTENCIA": "Você desistiu."}
    return f"Você perdeu. {details.get(state['reason'], '')}"


def render(state, player_id):
    if not state:
        return "Você não está em nenhuma sala. Digite /nova para entrar em uma."
    players = state["players"]
    lines = ["=" * 68, f"FORCA | {state['room_id']} | {state['status']}", ""]
    labels = []
    drawings = []
    for p in players:
        labels.append(f"{p['name']}{' (você)' if p['player_id'] == player_id else ''}")
        drawings.append(gallows(p["errors"]))
    if len(players) == 1:
        labels.append("Aguardando adversário")
        drawings.append(gallows(0))
    lines.append(f"{labels[0]:<34}{labels[1]}")
    for left, right in zip(*drawings):
        lines.append(f"{left:<34}{right}")
    left_errors = players[0]["errors"]
    right_errors = players[1]["errors"] if len(players) == 2 else 0
    lines.extend([f"Erros: {left_errors}/6{' ' * 24}Erros: {right_errors}/6", ""])
    if state["masked_word"]:
        lines.append("Palavra: " + " ".join(state["masked_word"]))
    lines.append("Letras tentadas: " + (", ".join(state["guesses"]) or "nenhuma"))
    if state.get("wrong_words"):
        lines.append("Chutes errados: " + ", ".join(state["wrong_words"]))
    if state["status"] == "AGUARDANDO":
        lines.append("A partida começa quando o segundo jogador entrar.")
    elif state["status"] == "PAUSADA":
        absent = ", ".join(p["name"] for p in players if not p["connected"])
        lines.append(f"Partida pausada. Aguardando reconexão: {absent}.")
    elif state["status"] == "EM_JOGO":
        current = next(p["name"] for p in players if p["player_id"] == state["turn"])
        lines.append("Sua vez! Tente uma letra ou chute a palavra." if state["turn"] == player_id
                     else f"Vez de {current}. Aguarde.")
    else:
        lines.append(outcome(state, player_id))
        lines.append("Digite /nova para jogar novamente.")
    lines.append("=" * 68)
    return "\n".join(lines)

