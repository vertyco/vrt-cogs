// The battlefield: the loading screen, the world (the mission's map with its cover, midground strips, wire and rain,
// buildMap F6:7267-7379), the drawn-step clock that keeps the drawing in time with the bot, the camera (cameraSetup,
// cameraControl and cameraPanKeys, F6:1204-1277) and the screen shake (screenShake and shakeScreen, F6:5150-5191).
//
// The bot runs the battle and sends an update every 3 steps. The field keeps every update and draws a little behind
// the newest on its own clock, so the drawing never runs out of updates to slide toward. Playing the bot's tick n on
// the page does what the bot did in it, in the bot's order: the world's clips step one frame (the bot advances every
// timeline first), then the onDrawnStep listeners run, then the events stamped n fire (onEvent). drawnStep counts the
// ticks played, like the bot's own step. A paused battle stops the clock where the bot paused, and with it every clip
// in the world (B19); watchers see PAUSED (D11).
import { Effects } from "./effects.js";
import { makeFilter, TextField } from "./flash.js";
import { Hud } from "./hud.js";
import { Orders } from "./orders.js";
import { Panels } from "./panels.js";
import { Results } from "./results.js";
import { Container } from "./vendor/pixi.min.mjs";
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { Units } from "./units.js";

// The bot's steps a second and its steps between updates
const FPS = 30;
const STEPS = 3;
// The drawing stays two updates behind the newest, so there is nearly always a newer update to slide toward
const DELAY = 2 * STEPS;
// The drawn clock runs up to a tenth faster or slower to keep that delay. It never goes back, and it jumps ahead when
// a second or more behind (a hidden tab, a stalled phone)
const STEER = 0.05;
const MIN_RATE = 0.9;
const MAX_RATE = 1.1;
const JUMP = FPS;
const STAGE_WIDTH = 800;
const STAGE_HEIGHT = 500;
const EASE = "easeOutSine";
// The original's root depths (F6:10108-10124). The world sits at depth_testMap, which the original never sets, so at 0
const DEPTH_WORLD = 0;
const DEPTH_HUD = 900000;
const DEPTH_HUD_PAN_ARROW = 1000;
const DEPTH_BLACKOUT = 1500000;
// The world's layers, bottom to top, at the original's world depths (F6:10125-10144). Each holds the clips the
// original attached from that depth up
const WORLD_LAYERS = [
  ["deployButtons", 1100],
  ["deployZoneHighlight", 1200],
  ["specialAttackRange", 1250],
  ["decals", 1500],
  ["deadSoldiers", 10000],
  ["cover", 14000],
  ["wire", 15000],
  ["soldiers", 20000],
  ["soldiersSorted", 30000],
  ["grenade", 400000],
  ["bazookaRounds", 450000],
  ["bazookaImpacts", 475000],
  ["particles", 480000],
  ["artillery", 500000],
  ["bounceParticles", 680000],
  ["rainHolder", 700000],
  ["target", 900000],
  ["fighter", 920000],
  ["xpIcons", 950000],
];
// The three lanes' click areas (deployBlock, sprite 4 at 70 high, F6:1840-1853): from 34 above each lane's line to 36
// below it, so y 111 to 181, 196 to 266 and 282 to 352, with gaps between that take no click
const LANE_TOP = 34;
const LANE_HEIGHT = 70;
// buildMap (F6:7283-7311): each cover sits 25 above its lane's line (zone - deployZoneHeight / 2 + 10) on the
// coverBlock frame named for its kind. Two kinds hold a part whose placement script picks a variant: the hedgerow's
// (S1863/frame_120, gotoAndStop(random(2) + 1)) and the headstones' (S1863/frame_158, gotoAndStop(random(2)), where
// frame 0 leaves it on frame 1, so only the hedgerow varies). Frame labels match without case, as in AS2
const COVER_RISE = 25;
const COVER_VARIANTS = { 1849: 2 };
// buildMap (F6:7313-7340): the map's three midground strips, at x 0 and these heights. A strip the file lacks attaches
// nothing
const MIDGROUND_Y = [195, 275, 375];
// buildMap (F6:7341-7366): each wire line is 9 fence pieces, 5 pixels apart give or take 11, from y 125 down in steps
// of 30
const WIRE_PIECES = 9;
const WIRE_STEP_X = 5;
const WIRE_SPREAD = 22;
const WIRE_Y = 125;
const WIRE_STEP_Y = 30;
// rainEffect (F6:5113-5149): rainDrops is 130 and the loop counts from 1 while below it, so 129 drops fall, each 2
// across and 30 down a step, splashing below y 170 to 419 and starting again 300 to 500 above the top
const RAIN_DROPS = 130;
const RAIN_DROP_DEPTH = 50;
const RAIN_SPLASH_DEPTH = 500;
const RAIN_DX = 2;
const RAIN_DY = 30;
const RAIN_START_RANGE = 200;
const RAIN_START_TOP = -500;
const RAIN_SPLASH_RANGE = 250;
const GROUND = 170;
// The camera (F6:10165-10167): 20 pixels a step while the pointer is within 80 pixels of a side and at y 335 or above
// (panInterfaceBlock, Stage.height - 165). The German side starts at the German end (F6:1206-1209)
const PAN_SPEED = 20;
const PAN_BUFFER = 80;
const PAN_BLOCK = STAGE_HEIGHT - 165;
const GERMAN_START = STAGE_WIDTH + 100;
const TWIPS = 20;
// A drag scrolls the field from anywhere above the HUD, so the bottom lane can be dragged too
const HUD_TOP = 353;
// screenShake and shakeScreen (F6:5150-5191, screenShakeDelay F6:10942): a shake moves the world once every 50 ms,
// as many times as asked, by up to half the magnitude each way, and never leaves it above y -10, below y 0, right of
// x 0 or left of minus the field's width less 300. Nothing puts it back. A shake asked for while one runs is dropped
const SHAKE_DELAY_MS = 50;
const SHAKE_TOP = -10;
const SHAKE_PAST_END = 300;
// A player's page tells the bot where its camera is at most this often (ms), so a watcher can start there
const CAMERA_SEND_MS = 1000;
// A press that moves this many stage pixels sideways scrolls the field instead. A finger wobbles more than a mouse, so
// on a touch screen it takes this many screen pixels too, which is more than 8 stage pixels once the stage is small
const DRAG_START = 8;
const TOUCH_DRAG_PX = 10;
// showLoadScreen and startBattle (F6:802-812, 6792-6797): the screen fades in over 1.8 seconds and out over 1, 3
// seconds after the battle starts. A battle joined later than that shows no loading screen
const LOADING_IN = 1.8;
const LOADING_HOLD = 3;
const LOADING_OUT = 1;
// hideMenu (F6:474-486): the menu music fades over 5 seconds, and the menu goes 2 seconds on, over 1
const MENU_MUSIC_FADE = 5;
const MENU_FADE_DELAY = 2;
const MENU_FADE = 1;
// The hint field grows downward to hold its words (autoSize "center" on a wrapping field), up to this many lines
const HINT_LINES = 3;
// The original's hints (F2:83), repeats and all, so each comes up as often as it did, less the four that ask players
// to leave a comment about bugs (W17)
const HINTS = [
  "ONE squad to ONE piece of cover, thems the rules (for now).",
  "ONE squad to ONE piece of cover, thems the rules (for now).",
  "ONE squad to ONE piece of cover, thems the rules (for now).",
  "ONE squad to ONE piece of cover, thems the rules (for now).",
  "Make sure you have empty cover for your Snipers and Machine Gun teams to move into.",
  "All's fair in love and Warfare.",
  "Use Assault Teams to throw grenades at tanks in an attempt to disable them.",
  "Experience is earned by killing enemy units, winning battles quickly and efficiently.",
  "Keep an eye on the green Morale Bar at the top of screen, depletion of morale will lead to your men surrendering.",
  "Killing enemies, deploying Officers and bringing Tanks to the battlefield will boost the Morale of your men.",
  "Outnumbering your enemy will boost the Morale of your men and reduce theirs.",
  "Outnumbering your enemy will boost the Morale of your men and reduce theirs.",
  "Resupply of Resource Points occurs about every 8 seconds.",
  "The maximum amount of Resource Points available varies from mission to mission.",
  "Use smoke to block the view of enemies ahead of you. They will still fire at you but with decreased accuracy",
  "The destruction of Tanks and the death of Officers will greatly affect the morale of the men.",
  "Upgrade your units via the upgrades button on the HUD or in the Campaign Map menu.",
  "Officers provide a damage bonus to any infantry near them.",
  "Be cautious when moving over open ground. Listen in the distance for artillery guns before sending your men over the top.",
  "Upgrades carry over between battles.",
  "Your game is saved automatically each time you start and finish a battle.",
  "Deploy weaker units such as Machine Gunners and Snipers behind other Infantry for protection.",
  "Use Assault Teams to charge trenches and gain ground on long range infantry.",
  "Mortar strikes do a great deal of damage to infantry in the open.",
  "Artillery strikes are costly in terms of resources use them wisely.",
  "Machine Gun Teams and Snipers are weak in the open, try to get them to cover positions quickly.",
  "Tanks are almost invulnerable against small arms fire. Use anti-tank teams to knock them out.",
  "Take notice of the 'Ground Taken' progress bar at the top of screen. It shows your units front most position.",
];
// Watchers' PAUSED: the loading screen's heading (character 1439) with its black glow, over the field below the HUD
const HEADING_TEXT = 1439;
const PAUSED_GLOW = { type: "glow", color: "#000000", alpha: 1, x: 5, y: 5, passes: 1, strength: 2, inner: false };
const PAUSED_Y = 150;

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

