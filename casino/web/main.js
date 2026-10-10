// The casino's page: the live connection, the top bar, and switching between the lobby and a table.
// The bot runs every game; this page sends the player's bets and moves and shows what the bot sends back.
import { backToMenu, connect } from "activityhub";
import { money, tierColor } from "./format.js";
import { Lobby } from "./lobby.js";
import * as panels from "./panels.js";
import { Sound } from "./sound.js";
import { TableView } from "./table.js";

const CLOSED_BECAUSE = {
  1006: "Lost the connection. Go back to the menu and open the casino again.",
  1011: "Couldn't open the casino.",
  4003: "The casino was turned off in this server.",
  4029: "This page sent too many messages, so the bot disconnected it.",
  4100: "Open the casino in a server.",
  4101: "The casino is still opening. Go back and try again in a moment.",
};
const CLOSED_OTHERWISE = "The casino closed. Go back to the menu and open it again.";
const TOAST_MS = 4000;

const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  me: null,
  casino: null,
  currency: "credits",
  canManage: false,
  owner: false,
  counts: {},
  // When each game is ready again, as performance.now() times, from the seconds the bot sent
  readyAt: {},
  game: null,
  table: null,
  lobby: null,
  toastTimer: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  page.lobby = new Lobby($("lobby"), $("floor"), enter);
  page.lobby.render(null, {}, null);
  bindTopBar();
  panels.setup({
    api: (name, data) => page.hub.api(name, data),
    hub: () => page.hub,
    toast,
    afterChange: () => {},
  });
  try {
    page.hub = await connect();
  } catch (e) {
    toast(e.message);
    return;
  }
  if (page.hub.offline) {
    toast("This is a preview. Open the casino from Discord to play.");
    return;
  }
  await goLive();
}

async function goLive() {
  try {
    page.conn = await page.hub.socket();
  } catch (e) {
    toast(CLOSED_BECAUSE[e.status] || e.message);
    return;
  }
  page.conn.on(receive);
  page.conn.onReconnecting(() => {
    $("banner").hidden = false;
  });
  page.conn.onReconnected(() => {
    $("banner").hidden = true;
  });
  page.conn.onClose((code) => {
    $("banner").hidden = true;
    toast(CLOSED_BECAUSE[code] || CLOSED_OTHERWISE, true);
  });
}

function bindTopBar() {
  $("back").addEventListener("click", back);
  $("open-rules").addEventListener("click", () => panels.showRules());
  $("open-stats").addEventListener("click", () => panels.showStats(null));
  $("open-tiers").addEventListener("click", () => panels.showTiers());
  $("open-settings").addEventListener("click", () => panels.showSettings());
  const music = $("music");
  const sfx = $("sfx");
  music.setAttribute("aria-pressed", String(sound.musicOn));
  sfx.setAttribute("aria-pressed", String(sound.sfxOn));
  music.addEventListener("click", () => {
    sound.setMusic(!sound.musicOn);
    music.setAttribute("aria-pressed", String(sound.musicOn));
  });
  sfx.addEventListener("click", () => {
    sound.setSfx(!sound.sfxOn);
    sfx.setAttribute("aria-pressed", String(sound.sfxOn));
  });
}

// ---------- Messages from the bot ----------

function receive(data) {
  if (!data || typeof data !== "object") {
    return;
  }
  switch (data.t) {
    case "hello":
      hello(data);
      break;
    case "lobby":
      page.counts = data.counts || {};
      page.lobby.render(page.casino, page.counts, page.me);
      break;
    case "casino":
      page.casino = data.casino;
      refresh();
      break;
    case "me":
      setMe(data);
      break;
    case "notice":
      toast(data.text);
      page.table?.notice();
      break;
    default:
      if (["table", "event", "result", "ask"].includes(data.t) && page.table && data.game === page.game) {
        page.table.receive(data);
      }
  }
}

function hello(data) {
  page.casino = data.casino;
  page.currency = data.currency || "credits";
  page.canManage = Boolean(data.can_manage);
  page.owner = Boolean(data.owner);
  setMe(data.me);
  // After a reconnect the bot has the player in the lobby, so a page showing a table walks back up to it
  if (page.game) {
    send({ t: "enter", game: page.game });
  }
}

function setMe(me) {
  page.me = me;
  const now = performance.now();
  page.readyAt = Object.fromEntries(Object.entries(me.ready || {}).map(([key, seconds]) => [key, now + seconds * 1000]));
  refresh();
}

// Everything that shows the casino's settings or the player's facts
function refresh() {
  const me = page.me;
  $("casino-name").textContent = page.casino ? `${page.casino.name} Casino` : "Casino";
  $("balance").textContent = me ? money(me.balance) : "-";
  $("currency").textContent = page.currency;
  const tier = $("tier");
  tier.textContent = me ? me.membership.name : "";
  tier.style.setProperty("--tier-color", me ? tierColor(me.membership.color) : "");
  $("open-settings").hidden = !page.canManage && !page.owner;
  page.lobby.render(page.casino, page.counts, me);
  page.table?.update();
}

function readyIn(game) {
  const at = page.readyAt[game];
  return at ? Math.max(0, (at - performance.now()) / 1000) : 0;
}

function send(message) {
  if (!page.conn || !page.conn.send(message)) {
    toast("Not connected right now.");
  }
}

// ---------- Moving around ----------

function enter(game) {
  if (!page.conn) {
    toast(page.hub && page.hub.offline ? "Open the casino from Discord to play." : "Still connecting...");
    return;
  }
  sound.play("click");
  page.game = game;
  $("app").dataset.view = "table";
  $("lobby").hidden = true;
  $("table").hidden = false;
  $("back").setAttribute("aria-label", "Back to the casino floor");
  page.table = new TableView(game, {
    send,
    sound,
    casino: () => page.casino,
    me: () => page.me,
    readyIn,
    showPlayer: (id) => panels.showStats(id),
    toast,
  });
  send({ t: "enter", game });
}

function back() {
  if (!page.table) {
    backToMenu();
    return;
  }
  send({ t: "lobby" });
  page.table.close();
  page.table = null;
  page.game = null;
  $("app").dataset.view = "lobby";
  $("table").hidden = true;
  $("lobby").hidden = false;
  $("back").setAttribute("aria-label", "Back to the menu");
  page.lobby.layout();
}

function toast(text, stay = false) {
  const node = $("toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.toastTimer);
  if (!stay) {
    page.toastTimer = setTimeout(() => {
      node.hidden = true;
    }, TOAST_MS);
  }
}

start();
