import { mark, startHost } from "./host.js";
import { request } from "./sdk.js";
import { FrameRate } from "./fps.js";
import { MenuSounds } from "./sounds.js";
import { applyGlow, buildArm, buildOrbParts, drawWeb, gearIcon, introPills, turnArm, turnPanels } from "./orb.js";
import { PressHold, avatar, elsewhereLine, icon, personRow, statusText } from "./people.js";

const TAB_NAMES = { look: "My look", order: "My order", server: "This server", payouts: "Payouts", defaults: "Defaults" };
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
// The Payouts tab's number boxes: the saved setting, its label and what one step is
const PAYOUT_FIELDS = [
  ["rate", (game, currency) => `${currency} per ${game.unit}`, "any"],
  ["cap", () => "Most per cash-in", "1"],
  ["plays", () => "Cash-ins a day", "1"],
];
const ACCENTS = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#00A8FC", "#F0B232", "#99AAB5"];
// How long the mouse rests on a card (or the keyboard on it) before its players show
const HOVER_MS = 250;
const HOVER_LEAVE_MS = 150;
const ROW_MAX = 5;
const SCREEN_MAX = 4;
// The gap kept between a list and the edge of the screen
const EDGE = 8;
// The header row's parts as menu.css draws them, to fit the row to the room: the button's padding and border, the
// first face, how much of each face after it shows, the "+N" after the last (with room for three characters), and
// the whole button when it is only a count. A little room is left over so a rounding never squeezes the name
const STACK_PAD = 16;
const FACE_FIRST = 26;
const FACE_NEXT = 20;
const FACE_MORE = 34;
const COUNT_ONLY = 64;
const FIT_SLACK = 4;
// The server's name keeps this many em of its text, or all of it when it is shorter
const NAME_KEEP_EM = 6;
// Under this width the invite pill is only its icon
const COMPACT_WIDTH = 480;
// The lists with Join buttons or a button to press: a card's players, the header's people, the Orb screen's players
const PEOPLE_LISTS = "#hover-people, #people-row, .screen-people";

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
  // Where the mouse last was, and where it was when the wheel or the arrow keys last took the selection from it
  pointer: null,
  hoverHeld: null,
  orbScroll: 0,
  // The first look at the menu, and each return from a game, plays the menu's opening
  intro: true,
  // How far the fins around the orb have turned, in degrees
  finTurn: 0,
  // The Orb theme's tones from orb.js, and the size and color the web behind the orb was last drawn at
  tones: null,
  webDrawn: "",
  dragging: null,
  // The card whose players the hover list shows, and the timer that opens or closes it
  hoverTimer: null,
  hoverKey: null,
  // Holds the people lists as they are while a press is under way in one of them
  hold: null,
  // The count each game's bubble last showed, so drawing the cards again isn't taken for a new arrival
  counts: new Map(),
  // Watches the Orb screen's size, which the people list changes
  screenWatch: null,
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
    onJoin: (key, follow) => openGame(key, follow),
    onSessionExpired: sessionExpired,
    onStat: (text) => frameRate.setStat(text),
    onLatency: (ms) => frameRate.setLatency(ms),
    // Shown until the menu loads, which hides it, in case Discord answers after all
    onDiscordSilent: (text) => showNotice(text),
  });
  bindPanel();
  buildOrbParts();
  bindOrb();
  page.hold = new PressHold((node) => Boolean(node.closest?.(PEOPLE_LISTS)), redrawPeople);
  bindHover();
  page.host.presence.listen(peopleChanged);
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
  layoutOrb();
}

function hideNotice() {
  $("notice").hidden = true;
  layoutOrb();
}

