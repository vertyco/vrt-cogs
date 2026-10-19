// The level's verdict panels. The win panel opens a moment after the last pig is gone: a trophy, the level's name, the
// coins counting up and Continue. The fail panel names the fail, shows its picture and line, and offers the revive
// for coins or Retry. The bot decides every result and charges for the revive; this file only shows them.
// It also shows what a player is told the first time: a feature's New Feature popup, a booster's unlock popup with its
// CLAIM, and the tutorials (a dark overlay, a spotlight, the pointing finger and the mascot's bubble). The bot
// remembers which of them a player has seen.
import * as THREE from "./vendor/three.module.min.js";
import { GLTFLoader } from "./vendor/GLTFLoader.js";
import * as hud from "./hud.js";
import {
  BOOSTER_INTROS,
  FEATURE_FIRST,
  INTROS,
  LATER_TUTORIALS,
  HAND_PICK,
  TUTORIALS,
  WAIT_LINE,
} from "./intros.js";
import { hitTest } from "./pigs.js";
import { freeTrays } from "./sim/belt.js";
import { HOP } from "./sim/numbers.js";
import { play as sound } from "./sound.js";

const ART = "art/ui/";
// The win panel waits this long after the win (the original's 1.5 to 2 seconds, section 2.8)
const WIN_DELAY_MS = 1700;
// The fail panel follows its fail quickly, so the full slots stay in view for a moment
const FAIL_DELAY_MS = 600;
const COUNT_MS = 900;
const CONFETTI = 16;
const CONFETTI_STARS = ["fx_star_yellow", "fx_star_white", "fx_star_yellow"];
// What a revive costs when the bot's progress doesn't say
const REVIVE_PRICE = 900;
// A fail's title, line and picture (the original's Level Fail Offer String Table). The picture is the offer's, and the
// totem fail shares the obstacles' because the original has none of its own. The spaceship fail has no strings in the
// original's files; its words follow the UFO fail's.
const FAILS = {
  out_of_space: {
    title: "Out of space!",
    line: "Clear conveyor and open up slots to keep playing!",
    picture: "Icon_Out_Of_Space_Offer",
  },
  locked_out: { title: "Locked out!", line: "Open locks to keep playing!", picture: "Icon_Locked_Out_Offer" },
  frozen: { title: "Frozen!", line: "Shatter the ice to keep playing!", picture: "Icon_Frozen_Offer" },
  ufo: { title: "UFO block!", line: "Launch UFOs to keep playing!", picture: "Icon_Ufo_Fail_Offer" },
  curtain: {
    title: "Curtains closed!",
    line: "Open the curtains to keep playing!",
    picture: "Icon_Curtain_Fail_Offer",
  },
  spaceship: {
    title: "Spaceship block!",
    line: "Launch the spaceships to keep playing!",
    picture: "Icon_Spaceship_Fail_Offer",
  },
  obstacles: {
    title: "Out of shoots!",
    line: "Remove the obstacles to keep playing!",
    picture: "Icon_Obstacle_Fail_Offer",
  },
  totem: { title: "Totem block!", line: "Remove the totems to keep playing!", picture: "Icon_Obstacle_Fail_Offer" },
};

// The mascot is drawn once into a picture this size
const MASCOT_MODEL = "models/mascot.glb";
const MASCOT_SIZE = 256;
const MASCOT_BUBBLE_PARTS = ["Bubble", "BubbleTail"];
// The spotlight stands this far outside what it points at. On the free-tray counter it takes in the stack of free trays
// above the number: the box is this wide, and reaches this far up and down from the number, as shares of the column's
// width
const SPOT_PAD = 10;
const COUNTER_BOX = { w: 0.22, up: 0.22, down: 0.06 };
// Where the finger's tip sits in its picture (share of its width and height), and how wide it is drawn
const FINGER_TIP = { x: 0.08, y: 0.06 };
const HAND_WIDTH = 62;
const HAND_ASPECT = 214 / 190;
// The boosters in the order they unlock
// A tutorial that opens when something happens waits this long first, so a pig has landed in its slot (its hop takes
// HOP ticks) before the spotlight points at it
const HAPPENED_TICKS = HOP + 2;
const BOOSTER_KEYS = ["tray", "hand", "shuffle", "bomb", "super"];
// The shop lists the boosters in the booster bar's order
const SHOP_ORDER = ["tray", "hand", "shuffle", "super", "bomb"];
// The pick bubble's bottom edge stands this far above the slots' top edge
const PICK_GAP = 8;

