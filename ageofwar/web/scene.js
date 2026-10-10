// The battlefield: the original's art played by flash.js, placed from the bot's updates. The page draws about two
// updates behind the newest, sliding units and shots between updates, and steps every animation 40 times a second
// like the original did.
import {
  Application,
  Assets,
  Container,
  Graphics,
  Rectangle,
  Text,
} from "./vendor/pixi.min.mjs";
import { Library } from "./flash.js";
import { Particles } from "./particles.js";

export const FPS = 40;
const FRAME_MS = 1000 / FPS;
// Updates come every second frame. Drawing stays this many frames behind the newest, so one late update doesn't stall
const BUFFER_FRAMES = 4;
// Drawn this far past the newest update, the battle is taken as stopped (paused, or waiting for a player)
const STALL_FRAMES = 8;
// How fast the drawing's delay shrinks back after a late update, in milliseconds per update
const OFFSET_DRIFT = 2;
export const FIELD = { width: 1000, height: 450, ground: 425 };
// The original's view was 650 wide, so the field always scrolled. A wide window may cut off the top of the sky, at
// most down to this height, rather than show more of the field
const VIEW_WIDTH = 650;
const MIN_VIEW_HEIGHT = 390;
// The original only scrolled with the mouse below its 120 tall menu
const MENU_HEIGHT = 120;
const SKY = 0x3db2ff;
const STATES = ["idle", "walk", "attack", "die", "shoot", "shootwalk"];
const SHOT_KINDS = [
  "bullet1",
  "bullet2",
  "bullet3",
  "bullet4",
  "bullet5",
  "bullet6",
  "bullet7",
  "bullet8",
  "bullet9",
  "bullet10",
  "bullet11",
  "bullet12",
  "bulletspecial1",
  "bulletspecial2",
  "bulletspecial4",
  "bulletspecial5",
  "part5",
  "part8",
  "part11",
];
// Where each turret spot hangs on a base, from the base's position (the left base; the right one is mirrored)
const SPOT_X = 52;
const SPOT_Y = [-80, -125, -172, -220];
// The spot buttons on the left base, which the right base lacks in the original
const SPOT_BUTTONS = { build: [38, 39, 40, 41], sell: [42, 43, 44, 45] };
const SPOT_BUTTON_AT = [
  [54.0, -78.8],
  [54.2, -125.0],
  [54.2, -172.0],
  [54.2, -219.0],
];
// The specials that shake the field while they last, and by how much (the original's random jiggle)
const SHAKE = { 1: 5, 2: 2, 4: 1, 5: 1 };
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpAngle(a, b, t) {
  let d = ((b - a + 540) % 360) - 180;
  return a + d * t;
}

// The only part a clip shows at its current frame, like a unit's animation inside its "anims" holder
function inner(clip) {
  for (const slot of clip.slots.values()) {
    return slot.node;
  }
  return null;
}

export class Scene {
  constructor(app, lib) {
    this.app = app;
    this.lib = lib;
    this.font = "AoW Arial, Arial, sans-serif";
    this.sky = new Graphics();
    this.sky.eventMode = "none";
    this.world = new Container();
    app.stage.addChild(this.sky, this.world);
    this.layers = {};
    for (const name of ["back", "bases", "units", "shots", "fx", "specials", "ui"]) {
      this.layers[name] = new Container();
      this.world.addChild(this.layers[name]);
    }
    // Only the spot buttons and the units answer the pointer. Pixi stops at the first picture under it, so anything
    // else drawn over a spot button would take its clicks: the turret shown under the pointer, a shot, some smoke
    for (const name of ["back", "shots", "fx", "specials", "ui"]) {
      this.layers[name].eventMode = "none";
    }
    this.bg = lib.makeExported("bg");
    this.layers.back.addChild(this.bg);
    this.bases = { 1: this.makeBase(1), 2: this.makeBase(2) };
    this.units = new Map();
    this.shots = new Map();
    this.specials = new Map();
    this.particles = new Particles(lib, this.layers.fx, this.font);
    this.frames = [];
    this.offset = 0;
    this.applied = 0;
    this.drawnAt = 0;
    this.carry = 0;
    this.scale = 1;
    this.view = { x: 0, width: FIELD.width, max: 0 };
    this.camera = { x: 0, keys: 0, edge: 0, drag: null };
    // Whether the last press dragged the field, so letting go over a spot button doesn't also press it
    this.dragged = false;
    // Where the pointer is on the screen, so the turret under it stays there while the field scrolls
    this.pointer = { x: 0, y: 0 };
    this.mySide = null;
    this.mode = { kind: "none", turret: 0 };
    this.shake = 0;
    this.hovered = null;
    // Called by the page: a spot button pressed ({ build: spot } or { sell: spot }), or the pointer over one
    this.onSpot = null;
    this.onSpotHover = null;
    // Called with the field's new scale whenever the window's size changes it
    this.onFit = null;
    this.size = { width: 0, height: 0 };
    this.cursor = null;
    this.setupPointer();
    app.ticker.add((ticker) => this.draw(ticker.deltaMS));
  }

