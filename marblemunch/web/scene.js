// Marble Munch's board, drawn with PixiJS. The bot sends where everything is 30 times a second; this draws it
// smoothly at the screen's own frame rate, turned so the player's own hippo is at the bottom.
import { Application, Assets, Container, Graphics, Sprite, Text } from "./vendor/pixi.min.mjs";

// The same numbers as marblemunch/common/rules.py (tests/test_page.py checks they match)
const TICK_RATE = 30;
const HOME_DEPTH = 250;
const MAX_REACH = 200;
const STRETCH_SECONDS = 0.6;
const RETRACT_SECONDS = 0.4;
const SNAP_COOLDOWN = 0.3;
const POOL_MIN = 100;
const POOL_MAX = 900;
const MARBLE_RADIUS = 23;

const STRETCH_SPEED = MAX_REACH / STRETCH_SECONDS;
const RETRACT_SPEED = MAX_REACH / RETRACT_SECONDS;
const TICK_MS = 1000 / TICK_RATE;
// Drawn this many updates behind the newest one, so small changes in when updates arrive never show
const BUFFER_TICKS = 2;
// How fast the drawing's delay shrinks back after a late update, in milliseconds per update
const OFFSET_DRIFT = 0.5;
// The board art is 600 pixels across; the bot's 1000 units map onto it
const ART = 600;
const SCALE = ART / 1000;
const COLORS = ["p1", "p2", "p3", "p4"];
const TAU = Math.PI * 2;
const TURN_MS = 500;
const SHAKE_SECONDS = 0.35;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const PLUS_STYLE = {
  fontFamily: "Fredoka",
  fontSize: 34,
  fontWeight: "700",
  fill: "#ffffff",
  stroke: { color: "#3a2aa8", width: 6 },
};

// Where a mouth `depth` units out from its wall is on the board. Seats are 0 bottom, 1 left, 2 top, 3 right
function mouthPosition(seat, depth) {
  if (seat === 0) {
    return [500, 1000 - depth];
  }
  if (seat === 1) {
    return [depth, 500];
  }
  if (seat === 2) {
    return [500, depth];
  }
  return [1000 - depth, 500];
}

function bounce(position, speed) {
  const low = POOL_MIN + MARBLE_RADIUS;
  const high = POOL_MAX - MARBLE_RADIUS;
  if (position < low) {
    return [2 * low - position, Math.abs(speed)];
  }
  if (position > high) {
    return [2 * high - position, -Math.abs(speed)];
  }
  return [position, speed];
}

// The player's own hippo, run on the page with the bot's rules so it answers the moment they press.
// The bot is still the judge: what it eats comes from the bot's updates
class LocalHippo {
  constructor() {
    this.reach = 0;
    this.open = false;
    this.holding = false;
    this.queued = false;
    this.cooldown = 0;
  }

  press() {
    this.holding = true;
    if (this.open) {
      return;
    }
    if (this.cooldown <= 0) {
      this.open = true;
    } else {
      this.queued = true;
    }
  }

  release() {
    this.holding = false;
    this.queued = false;
  }

  // True when the mouth snapped shut
  step(dt) {
    if (this.open) {
      this.reach = Math.min(MAX_REACH, this.reach + STRETCH_SPEED * dt);
      if (!this.holding || this.reach >= MAX_REACH) {
        this.open = false;
        this.cooldown = SNAP_COOLDOWN;
        return true;
      }
      return false;
    }
    this.reach = Math.max(0, this.reach - RETRACT_SPEED * dt);
    this.cooldown = Math.max(0, this.cooldown - dt);
    if (this.queued && this.holding && this.cooldown <= 0) {
      this.queued = false;
      this.open = true;
    }
    return false;
  }
}

function sprite(texture, anchorX, anchorY, x, y) {
  const node = new Sprite(texture);
  node.anchor.set(anchorX, anchorY);
  node.position.set(x, y);
  return node;
}

