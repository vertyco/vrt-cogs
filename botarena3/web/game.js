// Bot Arena 3's page: the live connection, the original's root timeline and the screens it shows. The bot keeps every
// career and runs every battle; this page sends what the player presses and draws what the bot sends back.
//
// The root clip is built once and shows one screen at a time on its frame labels. Each screen ports its root frame's
// script against the clips that frame places, and is registered in `screens` as
//   { frame?, art?, opens?, scripts?, enter(page), leave?(page), receive?(page, data), step?(page) }
// frame: the root's label (the screen's own name when left out). art: characters whose atlas pages must load first
// (the frame's own parts when left out). opens: the screen sets document.body.dataset.screen itself, once its
// buttons take presses (page.ready(name)); other screens have it set when they show. scripts:
// { character id: fn(page, clip, frame) }, the screen's ports of the frame scripts of sprites it shows, run when their
// frames do. receive gets every message from the bot while the screen shows, and step runs once a tick (33 a second).
import { backToMenu, connect } from "activityhub";
import { Application, Container, ImageSource, Rectangle, Texture } from "./vendor/pixi.min.mjs";
import { battle } from "./battle.js";
import { FPS, Library, makeFilter, setTextResolution, TextField } from "./flash.js";
import { challengeselect, levelselect, wingame } from "./lists.js";
import { shop } from "./shop.js";
import { Sound } from "./sound.js";
import { board, pvp, watch } from "./together.js";

