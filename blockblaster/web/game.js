// Block Blaster's page: the live connection, the screens, and the debug handle other checks read.
// The bot keeps every player's progress and decides every result; this page draws the level and sends the taps.
import { backToMenu, connect } from "activityhub";
import * as hud from "./hud.js";
import { loadLevel } from "./levels.js";
import { initMap, onPlay, onWatch, setWaiting, showFaces, showPath } from "./map.js";
import * as panels from "./panels.js";
import * as play from "./play.js";
import { createScene } from "./scene.js";
import * as sound from "./sound.js";
import { newState } from "./sim/core.js";
import { expand } from "./sim/level.js";
import * as watch from "./watch.js";
import * as people from "./whoshere.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open Block Blaster again.",
  1011: "Couldn't join the game.",
  4003: "Block Blaster was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
  4100: "Block Blaster was opened somewhere else.",
};
const CLOSED_OTHERWISE = "The game ended. Go back to the menu and open it again.";
const OFFLINE_NOTE = "Open Block Blaster in Discord to play.";
const SCENE_FAILED = "This device couldn't start the 3D view. Go back to the menu and open Block Blaster again.";
const LEVEL_FAILED = "Couldn't open that level. Try again.";
// The splash between a won level and the next one (the original's 1 to 2 seconds)
const NEXT_SPLASH_MS = 1500;
const NOT_PLAYING = "That friend isn't playing a level right now.";
const TOAST_MS = 3000;

const SCREENS = ["splash", "path", "level", "watch"];

// screen is one of SCREENS. progress and sim stay empty until the bot sends a player's progress and a level starts;
// scene is the 3D scene (scene.js) once its models have loaded
const page = {
  hub: null,
  conn: null,
  screen: "splash",
  progress: null,
  sim: null,
  scene: null,
  board: null,
  toastTimer: null,
  nextTimer: null,
  // The player's own level number while they watch a friend, so "Back to my game" resumes it, or null
  ownLevel: null,
};

// What other checks read: the page, the drawn scene and the sounds played (sound.played)
window.blockblaster = { page, scene: null, sound };

function $(id) {
  return document.getElementById(id);
}

function showScreen(name) {
  if (!SCREENS.includes(name)) {
    throw new Error(`Block Blaster has no screen called ${name}`);
  }
  if (name !== "watch" && watch.watching()) {
    watch.stop();
  }
  page.screen = name;
  $("play").dataset.screen = name;
  $("watch-back").hidden = name !== "watch";
  $("splash").hidden = name !== "splash";
  $("path").hidden = name !== "path";
  if (name !== "level") {
    hud.hideHud();
    panels.hidePanels();
  }
  showCoins();
  people.screenShown(name, name === "watch" && watch.friend() ? watch.shortName(watch.friend().name) : null);
}

// The coin pill sits in the top bar on every screen after the loading one, once the bot has said how many there are
function showCoins() {
  const known = page.progress !== null && page.screen !== "splash";
  $("coins").hidden = !known;
  if (known) {
    $("coins-count").textContent = page.progress.coins.toLocaleString("en-US");
  }
}

function setStatus(text) {
  $("splash-status").textContent = text;
}

function send(data) {
  return page.conn ? page.conn.send(data) : false;
}

function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(() => {
    node.hidden = true;
  }, TOAST_MS);
}

function setProgress(progress) {
  page.progress = progress;
  showCoins();
  if (page.screen === "level") {
    hud.setBoosters(progress, page.sim);
  }
}

// The bot's verdict on the level: its panel opens after a short pause (panels.js)
function over(result) {
  setProgress(result.progress);
  if (result.result === "won") {
    panels.showWin(result);
  } else {
    panels.showFail(result);
  }
}

// The win panel's Continue: a short splash, then the player's next level. After level 2,600 the path comes back
function nextLevel() {
  if (page.progress.cleared) {
    openPath();
    return;
  }
  play.stopLevel();
  showScreen("splash");
  setStatus("Loading");
  clearTimeout(page.nextTimer);
  page.nextTimer = setTimeout(() => {
    if (page.screen === "splash" && send({ start: page.progress.level }) === false) {
      openPath();
    }
  }, NEXT_SPLASH_MS);
}

// The fail panel's Retry: the bot opens the level afresh, and its arrival closes the panel
function retryLevel(n) {
  if (send({ start: n }) === false) {
    return false;
  }
  play.stopLevel();
  return true;
}

// The fail panel's Revive: the bot charges the coins and applies the revive at the tick the level stopped at, then the
// page applies the same tap there. False when the page had to ask the bot for its copy instead
async function reviveLevel() {
  const result = await page.hub.api("revive");
  setProgress(result.progress);
  return play.revived(result.tick, result.sum);
}

