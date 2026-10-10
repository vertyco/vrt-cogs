// Tanks' field, drawn with PixiJS in the original's 550 x 400 pixels and scaled to fit the screen. Things stack
// as the original stacked them: the landscape, tanks, shells and blasts, then trees, then the ground in front.
import { Application, Assets, Container, Graphics, Sprite } from "./vendor/pixi.min.mjs";

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
// The original's tank colors, one per seat
const COLORS = [0xf02400, 0x00cc33, 0x0033ff, 0xf0df0f, 0xea9300];
const GROUND_COLORS = { 1: 0xffffff, 2: 0x78ab00, 3: 0xeaddb5 };
const SHIELD_ART = { 3: "shield_weak", 4: "shield", 5: "shield_strong", 6: "shield_super" };
// The teleport's frames: the beam starts at the tank, the tank vanishes, the beam moves to the spot, the tank
// appears there. Its first frame is the picking cursor
const TELEPORT_HIDE = 17;
const TELEPORT_MOVE = 35;
const TELEPORT_SHOW = 41;
// How quickly a tank slides to where the bot last put it
const FOLLOW_RATE = 15;
// Your own driving runs ahead of the bot by at most this many pixels
const MAX_LEAD = 4;

// An animation's frames, named prefix_01, prefix_02 and so on
function frameNames(art, prefix) {
  return Object.keys(art.info)
    .filter((name) => name.startsWith(`${prefix}_`) && /_\d+$/.test(name))
    .sort();
}

function place(art, name, x = 0, y = 0) {
  const node = new Sprite(art.texture(name));
  const info = art.info[name];
  node.anchor.set(info.ax / info.w, info.ay / info.h);
  node.position.set(x, y);
  return node;
}

// One tank: its shield and parachute behind it, its tracks, its body in the seat's color, and its barrel
class TankView {
  constructor(art, seat, layer) {
    this.root = new Container();
    this.shields = Object.fromEntries(Object.entries(SHIELD_ART).map(([kind, name]) => [kind, place(art, name)]));
    this.parachute = place(art, "parachute");
    this.body = new Container();
    const color = place(art, "tank_body");
    color.tint = COLORS[seat];
    this.body.addChild(place(art, "tank_tracks"), color);
    this.barrelFrames = frameNames(art, "barrel").map((name) => art.texture(name));
    this.barrel = place(art, "barrel_01");
    this.recoil = -1;
    this.root.addChild(...Object.values(this.shields), this.parachute, this.body, this.barrel);
    layer.addChild(this.root);
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

  draw(dt) {
    const view = this.view;
    this.root.visible = Boolean(view && view.alive && !this.hidden);
    if (!this.root.visible) {
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
    const frame = Math.floor(this.recoil);
    if (frame >= this.barrelFrames.length) {
      this.recoil = -1;
      this.barrel.texture = this.barrelFrames[0];
      return;
    }
    this.barrel.texture = this.barrelFrames[frame];
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
    for (const name of ["land", "tanks", "effects", "shells", "trees", "ground", "marks"]) {
      this.layers[name] = new Container();
      this.world.addChild(this.layers[name]);
    }
    this.ground = new Graphics();
    this.layers.ground.addChild(this.ground);
    this.landscape = null;
    this.tops = null;
    this.groundColor = GROUND_COLORS[1];
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
    this.target = place(art, "teleport_01");
    this.layers.marks.addChild(this.aimLine, this.cursor, this.target);
    this.cursor.visible = false;
    this.target.visible = false;
    this.size = { width: 0, height: 0 };
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
      this.tanks.set(seat, new TankView(this.art, seat, this.layers.tanks));
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

  // The shell's explosion: the fireball grows, then a glow fades out
  blast(x, y, key, rotation) {
    const { scale, frames } = this.art.blasts[BLAST_ART[key]];
    const node = new Container();
    node.position.set(x, y);
    node.scale.set(scale[0], scale[1]);
    const sprites = {};
    this.layers.shells.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, frames.length, (root, index) => {
        const frame = frames[index];
        root.children.forEach((child) => {
          child.visible = false;
        });
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

  die(seat, x, y) {
    this.tanks.get(seat).view = null;
    this.animate("tank_boom", x, y, this.layers.tanks);
    this.onEvent("die", seat);
  }

  beam(seat, x0, y0, x1, y1) {
    const names = frameNames(this.art, "teleport").slice(1);
    const tank = this.tank(seat);
    const node = place(this.art, names[0], x0, y0);
    this.layers.effects.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, names.length, (sprite, index) => {
        // Frame 2 of the original is the first one played
        const frame = index + 2;
        sprite.texture = this.art.texture(names[index]);
        sprite.position.set(frame >= TELEPORT_MOVE ? x1 : x0, frame >= TELEPORT_MOVE ? y1 : y0);
        tank.hidden = frame >= TELEPORT_HIDE && frame < TELEPORT_SHOW;
      }),
    );
  }

  // The arrow over the tank whose turn it is
  blink(view) {
    this.animate("blink", view.x, view.y - 10, this.layers.effects);
  }

  animate(prefix, x, y, layer) {
    const names = frameNames(this.art, prefix);
    const node = place(this.art, names[0], x, y);
    layer.addChild(node);
    this.flipbooks.push(
      new Flipbook(node, names.length, (sprite, frame) => {
        sprite.texture = this.art.texture(names[frame]);
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
    this.drawAimLine();
    this.flipbooks = this.flipbooks.filter((book) => book.step(dt));
  }

  // The ground as one shape: a step for each column, from its top down past the bottom of the field
  drawGround() {
    this.groundDirty = false;
    const points = [0, HEIGHT + 1];
    this.tops.forEach((top, column) => {
      const y = Math.min(HEIGHT + 1, top);
      points.push(column, y, column + 1, y);
    });
    points.push(WIDTH, HEIGHT + 1);
    this.ground.clear().poly(points).fill(this.groundColor);
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
