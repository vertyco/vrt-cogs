// The player's menus, as in the original: money and experience on the left, training in the middle, and the
// wooden menu on the right. Every picture is the original's own button art, drawn once when the page loads, and
// every button sits where the original put it on its 650 by 120 strip.

// Names and prices, from the original's tables (ageofwar/common/data.py has the same; tests/test_page.py checks)
export const UNITS = {
  1: ["Club man", 15],
  2: ["Slingshot man", 25],
  3: ["Dino rider", 100],
  4: ["Sword man", 50],
  5: ["Archer", 75],
  6: ["Knight", 500],
  7: ["Dueler", 200],
  8: ["Mousquettere", 400],
  9: ["Canoneer", 1000],
  10: ["Melee Infantry", 1500],
  11: ["Infantry", 2000],
  12: ["Tank", 7000],
  13: ["God's Blade", 5000],
  14: ["Blaster", 6000],
  15: ["War machine", 20000],
  16: ["Super Soldier", 150000],
};
export const TURRETS = {
  1: ["Rock slingshot", 100],
  2: ["Egg automatic", 200],
  3: ["Primitive Catapult", 500],
  4: ["Catapult", 500],
  5: ["Fire Catapult", 750],
  6: ["Oil", 1000],
  7: ["Small Cannon", 1500],
  8: ["Large Cannon", 3000],
  9: ["Explosives Cannon", 6000],
  10: ["Single Turret", 7000],
  11: ["Rocket Turret", 9000],
  12: ["Double Turret", 14000],
  13: ["Titanium Shooter", 24000],
  14: ["LazerCannon", 40000],
  15: ["IonRay", 100000],
};
export const EVOLVE_XP = [4000, 14000, 45000, 200000];
export const SPOT_PRICES = [1000, 3000, 7500];
export const SPECIAL_COOLDOWN = 2000;

// The original's button characters: each age's unit and turret buttons, the main menu, back and cancel
const UNIT_BUTTONS = [
  [89, 92, 101],
  [103, 105, 107],
  [109, 111, 113],
  [115, 117, 119],
  [122, 138, 140, 141],
];
const TURRET_BUTTONS = [
  [145, 147, 149],
  [151, 153, 155],
  [157, 159, 161],
  [163, 165, 167],
  [169, 171, 176],
];
const MAIN_BUTTONS = [179, 181, 184, 186, 188];
const SPECIAL_BUTTONS = [58, 71, 73, 75, 77];
// Where each row starts on the original's strip (its buttons are 40 apart), and the back button's place
const ROWS = { main: [433, 24], units: [442, 24], turrets: [433, 24] };
const BACK = { units: [83, 613, 24], turrets: [143, 604, 24] };
const CANCEL = { place: 195, sell: 196 };
const CANCEL_AT = [534.2, 41, 0.72];
const SPECIAL_AT = [614.2, 85.9];
const SPECIAL_FRAME = 59;
const TRAY_EMPTY = 209;
const TRAY_FULL = 210;
const MENU_ART = 212;
// The menu's parts that the page draws itself, hidden when its background is drawn
const MENU_PARTS = ["bf1", "bt1", "m1", "btc", "stc", "prog", "t1", "t2", "t3", "t4", "t5"];
// The left strip ends where the menu's wood begins
export const SPLIT = 410;
export const STRIP = { width: 650, height: 120 };

const TITLES = { main: "Menu", units: "Menu - Units", turrets: "Menu - Turrets", place: "Menu - Turrets", sell: "Sell a turret" };

function el(tag, className, parent) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  parent?.appendChild(node);
  return node;
}

// A button made from one of the original's button characters: its up picture, and its over picture on hover
function artButton(parent, pictures, x, y, scale = 1) {
  const { up, over } = pictures;
  const button = el("button", "art", parent);
  button.type = "button";
  button.style.left = `${x + up.x * scale}px`;
  button.style.top = `${y + up.y * scale}px`;
  button.style.width = `${up.width * scale}px`;
  button.style.height = `${up.height * scale}px`;
  button.style.backgroundImage = `url(${up.url})`;
  button.style.setProperty("--over", `url(${over.url})`);
  return button;
}

export class Hud {
  constructor(root, scene, send) {
    this.root = root;
    this.scene = scene;
    this.send = send;
    this.menu = "main";
    this.view = null;
    this.hoverText = "";
    this.pressedText = "";
    this.pressedTimer = null;
    this.pictures = new Map();
    this.build();
  }

  picture(id, state = "u") {
    const key = `${id}:${state}`;
    if (!this.pictures.has(key)) {
      this.pictures.set(key, this.scene.picture(id, state));
    }
    return this.pictures.get(key);
  }

  buttonPictures(id) {
    return { up: this.picture(id, "u"), over: this.picture(id, "o") };
  }

  // ---------- Building ----------

