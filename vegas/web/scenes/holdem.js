// Texas Hold'em: an oval table with six seats on its rail, the shared cards across the middle and the pot above them.
// A wide screen has the table across; a tall one has it upright, with one seat at the top, two down each side and the
// viewer at the bottom. The deck sits in the dealer's tray on the rail: cards fly from there to each seat, one at a
// time in dealing order, and the flop, turn and river slide out from it and turn over. The viewer's own seat is always
// at the bottom middle, with their cards big and face up; everyone else's stay face down until a showdown.
//
// Every event the bot sends animates within its pace (table.js's PACE): bets slide from a seat to the felt in front of
// it, each round's bets sweep into the pot, folded cards slide into the dealer's tray, the dealer button glides, and
// at the end the pot slides to its winners. show(state) draws the table exactly as the bot describes it, at once, so a
// reconnect never replays anything; it only redraws what changed.
//
// layoutFor(width, height) is where everything goes in a scene space of that size, in CSS pixels from its top left
// corner. A small screen draws the seats, cards and words bigger than the table around them, so names stay at least
// 10 CSS pixels and the cards stay readable; the seats' boxes never overlap each other or the cards, and every bet's
// chips (up to two columns) and amount have room beside them or, where a row is crowded, under them.
import { Assets, Container, Graphics, Sprite, Texture, TilingSprite } from "../vendor/pixi.min.mjs";
import { money } from "../format.js";
import { CARD, cardSprite, dealCard, flipCard, loadArt, showCard, sparkle } from "./art.js";
import { ease, tween, wait } from "./kit.js";
import {
  BUTTON,
  CHIP,
  COLUMN,
  FACE,
  GAP,
  NAME_FONT,
  PAD,
  PILE,
  RIM,
  SMALLEST,
  SMALL_CARD,
  SUM,
  Seat,
  TURN_SECONDS,
  UNDER,
  WON_CARD,
  cardSpot,
  chipPile,
  crosses,
  drawnWidth,
  fitSized,
  handNames,
  heroBox,
  heroParts,
  markSmall,
  moveWords,
  nameBox,
  personFace,
  pileReach,
  pileRise,
  pill,
  sameCard,
  seatBox,
  seatMarks,
  setPill,
  slideChips,
} from "./holdem_seats.js";

// The two tables, each measured on its picture (assets/vegas/holdem/measurements.md) in table units, one picture pixel
// to a unit: across for wide screens, upright for tall ones. For each: its size, the width a narrow screen fits (the
// rail and a little beside it, so the end seats' plates keep a margin from the screen's edge), where its picture lies,
// each seat's gold pad (clockwise from the bottom middle, where its face goes) and where its bets go, which way each
// seat's plate hangs (1: under the face, -1: over it) and which side the middle of the table is (where its cards tuck
// and its bet's amount goes), the shared cards' middle and least size, the pot, the table's middle (bets move toward
// it), the dealer's tray (dealt cards fly from it and the casino's cut goes into it), the felt's left end and bottom,
// the rail's top and bottom, and how big the viewer's own cards are
const TABLES = {
  across: {
    picture: "table.jpg",
    width: 900,
    height: 600,
    fit: 870,
    background: { x: -270, y: -180, width: 1440, height: 960 },
    plaques: [
      { x: 450, y: 479 },
      { x: 116, y: 407 },
      { x: 116, y: 151 },
      { x: 450, y: 77 },
      { x: 786, y: 151 },
      { x: 786, y: 407 },
    ],
    bets: [
      { x: 450, y: 402 },
      { x: 173, y: 359 },
      { x: 175, y: 203 },
      { x: 450, y: 162 },
      { x: 726, y: 203 },
      { x: 728, y: 359 },
    ],
    outward: [1, 1, -1, -1, -1, 1],
    inward: [1, 1, 1, 1, -1, -1],
    board: { x: 450, y: 280, scale: 0.49, gap: 9 },
    pot: { x: 450, y: 202 },
    middle: { x: 450, y: 280 },
    dealer: { x: 838, y: 281 },
    felt: { left: 90, bottom: 455 },
    rail: { top: 51, bottom: 508 },
    big: 1,
  },
  upright: {
    picture: "table-upright.jpg",
    width: 640,
    height: 880,
    fit: 640,
    background: { x: -60, y: -61, width: 760, height: 1000 },
    plaques: [
      { x: 320, y: 782 },
      { x: 75, y: 633 },
      { x: 75, y: 245 },
      { x: 320, y: 96 },
      { x: 565, y: 245 },
      { x: 565, y: 633 },
    ],
    bets: [
      { x: 320, y: 640 },
      { x: 170, y: 560 },
      { x: 170, y: 318 },
      { x: 320, y: 190 },
      { x: 470, y: 318 },
      { x: 470, y: 560 },
    ],
    outward: [1, 1, -1, -1, -1, 1],
    inward: [1, 1, 1, 1, -1, -1],
    board: { x: 320, y: 439, scale: 0.72, gap: 8 },
    pot: { x: 320, y: 340 },
    middle: { x: 320, y: 439 },
    dealer: { x: 594, y: 439 },
    felt: { left: 72, bottom: 756 },
    rail: { top: 70, bottom: 808 },
    big: 1.5,
  },
};
// The narrowest an amount's label may be beside its chips, in seat units: "1,240" or "12.3K" fits. A bet with less
// room has its amount under its chips instead (holdem_seats.js's UNDER)
const LABEL = 50;
// How far every seat keeps from the scene's edges, in CSS pixels
const EDGE = 7;
// The smallest a name and a shared card are drawn on screen, in CSS pixels
const NAME_MIN = 10.3;
const CARD_MIN = 32;
// How big the deck in the dealer's tray is, as a card scale: dealt cards start at its size
const DECK_SCALE = 0.28;
const SEATS = 6;
// Animation timings, each inside its event's pace
const MS = { seat: 320, button: 340, chips: 380, pitch: 115, sweep: 420, slide: 330, flip: 270, muck: 280 };
const SPLIT_MS = 200;
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const GOLD_DEEP = 0x8a6a14;
const INK = 0x1a0f08;
const WATCHER_FACES = 5;
const WATCHER_RADIUS = 13;
// How dark a card that didn't win goes at the end of a hand, as a grey level
const DARK = 0x70;
// How far a winning shared card lifts, in table units, and how far its glow reaches past its edge, in card units
const BOARD_LIFT = 10;
const GLOW = { board: 10.5 };
// How far past the scene's edges the wallpaper reaches, in CSS pixels
const WALL_SPARE = 200;
// The practice label on the felt, and its shorter form for a tight spot
const PRACTICE = ["Practice · play chips", "Practice"];

// ---- Layout ----

function boardBox(scale, table) {
  const width = CARD.width * scale;
  const height = CARD.height * scale;
  const step = width + table.board.gap;
  return {
    scale,
    step,
    left: table.board.x - 2 * step - width / 2,
    right: table.board.x + 2 * step + width / 2,
    top: table.board.y - height / 2,
    bottom: table.board.y + height / 2,
  };
}