  // ---------- Bases ----------

  makeBase(side) {
    const node = this.lib.makeExported(side === 1 ? "base_player" : "base_comp");
    node.position.set(side === 1 ? 0 : FIELD.width, FIELD.ground);
    for (const name of ["b1", "b2", "b3", "b4", "s1", "s2", "s3", "s4"]) {
      const button = node.child(name);
      if (button) {
        button.visible = false;
      }
    }
    // The original's base health number: red bold text above the bar
    const label = new Text({
      text: "500",
      style: { fontFamily: this.font, fontSize: 12, fill: 0xcc0000, fontWeight: "bold", align: side === 1 ? "left" : "right" },
    });
    label.position.set(side === 1 ? 19.6 : -105.4, -306);
    node.addChild(label);
    // The health bar, its frame and the number only show during a battle
    const bars = [label, node.child("hb")];
    for (const slot of node.slots.values()) {
      if (slot.node.charId === 29 || slot.node.charId === 32) {
        bars.push(slot.node);
      }
    }
    const base = {
      side,
      node,
      label,
      bars,
      turrets: [null, null, null, null],
      spots: this.makeSpots(node, side),
      age: 0,
      addons: -1,
    };
    this.layers.bases.addChild(node);
    this.showBase(base, [175, 0, 1, 0, 500, 500, 0, 0, [0, 0, 0, 0, 0], 0, [0, 0, 0, 0], false]);
    return base;
  }

  // Build and sell buttons for each turret spot, mirrored on the right base
  makeSpots(node, side) {
    const spots = { build: [], sell: [] };
    for (const kind of ["build", "sell"]) {
      SPOT_BUTTONS[kind].forEach((id, index) => {
        const button = this.lib.make(id);
        const [x, y] = SPOT_BUTTON_AT[index];
        button.position.set(side === 1 ? x : -x, y);
        if (side === 2) {
          button.scale.x = -1;
        }
        button.visible = false;
        button.eventMode = "static";
        button.cursor = "pointer";
        const spot = index + 1;
        button.on("pointerover", () => {
          button.show("o");
          this.onSpotHover?.(kind, spot);
        });
        button.on("pointerout", () => {
          button.show("u");
          this.onSpotHover?.(kind, null);
        });
        button.on("pointertap", () => {
          if (!this.dragged) {
            this.onSpot?.({ [kind]: spot });
          }
        });
        node.addChild(button);
        spots[kind].push(button);
      });
    }
    return spots;
  }

  // view is the side's part of an update, and next the same from the update after it, for the turrets' aim
  showBase(base, view, next = null, f = null) {
    const [, , age, addons, health, maxHealth, , , , , turrets] = view;
    const node = base.node;
    if (age !== base.age) {
      base.age = age;
      (node.child("base") || node.child("bu"))?.gotoAndStop(age);
      for (const name of ["e1", "e2", "e3"]) {
        node.child(name)?.gotoAndStop(age);
      }
    }
    if (addons !== base.addons) {
      base.addons = addons;
      ["e1", "e2", "e3"].forEach((name, index) => {
        const part = node.child(name);
        if (part) {
          part.visible = index < addons;
        }
      });
    }
    const bar = node.child("hb");
    if (bar) {
      bar.scale.y = Math.max(0, Math.min(1, health / maxHealth));
    }
    base.label.text = String(health);
    turrets.forEach((turret, index) => this.showTurret(base, index, turret, next ? next[10][index] : null, f));
  }

