// The dice and sums of a fight: whether an attack misses (checkMiss F4:2307), what a round does to the body part it
// lands on (applyDamageProjectiles F4:5566), what a swing or a shove does (applyDamageMelee F4:6280, meleeCollisions
// F4:6503), the stumble a hard hit knocks a target into (stumbleTarget F4:2263) and the stumble's slide, the damage
// numbers that float over whoever was hurt (showDamageText F4:18400, checkShowDamage F4:18449), and what a blast does
// to everyone near it (splashDamageCheck F4:6918, applyDamageSplash F4:6936).
//
// Every rule reads the attacker it is given, never the player, unless the original says the player: crits and the
// skill term belong to the player's own shots. A round carries the skill, ammo and weapon it left the gun with, so a
// swap while it flies changes nothing. A swing's "this swing hit" and "this swing missed" belong to the one swinging
// (hitThisSwing, missedThisSwing), so one person's miss never spoils another's swing.
//
// A stumbling zombie (state "stumble") slides here, in the zombies stage, as the original's zombie loop slid it; the
// zombie's own rules leave that state alone until the slide hands it back to its last state.
//
// What follows a hit or a death is other systems' work (alerts, bodies, drops, counters, the death screen): they hear
// of it with onCombat(event, fn). Events: "alert" (target, attacker, condition), "hit" (entry), "kill" (entry), "down"
// (entry: a companion's health ran out), "playerDead" (entry) and "shove" (entry: a shove touched someone). entry is
// { target, owner, zone, damage, crit, round, airborne }; airborne is true when the attacker was jumping or falling. A
// blast's entries have zone "blast", blast: true and dist, the blast's distance across the floor; a swing's or shove's
// have melee: true and shove (true for a shove).
import { boxOf, overlap, shown } from "./collide.js";
import { data } from "./data.js";
import { effects } from "./effects.js";
import { help } from "./help.js";
import { adjustedSkill, critChance, damagePlayer, killXP, player } from "./player.js";
import { gotoPlay, partAt } from "./rig.js";
import { rng } from "./rng.js";
import { camera, layers, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

// Used until the converted constants load (F4:26393-26408, 26616-26640, 26702)
const DEFAULTS = {
  missRange: 1000,
  missRangeMelee: 1000,
  missChance: 400,
  missChanceMelee: 25,
  zomMissChance: 100,
  companionWeaponSkill: 30,
  enemyWeaponSkill: 10,
  missRoundCrouchBonus: 0.5,
  hitHeadMod: 1.2,
  hitChestMod: 1,
  hitBellyMod: 0.8,
  hitLegsMod: 0.6,
  skillDamageMod: 0.05,
  criticalDamage: 3,
  criticalHitChance: 100,
  playerProjDamRed: 1,
  minStumbleDist: 30,
  critDamageTextScale: 120,
  zombieScale: 55,
  meleeCollCheckBuffer: 100,
  meleeSkillAdjust: 75,
  skillDamageModMelee: 0.1,
  shoveDamage: 0.5,
  struggleDamageMod: 0.5,
  knockbackChance: 100,
  stumbleSpeed: 2,
  moveEdgeBuffer: 50,
  screenShakeDelay: 50,
};
// The share of a hit's damage a body part takes (F4:26624-26627)
const ZONE_MODS = { Head: "hitHeadMod", Chest: "hitChestMod", Belly: "hitBellyMod", Legs: "hitLegsMod" };
// A hit loses up to a fifth of its damage at random (F4:5590)
const DAMAGE_SPREAD = 5;
// The player's skill term works from this skill (F4:5611)
const SKILL_CENTRE = 50;
// A blast's damage falls by one share for every 20 px across the floor from its middle (F4:6939)
const BLAST_STEP = 20;
// Zombie kinds that never stumble (F4:2266)
const NO_STUMBLE = new Set(["zombieCrawl", "zombieDog", "zombieRiotShield"]);
// A damage number: crits orange, misses grey (colorTo 16763904 and 9737364, F4:18419, 18437)
const CRIT_COLOUR = 0xffc800;
const MISS_COLOUR = 0x949494;
// It starts 10 px over the target's head, up to 15 px either side of its middle (F4:18413)
const TEXT_START = 10;
const TEXT_SPREAD = 30;
// A number too big to show (a hit worth Infinity) shows as 300 (F4:18426)
const TOO_BIG = 300;
const MOST_LOGGED = 200;

let page = null;
// fn lists by event name
const listeners = {};

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function emit(event, ...args) {
  for (const fn of listeners[event] ?? []) {
    try {
      fn(...args);
    } catch (e) {
      console.warn(`Union City: a ${event} listener failed`, e);
    }
  }
}

// Registers fn for a fight event: "alert", "hit", "kill", "down" or "playerDead"
export function onCombat(event, fn) {
  listeners[event] ??= [];
  listeners[event].push(fn);
}

function keep(entry) {
  combat.log.push({ ...entry, frame: world.frame });
  if (combat.log.length > MOST_LOGGED) {
    combat.log.shift();
  }
}

// ---------- Misses ----------

// A skill as the rules read it for anyone: the player's and anyone with their own skills adjusted by their attribute
function skillOf(actor, skill) {
  if (!actor?.skills || !actor.attributes || !skill) {
    return 0;
  }
  return adjustedSkill(actor, skill);
}

// A gun's miss, out of 1,000 (F4:2311-2339). The player misses by their own adjusted skill with the round's weapon,
// half again as steady crouched, and never with the chainsaw; a companion misses as skill 30, a friendly guard never,
// anyone else (enemy humans) as skill 10
function gunMiss(owner, roll, { skill, weaponType }) {
  const chance = constant("missChance");
  if (owner === player) {
    if (weaponType === "chainsaw") {
      return false;
    }
    let steady = skillOf(owner, skill);
    if (owner.crouched === true) {
      steady += steady * constant("missRoundCrouchBonus");
    }
    return roll < chance - Math.round(steady * 2);
  }
  if (owner.companion === true) {
    return roll < chance - Math.round(constant("companionWeaponSkill") * 2);
  }
  if (owner.friendly === true) {
    return false;
  }
  return roll < chance - Math.round(constant("enemyWeaponSkill") * 2);
}

// A zombie's swing misses by the player's Endurance and Luck, with a swish (F4:2340-2347)
function zombieMiss(roll) {
  const attributes = story.player?.attributes ?? {};
  const guard = Math.round(((attributes.endurance ?? 0) + (attributes.luck ?? 0)) / 3);
  const missed = roll < constant("zomMissChance") - guard;
  if (missed) {
    sound.play(`sound_wood_swing${rng.random(2) + 1}`);
  }
  return missed;
}

// A person's swing misses by the swinger's own skill with the weapon in hand (F4:2349-2362)
function meleeMiss(owner, { skill }) {
  const roll = rng.random(constant("missRangeMelee"));
  const chance = Math.max(0, constant("missChanceMelee") - Math.round(skillOf(owner, skill) * 2));
  return roll < chance;
}

// Whether an attack misses. kind is "gun" (a round; how: the skill and weapon type it was fired with), "zombie" (a
// zombie's swing), "melee" (a person's swing; how: the skill of the weapon swung) or "grenade" (never misses)
export function checkMiss(owner, target, kind, how = {}) {
  if (kind === "grenade" || !owner) {
    return false;
  }
  if (kind === "melee") {
    return meleeMiss(owner, how);
  }
  const roll = rng.random(constant("missRange"));
  return kind === "zombie" ? zombieMiss(roll) : gunMiss(owner, roll, how);
}

// ---------- Ranged damage ----------

// Whether the player's hit is critical: a fresh roll against the chance from their Luck and their skill with the
// round's weapon, worked out at the hit (F4:2236-2252). A round's own crit (true or false) stands when set
function rollCrit(round) {
  if (typeof round.crit === "boolean") {
    return round.crit;
  }
  if (round.owner !== player || !story.player) {
    return false;
  }
  return rng.random(constant("criticalHitChance")) < critChance(story.player, round.skill);
}

// The damage before Headshots Only, in the original's order (F4:5589-5623): the body part's share, up to a fifth off,
// armour unless the round pierces, then for the player's rounds the skill term and the crit. Never below 1 after all
// of that. Returns { damage, crit }
function rangedSum(target, round, zone) {
  let d = round.damage * constant(ZONE_MODS[zone] ?? "hitChestMod");
  d -= Math.round(rng.float() * (d / DAMAGE_SPREAD));
  const armour = target[`armor${zone}`];
  if (armour !== undefined && armour !== null && (round.piercing === undefined || round.piercing === null)) {
    d = Math.round(d * armour);
  }
  const crit = rollCrit(round);
  if (round.owner === player && story.player) {
    d += Math.round(constant("skillDamageMod") * (skillOf(story.player, round.skill) - SKILL_CENTRE));
    if (crit) {
      d *= constant("criticalDamage");
      stumble(target, d, { from: round.owner.x });
      sound.play("sound_criticalHit", { x: target.x });
    }
    if (round.knockback === true) {
      stumble(target, d, { from: round.owner.x });
    }
  }
  return { damage: Math.max(1, d), crit };
}

// Whether the attacker was off the ground (jumping or falling) when the hit landed (F4:5672, 6453)
function airborne(owner) {
  return owner?.jumping === true || owner?.falling === true;
}

function isZombie(target) {
  return target.side === "zombie";
}

// A round lands on a body part: the target is alerted, takes the damage, and dies, goes down or is killed as the
// original says (F4:5566-5856). Returns the entry the events carry
export function damageRanged(target, round, zone) {
  emit("alert", target, round.owner, "gunshotHit");
  const sum = rangedSum(target, round, zone);
  let d = sum.damage;
  if (story.headshots === true && zone !== "Head" && isZombie(target)) {
    d = 1;
  }
  sound.play(`sound_bodyHit${rng.random(4) + 1}`, { x: target.x });
  if (round.weaponRef === "chainsaw") {
    sound.play("sound_chainsawHit", { x: target.x });
  }
  const entry = { target, owner: round.owner, zone, damage: d, crit: sum.crit, round, airborne: airborne(round.owner) };
  takeDamage(target, d * (target === player ? constant("playerProjDamRed") : 1), sum.crit);
  const names = { target: target.name ?? target.kind, owner: round.owner?.name ?? round.owner?.kind };
  keep({ ...names, zone, damage: d, crit: sum.crit });
  emit("hit", entry);
  afterHit(entry);
  return entry;
}

// Health comes off. The player's comes off through their vitals, which take the share from permanent health too
function takeDamage(target, d, crit) {
  if (target === player) {
    damagePlayer(d);
    return;
  }
  target.lastHealth ??= target.health;
  target.windowCrit ||= crit;
  target.health -= d;
}

// The player earns XP for zombies they kill, and for enemy people they or a companion kill (F4:5664-5666, 5767)
function scoresXP(target, owner) {
  if (isZombie(target)) {
    return owner === player;
  }
  return target.side === "enemy" && (owner === player || owner?.companion === true);
}

// What follows a hit whose damage emptied the target's health (F4:5657-5855)
function afterHit(entry) {
  const { target, owner } = entry;
  if (target.alive !== true || target.health > 0) {
    return;
  }
  if (target === player) {
    target.alive = false;
    target.controlsLocked = true;
    emit("playerDead", entry);
    return;
  }
  if (target.companion === true) {
    emit("down", entry);
    return;
  }
  target.alive = false;
  if (scoresXP(target, owner) && story.player) {
    killXP(target);
  }
  if (isZombie(target)) {
    showDamage();
  }
  emit("kill", entry);
}

// ---------- Blasts ----------

// Whom a blast can reach (F4:6920-6933): the player's own blast hurts everyone but their friends, the player included;
// anyone else's spares the player and the one who set it off. Each target is reached once
function blastTargets(owner) {
  const all = [...world.companions, ...world.humans, ...world.zombies];
  if (world.player === player) {
    all.unshift(player);
  }
  return all.filter((target) => {
    if (target.alive !== true || !target.clip || target.clip.destroyed) {
      return false;
    }
    if (owner === player) {
      return target.friendly !== true && target.side !== "friend";
    }
    return target !== player && target !== owner;
  });
}

// What a blast does to one target dist px from it across the floor (applyDamageSplash F4:6936): splashDamage shared by
// round(dist / 20), at least one share. The player's blasts add the skill term of direct hits and can crit; a crit and
// a knockback both stumble the target by the blast's damage. No armour and no Headshots Only
function blastDamage(target, owner, source, dist) {
  emit("alert", target, owner, "gunshotHit");
  let d = source.splashDamage / Math.max(1, Math.round(dist / BLAST_STEP));
  const crit = rollCrit({ ...source, owner });
  if (owner === player && story.player) {
    d += Math.round(constant("skillDamageMod") * (skillOf(story.player, source.skill) - SKILL_CENTRE));
    if (crit) {
      d *= constant("criticalDamage");
      stumble(target, d, { from: owner.x });
      sound.play("sound_criticalHit", { x: target.x });
    }
    if (source.knockback === true) {
      stumble(target, d, { from: owner.x });
    }
  }
  sound.play(`sound_bodyHit${rng.random(4) + 1}`, { x: target.x });
  takeDamage(target, d, crit);
  const entry = { target, owner, zone: "blast", damage: d, crit, round: source, blast: true, dist };
  entry.airborne = airborne(owner);
  const names = { target: target.name ?? target.kind, owner: owner?.name ?? owner?.kind };
  keep({ ...names, zone: "blast", damage: d, crit, dist });
  emit("hit", entry);
  afterHit(entry);
  return entry;
}

// A blast at room point x (only its distance across the floor counts) set off by owner. source is the round or weapon
// it came from: { splashDamage, splashSize, skill, knockback (true when this shot knocks back), crit }. Everyone within
// splashSize px takes it once. Returns the entries, one per target reached
export function splash(x, y, owner, source) {
  const entries = [];
  for (const target of blastTargets(owner)) {
    const dist = Math.abs(target.x - x);
    if (dist < (source.splashSize ?? 0)) {
      entries.push(blastDamage(target, owner, source, dist));
    }
  }
  return entries;
}

// Tells the systems that care that a target was struck by something that does no damage of its own, as a thrown
// grenade bouncing off a body does (applyDamageProjectiles F4:5568)
export function alertHit(target, owner) {
  emit("alert", target, owner, "gunshotHit");
}

// ---------- Melee ----------

// The player and their friends are one side, zombies another, enemy people a third
function sideOf(actor) {
  return actor.side === "player" || actor.side === "friend" ? "us" : actor.side;
}

// Whom a person (the player, a companion or another human) can swing at or shove: the living, not on the attacker's
// side, within 100 px across the floor (F4:6516, 6644). The player comes first, as in the original's list
function meleeReach(attacker) {
  const all = [...world.companions, ...world.humans, ...world.zombies];
  if (world.player === player) {
    all.unshift(player);
  }
  const reach = constant("meleeCollCheckBuffer");
  return all.filter((target) => {
    if (target === attacker || target.alive !== true || !target.clip || target.clip.destroyed) {
      return false;
    }
    const dx = target.x - attacker.x;
    return dx > -reach && dx <= reach && sideOf(target) !== sideOf(attacker);
  });
}

// The weapon in a person's hands; a zombie has none
function weaponIn(actor) {
  const weapons = data.items?.weapons ?? {};
  return weapons[actor.weapon ?? actor.rig?.weapon ?? "hands"] ?? weapons.hands ?? {};
}

function isPerson(actor) {
  return actor.side !== "zombie";
}

// A hit's damage before its random cut (F4:6293-6316): a zombie's own damage; a person's bare hands by their own
// Strength; a person's weapon by its damage, a third of their own Strength and their own skill term
function meleeBase(attacker, weapon) {
  if (!isPerson(attacker)) {
    return attacker.damage ?? 0;
  }
  const strength = attacker.attributes?.strength ?? 0;
  if (weapon.ref === "hands") {
    return Math.round(1 + strength / 5);
  }
  const skillTerm = constant("skillDamageModMelee") * (skillOf(attacker, weapon.skill) - constant("meleeSkillAdjust"));
  return Math.round((weapon.damage ?? 0) + strength / 3) + Math.round(skillTerm);
}

// A person's hit rolls the weapon's knockback, which stumbles the target by the damage so far, and the player's own hit
// rolls a crit, three times the damage (F4:6323-6342). Zombies do neither. Returns { damage, crit }
function meleeKnocks(attacker, target, weapon, damage) {
  if (!isPerson(attacker)) {
    return { damage, crit: false };
  }
  if (rng.random(constant("knockbackChance")) < (weapon.knockback ?? 0)) {
    stumble(target, damage, { from: attacker.x, attacker });
  }
  if (attacker !== player || !story.player) {
    return { damage, crit: false };
  }
  const crit = rng.random(constant("criticalHitChance")) < critChance(story.player, weapon.skill);
  if (crit) {
    sound.play("sound_criticalHit");
  }
  return { damage: crit ? damage * constant("criticalDamage") : damage, crit };
}

// The sum of a swing or a shove on a body part, in the original's order (F4:6316-6375): up to a tenth off, the screen
// shakes when the player is the one hit, knockback and crit, a shove's own small damage in place of all that, armour,
// Headshots Only, half while the player struggles, and never below 1. No body part share in melee. Returns
// { damage, crit }
function meleeSum(attacker, target, kind, zone) {
  const weapon = weaponIn(attacker);
  let d = meleeBase(attacker, weapon);
  d -= Math.round(rng.float() * (d / 10));
  if (target === player) {
    camera.shake(Math.round(d / 5), 2 * constant("screenShakeDelay"));
  }
  const knocked = meleeKnocks(attacker, target, weapon, d);
  d = knocked.damage;
  if (kind === "shove") {
    d = constant("shoveDamage") + (attacker.attributes?.strength ?? 0) / 3 / 4;
  }
  const armour = target[`armor${zone}`];
  if (armour !== undefined && armour !== null) {
    d = Math.round(d * armour);
  }
  if (story.headshots === true && zone !== "Head" && isZombie(target)) {
    d = 1;
  }
  if (target === player && player.struggling === true) {
    d *= constant("struggleDamageMod");
  }
  return { damage: Math.max(1, d), crit: knocked.crit && kind !== "shove" };
}

// A swing or a shove lands on a body part (applyDamageMelee F4:6280): the weapon's hit sound, the body's thud, the
// target alerted, the damage taken, and death, going down or a kill as the original says. kind is "swing" or "shove";
// a zombie's blow is a "swing" on the chest. Returns the entry the events carry
export function damageMelee(attacker, target, kind = "swing", zone = "Chest") {
  // A gun has no hit material (the original asks for "sound_undefined_hit" and hears nothing)
  const material = weaponIn(attacker).material;
  if (isPerson(attacker) && target.down !== true && material) {
    sound.play(`sound_${material}_hit${rng.random(2) + 1}`);
  }
  sound.play(`sound_bodyHit${rng.random(4) + 1}`, { x: target.x });
  emit("alert", target, attacker, "meleeHit");
  const { damage, crit } = meleeSum(attacker, target, kind, zone);
  if (target === player && kind === "swing" && attacker !== player && !help.has("shove")) {
    help.show("shove");
  }
  takeDamage(target, damage, crit);
  const entry = { target, owner: attacker, zone, damage, crit, melee: true, shove: kind === "shove" };
  entry.airborne = airborne(attacker);
  const names = { target: target.name ?? target.kind, owner: attacker.name ?? attacker.kind };
  keep({ ...names, zone, damage, crit, kind });
  emit("hit", entry);
  afterHit(entry);
  return entry;
}

// A swing's live box on the weapon in the arms, and the box a shove pushes with on the arms (F4:6516, 6607)
const SWING_BOX = "arms.weapon.collision";
const SHOVE_BOX = "arms.collision";
// A swing tests body parts in this order (F4:6646-6731); a shove touches the head, chest or belly and counts as the
// head
const SWING_ZONES = ["Head", "Legs", "Chest", "Belly"];
const SHOVE_ZONES = ["Head", "Chest", "Belly"];
// Riot gear turns a swing on these parts into a puff of dust and no blood (F4:6652, 6697)
const RIOT_PARTS = { Head: new Set(["zombieRiot"]), Chest: new Set(["zombieRiot", "zombieRiotNoHelmet"]) };
// The dust puffs up to 10 px across and 20 px up or down from the chest's middle (F4:6654)
const DUST_ACROSS = 10;
const DUST_UPDOWN = 20;
// Blood thrown from a swing's hit: two drops from the head, one from anywhere else (F4:6662-6663)
const SWING_BLOOD = { Head: 2, Chest: 1, Belly: 1, Legs: 1 };
// A shove knocks back by this before the shover's own bonus (F4:6524)
const SHOVE_STUMBLE = 2;

function middleOf(box) {
  return { x: box.x + box.w / 2, y: box.y + box.h / 2 };
}

// The first of a target's body parts a box overlaps, of those listed
function partHit(target, box, zones) {
  return zones.find((zone) => overlap(boxOf(target.clip, `collision${zone}`), box)) ?? null;
}

// Riot gear: a puff of dust near the chest's middle (bulletDustParticle, F4:6654)
function riotDust(target) {
  const chest = middleOf(boxOf(target.clip, "collisionChest") ?? { x: target.x, y: target.y, w: 0, h: 0 });
  const x = chest.x + Math.floor(Math.random() * DUST_ACROSS * 2) - DUST_ACROSS;
  effects.particle("dust", x, chest.y + Math.floor(Math.random() * DUST_UPDOWN * 2) - DUST_UPDOWN);
}

// A swing's box has met a body part: the swinger's miss roll, then the hit, which switches the box off for the rest of
// the swing. Riot gear puffs dust; anything else bleeds (F4:6646-6731)
function landSwing(attacker, target, zone) {
  if (checkMiss(attacker, target, "melee", { skill: weaponIn(attacker).skill })) {
    missText(target);
    attacker.missedThisSwing = true;
    return;
  }
  attacker.hitThisSwing = true;
  const live = partAt(attacker.clip, SWING_BOX);
  if (live) {
    live.visible = false;
  }
  if (RIOT_PARTS[zone]?.has(target.type)) {
    riotDust(target);
    damageMelee(attacker, target, "swing", zone);
    return;
  }
  const part = middleOf(boxOf(target.clip, `collision${zone}`));
  damageMelee(attacker, target, "swing", zone);
  effects.bloodPack(target, zone, attacker);
  effects.blood(part.x, part.y, target.x >= attacker.x ? 1 : -1, SWING_BLOOD[zone]);
}

// A person holding a melee weapon whose swing box is live this step hits the first target in reach it overlaps, once a
// swing. A hit or a miss ends the swing's chances
function swingHits(attacker) {
  if (attacker.hitThisSwing === true || attacker.missedThisSwing === true) {
    return;
  }
  if (weaponIn(attacker).weaponClass !== "melee" || !shown(attacker.clip, SWING_BOX)) {
    return;
  }
  const box = boxOf(attacker.clip, SWING_BOX);
  for (const target of meleeReach(attacker)) {
    const zone = partHit(target, box, SWING_ZONES);
    if (zone) {
      landSwing(attacker, target, zone);
      return;
    }
  }
}

// While a person shoves, everyone in reach their arms touch takes the shove's damage and stumbles back, each once a
// shove (F4:6509-6531). shoveHits is emptied when a shove starts
function shoveHits(shover) {
  if (shover.shoving !== true) {
    return;
  }
  const box = boxOf(shover.clip, SHOVE_BOX);
  if (!box) {
    return;
  }
  shover.shoveHits ??= new Set();
  for (const target of meleeReach(shover)) {
    if (shover.shoveHits.has(target) || !partHit(target, box, SHOVE_ZONES)) {
      continue;
    }
    shover.shoveHits.add(target);
    const entry = damageMelee(shover, target, "shove", "Head");
    if (target.alive === true) {
      stumble(target, SHOVE_STUMBLE, { from: shover.x, attacker: shover });
    }
    emit("shove", entry);
  }
}

// The people who can swing or shove: the player, companions and the other humans, the living only
function fighters() {
  const all = [...world.companions, ...world.humans];
  if (world.player === player) {
    all.unshift(player);
  }
  return all.filter((each) => each.alive === true && each.clip && !each.clip.destroyed);
}

// The melee stage (meleeCollisions F4:6503): shoves first, then swings. Zombies' blows are the zombies' own to land
function meleeCollisions() {
  for (const each of fighters()) {
    shoveHits(each);
  }
  for (const each of fighters()) {
    swingHits(each);
  }
}

// ---------- Stumbles ----------

function canStumble(target) {
  if (target.state === "stumble" || target.stumbling === true || target.laying === true || target.rising === true) {
    return false;
  }
  return !NO_STUMBLE.has(target.type);
}

// The one whose Strength and Fitness push a stumble further: a person who swung or shoved, with their own stats
function pusherOf(attacker) {
  if (attacker === player) {
    return story.player ?? null;
  }
  return attacker?.attributes && attacker.skills && isPerson(attacker) ? attacker : null;
}

// A shove's thud: the gun's butt, or the melee weapon's own hit sound (playShoveHitSound F4:5402)
function shoveSound(shover) {
  const weapon = weaponIn(shover);
  if (weapon.weaponClass === "firearm") {
    sound.play(`sound_shove_firearm${rng.random(2) + 1}`);
  } else if (weapon.weaponClass === "melee") {
    sound.play(`sound_${weapon.material}_hit${rng.random(2) + 1}`);
  }
}

// A hard hit knocks the target back, away from the attacker (stumbleTarget F4:2263): 30 px plus the damage, plus the
// swinger's or shover's own Strength and a fifth of their adjusted Fitness when a person's swing or shove did it
// (attacker). Nothing happens to a target already stumbling, lying, rising, or of a kind that never stumbles. The
// slide moves it at 2 px a step until it has gone the distance. from is the attacker's x
export function stumble(target, damage, { from, attacker = null } = {}) {
  if (!canStumble(target)) {
    return false;
  }
  if (attacker?.shoving === true) {
    shoveSound(attacker);
  }
  Object.assign(target, { stumbling: true, stumbleMoving: true, attacking: false, grabbing: false, animWalk: false });
  if (target.target) {
    target.target.grabbed = false;
  }
  target.lastState = target.state === "attack" ? "chase" : target.state;
  target.state = "stumble";
  target.stumbleDir = from > target.x ? "left" : "right";
  const pusher = pusherOf(attacker);
  const bonus = pusher ? pusher.attributes.strength + Math.round(adjustedSkill(pusher, "fitness") / 5) : 0;
  const distance = Math.round(constant("minStumbleDist") + damage + bonus);
  target.stumbleDistance = target.x + (target.stumbleDir === "left" ? -distance : distance);
  return true;
}

// The stumble starts its art: staggering back when pushed the way it faces away from, forward otherwise, one of two
// takes (F4:9205-9224)
function stumbleArt(zombie) {
  zombie.animWalk = true;
  const take = rng.random(2) + 1;
  const facesRight = (zombie.clip?.scale.x ?? 1) > 0;
  const back = facesRight === (zombie.stumbleDir === "left");
  if (zombie.clip && !zombie.clip.destroyed) {
    gotoPlay(zombie.clip, `stumble_${back ? "back" : "forward"}${take}`);
  }
}

// One step of a zombie's stumble (F4:9204-9259): it slides 2 px a step until it has gone the distance or meets the
// room's edge or something it collides with, and once its art says the stumble is over it goes back to what it was
// doing
function slideStumble(zombie) {
  if (zombie.animWalk === false) {
    stumbleArt(zombie);
  }
  const left = zombie.stumbleDir === "left";
  const inRoom = left ? zombie.x > room.edges.left : zombie.x < room.edges.right;
  const short = left ? zombie.x > zombie.stumbleDistance : zombie.x < zombie.stumbleDistance;
  const blocked = left ? zombie.collideLeft === true : zombie.collideRight === true;
  if (short && inRoom && zombie.stumbleMoving === true && !blocked) {
    zombie.x += left ? -constant("stumbleSpeed") : constant("stumbleSpeed");
  } else {
    zombie.stumbleMoving = false;
  }
  if (zombie.stumbling === false) {
    zombie.stumbleDistance = 0;
    zombie.state = zombie.lastState;
    zombie.animWalk = false;
  }
  if (zombie.clip && !zombie.clip.destroyed) {
    zombie.clip.x = zombie.x;
  }
}

function slideStumbles() {
  for (const zombie of world.zombies) {
    if (zombie.state === "stumble" && zombie.alive === true) {
      slideStumble(zombie);
    }
  }
}

// ---------- Damage numbers ----------

function textHeight(target) {
  return target.charHeight ?? target.clip?.height ?? 0;
}

// A number or MISS! floats up from over a target's head, if the player has damage numbers on
function floatText(target, text, style) {
  if (!story.settings?.showDamageText) {
    return null;
  }
  const x = target.x + Math.floor(Math.random() * TEXT_SPREAD) - TEXT_SPREAD / 2;
  return effects.float(text, x, target.y - (textHeight(target) + TEXT_START), style);
}

// "-n" over a target for the health it lost; crits bigger and orange
export function damageText(target, n, crit = false) {
  let shown = Math.round(n);
  if (shown === Infinity) {
    shown = TOO_BIG;
  }
  return floatText(target, shown > 0 ? `-${shown}` : "", { colour: crit ? CRIT_COLOUR : null, crit });
}

// "MISS!" in grey over a target (showMiss F4:2364)
export function missText(target) {
  return floatText(target, "MISS!", { colour: MISS_COLOUR });
}

// Everyone not friendly who lost health since the last look shows the total as one number (checkShowDamage F4:18449,
// run every 5 steps and at a zombie's death)
export function showDamage() {
  for (const target of [...world.zombies, ...world.humans, ...world.companions]) {
    if (target.lastHealth === undefined || target.friendly === true || !(target.health < target.lastHealth)) {
      continue;
    }
    damageText(target, Math.abs(target.health - target.lastHealth), target.windowCrit === true);
    target.lastHealth = target.health;
    target.windowCrit = false;
  }
}

// ---------- Setup ----------

export function initCombat(owner) {
  page = owner;
  page.lib.need([page.lib.exported("damageText")]).catch((e) => {
    console.warn("Union City: the damage numbers' art didn't load", e);
  });
  world.stage("melee", meleeCollisions);
  world.stage("zombies", slideStumbles);
  world.stage("quick", showDamage);
}

// Helpers for page.py checks
export const combatDebug = {
  // Stands a plain zombie of a type in the room at x, facing 1 (right) or -1 (left), with the health given and its
  // type's armour, as a target for rounds. Resolves to the actor once its art is in
  async zombie(type = "zombieSlow", x = 0, { facing = -1, health = 1000, label = "idle" } = {}) {
    await page.lib.need([page.lib.exported("zombie")]);
    const def = data.actors.zombies[type] ?? {};
    const clip = page.lib.makeExported("zombie");
    clip.gotoAndStop(label);
    const size = constant("zombieScale") / 100;
    clip.scale.set(size * facing, size);
    clip.x = x;
    clip.y = world.room?.floorY ?? 0;
    layers.actors.addChild(clip);
    const actor = { kind: "zombie", name: `zombie${world.zombies.length + 1}`, type, side: "zombie", clip, x, facing };
    Object.assign(actor, { y: clip.y, health, healthMax: health, alive: true, state: "idle", alerted: false });
    Object.assign(actor, { armorHead: def.armorHead, armorChest: def.armorChest, xpBonus: def.xpBonus ?? 1 });
    actor.charHeight = clip.height;
    // The art's frame scripts set their flags (stumbling, animating) on the actor
    clip.owner = actor;
    world.zombies.push(actor);
    return actor;
  },

  // Takes every zombie out of the room
  clearZombies() {
    for (const each of world.zombies) {
      each.clip?.destroy({ children: true });
    }
    world.zombies.length = 0;
  },
};

export const combat = {
  // { target, owner, zone, damage, crit, kind, frame } for the latest hits, oldest first (kind for swings and shoves)
  log: [],
  checkMiss,
  damageRanged,
  damageMelee,
  splash,
  alertHit,
  stumble,
  damageText,
  missText,
  showDamage,
  onCombat,
  get floats() {
    return effects.counts.floats;
  },
};
