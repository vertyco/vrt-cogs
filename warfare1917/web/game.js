// Warfare 1917's page: the live connection, the original's root and the screens it shows. The bot keeps every save
// and runs every battle; this page sends what the player presses and draws what the bot sends back.
//
// The root is a plain container holding the clips the original attached to its root, each at one of the original's
// depths (attach). A screen is { scripts?, enter(page), leave?(page), receive?(page, data), step?(page) } registered
// with registerScreen; scripts is { character id: fn(page, clip, frame) }, the screen's ports of the frame scripts of
// sprites it shows, run when their frames do. The page keeps the bot's word in page.save, page.lobby and
// page.battle, and onMessage(key, fn) runs fn(value, whole message) for each message that carries that key.
import { backToMenu, connect } from "activityhub";
import { Application, Container, ImageSource, Rectangle, Texture } from "./vendor/pixi.min.mjs";
import { Library, setTextResolution } from "./flash.js";
import * as campaign from "./campaign.js";
import * as custom from "./custom.js";
import { field } from "./field.js";
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as together from "./together.js";
import * as tweens from "./tween.js";

const STAGE_WIDTH = 800;
const STAGE_HEIGHT = 420;
// Steps of the original's clock run in one frame at most, so a stalled tab doesn't replay minutes at once
const MOST_STEPS = 4;
const RETRY_MS = 2000;
// How long a sent launch waits for the bot's answer before another press may send it again
const LAUNCH_WAIT_MS = 4000;
const MOST_RETRY_MS = 15000;
// Tries at a new connection that may fail in a row before the window is told the player is gone
const TRIES_BEFORE_GONE = 3;
// Room the black bars keep for the back button and its gap to the screen's edge
const BACK_ROOM = 52;
const EDGE = 8;
// Where the people button sits on the stage (spec 8.4), in the original's stage pixels. On menus it is in the top right
// corner of the metal frame: its right edge before the corner bolt, centred on the frame's top band between the bolts.
// In a battle it is on the HUD's "WARFARE 1917" plate, inside the plate's four bolts
const PEOPLE_FRAME = { right: 780, centerY: 8, height: 16 };
const PEOPLE_PLATE = { x: 8, y: 349, width: 78, height: 58 };
// The button's smallest and biggest size on the screen, in CSS pixels
const PEOPLE_MIN = 16;
const PEOPLE_MAX = 36;
const PEOPLE_FIT_TRIES = 4;
// An arrival note slides out under the button, and goes above it when less than this much screen is left below
const NOTE_ROOM = 48;
// A name shown in words (a status line, a tag) is cut to this many whole characters
const NAME_MOST = 16;
const RECONNECTING = "Reconnecting...";
const BATTLE_ENDED = "That battle has ended.";
const OFFLINE = "Open this in Discord to play.";
const NO_GRAPHICS = "This device couldn't start the game's graphics.";
const CLOSED_BECAUSE = {
  4003: "Warfare 1917 was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
const FONT_FAMILIES = ["DIN", "DIN-Bold", "DIN-Black", "Arno Pro", "Arno Pro Caption", "AlternateGothic2 BT", "Courier New"];
const NOT_CONNECTED = "Not connected";
// playIncomingSound (F5:3445-3451) plays a whistle one time in this many calls, one of this many
const INCOMING_ONE_IN = 6;
const INCOMING_KINDS = 3;
const SIDE_NAMES = { british: "British", german: "German" };

const page = {
  hub: null,
  conn: null,
  offline: false,
  app: null,
  lib: null,
  // The stage at the original's size, and the original's root inside it
  world: null,
  root: null,
  screen: null,
  // The screen that was showing before this one, null at the start
  previousScreen: null,
  // Screen name -> its definition; what the status line says for each screen (a line, or a function of the page
  // returning [line, busy])
  screens: {},
  statuses: {
    main: "Main menu",
    options: "Main menu",
    instructions: "Main menu",
    credits: "Main menu",
    select: "Main menu",
    map: campaignLine,
    upgrades: campaignLine,
    custom: "Custom battle",
    watch: "Main menu",
    versus: versusLine,
    versusSetup: "Versus",
    battle: battleLine,
  },
  // Bot message key -> handlers
  handlers: new Map(),
  // The bot's word: the campaign view (null for none, undefined before the bot has said), the window's lobby and the
  // battle this page sees
  save: undefined,
  lobby: null,
  battle: null,
  clock: 0,
  toastTimer: null,
  // What the hub was last told, so only changes go to it, and whether the connection is gone for good
  reported: null,
  gone: false,
  // Tries at a new connection that failed in a row
  failedTries: 0,
  // Where the people button sits now: "plate" or "frame"
  peopleSpot: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  $("back").addEventListener("click", backToMenu);
  window.warfare1917 = { page, find, tweens, sound, field, hud: field.hud, results: field.results, cutName };
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
    console.error("Warfare 1917: couldn't start drawing", e);
    toast(NO_GRAPHICS, 0);
    $("people").dataset.placed = "corner";
    return;
  }
  await show("main");
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

async function loadPage(index) {
  const blob = await (await download(`art/${page.lib.data.atlas.pages[index]}`)).blob();
  // Browsers don't premultiply a decoded bitmap's colors on upload, so it is decoded premultiplied, which is how
  // Pixi blends; the art's see-through panels would otherwise draw solid
  const bitmap = await createImageBitmap(blob, { premultiplyAlpha: "premultiply" });
  return new Texture({ source: new ImageSource({ resource: bitmap, alphaMode: "premultiplied-alpha" }) });
}

async function buildStage() {
  const data = await (await download("art/flash.json")).json();
  const lib = new Library(data, loadPage);
  page.lib = lib;
  // The Upgrades dial's ring (1394) shows the dial only inside the ring
  lib.alphaMasks.add(1394);
  // Text is drawn once per change, so the original's fonts have to be ready before the first field
  await Promise.all(
    FONT_FAMILIES.map((family) =>
      document.fonts.load(`14px "${family}"`).catch((e) => console.warn(`Warfare 1917: couldn't load ${family}`, e)),
    ),
  );
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
  skipUnbatchedMasks(app.renderer);
  $("stage").appendChild(app.canvas);
  app.stage.eventMode = "static";
  app.stage.hitArea = app.screen;
  lib.trackPointer(app.stage);
  lib.onHook = hook;
  sound.setSounds(lib.data.sounds);
  lib.onSound = sound.play;
  tweens.startTweens(app.ticker, lib);
  for (const def of Object.values(page.screens)) {
    setScripts(def);
  }
  fit();
  new ResizeObserver(fit).observe($("stage"));
  // The people button grows with the people in the window, and its place on the stage follows
  new ResizeObserver(placePeople).observe($("people"));
  page.world = new Container();
  page.root = new Container();
  // Clips sit in the root at the depths the original attached them at
  page.root.sortableChildren = true;
  page.world.addChild(page.root);
  app.stage.addChild(page.world);
  fit();
  app.ticker.add((ticker) => tick(ticker.deltaMS));
}

// PixiJS puts a mask picture in a batch only while something under the mask is shown. A mask whose parts are all
// hidden (a wreck's fire that didn't light) is in no batch, yet Pixi still updates it when a parent changes (the wreck
// fading in), which throws inside the ticker and stops all drawing for good. Such a mask draws nothing, so its update
// is skipped; the next rebuild that shows it batches it again
function skipUnbatchedMasks(renderer) {
  const pipe = renderer.renderPipes.sprite;
  const update = pipe.updateRenderable.bind(pipe);
  pipe.updateRenderable = (sprite) => {
    if (pipe._getGpuSprite(sprite)._batcher) {
      update(sprite);
    }
  };
}

// The original's stage, as big as the room between Discord's buttons allows, with black bars around it. A phone held
// sideways fills the screen's height; one held upright fits the stage to its width, centred, with the line asking for
// a sideways phone below it. The bars beside it or the ones above and below it are kept wide enough for the back
// button, so it never covers the art
function fit() {
  const box = $("stage").getBoundingClientRect();
  const beside = Math.min((box.width - BACK_ROOM * 2) / STAGE_WIDTH, box.height / STAGE_HEIGHT);
  const above = Math.min(box.width / STAGE_WIDTH, (box.height - BACK_ROOM * 2) / STAGE_HEIGHT);
  const scale = Math.max(0.05, beside, above);
  const width = Math.round(STAGE_WIDTH * scale);
  const height = Math.round(STAGE_HEIGHT * scale);
  page.app.renderer.resize(width, height);
  page.app.stage.hitArea = page.app.screen;
  page.world?.scale.set(width / STAGE_WIDTH, height / STAGE_HEIGHT);
  page.lib.filterScale = scale;
  // Words drawn from now on match the screen's pixels
  setTextResolution(scale * page.app.renderer.resolution);
  placeTurnLine(box, height);
  placePeople();
  together.place();
}

// "Turn your phone sideways for a bigger view" shows only while the window is taller than wide, in the room under the
// stage
function placeTurnLine(box, stageHeight) {
  const line = $("turn");
  const upright = box.height > box.width;
  line.hidden = !upright;
  if (upright) {
    line.style.top = `${box.top + (box.height + stageHeight) / 2 + EDGE}px`;
    line.style.width = `${Math.min(box.width, STAGE_WIDTH) - EDGE * 2}px`;
  }
}

// The people button on the HUD's plate while a battle's HUD shows, and in the metal frame's corner everywhere else
function peopleSpot() {
  return page.screen === "battle" && field.hud.clip?.visible ? "plate" : "frame";
}

// Puts the people button at its spot on the stage, as big as fits there. Called whenever the stage moves or resizes,
// the button grows or shrinks with the people in the window, or the spot changes
function placePeople() {
  const wrap = $("people");
  const canvas = page.app?.canvas.getBoundingClientRect();
  if (!canvas?.width) {
    return;
  }
  const scale = canvas.width / STAGE_WIDTH;
  const spot = peopleSpot();
  page.peopleSpot = spot;
  const plate = spot === "plate";
  const room = plate
    ? { width: PEOPLE_PLATE.width * scale, height: PEOPLE_PLATE.height * scale }
    : { width: Infinity, height: PEOPLE_FRAME.height * scale };
  let size = Math.max(PEOPLE_MIN, Math.min(PEOPLE_MAX, room.height));
  delete wrap.dataset.compact;
  wrap.style.setProperty("--hub-people-size", `${size}px`);
  let box = wrap.getBoundingClientRect();
  // Faces make the button wider than the plate, so it is made smaller until it fits. Its words don't shrink with it, so
  // the first guess (the same share of the size) is off, and the next ones follow the two widths measured so far
  let before = null;
  for (let tries = 0; tries < PEOPLE_FIT_TRIES && box.width > room.width && size > PEOPLE_MIN; tries += 1) {
    const slope = before ? (before.width - box.width) / (before.size - size) : box.width / size;
    before = { size, width: box.width };
    size = Math.max(PEOPLE_MIN, Math.min(size - 0.5, size - (box.width - room.width) / slope));
    wrap.style.setProperty("--hub-people-size", `${size}px`);
    box = wrap.getBoundingClientRect();
  }
  if (box.width > room.width) {
    // Still too wide on a very small stage: the faces go and the count stays
    wrap.dataset.compact = "true";
    box = wrap.getBoundingClientRect();
  }
  const centerX = canvas.left + (PEOPLE_PLATE.x + PEOPLE_PLATE.width / 2) * scale;
  const centerY = plate ? PEOPLE_PLATE.y + PEOPLE_PLATE.height / 2 : PEOPLE_FRAME.centerY;
  const left = plate ? centerX - box.width / 2 : canvas.left + PEOPLE_FRAME.right * scale - box.width;
  // Never above the screen's top edge, which is where a sideways phone's stage starts
  const top = Math.max(EDGE / 4, canvas.top + centerY * scale - box.height / 2);
  wrap.style.left = `${Math.round(left)}px`;
  wrap.style.top = `${Math.round(top)}px`;
  wrap.dataset.placed = "stage";
  wrap.dataset.note = window.innerHeight - (top + box.height) < NOTE_ROOM ? "up" : "down";
}

function tick(deltaMS) {
  if (peopleSpot() !== page.peopleSpot) {
    placePeople();
  }
  together.sync();
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
    page.screens[page.screen]?.step?.(page);
  }
}

