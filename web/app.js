"use strict";
// Cliente do navegador. Mesmas regras do cliente.py: um comando pendente por vez, salvo antes do
// envio e reenviado idêntico até haver resposta. Assim uma queda de servidor não repete jogadas.

const KEY = "forca.sessao";      // sessionStorage: cada aba é um jogador e sobrevive a recarregar.
const POLL = 1000;               // Consulta de estado.
const RESEND = 150;              // Comando pendente sai logo.
const TIMEOUT = 20000;           // Maior que a última tentativa possível do gateway (~17 s).
const MAX_ERRORS = 6;
const STATUS = { AGUARDANDO: "Aguardando adversário", EM_JOGO: "Em jogo", PAUSADA: "Pausada",
                 ENCERRADA: "Encerrada", CANCELADA: "Cancelada" };

let memory = null;               // Usado se o navegador bloquear o sessionStorage.
let session = load();
let view = { state: null, me: null, connected: null, node: null, busy: false };
let timer = null;

const $ = (id) => document.getElementById(id);

function load() {
  try { return JSON.parse(sessionStorage.getItem(KEY)); } catch { return memory; }
}

function save() {
  memory = session;
  try { sessionStorage.setItem(KEY, JSON.stringify(session)); } catch { /* fica em memória */ }
}

function forget() {
  session = memory = null;
  try { sessionStorage.removeItem(KEY); } catch { /* nada a apagar */ }
}

function randomBytes(size) {
  const bytes = new Uint8Array(size);
  crypto.getRandomValues(bytes);
  return bytes;
}

function newToken() {
  return btoa(String.fromCharCode(...randomBytes(32)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function newRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = randomBytes(16);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function normalize(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
}

// Rede -------------------------------------------------------------------------------------------

async function post(command) {
  const controller = new AbortController();
  const limit = setTimeout(() => controller.abort(), TIMEOUT);
  try {
    const response = await fetch("/api", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command), signal: controller.signal, cache: "no-store",
    });
    return await response.json();
  } catch {
    return null;  // Rede, gateway ou resposta ilegível: tenta de novo com o mesmo comando.
  } finally {
    clearTimeout(limit);
  }
}

function schedule(ms) {
  clearTimeout(timer);
  timer = setTimeout(run, ms);
}

async function run() {
  try {
    await tick();
  } finally {  // Um erro ao desenhar a tela não pode parar as consultas.
    if (session) schedule(session.pending ? RESEND : POLL);
  }
}

async function tick() {
  if (!session || view.busy) return;
  view.busy = true;
  const sent = session.pending;
  const command = sent || { type: "ESTADO", token: session.token, deployment: session.deployment };
  const response = await post(command);
  view.busy = false;
  if (!session) return;
  if (!response || response.retry) {
    view.connected = false;
    render();
    return;
  }
  if (response.fatal) {
    forget();
    showEntry(response.message);
    return;
  }
  const reconnected = view.connected !== true;
  view.connected = true;
  view.node = response.node || view.node;
  if (response.deployment) session.deployment = response.deployment;
  if (sent) {
    session.pending = null;
    if (response.code === "NOME_EM_USO") {
      forget();
      showEntry(response.message);
      return;
    }
    if (sent.type === "SAIR" && (response.ok || response.code === "SEM_SALA")) {
      forget();
      showEntry("Você saiu. Até a próxima!");
      return;
    }
    flash(response.message, response.ok !== false);
  }
  save();
  if ("state" in response) {
    view.state = response.state;
    view.me = response.player_id;
  }
  // Quem volta esperando procura outro jogador que também espera (RF02a).
  if (reconnected && !sent && view.state && view.state.status === "AGUARDANDO") queue("ENTRAR");
  render();
}

function queue(type, fields = {}) {
  if (!session || session.pending) return;
  session.pending = { type, ...fields, request_id: newRequestId(), name: session.name,
                      token: session.token, deployment: session.deployment };
  save();  // Antes do envio: um reenvio depois de recarregar a página usa o mesmo identificador.
  render();
  if (!view.busy) schedule(0);
}

// Ações ------------------------------------------------------------------------------------------

function canPlay() {
  const s = view.state;
  return Boolean(session && !session.pending && view.connected && s
                 && s.status === "EM_JOGO" && s.turn === view.me);
}

function guess(letter) {
  if (canPlay() && !view.state.guesses.includes(letter)) {
    queue("JOGAR", { letter, version: view.state.room_version });
  }
}

function showEntry(message = "") {
  clearTimeout(timer);
  view = { state: null, me: null, connected: null, node: null, busy: false };
  $("jogo").hidden = true;
  $("entrada").hidden = false;
  $("entrada-erro").textContent = message;
  renderConnection();
  $("nome").focus();
}

function showGame() {
  $("entrada").hidden = true;
  $("jogo").hidden = false;
  render();
  schedule(0);
}

function flash(message, ok) {
  const target = $("mensagem");
  target.textContent = message || "";
  target.classList.toggle("falha", !ok);
}

// Tela -------------------------------------------------------------------------------------------

function svg(tag, attributes) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}

