// People who fight: the hostile humans (HERC scientists and soldiers, Jeb and Paul once they turn) and the friendly
// guards (the army at the Stadium, the HERC heavies on 10th Ave, the Union Island wall). Each is an actor (spec 5 B) of
// side "enemy" or "friend" built with makeHuman and dressed from its table in actors.json (setupAHuman F4:24676), with
// its own weapon, health and skills. A room's `enemies` list places them as the room is built, half a second of game
// time apart (setupHuman F4:24630).
//
// What a human does each step (humanAIRoutine F4:24841) is its state: "idle", "attack" (aim for 30 steps, pull the
// trigger whenever the gun is ready for up to 30 more, rest 20), "chase" (walk at 225 px a second to a point by the
// target), "follow" (a friendly one that may move walks after the player) and "stumble" (a hard hit slides it back).
// Every 10 steps it looks over everyone in the room and goes after the nearest it may fight: hostile humans fight the
// player, companions and zombies; friendly ones fight zombies only. Zombies go after both (zombies.js).
//
// Friendly guards never miss and take no damage, as they always played. Humans fall and land like the player, and are
// kept inside the room's edges. They are not remembered between visits: a room whose humans are all dead when the
// player leaves stays empty for good.
import { originOf } from "./collide.js";
import { onCombat } from "./combat.js";
import { data } from "./data.js";
import { blockCollide, player } from "./player.js";
import { goto, gotoPlay, makeHuman, partAt } from "./rig.js";
import { rng } from "./rng.js";
import { layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { aimWeapon, showPose, swing, weaponOf } from "./weapons.js";
import { world } from "./world.js";

// Used until the converted constants load (F4:36417-36418, 26111, 36300-36302)
const DEFAULTS = {
  humanRange: 400,
  humanMeleeRange: 80,
  wpSetCountMax: 35,
  NPCsetupDelay: 500,
  gravity: 1.5,
  jumpHeightBase: 11,
  chestHeadOffset: 10,
  enemyWeaponSkill: 10,
  companionWeaponSkill: 30,
  stumbleSpeed: 2,
  depth_world_human: 115250,
  depth_world_player: 115000,
};
// A human walks at the player's base speed, 7.5 px a step (225 px a second)
const WALK_SPEED = 7.5;
// The range a gun keeps is rolled up to 40 px either side of humanRange at each look (F4:24905)
const RANGE_SPREAD = 80;
// A human looks over the room every 10 steps (humTargCount F4:24868)
const SCAN_EVERY = 10;
// The fire cycle in steps: aim, then pull for up to 30, then rest until 50 have passed since the aim ended
const AIM_STEPS = 30;
const PULL_STEPS = 30;
const CYCLE_STEPS = 50;
// One time in 100 a firing human crouches, and one time in 100 a crouched one stands (F4:25024-25031)
const STANCE_ODDS = 100;
// Each human's walking point sits 50 px further along than the one before it in the list
const SPACING = 50;
// Humans are named human1 to human11 and the count wraps after that (setupAHuman F4:24678)
const MOST_NAMES = 10;
const FAR = 9999999;
// The edges a fall falls at most per step, as the player's
const FALL_MOST = 10;
// Jeb and Paul turned hostile stand where the original's stand-in room puts them (fakeRoom F4:36347-36349)
const TURN_PLACES = { JebEnemy: 550, PaulEnemy: 950 };
// The arm aims at a zombie's chest, a riot zombie's legs, a helmetless riot zombie's head and a crawler's legs, each
// 10 px higher except the riot zombies' (aimWeapon F4:12750-12769)
const AIM_PARTS = {
  zombieRiotShield: ["collisionLegs", false],
  zombieRiot: ["collisionLegs", false],
  zombieRiotNoHelmet: ["collisionHead", false],
  zombieCrawl: ["collisionLegs", true],
};
const DEFAULT_AIM = ["collisionChest", true];
const MOST_LOGGED = 300;

let page = null;
let named = 0;
// Spawns still waiting on their delay in this room, so a room left before they appear is not taken for cleared
let waiting = 0;
// Counters a human's death adds to, and who hears of each
const tally = {};
const countListeners = [];

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

// The table of a human type, or undefined for a name that is not one
function humanType(key) {
  return data.actors?.humans?.[key];
}

// ---------- Setup ----------

function pickName(list) {
  return rng.pick(list ?? [])?.name;
}

// The head as the table gives it, with "random" picked from the appearance lists (F4:24785-24808)
function lookOf(def) {
  const appearance = data.actors?.appearance ?? {};
  const pick = (value, list) => (value === "random" ? rng.pick(list ?? []) : value);
  return {
    sex: def.sex,
    skin: def.skinColour === "random" ? pickName(appearance.skins) : def.skinColour,
    hairColour: def.hairColour === "random" ? pickName(appearance.hairColours) : def.hairColour,
    hair: pick(def.hair, appearance.hairStyles),
    facialHair: pick(def.facialHair, appearance.facialHair),
  };
}

function clothesOf(def) {
  return {
    top: def.clothesTop,
    bottom: def.clothesBottom,
    shoes: def.clothesShoe,
    torso: def.torsoAccessory,
    head: def.headAccessory,
    face: def.faceAccessory,
  };
}

// The human's own skills: every skill at the skill the original gives people it shoots for, a guard's like a
// companion's and an enemy's lower (F4:26702), with no attributes to add to them
function ownStats(friendly) {
  const level = constant(friendly ? "companionWeaponSkill" : "enemyWeaponSkill");
  const skills = Object.fromEntries(Object.keys(data.actors?.skills ?? {}).map((name) => [name, level]));
  const attributes = Object.fromEntries((data.actors?.lists?.allAttributes ?? []).map((name) => [name, 0]));
  return { skills, attributes };
}

function nextName() {
  if (named > MOST_NAMES) {
    named = 0;
  }
  named += 1;
  return `human${named}`;
}

// The actor's flags at the start (setupAHuman F4:24702-24760). Its weapon, spare and stored weapon, health and last
// health are its own
function makeActor(key, def, x, facing) {
  const friendly = def.friendly === true;
  const actor = { kind: "human", key, name: nextName(), side: friendly ? "friend" : "enemy", friendly };
  Object.assign(actor, { stationary: def.stationary === true, invulnerable: def.invulnerable === true });
  Object.assign(actor, { health: def.health, healthMax: def.health, lastHealth: def.health, xpBonus: def.xpBonus });
  Object.assign(actor, { x, y: room.floorY, facing, sex: def.sex, weapon: def.weapon, ...ownStats(friendly) });
  Object.assign(actor, { survivor: true, humanEnemy: true, human: true, alive: true, state: "idle" });
  Object.assign(actor, { wp: world.player?.x ?? x, wpSet: false, wpReached: false, wpSetCount: 0 });
  Object.assign(actor, { shotCount: 0, burstCount: 0, waitCount: 0, scanCount: 0, curTarget: null, closeZom: FAR });
  Object.assign(actor, { range: constant("humanRange"), crouched: false, standing: true, moving: false });
  Object.assign(actor, { jumping: false, falling: false, landed: true, jumpAnim: false, walkForwardAnim: false });
  Object.assign(actor, { jumpHeight: constant("jumpHeightBase"), jumpHeightBase: constant("jumpHeightBase") });
  Object.assign(actor, { firing: false, firingAnim: false, reloading: false, shoving: false, meleeSwing: false });
  Object.assign(actor, { collideLeft: false, collideRight: false, climbing: false, lastCollision: null });
  Object.assign(actor, { transitioning: false, aimLocked: false, controlsLocked: false, animating: false });
  return actor;
}

// The weapon in hand and the backpack: a human carries no spare weapon (F4:24770-24776)
function weaponsOf(def) {
  return { weapon: def.weapon, stored: "hands", backpack: def.backpack === true };
}

function placeClip(human) {
  if (human.clip && !human.clip.destroyed) {
    human.clip.x = human.x;
    human.clip.y = human.y;
  }
}

// x inside the room's edges (the edge buffer, setupAHuman F4:24688-24695)
function withinEdges(x) {
  return Math.min(room.edges.right, Math.max(room.edges.left, x));
}

// A human of a type stands in the room at x, dressed, armed and facing 1 (right) or -1 (left). Left out, it faces left
// when the player came in past x 100 (F4:24697). Returns the actor, or null for a type that does not exist
export function spawnHuman(key, x, { facing } = {}) {
  const def = humanType(key);
  if (!def) {
    console.warn(`Union City: no human type called ${key}`);
    return null;
  }
  const dir = facing ?? ((room.arrivalX ?? 0) > 100 ? -1 : 1);
  const human = makeActor(key, def, withinEdges(Number(x)), dir < 0 ? -1 : 1);
  const made = makeHuman({ sex: def.sex, look: lookOf(def), clothes: clothesOf(def), ...weaponsOf(def) });
  made.bind(human);
  made.setFacing(human.facing);
  goto(made.clip, "standing");
  made.clip.zIndex = constant("depth_world_human") - constant("depth_world_player") + named;
  layers.actors.addChild(made.clip);
  placeClip(human);
  human.charHeight = made.clip.height;
  world.humans.push(human);
  return human;
}

// Jeb or Paul turns on the player after quest 015 (triggerJebAndPaul F4:24181): the hostile one appears at its place.
// key is "Jeb", "Paul" or the hostile one's own key
export function humanTurnHostile(key) {
  const hostile = key.endsWith("Enemy") ? key : `${key}Enemy`;
  return spawnHuman(hostile, TURN_PLACES[hostile] ?? room.arrivalX);
}

// Whether a person's story state keeps them out of the room (npc[key].state == "off", F4:24637)
function switchedOff(key) {
  const state = story.npcs?.[key]?.state ?? data.story?.npcs?.[key]?.state;
  return state === "off";
}

function cleared() {
  return story.rooms?.[room.id]?.clr === true;
}

// The room's enemies list, each half a second of game time after the one before (setupHuman F4:24630). A room left
// with nobody alive in it stays cleared
function placeRoomHumans() {
  world.humans.length = 0;
  waiting = 0;
  if (!story.player || cleared()) {
    return;
  }
  const delay = (constant("NPCsetupDelay") * page.lib.fps) / 1000;
  (room.def?.enemies ?? []).forEach((entry, i) => {
    if (switchedOff(entry.key)) {
      return;
    }
    if (i === 0) {
      spawnHuman(entry.key, entry.x);
      return;
    }
    waiting += 1;
    world.later(
      Math.round(i * delay),
      () => {
        waiting -= 1;
        spawnHuman(entry.key, entry.x);
      },
      { room: true },
    );
  });
}

// Leaving a room that places humans with none of them alive marks it cleared (saveClearRoom F4:1280, 14479)
function leaveRoom(left) {
  if (!left?.id || !story.player || !(left.def?.enemies?.length > 0)) {
    return;
  }
  if (world.humans.length === 0 && waiting === 0) {
    story.rooms ??= {};
    story.rooms[left.id] = { ...story.rooms[left.id], clr: true };
  }
}

// ---------- Targets ----------

// Whom a human leaves alone (F4:24876-24896): a friendly one spares the player, survivors (other humans and companions)
// and anyone friendly; a hostile one spares the other hostile ones
function spares(human, other) {
  if (human.friendly) {
    return other === player || other.survivor === true || other.friendly === true || other.companion === true;
  }
  return other.friendly === false;
}

// Everyone in the room a human could look at: the player, companions, the other humans and zombies
function everyone() {
  const all = [...world.companions, ...world.humans, ...world.zombies];
  if (world.player === player) {
    all.unshift(player);
  }
  return all;
}

function isMelee(human) {
  return weaponOf(human).weaponClass === "melee";
}

// How close a human gets before it attacks: its gun's rolled range, or 80 px with a melee weapon
function reachOf(human) {
  return isMelee(human) ? constant("humanMeleeRange") : human.range;
}

// One person the look found (F4:24898-24976): someone no further than the current target, and nearer than any picked
// since the target was last lost, becomes the target, attacked within reach and chased beyond it. A melee human whose
// target is out of reach chases it
function weigh(human, other) {
  const dist = Math.abs(human.x - other.x);
  const current = human.curTarget ? Math.abs(human.x - human.curTarget.x) : FAR;
  human.range = constant("humanRange") + (rng.random(RANGE_SPREAD) - RANGE_SPREAD / 2);
  human.alerted = true;
  if (dist > current || other === human) {
    return;
  }
  if (dist < human.closeZom) {
    human.closeZom = dist;
    human.curTarget = other;
    human.state = dist <= reachOf(human) ? "attack" : "chase";
  }
  if (isMelee(human) && current > constant("humanMeleeRange")) {
    human.state = "chase";
  }
}

// Every 10 steps of its own count a human looks over the room
function scan(human) {
  human.scanCount -= 1;
  if (human.scanCount >= 0) {
    return;
  }
  human.scanCount = SCAN_EVERY;
  for (const other of everyone()) {
    if (other.alive === true && !spares(human, other)) {
      weigh(human, other);
    }
  }
}

function lostTarget(human) {
  return human.curTarget?.alive !== true;
}

// Where the arm points (aimWeapon F4:12748-12786): at the target's chest or the part its kind calls for, or, with no
// target, at the player's chest for a hostile human and for a friendly one following them
function aimPoint(human) {
  const target = human.curTarget;
  if (target?.alive === true && target.clip && partAt(target.clip, "collisionHead")) {
    const [path, lift] = AIM_PARTS[target.type] ?? DEFAULT_AIM;
    return chestOf(target, path, lift);
  }
  const follows = human.friendly && human.state === "follow" && !human.stationary;
  if ((!human.friendly || follows) && world.player?.clip) {
    return chestOf(world.player, DEFAULT_AIM[0], true);
  }
  return human.aimTarget ?? null;
}

function chestOf(actor, path, lift) {
  const node = partAt(actor.clip, path);
  if (!node) {
    return { x: actor.x, y: actor.y };
  }
  const point = originOf(node);
  return { x: point.x, y: point.y - (lift ? constant("chestHeadOffset") : 0) };
}

function aimAt(human) {
  human.aimTarget = aimPoint(human);
  aimWeapon(human);
}

// ---------- States ----------

function standStill(human) {
  human.walkForwardAnim = false;
  goto(human.clip, "standing");
}

function walkAnim(human) {
  if (!human.walkForwardAnim) {
    human.walkForwardAnim = true;
    gotoPlay(human.clip, "walk");
  }
}

// A step toward the walking point at the walking speed; a block in the way makes it jump. The original lets the side it
// is blocked on hold back the other way (F4:25096-25117)
function walkToWaypoint(human) {
  if (human.wp === null || human.wp === undefined) {
    return;
  }
  if (human.x < human.wp && !human.collideLeft) {
    walkAnim(human);
    human.x += WALK_SPEED;
  }
  if (human.x > human.wp && !human.collideRight) {
    walkAnim(human);
    human.x -= WALK_SPEED;
  }
  human.x = withinEdges(human.x);
  if (human.collideLeft || human.collideRight) {
    human.jumping = true;
  }
}

// One time in 100 the human drops to a crouch, and one time in 100 a crouched one stands, through the art's transition
function changeStance(human) {
  const crouch = rng.random(STANCE_ODDS) === 0;
  const stand = rng.random(STANCE_ODDS) === 0 && human.crouched;
  if (crouch) {
    human.transitioning = true;
    human.rig.setCrouch(true);
  }
  if (stand) {
    human.transitioning = true;
    human.rig.setCrouch(false);
  }
}

// The trigger: a gun fires its animation until the magazine is out, then reloads; a melee weapon swings
// (F4:25042-25073). The rate is the length of the weapon's animation, as for the player
function pullTrigger(human) {
  const weapon = weaponOf(human);
  if (weapon.weaponClass === "melee") {
    swing(human, weapon);
    logFire(human, "swing");
    return;
  }
  if (human.shotCount < (weapon.maxAmmo ?? 0)) {
    human.firing = true;
    gotoPlay(human.rig.arms, `${weapon.weaponType}_fire`);
    human.shotCount += 1;
    logFire(human, "fire");
    return;
  }
  human.shotCount = 0;
  human.reloading = true;
  human.reloadCount = 0;
  gotoPlay(human.rig.arms, `${weapon.reloadClip ?? weapon.weaponType}_reload`);
  logFire(human, "reload");
}

// After the aim, the trigger is pulled whenever the weapon is ready for 30 steps, then the human rests until 50 have
// passed and the cycle starts over
function burst(human) {
  human.burstCount += 1;
  if (human.burstCount <= PULL_STEPS && !human.firingAnim && !human.reloading) {
    changeStance(human);
    pullTrigger(human);
  }
  if (human.burstCount > CYCLE_STEPS) {
    human.burstCount = 0;
    human.waitCount = 0;
    human.firing = false;
  }
}

// Attack (F4:24990-25081): aim at the target every step; a target that walks out of reach is chased, a dead one
// dropped; after 30 steps of aiming the trigger cycle runs
function attack(human) {
  human.waitCount += 1;
  aimAt(human);
  if (human.animating) {
    human.animating = false;
    human.transitioning = false;
    standStill(human);
  }
  if (human.curTarget && Math.abs(human.x - human.curTarget.x) > reachOf(human)) {
    human.firingAnim = false;
    human.reloading = false;
    human.state = "chase";
  }
  if (lostTarget(human)) {
    human.curTarget = null;
    human.state = "idle";
  }
  if (human.waitCount >= AIM_STEPS) {
    burst(human);
  }
}

// Chase (F4:25083-25134): now and then a walking point is set just past the target, 50 px further along for each
// human before this one; within 80 px of it the human stops and attacks. Stationary humans never move
function chase(human, index) {
  if (human.stationary) {
    return;
  }
  const most = constant("wpSetCountMax");
  human.wpSetCount -= 1;
  if (human.wpSetCount <= rng.random(Math.floor(most / 20))) {
    human.wpSetCount = most;
    if (!human.wpSet && human.curTarget) {
      aimAt(human);
      human.wpReached = false;
      human.wpSet = true;
      human.wp = human.curTarget.x + Math.round(SPACING * index);
    }
  }
  walkToWaypoint(human);
  if (human.wp !== null && Math.abs(human.x - human.wp) <= constant("humanMeleeRange") && !human.wpReached) {
    human.wpReached = true;
    human.wpSet = false;
    human.wp = null;
    standStill(human);
    human.state = "attack";
  }
}

// Follow (F4:25136-25180): a friendly human that may move walks after the player while they walk, stopping a little
// short, each further back than the one before
function follow(human, index) {
  const most = constant("wpSetCountMax");
  human.wpSetCount -= 1;
  if (human.wpSetCount <= rng.random(Math.floor(most / 3))) {
    human.wpSetCount = most;
    if (!human.wpSet && world.player?.moving === true) {
      aimAt(human);
      human.wpReached = false;
      human.wpSet = true;
      human.wp = world.player.x + Math.round(SPACING * index);
    }
  }
  walkToWaypoint(human);
  const near = rng.random(SPACING) + Math.round(index * SPACING);
  if (human.wp !== null && Math.abs(human.x - human.wp) <= near && !human.wpReached) {
    human.wpReached = true;
    human.wpSet = false;
    human.wp = null;
    standStill(human);
  }
}

// A hard hit slides a human back 2 px a step for the stumble's distance, then it carries on with what it was doing.
// The human's art has no stumble of its own, so the slide's end hands it back
function stumbleSlide(human) {
  const left = human.stumbleDir === "left";
  const short = left ? human.x > human.stumbleDistance : human.x < human.stumbleDistance;
  const inRoom = left ? human.x > room.edges.left : human.x < room.edges.right;
  const blocked = left ? human.collideLeft : human.collideRight;
  if (short && inRoom && !blocked) {
    human.x += left ? -constant("stumbleSpeed") : constant("stumbleSpeed");
    return;
  }
  Object.assign(human, { stumbling: false, stumbleMoving: false, stumbleDistance: 0 });
  human.state = human.lastState ?? "idle";
}

const STATES = {
  idle(human) {
    if (human.animating) {
      human.animating = false;
      standStill(human);
    }
  },
  attack,
  chase,
  follow,
  stumble: stumbleSlide,
};

// One human's step (humanAIRoutine F4:24851-24983): a lost target is dropped, the room looked over, a friendly human
// with nobody to fight follows the player, then the state runs
function think(human, index) {
  if (lostTarget(human)) {
    human.closeZom = FAR;
    human.curTarget = null;
    if (human.state !== "stumble") {
      human.state = "idle";
    }
  }
  if (human.state !== "stumble") {
    scan(human);
  }
  if (!human.curTarget && human.friendly && !human.stationary && human.state !== "stumble") {
    human.state = "follow";
    human.closeZom = FAR;
    human.firing = false;
  }
  STATES[human.state]?.(human, index);
  placeClip(human);
}

function humanAI() {
  world.humans.forEach((human, index) => {
    if (human.alive === true && human.rig && !human.clip.destroyed) {
      think(human, index);
    }
  });
}

// ---------- Falling and blocks ----------

function land(human) {
  human.y = room.floorY;
  human.jumpHeight = human.jumpHeightBase;
  Object.assign(human, { jumping: false, falling: false, landed: true, standing: true, crouched: false });
  human.jumpAnim = false;
  human.walkForwardAnim = false;
}

// A jump rises by its speed and slows by gravity each step, falling at most 10 a step, and lands on the floor; a walk
// off a block drops the same way (characterGravity F4:12168, run for humans)
export function humanGravity(human) {
  if (human.jumping) {
    human.landed = false;
    if (!human.jumpAnim) {
      human.jumpAnim = true;
      gotoPlay(human.clip, "jump");
    }
    human.y -= human.jumpHeight;
    human.jumpHeight -= constant("gravity");
    human.falling ||= human.jumpHeight < 0;
    human.jumpHeight = Math.max(-FALL_MOST, human.jumpHeight);
    if (human.y >= room.floorY && human.falling) {
      land(human);
    }
  } else if (human.falling) {
    human.y -= human.jumpHeight;
    human.jumpHeight -= constant("gravity");
    if (human.y >= room.floorY) {
      land(human);
    }
  }
}

function living() {
  return world.humans.filter((human) => human.alive === true && human.clip && !human.clip.destroyed);
}

// The room's blocks stop a human walking into their sides and catch it falling onto their tops (moveCollisions
// F4:6815-6878). What blocked it last step is forgotten first
function humanBlocks() {
  for (const human of living()) {
    human.collideLeft = false;
    human.collideRight = false;
    blockCollide(human);
  }
}

// ---------- Hits and deaths ----------

// A guard's health never goes down
function guardHit({ target }) {
  if (target?.invulnerable === true && target.human === true) {
    target.health = target.healthMax;
    target.lastHealth = target.health;
  }
}

// A man's death cry, now and then the Wilhelm scream; a woman's own (playHumanDeadSound F4:5369)
function deathSound(human) {
  let name = `sound_humanDead${rng.random(4) + 1}`;
  if (human.sex === "male") {
    name = rng.random(100) === 0 ? "sound_humanDeadWilhelm" : `sound_humanDead${rng.random(3) + 1}`;
  } else if (human.sex === "female") {
    name = `sound_humanDeadFemale${rng.random(2) + 1}`;
  }
  sound.play(name, { x: human.x });
}

function count(key) {
  tally[key] = (tally[key] ?? 0) + 1;
  for (const fn of countListeners) {
    try {
      fn(key, 1);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

// Registers fn(key, amount) for each counter a human's death adds to: killHuman for the player's kills, and
// killJumping when the player was off the ground (F4:5666-5673, 6392-6403)
export function onHumanCount(fn) {
  countListeners.push(fn);
}

// A human dies (F4:5657-5712): the cry, the counters, a standing death in the full-body pose with the weapon hidden,
// and it leaves the room's list. The body stays where it fell
function killedByHit(entry) {
  const human = entry.target;
  const index = world.humans.indexOf(human);
  if (index < 0 || human.human !== true) {
    return;
  }
  world.humans.splice(index, 1);
  Object.assign(human, { state: "dead", firing: false, curTarget: null });
  deathSound(human);
  if (entry.owner === player) {
    count("killHuman");
    if (entry.airborne === true) {
      count("killJumping");
    }
  }
  if (human.clip && !human.clip.destroyed) {
    human.rig.setAnimMode("full");
    const held = human.rig.animWeapon;
    if (held) {
      held.visible = false;
    }
    gotoPlay(human.clip, `death_standing${rng.random(2) + 1}`);
  }
}

// ---------- The step ----------

// The arm, torso and head keep their aim after the timeline moved them
function holdPoses() {
  for (const human of living()) {
    showPose(human);
  }
}

function placeClips() {
  world.humans.forEach(placeClip);
}

function logFire(human, kind) {
  humans.fireLog.push({ name: human.name, key: human.key, kind, frame: world.frame, target: human.curTarget?.name });
  if (humans.fireLog.length > MOST_LOGGED) {
    humans.fireLog.shift();
  }
}

export function initHumans(owner) {
  page = owner;
  onRoom("leave", leaveRoom);
  onRoom("build", placeRoomHumans);
  onCombat("hit", guardHit);
  onCombat("kill", killedByHit);
  world.onReset(() => {
    waiting = 0;
  });
  world.stage("interface", holdPoses);
  world.stage("gravity", () => living().forEach(humanGravity));
  world.stage("collisions", humanBlocks);
  world.stage("humans", humanAI);
  page.steppers.push(placeClips);
}

export const humans = {
  spawnHuman,
  humanTurnHostile,
  onHumanCount,
  tally,
  // { name, key, kind ("fire", "swing" or "reload"), frame, target } for each trigger pull, oldest first
  fireLog: [],
};

// Helpers for page.py checks
export const humansDebug = {
  spawnHuman,
  humanTurnHostile,

  // The humans in the room now
  humanList() {
    return world.humans.map((human) => ({
      name: human.name,
      key: human.key,
      side: human.side,
      x: Math.round(human.x),
      y: Math.round(human.y),
      facing: human.facing,
      state: human.state,
      health: human.health,
      healthMax: human.healthMax,
      target: human.curTarget?.name ?? human.curTarget?.kind ?? null,
      range: human.range,
      waitCount: human.waitCount,
      burstCount: human.burstCount,
      shotCount: human.shotCount,
      firing: human.firing,
      firingAnim: human.firingAnim,
      reloading: human.reloading,
      crouched: human.crouched,
      jumping: human.jumping,
    }));
  },

  // The trigger pulls since the given world step
  fireLog(since = 0) {
    return humans.fireLog.filter((each) => each.frame >= since);
  },
};
