// Tanks' field, drawn with PixiJS in the original's 550 x 400 pixels and scaled to fit the screen. Things stack
// as the original stacked them: the landscape, tanks, shells and blasts, then trees, then the ground in front, and
// the tanks' names over all of it.
import { Application, Assets, Container, Graphics, Sprite, Text } from "./vendor/pixi.min.mjs";

// The same numbers as tanks/common (tests/test_page.py checks they match)
const WIDTH = 550;
const HEIGHT = 400;
const STEP_RATE = 25;
const DRIVE_STEP = 0.5;
const MIN_X = 10;
const MAX_X = 540;
const SHIELD_STRENGTH = { 3: 100, 4: 200, 5: 400, 6: 600 };
// The shell whose explosion each blast plays (tests/test_page.py checks the art matches the bot's blast sizes)
const BLAST_ART = {
  small: "bmissile_g",
  missile: "missile_g",
  bnuke: "bnuke_g",
  nuke: "nuke_g",
  funky: "funky_g",
  mirv: "mirv_g",
  death: "death_g",
  broller: "broller_g",
  roller: "roller_g",
  hroller: "hroller_g",
  strike: "amissile",
};
// Until the blast goes off (its fifth frame) the fireball keeps the shell's launch angle, then it turns upright
const UPRIGHT_FROM = 4;
const BIG_BOOMS = new Set(["nuke", "death", "hroller"]);
const MEDIUM_BOOMS = new Set(["bnuke", "mirv", "roller", "strike"]);
// Each tank's name, in the field's own pixels. Names sit in a layer above the ground and trees, so a hill beside a
// tank never hides part of its name. When the field is scaled down to fit a phone, a name is drawn bigger so it
// stays NAME_MIN_PX on screen, and cut shorter so five of them still fit along the field (see sizeNames)
const NAME_FONT = 8;
const NAME_STYLE = {
  fontFamily: "system-ui, sans-serif",
  fontSize: NAME_FONT,
  fontWeight: "700",
  fill: "#ffffff",
  stroke: { color: "#000000", width: 2 },
};
const NAME_ABOVE = 17;
const NAME_MIN_PX = 10;
// Longer names are cut to this many characters, and to NAME_MAX_SMALL on a field scaled below SMALL_FIELD
const NAME_MAX = 12;
const NAME_MAX_SMALL = 8;
const SMALL_FIELD = 0.9;
// Names keep at least this many pixels apart sideways, and go up a row where they would be closer, at most
// NAME_ROWS - 1 rows. Five rows is one for each seat, so a name finds a free one unless the tanks are packed together
const NAME_GAP = 2;
const NAME_ROWS = 5;
// A raised name is tied to its tank by a line that ends this far above the tank's ground point, clear of its barrel
const TICK_END = 13;
// The original's tank colors, one per seat
const COLORS = [0xf02400, 0x00cc33, 0x0033ff, 0xf0df0f, 0xea9300];
const GROUND_COLORS = { 1: 0xf7fbff, 2: 0x4f9a2f, 3: 0xe6c27f };
// A line along the ground's top in each landscape: blue shadow on snow, fresh grass, darker sand
const GROUND_EDGES = { 1: 0xbfd2ea, 2: 0x8fd14f, 3: 0xc99a55 };
const GROUND_EDGE_WIDTH = 1.5;
const SHIELD_ART = { 3: "shield_weak", 4: "shield", 5: "shield_strong", 6: "shield_super" };
// The teleport's frames, as the bot times them (the first is never played): a light column rises at the tank, the
// tank vanishes, the column moves to the spot, and the tank appears there
const TELEPORT_HIDE = 17;
const TELEPORT_MOVE = 35;
const TELEPORT_SHOW = 41;
const TELEPORT_END = 48;
const BEAM_COLOR = 0x4fd8ff;
const BEAM_WIDE = 7;
const BEAM_TALL = 60;
// Firing kicks the barrel back along itself for its first frames, then it slides forward again
const RECOIL_FRAMES = 15;
const RECOIL_KICK = 2;
const RECOIL_PX = 2.2;
// The turn marker: two gold rings pulse out round the tank and a small arrow bobs over it, for 35 frames
const TURN_FRAMES = 35;
const TURN_COLOR = 0xffd23f;
const OUTLINE = 0x27303f;
// A destroyed tank: a flash, a puff of smoke and pieces of its body thrown out, for 11 frames. Each piece is
// [x speed, y speed, size] in pixels a frame, the same on every screen
const WRECK_FRAMES = 11;
const WRECK_FALL = 0.35;
const DEBRIS = [
  [-1.6, -2.4, 2.2],
  [1.4, -2.8, 1.8],
  [-0.6, -3.4, 1.4],
  [2.2, -1.6, 1.6],
  [-2.4, -1.2, 1.2],
  [0.5, -2.2, 2.4],
];
// The shock ring round a blast is this flat, as the fireball is about twice as wide as it is tall
const RING_FLAT = 0.48;
const RING_COLOR = 0xfff1c4;
// How quickly a tank slides to where the bot last put it
const FOLLOW_RATE = 15;
// Your own driving runs ahead of the bot by at most this many pixels
const MAX_LEAD = 4;

