// Searching containers: what a container holds the first time it is searched, the "[E] SEARCH" thing the room offers
// for it, and the search panel (searchContainer F4:13830, showSearch F4:14096, takeSearchItem, takeAllSearchItems).
//
// A container is searched once. Its contents are rolled at that moment (its fixed items, some junk from the room's
// table, lucky finds from the rarity tables, and a little cash in an "anywhere" room), shuffled, saved in
// story.containers and never filled again. What is left in it after the panel closes is what the next visit shows.
//
// story.containers[`${room id}_${container name}`] is { items, unlocked, broken }. items is null until the container is
// searched, then the list still inside it: { ref, lucky }, where ref is an item's key, "ammo9mm_5" (5 rounds) or
// "cash_10" ($10), the refs inventory.addItem takes. unlocked and broken are the lock's state (spec 2.9 "Locks and
// keys"): the lock's own system sets them.
//
// A container the art placed that the world data has no entry for is a plain prop: it opens the panel with nothing
// in it (W26). cont100 is the stash's footlocker, which the stash owns.
import { data } from "./data.js";
import { rangeRound, rarityItem } from "./drops.js";
import { help } from "./help.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { register } from "./interact.js";
import { addItem, carry, weight } from "./inventory.js";
import { closePanel, openPanel, panelOpen, restButtons, rowList } from "./panels.js";
import { addXP, searchXP } from "./player.js";
import { rng } from "./rng.js";
import { room } from "./rooms.js";
import { sound } from "./sound.js";
import { findItem, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "search";
const STORAGE = "cont100";
const PROP_TITLE = "Container";
const TEXT = { search: "[E] SEARCH", empty: "[E] EMPTY", pick: "[E] PICK LOCK", broken: "LOCK IS BROKEN" };
const TOO_HEAVY = "TOO MUCH WEIGHT";
// The panel stands in the middle of the stage, 7 px above it (F4:14100)
const PANEL_LIFT = 7;
// A row is 30 px tall, and the scroll bar's thumb runs along this track (F4:14126, 14187)
const ROW_HEIGHT = 30;
const BAR = { x: 18, top: -56, bottom: 94 };
// The item name's box: it starts this high and drops half a pixel for each size it shrinks (updateItemInfo F4:14238)
const NAME_TOP = -92;
const NAME_STEP = 0.5;
// Only a room whose junk table is "anywhere" holds cash
const CASH_ROOM = "anywhere";
const CASH_REF = /^cash_(\d+)$/;
const AMMO_REF = /^ammo(.+)_(\d+)$/;
const MOST_RECORDED = 100;
// TAKE ALL and EXIT take no press for this long after the panel opens: on a phone TAKE ALL overlaps the action button,
// and quick taps on SEARCH would take everything
const BUTTONS_REST_SECONDS = 0.5;

// Registers fn(key, amount) for each counter a search adds to: "search" for a container searched the first time and
// "luckyFind" for each lucky roll (checkAch F4:13852, 13897)
const countListeners = [];
// What was searched and taken, newest last, for checks
const log = [];
// The open panel: { clip, container, items, list, lucky }
let view = null;
let page = null;
let serial = 0;
const ids = new WeakMap();

export const search = {
  // What a lock's system plugs in. lock(container) runs when E is pressed on a shut lock, and words(container) says
  // what the prompt reads for it ({ text, grey } or a string), where the default is "[E] PICK LOCK"
  hooks: { lock: null, words: null },
};

export function onSearchCount(fn) {
  countListeners.push(fn);
}

function count(key, amount = 1) {
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function constant(name) {
  return data.actors.constants[name];
}

function note(kind, container, extra = {}) {
  log.push({ kind, container: container.key, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- What an item is ----------

// What the panel shows for a ref: its name, words, picture, weight and type, or null for a ref nothing knows
export function lookup(ref) {
  const cash = CASH_REF.exec(ref);
  if (cash) {
    const info = data.items.cash;
    const name = info.name.replace("{n}", cash[1]);
    return { name, desc: info.desc, icon: info.icon, weight: info.weight ?? 0, type: "money" };
  }
  const ammo = AMMO_REF.exec(ref);
  if (ammo && data.items.ammoTypes.includes(ammo[1])) {
    const info = data.items.ammo[ammo[1]];
    return {
      name: info.name.replace("{n}", ammo[2]),
      desc: `${ammo[2]}${info.desc}`,
      icon: info.icon,
      weight: info.weight ?? 0,
      type: "ammo",
    };
  }
  const found = findItem(ref);
  if (!found) {
    return null;
  }
  const { item } = found;
  return { name: item.name, desc: item.desc ?? "", icon: item.icon, weight: item.weight ?? 0, type: item.type, item };
}

// The lines under the picture for an item, by what it is (updateItemInfo F4:14254-14281)
function fieldsOf(info) {
  const { item } = info;
  const weightLine = `WEIGHT: ${info.weight}`;
  switch (info.type) {
    case "junk":
      return ["", weightLine, "", ""];
    case "food":
      return ["", weightLine, `EFFECT: +${item.bonus}`, ""];
    case "meds":
      return ["", weightLine, `EFFECT: ${item.effect.toUpperCase()}`, ""];
    case "books":
      return [weightLine, "EFFECT: ", item.effect, ""];
    case "weapon":
      return [weightLine, `DMG: ${item.damage}`, `RNDS: ${item.maxAmmo}`, `KNOCKBACK: ${item.knockback}%`];
    default:
      return ["", "", "", ""];
  }
}

// ---------- Rolling the contents ----------

function roomDanger(roomDef) {
  return roomDef.safeHouse ? 0 : (roomDef.danger ?? 0);
}

function shuffle(list) {
  for (let place = list.length - 1; place > 0; place -= 1) {
    const other = rng.random(place + 1);
    [list[place], list[other]] = [list[other], list[place]];
  }
}

// Junk from the room's table: the container may hold some half the time, fewer the more Searching the player has
// (more Searching also makes lucky finds likelier, which is the original's way, W29)
function rollJunk(roomDef, searching) {
  if (rng.random(constant("randomSearchRange")) > constant("randomSearchChance")) {
    return [];
  }
  const table = data.items.junkTables[roomDef.type] ?? [];
  const many = Math.max(0, Math.round(rng.random(constant("randomSearchUnits")) - searching / 10));
  return Array.from({ length: many }, () => table[rng.random(table.length)]).filter((ref) => findItem(ref));
}

// One or two lucky items, from the rarity tables the room's danger and the player's luck choose
function rollLucky(roomDef, luck, searching) {
  const chance = Math.round(constant("luckSearchChance") + luck * 5 + searching * 2);
  const tries = rng.random(constant("luckSearchUnits")) + 1;
  if (rng.random(constant("luckSearchRange")) > chance) {
    return { refs: [], tries: 0 };
  }
  const refs = [];
  for (let n = 0; n < tries; n += 1) {
    const found = rarityItem(roomDanger(roomDef));
    if (found && findItem(found.ref)) {
      refs.push(found.ref);
    }
  }
  return { refs, tries };
}

// A small pile of cash, up to the room's danger and the player's luck, in a room that is "anywhere"
function rollCash(roomDef, luck) {
  if (roomDef.type !== CASH_ROOM || rng.random(100) > constant("dropRateCash")) {
    return null;
  }
  const most = Math.min(Math.round(roomDanger(roomDef) * constant("cashAmountMod") + luck), data.items.cash.max);
  return `cash_${rangeRound(1, Math.max(1, Math.ceil(most / constant("searchCashMod"))))}`;
}

// What a container holds when it is first searched: { items, junk, lucky, cash } (items shuffled, the rest counts for
// a check). A container marked "no junk" holds only its fixed items. The Searching skill and Luck are the player's own
// (player.searching and player.luck, which are the raw numbers)
export function rollContents(def, roomDef) {
  const luck = story.player.attributes.luck;
  const searching = story.player.skills.searching;
  const items = (def.cnt ?? []).filter((ref) => lookup(ref)).map((ref) => ({ ref, lucky: false }));
  const result = { items, junk: 0, lucky: 0, cash: false, tries: 0 };
  if (def.noJunk !== true) {
    const junk = rollJunk(roomDef, searching);
    const lucky = rollLucky(roomDef, luck, searching);
    const cash = rollCash(roomDef, luck);
    items.push(...junk.map((ref) => ({ ref, lucky: false })));
    items.push(...lucky.refs.map((ref) => ({ ref, lucky: true })));
    if (cash) {
      items.push({ ref: cash, lucky: false });
    }
    Object.assign(result, { junk: junk.length, lucky: lucky.refs.length, cash: Boolean(cash), tries: lucky.tries });
  }
  shuffle(items);
  return result;
}

// ---------- Containers ----------

function keyOf(roomId, name) {
  return `${roomId}_${name}`;
}

// The container as the rest of the game holds it: { key, roomId, name, title, def }. def is the world data's entry, or
// null for a prop the art placed with none
export function containerFor(roomId, name) {
  const def = data.world.rooms[roomId]?.containers?.[name] ?? null;
  return { key: keyOf(roomId, name), roomId, name, title: def?.desc || PROP_TITLE, def };
}

// The lock record of a container, made empty when it has none yet
export function recordOf(container) {
  story.containers[container.key] ??= { items: null, unlocked: false, broken: false };
  return story.containers[container.key];
}

// "open" for a container anyone may search, "locked" for one with a lock still shut, "broken" for one whose lock was
// forced and lost its contents
export function lockState(container) {
  const record = story.containers[container.key];
  if (record?.broken) {
    return "broken";
  }
  return container.def?.locked === true && !record?.unlocked ? "locked" : "open";
}

// Whether a container has been searched and has nothing left (checkContEmpty F4:13819), or is a prop
function isEmpty(container) {
  const items = story.containers[container.key]?.items;
  return !container.def || (Array.isArray(items) && items.length === 0);
}

// The contents of a container, rolled the first time and then the same list every time. Returns the list still inside
export function searchContainer(roomId, name) {
  const container = containerFor(roomId, name);
  if (!container.def) {
    return [];
  }
  const record = recordOf(container);
  if (Array.isArray(record.items)) {
    return record.items;
  }
  const rolled = rollContents(container.def, data.world.rooms[roomId]);
  record.items = rolled.items;
  addXP(searchXP(), { reason: "search" });
  count("search");
  for (let n = 0; n < rolled.tries; n += 1) {
    count("luckyFind");
  }
  note("search", container, { items: rolled.items.map((each) => each.ref), lucky: rolled.lucky });
  return record.items;
}

// ---------- The panel ----------

function idOf(item) {
  if (!ids.has(item)) {
    serial += 1;
    ids.set(item, serial);
  }
  return ids.get(item);
}

function toRow(item) {
  const info = lookup(item.ref);
  return { key: idOf(item), label: info.name.toUpperCase(), value: String(info.weight), marked: item.lucky, item };
}

function roundTenth(value) {
  return Math.round(value * 10) / 10;
}

function insideWeight() {
  return roundTenth(view.items.reduce((sum, item) => sum + lookup(item.ref).weight, 0));
}

function refreshTop() {
  setText(view.clip.child("currentWeight"), `${roundTenth(weight())}/${carry()} Ibs`);
  setText(view.clip.child("totalWeight"), `${insideWeight()} Ibs`);
}

// The item name, kept to its box by drawing it smaller, a little lower for each step
function setName(field, text) {
  setText(field, text);
  const smaller = Math.max(0, Math.ceil(field.def.size - field.sizeFor(text)));
  field.y = NAME_TOP + smaller * NAME_STEP;
}

// What the right side shows for the row lit, or for nothing
function showInfo(item) {
  const clip = view.clip;
  const info = item ? lookup(item.ref) : null;
  setName(clip.child("itemName"), info ? info.name.toUpperCase() : "");
  setText(clip.child("desc"), info?.desc ?? "");
  const icon = clip.child("itemIcon");
  icon.gotoAndStop("none");
  icon.gotoAndStop(info?.icon ?? "none");
  const fields = info ? fieldsOf(info) : ["", "", "", ""];
  fields.forEach((text, place) => setText(clip.child(`field${place + 1}`), text));
}

function refresh() {
  view.list.setRows(view.items.map(toRow));
  refreshTop();
  showInfo(view.list.hot?.row.item ?? null);
}

// One press on a row takes that item (takeSearchItem F4:14156)
function takeOne(row) {
  const at = view.items.indexOf(row.item);
  if (at < 0) {
    return;
  }
  sound.play(`sound_pickupItem${rng.random(2) + 1}`);
  view.items.splice(at, 1);
  addItem(row.item.ref, { lucky: row.item.lucky });
  note("take", view.container, { ref: row.item.ref });
  refresh();
}

// TAKE ALL takes everything when it all fits under the carry weight, and closes the panel. Otherwise it says so
// (takeAllSearchItems F4:14194, with the alert the original left out, I26). Returns whether it took them
export function takeAll() {
  if (!view) {
    return false;
  }
  if (roundTenth(weight() + insideWeight()) > carry()) {
    hud.alert(TOO_HEAVY);
    note("tooHeavy", view.container);
    return false;
  }
  const taken = view.items.splice(0, view.items.length);
  sound.play(`sound_pickupItem${rng.random(2) + 1}`);
  for (const item of taken) {
    addItem(item.ref, { lucky: item.lucky });
  }
  note("takeAll", view.container, { refs: taken.map((each) => each.ref) });
  closePanel();
  return true;
}

function build(clip, container, items) {
  view = { clip, container, items, list: null };
  clip.position.set(page.width / 2, page.height / 2 - PANEL_LIFT);
  clip.child("itemName").fit();
  clip.child("luckyNote").visible = items.some((item) => item.lucky);
  setText(clip.child("containerName"), view.container.title.toUpperCase());
  clip.child("takeAll").setHandler("onPress", () => input.swallowPress());
  clip.child("takeAll").setHandler("onRelease", takeAll);
  clip.child("exit").setHandler("onPress", () => input.swallowPress());
  clip.child("exit").setHandler("onRelease", closePanel);
  restButtons([clip.child("takeAll"), clip.child("exit")], BUTTONS_REST_SECONDS);
  view.list = rowList(clip.child("scrollPanel").child("scrollContainer"), [], {
    art: "searchItem",
    markName: "lucky",
    rowHeight: ROW_HEIGHT,
    onSelect: (row) => showInfo(row.item),
    onAct: takeOne,
    bar: { clip: clip.child("scrollBar"), line: clip.child("scrollBarLine"), ...BAR },
  });
  refresh();
}

function finish() {
  view = null;
  hud.hidePlay(false);
  sound.play(`sound_searchClose${rng.random(2) + 1}`);
}

// Opens the search panel on a container, searching it first if it never was (showSearch F4:14096)
export function openSearch(container) {
  const items = searchContainer(container.roomId, container.name);
  help.did("search");
  sound.play(`sound_search${rng.random(2) + 1}`);
  openPanel(PANEL, { art: "int_search", setup: (clip) => build(clip, container, items), close: finish });
  // The play parts of the HUD hide behind the panel (showSearch F4:13949)
  hud.hidePlay(true);
  note("open", container, { count: items.length });
}

// A is TAKE ALL while the panel is open
function keys() {
  if (view && panelOpen(PANEL) && input.keys.pressed("KeyA")) {
    takeAll();
  }
}

// ---------- The thing in the room ----------

function containerOf(thing) {
  return containerFor(room.id, thing.name);
}

// The words for E on a container: its search, "[E] EMPTY" in grey for one with nothing left, and the lock's own words
// while a lock is shut
function wordsFor(thing) {
  const container = containerOf(thing);
  const state = lockState(container);
  if (state === "broken") {
    return { text: TEXT.broken, grey: true };
  }
  if (state === "locked") {
    return search.hooks.words?.(container) ?? TEXT.pick;
  }
  return isEmpty(container) ? { text: TEXT.empty, grey: true } : TEXT.search;
}

function useContainer(thing) {
  const container = containerOf(thing);
  const state = lockState(container);
  if (state === "broken") {
    sound.play("sound_security_break");
  } else if (state === "locked") {
    search.hooks.lock?.(container);
  } else {
    openSearch(container);
  }
}

export function initSearch(owner) {
  page = owner;
  register("cont", {
    prompt: wordsFor,
    use: useContainer,
    available: (thing) => thing.name !== STORAGE,
    look: {},
  });
  world.stage("interface", keys);
  world.onReset(() => {
    if (view) {
      hud.hidePlay(false);
    }
    view = null;
    log.length = 0;
  });
}

Object.assign(search, {
  containerFor,
  recordOf,
  lockState,
  searchContainer,
  openSearch,
  takeAll,
  rollContents,
  onCount: onSearchCount,
  get isOpen() {
    return panelOpen(PANEL);
  },
});

// Helpers for page.py checks
export const searchDebug = {
  // Searches and opens a container of the room by its name ("cont1")
  searchOpen(name) {
    openSearch(containerFor(room.id, name));
    return searchDebug.searchState();
  },

  // What the open panel shows, in words; null when it is shut
  searchState() {
    if (!view) {
      return null;
    }
    const text = (name) => view.clip.child(name).text;
    return {
      title: text("containerName"),
      carried: text("currentWeight"),
      inside: text("totalWeight"),
      rows: view.list.entries.map((each) => {
        const { label, value, marked } = each.row;
        return `${label} | ${value}${marked ? " | lucky" : ""}`;
      }),
      luckyNote: view.clip.child("luckyNote").visible,
      lit: view.list.hot ? view.list.hot.index : null,
      name: text("itemName"),
      desc: text("desc"),
      fields: [1, 2, 3, 4].map((place) => text(`field${place}`)),
      icon: view.clip.child("itemIcon").frame,
      bar: view.clip.child("scrollBar").visible,
      scroll: view.list.container.y,
      paused: world.paused,
    };
  },

  // The pointer over a row, and a press on it, by its place in the list
  searchHover(index) {
    return view.list.select(view.list.entries[index].row.key);
  },

  searchPress(index) {
    takeOne(view.list.entries[index].row);
    return searchDebug.searchState();
  },

  searchTakeAll: takeAll,

  searchClose: closePanel,

  // What a container's save record holds now
  searchRecord(name) {
    const record = story.containers[keyOf(room.id, name)];
    return record && { ...record, items: record.items?.map((each) => each.ref) ?? null };
  },

  // What the searches and takes did so far
  searchLog() {
    return log.map((each) => ({ ...each }));
  },

  // n fresh searches of a made-up container, rolled with the real rules at the player's luck and Searching. options:
  // type (the room's junk table, "anywhere"), danger, noJunk, cnt. Returns the totals
  searchRoll(n = 200, { type = CASH_ROOM, danger = 5, noJunk = false, cnt = [] } = {}) {
    const roomDef = { type, danger, safeHouse: false };
    const totals = { searches: n, withJunk: 0, junkItems: 0, withLucky: 0, luckyItems: 0, withCash: 0, items: 0 };
    for (let i = 0; i < n; i += 1) {
      const found = rollContents({ cnt, noJunk }, roomDef);
      totals.withJunk += found.junk > 0 ? 1 : 0;
      totals.junkItems += found.junk;
      totals.withLucky += found.lucky > 0 ? 1 : 0;
      totals.luckyItems += found.lucky;
      totals.withCash += found.cash ? 1 : 0;
      totals.items += found.items.length;
    }
    return totals;
  },
};
