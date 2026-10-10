// Craps: a long table with padded rails. The shooter stands at the left end; the dice fly the length of the table,
// hit the far wall on the right and roll back. The point numbers sit in a row of boxes on the felt with the puck:
// black OFF beside them before a point, white ON on the point's box once there is one. The shooter's bet sits at
// their end, every other bettor's chips along the near rail, and this round's rolls in a strip on the far rail.
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
const INK = 0x1a0f08;
const POINTS = [4, 5, 6, 8, 9, 10];
const BOX = { width: 96, height: 104, y: 146, gap: 10, x: 500 };
const PUCK = { size: 60, off: { x: 112, y: 146 } };
const NOTE_Y = 236;
// Where the shooter stands, where the dice wait in front of them, the far wall they hit, and where they come to rest
const SHOOTER = { x: 114, y: 410 };
const WAITING = { x: 262, y: 372 };
const WALL = { x: 806, y: 352 };
const LANDING = { x: 690, y: 352 };
const DIE_SCALE = 1.35;
const DIE_GAP = 38;
const STRIP = { x: 470, y: 26, scale: 0.62, gap: 100 };
const SPOTS = 6;
const SPOT_Y = 470;
const NAME_Y = 566;
const RAIL = { left: 210, right: 840 };
const STACK_SCALE = 1.0;
const HOUSE = { x: WIDTH / 2, y: 20 };
// The roll's steps, in ms: all of them end well inside the bot's 2 second wait for a roll
const SHAKE_MS = 260;
const FLY_MS = 520;
const BACK_MS = 660;
const PUCK_MS = 200;

async function loadTable() {
  const base = new URL("../art/craps/", import.meta.url).href;
  const sprite = (file) => Assets.load({ src: base + file, data: { autoGenerateMipmaps: true } });
  const [table, on, off] = await Promise.all([
    Assets.load(base + "table.jpg"),
    sprite("puck-on.png"),
    sprite("puck-off.png"),
  ]);
  return { table, on, off };
}

function makeText(text, size, fill, fontFamily = FONT) {
  const mark = new Text({ text, style: { fontFamily, fontWeight: "700", fontSize: size, fill }, resolution: 2 });
  mark.anchor.set(0.5);
  return mark;
}

function sum(dice) {
  return dice[0] + dice[1];
}

// What this round's rolls add up to so far: the point (if the come-out set one) and the call on the latest roll
function callFor(rolls) {
  if (!rolls || !rolls.length) {
    return { point: null, call: null, total: null };
  }
  const first = sum(rolls[0]);
  const point = [7, 11, 2, 3, 12].includes(first) ? null : first;
  const total = sum(rolls[rolls.length - 1]);
  if (rolls.length === 1) {
    return { point, total, call: point ? "point" : [7, 11].includes(first) ? "win" : "lose" };
  }
  return { point, total, call: total === point ? "win" : "lose" };
}

// One gold-rimmed point box; lit() marks it as the point
function pointBox(number) {
  const box = new Container();
  const { width, height } = BOX;
  box.plate = new Graphics();
  box.number = makeText(String(number), 50, GOLD_LIGHT, MARKS);
  box.number.y = 16;
  box.addChild(box.plate, box.number);
  box.lit = (on) => {
    box.plate.clear();
    box.plate
      .roundRect(-width / 2, -height / 2, width, height, 12)
      .fill({ color: on ? BURGUNDY : FELT, alpha: on ? 0.95 : 0.5 })
      .stroke({ width: on ? 5 : 3, color: on ? GOLD_LIGHT : GOLD });
    box.number.style.fill = on ? 0xffffff : GOLD_LIGHT;
  };
  box.lit(false);
  return box;
}

function pointRow() {
  const row = new Container();
  const span = POINTS.length * BOX.width + (POINTS.length - 1) * BOX.gap;
  const boxes = {};
  POINTS.forEach((number, index) => {
    const box = pointBox(number);
    box.position.set(BOX.x - span / 2 + BOX.width / 2 + index * (BOX.width + BOX.gap), BOX.y);
    boxes[number] = box;
    row.addChild(box);
  });
  return { row, boxes };
}