// `page` is game.js's page; `actions` is what the panels need from the rest of the game: revive() (resolves true once
// the level goes on), buy(booster, pay) (the shop's purchase with "coins" or "credits", rejects with the bot's words when
// it won't), credits() (the server's credit prices), shopSettings() and saveShop(settings) (the admin dialog), retry(n) and next() (the win's Continue), leave() (the fail's close button back to the path),
// claim(booster) (the unlock popup's CLAIM, rejects with the bot's words), seen(id) (the bot remembers a popup or
// tutorial was shown), tap(tap) and hold(reason) / release(reason) for the level's clock.
// `answer` settles the popup on screen; `token` changes whenever what is open is thrown away, so a sequence that was
// cut off knows to stop; `opening` is true while a sequence of popups or a tutorial step holds the clock; `step` is
// the tutorial step waiting for its press; `hintLevel` is the level whose belt-full hint shows; `mascot` is the
// promise of the mascot's picture; `hooked` is true once the spotlight follows resizes; `happened` is {id, tick} for
// the tutorial whose moment has come and is waiting out HAPPENED_TICKS
const panels = {
  page: null,
  actions: null,
  el: {},
  timer: 0,
  count: 0,
  shown: "",
  busy: false,
  answer: null,
  token: 0,
  opening: false,
  step: null,
  hintLevel: 0,
  mascot: null,
  hooked: false,
  happened: null,
  pickHint: false,
  pickHooked: false,
  shopOpen: false,
  shopBusy: false,
  shopRows: new Map(),
  // What the server sells for credits: {prices: {booster: price}, currency}. Empty prices sell nothing
  credits: { prices: {}, currency: "credits" },
  // The admin dialog: its state from the bot ({settings, currency, global, today}), or null for players who can't
  // change prices; its inputs by booster; whether it stands; whether a save is on its way
  admin: null,
  adminInputs: new Map(),
  adminOpen: false,
  adminBusy: false,
};

