// The pawn shops: King-O-Pawn in Uptown (shop set 2) and in Canal Park (shop set 1), nine pedestals each (setupShop
// F4:4601, setShopInteractiveVars F4:4558, buyItem F4:4566, the shop sets F4:26522-26592). Stock is endless and nothing
// can be sold. A pedestal's picture and price are set when the room is built; E on one asks "BUY <NAME> FOR $<cost>"
// in the dialog box, and BUY takes the cash and puts the item in the backpack.
//
// The price is the list price less half the raw Smarts skill in percent, rounded up (discountCost F4:4553): Smarts
// 60 pays 70 percent. The raw skill is used, not the adjusted one. The price shown and the price charged are the ones
// worked out when the room was built.
import { data } from "./data.js";
import { dressPickup, itemName } from "./drops.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { register } from "./interact.js";
import { addItem } from "./inventory.js";
import { fadeInBox, fadeOutBox, finger, setAlpha } from "./panels.js";
import { onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

const KIND = "shop";
const PAUSE = "shop";
// The dialog box stands in the middle of the stage; its shade and its fade as the original's showDialogBox draws them
// (F4:20000-20044)
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
const ASK_BODY = "DO YOU WANT TO BUY\r\r";
const NO_CASH = {
  heading: "NOT ENOUGH CASH",
  body: "\rYOU DON'T HAVE ENOUGH\rCASH TO PURCHASE THIS ITEM.",
};
// An ammo pack's ref: the ammo type and how many rounds it holds ("ammo556_50")
const AMMO_PACK = /^ammo(.+)_(\d+)$/;
const MOST_RECORDED = 100;

// Registers fn(key, amount) for each counter the shop adds to: "spendBig" for the dollars of a purchase (checkAch
// F4:4583)
const countListeners = [];
// What was asked, bought and refused, newest last, for checks
const log = [];
// The pedestals of the room built now, by number: { number, ref, item, name, cost }
let pedestals = {};
// The dialog box over the room, or null
let dialog = null;
let page = null;
let depth = 0;

export function onShopCount(fn) {
  countListeners.push(fn);
}

function count(key, amount) {
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function note(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- What is for sale ----------

// The price of a list price for this player (discountCost F4:4553), with the raw Smarts skill
export function discountCost(list) {
  return Math.ceil(list * ((100 - story.player.skills.smarts / 2) / 100));
}

// A shop ref as the item pictures and names read it: an ammo pack is { kind: "ammo", ref: the type, count }, anything
// else { kind: "item", ref }
function stockItem(ref) {
  const pack = AMMO_PACK.exec(ref);
  if (pack && data.items.ammoTypes.includes(pack[1])) {
    return { kind: "ammo", ref: pack[1], count: Number(pack[2]) };
  }
  return { kind: "item", ref };
}

function pedestalNumber(name) {
  return Number(name.slice(KIND.length));
}

// Each pedestal of the room's shop set, priced for the player now
function stock() {
  const set = data.items.shops[String(room.def.shopSet)] ?? [];
  const found = {};
  for (const entry of set) {
    const item = stockItem(entry.ref);
    found[entry.num] = {
      number: entry.num,
      ref: entry.ref,
      item,
      name: itemName(item),
      cost: discountCost(entry.cost),
    };
  }
  return found;
}

// ---------- The room ----------

// Each pedestal shows its item and its price (setupShop F4:4601)
function dressPedestals() {
  const bg = room.clip?.child("bg");
  if (!bg) {
    return;
  }
  for (const entry of Object.values(pedestals)) {
    const icon = bg.child(`item${entry.number}`)?.child("itemIcon");
    if (icon) {
      dressPickup(icon, entry.item);
    }
    setText(bg.child(`price${entry.number}`), String(entry.cost));
  }
}

function buildRoom() {
  pedestals = room.def?.isShop === true ? stock() : {};
  dressPedestals();
}

// ---------- The dialog box ----------

function closeDialog() {
  const box = dialog;
  if (!box) {
    return;
  }
  dialog = null;
  hud.hidePlay(false);
  fadeOutBox(box, DIALOG.out);
}

// A button of the box: it clicks when pressed, rolls over with a sound for a mouse and does its action on release
function dialogButton(box, name, words, action) {
  const button = box.child(name);
  button.visible = true;
  setText(button.child("buttonText"), words);
  button.setHandler("onPress", () => {
    input.swallowPress();
    sound.play("sound_interfaceClick");
  });
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

// The box over the room with a heading, words and its buttons ({ button, words, action } each). It shuts everything
// behind it off until a button is pressed
function showDialog(heading, body, buttons) {
  const box = page.attach("dialogBox", depth, "shopDialog");
  box.position.set(DIALOG.x, DIALOG.y);
  dialog = box;
  hud.hidePlay(true);
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), heading);
  setText(box.child("textBoxes").child("bodyText"), body);
  for (const { button, words, action } of buttons) {
    dialogButton(box, button, words, action);
  }
  fadeInBox(box, DIALOG.fade);
}

// ---------- Buying ----------

function leave() {
  closeDialog();
  world.resume(PAUSE);
}

// BUY: the cash is taken, the item goes in the backpack, and the cash counter flashes red (F4:4581-4592)
function buy(entry) {
  if (dialog === null || entry.cost > story.player.cash) {
    return;
  }
  count("spendBig", entry.cost);
  story.player.cash -= entry.cost;
  addItem(entry.ref);
  note("buy", { ref: entry.ref, cost: entry.cost });
  leave();
  hud.cashFlash();
}

// E on a pedestal (buyItem F4:4566): the world stops, and the box asks, or says the cash is short
function ask(entry) {
  world.pause(PAUSE);
  if (entry.cost > story.player.cash) {
    note("short", { ref: entry.ref, cost: entry.cost });
    showDialog(NO_CASH.heading, NO_CASH.body, [{ button: "button3", words: "OK", action: leave }]);
    return;
  }
  note("ask", { ref: entry.ref, cost: entry.cost });
  const name = entry.name.toUpperCase();
  showDialog(`BUY ${name}`, `${ASK_BODY}${name}\rFOR $${entry.cost}`, [
    { button: "button1", words: "BUY", action: () => buy(entry) },
    { button: "button2", words: "CANCEL", action: leave },
  ]);
}

function pedestalOf(thing) {
  return pedestals[pedestalNumber(thing.name)] ?? null;
}

function prompt(thing) {
  const entry = pedestalOf(thing);
  return entry ? `[E] BUY ${entry.name.toUpperCase()} FOR $${entry.cost}` : null;
}

function use(thing) {
  const entry = pedestalOf(thing);
  if (entry && !dialog) {
    ask(entry);
  }
}

export function initShop(owner, band) {
  page = owner;
  depth = band;
  register(KIND, { prompt, use, look: { icon: "shopIcon" } });
  onRoom("build", buildRoom);
  world.onReset(() => {
    if (dialog) {
      hud.hidePlay(false);
      dialog.destroy({ children: true });
    }
    dialog = null;
    pedestals = {};
    log.length = 0;
  });
}

export const shop = {
  onCount: onShopCount,
  discountCost,
  get pedestals() {
    return pedestals;
  },
  get isAsking() {
    return dialog !== null;
  },
};

// Helpers for page.py checks
export const shopDebug = {
  // Each pedestal as the room shows it: its number, item, price and the price text on the art
  shopState() {
    const bg = room.clip?.child("bg");
    return {
      set: room.def?.shopSet ?? null,
      smarts: story.player?.skills.smarts,
      cash: story.player?.cash,
      pedestals: Object.values(pedestals).map((each) => ({
        number: each.number,
        ref: each.ref,
        name: each.name,
        cost: each.cost,
        text: bg?.child(`price${each.number}`)?.text ?? null,
      })),
      dialog: dialog && {
        heading: dialog.child("textBoxes").child("headingText").text,
        body: dialog.child("textBoxes").child("bodyText").text,
        buttons: ["button1", "button2", "button3"]
          .filter((name) => dialog.child(name).visible)
          .map((name) => `${name}: ${dialog.child(name).child("buttonText").text}`),
      },
      paused: world.paused,
    };
  },

  // E on pedestal n, whatever the player's place
  shopAsk(number) {
    ask(pedestals[number]);
    return shopDebug.shopState();
  },

  // The open dialog's BUY (true) or CANCEL and OK (false)
  shopAnswer(yes) {
    const names = yes ? ["button1"] : ["button2", "button3"];
    const name = names.find((each) => dialog?.child(each).visible);
    dialog?.child(name).handlers.onRelease?.();
    return shopDebug.shopState();
  },

  // Where the middle of a part of the open dialog ("button1") is, in the game frame's CSS pixels
  shopPoint(path) {
    const node = dialog?.child(path);
    if (!node) {
      return null;
    }
    const box = node.getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    return {
      x: Math.round(canvas.left + (box.x + box.width / 2) * (canvas.width / page.app.screen.width)),
      y: Math.round(canvas.top + (box.y + box.height / 2) * (canvas.height / page.app.screen.height)),
    };
  },

  // What was asked, bought and refused so far
  shopLog() {
    return log.map((each) => ({ ...each }));
  },
};
