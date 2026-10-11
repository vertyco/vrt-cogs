// The original's battle screen (root frame 5, frame_5/DoAction.as). The bot runs the battle, and this page draws it the
// way the original did: the arena, each robot's top in its team's color with its gun, name and health bar, shots with
// their sparks, streaks and ricochets, explosions and burning wrecks, the countdown and the end banners.
//
// The drawing runs a moment behind the bot's updates, on its own battle clock, so robots slide from one update to the
// next instead of jumping, and each shot and wreck shows on the step the bot says it happened. A drag from one of your
// robots sends the bot an order. Nothing here decides a hit, a death or a winner.
import { FPS, makeFilter, TextField } from "./flash.js";
import { Container, Rectangle } from "./vendor/pixi.min.mjs";

// The bot's numbers. It runs STEPS steps between updates, and its robots start moving on MOVE_AT, the countdown's GO
// frame. After the result the banner plays for BANNER_STEPS, then the screen fades for FADE_STEPS (the fader's own 16
// frames) before the bot names the next screen
export const STEPS = 3;
export const MOVE_AT = 140;
export const BANNER_STEPS = 69;
export const FADE_STEPS = 16;
// A go-there order lands inside this box (left, top, right, bottom), where the bot keeps it
export const ORDER_BOX = [40, 40, 500, 440];

const STAGE_WIDTH = 640;
const STAGE_HEIGHT = 480;
// The drawing stays two updates behind the newest, so there is nearly always a newer update to slide toward
const DELAY = 2 * STEPS;
// The battle clock runs up to a tenth faster or slower to keep that delay. It never goes back, and it jumps ahead when
// a second or more behind (a hidden tab, a stalled phone)
const STEER = 0.05;
const MIN_RATE = 0.9;
const MAX_RATE = 1.1;
const JUMP = FPS;
// The parts root frame 5 places: the arena, its walls' hit shape, the countdown, the order rings, the move marker,
// the original's unused route crosses, the side bars and the rings beside a robot
const FRAME_PARTS = [535, 537, 550, 562, 568, 575, 584, 593];
// The original's characters the battle attaches or reaches for by id
const BOT = 67;
const TOP = 155;
const STATS = 293;
const BOOM = 57;
const FIRE = 162;
const SPARK = 201;
const RICCO = 286;
const STREAK = 318;
// The countdown (sprite 550) stops on this empty frame after GO. Its banners start on these labels, and each banner's
// picture of words sits at this depth while it plays
const COUNTDOWN_END = 161;
const WON = "complose";
const LOST = "playerlose";
const BANNER_DEPTH = 1;
// Words in place of a banner, for a draw and for watchers: the banners' pixel font, size and white, centered where the
// banners are, and drawn smaller when a long name would be wider than the arena
const DRAW = "DRAW";
const WINS = "WINS";
const COMPUTER = "COMPUTER";
const RESULT_WIDTH = 500;
const RESULT_WORDS = {
  bounds: [-RESULT_WIDTH / 2, -15, RESULT_WIDTH / 2, 20],
  font: '"04b_03b", monospace',
  bold: false,
  size: 30,
  color: "#ffffff",
  align: "center",
  multiline: false,
  wrap: false,
  leading: 0,
  var: "result",
  text: "",
  fit: true,
};
// Watchers' LEAVE: the shop's small tab button, at the top of the side bar
const TAB_BUTTON = 383;
const LEAVE_AT = [588, 16];
// The original's manageqfx: the newest 96 sparks, ricochets and explosions stay, and the newest 96 streaks
const MOST_EFFECTS = 96;
const MOST_STREAKS = 96;
// Each robot's top casts the original's drop shadow: 3 pixels at 45 degrees, 80% black, blurred 10 pixels
const SHADOW = {
  type: "shadow",
  color: "#000000",
  alpha: 0.8,
  x: 10,
  y: 10,
  passes: 1,
  strength: 1,
  angle: 45,
  distance: 3,
};
// A wreck's top is darkened to 60% (the original's ColorTransform(0.6, 0.6, 0.6))
const WRECKED = 0x999999;
// The blend modes the original gives explosions (Flash's 8) and flames (its 14)
const BOOM_BLEND = "add";
const FIRE_BLEND = "hard-light";
// Where the original parks its order rings while they show nothing
const AWAY = 5000;
// A shot's end: 1 when it hit a robot (0 missed, 2 hit a wall)
const HIT_ROBOT = 1;
// A robot's order as the bot sends it: 0 normal, [1, x, y] go there, [2, id] follow, [3, id] normal and closing in
const GOTO = 1;
const FOLLOW = 2;
const CLOSING = 3;
// The rings beside a robot (ios) show frames 1 to 3 for a robot with a gun, and the same three plus this without
const UNARMED_RINGS = 3;
// The move marker's (mo) pictures: go there, follow, back to normal
const MARK_GOTO = 1;
const MARK_FOLLOW = 2;
const MARK_NORMAL = 3;
// The battle's layers, bottom to top, in the original's depth order: tops (its depths 200 up), streaks (400 up), sparks
// and ricochets (500 up), flames (700 up), explosions (800 up), names and health bars (1500 up)
const LAYERS = ["tops", "streaks", "effects", "fires", "booms", "stats"];