function overlaps(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

// How much wider than one chip a pile's columns make it, in table units
const PILE_WIDE = (PILE.columns - 1) * COLUMN;

// How far past a bet's first column of chips its words start, in table units: past the other columns too when they
// grow on the words' side
function wordsFrom(bet) {
  return CHIP / 2 + (bet.grow === bet.side ? PILE_WIDE : 0) + GAP;
}

// A bet's chips, piled as high and as wide as they go, and its amount when that sits under them, in table units. A
// pile's next columns stand on its grow side: its amount's side for the seats around the rail, so a pile never reaches
// back toward its seat, and away from it for the bottom seat's, which has open felt on both sides. Over an amount
// under them the columns center
function unitBox(bet, k) {
  const below = bet.under ? UNDER.drop + SUM.height / 2 : CHIP / 2;
  const top = bet.y - (CHIP / 2 + pileRise(bet.most)) * k;
  const half = Math.max(bet.width ?? UNDER.width, CHIP + PILE_WIDE) / 2;
  const left = bet.under ? half : CHIP / 2 + (bet.grow < 0 ? PILE_WIDE : 0);
  const right = bet.under ? half : CHIP / 2 + (bet.grow > 0 ? PILE_WIDE : 0);
  return { left: bet.x - left * k, right: bet.x + right * k, top, bottom: bet.y + below * k };
}

// Where the words beside a bet may go: from its chips to the far end of its lane, on its side
function labelBox(bet, k) {
  if (bet.under) {
    return unitBox(bet, k);
  }
  const near = bet.x + bet.side * wordsFrom(bet) * k;
  const far = bet.side > 0 ? bet.lane.right : bet.lane.left;
  return { left: Math.min(near, far), right: Math.max(near, far), top: bet.lane.top, bottom: bet.lane.bottom };
}

// How wide the words beside a bet may be, in seat units
function labelRoom(bet, k) {
  if (bet.under) {
    return bet.width ?? UNDER.width;
  }
  const box = labelBox(bet, k);
  return (box.right - box.left) / k;
}

// A bet clear of the shared cards: under them with room for its chips to pile up, or over them. A bet beside them
// moves too when the words beside its chips would run into them
function offBoard(bet, board, k, below) {
  const box = unitBox(bet, k);
  const gap = 3 * k;
  const reach = bet.under ? 0 : (GAP + LABEL) * k;
  const right = box.right + (bet.side > 0 ? reach : 0);
  const left = box.left - (bet.side < 0 ? reach : 0);
  if (right > board.left && left < board.right && box.bottom > board.top - gap && box.top < board.bottom + gap) {
    bet.y = below ? board.bottom + gap + (bet.y - box.top) : board.top - gap - (box.bottom - bet.y);
  }
  return bet;
}

// A seat's bet: its spot on the art, moved toward the middle until it clears the seat, then off the shared cards
function betSpot(spot, slot, board, most, table) {
  const box = seatBox(spot);
  const gap = 4 * spot.k;
  const clear = { left: box.left - gap, right: box.right + gap, top: box.top - gap, bottom: box.bottom + gap };
  const side = table.inward[slot];
  const bet = { ...table.bets[slot], side, grow: slot ? side : -1, under: false, most };
  const middle = table.middle;
  const length = Math.hypot(middle.x - spot.x, middle.y - spot.y);
  const step = { x: ((middle.x - spot.x) / length) * 3, y: ((middle.y - spot.y) / length) * 3 };
  for (let tries = 0; tries < 80 && overlaps(unitBox(bet, spot.k), clear); tries += 1) {
    bet.x += step.x;
    bet.y += step.y;
  }
  offBoard(bet, board, spot.k, spot.outward > 0);
  // Moving off the cards may bring it back to its seat: then it moves along toward the middle
  for (let tries = 0; tries < 80 && overlaps(unitBox(bet, spot.k), clear); tries += 1) {
    bet.x += Math.sign(step.x) * 3;
  }
  return bet;
}

// The bottom seat a watcher sees keeps its words under its chips when its row is crowded, and sits a little lower
// to make room for them
function lowerBottomSeat(spot, board) {
  const k = spot.k;
  spot.bet = offBoard({ ...spot.bet, under: true }, board, k, true);
  const lift = spot.y - seatBox(spot).top;
  spot.y = Math.max(spot.y, unitBox(spot.bet, k).bottom + 4 * k + lift);
}

// On a narrow screen the big corner seats reach the shared cards: they move away from them, down or up
function clearOfBoard(spot, board) {
  const box = seatBox(spot);
  const gap = 4 * spot.k;
  if (box.right <= board.left || box.left >= board.right) {
    return;
  }
  if (spot.outward > 0) {
    spot.y = Math.max(spot.y, board.bottom + gap + (spot.y - box.top));
  } else {
    spot.y = Math.min(spot.y, board.top - gap - (box.bottom - spot.y));
  }
}

// The top seat's chips sit over the pot; a big seat moves up to make room
function placeTop(spot, pot, k, table) {
  const under = Boolean(spot.bet?.under);
  const below = (under ? UNDER.drop + SUM.height / 2 : CHIP / 2) * k;
  const y = Math.min(table.bets[3].y, unitBox(pot, k).top - 6 * k - below);
  spot.bet = { ...spot.bet, x: table.bets[3].x, y, side: 1, grow: 1, under, most: pot.most };
  // The tag on the face reaches into the gap between the face and the chips
  spot.y = Math.min(table.plaques[3].y, y - (CHIP / 2 + pileRise(pot.most) + 6) * k - (FACE + RIM) * k);
}

// The free stretch of a bet's row for its words, as far as no seat, card or other bet is. A neighbour whose
// words face these ones shares the space between the two piles' middles halfway. shared: every neighbour shares the
// space between the two bets halfway, for words that sit centered on the bet with no chips (a shown hand's name).
// band: how high the words reach, when that's more than the row
function laneFor(bet, plan, others, obstacles, shared, band = null) {
  const { k, table } = plan;
  const half = (SUM.height / 2 + 2) * k;
  const row = band ? { top: band.top, bottom: band.bottom } : { top: bet.y - half, bottom: bet.y + half };
  // Never past the part of the table every screen shows
  let left = (table.width - table.fit) / 2;
  let right = (table.width + table.fit) / 2;
  for (const box of obstacles) {
    if (box.bottom > row.top && box.top < row.bottom) {
      if (box.right <= bet.x) {
        left = Math.max(left, box.right);
      } else if (box.left >= bet.x) {
        right = Math.min(right, box.left);
      }
    }
  }
  // The middle of a bet's pile, or the bet itself for words under it or centered on it
  const middleOf = (one) => (one.under || shared ? one.x : one.x + (one.grow * PILE_WIDE * k) / 2);
  for (const other of others) {
    const facing = !other.under && (other.x < bet.x ? other.side > 0 : other.side < 0);
    const level = other.y + half > row.top && other.y - half < row.bottom;
    if (level && other.x !== bet.x && (shared || facing)) {
      const middle = (middleOf(bet) + middleOf(other)) / 2;
      left = other.x < bet.x ? Math.max(left, middle) : left;
      right = other.x > bet.x ? Math.min(right, middle) : right;
    }
  }
  const gap = 4 * k;
  return { left: left + gap, right: right - gap, ...row };
}

// The viewer's own seat and the bottom seat a watcher sees are never on the table together
function together(one, other) {
  return one !== other && !(one.only && other.only && one.only !== other.only);
}

// What a bet's chips and words must stay clear of: every seat, the shared cards, the practice label's place, and the
// other bets' chips. The pot takes the top seat along when it moves, so that one never blocks it
function obstaclesFor(unit, units, plan) {
  const others = units.filter((other) => together(unit, other) && !(unit.carries && other.spot === plan.spots[3]));
  const seats = [unit, ...others].filter((other) => other.seat);
  const fixed = [plan.board, noteBox(plan.note, plan.k)];
  return [...seats.flatMap((other) => other.seat()), ...fixed, ...others.map((other) => unitBox(other.bet, plan.k))];
}

function laneOf(unit, units, plan, shared = false) {
  const others = units.filter((other) => together(unit, other)).map((other) => other.bet);
  return laneFor(unit.bet, plan, others, obstaclesFor(unit, units, plan), shared);
}

// A bet with its amount under its chips, as wide as its row is free (up to UNDER.most, so a long amount keeps every
// digit) and moved along the row to fit, or null when even UNDER.width doesn't fit there
function underFits(unit, bet, units, plan) {
  const k = plan.k;
  const obstacles = obstaclesFor(unit, units, plan);
  const others = units.filter((other) => together(unit, other)).map((other) => other.bet);
  const free = laneFor(bet, plan, others, obstacles, false, unitBox({ ...bet, width: UNDER.width }, k));
  const width = Math.min(UNDER.most, (free.right - free.left) / k);
  if (width < UNDER.width) {
    return null;
  }
  const half = (width / 2) * k;
  const placed = { ...bet, width, x: Math.min(Math.max(bet.x, free.left + half), free.right - half) };
  return obstacles.some((other) => overlaps(unitBox(placed, k), other)) ? null : placed;
}

// Each bet's words go beside its chips when its lane has room for an amount, else under them when that space is
// free, else beside them, shortened to fit. The pot keeps its words beside down to a short amount's room ("12K"),
// since words under it would push the top seat up. Words under their chips take what room their row has
function settleBets(units, plan) {
  const k = plan.k;
  for (const unit of units) {
    unit.bet.lane = laneOf(unit, units, plan);
    let placed = null;
    if (unit.bet.under) {
      placed = underFits(unit, unit.bet, units, plan);
    } else if (!unit.fixed && labelRoom(unit.bet, k) < LABEL * (unit.carries ? 0.8 : 1)) {
      const under = offBoard({ ...unit.bet, under: true }, plan.board, k, unit.bet.y > plan.board.bottom);
      placed = underFits(unit, under, units, plan);
    }
    if (placed) {
      unit.set(placed);
    }
  }
  units.forEach((unit) => {
    unit.bet.lane = laneOf(unit, units, plan);
    unit.bet.zone = laneOf(unit, units, plan, true);
  });
}

// The viewer's own seat: as low as the table allows, so their cards lie over the rail, but never so high that their
// cards crowd the shared ones; their bet sits between. lowest is the lowest the plate may reach; big: how much bigger
// than usual their cards are
function heroSpot({ k, px, nameWidth, board, table }, lowest, under, most, big) {
  const spot = { x: table.plaques[0].x, y: 0, k, px, nameWidth, outward: 1, inward: 1, hero: true, big };
  const [cards, plate] = heroParts(spot);
  const above = -cards.top;
  const below = plate.bottom;
  const highestBet = board.bottom + (CHIP / 2 + pileRise(most) + 3) * k;
  const drop = (under ? UNDER.drop + SUM.height / 2 : CHIP / 2) * k;
  const highest = highestBet + drop + 4 * k + above;
  spot.y = Math.max(highest, Math.min(table.felt.bottom - 20 + above, lowest - below));
  const lowestBet = spot.y - above - 4 * k - drop;
  const y = Math.min(table.bets[0].y, (highestBet + lowestBet) / 2);
  spot.bet = { x: table.bets[0].x, y, side: 1, grow: -1, under, most };
  return spot;
}

// The viewer's own seat with their cards as big as the table draws them, or smaller where a narrow screen brings
// the bottom corner seats too close to them
function placeHero(plan, lowest, under, most) {
  const corners = [plan.spots[1], plan.spots[5]].map(seatBox);
  const crowded = (hero) => corners.some((box) => heroParts(hero).some((part) => overlaps(box, part)));
  let hero = heroSpot(plan, lowest, under, most, plan.table.big);
  for (let big = plan.table.big - 0.05; big >= 1 && crowded(hero); big -= 0.05) {
    hero = heroSpot(plan, lowest, under, most, big);
  }
  return hero;
}

// A bottom corner seat's bet moves up out of the row of the bet in the middle (the viewer's, or the bottom seat's a
// watcher sees), so its words reach toward the middle over those chips. It never moves onto the shared cards
function liftOverMiddle(spot, middles, board) {
  const k = spot.k;
  const bet = spot.bet;
  const top = Math.min(...middles.map((middle) => unitBox(middle, k).top)) - 2 * k;
  const box = unitBox(bet, k);
  const bottom = Math.max(box.bottom, bet.y + (SUM.height / 2 + 2) * k);
  if (bottom > top) {
    bet.y = Math.max(board.bottom + 3 * k + (bet.y - box.top), bet.y - (bottom - top));
  }
}

// Where the practice label goes on the felt, in table units: across, in the shared cards' row between the felt's left
// end and the cards; upright, between the top seat's chips and the pot, as wide as the side seats there leave room
// for. Its words fit its width
function notePlace(plan) {
  const { k, board, table, pot, spots } = plan;
  const height = SUM.height * k;
  if (table === TABLES.across) {
    const left = table.felt.left + 8 * k;
    const right = board.left - 8 * k;
    return { x: (left + right) / 2, y: table.board.y, width: right - left, height };
  }
  const y = (unitBox(spots[3].bet, k).bottom + unitBox(pot, k).top) / 2;
  const row = { top: y - height, bottom: y + height };
  const beside = [spots[2], spots[4]].map(seatBox).filter((box) => box.bottom > row.top && box.top < row.bottom);
  const reach = Math.min(table.middle.x - table.felt.left, ...beside.map((box) => Math.abs(box.left - table.middle.x)));
  const left = Math.max(table.felt.left, ...beside.filter((box) => box.left < table.middle.x).map((box) => box.right));
  const half = Math.min(reach, table.middle.x - left) - 8 * k;
  return { x: table.middle.x, y, width: 2 * half, height };
}

function noteBox(note, k) {
  return {
    left: note.x - note.width / 2,
    right: note.x + note.width / 2,
    top: note.y - note.height / 2 - 2 * k,
    bottom: note.y + note.height / 2 + 2 * k,
  };
}

// Every bet on the felt and the pot, for settling where their words go. set(bet) moves one; the top seat follows the
// pot
function unitsOf(plan) {
  const { spots, hero, k, table } = plan;
  const units = [];
  const top = () => {
    placeTop(spots[3], plan.pot, k, table);
    units[4].bet = spots[3].bet;
  };
  units.push({
    bet: plan.pot,
    carries: true,
    set(bet) {
      this.bet = plan.pot = bet;
      top();
    },
  });
  spots.forEach((spot, slot) => {
    units.push({
      bet: spot.bet,
      spot,
      only: slot ? null : "watching",
      seat: () => [seatBox(spot)],
      fixed: slot === 0,
      set(bet) {
        this.bet = spot.bet = bet;
        if (slot === 3) {
          top();
        }
      },
    });
  });
  units.push({
    bet: hero.bet,
    spot: hero,
    only: "seated",
    fixed: true,
    seat: () => heroParts(hero),
    set(bet) {
      this.bet = hero.bet = bet;
    },
  });
  return units;
}

// The shared cards' size at a scale: the table's own, or bigger where that would be too small to read
function boardAt(scale, table) {
  return boardBox(Math.max(table.board.scale, CARD_MIN / (CARD.width * scale)), table);
}

// Everything's place at one scale. lowest: how far down the viewer's plate may go. under: whether the viewer's words
// and the bottom seat's go under their chips, which moves those seats down. most: how high chips pile. watching: the
// viewer has no seat, so the table is planned with six seats on the rail and no seat of their own
function planAt(table, scale, lowest, under, most, watching) {
  const k = Math.max(1, NAME_MIN / (NAME_FONT * scale));
  // CSS pixels per seat unit, for the smallest words a seat may draw
  const px = k * scale;
  const nameWidth = k > 1.15 ? 84 : 100;
  const board = { ...boardAt(scale, table), y: table.board.y };
  const spots = table.plaques.map((plaque, slot) => {
    return { ...plaque, k, px, nameWidth, outward: table.outward[slot], inward: table.inward[slot] };
  });
  // The pot sits just over the shared cards, so the top seat over it keeps as much room as it can. Its amount is on
  // its right and its second column of chips on its left, so the amount starts close to it
  const potY = board.top - (12 + CHIP / 2) * k;
  const pot = offBoard({ ...table.pot, y: potY, side: 1, grow: -1, under: false, most }, board, k, false);
  [1, 2, 4, 5].forEach((slot) => clearOfBoard(spots[slot], board));
  [0, 1, 2, 4, 5].forEach((slot) => {
    spots[slot].bet = betSpot(spots[slot], slot, board, most, table);
  });
  placeTop(spots[3], pot, k, table);
  if (under.bottom) {
    lowerBottomSeat(spots[0], board);
  }
  const plan = { table, scale, k, px, nameWidth, spots, board, pot };
  plan.hero = placeHero(plan, lowest, under.hero, most);
  [1, 5].forEach((slot) => liftOverMiddle(spots[slot], [plan.hero.bet, spots[0].bet], board));
  plan.note = notePlace(plan);
  settleBets(unitsOf(plan), plan);
  const boxes = watching ? spots.map(seatBox) : [...spots.map(seatBox), heroBox(plan.hero)];
  plan.top = Math.min(table.rail.top - 8, ...boxes.map((box) => box.top));
  plan.bottom = Math.max(table.rail.bottom + 8, ...boxes.map((box) => box.bottom));
  // How far the seats reach from the middle of the table, left or right
  const middle = table.width / 2;
  plan.reach = Math.max(...boxes.map((box) => Math.max(middle - box.left, box.right - middle)));
  return plan;
}

// The viewer's words and the bottom seat's go beside their chips when they get half the way to the nearer bottom
// corner's bet (whose words face theirs), else under them
function planFor(table, scale, lowest, most, watching) {
  const k = Math.max(1, NAME_MIN / (NAME_FONT * scale));
  const board = boardAt(scale, table);
  const corners = [1, 5].map((slot) => {
    const spot = { ...table.plaques[slot], k, nameWidth: k > 1.15 ? 84 : 100 };
    Object.assign(spot, { outward: table.outward[slot], inward: table.inward[slot] });
    return Math.abs(betSpot(spot, slot, board, most, table).x - table.bets[0].x);
  });
  const room = (Math.min(...corners) / 2 - 4 * k) / k - (CHIP / 2 + GAP);
  const crowded = room < LABEL;
  return planAt(table, scale, lowest, { hero: crowded, bottom: crowded }, most, watching);
}

// Everything at one scale, the viewer's seat as low as a space height tall allows
function fittedAt(table, scale, height, most, watching) {
  const loose = planFor(table, scale, Infinity, most, watching);
  return planFor(table, scale, loose.top + height / scale, most, watching);
}

// The biggest scale that fits one table and its seats inside the scene's edges, EDGE in from them, and the offsets
// that center them. Seats grow as the table shrinks, so a smaller table can need more room: the scale steps down
// until everything fits. Chips pile tall when that fits at the same scale
function arrangeOn(table, width, height, watching) {
  const room = height - EDGE * 2;
  const biggest = Math.min(width / table.fit, room / table.height);
  // How far a plan spills past the scene's edges, in CSS pixels. A screen too small for every scale keeps the plan
  // that spills least
  const spill = (one) => {
    return Math.max(0, (one.bottom - one.top) * one.scale - room, one.reach * one.scale - (width / 2 - EDGE));
  };
  const fits = (one) => spill(one) === 0;
  let plan = fittedAt(table, biggest, room, PILE.low, watching);
  let least = plan;
  for (let scale = biggest * 0.985; scale > biggest / 2 && !fits(plan); scale *= 0.985) {
    plan = fittedAt(table, scale, room, PILE.low, watching);
    least = spill(plan) < spill(least) ? plan : least;
  }
  plan = fits(plan) ? plan : least;
  plan.watching = watching;
  const tall = fittedAt(table, plan.scale, room, PILE.tall, watching);
  tall.watching = watching;
  // Tall piles stand further apart, so they only come where they cost no seat or bet its room: a narrow phone keeps
  // the upright table with low piles rather than turning to the smaller table across
  plan = fits(tall) && (roomy(tall) || !roomy(plan)) ? tall : plan;
  plan.left = (width - table.width * plan.scale) / 2;
  plan.offset = (height - (plan.bottom - plan.top) * plan.scale) / 2 - plan.top * plan.scale;
  plan.view = {
    left: -plan.left / plan.scale,
    right: (width - plan.left) / plan.scale,
    top: -plan.offset / plan.scale,
    bottom: (height - plan.offset) / plan.scale,
  };
  return plan;
}

// How much of the scene a table fills, in square CSS pixels
function filled(plan) {
  return plan.table.width * plan.table.height * plan.scale * plan.scale;
}

// Whether every seat has its own room and every bet room for a short amount beside or under its chips (LABEL less a
// fifth: "12K"), for a watcher's six seats and for the viewer's own seat with the other five
function roomy(plan) {
  const seats = plan.spots.slice(1).map(seatBox);
  const apart = (boxes) => boxes.every((box, one) => boxes.slice(one + 1).every((other) => !overlaps(box, other)));
  // The parts of the viewer's own seat lie against each other; each keeps clear of the other seats
  const own = plan.watching || heroParts(plan.hero).every((part) => seats.every((box) => !overlaps(part, box)));
  const bets = [plan.pot, plan.hero.bet, ...plan.spots.map((spot) => spot.bet)];
  return apart([seatBox(plan.spots[0]), ...seats]) && own && bets.every((bet) => labelRoom(bet, plan.k) >= LABEL * 0.8);
}

// The table that fills more of the scene: upright on a tall screen, across on a wide one. The two fill it equally
// close to a square, so the table never jumps in size where it turns, and a dock that grows or shrinks a little
// never turns it. On a small screen close to square the upright table can't give every seat and bet its room: there
// the table stays across. shape ("across" or "upright") picks one, for checking each at any size. watching: the viewer
// has no seat, so the table is centered with its six seats and nothing of the viewer's own
function arrange(width, height, shape = null, watching = false) {
  if (shape) {
    return arrangeOn(TABLES[shape], width, height, watching);
  }
  const across = arrangeOn(TABLES.across, width, height, watching);
  if (width >= height) {
    return across;
  }
  const upright = arrangeOn(TABLES.upright, width, height, watching);
  return filled(upright) > filled(across) && roomy(upright) ? upright : across;
}

export function layoutFor(width, height, shape = null, watching = false) {
  const plan = arrange(width, height, shape, watching);
  const { scale, left, offset, k } = plan;
  const box = (b) => ({
    left: left + b.left * scale,
    top: offset + b.top * scale,
    width: (b.right - b.left) * scale,
    height: (b.bottom - b.top) * scale,
  });
  // A bet's chips, the space its words may take beside or under them, and its whole lane, in CSS pixels
  const bet = (one) => ({
    chips: box(unitBox(one, k)),
    words: box(labelBox(one, k)),
    lane: box(one.lane),
    zone: box(one.zone),
    under: one.under,
  });
  // The marks on a seat that must never meet (the dealer button, the face's tag, shown cards, your cards and your
  // hand's tag)
  const marks = (spot) => Object.fromEntries(Object.entries(seatMarks(spot)).map(([name, mark]) => [name, box(mark)]));
  return {
    table: plan.table === TABLES.across ? "across" : "upright",
    scale,
    cardScale: plan.board.scale * scale,
    seats: plan.spots.map((spot) => ({
      x: left + spot.x * scale,
      y: offset + spot.y * scale,
      nameSize: NAME_FONT * spot.k * scale,
      nameWidth: spot.nameWidth * spot.k * scale,
      name: box(nameBox(spot)),
      box: box(seatBox(spot)),
      bet: bet(spot.bet),
      marks: marks(spot),
    })),
    hero: {
      ...box(heroBox(plan.hero)),
      parts: heroParts(plan.hero).map(box),
      bet: bet(plan.hero.bet),
      marks: marks(plan.hero),
    },
    board: box(plan.board),
    pot: { x: left + plan.pot.x * scale, y: offset + plan.pot.y * scale, ...bet(plan.pot) },
    note: box(noteBox(plan.note, k)),
    dealer: { x: left + plan.table.dealer.x * scale, y: offset + plan.table.dealer.y * scale },
  };
}

// ---- Drawing helpers ----

function loadPicture(name) {
  return Assets.load(new URL(`../art/holdem/${name}`, import.meta.url).href);
}

// The room around the table: the wallpaper repeated to every edge of the scene, the table's picture over it (its
// wallpaper is the same tile, lined up), and the dark gathering toward the scene's edges
function roomArt(wallpaper) {
  const art = new Container();
  art.wall = new TilingSprite({ texture: wallpaper, width: 1, height: 1 });
  art.picture = new Sprite();
  art.shade = new Sprite();
  art.addChild(art.wall, art.picture, art.shade);
  return art;
}

// A soft dark ring, clear inside clear (0 to 1 of its radius) and darkest at its edge, for the scene's corners
function shadeTexture(clear) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const context = canvas.getContext("2d");
  const ring = context.createRadialGradient(128, 128, 0, 128, 128, 128);
  ring.addColorStop(0, "rgba(10, 4, 2, 0)");
  ring.addColorStop(Math.min(0.95, clear), "rgba(10, 4, 2, 0)");
  ring.addColorStop(1, "rgba(10, 4, 2, 0.62)");
  context.fillStyle = ring;
  context.fillRect(0, 0, 256, 256);
  return Texture.from(canvas);
}

