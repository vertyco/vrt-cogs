// The ground under the game: the moon backdrop, the road drawn from the rules' own road points (so the picture and
// the game always agree), the glowing build pads and the reactor core. Without the backdrop picture the ground is
// drawn in code. The backdrop goes on past the map's edges, mirrored, so a screen of any shape is moon to its edges,
// and the road comes in from beyond the picture. The backdrop and the road are drawn in map units and turned with the
// view; the pads and the core are placed in view units, so a pad's point stays at its top either way.
import { Assets, Container, Graphics, Sprite } from "../vendor/pixi.min.mjs";
import { MAP } from "../sim/rules.js";
import { toView, view } from "./view.js";

const ROAD_EDGE = 0x0a0e13;
const ROAD_BED = 0x252e38;
const ROAD_TOP = 0x313c48;
const ROAD_SEAM = 0x1b222b;
const LIGHT = 0x4fd8ff;
const PAD = 0x0d1a24;
const PAD_LINE = 0x3fd2ff;
const CORE = 0x6ff3ff;
const SEAM_EVERY = 40;
const LIGHT_EVERY = 60;
const PAD_RADIUS = 34;
const HEX = Math.PI / 6;
const CRATERS = 40;
const FLASH_FADE = 0.04;
// How far the road is drawn on before its start, off the map's edge
const RUN_IN = 2000;

// The road's points, with one more before its start along its first stretch
function roadPoints() {
  const [[ax, ay], [bx, by]] = MAP.road;
  const length = Math.hypot(bx - ax, by - ay);
  return [[ax - ((bx - ax) / length) * RUN_IN, ay - ((by - ay) / length) * RUN_IN], ...MAP.road];
}

function roadPath(g) {
  const [first, ...rest] = roadPoints();
  g.moveTo(first[0], first[1]);
  for (const [x, y] of rest) {
    g.lineTo(x, y);
  }
  return g;
}

// Points along the road this far apart, each with the direction the road runs there
function alongRoad(every) {
  const road = roadPoints();
  const points = [];
  for (let i = 1; i < road.length; i++) {
    const [ax, ay] = road[i - 1];
    const [bx, by] = road[i];
    const length = Math.hypot(bx - ax, by - ay);
    const dx = (bx - ax) / length;
    const dy = (by - ay) / length;
    for (let at = every / 2; at < length; at += every) {
      points.push({ x: ax + dx * at, y: ay + dy * at, dx, dy });
    }
  }
  return points;
}

// The same craters on every screen: a fixed little number sequence, not Math.random
function craterSpots() {
  let seed = 7;
  const next = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  return Array.from({ length: CRATERS }, () => ({ x: next() * MAP.width, y: next() * MAP.height, r: 6 + next() * 34 }));
}

export class MapView {
  constructor(layer) {
    this.layer = layer;
    // In map units, turned with the view: the backdrop and the road
    this.ground = new Container();
    this.backdrop = new Container();
    this.road = new Graphics();
    this.lights = new Graphics();
    this.ground.addChild(this.backdrop, this.road, this.lights);
    this.pads = new Graphics();
    this.padGlow = new Graphics();
    this.core = new Container();
    layer.addChild(this.ground, this.pads, this.padGlow, this.core);
    this.flash = 0;
    this.drawGround();
    this.drawRoad();
    this.buildCore();
    this.reorient();
  }

  async load() {
    try {
      const texture = await Assets.load(MAP.backdrop);
      for (const child of this.backdrop.removeChildren()) {
        child.destroy({ children: true, context: true });
      }
      // The picture in the middle, and a mirrored copy against each of its edges and corners
      for (const across of [-1, 0, 1]) {
        for (const down of [-1, 0, 1]) {
          const sprite = new Sprite(texture);
          sprite.width = MAP.width;
          sprite.height = MAP.height;
          sprite.scale.x *= across ? -1 : 1;
          sprite.scale.y *= down ? -1 : 1;
          sprite.position.set(across > 0 ? 2 * MAP.width : 0, down > 0 ? 2 * MAP.height : 0);
          this.backdrop.addChild(sprite);
        }
      }
    } catch (e) {
      console.warn("Starhold: no backdrop picture yet, so the map is drawn in code", e);
    }
  }

