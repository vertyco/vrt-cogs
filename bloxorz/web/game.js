// Bloxorz's page: the live connection, the original's art and the screens it shows. The bot keeps every run and decides
// every landing; this page sends what the player presses and draws what the bot sends back.
//
// The root is a plain container holding the current screen's clips. Each screen is registered in `screens` as
//   { art?, enter(page), leave?(page), receive?(page, data), step?(page) }
// and is shown with show(name) / go(name). art: characters whose atlas pages must load first. step runs once a tick
// (36 a second, the original's rate).
import { backToMenu, connect } from "activityhub";
import { Application, Container, ImageSource, Texture } from "./vendor/pixi.min.mjs";
import { setupBoard } from "./board.js";
import { Library, setMatrix, setTextResolution } from "./flash.js";
import { setupLeaderboard } from "./leaderboard.js";
import { setupMenus } from "./menu.js";
import { setupPanels } from "./panels.js";
import { setupPieces } from "./pieces.js";
import { Sound } from "./sound.js";
import { isTouchScreen, setupTouch, SWITCH_BAND, SWITCH_SIDE } from "./touch.js";

const STAGE_WIDTH = 550;
const STAGE_HEIGHT = 300;
// After a stall (a hidden tab, a slow phone) the timelines skip ahead rather than race through every missed frame
const MOST_STEPS = 4;
const RETRY_MS = 2000;
// A new connection that keeps failing is tried a little further apart each time, up to this
const MOST_RETRY_MS = 15000;
// Failed tries at a new connection before the rest of the window is told the player is no longer connected. The
// page keeps trying after that
const TRIES_BEFORE_GONE = 3;
// The back button's corner of the page: its 36 pixels with 8 either side, which the original's stage stays out of
const BACK_ROOM = 52;
// The people button's place in the stage's bottom right corner (stage pixels from the edges), and its size in screen
// pixels, which follows the stage's scale between these
const PEOPLE_EDGE = 4;
const PEOPLE_SIZE = 26;
const PEOPLE_MOST = 36;
const PEOPLE_LEAST = 28;
// Below this much room under the people button (screen pixels) its arrival notes slide up instead
const NOTE_ROOM = 70;
// The end screen's Next button reaches this far right (stage pixels, with a little gap). A people button wider than
// the corner's room right of it would cover it, so it moves to the bar under the stage, or beside it, when one has room
const NEXT_RIGHT = 521;
const RECONNECTING = "Reconnecting...";
const OFFLINE = "Open this in Discord to play.";
const NO_GRAPHICS = "This device couldn't start the game's graphics.";
const NOT_CONNECTED = "Not connected";
const CLOSED_BECAUSE = {
  4003: "Bloxorz was turned off in this server.",
  4100: "Bloxorz was opened somewhere else.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const FONT = '14px "Square721 BT_10pt_st"';
// The original's `bc` clip (root depth 3, sprite 4): its frames 2 and 4 play the buttons' hover and press sounds
const BUTTON_SOUNDS = 4;
// Where the original's root places it (frame 1, depth 3): off the stage's left edge, so its frame 1 square never shows
const BUTTON_SOUNDS_AT = [1, 0, 0, 1, -181.5, -8];

const sound = new Sound();

const page = {
  hub: null,
  conn: null,
  offline: false,
  app: null,
  lib: null,
  // The stage at the original's size, and the root holding the shown screen's clips
  world: null,
  root: null,
  screen: null,
  // Counts screen changes, so a slow one that finished loading late doesn't replace a newer one
  showing: 0,
  // The clip of the main menu, Load Stage and Credits while they show, and the instruction pages while they show
  menu: null,
  instructions: null,
  // Plays the buttons' sounds (the original's bc clip), and the sound
  bc: null,
  sound,
  // What the page asked the bot to start: "new", "passcode", "continue", or null
  requested: null,
  // The run as the bot last saved it, the stage the bot last sent, and the keys held down
  saved: null,
  stageMsg: null,
  held: new Set(),
  // True from a stage's first roll until it is won or left, which marks the player busy for a friend's Join
  playing: false,
  // The attempt's counters, and the page clock reading (ms) when `seconds` was current
  moves: 0,
  falls: 0,
  seconds: 0,
  secondsAt: 0,
  // The menu's title animation skips ahead when set (the original's skiptoend and skiptomenu, read by sprite 197)
  skiptoend: false,
  skiptomenu: false,
  // The run's totals from the bot's `done`, and whether the menu clip is showing the end screen
  done: null,
  ending: false,
  clock: 0,
  toastTimer: null,
  // What the hub was last told, so only changes go to it, and whether the connection is gone for good
  reported: null,
  gone: false,
  // Tries at a new connection that failed in a row
  failedTries: 0,
  // What the bot's messages call for, by message key
  handlers: new Map(),
  // What the screens made in other files do for the original's script hooks, by hook name
  hooks: new Map(),
  // Hooks that reached the page with nothing to do them, named once
  unhandled: new Set(),
  // The swipes and the Switch button (touch.js): place(), update()
  touch: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  $("back").addEventListener("click", backToMenu);
  const hubReady = connect().then(
    (hub) => {
      // Placed at once, so the hub's floating button never shows
      $("people").append(hub.peopleButton());
      return hub;
    },
    (e) => e,
  );
  try {
    await buildStage();
  } catch (e) {
    console.error("Bloxorz: couldn't start drawing", e);
    toast(NO_GRAPHICS, 0);
    return;
  }
  go("menu");
  const hub = await hubReady;
  if (hub instanceof Error) {
    page.offline = true;
    toast(hub.message, 0);
    return;
  }
  page.hub = hub;
  page.offline = hub.offline;
  report();
  if (hub.offline) {
    toast(OFFLINE, 0);
    return;
  }
  goLive();
}

async function download(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`${url}: ${resp.status}`);
  }
  return resp;
}

