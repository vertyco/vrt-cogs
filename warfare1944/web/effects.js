// Strikes, blasts, rockets, grenades, smoke screens, the plane, damage reports and shots on the field, with their
// sounds: the pictures of what the bot decided (F6:5046-5084 and 5192-5524, bazookaFire F6:9756-9813,
// reportTankDamage F6:9911-9931, hitEnemy's looks F6:4425-4434, and the strike clips' frame scripts).
//
// The bot starts each strike clip, mine, shell and grenade on a step and lands its blast on the clip's blast frame.
// The page starts the same clip on the step the event names and steps it one frame a drawn step, so the clip's blast
// frame comes on the very step the bot's blast does. Those frames draw the explosion, its scorch mark and the screen
// shake here; the hits, deaths and damage come from the bot. A blast whose clip the page never played (a rejoin, a
// jump, a rocket's scattered burst) is drawn from the bot's "blast" event instead.
//
// Smoke screens follow the bot's list of screens (state "k"): each fades from the step the bot says over 2 seconds,
// and goes when the fade ends.
import { Particles } from "./particles.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { MAIN_WEAPON } from "./units.js";

const FPS = 30;
const SIDES = ["british", "german"];
// The strike clips started by a "round", "mine" or "shell" event (artilleryRound, airSupportRound, mortarRound,
// smokeRound F6:5242-5500, findMines, tankRound), their sprites and the frame whose script draws the blast. The smoke
// round's frame 100 only makes the screen, which comes from the bot's "smoke" event
const STRIKES = {
  artillery: { name: "artilleryStrike", sprite: 410, blast: 152 },
  airSupport: { name: "airSupportStrike", sprite: 437, blast: 7 },
  mortar: { name: "mortarStrike", sprite: 427, blast: 101 },
  smoke: { name: "smokeStrikeAnim", sprite: 415, blast: null },
  mine: { name: "mineStrike", sprite: 426, blast: 16 },
  shell: { name: "tankRound", sprite: 428, blast: 6 },
};
// The thrown grenades (sprites 1580 and 1589): their two throw arcs by label, from frame 2 or 48, each bursting on
// frame 41 or 83. The smoke grenade's burst frames call smokeGrenadeRound, whose screen comes from the bot's "smoke"
// event
const ARCS = [
  [2, 41],
  [48, 83],
];
const GRENADES = {
  frag: { name: "handGrenade", sprite: 1580, bursts: ARCS.map((arc) => arc[1]) },
  smoke: { name: "smokeGrenade", sprite: 1589, bursts: [] },
};
// smokeGrenadeRound's clip (sprite 1590) makes its screen on its frame 2, the step after the burst, and calls
// gasExplosion twice there, so a smoke grenade's screen is two clouds on one spot; a smoke round's is one
const GRENADE_SCREEN_DELAY = 1;
const GRENADE_CLOUDS = 2;
// The grenade's own picture (sprites 1579 and 1588 at depth 1): a German grenade is the stick grenade (the placement
// scripts in 1580 and 1589)
const GRENADE_PICTURE_DEPTH = 1;
// The bazooka round (1584) and the bazooka strike (1586, whose frame 1 script draws a mortar explosion)
const ROCKET = "bazookaRound";
const ROCKET_STRIKE = "bazookaStrike";
// bazookaSpeed (F6:11811): how far a rocket flies a step, for one that leaves the field without bursting
const ROCKET_SPEED = 35;
// The plane (aircraft_british, sprite 2209): its "aircraft" part shows the German plane at its "german" frame
const PLANE = "aircraft_british";
// The collision box every strike clip places on its first frame, hidden by its placement script
const COLLISION = 406;
// What each blast frame calls: which explosion, which scorch mark (artilleryScorchDecal is the large one,
// mortarScorchDecal the small) and how the screen shakes (screenShake(magnitude, times))
const BLASTS = {
  artillery: { explosion: "artillery", scorch: "large", shake: [10, 14] },
  airSupport: { explosion: "airSupport", scorch: null, shake: null },
  mortar: { explosion: "mortar", scorch: "small", shake: [3, 8] },
  mine: { explosion: "mine", scorch: "small", shake: [3, 8] },
  shell: { explosion: "mortar", scorch: "small", shake: [3, 8] },
  bazooka: { explosion: "mortar", scorch: "small", shake: [3, 8] },
  grenade: { explosion: "grenade", scorch: null, shake: null },
};
// mortarExplosion, mineExplosion, artilleryExplosion, grenadeExplosion and airSupportExplosion (F6:5046-5084): a
// particle burst and one of a few sounds
const EXPLOSIONS = {
  mortar: { particles: "mortarExplosion", sound: ["sound_mortar_explosion", 2] },
  mine: { particles: "mineExplosion", sound: ["sound_mine_explosion", 2] },
  artillery: { particles: "artilleryExplosion", sound: ["sound_artillery_explosion", 3] },
  grenade: { particles: "grenadeExplosion", sound: ["sound_grenade_explosion", 2] },
  airSupport: { particles: "airSupportDust", sound: ["sound_bulletHit", 2] },
};
// artilleryScorchDecal and mortarScorchDecal (F6:5269-5285, 5411-5424): size random(spread) + low percent,
// see-through random(spread) + low percent; each fades over 6 seconds after decalRemoveDelay, 15 seconds (F6:10959)
const SCORCH = {
  large: { size: [90, 40], alpha: [70, 30] },
  small: { size: [50, 20], alpha: [80, 20] },
};
const DECAL_DELAY = 15;
const DECAL_FADE = 6;
// hitEnemy's looks (F6:4425-4434, 4514-4517): against a tank a ricochet random(10) <= 8, on one of its 11 ricochet
// clips; bullet dust random(100) <= showBulletDustChance (8, F6:10919), up to 60 pixels either side
const RICOCHET_ROLL = 10;
const RICOCHETS = 11;
const DUST_ROLL = 100;
const DUST_CHANCE = 8;
const DUST_SPREAD = 120;
// bulletDust (F6:5079-5084): the hit sound comes up to a tenth of a second after the dust
const DUST_SOUND_DELAY = 100;
// A screen is turned at random; it fades over 2 seconds (easeOutSine) once its time is up
const CLOUD_TURNS = 360;
const CLOUD_FADE_STEPS = 2 * FPS;
// A screen gone from every update without its fade (an update lost to a jump) goes this many steps later
const GONE_AFTER = 4;
// reportTankDamage (F6:9911-9931): the line starts at y -87, slides to -110 over 4 seconds, shows over 1 and fades
// over 3 after 1
const REPORT_TEXT = { mg: "MG DESTROYED!", gun: "MAIN GUN DESTROYED!", engine: "ENGINE DAMAGED!" };
const REPORT_Y = -87;
const REPORT_TO_Y = -110;
const REPORT_SLIDE = 4;
const REPORT_IN = 1;
const REPORT_OUT = 3;
const EASE = "easeOutSine";

