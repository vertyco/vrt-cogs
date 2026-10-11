// Boulder Bash's page: the live connection, the screens around the boards, and the player's taps.
// The bot keeps every board; this page only says where the player tapped, and plays back what the bot sends.
import { backToMenu, connect } from "activityhub";
import { BOMB, EXTREMES, MAX_COLORS, TWO_BOARDS, WILD } from "./motion.js";
import { createScene } from "./scene.js";
import { Sound } from "./sound.js";
import {
  checkPassed,
  disconnected,
  hidePass,
  onPeople,
  placePeople,
  report,
  showLive,
  startPassing,
  watchPeople,
  ZEN,
} from "./whoshere.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Boulder Bash again.",
  1011: "Couldn't join the game.",
  4003: "Boulder Bash was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
  4100: "Boulder Bash was opened somewhere else.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
const OFFLINE_PLAY = "Open Boulder Bash in Discord to play.";
const EFFECTS_KEY = "boulderbash:effects";
// A phone held upright gets the stacked layout
const TALL_BELOW = 0.8;
const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  scene: null,
  screen: "title",
  game: null,
  boards: [],
  result: null,
  popupOpen: false,
  helpPage: 1,
  logoBuilt: false,
  effects: readEffects(),
  payouts: null,
  toastTimer: null,
};
watchPeople(page);

function $(id) {
  return document.getElementById(id);
}

function plural(count, word) {
  return `${count.toLocaleString()} ${count === 1 ? word : `${word}s`}`;
}

function readEffects() {
  try {
    return localStorage.getItem(EFFECTS_KEY) !== "off";
  } catch (e) {
    console.warn("Boulder Bash: couldn't read the effects setting", e);
    return true;
  }
}

function saveEffects(on) {
  try {
    localStorage.setItem(EFFECTS_KEY, on ? "on" : "off");
  } catch (e) {
    console.warn("Boulder Bash: couldn't save the effects setting", e);
  }
}

// ---------- Starting ----------

async function start() {
  bindButtons();
  try {
    page.scene = await createScene($("scene"));
    // Where the scene drew things can be read from outside, as the browser tests do
    window.boulderbashScene = page.scene;
  } catch (e) {
    console.error("Boulder Bash: couldn't start drawing", e);
    showMessage("This device couldn't start the game's graphics.");
    return;
  }
  const scene = page.scene;
  scene.effects = page.effects;
  scene.onTap = tap;
  scene.onSound = playSound;
  scene.onCameo = () => scene.cameo() && sound.play("roar");
  window.addEventListener("resize", layout);
  showScreen("title");
  try {
    page.hub = await connect();
  } catch (e) {
    showMessage(e.message);
    return;
  }
  // Placed straight after connecting, so the hub never floats a button of its own over the game
  $("people").append(page.hub.peopleButton());
  page.hub.onPeople(onPeople);
  if (page.hub.offline) {
    return;
  }
  report();
  loadPayouts();
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showMessage(CLOSED_BECAUSE[e.status] || e.message);
    disconnected();
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    showMessage(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
    disconnected();
  });
}

function showMessage(text) {
  $("message-text").textContent = text;
  $("message").hidden = false;
}

function send(data) {
  return page.conn ? page.conn.send(data) : false;
}

// ---------- Screens and layout ----------

function showScreen(name) {
  const before = page.screen;
  page.screen = name;
  $("stage").dataset.screen = name;
  // The people button and the strip sit outside the stage, and follow the screen from here
  document.body.dataset.screen = name;
  for (const id of ["title", "modes", "help", "play", "over"]) {
    $(id).hidden = id !== name;
  }
  if (name === "title" || name === "modes") {
    buildLogo();
  }
  if (name !== "play") {
    hidePopup();
    hidePass();
  }
  layout();
  if (["title", "modes", "over"].includes(name) && before !== name) {
    page.scene?.entrance();
  }
  sound.setScene(name === "play" ? "play" : "menu");
  report();
}

// The logo tumbles in on the first visit, and again after a restart when effects are on
function buildLogo() {
  const logo = $("logo");
  const build = !page.logoBuilt && page.effects;
  page.logoBuilt = true;
  logo.classList.toggle("build", build);
  [...logo.querySelectorAll(".logo-line span")].forEach((letter, i) => letter.style.setProperty("--i", i));
}

function safeArea() {
  const style = getComputedStyle($("safe"));
  return {
    top: parseFloat(style.paddingTop) || 0,
    right: parseFloat(style.paddingRight) || 0,
    bottom: parseFloat(style.paddingBottom) || 0,
    left: parseFloat(style.paddingLeft) || 0,
  };
}

