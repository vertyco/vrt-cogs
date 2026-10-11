// The Market. The stall opens the shop: seeds, baby animals, feed and better tools to buy, crops and grown animals to
// sell, and decorations and outfits. The signpost beside it is the bank counter, where FarmCoins become the server's
// credits. A button in the corner hands out a free seed packet, for a farm with nothing left to grow or sell. Prices,
// counts and levels all come from the bot's state and catalog, and the bot decides each deal.
import { openBank } from "./bank.js";
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
import { Container, Graphics, Text } from "./vendor/pixi.min.mjs";

// The room's tappable pieces (labelled in rooms.js), where the farmer stands to use each, and the name over it
const COUNTERS = {
  stall: { stand: { x: 500, y: 525 }, name: "Shop" },
  bank: { stand: { x: 860, y: 520 }, name: "Bank" },
};
const NAME_STYLE = { fontFamily: "Fredoka", fontSize: 24, fontWeight: "700", fill: "#3a2a12" };
// How far above a counter's top its name floats, and the coin over the bank's signpost
const NAME_GAP = 26;
const COIN_SIZE = 64;
// The bot's own words for refusals the state already shows coming (the rest are in rows.js)
const STORAGE_FULL = "Storage full";
const EXPECTING = "She's expecting. Sell her after the babies arrive.";
// What a better tool does besides holding more water
const TOOL_NOTES = {
  sprinkler_can: "Waters a whole row at once",
  wide_hoe: "Tills a whole row at once",
  plow: "Tills a whole plot at once",
};
const LOOKS = [
  { kinds: ["decoration"], title: "Decorations", note: "Place them in your Yard or a farmhouse room" },
  { kinds: ["hat", "top", "bottom"], title: "Clothes", note: "Wear them from the farmhouse" },
];
const SLOT_WORDS = { hat: "Hat", top: "Top", bottom: "Bottom" };
const TABS = [
  { key: "seeds", name: "Seeds", rows: seedRows },
  { key: "animals", name: "Animals", rows: animalRows },
  { key: "feed", name: "Feed", rows: feedRows },
  { key: "tools", name: "Tools", rows: toolRows },
  { key: "sell", name: "Sell", rows: sellRows },
  { key: "looks", name: "Looks", rows: lookRows },
];
const NOTHING_TO_SELL = "Nothing to sell yet. Harvest crops, or raise animals until they grow up.";

const shop = {
  tab: "seeds",
  // The shop's contents while it is open
  root: null,
  // The number in each row's box, by row key, kept while the shop is drawn again
  counts: {},
  // The pen last picked for a new animal
  pen: null,
};

function $(id) {
  return document.getElementById(id);
}

// ---------- The room ----------

function enter(ctx) {
  for (const [label, counter] of Object.entries(COUNTERS)) {
    const piece = ctx.scene.things.getChildByLabel(label);
    const open = label === "stall" ? openShop : openBank;
    const onTap = ctx.safe(`tapping the ${counter.name}`, () => open(ctx));
    ctx.scene.addTarget(piece, { walkTo: counter.stand, onTap });
    let top = piece.y - piece.anchor.y * piece.height;
    if (label === "bank") {
      const coin = ctx.scene.sprite("icon/coin", piece.x, top - COIN_SIZE / 2);
      coin.zIndex = piece.zIndex;
      ctx.scene.things.addChild(coin);
      ctx.scene.addTarget(coin, { walkTo: counter.stand, onTap });
      top -= COIN_SIZE;
    }
    const sign = nameSign(counter.name, piece.x, top - NAME_GAP, piece.zIndex);
    ctx.scene.things.addChild(sign);
    ctx.scene.addTarget(sign, { walkTo: counter.stand, onTap });
  }
  const packet = [ctx.hud.icon("icon/seed:wildflowers", 32), ctx.hud.make("span", "", "Free seed packet")];
  $("free-packet").replaceChildren(...packet);
  $("free-packet").onclick = ctx.safe("the free packet button", () => freePacket(ctx, $("free-packet")));
  update(ctx);
}

function update(ctx) {
  $("market-buttons").hidden = false;
  $("free-packet").hidden = !ctx.state().free_packet;
  if (shopOpen()) {
    drawShop(ctx);
  }
}

function leave() {
  $("market-buttons").hidden = true;
}

export const marketView = { enter, update, leave };

// A counter's name on a little cream board, standing over it. The farmhouse names its board and wardrobe the same way
export function nameSign(text, x, y, zIndex) {
  const words = new Text({ text, style: NAME_STYLE });
  words.anchor.set(0.5);
  const width = words.width + 28;
  const height = words.height + 10;
  const board = new Graphics()
    .roundRect(-width / 2, -height / 2, width, height, height / 2)
    .fill(0xfffaf0)
    .stroke({ width: 3, color: 0x6b3f1c });
  const sign = new Container();
  sign.addChild(board, words);
  sign.position.set(x, y);
  sign.zIndex = zIndex;
  return sign;
}