function $(id) {
  return document.getElementById(id);
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function levelNumber() {
  const { sim, progress } = panels.page;
  return sim ? sim.level.number : progress.level;
}

// Show one panel (or none, with "") and drop the other
function setShown(name) {
  panels.shown = name;
  for (const id of ["win", "fail", "intro", "unlock"]) {
    $(id).hidden = name !== id;
  }
}

// Take everything down, popups and tutorial too: whatever was waiting on a press stops waiting, and the clock they held
// goes free
export function hidePanels() {
  clearTimeout(panels.timer);
  cancelAnimationFrame(panels.count);
  panels.busy = false;
  setShown("");
  panels.token += 1;
  settle(false);
  closeShop();
  closeShopAdmin();
  endOpening();
  hideStep();
  $("tut-hint").hidden = true;
  panels.pickHint = false;
  $("tut-pick").hidden = true;
}

// ---------- Win ----------

function sparkles() {
  const box = $("win-confetti");
  box.replaceChildren();
  for (let i = 0; i < CONFETTI; i++) {
    const star = document.createElement("span");
    star.style.setProperty("--x", `${Math.round(((i + 0.5) / CONFETTI) * 100)}%`);
    star.style.setProperty("--d", `${((i * 7) % CONFETTI) * 0.18}s`);
    star.style.setProperty("--t", `${2.4 + (i % 5) * 0.5}s`);
    star.style.setProperty("--s", `${14 + (i % 4) * 5}px`);
    star.style.backgroundImage = `url("art/effects/${CONFETTI_STARS[i % CONFETTI_STARS.length]}.png")`;
    box.append(star);
  }
}

// The coin number counts up from 0 over COUNT_MS, easing out
function countUp(to) {
  const node = $("win-coins");
  cancelAnimationFrame(panels.count);
  if (reducedMotion() || to === 0) {
    node.textContent = `+${to}`;
    return;
  }
  const began = performance.now();
  sound("coins");
  const tick = (now) => {
    sound("count");
    const share = Math.min((now - began) / COUNT_MS, 1);
    node.textContent = `+${Math.round(to * (1 - (1 - share) ** 3))}`;
    if (share < 1) {
      panels.count = requestAnimationFrame(tick);
    }
  };
  node.textContent = "+0";
  panels.count = requestAnimationFrame(tick);
}

function openWin(over) {
  hud.closeSettings();
  $("win-title").textContent = `Level ${levelNumber()} completed!`;
  sparkles();
  sound("win");
  setShown("win");
  countUp(over.coins);
  $("win-continue").disabled = false;
}

// The level was won (`over` is the bot's verdict). The panel opens after the win's pause
export function showWin(over) {
  hidePanels();
  panels.timer = setTimeout(() => panels.page.screen === "level" && openWin(over), WIN_DELAY_MS);
}

// ---------- Fail ----------

// The words a fail goes by, like "Out of space!"
export function failTitle(name) {
  return (FAILS[name] || FAILS.obstacles).title;
}

function drawFail(over) {
  const fail = FAILS[over.name] || FAILS.obstacles;
  const { coins, revive_price: price = REVIVE_PRICE } = panels.page.progress;
  $("fail-title").textContent = fail.title;
  $("fail-picture").src = `${ART}${fail.picture}.png`;
  $("fail-line").textContent = fail.line;
  $("fail-price").textContent = price.toLocaleString("en-US");
  $("fail-revive").setAttribute("aria-label", `Revive for ${price.toLocaleString("en-US")} coins`);
  const short = coins < price;
  $("fail-revive").disabled = short;
  $("fail-note").textContent = short ? `Need ${(price - coins).toLocaleString("en-US")} more coins to revive.` : "";
  $("fail-retry").disabled = false;
  $("fail-close").disabled = false;
}

function openFail(over) {
  hud.closeSettings();
  drawFail(over);
  panels.busy = false;
  sound("fail");
  setShown("fail");
}

// The level failed (`over` is the bot's verdict, with its fail's name). The panel opens soon after
export function showFail(over) {
  hidePanels();
  panels.timer = setTimeout(() => panels.page.screen === "level" && openFail(over), FAIL_DELAY_MS);
}

function lockFail(locked) {
  panels.busy = locked;
  for (const id of ["fail-revive", "fail-retry", "fail-close"]) {
    $(id).disabled = locked;
  }
}

async function revive() {
  if (panels.busy) {
    return;
  }
  sound("click");
  lockFail(true);
  $("fail-note").textContent = "";
  let ok = false;
  try {
    ok = await panels.actions.revive();
  } catch (e) {
    console.warn("Block Blaster: the revive didn't work", e);
    $("fail-note").textContent = e.message || "The revive didn't work. Try again.";
  }
  if (panels.shown !== "fail") {
    return;
  }
  if (ok) {
    hidePanels();
    return;
  }
  lockFail(false);
  $("fail-revive").disabled = panels.page.progress.coins < (panels.page.progress.revive_price || REVIVE_PRICE);
}

function retry() {
  if (panels.busy) {
    return;
  }
  sound("retry");
  lockFail(true);
  // The new level arriving closes the panel (hidePanels in game.js). A send that goes nowhere gives the buttons back
  if (!panels.actions.retry(levelNumber())) {
    lockFail(false);
  }
}

function proceed() {
  sound("click");
  $("win-continue").disabled = true;
  hidePanels();
  panels.actions.next();
}

// ---------- First-time popups and tutorials ----------

function seen(id) {
  return panels.page.progress.shown.includes(id);
}

// The bot remembers `id`; the page's copy of the list says so at once, so nothing asks twice before its answer is back
function mark(id) {
  const { shown } = panels.page.progress;
  if (!shown.includes(id)) {
    shown.push(id);
  }
  panels.actions.seen(id);
}

// Settle the popup that is waiting for an answer (true: the player pressed its button; false: it was thrown away)
function settle(value) {
  const resolve = panels.answer;
  panels.answer = null;
  if (resolve) {
    resolve(value);
  }
}

function ask(name) {
  return new Promise((resolve) => {
    panels.answer = resolve;
    setShown(name);
  });
}

function endOpening() {
  if (panels.opening) {
    panels.opening = false;
    panels.actions.release("intro");
  }
}

// Run `job(token)` with the level's clock held. A job checks `token === panels.token` after every wait: when it no
// longer matches, hidePanels threw the job's popups away and the job stops
function begin(job) {
  const token = ++panels.token;
  panels.opening = true;
  panels.actions.hold("intro");
  job(token)
    .catch((e) => console.warn("Block Blaster: a popup didn't finish", e))
    .finally(() => token === panels.token && endOpening());
}

// A line with **stars** around the words that show blue
function setLine(node, line) {
  node.replaceChildren(
    ...line.split("**").map((part, i) => {
      if (i % 2 === 0) {
        return document.createTextNode(part);
      }
      const word = document.createElement("b");
      word.textContent = part;
      return word;
    }),
  );
}

// The New Feature popup. Resolves true when the player presses Continue, false when it was thrown away
export function showIntro(n) {
  const intro = INTROS[n];
  $("intro-picture").src = intro.picture;
  $("intro-name").textContent = intro.name;
  $("intro-line").textContent = intro.line;
  $("intro-continue").disabled = false;
  const answer = ask("intro");
  $("intro-continue").focus({ preventScroll: true });
  return answer;
}

// A booster's unlock popup. Resolves true once its CLAIM took, false when it was thrown away
export function showUnlock(booster) {
  const intro = BOOSTER_INTROS[booster];
  $("unlock-icon").src = intro.icon;
  $("unlock-name").textContent = intro.name;
  $("unlock-line").textContent = intro.line;
  $("unlock-note").textContent = "";
  $("unlock-claim").dataset.booster = booster;
  $("unlock-claim").disabled = false;
  sound("appear");
  return ask("unlock");
}

async function claim() {
  const button = $("unlock-claim");
  button.disabled = true;
  $("unlock-note").textContent = "";
  try {
    await panels.actions.claim(button.dataset.booster);
    sound("unlock");
    settle(true);
  } catch (e) {
    console.warn("Block Blaster: the claim didn't work", e);
    $("unlock-note").textContent = e.message || "That didn't work. Try again.";
    button.disabled = false;
  }
}

// The mascot is drawn once from its model, without its speech bubble (the page draws the words), into a picture
async function renderMascot() {
  const gltf = await new GLTFLoader().loadAsync(MASCOT_MODEL);
  for (const name of MASCOT_BUBBLE_PARTS) {
    gltf.scene.getObjectByName(name).removeFromParent();
  }
  const canvas = document.createElement("canvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(1);
  renderer.setSize(MASCOT_SIZE, MASCOT_SIZE, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  scene.add(gltf.scene);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x6a6aa0, 1.4));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(-3, 6, 5);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 20);
  camera.position.set(0.5, 1.2, 3.2);
  camera.lookAt(0, 0.5, 0);
  renderer.render(scene, camera);
  const url = canvas.toDataURL("image/png");
  renderer.dispose();
  renderer.forceContextLoss();
  return url;
}