// The unlock popup's CLAIM: the bot gives the free booster. Rejects with the bot's words when it won't
async function claimBooster(booster) {
  const result = await page.hub.api("claim", { booster });
  setProgress(result.progress);
}

// The shop's purchase: the bot takes the payment and adds the pack. Rejects with the bot's words when it won't
async function buyBooster(booster, pay) {
  const result = await page.hub.api("buy", { booster, pay });
  setProgress(result.progress);
}

// The bot remembers a popup or tutorial was shown, so it never shows again
async function markSeen(id) {
  try {
    setProgress((await page.hub.api("shown", { id })).progress);
  } catch (e) {
    console.warn("Block Blaster: the bot couldn't note a popup as shown", e);
  }
}

function levelArrived(levelStart) {
  setWaiting(false);
  panels.hidePanels();
  if (play.playing()) {
    play.rebuild(levelStart);
    return;
  }
  play.startLevel(levelStart).catch((e) => {
    console.warn("Block Blaster: couldn't start the level", e);
    toast(LEVEL_FAILED);
  });
}

// The bot greets every page that connects, and again after the hub reconnects a dropped link. A level in play then
// follows the bot's copy, which never saw taps sent while the link was down
function hello(greeting) {
  setProgress(greeting.progress);
  // A new link starts on the player's own game on the bot, so watching is asked for again
  if (watch.watching()) {
    watchFriend(watch.friend().id);
  }
  if (!play.playing()) {
    return;
  }
  if (greeting.level) {
    play.resume(greeting.level);
  } else {
    stopped("The level was lost while the connection was down.");
  }
}

function stopped(text) {
  toast(text);
  if (page.screen === "level") {
    openPath();
  }
}

// ---------- Watching a friend ----------

// Ask the bot to watch a friend's level (`id` their user id). The player's own level stays on the bot meanwhile
function watchFriend(id) {
  return send({ watch: String(id) }) !== false;
}

// The bot's yes: the player's own level is left (the bot keeps it) and the friend's goes on screen
function watchingArrived(watching) {
  if (!watch.watching()) {
    const own = page.sim;
    page.ownLevel = play.playing() && own.over === null ? own.level.number : null;
  }
  play.stopLevel();
  watch.begin(watching).catch((e) => {
    console.warn("Block Blaster: couldn't open the friend's level", e);
    toast(LEVEL_FAILED);
    backToGame();
  });
}

// "Back to my game": the level the player left resumes, or the path comes back
function backToGame() {
  watch.stop();
  send({ unwatch: true });
  const own = page.ownLevel;
  page.ownLevel = null;
  if (own === null) {
    openPath();
    return;
  }
  showScreen("splash");
  setStatus("Loading");
  if (send({ start: own }) === false) {
    openPath();
  }
}

// The friend left or stopped playing, or the bot said no to watching them
function friendGone() {
  const friend = watch.friend();
  if (!friend) {
    toast(NOT_PLAYING);
    return;
  }
  backToGame();
  toast(`${friend.name} stopped playing.`);
}

// The friend's level messages, or false for any other message
function watchMessage(data) {
  if ("watching" in data) {
    watchingArrived(data.watching);
  } else if ("ftap" in data) {
    watch.friendTap(data.ftap);
  } else if ("fat" in data) {
    watch.friendAt(data.fat);
  } else if ("fover" in data) {
    watch.friendOver(data.fover);
  } else if ("flevel" in data) {
    watch.newLevel(data.flevel);
  } else if ("fgone" in data) {
    friendGone();
  } else {
    return false;
  }
  return true;
}

// While watching, the player's own level is off screen: late answers about it are dropped, and its result only
// updates the coins
function ownLevelMessage(data) {
  if ("ok" in data || "refused" in data || "level" in data) {
    return true;
  }
  if ("over" in data) {
    setProgress(data.over.progress);
    return true;
  }
  return false;
}

// Every message from the bot lands here
function receive(data) {
  if (watchMessage(data) || (page.screen === "watch" && ownLevelMessage(data))) {
    return;
  }
  if ("ok" in data) {
    play.answered(data.ok, data.sum);
  } else if ("refused" in data) {
    play.refused(data.refused, data.level);
  } else if ("level" in data) {
    levelArrived(data.level);
  } else if ("over" in data) {
    over(data.over);
  } else if ("progress" in data) {
    setProgress(data.progress);
  } else if ("hello" in data) {
    hello(data.hello);
  } else if ("stopped" in data) {
    stopped(data.stopped);
  } else if ("elsewhere" in data) {
    toast(data.elsewhere);
  } else {
    console.warn("Block Blaster: a message nothing handles yet", data);
  }
}