async function freePacket(ctx, button) {
  const reply = await ctx.actButton(button, "free_packet", {});
  if (reply) {
    ctx.hud.toast(`Here's a free packet of ${ctx.hud.cropName(ctx.catalog(), reply.result.item)} seeds.`);
  }
}

// ---------- The shop ----------

function openShop(ctx) {
  ctx.sound.play("tap");
  const body = ctx.hud.openPanel("Shop");
  shop.root = ctx.hud.make("div", "shop");
  body.append(shop.root);
  drawShop(ctx);
}

function shopOpen() {
  return Boolean(shop.root?.isConnected) && $("panel").open;
}

// The tabs and the open tab's rows. A box being typed in keeps its focus when a new state draws the shop again
function drawShop(ctx) {
  const { make } = ctx.hud;
  const typing = document.activeElement?.closest?.(".shop-row")?.dataset.key;
  const tabs = make("nav", "shop-tabs");
  tabs.setAttribute("aria-label", "Shop");
  for (const tab of TABS) {
    const button = make("button", "shop-tab", tab.name);
    button.type = "button";
    button.dataset.tab = tab.key;
    button.setAttribute("aria-pressed", String(tab.key === shop.tab));
    button.addEventListener("click", ctx.safe("a shop tab", () => showTab(ctx, tab.key)));
    tabs.append(button);
  }
  const list = make("ul", "shop-list");
  const rows = TABS.find((tab) => tab.key === shop.tab).rows(ctx);
  list.append(...rows);
  if (!rows.length) {
    list.append(make("li", "shop-empty dim", NOTHING_TO_SELL));
  }
  shop.root.replaceChildren(tabs, list);
  if (typing) {
    shop.root.querySelector(`.shop-row[data-key="${typing}"] input`)?.focus();
  }
}

function showTab(ctx, key) {
  ctx.sound.play("tap");
  shop.tab = key;
  drawShop(ctx);
  $("panel").scrollTop = 0;
}

// Only the amount's text changes: a count box's change lands as the press on this button begins, and swapping the
// pressed element out then would lose the press
function showAmount(ctx, button, coins) {
  button.querySelector(".price b").textContent = ctx.hud.number(coins);
}

// One deal with one button: a tool, a decoration or outfit, an animal to sell. `done(reply)` runs when the bot agrees
function oneDeal(ctx, base, verb, coins, [name, data], { why = "", options = {}, done = null } = {}) {
  const button = dealButton(ctx, verb, coins);
  const problem = why || (verb === "Buy" && coins > ctx.state().player.coins ? NO_COINS : "");
  button.disabled = Boolean(problem);
  const send = async () => {
    const reply = await ctx.actButton(button, name, data, options);
    if (reply && done) {
      done(reply);
    }
  };
  button.addEventListener("click", ctx.safe(`the ${verb} button`, send));
  return shopRow(ctx, base, [button], problem);
}

// A deal for a number of one thing: { verb, start, most, total(n), problem(n), request(n) -> [action, data],
// done(reply) }. The button shows what that many cost or bring, and turns off with the reason the state shows
function countedRow(ctx, base, deal) {
  keep(shop.counts, base.key, deal.start, deal.most);
  const button = dealButton(ctx, deal.verb, 0);
  const row = shopRow(ctx, base, [countBox(ctx, shop.counts, base.key, deal.most, (n) => show(n)), button]);
  const why = row.querySelector(".shop-why");
  const show = (n) => {
    showAmount(ctx, button, deal.total(n));
    const problem = deal.problem(n);
    button.disabled = Boolean(problem);
    why.textContent = problem;
    why.hidden = !problem;
  };
  const send = async () => {
    const count = shop.counts[base.key];
    const reply = await ctx.actButton(button, ...deal.request(count));
    if (reply && deal.done) {
      deal.done(reply);
    }
  };
  button.addEventListener("click", ctx.safe(`the ${deal.verb} button`, send));
  show(shop.counts[base.key]);
  return row;
}

// Seeds or feed: as many as fit in storage, at a price each
function stockRow(ctx, base, each, request) {
  const state = ctx.state();
  const have = state.items[base.key]?.quantity || 0;
  const room = state.storage.limit - have;
  const problem = (n) => (room < 1 ? STORAGE_FULL : n * each > state.player.coins ? NO_COINS : "");
  const owned = `You have ${ctx.hud.number(have)}`;
  const deal = { verb: "Buy", start: 1, most: Math.max(1, room), total: (n) => n * each, problem, request };
  return countedRow(ctx, { ...base, owned }, deal);
}