function gallows(errors) {
  const drawing = svg("svg", { viewBox: "0 0 120 140", role: "img",
                               "aria-label": `Forca com ${errors} de ${MAX_ERRORS} erros` });
  const frame = svg("g", { class: "forca-estrutura", "stroke-width": "4", "stroke-linecap": "round", fill: "none" });
  for (const d of ["M10 132 H80", "M30 132 V10", "M30 10 H82", "M82 10 V26"]) frame.append(svg("path", { d }));
  drawing.append(frame);
  const body = svg("g", { class: "forca-boneco", "stroke-width": "4", "stroke-linecap": "round", fill: "none" });
  const parts = [
    svg("circle", { cx: "82", cy: "38", r: "12" }),
    svg("path", { d: "M82 50 V88" }),
    svg("path", { d: "M82 60 L66 76" }),
    svg("path", { d: "M82 60 L98 76" }),
    svg("path", { d: "M82 88 L68 110" }),
    svg("path", { d: "M82 88 L96 110" }),
  ];
  parts.slice(0, errors).forEach((part) => body.append(part));
  drawing.append(body);
  return drawing;
}

function playerCard(target, player, isTurn) {
  target.replaceChildren();
  target.classList.toggle("vez", Boolean(isTurn));
  target.classList.toggle("ausente", Boolean(player && !player.connected));
  const title = document.createElement("h3");
  const line = document.createElement("p");
  if (player) {
    title.textContent = player.name + (player.player_id === view.me ? " (você)" : "");
    line.textContent = `Erros: ${player.errors}/${MAX_ERRORS}` + (player.connected ? "" : " · desconectado");
  } else {
    title.textContent = "Aguardando adversário";
    line.textContent = " ";
  }
  target.append(title, gallows(player ? player.errors : 0), line);
}

function outcome(s) {
  if (!s.winner) return "Partida cancelada.";
  const names = Object.fromEntries(s.players.map((p) => [p.player_id, p.name]));
  const loser = s.players.map((p) => p.player_id).find((id) => id !== s.winner);
  if (s.winner === view.me) {
    const why = { PALAVRA_COMPLETA: "Você completou a palavra.",
                  SEIS_ERROS: `${names[loser]} chegou a seis erros.`,
                  DESISTENCIA: `${names[loser]} desistiu.` };
    return `Você venceu! ${why[s.reason] || ""}`;
  }
  const why = { PALAVRA_COMPLETA: `${names[s.winner]} completou a palavra.`,
                SEIS_ERROS: "Você chegou a seis erros.", DESISTENCIA: "Você desistiu." };
  return `Você perdeu. ${why[s.reason] || ""}`;
}

