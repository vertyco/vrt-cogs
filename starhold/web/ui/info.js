// The info card: what a tower, a wave or a robot is, with its numbers. It shows for a built tower whose ring is open,
// for the ring choice under the mouse or picked by a first tap on a touch screen (an upgrade shows its numbers before
// and after), for the wave button the same way (the robots the next wave brings), and for a robot tapped on the map.
// It floats over the map inside the field: by the ring or the wave button, on whichever side has room without
// covering a button, or for a robot at the bottom between the power buttons. It is rebuilt only when what it shows
// changes.
import { Dice } from "../sim/dice.js";
import { DRONE, DRONES, MISSILE, ROBOTS, SELL_BACK, STEPS, TESLA, TOWERS, WAVES } from "../sim/rules.js";
import { buildWave } from "../sim/waves.js";

// What each tower and final form does, by key
const ROLES = {
  blaster: "Quick shots at one robot. Hits flying robots. Armor halves its damage.",
  missile: "Missiles that burst on a group. Can't hit flying robots. Armor halves its damage.",
  tesla: "Lightning that jumps from robot to robot. Hits flying robots and ignores armor.",
  drones: "Its drones wall off the road. Ground robots pile up there until the drones fall.",
  gatling: "Spins up a stream of very fast shots.",
  railgun: "A slow beam that goes through every robot in a line, flying ones too.",
  swarm: "Six small missiles at once, spread over the robots furthest along.",
  mortar: "A huge, slow shell with a wide blast, from far away.",
  storm: "Lightning that jumps to 8 robots.",
  disruptor: "Lightning that also slows robots down.",
  guardians: "Tough drones that heal while nothing is piled up.",
  strikers: "Drones that hit hard.",
};
// What each robot does and what stops it, by key
const ROBOT_ROLES = {
  scrapper: "Walks the road. Every tower hurts it.",
  skitter: "Small and fast, in threes. A missile's blast catches the whole group.",
  buzzer: "Flies over the road, past Drone bays. Missile pods can't hit it; Blasters and Tesla coils can.",
  brute: "Slow and tough. Armor halves Blaster and Missile damage; Tesla coils ignore it.",
  splitter: "Bursts into 3 Skitters when destroyed.",
  colossus: "The boss, every 10th wave. Armored, and drops Skitters as it walks.",
};
// Gap kept between the card and what it describes, the field's edge and the buttons, in page pixels
const MARGIN = 8;
const WIDEST = 300;
// The power buttons' size and gap from the screen's edge, which a robot's card stays clear of
const POWER = 56;

function $(id) {
  return document.getElementById(id);
}

function speed(every) {
  if (every <= STEPS) {
    const shots = Math.round((STEPS / every) * 10) / 10;
    return `${shots}/s`;
  }
  return `every ${Math.round((every / STEPS) * 10) / 10} s`;
}

// A tower's numbers at one level or form, as [label, value] in the order the card lists them
function numbers(kind, at) {
  if (kind === DRONES) {
    const rows = [
      ["Drones", String(DRONE.count)],
      ["Drone health", String(at.hp)],
      ["Damage", `${at.damage}/s`],
    ];
    return at.heal ? [...rows, ["Heals", `${at.heal}/s`]] : rows;
  }
  const rows = [["Damage", String(at.damage)]];
  if (kind === MISSILE) {
    if (at.missiles) {
      rows.push(["Missiles", String(at.missiles)]);
    }
    rows.push(["Blast", String(at.blast)]);
  }
  if (kind === TESLA) {
    rows.push(["Jumps to", String(at.chain)]);
    if (at.slow) {
      rows.push(["Slows", `${at.slow}% for ${at.slowFor / STEPS} s`]);
    }
  }
  rows.push(["Speed", speed(at.every)], ["Range", String(at.range)]);
  return rows;
}

// Before and after, for an upgrade: each number that changes shows both
function changes(kind, from, to) {
  const before = new Map(numbers(kind, from));
  return numbers(kind, to).map(([label, value]) => {
    const old = before.get(label);
    return [label, old !== undefined && old !== value ? `${old} → ${value}` : value];
  });
}

function levelName(tower) {
  return tower.form >= 0 ? "Final form" : `Level ${tower.level}`;
}

