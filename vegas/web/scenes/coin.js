// Coin: a small round felt table with a HEADS spot and a TAILS spot. Each player's bet sits as a chip stack on the
// spot they called, and one big gold coin rests between them. A flip tosses the coin; at the results the winning spot
// glows, its stacks grow to what they paid with a sparkle, and the other spot's chips slide off to the house.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { CHOICES } from "../tray.js";
import { chipStack, coinSprite, flipCoin, loadArt, moveChips, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
const FONT = '"Playfair Display", Georgia, serif';
const NAMES = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const CREAM = 0xf6ecd2;
const FELT_LIGHT = 0x13643a;
const INK = 0x1a0f08;
// Where things sit in the scene's 900 x 600 space. The spots are ellipses, flattened like the table they lie on
const COIN_AT = { x: 450, y: 244 };
const COIN_SCALE = 1.35;
const SPOTS = {
  heads: { x: 228, y: 268 },
  tails: { x: 672, y: 268 },
};
const SPOT = { rx: 146, ry: 98 };
// The house's side of the table, where lost chips go
const HOUSE = { x: 450, y: 50 };
// Stacks shown on one spot; anyone past that is counted in a "+N"
const PER_SPOT = 3;
const STACK_GAP = 88;
const FLIP_MS = 1600;
const LABELS = Object.fromEntries(CHOICES.coin.map(([value, label]) => [value, label.toUpperCase()]));

function text(value, style) {
  const piece = new Text({ text: value, style, resolution: 2 });
  piece.anchor.set(0.5);
  return piece;
}

function shortName(name) {
  const value = String(name || "");
  return value.length > 10 ? `${value.slice(0, 9)}…` : value;
}

// One betting spot: a gold-rimmed circle on the felt with its word, which picks that call in the tray when tapped
function makeSpot(side, stage) {
  const { x, y } = SPOTS[side];
  const spot = new Container();
  spot.position.set(x, y);
  // A soft halo from rings that fade outward (a blur filter would cut its edges square)
  const glow = new Graphics().ellipse(0, 0, SPOT.rx, SPOT.ry).fill({ color: GOLD_LIGHT, alpha: 0.2 });
  for (let ring = 0; ring < 14; ring += 1) {
    const fade = (1 - ring / 14) ** 2;
    glow
      .ellipse(0, 0, SPOT.rx + ring * 2.5, SPOT.ry + ring * 2)
      .stroke({ width: 3, color: GOLD_LIGHT, alpha: 0.5 * fade });
  }
  glow.alpha = 0;
  const ring = new Graphics()
    .ellipse(0, 0, SPOT.rx, SPOT.ry)
    .fill({ color: FELT_LIGHT, alpha: 0.45 })
    .stroke({ width: 4, color: GOLD })
    .ellipse(0, 0, SPOT.rx - 9, SPOT.ry - 8)
    .stroke({ width: 1.5, color: GOLD, alpha: 0.6 });
  const label = text(LABELS[side], {
    fontFamily: FONT,
    fontWeight: "700",
    fontSize: 30,
    fill: GOLD_LIGHT,
    letterSpacing: 4,
    stroke: { color: INK, width: 3 },
  });
  label.y = -SPOT.ry + 34;
  const pile = new Container();
  spot.addChild(glow, ring, label, pile);
  spot.glow = glow;
  spot.pile = pile;
  spot.eventMode = "static";
  spot.cursor = "pointer";
  spot.on("pointertap", () => stage.actions.choose(side));
  return spot;
}

function nameTag(name, mine) {
  return text(shortName(name), {
    fontFamily: NAMES,
    fontWeight: "600",
    fontSize: 14,
    fill: mine ? GOLD_LIGHT : CREAM,
    stroke: { color: INK, width: 4 },
  });
}

// One player's bet on a spot: their chips, their name under them, and a gold ring if it's the viewer's
function betPiece(player, amount, mine, name) {
  const piece = new Container();
  const chips = new Container();
  if (mine) {
    chips.addChild(new Graphics().circle(0, 0, 34).stroke({ width: 3, color: GOLD_LIGHT }));
  }
  const stack = chipStack(amount);
  chips.addChild(stack);
  piece.addChild(chips);
  const tag = nameTag(name, mine);
  tag.y = 44;
  piece.addChild(tag);
  piece.stack = stack;
  piece.player = player;
  piece.alpha = player.away ? 0.55 : 1;
  return piece;
}

// The viewer first, then the biggest bets
function ordered(players, me) {
  return [...players].sort((a, b) => (b.id === me) - (a.id === me) || b.bet - a.bet);
}

export async function createScene(stage) {
  await loadArt();
  const background = await Assets.load(new URL("../art/coin/table.jpg", import.meta.url).href);
  const root = fitted(WIDTH, HEIGHT);
  const table = new Sprite(background);
  table.anchor.set(0.5);
  table.position.set(WIDTH / 2, HEIGHT / 2);
  table.width = 1200;
  table.height = 1240;
  const spots = { heads: makeSpot("heads", stage), tails: makeSpot("tails", stage) };
  const shadow = new Graphics().ellipse(0, 0, 50, 16).fill({ color: 0x000000, alpha: 0.35 });
  shadow.position.set(COIN_AT.x, COIN_AT.y + 52);
  const effects = new Container();
  let coin = null;
  let lastSide = "heads";
  let lastPhase = null;
  let flourished = null;
  // While the coin is in the air, a table update must not swap the sprite out from under flipCoin
  let flipping = false;
  root.addChild(table, spots.heads, spots.tails, shadow, effects);
  stage.root.addChild(root);
  placeCoin(lastSide);

  function placeCoin(side) {
    if (flipping || (coin && coin.side === side)) {
      return;
    }
    coin?.destroy({ children: true });
    coin = coinSprite(side);
    coin.scale.set(COIN_SCALE);
    coin.position.set(COIN_AT.x, COIN_AT.y);
    root.addChild(coin);
  }

  // What a player's stack shows: the bet, or for a win at the results what it paid
  function amountFor(player, results) {
    if (!results || player.outcome !== "win") {
      return player.bet;
    }
    return player.payout || player.bet;
  }

  function fillSpot(side, players, results) {
    const spot = spots[side];
    spot.pile.removeChildren().forEach((child) => child.destroy({ children: true }));
    const me = stage.me();
    const shown = ordered(players, me).slice(0, PER_SPOT);
    const pieces = shown.map((player, index) => {
      const amount = amountFor(player, results);
      const piece = betPiece(player, amount, player.id === me, stage.nameOf(player.id));
      piece.position.set((index - (shown.length - 1) / 2) * STACK_GAP, 22);
      spot.pile.addChild(piece);
      return piece;
    });
    const more = players.length - shown.length;
    if (more > 0) {
      const tag = text(`+${more}`, { fontFamily: NAMES, fontWeight: "700", fontSize: 16, fill: GOLD_LIGHT });
      tag.position.set(0, SPOT.ry - 14);
      spot.pile.addChild(tag);
    }
    return pieces;
  }

  // The results moment: the winning spot glows, winners' stacks grow with a sparkle, losers' chips go to the house
// and their name fades with them
  async function flourish(pieces, side) {
    tween(spots[side].glow, { alpha: 1 }, 400);
    const jobs = [];
    for (const piece of pieces) {
      // Where the piece sits in the scene: its spot's place plus its place on the spot
      const x = spots[piece.player.choice].x + piece.x;
      const y = spots[piece.player.choice].y + piece.y;
      if (piece.player.outcome === "lose") {
        const target = { x: HOUSE.x - x, y: HOUSE.y - y };
        jobs.push(moveChips(piece.stack, target, 700), tween(piece, { alpha: 0 }, 700, ease.inOut));
      } else if (piece.player.outcome === "win") {
        piece.stack.scale.set(0.6);
        jobs.push(tween(piece.stack, { scale: 1 }, 450, ease.back), sparkle(effects, x, y - 20, 800));
      }
    }
    await Promise.all(jobs);
  }

  function show(state) {
    const results = state.phase === "results" && state.drawn;
    if (state.drawn?.side) {
      lastSide = state.drawn.side;
    }
    placeCoin(lastSide);
    const players = (state.players || []).filter((player) => player.bet);
    const pieces = [];
    for (const side of ["heads", "tails"]) {
      pieces.push(...fillSpot(side, players.filter((player) => player.choice === side), results));
      spots[side].glow.alpha = results && state.drawn.side === side ? 1 : 0;
    }
    const fresh = results && lastPhase !== null && lastPhase !== "results" && flourished !== state.round;
    if (results) {
      if (fresh) {
        spots[state.drawn.side].glow.alpha = 0;
        flourish(pieces, state.drawn.side);
      } else {
        pieces.filter((piece) => piece.player.outcome === "lose").forEach((piece) => (piece.alpha = 0));
      }
      flourished = state.round;
    }
    lastPhase = state.phase;
  }

  async function play(event) {
    if (event.kind !== "flip") {
      return;
    }
    stage.sound.play("coin");
    flipping = true;
    // The shadow shrinks while the coin is up, the same arc flipCoin flies (in the air for the first 82 percent)
    const air = (k) => (k < 0.82 ? Math.sin((k / 0.82) * Math.PI) : 0);
    try {
      await Promise.all([tween(shadow, { scale: 0.5 }, FLIP_MS, air), flipCoin(coin, event.side, FLIP_MS)]);
    } finally {
      flipping = false;
    }
    shadow.scale.set(1);
    lastSide = event.side;
    stage.sound.play("land");
  }

  return {
    show,
    play,
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {},
  };
}