function layout() {
  const tall = window.innerWidth / window.innerHeight < TALL_BELOW;
  document.body.classList.toggle("tall", tall);
  const safe = safeArea();
  let stage = null;
  if (!tall) {
    const roomW = window.innerWidth - safe.left - safe.right;
    const roomH = window.innerHeight - safe.top - safe.bottom;
    const scale = Math.min(roomW / 800, roomH / 600);
    const x = safe.left + (roomW - 800 * scale) / 2;
    const y = safe.top + (roomH - 600 * scale) / 2;
    $("stage").style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    stage = { x, y, scale };
  }
  let playArea = null;
  if (tall && page.screen === "play") {
    const top = $("hud-top").getBoundingClientRect().bottom + 10;
    const bottom = $("hud-bottom").getBoundingClientRect().top - 10;
    playArea = { top, height: Math.max(100, bottom - top) };
  }
  page.scene?.layout({ tall, screen: page.screen, safe, playArea });
  placePeople(stage, safe);
}

function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 3000);
}

function playSound(name, options) {
  if (name === "boom") {
    sound.boom();
  } else if (name === "shuffle-start") {
    sound.startShuffle();
  } else if (name === "shuffle-stop") {
    sound.stopShuffle();
  } else if (name === "crash-shake") {
    const stage = $("stage");
    stage.classList.remove("shaking");
    void stage.offsetWidth;
    stage.classList.add("shaking");
  } else {
    sound.play(name, options);
  }
}

// ---------- Messages from the bot ----------

const HANDLERS = {
  hello: onHello,
  game: (snapshot) => enterPlay(snapshot, true),
  select: (select) => page.scene.select(select.board, select.cells, performance.now()),
  move: onMove,
  undo: (undo) => onBoardChange(undo, () => page.scene.undo(undo, performance.now())),
  shuffle: (shuffle) => onBoardChange(shuffle, () => page.scene.shuffle(shuffle, performance.now())),
  timer: (timer) => onBoardChange(timer, () => page.scene.timer(timer, performance.now())),
  rise: onRise,
  level: onLevel,
  popup: (popup) => page.scene.whenIdle(() => showPopup(popup)),
  done: (done) => {
    page.boards[done.board].phase = "done";
    renderHud();
  },
  over: onOver,
  result: (result) => {
    page.result = result;
    renderResult();
  },
  cashed: onCashed,
  notice: (text) => {
    $("cashin-button").disabled = false;
    toast(text);
  },
  stopped: (text) => {
    page.game = null;
    page.scene.clearGame();
    showScreen("title");
    toast(text);
  },
  elsewhere: showMessage,
};

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  const [name] = Object.keys(data);
  const handler = HANDLERS[name];
  if (!handler) {
    return;
  }
  try {
    handler(data[name]);
  } catch (e) {
    console.error(`Boulder Bash: couldn't show a ${name} message`, e);
  }
}

function onHello(hello) {
  const game = hello.game;
  if (!game) {
    page.game = null;
    page.scene.clearGame();
    showScreen("title");
    return;
  }
  if (game.state === "over") {
    page.game = game;
    page.result = hello.result;
    page.scene.clearGame();
    showOver();
    return;
  }
  enterPlay(game, false);
}

function enterPlay(snapshot, rain) {
  page.game = { mode: snapshot.mode, state: snapshot.state, score: snapshot.score, slots: snapshot.slots, last: snapshot.last };
  page.boards = snapshot.boards.map(boardNumbers);
  startPassing();
  renderSlots(snapshot.slots);
  page.result = null;
  showScreen("play");
  page.scene.setGame(snapshot, performance.now(), rain);
  renderHud();
  if (snapshot.state === "popup" && snapshot.popup) {
    showPopup(snapshot.popup);
  }
}

function boardNumbers(view) {
  return { level: view.level, levelScore: view.levelScore, goal: view.goal, phase: view.phase };
}

// Numbers that change with the board: score, level score, goal and the slots
function takeNumbers(message) {
  const board = page.boards[message.board];
  const before = { ...board };
  Object.assign(board, { level: message.level, levelScore: message.levelScore, goal: message.goal });
  if ("score" in message) {
    page.game.score = message.score;
  }
  const extreme = EXTREMES.includes(page.game.mode);
  const reached = extreme ? board.level > before.level : before.levelScore < board.goal && board.levelScore >= board.goal;
  if (reached && board.goal > 0) {
    sound.play("goal");
  }
  if (message.slots) {
    setSlots(message.slots);
  }
  renderHud();
}