// Flash's random(n): a whole number from 0 to n - 1. Only for what the page draws
function random(n) {
  return Math.floor(Math.random() * n);
}

function key(kind, x10, y10) {
  return `${kind}:${x10}:${y10}`;
}

function strikeOf(sprite) {
  return Object.keys(STRIKES).find((kind) => STRIKES[kind].sprite === sprite) ?? null;
}

function hideCollision(clip) {
  for (const slot of clip.slots.values()) {
    if (slot.node.charId === COLLISION) {
      slot.node.visible = false;
    }
  }
}

export class Effects {
  constructor(field) {
    this.field = field;
    this.world = null;
    // Clips the page steps on: { clip, at }, at the drawn step its frame stands for
    this.clips = [];
    // Rockets in flight: { clip, x0, y0, dx, dy, stamp, steps }
    this.rockets = [];
    // Blasts a clip's blast frame drew, by kind and place, until the bot's "blast" event for them comes
    this.bursts = new Map();
    // Smoke screens by the bot's id: { clips, fadeStart, seen }
    this.clouds = new Map();
    // The steps smoke grenades in the air make their screens on
    this.grenadeScreens = [];
    // The original's counters, which set each new clip's depth in its layer
    this.rounds = 0;
    this.grenades = 0;
    this.rocketCount = 0;
    this.impacts = 0;
    this.fighters = 0;
    this.decals = 0;
    // True while clips catch up quietly: their sounds and particles are skipped, what lasts stays
    this.hushed = false;
    // The particle bursts, drawn by the particle module
    this.particles = new Particles(field);
    this.emitter = (kind, x, y) => this.particles.emit(kind, x, y);
    field.onLoad((battle) => this.load(battle));
    field.onDrawnStep((n) => this.tick(n));
    field.onClear(() => this.reset());
    field.onEvent("round", (event, quiet) => this.round(event, quiet));
    field.onEvent("mine", (event, quiet) => this.mine(event, quiet));
    field.onEvent("shell", (event, quiet) => this.shell(event, quiet));
    field.onEvent("grenade", (event, quiet) => this.grenade(event, quiet));
    field.onEvent("rocket", (event, quiet) => this.rocket(event, quiet));
    field.onEvent("plane", (event, quiet) => this.plane(event, quiet));
    field.onEvent("smoke", (event) => this.smoke(event));
    field.onEvent("blast", (event, quiet) => this.blast(event, quiet));
    field.onEvent("report", (event, quiet) => this.report(event, quiet));
    field.onEvent("shot", (event, quiet) => this.shot(event, quiet));
  }

