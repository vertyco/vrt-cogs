// Plays a Flash game's original timelines with PixiJS: shapes come from the art pages, and each sprite steps through
// its frames at the game's frame rate (lib.fps) like the Flash player did, placing, moving and removing its parts.
// Text fields show the variables of the clips they sit in, buttons show their up, over and down looks, and clips take
// presses, hovers and drags the way the original's handlers did.
import {
  BlurFilter,
  CanvasSource,
  ColorMatrixFilter,
  Container,
  extensions,
  Filter,
  GlProgram,
  HardLightBlend,
  Matrix,
  OverlayBlend,
  Rectangle,
  Sprite,
  Texture,
} from "./vendor/pixi.min.mjs";

const IDENTITY = [1, 0, 0, 1, 0, 0];
// Text is drawn at the screen's own pixels per stage pixel (the page sets it as the stage is fitted), up to 3. Drawn
// any sharper and then shrunk, the pixel font's thin strokes would drop out on small screens
const MOST_TEXT_RESOLUTION = 3;
const LEAST_TEXT_RESOLUTION = 0.25;
let textResolution = MOST_TEXT_RESOLUTION;
// Every picture of words on show, so a new screen size redraws them all at its own pixels
const shownWords = new Set();

export function setTextResolution(value) {
  const resolution = Math.max(LEAST_TEXT_RESOLUTION, Math.min(MOST_TEXT_RESOLUTION, value));
  if (resolution === textResolution) {
    return;
  }
  textResolution = resolution;
  for (const words of shownWords) {
    words.redraw();
  }
}
// Flash keeps 2 pixels between a text field's edge and its words
const GUTTER = 2;
const BLUR_MOST_PASSES = 8;
const BLUR_SPREAD = 0.28;
// Flash's blend modes by name. Pixi draws overlay and hard light with its advanced blend extensions (the page asks for
// the back buffer they need). A mode not listed draws as normal
const BLENDS = {
  normal: "normal",
  layer: "normal",
  multiply: "multiply",
  screen: "screen",
  add: "add",
  overlay: "overlay",
  hardlight: "hard-light",
};
extensions.add(OverlayBlend, HardLightBlend);
// Filters draw at the screen's pixel density. Pixi copies the screen under a blend at the screen's density but draws
// the blend at the lowest density of the part's filters, so a filter left at 1 on a 2x screen samples the wrong place
// (a blurred, doubled copy of the room covers everything under a lamp's overlay)
Filter.defaultOptions.resolution = "inherit";
const PRESS_EVENTS = {
  onPress: "pointerdown",
  onRelease: "pointerup",
  onReleaseOutside: "pointerupoutside",
  onRollOver: "pointerover",
  onRollOut: "pointerout",
};

const measure = document.createElement("canvas").getContext("2d");

// One frame's display list: depth -> { c: character, m: matrix, cx: color, pid: placement, at: the frame it was placed
// on, n: name, clip: mask depth, fx: blend and filters }
function buildFrames(def) {
  const lists = [];
  const current = new Map();
  let pid = 0;
  for (const [index, ops] of def.f.entries()) {
    for (const op of ops) {
      if (op.length === 1) {
        current.delete(op[0]);
        continue;
      }
      const [depth, char, matrix, color, move, name, clip, extras] = op;
      const old = current.get(depth);
      if (char) {
        // A new character at this depth is a new object, even when it replaces one
        pid += 1;
        const kept = move && old;
        current.set(depth, {
          c: char,
          m: matrix || (kept ? old.m : IDENTITY),
          cx: color || (kept ? old.cx : 0),
          pid,
          at: index + 1,
          n: name || (kept ? old.n : ""),
          clip: clip || 0,
          fx: extras || (kept ? old.fx : null),
        });
      } else if (old) {
        // A move with new extras replaces the old ones; one without keeps them, as Flash does
        current.set(depth, { ...old, m: matrix || old.m, cx: color || old.cx, n: name || old.n, fx: extras || old.fx });
      }
    }
    lists.push([...current.entries()].sort((a, b) => a[0] - b[0]).map(([d, e]) => ({ d, ...e })));
  }
  return lists;
}

// Puts the placement's color matrix among the node's filters, or takes it out. Other filters the node has stay
function setColorFilter(node, filter) {
  const old = node.placementColor ?? null;
  if (!old && !filter) {
    return;
  }
  node.placementColor = filter;
  const rest = (node.filters ?? []).filter((item) => item !== old);
  if (filter) {
    rest.push(filter);
  }
  node.filters = rest.length ? rest : null;
}

// Flash's transform is color x mult + add. A tint can only multiply, so a transform that adds color is drawn with a
// color matrix: mult/256 on the diagonal, add/255 as the offsets, and the alpha row the same. A parent's tint reaches
// the picture before this filter, but Flash applies it after the child's own transform, so the offsets are scaled by
// the tints above the node (fitColorFilter) and the filter's own multipliers stay as they are
function fitColorFilter(node, filter = node.placementColor) {
  const [r, g, b] = [0, 1, 2].map((channel) => {
    let product = 1;
    for (let up = node.parent; up; up = up.parent) {
      product *= up.tintMult?.[channel] ?? 1;
    }
    return product;
  });
  const key = `${r},${g},${b}`;
  if (node.placementKey === key) {
    return;
  }
  node.placementKey = key;
  const { mult, add } = node.placementCx;
  const [mr, mg, mb, ma] = mult.map((value) => value / 256);
  // prettier-ignore
  filter.matrix = [
    mr, 0, 0, 0, (add[0] / 255) * r,
    0, mg, 0, 0, (add[1] / 255) * g,
    0, 0, mb, 0, (add[2] / 255) * b,
    0, 0, 0, ma, add[3] / 255,
  ];
}

// Puts a placement's color transform on a node. A node the page's script has given its own alpha or color (a load
// handler's _alpha or colorTo) keeps it when the timeline moves the placement, as in Flash
export function applyColor(node, cx) {
  paintColor(node, node.scriptColor ?? cx);
  if (node.scriptAlpha !== undefined) {
    node.alpha = node.scriptAlpha;
  }
}

function paintColor(node, cx) {
  const add = cx?.add || [0, 0, 0, 0];
  // A baked picture holds the part's colour matrix, but not its alpha or tint, which stay on the part
  if (node.bakedState && (add[0] || add[1] || add[2] || node.placementColor)) {
    unbakeForChange(node);
  }
  if (!cx) {
    node.alpha = 1;
    node.tint = 0xffffff;
    node.tintMult = null;
    node.placementCx = null;
    node.onRender = null;
    setColorFilter(node, null);
    return;
  }
  const mult = cx.mult || [256, 256, 256, 256];
  if (add[0] || add[1] || add[2]) {
    node.alpha = 1;
    node.tint = 0xffffff;
    node.tintMult = null;
    node.placementCx = { mult, add };
    node.placementKey = null;
    const filter = node.placementColor ?? new ColorMatrixFilter();
    fitColorFilter(node, filter);
    setColorFilter(node, filter);
    node.onRender = () => fitColorFilter(node);
    bakeQueue.add(node);
    return;
  }
  node.onRender = null;
  node.placementCx = null;
  setColorFilter(node, null);
  node.tintMult = mult.slice(0, 3).map((value) => Math.max(0, Math.min(1, value / 256)));
  node.alpha = Math.max(0, Math.min(1, mult[3] / 256 + add[3] / 255));
  const channel = (i) => Math.max(0, Math.min(255, Math.round((mult[i] / 256) * 255 + add[i])));
  node.tint = (channel(0) << 16) | (channel(1) << 8) | channel(2);
}

