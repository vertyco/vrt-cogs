// The level screen's page parts: the top bar's gear and level pill, the free-tray counter under the belt's entrance,
// the booster bar and the settings dialog. They are page elements over the canvas, so the 3D scene is left alone.
// The bot owns every booster's stock; this file only shows what the player's progress says and sends the taps.
import { BOMB_DROP_MS, BOMB_FLASH_MS, SHUFFLE_MS, SUPER_LEAD_MS, UNICORN_LEAD_MS } from "./fx.js";
import { freeTrays, trayTotal } from "./sim/belt.js";
import { bombTargets, canShuffle, superTargets } from "./sim/boosters.js";
import { full as unicornFull, gather } from "./sim/unicorn.js";
import { play as sound } from "./sound.js";

const ART = "art/ui/";
const BUTTON_BLUE = `${ART}PowerupButton_Blue.png`;
const BUTTON_OFF = `${ART}PowerupButton_Disabled.png`;
const SOUND_KEY = "blockblaster:sound";
const MUSIC_KEY = "blockblaster:music";
// Hard (2) and Very Hard (3) levels turn the pill, the gear and the booster strip red
const HARD_FROM = 2;
// A restart that the bot never answers gives the button back after this long
const RESTART_WAIT_MS = 4000;
// The Super Unicorn's button: grey while it is still to be earned, blue while its bar charges (the white ring
// fills), purple once it is full (Button_SuperBooster_*, Icon_SuperBooster_Inactive, Icon_SuperUnicorn_Active)
const UNICORN_ART = {
  waiting: [`${ART}Button_SuperBooster_Inactive.png`, `${ART}Icon_SuperBooster_Inactive.png`],
  charging: [`${ART}Button_SuperBooster_Blue.png`, `${ART}Icon_SuperUnicorn_Active.png`],
  ready: [`${ART}Button_SuperBooster_Purple.png`, `${ART}Icon_SuperUnicorn_Active.png`],
  off: [`${ART}Button_SuperBooster_Inactive.png`, `${ART}Icon_SuperUnicorn_Active.png`],
};
const UNICORN_ACTIVE_NOTE = "Super Unicorn will be active until your first fail!";
const UNICORN_EMPTY_NOTE = "Put a kitty in a slot for the Super Unicorn to merge!";

// The bar's buttons, left to right (decision D3 puts Demolish fifth). `key` is the booster's name in the bot's
// progress and in its tap
const BOOSTERS = [
  { key: "tray", name: "Tray", icon: "IconPowerup_ExtraSlot_Blue" },
  { key: "hand", name: "Hand", icon: "IconPowerup_Hand_Blue" },
  { key: "shuffle", name: "Shuffle", icon: "IconPowerup_Shuffle_Blue" },
  { key: "super", name: "Super Shooter", icon: "IconPowerup_SuperShooter_Blue" },
  { key: "bomb", name: "Demolish", icon: "IconPowerup_Bomb_Blue" },
];
// The gap between the lowest pig of a queue and the booster buttons (or the screen's bottom), in pixels
const FLOOR_GAP = 4;
// What a press on a ready booster does
const PRESSES = new Map([
  ["tray", () => hud.actions.tap(["tray"])],
  ["hand", () => (hud.armed ? disarm() : arm("hand"))],
  ["shuffle", () => shuffle()],
  ["super", () => (hud.armed ? disarm() : arm("super"))],
  ["bomb", () => (hud.armed ? disarm() : arm("bomb"))],
]);

// `page` is game.js's page and `actions` what the screen needs from the rest of the game: tap(tap) (returns why it was
// refused, or null), hold(reason), release(reason), restart() (true when asked) and backToMenu(). `buttons` keeps each
// booster's button parts and the last look drawn, so a progress update touches only what changed. `armed` is the key of
// the booster waiting for its pick (the clock is held meanwhile), else null; `pickHandlers` hear it change
const hud = {
  page: null,
  actions: null,
  el: {},
  buttons: new Map(),
  armed: null,
  pickHandlers: [],
  progress: null,
  sim: null,
  free: null,
  total: null,
  finished: false,
  full: false,
  spare: true,
  shuffling: false,
  shuffleTimer: 0,
  bombing: false,
  bombTimer: 0,
  supering: false,
  superTimer: 0,
  // The Super Unicorn's button parts and last look, and whether its run is playing (the clock is held)
  unicorn: null,
  unicorning: false,
  unicornTimer: 0,
  shown: false,
  hooked: false,
  open: false,
  restartTimer: 0,
  sound: true,
  music: true,
  switchHandlers: [],
  shopHandler: null,
  // The y (pixels from the scene's top) the queues must end above: the top of the booster buttons while the bar shows, else the screen's bottom
  floor: null,
  floorHandler: null,
};