// The rules for the next roll under the boxes: a small heading, then the payouts in the sans-serif so the numbers
// line up. Before a point it's the come-out's payouts; once there is a point, one more roll must hit it
function rollNote() {
  const note = new Container();
  const heading = makeText("", 18, GOLD_LIGHT);
  heading.style.letterSpacing = 3;
  const rules = makeText("", 24, CREAM, MARKS);
  rules.y = 30;
  note.addChild(heading, rules);
  note.position.set(BOX.x, NOTE_Y);
  note.update = (point) => {
    heading.text = point ? `POINT IS ${point}` : "COME-OUT ROLL";
    rules.text = point
      ? `Roll a ${point} to win   ·   anything else loses`
      : "7 pays 3x   ·   11 pays 1x   ·   2, 3, 12 lose";
  };
  note.update(null);
  return note;
}

// The puck: a black OFF face before a point, a white ON face on the point's box
function makePuck(art) {
  const puck = new Container();
  puck.shadow = new Graphics().circle(3, 5, PUCK.size / 2).fill({ color: 0x000000, alpha: 0.35 });
  puck.face = new Sprite(art.off);
  puck.face.anchor.set(0.5);
  puck.face.width = PUCK.size;
  puck.face.height = PUCK.size;
  puck.word = makeText("OFF", 17, CREAM);
  puck.addChild(puck.shadow, puck.face, puck.word);
  puck.turn = (on) => {
    puck.face.texture = on ? art.on : art.off;
    puck.word.text = on ? "ON" : "OFF";
    puck.word.style.fill = on ? INK : CREAM;
  };
  return puck;
}

// Up to SPOTS bettors along the rail; more than that folds the rest into a "+N" spot at the end
function spotsFor(players) {
  if (players.length <= SPOTS) {
    return players.map((player) => ({ player }));
  }
  const shown = players.slice(0, SPOTS - 1).map((player) => ({ player }));
  return [...shown, { more: players.length - (SPOTS - 1) }];
}

function spotStep(count) {
  return Math.min(130, (RAIL.right - RAIL.left) / Math.max(1, count));
}

function spotX(index, count) {
  return (RAIL.left + RAIL.right) / 2 + (index - (count - 1) / 2) * spotStep(count);
}

