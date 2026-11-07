// One seat at the Hold'em table. Every seat looks the same: the player's face in a gold rim, on the table's brass
// plaque, with a dark plate holding their name and chips on its outer side (under the face for the seats along the
// bottom, over it for those along the top). The name always shows. Their two cards sit tucked behind the face; at a
// showdown they come out over the face, face up, and the plate's second line names the hand. The player's own cards
// lie big and face up over their face, with the name of their hand in a tag under them. While a betting round lasts,
// a tag on the face says what the seat last did ("Raise 400").
//
// The chips a seat has bet this round sit on the felt in front of it, with their amount. A seat lives in two layers,
// its group and its bet; the scene says where both go (holdem.js's layoutFor) and plays the events. The table's state
// arrives up to 4 times a second, so a seat only redraws the parts whose words or pictures changed.
import { CanvasTextMetrics, Container, Graphics, Sprite, Text, Texture } from "../vendor/pixi.min.mjs";
import { money } from "../format.js";
import { CARD, DENOMINATIONS, cardSprite, chipSprite, flipCard, moveChips, showCard } from "./art.js";
import { ease, tween, wait } from "./kit.js";

// Sizes in table units at a seat scale of 1. On a small screen the scene draws seats bigger than the table around
// them (the seat scale, k), so names stay readable
export const FACE = 28;
export const RIM = 3;
export const PLATE = { height: 42, pad: 10, overlap: 10 };
export const NAME_FONT = 14;
const STACK_FONT = 14;
export const CHIP = 26;
// The dealer button: a badge this wide at the end of the dealer's plate toward the middle of the table, level with
// the plate, so it never meets the face's tag or cards shown over the face. The viewer's own is at their plate's left
export const BUTTON = 24;
// The label beside a bet or a pot: big enough to read on a phone, like the names
export const SUM = { font: 14, height: 24 };
// A tag on the face (the last move, Away, Waiting) or under the player's own cards (their hand). A face's tag has its
// middle this far from the face's middle, toward the felt
export const TAG = { font: 14, height: 20, y: FACE - 4 };
// A pile of chips on the felt is at most this many high, so it never climbs over the cards; bigger amounts grow
// sideways into more columns. Piles stand tall where the screen has the room, and low where it would make the table
// smaller
export const PILE = { tall: 5, low: 3, columns: 2 };
// How far apart a pile's columns stand, in table units
export const COLUMN = 29;
// The smallest words on screen, in CSS pixels: an amount shrinks to this before it shortens
export const SMALLEST = 10;

// How far each chip in a pile sits above the one under it, in chip units (a chip is 52 across): further where the
// table has room for tall piles
function chipRise(most) {
  return most >= PILE.tall ? 7 : 5;
}

// How far up a pile at most this high its chip `index` (0 at the bottom) sits, in chip units. Where the table has
// room for tall piles, the second chip stands further above the first than the rest, so a pile of two never reads as
// one thick chip; low piles keep the room they have
const SECOND_RISE = 5;
function chipHeight(index, most) {
  const second = index > 0 && most >= PILE.tall ? SECOND_RISE : 0;
  return index * chipRise(most) + second;
}

// How far the top chip of a pile at most this high sits above the bottom one, in table units
export function pileRise(most) {
  return (CHIP / 52) * chipHeight(most - 1, most);
}
// Where a crowded table puts a bet's amount: in a label at least this wide under its chips (most where its row has
// the room), its middle drop below theirs
export const UNDER = { width: 58, most: 72, drop: 21 };
// A label's words sit this far in from its ends, as a share of its height; an amount sits this far from its chips
export const PAD = 0.3;
export const GAP = 3;
// Card scales: tucked behind a face, shown over it at the showdown, and the player's own (about 1.6 times the others)
const CARD_SCALE = { tucked: 0.34, shown: 0.36, hero: 0.55 };
// A seat's winning shown card at a showdown: how far it lifts away from the plate, in seat units, and how far its
// glow's line sits out from its edge and how wide it is, in card units
export const WON_CARD = { lift: 6, out: 3, width: 5 };
// How far toward the plate tucked cards sit from the face's middle: their edge toward the felt stays clear of the tag
const TUCK = 23;
// The player's own cards sit this far above their face, with room between them and the plate for their hand's tag
// (this tall), which hangs this far over the plate's top edge (above the name's letters) and may grow this wide where
// the cards are narrower, before its words shrink
const HERO_RISE = 43;
const HAND = { height: 17, dip: 3, wide: 170 };
// The name's middle sits this far above the plate's middle, the stack's this far below it
const LINES = { name: -7, stack: 10 };

// The player's own two cards at big times their usual size (the upright table draws them bigger): their scale, how
// far above the face they sit (their bottom stays where it is, clear of the plate and the hand's tag), how far apart,
// how wide the pair lies (and so the hand's tag under them), and where their top is
export function heroSize(spot) {
  const big = spot.big ?? 1;
  const scale = CARD_SCALE.hero * big;
  const rise = HERO_RISE + (CARD.height * (scale - CARD_SCALE.hero)) / 2;
  const spread = 24 * big;
  const width = 2 * (spread + (CARD.width * scale) / 2);
  return { scale, rise, spread, width, top: -rise - (CARD.height * scale) / 2 };
}

// How wide the player's own hand's tag may grow, in table units
function handWidth(spot) {
  return Math.max(heroSize(spot).width, HAND.wide);
}
// How long a turn lasts (the bot's DECISION_TIME), for the share of the clock still to drain
export const TURN_SECONDS = 35;
// The turn ring's dark track: this wide, its middle this far inside the colored arc's, so it reaches past the arc's
// outer edge a little and in over the face's gold rim
const RING_TRACK = { width: 10, inside: 1.25 };
// How solid an empty seat's "Sit" disc is
export const SIT_FILL = 0.92;
// How far beside the player's own cards their win's sparkles start, in table units: half the biggest sparkle, turned
const SPARK_CLEAR = 32;
// How far a burst's sparkles fly from where it starts at most, a turned sparkle's corner included, and how far either
// side of its way they spread (art.js sparkle), in table units and radians
const SPARK_REACH = 160;
const SPARK_SPREAD = Math.PI / 3;
// Players' pictures are cut round once at this size, in pixels
const PICTURE = 128;
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const GOLD_DEEP = 0x8a6a14;
const INK = 0x1a0f08;
const GREY = 0x6b6355;
const GREEN = 0x5ad17a;
const AMBER = 0xffb020;
const ALARM = 0xff4d4d;
const ALL_IN = 0xff7a7a;
const SHADOW = { color: 0x000000, alpha: 0.75, blur: 3, distance: 1.5, angle: Math.PI / 2 };
// Background colors for faces without a picture, picked by name so a person keeps theirs
const FACE_COLORS = [0x2f6f8f, 0x8f3f6f, 0x3f8f5f, 0x8f6f2f, 0x5f4f9f, 0x9f4f3f];
// What each move says on the face's tag, and its color
const MOVES = {
  blind: { color: CREAM },
  post: { word: "Posted", color: CREAM },
  fold: { word: "Fold", color: 0xb8ae98 },
  check: { word: "Check", color: 0xa8d4ff },
  call: { word: "Call", color: GREEN },
  raise: { word: "Raise", color: GOLD_LIGHT },
  bet: { word: "Bet", color: GOLD_LIGHT },
  all_in: { word: "All in", color: ALL_IN },
  return: { word: "Got back", color: CREAM },
};

