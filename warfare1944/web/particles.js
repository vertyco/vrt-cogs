// Particles, thrown bodies, blood, the floating "+n" of experience and the floating RP, death sounds and voices:
// everything the original drew or said for the look of a battle without changing its outcome (particleEmitter and
// moveParticle F6:4820-4882, the kinds F6:4883-4941, bodyRagdoll F6:4942-5045, updateExperience F6:8771-8850, adjustRP
// F6:1345-1423, playVoice F6:8556-8638).
//
// None of it is the bot's to decide, so every roll here is the page's own Math.random, and the bot never hears of it.
// The strike module calls emit() on each blast and bullet hit it draws, and the units module calls the death hook
// just before a soldier's death animation starts, the order the original does the same things in. The rest listens to
// the field's events.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const SIDES = ["british", "german"];
const HOW_BULLET = 0;
const HOW_BLAST = 1;

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
  // airSupportDustParticle (F6:4904-4909)
  airSupportDust: [
    ["particle_dustShaft_bulletLarge", 0.015, 1, 0, 0.5, 1.75, 0.05, true, false, 0, 0],
    ["particle_cloudDust_bulletLarge", 0.01, 2, 0.5, 0.5, 1.5, 0.05, true, true, 0, 0],
    ["particle_dirt2_bulletLarge", 0.4, 2, 1, 1, 6, 1.5, true, true, 50, 20],
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
// The dust shafts of the mortar, bullet and grenade (sprites 387, 403 and 420) face either way, 1 time in 2 (the
// placement scripts of S2213/frame_2)
const FLIPPED_SHAFTS = new Set(["particle_dustShaft_mortar", "particle_dustShaft_bullet", "particle_dustShaft_grenade"]);
// The fireball a shell or blast leaves on a tank (F6:4590-4593, 4655-4658): sprite 414's own fireball part (380) is
// turned and sized by its placement script, and the particle goes by itself when its timeline ends
const TANK_FIREBALL = "particle_fireball_tank";
const TANK_FIREBALL_PART = 380;
const TANK_FIREBALL_PART_DEPTH = 1;
const TANK_FIREBALL_ROTATE = 360;
const TANK_FIREBALL_SIZE_LOW = 40;
const TANK_FIREBALL_SIZE_SPREAD = 60;
const TANK_FIREBALL_X = 10;
const TANK_FIREBALL_RISE = 15;
const TANK_FIREBALL_RISE_LOW = 15;
// The spray of metal: a hit on a tank throws it from 30 above the blast, a tank going up from the blast itself and
// from 50 to 74 below it, up to 49 to the side (F6:4594, 4659-4660)
const HIT_FRAGMENT_RISE = 30;
const WRECK_FRAGMENT_SIDE = 50;
const WRECK_FRAGMENT_DROP = 50;
const WRECK_FRAGMENT_DROP_SPREAD = 25;

// bodyRagdoll (F6:4942-5045): a soldier thrown by a blast loses limbs, then flies and lands
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
// A shot or blast death shows blood on the torso and on the head 1 time in 10 each (F6:4452-4459, 4729-4737)
const BLOOD_ONE_IN = 10;
// The blood cloud of a blast death rises from the body up to 15 pixels (F6:4745)
const BLOOD_RISE = 15;

// updateExperience's float (F6:8818-8845): it rises over 4 seconds while it fades in over 1, holds 1 and fades out in 1
const XP_RISE_BY = 30;
const XP_RISE_SECONDS = 4;
const XP_FADE_SECONDS = 1;
const EASE = "easeOutSine";

// The floating RP (floatingRP, sprite 1769) beside the RP counter: attached to the hud at depth 16000 plus a counter
// that comes back round after 100, 59.3 across and 443 down, it rises to 423 over 4 seconds and fades out over the
// last of them (adjustRP F6:1352-1368, 1398-1412). Red for RP spent, green for RP gained
const RP_DEPTH = 16000;
const RP_NAMES = 100;
const RP_X = 59.3;
const RP_Y = 443;
const RP_RISE_TO = 423;
const RP_RISE_SECONDS = 4;
const RP_FADE_SECONDS = 1;
const RP_FADE_DELAY = 1;
const RP_SPENT = 10027008;
const RP_GAINED = 6723840;

// soldierDeath1 to 6 exist of the 10 the original picks from (F6:4493, 4741), so 4 in 10 deaths are silent
const DEATH_PICKS = 10;
const DEATH_SOUNDS = 6;

// playVoice (F6:8556-8638, the clip counts F6:11744-11752): a voice is called one time in `oneIn`, picks one of
// `count` files named `sound_voice_<side>_<stem><n>`, and plays after random(spread) + least milliseconds. A pick
// with no file stays silent: a side with fewer files than the count, and the two exports named ".wav"
// (`sound_voice_british_sniper2.wav`, `..._tank1.wav`)
const VOICES = {
  advance: { stem: "advance", oneIn: 5, count: 7, spread: 600, least: 100 },
  enemyDown: { stem: "enemyDown", oneIn: 20, count: 8, spread: 600, least: 100 },
  bazooka: { stem: "bazooka", oneIn: 6, count: 3, spread: 600, least: 100 },
  suppress: { stem: "suppressingFire", oneIn: 1, count: 4, spread: 600, least: 100 },
  flanked: { stem: "losingFlank", oneIn: 1, count: 2, spread: 600, least: 100 },
  grenade: { stem: "throwGrenade", oneIn: 3, count: 3, spread: 600, least: 100 },
  smoke: { stem: "throwSmoke", oneIn: 1, count: { british: 4, german: 1 }, spread: 600, least: 100 },
  attack: { stem: "attack", oneIn: 40, count: 2, spread: 600, least: 100 },
  sniper: { stem: "sniper", oneIn: 3, count: 3, spread: 600, least: 100 },
  incoming: { stem: "incoming", oneIn: 20, count: 4, spread: 600, least: 400 },
  machineGun: { stem: "machineGun", oneIn: 20, count: 3, spread: 10, least: 100 },
  tank: { stem: "tank", oneIn: 10, count: 2, spread: 900, least: 100 },
};
// The soldiers who shoot one shot at every chance (fireType none or unset, F6:10289-10700): the "else" of the burst
// rules, which calls "attack" before each shot (F6:2586-2589, 2975-2978)
const SINGLE_SHOT = {
  british: new Set(["sharpShooter", "mortarCarrier", "bazookaMan"]),
  german: new Set(["rifleman", "sharpShooter", "mortarCarrier", "bazookaMan"]),
};
// A blast reaches a squad whose leader is less than 80 pixels away in x and in y (F6:4551-4553). A squad in reach is
// hit unless random(9) is 0, random(3) when smoked (explosionSurvivalChanceBase F6:10926); armour is always hit
const BLAST_REACH = 80;
const SURVIVAL_ROLL = 9;
const SURVIVAL_ROLL_SMOKED = 3;
const SMOKED_FLAG = 4;
// A bullet kill of a soldier who wasn't the squad's first makes the shooter's squad call out by its kind: a
// machine gun team's, a sharpshooter's and a tank's (hitEnemy F6:4468-4489). Keyed by the squad's slot
const KILLER_VOICE = { 3: "machineGun", 4: "sniper", 8: "tank" };

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
    this.rpCount = 0;
    // Where the newest blast landed, for the hits on tanks that follow it in the same step
    this.lastBlast = { x: 0, y: 0 };
    // The soldier who fired the newest shot, whose bullet the next death comes from
    this.lastShooter = null;
    // The newest soldier killed, for the "enemy down" call when it was its squad's last
    this.lastKill = null;
    this.timers = new Set();
    field.onClear(() => this.reset());
    field.onEvent("shot", (event, quiet) => this.shot(event, quiet));
    field.onEvent("die", (event, quiet) => this.died(event, quiet));
    field.onEvent("gone", (event, quiet) => this.gone(event, quiet));
    field.onEvent("blast", (event, quiet) => this.blast(event, quiet));
    field.onEvent("tankhit", (event, quiet) => this.tankHit(quiet));
    field.onEvent("tankdie", (event, quiet) => this.tankDied(quiet));
    field.onEvent("xp", (event, quiet) => this.xp(event, quiet));
    field.onEvent("rp", (event, quiet) => this.rp(event, quiet));
    field.onEvent("flank", (event, quiet) => this.flanked(event, quiet));
    field.onEvent("grenade", (event, quiet) => this.thrown(event, quiet));
    field.units.onDeath((unit, how, exploded, quiet) => this.death(unit, how, exploded, quiet));
    field.units.onAdvance((unit) => this.voice("advance", unit.side));
    field.units.onSuppress((side) => this.isPlayer(side) && this.voice("suppress", side));
  }

  get lib() {
    return this.field.page.lib;
  }

  get units() {
    return this.field.units;
  }

  // The clips this module draws, loaded with the battlefield's
  static art() {
    const names = new Set(["xpIcon", "floatingRP", TANK_FIREBALL]);
    for (const rows of Object.values(EMITTERS)) {
      rows.forEach((row) => names.add(row[0]));
    }
    return [...names];
  }

  reset() {
    this.timers.forEach((timer) => clearTimeout(timer));
    this.timers.clear();
    this.lastShooter = null;
    this.lastKill = null;
  }

  // ---------- Particles ----------

  // One of the kinds above at a place on the field (the original's xxxExplosionParticle functions)
  emit(kind, x, y) {
    for (const row of EMITTERS[kind] ?? []) {
      this.emitRow(row, x, y);
    }
  }

  // particleEmitter (F6:4820-4862) for one row. The place is shifted once for the whole row
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
      const facing = FLIPPED_SHAFTS.has(look.clip) && random(2) > 0 ? -1 : 1;
      part.scale.set(size * facing, size);
    }
    part.alpha = motion.alpha / 100;
    part.position.set(at.x, at.y);
    this.count += 1;
    part.zIndex = this.count;
    layer.addChild(part);
    const originY = at.y;
    // moveParticle (F6:4863-4882)
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

  // The fireball a blast leaves above a tank (F6:4590-4593, 4655-4658), turned and sized by sprite 414's part
  tankFireball() {
    const layer = this.field.layer("particles");
    if (!layer) {
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
  }

  // A blast or shell that hits a tank leaves a fireball above it, a spray of metal and a clang (F6:4590-4595). The
  // bot says which tank; the blast that hit it came the step before, so its place is the fireball's
  tankHit(quiet) {
    if (quiet) {
      return;
    }
    this.tankFireball();
    this.emit("metalFragment", this.lastBlast.x, this.lastBlast.y - HIT_FRAGMENT_RISE);
    sound.play("sound_metalImpact");
  }

  // A tank or the bunker going up adds a second fireball, two sprays of metal and another clang (F6:4655-4662)
  tankDied(quiet) {
    if (quiet) {
      return;
    }
    const { x, y } = this.lastBlast;
    this.tankFireball();
    this.emit("metalFragment", x, y);
    this.emit("metalFragment", x + random(WRECK_FRAGMENT_SIDE), y + random(WRECK_FRAGMENT_DROP_SPREAD) + WRECK_FRAGMENT_DROP);
    sound.play("sound_metalImpact");
  }

  // ---------- Bodies ----------

  // A soldier dies (before its death animation starts). A thrown one loses limbs and flies; any other shot or blast
  // death may show blood, and a blast death rises as a cloud of it
  death(unit, how, exploded, quiet) {
    const clip = unit.clip;
    if (exploded) {
      this.ragdoll(clip);
    } else {
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

  // bodyRagdoll (F6:4942-5045): a limb or two come off, then the body flies on its own energy until it comes down on
  // the ground it first stood on, and lies there flat
  ragdoll(clip) {
    const unit = clip.unit;
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
  }

  // ---------- Experience and RP ----------

  // updateExperience's "+n" (F6:8818-8845): it starts clear, fades in over a second while it rises 30 pixels over 4,
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

  // adjustRP is told "player" only for the side the HUD shows, so only that side's RP floats (a watcher's HUD shows
  // the side it watches)
  rp(event, quiet) {
    const battle = this.field.battle;
    if (quiet || !battle) {
      return;
    }
    const [, , sideIndex, amount] = event;
    if (SIDES[sideIndex] === (battle.you ?? battle.map.side)) {
      this.rpFloat(SIDES[sideIndex], amount);
    }
  }

  // The floating RP (F6:1352-1368, 1398-1412): "-n" in red for RP spent, "+n" in green for RP gained
  rpFloat(side, amount) {
    const hud = this.field.page.root.children.find((node) => node.label === "hud");
    if (!hud) {
      return;
    }
    this.rpCount = (this.rpCount % RP_NAMES) + 1;
    const name = `rpText${this.rpCount}`;
    hud.children.find((node) => node.label === name)?.destroy({ children: true });
    const float = this.lib.makeExported("floatingRP");
    float.fresh = false;
    float.label = name;
    const box = float.child("glowBox")?.child("colourBox");
    if (box) {
      tweens.colorTo(box, amount < 0 ? RP_SPENT : RP_GAINED, 0);
    }
    const text = box?.child("textRP");
    if (text) {
      text.text = amount < 0 ? `-${-amount}` : `+${amount}`;
    }
    float.position.set(RP_X, RP_Y);
    float.zIndex = RP_DEPTH + this.rpCount;
    hud.addChild(float);
    tweens.ySlideTo(float, RP_RISE_TO, RP_RISE_SECONDS, EASE);
    tweens.alphaTo(float, 0, RP_FADE_SECONDS, "linear", RP_FADE_DELAY, () => float.destroy({ children: true }));
  }

  // ---------- Sounds and voices ----------

  // A shot: a soldier who shoots one shot at every chance calls out (F6:2586-2589, 2975-2978), and the shot is
  // remembered for the death it may cause
  shot(event, quiet) {
    const shooter = this.units.members.get(event[2]);
    this.lastShooter = shooter ?? null;
    if (quiet || !shooter || shooter.kind !== "soldier") {
      return;
    }
    if (SINGLE_SHOT[shooter.side].has(shooter.type)) {
      this.voice("attack", shooter.side);
    }
  }

  // A death: its sound, and the cry of a victim who wasn't the squad's first, shot by a sharpshooter, a machine gun
  // crew or a tank (F6:4468-4493, 4741)
  died(event, quiet) {
    const [, , id, how, killer] = event;
    const unit = this.units.members.get(id);
    this.lastKill = unit ? { squadId: unit.squadId, how, killer } : null;
    if (quiet || !unit) {
      return;
    }
    const pick = random(DEATH_PICKS) + 1;
    if (pick <= DEATH_SOUNDS) {
      sound.play(`sound_soldierDeath${pick}`);
    }
    const cry = how === HOW_BULLET ? KILLER_VOICE[this.lastShooter?.slot] : null;
    const squad = this.units.squads.get(unit.squadId);
    if (cry && squad?.order?.[0] !== id) {
      this.voice(cry, unit.side);
    }
  }

  // A squad shot down to its last soldier is gone: the shooters' side calls "enemy down" (F6:4537). A blast's kills
  // don't
  gone(event, quiet) {
    const kill = this.lastKill;
    this.lastKill = null;
    if (!quiet && kill && kill.squadId === event[2] && kill.how === HOW_BULLET && kill.killer >= 0) {
      this.voice("enemyDown", SIDES[kill.killer]);
    }
  }

  // A blast: where it landed, then each squad whose leader is in reach (F6:4551-4578). A bazooka rocket makes the
  // squad call "bazooka", and every soldier of a squad of the other side that the blast will hit calls "incoming"
  blast(event, quiet) {
    this.lastBlast = { x: event[3] / 10, y: event[4] / 10 };
    if (quiet) {
      return;
    }
    const owner = SIDES[event[5]];
    for (const [squadId, squad] of this.units.squads) {
      const order = squad.order ?? [];
      const leader = this.units.members.get(order[0]);
      if (!leader || leader.dead || !this.inReach(leader)) {
        continue;
      }
      if (event[2] === "bazooka") {
        this.voice("bazooka", leader.side);
      }
      if (leader.side !== owner && this.hit(leader, squadId)) {
        order.forEach(() => this.voice("incoming", leader.side));
      }
    }
  }

  inReach(leader) {
    return Math.abs(leader.x - this.lastBlast.x) < BLAST_REACH && Math.abs(leader.y - this.lastBlast.y) < BLAST_REACH;
  }

  // The survival roll: armour is always hit, a squad otherwise unless the roll comes up 0 (smoked: a shorter roll)
  hit(leader, squadId) {
    if (leader.kind === "tank") {
      return true;
    }
    const smoked = ((this.units.squadRow(squadId)?.[4] ?? 0) & SMOKED_FLAG) !== 0;
    return random(smoked ? SURVIVAL_ROLL_SMOKED : SURVIVAL_ROLL) !== 0;
  }

  // A squad left by the far edge flanks the other side, whose soldiers call "losing the flank" (F6:2129, 2161)
  flanked(event, quiet) {
    if (!quiet) {
      this.voice("flanked", SIDES[1 - event[2]]);
    }
  }

  // A thrown grenade of a side a person plays is that player's order, and the soldier calls it out: "grenade" for a
  // hand grenade, "smoke" for a smoke grenade (F6:6350, 6474). A CPU squad's grenades call nothing
  thrown(event, quiet) {
    const thrower = this.units.members.get(event[2]);
    if (!quiet && thrower && this.isPlayer(thrower.side)) {
      this.voice(event[6] === "smoke" ? "smoke" : "grenade", thrower.side);
    }
  }

  // Whether a person plays this side (the CPU's name is empty)
  isPlayer(side) {
    return Boolean(this.field.battle?.names?.[side]);
  }

  // playVoice (F6:8556-8638): one call of a kind of voice for a side
  voice(kind, side) {
    const voice = VOICES[kind];
    if (random(voice.oneIn) !== 0) {
      return;
    }
    const count = typeof voice.count === "number" ? voice.count : voice.count[side];
    const name = `sound_voice_${side}_${voice.stem}${random(count) + 1}`;
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
