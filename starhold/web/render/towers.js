// The player's towers and drones: sleek and high-tech, cool blues and teals with clean glow, each with a dark
// outline so it reads on a small phone. Every level adds hardware you can see, so a tower's level reads at a glance.
// Turrets turn toward what they shoot and kick back on each shot; a new tower rises out of its pad on hydraulics, and
// an upgrade slams down with a flash. A Drone bay's drones hover across the road at its wall, a glowing barrier
// between them while any is up, and lean in over the robots piled against it. Towers are placed and aimed in view
// units (see view.js), so they stand upright whichever way the map is turned.
import { Container, Graphics } from "../vendor/pixi.min.mjs";
import { pointAt } from "../sim/road.js";
import { BLASTER, DRONE, DRONES, MAP, MISSILE, TESLA } from "../sim/rules.js";
import { toView } from "./view.js";

const OUT = { width: 2, color: 0x041018 };
const THIN = { width: 1.5, color: 0x041018 };
const HULL = 0x1f5f82;
const HULL_LIGHT = 0x2f86b0;
const HULL_DARK = 0x16465f;
const STEEL = 0xcdeffa;
const STEEL_DARK = 0x8fb3c2;
const GLOW = 0x5ff3ff;
const VIOLET = 0x9b8cff;
const DARK = 0x08141d;
const HEX = Math.PI / 6;
const RISE_S = 0.4;
const SLAM_S = 0.28;
// How quickly a turret swings to a new target, and how far it kicks back on a shot (map units)
const TURN_RATE = 12;
const RECOIL = 5;
const RECOIL_RETURN = 40;
// Guns are drawn at this size, big against their pad so they read as turrets; shots leave this far from the centre
const GUN_SCALE = 1.2;
const MUZZLE = 36;
// Where each of a bay's three drones hovers at its wall: across the road from its middle, and ahead of the wall
const DRONE_OFFSETS = [
  [-17, 0],
  [17, 0],
  [0, 9],
];
// The wall's barrier reaches this far either side of the road's middle (the road's top is 44 across)
const BARRIER = 24;
// How far a drone leans toward the robot it holds
const DRONE_LEAN = 0.35;

function easeOutBack(p) {
  const q = p - 1;
  return 1 + 2.7 * q * q * q + 1.7 * q * q;
}

function base(level, form) {
  const g = new Graphics();
  g.regularPoly(0, 0, 27, 6, HEX).fill(0x132433).stroke(OUT);
  g.regularPoly(0, 0, 21, 6, HEX).stroke({ width: 1.5, color: GLOW, alpha: 0.45 });
  const pips = form >= 0 ? 3 : level;
  for (let i = 0; i < pips; i++) {
    g.circle((i - (pips - 1) / 2) * 7, 21, 2.2).fill(GLOW);
  }
  if (form >= 0) {
    g.regularPoly(0, 0, 30, 6, HEX).stroke({ width: 2, color: 0xb8fff4, alpha: 0.9 });
  }
  return g;
}

// The Blaster's barrels by level: one short barrel, then two, then two long ones with muzzle brakes
function blasterBarrels(g, level) {
  const length = [17, 19, 23][level - 1];
  const rows = level === 1 ? [0] : [-5, 5];
  for (const y of rows) {
    g.rect(10, y - 2.5, length, 5).fill(STEEL).stroke(THIN);
    if (level >= 3) {
      g.rect(8 + length, y - 3.6, 6, 7.2).fill(STEEL_DARK).stroke(THIN);
    } else {
      g.rect(8 + length, y - 3, 3, 6).fill(STEEL_DARK).stroke(THIN);
    }
  }
}

function gatling(g) {
  for (const y of [-5.5, 0, 5.5]) {
    g.rect(12, y - 2, 22, 4).fill(STEEL).stroke(THIN);
  }
  g.rect(27, -10, 4, 20).fill(STEEL_DARK).stroke(THIN);
  g.circle(13, 0, 9).fill(HULL_DARK).stroke(OUT);
  g.circle(13, 0, 3.5).fill(STEEL);
}

function railgun(g) {
  g.rect(-2, -11, 44, 5).fill(STEEL).stroke(THIN);
  g.rect(-2, 6, 44, 5).fill(STEEL).stroke(THIN);
  g.rect(4, -2.5, 38, 5).fill({ color: GLOW, alpha: 0.9 });
  for (const x of [16, 26, 36]) {
    g.rect(x, -12.5, 3.5, 25).fill(HULL_DARK).stroke(THIN);
  }
}

