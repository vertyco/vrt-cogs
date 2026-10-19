// The Last Stand: Union City's page: the stage, the original's root and the screens it shows. The whole game runs
// here; the bot only keeps save slots.
//
// The root is a plain container holding the clips the original attached to its root, each at one of the depth bands
// below (attach). A screen is { scripts?, enter(page), leave?(page, next), step?(page) } registered with
// registerScreen; scripts is { character id: fn(page, clip, frame) }, the screen's ports of the frame scripts of
// sprites it shows. onHook(kind, fn) registers the part of the original's script hooks (port.json's art.hooks) that
// one system owns: fn(arg, clip, values) returns true when it did what the hook asks.
//
// The world's clock, input and story live in world.js, input.js and story.js; tick() below gives the world one step for
// each of the original's frames. window.laststand holds the page's state for the checks that drive it, and
// laststand.debug the helpers those checks use (no button or key reaches them).
import { connect } from "activityhub";
import { Application, Container, Graphics, Text } from "./vendor/pixi.min.mjs";
import { applyColor, bakeQueued, Library, rebakeAll, setTextResolution } from "./flash.js";
import { ACHIEVE_LOAD_CALLS, achieve, achieveDebug, initAchieve } from "./achieve.js";
import { art, coreLoaded, download, initArt, loadGroup, loadPage } from "./art.js";
import { BACKPACK_LOAD_CALLS, backpack, backpackDebug, initBackpack } from "./backpack.js";
import { boxesDebug, initBoxes } from "./boxes.js";
import { citymap, citymapDebug, initCityMap } from "./citymap.js";
import { collide, initCollide } from "./collide.js";
import { combat, combatDebug, initCombat } from "./combat.js";
import { companions, companionsDebug, initCompanions } from "./companions.js";
import { CREATE_SCREEN, create, createDebug, initCreate } from "./create.js";
import { cutscenes, cutscenesDebug, initCutscenes } from "./cutscenes.js";
import { DEATH_LOAD_CALLS, death, deathDebug, initDeath } from "./death.js";
import { dialog, dialogDebug, initDialog } from "./dialog.js";
import { data, loadData } from "./data.js";
import { director, directorDebug, initDirector, musicDirector } from "./director.js";
import { drops, dropsDebug, initDrops } from "./drops.js";
import { effects, initEffects } from "./effects.js";
import { ending, ENDING_HOOKS, endingDebug, initEnding } from "./ending.js";
import { humans, humansDebug, initHumans } from "./humans.js";
import { help, helpDebug, initHelp } from "./help.js";
import { HUD_LOAD_ACTIONS, HUD_LOAD_CALLS, hud, hudDebug, initHud } from "./hud.js";
import { input } from "./input.js";
import { initIntro, intro, INTRO_HOOKS, INTRO_SCREEN, introDebug } from "./intro.js";
import { initInteract, interact, interactDebug } from "./interact.js";
import { initInventory, inventory, inventoryDebug } from "./inventory.js";
import { initJournal, journal, journalDebug } from "./journal.js";
import { initLocks, locks, locksDebug } from "./locks.js";
import { initLight, light } from "./light.js";
import { initMenus, MENU_LOAD_CALLS, MENU_SCREENS, menus, menusDebug } from "./menus.js";
import { initNotes, notes, notesDebug } from "./notes.js";
import { initNPCs, npcs, npcsDebug } from "./npcs.js";
import { initPanels, panelsDebug } from "./panels.js";
import { initPause, pause, pauseDebug } from "./pause.js";
import { initPlayer, player, playerDebug } from "./player.js";
import { initQuests, quests, questsDebug } from "./quests.js";
import { initRig, makeHuman, RIG_HOOKS, RIG_LOAD_ACTIONS, rig, rigPlaced, storyLook } from "./rig.js";
import { rng } from "./rng.js";
import { camera, enterRoom, initRooms, layers, marker, neighbours, onRoom, room, toScreen, toWorld } from "./rooms.js";
import { initSave, saveDebug, saveOnLeave, saves } from "./save.js";
import { initSheet, SHEET_LOAD_CALLS, sheet, sheetDebug } from "./sheet.js";
import { initSearch, search, searchDebug } from "./search.js";
import { initSleep, SLEEP_LOAD_CALLS, sleep, sleepDebug } from "./sleep.js";
import { sound } from "./sound.js";
import { initShots, shots } from "./shots.js";
import { initShop, shop, shopDebug } from "./shop.js";
import { initStorage, storage, storageDebug } from "./storage.js";
import { addRow, newStory, story } from "./story.js";
import { bindHub, initTogether, placePeople, report, togetherDebug } from "./together.js";
import { initTouch, touch, touchDebug } from "./touch.js";
import { initTriggers, triggers, triggersDebug } from "./triggers.js";
import { crosshair, initWeapons, WEAPON_HOOKS, weaponsDebug } from "./weapons.js";
import { START_ROOM, START_TIME, START_X, world } from "./world.js";
import { initZombies, ZOMBIE_HOOKS, ZOMBIE_LOAD_ACTIONS, zombies, zombiesDebug } from "./zombies.js";

