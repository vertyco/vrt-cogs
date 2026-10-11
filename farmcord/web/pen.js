// A pen's animals. Each one wanders the fenced field, baby or grown up, with a mark for male or female and one for
// sickly or malnourished. Feed and the watering can work on the animal tapped; any other tool opens its panel, which
// tells how it is doing and lets a female who can try for babies breed, or gives the bot's reason she can't.
import { Container, Graphics, Sprite } from "./vendor/pixi.min.mjs";
import { FIELD } from "./rooms.js";

// Where animals roam: the fenced diamond, shrunk so the biggest stay clear of the fence
const ROAM = { x: FIELD.x, y: FIELD.y + 10, width: FIELD.fenceWidth * 0.36, height: FIELD.fenceHeight * 0.36 };
// Where each animal first stands, in the order the bot lists them: three staggered rows of two, so that not even a
// grown cow or horse stands in front of another animal's body
const PLACES = [
  { x: 560, y: 440 },
  { x: 720, y: 440 },
  { x: 480, y: 505 },
  { x: 800, y: 505 },
  { x: 590, y: 575 },
  { x: 690, y: 575 },
];
// Room pixels a second
const SPEED = 40;
// Seconds an animal stands about between strolls: at least the first, up to both
const REST = [1.5, 5];
// The feed and water troughs at the back of the pen
const TROUGHS = [
  { art: "scene/trough_feed", x: 545, y: 400 },
  { art: "scene/trough_water", x: 735, y: 400 },
];
const MARK_RADIUS = 11;
// The smallest a tap on an animal can be off its middle and still count, in room pixels, so a chick is as easy to tap
// as a cow
const TAP_RADIUS = 22;
const SEX_COLORS = { male: 0x3d7fd1, female: 0xd9568f };
const CONDITION_COLORS = { sickly: 0xe39b1b, malnourished: 0xc8352a };
const CONDITION_WORDS = {
  healthy: "Healthy",
  sickly: "Sickly: worth 75% until healthy again",
  malnourished: "Malnourished: worth 25%, for good",
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const pen = {
  // The animals drawn, by id
  animals: new Map(),
  troughs: [],
  // The panel's contents while it shows an animal, and that animal's id
  panel: null,
  panelId: null,
};

function randomIn(low, high) {
  return low + Math.random() * (high - low);
}

// A random point of the roaming diamond
function roamPoint() {
  const across = randomIn(-1, 1);
  const down = randomIn(-1, 1) * (1 - Math.abs(across));
  return { x: ROAM.x + across * ROAM.width, y: ROAM.y + down * ROAM.height };
}

// The picture set for an animal. Chickens and cows have a look for each sex once grown; the others share one
function artKey(art, row) {
  if (!row.adult) {
    return `animal/${row.kind}/baby`;
  }
  const sexed = `animal/${row.kind}/adult/${row.sex}`;
  return art.animation(sexed) ? sexed : `animal/${row.kind}/adult`;
}

function sexMark(sex) {
  const mark = new Graphics().circle(0, 0, MARK_RADIUS).fill(SEX_COLORS[sex]).stroke({ width: 2, color: 0xffffff });
  const line = { width: 2.2, color: 0xffffff, cap: "round" };
  if (sex === "male") {
    mark.circle(-2, 2, 4).moveTo(1, -1).lineTo(5, -5).moveTo(1.5, -5).lineTo(5, -5).lineTo(5, -1.5).stroke(line);
  } else {
    mark.circle(0, -2.5, 4).moveTo(0, 1.5).lineTo(0, 7).moveTo(-2.8, 4.5).lineTo(2.8, 4.5).stroke(line);
  }
  return mark;
}

// A round "!" over an animal that is sickly or malnourished
function conditionMark(condition) {
  return new Graphics()
    .circle(0, 0, MARK_RADIUS)
    .fill(CONDITION_COLORS[condition])
    .stroke({ width: 2, color: 0xffffff })
    .roundRect(-1.6, -7, 3.2, 9, 1.6)
    .circle(0, 5, 1.8)
    .fill(0xffffff);
}

// One animal in the pen, strolling about and standing still in turns
class PenAnimal {
  constructor(art, row, place) {
    this.art = art;
    this.node = new Container();
    this.node.label = `animal:${row.id}`;
    this.sprite = new Sprite();
    this.marks = new Container();
    this.node.addChild(this.sprite, this.marks);
    this.key = null;
    this.time = 0;
    this.goal = null;
    this.rest = randomIn(0, REST[1]);
    this.facing = "front";
    this.mirrored = Math.random() < 0.5;
    // Takes away its tap target; set once it is in the scene
    this.remove = () => {};
    this.moveTo(place.x, place.y);
    this.dress(row);
  }

  moveTo(x, y) {
    this.node.position.set(x, y);
    this.node.zIndex = y;
  }

  // Whether a tap lands on its body: an ellipse over its picture from just above its feet to its top. Not the whole
  // picture, whose empty corners would let a big animal take the taps meant for a small one behind it
  hits(point) {
    const { size, anchor } = this.animation;
    const top = size.h * anchor.y;
    const middle = (0.5 - anchor.x) * size.w * (this.mirrored ? -1 : 1);
    const across = (point.x - (this.node.x + middle)) / Math.max(size.w * 0.3, TAP_RADIUS);
    const down = (point.y - (this.node.y - top / 2)) / Math.max(top * 0.45, TAP_RADIUS);
    return across * across + down * down <= 1;
  }

  // Its look for the state's row: baby or grown, and its marks
  dress(row) {
    const key = artKey(this.art, row);
    if (key !== this.key) {
      this.key = key;
      this.animation = this.art.animation(key);
      this.sprite.anchor.set(this.animation.anchor.x, this.animation.anchor.y);
      this.time = 0;
    }
    const marks = [sexMark(row.sex)];
    if (row.condition !== "healthy") {
      marks.push(conditionMark(row.condition));
    }
    this.marks.removeChildren().forEach((mark) => mark.destroy());
    const top = -this.animation.size.h * this.animation.anchor.y - MARK_RADIUS;
    marks.forEach((mark, i) => {
      mark.position.set((i - (marks.length - 1) / 2) * (MARK_RADIUS * 2 + 4), top);
      this.marks.addChild(mark);
    });
    this.draw();
  }

  step(dt) {
    this.time += dt;
    if (reducedMotion.matches) {
      this.goal = null;
    } else if (this.goal) {
      this.walk(dt);
    } else {
      this.rest -= dt;
      if (this.rest <= 0) {
        this.goal = roamPoint();
        this.face(this.goal.x - this.node.x, this.goal.y - this.node.y);
      }
    }
    this.draw();
  }

  walk(dt) {
    const dx = this.goal.x - this.node.x;
    const dy = this.goal.y - this.node.y;
    const distance = Math.hypot(dx, dy);
    const reach = SPEED * dt;
    if (distance <= reach) {
      this.moveTo(this.goal.x, this.goal.y);
      this.goal = null;
      this.rest = randomIn(...REST);
      return;
    }
    this.moveTo(this.node.x + (dx / distance) * reach, this.node.y + (dy / distance) * reach);
  }

  // FarmVille draws an animal's front facing down and to the right, and its back facing up and to the left
  face(dx, dy) {
    this.facing = dy < -Math.abs(dx) * 0.3 ? "back" : "front";
    this.time = 0;
  }

  // The clip to play: some animals have no walk (play the idle) or no back (play the front)
  clip() {
    const clips = this.animation.clips;
    const side = clips[`idle_${this.facing}`] ? this.facing : "front";
    const walk = clips[`walk_${side}`];
    return { side, clip: this.goal && walk ? walk : clips[`idle_${side}`] };
  }

  draw() {
    const { side, clip } = this.clip();
    if (this.goal) {
      const dx = this.goal.x - this.node.x;
      if (Math.abs(dx) > 1) {
        this.mirrored = side === "back" ? dx > 0 : dx < 0;
      }
    }
    const frame = clip.start + (Math.floor(this.time * clip.fps) % clip.count);
    this.sprite.texture = this.art.texture(`${this.key}/${frame}`);
    this.sprite.scale.x = this.mirrored ? -1 : 1;
  }
}

// ---------- Drawing the pen ----------

// The room was drawn again from scratch, so what the pen drew is already gone
export function forget() {
  pen.animals.clear();
  pen.troughs = [];
}

// Takes down everything the pen drew, when the plot stops being a pen
export function takeDown() {
  for (const animal of pen.animals.values()) {
    animal.remove();
    animal.node.destroy({ children: true });
  }
  pen.troughs.forEach((node) => node.destroy());
  forget();
}

// Draws the pen for the plot's row in the state: its troughs once, then its animals as the state has them now
export function show(ctx, plot) {
  const scene = ctx.scene;
  if (!pen.troughs.length) {
    pen.troughs = TROUGHS.map(({ art, x, y }) => scene.things.addChild(scene.sprite(art, x, y)));
  }
  const rows = ctx.state().animals.filter((row) => row.plot === plot.number);
  const ids = new Set(rows.map((row) => row.id));
  for (const [id, animal] of pen.animals) {
    if (!ids.has(id)) {
      animal.remove();
      animal.node.destroy({ children: true });
      pen.animals.delete(id);
    }
  }
  rows.forEach((row, i) => {
    let animal = pen.animals.get(row.id);
    if (!animal) {
      animal = new PenAnimal(scene.art, row, PLACES[i % PLACES.length]);
      scene.things.addChild(animal.node);
      const onTap = ctx.safe("tapping an animal", () => useOn(ctx, row.id));
      animal.remove = scene.addTarget(animal.node, { onTap, hit: (point) => animal.hits(point) });
      pen.animals.set(row.id, animal);
    }
    animal.dress(row);
  });
  // The animal's panel, if it is still open, shows the new state
  if (pen.panel?.isConnected && pen.panel.closest("dialog").open) {
    fillPanel(ctx);
  }
}

export function step(dt) {
  for (const animal of pen.animals.values()) {
    animal.step(dt);
  }
}

// ---------- Tapping an animal ----------

function find(ctx, id) {
  return ctx.state().animals.find((row) => row.id === id);
}

function useOn(ctx, id) {
  const row = find(ctx, id);
  if (!row) {
    return;
  }
  const tool = ctx.tool();
  // One request per animal at a time, so a double tap never feeds twice
  const key = `animal:${id}`;
  if (tool.name === "feed") {
    return ctx.act("feed", { animal: id, item: tool.item }, { key });
  }
  if (tool.name === "can") {
    return ctx.act("water_animal", { animal: id }, { key });
  }
  ctx.sound.play(row.kind);
  pen.panelId = id;
  fillPanel(ctx);
}

function animalName(ctx, row) {
  return ctx.catalog().animals.find((animal) => animal.key === row.kind).name;
}

// "Next meal due in 5 h", or that it missed one
function needLine(ctx, by, due, missed) {
  const left = by - ctx.now();
  return left > 0 ? `${due} ${ctx.hud.duration(left)}` : missed;
}

function facts(ctx, row) {
  const { duration } = ctx.hud;
  const grownUp = row.adult ? "grown up" : `baby, grows up in ${duration(row.grows_up_at - ctx.now())}`;
  const lines = [`${row.sex === "male" ? "Male" : "Female"}, ${grownUp}`];
  if (row.exceptional) {
    lines.push("Exceptional: worth double");
  }
  lines.push(CONDITION_WORDS[row.condition]);
  lines.push(needLine(ctx, row.feed_by, "Next meal due in", "Hungry! It missed a meal"));
  lines.push(needLine(ctx, row.water_by, "Next drink due in", "Thirsty! It missed a drink"));
  if (row.price !== null) {
    lines.push(`Sells for ${ctx.hud.number(row.price)} FarmCoins`);
  }
  if (row.expecting_until) {
    lines.push(`Babies coming in ${duration(row.expecting_until - ctx.now())}`);
  }
  return lines;
}

// The Breed button, or why she can't try for babies now in the bot's own words
function breedPart(ctx, row) {
  const { make } = ctx.hud;
  if (!row.can_breed) {
    return make("p", "breed-note", row.breed_refusal);
  }
  const button = make("button", "button primary", "Breed");
  button.type = "button";
  button.id = "breed";
  button.addEventListener("click", ctx.safe("the Breed button", () => breed(ctx, button, row)));
  return button;
}

async function breed(ctx, button, row) {
  const reply = await ctx.actButton(button, "breed", { animal: row.id }, { key: `animal:${row.id}`, sound: row.kind });
  if (!reply) {
    return;
  }
  const { result } = reply;
  if (result.success) {
    ctx.hud.toast(`She's expecting! Babies come in ${ctx.hud.duration(result.due - ctx.now())}.`);
  } else {
    ctx.hud.toast(result.message);
  }
}

// The panel for the animal last tapped, filled again as new states arrive. It closes when that animal is gone
function fillPanel(ctx) {
  const row = find(ctx, pen.panelId);
  if (!row) {
    pen.panel = null;
    ctx.hud.closePanel();
    return;
  }
  const name = animalName(ctx, row);
  const body = ctx.hud.openPanel(row.adult ? name : `Baby ${name.toLowerCase()}`);
  const { make } = ctx.hud;
  pen.panel = make("div", "animal-panel");
  const list = make("ul", "animal-facts");
  list.append(...facts(ctx, row).map((line) => make("li", "", line)));
  pen.panel.append(list);
  if (row.sex === "female" && row.adult) {
    pen.panel.append(breedPart(ctx, row));
  }
  body.append(pen.panel);
}