// Flash's random(n): a whole number from 0 to n - 1. Only for what the page draws; the bot decides everything else
function random(n) {
  return Math.floor(Math.random() * n);
}

// A holder that steps the clips in it once a drawn step, as Flash steps attached clips, and drops each one that
// removed itself. Its clips sort by zIndex, which takes the place of the original's depth inside the layer
class Layer extends Container {
  constructor() {
    super();
    this.sortableChildren = true;
  }

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

export class Field {
  constructor() {
    this.page = null;
    // The full battle on show, or null
    this.battle = null;
    // The holder on the root (never stepped by the root's own tick), the map clip in it, and its layers by name
    this.holder = null;
    this.world = null;
    this.layers = {};
    // The bot's updates still ahead of the drawing: { step, s }, oldest first
    this.snaps = [];
    this.events = [];
    this.clock = 0;
    this.played = 0;
    // The step the bot paused on, or null while it runs
    this.pausedAt = null;
    this.result = null;
    // True from the update that carries the battle's end event: the fighting is over and the results are coming
    this.ending = false;
    this.camera = { state: "free", width: STAGE_WIDTH };
    // The shake running: { magnitude, count, done, start (the drawn step it began on) }, or null
    this.shaking = null;
    // The map's clips the depth sort walks with the soldiers, in the order buildMap made them (F6:7273, 7290-7340):
    // the midground strips and the cover
    this.midGround = [];
    this.covers = [];
    this.cameraSent = { x: null, at: 0 };
    this.pointer = { x: 0, y: 0, inside: false, touch: false, down: false };
    this.drag = null;
    this.arrow = null;
    this.pausedText = null;
    this.handlers = new Map();
    this.stepListeners = [];
    this.loadListeners = [];
    this.drawListeners = [];
    this.clearListeners = [];
    this.listening = false;
    // Bumped on every load, so a load still waiting on the art gives way to a newer one. waiting: { id, updates } for
    // the battle being loaded
    this.loads = 0;
    this.waiting = null;
    // The soldiers and tanks, then the strikes and blasts, which listen to the field from here on
    this.units = new Units(this);
    this.effects = new Effects(this);
    // The HUD and the bars along the top and bottom, which listen to the field from here on
    this.hud = new Hud(this);
    // The squad the player selected, the INTEL panel's order buttons and the aiming of an order
    this.orders = new Orders(this, this.hud);
    // The help tips and the in-battle menu, over the HUD
    this.panels = new Panels(this);
    // The end banner, the results screen and the ending, over everything
    this.results = new Results(this);
  }