function turnText(s) {
  if (s.status === "AGUARDANDO") return "A partida começa quando o segundo jogador entrar.";
  if (s.status === "PAUSADA") {
    const absent = s.players.filter((p) => !p.connected).map((p) => p.name).join(", ");
    return `Partida pausada. Aguardando reconexão: ${absent}.`;
  }
  if (s.status === "EM_JOGO") {
    if (s.turn === view.me) return "Sua vez! Escolha uma letra ou chute a palavra.";
    const current = s.players.find((p) => p.player_id === s.turn);
    return `Vez de ${current ? current.name : "adversário"}. Aguarde.`;
  }
  return outcome(s);
}

function renderConnection() {
  const target = $("conexao");
  target.classList.toggle("ok", view.connected === true);
  let text = "Desconectado";
  if (session && view.connected === true) text = `Conectado · ${view.node || "servidor"}`;
  else if (session && view.connected === false) text = "Reconectando…";
  else if (session) text = "Conectando…";
  $("conexao-texto").textContent = text;
}

function renderKeyboard(s) {
  const keyboard = $("teclado");
  if (!keyboard.childElementCount) {
    for (const letter of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = letter;
      button.dataset.letter = letter;
      button.addEventListener("click", () => guess(letter));
      keyboard.append(button);
    }
  }
  const playable = canPlay();
  for (const button of keyboard.children) {
    const letter = button.dataset.letter;
    const used = s.guesses.includes(letter);
    button.classList.toggle("acerto", used && s.masked_word.includes(letter));
    button.classList.toggle("errou", used && !s.masked_word.includes(letter));
    button.disabled = !playable || used;
  }
}

function render() {
  renderConnection();
  if (!session) return;
  const s = view.state;
  const finished = !s || s.status === "ENCERRADA" || s.status === "CANCELADA";
  $("sem-sala").hidden = Boolean(s) || view.connected !== true;
  $("tabuleiro").hidden = !s;
  $("sala-id").textContent = s ? s.room_id : "";
  const badge = $("sala-status");
  badge.textContent = s ? STATUS[s.status] || s.status : "";
  badge.className = "selo" + (s ? ` ${s.status.toLowerCase()}` : "");
  badge.hidden = !s;
  $("nova").hidden = !finished || view.connected !== true;
  $("nova").disabled = Boolean(session.pending);
  $("sair").disabled = Boolean(session.pending);
  if (!s) return;

  const turn = s.status === "EM_JOGO" ? s.turn : null;
  [0, 1].forEach((i) => playerCard($(`jogador-${i}`), s.players[i], s.players[i] && s.players[i].player_id === turn));
  $("palavra").textContent = s.masked_word ? s.masked_word.split("").join(" ") : "";
  $("vez").textContent = turnText(s);
  renderKeyboard(s);
  const playable = canPlay();
  $("chute").disabled = !playable;
  $("form-chute").querySelector("button").disabled = !playable;
  $("chutes-errados").textContent = s.wrong_words.length ? `Chutes errados: ${s.wrong_words.join(", ")}` : "";
}

// Eventos ----------------------------------------------------------------------------------------

$("form-entrada").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = $("nome").value.trim();
  if (name.length < 1 || name.length > 24) {
    $("entrada-erro").textContent = "Use um nome de 1 a 24 caracteres.";
    return;
  }
  session = { name, token: newToken(), deployment: null, pending: null };
  save();
  flash("", true);
  queue("ENTRAR");
  showGame();
});

$("form-chute").addEventListener("submit", (event) => {
  event.preventDefault();
  const word = $("chute").value.trim();
  if (!word || !canPlay()) return;
  queue("CHUTAR", { word, version: view.state.room_version });
  $("chute").value = "";
});

$("nova").addEventListener("click", () => queue("ENTRAR"));

$("sair").addEventListener("click", () => {
  const playing = view.state && (view.state.status === "EM_JOGO" || view.state.status === "PAUSADA");
  if (!playing || confirm("Sair agora conta como desistência. Deseja sair?")) queue("SAIR");
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.target.tagName === "INPUT") return;
  const letter = normalize(event.key);
  if (/^[A-Z]$/.test(letter)) guess(letter);
});

if (session) showGame();
else showEntry();
