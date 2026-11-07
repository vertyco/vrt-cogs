// All In: a lit prize wheel on a brass stand in the casino's hall. All In is solo and each spin is private, so the
// wheel is the viewer's own, with their name on the stand's plate. One gold slice is the win: its share of the wheel is
// the true chance, 1 in (multiplier + 2), so it thins as the multiplier grows, and it redraws as the tray's multiplier
// changes. The bot decides each spin; the wheel turns several times, ticks against the pointer as it slows, and stops
// where the bot's answer says. The scene contract is the comment at the top of the stand-in scene.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { money } from "../format.js";
import { NAME_MAX, shortName } from "../lobby.js";
import { loadArt, sparkle } from "./art.js";
import { fit, fitted, wait } from "./kit.js";

const WIDTH = 560;
const HEIGHT = 700;
// The hall is bigger than the scene so a letterbox shows more hall, not black
const BACKDROP = { width: 1560, height: 1040, y: 350 };
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const INK = 0x1a0f08;
const MAROON = 0x4e0a10;
const RED = 0x7d111b;
const RED_DARK = 0x62101a;

// The wheel, in scene pixels: its middle, the brass rim's outer edge, the painted face inside it, the ring of bulbs,
// the ring of pegs the pointer ticks against, and the hub
const CENTER = { x: 280, y: 262 };
const RIM = 206;
const FACE = 176;
const BULB_RING = 191;
const BULBS = 28;
const PEG_RING = 165;
const HUB = 31;
// The pointer hangs from a cap just above the rim and reaches past the pegs
const POINTER_AT = -RIM - 2;
const POINTER_LENGTH = RIM + 2 - (PEG_RING - 9);
// stand.png is drawn at STAND_SCALE. Measured in its pixels: where the bottom of the wheel rests, and the name plate's
// middle, width and height
const STAND_SCALE = 0.78;
const SEAT = { x: 320, y: 168 };
const PLATE = { x: 320, y: 375, width: 192, height: 44 };
const STAND_AT = { x: CENTER.x - SEAT.x * STAND_SCALE, y: CENTER.y + RIM - SEAT.y * STAND_SCALE };
// The name on the plate: its size, and the smallest it may shrink to on screen, in CSS pixels, before it is cut instead
const PLATE_FONT = 23;
const PLATE_MIN_PX = 10;
// The band of stand between the wheel's rim and the plate, where the result card covers nothing that matters
const CARD_BAND = {
  top: CENTER.y + RIM + 4,
  bottom: STAND_AT.y + (PLATE.y - PLATE.height / 2) * STAND_SCALE - 4,
};

// The red part of the wheel is split into this many slices, so the pointer has pegs to tick against
const RED_SLICES = 11;
// A gold slice this narrow (degrees) or narrower has its label on a tag outside the rim. The tag keeps this far round
// from the pointer, on its right, so the pointer never covers it, and its line ends on the slice this far from the
// wheel's middle, below the pointer's tip
const LABEL_INSIDE = 24;
const CLEAR_DEGREES = 19;
const TAG_LINE_END = PEG_RING - 40;
// The gold slice's color along its length, [share of the face's radius, color]: brightest two thirds of the way out,
// deeper toward the hub and the rim. It is painted in GOLD_STEPS thin bands, too close in color to be seen
const GOLD_STOPS = [
  [0.15, 0xb98928],
  [0.42, 0xe4b54b],
  [0.66, 0xf8d97f],
  [0.84, 0xe8b746],
  [0.95, 0xc58d24],
  [1, 0x9a6815],
];
const GOLD_STEPS = 24;
// The glow past the gold slice's edges: how far it reaches, in degrees, in how many fading rings
const GLOW_DEGREES = 1;
const GLOW_RINGS = 4;
// The fine gold lines between the slices, and the pegs' gold
const SPOKE = 0xc9a043;
const PEG_GOLD = 0xe9c66a;
// Racing, the wheel covers about a slice a frame, so sharp spokes and pegs would seem to stand still or flicker. They
// smear back over the ground the wheel covers in SMEAR_MS (at most SMEAR_MAX degrees), in SMEAR_BANDS bands that fade
// toward the back, and the sharp ones fade as the smear grows. It is redrawn only when its length changes by a degree
const SMEAR_MS = 20;
const SMEAR_MAX = 26;
const SMEAR_BANDS = 6;

// A spin, in ms: the wheel rocks back as a hand takes it, is pushed up to speed, then slows to its stop. It finishes
// inside All In's pull pace (3.0 s) with a moment to spare before the bot's result
const WIND_MS = 170;
const PUSH_MS = 260;
const SPIN_MS = 2750;
const WIND_BACK = 7;
const TURNS = 3;
// The slice's width eases to a new multiplier over RESIZE_MS
const RESIZE_MS = 220;
// The pointer: how far a peg bends it (radians), over how many degrees a peg pushes it before slipping past, and how
// it springs back. Ticks are at least TICK_GAP_MS apart
const FLAP = 0.32;
const CONTACT = 5;
const FLAP_SETTLE_MS = 90;
const FLAP_WOBBLE_MS = 150;
const TICK_GAP_MS = 38;
// The bulbs chase one step for every CHASE_DEGREES the wheel turns, so they slow with it
const CHASE_DEGREES = 9;
const WIN_MS = 2000;
const LOSE_MS = 1400;

