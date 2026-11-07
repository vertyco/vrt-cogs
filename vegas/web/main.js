// The casino's page: the live connection, the top bar, and switching between the lobby and a table.
// The bot runs every game; this page sends the player's bets and moves and shows what the bot sends back.
import { backToMenu, connect } from "activityhub";
import { money, tierColor } from "./format.js";
import { Lobby, shortName } from "./lobby.js";
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
// What the bot sends the table the player is at. Hold'em adds the player's own cards and its offers to buy in
const TABLE_MESSAGES = ["table", "event", "result", "ask", "hole", "offer"];
const TOAST_MS = 4000;
const NEWS_MS = 5000;

const sound = new Sound();
const page = {
  hub: null,
  conn: null,
  me: null,
  casino: null,
  currency: "credits",
  canManage: false,
  owner: false,
  // Who is at each table and in the lobby, as the bot last sent it
  faces: {},
  // Whether the walk to a friend's table (Join) has been done, which it is at most once
  followed: false,
  // The last status line, data and busy flag given to the hub, and whether the live connection is gone for good
  reported: "",
  closed: false,
  // When each game is ready again, as performance.now() times, from the seconds the bot sent
  readyAt: {},
  game: null,
  table: null,
  lobby: null,
  toastTimer: null,
  // The Slots jackpot in whole credits, as the bot last said
  jackpot: null,
  newsTimer: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Starting ----------

async function start() {
  page.lobby = new Lobby($("lobby"), $("menu"), enter);
  page.lobby.render(null, null);
  bindTopBar();
  panels.setup({
    api: (name, data) => page.hub.api(name, data),
    hub: () => page.hub,
    currency: () => page.currency,
    toast,
    afterChange: () => {},
  });
  try {
    page.hub = await connect();
  } catch (e) {
    toast(e.message);
    return;
  }
  document.querySelector(".tools").prepend(page.hub.peopleButton());
  page.hub.onPeople(() => drawLobby());
  // A tap on a face in the lobby says who it is, for phones
  $("app").addEventListener("face", (event) => toast(event.detail));
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
    leaveCasino();
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
    leaveCasino();
  });
}

function bindTopBar() {
  $("back").addEventListener("click", back);
  $("open-rules").addEventListener("click", () => panels.showRules());
  $("open-stats").addEventListener("click", () => panels.showStats(null));
  $("open-tiers").addEventListener("click", () => panels.showTiers());
  $("open-settings").addEventListener("click", () => panels.showSettings());
  bindSound();
}

// ---------- Sound panel ----------

// The sound button opens a small panel under it: a switch and a volume slider for the sound effects, and the same for
// the music. A press anywhere else, Escape, or the button again closes it
function bindSound() {
  $("sound").addEventListener("click", () => showSound($("sound-panel").hidden));
  // Caught on the way down, so a press that the menu or a table handles itself still closes the panel
  document.addEventListener(
    "pointerdown",
    (event) => {
      if (!$("sound-spot").contains(event.target)) {
        showSound(false);
      }
    },
    true,
  );
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || $("sound-panel").hidden) {
      return;
    }
    const inside = $("sound-panel").contains(document.activeElement);
    showSound(false);
    if (inside) {
      $("sound").focus();
    }
  });
  $("sfx-switch").addEventListener("click", () => {
    sound.setSfx(!sound.sfxOn);
    drawSound();
  });
  $("music-switch").addEventListener("click", () => {
    sound.setMusic(!sound.musicOn);
    drawSound();
  });
  // Letting go of the effects slider lays a chip at the new volume, so the player hears it
  bindVolume($("sfx-volume"), sound.sfxVolume, (volume) => sound.setSfxVolume(volume), () => sound.play("chip"));
  bindVolume($("music-volume"), sound.musicVolume, (volume) => sound.setMusicVolume(volume), () => {});
  drawSound();
}

function showSound(open) {
  $("sound-panel").hidden = !open;
  $("sound").setAttribute("aria-expanded", String(open));
}

// The switches, and the sound button crossed out once every sound is off
function drawSound() {
  $("sfx-switch").setAttribute("aria-checked", String(sound.sfxOn));
  $("music-switch").setAttribute("aria-checked", String(sound.musicOn));
  $("sound").classList.toggle("muted", !sound.sfxOn && !sound.musicOn);
}

// A slider is heard as it moves and saved once it is let go
function bindVolume(slider, volume, set, letGo) {
  drawVolume(slider, volume);
  slider.addEventListener("input", () => {
    set(Number(slider.value));
    drawVolume(slider, Number(slider.value));
  });
  slider.addEventListener("change", () => {
    sound.keepVolumes();
    letGo();
  });
}

// The track fills gold up to the knob
function drawVolume(slider, volume) {
  slider.value = String(volume);
  slider.style.setProperty("--level", `${volume}%`);
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
      page.faces = data.faces || {};
      drawLobby();
      followFriend();
      report();
      break;
    case "casino":
      page.casino = data.casino;
      setJackpot(data.casino.games.slots?.jackpot);
      refresh();
      break;
    case "jackpot":
      jackpotNews(data);
      break;
    case "me":
      setMe(data);
      break;
    case "notice":
      toast(data.text);
      page.table?.notice();
      break;
    default:
      if (TABLE_MESSAGES.includes(data.t) && page.table && data.game === page.game) {
        page.table.receive(data);
      }
  }
}

