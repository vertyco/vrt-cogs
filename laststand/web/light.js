// Light: the colour the time of day and the room give the world, the lamps that glow when it is dark, and the
// flashlight.
//
// The original tints each thing in the room with a colour transform (red, green and blue as percents of the picture's
// own). Here the room's layers (the room's art, the bodies and decals, everything sorted among the actors, and the
// foreground) are tinted as wholes, so whatever a system adds to them is lit without asking. The rest of the world
// (bullets, lamps, effects) keeps its own colours, as in the original, and apply(node) tints a node that lives outside
// those layers. A percent above 100 brightens, which a tint cannot do: the tint stops at 100 and one colour matrix on
// the whole world supplies the rest, so the two together give exactly color x percent.
import { ColorMatrixFilter } from "./vendor/pixi.min.mjs";
import { applyColor } from "./flash.js";
import { data } from "./data.js";
import { input } from "./input.js";
import { layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

// Red / green / blue percents from this minute of the day on (spec 3.16, F4:35656-36002), one row per level. Every
// minute falls in exactly one row, so a long sleep or a trip never leaves the old light behind. Every level cuts a
// zombie's sight to 0.6 of its range
const SIGHT_MOD = 0.6;
// prettier-ignore
const LEVELS = [
  [0, 20, 20, 25], [240, 30, 30, 35], [331, 35, 35, 40], [360, 38, 38, 43], [376, 50, 45, 50], [390, 65, 55, 60],
  [420, 70, 65, 65], [435, 75, 70, 70], [450, 85, 80, 80], [480, 90, 85, 85], [511, 90, 90, 88], [540, 95, 95, 93],
  [571, 100, 100, 100], [780, 105, 105, 105], [960, 102, 102, 100], [991, 100, 97, 95], [1020, 98, 93, 91],
  [1035, 93, 87, 86], [1050, 87, 81, 80], [1065, 80, 74, 73], [1095, 70, 64, 70], [1110, 58, 54, 60],
  [1125, 52, 48, 54], [1140, 42, 38, 44], [1155, 30, 28, 34], [1170, 28, 25, 32], [1200, 20, 20, 25],
]; // fmt: skip
// The lamp art a marker's first four letters call for (setupRoom, F4:22190-22250)
const LAMPS = {
  lstr: "streetLight",
  lstf: "streetLightFlicker",
  lhom: "homeLight",
  lhmf: "homeLight",
  lsml: "smallLight",
  lsmg: "smallLightGreen",
  lflu: "fluroLight",
  lflf: "fluroLightFlicker",
};
// The layers that are lit as wholes; everything in them takes the tint
const LIT_LAYERS = ["bg", "back", "actors", "fg"];
// The least alpha, in percent, at which a lamp shows
const LAMP_LEAST_ALPHA = 25;
// How much further a zombie sees the player with the flashlight on (F4:9081)
const FLASHLIGHT_SIGHT = 1.25;
const CLICK = "sound_flashlight";
// Used until the converted constants load
const DEFAULT_CONSTANTS = { lightTransitionTime: 0.1, streetLightBase: 65, minLight: 5, brightnessMultiplier: 4 };
const DEFAULT_BRIGHTNESS = 3;

let page = null;
let brightener = null;
// The percents on the layers now, and where a tween to the goal has got to
const shown = { r: 0, g: 0, b: 0 };
// The percents the world is heading for; lamps and the beam read their red from it, since they do not ease
const goal = { r: 0, g: 0, b: 0 };
let tween = null;
// What the last refresh worked from: the level's row, and the room's reduction and the brightness setting
let lastLevel = null;
let lastTweak = null;
let lastTime = null;
let lastLowLamps = null;
let lamps = [];
let beam = null;
let beamPlace = { x: 0, y: 0, aim: 0 };
let flashlightOn = false;

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULT_CONSTANTS[name];
}

function brightnessSetting() {
  return story.settings?.brightness ?? DEFAULT_BRIGHTNESS;
}

function lowQuality() {
  return Boolean(story.settings?.lowFlashlight);
}