// How far a pile reaches around where it stands, in its parent's units
function pileBox(stack) {
  const bounds = stack.getLocalBounds();
  const scale = Math.abs(stack.scale.x);
  const [left, right, top, bottom] = [bounds.minX, bounds.maxX, bounds.minY, bounds.maxY].map((one) => one * scale);
  return { left, right, top, bottom };
}

// Which pot a pile is, before its amount, once there are side pots: "Main ", then "Side ", or "Side 1 ", "Side 2 "
// when there are more
function potName(index, count) {
  if (count < 2) {
    return "";
  }
  if (index === 0) {
    return "Main ";
  }
  return count > 2 ? `Side ${index} ` : "Side ";
}

function destroyChildren(container) {
  container.removeChildren().forEach((child) => child.destroy({ children: true }));
}

function settle(piece) {
  return piece.destroyed ? null : piece;
}

// A card fades into the dark without turning see-through, so nothing behind it shows
function darken(piece, ms) {
  let share = 0;
  const shade = {
    get destroyed() {
      return piece.destroyed;
    },
    get k() {
      return share;
    },
    set k(value) {
      share = value;
      const level = Math.min(255, Math.max(DARK, Math.round(255 - (255 - DARK) * value)));
      piece.tint = (level << 16) | (level << 8) | level;
    },
  };
  return tween(shade, { k: 1 }, ms);
}

