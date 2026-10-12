// The original's tweens (F1:940-1340): the calls it makes on clips, text fields and sounds to move, fade, tint, blur
// or scale them over a few seconds. Each call keeps the original's arguments after the thing it works on, so
// `hud.progressBar.xScaleTo(80, 5, "linear")` is `xScaleTo(hud.progressBar, 80, 5, "linear")`. Seconds are seconds
// and the easing is its name, "easeOutSine" and the like, which is the original's default "easeOutExpo" when left out.
//
// What it does as the original did: a new tween on a property replaces an older one on it that is still running or
// waiting, unless the new one starts after the older one ends. A tween reads where it starts from when its delay is
// over, not when it is asked for. A call with 0 seconds lands on the next frame. The callback runs once, after the
// first property of the call has arrived, with the target as `this` and as its argument. A target that was destroyed
// drops its tweens without calling them back.
//
// Added for the port: pauseTweens(true) holds every tween where it is (a paused battle), and the clock the tweens
// run on stops with it.
import { makeFilter } from "./flash.js";

const DEFAULT_EASE = "easeOutExpo";
const NORMAL = { ra: 100, rb: 0, ga: 100, gb: 0, ba: 100, bb: 0, aa: 100, ab: 0 };
const COLOR_CHANNELS = [16, 8, 0];

// ---------- Easings ----------

const HALF_PI = Math.PI / 2;
const TWO_PI = Math.PI * 2;
const POWERS = { quad: 2, cubic: 3, quart: 4, quint: 5 };

function bounceOut(u) {
  if (u < 1 / 2.75) {
    return 7.5625 * u * u;
  }
  if (u < 2 / 2.75) {
    return 7.5625 * (u - 1.5 / 2.75) ** 2 + 0.75;
  }
  if (u < 2.5 / 2.75) {
    return 7.5625 * (u - 2.25 / 2.75) ** 2 + 0.9375;
  }
  return 7.5625 * (u - 2.625 / 2.75) ** 2 + 0.984375;
}

// The elastic easings' amplitude, in changes, and the sine's period and phase in milliseconds. ctx: { d: how long the
// tween runs in ms, c: how far it goes, e1: amplitude, e2: period }
function springOf(ctx, share) {
  const period = ctx.e2 || ctx.d * share;
  if (!ctx.e1 || ctx.e1 < Math.abs(ctx.c)) {
    return { period, phase: period / 4, amplitude: 1 };
  }
  return { period, phase: (period / TWO_PI) * Math.asin(ctx.c / ctx.e1), amplitude: ctx.e1 / ctx.c };
}

function wave(ctx, spring, over) {
  return Math.sin(((over * ctx.d) - spring.phase) * TWO_PI / spring.period);
}

// Each easing as its "in" and "out" halves over 0..1: the other two kinds ("inOut" and "outIn") are built from them
const IN = {
  sine: (u) => 1 - Math.cos(u * HALF_PI),
  expo: (u) => (u === 0 ? 0 : 2 ** (10 * (u - 1))),
  circ: (u) => 1 - Math.sqrt(1 - u * u),
  back: (u, ctx) => {
    const s = ctx.e1 ?? 1.70158;
    return u * u * ((s + 1) * u - s);
  },
  bounce: (u) => 1 - bounceOut(1 - u),
  elastic: (u, ctx) => {
    if (u === 0 || u === 1) {
      return u;
    }
    const spring = springOf(ctx, 0.3);
    return -spring.amplitude * 2 ** (10 * (u - 1)) * wave(ctx, spring, u - 1);
  },
};
const OUT = {
  sine: (u) => Math.sin(u * HALF_PI),
  expo: (u) => (u === 1 ? 1 : 1 - 2 ** (-10 * u)),
  circ: (u) => Math.sqrt(1 - (u - 1) ** 2),
  back: (u, ctx) => {
    const s = ctx.e1 ?? 1.70158;
    return (u - 1) ** 2 * ((s + 1) * (u - 1) + s) + 1;
  },
  bounce: bounceOut,
  elastic: (u, ctx) => {
    if (u === 0 || u === 1) {
      return u;
    }
    const spring = springOf(ctx, 0.3);
    return spring.amplitude * 2 ** (-10 * u) * wave(ctx, spring, u) + 1;
  },
};
for (const [name, power] of Object.entries(POWERS)) {
  IN[name] = (u) => u ** power;
  OUT[name] = (u) => 1 - (1 - u) ** power;
}

// The two easings that are not just two halves of "in" and "out" put together
function inOutBack(u, ctx) {
  const s = (ctx.e1 ?? 1.70158) * 1.525;
  const v = u * 2;
  if (v < 1) {
    return 0.5 * (v * v * ((s + 1) * v - s));
  }
  return 0.5 * ((v - 2) ** 2 * ((s + 1) * (v - 2) + s) + 2);
}