const STAGE_WIDTH = 640;
const STAGE_HEIGHT = 480;
const FRAME_MS = 1000 / FPS;
// After a stall (a hidden tab, a slow phone) the timelines skip ahead rather than race through every missed frame
const MOST_STEPS = 4;
const RETRY_MS = 2000;
// A new connection that keeps failing (the bot refusing it as it joins) is tried a little further apart each time, up
// to this, so a page left open doesn't ask the bot every two seconds for ever
const MOST_RETRY_MS = 15000;
// Failed tries at a new connection before the rest of the window is told the player is no longer connected. The
// page keeps trying after that
const TRIES_BEFORE_GONE = 3;
// The back button's corner of the page: its 36 pixels with 8 either side, which the original's stage stays out of
const BACK_ROOM = 52;
const RECONNECTING = "Reconnecting...";
const OFFLINE = "Open this in Discord to play.";
const NO_GRAPHICS = "This device couldn't start the game's graphics.";
const CLOSED_BECAUSE = {
  4003: "Bot Arena 3 was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
};
// The battle's "next" screens that go by another name here
const SCREEN_NAMES = { challenges: "challengeselect" };
// The original's characters the page builds or reaches for by id
const FADER = 15;
const INTRO = 333;
const MENU = 362;
const MENU_BUTTONS = 361;
const MENU_BUTTON = 358;
const FLICKER = 339;
// The spinner on top of KURON plating, in the shop and in battle: 7.5 degrees a frame
const SPINNER = 151;
const SPIN = 7.5;
// Two guns' moving parts, in the shop and in battle: a spinner that starts at a random turn and turns 13 degrees a
// frame (sprite 94), and a crystal whose shine jumps to a random place each frame (sprite 115)
const GUN_SPINNER = 94;
const GUN_SPIN = 13;
const CRYSTAL = 115;
const INFO_MONITOR = 477;
const PROMPT_FIELD = 470;
const WIDE_BUTTON = 378;
const INSTRUCTIONS = 718;
const SHOP_BLURS = 755;
const QUALITY_BUTTONS = 611;
// The menu's leaving starts on this frame of its timeline (sprite 362)
const MENU_LEAVE = 61;
// The menu's buttons: their words, where each one leaves for, and whether the music fades out on the way (the
// original's "ms"). PVP and WATCH are new, made from the same button
const MENU_CHOICES = {
  b1: { words: "NEW CAREER", to: "shop", music: true },
  b2: { words: "CONTINUE", to: "shop", music: true },
  b3: { words: "CHALLENGE MODE", to: "challengeselect", music: true },
  b4: { words: "INSTRUCTIONS", to: "instructions", music: false },
  b5: { words: "SETTINGS/CREDITS", to: "settings", music: false },
  pvpbutton: { words: "PVP", to: "pvp", music: false },
  watchbutton: { words: "WATCH", to: "watch", music: false },
};
// What works in a plain browser, without the bot
const OFFLINE_CHOICES = ["b4", "b5"];
// Asked before a new career replaces an old one, on the shop's info monitor
const CONFIRM_WORDS = "START A NEW CAREER?\nYOUR OLD ONE WILL BE GONE.";
// The info monitor sits in the middle of the stage, its question in the upper half and the buttons under it
const CONFIRM_AT = { x: 113.5, y: 156 };
const CONFIRM_WORDS_Y = 36;
const CONFIRM_YES_Y = 104;
const CONFIRM_NO_Y = 132;
// Where the info monitor's flash leaves its screen standing
const MONITOR_SCREEN_Y = 80;
// The instructions' pages: the original's "next page" stops on its last one
const LAST_PAGE = 40;
// The volume sliders run 180 pixels, 1.8 to each step of 100
const SLIDER_RANGE = 180;
const SLIDER_STEP = 1.8;
// What the rest of the window sees the player doing on each screen. The intro, menu, instructions and settings are
// all the menu; PvP and battles say more (see activity)
const STATUS = {
  shop: "In the shop",
  levelselect: "Picking an arena",
  challengeselect: "Picking an arena",
  wingame: "Beat the game",
  watch: "Picking a battle to watch",
  board: "Looking at the leaderboard",
};
const IN_THE_MENU = "In the menu";
const NOT_CONNECTED = "Not connected";
const COMPUTER = "COMPUTER";
// The watchers' faces: the most shown before "+N", the gap kept from the screen's edges and the stage, the height
// of their row, and the narrowest box the "N watching" words fit beside the faces
const WATCHER_FACES = 6;
const EDGE = 8;
const FACES_ROW = 36;
const WORDS_ROOM = { beside: 72, under: 280, between: 280 };
// The longest name a tapped face says, in whole characters
const NAME_MOST = 24;
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  offline: false,
  app: null,
  lib: null,
  // The stage at the original's size: the root clip, the page's own panels over it, and the fader over both
  world: null,
  root: null,
  layer: null,
  fader: null,
  sound,
  screen: null,
  // Counts screen changes, so a slow one that finished loading late doesn't replace a newer one
  showing: 0,
  // The screen on its way while its art loads, so the intro's or the menu's own ending doesn't replace it
  loading: null,
  // The screen the fader shows once it is black, and whether the sound carries on through it (the original's
  // cancelstop). holding: the fade on its way has no screen yet. dark: it went black and waits for one
  next: null,
  cancelstop: false,
  holding: false,
  dark: false,
  // Whether the menu starts its music when it shows (the original's playstart)
  playstart: false,
  // The bot's game data, the player's career view (null for none) once the bot has said, and this window's lobby
  data: null,
  career: null,
  careerKnown: false,
  lobby: null,
  // The battle this page sees, as the bot last sent it whole, and the bot's updates to it since, which the battle
  // screen takes as it draws (they start coming while the screen fades in)
  battle: null,
  updates: [],
  menu: null,
  confirm: null,
  // The settings screen's SHOP BLURS choice (the original's noshopblur), and whether its sliders set the volumes
  noShopBlur: false,
  settingVolumes: false,
  clock: 0,
  toastTimer: null,
  // What the hub was last told, so only changes go to it, and whether the connection is gone for good
  reported: null,
  gone: false,
  // Tries at a new connection that failed in a row
  failedTries: 0,
  // The watchers' faces as last drawn, and the screen a friend's Join asks for once the intro is over
  watchLook: null,
  follow: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  $("back").addEventListener("click", backToMenu);
  window.botArena3 = { find };
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
    console.error("Bot Arena 3: couldn't start drawing", e);
    toast(NO_GRAPHICS, 0);
    return;
  }
  show("intro");
  loadTheRest();
  const hub = await hubReady;
  if (hub instanceof Error) {
    page.offline = true;
    toast(hub.message, 0);
    refreshMenu();
    return;
  }
  page.hub = hub;
  page.offline = hub.offline;
  hub.onPeople(renderWatchers);
  report();
  if (hub.offline) {
    toast(OFFLINE, 0);
    refreshMenu();
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
  // Text is drawn once per change, so the pixel font has to be ready before the first field
  try {
    await document.fonts.load('14px "04b_03b"');
  } catch (e) {
    console.warn("Bot Arena 3: couldn't load the pixel font", e);
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
  lib.onHook = hook;
  registerScripts(lib);
  fit();
  new ResizeObserver(fit).observe($("stage"));
  // The people button grows with the people in the window, and the bar beside the stage grows with it
  new ResizeObserver(fit).observe($("people"));
  await lib.need([FADER, INTRO]);
  page.world = new Container();
  // The root starts on its empty frame: its first frame is the original's loader, which the page doesn't use
  page.root = lib.make(0, data.sprites[0].labels.blank);
  page.root.stop();
  page.layer = new Container();
  page.fader = lib.make(FADER);
  page.fader.position.set(STAGE_WIDTH / 2, STAGE_HEIGHT / 2);
  page.fader.gotoAndStop("clear");
  page.fader.hitArea = new Rectangle(-STAGE_WIDTH / 2, -STAGE_HEIGHT / 2, STAGE_WIDTH, STAGE_HEIGHT);
  block(false);
  page.world.addChild(page.root, page.layer, page.fader);
  app.stage.addChild(page.world);
  fit();
  app.ticker.add((ticker) => tick(ticker.deltaMS));
}

// The rest of the art loads behind the intro: the menu's pages first, then the others
async function loadTheRest() {
  try {
    await page.lib.need([MENU]);
    await Promise.all(page.lib.data.atlas.pages.map((_, index) => page.lib.page(index)));
  } catch (e) {
    console.error("Bot Arena 3: couldn't load the art", e);
  }
}

// The original's stage, as big as the room between Discord's buttons allows, with black bars around it. The bars
// beside it or the ones above and below it are kept wide enough for the back button and the people button (as wide
// as it is now), so neither covers the art. The stage stays in the middle, so both side bars get the wider room
function fit() {
  const box = $("stage").getBoundingClientRect();
  const sideRoom = Math.max(BACK_ROOM, $("people").getBoundingClientRect().width + EDGE * 2);
  const beside = Math.min((box.width - sideRoom * 2) / STAGE_WIDTH, box.height / STAGE_HEIGHT);
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
  placeWatchers(box, width, height);
}

// The watchers' box goes in the wider black bars: down the left one under the back button, or in the top one. A
// top bar with room for it gives the faces a row of their own under the corner buttons; a short one fits them
// between the back button and the people button, as wide as the people button is now
function placeWatchers(box, width, height) {
  const side = (box.width - width) / 2;
  const top = (box.height - height) / 2;
  let layout = "beside";
  let left = box.left + EDGE;
  let room = side - EDGE * 2;
  let y = box.top + BACK_ROOM;
  if (side < top && top >= BACK_ROOM + FACES_ROW + EDGE) {
    layout = "under";
    room = box.width - EDGE * 2;
  } else if (side < top) {
    layout = "between";
    left = box.left + BACK_ROOM;
    room = $("people").getBoundingClientRect().left - EDGE - left;
    y = box.top + EDGE;
  }
  const row = $("watchers");
  row.dataset.layout = layout;
  row.classList.toggle("narrow", room < WORDS_ROOM[layout]);
  row.style.left = `${left}px`;
  row.style.top = `${y}px`;
  row.style.width = `${Math.max(0, room)}px`;
}

function tick(deltaMS) {
  page.clock += deltaMS;
  let steps = Math.floor(page.clock / FRAME_MS);
  page.clock -= steps * FRAME_MS;
  if (steps > MOST_STEPS) {
    steps = MOST_STEPS;
    page.clock = 0;
  }
  for (let i = 0; i < steps; i += 1) {
    page.root.advance();
    for (const node of [...page.layer.children]) {
      node.advance?.();
    }
    page.fader.advance();
    sound.step();
    screens[page.screen]?.step?.(page);
  }
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

// The bot's first message on a new connection: the player is back, and the window hears what they are doing again
function arrived() {
  page.failedTries = 0;
  page.gone = false;
}

// True when the message went; false while the connection is down, when the request is better forgotten
function send(message) {
  return page.conn ? page.conn.send(message) : false;
}

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  const before = page.battle?.id;
  remember(data);
  screens[page.screen]?.receive?.(page, data);
  answers(data);
  if (data.battle) {
    toBattle(data.battle, before);
  }
  moveOn(data);
  report();
  renderWatchers();
}

// What the page keeps of the bot's word: the game data, the career, the window's lobby and the battle on the page
function remember(data) {
  if ("data" in data) {
    page.data = data.data;
    arrived();
  }
  if ("career" in data) {
    page.career = data.career;
    page.careerKnown = true;
  }
  if ("lobby" in data) {
    page.lobby = data.lobby;
  }
  if (data.battle) {
    page.battle = data.battle;
    page.updates = [];
  }
  if (data.u && data.u.id === page.battle?.id) {
    page.updates.push(data.u);
  }
  if (data.watchers && data.watchers.id === page.battle?.id) {
    page.battle.watchers = data.watchers.people;
  }
}

// The bot's answer to the menu's NEW CAREER, and its notices
function answers(data) {
  if (data.done === "newCareer") {
    newCareerMade();
  } else if ("career" in data && page.menu?.waiting) {
    // The career came without the new one asked for: the connection dropped and the bot sent the career again, or
    // another device changed it first. Either way no new career is coming, so the menu comes back
    menuBack();
  }
  if (data.notice) {
    noticed(data.notice);
  }
}

// A screen may have started the fade to it already, at its own pace (the lists' PLAY). On the battle screen, the
// battle draws itself again, unless the page is on its way out of it
function toBattle(battle, before) {
  if (page.screen !== "battle" && page.next !== "battle") {
    go("battle", { fadeSound: 3 });
  } else if (battle.you !== null && battle.id !== before && leavingBattle()) {
    backToBattle();
  }
}

// Where the bot sends the player: on from the battle on the page (a battle left behind may still end after another
// one came, and only this one counts), or to a friend they joined
function moveOn(data) {
  if (data.over && data.over.id === page.battle?.id) {
    go(SCREEN_NAMES[data.over.next] ?? data.over.next, { fadeSound: 3 });
  }
  if (data.follow) {
    followed(SCREEN_NAMES[data.follow] ?? data.follow);
  }
}

// The bot puts a player who joined a friend where the friend is. A battle comes as the battle itself; anything else
// is a screen to show, which waits for the end of the intro, and is dropped once the player has gone somewhere
function followed(name) {
  if (page.screen === "intro" || page.screen === null) {
    page.follow = name;
  } else if (page.screen === "menu" && page.menu && !page.menu.choice && !page.confirm) {
    go(name, { keepSound: true });
  }
}

// The battle screen fading out, or black after its fade, on the way to another screen
function leavingBattle() {
  return page.screen === "battle" && page.next !== "battle" && Boolean(page.next || page.holding || page.dark);
}

// A battle of the player's own came while the page was leaving the battle screen (a watcher's LEAVE, or the end of
// the battle they watched): the page goes back to the battle screen instead, so they don't miss their own fight
function backToBattle() {
  if (page.next && !page.holding) {
    // The fade carries on, and ends on the battle screen
    page.next = "battle";
    return;
  }
  go("battle", { fadeSound: 3 });
}

function noticed(text) {
  toast(text);
  // A new career the bot wouldn't start: the menu comes back
  if (page.menu?.waiting) {
    menuBack();
  }
}

function menuBack() {
  page.menu.waiting = false;
  page.playstart = true;
  show("menu");
}

// ---------- Screens ----------

const screens = {
  intro: { art: [INTRO], enter: enterIntro },
  menu: { opens: true, enter: enterMenu, leave: leaveMenuScreen, receive: () => refreshMenu() },
  instructions: { enter: enterInstructions },
  settings: { enter: enterSettings, step: stepSettings, leave: leaveSettings },
  shop,
  levelselect,
  challengeselect,
  wingame,
  battle,
  pvp,
  watch,
  board,
};

// The characters a root frame places, whose art pages its screen needs
function artOn(frame) {
  return page.lib.frames(0)[frame - 1].map((entry) => entry.c);
}

// Shows a screen at once: the root goes to its frame, and its script runs
async function show(name) {
  if (name === "menu" && page.follow) {
    name = page.follow;
    page.follow = null;
  }
  const screen = screens[name];
  if (!screen) {
    console.warn(`Bot Arena 3: no screen called ${name}`);
    return;
  }
  const frame = page.root.frameOf(screen.frame ?? name);
  page.showing += 1;
  const token = page.showing;
  page.loading = name;
  try {
    await page.lib.need(screen.art ?? artOn(frame));
  } catch (e) {
    console.error("Bot Arena 3: couldn't load the art", e);
    // Tried again, unless another screen was asked for meanwhile
    setTimeout(() => token === page.showing && show(name), RETRY_MS);
    return;
  }
  if (token !== page.showing) {
    return;
  }
  page.loading = null;
  screens[page.screen]?.leave?.(page);
  closeConfirm();
  // A screen after a fade that waited in the dark: the fader clears again
  if (page.dark) {
    page.dark = false;
    block(false);
    page.fader.gotoAndPlay("fadein");
  }
  page.screen = name;
  // A screen shown again starts over, as it does when the original comes back to its frame from another
  if (page.root.frame === frame) {
    page.root.gotoAndStop("blank");
  }
  page.root.gotoAndStop(frame);
  if (!screen.opens) {
    ready(name);
  }
  screen.enter?.(page);
  report();
  renderWatchers();
}

function ready(name) {
  if (page.screen === name) {
    document.body.dataset.screen = name;
  }
}

// The original's fades between screens: the fader goes black, the next screen shows, then it clears again by itself.
// keepSound: the sound carries on (the original's cancelstop). fadeSound: how fast the sound fades out on the way.
// A null name fades out and stays black until a later go() names the screen: a battle's banner fades out before the
// bot says where the player goes next
function go(name, { keepSound = false, fadeSound = 0 } = {}) {
  if (page.dark) {
    if (name) {
      show(name);
    }
    return;
  }
  if (page.holding) {
    if (name) {
      page.holding = false;
      page.next = name;
    }
    return;
  }
  if (!name && page.next) {
    return;
  }
  if (fadeSound) {
    sound.fadeOut(fadeSound);
  }
  page.cancelstop = keepSound;
  page.next = name;
  page.holding = !name;
  block(true);
  page.fader.gotoAndPlay("fadeout");
}

// While the fader goes black, it takes every press (the original gave it an empty onPress)
function block(on) {
  page.fader.eventMode = on ? "static" : "none";
}

function fadeoutCompleted() {
  if (!page.cancelstop) {
    sound.stopAll();
  }
  page.cancelstop = false;
  const next = page.next;
  page.next = null;
  if (page.holding) {
    // Black, and still taking presses, until the next screen is named
    page.holding = false;
    page.dark = true;
    page.fader.gotoAndStop("end");
    return;
  }
  block(false);
  if (next) {
    show(next);
  }
}

// The original's script hooks that reach the page
function hook(kind, argument, clip) {
  if (kind === "fadeoutcompleted") {
    fadeoutCompleted();
    return true;
  }
  if (kind === "parentstop" && clip.parentClip === page.root) {
    // A screen already on its way (the battle the bot sent while the intro played, its art still loading) goes ahead
    // instead, and the intro holds its last frame until it shows
    if (page.next || page.loading) {
      clip.stop();
    } else {
      show(argument);
    }
    return true;
  }
  return false;
}

// Frame scripts of the original's sprites, ported
function registerScripts(lib) {
  lib.scripts.set(MENU_BUTTON, menuButtonScript);
  lib.scripts.set(MENU_BUTTONS, setUpMenu);
  lib.scripts.set(MENU, menuLeft);
  lib.scripts.set(FLICKER, flicker);
  lib.scripts.set(SPINNER, spinner);
  lib.scripts.set(GUN_SPINNER, gunSpinner);
  lib.scripts.set(CRYSTAL, crystal);
  for (const screen of Object.values(screens)) {
    for (const [id, script] of Object.entries(screen.scripts ?? {})) {
      lib.scripts.set(Number(id), (clip, frame) => script(page, clip, frame));
    }
  }
}

// A part of a clip the original left unnamed, by its character
function partOf(clip, id) {
  for (const slot of clip.slots.values()) {
    if (slot.node.charId === id) {
      return slot.node;
    }
  }
  return null;
}

// ---------- Intro (root frame 2) ----------

function enterIntro() {
  sound.fadeIn(2);
  sound.music("dnb");
  page.playstart = false;
}

// The KURON plating's spinner (sprite 151)
function spinner(clip) {
  clip.onEnterFrame = () => {
    clip.angle += SPIN;
  };
}

// Flash's random(n): a whole number from 0 to n - 1. Flash drops n's fraction first, and gives 0 for n below 1
function random(n) {
  return Math.floor(page.lib.random() * Math.max(0, Math.floor(n)));
}

function gunSpinner(clip) {
  clip.angle = random(360);
  clip.onEnterFrame = () => {
    clip.angle += GUN_SPIN;
  };
}

function crystal(clip) {
  const shine = clip.child("shine");
  shine.onEnterFrame = () => {
    shine.x = -(random(34) + 6);
  };
}

// The menu hologram's glow (sprite 339): a random picture, strength, size and tilt each frame
function flicker(clip) {
  clip.onEnterFrame = () => {
    clip.gotoAndStop(random(4) + 2);
    clip.alpha = (20 + random(30) + random(30) + random(30)) / 100;
    const size = random(40) + 90;
    const wide = size - random(60);
    const tall = size + random(60) + Math.pow(random(3), 5) * 3;
    clip.scale.set(wide / 100, tall / 100);
    clip.angle = random(30) - 15;
  };
}

// ---------- Menu (root frame 3, sprites 361 and 362) ----------

function enterMenu() {
  page.fader.gotoAndStop("clear");
  if (page.playstart) {
    sound.fadeIn(2);
    sound.music("dnb");
  }
}

function leaveMenuScreen() {
  page.menu = null;
}

// Each menu button (sprite 358): frame 2, or 3 under the pointer, when it works
function menuButtonScript(button) {
  button.gotoAndStop(2);
  button.setHandler("onRollOver", () => {
    if (button.vars.ena) {
      button.gotoAndStop(3);
    }
  });
  button.setHandler("onRollOut", () => {
    if (button.vars.ena) {
      button.gotoAndStop(2);
    }
  });
  button.setHandler("onPress", () => {
    if (button.vars.ena) {
      menuPressed(button.label);
    }
  });
}

// The buttons' holder (sprite 361) appears as the menu opens: PLAY MORE GAMES goes, PVP and WATCH take its place
function setUpMenu(holder) {
  const last = holder.child("b6");
  last.visible = false;
  const spacing = last.y - holder.child("b5").y;
  const buttons = {};
  for (const [name, choice] of Object.entries(MENU_CHOICES)) {
    let button = holder.child(name);
    if (!button) {
      const index = Object.keys(buttons).length - 5;
      button = holder.attach(page.lib.make(MENU_BUTTON), name);
      button.position.set(last.x, last.y + spacing * index);
    }
    button.set("dt", choice.words);
    buttons[name] = button;
  }
  page.menu = { holder, buttons, choice: null, left: false, waiting: false };
  refreshMenu();
}

function menuEnabled(name) {
  if (page.offline) {
    return OFFLINE_CHOICES.includes(name);
  }
  if (name === "b1") {
    return page.careerKnown;
  }
  if (name === "b2") {
    return page.careerKnown && page.career !== null;
  }
  return true;
}

// A button that can't be used is greyed to half, as the original greys LOAD CAREER without a save. NEW CAREER waits
// for the bot to say whether there is a career to ask about
function refreshMenu() {
  const menu = page.menu;
  if (!menu || menu.choice) {
    return;
  }
  for (const [name, button] of Object.entries(menu.buttons)) {
    const on = menuEnabled(name);
    button.vars.ena = on;
    button.alpha = on ? 1 : 0.5;
    if (!on && button.frame === 3) {
      button.gotoAndStop(2);
    }
  }
  if (page.offline || page.careerKnown) {
    ready("menu");
  }
}

function menuPressed(name) {
  if (!page.menu || page.menu.choice || page.confirm) {
    return;
  }
  if (name === "b1" && page.career) {
    openConfirm();
    return;
  }
  leaveMenu(name);
}

// The original's leaving: the music fades (or carries on), every other button goes, and the menu plays out
function leaveMenu(name) {
  const menu = page.menu;
  if (name === "b1") {
    menu.waiting = send({ newCareer: true });
    if (!menu.waiting) {
      return;
    }
  }
  const choice = MENU_CHOICES[name];
  menu.choice = name;
  if (choice.music) {
    sound.fadeOut(4);
  } else {
    page.cancelstop = true;
  }
  for (const [other, button] of Object.entries(menu.buttons)) {
    button.visible = other === name;
  }
  menu.holder.child("b0").visible = false;
  const button = menu.buttons[name];
  button.setHandler("onRollOver", null);
  button.setHandler("onRollOut", null);
  menu.holder.parentClip.gotoAndPlay(MENU_LEAVE);
}

// The menu's last frame (sprite 362, frame 90): black, and on to the chosen screen
function menuLeft(clip) {
  const menu = page.menu;
  if (!menu) {
    return;
  }
  // A screen the bot sent while the menu played out (the player's own battle) goes ahead instead of the choice
  const elsewhere = Boolean(page.next || page.loading);
  page.fader.gotoAndPlay("end");
  page.playstart = MENU_CHOICES[menu.choice].music;
  menu.left = true;
  clip.stop();
  // A new career goes on once the bot has made it
  if (!menu.waiting && !elsewhere) {
    show(MENU_CHOICES[menu.choice].to);
  }
}

function newCareerMade() {
  const menu = page.menu;
  if (!menu?.waiting) {
    return;
  }
  menu.waiting = false;
  if (menu.left) {
    show("shop");
  }
}

// ---------- New career over an old one: the shop's info monitor asks first ----------

// A holder that steps the clips in it, for the page's own panels
class Panel extends Container {
  advance() {
    for (const node of [...this.children]) {
      node.advance?.();
    }
  }
}

function confirmButton(name, words, y, pressed) {
  const button = page.lib.make(WIDE_BUTTON);
  button.set("displaytext", words);
  button.position.set(205, y);
  button.setHandler("onPress", pressed);
  return [button, name];
}

async function openConfirm() {
  const lib = page.lib;
  const panel = new Panel();
  panel.label = "confirm";
  // Nothing under the panel takes a press while its art loads and while it asks
  panel.eventMode = "static";
  panel.hitArea = new Rectangle(0, 0, STAGE_WIDTH, STAGE_HEIGHT);
  page.layer.addChild(panel);
  page.confirm = panel;
  try {
    await lib.need([INFO_MONITOR, WIDE_BUTTON]);
  } catch (e) {
    console.error("Bot Arena 3: couldn't load the art", e);
    if (page.confirm === panel) {
      closeConfirm();
    }
    return;
  }
  // Another screen showing meanwhile closed it
  if (page.confirm !== panel) {
    return;
  }
  const monitor = lib.make(INFO_MONITOR);
  monitor.position.set(CONFIRM_AT.x, CONFIRM_AT.y);
  const screen = monitor.child("screen");
  screen.gotoAndStop("prompt");
  screen.set("txt_displaytext", "");
  flashMonitor(screen);
  // The monitor's own prompt field holds one line, so the question takes two in the same format
  const prompt = lib.data.texts[PROMPT_FIELD];
  const [, , right, bottom] = prompt.bounds;
  const words = new TextField({
    ...prompt,
    bounds: [-2, -2, right, bottom * 2 + prompt.leading],
    multiline: true,
    var: "",
    text: CONFIRM_WORDS,
  });
  words.bind(null);
  words.position.set(205 - right / 2, CONFIRM_WORDS_Y);
  monitor.attach(words);
  monitor.attach(...confirmButton("yes", "YES", CONFIRM_YES_Y, confirmed));
  monitor.attach(...confirmButton("no", "NO", CONFIRM_NO_Y, closeConfirm));
  panel.addChild(monitor);
}

// The info monitor's flash when its page changes (the shop's flasher): white that fades by a tenth each frame,
// shaking the monitor's screen and blurring it up and down (unless SHOP BLURS is off) while it lasts
function flashMonitor(screen) {
  const flasher = screen.child("flasher");
  let alpha = 100;
  flasher.alpha = 1;
  flasher.onEnterFrame = () => {
    if (alpha > 0.5) {
      alpha /= 1.1;
    }
    if (alpha > 0) {
      screen.y = (random(alpha) - alpha / 2) / 10 + MONITOR_SCREEN_Y;
      if (!page.noShopBlur) {
        const blur = { type: "blur", x: 0, y: random(alpha / 4) + alpha / 4, passes: 1 };
        const made = makeFilter(blur, screen.filters?.[0], page.lib.filterScale);
        screen.filters = made ? [made] : null;
      }
    }
    if (alpha <= 0.5) {
      alpha = 0;
      screen.y = MONITOR_SCREEN_Y;
      screen.filters = null;
    }
    flasher.alpha = alpha / 100;
  };
}

function confirmed() {
  closeConfirm();
  leaveMenu("b1");
}

function closeConfirm() {
  if (page.confirm) {
    page.confirm.destroy({ children: true });
    page.confirm = null;
  }
}

// ---------- Instructions (root frame 9, sprite 718) ----------

function enterInstructions() {
  const book = partOf(page.root, INSTRUCTIONS);
  // The previous, next and exit buttons, at depths 6, 9 and 12 of its first 40 pages
  const [previous, next, exit] = [6, 9, 12].map((depth) => book.at(depth));
  previous.setHandler("onPress", () => {
    if (book.frame > 1) {
      book.gotoAndStop(book.frame - 1);
    }
  });
  next.setHandler("onPress", () => {
    if (book.frame < LAST_PAGE) {
      book.gotoAndStop(book.frame + 1);
    }
  });
  exit.setHandler("onPress", () => go("menu", { keepSound: true }));
}

// ---------- Settings (root frame 13) ----------

function enterSettings() {
  const root = page.root;
  const svol = root.child("svol");
  const mvol = root.child("mvol");
  svol.set("displaytext", "SOUND VOLUME");
  mvol.set("displaytext", "MUSIC VOLUME");
  for (const [holder, volume] of [
    [svol, sound.soundVolume],
    [mvol, sound.musicVolume],
  ]) {
    const slider = holder.child("slider");
    slider.y = SLIDER_RANGE - volume * SLIDER_STEP;
    slider.setHandler("onPress", () => slider.startDrag(true, [0, 0, 0, SLIDER_RANGE]));
    slider.setHandler("onRelease", () => slider.stopDrag());
    slider.setHandler("onReleaseOutside", () => slider.stopDrag());
    slider.onEnterFrame = () => holder.set("amount", Math.round(100 - slider.y / SLIDER_STEP));
  }
  // The original's LOW, MID and HIGH were Flash's drawing quality, which the browser decides here
  partOf(root, QUALITY_BUTTONS).visible = false;
  const blurs = partOf(root, SHOP_BLURS);
  blurs.at(1).setHandler("onPress", () => {
    page.noShopBlur = false;
  });
  blurs.at(3).setHandler("onPress", () => {
    page.noShopBlur = true;
  });
  page.settingVolumes = true;
  root.child("donebut").setHandler("onPress", () => {
    page.settingVolumes = false;
    go("menu", { keepSound: true });
  });
}

// The sliders set the volumes every frame, as the original's settings frame does
function stepSettings() {
  const sliders = [page.root.child("svol"), page.root.child("mvol")];
  if (!page.settingVolumes || sliders.some((holder) => holder?.get("amount") === undefined)) {
    return;
  }
  sound.setVolumes(sliders[0].get("amount"), sliders[1].get("amount"));
}

function leaveSettings() {
  page.settingVolumes = false;
}

// ---------- Who's here ----------

// What the rest of the window sees this player doing, and whether a battle of their own is on, where leaving costs
// them the battle
function activity() {
  const battle = page.battle;
  if (page.screen === "battle" && battle) {
    return [battleActivity(battle), battle.you !== null];
  }
  if (page.screen === "pvp") {
    const mine = page.hub?.player?.id;
    const waiting = Boolean(page.lobby?.fights?.some((fight) => fight.user === mine));
    return [waiting ? "Waiting for a 1 vs 1" : "Looking for a 1 vs 1", false];
  }
  return [STATUS[page.screen] ?? IN_THE_MENU, false];
}

// The arena's or challenge's name as its list shows it, or who fights whom
function battleActivity(battle) {
  const { you, kind, title, names } = battle;
  if (you === null) {
    return `Watching ${names.map((name) => name ?? COMPUTER).join(" vs ")}`;
  }
  if (kind === "pvp") {
    return `Battle vs ${names[2 - you]}`;
  }
  return kind === "challenge" ? `Challenge: ${title}` : title;
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
    tell(...activity());
  }
}

