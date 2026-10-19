// The ring menu: tap a spot and its choices pop up around it, drawn on the canvas in screen pixels so every button
// stays thumb sized however small the map is drawn. Also the parking mode for a Drone bay's drones: the road lights
// up where they can go, and the next tap picks the place. The choice in focus (under the mouse, or picked by a first
// tap on a touch screen, which a second tap buys) is lit, and the range circle shows what it would reach.
import { Container, Graphics, Text } from "../vendor/pixi.min.mjs";
import { canPark, nearestRoad, pointAt, ROAD_LENGTH } from "../sim/road.js";
import { DRONE, DRONES, MAP, SELL_BACK, TOWERS } from "../sim/rules.js";
import { stats } from "../sim/towers.js";
import { towerIcon } from "./towers.js";
import { toView } from "./view.js";

// Each button's radius on screen (52 px across), and how far from the ring's middle the buttons sit
const BUTTON = 26;
const REACH = 70;
// A price label hangs this far below the bottom button's middle (its radius, the gap and the text's height), and a
// long label (a final form's name and price) reaches this much further out to the sides than the button does
const LABEL_BELOW = BUTTON + 24;
const LONG_LABEL = 16;
// The picked choice's check mark: its radius, and where it sits on the button
const CHECK = 9;
const CHECK_AT = 19;
const FOCUS = 0xb8fff4;
// A tap this close outside a button's edge still counts
const TAP_SLACK = 6;
const ICON_SCALE = 0.7;
// The road's lit dots while parking, this many hundredths of a map unit apart
const LIGHT_EVERY = 500;
// A parking tap must land this close to the road: in map units, and never less than this many pixels on screen
const PARK_TAP = 40;
const PARK_TAP_PX = 24;
const LIVE = 0x5fe3ff;
const DEAD = 0x3a4a55;
const SELL = 0xffd9a0;
const LABEL = {
  fontFamily: "Rajdhani",
  fontWeight: "700",
  fontSize: 15,
  fill: 0xe8fbff,
  stroke: { color: 0x02080d, width: 4 },
};

// The choices for a spot: four towers on an empty one; upgrade (or the two final forms at level 3), move drones on a
// Drone bay, and sell on a built one. price is what it costs (null when free); refund is what selling gives back.
// preview marks the choices a first tap on a touch screen only shows, so a second tap buys them
export function ringOptions(run, spot) {
  const tower = run.towers[spot];
  if (!tower) {
    return TOWERS.map((type, kind) => {
      return { action: `build:${kind}`, icon: [kind, -1], label: "", price: type.levels[0].cost, preview: true };
    });
  }
  const type = TOWERS[tower.kind];
  const options = [];
  if (tower.form < 0 && tower.level < 3) {
    options.push({ action: "upgrade", icon: "up", label: "", price: type.levels[tower.level].cost, preview: true });
  }
  if (tower.form < 0 && tower.level === 3) {
    type.forms.forEach((form, which) => {
      const option = { action: `form:${which}`, icon: [tower.kind, which], label: form.name, price: form.cost };
      options.push({ ...option, preview: true });
    });
  }
  if (tower.kind === DRONES) {
    options.push({ action: "park", icon: "park", label: "Move", price: null });
  }
  const refund = Math.floor((tower.spent * SELL_BACK) / 100);
  options.push({ action: "sell", icon: "sell", label: "Sell", price: null, refund });
  return options;
}

function glyph(icon) {
  if (Array.isArray(icon)) {
    const picture = towerIcon(icon[0], icon[1]);
    picture.scale.set(ICON_SCALE);
    return picture;
  }
  const g = new Graphics();
  if (icon === "up") {
    g.poly([-9, 3, 0, -7, 9, 3, 5, 3, 0, -2, -5, 3]).fill(LIVE);
    g.poly([-9, 10, 0, 0, 9, 10, 5, 10, 0, 5, -5, 10]).fill(LIVE);
  } else if (icon === "sell") {
    g.circle(0, -1, 9).stroke({ width: 2.5, color: SELL });
    g.moveTo(0, -6).lineTo(0, 4).moveTo(-4, 0).lineTo(0, 4).lineTo(4, 0).stroke({ width: 2.5, color: SELL });
  } else {
    g.circle(0, 0, 8).stroke({ width: 2, color: LIVE });
    g.moveTo(-12, 0).lineTo(-4, 0).moveTo(4, 0).lineTo(12, 0).moveTo(0, -12).lineTo(0, -4).moveTo(0, 4).lineTo(0, 12);
    g.stroke({ width: 2, color: LIVE });
  }
  return g;
}