function mod(value, size) {
  return ((value % size) + size) % size;
}

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

function text(value, style) {
  const piece = new Text({ text: value, style, resolution: 2 });
  piece.anchor.set(0.5);
  return piece;
}

// Shrinks a text to fit a box, never growing it past its size
function fitText(piece, width, height = Infinity) {
  piece.scale.set(1);
  const scale = Math.min(1, width / Math.max(1, piece.width), height / Math.max(1, piece.height));
  piece.scale.set(scale);
}

// A soft round glow made of rings that fade outward
function glow(radius, color, strength = 0.5) {
  const piece = new Graphics();
  for (let ring = 16; ring >= 1; ring -= 1) {
    piece.circle(0, 0, (radius * ring) / 16).fill({ color, alpha: strength * (1 - ring / 17) * 0.18 });
  }
  piece.blendMode = "add";
  return piece;
}

// ---- The wheel's math, shared with the tests ----

// The multiplier the wheel draws: under 2, or not a number, counts as 2
function counted(multiplier) {
  const value = Number(multiplier);
  return Number.isFinite(value) && value >= 2 ? value : 2;
}

// The gold slice's width in degrees: its share of the wheel is the chance to win, 1 in (multiplier + 2). A thin
// slice is never drawn under 2 degrees, so it can always be seen
export function sliceDegrees(multiplier) {
  return Math.max(2, 360 / (counted(multiplier) + 2));
}

// Where the pointer stops, in degrees clockwise from the gold slice's middle, 0 to 360. A win stops inside the slice,
// at least 15% of its width from either edge; a loss stops in the red, at least 2 degrees clear of the slice
export function landing(win, multiplier, random) {
  const width = sliceDegrees(multiplier);
  const share = clamp(Number(random) || 0, 0, 1);
  if (win) {
    return mod((share - 0.5) * 0.7 * width, 360);
  }
  return width / 2 + 2 + share * (360 - width - 4);
}

// The wheel's turn `t` ms into a spin from `from` that ends `travel` degrees further on
function spinAngle(from, travel, t) {
  if (t <= WIND_MS) {
    return from - (WIND_BACK * (1 - Math.cos((Math.PI * t) / WIND_MS))) / 2;
  }
  const start = from - WIND_BACK;
  const coast = SPIN_MS - WIND_MS - PUSH_MS;
  // The top speed, in degrees a ms, that covers the whole way: speeding up evenly, then slowing ever more gently
  const top = (travel + WIND_BACK) / (PUSH_MS / 2 + coast / 3);
  const since = t - WIND_MS;
  if (since <= PUSH_MS) {
    return start + (top * since * since) / (2 * PUSH_MS);
  }
  const k = Math.min(1, (since - PUSH_MS) / coast);
  return start + (top * PUSH_MS) / 2 + ((top * coast) / 3) * (1 - (1 - k) ** 3);
}

// ---- Drawing ----

// Angles on the wheel are degrees clockwise from the top, the way the pointer reads them
function toRadians(degrees) {
  return ((degrees - 90) * Math.PI) / 180;
}