  get lib() {
    return this.field.page.lib;
  }

  get units() {
    return this.field.units;
  }

  // The clips' art, loaded with the battlefield's
  static art() {
    return [
      ...Object.values(STRIKES).map((strike) => strike.name),
      ...Object.values(GRENADES).map((grenade) => grenade.name),
      ROCKET,
      ROCKET_STRIKE,
      PLANE,
      "gasCloud",
      "decal_artilleryScorch",
      ...Particles.art(),
    ];
  }

  // ---------- The battle ----------

  load(battle) {
    if (this.world !== this.field.world) {
      this.reset();
      this.world = this.field.world;
    }
    // The blast frames are the page's: they draw the explosion; the bot's blast does the rest
    for (const strike of Object.values(STRIKES)) {
      this.lib.scripts.set(strike.sprite, (clip, frame) => this.blastFrame(clip, frame));
    }
    this.lib.scripts.set(GRENADES.frag.sprite, (clip, frame) => this.blastFrame(clip, frame));
    // A rejoin finds the screens already out
    for (const row of battle.s?.k ?? []) {
      if (!this.clouds.has(row[0])) {
        this.makeCloud(row[0], row[1] / 10, row[2] / 10, row[4], true);
      }
    }
  }

  reset() {
    this.clips = [];
    this.rockets = [];
    this.bursts.clear();
    this.clouds.clear();
    this.grenadeScreens = [];
    this.world = null;
  }

  // The bot's tick n, after the world's clips stepped: clips that missed ticks (a jump) catch up, a smoke round's clip
  // goes once it stops (its last frame is never reached), rockets fly, and the screens fade and go
  tick(n) {
    if (!this.world || this.world !== this.field.world) {
      return;
    }
    this.clips = this.clips.filter(({ clip }) => !clip.removed && !clip.destroyed);
    for (const item of this.clips) {
      this.catchUp(item.clip, n - item.at - 1);
      item.at = n;
      if (item.clip.effect?.kind === "smoke" && !item.clip.playing) {
        item.clip.removeMovieClip();
      }
    }
    this.flyRockets(n);
    this.followClouds(n);
  }

  // Steps a clip on quietly, stopping once it stops or goes
  catchUp(clip, steps) {
    this.hushed = true;
    for (let k = 0; k < steps && clip.playing && !clip.removed && !clip.destroyed; k += 1) {
      clip.advance();
    }
    this.hushed = false;
  }

