// Starhold's page: the live connection, the screens, and the run loop. The page plays the run itself with the rules
// in sim/, 30 steps a second, and sends the bot each input as a move, so the bot can replay the run when its score
// is about to pay out or reach the high score table.
import { backToMenu, connect } from "activityhub";
import { createScene } from "./render/scene.js";
import { BUILD, CALL, FORM, MAP, PARK, ROBOTS, SELL, STASIS, STEPS, STRIKE, UPGRADE } from "./sim/rules.js";
import { replay } from "./sim/replay.js";
import { apply, createRun, tick } from "./sim/run.js";
import { Sound } from "./sound.js";
import { Hud } from "./ui/hud.js";
import { InfoCard } from "./ui/info.js";
import {
  NOT_CONNECTED,
  askConfirm,
  bindPanels,
  isCashing,
  notice,
  onCashed,
  renderResult,
  showMessage,
} from "./ui/panels.js";
import { bindSettings, loadPayouts } from "./ui/settings.js";
import { disconnected, onPeople, report, showLive, watchPeople } from "./ui/strip.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Starhold again.",
  1011: "Couldn't join the game.",
  4003: "Starhold was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
  4100: "Starhold was opened somewhere else.",
};
const TAKEN_OVER = 4100;
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
const OFFLINE_PLAY = "Open Starhold in Discord to play.";
const GIVE_UP = "Start a new run? This run's cash-in will be given up.";
const RESUME_FAILED = "Couldn't bring your run back.";
const STEP_MS = 1000 / STEPS;
// A frame never plays more than this much missed time, so a page coming back from sleep doesn't rush ahead
const CATCH_UP_MS = 250;
// Progress goes to the bot every 5 seconds of play, so a reopened run lands where the player was
const AT_EVERY = 5 * STEPS;
// The gap kept between the field (where the map's pads and core go) and the bar or the screen's edges
const EDGE = 6;
// The friends strip's height, for placing it in the moon above the pads and the road on an upright map
const STRIP_HEIGHT = 28;
// How far the road's edge and a pad's edge reach from their middles, in map units
const ROAD_HALF = 33;
const PAD_REACH = 34;
const ACTIONS = { build: BUILD, upgrade: UPGRADE, form: FORM, sell: SELL };
const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  scene: null,
  hud: null,
  screen: "title",
  // The run on the page, its seed from the bot, and every move applied to it so far
  run: null,
  seed: null,
  moves: [],
  paused: false,
  // Over: [step, score, wave] as sent to the bot, and the numbers the game over card shows
  finished: false,
  claim: null,
  final: null,
  result: null,
  // A run the bot no longer holds (it restarted): it plays on, but can't be cashed in or saved
  orphan: false,
  // Waiting for the bot's hello, on a fresh page or a reconnect: it says which run the bot holds and which moves it
  // already has, so moves wait for it and Play does nothing until then
  syncing: true,
  // Opened somewhere else: this page's run stops for good
  stopped: false,
  acc: 0,
  last: 0,
  move: makeMove,
  clearFocus,
  sound,
};
window.starhold = { page, scene: null };
watchPeople(page);

function $(id) {
  return document.getElementById(id);
}

// The run's progress (moves, position, ending) isn't sent while reconnecting, because the join's reply resends exactly
// what the bot is missing, nor once the bot has stopped following the run
const PROGRESS = ["move", "at", "over"];

function send(data) {
  if ((page.syncing || page.orphan) && PROGRESS.some((name) => name in data)) {
    return false;
  }
  return page.conn ? page.conn.send(data) : false;
}

// ---------- Starting ----------

async function start() {
  bindPanels(page, { play, back: goBack, show: showScreen, resume: () => setPaused(false), endRun, cashIn, sound });
  bindSettings(page);
  try {
    page.scene = await createScene($("scene"));
  } catch (e) {
    console.warn("Starhold: couldn't start drawing", e);
    showMessage("This device couldn't start the game's graphics.");
    return;
  }
  window.starhold.scene = page.scene;
  page.scene.onPress = onPress;
  page.scene.onFrame = frame;
  page.hud = new Hud(page, { pause: () => setPaused(true) });
  page.info = new InfoCard();
  window.addEventListener("resize", layout);
  // The bar's size can change without a resize (the fonts arriving), which moves the field under it
  new ResizeObserver(layout).observe($("bar"));
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("keydown", onKey);
  showScreen("title");
  try {
    page.hub = await connect();
  } catch (e) {
    console.warn("Starhold: couldn't reach the hub", e);
    showMessage(CLOSED_BECAUSE[e.status] || CLOSED_OTHERWISE);
    return;
  }
  // Placed straight after connecting, so the hub never floats a button of its own over the game
  $("people").append(page.hub.peopleButton());
  page.hub.onPeople(onPeople);
  if (page.hub.offline) {
    return;
  }
  report();
  loadPayouts(page);
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    console.warn("Starhold: couldn't open the live connection", e);
    showMessage(CLOSED_BECAUSE[e.status] || CLOSED_OTHERWISE);
    // No hello will ever come, so Play falls through to saying it isn't connected instead of doing nothing
    page.syncing = false;
    disconnected();
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    page.syncing = true;
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    if (code === TAKEN_OVER) {
      stopRun();
    } else if (page.run && !page.finished) {
      // The bot can't hear this run any more, so it can't be checked
      page.orphan = true;
    }
    showMessage(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
    page.syncing = false;
    disconnected();
  });
}

