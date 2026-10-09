import { mark, startHost } from "./host.js";
import { request } from "./sdk.js";
import { FrameRate } from "./fps.js";
import { MenuSounds } from "./sounds.js";

const TAB_NAMES = { look: "My look", order: "My order", server: "This server", defaults: "Defaults" };
// Each look tab edits one saved level and falls back to the levels before it
const LEVELS = ["global", "guild", "user"];
const TAB_LEVEL = { defaults: "global", server: "guild", look: "user" };
// Tabs with game on/off switches: the state list they come from and their heading
const SWITCHES = {
  server: { list: "switches", legend: "Activities in this server" },
  defaults: { list: "globalSwitches", legend: "Activities in every server" },
};
const FIELDS = ["theme", "layout", "accent", "background", "details", "sounds", "fps"];
const FIELD_NAMES = {
  theme: "Theme",
  layout: "Layout",
  accent: "Accent color",
  background: "Background",
  details: "Descriptions",
  sounds: "Menu sounds",
  fps: "Frame rate",
};
const CHOICES = {
  theme: [["standard", "Standard"], ["orb", "Orb"]],
  layout: [["grid", "Grid"], ["list", "List"], ["compact", "Compact"]],
  background: [["dark", "Dark"], ["darker", "Darker"], ["gradient", "Gradient"]],
  details: [[true, "Show"], [false, "Hide"]],
  sounds: [[true, "On"], [false, "Off"]],
  fps: [[true, "Show"], [false, "Hide"]],
};
const TRUE_FALSE = new Set(["details", "sounds", "fps"]);
// Settings is the orb theme's last pill, with an empty key, in place of the gear button
const SETTINGS_ITEM = { key: "", name: "Settings", description: "Change how this menu looks and the order of your games." };
const ACCENTS = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#00A8FC", "#F0B232", "#99AAB5"];

const $ = (id) => document.getElementById(id);
const clamp = (value, low, high) => Math.min(Math.max(value, low), high);
const page = {
  host: null,
  state: null,
  tab: null,
  staged: null,
  retried: false,
  selected: null,
  touch: false,
  orbScroll: 0,
  dragging: null,
};
const sounds = new MenuSounds();
const frameRate = new FrameRate();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function initial(name) {
  return (name || "?").trim().charAt(0).toUpperCase() || "?";
}

// ---------- Loading ----------

async function start() {
  mark("menu script running");
  page.host = startHost({
    onGameClosed: gameClosed,
    onSessionExpired: sessionExpired,
    // Shown until the menu loads, which hides it, in case Discord answers after all
    onDiscordSilent: (text) => showNotice(text),
  });
  bindPanel();
  bindOrb();
  // The menu shows as soon as the bot has logged the player in; Discord accepting the login finishes after
  page.host.ready.catch((e) => {
    if (page.state) {
      console.error(e);
      showNotice(`Couldn't finish logging in to Discord: ${e.message}`);
    }
  });
  try {
    await page.host.loggedIn;
  } catch (e) {
    console.error(e);
    showNotice(`Couldn't log in to Discord: ${e.message}`);
    return;
  }
  if (!page.host.inDiscord) {
    showNotice("Preview: open this from Discord to play online and to save settings.");
  }
  await loadState();
}

// The login brings the first menu with it; later loads ask the bot again
async function fetchState() {
  const login = page.host.login;
  if (login && login.menu) {
    const menu = login.menu;
    login.menu = null;
    return menu;
  }
  return request("/hub/api/menu", { session: login?.session });
}

async function loadState() {
  try {
    page.state = await fetchState();
  } catch (e) {
    if (e.status === 401 && !page.retried) {
      await sessionExpired();
    } else if (e.status === 401) {
      showNotice("Your session expired. Close this activity and open it again.");
    } else {
      showNotice(`Couldn't load the menu: ${e.message}`, loadState);
    }
    return;
  }
  page.retried = false;
  if (page.host.inDiscord) {
    hideNotice();
  }
  render();
  mark("menu shown");
  if (page.state.launch) {
    openGame(page.state.launch);
  } else {
    sounds.playFile("menu");
  }
}