// ---------- The original's root ----------

// Flash's attachMovie on the root: a new copy of an exported clip at one of the original's depths, named so find()
// and the screens can reach it. A clip already attached by that name goes first, as attaching over a name replaces it
function attach(exportName, depth, name) {
  detach(name);
  const clip = page.lib.makeExported(exportName);
  clip.label = name;
  clip.zIndex = depth;
  page.root.addChild(clip);
  return clip;
}

// Flash's removeMovieClip on a clip attached to the root
function detach(name) {
  for (const old of [...page.root.children]) {
    if (old.label === name) {
      old.destroy({ children: true });
    }
  }
}

// The original's script hooks that reach the page (port.json's art.hooks): lines of a clip's frame scripts that draw or
// sound rather than decide. The root's own frames (preloader and intros) are never shown, so none belong to it. Returns
// true when the hook was one of these
function hook(kind, arg, clip) {
  switch (kind) {
    case "go":
      clip.play();
      return true;
    case "childplay":
      // "weapon.muzzleFlash.play();": the named part, a dotted path from the clip, plays
      arg
        .split(".")
        .reduce((part, name) => part?.child?.(name), clip)
        ?.play();
      return true;
    case "gasmask": {
      const mask = clip.child("head")?.child?.("gasMask");
      if (mask) {
        mask.visible = arg === 1;
      }
      return true;
    }
    case "golabel":
      clip.gotoAndStop(arg);
      return true;
    case "sound":
      sound.play(arg);
      return true;
    case "incoming":
      if (Math.floor(page.lib.random() * INCOMING_ONE_IN) === 0) {
        sound.play(`sound_incoming_${arg}${1 + Math.floor(page.lib.random() * INCOMING_KINDS)}`);
      }
      return true;
    default:
      return false;
  }
}