// Put the mascot's picture into the bubble with image `id` once it is drawn. A mascot that can't be drawn leaves the
// bubble with words only
function showMascot(id) {
  if (!panels.mascot) {
    panels.mascot = renderMascot().catch((e) => {
      console.warn("Block Blaster: couldn't draw the mascot", e);
      return null;
    });
  }
  panels.mascot.then((url) => {
    if (url) {
      $(id).src = url;
      $(id).hidden = false;
      $(id).parentElement.classList.add("pictured");
    }
  });
}

// ---------- Tutorial steps ----------

// The box of a booster's button (pixels from the tutorial layer's top left), or null while the bar is hidden
function buttonTarget(key) {
  const button = document.querySelector(`#booster-bar [data-booster="${key}"]`);
  if (!button || button.offsetParent === null) {
    return null;
  }
  const from = $("tutorial").getBoundingClientRect();
  const at = button.getBoundingClientRect();
  return { box: { x: at.left - from.left, y: at.top - from.top, w: at.width, h: at.height }, slot: -1 };
}

// The box (pixels from the column's top left) a step spotlights, and the slot it points at, or null when there is
// nothing to point at
function stepTarget(step) {
  const { sim, scene } = panels.page;
  const boxes = scene.screenBoxes();
  if (step.target === "queue") {
    return { box: boxes.queues[0].front, slot: -1 };
  }
  if (step.target === "hand") {
    return buttonTarget(step.target);
  }
  if (step.target === "counter") {
    const spot = scene.counterSpot();
    const w = boxes.width * COUNTER_BOX.w;
    const up = boxes.width * COUNTER_BOX.up;
    return { box: { x: spot.x - w / 2, y: spot.y - up, w, h: up + boxes.width * COUNTER_BOX.down }, slot: -1 };
  }
  const first = sim.slots.findIndex((pig) => pig !== null);
  if (first < 0) {
    return null;
  }
  if (step.target === "slot") {
    return { box: boxes.slots[first], slot: first };
  }
  const left = Math.min(...boxes.slots.map((box) => box.x));
  const top = Math.min(...boxes.slots.map((box) => box.y));
  const right = Math.max(...boxes.slots.map((box) => box.x + box.w));
  const bottom = Math.max(...boxes.slots.map((box) => box.y + box.h));
  return { box: { x: left, y: top, w: right - left, h: bottom - top }, slot: first };
}