/** What the card shows for a spot and the ring choice in focus (null for the built tower itself), or null for none */
export function cardFor(run, spot, action) {
  const tower = run.towers[spot];
  const [name, which] = (action ?? "").split(":");
  if (name === "build") {
    const type = TOWERS[Number(which)];
    return { title: type.name, tag: "", text: ROLES[type.key], rows: numbers(Number(which), type.levels[0]) };
  }
  if (!tower) {
    return null;
  }
  const type = TOWERS[tower.kind];
  const now = tower.form >= 0 ? type.forms[tower.form] : type.levels[tower.level - 1];
  if (name === "upgrade") {
    const next = type.levels[tower.level];
    const text = `Upgrade ${type.name} to level ${tower.level + 1}.`;
    return { title: type.name, tag: `Level ${tower.level + 1}`, text, rows: changes(tower.kind, now, next) };
  }
  if (name === "form") {
    const form = type.forms[Number(which)];
    return { title: form.name, tag: "Final form", text: ROLES[form.key], rows: changes(tower.kind, now, form) };
  }
  if (name === "sell") {
    const refund = Math.floor((tower.spent * SELL_BACK) / 100);
    const text = `Gives back ${SELL_BACK}% of everything spent on it: ${refund}.`;
    return { title: `Sell ${type.name}`, tag: "", text, rows: [] };
  }
  if (name === "park") {
    const text = "Then tap the lit road where its wall should stand.";
    return { title: "Move drones", tag: "", text, rows: [] };
  }
  const title = tower.form >= 0 ? now.name : type.name;
  const role = tower.form >= 0 ? ROLES[now.key] : ROLES[type.key];
  return { title, tag: levelName(tower), text: role, rows: numbers(tower.kind, now) };
}

// The next wave's robots by type, in the order they first come in. The wave is drawn from a copy of the run's dice,
// which nothing else rolls, so it is exactly the wave that will come
const preview = { key: "", counts: [] };

function nextWave(run) {
  const key = `${run.wave}/${run.dice.state}`;
  if (preview.key !== key) {
    const counts = new Map();
    for (const entry of buildWave({ dice: new Dice(run.dice.state) }, run.wave + 1)) {
      counts.set(entry.type, (counts.get(entry.type) ?? 0) + 1);
    }
    preview.key = key;
    preview.counts = [...counts];
  }
  return preview.counts;
}

/** What the card shows for the wave button: the robots the next wave brings, and the money for calling it now */
export function waveCard(run, icons) {
  const n = run.wave + 1;
  const counts = nextWave(run);
  const total = counts.reduce((sum, [, count]) => sum + count, 0);
  const bonus = WAVES.callBonus * Math.floor(run.countdown / STEPS);
  const rows = counts.map(([type, count]) => [ROBOTS[type].name, `×${count}`, icons[type] || ""]);
  const tag = n % WAVES.bossEvery === 0 ? "Boss wave" : "";
  return { title: `Wave ${n}`, tag, text: `${total} robots. Calling it now pays +${bonus}.`, rows };
}

function robotTags(info) {
  return [info.flies && "Flies", info.armored && "Armored", info.boss && "Boss"].filter(Boolean).join(" · ");
}

/** What the card shows for a robot on the map */
export function robotCard(robot, icons) {
  const info = ROBOTS[robot.type];
  const rows = [
    ["Health", `${Math.max(0, robot.hp).toLocaleString()} / ${robot.maxHp.toLocaleString()}`],
    ["Core hit", info.lives === 1 ? "−1 life" : `−${info.lives} lives`],
    ["Money", `+${info.bounty}`],
    ["Score", `+${(info.points * robot.wave).toLocaleString()}`],
  ];
  return { title: info.name, tag: robotTags(info), text: ROBOT_ROLES[info.key], rows, icon: icons[robot.type] || "" };
}

/** What a robot does, for the note the first time its type comes in */
export function robotRole(type) {
  return ROBOT_ROLES[ROBOTS[type].key];
}