// What a person sees as single characters, so a flag or a joined emoji is never split
const segmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

function characters(text) {
  return segmenter ? Array.from(segmenter.segment(text), (part) => part.segment) : Array.from(text);
}

// The words as long as fit the width, cut by whole characters
function cutWords(text, style, width) {
  const fits = (words) => CanvasTextMetrics.measureText(words, style).width <= width;
  const whole = String(text || "");
  if (fits(whole)) {
    return whole;
  }
  const letters = characters(whole);
  for (let count = letters.length - 1; count > 0; count -= 1) {
    const cut = `${letters.slice(0, count).join("").trimEnd()}…`;
    if (fits(cut)) {
      return cut;
    }
  }
  return "…";
}

export function words(text, size, fill) {
  const piece = new Text({
    text,
    style: { fontFamily: MARKS, fontWeight: "700", fontSize: size, fill, dropShadow: SHADOW },
    resolution: 3,
  });
  piece.anchor.set(0.5);
  return piece;
}

function setText(piece, text) {
  if (piece.text !== text) {
    piece.text = text;
  }
}

// A rounded label; its words and colors are redrawn only when they change. size: its words' size
export function pill(size, height) {
  const piece = new Container();
  piece.back = new Graphics();
  piece.words = words("", size, CREAM);
  piece.size = height;
  piece.font = size;
  piece.look = "";
  piece.span = 0;
  piece.addChild(piece.back, piece.words);
  return piece;
}

// look: {fill, stroke, back}. size: the words' size, when smaller than the label's own
export function setPill(piece, text, look, size = piece.font) {
  const key = JSON.stringify([text, look, size]);
  if (piece.look === key) {
    return;
  }
  piece.look = key;
  if (piece.words.style.fontSize !== size) {
    piece.words.style.fontSize = size;
  }
  setText(piece.words, text);
  piece.words.style.fill = look.fill;
  piece.span = piece.words.width + piece.size * PAD * 2;
  piece.back
    .clear()
    .roundRect(-piece.span / 2, -piece.size / 2, piece.span, piece.size, piece.size / 2)
    .fill({ color: look.back ?? INK, alpha: look.back ? 0.95 : 0.8 })
    .stroke({ width: 1.5, color: look.stroke });
}

// What a seat's last move says, "Raise 400", "Check", "Small blind", and its color; shorter holds the move alone, for
// a tag too narrow for the amount. word overrides the move's word, such as "Bet" for the first chips of a round
export function moveWords(last, stakes, word = null) {
  if (!last) {
    return null;
  }
  const move = MOVES[word || last.move] || MOVES.call;
  if (last.move === "blind") {
    const text = `${last.amount >= (stakes?.big ?? 0) ? "Big" : "Small"} blind`;
    return { text, color: move.color };
  }
  if (last.move === "return") {
    // How much came back, when the scene saw the bet before it: "Got 40 back", and "40 back" on a tight tag
    if (!last.back) {
      return { text: "Got chips back", shorter: [move.word], color: move.color };
    }
    return { text: `Got ${money(last.back)} back`, shorter: [`${money(last.back)} back`], color: move.color };
  }
  const amount = ["raise", "call", "post"].includes(last.move) && last.amount ? ` ${money(last.amount)}` : "";
  return { text: `${move.word}${amount}`, shorter: [move.word], color: move.color };
}

// Every way to say some words ({text, shorter}), longest first
function choicesOf(words) {
  return [words.text, ...(words.shorter || [])];
}

// The words that fit width: the first choice that fits whole, else the last one cut short
export function fitWords(choices, style, width) {
  const fitting = choices.filter(Boolean);
  for (const choice of fitting) {
    if (CanvasTextMetrics.measureText(choice, style).width <= width) {
      return choice;
    }
  }
  return cutWords(fitting[fitting.length - 1] || "", style, width);
}

// The first choice that fits width at size or smaller, down to least: each choice shrinks to least before the next
// one is tried. Nothing is cut: with no choice fitting, the last one at least. style is measured at its own size
export function fitSized(choices, style, width, least, size) {
  for (const choice of choices) {
    const wide = (CanvasTextMetrics.measureText(choice, style).width * size) / style.fontSize;
    const fits = Math.floor(Math.min(size, (size * width) / wide) * 2) / 2;
    if (fits >= least) {
      return { text: choice, size: fits };
    }
  }
  return { text: choices[choices.length - 1], size: least };
}

// An amount in few characters, for a bet's label with no room even at the smallest size: 1.2K, 12.3K, 123K, 1.2M
// with one decimal, or 1K, 12K with none. It rounds down, so it never claims more than there is
export function shortMoney(amount, decimals = 1) {
  const units = [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, mark] of units) {
    if (amount >= size) {
      const value = amount / size;
      const step = value >= 100 ? 1 : 10 ** decimals;
      return `${Math.floor(value * step) / step}${mark}`;
    }
  }
  return money(amount);
}

// Ranks as poker writes them short: a letter for a court card or an Ace ("Ks", "Q"), a number as it is ("7s")
const RANK_LETTERS = { Ace: "A", Aces: "As", King: "K", Kings: "Ks", Queen: "Q", Queens: "Qs", Jack: "J", Jacks: "Js" };

function short(rank) {
  return RANK_LETTERS[rank] ?? rank;
}

// A rank in the plural, short unless it is Aces: "As" alone reads as a word
function many(rank) {
  return rank === "Aces" ? rank : short(rank);
}

// Shorter ways to name a hand, for a tight label: in poker's own short words ("Pair of Qs", "Q high", "Trips 7s",
// "Two pair, Ks & 7s"), then its ranks alone ("Ks & 7s", "Ks full", "K flush"), then the hand alone ("Pair", "Two
// pair"). Aces keep their word where "As" would read as a word: "Pair of Aces", "Aces & 7s"
const HAND_SHORTHAND = [
  [/^High card, (.+)$/, (rank) => [`${short(rank)} high`]],
  [/^Pair of (.+)$/, (rank) => [`Pair of ${many(rank)}`, "Pair"]],
  [
    /^Two pair, (.+) and (.+)$/,
    (high, low) => [`Two pair, ${short(high)} & ${short(low)}`, `${many(high)} & ${short(low)}`, "Two pair"],
  ],
  [/^Three of a kind, (.+)$/, (rank) => [`Trips ${short(rank)}`, "Trips"]],
  [
    /^Straight, (.+) high$/,
    (rank) => [`Straight, ${short(rank)} high`, `${short(rank)}-high straight`, `${short(rank)} straight`, "Straight"],
  ],
  [
    /^Flush, (.+) high$/,
    (rank) => [`Flush, ${short(rank)} high`, `${short(rank)}-high flush`, `${short(rank)} flush`, "Flush"],
  ],
  [
    /^Full house, (.+) over (.+)$/,
    (high, low) => [`${short(high)} full of ${short(low)}`, `${many(high)} full`, "Full house"],
  ],
  [/^Four of a kind, (.+)$/, (rank) => [`Quads ${short(rank)}`, "Quads"]],
  [/^Straight flush, .+$/, () => ["Straight flush", "Str. flush"]],
];

