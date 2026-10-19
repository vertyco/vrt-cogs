// Tanks' page: the live connection, the bot's snapshots and shots, and the player's input on their turn.
// The bot runs the game; this page sends seat, setup, shop and turn requests, and shows what the bot sends back.
import { backToMenu, connect } from "activityhub";
import * as panels from "./panels.js";
import { Playback } from "./playback.js";
import { characters, createScene } from "./scene.js";
import { Sound } from "./sound.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Tanks again.",
  1011: "Couldn't join the game.",
  4003: "Tanks was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
// The same numbers as tanks/common (tests/test_page.py checks they match)
const STEP_RATE = 25;
const TICK_RATE = 20;
// Held keys move the barrel and power once per step of the original's clock, as the original did
const ANGLE_STEP = 2;
const POWER_STEP = 1;
// A held − or + button beside a slider waits this long after its first step, then steps at the original's pace
const NUDGE_DELAY_MS = 350;
const NUDGE_EVERY_MS = 1000 / STEP_RATE;
// Aim and drive go out at most once per update of the bot's loop
const SEND_MS = 1000 / TICK_RATE;
// How close to your own tank a press has to start to aim by dragging, in field pixels
const GRAB_DISTANCE = 30;
const WATCHER_FACES = 6;
const touchScreen = window.matchMedia("(pointer: coarse)");
const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  scene: null,
  state: null,
  mySeat: null,
  live: null,
  playback: null,
  // Snapshots and live updates that arrive while a shot plays wait for it to finish
  waiting: [],
  aim: { angle: 90, power: 50 },
  sentAim: null,
  aimTimer: null,
  lastAimSend: 0,
  touchedAt: 0,
  drive: 0,
  keys: new Set(),
  dragging: false,
  picking: null,
  updates: 0,
  toastTimer: null,
  preview: false,
  // What the watcher row last showed, so an identical list leaves its faces alone
  watchLook: null,
  // The status last given to the hub, and whether the game's connection has closed for good
  reported: null,
  closed: false,
};

function $(id) {
  return document.getElementById(id);
}