function hello(data) {
  page.casino = data.casino;
  setJackpot(data.casino.games.slots?.jackpot);
  page.currency = data.currency || "credits";
  page.canManage = Boolean(data.can_manage);
  page.owner = Boolean(data.owner);
  setMe(data.me);
  // After a reconnect the bot has the player in the lobby, so a page showing a table walks back up to it. A pull sent
  // on the old connection never gets its spin, so the table stops waiting for it
  if (page.game) {
    page.table?.notice();
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
  drawLobby();
  page.table?.update();
}

// The pot on the menu card, and on the machine at Slots, where it waits behind the spin being shown (with the
// winner's note, when it is theirs)
function setJackpot(amount, note = null) {
  page.jackpot = amount ?? null;
  page.lobby.showJackpot(page.jackpot);
  if (page.game === "slots") {
    page.table?.receive({ t: "jackpot", amount: page.jackpot, note });
  }
}

// After every Slots spin the bot sends the pot. When someone in this window hit it, everyone here sees a note. The
// winner's own note waits at the machine until their reels have landed and their result shows, so it spoils nothing
function jackpotNews(data) {
  const note = data.hit ? `${shortName(data.hit.name)} hit the jackpot: ${money(data.hit.amount)}!` : null;
  const mine = note !== null && data.hit.id === page.me?.id && page.game === "slots";
  setJackpot(data.amount, mine ? note : null);
  if (note && !mine) {
    news(note);
  }
}

function readyIn(game) {
  const at = page.readyAt[game];
  return at ? Math.max(0, (at - performance.now()) / 1000) : 0;
}

// False when the message couldn't go, as while the connection comes back
function send(message) {
  if (page.conn?.send(message)) {
    return true;
  }
  toast("Not connected right now.");
  return false;
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
  $("table").dataset.game = game;
  $("back").setAttribute("aria-label", "Back to the casino");
  page.table = new TableView(game, {
    send,
    sound,
    casino: () => page.casino,
    me: () => page.me,
    readyIn,
    showPlayer: (id) => panels.showStats(id),
    toast,
    changed: report,
    jackpot: () => page.jackpot,
    news,
  });
  send({ t: "enter", game });
  report();
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
  report();
}

// ---------- Who's here ----------

// The lobby with who is where, and what the hub's people list says about each of them
function drawLobby() {
  const rows = new Map((page.hub?.people || []).map((person) => [person.id, person]));
  page.lobby.render(
    page.casino,
    page.me,
    page.faces,
    (id) => rows.get(id)?.status ?? "",
    (id) => Boolean(rows.get(id)?.away),
  );
}

// Join from the hub's people list: on the first lobby update, walk to the friend's table as if it were picked.
// A friend in the lobby, or already gone, leaves this player in the lobby
function followFriend() {
  const follow = page.hub?.follow;
  if (!follow || page.followed || !page.conn) {
    return;
  }
  page.followed = true;
  const table = Object.keys(page.faces).find(
    (spot) => spot !== "lobby" && page.faces[spot].some((person) => person.id === follow.id),
  );
  if (table && !page.game) {
    enter(table);
  }
}

// What the rest of the window sees this player doing, and whether a bet is riding on a round
function activity() {
  if (!page.game) {
    return ["In the lobby", null, false];
  }
  const name = page.casino?.games?.[page.game]?.name || page.game;
  const table = page.table;
  if (page.game === "holdem") {
    return holdemActivity(name, table);
  }
  const row = table?.myRow();
  const phase = table?.state?.phase || "idle";
  const inRound = Boolean(row && row.bet != null && row.outcome == null && phase !== "idle");
  let text = `At ${name}`;
  if (inRound && page.game === "craps" && table.state.shooter === table.myId()) {
    text = `${name} · has the dice`;
  } else if (inRound) {
    text = `${name} · bet ${money(row.bet)}`;
  }
  return [text, { table: page.game }, inRound];
}

// Hold'em has no bets riding on rounds: a seated player has a stack, and is busy while dealt into a hand
function holdemActivity(name, table) {
  const data = { table: "holdem" };
  const seat = table?.dock?.mySeat();
  if (!seat) {
    return ["Watching Hold'em", data, false];
  }
  const busy = seat.in_hand && !seat.folded;
  if (table.state.mode === "real") {
    return [`${name} · ${money(seat.stack)} chips`, data, busy];
  }
  return ["Practicing Hold'em", data, busy];
}

// The hub passes on whatever it is told, even when nothing changed, so only changes go to it
function tell(text, data, busy) {
  const look = JSON.stringify([text, data, busy]);
  if (look === page.reported) {
    return;
  }
  page.reported = look;
  page.hub.status(text, data);
  page.hub.busy(busy);
}

function report() {
  if (!page.closed) {
    tell(...activity());
  }
}

// The live connection is gone for good, so a friend's Join has nothing to interrupt
function leaveCasino() {
  page.closed = true;
  tell("Not connected", null, false);
}

// A short gold note under the top bar, over the menu or a table, that nothing can be pressed through
function news(text) {
  const node = $("news");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(page.newsTimer);
  page.newsTimer = setTimeout(() => {
    node.hidden = true;
  }, NEWS_MS);
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