// ---------- Screens ----------

function registerScreen(name, def) {
  page.screens[name] = def;
  if (page.lib) {
    setScripts(def);
  }
}

function setScripts(def) {
  for (const [id, script] of Object.entries(def.scripts ?? {})) {
    page.lib.scripts.set(Number(id), (clip, frame) => script(page, clip, frame));
  }
}

// Switches to a screen: the one showing leaves (told which screen comes next), the new one enters
async function show(name) {
  const next = page.screens[name];
  if (!next) {
    console.warn(`Warfare 1917: no screen called ${name}`);
    return;
  }
  page.screens[page.screen]?.leave?.(page, name);
  page.previousScreen = page.screen;
  page.screen = name;
  document.body.dataset.screen = name;
  try {
    await next.enter(page);
  } catch (e) {
    console.error(`Warfare 1917: couldn't show ${name}`, e);
  }
  report();
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

// A request that starts a battle. Pressing Launch twice quickly (a double click or tap) sends it once: later presses
// wait for the bot's battle or notice, or for the wait to run out. True when the request went or is already on its way
let launching = false;
let launchTimer = null;

function launch(message) {
  if (launching) {
    return true;
  }
  if (!send(message)) {
    return false;
  }
  launching = true;
  launchTimer = setTimeout(launched, LAUNCH_WAIT_MS);
  return true;
}

function launched() {
  launching = false;
  clearTimeout(launchTimer);
}

function onMessage(key, fn) {
  const list = page.handlers.get(key) ?? [];
  list.push(fn);
  page.handlers.set(key, list);
}

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  // Any word from the bot means the connection works: the player is back, and the window hears what they do again
  page.failedTries = 0;
  page.gone = false;
  remember(data);
  checkBattle(data);
  page.screens[page.screen]?.receive?.(page, data);
  for (const [key, value] of Object.entries(data)) {
    for (const fn of page.handlers.get(key) ?? []) {
      fn(value, data);
    }
  }
  report();
}