// Put the spotlight and the finger on the current step's target. Also called after every resize
function placeStep() {
  const { step } = panels;
  const target = step && stepTarget(step);
  if (!target) {
    return;
  }
  step.slot = target.slot;
  const { box } = target;
  const spot = $("tut-spot").style;
  spot.left = `${box.x - SPOT_PAD}px`;
  spot.top = `${box.y - SPOT_PAD}px`;
  spot.width = `${box.w + SPOT_PAD * 2}px`;
  spot.height = `${box.h + SPOT_PAD * 2}px`;
  const hand = $("tut-hand").style;
  hand.left = `${box.x + box.w / 2 - FINGER_TIP.x * HAND_WIDTH}px`;
  hand.top = `${box.y + box.h / 2 - FINGER_TIP.y * HAND_WIDTH * HAND_ASPECT}px`;
}

// True when a press that landed on `what` (a tap from hitTest, or null) is the one the step waits for
function isExpected(step, what) {
  if (!what) {
    return false;
  }
  if (step.target === "queue") {
    return what[0] === "q" && what[1] === 0;
  }
  return what[0] === "s" && (step.target === "slots" || what[1] === step.slot);
}

// True when a press at x, y (pixels from the tutorial layer's top left) is on the step's button
function onButton(step, x, y) {
  const target = stepTarget(step);
  if (target === null) {
    return false;
  }
  const { box } = target;
  return x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h;
}

function hideStep() {
  const { step } = panels;
  panels.step = null;
  $("tutorial").hidden = true;
  if (step) {
    step.resolve(false);
  }
}

// The press the step waits for: the tap goes on to the game, and the step is done. Every other press is held back
function pressStep(event) {
  const { step } = panels;
  if (!step) {
    return;
  }
  event.preventDefault();
  const box = $("tutorial").getBoundingClientRect();
  const x = event.clientX - box.left;
  const y = event.clientY - box.top;
  const what = step.then === "tap" ? hitTest(x, y) : null;
  const wrong = step.then === "tap" ? !isExpected(step, what) : step.then === "button" && !onButton(step, x, y);
  if (wrong) {
    const node = $("tutorial");
    node.classList.remove("nudge");
    void node.offsetWidth;
    node.classList.add("nudge");
    return;
  }
  panels.step = null;
  $("tutorial").hidden = true;
  if (what) {
    panels.actions.tap(what);
  }
  if (step.then === "button") {
    panels.pickHint = Boolean(step.pick);
    hud.pressBooster(step.target);
  }
  step.resolve(true);
}

// Show one step and wait for its press. Resolves true when the player did it, false when it was thrown away
function showStep(step) {
  return new Promise((resolve) => {
    if (!panels.hooked && panels.page.scene) {
      panels.hooked = true;
      panels.page.scene.onLayout(placeStep);
    }
    panels.step = { ...step, resolve, slot: -1 };
    $("tutorial").dataset.then = step.then;
    $("tutorial").dataset.target = step.target;
    setLine($("tut-line"), step.line);
    showMascot("tut-mascot");
    placeStep();
    $("tutorial").hidden = false;
  });
}

// Every step of a tutorial in turn; the bot is told the player has seen it once the last step was done
async function playTutorial(token, tutorial) {
  for (const step of tutorial.steps) {
    if (!(await showStep(step)) || token !== panels.token) {
      return;
    }
  }
  mark(tutorial.id);
  if (tutorial.hint) {
    panels.hintLevel = levelNumber();
  }
}

// Open the tutorial of `level`, when it has one the player hasn't done and nothing else is open
export function runTutorial(level) {
  const tutorial = TUTORIALS[level];
  if (!tutorial || seen(tutorial.id) || panels.opening) {
    return;
  }
  begin((token) => playTutorial(token, tutorial));
}

// ---------- A level's opening ----------

// What a level owes the player before its clock runs: the New Feature popups of the features it is the first level of,
// then the unlock popup of each booster the player has reached and not claimed
function openingPlan(sim) {
  const { progress } = panels.page;
  const features = sim.level.used
    .filter((n) => FEATURE_FIRST[n] === sim.level.number && !seen(`feature-${n}`))
    .sort((a, b) => a - b);
  const boosters = BOOSTER_KEYS.filter(
    (key) => (progress.cleared || progress.level >= progress.unlocks[key]) && !progress.claimed.includes(key),
  );
  return { features, boosters };
}

async function opening(token, plan, tutorial) {
  for (const n of plan.features) {
    if (!(await showIntro(n)) || token !== panels.token) {
      return;
    }
    mark(`feature-${n}`);
  }
  for (const key of plan.boosters) {
    if (!(await showUnlock(key)) || token !== panels.token) {
      return;
    }
  }
  setShown("");
  if (tutorial) {
    await playTutorial(token, tutorial);
  }
}

