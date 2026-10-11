// The farmhouse board: everything the farm owns, on tabs. Farm: FarmCoins, tools, and the storage upgrades and extra
// rooms bought here. Storage: seeds, crops and feed, with seeds and crops thrown away here. Animals: the babies waiting
// in the farmhouse, each with a button to move it into a pen with room, and every pen. Badges: all of them, the earned
// ones lit. Top farms: the leaderboard. About: who designed the game. Counts, prices and levels come from the bot's
// state and catalog, and the bot decides each deal. The tabs and rows are the shop's (rows.js, market.css).
import { showLeaderboard } from "./leaderboard.js";
import { ROOMS } from "./rooms.js";
import {
  NO_COINS,
  NO_PEN,
  PENS_FULL,
  PICTURE,
  animalPicture,
  countBox,
  dealButton,
  keep,
  lockedRow,
  penPicker,
  shopRow,
} from "./rows.js";

const TABS = [
  { key: "farm", name: "Farm", page: farmPage },
  { key: "storage", name: "Storage", page: storagePage },
  { key: "animals", name: "Animals", page: animalsPage },
  { key: "badges", name: "Badges", page: badgesPage },
  { key: "leaders", name: "Top farms", page: leadersPage },
  { key: "about", name: "About", page: aboutPage },
];
const BADGE = 56;
const STORED = [
  { prefix: "seed:", title: "Seeds", empty: "No seeds. Buy some at the Market." },
  { prefix: "crop:", title: "Crops", empty: "No crops yet. Harvest some from your plots." },
  { prefix: "feed:", title: "Feed", empty: "No feed. Buy some at the Market." },
];

