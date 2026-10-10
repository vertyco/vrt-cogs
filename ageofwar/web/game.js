// Age of War's page: the live connection, the bot's snapshots, the setup and results panels, and the player's orders.
// The bot runs the battle; this page sends what the player presses and draws what the bot sends back.
import { backToMenu, connect } from "activityhub";
import { Hud, SPLIT, STRIP } from "./hud.js";
import { createScene, FPS } from "./scene.js";
import { Sound } from "./sound.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Age of War again.",
  1011: "Couldn't join the game.",
  4003: "Age of War was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
const DIFFICULTY_NAMES = { normal: "Normal", harder: "Harder", impossible: "Impossible" };
const SIDE_NAMES = ["Left base", "Right base"];
// The original's last screens
const VICTORY = ["Victory!", "Congratulations, you won the war and destroyed your ennemy."];
const DEFEAT = ["Defeat!", "Maybe you didn't tried hard enough?"];
// Room the corner buttons need between the menu strips: five buttons and their gaps, with a margin, at full size
// and at their smaller size
const CORNER_ROOM = 230;
const SMALL_CORNER_ROOM = 180;
// The menu button whose hover picture is the sword that marks a line
const SWORD = 1032;
const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  scene: null,
  hud: null,
  state: null,
  mySeat: null,
  stage: null,
  board: "normal",
  boards: null,
  updates: 0,
  toastTimer: null,
  preview: false,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  bindButtons();
  try {
    page.scene = await createScene($("field"));
  } catch (e) {
    console.error("Age of War: couldn't start drawing", e);
    showOverlay("Sorry!", "This device couldn't start the game's graphics.");
    return;
  }
  page.scene.lib.onSound = (id) => sound.play(id);
  page.scene.setBattle(false);
  page.scene.onFit = layout;
  page.hud = new Hud($("hud"), page.scene, send);
  page.scene.onSpot = (press) => page.hud.spot(press);
  page.scene.onSpotHover = (kind, spot) => page.hud.spotHover(kind, spot);
  $("logo").src = page.scene.picture(1013, null, 2).url;
  // The original's menus point at a line with a knight's sword
  const sword = page.scene.picture(SWORD, "o", 2);
  $("app").style.setProperty("--sword", `url(${sword.url})`);
  $("app").style.setProperty("--sword-ratio", String(sword.width / sword.height));
  window.addEventListener("resize", () => layout(page.scene.scale));
  layout(page.scene.scale);
  try {
    page.hub = await connect();
  } catch (e) {
    showOverlay("Sorry!", e.message);
    return;
  }
  if (page.hub.offline) {
    await showPreview();
    return;
  }
  bindInput();
  setInterval(showRate, 1000);
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showOverlay("Sorry!", CLOSED_BECAUSE[e.status] || e.message);
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
    showOverlay("Sorry!", CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
  });
}

function send(message) {
  if (page.conn) {
    page.conn.send(message);
  }
}

function showRate() {
  page.hub.stat(page.updates ? `${page.updates} TPS` : "");
  page.updates = 0;
}

// ---------- The browser preview ----------

// Outside Discord the page plays a recording of two computers fighting, made by the bot's own battle code
async function showPreview() {
  page.preview = true;
  $("setup").hidden = true;
  showToast("Preview: open Age of War in Discord to play.", 0);
  let recording;
  try {
    const resp = await fetch("demo.json");
    recording = await resp.json();
  } catch (e) {
    console.warn("Age of War: couldn't load the preview", e);
    return;
  }
  const replay = () => {
    page.scene.clear();
    recording.forEach((frame, index) => setTimeout(() => page.scene.push(frame), (index * 1000) / (FPS / 2)));
    setTimeout(replay, (recording.length * 1000) / (FPS / 2) + 3000);
  };
  page.scene.focus(1);
  replay();
}

// ---------- Messages from the bot ----------

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  if (data.state) {
    applyState(data.state);
  }
  // A frame that arrives after its battle ended would put the battle back on the cleared field
  if (data.f && page.stage === "playing") {
    page.updates += 1;
    page.scene.push(data.f);
    const side = mySide();
    if (side !== null && page.stage === "playing") {
      page.hud.update(data.f.s[side - 1]);
    }
  }
  if (data.notice) {
    showToast(data.notice);
  }
}

function myId() {
  return page.hub && page.hub.player ? page.hub.player.id : null;
}