// Drawn pointing right; the turret turns it. Level 2 adds side armor, level 3 a lighter hull and cooling fins
function blaster(level, form) {
  const g = new Graphics();
  const top = level >= 3 || form >= 0;
  if (form === 1) {
    railgun(g);
  } else if (form === 0) {
    gatling(g);
  } else {
    blasterBarrels(g, level);
  }
  if (level >= 2 || form >= 0) {
    g.poly([-12, -19, 6, -19, 10, -14, -14, -14]).fill(HULL_DARK).stroke(THIN);
    g.poly([-12, 19, 6, 19, 10, 14, -14, 14]).fill(HULL_DARK).stroke(THIN);
  }
  if (top) {
    for (const y of [-7, 0, 7]) {
      g.rect(-22, y - 1.6, 7, 3.2).fill(STEEL).stroke(THIN);
    }
  }
  g.poly([-16, -14, 7, -14, 14, -7, 14, 7, 7, 14, -16, 14]).fill(top ? HULL_LIGHT : HULL).stroke(OUT);
  g.poly([-11, -9, 4, -9, 8.5, -4.5, 8.5, 4.5, 4, 9, -11, 9]).stroke({ width: 1.5, color: GLOW, alpha: 0.4 });
  g.circle(-3, 0, 5).fill(GLOW).stroke(THIN);
  g.scale.set(GUN_SCALE);
  return g;
}

// Launch tubes, each with a missile's nose showing: two in line with the aim at level 1, four at levels 2 and 3, nine
// smaller for Swarm
function tubes(g, level, form) {
  const cols = form === 0 ? 3 : 2;
  const rows = form === 0 ? 3 : level === 1 ? 1 : 2;
  const gap = form === 0 ? 9 : 11;
  const r = form === 0 ? 3.6 : 4.8;
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = 1 + (i - (cols - 1) / 2) * gap;
      const y = (j - (rows - 1) / 2) * gap;
      g.circle(x, y, r).fill(DARK).stroke({ width: 1.8, color: GLOW, alpha: 0.85 });
      g.circle(x + r * 0.25, y, r * 0.38).fill(STEEL_DARK);
    }
  }
}

function mortar(g) {
  g.rect(-4, -17, 22, 5).fill(STEEL_DARK).stroke(THIN);
  g.rect(-4, 12, 22, 5).fill(STEEL_DARK).stroke(THIN);
  g.circle(4, 0, 13).fill(DARK).stroke({ width: 4, color: STEEL });
  g.circle(4, 0, 6.5).fill({ color: GLOW, alpha: 0.5 });
}

// Drawn pointing right, a nose plate showing its aim. Level 1 is a small two-tube launcher, level 2 a bigger
// four-tube box, level 3 adds launch rails along both sides and a lighter hull
function missile(level, form) {
  const g = new Graphics();
  const top = level >= 3 || form >= 0;
  const half = level === 1 ? 12 : 16;
  if (top) {
    g.rect(-18, -22, 32, 5).fill(HULL_LIGHT).stroke(THIN);
    g.rect(-18, 17, 32, 5).fill(HULL_LIGHT).stroke(THIN);
  }
  const nose = [half - 2, -half + 4, half + 6, -half + 8, half + 6, half - 8, half - 2, half - 4];
  g.poly(nose).fill(HULL_DARK).stroke(OUT);
  g.roundRect(-half - 2, -half, half * 2 + 2, half * 2, 6).fill(top ? HULL_LIGHT : HULL).stroke(OUT);
  if (form === 1) {
    mortar(g);
  } else {
    tubes(g, level, form);
  }
  if (level >= 2 || form >= 0) {
    g.circle(-half + 3, -half + 3, 2.2).fill(GLOW);
  }
  g.scale.set(GUN_SCALE);
  return g;
}

// A coil with a ring per level and a glowing orb on top; level 3 and the final forms add capacitor prongs
function tesla(level, form) {
  const coil = new Graphics();
  const rings = form >= 0 ? 5 : level + 1;
  const gap = 6.5;
  if (level >= 3 || form >= 0) {
    for (const x of [-15, 15]) {
      coil.rect(x - 1.5, -12, 3, 20).fill(STEEL).stroke(THIN);
      coil.circle(x, -13, 3).fill(GLOW).stroke(THIN);
    }
  }
  coil.rect(-3.5, -rings * gap, 7, rings * gap + 8).fill(STEEL).stroke(THIN);
  for (let i = 0; i < rings; i++) {
    coil.ellipse(0, 8 - i * gap, 17 - i * 2, 5.5).fill(i % 2 ? HULL_LIGHT : HULL).stroke(OUT);
  }
  const color = form === 1 ? VIOLET : GLOW;
  const size = form === 0 ? 10.5 : 8;
  const orb = new Graphics();
  orb.circle(0, 0, size * 1.9).fill({ color, alpha: 0.22 });
  if (form === 1) {
    orb.circle(0, 0, size * 1.45).stroke({ width: 2, color, alpha: 0.8 });
  }
  orb.circle(0, 0, size).fill(0xe6fdff).stroke({ width: 2.5, color });
  orb.position.set(0, -rings * gap - 3);
  return { coil, orb };
}