// What a player's stack shows once the round is settled: winnings for a win, the bet back for a refund
function shownAmount(player) {
  if (player.bet == null || player.outcome === "lose") {
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
    .ellipse(0, 8, 50, 22)
    .stroke({ width: mine ? 4 : 2, color: mine ? GOLD_LIGHT : CREAM_DIM, alpha: mine ? 1 : 0.5 });
  spot.addChild(ring);
  if (more) {
    spot.addChild(makeText(`+${more}`, 32, CREAM));
    return;
  }
  const amount = shownAmount(player);
  if (amount > 0) {
    spot.stack = chipStack(amount);
    spot.stack.scale.set(STACK_SCALE);
    spot.addChild(spot.stack);
  }
  spot.caption = makeText(nameOf(player.id), 26, mine ? GOLD_LIGHT : CREAM);
  spot.caption.position.set(0, NAME_Y - SPOT_Y);
  shorten(spot.caption, room);
  spot.addChild(spot.caption);
}

// The shooter's gold marker, above their spot at the left end
function shooterMark() {
  const mark = new Container();
  const word = makeText("SHOOTER", 17, INK);
  word.style.letterSpacing = 2;
  const width = word.width + 26;
  const plate = new Graphics()
    .roundRect(-width / 2, -15, width, 30, 15)
    .fill(GOLD_LIGHT)
    .stroke({ width: 2, color: GOLD });
  mark.addChild(plate, word);
  return mark;
}

// A small pair of dice for the strip of this round's rolls
function rollPair(dice) {
  const pair = new Container();
  dice.forEach((face, index) => {
    const die = dieSprite(face);
    die.scale.set(STRIP.scale);
    die.x = (index - 0.5) * 34;
    pair.addChild(die);
  });
  return pair;
}

// A die thrown from the shooter's end: one long arc across the felt to the far wall, spinning and lifting as it flies
function fly(die, from, to, ms, spin) {
  const scale = die.scale.x;
  const start = performance.now();
  return new Promise((resolve) => {
    const step = (now) => {
      if (die.destroyed) {
        resolve();
        return;
      }
      const k = Math.min(1, (now - start) / ms);
      const height = Math.sin(k * Math.PI);
      die.x = from.x + (to.x - from.x) * k;
      die.y = from.y + (to.y - from.y) * k - height * 90;
      die.scale.set(scale * (1 + height * 0.35));
      die.rotation = spin * k;
      if (k < 1) {
        requestAnimationFrame(step);
      } else {
        die.scale.set(scale);
        resolve();
      }
    };
    requestAnimationFrame(step);
  });
}

function buildTable(art) {
  const table = new Sprite(art.table);
  table.anchor.set(0.5);
  table.position.set(WIDTH / 2, HEIGHT / 2);
  table.width = 1200;
  table.height = 1200;
  return table;
}

export async function createScene(stage) {
  await loadArt();
  const art = await loadTable();
  const root = fitted(WIDTH, HEIGHT);
  const { row, boxes } = pointRow();
  const puck = makePuck(art);
  puck.position.set(PUCK.off.x, PUCK.off.y);
  const strip = new Container();
  const spotsLayer = new Container();
  const shooterLayer = new Container();
  const ready = new Graphics().ellipse(0, 0, 92, 50).stroke({ width: 4, color: GOLD_LIGHT });
  ready.position.set(WAITING.x, WAITING.y + 4);
  ready.visible = false;
  // A soft gold halo under winning dice: rings of faint gold that add up brighter toward the middle
  const glow = new Graphics();
  for (let ring = 0; ring < 7; ring += 1) {
    glow.ellipse(0, 0, 150 - ring * 14, 86 - ring * 9).fill({ color: GOLD_LIGHT, alpha: 0.09 });
  }
  glow.visible = false;
  const diceLayer = new Container();
  diceLayer.eventMode = "static";
  const total = makeText("", 46, CREAM, MARKS);
  const flourishLayer = new Container();
  const note = rollNote();
  root.addChild(buildTable(art), row, note, strip, spotsLayer, shooterLayer, puck, ready, glow);
  root.addChild(diceLayer, total, flourishLayer);
  stage.root.addChild(root);

  let dice = [];
  let diceKey = "";
  let diceHome = true;
  let spotsKey = "";
  let stripKey = "";
  let spots = [];
  let rolls = [];
  let canRoll = false;
  let flourished = null;
  let first = true;
  let rolling = false;

  // The ready ring breathes while the viewer is the shooter and the table waits on their roll
  const breathe = () => {
    if (ready.visible) {
      ready.alpha = 0.55 + 0.45 * Math.sin(performance.now() / 260);
    }
  };
  stage.app.ticker.add(breathe);

  diceLayer.on("pointertap", () => {
    if (canRoll && !rolling) {
      canRoll = false;
      ready.visible = false;
      diceLayer.cursor = "default";
      stage.sound.play("click");
      stage.actions.move("roll");
    }
  });

  function makeDice(faces, at) {
    diceHome = at === WAITING;
    dice.forEach((die) => die.destroy({ children: true }));
    dice = faces.map((face, index) => {
      const die = dieSprite(face);
      die.scale.set(DIE_SCALE);
      die.position.set(at.x + (index - 0.5) * DIE_GAP * 2, at.y + (index ? 8 : -8));
      die.rotation = (index ? 1 : -1) * 0.12;
      diceLayer.addChild(die);
      return die;
    });
  }

  // The call on the latest roll: the point's box lights and the puck goes ON, a win glows gold, a loss dims
  function callOut(called) {
    const { point, call, total: rolled } = called;
    for (const [number, box] of Object.entries(boxes)) {
      box.lit(Number(number) === point);
    }
    puck.turn(Boolean(point));
    note.update(point);
    const spot = point ? { x: boxes[point].x, y: BOX.y - BOX.height / 2 + 4 } : PUCK.off;
    puck.position.set(spot.x, spot.y);
    glow.visible = call === "win";
    glow.position.set(LANDING.x, LANDING.y);
    diceLayer.alpha = call === "lose" ? 0.5 : 1;
    total.text = rolled == null ? "" : String(rolled);
    total.style.fill = call === "win" ? GOLD_LIGHT : call === "lose" ? CREAM_DIM : CREAM;
    total.alpha = call === "lose" ? 0.7 : 1;
    total.position.set(LANDING.x - 128, LANDING.y);
  }

  // The dice wait in front of the shooter between rounds and when it's time to roll, otherwise where they landed
  function placeDice(waitingOnShooter) {
    const last = rolls.length ? rolls[rolls.length - 1] : null;
    const atShooter = !last || waitingOnShooter;
    const faces = last || (dice.length ? dice.map((die) => die.face) : [5, 2]);
    const key = JSON.stringify([faces, atShooter]);
    if (key !== diceKey) {
      diceKey = key;
      makeDice(faces, atShooter ? WAITING : LANDING);
    }
    callOut(atShooter ? { ...callFor(rolls), call: null, total: null } : callFor(rolls));
    if (atShooter) {
      diceLayer.alpha = 1;
    }
  }

  function drawStrip() {
    const key = JSON.stringify(rolls);
    if (key === stripKey) {
      return;
    }
    stripKey = key;
    strip.removeChildren().forEach((child) => child.destroy({ children: true }));
    rolls.forEach((pair, index) => {
      const piece = rollPair(pair);
      piece.position.set(STRIP.x + index * STRIP.gap, STRIP.y);
      strip.addChild(piece);
    });
  }

  function drawSpots(state) {
    const players = (state.players || []).filter((player) => !player.away || player.bet != null);
    const me = stage.me();
    const shooter = state.shooter;
    const key = JSON.stringify([players.map((p) => [p.id, p.bet, p.outcome, p.payout]), me, shooter]);
    if (key === spotsKey) {
      return;
    }
    spotsKey = key;
    for (const layer of [spotsLayer, shooterLayer]) {
      layer.removeChildren().forEach((child) => child.destroy({ children: true }));
    }
    spots = [];
    const thrower = players.find((player) => player.id === shooter);
    if (thrower) {
      const spot = new Container();
      spot.position.set(SHOOTER.x, SHOOTER.y);
      spot.player = thrower;
      drawSpot(spot, { player: thrower }, thrower.id === me, stage.nameOf, 170);
      spot.caption.y = 74;
      const mark = shooterMark();
      mark.y = -100;
      spot.addChild(mark);
      shooterLayer.addChild(spot);
      spots.push(spot);
    }
    const list = spotsFor(players.filter((player) => player !== thrower));
    list.forEach((entry, index) => {
      const spot = new Container();
      spot.position.set(spotX(index, list.length), SPOT_Y);
      spot.player = entry.player;
      drawSpot(spot, entry, entry.player && entry.player.id === me, stage.nameOf, spotStep(list.length) - 10);
      spotsLayer.addChild(spot);
      spots.push(spot);
    });
  }

  // Winners' stacks grow with a sparkle (three for a come-out 7); losers' bets are swept off to the house and fade
  function flourish() {
    const natural = rolls.length === 1 && sum(rolls[0]) === 7;
    for (const spot of spots) {
      const player = spot.player;
      if (!player || player.bet == null) {
        continue;
      }
      if (player.outcome === "win" && spot.stack) {
        spot.stack.scale.set(STACK_SCALE * 0.6);
        tween(spot.stack, { scale: STACK_SCALE }, 500, ease.back);
        for (let burst = 0; burst < (natural ? 3 : 1); burst += 1) {
          wait(burst * 380).then(() => !flourishLayer.destroyed && sparkle(flourishLayer, spot.x, spot.y - 24, 1100));
        }
      } else if (player.outcome === "lose") {
        const gone = chipStack(player.bet);
        gone.scale.set(STACK_SCALE);
        gone.position.set(spot.x, spot.y);
        flourishLayer.addChild(gone);
        Promise.all([moveChips(gone, HOUSE, 900), tween(gone, { alpha: 0 }, 900, ease.inOut)]).then(() => {
          if (!gone.destroyed) {
            gone.destroy({ children: true });
          }
        });
      }
    }
  }

  async function shake() {
    const start = performance.now();
    const home = dice.map((die) => ({ x: die.x, y: die.y }));
    while (performance.now() - start < SHAKE_MS && !diceLayer.destroyed) {
      const k = (performance.now() - start) / SHAKE_MS;
      dice.forEach((die, index) => {
        die.x = home[index].x + Math.sin(k * Math.PI * 11 + index) * 5;
        die.y = home[index].y + Math.cos(k * Math.PI * 9 + index) * 4;
      });
      await wait(16);
    }
  }

  // Shake in the shooter's hand, fly the length of the table to the far wall, bounce back and settle
  async function roll(faces) {
    rolling = true;
    canRoll = false;
    ready.visible = false;
    glow.visible = false;
    total.text = "";
    diceLayer.alpha = 1;
    if (!diceHome || !dice.length) {
      makeDice(dice.length ? dice.map((die) => die.face) : faces, WAITING);
    }
    stage.sound.play("shake");
    await shake();
    stage.sound.play("throw");
    const wall = (index) => ({ x: WALL.x - (index ? 4 : 30), y: WALL.y + (index ? 30 : -26) });
    const from = dice.map((die) => ({ x: die.x, y: die.y }));
    await Promise.all(dice.map((die, index) => fly(die, from[index], wall(index), FLY_MS, (index ? 1 : -1) * 8)));
    if (diceLayer.destroyed) {
      return;
    }
    stage.sound.play("land");
    const rest = (index) => ({ x: LANDING.x + (index - 0.5) * DIE_GAP * 2, y: LANDING.y + (index ? 8 : -8) });
    await Promise.all(dice.map((die, index) => rollDice([die], [faces[index]], wall(index), rest(index), BACK_MS)));
    if (diceLayer.destroyed) {
      return;
    }
    rolls = [...rolls, faces];
    diceKey = JSON.stringify([faces, false]);
    diceHome = false;
    drawStrip();
    const called = callFor(rolls);
    if (called.call === "point") {
      callOut({ ...called, point: null });
      await settlePuck(called);
    } else {
      callOut(called);
    }
  }

  // The puck slides from wherever it is onto the point's box and turns ON
  async function settlePuck(called) {
    const box = boxes[called.point];
    puck.turn(true);
    stage.sound.play("click");
    await tween(puck, { x: box.x, y: BOX.y - BOX.height / 2 + 4 }, PUCK_MS, ease.out);
    callOut(called);
  }

  return {
    show(state) {
      rolls = state.rolls || [];
      const me = stage.me();
      const waitingOnShooter = Boolean(state.shooter && (state.waiting || []).includes(state.shooter));
      canRoll = waitingOnShooter && state.shooter === me && !rolling;
      ready.visible = canRoll;
      diceLayer.cursor = canRoll ? "pointer" : "default";
      placeDice(waitingOnShooter);
      drawStrip();
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
        try {
          await roll(event.dice);
        } finally {
          rolling = false;
        }
      }
    },
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {
      stage.app.ticker.remove(breathe);
    },
  };
}