// ---------- Messages from the bot ----------

const HANDLERS = {
  hello: onHello,
  run: (value) => beginRun(value.seed, createRun(value.seed), []),
  result: onResult,
  cashed: (value) => onCashed(page, value),
  notice: (text) => notice(page, text),
  elsewhere: (text) => {
    stopRun();
    showMessage(text);
  },
};

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  for (const [name, value] of Object.entries(data)) {
    HANDLERS[name]?.(value);
  }
}

// On every join, a reconnect included: the bot's open run, or its finished one
function onHello(hello) {
  page.syncing = false;
  if (page.stopped) {
    return;
  }
  const open = hello.run;
  if (open && page.run && open.seed === page.seed) {
    resync(open);
  } else if (open) {
    resumeRun(open);
  } else if (hello.result && page.run && page.finished) {
    onResult(hello.result);
  } else if (hello.result && !page.run) {
    showFinished(hello.result);
  } else if (page.run && !page.result) {
    // The page has a run the bot no longer holds: the bot restarted. It plays on, but can't be cashed in or saved
    page.orphan = true;
    renderResult(page);
  }
}

// After a dropped connection: the bot has every move the page sent before the drop, and none after. Those go
// again, in order, so the bot's copy of the run matches the page's
function resync(open) {
  const known = open.moves.length;
  const same = JSON.stringify(open.moves) === JSON.stringify(page.moves.slice(0, known));
  if (!same) {
    console.warn("Starhold: the bot's moves don't match this run's, so it can't be checked");
    page.orphan = true;
    return;
  }
  for (const move of page.moves.slice(known)) {
    send({ move });
  }
  send(page.finished ? { over: page.claim } : { at: page.run.step });
}

// The page was closed mid-run: play the bot's moves again from the seed, as fast as the phone can, to the latest
// step the bot has, and wait paused there
function resumeRun(open) {
  let run = null;
  try {
    run = replay(open.seed, open.moves, open.at);
  } catch (e) {
    console.warn("Starhold: couldn't replay the run to bring it back", e);
    showMessage(RESUME_FAILED);
    return;
  }
  beginRun(open.seed, run, open.moves.slice());
  if (run.over) {
    finishRun();
    return;
  }
  setPaused(true);
}

function beginRun(seed, run, moves) {
  run.events = [];
  Object.assign(page, { seed, run, moves, finished: false, claim: null, final: null, result: null });
  Object.assign(page, { orphan: false, stopped: false, acc: 0 });
  page.scene.resetRun(run);
  page.hud.startRun(run);
  showScreen("play");
  setPaused(false);
}

function onResult(result) {
  page.result = result;
  renderResult(page);
  report();
}

// A finished run the bot still holds, seen again on a fresh page: straight to its game over card
function showFinished(result) {
  Object.assign(page, { run: null, seed: null, moves: [], finished: true, claim: null, result, orphan: false });
  page.final = { score: result.score, wave: result.wave };
  showScreen("over");
  renderResult(page);
}

// ---------- The run loop ----------

function frame(now) {
  const elapsed = Math.min(Math.max(0, now - page.last), CATCH_UP_MS);
  page.last = now;
  const run = page.run;
  const playing = Boolean(run) && page.screen === "play";
  if (playing && !page.paused && !page.finished && !page.stopped) {
    page.acc += elapsed;
    while (page.acc >= STEP_MS && !page.finished) {
      page.acc -= STEP_MS;
      step(run);
    }
  }
  const scene = page.scene;
  if (scene.selected !== null && !(playing && run.robots.some((robot) => robot.id === scene.selected && !robot.gone))) {
    scene.selected = null;
  }
  scene.draw(playing ? run : null, Math.min(1, page.acc / STEP_MS));
  page.info.sync(playing ? run : null, scene);
  sound.walk(walkers(playing ? run : null));
  if (playing) {
    page.hud.update(run);
    report();
    showLive();
  }
}