// One hippo, drawn in the bottom seat's frame and turned into its own seat. Its neck stretches to its reach,
// and its head sits at the end of the neck
class HippoView {
  constructor(textures, seat) {
    const color = COLORS[seat];
    this.root = new Container();
    this.root.pivot.set(ART / 2, ART / 2);
    this.root.position.set(ART / 2, ART / 2);
    this.root.rotation = (seat * Math.PI) / 2;
    this.neck = sprite(textures[`hippo_neck_${color}`], 0.5, 1, 300, 530);
    this.body = sprite(textures[`hippo_body_${color}`], 0.5, 0, 300, 492);
    this.open = sprite(textures[`hippo_head_open_${color}`], 0.5, 1, 300, 527);
    this.closed = sprite(textures[`hippo_head_closed_${color}`], 0.5, 1, 300, 527);
    this.root.addChild(this.neck, this.body, this.open, this.closed);
    this.root.eventMode = "static";
    this.root.cursor = "pointer";
    this.pose(0, false);
  }

  pose(reach, open) {
    const headBottom = 527 - reach * SCALE;
    this.neck.visible = reach > 1;
    this.neck.height = 530 - (headBottom - 10);
    this.open.visible = open;
    this.closed.visible = !open;
    this.open.y = headBottom;
    this.closed.y = headBottom;
  }
}

// The drawn moment between two updates: marbles and necks slide from `a` toward `b`
function blend(a, b, t) {
  const next = new Map(b.m.map((marble) => [marble[0], marble]));
  const marbles = [];
  for (const [id, x, y] of a.m) {
    const to = next.get(id);
    // A marble missing from the next update was eaten in between; it pops when that update is drawn
    if (to) {
      marbles.push([id, x + (to[1] - x) * t, y + (to[2] - y) * t]);
    }
  }
  return {
    f: a.f + (b.f - a.f) * t,
    m: marbles,
    r: a.r.map((reach, seat) => reach + (b.r[seat] - reach) * t),
    o: t < 0.5 ? a.o : b.o,
    s: a.s,
  };
}

class Scene {
  constructor(app, textures) {
    this.app = app;
    // The whole board, turned so the player's own hippo is at the bottom
    this.world = new Container();
    this.world.pivot.set(ART / 2, ART / 2);
    app.stage.addChild(this.world);
    this.world.addChild(new Sprite(textures.hippo_board));
    this.marbleLayer = new Container();
    this.world.addChild(this.marbleLayer);
    this.hippos = COLORS.map((color, seat) => new HippoView(textures, seat));
    this.hippos.forEach((hippo, seat) => {
      hippo.root.on("pointertap", () => this.onSeatTap(seat));
      this.world.addChild(hippo.root);
    });
    this.effectLayer = new Container();
    this.world.addChild(this.effectLayer);
    this.marbleTexture = textures.hippo_marble;
    this.marbleSprites = new Map();
    this.frames = [];
    this.offset = 0;
    this.drawn = null;
    this.pending = [];
    this.animations = [];
    this.turn = { from: 0, to: 0, start: 0 };
    this.mine = { seat: null, playing: false, hippo: new LocalHippo() };
    this.shakeLeft = 0;
    this.demo = null;
    this.size = { width: 0, height: 0 };
    this.onSeatTap = () => {};
    this.onEffect = () => {};
    app.ticker.add((ticker) => this.draw(ticker.deltaMS / 1000));
  }

  setSeats(kinds) {
    this.hippos.forEach((hippo, seat) => {
      hippo.root.alpha = kinds[seat] === "empty" ? 0.5 : 1;
    });
  }

  setMySeat(seat, playing) {
    this.mine.playing = playing && seat !== null;
    if (!this.mine.playing) {
      this.mine.hippo = new LocalHippo();
    }
    if (seat === this.mine.seat) {
      return;
    }
    this.mine.seat = seat;
    const target = seat === null ? 0 : (-seat * Math.PI) / 2;
    const current = this.world.rotation;
    // The short way round
    const diff = ((((target - current) % TAU) + TAU + Math.PI) % TAU) - Math.PI;
    this.turn = { from: current, to: current + diff, start: performance.now() };
  }

  setHeld(held) {
    if (!this.mine.playing) {
      return;
    }
    if (held) {
      this.mine.hippo.press();
    } else {
      this.mine.hippo.release();
    }
  }

  // A full snapshot: start drawing again from this board, or clear it
  reset(board) {
    this.demo = null;
    this.pending = [];
    this.frames = board ? [board] : [];
    if (board) {
      this.offset = performance.now() - board.f * TICK_MS;
    }
  }