// A level was put on screen (a fresh start, a resume or a rebuild). Anything it owes opens now, over the held clock.
// The tutorial belongs to the start of a level only: a level with taps already made is past it
export function levelOpened(sim, levelStart) {
  if (panels.opening) {
    return;
  }
  const fresh = levelStart.taps.length === 0;
  const named = TUTORIALS[sim.level.number];
  const tutorial = fresh && named && !seen(named.id) ? named : null;
  if (fresh) {
    panels.hintLevel = 0;
  }
  const plan = openingPlan(sim);
  if (plan.features.length || plan.boosters.length || tutorial) {
    begin((token) => opening(token, plan, tutorial));
  }
}

// The belt-full hint of the first level's tutorial: the mascot's bubble, no overlay, while no tray is free
function hint(sim) {
  const node = $("tut-hint");
  const show =
    panels.hintLevel === sim.level.number &&
    sim.over === null &&
    !sim.finishing &&
    !panels.opening &&
    freeTrays(sim) === 0;
  if (node.hidden !== show) {
    return;
  }
  node.hidden = !show;
  if (show) {
    setLine($("tut-hint-line"), WAIT_LINE);
    showMascot("tut-hint-mascot");
  }
}

// The pick bubble stands just above the slots, in the middle of the column
function placePick() {
  const { scene } = panels.page;
  if (!scene || $("tut-pick").hidden) {
    return;
  }
  const boxes = scene.screenBoxes();
  $("tut-pick").style.top = `${Math.min(...boxes.slots.map((box) => box.y)) - PICK_GAP}px`;
}

// The Hand's pick bubble shows while a first pick waits, and goes when the pick lands or is cancelled. `armed` is the
// booster waiting for its pick, or null
function pickChanged(armed) {
  const show = armed !== null && panels.pickHint;
  if (!show) {
    panels.pickHint = false;
  }
  $("tut-pick").hidden = !show;
  if (show) {
    $("tut-pick-name").textContent = HAND_PICK.name;
    $("tut-pick-line").textContent = HAND_PICK.line;
    if (!panels.pickHooked && panels.page.scene) {
      panels.pickHooked = true;
      panels.page.scene.onLayout(placePick);
    }
    placePick();
  }
}

// Called for every drawn frame of a level: the hint follows the belt, and a tutorial that opens when something happens
// in play (the first pig in a slot, every slot full) opens the moment it does
export function watch(sim) {
  hint(sim);
  if (panels.opening || sim.over !== null || sim.finishing || panels.page.screen !== "level") {
    return;
  }
  const later = LATER_TUTORIALS.find((tutorial) => !seen(tutorial.id) && tutorial.when(sim));
  if (!later) {
    panels.happened = null;
    return;
  }
  if (!panels.happened || panels.happened.id !== later.id) {
    panels.happened = { id: later.id, tick: sim.tick };
  }
  if (sim.tick - panels.happened.tick >= HAPPENED_TICKS) {
    panels.happened = null;
    begin((token) => playTutorial(token, { id: later.id, steps: [later.step] }));
  }
}

// ---------- The booster shop ----------

function numberText(n) {
  return n.toLocaleString("en-US");
}

function makeShopRow(key) {
  const intro = BOOSTER_INTROS[key];
  const row = document.createElement("li");
  row.className = "shop-row";
  row.dataset.booster = key;
  row.innerHTML =
    `<img class="shop-icon" src="${intro.icon}" alt="" />` +
    '<div class="shop-info"><b class="shop-name"></b><span class="shop-have"><span class="shop-stock"></span><span class="shop-pack"></span></span></div>' +
    '<div class="shop-pay"><button type="button" class="dialog-button green shop-buy" data-pay="coins">' +
    `<span class="shop-price"></span><img src="${ART}Icon_Gold.png" alt="" /></button>` +
    '<button type="button" class="dialog-button blue shop-buy shop-credits" data-pay="credits" hidden>' +
    '<span class="shop-credit-price"></span><span class="shop-currency"></span></button></div>';
  row.querySelector(".shop-name").textContent = intro.name;
  const buy = row.querySelector(".shop-buy");
  buy.addEventListener("click", () => buyBooster(key, "coins"));
  const credits = row.querySelector(".shop-credits");
  credits.addEventListener("click", () => buyBooster(key, "credits"));
  return {
    row,
    buy,
    credits,
    creditPrice: row.querySelector(".shop-credit-price"),
    currency: row.querySelector(".shop-currency"),
    stock: row.querySelector(".shop-stock"),
    pack: row.querySelector(".shop-pack"),
    price: row.querySelector(".shop-price"),
  };
}

