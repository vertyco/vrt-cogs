// How the fights look: shots, beams, zaps, missiles in flight, explosions, sparks, scrap, the Orbital strike and the
// Stasis field, and the screen shake on big blasts. Effects are drawing only: the rules never see them, so they may
// use Math.random freely. Effects are placed in view units (see view.js), so smoke rises and scrap falls down the
// screen whichever way the map is turned.
import { Graphics } from "../vendor/pixi.min.mjs";
import { COLOSSUS, MAP, MISSILE, POWERS, STEPS, TESLA } from "../sim/rules.js";
import { toView } from "./view.js";

const TRACER = 0xc9f7ff;
const RAIL = 0x5ff3ff;
const ZAP = 0xa8ecff;
const VIOLET = 0x9b8cff;
const FIRE = 0xffb347;
const FIRE_DEEP = 0xff5a1f;
const FIRE_HOT = 0xffe066;
const WHITE_HOT = 0xfffbe8;
// The color a fireball cools to as it fades
const EMBER = 0xb8432c;
const INK = 0x140b06;
const DEBRIS = [0x2b2e33, 0x474c51, 0x5e321c, 0x3a3f46];
// A fireball's layers, outside in: color, size as a share of the whole fireball, and how many blobs make it ragged
const FIRE_LAYERS = [
  [FIRE_DEEP, 1, 6],
  [FIRE, 0.72, 5],
  [FIRE_HOT, 0.46, 4],
  [WHITE_HOT, 0.22, 2],
];
const SMOKE = 0x3a3f46;
const STASIS_BLUE = 0x7fc8ff;
const SCRAP = [0x8a4a28, 0x767b80, 0x474c51, 0x5e321c];
// Map units a second squared, for falling scrap
const GRAVITY = 300;
// Past this many effect pieces on show, new sparks, smoke and debris are skipped: they are cosmetic, and a big wave on
// a phone needs the frame time
const MOST_PIECES = 300;
// How high a Mortar shell climbs at the top of its arc, in map units
const MORTAR_ARC = 120;
const SHAKE_MOST = 10;
const SHAKE_DECAY = 26;
// A zap's jagged line: how many kinks between two robots, and how far each kink strays
const ZAP_KINKS = 4;
const ZAP_STRAY = 6;

function line(from, to, width, color, alpha = 1) {
  return new Graphics().moveTo(from.x, from.y).lineTo(to.x, to.y).stroke({ width, color, alpha, cap: "round" });
}

// A color part of the way from a to b
function mix(a, b, p) {
  let out = 0;
  for (const shift of [16, 8, 0]) {
    const from = (a >> shift) & 255;
    const to = (b >> shift) & 255;
    out |= Math.round(from + (to - from) * p) << shift;
  }
  return out;
}

function fade(node, p) {
  node.alpha = 1 - p;
}

function jagged(g, points) {
  g.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    for (let k = 1; k <= ZAP_KINKS; k++) {
      const f = k / (ZAP_KINKS + 1);
      const strayX = (Math.random() - 0.5) * ZAP_STRAY * 2;
      const strayY = (Math.random() - 0.5) * ZAP_STRAY * 2;
      g.lineTo(a.x + (b.x - a.x) * f + strayX, a.y + (b.y - a.y) * f + strayY);
    }
    g.lineTo(b.x, b.y);
  }
}

// A point in the rules' hundredths of a map unit, in view units
function at(x, y) {
  return toView(x / 100, y / 100);
}