function onMove(move) {
  page.game.last = move.board;
  onBoardChange(move, () => page.scene.move(move, performance.now()));
}

function onBoardChange(message, play) {
  if (!page.game) {
    return;
  }
  takeNumbers(message);
  play();
}

function onRise(rise) {
  onBoardChange(rise, () => page.scene.rise(rise, performance.now()));
}

function onLevel(view) {
  if (!page.game) {
    return;
  }
  page.game.state = "play";
  page.boards[view.board] = boardNumbers(view);
  renderHud();
  page.scene.newLevel(view, performance.now());
}

function onOver(over) {
  if (!page.game) {
    return;
  }
  page.game.state = "over";
  page.game.score = over.score;
  page.scene.whenIdle(() => {
    if (page.game?.state === "over") {
      showOver();
    }
  });
}

// ---------- The play screen ----------

function renderHud() {
  const game = page.game;
  $("score").textContent = game.score.toLocaleString();
  [0, 1].forEach((side) => {
    $(`next-${side}`).textContent = nextLine(side);
  });
  report();
  checkPassed();
  showLive();
}

function nextLine(side) {
  const board = page.boards[side];
  if (!board || page.game.mode === ZEN) {
    return "";
  }
  if (board.phase === "done" && TWO_BOARDS.includes(page.game.mode)) {
    return "Finished";
  }
  if (page.popupOpen && side === 0) {
    return `Level score\n(${board.levelScore.toLocaleString()})`;
  }
  return `Next level\n(${board.levelScore.toLocaleString()} of ${board.goal.toLocaleString()})`;
}

function renderSlots(slots) {
  for (const name of ["undo", "shuffle"]) {
    const button = $(`slot-${name}`);
    button.dataset.state = slots[name];
    button.disabled = slots[name] !== "ready";
  }
}

// A slot glows once when it charges
function setSlots(slots) {
  const old = page.game.slots || {};
  page.game.slots = slots;
  renderSlots(slots);
  for (const name of ["undo", "shuffle"]) {
    const button = $(`slot-${name}`);
    if (old[name] === "empty" && slots[name] !== "empty") {
      button.classList.remove("charged");
      void button.offsetWidth;
      button.classList.add("charged");
    }
  }
}

function useSlot(name) {
  const game = page.game;
  if (!game || game.state !== "play" || game.slots?.[name] !== "ready" || game.last === null) {
    return;
  }
  if (page.scene.canTap(game.last, performance.now())) {
    send({ [name]: true });
  }
}

// A tap on a block. The page draws the selection at once, since it can work the group out from the board; the bot's
// answer confirms it. Taps while a board is still moving are thrown away, as the original threw them away
function tap(side, row, col) {
  const game = page.game;
  const scene = page.scene;
  if (!game || game.state !== "play" || page.popupOpen || page.boards[side]?.phase !== "play") {
    return;
  }
  if (!scene.canTap(side, performance.now())) {
    return;
  }
  const block = scene.blockAt(side, row, col);
  if (!block || block.special === WILD) {
    return;
  }
  send({ tap: [side, col, row] });
  const extreme = EXTREMES.includes(game.mode);
  const selected = scene.boards[side].selection.some(([r, c]) => r === row && c === col);
  if (block.special === BOMB || selected) {
    sound.play("click", { volume: 0.6 });
    return;
  }
  const group = block.color < MAX_COLORS ? scene.groupAt(side, row, col) : [];
  if (extreme && group.length >= 2) {
    sound.play("click", { volume: 0.6 });
    return;
  }
  sound.play("select", { volume: 0.6 });
  if (!extreme) {
    scene.previewSelection(side, group.length >= 2 ? group : []);
  }
}

function showPopup(popup) {
  if (!page.game || page.game.state === "over" || page.screen !== "play") {
    return;
  }
  // The popup's score includes the blocks-left bonus, which no other message carries
  page.game.score = popup.score;
  page.popupOpen = true;
  $("popup-title").textContent = popup.kind === "level" ? "Level complete" : "Game over";
  $("popup-lines").textContent =
    popup.kind === "level" ? `Blocks left: ${popup.left}\nBonus: ${popup.bonus.toLocaleString()}` : "";
  $("popup").hidden = false;
  renderHud();
}

function hidePopup() {
  page.popupOpen = false;
  $("popup").hidden = true;
}