// ---- The scene ----

export async function createScene(stage) {
  await loadArt();
  const names = ["table.jpg", "table-upright.jpg", "wallpaper.jpg", "button.png"];
  const [across, upright, wallpaper, button] = await Promise.all(names.map(loadPicture));
  const pictures = { [TABLES.across.picture]: across, [TABLES.upright.picture]: upright };
  const scene = new HoldemTable(stage, { pictures, wallpaper, button });
  return {
    show: (state) => scene.show(state),
    play: (event) => scene.play(event),
    hole: (message) => scene.hole(message),
    result() {},
    layout: (width, height) => scene.layout(width, height),
    destroy: () => scene.destroy(),
    // The table itself, for its tests to look inside
    table: scene,
  };
}

class HoldemTable {
  // art: the table's pictures by name, the wallpaper tile and the dealer button
  constructor(stage, { pictures, wallpaper, button }) {
    this.stage = stage;
    this.pictures = pictures;
    this.art = roomArt(wallpaper);
    // The places for the shared cards and the pot's ring, drawn on the felt at the cards' own size
    this.feltMarks = new Graphics();
    this.feltMarks.label = "marks";
    // Where the pot sits, gone once a hand's pot has gone to its winners
    this.potRing = new Graphics();
    this.potRing.label = "pot-ring";
    // The practice label on the felt
    this.note = pill(SUM.font, SUM.height);
    this.note.label = "note";
    this.note.visible = false;
    this.root = new Container();
    this.layers = { felt: new Container(), seats: new Container(), fx: new Container() };
    for (const [name, layer] of Object.entries(this.layers)) {
      layer.label = name;
    }
    this.pot = new Container();
    this.pot.label = "pot";
    this.button = new Sprite(button);
    this.button.anchor.set(0.5);
    this.button.visible = false;
    this.button.label = "button";
    this.watchers = new Container();
    this.layers.felt.addChild(this.feltMarks, this.potRing, this.note, this.pot);
    this.root.addChild(this.art, this.layers.felt, this.layers.seats, this.watchers, this.layers.fx);
    stage.root.addChild(this.root);
    this.seats = Array.from({ length: SEATS }, (_, number) => new Seat(number, this.layers, (seat) => this.sit(seat)));
    // Over every seat: it sits on the corner of the dealer's picture
    this.layers.seats.addChild(this.button);
    this.gliding = false;
    this.playing = false;
    // Set once the table has left the screen: animations still running stop at their next step
    this.closed = false;
    this.board = [];
    this.potKey = "";
    this.watcherKey = "";
    this.buttonSeat = null;
    this.state = null;
    // A table that arrived before the scene had any room, drawn at the first layout
    this.unshown = null;
    // The scene's size in CSS pixels, once laid out
    this.size = null;
    // The newest move of the table to its place, which an older glide gives way to
    this.move = null;
    this.mine = null;
    this.holeCards = null;
    this.plan = null;
    this.won = {};
    this.firstBets = {};
    // How many cards each seat has been dealt this hand
    this.pitched = {};
    this.turnKey = "";
    this.turnAt = null;
    this.ringSeat = null;
    this.ticked = null;
    this.tick = () => this.everyFrame();
    stage.app.ticker.add(this.tick);
  }

  destroy() {
    this.closed = true;
    this.stage.app.ticker.remove(this.tick);
    this.shadeTo(Texture.EMPTY);
  }

  // The dark toward the scene's edges gets a new texture, and the old one, made for the last size, goes
  shadeTo(texture) {
    const shade = this.art.shade;
    const old = shade.texture;
    shade.texture = texture;
    if (old && old !== Texture.EMPTY) {
      old.destroy(true);
    }
  }

  sit(number) {
    this.stage.sound.play("click");
    this.stage.actions.sit(number);
  }

  // ---- Where things go ----

  layout(width, height) {
    if (!(width > 0 && height > 0)) {
      return;
    }
    this.size = [width, height];
    this.replan();
    this.placeAll(false);
    if (this.unshown) {
      const state = this.unshown;
      this.unshown = null;
      this.show(state);
    }
  }

  // The table planned for the scene's size, for a viewer with a seat or without one
  replan(glide = true) {
    const had = glide ? this.plan : null;
    this.plan = arrange(...this.size, null, this.mine === null);
    this.root.scale.set(this.plan.scale);
    this.drawRoom();
    this.potKey = "";
    this.drawPots(this.state?.pots || []);
    // A new size of screen, or sitting down or standing up, glides the table to its new place where its size and
    // picture stay the same; the first table drawn is simply put there. Only the newest move counts: a glide still
    // running from an earlier change stops, so it never pulls the table back to where that change wanted it
    const from = { x: this.root.x, y: this.root.y };
    const to = { x: this.plan.left, y: this.plan.offset };
    const move = {};
    this.move = move;
    const put = (k) => {
      if (this.move === move && !this.root.destroyed) {
        this.root.position.set(from.x + (to.x - from.x) * k, from.y + (to.y - from.y) * k);
      }
    };
    if (had && had.scale === this.plan.scale && had.table === this.plan.table) {
      const share = {
        get k() {
          return 0;
        },
        set k(value) {
          put(value);
        },
      };
      tween(share, { k: 1 }, 220, ease.out);
    } else {
      put(1);
    }
  }

  // The table's picture for this screen, the wallpaper around it to every edge of the scene (its tiles start at the
  // picture's corner, so they line up with the picture's own), and the dark toward the scene's edges
  drawRoom() {
    const { table, view } = this.plan;
    const { wall, picture, shade } = this.art;
    const back = table.background;
    picture.texture = this.pictures[table.picture];
    picture.position.set(back.x, back.y);
    picture.width = back.width;
    picture.height = back.height;
    // A margin past every edge, so the wall still covers the scene while the table glides to a new place
    const spare = WALL_SPARE / this.plan.scale;
    wall.position.set(view.left - spare, view.top - spare);
    wall.width = view.right - view.left + spare * 2;
    wall.height = view.bottom - view.top + spare * 2;
    wall.tilePosition.set(back.x - view.left + spare, back.y - view.top + spare);
    // The dark reaches the scene's farthest corner, and stays clear over the table
    const middle = table.middle;
    const reach = {
      x: Math.max(middle.x - view.left, view.right - middle.x) * 1.42,
      y: Math.max(middle.y - view.top, view.bottom - middle.y) * 1.42,
    };
    const rail = { x: (table.fit - 40) / 2 + 30, y: (table.rail.bottom - table.rail.top) / 2 + 30 };
    this.shadeTo(shadeTexture(Math.min(rail.x / reach.x, rail.y / reach.y)));
    shade.anchor.set(0.5);
    shade.position.set(middle.x, middle.y);
    shade.width = reach.x * 2;
    shade.height = reach.y * 2;
  }