function openGame(key, follow = null) {
  closePanel();
  hideHover();
  page.selected = key;
  sounds.setInMenu(false);
  page.host.openGame(key, follow);
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
  page.host.setGames(page.state.games);
  applyLook(page.state.look);
  renderHeader();
  renderGames(page.state.games);
  $("gear").hidden = page.state.tabs.length === 0;
  peopleChanged();
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
  } else {
    $("games").replaceChildren(...(games.length ? games.map(gameCard) : [emptyState()]));
  }
  // Settings previews redraw the cards too, and the bubbles go back on them with the rest
  updateBubbles();
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
// How far the mouse moves, after the wheel or the arrow keys moved the selection, before pointing picks a pill again
const HOVER_SLACK = 12;
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
  // Pointing at a pill selects it once the mouse moves. When the list scrolls, the pills glide along the ring under
  // a still mouse, and that isn't the player pointing
  pill.addEventListener("pointermove", (event) => {
    if (event.pointerType === "mouse" && !page.hoverHeld) {
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
  // The panel grows and shrinks as faces and their lists change, and the room for it changes with the window
  page.screenWatch?.disconnect();
  // A frame later, since a fit that changes the panel's size would otherwise be seen as a loop in the observer
  page.screenWatch = new ResizeObserver(() => requestAnimationFrame(fitScreenPeople));
  page.screenWatch.observe(screen);
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
  // On a phone held upright the panel and the orb sit below the header (orb.css), so they move with it
  const header = [document.querySelector(".bar"), $("notice")].filter((node) => !node.hidden);
  const head = Math.max(...header.map((node) => node.getBoundingClientRect().bottom));
  document.body.style.setProperty("--head", `${head}px`);
  const ring = document.querySelector(".orb-ring");
  const box = ring.getBoundingClientRect();
  const [cx, cy] = [box.left + box.width / 2, box.top + box.height / 2];
  // The pods sit on the middle of the tube, not its outer edge
  const radius = box.width / 2 - parseFloat(getComputedStyle(ring).borderTopWidth) / 2;
  const pod = pills[0].querySelector(".pod").offsetWidth;
  let row = pod * ROW_SPACING;
  // The rows stay clear of the header, of the panel where it sits above the ring (a phone held upright) and of
  // the bottom edge, with room past their ends for the arrows
  const screen = $("orb-screen").getBoundingClientRect();
  const top = screen.height && screen.bottom < cy ? screen.bottom + row * 0.9 : head + row / 2;
  const bottom = window.innerHeight - parseFloat(getComputedStyle($("menu")).paddingBottom) - row * 0.9;
  const reach = Math.max(0, Math.min(radius * 0.85, cy - top, bottom - cy));
  const rows = Math.min(pills.length, Math.floor((2 * reach) / row) + 1);
  // When every pill fits, the rows spread out along the ring, as far as the layout allows (orb.css)
  const spread = parseFloat(getComputedStyle(document.body).getPropertyValue("--row-spread"));
  if (rows === pills.length && rows > 1 && spread) {
    row = Math.min(pod * spread, (2 * reach) / (rows - 1));
  }
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
  // A list opened from another pod's bubble belongs to that pod
  if (page.hoverKey && page.hoverKey !== page.selected) {
    hideHover();
  }
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
    fitScreenPeople();
    return;
  }
  old.classList.add("leaving");
  old.setAttribute("aria-hidden", "true");
  faces.prepend(face);
  fitScreenPeople();
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
  if (item.key) {
    const people = el("div", "screen-people");
    people.dataset.key = item.key;
    people.tabIndex = -1;
    fillScreenPeople(people);
    text.append(people);
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
  // Runs before the pill's own listener, so the move that ends a hold also selects the pill under the mouse
  document.addEventListener(
    "pointermove",
    (event) => {
      if (event.pointerType !== "mouse") {
        return;
      }
      page.pointer = [event.clientX, event.clientY];
      const held = page.hoverHeld;
      if (held && Math.hypot(event.clientX - held[0], event.clientY - held[1]) >= HOVER_SLACK) {
        holdHover(null);
      }
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
    holdHover(page.pointer);
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
      holdHover([event.clientX, event.clientY]);
      // A mouse wheel moves one pill per notch; a touchpad's many small turns add up to the same
      turned += event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 33 : event.deltaY;
      if (Math.abs(turned) >= WHEEL_STEP) {
        moveSelection(Math.sign(turned));
        turned = 0;
      }
    },
    { passive: false },
  );
  window.addEventListener("resize", layoutOrb);
  bindSwipe();
}

// The wheel and the arrow keys keep the selection until the mouse moves away from where it was, so a hand resting
// on the mouse can scroll the whole list. Meanwhile the pill under the mouse doesn't light up, only the selected one
function holdHover(at) {
  page.hoverHeld = at;
  document.body.classList.toggle("hover-held", Boolean(at));
}

// The screen's size and the header place the ring and the panel. Behind a game the scene is hidden and has no
// size, so the menu waits to be shown again, which places it
function layoutOrb() {
  if (orbTheme() && page.state && !page.host.frame) {
    placePills();
    drawOrbWeb();
    fitScreenPeople();
  }
}

// On a touch screen, sliding a finger up or down along the ring, or left and right across the screen, moves one
// pill per step. The selection follows the finger, so sliding down or right moves to the next one
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
      moveSelection(steps);
    }
  });
  // Some phones still scroll or bounce the page under a finger, which would take the slide away from the ring,
  // so a slide holds the page still itself
  document.addEventListener(
    "touchmove",
    (event) => {
      if (swipe) {
        event.preventDefault();
      }
    },
    { passive: false },
  );
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

