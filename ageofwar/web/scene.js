// The battlefield: the original's art played by flash.js, placed from the bot's updates. The page draws a few frames
// behind the newest update on a steady battle clock, sliding units and shots between updates, and steps every
// animation on that same clock, so legs and positions move together like the original's one step per frame.
import {
  Application,
  Container,
  Graphics,
  Rectangle,
  Text,
  Texture,
} from "./vendor/pixi.min.mjs";
import { Library } from "./flash.js";
import { Particles } from "./particles.js";

export const FPS = 40;
const FRAME_MS = 1000 / FPS;
// Updates come every second frame. The drawing stays behind the earliest an update could arrive by the gap to the next
// update, a margin, and how unevenly updates have been arriving, kept between these
const UPDATE_GAP = 2;
const MARGIN = 2;
const MIN_DELAY = 4;
const MAX_DELAY = 12;
// How many recent updates that unevenness is judged on: two seconds of them
const LATENESS_WINDOW = 40;
// The battle clock runs up to a tenth faster or slower to keep its delay. It never goes back, and only jumps ahead
// when this many frames behind (the page was hidden, say)
const STEER = 0.05;
const MIN_RATE = 0.9;
const MAX_RATE = 1.1;
const JUMP_FRAMES = 20;
// An update this many frames later than any recent one means the battle stood still: a pause, or the bot froze
const RESTART_FRAMES = 10;
// After a jump, only this many of the skipped frames are stepped
const MAX_STEPS = 8;
export const FIELD = { width: 1000, height: 450, ground: 425 };
// The original's view was 650 wide, so the field always scrolled. A wide window may cut off the top of the sky, at
// most down to this height, rather than show more of the field
const VIEW_WIDTH = 650;
const MIN_VIEW_HEIGHT = 390;
// The original only scrolled with the mouse below its 120 tall menu
const MENU_HEIGHT = 120;
// The biggest pointer picture browsers take, in pixels
const POINTER_MOST = 128;
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