// The bot restarted and forgot every session. The menu never reloads inside Discord (Discord allows one
// toolkit handshake per Activity), so it asks the still-connected toolkit for a fresh login instead.
async function sessionExpired() {
  sounds.setInMenu(true);
  closePanel();
  page.retried = true;
  try {
    await page.host.relogin();
  } catch (e) {
    console.error(e);
    showNotice("Your session expired. Close this activity and open it again.");
    return;
  }
  await loadState();
}

function showNotice(text, retry) {
  const box = $("notice");
  box.replaceChildren(el("span", "", text));
  if (retry) {
    const button = el("button", "secondary", "Try again");
    button.type = "button";
    button.addEventListener("click", retry);
    box.append(button);
  }
  box.hidden = false;
}

function hideNotice() {
  $("notice").hidden = true;
}

function openGame(key) {
  closePanel();
  page.selected = key;
  sounds.setInMenu(false);
  page.host.openGame(key);
}

function gameClosed() {
  sounds.setInMenu(true);
  render();
  sounds.play("back");
  sounds.playFile("menu");
  focusSelected();
}

// ---------- The menu ----------

function readableOn(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 ? "#111214" : "#ffffff";
}

function applyLook(look) {
  const root = document.documentElement.style;
  root.setProperty("--accent", look.accent);
  root.setProperty("--on-accent", readableOn(look.accent));
  document.body.dataset.background = look.background;
  document.body.dataset.theme = look.theme;
  sounds.setEnabled(look.theme === "orb" && look.sounds);
  frameRate.setEnabled(look.fps);
  const games = $("games");
  games.className = `games ${look.theme === "orb" ? "orb-menu" : look.layout}`;
  games.classList.toggle("no-details", !look.details);
}

function orbTheme() {
  return document.body.dataset.theme === "orb";
}

function render() {
  if (!page.state) {
    return;
  }
  applyLook(page.state.look);
  renderHeader();
  renderGames(page.state.games);
  $("gear").hidden = page.state.tabs.length === 0;
}

function renderHeader() {
  const player = page.state.player;
  let name = "Activities";
  let image = null;
  if (player && player.guildId) {
    name = player.guildName;
    image = player.guildIcon;
  } else if (player) {
    name = player.username;
    image = player.avatar;
  }
  $("who-name").textContent = name;
  const img = $("who-icon");
  const letter = $("who-letter");
  letter.textContent = initial(name);
  letter.hidden = Boolean(image);
  img.hidden = !image;
  if (image) {
    // Discord's frame may block outside images; the letter takes over when it does
    img.onerror = () => {
      img.hidden = true;
      letter.hidden = false;
    };
    img.src = image;
  }
}

function renderGames(games) {
  if (orbTheme()) {
    renderOrb(games);
    return;
  }
  $("games").replaceChildren(...(games.length ? games.map(gameCard) : [emptyState()]));
}

function cardText(game) {
  const text = el("span", "text");
  text.append(el("span", "name", game.name));
  if (game.description) {
    text.append(el("span", "desc", game.description));
  }
  return text;
}

// Grid and list cards show the thumbnail in place of the icon; compact cards keep the icon
function gameCard(game) {
  const card = el("button", "card");
  card.type = "button";
  card.dataset.key = game.key;
  if (game.thumbnail) {
    card.classList.add("has-thumb");
    card.append(thumbnail(game, () => card.classList.remove("has-thumb")));
  }
  card.append(gameIcon(game), cardText(game));
  card.addEventListener("click", () => openGame(game.key));
  return card;
}

function thumbnail(game, failed) {
  const img = el("img", "thumb");
  img.alt = "";
  img.addEventListener("error", () => {
    img.remove();
    failed();
  });
  img.src = game.thumbnail;
  return img;
}

