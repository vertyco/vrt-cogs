// The wardrobe, where a player tries on, buys and wears looks, a player's profile card, the crate and party round
// buttons, the gear's prices dialog for server admins, the bot owner's tuning sliders and everyone's sound panel. For
// all but the last the bot decides everything: this page shows what it says and passes on what the player taps. The
// sound panel's choices stay on this device.
import { TRAILS } from "./fx.js";
import { buildPenguin, meshShape, paint, shape } from "./models.js";
import { fieldName, fillTag, NAME_STYLES, nameStyleOf, styledName, tagLines, titleOf, TITLES } from "./tags.js";

// Far out to sea, where the game's camera never looks
const ROOM_X = 300;
const SWAY = 0.55;
// How wide the circle a trail is shown on is, and how fast it goes round
const LOOP = 1;
const LOOP_SPEED = 2.6;
// How far a finger's pixel turns the penguin, and the turn that shows its back
const TURN_PER_PIXEL = 0.012;
const BACK_VIEW = Math.PI;
// A cheer and a splash play again this many seconds after they began, and the splash lands this far in front
const CHEER_EVERY = 3.4;
const SPLASH_EVERY = 2.2;
const SPLASH_FRONT = 1.75;
// The name over the penguin's head keeps this many pixels inside the window
const TAG_EDGE = 4;
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const NO_SERVER_NOTE = "Open Penguin Wars in a server to buy this.";
const NOT_SOLD_NOTE = "This server doesn't sell this.";

// How long the page waits for the bot. A phone can lose an answer, and that must never leave a button dead
const ANSWER_MS = 10000;
const NO_ANSWER = new Error("The bot didn't answer in time. Try again in a moment.");

// The wardrobe's tabs, one for each thing a penguin wears, in the bot's order. `bare` names the card for wearing
// none of that kind
const TABS = [
  {
    kind: "skin",
    label: "Skin",
    bare: "Classic",
    icon: `<path fill="currentColor" d="M12 2.5c3.6 0 5.5 2.7 5.5 6.5v6.5c0 3.3-2.2 6-5.5 6s-5.5-2.7-5.5-6V9c0-3.8 1.9-6.5 5.5-6.5z"/>`,
  },
  {
    kind: "hat",
    label: "Hat",
    bare: "No hat",
    icon: `<path fill="currentColor" d="M8 4h8a1 1 0 0 1 1 1v9.5H7V5a1 1 0 0 1 1-1z"/><rect fill="currentColor" x="3" y="15.5" width="18" height="3.6" rx="1.8"/>`,
  },
  {
    kind: "face",
    label: "Face",
    bare: "Nothing",
    icon: `<g fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="7" cy="13" r="3.8"/><circle cx="17" cy="13" r="3.8"/><path d="M10.8 12.5h2.4"/></g>`,
  },
  {
    kind: "neck",
    label: "Neck",
    bare: "Bare neck",
    icon: `<rect fill="currentColor" x="3" y="3.5" width="18" height="6.5" rx="3.25"/><path fill="currentColor" d="M7.5 11.5h4.2v6l-2.1-1.7-2.1 1.7zM13 11.5h4.5v9.5l-2.25-1.8L13 21z"/>`,
  },
  {
    kind: "back",
    label: "Back",
    bare: "Nothing",
    icon: `<path fill="currentColor" d="M9 3h6v2.5a5 5 0 0 1 3 4.5v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-9a5 5 0 0 1 3-4.5z"/>`,
  },
  {
    kind: "trail",
    label: "Trail",
    bare: "No trail",
    icon: `<path fill="currentColor" d="M10 3l2 6.5 6.5 2-6.5 2-2 6.5-2-6.5L1.5 11.5 8 9.5zM18.5 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"/>`,
  },
  {
    kind: "cheer",
    label: "Cheer",
    bare: "Hops",
    icon: `<path fill="currentColor" d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.200 6.5-5.9-3.200-5.9 3.200 1.200-6.5L2.5 9.4l6.6-.9z"/>`,
  },
  {
    kind: "splash",
    label: "Splash",
    bare: "Water",
    icon: `<path fill="currentColor" d="M12 2.5c3.5 4.5 6 7.8 6 11.5a6 6 0 0 1-12 0c0-3.7 2.5-7 6-11.5z"/>`,
  },
  {
    kind: "title",
    label: "Title",
    bare: "No title",
    icon: `<circle fill="currentColor" cx="12" cy="8.500" r="6"/><path fill="currentColor" d="M8 13l-2.500 8.500 6.500-3.200 6.500 3.200L16 13z"/>`,
  },
  {
    kind: "name",
    label: "Name",
    bare: "Plain",
    icon: `<path fill="none" stroke="currentColor" stroke-width="2.800" stroke-linecap="round" stroke-linejoin="round" d="M6.500 15L12 3l5.500 12M8.500 11h7"/><rect fill="currentColor" x="4" y="18.500" width="16" height="3.500" rx="1.750"/>`,
  },
];
// The two kinds that are words and not shapes. Their cards show the words themselves in place of a picture, and the
// penguin carries a name tag while one of their tabs is on show
const WORDS = ["title", "name"];
// The player's own name on a name style's card is cut to this many characters
const CARD_NAME_MAX = 12;
// The id of the card that takes a thing off, which no item has
const BARE = "(bare)";
// How many pictures looks.webp holds in a row
const THUMBS_ACROSS = 8;

function $(id) {
  return document.getElementById(id);
}

function count(number) {
  return number.toLocaleString();
}

function answerOf(request) {
  let timer;
  const limit = new Promise((unused, giveUp) => {
    timer = setTimeout(() => giveUp(NO_ANSWER), ANSWER_MS);
  });
  return Promise.race([request, limit]).finally(() => clearTimeout(timer));
}

// ---------- The preview ----------

// A penguin standing on a bit of ice in a dialog's window: the wardrobe's, or a profile card's. It shares the game's
// engine: the window is a gap in the dialog, and a second camera draws the penguin into just that part of the game's
// own canvas. It has a layer and a light of its own, so it adds no shadows or game objects, and nothing of it runs
// while no window is open. There is one of it, so only one window shows at a time
class FittingRoom {
  constructor(scene) {
    this.scene = scene;
    this.room = null;
    this.looks = {};
    // The tab on show, which decides what the penguin does: turn its back, slide a trail, cheer or make a splash
    this.kind = null;
    this.time = 0;
    this.nextPuff = 0;
    // Seconds into the cheer or the splash on show
    this.showFor = 0;
    // The turn the player's finger has given the penguin, the turn the tab asks for, and where it is between them
    this.turned = 0;
    this.facing = 0;
    this.drag = { on: false, id: 0, x: 0 };
    // The windows that already turn the penguin under a finger
    this.heard = new WeakSet();
    // The name tag over the penguin's head, with its two lines and its size, which is 0 until it is measured
    this.tag = document.createElement("div");
    this.tag.className = "tag";
    this.tag.hidden = true;
    this.lines = tagLines(this.tag);
    this.tagSize = { width: 0, height: 0 };
  }