export function handNames(name) {
  const known = HAND_SHORTHAND.find(([pattern]) => pattern.test(name));
  const shorter = known ? known[1](...name.match(known[0]).slice(1)) : [name.split(",")[0]];
  return [...new Set([name, ...shorter])];
}

// ---- Chips ----

// The fewest chips that make amount, largest first
function fewest(amount) {
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

// A pile of chips for the felt: the fewest chips that make amount exactly, in columns at most `most` high, each
// column's biggest chip on top. Only past PILE.columns full columns are the smallest chips left over dropped.
// toward: the side its next columns stand on (-1 or 1), or 0 to center them
export function chipPile(amount, most, toward = 0) {
  const chips = fewest(amount).slice(0, most * PILE.columns);
  const columns = Math.ceil(chips.length / most);
  const pile = new Container();
  for (let column = 0; column < columns; column += 1) {
    const across = toward ? toward * column : column - (columns - 1) / 2;
    // Drawn bottom to top, so the column's smallest chip is at the bottom and its biggest on top
    const stack = chips.slice(column * most, (column + 1) * most).reverse();
    stack.forEach((value, index) => {
      const chip = chipSprite(value);
      chip.x = across * COLUMN * 2 + (Math.random() - 0.5) * 3;
      chip.y = -chipHeight(index, most) + (Math.random() - 0.5) * 1.5;
      pile.addChild(chip);
    });
  }
  pile.scale.set(CHIP / 52);
  pile.columns = columns;
  return pile;
}

// How far a pile reaches either side of where it stands, in its parent's units: its columns may all stand to one side
export function pileReach(stack) {
  const bounds = stack.getLocalBounds();
  return Math.max(-bounds.minX, bounds.maxX) * Math.abs(stack.scale.x);
}

// Whether the straight way from a to b passes through the box's inside
export function crosses(a, b, box) {
  let [enter, leave] = [0, 1];
  const steps = [
    [-(b.x - a.x), a.x - box.left],
    [b.x - a.x, box.right - a.x],
    [-(b.y - a.y), a.y - box.top],
    [b.y - a.y, box.bottom - a.y],
  ];
  for (const [toward, room] of steps) {
    if (toward === 0) {
      if (room <= 0) {
        return false;
      }
      continue;
    }
    const at = room / toward;
    if (toward < 0) {
      enter = Math.max(enter, at);
    } else {
      leave = Math.min(leave, at);
    }
  }
  return leave - enter > 1e-6;
}

// Chips slide through each point in turn, as one smooth move: they speed up at the start and slow at the end
export async function slideChips(stack, points, ms) {
  if (points.length === 1) {
    await moveChips(stack, points[0], ms);
    return;
  }
  const path = [{ x: stack.x, y: stack.y }, ...points];
  const legs = path.slice(1).map((point, index) => Math.hypot(point.x - path[index].x, point.y - path[index].y));
  const total = legs.reduce((sum, leg) => sum + leg, 0) || 1;
  let travelled = 0;
  const driver = {
    get destroyed() {
      return stack.destroyed;
    },
    get d() {
      return travelled;
    },
    set d(value) {
      travelled = value;
      let rest = value;
      let leg = 0;
      while (leg < legs.length - 1 && rest > legs[leg]) {
        rest -= legs[leg];
        leg += 1;
      }
      const share = legs[leg] ? Math.min(1, rest / legs[leg]) : 1;
      stack.x = path[leg].x + (path[leg + 1].x - path[leg].x) * share;
      stack.y = path[leg].y + (path[leg + 1].y - path[leg].y) * share;
    },
  };
  await tween(driver, { d: total }, ms, ease.inOut);
}

// ---- Cards too small for their art ----

// Under this many CSS pixels wide, a face-up card shows a big rank and suit instead of its own art
export const SMALL_CARD = 45;
const CARD_RED = 0xc8202f;
// Each suit's mark as a letter, held to its plain text form so no font draws it as a colored emoji
const SUIT_MARKS = { spades: "♠︎", hearts: "♥︎", diamonds: "♦︎", clubs: "♣︎" };

function indexMark(text, size, fill) {
  const mark = new Text({ text, style: { fontFamily: MARKS, fontWeight: "800", fontSize: size, fill }, resolution: 4 });
  mark.anchor.set(0, 0);
  return mark;
}

// How wide a card is drawn on screen, in CSS pixels. Its own height measures it, which a flip leaves alone
export function drawnWidth(piece) {
  let scale = 1;
  for (let at = piece; at; at = at.parent) {
    scale *= Math.abs(at.scale.y);
  }
  return CARD.width * scale;
}

// A small face-up card wears a plain face with a big rank and suit in its top corner and a big suit in the other,
// so a Jack, a Queen and a King read apart on a phone; drawn bigger, the card shows its own art again
export function markSmall(piece, small) {
  const show = small && Boolean(piece.card) && piece.face.visible;
  const key = show ? piece.card.join(" ") : "";
  if ((piece.bigIndex?.key ?? "") === key) {
    return;
  }
  piece.bigIndex?.destroy({ children: true });
  piece.bigIndex = null;
  if (!show) {
    return;
  }
  const [rank, suit] = piece.card;
  const color = suit === "hearts" || suit === "diamonds" ? CARD_RED : INK;
  const index = new Container();
  index.label = "index";
  index.key = key;
  const { width, height } = CARD;
  const plain = new Graphics()
    .roundRect(-width / 2, -height / 2, width, height, 11)
    .fill(0xfbf5e6)
    .stroke({ width: 2, color: 0xcdbf9c });
  const big = indexMark(rank, rank === "10" ? 54 : 66, color);
  big.position.set(-width / 2 + 9, -height / 2 + 4);
  const mark = indexMark(SUIT_MARKS[suit], 52, color);
  mark.position.set(-width / 2 + 10, -height / 2 + 70);
  const corner = indexMark(SUIT_MARKS[suit], 64, color);
  corner.anchor.set(1, 1);
  corner.position.set(width / 2 - 8, height / 2 - 2);
  index.addChild(plain, big, mark, corner);
  piece.addChild(index);
  piece.bigIndex = index;
}

// ---- Faces ----

const pictures = new Map();

// A player's picture cut round, drawn once, so no mask runs every frame
function roundPicture(image) {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = PICTURE;
    const paint = canvas.getContext("2d");
    paint.beginPath();
    paint.arc(PICTURE / 2, PICTURE / 2, PICTURE / 2, 0, Math.PI * 2);
    paint.clip();
    paint.drawImage(image, 0, 0, PICTURE, PICTURE);
    return Texture.from(canvas);
  } catch (e) {
    console.warn("A player's picture couldn't be drawn, so their letter stays", e);
    return null;
  }
}

// A player's picture as a round texture, or null when it can't be had (the letter stays)
function loadPicture(url) {
  if (!pictures.has(url)) {
    pictures.set(
      url,
      new Promise((resolve) => {
        const image = new Image();
        image.crossOrigin = "anonymous";
        image.onload = () => resolve(roundPicture(image));
        image.onerror = () => resolve(null);
        image.src = url;
      }),
    );
  }
  return pictures.get(url);
}

function colorFor(name) {
  let sum = 0;
  for (const letter of String(name)) {
    sum = (sum * 31 + letter.codePointAt(0)) % 9973;
  }
  return FACE_COLORS[sum % FACE_COLORS.length];
}