function gameIcon(game) {
  const box = el("span", "icon");
  const letter = el("span", "", initial(game.name));
  if (!game.icon) {
    box.append(letter);
    return box;
  }
  const img = el("img");
  img.alt = "";
  img.addEventListener("error", () => img.replaceWith(letter));
  img.src = game.icon;
  box.append(img);
  return box;
}

// ---------- The orb theme ----------

// The pills sit like pods on a ring around the orb, this far apart. A phone gets a plain list instead
const ORB_ROW = 60;
// How far the scroll wheel turns before the selection moves one pill
const WHEEL_STEP = 50;
const phoneSize = window.matchMedia("(max-width: 640px)");

function renderOrb(games) {
  const items = page.state.tabs.length > 0 ? [...games, SETTINGS_ITEM] : games;
  const list = el("div", "orb-list");
  list.id = "orb-list";
  list.append(...items.map(orbPill));
  const screen = el("div", "orb-screen");
  screen.id = "orb-screen";
  $("games").replaceChildren(list, orbArrow(-1), orbArrow(1), screen, ...(games.length ? [] : [emptyState()]));
  const keys = items.map((item) => item.key);
  if (!keys.includes(page.selected)) {
    page.selected = keys.length ? keys[0] : null;
  }
  const pill = selectedPill();
  if (pill) {
    selectPill(pill, true);
  }
  placePills();
  // The pills glide between places from now on, but not into their first ones
  requestAnimationFrame(() => list.classList.add("placed"));
}

function orbPill(item) {
  const pill = el("button", item.key ? "card pill" : "pill settings-pill");
  pill.type = "button";
  pill.dataset.key = item.key;
  const plate = el("span", "plate");
  plate.append(item.key ? gameIcon(item) : el("span", "icon", "⚙"), cardText(item));
  pill.append(el("span", "pod"), plate);
  pill.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "mouse") {
      pill.focus({ preventScroll: true });
    }
  });
  pill.addEventListener("focus", () => selectPill(pill, page.touch));
  pill.addEventListener("click", () => {
    sounds.play("select");
    if (item.key) {
      openGame(item.key);
    } else {
      openPanel();
    }
  });
  return pill;
}

function orbArrow(step) {
  const arrow = el("button", `orb-arrow ${step < 0 ? "up" : "down"}`);
  arrow.type = "button";
  arrow.tabIndex = -1;
  arrow.hidden = true;
  arrow.setAttribute("aria-label", step < 0 ? "Previous" : "Next");
  arrow.addEventListener("click", () => moveSelection(step));
  return arrow;
}

// Rows are evenly spaced around the orb's middle, and each pod sits on the ring at its row's height, so the
// list curves around the orb. With more pills than rows, the rows scroll to keep the selected pill in view
function placePills() {
  const pills = [...document.querySelectorAll("#games .pill")];
  if (!orbTheme() || !pills.length) {
    return;
  }
  if (phoneSize.matches) {
    pills.forEach((pill) => {
      pill.style.transform = "";
      pill.classList.remove("off-ring");
    });
    document.querySelectorAll(".orb-arrow").forEach((arrow) => (arrow.hidden = true));
    return;
  }
  const ring = document.querySelector(".orb-ring");
  const box = ring.getBoundingClientRect();
  const [cx, cy] = [box.left + box.width / 2, box.top + box.height / 2];
  // The pods sit on the middle of the tube, not its outer edge
  const radius = box.width / 2 - parseFloat(getComputedStyle(ring).borderTopWidth) / 2;
  const top = document.querySelector(".bar").getBoundingClientRect().bottom + ORB_ROW / 2;
  const reach = Math.max(0, Math.min(radius * 0.85, cy - top, window.innerHeight - ORB_ROW / 2 - cy));
  const rows = Math.min(pills.length, Math.floor((2 * reach) / ORB_ROW) + 1);
  const index = Math.max(0, pills.findIndex((pill) => pill.dataset.key === page.selected));
  page.orbScroll = clamp(clamp(page.orbScroll, index - rows + 1, index), 0, pills.length - rows);
  const spot = (row) => {
    const dy = (row - (rows - 1) / 2) * ORB_ROW;
    return [cx + Math.sqrt(Math.max(0, radius ** 2 - dy ** 2)), cy + dy];
  };
  pills.forEach((pill, i) => {
    const row = i - page.orbScroll;
    const [x, y] = spot(row);
    pill.style.transform = `translate(${x}px, ${y}px)`;
    pill.classList.toggle("off-ring", row < 0 || row >= rows);
  });
  // Each arrow sits just past the end pod it leads from
  placeArrow("up", spot(0), -1, page.orbScroll > 0);
  placeArrow("down", spot(rows - 1), 1, page.orbScroll + rows < pills.length);
}