export function setMatrix(node, m) {
  node.setFromMatrix(new Matrix(m[0], m[1], m[2], m[3], m[4], m[5]));
}

// ---------- Filters ----------

// Pixi's own filter vertex program: the filter's input drawn over its output area
const FILTER_VERTEX = `in vec2 aPosition;
out vec2 vTextureCoord;

uniform vec4 uInputSize;
uniform vec4 uOutputFrame;
uniform vec4 uOutputTexture;

void main(void) {
  vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
  position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
  position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z;
  gl_Position = vec4(position, 0.0, 1.0);
  vTextureCoord = aPosition * (uOutputFrame.zw * uInputSize.zw);
}`;

// Flash's drop shadow and glow: the picture's outline, blurred, colored and moved, drawn under the picture. High
// precision, as the vertex program's, since both read the input size
const SHADOW_FRAGMENT = `precision highp float;

in vec2 vTextureCoord;
out vec4 finalColor;

uniform sampler2D uTexture;
uniform vec4 uInputSize;
uniform vec4 uInputClamp;
uniform vec2 uOffset;
uniform vec2 uBlur;
uniform vec4 uColor;

void main(void) {
  vec4 picture = texture(uTexture, vTextureCoord);
  float shade = 0.0;
  for (int i = -2; i <= 2; i++) {
    for (int j = -2; j <= 2; j++) {
      vec2 at = vTextureCoord - uOffset * uInputSize.zw + vec2(float(i), float(j)) * uBlur * 0.25 * uInputSize.zw;
      shade += texture(uTexture, clamp(at, uInputClamp.xy, uInputClamp.zw)).a;
    }
  }
  shade = min(1.0, shade / 25.0 * uColor.a);
  finalColor = picture + vec4(uColor.rgb * shade, shade) * (1.0 - picture.a);
}`;

let shadowProgram = null;

class ShadowFilter extends Filter {
  constructor() {
    shadowProgram ??= GlProgram.from({ vertex: FILTER_VERTEX, fragment: SHADOW_FRAGMENT, name: "flash-shadow" });
    super({
      glProgram: shadowProgram,
      resources: {
        shadowUniforms: {
          uOffset: { value: new Float32Array(2), type: "vec2<f32>" },
          uBlur: { value: new Float32Array(2), type: "vec2<f32>" },
          uColor: { value: new Float32Array(4), type: "vec4<f32>" },
        },
      },
    });
  }

  // spec: the art's shadow or glow; scale: screen pixels per stage pixel
  set(spec, scale) {
    const uniforms = this.resources.shadowUniforms.uniforms;
    const distance = (spec.distance ?? 0) * scale;
    const angle = ((spec.angle ?? 0) * Math.PI) / 180;
    uniforms.uOffset[0] = Math.cos(angle) * distance;
    uniforms.uOffset[1] = Math.sin(angle) * distance;
    uniforms.uBlur[0] = spec.x * scale;
    uniforms.uBlur[1] = spec.y * scale;
    const rgb = parseInt(spec.color.slice(1), 16);
    uniforms.uColor[0] = ((rgb >> 16) & 255) / 255;
    uniforms.uColor[1] = ((rgb >> 8) & 255) / 255;
    uniforms.uColor[2] = (rgb & 255) / 255;
    uniforms.uColor[3] = spec.alpha * spec.strength;
    this.padding = Math.ceil(distance + Math.max(spec.x, spec.y) * scale) + 2;
    this.resources.shadowUniforms.update();
  }
}

// One of the art's filters (or one the page makes in the same form) as a Pixi filter, reusing the old one when it is
// the same kind. Null when it changes nothing, like a blur that has tweened down to 0
export function makeFilter(spec, old, scale) {
  if (spec.type === "blur") {
    if (!spec.x && !spec.y) {
      return null;
    }
    const blur = old instanceof BlurFilter ? old : new BlurFilter();
    // Flash's blurX is the width of a box blur, whose spread is about 0.28 of it; Pixi's strength is about the spread
    blur.strengthX = spec.x * BLUR_SPREAD * scale;
    blur.strengthY = spec.y * BLUR_SPREAD * scale;
    // Pixi's passes sample further apart as a blur grows, so big ones get more of them to stay smooth like Flash's
    blur.quality = Math.min(BLUR_MOST_PASSES, Math.max(spec.passes, Math.ceil(Math.max(spec.x, spec.y) * scale / 4)));
    return blur;
  }
  if (spec.type === "shadow" || spec.type === "glow") {
    const shadow = old instanceof ShadowFilter ? old : new ShadowFilter();
    shadow.set(spec, scale);
    return shadow;
  }
  if (spec.type === "matrix") {
    const matrix = old instanceof ColorMatrixFilter ? old : new ColorMatrixFilter();
    // Flash's offsets count 0 to 255, Pixi's 0 to 1
    matrix.matrix = spec.matrix.map((value, index) => (index % 5 === 4 ? value / 255 : value));
    return matrix;
  }
  return null;
}

// A placement's blend mode and filters. A part with no blend of its own takes its clip's, as in Flash, where a clip's
// blend mode applies to everything in it
function applyExtras(node, fx, scale) {
  if (node.bakedState) {
    unbakeForChange(node);
  }
  node.blendMode = BLENDS[fx?.blend] ?? "inherit";
  node.bakeFx = fx;
  const color = node.placementColor ?? null;
  const old = (node.filters ?? []).filter((item) => item !== color);
  const made = (fx?.filters ?? []).map((spec, index) => makeFilter(spec, old[index], scale)).filter(Boolean);
  if (color) {
    made.push(color);
  }
  node.filters = made.length ? made : null;
  if (node.filters) {
    bakeQueue.add(node);
  }
}

// ---------- Baking ----------

// A filter draws its part off screen and back every frame, which costs a phone more than the rest of a room. A part
// whose picture can't change is drawn once, filters and all, into a picture shown in place of its own parts. Parts
// that get filters wait in a queue for the next draw (bakeQueued), when they stand on the stage at their screen size.
// Pictures wider or taller than this many pixels are not made: phones cap a texture there
const BAKE_MOST_PIXELS = 4096;
// Pixels round the part's outline kept for a shadow or a blur, beyond the filter's own padding
const BAKE_MARGIN = 2;
// A part whose picture changes more often than this is left unbaked
const MOST_REBAKES = 3;
const bakeQueue = new Set();
// Every part baked once, so a new screen size can draw them all again
const baked = new Set();
// Pictures of parts that look the same (the blurred shadow every zombie wears), shared: key -> picture
const pictures = new Map();

// Overlay and the other blends mix a part with what is under it on the screen, which a picture of the part alone lacks
function blends(node) {
  return node.blendMode !== "inherit" && node.blendMode !== "normal";
}