function onCircle(degrees, radius) {
  const angle = toRadians(degrees);
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

// A color part of the way from one to another
function mix(from, to, k) {
  const channel = (shift) => {
    const low = (from >> shift) & 255;
    return Math.round(low + (((to >> shift) & 255) - low) * k);
  };
  return (channel(16) << 16) | (channel(8) << 8) | channel(0);
}

// The gold at a share of the face's radius
function goldAt(share) {
  const next = GOLD_STOPS.findIndex(([at]) => at >= share);
  if (next <= 0) {
    return GOLD_STOPS[Math.max(0, next)][1];
  }
  const [from, low] = GOLD_STOPS[next - 1];
  const [to, high] = GOLD_STOPS[next];
  return mix(low, high, (share - from) / (to - from));
}

// A slice of a ring from `inner` to `outer`, between two angles, added to the drawing's path
function wedge(drawing, inner, outer, from, to) {
  const start = toRadians(from);
  const end = toRadians(to);
  drawing.moveTo(Math.cos(start) * inner, Math.sin(start) * inner);
  drawing.arc(0, 0, outer, start, end);
  if (inner > 0) {
    drawing.arc(0, 0, inner, end, start, true);
  }
  return drawing.closePath();
}

// The red slices between the gold slice's edges, each [from, to]
function redSlices(width) {
  const size = (360 - width) / RED_SLICES;
  return Array.from({ length: RED_SLICES }, (_, index) => [width / 2 + index * size, width / 2 + (index + 1) * size]);
}

// The pegs on the slices' edges, each [angle, how much it shows]. The two on the gold slice's edges fade as the slice
// thins, so they never hide a sliver
function pegsFor(width) {
  const size = (360 - width) / RED_SLICES;
  const edge = clamp((width - 6) / 6, 0, 1);
  return Array.from({ length: RED_SLICES + 1 }, (_, index) => [
    width / 2 + index * size,
    index === 0 || index === RED_SLICES ? edge : 1,
  ]);
}

// The painted face: dark red slices with fine gold lines between them and the gold slice centered at the top
function drawFace(face, width) {
  face.clear();
  face.circle(0, 0, FACE).fill(0x2a0508);
  redSlices(width).forEach(([from, to], index) => wedge(face, 0, FACE, from, to).fill(index % 2 ? RED_DARK : RED));
  for (let step = 0; step < GOLD_STEPS; step += 1) {
    const share = 1 - (step / GOLD_STEPS) * 0.85;
    wedge(face, 0, FACE * share, -width / 2, width / 2).fill(goldAt(share));
  }
  // A brighter ridge down the slice's middle, as if it were embossed
  wedge(face, HUB, FACE * 0.97, -width * 0.16, width * 0.16).fill({ color: 0xfff4c4, alpha: 0.16 });
}

function drawSpokes(spokes, width) {
  spokes.clear();
  for (const [angle] of pegsFor(width)) {
    const inner = onCircle(angle, HUB);
    const outer = onCircle(angle, FACE);
    spokes.moveTo(inner.x, inner.y).lineTo(outer.x, outer.y);
  }
  spokes.stroke({ width: 1.6, color: SPOKE, alpha: 0.9 });
}

// The spokes' and pegs' smear, `arc` degrees long behind them (ahead of them for a negative arc, as the wheel rocks
// back), brightest next to them
function drawSmear(smear, width, arc) {
  smear.clear();
  const amount = Math.abs(arc) / SMEAR_MAX;
  if (amount === 0) {
    return;
  }
  for (const [angle, shown] of pegsFor(width)) {
    for (let band = 0; band < SMEAR_BANDS; band += 1) {
      const near = angle - (arc * band) / SMEAR_BANDS;
      const far = angle - (arc * (band + 1)) / SMEAR_BANDS;
      const [from, to] = [Math.min(near, far), Math.max(near, far)];
      const fade = amount * (1 - band / SMEAR_BANDS);
      wedge(smear, HUB, FACE, from, to).fill({ color: SPOKE, alpha: 0.4 * fade });
      if (shown > 0) {
        wedge(smear, PEG_RING - 3.5, PEG_RING + 3.5, from, to).fill({ color: PEG_GOLD, alpha: 0.6 * fade * shown });
      }
    }
  }
}

// The slice's gold glow just past its edges, fading out within GLOW_DEGREES, so even a 2 degree sliver shines. A loss
// stops at least 2 degrees clear of the slice, so the red where it stops never takes the glow's gold. A sliver is lit
// bright inside too, so it reads as the slice rather than part of the pointer
function drawGlow(halo, width) {
  halo.clear();
  const edge = width / 2;
  for (let ring = 1; ring <= GLOW_RINGS; ring += 1) {
    const spread = edge + (ring * GLOW_DEGREES) / GLOW_RINGS;
    wedge(halo, HUB + 6, FACE + 3, edge, spread).fill({ color: 0xffd66b, alpha: 0.1 });
    wedge(halo, HUB + 6, FACE + 3, -spread, -edge).fill({ color: 0xffd66b, alpha: 0.1 });
  }
  if (width < 8) {
    wedge(halo, HUB + 6, FACE + 3, -edge, edge).fill({ color: 0xfff0b8, alpha: 0.9 });
  }
}

// The gold flash that lights the slice up on a win, at least 8 degrees wide so a sliver's win can be seen
function drawFlare(flare, width) {
  const spread = Math.max(width, 8) / 2;
  flare.clear();
  wedge(flare, HUB, FACE + 4, -spread, spread).fill({ color: 0xffc23a, alpha: 0.9 });
}

function drawPegs(pegs, width) {
  pegs.clear();
  for (const [angle, shown] of pegsFor(width)) {
    if (shown <= 0) {
      continue;
    }
    const { x, y } = onCircle(angle, PEG_RING);
    pegs.circle(x + 1, y + 1.5, 4).fill({ color: 0x000000, alpha: 0.35 * shown });
    pegs.circle(x, y, 4).fill({ color: 0x6e4a12, alpha: shown });
    pegs.circle(x, y, 3).fill({ color: PEG_GOLD, alpha: shown });
    pegs.circle(x - 1, y - 1, 1.2).fill({ color: 0xffffff, alpha: 0.8 * shown });
  }
}

// The gold slice's own label, painted on it, or nothing when the slice is too thin and the tag shows it instead
function placeLabel(label, width) {
  label.visible = width >= LABEL_INSIDE;
  if (!label.visible) {
    return;
  }
  // Further out on a narrower slice, where it is wider
  const radius = FACE * (0.62 + 0.13 * clamp((60 - width) / 36, 0, 1));
  const room = 2 * radius * Math.sin((width * Math.PI) / 360) * 0.78;
  label.position.set(0, -radius);
  fitText(label, room, (FACE - HUB) * 0.36);
}

// ---- Building the scene ----

async function loadWheelArt() {
  const base = new URL("../art/allin/", import.meta.url).href;
  const [hall, stand] = await Promise.all(
    ["hall.jpg", "stand.png"].map((file) => Assets.load({ src: base + file, data: { autoGenerateMipmaps: true } })),
  );
  return { hall, stand };
}

function makeHall(texture) {
  const hall = new Container();
  const picture = new Sprite(texture);
  picture.anchor.set(0.5);
  picture.position.set(WIDTH / 2, BACKDROP.y);
  picture.width = BACKDROP.width;
  picture.height = BACKDROP.height;
  // The hall a little darker, so the lit wheel stands out from it, and warm light spilling around the wheel
  const shade = new Graphics()
    .rect(WIDTH / 2 - BACKDROP.width / 2, BACKDROP.y - BACKDROP.height / 2, BACKDROP.width, BACKDROP.height)
    .fill({ color: 0x0a0402, alpha: 0.28 });
  const light = glow(RIM * 1.75, 0xffc76a, 0.55);
  light.position.set(CENTER.x, CENTER.y);
  hall.addChild(picture, shade, light);
  return hall;
}

// The stand, its shadow on the carpet, and the player's name engraved on its plate
function makeStand(texture) {
  const stand = new Container();
  const floor = new Graphics();
  const bottom = STAND_AT.y + texture.height * STAND_SCALE - 6;
  for (let ring = 10; ring >= 1; ring -= 1) {
    floor.ellipse(CENTER.x, bottom, 210 + ring * 9, 14 + ring * 2.2).fill({ color: 0x000000, alpha: 0.06 });
  }
  const picture = new Sprite(texture);
  picture.position.set(STAND_AT.x, STAND_AT.y);
  picture.scale.set(STAND_SCALE);
  stand.plate = text("", {
    fontFamily: MARKS,
    fontWeight: "700",
    fontSize: PLATE_FONT,
    fill: 0x3a2306,
    letterSpacing: 1,
    dropShadow: { color: 0xfff0b8, alpha: 0.5, blur: 0, distance: 1, angle: Math.PI / 2 },
  });
  stand.plate.label = "plate";
  stand.plate.position.set(STAND_AT.x + PLATE.x * STAND_SCALE, STAND_AT.y + PLATE.y * STAND_SCALE);
  stand.addChild(floor, picture, stand.plate);
  return stand;
}

// The wheel's soft shadow on the stand and the hall behind it
function makeShadow() {
  const shadow = new Graphics();
  for (let ring = 10; ring >= 0; ring -= 1) {
    shadow.circle(0, 0, RIM + ring * 2.2).fill({ color: 0x000000, alpha: 0.055 });
  }
  shadow.position.set(CENTER.x + 9, CENTER.y + 16);
  return shadow;
}

// The brass rim, lit from the top left. The face covers its middle
function makeRim() {
  const rim = new Graphics({ label: "rim" });
  const bands = [
    [RIM + 2.5, 0x24140a],
    [RIM, 0x7d5716],
    [RIM - 2, 0xc89a3c],
    [RIM - 5, 0xf1d688],
    [RIM - 8, 0xd8aa45],
    [RIM - 14, 0xb98a2e],
    [RIM - 22, 0x9c6f20],
    [FACE + 4, 0x6b4612],
    [FACE + 1.5, 0x2a1606],
  ];
  for (const [radius, color] of bands) {
    rim.circle(0, 0, radius).fill(color);
  }
  const arc = (from, to, color, alpha) => {
    const start = Math.PI * from;
    rim.moveTo(Math.cos(start) * (RIM - 5), Math.sin(start) * (RIM - 5));
    rim.arc(0, 0, RIM - 5, start, Math.PI * to).stroke({ width: 4, color, alpha });
  };
  arc(0.95, 1.6, 0xfff6d0, 0.5);
  arc(-0.05, 0.6, 0x2a1606, 0.35);
  return rim;
}

// Light that stays put while the face turns under it: a shadow the rim casts round the face's edge, darker paint by
// the hub, and a soft shine at the top left
function makeShade() {
  const shade = new Graphics();
  for (let ring = 0; ring < 14; ring += 1) {
    shade.circle(0, 0, FACE - ring * 2 - 1).stroke({ width: 2, color: 0x000000, alpha: 0.3 * (1 - ring / 14) ** 2 });
  }
  for (let ring = 0; ring < 10; ring += 1) {
    shade.circle(0, 0, HUB + 4 + ring * 3).stroke({ width: 3, color: 0x000000, alpha: 0.16 * (1 - ring / 10) });
  }
  for (let ring = 1; ring <= 6; ring += 1) {
    const size = 1 - ring * 0.1;
    shade.ellipse(-FACE * 0.3, -FACE * 0.42, FACE * 0.55 * size, FACE * 0.3 * size);
    shade.fill({ color: 0xffffff, alpha: 0.022 });
  }
  return shade;
}

// Each bulb: a dark socket, its light, and a glow round it. Placed half a step off the top, so none sits under the
// pointer
function makeBulbs() {
  return Array.from({ length: BULBS }, (_, index) => {
    const bulb = new Container();
    const { x, y } = onCircle(((index + 0.5) * 360) / BULBS, BULB_RING);
    bulb.position.set(x, y);
    const socket = new Graphics().circle(0, 0, 8).fill(0x3a2208).circle(0, 0, 6.6).fill(0x70501f);
    bulb.on = new Graphics().circle(0, 0, 6).fill(0xfff4d4).circle(-1.7, -1.9, 2.1).fill(0xffffff);
    bulb.halo = glow(19, 0xffd88a, 0.95);
    bulb.addChild(socket, bulb.halo, bulb.on);
    return bulb;
  });
}

function makeHub() {
  const hub = new Graphics();
  hub.circle(2, 3, HUB + 3).fill({ color: 0x000000, alpha: 0.4 });
  const rings = [
    [HUB + 2, 0x3a2207],
    [HUB, 0x9b6d1e],
    [HUB - 3, 0xe8c45f],
    [HUB - 7, 0xc6963a],
    [HUB - 12, 0xf2d482],
    [HUB - 19, 0xbb8b30],
    [HUB - 23, 0xe3bd5a],
  ];
  for (const [radius, color] of rings) {
    hub.circle(0, 0, radius).fill(color);
  }
  hub.ellipse(-HUB * 0.3, -HUB * 0.36, HUB * 0.42, HUB * 0.24).fill({ color: 0xffffff, alpha: 0.35 });
  return hub;
}

// The pointer: a brass blade hanging from a cap with a ruby in it, its shadow falling on the face. It turns on the cap
function makePointer() {
  const pointer = new Container({ label: "pointer" });
  pointer.position.set(CENTER.x, CENTER.y + POINTER_AT);
  const blade = (dx, dy) =>
    new Graphics()
      .moveTo(-20 + dx, -4 + dy)
      .lineTo(20 + dx, -4 + dy)
      .lineTo(2.5 + dx, POINTER_LENGTH + dy)
      .lineTo(-2.5 + dx, POINTER_LENGTH + dy)
      .closePath();
  const shadow = blade(4, 7).fill({ color: 0x000000, alpha: 0.4 });
  const body = blade(0, 0).fill(0xc99a3b).stroke({ width: 2, color: 0x5a3a0c });
  const lit = new Graphics()
    .moveTo(-16, -2)
    .lineTo(0, -2)
    .lineTo(0, POINTER_LENGTH - 6)
    .closePath()
    .fill({ color: 0xfff1bd, alpha: 0.5 });
  const cap = new Graphics()
    .circle(1.5, 2.5, 17)
    .fill({ color: 0x000000, alpha: 0.35 })
    .circle(0, 0, 17)
    .fill(0x7a5214)
    .circle(0, 0, 14.5)
    .fill(0xe2b955)
    .circle(0, 0, 8)
    .fill(0x6e0a12)
    .circle(0, 0, 6.2)
    .fill(0xc8202f)
    .circle(-2.2, -2.2, 2.2)
    .fill({ color: 0xffffff, alpha: 0.8 });
  pointer.addChild(shadow, body, lit, cap);
  return pointer;
}

// The tag beside a thin slice: a gold pill with the multiplier, an arrow and a fine line to the slice
function makeTag() {
  const tag = new Container({ label: "tag" });
  tag.shape = new Graphics();
  tag.words = text("", { fontFamily: MARKS, fontWeight: "800", fontSize: 24, fill: MAROON });
  tag.addChild(tag.shape, tag.words);
  tag.alpha = 0;
  return tag;
}

// Draws the tag's pill, and its arrow and line toward `target` (in the tag's own space)
function drawTag(shape, half, target) {
  const length = Math.hypot(target.x, target.y) || 1;
  const way = { x: target.x / length, y: target.y / length };
  const edge = Math.min(half.x / Math.max(1e-6, Math.abs(way.x)), half.y / Math.max(1e-6, Math.abs(way.y)));
  const base = { x: way.x * edge, y: way.y * edge };
  const tip = { x: base.x + way.x * 10, y: base.y + way.y * 10 };
  const across = { x: -way.y * 7, y: way.x * 7 };
  shape.clear();
  if (length > edge + 14) {
    shape.moveTo(tip.x, tip.y).lineTo(target.x, target.y).stroke({ width: 1.6, color: GOLD_LIGHT, alpha: 0.95 });
    shape.circle(target.x, target.y, 2.6).fill(GOLD_LIGHT);
  }
  shape.roundRect(-half.x + 2, -half.y + 3, half.x * 2, half.y * 2, 9).fill({ color: 0x000000, alpha: 0.4 });
  shape
    .moveTo(base.x + across.x, base.y + across.y)
    .lineTo(tip.x, tip.y)
    .lineTo(base.x - across.x, base.y - across.y)
    .closePath()
    .fill(GOLD)
    .stroke({ width: 1.5, color: 0x6e4b10 });
  shape.roundRect(-half.x, -half.y, half.x * 2, half.y * 2, 9).fill(0xf0cf6c).stroke({ width: 2, color: 0x6e4b10 });
  shape.roundRect(-half.x + 3, -half.y + 3, half.x * 2 - 6, half.y - 3, 7).fill({ color: 0xfff6d6, alpha: 0.4 });
}

// Puts the tag just outside the rim beside the slice whose middle is at `angle`, upright, clear of the pointer (on its
// right when the slice is under it) and inside the scene
function placeTag(tag, angle) {
  const half = { x: tag.words.width / 2 + 13, y: 17 };
  let side = mod(angle + 180, 360) - 180;
  if (Math.abs(side) < CLEAR_DEGREES) {
    side = CLEAR_DEGREES;
  }
  const out = onCircle(side, 1);
  const reach = RIM + 8 + Math.abs(out.x) * half.x + Math.abs(out.y) * half.y;
  const x = clamp(CENTER.x + out.x * reach, half.x + 4, WIDTH - half.x - 4);
  const y = clamp(CENTER.y + out.y * reach, half.y + 4, HEIGHT - half.y - 4);
  tag.position.set(x, y);
  const end = onCircle(angle, TAG_LINE_END);
  tag.end = { x: CENTER.x + end.x - x, y: CENTER.y + end.y - y };
  drawTag(tag.shape, half, tag.end);
}

// How bright each bulb is, 0 to 1: a gentle shimmer at rest, a chase that turns with the wheel, a flashing win, and
// a loss that goes dark and comes back
function bulbLevel(mode, index, since, angle) {
  if (mode === "spin") {
    return mod(index - Math.floor(angle / CHASE_DEGREES), 4) < 2 ? 1 : 0.15;
  }
  if (mode === "win" && since < 1300) {
    return Math.floor(since / 110) % 2 ? 0.35 : 1;
  }
  if (mode === "win") {
    return mod(index - Math.floor(since / 45), 3) === 0 ? 1 : 0.3;
  }
  if (mode === "lose") {
    return 0.08 + 0.64 * clamp((since - 650) / 700, 0, 1);
  }
  return 0.72 + 0.14 * Math.sin(since / 650 + index * 0.85);
}

// ---- The scene ----

export async function createScene(stage) {
  await loadArt();
  const wheel = new PrizeWheel(stage, await loadWheelArt());
  return {
    show: () => wheel.showOwner(),
    play: (event) => wheel.play(event),
    result: (message) => wheel.result(message),
    preview: (value) => wheel.preview(value),
    layout: (width, height) => wheel.layout(width, height),
    resultSpot: () => wheel.resultSpot(),
    destroy: () => wheel.destroy(),
  };
}

class PrizeWheel {
  constructor(stage, art) {
    this.stage = stage;
    // The face's turn in degrees, clockwise; the pointer reads the face at -angle. At rest the gold slice starts under
    // the pointer
    this.angle = 0;
    // The multiplier drawn, the slice's width now, the tray's multiplier, and the width easing to a new one
    this.multiplier = 2;
    this.width = sliceDegrees(2);
    this.wanted = 2;
    this.resize = null;
    // The spin under way, and the win or loss being shown after one, with its timers
    this.spin = null;
    this.flourish = null;
    this.timers = [];
    this.lights = { mode: "rest", since: performance.now() };
    // The pointer's last kick from a peg, and when the last tick sounded
    this.flap = { at: 0, from: 0 };
    this.lastTick = 0;
    this.tagAt = null;
    // How long the spokes' smear is, in degrees
    this.smearArc = 0;
    // The viewer's whole name, and the room the scene has, in CSS pixels
    this.owner = "";
    this.space = { width: WIDTH, height: HEIGHT };
    this.closed = false;
    this.build(art);
    this.aim(this.multiplier);
    this.drawSlice();
    this.frame = () => this.tick(performance.now());
    stage.app.ticker.add(this.frame);
  }

  build(art) {
    this.root = fitted(WIDTH, HEIGHT);
    this.stage.root.addChild(this.root);
    this.stand = makeStand(art.stand);
    const wheel = new Container({ label: "wheel" });
    wheel.position.set(CENTER.x, CENTER.y);
    this.disc = new Container({ label: "disc" });
    this.face = new Graphics();
    // A faint copy of the face trailing just behind it, which smears the slices as the wheel races
    this.ghost = new Graphics(this.face.context);
    this.ghost.alpha = 0;
    this.smear = new Graphics({ label: "smear" });
    this.spokes = new Graphics({ label: "spokes" });
    this.halo = new Graphics({ label: "glow" });
    this.halo.blendMode = "add";
    this.flare = new Graphics();
    this.flare.blendMode = "add";
    this.flare.alpha = 0;
    this.pegs = new Graphics();
    this.label = text("", {
      fontFamily: MARKS,
      fontWeight: "900",
      fontSize: 56,
      fill: MAROON,
      letterSpacing: 1,
      dropShadow: { color: 0xfff2bd, alpha: 0.55, blur: 0, distance: 1.5, angle: Math.PI / 2 },
    });
    this.disc.addChild(this.face, this.ghost, this.smear, this.spokes, this.halo, this.flare, this.pegs, this.label);
    this.dim = new Graphics().circle(0, 0, RIM + 3).fill(INK);
    this.dim.alpha = 0;
    this.bulbs = makeBulbs();
    wheel.addChild(makeRim(), this.disc, makeShade(), this.dim, ...this.bulbs, makeHub());
    this.tag = makeTag();
    this.pointer = makePointer();
    this.sparks = new Container();
    this.root.addChild(makeHall(art.hall), this.stand, makeShadow(), wheel, this.tag, this.pointer, this.sparks);
  }

  // ---- The gold slice ----

  // Redraws the slice at this.width, with its label or its tag
  drawSlice() {
    drawFace(this.face, this.width);
    drawSpokes(this.spokes, this.width);
    drawSmear(this.smear, this.width, this.smearArc);
    drawGlow(this.halo, this.width);
    drawFlare(this.flare, this.width);
    drawPegs(this.pegs, this.width);
    placeLabel(this.label, this.width);
    this.pegList = pegsFor(this.width);
    this.tagAt = null;
  }

  // Shows a multiplier: the label at once, the slice easing to its width
  aim(multiplier, ms = RESIZE_MS) {
    this.multiplier = counted(multiplier);
    const words = `x${money(this.multiplier)}`;
    if (this.label.text !== words) {
      this.label.text = words;
      this.tag.words.text = words;
    }
    const width = sliceDegrees(this.multiplier);
    this.resize = { from: this.width, to: width, start: performance.now(), ms };
  }

  resizeAt(now) {
    if (!this.resize) {
      return;
    }
    const { from, to, start, ms } = this.resize;
    const k = clamp((now - start) / Math.max(1, ms), 0, 1);
    this.width = from + (to - from) * (1 - (1 - k) ** 3);
    if (k >= 1) {
      this.resize = null;
    }
    this.drawSlice();
  }

  // The tag shows for a thin slice while the wheel stands still, fading out as it spins
  showTag() {
    const wanted = this.width < LABEL_INSIDE && !this.spin ? 1 : 0;
    this.tag.alpha += clamp(wanted - this.tag.alpha, -0.12, 0.08);
    this.tag.visible = this.tag.alpha > 0.01;
    if (this.tag.visible && this.tagAt !== this.angle) {
      this.tagAt = this.angle;
      placeTag(this.tag, this.angle);
    }
  }

  // ---- A spin ----

  async play(event) {
    if (event.kind !== "pull") {
      return;
    }
    this.calm();
    this.aim(event.multiplier, 120);
    const stop = landing(event.win, event.multiplier, Math.random());
    const from = mod(this.angle, 360);
    const spin = { start: performance.now(), from, travel: TURNS * 360 + mod(-stop - from, 360), at: null };
    this.spin = spin;
    this.setLights("spin");
    this.stage.sound.play("allin");
    try {
      await wait(SPIN_MS);
    } finally {
      if (this.spin === spin) {
        this.endSpin(spin);
      }
    }
  }

  // The wheel stops exactly where the spin ends, and the pointer springs off its last peg
  endSpin(spin) {
    this.spin = null;
    if (this.closed) {
      return;
    }
    this.turnTo(mod(spin.from + spin.travel, 360));
    this.ghost.alpha = 0;
    this.smearBy(0);
    this.flap = { at: performance.now(), from: -this.pointer.rotation };
    if (!this.flourish) {
      this.setLights("rest");
    }
  }

  turnTo(angle) {
    this.angle = angle;
    this.disc.angle = angle;
  }

  // Turns the wheel to where the spin is now, smears it by its speed, and ticks for each peg that passed the pointer
  turn(now) {
    const spin = this.spin;
    const before = this.angle;
    const after = spinAngle(spin.from, spin.travel, Math.min(SPIN_MS, now - spin.start));
    const velocity = spin.at === null ? 0 : (after - before) / Math.max(1, now - spin.at);
    const speed = Math.abs(velocity);
    spin.at = now;
    this.turnTo(after);
    this.ghost.angle = -Math.min(14, speed * 10);
    this.ghost.alpha = Math.min(0.45, speed * 0.32);
    this.smearBy(velocity);
    let passed = 0;
    for (const [at, shown] of this.pegList) {
      if (shown >= 0.5) {
        passed += Math.abs(Math.floor((at + after) / 360) - Math.floor((at + before) / 360));
      }
    }
    if (passed) {
      this.flap = { at: now, from: FLAP };
      if (now - this.lastTick >= TICK_GAP_MS) {
        this.lastTick = now;
        this.stage.sound.play("tick");
      }
    }
  }

  smearBy(velocity) {
    const arc = Math.round(clamp(velocity * SMEAR_MS, -SMEAR_MAX, SMEAR_MAX));
    if (arc === this.smearArc) {
      return;
    }
    this.smearArc = arc;
    drawSmear(this.smear, this.width, arc);
    const amount = Math.abs(arc) / SMEAR_MAX;
    this.spokes.alpha = 1 - 0.7 * amount;
    this.pegs.alpha = 1 - 0.5 * amount;
  }

  // The pointer bends as a peg pushes its tip, snaps back as the peg slips past and wobbles to rest
  swing(now) {
    const since = now - this.flap.at;
    let lean = this.flap.from * Math.exp(-since / FLAP_SETTLE_MS) * Math.cos((since / FLAP_WOBBLE_MS) * Math.PI * 2);
    if (this.spin) {
      for (const [at, shown] of this.pegList) {
        const near = mod(at + this.angle + 180, 360) - 180;
        if (shown >= 0.5 && near > -CONTACT && near <= 0) {
          lean = Math.max(lean, FLAP * (1 + near / CONTACT));
        }
      }
    }
    this.pointer.rotation = -lean;
  }

  // ---- Every frame ----

  setLights(mode) {
    this.lights = { mode, since: performance.now() };
  }

  tick(now) {
    if (this.spin) {
      this.turn(now);
    }
    this.resizeAt(now);
    this.swing(now);
    this.showTag();
    const { mode, since } = this.lights;
    this.bulbs.forEach((bulb, index) => {
      const level = bulbLevel(mode, index, now - since, this.angle);
      bulb.on.alpha = 0.25 + 0.75 * level;
      bulb.halo.alpha = level;
    });
    this.showAt(now);
  }

  // The slice breathes gently at rest; a win flares it, a loss dims the wheel. Either show ends by itself
  showAt(now) {
    const show = this.flourish;
    const since = show ? now - show.since : 0;
    this.halo.alpha = 0.6 + 0.25 * Math.sin(now / 900);
    if (show?.kind === "win") {
      this.halo.alpha = 1;
      this.flare.alpha = Math.max(0, 1 - since / WIN_MS) * (0.5 + 0.5 * Math.cos(since / 95));
    } else if (show?.kind === "lose") {
      this.dim.alpha = 0.5 * clamp(since / 200, 0, 1) * clamp((LOSE_MS - since) / 700, 0, 1);
    }
    if (show && since >= (show.kind === "win" ? WIN_MS : LOSE_MS)) {
      this.calm();
      this.aim(this.wanted);
    }
  }

  // ---- After a spin ----

  result(message) {
    if (!["win", "lose"].includes(message.outcome)) {
      return;
    }
    this.calm();
    this.flourish = { kind: message.outcome, since: performance.now() };
    this.setLights(message.outcome);
    if (message.outcome === "win") {
      this.burst();
    }
  }

  // The casino's sparkle bursts from the gold slice under the pointer, then either side of it along the rim
  burst() {
    const bursts = [
      [0, 0, FACE * 0.72],
      [180, -38, RIM],
      [340, 38, RIM],
    ];
    this.timers = bursts.map(([delay, angle, radius]) =>
      setTimeout(() => {
        if (!this.closed && this.flourish?.kind === "win") {
          const { x, y } = onCircle(angle, radius);
          sparkle(this.sparks, CENTER.x + x, CENTER.y + y, 1000);
        }
      }, delay),
    );
  }

  // Ends whatever win or loss is showing
  calm() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    this.flourish = null;
    this.flare.alpha = 0;
    this.dim.alpha = 0;
    if (!this.spin) {
      this.setLights("rest");
    }
  }

  // ---- The page ----

  showOwner() {
    const me = this.stage.me();
    this.owner = me ? this.stage.nameOf(me) : "";
    this.fitPlate();
  }

  // The name shrinks to fit the plate, but never under PLATE_MIN_PX on screen: a name still too long is cut by whole
  // characters
  fitPlate() {
    const plate = this.stand.plate;
    const least = Math.min(1, PLATE_MIN_PX / (PLATE_FONT * this.root.scale.y));
    for (let most = NAME_MAX; most >= 2; most -= 1) {
      plate.text = shortName(this.owner, most);
      fitText(plate, PLATE.width * STAND_SCALE);
      if (plate.scale.x >= least) {
        return;
      }
    }
  }

  layout(width, height) {
    this.space = { width, height };
    fit(this.root, width, height);
    this.fitPlate();
  }

  // The result card goes on the stand between the wheel and the plate, in CSS pixels of the scene's room
  resultSpot() {
    const { y } = this.root.position;
    const scale = this.root.scale.y;
    return { left: 0, top: y + CARD_BAND.top * scale, right: this.space.width, bottom: y + CARD_BAND.bottom * scale };
  }

  // The tray's multiplier. A spin or the show after it keeps the slice it was played with, then the wheel moves on to
  // the latest multiplier
  preview(value) {
    this.wanted = value;
    if (!this.spin && !this.flourish) {
      this.aim(value);
    }
  }

  destroy() {
    this.closed = true;
    this.timers.forEach(clearTimeout);
    this.stage.app.ticker?.remove(this.frame);
  }
}