  // A clip of this module, its first frame run: its whistles and firing sounds stay quiet while it catches up, and
  // from the start when its moment has passed. `ready` sets it up before its first frame's script runs
  make(name, quiet, ready = null) {
    const lib = this.lib;
    const clip = lib.create(lib.exported(name));
    clip.onHook = (kind, arg, node) => {
      if (this.hushed && (kind === "sound" || kind === "incoming" || kind === "soundpick")) {
        return true;
      }
      return lib.onHook?.(kind, arg, node) ?? false;
    };
    ready?.(clip);
    this.hushed = quiet;
    clip.start();
    this.hushed = false;
    return clip;
  }

  // The clip goes on the field on the step its event names, and steps from the next one, as the bot's does. One whose
  // event the drawing reached late (a jump) catches up by the steps it missed
  place(clip, layerName, depth, x, y, stamp) {
    clip.fresh = false;
    clip.position.set(x, y);
    clip.zIndex = depth;
    this.field.layer(layerName).addChild(clip);
    const now = this.field.drawnStep;
    this.catchUp(clip, now - stamp);
    this.clips.push({ clip, at: now });
  }

  // ---------- Strikes, mines and shells ----------

  // A strike's round starts playing at its spot (artilleryRound, airSupportRound, mortarRound and smokeRound), on the
  // artillery layer
  round(event, quiet) {
    const [stamp, , kind, x10, y10] = event;
    if (!STRIKES[kind] || kind === "mine" || kind === "shell") {
      return;
    }
    this.strike(kind, x10, y10, stamp, quiet);
  }

  // The clip at its spot on its first frame, playing: the artillery, air support and mortar clips wait stopped on
  // frame 1 until their round's delay is up, then play (F6:5255 and siblings)
  strike(kind, x10, y10, stamp, quiet) {
    const x = x10 / 10;
    const y = y10 / 10;
    const clip = this.make(STRIKES[kind].name, quiet, (made) => {
      made.effect = { kind, key: key(kind, x10, y10) };
      made.position.set(x, y);
    });
    hideCollision(clip);
    clip.play();
    this.rounds += 1;
    this.place(clip, "artillery", this.rounds, x, y, stamp);
  }

  // A mine goes off (findMines): the mine clip clicks on its first frame and bursts on frame 16
  mine(event, quiet) {
    const [stamp, , x10, y10] = event;
    this.strike("mine", x10, y10, stamp, quiet);
  }

  // A tank's or the bunker's main gun fires (F6:3109-3111 and the tank's): its sound, and the shell clip (tankRound)
  // where it lands
  shell(event, quiet) {
    const [stamp, , , x10, y10] = event;
    if (!quiet) {
      sound.play("sound_tankMainGunFire");
    }
    this.strike("shell", x10, y10, stamp, quiet);
  }

  // A clip's blast frame (410 frame 152, 437 frame 7, 427 frame 101, 426 frame 16, 428 frame 6, and 1580 frames 41
  // and 83): the explosion, its scorch mark and the shake. The smoke round's frame 100 draws nothing
  blastFrame(clip, frame) {
    const effect = clip.effect;
    const strike = strikeOf(clip.charId);
    const due = strike ? STRIKES[strike].blast === frame : GRENADES.frag.bursts.includes(frame);
    if (!effect || !due) {
      return;
    }
    this.bursts.set(effect.key, this.field.drawnStep);
    this.explode(effect.kind, clip.x, clip.y, this.hushed);
  }

  // The bot's blast. Its clip's blast frame has drawn it already, unless the page never played that clip. A rocket's
  // burst is the bazooka strike clip at the scattered spot (bazookaImpact, F6:9806-9813)
  blast(event, quiet) {
    const [stamp, , kind, x10, y10] = event;
    if (kind === "bazooka") {
      this.bazookaStrike(x10 / 10, y10 / 10, stamp, quiet);
      return;
    }
    const id = key(kind, x10, y10);
    if (this.bursts.has(id)) {
      this.bursts.delete(id);
      return;
    }
    this.explode(kind, x10 / 10, y10 / 10, quiet);
  }