  build() {
    this.root.replaceChildren();
    this.left = el("div", "strip left", this.root);
    this.right = el("div", "strip right", this.root);
    const art = this.menuArt();
    for (const strip of [this.left, this.right]) {
      const offset = strip === this.left ? 0 : SPLIT;
      strip.style.backgroundImage = `url(${art.url})`;
      strip.style.backgroundSize = `${art.width}px ${art.height}px`;
      strip.style.backgroundPosition = `${art.x - offset}px ${art.y}px`;
    }
    this.buildLeft();
    this.buildRight();
  }

  // The menu's wooden panels, coin and bar frame, as one picture
  menuArt() {
    return this.scene.picture(MENU_ART, null, 2, (clip) => {
      for (const name of MENU_PARTS) {
        const part = clip.child(name);
        if (part) {
          part.visible = false;
        }
      }
      for (const slot of clip.slots.values()) {
        if (slot.node.charId === 78) {
          slot.node.visible = false;
        }
      }
    });
  }

  buildLeft() {
    this.cash = this.shadowText(this.left, "cash", 20, 7);
    this.xp = this.shadowText(this.left, "xp", 30, 25);
    this.bar = el("div", "progress", this.left);
    this.barFill = el("div", "fill", this.bar);
    this.training = el("p", "training", this.left);
    this.desc = el("p", "desc", this.left);
    this.tray = [];
    for (let i = 0; i < 5; i += 1) {
      const square = el("img", "tray", this.left);
      square.alt = "";
      const empty = this.picture(TRAY_EMPTY, null);
      square.src = empty.url;
      square.style.left = `${349.5 + 12 * i + empty.x}px`;
      square.style.top = `${4.5 + empty.y}px`;
      square.style.width = `${empty.width}px`;
      square.style.height = `${empty.height}px`;
      this.tray.push(square);
    }
  }

  shadowText(parent, className, x, y) {
    const text = el("span", `shadow ${className}`, parent);
    text.style.left = `${x}px`;
    text.style.top = `${y}px`;
    return text;
  }

  buildRight() {
    this.title = el("span", "title", this.right);
    this.title.style.left = `${433 - SPLIT}px`;
    this.title.style.top = "5px";
    this.rows = {};
    this.rows.main = el("div", "row", this.right);
    MAIN_BUTTONS.forEach((id, index) => {
      const button = artButton(this.rows.main, this.buttonPictures(id), ROWS.main[0] - SPLIT + 40 * index, ROWS.main[1]);
      this.wire(button, () => this.mainButton(index), () => this.mainText(index));
    });
    this.unitRows = UNIT_BUTTONS.map((ids, age) => this.itemRow("units", ids, age, (kind) => this.buyUnit(kind)));
    this.turretRows = TURRET_BUTTONS.map((ids, age) => this.itemRow("turrets", ids, age, (kind) => this.pickTurret(kind)));
    for (const kind of ["place", "sell"]) {
      const [x, y, scale] = CANCEL_AT;
      const row = el("div", "row", this.right);
      const button = artButton(row, this.buttonPictures(CANCEL[kind]), x - SPLIT, y, scale);
      this.wire(button, () => this.setMenu("main"), () => "");
      this.rows[kind] = row;
    }
    this.special = el("div", "special", this.right);
    this.specialButtons = SPECIAL_BUTTONS.map((id) => {
      const button = artButton(this.special, this.buttonPictures(id), SPECIAL_AT[0] - SPLIT, SPECIAL_AT[1]);
      this.wire(button, () => this.send({ special: true }), () => "");
      return button;
    });
    const frame = this.picture(SPECIAL_FRAME, null);
    const ring = el("img", "special-frame", this.special);
    ring.alt = "";
    ring.src = frame.url;
    ring.style.left = `${SPECIAL_AT[0] - SPLIT + frame.x}px`;
    ring.style.top = `${SPECIAL_AT[1] + frame.y}px`;
    ring.style.width = `${frame.width}px`;
    ring.style.height = `${frame.height}px`;
    this.cooldown = el("div", "cooldown", this.special);
    const first = this.specialButtons[0];
    for (const prop of ["left", "top", "width", "height"]) {
      this.cooldown.style[prop] = first.style[prop];
    }
  }

  itemRow(kind, ids, age, act) {
    const row = el("div", "row", this.right);
    const [x0, y0] = ROWS[kind];
    ids.forEach((id, index) => {
      const item = kind === "units" ? (age === 4 && index === 3 ? 16 : age * 3 + index + 1) : age * 3 + index + 1;
      const button = artButton(row, this.buttonPictures(id), x0 - SPLIT + 40 * index, y0);
      this.wire(button, () => act(item), () => this.itemText(kind, item));
    });
    const [backId, bx, by] = BACK[kind];
    const back = artButton(row, this.buttonPictures(backId), bx - SPLIT, by);
    this.wire(back, () => this.setMenu("main"), () => "Return to previous menu");
    return row;
  }