  // The five places for the shared cards and the pot's ring, thin gold lines on the felt at the cards' real size
  drawFeltMarks() {
    const { board, pot, k } = this.plan;
    const width = CARD.width * board.scale;
    const height = CARD.height * board.scale;
    const marks = this.feltMarks.clear();
    for (let index = 0; index < 5; index += 1) {
      const spot = this.boardSpot(index);
      marks.roundRect(spot.x - width / 2, spot.y - height / 2, width, height, width * 0.1);
    }
    marks.stroke({ width: 1.6, color: GOLD, alpha: 0.75 });
    this.potRing.clear().circle(pot.x, pot.y, 19 * k).stroke({ width: 1.6, color: GOLD, alpha: 0.75 });
  }

  // While the table practices, a label on the felt says the chips are play chips, not credits
  drawNote() {
    const practice = this.state?.mode === "practice";
    this.note.visible = practice && Boolean(this.plan);
    if (!this.note.visible) {
      return;
    }
    const { note, k, px } = this.plan;
    const room = note.width / k - SUM.height * PAD * 2;
    const fit = fitSized(PRACTICE, this.note.words.style, room, SMALLEST / px, SUM.font);
    setPill(this.note, fit.text, { fill: CREAM, stroke: GOLD_DEEP }, fit.size);
    this.note.position.set(note.x, note.y);
    this.note.scale.set(k);
  }

  slotOf(number) {
    return this.mine === null ? number : (number - this.mine + SEATS) % SEATS;
  }

  spotOf(number) {
    const slot = this.slotOf(number);
    return slot === 0 && this.mine !== null ? this.plan.hero : this.plan.spots[slot];
  }

  placeAll(glide) {
    if (!this.plan) {
      return;
    }
    const plan = this.plan;
    this.seats.forEach((seat) => {
      const from = { x: seat.group.x, y: seat.group.y };
      seat.place(this.spotOf(seat.number));
      if (glide) {
        // The viewer sat down: the table turns so their seat comes to the bottom. A new layout during the turn (the
        // dock growing) puts the seat at its new spot once the turn ends
        const to = { x: seat.group.x, y: seat.group.y };
        seat.group.position.set(from.x, from.y);
        tween(seat.group, to, 450, ease.inOut).then(() => {
          if (this.plan !== plan && !seat.group.destroyed) {
            seat.place(this.spotOf(seat.number));
          }
        });
      }
    });
    this.board.forEach((piece, index) => this.placeBoardCard(piece, index));
    this.placePot();
    this.placeButton(false);
    this.placeWatchers();
    this.drawFeltMarks();
    this.drawNote();
  }

  boardSpot(index) {
    const { board, table } = this.plan;
    return { x: table.board.x + (index - 2) * board.step, y: table.board.y, scale: board.scale };
  }

  // Where dealt cards come from and the cut goes: the deck in the dealer's tray
  dealerPoint() {
    return this.plan.table.dealer;
  }

  placeBoardCard(piece, index) {
    const spot = this.boardSpot(index);
    piece.position.set(spot.x, spot.y - (piece.lifted ? BOARD_LIFT : 0));
    piece.scale.set(spot.scale);
    piece.rotation = 0;
  }

  placeButton(glide) {
    if (this.buttonSeat === null || !this.plan) {
      this.button.visible = false;
      return Promise.resolve();
    }
    const seat = this.seats[this.buttonSeat];
    const spot = seat.buttonPoint();
    this.button.scale.set((BUTTON / this.button.texture.width) * seat.spot.k);
    if (glide && this.button.visible) {
      this.gliding = true;
      return tween(this.button, { x: spot.x, y: spot.y }, MS.button, ease.inOut).then(() => {
        this.gliding = false;
      });
    }
    this.button.visible = true;
    if (!this.gliding) {
      this.button.position.set(spot.x, spot.y);
    }
    return Promise.resolve();
  }

  // ---- The table as the bot describes it ----

  show(state) {
    if (!this.plan) {
      this.unshown = state;
      return;
    }
    const first = this.state === null;
    const me = this.stage.me();
    const mine = (state.seats || []).find((seat) => seat && seat.id === me)?.seat ?? null;
    if (this.state && state.hand !== this.state.hand) {
      this.newHand();
    }
    this.state = state;
    if (mine !== this.mine) {
      // Sitting down or standing up plans the table again: a viewer with no seat sees it centered
      const watching = (this.mine === null) !== (mine === null);
      this.mine = mine;
      if (watching && this.size) {
        this.replan(!first);
      }
      this.placeAll(!first);
    }
    (state.seats || []).forEach((seat, number) => this.drawSeat(number, seat, first));
    this.drawBoard(state.board || []);
    this.drawPots(state.pots || []);
    if (state.button !== this.buttonSeat) {
      this.buttonSeat = state.button;
      this.placeButton(false);
    }
    this.drawWatchers(state);
    this.drawNote();
    this.followTurn(state);
  }

  // A new hand: last hand's cards leave the table, and its winners and first bets no longer count
  newHand() {
    this.potRing.visible = true;
    this.potRing.renderable = true;
    this.won = {};
    this.firstBets = {};
    this.pitched = {};
    for (const view of this.seats) {
      if (view.cards.length) {
        this.muck(view.giveUpCards(), view);
      }
    }
    this.muck(this.board.splice(0));
    if (this.state) {
      const seats = (this.state.seats || []).map((seat) => seat && { ...seat, cards: 0, last: null, folded: false });
      this.state = { ...this.state, seats, board: [], shown: null };
    }
  }

  hole(message) {
    this.holeCards = message;
    if (this.state && this.mine !== null) {
      this.drawSeat(this.mine, this.state.seats[this.mine], false);
    }
  }

  // The viewer's own cards for the hand on the table, when the bot has told them
  myCards() {
    const hole = this.holeCards;
    return hole && this.state && hole.hand === this.state.hand ? hole : null;
  }

  // The tag on a seat's face while a betting round lasts: its last move. The viewer's own moves show in the dock
  moveFor(number, seat) {
    if (!seat.last || number === this.mine) {
      return null;
    }
    return moveWords(seat.last, this.state.stakes, this.firstBets[number] ? "bet" : null);
  }

  // A hand's name to show: one turned face up at a showdown, or the viewer's own while they hold it. Gold once it
  // wins. It shortens to fit ("Two pair, 7s and 2s" to "Two pair", "Three of a kind, 7s" to "Trips 7s")
  handFor(number, seat) {
    const won = this.won[number] !== undefined;
    const held = number === this.mine && ((seat.cards || 0) >= 2 || won);
    const name = this.state.shown?.[number]?.name || (held ? this.myCards()?.name : "");
    if (!name) {
      return null;
    }
    return { text: name, shorter: handNames(name).slice(1), color: won ? GOLD_LIGHT : CREAM, won };
  }

  // The gold label on the felt in front of a seat that won, in place of a bet's amount. A win is never rounded
  feltWords(number) {
    const won = this.won[number];
    if (won === undefined) {
      return null;
    }
    return { text: `Won ${money(won)}`, shorter: [`+${money(won)}`], color: INK, back: GOLD_LIGHT };
  }

  lookFor(number, seat) {
    if (!seat) {
      return { canSit: this.mine === null, turn: false, move: null, hand: null };
    }
    const move = this.moveFor(number, seat);
    const hand = this.handFor(number, seat);
    const joining = this.joining(seat);
    return { canSit: false, turn: this.state.turn === number, move, hand, joining, fade: this.playing };
  }

  // Someone who bought in for real while a practice hand plays: their play chips aren't theirs, they join next hand
  joining(seat) {
    const seats = this.state.seats || [];
    return this.state.mode === "practice" && !seat.cpu && !seat.in_hand && seats.some((row) => row && row.in_hand);
  }

  drawSeat(number, seat, first) {
    const view = this.seats[number];
    const was = view.data;
    if (view.leaving) {
      return;
    }
    if (was && !seat && !first) {
      // The table no longer has the seat (the CPUs leaving as a real game starts): it fades out, as when it leaves
      this.unseated({ seat: number });
      return;
    }
    view.draw(seat, this.lookFor(number, seat));
    if (!first && !was && seat && !view.appearing) {
      view.appearing = this.fadeSeat(view, 0, 1);
    }
    view.drawBet(seat ? seat.bet : 0, seat ? this.feltWords(number) : null);
    this.syncCards(view, seat);
    if (number === this.buttonSeat) {
      this.placeButton(false);
    }
  }

  async fadeSeat(view, from, to) {
    view.group.alpha = from;
    view.betGroup.alpha = from;
    await Promise.all([tween(view.group, { alpha: to }, MS.seat), tween(view.betGroup, { alpha: to }, MS.seat)]);
    view.appearing = null;
  }

  // The cards a seat should hold: shown ones at a showdown, the viewer's own face up, everyone else's face down
  cardsFor(number, seat) {
    const shown = this.state.shown?.[number];
    const mine = number === this.mine;
    if (shown) {
      return { mode: mine ? "hero" : "shown", faces: shown.cards };
    }
    const count = seat ? seat.cards : 0;
    if (!count) {
      return null;
    }
    const faces = (mine && this.myCards()?.cards) || [null, null];
    return { mode: mine ? "hero" : "tucked", faces: faces.slice(0, count) };
  }

  syncCards(view, seat) {
    const want = this.cardsFor(view.number, seat);
    if (want) {
      view.setCards(want.mode, want.faces);
      return;
    }
    // A finished hand's cards stay on the table until the next deal
    if (this.state.phase === "results" && seat && view.cards.length) {
      return;
    }
    if (view.cards.length) {
      this.muck(view.giveUpCards(), view);
    }
  }

