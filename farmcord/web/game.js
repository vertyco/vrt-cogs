// FarmCord's page: opening the farm, keeping its state, moving between rooms, and sending the player's actions.
// The bot keeps the clock and the rules. This page walks the farmer, draws what the bot says, and asks again when a
// moment it shows has passed.
import { backToMenu, connect, HubError } from "activityhub";
import { extraRoomView, houseView, yardView } from "./house.js";
import * as hud from "./hud.js";
import { marketView } from "./market.js";
import { plotView, pondView } from "./plots.js";
import { DIRECTIONS, ROOMS, START_ROOM } from "./rooms.js";
import { createScene } from "./scene.js";
import { Sound } from "./sound.js";

// The sound an accepted action makes. Others make none, or pass their own to act()
const ACTION_SOUNDS = {
  till: "hoe",
  plant: "plant",
  water: "water",
  water_animal: "water",
  refill: "refill",
  harvest: "harvest",
  feed: "feed",
  buy_seeds: "buy",
  buy_feed: "buy",
  buy_animal: "buy",
  buy_tool: "buy",
  buy_storage: "buy",
  buy_room: "buy",
  buy_cosmetic: "buy",
  unlock_plot: "buy",
  switch_plot: "buy",
  free_packet: "buy",
  sell_crops: "sell",
  sell_animal: "sell",
  convert: "sell",
  discard: "clear",
  place: "plant",
  pick_up: "tap",
  wear: "tap",
  describe: "tap",
};
// The sound news makes when an action brings it
const NEWS_SOUNDS = { level: "levelup", achievement: "achievement", born: "birth" };
// A refresh waits this long past its moment, so the bot's clock has passed it too
const REFRESH_LATE_MS = 1000;
// Longer waits wake early and wait again, since browsers can't wait more than about 24 days at once
const LONGEST_WAIT_MS = 6 * 3600 * 1000;
// After a request for the farm fails, the page asks again this much later
const RETRY_MS = 30 * 1000;
// What the player sees when something fails on the page's side rather than the bot turning an action down
const PAGE_BUG = "Something went wrong. If it keeps happening, close FarmCord and open it again.";
// What each kind of room adds to the farm, by room kind. A view has any of enter(ctx, room), update(ctx, room) (a new
// state arrived), leave(ctx, room) and tapGround(ctx, room, point) (a tap on nothing, once the farmer got there).
// Exported so the browser tests can put in a view of their own
export const VIEWS = {
  farmhouse: houseView,
  room: extraRoomView,
  yard: yardView,
  plot: plotView,
  pond: pondView,
  market: marketView,
};

const sound = new Sound();
const page = {
  hub: null,
  scene: null,
  state: null,
  // performance.now() when the state arrived, to tell the bot's time from the page's
  stateAt: 0,
  catalog: null,
  // The rest of the open reply: { credit, creditUrl, canSetPayouts }
  info: null,
  room: START_ROOM,
  // Keys of the requests in flight, and the chain that sends them one after another
  busy: new Set(),
  queue: Promise.resolve(),
  refreshAt: null,
  refreshTimer: null,
};

// What room views get to work with
const ctx = {
  state: () => page.state,
  catalog: () => page.catalog,
  info: () => page.info,
  hub: () => page.hub,
  now,
  act,
  actButton,
  busy: (key) => page.busy.has(key),
  refresh,
  room: () => ROOMS[page.room],
  goTo: (id) => enterRoom(id, null),
  safe,
  tool: hud.tool,
  hud,
  sound,
  scene: null,
};

function $(id) {
  return document.getElementById(id);
}

// Wraps a view's function so a mistake in it, thrown or in a promise it returns, goes to the console and a plain toast
// while the rest of the page carries on. Views wrap their own tap and button handlers in it
function safe(where, fn) {
  return (...args) => {
    const failed = (e) => pageBug(where, e);
    try {
      Promise.resolve(fn(...args)).catch(failed);
    } catch (e) {
      failed(e);
    }
  };
}

// Runs one of a room view's hooks. A mistake in a view doesn't stop the rest of the update: the state, the refresh
// timer, the sounds and news
function callView(room, hook, ...args) {
  const run = VIEWS[room.kind]?.[hook];
  if (run) {
    safe(`the ${room.kind} room's ${hook}()`, run)(ctx, room, ...args);
  }
}

function pageBug(where, e) {
  console.error(`FarmCord: ${where} failed`, e);
  hud.toast(PAGE_BUG, "error");
}

// What the notice says when the page can't get going: the bot's own words when it turned a request down, else the
// plain words for a failure on this side, whose details go to the console
function failure(where, e) {
  if (e instanceof HubError) {
    return e.message;
  }
  console.error(`FarmCord: ${where} failed`, e);
  return PAGE_BUG;
}

// The bot's time now: its moment for the last state, plus the time that passed on this page since
function now() {
  return page.state ? page.state.now + (performance.now() - page.stateAt) / 1000 : Date.now() / 1000;
}

// ---------- Starting ----------

