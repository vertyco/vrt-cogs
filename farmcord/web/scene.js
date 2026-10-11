// FarmCord's world, drawn with PixiJS: one room at a time with its sky, ground and scenery for the season, rain or
// snow, and the farmer walking to whatever the player taps. Room views (plots, the Market, the farmhouse) draw their
// own things into this scene's layers and register what can be tapped.
import { Application, Assets, Container, Graphics, Sprite, TilingSprite } from "./vendor/pixi.min.mjs";
import { FIELD, HORIZON, ROOM, VIEW } from "./rooms.js";

// The colour above each season's sky picture, where the screen is taller than the room
const SKY_TOP = { spring: 0x3b80bb, summer: 0x206fb1, autumn: 0x2b6aed, winter: 0x0e97e8 };
// Around the farmhouse's inside picture
const INSIDE_COLOR = 0x3a2414;
// The smallest a room is drawn while its band still fits the screen's height. A narrow screen then shows part of the
// room and follows the farmer, so things stay big enough to tap
const MIN_SCALE = 0.55;
// Room pixels a second
const WALK_SPEED = 320;
// How far the farmer walks in from the edge of a room he enters, across and up or down
const WALK_IN = { across: 150, down: 40 };
// A press that moves further than this, in screen pixels, pans the room instead of tapping it
const DRAG_DISTANCE = 12;
// How quickly the view catches up with the farmer, per second
const FOLLOW = 5;
// A frame that took longer than this (a paused tab) moves things as if it took this long
const LONGEST_FRAME = 0.1;
// Each season's fence is a different FarmVille piece: how far apart the pieces stand along an edge, and how far below
// the middle of a piece's ground line its anchor sits
const FENCE = {
  spring: { run: 112, lift: 26 },
  summer: { run: 112, lift: 26 },
  autumn: { run: 128, lift: 28 },
  winter: { run: 116, lift: 22 },
};
const GATE_LIFT = 18;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

// Every picture in art/art.json, by its key
class Art {
  constructor(data, sheets, images) {
    this.data = data;
    this.images = images;
    this.textures = {};
    this.frames = {};
    data.sheets.forEach((info, index) => {
      const sheet = sheets[index];
      const folder = `art/${info.file.slice(0, info.file.lastIndexOf("/") + 1)}`;
      Object.assign(this.textures, sheet.textures);
      for (const [key, frame] of Object.entries(sheet.data.frames)) {
        this.frames[key] = { url: `${folder}${sheet.data.meta.image}`, size: sheet.data.meta.size, ...frame };
      }
    });
  }

  texture(key) {
    return this.textures[key];
  }

  // A scene piece's key: the farmhouse, market, pond, fence, trees and bushes change with the season
  scenery(name, season) {
    return this.data.seasonal_scenes.includes(name) ? `scene/${name}_${season}` : `scene/${name}`;
  }

  // Where a picture sits in its sheet, for showing it in the page's HTML: { url, size, frame, spriteSourceSize,
  // sourceSize }, in the sheet's own pixels
  frame(key) {
    return this.frames[key];
  }

  animation(key) {
    return this.data.animations[key];
  }
}

// The farmer: the plain base drawing with the worn outfit pieces over it, every layer on the same frame of one clip.
// FarmVille draws him facing right; facing left mirrors him
class Farmer {
  constructor(art) {
    this.art = art;
    this.node = new Container();
    const { anchor } = art.animation("farmer/base");
    this.layers = art.data.farmer.layers.map((layer) => {
      const sprite = new Sprite();
      sprite.anchor.set(anchor.x, anchor.y);
      this.node.addChild(sprite);
      return { layer, sprite };
    });
    this.outfit = {};
    this.clip = "stand_front";
    this.mirrored = false;
    this.time = 0;
    this.walk = null;
    this.onStep = () => {};
    this.draw();
  }

  get x() {
    return this.node.x;
  }

  get y() {
    return this.node.y;
  }

  // { hat, top, bottom }: outfit keys, or null for the plain look
  dress(outfit) {
    this.outfit = { ...outfit };
    this.draw();
  }

  place(x, y) {
    this.stop(false);
    this.moveTo(x, y);
  }

  moveTo(x, y) {
    this.node.position.set(x, y);
    this.node.zIndex = y;
  }

