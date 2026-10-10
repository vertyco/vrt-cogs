// The Cups table: three brass cups on a round felt table, one hiding a coin. Players' chips sit in front of the cup
// they picked. A shuffle shows the coin under the middle cup, swaps the cups around, and lifts the coin's cup.
// The scene contract is the comment at the top of the stand-in scene in this folder.
import { Assets, Container, Graphics, Sprite, Text } from "../vendor/pixi.min.mjs";
import { chipStack, coinSprite, loadArt, sparkle } from "./art.js";
import { ease, fit, fitted, tween } from "./kit.js";

const WIDTH = 900;
const HEIGHT = 600;
// The background is bigger than the scene so a letterbox shows more table, not black
const BACKDROP = { width: 1200, height: 800 };
// Where each cup's rim sits on the felt, by cup number
const SLOTS = { 1: 210, 2: 450, 3: 690 };
const RIM_Y = 215;
const CUP_HEIGHT = 145;
const LIFT = 72;
const COIN_SIZE = 64;
const SPOT_Y = 400;
const SPOT_GAP = 58;
// Two players' chips fit in front of each cup; any more fold into a "+N"
const SPOTS_PER_CUP = 2;
const DEALER = { x: 450, y: 90 };
const NAME_LENGTH = 10;
const FONT = '"Playfair Display", Georgia, serif';
const MARKS = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif';
const GOLD = 0xd4af37;
const GOLD_LIGHT = 0xf3d77a;
const CREAM = 0xf6ecd2;
const WIN_SCALE = 1.25;
// Shuffle timing in ms; the whole shuffle stays well inside its 3 second PACE
const SHOW_LIFT = 300;
const SHOW_LOWER = 200;
const SWAPS_TIME = 1750;
const REVEAL_LIFT = 300;