async function start() {
  hud.setup({ back: () => backToMenu(), exit: go, sound: switchSound, music: switchMusic, tool: () => sound.play("tap") });
  hud.showSwitches(sound.sfxOn, sound.musicOn);
  hud.showPlay(false);
  hud.showNotice("Loading the farm...");
  try {
    page.scene = await createScene($("stage"));
  } catch (e) {
    console.error("FarmCord: couldn't start drawing", e);
    hud.showNotice("This device couldn't start the game's graphics.");
    return;
  }
  ctx.scene = page.scene;
  hud.setArt(page.scene.art);
  page.scene.onGround = (point) => {
    const room = ROOMS[page.room];
    callView(room, "tapGround", point);
  };
  page.scene.farmer.onStep = () => sound.play("step");
  watchLayout();
  enterRoom(START_ROOM, null);
  bindKeys();
  try {
    page.hub = await connect();
  } catch (e) {
    hud.showNotice(failure("connecting to ActivityHub", e));
    return;
  }
  // ActivityHub's "who's here" button goes in the HUD, or the hub floats it over the corner the switches are in
  if (page.hub.peopleButton) {
    $("people").append(page.hub.peopleButton());
  }
  if (page.hub.offline) {
    hud.showNotice("Open FarmCord from Discord to play.");
    return;
  }
  await open();
}

// Opens the farm. When that fails, the notice says why and offers to try again
async function open() {
  hud.showNotice("Loading the farm...");
  let reply;
  try {
    reply = await page.hub.api("open");
  } catch (e) {
    hud.showNotice(failure("opening the farm", e), safe("opening the farm", open));
    return;
  }
  page.catalog = reply.catalog;
  page.info = { credit: reply.credit, creditUrl: reply.credit_url, canSetPayouts: reply.can_set_payouts };
  // The switches saved with the farm win over the ones this browser remembers
  sound.setSfx(reply.state.prefs.sound);
  sound.setMusic(reply.state.prefs.music);
  hud.showSwitches(sound.sfxOn, sound.musicOn);
  hud.showNotice("");
  hud.showPlay(true);
  applyState(reply.state);
  hud.showAway(reply.events, page.catalog, reply.state.now);
}

// The HUD and the tool bar float over the farm; the scene fits the room between them, and the exit buttons sit
// between them too
function watchLayout() {
  const measure = () => {
    const top = $("hud").getBoundingClientRect().bottom;
    const tools = $("tools");
    const bottom = tools.hidden ? 0 : window.innerHeight - tools.getBoundingClientRect().top;
    page.scene.setInsets(top, bottom);
    $("app").style.setProperty("--hud-bottom", `${top}px`);
    $("app").style.setProperty("--bar-height", `${bottom}px`);
  };
  const observer = new ResizeObserver(measure);
  observer.observe($("hud"));
  observer.observe($("tools"));
  window.addEventListener("resize", measure);
  measure();
}

// ---------- The farm's state ----------

function applyState(state) {
  const before = page.state;
  page.state = state;
  page.stateAt = performance.now();
  hud.render(state, page.catalog);
  page.scene.farmer.dress(state.outfit);
  const room = ROOMS[page.room];
  // A farmhouse room bought, or the first state, shows its door
  if (!before || before.rooms !== state.rooms) {
    hud.showRoom(room, opens);
  }
  const skyChanged = before && (before.season.name !== state.season.name || before.weather.name !== state.weather.name);
  if (!before || skyChanged) {
    redraw();
  } else {
    callView(room, "update");
  }
  hearRain();
  scheduleRefresh();
}

// The moments in the state when what the page shows changes: a crop's next stage or spoil mark, an animal growing
// up, going hungry or thirsty, or having babies, the next day's weather and the next season
function moments(state) {
  const list = [state.season.ends_at, state.weather.ends_at];
  for (const plot of state.plots) {
    for (const spot of plot.spots) {
      list.push(spot.stage_ends_at, spot.spoil_ends_at);
    }
  }
  for (const animal of state.animals) {
    list.push(animal.grows_up_at, animal.feed_by, animal.water_by, animal.expecting_until);
  }
  return list.filter((moment) => moment !== null && moment > state.now);
}

function scheduleRefresh() {
  clearTimeout(page.refreshTimer);
  const next = Math.min(...moments(page.state));
  page.refreshAt = Number.isFinite(next) ? next : null;
  if (page.refreshAt !== null) {
    waitForRefresh();
  }
}

function waitForRefresh() {
  const wait = (page.refreshAt - now()) * 1000 + REFRESH_LATE_MS;
  const due = wait <= LONGEST_WAIT_MS;
  page.refreshTimer = setTimeout(due ? refresh : waitForRefresh, Math.max(0, Math.min(wait, LONGEST_WAIT_MS)));
}

// Asks the bot for the farm again. A request that fails is asked again a little later, or the page would stop following
// the farm's moments. A new state replaces that wait with the next moment's
async function refresh() {
  const reply = await act("state", {}, { sound: null });
  // With the key still busy, this one was skipped for a refresh already on its way
  if (!reply && !page.busy.has("state")) {
    clearTimeout(page.refreshTimer);
    page.refreshTimer = setTimeout(refresh, RETRY_MS);
  }
  return reply;
}