  build() {
    const { app, fx, ice } = this.scene;
    this.layer = new pc.Layer({ name: "Shop" });
    app.scene.layers.push(this.layer);
    fx.drawEffectsIn(this.layer);
    this.room = new pc.Entity("shop-room");
    app.root.addChild(this.room);
    this.camera = new pc.Entity("shop-camera");
    this.camera.addComponent("camera", {
      clearColor: new pc.Color().fromString("#14587a"),
      fov: 30,
      nearClip: 0.5,
      farClip: 30,
      priority: 1,
      layers: [this.layer.id],
    });
    this.camera.setPosition(ROOM_X, 1.9, 6.4);
    this.camera.lookAt(ROOM_X, 0.92, 0);
    this.room.addChild(this.camera);
    const sun = new pc.Entity();
    sun.addComponent("light", {
      type: "directional",
      color: new pc.Color(1, 0.97, 0.92),
      intensity: 1.15,
      layers: [this.layer.id],
    });
    sun.setEulerAngles(52, 28, 0);
    this.room.addChild(sun);
    const floe = new pc.Entity();
    floe.setPosition(ROOM_X, 0, 0);
    floe.setLocalScale(2.2, 1, 2.2);
    this.room.addChild(floe);
    meshShape(floe, ice.tileMesh, ice.ice, false);
    meshShape(floe, ice.capMesh, ice.snow, false);
    const shadow = paint("#0b3245", { opacity: 0.22 });
    shape(this.room, "cylinder", shadow, [ROOM_X, 0.1, 0], [1.25, 0.01, 1.05], null, false);
    const parts = buildPenguin(app, null, false);
    parts.root.name = "shop-penguin";
    parts.root.reparent(this.room);
    // The fields the game's own pose reads, so the penguin moves as one on the ice does
    this.pen = {
      parts,
      looks: {},
      x: ROOM_X,
      z: 0,
      yaw: 0,
      slide: 0,
      squash: 0,
      windup: 0,
      bracing: false,
      braceLeft: 0,
      ph: 0,
      hop: 0,
      cheering: false,
      flip: 0,
      twirl: 0,
      center: 0,
      nameRise: 0,
    };
    this.spot = new pc.Vec3();
    this.onLayer(this.room);
  }

  onLayer(entity) {
    for (const node of entity.find((item) => item.render)) {
      node.render.layers = [this.layer.id];
    }
  }

  // `box` is the window to draw in and `looks` what the penguin wears. It opens standing still, with no name tag
  open(box, looks) {
    if (!this.room) {
      this.build();
    }
    if (!this.heard.has(box)) {
      this.heard.add(box);
      this.listen(box);
    }
    this.box = box;
    box.append(this.tag);
    this.name(null);
    this.show(null);
    this.wear(looks);
    this.room.enabled = true;
    this.scene.previewing = true;
    this.scene.app.on("update", this.tick, this);
    this.fit();
  }

  close() {
    this.room.enabled = false;
    this.drag.on = false;
    this.scene.previewing = false;
    this.scene.app.off("update", this.tick, this);
    this.scene.camera.enabled = true;
  }

  // `looks` is everything the penguin has on, as { kind: id }
  wear(looks) {
    this.looks = looks;
    this.scene.dress(this.pen, looks);
    this.onLayer(this.pen.parts.root);
  }

  // The name tag over the penguin's head: `who` is { name, style, title }, with a name style's id or null and a
  // title's words or "", or null for no tag
  name(who) {
    this.tag.hidden = !who;
    if (who) {
      fillTag(this.tag, this.lines, who.name, who.style, who.title);
      this.tagSize.width = 0;
    }
  }

  // The tab on show, or null for none. The Back tab turns the penguin round, and the others face it forward again.
  // What the last tab's cheer or splash still had to come goes with it
  show(kind) {
    if (kind !== this.kind) {
      this.kind = kind;
      this.turned = 0;
      this.showFor = 0;
      this.scene.fx.dropShows(ROOM_X);
    }
  }

  // A finger or the mouse on the window turns the penguin
  listen(box) {
    const { drag } = this;
    const letGo = (e) => {
      if (e.pointerId === drag.id) {
        drag.on = false;
      }
    };
    box.addEventListener("pointerdown", (e) => {
      Object.assign(drag, { on: true, id: e.pointerId, x: e.clientX });
      box.setPointerCapture?.(e.pointerId);
    });
    box.addEventListener("pointermove", (e) => {
      if (drag.on && e.pointerId === drag.id) {
        this.turned += (e.clientX - drag.x) * TURN_PER_PIXEL;
        drag.x = e.clientX;
      }
    });
    box.addEventListener("pointerup", letGo);
    box.addEventListener("pointercancel", letGo);
  }

  // Draws into the part of the canvas under the dialog's window. A camera counts from the canvas's bottom left, 0 to 1
  fit() {
    const box = this.box.getBoundingClientRect();
    this.rect = box;
    const { clientWidth, clientHeight } = this.scene.canvas;
    const { camera } = this.camera;
    camera.rect = camera.rect.set(
      box.left / clientWidth,
      1 - box.bottom / clientHeight,
      box.width / clientWidth,
      box.height / clientHeight,
    );
    // Where the wardrobe covers the whole game, as on a phone, nothing is left for the game's camera to draw
    const whole = this.box.parentElement.getBoundingClientRect();
    this.scene.camera.enabled = whole.width < clientWidth - 1 || whole.height < clientHeight - 1;
  }

  // A trail needs a slide to show, so it runs round the penguin's feet
  puff(dt) {
    const look = this.kind === "trail" ? TRAILS[this.looks.trail] : null;
    this.nextPuff -= dt;
    if (look && this.nextPuff <= 0) {
      this.nextPuff = look.every;
      const angle = this.time * LOOP_SPEED;
      this.scene.fx.puff(look, ROOM_X + Math.cos(angle) * LOOP, Math.sin(angle) * LOOP);
    }
  }

  // The cheer plays over and over on its tab, and so does the splash, in the water in front of the ice
  perform(dt) {
    const { scene, pen, kind } = this;
    const begins = this.showFor === 0;
    this.showFor += dt;
    if (kind === "cheer") {
      if (begins) {
        scene.fx.cheerBurst(this.looks.cheer, pen.x, pen.z);
      }
      // A cheer longer than the wait plays to its end first
      if (!scene.cheerPose(pen, this.showFor) && this.showFor > CHEER_EVERY) {
        this.showFor = 0;
      }
      return;
    }
    scene.restPose(pen);
    if (kind === "splash" && begins) {
      scene.fx.knockout(this.looks.splash, ROOM_X, SPLASH_FRONT);
    }
    if (this.showFor > SPLASH_EVERY) {
      this.showFor = 0;
    }
  }

  // Keeps the name tag over the penguin's head, whatever hat it wears, and inside the window. The camera gives a point
  // on the canvas, which fills the screen, and the tag is placed from the window's own corner
  placeTag() {
    const { tag, tagSize, rect } = this;
    if (tag.hidden) {
      return;
    }
    if (!tagSize.width) {
      tagSize.width = tag.offsetWidth;
      tagSize.height = tag.offsetHeight;
    }
    const spot = this.camera.camera.worldToScreen(this.scene.namePoint(this.pen), this.spot);
    const most = rect.width - tagSize.width - TAG_EDGE;
    const left = Math.max(TAG_EDGE, Math.min(most, spot.x - rect.left - tagSize.width / 2));
    const top = Math.max(TAG_EDGE, spot.y - rect.top - tagSize.height);
    tag.style.transform = `translate(${left.toFixed(1)}px,${top.toFixed(1)}px)`;
  }

