// The pieces every table shares, so all the tables' cards, chips, dice and coins match: pictures from art/kit/,
// readable marks drawn as text, and the animations that move them. Every animation resolves within the ms it gets.
// Positions are {x, y} in the parent container's space. Call loadArt() once before drawing anything.
import { Assets, Container, Sprite, Text } from "../vendor/pixi.min.mjs";
import { chipLabel } from "../format.js";
import { DENOMINATIONS } from "../tray.js";
import { ease, tween } from "./kit.js";

export { DENOMINATIONS };

export const CARD = { width: 120, height: 168 };
const CHIP = 52;
const DIE = 48;
const COIN = 80;
// Scenes write words in Playfair Display, so loadArt() waits for it. Its numbers are old-style (a "10" reads like
// "IO"), so card ranks and chip values use the page's bold sans-serif, whose numbers line up
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const RED = 0xc8202f;
const INK = 0x1a0f08;
const CREAM = 0xf6ecd2;
const BURGUNDY = 0x6b0f1a;
const GOLD = 0xd4af37;
// Each texture's file in art/kit/, by the name the code uses
const FILES = {
  back: "card-back.png",
  face: "card-face.png",
  spades: "suit-spades.png",
  hearts: "suit-hearts.png",
  diamonds: "suit-diamonds.png",
  clubs: "suit-clubs.png",
  J: "court-jack.png",
  Q: "court-queen.png",
  K: "court-king.png",
  chip: "chip.png",
  spots: "chip-spots.png",
  die1: "die-1.png",
  die2: "die-2.png",
  die3: "die-3.png",
  die4: "die-4.png",
  die5: "die-5.png",
  die6: "die-6.png",
  heads: "coin-heads.png",
  tails: "coin-tails.png",
  edge: "coin-edge.png",
  spark: "spark.png",
};
const RED_SUITS = new Set(["hearts", "diamonds"]);
// Where a number card's pips sit, in card units from its center: columns at -22, 0 and 22
const PIPS = {
  2: [[0, -52], [0, 52]],
  3: [[0, -52], [0, 0], [0, 52]],
  4: [[-22, -52], [22, -52], [-22, 52], [22, 52]],
  5: [[-22, -52], [22, -52], [0, 0], [-22, 52], [22, 52]],
  6: [[-22, -52], [22, -52], [-22, 0], [22, 0], [-22, 52], [22, 52]],
  7: [[-22, -52], [22, -52], [0, -26], [-22, 0], [22, 0], [-22, 52], [22, 52]],
  8: [[-22, -52], [22, -52], [0, -26], [-22, 0], [22, 0], [0, 26], [-22, 52], [22, 52]],
  9: [[-22, -52], [22, -52], [-22, -17], [22, -17], [0, 0], [-22, 17], [22, 17], [-22, 52], [22, 52]],
  10: [[-22, -52], [22, -52], [0, -35], [-22, -17], [22, -17], [-22, 17], [22, 17], [0, 35], [-22, 52], [22, 52]],
};

const textures = {};
const colors = {};
let loading = null;

async function load() {
  const base = new URL("../art/kit/", import.meta.url).href;
  const names = Object.keys(FILES);
  const loaded = await Promise.all(
    names.map((name) => Assets.load({ src: base + FILES[name], data: { autoGenerateMipmaps: true } })),
  );
  names.forEach((name, index) => {
    textures[name] = loaded[index];
  });
  try {
    await document.fonts.load(`700 24px ${FONT}`);
  } catch (e) {
    console.warn("Casino: couldn't load Playfair Display", e);
  }
}

export function loadArt() {
  if (!loading) {
    loading = load().catch((e) => {
      console.error("Casino: couldn't load the art kit", e);
      loading = null;
      throw e;
    });
  }
  return loading;
}

// A color from the page's tokens in style.css, as a number for Pixi
function token(name) {
  if (!(name in colors)) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    colors[name] = value ? parseInt(value.replace("#", ""), 16) : CREAM;
  }
  return colors[name];
}