// What a person sees as single characters, so a flag or a joined emoji is never split. Older browsers have no
// segmenter and count code points instead
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

export function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

// The name as it shows over a tank, cut with an ellipsis when it is longer than `max` characters
export function fieldName(name, max = NAME_MAX) {
  const letters = characters(name);
  return letters.length > max ? `${letters.slice(0, max - 1).join("")}…` : name;
}

// How much of rectangle `a` lies on rectangle `b`, counting the gap beside it as covered. Rectangles are
// { left, top, width, height }
function nameCovered(a, b) {
  const across = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left) + NAME_GAP;
  const down = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top);
  return across > 0 && down > 0 ? across * down : 0;
}

// Where each name goes, for boxes of { x, y, width, height } centered on x with y the top edge: pulled inside the
// field's edges, and raised up to NAME_ROWS - 1 rows (a row is a name's height and a pixel) to the first place that
// touches no name already placed, or to the one that covers least when there is none. Names are placed from left
// to right. Gives { x, rise } for each box, in the order they came in
export function layoutNames(boxes) {
  const order = boxes.map((box, index) => index).sort((a, b) => boxes[a].x - boxes[b].x);
  const taken = [];
  const placed = [];
  for (const index of order) {
    const { x, y, width, height } = boxes[index];
    const left = Math.min(WIDTH - width, Math.max(0, x - width / 2));
    let best = null;
    for (let row = 0; row < NAME_ROWS && (best === null || best.covered > 0); row += 1) {
      const rise = row * (height + 1);
      const rect = { left, top: y - rise, width, height };
      const covered = taken.reduce((sum, other) => sum + nameCovered(rect, other), 0);
      if (best === null || covered < best.covered) {
        best = { rise, rect, covered };
      }
    }
    taken.push(best.rect);
    placed[index] = { x: left + width / 2, rise: best.rise };
  }
  return placed;
}

function place(art, name, x = 0, y = 0) {
  const node = new Sprite(art.texture(name));
  const info = art.info[name];
  node.anchor.set(info.ax / info.w, info.ay / info.h);
  node.position.set(x, y);
  return node;
}

// How wide the teleport's light column is on each frame: it opens at the tank until the tank vanishes, closes, and
// opens again at the spot until the tank appears there
function beamWidth(frame) {
  const close = 6;
  if (frame < TELEPORT_HIDE) {
    return (BEAM_WIDE * (frame - 1)) / (TELEPORT_HIDE - 1);
  }
  if (frame < TELEPORT_HIDE + close) {
    return BEAM_WIDE * (1 - (frame - TELEPORT_HIDE) / close);
  }
  if (frame < TELEPORT_MOVE) {
    return 0;
  }
  if (frame < TELEPORT_SHOW) {
    return (BEAM_WIDE * (frame - TELEPORT_MOVE + 1)) / (TELEPORT_SHOW - TELEPORT_MOVE);
  }
  return BEAM_WIDE * (1 - (frame - TELEPORT_SHOW) / (TELEPORT_END - TELEPORT_SHOW));
}

