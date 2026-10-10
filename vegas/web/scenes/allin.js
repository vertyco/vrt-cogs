// All In: the tall golden slot machine from the back of the lobby, up close. Three reels show through its windows,
// its lit display says ALL IN (and the multiplier during a pull), and the lever on its right pulls like the Pull
// button. All In is solo and each pull is private, so the scene is the viewer's own machine, with their name on its
// belly plate. The scene contract is the comment at the top of the stand-in scene.
import { Assets, Container, Graphics, Rectangle, Sprite, Text } from "../vendor/pixi.min.mjs";
import { loadArt, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

// Narrower than the other tables: the machine is tall, so it fills more of an upright phone
const WIDTH = 600;
const HEIGHT = 600;
// The room is bigger than the scene so a letterbox shows more room, not black
const BACKDROP = { width: 1350, height: 900 };
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const CREAM = 0xf6ecd2;
const INK = 0x1a0f08;
const RED = 0xc8202f;
// machine.png is saved at twice its drawn size; everything on the machine is placed in its pixels
const ART_SCALE = 0.5;
const MACHINE_AT = { x: 100, y: 10 };
// Measured from machine.png: the three reel windows (x0, y0, x1, y1), the display panel, the lever's hub, the
// payout tray's mouth, the name plate on the belly and the marquee bulbs
const WINDOWS = [
  [108, 389, 267, 663],
  [301, 389, 458, 663],
  [492, 389, 652, 663],
];
const DISPLAY = { x: 91, y: 227, width: 572, height: 108 };
const HUB = { x: 744, y: 535 };
const TRAY = { x: 380, y: 950 };
const PLATE = { x: 383, y: 843 };
const ARCH = [[108, 157], [150, 111], [201, 75], [260, 48], [319, 32], [380, 27], [442, 32], [500, 48], [559, 75]];
const SIDES = [248, 308, 369, 432, 496, 562, 627, 692, 801, 867];
// In chase order: up the left side, over the arch, down the right side
const BULBS = [
  ...[...SIDES].reverse().map((y) => [50, y]),
  ...ARCH,
  [610, 111],
  [651, 157],
  ...SIDES.map((y) => [707, y]),
];
// One reel's strip, top to bottom; one 7 per strip, like a real reel
const STRIP = ["seven", "cherry", "bell", "bar", "diamond", "coin", "cherry", "bell", "diamond", "bar", "coin", "bell"];
const SYMBOLS = ["seven", "cherry", "bell", "bar", "diamond", "coin"];
const DUDS = SYMBOLS.filter((name) => name !== "seven");
// Pull timing in ms from the event: the lever, the reels starting, each reel landing, and how long a reel's
// slow-down and bounce takes (it reaches its symbol about 37 percent of the way through)
const LEVER_MS = 300;
const SPIN_AT = 220;
const LANDS = [1400, 1900, 2350];
const SETTLE_MS = 380;
const ARRIVE = 0.37;
const MIN_SPEED = 0.016;
const CHASE_MS = 90;
const NAME_LENGTH = 12;
// The jackpot's coin bursts: when each starts (ms after the last reel lands) and where along the tray's mouth
const BURSTS = [[0, 0], [200, -60], [350, 60], [550, -25], [750, 30]];
const FOUNTAIN_SCALE = 1.5;

function text(value, style) {
  const piece = new Text({ text: value, style, resolution: 2 });
  piece.anchor.set(0.5);
  return piece;
}

function shortName(name) {
  const value = String(name || "");
  return value.length > NAME_LENGTH ? `${value.slice(0, NAME_LENGTH - 1)}…` : value;
}

function mod(value, size) {
  return ((value % size) + size) % size;
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

// A losing line: three different symbols with at most one 7, so it never looks like a near win
function dudLine() {
  const line = [];
  const pool = Math.random() < 0.4 ? [...SYMBOLS] : [...DUDS];
  while (line.length < 3) {
    const name = pick(pool);
    pool.splice(pool.indexOf(name), 1);
    line.push(name);
  }
  return line.sort(() => Math.random() - 0.5);
}

// Runs apply(k) every frame as k goes 0 to 1 over ms; stops when the scene is destroyed
function run(owner, ms, apply, curve = ease.linear) {
  const driver = {
    value: 0,
    get destroyed() {
      return owner.destroyed;
    },
    get k() {
      return this.value;
    },
    set k(next) {
      this.value = next;
      apply(next);
    },
  };
  return tween(driver, { k: 1 }, Math.max(1, ms), curve);
}

// A soft round glow made of rings that fade outward
function glow(radius, color, strength = 0.5) {
  const piece = new Graphics();
  for (let ring = 16; ring >= 1; ring -= 1) {
    piece.circle(0, 0, (radius * ring) / 16).fill({ color, alpha: strength * (1 - ring / 17) * 0.18 });
  }
  piece.blendMode = "add";
  return piece;
}

export async function createScene(stage) {
  await loadArt();
  const base = new URL("../art/allin/", import.meta.url).href;
  const names = ["room.jpg", "machine.png", "lever-arm.png", "lever-knob.png", "cherry.png", "bell.png", "diamond.png"];
  names.push("coin.png");
  const loaded = await Promise.all(names.map((name) => Assets.load({ src: base + name, data: { autoGenerateMipmaps: true } })));
  const art = Object.fromEntries(names.map((name, index) => [name.split(".")[0], loaded[index]]));
  const root = fitted(WIDTH, HEIGHT);
  stage.root.addChild(root);
  const room = new Sprite(art.room);
  room.anchor.set(0.5);
  room.position.set(WIDTH / 2, HEIGHT / 2);
  room.width = BACKDROP.width;
  room.height = BACKDROP.height;
  root.addChild(room);
  const machine = new Container();
  machine.position.set(MACHINE_AT.x, MACHINE_AT.y);
  machine.scale.set(ART_SCALE);
  root.addChild(machine);
  const cabinet = new Sprite(art.machine);
  const reels = WINDOWS.map((rect) => makeReel(rect, art));
  machine.addChild(...reels.map((reel) => reel.box), cabinet);
  // Each bulb: a glow to light it up and a dark disc to turn it off, since the picture's bulbs are all lit
  const lights = BULBS.map(([x, y]) => {
    const bulb = new Container();
    bulb.position.set(x, y);
    bulb.off = new Graphics().circle(0, 0, 15).fill({ color: 0x2a0a06, alpha: 0.7 });
    bulb.on = glow(30, 0xffe9a8);
    bulb.addChild(bulb.off, bulb.on);
    machine.addChild(bulb);
    return bulb;
  });
  const display = makeDisplay();
  machine.addChild(display);
  const lever = makeLever(art);
  machine.addChild(lever);
  const plate = text("", { fontFamily: MARKS, fontWeight: "700", fontSize: 34, fill: GOLD_LIGHT, letterSpacing: 1 });
  plate.position.set(PLATE.x, PLATE.y);
  machine.addChild(plate);
  // Coin bursts come out of the tray's mouth, drawn bigger than the kit's sparkle so they read as a jackpot
  const fountain = new Container();
  fountain.position.set(MACHINE_AT.x + TRAY.x * ART_SCALE, MACHINE_AT.y + TRAY.y * ART_SCALE);
  fountain.scale.set(FOUNTAIN_SCALE);
  root.addChild(fountain);
  let line = ["bell", "seven", "cherry"];
  let spinning = false;
  // Set by a lever tap until the pull starts, so a double tap sends one pull
  let armed = null;
  // Each pull's number, so a win's flourish stops when the next pull starts
  let pulls = 0;
  reels.forEach((reel, index) => reel.rest(line[index]));
  setLights("rest", 0);
  lever.on("pointertap", () => {
    if (spinning || armed) {
      return;
    }
    armed = setTimeout(() => (armed = null), 2000);
    stage.actions.place();
  });

  // ---- The display ----

  function makeDisplay() {
    const panel = new Container();
    panel.position.set(DISPLAY.x + DISPLAY.width / 2, DISPLAY.y + DISPLAY.height / 2);
    panel.halo = glow(DISPLAY.width * 0.55, GOLD_LIGHT, 0.6);
    panel.halo.scale.y = 0.35;
    panel.halo.alpha = 0.3;
    const style = { fontFamily: FONT, fontWeight: "900", fontSize: 64, fill: GOLD_LIGHT, letterSpacing: 6 };
    panel.words = text("ALL IN", { ...style, stroke: { color: INK, width: 4 } });
    panel.odds = text("", { ...style, fontFamily: MARKS, fontSize: 72, letterSpacing: 2, fill: 0xffe6a0 });
    panel.odds.visible = false;
    panel.addChild(panel.halo, panel.words, panel.odds);
    return panel;
  }

  function showOdds(multiplier) {
    display.odds.tint = 0xffffff;
    display.words.visible = multiplier === null;
    display.odds.visible = multiplier !== null;
    display.odds.text = multiplier === null ? "" : `×${multiplier}`;
    display.halo.alpha = 0.3;
    display.scale.set(1);
  }

  // ---- The lever ----

  function makeLever() {
    const piece = new Container();
    piece.position.set(HUB.x, HUB.y);
    piece.arm = new Sprite(art["lever-arm"]);
    piece.arm.anchor.set(0.5, 0.97);
    piece.arm.scale.x = 1.6;
    piece.knob = new Sprite(art["lever-knob"]);
    piece.knob.anchor.set(0.5);
    piece.addChild(piece.arm, piece.knob);
    piece.eventMode = "static";
    piece.cursor = "pointer";
    piece.hitArea = new Rectangle(-70, -piece.arm.height - 60, 140, piece.arm.height + 100);
    setLever(piece, 1);
    return piece;
  }

  // How far up the lever stands: 1 at rest, below 0 when pulled down past its hub toward the viewer
  function setLever(piece, reach) {
    piece.arm.scale.y = reach;
    const length = piece.arm.texture.height * 0.94;
    piece.knob.y = -length * reach;
    piece.knob.scale.set(1 + Math.max(0, -reach) * 0.35);
  }

  async function pullLever() {
    await run(lever, LEVER_MS * 0.45, (k) => setLever(lever, 1 - 1.45 * k), ease.inOut);
    await run(lever, LEVER_MS * 0.55, (k) => setLever(lever, -0.45 + 1.45 * k), ease.back);
  }

  // ---- The lights ----

  function setLights(mode, now) {
    const step = Math.floor(now / (mode === "win" ? CHASE_MS * 0.6 : CHASE_MS));
    const flash = mode === "win" && Math.floor(now / 240) % 2 === 0;
    lights.forEach((bulb, index) => {
      const lit = mode === "rest" || flash || mod(index - step, 3) === 0;
      bulb.off.visible = !lit;
      bulb.on.alpha = mode === "rest" ? 0.35 : lit ? 1 : 0;
    });
  }

  // ---- The player ----

  function showOwner() {
    const me = stage.me();
    plate.text = me ? shortName(stage.nameOf(me)) : "";
  }

  // ---- A pull ----

  // Where each reel lands for this pull, and how fast it spins to get there
  function plan(reel, symbol, landAt) {
    const cruise = landAt - SETTLE_MS * ARRIVE - SPIN_AT;
    const glide = SETTLE_MS / 4.7;
    let target = Math.ceil(reel.pos + MIN_SPEED * (cruise + glide));
    while (STRIP[mod(target, STRIP.length)] !== symbol) {
      target += 1;
    }
    const speed = (target - reel.pos) / (cruise + glide);
    return { start: reel.pos, target, speed, cruise, settleAt: SPIN_AT + cruise };
  }

  function reelAt(route, now) {
    if (now < SPIN_AT) {
      return route.start;
    }
    if (now < route.settleAt) {
      return route.start + route.speed * (now - SPIN_AT);
    }
    const from = route.start + route.speed * route.cruise;
    const k = Math.min(1, (now - route.settleAt) / SETTLE_MS);
    return from + (route.target - from) * ease.back(k);
  }

  async function play(event) {
    if (event.kind !== "pull") {
      return;
    }
    pulls += 1;
    clearTimeout(armed);
    armed = null;
    spinning = true;
    const next = event.win ? ["seven", "seven", "seven"] : dudLine();
    const routes = reels.map((reel, index) => plan(reel, next[index], LANDS[index]));
    const total = LANDS[2] + SETTLE_MS * (1 - ARRIVE);
    const cues = [
      [SPIN_AT, "reel"],
      ...LANDS.map((at) => [at, "stop"]),
    ];
    stage.sound.play("lever");
    pullLever();
    showOdds(event.multiplier);
    try {
      await run(root, total, (k) => {
        const now = k * total;
        while (cues.length && cues[0][0] <= now) {
          stage.sound.play(cues.shift()[1]);
        }
        reels.forEach((reel, index) => reel.spin(reelAt(routes[index], now), now < LANDS[index] - 120));
        setLights("spin", now);
      });
    } finally {
      spinning = false;
    }
    line = next;
    reels.forEach((reel, index) => reel.rest(line[index]));
    if (event.win) {
      jackpot(pulls);
    } else {
      setLights("rest", 0);
      showOdds(null);
    }
  }

  // The win: the display flashes, the lights chase, the 7s pulse and coins burst from the tray. It runs on after
  // play() resolves, and stops early if another pull starts
  async function jackpot(pull) {
    stage.sound.play("coin");
    const bursts = BURSTS.map(([delay, x]) =>
      setTimeout(() => {
        if (pull === pulls && !root.destroyed) {
          sparkle(fountain, x, 0, 1000);
        }
      }, delay),
    );
    await run(root, 1800, (k) => {
      if (pull !== pulls) {
        return;
      }
      const now = k * 1800;
      setLights("win", now);
      const beat = Math.abs(Math.sin(now / 120));
      display.halo.alpha = 0.3 + 0.7 * beat;
      display.odds.tint = beat > 0.5 ? 0xffffff : GOLD_LIGHT;
      display.scale.set(1 + 0.06 * beat);
      reels.forEach((reel) => reel.pulse(1 + 0.12 * Math.abs(Math.sin(now / 160))));
    });
    if (pull === pulls) {
      bursts.forEach(clearTimeout);
      reels.forEach((reel) => reel.pulse(1));
      setLights("rest", 0);
      showOdds(null);
    }
  }

  return {
    show() {
      showOwner();
      if (!spinning) {
        reels.forEach((reel, index) => reel.rest(line[index]));
      }
    },
    play,
    result() {},
    layout(width, height) {
      fit(root, width, height);
    },
    destroy() {
      clearTimeout(armed);
    },
  };
}

// ---- The reels ----

// One reel symbol, drawn about size across. The 7 and BAR are drawn here so their marks stay crisp
function makeSymbol(name, size, art) {
  if (name === "seven") {
    return text("7", {
      fontFamily: FONT,
      fontWeight: "900",
      fontSize: size * 1.05,
      fill: RED,
      stroke: { color: GOLD, width: 8 },
      dropShadow: { color: INK, alpha: 0.5, blur: 4, distance: 4 },
    });
  }
  if (name === "bar") {
    const piece = new Container();
    const width = size;
    const height = size * 0.42;
    const plate = new Graphics()
      .roundRect(-width / 2, -height / 2, width, height, height * 0.28)
      .fill(INK)
      .stroke({ width: 6, color: GOLD })
      .roundRect(-width / 2 + 9, -height / 2 + 9, width - 18, height - 18, height * 0.2)
      .stroke({ width: 2, color: GOLD_LIGHT, alpha: 0.7 });
    const word = text("BAR", { fontFamily: FONT, fontWeight: "900", fontSize: height * 0.62, fill: CREAM, letterSpacing: 3 });
    piece.addChild(plate, word);
    return piece;
  }
  const piece = new Sprite(art[name]);
  piece.anchor.set(0.5);
  piece.scale.set((size * 0.92) / Math.max(piece.texture.width, piece.texture.height));
  return piece;
}

// A reel: a cream drum behind a window, with four slots that scroll down as its position grows. Position p shows
// strip symbol p in the middle of the window
function makeReel([x0, y0, x1, y1], art) {
  const width = x1 - x0;
  const height = y1 - y0;
  const cell = height * 0.6;
  const box = new Container();
  box.position.set(x0 + width / 2, y0 + height / 2);
  const drum = new Graphics().rect(-width / 2 - 8, -height / 2 - 8, width + 16, height + 16).fill(CREAM);
  const strip = new Container();
  const slots = [0, 1, 2, 3].map(() => {
    const slot = new Container();
    slot.symbols = Object.fromEntries(
      SYMBOLS.map((name) => {
        const piece = makeSymbol(name, Math.min(width, cell) * 0.82, art);
        piece.visible = false;
        slot.addChild(piece);
        return [name, piece];
      }),
    );
    strip.addChild(slot);
    return slot;
  });
  // The drum curves away at the top and bottom, so it darkens there
  const shade = new Graphics();
  for (let band = 0; band < 24; band += 1) {
    const depth = (height / 2) * (band / 24);
    const alpha = 0.022 + 0.012 * (band / 24);
    shade.rect(-width / 2 - 8, -height / 2 - 8, width + 16, height / 2 - depth).fill({ color: INK, alpha });
    shade.rect(-width / 2 - 8, depth, width + 16, height / 2 - depth + 8).fill({ color: INK, alpha });
  }
  const payline = new Graphics().rect(-width / 2 - 8, -2, width + 16, 4).fill({ color: RED, alpha: 0.55 });
  const mask = new Graphics().rect(-width / 2 - 8, -height / 2 - 8, width + 16, height + 16).fill(0xffffff);
  box.addChild(drum, strip, shade, payline, mask);
  box.mask = mask;
  const reel = { box, pos: 0 };

  reel.spin = (pos, blurred) => {
    reel.pos = pos;
    const top = Math.floor(pos) - 1;
    slots.forEach((slot, index) => {
      const at = top + index;
      const name = STRIP[mod(at, STRIP.length)];
      for (const [key, piece] of Object.entries(slot.symbols)) {
        piece.visible = key === name;
      }
      slot.y = (pos - at) * cell;
      slot.scale.set(1, blurred ? 1.25 : 1);
      slot.alpha = blurred ? 0.8 : 1;
    });
  };

  // Puts the reel at rest on a symbol, at the strip place nearest where it is now
  reel.rest = (name) => {
    let target = Math.round(reel.pos);
    while (STRIP[mod(target, STRIP.length)] !== name) {
      target += 1;
    }
    reel.spin(target, false);
  };

  reel.pulse = (size) => {
    slots.forEach((slot) => slot.scale.set(slot.y === 0 ? size : 1));
  };
  return reel;
}