// One frame all the way down, nothing stepping it each tick, no presses, no blends, no text a variable can change and
// no named parts, which a script may show, hide or move. A text field may be baked on its own: new words unbake it
function isStill(node, top = true) {
  if (blends(node)) {
    return false;
  }
  // Parts get names only from their clip's timeline (a Sprite's label is its class name)
  if (!top && ((node.label && node.parent instanceof Clip) || node instanceof TextField)) {
    return false;
  }
  if (node instanceof Clip) {
    const plays = node.def.n > 1 && !stillTimeline(node.def);
    if (plays || node.onEnterFrame || node.attached.size || Object.keys(node.handlers).length) {
      return false;
    }
  } else if (node instanceof Button) {
    return false;
  }
  return node.children.every((child) => isStill(child, false));
}

// The filters a part and everything in it draw with
function filtersIn(node, found = []) {
  if (node.filters) {
    found.push(...node.filters);
  }
  node.children.forEach((child) => filtersIn(child, found));
  return found;
}

// A picture is drawn the way the part faces on the screen. Colour and an even blur look the same however the part
// turns later, but a shadow falls one way and an uneven blur spreads one way, so a part with those is baked only when
// no timeline above it can turn or flip it
function turnsFreely(filters) {
  const even = (filter) => filter instanceof BlurFilter && filter.strengthX === filter.strengthY;
  return filters.every((filter) => filter instanceof ColorMatrixFilter || even(filter));
}

function bakeable(node) {
  const shown = node.renderable && node.includeInBuild !== false;
  return shown && !node.destroyed && !node.bakedState && !node.bakeSkip && node.filters?.length > 0;
}

// What the parts above a part allow: "drop" under a baked, hidden or blended part; "wait" off the stage, or under a
// part fading in or out (a filter mixes a see-through picture with what is under it unlike a picture of it would);
// else "still" when no timeline above can turn the part, "moving" when one can
function placeOf(node, stage) {
  let settled = true;
  let solid = true;
  let up = node.parent;
  for (; up && up !== stage; up = up.parent) {
    if (up.bakedState || !up.renderable || blends(up)) {
      return "drop";
    }
    settled &&= !(up instanceof Clip) || up.def.n === 1 || stillTimeline(up.def);
    solid &&= up.alpha >= 1;
  }
  if (!up || !solid) {
    return "wait";
  }
  return settled ? "still" : "moving";
}

// "bake" for a still part that can be baked now, "wait" for one to try again at the next draw, "drop" for the rest
function bakeCheck(node, stage) {
  if (!bakeable(node)) {
    return "drop";
  }
  const place = placeOf(node, stage);
  if (place === "drop" || place === "wait") {
    return place;
  }
  return isStill(node) && (place === "still" || turnsFreely(filtersIn(node))) ? "bake" : "drop";
}

// Bakes the queued parts that stand on the stage. Call before drawing it
export function bakeQueued(renderer, stage) {
  for (const node of bakeQueue) {
    const check = bakeCheck(node, stage);
    if (check !== "wait") {
      bakeQueue.delete(node);
    }
    if (check === "bake") {
      bake(node, renderer);
    }
  }
}

// What the picture of a part shows, for sharing it: the part, its placement's filters and colour, how it stands on
// the screen, and the place, look and colour of everything in it
function pictureKey(node, turn, resolution) {
  if (node instanceof TextField) {
    return null;
  }
  const inside = [];
  const walk = (each) => {
    const m = each.localTransform;
    inside.push(each.charId ?? "", each.visible, each.renderable, each.alpha, each.tint);
    inside.push(m.a, m.b, m.c, m.d, m.tx, m.ty);
    each.children.forEach(walk);
  };
  node.children.forEach(walk);
  const look = JSON.stringify([node.bakeFx ?? null, node.placementCx ?? null]);
  const stands = [turn.a, turn.b, turn.c, turn.d].map((value) => value.toFixed(3)).join(",");
  return `${node.charId}|${look}|${stands},${resolution}|${inside.join(",")}`;
}

// Draws the part as it stands on the screen (turn: its size, turn and flip there) with its filters, but without its
// own place, alpha, tint and mask, which stay on the part and so reach the picture as they reached its insides. The
// tints of the layers above it (the room's light) reach the picture after its own colour transform, as Flash applies
// them
function drawPicture(node, renderer, turn) {
  const parent = node.parent;
  const index = parent.getChildIndex(node);
  node.updateLocalTransform();
  const kept = { m: node.localTransform.clone(), mask: node.mask, alpha: node.alpha, tint: node.tint };
  // Container's own setFromMatrix: a part a script took over replaces it with one that ignores the timeline, which
  // would leave its scale on while the turn applies it again
  Container.prototype.setFromMatrix.call(node, new Matrix());
  Object.assign(node, { mask: null, alpha: 1, tint: 0xffffff });
  const turner = new Container();
  turner.setFromMatrix(turn);
  turner.addChild(node);
  const holder = new Container();
  holder.addChild(turner);
  const box = holder.getLocalBounds().rectangle;
  const pad = Math.max(0, ...filtersIn(node).map((filter) => filter.padding ?? 0)) + BAKE_MARGIN;
  const frame = new Rectangle(Math.floor(box.x - pad), Math.floor(box.y - pad));
  frame.width = Math.ceil(box.x + box.width + pad) - frame.x;
  frame.height = Math.ceil(box.y + box.height + pad) - frame.y;
  const fits = box.width > 0 && Math.max(frame.width, frame.height) * renderer.resolution <= BAKE_MOST_PIXELS;
  const texture = fits ? renderer.generateTexture({ target: holder, frame, resolution: renderer.resolution }) : null;
  parent.addChildAt(node, index);
  Container.prototype.setFromMatrix.call(node, kept.m);
  Object.assign(node, { mask: kept.mask, alpha: kept.alpha, tint: kept.tint });
  holder.destroy({ children: true });
  if (!texture) {
    return null;
  }
  // The picture goes back into the part's own space: the turn undone, from the frame's corner
  const back = turn.clone().invert();
  back.tx = back.a * frame.x + back.c * frame.y;
  back.ty = back.b * frame.x + back.d * frame.y;
  return { texture, back, users: 0 };
}

function bake(node, renderer) {
  const world = node.getGlobalTransform(new Matrix(), false);
  const turn = new Matrix(world.a, world.b, world.c, world.d, 0, 0);
  if (Math.abs(turn.a * turn.d - turn.b * turn.c) < 1e-6) {
    return;
  }
  const key = pictureKey(node, turn, renderer.resolution);
  let picture = key && pictures.get(key);
  if (!picture) {
    picture = drawPicture(node, renderer, turn);
    if (!picture) {
      return;
    }
    if (key) {
      pictures.set(key, picture);
    }
  }
  picture.users += 1;
  const sprite = new Sprite(picture.texture);
  sprite.setFromMatrix(picture.back);
  // Words stay on the screen's pixels, as their own picture does
  sprite.roundPixels = node instanceof Words;
  const hidden = node.children.filter((child) => child.renderable);
  hidden.forEach((child) => (child.renderable = false));
  node.bakedState = { sprite, hidden, picture, key, filters: node.filters, onRender: node.onRender };
  node.filters = null;
  node.onRender = null;
  node.addChild(sprite);
  if (!baked.has(node)) {
    baked.add(node);
    node.once("destroyed", () => {
      if (node.bakedState) {
        release(node.bakedState);
      }
      baked.delete(node);
    });
  }
}

