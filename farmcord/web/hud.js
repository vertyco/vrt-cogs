// Everything drawn in HTML over the farm: the always-on HUD (FarmCoins, level, season and weather, the sound
// switches), the room's name and exit buttons, the tool bar and its pickers, toasts, the "while you were away"
// summary, level-up popups, and the panel and yes-or-no boxes the rooms open.
import { ROOMS } from "./rooms.js";

const TOAST_MS = 4500;
const MOST_TOASTS = 4;
const SEASONS = { spring: "Spring", summer: "Summer", autumn: "Autumn", winter: "Winter" };
const WEATHER = { sun: "Sunny", rain: "Rain", snow: "Snow" };
const ARROWS = {
  left: "M15 5 L8 12 L15 19",
  right: "M9 5 L16 12 L9 19",
  up: "M5 15 L12 8 L19 15",
  down: "M5 9 L12 16 L19 9",
};
const CROP_NEWS = { ripe: "are ripe", dried: "dried out", withered: "withered", rotted: "rotted" };
const ANIMAL_NEWS = { sickly: "is sickly", malnourished: "is malnourished", healed: "is healthy again", died: "died" };
const UNLOCK_KINDS = {
  crop: "Crop",
  animal: "Animal",
  tool: "Tool",
  plot: "Plot",
  storage: "Storage",
  room: "Room",
  cosmetic: "Looks",
};

// What the seed and feed buttons offer: what the player owns, with how many
export const CHOICES = {
  seed: {
    title: "Seeds",
    empty: "You have no seeds. Buy some at the Market.",
    list: (state, catalog) =>
      owned(state, "seed:").map(([key, item]) => ({
        key,
        name: cropName(catalog, key),
        count: item.quantity,
        note: growNote(catalogEntry(catalog.crops, key.slice(5)), state.season.name),
      })),
  },
  feed: {
    title: "Feed",
    empty: "You have no feed. Buy some at the Market, or grow a feed crop.",
    list: (state, catalog) => [
      ...owned(state, "feed:").map(([key, item]) => ({
        key,
        name: `${catalogEntry(catalog.animals, key.slice(5)).name} feed`,
        count: item.quantity,
      })),
      ...owned(state, "crop:")
        .filter(([key]) => catalogEntry(catalog.crops, key.split(":")[1]).feed)
        .map(([key, item]) => ({ key, name: cropName(catalog, key), count: item.quantity, note: "Feeds any animal" })),
    ],
  },
};

// How long a seed planted now takes to ripen: out of its seasons it grows at half speed
export function growNote(crop, season) {
  const inSeason = crop.seasons.includes(season);
  const time = duration(crop.grow_time * (inSeason ? 1 : 2));
  return inSeason ? `Grows in ${time}` : `Grows in ${time} (out of season)`;
}

const hud = {
  art: null,
  handlers: null,
  state: null,
  catalog: null,
  tool: { name: "hand", seed: null, feed: null },
  // Dialogs waiting for the one on screen to close: the away summary first, then each level reached
  waiting: [],
  picking: null,
};

function $(id) {
  return document.getElementById(id);
}

export function make(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

export function number(value) {
  return value.toLocaleString("en-US");
}

// A FarmCoins amount with the coin picture
export function price(coins) {
  const box = make("span", "price");
  box.append(icon("icon/coin", 22), make("b", "", number(coins)));
  return box;
}

// A time ahead, rounded up to the minute: "under a minute", "25 min", "3 h 5 min", "2 days 4 h"
export function duration(seconds) {
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 1) {
    return "under a minute";
  }
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  }
  const days = Math.floor(hours / 24);
  const words = days === 1 ? "1 day" : `${days} days`;
  return hours % 24 ? `${words} ${hours % 24} h` : words;
}

export function catalogEntry(list, key) {
  return list.find((entry) => entry.key === key) || { key, name: key };
}

// "Wildflowers", or "Wildflowers (exceptional)" for an item key like crop:wildflowers:x
export function cropName(catalog, key) {
  const [, crop, exceptional] = key.split(":");
  const name = catalogEntry(catalog.crops, crop).name;
  return exceptional ? `${name} (exceptional)` : name;
}

function owned(state, prefix) {
  return Object.entries(state.items).filter(([key, item]) => key.startsWith(prefix) && item.quantity > 0);
}

// ---------- Setting up ----------

