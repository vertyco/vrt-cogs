// Dice: a felt table with a leather dice cup. The cup rattles, the two dice are thrown across the felt and land, and
// the winning totals (2, 7, 11 and 12) sit in gold boxes on the felt; the one rolled lights up. Each player's bet is
// a chip stack along the near rail with their name under it.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { chipStack, dieSprite, loadArt, moveChips, rollDice, sparkle } from "./art.js";
import { ease, fit, fitted, tween, wait } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const CREAM = 0xf6ecd2;
const CREAM_DIM = 0xc9b98f;
const FELT = 0x0b4424;
const BURGUNDY = 0x6b0f1a;
const WINS = [2, 7, 11, 12];
const BOX = { width: 128, height: 84, y: 128, gap: 26 };
const CUP = { x: 150, y: 318, width: 230 };
// The cup's mouth, where the dice leave it, and where they come to rest
const MOUTH = { x: 240, y: 314 };
const LANDING = [
  { x: 470, y: 312 },
  { x: 566, y: 330 },
];
const DIE_SCALE = 1.6;
const SPOTS = 6;
const SPOT_Y = 482;
const STACK_SCALE = 1.1;
const DEALER = { x: WIDTH / 2, y: 30 };
// The roll's steps, in ms: all of them end well inside the bot's 2 second wait for a roll
const SHAKE_MS = 350;
const THROW_MS = 1250;

async function loadTable() {
  const base = new URL("../art/dice/", import.meta.url).href;
  const [table, cup] = await Promise.all([
    Assets.load(base + "table.jpg"),
    Assets.load({ src: base + "cup.png", data: { autoGenerateMipmaps: true } }),
  ]);
  return { table, cup };
}

function makeText(text, size, fill, fontFamily = FONT) {
  const mark = new Text({ text, style: { fontFamily, fontWeight: "700", fontSize: size, fill }, resolution: 2 });
  mark.anchor.set(0.5);
  return mark;
}

// One gold-rimmed box on the felt for a winning total; lit() turns its glow on or off
function totalBox(total) {
  const box = new Container();
  const { width, height } = BOX;
  box.glow = new Graphics()
    .roundRect(-width / 2 - 10, -height / 2 - 10, width + 20, height + 20, 22)
    .fill({ color: GOLD_LIGHT, alpha: 0.35 });
  box.glow.visible = false;
  box.plate = new Graphics();
  box.number = makeText(String(total), 48, GOLD_LIGHT, MARKS);
  box.addChild(box.glow, box.plate, box.number);
  box.lit = (on) => {
    box.glow.visible = on;
    box.plate.clear();
    box.plate
      .roundRect(-width / 2, -height / 2, width, height, 14)
      .fill({ color: on ? BURGUNDY : FELT, alpha: on ? 0.95 : 0.55 })
      .stroke({ width: on ? 5 : 3, color: on ? GOLD_LIGHT : GOLD });
    box.number.style.fill = on ? 0xffffff : GOLD_LIGHT;
  };
  box.lit(false);
  return box;
}

function boxRow() {
  const row = new Container();
  const span = WINS.length * BOX.width + (WINS.length - 1) * BOX.gap;
  const boxes = {};
  WINS.forEach((total, index) => {
    const box = totalBox(total);
    box.position.set(WIDTH / 2 - span / 2 + BOX.width / 2 + index * (BOX.width + BOX.gap), BOX.y);
    boxes[total] = box;
    row.addChild(box);
  });
  return { row, boxes };
}

// Up to SPOTS players along the rail; more than that folds the rest into a "+N" spot at the end
function spotsFor(players) {
  if (players.length <= SPOTS) {
    return players.map((player) => ({ player }));
  }
  const shown = players.slice(0, SPOTS - 1).map((player) => ({ player }));
  return [...shown, { more: players.length - (SPOTS - 1) }];
}

function spotStep(count) {
  return Math.min(140, 760 / Math.max(1, count));
}

function spotX(index, count) {
  return WIDTH / 2 + (index - (count - 1) / 2) * spotStep(count);
}

// What a player's stack shows once the round is settled: winnings for a win, the bet back for a refund
function shownAmount(player) {
  if (player.bet == null) {
    return 0;
  }
  if (player.outcome === "lose") {
    return 0;
  }
  if (player.outcome && player.payout != null) {
    return player.payout;
  }
  return player.bet;
}

// Cuts a name down with an ellipsis until it fits its spot, so neighbors' names never run together
function shorten(name, room) {
  const full = name.text;
  let keep = full.length;
  while (name.width > room && keep > 1) {
    keep -= 1;
    name.text = `${full.slice(0, keep).trimEnd()}…`;
  }
}

function drawSpot(spot, { player, more }, mine, nameOf, room) {
  const ring = new Graphics()
    .ellipse(0, 8, 56, 24)
    .stroke({ width: mine ? 4 : 2, color: mine ? GOLD_LIGHT : CREAM_DIM, alpha: mine ? 1 : 0.5 });
  spot.addChild(ring);
  if (more) {
    spot.addChild(makeText(`+${more}`, 34, CREAM));
    return;
  }
  const amount = shownAmount(player);
  if (amount > 0) {
    spot.stack = chipStack(amount);
    spot.stack.scale.set(STACK_SCALE);
    spot.addChild(spot.stack);
  }
  const name = makeText(nameOf(player.id), 28, mine ? GOLD_LIGHT : CREAM);
  name.position.set(0, 98);
  shorten(name, room);
  spot.addChild(name);
}

