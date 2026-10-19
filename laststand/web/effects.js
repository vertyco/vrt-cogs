// Effects in the world: muzzle flashes, shell casings and magazines, blood, dust and sparks, the marks rounds leave and
// the numbers that float up from a hit. Everything is picture only, so it rolls with Math.random and not the game's
// own dice, and everything timed runs on the game clock, so a pause holds it where it is.
//
// A thrown thing (casing, magazine, blood drop, chunk of meat) flies through layers.shots, tinted by the room's light,
// and when it lands it moves into layers.back, where the room's own tint covers it, and is taken away after the decal
// time. Until the pictures are in, an effect only records what was asked for.
import { boxOf, originOf, worldMatrix } from "./collide.js";
import { data } from "./data.js";
import { applyColor } from "./flash.js";
import { light } from "./light.js";
import { goto, gotoPlay, partAt } from "./rig.js";
import { layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { weaponOf } from "./weapons.js";
import { world } from "./world.js";

// Used until the converted constants load (F4:27040-27100)
const DEFAULTS = {
  bulletDustChance: 3,
  shellCasingChance: 2,
  bloodChance: 3,
  pickupEdgeBuffer: 100,
  lowDecalFade: 20000,
  medDecalFade: 10000,
  highDecalFade: 2000,
  lowBodyFade: 20000,
  medBodyFade: 10000,
  highBodyFade: 2000,
  critDamageTextScale: 120,
};
// The pictures the effects draw with, by export name
const ART = /^(particle_|shellCasing_|magazine_|decal_|ammo_|muzzleFlash|bloodPack$|damageText$)/;
// The most of each kind alive at once; the original reuses a depth after this many and the old one goes (F4:9840,
// 9691, 10640, 10602)
const MOST_THROWN = 300;
const MOST_PARTICLES = 100;
const MOST_DECALS = 1000;
const MOST_FLASHES = 50;
const MOST_BLOOD_PACKS = 100;
// Where settled things sit among the room's bodies and marks (depth_world_decals, _shellCasings, _blood)
const DECAL_DEPTH = 2000;
const CASING_DEPTH = 5000;
const BLOOD_DEPTH = 6000;
// A thrown thing falls 1.5 faster every step and loses 2% of its sideways speed (F4:10236-10237)
const GRAVITY = 1.5;
const FRICTION = 0.98;
// It lands somewhere in this many pixels above the floor, and hits it a little less far up while it is still bouncing
const LAND_BAND = 40;
const BOUNCE_BAND = 20;
const SINK_BELOW_FLOOR = 20;
// A thrown thing whose sideways speed is under this lands and stays; a faster one bounces back up at half speed. The
// speed is signed, so one thrown to the left never bounces (F4:10365, 10417)
const BOUNCE_SPEED = 2.5;
// Blood in the air splats on a wall one step in this many (F4:10263)
const WALL_SPLAT_ODDS = 60;
// A thrown thing's sideways speed turns round one time in this many (F4:10211)
const TURN_ODDS = 8;
// Numbers rise 20 px from 10 px over the target's head (ySlideTo over 4 s, easing out), and fade out over 1 s after
// 0.5 s (F4:18413-18446)
const TEXT_RISE = 20;
const TEXT_SLIDE_SECONDS = 4;
const TEXT_FADE_DELAY = 0.5;
const TEXT_FADE_SECONDS = 1;
// The most pictures kept in the log a check reads
const MOST_RECORDED = 200;

let page = null;
let artReady = false;
let serial = 0;
let bloodPacks = 0;
// Thrown things in the air: { node, kind, owner, across, up, angle, spin, bounces, flat, splatter, blood, sound }
let flying = [];
// Dust, sparks and smoke fading: { node, across, up, angle, spin, fade, hitGround }
let particles = [];
// Muzzle flashes, whose own timeline takes them away
let flashes = [];
// Marks on walls and floors, oldest first
let decals = [];
// Numbers rising: { clip, from, step }
let floats = [];
// The blocks of the room with their boxes, worked out once the room stands
let blocks = [];

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function roll(count) {
  return Math.floor(Math.random() * count);
}

function radians(degrees) {
  return (degrees * Math.PI) / 180;
}

function lowEffects() {
  return story.settings?.lowEffects === true;
}

function lowViolence() {
  return story.settings?.lowViolence === true;
}

function keep(entry) {
  entry.frame = world.frame;
  effects.log.push(entry);
  if (effects.log.length > MOST_RECORDED) {
    effects.log.shift();
  }
}

// Whether an export exists and its pictures are in
function drawable(name) {
  return artReady && Boolean(page.lib.exported(name));
}

// Keeps a list to its most, taking the oldest out of the world
function limit(list, most) {
  while (list.length > most) {
    const old = list.shift();
    (old.node ?? old).destroy?.({ children: true });
  }
}

// ---------- Taking things away ----------

// How long a body or a mark stays, by the player's setting: LOW 20 s, MED 10 s, HIGH 2 s of game time (the labels read
// backwards and are kept as the original has them)
function fadeFrames(type) {
  const setting = story.settings?.[`${type}Fade`] ?? "low";
  const name = `${setting}${type === "body" ? "Body" : "Decal"}Fade`;
  return Math.round((constant(name) / 1000) * page.lib.fps);
}

// The node is taken out of the room once its time is up. A pause stops the count
function expire(node, type = "decal") {
  world.later(
    fadeFrames(type),
    () => {
      if (!node.destroyed) {
        node.destroy({ children: true });
      }
    },
    { room: true },
  );
}

// ---------- Thrown things ----------

// Which way a body or a point faces: -1 left, 1 right
function facing(owner) {
  const across = owner.clip?.scale.x ?? owner.facing ?? 1;
  return across < 0 ? -1 : 1;
}

// A picture made at a size, mirrored when it faces left
function scaled(owner, size = 1) {
  return { x: facing(owner) * size, y: size };
}

// The world point of a marker node, a plain { x, y }, or a body part of the owner (its collision box clip). "ground" and
// no part mean the owner's own feet
function startOf(owner, point, part) {
  if (point?.parent) {
    return originOf(point);
  }
  if (point) {
    return { x: point.x, y: point.y };
  }
  const box = part && part !== "ground" && owner.clip ? partAt(owner.clip, `collision${part}`) : null;
  return box ? originOf(box) : { x: owner.x, y: owner.y };
}

// What each kind of thrown thing is made of (createBounceObject F4:9832-10208): its picture, how hard it is thrown
// sideways (away from the way its owner faces) and up, how fast it spins, and where it starts. null when the player's
// settings or the dice say there is none. bounces: it bounces off the floor and lands only when slow
const THROWN = {
  // Pieces of a roof coming down through a hole
  roof(owner) {
    return {
      art: "particle_roof",
      across: 1,
      up: 2,
      spin: roll(15),
      at: { x: owner.x + roll(150) - 75, y: owner.y + roll(20) - 10 },
      bounces: true,
      sound: "shellBounce",
    };
  },
  "40mm"(owner, point, part) {
    return { art: "ammo_40mm", across: 6, up: 13, spin: 25, scale: scaled(owner), at: startOf(owner, point, part), bounces: true, sound: "shellBounce" };
  },
  RPG(owner, point, part) {
    return { art: "ammo_RPG", across: 6, up: 13, spin: 25, scale: scaled(owner), at: startOf(owner, point, part), bounces: true, sound: "shellBounce" };
  },
  // A riot shield dropped from the hand of the zombie who held it
  riotShield(owner) {
    const size = Math.abs(owner.clip?.scale.x ?? 1);
    return {
      art: "particle_riotShield",
      across: 5,
      up: 5,
      spin: 10,
      scale: { x: size, y: owner.clip?.scale.x ?? 1 },
      at: startOf(owner, owner.clip ? partAt(owner.clip, "hand_front") : null),
      bounces: true,
    };
  },
  // The player's spent casing leaves the gun one shot in two
  shellCasing(owner) {
    if (lowEffects() || owner !== world.player || roll(constant("shellCasingChance")) !== 0) {
      return null;
    }
    const weapon = weaponOf(owner);
    const eject = owner.rig?.arms?.child("ejectPoint");
    if (!eject) {
      return null;
    }
    return {
      art: `shellCasing_${weapon.shell}`,
      across: 6,
      up: weapon.ref === "M249" ? -2 : 13,
      spin: 25,
      scale: scaled(owner),
      at: originOf(eject),
      bounces: true,
      sound: "shellBounce",
    };
  },
  // A magazine drops from the gun's mag point at 55% of its size
  mag(owner, point, type) {
    const weapon = weaponOf(owner);
    if (lowEffects() || !point) {
      return null;
    }
    const art = weapon.weaponType === "pistolAutomatic" ? `magazine_${type}` : `magazine_${weapon.ref}`;
    return { art, across: 0, up: 0, spin: 2, scale: scaled(owner, 0.55), at: originOf(point), bounces: true, flat: true, sound: "clipDrop" };
  },
  armChunk(owner, point, part) {
    if (lowViolence() || lowEffects()) {
      return null;
    }
    return { art: "particle_armChunk", across: 9, up: 4, spin: 2, scale: scaled(owner), at: startOf(owner, point, part), skin: owner.skinColour };
  },
  meatChunk(owner, point, part) {
    if (lowViolence() || lowEffects()) {
      return null;
    }
    return { art: "particle_meatChunk", across: 9, up: 4, spin: 10, scale: scaled(owner), at: startOf(owner, point, part), turn: roll(360) };
  },
  // A drop of blood: one in three is drawn. In the air it may splat on a wall, on the floor it splats flat
  blood(owner, point, part) {
    if (lowViolence() || lowEffects() || roll(constant("bloodChance")) !== 0) {
      return null;
    }
    return { art: "particle_blood", across: 8, up: 5, spin: 0, at: startOf(owner, point, part), turn: roll(360), splatter: true, blood: true };
  },
};

// Makes a thrown thing and starts it flying. owner is whose body it comes from (an actor, or { x, y, facing } for a
// place); point is a marker node or { x, y } it starts at, and sub the body part ("Head", "ground") or, for a
// magazine, the kind of gun it is for. Returns the picture, or null when nothing is drawn
export function createBounceObject(kind, owner, point = null, sub = null) {
  keep({ kind: "bounce", object: kind, sub, owner: owner.name ?? owner.kind });
  const make = THROWN[kind];
  const spec = make && artReady ? make(owner, point, sub) : null;
  if (!spec || !drawable(spec.art)) {
    return null;
  }
  const node = page.lib.makeExported(spec.art);
  node.label = kind;
  node.eventMode = "none";
  node.x = spec.at.x;
  node.y = spec.at.y;
  node.rotation = radians(spec.turn ?? 0);
  node.scale.set(spec.scale?.x ?? 1, spec.scale?.y ?? 1);
  if (spec.skin) {
    goto(node.child("armSkin"), spec.skin);
    goto(node.child("handSkin"), spec.skin);
  }
  layers.shots.addChild(node);
  light.apply(node);
  const across = (facing(owner) > 0 ? 1 : -1) * spec.across;
  const turned = roll(TURN_ODDS) === 0;
  flying.push({
    node,
    owner,
    across: Math.random() * (turned ? -across : across),
    up: -spec.up + (Math.random() * spec.up) / 2,
    angle: radians(Math.random() < 0.5 ? roll(60) : roll(60) + 300),
    spin: radians(spec.spin),
    bounces: spec.bounces === true,
    flat: spec.flat === true,
    splatter: spec.splatter === true,
    blood: spec.blood === true,
    sound: spec.sound,
  });
  limit(flying, MOST_THROWN);
  return node;
}

// Whether a point is over one of the room's blocks, where a landing thing is simply gone (particleCollisionBlocks
// F4:6891)
function overBlock(x) {
  if (blocks.roomId !== room.id) {
    blocks = (room.blocks ?? [])
      .map((each) => boxOf(room.markers[each.name]?.clip, "collision"))
      .filter((box) => box);
    blocks.roomId = room.id;
  }
  return blocks.some((box) => x >= box.x && x <= box.x + box.w);
}

// A thing comes to rest: it leaves the air for the room's back layer, loses its own tint (the layer is lit as a whole),
// and goes after the decal time
function settle(piece, depth, label = null) {
  const node = piece.node;
  flying = flying.filter((each) => each !== piece);
  if (overBlock(node.x)) {
    node.destroy({ children: true });
    return;
  }
  if (label) {
    node.gotoAndStop(label);
    node.rotation = 0;
  }
  node.scriptColor = null;
  applyColor(node, null);
  serial += 1;
  node.zIndex = depth + (serial % MOST_THROWN);
  layers.back.addChild(node);
  expire(node, "decal");
}

function floorY() {
  return room.floorY;
}

// One step of a thrown thing (the clip's onEnterFrame, F4:10230-10321)
function stepThrown(piece) {
  const node = piece.node;
  node.rotation += piece.spin;
  piece.across *= FRICTION;
  node.x -= Math.cos(piece.angle) * piece.across;
  piece.up += GRAVITY;
  node.y += piece.up;
  const ground = floorY();
  const bounds = room.markers.bounds ?? { x: 0, w: room.width };
  const edge = constant("pickupEdgeBuffer");
  if (!piece.bounces && piece.splatter && roll(WALL_SPLAT_ODDS) === 0) {
    settle(piece, BLOOD_DEPTH, piece.blood ? "wallSplat" : null);
    return;
  }
  if (!piece.bounces && node.y > ground - roll(LAND_BAND)) {
    settle(piece, BLOOD_DEPTH, piece.blood ? "splat" : null);
    return;
  }
  if (piece.bounces && node.y > ground - roll(LAND_BAND) && piece.across < BOUNCE_SPEED) {
    land(piece);
    return;
  }
  if (node.y > ground + SINK_BELOW_FLOOR) {
    settle(piece, CASING_DEPTH);
    return;
  }
  if (node.x <= bounds.x + edge || node.x >= bounds.x + bounds.w - edge) {
    piece.across = 0;
  }
  if (piece.bounces && node.y > ground - roll(BOUNCE_BAND) && piece.across >= BOUNCE_SPEED) {
    piece.up = -piece.up / 2;
  }
}

// A casing or magazine that has slowed enough comes to rest with its clink, flat if it is the kind that lies down
function land(piece) {
  if (piece.sound && piece.owner === world.player) {
    sound.play(`sound_${piece.sound}${roll(2) + 1}`);
  }
  if (piece.flat) {
    piece.node.rotation = radians(roll(2) === 0 ? -90 : 90);
  }
  settle(piece, CASING_DEPTH);
}

// ---------- Particles ----------

// A cloud of pieces thrown from a point (particleEmitter F4:9691): count + 1 of them, each 50% to 99% of its size.
// Each drifts along its angle and fades; those that may not touch the floor vanish when they reach it. wall names the
// wall or floor the dust drifts along ("random" for any way), turn picks a random way up or down instead
function emit(art, x, y, { count, across, up, fade, spin, wall = null, turn = false, hitGround = false }) {
  if (lowEffects() || !drawable(art)) {
    return;
  }
  for (let i = 0; i <= count; i += 1) {
    const node = page.lib.makeExported(art);
    node.eventMode = "none";
    node.x = x;
    node.y = y;
    node.scale.set((roll(50) + 50) / 100);
    const aim = particleAngle(turn, wall);
    node.rotation = radians(aim);
    layers.shots.addChild(node);
    light.apply(node);
    node.alpha = (roll(30) + 70) / 100;
    particles.push({
      node,
      across: Math.random() * (roll(2) > 0 ? across : -across),
      up: -up + (Math.random() * up) / 2,
      angle: radians(aim),
      spin: radians(spin),
      fade,
      hitGround,
    });
    limit(particles, MOST_PARTICLES);
  }
}

// The way a particle drifts: along a wall's face, any way, or a turn picked for it
const WALL_ANGLES = { leftWall: 90, rightWall: -90, roof: 180, floor: 0 };

function particleAngle(turn, wall) {
  if (wall === "random") {
    return roll(360);
  }
  if (wall && wall in WALL_ANGLES) {
    return WALL_ANGLES[wall];
  }
  if (turn) {
    return roll(2) > 0 ? roll(60) : roll(60) + 300;
  }
  return 0;
}

// One step of a particle (moveParticle F4:9786)
function stepParticle(each) {
  const node = each.node;
  node.alpha -= each.fade / 100;
  if (node.alpha < 0.15 || (each.hitGround && node.y >= floorY())) {
    each.dead = true;
    node.destroy({ children: true });
    return;
  }
  node.rotation += each.spin;
  node.x += Math.cos(each.angle) * each.across;
  node.y += Math.sin(each.angle) * each.up;
}

// Dust puffs off a wall, the roof, the floor or armour: one hit in three throws three clouds (bulletDustParticle)
function dust(x, y, wall) {
  if (roll(constant("bulletDustChance")) !== 0) {
    return;
  }
  emit("particle_dustShaft_bullet", x, y, { count: 0, across: 0, up: 0.5, fade: 6, spin: 0.05, wall });
  emit("particle_cloudDust_bullet", x, y, { count: 1, across: 0.5, up: 0.5, fade: 6, spin: 0.05, wall });
  emit("particle_dirt2_bullet", x + roll(50) - 25, y - 20, { count: 1, across: 1, up: 1, fade: 6, spin: 1.5, wall });
}

// Sparks off a riot shield (sparkParticle): two flecks that stay where they are and fade
function spark(x, y) {
  emit("particle_bulletHit", x, y, { count: 1, across: 0, up: 0, fade: 2, spin: 0, turn: true, hitGround: true });
}

// ---------- Steps ----------

function sweep(list) {
  return list.filter((each) => !(each.node ?? each).destroyed && !(each.node ?? each).removed);
}

function stepEffects() {
  for (const piece of [...flying]) {
    if (piece.node.destroyed) {
      flying = flying.filter((each) => each !== piece);
    } else {
      stepThrown(piece);
    }
  }
  for (const each of [...particles]) {
    if (!each.node.destroyed) {
      stepParticle(each);
    }
  }
  particles = particles.filter((each) => !each.dead && !each.node.destroyed);
  for (const clip of flashes) {
    if (clip.removed && !clip.destroyed) {
      clip.destroy({ children: true });
    }
  }
  flashes = sweep(flashes);
  decals = decals.filter((each) => !each.destroyed);
  stepFloats();
}

function easeOutExpo(t) {
  return t >= 1 ? 1 : 1 - 2 ** (-10 * t);
}

// Each number rises and fades on the game's clock, so a pause holds it where it is
function stepFloats() {
  const fps = page.lib.fps;
  floats = floats.filter((each) => !each.clip.destroyed);
  for (const each of floats) {
    each.step += 1;
    each.clip.y = each.from - TEXT_RISE * easeOutExpo(each.step / (TEXT_SLIDE_SECONDS * fps));
    const fading = (each.step - TEXT_FADE_DELAY * fps) / (TEXT_FADE_SECONDS * fps);
    each.clip.alpha = Math.max(0, Math.min(1, 1 - fading));
    if (fading >= 1) {
      each.clip.destroy({ children: true });
    }
  }
}

function clearRoom() {
  flying = [];
  particles = [];
  flashes = [];
  decals = [];
  floats = [];
  blocks = [];
}

export const effects = {
  // { kind, ..., frame } for the latest effects, oldest first
  log: [],

  // The flash at the muzzle of the shooter's gun (muzzleFlash F4:10602). It sits at the arms' flash point, moved along
  // the barrel by the weapon's flash offset, and points where the gun points
  muzzleFlash(actor, weapon) {
    keep({ kind: "muzzleFlash", owner: actor.name ?? actor.kind, weapon: weapon.ref, art: weapon.muzzleFlash });
    const arms = actor.rig?.arms;
    const point = arms?.child("flashPoint");
    if (!point || !weapon.muzzleFlash || !drawable(weapon.muzzleFlash)) {
      return null;
    }
    const m = worldMatrix(arms);
    const along = point.x + (weapon.flashOffset ?? 0);
    const clip = page.lib.makeExported(weapon.muzzleFlash);
    clip.eventMode = "none";
    clip.x = m[0] * along + m[2] * point.y + m[4];
    clip.y = m[1] * along + m[3] * point.y + m[5];
    clip.rotation = Math.atan2(m[1], m[0]);
    clip.scale.set(1, m[0] * m[3] - m[1] * m[2] < 0 ? -1 : 1);
    layers.shots.addChild(clip);
    flashes.push(clip);
    limit(flashes, MOST_FLASHES);
    return clip;
  },

  // A thing thrown from the shooter that bounces on the floor: "shellCasing", or "mag" with the magazine's kind
  // ("pistol", "rifle", "M249" or none) and the point in the arms it leaves from. Also the dropped riot shield, a
  // roof's pieces, and the chunks of a body
  bounce(kind, actor, { type = null, point = null } = {}) {
    return createBounceObject(kind, actor, point, type);
  },

  // Blood from a hit at a room point, thrown toward dir (1 right, -1 left): amount drops, each drawn one time in three
  // (the blood bounce objects of each hit)
  blood(x, y, dir, amount) {
    keep({ kind: "blood", x, y, dir, amount });
    for (let i = 0; i < amount; i += 1) {
      createBounceObject("blood", { x, y, facing: -dir }, { x, y });
    }
  },

  // The spray on the body that was hit (showBloodHit F4:10698): a puff of blood over the part, on the target's own
  // clip, bigger or smaller by chance and turned away from the shooter. Low violence shows only the smallest
  bloodPack(target, zone, owner) {
    keep({ kind: "bloodPack", zone });
    const body = target.clip;
    if (!drawable("bloodPack") || !body?.attach) {
      return null;
    }
    bloodPacks = (bloodPacks + 1) % MOST_BLOOD_PACKS;
    const name = `bldPack${bloodPacks}`;
    body.child(name)?.removeMovieClip();
    const pack = page.lib.makeExported("bloodPack");
    const part = partAt(body, `collision${zone}`);
    pack.x = (part?.x ?? 0) + roll(25) - 5;
    pack.y = (part?.y ?? 0) + roll(25) - 13;
    const size = (roll(40) + 80) / 100;
    const faces = body.scale.x > 0 ? 1 : -1;
    const turned = (owner.x < target.x && faces > 0) || (owner.x > target.x && faces < 0);
    pack.scale.set(turned ? -size : size, size);
    if (lowViolence()) {
      gotoPlay(pack, "base4");
    } else {
      gotoPlay(pack, zone === "Head" ? `head${roll(2) + 1}` : `base${roll(4) + 1}`);
    }
    body.attach(pack, name);
    return pack;
  },

  // A round's mark where a wall, the roof, the floor or a block stopped it (attachDecal F4:10629). kind is the weapon's
  // decal ("bulletSmall", "arrow", "blast"); rotation is in degrees; side is "leftWall", "rightWall", "roof" or "floor"
  decal(x, y, kind, { rotation = 0, side = null } = {}) {
    keep({ kind: "decal", x, y, decal: kind, rotation, side });
    const art = `decal_${kind}`;
    if (!drawable(art)) {
      return null;
    }
    const node = page.lib.makeExported(art);
    node.eventMode = "none";
    node.x = x;
    node.y = y;
    node.rotation = radians(rotation);
    serial += 1;
    node.zIndex = DECAL_DEPTH + (serial % MOST_DECALS);
    layers.back.addChild(node);
    decals.push(node);
    limit(decals, MOST_DECALS);
    expire(node, "decal");
    return node;
  },

  // A puff at a room point: "dust" off a wall or armour (bulletDustParticle), "spark" off a riot shield
  // (sparkParticle). side is the wall the dust drifts along
  particle(kind, x, y, { side = null } = {}) {
    keep({ kind: "particle", particle: kind, x, y, side });
    if (kind === "spark") {
      spark(x, y);
    } else {
      dust(x, y, side ?? "random");
    }
  },

  // A number or word floating up from a room point (showDamageText F4:18400): colour is a 0xRRGGBB for the words, crit
  // makes it bigger. Rises and fades on the game clock
  float(text, x, y, { colour = null, crit = false } = {}) {
    if (!drawable("damageText")) {
      return null;
    }
    const clip = page.lib.makeExported("damageText");
    const field = clip.child("txt");
    clip.x = x;
    clip.y = y;
    if (crit) {
      clip.scale.set(constant("critDamageTextScale") / 100);
    }
    if (field) {
      // The words take the colour themselves, so the field's black glow stays black around them
      if (colour !== null) {
        field.def = { ...field.def, color: `#${colour.toString(16).padStart(6, "0")}` };
        field.shown = null;
      }
      field.text = text;
    }
    clip.eventMode = "none";
    layers.effects.addChild(clip);
    floats.push({ clip, from: y, step: 0 });
    return clip;
  },

  // Takes a node out of the room once the body or decal fade time has passed on the game clock
  expire,

  // The state of the live effects, for checks
  get counts() {
    return { flying: flying.length, particles: particles.length, flashes: flashes.length, decals: decals.length, floats: floats.length };
  },

  // Everything in the air stops at a room change; the room's layers take the rest
  clearRoom,
};

export function initEffects(owner) {
  page = owner;
  layers.back.sortableChildren = true;
  const ids = Object.keys(page.lib.data.exports)
    .filter((name) => ART.test(name))
    .map((name) => page.lib.exported(name));
  page.lib
    .need(ids)
    .then(() => {
      artReady = true;
    })
    .catch((e) => console.warn("Union City: the effects' art didn't load", e));
  world.stage("shots", stepEffects);
  onRoom("build", clearRoom);
}