// Depth bands on the root: the world draws inside its room's layers (0 to 999), then each kind of overlay
export const DEPTH = {
  world: 0,
  crosshair: 1900,
  hud: 2000,
  panels: 3000,
  dialogs: 4000,
  touch: 5000,
  fades: 6000,
  card: 7000,
};
// Where the hint bar sits within the dialogs' band: over them, under the alert line
const HELP_RAISE = 400;
// Room the black bars keep for the back button and its gap to the screen's edge
const BACK_ROOM = 52;
// The smallest scale the stage is drawn at, so a tiny window never asks for a zero-sized canvas
const LEAST_SCALE = 0.05;
// Steps of the original's clock run in one frame at most, so a stalled tab doesn't replay minutes at once
const MOST_STEPS = 4;
// The pause reason the upright card holds the world with, and the card's words (AlternateGothic2 BT has capitals only)
const UPRIGHT_PAUSE = "upright";
const UPRIGHT_WORDS = "TURN YOUR PHONE SIDEWAYS TO PLAY";
const CARD_SHADE = 0x000000;
const CARD_FILL = 0x1c1c1c;
const CARD_EDGE = 0xb6b0a5;
const CARD_LETTERS = 0xe8e4da;
const CARD_FONT = "AlternateGothic2 BT";
const CARD_SIZE = 40;
const CARD_PADDING = 30;
// Where the card's words are drawn at their sharpest, as the most pixels per stage pixel
const CARD_MOST_RESOLUTION = 3;
const NO_GRAPHICS = "This device couldn't start the game's graphics.";
const NO_ART = "The game's pictures didn't load. Close this window and open the game again.";
const NO_DATA = "The game's data didn't load. Close this window and open the game again.";
// The original's embedded fonts, by the names its text fields use (the cog's web/fonts holds one file per name)
const FONT_FAMILIES = [
  "AlternateGothic2 BT",
  "Arial",
  "Calibri",
  "Courier New",
  "DIN-Black",
  "DIN-Bold",
  "DINChadstone",
  "DIN-Regular",
  "HarleyHand1",
  "Kuenst480 BT",
  "Machine BT",
  "Rockwell Extra Bold",
  "standard 07_56",
  "Tahoma",
  "Times New Roman",
];
export const page = {
  hub: null,
  lib: null,
  app: null,
  // The original's root: attached clips sit in it at their depths
  root: null,
  // Screen pixels per stage pixel
  scale: 1,
  // True while a phone is held upright: the world is paused under the card that asks for it to be turned
  upright: false,
  // True on a phone or tablet: a coarse pointer, or the hub says Discord's mobile app
  touch: matchMedia("(pointer: coarse)").matches,
  // The stage's size in the original's pixels, from flash.json
  width: 760,
  height: 400,
  screen: null,
  screens: {},
  // Time left over from the last step, in milliseconds
  clock: 0,
  // Functions run once per step of the original's clock, after the root's clips have advanced
  steppers: [],
  // A press moved something since the stage was last drawn, so the next display frame draws it even without a step
  drawWanted: false,
};

