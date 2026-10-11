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
// Room the corner buttons and the people button need between the menu strips: five buttons, the people button and
// their gaps, with a margin, at full size and at their smaller size
const CORNER_ROOM = 290;
const SMALL_CORNER_ROOM = 244;
// The menu button whose hover picture is the sword that marks a line
const SWORD = 1032;
// The original's loading bar is 288 long when full
const LOADING_BAR = 288;
// People who aren't at a base show as faces, this many at most, then "+N"
const WATCHER_FACES = 6;
// Longer names are cut to this many characters on the side tags, where both sides' names share the screen
const TAG_NAME_MAX = 12;
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
  // What the watcher faces last showed, so an identical list leaves them alone
  watchLook: null,
  // The status last given to the hub, and whether the game's connection has closed for good
  reported: null,
  closed: false,
};

function $(id) {
  return document.getElementById(id);
}

// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

// ---------- Starting ----------

async function start() {
  bindButtons();
  try {
    page.scene = await createScene($("field"), showLoaded);
  } catch (e) {
    console.error("Age of War: couldn't start drawing", e);
    showOverlay("Sorry!", "This device couldn't start the game's graphics.");
    return;
  }
  page.scene.lib.onSound = (id, points) => sound.play(id, points);
  page.scene.setBattle(false);
  page.scene.onFit = layout;
  page.hud = new Hud($("hud"), page.scene, send);
  page.scene.orders = page.hud.orders;
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
  document.querySelector(".corner").append(page.hub.peopleButton());
  page.hub.onPeople(renderWatchers);
  if (page.hub.offline) {
    await showPreview();
    return;
  }
  bindInput();
  setInterval(showRate, 1000);
  await goLive();
}

// The original's loading bar showed how much of the game had come; here, how much of the art has
function showLoaded(part) {
  $("loading-bar").setAttribute("width", String(LOADING_BAR * part));
}

// The loading screen fades once there is something to show: the bot's first state, the preview, or a problem
function doneLoading() {
  $("loading").classList.add("done");
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showOverlay("Sorry!", CLOSED_BECAUSE[e.status] || e.message);
    leaveGame();
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
    leaveGame();
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
  doneLoading();
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
  doneLoading();
  const before = page.stage;
  page.state = state;
  page.stage = state.stage;
  const seat = state.seats.findIndex((s) => s.kind === "human" && s.id === myId());
  page.mySeat = seat === -1 ? null : seat;
  $("app").dataset.stage = state.stage;
  if (state.stage === "playing" && before !== "playing") {
    // A new battle: everything on the field starts over
    page.scene.clear();
    page.hud.reset(mySide());
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
  renderWatchers();
  report(state);
  layout(page.scene.scale);
}

// ---------- Who's here ----------

// What the rest of the window sees this player doing: a status line, its data, and whether a battle is on for them
function activity(state) {
  const seat = page.mySeat;
  if (seat === null) {
    return ["Watching", null, false];
  }
  let text = "Setting up";
  if (state.stage === "playing") {
    const other = 1 - seat;
    const rival = state.players[other] === "human" ? state.seats[other].name : "CPU";
    text = `Battle vs ${rival}`;
  } else if (state.stage === "results" && state.results) {
    text = state.results.winner - 1 === seat ? "Won" : "Lost";
  }
  return [text, { seat }, state.stage === "playing"];
}

// The hub passes on whatever it is told, even when nothing changed, so only changes go to it
function tell(text, data, busy) {
  const look = JSON.stringify([text, data, busy]);
  if (look === page.reported) {
    return;
  }
  page.reported = look;
  page.hub.status(text, data);
  page.hub.busy(busy);
}

function report(state) {
  if (!page.closed) {
    tell(...activity(state));
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveGame() {
  page.closed = true;
  tell("Not connected", null, false);
}

// The people here who aren't at a base, from the hub's list: in the setup panel, and next to the side names in a
// battle
function renderWatchers() {
  const state = page.state;
  if (!state) {
    return;
  }
  const people = page.hub.people;
  const seated = new Set(state.seats.filter((seat) => seat.kind === "human").map((seat) => seat.id));
  const watchers = people.filter((person) => person.here && !seated.has(person.id));
  // The hub's list counts people. The bot's number counts connections, so someone with the game open on two
  // devices is two there. It stands in only while the hub has no list
  const count = people.length ? watchers.length : state.watching;
  const shown = watchers.slice(0, WATCHER_FACES);
  // Lists arrive several times a second, and a face rebuilt between a press and its release loses the tap
  const faceKeys = shown.map((person) => [person.id, person.name, person.avatar, person.you, person.away]);
  const look = JSON.stringify([count, faceKeys]);
  if (look === page.watchLook) {
    return;
  }
  page.watchLook = look;
  for (const box of [$("watching"), $("side-watchers")]) {
    box.hidden = !count;
    box.replaceChildren(...(count ? watcherRow(shown, count) : []));
  }
}

function watcherRow(shown, count) {
  const row = shown.map(watcherFace);
  const more = count - row.length;
  if (more > 0 && row.length) {
    const extra = document.createElement("span");
    extra.className = "more";
    extra.textContent = `+${more}`;
    row.push(extra);
  }
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = `${count} watching`;
  row.push(label);
  return row;
}

// A watcher's picture. Hovering shows their name; tapping says it, for phones
function watcherFace(person) {
  const face = document.createElement("button");
  face.type = "button";
  face.className = "face";
  const name = person.you ? "You" : person.name;
  face.title = name;
  face.setAttribute("aria-label", name);
  face.classList.toggle("away", Boolean(person.away));
  const letter = document.createTextNode(characters(name)[0]?.toUpperCase() ?? "");
  if (person.avatar) {
    const img = document.createElement("img");
    img.alt = "";
    img.addEventListener("error", () => img.replaceWith(letter));
    img.src = person.avatar;
    face.append(img);
  } else {
    face.append(letter);
  }
  face.addEventListener("click", () => {
    // A focused button would also take the Space key that pauses
    face.blur();
    // The name sits between marks that keep a right-to-left name from turning the sentence around
    showToast(person.you ? "That's you." : `\u2068${person.name}\u2069 is watching.`, 2500);
  });
  return face;
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
  // Everyone sees whose side is whose, not only the people watching
  $("sides").hidden = !playing;
  if (playing) {
    state.seats.forEach((seat, number) => showTag($(`side-${number + 1}`), state.players[number], seat));
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

// A side's name tag. A name too long for the screen is cut, and a base the computer plays says so under the name.
// The arrow that says which base it is (style.css) belongs to the name, so it stays with it when the row wraps
function showTag(tag, kind, seat) {
  const name = document.createElement("span");
  name.className = "tag-name";
  name.textContent = kind === "cpu" ? "Computer" : cut(seat.name);
  tag.replaceChildren(name);
  if (seat.standIn) {
    const note = document.createElement("span");
    note.className = "note";
    note.textContent = "(computer playing)";
    tag.append(note);
  }
}

function cut(name) {
  const letters = characters(name);
  return letters.length > TAG_NAME_MAX ? `${letters.slice(0, TAG_NAME_MAX - 1).join("")}\u2026` : name;
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
    // At the field's own zoom, the menu covers the top of the view as it did over the original's 650 wide field
    left = right = scale || 1;
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
  doneLoading();
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
    page.scene.camera.edge = 0;
    autoPause();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      autoPause();
    }
  });
}

start();