// ---------- Who's here ----------

function menuPeople() {
  return page.host.presence.view(null);
}

// The others in this window playing a game
function playing(key) {
  return menuPeople().filter((person) => !person.you && person.game === key);
}

function joinPerson(person) {
  page.host.join(person);
}

// What a person's row shows
function rowSignature(person) {
  return [person.id, person.name, person.avatar, statusText(person), Boolean(person.away)];
}

// Fills a box with the parts `build` makes, unless `shown` says it already has them. Lists come up to 4 times a
// second, mostly with new game data nobody sees, and drawing a list again reloads its pictures
function drawPeople(box, shown, build) {
  if (box.dataset.shown === shown) {
    return false;
  }
  // Keyboard focus on a button in the box goes back to that button, or to the box itself once that person has gone
  const focused = box !== document.activeElement && box.contains(document.activeElement) ? document.activeElement : null;
  box.dataset.shown = shown;
  box.replaceChildren(...build());
  if (focused) {
    const same = focused.dataset.join === undefined ? `.${focused.classList[0]}` : `[data-join="${CSS.escape(focused.dataset.join)}"]`;
    (box.querySelector(same) || box).focus();
  }
  return true;
}

function peopleChanged() {
  if (!page.state) {
    return;
  }
  updateBubbles();
  page.hold.request();
}

// The lists drawn again from the newest people. Buttons in them wait for a press to end first (page.hold)
function redrawPeople() {
  renderPeopleRow();
  const boxes = document.querySelectorAll("#orb-screen .screen-face:not(.leaving) .screen-people");
  if ([...boxes].map(fillScreenPeople).includes(true)) {
    fitScreenPeople();
  }
  if (page.hoverKey) {
    showHover(page.hoverKey);
  }
}

// The count on each card's corner (an Orb pod's, in that theme), changed in place so nothing else redraws
function updateBubbles() {
  for (const card of document.querySelectorAll("#games .card[data-key]")) {
    const key = card.dataset.key;
    const count = playing(key).length;
    const holder = card.querySelector(".pod") || card;
    let bubble = holder.querySelector(".bubble");
    // A title runs clear of the bubble in the layouts where it reaches that far
    card.classList.toggle("has-bubble", count > 0);
    if (!count) {
      bubble?.remove();
      page.counts.delete(key);
      continue;
    }
    if (!bubble) {
      bubble = el("span", "bubble");
      bubble.addEventListener("click", (event) => bubbleTapped(event, key));
      holder.append(bubble);
    }
    if ((page.counts.get(key) || 0) < count) {
      // Restarting the pop needs a reflow between taking the class off and putting it back
      bubble.classList.remove("pop");
      void bubble.offsetWidth;
      bubble.classList.add("pop");
    }
    page.counts.set(key, count);
    bubble.textContent = count > 9 ? "9+" : String(count);
    const game = page.state.games.find((item) => item.key === key);
    bubble.setAttribute("aria-label", `${count} playing ${game ? game.name : key}`);
  }
}