// The side this page commands, while its player sits in a battle the computer hasn't taken over
function mySide() {
  const state = page.state;
  if (!state || page.mySeat === null || state.seats[page.mySeat].standIn) {
    return null;
  }
  return page.mySeat + 1;
}

function applyState(state) {
  const before = page.stage;
  page.state = state;
  page.stage = state.stage;
  const seat = state.seats.findIndex((s) => s.kind === "human" && s.id === myId());
  page.mySeat = seat === -1 ? null : seat;
  $("app").dataset.stage = state.stage;
  if (state.stage === "playing" && before !== "playing") {
    // A new battle: everything on the field starts over
    page.scene.clear();
    page.hud.reset();
    page.scene.mySide = mySide();
    page.scene.focus(mySide() || 1);
  }
  if (state.stage !== "playing") {
    page.scene.mySide = null;
    page.scene.setMode("none");
    // A give-up question left open would otherwise give up the next battle
    if ($("quit").open) {
      $("quit").close();
    }
  }
  if ((state.stage === "playing") !== (before === "playing")) {
    page.scene.setBattle(state.stage === "playing");
  }
  sound.battle(state.stage === "playing");
  showSetup(state);
  showResults(state);
  showPlaying(state);
  layout(page.scene.scale);
}

// ---------- Setup ----------

function showSetup(state) {
  const setup = state.stage === "setup";
  $("setup").hidden = !setup;
  if (!setup) {
    return;
  }
  const host = state.host !== null && state.host === page.mySeat;
  const seats = $("seats");
  seats.replaceChildren();
  state.seats.forEach((seat, number) => seats.appendChild(seatCard(seat, number)));
  const vsComputer = state.seats.some((seat) => seat.kind === "empty");
  for (const choice of document.querySelectorAll("[data-difficulty]")) {
    const on = choice.dataset.difficulty === state.difficulty;
    choice.setAttribute("aria-checked", String(on));
    choice.classList.toggle("on", on);
    choice.disabled = !host;
  }
  $("difficulty-box").classList.toggle("off", !vsComputer);
  $("start").hidden = !host;
  $("stand").hidden = page.mySeat === null;
  $("hint").textContent = setupHint(state, host, vsComputer);
  $("watching").textContent = state.watching ? `${state.watching} watching` : "";
}

function seatCard(seat, number) {
  const card = document.createElement("li");
  card.className = `seat ${seat.kind}`;
  const label = document.createElement("span");
  label.className = "side-name";
  label.textContent = SIDE_NAMES[number];
  card.appendChild(label);
  if (seat.kind === "human") {
    const who = document.createElement("span");
    who.className = "who";
    if (seat.avatar) {
      const avatar = document.createElement("img");
      avatar.src = seat.avatar;
      avatar.alt = "";
      who.appendChild(avatar);
    }
    who.append(seat.name + (seat.away ? " (away)" : ""));
    card.appendChild(who);
  } else if (page.mySeat === null) {
    const sit = document.createElement("button");
    sit.type = "button";
    sit.className = "button";
    sit.textContent = "Sit here";
    sit.addEventListener("click", () => send({ sit: number }));
    card.appendChild(sit);
  } else {
    const who = document.createElement("span");
    who.className = "who cpu";
    who.textContent = "Computer";
    card.appendChild(who);
  }
  return card;
}

function setupHint(state, host, vsComputer) {
  if (page.mySeat === null) {
    return state.seats.some((seat) => seat.kind === "empty") ? "Pick a base to play." : "Both bases are taken.";
  }
  if (!host) {
    return "The host starts the game.";
  }
  return vsComputer ? "Play the computer, or wait for a friend to take the other base." : "Two players: no computer.";
}

// ---------- Playing ----------

function showPlaying(state) {
  const playing = state.stage === "playing";
  const side = playing ? mySide() : null;
  $("hud").hidden = side === null;
  const watching = playing && side === null;
  $("sides").hidden = !watching;
  if (watching) {
    state.seats.forEach((seat, number) => {
      const name = state.players[number] === "cpu" ? "Computer" : seat.name;
      $(`side-${number + 1}`).textContent = seat.standIn ? `${name} (computer playing)` : name;
    });
  }
  const solo = playing && state.players.filter((kind) => kind === "human").length === 1;
  $("pause").hidden = !(solo && side !== null);
  $("give-up").hidden = !(playing && side !== null);
  if (playing && state.paused) {
    showOverlay("Paused", side !== null ? "Press Resume or the space bar to carry on." : "", side !== null);
  } else if (playing && state.waiting) {
    showOverlay("Waiting", "The player is away. The game carries on when they're back.");
  } else {
    hideOverlay();
  }
}