function $(id) {
  return document.getElementById(id);
}

function readSwitch(key) {
  try {
    return localStorage.getItem(key) !== "0";
  } catch (e) {
    console.warn("Block Blaster: couldn't read a setting", e);
    return true;
  }
}

function writeSwitch(key, on) {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch (e) {
    console.warn("Block Blaster: couldn't save a setting", e);
  }
}

// Play an animation class again from its start, even when it is still running
function retrigger(node, name) {
  node.classList.remove(name);
  void node.offsetWidth;
  node.classList.add(name);
}

// ---------- Progress, as the bot's rules read it (common/progress.py) ----------

function unlocked(progress, key) {
  return progress.cleared || progress.level >= progress.unlocks[key];
}

// Claimed, and either some in stock or the first use still free
function usable(progress, key) {
  return progress.claimed.includes(key) && (progress.stock[key] > 0 || !progress.used.includes(key));
}

function stateOf(key) {
  const { progress, sim } = hud;
  if (!unlocked(progress, key)) {
    return "locked";
  }
  if (sim && (sim.over !== null || sim.finishing)) {
    return "off";
  }
  if (hud.armed === key) {
    return "ready";
  }
  // The Hand can't take a pig onto a full belt, so its button is greyed until a tray frees up
  if (sim && key === "hand" && usable(progress, key) && freeTrays(sim) === 0) {
    return "off";
  }
  // Shuffle needs two plain pigs in the queues, else nothing could move
  if (sim && key === "shuffle" && usable(progress, key) && !canShuffle(sim)) {
    return "off";
  }
  return usable(progress, key) ? "ready" : "empty";
}

// ---------- Booster bar ----------

function makeButton(def) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "boost";
  button.dataset.booster = def.key;
  button.innerHTML =
    `<img class="boost-bg" src="${BUTTON_BLUE}" alt="" />` +
    `<img class="boost-icon" src="${ART}${def.icon}.png" alt="" />` +
    '<span class="boost-badge">0</span>' +
    `<span class="boost-lock"><img src="${ART}Icon_Lock_White.png" alt="" /><b>Lv 1</b></span>`;
  button.addEventListener("click", () => pressBooster(def.key));
  return {
    def,
    button,
    bg: button.querySelector(".boost-bg"),
    badge: button.querySelector(".boost-badge"),
    lock: button.querySelector(".boost-lock b"),
    look: "",
  };
}

export function pressBooster(key) {
  if ((hud.armed && hud.armed !== key) || busy()) {
    return;
  }
  const state = hud.buttons.get(key).button.dataset.state;
  if (state === "empty" || state === "ready") {
    sound("button");
  }
  if (state === "empty" && hud.shopHandler) {
    hud.shopHandler(key);
  } else if (state === "ready" && PRESSES.has(key)) {
    PRESSES.get(key)();
  }
}

function drawButton(part) {
  const { key, name } = part.def;
  const state = stateOf(key);
  const stock = hud.progress.stock[key];
  const armed = hud.armed === key;
  const look = `${state}|${stock}|${hud.progress.unlocks[key]}|${armed}`;
  if (look === part.look) {
    return;
  }
  part.look = look;
  part.button.dataset.state = state;
  part.button.toggleAttribute("data-armed", armed);
  part.button.setAttribute("aria-pressed", String(armed));
  part.button.disabled = state === "locked" || state === "off";
  part.bg.src = part.button.disabled ? BUTTON_OFF : BUTTON_BLUE;
  part.badge.textContent = String(stock);
  const unlockLevel = hud.progress.unlocks[key];
  part.lock.textContent = `Lv ${unlockLevel}`;
  const words = state === "locked" ? `unlocks at level ${unlockLevel}` : `${stock} left`;
  part.button.setAttribute("aria-label", `${name}, ${words}`);
}

// ---------- Shuffle ----------

// True while the Shuffle animation, the Demolish bomb or the Super Shooter plays: the clock is held and no press acts
export function busy() {
  return hud.shuffling || hud.bombing || hud.supering || hud.unicorning;
}