function isLight(color) {
  const r = (color >> 16) & 255;
  const g = (color >> 8) & 255;
  const b = color & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 150;
}

function sprite(name, width, height = width) {
  const piece = new Sprite(textures[name]);
  piece.anchor.set(0.5);
  piece.width = width;
  piece.height = height;
  return piece;
}

function label(text, size, fill) {
  const mark = new Text({ text, style: { fontFamily: MARKS, fontWeight: "700", fontSize: size, fill }, resolution: 4 });
  mark.anchor.set(0.5);
  return mark;
}

// Time left before a deadline, so a run of steps ends exactly when the whole animation should
function left(end) {
  return Math.max(1, end - performance.now());
}

// Runs apply(k) every frame as k goes from 0 to 1 over ms; stops early if the piece is destroyed
function progress(piece, ms, apply, curve = ease.linear) {
  let value = 0;
  const driver = {
    get destroyed() {
      return piece.destroyed;
    },
    get k() {
      return value;
    },
    set k(next) {
      value = next;
      apply(next);
    },
  };
  return tween(driver, { k: 1 }, Math.max(1, ms), curve);
}

// ---- Cards ----

// One corner's rank and suit; the opposite corner is the same turned upside down
function corner(rank, suit, color) {
  const mark = new Container();
  const text = label(rank, rank === "10" ? 20 : 24, color);
  const pip = sprite(suit, 15);
  pip.position.set(0, 22);
  mark.addChild(text, pip);
  return mark;
}

function centerPieces(rank, suit) {
  if (rank === "A") {
    return [sprite(suit, 58)];
  }
  if (rank in PIPS) {
    return PIPS[rank].map(([x, y]) => {
      const pip = sprite(suit, 22);
      pip.position.set(x, y);
      pip.rotation = y > 0 ? Math.PI : 0;
      return pip;
    });
  }
  const portrait = sprite(rank, 68, 108);
  const corners = [-1, 1].map((side) => {
    const pip = sprite(suit, 14);
    pip.position.set(side * 24, side * -44);
    pip.rotation = side > 0 ? 0 : Math.PI;
    return pip;
  });
  return [portrait, ...corners];
}

function drawFace(face, card) {
  face.removeChildren().forEach((child) => child.destroy({ children: true }));
  const [rank, suit] = card;
  const color = RED_SUITS.has(suit) ? RED : INK;
  face.addChild(sprite("face", CARD.width, CARD.height), ...centerPieces(rank, suit));
  const top = corner(rank, suit, color);
  top.position.set(-CARD.width / 2 + 13, -CARD.height / 2 + 18);
  const bottom = corner(rank, suit, color);
  bottom.position.set(CARD.width / 2 - 13, CARD.height / 2 - 18);
  bottom.rotation = Math.PI;
  face.addChild(top, bottom);
}

export function cardSprite(card) {
  const piece = new Container();
  piece.face = new Container();
  piece.back = sprite("back", CARD.width, CARD.height);
  piece.addChild(piece.face, piece.back);
  showCard(piece, card);
  return piece;
}

export function showCard(piece, card) {
  piece.card = card;
  piece.back.visible = !card;
  piece.face.visible = Boolean(card);
  if (card) {
    drawFace(piece.face, card);
  }
}

export async function dealCard(piece, from, to, ms) {
  const turn = (Math.random() < 0.5 ? -1 : 1) * (0.3 + Math.random() * 0.15);
  piece.visible = true;
  piece.position.set(from.x, from.y);
  piece.rotation = turn;
  await progress(piece, ms, (k) => {
    const glide = ease.out(k);
    piece.x = from.x + (to.x - from.x) * glide;
    piece.y = from.y + (to.y - from.y) * glide;
    piece.rotation = turn * (1 - k) ** 2 * Math.cos(k * 4);
  });
  if (!piece.destroyed) {
    piece.position.set(to.x, to.y);
    piece.rotation = 0;
  }
}