  // The explosions (F6:5046-5084) and the scorch decals. Quiet: only the scorch
  explode(kind, x, y, quiet) {
    const blast = BLASTS[kind];
    if (!blast) {
      return;
    }
    if (!quiet) {
      const explosion = EXPLOSIONS[blast.explosion];
      this.emitter(explosion.particles, x, y);
      const [stem, count] = explosion.sound;
      sound.play(`${stem}${random(count) + 1}`);
      if (blast.shake) {
        this.field.shake(...blast.shake);
      }
    }
    if (blast.scorch) {
      this.scorch(blast.scorch, x, y);
    }
  }

  scorch(size, x, y) {
    const look = SCORCH[size];
    const decal = this.lib.makeExported("decal_artilleryScorch");
    const scale = (random(look.size[1]) + look.size[0]) / 100;
    decal.scale.set(scale, scale);
    decal.alpha = (random(look.alpha[1]) + look.alpha[0]) / 100;
    decal.position.set(x, y);
    this.decals += 1;
    decal.zIndex = this.decals;
    decal.fresh = false;
    this.field.layer("decals").addChild(decal);
    tweens.alphaTo(decal, 0, DECAL_FADE, EASE, DECAL_DELAY, () => decal.removeMovieClip());
  }

  // ---------- Grenades ----------

  // throwGrenade and throwSmokeGrenade (F6:8473-8546): the grenade clip at its landing point on the grenade layer,
  // turned along the throw, upside down for an American throw and a stick grenade for a German one, playing its arc.
  // The original turned it toward the member it aimed at; the landing point is within 20 of it
  grenade(event, quiet) {
    const [stamp, , throwerId, x10, y10, arc, kind] = event;
    const look = GRENADES[kind] ?? GRENADES.frag;
    const thrower = this.units.members.get(throwerId);
    const side = thrower?.side ?? "british";
    const x = x10 / 10;
    const y = y10 / 10;
    const clip = this.make(look.name, quiet, (made) => {
      made.effect = { kind: kind === "smoke" ? "smokeGrenade" : "grenade", key: key("grenade", x10, y10) };
      made.position.set(x, y);
    });
    if (side === "german") {
      clip.at(GRENADE_PICTURE_DEPTH)?.gotoAndStop("stick");
    }
    if (thrower) {
      const angle = Math.round((Math.atan2(-(thrower.y - y), thrower.x - x) / Math.PI) * 180);
      clip.angle = -angle;
    }
    if (side === "british") {
      clip.scale.y = -1;
    }
    if (kind === "smoke") {
      const [start, burst] = ARCS[arc - 1];
      this.grenadeScreens.push(stamp + burst - start + GRENADE_SCREEN_DELAY);
    }
    this.hushed = quiet;
    clip.gotoAndPlay(`throw${arc}`);
    this.hushed = false;
    this.grenades += 1;
    this.place(clip, "grenade", this.grenades, x, y, stamp);
  }

  // ---------- Rockets ----------

  // bazookaFire (F6:9756-9805): the round leaves the bazooka man, turned along its line (the German one mirrored),
  // and flies 35 pixels a step to where it bursts. It goes on the step it bursts; one that never bursts goes once it
  // has flown off the field
  rocket(event, quiet) {
    const [stamp, , shooterId, x0, y0, x1, y1, burst] = event;
    const shooter = this.units.members.get(shooterId);
    const side = shooter?.side ?? (x1 >= x0 ? "british" : "german");
    const start = { x: x0 / 10, y: y0 / 10 };
    const end = { x: x1 / 10, y: y1 / 10 };
    const distance = Math.hypot(end.x - start.x, end.y - start.y);
    const steps = burst >= 0 ? burst - stamp : Math.ceil(distance / ROCKET_SPEED);
    if (quiet || steps <= 0 || this.field.drawnStep >= stamp + steps) {
      return;
    }
    const clip = this.lib.makeExported(ROCKET);
    clip.fresh = false;
    if (side === "german") {
      clip.scale.x = -1;
    }
    clip.angle = (Math.atan2(start.y - end.y, start.x - end.x) * 180) / Math.PI;
    clip.position.set(start.x, start.y);
    this.rocketCount += 1;
    clip.zIndex = this.rocketCount;
    this.field.layer("bazookaRounds").addChild(clip);
    this.rockets.push({ clip, start, end, stamp, steps });
    this.flyRockets(this.field.drawnStep);
  }