// The final forms' marks on a hangar roof: a shield for Guardians, blade chevrons for Strikers
function bayMark(g, form, h) {
  const y = -h + 4.5;
  if (form === 0) {
    g.regularPoly(0, y, 4, 6, HEX).stroke({ width: 2, color: GLOW });
  } else if (form === 1) {
    g.moveTo(-6, y - 2.5).lineTo(-2, y).lineTo(-6, y + 2.5).moveTo(1, y - 2.5).lineTo(5, y).lineTo(1, y + 2.5);
    g.stroke({ width: 2, color: STEEL });
  }
}

// A drone hangar seen from above. Level 1 has one door, level 2 is bigger with two doors and an aerial, level 3 adds
// a lighter hull and a radar dish
function bay(level, form) {
  const g = new Graphics();
  const top = level >= 3 || form >= 0;
  const w = level === 1 ? 17 : 22;
  const h = level === 1 ? 14 : 17;
  if (level >= 2 || form >= 0) {
    g.moveTo(w - 5, -h + 4).lineTo(w + 3, -h - 5).stroke({ width: 2, color: STEEL });
    g.circle(w + 3, -h - 5, 2.4).fill(GLOW).stroke(THIN);
  }
  g.roundRect(-w, -h, w * 2, h * 2, 6).fill(top ? HULL_LIGHT : HULL).stroke(OUT);
  for (const x of level === 1 ? [-8] : [-18, 2]) {
    g.roundRect(x, -8, 16, 18, 2).fill(DARK).stroke(THIN);
    for (let k = 0; k < 3; k++) {
      g.rect(x + 2, -5 + k * 5, 12, 2).fill(HULL_DARK);
    }
  }
  if (top) {
    g.circle(-w + 6, -h + 5, 4.5).fill(STEEL).stroke(THIN);
    g.moveTo(-w + 6, -h + 5).lineTo(-w + 10, -h + 1).stroke({ width: 1.5, color: DARK });
  }
  bayMark(g, form, h);
  g.circle(w - 5, h - 4, 2.4).fill(GLOW);
  return g;
}

// Where a drone's rotors sit: two at level 1, four from level 2
const ROTORS_TWO = [
  [-11, -2],
  [11, -2],
];
const ROTORS_FOUR = [
  [-10, -8],
  [10, -8],
  [-10, 4],
  [10, 4],
];

// A Drone bay's wall: a glowing bar across the road between two emitter nodes, drawn along its own y axis so turning
// it to the road's way forward lays it across the road
function barrier() {
  const g = new Graphics();
  g.moveTo(0, -BARRIER).lineTo(0, BARRIER).stroke({ width: 9, color: GLOW, alpha: 0.22 });
  g.moveTo(0, -BARRIER).lineTo(0, BARRIER).stroke({ width: 2.5, color: 0xb8fff4, alpha: 0.95 });
  g.circle(0, -BARRIER, 4).fill(GLOW).stroke(THIN);
  g.circle(0, BARRIER, 4).fill(GLOW).stroke(THIN);
  return g;
}

// A bay's drone: two rotors at level 1, four from level 2, a gun pod and a lighter hull from level 3. Guardians
// carry a shield ring and Strikers blades
function droneGraphic(level, form) {
  const g = new Graphics();
  const top = level >= 3 || form >= 0;
  const rotors = level >= 2 || form >= 0 ? ROTORS_FOUR : ROTORS_TWO;
  g.ellipse(0, 15, 8, 2.8).fill({ color: 0x000000, alpha: 0.3 });
  for (const [x, y] of rotors) {
    g.moveTo(0, -2).lineTo(x, y);
  }
  g.stroke({ width: 2.2, color: STEEL });
  for (const [x, y] of rotors) {
    g.circle(x, y, 4.4).fill({ color: GLOW, alpha: 0.35 }).stroke({ width: 1, color: GLOW, alpha: 0.8 });
  }
  if (top) {
    g.rect(-2, 2, 4, 8).fill(STEEL).stroke(THIN);
  }
  g.roundRect(-6, -7, 12, 10, 3).fill(form === 1 ? 0x3a7fb0 : top ? HULL_LIGHT : HULL).stroke(OUT);
  g.circle(0, -2, 2).fill(GLOW);
  if (form === 0) {
    g.circle(0, -2, 14).stroke({ width: 1.8, color: GLOW, alpha: 0.55 });
  }
  if (form === 1) {
    g.poly([-6, 3, -11, 10, -3, 6]).fill(STEEL).stroke(THIN);
    g.poly([6, 3, 11, 10, 3, 6]).fill(STEEL).stroke(THIN);
  }
  return g;
}