// What the page keeps of the bot's word
function remember(data) {
  if ("save" in data) {
    page.save = data.save;
  }
  if ("lobby" in data) {
    page.lobby = data.lobby;
  }
  if (data.battle) {
    page.battle = data.battle;
  }
  if (typeof data.notice === "string") {
    toast(data.notice);
  }
}

// Every join says which battle is the player's own (`mine`, null for none). A battle screen still showing a battle
// whose end it missed, because the page was away or reconnected, is put right here
function checkBattle(data) {
  const battle = page.battle;
  if (!("mine" in data) || page.screen !== "battle" || !battle || battle.result) {
    return;
  }
  if (battle.you !== null) {
    // A player's battle that is not theirs any more. When `mine` names another battle, its full battle follows
    if (data.mine === null) {
      page.battle = null;
      toast(BATTLE_ENDED);
      show("main");
    }
  } else if (page.lobby?.battles.some((row) => row.id === battle.id)) {
    // A new connection is not on the battle's watcher list, so the watch is asked for again
    send({ watch: battle.id });
  } else {
    page.battle = null;
    toast(BATTLE_ENDED);
    show("watch");
  }
}

// ---------- What the hub is told ----------

// The line and busy flag for what the player is doing now: the screen's entry in page.statuses, a line or a function of
// the page returning [line, busy]. Screens built later add their own
function activity() {
  const status = page.statuses[page.screen] ?? "Main menu";
  return typeof status === "function" ? status(page) : [status, false];
}

// "British campaign · Mission 3" on the campaign map and the upgrade screen
function campaignLine(from) {
  const save = from.save;
  return save ? [`${SIDE_NAMES[save.side]} campaign · Mission ${save.mission}`, false] : ["Main menu", false];
}