// The row of the table that holds a minute of the day
function levelAt(minute) {
  let found = 0;
  for (let i = 0; i < LEVELS.length; i += 1) {
    if (LEVELS[i][0] <= minute) {
      found = i;
    }
  }
  return found;
}

// The percents the world should show: the level cut by the room's light reduction, plus the brightness setting, never
// under the least light (F4:22534-22551)
function goalFor(row) {
  const [, ...colours] = LEVELS[row];
  const reduction = room.def?.lightReduction ?? 0;
  const lift = Math.round(brightnessSetting() * constant("brightnessMultiplier"));
  const [r, g, b] = colours.map((each) =>
    Math.max(constant("minLight"), each - Math.round((each / 100) * reduction) + lift),
  );
  return { r, g, b };
}

// ---------- Painting ----------

// A colour transform for percents: Flash's multiplier is 256 for 100%
function transformFor(percents) {
  return { mult: percents.map((each) => (Math.min(100, each) * 256) / 100).concat(256), add: [0, 0, 0, 0] };
}

function tintParts(colour) {
  return transformFor([colour.r, colour.g, colour.b]);
}

function paint() {
  const cx = tintParts(shown);
  for (const name of LIT_LAYERS) {
    layers[name].scriptColor = cx;
    applyColor(layers[name], null);
  }
  const lift = [shown.r, shown.g, shown.b].map((each) => Math.max(100, each) / 100);
  const worldNode = layers.bg.parent;
  if (lift.some((each) => each > 1)) {
    // prettier-ignore
    brightener.matrix = [
      lift[0], 0, 0, 0, 0,
      0, lift[1], 0, 0, 0,
      0, 0, lift[2], 0, 0,
      0, 0, 0, 1, 0,
    ];
    worldNode.filters = [brightener];
  } else {
    worldNode.filters = null;
  }
}

// Eases the layers to the goal over the original's transition time (linear)
function stepTween() {
  if (!tween) {
    return;
  }
  tween.at += 1;
  const t = Math.min(1, tween.at / tween.steps);
  for (const key of ["r", "g", "b"]) {
    shown[key] = tween.from[key] + (tween.to[key] - tween.from[key]) * t;
  }
  paint();
  if (t >= 1) {
    tween = null;
  }
}

// ---------- Lamps ----------

// A lamp's alpha is the street light base less the red light, and it shows while that is at least 25 (F4:22558). The
// fade goes on the lamp as a whole: its overlay parts blend with the room under them and the lamp's alpha then mixes
// that back toward the room, as Flash's alpha on the clip does
function showLamps() {
  const alpha = constant("streetLightBase") - goal.r;
  const shows = alpha >= LAMP_LEAST_ALPHA;
  const low = lowQuality();
  for (const lamp of lamps) {
    lamp.visible = shows;
    lamp.alpha = Math.min(100, alpha) / 100;
    if (lastLowLamps !== low) {
      if (low) {
        lamp.gotoAndStop("lowQuality");
      } else {
        lamp.gotoAndPlay("highQuality");
      }
    }
  }
  lastLowLamps = low;
  showBeam();
}

// A flickering lamp's last frame sends it back to its glow and plays on (the art's own "gotoAndStop(label); play();")
function lampHook(kind, arg, clip) {
  if (kind === "golabel") {
    clip.gotoAndStop(arg);
    return true;
  }
  if (kind === "go") {
    clip.play();
    return true;
  }
  return false;
}

function buildLamps() {
  lamps = [];
  lastLowLamps = null;
  for (const each of room.art?.lights ?? []) {
    const art = LAMPS[each.light];
    if (!art) {
      continue;
    }
    const lamp = page.lib.makeExported(art);
    lamp.onHook = lampHook;
    lamp.x = each.x;
    lamp.y = each.y;
    layers.lights.addChild(lamp);
    lamps.push(lamp);
  }
}

// ---------- The flashlight ----------

// The beam shows while it is on and the world is lit under 100% (the original fades it by 100 less the red light,
// F4:15722)
function showBeam() {
  if (beam && !beam.destroyed) {
    beam.visible = flashlightOn && goal.r < 100;
  }
}