  // Cards swept off the table: they slide to the deck and fade
  muck(pieces, view = null) {
    for (const piece of pieces) {
      if (view) {
        const at = this.layers.fx.toLocal(piece.getGlobalPosition());
        piece.scale.set(piece.scale.x * view.spot.k);
        piece.position.set(at.x, at.y);
      }
      this.layers.fx.addChild(piece);
      const dealer = this.dealerPoint();
      const to = { x: dealer.x, y: dealer.y, alpha: 0, scale: DECK_SCALE, rotation: piece.rotation * 0.3 };
      tween(piece, to, MS.muck, ease.inOut).then(() => settle(piece)?.destroy({ children: true }));
    }
  }

  drawBoard(cards) {
    cards.forEach((card, index) => {
      let piece = this.board[index];
      if (!piece) {
        piece = cardSprite(card);
        piece.label = "board";
        this.board[index] = piece;
        this.layers.felt.addChild(piece);
        this.placeBoardCard(piece, index);
      } else if (!sameCard(piece.card, card)) {
        showCard(piece, card);
      }
    });
    if (this.board.length > cards.length) {
      this.muck(this.board.splice(cards.length));
    }
  }

  // The pot, and any side pots: chips with their amount, beside them or under them as the layout says. With side pots
  // each amount says which pot it is, "Main 1,200" and "Side 1,200", so nobody wonders why there are two piles. An
  // amount shrinks to the smallest readable size if it must, and is never rounded
  drawPots(pots) {
    const key = JSON.stringify(pots);
    if (key === this.potKey || !this.plan) {
      return;
    }
    this.potKey = key;
    destroyChildren(this.pot);
    const shown = pots.filter((amount) => amount > 0);
    // Named side-pot piles stand in a row across the pot's place, so its empty ring would show between them
    this.potRing.renderable = shown.length < 2;
    const room = labelRoom(this.plan.pot, this.plan.k) / Math.max(1, shown.length) - SUM.height * PAD * 2;
    shown.forEach((amount, index) => {
      const group = new Container();
      const sum = pill(SUM.font, SUM.height);
      const words = `${potName(index, shown.length)}${money(amount)}`;
      const fit = fitSized([words], sum.words.style, room, SMALLEST / this.plan.px, SUM.font);
      setPill(sum, fit.text, { fill: GOLD_LIGHT, stroke: GOLD_DEEP }, fit.size);
      group.addChild(chipPile(amount, this.plan.pot.most, this.plan.pot.under ? 0 : 1), sum);
      this.pot.addChild(group);
    });
    this.placePot();
  }

  // The pot's chips sit on its ring; side pots make a row centered on it
  placePot() {
    if (!this.plan) {
      return;
    }
    const under = this.plan.pot.under;
    const groups = this.pot.children;
    for (const group of groups) {
      const [pile, sum] = group.children;
      const wide = (pile.columns - 1) * COLUMN;
      sum.position.set(under ? 0 : CHIP / 2 + wide + GAP + sum.span / 2, under ? UNDER.drop : 0);
      // How far the group reaches to each side of its first column of chips
      const half = Math.max(CHIP + wide, sum.span) / 2;
      group.reach = under ? [half, half] : [CHIP / 2, CHIP / 2 + wide + GAP + sum.span];
    }
    const total = groups.reduce((sum, group) => sum + group.reach[0] + group.reach[1], 0) + (groups.length - 1) * 14;
    let x = -total / 2;
    for (const group of groups) {
      group.x = groups.length > 1 ? x + group.reach[0] : 0;
      x += group.reach[0] + group.reach[1] + 14;
    }
    this.pot.position.set(this.plan.pot.x, this.plan.pot.y);
    this.pot.scale.set(this.plan.k);
  }

  potPoint() {
    return { x: this.plan.pot.x, y: this.plan.pot.y };
  }

  // People at the table who aren't seated, as a row of faces in the corner: the first few, then "+N"
  drawWatchers(state) {
    const seated = new Set((state.seats || []).filter(Boolean).map((seat) => seat.id));
    const people = (state.players || []).filter((person) => !seated.has(person.id));
    const shown = people.slice(0, WATCHER_FACES);
    const key = JSON.stringify([people.length, shown.map((person) => [person.id, person.name, person.avatar])]);
    if (key !== this.watcherKey) {
      this.watcherKey = key;
      destroyChildren(this.watchers);
      shown.forEach((person, index) => this.watchers.addChild(this.watcherFace(person, index)));
      if (people.length > shown.length) {
        const more = pill(NAME_FONT, 24);
        setPill(more, `+${people.length - shown.length}`, { fill: CREAM, stroke: GOLD_DEEP });
        more.x = shown.length * (WATCHER_RADIUS * 2 + 4) + more.span / 2 - WATCHER_RADIUS;
        this.watchers.addChild(more);
      }
      this.placeWatchers();
    }
    const away = new Set(people.filter((person) => person.away).map((person) => person.id));
    this.watchers.children.forEach((face) => {
      face.alpha = face.person && away.has(face.person) ? 0.4 : 1;
    });
  }

  watcherFace(person, index) {
    const face = new Container();
    const picture = new Container();
    picture.key = person.id;
    personFace(picture, person, WATCHER_RADIUS);
    const rim = new Graphics().circle(0, 0, WATCHER_RADIUS + 1).stroke({ width: 2, color: GOLD });
    face.addChild(picture, rim);
    face.x = index * (WATCHER_RADIUS * 2 + 4);
    face.person = person.id;
    return face;
  }

  placeWatchers() {
    if (!this.plan) {
      return;
    }
    const k = this.plan.k;
    const view = this.plan.view;
    this.watchers.scale.set(k);
    this.watchers.position.set(view.left + (WATCHER_RADIUS + 10) * k, view.top + (WATCHER_RADIUS + 10) * k);
  }

  // ---- Whose turn ----

  followTurn(state) {
    const turn = state.turn;
    this.turnAt = turn === null || turn === undefined ? null : { seat: turn, left: state.left, at: performance.now() };
    const me = this.stage.me();
    const mine = turn !== null && turn === this.mine && (state.waiting || []).includes(me);
    const key = mine ? `${state.hand}:${state.street}:${state.round}:${(state.seats[turn] || {}).bet}` : "";
    if (mine && key !== this.turnKey) {
      this.stage.sound.play("turn");
      this.ticked = null;
    }
    this.turnKey = key;
  }

  // Each frame: small face-up cards wear their big rank, the clock ring drains around the acting seat, and the
  // viewer's own last seconds tick
  everyFrame() {
    this.indexCards();
    const now = performance.now();
    const turn = this.turnAt;
    if (this.ringSeat !== null && (!turn || turn.seat !== this.ringSeat)) {
      this.seats[this.ringSeat].stopClock();
      this.ringSeat = null;
    }
    if (!turn) {
      return;
    }
    this.ringSeat = turn.seat;
    const seat = this.seats[turn.seat];
    if (turn.left === null || turn.left === undefined) {
      seat.drawRing(null, 0, now);
      return;
    }
    const seconds = Math.max(0, turn.left - (now - turn.at) / 1000);
    seat.drawRing(seconds / TURN_SECONDS, seconds, now);
    const whole = Math.ceil(seconds);
    if (this.turnKey && whole <= 5 && whole > 0 && whole !== this.ticked) {
      this.ticked = whole;
      this.stage.sound.play("tick");
    }
  }

  // A face-up card drawn too small for its art shows a big rank and suit; a flip or a new size changes it next frame
  indexCards() {
    for (const piece of [...this.board, ...this.seats.flatMap((seat) => seat.cards)]) {
      if (!piece.destroyed) {
        markSmall(piece, drawnWidth(piece) < SMALL_CARD);
      }
    }
  }

  // ---- Events ----

  async play(event) {
    if (!this.state || !this.plan || this.closed) {
      return;
    }
    const handlers = {
      seat: () => this.seated(event),
      unseat: () => this.unseated(event),
      button: () => this.moveButton(event),
      act: () => this.acted(event),
      pitch: () => this.pitch(event),
      sweep: () => this.sweep(event),
      flop: () => this.flop(event),
      street: () => this.street(event, MS.slide, 0),
      runout: () => this.runout(event),
      show: () => this.showdown(event),
      win: () => this.win(event),
    };
    // Any move, deal or end of a round ends the turn that was running; the next state starts the next one
    if (event.kind !== "seat" && event.kind !== "unseat") {
      this.turnAt = null;
      this.state = { ...this.state, turn: null };
    }
    // Words that change while an event plays fade in; a redraw from the table's state is instant
    this.playing = true;
    try {
      await handlers[event.kind]?.();
    } finally {
      this.playing = false;
    }
  }

  async seated({ seat }) {
    const view = this.seats[seat];
    if (view.appearing) {
      await view.appearing;
    }
  }

  // A seat fades out and empties. Its bet's words (a win) go with it. The table without the seat may come before or
  // after: until it comes the seat stays faded
  async unseated({ seat }) {
    const view = this.seats[seat];
    if (!view.data || view.leaving) {
      await view.leaving;
      return;
    }
    view.leaving = this.leave(view, seat);
    await view.leaving;
  }

  async leave(view, number) {
    const who = view.data.id;
    if (view.cards.length) {
      this.muck(view.giveUpCards(), view);
    }
    await Promise.all([tween(view.group, { alpha: 0 }, MS.seat), tween(view.betGroup, { alpha: 0 }, MS.seat)]);
    view.leaving = null;
    if (this.closed) {
      return;
    }
    view.data = null;
    delete this.won[number];
    const gone = this.state?.seats?.[number] === null;
    view.draw(null, gone ? this.lookFor(number, null) : { canSit: false, turn: false, move: null, hand: null });
    view.drawBet(0, null);
    view.group.alpha = 1;
    view.betGroup.alpha = 1;
    // Someone else may have sat there while it faded
    const now = this.state?.seats?.[number];
    if (now && now.id !== who) {
      this.drawSeat(number, now, false);
    }
  }