function locked(ctx, level) {
  return level > ctx.state().player.level;
}

// ---------- What each tab lists ----------

function seedRows(ctx) {
  const season = ctx.state().season.name;
  return ctx.catalog().crops.map((crop) => {
    const key = `seed:${crop.key}`;
    const note = ctx.hud.growNote(crop, season);
    const base = { key, picture: ctx.hud.icon(`icon/${key}`, PICTURE), name: crop.name, note };
    if (locked(ctx, crop.level)) {
      return lockedRow(ctx, base, crop.level, crop.seed_price);
    }
    return stockRow(ctx, base, crop.seed_price, (quantity) => ["buy_seeds", { crop: crop.key, quantity }]);
  });
}

// "Wheat, radishes and corn"
function listWords(names) {
  const words = names.map((name, i) => (i ? name.toLowerCase() : name));
  return words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words.at(-1)}` : words.join("");
}

function feedRows(ctx) {
  const crops = ctx.catalog().crops.filter((crop) => crop.feed);
  const words = `${listWords(crops.map((crop) => crop.name))} from your fields feed any animal too.`;
  const intro = ctx.hud.make("li", "shop-intro dim", words);
  const rows = ctx.catalog().animals.map((animal) => {
    const key = `feed:${animal.key}`;
    const note = `One meal for a ${animal.name.toLowerCase()}`;
    const base = { key, picture: ctx.hud.icon(`icon/${key}`, PICTURE), name: `${animal.name} feed`, note };
    if (locked(ctx, animal.level)) {
      return lockedRow(ctx, base, animal.level, animal.feed_price);
    }
    return stockRow(ctx, base, animal.feed_price, (quantity) => ["buy_feed", { kind: animal.key, quantity }]);
  });
  return [intro, ...rows];
}

// Grown chickens and cows look different by sex; the others share one look
function grownLook(ctx, row) {
  const sexed = `animal/${row.kind}/adult/${row.sex}`;
  return ctx.scene.art.animation(sexed) ? sexed : `animal/${row.kind}/adult`;
}

function animalRows(ctx) {
  const state = ctx.state();
  const size = ctx.catalog().constants.pen_size;
  const pens = state.plots.filter((plot) => plot.unlocked && plot.kind === "animals");
  const open = pens.filter((plot) => plot.animals.length < size);
  const why = !pens.length ? NO_PEN : !open.length ? PENS_FULL : "";
  return ctx.catalog().animals.map((animal) => {
    const grown = `worth ${ctx.hud.number(animal.adult_price)} grown up`;
    const note = `Grows up in ${ctx.hud.duration(animal.grow_time)}, ${grown}`;
    const picture = animalPicture(ctx, `animal/${animal.key}/baby`);
    const base = { key: `baby:${animal.key}`, picture, name: animal.name, note };
    if (locked(ctx, animal.level)) {
      return lockedRow(ctx, base, animal.level, animal.baby_price);
    }
    const have = [...state.animals, ...state.waiting].filter((row) => row.kind === animal.key).length;
    const problem = why || (animal.baby_price > state.player.coins ? NO_COINS : "");
    return babyRow(ctx, { ...base, owned: `You have ${have}` }, animal, open, problem);
  });
}

// A baby animal: the pen it goes into, its price, then a button for each sex
function babyRow(ctx, base, animal, open, problem) {
  const pen = open.length ? penPicker(ctx, open, shop) : null;
  const parts = pen ? [pen] : [];
  parts.push(ctx.hud.price(animal.baby_price));
  for (const sex of ["male", "female"]) {
    const button = ctx.hud.make("button", `button deal ${sex}`, sex === "male" ? "Male" : "Female");
    button.type = "button";
    button.dataset.sex = sex;
    button.disabled = Boolean(problem);
    const buy = () => buyAnimal(ctx, button, animal, sex, Number(pen.value));
    button.addEventListener("click", ctx.safe("buying an animal", buy));
    parts.push(button);
  }
  return shopRow(ctx, base, parts, problem);
}

async function buyAnimal(ctx, button, animal, sex, plot) {
  shop.pen = plot;
  const reply = await ctx.actButton(button, "buy_animal", { kind: animal.key, sex, plot });
  if (reply) {
    ctx.hud.toast(`Your new ${animal.name.toLowerCase()} is in Plot ${plot}`);
  }
}

function toolRows(ctx) {
  const catalog = ctx.catalog();
  const rows = [];
  for (const [tool, tiers] of [
    ["can", catalog.cans],
    ["hoe", catalog.hoes],
  ]) {
    // The first of each is the starter every farm has
    for (const info of tiers.slice(1)) {
      const holds = tool === "can" ? `Holds ${ctx.hud.number(info.capacity)} water` : "";
      const note = [holds, TOOL_NOTES[info.key]].filter(Boolean).join(". ");
      const picture = ctx.hud.icon(`icon/${tool}_${info.tier}`, PICTURE);
      const base = { key: `${tool}:${info.tier}`, picture, name: info.name, note };
      rows.push(toolRow(ctx, base, tool, info));
    }
  }
  return rows;
}

function toolRow(ctx, base, tool, info) {
  const held = ctx.state().tools[tool];
  if (held >= info.tier) {
    return shopRow(ctx, { ...base, owned: held === info.tier ? "Yours" : "You have a better one" });
  }
  if (locked(ctx, info.level)) {
    return lockedRow(ctx, base, info.level, info.price);
  }
  return oneDeal(ctx, base, "Buy", info.price, ["buy_tool", { tool, tier: info.tier }]);
}

function sellRows(ctx) {
  const state = ctx.state();
  const crops = Object.entries(state.items).filter(([key, item]) => key.startsWith("crop:") && item.quantity > 0);
  const rows = crops.map(([key, item]) => cropSale(ctx, key, item));
  for (const animal of state.animals.filter((row) => row.adult)) {
    rows.push(animalSale(ctx, animal));
  }
  return rows;
}

// Part of a crop stack sells for that share of the whole stack's worth. The whole stack is offered first
function cropSale(ctx, key, item) {
  const { number } = ctx.hud;
  const name = ctx.hud.cropName(ctx.catalog(), key);
  const note = `Worth ${number(item.worth)} FarmCoins in all`;
  const owned = `You have ${number(item.quantity)}`;
  const base = { key, picture: ctx.hud.icon(`icon/${key}`, PICTURE), name, note, owned };
  const done = ({ result }) => {
    ctx.hud.toast(`+${number(result.coins)} FarmCoins for ${number(result.quantity)} ${name}`);
  };
  return countedRow(ctx, base, {
    verb: "Sell",
    start: item.quantity,
    most: item.quantity,
    total: (n) => Math.floor((item.worth * n) / item.quantity),
    problem: () => "",
    request: (quantity) => ["sell_crops", { item: key, quantity }],
    done,
  });
}

function animalSale(ctx, row) {
  const name = ctx.hud.catalogEntry(ctx.catalog().animals, row.kind).name;
  const facts = [`${row.sex === "male" ? "Male" : "Female"} in Plot ${row.plot}`];
  if (row.exceptional) {
    facts.push("exceptional");
  }
  if (row.condition !== "healthy") {
    facts.push(row.condition);
  }
  const picture = animalPicture(ctx, grownLook(ctx, row));
  const base = { key: `animal:${row.id}`, picture, name, note: facts.join(", ") };
  const done = ({ result }) => {
    ctx.hud.toast(`+${ctx.hud.number(result.coins)} FarmCoins for your ${name.toLowerCase()}`);
  };
  // The animal's own key, so a sale and a feeding of it never go at once
  const options = { key: `animal:${row.id}` };
  const why = row.expecting_until ? EXPECTING : "";
  return oneDeal(ctx, base, "Sell", row.price, ["sell_animal", { animal: row.id }], { why, options, done });
}

function lookRows(ctx) {
  const rows = [];
  for (const group of LOOKS) {
    const heading = ctx.hud.make("li", "shop-heading");
    heading.append(ctx.hud.make("b", "", group.title), ctx.hud.make("small", "dim", group.note));
    rows.push(heading);
    for (const item of ctx.catalog().cosmetics.filter((entry) => group.kinds.includes(entry.kind))) {
      rows.push(lookRow(ctx, item));
    }
  }
  return rows;
}

// A decoration (the player may own several of one) or an outfit piece (owned once), drawn alone
function lookRow(ctx, item) {
  const state = ctx.state();
  const decoration = item.kind === "decoration";
  const stand = ctx.scene.art.animation("farmer/base").clips.stand_front.start;
  const art = decoration ? `decor/${item.key}` : `farmer/${item.kind}/${item.key}/${stand}`;
  const picture = ctx.hud.icon(art, PICTURE, true);
  const base = { key: `cosmetic:${item.key}`, picture, name: item.name, note: SLOT_WORDS[item.kind] || "" };
  if (!decoration && state.outfits.includes(item.key)) {
    return shopRow(ctx, { ...base, owned: "Owned" });
  }
  if (locked(ctx, item.level)) {
    return lockedRow(ctx, base, item.level, item.price);
  }
  const have = state.decorations.filter((placed) => placed.item === item.key).length;
  const owned = decoration ? `You have ${have}` : "";
  return oneDeal(ctx, { ...base, owned }, "Buy", item.price, ["buy_cosmetic", { item: item.key }]);
}