// Any tap or key closes the popup
function closePopup(event) {
  if (!page.popupOpen || page.screen !== "play") {
    return;
  }
  event.preventDefault();
  hidePopup();
  sound.play("click");
  send({ next: true });
  renderHud();
}

// ---------- Game over and cashing in ----------

function showOver() {
  hidePopup();
  page.scene.clearGame();
  showScreen("over");
  $("final-score").textContent = (page.game?.score ?? 0).toLocaleString();
  renderResult();
}

function renderResult() {
  const result = page.result;
  const standing = $("standing");
  standing.replaceChildren();
  $("cashin").hidden = true;
  if (!result) {
    return;
  }
  if (result.dm) {
    standing.textContent = "High scores and cash-ins work in servers.";
  } else if (result.mode === ZEN) {
    standing.textContent = "Zen games don't score.";
  } else if (result.best && result.newBest) {
    const news = document.createElement("span");
    news.className = "new";
    news.textContent = "New best! ";
    standing.append(news, `#${result.rank} on this server`);
  } else if (result.best) {
    standing.textContent = `Your best: ${result.best.toLocaleString()} · #${result.rank} on this server`;
  }
  showOffer(result.offer);
}

// What the finished game is worth where this server pays out. Starting another game gives it up, so players choose
// which games to spend their few cash-ins a day on
function showOffer(offer) {
  const box = $("cashin");
  const button = $("cashin-button");
  box.hidden = !offer;
  if (!offer) {
    return;
  }
  button.disabled = false;
  button.hidden = offer.left <= 0 || offer.worth <= 0;
  if (offer.left <= 0) {
    $("cashin-text").textContent = "No cash-ins left today. They come back at midnight UTC.";
  } else if (offer.worth <= 0) {
    $("cashin-text").textContent = `Score more to earn ${offer.currency}.`;
  } else {
    $("cashin-text").textContent = `Worth ${offer.worth.toLocaleString()} ${offer.currency} · ${offer.left} of ${offer.plays} cash-ins left today`;
    button.textContent = `Cash in ${offer.worth.toLocaleString()}`;
  }
}

function onCashed(paid) {
  $("cashin").hidden = true;
  if (page.result) {
    page.result.offer = null;
    Object.assign(page.result, { best: paid.best, rank: paid.rank });
  }
  toast(`+${paid.paid.toLocaleString()} ${paid.currency}! ${plural(paid.left, "cash-in")} left today`);
  sound.play("bonus");
}

function cashIn() {
  if (send({ cashin: true })) {
    $("cashin-button").disabled = true;
  }
}

function restart() {
  send({ restart: true });
  page.game = null;
  page.result = null;
  page.logoBuilt = !page.effects;
  showScreen("title");
}

// ---------- High scores ----------

async function openScores() {
  $("leaders").replaceChildren();
  $("you").textContent = "Loading...";
  $("scores").showModal();
  if (!page.hub || page.hub.offline) {
    $("you").textContent = "Open Boulder Bash in Discord to see the high scores.";
    return;
  }
  try {
    renderScores(await page.hub.api("scores"));
  } catch (e) {
    $("you").textContent = e.message;
  }
}

function renderScores(table) {
  $("leaders").replaceChildren(...table.top.map(scoreRow));
  if (table.dm) {
    $("you").textContent = "High scores are kept per server.";
  } else if (!table.top.length) {
    $("you").textContent = "No games yet. Be the first!";
  } else if (table.you) {
    $("you").textContent = `You: #${table.you.rank} with ${table.you.best.toLocaleString()}`;
  } else {
    $("you").textContent = "Finish a game to get on the table.";
  }
}

function scoreRow(row) {
  const item = document.createElement("li");
  item.classList.toggle("mine", row.id === page.hub.player?.id);
  const place = document.createElement("span");
  place.className = "place";
  place.textContent = `#${row.rank}`;
  const name = document.createElement("span");
  name.className = "name";
  // Names come from Discord, so they only ever go in as text
  name.textContent = row.name;
  const best = document.createElement("span");
  best.className = "best";
  best.textContent = row.best.toLocaleString();
  item.append(place, name, best);
  return item;
}

// ---------- Payout settings (server admins) ----------

async function loadPayouts() {
  try {
    showPayouts(await page.hub.api("payouts"));
  } catch (e) {
    console.warn("Boulder Bash: couldn't load the payout settings", e);
  }
}