// The upright card: { holder, words }
let card = null;

// The room functions, for the checks that drive the page
const rooms = { enterRoom, marker, neighbours, onRoom };

// Hook kind -> function(arg, clip, values)
const hooks = new Map();
// Load-handler kind -> function(node, args, cx), for the kinds a later system owns
const loadActions = new Map();
// Button setup name -> function(node, instanceName, ...args)
const loadCalls = new Map();
// Handler kinds and setup names nothing has taken yet, so a check can see what is still unbuilt
const skippedLoads = new Set();

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  $("back").addEventListener("click", saveOnLeave);
  window.addEventListener("error", (e) => {
    // The browser's note that a resize landed while the stage was being fitted is a warning, not a fault
    if (!e.message?.startsWith("ResizeObserver loop")) {
      console.warn("Union City: page error", e.message, e.error);
    }
  });
  window.addEventListener("unhandledrejection", (e) => console.warn("Union City: unhandled rejection", e.reason));
  window.laststand = {
    page, art, data, world, story, input, rng, sound, room, camera, layers, rooms, light, rig, collide, player, hud,
    toScreen, toWorld, crosshair, shots, combat, effects, zombies, drops, director, musicDirector, humans, companions,
    interact, help, inventory, backpack, sheet, journal, achieve, search, locks, storage, notes, shop, sleep, citymap,
    pause, death, quests, npcs, dialog, triggers, cutscenes, ending, menus, create, intro, touch, debug,
  };
  // The tables start downloading beside the stage; the menu waits for them, since its parts run load handlers
  const dataReady = loadData().then(
    () => true,
    (e) => {
      console.error("Union City: couldn't load the game's data", e);
      return false;
    },
  );
  // Not awaited yet: the people button goes into the page the moment the hub answers, before anything else waits, so
  // the hub's floating one never shows
  const hubReady = connect().then(
    (hub) => {
      $("people").append(hub.peopleButton());
      $("people").dataset.placed = "corner";
      page.hub = hub;
      page.touch = page.touch || hub.platform === "mobile";
      bindHub(hub);
      return hub;
    },
    (e) => e,
  );
  page.hubReady = hubReady;
  try {
    await buildStage();
  } catch (e) {
    console.error("Union City: couldn't start drawing", e);
    $("loading").textContent = NO_GRAPHICS;
    return;
  }
  // The menus' art is in before the first one draws; the world's shared art loads behind them, and the world never
  // starts until it is in (coreLoaded)
  try {
    await loadGroup("ui");
  } catch (e) {
    console.error("Union City: couldn't load the menus' art", e);
    $("loading").textContent = NO_ART;
    return;
  }
  if (!(await dataReady)) {
    $("loading").textContent = NO_DATA;
    return;
  }
  await show("menu");
  $("loading").hidden = true;
  coreLoaded().catch((e) => console.warn("Union City: couldn't load the shared art", e));
  const hub = await hubReady;
  if (hub instanceof Error) {
    console.warn("Union City: no connection to ActivityHub", hub);
  }
}