// How many robots of each type are walking now (none while paused or off the play screen), for the footsteps
function walkers(run) {
  const walking = ROBOTS.map(() => 0);
  if (run && !page.paused && !page.finished && !page.stopped) {
    for (const robot of run.robots) {
      if (!robot.gone && robot.heldBy < 0 && robot.leaveAt <= run.step && robot.frozenUntil <= run.step) {
        walking[robot.type] += 1;
      }
    }
  }
  return walking;
}

function step(run) {
  page.scene.beforeTick(run);
  tick(run);
  sound.events(page.scene.takeEvents(run), run);
  if (run.step % AT_EVERY === 0) {
    send({ at: run.step });
  }
  if (run.over) {
    finishRun();
  }
}

// Every input goes through here: applied to the page's run at once (so it shows this frame), then sent
function makeMove(details) {
  const run = page.run;
  if (!run || page.finished || page.paused || page.stopped || page.screen !== "play") {
    return false;
  }
  const move = [run.step, ...details];
  if (!apply(run, move)) {
    return false;
  }
  page.moves.push(move);
  sound.events(page.scene.takeEvents(run), run);
  send({ move });
  return true;
}

function finishRun() {
  const run = page.run;
  if (!run || page.finished) {
    return;
  }
  page.finished = true;
  page.claim = [run.step, run.score, run.wave];
  page.final = { score: run.score, wave: run.wave };
  page.result = null;
  setPaused(false);
  send({ over: page.claim });
  showScreen("over");
  renderResult(page);
}

// End run in the pause menu: game over now, with the score so far
function endRun() {
  if (page.run && !page.finished && !page.stopped) {
    finishRun();
  }
}

function stopRun() {
  page.stopped = true;
  setPaused(false);
}

function setPaused(on) {
  const paused = Boolean(on && page.run && !page.finished && !page.stopped);
  page.paused = paused;
  if (paused) {
    document.body.dataset.paused = "1";
  } else {
    delete document.body.dataset.paused;
  }
  $("pause-menu").hidden = !paused;
  page.acc = 0;
  if (paused) {
    clearFocus();
    page.hud?.setAim(null);
    // So a run closed while paused comes back at exactly this step
    send({ at: page.run.step });
  }
  report();
}

function onVisibility() {
  if (document.hidden && page.screen === "play" && page.run && !page.finished) {
    setPaused(true);
  }
}

function onKey(event) {
  if (event.key === "Escape" && page.screen === "play" && !page.paused && !page.finished) {
    setPaused(true);
  }
}

// ---------- Taps on the map ----------

// Nothing in focus: the ring closed, parking stopped, the wave button and any tapped robot let go
function clearFocus() {
  const scene = page.scene;
  if (!scene) {
    return;
  }
  scene.ring.close();
  scene.ring.stopParking();
  scene.wave.unpick();
  scene.selected = null;
}

function onPress(press) {
  if (page.screen !== "play" || page.paused || page.finished || page.stopped || !page.run) {
    return;
  }
  const ring = page.scene.ring;
  const hit = ring.isOpen ? ring.hit(press.client) : null;
  if (page.hud.aim) {
    fireAt(page.hud.aim, press.map);
  } else if (ring.parking >= 0) {
    parkAt(press.map);
  } else if (hit) {
    pressRing(hit, press.touch);
  } else if (page.scene.wave.hit(press.client)) {
    pressWave(press.touch);
  } else {
    pressMap(press);
  }
}

function pressRing(hit, touch) {
  const ring = page.scene.ring;
  // On a touch screen a first tap on a priced choice shows what it is, and a second tap on it buys it
  if (touch && hit.preview && ring.picked !== hit.action) {
    ring.pick(hit.action);
    return;
  }
  // A grayed button (too dear) takes the tap and does nothing
  if (hit.enabled) {
    ringAction(hit.action);
  }
}

// The wave button: on a touch screen a first tap shows what the wave brings, and a second calls it
function pressWave(touch) {
  const wave = page.scene.wave;
  if (touch && !wave.picked) {
    clearFocus();
    wave.pick();
    return;
  }
  clearFocus();
  makeMove([CALL]);
}

// A pad opens its ring (or closes it, when it's already open), a robot shows its card, and anywhere else lets go
function pressMap(press) {
  const scene = page.scene;
  const spot = scene.spotAt(press.map);
  const open = spot >= 0 && spot !== scene.ring.spot;
  const robot = spot < 0 ? scene.robotAt(press.client) : null;
  clearFocus();
  if (open) {
    scene.ring.open(spot, page.run);
  } else if (robot !== null) {
    scene.selected = robot;
  }
}

function ringAction(action) {
  const ring = page.scene.ring;
  const [name, which] = action.split(":");
  const spot = ring.spot;
  if (name === "park") {
    ring.startParking(spot, page.run);
    return;
  }
  const details = [ACTIONS[name], spot];
  if (which !== undefined) {
    details.push(Number(which));
  }
  if (makeMove(details)) {
    ring.close();
  }
}