  tick(dt) {
    this.time += dt;
    this.fit();
    const want = this.kind === "back" ? BACK_VIEW : 0;
    this.facing += (want - this.facing) * Math.min(1, dt * 6);
    const sway = this.drag.on ? 0 : Math.sin(this.time * 0.8) * SWAY;
    this.pen.yaw = this.facing + this.turned + sway;
    // Nothing slides or lands in here, so the penguin stands at its full height unless a cheer playing this frame lays
    // it down or squashes it. In a round the scene eases both away, and this penguin has no round
    this.pen.slide = 0;
    this.pen.squash = 0;
    this.perform(dt);
    this.scene.posePenguin(this.pen);
    this.placeTag();
    this.puff(dt);
  }
}

// ---------- The wardrobe ----------

const shop = {
  hub: null,
  room: null,
  // What the bot says there is and what this player has: items, currency, balance, owned and wear. It outlives the
  // dialog, so a reopened preview starts dressed
  data: null,
  // Which opening of the dialog this is, and whether its cards are in
  load: 0,
  loaded: false,
  // The player's own name, as a name style's card shows it
  me: "",
  // The tab on show and its cards, by item id
  tab: TABS[0].kind,
  cards: new Map(),
  // The card last tapped, which the preview tries on in place of what the player wears of its kind: an item's id, BARE
  // for the card that takes the thing off, or null with nothing tapped yet
  picked: null,
  // What the big button does now, its last press while that is still with the bot, the words for that press, and
  // the bot's last refusal
  step: null,
  asking: null,
  doing: "",
  failed: "",
};