  bind(page) {
    this.page = page;
    // The menu stays under the loading screen while it fades in, as hideMenu leaves it; the field removes it
    menus.MENU_SCREENS.add("battle");
  }

  // ---------- What other modules use ----------

  get drawnStep() {
    return this.played;
  }

  // True once the drawing has reached the step the bot paused on
  get paused() {
    return this.pausedAt !== null && this.clock >= this.pausedAt;
  }

  layer(name) {
    return this.layers[name] ?? null;
  }

  // A point on the stage (the original's 800 x 500 pixels) as a point on the field
  toField(screenX, screenY) {
    return { x: screenX - (this.world?.x ?? 0), y: screenY - (this.world?.y ?? 0) };
  }

  // The lane (1 to 3) whose click area holds a point on the field at this height, or null in a gap or off the lanes
  laneAt(fieldY) {
    const lanes = this.battle?.map.lanes ?? [];
    const index = lanes.findIndex((line) => fieldY >= line - LANE_TOP && fieldY <= line - LANE_TOP + LANE_HEIGHT);
    return index < 0 ? null : index + 1;
  }

  // screenShake (F6:5150-5166): the world shakes `steps` times, one every 50 ms of the drawn clock, unless a shake
  // already runs. Only the picture moves, so it draws from Math.random
  shake(magnitude, steps) {
    if (this.shaking || !this.world) {
      return;
    }
    this.shaking = { magnitude, count: steps, done: 0, start: this.played };
  }