// handlers: back(), exit(direction), sound(), music(), tool(name)
export function setup(handlers) {
  hud.handlers = handlers;
  $("back").addEventListener("click", () => handlers.back());
  $("sound").addEventListener("click", () => handlers.sound());
  $("music").addEventListener("click", () => handlers.music());
  for (const button of document.querySelectorAll("#tools .tool")) {
    button.addEventListener("click", () => chooseTool(button.dataset.tool));
  }
  $("picker-close").addEventListener("click", () => closePicker(null));
  $("panel-close").addEventListener("click", closePanel);
  for (const id of ["away", "levelup"]) {
    $(`${id}-ok`).addEventListener("click", () => $(id).close());
    $(id).addEventListener("close", showNextDialog);
  }
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && hud.picking) {
      closePicker(null);
    }
  });
  showTool();
}

export function setArt(art) {
  hud.art = art;
  $("coin-icon").replaceChildren(icon("icon/coin", 30));
  $("xp-icon").replaceChildren(icon("icon/xp", 30));
}

// A picture from the art sheets as an HTML element, `size` CSS pixels wide. Trimmed, it is only the picture's drawn
// part, fitted into a `size` square: for pieces drawn on a big canvas, like the farmer's clothes
export function icon(key, size = 32, trimmed = false) {
  const box = make("span", "art-icon");
  const info = hud.art && hud.art.frame(key);
  box.style.width = `${size}px`;
  box.style.height = `${size}px`;
  if (!info) {
    return box;
  }
  const whole = trimmed ? info.frame : info.sourceSize;
  const k = size / Math.max(whole.w, trimmed ? whole.h : 0);
  box.style.width = `${whole.w * k}px`;
  box.style.height = `${whole.h * k}px`;
  const picture = make("span");
  Object.assign(picture.style, {
    left: `${trimmed ? 0 : info.spriteSourceSize.x * k}px`,
    top: `${trimmed ? 0 : info.spriteSourceSize.y * k}px`,
    width: `${info.frame.w * k}px`,
    height: `${info.frame.h * k}px`,
    backgroundImage: `url("${info.url}")`,
    backgroundSize: `${info.size.w * k}px ${info.size.h * k}px`,
    backgroundPosition: `${-info.frame.x * k}px ${-info.frame.y * k}px`,
  });
  box.append(picture);
  return box;
}

// ---------- The HUD ----------

export function render(state, catalog) {
  hud.state = state;
  hud.catalog = catalog;
  const { coins, level, xp, next_xp: next, level_xp: start } = state.player;
  $("coins").textContent = number(coins);
  $("level").textContent = `Level ${level}`;
  const share = next === null ? 1 : (xp - start) / (next - start);
  $("xp-fill").style.width = `${Math.min(1, Math.max(0, share)) * 100}%`;
  $("xp-text").textContent = next === null ? `${number(xp)} XP` : `${number(xp)} / ${number(next)} XP`;
  $("season").textContent = SEASONS[state.season.name];
  $("weather-name").textContent = WEATHER[state.weather.name];
  $("weather").dataset.weather = state.weather.name;
  for (const node of document.querySelectorAll(".stat")) {
    node.hidden = false;
  }
  showTool();
}

export function showSwitches(soundOn, musicOn) {
  $("sound").setAttribute("aria-pressed", String(soundOn));
  $("music").setAttribute("aria-pressed", String(musicOn));
}

// The room's name, and a button at the screen's edge for each way out that opens(room id), named for the room it leads
// to
export function showRoom(room, opens) {
  closePicker(null);
  $("room-name").textContent = room.name;
  const ways = Object.entries(room.exits).filter(([, to]) => opens(to));
  const buttons = ways.map(([direction, to]) => {
    const button = make("button", "exit");
    button.type = "button";
    button.dataset.dir = direction;
    button.setAttribute("aria-label", `Go to ${ROOMS[to].name}`);
    const arrow = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ARROWS[direction]}" /></svg>`;
    button.innerHTML = arrow;
    button.append(make("span", "", ROOMS[to].name));
    button.addEventListener("click", () => hud.handlers.exit(direction));
    return button;
  });
  $("exits").replaceChildren(...buttons);
}

export function showPlay(on) {
  $("tools").hidden = !on;
  $("exits").hidden = !on;
}

// A message over the farm instead of play: the browser preview, or a reason the farm can't open. `retry`, when given,
// runs from a Try again button under the message
export function showNotice(text, retry = null) {
  $("notice-text").textContent = text;
  $("notice").hidden = !text;
  $("notice-retry").hidden = !retry;
  $("notice-retry").onclick = retry;
}

// ---------- The tool bar ----------

// What a tap does: { name: "hoe", "can", "seed", "feed" or "hand", item: the seed or feed key for those two }
export function tool() {
  const { name } = hud.tool;
  return { name, item: name === "seed" || name === "feed" ? hud.tool[name] : null };
}