// The light column, standing on its node's point: a soft outer glow, a bright core fading toward the top, a pool of
// light on the ground and sparks rising through it
function drawBeam(column, width, frame) {
  column.clear();
  if (width <= 0) {
    return;
  }
  const bands = 5;
  for (let band = 0; band < bands; band += 1) {
    const top = -BEAM_TALL + (band * BEAM_TALL) / bands;
    const alpha = (band + 1) / bands;
    column.rect(-width / 2, top, width, BEAM_TALL / bands).fill({ color: BEAM_COLOR, alpha: 0.3 * alpha });
    column.rect(-width / 5, top, width / 2.5, BEAM_TALL / bands).fill({ color: 0xffffff, alpha: 0.75 * alpha });
  }
  column.ellipse(0, 3, width * 1.4, width * 0.4).fill({ color: BEAM_COLOR, alpha: 0.5 });
  for (let spark = 0; spark < 4; spark += 1) {
    const rise = (frame * 3 + spark * 15) % BEAM_TALL;
    column.circle(Math.sin(spark * 2.1 + frame * 0.5) * width * 0.6, -rise, 0.8).fill({ color: 0xffffff, alpha: 0.9 });
  }
}

// One tank: its shield and parachute behind it, its tracks, its body in the seat's color, and its barrel
class TankView {
  constructor(art, seat, layer, tickLayer, nameLayer, nameSize) {
    this.root = new Container();
    this.shields = Object.fromEntries(Object.entries(SHIELD_ART).map(([kind, name]) => [kind, place(art, name)]));
    this.parachute = place(art, "parachute");
    this.body = new Container();
    const color = place(art, "tank_body");
    color.tint = COLORS[seat];
    this.body.addChild(place(art, "tank_tracks"), color);
    this.barrel = place(art, "barrel");
    this.barrelAnchor = this.barrel.anchor.x;
    this.barrelWidth = art.info.barrel.w;
    this.recoil = -1;
    // Made once and only given new text, since a new Text each frame would cost a texture each time
    this.label = new Text({ text: "", style: NAME_STYLE });
    this.label.anchor.set(0.5, 1);
    // The line from a raised name down to this tank, drawn in the seat's color with a black edge, under every name. One
    // Graphics, cleared and redrawn when it is needed
    this.seat = seat;
    this.tick = new Graphics();
    this.tick.visible = false;
    // The name as the bot sent it. The label shows it cut to the field's size
    this.name = "";
    this.sizeName(...nameSize);
    this.root.addChild(...Object.values(this.shields), this.parachute, this.body, this.barrel);
    layer.addChild(this.root);
    tickLayer.addChild(this.tick);
    nameLayer.addChild(this.label);
    this.shown = null;
    this.target = { x: 0, y: 0, angle: 90 };
    this.view = null;
    // Gone for a moment while it teleports
    this.hidden = false;
  }

  // The bot's view of this tank. `snap` jumps straight there, for shots played step by step
  set(view, snap) {
    this.view = view;
    this.target = { x: view.x, y: view.y, angle: view.angle };
    if (snap || !this.shown) {
      this.shown = { ...this.target };
    }
  }

  fire() {
    this.recoil = 0;
  }

  setName(name) {
    if (name !== this.name) {
      this.name = name;
      this.label.text = fieldName(name, this.nameMax);
    }
  }

  // Puts the name where the layout says. A name raised above its tank gets a line down to the tank, so it is clear
  // whose name it is
  placeName({ x, rise }) {
    const { label, tick } = this;
    label.x = x;
    label.y -= rise;
    tick.visible = rise > 0;
    if (rise > 0) {
      const { x: tankX, y: tankY } = this.shown;
      const length = tankY - TICK_END - label.y;
      tick
        .clear()
        .rect(tankX - 1.5, label.y, 3, length)
        .fill(0x000000)
        .rect(tankX - 0.5, label.y, 1, length)
        .fill(COLORS[this.seat]);
    }
  }

  // The label at `scale` times its size, drawn at `resolution`, with the name cut to `max` characters
  sizeName(scale, resolution, max) {
    this.nameMax = max;
    this.label.scale.set(scale);
    // Pixi redraws the text on every set, even to the same number
    if (this.label.resolution !== resolution) {
      this.label.resolution = resolution;
    }
    this.label.text = fieldName(this.name, max);
  }