// How far a tower would reach after a ring choice (build, upgrade or final form), or as it stands for any other: its
// range, or how far a Drone bay can place its wall. 0 for an empty spot with no choice in focus
function reachFor(tower, action) {
  const [name, which] = (action ?? "").split(":");
  if (name === "build") {
    const kind = Number(which);
    return kind === DRONES ? DRONE.reach : TOWERS[kind].levels[0].range;
  }
  if (!tower) {
    return 0;
  }
  if (tower.kind === DRONES) {
    return DRONE.reach;
  }
  const type = TOWERS[tower.kind];
  if (name === "upgrade") {
    return type.levels[tower.level].range;
  }
  if (name === "form") {
    return type.forms[Number(which)].range;
  }
  return stats(tower).range;
}

function checkMark() {
  const g = new Graphics().circle(CHECK_AT, -CHECK_AT, CHECK).fill(FOCUS).stroke({ width: 2, color: 0x0b1823 });
  g.moveTo(CHECK_AT - 4, -CHECK_AT).lineTo(CHECK_AT - 1, -CHECK_AT + 3).lineTo(CHECK_AT + 4, -CHECK_AT - 3);
  return g.stroke({ width: 2.5, color: 0x0b1823, cap: "round", join: "round" });
}

function words(option) {
  const amount = option.refund !== undefined ? `+${option.refund}` : option.price !== null ? String(option.price) : "";
  return [option.label, amount].filter(Boolean).join(" ");
}

// Keeps the ring's middle far enough inside the field (the screen inside the bar and Discord's edges) that every
// button stays in it; a field too small for that gets the ring in its middle
function clampInto(value, start, size, before, after) {
  if (size < before + after) {
    return start + size / 2;
  }
  return Math.min(Math.max(value, start + before), start + size - after);
}

export class Ring {
  constructor(scene) {
    this.scene = scene;
    this.layer = new Container();
    // In view units, under the towers: the range circle, and the road's lit dots while parking
    this.marks = new Graphics();
    scene.layers.marks.addChild(this.marks);
    this.spot = -1;
    this.parking = -1;
    // The buttons on show, in page pixels, and what they were drawn from
    this.shown = [];
    this.key = "";
    // The choice under the mouse, the one a first tap picked, and the ring's reach on the page (page pixels)
    this.hovered = null;
    this.picked = null;
    this.reach = null;
  }

  get isOpen() {
    return this.spot >= 0;
  }

  open(spot, run) {
    this.stopParking();
    this.spot = spot;
    this.key = "";
    this.hovered = null;
    this.picked = null;
    this.draw(run, 0);
  }

  close() {
    this.spot = -1;
    this.key = "";
    this.hovered = null;
    this.picked = null;
    this.clearButtons();
    if (this.parking < 0) {
      this.marks.clear();
    }
  }

  startParking(spot, run) {
    this.close();
    this.parking = spot;
    this.drawParking(run);
  }

  stopParking() {
    if (this.parking >= 0) {
      this.parking = -1;
      this.marks.clear();
      this.marks.alpha = 1;
    }
  }

  // The road distance (hundredths) a parking tap picks, or -1 when it isn't on the road within the bay's reach
  parkTarget(map) {
    if (this.parking < 0) {
      return -1;
    }
    const d = nearestRoad(Math.round(map.x * 100), Math.round(map.y * 100));
    const [x, y] = pointAt(d);
    const reach = Math.max(PARK_TAP, PARK_TAP_PX / this.scene.scale);
    const near = (x / 100 - map.x) ** 2 + (y / 100 - map.y) ** 2 <= reach * reach;
    return near && canPark(this.parking, d) ? d : -1;
  }

  // The map moved or changed size: the buttons are placed again on the next draw
  layout() {
    this.key = "";
  }

  buttons() {
    return this.shown.map(({ action, enabled, x, y, size, label }) => {
      return { action, enabled, x, y, r: BUTTON, size, label };
    });
  }

  hit(client) {
    const reach = (BUTTON + TAP_SLACK) ** 2;
    const button = this.shown.find((b) => (b.x - client.x) ** 2 + (b.y - client.y) ** 2 <= reach);
    return button ? { action: button.action, enabled: button.enabled, preview: Boolean(button.preview) } : null;
  }

  /** The mouse moved over the canvas (client in page pixels), or left it (null) */
  hover(client) {
    const hit = client && this.isOpen ? this.hit(client) : null;
    this.hovered = hit ? hit.action : null;
  }

  /** A first tap on a touch screen: show this choice, and buy it on the next tap */
  pick(action) {
    this.picked = action;
  }

  /** The choice the card describes: the one under the mouse, else the one picked, else none (the tower itself) */
  focus() {
    return this.hovered ?? this.picked;
  }

  /** A line under the card for a priced choice, { text, short }: what it still needs, or how to buy a picked one */
  hint(run, action) {
    const option = this.shown.find((b) => b.action === action);
    if (!option || !option.preview) {
      return null;
    }
    if (run.money < option.price) {
      return { text: `Needs ${(option.price - run.money).toLocaleString()} more`, short: true };
    }
    if (action === this.picked) {
      return { text: `Tap again to buy for ${option.price.toLocaleString()}`, short: false };
    }
    return null;
  }