function tabButton(tab) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "tab";
  button.dataset.kind = tab.kind;
  button.setAttribute("role", "tab");
  button.setAttribute("aria-selected", "false");
  button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${tab.icon}</svg>`;
  button.append(tab.label);
  button.addEventListener("click", () => showTab(tab.kind));
  return button;
}

function card(id, name) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "item";
  button.dataset.id = id;
  button.setAttribute("aria-pressed", "false");
  const thumb = document.createElement("span");
  thumb.className = "thumb";
  const label = document.createElement("span");
  label.className = "name";
  label.textContent = name;
  const state = document.createElement("span");
  state.className = "state";
  button.append(thumb, label, state);
  button.addEventListener("click", () => pick(id));
  shop.cards.set(id, button);
  return button;
}

// A title or a name style has no picture. Its card shows the words on a dark plate: a title as its text, and a name
// style as the player's own name in it. `id` is the name style's, or null for the card that takes the thing off. A
// title's card needs no line under the plate, which would say the same again
function wordsCard(button, kind, id) {
  const thumb = button.querySelector(".thumb");
  const label = button.querySelector(".name");
  const named = kind === "name";
  thumb.classList.add("words");
  thumb.classList.toggle("none", !named && id === null);
  thumb.append(styledName(named ? shop.me : label.textContent, named ? nameStyleOf({ name: id }) : null));
  label.hidden = !named;
}

// An item's card shows its picture out of looks.webp, by its place in the catalog, or its words, and how far along an
// earned one is
function itemCard(item) {
  const button = card(item.id, item.name);
  if (WORDS.includes(item.kind)) {
    wordsCard(button, item.kind, item.id);
  } else {
    const place = shop.data.items.indexOf(item);
    const thumb = button.querySelector(".thumb");
    thumb.style.setProperty("--col", place % THUMBS_ACROSS);
    thumb.style.setProperty("--row", Math.floor(place / THUMBS_ACROSS));
  }
  if (item.earn) {
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.append(document.createElement("span"));
    button.append(bar);
  }
  return button;
}

function bareCard(tab) {
  const button = card(BARE, tab.bare);
  if (WORDS.includes(tab.kind)) {
    wordsCard(button, tab.kind, null);
  } else {
    button.querySelector(".thumb").classList.add("bare");
  }
  return button;
}

// What the preview wears: what the player has on, with only the picked card tried on, over what they wear of its
// kind. On the Title and Name tabs the penguin carries the name tag those looks make
function dressRoom() {
  // The one preview penguin belongs to whichever dialog is open. An answer that comes after the wardrobe has closed
  // must leave it alone, as it may be showing someone's profile card
  if (!$("shop").open) {
    return;
  }
  const { data, picked, tab } = shop;
  const looks = { ...data?.wear };
  if (picked === BARE) {
    delete looks[tab];
  } else if (picked !== null) {
    looks[tab] = picked;
  }
  shop.room.wear(looks);
  const tagged = WORDS.includes(tab) && Boolean(shop.me);
  shop.room.name(tagged ? { name: shop.me, style: nameStyleOf(looks), title: titleOf(looks) ?? "" } : null);
}

function pick(id) {
  shop.picked = id;
  shop.failed = "";
  renderShop();
}

function cardText(item, data) {
  if (data.wear[item.kind] === item.id) {
    return "Wearing";
  }
  if (data.owned.includes(item.id)) {
    return item.earn ? "Earned" : "Owned";
  }
  if (item.earn) {
    return `${count(item.earn.have)}/${count(item.earn.need)}`;
  }
  if (item.price !== null) {
    return count(item.price);
  }
  return data.balance === null ? "In a server" : "Not sold here";
}

// The next thing the picked item can do: a button's words and what it does, or a note saying why there is no button
function stepFor(item, data) {
  if (data.wear[item.kind] === item.id) {
    return { label: "Take off", run: () => takeOff(item.kind) };
  }
  if (data.owned.includes(item.id)) {
    return { label: "Wear", run: () => ask("wear", { kind: item.kind, item: item.id }, "Putting it on...") };
  }
  if (item.earn) {
    return { note: `${item.earn.text} (${count(item.earn.have)}/${count(item.earn.need)}).` };
  }
  if (item.price === null) {
    return { note: data.balance === null ? NO_SERVER_NOTE : NOT_SOLD_NOTE };
  }
  if (data.balance < item.price) {
    return { note: `You need ${count(item.price - data.balance)} more ${data.currency}.` };
  }
  return { label: `Buy for ${count(item.price)}`, run: () => ask("buy", { item: item.id }, "Buying...") };
}

// The card that takes a thing off only has something to do while one is on
function bareStep(kind, data) {
  return data.wear[kind] ? { label: "Take off", run: () => takeOff(kind) } : { note: "" };
}

function renderCard(item, data) {
  const button = shop.cards.get(item.id);
  const text = cardText(item, data);
  const mine = data.owned.includes(item.id);
  button.querySelector(".state").textContent = text;
  button.classList.toggle("worn", text === "Wearing");
  button.classList.toggle("owned", mine && text !== "Wearing");
  button.classList.toggle("locked", Boolean(item.earn) && !mine);
  button.setAttribute("aria-pressed", String(item.id === shop.picked));
  const bar = button.querySelector(".bar");
  if (bar) {
    bar.hidden = mine;
    bar.style.setProperty("--done", `${Math.round((100 * item.earn.have) / item.earn.need)}%`);
  }
}

// Only changes what is on the cards, so a press that has started on one still lands
function renderShop() {
  if (!shop.loaded) {
    return;
  }
  const { data, picked, tab } = shop;
  const shown = data.items.filter((item) => item.kind === tab);
  shown.forEach((item) => renderCard(item, data));
  const bare = shop.cards.get(BARE);
  bare.querySelector(".state").textContent = data.wear[tab] ? "" : "Wearing";
  bare.classList.toggle("worn", !data.wear[tab]);
  bare.setAttribute("aria-pressed", String(picked === BARE));
  const inServer = data.balance !== null;
  $("shop-balance").textContent = inServer
    ? `${count(data.balance)} ${data.currency}`
    : "Buying works in a server. Wearing works anywhere.";
  const item = shown.find(({ id }) => id === picked);
  if (item) {
    shop.step = stepFor(item, data);
  } else {
    shop.step = picked === BARE ? bareStep(tab, data) : { note: "Tap something to try it on." };
  }
  $("shop-note").textContent = shop.doing || shop.failed || (shop.step.note ?? "");
  const act = $("shop-act");
  act.hidden = !shop.step.label;
  act.textContent = shop.step.label ?? "";
  act.disabled = shop.asking !== null;
  dressRoom();
}

// Ten tabs are more than a narrow phone shows at once, so their row scrolls sideways, and the tab on show is brought
// to its middle
function bringIntoRow(button) {
  const row = $("shop-tabs");
  const [box, tab] = [row.getBoundingClientRect(), button.getBoundingClientRect()];
  const left = row.scrollLeft + tab.left - box.left - (box.width - tab.width) / 2;
  row.scrollTo({ left, behavior: REDUCED ? "auto" : "smooth" });
}

// The row fades out at an end that has more tabs past it
function markRowEnds() {
  const row = $("shop-tabs");
  row.classList.toggle("more-left", row.scrollLeft > 1);
  row.classList.toggle("more-right", row.scrollLeft < row.scrollWidth - row.clientWidth - 1);
}

// The cards of one tab: taking the thing off, then what the player has, then the rest, each in catalog order. They are
// only put in order as the tab opens, so a card never moves under a finger after a buy
function showTab(kind) {
  Object.assign(shop, { tab: kind, picked: null, failed: "" });
  for (const button of $("shop-tabs").children) {
    button.setAttribute("aria-selected", String(button.dataset.kind === kind));
    if (button.dataset.kind === kind) {
      bringIntoRow(button);
    }
  }
  shop.room.show(kind);
  dressRoom();
  if (!shop.loaded) {
    return;
  }
  const { items, owned } = shop.data;
  const mine = (item) => owned.includes(item.id);
  const shown = items.filter((item) => item.kind === kind);
  shop.cards.clear();
  const shelf = $("shop-shelf");
  shelf.replaceChildren(
    bareCard(TABS.find((tab) => tab.kind === kind)),
    ...shown.filter(mine).map(itemCard),
    ...shown.filter((item) => !mine(item)).map(itemCard),
  );
  shelf.scrollTop = 0;
  renderShop();
}

// Reads what the bot has now. The dialog may have been shut and opened again since it was last read
async function reload() {
  try {
    shop.data = await answerOf(shop.hub.api("shop"));
  } catch (e) {
    console.warn("Penguin Wars: couldn't read the wardrobe again", e);
  }
}

// An answer that comes after the page stopped waiting is still the bot's word
async function lateAnswer(request) {
  const note = await request.then(
    () => "",
    (e) => e.message,
  );
  if (shop.failed === NO_ANSWER.message) {
    shop.failed = note;
  }
  await reload();
  renderShop();
}

// Reads `shop.data` only once the answer is here, since a reopen replaces it. A refusal or a lost answer means the
// page was behind the bot, or the bot may have acted without the page hearing, so it reads what is true again
async function settle(action, body) {
  const { picked } = shop;
  const request = shop.hub.api(action, body);
  try {
    const answer = await answerOf(request);
    Object.assign(shop.data, answer);
  } catch (e) {
    if (shop.picked === picked) {
      shop.failed = e.message;
    }
    await reload();
    if (e === NO_ANSWER) {
      lateAnswer(request);
    }
  }
}

// Sends a buy or wear. The bot's answer says what the player now has, and its refusals are worded for them.
// `doing` is what the note says until then
function ask(action, body, doing) {
  Object.assign(shop, { failed: "", doing });
  shop.asking = settle(action, body).then(() => {
    Object.assign(shop, { asking: null, doing: "" });
    renderShop();
  });
  renderShop();
}

function takeOff(kind) {
  shop.picked = null;
  ask("wear", { kind, item: null }, "Taking it off...");
}

function fillShop(data) {
  shop.data = data;
  shop.loaded = true;
  showTab(shop.tab);
}

export async function openShop(hub) {
  const dialog = $("shop");
  shop.load += 1;
  const { load, data } = shop;
  Object.assign(shop, {
    hub,
    me: fieldName(hub?.player?.displayName || hub?.player?.username || "", CARD_NAME_MAX),
    loaded: false,
    picked: null,
    step: null,
    failed: "",
  });
  $("shop-shelf").replaceChildren();
  $("shop-balance").textContent = "";
  $("shop-note").textContent = "Loading...";
  $("shop-act").hidden = true;
  dialog.showModal();
  document.body.classList.add("shopping");
  shop.room.open($("shop-window"), data?.wear ?? {});
  showTab(shop.tab);
  if (!hub || hub.offline) {
    $("shop-note").textContent = "Open Penguin Wars in Discord to change your looks.";
    return;
  }
  try {
    // A press from before the dialog shut has to finish first, or this reads the bot from before it
    await shop.asking;
    const fresh = await answerOf(hub.api("shop"));
    // The wardrobe may have closed while this was on its way, or been reopened
    if (load === shop.load && dialog.open) {
      fillShop(fresh);
    }
  } catch (e) {
    if (load === shop.load) {
      $("shop-note").textContent = e.message;
    }
  }
}

export function bindShop(scene) {
  shop.room = new FittingRoom(scene);
  $("shop-tabs").replaceChildren(...TABS.map(tabButton));
  $("shop-tabs").addEventListener("scroll", markRowEnds, { passive: true });
  new ResizeObserver(markRowEnds).observe($("shop-tabs"));
  $("shop-act").addEventListener("click", () => {
    if (!shop.asking) {
      shop.step?.run?.();
    }
  });
  $("close-shop").addEventListener("click", () => $("shop").close());
  $("shop").addEventListener("close", () => {
    document.body.classList.remove("shopping");
    shop.room.close();
  });
  $("close-profile").addEventListener("click", () => $("profile").close());
  $("profile").addEventListener("close", () => {
    document.body.classList.remove("shopping");
    shop.room.close();
    profile.after?.();
  });
}

// ---------- Profile ----------

// A player's play counts as the card's tiles, by the bot's name for each
const COUNTS = [
  ["rounds", "Rounds"],
  ["wins", "Wins"],
  ["knockouts", "Knockouts"],
  ["fish", "Fish eaten"],
  ["seal", "Seal splashes"],
  ["bounce", "Brace bounces"],
  ["best_streak", "Best win streak"],
  ["best_round", "Knockouts in one round"],
  ["party_wins", "Wins with 3+ playing"],
];
const PROFILE_NAME_MAX = 20;
const FOE_NAME_MAX = 16;
// How many achievements still to be earned the card shows
const NEXT_UP = 4;

const profile = {
  // Which opening of the card this is, so an answer meant for an earlier one can't fill it
  load: 0,
  // What game.js wants done once the card has closed, or null
  after: null,
};

function plural(number, word) {
  return `${count(number)} ${word}${number === 1 ? "" : "s"}`;
}

function countTile([key, label], stats) {
  const tile = document.createElement("li");
  const number = document.createElement("b");
  number.textContent = count(stats[key] ?? 0);
  tile.append(number, label);
  return tile;
}

function span(kind, text) {
  const node = document.createElement("span");
  node.className = kind;
  node.textContent = text;
  return node;
}

// An achievement the player has, as the name of the look it gave
function earnedName(row) {
  const item = document.createElement("li");
  item.textContent = row.name;
  return item;
}

// An achievement still to be earned: the look it gives, what to do for it, and how far along the player is
function nextRow(row) {
  const item = document.createElement("li");
  const name = document.createElement("b");
  name.textContent = row.name;
  const kind = TABS.find((tab) => tab.kind === row.kind)?.label ?? "";
  const bar = span("bar", "");
  bar.style.setProperty("--done", `${Math.round((100 * row.have) / row.need)}%`);
  bar.append(document.createElement("span"));
  const far = `${count(row.have)}/${count(row.need)}`;
  item.append(name, span("kind", kind), span("far", far), span("how", row.text), bar);
  return item;
}

// The achievements nearest to done. Ones as far along as each other keep the catalog's order
function nextUp(rows) {
  return [...rows].sort((a, b) => b.have / b.need - a.have / a.need).slice(0, NEXT_UP);
}

// All 36 achievements with their bars would be a long scroll on a phone. So the card counts them, names the ones the
// player has, and shows only the few they are closest to
function fillEarned(rows) {
  const earned = rows.filter((row) => row.have >= row.need);
  const open = rows.filter((row) => row.have < row.need);
  $("profile-earned-head").textContent = `Achievements ${earned.length}/${rows.length}`;
  $("profile-earned").replaceChildren(...earned.map(earnedName));
  $("profile-next-head").hidden = !open.length;
  $("profile-next").replaceChildren(...nextUp(open).map(nextRow));
}

function nemesisLine(card) {
  const foe = card.nemesis;
  if (!foe) {
    return "No nemesis yet";
  }
  const whom = card.you ? "you" : "them";
  return `Nemesis: ${fieldName(foe.name, FOE_NAME_MAX)}, who knocked ${whom} out ${plural(foe.count, "time")}`;
}

function serverLine(server) {
  if (!server) {
    return "Not on the leaderboard here yet";
  }
  const numbers = [plural(server.wins, "win"), plural(server.knockouts, "knockout"), plural(server.rounds, "round")];
  return `This server: #${server.rank} · ${numbers.join(" · ")}`;
}