function ordinal(n) {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${suffix}`;
}

// ---------- Starting ----------

async function start() {
  bindButtons();
  try {
    page.scene = await createScene($("field"));
  } catch (e) {
    console.error("Tanks: couldn't start drawing", e);
    showMessage("This device couldn't start the game's graphics.");
    return;
  }
  page.scene.onEvent = sceneEvent;
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
    await showPreview();
    return;
  }
  panels.setSender(send);
  bindInput();
  setInterval(stepKeys, 1000 / STEP_RATE);
  setInterval(showRate, 1000);
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    showMessage(CLOSED_BECAUSE[e.status] || e.message);
    leaveMatch();
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    stopDriving();
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    showMessage(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
    leaveMatch();
  });
}

function showMessage(text) {
  showOverlay("Sorry!", text);
  $("hint").textContent = text;
}

// ---------- The browser preview ----------

// Outside Discord the page plays a recording of two computer tanks, made by the bot's own match code
async function showPreview() {
  page.preview = true;
  $("setup").hidden = true;
  showOverlay("Preview", "Open Tanks in Discord to play.");
  $("hint").textContent = hintFor(null);
  let recording;
  try {
    const resp = await fetch("demo.json");
    recording = await resp.json();
  } catch (e) {
    console.warn("Tanks: couldn't load the preview", e);
    return;
  }
  const replay = () => {
    page.playback = null;
    page.waiting = [];
    recording.forEach(([tick, message]) => setTimeout(() => receive(message), (tick * 1000) / TICK_RATE));
    const last = recording[recording.length - 1][0];
    setTimeout(replay, (last * 1000) / TICK_RATE + 3000);
  };
  replay();
}

// ---------- Messages from the bot ----------

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  if (data.shot) {
    startShot(data.shot);
  } else if (data.state || data.t) {
    if (page.playback) {
      page.waiting.push(data);
    } else {
      apply(data);
    }
  } else if (data.notice) {
    toast(data.notice);
  }
}

function apply(data) {
  if (data.state) {
    applyState(data.state);
  } else {
    applyLive(data.t);
  }
}

function applyState(state) {
  const before = page.state;
  page.state = state;
  page.mySeat = findMySeat(state.seats);
  if (state.stage !== "playing" || state.turn !== before?.turn) {
    page.live = null;
  }
  $("app").dataset.stage = state.stage;
  page.scene.setState(state);
  if (myTurn() && (before?.turn !== state.turn || before?.stage !== "playing")) {
    startMyTurn();
  }
  if (!myTurn()) {
    stopDriving();
    stopPicking();
  }
  render();
  stageSounds(before, state);
}

function applyLive(live) {
  page.updates += 1;
  const changedAngle = page.live && page.live[3] !== live[3];
  page.live = live;
  if (myTurn()) {
    // Your own barrel and power answer at once; the bot's numbers take over once you've stopped touching them
    if (performance.now() - page.touchedAt > 600) {
      page.aim = { angle: live[3], power: live[4] };
    }
  } else {
    page.aim = { angle: live[3], power: live[4] };
    if (changedAngle) {
      sound.play("turret");
    }
  }
  page.scene.setLive(live, myTurn() ? page.aim : null);
  panels.renderInfo(page.state, page.live, page.aim);
}

function findMySeat(seats) {
  const index = seats.findIndex((seat) => seat.kind === "human" && seat.id === page.hub?.player?.id);
  return index === -1 ? null : index;
}

function myTurn() {
  const state = page.state;
  if (!state || state.stage !== "playing" || page.mySeat === null || state.turn !== page.mySeat) {
    return false;
  }
  return !page.playback && !state.seats[page.mySeat].standIn;
}

function startMyTurn() {
  const tank = page.state.tanks[page.mySeat];
  page.aim = { angle: tank.angle, power: tank.power };
  page.sentAim = [tank.angle, tank.power];
  page.touchedAt = 0;
}

function stageSounds(before, state) {
  if (state.stage === "shop" && before?.stage !== "shop") {
    sound.play("shop");
  }
}

// ---------- Shots ----------

function startShot(script) {
  if (page.playback) {
    // A new shot while the last one still plays: this screen fell behind, so the last one jumps to its end
    page.playback.finish(page.scene);
  }
  stopDriving();
  stopPicking();
  page.dragging = false;
  page.playback = new Playback(script, performance.now());
  page.scene.onFrame = (now) => runShot(now);
  if (script.weapon === panels.AIR_STRIKE) {
    // The original's air strike booms as the planes are called in
    sound.play("boom_big");
  } else if (script.shells.length) {
    page.scene.startShot(script.seat);
  }
  render();
}

function runShot(now) {
  if (!page.playback.update(now, page.scene)) {
    return;
  }
  page.playback = null;
  page.scene.onFrame = null;
  const waiting = page.waiting;
  page.waiting = [];
  waiting.forEach(apply);
  render();
}

function sceneEvent(kind, detail) {
  if (kind === "boom") {
    sound.play(detail);
  } else if (kind === "die") {
    sound.play("tank_death");
  } else if (kind === "tank") {
    panels.updateCard(detail.seat, detail.view);
  }
}

// ---------- The screen ----------

function render() {
  const state = page.state;
  if (!state) {
    return;
  }
  panels.renderCards(state, page.mySeat);
  panels.renderSetup(state, page.mySeat);
  panels.renderShop(state, page.mySeat);
  panels.renderResults(state, page.mySeat);
  panels.renderInfo(state, page.live, shownAim());
  renderControls();
  renderWatchers();
  report(state);
  $("hint").textContent = hintFor(state);
}

function shownAim() {
  if (myTurn() || page.live) {
    return page.aim;
  }
  const tank = page.state.turn === null ? null : page.state.tanks[page.state.turn];
  return tank ? { angle: tank.angle, power: tank.power } : page.aim;
}

function renderControls() {
  const mine = myTurn();
  // On your turn the angle and power show beside their sliders, so the bar above leaves them out
  $("info").classList.toggle("mine", mine);
  // A seated player keeps the controls' room between turns, so the field doesn't jump in size every turn
  $("controls").hidden = !(page.mySeat !== null && page.state.stage === "playing");
  $("controls").classList.toggle("waiting", !mine);
  if (!mine) {
    return;
  }
  const kit = page.state.kits[page.mySeat];
  const tank = page.state.tanks[page.mySeat];
  panels.renderWeapons(kit, page.live ? page.live[6] : kit.weapon);
  panels.renderItems(kit, tank, useItem);
  showAim(tank.health);
}

// The sliders and the numbers beside them. Power can't go past the tank's health, so the bar is shaded from there
function showAim(health) {
  const angle = page.aim.angle;
  const power = Math.round(page.aim.power);
  $("angle").value = String(angle);
  $("power").value = String(power);
  $("angle-value").textContent = `${angle}°`;
  $("power-value").textContent = String(power);
  paintSlider($("angle"), angle / 180, 1);
  paintSlider($("power"), power / 100, Math.min(100, health) / 100);
}

function paintSlider(input, fill, reach) {
  input.style.setProperty("--fill", `${fill * 100}%`);
  input.style.setProperty("--reach", `${reach * 100}%`);
}

function hintFor(state) {
  if (page.preview) {
    return "This is the browser preview. Open Tanks in Discord to play.";
  }
  const seated = page.mySeat !== null;
  if (state.stage === "setup") {
    if (!seated) {
      return "Tap an empty seat to sit down.";
    }
    return state.host === page.mySeat ? "Add computer tanks if you like, then press Start." : "Waiting for the host.";
  }
  if (state.stage === "shop") {
    if (seated && !state.done[page.mySeat]) {
      return "Buy weapons and extras, then press Done.";
    }
    return "The players are shopping.";
  }
  if (state.stage === "results") {
    return state.host === page.mySeat ? "Press Continue for a new match." : "Waiting for the host.";
  }
  if (myTurn()) {
    return touchScreen.matches
      ? "Your turn! Drag from your tank to aim, then press Fire."
      : "Your turn! Arrows aim and drive, Page Up and Down set power, Space fires. Or drag from your tank.";
  }
  return seated ? "Waiting for your turn." : "You're watching this match.";
}

// ---------- Who's here ----------

// What the rest of the window sees this player doing: a status line, its data, and whether a match is on for them
function activity(state) {
  const seat = page.mySeat;
  if (seat === null) {
    return ["Watching", null, false];
  }
  const data = { seat };
  if (state.stage === "setup") {
    return ["Setting up", data, false];
  }
  if (state.stage === "results") {
    return [finishedText(state, seat), data, false];
  }
  if (state.stage === "shop") {
    // The shop opens before each round, so it is for the next one
    return [`Shopping · round ${state.round + 1} of ${state.rounds}`, data, true];
  }
  // A computer plays an away player's tank, so its turn isn't the player's to aim
  const aiming = state.turn === seat && !state.seats[seat].standIn;
  const round = `${state.round} of ${state.rounds}`;
  return [aiming ? `Aiming · round ${round}` : `Round ${round}`, data, true];
}

function finishedText(state, seat) {
  const results = state.results || [];
  const mine = results.find((row) => row.seat === seat);
  if (!mine) {
    return "Finished";
  }
  return `Finished ${ordinal(1 + results.filter((row) => row.score > mine.score).length)}`;
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
  if (page.hub?.status && !page.closed) {
    tell(...activity(state));
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveMatch() {
  page.closed = true;
  if (page.hub?.status) {
    tell("Not connected", null, false);
  }
}

// The people here who aren't in a tank, from the hub's list
function renderWatchers() {
  const state = page.state;
  if (!state) {
    return;
  }
  const people = page.hub?.people || [];
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
  face.addEventListener("click", () => {
    // A focused button would also take the Space key that fires
    face.blur();
    // The name sits between marks that keep a right-to-left name from turning the sentence around
    toast(person.you ? "That's you." : `⁨${person.name}⁩ is watching.`);
  });
  return face;
}

function showOverlay(big, small) {
  $("overlay").hidden = !big;
  $("overlay-big").textContent = big;
  $("overlay-small").textContent = small;
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

// The live update rate next to the hub's frame rate counter, only while a turn's updates flow
function showRate() {
  page.hub.stat(page.state?.stage === "playing" && page.updates ? `${page.updates} TPS` : "");
  page.updates = 0;
}

// ---------- Buttons ----------

function bindButtons() {
  click("back", () => backToMenu());
  click("sound", () => {
    sound.setOn(!sound.on);
    $("sound").setAttribute("aria-pressed", String(sound.on));
  });
  $("sound").setAttribute("aria-pressed", String(sound.on));
  click("start", () => send({ start: true }));
  click("stand", () => send({ stand: true }));
  click("done", () => send({ done: true }));
  click("continue", () => send({ continue: true }));
  click("open-leaderboard", openLeaderboard);
  click("close-leaderboard", () => $("leaderboard").close());
  click("fire", fire);
  click("flip", flip);
  click("cancel-pick", stopPicking);
  // The original clicks when a setup option is ticked
  $("setup").addEventListener("change", () => sound.play("click"));
  $("rounds").addEventListener("change", () => send({ rounds: Number($("rounds").value) }));
  $("landscape").addEventListener("change", () => {
    const value = $("landscape").value;
    send({ landscape: value === "random" ? "random" : Number(value) });
  });
  $("timer").addEventListener("change", () => {
    const value = $("timer").value;
    send({ timer: value === "off" ? "off" : Number(value) });
  });
  $("weapon").addEventListener("change", () => send({ weapon: Number($("weapon").value) }));
  $("angle").addEventListener("input", () => setAim(Number($("angle").value), page.aim.power));
  $("power").addEventListener("input", () => setAim(page.aim.angle, Number($("power").value)));
  holdToNudge($("angle-down"), -1, 0);
  holdToNudge($("angle-up"), 1, 0);
  holdToNudge($("power-down"), 0, -1);
  holdToNudge($("power-up"), 0, 1);
  holdToDrive($("drive-left"), -1);
  holdToDrive($("drive-right"), 1);
}

// A − or + button beside a slider: one step on a tap, then steady steps while it's held
function holdToNudge(element, angleStep, powerStep) {
  let timer = null;
  const step = () => setAim(page.aim.angle + angleStep, page.aim.power + powerStep);
  const stop = () => {
    clearTimeout(timer);
    clearInterval(timer);
    timer = null;
  };
  element.addEventListener("pointerdown", (event) => {
    // Keeps focus off the button, so Space still fires
    event.preventDefault();
    stop();
    step();
    timer = setTimeout(() => {
      timer = setInterval(step, NUDGE_EVERY_MS);
    }, NUDGE_DELAY_MS);
  });
  for (const name of ["pointerup", "pointercancel", "pointerleave"]) {
    element.addEventListener(name, stop);
  }
  // Enter or Space on a focused button, which sends a click with no pointer press before it
  element.addEventListener("click", (event) => {
    if (event.detail === 0) {
      step();
    }
  });
}

function click(id, handler) {
  $(id).addEventListener("click", (event) => {
    // A focused button would also take the Space key that fires
    event.currentTarget.blur();
    handler();
  });
}

function send(data) {
  return page.conn ? page.conn.send(data) : false;
}

function useItem(item) {
  if (item === "teleport") {
    startPicking("teleport");
  } else {
    send({ use: item });
  }
}

// ---------- Aiming ----------

function setAim(angle, power) {
  if (!myTurn()) {
    return;
  }
  const health = page.state.tanks[page.mySeat].health;
  const next = {
    angle: Math.max(0, Math.min(180, Math.round(angle))),
    power: Math.max(0, Math.min(100, health, Math.round(power))),
  };
  if (next.angle !== page.aim.angle) {
    sound.play("turret");
  }
  page.aim = next;
  page.touchedAt = performance.now();
  page.scene.setLive(page.live, page.aim);
  panels.renderInfo(page.state, page.live, page.aim);
  showAim(health);
  queueAim();
}

// Sent at most once per update of the bot's loop, and the last change always goes out
function queueAim() {
  if (page.aimTimer !== null) {
    return;
  }
  const wait = Math.max(0, page.lastAimSend + SEND_MS - performance.now());
  page.aimTimer = setTimeout(() => {
    page.aimTimer = null;
    const aim = [page.aim.angle, page.aim.power];
    if (myTurn() && (!page.sentAim || aim[0] !== page.sentAim[0] || aim[1] !== page.sentAim[1])) {
      page.lastAimSend = performance.now();
      page.sentAim = aim;
      send({ aim });
    }
  }, wait);
}

function fire() {
  if (!myTurn()) {
    return;
  }
  const weapon = page.live ? page.live[6] : page.state.kits[page.mySeat].weapon;
  if (weapon === panels.AIR_STRIKE) {
    startPicking("strike");
    return;
  }
  // The latest aim goes first, so the shot uses exactly what the player sees
  send({ aim: [page.aim.angle, page.aim.power] });
  send({ fire: true });
}

// ---------- Picking a spot on the field: air strike and teleport ----------

function startPicking(kind) {
  if (!myTurn()) {
    return;
  }
  stopDriving();
  page.picking = { kind, dir: 1 };
  $("picking").hidden = false;
  $("flip").hidden = kind !== "strike" || !touchScreen.matches;
  showPicking();
}

function showPicking() {
  const picking = page.picking;
  if (picking.kind === "teleport") {
    $("picking-text").textContent = "Tap where to teleport.";
  } else {
    const from = picking.dir === 1 ? "left" : "right";
    $("picking-text").textContent = touchScreen.matches
      ? `Tap the target. The planes come from the ${from}.`
      : `Click the target. The planes come from the ${from}; the arrow keys change sides.`;
  }
  page.scene.setPicking(picking);
}

function flip() {
  if (page.picking?.kind === "strike") {
    page.picking.dir = -page.picking.dir;
    showPicking();
  }
}

function stopPicking() {
  page.picking = null;
  $("picking").hidden = true;
  page.scene?.setPicking(null);
}

function pick(x, y) {
  const picking = page.picking;
  stopPicking();
  if (picking.kind === "strike") {
    send({ fire: [Math.round(x), picking.dir] });
  } else {
    send({ use: ["teleport", Math.round(x), Math.round(y)] });
  }
}

// ---------- Driving ----------

function holdToDrive(element, direction) {
  element.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    if (element.hasPointerCapture(event.pointerId)) {
      element.releasePointerCapture(event.pointerId);
    }
    setDrive(direction);
  });
  for (const name of ["pointerup", "pointercancel", "pointerleave"]) {
    element.addEventListener(name, () => setDrive(0));
  }
}

function setDrive(direction) {
  if (direction !== 0 && !myTurn()) {
    return;
  }
  if (direction === page.drive) {
    return;
  }
  page.drive = direction;
  page.scene.setDriving(direction);
  send({ drive: direction });
}

function stopDriving() {
  if (page.drive !== 0) {
    setDrive(0);
  }
}

// ---------- Keyboard and dragging ----------

const KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Space", "Escape"]);

function bindInput() {
  window.addEventListener("keydown", (event) => {
    if (!KEYS.has(event.code) || event.target instanceof HTMLSelectElement) {
      return;
    }
    event.preventDefault();
    if (!event.repeat) {
      keyPressed(event.code);
    }
    page.keys.add(event.code);
  });
  window.addEventListener("keyup", (event) => {
    page.keys.delete(event.code);
    if ((event.code === "ArrowLeft" || event.code === "ArrowRight") && !page.picking) {
      setDrive(page.keys.has("ArrowLeft") ? -1 : page.keys.has("ArrowRight") ? 1 : 0);
    }
  });
  // Losing the window or hiding the page lets go of every key, so a tank can't drive on by itself
  window.addEventListener("blur", letGoOfKeys);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      letGoOfKeys();
    }
  });
  page.scene.onPointer = fieldPointer;
}

function letGoOfKeys() {
  page.keys.clear();
  stopDriving();
}

function keyPressed(code) {
  if (code === "Escape") {
    stopPicking();
  } else if (page.picking && (code === "ArrowLeft" || code === "ArrowRight")) {
    page.picking.dir = code === "ArrowLeft" ? 1 : -1;
    showPicking();
  } else if (code === "ArrowLeft" || code === "ArrowRight") {
    setDrive(code === "ArrowLeft" ? -1 : 1);
  } else if (code === "Space" && !page.picking) {
    fire();
  }
}

// Held keys step the barrel and power at the original's 25 steps a second
function stepKeys() {
  if (!myTurn() || page.picking) {
    return;
  }
  const keys = page.keys;
  // As in the original, Up turns the barrel toward the right and Down toward the left
  const turn = (keys.has("ArrowUp") ? ANGLE_STEP : 0) - (keys.has("ArrowDown") ? ANGLE_STEP : 0);
  const power = (keys.has("PageUp") ? POWER_STEP : 0) - (keys.has("PageDown") ? POWER_STEP : 0);
  if (turn || power) {
    setAim(page.aim.angle + turn, page.aim.power + power);
  }
}

// Presses on the field, in field pixels. `kind` is "down", "move" or "up"
function fieldPointer(kind, x, y) {
  if (page.picking) {
    page.scene.setPicking({ ...page.picking, x, y });
    if (kind === "down") {
      pick(x, y);
    }
    return;
  }
  if (!myTurn()) {
    return;
  }
  const tank = page.scene.tankPosition(page.mySeat);
  if (kind === "down") {
    page.dragging = Math.hypot(x - tank.x, y - tank.y) <= GRAB_DISTANCE;
  }
  if (page.dragging && kind !== "up") {
    dragAim(tank, x, y);
  }
  if (kind === "up") {
    page.dragging = false;
    page.scene.setAimLine(false);
  }
}

// The drag's direction sets the angle (0 points left, 90 up, 180 right) and its length the power
function dragAim(tank, x, y) {
  const dx = x - tank.x;
  const up = tank.y - 1 - y;
  const angle = up < 0 ? (dx < 0 ? 0 : 180) : 180 - (Math.atan2(up, dx) * 180) / Math.PI;
  setAim(angle, Math.hypot(dx, up));
  page.scene.setAimLine(true);
}

// ---------- Leaderboard ----------

async function openLeaderboard() {
  $("leaders").replaceChildren();
  $("you").textContent = "Loading...";
  $("leaderboard").showModal();
  if (!page.hub || page.hub.offline) {
    $("you").textContent = "Open Tanks in Discord to see the leaderboard.";
    return;
  }
  try {
    panels.renderLeaders(await page.hub.api("leaderboard"), page.hub.player?.id);
  } catch (e) {
    $("you").textContent = e.message;
  }
}

start();
