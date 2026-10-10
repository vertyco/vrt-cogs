import { mark, startHost } from "./host.js";
import { request } from "./sdk.js";
import { FrameRate } from "./fps.js";
import { MenuSounds } from "./sounds.js";
import { applyGlow, buildArm, buildOrbParts, drawWeb, gearIcon, introPills, turnArm, turnPanels } from "./orb.js";

const TAB_NAMES = { look: "My look", order: "My order", server: "This server", defaults: "Defaults" };
// Each look tab edits one saved level and falls back to the levels before it
const LEVELS = ["global", "guild", "user"];
const TAB_LEVEL = { defaults: "global", server: "guild", look: "user" };
// Tabs with game on/off switches: the state list they come from and their heading
const SWITCHES = {
  server: { list: "switches", legend: "Activities in this server" },
  defaults: { list: "globalSwitches", legend: "Activities in every server" },
};
const FIELDS = ["theme", "layout", "accent", "glow", "background", "details", "sounds", "fps"];
const FIELD_NAMES = {
  theme: "Theme",
  layout: "Layout",
  accent: "Accent color",
  glow: "Glow color",
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
  // The first look at the menu, and each return from a game, plays the menu's opening
  intro: true,
  // How far the fins around the orb have turned, in degrees
  finTurn: 0,
  // The Orb theme's tones from orb.js, and the size and color the web behind the orb was last drawn at
  tones: null,
  webDrawn: "",
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
    onStat: (text) => frameRate.setStat(text),
    onLatency: (ms) => frameRate.setLatency(ms),
    // Shown until the menu loads, which hides it, in case Discord answers after all
    onDiscordSilent: (text) => showNotice(text),
  });
  bindPanel();
  buildOrbParts();
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
  page.intro = true;
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
  if (look.theme === "orb") {
    page.tones = applyGlow(look.glow);
  }
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

// How far apart the pods sit along the ring, for a pod of size 1
const ROW_SPACING = 1.24;
// How far the scroll wheel turns before the selection moves one pill
const WHEEL_STEP = 50;
// How far a finger slides before the selection moves one pill, and before a touch counts as a slide at all
const SWIPE_STEP = 44;
const SWIPE_START = 10;
// How far the fins around the orb turn, in degrees, for each pill the selection moves, and when a menu opens
const FIN_NOTCH = 14;
const FIN_TURN = 70;

function renderOrb(games) {
  const items = page.state.tabs.length > 0 ? [...games, SETTINGS_ITEM] : games;
  const list = el("div", "orb-list");
  list.id = "orb-list";
  list.append(...items.map(orbPill));
  const screen = orbScreen();
  screen.hidden = items.length === 0;
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
  drawOrbWeb();
  if (page.intro && pill) {
    page.intro = false;
    introPills([...list.children]);
    turnPanels(null, screen.querySelector(".screen-face"), true);
    turnArm(screen.querySelector(".screen-arm"), true);
  }
  // The pills glide between places from now on, but not into their first ones
  requestAnimationFrame(() => list.classList.add("placed"));
}