  // fn(event, quiet) for each event of that code the drawing reaches. Quiet after a jump, when the moment has passed:
  // a handler may skip sounds and flights and only leave what lasts
  onEvent(code, fn) {
    const list = this.handlers.get(code) ?? [];
    list.push(fn);
    this.handlers.set(code, list);
  }

  // fn(step, jumped) once per tick the drawing plays, after the world's clips stepped. jumped: the clock leapt over
  // many steps at once, and this call stands for all of them
  onDrawnStep(fn) {
    this.stepListeners.push(fn);
  }

  // fn(battle) each time a battle is built or built again from a full battle (a rejoin)
  onLoad(fn) {
    this.loadListeners.push(fn);
  }

  // fn() once a page tick, after the ticks it played, for things that slide between updates (around)
  onDraw(fn) {
    this.drawListeners.push(fn);
  }

  // fn() when the world is taken down, before its clips go
  onClear(fn) {
    this.clearListeners.push(fn);
  }

  // The two updates around the drawn clock and how far between them it is (0 to 1), for sliding things between them
  around() {
    const [a, b] = this.snaps;
    const t = b ? clamp((this.clock - a.step) / (b.step - a.step), 0, 1) : 0;
    return { a, b: b ?? a, t };
  }

  // ---------- The battle arriving ----------

  // The battle screen opens on page.battle
  async enter() {
    this.listen();
    await this.load(this.page.battle);
  }

  async load(battle) {
    if (!battle) {
      return;
    }
    const load = (this.loads += 1);
    // Updates that come while the art loads wait, so none of their events is lost
    this.waiting = { id: battle.id, updates: [] };
    if (!this.world || this.battle?.id !== battle.id) {
      await this.page.lib.need(this.artFor(battle.map));
      if (load !== this.loads || this.page.screen !== "battle") {
        return;
      }
      this.clear();
      this.buildWorld(battle);
      this.startScreen(battle);
    }
    const waited = this.waiting.updates;
    this.waiting = null;
    this.battle = battle;
    this.result = battle.result ?? null;
    this.ending = this.result !== null;
    this.restartClock(battle);
    waited.forEach((u) => this.update(u));
    this.showPaused();
    for (const fn of this.loadListeners) {
      fn(battle);
    }
  }

  artFor(map) {
    const lib = this.page.lib;
    const strips = MIDGROUND_Y.map((y, index) => `midground_${map.art}${index + 1}`);
    const own = [map.art, ...strips, "coverBlock", "wireFence", "rainDrop", "rainSplash", "loadScreen", "panArrow"];
    const names = [...own, ...Units.art(), ...Effects.art(), ...Hud.art(), ...Orders.art(), ...Panels.art()];
    // A name the file lacks (a missing third strip) needs no art
    return names.map((name) => lib.exported(name)).filter((id) => id !== undefined);
  }

  // The drawing starts DELAY behind the newest update, also on a rejoin, when the whole battle is the newest: nothing
  // moves until the clock reaches it, and from then on it has its cushion against late updates
  restartClock(battle) {
    this.snaps = [{ step: battle.step, s: battle.s }];
    this.events = [];
    this.pausedAt = battle.paused ? battle.step : null;
    this.clock = battle.step - (battle.paused ? 0 : DELAY);
    this.played = battle.step;
  }

  update(u) {
    if (this.waiting?.id === u.id) {
      this.waiting.updates.push(u);
      return;
    }
    if (!this.battle || u.id !== this.battle.id) {
      return;
    }
    const newest = this.newest();
    if (u.step < newest) {
      return;
    }
    // A paused battle's update repeats the step it paused on
    const snap = { step: u.step, s: u.s };
    if (u.step === newest) {
      this.snaps[this.snaps.length - 1] = snap;
    } else {
      this.snaps.push(snap);
    }
    this.events.push(...u.e.filter((event) => event[0] >= this.played));
    this.ending ||= u.e.some((event) => event[1] === "end");
    this.pausedAt = u.paused ? u.step : null;
  }

  // The bot's word that the battle is over: the result stays here, and the results screen comes up
  over(over) {
    if (this.battle?.id !== over.id) {
      return;
    }
    this.result = over.result;
    this.battle.result = over.result;
    this.results.over(over);
  }

  // unloadBattle (F6:6914-6919): the battle goes out of sight under the results screen, which has covered it
  unload() {
    if (this.holder) {
      this.holder.visible = false;
    }
    if (this.hud.clip) {
      this.hud.clip.visible = false;
    }
    this.hideArrow();
  }