// A CPU's face: a little robot with lit eyes, in its own color
function robot(name) {
  return new Graphics()
    .circle(0, 0, FACE)
    .fill(colorFor(name))
    .moveTo(0, -16)
    .lineTo(0, -22)
    .stroke({ width: 2, color: 0xd9dde0 })
    .circle(0, -23, 3)
    .fill(GOLD_LIGHT)
    .roundRect(-15, -16, 30, 25, 8)
    .fill(0xdfe4e7)
    .stroke({ width: 1.5, color: 0x7d8a94 })
    .circle(-6.5, -5, 4.2)
    .fill(INK)
    .circle(6.5, -5, 4.2)
    .fill(INK)
    .circle(-6.5, -5, 2.2)
    .fill(0x7ff3ff)
    .circle(6.5, -5, 2.2)
    .fill(0x7ff3ff)
    .roundRect(-7, 2.5, 14, 3.5, 1.5)
    .fill(0x4a5560)
    .roundRect(-12, 11, 24, 10, 4)
    .fill(0xb7c0c6);
}

// A face for someone: their picture once it loads, and their first letter until then or if it never does
export function personFace(holder, person, radius = FACE) {
  holder.removeChildren().forEach((child) => child.destroy({ children: true }));
  const back = new Graphics().circle(0, 0, radius).fill(colorFor(person.name));
  const letter = words(characters(String(person.name || "?"))[0]?.toUpperCase() ?? "?", radius * 0.95, CREAM);
  holder.addChild(back, letter);
  if (!person.avatar) {
    return;
  }
  const key = holder.key;
  loadPicture(person.avatar).then((texture) => {
    if (!texture || holder.destroyed || holder.key !== key) {
      return;
    }
    const picture = new Sprite(texture);
    picture.anchor.set(0.5);
    picture.width = picture.height = radius * 2;
    holder.addChild(picture);
  });
}

function drawFace(holder, seat) {
  if (seat.cpu) {
    holder.removeChildren().forEach((child) => child.destroy({ children: true }));
    holder.addChild(robot(seat.name));
  } else {
    personFace(holder, seat);
  }
}

// ---- Glow ----

let glowTexture = null;

// A soft gold light, made once and shared by every seat
function glowSprite(size) {
  if (!glowTexture) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 128;
    const paint = canvas.getContext("2d");
    const light = paint.createRadialGradient(64, 64, 16, 64, 64, 64);
    light.addColorStop(0, "rgba(255, 224, 130, 0.95)");
    light.addColorStop(0.5, "rgba(243, 215, 122, 0.4)");
    light.addColorStop(1, "rgba(243, 215, 122, 0)");
    paint.fillStyle = light;
    paint.fillRect(0, 0, 128, 128);
    glowTexture = Texture.from(canvas);
  }
  const glow = new Sprite(glowTexture);
  glow.anchor.set(0.5);
  glow.width = glow.height = size;
  return glow;
}

// The clock's color as it runs down: amber at 10 seconds, red at 5
function ringColor(seconds) {
  return seconds <= 5 ? ALARM : seconds <= 10 ? AMBER : GREEN;
}

// ---- Geometry, shared with the scene's layout ----

// A seat's plate: how wide, and where its middle is from the face. outward is 1 when the plate hangs under the face
export function plateOf(spot) {
  const width = spot.nameWidth + PLATE.pad * 2;
  const y = spot.outward * (FACE + RIM + PLATE.height / 2 - PLATE.overlap);
  return { width, y };
}

// Where card index sits around the face: tucked behind it toward the middle of the table, shown over it, or the
// player's own, big, over it
export function cardSpot(spot, index, mode) {
  const side = index === 0 ? -1 : 1;
  if (mode === "hero") {
    // Clear of the plate under the face, with room between for the hand's tag
    const hero = heroSize(spot);
    return { x: side * hero.spread, y: -hero.rise, rotation: side * 0.07, scale: hero.scale };
  }
  if (mode === "shown") {
    // About as tall as the face, nudged off the plate so its words still show
    return { x: side * 14, y: -spot.outward * 9, rotation: side * 0.08, scale: CARD_SCALE.shown };
  }
  // A fan held behind the face, peeking out on the side toward the middle of the table, between the plate (which
  // hides its far end) and the face's tag, so the tag sits on the felt and not on the cards
  const inward = spot.inward;
  return {
    x: inward * (FACE + 12 + side * 8),
    y: spot.outward * TUCK + side * 2,
    rotation: inward * (0.1 + side * 0.12),
    scale: CARD_SCALE.tucked,
  };
}

// The box a seat takes around its spot (face, its tag, plate with the dealer button at its end, and tucked cards),
// in table units
export function seatBox(spot) {
  const k = spot.k;
  const plate = plateOf(spot);
  const reach = FACE + RIM;
  const card = cardSpot(spot, 1, "tucked");
  const tuckedReach = Math.abs(card.x) + (CARD.width * card.scale) / 2 + 6;
  const half = Math.max(plate.width / 2, reach);
  const button = plate.width / 2 + BUTTON - 3;
  const left = spot.inward < 0 ? -Math.max(half, tuckedReach, button) : -half;
  const right = spot.inward > 0 ? Math.max(half, tuckedReach, button) : half;
  // How far the tucked cards reach toward the felt (they sit toward the plate, which reaches further the other way)
  const first = cardSpot(spot, 0, "tucked");
  const tucked = (CARD.height * first.scale) / 2 - first.y * spot.outward + 2;
  const near = -spot.outward * Math.max(reach, tucked, TAG.y + TAG.height / 2);
  const far = plate.y + (spot.outward * PLATE.height) / 2;
  return {
    left: spot.x + left * k,
    right: spot.x + right * k,
    top: spot.y + Math.min(near, far) * k,
    bottom: spot.y + Math.max(near, far) * k,
  };
}

// Where the name is written, in table units
export function nameBox(spot) {
  const k = spot.k;
  const plate = plateOf(spot);
  const y = plate.y + LINES.name;
  return {
    left: spot.x - (spot.nameWidth / 2) * k,
    right: spot.x + (spot.nameWidth / 2) * k,
    top: spot.y + (y - NAME_FONT * 0.7) * k,
    bottom: spot.y + (y + NAME_FONT * 0.7) * k,
  };
}

// Where the dealer button sits when this seat deals, in table units: at the end of the plate toward the middle of
// the table, or at the left end of the viewer's own plate
export function buttonSpot(spot) {
  const { x, y, k, inward, hero } = spot;
  const plate = plateOf(spot);
  const side = hero ? -1 : inward;
  return { x: x + side * (plate.width / 2 + BUTTON / 2 - 3) * k, y: y + plate.y * k };
}

// A card's whole reach, turned as it lies, in table units around the seat's spot
function cardReach(spot, index, mode) {
  const card = cardSpot(spot, index, mode);
  const cos = Math.cos(card.rotation);
  const sin = Math.abs(Math.sin(card.rotation));
  const halfX = ((CARD.width * cos + CARD.height * sin) * card.scale) / 2;
  const halfY = ((CARD.height * cos + CARD.width * sin) * card.scale) / 2;
  const { x, y, k } = spot;
  return {
    left: x + (card.x - halfX) * k,
    right: x + (card.x + halfX) * k,
    top: y + (card.y - halfY) * k,
    bottom: y + (card.y + halfY) * k,
  };
}