export async function createScene(stage) {
  await loadArt();
  const art = await loadTable();
  const root = fitted(WIDTH, HEIGHT);
  const table = new Sprite(art.table);
  table.anchor.set(0.5);
  table.position.set(WIDTH / 2, HEIGHT / 2);
  table.width = 1200;
  table.height = 1200;
  const { row, boxes } = boxRow();
  const cup = new Sprite(art.cup);
  cup.anchor.set(0.5);
  cup.width = CUP.width;
  cup.scale.y = cup.scale.x;
  cup.position.set(CUP.x, CUP.y);
  const shadow = new Graphics().ellipse(CUP.x + 6, CUP.y + 58, 112, 20).fill({ color: 0x000000, alpha: 0.35 });
  const diceLayer = new Container();
  const spotsLayer = new Container();
  const flourishLayer = new Container();
  const total = makeText("", 34, CREAM, MARKS);
  total.position.set((LANDING[0].x + LANDING[1].x) / 2, 396);
  root.addChild(table, row, spotsLayer, shadow, cup, diceLayer, total, flourishLayer);
  stage.root.addChild(root);

  let dice = [];
  let lastDice = null;
  let spotsKey = "";
  let spots = [];
  let flourished = null;
  let first = true;

  function lightFor(faces) {
    const sum = faces ? faces[0] + faces[1] : 0;
    for (const [value, box] of Object.entries(boxes)) {
      box.lit(Number(value) === sum);
    }
    total.text = faces ? String(sum) : "";
  }

  function placeDice(faces) {
    if (dice.length === faces.length && dice.every((die, index) => die.face === faces[index])) {
      return;
    }
    dice.forEach((die) => die.destroy({ children: true }));
    dice = faces.map((face, index) => {
      const die = dieSprite(face);
      die.scale.set(DIE_SCALE);
      die.position.set(LANDING[index].x, LANDING[index].y);
      die.rotation = (index ? 1 : -1) * 0.12;
      diceLayer.addChild(die);
      return die;
    });
  }

  function drawSpots(state) {
    const players = (state.players || []).filter((player) => !player.away || player.bet != null);
    const me = stage.me();
    const key = JSON.stringify([players.map((p) => [p.id, p.bet, p.outcome, p.payout]), me]);
    if (key === spotsKey) {
      return;
    }
    spotsKey = key;
    spotsLayer.removeChildren().forEach((child) => child.destroy({ children: true }));
    const list = spotsFor(players);
    spots = list.map((entry, index) => {
      const spot = new Container();
      spot.position.set(spotX(index, list.length), SPOT_Y);
      spot.player = entry.player;
      drawSpot(spot, entry, entry.player && entry.player.id === me, stage.nameOf, spotStep(list.length) - 12);
      spotsLayer.addChild(spot);
      return spot;
    });
  }

  // Winners' stacks grow with a sparkle; losers' bets slide off toward the dealer and fade
  function flourish() {
    for (const spot of spots) {
      const player = spot.player;
      if (!player || player.bet == null) {
        continue;
      }
      if (player.outcome === "win" && spot.stack) {
        const stack = spot.stack;
        stack.scale.set(STACK_SCALE * 0.6);
        tween(stack, { scale: STACK_SCALE }, 500, ease.back);
        sparkle(flourishLayer, spot.x, spot.y - 20, 1100);
      } else if (player.outcome === "lose") {
        const gone = chipStack(player.bet);
        gone.scale.set(STACK_SCALE);
        gone.position.set(spot.x, spot.y);
        flourishLayer.addChild(gone);
        Promise.all([moveChips(gone, DEALER, 900), tween(gone, { alpha: 0 }, 900, ease.inOut)]).then(() => {
          if (!gone.destroyed) {
            gone.destroy({ children: true });
          }
        });
      }
    }
  }

  async function roll(faces) {
    lightFor(null);
    dice.forEach((die) => die.destroy({ children: true }));
    dice = [];
    stage.sound.play("shake");
    const start = performance.now();
    while (performance.now() - start < SHAKE_MS && !cup.destroyed) {
      const k = (performance.now() - start) / SHAKE_MS;
      cup.rotation = Math.sin(k * Math.PI * 9) * 0.12;
      cup.x = CUP.x + Math.sin(k * Math.PI * 13) * 5;
      await wait(16);
    }
    if (cup.destroyed) {
      return;
    }
    cup.rotation = 0;
    cup.x = CUP.x;
    stage.sound.play("throw");
    tween(cup, { x: CUP.x - 22, rotation: -0.08 }, 140, ease.out).then(() =>
      tween(cup, { x: CUP.x, rotation: 0 }, 320, ease.inOut),
    );
    dice = faces.map((face) => {
      const die = dieSprite(1 + Math.floor(Math.random() * 6));
      die.scale.set(DIE_SCALE);
      die.visible = false;
      diceLayer.addChild(die);
      return die;
    });
    const from = (index) => ({ x: MOUTH.x, y: MOUTH.y + (index ? 10 : -10) });
    await Promise.all(dice.map((die, index) => rollDice([die], [faces[index]], from(index), LANDING[index], THROW_MS)));
    if (cup.destroyed) {
      return;
    }
    stage.sound.play("land");
    lastDice = faces;
    lightFor(faces);
  }

  return {
    show(state) {
      const faces = state.drawn && state.drawn.dice ? state.drawn.dice : lastDice;
      if (faces) {
        lastDice = faces;
        placeDice(faces);
        lightFor(state.drawn && state.drawn.dice ? faces : null);
      }
      drawSpots(state);
      const fresh = state.phase === "results" && flourished !== state.round;
      if (fresh && !first) {
        flourish();
      }
      if (state.phase === "results") {
        flourished = state.round;
      }
      first = false;
    },
    async play(event) {
      if (event.kind === "roll" && event.dice) {
        await roll(event.dice);
      }
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {},
  };
}