  push(frame) {
    const newest = this.frames[this.frames.length - 1];
    if (newest && frame.f <= newest.f) {
      return;
    }
    const arrival = performance.now() - frame.f * TICK_MS;
    // Follow the latest an update has arrived, and drift back slowly, so one late update doesn't add delay for good
    this.offset = this.frames.length ? Math.max(arrival, this.offset - OFFSET_DRIFT) : arrival;
    this.frames.push(frame);
    if (this.frames.length > 30) {
      this.frames.shift();
    }
    if (newest) {
      this.queueEffects(newest, frame);
    }
  }

  // Effects wait until the drawn moment reaches the update they happened in, so pops line up with the marbles
  queueEffects(before, after) {
    const still = new Set(after.m.map((marble) => marble[0]));
    for (const [id, x, y] of before.m) {
      if (!still.has(id)) {
        this.pending.push({ f: after.f, kind: "pop", x, y });
      }
    }
    for (let seat = 0; seat < 4; seat += 1) {
      if (after.s[seat] > before.s[seat]) {
        this.pending.push({ f: after.f, kind: "score", seat, by: after.s[seat] - before.s[seat] });
      }
      if (before.o[seat] && !after.o[seat] && !(this.mine.playing && seat === this.mine.seat)) {
        this.pending.push({ f: after.f, kind: "snap", seat });
      }
    }
  }

  startDemo() {
    this.reset(null);
    this.demo = Array.from({ length: 20 }, (_, id) => {
      const angle = Math.random() * TAU;
      const speed = 150 + Math.random() * 100;
      const position = () => 200 + Math.random() * 600;
      return { id, x: position(), y: position(), vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed };
    });
  }

  shake() {
    if (!reducedMotion.matches) {
      this.shakeLeft = SHAKE_SECONDS;
    }
  }

  draw(dt) {
    this.fit();
    this.drawTurn(performance.now());
    if (this.demo) {
      this.stepDemo(dt);
    } else {
      this.drawn = this.sample(performance.now());
      this.drawMarbles(this.drawn ? this.drawn.m : []);
      this.drawHippos(this.drawn);
      if (this.drawn) {
        this.runEffects(this.drawn.f);
      }
    }
    this.drawMine(dt);
    this.drawAnimations(dt);
    this.drawShake(dt);
  }

  fit() {
    const { width, height } = this.app.screen;
    if (width === this.size.width && height === this.size.height) {
      return;
    }
    this.size = { width, height };
    this.world.scale.set(Math.min(width, height) / ART);
  }

  drawTurn(now) {
    const { from, to, start } = this.turn;
    const t = reducedMotion.matches ? 1 : Math.min(1, (now - start) / TURN_MS);
    const eased = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
    this.world.rotation = from + (to - from) * eased;
  }

  // The board two updates behind the newest, timed from when updates arrive
  sample(now) {
    const frames = this.frames;
    if (!frames.length) {
      return null;
    }
    const at = (now - this.offset) / TICK_MS - BUFFER_TICKS;
    const index = frames.findIndex((frame) => frame.f > at);
    if (index === -1) {
      // Out of updates: hold the newest until the next one arrives
      return frames[frames.length - 1];
    }
    if (index === 0) {
      return frames[0];
    }
    const a = frames[index - 1];
    const b = frames[index];
    return blend(a, b, (at - a.f) / (b.f - a.f));
  }

  drawMarbles(list) {
    const seen = new Set();
    for (const [id, x, y] of list) {
      seen.add(id);
      let node = this.marbleSprites.get(id);
      if (!node) {
        node = sprite(this.marbleTexture, 0.5, 0.5, 0, 0);
        this.marbleSprites.set(id, node);
        this.marbleLayer.addChild(node);
      }
      node.position.set(x * SCALE, y * SCALE);
    }
    for (const [id, node] of this.marbleSprites) {
      if (!seen.has(id)) {
        node.destroy();
        this.marbleSprites.delete(id);
      }
    }
  }

  drawHippos(frame) {
    this.hippos.forEach((hippo, seat) => {
      if (this.mine.playing && seat === this.mine.seat) {
        return;
      }
      if (frame) {
        hippo.pose(frame.r[seat], frame.o[seat] === 1);
      } else {
        hippo.pose(0, false);
      }
    });
  }