const HANDLERS = {
  shot(fx, e) {
    const from = fx.scene.towers.muzzle(e.spot);
    const to = fx.scene.robots.positionOf(e.id);
    if (!to) {
      return;
    }
    fx.add(line(from, to, 2, TRACER), 0.08, fade);
    fx.spark(from, 1, TRACER, 40);
    fx.spark(to, 3, TRACER, 70);
  },
  rail(fx, e) {
    const from = fx.scene.towers.muzzle(e.spot);
    const [x, y] = at(e.x, e.y);
    const to = { x, y };
    const beam = line(from, to, 9, RAIL, 0.85);
    beam.blendMode = "add";
    fx.add(beam, 0.25, fade);
    fx.add(line(from, to, 2.5, 0xffffff), 0.12, fade);
  },
  launch(fx, e) {
    fx.puff(fx.scene.towers.muzzle(e.spot), 2, 4);
  },
  zap(fx, e, run) {
    const tower = run.towers[e.spot];
    const color = tower && tower.kind === TESLA && tower.form === 1 ? VIOLET : ZAP;
    const hit = e.ids.map((id) => fx.scene.robots.positionOf(id)).filter(Boolean);
    const points = [fx.scene.towers.muzzle(e.spot), ...hit];
    if (points.length < 2) {
      return;
    }
    const g = new Graphics();
    g.blendMode = "add";
    fx.add(g, 0.16, (node, p) => {
      node.clear();
      jagged(node, points);
      node.stroke({ width: 2.5, color, alpha: 1 - p });
    });
    for (const at of points.slice(1)) {
      fx.spark(at, 2, color, 60);
    }
  },
  boom(fx, e) {
    fx.explode(...at(e.x, e.y), e.r, e.big);
    if (e.strike) {
      fx.strikeBeam(...at(e.x, e.y), e.r);
    }
  },
  die(fx, e) {
    fx.scrap(...at(e.x, e.y), e.type);
  },
  leak(fx) {
    fx.scene.map.flashCore();
    fx.bump(3);
  },
  strike(fx, e) {
    fx.charge(...at(e.x, e.y));
  },
  stasis(fx, e) {
    fx.field(...at(e.x, e.y));
  },
  grab(fx, e) {
    const at = fx.scene.robots.positionOf(e.id);
    if (at) {
      fx.spark(at, 4, RAIL, 50);
    }
  },
  droneDown(fx, e) {
    const at = fx.scene.towers.dronePosition(e.spot, e.drone);
    if (at) {
      fx.explode(at.x, at.y, 14, false);
    }
  },
  build(fx, e) {
    fx.pulse(e.spot);
  },
  upgrade(fx, e) {
    fx.pulse(e.spot);
  },
  form(fx, e) {
    fx.pulse(e.spot);
  },
};

export class Effects {
  constructor(layer, shellLayer, scene) {
    this.layer = layer;
    this.scene = scene;
    this.shellGraphics = new Graphics();
    shellLayer.addChild(this.shellGraphics);
    // Each effect on show: its node, how long it lasts and has lasted (seconds), and how it changes as it goes
    this.items = [];
    // Orbital strikes charging, so the blast that lands there gets its beam from the sky
    this.charges = [];
    this.shake = 0;
  }

  clear() {
    for (const item of this.items) {
      item.node.destroy({ context: true });
    }
    this.items = [];
    this.charges = [];
    this.shellGraphics.clear();
    this.shake = 0;
  }

  add(node, life, update) {
    this.layer.addChild(node);
    this.items.push({ node, life, age: 0, update });
  }

  event(e, run) {
    HANDLERS[e.kind]?.(this, e, run);
  }

  bump(amount) {
    this.shake = Math.min(SHAKE_MOST, this.shake + amount);
  }

  shakeOffset() {
    if (this.shake < 0.05) {
      return { x: 0, y: 0 };
    }
    return { x: (Math.random() - 0.5) * this.shake, y: (Math.random() - 0.5) * this.shake };
  }

  crowded() {
    return this.items.length >= MOST_PIECES;
  }