// Show what the player's progress says in the rows that stand: stock, price, and a dim look on a price they can't pay
function drawShop() {
  const { progress } = panels.page;
  for (const [key, part] of panels.shopRows) {
    const price = progress.prices[key];
    const name = BOOSTER_INTROS[key].name;
    part.stock.textContent = `You have ${progress.stock[key]}`;
    part.pack.textContent = ` · pack of ${progress.pack}`;
    part.price.textContent = numberText(price);
    part.buy.toggleAttribute("data-short", progress.coins < price);
    part.buy.disabled = panels.shopBusy;
    part.buy.setAttribute("aria-label", `Buy ${progress.pack} ${name} for ${numberText(price)} coins`);
    const credit = panels.credits.prices[key];
    part.credits.hidden = credit === undefined;
    part.row.toggleAttribute("data-credit", credit !== undefined);
    if (credit !== undefined) {
      const { currency } = panels.credits;
      part.creditPrice.textContent = numberText(credit);
      part.currency.textContent = currency;
      part.credits.disabled = panels.shopBusy;
      part.credits.setAttribute("aria-label", `Buy ${progress.pack} ${name} for ${numberText(credit)} ${currency}`);
    }
  }
}

// Ask the bot what this server sells for credits, and redraw the rows that stand. Nothing is sold when it can't say
export async function loadCredits() {
  try {
    panels.credits = await panels.actions.credits();
  } catch (e) {
    console.warn("Block Blaster: couldn't read the credit prices", e);
    panels.credits = { prices: {}, currency: "credits" };
  }
  if (panels.shopOpen) {
    drawShop();
  }
}

// Open the shop. `pick` is the booster whose empty button opened it (its row is lit), or null for the coins' plus.
// The level's clock is held while it stands
export function openShop(pick) {
  const { progress } = panels.page;
  if (panels.shopOpen || !progress) {
    return;
  }
  const keys = SHOP_ORDER.filter((key) => progress.cleared || progress.level >= progress.unlocks[key]);
  panels.shopRows = new Map(keys.map((key) => [key, makeShopRow(key)]));
  const list = $("shop-list");
  if (keys.length) {
    list.replaceChildren(...[...panels.shopRows.values()].map((part) => part.row));
  } else {
    const empty = document.createElement("li");
    empty.className = "shop-empty";
    empty.textContent = `Boosters unlock at level ${Math.min(...Object.values(progress.unlocks))}.`;
    list.replaceChildren(empty);
  }
  const lit = panels.shopRows.get(pick);
  if (lit) {
    lit.row.dataset.pick = "";
  }
  $("shop-note").textContent = "";
  panels.shopBusy = false;
  drawShop();
  panels.shopOpen = true;
  loadCredits();
  panels.actions.hold("shop");
  $("shop").hidden = false;
  if (lit) {
    lit.row.scrollIntoView({ block: "nearest" });
  }
  $("shop-close").focus({ preventScroll: true });
}

export function closeShop() {
  if (!panels.shopOpen) {
    return;
  }
  panels.shopOpen = false;
  $("shop").hidden = true;
  panels.actions.release("shop");
}

// Buy a pack with `pay` ("coins" or "credits"). The bot checks the money and answers with the new progress, or its own words when it
// won't; those words go in the shop's note
async function buyBooster(key, pay) {
  if (panels.shopBusy) {
    return;
  }
  panels.shopBusy = true;
  drawShop();
  sound("button");
  let note = "";
  try {
    await panels.actions.buy(key, pay);
    sound("coins");
    note = `Got ${panels.page.progress.pack} ${BOOSTER_INTROS[key].name}.`;
  } catch (e) {
    console.warn("Block Blaster: the purchase didn't go through", e);
    note = e.message || "That didn't work. Try again.";
  }
  if (!panels.shopOpen) {
    return;
  }
  panels.shopBusy = false;
  $("shop-note").textContent = note;
  drawShop();
}

// ---------- Shop settings (server admins) ----------

// The settings panel's button shows for players the bot lets change prices
function showAdminButton(state) {
  panels.admin = state.settings ? state : null;
  $("shop-settings-open").hidden = !panels.admin;
}

export async function loadShopSettings() {
  try {
    showAdminButton(await panels.actions.shopSettings());
  } catch (e) {
    console.warn("Block Blaster: couldn't read the shop settings", e);
    showAdminButton({ settings: null });
  }
}

