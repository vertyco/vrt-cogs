// Double or Nothing: one round felt table with a big gold coin in the middle and every player's stack around it.
// Heads doubles every stack still in (the chips rebuild taller with a gold flash); tails sweeps every stack still
// in off to the house. A player who cashes out has their stack slide back to their edge of the table.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { money } from "../format.js";
import { chipStack, coinSprite, flipCoin, loadArt, moveChips, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
// The background is drawn bigger than the scene so a letterbox shows carpet, not black
const BACKGROUND = { x: -148, y: -297, width: 1200, height: 1240 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const INK = 0x1a0f08;
const COIN_AT = { x: 450, y: 205 };
const COIN_SCALE = 1.5;
// This round's flips, a row of small coins under the big one; the newest is on the right
const FLIPS_AT = { x: 450, y: 312 };
const FLIP_SIZE = 0.36;
const FLIP_GAP = 32;
const FLIPS_SHOWN = 12;
// The house's side of the table, where lost chips go
const HOUSE = { x: 450, y: 10 };
// Player spots lie on this ellipse around the coin, at angles in degrees (90 is straight toward the viewer), laid
// out by how many spots there are so they stay balanced. The viewer takes the first, so they sit at the front.
// A cashed-out stack sits further out, at its player's edge
const RING = { x: 450, y: 284, rx: 300, ry: 150 };
const LAYOUTS = [[], [90], [112, 68], [90, 140, 40], [112, 68, 152, 28], [90, 140, 40, 235, 305]];
const MOST = [112, 68, 152, 28, 235, 305];
const EDGE = 1.16;
// Chips are drawn bigger than the kit size so a stack still reads on an upright phone
const CHIP_SCALE = 1.35;
// How far up each chip in a kit stack sits from the one under it
const CHIP_RISE = 5;
const FLIP_MS = 1200;
const STEP_MS = 360;
const COLOR_UP_MS = 150;

function words(text, size, fill, family = MARKS, style = {}) {
  const shadow = { color: 0x000000, alpha: 0.7, blur: 4, distance: 2, angle: Math.PI / 2 };
  const piece = new Text({
    text,
    style: { fontFamily: family, fontWeight: "700", fontSize: size, fill, dropShadow: shadow, ...style },
    resolution: 3,
  });
  piece.anchor.set(0.5);
  return piece;
}

function shortName(name) {
  const text = String(name || "");
  return text.length > 11 ? `${text.slice(0, 10)}…` : text;
}

function slot(index, count) {
  const angle = ((LAYOUTS[count] || MOST)[index] * Math.PI) / 180;
  const dx = Math.cos(angle) * RING.rx;
  const dy = Math.sin(angle) * RING.ry;
  return {
    at: { x: RING.x + dx, y: RING.y + dy },
    edge: { x: RING.x + dx * EDGE, y: RING.y + dy * EDGE },
  };
}

// Everyone with chips on the table, the viewer first: the standing amount and status once the round has them,
// otherwise the bet. A cash-out the viewer already heard about counts even before the table says so
function entries(state, me, cashed) {
  const standing = state.standing || {};
  const list = [];
  for (const player of state.players || []) {
    const row = standing[player.id];
    if (!row && !player.bet) {
      continue;
    }
    const entry = row ? { id: player.id, amount: row.amount, status: row.status } : null;
    const fallback = { id: player.id, amount: player.bet, status: "in" };
    list.push(entry || fallback);
  }
  for (const entry of list) {
    if (cashed.has(entry.id) && entry.status === "in") {
      entry.status = "out";
    }
  }
  return list.sort((a, b) => (b.id === me) - (a.id === me));
}

function statusWords(entry, choosing) {
  if (entry.status === "out") {
    return { text: "Cashed out", fill: GOLD_LIGHT };
  }
  if (entry.status === "lost") {
    return { text: "Lost", fill: CREAM };
  }
  return { text: choosing ? "choosing..." : "", fill: CREAM };
}

function setStack(spot, amount) {
  spot.stack?.destroy({ children: true });
  spot.stack = chipStack(amount);
  spot.stack.scale.set(CHIP_SCALE);
  spot.chips.addChild(spot.stack);
  spot.amount.text = amount > 0 ? money(amount) : "";
}

function setStatus(spot, status, choosing = false) {
  spot.entry.status = status;
  const { text, fill } = statusWords(spot.entry, choosing);
  spot.status.text = text;
  spot.status.style.fill = fill;
}

// One player's place: a gold ring under the viewer's chips, the stack, its number, the name and what they're doing
function makeSpot(entry, place, mine, name, choosing) {
  const spot = new Container();
  spot.entry = { ...entry };
  spot.place = place;
  const where = entry.status === "out" ? place.edge : place.at;
  spot.position.set(where.x, where.y);
  spot.glow = new Graphics();
  for (let ring = 0; ring < 10; ring += 1) {
    spot.glow.ellipse(0, 6, 40 + ring * 3.4, 18 + ring * 1.8).fill({ color: GOLD_LIGHT, alpha: 0.12 });
  }
  spot.glow.alpha = 0;
  spot.addChild(spot.glow);
  if (mine) {
    spot.addChild(new Graphics().ellipse(0, 10, 48, 21).stroke({ width: 3, color: GOLD_LIGHT }));
  }
  spot.chips = new Container();
  spot.amount = words("", 23, mine ? GOLD_LIGHT : CREAM);
  spot.amount.y = 46;
  const tag = words(shortName(name), 19, mine ? GOLD_LIGHT : CREAM);
  const pill = new Graphics()
    .roundRect(-tag.width / 2 - 10, -15, tag.width + 20, 30, 15)
    .fill({ color: INK, alpha: 0.7 })
    .stroke({ width: 2, color: mine ? GOLD_LIGHT : GOLD, alpha: mine ? 1 : 0.5 });
  pill.y = tag.y = 76;
  spot.status = words("", 20, CREAM, FONT, { fontStyle: "italic" });
  spot.status.y = 106;
  spot.addChild(spot.chips, spot.amount, pill, tag, spot.status);
  setStack(spot, entry.status === "lost" ? 0 : entry.amount);
  setStatus(spot, entry.status, choosing);
  spot.alpha = entry.status === "lost" ? 0.45 : 1;
  return spot;
}

function moreSpot(count, place) {
  const spot = new Container();
  spot.position.set(place.at.x, place.at.y);
  spot.addChild(new Graphics().circle(0, 0, 30).fill({ color: INK, alpha: 0.6 }).stroke({ width: 3, color: GOLD }));
  spot.addChild(words(`+${count}`, 24, CREAM));
  return spot;
}

function flipPiece(side) {
  const piece = coinSprite(side);
  piece.scale.set(FLIP_SIZE);
  return piece;
}

// Lines the row of flips up around its center, dropping the oldest past FLIPS_SHOWN
function arrangeFlips(row) {
  while (row.children.length > FLIPS_SHOWN) {
    row.children[0].destroy({ children: true });
  }
  const count = row.children.length;
  row.children.forEach((piece, index) => {
    piece.x = (index - (count - 1) / 2) * FLIP_GAP;
  });
}

async function loadBackground() {
  const texture = await Assets.load(new URL("../art/double/table.jpg", import.meta.url).href);
  const back = new Sprite(texture);
  back.position.set(BACKGROUND.x, BACKGROUND.y);
  back.width = BACKGROUND.width;
  back.height = BACKGROUND.height;
  return back;
}

export async function createScene(stage) {
  await loadArt();
  const root = fitted(WIDTH, HEIGHT);
  const shadow = new Graphics().ellipse(0, 0, 56, 17).fill({ color: 0x000000, alpha: 0.35 });
  shadow.position.set(COIN_AT.x, COIN_AT.y + 62);
  const flips = new Container();
  flips.position.set(FLIPS_AT.x, FLIPS_AT.y);
  const parts = { root, shadow, flips, spots: new Container(), effects: new Container(), coin: null };
  root.addChild(await loadBackground(), shadow, flips, parts.spots);
  placeCoin(parts, "heads");
  root.addChild(parts.effects);
  stage.root.addChild(root);
  return sceneApi(stage, parts);
}

function placeCoin(parts, side) {
  if (parts.coin && parts.coin.side === side) {
    return;
  }
  parts.coin?.destroy({ children: true });
  parts.coin = coinSprite(side);
  parts.coin.scale.set(COIN_SCALE);
  parts.coin.position.set(COIN_AT.x, COIN_AT.y);
  parts.root.addChildAt(parts.coin, parts.root.getChildIndex(parts.flips));
}

function showFlips(parts, sides) {
  parts.flips.removeChildren().forEach((child) => child.destroy({ children: true }));
  sides.slice(-FLIPS_SHOWN).forEach((side) => parts.flips.addChild(flipPiece(side)));
  arrangeFlips(parts.flips);
}

// Draws every spot as the entries say; returns the drawn spots
function drawSpots(stage, parts, list, waiting) {
  parts.spots.removeChildren().forEach((child) => child.destroy({ children: true }));
  const me = stage.me();
  const count = Math.min(list.length, MOST.length);
  const folded = list.length > MOST.length;
  const shown = folded ? list.slice(0, MOST.length - 1) : list;
  const drawn = shown.map((entry, index) => {
    const place = slot(index, count);
    const spot = makeSpot(entry, place, entry.id === me, stage.nameOf(entry.id), waiting.has(entry.id));
    parts.spots.addChild(spot);
    return spot;
  });
  if (folded) {
    parts.spots.addChild(moreSpot(list.length - shown.length, slot(MOST.length - 1, count)));
  }
  return drawn;
}

// Heads: a second copy of the stack drops onto the first out of a gold flash, then the dealer colors the pile up
// into the fewest chips, the way chipStack always draws an amount
async function doubleUp(spot, effects) {
  const old = spot.stack;
  const copy = chipStack(spot.entry.amount);
  copy.scale.set(CHIP_SCALE);
  const top = -Math.min(12, old.children.length) * CHIP_RISE * CHIP_SCALE;
  copy.position.set(0, top - 46);
  copy.alpha = 0;
  spot.chips.addChild(copy);
  spot.glow.alpha = 1;
  sparkle(effects, spot.x, spot.y - 30, STEP_MS + COLOR_UP_MS);
  await Promise.all([
    tween(copy, { y: top, alpha: 1 }, STEP_MS, ease.out),
    tween(spot.glow, { alpha: 0 }, STEP_MS, ease.inOut),
  ]);
  if (spot.destroyed) {
    return;
  }
  spot.entry.amount *= 2;
  spot.stack = null;
  setStack(spot, spot.entry.amount);
  spot.stack.alpha = 0;
  await Promise.all([
    tween(spot.stack, { alpha: 1 }, COLOR_UP_MS),
    tween(old, { alpha: 0 }, COLOR_UP_MS),
    tween(copy, { alpha: 0 }, COLOR_UP_MS),
  ]);
  old.destroy({ children: true });
  copy.destroy({ children: true });
}

// Tails, or a loss found at the results: the chips slide to the house and fade, and the spot dims
async function sweep(spot) {
  const target = { x: HOUSE.x - spot.x, y: HOUSE.y - spot.y };
  setStatus(spot, "lost");
  spot.amount.text = "";
  await Promise.all([
    moveChips(spot.chips, target, STEP_MS),
    tween(spot.chips, { alpha: 0 }, STEP_MS, ease.inOut),
    tween(spot, { alpha: 0.45 }, STEP_MS, ease.inOut),
  ]);
}

// A cash-out: the stack slides back to its player's edge with a little sparkle
async function cashOut(spot, effects) {
  setStatus(spot, "out");
  const { edge } = spot.place;
  sparkle(effects, edge.x, edge.y - 30, STEP_MS + 200);
  await tween(spot, { x: edge.x, y: edge.y }, STEP_MS, ease.inOut);
}

function sceneApi(stage, parts) {
  const cashed = new Set();
  let spots = [];
  let seen = null;
  let flourished = null;

  // R4: the results moment animates only on the change into results for a round this scene already saw
  function flourish(before) {
    for (const spot of spots) {
      const was = before[spot.entry.id];
      if (!was || was.status !== "in") {
        continue;
      }
      const now = spot.entry.status;
      if (now === "out") {
        spot.position.set(spot.place.at.x, spot.place.at.y);
        cashOut(spot, parts.effects);
      } else if (now === "lost") {
        spot.alpha = 1;
        setStack(spot, was.amount);
        sweep(spot);
      }
    }
  }

  function show(state) {
    if (!seen || seen.round !== state.round || state.phase === "idle") {
      cashed.clear();
    }
    const sides = state.flips || [];
    placeCoin(parts, sides.length ? sides[sides.length - 1] : parts.coin.side);
    showFlips(parts, sides);
    const before = Object.fromEntries(spots.map((spot) => [spot.entry.id, { ...spot.entry }]));
    spots = drawSpots(stage, parts, entries(state, stage.me(), cashed), new Set(state.waiting || []));
    const fresh = state.phase === "results" && seen && seen.round === state.round && seen.phase !== "results";
    if (fresh && flourished !== state.round) {
      flourish(before);
    }
    if (state.phase === "results") {
      flourished = state.round;
    }
    seen = { round: state.round, phase: state.phase };
  }

  async function play(event) {
    if (event.kind !== "flip") {
      return;
    }
    // A flip means everyone's choice is in, so nobody is still choosing
    spots.forEach((spot) => setStatus(spot, spot.entry.status));
    stage.sound.play("coin");
    const air = (k) => (k < 0.82 ? Math.sin((k / 0.82) * Math.PI) : 0);
    await Promise.all([tween(parts.shadow, { scale: 0.5 }, FLIP_MS, air), flipCoin(parts.coin, event.side, FLIP_MS)]);
    parts.shadow.scale.set(1);
    stage.sound.play("land");
    const landed = flipPiece(event.side);
    parts.flips.addChild(landed);
    arrangeFlips(parts.flips);
    const still = spots.filter((spot) => spot.entry.status === "in");
    if (event.side === "heads") {
      stage.sound.play("chip");
      await Promise.all(still.map((spot) => doubleUp(spot, parts.effects)));
    } else {
      stage.sound.play("collect");
      await Promise.all(still.map((spot) => sweep(spot)));
    }
  }

  // The viewer's own cash-out is heard here before the table says so; their stack goes back to them at once
  function result(message) {
    const me = stage.me();
    const spot = spots.find((piece) => piece.entry.id === me);
    if (message.outcome !== "win" || !spot || spot.entry.status !== "in") {
      return;
    }
    cashed.add(me);
    cashOut(spot, parts.effects);
  }

  return {
    show,
    play,
    result,
    layout(width, height) {
      fit(parts.root, width, height);
    },
    destroy() {},
  };
}