  showTurret(base, index, view, next, f) {
    const kind = view ? view[0] : 0;
    let turret = base.turrets[index];
    if (turret && turret.kind !== kind) {
      turret.node.destroy({ children: true });
      turret = base.turrets[index] = null;
    }
    if (!kind) {
      return;
    }
    if (!turret) {
      const node = this.lib.makeExported("turret");
      node.position.set(base.side === 1 ? SPOT_X : -SPOT_X, SPOT_Y[index]);
      const tu = node.child("tu");
      tu.gotoAndStop(kind);
      if (base.side === 2) {
        tu.scale.y = -1;
      }
      base.node.addChildAt(node, base.node.children.length - 9);
      turret = base.turrets[index] = { kind, node, tu, from: view[1], to: view[1], seen: null };
    }
    turret.from = view[1];
    turret.to = next && next[0] === kind ? next[1] : view[1];
    // The bot says how far through its firing animation the turret is: start it there, once per update, so a
    // battle standing still doesn't fire it over and over
    const anim = turret.tu.child("anim");
    if (anim && f !== turret.seen && view[2] > 1 && !anim.playing) {
      anim.gotoAndPlay(view[2]);
    }
    turret.seen = f;
  }

  // Battles show the bases' health. Between them the field is only scenery, like the original's menu screens
  setBattle(on) {
    for (const base of Object.values(this.bases)) {
      for (const bar of base.bars) {
        if (bar) {
          bar.visible = on;
        }
      }
    }
    if (!on) {
      this.clear();
      for (const base of Object.values(this.bases)) {
        this.showBase(base, [0, 0, 1, 0, 500, 500, 0, 0, [0, 0, 0, 0, 0], 0, [0, 0, 0, 0], false]);
      }
    }
  }

  // ---------- Updates from the bot ----------

  reset(frame) {
    this.frames = frame ? [frame] : [];
    this.applied = 0;
    if (frame) {
      this.offset = performance.now() - frame.f * FRAME_MS;
    }
  }

  push(frame) {
    const newest = this.frames[this.frames.length - 1];
    // A pause stops the clock, but the original's training carries on, so a paused update replaces the last one
    if (newest && frame.f === newest.f) {
      this.frames[this.frames.length - 1] = frame;
      return;
    }
    if (newest && frame.f < newest.f) {
      if (frame.f < newest.f - 40) {
        // A new battle started: its frames count from zero again
        this.clear();
        this.reset(frame);
      }
      return;
    }
    const arrival = performance.now() - frame.f * FRAME_MS;
    this.offset = this.frames.length ? Math.max(arrival, this.offset - OFFSET_DRIFT) : arrival;
    this.frames.push(frame);
    if (this.frames.length > 40) {
      this.frames.shift();
    }
  }

  clear() {
    for (const unit of this.units.values()) {
      unit.node.destroy({ children: true });
    }
    for (const node of [...this.shots.values(), ...this.specials.values()]) {
      node.destroy({ children: true });
    }
    this.units.clear();
    this.shots.clear();
    this.specials.clear();
    this.particles.clear();
    for (const base of Object.values(this.bases)) {
      for (const turret of base.turrets) {
        turret?.node.destroy({ children: true });
      }
      base.turrets = [null, null, null, null];
    }
    this.frames = [];
    this.applied = 0;
    this.shake = 0;
  }

  // The update just at or before the drawn moment, the one after it, and how far between them
  sample(now) {
    const frames = this.frames;
    if (!frames.length) {
      return null;
    }
    const at = (now - this.offset) / FRAME_MS - BUFFER_FRAMES;
    let index = frames.findIndex((frame) => frame.f > at);
    if (index === -1) {
      return { a: frames[frames.length - 1], b: null, t: 0, at };
    }
    if (index === 0) {
      return { a: frames[0], b: null, t: 0, at };
    }
    const a = frames[index - 1];
    const b = frames[index];
    return { a, b, t: (at - a.f) / (b.f - a.f), at };
  }

  // ---------- Drawing ----------

  draw(deltaMS) {
    this.fit();
    const now = performance.now();
    const sample = this.sample(now);
    let stopped = false;
    if (sample) {
      this.catchUp(sample.a);
      this.place(sample);
      stopped = sample.b === null && sample.at > sample.a.f + STALL_FRAMES;
    }
    // The original's animations run at 40 frames a second, whatever the screen's rate
    this.carry += Math.min(deltaMS, 250);
    while (this.carry >= FRAME_MS) {
      this.carry -= FRAME_MS;
      this.tick(stopped);
    }
    this.moveCamera(deltaMS);
  }