  /** Where the ring's buttons and labels reach on the page, or null while it's closed */
  extent() {
    return this.reach;
  }

  // Where the ring sits: its spot, moved in enough that every button and the price label under the bottom one stay in
  // the field
  center(options) {
    const [x, y] = MAP.spots[this.spot];
    const at = this.scene.mapToClient(x, y);
    const box = this.scene.field;
    const side = REACH + BUTTON + 4 + (options.some((option) => option.label.length > 5) ? LONG_LABEL : 0);
    return {
      x: clampInto(at.x, box.x, box.width, side, side),
      y: clampInto(at.y, box.y, box.height, REACH + BUTTON + 4, REACH + LABEL_BELOW),
    };
  }

  // Each frame: the parking dots pulse, and the buttons are rebuilt only when something they show changed (money
  // crossing a price, the map moving)
  draw(run, t) {
    if (this.parking >= 0) {
      this.marks.alpha = 0.6 + 0.4 * Math.sin(t * 6);
    }
    if (!run || this.spot < 0) {
      if (this.shown.length) {
        this.clearButtons();
      }
      return;
    }
    const options = ringOptions(run, this.spot);
    const center = this.center(options);
    const placed = options.map((option, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / options.length;
      const enabled = option.price === null || run.money >= option.price;
      return { ...option, enabled, x: center.x + Math.cos(angle) * REACH, y: center.y + Math.sin(angle) * REACH };
    });
    const state = placed.map((b) => [b.action, b.enabled, b.price, b.refund]);
    const key = JSON.stringify([center.x, center.y, state, this.hovered, this.picked]);
    if (key === this.key) {
      return;
    }
    this.build(placed, center);
    this.key = key;
    this.shown = placed;
    this.drawRange(run);
  }

  build(placed, center) {
    this.clearButtons();
    const ring = new Graphics().circle(center.x, center.y, REACH).stroke({ width: 2, color: LIVE, alpha: 0.3 });
    this.layer.addChild(ring);
    // Each button's drawn width and its price label's box, in page pixels
    const focus = this.focus();
    for (const option of placed) {
      const button = new Container();
      button.position.set(option.x, option.y);
      const lit = option.action === focus;
      button.alpha = option.enabled || lit ? 1 : 0.45;
      const disc = new Graphics().circle(0, 0, BUTTON).fill({ color: 0x0b1823, alpha: 0.94 });
      disc.stroke({ width: lit ? 3.5 : 2, color: lit ? FOCUS : option.enabled ? LIVE : DEAD });
      button.addChild(disc, glyph(option.icon));
      if (option.action === this.picked) {
        button.addChild(checkMark());
      }
      const label = words(option);
      option.label = null;
      let text = null;
      if (label) {
        text = new Text({ text: label, style: LABEL });
        text.anchor.set(0.5, 0);
        text.y = BUTTON + 2;
        button.addChild(text);
      }
      this.layer.addChild(button);
      option.size = disc.getBounds().width;
      if (text) {
        const { x, y, width, height } = text.getBounds().rectangle;
        option.label = { x, y, width, height };
      }
    }
    this.reach = {
      left: Math.min(...placed.map((b) => Math.min(b.x - BUTTON, b.label ? b.label.x : Infinity))),
      top: Math.min(...placed.map((b) => b.y - BUTTON)),
      right: Math.max(...placed.map((b) => Math.max(b.x + BUTTON, b.label ? b.label.x + b.label.width : -Infinity))),
      bottom: Math.max(...placed.map((b) => (b.label ? b.label.y + b.label.height : b.y + BUTTON))),
    };
  }

  clearButtons() {
    for (const child of this.layer.removeChildren()) {
      child.destroy({ children: true, context: true });
    }
    this.shown = [];
    this.key = "";
    this.reach = null;
  }

  // The reach of the choice in focus, or of the built tower: its range, or how far a Drone bay can place its wall
  drawRange(run) {
    if (this.parking >= 0) {
      return;
    }
    this.marks.clear();
    const reach = reachFor(run.towers[this.spot], this.focus());
    if (!reach) {
      return;
    }
    const [x, y] = toView(...MAP.spots[this.spot]);
    this.marks.circle(x, y, reach).fill({ color: LIVE, alpha: 0.07 }).stroke({ width: 2, color: LIVE, alpha: 0.5 });
  }

  drawParking(run) {
    this.marks.clear();
    for (let d = 0; d <= ROAD_LENGTH; d += LIGHT_EVERY) {
      if (canPark(this.parking, d)) {
        const [x, y] = toView(...pointAt(d));
        this.marks.circle(x / 100, y / 100, 6).fill({ color: 0x7fffd4, alpha: 0.85 });
      }
    }
    const tower = run?.towers[this.parking];
    if (tower) {
      const [x, y] = toView(...pointAt(tower.park));
      this.marks.circle(x / 100, y / 100, 14).stroke({ width: 3, color: 0xffffff, alpha: 0.9 });
    }
  }
}