function parkAt(map) {
  const ring = page.scene.ring;
  const spot = ring.parking;
  const d = ring.parkTarget(map);
  ring.stopParking();
  if (d >= 0) {
    makeMove([PARK, spot, Math.round(d / 100)]);
  }
}

function fireAt(aim, map) {
  page.hud.setAim(null);
  const x = Math.round(map.x);
  const y = Math.round(map.y);
  if (x < 0 || y < 0 || x > MAP.width || y > MAP.height) {
    return;
  }
  makeMove([aim === "strike" ? STRIKE : STASIS, x, y]);
}

// ---------- Screens and layout ----------

async function play() {
  if (!page.hub || page.hub.offline) {
    showMessage(OFFLINE_PLAY);
    return;
  }
  // Until the bot's hello the bot's run isn't settled yet: a new one would take the old run's resent moves and progress
  if (page.syncing) {
    return;
  }
  const offer = page.result?.offer;
  // A cash-in already sent isn't given up: the bot still pays it. Its answer may arrive after the new run starts, and
  // the panels keep it off the new run's card
  if (offer && offer.left > 0 && offer.worth > 0 && !isCashing() && !(await askConfirm(GIVE_UP))) {
    return;
  }
  if (!send({ start: true })) {
    showMessage(NOT_CONNECTED);
  }
}

function cashIn() {
  return send({ cashin: true });
}

function goBack() {
  if (page.screen === "title") {
    backToMenu();
    return;
  }
  showScreen("title");
}

function showScreen(name) {
  page.screen = name;
  document.body.dataset.screen = name;
  for (const id of ["title", "help", "over"]) {
    $(id).hidden = id !== name;
  }
  $("hud").hidden = name !== "play";
  $("back").hidden = name === "play";
  if (name !== "play") {
    clearFocus();
    page.hud?.setAim(null);
  }
  layout();
  sound.setScene(name === "play" ? "play" : "menu");
  report();
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

// The run's map fills the screen: its pads and core go in the field, the part of the screen inside the bar and
// Discord's edges, turned whichever way draws them bigger. Outside a run the map covers the screen behind the menus
function layout() {
  placePeople();
  const scene = page.scene;
  if (scene) {
    const width = window.innerWidth;
    const height = window.innerHeight;
    if (page.screen === "play") {
      const safe = safeArea();
      const top = $("bar").getBoundingClientRect().bottom + EDGE;
      const field = { x: safe.left + EDGE, y: top, width: width - safe.left - safe.right - 2 * EDGE };
      scene.layout({ ...field, height: height - safe.bottom - EDGE - top });
    } else {
      scene.layout({ x: 0, y: 0, width, height }, true);
    }
    // tall: the map is drawn upright; wide: turned on its side
    document.body.classList.toggle("tall", !scene.turned);
    document.body.classList.toggle("wide", scene.turned);
    placeStrip();
  }
  showLive();
  page.info?.relayout();
}

// On an upright map the friends strip sits in the moon between the field's top and the first pads or road bend,
// right of where the road and the wave button come in, and a new robot's note sits over it there, clear of the road
// where the new robot walks in. On a turned map the strip sits in the bar, and the note at the top of the field in its
// middle
function placeStrip() {
  const scene = page.scene;
  const strip = $("strip").style;
  const news = $("news").style;
  const field = scene.field;
  if (scene.turned || page.screen !== "play") {
    strip.left = strip.top = strip.width = "";
    news.left = news.maxWidth = news.transform = "";
    news.top = `${field.y + EDGE}px`;
    return;
  }
  const road = scene.mapToClient(MAP.road[0][0] + ROAD_HALF, 0).x;
  const left = Math.max(road, scene.wave.area().right) + EDGE;
  const width = Math.max(0, field.x + field.width - left);
  // The highest pad or bend of the road the strip must keep above (the road's first stretch is left of the strip)
  const tops = [...MAP.spots.map(([, y]) => y - PAD_REACH), ...MAP.road.slice(1).map(([, y]) => y - ROAD_HALF)];
  const below = scene.mapToClient(0, Math.min(...tops)).y;
  strip.left = `${left}px`;
  strip.width = `${width}px`;
  strip.top = `${Math.max(field.y, (field.y + below - STRIP_HEIGHT) / 2)}px`;
  Object.assign(news, { left: `${left}px`, top: `${field.y}px`, maxWidth: `${width}px`, transform: "none" });
}

// The hub's people button: in the run's own controls during a run, in the top right corner otherwise
function placePeople() {
  const people = $("people");
  const slot = $(page.screen === "play" ? "people-play-slot" : "people-corner-slot");
  if (people.parentElement !== slot) {
    slot.append(people);
  }
}

start();