  // Hover shows the original's description. A touch has no hover, so a press shows it for a moment instead
  wire(button, press, text) {
    button.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "mouse") {
        this.hoverText = text();
        this.showDesc();
      }
    });
    button.addEventListener("pointerleave", (event) => {
      if (event.pointerType === "mouse") {
        this.hoverText = "";
        this.showDesc();
      }
    });
    button.addEventListener("click", () => {
      const before = text();
      press();
      if (before) {
        this.pressedText = before;
        clearTimeout(this.pressedTimer);
        this.pressedTimer = setTimeout(() => {
          this.pressedText = "";
          this.showDesc();
        }, 1500);
      }
      this.showDesc();
    });
  }

  showDesc() {
    this.desc.textContent = this.hoverText || this.pressedText;
  }

  // ---------- The menus ----------

  setMenu(menu, turret = 0) {
    this.menu = menu;
    this.hoverText = "";
    this.showDesc();
    this.scene.setMode(menu === "place" || menu === "sell" ? menu : "none", turret, this.view);
    this.render();
  }

  mainButton(index) {
    if (index === 0) {
      this.setMenu("units");
    } else if (index === 1) {
      this.setMenu("turrets");
    } else if (index === 2) {
      this.setMenu("sell");
    } else if (index === 3) {
      this.send({ spot: true });
    } else {
      this.send({ evolve: true });
    }
  }

  mainText(index) {
    const view = this.view;
    if (index === 0) {
      return "Train units menu";
    }
    if (index === 1) {
      return "Build turrets menu";
    }
    if (index === 2) {
      return "Sell a turret";
    }
    if (index === 3) {
      return view && view[3] < 3 ? `${SPOT_PRICES[view[3]]}$ - Add a turret spot` : "Can't build any more";
    }
    return view && view[2] < 5 ? `${EVOLVE_XP[view[2] - 1]} Xp - Evolve to next age` : "You cannot evolve anymore";
  }

  itemText(kind, item) {
    const [name, price] = (kind === "units" ? UNITS : TURRETS)[item];
    return `${price}$ - ${name}`;
  }

  buyUnit(kind) {
    this.send({ buy: kind });
  }

  pickTurret(kind) {
    if (this.view && this.view[0] >= TURRETS[kind][1]) {
      this.setMenu("place", kind);
    }
  }

  // A spot on the base was pressed, in the turret or the selling menu
  spot(press) {
    if (this.menu === "place" && press.build) {
      this.send({ build: [this.scene.mode.turret, press.build] });
      this.setMenu("main");
    } else if (this.menu === "sell" && press.sell) {
      this.send({ sell: press.sell });
      this.setMenu("main");
    }
  }

  spotHover(kind, spot) {
    if (kind === "sell" && spot && this.view) {
      const turret = this.view[10][spot - 1];
      if (turret) {
        const [name, price] = TURRETS[turret[0]];
        this.hoverText = `Sell ${name} for ${Math.floor(price / 2 + 0.5)}$`;
      }
    } else {
      this.hoverText = "";
    }
    this.showDesc();
  }

  // ---------- Updates ----------

  // The player's side, from the bot: [cash, xp, age, spots, health, most, training, progress, queue, special, turrets]
  update(view) {
    const before = this.view;
    this.view = view;
    const [cash, xp, age, , , , training, progress, tray, special] = view;
    this.cash.textContent = String(cash);
    this.xp.textContent = String(xp);
    this.barFill.style.width = `${progress}%`;
    this.training.textContent = training ? `Training ${UNITS[training][0]}...` : "";
    tray.forEach((kind, index) => {
      const picture = this.picture(kind ? TRAY_FULL : TRAY_EMPTY, null);
      if (this.tray[index].dataset.full !== String(Boolean(kind))) {
        this.tray[index].dataset.full = String(Boolean(kind));
        this.tray[index].src = picture.url;
      }
    });
    const ready = special >= SPECIAL_COOLDOWN;
    this.cooldown.style.setProperty("--left", `${(1 - special / SPECIAL_COOLDOWN) * 360}deg`);
    this.cooldown.hidden = ready;
    this.special.classList.toggle("ready", ready);
    if (!before || before[2] !== age || before[3] !== view[3] || String(before[10]) !== String(view[10])) {
      if (this.menu === "place" || this.menu === "sell") {
        this.scene.setMode(this.menu, this.scene.mode.turret, view);
      }
      this.render();
    }
    if (this.hoverText) {
      this.showDesc();
    }
  }

  render() {
    const age = this.view ? this.view[2] : 1;
    this.title.textContent = TITLES[this.menu];
    this.title.dataset.text = TITLES[this.menu];
    this.rows.main.hidden = this.menu !== "main";
    this.unitRows.forEach((row, index) => {
      row.hidden = !(this.menu === "units" && index === age - 1);
    });
    this.turretRows.forEach((row, index) => {
      row.hidden = !(this.menu === "turrets" && index === age - 1);
    });
    this.rows.place.hidden = this.menu !== "place";
    this.rows.sell.hidden = this.menu !== "sell";
    this.specialButtons.forEach((button, index) => {
      button.hidden = index !== age - 1;
    });
  }

  reset() {
    this.view = null;
    this.hoverText = "";
    this.pressedText = "";
    this.setMenu("main");
  }
}