function placeArrow(name, [x, y], side, show) {
  const arrow = document.querySelector(`.orb-arrow.${name}`);
  arrow.hidden = !show;
  arrow.style.transform = `translate(${x}px, ${y + side * ORB_ROW * 0.62}px)`;
}

function moveSelection(step) {
  const pills = [...document.querySelectorAll("#games .pill")];
  const next = pills[clamp(pills.indexOf(selectedPill()) + step, 0, pills.length - 1)];
  // On a phone the list is a plain page that scrolls, so the page follows the selection there
  if (next) {
    next.focus({ preventScroll: !phoneSize.matches });
  }
}

function selectedPill() {
  if (page.selected === null) {
    return null;
  }
  return document.querySelector(`#games .pill[data-key="${CSS.escape(page.selected)}"]`);
}

function selectPill(pill, quiet) {
  const before = document.querySelector("#games .pill.selected");
  if (pill === before) {
    return;
  }
  if (before) {
    before.classList.remove("selected");
  }
  pill.classList.add("selected");
  page.selected = pill.dataset.key;
  showOnScreen(page.state.games.find((game) => game.key === page.selected) || SETTINGS_ITEM);
  placePills();
  if (!quiet) {
    sounds.play("move");
    pulseOrb();
  }
}

function showOnScreen(item) {
  const picture = el("div", "screen-picture");
  if (item.thumbnail) {
    picture.append(thumbnail(item, () => picture.append(screenIcon(item))));
  } else {
    picture.append(screenIcon(item));
  }
  const text = el("div", "screen-text");
  text.append(el("h2", "screen-name", item.name));
  if (item.description) {
    text.append(el("p", "screen-desc", item.description));
  }
  $("orb-screen").replaceChildren(picture, text);
}

function screenIcon(item) {
  const letter = el("span", "screen-letter", item.key ? initial(item.name) : "⚙");
  if (!item.icon) {
    return letter;
  }
  const img = el("img", "screen-icon");
  img.alt = "";
  img.addEventListener("error", () => img.replaceWith(letter));
  img.src = item.icon;
  return img;
}

// Restarting the animation needs a reflow between taking the class off and putting it back
function pulseOrb() {
  const orb = $("orb");
  orb.classList.remove("pulse");
  void orb.offsetWidth;
  orb.classList.add("pulse");
}

function focusSelected() {
  const pill = orbTheme() ? selectedPill() : null;
  if (pill) {
    pill.focus({ preventScroll: true });
  }
}

// Up and down, or the scroll wheel, move between the pills like a controller. A tap opens a game without the
// move sound.
function bindOrb() {
  document.addEventListener(
    "pointerdown",
    (event) => {
      page.touch = event.pointerType === "touch";
    },
    { capture: true },
  );
  document.addEventListener("keydown", (event) => {
    page.touch = false;
    const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (!step || !orbTheme() || page.staged !== null || page.host.frame) {
      return;
    }
    event.preventDefault();
    moveSelection(step);
  });
  let turned = 0;
  document.addEventListener(
    "wheel",
    (event) => {
      if (!orbTheme() || page.staged !== null || page.host.frame || phoneSize.matches) {
        return;
      }
      event.preventDefault();
      // A mouse wheel moves one pill per notch; a touchpad's many small turns add up to the same
      turned += event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 33 : event.deltaY;
      if (Math.abs(turned) >= WHEEL_STEP) {
        moveSelection(Math.sign(turned));
        turned = 0;
      }
    },
    { passive: false },
  );
  window.addEventListener("resize", placePills);
}