  draw(dt) {
    const view = this.view;
    this.root.visible = Boolean(view && view.alive && !this.hidden);
    // The name goes with the tank, whether it is destroyed or for a moment gone while it teleports
    this.label.visible = this.root.visible;
    if (!this.root.visible) {
      this.tick.visible = false;
      return;
    }
    const follow = 1 - Math.exp(-dt * FOLLOW_RATE);
    for (const key of ["x", "y", "angle"]) {
      this.shown[key] += (this.target[key] - this.shown[key]) * follow;
    }
    const { x, y, angle } = this.shown;
    this.body.position.set(x, y);
    this.barrel.position.set(x, y - 1);
    // The barrel's art points left, so its angle (0 left, 90 up, 180 right) is its rotation
    this.barrel.angle = angle;
    this.parachute.visible = view.chute;
    this.parachute.position.set(x, y - 7.5);
    this.label.position.set(x, y - NAME_ABOVE);
    for (const [kind, sprite] of Object.entries(this.shields)) {
      sprite.visible = view.shield === Number(kind);
      sprite.position.set(x, y);
      // A shield fades as it wears down
      sprite.alpha = Math.round((view.shieldLeft / SHIELD_STRENGTH[kind]) * 100) / 100;
    }
    this.drawRecoil(dt);
  }

  drawRecoil(dt) {
    if (this.recoil < 0) {
      return;
    }
    this.recoil += dt * STEP_RATE;
    if (this.recoil >= RECOIL_FRAMES) {
      this.recoil = -1;
      this.barrel.anchor.x = this.barrelAnchor;
      return;
    }
    const back =
      this.recoil < RECOIL_KICK
        ? this.recoil / RECOIL_KICK
        : 1 - (this.recoil - RECOIL_KICK) / (RECOIL_FRAMES - RECOIL_KICK);
    // The barrel points left from its anchor, so moving the anchor left within it slides it back toward the tank
    this.barrel.anchor.x = this.barrelAnchor - (RECOIL_PX * back) / this.barrelWidth;
  }
}

// A one-off animation at the original's 25 frames a second
class Flipbook {
  constructor(node, count, drawFrame) {
    this.node = node;
    this.count = count;
    this.drawFrame = drawFrame;
    this.age = 0;
    drawFrame(node, 0);
  }

  // False once it has finished
  step(dt) {
    this.age += dt * STEP_RATE;
    const frame = Math.floor(this.age);
    if (frame >= this.count) {
      this.node.destroy({ children: true });
      return false;
    }
    this.drawFrame(this.node, frame);
    return true;
  }
}

class Scene {
  constructor(app, art) {
    this.app = app;
    this.art = art;
    this.world = new Container();
    app.stage.addChild(this.world);
    const mask = new Graphics().rect(0, 0, WIDTH, HEIGHT).fill(0xffffff);
    this.world.addChild(mask);
    this.world.mask = mask;
    this.layers = {};
    for (const name of ["land", "tanks", "effects", "shells", "trees", "ground", "ticks", "names", "marks"]) {
      this.layers[name] = new Container();
      this.world.addChild(this.layers[name]);
    }
    this.ground = new Graphics();
    this.layers.ground.addChild(this.ground);
    this.landscape = null;
    this.tops = null;
    this.groundColor = GROUND_COLORS[1];
    this.groundEdge = GROUND_EDGES[1];
    this.groundDirty = false;
    this.trees = [];
    this.tanks = new Map();
    this.shellSprites = new Map();
    this.flipbooks = [];
    this.turn = null;
    this.live = null;
    this.liveAt = 0;
    this.ownAim = null;
    this.drive = 0;
    this.aimLine = new Graphics();
    this.aimLine.visible = false;
    this.cursor = place(art, "strike_cursor");
    this.target = place(art, "teleport_target");
    this.layers.marks.addChild(this.aimLine, this.cursor, this.target);
    this.cursor.visible = false;
    this.target.visible = false;
    this.size = { width: 0, height: 0 };
    // The labels' scale, resolution and longest name for the field's current size, set by sizeNames
    this.nameSize = [1, 2, NAME_MAX];
    this.shownNames = "";
    this.shownTicks = "";
    this.onEvent = () => {};
    this.onPointer = () => {};
    this.onFrame = null;
    this.listen();
    this.setLandscape(1);
    app.ticker.add((ticker) => this.draw(ticker.deltaMS / 1000));
  }