// The tap lands at the current tick, then the clock waits for the 0.4 s animation
function shuffle() {
  if (hud.actions.tap(["shuffle"]) !== null) {
    return;
  }
  hud.shuffling = true;
  hud.actions.hold("shuffle");
  hud.shuffleTimer = setTimeout(endShuffle, SHUFFLE_MS);
}

export function endShuffle() {
  clearTimeout(hud.shuffleTimer);
  if (!hud.shuffling) {
    return;
  }
  hud.shuffling = false;
  hud.actions.release("shuffle");
}

// ---------- Picks (the Hand and Demolish) ----------

// The booster waiting for its pick: the button stays lit, the clock is held, and a second press of the button cancels
// for free. Called with the armed key, or null, each time it changes
export function onPick(handler) {
  hud.pickHandlers.push(handler);
}

function setArmed(key) {
  hud.armed = key;
  hud.buttons.forEach(drawButton);
  hud.pickHandlers.forEach((handler) => handler(key));
}

function arm(key) {
  if (hud.armed) {
    return;
  }
  sound("select");
  hud.actions.hold("booster");
  setArmed(key);
}

// Stop waiting for a pick. Cancelling costs nothing: the bot is only told when a pick lands
export function disarm() {
  if (!hud.armed) {
    return;
  }
  hud.actions.release("booster");
  setArmed(null);
}

// True while the Hand waits for a queue pig
export function picking() {
  return hud.armed === "hand";
}

// A press landed on queue pig `at` ([queue, index]) while the Hand is armed. The tap is sent at the held tick, then the
// clock goes on. A refused tap leaves the Hand armed. True when it was taken
export function pickPig(at) {
  if (!picking() || hud.actions.tap(["hand", at[0], at[1]]) !== null) {
    return false;
  }
  sound("pick");
  disarm();
  return true;
}

// True while the Demolish or the Super Shooter waits for a cell
export function pickingCell() {
  return hud.armed === "bomb" || hud.armed === "super";
}

// A press landed on picture cell `at` ([x, y]) while the Demolish is armed. A cell whose cross holds nothing to hit is
// ignored and the Demolish stays armed. Otherwise the bomb drops with the clock held, and its tap lands when it hits
// (the cubes break at the blast, not before). True when it was taken
export function pickCell(at) {
  const sim = hud.page.sim;
  if (!pickingCell() || !sim) {
    return false;
  }
  if (hud.armed === "super") {
    return pickSuper(at, sim);
  }
  if (bombTargets(sim, at[0], at[1]).length === 0) {
    return false;
  }
  sound("pick");
  hud.bombing = true;
  hud.actions.hold("bomb");
  disarm();
  hud.page.scene.picture.dropBomb(at[0], at[1]);
  hud.bombTimer = setTimeout(() => landBomb(at), BOMB_DROP_MS);
  return true;
}

// The bomb hit: the tap goes to the bot, then the clock waits for the blast's flash
function landBomb(at) {
  if (hud.actions.tap(["bomb", at[0], at[1]]) !== null) {
    endBomb();
    return;
  }
  hud.bombTimer = setTimeout(endBomb, BOMB_FLASH_MS);
}

// The Super Shooter's pick: a cube whose color has something to shoot. The pig appears and winds up with the clock held,
// then the tap lands (the cubes break as the shots reach them, not before) and the clock waits for the volley to end.
// A cube with nothing to shoot is ignored and the Super Shooter stays armed
function pickSuper(at, sim) {
  const targets = superTargets(sim, at[0], at[1]);
  if (targets.length === 0) {
    return false;
  }
  const picture = hud.page.scene.picture;
  sound("pick");
  hud.supering = true;
  hud.actions.hold("super");
  disarm();
  picture.showSuper();
  const ids = targets.map((target) => target.id);
  hud.superTimer = setTimeout(() => landSuper(at, picture.volleyMs(ids)), SUPER_LEAD_MS);
  return true;
}

// The wind-up is over: the tap goes to the bot, then the clock waits for the shots to land and the pig to leave
function landSuper(at, ms) {
  if (hud.actions.tap(["super", at[0], at[1]]) !== null) {
    endSuper();
    return;
  }
  hud.superTimer = setTimeout(endSuper, ms);
}