function inOutElastic(u, ctx) {
  if (u === 0 || u === 1) {
    return u;
  }
  const spring = springOf(ctx, 0.45);
  const v = u * 2;
  if (v < 1) {
    return -0.5 * spring.amplitude * 2 ** (10 * (v - 1)) * wave(ctx, spring, v - 1);
  }
  return spring.amplitude * 2 ** (-10 * (v - 1)) * wave(ctx, spring, v - 1) * 0.5 + 1;
}

const warned = new Set();

// How far along a tween is, 0..1 and beyond for the overshooting easings, after u of its time
function eased(name, u, ctx) {
  const lower = String(name).toLowerCase();
  if (lower === "linear") {
    return u;
  }
  const match = /^ease(inout|outin|in|out)(.+)$/.exec(lower);
  const family = match?.[2];
  if (!family || !IN[family]) {
    if (!warned.has(lower)) {
      warned.add(lower);
      console.warn(`Warfare 1917: no easing called ${name}`);
    }
    return u;
  }
  switch (match[1]) {
    case "in":
      return IN[family](u, ctx);
    case "out":
      return OUT[family](u, ctx);
    case "inout":
      if (family === "back") {
        return inOutBack(u, ctx);
      }
      if (family === "elastic") {
        return inOutElastic(u, ctx);
      }
      return u < 0.5 ? IN[family](u * 2, ctx) / 2 : 0.5 + OUT[family](u * 2 - 1, ctx) / 2;
    default:
      return u < 0.5 ? OUT[family](u * 2, ctx) / 2 : 0.5 + IN[family](u * 2 - 1, ctx) / 2;
  }
}

// ---------- What a property is, on each kind of target ----------

// Per target: its color transform, blur and glow as the original keeps them, and the filters they are drawn with
const states = new WeakMap();

function stateOf(target) {
  let state = states.get(target);
  if (!state) {
    state = {
      cx: { ...NORMAL },
      blur: { x: 0, y: 0, passes: 2 },
      glow: { color: 0xffffff, alpha: 1, x: 0, y: 0, strength: 1 },
      filters: {},
    };
    states.set(target, state);
  }
  return state;
}

// Targets whose filters or words need drawing again after this frame's tweens have all set their values
const changed = new Map();

function touch(target, kind) {
  if (!changed.has(target)) {
    changed.set(target, new Set());
  }
  changed.get(target).add(kind);
}

const PROPS = {
  _alpha: { get: (t) => t.alpha * 100, set: (t, v) => (t.alpha = v / 100) },
  _x: { get: (t) => t.x, set: (t, v) => (t.x = v) },
  _y: { get: (t) => t.y, set: (t, v) => (t.y = v) },
  _xscale: { get: (t) => t.scale.x * 100, set: (t, v) => (t.scale.x = v / 100) },
  _yscale: { get: (t) => t.scale.y * 100, set: (t, v) => (t.scale.y = v / 100) },
  // A sound's volume out of 100 (sound.js's voices)
  volume: { get: (t) => t.volume, set: (t, v) => (t.volume = v) },
  text_color: {
    color: true,
    get: (t) => parseInt((t.def?.color ?? "#000000").slice(1), 16),
    set: (t, v) => {
      stateOf(t).textColor = v;
      touch(t, "text");
    },
  },
  glow_color: { color: true, get: (t) => stateOf(t).glow.color, set: (t, v) => setGlow(t, "color", v) },
  glow_alpha: { get: (t) => stateOf(t).glow.alpha, set: (t, v) => setGlow(t, "alpha", v) },
  glow_x: { get: (t) => stateOf(t).glow.x, set: (t, v) => setGlow(t, "x", v) },
  glow_y: { get: (t) => stateOf(t).glow.y, set: (t, v) => setGlow(t, "y", v) },
  glow_strength: { get: (t) => stateOf(t).glow.strength, set: (t, v) => setGlow(t, "strength", v) },
  blur_x: { get: (t) => stateOf(t).blur.x, set: (t, v) => setBlur(t, "x", v) },
  blur_y: { get: (t) => stateOf(t).blur.y, set: (t, v) => setBlur(t, "y", v) },
};
for (const channel of Object.keys(NORMAL)) {
  PROPS[`cx_${channel}`] = {
    get: (t) => stateOf(t).cx[channel],
    set: (t, v) => {
      stateOf(t).cx[channel] = v;
      touch(t, "cx");
    },
  };
}

function setGlow(target, key, value) {
  stateOf(target).glow[key] = value;
  touch(target, "glow");
}