// Which of an animation's random swings holds a frame: the last one starting at or before it
function branch(starts, frame) {
  let found = null;
  for (const start of starts) {
    if (start <= frame && (found === null || start > found)) {
      found = start;
    }
  }
  return found;
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
    // How late each recent update arrived, in milliseconds past where its frame would sit on a steady clock
    this.lateness = [];
    // The battle clock: the frame being drawn, with a fraction between updates. Null until the first update
    this.clock = null;
    // Holding the clock still while its delay builds up again after the battle stood still
    this.waiting = false;
    // The last whole frame the field's animations stepped to
    this.stepped = null;
    this.applied = 0;
    this.carry = 0;
    // The player's orders the bot hasn't counted yet (hud.js), shown on their own base right away
    this.orders = null;
    this.scale = 1;
    // Where the field's top sits on the screen, before any shake
    this.groundY = 0;
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
    // Which picture the page's pointer shows during a battle, so it is only drawn again when that changes
    this.pointerKey = null;
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
      // Where each of those sits in the original, before fit() moves them under the menu
      barY: bars.map((bar) => (bar ? bar.y : 0)),
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
        // The page's own pointer (the original's arrow) shows over the spots too
        button.cursor = "inherit";
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

  // view is the side's part of an update, and next the same from the update after it, for the turrets' aim. The
  // player's own base also shows the orders they just gave
  showBase(base, view, next = null, f = null) {
    if (base.side === this.mySide && this.orders) {
      view = this.orders.apply(view);
      next = this.orders.apply(next);
    }
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
      this.camera.edge = 0;
      for (const base of Object.values(this.bases)) {
        this.showBase(base, [0, 0, 1, 0, 500, 500, 0, 0, [0, 0, 0, 0, 0], 0, [0, 0, 0, 0], false]);
      }
    }
  }

  // ---------- Updates from the bot ----------

  reset(frame) {
    this.frames = frame ? [frame] : [];
    this.lateness = frame ? [performance.now() - frame.f * FRAME_MS] : [];
    this.clock = null;
    this.waiting = false;
    this.stepped = null;
    this.applied = 0;
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
    const late = performance.now() - frame.f * FRAME_MS;
    if (this.lateness.length && late > Math.max(...this.lateness) + RESTART_FRAMES * FRAME_MS) {
      // The battle stood still for a while: judge the delay afresh, and hold the clock until it has built up again
      this.lateness = [];
      this.waiting = this.clock !== null;
    }
    this.lateness.push(late);
    if (this.lateness.length > LATENESS_WINDOW) {
      this.lateness.shift();
    }
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
    this.reset(null);
    this.shake = 0;
  }

  // Move the battle clock on by the time since the last drawing. It aims a few frames behind the newest update, by
  // how unevenly updates have been arriving, and steers toward that gently rather than jumping back and forth
  moveClock(deltaMS, now) {
    const base = Math.min(...this.lateness);
    const spread = (Math.max(...this.lateness) - base) / FRAME_MS;
    const delay = Math.max(MIN_DELAY, Math.min(MAX_DELAY, UPDATE_GAP + MARGIN + spread));
    const target = (now - base) / FRAME_MS - delay;
    if (this.clock === null || target - this.clock > JUMP_FRAMES) {
      this.clock = target;
      this.waiting = false;
    } else if (this.waiting) {
      this.waiting = target < this.clock;
    } else {
      const rate = Math.max(MIN_RATE, Math.min(MAX_RATE, 1 + (target - this.clock) * STEER));
      this.clock += (Math.min(deltaMS, 250) / FRAME_MS) * rate;
    }
    // With nothing newer to show, the battle holds still at the newest update instead of guessing ahead
    this.clock = Math.min(this.clock, this.frames[this.frames.length - 1].f);
  }

  // The update just at or before the clock, the one after it, and how far between them
  sample(clock) {
    const frames = this.frames;
    const index = frames.findIndex((frame) => frame.f > clock);
    if (index === -1) {
      return { a: frames[frames.length - 1], b: null, t: 0 };
    }
    if (index === 0) {
      return { a: frames[0], b: null, t: 0 };
    }
    const a = frames[index - 1];
    const b = frames[index];
    return { a, b, t: (clock - a.f) / (b.f - a.f) };
  }

  // ---------- Drawing ----------

  draw(deltaMS) {
    this.fit();
    if (this.frames.length) {
      this.moveClock(deltaMS, performance.now());
      this.stepTo(Math.floor(this.clock));
      const sample = this.sample(this.clock);
      this.catchUp(sample.a);
      this.place(sample);
    }
    // The background and the cursor keep the original's 40 frames a second on their own, battle or not
    this.carry += Math.min(deltaMS, 250);
    while (this.carry >= FRAME_MS) {
      this.carry -= FRAME_MS;
      this.bg.advance();
      this.cursor?.advance();
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

  // Step the field's animations once for each whole frame the clock has passed. A clock standing still (a pause,
  // or no updates) leaves the fighters, shots and bits standing still too, as in the original's pause
  stepTo(whole) {
    if (this.stepped === null || whole < this.stepped) {
      this.stepped = whole;
      return;
    }
    this.stepped = Math.max(this.stepped, whole - MAX_STEPS);
    while (this.stepped < whole) {
      this.stepped += 1;
      this.tick(this.stepped);
    }
  }

  // One frame of the battle clock. Units then take the bot's own animation frame from this frame's update, if
  // there is one, so the page's animations can't wander from the bot's
  tick(frame) {
    for (const unit of this.units.values()) {
      this.stepUnit(unit, frame);
    }
    const update = this.frames.find((candidate) => candidate.f === frame);
    for (const view of update ? update.u : []) {
      const unit = this.units.get(view[0]);
      if (unit) {
        this.setState(unit, STATES[view[4]], view[5]);
      }
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

  stepUnit(unit, frame) {
    // A random swing picks what the bot picked, seen in an update the page already holds
    this.lib.choose = (starts) => this.botSwing(unit, frame, starts);
    unit.node.advance();
    this.lib.choose = null;
  }

  // The swing the bot picked for a unit's animation at this frame: the one holding its frame in the next update
  botSwing(unit, frame, starts) {
    for (const update of this.frames) {
      if (update.f < frame) {
        continue;
      }
      const view = update.u.find((candidate) => candidate[0] === unit.uid);
      return view && STATES[view[4]] === unit.state ? branch(starts, view[5]) : null;
    }
    return null;
  }

  place({ a, b, t }) {
    // Orders the drawn update already counts show from the bot's own numbers now
    if (this.mySide && this.orders) {
      this.orders.drop(a.s[this.mySide - 1][12]);
    }
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
        this.setState(unit, STATES[stateIndex], frame);
        // The clock may already have stepped past this update: the new unit catches up
        for (let step = a.f + 1; step <= this.stepped; step += 1) {
          this.stepUnit(unit, step);
        }
      }
      const next = later.get(uid);
      unit.node.x = next ? lerp(x10, next[3], t) / 10 : x10 / 10;
      unit.health = health;
      unit.aura.visible = healing[side - 1] && unit.state !== "die";
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
    // A new clip waits a frame before stepping its parts. The bot's timing only has the animation itself, so the
    // layers holding it step their parts straight away
    for (const layer of [node, holder, holder.child("anims")]) {
      if (layer) {
        layer.fresh = false;
      }
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

  // The unit shows the bot's state and animation frame. A new state starts its animation on the bot's frame (and
  // its swing, if it picks one). Otherwise the page only moves to the bot's frame when its own stepping ended up
  // elsewhere, so each frame's sound plays once
  setState(unit, state, frame) {
    const anims = unit.holder.child("anims");
    if (!anims) {
      return;
    }
    let anim = inner(anims);
    if (state !== unit.state) {
      unit.state = state;
      this.lib.choose = (starts) => branch(starts, frame);
      anims.gotoAndStop(state);
      this.lib.choose = null;
      anim = inner(anims);
      if (anim) {
        // The bot's frame already counts the first frame's wait
        anim.fresh = false;
      }
      if (state === "die") {
        unit.bar.visible = false;
      }
    }
    if (anim && anim.frame !== frame) {
      anim.playing = true;
      anim.enter(frame);
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
    this.updatePointer();
  }

  // The original hides the computer's pointer in a battle and draws its own arrow, with a sell sign while selling.
  // The page turns that into a pointer picture at the field's zoom (a CSS cursor, so it never lags), which the
  // stylesheet uses while a battle is on. The turret being placed is drawn on the field as before
  updatePointer() {
    const kind = this.mode.kind === "sell" ? "sell" : "arrow";
    const zoom = Math.max(1, Math.round(this.scale * 4) / 4);
    const key = `${kind}:${zoom}`;
    if (key === this.pointerKey) {
      return;
    }
    this.pointerKey = key;
    const prepare = (clip) => {
      for (const [name, on] of [
        ["tu", false],
        ["se", kind === "sell"],
      ]) {
        const part = clip.child(name);
        if (part) {
          part.visible = on;
        }
      }
    };
    const id = this.lib.exported("cursor");
    let picture = this.picture(id, null, zoom, prepare);
    // Browsers ignore pointer pictures bigger than 128 pixels
    const most = POINTER_MOST / Math.max(picture.width, picture.height);
    const fitted = Math.min(zoom, most);
    if (fitted < zoom) {
      picture = this.picture(id, null, fitted, prepare);
    }
    const hotX = Math.max(0, Math.round(-picture.x * fitted));
    const hotY = Math.max(0, Math.round(-picture.y * fitted));
    document.documentElement.style.setProperty("--battle-cursor", `url(${picture.url}) ${hotX} ${hotY}, auto`);
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
      this.cursor.visible = false;
    });
    // Edge scrolling follows the mouse over the whole page, menus included. When the mouse leaves the page no more
    // moves come, so it keeps its last speed, as the original kept the last mouse position
    window.addEventListener("pointermove", (event) => this.edgeScroll(event));
  }

  edgeScroll(event) {
    if (event.pointerType !== "mouse" || document.querySelector("dialog[open]")) {
      this.camera.edge = 0;
      return;
    }
    const box = this.app.canvas.getBoundingClientRect();
    const x = event.clientX - box.left;
    const point = this.world.toLocal({ x, y: event.clientY - box.top });
    if (point.y <= MENU_HEIGHT) {
      this.camera.edge = 0;
      return;
    }
    // The original scrolled when the mouse was within 100 of its 650 wide view's edges
    const edge = 100 * this.scale;
    this.camera.edge = x < edge ? -(edge - x) / edge : x > box.width - edge ? (x - (box.width - edge)) / edge : 0;
    this.camera.edge = Math.max(-1, Math.min(1, this.camera.edge));
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
    this.groundY = height - FIELD.height * scale;
    this.sky.clear().rect(0, 0, width, height).fill(SKY);
    // A wide window cuts off some of the original's sky, where its menu sat with the bases' health bars just under
    // it. The bars move down by what was cut, so on screen they still sit just under the full-size menu
    const cut = Math.max(0, FIELD.height - height / scale);
    for (const base of Object.values(this.bases)) {
      base.bars.forEach((bar, index) => {
        if (bar) {
          bar.y = base.barY[index] + cut;
        }
      });
    }
    this.lookAt(this.camera.x);
    this.updatePointer();
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
    let lift = 0;
    // The original's specials shook the field both ways
    if (this.shake && !reducedMotion.matches) {
      offset += (Math.random() * 2 - 1) * this.shake * this.scale;
      lift = (Math.random() * 2 - 1) * this.shake * this.scale;
    }
    this.world.x = offset;
    this.world.y = this.groundY + lift;
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

// A file's contents, telling onPart how much of it has come so far (0 to 1). A server that doesn't say the size, or
// sends it packed, only gets a 1 at the end
async function download(url, onPart) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`${url}: ${resp.status}`);
  }
  const size = resp.headers.has("Content-Encoding") ? 0 : Number(resp.headers.get("Content-Length"));
  if (!size || !resp.body) {
    const blob = await resp.blob();
    onPart(1);
    return blob;
  }
  const reader = resp.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    chunks.push(value);
    got += value.length;
    onPart(Math.min(got / size, 1));
  }
  onPart(1);
  return new Blob(chunks, { type: resp.headers.get("Content-Type") || "" });
}

// onProgress hears how much of the art has loaded, 0 to 1: the timelines are the first half, the atlas pages the rest
export async function createScene(host, onProgress) {
  const data = JSON.parse(await (await download("art/flash.json", (part) => onProgress(part / 2))).text());
  const parts = data.atlas.pages.map(() => 0);
  const pages = await Promise.all(
    data.atlas.pages.map(async (page, index) => {
      const blob = await download(`art/${page}`, (part) => {
        parts[index] = part;
        onProgress(0.5 + parts.reduce((sum, done) => sum + done, 0) / parts.length / 2);
      });
      // Decoded as Pixi decodes the files it loads itself: it puts the colors over the see-through parts on upload
      return Texture.from(await createImageBitmap(blob, { premultiplyAlpha: "none" }));
    }),
  );
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