  // Resolves true once he gets there, or false when another walk or a room change cuts it short
  walkTo(x, y) {
    this.stop(false);
    if (reducedMotion.matches) {
      this.moveTo(x, y);
      return Promise.resolve(true);
    }
    return new Promise((resolve) => {
      this.walk = { x, y, resolve };
      this.face(x - this.x, y - this.y);
    });
  }

  stop(arrived) {
    const walk = this.walk;
    this.walk = null;
    this.clip = this.clip.endsWith("back") ? "stand_back" : "stand_front";
    if (walk) {
      walk.resolve(arrived);
    }
  }

  face(dx, dy) {
    if (Math.abs(dx) > 1) {
      this.mirrored = dx < 0;
    }
    this.clip = dy < -Math.abs(dx) * 0.3 ? "walk_back" : "walk_front";
    this.time = 0;
  }

  step(dt) {
    const before = this.stepsTaken();
    this.time += dt;
    if (this.walk) {
      this.move(dt);
      if (this.walk && this.stepsTaken() > before) {
        this.onStep();
      }
    }
    this.draw();
  }

  // Two steps a walk cycle
  stepsTaken() {
    const clip = this.art.animation("farmer/base").clips[this.clip];
    return Math.floor((this.time * clip.fps * 2) / clip.count);
  }

  move(dt) {
    const dx = this.walk.x - this.x;
    const dy = this.walk.y - this.y;
    const distance = Math.hypot(dx, dy);
    const reach = WALK_SPEED * dt;
    if (distance <= reach) {
      this.moveTo(this.walk.x, this.walk.y);
      this.stop(true);
      return;
    }
    this.moveTo(this.x + (dx / distance) * reach, this.y + (dy / distance) * reach);
  }

  draw() {
    const clip = this.art.animation("farmer/base").clips[this.clip];
    const frame = clip.start + (Math.floor(this.time * clip.fps) % clip.count);
    for (const { layer, sprite } of this.layers) {
      const piece = layer === "base" ? "base" : this.outfit[layer] && `${layer}/${this.outfit[layer]}`;
      sprite.visible = Boolean(piece);
      if (piece) {
        sprite.texture = this.art.texture(`farmer/${piece}/${frame}`);
      }
    }
    this.node.scale.x = this.mirrored ? -1 : 1;
  }
}

// Rain or snow falling over the whole screen, drawn in code, with the light dimmed a little on a rainy day
class Weather {
  constructor() {
    this.node = new Container();
    this.shade = new Graphics();
    this.drops = new Graphics();
    this.node.addChild(this.shade, this.drops);
    this.kind = "sun";
    this.particles = [];
    this.size = { width: 0, height: 0 };
  }

  set(kind) {
    if (kind !== this.kind) {
      this.kind = kind;
      this.size = { width: 0, height: 0 };
    }
  }

  // A fresh set of drops or flakes for the screen's size, scattered over it
  reseed(width, height) {
    this.size = { width, height };
    const area = width * height;
    const count = this.kind === "rain" ? area / 5500 : this.kind === "snow" ? area / 7000 : 0;
    this.particles = Array.from({ length: Math.round(reducedMotion.matches ? count / 3 : count) }, () =>
      this.particle(Math.random() * height),
    );
    this.shade.clear();
    if (this.kind !== "sun") {
      this.shade.rect(0, 0, width, height).fill({ color: this.kind === "rain" ? 0x1d2b3a : 0xffffff, alpha: 0.16 });
    }
  }

  particle(y) {
    const x = Math.random() * (this.size.width + 200);
    if (this.kind === "rain") {
      return { x, y, speed: 900 + Math.random() * 400, length: 14 + Math.random() * 12 };
    }
    return { x, y, speed: 40 + Math.random() * 50, radius: 1.5 + Math.random() * 2.5, phase: Math.random() * 6.3 };
  }