function release(state) {
  state.picture.users -= 1;
  if (state.picture.users <= 0) {
    if (state.key) {
      pictures.delete(state.key);
    }
    state.picture.texture.destroy(true);
  }
}

// The part shows its own parts and filters again, as before it was baked
function unbake(node) {
  const state = node.bakedState;
  node.bakedState = null;
  state.sprite.destroy();
  release(state);
  state.hidden.forEach((child) => {
    if (!child.destroyed) {
      child.renderable = true;
    }
  });
  node.filters = state.filters;
  node.onRender = state.onRender;
  node.placementKey = null;
}

// The part's picture changed (new words, a new colour or filter). One that keeps changing, a counter or a tween, stays
// unbaked, as drawing it again every step would cost more than its filters
function unbakeForChange(node) {
  unbake(node);
  node.rebakes = (node.rebakes ?? 0) + 1;
  if (node.rebakes > MOST_REBAKES) {
    node.bakeSkip = true;
  } else {
    bakeQueue.add(node);
  }
}

// The screen's pixel size changed: every baked part is drawn again at the next draw
export function rebakeAll() {
  for (const node of baked) {
    if (node.bakedState) {
      unbake(node);
      bakeQueue.add(node);
    }
  }
}

// ---------- Text ----------

function fontOf(font, bold, size) {
  return `${bold ? "bold " : ""}${size}px ${font}`;
}

// Ascent and descent per em that Flash lays text out with: the embedded fonts' own (their DefineFont3 tags, in units
// of 20480 to the em), and for the device fonts the system font's. The font files the page loads were rebuilt from the
// embedded outlines and carry other vertical metrics, which would put every line higher and closer than Flash does
const FONT_METRICS = {
  "AlternateGothic2 BT": [18480 / 20480, 4840 / 20480],
  "Courier New": [17060 / 20480, 6160 / 20480],
  "DIN-Black": [21120 / 20480, 4100 / 20480],
  "DIN-Bold": [20780 / 20480, 4220 / 20480],
  DINChadstone: [19180 / 20480, 5120 / 20480],
  "DIN-Regular": [20180 / 20480, 4620 / 20480],
  HarleyHand1: [15180 / 20480, 6020 / 20480],
  "Rockwell Extra Bold": [19380 / 20480, 4680 / 20480],
  Tahoma: [20500 / 20480, 4240 / 20480],
  Arial: [0.905, 0.212],
  Calibri: [0.75, 0.25],
  "Times New Roman": [0.891, 0.216],
};

// How far a font reaches above and below its baseline, as Flash measures it. A font with no known metrics uses the
// browser's, and browsers without those get a typical font's
function metricsOf(font, size) {
  const family = /px\s+"?([^",]+)/.exec(font)?.[1];
  const known = FONT_METRICS[family];
  if (known) {
    return { ascent: known[0] * size, descent: known[1] * size };
  }
  measure.font = font;
  const m = measure.measureText("M");
  return { ascent: m.fontBoundingBoxAscent ?? size * 0.8, descent: m.fontBoundingBoxDescent ?? size * 0.2 };
}

// A picture of words drawn on a canvas at the screen's resolution, shown at its stage size. Like a shape, it never
// takes the pointer: in Flash only clips with handlers do, so words over a button let its presses through
class Words extends Container {
  constructor(x, y, width, height) {
    super();
    this.eventMode = "none";
    this.box = { x, y, width, height };
    // The last painting, done again when the picture is redrawn at a new resolution
    this.drawing = null;
    this.build();
    shownWords.add(this);
  }

  // A canvas at the current text resolution, shown through a sprite at the picture's stage size
  build() {
    const { x, y, width, height } = this.box;
    this.density = textResolution;
    this.canvas = document.createElement("canvas");
    this.canvas.width = Math.max(1, Math.ceil(width * this.density));
    this.canvas.height = Math.max(1, Math.ceil(height * this.density));
    this.source = new CanvasSource({ resource: this.canvas });
    this.sprite = new Sprite(new Texture({ source: this.source }));
    this.sprite.position.set(x, y);
    this.sprite.scale.set(1 / this.density);
    // Each of the drawing's pixels lands on one of the screen's, not smeared across two
    this.sprite.roundPixels = true;
    this.addChild(this.sprite);
  }

  // The screen's pixel size changed: a new canvas at the new resolution, painted again
  redraw() {
    this.sprite.destroy();
    this.source.destroy();
    this.build();
    if (this.drawing) {
      this.paint(this.drawing);
    }
  }

  // draw(context) paints in stage pixels from the picture's corner
  paint(draw) {
    this.drawing = draw;
    const context = this.canvas.getContext("2d");
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    context.setTransform(this.density, 0, 0, this.density, 0, 0);
    context.textBaseline = "alphabetic";
    draw(context);
    this.source.update();
    // A baked field shows its old words until it is baked again
    if (this.bakedState) {
      unbakeForChange(this);
    }
  }

  destroy(options) {
    shownWords.delete(this);
    this.source.destroy();
    super.destroy(options);
  }

  advance() {}
}

// The original's fixed text, such as the "DONE" on the settings button: one line per text record. Flash puts each glyph
// of a static text where its record's advances say, which carry the author's letter spacing and are not the font's
// own widths, so a record with advances is drawn glyph by glyph
const LABEL_MARGIN = 2;

export class Label extends Words {
  constructor(records) {
    const lines = records.map(([words, font, bold, size, color, x, baseline, advances]) => {
      const style = fontOf(font, bold, size);
      const { ascent, descent } = metricsOf(style, size);
      measure.font = style;
      const width = advances ? advances.reduce((sum, step) => sum + step, 0) : measure.measureText(words).width;
      return { words, style, color, x, baseline, advances, width, ascent, descent };
    });
    const left = Math.min(...lines.map((line) => line.x)) - LABEL_MARGIN;
    const top = Math.min(...lines.map((line) => line.baseline - line.ascent));
    const right = Math.max(...lines.map((line) => line.x + line.width)) + LABEL_MARGIN;
    const bottom = Math.max(...lines.map((line) => line.baseline + line.descent));
    super(left, top, right - left, bottom - top);
    this.paint((context) => {
      for (const line of lines) {
        context.font = line.style;
        context.fillStyle = line.color;
        if (!line.advances) {
          context.fillText(line.words, line.x - left, line.baseline - top);
          continue;
        }
        let x = line.x - left;
        for (const [index, step] of line.advances.entries()) {
          context.fillText(line.words[index], x, line.baseline - top);
          x += step;
        }
      }
    });
  }
}