  newest() {
    return this.snaps[this.snaps.length - 1].step;
  }

  // ---------- Building ----------

  // buildMap (F6:7267-7379): the map, its cover, its midground strips, the wire and the rain, with the world's layers
  // on top in the original's depth order
  buildWorld(battle) {
    const page = this.page;
    const map = battle.map;
    this.holder = new Container();
    this.holder.zIndex = DEPTH_WORLD;
    page.root.addChild(this.holder);
    const world = page.lib.makeExported(map.art);
    world.label = "world";
    // A new clip holds its first frame for a tick with everything in it, but the world is only a holder: the members
    // put in it on a rejoin step on the very next tick, as their timelines on the bot do
    world.fresh = false;
    this.holder.addChild(world);
    this.world = world;
    this.layers = {};
    for (const [name] of WORLD_LAYERS) {
      this.layers[name] = world.attach(new Layer(), name);
    }
    this.shaking = null;
    this.addCovers(map);
    this.addMidground(map.art);
    this.addWire(map.wire);
    this.camera = { state: "free", width: map.width };
    if (map.rain) {
      this.addRain(map.width);
    }
    this.cameraSetup(battle.you ?? map.side, battle.you === null ? battle.camera : null);
    this.cameraSent = { x: null, at: 0 };
  }

  // Each cover on its lane at its x, lane 1's first (F6:7286-7311), on the frame for its kind
  addCovers(map) {
    const lib = this.page.lib;
    const labels = Object.entries(lib.data.sprites[lib.exported("coverBlock")].labels ?? {});
    this.covers = map.covers.map(([lane, x, kind], index) => {
      const cover = this.layers.cover.addChild(lib.makeExported("coverBlock"));
      cover.label = `cover${index + 1}`;
      cover.zIndex = index + 1;
      const label = labels.find(([name]) => name.toLowerCase() === kind.toLowerCase());
      if (label) {
        cover.gotoAndStop(label[1]);
      } else {
        console.warn("Warfare 1944: no cover art for", kind);
      }
      for (const node of cover.children) {
        const frames = COVER_VARIANTS[node.charId];
        if (frames) {
          node.gotoAndStop(random(frames) + 1);
        }
      }
      cover.position.set(x, map.lanes[lane - 1] - COVER_RISE);
      cover.depth = cover.y;
      return cover;
    });
  }

  // The map's midground strips, after the cover (F6:7313-7340)
  addMidground(art) {
    const lib = this.page.lib;
    this.midGround = [];
    MIDGROUND_Y.forEach((y, index) => {
      const name = `midground_${art}${index + 1}`;
      if (lib.exported(name) === undefined) {
        return;
      }
      const strip = this.layers.cover.addChild(lib.makeExported(name));
      strip.label = `midGround${this.covers.length + index + 1}`;
      strip.zIndex = this.covers.length + index + 1;
      strip.position.set(0, y);
      strip.depth = y;
      this.midGround.push(strip);
    });
  }

  // Each wire line's fence pieces, some turned around, scattered a little about the line (F6:7341-7366)
  addWire(lines) {
    let count = 0;
    for (const x of lines) {
      for (let w = 0; w < WIRE_PIECES; w += 1) {
        count += 1;
        const piece = this.layers.wire.addChild(this.page.lib.makeExported("wireFence"));
        piece.label = `wire${count}`;
        piece.zIndex = count;
        if (random(2) === 0) {
          piece.scale.x = -1;
        }
        piece.gotoAndStop(2);
        piece.position.set(x + w * WIRE_STEP_X + random(WIRE_SPREAD) - WIRE_SPREAD / 2, WIRE_Y + w * WIRE_STEP_Y);
        piece.depth = piece.y;
      }
    }
  }

  // rainEffect (F6:5113-5149): drops fall over the whole field and splash on the ground, with the rain's loop
  addRain(width) {
    const lib = this.page.lib;
    const holder = this.layers.rainHolder;
    for (let n = 1; n < RAIN_DROPS; n += 1) {
      const drop = holder.addChild(lib.makeExported("rainDrop"));
      const splash = holder.addChild(lib.makeExported("rainSplash"));
      drop.zIndex = RAIN_DROP_DEPTH + n;
      splash.zIndex = RAIN_SPLASH_DEPTH + n;
      drop.position.set(random(width), random(RAIN_START_RANGE) + RAIN_START_TOP);
      drop.onEnterFrame = () => {
        drop.x += RAIN_DX;
        drop.y += RAIN_DY;
        if (drop.y > random(RAIN_SPLASH_RANGE) + GROUND) {
          splash.position.set(drop.x, drop.y);
          splash.gotoAndPlay(1);
          drop.position.set(random(width), random(RAIN_START_RANGE) + RAIN_START_TOP);
        }
      };
    }
    sound.loop("sound_ambienceRain", "ambienceRain");
  }