export async function flipCard(piece, card, ms) {
  const end = performance.now() + ms;
  const width = piece.scale.x;
  const height = piece.scale.y;
  const y = piece.y;
  const lift = (k) => {
    piece.scale.y = height * (1 + 0.08 * k);
    piece.y = y - 8 * k;
  };
  await progress(piece, ms / 2, (k) => {
    piece.scale.x = width * (1 - k);
    lift(k);
  }, ease.inOut);
  if (piece.destroyed) {
    return;
  }
  showCard(piece, card);
  await progress(piece, left(end), (k) => {
    piece.scale.x = width * k;
    lift(1 - k);
  }, ease.inOut);
  if (!piece.destroyed) {
    piece.scale.set(width, height);
    piece.y = y;
  }
}

// ---- Chips ----

export function chipSprite(value) {
  const color = token(`--chip-${value}`);
  const piece = new Container();
  const body = sprite("chip", CHIP);
  body.tint = color;
  const spots = sprite("spots", CHIP);
  spots.tint = isLight(color) ? BURGUNDY : CREAM;
  const text = chipLabel(value);
  const mark = label(text, text.length > 3 ? 12 : text.length > 2 ? 14 : 17, isLight(color) ? INK : CREAM);
  piece.addChild(body, spots, mark);
  piece.value = value;
  return piece;
}

// The fewest chips that make amount, largest first
function breakdown(amount) {
  const chips = [];
  let rest = Math.max(0, Math.floor(amount));
  for (const value of [...DENOMINATIONS].reverse()) {
    while (rest >= value) {
      chips.push(value);
      rest -= value;
    }
  }
  return chips;
}

export function chipStack(amount) {
  const stack = new Container();
  stack.amount = amount;
  const chips = breakdown(amount);
  const columns = Math.ceil(chips.length / 12);
  chips.forEach((value, index) => {
    const column = Math.floor(index / 12);
    const chip = chipSprite(value);
    chip.x = (column - (columns - 1) / 2) * (CHIP + 6) + (Math.random() - 0.5) * 3;
    chip.y = -(index % 12) * 5 + (Math.random() - 0.5) * 1.5;
    stack.addChild(chip);
  });
  return stack;
}

export async function moveChips(stack, to, ms) {
  const from = { x: stack.x, y: stack.y };
  await progress(stack, ms, (k) => {
    const glide = ease.inOut(k);
    stack.x = from.x + (to.x - from.x) * glide;
    stack.y = from.y + (to.y - from.y) * glide - Math.sin(k * Math.PI) * 18;
  });
  if (!stack.destroyed) {
    stack.position.set(to.x, to.y);
  }
}

// ---- Dice ----

export function dieSprite(face) {
  const piece = new Container();
  piece.pips = sprite(`die${face}`, DIE);
  piece.addChild(piece.pips);
  piece.face = face;
  return piece;
}

function showFace(die, face) {
  die.face = face;
  die.pips.texture = textures[`die${face}`];
}

// How high a thrown die is at k (0 to 1): one long flight, then two shrinking hops, then it rests
function bounce(k) {
  const hops = [
    [0, 0.5, 1],
    [0.5, 0.75, 0.35],
    [0.75, 0.9, 0.12],
  ];
  for (const [start, stop, height] of hops) {
    if (k < stop) {
      return height * Math.sin(((k - start) / (stop - start)) * Math.PI);
    }
  }
  return 0;
}

function tumble(die, face, from, to, spin, end) {
  const scale = die.scale.x;
  let shown = 0;
  return progress(die, left(end), (k) => {
    const glide = ease.out(k);
    const height = bounce(k);
    die.x = from.x + (to.x - from.x) * glide;
    die.y = from.y + (to.y - from.y) * glide - height * 70;
    die.scale.set(scale * (1 + height * 0.3));
    die.rotation = spin * (1 - glide) + to.tilt * glide;
    const flash = Math.floor(k * 14);
    if (k >= 0.9) {
      showFace(die, face);
    } else if (flash !== shown) {
      shown = flash;
      showFace(die, 1 + Math.floor(Math.random() * 6));
    }
  });
}