// A picture from art/ as a texture. mipmaps: for one drawn much smaller than it is
async function picture(file, mipmaps = false) {
  const blob = await (await download(`art/${file}`)).blob();
  // Browsers don't premultiply a decoded bitmap's colors on upload, so it is decoded premultiplied, which is how
  // Pixi blends; the art's see-through panels would otherwise draw solid
  const bitmap = await createImageBitmap(blob, { premultiplyAlpha: "premultiply" });
  const source = new ImageSource({
    resource: bitmap,
    alphaMode: "premultiplied-alpha",
    autoGenerateMipmaps: mipmaps,
  });
  return new Texture({ source });
}

function loadPage(index) {
  return picture(page.lib.data.atlas.pages[index]);
}

async function buildStage() {
  const data = await (await download("art/flash.json")).json();
  const lib = new Library(data, loadPage);
  page.lib = lib;
  // Text is drawn once per change, so the font has to be ready before the first field
  try {
    await document.fonts.load(FONT);
  } catch (e) {
    console.warn("Bloxorz: couldn't load the font", e);
  }
  const app = new Application();
  await app.init({
    width: STAGE_WIDTH,
    height: STAGE_HEIGHT,
    background: 0x000000,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    preference: "webgl",
    // The art's overlay blend draws from what is already on the screen
    useBackBuffer: true,
  });
  page.app = app;
  $("stage").appendChild(app.canvas);
  app.stage.eventMode = "static";
  app.stage.hitArea = app.screen;
  lib.trackPointer(app.stage);
  registerScripts(lib);
  lib.onHook = hook;
  lib.onSound = (name, fade) => sound.play(name, fade);
  sound.load(data.sounds);
  page.world = new Container();
  page.root = new Container();
  await lib.need([BUTTON_SOUNDS]);
  page.bc = lib.make(BUTTON_SOUNDS);
  setMatrix(page.bc, BUTTON_SOUNDS_AT);
  page.world.addChild(page.root, page.bc);
  app.stage.addChild(page.world);
  page.touch = setupTouch(page, app.canvas, $("switch"));
  fit();
  new ResizeObserver(fit).observe($("stage"));
  // The hub's button arrives after the first fit and changes width with what it shows
  new ResizeObserver(() => placePeople(page.app.canvas.getBoundingClientRect(), page.lib.filterScale)).observe(
    $("people"),
  );
  app.ticker.add((ticker) => tick(ticker.deltaMS));
}