// One row per booster, made once: its picture, name and a price box (empty means not sold for credits)
function makeAdminRows() {
  const rows = SHOP_ORDER.map((key) => {
    const intro = BOOSTER_INTROS[key];
    const row = document.createElement("li");
    row.className = "admin-row";
    row.innerHTML =
      `<img class="shop-icon" src="${intro.icon}" alt="" />` +
      '<label><span class="shop-name"></span><input type="number" min="1" step="1" inputmode="numeric" placeholder="None" /></label>';
    row.querySelector(".shop-name").textContent = intro.name;
    const input = row.querySelector("input");
    input.setAttribute("aria-label", `${intro.name} price in credits`);
    panels.adminInputs.set(key, input);
    return row;
  });
  $("shop-admin-list").replaceChildren(...rows);
}

function fillAdmin() {
  const state = panels.admin;
  if (!panels.adminInputs.size) {
    makeAdminRows();
  }
  for (const [key, input] of panels.adminInputs) {
    const price = state.settings[key];
    input.value = price === null ? "" : String(price);
  }
  const { spent, players } = state.today;
  const who = players === 1 ? "1 player" : `${players.toLocaleString("en-US")} players`;
  $("shop-admin-global").hidden = !state.global;
  $("shop-admin-today").textContent = `Today: ${numberText(spent)} ${state.currency} spent by ${who}.`;
}

export async function openShopSettings() {
  if (panels.adminOpen) {
    return;
  }
  hud.closeSettings();
  await loadShopSettings();
  if (!panels.admin) {
    return;
  }
  fillAdmin();
  $("shop-admin-status").textContent = "";
  panels.adminBusy = false;
  $("shop-admin-save").disabled = false;
  panels.adminOpen = true;
  panels.actions.hold("shopadmin");
  $("shop-admin").hidden = false;
  $("shop-admin-close").focus({ preventScroll: true });
}

export function closeShopAdmin() {
  if (!panels.adminOpen) {
    return;
  }
  panels.adminOpen = false;
  $("shop-admin").hidden = true;
  panels.actions.release("shopadmin");
}

// Send the prices. The bot checks who is asking again and words any refusal for the admin
async function saveShopSettings() {
  if (panels.adminBusy) {
    return;
  }
  const settings = {};
  for (const [key, input] of panels.adminInputs) {
    settings[key] = input.value.trim() === "" ? null : Number(input.value);
  }
  panels.adminBusy = true;
  $("shop-admin-save").disabled = true;
  $("shop-admin-status").textContent = "Saving...";
  sound("button");
  try {
    showAdminButton(await panels.actions.saveShop(settings));
    if (panels.admin) {
      fillAdmin();
    }
    $("shop-admin-status").textContent = "Saved.";
    loadCredits();
  } catch (e) {
    console.warn("Block Blaster: the shop settings didn't save", e);
    $("shop-admin-status").textContent = e.message || "That didn't save. Try again.";
  }
  panels.adminBusy = false;
  $("shop-admin-save").disabled = false;
}

export function initPanels(page, actions) {
  Object.assign(panels, { page, actions });
  $("win-continue").addEventListener("click", proceed);
  $("fail-revive").addEventListener("click", revive);
  $("fail-retry").addEventListener("click", retry);
  $("intro-continue").addEventListener("click", () => {
    sound("button");
    settle(true);
  });
  $("unlock-claim").addEventListener("click", claim);
  $("shop-close").addEventListener("click", () => {
    sound("button");
    closeShop();
  });
  $("shop").addEventListener("click", (event) => event.target === $("shop") && closeShop());
  document.addEventListener("keydown", (event) => event.key === "Escape" && (closeShop(), closeShopAdmin()));
  $("shop-settings-open").addEventListener("click", () => {
    sound("button");
    openShopSettings();
  });
  $("shop-admin-close").addEventListener("click", () => {
    sound("button");
    closeShopAdmin();
  });
  $("shop-admin").addEventListener("click", (event) => event.target === $("shop-admin") && closeShopAdmin());
  $("shop-admin-save").addEventListener("click", saveShopSettings);
  hud.onShop(openShop);
  $("tutorial").addEventListener("pointerdown", pressStep);
  hud.onPick(pickChanged);
  $("fail-close").addEventListener("click", () => {
    if (!panels.busy) {
      sound("button");
      hidePanels();
      panels.actions.leave();
    }
  });
}

// What checks read through window.blockblaster.panels
export function shown() {
  return panels.shown;
}

// True while the shop stands
export function shopping() {
  return panels.shopOpen;
}

// True while the admin's shop settings stand
export function adminShopping() {
  return panels.adminOpen;
}