function setBlur(target, key, value) {
  stateOf(target).blur[key] = value;
  touch(target, "blur");
}

// ---------- Filters and words ----------

let library = null;

// Puts a filter made for one of the target's tweened looks among its filters, in place of the one it made before
function putFilter(target, slot, made) {
  const state = stateOf(target);
  const old = state.filters[slot] ?? null;
  const rest = (target.filters ?? []).filter((filter) => filter !== old);
  state.filters[slot] = made;
  target.filters = made ? [...rest, made] : rest.length ? rest : null;
}

function hex(rgb) {
  return `#${Math.round(rgb).toString(16).padStart(6, "0")}`;
}

function redraw(target, kind) {
  const state = stateOf(target);
  const scale = library?.filterScale ?? 1;
  const old = state.filters[kind] ?? null;
  if (kind === "cx") {
    const { ra, rb, ga, gb, ba, bb, aa, ab } = state.cx;
    const plain = Object.entries(NORMAL).every(([channel, value]) => state.cx[channel] === value);
    const matrix = [ra / 100, 0, 0, 0, rb, 0, ga / 100, 0, 0, gb, 0, 0, ba / 100, 0, bb, 0, 0, 0, aa / 100, ab];
    putFilter(target, kind, plain ? null : makeFilter({ type: "matrix", matrix }, old, scale));
  } else if (kind === "blur") {
    const { x, y, passes } = state.blur;
    putFilter(target, kind, makeFilter({ type: "blur", x, y, passes }, old, scale));
  } else if (kind === "glow") {
    const { color, alpha, x, y, strength } = state.glow;
    const spec = { type: "glow", color: hex(color), alpha, x, y, strength, distance: 0, angle: 0 };
    putFilter(target, kind, alpha > 0 && (x > 0 || y > 0) ? makeFilter(spec, old, scale) : null);
  } else if (kind === "text" && target.def && target.draw) {
    target.def = { ...target.def, color: hex(state.textColor) };
    target.shown = null;
    target.draw();
  }
}

// ---------- The running tweens ----------

let list = [];
let clock = 0;
let lastReal = null;
let held = false;

function tweenValue(item, now) {
  if (item.end + item.delay <= now) {
    return item.to;
  }
  const ctx = { d: item.end - item.start, c: item.to - item.from, e1: item.e1, e2: item.e2 };
  const u = (now - item.delay - item.start) / ctx.d;
  if (item.color) {
    const channel = (shift) => {
      const from = (item.from >> shift) & 255;
      const to = (item.to >> shift) & 255;
      return Math.round(from + (to - from) * eased(item.ease, u, { ...ctx, c: to - from }));
    };
    return (channel(16) << 16) + (channel(8) << 8) + channel(0);
  }
  return ctx.c === 0 ? item.to : item.from + ctx.c * eased(item.ease, u, ctx);
}

function update() {
  const real = performance.now();
  if (!held && lastReal !== null) {
    clock += real - lastReal;
  }
  lastReal = real;
  if (held) {
    return;
  }
  for (const item of [...list]) {
    if (!list.includes(item)) {
      continue;
    }
    if (item.target.destroyed) {
      list = list.filter((other) => other !== item);
      continue;
    }
    if (item.start + item.delay > clock) {
      continue;
    }
    const prop = PROPS[item.prop];
    item.from ??= prop.get(item.target);
    prop.set(item.target, tweenValue(item, clock));
    if (item.end + item.delay <= clock) {
      list = list.filter((other) => other !== item);
      item.done?.call(item.target, item.target);
    }
  }
  const redrawn = [...changed];
  changed.clear();
  for (const [target, kinds] of redrawn) {
    if (!target.destroyed) {
      kinds.forEach((kind) => redraw(target, kind));
    }
  }
}

// Starts the tweens' clock on Pixi's ticker. lib: the art library, for the screen's scale that filters work in
export function startTweens(ticker, lib) {
  library = lib;
  ticker.add(update);
}

// Holds every tween where it is, or lets them go on from there
export function pauseTweens(on) {
  held = on;
}

export function isTweening(target) {
  return list.some((item) => item.target === target);
}

// Flash's stopTween: the target's tweens stop where they are, with no callback. props: the names to stop, or all
export function stopTween(target, ...props) {
  const names = props.flat();
  list = list.filter((item) => item.target !== target || (names.length && !names.includes(item.prop)));
}

