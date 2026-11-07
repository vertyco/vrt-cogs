// Slots: the tall golden slot machine, up close. Each machine is private, so the scene is the viewer's own, with their
// name on its belly plate. Three reels show through its windows, the marquee shows the live jackpot and what 7-7-7
// would pay at the tray's bet, and the lever on its right is the only way to spin: drag it down. How fast it goes down
// sets how fast and how long the reels spin, never where they stop: the bot draws the stops and the reels land on them.
// The scene contract is the comment at the top of the stand-in scene.
import { Assets, BlurFilter, Container, Graphics, Rectangle, Sprite, Text } from "../vendor/pixi.min.mjs";
import { money } from "../format.js";
import { shortName } from "../lobby.js";
import { loadArt, sparkle } from "./art.js";
import { ease, fitted, tween, wait } from "./kit.js";

// Just the machine and its lever with a little room, so the machine is as big as the space allows on a phone
// The share of each bet fed into the pot, in percent, and the hundredths in a credit: both as the bot has them
const JACKPOT_PERCENT = 2;
const CENTS = 100;
const WIDTH = 440;
const HEIGHT = 590;
// The room is bigger than the scene so a letterbox shows more room, not black
const BACKDROP = { width: 1500, height: 1000 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const CREAM = 0xf6ecd2;
const INK = 0x1a0f08;
const RED = 0xc8202f;
// machine.png is saved at twice its drawn size; everything on the machine is placed in its pixels
const ART_SCALE = 0.5;
// The machine sits a little left of the middle, so the machine and the lever beside it are centered together
const MACHINE_AT = { x: 11, y: 5 };
// Measured from machine.png: the three reel windows (x0, y0, x1, y1), the marquee's display, where the lever's arm
// rises (a hair right of the middle of the side hub that sticks out past the cabinet, where it looks centred), the
// payout tray's mouth, the belly panel's middle and the marquee bulbs
const WINDOWS = [
  [108, 389, 267, 663],
  [301, 389, 458, 663],
  [492, 389, 652, 663],
];
const DISPLAY = { x: 91, y: 227, width: 572, height: 108 };
// The marquee's middle in the scene's pixels
const MARQUEE_Y = MACHINE_AT.y + (DISPLAY.y + DISPLAY.height / 2) * ART_SCALE;
const HUB = { x: 753, y: 535 };
const TRAY = { x: 380, y: 950 };
const BELLY = { x: 383, y: 830, width: 540 };
const ARCH = [[108, 157], [150, 111], [201, 75], [260, 48], [319, 32], [380, 27], [442, 32], [500, 48], [559, 75]];
const SIDES = [248, 308, 369, 432, 496, 562, 627, 692, 801, 867];
// In chase order: up the left side, over the arch, down the right side
const BULBS = [
  ...[...SIDES].reverse().map((y) => [50, y]),
  ...ARCH,
  [610, 111],
  [651, 157],
  ...SIDES.map((y) => [707, y]),
];

// The bot's reel strip (vegas/common/games/slots.py), index 0 first. All three reels use it
export const STRIP = [
  "seven", "blank", "cherry", "bell", "blank", "coin", "bell", "cherry", "blank", "diamond", "bell",
  "blank", "coin", "cherry", "bell", "blank", "diamond", "blank", "coin", "cherry", "bell", "blank",
];
const SYMBOLS = ["seven", "blank", "cherry", "bell", "coin", "diamond"];
// The reels the machine shows before its first spin
const IDLE_STOPS = [14, 0, 7];

// The lever, in machine pixels: the knob's height above the hub at rest, and how far past the hub it goes at the
// bottom (a share of that height, as it swings toward the viewer)
const LEVER_LENGTH = 282;
const PAST_HUB = 0.45;
const TRAVEL = LEVER_LENGTH * (1 + PAST_HUB) * ART_SCALE;
// A pull counts once the knob is this far down. A press that moves less than TAP_PX is a tap, the gentlest pull
const PULL_POINT = 0.85;
const TAP_PX = 8;
// A knob that reaches the pull point this fast is the hardest pull, and this slow or slower the gentlest
const FAST_MS = 120;
const SLOW_MS = 900;
// The ratchet clicks this many times on the way down
const NOTCHES = 6;
// After a pull is sent, another is ignored until its spin arrives or this passes. Reels spun up by a pull the bot
// never answers coast to a stop after WAIT_FOR_SPIN_MS
const ARMED_MS = 2000;
const WAIT_FOR_SPIN_MS = 1200;
// Reels that coast to a stop slow down over COAST_MS, landing left to right this far apart
const COAST_MS = 240;
const COAST_GAP_MS = 60;

// Reel speeds in symbols a millisecond: the gentlest and the hardest pull
const SLOWEST = 0.01;
const FASTEST = 0.02;
// Reels reach their speed this long after the lever hits the bottom, left to right this far apart
const RAMP_MS = 220;
const KICK_GAP_MS = 45;
// A landing reel slows down over SLOW_DOWN_MS, its speed falling off with the square of the time left, until it moves
// CRAWL symbols a millisecond as its symbol reaches the line, so the last few symbols crawl past. Then it runs a
// little past the line and settles back onto it over BOUNCE_MS
const SLOW_DOWN_MS = 1300;
const CRAWL = 0.0025;
const BOUNCE_MS = 340;
// A reel steps along the strip to line up with its stop once it spins at least this share of its speed
const BLUR_SHARE = 0.6;
// Every spin's last reel is settled this long before the bot pays
const END_MARGIN_MS = 60;
// The gap between reels landing: a share of the spin, within these bounds. The last reel lingers LINGER times longer
// when the first two match
const GAP_SHARE = 0.17;
const MIN_GAP_MS = 420;
const MAX_GAP_MS = 700;
const LINGER = 1.6;
const CHASE_MS = 90;
const CLICK_MS = 90;

// The marquee: the jackpot's place with the line under it, the line's size, and the smallest the line may be on
// screen, in CSS pixels. Smaller than that, the line goes on a sign in the middle of the gap beside the machine: its
// words SIGN_FONT big but never under SIGN_MIN_PX on screen, SIGN_PAD inside its rim, at least SIGN_GAP from the
// machine and the scene's edge and never under SIGN_EDGE_PX on screen, and only when it can be SIGN_ROOM_PX wide on
// screen
const TITLE_Y = -19;
const LINE_Y = 31;
const LINE_FONT = 30;
const LINE_MIN_PX = 10;
const SIGN_FONT = 22;
const SIGN_MIN_PX = 11;
const SIGN_PAD = 14;
const SIGN_GAP = 10;
const SIGN_EDGE_PX = 12;
const SIGN_ROOM_PX = 110;
// The result card goes beside the machine when the scene has this many CSS pixels to the right of it, otherwise in the
// room kept over the machine for a jackpot note, which the machine stays NOTE_GAP_PX under. The top of the crown's
// bulbs, their glow included, in design pixels
const SIDE_SPOT_PX = 150;
const NOTE_GAP_PX = 6;
const CROWN_TOP = 3;

// Celebrations: wins of BIG_WIN times the bet or more shower coins, and the jackpot runs JACKPOT_MS
const BIG_WIN = 14;
const JACKPOT_MS = 4200;
const METER_HOLD_MS = 1600;
// The jackpot's coin bursts: when each starts (ms after the result) and where along the tray's mouth
const BURSTS = [[0, 0], [200, -60], [350, 60], [550, -25], [750, 30], [1500, -45], [1700, 50], [1900, 0], [2600, 20]];
const FOUNTAIN_SCALE = 1.5;
// A thrown coin's size, how high the biggest throws go, how wide the tray's mouth is, how fast a coin may fly out
// sideways (per ms), how fast it falls back (per ms per ms) and how long it flies, in the fountain's units
const COIN_SIZE = 18;
const COIN_RISE = 92;
const TRAY_MOUTH = 150;
const COIN_SPREAD = 0.2;
const GRAVITY = 0.00115;
const COIN_LIFE_MS = 1400;
// The jackpot's rain of coins behind the machine: how big a coin is in design pixels, and how many fall over how long
const RAIN_SIZE = 26;
const RAIN_COINS = 90;
const RAIN_MS = 3000;
// The marquee's JACKPOT! grows this much in the jackpot's show, and a reel at full speed blurs up and down by this
// share of a symbol's height. A reel under SHARP symbols a millisecond isn't blurred, so a crawl can be read
const SHOW_TITLE = 1.3;
const BLUR_SHARE_OF_CELL = 0.22;
const SHARP = 0.005;

function text(value, style) {
  const piece = new Text({ text: value, style, resolution: 2 });
  piece.anchor.set(0.5);
  return piece;
}

// Shrinks a text to fit a width, never growing it past its size
function fitWidth(piece, width) {
  piece.scale.set(1);
  if (piece.width > width) {
    piece.scale.set(width / piece.width);
  }
}

function mod(value, size) {
  return ((value % size) + size) % size;
}

// Runs apply(k) every frame as k goes 0 to 1 over ms; stops when the scene is destroyed
function run(owner, ms, apply, curve = ease.linear) {
  const driver = {
    value: 0,
    get destroyed() {
      return owner.destroyed;
    },
    get k() {
      return this.value;
    },
    set k(next) {
      this.value = next;
      apply(next);
    },
  };
  return tween(driver, { k: 1 }, Math.max(1, ms), curve);
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

// ---- The page's math, shared with the tests ----

// How hard a pull was, 0 to 1, from the ms between the press and the knob passing the pull point. A tap is null
export function strengthOf(ms) {
  if (ms === null || ms === undefined) {
    return 0;
  }
  return Math.min(1, Math.max(0, (SLOW_MS - ms) / (SLOW_MS - FAST_MS)));
}

// When each reel's symbol reaches the line, in ms after the spin starts. The last reel is settled before `seconds`,
// and lingers when the first two match
export function landTimes(seconds, line) {
  const last = seconds * 1000 - BOUNCE_MS - END_MARGIN_MS;
  const gap = Math.min(MAX_GAP_MS, Math.max(MIN_GAP_MS, last * GAP_SHARE));
  const before = line[0] === line[1] ? gap * LINGER : gap;
  return [last - before - gap, last - before, last];
}

// The bot's jackpot share in whole credits: the pot with this bet's own feed in it (JACKPOT_PERCENT of the bet, in
// hundredths, rounded down to whole credits), times the bet over the max bet, the whole pot at the max
// bet. BigInt keeps it exact for any pot
export function shareOf(amount, bet, max) {
  if (!(bet > 0) || !(max > 0) || !(amount > 0)) {
    return 0;
  }
  const most = Math.floor(max);
  const staked = Math.min(Math.floor(bet), most);
  const pot = BigInt(Math.floor(amount)) + BigInt(Math.floor((staked * JACKPOT_PERCENT) / CENTS));
  return Number((pot * BigInt(staked)) / BigInt(most));
}

export function jackpotLine(amount, bet, max) {
  return `7-7-7 pays you ${money(shareOf(amount, bet, max))} at this bet`;
}

// Where the scene's design sits in a scene of this size, in CSS pixels: as big as fits under the room a jackpot note
// reaching `note` down the scene takes, and centered in what is left
function placeIn(width, height, note) {
  const top = note > 0 ? note + NOTE_GAP_PX : 0;
  const room = Math.max(1, height - top);
  const scale = Math.min(width / WIDTH, room / HEIGHT);
  return { scale, left: (width - WIDTH * scale) / 2, top: top + (room - HEIGHT * scale) / 2 };
}

// The knob at rest and how far down it travels, in CSS pixels of a scene of this size
export function leverAt(width, height, note = 0) {
  const { scale, left, top } = placeIn(width, height, note);
  const x = MACHINE_AT.x + HUB.x * ART_SCALE;
  const y = MACHINE_AT.y + (HUB.y - LEVER_LENGTH) * ART_SCALE;
  return { x: left + x * scale, y: top + y * scale, travel: TRAVEL * scale };
}

// How fast the reels spin for a pull this hard, 0 to 1, in symbols a millisecond
export function reelSpeed(strength) {
  return SLOWEST + (FASTEST - SLOWEST) * strength;
}

// The whole number of symbols to add to a reel ending at place `end` so it ends showing `stop` on the line instead: the
// smallest step either way. A reel's place counts down the strip, so place p shows stop -p
function stepTo(stop, end) {
  const step = mod(-stop - end, STRIP.length);
  return step > STRIP.length / 2 ? step - STRIP.length : step;
}

// A reel speeding from v0 to v1 symbols a millisecond over ramp ms, starting at `start`, then cruising
function cruise(pos, v0, start, v1, ramp) {
  return (now) => {
    const t = Math.max(0, now - start);
    if (t < ramp) {
      const speed = v0 + ((v1 - v0) * t) / ramp;
      return { pos: pos + ((v0 + speed) / 2) * t, speed };
    }
    return { pos: pos + ((v0 + v1) / 2) * ramp + v1 * (t - ramp), speed: v1 };
  };
}

// A reel whose stop reached the line `t` ms ago, moving CRAWL symbols a millisecond: it runs on a little past the line,
// then settles back onto `target`, standing still BOUNCE_MS after it arrived
function bounce(target, t) {
  const k = Math.min(1, t / BOUNCE_MS);
  if (k >= 1) {
    return { pos: target, speed: 0 };
  }
  const turn = Math.PI * k;
  const pos = target + ((CRAWL * BOUNCE_MS) / Math.PI) * Math.sin(turn) * (1 - k);
  return { pos, speed: Math.abs(CRAWL * (Math.cos(turn) * (1 - k) - Math.sin(turn) / Math.PI)) };
}

// A reel moving at `now` as `from` says, brought to land on `stop` (or wherever it comes to, when null) with its symbol
// on the line at landAt ms after `now`: it eases to the spin's speed, spends its last `slow` ms slowing down to a crawl
// as its symbol reaches the line, then runs a little past and settles back. Every reel keeps the spin's speed, so a
// harder pull always looks faster. A short spin may not pass enough of the strip to reach its stop at that speed, so
// once the reel is a blur it steps a whole number of symbols along the strip: each symbol stays where it is on screen
// and only which one shows there changes, which a spinning reel hides. Returns the reel's place over time and the
// place it ends on
export function landing(from, now, stop, landAt, speed, slow = SLOW_DOWN_MS) {
  const { pos, speed: v0 } = from;
  const slowAt = Math.max(0, landAt - slow);
  const slowing = landAt - slowAt;
  const ramp = Math.min(RAMP_MS, slowAt);
  // Slowing down from speed v covers (2 x CRAWL + v) / 3 symbols for each of its ms, so the reel ends at
  // start + v x span
  const start = pos + (v0 * ramp) / 2 + (CRAWL * slowing * 2) / 3;
  const span = ramp / 2 + (slowAt - ramp) + slowing / 3;
  // The speed nudged by under half a symbol over the spin, so it ends on a whole place
  const end = Math.round(start + speed * span);
  const even = (end - start) / span;
  const step = stop === null ? 0 : stepTo(stop, end);
  const target = end + step;
  const blurAt = v0 >= BLUR_SHARE * even ? 0 : (ramp * (BLUR_SHARE * even - v0)) / (even - v0);
  const before = cruise(pos, v0, now, even, ramp);
  const slowFrom = before(now + slowAt).pos + step;
  return {
    target,
    motion: (at) => {
      const t = at - now;
      if (t < slowAt) {
        const { pos: place, speed: moving } = before(at);
        return { pos: place + (t >= blurAt ? step : 0), speed: moving };
      }
      if (t >= landAt) {
        return bounce(target, t - landAt);
      }
      const left = 1 - (t - slowAt) / slowing;
      const lost = ((even - CRAWL) * slowing * (1 - left ** 3)) / 3;
      return { pos: slowFrom + CRAWL * (t - slowAt) + lost, speed: CRAWL + (even - CRAWL) * left * left };
    },
  };
}

// ---- Building the machine ----

async function loadMachineArt() {
  const base = new URL("../art/slots/", import.meta.url).href;
  const names = ["room", "machine", "lever-arm", "lever-knob", ...SYMBOLS];
  const files = names.map((name) => `${name}.${name === "room" ? "jpg" : "png"}`);
  const loaded = await Promise.all(
    files.map((file) => Assets.load({ src: base + file, data: { autoGenerateMipmaps: true } })),
  );
  return Object.fromEntries(names.map((name, index) => [name, loaded[index]]));
}

function makeRoom(texture) {
  const room = new Sprite(texture);
  room.anchor.set(0.5);
  room.position.set(WIDTH / 2, HEIGHT / 2);
  room.width = BACKDROP.width;
  room.height = BACKDROP.height;
  return room;
}

// Each bulb: a glow to light it up and a dark disc to turn it off, since the picture's bulbs are all lit
function makeLights() {
  return BULBS.map(([x, y]) => {
    const bulb = new Container();
    bulb.position.set(x, y);
    bulb.off = new Graphics().circle(0, 0, 15).fill({ color: 0x2a0a06, alpha: 0.7 });
    bulb.on = glow(30, 0xffe9a8);
    bulb.addChild(bulb.off, bulb.on);
    return bulb;
  });
}

// Lit all round at rest, chasing while the reels spin, racing while the last reel lingers, flashing on a win
function drawLights(lights, mode, since, now) {
  const pace = { tease: CHASE_MS * 0.45, win: CHASE_MS * 0.6 }[mode] ?? CHASE_MS;
  const step = Math.floor((now - since) / pace);
  const flash = mode === "win" && Math.floor((now - since) / 240) % 2 === 0;
  lights.forEach((bulb, index) => {
    const lit = mode === "rest" || flash || mod(index - step, 3) === 0;
    bulb.off.visible = !lit;
    bulb.on.alpha = mode === "rest" ? 0.35 : lit ? 1 : 0;
  });
}

// The marquee's display: the jackpot on top, what 7-7-7 pays at the tray's bet under it
function makeDisplay() {
  const panel = new Container();
  panel.position.set(DISPLAY.x + DISPLAY.width / 2, DISPLAY.y + DISPLAY.height / 2);
  panel.halo = glow(DISPLAY.width * 0.55, GOLD_LIGHT, 0.6);
  panel.halo.scale.y = 0.35;
  panel.halo.alpha = 0.3;
  panel.title = text("JACKPOT", {
    fontFamily: FONT,
    fontWeight: "900",
    fontSize: 52,
    fill: GOLD_LIGHT,
    letterSpacing: 3,
    stroke: { color: INK, width: 4 },
  });
  panel.title.label = "jackpot-title";
  panel.title.y = TITLE_Y;
  panel.line = text("", { fontFamily: MARKS, fontWeight: "600", fontSize: LINE_FONT, fill: CREAM });
  panel.line.label = "jackpot-line";
  panel.line.y = LINE_Y;
  panel.addChild(panel.halo, panel.title, panel.line);
  return panel;
}

// The jackpot line's sign beside the machine, for a machine drawn too small for the marquee's line to read
function makeSign() {
  const sign = new Container({ label: "sign" });
  sign.plate = new Graphics();
  const style = { fontFamily: MARKS, fontWeight: "600", fontSize: SIGN_FONT, fill: CREAM, align: "center" };
  sign.words = text("", { ...style, wordWrap: true });
  sign.words.label = "jackpot-line";
  sign.addChild(sign.plate, sign.words);
  sign.visible = false;
  return sign;
}

// Narrows a wrapped text as far as it goes without adding a line, so its lines come out even and no word sits alone
function evenLines(piece, widest) {
  piece.style.wordWrapWidth = widest;
  const height = piece.height;
  let low = widest / 2;
  let high = widest;
  while (high - low > 2) {
    const middle = (low + high) / 2;
    piece.style.wordWrapWidth = middle;
    if (piece.height > height + 1) {
      low = middle;
    } else {
      high = middle;
    }
  }
  piece.style.wordWrapWidth = high;
}

// How far the sign keeps from the machine and the scene's edge, in scene pixels
function signGap(scale) {
  return Math.max(SIGN_GAP, SIGN_EDGE_PX / scale);
}

// The sign's words wrapped in even lines to fit `room`, the scene pixels left of the machine, on a dark plate with a
// gold rim, level with the marquee and in the middle of that room
function drawSign(sign, words, room, scale) {
  const size = Math.max(SIGN_FONT, SIGN_MIN_PX / scale);
  Object.assign(sign.words.style, { fontSize: size, lineHeight: size * 1.2 });
  sign.words.text = words;
  evenLines(sign.words, room - 2 * (signGap(scale) + SIGN_PAD));
  const width = sign.words.width + 2 * SIGN_PAD;
  const height = sign.words.height + 1.4 * SIGN_PAD;
  sign.plate.clear();
  sign.plate.roundRect(-width / 2 + 2, -height / 2 + 3, width, height, 12).fill({ color: 0x000000, alpha: 0.35 });
  sign.plate.roundRect(-width / 2, -height / 2, width, height, 12).fill({ color: INK, alpha: 0.9 });
  sign.plate.stroke({ width: 2.5, color: GOLD });
  sign.position.set(MACHINE_AT.x - room / 2, MARQUEE_Y);
}

// The belly: the player's name, and the win meter that takes its place while a win counts up
function makeBelly() {
  const panel = new Container();
  panel.position.set(BELLY.x, BELLY.y);
  panel.plate = text("", { fontFamily: MARKS, fontWeight: "700", fontSize: 40, fill: GOLD_LIGHT, letterSpacing: 1 });
  panel.meter = text("", {
    fontFamily: FONT,
    fontWeight: "900",
    fontSize: 66,
    fill: GOLD_LIGHT,
    letterSpacing: 2,
    stroke: { color: INK, width: 5 },
    dropShadow: { color: 0xffd36b, alpha: 0.55, blur: 10, distance: 0 },
  });
  panel.meter.label = "meter";
  panel.meter.visible = false;
  panel.addChild(panel.plate, panel.meter);
  return panel;
}

// The lever on its hub, pressable wide enough for a thumb on an upright phone and down the whole way the knob travels
function makeLever(art) {
  const piece = new Container({ label: "lever" });
  piece.position.set(HUB.x, HUB.y);
  piece.arm = new Sprite({ texture: art["lever-arm"], label: "arm" });
  piece.arm.anchor.set(0.5, 0.97);
  piece.arm.scale.x = 1.6;
  piece.knob = new Sprite({ texture: art["lever-knob"], label: "knob" });
  piece.knob.anchor.set(0.5);
  piece.addChild(piece.arm, piece.knob);
  piece.eventMode = "static";
  piece.cursor = "pointer";
  const bottom = LEVER_LENGTH * PAST_HUB + 80;
  piece.hitArea = new Rectangle(-100, -LEVER_LENGTH - 70, 200, LEVER_LENGTH + 70 + bottom);
  return piece;
}

// How far down the lever is: 0 at rest, 1 at the bottom, a little under 0 as it springs back past rest. The knob
// moves straight down the screen as the lever swings toward the viewer, so it stays under a dragging finger. A gripped
// knob is a little bigger
function poseLever(lever, down, gripped) {
  const reach = 1 - (1 + PAST_HUB) * down;
  lever.arm.scale.y = reach;
  lever.knob.y = -LEVER_LENGTH * reach;
  lever.knob.scale.set((1 + Math.max(0, -reach) * 0.35) * (gripped ? 1.08 : 1));
}

// The fastest a coin leaving the tray at x0 with sideways speed vx may go up without crossing `clear`, the box the
// belly's count fills (its left, right and bottom in the fountain's units, the tray's mouth being 0): over the count it
// stays low, out past it it may climb
function upSpeed(x0, vx, wanted, clear) {
  const half = COIN_SIZE / 2 + 1;
  const lowest = clear.bottom + half;
  const wide = half + COIN_SIZE / 3;
  let most = wanted;
  for (let t = 20; t <= COIN_LIFE_MS; t += 20) {
    const x = x0 + vx * t;
    if (x + wide > clear.left && x - wide < clear.right) {
      most = Math.min(most, (0.5 * GRAVITY * t * t - lowest) / t);
    }
  }
  return Math.max(0, most);
}

// Coins thrown out of the tray's mouth, turning over as they fly out to the sides and dropping out of sight under their
// own weight. Each leaves at its own moment. None crosses `clear`, so the belly's count always reads. They vanish once
// showing() turns false
async function throwCoins(fountain, texture, showing, count, ms, clear) {
  const size = COIN_SIZE / texture.width;
  const coins = Array.from({ length: count }, (_, index) => {
    const coin = new Sprite({ texture, label: "flying-coin" });
    coin.anchor.set(0.5);
    coin.visible = false;
    fountain.addChild(coin);
    const x0 = (Math.random() - 0.5) * TRAY_MOUTH;
    const vx = Math.sign(x0 || 1) * (0.02 + Math.random() * COIN_SPREAD);
    const wanted = Math.sqrt(2 * GRAVITY * COIN_RISE * (0.7 + Math.random() * 0.45));
    const delay = (index / count) * (ms - COIN_LIFE_MS * 0.6);
    return { coin, delay, x0, vx, up: upSpeed(x0, vx, wanted, clear), turn: 7 + Math.random() * 9 };
  });
  const span = ms + COIN_LIFE_MS * 0.4;
  await run(fountain, span, (k) => {
    const now = k * span;
    const shown = showing();
    for (const { coin, delay, x0, vx, up, turn } of coins) {
      const t = now - delay;
      coin.visible = shown && t >= 0 && t <= COIN_LIFE_MS;
      coin.position.set(x0 + vx * t, -up * t + 0.5 * GRAVITY * t * t);
      coin.scale.set(size * Math.cos((t / 1000) * turn), size);
      coin.alpha = Math.min(1, Math.max(0, (COIN_LIFE_MS - t) / 300));
    }
  });
  coins.forEach(({ coin }) => !coin.destroyed && coin.destroy());
}

// The jackpot's rain: coins falling behind the machine from above the top of `area` (the room on screen, in design
// pixels) to below its bottom, each its own size, speed and turn, so the whole stage pours with gold past the cabinet
async function rainCoins(layer, texture, showing, area) {
  const drop = area.bottom - area.top + 2 * RAIN_SIZE;
  const coins = Array.from({ length: RAIN_COINS }, (_, index) => {
    const coin = new Sprite({ texture, label: "flying-coin" });
    coin.anchor.set(0.5);
    coin.visible = false;
    layer.addChild(coin);
    const fall = 1100 + Math.random() * 700;
    return {
      coin,
      fall,
      delay: (index / RAIN_COINS) * (RAIN_MS - fall),
      x: area.left + Math.random() * (area.right - area.left),
      size: (RAIN_SIZE * (0.65 + Math.random() * 0.7)) / texture.width,
      turn: 6 + Math.random() * 8,
      tilt: Math.random() * 6,
    };
  });
  await run(layer, RAIN_MS, (k) => {
    const now = k * RAIN_MS;
    const shown = showing();
    for (const { coin, fall, delay, x, size, turn, tilt } of coins) {
      const t = (now - delay) / fall;
      coin.visible = shown && t >= 0 && t <= 1;
      coin.position.set(x, area.top - RAIN_SIZE + drop * (0.35 * t + 0.65 * t * t));
      coin.scale.set(size * Math.cos(tilt + (now / 1000) * turn), size);
    }
  });
  coins.forEach(({ coin }) => !coin.destroyed && coin.destroy());
}

// ---- The scene ----

export async function createScene(stage) {
  await loadArt();
  const machine = new SlotMachine(stage, await loadMachineArt());
  return {
    show: () => machine.showOwner(),
    play: (event) => machine.play(event),
    result: (message) => machine.result(message),
    notice: () => machine.notice(),
    preview: (value) => machine.preview(value),
    jackpot: (amount) => machine.jackpot(amount),
    layout: (width, height, note) => machine.layout(width, height, note),
    resultSpot: () => machine.resultSpot(),
    destroy: () => machine.destroy(),
  };
}

class SlotMachine {
  constructor(stage, art) {
    this.stage = stage;
    this.art = art;
    // The jackpot in whole credits as the bot last said, the tray's bet, and the number the marquee shows now
    this.pot = null;
    this.bet = 0;
    this.shownPot = null;
    // What 7-7-7 pays at the tray's bet, in words, or "" with no bet; and the room the scene has, in CSS pixels
    this.lineWords = "";
    this.space = { width: WIDTH, height: HEIGHT };
    // A press on the lever being dragged, and whether the lever is moving by itself (a pull or a spring back)
    this.grip = null;
    this.leverBusy = false;
    // Set from a sent pull until its spin arrives (or ARMED_MS passes), so a second pull isn't sent; and the timer that
    // lets reels spun up by a pull the bot never answered coast to a stop
    this.armed = null;
    this.waiting = null;
    this.spinning = false;
    // Each pull's number, so a win's celebration stops when the next pull starts
    this.pulls = 0;
    this.celebrating = false;
    this.lights = { mode: "rest", since: 0 };
    this.click = { at: 0, place: 0 };
    // Set once the scene is gone, so animations still waiting stop at their next step
    this.closed = false;
    this.build();
    this.reels.forEach((reel, index) => reel.rest(-IDLE_STOPS[index]));
    this.setLever(0);
    this.frame = () => this.tick(performance.now());
    stage.app.ticker.add(this.frame);
    // Pixi passes on no cancelled touch, so the canvas is watched for one
    this.canvas = stage.app.canvas;
    this.cancelled = (event) => this.cancel(event);
    this.canvas.addEventListener("pointercancel", this.cancelled);
  }

  build() {
    const { art } = this;
    this.root = fitted(WIDTH, HEIGHT);
    this.stage.root.addChild(this.root);
    this.machine = new Container({ label: "machine" });
    this.machine.position.set(MACHINE_AT.x, MACHINE_AT.y);
    this.machine.scale.set(ART_SCALE);
    this.reels = WINDOWS.map((rect, index) => new Reel(rect, art, `reel-${index}`));
    this.bulbs = makeLights();
    this.display = makeDisplay();
    this.lever = makeLever(art);
    this.lever.on("pointerdown", (event) => this.grab(event));
    this.lever.on("globalpointermove", (event) => this.drag(event));
    this.lever.on("pointerup", (event) => this.letGo(event));
    this.lever.on("pointerupoutside", (event) => this.letGo(event));
    const cabinet = new Sprite(art.machine);
    this.machine.addChild(...this.reels.map((reel) => reel.box), cabinet, ...this.bulbs, this.display, this.lever);
    // The jackpot's rain falls behind the machine. Coins come out of the tray's mouth, drawn bigger than the kit's
    // sparkle so they read as a win
    this.rain = new Container({ label: "rain" });
    this.fountain = new Container({ label: "fountain" });
    this.fountain.position.set(MACHINE_AT.x + TRAY.x * ART_SCALE, MACHINE_AT.y + TRAY.y * ART_SCALE);
    this.fountain.scale.set(FOUNTAIN_SCALE);
    // The belly's words sit over the coins flying past them, so a win can be read through its own shower
    this.front = new Container();
    this.front.position.copyFrom(this.machine.position);
    this.front.scale.set(ART_SCALE);
    this.belly = makeBelly();
    this.front.addChild(this.belly);
    this.sign = makeSign();
    this.root.addChild(makeRoom(art.room), this.rain, this.machine, this.sign, this.fountain, this.front);
  }

  // The machine fits under the room a jackpot note takes at the top of the scene, so a note never covers its crown
  layout(width, height, note = 0) {
    this.space = { width, height };
    const { scale, left, top } = placeIn(width, height, note);
    this.root.scale.set(scale);
    this.root.position.set(left, top);
    this.placeLine();
  }

  // Where the result card covers nothing that matters, in CSS pixels of the scene's room: beside the machine on the
  // lever's side when there is room, otherwise across the top of the scene, over the crown's bulbs
  resultSpot() {
    const { x, y } = this.root.position;
    const scale = this.root.scale.x;
    const right = x + WIDTH * scale;
    if (this.space.width - right >= SIDE_SPOT_PX) {
      return { left: right, top: 0, right: this.space.width, bottom: this.space.height };
    }
    return { left: 0, top: 0, right: this.space.width, bottom: y + CROWN_TOP * scale };
  }

  // ---- The marquee ----

  showPot(amount) {
    this.shownPot = amount;
    this.display.title.text = amount === null ? "JACKPOT" : `JACKPOT ${money(amount)}`;
    fitWidth(this.display.title, DISPLAY.width - 30);
  }

  // A pot that grew rolls up to its new amount with a flash of the halo, so the player sees it climb
  async rollPot(amount) {
    const from = this.shownPot;
    if (from === null || amount === null || amount <= from) {
      this.showPot(amount);
      return;
    }
    const step = (k) => {
      if (!this.celebrating && this.pot === amount) {
        this.showPot(Math.round(from + (amount - from) * k));
        this.display.halo.alpha = 0.3 + 0.5 * Math.sin(Math.PI * k);
      }
    };
    await run(this.display, 600, step, ease.out);
  }

  // What 7-7-7 pays at the tray's bet. A cleared bet has nothing to win, so the line hides
  showLine() {
    const max = this.stage.settings?.()?.max ?? 0;
    this.lineWords = this.pot === null || this.bet <= 0 ? "" : jackpotLine(this.pot, this.bet, max);
    this.placeLine();
  }

  // The line goes under the marquee's jackpot. On a machine drawn so small that it would be under LINE_MIN_PX on screen
  // there, it goes on a sign beside the machine instead, when there is room for one. With no line under it, as all
  // through the jackpot's show, the jackpot takes the marquee's middle
  placeLine() {
    const { line, title } = this.display;
    const scale = this.root.scale.x;
    const words = this.celebrating ? "" : this.lineWords;
    line.text = words;
    fitWidth(line, DISPLAY.width - 32);
    const small = LINE_FONT * line.scale.x * ART_SCALE * scale < LINE_MIN_PX;
    const room = this.root.position.x / scale + MACHINE_AT.x;
    const signed = Boolean(words) && small && (room - 2 * signGap(scale)) * scale >= SIGN_ROOM_PX;
    line.visible = Boolean(words) && !signed;
    title.y = line.visible ? TITLE_Y : 0;
    this.sign.visible = signed;
    if (signed) {
      drawSign(this.sign, words, room, scale);
    }
  }

  // ---- The belly ----

  showOwner() {
    const me = this.stage.me();
    this.belly.plate.text = me ? shortName(this.stage.nameOf(me)) : "";
    fitWidth(this.belly.plate, BELLY.width);
  }

  showMeter(amount) {
    this.belly.meter.text = `WIN ${money(amount)}`;
    fitWidth(this.belly.meter, BELLY.width);
  }

  // Counts the payout up on the belly, holds it, then gives the plate back
  async countUp(pull, amount, ms) {
    this.belly.meter.visible = true;
    this.belly.plate.visible = false;
    await run(this.belly, ms, (k) => pull === this.pulls && this.showMeter(Math.floor(amount * k)), ease.out);
    await wait(METER_HOLD_MS);
    if (pull === this.pulls && !this.closed) {
      this.quietBelly();
    }
  }

  quietBelly() {
    this.belly.meter.visible = false;
    this.belly.plate.visible = true;
  }

  // The box the belly's count fills at `amount`, in the fountain's units, for coins to fly clear of
  clearOf(amount) {
    const shown = this.belly.meter.text;
    this.showMeter(amount);
    const box = this.belly.meter.getBounds();
    this.belly.meter.text = shown;
    const corner = this.fountain.toLocal({ x: box.minX, y: box.maxY });
    const across = this.fountain.toLocal({ x: box.maxX, y: box.maxY });
    return { left: corner.x, right: across.x, bottom: corner.y };
  }

  // The room on screen, in design pixels
  shownArea() {
    const { x, y } = this.root.position;
    const scale = this.root.scale.x;
    const { width, height } = this.space;
    return { left: -x / scale, top: -y / scale, right: (width - x) / scale, bottom: (height - y) / scale };
  }

  // ---- The lever ----

  setLever(down) {
    poseLever(this.lever, down, Boolean(this.grip && !this.grip.sent));
  }

  designY(event) {
    return this.root.toLocal(event.global).y;
  }

  grab(event) {
    // A press while an unsent drag is still held means that drag's release never came, so the new press takes over
    if (this.grip && !this.grip.sent) {
      this.grip = null;
    }
    if (this.grip || this.leverBusy || this.spinning || this.armed || event.button > 0) {
      return;
    }
    const at = event.global;
    this.grip = { id: event.pointerId, start: performance.now(), y: this.designY(event), x0: at.x, y0: at.y };
    Object.assign(this.grip, { moved: 0, down: 0, notch: 0, sent: false });
    this.setLever(0);
  }

  drag(event) {
    const grip = this.grip;
    if (!grip || event.pointerId !== grip.id || grip.sent) {
      return;
    }
    // A mouse let go outside the page never sends its release
    if (event.pointerType === "mouse" && event.buttons === 0) {
      this.letGo(event);
      return;
    }
    grip.moved = Math.max(grip.moved, Math.hypot(event.global.x - grip.x0, event.global.y - grip.y0));
    grip.down = Math.min(1, Math.max(0, (this.designY(event) - grip.y) / TRAVEL));
    this.setLever(grip.down);
    const notch = Math.floor(grip.down * NOTCHES);
    if (notch > grip.notch) {
      this.stage.sound.play("tick");
    }
    grip.notch = Math.max(grip.notch, notch);
    if (grip.down >= PULL_POINT) {
      this.pullAt(strengthOf(performance.now() - grip.start));
    }
  }

  // The knob passed the pull point: send the pull, and slam the lever home if it went
  pullAt(strength) {
    const down = this.grip.down;
    this.grip.sent = true;
    if (!this.send(strength)) {
      this.grip = null;
      this.springBack(down);
      return;
    }
    this.slam(down, strength, 70);
  }

  letGo(event) {
    const grip = this.grip;
    if (!grip || event.pointerId !== grip.id) {
      return;
    }
    this.grip = null;
    if (grip.sent) {
      return;
    }
    // A tap is the gentlest pull, and the lever goes all the way down by itself
    if (grip.moved >= TAP_PX) {
      this.springBack(grip.down);
    } else if (this.send(0)) {
      this.slam(0, 0, 260);
    } else {
      this.springBack(0.12);
    }
  }

  // The phone took the touch back (an edge swipe, a turn of the phone): an unsent drag springs back, and the lever is
  // free for the next press
  cancel(event) {
    const grip = this.grip;
    if (!grip || event.pointerId !== grip.id) {
      return;
    }
    this.grip = null;
    if (!grip.sent) {
      this.springBack(grip.down);
    }
  }

  // The tray refuses a pull it can't place (the dock says why), and one that can't reach the bot
  send(strength) {
    if (!this.stage.actions.place(strength)) {
      this.stage.sound.play("click");
      return false;
    }
    this.armed = setTimeout(() => (this.armed = null), ARMED_MS);
    return true;
  }

  // The lever runs to the bottom, clunks, kicks the reels into motion and the machine with them, then springs back up
  async slam(from, strength, ms) {
    this.leverBusy = true;
    await run(this.lever, ms, (k) => this.setLever(from + (1 - from) * k), from > 0 ? ease.out : ease.inOut);
    if (this.closed) {
      return;
    }
    this.stage.sound.play("lever");
    this.kick(strength);
    this.shake(strength);
    await wait(70);
    await run(this.lever, 520, (k) => this.setLever(1 - k), ease.back);
    // A finger that went home with the lever and never lifted (its release was lost) lets go here
    if (this.grip?.sent) {
      this.grip = null;
    }
    this.leverBusy = false;
  }

  async springBack(from) {
    this.leverBusy = true;
    await run(this.lever, 180 + 220 * from, (k) => this.setLever(from * (1 - k)), ease.back);
    this.leverBusy = false;
  }

  async shake(strength) {
    const size = 1.5 + 4 * strength;
    await run(this.root, 220, (k) => {
      this.machine.x = MACHINE_AT.x + Math.sin(k * 38) * size * (1 - k);
      this.machine.y = MACHINE_AT.y + Math.cos(k * 31) * size * 0.5 * (1 - k);
      this.front.position.copyFrom(this.machine.position);
    });
  }

  // ---- Every frame ----

  setLights(mode) {
    this.lights = { mode, since: performance.now() };
  }

  // Moves the reels, clicks as symbols pass the line on the last reel still spinning, and chases the lights
  tick(now) {
    this.reels.forEach((reel) => reel.update(now));
    const moving = [...this.reels].reverse().find((reel) => reel.speed > 0.002);
    const place = moving ? Math.floor(moving.pos) : null;
    if (moving && place !== this.click.place && now - this.click.at >= CLICK_MS) {
      this.click = { at: now, place };
      this.stage.sound.play("click");
    }
    drawLights(this.bulbs, this.lights.mode, this.lights.since, now);
  }

  // ---- A spin ----

  // The lever hit the bottom: the reels spin up left to right at the pull's speed while the bot draws the stops. A spin
  // that is already landing keeps going
  kick(strength) {
    this.pulls += 1;
    this.calm();
    if (this.spinning) {
      return;
    }
    const now = performance.now();
    const speed = reelSpeed(strength);
    this.reels.forEach((reel, index) => reel.spinUp(cruise(reel.pos, 0, now + index * KICK_GAP_MS, speed, RAMP_MS)));
    this.setLights("spin");
    clearTimeout(this.waiting);
    this.waiting = setTimeout(() => this.coast(), WAIT_FOR_SPIN_MS);
  }

  // Reels spun up for a pull that gets no spin slow down where they are, left to right
  coast() {
    clearTimeout(this.waiting);
    if (this.spinning || this.closed) {
      return;
    }
    const now = performance.now();
    let moving = false;
    this.reels.forEach((reel, index) => {
      const from = reel.state(now);
      if (from.speed > 0) {
        moving = true;
        const landAt = COAST_MS + index * COAST_GAP_MS;
        reel.landOn(landing(from, now, null, landAt, from.speed, landAt), now + landAt + BOUNCE_MS);
      }
    });
    if (moving) {
      const stopped = COAST_MS + (this.reels.length - 1) * COAST_GAP_MS + BOUNCE_MS;
      setTimeout(() => !this.spinning && !this.celebrating && this.setLights("rest"), stopped);
    }
  }

  // The bot refused something, a pull among them, or the link came back: a pull it never answered frees the lever and
  // its reels stop now
  notice() {
    clearTimeout(this.armed);
    this.armed = null;
    this.coast();
  }

  async play(event) {
    if (event.kind !== "spin") {
      return;
    }
    clearTimeout(this.armed);
    clearTimeout(this.waiting);
    this.armed = null;
    this.spinning = true;
    const now = performance.now();
    const line = event.reels.map((reel) => reel[1]);
    const lands = landTimes(event.seconds, line);
    const speed = reelSpeed(event.strength ?? 0);
    this.reels.forEach((reel, index) => {
      const plan = landing(reel.state(now), now, event.stops[index], lands[index], speed);
      reel.landOn(plan, now + lands[index] + BOUNCE_MS);
    });
    if (this.lights.mode === "rest") {
      this.setLights("spin");
    }
    try {
      await this.landAll(now, lands, line);
    } finally {
      this.spinning = false;
    }
    if (!this.closed && !this.celebrating) {
      this.setLights("rest");
    }
  }

  // Waits for each reel to land with its thump. Once the first two match, the lights race while the last one lingers
  async landAll(start, lands, line) {
    for (const [index, at] of lands.entries()) {
      await wait(Math.max(0, start + at - performance.now()));
      if (this.closed) {
        return;
      }
      this.stage.sound.play("stop");
      if (index === 1 && line[0] === line[1]) {
        this.setLights("tease");
      }
    }
    await wait(Math.max(0, start + lands[2] + BOUNCE_MS - performance.now()));
    this.reels.forEach((reel) => reel.settle());
  }

  // ---- Wins ----

  result(message) {
    if (!["win", "jackpot"].includes(message.outcome)) {
      return;
    }
    const pull = this.pulls;
    const showing = () => pull === this.pulls && !this.closed;
    const jackpot = message.outcome === "jackpot";
    const big = jackpot || message.payout >= message.stake * BIG_WIN;
    this.countUp(pull, message.payout, jackpot ? 2200 : big ? 1300 : 800);
    const clear = big ? this.clearOf(message.payout) : null;
    if (big) {
      throwCoins(this.fountain, this.art.coin, showing, jackpot ? 48 : 24, jackpot ? 2200 : 1500, clear);
    }
    if (jackpot) {
      this.celebrate(showing, clear);
      return;
    }
    this.flash(showing, big ? 1600 : 900);
    if (big) {
      this.stage.sound.play("coin");
      sparkle(this.fountain, -40, 0, 900);
      setTimeout(() => showing() && sparkle(this.fountain, 40, 0, 900), 260);
    }
  }

  // The lights flash and chase and the winning line pulses
  async flash(showing, ms) {
    this.setLights("win");
    await run(this.root, ms, (k) => {
      if (showing()) {
        this.reels.forEach((reel) => reel.pulse(1 + 0.08 * Math.abs(Math.sin((k * ms) / 160))));
      }
    });
    if (showing()) {
      this.endShow();
    }
  }

  // The jackpot, the casino's biggest show: the marquee flashes a big JACKPOT! with nothing under it, the lights chase,
  // the 7s and the line light up and pulse, coins rain down behind the machine across the whole stage and burst from
  // the tray again and again, clear of the belly's count. It runs on after result() returns, and stops early if another
  // pull starts
  async celebrate(showing, clear) {
    this.celebrating = true;
    this.placeLine();
    this.stage.sound.play("coin");
    this.setLights("win");
    this.display.title.text = "JACKPOT!";
    fitWidth(this.display.title, DISPLAY.width - 30);
    this.display.title.base = this.display.title.scale.x;
    rainCoins(this.rain, this.art.coin, showing, this.shownArea());
    const burst = (x) => {
      if (showing()) {
        sparkle(this.fountain, x, 0, 1000);
        this.stage.sound.play("coin");
      }
    };
    const timers = BURSTS.map(([delay, x]) => setTimeout(() => burst(x), delay));
    const again = () => showing() && throwCoins(this.fountain, this.art.coin, showing, 30, 1700, clear);
    timers.push(setTimeout(again, JACKPOT_MS * 0.45));
    await run(this.root, JACKPOT_MS, (k) => showing() && this.beat(k * JACKPOT_MS));
    timers.forEach(clearTimeout);
    if (showing()) {
      this.endShow();
    }
  }

  // One moment of the jackpot's show, `now` ms into it
  beat(now) {
    const pulse = Math.abs(Math.sin(now / 120));
    const { title, halo } = this.display;
    halo.alpha = 0.4 + 0.6 * pulse;
    title.tint = pulse > 0.5 ? 0xffffff : GOLD_LIGHT;
    title.scale.set(title.base * (SHOW_TITLE + 0.1 * pulse));
    this.display.scale.set(1 + 0.04 * pulse);
    this.reels.forEach((reel) => {
      reel.pulse(1 + 0.12 * Math.abs(Math.sin(now / 160)));
      reel.light(0.55 + 0.45 * pulse);
    });
  }

  // A show ended: the lights, the line and the marquee go back as they rest. The win meter keeps its own time
  endShow() {
    this.celebrating = false;
    this.reels.forEach((reel) => {
      reel.pulse(1);
      reel.light(0);
    });
    this.display.title.tint = 0xffffff;
    this.display.halo.alpha = 0.3;
    this.display.scale.set(1);
    this.showPot(this.pot);
    this.placeLine();
    if (!this.spinning) {
      this.setLights("rest");
    }
  }

  // A new pull stops whatever is still showing
  calm() {
    this.endShow();
    this.quietBelly();
  }

  // ---- The page ----

  preview(value) {
    this.bet = Number(value) || 0;
    this.showLine();
  }

  jackpot(amount) {
    this.pot = amount ?? null;
    if (!this.celebrating) {
      this.rollPot(this.pot);
    }
    this.showLine();
  }

  destroy() {
    this.closed = true;
    this.grip = null;
    clearTimeout(this.armed);
    clearTimeout(this.waiting);
    this.stage.app.ticker?.remove(this.frame);
    this.canvas.removeEventListener("pointercancel", this.cancelled);
  }
}

// ---- The reels ----

// One reel symbol, drawn about size across. The blank stop is a smaller plate, so the strip reads as gaps between
// symbols
function makeSymbol(name, size, art) {
  const piece = new Sprite({ texture: art[name], label: name });
  piece.anchor.set(0.5);
  const across = name === "blank" ? size * 0.6 : size * 0.92;
  piece.scale.set(across / Math.max(piece.texture.width, piece.texture.height));
  return piece;
}

// A slot on the reel's strip: every symbol, one showing at a time
function makeSlot(size, art) {
  const slot = new Container({ label: "slot" });
  slot.symbols = Object.fromEntries(
    SYMBOLS.map((name) => {
      const piece = makeSymbol(name, size, art);
      piece.visible = false;
      slot.addChild(piece);
      return [name, piece];
    }),
  );
  return slot;
}

// The drum curves away at the top and bottom of its window, so it darkens there
function drumShade(width, height) {
  const shade = new Graphics();
  for (let band = 0; band < 24; band += 1) {
    const depth = (height / 2) * (band / 24);
    const alpha = 0.022 + 0.012 * (band / 24);
    shade.rect(-width / 2 - 8, -height / 2 - 8, width + 16, height / 2 - depth).fill({ color: INK, alpha });
    shade.rect(-width / 2 - 8, depth, width + 16, height / 2 - depth + 8).fill({ color: INK, alpha });
  }
  return shade;
}

// A reel: a cream drum behind a window, with four slots that scroll down as its place grows. Place p shows strip stop
// -p on the line, so as the place grows the strip runs down the window in the bot's order, the stop above the line
// being the one before it. The reel and its slots carry labels, and each symbol its name, so a test can read the window
class Reel {
  constructor([x0, y0, x1, y1], art, label) {
    const width = x1 - x0;
    const height = y1 - y0;
    this.cell = height * 0.5;
    this.box = new Container({ label });
    this.box.position.set(x0 + width / 2, y0 + height / 2);
    const area = [-width / 2 - 8, -height / 2 - 8, width + 16, height + 16];
    const drum = new Graphics().rect(...area).fill(CREAM);
    const strip = new Container({ label: "strip" });
    this.slots = [0, 1, 2, 3].map(() => makeSlot(Math.min(width, this.cell) * 0.82, art));
    strip.addChild(...this.slots);
    // Blurs the strip up and down as it speeds by, so a spin reads as motion; off while the reel stands still
    this.smear = new BlurFilter({ strength: 0, quality: 3 });
    this.smear.strengthX = 0;
    this.smear.enabled = false;
    strip.filters = [this.smear];
    // The jackpot lights the drum up gold behind the symbol on the line, and turns the line gold
    this.lamp = glow(width * 0.62, 0xffa424, 1.7);
    this.lamp.blendMode = "normal";
    this.payline = new Graphics().rect(-width / 2 - 8, -2, width + 16, 4).fill(0xffffff);
    this.light(0);
    const mask = new Graphics().rect(...area).fill(0xffffff);
    this.box.addChild(drum, this.lamp, strip, drumShade(width, height), this.payline, mask);
    this.box.mask = mask;
    this.pos = 0;
    this.speed = 0;
    // Where the reel is over time while it moves, the place it lands on, and when it is done
    this.motion = null;
    this.target = null;
    this.until = 0;
  }

  // Draws the reel at a place, its symbols stretched, faded and blurred the faster it goes. The blur is in screen
  // pixels, so it follows the reel's size on screen
  draw(pos, speed) {
    this.pos = pos;
    this.speed = speed;
    const top = Math.floor(pos) - 1;
    const blur = Math.min(1, Math.max(0, speed - SHARP) / (0.04 - SHARP));
    const smear = blur * this.cell * BLUR_SHARE_OF_CELL * Math.abs(this.box.worldTransform.d);
    this.smear.enabled = smear >= 0.5;
    this.smear.strengthY = this.smear.enabled ? smear : 0;
    this.slots.forEach((slot, index) => {
      const at = top + index;
      const name = STRIP[mod(-at, STRIP.length)];
      for (const [key, piece] of Object.entries(slot.symbols)) {
        piece.visible = key === name;
      }
      slot.y = (pos - at) * this.cell;
      slot.scale.set(1, 1 + 0.45 * blur);
      slot.alpha = 1 - 0.32 * blur;
    });
  }

  update(now) {
    if (this.motion && now >= this.until) {
      this.settle();
    } else if (this.motion) {
      const { pos, speed } = this.motion(now);
      this.draw(pos, speed);
    }
  }

  state(now) {
    return this.motion ? this.motion(now) : { pos: this.pos, speed: 0 };
  }

  spinUp(motion) {
    this.motion = motion;
    this.target = null;
    this.until = Infinity;
  }

  landOn(plan, until) {
    this.motion = plan.motion;
    this.target = plan.target;
    this.until = until;
  }

  // Ends a landing on exactly its stop, kept to one turn of the strip
  settle() {
    if (this.target !== null) {
      this.rest(this.target);
    }
  }

  rest(pos) {
    this.motion = null;
    this.target = null;
    this.draw(mod(pos, STRIP.length), 0);
  }

  pulse(size) {
    this.slots.forEach((slot) => slot.scale.set(Math.abs(slot.y) < this.cell / 2 ? size : 1));
  }

  // 0 to 1: how lit the symbol on the line and the line are
  light(amount) {
    this.lamp.alpha = amount;
    this.payline.tint = amount > 0 ? GOLD_LIGHT : RED;
    this.payline.alpha = amount > 0 ? 0.6 + 0.4 * amount : 0.55;
  }
}
