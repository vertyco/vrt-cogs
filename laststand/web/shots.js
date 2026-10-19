// Rounds in flight: bullets, arrows, hand grenades, M79 shells and rockets (projectileCollisions F4:5857, the rounds'
// onEnterFrame F4:21523-21616). A round moves, tests the bodies near it once a step, then the room's blocks, then the
// room's walls and floor, and its life runs out. Each round carries every value it needs from the gun that fired it:
// { owner, kind, x, y, angle, speed, life, weaponRef, projectile, decal, damage, piercing, skill, ammo, shell,
// weaponClass, crit, knockback, splashDamage, splashSize, gravity }. kind is "bullet", "arrow", "grenade", "m79" or
// "rocket"; other kinds register their own flight and hits with onKind, and a round of a kind nobody registered is
// only recorded.
//
// A hand grenade bounces off everything and blows up when its fuse (its life) runs out. An M79 shell drops faster and
// faster and blows up on whatever it hits once it has flown a few steps; before that it falls away as a dud. A rocket
// trails smoke and blows up on the first thing it hits. A blast (splash in combat.js) hurts everyone near it.
//
// A body's hit boxes are tested Shield, Head, Legs, Chest, Belly (F4:5926-6167). A miss shows "MISS!" once and the
// round flies on past that target; a hit stops the round's tests for this step. A piercing round goes on through,
// hitting each target once, until it has hit as many as its piercing; armoured zombies stop it whatever it pierces.
import { boxOf, overlap } from "./collide.js";
import { alertHit, checkMiss, damageRanged, missText, splash } from "./combat.js";
import { data } from "./data.js";
import { effects } from "./effects.js";
import { light } from "./light.js";
import { player } from "./player.js";
import { rng } from "./rng.js";
import { camera, layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";

// The most rounds kept for a check to read
const MOST_RECORDED = 500;
// Used until the converted constants load (F4:26616-26623)
const DEFAULTS = {
  rangeCheck: 160,
  collCheckBuffer: 80,
  wallCollX: 50,
  wallCollY: 50,
  armDistance40mm: 5,
  screenShakeDelay: 50,
};
const ZONES = ["Shield", "Head", "Legs", "Chest", "Belly"];
// Zombies whose armour stops a round on that body part, as each zone's test lists them (F4:5988, 6086, 6138)
const ARMOURED = {
  Head: new Set(["zombieArmy", "zombieRiot", "zombieArmySprint"]),
  Chest: new Set(["zombieRiot", "zombieRiotNoHelmet", "zombieArmyNoHelmet", "zombieArmy", "zombieArmySprint"]),
  Belly: new Set(["zombieRiot", "zombieRiotNoHelmet", "zombieArmyNoHelmet", "zombieArmy"]),
};
const SHIELD_ZOMBIE = "zombieRiotShield";
const ARMOUR_DUST = 20;
// Blood thrown from a hit: two drops from the head and body, one from the legs (F4:6004, 6048, 6102, 6154)
const BLOOD_DROPS = { Head: 2, Chest: 2, Belly: 2, Legs: 1 };
// The part a stuck arrow hangs in, by body part; legs pick the front or back leg (showArrowHit F4:10740-10760)
const ARROW_PARTS = { Head: ["head"], Chest: ["torso"], Belly: ["torso"], Legs: ["upperLeg_front", "upperLeg_back"] };
// Arrows cycle through six names, so a seventh replaces the first (F4:10735)
const STUCK_ARROWS = 6;
const STUCK_ARROW_SPRITE = 5312;
// Wall decals sit 5 to 14 px inside the room's edge, block decals 10 to 24 px into the block (attachDecal F4:10629)
const EDGE_INSET = 10;
const EDGE_INSET_MIN = 5;
const BLOCK_INSET = 15;
const BLOCK_INSET_MIN = 10;
// The art each projectile draws with, made once it has loaded
const PROJECTILES = ["tracer", "arrow", "none", "noneSlow", "grenade", "40mmGrenade", "RPG"];
// A thrown grenade starts 25 px a step along the aim and 15 px a step up, loses 2% of its speed across the floor every
// step, and spins twice its speed in degrees (F4:21503-21507, 21599-21608)
const GRENADE_THROW = 25;
const GRENADE_UP = -15;
const GRENADE_FRICTION = 0.98;
const GRENADE_SPIN = 2;
// On the floor it stops falling once it bounces slower than 3 px a step, and rests once it rolls slower than 1
// (F4:21585-21595)
const GRENADE_SETTLE_UP = 3;
const GRENADE_SETTLE_ACROSS = 1;
// A floor bounce keeps 1 / 1.95 of its fall, upward, and divides its roll by 1 to 3.9 (bounceGrenade F4:21625)
const BOUNCE_KEEP = 1.95;
const BOUNCE_SLOW = 30;
// An M79 shell loses 2% of its speed and drops 5% faster every step (F4:21569-21575)
const SHELL_SLOW = 0.98;
const SHELL_DROP = 1.05;
// A blast shakes the view 5 px for five shake pulses (screenShake(5, 5) F4:10833)
const BLAST_SHAKE = 5;
const BLAST_SHAKE_PULSES = 5;
// A blast on a body shows within 10 px across and 20 px up or down of the body part's middle, 60% to 119% of its size,
// mirrored one time in two (F4:10839-10856)
const BLAST_SPREAD_X = 20;
const BLAST_SPREAD_Y = 40;
const BLAST_SIZE_MIN = 60;
const BLAST_SIZE_RANGE = 60;
const BLAST_SOUNDS = 2;
// A rocket's smoke puff stays where it was left, 50% to 99% of its size and 70% to 99% seen, fading 3% a step until
// it is under 15% (smokeParticle F4:10912, particleEmitter, moveParticle)
const SMOKE_SIZE_MIN = 50;
const SMOKE_SIZE_RANGE = 50;
const SMOKE_ALPHA_MIN = 70;
const SMOKE_ALPHA_RANGE = 30;
const SMOKE_FADE = 3;
const SMOKE_GONE = 15;
// Art the rounds use besides their projectiles
const EXTRA_ART = ["stuckArrow", "effect_explosion", "smoke_RPGtrail"];
// The most blasts kept for a check to read
const MOST_BLASTS = 100;

let page = null;
let artReady = false;
let stuckArrows = 0;
// The room's blocks with their collision boxes, worked out once a room stands
let blocks = [];
// A rocket's smoke puffs still fading: { clip, alpha } (alpha in percent)
let smoke = [];
// kind name -> { move(round), hit(round, target, zone, box) -> "stop" | null, block(round, block), wall(round),
// expire(round) }
const kinds = new Map();

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function radians(value) {
  return (value * Math.PI) / 180;
}

// ---------- Flying ----------

// Takes a round out of the world
function remove(round) {
  round.gone = true;
  if (round.clip && !round.clip.destroyed) {
    round.clip.destroy({ children: true });
  }
  const at = world.shots.indexOf(round);
  if (at >= 0) {
    world.shots.splice(at, 1);
  }
}

function placeClip(round) {
  if (round.clip && !round.clip.destroyed) {
    round.clip.x = round.x;
    round.clip.y = round.y;
    round.clip.rotation = radians(round.spin ?? round.angle);
  }
}

// A bullet or arrow flies straight on (F4:21562-21565)
function flyStraight(round) {
  round.x += Math.cos(radians(round.angle)) * round.speed;
  round.y += Math.sin(radians(round.angle)) * round.speed;
  placeClip(round);
}

// The round's art, lit by the room unless it is a tracer (lightObject F4:21421)
function makeClip(round) {
  const name = `projectile_${round.projectile}`;
  if (!artReady || !layers.shots || !page.lib.exported(name)) {
    return null;
  }
  const clip = page.lib.makeExported(name);
  clip.label = "round";
  clip.eventMode = "none";
  layers.shots.addChild(clip);
  if (round.projectile !== "tracer") {
    light.apply(clip);
  }
  return clip;
}

// What the round covers this step: its art's box, as Flash's hitTest between two clips measures it. A round with no art
// is a point
function roundBox(round) {
  if (round.clip && !round.clip.destroyed) {
    return boxOf(round.clip);
  }
  return { x: round.x, y: round.y, w: 0, h: 0 };
}

// ---------- Hitting bodies ----------

// Everyone a round could hit: the player, companions, people and zombies, the living only
function bodies() {
  const all = [...world.companions, ...world.humans, ...world.zombies];
  if (world.player === player) {
    all.unshift(player);
  }
  return all.filter((each) => each.alive === true && each.clip && !each.clip.destroyed);
}

// The player and their friends are one side (F4:5880-5917): no round hurts its own side, and no one hits themselves
function sideOf(actor) {
  return actor.side === "player" || actor.side === "friend" ? "us" : actor.side;
}

function sameSide(owner, target) {
  return target === owner || sideOf(owner) === sideOf(target);
}

// Only bodies on the side the shooter faces count, and only within 80 px of the round across the floor (F4:5874-5920)
function inReach(round, target) {
  const owner = round.owner;
  const across = Math.abs(target.x - round.x);
  if (across >= constant("rangeCheck") || sameSide(owner, target) || round.hits.has(target)) {
    return false;
  }
  const ahead = (owner.x > target.x && owner.facing < 0) || (owner.x < target.x && owner.facing > 0);
  return ahead && across < constant("collCheckBuffer");
}

// Blood from the hit body part, thrown away from the shooter (showBloodHit F4:10698, the blood bounces)
function bleed(round, target, zone, box) {
  const dir = target.x >= round.owner.x ? 1 : -1;
  effects.bloodPack(target, zone, round.owner);
  effects.blood(box.x + box.w / 2, box.y + box.h / 2, dir, BLOOD_DROPS[zone]);
}

// An arrow stays in the body part it hit, turned the way it flew unless the target faces the shooter
// (showArrowHit F4:10732)
function stickArrow(round, target, zone, box) {
  const names = ARROW_PARTS[zone];
  const part = target.clip.child(names[Math.floor(Math.random() * names.length)]);
  if (!part?.attach || !artReady) {
    return;
  }
  stuckArrows = (stuckArrows + 1) % STUCK_ARROWS;
  const name = `arrow${stuckArrows}`;
  part.child(name)?.removeMovieClip();
  const arrow = page.lib.makeExported("stuckArrow");
  const scale = Math.abs(target.clip.scale.x) || 1;
  arrow.x += Math.floor(Math.random() * (box.w / scale / 2));
  arrow.y += Math.floor(Math.random() * (box.h / scale / 2));
  const facing = target.clip.scale.x < 0 ? -1 : 1;
  const facesShooter = (round.owner.x > target.x && facing > 0) || (round.owner.x < target.x && facing < 0);
  arrow.rotation = facesShooter ? 0 : radians(round.angle) + arrow.rotation;
  part.attach(arrow, name);
}

// Armour's dust puffs 20 px in front of the target on the round's side, or at the round (showHitEffect F4:10782)
function dustX(round, target) {
  if (round.x <= target.x) {
    return round.x;
  }
  return target.clip.scale.x < 0 ? target.x - ARMOUR_DUST : target.x + ARMOUR_DUST;
}

// The round hits a body part it overlaps: damage, an arrow left in it, blood, and the round goes on if it pierces
// (F4:5962-6167). Armour on the part stops the round with a puff of dust; a riot shield stops it with sparks. Returns
// "stop" when the round is done with bodies this step
function hitZone(round, target, zone, box) {
  if (zone === "Shield") {
    if (target.type !== SHIELD_ZOMBIE) {
      return null;
    }
    if (round.weaponClass === "firearm") {
      sound.play(`sound_armorHit${Math.floor(Math.random() * 2) + 1}`, { x: target.x });
    }
    effects.particle("spark", box.x + box.w / 2, round.y);
    remove(round);
    return "stop";
  }
  if (ARMOURED[zone]?.has(target.type)) {
    effects.particle("dust", dustX(round, target), round.y);
    damageRanged(target, round, zone);
    remove(round);
    return "stop";
  }
  damageRanged(target, round, zone);
  if (round.kind === "arrow") {
    stickArrow(round, target, zone, box);
  }
  bleed(round, target, zone, box);
  round.hits.add(target);
  if (round.hits.size >= Math.max(1, round.piercing ?? 0)) {
    remove(round);
  }
  return "stop";
}

// Each body part in turn: the first the round overlaps and does not miss takes the hit. A miss marks the target, so the
// round never rolls on it again
function testZones(round, target, kind) {
  for (const zone of ZONES) {
    if (round.missed.has(target)) {
      return null;
    }
    const box = boxOf(target.clip, `collision${zone}`);
    if (!overlap(box, round.box)) {
      continue;
    }
    const how = { skill: round.skill, weaponType: round.weaponType };
    if (checkMiss(round.owner, target, round.kind === "grenade" ? "grenade" : "gun", how)) {
      round.missed.add(target);
      missText(target);
      continue;
    }
    const done = kind.hit(round, target, zone, box);
    if (done) {
      return done;
    }
  }
  return null;
}

function hitBodies(round, kind) {
  for (const target of bodies()) {
    if (inReach(round, target) && testZones(round, target, kind)) {
      return;
    }
  }
}

// ---------- Walls, floors and blocks ----------

function inset(min, range) {
  return Math.floor(Math.random() * range) + min;
}

// A wall decal across the floor: inside the room's edges, or on the near side of the block that stopped the round
function decalX(round, bounds, hitBlock) {
  let x = round.x;
  if (x < bounds.x) {
    x = bounds.x + inset(EDGE_INSET_MIN, EDGE_INSET);
  }
  if (x > bounds.w) {
    x = bounds.w - inset(EDGE_INSET_MIN, EDGE_INSET);
  }
  if (hitBlock) {
    const half = hitBlock.box.w / 2;
    const into = inset(BLOCK_INSET_MIN, BLOCK_INSET);
    x = round.owner.x > hitBlock.x ? hitBlock.x + half - into : hitBlock.x - half + into;
  }
  return x;
}

// Near the roof a decal turns up and near the floor down, kept inside the room's box (F4:10666-10686)
function decalSurface(round, bounds) {
  const place = { y: round.y, rotation: 0, side: round.owner.x < round.x ? "rightWall" : "leftWall" };
  if (place.y < bounds.y + constant("wallCollY")) {
    Object.assign(place, { rotation: -90, side: "roof" });
    if (place.y < bounds.y) {
      place.y = bounds.y + inset(EDGE_INSET_MIN, EDGE_INSET);
    }
  }
  if (place.y > room.floorY - constant("wallCollY")) {
    Object.assign(place, { rotation: 90, side: "floor" });
    if (place.y > bounds.y + bounds.h) {
      place.y = bounds.y + bounds.h - inset(EDGE_INSET_MIN, EDGE_INSET);
    }
  }
  return place;
}

// Where a round leaves its mark and what it marks: a wall, the roof or the floor, with a puff of dust (attachDecal
// F4:10629). An arrow's mark keeps the arrow's angle
function decalAt(round, hitBlock = null) {
  if (!round.decal || round.decal === "none") {
    return;
  }
  const bounds = room.markers.bounds ?? { x: 0, y: 0, w: room.width, h: room.floorY };
  const x = decalX(round, bounds, hitBlock);
  const place = hitBlock ? { y: round.y, rotation: 0, side: "block" } : decalSurface(round, bounds);
  if (hitBlock) {
    place.side = round.owner.x < x ? "rightWall" : "leftWall";
  }
  if (round.decal === "arrow") {
    place.rotation = round.angle - 180;
  }
  effects.decal(x, place.y, round.decal, { rotation: place.rotation, side: place.side });
  effects.particle("dust", x, place.y, { side: place.side });
}

function roomBlocks() {
  if (blocks.roomId !== room.id) {
    blocks = (room.blocks ?? [])
      .map((each) => ({ ...each, box: boxOf(room.markers[each.name]?.clip, "collision") }))
      .filter((each) => each.box);
    blocks.roomId = room.id;
  }
  return blocks;
}

// A block within 80 px stops a round that reaches it below its top (F4:6174-6212)
function hitBlocks(round, kind) {
  for (const block of roomBlocks()) {
    if (round.gone) {
      return;
    }
    const near = Math.abs(block.x - round.x) <= constant("collCheckBuffer");
    if (near && round.y > room.floorY - block.box.h && overlap(block.box, round.box)) {
      kind.block(round, block);
    }
  }
}

// Inside, the walls, the roof and the floor stop a round; outside, only the floor does (F4:6213-6276)
function hitWalls(round, kind) {
  const bounds = room.markers.bounds ?? { x: 0, y: 0, w: room.width };
  const pastWall = round.x < bounds.x + constant("wallCollX") || round.x > bounds.w - constant("wallCollX");
  const pastRoof = round.y < bounds.y + constant("wallCollY");
  const floor = round.y > room.floorY;
  const outside = room.def?.outside === true;
  if (outside ? floor : pastWall || pastRoof || floor) {
    kind.wall(round);
  }
}

// ---------- Kinds ----------

// Bullets and arrows: straight flight, damage on the body part they hit, a mark where a wall or block stops them
const STRAIGHT = {
  move: flyStraight,
  hit: hitZone,
  block(round, block) {
    decalAt(round, block);
    remove(round);
  },
  wall(round) {
    decalAt(round);
    remove(round);
  },
  expire: remove,
};

// ---------- Blasts ----------

// The explosion's picture at a room point, not lit by the room; its own timeline takes it away when it ends
function blastClip(x, y) {
  if (!artReady || !layers.effects || !page.lib.exported("effect_explosion")) {
    return;
  }
  const clip = page.lib.makeExported("effect_explosion");
  clip.label = "explosion";
  clip.eventMode = "none";
  const size = (Math.floor(Math.random() * BLAST_SIZE_RANGE) + BLAST_SIZE_MIN) / 100;
  clip.scale.set(Math.random() < 0.5 ? -size : size, size);
  clip.x = x;
  clip.y = y;
  layers.effects.addChild(clip);
}

// Where a blast on a body shows: near the middle of the body part it hit
function onBody(box) {
  const x = box.x + box.w / 2 + Math.floor(Math.random() * BLAST_SPREAD_X) - BLAST_SPREAD_X / 2;
  const y = box.y + box.h / 2 + Math.floor(Math.random() * BLAST_SPREAD_Y) - BLAST_SPREAD_Y / 2;
  return { x, y };
}

// A round blows up (showHitEffect "explosion" F4:10832, splashDamageCheck F4:6918): the picture where it struck (at the
// round itself on the ground), the shake and the bang, then the blast measured from the round. A round blows up once
function explode(round, at = null) {
  if (round.exploded) {
    return;
  }
  round.exploded = true;
  const where = at ?? { x: round.x, y: round.y };
  blastClip(where.x, where.y);
  camera.shake(BLAST_SHAKE, BLAST_SHAKE_PULSES * constant("screenShakeDelay"));
  sound.play(`sound_explosion_big${Math.floor(Math.random() * BLAST_SOUNDS) + 1}`);
  const hits = splash(round.x, round.y, round.owner, round);
  shots.blasts.push({ kind: round.kind, x: round.x, y: round.y, frame: world.frame, travel: round.travel, hits });
  if (shots.blasts.length > MOST_BLASTS) {
    shots.blasts.shift();
  }
}

// ---------- Hand grenades ----------

// Off a wall, a block or a body: the roll turns back, a little under half as fast, and the spin turns the other way
// (bounceGrenadeWall F4:21633)
function bounceWall(round) {
  if (round.stopped !== true) {
    round.across = -round.across / BOUNCE_KEEP;
    round.spinDir = 1;
  }
}

// Off the floor: the fall turns upward at a little under half its speed, and the roll slows by 1 to 3.9 times
// (bounceGrenade F4:21625)
function bounceFloor(round) {
  if (round.stopped !== true) {
    round.across /= rng.random(BOUNCE_SLOW) / 10 + 1;
    round.up = -round.up / BOUNCE_KEEP;
    round.spinDir = 1;
  }
}

// One step of a thrown grenade (F4:21583-21611): on the floor a slow bounce stops falling and a slow roll rests; it
// spins by its roll, rolls along its aim, and falls by its own gravity
function flyGrenade(round) {
  if (round.stopped === true) {
    return;
  }
  if (round.y >= room.floorY) {
    if (Math.abs(round.up) < GRENADE_SETTLE_UP) {
      round.up = 0;
      round.gravity = 0;
    }
    if (Math.abs(round.across) < GRENADE_SETTLE_ACROSS) {
      round.stopped = true;
    }
  }
  round.spin += round.spinDir * round.across * GRENADE_SPIN;
  round.across *= GRENADE_FRICTION;
  round.x += Math.cos(radians(round.angle)) * round.across;
  if (Math.abs(round.up) > 0) {
    round.up += round.gravity;
    round.y += round.up;
  }
  placeClip(round);
}

// A grenade bounces off the first body part it touches; the body only hears it (F4:5926-6167)
function grenadeHit(round, target) {
  bounceWall(round);
  alertHit(target, round.owner);
  return "stop";
}

const GRENADE = {
  move: flyGrenade,
  hit: grenadeHit,
  block: bounceWall,
  wall(round) {
    if (round.y >= room.floorY) {
      bounceFloor(round);
    } else {
      bounceWall(round);
    }
  },
  expire(round) {
    explode(round);
    remove(round);
  },
};

// ---------- M79 shells and rockets ----------

// An M79 shell flies along its aim, losing speed, and drops by a pull that grows every step; it points the way it
// moves (F4:21566-21576)
function flyShell(round) {
  const fromX = round.x;
  const fromY = round.y;
  round.x += Math.cos(radians(round.angle)) * round.speed;
  round.y += round.gravity + Math.sin(radians(round.angle)) * round.speed;
  round.speed *= SHELL_SLOW;
  round.gravity *= SHELL_DROP;
  round.spin = (Math.atan2(round.y - fromY, round.x - fromX) * 180) / Math.PI;
  placeClip(round);
}

// Whether a shell has flown far enough to go off; one that has not falls away as a dud (armDistance40mm F4:27987)
function armed(round) {
  return round.kind !== "m79" || round.travel >= constant("armDistance40mm");
}

// A dud shell drops off what it struck as a loose object (createBounceObject F4:5930)
function dud(round, onto, part) {
  effects.bounce(round.projectile, onto, { type: part });
}

// A shell or rocket on a body part: it blows up there once armed (a dud drops off instead), and the round's own
// damage lands as a bullet's would. A riot shield's box counts only on the riot shield zombie
function shellHit(round, target, zone, box) {
  if (zone === "Shield" && target.type !== SHIELD_ZOMBIE) {
    return null;
  }
  if (armed(round)) {
    explode(round, onBody(box));
  } else {
    dud(round, target, zone);
  }
  return hitZone(round, target, zone, box);
}

// A block or the room's walls and floor stop it: a mark, and a blast once armed (F4:6181-6276)
function shellStopped(round, block = null) {
  decalAt(round, block);
  if (armed(round)) {
    explode(round);
  } else {
    dud(round, round, "ground");
  }
  remove(round);
}

const SHELL = {
  move: flyShell,
  hit: shellHit,
  block: shellStopped,
  wall: (round) => shellStopped(round),
  expire: remove,
};

// A puff of the rocket's smoke where it is before it moves on, unless the player turned effects down
function puff(round) {
  if (!artReady || story.settings?.lowEffects || !layers.shots || !page.lib.exported("smoke_RPGtrail")) {
    return;
  }
  const clip = page.lib.makeExported("smoke_RPGtrail");
  clip.label = "smoke";
  clip.eventMode = "none";
  clip.scale.set((Math.floor(Math.random() * SMOKE_SIZE_RANGE) + SMOKE_SIZE_MIN) / 100);
  clip.x = round.x;
  clip.y = round.y;
  clip.rotation = radians(round.angle);
  layers.shots.addChildAt(clip, 0);
  light.apply(clip);
  const alpha = Math.floor(Math.random() * SMOKE_ALPHA_RANGE) + SMOKE_ALPHA_MIN;
  clip.alpha = alpha / 100;
  smoke.push({ clip, alpha });
}

function stepSmoke() {
  smoke = smoke.filter((each) => !each.clip.destroyed);
  for (const each of smoke) {
    each.alpha -= SMOKE_FADE;
    each.clip.alpha = each.alpha / 100;
    if (each.alpha < SMOKE_GONE) {
      each.clip.destroy({ children: true });
    }
  }
}

const ROCKET = {
  ...SHELL,
  move(round) {
    puff(round);
    flyStraight(round);
  },
};

// Registers how a kind of round flies and hits: { move, hit, block, wall, expire }, any left out as bullets do it
export function onKind(name, def) {
  kinds.set(name, { ...STRAIGHT, ...def });
}

// One step of every round in flight: its life runs down, it moves, then it tests bodies, blocks and walls in turn
function stepRound(round) {
  const kind = kinds.get(round.kind);
  round.life -= 1;
  round.travel += 1;
  if (round.life <= 0) {
    kind.expire(round);
    return;
  }
  kind.move(round);
  round.box = roundBox(round);
  hitBodies(round, kind);
  if (!round.gone) {
    hitBlocks(round, kind);
  }
  if (!round.gone) {
    hitWalls(round, kind);
  }
}

function stepShots() {
  stepSmoke();
  for (const round of [...world.shots]) {
    if (!round.gone) {
      stepRound(round);
    }
  }
}

export const shots = {
  // The latest rounds fired, oldest first, each with the world step it left on
  fired: [],

  // A round leaves the gun. It flies from the next step on
  spawn(round) {
    round.frame = world.frame;
    shots.fired.push(round);
    if (shots.fired.length > MOST_RECORDED) {
      shots.fired.shift();
    }
    if (!kinds.has(round.kind)) {
      return round;
    }
    Object.assign(round, { travel: 0, hits: new Set(), missed: new Set(), gone: false, box: null });
    if (round.kind === "grenade") {
      Object.assign(round, { across: GRENADE_THROW, up: GRENADE_UP, spin: round.angle, spinDir: -1, stopped: false });
    }
    round.clip = makeClip(round);
    placeClip(round);
    world.shots.push(round);
    return round;
  },

  // The latest blasts, oldest first: { kind, x, y, frame, travel, hits (combat entries) }
  blasts: [],

  // The rounds in flight now
  get flying() {
    return world.shots;
  },

  onKind,
  splash,
};

// The stuck arrow shows its "through" frame one time in two (S5312 frame 1)
function stuckArrowScript(clip, frame) {
  if (frame !== 1) {
    return;
  }
  if (Math.floor(Math.random() * 2) === 0) {
    clip.gotoAndStop("through");
  } else {
    clip.stop();
  }
}

// A new room starts with no rounds in the air
function clearRoom() {
  for (const round of [...world.shots]) {
    remove(round);
  }
  for (const each of smoke) {
    each.clip.destroy({ children: true });
  }
  smoke = [];
  blocks = [];
}

export function initShots(owner) {
  page = owner;
  onKind("bullet", {});
  onKind("arrow", {});
  onKind("grenade", GRENADE);
  onKind("m79", SHELL);
  onKind("rocket", ROCKET);
  page.lib.scripts.set(STUCK_ARROW_SPRITE, stuckArrowScript);
  const names = [...PROJECTILES.map((name) => `projectile_${name}`), ...EXTRA_ART];
  const ids = names.map((name) => page.lib.exported(name));
  page.lib
    .need(ids.filter(Boolean))
    .then(() => {
      artReady = true;
    })
    .catch((e) => console.warn("Union City: the rounds' art didn't load", e));
  world.stage("shots", stepShots);
  onRoom("leave", clearRoom);
  onRoom("build", clearRoom);
}
