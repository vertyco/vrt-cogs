// Strikes, blasts, grenades, tank shells, mines and gas on the field, with their sounds: the pictures of what the bot
// decided (sections F5:3319-3720 and the strike clips' frame scripts).
//
// The bot starts each strike clip, mine, shell and grenade on a step and lands its blast on the clip's blast frame.
// The page starts the same clip on the step the event names and steps it one frame a drawn step, so the clip's blast
// frame comes on the very step the bot's blast does. Those frames draw the explosion and its scorch mark here; the
// hits, deaths and damage come from the bot. A blast whose clip the page never played (a rejoin, a jump) is drawn from
// the bot's "blast" event instead.
//
// Gas clouds follow the bot's list of clouds: each appears on its "gas" event, fades from the step the bot says over
// 2 seconds, and goes with its strike clip when the fade ends.
import { Particles } from "./particles.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { MAIN_WEAPON } from "./units.js";

const FPS = 35;
const SIDES = ["british", "german"];
// The strike clips (F5:3463-3629, 3713-3720), their sprites and the frame each one's blast lands on
const STRIKES = {
  mortar: { name: "mortarStrike", sprite: 346, blast: 101 },
  artillery: { name: "artilleryStrike", sprite: 329, blast: 152 },
  antiTank: { name: "antiTankStrike", sprite: 343, blast: 82 },
  gas: { name: "gasStrikeAnim", sprite: 334, blast: 152 },
  mine: { name: "mineStrike", sprite: 345, blast: 16 },
  shell: { name: "tankRound", sprite: 347, blast: 6 },
};
// handGrenade (sprite 1376): its two throw arcs by label, each bursting on its last frame (frames 41 and 83)
const GRENADE = { name: "handGrenade", sprite: 1376, bursts: [41, 83] };
// The collision box every strike clip places on its first frame, hidden by its placement script
const COLLISION = 325;
// The grenade's own picture (sprite 1375): a German grenade is the stick grenade (its placement script in 1376)
const GRENADE_PICTURE_DEPTH = 1;
// What each blast frame calls (the frame scripts of 346, 329, 343, 345, 347, 1376 and 334): which explosion, and
// which scorch mark (artilleryScorchDecal is the large one, mortarScorchDecal the small)
const BLASTS = {
  mortar: { explosion: "mortar", scorch: "small" },
  artillery: { explosion: "artillery", scorch: "large" },
  antiTank: { explosion: "mortar", scorch: "large" },
  mine: { explosion: "mine", scorch: "small" },
  shell: { explosion: "mortar", scorch: "small" },
  grenade: { explosion: "grenade", scorch: null },
  // gasExplosion (F5:3347-3379) only sounds like a mortar; the cloud comes with the "gas" event
  gas: { explosion: "gas", scorch: null },
};
// mortarExplosion, mineExplosion, artilleryExplosion and grenadeExplosion (F5:3319-3342): a particle burst and one of
// a few explosion sounds. gasExplosion plays a mortar's
const EXPLOSION_SOUNDS = {
  mortar: ["sound_mortar_explosion", 2],
  artillery: ["sound_artillery_explosion", 3],
  mine: ["sound_mine_explosion", 2],
  grenade: ["sound_grenade_explosion", 2],
  gas: ["sound_mortar_explosion", 2],
};
// artilleryScorchDecal and mortarScorchDecal (F5:3499-3569): size random(spread) + low percent, see-through
// random(spread) + low percent; each fades over 6 seconds after decalRemoveDelay, 15 seconds (F5:7285)
const SCORCH = {
  large: { size: [90, 40], alpha: [70, 30] },
  small: { size: [50, 20], alpha: [80, 20] },
};
const DECAL_DELAY = 15;
const DECAL_FADE = 6;
// hitEnemy's walk over the target (F5:2816-2904): against a tank a ricochet random(10) <= 8, on one of its 11
// ricochet clips; bullet dust random(100) <= showBulletDustChance (8, F5:7269), up to 60 pixels either side
const RICOCHET_ROLL = 10;
const RICOCHETS = 11;
const DUST_ROLL = 100;
const DUST_CHANCE = 8;
const DUST_SPREAD = 120;
// bulletDust (F5:3343-3348): the hit sound comes up to a tenth of a second after the dust
const DUST_SOUND_DELAY = 100;
// gasCloudCollisions plays sound_soldierCough1 to 5 on a gas death (F5:3672); there is no fifth, so 1 in 5 is silent
const COUGH_PICKS = 5;
const COUGH_SOUNDS = 4;
const HOW_GAS = 2;
// gasExplosion (F5:3347-3379): the cloud turned at random; it fades over 2 seconds (easeOutSine) once its time is up
const GAS_TURNS = 360;
const GAS_FADE_STEPS = 2 * FPS;
// A cloud gone from every update without its fade (an update lost to a jump) goes this many steps later
const GONE_AFTER = 4;
// throwGrenade (F5:5759-5791): the grenade lands 30 short of the target's leader, give or take 20, and 10 to 29 below
// it (a tank: 5 either side). The page finds that leader again from the landing point
const GRENADE_SHORT = 30;
const GRENADE_DROP = 19.5;

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