function togglePause() {
  const state = page.state;
  if (state && state.stage === "playing" && !$("pause").hidden) {
    send({ pause: !state.paused });
  }
}

function autoPause() {
  const state = page.state;
  if (state && state.stage === "playing" && !state.paused && !$("pause").hidden) {
    send({ pause: true });
  }
}

// ---------- Results ----------

function showResults(state) {
  const results = state.stage === "results" ? state.results : null;
  $("results").hidden = !results;
  if (!results) {
    return;
  }
  const winnerSeat = results.winner - 1;
  const winner = results.seats[winnerSeat];
  let words;
  if (page.mySeat !== null && results.seats[page.mySeat].kind === "human") {
    words = page.mySeat === winnerSeat ? VICTORY : DEFEAT;
  } else {
    words = [`${winner.name} won!`, `The ${SIDE_NAMES[winnerSeat].toLowerCase()} destroyed the enemy base.`];
  }
  $("results-title").textContent = words[0];
  $("results-text").textContent = words[1];
  const difficulty = results.difficulty ? ` on ${DIFFICULTY_NAMES[results.difficulty]}` : "";
  $("results-time").textContent = `Game time ${formatTime(results.frames)}${difficulty}`;
  const solo = results.seats.filter((seat) => seat.kind === "human").length === 1;
  const humanWon = winner.kind === "human" && !winner.standIn;
  $("results-note").textContent = solo && humanWon ? "Your time counts for the fastest wins." : "";
  const host = state.host !== null && state.host === page.mySeat;
  $("continue").hidden = !host;
}

function formatTime(frames) {
  const tenths = Math.floor(frames / (FPS / 10));
  const minutes = Math.floor(tenths / 600);
  const seconds = Math.floor((tenths % 600) / 10);
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths % 10}`;
}

// ---------- Leaderboard ----------

async function openLeaderboard() {
  $("leaders").replaceChildren();
  $("you").textContent = "Loading...";
  $("leaderboard").showModal();
  if (!page.hub || page.hub.offline) {
    $("you").textContent = "Open Age of War in Discord to see the fastest wins.";
    return;
  }
  try {
    page.boards = await page.hub.api("leaderboard");
  } catch (e) {
    $("you").textContent = e.message;
    return;
  }
  showBoard(page.state && page.state.difficulty ? page.state.difficulty : "normal");
}

function showBoard(board) {
  page.board = board;
  for (const tab of document.querySelectorAll("[data-board]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.board === board));
  }
  if (!page.boards) {
    return;
  }
  const { top, you } = page.boards[board];
  const list = $("leaders");
  list.replaceChildren();
  for (const row of top) {
    const item = document.createElement("li");
    const wins = row.wins === 1 ? "1 win" : `${row.wins} wins`;
    item.innerHTML = `<span class="rank"></span><span class="name"></span><span class="time"></span><span class="wins"></span>`;
    item.querySelector(".rank").textContent = `#${row.rank}`;
    item.querySelector(".name").textContent = row.name;
    item.querySelector(".time").textContent = formatTime(row.frames);
    item.querySelector(".wins").textContent = wins;
    if (row.id === myId()) {
      item.classList.add("me");
    }
    list.appendChild(item);
  }
  if (!top.length) {
    $("you").textContent = `Nobody has beaten the computer on ${DIFFICULTY_NAMES[board]} yet.`;
  } else if (you) {
    $("you").textContent = `Your best: #${you.rank}, ${formatTime(you.frames)}.`;
  } else {
    $("you").textContent = `You haven't beaten the computer on ${DIFFICULTY_NAMES[board]} yet.`;
  }
}

// ---------- Layout ----------