  // Each rocket where its flight has it on step n: one step further along its line a step, gone once it bursts
  flyRockets(n) {
    this.rockets = this.rockets.filter((rocket) => {
      const flown = n - rocket.stamp;
      if (flown >= rocket.steps || rocket.clip.destroyed) {
        rocket.clip.removeMovieClip();
        return false;
      }
      const t = Math.max(0, flown) / rocket.steps;
      rocket.clip.position.set(
        rocket.start.x + (rocket.end.x - rocket.start.x) * t,
        rocket.start.y + (rocket.end.y - rocket.start.y) * t,
      );
      return true;
    });
  }

  // bazookaImpact (F6:9806-9813): the bazooka strike clip at the burst, whose first frame draws a mortar explosion,
  // its scorch and the shake
  bazookaStrike(x, y, stamp, quiet) {
    const clip = this.make(ROCKET_STRIKE, true);
    hideCollision(clip);
    this.explode("bazooka", x, y, quiet);
    this.impacts += 1;
    this.place(clip, "bazookaImpacts", this.impacts, x, y, stamp);
  }

  // ---------- The plane ----------

  // airStrike (F6:5286-5305): the plane over the aimed point, the German one at its own frame and mirrored. Its
  // engine, guns and muzzle flashes are its own frames' hooks
  plane(event, quiet) {
    const [stamp, , x10, y10, owner] = event;
    const clip = this.make(PLANE, quiet);
    if (SIDES[owner] === "german") {
      clip.child("aircraft")?.gotoAndStop("german");
      clip.scale.x = -1;
    }
    this.fighters += 1;
    this.place(clip, "fighter", this.fighters, x10 / 10, y10 / 10, stamp);
  }

  // ---------- Damage reports ----------

  // reportTankDamage (F6:9911-9931): the line over the tank, the right way round on a German one, rising and fading
  report(event, quiet) {
    const [, , tankId, part] = event;
    const clip = this.units.tank(tankId);
    const report = clip?.child("damageReport");
    if (quiet || !report || !REPORT_TEXT[part]) {
      return;
    }
    const line = report.child("damage");
    if (line) {
      line.text = REPORT_TEXT[part];
    }
    report.y = REPORT_Y;
    report.scale.x = clip.scale.x < 0 ? -Math.abs(report.scale.x) : Math.abs(report.scale.x);
    report.alpha = 0;
    tweens.ySlideTo(report, REPORT_TO_Y, REPORT_SLIDE, EASE);
    tweens.alphaTo(report, 100, REPORT_IN, EASE);
    tweens.alphaTo(report, 0, REPORT_OUT, EASE, REPORT_IN);
  }

  // ---------- Smoke screens ----------

  // gasExplosion (F6:5085-5110): a screen appears, each of its clouds turned at random, and plays its puff
  smoke(event) {
    const [stamp, , id, x10, y10, , , fadeStart] = event;
    const thrown = this.grenadeScreens.indexOf(stamp);
    if (thrown >= 0) {
      this.grenadeScreens.splice(thrown, 1);
    }
    this.grenadeScreens = this.grenadeScreens.filter((due) => due > stamp);
    if (!this.clouds.has(id)) {
      this.makeCloud(id, x10 / 10, y10 / 10, fadeStart, false, thrown >= 0 ? GRENADE_CLOUDS : 1);
    }
  }

  makeCloud(id, x, y, fadeStart, settled, count = 1) {
    const clips = [];
    for (let k = 0; k < count; k += 1) {
      const clip = this.lib.makeExported("gasCloud");
      clip.angle = random(CLOUD_TURNS);
      if (settled) {
        clip.gotoAndStop(clip.totalFrames);
      }
      this.rounds += 1;
      this.place(clip, "artillery", this.rounds, x, y, this.field.drawnStep);
      clips.push(clip);
    }
    this.clouds.set(id, { clips, fadeStart: fadeStart >= 0 ? fadeStart : null, seen: this.field.drawnStep });
  }