// A tower's picture for the ring menu: level 1, or level 3's look for a final form
export function towerIcon(kind, form = -1) {
  const icon = new Container();
  const level = form >= 0 ? 3 : 1;
  if (kind === TESLA) {
    const { coil, orb } = tesla(level, form);
    icon.addChild(coil, orb);
    icon.y = 10;
  } else if (kind === DRONES) {
    icon.addChild(form >= 0 ? droneGraphic(level, form) : bay(level, form));
  } else {
    const gun = kind === BLASTER ? blaster(level, form) : missile(level, form);
    gun.rotation = -Math.PI / 2;
    icon.addChild(gun);
  }
  return icon;
}

// A spot's middle in view units
function spotAt(spot) {
  return toView(...MAP.spots[spot]);
}

// A point in the rules' hundredths of a map unit, as { x, y } in view units
function viewOf(x, y) {
  const [vx, vy] = toView(x / 100, y / 100);
  return { x: vx, y: vy };
}

function makeView(tower, spot) {
  const [x, y] = spotAt(spot);
  const root = new Container();
  root.position.set(x, y);
  const body = new Container();
  root.addChild(body);
  body.addChild(base(tower.level, tower.form));
  const view = { root, body, turret: null, gun: null, orb: null, flash: null, kind: tower.kind, drones: [] };
  view.barrier = null;
  Object.assign(view, { aim: -Math.PI / 2, want: -Math.PI / 2, recoil: 0, born: 0, slamAt: -Infinity, look: "" });
  if (tower.kind === BLASTER || tower.kind === MISSILE) {
    view.turret = new Container();
    view.gun = tower.kind === BLASTER ? blaster(tower.level, tower.form) : missile(tower.level, tower.form);
    view.turret.addChild(view.gun);
    body.addChild(view.turret);
  } else if (tower.kind === TESLA) {
    const { coil, orb } = tesla(tower.level, tower.form);
    body.addChild(coil, orb);
    view.orb = orb;
  } else {
    body.addChild(bay(tower.level, tower.form));
  }
  view.flash = new Graphics().regularPoly(0, 0, 30, 6, HEX).fill(0xffffff);
  view.flash.alpha = 0;
  body.addChild(view.flash);
  return view;
}

export class TowerViews {
  constructor(layer) {
    this.layer = layer;
    this.views = [];
    this.time = 0;
  }

  clear() {
    for (const view of this.views) {
      if (view) {
        this.drop(view);
      }
    }
    this.views = [];
  }

  drop(view) {
    view.root.destroy({ children: true, context: true });
    for (const drone of view.drones) {
      drone.destroy({ context: true });
    }
    view.barrier?.destroy({ context: true });
  }

  // The view turned: each tower moves to its spot's new place, and its turret keeps pointing at the same thing
  reorient() {
    this.views.forEach((view, spot) => {
      if (view) {
        view.root.position.set(...spotAt(spot));
        view.aim = Math.PI / 2 - view.aim;
        view.want = Math.PI / 2 - view.want;
      }
    });
  }

  draw(run, t, scene) {
    const dt = Math.max(0, t - this.time);
    this.time = t;
    for (let spot = 0; spot < MAP.spots.length; spot++) {
      const tower = run ? run.towers[spot] : null;
      const look = tower ? `${tower.kind}/${tower.level}/${tower.form}` : "";
      let view = this.views[spot];
      if ((view ? view.look : "") !== look) {
        view = this.replace(spot, tower, look, t);
      }
      if (view) {
        this.animate(view, t, dt);
        this.placeDrones(view, tower, run, t, scene);
      }
    }
  }