// The battle while it shows, or null
let state = null;

// A holder that steps the clips in it once a tick, as Flash steps attached clips, and drops each one that removed
// itself (an effect's last frame removes it)
class Layer extends Container {
  advance() {
    for (const node of [...this.children]) {
      if (node.removed) {
        node.destroy({ children: true });
      } else {
        node.advance?.();
      }
    }
  }
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

// Rotations slide the short way round
function turn(a, b, t) {
  const gap = ((((b - a) % 360) + 540) % 360) - 180;
  return a + gap * t;
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function park(clip) {
  clip.position.set(AWAY, AWAY);
}

// ---------- Showing and leaving ----------

function enter(page) {
  page.sound.music("ambi");
  page.sound.fadeIn(2);
  const root = page.root;
  const field = root.attach(new Layer());
  const layers = Object.fromEntries(LAYERS.map((name) => [name, field.addChild(new Layer())]));
  // The order rings, the move marker and the countdown sit over everything the battle attaches, where the original
  // moves them (its depths 150001, 150002 and 200002). The rings beside a robot (ios) stay under the robots, as the
  // original leaves them
  const marks = root.attach(new Container());
  const [os, mo, countdown] = ["os", "mo", "startcountdown"].map((name) => marks.addChild(root.child(name)));
  // The countdown's GO and its banners' end are the bot's here: the robots move when the bot says, and the screen
  // fades on the drawn step
  countdown.onHook = () => true;
  const words = countdown.attach(new TextField(RESULT_WORDS), "result");
  words.bind(countdown);
  words.visible = false;
  state = {
    field,
    layers,
    marks,
    os,
    mo,
    countdown,
    words,
    leave: addLeave(page),
    ios: root.child("ios"),
    hud: root.child("hhud"),
    // Each bot frame's outline box, for presses
    outlines: new Map(),
    pointer: { x: 0, y: 0, over: false },
    // What the page last wrote for tests to read
    shown: { step: null, robots: null },
  };
  listen(page, field);
  build(page, page.battle);
}

// Watchers leave when they like: the bot stops sending them the battle, and the list of battles comes back
function addLeave(page) {
  const button = page.root.attach(page.lib.make(TAB_BUTTON), "leavebutton");
  button.position.set(...LEAVE_AT);
  button.set("displaytext", "LEAVE");
  button.visible = false;
  button.setHandler("onPress", () => {
    if (state?.battle.you === null && !state.left) {
      state.left = true;
      page.send({ unwatch: true });
      page.go("watch", { fadeSound: 3 });
    }
  });
  return button;
}

function leave() {
  delete document.body.dataset.step;
  delete document.body.dataset.robots;
  delete document.body.dataset.watching;
  if (!state) {
    return;
  }
  state.leave.destroy({ children: true });
  state.words.destroy();
  state.field.destroy({ children: true });
  // The rings, marker and countdown are the root frame's own, and go with its next frame
  state.marks.removeChildren();
  state.marks.destroy();
  state = null;
}

function receive(page, data) {
  if (!state) {
    return;
  }
  // The same battle sent again (a reconnect) is drawn again from where the bot has it
  if (data.battle) {
    build(page, data.battle);
    return;
  }
  // A watcher's page that connected again: the bot forgot what it watched, so it asks again
  if (data.data && state.battle.you === null && !state.left) {
    page.send({ watch: state.id });
  }
  // A battle left behind may end after another one came; only this one's end counts
  if (data.over && data.over.id === state.id) {
    state.over = true;
  }
  if (data.lobby) {
    checkList(page, data.lobby);
  }
}

function step(page) {
  if (!state) {
    return;
  }
  take(page);
  moveClock(page);
  catchUp(page, false);
  draw(page);
}

function draw(page) {
  place();
  hover();
  rings();
  countdown(page);
  shade(page);
  const shown = { step: Math.floor(state.clock), robots: state.robots.length };
  if (shown.step !== state.shown.step) {
    document.body.dataset.step = String(shown.step);
  }
  if (shown.robots !== state.shown.robots) {
    document.body.dataset.robots = String(shown.robots);
  }
  state.shown = shown;
}

// ---------- Building a battle ----------

// The battle as the bot has it at its step: each robot, the wrecks burning, the arena, the side bars, and the
// updates that came since
function build(page, battle) {
  for (const layer of Object.values(state.layers)) {
    for (const node of layer.removeChildren()) {
      node.destroy({ children: true });
    }
  }
  if (battle.id !== state.id) {
    // Whether the window's list has shown this battle, whether the bot has said it is over, and whether the page left
    // it (it vanished from the list, or its watcher pressed LEAVE)
    state.id = battle.id;
    Object.assign(state, { listed: listedIn(page.lobby), over: false, left: false });
  }
  // Watchers give no orders and see no rings (they have no robots of their own), and can leave
  const watching = battle.you === null;
  state.leave.visible = watching;
  if (watching) {
    document.body.dataset.watching = "true";
  } else {
    delete document.body.dataset.watching;
  }
  state.countdown.set("result", "");
  Object.assign(state, {
    battle,
    // The side whose sounds and side bar count as yours: watchers take the left side's
    side: battle.you ?? 1,
    snaps: [{ step: battle.step, r: battle.r }],
    events: [],
    base: battle.step,
    clock: battle.step,
    ended: battle.ended,
    winner: battle.winner,
    faded: false,
    effects: { slots: [], n: 0 },
    streaks: { slots: [], n: 0 },
    fires: 0,
    drag: null,
    under: null,
    owner: null,
    filterScale: null,
  });
  state.robots = battle.robots.map((setup, index) => makeRobot(page, setup, index, battle.colors[setup.team - 1]));
  const flames = new Map(battle.flames);
  for (const robot of state.robots) {
    const [x, y, , , health] = battle.r[robot.index];
    if (health <= 0) {
      wreck(page, robot, x, y, flames.get(robot.id) ?? [], true);
    }
  }
  page.root.child("arenabg").gotoAndStop(battle.background);
  colorHud(battle.colors);
  park(state.os);
  park(state.ios);
  state.mo.onEnterFrame = null;
  park(state.mo);
  // The drawing starts DELAY behind the newest update, also on a rejoin, when the whole battle is the newest: the
  // robots hold their places until the clock reaches it, and from then on it has its cushion against late updates
  take(page);
  state.clock = newest() - DELAY;
  catchUp(page, true);
  draw(page);
}

function makeRobot(page, setup, index, color) {
  const lib = page.lib;
  outline(page, setup.frame);
  const weapon = page.data?.weapons.find((part) => part.name === setup.weapon) ?? null;
  const plating = page.data?.platings.find((part) => part.name === setup.plating);
  // The top on its plating's picture, every light and stripe in the team's color, and the gun on its weapon's
  const top = state.layers.tops.addChild(lib.make(TOP, plating?.graphic ?? 1));
  top.stop();
  top.label = `top${setup.id}`;
  for (let n = 1; top.child(`teamlight${n}`); n += 1) {
    top.child(`teamlight${n}`).child("tcolor")?.gotoAndStop(color);
  }
  top.child("tcolor")?.gotoAndStop(color);
  const gun = top.child("gun");
  gun.gotoAndStop(weapon?.gun ?? 1);
  gun.visible = weapon !== null;
  // The name and health bar that follow it
  const stats = state.layers.stats.addChild(lib.make(STATS));
  stats.label = `stats${setup.id}`;
  stats.set("botname", setup.name);
  const hp = stats.child("hp");
  hp.child("tcolor").gotoAndStop(color);
  return {
    ...setup,
    index,
    weapon,
    top,
    gun,
    stats,
    bar: hp.child("bar"),
    dead: false,
    x: 0,
    y: 0,
    rot: 0,
    health: setup.max,
    cooldown: 0,
    order: 0,
  };
}

// The side bars' colors: yours (or the left side's) first
function colorHud(colors) {
  state.hud.child("bar1").child("bar").child("tcolor").gotoAndStop(colors[state.side - 1]);
  state.hud.child("bar2").child("bar").child("tcolor").gotoAndStop(colors[2 - state.side]);
}

// ---------- The battle clock ----------

// The bot's updates since the last step: each one's robots, and its events, to play when the drawing reaches them.
// Events from before the battle was last built are already in it
function take(page) {
  for (const update of page.updates.splice(0)) {
    if (update.id !== state.id || update.step <= newest()) {
      continue;
    }
    state.snaps.push({ step: update.step, r: update.r });
    state.events.push(...update.e.filter((event) => event[0] > state.base));
  }
}

function newest() {
  return state.snaps[state.snaps.length - 1].step;
}

// The drawn step moves on once a tick, a little faster or slower to stay DELAY behind the newest update. It never
// passes the newest update, and jumps when far behind
function moveClock(page) {
  const target = newest() - DELAY;
  if (target - state.clock > JUMP) {
    state.clock = target;
    catchUp(page, true);
  } else {
    const rate = clamp(1 + (target - state.clock) * STEER, MIN_RATE, MAX_RATE);
    state.clock = Math.min(newest(), state.clock + rate);
  }
  while (state.snaps.length > 1 && state.snaps[1].step <= state.clock) {
    state.snaps.shift();
  }
}

// Every event the drawn step has reached, in the bot's order. Quietly, after a jump or when the battle is built:
// shots long gone are skipped, and wrecks appear burning, without their explosion
function catchUp(page, quiet) {
  const now = Math.floor(state.clock);
  while (state.events.length && state.events[0][0] <= now) {
    const event = state.events.shift();
    const kind = event[1];
    if (kind === "shot" && !quiet) {
      shot(page, event);
    } else if (kind === "die") {
      died(page, event, quiet);
    } else if (kind === "end") {
      state.ended = event[0];
      state.winner = event[2];
    }
  }
}

// Each robot where the drawn step has it, between the two updates around that step
function place() {
  const [a, b] = state.snaps;
  const t = b ? clamp((state.clock - a.step) / (b.step - a.step), 0, 1) : 0;
  for (const robot of state.robots) {
    const now = a.r[robot.index];
    const next = b ? b.r[robot.index] : now;
    robot.x = lerp(now[0], next[0], t);
    robot.y = lerp(now[1], next[1], t);
    robot.rot = turn(now[2], next[2], t);
    [robot.health, robot.cooldown, robot.order] = [now[4], now[5], now[6]];
    robot.top.position.set(robot.x, robot.y);
    robot.top.angle = robot.rot;
    robot.gun.angle = turn(now[3], next[3], t);
    if (robot.stats) {
      robot.stats.position.set(robot.x, robot.y);
      robot.bar.scale.x = robot.health / robot.max;
    }
  }
  fillHud(a.r);
}

// The side bars (the original's fixplayerhud and fixenemyhud): each side's health out of its most
function fillHud(r) {
  for (const [name, side] of [
    ["bar1", state.side],
    ["bar2", 3 - state.side],
  ]) {
    const robots = state.robots.filter((robot) => robot.team === side);
    const health = robots.reduce((sum, robot) => sum + r[robot.index][4], 0);
    const most = robots.reduce((sum, robot) => sum + robot.max, 0);
    state.hud.child(name).child("bar").scale.y = most ? health / most : 0;
  }
}

// The countdown shows the drawn step, so its GO lines up with the bot's MOVE_AT. Once the battle has a result, your
// side's banner plays from the step it came, or for a draw, and for watchers, words in the banner's place. When the
// banner ends the screen fades out with the sound (the original's textdone) to wait for the bot's next screen
function countdown(page) {
  const now = Math.floor(state.clock);
  let frame = clamp(now, 1, COUNTDOWN_END);
  const words = state.ended === null ? null : resultWords();
  if (state.ended !== null) {
    // Both banners move the same way, so words borrow the first one's motion
    const banner = words ? LOST : bannerOf();
    if (banner) {
      frame = state.countdown.frameOf(banner) + clamp(now - state.ended, 0, BANNER_STEPS);
    }
    // Once the bot's "over" has come, its own fade to the next screen is the one that counts
    if (now >= state.ended + BANNER_STEPS && !state.faded && !state.over) {
      state.faded = true;
      page.go(null, { fadeSound: 3 });
    }
  }
  state.countdown.gotoAndStop(frame);
  showWords(words);
}

function bannerOf() {
  const you = state.battle.you;
  if (you === null || !state.winner) {
    return null;
  }
  return state.winner === you ? WON : LOST;
}

// DRAW for everyone, and for watchers the winner's name: the side's player, or the computer
function resultWords() {
  const { you, names } = state.battle;
  if (state.winner === 0) {
    return DRAW;
  }
  if (you !== null || !state.winner) {
    return null;
  }
  return `${String(names[state.winner - 1] ?? COMPUTER).toUpperCase()} ${WINS}`;
}

// The words take the banner picture's place: its size and see-through as it grows in and out, the picture hidden
function showWords(words) {
  const art = words ? state.countdown.at(BANNER_DEPTH) : null;
  state.words.visible = Boolean(art);
  if (!art) {
    return;
  }
  art.visible = false;
  state.countdown.set("result", words);
  state.words.scale.copyFrom(art.scale);
  state.words.alpha = art.alpha;
}

// Filters work in screen pixels, so the shadows follow the stage's size
function shade(page) {
  const scale = page.lib.filterScale;
  if (scale === state.filterScale) {
    return;
  }
  state.filterScale = scale;
  for (const robot of state.robots) {
    robot.top.filters = [makeFilter(SHADOW, robot.top.filters?.[0], scale)];
  }
}

// ---------- Shots, explosions and flames ----------

function effect(page, layer, id, frame, x, y, angle) {
  const clip = layer.addChild(page.lib.make(id, frame));
  clip.position.set(x, y);
  clip.angle = angle;
  return clip;
}

// The original's manageqfx: a new effect takes the ring's next place, and the oldest, in the place after it, goes
function keep(ring, clip, most, prefix) {
  clip.label = `${prefix}${ring.n}`;
  ring.slots[ring.n] = clip;
  ring.n = (ring.n + 1) % most;
  const oldest = ring.slots[ring.n];
  if (oldest && !oldest.destroyed) {
    oldest.removeMovieClip();
  }
  ring.slots[ring.n] = null;
}

// The original's fire and drawpath, drawn from the bot's shot: the ricochet where the shot ended, turned back when it
// hit something, the gun's kick, the spark at the gun's tip, and the streak from the tip as long as the shot went
function shot(page, event) {
  const [, , id, tipX, tipY, muzzle, direction, length, endX, endY, hit, rico] = event;
  const robot = state.robots.find((one) => one.id === id);
  const weapon = robot?.weapon;
  if (!weapon) {
    return;
  }
  const yours = robot.team === state.side;
  const back = hit ? direction + 180 : direction;
  const ricco = effect(page, state.layers.effects, RICCO, weapon.spark, endX, endY, back);
  ricco.stop();
  keep(state.effects, ricco, MOST_EFFECTS, "qfx");
  page.sound.effect(`rico${rico}`, `${yours}_${hit === HIT_ROBOT ? "hit" : "miss"}`);
  robot.gun.child("anim")?.gotoAndPlay(2);
  page.sound.effect(weapon.sound, `${yours}_shot`);
  const spark = effect(page, state.layers.effects, SPARK, weapon.discharge, tipX, tipY, muzzle);
  spark.stop();
  keep(state.effects, spark, MOST_EFFECTS, "qfx");
  const streak = effect(page, state.layers.streaks, STREAK, weapon.streak, tipX, tipY, direction);
  streak.stop();
  stretch(streak.child("streaktween"), length);
  keep(state.streaks, streak, MOST_STREAKS, "streak");
}

// Flash's _height: the streak's picture is stretched to the shot's length
function stretch(tween, length) {
  const height = tween?.getLocalBounds().height;
  if (height > 0) {
    tween.scale.y = length / height;
  }
}

function died(page, event, quiet) {
  const [, , id, x, y, flames] = event;
  const robot = state.robots.find((one) => one.id === id);
  if (robot && !robot.dead) {
    wreck(page, robot, x, y, flames, quiet);
  }
}

// The original's killme: the top darkens and its lights and spinners stop, the name and health bar go, and the wreck
// explodes and burns
function wreck(page, robot, x, y, flames, quiet) {
  robot.dead = true;
  robot.top.tint = WRECKED;
  robot.stats.destroy({ children: true });
  robot.stats = null;
  const spinners = [robot.gun.child("spinner"), robot.top.child("spinnr"), robot.gun.child("cry")?.child("shine")];
  for (const spinning of spinners) {
    if (spinning) {
      spinning.onEnterFrame = null;
    }
  }
  for (let n = 1; robot.top.child(`teamlight${n}`); n += 1) {
    const light = robot.top.child(`teamlight${n}`);
    light.vars.stopanimating = true;
    light.gotoAndStop(2);
  }
  if (!quiet) {
    const boom = effect(page, state.layers.booms, BOOM, 1, x, y, 0);
    boom.blendMode = BOOM_BLEND;
    keep(state.effects, boom, MOST_EFFECTS, "qfx");
    page.sound.effect("splode", "misc");
  }
  for (const [dx, dy, size] of flames) {
    burn(page, x + dx, y + dy, size, quiet);
  }
  if (state.owner === robot) {
    state.owner = null;
  }
}

// The original's makefire: a flame that grows into its size over a few seconds (or has, on a wreck drawn later),
// flickering in size and strength
function burn(page, x, y, size, grown) {
  const fire = state.layers.fires.addChild(page.lib.make(FIRE));
  fire.label = `fire${state.fires}`;
  state.fires += 1;
  fire.position.set(x, y);
  fire.blendMode = FIRE_BLEND;
  let growth = grown ? 1 : 0;
  let wide = size * growth;
  let tall = size * growth;
  fire.scale.set(wide / 100, tall / 100);
  fire.onEnterFrame = () => {
    if (growth < 1.01) {
      growth += (1 - growth) / 75;
    }
    wide = size * growth + page.random(wide / 10);
    tall = size * growth + page.random(tall / 3);
    fire.scale.set(wide / 100, tall / 100);
    fire.alpha = (page.random(15) + 75) / 100;
  };
}

// ---------- Orders ----------

function listen(page, field) {
  field.eventMode = "static";
  field.hitArea = new Rectangle(0, 0, STAGE_WIDTH, STAGE_HEIGHT);
  field.interactiveChildren = false;
  const at = (event, over) => {
    const point = field.toLocal(event.global);
    state.pointer = { x: point.x, y: point.y, over };
    return point;
  };
  field.on("pointermove", (event) => at(event, true));
  field.on("pointerout", () => {
    state.pointer.over = false;
  });
  field.on("pointerdown", (event) => pressed(at(event, true)));
  // A finger lifted is no longer over anything
  field.on("pointerup", (event) => released(page, at(event, event.pointerType !== "touch")));
  field.on("pointerupoutside", (event) => released(page, at(event, false)));
}

// The box round a bot frame's outline, in the robot's own pixels (the original's bot clip, which takes its presses)
function outline(page, frame) {
  if (!state.outlines.has(frame)) {
    const bot = page.lib.make(BOT, frame);
    const { minX, minY, maxX, maxY } = bot.getLocalBounds();
    bot.destroy({ children: true });
    state.outlines.set(frame, { minX, minY, maxX, maxY });
  }
  return state.outlines.get(frame);
}

function covers(robot, x, y) {
  const box = state.outlines.get(robot.frame);
  const radians = (robot.rot * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const dx = x - robot.x;
  const dy = y - robot.y;
  const across = cos * dx + sin * dy;
  const along = -sin * dx + cos * dy;
  return across >= box.minX && across <= box.maxX && along >= box.minY && along <= box.maxY;
}

// One of your living robots under the point, the topmost (the last attached) first, as Flash finds a press
function yoursAt(x, y) {
  const you = state.battle.you;
  for (let index = state.robots.length - 1; index >= 0; index -= 1) {
    const robot = state.robots[index];
    if (you !== null && robot.team === you && !robot.dead && covers(robot, x, y)) {
      return robot;
    }
  }
  return null;
}

// Whatever robot is under the point, wrecks too, the first by id (the original's whogothit)
function robotAt(x, y) {
  return state.robots.find((robot) => covers(robot, x, y)) ?? null;
}

// The original's roll over and roll out: the rings show while the pointer is over one of your robots. A robot being
// dragged keeps them until the release
function hover() {
  if (state.drag) {
    return;
  }
  const { x, y, over } = state.pointer;
  const under = over ? yoursAt(x, y) : null;
  if (under !== state.under) {
    state.under = under;
    state.owner = under;
  }
}

function pressed(point) {
  state.drag = yoursAt(point.x, point.y);
  if (state.drag) {
    // A finger has no roll over before its press, so the press shows the rings
    state.under = state.drag;
    state.owner = state.drag;
  }
}

// The original's onRelease (back on the robot: back to normal) and onReleaseOutside (anywhere else: go there, or follow
// the robot it ended on). A release on a drawn robot is sent as where the bot last had that robot: the drawing is a
// moment behind, and the bot checks the point against its own newest positions
function released(page, point) {
  const robot = state.drag;
  state.drag = null;
  if (!robot) {
    return;
  }
  state.owner = null;
  if (robot.dead) {
    return;
  }
  const target = covers(robot, point.x, point.y) ? robot : robotAt(point.x, point.y);
  const latest = target && state.snaps[state.snaps.length - 1].r[target.index];
  const [x, y] = latest ? [latest[0], latest[1]] : [point.x, point.y];
  if (!page.send({ order: [robot.id, x, y] })) {
    return;
  }
  if (target === robot) {
    mark(MARK_NORMAL, () => robot);
  } else if (target && !target.dead) {
    mark(MARK_FOLLOW, () => target);
  } else if (!target) {
    const [left, top, right, bottom] = ORDER_BOX;
    const spot = { x: clamp(point.x, left, right), y: clamp(point.y, top, bottom) };
    mark(MARK_GOTO, () => spot);
  }
}

// The original's mo: the marker plays from its start on the order's goal, and keeps to it
function mark(picture, goal) {
  const mo = state.mo;
  mo.gotoAndPlay(1);
  mo.onEnterFrame = () => {
    const { x, y } = goal();
    mo.position.set(x, y);
    mo.child("stat")?.gotoAndStop(picture);
  };
  mo.onEnterFrame();
}

// The original's os.onEnterFrame: over one of your robots, the rings beside it (ios) show how it is ordered, with its
// gun's charge on the dial, and the ring at its goal (os) shows where it goes, or whom it follows or closes in on
function rings() {
  const { os, ios, owner } = state;
  if (!owner) {
    park(os);
    park(ios);
    return;
  }
  const armed = owner.weapon !== null;
  if (armed) {
    ios.child("fs")?.child("am")?.scale.set(owner.cooldown / 1000);
  }
  const [kind, ...goal] = Array.isArray(owner.order) ? owner.order : [0];
  const shown = kind === GOTO || kind === FOLLOW ? kind : 3;
  ios.gotoAndStop(armed ? shown : shown + UNARMED_RINGS);
  ios.position.set(owner.x, owner.y);
  if (kind === GOTO) {
    os.gotoAndStop(GOTO);
    os.position.set(goal[0], goal[1]);
  } else if (kind === FOLLOW || kind === CLOSING) {
    const leader = state.robots.find((robot) => robot.id === goal[0]);
    os.gotoAndStop(kind);
    os.position.set(leader?.x ?? AWAY, leader?.y ?? AWAY);
  } else if (armed) {
    park(os);
  }
}

// ---------- The window's list ----------

function listedIn(lobby) {
  return Boolean(lobby?.battles?.some((entry) => entry.id === state.id));
}

// A battle that leaves the window's list with no "over" was stopped (the bot's battle loop failed). The player goes
// where the battle would have sent them
function checkList(page, lobby) {
  if (listedIn(lobby)) {
    state.listed = true;
    return;
  }
  if (state.listed && !state.over && !state.left) {
    state.left = true;
    const { you, kind } = state.battle;
    const next = you === null ? "watch" : ({ pvp: "pvp", challenge: "challengeselect" }[kind] ?? "shop");
    page.go(next, { fadeSound: 3 });
  }
}

// ---------- The order rings' turning (sprites 552, 557 and 560) ----------

function spin(page, clip) {
  clip.onEnterFrame = () => {
    clip.angle += 1;
  };
}

export const battle = {
  // The parts its root frame places, and the clips it attaches
  art: [...FRAME_PARTS, BOT, TOP, STATS, BOOM, FIRE, SPARK, RICCO, STREAK, TAB_BUTTON],
  enter,
  leave,
  receive,
  step,
  scripts: { 552: spin, 557: spin, 560: spin },
};