// Whether the Orb screen is showing this game's players right now. It has no room for them on a small screen
function screenListsPlayers(key) {
  const box = document.querySelector(`#orb-screen .screen-face:not(.leaving) .screen-people[data-key="${CSS.escape(key)}"]`);
  return Boolean(box && box.getClientRects().length);
}

// The bubble shows the list instead of opening the game. Where the Orb screen lists the selected game's players, a
// tap there only selects the pod
function bubbleTapped(event, key) {
  event.preventDefault();
  event.stopPropagation();
  const card = event.currentTarget.closest(".card");
  if (orbTheme()) {
    card.focus({ preventScroll: true });
    if (screenListsPlayers(key)) {
      return;
    }
  }
  if (page.hoverKey === key) {
    hideHover();
  } else {
    showHover(key, card);
  }
}

function bindHover() {
  const games = $("games");
  const box = $("hover-people");
  games.addEventListener("pointerover", (event) => {
    const card = event.target.closest(".card[data-key]");
    if (event.pointerType === "mouse" && card && !orbTheme()) {
      hoverSoon(card);
    }
  });
  games.addEventListener("pointerout", (event) => {
    const card = event.target.closest(".card[data-key]");
    if (event.pointerType === "mouse" && card && !card.contains(event.relatedTarget) && !box.contains(event.relatedTarget)) {
      hoverLeft();
    }
  });
  games.addEventListener("focusin", (event) => {
    const card = event.target.closest(".card[data-key]");
    if (card && !orbTheme()) {
      hoverSoon(card);
    }
  });
  games.addEventListener("focusout", (event) => {
    if (!box.contains(event.relatedTarget)) {
      hoverLeft();
    }
  });
  // Only a mouse leaves a list by moving away: a finger lifted from it, after a scroll, has not gone anywhere
  box.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "mouse") {
      clearTimeout(page.hoverTimer);
    }
  });
  box.addEventListener("pointerleave", (event) => {
    if (event.pointerType === "mouse") {
      hoverLeft();
    }
  });
  // The list follows the last card in the page, so Tab goes from that card into its Join buttons. A timer from the
  // card that focus just left would otherwise swap or close the list under the keyboard, and the list closes when
  // focus leaves it for anything but a card
  box.addEventListener("focusin", () => clearTimeout(page.hoverTimer));
  box.addEventListener("focusout", (event) => {
    if (!box.contains(event.relatedTarget)) {
      hoverLeft();
    }
  });
  // A long list scrolls, so the Orb's wheel and swipe, which move its selection, leave presses and turns in it alone
  box.addEventListener("pointerdown", (event) => event.stopPropagation());
  box.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
  // The header row is fitted to the width of the name, the name's font arrives after the first draw, and the window
  // changes size
  window.addEventListener("resize", () => page.hold.request());
  document.fonts?.addEventListener("loadingdone", () => page.hold.request());
  document.addEventListener("pointerdown", (event) => {
    if (page.hoverKey && !box.contains(event.target) && !event.target.closest(".bubble")) {
      hideHover();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideHover();
    }
  });
}

function hoverSoon(card) {
  clearTimeout(page.hoverTimer);
  if (page.hoverKey !== card.dataset.key) {
    page.hoverTimer = setTimeout(() => showHover(card.dataset.key, card), HOVER_MS);
  }
}

// A moment to move onto the list, so its Join buttons can be reached
function hoverLeft() {
  clearTimeout(page.hoverTimer);
  page.hoverTimer = setTimeout(hideHover, HOVER_LEAVE_MS);
}

function peopleList(people) {
  const list = el("ul", "hub-people-list");
  list.append(...people.map((person) => personRow(document, person, joinPerson)));
  return list;
}