  // The loading screen over a battle that has just started, the pan arrow, and watchers' PAUSED
  startScreen(battle) {
    const page = this.page;
    this.arrow = page.attach("panArrow", DEPTH_HUD + DEPTH_HUD_PAN_ARROW, "panArrow");
    this.arrow.visible = false;
    this.pausedText = this.makePausedText();
    sound.stopMenuMusic(MENU_MUSIC_FADE);
    const seconds = battle.step / FPS;
    if (seconds >= LOADING_HOLD) {
      page.detach("menu");
      sound.loop("sound_ambienceBattle", "ambience");
      return;
    }
    this.showLoadScreen(battle, seconds);
    const menu = page.root.children.find((child) => child.label === "menu" && !child.destroyed);
    if (menu) {
      tweens.alphaTo(menu, 0, MENU_FADE, EASE, MENU_FADE_DELAY, () => {
        if (page.screen === "battle") {
          page.detach("menu");
        }
      });
    }
  }

  // showLoadScreen (F6:802-812): the side's background, the mission's title and a random hint. Its backing takes the
  // pointer, with no hand cursor (S1528/frame_1), so nothing under it can be pressed. It fades out 3 seconds into the
  // battle, and the battle's ambience starts as it goes (F6:6792-6797)
  showLoadScreen(battle, seconds) {
    const page = this.page;
    const load = page.attach("loadScreen", DEPTH_BLACKOUT, "loadScreen");
    load.alpha = 0;
    load.child("bg").gotoAndStop(battle.you ?? battle.map.side);
    load.child("bg").useHandCursor = false;
    load.child("bg").setHandler("onRollOver", () => {});
    load.child("battleHeading").text = battle.map.title ?? "";
    const hint = load.child("hintText");
    hint.box = { ...hint.box, height: hint.box.height * HINT_LINES };
    hint.redraw();
    hint.text = `HINT: ${HINTS[random(HINTS.length)]}`;
    tweens.alphaTo(load, 100, LOADING_IN, EASE);
    const hold = Math.max(LOADING_IN, LOADING_HOLD - seconds);
    tweens.alphaTo(load, 0, LOADING_OUT, EASE, hold, () => {
      if (this.battle?.id === battle.id) {
        sound.loop("sound_ambienceBattle", "ambience");
      }
      page.detach("loadScreen");
    });
  }

  makePausedText() {
    const def = this.page.lib.data.texts[HEADING_TEXT];
    const text = new TextField({ ...def, text: "PAUSED" });
    const [left, , right] = def.bounds;
    text.position.set(STAGE_WIDTH / 2 - (left + right) / 2, PAUSED_Y);
    text.filters = [makeFilter(PAUSED_GLOW, null, this.page.lib.filterScale)];
    text.zIndex = DEPTH_HUD - 1;
    text.label = "pausedText";
    text.visible = false;
    text.draw();
    this.page.root.addChild(text);
    return text;
  }

  showPaused() {
    if (this.pausedText) {
      this.pausedText.visible = this.paused && this.battle?.you === null;
    }
  }

  // ---------- Leaving ----------

  leave() {
    this.clear();
    this.battle = null;
    this.result = null;
    this.waiting = null;
    this.loads += 1;
  }

  clear() {
    const page = this.page;
    for (const fn of this.clearListeners) {
      fn();
    }
    sound.stopLoop("ambience");
    sound.stopLoop("ambienceRain");
    this.holder?.destroy({ children: true });
    this.pausedText?.destroy();
    page.detach("panArrow");
    page.detach("loadScreen");
    Object.assign(this, { holder: null, world: null, layers: {}, arrow: null, pausedText: null, drag: null });
    Object.assign(this, { shaking: null, covers: [], midGround: [] });
    delete document.body.dataset.panning;
  }

  // ---------- The drawn clock ----------

  // Once a page tick (the original's 30 a second): the clock moves, the ticks it passed play, and the camera follows
  // the pointer unless the battle is paused
  step() {
    if (!this.world || !this.battle) {
      return;
    }
    const jumped = this.moveClock();
    while (this.snaps.length > 1 && this.snaps[1].step <= this.clock) {
      this.snaps.shift();
    }
    if (jumped) {
      this.leap();
    }
    while (this.played < Math.floor(this.clock)) {
      this.playTick(this.played, false);
    }
    for (const fn of this.drawListeners) {
      fn();
    }
    this.showPaused();
    if (this.paused) {
      this.hideArrow();
    } else {
      this.cameraControl();
    }
    this.reportCamera();
  }