export function endSuper() {
  clearTimeout(hud.superTimer);
  if (!hud.supering) {
    return;
  }
  hud.supering = false;
  hud.page.scene.picture.stopSuper();
  hud.actions.release("super");
}

export function endBomb() {
  clearTimeout(hud.bombTimer);
  if (!hud.bombing) {
    return;
  }
  hud.bombing = false;
  hud.actions.release("bomb");
}

// ---------- The Super Unicorn ----------

function makeUnicorn() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "boost boost-unicorn";
  button.dataset.booster = "unicorn";
  button.hidden = true;
  button.innerHTML =
    '<img class="boost-bg" alt="" />' +
    '<span class="unicorn-ring"></span>' +
    '<img class="boost-icon" alt="" />' +
    '<span class="boost-badge"></span>';
  button.addEventListener("click", pressUnicorn);
  return {
    button,
    bg: button.querySelector(".boost-bg"),
    icon: button.querySelector(".boost-icon"),
    ring: button.querySelector(".unicorn-ring"),
    badge: button.querySelector(".boost-badge"),
    look: "",
    state: null,
  };
}

// What the progress and the level say: hidden before the icon level, "waiting" while it is still to be earned, then
// "charging", "ready" (full) or "off" (the level is over or the auto-finisher runs)
function unicornState() {
  const { progress, sim } = hud;
  if (!progress.cleared && progress.level < progress.unicorn_levels.icon) {
    return "hidden";
  }
  if (!sim || !sim.unicorn.active) {
    return "waiting";
  }
  if (sim.over !== null || sim.finishing) {
    return "off";
  }
  return unicornFull(sim) ? "ready" : "charging";
}

function drawUnicorn() {
  const part = hud.unicorn;
  if (!part || !hud.progress) {
    return;
  }
  const state = unicornState();
  const { sim } = hud;
  const charge = sim ? Math.min(sim.unicorn.charge, sim.unicorn.need) : 0;
  const need = sim ? sim.unicorn.need : 1;
  const wins = hud.progress.unicorn.wins;
  const look = `${state}|${charge}|${need}|${wins}|${hud.unicorning}`;
  if (look === part.look) {
    return;
  }
  part.look = look;
  // The ready sound plays when the bar fills during play, not when a level opens with it full
  if (state === "ready" && part.state === "charging") {
    sound("unicorn_ready");
  }
  part.state = state;
  const bar = $("booster-bar");
  part.button.hidden = state === "hidden";
  bar.toggleAttribute("data-unicorn", state !== "hidden");
  bar.toggleAttribute("data-running", hud.unicorning);
  if (state === "hidden") {
    return;
  }
  part.button.dataset.state = state;
  part.button.disabled = state === "off";
  [part.bg.src, part.icon.src] = UNICORN_ART[state];
  part.ring.style.setProperty("--fill", `${state === "ready" ? 360 : Math.floor((charge * 360) / need)}deg`);
  part.ring.hidden = state === "waiting";
  const goal = hud.progress.unicorn_levels.wins;
  part.badge.hidden = state !== "waiting";
  part.badge.textContent = `${wins}/${goal}`;
  const words = state === "waiting" ? `${wins} of ${goal} wins` : `${charge} of ${need} charged`;
  part.button.setAttribute("aria-label", `Super Unicorn, ${words}`);
}

function pressUnicorn() {
  if (hud.armed || busy()) {
    return;
  }
  sound("button");
  const state = hud.unicorn.state;
  if (state === "waiting") {
    const left = hud.progress.unicorn_levels.wins - hud.progress.unicorn.wins;
    hud.actions.note(`Beat ${left} Levels to activate Super Unicorn!`);
  } else if (state === "charging") {
    hud.actions.note(UNICORN_ACTIVE_NOTE);
  } else if (state === "ready") {
    startUnicorn();
  }
}

// The bar is full: the Unicorn comes in with the clock held, then its tap lands and the clock waits for its run. With
// no pig in a slot to merge, nothing happens but a note
function startUnicorn() {
  const sim = hud.page.sim;
  if (!sim || gather(sim).length === 0) {
    hud.actions.note(UNICORN_EMPTY_NOTE);
    return;
  }
  sound("appear");
  hud.unicorning = true;
  hud.actions.hold("unicorn");
  hud.page.scene.picture.showSuper(false, true);
  drawUnicorn();
  hud.unicornTimer = setTimeout(landUnicorn, UNICORN_LEAD_MS);
}

