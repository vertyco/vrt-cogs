// Casino War: a half-moon table with the dealer's card box at the top and up to six player spots around the curved
// edge. One card from the shoe to each player and one to the dealer; the higher card wins. A tie waits on the
// player's choice, and going to war burns three cards into the discard tray and deals each side a second card.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { cardSprite, chipStack, dealCard, flipCard, loadArt, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
// The background is drawn bigger than the scene so a letterbox shows more table, not black
const BACKGROUND = { x: -150, y: -250, width: 1200, height: 1100 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const BURGUNDY = 0x6b0f1a;
const INK = 0x1a0f08;
// The card boxes printed on the felt, in scene space (measured from art/war/table.jpg), left to right
const SLOTS = [
  { x: 91, y: 250 },
  { x: 227, y: 325 },
  { x: 371, y: 373 },
  { x: 529, y: 373 },
  { x: 672, y: 325 },
  { x: 808, y: 250 },
];
// From a card box's center: its betting circle and the player's name; and the printed box's and circle's size
const CIRCLE_DY = 107;
const CIRCLE_RADIUS = 36;
const NAME_DY = 162;
const BOX = { width: 86, height: 118 };
const DEALER = { x: 450, y: 123, scale: 0.78 };
const SHOE = { x: 745, y: 92, width: 176 };
const DISCARD = { x: 160, y: 92, width: 104 };
// Where cards leave the shoe: the card showing in its open mouth on the left end
const MOUTH = { x: SHOE.x - 52, y: SHOE.y };
const CARD_SCALE = 0.62;
const DISCARD_SCALE = 0.5;
// A war card lands on top of the first card, this far down and to the right
const WAR_OFFSET = { x: 24, y: 14 };
const CHIP_SCALE = 0.95;
const WAR_CHIP_SCALE = 0.8;
const WAR_CHIP_DX = 26;
// A surrendered player's returned half rests here, just off the circle on the player's side
const RETURNED = { x: 48, y: 128, scale: 0.75 };
const DEAL_MS = 280;
const FLIP_MS = 100;
const BURN_MS = 700;
const BURN_GAP = 150;
// The bot's shoe is one 52-card deck, swapped for a fresh one when it can't cover a draw or a burn
const DECK_SIZE = 52;
// How dark a losing or surrendered hand's cards turn
const DIM = 0.55;

function words(text, size, fill, family = MARKS, weight = "700") {
  const shadow = { color: 0x000000, alpha: 0.7, blur: 4, distance: 2, angle: Math.PI / 2 };
  const piece = new Text({
    text,
    style: { fontFamily: family, fontWeight: weight, fontSize: size, fill, dropShadow: shadow },
    resolution: 3,
  });
  piece.anchor.set(0.5);
  return piece;
}

function shortName(name) {
  const text = String(name || "");
  return text.length > 11 ? `${text.slice(0, 10)}…` : text;
}

function clear(layer) {
  layer.removeChildren().forEach((child) => child.destroy({ children: true }));
}

async function loadSprite(file, width) {
  const texture = await Assets.load(new URL(`../art/war/${file}`, import.meta.url).href);
  const piece = new Sprite(texture);
  piece.anchor.set(0.5);
  piece.scale.set(width / texture.width);
  return piece;
}

// Everyone at the table: players still here, and anyone with a bet or a hand this round
function seated(state) {
  const hands = state.hands || {};
  return (state.players || []).filter((player) => player.bet || hands[player.id] || !player.away);
}

// The seated players, the viewer kept in view, folded to six spots with a "+N" in the last one
function seating(state, me) {
  const players = seated(state);
  if (players.length <= SLOTS.length) {
    return { shown: players, more: 0 };
  }
  const keep = SLOTS.length - 1;
  const mine = players.find((player) => player.id === me);
  let shown = players.slice(0, keep);
  if (mine && !shown.includes(mine)) {
    shown = [...players.slice(0, keep - 1), mine];
  }
  return { shown, more: players.length - keep };
}

// Spots fill from the middle of the curve outwards, so a small table sits in front of the dealer
function slotsFor(count) {
  const start = Math.floor((SLOTS.length - count) / 2);
  return SLOTS.slice(start, start + count);
}

function placeCards(layer, cards, scale) {
  clear(layer);
  cards.forEach((card, index) => {
    const piece = cardSprite(card);
    piece.scale.set(scale);
    piece.position.set(index * WAR_OFFSET.x, index * WAR_OFFSET.y);
    layer.addChild(piece);
  });
}

function badge(text, fill, color) {
  const piece = new Container();
  const label = words(text, 24, color, FONT, "800");
  piece.addChild(
    new Graphics()
      .roundRect(-label.width / 2 - 14, -18, label.width + 28, 36, 18)
      .fill({ color: fill })
      .stroke({ width: 2, color: GOLD_LIGHT }),
    label,
  );
  return piece;
}

function namePill(name, isMe) {
  const pill = new Container();
  const label = words(shortName(name), 22, isMe ? GOLD_LIGHT : CREAM);
  pill.addChild(
    new Graphics()
      .roundRect(-label.width / 2 - 12, -17, label.width + 24, 34, 17)
      .fill({ color: INK, alpha: 0.7 })
      .stroke({ width: 2, color: isMe ? GOLD_LIGHT : GOLD, alpha: isMe ? 1 : 0.5 }),
    label,
  );
  pill.y = NAME_DY;
  return pill;
}

function stacksOf(amounts) {
  const chips = new Container();
  const scale = amounts.length > 1 ? WAR_CHIP_SCALE : CHIP_SCALE;
  amounts.forEach((amount, index) => {
    const stack = chipStack(amount);
    stack.scale.set(scale);
    stack.x = amounts.length > 1 ? (index ? WAR_CHIP_DX : -WAR_CHIP_DX) : 0;
    chips.addChild(stack);
  });
  chips.y = CIRCLE_DY + 8;
  return chips;
}

// The stakes on the circle: one bet, or two equal ones at war. The table's bet is already the doubled stake once a
// player has gone to war; a war only this scene has seen dealt (no table update since) still shows the first bet
function stakes(player, hand, dealtWar) {
  if (!player.bet) {
    return [];
  }
  if (hand && (hand.war_card || hand.status === "war")) {
    return [Math.floor(player.bet / 2), Math.ceil(player.bet / 2)];
  }
  return dealtWar ? [player.bet, player.bet] : [player.bet];
}

function makeSpot(seat, nameOf, isMe) {
  const spot = new Container();
  spot.glow = new Graphics();
  for (let ring = 0; ring < 4; ring += 1) {
    const grow = 6 + ring * 7;
    spot.glow
      .roundRect(-BOX.width / 2 - grow, -BOX.height / 2 - grow, BOX.width + grow * 2, BOX.height + grow * 2, 12 + grow)
      .stroke({ width: 7, color: GOLD_LIGHT, alpha: 0.5 - ring * 0.11 });
  }
  spot.glow.position.set(WAR_OFFSET.x / 2, WAR_OFFSET.y / 2);
  spot.glow.visible = false;
  spot.addChild(spot.glow);
  if (isMe) {
    spot.addChild(
      new Graphics()
        .roundRect(-BOX.width / 2 - 5, -BOX.height / 2 - 5, BOX.width + 10, BOX.height + 10, 12)
        .stroke({ width: 4, color: GOLD_LIGHT }),
      new Graphics().circle(0, CIRCLE_DY, CIRCLE_RADIUS + 4).stroke({ width: 4, color: GOLD_LIGHT }),
    );
  }
  spot.cards = new Container();
  spot.chips = stacksOf(seat.amounts);
  spot.addChild(spot.cards, spot.chips, namePill(nameOf(seat.player.id), isMe));
  placeCards(spot.cards, seat.cards, CARD_SCALE);
  return spot;
}

function moreSpot(count) {
  const spot = new Container();
  const circle = new Graphics().circle(0, CIRCLE_DY, 40).fill({ color: INK, alpha: 0.6 }).stroke({ width: 3, color: GOLD });
  const label = words(`+${count}`, 30, CREAM);
  label.y = CIRCLE_DY;
  spot.addChild(circle, label);
  return spot;
}

// "choosing..." on a dark pill just under the TIE badge, over the top of the card
function choosing() {
  const note = new Container();
  const label = words("choosing...", 17, CREAM, FONT, "600");
  note.addChild(
    new Graphics().roundRect(-label.width / 2 - 8, -12, label.width + 16, 24, 12).fill({ color: INK, alpha: 0.8 }),
    label,
  );
  note.y = 31;
  return note;
}

// TIE pulses while the player chooses; WAR stays up until the war cards decide it
function addBadge(spot, seat, waiting, pulses) {
  const status = seat.hand ? seat.hand.status : "";
  let piece = null;
  if (status === "war" || (seat.dealtWar && !["win", "lose"].includes(status))) {
    piece = badge("WAR", BURGUNDY, GOLD_LIGHT);
  } else if (status === "tie") {
    piece = badge("TIE", GOLD, INK);
    pulses.push(piece);
    if (waiting) {
      piece.addChild(choosing());
    }
  }
  if (piece) {
    piece.y = -BOX.height / 2 - 14;
    spot.addChild(piece);
  }
}

// The look of a settled spot without animating: winners glow on their payout, losers' cards dim and their chips are
// gone, a surrender keeps only the half that came back
function settle(spot, seat) {
  const status = seat.hand ? seat.hand.status : "";
  const payout = seat.player.payout || 0;
  if (status === "win") {
    spot.glow.visible = true;
    if (payout) {
      replaceChips(spot, [payout]);
    }
  } else if (status === "lose") {
    dim(spot.cards, DIM);
    spot.chips.visible = false;
  } else if (status === "surrender") {
    dim(spot.cards, DIM);
    replaceChips(spot, payout ? [payout] : []);
    spot.chips.scale.set(RETURNED.scale);
    spot.chips.position.set(RETURNED.x, RETURNED.y);
  }
}

// Darkens a hand's cards: level 1 leaves them as they are, 0 is black
function dim(cards, level) {
  const grey = Math.round(255 * Math.min(1, Math.max(0, level)));
  cards.tint = (grey << 16) | (grey << 8) | grey;
}

function dimOver(cards, ms) {
  let level = 1;
  const driver = {
    get destroyed() {
      return cards.destroyed;
    },
    get level() {
      return level;
    },
    set level(next) {
      level = next;
      dim(cards, next);
    },
  };
  return tween(driver, { level: DIM }, ms);
}

function replaceChips(spot, amounts) {
  const fresh = stacksOf(amounts);
  spot.addChildAt(fresh, spot.getChildIndex(spot.chips));
  spot.chips.destroy({ children: true });
  spot.chips = fresh;
}

// The same end state as settle, arrived at with a short flourish that nothing waits on
function flourish(spot, seat, effects) {
  const status = seat.hand ? seat.hand.status : "";
  if (status === "win") {
    settle(spot, seat);
    spot.glow.alpha = 0;
    spot.chips.scale.set(0.5);
    tween(spot.glow, { alpha: 1 }, 500);
    tween(spot.chips, { scale: 1.12 }, 450, ease.back).then(() => tween(spot.chips, { scale: 1 }, 250));
    sparkle(effects, spot.x, spot.y + CIRCLE_DY - 10, 1100);
  } else if (status === "lose") {
    dimOver(spot.cards, 500);
    tween(spot.chips, { y: spot.chips.y - 90, alpha: 0 }, 600, ease.inOut);
  } else if (status === "surrender") {
    const kept = spot.chips;
    dimOver(spot.cards, 500);
    tween(kept, { y: kept.y - 90, alpha: 0 }, 600, ease.inOut).then(() => kept.destroy({ children: true }));
    const back = stacksOf(seat.player.payout ? [seat.player.payout] : []);
    spot.addChild(back);
    spot.chips = back;
    tween(back, { x: RETURNED.x, y: RETURNED.y, scale: RETURNED.scale }, 600, ease.inOut);
  }
}

async function loadBackground() {
  const texture = await Assets.load(new URL("../art/war/table.jpg", import.meta.url).href);
  const back = new Sprite(texture);
  back.position.set(BACKGROUND.x, BACKGROUND.y);
  back.width = BACKGROUND.width;
  back.height = BACKGROUND.height;
  return back;
}

async function buildTable(root) {
  const [back, shoe, tray] = await Promise.all([
    loadBackground(),
    loadSprite("shoe.png", SHOE.width),
    loadSprite("discard-tray.png", DISCARD.width),
  ]);
  shoe.position.set(SHOE.x, SHOE.y);
  tray.position.set(DISCARD.x, DISCARD.y);
  const parts = {
    discard: new Container(),
    dealer: new Container(),
    spots: new Container(),
    effects: new Container(),
    count: words("", 20, CREAM),
  };
  parts.discard.position.set(DISCARD.x, DISCARD.y);
  parts.dealer.position.set(DEALER.x, DEALER.y);
  parts.count.position.set(SHOE.x, SHOE.y + 58);
  root.addChild(back, tray, parts.discard, shoe, parts.count, parts.dealer, parts.spots, parts.effects);
  return parts;
}

export async function createScene(stage) {
  await loadArt();
  const root = fitted(WIDTH, HEIGHT);
  const parts = await buildTable(root);
  stage.root.addChild(root);
  return sceneApi(stage, root, parts);
}

// Before its first draw the bot's shoe is empty and the first card comes from a fresh deck, so that is what shows
function countText(deck) {
  return Number.isFinite(deck) ? `Cards in shoe: ${deck || DECK_SIZE}` : "";
}

// The shoe after count cards leave it, refilled first the way the bot does when it runs short
function drawFrom(table, parts, count) {
  if (!Number.isFinite(table.deck)) {
    return;
  }
  table.deck = (table.deck < count ? DECK_SIZE : table.deck) - count;
  parts.count.text = countText(table.deck);
}

function showBurned(layer, count) {
  clear(layer);
  for (let index = 0; index < count; index += 1) {
    const piece = cardSprite(null);
    piece.scale.set(DISCARD_SCALE);
    piece.position.set(index * 2 - 2, -index * 3 + 3);
    piece.rotation = (index - 1) * 0.06;
    layer.addChild(piece);
  }
}

function sceneApi(stage, root, parts) {
  const table = createTable(stage, parts);
  const pulse = () => {
    const k = 1 + 0.08 * Math.sin(performance.now() / 160);
    table.pulses.forEach((piece) => {
      if (!piece.destroyed) {
        piece.scale.set(k);
      }
    });
  };
  stage.app.ticker.add(pulse);
  return {
    show(state) {
      table.show(state);
    },
    async play(event) {
      if (event.kind === "deal") {
        await table.deal(event);
      } else if (event.kind === "burn") {
        await table.burn(event.count || 3);
      }
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {
      stage.app.ticker.remove(pulse);
    },
  };
}

// The scene's memory of one round: the bot only sends the table again once the dealing stops, so the cards dealt
// since are kept here to redraw the table between deals
function createTable(stage, parts) {
  const table = {
    state: null,
    seen: null,
    flourished: null,
    round: null,
    dealt: {},
    burned: 0,
    deck: null,
    where: {},
    pulses: [],
  };
  table.show = (state) => showTable(stage, parts, table, state);
  table.deal = (event) => dealTo(stage, parts, table, event);
  table.burn = (count) => burnCards(stage, parts, table, count);
  return table;
}

function cardsOf(table, state, to) {
  let cards;
  if (to === "dealer") {
    cards = [state.dealer, state.war_dealer].filter(Boolean);
  } else {
    const hand = (state.hands || {})[to];
    cards = hand ? [hand.card, hand.war_card].filter(Boolean) : [];
  }
  const dealt = state.phase === "playing" ? table.dealt[to] || [] : [];
  return dealt.length > cards.length ? dealt : cards;
}

// fromBot is false when the scene redraws its own memory between deals, which keeps its own count of the shoe
function showTable(stage, parts, table, state, fromBot = true) {
  if (state.round !== table.round || !["playing", "results"].includes(state.phase)) {
    table.round = state.round;
    table.dealt = {};
    table.burned = 0;
  }
  table.state = state;
  if (fromBot) {
    table.deck = state.deck;
  }
  parts.count.text = countText(table.deck);
  placeCards(parts.dealer, cardsOf(table, state, "dealer"), DEALER.scale);
  showBurned(parts.discard, state.war_dealer || table.burned ? 3 : 0);
  const fresh = state.phase === "results" && table.seen && table.seen.round === state.round;
  const animate = fresh && table.seen.phase !== "results" && table.flourished !== state.round;
  drawSpots(stage, parts, table, state, animate);
  if (animate) {
    table.flourished = state.round;
  }
  table.seen = { round: state.round, phase: state.phase };
}

function drawSpots(stage, parts, table, state, animate) {
  const me = stage.me();
  clear(parts.spots);
  table.pulses = [];
  table.where = {};
  const { shown, more } = seating(state, me);
  const slots = slotsFor(shown.length + (more ? 1 : 0));
  const waiting = new Set(state.waiting || []);
  shown.forEach((player, index) => {
    const hand = (state.hands || {})[player.id];
    const cards = cardsOf(table, state, player.id);
    const dealtWar = cards.length > 1 && !(hand && hand.war_card);
    const seat = { player, hand, cards, dealtWar, amounts: stakes(player, hand, dealtWar) };
    const spot = makeSpot(seat, stage.nameOf, player.id === me);
    spot.position.set(slots[index].x, slots[index].y);
    addBadge(spot, seat, waiting.has(player.id), table.pulses);
    parts.spots.addChild(spot);
    table.where[player.id] = slots[index];
    if (state.phase === "results") {
      (animate ? flourish : settle)(spot, seat, parts.effects);
    }
  });
  if (more) {
    const spot = moreSpot(more);
    const slot = slots[slots.length - 1];
    spot.position.set(slot.x, slot.y);
    parts.spots.addChild(spot);
    // Cards for the folded players still fly to the table, into the "+N" spot
    const folded = { x: slot.x, y: slot.y + CIRCLE_DY };
    seated(state).forEach((player) => {
      table.where[player.id] = table.where[player.id] || folded;
    });
  }
}

// One card from the shoe's mouth to its place, face down, then turned up
async function dealTo(stage, parts, table, event) {
  const to = String(event.to);
  const held = (table.dealt[to] = table.dealt[to] || []);
  const count = Math.max(held.length, table.state ? cardsOf(table, table.state, to).length : 0);
  const base = to === "dealer" ? DEALER : table.where[to];
  held.push(event.card);
  drawFrom(table, parts, 1);
  if (!base) {
    return;
  }
  const scale = to === "dealer" ? DEALER.scale : CARD_SCALE;
  const target = { x: base.x + Math.min(count, 1) * WAR_OFFSET.x, y: base.y + Math.min(count, 1) * WAR_OFFSET.y };
  const piece = cardSprite(null);
  piece.scale.set(scale);
  parts.effects.addChild(piece);
  stage.sound.play("deal");
  await dealCard(piece, MOUTH, target, DEAL_MS);
  await flipCard(piece, event.card, FLIP_MS);
  piece.destroy({ children: true });
  if (table.state) {
    showTable(stage, parts, table, { ...table.state, phase: "playing" }, false);
  }
}

// Three cards face down from the shoe to the discard tray, one after another
async function burnCards(stage, parts, table, count) {
  stage.sound.play("slide");
  const flights = [];
  for (let index = 0; index < count; index += 1) {
    const piece = cardSprite(null);
    piece.scale.set(DISCARD_SCALE);
    piece.visible = false;
    parts.effects.addChild(piece);
    const landing = { x: DISCARD.x + index * 2 - 2, y: DISCARD.y - index * 3 + 3 };
    flights.push(
      new Promise((resolve) => setTimeout(resolve, index * BURN_GAP))
        .then(() => dealCard(piece, MOUTH, landing, BURN_MS))
        .then(() => piece.destroy({ children: true })),
    );
  }
  await Promise.all(flights);
  table.burned = count;
  // Everyone has chosen by the time cards burn
  if (table.state) {
    table.state = { ...table.state, waiting: [] };
  }
  drawFrom(table, parts, count);
  showBurned(parts.discard, count);
}