  // The clock moves on a little faster or slower to stay DELAY behind the newest update, or to reach the step the bot
  // paused on. It never passes the newest update, and jumps when far behind. Returns true on a jump
  moveClock() {
    const newest = this.newest();
    const target = this.pausedAt === null ? newest - DELAY : this.pausedAt;
    if (target - this.clock > JUMP) {
      this.clock = target;
      return true;
    }
    const rate = clamp(1 + (target - this.clock) * STEER, MIN_RATE, MAX_RATE);
    this.clock = Math.min(newest, this.clock + rate);
    return false;
  }

  // The bot's tick n on the page: the clips step, the listeners run, then the tick's events fire
  playTick(n, jumped) {
    this.world.advance();
    this.runShake(n, jumped);
    for (const fn of this.stepListeners) {
      fn(n, jumped);
    }
    this.fireEvents(n, jumped);
    this.played = n + 1;
  }

  // Far behind: every tick passed at once, its events quietly
  leap() {
    const reached = Math.floor(this.clock);
    if (reached > this.played) {
      this.playTick(reached - 1, true);
    }
  }

  // shakeScreen (F6:5167-5191): each shake due by tick n moves the world. After a jump the moment has passed, and the
  // shake ends without moving anything
  runShake(n, jumped) {
    const shake = this.shaking;
    if (!shake) {
      return;
    }
    const elapsed = ((n - shake.start) * 1000) / FPS;
    while (!jumped && shake.done < shake.count && (shake.done + 1) * SHAKE_DELAY_MS <= elapsed) {
      shake.done += 1;
      this.shakeOnce(shake.magnitude);
    }
    if (jumped || shake.done >= shake.count) {
      this.shaking = null;
    }
  }

  shakeOnce(magnitude) {
    const world = this.world;
    world.x -= random(magnitude) - magnitude / 2;
    world.y -= random(magnitude) - magnitude / 2;
    world.y = clamp(world.y, SHAKE_TOP, 0);
    world.x = clamp(world.x, -(this.camera.width + SHAKE_PAST_END), 0);
  }

  fireEvents(upTo, quiet) {
    while (this.events.length && this.events[0][0] <= upTo) {
      const event = this.events.shift();
      for (const fn of this.handlers.get(event[1]) ?? []) {
        fn(event, quiet);
      }
    }
  }

  // ---------- The camera ----------

  // cameraSetup (F6:1204-1223): the German side starts at its own end of the field, world x = -(width - 900)
  // Flash keeps _x in whole twips (twentieths of a pixel), cut toward zero, which lets the pan rule take one more
  // step on a field whose width has more decimals (the custom short map, 1218.17 wide, stops at 358, not 338)
  // A watcher starts where the player it watches was looking (`looking`, the player's world x), when the bot knows
  cameraSetup(side, looking = null) {
    if (typeof looking === "number") {
      this.world.x = clamp(looking, STAGE_WIDTH - this.camera.width, 0);
      return;
    }
    const x = side === "german" ? -this.camera.width + GERMAN_START : 0;
    this.world.x = clamp(Math.trunc(x * TWIPS) / TWIPS, STAGE_WIDTH - this.camera.width, 0);
  }

  // A player's page tells the bot where its camera is, now and then, for the watchers who arrive later
  reportCamera() {
    if (this.battle.you === null) {
      return;
    }
    const x = Math.round(this.world.x);
    const now = performance.now();
    if (x === this.cameraSent.x || now - this.cameraSent.at < CAMERA_SEND_MS) {
      return;
    }
    if (this.page.send({ camera: x })) {
      this.cameraSent = { x, at: now };
    }
  }

  // The pointer's place on the stage, kept from the canvas's own events so a pointer that left the stage, or a
  // finger that lifted, scrolls nothing
  listen() {
    if (this.listening) {
      return;
    }
    this.listening = true;
    const canvas = this.page.app.canvas;
    canvas.addEventListener("pointermove", (e) => this.pointerMoved(e));
    canvas.addEventListener("pointerdown", (e) => this.pointerDown(e));
    for (const name of ["pointerup", "pointercancel"]) {
      canvas.addEventListener(name, (e) => this.pointerUp(e));
    }
    canvas.addEventListener("pointerleave", () => {
      this.pointer.inside = false;
    });
    document.addEventListener("keydown", (e) => this.keyDown(e));
  }