  // The first event of every hand: the cards are shuffled and the button glides to its seat. The bot numbers this
  // hand one past the table it sent last, so the viewer's own cards for it count from here
  async moveButton({ seat }) {
    this.stage.sound.play("shuffle");
    const glide = this.buttonSeat !== null && this.button.visible;
    this.buttonSeat = seat;
    // The glide starts before the seats redraw, so they leave the moving button alone
    const moving = glide ? this.placeButton(true) : null;
    this.newHand();
    if (this.state.phase !== "playing") {
      this.state = { ...this.state, hand: this.state.hand + 1, phase: "playing" };
    }
    (this.state.seats || []).forEach((row, number) => this.drawSeat(number, row, false));
    if (moving) {
      await moving;
      return;
    }
    this.placeButton(false);
    this.button.alpha = 0;
    await tween(this.button, { alpha: 1 }, MS.button);
  }

  // The highest bet on the table this round
  topBet() {
    return Math.max(0, ...(this.state.seats || []).map((seat) => (seat ? seat.bet : 0)));
  }

  // The seat's row as it is after a move, until the bot's next state confirms it
  changeSeat(number, change) {
    const seats = [...this.state.seats];
    seats[number] = seats[number] ? { ...seats[number], ...change } : seats[number];
    this.state = { ...this.state, seats };
    return seats[number];
  }

  async acted({ seat: number, move, amount, stack }) {
    const view = this.seats[number];
    const before = this.state.seats[number];
    if (!before) {
      return;
    }
    // A raise with nothing bet yet this round is the round's first bet; every move names itself again
    this.firstBets[number] = move === "raise" && this.topBet() === 0;
    const folded = before.folded || move === "fold";
    const last = move === "return" ? { move, amount, back: before.bet - amount } : { move, amount };
    const change = { stack, bet: amount, last, folded, all_in: move === "all_in" };
    const seat = this.changeSeat(number, folded ? { ...change, cards: 0 } : change);
    this.actSound(move, amount - before.bet);
    if (move === "fold") {
      await this.fold(view, seat);
      return;
    }
    view.draw(seat, this.lookFor(number, seat));
    this.pop(view.tag);
    await view.moveBet(amount, this.feltWords(number), MS.chips);
  }

  actSound(move, added) {
    const sound = this.stage.sound;
    if (move === "fold") {
      sound.play("slide");
    } else if (move === "check") {
      sound.play("knock");
    } else if (move === "return") {
      sound.play("chip");
    } else if (added > 0) {
      sound.play("bet");
    }
    if (move === "all_in") {
      sound.play("allin");
    }
  }

  // Words that just changed grow and settle back
  pop(piece) {
    piece.scale.set(1.25);
    tween(piece, { scale: 1 }, 220, ease.back);
  }

  async fold(view, seat) {
    const cards = view.giveUpCards();
    view.draw(seat, this.lookFor(view.number, seat));
    this.pop(view.tag);
    view.body.alpha = 1;
    this.muck(cards, view);
    await tween(view.body, { alpha: 0.5 }, MS.muck);
    if (!this.closed) {
      view.drawBet(seat.bet, null);
    }
  }

  // A card flies to its seat. One the seat already shows (a table that arrived mid-deal drew it) lands on it and is
  // gone, so a seat never holds more than its two
  async pitch({ seat: number }) {
    const view = this.seats[number];
    const mine = number === this.mine;
    const mode = mine ? "hero" : "tucked";
    const index = this.pitched[number] || 0;
    this.pitched[number] = index + 1;
    const spot = view.tableSpot(index, mode);
    const piece = cardSprite(null);
    piece.scale.set(DECK_SCALE);
    this.layers.fx.addChild(piece);
    this.stage.sound.play("deal");
    tween(piece, { scale: spot.scale }, MS.pitch);
    await dealCard(piece, this.dealerPoint(), spot, MS.pitch);
    if (this.closed || piece.destroyed) {
      return;
    }
    if (view.cards.length > index) {
      piece.destroy({ children: true });
      return;
    }
    piece.scale.set(spot.scale / view.spot.k);
    view.takeCard(piece, mode);
    const local = cardSpot(view.spot, index, mode);
    piece.rotation = 0;
    tween(piece, { rotation: local.rotation }, 90);
    // The seat holds this many cards now, until the bot's next table says so too
    const seat = this.state.seats[number] && this.changeSeat(number, { cards: view.cards.length });
    const face = mine ? this.myCards()?.cards[index] : null;
    if (face) {
      flipCard(piece, face, 220);
      // It counts as that card from now, so a table arriving mid-turn leaves it to turn over
      piece.card = face;
    }
    if (mine && seat) {
      view.draw(seat, this.lookFor(number, seat));
    }
  }

  // Every bet slides into the pot, and the round's tags fade. The bets leave the table as they start to slide, so a
  // seat drawn again on the way (its move's tag clearing) never puts its chips back in front of it
  async gatherBets(ms) {
    const pot = this.potPoint();
    const route = (from, to, half) => this.route(from, to, half);
    const gathering = Promise.all(this.seats.map((seat) => seat.gather(pot, ms, route)));
    const seats = this.state.seats.map((seat) => (seat ? { ...seat, bet: 0 } : seat));
    this.state = { ...this.state, seats };
    const moved = await gathering;
    return moved.reduce((sum, amount) => sum + amount, 0);
  }

  // The round is over: each seat's last move clears from its face, and the next round's first bet is a bet again
  clearMoves() {
    this.firstBets = {};
    const seats = this.state.seats.map((seat) => (seat ? { ...seat, last: null } : seat));
    this.state = { ...this.state, seats };
    seats.forEach((seat, number) => {
      if (seat) {
        this.drawSeat(number, seat, false);
      }
    });
  }

  async sweep({ pots }) {
    const any = this.state.seats.some((seat) => seat && seat.bet > 0);
    if (any) {
      this.stage.sound.play("chip");
    }
    await this.gatherBets(MS.sweep);
    if (this.closed) {
      return;
    }
    this.setPots(pots);
    this.clearMoves();
  }

  setPots(pots) {
    this.state = { ...this.state, pots };
    this.drawPots(pots);
  }

  // A card slides out of the deck to its place on the board, face down
  async slideOut(index, ms) {
    const piece = cardSprite(null);
    piece.label = "board";
    this.board[index] = piece;
    this.layers.felt.addChild(piece);
    const plan = this.plan;
    const spot = this.boardSpot(index);
    const dealer = this.dealerPoint();
    piece.scale.set(DECK_SCALE);
    piece.position.set(dealer.x, dealer.y);
    tween(piece, { scale: spot.scale }, ms * 0.8, ease.out);
    await tween(piece, { x: spot.x, y: spot.y }, ms, ease.out);
    // The table took a new shape while the card slid (the phone turned): it goes to its place on the new one
    if (this.plan !== plan && !piece.destroyed) {
      this.placeBoardCard(piece, index);
    }
    return piece;
  }

  async flop({ cards }) {
    this.clearMoves();
    this.stage.sound.play("slide");
    const start = this.board.length;
    const pieces = await Promise.all(cards.map((card, index) => this.slideOut(start + index, MS.slide)));
    await Promise.all(
      pieces.map(async (piece, index) => {
        await wait(index * 150);
        if (!piece.destroyed) {
          this.stage.sound.play("deal");
          await flipCard(piece, cards[index], MS.flip);
        }
      }),
    );
    this.state = { ...this.state, board: [...(this.state.board || []), ...cards] };
  }

  async street({ card }, slide, hold) {
    this.clearMoves();
    if (hold) {
      await wait(hold);
      if (this.closed) {
        return;
      }
    }
    this.stage.sound.play("slide");
    const piece = await this.slideOut(this.board.length, slide);
    if (piece.destroyed) {
      return;
    }
    await flipCard(piece, card, hold ? 420 : MS.flip);
    this.state = { ...this.state, board: [...(this.state.board || []), card] };
  }

  // A card dealt once nobody can bet: any bets left join the pot, a beat of suspense, then it turns over
  async runout(event) {
    const started = performance.now();
    if (this.state.seats.some((seat) => seat && seat.bet > 0)) {
      this.stage.sound.play("chip");
      const gathered = await this.gatherBets(MS.sweep);
      if (this.closed) {
        return;
      }
      this.addToPot(gathered);
    }
    const hold = Math.max(0, 520 - (performance.now() - started));
    await this.street(event, 300, hold);
  }

  // Chips gathered without a sweep join the pot as one amount until the bot's next state splits them
  addToPot(amount) {
    if (amount > 0) {
      const pots = [...(this.state.pots || [])];
      pots[Math.max(0, pots.length - 1)] = (pots[pots.length - 1] || 0) + amount;
      this.state = { ...this.state, pots };
      this.drawPots(pots);
    }
  }

  // Betting is over: any bets join the pots the bot names, main pot first, so a side pot slides in as a pile of its
  // own; then each hand still in turns face up and its plate names it
  async showdown({ hands, pots }) {
    this.stage.sound.play("slide");
    const bets = this.state.seats.some((seat) => seat && seat.bet > 0) ? this.gatherBets(300) : Promise.resolve();
    const gather = bets.then(() => !this.closed && this.setPots(pots));
    this.clearMoves();
    const numbers = Object.keys(hands).map(Number);
    const step = numbers.length > 1 ? Math.min(120, 380 / (numbers.length - 1)) : 0;
    const reveals = numbers.map(async (number, order) => {
      await wait(order * step);
      if (!this.closed) {
        await this.seats[number].reveal(hands[number].cards, 480);
      }
    });
    await Promise.all([gather, ...reveals]);
    if (this.closed) {
      return;
    }
    this.state = { ...this.state, shown: hands };
    numbers.forEach((number) => {
      const seat = this.state.seats[number];
      if (seat) {
        this.drawSeat(number, seat, false);
        const view = this.seats[number];
        this.pop(number === this.mine ? view.handTag : view.stack);
      }
    });
  }

  // ---- The win ----