  // Effects from every update the drawn moment has passed, in order
  catchUp(a) {
    for (const frame of this.frames) {
      if (frame.f > this.applied && frame.f <= a.f) {
        for (const event of frame.e) {
          this.particles.spawn(event);
        }
      }
    }
    this.applied = Math.max(this.applied, a.f);
  }

  // While the battle stands still its fighters, shots and bits hold still too, as in the original's pause
  tick(stopped) {
    this.bg.advance();
    this.cursor?.advance();
    if (stopped) {
      return;
    }
    for (const unit of this.units.values()) {
      unit.node.advance();
    }
    for (const node of this.shots.values()) {
      node.advance?.();
    }
    for (const node of this.specials.values()) {
      node.advance?.();
    }
    for (const base of Object.values(this.bases)) {
      for (const turret of base.turrets) {
        turret?.node.advance();
      }
    }
    this.particles.step();
  }

  place({ a, b, t }) {
    this.placeUnits(a, b, t);
    this.placeShots(a, b, t);
    this.placeSpecials(a, b, t);
    for (const side of [1, 2]) {
      const base = this.bases[side];
      this.showBase(base, a.s[side - 1], b ? b.s[side - 1] : null, a.f);
      for (const turret of base.turrets) {
        if (turret) {
          turret.node.angle = lerpAngle(turret.from, turret.to, t);
        }
      }
    }
  }

  placeUnits(a, b, t) {
    const later = new Map((b ? b.u : []).map((unit) => [unit[0], unit]));
    const seen = new Set();
    const healing = [a.s[0][11], a.s[1][11]];
    for (const view of a.u) {
      const [uid, kind, side, x10, stateIndex, frame, health] = view;
      seen.add(uid);
      let unit = this.units.get(uid);
      if (!unit) {
        unit = this.makeUnit(uid, kind, side);
      }
      const next = later.get(uid);
      unit.node.x = next ? lerp(x10, next[3], t) / 10 : x10 / 10;
      this.setState(unit, STATES[stateIndex], frame);
      unit.health = health;
      unit.aura.visible = healing[side - 1] && STATES[stateIndex] !== "die";
      if (unit.bar.visible) {
        this.showHealth(unit);
      }
    }
    for (const [uid, unit] of this.units) {
      if (!seen.has(uid)) {
        unit.node.destroy({ children: true });
        this.units.delete(uid);
      }
    }
  }

  makeUnit(uid, kind, side) {
    const node = this.lib.makeExported("ennemy");
    node.position.set(0, FIELD.ground);
    node.child("hitzone")?.gotoAndStop(kind);
    const holder = node.child("units");
    holder.gotoAndStop(kind);
    if (side === 2) {
      holder.scale.x = -1;
    }
    const bar = node.child("hb");
    bar.visible = false;
    const aura = node.child("aura");
    aura.visible = false;
    const zone = node.child("hitzone");
    const box = zone ? zone.getLocalBounds() : new Rectangle(-16, -44, 32, 44);
    aura.width = box.width;
    // The original shows a unit's health bar while the pointer is over it, just above its hit box
    bar.y = box.y - 10;
    node.eventMode = "static";
    node.hitArea = new Rectangle(box.x, box.y, box.width, box.height);
    node.on("pointerover", () => this.hover(unit, true));
    node.on("pointerout", () => this.hover(unit, false));
    node.on("pointertap", (event) => {
      if (event.pointerType !== "mouse") {
        this.hover(unit, true);
        clearTimeout(unit.hide);
        unit.hide = setTimeout(() => this.hover(unit, false), 2000);
      }
    });
    const unit = { uid, kind, side, node, holder, bar, aura, state: "", health: 100, hide: null };
    this.layers.units.addChild(node);
    this.units.set(uid, unit);
    return unit;
  }

  hover(unit, on) {
    if (unit.node.destroyed) {
      return;
    }
    unit.bar.visible = on && unit.state !== "die";
    if (on) {
      this.showHealth(unit);
    }
  }

  showHealth(unit) {
    const fill = unit.bar.child("hb");
    if (fill) {
      fill.scale.x = unit.health / 100;
    }
  }

