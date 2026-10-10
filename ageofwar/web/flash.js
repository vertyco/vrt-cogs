// Plays the original Flash timelines with PixiJS: shapes come from the art pages, and each sprite steps through its
// frames 40 times a second like the Flash player did, placing, moving and removing its parts.
import { Container, Matrix, Rectangle, Sprite, Text, Texture } from "./vendor/pixi.min.mjs";

const IDENTITY = [1, 0, 0, 1, 0, 0];
// Where a line's letters sit above its baseline, as a share of the font size (Arial's ascent)
const ASCENT = 0.905;
// Static text is drawn sharper than the screen needs, so it stays crisp when the field is scaled up
const TEXT_RESOLUTION = 3;

// One frame's display list: depth -> { c: character, m: matrix, cx: color, pid: placement, n: name }
function buildFrames(def) {
  const lists = [];
  const current = new Map();
  let pid = 0;
  for (const ops of def.f) {
    for (const op of ops) {
      if (op.length === 1) {
        current.delete(op[0]);
        continue;
      }
      const [depth, char, matrix, color, move, name, clip] = op;
      const old = current.get(depth);
      if (char) {
        // A new character at this depth is a new object, even when it replaces one
        pid += 1;
        current.set(depth, {
          c: char,
          m: matrix || (move && old ? old.m : IDENTITY),
          cx: color || (move && old ? old.cx : 0),
          pid,
          n: name || (move && old ? old.n : ""),
          clip: clip || 0,
        });
      } else if (old) {
        current.set(depth, {
          ...old,
          m: matrix || old.m,
          cx: color || old.cx,
          n: name || old.n,
        });
      }
    }
    lists.push([...current.entries()].sort((a, b) => a[0] - b[0]).map(([d, e]) => ({ d, ...e })));
  }
  return lists;
}

function applyColor(node, cx) {
  if (!cx) {
    node.alpha = 1;
    node.tint = 0xffffff;
    return;
  }
  const mult = cx.mult || [256, 256, 256, 256];
  const add = cx.add || [0, 0, 0, 0];
  node.alpha = Math.max(0, Math.min(1, mult[3] / 256 + add[3] / 255));
  const channel = (i) => Math.max(0, Math.min(255, Math.round((mult[i] / 256) * 255 + add[i])));
  node.tint = (channel(0) << 16) | (channel(1) << 8) | channel(2);
}

function setMatrix(node, m, scale = 1) {
  node.setFromMatrix(new Matrix(m[0] * scale, m[1] * scale, m[2] * scale, m[3] * scale, m[4], m[5]));
}

export class Library {
  // data: flash.json, pages: the atlas page textures in order
  constructor(data, pages) {
    this.data = data;
    this.scale = data.atlas.scale;
    this.pieces = new Map();
    for (const [id, list] of Object.entries(data.atlas.shapes)) {
      this.pieces.set(
        Number(id),
        list.map(([page, x, y, w, h, left, top]) => ({
          texture: new Texture({ source: pages[page].source, frame: new Rectangle(x, y, w, h) }),
          left: left / this.scale,
          top: top / this.scale,
        })),
      );
    }
    this.frameCache = new Map();
    this.random = Math.random;
    // Called with a sound id when a timeline reaches a frame that starts one
    this.onSound = null;
  }

  frames(id) {
    let lists = this.frameCache.get(id);
    if (!lists) {
      lists = buildFrames(this.data.sprites[id]);
      this.frameCache.set(id, lists);
    }
    return lists;
  }

  exported(name) {
    return this.data.exports[name];
  }

  // A new display object for a character: a Clip for a sprite, a Shape, a Button, a Label, or an empty spot for
  // a text field the page fills itself
  make(id) {
    if (this.data.sprites[id]) {
      return new Clip(this, id);
    }
    if (this.pieces.has(id)) {
      return new Shape(this, id);
    }
    if (this.data.buttons[id]) {
      return new Button(this, id);
    }
    if (this.data.labels[id]) {
      return new Label(this.data.labels[id]);
    }
    const node = new Container();
    node.textVariable = this.data.texts[id] ?? null;
    return node;
  }

  makeExported(name) {
    return this.make(this.exported(name));
  }
}

// The original's fixed text, such as the "CANCEL" on the cancel button: one line per text record
class Label extends Container {
  constructor(lines) {
    super();
    for (const [words, font, bold, size, color, x, baseline] of lines) {
      const text = new Text({
        text: words,
        style: { fontFamily: font, fontSize: size, fontWeight: bold ? "bold" : "normal", fill: color },
        resolution: TEXT_RESOLUTION,
      });
      text.position.set(x, baseline - size * ASCENT);
      this.addChild(text);
    }
  }

  advance() {}
}

class Shape extends Container {
  constructor(lib, id) {
    super();
    this.charId = id;
    for (const piece of lib.pieces.get(id)) {
      const sprite = new Sprite(piece.texture);
      sprite.position.set(piece.left, piece.top);
      sprite.scale.set(1 / lib.scale);
      this.addChild(sprite);
    }
  }

  advance() {}
}

export class Button extends Container {
  constructor(lib, id) {
    super();
    this.charId = id;
    this.lib = lib;
    this.records = lib.data.buttons[id];
    this.state = "u";
    this.show("u");
  }