  // Within the win's 1.8 seconds, even with bets left to gather, a cut, a split and a big pot, with time to spare on
  // a slow phone: the winning cards light up, the cut leaves, the pot slides to its winners and they celebrate as it
  // lands
  async win({ awards, best, cut, big }) {
    if (this.state.seats.some((seat) => seat && seat.bet > 0)) {
      const gathered = await this.gatherBets(200);
      if (this.closed) {
        return;
      }
      this.addToPot(gathered);
    }
    this.clearMoves();
    this.highlight(Object.values(best || {}).flat());
    if (cut > 0) {
      this.takeCut(cut);
    }
    await wait(cut > 0 ? 120 : 60);
    if (this.closed) {
      return;
    }
    destroyChildren(this.pot);
    this.potKey = JSON.stringify([]);
    this.potRing.visible = false;
    this.stage.sound.play("collect");
    const shares = {};
    for (const award of awards) {
      for (const [number, amount] of Object.entries(award.shares)) {
        shares[number] = (shares[number] || 0) + amount;
      }
    }
    const split = awards.some((award) => Object.keys(award.shares).length > 1);
    const pushes = Promise.all(awards.map((award, order) => this.pushPot(award, order, awards.length, split)));
    await wait((split ? SPLIT_MS : 0) + 340);
    if (this.closed) {
      return;
    }
    if (big) {
      this.stage.sound.play("bigwin");
    }
    const parties = Object.entries(shares).map(([number, amount]) => this.celebrate(Number(number), amount, big));
    await Promise.all([pushes, ...parties]);
    this.state = { ...this.state, pots: [] };
  }

  // The winning five cards lift and glow; every other card on the table dims. The shared cards lift up; a seat's shown
  // cards lift away from its plate and glow thinner, so its hand's name on the plate stays clear; the player's own big
  // cards glow thinner and stay put, with their hand's tag under them and their bet's words just above
  highlight(cards) {
    if (!cards.length) {
      return;
    }
    const owners = new Map(this.seats.flatMap((seat) => seat.cards.map((piece) => [piece, seat])));
    for (const piece of [...this.board, ...owners.keys()]) {
      const winning = piece.card && cards.some((card) => sameCard(card, piece.card));
      if (!winning) {
        darken(piece, 260);
        continue;
      }
      const seat = owners.get(piece);
      const mine = Boolean(seat) && seat.number === this.mine;
      const [out, width] = seat ? [WON_CARD.out, WON_CARD.width] : [GLOW.board - 3.5, 7];
      const glow = new Graphics()
        .roundRect(-CARD.width / 2 - out, -CARD.height / 2 - out, CARD.width + out * 2, CARD.height + out * 2, 9 + out)
        .stroke({ width, color: GOLD_LIGHT, alpha: 0.95 });
      glow.label = "glow";
      piece.addChildAt(glow, 0);
      if (!mine) {
        piece.lifted = true;
        const lift = seat ? WON_CARD.lift * seat.spot.outward : BOARD_LIFT;
        tween(piece, { y: piece.y - lift }, 260, ease.out);
      }
    }
  }

  // The casino's cut: its chips leave the pot for the dealer's tray, around the shared cards, and a label over the pot
  // (above the tallest pile a split makes) says how much, held a second before it fades
  takeCut(cut) {
    const k = this.plan.k;
    const most = this.plan.pot.most;
    const stack = chipPile(cut, most);
    stack.scale.set((CHIP / 52) * k);
    const pot = this.potPoint();
    stack.position.set(pot.x, pot.y);
    this.layers.fx.addChild(stack);
    const note = pill(SUM.font, SUM.height);
    setPill(note, `House ${money(cut)}`, { fill: CREAM, stroke: GOLD_DEEP });
    note.scale.set(k);
    const above = Math.min(pot.y, this.clearOfCards(0).top);
    note.position.set(pot.x, above - (CHIP / 2 + pileRise(most) + 4 + SUM.height / 2) * k);
    this.layers.fx.addChild(note);
    slideChips(stack, this.route(pot, this.dealerPoint(), pileReach(stack)), 600).then(() => {
      settle(stack)?.destroy({ children: true });
    });
    wait(1000)
      .then(() => !note.destroyed && tween(note, { alpha: 0 }, 300))
      .then(() => settle(note)?.destroy({ children: true }));
  }

  // One pot slides to its winners. A split pot visibly divides first, so every pot waits the same before it moves.
  // Each winner's chips stop at their bet's spot on the felt and melt into their "Won" words there, never landing on
  // their cards, the player's own or a hand shown over a face
  async pushPot(award, order, count, split) {
    const k = this.plan.k;
    const entries = Object.entries(award.shares).filter(([, amount]) => amount > 0);
    const pot = this.potPoint();
    const startX = pot.x + (order - (count - 1) / 2) * 60 * k;
    const stacks = entries.map(([number, amount]) => {
      const stack = chipPile(amount, this.plan.pot.most);
      stack.scale.set((CHIP / 52) * k);
      stack.position.set(startX, pot.y);
      // Under the cut's "House" label, which stays readable while the piles pass it
      this.layers.fx.addChildAt(stack, 0);
      return { stack, number: Number(number) };
    });
    if (split) {
      // The piles part above the winning cards as those lift
      const apart = (index) => startX + (index - (stacks.length - 1) / 2) * 38 * k;
      const y = (stack) => Math.min(pot.y, this.clearOfCards(pileReach(stack)).top);
      const parts = stacks.map(({ stack }, index) => tween(stack, { x: apart(index), y: y(stack) }, SPLIT_MS - 20));
      await Promise.all(parts);
      if (this.closed) {
        return;
      }
    }
    await Promise.all(
      stacks.map(async ({ stack, number }) => {
        const view = this.seats[number];
        const to = view.winPoint(pileBox(stack));
        const way = this.route({ x: stack.x, y: stack.y }, to, pileReach(stack));
        // Chips stopping just clear of a hand shown over the face slide in flat: their usual hop would land on it
        await slideChips(stack, to.moved ? [...way, to] : way, 520);
        if (!stack.destroyed) {
          // The winner's "Won" words, waiting under the chips, come in as the chips melt away
          const words = view.sum.visible ? tween(view.sum, { alpha: 1 }, 260, ease.out) : null;
          await Promise.all([tween(stack, { alpha: 0, scale: stack.scale.x * 0.8 }, 260, ease.out), words]);
        }
        settle(stack)?.destroy({ children: true });
      }),
    );
  }

  // Where a pile of chips this far across either side of its middle never meets the shared cards, a winning one
  // lifted with its glow included, in table units
  clearOfCards(half) {
    const { board, k } = this.plan;
    return {
      left: board.left - half - 4 * k,
      right: board.right + half + 4 * k,
      top: board.top - (CHIP / 2) * k - BOARD_LIFT - GLOW.board * board.scale,
      bottom: board.bottom + (CHIP / 2) * k,
    };
  }

  // The way chips go from one point to another without crossing the shared cards, as the points after `from`:
  // straight when that misses the cards, else sideways to beside them, along them, and on. The space kept clear
  // includes a winning card lifted with its glow. A point in that space (the pot sits just over the cards) leaves it
  // straight up or down first. half: how far the chips reach either side of their middle
  route(from, to, half) {
    const { board, view } = this.plan;
    const middle = (board.top + board.bottom) / 2;
    const clear = this.clearOfCards(half);
    const out = (point) => {
      const inside = point.x > clear.left && point.x < clear.right && point.y > clear.top && point.y < clear.bottom;
      return inside ? { x: point.x, y: point.y < middle ? clear.top : clear.bottom } : point;
    };
    const start = out(from);
    const end = out(to);
    let way = [end];
    const x = start.x + end.x < board.left + board.right ? clear.left : clear.right;
    // Beside the cards, but not past the rail: with no room there the chips go straight
    if (crosses(start, end, clear) && x > view.left + 20 && x < view.right - 20) {
      way = [{ x, y: start.y }, { x, y: end.y }, end];
    }
    const points = [start, ...way, to];
    return points.filter((point, index) => {
      const before = index ? points[index - 1] : from;
      return point.x !== before.x || point.y !== before.y;
    });
  }

  // A winner's stack counts up, sparkles burst and "+amount" moves beside their plate in a dark label; a big pot bursts
  // three times. Cards over the face (the viewer's own, or a hand shown at the showdown) have the sparkles burst from
  // their sides, flying outward. A shown winner's plate names their hand instead of counting
  async celebrate(number, amount, big) {
    const view = this.seats[number];
    if (!view.data) {
      return;
    }
    this.won[number] = amount;
    const stack = view.data.stack + amount;
    view.counting = true;
    this.drawSeat(number, this.changeSeat(number, { stack, all_in: false }), false);
    const counting = view.showsStack ? view.countTo(stack, 460) : null;
    view.counting = Boolean(counting);
    this.pop(view.sum);
    // The pot is still sliding onto the winner's "Won" words: those wait unseen until it melts (pushPot)
    if (amount > 0) {
      view.sum.alpha = 0;
    }
    const k = this.plan.k;
    const gain = pill(big ? 18 : SUM.font, big ? 28 : SUM.height);
    setPill(gain, `+${money(amount)}`, { fill: GOLD_LIGHT, stroke: GOLD });
    gain.scale.set(k);
    const from = view.gainPoint(gain.span * k);
    gain.position.set(from.x, from.y);
    this.layers.fx.addChild(gain);
    // Over cards lying on a face no coins fall back: their bursts fly outward, away from the cards
    const points = view.sparkPoints(big ? 3 : 1, this.plan.view);
    const burst = (index) => {
      const { x, y, toward, coins } = points[index];
      return this.closed || sparkle(this.layers.fx, x, y, 520, { toward, coins });
    };
    await Promise.all([
      counting,
      tween(gain, { y: from.y + from.rise }, 420, ease.out).then(() => tween(gain, { alpha: 0 }, 180)),
      ...points.map((point, index) => wait(index * 80).then(() => burst(index))),
    ]);
    settle(gain)?.destroy({ children: true });
  }
}
