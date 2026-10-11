// The plot rooms and the Pond. A plot is for sale until bought, then holds crops (9 spots) or animals (a pen), and an
// empty one can switch between the two for a fee. The tool in hand decides what a tap on a spot does: the hoe tills
// (asking before it digs up a crop), the can waters, a seed is planted, and the hand harvests a ripe crop or says what
// grows there. At the Pond the watering can fills up.
import { Container, Graphics } from "./vendor/pixi.min.mjs";
import * as pen from "./pen.js";
import { FIELD, spotCenter } from "./rooms.js";

// The soil pictures are a little smaller than a spot, so they are drawn bigger to meet like FarmVille's field
const SPOT_SCALE = 1.2;
// How far above its soil a standing crop can still be tapped, and how wide that is
const PLANT = { height: 90, halfWidth: 50 };
// The farmer works a spot from just in front of its middle
const WORK_OFFSET = 20;
// Watered soil, and the crop on it, look darker and a little blue
const WET_TINT = 0xb3c3e6;
const STAGE_ART = ["seed", "sprout", "growing"];
const STAGE_WORDS = ["just planted", "sprouting", "growing"];
const SPOIL = {
  fresh: { art: "ripe", words: "ripe", next: "dries" },
  dried: { art: "dried", words: "dried out", next: "withers" },
  withered: { art: "withered", words: "withered", next: "rots" },
};
// Sparkles over a ripe crop: where each sits from the spot's middle, and its size
const SPARKLES = [
  { x: -30, y: -60, size: 9 },
  { x: 26, y: -78, size: 7 },
  { x: 8, y: -40, size: 6 },
];
// The Pond's water as a tap sees it, and where the farmer stands to fill the can
const POND = { x: 640, y: 440, rx: 200, ry: 110, stand: { x: 640, y: 585 } };

const view = {
  plot: 0,
  // What the plot holds as drawn: "locked", "crops" or "animals". When that changes the plot is drawn anew
  shape: null,
  // What the field or the sale sign drew, each with the remover of its tap target
  parts: [],
  sparkles: [],
  time: 0,
};

function $(id) {
  return document.getElementById(id);
}

function currentPlot(ctx) {
  return ctx.state().plots.find((plot) => plot.number === view.plot);
}

function shapeOf(plot) {
  return plot.unlocked ? plot.kind : "locked";
}

function cropWord(ctx, key) {
  return ctx.hud.catalogEntry(ctx.catalog().crops, key).name;
}

// ---------- The view ----------

function enter(ctx, room) {
  // The scene was emptied, so nothing drawn before is left to take down
  view.plot = room.plot;
  view.shape = null;
  view.parts = [];
  view.sparkles = [];
  pen.forget();
  ctx.scene.everyFrame((dt) => {
    view.time += dt;
    twinkle();
    pen.step(dt);
  });
  draw(ctx);
}

function draw(ctx) {
  const plot = currentPlot(ctx);
  const shape = shapeOf(plot);
  if (shape !== view.shape) {
    pen.takeDown();
    view.shape = shape;
  }
  takeDown();
  if (shape === "animals") {
    pen.show(ctx, plot);
  } else if (shape === "crops") {
    drawField(ctx, plot);
  } else {
    drawSaleSign(ctx);
  }
  showCard(ctx, plot);
  showSwitch(ctx, plot);
}

function leave() {
  $("plot-card").hidden = true;
  $("plot-switch").hidden = true;
}

function takeDown() {
  for (const { node, remove } of view.parts) {
    remove?.();
    node.destroy({ children: true });
  }
  view.parts = [];
  view.sparkles = [];
}

export const plotView = { enter, update: draw, leave };

// ---------- A crop field ----------

// The picture for a spot: bare or tilled soil, a crop at its stage, how far a ripe one spoiled, or a rotted one
function spotArt(spot) {
  if (spot.state === "untilled" || spot.state === "tilled") {
    return `soil/${spot.state}`;
  }
  if (spot.state === "rotted") {
    return "crop/rotted";
  }
  if (spot.stage === 3) {
    return `crop/${spot.crop}/${SPOIL[spot.spoil].art}`;
  }
  // A bush that has given a harvest starts its next round as a sprout, not a seed
  const stage = spot.stage === 0 && spot.cycle > 0 ? 1 : spot.stage;
  return `crop/${spot.crop}/${STAGE_ART[stage]}`;
}