  show(state) {
    this.state = state;
    for (const child of this.removeChildren()) {
      child.destroy({ children: true });
    }
    for (const [char, , states, m, cx] of [...this.records].sort((a, b) => a[1] - b[1])) {
      if (!states.includes(state)) {
        continue;
      }
      const node = this.lib.make(char);
      setMatrix(node, m);
      applyColor(node, cx);
      this.addChild(node);
    }
  }

  advance() {
    for (const child of this.children) {
      child.advance?.();
    }
  }
}

export class Clip extends Container {
  constructor(lib, id) {
    super();
    this.lib = lib;
    this.charId = id;
    this.def = lib.data.sprites[id];
    this.lists = lib.frames(id);
    this.frame = 0;
    this.playing = true;
    this.removed = false;
    // depth -> { pid, node }
    this.slots = new Map();
    this.named = {};
    // Set on the tick this clip was made, so it shows frame 1 for a whole tick before moving on
    this.fresh = true;
    // Called with "hit", "rhit" or "shoot" when the timeline reaches one of the original's game hooks
    this.onHook = null;
    this.enter(1);
  }

  get totalFrames() {
    return this.def.n;
  }

  child(name) {
    return this.named[name] ?? null;
  }

  // Show a frame: keep the parts that carry on, make the new ones, drop the rest, then run its script and sound
  show(frame) {
    this.frame = frame;
    const list = this.lists[frame - 1];
    const keep = new Set();
    this.named = {};
    let index = 0;
    for (const entry of list) {
      keep.add(entry.d);
      let slot = this.slots.get(entry.d);
      if (!slot || slot.pid !== entry.pid) {
        if (slot) {
          slot.node.destroy({ children: true });
        }
        slot = { pid: entry.pid, node: this.lib.make(entry.c), m: null, cx: null };
        this.slots.set(entry.d, slot);
      }
      if (slot.m !== entry.m) {
        setMatrix(slot.node, entry.m);
        slot.m = entry.m;
      }
      if (slot.cx !== entry.cx) {
        applyColor(slot.node, entry.cx);
        slot.cx = entry.cx;
      }
      if (this.children[index] !== slot.node) {
        this.addChildAt(slot.node, index);
      }
      index += 1;
      if (entry.n) {
        this.named[entry.n] = slot.node;
      }
    }
    for (const [depth, slot] of [...this.slots]) {
      if (!keep.has(depth)) {
        slot.node.destroy({ children: true });
        this.slots.delete(depth);
      }
    }
    this.applyMasks(list);
  }

  // A mask entry hides everything outside its shape at the depths above it, up to its clip depth
  applyMasks(list) {
    let mask = null;
    for (const entry of list) {
      const node = this.slots.get(entry.d).node;
      if (entry.clip) {
        mask = { node, until: entry.clip };
        continue;
      }
      const masked = mask && entry.d <= mask.until;
      if (masked && node.mask !== mask.node) {
        node.mask = mask.node;
      } else if (!masked && node.mask) {
        node.mask = null;
      }
    }
  }

  // Arrive on a frame the way the player does: draw it, start its sound, then run its script
  enter(frame) {
    this.show(frame);
    const sound = this.def.a?.[frame];
    if (sound && this.lib.onSound) {
      this.lib.onSound(sound);
    }
    const actions = this.def.s?.[frame];
    if (actions) {
      for (const action of actions) {
        if (this.run(action)) {
          break;
        }
      }
    }
  }

  // Returns true when the action moved the playhead, which ends the frame's script
  run(action) {
    const [kind, a, b] = action;
    const pick = (from, to) => from + Math.floor(this.lib.random() * (to - from + 1));
    switch (kind) {
      case "stop":
        this.playing = false;
        return false;
      case "play":
        this.playing = true;
        this.enter(Math.max(1, a));
        return true;
      case "pick":
        this.playing = true;
        this.enter(a[Math.floor(this.lib.random() * a.length)]);
        return true;
      case "rstop":
        this.playing = false;
        this.show(pick(a, b));
        return true;
      case "rplay":
        this.playing = true;
        this.enter(Math.max(1, pick(a, b)));
        return true;
      case "remove":
        this.removed = true;
        this.playing = false;
        return true;
      default:
        this.onHook?.(kind);
        return false;
    }
  }

  label(name) {
    return this.def.l?.[name] ?? null;
  }

  // Flash's gotoAndStop: a jump to the frame already showing changes nothing
  gotoAndStop(target) {
    const frame = typeof target === "string" ? this.label(target) : target;
    this.playing = false;
    if (frame && frame !== this.frame) {
      this.enter(Math.min(frame, this.def.n));
      this.playing = false;
    }
  }

  gotoAndPlay(target) {
    const frame = typeof target === "string" ? this.label(target) : target;
    this.playing = true;
    if (frame) {
      this.enter(Math.min(frame, this.def.n));
    }
  }

  play() {
    this.playing = true;
  }

  stop() {
    this.playing = false;
  }

  // One tick of the 40 a second clock: this timeline steps, then every part that was already here steps
  advance() {
    if (this.fresh) {
      this.fresh = false;
      return;
    }
    if (this.playing && !this.removed && this.def.n > 1) {
      this.enter(this.frame >= this.def.n ? 1 : this.frame + 1);
    }
    for (const slot of [...this.slots.values()]) {
      if (!slot.node.destroyed) {
        slot.node.advance?.();
      }
    }
  }
}