function hoverParts(people, elsewhere) {
  const parts = [];
  if (people.length) {
    parts.push(peopleList(people));
  }
  if (elsewhere) {
    parts.push(el("p", "hover-elsewhere", elsewhereLine(elsewhere)));
  }
  return parts;
}

function showHover(key, card = document.querySelector(`#games .card[data-key="${CSS.escape(key)}"]`)) {
  const people = playing(key);
  const elsewhere = page.host.presence.elsewhere[key] || 0;
  if (!card || (!people.length && !elsewhere)) {
    hideHover();
    return;
  }
  const box = $("hover-people");
  drawPeople(box, JSON.stringify([key, people.map(rowSignature), elsewhere]), () => hoverParts(people, elsewhere));
  box.setAttribute("aria-label", `Playing ${page.host.gameName(key)}`);
  box.hidden = false;
  page.hoverKey = key;
  placeHover(box, card);
}

// Under the card, or above it when there is no room below. The list is never taller than the screen: with more
// players than fit it scrolls, so the last Join stays reachable
function placeHover(box, card) {
  const safe = getComputedStyle(page.host.safeArea);
  const low = EDGE + parseFloat(safe.paddingTop);
  const high = window.innerHeight - EDGE - parseFloat(safe.paddingBottom);
  box.style.maxHeight = `${Math.max(0, high - low)}px`;
  const height = box.offsetHeight;
  const at = card.getBoundingClientRect();
  const below = at.bottom + 6;
  const top = below + height > high ? at.top - height - 6 : below;
  box.style.left = `${clamp(at.left, EDGE, window.innerWidth - box.offsetWidth - EDGE)}px`;
  box.style.top = `${clamp(top, low, Math.max(low, high - height))}px`;
}

function hideHover() {
  clearTimeout(page.hoverTimer);
  page.hoverKey = null;
  $("hover-people").hidden = true;
}

// How wide the header row's button is with this many faces. With none it is only the count
function stackWidth(faces, others) {
  if (!faces) {
    return COUNT_ONLY;
  }
  return STACK_PAD + FACE_FIRST + (faces - 1) * FACE_NEXT + (others > faces ? FACE_MORE : 0);
}

// How many faces the header row has room for, possibly none (then it is only the count). The row never shrinks and
// the server's name does, with an ellipsis, so this is the one place that decides how they share the line: the name
// keeps NAME_KEEP_EM of its text (all of it when it is shorter) and the row takes the rest
function faceCount(others) {
  const bar = document.querySelector(".bar");
  const who = document.querySelector(".who");
  const name = $("who-name");
  const barStyle = getComputedStyle(bar);
  const whoStyle = getComputedStyle(who);
  const inside = bar.clientWidth - parseFloat(barStyle.paddingLeft) - parseFloat(barStyle.paddingRight);
  // A menu that isn't showing has no width to fit to
  if (inside <= 0) {
    return Math.min(others, ROW_MAX);
  }
  // The gear takes no room when it is hidden, and the Orb has none at all (Settings is a pod there)
  const gear = $("gear");
  const beside = gear.offsetWidth ? gear.offsetWidth + parseFloat(barStyle.columnGap) : 0;
  const share = whoStyle.maxWidth.endsWith("%") ? (inside * parseFloat(whoStyle.maxWidth)) / 100 : Infinity;
  const gap = parseFloat(whoStyle.columnGap);
  // What the name and the row share: the badge and the gap after it come first, then the gap and margin before the row
  const room = Math.min(inside - beside, share) - who.querySelector(".badge").offsetWidth - 2 * gap;
  // The Orb's name has padding for its glow and the margins to cancel it, so its text is what it takes of the line
  const nameStyle = getComputedStyle(name);
  const margins = parseFloat(nameStyle.marginLeft) + parseFloat(nameStyle.marginRight);
  const keep = Math.min(name.scrollWidth + margins, NAME_KEEP_EM * parseFloat(nameStyle.fontSize));
  const rowRoom = room - keep - parseFloat(getComputedStyle($("people-row")).marginLeft) - FIT_SLACK;
  for (let faces = Math.min(others, ROW_MAX); faces > 0; faces -= 1) {
    if (stackWidth(faces, others) <= rowRoom) {
      return faces;
    }
  }
  // Not even one face fits: the count, unless that is wider than one face would be
  return stackWidth(1, others) <= COUNT_ONLY ? 1 : 0;
}