// Paragraphs of an HTML field's starting text, each in its own size and color
function paragraphsOf(def) {
  const found = [];
  for (const match of def.html.matchAll(/<p[^>]*>(.*?)<\/p>/gs)) {
    const body = match[1];
    const size = Number(/size="(\d+)"/.exec(body)?.[1] ?? def.size);
    const color = /color="(#[0-9a-fA-F]{6})"/.exec(body)?.[1] ?? def.color;
    const text = body
      .replace(/<sbr\s*\/?>/g, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'");
    for (const line of text.split("\n")) {
      found.push({ text: line, size, color });
    }
  }
  return found;
}

// Breaks a line into lines no wider than width, at spaces
function wrapLine(line, width) {
  const words = line.split(" ");
  const lines = [];
  let current = "";
  for (const word of words) {
    const tried = current ? `${current} ${word}` : word;
    if (current && measure.measureText(tried).width > width) {
      lines.push(current);
      current = word;
    } else {
      current = tried;
    }
  }
  lines.push(current);
  return lines;
}

// One line of a justified field: the space left over shared out between its words
function justify(context, line, left, right, baseline) {
  const words = line.split(" ").filter(Boolean);
  const widths = words.map((word) => measure.measureText(word).width);
  const gap = words.length > 1 ? (right - left - widths.reduce((a, b) => a + b, 0)) / (words.length - 1) : 0;
  let x = left;
  words.forEach((word, index) => {
    context.fillText(word, x, baseline);
    x += widths[index] + gap;
  });
}

// A text field: shows the variable named by its variableName, read from the clip it sits in, or from that clip's
// parents for "_parent." names, or the words set on its text, in the field's own font, size, color and alignment, cut
// off at its bounds
export class TextField extends Words {
  constructor(def) {
    const [xmin, ymin, xmax, ymax] = def.bounds;
    super(xmin, ymin, xmax - xmin, ymax - ymin);
    this.def = def;
    this.width0 = xmax - xmin;
    this.owner = null;
    this.variable = "";
    // Words set straight on a field with no variable
    this.own = null;
    this.shown = null;
    if (def.alpha !== undefined) {
      this.alpha = def.alpha;
    }
  }

  // Finds the clip holding this field's variable, starting from the clip it sits in. Flash gives a missing variable
  // the field's starting text
  bind(scope) {
    let path = this.def.var || "";
    let owner = scope;
    while (owner && path.startsWith("_parent.")) {
      owner = owner.parentClip;
      path = path.slice("_parent.".length);
    }
    const parts = path.split(".");
    this.variable = parts.pop();
    for (const part of parts) {
      owner = owner?.child(part) ?? null;
    }
    this.owner = this.variable ? owner : null;
    if (this.owner) {
      if (this.owner.vars[this.variable] === undefined) {
        this.owner.vars[this.variable] = this.def.text;
      }
      this.owner.watch(this.variable, this);
    }
    this.draw();
  }

  get text() {
    if (!this.owner) {
      return this.own ?? this.def.text;
    }
    const value = this.owner.vars[this.variable];
    return value === undefined || value === null ? "" : String(value);
  }

  // ActionScript 3 sets a field's words directly (field.text = ...), as its fields have no variable to show
  set text(value) {
    if (this.owner) {
      this.owner.set(this.variable, value);
      return;
    }
    this.own = value === undefined || value === null ? "" : String(value);
    this.draw();
  }

  // From now on, words wider than the field are drawn smaller until they fit its width. The original's fields were
  // made for its own words; players' names can be longer
  fit() {
    this.def = { ...this.def, fit: true };
    this.shown = null;
    this.draw();
  }

  sizeFor(line) {
    const def = this.def;
    if (!def.fit) {
      return def.size;
    }
    measure.font = fontOf(def.font, def.bold, def.size);
    const room = this.width0 - GUTTER * 2;
    const wide = measure.measureText(line).width;
    return wide > room ? (def.size * room) / wide : def.size;
  }

  draw() {
    const text = this.text;
    if (text === this.shown) {
      return;
    }
    this.shown = text;
    const def = this.def;
    const lines =
      def.html && text === def.text
        ? paragraphsOf(def)
        : text.split(/\r\n|\r|\n/).map((line) => ({ text: line, size: this.sizeFor(line), color: def.color }));
    const margins = def.margins ?? {};
    const left = GUTTER + (margins.left ?? 0);
    const right = this.width0 - GUTTER - (margins.right ?? 0);
    let end = GUTTER;
    this.paint((context) => {
      let top = GUTTER;
      for (const paragraph of def.multiline ? lines : lines.slice(0, 1)) {
        const style = fontOf(def.font, def.bold, paragraph.size);
        const { ascent, descent } = metricsOf(style, paragraph.size);
        context.font = style;
        measure.font = style;
        context.fillStyle = paragraph.color;
        const parts = def.wrap ? wrapLine(paragraph.text, right - left) : [paragraph.text];
        for (const [index, part] of parts.entries()) {
          // Justified lines spread their words to both edges, all but a paragraph's last, which stays on the left
          if (def.align === "justify" && index < parts.length - 1) {
            justify(context, part, left, right, top + ascent);
            top += ascent + descent + (def.leading ?? 0);
            continue;
          }
          const width = measure.measureText(part).width;
          let x = left;
          if (def.align === "center") {
            x = (left + right - width) / 2;
          } else if (def.align === "right") {
            x = right - width;
          }
          context.fillText(part, x, top + ascent);
          top += ascent + descent + (def.leading ?? 0);
        }
      }
      end = top;
    });
    // How tall the field would be to hold every line (Flash's autoSize height), whatever its own bounds cut off
    this.contentHeight = end + GUTTER;
  }

  destroy(options) {
    this.owner?.unwatch(this.variable, this);
    super.destroy(options);
  }
}

// ---------- The library ----------

export class Library {
  // data: flash.json. loadPage(index) resolves with an atlas page's texture; pages load when first needed
  constructor(data, loadPage) {
    this.data = data;
    // The original's frames per second, from the SWF header
    this.fps = data.fps;
    this.scale = data.atlas.scale;
    this.loadPage = loadPage;
    this.loading = data.atlas.pages.map(() => null);
    this.textures = data.atlas.pages.map(() => null);
    this.pieces = new Map();
    this.frameCache = new Map();
    // Sprite id -> whether a copy of it can never change on its own (inert)
    this.inertSprites = new Map();
    this.random = Math.random;
    // Set while the page replays the bot's game: picks which of a timeline's frames a random jump goes to, or null to
    // pick at random
    this.choose = null;
    // Called with a sound name and its fade ([[seconds, volume], ...], or undefined for full volume) when a timeline
    // reaches a frame that starts one. data.sounds maps the name to its file in sounds/
    this.onSound = null;
    // Called with (kind, argument, clip, action) when a timeline reaches one of the original's script hooks
    // (port.json's hooks and patterns, and "parentstop") and the clip has no onHook of its own. action is the whole
    // entry, so a frame with two hooks of one kind and argument (head._x, then head._y) gives each its own values.
    // Returning true means the page did what the hook asks
    this.onHook = null;
    // Called with (node, parentClip, depth, frame, cx) when a timeline makes a new part, once it is in its parent and
    // named: the page's run of the part's onClipEvent(load) handler. frame is the one the part was placed on
    this.onPlace = null;
    // Sprite id -> function(clip, frame): the page's port of a frame script the art lists under "code"
    this.scripts = new Map();
    // Shape ids a mask layer uses that cut by their see-through parts (a ring), not their outline
    this.alphaMasks = new Set();
    // Screen pixels per stage pixel, for filters, which work in screen pixels
    this.filterScale = 1;
    // The clip being dragged (Clip.startDrag), and the pointer's last place on the screen
    this.drag = null;
    this.pointer = { x: 0, y: 0 };
    // What each pointer (by id) went down on, until it comes up: a clip's onRelease is only for its own press
    this.pressed = new Map();
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

  // A sprite whose copies never change once made: one frame (or frames that change nothing), no sound or script, and
  // nothing in it but shapes, words and other such sprites. Stepping one does nothing until a part is attached inside
  inert(id) {
    let known = this.inertSprites.get(id);
    if (known === undefined) {
      // A sprite that holds itself is not inert
      this.inertSprites.set(id, false);
      const def = this.data.sprites[id];
      const quiet = !def.a && !def.s && !def.code?.length && (def.n === 1 || stillTimeline(def));
      known = quiet && def.f.every((ops) => ops.every((op) => this.inertPart(op[1])));
      this.inertSprites.set(id, known);
    }
    return known;
  }

  inertPart(char) {
    if (!char || this.data.buttons?.[char]) {
      return !char;
    }
    return !this.data.sprites[char] || this.inert(char);
  }

  // The atlas pages some characters draw from, following sprites into everything they place
  pagesFor(ids) {
    const pages = new Set();
    const seen = new Set();
    const walk = (id) => {
      if (seen.has(id)) {
        return;
      }
      seen.add(id);
      for (const piece of this.data.atlas.shapes[id] ?? []) {
        pages.add(piece[0]);
      }
      for (const ops of this.data.sprites[id]?.f ?? []) {
        for (const op of ops) {
          if (op[1]) {
            walk(op[1]);
          }
        }
      }
      for (const [char] of this.data.buttons?.[id] ?? []) {
        walk(char);
      }
    };
    ids.forEach(walk);
    return pages;
  }

  // A page that failed to load is tried again the next time it is needed
  page(index) {
    this.loading[index] ??= this.loadPage(index).then(
      (texture) => {
        this.textures[index] = texture;
        return texture;
      },
      (e) => {
        this.loading[index] = null;
        throw e;
      },
    );
    return this.loading[index];
  }

  // Frees one atlas page's texture and the pieces cut from it, so the next need() loads it again. Clips still showing
  // those shapes must be destroyed first. A page that is still loading is left alone and false is returned
  forgetPage(index) {
    const texture = this.textures[index];
    if (!texture) {
      return false;
    }
    this.textures[index] = null;
    this.loading[index] = null;
    for (const [id, pieces] of this.pieces) {
      if (this.data.atlas.shapes[id].some(([page]) => page === index)) {
        pieces.forEach((piece) => piece.texture.destroy(false));
        this.pieces.delete(id);
      }
    }
    texture.destroy(true);
    return true;
  }

  // Resolves once every page those characters draw from has loaded
  need(ids) {
    return Promise.all([...this.pagesFor(ids)].map((index) => this.page(index)));
  }

  piecesOf(id) {
    let pieces = this.pieces.get(id);
    if (pieces) {
      return pieces;
    }
    const list = this.data.atlas.shapes[id];
    if (list.some(([page]) => !this.textures[page])) {
      console.warn(`flash.js: shape ${id} was drawn before its art page loaded`);
      return [];
    }
    pieces = list.map(([page, x, y, w, h, left, top]) => ({
      texture: new Texture({ source: this.textures[page].source, frame: new Rectangle(x, y, w, h) }),
      left: left / this.scale,
      top: top / this.scale,
    }));
    this.pieces.set(id, pieces);
    return pieces;
  }

  // A new display object for a character, ready to show: a sprite's clip has run its first frame's script
  make(id, frame = 1) {
    const node = this.create(id, frame);
    node.start?.();
    return node;
  }

  makeExported(name) {
    return this.make(this.exported(name));
  }

  // A new display object as a timeline places it: a sprite's first frame script waits until the timeline's own has
  // run, as Flash runs a frame's script before its new parts' scripts
  create(id, frame = 1) {
    if (this.data.sprites[id]) {
      return new Clip(this, id, frame);
    }
    if (this.data.atlas.shapes[id]) {
      return new Shape(this, id);
    }
    if (this.data.buttons?.[id]) {
      return new Button(this, id);
    }
    const text = this.data.texts[id];
    if (text) {
      return Object.assign(new TextField(text), { charId: id });
    }
    if (this.data.labels[id]) {
      return Object.assign(new Label(this.data.labels[id]), { charId: id });
    }
    return new Container();
  }

  // Drags follow the pointer over the whole stage (stage: Pixi's root container, taking pointer events), and each
  // press is kept until its pointer comes up. Every press and release on the stage reaches it after its target
  trackPointer(stage) {
    const moved = (event) => {
      this.pointer = { x: event.global.x, y: event.global.y };
      this.moveDrag();
    };
    stage.on("globalpointermove", moved);
    stage.on("pointerdown", (event) => {
      this.pressed.set(event.pointerId, event.target);
      moved(event);
    });
    const lifted = (event) => this.pressed.delete(event.pointerId);
    stage.on("pointerup", lifted);
    stage.on("pointerupoutside", lifted);
    // A pointer the browser takes away (a system gesture) never comes up, and Pixi passes no word of it on; losing
    // focus takes every pointer. Each press it held is let go and a drag stops
    window.addEventListener("pointercancel", (event) => this.cancelPress(event.pointerId, event.pointerType));
    window.addEventListener("blur", () => {
      for (const id of [...this.pressed.keys()]) {
        this.cancelPress(id);
      }
      this.drag = null;
    });
  }

  // A clip's own handlers hear a cancelled press as a release outside (Flash had no word for a press taken away), and
  // whatever listens for Pixi's pointercancel hears that
  cancelPress(id, pointerType = undefined) {
    const target = this.pressed.get(id);
    this.pressed.delete(id);
    this.drag = null;
    if (!target || target.destroyed) {
      return;
    }
    const event = { pointerId: id, pointerType, button: 0, global: { ...this.pointer } };
    target.handlers?.onReleaseOutside?.(event);
    target.emit("pointercancel", event);
  }

  moveDrag() {
    const drag = this.drag;
    if (!drag) {
      return;
    }
    const clip = drag.clip;
    if (clip.destroyed || !clip.parent) {
      this.drag = null;
      return;
    }
    const at = clip.parent.toLocal(this.pointer);
    const [left, top, right, bottom] = drag.bounds ?? [-Infinity, -Infinity, Infinity, Infinity];
    clip.x = Math.max(left, Math.min(right, at.x + drag.dx));
    clip.y = Math.max(top, Math.min(bottom, at.y + drag.dy));
  }
}

// One of the art's shapes. It never takes the pointer itself (in Flash only clips with handlers do, so a frame drawn
// over a list lets presses through to the list)
class Shape extends Container {
  constructor(lib, id) {
    super();
    this.charId = id;
    this.eventMode = "none";
    for (const piece of lib.piecesOf(id)) {
      const sprite = new Sprite(piece.texture);
      sprite.position.set(piece.left, piece.top);
      sprite.scale.set(1 / lib.scale);
      this.addChild(sprite);
    }
    // A shape that draws nothing (an invisible hit area under a button's lettering) still has its size, which
    // Flash presses and measures by
    const blank = lib.data.atlas.blank[id];
    if (blank) {
      const [left, top, right, bottom] = blank;
      this.boundsArea = new Rectangle(left, top, right - left, bottom - top);
    }
  }

  // Pixi asks a mask whether a point is inside it before a press reaches the parts it covers, so, as in Flash, a
  // list's rows take presses only where its mask shows them
  containsPoint(point) {
    return this.getLocalBounds().containsPoint(point.x, point.y);
  }

  advance() {}
}

// A Flash button: a look for each state ("u" up, "o" over, "d" down) built from its records. The page chooses the
// state, and gives the button its own hit area from the "h" records when it needs presses
export class Button extends Container {
  constructor(lib, id) {
    super();
    this.lib = lib;
    this.charId = id;
    this.records = [...lib.data.buttons[id]].sort((a, b) => a[1] - b[1]);
    this.state = "";
    this.show("u");
  }

  show(state) {
    if (state === this.state) {
      return;
    }
    this.state = state;
    for (const child of this.removeChildren()) {
      child.destroy({ children: true });
    }
    for (const [char, , states, m, cx] of this.records) {
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

// ---------- Clips ----------

// A timeline whose later frames change nothing and that plays no sound or script: however it plays, it looks like its
// first frame
function stillTimeline(def) {
  def.still ??= !def.a && !def.s && !def.code?.length && def.f.slice(1).every((ops) => ops.length === 0);
  return def.still;
}

// No timeline below that still plays, and nothing stepping each tick
function isSettled(node) {
  if (node instanceof Clip) {
    const plays = node.playing && node.def.n > 1 && !stillTimeline(node.def);
    if (plays || node.onEnterFrame || node.attached.size) {
      return false;
    }
  }
  return node.children.every(isSettled);
}

export class Clip extends Container {
  constructor(lib, id, frame = 1) {
    super();
    this.lib = lib;
    this.charId = id;
    this.def = lib.data.sprites[id];
    this.lists = lib.frames(id);
    this.frame = 0;
    this.playing = true;
    this.removed = false;
    // depth -> { pid, node, m, cx, fx, steps }
    this.slots = new Map();
    this.named = {};
    // The clip's variables, and the text fields showing each one
    this.vars = {};
    this.fields = new Map();
    // Clips the page attached on top of the timeline's parts, which step with it (Flash's attachMovie)
    this.attached = new Set();
    // Set on the tick this clip was made, so it shows frame 1 for a whole tick before moving on
    this.fresh = true;
    // Called with (kind, argument, clip) when the timeline reaches one of the original's script hooks
    this.onHook = null;
    // Flash's onEnterFrame: called once a tick, after the timeline steps
    this.onEnterFrame = null;
    // Nothing in an inert clip changes as it steps, until something is attached inside it (lively)
    this.inert = lib.inert(id);
    this.lively = false;
    this.handlers = {};
    this.listening = false;
    this.hand = true;
    this.started = false;
    this.waiting = this.show(Math.min(frame, this.def.n));
  }

  get totalFrames() {
    return this.def.n;
  }

  // The nearest clip this one sits in (Flash's _parent)
  get parentClip() {
    let up = this.parent;
    while (up && !(up instanceof Clip)) {
      up = up.parent;
    }
    return up;
  }

  // A named part: one the timeline placed, or one attached by that name (Flash finds both the same way)
  child(name) {
    if (this.named[name]) {
      return this.named[name];
    }
    for (const node of this.attached) {
      if (node.label === name && !node.removed && !node.destroyed) {
        return node;
      }
    }
    return null;
  }

  // The part the timeline shows at a depth, for parts the original left unnamed
  at(depth) {
    return this.slots.get(depth)?.node ?? null;
  }

  // ---------- Variables ----------

  get(name) {
    return this.vars[name];
  }

  set(name, value) {
    this.vars[name] = value;
    for (const field of this.fields.get(name) ?? []) {
      field.draw();
    }
  }

  watch(name, field) {
    if (!this.fields.has(name)) {
      this.fields.set(name, new Set());
    }
    this.fields.get(name).add(field);
  }

  unwatch(name, field) {
    this.fields.get(name)?.delete(field);
  }

  // ---------- The timeline ----------

  // Show a frame: keep the parts that carry on, make the new ones, drop the rest. Returns the new parts, whose
  // scripts run after this frame's own
  show(frame) {
    this.frame = frame;
    const list = this.lists[frame - 1];
    const keep = new Set();
    const made = [];
    this.named = {};
    let index = 0;
    for (const entry of list) {
      keep.add(entry.d);
      let slot = this.slots.get(entry.d);
      const placed = !slot || slot.pid !== entry.pid;
      if (placed) {
        if (slot) {
          slot.node.destroy({ children: true });
        }
        const part = this.lib.create(entry.c);
        // Only clips and buttons do anything when stepped; shapes and words are left out of the step
        const steps = part instanceof Clip || part instanceof Button;
        slot = { pid: entry.pid, node: part, m: null, cx: null, fx: null, steps };
        this.slots.set(entry.d, slot);
        made.push(slot.node);
      }
      const node = slot.node;
      if (slot.m !== entry.m) {
        setMatrix(node, entry.m);
        slot.m = entry.m;
      }
      if (slot.cx !== entry.cx) {
        applyColor(node, entry.cx);
        slot.cx = entry.cx;
      }
      if (slot.fx !== entry.fx) {
        applyExtras(node, entry.fx, this.lib.filterScale);
        slot.fx = entry.fx;
      }
      if (this.children[index] !== node) {
        this.addChildAt(node, index);
      }
      index += 1;
      node.label = entry.n || null;
      if (entry.n) {
        this.named[entry.n] = node;
      }
      if (placed) {
        this.lib.onPlace?.(node, this, entry.d, entry.at, entry.cx);
      }
    }
    for (const [depth, slot] of [...this.slots]) {
      if (!keep.has(depth)) {
        slot.node.destroy({ children: true });
        this.slots.delete(depth);
      }
    }
    this.applyMasks(list);
    return made;
  }

  // A mask entry hides everything outside its shape at the depths above it, up to its clip depth. Flash never
  // draws a mask layer, so one that nothing falls under is hidden instead of drawn like any other shape
  applyMasks(list) {
    let mask = null;
    const layers = [];
    const used = new Set();
    for (const entry of list) {
      const node = this.slots.get(entry.d).node;
      if (entry.clip) {
        // Pixi cuts out a container's mask by its whole outline, and by its see-through parts only when the mask is
        // a single picture
        const alpha = this.lib.alphaMasks.has(node.charId) && node.children.length === 1;
        mask = { node, until: entry.clip, shown: alpha ? node.children[0] : node };
        layers.push(node);
        continue;
      }
      const masked = mask && entry.d <= mask.until;
      if (masked && node.mask !== mask.shown) {
        node.mask = mask.shown;
      } else if (!masked && node.mask) {
        node.mask = null;
      }
      if (masked) {
        used.add(mask.node);
      }
    }
    for (const node of layers) {
      node.renderable = used.has(node);
    }
  }

  // Runs the first frame's script once the clip sits in its parent
  start() {
    if (this.started) {
      return;
    }
    this.started = true;
    const made = this.waiting;
    this.waiting = [];
    this.runFrame(this.frame, made);
  }

  // Arrive on a frame the way the player does: draw it, then run its sound and script, then its new parts' scripts
  enter(frame) {
    this.runFrame(frame, this.show(frame));
  }

  runFrame(frame, made) {
    for (const node of made) {
      if (node instanceof TextField && !node.destroyed) {
        node.bind(this);
      }
    }
    const sound = this.def.a?.[frame];
    if (sound && this.lib.onSound) {
      this.lib.onSound(sound[0], sound[1]);
    }
    let moved = false;
    for (const action of this.def.s?.[frame] ?? []) {
      if (this.run(action)) {
        moved = true;
        break;
      }
    }
    if (!moved && this.def.code?.includes(frame)) {
      this.lib.scripts.get(this.charId)?.(this, frame);
    }
    for (const node of made) {
      if (!node.destroyed) {
        node.start?.();
      }
    }
  }

  // A frame number kept inside the timeline, as Flash does when a script asks for one past the end
  clampFrame(frame) {
    return Math.min(this.def.n, Math.max(1, frame));
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
        this.enter(this.lib.choose?.(a) ?? a[Math.floor(this.lib.random() * a.length)]);
        return true;
      case "rstop":
        this.playing = false;
        this.show(this.clampFrame(pick(a, b)));
        return true;
      case "rplay":
        this.playing = true;
        this.enter(this.clampFrame(pick(a, b)));
        return true;
      case "stopat":
        this.gotoAndStop(a);
        return true;
      case "remove":
        this.removeMovieClip();
        return true;
      case "removeparent":
        this.parentClip?.removeMovieClip();
        return true;
      default: {
        const hook = this.onHook ?? this.lib.onHook;
        if (!hook?.(kind, a, this, action) && kind === "parentstop") {
          this.parentClip?.gotoAndStop(a);
        }
        return false;
      }
    }
  }

  // A frame label's frame number. (Pixi's own "label" is the clip's instance name, which find() reads)
  frameOf(name) {
    return this.def.labels?.[name] ?? null;
  }

  // Flash's gotoAndStop: a jump to the frame already showing changes nothing. The playhead stops before the frame's
  // script runs, so a play() in that script starts it again, as in Flash (the art's walk and struggle loops rely on it)
  gotoAndStop(target) {
    const frame = typeof target === "string" ? this.frameOf(target) : target;
    this.playing = false;
    if (frame && frame !== this.frame) {
      this.jump(Math.min(frame, this.def.n));
    }
  }

  gotoAndPlay(target) {
    const frame = typeof target === "string" ? this.frameOf(target) : target;
    this.playing = true;
    if (frame) {
      this.jump(Math.min(frame, this.def.n));
    }
  }

  // Moves the playhead. A clip whose first frame script hasn't run yet (its load handler jumps) only moves, and
  // start() runs the script of the frame it lands on, once
  jump(frame) {
    if (this.started) {
      this.enter(frame);
    } else {
      const made = this.show(frame);
      // Parts the old frame made and the new one kept still wait for their first script
      this.waiting = [...this.waiting.filter((node) => !node.destroyed), ...made];
    }
  }

  play() {
    this.playing = true;
  }

  stop() {
    this.playing = false;
  }

  // ---------- Attached clips ----------

  // Flash's attachMovie: a clip on top of the timeline's parts, stepping with this one
  attach(node, name = null) {
    node.label = name;
    for (let up = this; up; up = up.parent) {
      if (up instanceof Clip) {
        up.lively = true;
      }
    }
    this.attached.add(node);
    this.addChild(node);
    node.start?.();
    return node;
  }

  // Flash's removeMovieClip: the clip disappears, and an attached one is dropped at the end of its parent's tick
  removeMovieClip() {
    this.removed = true;
    this.playing = false;
    this.visible = false;
  }

  // ---------- The pointer ----------

  // The original's onPress, onRelease, onReleaseOutside, onRollOver and onRollOut, as functions or null. A clip
  // with any of them takes the pointer over its own bounds, and the parts inside it no longer do, as in Flash
  setHandler(name, handler) {
    this.handlers[name] = handler;
    if (this.listening) {
      return;
    }
    this.listening = true;
    this.eventMode = "static";
    this.interactiveChildren = false;
    this.cursor = this.hand ? "pointer" : "default";
    this.hitArea = {
      contains: (x, y) => {
        const bounds = this.getLocalBounds();
        return x >= bounds.minX && x <= bounds.maxX && y >= bounds.minY && y <= bounds.maxY;
      },
    };
    for (const [handlerName, event] of Object.entries(PRESS_EVENTS)) {
      this.on(event, (e) => {
        // As in Flash, a pointer that went down somewhere else and comes up here is not this clip's release (a tap
        // on a world button that opens a panel never presses the panel's button under the finger)
        if (handlerName === "onRelease" && this.lib.pressed.get(e.pointerId) !== this) {
          return;
        }
        // A press handler may start a drag, which needs to know where the pointer is
        this.lib.pointer = { x: e.global.x, y: e.global.y };
        this.handlers[handlerName]?.(e);
      });
    }
  }

  // Flash's useHandCursor
  set useHandCursor(on) {
    this.hand = on;
    if (this.listening) {
      this.cursor = on ? "pointer" : "default";
    }
  }

  get useHandCursor() {
    return this.hand;
  }

  // Flash's startDrag: the clip follows the pointer, kept inside [left, top, right, bottom] of its parent. With
  // lockCenter its own origin sits under the pointer, otherwise it keeps where it was grabbed
  startDrag(lockCenter = false, bounds = null) {
    const at = this.parent.toLocal(this.lib.pointer);
    this.lib.drag = {
      clip: this,
      bounds,
      dx: lockCenter ? 0 : this.x - at.x,
      dy: lockCenter ? 0 : this.y - at.y,
    };
    this.lib.moveDrag();
  }

  stopDrag() {
    if (this.lib.drag?.clip === this) {
      this.lib.drag = null;
    }
  }

  // The page knows nothing will change this clip again (a body that has stopped falling), so once every part has
  // stopped playing it is drawn from one cached picture and no longer stepped. False while a part still plays
  freeze(resolution) {
    if (!isSettled(this)) {
      return false;
    }
    this.frozen = true;
    this.cacheAsTexture({ resolution });
    return true;
  }

  // One tick of the game's clock (lib.fps a second): this timeline steps, then every part that was already here steps
  advance() {
    if (this.frozen) {
      return;
    }
    if (this.fresh) {
      this.fresh = false;
      return;
    }
    if (this.inert && !this.lively && !this.onEnterFrame) {
      return;
    }
    if (this.playing && !this.removed && this.def.n > 1) {
      this.enter(this.frame >= this.def.n ? 1 : this.frame + 1);
    }
    // A one-frame timeline's parts never change, so they are stepped as they stand; a longer one's may change while
    // its parts step, and only the parts there when the step began take it
    for (const slot of this.def.n > 1 ? [...this.slots.values()] : this.slots.values()) {
      if (slot.steps && !slot.node.destroyed) {
        slot.node.advance();
      }
    }
    if (this.attached.size > 0) {
      this.advanceAttached();
    }
    if (!this.destroyed) {
      this.onEnterFrame?.();
    }
  }

  advanceAttached() {
    for (const node of [...this.attached]) {
      if (node.removed || node.destroyed) {
        this.attached.delete(node);
        if (!node.destroyed) {
          node.destroy({ children: true });
        }
      } else {
        node.advance?.();
      }
    }
  }
}