// Runs apply(k) every frame as k goes 0 to 1 over ms; stops when the scene is destroyed
function run(scene, ms, apply, curve = ease.linear) {
  const driver = {
    value: 0,
    get destroyed() {
      return scene.destroyed;
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

function shortName(name) {
  return name.length > NAME_LENGTH ? `${name.slice(0, NAME_LENGTH - 1)}…` : name;
}

function text(value, size, fill, family = FONT) {
  const shadow = { color: 0x000000, alpha: 0.6, blur: 3, distance: 2 };
  const style = { fontFamily: family, fontWeight: "700", fontSize: size, fill, dropShadow: shadow };
  const piece = new Text({ text: value, style });
  piece.anchor.set(0.5);
  return piece;
}

// 5 or 6 swaps of two cups that end with the coin's cup (starting in the middle) at the drawn cup's place
function planSwaps(target) {
  const swaps = [];
  let coin = 2;
  for (let index = 0; index < 5; index += 1) {
    const pair = [1, 2, 3].sort(() => Math.random() - 0.5).slice(0, 2);
    swaps.push(pair);
    coin = pair.includes(coin) ? pair.find((slot) => slot !== coin) : coin;
  }
  if (coin !== target) {
    swaps.push([coin, target]);
  }
  return swaps;
}

function makeCup(textures, number, onTap) {
  const shadow = new Sprite(textures.shadow);
  shadow.anchor.set(0.5);
  const body = new Container();
  const art = new Sprite(textures.cup);
  art.anchor.set(0.5, textures.rim);
  art.scale.set(CUP_HEIGHT / textures.cup.height);
  body.addChild(art);
  body.eventMode = "static";
  body.cursor = "pointer";
  body.on("pointertap", () => onTap(cup.slot));
  const cup = { number, slot: number, body, shadow, width: art.width };
  shadow.width = cup.width * 1.25;
  shadow.height = cup.width * 0.36;
  return cup;
}

// Puts a cup at x with its rim lifted by lift and pushed toward (+) or away from (-) the viewer by depth
function placeCup(cup, x, lift = 0, depth = 0) {
  const grow = 1 + depth * 0.0016;
  cup.body.position.set(x, RIM_Y + depth - lift);
  cup.body.scale.set(grow);
  cup.body.zIndex = depth;
  const fade = 1 - Math.min(1, lift / (LIFT * 1.6));
  cup.shadow.position.set(x, RIM_Y + depth + 2);
  cup.shadow.alpha = 0.85 * fade;
  cup.shadow.width = cup.width * 1.25 * grow * (0.75 + 0.25 * fade);
  cup.shadow.height = cup.width * 0.36 * grow * (0.75 + 0.25 * fade);
}

async function loadTextures() {
  const base = new URL("../art/cups/", import.meta.url).href;
  const [table, cup, shadow] = await Promise.all(
    ["table.jpg", "cup.png", "cup-shadow.png"].map((file) =>
      Assets.load({ src: base + file, data: { autoGenerateMipmaps: true } }),
    ),
  );
  // How far down the cup picture its front rim sits, as a fraction of its height
  return { table, cup, shadow, rim: 0.93 };
}

function numberMark(number, x) {
  const mark = new Container();
  mark.addChild(
    new Graphics().circle(0, 0, 22).fill({ color: 0x000000, alpha: 0.35 }).stroke({ width: 2, color: GOLD }),
    text(String(number), 26, GOLD_LIGHT, MARKS),
  );
  mark.position.set(x, RIM_Y + 44);
  return mark;
}

class CupsScene {
  constructor(stage, textures) {
    this.stage = stage;
    this.state = null;
    this.busy = false;
    this.root = fitted(WIDTH, HEIGHT);
    this.backdrop = new Sprite(textures.table);
    this.backdrop.anchor.set(0.5);
    this.backdrop.position.set(WIDTH / 2, HEIGHT / 2);
    const shadows = new Container();
    this.coin = coinSprite("heads");
    this.coin.scale.set(COIN_SIZE / 80, (COIN_SIZE / 80) * 0.45);
    const numbers = new Container();
    numbers.addChild(...Object.entries(SLOTS).map(([number, x]) => numberMark(number, x)));
    const cupsLayer = new Container();
    cupsLayer.sortableChildren = true;
    this.cups = [1, 2, 3].map((number) => makeCup(textures, number, (slot) => this.tap(slot)));
    for (const cup of this.cups) {
      shadows.addChild(cup.shadow);
      cupsLayer.addChild(cup.body);
    }
    this.spots = new Container();
    this.effects = new Container();
    this.root.addChild(this.backdrop, shadows, this.coin, numbers, cupsLayer, this.spots, this.effects);
    stage.root.addChild(this.root);
    this.poseCups(null);
  }

  // A cup picks the player's call while bets are open
  tap(slot) {
    if (!this.busy && (!this.state || ["idle", "betting"].includes(this.state.phase))) {
      this.stage.actions.choose(slot);
    }
  }

  // Every cup back in its own place, the one over the coin lifted when revealed
  poseCups(revealed) {
    for (const cup of this.cups) {
      cup.slot = cup.number;
      placeCup(cup, SLOTS[cup.number], revealed === cup.number ? LIFT : 0);
    }
    this.coin.visible = Boolean(revealed);
    this.coin.position.set(SLOTS[revealed || 2], RIM_Y - 12);
  }

  spotFor(player, x, final) {
    const spot = new Container();
    spot.position.set(x, SPOT_Y);
    // The viewer's own spot gets a gold ring, which leaves with their chips if they lose
    const ring = new Graphics().ellipse(0, 6, 44, 18).stroke({ width: 3, color: GOLD_LIGHT });
    ring.visible = String(player.id) === String(this.stage.me());
    const stack = chipStack(player.bet);
    const caption = text(shortName(this.stage.nameOf(player.id) || player.name || ""), 20, CREAM);
    caption.position.set(0, 44);
    spot.addChild(ring, stack, caption);
    Object.assign(spot, { ring, stack, caption, player });
    if (final && player.outcome === "win") {
      stack.scale.set(WIN_SCALE);
    } else if (final && player.outcome) {
      for (const piece of [ring, stack, caption]) {
        piece.alpha = 0;
      }
    }
    return spot;
  }

  // Each betting player's chips and name in front of the cup they picked, the viewer first
  drawSpots(players, final) {
    this.spots.removeChildren().forEach((child) => child.destroy({ children: true }));
    const me = String(this.stage.me());
    const made = [];
    for (const number of [1, 2, 3]) {
      const here = players.filter((player) => player.bet && player.choice === number);
      here.sort((a, b) => (String(b.id) === me) - (String(a.id) === me));
      const shown = here.slice(0, SPOTS_PER_CUP);
      shown.forEach((player, index) => {
        const offset = shown.length === 1 ? 0 : (index - 0.5) * 2 * SPOT_GAP;
        made.push(this.spots.addChild(this.spotFor(player, SLOTS[number] + offset, final)));
      });
      if (here.length > shown.length) {
        const more = text(`+${here.length - shown.length}`, 20, GOLD_LIGHT, MARKS);
        more.position.set(SLOTS[number], SPOT_Y + 72);
        this.spots.addChild(more);
      }
    }
    return made;
  }

  // The results flourish: winners' chips grow with a sparkle; losers' chips, names and rings slide off and fade
  flourish(made) {
    for (const { ring, stack, caption, player, x, y } of made) {
      if (player.outcome === "win") {
        tween(stack, { scale: WIN_SCALE }, 450, ease.back);
        sparkle(this.effects, x, y - 20, 900);
      } else if (player.outcome) {
        tween(stack, { x: (DEALER.x - x) * 0.5, y: (DEALER.y - y) * 0.5, alpha: 0 }, 700, ease.inOut);
        tween(caption, { alpha: 0 }, 700);
        tween(ring, { alpha: 0 }, 700);
      }
    }
  }

  lift(cup, from, to, ms) {
    return run(this.root, ms, (k) => placeCup(cup, SLOTS[cup.slot], from + (to - from) * k), ease.out);
  }

  // Two cups trade places along curved paths, one passing in front and one behind
  async swap([first, second], ms) {
    const one = this.cups.find((cup) => cup.slot === first);
    const two = this.cups.find((cup) => cup.slot === second);
    const reach = 30 + 14 * Math.abs(first - second);
    this.stage.sound.play("cups");
    await run(this.root, ms, (k) => {
      const glide = ease.inOut(k);
      const arc = Math.sin(Math.PI * k) * reach;
      placeCup(one, SLOTS[first] + (SLOTS[second] - SLOTS[first]) * glide, 0, arc);
      placeCup(two, SLOTS[second] + (SLOTS[first] - SLOTS[second]) * glide, 0, -arc);
    });
    one.slot = second;
    two.slot = first;
  }

  async shuffle(event) {
    const middle = this.cups.find((cup) => cup.slot === 2);
    this.coin.position.set(SLOTS[2], RIM_Y - 12);
    this.coin.visible = true;
    await this.lift(middle, 0, LIFT, SHOW_LIFT);
    await this.lift(middle, LIFT, 0, SHOW_LOWER);
    this.coin.visible = false;
    const swaps = planSwaps(event.cup);
    for (const pair of swaps) {
      await this.swap(pair, SWAPS_TIME / swaps.length);
    }
    const winner = this.cups.find((cup) => cup.slot === event.cup);
    this.coin.position.set(SLOTS[event.cup], RIM_Y - 12);
    this.coin.visible = true;
    this.stage.sound.play("land");
    await this.lift(winner, 0, LIFT, REVEAL_LIFT);
  }

  show(next) {
    const previous = this.state;
    this.state = next;
    const final = next.phase === "results";
    // Only the first results update of a round that was seen playing animates; any other draws the end state
    const fresh = final && previous && previous.round === next.round && previous.phase !== "results";
    const made = this.drawSpots(next.players || [], final && !fresh);
    if (!this.busy) {
      this.poseCups(final && next.drawn ? next.drawn.cup : null);
    }
    if (fresh) {
      this.flourish(made);
    }
  }

  async play(event) {
    if (event.kind !== "shuffle") {
      return;
    }
    this.busy = true;
    try {
      await this.shuffle(event);
    } finally {
      this.busy = false;
    }
  }

  layout(width, height) {
    fit(this.root, width, height);
    // The table covers the whole space, however tall or wide, so the letterbox never shows bare page
    const scale = this.root.scale.x;
    const cover = Math.max(1, width / scale / BACKDROP.width, height / scale / BACKDROP.height);
    this.backdrop.width = BACKDROP.width * cover;
    this.backdrop.height = BACKDROP.height * cover;
  }

  destroy() {}
}

export async function createScene(stage) {
  const [textures] = await Promise.all([loadTextures(), loadArt()]);
  return new CupsScene(stage, textures);
}