// It stands: the tap goes to the bot, then the clock waits for the shots to land and the Unicorn to leave
function landUnicorn() {
  const sim = hud.page.sim;
  const known = sim ? sim.events.length : 0;
  if (!sim || hud.actions.tap(["unicorn"]) !== null) {
    endUnicorn();
    return;
  }
  const shots = sim.events.slice(known).filter((event) => event.k === "unicorn_shot");
  hud.unicornTimer = setTimeout(endUnicorn, hud.page.scene.picture.unicornMs(shots));
}

export function endUnicorn() {
  clearTimeout(hud.unicornTimer);
  if (!hud.unicorning) {
    return;
  }
  hud.unicorning = false;
  sound("unicorn_exit");
  hud.page.scene.picture.stopSuper();
  hud.actions.release("unicorn");
  drawUnicorn();
}

export function floorY() {
  return hud.floor;
}

// Where the queues must end: just above the booster buttons while the bar shows, else at the bottom of the screen. Tells
// the handler when the answer changed
export function measureFloor() {
  const bar = $("booster-bar");
  const scene = $("scene");
  let floor = scene.clientHeight - FLOOR_GAP;
  if (!bar.hidden && bar.offsetParent !== null && bar.children.length) {
    const top = Math.min(...[...bar.children].map((button) => button.getBoundingClientRect().top));
    floor = top - scene.getBoundingClientRect().top - FLOOR_GAP;
  }
  if (floor !== hud.floor) {
    hud.floor = floor;
    if (hud.floorHandler) {
      hud.floorHandler();
    }
  }
}

export function onFloor(handler) {
  hud.floorHandler = handler;
}

// Show what the player's progress says about each booster. `state` is the level's simulation, or null when none runs
export function setBoosters(progress, state) {
  hud.progress = progress;
  hud.sim = state;
  if (!progress) {
    return;
  }
  // The whole bar stays hidden until the first booster unlocks
  $("booster-bar").hidden = !hud.shown || !unlocked(progress, BOOSTERS[0].key);
  hud.buttons.forEach(drawButton);
  drawUnicorn();
  measureFloor();
}

// ---------- Free-tray counter ----------

// `free` of `total` belt places are free. Red when none is; it pops when the number changes
export function setCounter(free, total) {
  if (free === hud.free && total === hud.total) {
    return;
  }
  const first = hud.free === null;
  hud.free = free;
  hud.total = total;
  $("tray-free").textContent = String(free);
  $("tray-total").textContent = String(total);
  $("tray-counter").toggleAttribute("data-empty", free === 0);
  if (!first) {
    retrigger($("tray-counter"), "pop");
  }
}

// A tap found no free tray: the counter flashes red and shakes for half a second
export function flashCounter() {
  retrigger($("tray-counter"), "flash");
}

// The counter sits under the belt's entrance wherever the camera put it
function placeCounter() {
  if (!hud.page.scene) {
    return;
  }
  const spot = hud.page.scene.counterSpot();
  const node = $("tray-counter");
  node.style.left = `${spot.x}px`;
  node.style.top = `${spot.y}px`;
}

// ---------- Level screen ----------

// Put the level screen's parts up for `level` (an expanded level) with the player's progress
export function showHud(level, progress) {
  hud.shown = true;
  disarm();
  endShuffle();
  endBomb();
  endSuper();
  endUnicorn();
  hud.unicorn.state = null;
  hud.unicorn.look = "";
  if (!hud.hooked && hud.page.scene) {
    hud.hooked = true;
    hud.page.scene.onLayout(placeCounter);
  }
  const play = $("play");
  if (level.difficulty >= HARD_FROM) {
    play.dataset.hard = "";
  } else {
    delete play.dataset.hard;
  }
  $("level-pill-text").textContent = `Level ${level.number}`;
  $("back").hidden = true;
  $("gear").hidden = false;
  $("level-pill").hidden = false;
  $("tray-counter").hidden = false;
  hud.free = null;
  hud.finished = false;
  placeCounter();
  closeSettings();
  setBoosters(progress, null);
}

// Take the level screen's parts down; the menu's back button comes back
export function hideHud() {
  hud.shown = false;
  disarm();
  endShuffle();
  endBomb();
  endSuper();
  endUnicorn();
  delete $("play").dataset.hard;
  $("back").hidden = false;
  $("gear").hidden = true;
  $("level-pill").hidden = true;
  $("tray-counter").hidden = true;
  $("booster-bar").hidden = true;
  measureFloor();
  closeSettings();
}