// `card` is the bot's word on one player. Names come from Discord, so they only ever go in as text
function fillProfile(card) {
  shop.room.wear(card.looks);
  const style = nameStyleOf({ name: card.style });
  $("profile-name").replaceChildren(styledName(fieldName(card.name, PROFILE_NAME_MAX), style));
  $("profile-title").textContent = card.title ?? "";
  $("profile-title").hidden = !card.title;
  $("profile-counts").replaceChildren(...COUNTS.map((tile) => countTile(tile, card.stats)));
  $("profile-server").textContent = serverLine(card.server);
  $("profile-nemesis").textContent = nemesisLine(card);
  $("profile-nemesis").classList.toggle("foe", Boolean(card.nemesis));
  fillEarned(card.achievements);
  $("profile-body").hidden = false;
  $("profile-body").scrollTop = 0;
  $("profile-note").textContent = "";
}

// Opens one player's card: `id` is their Discord id as text, or null for the player's own. `after()` runs once the
// card has closed. The card covers the game, as the wardrobe does
export async function openProfile(hub, id, after = null) {
  const dialog = $("profile");
  profile.load += 1;
  const { load } = profile;
  profile.after = after;
  $("profile-name").textContent = "Profile";
  $("profile-title").hidden = true;
  $("profile-body").hidden = true;
  $("profile-note").textContent = "Loading...";
  dialog.showModal();
  document.body.classList.add("shopping");
  shop.room.open($("profile-window"), {});
  if (!hub || hub.offline) {
    $("profile-note").textContent = "Open Penguin Wars in Discord to see profiles.";
    return;
  }
  try {
    const card = await answerOf(hub.api("profile", id === null ? {} : { id }));
    // The card may have closed while this was on its way, or been opened for someone else
    if (load === profile.load && dialog.open) {
      fillProfile(card);
    }
  } catch (e) {
    if (load === profile.load) {
      $("profile-note").textContent = e.message;
    }
  }
}

// ---------- Crates and party rounds ----------

// How long the crate button waits for its second press
const ARMED_MS = 3000;
const PARTY_BUTTONS = ["open-party", "end-party"];

const extras = {
  hub: null,
  toast: null,
  // What the bot says a crate and a party round cost where the player is: prices, twists, currency and balance.
  // null until it answers
  data: null,
  // The game's last state, and whether this player has a penguin in it
  state: null,
  seated: false,
  // Turns throwing on and off for taps on the ice (game.js)
  aim: null,
  armedTimer: null,
  // A crate or a party round on its way to the bot, and the bot's last refusal of a party round
  busy: false,
  refused: "",
};

async function loadExtras() {
  try {
    extras.data = await answerOf(extras.hub.api("extras"));
  } catch (e) {
    console.warn("Penguin Wars: couldn't load what crates and party rounds cost", e);
  }
  renderExtras();
}

// The crate button shows its price, and after one press asks before it spends anything
function renderCrate() {
  const { data, state, busy } = extras;
  const price = data?.prices.crate ?? null;
  const button = $("drop-crate");
  button.hidden = price === null || state?.stage !== "playing";
  if (price === null) {
    return;
  }
  const armed = button.classList.contains("armed");
  const cost = `${count(price)} ${data.currency}`;
  $("crate-text").textContent = armed ? `Drop for ${count(price)}?` : count(price);
  button.setAttribute("aria-label", armed ? `Press again to drop a crate for ${cost}` : `Drop a crate for ${cost}`);
  button.disabled = busy;
}

function disarm() {
  clearTimeout(extras.armedTimer);
  $("drop-crate").classList.remove("armed");
  renderCrate();
}

async function pressCrate() {
  const button = $("drop-crate");
  if (extras.busy) {
    return;
  }
  if (!button.classList.contains("armed")) {
    button.classList.add("armed");
    extras.armedTimer = setTimeout(disarm, ARMED_MS);
    renderCrate();
    return;
  }
  disarm();
  extras.busy = true;
  renderCrate();
  try {
    const answer = await answerOf(extras.hub.api("crate"));
    extras.data.balance = answer.balance;
  } catch (e) {
    extras.toast(e.message);
  }
  extras.busy = false;
  renderCrate();
}