// ---------- Actions ----------

// Sends an action to the bot. While a request with the same key (by default the action's name) is in flight, another
// is ignored and this returns null, so a double tap never spends twice; key: null sends regardless. Requests go one
// after another, so their replies arrive in order. An accepted action redraws the farm, plays its sound (sound: a
// name, or null for none) and shows its news; a refused one shows the bot's reason. Resolves with the reply, or null
async function act(name, data = {}, { key = name, sound: effect = ACTION_SOUNDS[name] } = {}) {
  if (!page.hub || page.hub.offline || (key !== null && page.busy.has(key))) {
    return null;
  }
  if (key !== null) {
    page.busy.add(key);
  }
  const request = page.queue.then(() => page.hub.api(name, data));
  // The queue only waits for each request to finish. A failed one is reported just below
  page.queue = request.catch(() => {});
  let reply;
  try {
    reply = await request;
  } catch (e) {
    turnedDown(name, e);
    return null;
  } finally {
    page.busy.delete(key);
  }
  // Only the request is the bot's part. A mistake in showing its reply is the page's
  try {
    showReply(reply, effect);
  } catch (e) {
    pageBug(`showing the reply to ${name}`, e);
  }
  return reply;
}

// The bot turning an action down arrives as a HubError carrying its reason. Anything else, like a lost connection, is
// a failure on this side
function turnedDown(name, e) {
  if (e instanceof HubError) {
    hud.toast(e.message, "error");
    sound.play("refused");
  } else {
    pageBug(`the ${name} request`, e);
  }
}

function showReply(reply, effect) {
  if (reply.state) {
    applyState(reply.state);
  }
  if (effect) {
    sound.play(effect);
  }
  newsFrom(reply.events || []);
}

// A button that sends an action, disabled while its request is in flight
async function actButton(button, name, data, options) {
  button.disabled = true;
  try {
    return await act(name, data, options);
  } finally {
    button.disabled = false;
  }
}

function newsFrom(events) {
  const kinds = new Set(events.map((event) => event.kind));
  for (const [kind, effect] of Object.entries(NEWS_SOUNDS)) {
    if (kinds.has(kind)) {
      sound.play(effect);
    }
  }
  hud.showNews(events, page.catalog);
}

// ---------- Rooms ----------

function go(direction) {
  const to = ROOMS[page.room].exits[direction];
  if (to && page.state && opens(to) && !hud.covered()) {
    enterRoom(to, DIRECTIONS[direction].from);
  }
}

// Whether a room's door is open: an extra farmhouse room only once the farm owns it
function opens(id) {
  return (ROOMS[id].needs || 0) <= (page.state ? page.state.rooms : 0);
}

// Walks into a room from one side (null: appears in the middle)
function enterRoom(id, from) {
  const before = page.scene.room;
  if (before && page.state) {
    callView(before, "leave");
  }
  page.room = id;
  const room = ROOMS[id];
  $("app").dataset.room = id;
  page.scene.show(room, ...sky());
  page.scene.arrive(from);
  hud.showRoom(room, opens);
  hearRain();
  if (before && Boolean(before.inside) !== Boolean(room.inside)) {
    sound.play("door");
  } else if (before) {
    sound.play("tap");
  }
  if (page.state) {
    callView(room, "enter");
  }
}

// Draws the room again where the farmer stands: the farm's first state, a new season or a new day's weather. The view's
// enter() runs again with no leave() first, so a view can keep what the player is in the middle of
function redraw() {
  const room = ROOMS[page.room];
  const { x, y } = page.scene.farmer;
  page.scene.show(room, ...sky());
  page.scene.farmer.place(x, y);
  callView(room, "enter");
}

// The season and weather to draw: the bot's, or a sunny summer before the farm opens
function sky() {
  return page.state ? [page.state.season.name, page.state.weather.name] : ["summer", "sun"];
}

function hearRain() {
  sound.setRain(Boolean(page.state) && page.state.weather.name === "rain" && !ROOMS[page.room].inside);
}

function bindKeys() {
  window.addEventListener("keydown", (event) => {
    const direction = Object.keys(DIRECTIONS).find((name) => DIRECTIONS[name].key === event.key);
    if (!direction || event.target.closest("input, textarea, select")) {
      return;
    }
    event.preventDefault();
    go(direction);
  });
}

// ---------- Sound switches ----------

// Presses wait for the farm's state: until it arrives, the switches saved with the farm are on their way and would undo
// a press
function switchSound() {
  if (page.state) {
    sound.setSfx(!sound.sfxOn);
    savePrefs();
  }
}

function switchMusic() {
  if (page.state) {
    sound.setMusic(!sound.musicOn);
    savePrefs();
  }
}

// Each press saves both switches as they are now, so the last press always wins
function savePrefs() {
  hud.showSwitches(sound.sfxOn, sound.musicOn);
  sound.play("tap");
  act("prefs", { sound: sound.sfxOn, music: sound.musicOn }, { key: null, sound: null });
}

window.addEventListener("pagehide", () => clearTimeout(page.refreshTimer));

start().catch((e) => hud.showNotice(failure("starting the page", e)));