async function buildStage() {
  const data = await (await download("art/flash.json")).json();
  [page.width, page.height] = data.stage;
  const lib = new Library(data, loadPage);
  page.lib = lib;
  // Text is drawn once per change, so the original's fonts have to be ready before the first field
  await Promise.all(
    FONT_FAMILIES.map((family) =>
      document.fonts.load(`14px "${family}"`).catch((e) => console.warn(`Union City: couldn't load ${family}`, e)),
    ),
  );
  const app = new Application();
  await app.init({
    width: page.width,
    height: page.height,
    background: 0x000000,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    preference: "webgl",
    // The art's overlay and hard light blends draw from what is already on the screen
    useBackBuffer: true,
  });
  page.app = app;
  $("stage").appendChild(app.canvas);
  app.stage.eventMode = "static";
  app.stage.hitArea = app.screen;
  lib.trackPointer(app.stage);
  lib.onHook = hook;
  lib.onSound = sound.startTimeline;
  sound.setSounds(data.sounds);
  lib.onPlace = placed;
  for (const def of Object.values(page.screens)) {
    setScripts(def);
  }
  page.root = new Container();
  // Clips sit in the root at the depths the original attached them at
  page.root.sortableChildren = true;
  app.stage.addChild(page.root);
  initArt(page, DEPTH.fades);
  initRooms(page, DEPTH.world);
  initLight(page);
  initEffects(page);
  initRig(page);
  initCollide(page);
  initPlayer(page);
  initWeapons(page, DEPTH.crosshair);
  initShots(page);
  initCombat(page);
  initZombies(page);
  initDrops(page);
  // The room's humans stand before the director counts who is there
  initHumans(page);
  initCompanions(page);
  initDirector(page);
  initHud(page, DEPTH.hud);
  // The hint bar sits over the panels and dialogs, as the original's depth 9000 is over every HUD panel
  initHelp(page, DEPTH.dialogs + HELP_RAISE);
  initInteract(page);
  initInventory();
  initPanels(page, DEPTH.panels);
  initBackpack();
  initSheet();
  initJournal();
  initSearch(page);
  initLocks(page);
  initStorage();
  initNotes();
  initSleep(page);
  initCityMap(page, DEPTH.dialogs);
  initShop(page, DEPTH.dialogs);
  initAchieve(page, DEPTH.dialogs);
  initBoxes(page, DEPTH.dialogs);
  initQuests();
  initNPCs(page);
  initDialog(page);
  initTriggers();
  initCutscenes();
  initPause(page);
  initDeath(page, DEPTH.hud + 2);
  initTouch(page, DEPTH.touch);
  initEnding(page, DEPTH.fades + 100);
  initSave(page);
  initTogether(page);
  initMenus(page, DEPTH.panels);
  initCreate(page, DEPTH.panels, DEPTH.dialogs);
  initIntro(page, DEPTH.panels);
  for (const [kind, fn] of Object.entries({ ...RIG_HOOKS, ...WEAPON_HOOKS, ...ZOMBIE_HOOKS, ...ENDING_HOOKS, ...INTRO_HOOKS })) {
    onHook(kind, fn);
  }
  for (const [kind, fn] of Object.entries({ ...RIG_LOAD_ACTIONS, ...ZOMBIE_LOAD_ACTIONS, ...HUD_LOAD_ACTIONS })) {
    onLoadAction(kind, fn);
  }
  const loadCalls = {
    ...HUD_LOAD_CALLS,
    ...BACKPACK_LOAD_CALLS,
    ...SHEET_LOAD_CALLS,
    ...ACHIEVE_LOAD_CALLS,
    ...SLEEP_LOAD_CALLS,
    ...DEATH_LOAD_CALLS,
    ...MENU_LOAD_CALLS,
  };
  for (const [name, fn] of Object.entries(loadCalls)) {
    onLoadCall(name, fn);
  }
  buildCard();
  page.steppers.push(syncUpright);
  fit();
  input.attach(page);
  new ResizeObserver(fit).observe($("stage"));
  // The stage is drawn by tick, once for each run of steps, in place of every display frame
  app.ticker.remove(app.render, app);
  app.ticker.add((ticker) => tick(ticker.deltaMS));
  for (const kind of ["pointerdown", "pointermove", "pointerup"]) {
    window.addEventListener(kind, wantDraw, { passive: true });
  }
}

// A finger or the mouse moved something on the screen (a stick's knob, a dragged item) between two steps
function wantDraw() {
  page.drawWanted = true;
}