  // ---------- Snapshots ----------

  setState(state) {
    const field = state.field;
    const landscape = field ? field.landscape : state.landscape === "random" ? 1 : state.landscape;
    this.setLandscape(landscape);
    for (const name of ["ground", "tanks", "trees"]) {
      this.layers[name].visible = Boolean(field);
    }
    if (field) {
      const fresh = !this.tops || state.round !== this.round;
      this.tops = [...field.ground];
      this.groundDirty = true;
      if (fresh) {
        this.setTrees(field.trees);
      }
    }
    this.round = state.round;
    state.tanks.forEach((view, seat) => {
      if (view) {
        this.tank(seat).set(view, false);
      } else if (this.tanks.has(seat)) {
        this.tanks.get(seat).view = null;
      }
    });
    state.seats.forEach((seat, number) => this.tanks.get(number)?.setName(seat.kind === "empty" ? "" : seat.name));
    this.publishNames();
    const turn = state.stage === "playing" ? state.turn : null;
    if (turn !== null && turn !== this.turn && state.tanks[turn]) {
      this.blink(state.tanks[turn]);
    }
    this.turn = turn;
    if (turn === null) {
      this.live = null;
    }
  }

  setLandscape(landscape) {
    if (landscape === this.landscape) {
      return;
    }
    this.landscape = landscape;
    this.groundColor = GROUND_COLORS[landscape];
    this.groundEdge = GROUND_EDGES[landscape];
    this.groundDirty = true;
    const name = `land${landscape}`;
    const [x, y] = this.art.at[name];
    this.layers.land.removeChildren().forEach((child) => child.destroy());
    this.layers.land.addChild(place(this.art, name, x, y));
  }

  setTrees(trees) {
    this.layers.trees.removeChildren().forEach((child) => child.destroy());
    this.trees = trees.map(([x, kind]) => {
      const node = place(this.art, `tree${kind}`, x, this.groundAt(x));
      this.layers.trees.addChild(node);
      return { x, node, speed: 0 };
    });
  }

  groundAt(x) {
    return this.tops[Math.min(WIDTH - 1, Math.max(0, Math.round(x)))];
  }

  // A tree whose ground was blown away falls, faster each frame, until it lands, as in the original
  dropTrees(frames) {
    for (const tree of this.trees) {
      const top = this.groundAt(tree.x);
      if (tree.node.y >= top) {
        tree.node.y = top;
        tree.speed = 0;
        continue;
      }
      tree.speed += frames;
      tree.node.y = Math.min(top, tree.node.y + tree.speed * frames);
    }
  }

  tank(seat) {
    if (!this.tanks.has(seat)) {
      const { tanks, ticks, names } = this.layers;
      this.tanks.set(seat, new TankView(this.art, seat, tanks, ticks, names, this.nameSize));
    }
    return this.tanks.get(seat);
  }

  tankPosition(seat) {
    const tank = this.tanks.get(seat);
    return tank && tank.shown ? { x: tank.shown.x, y: tank.shown.y } : { x: -1000, y: -1000 };
  }

  // ---------- The turn ----------

  // The bot's newest turn update. `ownAim` is your own barrel and power while it's your turn, drawn at once
  setLive(live, ownAim) {
    if (live && live !== this.live) {
      this.live = live;
      this.liveAt = performance.now();
    }
    this.ownAim = ownAim;
    if (!this.live || !this.tanks.has(this.live[0])) {
      return;
    }
    const tank = this.tanks.get(this.live[0]);
    tank.target = { x: this.live[1], y: this.live[2], angle: ownAim ? ownAim.angle : this.live[3] };
    if (ownAim && tank.shown) {
      tank.shown.angle = ownAim.angle;
    }
  }

  setDriving(direction) {
    this.drive = direction;
  }

  // Your own tank drives ahead of the bot's updates, so it moves the moment you press
  leadOwnTank() {
    if (!this.live || !this.ownAim || this.drive === 0 || !this.tanks.has(this.live[0])) {
      return;
    }
    const tank = this.tanks.get(this.live[0]);
    const seconds = (performance.now() - this.liveAt) / 1000;
    const lead = Math.min(MAX_LEAD, seconds * STEP_RATE * DRIVE_STEP);
    const x = Math.max(MIN_X, Math.min(MAX_X, this.live[1] + this.drive * lead));
    tank.target.x = this.live[5] > 0 ? x : this.live[1];
    tank.target.y = this.surface(tank.target.x) - 2;
  }