  // A new tower rises; the same kind at a new level or form is an upgrade, which slams down
  replace(spot, tower, look, t) {
    const old = this.views[spot];
    const upgrade = Boolean(old && tower && old.kind === tower.kind);
    if (old) {
      this.drop(old);
    }
    this.views[spot] = null;
    if (!tower) {
      return null;
    }
    const view = makeView(tower, spot);
    view.look = look;
    view.born = upgrade ? -Infinity : t;
    view.slamAt = upgrade ? t : -Infinity;
    if (upgrade) {
      view.aim = old.aim;
      view.want = old.want;
    }
    this.layer.addChild(view.root);
    this.views[spot] = view;
    return view;
  }

  animate(view, t, dt) {
    // Out of the pad on hydraulics: up past its rest, then settling back
    const rise = Math.min(1, (t - view.born) / RISE_S);
    view.body.y = (1 - easeOutBack(rise)) * 16;
    view.body.alpha = Math.min(1, 0.3 + rise);
    const slam = Math.max(0, 1 - (t - view.slamAt) / SLAM_S);
    view.body.scale.set(1 + slam * slam * 0.22);
    view.flash.alpha = slam * 0.75;
    if (view.turret) {
      const turn = Math.atan2(Math.sin(view.want - view.aim), Math.cos(view.want - view.aim));
      view.aim += turn * Math.min(1, TURN_RATE * dt);
      view.turret.rotation = view.aim;
      view.recoil = Math.max(0, view.recoil - dt * RECOIL_RETURN);
      view.gun.x = -view.recoil;
    }
    if (view.orb) {
      view.orb.alpha = 0.75 + 0.25 * Math.sin(t * 5);
      view.orb.scale.set(1 + 0.08 * Math.sin(t * 7));
    }
  }

  placeDrones(view, tower, run, t, scene) {
    if (tower.kind !== DRONES) {
      return;
    }
    if (!view.barrier) {
      view.barrier = barrier();
      scene.layers.drones.addChild(view.barrier);
    }
    while (view.drones.length < DRONE.count) {
      const drone = droneGraphic(tower.level, tower.form);
      // Drones fly above the robots, so a robot a drone holds shows beneath it
      scene.layers.drones.addChild(drone);
      view.drones.push(drone);
    }
    // The wall's middle, and the road's way forward there, in view units
    const wall = tower.park - DRONE.grab * 100;
    const [ax, ay] = toView(...pointAt(wall - 100));
    const [px, py] = toView(...pointAt(wall));
    const length = Math.hypot(px - ax, py - ay) || 1;
    const fx = (px - ax) / length;
    const fy = (py - ay) / length;
    view.barrier.position.set(px / 100, py / 100);
    view.barrier.rotation = Math.atan2(fy, fx);
    view.barrier.visible = tower.drones.some((drone) => drone.backAt === 0);
    view.barrier.alpha = 0.6 + 0.3 * Math.sin(t * 6);
    tower.drones.forEach((drone, i) => {
      const g = view.drones[i];
      g.visible = !(drone.backAt > run.step);
      const [across, ahead] = DRONE_OFFSETS[i];
      let x = px / 100 - fy * across + fx * ahead;
      let y = py / 100 + fx * across + fy * ahead + Math.sin(t * 4 + i * 2) * 2;
      const target = drone.holding >= 0 ? scene.robots.positionOf(drone.holding) : null;
      if (target) {
        x += (target.x - x) * DRONE_LEAN;
        y += (target.y - y) * DRONE_LEAN;
      }
      g.rotation = target ? Math.sin(t * 18 + i) * 0.15 : 0;
      g.position.set(x, y);
    });
  }

  // Turrets swing toward what they shoot, and kick back
  event(e, scene) {
    const view = e.spot === undefined ? null : this.views[e.spot];
    if (!view || !view.turret) {
      return;
    }
    let target = null;
    if (e.kind === "shot") {
      target = scene.robots.positionOf(e.id);
    } else if (e.kind === "rail") {
      target = viewOf(e.x, e.y);
    } else if (e.kind === "launch") {
      target = viewOf(e.shell.x, e.shell.y);
    }
    if (!target) {
      return;
    }
    const [x, y] = spotAt(e.spot);
    view.want = Math.atan2(target.y - y, target.x - x);
    view.recoil = RECOIL;
  }

  // Where a tower's shot leaves from, in view units
  muzzle(spot) {
    const [x, y] = spotAt(spot);
    const view = this.views[spot];
    if (view?.orb) {
      return { x, y: y + view.orb.y };
    }
    if (!view?.turret) {
      return { x, y };
    }
    return { x: x + Math.cos(view.aim) * MUZZLE, y: y + Math.sin(view.aim) * MUZZLE };
  }

  dronePosition(spot, drone) {
    const g = this.views[spot]?.drones[drone];
    return g ? { x: g.x, y: g.y } : null;
  }
}