async function chooseTool(name) {
  hud.handlers.tool(name);
  if (name !== "seed" && name !== "feed") {
    hud.tool.name = name;
    showTool();
    return;
  }
  const choices = hud.state ? CHOICES[name].list(hud.state, hud.catalog) : [];
  const key = await pick(CHOICES[name].title, choices, CHOICES[name].empty);
  if (key) {
    hud.tool = { ...hud.tool, name, [name]: key };
    showTool();
  }
}

function showTool() {
  for (const button of document.querySelectorAll("#tools .tool")) {
    button.setAttribute("aria-pressed", String(button.dataset.tool === hud.tool.name));
  }
  const state = hud.state;
  if (!state || !hud.art) {
    return;
  }
  // A chosen seed or feed that ran out is dropped, so the button shows what is left
  for (const name of ["seed", "feed"]) {
    if (hud.tool[name] && !state.items[hud.tool[name]]) {
      hud.tool[name] = null;
      if (hud.tool.name === name) {
        hud.tool.name = "hand";
        showTool();
        return;
      }
    }
  }
  toolPicture("hoe", `icon/hoe_${state.tools.hoe}`, "");
  toolPicture("can", `icon/can_${state.tools.can}`, `${state.tools.water}/${state.tools.capacity}`);
  const seed = hud.tool.seed;
  toolPicture("seed", `icon/${seed || "seed:wildflowers"}`, seed ? number(state.items[seed].quantity) : "");
  const feed = hud.tool.feed;
  toolPicture("feed", `icon/${feed || "feed:chicken"}`, feed ? number(state.items[feed].quantity) : "");
}

function toolPicture(name, key, badge) {
  const button = document.querySelector(`#tools .tool[data-tool="${name}"]`);
  button.querySelector(".picture").replaceChildren(icon(key, 40));
  const count = button.querySelector(".badge");
  count.textContent = badge;
  count.hidden = !badge;
}

// A popup of choices over the tool bar: [{ key, name, count, note }]. Resolves with the chosen key, or null when
// it closes without one
export function pick(title, choices, emptyText) {
  closePicker(null);
  $("picker-title").textContent = title;
  const items = choices.map((choice) => {
    const button = make("button", "choice");
    button.type = "button";
    button.dataset.key = choice.key;
    const words = make("span", "words");
    words.append(make("b", "", choice.name));
    if (choice.note) {
      words.append(make("small", "", choice.note));
    }
    button.append(icon(`icon/${choice.key}`, 36), words);
    if (choice.count !== undefined) {
      button.append(make("span", "count", number(choice.count)));
    }
    button.addEventListener("click", () => closePicker(choice.key));
    const item = make("li");
    item.append(button);
    return item;
  });
  $("picker-list").replaceChildren(...items);
  $("picker-empty").textContent = choices.length ? "" : emptyText;
  $("picker-empty").hidden = Boolean(choices.length);
  $("picker").hidden = false;
  return new Promise((resolve) => {
    hud.picking = resolve;
  });
}

function closePicker(key) {
  $("picker").hidden = true;
  const resolve = hud.picking;
  hud.picking = null;
  if (resolve) {
    resolve(key);
  }
}

// ---------- Toasts and news ----------

// A short message over the farm that leaves on its own. `content` is text, or elements like a harvest's popup. The
// toasts are a popover, shown again with each one so they sit over any box open on the farm, like the shop
export function toast(content, kind = "") {
  const box = $("toasts");
  const node = make("p", `toast ${kind}`.trim());
  node.append(content);
  box.append(node);
  while (box.children.length > MOST_TOASTS) {
    box.firstElementChild.remove();
  }
  if (box.showPopover) {
    box.hidePopover();
    box.showPopover();
  }
  setTimeout(() => node.remove(), TOAST_MS);
}

function animalName(catalog, species) {
  return catalogEntry(catalog.animals, species).name.toLowerCase();
}

// One event as a line of news. Lines with the same key in a row merge, so nine spots ripening make one line
function newsFor(event, catalog) {
  if (CROP_NEWS[event.kind]) {
    const crop = catalogEntry(catalog.crops, event.crop).name;
    const text = `${crop} in Plot ${event.plot} ${CROP_NEWS[event.kind]}`;
    return { key: `${event.kind}:${event.plot}:${event.crop}`, text: (n) => (n > 1 ? `${text} (${n} spots)` : text) };
  }
  if (ANIMAL_NEWS[event.kind]) {
    const text = `Your ${animalName(catalog, event.species)} ${ANIMAL_NEWS[event.kind]}`;
    return { key: `${event.kind}:${event.species}`, text: (n) => (n > 1 ? `${text} ×${n}` : text) };
  }
  if (event.kind === "grown") {
    const kind = `${event.exceptional ? "exceptional " : ""}${animalName(catalog, event.species)}`;
    return { key: `grown:${event.animal}`, text: () => `Your ${kind} grew up (+${number(event.xp)} XP)` };
  }
  if (event.kind === "born") {
    const babies = event.babies === 1 ? "a baby" : `${event.babies} babies`;
    const waiting = event.waiting ? `, ${event.waiting} waiting in the farmhouse` : "";
    const text = `Your ${animalName(catalog, event.species)} had ${babies}${waiting} (+${number(event.xp)} XP)`;
    return { key: `born:${event.mother}:${event.at}`, text: () => text };
  }
  if (event.kind === "achievement") {
    const badge = catalogEntry(catalog.achievements, event.key).name;
    const text = `Badge earned: ${badge}! +${number(event.coins)} FarmCoins, +${number(event.xp)} XP`;
    return { key: `achievement:${event.key}`, text: () => text };
  }
  return null;
}