// Everyone else in the window next to the server's name, or an invite when nobody else is here. Without the menu
// link there is no list at all, and the row goes away with it
function renderPeopleRow() {
  const row = $("people-row");
  const people = menuPeople();
  if (!page.host.inDiscord || !page.host.login || !people.length) {
    row.hidden = true;
    return;
  }
  const others = people.filter((person) => !person.you);
  const faces = others.slice(0, others.length ? faceCount(others.length) : 0);
  const compact = window.innerWidth < COMPACT_WIDTH;
  // The status lines only show in the faces' tooltips, so they are set in place and don't count as a new row
  const shown = JSON.stringify([
    others.length,
    compact,
    faces.map((person) => [
      person.id,
      person.name,
      person.avatar,
      Boolean(person.away),
      person.game,
      page.host.gameName(person.game),
      page.host.gameIcon(person.game),
    ]),
  ]);
  drawPeople(row, shown, () => [others.length ? peopleStack(others, faces) : invitePill(compact)]);
  row.querySelectorAll(".face").forEach((face, i) => {
    face.title = `${faces[i].name}: ${statusText(faces[i])}`;
  });
  row.hidden = false;
}

// A phone's header has no room for the words, so the pill is only its icon
function invitePill(compact) {
  const invite = el("button", "invite-pill");
  invite.type = "button";
  if (compact) {
    invite.classList.add("compact");
    invite.append(icon(document, "invite"));
    invite.title = "Invite friends";
    invite.setAttribute("aria-label", "Invite friends");
  } else {
    invite.textContent = "Invite friends";
  }
  invite.addEventListener("click", () => page.host.invite());
  return invite;
}

function peopleStack(others, faces) {
  const open = el("button", "people-stack");
  open.type = "button";
  open.setAttribute("aria-label", `Who's here: ${others.length} ${others.length === 1 ? "other" : "others"}`);
  if (!faces.length) {
    // No room for a face: the people icon and how many
    open.classList.add("count-only");
    open.append(icon(document, "people"), el("span", "more", String(others.length)));
  } else {
    open.append(...faces.map(headerFace));
    if (others.length > faces.length) {
      open.append(el("span", "more", `+${others.length - faces.length}`));
    }
  }
  open.addEventListener("click", () => page.host.people.open());
  return open;
}

// The game's first letter, for a game without a picture or whose picture won't load, as on its card
function letterBadge(game) {
  return el("span", "game-badge letter", initial(page.host.gameName(game)));
}

// A face with a small badge for the game they're in
function headerFace(person) {
  const face = el("span", "face");
  face.append(avatar(document, person));
  if (!person.game) {
    return face;
  }
  const picture = page.host.gameIcon(person.game);
  if (picture) {
    const badge = el("img", "game-badge");
    badge.alt = "";
    badge.addEventListener("error", () => badge.replaceWith(letterBadge(person.game)));
    badge.src = picture;
    face.append(badge);
  } else {
    face.append(letterBadge(person.game));
  }
  return face;
}

function screenParts(people, elsewhere) {
  const parts = [];
  if (people.length) {
    parts.push(el("p", "screen-people-title", "Playing now"), peopleList(people.slice(0, SCREEN_MAX)));
    if (people.length > SCREEN_MAX) {
      parts.push(el("p", "screen-more", `and ${people.length - SCREEN_MAX} more`));
    }
  }
  if (elsewhere) {
    parts.push(el("p", "hover-elsewhere", elsewhereLine(elsewhere)));
  }
  return parts;
}