export class Effects {
  constructor(field) {
    this.field = field;
    this.world = null;
    // Clips the page steps on: { clip, at }, at the drawn step its frame stands for
    this.clips = [];
    // Blasts a clip's blast frame drew, by kind and place, until the bot's "blast" event for them comes
    this.bursts = new Map();
    // Gas strike clips waiting for their cloud, by place; clouds by the bot's id
    this.gasStrikes = new Map();
    this.clouds = new Map();
    // The original's counters, which set each new clip's depth in its layer
    this.rounds = 0;
    this.grenades = 0;
    this.decals = 0;
    // True while clips catch up quietly: their sounds and particles are skipped, what lasts stays
    this.hushed = false;
    // The particle bursts, drawn by the particle module. Kinds: "<explosion>Explosion", "bulletDust"
    this.particles = new Particles(field);
    this.emitter = (kind, x, y) => this.particles.emit(kind, x, y);
    field.onLoad((battle) => this.load(battle));
    field.onDrawnStep((n) => this.tick(n));
    field.onClear(() => this.reset());
    field.onEvent("round", (event, quiet) => this.round(event, quiet));
    field.onEvent("mine", (event, quiet) => this.mine(event, quiet));
    field.onEvent("shell", (event, quiet) => this.shell(event, quiet));
    field.onEvent("grenade", (event, quiet) => this.grenade(event, quiet));
    field.onEvent("blast", (event, quiet) => this.blast(event, quiet));
    field.onEvent("gas", (event, quiet) => this.gas(event, quiet));
    field.onEvent("shot", (event, quiet) => this.shot(event, quiet));
    field.onEvent("die", (event, quiet) => this.died(event, quiet));
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
      GRENADE.name,
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
    this.lib.scripts.set(GRENADE.sprite, (clip, frame) => this.blastFrame(clip, frame));
    // A rejoin finds the clouds already out
    for (const row of battle.s?.g ?? []) {
      if (!this.clouds.has(row[0])) {
        this.makeCloud(row[0], row[1] / 10, row[2] / 10, null, true);
      }
    }
  }

  reset() {
    this.clips = [];
    this.bursts.clear();
    this.gasStrikes.clear();
    this.clouds.clear();
    this.world = null;
  }