const board = {
  tab: "farm",
  // The board's contents while it is open
  root: null,
  // The number in each throw-away box, by item key, kept while the board is drawn again
  counts: {},
  // The pen last picked for a waiting baby
  pen: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- Opening and drawing ----------

export function openBoard(ctx, tab = board.tab) {
  ctx.sound.play("tap");
  board.tab = tab;
  const body = ctx.hud.openPanel("Farm board");
  board.root = ctx.hud.make("div", "board");
  body.append(board.root);
  drawBoard(ctx);
}

function boardOpen() {
  return Boolean(board.root?.isConnected) && $("panel").open;
}

// A new state draws the open tab again. The leaderboard isn't in the state, so it stays as it was asked for
export function updateBoard(ctx) {
  if (boardOpen() && board.tab !== "leaders") {
    drawBoard(ctx);
  }
}

// The tabs and the open tab's page. A box being typed in keeps its focus when a new state draws the board again
function drawBoard(ctx) {
  const { make } = ctx.hud;
  const typing = document.activeElement?.closest?.(".shop-row")?.dataset.key;
  const tabs = make("nav", "shop-tabs");
  tabs.setAttribute("aria-label", "Farm board");
  for (const tab of TABS) {
    const button = make("button", "shop-tab", tab.name);
    button.type = "button";
    button.dataset.tab = tab.key;
    button.setAttribute("aria-pressed", String(tab.key === board.tab));
    button.addEventListener("click", ctx.safe("a board tab", () => showTab(ctx, tab.key)));
    tabs.append(button);
  }
  const page = make("div", "board-page");
  page.append(...TABS.find((tab) => tab.key === board.tab).page(ctx));
  board.root.replaceChildren(tabs, page);
  if (typing) {
    board.root.querySelector(`.shop-row[data-key="${typing}"] input`)?.focus();
  }
}

function showTab(ctx, key) {
  ctx.sound.play("tap");
  board.tab = key;
  drawBoard(ctx);
  $("panel").scrollTop = 0;
}

// ---------- Rows ----------

function list(ctx, rows) {
  const items = ctx.hud.make("ul", "shop-list");
  items.append(...rows);
  return items;
}

function heading(ctx, title, note = "") {
  const item = ctx.hud.make("li", "shop-heading");
  item.append(ctx.hud.make("b", "", title));
  if (note) {
    item.append(ctx.hud.make("small", "dim", note));
  }
  return item;
}

function line(ctx, words) {
  return ctx.hud.make("li", "shop-intro dim", words);
}

// ---------- Farm: FarmCoins, tools, storage and rooms ----------

function farmPage(ctx) {
  const state = ctx.state();
  const catalog = ctx.catalog();
  const { icon, number } = ctx.hud;
  const { coins, level, xp } = state.player;
  const purse = { key: "coins", picture: icon("icon/coin", PICTURE), name: `${number(coins)} FarmCoins` };
  const can = catalog.cans[state.tools.can];
  const hoe = catalog.hoes[state.tools.hoe];
  const water = `${number(state.tools.water)} of ${number(state.tools.capacity)} water`;
  const rooms = catalog.rooms;
  return [
    list(ctx, [
      shopRow(ctx, { ...purse, note: `Level ${number(level)}, ${number(xp)} XP` }),
      heading(ctx, "Tools", "Better ones are sold at the Market"),
      shopRow(ctx, { key: "tool:can", picture: icon(`icon/can_${can.tier}`, PICTURE), name: can.name, owned: water }),
      shopRow(ctx, { key: "tool:hoe", picture: icon(`icon/hoe_${hoe.tier}`, PICTURE), name: hoe.name }),
      heading(ctx, "Storage", `Holds ${number(state.storage.limit)} of each seed, crop and feed`),
      storageRow(ctx),
      heading(ctx, "Farmhouse rooms", `${state.rooms} of ${rooms.length} extra rooms`),
      roomRow(ctx),
    ]),
  ];
}

// The next thing in line to buy: its level and price with nothing to press while the level is too low, else a button
// that is off, with the reason, while the FarmCoins fall short
function upgradeRow(ctx, base, { level, price }, send) {
  const state = ctx.state();
  if (level > state.player.level) {
    return lockedRow(ctx, base, level, price);
  }
  const button = dealButton(ctx, "Buy", price);
  const problem = price > state.player.coins ? NO_COINS : "";
  button.disabled = Boolean(problem);
  button.addEventListener("click", ctx.safe("a board purchase", () => send(button)));
  return shopRow(ctx, base, [button], problem);
}

function storageRow(ctx) {
  const next = ctx.catalog().storage[ctx.state().storage.tier + 1];
  if (!next) {
    return shopRow(ctx, { key: "storage", name: "The biggest storage there is" });
  }
  const base = { key: "storage", name: `Upgrade to ${ctx.hud.number(next.limit)} of each` };
  return upgradeRow(ctx, base, next, (button) => ctx.actButton(button, "buy_storage", { tier: next.tier }));
}

function roomRow(ctx) {
  const next = ctx.catalog().rooms[ctx.state().rooms];
  if (!next) {
    return shopRow(ctx, { key: "room", name: "Every room is yours" });
  }
  const base = { key: "room", name: next.name, note: "Holds decorations, and a description you write" };
  return upgradeRow(ctx, base, next, (button) => buyRoom(ctx, button, next));
}

async function buyRoom(ctx, button, info) {
  const reply = await ctx.actButton(button, "buy_room", { room: info.number });
  if (reply) {
    ctx.hud.toast(`Your ${info.name.toLowerCase()} is ready. Its door is ${doorOf(info.number)}.`);
  }
}

// Where an extra room's door is: "on the left side of the Farmhouse"
function doorOf(number) {
  for (const from of Object.values(ROOMS)) {
    for (const [side, to] of Object.entries(from.exits)) {
      if (ROOMS[to].kind === "room" && ROOMS[to].number === number) {
        return `on the ${side} side of the ${from.name}`;
      }
    }
  }
  return "in the farmhouse";
}

// ---------- Storage: seeds, crops and feed ----------

function storagePage(ctx) {
  const state = ctx.state();
  const rows = [line(ctx, `Storage holds ${ctx.hud.number(state.storage.limit)} of each item.`)];
  for (const kind of STORED) {
    rows.push(heading(ctx, kind.title));
    const items = Object.entries(state.items).filter(([key, item]) => key.startsWith(kind.prefix) && item.quantity);
    rows.push(...items.map(([key, item]) => storedRow(ctx, key, item)));
    if (!items.length) {
      rows.push(line(ctx, kind.empty));
    }
  }
  return [list(ctx, rows)];
}

// "Wildflowers seeds", "Wildflowers (exceptional)" or "Chicken feed"
function itemWords(ctx, key) {
  const [kind, name] = key.split(":");
  if (kind === "feed") {
    return `${ctx.hud.catalogEntry(ctx.catalog().animals, name).name} feed`;
  }
  const crop = ctx.hud.cropName(ctx.catalog(), key);
  return kind === "seed" ? `${crop} seeds` : crop;
}

// One stack. Seeds and crops can be thrown away, any number of them; feed can't
function storedRow(ctx, key, item) {
  const { icon, number } = ctx.hud;
  const seed = key.startsWith("seed:");
  const name = seed ? ctx.hud.cropName(ctx.catalog(), `crop:${key.slice(5)}`) : itemWords(ctx, key);
  const note = key.startsWith("crop:") ? `Worth ${number(item.worth)} FarmCoins in all` : "";
  const owned = `${number(item.quantity)} of ${number(ctx.state().storage.limit)}`;
  const base = { key, picture: icon(`icon/${key}`, PICTURE), name, note, owned };
  if (key.startsWith("feed:")) {
    return shopRow(ctx, base);
  }
  const button = dealButton(ctx, "Throw away");
  button.classList.remove("primary");
  button.addEventListener("click", ctx.safe("the Throw away button", () => throwAway(ctx, button, key)));
  keep(board.counts, key, 1, item.quantity);
  return shopRow(ctx, base, [countBox(ctx, board.counts, key, item.quantity), button]);
}

async function throwAway(ctx, button, key) {
  const count = board.counts[key];
  const words = `${ctx.hud.number(count)} ${itemWords(ctx, key)}`;
  if (!(await ctx.hud.confirmBox(`Throw away ${words}? They're gone for good.`, "Throw away", "Keep them"))) {
    return;
  }
  if (await ctx.actButton(button, "discard", { item: key, quantity: count })) {
    delete board.counts[key];
  }
}

// ---------- Animals: waiting babies and pens ----------

function animalsPage(ctx) {
  const state = ctx.state();
  const size = ctx.catalog().constants.pen_size;
  const pens = state.plots.filter((plot) => plot.unlocked && plot.kind === "animals");
  const rows = [];
  if (state.waiting.length) {
    rows.push(heading(ctx, "Waiting in the farmhouse", "Babies don't grow until they move into a pen"));
    const open = pens.filter((plot) => plot.animals.length < size);
    const why = !pens.length ? NO_PEN : !open.length ? PENS_FULL : "";
    rows.push(...state.waiting.map((baby) => babyRow(ctx, baby, open, why)));
  }
  rows.push(heading(ctx, "Pens"));
  rows.push(...pens.map((plot) => penRow(ctx, plot, size)));
  if (!pens.length) {
    rows.push(line(ctx, NO_PEN));
  }
  return [list(ctx, rows)];
}

function animalName(ctx, kind) {
  return ctx.hud.catalogEntry(ctx.catalog().animals, kind).name;
}

// A waiting baby: the pens with room, then a button that moves it into the one picked
function babyRow(ctx, baby, open, why) {
  const name = animalName(ctx, baby.kind);
  const picture = animalPicture(ctx, `animal/${baby.kind}/baby`);
  const base = { key: `baby:${baby.id}`, picture, name, note: baby.sex === "male" ? "Male baby" : "Female baby" };
  const pen = open.length ? penPicker(ctx, open, board) : null;
  const button = dealButton(ctx, "Move in");
  button.disabled = Boolean(why);
  const move = () => moveBaby(ctx, button, baby, name, Number(pen.value));
  button.addEventListener("click", ctx.safe("moving a baby", move));
  return shopRow(ctx, base, pen ? [pen, button] : [button], why);
}

async function moveBaby(ctx, button, baby, name, plot) {
  board.pen = plot;
  // The animal's own key, as its feeding and sale use, and its own voice
  const options = { key: `animal:${baby.id}`, sound: baby.kind };
  if (await ctx.actButton(button, "move_baby", { animal: baby.id, plot }, options)) {
    ctx.hud.toast(`Your ${name.toLowerCase()} moved into Plot ${plot}`);
  }
}

// A pen: how full it is and what lives in it, like "Chicken ×3, Cow ×1"
function penRow(ctx, plot, size) {
  const state = ctx.state();
  const counts = new Map();
  for (const id of plot.animals) {
    const kind = state.animals.find((animal) => animal.id === id)?.kind;
    counts.set(kind, (counts.get(kind) || 0) + 1);
  }
  const note = [...counts].map(([kind, n]) => `${animalName(ctx, kind)} ×${n}`).join(", ") || "Empty";
  const owned = `${plot.animals.length} of ${size}`;
  return shopRow(ctx, { key: `pen:${plot.number}`, name: `Plot ${plot.number}`, note, owned });
}

// ---------- Badges ----------

function badgesPage(ctx) {
  const { make, number } = ctx.hud;
  const earned = ctx.state().achievements;
  const all = ctx.catalog().achievements;
  const count = all.filter((badge) => badge.key in earned).length;
  const tiles = make("ul", "badges");
  for (const badge of all) {
    const tile = make("li", badge.key in earned ? "earned" : "");
    tile.dataset.key = badge.key;
    const words = make("span", "badge-words");
    const reward = `+${number(badge.coins)} FarmCoins, +${number(badge.xp)} XP`;
    words.append(make("b", "", badge.name), make("small", "", reward));
    if (badge.key in earned) {
      words.append(make("small", "earned-on", `Earned ${day(earned[badge.key])}`));
    }
    tile.append(ctx.hud.icon(`badge/${badge.key}`, BADGE), words);
    tiles.append(tile);
  }
  return [make("p", "board-intro", `${count} of ${all.length} earned`), tiles];
}

// "Oct 11, 2026", in UTC like the farm's calendar
function day(at) {
  return new Date(at * 1000).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

// ---------- Top farms and About ----------

function leadersPage(ctx) {
  const box = ctx.hud.make("div", "board-leaders");
  ctx.safe("the leaderboard", () => showLeaderboard(ctx, box))();
  return [box];
}

// The credit opens its link through Discord. Outside Discord there is nothing to open it with, so it is plain text
function aboutPage(ctx) {
  const { make } = ctx.hud;
  const { credit, creditUrl } = ctx.info();
  const hub = ctx.hub();
  const about = make("div", "about");
  about.append(make("h3", "", "FarmCord"));
  if (hub && hub.discord) {
    const link = make("button", "credit-link", credit);
    link.type = "button";
    link.id = "credit";
    link.addEventListener("click", ctx.safe("the credit link", () => openLink(ctx, creditUrl)));
    about.append(link);
  } else {
    const words = make("p", "", credit);
    words.id = "credit";
    about.append(words);
  }
  return [about];
}

async function openLink(ctx, url) {
  try {
    await ctx.hub().discord.commands.openExternalLink({ url });
  } catch (e) {
    console.warn("FarmCord: Discord didn't open the link", e);
    ctx.hud.toast("Discord didn't open the link.", "error");
  }
}