// The marks on a seat that must never meet, in table units: the dealer button, the face's tag (as wide as it may
// grow) and the cards shown over the face at a showdown on any seat, and on the viewer's own seat the button, their
// two cards and their hand's tag under them
export function seatMarks(spot) {
  const k = spot.k;
  const button = buttonSpot(spot);
  const half = (BUTTON / 2) * k;
  const marks = {
    button: { left: button.x - half, right: button.x + half, top: button.y - half, bottom: button.y + half },
  };
  if (!spot.hero) {
    const y = spot.y - spot.outward * TAG.y * k;
    const tag = { left: spot.x - (spot.nameWidth / 2) * k, right: spot.x + (spot.nameWidth / 2) * k };
    const shown = pairReach(spot, "shown");
    return { ...marks, shown, tag: { ...tag, top: y - (TAG.height / 2) * k, bottom: y + (TAG.height / 2) * k } };
  }
  const bottom = spot.y + (plateOf(spot).y - PLATE.height / 2 + HAND.dip) * k;
  const wide = (handWidth(spot) / 2) * k;
  const hand = { left: spot.x - wide, right: spot.x + wide, top: bottom - HAND.height * k, bottom };
  return { ...marks, cards: pairReach(spot, "hero"), hand };
}

// A burst from this point flying this way, then tilted a little either way: tilted off a top or bottom edge, it
// still flies away from what it started beside
function tilted(point, toward) {
  return [0, 1, -1, 2, -2].map((step) => ({ ...point, toward: toward + (step * Math.PI) / 12 }));
}

// How far past the view's edges a burst's sparkles reach at most, in table units
function sparkOvershoot({ x, y, toward }, view) {
  let worst = -Infinity;
  for (let step = 0; step <= 24; step += 1) {
    const angle = toward === null ? (step / 24) * Math.PI * 2 : toward + (step / 24 - 0.5) * 2 * SPARK_SPREAD;
    const [reachX, reachY] = [x + Math.cos(angle) * SPARK_REACH, y + Math.sin(angle) * SPARK_REACH];
    worst = Math.max(worst, view.left - reachX, reachX - view.right, view.top - reachY, reachY - view.bottom);
  }
  return worst;
}

// The first of these bursts whose sparkles all stay in the view, else the one that leaves it least
function insideBurst(bursts, view) {
  const overs = bursts.map((burst) => sparkOvershoot(burst, view));
  const first = overs.findIndex((over) => over <= 0);
  return bursts[first >= 0 ? first : overs.indexOf(Math.min(...overs))];
}

// Both of a seat's cards together, in table units
function pairReach(spot, mode) {
  const [first, second] = [0, 1].map((index) => cardReach(spot, index, mode));
  return {
    left: first.left,
    right: second.right,
    top: Math.min(first.top, second.top),
    bottom: Math.max(first.bottom, second.bottom),
  };
}

// The player's own seat as its two parts, in table units: the big cards with their clock over them and their hand's
// tag under them, and the plate with the dealer button's room at its left end
export function heroParts(spot) {
  const k = spot.k;
  const hero = heroSize(spot);
  const half = hero.width / 2 + 6;
  const plate = plateOf(spot);
  const plateTop = plate.y - PLATE.height / 2;
  const hand = handWidth(spot) / 2;
  return [
    {
      left: spot.x - half * k,
      right: spot.x + half * k,
      top: spot.y + (hero.top - 4) * k,
      bottom: spot.y + plateTop * k,
    },
    {
      left: spot.x - (plate.width / 2 + BUTTON - 3) * k,
      right: spot.x + (plate.width / 2) * k,
      top: spot.y + plateTop * k,
      bottom: spot.y + (plate.y + PLATE.height / 2 + 2) * k,
    },
    // The hand's tag between the cards and the plate, which may be wider than both
    {
      left: spot.x - hand * k,
      right: spot.x + hand * k,
      top: spot.y + (plateTop + HAND.dip - HAND.height) * k,
      bottom: spot.y + (plateTop + HAND.dip) * k,
    },
  ];
}

// The player's own seat as one box, in table units
export function heroBox(spot) {
  const parts = heroParts(spot);
  return {
    left: Math.min(...parts.map((part) => part.left)),
    right: Math.max(...parts.map((part) => part.right)),
    top: Math.min(...parts.map((part) => part.top)),
    bottom: Math.max(...parts.map((part) => part.bottom)),
  };
}

// ---- A seat ----

export class Seat {
  // layers: the scene's {seats, felt, fx} containers. sit(number): the viewer tapped this empty seat
  constructor(number, layers, sit) {
    this.number = number;
    this.layers = layers;
    this.data = null;
    this.look = null;
    this.spot = null;
    this.cards = [];
    this.mode = null;
    this.amount = 0;
    this.turn = false;
    this.counting = false;
    this.showsStack = true;
    this.makeGroup(sit);
    this.makeBet();
  }

  makeGroup(sit) {
    const group = new Container();
    group.label = `seat-${this.number}`;
    this.group = group;
    this.glow = glowSprite((FACE + 30) * 2);
    this.glow.visible = false;
    this.tucked = new Container();
    this.face = new Container();
    this.face.key = "";
    this.rim = new Graphics();
    this.ring = new Graphics();
    this.plate = new Graphics();
    // The player's own clock, a bar along the bottom of their plate
    this.bar = new Graphics();
    this.name = words("", NAME_FONT, CREAM);
    this.name.label = "name";
    this.stack = words("", STACK_FONT, GOLD_LIGHT);
    this.stack.label = "stack";
    this.tag = pill(TAG.font, TAG.height);
    this.tag.label = "tag";
    this.tag.visible = false;
    this.handTag = pill(TAG.font, HAND.height);
    this.handTag.label = "hand";
    this.handTag.visible = false;
    this.held = new Container();
    this.empty = this.emptySpot(sit);
    this.body = new Container();
    this.body.addChild(this.glow, this.tucked, this.face, this.rim, this.ring, this.plate, this.bar, this.name);
    this.body.addChild(this.stack);
    this.body.addChild(this.held, this.tag, this.handTag);
    group.addChild(this.body, this.empty);
    this.layers.seats.addChild(group);
  }

  makeBet() {
    this.betGroup = new Container();
    this.betGroup.label = `bet-${this.number}`;
    this.chips = new Container();
    this.sum = pill(SUM.font, SUM.height);
    this.sum.visible = false;
    this.betGroup.addChild(this.chips, this.sum);
    this.layers.felt.addChild(this.betGroup);
  }

  // A gold ring with "Sit" on the empty seat, for a viewer who may sit down. Its disc is nearly solid, so the rail's
  // pad doesn't show through as a bar across the word
  emptySpot(sit) {
    const spot = new Container();
    const ring = new Graphics()
      .circle(0, 0, FACE + 3)
      .fill({ color: INK, alpha: SIT_FILL })
      .stroke({ width: 2.5, color: GOLD_LIGHT, alpha: 0.85 });
    const label = words("Sit", 16, GOLD_LIGHT);
    const hit = new Graphics().circle(0, 0, FACE + 16).fill({ color: 0x000000, alpha: 0.001 });
    hit.eventMode = "static";
    hit.cursor = "pointer";
    hit.on("pointertap", () => this.data === null && spot.visible && sit(this.number));
    spot.addChild(ring, label, hit);
    spot.visible = false;
    return spot;
  }