  // The bot's tick n, after the world's clips stepped: clips that missed ticks (a jump) catch up, and the clouds
  // fade and go
  tick(n) {
    if (!this.world || this.world !== this.field.world) {
      return;
    }
    this.clips = this.clips.filter(({ clip }) => !clip.removed && !clip.destroyed);
    for (const item of this.clips) {
      this.catchUp(item.clip, n - item.at - 1);
      item.at = n;
    }
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
  // from the start when its moment has passed
  make(name, quiet) {
    const lib = this.lib;
    const clip = lib.create(lib.exported(name));
    clip.onHook = (kind, arg, node) => {
      if (this.hushed && (kind === "sound" || kind === "incoming")) {
        return true;
      }
      return lib.onHook?.(kind, arg, node) ?? false;
    };
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

  // A strike's round starts playing at its spot (artilleryRound, mortarRound, antiTankRound and gasRound,
  // F5:3466-3629), on the artillery layer; a German anti-tank round is turned around (F5:3584-3587)
  round(event, quiet) {
    const [stamp, , kind, x10, y10, owner] = event;
    if (!STRIKES[kind]) {
      return;
    }
    const clip = this.strikeClip(kind, x10, y10, quiet);
    if (kind === "antiTank" && SIDES[owner] === "german") {
      clip.scale.x = -1;
    }
    this.rounds += 1;
    this.place(clip, "artillery", this.rounds, x10 / 10, y10 / 10, stamp);
    if (kind === "gas") {
      this.gasStrikes.set(key(kind, x10, y10), clip);
    }
  }

  // The clip at its first frame, playing; the mortar, artillery and anti-tank clips wait stopped on frame 1 until
  // their round's delay is up, then play (F5:3483)
  strikeClip(kind, x10, y10, quiet) {
    const clip = this.make(STRIKES[kind].name, quiet);
    clip.effect = { kind, key: key(kind, x10, y10) };
    for (const slot of clip.slots.values()) {
      if (slot.node.charId === COLLISION) {
        slot.node.visible = false;
      }
    }
    clip.play();
    return clip;
  }

  // A mine goes off: the mine clip clicks on its first frame and bursts on frame 16
  mine(event, quiet) {
    const [stamp, , x10, y10] = event;
    const clip = this.strikeClip("mine", x10, y10, quiet);
    this.rounds += 1;
    this.place(clip, "artillery", this.rounds, x10 / 10, y10 / 10, stamp);
  }

  // A tank's main gun fires (F5:2074-2080): its sound, and the shell clip (tankRound, F5:3713-3720) where it lands
  shell(event, quiet) {
    const [stamp, , , x10, y10] = event;
    if (!quiet) {
      sound.play("sound_tankMainGunFire");
    }
    const clip = this.strikeClip("shell", x10, y10, quiet);
    this.rounds += 1;
    this.place(clip, "artillery", this.rounds, x10 / 10, y10 / 10, stamp);
  }

  // A clip's blast frame (the frame scripts of 346 frame 101, 329 frame 152, 343 frame 82, 345 frame 16, 347 frame 6,
  // 334 frame 152 and 1376 frames 41 and 83): the explosion and its scorch mark
  blastFrame(clip, frame) {
    const effect = clip.effect;
    const strike = strikeOf(clip.charId);
    const due = strike ? STRIKES[strike].blast === frame : GRENADE.bursts.includes(frame);
    if (!effect || !due) {
      return;
    }
    this.bursts.set(effect.key, this.field.drawnStep);
    this.explode(effect.kind, clip.x, clip.y, this.hushed);
  }

  // The bot's blast. Its clip's blast frame has drawn it already, unless the page never played that clip
  blast(event, quiet) {
    const [, , kind, x10, y10] = event;
    const id = key(kind, x10, y10);
    if (this.bursts.has(id)) {
      this.bursts.delete(id);
      return;
    }
    this.explode(kind, x10 / 10, y10 / 10, quiet);
  }

  // mortarExplosion and its siblings (F5:3319-3342) and the scorch decals (F5:3499-3569). Quiet: only the scorch
  explode(kind, x, y, quiet) {
    const blast = BLASTS[kind];
    if (!blast) {
      return;
    }
    if (!quiet) {
      if (blast.explosion !== "gas") {
        this.emitter(`${blast.explosion}Explosion`, x, y);
      }
      const [stem, count] = EXPLOSION_SOUNDS[blast.explosion];
      sound.play(`${stem}${random(count) + 1}`);
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
    tweens.alphaTo(decal, 0, DECAL_FADE, "easeOutSine", DECAL_DELAY, () => decal.removeMovieClip());
  }

  // ---------- Grenades ----------

  // throwGrenade (F5:5759-5791): the grenade clip at its landing point on the grenade layer, turned along the throw,
  // upside down for a British throw and a stick grenade for a German one, playing its arc
  grenade(event, quiet) {
    const [stamp, , throwerId, x10, y10, arc] = event;
    const thrower = this.units.members.get(throwerId);
    const side = thrower?.side ?? "british";
    const x = x10 / 10;
    const y = y10 / 10;
    const clip = this.make(GRENADE.name, quiet);
    clip.effect = { kind: "grenade", key: key("grenade", x10, y10) };
    if (side === "german") {
      clip.at(GRENADE_PICTURE_DEPTH)?.gotoAndStop("stick");
    }
    if (thrower) {
      const leader = this.leaderNear(side, x, y);
      const angle = Math.round((Math.atan2(-(thrower.y - leader.y), thrower.x - leader.x) / Math.PI) * 180);
      clip.angle = -angle;
    }
    if (side === "british") {
      clip.scale.y = -1;
    }
    this.hushed = quiet;
    clip.gotoAndPlay(`throw${arc}`);
    this.hushed = false;
    this.grenades += 1;
    this.place(clip, "grenade", this.grenades, x, y, stamp);
  }

  // The enemy leader the grenade was thrown at: the one nearest where the throw aims, given its landing point
  leaderNear(side, x, y) {
    const aimX = x + (side === "british" ? GRENADE_SHORT : -GRENADE_SHORT);
    let best = null;
    let bestDistance = Infinity;
    for (const squad of this.units.squads.values()) {
      const leader = (squad.order ?? [])
        .map((id) => this.units.members.get(id))
        .find((unit) => unit && !unit.dead && !unit.wrecked);
      if (!leader || leader.side === side) {
        continue;
      }
      const aimY = leader.kind === "tank" ? y : y - GRENADE_DROP;
      const distance = Math.hypot(leader.x - aimX, leader.y - aimY);
      if (distance < bestDistance) {
        best = leader;
        bestDistance = distance;
      }
    }
    return best ?? { x: aimX, y: y - GRENADE_DROP };
  }

  // ---------- Gas ----------

  // gasExplosion (F5:3347-3379): the cloud at the round's spot, above its strike clip
  gas(event, quiet) {
    const [, , id, x10, y10] = event;
    if (this.clouds.has(id)) {
      return;
    }
    const strikeKey = key("gas", x10, y10);
    const strike = this.gasStrikes.get(strikeKey) ?? null;
    this.gasStrikes.delete(strikeKey);
    this.makeCloud(id, x10 / 10, y10 / 10, strike, quiet);
  }

  makeCloud(id, x, y, strike, settled) {
    const clip = this.lib.makeExported("gasCloud");
    clip.angle = random(GAS_TURNS);
    if (settled) {
      clip.gotoAndStop(clip.totalFrames);
    }
    this.rounds += 1;
    this.place(clip, "artillery", this.rounds, x, y, this.field.drawnStep);
    this.clouds.set(id, { clip, strike, fadeStart: null, seen: this.field.drawnStep });
  }

  // Each cloud's fade starts on the step the bot gives and lasts 2 seconds of drawn steps, so a pause holds it; the
  // cloud and its strike clip go when it ends (clearGas, F5:3687-3712)
  followClouds(n) {
    for (const snap of this.field.snaps) {
      for (const row of snap.s.g ?? []) {
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
      const t = fading ? Math.min(1, (n - cloud.fadeStart) / GAS_FADE_STEPS) : 0;
      cloud.clip.alpha = 1 - Math.sin((t * Math.PI) / 2);
      if (t >= 1 || n > cloud.seen + GONE_AFTER) {
        cloud.clip.removeMovieClip();
        cloud.strike?.removeMovieClip();
        this.clouds.delete(id);
      }
    }
  }

  // A soldier killed by gas coughs (F5:3672)
  died(event, quiet) {
    const pick = random(COUGH_PICKS) + 1;
    if (!quiet && event[3] === HOW_GAS && pick <= COUGH_SOUNDS) {
      sound.play(`sound_soldierCough${pick}`);
    }
  }

  // ---------- Shots ----------

  // A shot (F5:1580 and siblings, 2090-2097): the weapon's sound, then hitEnemy's walk over the target squad
  // (F5:2816-2904): ricochets off a tank, and a puff of dust that ends the walk
  shot(event, quiet) {
    const [, , shooterId, targetId, atTank] = event;
    const shooter = this.units.members.get(shooterId);
    if (quiet || !shooter) {
      return;
    }
    if (shooter.kind === "tank") {
      // The tank's machine gun is a Lewis gun with its own tracer
      sound.play(`sound_lewis_fire${random(2) + 1}`);
      shooter.clip.child("tracer")?.play();
    } else {
      sound.play(`sound_${MAIN_WEAPON[shooter.side][shooter.type]}_fire${random(2) + 1}`);
    }
    const squadId = this.units.squadOf(targetId);
    const order = this.units.squads.get(squadId)?.order ?? [targetId];
    for (const id of order) {
      const unit = this.units.members.get(id);
      if (!unit || unit.dead || unit.wrecked) {
        continue;
      }
      if (atTank && unit.kind === "tank" && random(RICOCHET_ROLL) <= DUST_CHANCE) {
        sound.play(`sound_ricochetMetal${random(2) + 1}`);
        unit.clip.child(`ricochet${random(RICOCHETS) + 1}`)?.play();
      }
      if (random(DUST_ROLL) <= DUST_CHANCE) {
        this.bulletDust(unit.x + random(DUST_SPREAD) - DUST_SPREAD / 2, unit.y);
        break;
      }
    }
  }

  bulletDust(x, y) {
    this.emitter("bulletDust", x, y);
    const name = `sound_bulletHit${random(2) + 1}`;
    setTimeout(() => sound.play(name), random(DUST_SOUND_DELAY));
  }
}