// Flash's tween(property, to, seconds, easing, delay, callback, extra1, extra2). prop and to may be lists, which
// move together. A destination left out, null or undefined, leaves that property alone
export function tween(target, prop, to, seconds = 0, ease = DEFAULT_EASE, delay = 0, done = null, e1, e2) {
  const props = Array.isArray(prop) ? prop : [prop];
  const dests = Array.isArray(to) ? to : [to];
  let callback = done;
  for (const [index, name] of props.entries()) {
    const dest = dests[index];
    if (dest === undefined || dest === null) {
      continue;
    }
    const info = PROPS[name];
    if (!info) {
      console.warn(`Warfare 1917: can't tween ${name}`);
      continue;
    }
    const begin = clock + delay * 1000;
    const end = clock + (seconds ?? 0) * 1000;
    list = list.filter((item) => item.target !== target || item.prop !== name || begin >= item.end);
    list.push({
      target,
      prop: name,
      to: dest,
      from: undefined,
      color: info.color === true,
      start: clock,
      end,
      delay: (delay ?? 0) * 1000,
      ease: ease || DEFAULT_EASE,
      e1,
      e2,
      done: callback,
    });
    callback = null;
  }
}

// ---------- The calls the game makes ----------

export function alphaTo(target, alpha, seconds, ease, delay, done, e1, e2) {
  tween(target, "_alpha", alpha, seconds, ease, delay, done, e1, e2);
}

export function slideTo(target, x, y, seconds, ease, delay, done, e1, e2) {
  tween(target, ["_x", "_y"], [x, y], seconds, ease, delay, done, e1, e2);
}

export function xSlideTo(target, x, seconds, ease, delay, done, e1, e2) {
  tween(target, "_x", x, seconds, ease, delay, done, e1, e2);
}

export function ySlideTo(target, y, seconds, ease, delay, done, e1, e2) {
  tween(target, "_y", y, seconds, ease, delay, done, e1, e2);
}

export function scaleTo(target, scale, seconds, ease, delay, done, e1, e2) {
  tween(target, ["_xscale", "_yscale"], [scale, scale], seconds, ease, delay, done, e1, e2);
}

export function xScaleTo(target, scale, seconds, ease, delay, done, e1, e2) {
  tween(target, "_xscale", scale, seconds, ease, delay, done, e1, e2);
}

export function yScaleTo(target, scale, seconds, ease, delay, done, e1, e2) {
  tween(target, "_yscale", scale, seconds, ease, delay, done, e1, e2);
}

// A sound's volume (sound.js's voices), out of 100
export function volumeTo(target, volume, seconds, ease, delay, done, e1, e2) {
  tween(target, "volume", volume, seconds, ease, delay, done, e1, e2);
}

// The color transform of a clip: each channel's percent kept and amount added, 0 to 255. 100, 0 is unchanged. A
// channel left undefined stays as it is
export function colorTransformTo(target, ra, rb, ga, gb, ba, bb, aa, ab, seconds, ease, delay, done, e1, e2) {
  const channels = ["cx_ra", "cx_rb", "cx_ga", "cx_gb", "cx_ba", "cx_bb", "cx_aa", "cx_ab"];
  tween(target, channels, [ra, rb, ga, gb, ba, bb, aa, ab], seconds, ease, delay, done, e1, e2);
}

// A clip's whole color replaced by one color (16777215 is white), or null to get its own colors back. A text
// field's words change color instead, which has no null
export function colorTo(target, rgb, seconds, ease, delay, done, e1, e2) {
  if (target.def && target.draw) {
    tween(target, "text_color", rgb ?? 0, seconds, ease, delay, done, e1, e2);
  } else if (rgb === null || rgb === undefined) {
    colorTransformTo(target, 100, 0, 100, 0, 100, 0, undefined, undefined, seconds, ease, delay, done, e1, e2);
  } else {
    const [r, g, b] = COLOR_CHANNELS.map((shift) => (rgb >> shift) & 255);
    colorTransformTo(target, 0, r, 0, g, 0, b, undefined, undefined, seconds, ease, delay, done, e1, e2);
  }
}

// Flash's blurTo(blur, quality, seconds, ...): a blur of that many pixels each way, drawn in that many passes. Its
// seconds are the third argument, so blurTo(target, 5, 1) is an instant blur of 5
export function blurTo(target, blur, quality, seconds, ease, delay, done, e1, e2) {
  stateOf(target).blur.passes = quality ?? 2;
  tween(target, ["blur_x", "blur_y"], [blur, blur], seconds, ease, delay, done, e1, e2);
}

// Flash's glowTo(color, alpha, blur, strength, quality, inner, knockout, seconds, ...). Quality, inner and knockout
// are not drawn
export function glowTo(target, color, alpha, blur, strength, quality, inner, knockout, seconds, ease, delay, done) {
  const props = ["glow_color", "glow_alpha", "glow_x", "glow_y", "glow_strength"];
  tween(target, props, [color, alpha, blur, blur, strength], seconds, ease, delay, done);
}