  // ---- Where it goes ----

  // spot: x, y, k (seat scale), px (CSS pixels per seat unit), outward (1: plate under the face, -1: over it), inward
  // (which side the middle of the table is, -1 or 1), nameWidth, hero (the player's own seat), and its bet's spot
  // {x, y, side, under, most, lane, zone}
  place(spot) {
    this.spot = spot;
    this.group.position.set(spot.x, spot.y);
    this.group.scale.set(spot.k);
    this.betGroup.position.set(spot.bet.x, spot.bet.y);
    this.betGroup.scale.set(spot.k);
    this.arrange();
    // A new size can mean new room for the words, and piles of another height
    if (this.data) {
      const amount = this.amount;
      this.amount = null;
      this.draw(this.data, { ...this.look, fade: false });
      this.drawBet(amount, this.feltWords);
    }
  }

  arrange() {
    if (!this.spot) {
      return;
    }
    const plate = plateOf(this.spot);
    this.name.position.set(0, plate.y + LINES.name);
    this.stack.position.set(0, plate.y + LINES.stack);
    this.handTag.position.set(0, plate.y - PLATE.height / 2 + HAND.dip - HAND.height / 2);
    this.textWidth = plate.width - PLATE.pad * 2;
    this.drawPlate(plate);
    this.placeCards(false);
    this.placeSum();
  }

  drawPlate(plate) {
    const turn = this.turn;
    const top = plate.y - PLATE.height / 2;
    this.plate
      .clear()
      .roundRect(-plate.width / 2, top, plate.width, PLATE.height, 11)
      .fill({ color: INK, alpha: 0.9 })
      .stroke({ width: turn ? 2.5 : 1.5, color: turn ? GOLD_LIGHT : GOLD_DEEP });
    this.rim.clear().circle(0, 0, FACE + RIM / 2).stroke({ width: RIM, color: turn ? GOLD_LIGHT : GOLD });
  }

  // ---- What it shows ----

  // seat: the seat's row in the table's state, or null. look: {canSit, turn, move (the last move's words for the
  // face's tag), hand (a hand's name to show: {text, shorter, color, won}), fade (new words fade in)}
  draw(seat, look) {
    this.data = seat;
    this.look = look;
    this.empty.visible = !seat && look.canSit;
    this.body.visible = Boolean(seat);
    if (!seat) {
      this.setTurn(false);
      return;
    }
    const key = seat.cpu ? `cpu:${seat.name}` : `${seat.avatar}|${seat.name}`;
    if (this.face.key !== key) {
      this.face.key = key;
      drawFace(this.face, seat);
    }
    setText(this.name, fitWords([seat.name], this.name.style, this.textWidth));
    this.drawSecond(seat, look);
    this.drawMarks();
    this.setTurn(look.turn);
    this.body.alpha = seat.folded ? 0.5 : 1;
    this.face.alpha = seat.away ? 0.45 : 1;
  }

  // The plate's second line: the stack, "All in" once every chip is in, at a showdown the hand's name (shrunk to the
  // smallest readable size before it shortens), or "Next hand" for someone who bought in during a practice hand. The
  // player's own hand has its tag under their cards instead
  drawSecond(seat, look) {
    const hand = look.hand;
    const named = Boolean(hand) && !this.spot.hero;
    let text = money(seat.stack);
    let color = GOLD_LIGHT;
    let size = STACK_FONT;
    if (named) {
      const fit = fitSized(choicesOf(hand), this.stack.style, this.textWidth, this.least(), STACK_FONT);
      [text, size, color] = [fit.text, fit.size, hand.color];
    } else if (look.joining) {
      [text, color] = ["Next hand", CREAM];
    } else if (seat.all_in) {
      text = "All in";
      color = ALL_IN;
    }
    this.showsStack = !named && !seat.all_in && !look.joining;
    if (this.stack.style.fill !== color) {
      this.stack.style.fill = color;
    }
    if (this.stack.style.fontSize !== size) {
      this.stack.style.fontSize = size;
    }
    // A stack counting up to a win keeps its own numbers until it lands
    if (!(this.showsStack && this.counting)) {
      setText(this.stack, text);
    }
  }

  // The tag on the face: the last move this round, else Away or Waiting. And the player's own hand under their cards
  drawMarks() {
    const seat = this.data;
    if (!seat || !this.spot) {
      return;
    }
    const covered = this.covered();
    let tag = this.look.move;
    if (!tag && (seat.away || seat.waiting)) {
      tag = { text: seat.away ? "Away" : "Waiting", color: CREAM, stroke: GREY };
    }
    // A showdown's cards and the player's own big cards take the face's place
    this.tag.visible = Boolean(tag) && !covered && this.mode !== "shown";
    if (this.tag.visible) {
      const before = this.tag.look;
      const room = this.textWidth - TAG.height * PAD * 2;
      const fit = fitSized(choicesOf(tag), this.tag.words.style, room, this.least(), TAG.font);
      setPill(this.tag, fit.text, { fill: tag.color, stroke: tag.stroke ?? GOLD_DEEP }, fit.size);
      if (this.look.fade && this.tag.look !== before) {
        this.tag.alpha = 0;
        tween(this.tag, { alpha: 1 }, 200);
      }
    }
    const hand = this.spot.hero && covered ? this.look.hand : null;
    this.handTag.visible = Boolean(hand);
    if (hand) {
      const room = handWidth(this.spot) - HAND.height * PAD * 2;
      const fit = fitSized(choicesOf(hand), this.handTag.words.style, room, this.least(), TAG.font);
      const look = hand.won ? { fill: INK, stroke: GOLD, back: GOLD_LIGHT } : { fill: CREAM, stroke: GOLD_DEEP };
      setPill(this.handTag, fit.text, look, fit.size);
    }
  }

  // The smallest words may be drawn here, in seat units, to stay readable on screen
  least() {
    return SMALLEST / this.spot.px;
  }

  setTurn(turn) {
    if (this.turn === Boolean(turn)) {
      return;
    }
    this.turn = Boolean(turn);
    this.glow.visible = this.turn;
    this.stopClock();
    this.arrange();
  }

  // The clock, drawn each frame on the seat's turn: share is how much of the turn is left. It drains as a ring around
  // the face, or, when the player's own big cards cover their face, as a bar along the bottom of their plate
  drawRing(share, seconds, now) {
    this.stopClock();
    if (!this.turn) {
      return;
    }
    // A CPU's turn has no clock, so its glow alone says whose turn it is: it pulses, but never faintly
    this.glow.alpha = 0.75 + 0.2 * Math.sin(now / 280);
    if (share === null) {
      return;
    }
    const left = Math.max(0.001, Math.min(1, share));
    const color = ringColor(seconds);
    if (this.covered()) {
      const plate = plateOf(this.spot);
      const width = plate.width - PLATE.height * 0.5;
      const y = plate.y + PLATE.height / 2 - 5;
      this.bar.roundRect(-width / 2, y, width * left, 3, 1.5).fill(color);
      return;
    }
    // The plate hangs on one side of the face, the tag sits on the other and the tucked cards on the side toward the
    // middle of the table, so the ring drains toward the face's outer side, where its last seconds stay in view
    const open = this.spot.inward > 0 ? Math.PI : 0;
    const reach = Math.PI * left;
    const radius = FACE + RIM + 3.5;
    // On a dark track around the whole face, so the warning colors still read on a face of the same color. The track
    // reaches in over the gold rim, so a phone shows dark between the face and the arc, not just a hairline. The arc
    // starts at its own first point, or it would be joined to the middle of the face by a line
    const track = { width: RING_TRACK.width, color: 0x000000, alpha: 0.55 };
    this.ring.circle(0, 0, radius - RING_TRACK.inside).stroke(track);
    this.ring.moveTo(Math.cos(open - reach) * radius, Math.sin(open - reach) * radius);
    this.ring.arc(0, 0, radius, open - reach, open + reach).stroke({ width: 4.5, color, cap: "round" });
  }