// Players who can't change the settings get none, and never see the button
function showPayouts(state) {
  page.payouts = state.settings ? state : null;
  $("open-payouts").hidden = !page.payouts;
  if (!page.payouts) {
    return;
  }
  $("payouts-global").hidden = !state.global;
  const currency = state.currency;
  $("payouts-rate-label").textContent = `${currency[0].toUpperCase()}${currency.slice(1)} per point`;
  fillPayouts(state.settings);
  const today = state.today;
  $("payouts-today").textContent = `Today: ${today.paid.toLocaleString()} ${currency} paid to ${plural(today.players, "player")}.`;
}

function fillPayouts(settings) {
  $("payouts-on").checked = settings.on;
  for (const name of ["rate", "cap", "plays"]) {
    $(`payouts-${name}`).value = String(settings[name]);
  }
  showDailyMost();
}

function showDailyMost() {
  const cap = Number($("payouts-cap").value);
  const plays = Number($("payouts-plays").value);
  const currency = page.payouts?.currency || "credits";
  $("payouts-day").textContent =
    cap > 0 && plays > 0 ? `A player can earn at most ${(cap * plays).toLocaleString()} ${currency} a day.` : "";
}

// An empty box goes as null, which the bot refuses with a message saying what it needs
function numberIn(id) {
  const value = $(id).value;
  return value === "" ? null : Number(value);
}

async function savePayouts() {
  const settings = {
    on: $("payouts-on").checked,
    rate: numberIn("payouts-rate"),
    cap: numberIn("payouts-cap"),
    plays: numberIn("payouts-plays"),
  };
  $("payouts-status").textContent = "Saving...";
  try {
    showPayouts(await page.hub.api("save_payouts", { settings }));
    $("payouts-status").textContent = "Saved.";
  } catch (e) {
    $("payouts-status").textContent = e.message;
  }
}

// ---------- Buttons ----------

function click(id, handler) {
  $(id).addEventListener("click", (event) => {
    event.currentTarget.blur();
    if (page.popupOpen) {
      return;
    }
    if (event.currentTarget.classList.contains("sign")) {
      sound.play("click");
    }
    handler(event);
  });
}

function showHelpPage(number) {
  page.helpPage = number;
  document.querySelectorAll(".help-page").forEach((node) => {
    node.hidden = Number(node.dataset.page) !== number;
  });
}

function startMode(mode) {
  if (!send({ start: mode })) {
    showMessage(OFFLINE_PLAY);
  }
}

function bindButtons() {
  click("back", () => backToMenu());
  // The browser preview can't play: games need the bot
  click("start", () => (page.hub?.offline ? showMessage(OFFLINE_PLAY) : showScreen("modes")));
  click("how", () => {
    showHelpPage(1);
    showScreen("help");
  });
  click("help-back", () => showScreen("title"));
  click("help-more", () => showHelpPage((page.helpPage % 4) + 1));
  click("open-scores", openScores);
  click("close-scores", () => $("scores").close());
  click("sound", () => {
    sound.cycle();
    showToggles();
  });
  click("effects", () => {
    page.effects = !page.effects;
    saveEffects(page.effects);
    page.scene.effects = page.effects;
    showToggles();
  });
  document.querySelectorAll("[data-mode]").forEach((sign) => {
    sign.addEventListener("click", () => {
      sound.play("click");
      startMode(Number(sign.dataset.mode));
    });
  });
  click("end", () => send({ end: true }));
  click("slot-undo", () => useSlot("undo"));
  click("slot-shuffle", () => useSlot("shuffle"));
  click("restart", restart);
  click("cashin-button", cashIn);
  click("message-close", () => {
    $("message").hidden = true;
  });
  bindPayouts();
  window.addEventListener("pointerdown", closePopup, true);
  window.addEventListener("keydown", closePopup);
  showToggles();
}

function bindPayouts() {
  click("open-payouts", () => {
    $("payouts-status").textContent = "";
    $("payouts").showModal();
    loadPayouts();
  });
  click("close-payouts", () => $("payouts").close());
  click("save-payouts", savePayouts);
  click("reset-payouts", () => {
    fillPayouts(page.payouts.defaults);
    $("payouts-status").textContent = "Reset. Save to keep it.";
  });
  for (const id of ["payouts-cap", "payouts-plays"]) {
    $(id).addEventListener("input", showDailyMost);
  }
}

function showToggles() {
  $("sound").textContent = sound.nextAction;
  $("effects").textContent = page.effects ? "Turn effects off" : "Turn effects on";
}

start();