  // The view turned: the ground is mirrored across its diagonal (a quarter turn, then a flip), and the pads and the
  // core go to their places in view units
  reorient() {
    this.ground.rotation = view.turned ? Math.PI / 2 : 0;
    this.ground.scale.set(1, view.turned ? -1 : 1);
    this.drawPads();
    this.core.position.set(...toView(...MAP.core));
  }

  drawGround() {
    const g = new Graphics();
    g.rect(0, -80, MAP.width, MAP.height + 80).fill(0x181b20);
    for (let band = 0; band < 8; band++) {
      g.rect(0, band * 160, MAP.width, 160).fill({ color: band % 2 ? 0x1d2127 : 0x16191e });
    }
    for (const { x, y, r } of craterSpots()) {
      g.circle(x, y, r).fill({ color: 0x0f1115, alpha: 0.75 });
      g.circle(x - r * 0.12, y - r * 0.12, r * 0.82).fill({ color: 0x23272e, alpha: 0.6 });
    }
    this.backdrop.addChild(g);
  }

  drawRoad() {
    const g = this.road;
    roadPath(g).stroke({ width: 66, color: ROAD_EDGE, join: "round", cap: "round" });
    roadPath(g).stroke({ width: 58, color: ROAD_BED, join: "round", cap: "round" });
    roadPath(g).stroke({ width: 44, color: ROAD_TOP, join: "round", cap: "round" });
    // Seams across the road's plates, and a row of guide lights down each edge
    for (const p of alongRoad(SEAM_EVERY)) {
      g.moveTo(p.x - p.dy * 22, p.y + p.dx * 22).lineTo(p.x + p.dy * 22, p.y - p.dx * 22);
    }
    g.stroke({ width: 2, color: ROAD_SEAM });
    for (const p of alongRoad(LIGHT_EVERY)) {
      this.lights.circle(p.x - p.dy * 26, p.y + p.dx * 26, 2.6).circle(p.x + p.dy * 26, p.y - p.dx * 26, 2.6);
    }
    this.lights.fill({ color: LIGHT });
  }

  drawPads() {
    this.pads.clear();
    this.padGlow.clear();
    for (const spot of MAP.spots) {
      const [x, y] = toView(...spot);
      this.pads.regularPoly(x, y, PAD_RADIUS, 6, HEX).fill(PAD).stroke({ width: 2, color: 0x081118 });
      this.pads.regularPoly(x, y, PAD_RADIUS - 9, 6, HEX).stroke({ width: 1.5, color: PAD_LINE, alpha: 0.25 });
      this.padGlow.regularPoly(x, y, PAD_RADIUS - 2, 6, HEX).stroke({ width: 3, color: PAD_LINE });
    }
  }

  buildCore() {
    const base = new Graphics();
    base.circle(0, 0, 52).fill({ color: 0x050a10, alpha: 0.85 }).stroke({ width: 3, color: 0x2a6f8f });
    base.circle(0, 0, 40).fill(0x0c1d29).stroke({ width: 2, color: 0x6fe6ff, alpha: 0.6 });
    this.coreSpin = new Graphics();
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3;
      this.coreSpin.moveTo(Math.cos(a) * 33, Math.sin(a) * 33).arc(0, 0, 33, a, a + 0.6);
    }
    this.coreSpin.stroke({ width: 4, color: CORE, alpha: 0.8 });
    this.coreHalo = new Graphics().circle(0, 0, 30).fill({ color: CORE, alpha: 0.25 });
    this.coreHalo.blendMode = "add";
    this.coreGlow = new Graphics().circle(0, 0, 16).fill({ color: 0xe6fdff });
    this.core.addChild(base, this.coreSpin, this.coreHalo, this.coreGlow);
  }

  animate(t) {
    this.lights.alpha = 0.55 + 0.25 * Math.sin(t * 2);
    this.padGlow.alpha = 0.35 + 0.2 * Math.sin(t * 2.4);
    this.coreSpin.rotation = t * 0.8;
    this.coreGlow.scale.set(0.85 + 0.15 * Math.sin(t * 3));
    this.coreHalo.scale.set(1 + 0.2 * Math.sin(t * 3));
    this.flash = Math.max(0, this.flash - FLASH_FADE);
    this.core.tint = this.flash > 0 ? 0xff5d86 : 0xffffff;
  }

  // A robot reached the core
  flashCore() {
    this.flash = 1;
  }
}
