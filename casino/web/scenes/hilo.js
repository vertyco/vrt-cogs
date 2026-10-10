// Hi-Lo: a dice tray split into LOW (2 to 6), SEVEN and HIGH (8 to 12). Each player's chips sit in the zone they
// called; the dice tumble onto the felt above the tray and the zone of their total lights up.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { chipStack, dieSprite, loadArt, rollDice, sparkle } from "./art.js";
import { ease, fit, fitted, tween, wait } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
// The background is drawn bigger than the scene so a letterbox shows more table, not black
const BACKGROUND = { x: -150, y: -150, width: 1200, height: 800 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const CREAM = 0xf6ecd2;
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const INK = 0x1a0f08;
// Each zone's felt inside the tray, in scene space (measured from art/hilo/table.jpg)
const ZONES = [
  { key: "low", word: "LOW", range: "2-6", x: 24, y: 205, width: 277, height: 323 },
  { key: "seven", word: "SEVEN", range: "×5", x: 309, y: 205, width: 283, height: 323 },
  { key: "high", word: "HIGH", range: "8-12", x: 599, y: 205, width: 276, height: 323 },
];
// Where the dice land, on the felt above the tray, and how big they are drawn there
const DICE = { x: 450, y: 78, scale: 1.4 };
// How far above its zone's top edge a zone's label sits, clear of the tray's frame
const LABEL_ABOVE = 46;
const THROW_FROM = { x: 880, y: -40 };
const DIE_SPREAD = 48 * 0.7;
// Players shown per zone before the rest fold into a "+N" spot
const PER_ZONE = 3;
const SPOT_GAP = 86;
const ROLL_MS = 1400;
// A winning stack ends this much bigger; a right Seven pays five times as much, so it grows more
const GROWTH = { low: 1.12, seven: 1.3, high: 1.12 };
// Chips are drawn bigger than the kit size so a stack still reads on an upright phone
const CHIP_SCALE = 1.3;

function zoneOf(total) {
  return total < 7 ? "low" : total > 7 ? "high" : "seven";
}

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

function shortName(name) {
  const text = String(name || "");
  return text.length > 10 ? `${text.slice(0, 9)}…` : text;
}

// One zone: its tap area, its label, the light for a winning total and a dimmer for the others
function makeZone(zone, onTap) {
  const piece = new Container();
  piece.position.set(zone.x, zone.y);
  const hit = new Graphics().rect(0, 0, zone.width, zone.height).fill({ color: 0x000000, alpha: 0.001 });
  hit.eventMode = "static";
  hit.cursor = "pointer";
  hit.on("pointertap", () => onTap(zone));
  piece.dim = new Graphics().rect(0, 0, zone.width, zone.height).fill({ color: 0x000000, alpha: 0.35 });
  piece.light = new Graphics()
    .roundRect(3, 3, zone.width - 6, zone.height - 6, 10)
    .fill({ color: GOLD_LIGHT, alpha: 0.07 })
    .stroke({ width: 6, color: GOLD_LIGHT, alpha: 0.95 });
  piece.flash = new Graphics().rect(0, 0, zone.width, zone.height).fill({ color: CREAM, alpha: 0.18 });
  piece.dim.visible = piece.light.visible = piece.flash.visible = false;
  piece.spots = new Container();
  piece.addChild(hit, piece.dim, piece.light, piece.flash, zoneLabel(zone), piece.spots);
  return piece;
}

// "LOW 2-6" on the felt just above its zone: the word in Playfair, the numbers in sans-serif
function zoneLabel(zone) {
  const label = new Container();
  const word = words(zone.word, 40, CREAM, FONT);
  const range = words(zone.range, 32, GOLD_LIGHT);
  const gap = 14;
  const width = word.width + gap + range.width;
  word.x = -width / 2 + word.width / 2;
  range.x = width / 2 - range.width / 2;
  range.y = 2;
  label.addChild(word, range);
  label.position.set(zone.width / 2, -LABEL_ABOVE);
  return label;
}

// The players who called this zone, the viewer first, folded to PER_ZONE spots
function spotsFor(players, key, me) {
  const here = players.filter((player) => player.choice === key && player.bet);
  here.sort((a, b) => (b.id === me) - (a.id === me));
  if (here.length <= PER_ZONE) {
    return { shown: here, more: 0 };
  }
  return { shown: here.slice(0, PER_ZONE - 1), more: here.length - (PER_ZONE - 1) };
}

// One player's spot: a gold ring for the viewer, their chips (the payout once they've won) and their name
function makeSpot(player, isMe, nameOf, low) {
  const spot = new Container();
  if (isMe) {
    spot.addChild(new Graphics().ellipse(0, 16, 48, 19).stroke({ width: 4, color: GOLD_LIGHT }));
  }
  const won = player.outcome === "win" && player.payout;
  spot.stack = chipStack(won ? player.payout : player.bet);
  spot.stack.scale.set(CHIP_SCALE);
  spot.addChild(spot.stack);
  const name = words(shortName(nameOf(player.id)), 22, isMe ? GOLD_LIGHT : CREAM);
  const pill = new Graphics()
    .roundRect(-name.width / 2 - 10, -16, name.width + 20, 32, 16)
    .fill({ color: INK, alpha: 0.65 })
    .stroke({ width: 2, color: isMe ? GOLD_LIGHT : GOLD, alpha: isMe ? 1 : 0.5 });
  // Neighbours' names sit at two heights, so long names never cover each other
  const nameY = low ? 98 : 62;
  pill.position.set(0, nameY);
  name.position.set(0, nameY);
  spot.addChild(pill, name);
  if (won) {
    spot.prize = words(`+${Number(player.payout).toLocaleString("en-US")}`, 26, GOLD_LIGHT);
    spot.prize.position.set(0, -120);
    spot.addChild(spot.prize);
  }
  return spot;
}

function moreSpot(count) {
  const spot = new Container();
  spot.addChild(new Graphics().circle(0, 0, 30).fill({ color: INK, alpha: 0.6 }).stroke({ width: 3, color: GOLD }));
  spot.addChild(words(`+${count}`, 26, CREAM));
  return spot;
}

// Draws one zone's spots; returns each player's spot by id, for the results flourish
function placeSpots(zonePiece, zone, state, me, nameOf) {
  zonePiece.spots.removeChildren().forEach((child) => child.destroy({ children: true }));
  const { shown, more } = spotsFor(state.players || [], zone.key, me);
  const count = shown.length + (more ? 1 : 0);
  const byId = {};
  const baseline = zone.height - 128;
  shown.forEach((player, index) => {
    const spot = makeSpot(player, player.id === me, nameOf, index % 2 === 1);
    spot.position.set(zone.width / 2 + (index - (count - 1) / 2) * SPOT_GAP, baseline);
    spot.outcome = player.outcome;
    zonePiece.spots.addChild(spot);
    byId[player.id] = spot;
  });
  if (more) {
    const spot = moreSpot(more);
    spot.position.set(zone.width / 2 + (count - 1 - (count - 1) / 2) * SPOT_GAP, baseline - 20);
    zonePiece.spots.addChild(spot);
  }
  return byId;
}

// The final look of a settled spot: winners bigger, losers faded
function settle(spot, key) {
  if (spot.outcome === "win") {
    spot.stack.scale.set(CHIP_SCALE * GROWTH[key]);
  } else if (spot.outcome === "lose") {
    spot.alpha = 0.3;
    spot.y += 12;
  }
}

function flourish(spot, key, layer) {
  if (spot.outcome === "win") {
    const grow = CHIP_SCALE * GROWTH[key];
    spot.stack.scale.set(CHIP_SCALE * 0.6);
    tween(spot.stack, { scale: grow }, 650, ease.back);
    const at = spot.getGlobalPosition();
    const local = layer.toLocal(at);
    sparkle(layer, local.x, local.y - 30, key === "seven" ? 1300 : 900);
    if (key === "seven") {
      wait(250).then(() => !layer.destroyed && sparkle(layer, local.x, local.y - 60, 1100));
    }
  } else if (spot.outcome === "lose") {
    spot.alpha = 1;
    tween(spot, { alpha: 0.3, y: spot.y + 12 }, 600);
  }
}

function lightZones(zonePieces, key) {
  for (const piece of zonePieces) {
    piece.light.visible = piece.zone.key === key;
    piece.light.alpha = 1;
    piece.dim.visible = Boolean(key) && piece.zone.key !== key;
  }
}

function makeDice(layer) {
  const dice = [dieSprite(1), dieSprite(1)];
  dice.forEach((die) => {
    die.visible = false;
    layer.addChild(die);
  });
  return dice;
}

// The dice at rest where rollDice leaves them, showing faces
function restDice(dice, faces) {
  dice.forEach((die, index) => {
    const side = index === 0 ? -1 : 1;
    die.visible = true;
    die.position.set(side * DIE_SPREAD, side * 4);
    die.rotation = 0;
    die.scale.set(1);
    setFace(die, faces[index]);
  });
}

// art.js keeps its textures to itself, so a face is borrowed from a fresh die of that face
function setFace(die, face) {
  const fresh = dieSprite(face);
  die.pips.texture = fresh.pips.texture;
  die.face = face;
  fresh.destroy({ children: true });
}

async function loadBackground() {
  const url = new URL("../art/hilo/table.jpg", import.meta.url).href;
  const texture = await Assets.load(url);
  const back = new Sprite(texture);
  back.position.set(BACKGROUND.x, BACKGROUND.y);
  back.width = BACKGROUND.width;
  back.height = BACKGROUND.height;
  return back;
}

export async function createScene(stage) {
  await loadArt();
  const root = fitted(WIDTH, HEIGHT);
  root.addChild(await loadBackground());
  const flashZone = (piece) => {
    piece.flash.visible = true;
    piece.flash.alpha = 1;
    tween(piece.flash, { alpha: 0 }, 350).then(() => {
      if (!piece.destroyed) {
        piece.flash.visible = false;
      }
    });
  };
  const zonePieces = ZONES.map((zone) => {
    const piece = makeZone(zone, () => {
      stage.sound.play("click");
      stage.actions.choose(zone.key);
      flashZone(piece);
    });
    piece.zone = zone;
    return piece;
  });
  root.addChild(...zonePieces);
  const diceLayer = new Container();
  diceLayer.position.set(DICE.x, DICE.y);
  diceLayer.scale.set(DICE.scale);
  const dice = makeDice(diceLayer);
  const total = words("", 46, CREAM);
  total.position.set(DICE.x + 140, DICE.y);
  const effects = new Container();
  root.addChild(diceLayer, total, effects);
  stage.root.addChild(root);
  return sceneApi(stage, root, { zonePieces, dice, total, effects });
}

function showDrawn(parts, drawn) {
  const faces = drawn && drawn.dice;
  if (!faces) {
    parts.dice.forEach((die) => {
      die.visible = false;
    });
    parts.total.text = "";
    lightZones(parts.zonePieces, null);
    return;
  }
  restDice(parts.dice, faces);
  parts.total.text = `= ${faces[0] + faces[1]}`;
  lightZones(parts.zonePieces, zoneOf(faces[0] + faces[1]));
}

function sceneApi(stage, root, parts) {
  let seen = null;
  let flourished = null;
  return {
    show(state) {
      const me = stage.me();
      showDrawn(parts, state.drawn);
      const fresh =
        state.phase === "results" && seen && seen.round === state.round && seen.phase !== "results";
      const animate = fresh && flourished !== state.round;
      for (const piece of parts.zonePieces) {
        const spots = placeSpots(piece, piece.zone, state, me, stage.nameOf);
        if (state.phase !== "results") {
          continue;
        }
        for (const spot of Object.values(spots)) {
          if (animate) {
            flourish(spot, piece.zone.key, parts.effects);
          } else {
            settle(spot, piece.zone.key);
          }
        }
      }
      if (animate) {
        flourished = state.round;
      }
      seen = { round: state.round, phase: state.phase };
    },
    async play(event) {
      if (event.kind !== "roll" || !event.dice) {
        return;
      }
      await roll(stage, parts, event.dice);
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {},
  };
}

async function roll(stage, parts, faces) {
  lightZones(parts.zonePieces, null);
  parts.total.text = "";
  const from = { x: (THROW_FROM.x - DICE.x) / DICE.scale, y: (THROW_FROM.y - DICE.y) / DICE.scale };
  parts.dice.forEach((die) => die.scale.set(1));
  stage.sound.play("throw");
  await rollDice(parts.dice, faces, from, { x: 0, y: 0 }, ROLL_MS);
  const sum = faces[0] + faces[1];
  stage.sound.play("land");
  parts.total.text = `= ${sum}`;
  parts.total.alpha = 0;
  lightZones(parts.zonePieces, zoneOf(sum));
  const lit = parts.zonePieces.find((piece) => piece.zone.key === zoneOf(sum));
  lit.light.alpha = 0;
  await Promise.all([tween(parts.total, { alpha: 1 }, 250), tween(lit.light, { alpha: 1 }, 250)]);
}