// The pod holds the game's icon, or a cog for Settings, and the tab holds its name
function orbPill(item) {
  const pill = el("button", item.key ? "card pill" : "pill settings-pill");
  pill.type = "button";
  pill.dataset.key = item.key;
  const pod = el("span", "pod");
  pod.append(item.key ? gameIcon(item) : gearIcon());
  const plate = el("span", "plate");
  plate.append(cardText(item));
  pill.append(pod, plate);
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

// The selected item's panel, hanging from its arm, with the console's Select prompt under it. Keyboard players
// have Enter on the focused pill, so the prompt stays out of the tab order
function orbScreen() {
  const screen = el("div", "orb-screen");
  screen.id = "orb-screen";
  const select = el("button", "screen-select");
  select.type = "button";
  select.tabIndex = -1;
  select.append(el("span", "select-button"), el("span", "", "Select"));
  select.addEventListener("click", () => selectedPill()?.click());
  screen.append(buildArm(), el("div", "screen-faces"), select);
  return screen;
}

// Rows are evenly spaced around the orb's middle, and each pod sits on the ring at its row's height, so the
// list curves around the orb. With more pills than rows, the rows scroll to keep the selected pill in view.
// Each tab ends before the edge of the screen
function placePills() {
  const pills = [...document.querySelectorAll("#games .pill")];
  if (!orbTheme() || !pills.length) {
    return;
  }
  const ring = document.querySelector(".orb-ring");
  const box = ring.getBoundingClientRect();
  const [cx, cy] = [box.left + box.width / 2, box.top + box.height / 2];
  // The pods sit on the middle of the tube, not its outer edge
  const radius = box.width / 2 - parseFloat(getComputedStyle(ring).borderTopWidth) / 2;
  const pod = pills[0].querySelector(".pod").offsetWidth;
  const row = pod * ROW_SPACING;
  // A phone held upright keeps the bottom of the screen for the panel. The rows leave room past their ends for
  // the arrows
  const room = parseFloat(getComputedStyle(document.body).getPropertyValue("--screen-room")) || 0;
  const top = document.querySelector(".bar").getBoundingClientRect().bottom + row / 2;
  const bottom = window.innerHeight - room - row * 0.8;
  const reach = Math.max(0, Math.min(radius * 0.85, cy - top, bottom - cy));
  const rows = Math.min(pills.length, Math.floor((2 * reach) / row) + 1);
  const index = Math.max(0, pills.findIndex((pill) => pill.dataset.key === page.selected));
  page.orbScroll = clamp(clamp(page.orbScroll, index - rows + 1, index), 0, pills.length - rows);
  const spot = (at) => {
    const dy = (at - (rows - 1) / 2) * row;
    return [cx + Math.sqrt(Math.max(0, radius ** 2 - dy ** 2)), cy + dy];
  };
  // The selected tab leans out a little further than the rest, so it gets that much room too
  const edge = window.innerWidth - parseFloat(getComputedStyle($("menu")).paddingRight) - 22;
  pills.forEach((pill, i) => {
    const at = i - page.orbScroll;
    const [x, y] = spot(at);
    pill.style.transform = `translate(${x}px, ${y}px)`;
    pill.style.maxWidth = `${edge - x + pod / 2}px`;
    pill.classList.toggle("off-ring", at < 0 || at >= rows);
  });
  // Each arrow sits just past the end pod it leads from
  placeArrow("up", spot(0), -1, page.orbScroll > 0, row);
  placeArrow("down", spot(rows - 1), 1, page.orbScroll + rows < pills.length, row);
}

function placeArrow(name, [x, y], side, show, row) {
  const arrow = document.querySelector(`.orb-arrow.${name}`);
  arrow.hidden = !show;
  arrow.style.transform = `translate(${x}px, ${y + side * row * 0.62}px)`;
}

// The web is drawn around the orb in the glow color, again only when the screen's size or the color changes
function drawOrbWeb() {
  const ring = document.querySelector(".orb-ring").getBoundingClientRect();
  const drawn = [window.innerWidth, window.innerHeight, ring.left, ring.top, ring.width, page.tones.main].join();
  if (drawn === page.webDrawn) {
    return;
  }
  page.webDrawn = drawn;
  const center = [ring.left + ring.width / 2, ring.top + ring.height / 2];
  drawWeb($("orb-web"), center, ring.width * 0.36, page.tones.main);
}

function moveSelection(step) {
  const pills = [...document.querySelectorAll("#games .pill")];
  const next = pills[clamp(pills.indexOf(selectedPill()) + step, 0, pills.length - 1)];
  if (next) {
    next.focus({ preventScroll: true });
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
  const pills = [...document.querySelectorAll("#games .pill")];
  const step = Math.sign(pills.indexOf(pill) - pills.indexOf(before));
  if (before) {
    before.classList.remove("selected");
  }
  pill.classList.add("selected");
  page.selected = pill.dataset.key;
  showOnScreen(page.state.games.find((game) => game.key === page.selected) || SETTINGS_ITEM, !quiet);
  placePills();
  if (!quiet) {
    sounds.play("move");
    pulseOrb();
    turnFins(step * FIN_NOTCH);
  }
}

// The panel shows the new item at once, so the page always says what is selected. With a turn, the old panel
// turns away on the arm while the new one turns in
function showOnScreen(item, turn) {
  const faces = document.querySelector("#orb-screen .screen-faces");
  const face = screenFace(item);
  faces.querySelectorAll(".leaving").forEach((node) => node.remove());
  const old = faces.querySelector(".screen-face");
  if (!old || !turn) {
    faces.replaceChildren(face);
    return;
  }
  old.classList.add("leaving");
  old.setAttribute("aria-hidden", "true");
  faces.prepend(face);
  turnPanels(old, face, false);
  turnArm(document.querySelector("#orb-screen .screen-arm"), false);
}

function screenFace(item) {
  const face = el("div", "screen-face");
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
  face.append(picture, text);
  return face;
}

function screenIcon(item) {
  const letter = el("span", "screen-letter", item.key ? initial(item.name) : undefined);
  if (!item.key) {
    letter.append(gearIcon());
  }
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

// The fins around the orb turn and stay turned, so a long scroll winds them round like a dial
function turnFins(degrees) {
  page.finTurn += degrees;
  $("orb-fins").style.setProperty("--fin-turn", `${page.finTurn}deg`);
}

// Settings opening or closing turns the whole frame, and the arm swings round with it. Closing brings the panel
// back round on the arm, from behind where Settings stood
function turnMenu(step) {
  if (!orbTheme()) {
    return;
  }
  turnFins(step * FIN_TURN);
  turnArm(document.querySelector("#orb-screen .screen-arm"), true);
  if (step < 0) {
    turnPanels(null, document.querySelector("#orb-screen .screen-face"), true);
  }
}

function focusSelected() {
  const pill = orbTheme() ? selectedPill() : null;
  if (pill) {
    pill.focus({ preventScroll: true });
  }
}

// Up and down, the scroll wheel, or a swipe move between the pills like a controller. A tap opens a game without
// the move sound.
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
      if (!orbTheme() || page.staged !== null || page.host.frame) {
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
  // Behind a game the scene is hidden and has no size, so the menu waits to be shown again, which places it
  window.addEventListener("resize", () => {
    if (orbTheme() && page.state && !page.host.frame) {
      placePills();
      drawOrbWeb();
    }
  });
  bindSwipe();
}

// On a touch screen, sliding a finger up or down along the ring, or left and right across the screen, moves one
// pill per step. The pills follow the finger, so sliding up or left brings the next one in
function bindSwipe() {
  let swipe = null;
  document.addEventListener("pointerdown", (event) => {
    const ring = orbTheme() && page.staged === null && !page.host.frame;
    swipe = ring && event.pointerType === "touch" ? { id: event.pointerId, x: event.clientX, y: event.clientY } : null;
  });
  document.addEventListener("pointermove", (event) => {
    if (!swipe || event.pointerId !== swipe.id) {
      return;
    }
    const [dx, dy] = [event.clientX - swipe.x, event.clientY - swipe.y];
    // The first clear direction holds for the rest of the slide, so a thumb's curve doesn't switch it
    if (!swipe.axis && Math.hypot(dx, dy) >= SWIPE_START) {
      swipe.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
    }
    const steps = Math.trunc(({ x: dx, y: dy }[swipe.axis] || 0) / SWIPE_STEP);
    if (steps) {
      // Every whole step counts and the rest carries over, so a fast slide that arrives in a few big moves goes as
      // far as a slow one
      swipe[swipe.axis] += steps * SWIPE_STEP;
      // A slide sounds like the arrow keys, unlike a tap on a pill, which opens it with the select sound
      page.touch = false;
      moveSelection(-steps);
    }
  });
  for (const type of ["pointerup", "pointercancel"]) {
    document.addEventListener(type, () => (swipe = null));
  }
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
  turnMenu(1);
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
  turnMenu(-1);
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

// The orb theme has its own background and layout, its glow color in place of the accent, and only it has menu
// sounds
function lookEditor() {
  const base = inherited(page.tab);
  if (previewLook().theme === "orb") {
    return [
      choiceField("theme", base),
      colorField("glow", base),
      choiceField("details", base),
      choiceField("sounds", base),
      choiceField("fps", base),
    ];
  }
  return [
    choiceField("theme", base),
    choiceField("layout", base),
    colorField("accent", base),
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

// The accent color in the Standard theme and the glow color in the Orb theme: a default, the preset colors and
// a picker for any other
function colorField(name, base) {
  const row = el("div", "swatches");
  row.id = `field-${name}`;
  const current = page.staged.look[name];
  row.append(swatch(name, null, base[name], current === undefined));
  for (const color of ACCENTS) {
    row.append(swatch(name, color, color, sameColor(current, color)));
  }
  const picker = el("input");
  picker.type = "color";
  picker.setAttribute("aria-label", `Custom ${FIELD_NAMES[name].toLowerCase()}`);
  picker.value = (current || base[name]).toLowerCase();
  picker.addEventListener("input", () => {
    page.staged.look[name] = picker.value;
    preview();
  });
  picker.addEventListener("change", renderPanel);
  row.append(picker);
  return field(name, row);
}

function swatch(name, value, color, pressed) {
  const button = el("button", value === null ? "swatch default" : "swatch");
  button.type = "button";
  button.dataset.swatch = value === null ? "default" : value;
  button.style.backgroundColor = color;
  button.title = value === null ? `Default (${color})` : color;
  button.setAttribute("aria-label", button.title);
  button.setAttribute("aria-pressed", String(pressed));
  button.addEventListener("click", () => {
    if (value === null) {
      delete page.staged.look[name];
    } else {
      page.staged.look[name] = value;
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