function twistButton(twist) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "twist";
  const name = document.createElement("b");
  name.textContent = twist.name;
  const line = document.createElement("span");
  line.textContent = twist.line;
  button.append(name, line);
  button.addEventListener("click", () => buyTwist(twist));
  return button;
}

// Why no party round can be bought right now, or "" when one can
function partyBlock(data, state) {
  const price = data.prices.twist;
  const coming = state?.next_twist;
  if (price === null) {
    return "Party rounds aren't sold here.";
  }
  if (coming) {
    return `${coming.name} is already coming up, from ${coming.by}.`;
  }
  return data.balance < price ? `You need ${count(price - data.balance)} more ${data.currency}.` : "";
}

// The buttons are built once per opening, and only switched on and off after that, so a press that has started on
// one still lands
function renderParty() {
  const { data, state, busy, refused } = extras;
  if (!$("party").open || !data) {
    return;
  }
  const price = data.prices.twist;
  const twists = $("twists");
  if (twists.children.length !== data.twists.length) {
    twists.replaceChildren(...data.twists.map(twistButton));
  }
  const block = partyBlock(data, state);
  for (const button of twists.children) {
    button.disabled = busy || Boolean(block);
  }
  $("party-cost").textContent =
    price === null ? "" : `${count(price)} ${data.currency} each. You have ${count(data.balance)}.`;
  $("party-status").textContent = busy ? "Buying..." : refused || block;
}

async function buyTwist(twist) {
  if (extras.busy) {
    return;
  }
  Object.assign(extras, { busy: true, refused: "" });
  renderParty();
  try {
    const answer = await answerOf(extras.hub.api("party", { kind: twist.id }));
    extras.data.balance = answer.balance;
    $("party").close();
    extras.toast(`${twist.name} is up next!`);
  } catch (e) {
    extras.refused = e.message;
  }
  extras.busy = false;
  renderParty();
}

// Opens with the last numbers the bot gave, then reads the balance again
function openParty() {
  extras.refused = "";
  $("twists").replaceChildren();
  $("party-cost").textContent = "";
  $("party-status").textContent = extras.data ? "" : "Loading...";
  $("party").showModal();
  renderParty();
  loadExtras();
}

// The party round still to come, on the cards, and the one being played, called out over its 3-2-1
function renderTwists(state) {
  const coming = state.next_twist;
  for (const id of ["title-twist", "end-twist"]) {
    $(id).hidden = !coming;
    if (coming) {
      $(id).textContent = `Next round: ${coming.name}, from ${coming.by}`;
    }
  }
  const now = state.twist;
  const call = $("twist-call");
  const rolling = state.stage === "starting" || state.stage === "playing";
  // The title card covers the 3-2-1 for someone who can still hop in, and says the same
  call.hidden = !now || !rolling || !$("title").hidden;
  call.classList.toggle("leaving", state.stage === "playing");
  if (now) {
    $("twist-name").textContent = now.name;
    $("twist-line").textContent = `${now.line}. From ${now.by}`;
  }
  $("round").classList.toggle("party", Boolean(now) && state.stage !== "waiting");
}

// The round's map, called out under the party round's call through the 3-2-1 and the round's first moments: its shape,
// then its hazard by name, and one line on what to expect
function renderMap(state) {
  const map = state.board?.map;
  const call = $("map-call");
  const rolling = state.stage === "starting" || state.stage === "playing";
  // The title card covers the 3-2-1 for someone who can still hop in
  call.hidden = !map || !rolling || !$("title").hidden;
  call.classList.toggle("leaving", state.stage === "playing");
  if (map) {
    $("map-name").textContent = map.hazard_name ? `${map.name} · ${map.hazard_name}` : map.name;
    $("map-line").textContent = map.line;
  }
}

// ---------- Snowballs ----------

// What getting the snowballs out says, as the button itself only turns yellow
const SNOW_OUT = "Tap the ice to throw.";
// One person's throws are at least this far apart. The bot takes one a second from each, counted from when each
// reaches it, so the wait here is a little longer than that for a second throw that travels faster than the first
const THROW_EVERY_MS = 1100;
const PING_MS = 400;
const PING = REDUCED
  ? [{ opacity: 0.9 }, { opacity: 0 }]
  : [
      { opacity: 0.9, transform: "scale(0.4)" },
      { opacity: 0, transform: "scale(1.2)" },
    ];

// Whether this person has their snowballs out, a throw is on its way to the bot, and when the next one may go
const snow = { armed: false, busy: false, readyAt: 0, timer: null };

// The snowball button is for people with no seat, while a round is played. It shows what one throw costs, and turns
// yellow for as long as the snowballs are out
function renderSnow() {
  const { data, state, seated } = extras;
  const price = data?.prices.snowball ?? null;
  const button = $("throw-snow");
  const can = price !== null && state?.stage === "playing" && !seated;
  button.hidden = !can;
  if (!can) {
    armSnow(false);
    return;
  }
  const cost = `${count(price)} ${data.currency}`;
  $("snow-text").textContent = count(price);
  button.classList.toggle("armed", snow.armed);
  button.classList.toggle("wait", snow.armed && (snow.busy || performance.now() < snow.readyAt));
  button.setAttribute("aria-pressed", String(snow.armed));
  const armedLabel = `Put the snowballs away. Each tap on the ice throws one for ${cost}`;
  button.setAttribute("aria-label", snow.armed ? armedLabel : `Throw snowballs for ${cost} each`);
}

// Gets the snowballs out or puts them away. While they are out, a tap on the ice throws one
function armSnow(armed) {
  if (armed === snow.armed) {
    return;
  }
  snow.armed = armed;
  document.body.classList.toggle("throwing", armed);
  extras.aim(armed ? throwSnowball : null);
}

// A ring under the finger for the moment before the bot's snowball shows
function pingAt(px, py) {
  const ping = $("snow-ping");
  ping.style.left = `${px}px`;
  ping.style.top = `${py}px`;
  ping.hidden = false;
  ping.getAnimations?.().forEach((animation) => animation.cancel());
  const fading = ping.animate?.(PING, { duration: PING_MS, easing: "ease-out" });
  if (fading) {
    fading.onfinish = () => {
      ping.hidden = true;
    };
  } else {
    ping.hidden = true;
  }
}

// A tap at (x, z) on the ice, (px, py) on the screen. The bot throws the ball, and its refusal shows as a toast. A tap
// too soon after the last one does nothing
async function throwSnowball(x, z, px, py) {
  const now = performance.now();
  if (snow.busy || now < snow.readyAt) {
    return;
  }
  snow.busy = true;
  snow.readyAt = now + THROW_EVERY_MS;
  clearTimeout(snow.timer);
  snow.timer = setTimeout(renderSnow, THROW_EVERY_MS);
  pingAt(px, py);
  renderSnow();
  try {
    const spot = { x: Math.round(x * 100) / 100, z: Math.round(z * 100) / 100 };
    const answer = await answerOf(extras.hub.api("snowball", spot));
    extras.data.balance = answer.balance;
  } catch (e) {
    extras.toast(e.message);
  }
  snow.busy = false;
  renderSnow();
}