function overlaps(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

function rectOf(node) {
  const box = node.getBoundingClientRect();
  return { left: box.left, top: box.top, right: box.right, bottom: box.bottom };
}

export class InfoCard {
  constructor() {
    this.node = $("info");
    this.key = "";
    this.placed = "";
  }

  // Each frame: what the scene has in focus, rebuilt and placed only when that changed
  sync(run, scene) {
    const { card, hint, anchor } = run ? this.focus(run, scene) : {};
    const key = card ? JSON.stringify([card, hint]) : "";
    if (key !== this.key) {
      this.key = key;
      this.fill(card, hint);
    }
    if (card) {
      this.place(anchor, scene);
    }
  }

  // What to show: the open ring's tower or choice, else the wave button's wave, else the tapped robot
  focus(run, scene) {
    const ring = scene.ring;
    if (ring.isOpen) {
      const choice = ring.focus();
      return { card: cardFor(run, ring.spot, choice), hint: ring.hint(run, choice), anchor: ring.extent() };
    }
    if (scene.wave.focused) {
      const hint = scene.wave.picked ? { text: "Tap again to call it", short: false } : null;
      return { card: waveCard(run, scene.icons), hint, anchor: scene.wave.extent() };
    }
    const robot = scene.selected === null ? null : run.robots.find((r) => r.id === scene.selected && !r.gone);
    return robot ? { card: robotCard(robot, scene.icons), hint: null, anchor: null } : {};
  }

  // The page's layout changed: the card is placed again on the next frame
  relayout() {
    this.placed = "";
  }

  hide() {
    this.key = "";
    this.placed = "";
    this.node.hidden = true;
  }

  fill(card, hint) {
    if (!card) {
      this.hide();
      return;
    }
    const icon = $("info-icon");
    icon.hidden = !card.icon;
    if (card.icon) {
      icon.src = card.icon;
    }
    $("info-name").textContent = card.title;
    $("info-tag").textContent = card.tag;
    $("info-tag").hidden = !card.tag;
    $("info-text").textContent = card.text;
    const list = $("info-rows");
    list.replaceChildren(...card.rows.map(row));
    list.hidden = card.rows.length === 0;
    const line = $("info-hint");
    line.textContent = hint ? hint.text : "";
    line.hidden = !hint;
    line.classList.toggle("short", Boolean(hint?.short));
    this.placed = "";
    this.node.hidden = false;
  }

  // By what it describes (anchor, in page pixels), on the first side with room that covers no button; with no anchor
  // (a robot), at the bottom of the field between the power buttons
  place(anchor, scene) {
    const field = scene.field;
    const key = JSON.stringify([anchor, field, scene.turned]);
    if (key === this.placed) {
      return;
    }
    this.placed = key;
    const style = this.node.style;
    const room = {
      left: field.x + MARGIN,
      top: field.y + MARGIN,
      right: field.x + field.width - MARGIN,
      bottom: field.y + field.height - MARGIN,
    };
    if (!anchor) {
      const width = Math.min(WIDEST, room.right - room.left - 2 * (POWER + MARGIN));
      style.width = `${width}px`;
      style.left = `${(room.left + room.right - width) / 2}px`;
      style.top = `${room.bottom - this.node.offsetHeight}px`;
      return;
    }
    const width = Math.min(WIDEST, room.right - room.left);
    style.width = `${width}px`;
    const height = this.node.offsetHeight;
    const spot = bestSide(anchor, room, width, height, scene.turned, obstacles(anchor));
    style.left = `${spot.left}px`;
    style.top = `${spot.top}px`;
  }
}

function row([label, value, icon]) {
  const item = document.createElement("li");
  if (icon !== undefined) {
    const picture = document.createElement("img");
    picture.className = "info-row-icon";
    picture.alt = "";
    if (icon) {
      picture.src = icon;
    }
    item.append(picture);
  }
  const name = document.createElement("span");
  name.textContent = label;
  const amount = document.createElement("b");
  amount.textContent = value;
  item.append(name, amount);
  return item;
}

// The page's buttons a card must not cover, besides what it describes
function obstacles(anchor) {
  const nodes = [...document.querySelectorAll(".power, #bar")].filter((node) => node.getClientRects().length > 0);
  return nodes.map(rectOf).filter((box) => !overlaps(box, anchor));
}

// Above or below first on an upright map, beside first on a turned one: the first side where the whole card fits in
// the room without touching a button, else the first side squeezed into the room
function bestSide(anchor, room, width, height, turned, blocked) {
  const clamp = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high));
  const middleX = clamp((anchor.left + anchor.right) / 2 - width / 2, room.left, room.right - width);
  const middleY = clamp((anchor.top + anchor.bottom) / 2 - height / 2, room.top, room.bottom - height);
  const sides = {
    above: { left: middleX, top: anchor.top - MARGIN - height },
    below: { left: middleX, top: anchor.bottom + MARGIN },
    right: { left: anchor.right + MARGIN, top: middleY },
    left: { left: anchor.left - MARGIN - width, top: middleY },
  };
  const order = turned ? ["right", "left", "above", "below"] : ["above", "below", "right", "left"];
  const fits = (spot) => {
    const box = { left: spot.left, top: spot.top, right: spot.left + width, bottom: spot.top + height };
    const inside = box.left >= room.left && box.top >= room.top && box.right <= room.right && box.bottom <= room.bottom;
    return inside && !blocked.some((other) => overlaps(box, other));
  };
  const found = order.find((side) => fits(sides[side])) ?? order[0];
  const spot = sides[found];
  return { left: clamp(spot.left, room.left, room.right - width), top: clamp(spot.top, room.top, room.bottom - height) };
}