// The events as news lines in time order, levels left out (they get their own popup): [{ text, at }]
export function newsLines(events, catalog) {
  const lines = [];
  const sorted = [...events].sort((a, b) => a.at - b.at);
  for (const event of sorted) {
    const news = newsFor(event, catalog);
    if (!news) {
      continue;
    }
    const last = lines[lines.length - 1];
    if (last && last.key === news.key) {
      last.count += 1;
      last.at = event.at;
    } else {
      lines.push({ ...news, count: 1, at: event.at });
    }
  }
  return lines.map((line) => ({ text: line.text(line.count), at: line.at }));
}

function ago(seconds) {
  if (seconds < 60) {
    return "just now";
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)} min ago`;
  }
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)} h ago`;
  }
  const days = Math.floor(seconds / 86400);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

// What happened while the farm was closed, then a popup for each level reached
export function showAway(events, catalog, now) {
  const lines = newsLines(events, catalog);
  if (lines.length) {
    const items = lines.map((line) => {
      const item = make("li");
      item.append(make("span", "", line.text), make("small", "", ago(now - line.at)));
      return item;
    });
    queueDialog(() => {
      $("away-lines").replaceChildren(...items);
      return $("away");
    });
  }
  showLevels(events);
}

// News an action brought: a toast for each line, a popup for each level reached
export function showNews(events, catalog) {
  for (const line of newsLines(events, catalog)) {
    toast(line.text);
  }
  showLevels(events);
}

function showLevels(events) {
  for (const event of events.filter((e) => e.kind === "level")) {
    queueDialog(() => fillLevel(event));
  }
}

function fillLevel(event) {
  $("levelup-number").textContent = String(event.level);
  $("levelup-coins").textContent = `+${number(event.coins)} FarmCoins`;
  $("levelup-open").hidden = !event.unlocks.length;
  const items = event.unlocks.map((unlock) => {
    const item = make("li");
    item.append(make("span", "tag", UNLOCK_KINDS[unlock.kind] || unlock.kind), make("span", "", unlock.name));
    return item;
  });
  $("levelup-unlocks").replaceChildren(...items);
  return $("levelup");
}

function queueDialog(open) {
  hud.waiting.push(open);
  if (!$("away").open && !$("levelup").open) {
    showNextDialog();
  }
}

function showNextDialog() {
  const open = hud.waiting.shift();
  if (open) {
    open().showModal();
  }
}

// ---------- Panels for the rooms ----------

// True while a box covers the farm, so keys and exits wait
export function covered() {
  return [...document.querySelectorAll("dialog")].some((dialog) => dialog.open);
}

// Opens the panel with a title, and returns its emptied body for the room to fill
export function openPanel(title) {
  $("panel-title").textContent = title;
  $("panel-body").replaceChildren();
  if (!$("panel").open) {
    $("panel").showModal();
  }
  return $("panel-body");
}

export function closePanel() {
  $("panel").close();
}

// A yes or no question. Resolves true for yes. While one is on screen another resolves false at once, so a double tap
// never asks twice
export function confirmBox(text, yes = "Yes", no = "No") {
  const box = $("confirm");
  if (box.open) {
    return Promise.resolve(false);
  }
  $("confirm-text").textContent = text;
  $("confirm-yes").textContent = yes;
  $("confirm-no").textContent = no;
  box.showModal();
  return new Promise((resolve) => {
    const finish = (answer) => {
      $("confirm-yes").removeEventListener("click", onYes);
      $("confirm-no").removeEventListener("click", onNo);
      box.removeEventListener("cancel", onNo);
      box.close();
      resolve(answer);
    };
    const onYes = () => finish(true);
    const onNo = () => finish(false);
    $("confirm-yes").addEventListener("click", onYes);
    $("confirm-no").addEventListener("click", onNo);
    box.addEventListener("cancel", onNo);
  });
}