// The original's stage, as big as the room between Discord's buttons allows, with black bars around it. A phone held
// sideways fills the screen's height; one held upright fits the stage to its width, centred. The bars beside it or the
// ones above and below it are kept wide enough for the back button, so it never covers the art
export function fit() {
  const box = $("stage").getBoundingClientRect();
  const beside = Math.min((box.width - BACK_ROOM * 2) / page.width, box.height / page.height);
  const above = Math.min(box.width / page.width, (box.height - BACK_ROOM * 2) / page.height);
  const scale = Math.max(LEAST_SCALE, beside, above);
  const width = Math.round(page.width * scale);
  const height = Math.round(page.height * scale);
  page.scale = scale;
  page.app.renderer.resize(width, height);
  page.app.stage.hitArea = page.app.screen;
  page.root.scale.set(width / page.width, height / page.height);
  page.lib.filterScale = scale;
  // Words drawn from now on match the screen's pixels, and so do the baked pictures of still parts
  setTextResolution(scale * page.app.renderer.resolution);
  rebakeAll();
  if (card) {
    card.words.resolution = Math.min(CARD_MOST_RESOLUTION, scale * page.app.renderer.resolution);
  }
  placePeople();
  syncUpright();
}

// ---------- The upright card ----------

// The card over the world on a phone held upright: a shade over the whole stage and a plate with the words
function buildCard() {
  const holder = new Container();
  holder.label = "uprightCard";
  holder.zIndex = DEPTH.card;
  // The whole stage is the card's, so a press on it never reaches the world or the HUD under it
  holder.eventMode = "static";
  holder.visible = false;
  const shade = new Graphics().rect(0, 0, page.width, page.height).fill({ color: CARD_SHADE, alpha: 0.85 });
  const words = new Text({
    text: UPRIGHT_WORDS,
    style: { fontFamily: CARD_FONT, fontSize: CARD_SIZE, fill: CARD_LETTERS, letterSpacing: 2 },
  });
  words.anchor.set(0.5);
  words.position.set(page.width / 2, page.height / 2);
  const plateWidth = Math.min(page.width - 20, words.width + CARD_PADDING * 2);
  const plateHeight = words.height + CARD_PADDING * 2;
  const plate = new Graphics()
    .roundRect((page.width - plateWidth) / 2, (page.height - plateHeight) / 2, plateWidth, plateHeight, 6)
    .fill({ color: CARD_FILL, alpha: 0.95 })
    .stroke({ width: 2, color: CARD_EDGE });
  holder.addChild(shade, plate, words);
  page.root.addChild(holder);
  card = { holder, words };
  // The dim bar of a paused game would only peek out round the card
  hud.noOverlay.add(UPRIGHT_PAUSE);
}

// A phone or tablet held taller than wide. The window's own size decides, since the hub's frame is as big as the
// screen's room for it
function isUpright() {
  return page.touch && window.innerHeight > window.innerWidth;
}

// Each step: the card shows, and holds the world, while the story is being played upright. Turning sideways takes
// only its own hold off, so a panel or the pause menu that also holds the world still does
function syncUpright() {
  if (!card) {
    return;
  }
  page.upright = isUpright();
  document.body.dataset.upright = page.upright ? "true" : "false";
  const shown = page.upright && world.active;
  card.holder.visible = shown;
  if (shown && !world.reasons.has(UPRIGHT_PAUSE)) {
    world.pause(UPRIGHT_PAUSE);
  } else if (!shown && world.reasons.has(UPRIGHT_PAUSE)) {
    world.resume(UPRIGHT_PAUSE);
  }
}

// The original runs at the clip frame rate: the clock collects real time and every whole frame runs one step
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
    page.screens[page.screen]?.step?.(page);
    for (const fn of page.steppers) {
      fn();
    }
    world.step();
  }
  // Nothing on the stage changes between steps but what a press moves, so a display faster than the original's frame
  // rate draws each step once, as the Flash player did
  if (steps > 0 || page.drawWanted) {
    page.drawWanted = false;
    bakeQueued(page.app.renderer, page.app.stage);
    page.app.render();
  }
}

// ---------- The original's root ----------

// Flash's attachMovie on the root: a new copy of an exported clip at one of the original's depths, named so the screens
// can reach it. A clip already attached by that name goes first, as attaching over a name replaces it
export function attach(exportName, depth, name) {
  detach(name);
  const clip = page.lib.makeExported(exportName);
  clip.label = name;
  clip.zIndex = depth;
  page.root.addChild(clip);
  return clip;
}