// Wide windows lay the menus over the sky like the original. Upright phones put them under the field, bigger
function layout(scale) {
  const app = $("app");
  const tall = window.innerHeight > window.innerWidth * 1.1;
  app.dataset.layout = tall ? "tall" : "wide";
  const width = app.clientWidth || window.innerWidth;
  let left;
  let right;
  if (tall) {
    left = Math.min(width / SPLIT, 1.5);
    right = Math.min(width / (STRIP.width - SPLIT), 1.8);
  } else {
    left = right = Math.max(0.7, Math.min(scale || 1, 1.6));
  }
  app.style.setProperty("--left-scale", String(left));
  app.style.setProperty("--right-scale", String(right));
  // Upright, each strip is centered on its own row
  app.style.setProperty("--left-pad", `${(width - SPLIT * left) / 2}px`);
  app.style.setProperty("--right-pad", `${(width - (STRIP.width - SPLIT) * right) / 2}px`);
  // The corner buttons sit between the strips, smaller when room is short, or under them without room
  const gap = width - SPLIT * left - (STRIP.width - SPLIT) * right;
  app.dataset.corner = tall || gap >= CORNER_ROOM ? "gap" : gap >= SMALL_CORNER_ROOM ? "small" : "below";
}

// ---------- Overlays ----------

function showOverlay(big, small, resume = false) {
  $("overlay").hidden = false;
  $("overlay-big").textContent = big;
  $("overlay-small").textContent = small;
  $("resume").hidden = !resume;
}

function hideOverlay() {
  $("overlay").hidden = true;
}

function showToast(text, ms = 4000) {
  const toast = $("toast");
  toast.textContent = text;
  toast.hidden = false;
  clearTimeout(page.toastTimer);
  if (ms) {
    page.toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, ms);
  }
}

// ---------- Buttons and keys ----------

function bindButtons() {
  $("back").addEventListener("click", backToMenu);
  const soundButton = $("sound");
  soundButton.setAttribute("aria-pressed", String(sound.on));
  soundButton.addEventListener("click", () => {
    sound.setOn(!sound.on);
    soundButton.setAttribute("aria-pressed", String(sound.on));
  });
  const musicButton = $("music");
  musicButton.setAttribute("aria-pressed", String(sound.musicOn));
  musicButton.addEventListener("click", () => {
    sound.setMusicOn(!sound.musicOn);
    musicButton.setAttribute("aria-pressed", String(sound.musicOn));
  });
  $("pause").addEventListener("click", togglePause);
  $("resume").addEventListener("click", () => send({ pause: false }));
  // Discord's frame blocks the browser's own confirm box, so the page asks in its own dialog
  $("give-up").addEventListener("click", () => $("quit").showModal());
  $("quit-yes").addEventListener("click", () => {
    $("quit").close();
    if (page.stage === "playing") {
      send({ quit: true });
    }
  });
  $("quit-no").addEventListener("click", () => $("quit").close());
  $("start").addEventListener("click", () => send({ start: true }));
  $("stand").addEventListener("click", () => send({ stand: true }));
  $("continue").addEventListener("click", () => send({ continue: true }));
  for (const choice of document.querySelectorAll("[data-difficulty]")) {
    choice.addEventListener("click", () => send({ difficulty: choice.dataset.difficulty }));
  }
  $("open-leaderboard").addEventListener("click", openLeaderboard);
  $("close-leaderboard").addEventListener("click", () => $("leaderboard").close());
  for (const tab of document.querySelectorAll("[data-board]")) {
    tab.addEventListener("click", () => showBoard(tab.dataset.board));
  }
  $("open-help").addEventListener("click", () => $("help").showModal());
  $("close-help").addEventListener("click", () => $("help").close());
}

function bindInput() {
  const keys = new Set();
  const scroll = () => {
    const left = keys.has("ArrowLeft") || keys.has("a");
    const right = keys.has("ArrowRight") || keys.has("d");
    page.scene.camera.keys = (right ? 1 : 0) - (left ? 1 : 0);
  };
  window.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement || document.querySelector("dialog[open]")) {
      return;
    }
    if (event.code === "Space") {
      event.preventDefault();
      if (!event.repeat) {
        togglePause();
      }
      return;
    }
    keys.add(event.key.length === 1 ? event.key.toLowerCase() : event.key);
    scroll();
  });
  window.addEventListener("keyup", (event) => {
    keys.delete(event.key.length === 1 ? event.key.toLowerCase() : event.key);
    scroll();
  });
  // A game against the computer pauses when the player clicks away or hides the window, as the hub asks of games
  window.addEventListener("blur", () => {
    keys.clear();
    scroll();
    autoPause();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      autoPause();
    }
  });
}

start();