// The level path, over a faint still picture of the level Play would start. The splash stays up while that level's
// pack loads. A backdrop that fails to load never stops the path: the sky shows alone
async function openPath() {
  clearTimeout(page.nextTimer);
  play.stopLevel();
  setWaiting(false);
  let backdrop = null;
  try {
    backdrop = newState(expand(await loadLevel(page.progress.level)), 1, page.board);
  } catch (e) {
    console.warn("Block Blaster: couldn't load the path's backdrop", e);
  }
  showScreen("path");
  showPath(page.progress);
  if (backdrop) {
    page.scene.showLevel(backdrop);
    page.scene.render();
  }
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    setStatus(CLOSED_BECAUSE[e.status] || e.message);
    return;
  }
  page.conn.on(receive);
  page.conn.onClose((code) => {
    people.disconnected();
    play.stopLevel();
    watch.stop();
    showScreen("splash");
    setStatus(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE);
  });
}

async function openScene() {
  const response = await fetch("board.json");
  if (!response.ok) {
    throw new Error(`board.json came back ${response.status}`);
  }
  page.board = await response.json();
  page.scene = await createScene($("scene"), page.board);
  window.blockblaster.scene = page.scene;
  page.scene.onLayout(people.placeStrip);
  page.scene.layout.floor = hud.floorY;
  hud.onFloor(() => page.scene.pigs.relimit());
  page.scene.onLayout(hud.measureFloor);
}

// Dev check: draw level n's board with no game running
async function view(n) {
  play.stopLevel();
  const level = expand(await loadLevel(n));
  showScreen("level");
  const state = newState(level, 1, page.board);
  page.scene.showLevel(state);
  hud.showHud(level, page.progress);
  hud.frame(state);
  page.scene.render();
  return { level: n, width: level.width, height: level.height, calls: page.scene.renderer.info.render.calls };
}

async function start() {
  $("back").addEventListener("click", () => backToMenu());
  $("watch-back").addEventListener("click", () => {
    sound.play("button");
    backToGame();
  });
  showScreen("splash");
  try {
    page.hub = await connect();
  } catch (e) {
    setStatus(e.message);
    return;
  }
  // Right after connect(), so the hub's floating button never shows over the coins
  $("people-slot").append(page.hub.peopleButton());
  page.hub.onPeople(() => people.refresh());
  try {
    await openScene();
  } catch (e) {
    console.warn("Block Blaster: couldn't start the 3D scene", e);
    setStatus(SCENE_FAILED);
    return;
  }
  if (page.hub.offline) {
    setStatus(OFFLINE_NOTE);
    return;
  }
  try {
    page.progress = await page.hub.api("profile");
  } catch (e) {
    console.warn("Block Blaster: couldn't read the player's progress", e);
    setStatus(e.message);
    return;
  }
  // Which boosters the server sells for credits, and whether this player may change that
  panels.loadCredits();
  panels.loadShopSettings();
  await goLive();
  if (page.conn) {
    await openPath();
  }
}

// The settings dialog's restart: throw the held level away and open it afresh. True when the bot was asked
function restartLevel() {
  if (!page.sim) {
    return false;
  }
  return send({ restart: page.sim.level.number }) !== false;
}

page.view = view;
page.openPath = openPath;
onPlay((n) => {
  if (send({ start: n }) !== false) {
    setWaiting(true);
  }
});
initMap();
onWatch((id) => watchFriend(id));
people.initWhoshere(page, { watch: watchFriend, faces: showFaces });
play.initPlay(page, send, { show: showScreen });
watch.initWatch(page, { show: showScreen });
hud.initHud(page, {
  tap: play.tap,
  hold: play.hold,
  release: play.release,
  restart: restartLevel,
  backToMenu: () => backToMenu(),
  note: toast,
});
panels.initPanels(page, {
  revive: reviveLevel,
  retry: retryLevel,
  next: nextLevel,
  leave: () => openPath(),
  claim: claimBooster,
  buy: buyBooster,
  credits: () => page.hub.api("credits"),
  shopSettings: () => page.hub.api("shop_settings"),
  saveShop: (settings) => page.hub.api("save_shop", { settings }),
  seen: markSeen,
  tap: play.tap,
  hold: play.hold,
  release: play.release,
});
sound.initSound();
sound.setEffects(hud.soundOn());
sound.setMusic(hud.musicOn());
hud.onSwitch((name, on) => (name === "sound" ? sound.setEffects(on) : sound.setMusic(on)));
play.onLevelShown(panels.levelOpened);
play.onLevelShown((sim, levelStart) => people.levelShown(levelStart));
play.onTapSent(people.tapSent);
play.onEvents((events, sim) => {
  panels.watch(sim);
  people.frame(sim);
});
Object.assign(window.blockblaster, {
  showScreen,
  send,
  loadLevel,
  toast,
  play,
  hud,
  panels,
  watch,
  whoshere: people,
  watchFriend,
  backToGame,
});
start().catch((e) => {
  console.error("Block Blaster: couldn't start", e);
  setStatus("Something went wrong. Go back to the menu and open Block Blaster again.");
});
