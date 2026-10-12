// Particles, thrown bodies, blood, the floating "+n" of experience, death sounds and voices: everything the original
// drew or said for the look of a battle without changing its outcome (particleEmitter and moveParticle F5:3088-3150,
// the kinds F5:3151-3203, bodyRagdoll F5:3204-3318, updateExperience F5:5969-6033, playVoice F5:5792-5840).
//
// None of it is the bot's to decide, so every roll here is the page's own Math.random, and the bot never hears of it.
// The strike module calls emit() on each blast and bullet hit it draws, and the units module calls the death hook
// just before a soldier's death animation starts, the order the original does the same things in. The rest listens to
// the field's events.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { positionAt } from "./units.js";

const SIDES = ["british", "german"];
const HOW_BULLET = 0;
const HOW_BLAST = 1;
const HOW_GAS = 2;

// emitParticles' rows: [clip, gravity, extra particles, sideways energy, upward energy, fade a step, spin a step,
// sized at random, turned at random, sideways spread of the place, rise of the place]. A row makes extra + 1 particles
// (the original counts i from 0 up to and including the quantity)
const EMITTERS = {
  artilleryExplosion: [
    ["particle_dustShaft", 0.015, 0, 0, 0.5, 1.75, 0.01, true, true, 0, 0],
    ["particle_dustShaft", 0.015, 0, 0, 0.5, 1.75, 0.01, true, false, 0, 0],
    ["particle_cloudDust", 0.01, 0, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_cloudDust_white", 0.01, 0, 0.5, 0.5, 1, 0.05, true, true, 0, 0],
    ["particle_fireball", 0.015, 0, 0, 0.5, 3, 0, true, false, 0, 0],
    ["particle_cloudDust", 0.01, 0, 1.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_sparks", 0.4, 0, 4, 10, 6, 1.5, true, true, 50, 20],
    ["particle_dirt", 0.4, 1, 4, 10, 2, 1.5, true, true, 50, 20],
    ["particle_dirt2", 0.35, 1, 4, 10, 2, 0, true, true, 50, 20],
  ],
  mortarExplosion: [
    ["particle_dustShaft_mortar", 0.015, 0, 0, 0.5, 1.75, 0.05, true, false, 0, 0],
    ["particle_cloudDust_mortar", 0.01, 0, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_dirt", 0.4, 0, 2, 10, 2, 1.5, true, true, 10, 10],
    ["particle_fireball_mortar", 0.015, 0, 0, 0.5, 2, 0, true, false, 0, 0],
    ["particle_dirt2_mortar", 0.35, 0, 3, 8, 2, 0, true, true, 10, 10],
    ["particle_cloudDust_mortar", 0.01, 0, 4, 0.5, 2, 0.05, true, false, 20, 0],
  ],
  bulletDust: [
    ["particle_dustShaft_bullet", 0.015, 0, 0, 0.5, 1.75, 0.05, true, false, 0, 0],
    ["particle_cloudDust_bullet", 0.01, 1, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_dirt2_bullet", 0.4, 1, 1, 1, 6, 1.5, true, true, 50, 20],
  ],
  bloodCloud: [["particle_bloodCloud", 0.01, 0, 0.5, 0.5, 3, 0.05, true, true, 0, 0]],
  grenadeExplosion: [
    ["particle_dustShaft_grenade", 0.015, 0, 0, 0.5, 1.75, 0.05, true, false, 0, 0],
    ["particle_cloudDust_grenade", 0.01, 1, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_dirt", 0.4, 1, 2, 10, 2, 1.5, true, true, 0, 10],
    ["particle_fireball_grenade", 0.015, 0, 0, 0.5, 2, 0, true, false, 0, 0],
    ["particle_dirt2_grenade", 0.35, 1, 3, 8, 2, 0, true, true, 0, 10],
    ["particle_cloudDust_grenade", 0.01, 1, 4, 0.5, 2, 0.05, true, false, 0, 0],
  ],
  mineExplosion: [
    ["particle_dustShaft_mortar", 0.015, 0, 0, 0.5, 1.75, 0.05, true, false, 0, 0],
    ["particle_cloudDust_mortar", 0.01, 0, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_dirt", 0.4, 3, 2, 10, 2, 1.5, true, true, 10, 10],
    ["particle_fireball_mortar", 0.015, 0, 0, 0.5, 2, 0, true, false, 0, 0],
    ["particle_dirt2_mortar", 0.35, 2, 3, 8, 2, 0, true, true, 10, 10],
    ["particle_cloudDust_mortar", 0.01, 1, 4, 0.5, 2, 0.05, true, false, 20, 0],
  ],
  metalFragment: [["particle_metalFragment", 0.4, 6, 2, 8, 0, 1.5, true, true, 10, 10]],
};
// A particle: 70 to 99 percent seen, goes when under 15 or when it has fallen 10 below where it started
const ALPHA_LOW = 70;
const ALPHA_SPREAD = 30;
const ALPHA_GONE = 15;
const FALL_GONE = 10;
const SIZE_LOW = 50;
const SIZE_SPREAD = 50;
// A turned particle's angle: under 60 either way round
const TURN_SPREAD = 60;
const TURN_BACK = 300;
// The fireball a shell or blast leaves on a tank (F5:2949-2953): sprite 333's own fireball is turned and sized by its
// placement script, and the particle goes by itself when its timeline ends
const TANK_FIREBALL = "particle_fireball_tank";
const TANK_FIREBALL_PART = 299;
const TANK_FIREBALL_PART_DEPTH = 1;
const TANK_FIREBALL_ROTATE = 360;
const TANK_FIREBALL_SIZE_LOW = 40;
const TANK_FIREBALL_SIZE_SPREAD = 60;
const TANK_FIREBALL_X = 10;
const TANK_FIREBALL_RISE = 15;
const TANK_FIREBALL_RISE_LOW = 15;

// bodyRagdoll (F5:3204-3318): a soldier thrown by a blast loses limbs, then flies and lands. In a trench it starts 60
// pixels out toward the enemy's side of its own
const TRENCH_THROW = 60;
const THROW_SIDEWAYS = 6;
const THROW_UP = 11;
const THROW_GRAVITY = 0.45;
const THROW_TURN = 60;
const THROW_SPIN_LOW = 4;
const THROW_SPIN_SPREAD = 8;
// A body lands when it is this far above where the soldier first stood, and is put 2 above it
const LAND_ABOVE = 5;
const LAND_PUT = 2;
// What each of the ten throws takes off, as [part, frame] pairs, and where blood shows (the part's bloodSplat)
const LIMBS = [
  { off: [], blood: ["torso"] },
  {
    off: [["front_upperArm", "gone"], ["front_lowerArm", "gone"]],
    blood: ["torso", "head"],
  },
  { off: [["back_upperArm", "gone"], ["back_lowerArm", "gone"]], blood: ["torso"] },
  {
    off: [["front_upperLeg", "gone"], ["front_lowerLeg", "gone"], ["front_foot", "gone"]],
    blood: [],
  },
  {
    off: [["back_upperLeg", "gone"], ["back_lowerLeg", "gone"], ["back_foot", "gone"]],
    blood: [],
  },
  {
    off: [
      ["front_upperLeg", "gone"],
      ["front_lowerLeg", "gone"],
      ["front_foot", "gone"],
      ["back_upperLeg", "gone"],
      ["back_lowerLeg", "gone"],
      ["back_foot", "gone"],
    ],
    blood: [],
  },
  {
    off: [
      ["front_upperArm", "gone"],
      ["front_lowerArm", "gone"],
      ["back_upperArm", "gone"],
      ["back_lowerArm", "gone"],
    ],
    blood: ["torso", "head"],
  },
  { off: [["head", "gone"]], blood: ["torso"] },
  {
    off: [
      ["head", "off"],
      ["front_upperArm", "off"],
      ["front_lowerArm", "gone"],
      ["back_upperArm", "off"],
      ["back_lowerArm", "gone"],
      ["torso", "gone"],
    ],
    blood: [],
  },
  { off: [], blood: [] },
];
// A shot or blast death shows blood on the torso and on the head 1 time in 10 each (F5:2848-2857, 3038-3048)
const BLOOD_ONE_IN = 10;
// The blood cloud of a blast death rises from the body up to 15 pixels (F5:3054)
const BLOOD_RISE = 15;

// updateExperience's float (F5:6008-6033): it rises over 4 seconds while it fades in over 1, holds 1 and fades out in 1
const XP_RISE_BY = 30;
const XP_RISE_SECONDS = 4;
const XP_FADE_SECONDS = 1;
const EASE = "easeOutSine";

// soldierDeath1 to 6 exist of the 10 the original picks from (F5:2882, 3051), so 4 in 10 deaths are silent
const DEATH_PICKS = 10;
const DEATH_SOUNDS = 6;

// playVoice (F5:5792-5840): a voice is called one time in `oneIn`, `count` files to pick from, and plays after a delay
// of random(spread) + least milliseconds. The files that don't exist (the Germans have no attack calls, a fifth
// "advance" or a third sniper) stay silent
const VOICES = {
  advance: { oneIn: 6, count: 6, spread: 600, least: 100 },
  attack: { oneIn: 20, count: 3, spread: 600, least: 100 },
  sniper: { oneIn: 3, count: 3, spread: 600, least: 100 },
  incoming: { oneIn: 20, count: 4, spread: 600, least: 400 },
  machineGun: { oneIn: 20, count: 3, spread: 10, least: 100 },
  gas: { oneIn: 4, count: 0, spread: 10, least: 100 },
  tank: { oneIn: 10, count: 2, spread: 900, least: 100 },
};
// A blast reaches a squad whose leader is within 60 pixels of it (F5:2909-2918)
const BLAST_REACH = 60;
// A gas strike throws two rounds 1.1 seconds apart (gasStrike, F5:3612-3621) and the original calls the voice once
// when the strike is called: only a round with none of the same side's in the second before it calls it here
const GAS_QUIET_STEPS = 70;
// Which shooters make which death cry: a sharpshooter's, a machine gun crew's and a tank's kills (F5:2862-2880)
const KILLER_VOICE = {
  sharpShooter: "sniper",
  machineGunner: "machineGun",
  mgAssist: "machineGun",
  tankMarkIV: "tank",
};

// Flash's random(n): a whole number from 0 to n - 1
function random(n) {
  return Math.floor(Math.random() * n);
}

export class Particles {
  constructor(field) {
    this.field = field;
    // The original's counter that gives each new particle a depth above the last
    this.count = 0;
    this.xpCount = 0;
    // Where the newest blast landed, for the hits on tanks that follow it in the same step
    this.lastBlast = { x: 0, y: 0 };
    // The soldier who fired the newest shot, whose bullet the next death comes from
    this.lastShooter = null;
    this.lastGas = [-Infinity, -Infinity];
    this.timers = new Set();
    field.onClear(() => this.reset());
    field.onEvent("shot", (event, quiet) => this.shot(event, quiet));
    field.onEvent("die", (event, quiet) => this.died(event, quiet));
    field.onEvent("blast", (event, quiet) => this.blast(event, quiet));
    field.onEvent("tankhit", (event, quiet) => this.tankHit(quiet));
    field.onEvent("round", (event, quiet) => this.round(event, quiet));
    field.onEvent("xp", (event, quiet) => this.xp(event, quiet));
    field.units.onDeath((unit, how, exploded, quiet) => this.death(unit, how, exploded, quiet));
    field.units.onAdvance((unit) => this.voice("advance", unit.side));
  }

  get lib() {
    return this.field.page.lib;
  }

  get units() {
    return this.field.units;
  }

  // The clips this module draws, loaded with the battlefield's
  static art() {
    const names = new Set(["xpIcon", TANK_FIREBALL]);
    for (const rows of Object.values(EMITTERS)) {
      rows.forEach((row) => names.add(row[0]));
    }
    return [...names];
  }

  reset() {
    this.timers.forEach((timer) => clearTimeout(timer));
    this.timers.clear();
    this.lastShooter = null;
    this.lastGas = [-Infinity, -Infinity];
  }

  // ---------- Particles ----------

  // One of the kinds above at a place on the field (the original's xxxExplosionParticle functions)
  emit(kind, x, y) {
    for (const row of EMITTERS[kind] ?? []) {
      this.emitRow(row, x, y);
    }
  }

  // particleEmitter (F5:3088-3132) for one row. The place is shifted once for the whole row
  emitRow(row, x, y) {
    const [clip, gravity, extra, sideways, upward, fade, spin, sized, turned, spread, rise] = row;
    const at = { x: x + (spread ? random(spread) - spread / 2 : 0), y: y - rise };
    for (let n = 0; n <= extra; n += 1) {
      this.particle({ clip, gravity, sideways, upward, fade, spin, sized, turned }, at);
    }
  }

  particle(look, at) {
    const layer = this.field.layer("particles");
    if (!layer) {
      return;
    }
    const part = this.lib.makeExported(look.clip);
    part.fresh = false;
    // Sideways energy goes either way; upward energy is negative (up) plus up to half again of it
    const sideways = Math.random() * look.sideways * (random(2) > 0 ? 1 : -1);
    const motion = {
      vertical: -look.upward + (Math.random() * look.upward) / 2,
      alpha: random(ALPHA_SPREAD) + ALPHA_LOW,
    };
    // An unturned particle has no angle, so the original's sideways step comes out as nothing and it stays upright
    let angle = null;
    if (look.turned) {
      angle = random(2) > 0 ? random(TURN_SPREAD) : random(TURN_SPREAD) + TURN_BACK;
      part.angle = angle;
    }
    if (look.sized) {
      const size = (random(SIZE_SPREAD) + SIZE_LOW) / 100;
      part.scale.set(size, size);
    }
    part.alpha = motion.alpha / 100;
    part.position.set(at.x, at.y);
    this.count += 1;
    part.zIndex = this.count;
    layer.addChild(part);
    const originY = at.y;
    // moveParticle (F5:3133-3150)
    part.onEnterFrame = () => {
      motion.alpha -= look.fade;
      part.alpha = Math.max(0, motion.alpha) / 100;
      if (motion.alpha < ALPHA_GONE || part.y > originY + FALL_GONE) {
        part.removeMovieClip();
        return;
      }
      part.angle += look.spin;
      if (angle !== null) {
        part.x -= Math.cos((angle * Math.PI) / 180) * sideways;
      }
      motion.vertical += look.gravity;
      part.y += motion.vertical;
    };
  }

  // A blast or shell that hits a tank leaves a fireball above it, a spray of metal and a clang (F5:2949-2954). The
  // bot says which tank; the blast that hit it came the step before, so its place is the fireball's
  tankHit(quiet) {
    const layer = this.field.layer("particles");
    if (quiet || !layer) {
      return;
    }
    const { x, y } = this.lastBlast;
    const fire = this.lib.makeExported(TANK_FIREBALL);
    fire.fresh = false;
    const inner = fire.at(TANK_FIREBALL_PART_DEPTH);
    if (inner && inner.charId === TANK_FIREBALL_PART) {
      const size = (random(TANK_FIREBALL_SIZE_SPREAD) + TANK_FIREBALL_SIZE_LOW) / 100;
      inner.angle = random(TANK_FIREBALL_ROTATE);
      inner.scale.set(size, size);
    }
    fire.position.set(
      x + random(TANK_FIREBALL_X) - TANK_FIREBALL_X / 2,
      y - (random(TANK_FIREBALL_RISE) + TANK_FIREBALL_RISE_LOW),
    );
    this.count += 1;
    fire.zIndex = this.count;
    layer.addChild(fire);
    this.emit("metalFragment", x, y);
    sound.play("sound_metalImpact");
  }

  // ---------- Bodies ----------

  // A soldier dies (before its death animation starts). A thrown one loses limbs and flies; any other shot or blast
  // death may show blood, and a blast death rises as a cloud of it
  death(unit, how, exploded, quiet) {
    const clip = unit.clip;
    if (exploded) {
      this.ragdoll(clip);
    } else if (how !== HOW_GAS) {
      for (const part of ["torso", "head"]) {
        if (random(BLOOD_ONE_IN) === 0) {
          this.bleed(clip, part);
        }
      }
    }
    if (how === HOW_BLAST && !quiet) {
      this.emit("bloodCloud", clip.x, clip.y - random(BLOOD_RISE));
    }
  }

  bleed(clip, part) {
    const splat = clip.child(part)?.child("bloodSplat");
    if (splat) {
      splat.visible = true;
    }
  }

  // bodyRagdoll (F5:3204-3318): in a trench the body starts 60 pixels toward the field's middle, a limb or two come
  // off, then it flies on its own energy until it comes down on the ground it first stood on, and lies there flat
  ragdoll(clip) {
    const unit = clip.unit;
    if (positionAt(clip.frame) === "trench") {
      clip.x += unit.side === "british" ? TRENCH_THROW : -TRENCH_THROW;
    }
    const limbs = LIMBS[random(LIMBS.length)];
    for (const [part, frame] of limbs.off) {
      clip.child(part)?.gotoAndStop(frame);
    }
    limbs.blood.forEach((part) => this.bleed(clip, part));
    const flight = {
      sideways: Math.random() * THROW_SIDEWAYS * (random(2) > 0 ? 1 : -1),
      vertical: -THROW_UP + (Math.random() * THROW_UP) / 2,
      angle: 0,
      spin: 0,
    };
    if (random(2) > 0) {
      flight.angle = random(THROW_TURN);
      flight.spin = random(THROW_SPIN_SPREAD) + THROW_SPIN_LOW;
    } else {
      flight.angle = random(THROW_TURN) + TURN_BACK;
      flight.spin = -random(THROW_SPIN_SPREAD) + THROW_SPIN_LOW;
    }
    // The body fades 15 seconds after it lands, not after it died
    unit.diedAt = Infinity;
    clip.onEnterFrame = () => this.fly(clip, unit, flight);
  }

  fly(clip, unit, flight) {
    clip.angle += flight.spin;
    clip.x -= Math.cos((flight.angle * Math.PI) / 180) * flight.sideways;
    flight.vertical += THROW_GRAVITY;
    clip.y += flight.vertical;
    if (clip.y <= unit.ground - LAND_ABOVE) {
      return;
    }
    clip.y = unit.ground - LAND_PUT;
    clip.onEnterFrame = null;
    clip.angle = random(2) > 0 ? 0 : 180;
    clip.gotoAndPlay("flatDead");
    unit.diedAt = this.field.drawnStep;
  }

  // ---------- Experience ----------

  // updateExperience's "+n" (F5:6008-6033): it starts clear, fades in over a second while it rises 30 pixels over 4,
  // then fades out over a second after holding one
  xp(event, quiet) {
    if (!quiet) {
      const [, , x10, y10, amount] = event;
      this.xpFloat(x10 / 10, y10 / 10, amount);
    }
  }

  xpFloat(x, y, amount) {
    const layer = this.field.layer("xpIcons");
    if (!layer) {
      return;
    }
    const icon = this.lib.makeExported("xpIcon");
    icon.fresh = false;
    const text = icon.child("exp");
    if (text) {
      text.text = String(amount);
    }
    icon.alpha = 0;
    icon.position.set(x, y);
    this.xpCount += 1;
    icon.zIndex = this.xpCount;
    layer.addChild(icon);
    tweens.ySlideTo(icon, y - XP_RISE_BY, XP_RISE_SECONDS, EASE);
    tweens.alphaTo(icon, 100, XP_FADE_SECONDS, EASE);
    tweens.alphaTo(icon, 0, XP_FADE_SECONDS, EASE, XP_FADE_SECONDS, () => icon.removeMovieClip());
  }

  // ---------- Sounds and voices ----------

  // A shot: a rifleman firing in the open calls out (F5:1603), and the shot is remembered for the death it may cause
  shot(event, quiet) {
    const shooter = this.units.members.get(event[2]);
    this.lastShooter = shooter ?? null;
    if (quiet || !shooter || shooter.kind !== "soldier" || shooter.type === "machineGunner") {
      return;
    }
    if (positionAt(shooter.clip.frame) !== "trench") {
      this.voice("attack", shooter.side);
    }
  }

  // A death: its sound, and the cry of a victim who wasn't the squad's first, shot by a sharpshooter, a machine gun
  // crew or a tank (F5:2862-2880, 3051)
  died(event, quiet) {
    const [, , id, how] = event;
    const unit = this.units.members.get(id);
    if (quiet || !unit || how === HOW_GAS) {
      return;
    }
    const pick = random(DEATH_PICKS) + 1;
    if (pick <= DEATH_SOUNDS) {
      sound.play(`sound_soldierDeath${pick}`);
    }
    const cry = how === HOW_BULLET ? KILLER_VOICE[this.lastShooter?.type] : null;
    const squad = this.units.squads.get(unit.squadId);
    if (cry && squad?.order?.[0] !== id) {
      this.voice(cry, unit.side);
    }
  }

  // A blast: where it landed, and every soldier of the other side near it calls "incoming" (F5:2919-2925)
  blast(event, quiet) {
    this.lastBlast = { x: event[3] / 10, y: event[4] / 10 };
    if (quiet) {
      return;
    }
    const owner = SIDES[event[5]];
    for (const squad of this.units.squads.values()) {
      const order = squad.order ?? [];
      const leader = this.units.members.get(order[0]);
      if (!leader || leader.dead || leader.side === owner || Math.abs(leader.x - this.lastBlast.x) >= BLAST_REACH) {
        continue;
      }
      order.forEach(() => this.voice("incoming", leader.side));
    }
  }

  // A gas strike makes the other side shout "gas" (F5:3426-3434)
  round(event, quiet) {
    const [step, , kind, , , owner] = event;
    if (kind !== "gas" || quiet || step - this.lastGas[owner] < GAS_QUIET_STEPS) {
      return;
    }
    this.lastGas[owner] = step;
    this.voice("gas", SIDES[1 - owner]);
  }

  // playVoice (F5:5792-5840): one call of a kind of voice for a side
  voice(kind, side) {
    const voice = VOICES[kind];
    if (random(voice.oneIn) !== 0) {
      return;
    }
    const name = voice.count ? `sound_voice_${side}_${kind}${random(voice.count) + 1}` : `sound_voice_${side}_${kind}1`;
    if (!(name in this.lib.data.sounds)) {
      return;
    }
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      sound.play(name);
    }, random(voice.spread) + voice.least);
    this.timers.add(timer);
  }
}