  stopClock() {
    this.ring.clear();
    this.bar.clear();
  }

  // True while the player's own big cards lie over their face
  covered() {
    return this.mode === "hero" && this.cards.length > 0;
  }

  // The face shows unless the player's own cards cover it; the turn's glow sits behind whichever shows, and the tag on
  // the face's side toward the felt
  showFace() {
    const covered = this.covered();
    this.face.visible = !covered;
    this.rim.visible = !covered;
    this.glow.y = covered ? -heroSize(this.spot).rise : 0;
    this.glow.width = this.glow.height = covered ? 190 * (this.spot.big ?? 1) : (FACE + 30) * 2;
    this.tag.position.set(0, -this.spot.outward * TAG.y);
    this.drawMarks();
  }

  // ---- The bet in front of the seat ----

  // The chips bet this round, with their amount, or other words in its place ({text, shorter, color, back}): a win
  drawBet(amount, words = null) {
    this.feltWords = words;
    const bet = this.spot.bet;
    if (amount !== this.amount) {
      this.amount = amount;
      this.chips.removeChildren().forEach((child) => child.destroy({ children: true }));
      if (amount > 0) {
        this.chips.addChild(chipPile(amount, bet.most, bet.under ? 0 : bet.grow));
      }
    }
    // An amount shrinks to the smallest readable size before it shortens; a win never shortens
    const amounts = [money(amount), shortMoney(amount, 1), shortMoney(amount, 0)];
    const choices = words ? choicesOf(words) : amount > 0 ? amounts : [];
    this.sum.visible = choices.length > 0;
    if (choices.length) {
      const room = this.labelRoom() - SUM.height * PAD * 2;
      const fit = fitSized(choices, this.sum.words.style, room, this.least(), SUM.font);
      const look = { fill: words ? words.color : CREAM, stroke: words?.back ? GOLD : GOLD_DEEP };
      setPill(this.sum, fit.text, words?.back ? { ...look, back: words.back } : look, fit.size);
    }
    this.placeSum();
  }

  // How much further the bet's words sit for its pile's other columns, in seat units: none when they grow away
  pileWide() {
    const bet = this.spot.bet;
    return bet.grow === bet.side ? ((this.chips.children[0]?.columns ?? 1) - 1) * COLUMN : 0;
  }

  // How wide the bet's label may be, in seat units: beside the chips to the end of its lane, under them, or, with no
  // chips, its whole share of the row (its zone)
  labelRoom() {
    const { bet, k } = this.spot;
    if (this.amount > 0) {
      if (bet.under) {
        return bet.width ?? UNDER.width;
      }
      const end = bet.side > 0 ? bet.lane.right - bet.x : bet.x - bet.lane.left;
      return end / k - (CHIP / 2 + this.pileWide() + GAP);
    }
    return (bet.zone.right - bet.zone.left) / k;
  }

  // The amount sits beside the chips on the side toward the middle of the table, or under them where the table is
  // crowded. Words without chips sit where the chips would, kept inside the zone
  placeSum() {
    if (!this.spot) {
      return;
    }
    const { bet, k } = this.spot;
    const span = this.sum.span;
    if (this.amount > 0) {
      const beside = bet.side * (CHIP / 2 + this.pileWide() + GAP + span / 2);
      this.sum.position.set(bet.under ? 0 : beside, bet.under ? UNDER.drop : 0);
      return;
    }
    const left = (bet.zone.left - bet.x) / k + span / 2;
    const right = (bet.zone.right - bet.x) / k - span / 2;
    this.sum.position.set(left > right ? (left + right) / 2 : Math.min(Math.max(0, left), right), 0);
  }

  betPoint() {
    return { x: this.spot.bet.x, y: this.spot.bet.y };
  }

  // Where a won pot's chips melt: the bet's spot, or as much further toward the felt as keeps the pile off the hand
  // shown over the face, lifted and glowing (marked moved). pile: how far the pile reaches around where it stands, in
  // table units
  winPoint(pile) {
    const at = this.betPoint();
    if (this.mode !== "shown") {
      return at;
    }
    const { k, outward } = this.spot;
    const cards = pairReach(this.spot, "shown");
    const glow = ((WON_CARD.out + WON_CARD.width / 2) * CARD_SCALE.shown + 2) * k;
    const lift = -WON_CARD.lift * outward * k;
    const [top, bottom] = [cards.top + lift - glow, cards.bottom + lift + glow];
    const across = at.x + pile.right > cards.left - glow && at.x + pile.left < cards.right + glow;
    if (!across || at.y + pile.bottom <= top || at.y + pile.top >= bottom) {
      return at;
    }
    return { x: at.x, y: outward < 0 ? bottom - pile.top : top - pile.bottom, moved: true };
  }

  // Where the dealer button sits when this seat deals, in table units
  buttonPoint() {
    return buttonSpot(this.spot);
  }

  facePoint() {
    return { x: this.spot.x, y: this.spot.y };
  }

  // Chips on the felt in front of the player's own cards: they grow in where they stand, or melt away there
  async dropChips(stack, arriving, ms) {
    const { x, y } = this.betPoint();
    const scale = stack.scale.x;
    stack.position.set(x, y);
    stack.alpha = arriving ? 0 : 1;
    stack.scale.set(arriving ? scale * 0.8 : scale);
    await tween(stack, { alpha: arriving ? 1 : 0, scale: arriving ? scale : scale * 0.8 }, ms, ease.out);
  }

  // Where a win's "+amount" starts, its words this wide in table units, and how far it moves: level with the plate and
  // beside it, never on the cards or the hand's name. The player's own sits right of their plate, cards and hand's tag
  // and rises; anyone else's sits past the end of their plate toward the middle of the table, beyond the dealer
  // button's room there, and moves toward their face, so it stays on the screen whether the plate hangs under the face
  // or over it
  gainPoint(span) {
    const { x, y, k, inward, outward, hero } = this.spot;
    const plate = plateOf(this.spot);
    const level = y + plate.y * k;
    if (hero) {
      const tag = this.handTag.visible ? this.handTag.span : 0;
      const reach = Math.max(plate.width, heroSize(this.spot).width, tag) / 2;
      return { x: x + (reach + 10) * k + span / 2, y: level, rise: -40 * k };
    }
    const reach = (plate.width / 2 + BUTTON + 4) * k;
    return { x: x + inward * (reach + span / 2), y: level, rise: -outward * 40 * k };
  }