function renderExtras() {
  const { data, state } = extras;
  if (!state) {
    return;
  }
  renderCrate();
  renderSnow();
  renderTwists(state);
  renderMap(state);
  for (const id of PARTY_BUTTONS) {
    $(id).hidden = (data?.prices.twist ?? null) === null;
  }
  renderParty();
}

// `seated` is whether this player has a penguin. A round never starts under their party dialog
export function showExtras(state, seated) {
  extras.state = state;
  extras.seated = seated;
  if (state.stage !== "playing" && $("drop-crate").classList.contains("armed")) {
    disarm();
  }
  if (seated && (state.stage === "starting" || state.stage === "playing")) {
    $("party").close();
  }
  renderExtras();
}

// `toast(text)` shows a short note, `quiet()` drops a drag still held on the ice, and `aim(thrower)` has each tap on
// the ice by someone with no seat call thrower(x, z, px, py), or with null stops that
export function bindExtras(hub, toast, quiet, aim) {
  Object.assign(extras, { hub, toast, aim });
  $("drop-crate").addEventListener("click", () => {
    quiet();
    pressCrate();
  });
  $("throw-snow").addEventListener("click", () => {
    armSnow(!snow.armed);
    renderSnow();
    if (snow.armed) {
      toast(SNOW_OUT);
    }
  });
  for (const id of PARTY_BUTTONS) {
    $(id).addEventListener("click", () => {
      quiet();
      openParty();
    });
  }
  $("close-party").addEventListener("click", () => $("party").close());
  loadExtras();
}

// ---------- Prices (server admins) ----------

// The prices Reset to defaults puts back
let catalogPrices = null;
// Which opening of the dialog this is, so an answer meant for an earlier one can't touch the boxes
let pricesLoad = 0;

function priceBoxes() {
  return [...$("prices").querySelectorAll("input")];
}

// What a title or a name style is, said after its name, as "Rose" alone could be anything
function soldKind(id) {
  if (Object.hasOwn(TITLES, id)) {
    return "title";
  }
  return NAME_STYLES.includes(id) ? "name style" : "";
}

function priceBox(item) {
  const label = document.createElement("label");
  const name = document.createElement("span");
  name.textContent = item.name;
  const kind = soldKind(item.id);
  if (kind) {
    const small = document.createElement("small");
    small.textContent = ` ${kind}`;
    name.append(small);
  }
  const box = document.createElement("input");
  box.type = "number";
  box.min = "1";
  box.step = "1";
  box.inputMode = "numeric";
  box.placeholder = "Not sold";
  box.dataset.id = item.id;
  box.dataset.name = item.name;
  label.append(name, box);
  return label;
}

function fillPrices(prices) {
  for (const box of priceBoxes()) {
    box.value = prices[box.dataset.id] === null ? "" : String(prices[box.dataset.id]);
  }
}

function showPrices(state) {
  const { spent, players } = state.today;
  $("settings-global").hidden = !state.global;
  const people = `${count(players)} player${players === 1 ? "" : "s"}`;
  $("settings-today").textContent = `Today: ${count(spent)} ${state.currency} spent by ${people}.`;
  fillPrices(state.settings);
}

function setStatus(text) {
  $("settings-status").textContent = text;
}

function allowSaving(allowed) {
  $("save-settings").disabled = !allowed;
  $("reset-settings").disabled = !allowed;
}

async function openPrices(hub) {
  const dialog = $("settings");
  pricesLoad += 1;
  const load = pricesLoad;
  $("prices").replaceChildren();
  allowSaving(false);
  setStatus("Loading...");
  dialog.showModal();
  try {
    const state = await answerOf(hub.api("shop_settings"));
    if (load !== pricesLoad || !dialog.open) {
      return;
    }
    if (!state.settings) {
      dialog.close();
      $("open-settings").hidden = true;
      return;
    }
    $("prices").replaceChildren(...Object.entries(state.names).map(([id, name]) => priceBox({ id, name })));
    catalogPrices = state.defaults;
    showPrices(state);
    setStatus("");
    allowSaving(true);
  } catch (e) {
    if (load === pricesLoad) {
      setStatus(e.message);
    }
  }
}

// An empty box goes as null, which means not sold. A box holding something that isn't a number also reads as empty,
// so it stops the save instead of quietly taking the item off sale
async function savePrices(hub) {
  const unreadable = priceBoxes().find((box) => box.validity.badInput);
  if (unreadable) {
    setStatus(`The ${unreadable.dataset.name} price isn't a number.`);
    return;
  }
  const settings = {};
  for (const box of priceBoxes()) {
    settings[box.dataset.id] = box.value === "" ? null : Number(box.value);
  }
  const load = pricesLoad;
  setStatus("Saving...");
  try {
    const state = await answerOf(hub.api("save_shop", { settings }));
    if (load === pricesLoad) {
      showPrices(state);
      setStatus("Saved.");
    }
    // The crate and party buttons follow the new prices at once
    loadExtras();
  } catch (e) {
    if (load === pricesLoad) {
      setStatus(e.message);
    }
  }
}

// Players who can't change the prices get none, and never see the gear
export async function bindSettings(hub) {
  $("open-settings").addEventListener("click", () => openPrices(hub));
  $("save-settings").addEventListener("click", () => savePrices(hub));
  $("reset-settings").addEventListener("click", () => {
    fillPrices(catalogPrices);
    setStatus("Reset. Save to keep it.");
  });
  $("close-settings").addEventListener("click", () => $("settings").close());
  try {
    const state = await hub.api("shop_settings");
    $("open-settings").hidden = !state.settings;
  } catch (e) {
    console.warn("Penguin Wars: couldn't load the shop settings", e);
  }
}

// ---------- Tuning (bot owner) ----------

// How long after the last slider move the numbers go to the bot, so a drag sends one save and not hundreds
const SAVE_WAIT_MS = 300;

const tuning = {
  hub: null,
  // Which opening of the panel this is, so an answer meant for an earlier one can't touch the rows
  load: 0,
  sliders: null,
  defaults: null,
  // The numbers the sliders hold now
  values: {},
  inputs: new Map(),
  timer: null,
  // Saves go one after another, so an older one can't land after a newer one
  saving: Promise.resolve(),
};

function setTuningStatus(text) {
  $("tuning-status").textContent = text;
}

// How many decimals a step has, so 0.05 shows as 0.55 and 0.5 as 6.5
function decimals(step) {
  return (String(step).split(".")[1] ?? "").length;
}

function showNumber(name, value) {
  tuning.inputs.get(name).output.textContent = value.toFixed(decimals(tuning.sliders[name].step));
}

function tuningRow(name) {
  const { label, low, high, step } = tuning.sliders[name];
  const row = document.createElement("label");
  row.className = "slider-row";
  const text = document.createElement("span");
  text.textContent = label;
  const output = document.createElement("output");
  const input = document.createElement("input");
  Object.assign(input, { type: "range", min: low, max: high, step });
  input.dataset.name = name;
  input.value = tuning.values[name];
  input.addEventListener("input", () => {
    tuning.values[name] = Number(input.value);
    showNumber(name, tuning.values[name]);
    scheduleSave();
  });
  row.append(text, output, input);
  tuning.inputs.set(name, { input, output });
  return row;
}