function buildBeam() {
  beam = page.lib.makeExported("flashLightBeam");
  if (lowQuality()) {
    beam.gotoAndStop("low");
  }
  layers.lights.addChild(beam);
  light.placeBeam(beamPlace.x, beamPlace.y, beamPlace.aim);
}

// ---------- Refreshing ----------

// Works out the world's light and puts it on. forced paints it at once, as a room change or a setting does; a change of
// the level on its own eases in over the transition time
function refresh(forced = false) {
  lastTime = world.time;
  if (!room.id || !layers.bg) {
    return;
  }
  const row = levelAt(world.minuteOfDay);
  const tweak = `${room.def?.lightReduction ?? 0}|${brightnessSetting()}`;
  if (!forced && row === lastLevel && tweak === lastTweak) {
    return;
  }
  const live = !forced && lastLevel !== null && tweak === lastTweak;
  lastLevel = row;
  lastTweak = tweak;
  Object.assign(goal, goalFor(row));
  if (live) {
    tween = {
      from: { ...shown },
      to: { ...goal },
      at: 0,
      steps: Math.max(1, Math.round(constant("lightTransitionTime") * page.lib.fps)),
    };
  } else {
    tween = null;
    Object.assign(shown, goal);
    paint();
  }
  showLamps();
}

// Each step: the quality setting, a clock that jumped (sleep, a trip) and the tween
function watch() {
  if (world.time !== lastTime) {
    refresh();
  }
  if (lastLowLamps !== null && lastLowLamps !== lowQuality()) {
    showLamps();
    beam?.gotoAndStop(lowQuality() ? "low" : "high");
  }
  stepTween();
}

function controls() {
  if (input.flashPressed) {
    light.toggleFlashlight();
  }
}

function build() {
  lamps = [];
  beam = null;
  lastLevel = null;
  buildBeam();
  buildLamps();
  refresh(true);
}

// ---------- The module ----------

export const light = {
  // True while the flashlight is on
  get flashlight() {
    return flashlightOn;
  },

  // The percents the world is lit to now (red, green, blue)
  level() {
    return goalFor(levelAt(world.minuteOfDay));
  },

  // Lights a node that lives outside the lit layers with the tint the layers have. What is in a lit layer needs nothing
  apply(node) {
    node.scriptColor = tintParts(shown);
    applyColor(node, null);
  },

  // How far zombies see the player: x1.25 with the flashlight on
  sightBonus() {
    return flashlightOn ? FLASHLIGHT_SIGHT : 1;
  },

  // Every light level cuts a zombie's sight to this much of its range
  sightMod() {
    return SIGHT_MOD;
  },

  // Turns the flashlight on or off. click plays the switch's sound; the key press does, sleeping does not
  setFlashlight(on, { click = false } = {}) {
    flashlightOn = Boolean(on);
    showBeam();
    if (click) {
      sound.play(CLICK);
    }
  },

  // The F key: one click per toggle
  toggleFlashlight() {
    light.setFlashlight(!flashlightOn, { click: true });
  },

  // Puts the beam's base at a point of the world and points it. aim is the way the light goes, in degrees clockwise from
  // straight right: the arm's angle plus the weapon's flashlight point for a player facing right, and the same turned
  // the other way for one facing left (F4:12879-12893). The art is drawn pointing left, so it is flipped and turned
  // half a circle
  placeBeam(x, y, aim) {
    beamPlace = { x, y, aim };
    if (beam && !beam.destroyed) {
      beam.x = x;
      beam.y = y;
      beam.scale.x = -1;
      beam.rotation = ((aim - 180) * Math.PI) / 180;
    }
  },

  // The lamps in the room, for checks
  get lamps() {
    return lamps;
  },

  // The world's lighting is worked out again now
  refresh,

  // A new story or a loaded save starts with the flashlight off
  reset() {
    flashlightOn = false;
    lastLevel = null;
    lastTweak = null;
    tween = null;
    showBeam();
  },
};

// Hangs the light on the world's step and on room changes. Needs the rooms to be set up first
export function initLight(owner) {
  page = owner;
  brightener = new ColorMatrixFilter();
  world.stage("controls", controls);
  world.stage("interface", watch, { whilePaused: true });
  world.onMinute(() => refresh());
  onRoom("build", build);
}