// The original's stage, as big as the room between Discord's buttons allows, with black bars around it. The bars
// beside it or the ones above and below it are kept wide enough for the back button, and on a touch screen for the
// Switch button too: beside the stage on a sideways phone, below it on an upright one. The stage stays in the middle,
// so both bars get the wider room
function fit() {
  const box = $("stage").getBoundingClientRect();
  const touch = isTouchScreen();
  const sideRoom = touch ? Math.max(BACK_ROOM, SWITCH_SIDE) : BACK_ROOM;
  const bandRoom = touch ? Math.max(BACK_ROOM, SWITCH_BAND) : BACK_ROOM;
  const beside = Math.min((box.width - sideRoom * 2) / STAGE_WIDTH, box.height / STAGE_HEIGHT);
  const above = Math.min(box.width / STAGE_WIDTH, (box.height - bandRoom * 2) / STAGE_HEIGHT);
  const scale = Math.max(0.05, beside, above);
  const width = Math.round(STAGE_WIDTH * scale);
  const height = Math.round(STAGE_HEIGHT * scale);
  page.app.renderer.resize(width, height);
  page.app.stage.hitArea = page.app.screen;
  page.world.scale.set(width / STAGE_WIDTH, height / STAGE_HEIGHT);
  page.lib.filterScale = scale;
  // Words drawn from now on match the screen's pixels
  setTextResolution(scale * page.app.renderer.resolution);
  const rect = page.app.canvas.getBoundingClientRect();
  page.touch.place(rect, box, above > beside);
  placePeople(rect, scale);
}

// The people button goes over the stage's bottom right corner, where the sponsor link was: placed and sized in stage
// pixels times the page's scale, so it stays clear of the board, the Menu and Moves boxes and the hint line. On a small
// stage the button can't shrink below a finger's size, so when it is too wide for the corner beside the end screen's
// Next button it goes just under the stage's corner, or just right of it, whichever bar has the room
function placePeople(rect, scale) {
  const people = $("people");
  const edge = PEOPLE_EDGE * scale;
  people.style.setProperty("--hub-people-size", `${Math.max(PEOPLE_LEAST, Math.min(PEOPLE_MOST, PEOPLE_SIZE * scale))}px`);
  const size = people.getBoundingClientRect();
  const under = document.documentElement.clientHeight - rect.bottom;
  const beside = document.documentElement.clientWidth - rect.right;
  let right = beside + edge;
  let bottom = under + edge;
  if (page.screen === "instructions") {
    // The instruction pages leave the stage's top right corner empty; the bottom right holds their Skip button
    bottom = under + rect.height - size.height - edge;
  } else if (size.width > (STAGE_WIDTH - PEOPLE_EDGE - NEXT_RIGHT) * scale) {
    if (under >= size.height + edge * 2) {
      bottom = under - size.height - edge;
    } else if (beside >= size.width + edge * 2) {
      right = beside - size.width - edge;
    }
  }
  people.style.right = `${right}px`;
  people.style.bottom = `${bottom}px`;
  people.classList.toggle("notes-up", bottom < NOTE_ROOM);
}

function tick(deltaMS) {
  page.clock += deltaMS;
  const frameMs = 1000 / page.lib.fps;
  let steps = Math.floor(page.clock / frameMs);
  page.clock -= steps * frameMs;
  if (steps > MOST_STEPS) {
    steps = MOST_STEPS;
    page.clock = 0;
  }
  for (let i = 0; i < steps; i += 1) {
    for (const node of [...page.root.children]) {
      node.advance?.();
    }
    page.bc.advance();
    screens[page.screen]?.step?.(page);
  }
  page.touch.update();
}

// ---------- The live connection ----------

async function goLive() {
  try {
    useConnection(await page.hub.socket());
  } catch (e) {
    closed(e.status);
  }
}

function useConnection(conn) {
  page.conn = conn;
  conn.on(receive);
  conn.onReconnecting(() => toast(RECONNECTING, 0));
  conn.onReconnected(hideToast);
  conn.onClose(closed);
}