  drawMine(dt) {
    const { seat, playing, hippo } = this.mine;
    if (!playing) {
      return;
    }
    if (hippo.step(dt)) {
      this.onEffect("snap", seat);
    }
    // Once the mouth is shut, ease toward the bot's own reach, since the bot is the judge
    if (!hippo.open && this.drawn) {
      hippo.reach += (this.drawn.r[seat] - hippo.reach) * Math.min(1, dt * 6);
    }
    this.hippos[seat].pose(hippo.reach, hippo.open);
  }

  runEffects(f) {
    const due = this.pending.filter((effect) => effect.f <= f);
    if (!due.length) {
      return;
    }
    this.pending = this.pending.filter((effect) => effect.f > f);
    for (const effect of due) {
      if (effect.kind === "pop") {
        this.pop(effect.x, effect.y);
      } else if (effect.kind === "score") {
        this.plus(effect.seat, effect.by);
      }
      this.onEffect(effect.kind, effect.seat);
    }
  }

  pop(x, y) {
    const ring = new Graphics().circle(0, 0, 14).stroke({ width: 4, color: 0xffffff });
    ring.position.set(x * SCALE, y * SCALE);
    this.animate(ring, 0.35, (node, t) => {
      node.scale.set(1 + t * 1.6);
      node.alpha = 1 - t;
    });
  }

  plus(seat, amount) {
    const [x, y] = mouthPosition(seat, HOME_DEPTH);
    const label = new Text({ text: `+${amount}`, style: PLUS_STYLE });
    label.anchor.set(0.5);
    // Upright and floating up the screen, however the board is turned
    const turn = this.world.rotation;
    label.rotation = -turn;
    const upX = -Math.sin(turn);
    const upY = -Math.cos(turn);
    this.animate(label, 0.8, (node, t) => {
      node.position.set(x * SCALE + upX * t * 70, y * SCALE + upY * t * 70);
      node.alpha = 1 - t * t;
    });
  }

  animate(node, seconds, update) {
    this.effectLayer.addChild(node);
    this.animations.push({ node, seconds, age: 0, update });
    update(node, 0);
  }

  drawAnimations(dt) {
    this.animations = this.animations.filter((animation) => {
      animation.age += dt;
      const t = Math.min(1, animation.age / animation.seconds);
      animation.update(animation.node, t);
      if (t < 1) {
        return true;
      }
      animation.node.destroy();
      return false;
    });
  }

  drawShake(dt) {
    let dx = 0;
    let dy = 0;
    if (this.shakeLeft > 0) {
      this.shakeLeft = Math.max(0, this.shakeLeft - dt);
      const strength = 8 * (this.shakeLeft / SHAKE_SECONDS);
      dx = (Math.random() * 2 - 1) * strength;
      dy = (Math.random() * 2 - 1) * strength;
    }
    this.world.position.set(this.size.width / 2 + dx, this.size.height / 2 + dy);
  }

  // The browser preview: marbles rolling with the bot's bounce rules, no bot needed
  stepDemo(dt) {
    for (const marble of this.demo) {
      [marble.x, marble.vx] = bounce(marble.x + marble.vx * dt, marble.vx);
      [marble.y, marble.vy] = bounce(marble.y + marble.vy * dt, marble.vy);
    }
    this.drawMarbles(this.demo.map((marble) => [marble.id, marble.x, marble.y]));
    this.drawHippos(null);
  }
}

async function loadArt() {
  const names = ["hippo_board", "hippo_marble"];
  for (const color of COLORS) {
    names.push(`hippo_body_${color}`, `hippo_neck_${color}`, `hippo_head_open_${color}`, `hippo_head_closed_${color}`);
  }
  // Drawn at twice their size, so they stay sharp when the board is scaled up
  const textures = await Promise.all(names.map((name) => Assets.load({ src: `art/${name}.svg`, data: { resolution: 2 } })));
  return Object.fromEntries(names.map((name, i) => [name, textures[i]]));
}

async function loadFont() {
  try {
    await document.fonts.load('700 34px "Fredoka"');
  } catch (e) {
    console.warn("Marble Munch: the font didn't load, so the +1s use a fallback", e);
  }
}

export async function createScene(host) {
  const app = new Application();
  await app.init({
    resizeTo: host,
    backgroundAlpha: 0,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  host.append(app.canvas);
  const [textures] = await Promise.all([loadArt(), loadFont()]);
  return new Scene(app, textures);
}