// Called for every drawn frame with the level's simulation: the counter and the booster buttons follow it
export function frame(sim) {
  if (!hud.shown) {
    return;
  }
  setCounter(freeTrays(sim), trayTotal(sim));
  const finished = sim.over !== null || sim.finishing;
  const full = freeTrays(sim) === 0;
  const spare = canShuffle(sim);
  if (hud.sim !== sim || finished !== hud.finished || full !== hud.full || spare !== hud.spare) {
    hud.finished = finished;
    hud.full = full;
    hud.spare = spare;
    setBoosters(hud.progress, sim);
  }
  drawUnicorn();
}

// The coins' plus and an empty booster both open the shop. The handler gets a booster's name, or null for the plus
export function onShop(handler) {
  hud.shopHandler = handler;
}

// ---------- Settings dialog ----------

export function openSettings() {
  if (hud.open) {
    return;
  }
  hud.open = true;
  $("settings").hidden = false;
  hud.actions.hold("settings");
  $("settings-close").focus({ preventScroll: true });
}

export function closeSettings() {
  if (!hud.open) {
    return;
  }
  hud.open = false;
  $("settings").hidden = true;
  hud.actions.release("settings");
  resetRestart();
}

function resetRestart() {
  clearTimeout(hud.restartTimer);
  const button = $("restart-button");
  button.disabled = false;
  button.textContent = "Restart level";
}

function restart() {
  sound("button");
  const button = $("restart-button");
  button.disabled = true;
  button.textContent = "Restarting";
  if (hud.actions.restart()) {
    // The new level arriving closes the dialog (showHud)
    hud.restartTimer = setTimeout(resetRestart, RESTART_WAIT_MS);
  } else {
    resetRestart();
  }
}

// The sound effects and music switches. A sound module reads them with soundOn()/musicOn() and listens with onSwitch()
export function soundOn() {
  return hud.sound;
}

export function musicOn() {
  return hud.music;
}

// Called with ("sound" or "music", on) whenever the player flips a switch
export function onSwitch(handler) {
  hud.switchHandlers.push(handler);
}

function drawSwitch(id, on) {
  $(id).setAttribute("aria-checked", String(on));
}

function flip(name, key, id) {
  sound("button");
  hud[name] = !hud[name];
  writeSwitch(key, hud[name]);
  drawSwitch(id, hud[name]);
  hud.switchHandlers.forEach((handler) => handler(name, hud[name]));
}

// ---------- Setup ----------

export function initHud(page, actions) {
  Object.assign(hud, { page, actions });
  hud.sound = readSwitch(SOUND_KEY);
  hud.music = readSwitch(MUSIC_KEY);
  drawSwitch("sound-switch", hud.sound);
  drawSwitch("music-switch", hud.music);
  const bar = $("booster-bar");
  for (const def of BOOSTERS) {
    const part = makeButton(def);
    hud.buttons.set(def.key, part);
    bar.append(part.button);
  }
  hud.unicorn = makeUnicorn();
  bar.append(hud.unicorn.button);
  const counter = $("tray-counter");
  counter.addEventListener("animationend", () => counter.classList.remove("pop", "flash"));
  $("gear").addEventListener("click", () => {
    sound("button");
    openSettings();
  });
  $("settings-close").addEventListener("click", () => {
    sound("button");
    closeSettings();
  });
  $("settings").addEventListener("click", (event) => event.target === $("settings") && closeSettings());
  document.addEventListener("keydown", (event) => event.key === "Escape" && closeSettings());
  $("sound-switch").addEventListener("click", () => flip("sound", SOUND_KEY, "sound-switch"));
  $("music-switch").addEventListener("click", () => flip("music", MUSIC_KEY, "music-switch"));
  $("restart-button").addEventListener("click", restart);
  $("menu-button").addEventListener("click", () => {
    sound("button");
    actions.backToMenu();
  });
  $("coins-plus").addEventListener("click", () => {
    // Not while a booster waits for its pick or the Shuffle or the bomb plays: the clock is held for them already
    if (hud.armed || busy()) {
      return;
    }
    sound("button");
    if (hud.shopHandler) {
      hud.shopHandler(null);
    }
  });
}
