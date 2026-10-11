// Marble Munch's page: the live connection, the screen around the board, and the player's input.
// The bot runs the game; this page only sends seat, start, press and release, and shows what the bot sends back.
import { backToMenu, connect } from "activityhub";
import { createScene } from "./scene.js";
import { Sound } from "./sound.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Marble Munch again.",
  1011: "Couldn't join the game.",
  4003: "Marble Munch was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
const SEAT_COLORS = ["Orange", "Blue", "Green", "Pink"];
const WATCHER_FACES = 6;
// Longer names are cut to this many characters on the board, where four tags share the walls
const TAG_NAME_MAX = 12;
const touchScreen = window.matchMedia("(pointer: coarse)");
const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  scene: null,
  state: null,
  mySeat: null,
  held: false,
  updates: 0,
  left: null,
  flashTimer: null,
  toastTimer: null,
  // What the watcher row last showed, so an identical list leaves its faces alone
  watchLook: null,
  // The status last given to the hub, and whether the game's connection has closed for good
  reported: null,
  closed: false,
  // The payout settings, for server admins only
  payouts: null,
};

function $(id) {
  return document.getElementById(id);
}

function plural(count, word) {
  return `${count} ${count === 1 ? word : `${word}s`}`;
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
    page.scene = await createScene($("board"));
  } catch (e) {
    console.error("Marble Munch: couldn't start drawing", e);
    showMessage("This device couldn't start the game's graphics.");
    return;
  }
  page.scene.onSeatTap = sit;
  page.scene.onEffect = effect;
  try {
    page.hub = await connect();
  } catch (e) {
    showMessage(e.message);
    return;
  }
  // Older hubs have no people button
  if (page.hub.peopleButton) {
    $("watching").after(page.hub.peopleButton());
  }
  page.hub.onPeople?.(renderWatchers);
  if (page.hub.offline) {
    showPreview();
    return;
  }
  bindInput();
  setInterval(showRate, 1000);
  loadPayouts();
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showMessage(CLOSED_BECAUSE[e.status] || e.message);
    leaveRound();
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    letGo();
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    showMessage(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
    leaveRound();
  });
}

function showPreview() {
  page.scene.startDemo();
  showOverlay("Preview", "Open Marble Munch in Discord to play.");
  $("hint").textContent = "This is the browser preview. Open Marble Munch in Discord to play.";
  const empty = { kind: "empty", id: null, name: "", avatar: "", away: false, played: false };
  renderScores({ seats: [empty, empty, empty, empty], board: null });
}

function showMessage(text) {
  showOverlay("Sorry!", text);
  $("hint").textContent = text;
}

// ---------- Messages from the bot ----------

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  if (data.state) {
    applyState(data.state);
  } else if ("f" in data) {
    applyFrame(data);
  } else if ("offer" in data) {
    showOffer(data.offer);
  } else if (data.cashed) {
    showCashed(data.cashed);
  } else if (data.notice) {
    // A cash-in that didn't pay can be tried again
    $("cashin-button").disabled = false;
    toast(data.notice);
  }
}

// ---------- Cashing in ----------

// What the player's last round is worth where this server pays for marbles. The next round they finish
// replaces it, so they choose which rounds to spend their few cash-ins a day on
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
    $("cashin-text").textContent = `Munch some marbles to earn ${offer.currency}.`;
  } else {
    $("cashin-text").textContent = `Last round is worth ${offer.worth.toLocaleString()} ${offer.currency} · ${offer.left} of ${offer.plays} cash-ins left today`;
    button.textContent = `Cash in ${offer.worth.toLocaleString()}`;
  }
}

function showCashed(paid) {
  $("cashin").hidden = true;
  toast(`+${paid.paid.toLocaleString()} ${paid.currency}! ${plural(paid.left, "cash-in")} left today`);
  sound.play("win");
}

// ---------- Payout settings (server admins) ----------