function harvestable(spot) {
  return spot.state === "growing" && spot.stage === 3;
}

function sparkle(size) {
  const star = new Graphics()
    .star(0, 0, 4, size, size * 0.35)
    .fill(0xfff6c2)
    .stroke({ width: 1.5, color: 0xffc81e });
  star.label = "sparkle";
  return star;
}

function spotNode(ctx, spot) {
  const node = new Container();
  node.label = `spot:${spot.index}`;
  const picture = ctx.scene.sprite(spotArt(spot), 0, 0);
  picture.label = "crop";
  picture.scale.set(SPOT_SCALE);
  if (spot.watered) {
    picture.tint = WET_TINT;
  }
  node.addChild(picture);
  if (harvestable(spot)) {
    for (const [i, place] of SPARKLES.entries()) {
      const star = sparkle(place.size);
      star.position.set(place.x, place.y);
      node.addChild(star);
      view.sparkles.push({ star, phase: i * 2.1 });
    }
  }
  return node;
}

function onSoil(point, index) {
  const center = spotCenter(index);
  return (
    Math.abs(point.x - center.x) / (FIELD.spotWidth / 2) + Math.abs(point.y - center.y) / (FIELD.spotHeight / 2) <= 1
  );
}

// A tap on one of a field's `count` spots: its soil, or the plant standing on it. Plants reach up over the soil of
// the spots behind them, so a tap on any spot's soil is that spot's, and a plant only takes taps that miss all the soil
function hitsSpot(point, index, standing, count) {
  const soil = [...Array(count).keys()].find((other) => onSoil(point, other));
  if (soil !== undefined) {
    return soil === index;
  }
  const center = spotCenter(index);
  const dy = point.y - center.y;
  return standing && Math.abs(point.x - center.x) <= PLANT.halfWidth && dy <= 0 && dy >= -PLANT.height;
}

function drawField(ctx, plot) {
  for (const spot of plot.spots) {
    const center = spotCenter(spot.index);
    const node = spotNode(ctx, spot);
    node.position.set(center.x, center.y);
    node.zIndex = center.y;
    ctx.scene.things.addChild(node);
    const remove = ctx.scene.addTarget(node, {
      walkTo: { x: center.x, y: center.y + WORK_OFFSET },
      hit: (point) => hitsSpot(point, spot.index, spot.state === "growing", plot.spots.length),
      onTap: ctx.safe("tapping a spot", () => useOnSpot(ctx, spot.index)),
    });
    view.parts.push({ node, remove });
  }
}

function twinkle() {
  for (const { star, phase } of view.sparkles) {
    const wave = Math.sin(view.time * 3.2 + phase);
    star.alpha = 0.55 + 0.45 * wave;
    star.scale.set(0.75 + 0.3 * wave);
    star.rotation = view.time * 0.6 + phase;
  }
}

// What the hand finds on a spot, and the time left until it changes
function describe(ctx, spot) {
  const { duration } = ctx.hud;
  if (spot.state === "untilled") {
    return "Untilled ground. Till it with the hoe.";
  }
  if (spot.state === "tilled") {
    return "Tilled soil, ready for a seed.";
  }
  const name = cropWord(ctx, spot.crop);
  if (spot.state === "rotted") {
    return `The ${name.toLowerCase()} rotted. Clear it with the hoe.`;
  }
  if (spot.stage === 3) {
    const spoil = SPOIL[spot.spoil];
    const left = duration(spot.spoil_ends_at - ctx.now());
    return `${name}: ${spoil.words}! Harvest it with the hand. It ${spoil.next} in ${left}.`;
  }
  const water = spot.watered ? "Watered for this stage." : "Needs water.";
  const dry = spot.dry ? ` ${spot.dry} dry stage${spot.dry === 1 ? "" : "s"} so far.` : "";
  const stage = spot.stage === 0 && spot.cycle > 0 ? "growing back" : STAGE_WORDS[spot.stage];
  return `${name}: ${stage}, ripe in ${duration(spot.ripe_at - ctx.now())}. ${water}${dry}`;
}