// Flash's removeMovieClip on a clip attached to the root
export function detach(name) {
  for (const old of [...page.root.children]) {
    if (old.label === name) {
      old.destroy({ children: true });
    }
  }
}

page.attach = attach;
page.detach = detach;
page.show = show;

// ---------- Script hooks ----------

// Registers the part of the original's script hooks that one system owns
export function onHook(kind, fn) {
  hooks.set(kind, fn);
}

// The values after a hook's first one: from the whole action when flash.js hands it over, otherwise read from the first
// matching action on the clip's current frame
export function hookValues(kind, arg, clip, action = null) {
  const found = action ?? clip.def.s?.[clip.frame]?.find((each) => each[0] === kind && each[1] === arg);
  return found ? found.slice(2) : [];
}

// The one lib.onHook. Returns true when a registered system did what the hook asks
export function hook(kind, arg, clip, action) {
  const fn = hooks.get(kind);
  return fn ? Boolean(fn(arg, clip, hookValues(kind, arg, clip, action))) : false;
}

// ---------- Load handlers ----------

// The original's onClipEvent(load) handlers outside the rooms were normalized into data.loadscripts, keyed
// "<parent sprite>:<depth>" (and "@<frame it was placed on>" off the first frame), each one action. The rooms' own are
// applied by the rooms. Actions that belong to one system (a button's setup, a zombie's hat) wait in a registry for it.

// Registers a button setup a handler calls by name: fn(node, instanceName, ...args)
export function onLoadCall(name, fn) {
  loadCalls.set(name, fn);
}

// Registers a handler kind this file does not do itself (hatPick, headMask ...): fn(node, args, cx)
export function onLoadAction(kind, fn) {
  loadActions.set(kind, fn);
}

// Flash's random(n) for pictures that only need to look different
function roll(n) {
  return Math.floor(page.lib.random() * n);
}

function degrees(value) {
  return (value * Math.PI) / 180;
}

// A script's _alpha holds when the timeline later moves the placement
function setAlpha(node, alpha) {
  node.scriptAlpha = alpha;
  node.alpha = alpha;
}

// What a handler that calls gotoAndStop on its own clip does: a frame by label or number, only on a clip
function stopAt(node, frame) {
  node.gotoAndStop?.(frame);
}

// The handler kinds this file does itself: function(node, args, cx)
const LOAD = {
  none() {},
  hide(node) {
    node.visible = false;
  },
  alpha0(node) {
    setAlpha(node, 0);
  },
  goto(node, [label]) {
    stopAt(node, label);
  },
  // A random frame from 1 to the count
  gotoRandom(node, [count]) {
    stopAt(node, 1 + roll(count === "total" ? node.totalFrames : count));
  },
  // A random frame from 1 to the count - 1, then playing (frame 0 is frame 1)
  gotoPlayRandom(node, [count]) {
    node.gotoAndPlay?.(Math.max(1, roll(count)));
  },
  rotateRandom(node, [turn, frames]) {
    node.rotation = degrees(roll(turn));
    stopAt(node, 1 + roll(frames));
  },
  scaleRandom(node, [base, range, same, turn]) {
    const across = (base + roll(range)) / 100;
    node.scale.set(across, same ? across : (base + roll(range)) / 100);
    if (turn) {
      node.rotation = degrees(roll(turn));
    }
  },
  // A solid random colour over the picture, at once (colorTo with no time), keeping the placement's own alpha
  tintRandom(node, args, cx) {
    const colour = Math.round(page.lib.random() * 0xffffff);
    node.scriptColor = {
      mult: [0, 0, 0, cx?.mult?.[3] ?? 256],
      add: [colour >> 16, (colour >> 8) & 255, colour & 255, cx?.add?.[3] ?? 0],
    };
    applyColor(node, cx);
  },
  hideChance(node, [odds]) {
    if (roll(odds) === 0) {
      node.visible = false;
    }
  },
  // A press handler that does nothing, so the press stops here
  swallow(node) {
    if (node.setHandler) {
      node.useHandCursor = false;
      node.setHandler("onPress", () => {});
    }
  },
  releaseParentGoto(node, [label]) {
    node.setHandler?.("onRelease", () => node.parentClip?.gotoAndStop(label));
  },
  childAlpha(node, [name, percent]) {
    const child = node.named?.[name];
    if (child) {
      setAlpha(child, percent / 100);
    }
  },
  // Several actions of one handler, in order
  all(node, actions, cx) {
    for (const action of actions) {
      runLoad(node, action, cx);
    }
  },
  call(node, [name, ...rest]) {
    const fn = loadCalls.get(name);
    if (fn) {
      fn(node, node.label, ...rest);
    } else {
      skippedLoads.add(name);
    }
  },
};