// A connection gone for good: the page keeps trying for a new one, unless the bot can't take it back. After a few
// failed tries the window is told the player is no longer connected, so a friend's Join stops asking first
function closed(code) {
  page.conn = null;
  if (CLOSED_BECAUSE[code]) {
    toast(CLOSED_BECAUSE[code], 0);
    leaveGame();
    return;
  }
  // The lost connection, then each new one that failed or closed before the bot answered
  page.failedTries += 1;
  if (page.failedTries > TRIES_BEFORE_GONE) {
    leaveGame();
  }
  toast(RECONNECTING, 0);
  setTimeout(reconnect, Math.min(RETRY_MS * page.failedTries, MOST_RETRY_MS));
}

async function reconnect() {
  try {
    const conn = await page.hub.socket();
    // The bot sends everything again to a new connection
    hideToast();
    useConnection(conn);
  } catch (e) {
    closed(e.status);
  }
}

// True when the message went; false while the connection is down, when the request is better forgotten
function send(message) {
  return page.conn ? page.conn.send(message) : false;
}

// Registers what a bot message key calls for: fn(value, data) runs for every message holding that key
function onMessage(key, fn) {
  const list = page.handlers.get(key) ?? [];
  list.push(fn);
  page.handlers.set(key, list);
}

// True when a request can go to the bot. Otherwise the line the player sees says why: the browser preview has no bot,
// and a dropped connection is being retried
function needBot() {
  if (page.conn) {
    return true;
  }
  toast(page.offline ? OFFLINE : RECONNECTING, page.offline ? 0 : 4000);
  return false;
}

onMessage("hello", (value) => {
  page.saved = value?.saved ?? null;
  page.stageMsg = value?.game ?? null;
  // The bot answered, so the connection is good again: the window hears the true status and busy flag
  page.failedTries = 0;
  page.gone = false;
  page.reported = null;
  report();
});
onMessage("saved", (value) => {
  page.saved = value ?? null;
});
// A stage the bot sent becomes the page's, with its counters
function takeStage(value) {
  page.stageMsg = value;
  page.moves = value.moves;
  page.falls = value.falls;
  page.seconds = value.seconds;
  page.secondsAt = performance.now();
}

// While a board shows, the board holds the next stage until its unload frame, as the original's root did
onMessage("stage", (value) => {
  if (!page.board?.hold("stage", value)) {
    takeStage(value);
  }
});
onMessage("elsewhere", (text) => toast(text, 0));
onMessage("stopped", (text) => {
  page.stageMsg = null;
  page.playing = false;
  toast(text, 0);
  if (page.screen !== "menu") {
    go("menu");
  }
});

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  screens[page.screen]?.receive?.(page, data);
  for (const [key, value] of Object.entries(data)) {
    for (const fn of page.handlers.get(key) ?? []) {
      fn(value, data);
    }
  }
  report();
}

// ---------- Screens ----------

const screens = {};

// Shows a screen at once: its art loads, the old screen leaves, and the new one enters
async function show(name) {
  const screen = screens[name];
  if (!screen) {
    console.warn(`Bloxorz: no screen called ${name}`);
    return;
  }
  page.showing += 1;
  const token = page.showing;
  if (name !== "stage") {
    page.playing = false;
  }
  try {
    await Promise.all([page.lib.need(screen.art ?? []), screen.load?.(page)]);
  } catch (e) {
    console.error("Bloxorz: couldn't load the art", e);
    // Tried again, unless another screen was asked for meanwhile
    setTimeout(() => token === page.showing && show(name), RETRY_MS);
    return;
  }
  if (token !== page.showing) {
    return;
  }
  screens[page.screen]?.leave?.(page);
  page.screen = name;
  document.body.dataset.screen = name;
  screen.enter?.(page);
  placePeople(page.app.canvas.getBoundingClientRect(), page.lib.filterScale);
  report();
}

// Moves to another screen. The original cuts between its screens, so this is a plain show
function go(name) {
  return show(name);
}

// The screens made in other files take the hooks that end or start a screen: fn(argument, clip) for the hook's name
function onHook(kind, fn) {
  page.hooks.set(kind, fn);
}

