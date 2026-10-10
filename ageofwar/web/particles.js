// The original's cosmetic particles: blood, gold, debris, smoke and blasts. The bot sends where they start; each
// one then moves by its own sprite's script from the original, one step per frame of the 40 a second clock.
import { Text } from "./vendor/pixi.min.mjs";

const GROUND = 425;
// The original's part numbers
export const GOLD = 1;
const BLOOD = 2;
const TRAIL = 4;
const SMOKE = 6;
const BLAST = 7;
const BOMB_BLAST = 12;
const FALLING = new Set([3, 9, 10]);

const random = Math.random;
// ActionScript's random(n): a whole number from 0 to n - 1
const randomInt = (n) => Math.floor(random() * n);

class Particle {
  constructor(node) {
    this.node = node;
    this.done = false;
  }

  step() {}
}

// Blood, and the oil splash and rubble: thrown a little, slowed by the air, falling until they reach the ground
class Drop extends Particle {
  constructor(node, x, y, kind) {
    super(node);
    const falling = FALLING.has(kind);
    this.gravity = falling ? 0.15 : 0.2;
    this.xs = falling ? random() * 6 - 3 : random() * 2 - 1;
    this.g = falling ? -random() * 3 + 1 : random() * 1.5 - 1;
    const spread = falling ? [9, 4] : [6, 3];
    node.position.set(x + (random() * spread[0] - spread[1]), y + (random() * spread[0] - spread[1]));
    if (falling) {
      node.scale.set((randomInt(40) + 100) / 100);
    }
    this.spin = randomInt(4) - 1.5;
  }

  step() {
    this.g += this.gravity;
    this.xs /= 1.1;
    this.node.x += this.xs;
    this.node.y += this.g;
    this.node.angle += this.spin;
    this.done = this.node.y > GROUND;
  }
}

// The meteor's trail: rises a little, shrinking and fading
class Trail extends Particle {
  constructor(node, x, y, rotation) {
    super(node);
    this.scale = randomInt(20) + 100;
    node.angle = rotation;
    node.scale.set(this.scale / 100);
    node.position.set(x + (random() * 9 - 4), y + (random() * 9 - 4));
  }

  step() {
    this.node.y -= 1;
    this.scale -= 4;
    this.node.alpha -= 0.04;
    this.node.scale.set(Math.max(0, this.scale) / 100);
    this.done = this.node.alpha <= 0 || this.scale <= 0 || this.node.y > GROUND;
  }
}

class Smoke extends Particle {
  constructor(node, x, y) {
    super(node);
    node.position.set(x + (random() * 6 - 3), y + (random() * 6 - 3));
  }

  step() {
    this.node.alpha -= 0.01;
    this.done = this.node.alpha <= 0;
  }
}

// Blasts play their animation, which removes itself on its 28th frame
class Blast extends Particle {
  constructor(node, x, y) {
    super(node);
    node.position.set(x, y);
  }

  step() {
    this.done = this.node.removed;
  }
}

// "+ 20" over a dead unit: floats up, slowing, then fades
class Gold extends Particle {
  constructor(node, x, y, amount, font) {
    super(node);
    node.position.set(x, y);
    const label = new Text({
      text: `+ ${amount}`,
      style: { fontFamily: font, fontSize: 12, fill: 0xffff00, fontWeight: "bold", stroke: { color: 0x000000, width: 3 } },
    });
    label.position.set(-label.width / 2 + 8, -8);
    node.addChild(label);
    this.rise = 3;
  }

  step() {
    this.node.y -= this.rise;
    this.rise /= 1.1;
    if (this.rise <= 0.2) {
      this.node.alpha -= 0.02;
    }
    this.done = this.node.alpha <= 0;
  }
}

export class Particles {
  constructor(lib, layer, font) {
    this.lib = lib;
    this.layer = layer;
    this.font = font;
    this.list = [];
  }

  // One event from the bot: [part, x, y, count, extra]
  spawn([part, x, y, count, extra]) {
    for (let i = 0; i < count; i += 1) {
      const node = this.lib.makeExported(`part${part}`);
      const particle = this.make(part, node, x, y, extra);
      if (!particle) {
        node.destroy({ children: true });
        continue;
      }
      // The blood and oil drops show one of twelve shapes, picked when they appear
      for (const child of node.children) {
        if (child.charId === 946) {
          child.gotoAndStop(randomInt(12) + 1);
        }
      }
      this.layer.addChild(node);
      this.list.push(particle);
    }
  }

  make(part, node, x, y, extra) {
    if (part === GOLD) {
      // The original's gold sprite holds a coin and two text fields: this draws the text itself
      for (const child of [...node.children]) {
        if (child.textVariable !== undefined && child.textVariable !== null) {
          child.visible = false;
        }
      }
      return new Gold(node, x, y, extra, this.font);
    }
    if (part === BLOOD || FALLING.has(part)) {
      return new Drop(node, x, y, part);
    }
    if (part === TRAIL) {
      return new Trail(node, x, y, extra);
    }
    if (part === SMOKE) {
      return new Smoke(node, x, y);
    }
    if (part === BLAST || part === BOMB_BLAST) {
      return new Blast(node, x, y);
    }
    return null;
  }

  // One frame of the 40 a second clock
  step() {
    for (const particle of this.list) {
      particle.step();
      particle.node.advance?.();
      if (particle.done) {
        particle.node.destroy({ children: true });
      }
    }
    this.list = this.list.filter((particle) => !particle.done);
  }

  clear() {
    for (const particle of this.list) {
      particle.node.destroy({ children: true });
    }
    this.list = [];
  }
}