  // A new state starts its animation, at the frame the bot is on. Afterwards the page keeps the animation going
  // itself, and only jumps when it has drifted away from the bot's (a random second swing, say)
  setState(unit, state, frame) {
    const anims = unit.holder.child("anims");
    if (!anims) {
      return;
    }
    if (state !== unit.state) {
      unit.state = state;
      anims.gotoAndStop(state);
      const anim = inner(anims);
      if (anim && frame > 1) {
        anim.gotoAndPlay(frame);
      }
      if (state === "die") {
        unit.bar.visible = false;
      }
      return;
    }
    const anim = inner(anims);
    if (anim && anim.totalFrames > 1) {
      const n = anim.totalFrames;
      const drift = Math.abs(((anim.frame - frame + n + n / 2) % n) - n / 2);
      if (drift > 3 && anim.playing) {
        anim.gotoAndPlay(frame);
      }
    }
  }

  placeShots(a, b, t) {
    const later = new Map((b ? b.b : []).map((shot) => [shot[0], shot]));
    const seen = new Set();
    for (const [uid, code, x10, y10, rotation, scale] of a.b) {
      seen.add(uid);
      let node = this.shots.get(uid);
      if (!node) {
        node = this.lib.makeExported(SHOT_KINDS[code]);
        this.layers.shots.addChild(node);
        this.shots.set(uid, node);
      }
      const next = later.get(uid);
      node.position.set((next ? lerp(x10, next[2], t) : x10) / 10, (next ? lerp(y10, next[3], t) : y10) / 10);
      node.angle = next ? lerpAngle(rotation, next[4], t) : rotation;
      node.scale.set(scale / 100);
    }
    for (const [uid, node] of this.shots) {
      if (!seen.has(uid)) {
        node.destroy({ children: true });
        this.shots.delete(uid);
      }
    }
  }

  placeSpecials(a, b, t) {
    const later = new Map((b ? b.x : []).map((special) => [special[0], special]));
    const seen = new Set();
    this.shake = 0;
    for (const [uid, age, side, x10, y10] of a.x) {
      this.shake = Math.max(this.shake, SHAKE[age] || 0);
      if (age !== 4 && age !== 5) {
        continue;
      }
      seen.add(uid);
      let node = this.specials.get(uid);
      if (!node) {
        node = this.lib.makeExported(`special${age}`);
        if (side === 2) {
          node.scale.x = -1;
        }
        this.layers.specials.addChild(node);
        this.specials.set(uid, node);
      }
      const next = later.get(uid);
      node.position.set((next ? lerp(x10, next[3], t) : x10) / 10, (next ? lerp(y10, next[4], t) : y10) / 10);
    }
    for (const [uid, node] of this.specials) {
      if (!seen.has(uid)) {
        node.destroy({ children: true });
        this.specials.delete(uid);
      }
    }
  }

  // ---------- Turret spots and the cursor ----------

  // What the player's own base shows: "none", "place" (free spots for a new turret) or "sell" (their turrets)
  setMode(kind, turret = 0, view = null) {
    this.mode = { kind, turret };
    for (const side of [1, 2]) {
      const base = this.bases[side];
      const mine = side === this.mySide;
      base.spots.build.forEach((button, index) => {
        const free = view && index <= view[3] && !view[10][index];
        button.visible = mine && kind === "place" && Boolean(free);
      });
      base.spots.sell.forEach((button, index) => {
        button.visible = mine && kind === "sell" && Boolean(view && view[10][index]);
      });
    }
    if (this.cursor) {
      const tu = this.cursor.child("tu");
      if (tu) {
        tu.visible = kind === "place";
        if (kind === "place") {
          tu.gotoAndStop(turret);
        }
      }
    }
  }