// The Orb screen's "Playing now" for the game it shows
function fillScreenPeople(box) {
  const people = playing(box.dataset.key);
  const elsewhere = page.host.presence.elsewhere[box.dataset.key] || 0;
  const shown = JSON.stringify([people.slice(0, SCREEN_MAX).map(rowSignature), people.length, elsewhere]);
  const drew = drawPeople(box, shown, () => screenParts(people, elsewhere));
  box.hidden = !people.length && !elsewhere;
  return drew;
}

// The screen lists its players only while the panel, with the Select prompt hanging under it, still fits between
// the header and the bottom edge. A window too short for that leaves the list out, and the pod's bubble opens the
// hover list instead (screenListsPlayers). The list goes back in first, so the measure is of the panel as it
// would be; both happen before the browser draws, so nothing flickers
function fitScreenPeople() {
  const screen = document.getElementById("orb-screen");
  if (!screen || !orbTheme() || page.host.frame) {
    return;
  }
  screen.classList.remove("no-room");
  const panel = screen.getBoundingClientRect();
  if (!panel.height) {
    return;
  }
  const select = screen.querySelector(".screen-select").getBoundingClientRect();
  const bottom = window.innerHeight - parseFloat(getComputedStyle($("menu")).paddingBottom) - EDGE;
  const top = document.querySelector(".bar").getBoundingClientRect().bottom;
  screen.classList.toggle("no-room", select.bottom > bottom || panel.top < top);
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
  if (tab === "payouts") {
    return { payouts: Object.fromEntries(state.payouts.games.map((game) => [game.key, payoutSettings(game)])) };
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
  if (page.tab === "payouts") {
    applyLook(page.state.look);
    renderGames(page.state.games);
  } else if (page.tab === "order") {
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
  } else if (page.tab === "payouts") {
    body.replaceChildren(...payoutEditor());
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

// ---------- Payouts ----------

function payoutSettings(game) {
  return { on: game.on, rate: game.rate, cap: game.cap, plays: game.plays };
}

function payoutEditor() {
  const { games, currency } = page.state.payouts;
  const notes = [
    "After a round, players can cash in their score: each point pays the rate, up to the most per cash-in. Playing again first gives up the score, so players save their cash-ins for their best rounds. Cash-ins come back at midnight UTC.",
  ];
  if (page.state.payouts.global) {
    notes.push("The bank is global, so these payouts apply in every server, and cash-ins count across servers.");
  }
  if (!games.length) {
    notes.push("No installed game pays out yet.");
  }
  return [...notes.map((text) => el("p", "payout-note", text)), ...games.map((game) => payoutCard(game, currency))];
}

function payoutCard(game, currency) {
  const staged = page.staged.payouts[game.key];
  const box = el("fieldset", "payout");
  box.dataset.key = game.key;
  const toggle = el("input");
  toggle.type = "checkbox";
  toggle.checked = staged.on;
  toggle.addEventListener("change", () => {
    staged.on = toggle.checked;
    box.classList.toggle("off", !staged.on);
  });
  const label = el("label", "switch");
  label.append(toggle, el("span", "", `${game.name} pays out`));
  const numbers = el("div", "payout-numbers");
  for (const [name, text, step] of PAYOUT_FIELDS) {
    const input = el("input");
    input.type = "number";
    input.min = step === "any" ? "0" : "1";
    input.step = step;
    input.value = String(staged[name]);
    input.dataset.field = name;
    // An empty box goes as null, which the bot refuses with a message saying what it needs
    input.addEventListener("input", () => {
      staged[name] = input.value === "" ? null : Number(input.value);
    });
    const field = el("label", "payout-field");
    field.append(el("span", "field-label", text(game, currency)), input);
    numbers.append(field);
  }
  box.classList.toggle("off", !staged.on);
  box.append(label, numbers);
  return box;
}

// ---------- Save and reset ----------

function saveBody() {
  const body = { tab: page.tab };
  if (page.tab === "payouts") {
    body.payouts = page.staged.payouts;
    return body;
  }
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
  if (page.tab === "payouts") {
    page.staged.payouts = Object.fromEntries(
      page.state.payouts.games.map((game) => [game.key, { ...game.defaults }]),
    );
  } else if (page.tab === "order") {
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