async function loadPayouts() {
  try {
    showPayouts(await page.hub.api("payouts"));
  } catch (e) {
    console.warn("Marble Munch: couldn't load the payout settings", e);
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
  $("payouts-rate-label").textContent = `${state.currency[0].toUpperCase()}${state.currency.slice(1)} per marble`;
  fillPayouts(state.settings);
}

function fillPayouts(settings) {
  $("payouts-on").checked = settings.on;
  for (const name of ["rate", "cap", "plays"]) {
    $(`payouts-${name}`).value = String(settings[name]);
  }
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

function cashIn() {
  if (send({ cashin: true })) {
    $("cashin-button").disabled = true;
  }
}

function applyState(state) {
  const before = page.state;
  page.state = state;
  page.mySeat = findMySeat(state.seats);
  $("app").dataset.stage = state.stage;
  page.scene.setSeats(state.seats.map((seat) => seat.kind));
  page.scene.setMySeat(page.mySeat, state.stage === "playing");
  // The round's last update arrives inside the results snapshot, so it slides in and pops like any other update
  const sameBoard = before && (before.stage === state.stage || (before.stage === "playing" && state.stage === "results"));
  if (sameBoard && state.board) {
    page.scene.push(state.board);
    noteLeft(state.board);
  } else {
    page.scene.reset(state.board);
    page.left = state.board ? state.board.left : null;
  }
  renderScores(state);
  renderStatus(state);
  page.scene.setNames(state.seats.map(tagFor));
  renderWatchers();
  report(state);
  if (state.stage !== "playing") {
    letGo();
  }
  stageSounds(before, state);
}

function applyFrame(frame) {
  page.updates += 1;
  page.scene.push(frame);
  renderPoints(frame.s);
  if (page.state) {
    report({ ...page.state, board: frame });
  }
  showLeft(frame);
  noteLeft(frame);
}

// A little shake when the last marble is eaten
function noteLeft(board) {
  if (page.left > 0 && board.left === 0) {
    page.scene.shake();
  }
  page.left = board.left;
}

function findMySeat(seats) {
  const index = seats.findIndex((seat) => seat.kind === "human" && seat.id === page.hub.player.id);
  return index === -1 ? null : index;
}

function stageSounds(before, state) {
  const was = before ? before.stage : null;
  if (state.stage === "starting" && (was !== "starting" || before.left !== state.left)) {
    sound.play("beep");
  }
  if (state.stage === "playing" && was === "starting") {
    sound.play("go");
    flash("Munch!");
  }
  if (state.stage === "results" && was === "playing") {
    sound.play(state.winners.includes(page.mySeat) ? "win" : "end");
  }
}

function effect(kind, seat) {
  if (kind === "snap") {
    sound.play("chomp", seat === page.mySeat);
  } else if (kind === "pop") {
    sound.play("gulp");
  } else if (kind === "score" && seat === page.mySeat) {
    sound.play("score");
  }
}

// The update rate next to the hub's frame rate counter, only while a round streams updates
function showRate() {
  page.hub.stat(page.state?.stage === "playing" ? `${page.updates} TPS` : "");
  page.updates = 0;
}

// ---------- Who's here ----------

// A name tag over a hippo. Long names are cut so a tag stays near its own hippo, and "(away)" goes under the name
function tagFor(seat) {
  if (seat.kind === "empty") {
    return "";
  }
  const letters = characters(seat.name);
  const name = letters.length > TAG_NAME_MAX ? `${letters.slice(0, TAG_NAME_MAX - 1).join("")}…` : seat.name;
  return seat.away ? `${name}\n(away)` : name;
}

// What the rest of the window sees this player doing, and whether a round is on for them
function activity(state) {
  const seat = page.mySeat;
  if (seat === null) {
    return ["Watching", null, false];
  }
  const marbles = state.board ? state.board.s[seat] : 0;
  const live = state.stage === "playing" || state.stage === "starting";
  let text = "Waiting for a round";
  if (live) {
    text = `${SEAT_COLORS[seat]} hippo · ${plural(marbles, "marble")}`;
  } else if (state.stage === "results" && state.seats[seat].played) {
    // A seat taken during the results still holds the last player's marbles, but this player didn't play the round
    text = state.winners.includes(seat) ? `Won with ${plural(marbles, "marble")}` : `Ate ${plural(marbles, "marble")}`;
  }
  return [text, { seat, marbles }, live];
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
  if (page.hub.status && state && !page.closed) {
    tell(...activity(state));
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveRound() {
  page.closed = true;
  if (page.hub.status) {
    tell("Not connected", null, false);
  }
}

// The people here who aren't at the board, from the hub's list
function renderWatchers() {
  const state = page.state;
  if (!state) {
    return;
  }
  const people = page.hub.people || [];
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
  const box = $("watching");
  box.hidden = !count;
  if (!count) {
    box.replaceChildren();
    return;
  }
  const faces = shown.map(watcherFace);
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = `${count} watching`;
  const more = count - faces.length;
  if (more > 0 && faces.length) {
    const extra = document.createElement("span");
    extra.className = "more";
    extra.textContent = `+${more}`;
    faces.push(extra);
  }
  box.replaceChildren(...faces, label);
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
  // The name sits between marks that keep a right-to-left name from turning the sentence around
  face.addEventListener("click", () => toast(person.you ? "That's you." : `\u2068${person.name}\u2069 is watching.`));
  return face;
}

// ---------- The screen ----------

function renderScores(state) {
  const scores = state.board ? state.board.s : [0, 0, 0, 0];
  $("scores").replaceChildren(...state.seats.map((seat, index) => scoreCard(seat, index, scores[index])));
  renderPoints(scores);
}

function scoreCard(seat, index, score) {
  const card = document.createElement("li");
  card.className = `score seat-${index}`;
  card.dataset.kind = seat.kind;
  card.classList.toggle("mine", index === page.mySeat);
  const avatar = document.createElement("img");
  avatar.className = "avatar";
  avatar.alt = "";
  avatar.src = seat.kind === "human" && seat.avatar ? seat.avatar : `art/hippo_head_closed_p${index + 1}.svg`;
  const name = document.createElement("span");
  name.className = "name";
  // Names come from Discord, so they only ever go in as text
  name.textContent = seat.kind === "empty" ? "Empty seat" : seat.name;
  if (seat.kind === "npc") {
    name.append(tag("NPC"));
  }
  if (seat.away) {
    name.append(tag("Away"));
  }
  const points = document.createElement("span");
  points.className = "points";
  points.textContent = String(score);
  card.append(avatar, name, points);
  return card;
}

function tag(text) {
  const node = document.createElement("span");
  node.className = "tag";
  node.textContent = text;
  return node;
}

function renderPoints(scores) {
  const best = Math.max(...scores);
  [...$("scores").children].forEach((card, index) => {
    const points = card.querySelector(".points");
    const text = String(scores[index]);
    if (points.textContent !== text) {
      points.textContent = text;
      // Restart the bump, even if the last one is still playing
      points.classList.remove("bump");
      void points.offsetWidth;
      points.classList.add("bump");
    }
    card.classList.toggle("leader", best > 0 && scores[index] === best);
  });
}

function renderStatus(state) {
  const seated = page.mySeat !== null;
  const stage = state.stage;
  $("start").hidden = !(seated && stage === "waiting" && state.countdown !== null);
  $("stand").hidden = !(seated && (stage === "waiting" || stage === "results"));
  $("munch").hidden = !(seated && stage === "playing");
  $("open-leaderboard").hidden = stage !== "waiting";
  $("hint").textContent = hintFor(state);
  showLeft(state.board);
  const [big, small] = overlayText(state);
  showOverlay(big, small);
}

function hintFor(state) {
  const stage = state.stage;
  if (page.mySeat === null) {
    return stage === "waiting" || stage === "results" ? "Tap an empty hippo to sit down." : "You're watching this round.";
  }
  if (stage === "playing" || stage === "starting") {
    return touchScreen.matches
      ? "Hold the munch button to stretch out. Let go to munch."
      : "Hold Space or press the board to stretch out. Let go to munch.";
  }
  return "You're in! The round starts soon, or press Start to go now.";
}

function overlayText(state) {
  if (state.stage === "waiting") {
    return state.countdown === null ? ["", ""] : [String(state.countdown), "until the round starts"];
  }
  if (state.stage === "starting") {
    return [String(state.left), "Get ready"];
  }
  if (state.stage === "results") {
    return [resultTitle(state), "Next round soon"];
  }
  return ["", ""];
}

function resultTitle(state) {
  if (!state.winners.length) {
    return "Nobody munched a marble";
  }
  if (state.winners.length > 1) {
    return "It's a tie!";
  }
  return `${state.seats[state.winners[0]].name} wins!`;
}

function showLeft(board) {
  if (!board) {
    $("left").textContent = "20 marbles a round";
    return;
  }
  const minutes = Math.floor(board.time / 60);
  const seconds = String(board.time % 60).padStart(2, "0");
  $("left").textContent = `${plural(board.left, "marble")} left · ${minutes}:${seconds}`;
}

function showOverlay(big, small) {
  $("overlay").hidden = !big;
  $("overlay-big").textContent = big;
  $("overlay-small").textContent = small;
}

function flash(text) {
  showOverlay(text, "");
  clearTimeout(page.flashTimer);
  page.flashTimer = setTimeout(() => {
    if (page.state?.stage === "playing") {
      showOverlay("", "");
    }
  }, 700);
}

function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 2500);
}

// ---------- Buttons ----------

function bindButtons() {
  click("back", () => backToMenu());
  click("start", () => send({ start: true }));
  click("stand", () => send({ stand: true }));
  click("open-leaderboard", openLeaderboard);
  click("cashin-button", cashIn);
  click("open-payouts", () => $("payouts").showModal());
  click("close-payouts", () => $("payouts").close());
  click("save-payouts", savePayouts);
  click("reset-payouts", () => {
    fillPayouts(page.payouts.defaults);
    $("payouts-status").textContent = "Reset. Save to keep it.";
  });
  click("close-leaderboard", () => $("leaderboard").close());
  click("music", () => {
    sound.setMusic(!sound.musicOn);
    showToggles();
  });
  click("sfx", () => {
    sound.setSfx(!sound.sfxOn);
    showToggles();
  });
  showToggles();
}

function click(id, handler) {
  $(id).addEventListener("click", (event) => {
    // A focused button would also take the Space key the hippo uses
    event.currentTarget.blur();
    handler();
  });
}

function showToggles() {
  $("music").setAttribute("aria-pressed", String(sound.musicOn));
  $("sfx").setAttribute("aria-pressed", String(sound.sfxOn));
}

function send(data) {
  return page.conn ? page.conn.send(data) : false;
}

function sit(seat) {
  const stage = page.state?.stage;
  if (page.mySeat === null && (stage === "waiting" || stage === "results")) {
    send({ sit: seat });
  }
}

// ---------- Holding to stretch ----------

function bindInput() {
  window.addEventListener("keydown", (event) => {
    if (event.code !== "Space") {
      return;
    }
    event.preventDefault();
    // Held keys repeat; only the first press counts
    if (!event.repeat) {
      press();
    }
  });
  window.addEventListener("keyup", (event) => {
    if (event.code === "Space") {
      event.preventDefault();
      letGo();
    }
  });
  holdable($("board"));
  holdable($("munch"));
  // Losing the window or hiding the page counts as letting go, so a hippo can't get stuck stretched out
  window.addEventListener("blur", letGo);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      letGo();
    }
  });
}