  spark(at, count, color, speed) {
    if (this.crowded()) {
      return;
    }
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const v = speed * (0.5 + Math.random());
      const vx = Math.cos(angle) * v;
      const vy = Math.sin(angle) * v;
      const g = new Graphics().rect(-1.5, -0.6, 3, 1.2).fill(color);
      g.position.set(at.x, at.y);
      g.rotation = angle;
      g.blendMode = "add";
      this.add(g, 0.18 + Math.random() * 0.1, (node, p, dt) => {
        node.x += vx * dt;
        node.y += vy * dt;
        node.alpha = 1 - p;
      });
    }
  }

  puff(at, count, size) {
    if (this.crowded()) {
      return;
    }
    for (let i = 0; i < count; i++) {
      const drift = (Math.random() - 0.5) * 20;
      const rise = -12 - Math.random() * 10;
      const g = new Graphics().circle(0, 0, size).fill({ color: SMOKE, alpha: 0.6 });
      g.position.set(at.x + (Math.random() - 0.5) * size, at.y + (Math.random() - 0.5) * size);
      this.add(g, 0.6, (node, p, dt) => {
        node.x += drift * dt;
        node.y += rise * dt;
        node.scale.set(1 + p * 1.5);
        node.alpha = 0.6 * (1 - p);
      });
    }
  }

  // A blast: smoke rolling out underneath, an orange and yellow fireball, a white-hot flash at its heart, a shock
  // ring and sparks. Big blasts burn bigger and longer and throw debris, which flies out from under the fire
  explode(x, y, r, big) {
    this.smoke(x, y, r, big);
    if (big) {
      this.debris(x, y, r);
    }
    this.fireball(x, y, r, big);
    this.flare(x, y, r, big);
    const ring = new Graphics().circle(0, 0, r).stroke({ width: big ? 5 : 2.5, color: FIRE });
    ring.position.set(x, y);
    this.add(ring, big ? 0.4 : 0.28, (node, p) => {
      node.alpha = 0.7 * (1 - p);
      node.scale.set(0.3 + p * 0.75);
    });
    this.spark({ x, y }, big ? 16 : 7, FIRE_HOT, r * 2.6);
    this.bump(big ? 6 : r >= 70 ? 1.5 : 0.4);
  }

  // Ragged layers of fire, deep orange outside to white hot inside, swelling fast and cooling to a dull red
  fireball(x, y, r, big) {
    const size = r * (big ? 0.55 : 0.45);
    const g = new Graphics();
    for (const [color, share, count] of FIRE_LAYERS) {
      for (let i = 0; i < count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const off = size * share * 0.4 * Math.random();
        const blob = size * share * (0.65 + Math.random() * 0.35);
        g.circle(Math.cos(angle) * off, Math.sin(angle) * off, blob).fill(color);
      }
    }
    g.position.set(x, y);
    this.add(g, big ? 0.6 : 0.38, (node, p) => {
      node.scale.set(0.45 + 0.65 * (1 - (1 - p) ** 3));
      node.alpha = p < 0.4 ? 1 : 1 - (p - 0.4) / 0.6;
      node.tint = mix(0xffffff, EMBER, p);
    });
  }

  // The white-hot instant at the heart of a blast
  flare(x, y, r, big) {
    const g = new Graphics().circle(0, 0, r * 0.32).fill(0xffffff);
    g.position.set(x, y);
    g.blendMode = "add";
    this.add(g, big ? 0.12 : 0.08, (node, p) => {
      node.alpha = 1 - p;
      node.scale.set(0.7 + p * 0.8);
    });
  }

  // Smoke rolls out under the fire and lingers after it
  smoke(x, y, r, big) {
    if (this.crowded()) {
      return;
    }
    for (let i = 0; i < (big ? 7 : 4); i++) {
      const size = r * (0.2 + Math.random() * 0.1);
      const drift = (Math.random() - 0.5) * r * 0.5;
      const rise = -10 - Math.random() * 15;
      const g = new Graphics().circle(0, 0, size).fill(SMOKE);
      g.position.set(x + (Math.random() - 0.5) * r * 0.5, y + (Math.random() - 0.5) * r * 0.4);
      const life = (big ? 1.4 : 0.9) + Math.random() * 0.3;
      const update = (node, p, dt) => {
        node.x += drift * dt;
        node.y += rise * dt;
        node.scale.set(0.8 + p * 1.2);
        node.alpha = 0.65 * (1 - p);
      };
      this.add(g, life, update);
      // Beneath every other effect, so smoke never covers fire or a flash
      this.layer.setChildIndex(g, 0);
    }
  }

  // Chunks of road and robot thrown out by a big blast, falling back and settling
  debris(x, y, r) {
    if (this.crowded()) {
      return;
    }
    for (let i = 0; i < 10; i++) {
      const size = 2.5 + Math.random() * 3.5;
      const g = new Graphics()
        .poly([-size, -size * 0.4, size * 0.2, -size * 0.8, size, 0, -size * 0.1, size * 0.7])
        .fill(DEBRIS[i % DEBRIS.length])
        .stroke({ width: 1, color: INK });
      g.position.set(x, y);
      const angle = Math.random() * Math.PI * 2;
      const vx = Math.cos(angle) * r * (1 + Math.random() * 1.4);
      let vy = Math.sin(angle) * r * 0.6 - r * (1.2 + Math.random());
      const spin = (Math.random() - 0.5) * 16;
      const floor = y + Math.random() * r * 0.5;
      this.add(g, 1.1, (node, p, dt) => {
        vy += GRAVITY * 1.6 * dt;
        node.x += node.y < floor ? vx * dt : 0;
        node.y = Math.min(floor, node.y + vy * dt);
        node.rotation += node.y < floor ? spin * dt : 0;
        node.alpha = p > 0.75 ? (1 - p) / 0.25 : 1;
      });
    }
  }

  // A robot breaks into scrap pieces that tumble and settle on the ground
  scrap(x, y, type) {
    const big = type === COLOSSUS;
    const count = this.crowded() ? 0 : big ? 18 : 6;
    const size = big ? 9 : 3.5;
    for (let i = 0; i < count; i++) {
      const g = new Graphics()
        .rect(-size / 2, -size / 3, size, size * 0.66)
        .fill(SCRAP[i % SCRAP.length])
        .stroke({ width: 1, color: INK });
      g.position.set(x, y - size);
      const vx = (Math.random() - 0.5) * (big ? 220 : 140);
      let vy = -70 - Math.random() * (big ? 160 : 90);
      const spin = (Math.random() - 0.5) * 14;
      const floor = y + 4 + Math.random() * (big ? 30 : 8);
      this.add(g, big ? 1.4 : 0.9, (node, p, dt) => {
        vy += GRAVITY * dt;
        node.x += vx * dt;
        node.y = Math.min(floor, node.y + vy * dt);
        node.rotation += spin * dt;
        node.alpha = p > 0.7 ? (1 - p) / 0.3 : 1;
      });
    }
    this.explode(x, y - (big ? 30 : 6), big ? 90 : 18, big);
  }

  // The second between tapping the Orbital strike and its beam landing
  charge(x, y) {
    const r = POWERS.strike.radius;
    const g = new Graphics();
    g.position.set(x, y);
    this.charges.push({ x, y });
    this.add(g, POWERS.strike.delay / STEPS, (node, p) => {
      node.clear();
      node.circle(0, 0, r * (1.4 - p * 0.4)).stroke({ width: 2, color: RAIL, alpha: 0.4 + p * 0.5 });
      node.circle(0, 0, r * (1 - p)).stroke({ width: 3, color: 0xffffff, alpha: p });
      node.moveTo(-12, 0).lineTo(12, 0).moveTo(0, -12).lineTo(0, 12).stroke({ width: 2, color: 0xffffff, alpha: 0.8 });
    });
  }

  strikeBeam(x, y, r) {
    // The charge this blast answers is the nearest one still waiting
    let index = -1;
    let best = Infinity;
    this.charges.forEach((c, i) => {
      const gap = Math.hypot(c.x - x, c.y - y);
      if (gap < best) {
        best = gap;
        index = i;
      }
    });
    if (index >= 0) {
      this.charges.splice(index, 1);
    }
    const beam = new Graphics()
      .rect(-r * 0.35, -1400, r * 0.7, 1400)
      .fill({ color: RAIL, alpha: 0.75 })
      .rect(-r * 0.12, -1400, r * 0.24, 1400)
      .fill(0xffffff);
    beam.position.set(x, y);
    beam.blendMode = "add";
    this.add(beam, 0.45, (node, p) => {
      node.alpha = 1 - p;
      node.scale.x = 1 - p * 0.6;
    });
    this.bump(8);
  }

  field(x, y) {
    const r = POWERS.stasis.radius;
    const g = new Graphics();
    g.position.set(x, y);
    this.add(g, POWERS.stasis.length / STEPS, (node, p) => {
      const grow = Math.min(1, p * 8);
      node.clear();
      node.circle(0, 0, r * grow).fill({ color: STASIS_BLUE, alpha: 0.16 * (1 - p * 0.5) });
      node.circle(0, 0, r * grow).stroke({ width: 2, color: STASIS_BLUE, alpha: 0.7 * (1 - p) });
      const ripple = r * grow * (0.6 + 0.1 * Math.sin(p * 40));
      node.circle(0, 0, ripple).stroke({ width: 1, color: 0xffffff, alpha: 0.3 * (1 - p) });
    });
  }

  // A ring of light around a spot when something is built or upgraded there
  pulse(spot) {
    const [x, y] = toView(...MAP.spots[spot]);
    const g = new Graphics().regularPoly(0, 0, 34, 6, Math.PI / 6).stroke({ width: 3, color: RAIL });
    g.position.set(x, y);
    g.blendMode = "add";
    this.add(g, 0.4, (node, p) => {
      node.alpha = 1 - p;
      node.scale.set(1 + p * 0.5);
    });
  }

  drawShells(run, alpha) {
    const g = this.shellGraphics;
    g.clear();
    if (!run) {
      return;
    }
    for (const shell of run.shells) {
      if (shell.kind === "strike") {
        continue;
      }
      const span = Math.max(1, shell.landAt - shell.firedAt);
      const p = Math.min(1, Math.max(0, (run.step + alpha - shell.firedAt) / span));
      const [fromX, fromY] = at(shell.fromX, shell.fromY);
      const [toX, toY] = at(shell.x, shell.y);
      const x = fromX + (toX - fromX) * p;
      let y = fromY + (toY - fromY) * p;
      const tower = run.towers[shell.spot];
      if (tower && tower.kind === MISSILE && tower.form === 1) {
        y -= Math.sin(p * Math.PI) * MORTAR_ARC;
        g.circle(x, y, 6).fill(0x2a3640).stroke({ width: 2, color: FIRE });
        continue;
      }
      const angle = Math.atan2(toY - fromY, toX - fromX);
      g.moveTo(x - Math.cos(angle) * 14, y - Math.sin(angle) * 14)
        .lineTo(x, y)
        .stroke({ width: 3, color: FIRE, alpha: 0.5 });
      g.circle(x, y, 3).fill(0xe8f6ff).stroke({ width: 1, color: 0x041018 });
    }
  }

  draw(run, alpha, t, dt) {
    const keep = [];
    for (const item of this.items) {
      item.age += dt;
      if (item.age >= item.life) {
        item.node.destroy({ context: true });
        continue;
      }
      item.update(item.node, item.age / item.life, dt);
      keep.push(item);
    }
    this.items = keep;
    this.drawShells(run, alpha);
    this.shake = Math.max(0, this.shake - SHAKE_DECAY * dt);
  }
}