export async function rollDice(dice, faces, from, to, ms) {
  const end = performance.now() + ms;
  const spread = DIE * 0.7;
  await Promise.all(
    dice.map((die, index) => {
      const side = dice.length === 1 ? 0 : index === 0 ? -1 : 1;
      die.visible = true;
      const start = { x: from.x + side * 10, y: from.y + side * 6 };
      const land = { x: to.x + side * spread, y: to.y + side * 4, tilt: (Math.random() - 0.5) * 0.25 };
      const spin = (side || 1) * (9 + Math.random() * 3);
      return tumble(die, faces[index], start, land, spin, end);
    }),
  );
}

// ---- Coin ----

export function coinSprite(side) {
  const piece = new Container();
  piece.edge = sprite("edge", COIN, COIN * 0.1);
  piece.edge.visible = false;
  piece.disc = sprite(side, COIN);
  piece.addChild(piece.edge, piece.disc);
  piece.side = side;
  return piece;
}

function turnCoin(coin, angle, start, other) {
  const face = Math.cos(angle);
  const side = Math.floor(angle / Math.PI + 0.5) % 2 === 0 ? start : other;
  coin.disc.texture = textures[side];
  coin.disc.scale.y = Math.abs(coin.disc.scale.x * face);
  coin.edge.visible = Math.abs(face) < 0.95;
  coin.edge.height = COIN * 0.1 * Math.abs(Math.sin(angle));
  coin.edge.y = (face > 0 ? 1 : -1) * (COIN / 2) * Math.abs(face);
}

export async function flipCoin(coin, side, ms) {
  const start = coin.side;
  const other = start === "heads" ? "tails" : "heads";
  const turns = 8 + (side === start ? 0 : 1);
  const y = coin.y;
  const scale = coin.scale.x;
  await progress(coin, ms, (k) => {
    const air = Math.min(1, k / 0.82);
    const height = k < 0.82 ? Math.sin(air * Math.PI) : 0.08 * Math.sin(((k - 0.82) / 0.18) * Math.PI);
    coin.y = y - height * 150;
    coin.scale.set(scale * (1 + height * 0.6));
    turnCoin(coin, ease.out(air) * turns * Math.PI, start, other);
  });
  if (!coin.destroyed) {
    coin.y = y;
    coin.scale.set(scale);
    coin.side = side;
    turnCoin(coin, 0, side, start);
  }
}

// ---- Sparkle ----

function sparkPieces(burst) {
  const pieces = [];
  for (let index = 0; index < 16; index += 1) {
    const spark = sprite("spark", 20 + Math.random() * 22);
    spark.tint = Math.random() < 0.5 ? 0xffffff : GOLD;
    const angle = (index / 16) * Math.PI * 2 + Math.random() * 0.3;
    pieces.push({ piece: spark, angle, reach: 70 + Math.random() * 60, fall: 0, turn: Math.random() * 4 - 2 });
  }
  for (let index = 0; index < 4; index += 1) {
    const coin = sprite(index % 2 ? "tails" : "heads", 18);
    const angle = -Math.PI / 2 + (index - 1.5) * 0.6;
    pieces.push({ piece: coin, angle, reach: 60 + Math.random() * 30, fall: 90, turn: Math.random() * 6 - 3 });
  }
  pieces.forEach(({ piece }) => burst.addChild(piece));
  return pieces;
}

export async function sparkle(parent, x, y, ms) {
  const burst = new Container();
  burst.position.set(x, y);
  parent.addChild(burst);
  const pieces = sparkPieces(burst);
  await progress(burst, ms, (k) => {
    const spread = ease.out(k);
    for (const { piece, angle, reach, fall, turn } of pieces) {
      piece.x = Math.cos(angle) * reach * spread;
      piece.y = Math.sin(angle) * reach * spread + fall * k * k;
      piece.rotation = turn * k;
      piece.alpha = k < 0.6 ? 1 : 1 - (k - 0.6) / 0.4;
    }
  });
  if (!burst.destroyed) {
    burst.destroy({ children: true });
  }
}
