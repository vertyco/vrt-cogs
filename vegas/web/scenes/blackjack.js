// Blackjack: a half-moon table with five seats along its curve and the dealer at the straight edge. The shoe sits on
// the dealer's right; cards fly from it to each seat and to the dealer, whose second card stays face down until the
// players have acted. The seat whose turn it is glows; results grow the winners' chips and dim the losers.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { CARD, cardSprite, chipStack, dealCard, flipCard, loadArt, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
// The background is drawn bigger than the scene so a letterbox shows more table, not black
const BACKGROUND = { x: -270, y: -180, width: 1440, height: 960 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const INK = 0x1a0f08;
const RED = 0xc8202f;
// Each seat's betting circle, left to right from the players' side (measured from art/blackjack/table.jpg)
const SEATS = [
  { x: 112, y: 299 },
  { x: 277, y: 366 },
  { x: 450, y: 403 },
  { x: 623, y: 366 },
  { x: 788, y: 299 },
];
const SPOT_RADIUS = 47;
// A seat's cards sit this far above its circle, toward the dealer
const CARDS_ABOVE = 100;
const SEAT_CARDS = { scale: 0.72, step: 26 };
// The dealer's cards sit just below the chip tray, which ends at y 89
const DEALER = { x: 450, y: 150, scale: 0.72, step: 34 };
const SHOE = { x: 95, y: 46, width: 170 };
// Where a dealt card leaves the shoe's mouth
const MOUTH = { x: 168, y: 50 };
const CHIP_SCALE = 0.92;
const NAME_BELOW = 70;
const DEAL_MS = 290;
const TURN_MS = 90;
const REVEAL_MS = 450;
const WIN_GROWTH = 1.15;
const PHASES_IN_PLAY = new Set(["playing", "results"]);
const DECK = 52;

function words(text, size, fill, family = MARKS) {
  const shadow = { color: 0x000000, alpha: 0.7, blur: 4, distance: 2, angle: Math.PI / 2 };
  const piece = new Text({
    text,
    style: { fontFamily: family, fontWeight: "700", fontSize: size, fill, dropShadow: shadow },
    resolution: 3,
  });
  piece.anchor.set(0.5);
  return piece;
}

// Words on a dark rounded pill, so they read on felt and on top of cards
function pill(text, size, fill, stroke, family = MARKS) {
  const piece = new Container();
  const label = words(text, size, fill, family);
  const height = size + 14;
  const back = new Graphics()
    .roundRect(-label.width / 2 - 12, -height / 2, label.width + 24, height, height / 2)
    .fill({ color: INK, alpha: 0.72 })
    .stroke({ width: 2, color: stroke });
  piece.addChild(back, label);
  return piece;
}

function shortName(name) {
  const text = String(name || "");
  return text.length > 12 ? `${text.slice(0, 11)}…` : text;
}

function cardValue(card) {
  const rank = card[0];
  return rank === "A" ? 1 : ["J", "Q", "K"].includes(rank) ? 10 : Number(rank);
}

// A hand's total the way the bot counts it: one Ace counts 11 when that keeps the total at 21 or less
function handTotal(cards) {
  const shown = cards.filter(Boolean);
  let total = shown.reduce((sum, card) => sum + cardValue(card), 0);
  if (shown.some((card) => card[0] === "A") && total <= 11) {
    total += 10;
  }
  return total;
}

// ---- Hands: a fan of cards and a total badge ----

function makeHand(layer, anchor, size, badgeAt) {
  const hand = { layer, anchor, size, badgeAt, pieces: [], cards: [], doubled: false, status: "" };
  hand.badge = new Container();
  layer.addChild(hand.badge);
  return hand;
}

// Where card index sits in a fan of count cards; a doubled hand's third card lies sideways
function slot(hand, index, count) {
  const { anchor, size } = hand;
  const sideways = hand.doubled && index === 2;
  return {
    x: anchor.x + (index - (count - 1) / 2) * size.step + (sideways ? size.step * 0.6 : 0),
    y: anchor.y - index * 4 + (sideways ? 6 : 0),
    rotation: sideways ? Math.PI / 2 : (index - (count - 1) / 2) * 0.035,
  };
}

function placeCards(hand) {
  hand.pieces.forEach((piece, index) => {
    const spot = slot(hand, index, hand.pieces.length);
    piece.position.set(spot.x, spot.y);
    piece.rotation = spot.rotation;
  });
}

function addPiece(hand, card) {
  const piece = cardSprite(card);
  piece.scale.set(hand.size.scale);
  hand.layer.addChildAt(piece, hand.layer.getChildIndex(hand.badge));
  hand.pieces.push(piece);
  hand.cards.push(card);
  return piece;
}

function badgeLook(hand) {
  if (hand.status === "blackjack") {
    return { text: "BLACKJACK", fill: GOLD_LIGHT, stroke: GOLD_LIGHT, family: FONT };
  }
  const total = handTotal(hand.cards);
  if (hand.status === "bust" || total > 21) {
    return { text: "BUST", fill: 0xff6b6b, stroke: RED, family: FONT };
  }
  return { text: String(total), fill: CREAM, stroke: GOLD, family: MARKS };
}

function drawBadge(hand) {
  hand.badge.removeChildren().forEach((child) => child.destroy({ children: true }));
  if (!hand.cards.some(Boolean)) {
    return;
  }
  const look = badgeLook(hand);
  hand.badge.addChild(pill(look.text, 24, look.fill, look.stroke, look.family));
  const spot = hand.badgeAt(hand.pieces.length);
  hand.badge.position.set(spot.x, spot.y);
}

function fillHand(hand, cards, doubled, status) {
  hand.doubled = Boolean(doubled);
  hand.status = status || "";
  for (const card of cards || []) {
    addPiece(hand, card);
  }
  placeCards(hand);
  drawBadge(hand);
}

// ---- Seats ----

function seatHand(layer, index) {
  const seat = SEATS[index];
  const anchor = { x: seat.x, y: seat.y - CARDS_ABOVE };
  // The total sits over the bottom of the cards: above them is the dealer's area, below them the chips
  const bottom = (CARD.height * SEAT_CARDS.scale) / 2;
  return makeHand(layer, anchor, SEAT_CARDS, () => ({ x: anchor.x, y: anchor.y + bottom - 12 }));
}

function dealerHand(layer) {
  const half = (CARD.width * DEALER.scale) / 2;
  return makeHand(layer, DEALER, DEALER, (count) => ({
    x: DEALER.x + ((count - 1) / 2) * DEALER.step + half + 48,
    y: DEALER.y,
  }));
}

function spotRing(seat, color, alpha, width) {
  return new Graphics()
    .circle(seat.x, seat.y, SPOT_RADIUS)
    .fill({ color, alpha: alpha * 0.25 })
    .stroke({ width, color, alpha });
}

function emptySeat(group, seat, canSit) {
  if (!canSit) {
    return;
  }
  group.addChild(spotRing(seat, GOLD_LIGHT, 0.55, 4));
  const label = words("Sit", 26, GOLD_LIGHT, FONT);
  label.position.set(seat.x, seat.y);
  group.addChild(label);
}

function turnGlow(seat) {
  const glow = new Container();
  glow.addChild(
    new Graphics().circle(seat.x, seat.y, SPOT_RADIUS + 12).stroke({ width: 14, color: GOLD_LIGHT, alpha: 0.25 }),
    spotRing(seat, GOLD_LIGHT, 1, 5),
  );
  return glow;
}

function chips(group, seat, amount, doubled) {
  // A doubled hand's bet is both stakes, shown as two stacks side by side
  const offsets = doubled ? [-24, 24] : [0];
  const stacks = offsets.map(() => chipStack(Math.round(amount / offsets.length)));
  stacks.forEach((stack, index) => {
    stack.scale.set(CHIP_SCALE);
    stack.position.set(seat.x + offsets[index], seat.y + 12);
    group.addChild(stack);
  });
  return stacks;
}

function nameTag(seat, name, isMe) {
  const tag = pill(shortName(name), 20, isMe ? GOLD_LIGHT : CREAM, isMe ? GOLD_LIGHT : GOLD);
  tag.position.set(seat.x, seat.y + NAME_BELOW);
  return tag;
}

// A note under a seat's name: "Your turn", a win, or PUSH
function seatNote(seat, text, fill, family = FONT) {
  const note = pill(text, 22, fill, fill, family);
  note.position.set(seat.x, seat.y + NAME_BELOW + 40);
  return note;
}

function tapArea(seat, onTap) {
  const hit = new Graphics().circle(seat.x, seat.y, SPOT_RADIUS + 14).fill({ color: 0x000000, alpha: 0.001 });
  hit.eventMode = "static";
  hit.cursor = "pointer";
  hit.on("pointertap", onTap);
  return hit;
}

function takenSeat(group, index, ctx) {
  const { state, me, nameOf } = ctx;
  const taker = state.seats[index];
  const seat = SEATS[index];
  const row = (state.players || []).find((player) => player.id === taker.id);
  const hand = (state.hands || {})[taker.id];
  const isMe = taker.id === me;
  const view = { id: taker.id, group, seat, row, outcome: row && row.outcome, stacks: [] };
  if (state.turn === taker.id && state.phase === "playing") {
    group.addChild(turnGlow(seat));
    if (isMe) {
      group.addChild(seatNote(seat, "Your turn", GOLD_LIGHT));
    }
  }
  if (row && row.bet) {
    const won = row.outcome === "win" && row.payout;
    view.stacks = chips(group, seat, won ? row.payout : row.bet, hand && hand.doubled);
  }
  group.addChild(nameTag(seat, nameOf(taker.id) || taker.name, isMe));
  view.hand = seatHand(group, index);
  if (hand) {
    fillHand(view.hand, hand.cards, hand.doubled, hand.status);
  }
  return view;
}

// ---- Results ----

function resultNote(view) {
  if (view.outcome === "win" && view.row.payout) {
    return seatNote(view.seat, `+${Number(view.row.payout).toLocaleString("en-US")}`, GOLD_LIGHT, MARKS);
  }
  if (view.outcome === "push") {
    return seatNote(view.seat, "PUSH", CREAM);
  }
  return null;
}

function settle(view) {
  const note = resultNote(view);
  if (note) {
    view.group.addChild(note);
  }
  if (view.outcome === "win") {
    view.group.addChildAt(turnGlow(view.seat), 0);
    view.stacks.forEach((stack) => stack.scale.set(CHIP_SCALE * WIN_GROWTH));
  } else if (view.outcome === "lose" || view.outcome === "bust") {
    view.group.alpha = 0.45;
  }
}

function flourish(view, effects) {
  settle(view);
  if (view.outcome === "win") {
    view.stacks.forEach((stack) => {
      stack.scale.set(CHIP_SCALE * 0.6);
      tween(stack, { scale: CHIP_SCALE * WIN_GROWTH }, 650, ease.back);
    });
    sparkle(effects, view.seat.x, view.seat.y - 20, 900);
  } else if (view.outcome === "lose" || view.outcome === "bust") {
    view.group.alpha = 1;
    tween(view.group, { alpha: 0.45 }, 600);
  }
}

// ---- The scene ----

async function loadPicture(name) {
  return Assets.load(new URL(`../art/blackjack/${name}`, import.meta.url).href);
}

async function makeTable() {
  const [table, shoe] = await Promise.all([loadPicture("table.jpg"), loadPicture("shoe.png")]);
  const back = new Sprite(table);
  back.position.set(BACKGROUND.x, BACKGROUND.y);
  back.width = BACKGROUND.width;
  back.height = BACKGROUND.height;
  const box = new Sprite(shoe);
  box.anchor.set(0.5);
  box.scale.set(SHOE.width / box.texture.width);
  box.position.set(SHOE.x, SHOE.y);
  return { back, box };
}

export async function createScene(stage) {
  await loadArt();
  const root = fitted(WIDTH, HEIGHT);
  const { back, box } = await makeTable();
  const left = words("", 17, CREAM, FONT);
  left.anchor.set(0, 0.5);
  left.position.set(SHOE.x - SHOE.width / 2 + 4, SHOE.y + 48);
  const parts = { seats: new Container(), dealer: new Container(), effects: new Container(), left };
  root.addChild(back, parts.seats, box, left, parts.dealer, parts.effects);
  stage.root.addChild(root);
  return sceneApi(stage, root, parts);
}

function drawSeats(stage, parts, state) {
  parts.seats.removeChildren().forEach((child) => child.destroy({ children: true }));
  const me = stage.me();
  const seats = state.seats || [];
  const seated = seats.some((taker) => taker && taker.id === me);
  const between = !PHASES_IN_PLAY.has(state.phase);
  const ctx = { state, me, nameOf: stage.nameOf };
  const views = [];
  SEATS.forEach((seat, index) => {
    const group = new Container();
    parts.seats.addChild(group);
    const taker = seats[index];
    if (!taker) {
      emptySeat(group, seat, !seated);
      group.addChild(tapArea(seat, () => !seated && sit(stage, index)));
      return;
    }
    views.push(takenSeat(group, index, ctx));
    if (taker.id === me) {
      group.addChild(tapArea(seat, () => between && stand(stage)));
    }
  });
  return views;
}

function sit(stage, index) {
  stage.sound.play("click");
  stage.actions.sit(index);
}

function stand(stage) {
  stage.sound.play("click");
  stage.actions.stand();
}

function drawDealer(parts, state) {
  parts.dealer.removeChildren().forEach((child) => child.destroy({ children: true }));
  const hand = dealerHand(parts.dealer);
  fillHand(hand, state.dealer ? state.dealer.cards : [], false, "");
  return hand;
}

function sceneApi(stage, root, parts) {
  let seen = null;
  let flourished = null;
  // The hands on the table by player id ("dealer" for the dealer), so a deal adds to the right one
  let hands = {};
  // Cards left in the shoe, counted down per deal (the bot only sends the count between deals), and how many hands
  // the opening deal serves
  let shoe = 0;
  let bettors = 0;
  const countDeal = () => {
    // The bot refills a shoe too short for the opening deal just before its first card
    if (Object.values(hands).every((hand) => !hand.pieces.length) && shoe < 2 * (bettors + 1)) {
      shoe = DECK;
    }
    // A shoe that runs out mid-round is refilled before its next card, like the bot's deck
    if (shoe <= 0) {
      shoe = DECK;
    }
    shoe -= 1;
    parts.left.text = `Cards in shoe: ${shoe}`;
  };
  return {
    show(state) {
      const views = drawSeats(stage, parts, state);
      hands = { dealer: drawDealer(parts, state) };
      views.forEach((view) => {
        hands[view.id] = view.hand;
      });
      // An empty shoe is refilled before the next deal, so it shows as the full deck it is about to be
      shoe = state.deck || DECK;
      bettors = views.filter((view) => view.row && view.row.bet).length;
      parts.left.text = `Cards in shoe: ${shoe}`;
      const fresh = state.phase === "results" && seen && seen.round === state.round && seen.phase !== "results";
      const animate = fresh && flourished !== state.round;
      if (state.phase === "results") {
        views.filter((view) => view.row).forEach((view) => (animate ? flourish(view, parts.effects) : settle(view)));
      }
      if (animate) {
        flourished = state.round;
      }
      seen = { round: state.round, phase: state.phase };
    },
    async play(event) {
      if (event.kind === "deal") {
        countDeal();
        await deal(stage, hands[event.to], event.card);
      } else if (event.kind === "reveal") {
        await reveal(stage, hands.dealer, event.card);
      }
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {},
  };
}

async function deal(stage, hand, card) {
  if (!hand) {
    return;
  }
  stage.sound.play("deal");
  const piece = addPiece(hand, null);
  const count = hand.pieces.length;
  const target = slot(hand, count - 1, count);
  // The cards already there shift over to keep the fan centered while the new one flies in
  hand.pieces.slice(0, -1).forEach((other, index) => {
    const spot = slot(hand, index, count);
    tween(other, { x: spot.x, y: spot.y, rotation: spot.rotation }, DEAL_MS);
  });
  hand.badge.visible = false;
  await dealCard(piece, MOUTH, target, DEAL_MS);
  if (piece.destroyed) {
    return;
  }
  piece.rotation = target.rotation;
  if (card) {
    hand.cards[count - 1] = card;
    await flipCard(piece, card, TURN_MS);
    if (piece.destroyed) {
      return;
    }
  }
  drawBadge(hand);
  hand.badge.visible = true;
}

async function reveal(stage, hand, card) {
  const piece = hand && hand.pieces[1];
  if (!piece || !card) {
    return;
  }
  stage.sound.play("slide");
  await flipCard(piece, card, REVEAL_MS);
  hand.cards[1] = card;
  if (!piece.destroyed) {
    drawBadge(hand);
  }
}