// The farmer reached a spot: the tool in hand works on it. A tool that does nothing here shows what it is instead
function useOnSpot(ctx, index) {
  const plot = currentPlot(ctx);
  if (!plot || shapeOf(plot) !== "crops") {
    return;
  }
  const spot = plot.spots[index];
  const tool = ctx.tool();
  const where = { plot: plot.number, spot: index };
  // One request per spot at a time, so a double tap never plants or waters twice
  const key = `plot${plot.number}:${index}`;
  if (tool.name === "hoe") {
    return hoe(ctx, spot, where, key);
  }
  if (tool.name === "can") {
    return ctx.act("water", where, { key });
  }
  if (tool.name === "seed") {
    return ctx.act("plant", { ...where, crop: tool.item.slice("seed:".length) }, { key });
  }
  if (tool.name === "hand" && spot.state === "growing" && ctx.now() >= spot.ripe_at) {
    return harvest(ctx, where, key);
  }
  ctx.sound.play("tap");
  ctx.hud.toast(describe(ctx, spot));
}

// The hoe tills bare ground and clears a rotted crop. A living crop is only dug up once the player says so
async function hoe(ctx, spot, where, key) {
  if (spot.state === "rotted") {
    return ctx.act("till", where, { key, sound: "clear" });
  }
  if (spot.state !== "growing") {
    return ctx.act("till", where, { key });
  }
  if (ctx.busy(key)) {
    return null;
  }
  const crop = cropWord(ctx, spot.crop).toLowerCase();
  if (await ctx.hud.confirmBox(`Dig up the ${crop}?`, "Dig it up", "Keep it")) {
    return ctx.act("till", { ...where, dig: true }, { key, sound: "clear" });
  }
  return null;
}

async function harvest(ctx, where, key) {
  const reply = await ctx.act("harvest", where, { key });
  if (reply) {
    harvestPopup(ctx, reply.result);
  }
}

// What the harvest brought: how many, whether exceptional, any free seeds, and the XP
function harvestPopup(ctx, result) {
  const { make } = ctx.hud;
  const name = cropWord(ctx, result.crop);
  const item = result.exceptional ? `crop:${result.crop}:x` : `crop:${result.crop}`;
  const lines = make("span", "lines");
  lines.append(make("b", "", `+${result.amount} ${result.exceptional ? "exceptional " : ""}${name}`));
  if (result.exceptional) {
    lines.append(make("span", "", "Exceptional! Worth double"));
  }
  if (result.seeds) {
    lines.append(make("span", "", `+${result.seeds} free seed${result.seeds === 1 ? "" : "s"}`));
  }
  lines.append(make("span", "", `+${ctx.hud.number(result.xp)} XP`));
  const box = make("span", "reward");
  box.append(ctx.hud.icon(`icon/${item}`, 44), lines);
  ctx.hud.toast(box, result.exceptional ? "harvest exceptional" : "harvest");
  if (result.exceptional) {
    ctx.sound.play("exceptional");
  }
}

// ---------- A plot for sale ----------

function drawSaleSign(ctx) {
  const node = ctx.scene.sprite("scene/sign", FIELD.x, FIELD.y + 40);
  ctx.scene.things.addChild(node);
  view.parts.push({ node, remove: null });
}

// The plot's level and price over the field, with the Unlock button
function showCard(ctx, plot) {
  const card = $("plot-card");
  card.hidden = plot.unlocked;
  if (plot.unlocked) {
    return;
  }
  const { make } = ctx.hud;
  const info = ctx.catalog().plots.find((entry) => entry.number === plot.number);
  const { level, coins } = ctx.state().player;
  const facts = make("p", "plot-needs");
  facts.append(make("span", level >= info.level ? "met" : "unmet", `Level ${info.level}`), ctx.hud.price(info.price));
  const button = make("button", "button primary", "Unlock");
  button.type = "button";
  button.id = "plot-unlock";
  let missing = "";
  if (level < info.level) {
    missing = `Opens at level ${info.level}`;
  } else if (coins < info.price) {
    missing = "Not enough FarmCoins";
  }
  button.disabled = Boolean(missing);
  button.addEventListener("click", ctx.safe("the Unlock button", () => chooseKind(ctx, plot.number, info.price)));
  card.replaceChildren(make("h2", "", `Plot ${plot.number}`), make("p", "dim plot-sale", "For sale"), facts, button);
  if (missing) {
    card.append(make("p", "dim plot-missing", missing));
  }
}