  // Each screen's fade starts on the step the bot gives and lasts 2 seconds of drawn steps, so a pause holds it; the
  // screen goes when it ends
  followClouds(n) {
    for (const snap of this.field.snaps) {
      for (const row of snap.s.k ?? []) {
        const cloud = this.clouds.get(row[0]);
        if (cloud) {
          cloud.seen = Math.max(cloud.seen, snap.step);
          if (row[4] >= 0) {
            cloud.fadeStart = row[4];
          }
        }
      }
    }
    for (const [id, cloud] of this.clouds) {
      const fading = cloud.fadeStart !== null && n >= cloud.fadeStart;
      const t = fading ? Math.min(1, (n - cloud.fadeStart) / CLOUD_FADE_STEPS) : 0;
      const alpha = 1 - Math.sin((t * Math.PI) / 2);
      cloud.clips.forEach((clip) => {
        clip.alpha = alpha;
      });
      if (t >= 1 || n > cloud.seen + GONE_AFTER) {
        cloud.clips.forEach((clip) => clip.removeMovieClip());
        this.clouds.delete(id);
      }
    }
  }

  // ---------- Shots ----------

  // A shot (F6:2514 and siblings, the tank's and bunker's machine gun F6:3126-3135): the weapon's sound, then
  // hitEnemy's looks on the target squad's newest member (F6:4425-4434): against a tank a ricochet and a chance of
  // dust; then, unless the bullet killed that member, another chance of dust (F6:4514-4517). A shot naming no member
  // (a bazooka man's, a mortar carrier's) lands no bullet
  shot(event, quiet) {
    const [, , shooterId, targetId, atTank] = event;
    const shooter = this.units.members.get(shooterId);
    if (quiet || !shooter) {
      return;
    }
    this.fireSound(shooter);
    if (!targetId || shooter.type === "mortarCarrier") {
      return;
    }
    const member = this.newestMember(targetId);
    if (!member) {
      return;
    }
    if (atTank && member.kind === "tank") {
      if (random(RICOCHET_ROLL) <= DUST_CHANCE) {
        sound.play(`sound_ricochetMetal${random(2) + 1}`);
        member.clip.child(`ricochet${random(RICOCHETS) + 1}`)?.play();
      }
      this.dustChance(member);
    }
    // The bot's death for this bullet, if any, comes among this step's events: the dust waits until they are all out
    queueMicrotask(() => {
      if (!member.dead) {
        this.dustChance(member);
      }
    });
  }

  fireSound(shooter) {
    let name;
    if (shooter.kind === "tank") {
      name = `sound_${shooter.side === "british" ? "lewis" : "mg42"}_fire${random(2) + 1}`;
      shooter.clip.child("tracer")?.play();
    } else {
      name = `sound_${MAIN_WEAPON[shooter.side]?.[shooter.type]}_fire${random(2) + 1}`;
    }
    if (name in this.lib.data.sounds) {
      sound.play(name);
    }
  }

  // The newest living member of the squad the shot member is in
  newestMember(memberId) {
    const squadId = this.units.squadOf(memberId);
    const order = this.units.squads.get(squadId)?.order ?? [memberId];
    for (let k = order.length - 1; k >= 0; k -= 1) {
      const unit = this.units.members.get(order[k]);
      if (unit && !unit.dead && !unit.wrecked) {
        return unit;
      }
    }
    return null;
  }

  dustChance(member) {
    if (random(DUST_ROLL) <= DUST_CHANCE) {
      this.bulletDust(member.x + random(DUST_SPREAD) - DUST_SPREAD / 2, member.y);
    }
  }

  bulletDust(x, y) {
    this.emitter("bulletDust", x, y);
    const name = `sound_bulletHit${random(2) + 1}`;
    setTimeout(() => sound.play(name), random(DUST_SOUND_DELAY));
  }
}