  // Where a win's sparkles burst, which way they fly (null: all round) and whether coins fall. Cards lying over the
  // face, the player's own or a hand shown at the showdown, have them burst beside the cards, flying outward with no
  // coins to fall back on them; otherwise they burst over the face. Near an edge of the view (in table units) a burst
  // turns inward, so the edge cuts none of its sparkles
  sparkPoints(count, view) {
    const { x, y, k } = this.spot;
    const mode = this.cards.length ? this.mode : null;
    if (mode !== "hero" && mode !== "shown") {
      const middle = { x: (view.left + view.right) / 2, y: (view.top + view.bottom) / 2 };
      return Array.from({ length: count }, (_, index) => {
        const point = { x: x + (index - 1) * 26 * k, y: y - index * 8 * k, coins: true };
        const inward = Math.atan2(middle.y - point.y, middle.x - point.x);
        return insideBurst([{ ...point, toward: null }, ...tilted(point, inward)], view);
      });
    }
    // Far enough out that the biggest sparkle, turned, starts clear of the cards. A side whose burst would leave the
    // view bursts from the cards' other side instead, still flying away from them
    const cards = pairReach(this.spot, mode);
    const left = (at) => tilted({ x: cards.left - SPARK_CLEAR, y: at, coins: false }, Math.PI);
    const right = (at) => tilted({ x: cards.right + SPARK_CLEAR, y: at, coins: false }, 0);
    const middle = (cards.top + cards.bottom) / 2;
    const sides = [
      [...left(middle), ...right(middle)],
      [...right(middle), ...left(middle)],
      [...right(cards.top + 12 * k), ...left(cards.top + 12 * k)],
    ];
    return sides.slice(0, Math.max(2, count)).map((bursts) => insideBurst(bursts, view));
  }

  // ---- Cards ----

  // A card's spot in table units, for one flying in from elsewhere
  tableSpot(index, mode) {
    const spot = cardSpot(this.spot, index, mode);
    const k = this.spot.k;
    return { x: this.spot.x + spot.x * k, y: this.spot.y + spot.y * k, rotation: spot.rotation, scale: spot.scale * k };
  }

  placeCards(animate, ms = 300) {
    if (!this.spot) {
      return;
    }
    this.cards.forEach((piece, index) => {
      const spot = cardSpot(this.spot, index, this.mode);
      const holder = this.mode === "tucked" ? this.tucked : this.held;
      if (piece.parent !== holder) {
        holder.addChild(piece);
      }
      if (animate) {
        tween(piece, { x: spot.x, y: spot.y, rotation: spot.rotation, scale: spot.scale }, ms, ease.inOut);
      } else {
        piece.position.set(spot.x, spot.y);
        piece.rotation = spot.rotation;
        piece.scale.set(spot.scale);
      }
    });
    this.showFace();
  }

  // The cards this seat holds, drawn at once: mode "tucked", "hero" or "shown", each card's face or null for a back
  setCards(mode, faces) {
    while (this.cards.length < faces.length) {
      const piece = cardSprite(null);
      piece.label = "hole";
      this.cards.push(piece);
    }
    while (this.cards.length > faces.length) {
      this.cards.pop().destroy({ children: true });
    }
    this.cards.forEach((piece, index) => {
      if (!sameCard(piece.card, faces[index])) {
        showCard(piece, faces[index] ?? null);
      }
    });
    this.mode = mode;
    this.placeCards(false);
  }

  // A dealt card lands and joins the hand
  takeCard(piece, mode) {
    piece.label = "hole";
    this.cards.push(piece);
    this.mode = mode;
    this.placeCards(false);
  }

  // Every card leaves the seat, handed to the scene to sweep away
  giveUpCards() {
    const cards = this.cards;
    this.cards = [];
    this.mode = null;
    this.showFace();
    return cards;
  }

  // The tucked cards come out over the face and turn face up. The player's own are face up already
  async reveal(faces, ms) {
    if (!this.cards.length) {
      this.setCards("tucked", [null, null]);
    }
    if (this.mode !== "hero") {
      this.mode = "shown";
      this.placeCards(true, ms * 0.4);
    }
    await Promise.all(
      this.cards.map(async (piece, index) => {
        if (sameCard(piece.card, faces[index])) {
          return;
        }
        await wait(ms * 0.3 + index * 90);
        if (!piece.destroyed) {
          await flipCard(piece, faces[index], ms * 0.55);
        }
      }),
    );
    if (!this.group.destroyed) {
      this.placeCards(false);
    }
  }

  // ---- Moving chips ----

  // Chips fly from the seat to the bet, or back for a bet returned, then the bet shows its new amount. The player's
  // own big cards lie between their seat and their bet, so their chips drop onto the felt in front of the cards, or
  // melt away there when they come back, and never cross the cards
  async moveBet(amount, words, ms) {
    const delta = amount - this.amount;
    if (!delta) {
      this.drawBet(amount, words);
      return;
    }
    const flying = chipPile(Math.abs(delta), this.spot.bet.most);
    flying.scale.set((CHIP / 52) * this.spot.k);
    this.layers.fx.addChild(flying);
    if (delta < 0) {
      this.drawBet(amount, words);
    }
    if (this.covered()) {
      await this.dropChips(flying, delta > 0, ms);
    } else {
      const [from, to] = delta > 0 ? [this.facePoint(), this.betPoint()] : [this.betPoint(), this.facePoint()];
      flying.position.set(from.x, from.y);
      await moveChips(flying, to, ms);
    }
    if (this.group.destroyed) {
      return;
    }
    flying.destroy({ children: true });
    this.drawBet(amount, words);
  }

  // The bet slides to the pot along the way route(from, to, half) gives, its amount fading. Resolves with the amount
  // gathered
  async gather(pot, ms, route) {
    const amount = this.amount;
    const stack = this.chips.children[0];
    this.amount = 0;
    const fade = this.sum.visible ? tween(this.sum, { alpha: 0 }, ms * 0.5) : Promise.resolve();
    if (stack) {
      this.chips.removeChild(stack);
      stack.scale.set((CHIP / 52) * this.spot.k);
      stack.position.set(this.spot.bet.x, this.spot.bet.y);
      this.layers.fx.addChild(stack);
      await slideChips(stack, route({ x: stack.x, y: stack.y }, pot, pileReach(stack)), ms);
      if (!stack.destroyed) {
        stack.destroy({ children: true });
      }
    }
    await fade;
    if (!this.group.destroyed) {
      this.sum.visible = false;
      this.sum.alpha = 1;
    }
    return amount;
  }

  // The stack counts up to its new amount as won chips arrive
  async countTo(amount, ms) {
    const from = Number(String(this.stack.text).replace(/[^\d]/g, "")) || 0;
    this.counting = true;
    const counter = { value: from };
    const show = (value) => !this.stack.destroyed && setText(this.stack, money(Math.round(value)));
    const timer = setInterval(() => show(counter.value), 40);
    await tween(counter, { value: amount }, ms, ease.out);
    clearInterval(timer);
    this.counting = false;
    show(amount);
  }
}

export function sameCard(a, b) {
  return (a ?? null) === (b ?? null) || (Boolean(a) && Boolean(b) && a[0] === b[0] && a[1] === b[1]);
}