// The game's connection is gone for good, so a friend's Join has nothing to interrupt
function leaveGame() {
  page.gone = true;
  tell(NOT_CONNECTED, false);
}

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

function cut(name) {
  const letters = characters(name);
  return letters.length > NAME_MOST ? `${letters.slice(0, NAME_MOST - 1).join("")}\u2026` : name;
}

// The people watching the battle on the screen, from the bot, dimmed while the hub's list says they're away
function renderWatchers() {
  const battle = page.screen === "battle" ? page.battle : null;
  const people = page.hub?.people ?? [];
  const mine = page.hub?.player?.id;
  const watchers = (battle?.watchers ?? []).map((watcher) => ({
    id: watcher.id,
    name: watcher.name,
    avatar: watcher.avatar,
    you: watcher.id === mine,
    away: Boolean(people.find((person) => person.id === watcher.id)?.away),
  }));
  const shown = watchers.slice(0, WATCHER_FACES);
  // Lists arrive several times a second, and a face rebuilt between a press and its release loses the tap
  const look = JSON.stringify([watchers.length, shown]);
  if (look === page.watchLook) {
    return;
  }
  page.watchLook = look;
  const box = $("watchers");
  box.hidden = !watchers.length;
  box.replaceChildren(...(watchers.length ? watcherRow(shown, watchers.length) : []));
}