// The included games are always installed, so an empty menu usually means games were turned off
function emptyState() {
  const box = el("div", "empty");
  box.append(el("p", "", "No games to play here yet."));
  if (page.state.tabs.includes("server")) {
    const help = "Turn games on in Settings, or install a game cog. Making your own? See DEVELOPERS.md in the ActivityHub cog.";
    box.append(el("p", "", help));
  }
  return box;
}

// ---------- Settings panel ----------

function bindPanel() {
  $("gear").addEventListener("click", openPanel);
  $("close").addEventListener("click", closeByPlayer);
  $("scrim").addEventListener("click", closeByPlayer);
  $("save").addEventListener("click", save);
  $("reset").addEventListener("click", reset);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeByPlayer();
    }
  });
  $("panel").inert = true;
}

function closeByPlayer() {
  if (page.staged === null) {
    return;
  }
  sounds.play("back");
  closePanel();
  focusSelected();
}

function openPanel() {
  selectTab(page.state.tabs[0]);
  document.body.classList.add("panel-open");
  $("panel").inert = false;
  $("panel").setAttribute("aria-hidden", "false");
}

// Closing drops unsaved edits: the menu goes back to the saved state
function closePanel() {
  if (page.staged === null) {
    return;
  }
  document.body.classList.remove("panel-open");
  $("panel").inert = true;
  $("panel").setAttribute("aria-hidden", "true");
  page.tab = null;
  page.staged = null;
  render();
}

function selectTab(tab) {
  page.tab = tab;
  page.staged = stagedFrom(tab);
  status("");
  renderPanel();
}

function stagedFrom(tab) {
  const state = page.state;
  if (tab === "order") {
    return { order: state.games.map((game) => game.key), cleared: false };
  }
  const staged = { look: { ...state.looks[TAB_LEVEL[tab]] } };
  if (tab in SWITCHES) {
    staged.disabled = state[SWITCHES[tab].list].filter((game) => !game.on).map((game) => game.key);
  }
  return staged;
}

// What a look tab falls back to: the built-in look plus the levels before the tab's own
function inherited(tab) {
  const looks = page.state.looks;
  const below = LEVELS.slice(0, LEVELS.indexOf(TAB_LEVEL[tab]));
  return Object.assign({}, looks.builtin, ...below.map((level) => looks[level]));
}

// The preview leaves out levels after the tab's own, so an admin sees the server look even if they set their own
function previewLook() {
  return { ...inherited(page.tab), ...page.staged.look };
}

function preview() {
  if (page.tab === "order") {
    applyLook(page.state.look);
    const byKey = new Map(page.state.games.map((game) => [game.key, game]));
    renderGames(page.staged.order.map((key) => byKey.get(key)).filter(Boolean));
  } else {
    applyLook(previewLook());
    renderGames(page.state.games);
  }
}

function renderPanel() {
  $("tabs").replaceChildren(...page.state.tabs.map(tabButton));
  const body = $("tab-body");
  if (page.tab === "order") {
    body.replaceChildren(orderEditor());
  } else {
    body.replaceChildren(...lookEditor(), ...(page.tab in SWITCHES ? [switchEditor()] : []));
  }
  preview();
}

function tabButton(tab) {
  const button = el("button", "tab", TAB_NAMES[tab]);
  button.type = "button";
  button.dataset.tab = tab;
  button.setAttribute("role", "tab");
  button.setAttribute("aria-selected", String(tab === page.tab));
  button.addEventListener("click", () => selectTab(tab));
  return button;
}