// The versus lobby: "Waiting for an opponent" while the player's own game is open
function versusLine() {
  return [together.waiting() ? "Waiting for an opponent" : "Versus", false];
}

// In a battle: "Mission 3 · TAKE COVER!", "Custom battle", "Versus vs Ann" or "Watching Ann". Busy while the player's
// own battle runs, so a friend's Join asks first
function battleLine(from) {
  const battle = from.battle;
  if (!battle) {
    return ["Main menu", false];
  }
  const names = battle.names ?? {};
  if (!battle.you) {
    const watched = names.british ?? names.german;
    return [watched ? `Watching ${cutName(watched)}` : "Watching", false];
  }
  const busy = !battle.result;
  if (battle.kind === "versus") {
    const other = names[battle.you === "british" ? "german" : "british"];
    return [other ? `Versus vs ${cutName(other)}` : "Versus", busy];
  }
  if (battle.kind === "custom") {
    return ["Custom battle", busy];
  }
  const map = battle.map ?? {};
  return [map.mission ? `Mission ${map.mission} · ${map.title}` : map.title, busy];
}

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

function report() {
  if (!page.gone) {
    const [text, busy] = activity();
    tell(text, busy);
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveGame() {
  page.gone = true;
  tell(NOT_CONNECTED, false);
}

// A name cut to NAME_MOST whole characters (an emoji or an accented letter is one, never half), with "..." when cut
const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
function cutName(name, most = NAME_MOST) {
  const letters = Array.from(segmenter.segment(String(name ?? "")), (part) => part.segment);
  return letters.length > most ? `${letters.slice(0, most - 1).join("")}...` : letters.join("");
}

// ---------- Checking from outside ----------

// The named or numbered clip at a dotted path from the stage, with where it is on the screen. Only what a player can
// see: a hidden or see-through clip, or one off the stage, is null
function find(path) {
  let node = page.world;
  for (const name of path.split(".")) {
    node = node && childNamed(node, name);
  }
  if (!node) {
    return null;
  }
  let alpha = 1;
  for (let up = node; up; up = up.parent) {
    if (!up.visible) {
      return null;
    }
    alpha *= up.alpha;
  }
  const bounds = node.getBounds();
  const screen = page.app.screen;
  const onStage = bounds.maxX > 0 && bounds.minX < screen.width && bounds.maxY > 0 && bounds.minY < screen.height;
  if (bounds.width <= 0 || bounds.height <= 0 || !onStage) {
    return null;
  }
  const canvas = page.app.canvas.getBoundingClientRect();
  const box = { x: canvas.left + bounds.x, y: canvas.top + bounds.y, w: bounds.width, h: bounds.height };
  const plain = (value) => value === null || !["object", "function"].includes(typeof value);
  const vars = node.vars ? Object.fromEntries(Object.entries(node.vars).filter(([, value]) => plain(value))) : null;
  return { ...box, frame: node.frame ?? null, alpha, vars };
}

function childNamed(parent, name) {
  const queue = [...parent.children];
  while (queue.length) {
    const node = queue.shift();
    if (node.destroyed) {
      continue;
    }
    if (node.label === name || String(node.charId) === name) {
      return node;
    }
    if (!node.label) {
      queue.push(...node.children);
    }
  }
  return null;
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

// ---------- The battle ----------

// A battle from the bot opens the battle screen, or is built again on it (a rejoin, or the next battle)
function openBattle(battle) {
  if (page.screen === "battle") {
    field.load(battle);
  } else {
    show("battle");
  }
}

const battleScreen = {
  enter: () => field.enter(),
  leave: () => field.leave(),
  step: () => field.step(),
};

// What the screens built in other files use
Object.assign(page, { send, launch, show, attach, detach, toast, hideToast, onMessage, registerScreen, find, report, field });
Object.assign(page, { dialog: menus.dialog, quickMessage: menus.quickMessage, cutName });
menus.bindPage(page);
campaign.bindPage(page);
custom.bindPage(page);
together.bindPage(page);
field.bind(page);
onMessage("battle", openBattle);
onMessage("battle", launched);
onMessage("notice", launched);
onMessage("u", (u) => field.update(u));
onMessage("over", (over) => field.over(over));
registerScreen("battle", battleScreen);
const allScreens = { ...menus.screens, ...campaign.screens, ...custom.screens, ...together.screens };
for (const [name, def] of Object.entries(allScreens)) {
  registerScreen(name, def);
}

start();