  setupPointer() {
    const stage = this.app.stage;
    stage.eventMode = "static";
    stage.hitArea = this.app.screen;
    this.cursor = this.lib.makeExported("cursor");
    for (const child of this.cursor.children) {
      child.visible = false;
    }
    this.layers.ui.addChild(this.cursor);
    this.cursor.visible = false;
    stage.on("pointermove", (event) => {
      const mouse = event.pointerType === "mouse";
      this.pointer = { x: event.global.x, y: event.global.y };
      const point = this.world.toLocal(this.pointer);
      this.cursor.position.set(point.x, point.y);
      this.cursor.visible = mouse && this.mode.kind === "place";
      if (mouse && point.y > MENU_HEIGHT) {
        const x = event.global.x;
        const width = this.app.screen.width;
        // The original scrolled when the mouse was within 100 of its 650 wide view's edges
        const edge = 100 * this.scale;
        this.camera.edge = x < edge ? -(edge - x) / edge : x > width - edge ? (x - (width - edge)) / edge : 0;
      } else {
        this.camera.edge = 0;
      }
      if (this.camera.drag) {
        const drag = this.camera.drag;
        this.camera.x = drag.camera - (event.global.x - drag.x) / this.scale;
        drag.moved = drag.moved || Math.abs(event.global.x - drag.x) > 6;
      }
    });
    stage.on("pointerdown", (event) => {
      if (event.pointerType !== "mouse" || event.button === 0) {
        this.camera.drag = { x: event.global.x, camera: this.camera.x, moved: false };
      }
    });
    // Pixi tells the stage the pointer went up before it sends the tap, so the tap can see this
    const end = () => {
      this.dragged = Boolean(this.camera.drag?.moved);
      this.camera.drag = null;
    };
    stage.on("pointerup", end);
    stage.on("pointerupoutside", end);
    stage.on("pointerleave", () => {
      this.camera.edge = 0;
      this.cursor.visible = false;
    });
  }

  // ---------- The view ----------

  fit() {
    const { width, height } = this.app.screen;
    if (width === this.size.width && height === this.size.height) {
      return;
    }
    this.size = { width, height };
    const scale = Math.min(width / VIEW_WIDTH, height / MIN_VIEW_HEIGHT);
    this.scale = scale;
    this.world.scale.set(scale);
    const viewWidth = width / scale;
    this.view = { width: viewWidth, max: Math.max(0, FIELD.width - viewWidth) };
    // The field sits on the bottom edge. Any room above is more sky, where the menus go
    this.world.y = height - FIELD.height * scale;
    this.sky.clear().rect(0, 0, width, height).fill(SKY);
    this.lookAt(this.camera.x);
    this.onFit?.(scale);
  }

  // Start the view on a side's base
  focus(side) {
    this.camera.x = side === 2 ? this.view.max : 0;
    this.lookAt(this.camera.x);
  }

  moveCamera(deltaMS) {
    const frames = deltaMS / FRAME_MS;
    if (!this.camera.drag) {
      this.camera.x += (this.camera.keys * 12 + this.camera.edge * 10) * frames;
    }
    this.lookAt(this.camera.x);
    if (this.cursor.visible) {
      this.cursor.position.copyFrom(this.world.toLocal(this.pointer));
    }
  }

  lookAt(x) {
    this.camera.x = Math.max(0, Math.min(this.view.max, x));
    let offset = -this.camera.x * this.scale;
    if (this.view.width > FIELD.width) {
      offset = ((this.view.width - FIELD.width) / 2) * this.scale;
    }
    if (this.shake && !reducedMotion.matches) {
      offset += (Math.random() * 2 - 1) * this.shake * this.scale;
    }
    this.world.x = offset;
  }

  // ---------- Pictures for the page's own buttons ----------

  // Render one of the original's characters (a button in a state, a shape, a sprite after `prepare` sets it up) to a
  // picture the page can show, with where its corner sits from the character's own origin
  picture(id, state = "u", scale = 2, prepare = null) {
    const node = this.lib.make(id);
    if (state && node.show) {
      node.show(state);
    }
    prepare?.(node);
    const holder = new Container();
    holder.addChild(node);
    const bounds = holder.getLocalBounds();
    const canvas = this.app.renderer.extract.canvas({
      target: holder,
      resolution: scale,
      frame: new Rectangle(bounds.x, bounds.y, bounds.width, bounds.height),
    });
    const result = { url: canvas.toDataURL("image/png"), x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
    holder.destroy({ children: true });
    return result;
  }
}

export async function createScene(host) {
  const data = await (await fetch("art/flash.json")).json();
  const pages = await Promise.all(data.atlas.pages.map((page) => Assets.load(`art/${page}`)));
  // The original's labels draw once, so their font has to be ready before the first one is made
  try {
    await document.fonts.load('bold 19px "AoW Arial"');
  } catch (e) {
    console.warn("Age of War: couldn't load the game's font", e);
  }
  const lib = new Library(data, pages);
  const app = new Application();
  await app.init({
    resizeTo: host,
    background: SKY,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  host.appendChild(app.canvas);
  return new Scene(app, lib);
}