// The original's script hooks that reach the page. gotoAndStop(label) then play() jumps to the label and plays on,
// which holds the menu's block in its resting loop
function hook(kind, argument, clip, second) {
  const handler = page.hooks.get(kind) ?? HOOKS[kind];
  if (handler) {
    handler(argument, clip, second);
    return true;
  }
  if (!page.unhandled.has(kind)) {
    page.unhandled.add(kind);
    console.warn(`Bloxorz: nothing handles the script hook ${kind} yet`);
  }
  return false;
}

// Hooks the clip itself answers
const HOOKS = {
  // play(): the clip runs on from where it stopped
  go: (argument, clip) => clip.play(),
  playlabel: (label, clip) => clip.gotoAndPlay(label),
  // DefineSprite_1165's sound picker: frame N plus a random even step, K steps to choose from
  rplay2: (from, clip, count) => clip.gotoAndPlay(from + 2 * Math.floor(page.lib.random() * count)),
  // A tile shows (1) or hides (2) its square in the landmask, which its parent holds (S320/f33, f40, f123, f130)
  mask: (shown, clip) => {
    if (!clip.label) {
      return;
    }
    const square = clip.parentClip?.child("landmask")?.child(`maskstone${clip.label.slice(5)}`);
    square?.gotoAndStop(shown ? 1 : 2);
  },
  // A cube shows its shadow, which the stage holds (S829/f85, f99)
  shadow: (name, clip) => {
    const shadow = clip.parentClip?.child("shadowsandglow")?.child(name);
    if (shadow) {
      shadow.visible = true;
    }
  },
};

// Frame scripts of the original's sprites, ported
function registerScripts(lib) {
  for (const [id, script] of [...menus.scripts, ...stage.scripts, ...pieces.scripts, ...panels.scripts]) {
    lib.scripts.set(id, script);
  }
}

// ---------- What the rest of the window sees ----------

// The hub passes on whatever it is told, even when nothing changed, so only changes go to it
function tell(text, busy) {
  const look = JSON.stringify([text, busy]);
  if (!page.hub || look === page.reported) {
    return;
  }
  page.reported = look;
  page.hub.status(text);
  page.hub.busy(busy);
}

function moveWord(count) {
  return `${count} ${count === 1 ? "move" : "moves"}`;
}

// What the player is doing: [the status line, whether a stage is in play]
function activity() {
  switch (page.screen) {
    case "instructions":
      return ["Instructions", false];
    case "leaderboard":
      return ["Leaderboard", false];
    case "stage":
      if (page.stageMsg) {
        return [`Stage ${page.stageMsg.n} · ${moveWord(page.moves - page.stageMsg.start_moves)}`, page.playing];
      }
      return ["Menu", false];
    default:
      return [page.ending ? "Finished Bloxorz!" : "Menu", false];
  }
}

function report() {
  if (!page.gone) {
    tell(...activity());
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveGame() {
  page.gone = true;
  tell(NOT_CONNECTED, false);
}

function toast(text, ms = 4000) {
  const line = $("toast");
  line.textContent = text;
  line.hidden = false;
  clearTimeout(page.toastTimer);
  if (ms) {
    page.toastTimer = setTimeout(hideToast, ms);
  }
}

function hideToast() {
  clearTimeout(page.toastTimer);
  $("toast").hidden = true;
}

// What the screens built in other files use
Object.assign(page, { send, onMessage, onHook, needBot, go, show, report, toast, hideToast, picture, takeStage });
// The screens, scripts and hooks of the main menu and the instruction pages, and of the stage
const menus = setupMenus(page);
const stage = setupBoard(page);
// The block and the cubes, on the stage's board
const pieces = setupPieces(page);
// The pause panel and the number boxes on it and on the end screen
const panels = setupPanels(page);
// The leaderboard screen
const leaderboard = setupLeaderboard();
Object.assign(screens, menus.screens, stage.screens, leaderboard.screens);
// The debug handle for checks
window.bloxorz = {
  page,
  sound,
  get lib() {
    return page.lib;
  },
};

start();