function runLoad(node, [kind, ...args], cx) {
  if (Object.hasOwn(LOAD, kind)) {
    LOAD[kind](node, args, cx);
  } else if (loadActions.has(kind)) {
    loadActions.get(kind)(node, args, cx);
  } else {
    skippedLoads.add(kind);
  }
}

// lib.onPlace: a timeline made a new part. A rig's skin or hair part takes its colour, then the part's load handler
// runs, if the art has one
function placed(node, parent, depth, frame, cx) {
  rigPlaced(node);
  const key = frame === 1 ? `${parent.charId}:${depth}` : `${parent.charId}:${depth}@${frame}`;
  const action = data.loadscripts?.[key];
  if (!action) {
    return;
  }
  try {
    runLoad(node, action, cx);
  } catch (e) {
    console.warn(`Union City: the load handler for ${key} failed`, e);
  }
}

// ---------- The debug handle ----------

// Game minutes into the day from "13:30", "1330" or 1330
function minutesOfDay(text) {
  const [hours, minutes] = String(text).includes(":")
    ? String(text).split(":").map(Number)
    : [Math.floor(Number(text) / 100), Number(text) % 100];
  return hours * 60 + minutes;
}

function twoDigits(n) {
  return String(n).padStart(2, "0");
}

// Helpers for the checks that drive the page (page.py's js command). Each task adds the ones its own check needs
export const debug = {
  // The original's default character on a fresh clock, with the world running. options as newStory takes them. A
  // check plays from whatever screen is showing, so that screen reads the keyboard
  newStory(options) {
    rng.seed();
    input.clear();
    world.reset();
    input.own(page.screen);
    light.reset();
    newStory({ touch: page.touch, ...options });
    world.time = START_TIME;
    world.start();
    world.enter?.(START_ROOM, START_X);
    return debug.state();
  },

  // Moves to a room, arriving at a marker's name, "start", "end" or an x. Returns the promise of the room change
  goto(roomId, arrival) {
    return world.enter(roomId, arrival);
  },

  // Walks a stand-in for the player along the floor to x at speed pixels a step, so the camera follows it. Resolves
  // when it gets there
  walk(x, speed = 7.5) {
    world.player ??= { x: room.arrivalX };
    return new Promise((resolve) => {
      const stop = world.stage("controls", () => {
        const left = x - world.player.x;
        world.player.x += Math.sign(left) * Math.min(Math.abs(left), speed);
        if (world.player.x === x) {
          stop();
          resolve(x);
        }
      });
    });
  },

  // Whether the page counts as upright, whether the card shows, and what holds the world
  uprightState() {
    return {
      upright: page.upright,
      card: Boolean(card?.holder.visible),
      scale: page.scale,
      active: world.active,
      paused: world.paused,
      reasons: [...world.reasons],
      time: world.time,
    };
  },

  // The save points asked for so far
  saves,

  // Humans a check stood in the room, newest last
  humans: [],

  // Stands a dressed human in the room at x (the room's arrival place by default), facing 1 (right) or -1 (left).
  // options as makeHuman takes them; with none, the story's player as the original dresses them. Returns the rig
  human(options = {}) {
    const made = makeHuman({ ...(story.player ? storyLook() : {}), ...options });
    made.clip.x = options.x ?? room.arrivalX;
    made.clip.y = room.floorY;
    made.setFacing(options.facing ?? 1);
    layers.actors.addChild(made.clip);
    debug.humans = debug.humans.filter((each) => !each.clip.destroyed);
    debug.humans.push(made);
    return made;
  },

  // n of an item in the backpack; cash and ammo add to their counts
  give(ref, n = 1) {
    if (ref === "cash") {
      story.player.cash += n;
    } else if (ref in story.ammo) {
      story.ammo[ref] += n;
    } else {
      for (let i = 0; i < n; i += 1) {
        addRow(ref);
      }
    }
    return story.inventory.length;
  },

  // Points the flashlight's beam from (x, y) in the room along an angle, in degrees clockwise from straight right
  beam(x, y, aim) {
    light.placeBeam(x, y, aim);
  },

  // Sets the time of day, keeping the day: "13:30", "1330" or 1330
  time(text) {
    world.time = world.day * 1440 + minutesOfDay(text);
    world.sub = 0;
    return debug.state().clock;
  },

  // Takes n steps by hand, as if the world were unpaused
  step(n = 1) {
    for (let i = 0; i < n; i += 1) {
      world.step(true);
    }
    return world.frame;
  },

  state() {
    const player = story.player;
    return {
      screen: page.screen,
      active: world.active,
      paused: world.paused,
      reasons: [...world.reasons],
      frame: world.frame,
      time: world.time,
      day: world.day,
      clock: `${twoDigits(world.hour)}:${twoDigits(world.minute)}`,
      timers: world.pendingTimers,
      room: room.id,
      camera: camera.x,
      stage: { x: layers.bg.parent.x, y: layers.bg.parent.y },
      story: player && {
        name: player.name,
        level: player.level,
        mode: story.mode,
        cash: player.cash,
        backpack: story.inventory.length,
        stash: story.storage.length,
        worn: player.clothes,
      },
      skippedLoads: [...skippedLoads],
      missingCalls: [...rig.missingCalls],
    };
  },
};