  // The highest ground under a tank's 13 columns
  surface(x) {
    let top = Infinity;
    for (let column = Math.round(x) - 6; column <= Math.round(x) + 6; column += 1) {
      top = Math.min(top, this.groundAt(column));
    }
    return top;
  }

  setAimLine(on) {
    this.aimLine.visible = on;
    if (!on) {
      this.aimLine.clear();
    }
  }

  // Dots along the barrel, as long as the power
  drawAimLine() {
    if (!this.aimLine.visible || !this.ownAim || !this.live || !this.tanks.has(this.live[0])) {
      return;
    }
    const tank = this.tanks.get(this.live[0]);
    const radians = (this.ownAim.angle * Math.PI) / 180;
    const dx = -Math.cos(radians);
    const dy = -Math.sin(radians);
    this.aimLine.clear();
    for (let along = 8; along <= 8 + this.ownAim.power; along += 4) {
      this.aimLine.circle(tank.shown.x + dx * along, tank.shown.y - 1 + dy * along, 0.8);
    }
    this.aimLine.fill(0xffffff);
  }

  // The air strike's target (flipped to show which side the planes come from) or the teleport's landing spot,
  // following the pointer
  setPicking(picking) {
    this.cursor.visible = Boolean(picking && picking.kind === "strike" && picking.x !== undefined);
    this.target.visible = Boolean(picking && picking.kind === "teleport" && picking.x !== undefined);
    if (!picking || picking.x === undefined) {
      return;
    }
    this.cursor.position.set(picking.x, picking.y);
    this.cursor.scale.x = picking.dir;
    this.target.position.set(picking.x, picking.y);
  }

  // ---------- Shots ----------

  // Every shell flies as the same small dot
  setShells(shells) {
    const seen = new Set();
    for (const { index, x, y } of shells) {
      seen.add(index);
      let node = this.shellSprites.get(index);
      if (!node) {
        node = place(this.art, "shell");
        this.shellSprites.set(index, node);
        this.layers.shells.addChild(node);
      }
      node.position.set(x, y);
    }
    for (const [index, node] of this.shellSprites) {
      if (!seen.has(index)) {
        node.destroy();
        this.shellSprites.delete(index);
      }
    }
  }

  shotEvent([, kind, ...detail]) {
    if (kind === "ground") {
      this.setColumns(detail[0]);
    } else if (kind === "tank") {
      const [seat, view] = detail;
      this.tank(seat).set(view, true);
      this.onEvent("tank", { seat, view });
    } else if (kind === "boom") {
      this.blast(...detail);
    } else if (kind === "die") {
      this.die(...detail);
    } else if (kind === "beam") {
      this.beam(...detail);
    }
  }

  // Changed ground columns as [column, top, column, top, ...]
  setColumns(pairs) {
    for (let i = 0; i < pairs.length; i += 2) {
      this.tops[pairs[i]] = pairs[i + 1];
    }
    this.groundDirty = true;
  }

  startShot(seat) {
    this.tanks.get(seat)?.fire();
  }