function kindChoice(ctx, kind, picture, name, words) {
  const { make } = ctx.hud;
  const button = make("button", "kind-choice");
  button.type = "button";
  button.dataset.kind = kind;
  const text = make("span", "words");
  text.append(make("b", "", name), make("small", "", words));
  button.append(ctx.hud.icon(picture, 56), text);
  return button;
}

// After Unlock, the player picks what the plot holds. That first pick is free
function chooseKind(ctx, number, cost) {
  const body = ctx.hud.openPanel(`What will Plot ${number} hold?`);
  const { make } = ctx.hud;
  const { spots, pen_size: penSize } = ctx.catalog().constants;
  const note = make("p", "dim", "Unlocking costs ");
  note.append(ctx.hud.price(cost), ". Switching later costs a fee.");
  const choices = [
    kindChoice(ctx, "crops", "crop/wheat/ripe", "Crops", `${spots} spots to grow crops on`),
    kindChoice(ctx, "animals", "animal/chicken/adult/female/0", "Animals", `A pen for up to ${penSize} animals`),
  ];
  for (const button of choices) {
    const unlock = async () => {
      choices.forEach((other) => (other.disabled = true));
      const reply = await ctx.actButton(button, "unlock_plot", { plot: number, kind: button.dataset.kind });
      choices.forEach((other) => (other.disabled = false));
      if (reply) {
        ctx.hud.closePanel();
      }
    };
    button.addEventListener("click", ctx.safe("the crops or animals choice", unlock));
  }
  const list = make("div", "kind-choices");
  list.append(...choices);
  body.append(note, list);
}

// ---------- Switching between crops and animals ----------

// An empty plot's button to turn it into the other kind, with the fee
function showSwitch(ctx, plot) {
  const button = $("plot-switch");
  const offer = plot.switch;
  button.hidden = !offer;
  if (!offer) {
    return;
  }
  const words = offer.kind === "animals" ? "Make it a pen" : "Make it a crop plot";
  const fee = offer.fee ? ctx.hud.price(offer.fee) : ctx.hud.make("b", "", "Free");
  button.replaceChildren(ctx.hud.make("span", "", words), fee);
  button.onclick = ctx.safe("the switch button", () => switchPlot(ctx, button));
}

async function switchPlot(ctx, button) {
  const plot = currentPlot(ctx);
  const offer = plot?.switch;
  if (!offer || ctx.busy("switch_plot")) {
    return;
  }
  const into = offer.kind === "animals" ? "a pen" : "a crop plot";
  const cost = offer.fee ? `for ${ctx.hud.number(offer.fee)} FarmCoins` : "for free";
  if (await ctx.hud.confirmBox(`Turn Plot ${plot.number} into ${into} ${cost}?`, "Switch", "Cancel")) {
    await ctx.actButton(button, "switch_plot", { plot: plot.number, kind: offer.kind });
  }
}

// ---------- The Pond ----------

function enterPond(ctx) {
  // The pond's picture belongs to the room's scenery, so an invisible shape over its water takes the taps
  const water = new Graphics().ellipse(0, 0, POND.rx, POND.ry).fill({ color: 0xffffff, alpha: 0 });
  water.label = "pond";
  water.position.set(POND.x, POND.y);
  water.zIndex = POND.y;
  ctx.scene.things.addChild(water);
  ctx.scene.addTarget(water, {
    walkTo: POND.stand,
    hit: (point) => ((point.x - POND.x) / POND.rx) ** 2 + ((point.y - POND.y) / POND.ry) ** 2 <= 1,
    onTap: ctx.safe("tapping the Pond", () => {
      if (ctx.tool().name === "can") {
        return ctx.act("refill");
      }
      ctx.sound.play("tap");
      ctx.hud.toast("The Pond. Tap it with the watering can to fill the can.");
      return null;
    }),
  });
}

export const pondView = { enter: enterPond };