function refocus(selector) {
  const target = document.querySelector(selector);
  if (target && !target.disabled) {
    target.focus();
  }
}

function status(text) {
  $("panel-status").textContent = text;
}

// ---------- Look fields ----------

// The orb theme has its own colors, background and layout, and only it has menu sounds
function lookEditor() {
  const base = inherited(page.tab);
  if (previewLook().theme === "orb") {
    return [
      choiceField("theme", base),
      choiceField("details", base),
      choiceField("sounds", base),
      choiceField("fps", base),
    ];
  }
  return [
    choiceField("theme", base),
    choiceField("layout", base),
    accentField(base),
    choiceField("background", base),
    choiceField("details", base),
    choiceField("fps", base),
  ];
}

function field(name, control) {
  const box = el("div", "field");
  const label = el("label", "field-label", FIELD_NAMES[name]);
  if (control.tagName === "SELECT") {
    label.htmlFor = control.id;
  }
  box.append(label, control);
  return box;
}

function option(value, label) {
  const node = el("option", "", label);
  node.value = value;
  return node;
}

function choiceField(name, base) {
  const select = el("select");
  select.id = `field-${name}`;
  const fallback = CHOICES[name].find(([value]) => value === base[name]);
  select.append(option("", `Default (${fallback ? fallback[1] : base[name]})`));
  for (const [value, label] of CHOICES[name]) {
    select.append(option(String(value), label));
  }
  const staged = page.staged.look[name];
  select.value = staged === undefined ? "" : String(staged);
  select.addEventListener("change", () => {
    if (select.value === "") {
      delete page.staged.look[name];
    } else {
      page.staged.look[name] = TRUE_FALSE.has(name) ? select.value === "true" : select.value;
    }
    if (name === "theme") {
      renderPanel();
      refocus("#field-theme");
    } else {
      preview();
    }
  });
  return field(name, select);
}

function sameColor(a, b) {
  return Boolean(a) && a.toLowerCase() === b.toLowerCase();
}

function accentField(base) {
  const row = el("div", "swatches");
  row.id = "field-accent";
  const current = page.staged.look.accent;
  row.append(swatch(null, base.accent, current === undefined));
  for (const color of ACCENTS) {
    row.append(swatch(color, color, sameColor(current, color)));
  }
  const picker = el("input");
  picker.type = "color";
  picker.setAttribute("aria-label", "Custom accent color");
  picker.value = (current || base.accent).toLowerCase();
  picker.addEventListener("input", () => {
    page.staged.look.accent = picker.value;
    preview();
  });
  picker.addEventListener("change", renderPanel);
  row.append(picker);
  return field("accent", row);
}

function swatch(value, color, pressed) {
  const button = el("button", value === null ? "swatch default" : "swatch");
  button.type = "button";
  button.dataset.swatch = value === null ? "default" : value;
  button.style.backgroundColor = color;
  button.title = value === null ? `Default (${color})` : color;
  button.setAttribute("aria-label", button.title);
  button.setAttribute("aria-pressed", String(pressed));
  button.addEventListener("click", () => {
    if (value === null) {
      delete page.staged.look.accent;
    } else {
      page.staged.look.accent = value;
    }
    renderPanel();
    refocus(`.swatch[data-swatch="${button.dataset.swatch}"]`);
  });
  return button;
}

// ---------- Order and server switches ----------

function orderEditor() {
  const list = el("ol", "order");
  const names = new Map(page.state.games.map((game) => [game.key, game.name]));
  page.staged.order.forEach((key, index) => list.append(orderRow(key, names.get(key), index)));
  if (!page.staged.order.length) {
    list.append(el("li", "empty", "No activities to arrange yet."));
  }
  return list;
}