// The player's helpers: stats, facing and the movement state
Object.assign(
  debug,
  playerDebug,
  weaponsDebug,
  combatDebug,
  zombiesDebug,
  dropsDebug,
  directorDebug,
  humansDebug,
  companionsDebug,
  interactDebug,
  hudDebug,
  helpDebug,
  inventoryDebug,
  panelsDebug,
  backpackDebug,
  sheetDebug,
  journalDebug,
  searchDebug,
  locksDebug,
  storageDebug,
  notesDebug,
  sleepDebug,
  citymapDebug,
  shopDebug,
  boxesDebug,
  achieveDebug,
  pauseDebug,
  deathDebug,
  questsDebug,
  npcsDebug,
  dialogDebug,
  triggersDebug,
  cutscenesDebug,
  endingDebug,
  introDebug,
  saveDebug,
  menusDebug,
  createDebug,
  touchDebug,
  togetherDebug,
);

// ---------- Screens ----------

export function registerScreen(name, def) {
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

// Switches to a screen: the one showing leaves (told which screen comes next), the new one enters with the options the
// caller gives it
export async function show(name, options) {
  const next = page.screens[name];
  if (!next) {
    console.warn(`Union City: no screen called ${name}`);
    return;
  }
  // The new screen's buttons (or the world) take the old one's place under the pointer, so the second click of a double
  // click on the button that asked for it presses nothing
  input.shutByClick();
  page.screens[page.screen]?.leave?.(page, name);
  page.screen = name;
  document.body.dataset.screen = name;
  touch.show(name === "world");
  placePeople();
  report(name);
  try {
    await next.enter(page, options);
  } catch (e) {
    console.error(`Union City: couldn't show ${name}`, e);
  }
}

// The menu screens (menus.js) and the world, which has nothing of its own to draw: its parts come from the systems that
// run it
for (const [name, def] of Object.entries(MENU_SCREENS)) {
  registerScreen(name, def);
}
registerScreen("create", CREATE_SCREEN);
registerScreen("intro", INTRO_SCREEN);
registerScreen("world", { enter() {} });

start();