  step(dt, width, height) {
    if (width !== this.size.width || height !== this.size.height) {
      this.reseed(width, height);
    }
    const slow = reducedMotion.matches ? 0.35 : 1;
    this.drops.clear();
    if (this.kind === "sun") {
      return;
    }
    for (const drop of this.particles) {
      drop.y += drop.speed * dt * slow;
      drop.x -= (this.kind === "rain" ? drop.speed * 0.18 : Math.sin(drop.y / 40 + drop.phase) * 25) * dt * slow;
      if (drop.y > height + 30) {
        Object.assign(drop, this.particle(-30));
      }
      if (this.kind === "rain") {
        this.drops.moveTo(drop.x, drop.y).lineTo(drop.x + drop.length * 0.18, drop.y - drop.length);
      } else {
        this.drops.circle(drop.x, drop.y, drop.radius);
      }
    }
    if (this.kind === "rain") {
      this.drops.stroke({ width: 2, color: 0xdbe8ff, alpha: 0.55 });
    } else {
      // An edge, so flakes still show against snowy ground
      this.drops.fill({ color: 0xffffff, alpha: 0.95 }).stroke({ width: 1, color: 0x8aa4b8, alpha: 0.7 });
    }
  }
}

class Scene {
  constructor(app, art) {
    this.app = app;
    this.art = art;
    this.world = new Container();
    // Sky, ground, paths and the farmhouse's inside picture
    this.back = new Container();
    // Flat things lying on the ground, under everyone standing: soil spots
    this.floor = new Container();
    // Things standing on the ground: the ones lower on the screen are nearer, so they draw last
    this.things = new Container();
    this.things.sortableChildren = true;
    // Over everything in the room: labels, sparkles
    this.front = new Container();
    this.world.addChild(this.back, this.floor, this.things, this.front);
    this.weather = new Weather();
    app.stage.addChild(this.world, this.weather.node);
    this.farmer = new Farmer(art);
    this.room = null;
    // The season the room is drawn for, for views that draw seasonal pieces
    this.season = "summer";
    // The screen pixels the HUD and the tool bar cover at the top and bottom
    this.insets = { top: 0, bottom: 0 };
    // The room's x at the middle of the screen
    this.camera = { x: ROOM.width / 2, follow: true };
    this.targets = [];
    this.frameHandlers = [];
    this.press = null;
    this.onGround = () => {};
    this.bindPointer(app.canvas);
    app.ticker.add((ticker) => this.draw(Math.min(LONGEST_FRAME, ticker.deltaMS / 1000)));
    // Nothing moves while the page is hidden
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        app.ticker.stop();
      } else {
        app.ticker.start();
      }
    });
  }

  // ---------- Rooms ----------

  // Draws a room for a season and its weather ("sun", "rain" or "snow"), emptying what the last room drew
  show(room, season, sky) {
    this.room = room;
    this.season = season;
    this.farmer.stop(false);
    this.things.removeChild(this.farmer.node);
    for (const layer of [this.back, this.floor, this.things, this.front]) {
      layer.removeChildren().forEach((child) => child.destroy({ children: true }));
    }
    this.targets = [];
    this.frameHandlers = [];
    if (room.inside) {
      const picture = new Sprite(this.art.images["room/farmhouse_inside"]);
      const info = this.art.data.images["room/farmhouse_inside"];
      picture.setSize(info.w, info.h);
      this.back.addChild(picture);
    } else {
      this.drawOutside(room, season);
    }
    this.things.addChild(this.farmer.node);
    this.app.renderer.background.color = room.inside ? INSIDE_COLOR : SKY_TOP[season];
    this.weather.set(room.inside ? "sun" : sky);
  }

  drawOutside(room, season) {
    const sky = this.art.data.images[`sky/${season}`];
    // The sky's picture ends in hills that meet the ground, so only its sideways repeat lines up with the room
    const skyline = this.tiling(`sky/${season}`, -2000, HORIZON - sky.h, 5280, sky.h);
    skyline.tilePosition.y = 0;
    this.back.addChild(skyline);
    this.back.addChild(this.tiling(`ground/${season}`, -2000, HORIZON, 5280, 3000));
    for (const path of room.paths) {
      this.back.addChild(this.tiling("ground/path", path.x, path.y, path.w, path.h));
    }
    // A piece a view makes tappable carries a label to find it by
    for (const item of room.scenery) {
      const piece = this.sprite(this.art.scenery(item.art, season), item.x, item.y);
      piece.label = item.label || item.art;
      piece.scale.set(item.scale || 1);
      this.things.addChild(piece);
    }
    if (room.fence) {
      this.drawFence(room.fence.gate, season);
    }
  }

  // A repeating picture filling a box, lined up with the room so neighbouring boxes match
  tiling(key, x, y, width, height) {
    const info = this.art.data.images[key];
    const texture = this.art.images[key];
    const node = new TilingSprite({ texture, width, height });
    node.tileScale.set(info.w / texture.width, info.h / texture.height);
    node.position.set(x, y);
    node.tilePosition.set(-x, -y);
    return node;
  }

  // A picture standing at a point of the room. Sheet frames carry their own anchor, mostly their bottom middle
  sprite(key, x, y) {
    const node = new Sprite(this.art.texture(key));
    node.position.set(x, y);
    node.zIndex = y;
    return node;
  }

  // The plot's fence: pieces along the four edges of the field's diamond, with the gate on the side facing out
  drawFence(gate, season) {
    const { run, lift } = FENCE[season];
    const { x, y, fenceWidth, fenceHeight } = FIELD;
    const left = [x - fenceWidth / 2, y];
    const top = [x, y - fenceHeight / 2];
    const right = [x + fenceWidth / 2, y];
    const bottom = [x, y + fenceHeight / 2];
    // FarmVille's pieces run down to the right; the edges running up to the right mirror them
    const edges = {
      "back-left": [left, top, true],
      "back-right": [top, right, false],
      "front-left": [left, bottom, false],
      "front-right": [bottom, right, true],
    };
    for (const [name, [from, to, mirrored]] of Object.entries(edges)) {
      const count = Math.max(1, Math.round(Math.abs(to[0] - from[0]) / run));
      for (let i = 0; i < count; i += 1) {
        const t = (i + 0.5) / count;
        const isGate = name === gate && i === Math.floor(count / 2);
        const groundY = from[1] + (to[1] - from[1]) * t;
        const piece = this.sprite(isGate ? "scene/gate" : this.art.scenery("fence", season), 0, 0);
        piece.position.set(from[0] + (to[0] - from[0]) * t, groundY + (isGate ? GATE_LIFT : lift));
        piece.zIndex = groundY;
        piece.scale.x = mirrored ? -1 : 1;
        this.things.addChild(piece);
      }
    }
  }

  // The farmer comes in at the side of the room he walked in from (null: the middle of the room) and takes a few
  // steps in. A room can name where he stops instead (room.stops), when the usual place is in something's way. A plot
  // opens on its field, which a narrow screen can't show around a farmer at its side; once he walks the view follows
  // him again
  arrive(from) {
    const walk = this.room.walk;
    const middle = { x: (walk.left + walk.right) / 2, y: (walk.top + walk.bottom) / 2 };
    const starts = {
      left: [walk.left, middle.y, WALK_IN.across, 0],
      right: [walk.right, middle.y, -WALK_IN.across, 0],
      up: [middle.x, walk.top, 0, WALK_IN.down],
      down: [middle.x, walk.bottom, 0, -WALK_IN.down],
    };
    let [x, y, dx, dy] = starts[from] || [middle.x, walk.bottom - 60, 0, 0];
    const stop = this.room.stops?.[from];
    if (stop) {
      [x, y] = [stop.x - dx, stop.y - dy];
    }
    this.farmer.place(x, y);
    this.camera = this.room.fence ? { x: FIELD.x, follow: false } : { x, follow: true };
    if (dx || dy) {
      this.farmer.walkTo(x + dx, y + dy);
    }
  }

  // ---------- What views use ----------

  // Something in the room the player can tap. The farmer walks to walkTo ({x, y} in room pixels; by default just in
  // front of the node), then onTap runs. hit(point), with the point in room pixels, decides what counts as tapping
  // it; by default the node's picture box does. Returns a function that removes it again
  addTarget(node, { onTap, walkTo = null, hit = null }) {
    const target = { node, onTap, walkTo, hit };
    this.targets.push(target);
    return () => {
      this.targets = this.targets.filter((other) => other !== target);
    };
  }

  // Runs fn(dt) every frame until the room changes. Returns a function that stops it
  everyFrame(fn) {
    this.frameHandlers.push(fn);
    return () => {
      this.frameHandlers = this.frameHandlers.filter((other) => other !== fn);
    };
  }

  walkTo(x, y) {
    const walk = this.room.walk;
    this.camera.follow = true;
    return this.farmer.walkTo(clamp(x, walk.left, walk.right), clamp(y, walk.top, walk.bottom));
  }

  setInsets(top, bottom) {
    this.insets = { top, bottom };
  }

  // ---------- Tapping and panning ----------

  bindPointer(canvas) {
    canvas.addEventListener("pointerdown", (event) => {
      this.press = { id: event.pointerId, x: event.clientX, y: event.clientY, camera: this.camera.x, dragging: false };
    });
    canvas.addEventListener("pointermove", (event) => {
      const press = this.press;
      if (!press || press.id !== event.pointerId) {
        return;
      }
      const dx = event.clientX - press.x;
      if (!press.dragging && Math.hypot(dx, event.clientY - press.y) > DRAG_DISTANCE) {
        press.dragging = true;
      }
      if (press.dragging) {
        this.camera = { x: press.camera - dx / this.world.scale.x, follow: false };
      }
    });
    canvas.addEventListener("pointerup", (event) => {
      const press = this.press;
      this.press = null;
      if (press && press.id === event.pointerId && !press.dragging && this.room) {
        this.tap(event);
      }
    });
    canvas.addEventListener("pointercancel", () => {
      this.press = null;
    });
  }

  tap(event) {
    const box = this.app.canvas.getBoundingClientRect();
    const screen = { x: event.clientX - box.left, y: event.clientY - box.top };
    const point = this.world.toLocal(screen);
    const target = this.targetAt(screen, point);
    const goal = target ? target.walkTo || this.inFrontOf(target.node) : point;
    this.walkTo(goal.x, goal.y).then((arrived) => {
      if (!arrived) {
        return;
      }
      if (target) {
        target.onTap();
      } else {
        this.onGround(point);
      }
    });
  }

  // The nearest thing tapped, if any
  targetAt(screen, point) {
    const hits = this.targets.filter((target) => {
      if (target.node.destroyed || !target.node.visible) {
        return false;
      }
      return target.hit ? target.hit(point) : target.node.getBounds().rectangle.contains(screen.x, screen.y);
    });
    hits.sort((a, b) => b.node.zIndex - a.node.zIndex);
    return hits[0] || null;
  }

  inFrontOf(node) {
    const at = this.world.toLocal(node.getGlobalPosition());
    return { x: at.x, y: at.y + 12 };
  }

  // ---------- Every frame ----------

  draw(dt) {
    this.farmer.step(dt);
    for (const fn of this.frameHandlers) {
      fn(dt);
    }
    this.fit(dt);
    this.weather.step(dt, this.app.screen.width, this.app.screen.height);
  }

  // Fits the room's band between the HUD and the tool bar, as big as the screen's width allows, but never so small
  // that things are hard to tap. When the room is wider than the screen, the view follows the farmer
  fit(dt) {
    const { width, height } = this.app.screen;
    const view = this.room?.inside ? VIEW.inside : VIEW.outside;
    const band = view.bottom - view.top;
    const playHeight = Math.max(1, height - this.insets.top - this.insets.bottom);
    const contain = Math.min(width / ROOM.width, playHeight / band);
    const scale = Math.max(contain, Math.min(playHeight / band, MIN_SCALE));
    this.world.scale.set(scale);
    this.world.y = this.insets.top + (playHeight - band * scale) / 2 - view.top * scale;
    const half = width / scale / 2;
    if (half * 2 >= ROOM.width) {
      this.camera.x = ROOM.width / 2;
    } else {
      if (this.camera.follow) {
        this.camera.x += (this.farmer.x - this.camera.x) * Math.min(1, dt * FOLLOW);
      }
      this.camera.x = clamp(this.camera.x, half, ROOM.width - half);
    }
    this.world.x = width / 2 - this.camera.x * scale;
  }
}

async function loadArt() {
  const resp = await fetch("art/art.json");
  if (!resp.ok) {
    throw new Error(`The art list answered ${resp.status}`);
  }
  const data = await resp.json();
  const keys = Object.keys(data.images);
  const [sheets, images] = await Promise.all([
    Promise.all(data.sheets.map((sheet) => Assets.load(`art/${sheet.file}`))),
    Promise.all(keys.map((key) => Assets.load(`art/${data.images[key].file}`))),
  ]);
  return new Art(data, sheets, Object.fromEntries(keys.map((key, i) => [key, images[i]])));
}

export async function createScene(host) {
  const app = new Application();
  await app.init({
    resizeTo: host,
    background: SKY_TOP.summer,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  host.append(app.canvas);
  // resizeTo only follows the window, but the stage's box can change on its own too
  new ResizeObserver(() => app.resize()).observe(host);
  return new Scene(app, await loadArt());
}