  // The shell's explosion: the fireball swells with a shock ring racing out, then smoke rolls up and fades
  blast(x, y, key, rotation) {
    const { scale, frames } = this.art.blasts[BLAST_ART[key]];
    const node = new Container();
    node.position.set(x, y);
    node.scale.set(scale[0], scale[1]);
    const ring = node.addChild(new Graphics());
    const sprites = {};
    this.layers.shells.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, frames.length, (root, index) => {
        const frame = frames[index];
        root.children.forEach((child) => {
          child.visible = false;
        });
        if (frame.ring) {
          const [radius, alpha] = frame.ring;
          ring.visible = true;
          ring
            .clear()
            .ellipse(0, frame.y, radius, radius * RING_FLAT)
            .stroke({ color: RING_COLOR, width: 1.2 + radius * 0.06, alpha });
        }
        if (!frame.art) {
          return;
        }
        sprites[frame.art] ??= root.addChild(place(this.art, frame.art));
        const sprite = sprites[frame.art];
        sprite.visible = true;
        sprite.position.set(frame.x, frame.y);
        sprite.scale.set(frame.sx, frame.sy);
        sprite.angle = frame.rot + (index < UPRIGHT_FROM ? rotation : 0);
        sprite.alpha = frame.alpha;
      }),
    );
    this.onEvent("boom", BIG_BOOMS.has(key) ? "boom_big" : MEDIUM_BOOMS.has(key) ? "boom_medium" : "boom_small");
  }

  // A destroyed tank: a flash, smoke, and pieces of it in its seat's color thrown up and falling
  die(seat, x, y) {
    this.tanks.get(seat).view = null;
    const node = new Container();
    node.position.set(x, y);
    const fire = node.addChild(place(this.art, "fireball"));
    const smoke = node.addChild(place(this.art, "smoke"));
    const bits = node.addChild(new Graphics());
    this.layers.tanks.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, WRECK_FRAMES, (root, frame) => {
        const t = frame / (WRECK_FRAMES - 1);
        fire.visible = frame < 5;
        fire.scale.set(0.12 + frame * 0.07, 0.16 + frame * 0.09);
        smoke.visible = frame >= 3;
        smoke.scale.set(0.5 + t * 0.7, 0.4 + t * 0.5);
        smoke.y = -2 - t * 6;
        smoke.alpha = 0.9 * (1 - t);
        bits.clear();
        for (const [vx, vy, size] of DEBRIS) {
          const px = vx * frame;
          const py = vy * frame + WRECK_FALL * frame * frame;
          bits.rect(px - size / 2, py - size / 2, size, size);
        }
        bits.fill(COLORS[seat]).stroke({ color: OUTLINE, width: 0.4 });
      }),
    );
    this.onEvent("die", seat);
  }

  beam(seat, x0, y0, x1, y1) {
    const tank = this.tank(seat);
    const node = new Graphics();
    this.layers.effects.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, TELEPORT_END - 1, (column, index) => {
        // The first frame is never played
        const frame = index + 2;
        const there = frame >= TELEPORT_MOVE;
        column.position.set(there ? x1 : x0, there ? y1 : y0);
        drawBeam(column, beamWidth(frame), frame);
        tank.hidden = frame >= TELEPORT_HIDE && frame < TELEPORT_SHOW;
      }),
    );
  }

  // Gold rings pulsing out round the tank whose turn it is, with a small arrow bobbing over it
  blink(view) {
    const node = new Graphics();
    node.position.set(view.x, view.y);
    this.layers.effects.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, TURN_FRAMES, (marker, frame) => {
        const fade = Math.min(1, frame / 3, (TURN_FRAMES - 1 - frame) / 4);
        marker.clear();
        for (const start of [0, 0.5]) {
          const phase = ((frame / TURN_FRAMES) * 2 + start) % 1;
          const radius = 7 + phase * 9;
          marker.ellipse(0, 2, radius, radius * 0.42).stroke({ color: TURN_COLOR, width: 1.2, alpha: (1 - phase) * fade });
        }
        const bob = Math.abs(Math.sin((frame / TURN_FRAMES) * Math.PI * 3)) * 1.5;
        const top = -14.5 - bob;
        marker
          .poly([-3, top, 3, top, 0, top + 4])
          .fill({ color: TURN_COLOR, alpha: fade })
          .stroke({ color: OUTLINE, width: 0.6, alpha: fade, join: "round" });
      }),
    );
  }

  // ---------- Drawing ----------

  draw(dt) {
    this.fit();
    if (this.onFrame) {
      this.onFrame(performance.now());
    }
    this.leadOwnTank();
    if (this.tops) {
      this.dropTrees(dt * STEP_RATE);
    }
    if (this.groundDirty && this.tops) {
      this.drawGround();
    }
    for (const tank of this.tanks.values()) {
      tank.draw(dt);
    }
    this.stackNames();
    this.drawAimLine();
    this.flipbooks = this.flipbooks.filter((book) => book.step(dt));
  }

  // The ground as one shape: a step for each column, from its top down past the bottom of the field, with a line
  // along its top
  drawGround() {
    this.groundDirty = false;
    const top = [];
    this.tops.forEach((y, column) => {
      const clipped = Math.min(HEIGHT + 1, y);
      top.push(column, clipped, column + 1, clipped);
    });
    this.ground
      .clear()
      .poly([0, HEIGHT + 1, ...top, WIDTH, HEIGHT + 1])
      .fill(this.groundColor)
      .poly(top, false)
      .stroke({ color: this.groundEdge, width: GROUND_EDGE_WIDTH, join: "round" });
  }

  fit() {
    const { width, height } = this.app.screen;
    if (width === this.size.width && height === this.size.height) {
      return;
    }
    this.size = { width, height };
    const scale = Math.min(width / WIDTH, height / HEIGHT);
    this.world.scale.set(scale);
    this.world.position.set((width - WIDTH * scale) / 2, (height - HEIGHT * scale) / 2);
    this.sizeNames(scale);
  }

  // Names stay at least NAME_MIN_PX on screen however far the field is scaled down, so on a small field they are
  // drawn bigger and cut shorter. Their text is drawn at the resolution it shows at, which is only redone here
  sizeNames(scale) {
    const grow = Math.max(1, NAME_MIN_PX / (NAME_FONT * scale));
    const resolution = Math.max(1, Math.ceil(this.app.renderer.resolution * scale * grow));
    this.nameSize = [grow, resolution, scale < SMALL_FIELD ? NAME_MAX_SMALL : NAME_MAX];
    for (const tank of this.tanks.values()) {
      tank.sizeName(...this.nameSize);
    }
    this.publishNames();
  }

  // Names that would touch go up a row, and none is left half outside the field, where its mask would cut it. A label's
  // y is its bottom edge
  stackNames() {
    const tanks = [...this.tanks.values()].filter((tank) => tank.label.visible);
    const boxes = tanks.map(({ label: { x, y, width, height } }) => ({ x, y: y - height, width, height }));
    const placed = layoutNames(boxes);
    tanks.forEach((tank, index) => tank.placeName(placed[index]));
    this.publishTicks();
  }

  // The seats whose names are raised on a line to their tank, for the page's tests
  publishTicks() {
    const shown = JSON.stringify([...this.tanks.values()].filter((tank) => tank.tick.visible).map((tank) => tank.seat));
    if (shown !== this.shownTicks) {
      this.shownTicks = shown;
      this.app.canvas.dataset.ticks = shown;
    }
  }

  // The name each seat's tank shows, for the page's tests: the scene is drawn, so there is no text to read
  publishNames() {
    const shown = JSON.stringify(Object.fromEntries([...this.tanks].map(([seat, tank]) => [seat, tank.label.text])));
    if (shown !== this.shownNames) {
      this.shownNames = shown;
      this.app.canvas.dataset.names = shown;
    }
  }

  // Presses on the field reach the page in field pixels
  listen() {
    const stage = this.app.stage;
    stage.eventMode = "static";
    stage.hitArea = this.app.screen;
    const send = (kind) => (event) => {
      const point = this.world.toLocal(event.global);
      this.onPointer(kind, point.x, point.y);
    };
    stage.on("pointerdown", send("down"));
    stage.on("pointermove", send("move"));
    stage.on("pointerup", send("up"));
    stage.on("pointerupoutside", send("up"));
  }
}

async function loadArt() {
  const resp = await fetch("art/art.json");
  const info = await resp.json();
  // Pictures have a size; the other entries are the blast animations and where the backgrounds go
  const sprites = Object.fromEntries(Object.entries(info).filter(([, value]) => value.w !== undefined));
  const names = Object.keys(sprites);
  // Drawn at several times their size, so they stay sharp when the field is scaled up. The big backgrounds less so
  const textures = await Promise.all(
    names.map((name) => Assets.load({ src: `art/${name}.svg`, data: { resolution: name.startsWith("land") ? 2 : 4 } })),
  );
  const byName = Object.fromEntries(names.map((name, i) => [name, textures[i]]));
  return { info: sprites, blasts: info.blasts, at: info.at, texture: (name) => byName[name] };
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
  // The field's box changes size without the window changing, when the turn's controls come and go
  new ResizeObserver(() => app.resize()).observe(host);
  return new Scene(app, await loadArt());
}