function orderRow(key, name, index) {
  const row = el("li", "order-row");
  row.draggable = true;
  row.dataset.key = key;
  const handle = el("span", "handle", "⠿");
  handle.setAttribute("aria-hidden", "true");
  const last = page.staged.order.length - 1;
  row.append(
    handle,
    el("span", "order-name", name),
    moveButton("up", `Move ${name} up`, index, index - 1, index === 0),
    moveButton("down", `Move ${name} down`, index, index + 1, index === last),
  );
  row.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", String(index));
    page.dragging = index;
    row.classList.add("dragging");
  });
  row.addEventListener("dragend", () => {
    page.dragging = null;
    row.classList.remove("dragging");
  });
  row.addEventListener("dragover", (event) => event.preventDefault());
  row.addEventListener("drop", (event) => {
    event.preventDefault();
    // Only a row dragged from this list moves, not a file or text dropped from elsewhere
    if (page.dragging !== null) {
      moveGame(page.dragging, index);
    }
  });
  return row;
}

function moveButton(direction, label, from, to, disabled) {
  const button = el("button", "icon-button", direction === "up" ? "↑" : "↓");
  button.type = "button";
  button.dataset.move = direction;
  button.setAttribute("aria-label", label);
  button.disabled = disabled;
  button.addEventListener("click", () => moveGame(from, to, direction));
  return button;
}

function moveGame(from, to, direction) {
  const order = page.staged.order;
  if (Number.isNaN(from) || to < 0 || to >= order.length || from === to) {
    return;
  }
  const [key] = order.splice(from, 1);
  order.splice(to, 0, key);
  page.staged.cleared = false;
  renderPanel();
  if (direction) {
    refocus(`.order-row[data-key="${CSS.escape(key)}"] [data-move="${direction}"]`);
  }
}

function switchEditor() {
  const { list, legend } = SWITCHES[page.tab];
  const switches = page.state[list];
  const box = el("fieldset", "switches");
  box.append(el("legend", "field-label", legend));
  for (const game of switches) {
    const input = el("input");
    input.type = "checkbox";
    input.dataset.key = game.key;
    input.checked = !page.staged.disabled.includes(game.key);
    input.addEventListener("change", () => {
      const off = new Set(page.staged.disabled);
      if (input.checked) {
        off.delete(game.key);
      } else {
        off.add(game.key);
      }
      page.staged.disabled = [...off];
    });
    const label = el("label", "switch");
    label.append(input, el("span", "", game.name));
    box.append(label);
  }
  if (!switches.length) {
    box.append(el("p", "", "No activities installed yet."));
  }
  return box;
}

// ---------- Save and reset ----------

function saveBody() {
  const body = { tab: page.tab };
  if (page.tab === "order") {
    // After Reset no order means "alphabetical", so games installed later also land in order. An empty list
    // can't mean that: it is what a server with every game off sends
    body.order = page.staged.cleared ? null : page.staged.order;
  } else {
    body.look = Object.fromEntries(FIELDS.map((name) => [name, name in page.staged.look ? page.staged.look[name] : null]));
  }
  if (page.tab in SWITCHES) {
    body.disabled = page.staged.disabled;
  }
  return body;
}

async function save() {
  status("Saving…");
  try {
    page.state = await request("/hub/api/settings", { body: saveBody(), session: page.host.login?.session });
  } catch (e) {
    if (e.status === 401) {
      await sessionExpired();
      return;
    }
    status(e.message);
    return;
  }
  // The panel may have closed while the save was on its way
  if (page.tab === null) {
    render();
    return;
  }
  page.staged = stagedFrom(page.tab);
  renderPanel();
  status("Saved.");
}

// Reset is staged like any other edit: it shows the level above and saves nothing until Save
function reset() {
  if (page.tab === "order") {
    const games = [...page.state.games].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    page.staged.order = games.map((game) => game.key);
    page.staged.cleared = true;
  } else {
    page.staged.look = {};
  }
  renderPanel();
  status("Reset. Save to keep it.");
}

start();