function holdable(element) {
  element.addEventListener("pointerdown", (event) => {
    if (!canSteer()) {
      return;
    }
    event.preventDefault();
    // A finger stays tied to what it first touched, so sliding off would never count. Untying it makes
    // sliding off the button (or the mouse off the board) a let go
    if (element.hasPointerCapture(event.pointerId)) {
      element.releasePointerCapture(event.pointerId);
    }
    press();
  });
  for (const name of ["pointerup", "pointercancel", "pointerleave"]) {
    element.addEventListener(name, letGo);
  }
}

function canSteer() {
  return page.mySeat !== null && page.state?.stage === "playing";
}

function press() {
  if (!canSteer() || page.held) {
    return;
  }
  page.held = true;
  page.scene.setHeld(true);
  send({ press: true });
}

function letGo() {
  if (!page.held) {
    return;
  }
  page.held = false;
  page.scene?.setHeld(false);
  send({ release: true });
}

// ---------- Leaderboard ----------

async function openLeaderboard() {
  $("leaders").replaceChildren();
  $("you").textContent = "Loading...";
  $("leaderboard").showModal();
  if (!page.hub || page.hub.offline) {
    $("you").textContent = "Open Marble Munch in Discord to see the leaderboard.";
    return;
  }
  try {
    renderLeaders(await page.hub.api("leaderboard"));
  } catch (e) {
    $("you").textContent = e.message;
  }
}

function renderLeaders(board) {
  $("leaders").replaceChildren(...board.top.map(leaderRow));
  if (!board.top.length) {
    $("you").textContent = "No rounds yet. Be the first!";
  } else if (board.you) {
    $("you").textContent = `You: #${board.you.rank} with ${plural(board.you.wins, "win")}`;
  } else {
    $("you").textContent = "Finish a round to get on the board.";
  }
}

function leaderRow(row) {
  const item = document.createElement("li");
  item.classList.toggle("mine", row.id === page.hub.player?.id);
  const place = document.createElement("span");
  place.className = "place";
  place.textContent = `#${row.rank}`;
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = row.name;
  const numbers = document.createElement("span");
  numbers.className = "numbers";
  numbers.textContent = `${plural(row.wins, "win")} · ${plural(row.marbles, "marble")} · ${plural(row.rounds, "round")}`;
  item.append(place, name, numbers);
  return item;
}

start();