function fillTuning(state) {
  Object.assign(tuning, { sliders: state.sliders, defaults: state.defaults, values: { ...state.tuning } });
  tuning.inputs.clear();
  $("sliders").replaceChildren(...Object.keys(state.sliders).map(tuningRow));
  for (const name of tuning.inputs.keys()) {
    showNumber(name, tuning.values[name]);
  }
}

async function sendTuning() {
  const load = tuning.load;
  setTuningStatus("Saving...");
  try {
    // keepalive lets a save sent as the player leaves finish after the page is gone
    await answerOf(tuning.hub.api("save_tuning", { tuning: { ...tuning.values } }, { keepalive: true }));
    if (load === tuning.load && tuning.timer === null) {
      setTuningStatus("Saved.");
    }
  } catch (e) {
    if (load === tuning.load) {
      await showBotNumbers(load, e.message);
    }
  }
}

// After a save the bot refused or never answered, the sliders go back to what the bot really has
async function showBotNumbers(load, problem) {
  setTuningStatus(problem);
  try {
    const state = await answerOf(tuning.hub.api("tuning"));
    if (load === tuning.load && tuning.timer === null && state.tuning) {
      fillTuning(state);
    }
  } catch (e) {
    console.warn("Penguin Wars: couldn't read the tuning again", e);
  }
}

// Sends the numbers now. A save already on its way finishes first
function flushTuning() {
  clearTimeout(tuning.timer);
  tuning.timer = null;
  tuning.saving = tuning.saving.then(sendTuning);
}

function scheduleSave() {
  clearTimeout(tuning.timer);
  setTuningStatus("Changed...");
  tuning.timer = setTimeout(flushTuning, SAVE_WAIT_MS);
}

async function openTuning() {
  const dialog = $("tuning");
  tuning.load += 1;
  const { load } = tuning;
  // A close that has not been heard yet still owes its save
  if (tuning.timer !== null) {
    flushTuning();
  }
  $("sliders").replaceChildren();
  setTuningStatus("Loading...");
  // show, not showModal: the game stays playable and the sliders sit beside the ice
  dialog.show();
  try {
    // A save from just before the panel was shut has to land first, or this reads the numbers from before it
    await tuning.saving;
    const state = await answerOf(tuning.hub.api("tuning"));
    if (load !== tuning.load || !dialog.open) {
      return;
    }
    if (!state.tuning) {
      dialog.close();
      $("open-tuning").hidden = true;
      return;
    }
    fillTuning(state);
    setTuningStatus("");
  } catch (e) {
    if (load === tuning.load) {
      setTuningStatus(e.message);
    }
  }
}

function resetTuning() {
  if (!tuning.defaults) {
    return;
  }
  tuning.values = { ...tuning.defaults };
  for (const [name, { input }] of tuning.inputs) {
    input.value = tuning.values[name];
    showNumber(name, tuning.values[name]);
  }
  scheduleSave();
}

// Only the bot owner gets the icon. The bot checks again on every save
export async function bindTuning(hub) {
  tuning.hub = hub;
  $("open-tuning").addEventListener("click", () => ($("tuning").open ? $("tuning").close() : openTuning()));
  $("reset-tuning").addEventListener("click", resetTuning);
  $("close-tuning").addEventListener("click", () => $("tuning").close());
  // A save still waiting when the panel shuts goes out at once
  const flushWaiting = () => {
    if (tuning.timer !== null) {
      flushTuning();
    }
  };
  $("tuning").addEventListener("close", flushWaiting);
  // Captured, so the save is sent before the menu takes the page away
  $("back").addEventListener("click", flushWaiting, true);
  window.addEventListener("pagehide", flushWaiting);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      flushWaiting();
    }
  });
  try {
    const state = await answerOf(hub.api("tuning"));
    $("open-tuning").hidden = !state.tuning;
  } catch (e) {
    console.warn("Penguin Wars: couldn't load the tuning", e);
  }
}

// ---------- Sound ----------

// Saved on this device. "on" under the mute key means the effects are off. The volume is 0 to 100
const MUTE_KEY = "penguinwars:muted";
const VOLUME_KEY = "penguinwars:sfx-volume";
// Played as the slider is let go, so the player hears the new level
const VOLUME_SAMPLE = "bonk";

function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    console.warn("Penguin Wars: couldn't read a sound setting", e);
    return null;
  }
}

function saveSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    console.warn("Penguin Wars: couldn't save a sound setting", e);
  }
}

// Anything missing, or not a number from 0 to 100, means full volume
function readVolume() {
  const saved = readSetting(VOLUME_KEY)?.trim();
  const volume = saved ? Number(saved) : NaN;
  return volume >= 0 && volume <= 100 ? volume : 100;
}

// The switch, and the bar's speaker, which is crossed out while the effects are off. The speakers are SVG, which has
// no hidden property, so the attribute itself is set
function showMuted(muted) {
  $("sfx-switch").setAttribute("aria-checked", String(!muted));
  $("sound-on").toggleAttribute("hidden", muted);
  $("sound-off").toggleAttribute("hidden", !muted);
}

function showVolume(slider) {
  slider.style.setProperty("--level", `${slider.value}%`);
}

// A press outside the panel closes it, as long as it also started outside, so a mouse pressed on the panel and let go
// past its edge doesn't. The panel's clear backdrop takes that press, so it never reaches the ice or a button
function closeOnPressOutside(panel) {
  let outside = false;
  panel.addEventListener("pointerdown", (e) => {
    const box = panel.getBoundingClientRect();
    outside = e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom;
  });
  panel.addEventListener("click", (e) => {
    if (outside && e.target === panel) {
      panel.close();
    }
  });
}

// The sound button opens the panel and closes it again, and so do a press outside and Escape. The switch turns the
// effects on and off. The slider sets how loud they are as it moves, and is saved once let go
export function bindSound(sound, beforeOpen) {
  const panel = $("sound-panel");
  const button = $("mute");
  const slider = $("sfx-volume");
  button.addEventListener("click", () => {
    if (panel.open) {
      panel.close();
      return;
    }
    beforeOpen();
    panel.showModal();
    button.setAttribute("aria-expanded", "true");
  });
  panel.addEventListener("close", () => button.setAttribute("aria-expanded", "false"));
  closeOnPressOutside(panel);
  $("sfx-switch").addEventListener("click", () => {
    sound.muted = !sound.muted;
    showMuted(sound.muted);
    saveSetting(MUTE_KEY, sound.muted ? "on" : "off");
  });
  slider.addEventListener("input", () => {
    showVolume(slider);
    sound.setVolume(Number(slider.value));
  });
  slider.addEventListener("change", () => {
    saveSetting(VOLUME_KEY, slider.value);
    sound.play(VOLUME_SAMPLE);
  });
  // The slider snaps a saved number to its own steps, and the sound follows what it shows
  slider.value = String(readVolume());
  showVolume(slider);
  sound.setVolume(Number(slider.value));
  sound.muted = readSetting(MUTE_KEY) === "on";
  showMuted(sound.muted);
}