  readPointer(e) {
    const box = this.page.app.canvas.getBoundingClientRect();
    const pointer = this.pointer;
    pointer.x = ((e.clientX - box.left) * STAGE_WIDTH) / box.width;
    pointer.y = ((e.clientY - box.top) * STAGE_HEIGHT) / box.height;
    pointer.touch = e.pointerType === "touch";
    pointer.inside = true;
  }

  pointerMoved(e) {
    this.readPointer(e);
    const drag = this.drag;
    if (!drag || !this.world) {
      return;
    }
    if (!drag.moving && Math.abs(this.pointer.x - drag.from) >= this.slop()) {
      drag.moving = true;
    }
    if (drag.moving && !this.paused) {
      this.world.x = clamp(drag.worldX + this.pointer.x - drag.from, STAGE_WIDTH - this.camera.width, 0);
    }
  }

  // A press on the field above the HUD may become a drag that scrolls it
  pointerDown(e) {
    this.readPointer(e);
    this.pointer.down = true;
    if (this.world && this.pointer.y < HUD_TOP) {
      this.drag = { from: this.pointer.x, worldX: this.world.x, moving: false };
    }
  }

  pointerUp(e) {
    this.readPointer(e);
    this.pointer.down = false;
    this.pointer.inside = !this.pointer.touch;
    this.drag = null;
  }

  // How far a press moves, in stage pixels, before it is a drag and not a tap
  slop() {
    const scale = this.page.world.scale.x;
    return this.pointer.touch ? Math.max(DRAG_START, TOUCH_DRAG_PX / scale) : DRAG_START;
  }

  // True while the press now held has scrolled the field, so a press handler can tell a drag from a click
  get dragging() {
    return this.drag?.moving === true;
  }

  // True when the pointer event `e` is a drag's distance from the press that began at `from` ({ x, y } in screen
  // pixels), or the press scrolled the field: a lift that is no tap
  swept(from, e) {
    const scale = this.page.world.scale.x;
    const far = Math.max(Math.abs(e.global.x - from.x), Math.abs(e.global.y - from.y)) / scale;
    return this.dragging || far >= this.slop();
  }

  // cameraControl (F6:1224-1263): the field scrolls while the pointer rests near a side above the HUD, with the pan
  // arrow in place of the pointer. A finger scrolls this way only while it is down, and a drag scrolls by itself
  cameraControl() {
    this.hideArrow();
    const pointer = this.pointer;
    if (this.camera.state === "locked" || !pointer.inside || (pointer.touch && !pointer.down) || this.dragging) {
      return;
    }
    const world = this.world;
    if (pointer.x <= PAN_BUFFER && pointer.y <= PAN_BLOCK && world.x <= -PAN_BUFFER) {
      world.x += PAN_SPEED;
      this.showArrow(-1, pointer.x <= PAN_BUFFER / 3 ? 0 : pointer.x - this.arrow.width / 2);
    }
    const end = -this.camera.width + STAGE_WIDTH + PAN_BUFFER;
    if (pointer.x >= STAGE_WIDTH - PAN_BUFFER && pointer.y <= PAN_BLOCK && world.x > end) {
      world.x -= PAN_SPEED;
      const x = pointer.x >= STAGE_WIDTH - PAN_BUFFER / 2 ? STAGE_WIDTH : pointer.x + this.arrow.width / 2;
      this.showArrow(1, x);
    }
  }

  showArrow(facing, x) {
    this.arrow.scale.x = facing;
    this.arrow.position.set(x, this.pointer.y);
    this.arrow.visible = true;
    document.body.dataset.panning = "true";
  }

  hideArrow() {
    if (this.arrow) {
      this.arrow.visible = false;
    }
    delete document.body.dataset.panning;
  }

  // cameraPanKeys (F6:1264-1277): the arrow keys scroll 20 pixels a press, and again with each key repeat
  keyDown(e) {
    const blocked = this.paused || this.panels.menu || this.camera.state === "locked";
    if (!this.world || this.page.screen !== "battle" || blocked) {
      return;
    }
    if (e.key === "ArrowLeft" && this.world.x <= -PAN_BUFFER) {
      this.world.x += PAN_SPEED;
    } else if (e.key === "ArrowRight" && this.world.x > -this.camera.width + STAGE_WIDTH + PAN_BUFFER) {
      this.world.x -= PAN_SPEED;
    } else {
      return;
    }
    e.preventDefault();
  }
}

export const field = new Field();