function watcherRow(shown, count) {
  const row = shown.map(watcherFace);
  const more = count - row.length;
  if (more > 0) {
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

// A watcher's picture, or their name's first letter when it can't load. Hovering shows their name; tapping says it,
// for phones
function watcherFace(person) {
  const face = document.createElement("button");
  face.type = "button";
  face.className = "face";
  const name = person.you ? "You" : person.name;
  face.title = name;
  face.setAttribute("aria-label", name);
  face.classList.toggle("away", person.away);
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
    face.blur();
    // The name sits between marks that keep a right-to-left name from turning the sentence around
    toast(person.you ? "That's you." : `\u2068${cut(person.name)}\u2069 is watching.`, 2500);
  });
  return face;
}

// ---------- Tests and the toast ----------

// A clip's bounds on the page in CSS pixels, from a path walked from the stage of instance names or, for clips the
// original left unnamed, art ids ("b1", "confirm.yes", "718.657"). Unnamed clips are looked through on the way. With
// the bounds come the clip's frame, its alpha on the page (its own times its parents'), the variables its text
// fields show, and for a picture of words or a cached picture, its pixels per stage pixel and how many pixels wide
// it is drawn. Null when the clip is missing, hidden or off the stage. It only reads
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
  const pixels = node.canvas?.width ?? node.texture?.source?.pixelWidth ?? null;
  return { ...box, frame: node.frame ?? null, alpha, vars, density: node.density ?? null, pixels };
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

// What the screens built in other files use
Object.assign(page, { send, go, show, ready, toast, hideToast, find, partOf, flashMonitor, random });

start();
