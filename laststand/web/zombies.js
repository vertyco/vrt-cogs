// Zombies: the 21 types the director can spawn, how one is set up (setupZombie F4:8587), how it is dressed
// (decorateZombie F4:8835) and the voices it has. A zombie is an actor (spec 5 B) of side "zombie" whose art is the
// original's `zombie` clip (6800) or, for the dog, `zombieDog` (5302). Its flags (state, alerted, animating ...) sit on
// the actor, which the art's own script lines write to through the clip's owner.
//
// What a zombie does each step (zombieAIRoutines F4:9169) is its state: "wander", "idle", "chase", "climb", "attack",
// "stumble" (the slide is combat.js's), "grab" or "dead". Zombies also fall (zombieGravity F4:9512), meet the room's
// blocks (moveCollisions F4:6811) and land their blows (meleeCollisions F4:6540) here, each in its place in the step.
// They wake once a second by sensing or seeing the player and on every gunshot's noise, and a grab holds the player in
// a struggle until enough presses shove the zombie off (F4:9069-9157, 15821-15982).
//
// A zombie that dies plays the death its wound calls for and lies as a body until the body fade time passes. Zombies
// still alive when the player leaves a room are kept in a ring of ten memories and come back, unalerted, with the room
// (saveZombies F4:9573, restoreZombies F4:9614).
import { boxOf, inside } from "./collide.js";
import { checkMiss, damageMelee, damageRanged, missText, onCombat, stumble } from "./combat.js";
import { data } from "./data.js";
import { dropBackPack, rollDropper } from "./drops.js";
import { effects } from "./effects.js";
import { input } from "./input.js";
import { light } from "./light.js";
import { attributeOf, face, player, releaseCrouch, roomBlocks } from "./player.js";
import { colourOf, frameFor, goto, gotoPlay, onRigCall, ownerOf, paintFlat, partAt } from "./rig.js";
import { rng } from "./rng.js";
import { layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { onNoise, weaponNoise, weaponOf } from "./weapons.js";
import { world } from "./world.js";

const ZOMBIE_EXPORT = "zombie";
const DOG_EXPORT = "zombieDog";
// The zombie clip's frame script (S6800 frame 39): a zombie that has landed goes to its start pose
const ZOMBIE_SPRITE = 6800;
const START_FRAME = 39;
const SHIELD_TYPE = "zombieRiotShield";
// Used until the converted constants load (F4:26111-26112, 26500-26660)
const DEFAULTS = {
  zombieBaseHealth: 9,
  zombieBaseDamage: 7,
  zombieScale: 55,
  zombieFemaleChance: 4,
  zombieGrabRange: 65,
  zombSpawnBuffer: 130,
  moveEdgeBuffer: 50,
  dirChangeMax: 120,
  zomAttackSoundChance: 85,
  zomChancePlayNoDeathSound: 20,
  depth_world_zombies: 12800,
  depth_world_player: 115000,
  zombieIdleSoundChance: 200,
  zomAlertSoundChance: 5,
  zomChaseSoundChance: 90,
  zomMeleeHitRange: 90,
  meleeCollCheckBuffer: 100,
  dirChangeChance: 100,
  alertRandRange: 500,
  zombieRiotPause: 300,
  zombieRiotPauseLength: 90,
  numZombieAttacks: 2,
  grabYRange: 40,
  zombieGrabChance: 100,
  highClimbHeight: 180,
  struggleCountMultiplier: 2,
  struggleMin: 3,
  struggleMax: 8,
  struggleSoundChance: 99,
  climbXShift: 40,
  climbBuffer: 15,
  gravity: 1.5,
  jumpHeightBase: 11,
  moveCollBuffer: 45,
  collTopBuffer: 15,
  depth_world_zombiesDead: 11500,
  zombieHeadDeaths: 2,
  zombieBodyDeaths: 1,
  zombieLegDeaths: 2,
  zombieExplodeDeaths: 2,
  damageThreshold: 99,
};
// The shield zombie's reach, and the others' (F4:8746)
const ATTACK_RANGE_BASE = 45;
const ATTACK_RANGE_SPREAD = 30;
// A zombie's floor sits up to 5 px either side of the room's (F4:8658)
const FLOOR_JITTER = 10;
const FLOOR_JITTER_OFFSET = 5;
// A zombie's size is the base plus up to 3 either way, and 4 less for a woman (F4:8688)
const SCALE_SPREAD = 6;
const SCALE_OFFSET = 3;
const FEMALE_SCALE_DROP = 4;
const WANDER_SPEED = 0.75;
const SIGHT_RANGE = 600;
const SENSE_RANGE = 150;
const FAR = 9999999;
// Depth numbers wrap so a long play never grows them without end
const DEPTH_SLOTS = 1000;
// The hair every uniform wears (a crew cut) and the facial hair army wear (none), as indices into the lists
const UNIFORM_HAIR = 6;
const ARMY_FACIAL_HAIR = 7;
// The dog's sounds when it has no voice of its own to pick from
const DOG_VOICE = "sound_zombieDog";
// What a lying zombie's body type hides or shows
const CRAWLER_LEGS = ["upperLeg_front", "upperLeg_back", "lowerLeg_front", "lowerLeg_back", "foot_front", "foot_back"];
// The skin parts a skin colour's label is sent to (decorateZombie F4:9000-9017)
const SKIN_PARTS = [
  "torso.skin",
  "hand_front.skin",
  "hand_back.skin",
  "upperArm_front.skin",
  "upperArm_back.skin",
  "lowerArm_front.skin",
  "lowerArm_back.skin",
  "lowerArm_backFront.skin",
  "neck.skin",
  "upperLeg_front.skin",
  "upperLeg_back.skin",
  "lowerLeg_front.skin",
  "lowerLeg_back.skin",
  "foot_front.skin",
  "foot_back.skin",
];
const SLEEVE_PARTS = ["lowerArm_front", "lowerArm_back", "upperArm_front", "upperArm_back", "lowerArm_backFront"];
const LEG_PARTS = ["lowerLeg_front", "lowerLeg_back"];
const THIGH_PARTS = ["upperLeg_front", "upperLeg_back"];
// The wounds and the pack on a fresh zombie's body start hidden (F4:8836-8842)
const HIDDEN_AT_START = ["torso.deathDamageBelly", "head.deathDamage", "torso.deathDamageChest", "torso.bisected"];
// The uniforms: what each wears. hat and hair are set only when the body type says so
const UNIFORMS = {
  police: { hat: "none", top: "police", bottom: "police", shoes: "shoeBlack" },
  unionSec: { hat: "none", top: "unionSec", bottom: "police", shoes: "shoeBlack" },
  riot: { hat: "riot", top: "riot", bottom: "riot", shoes: "shoeBlack", hair: UNIFORM_HAIR },
  riotNoHelmet: { hat: "none", top: "riot", bottom: "riot", shoes: "shoeBlack", hair: UNIFORM_HAIR },
  army: { hat: "army", top: "army", bottom: "army", shoes: "shoeArmy", hair: UNIFORM_HAIR, facial: ARMY_FACIAL_HAIR },
  armyNoHelmet: { hat: "none", top: "army", bottom: "army", shoes: "shoeArmy", hair: UNIFORM_HAIR },
  riotShield: { hat: "riot", top: "riot", bottom: "riot", shoes: "shoeBlack", hair: UNIFORM_HAIR },
};
// Body types whose clothes are picked from the lists, as everyone's are
const CIVILIAN_BODIES = new Set(["survivor", "crawler", "civilian"]);

let page = null;
let serial = 0;

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

// The converted table of a zombie type, or undefined for a name that is not one
export function zombieType(type) {
  return data.actors?.zombies?.[type];
}

// The danger of the room being played: 0 in a safe house (setMaxThreat F4:1559)
export function roomDanger() {
  return room.def?.safeHouse ? 0 : (room.def?.danger ?? 0);
}

// A zombie's health in a room of that danger: round((9 + danger) x the type's health bonus) (zombieHlth F4:8573)
export function zombieHealth(type, danger = roomDanger()) {
  return Math.round((constant("zombieBaseHealth") + danger) * (zombieType(type)?.healthBonus ?? 1));
}

// A zombie's damage: round(7 x ceil(danger / 10)) x the type's damage bonus (zombieDmg F4:8569)
export function zombieDamage(type, danger = roomDanger()) {
  return Math.round(constant("zombieBaseDamage") * Math.ceil(danger / 10)) * (zombieType(type)?.damageBonus ?? 1);
}

// ---------- Dressing ----------

function list(name) {
  return data.actors?.lists?.[name] ?? [];
}

// One member of a list, picked at random. How a zombie looks is picture only
function pickFrom(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function hide(clip, path) {
  const part = partAt(clip, path);
  if (part) {
    part.visible = false;
  }
}

// A flat colour over a part (colorTo), for a part that is there
function colour(clip, path, value) {
  paintFlat(partAt(clip, path), value);
}

// Fills in a zombie's looks from the lists: skin and hair colour, shoes, clothes, hair and beard, then the type's
// uniform over them. The result is written onto the holder as the original writes onto the clip: skinColour,
// hairColour, hair, facialHair, clothesTop, clothesBottom, clothesShoe, hat. predef keeps what the holder already has
// and fills only what it lacks (a zombie coming back into its room); special draws fresh skin and hair colours anyway
function chooseLook(holder, predef, special) {
  const sex = holder.sex;
  const hairs = list("allZombieHair");
  const facials = list("allZombieFacialHair");
  if (!predef || special || holder.skinColour === undefined) {
    holder.skinColour = pickFrom(list("allZombieSkinColours"));
    holder.hairColour = colourOf(pickFrom(list("allZombieHairColours")), 0);
  }
  if (holder.skinColour === "black1" || holder.skinColour === "white3") {
    holder.hairColour = 0;
  }
  if (!predef || holder.clothesShoe === undefined) {
    holder.clothesShoe = pickFrom(list("allZombieShoes"));
  }
  let hairIndex = Math.floor(Math.random() * hairs.length);
  let facialIndex = Math.floor(Math.random() * facials.length);
  const uniform = UNIFORMS[holder.bodyType];
  if (uniform) {
    Object.assign(holder, { hat: uniform.hat, clothesTop: uniform.top, clothesBottom: uniform.bottom });
    holder.clothesShoe = uniform.shoes;
    hairIndex = uniform.hair ?? hairIndex;
    facialIndex = uniform.facial ?? facialIndex;
  } else if (holder.clothesTop === undefined ? !predef || CIVILIAN_BODIES.has(holder.bodyType) : !predef) {
    holder.clothesTop = `${sex}_${pickFrom(list(`${sex}ZombieClothesTop`))}`;
    holder.clothesBottom = `${sex}_${pickFrom(list(`${sex}ZombieClothesBottom`))}`;
  }
  if (holder.clothesTop?.startsWith("female_dress")) {
    holder.clothesBottom = "none";
  }
  if (holder.clothesTop === "male_suitBlack") {
    holder.clothesBottom = "male_suitBlack";
  }
  if (!predef || holder.hair === undefined) {
    holder.hair = `${sex}_${hairs[hairIndex]}`;
    holder.facialHair = sex === "female" ? "none" : facials[facialIndex];
  }
}

// The head: one of its two looks, the hat, hair and beard by label, and the hair's colour (F4:8991-9006)
function dressHead(clip, holder) {
  const head = clip.child("head");
  if (!head) {
    return;
  }
  goto(head, `head${Math.floor(Math.random() * 2) + 1}`);
  if (holder.hat !== undefined) {
    goto(head.child("hat"), holder.hat);
  }
  goto(head.child("hair"), holder.hair);
  goto(head.child("facialHair"), holder.facialHair);
  goto(head.child("skin"), holder.bodyType === "fat" ? `${holder.skinColour}_fat` : holder.skinColour);
  colour(clip, "head.hair.base", holder.hairColour);
  colour(clip, "head.facialHair.base", holder.hairColour);
}

// Sleeves, torso, trousers and shoes by the clothes' labels. A fat body takes the wide torso and trousers
function dressBody(clip, holder) {
  const fat = holder.bodyType === "fat";
  for (const name of SLEEVE_PARTS) {
    goto(clip.child(name), holder.clothesTop);
  }
  goto(clip.child("torso"), fat ? `${holder.clothesTop}_fat` : holder.clothesTop);
  for (const name of THIGH_PARTS) {
    goto(clip.child(name), fat ? `${holder.clothesBottom}_fat` : holder.clothesBottom);
  }
  for (const name of LEG_PARTS) {
    goto(clip.child(name), holder.clothesBottom);
  }
  goto(clip.child("foot_front"), holder.clothesShoe);
  goto(clip.child("foot_back"), holder.clothesShoe);
  for (const path of SKIN_PARTS) {
    goto(partAt(clip, path), holder.skinColour);
  }
}

// A crawler is a torso: the legs are gone and the torso shows its torn end
function bisect(clip) {
  for (const name of CRAWLER_LEGS) {
    const part = clip.child(name);
    if (part) {
      part.visible = false;
    }
  }
  const torn = partAt(clip, "torso.bisected");
  if (torn) {
    torn.visible = true;
  }
}

// Dresses a zombie (or a dead body: any holder with a clip, a sex and a body type) as decorateZombie does. predef keeps
// the looks the holder already has (a zombie coming back into its room); special draws fresh skin and hair colours
// anyway (a body the room places). A dog has none of the parts, so it is left as drawn
export function decorateZombie(holder, { predef = false, special = false } = {}) {
  const clip = holder.clip;
  if (!clip || clip.destroyed || holder.bodyType === "dog") {
    return;
  }
  clip.visible = false;
  HIDDEN_AT_START.forEach((path) => hide(clip, path));
  hide(clip, "torso.backpack");
  chooseLook(holder, predef, special);
  if (holder.bodyType === "crawler") {
    bisect(clip);
  }
  if (holder.dropper === true) {
    const pack = partAt(clip, "torso.backpack");
    if (pack) {
      pack.visible = true;
    }
  }
  dressHead(clip, holder);
  dressBody(clip, holder);
  goto(partAt(clip, "hand_front.weapon.weapons"), holder.currentWeapon ?? "hands");
  clip.visible = true;
}

// ---------- Setup ----------

// Where a zombie with no place given stands: off to one side of where the player came in, at least the spawn buffer
// away, inside the room's edges (setupZombie F4:8613-8666). The last test that fits decides, as in the original
export function spawnPlace() {
  const edge = constant("moveEdgeBuffer");
  const buffer = constant("zombSpawnBuffer");
  const start = room.arrivalX;
  const left = [edge, start - buffer];
  const right = [start + buffer, room.width - edge];
  let side = rng.random(2) === 0 ? left : right;
  if (start >= room.width - edge) {
    side = left;
  }
  if (start <= edge || start <= buffer) {
    side = right;
  }
  if (start >= room.width - buffer) {
    side = left;
  }
  return rng.range(Math.min(...side), Math.max(...side));
}

// A zombie put down over a block stands on its top and falls to it (spawnCollisionBlocks F4:6904)
function spawnOnBlock(zombie) {
  for (const block of roomBlocks()) {
    if (Math.abs(zombie.x - block.x) <= block.box.w / 2) {
      zombie.collideSpawn = true;
      zombie.lastCollision = block.name;
      if (zombie.falling !== true) {
        zombie.y = block.y - block.box.h;
      }
      zombie.jumping = true;
      zombie.falling = true;
    }
  }
}

// What a zombie starts with besides its type's numbers: not awake, not moving, not hurt (setupZombie F4:8700-8760)
function restingFlags() {
  return {
    dir: "none",
    closeHum: FAR,
    target: null,
    vy: 0,
    jumpHeight: -10,
    alive: true,
    rising: false,
    alerted: false,
    dropper: false,
    dropZombie: false,
    attackCount: 0,
    attacking: false,
    grabbing: false,
    climbing: false,
    jumping: false,
    falling: false,
    crouched: false,
    stumbling: false,
    stumbleMoving: false,
    animIdle: false,
    animWalk: false,
    animSprint: false,
    collideLeft: false,
    collideRight: false,
    collideSpawn: false,
  };
}

// The numbers a type gives its zombies, under the names the rules read (F4:8727-8760)
function typeFields(def) {
  return {
    state: def.startState,
    startPos: def.startPos,
    currentWeapon: def.weapon ?? "hands",
    threat: def.threat,
    xpBonus: def.xpBonus,
    armorChest: def.armorChest,
    armorHead: def.armorHead,
    armour: { Chest: def.armorChest, Head: def.armorHead },
    chaseSpeed: def.chaseSpeed,
    wanderSpeed: WANDER_SPEED,
    attackRange: def.attackRange ?? ATTACK_RANGE_BASE + rng.random(ATTACK_RANGE_SPREAD),
    grabRange: constant("zombieGrabRange"),
    sight: SIGHT_RANGE,
    sense: SENSE_RANGE,
    alertChance: def.alertChance,
    canGrab: def.canGrab,
    canStumble: def.canStumble,
    laying: def.lying === true,
  };
}

// The actor for a zombie of a type, before its art
function makeZombie(type, def, danger) {
  serial += 1;
  const sex = def.riot === true || rng.random(constant("zombieFemaleChance")) !== 0 ? "male" : "female";
  const size = constant("zombieScale") + (rng.random(SCALE_SPREAD) - SCALE_OFFSET);
  const health = zombieHealth(type, danger);
  return {
    kind: "zombie",
    zombie: true,
    side: "zombie",
    name: `zombie${serial}`,
    serial,
    type,
    def,
    sex,
    bodyType: def.bodyType,
    danger,
    scale: size - (sex === "female" ? FEMALE_SCALE_DROP : 0),
    health,
    healthMax: health,
    lastHealth: health,
    damage: zombieDamage(type, danger),
    dirChangeCount: rng.random(constant("dirChangeMax")),
    ...typeFields(def),
    ...restingFlags(),
  };
}

// The art of a zombie: the clip, its size and way round, and its place among the room's actors. Zombies sit behind the
// player and everyone placed after (the original's depth 12800 and up against 115000), so their depth is counted from
// the player's
function attachClip(zombie) {
  const clip = page.lib.makeExported(zombie.type === "zombieDog" ? DOG_EXPORT : ZOMBIE_EXPORT);
  clip.owner = zombie;
  zombie.clip = clip;
  clip.zIndex = constant("depth_world_zombies") - constant("depth_world_player") + (zombie.serial % DEPTH_SLOTS);
  layers.actors.addChild(clip);
  placeClip(zombie);
  return clip;
}

// Which way a zombie faces: 1 right, -1 left. The size stays the same on both axes
export function faceZombie(zombie, dir) {
  zombie.facing = dir < 0 ? -1 : 1;
  const size = zombie.scale / 100;
  zombie.clip.scale.set(zombie.facing * size, size);
}

function placeClip(zombie) {
  if (zombie.clip && !zombie.clip.destroyed) {
    zombie.clip.x = zombie.x;
    zombie.clip.y = zombie.y;
  }
}

// A zombie of a type in the room, dressed and in its start pose. x is where it stands (a place off to one side of the
// player when left out). Options: facing (1 or -1; random), state (the type's own), alerted (it starts awake), dropper
// (true or false decides whether it carries a backpack, if its type can; left out, the game's timer decides, as it does
// for every zombie made), fromRoof (it starts falling from the top of the room and wakes as it lands). Returns the
// zombie actor, or null for a type that does not exist
export function spawnZombie(type, x, { facing, state, alerted = false, dropper, fromRoof = false } = {}) {
  const def = zombieType(type);
  if (!def) {
    console.warn(`Union City: no zombie type called ${type}`);
    return null;
  }
  const zombie = makeZombie(type, def, roomDanger());
  zombie.x = x ?? spawnPlace();
  zombie.floor = room.floorY - (rng.random(FLOOR_JITTER) - FLOOR_JITTER_OFFSET);
  zombie.y = zombie.floor;
  zombie.dropper = (dropper ?? rollDropper()) === true && def.dropperAllowed === true;
  if (state !== undefined) {
    zombie.state = state;
  }
  attachClip(zombie);
  faceZombie(zombie, facing ?? (rng.random(2) === 0 ? -1 : 1));
  if (fromRoof) {
    Object.assign(zombie, { y: room.markers.bounds?.y ?? 0, jumping: true, falling: true, dropZombie: true });
    zombie.target = world.player ?? null;
  }
  spawnOnBlock(zombie);
  decorateZombie(zombie);
  startPose(zombie);
  zombie.charHeight = zombie.clip.height;
  placeClip(zombie);
  world.zombies.push(zombie);
  if (alerted && !fromRoof) {
    wakeAtSpawn(zombie);
  }
  return zombie;
}

// The pose a zombie starts in: one that lies stays lying until it is woken, the rest play their idle
function startPose(zombie) {
  if (zombie.laying) {
    goto(zombie.clip, zombie.startPos);
  } else {
    gotoPlay(zombie.clip, zombie.startPos);
  }
}

// A zombie that starts awake wakes as one that was seen (alertedZombie "seen" F4:9096): a riser rises (its rise ends in
// the chase), the rest chase. One dropped from the roof is not woken here: a falling zombie can't be, and it wakes as
// it lands
function wakeAtSpawn(zombie) {
  zombie.laying = false;
  wakeZombie(zombie);
}

// ---------- Voices ----------

function pickName(prefix, count) {
  return `${prefix}${Math.floor(Math.random() * count) + 1}`;
}

// The name of the sound a zombie makes for a kind ("idle", "alert", "attack", "struggle", "death", "voice"), or null
// for none. A dog has only the dog's sounds; people's voices are by sex
function soundNameFor(zombie, kind) {
  if (zombie.type === "zombieDog") {
    if (kind === "attack") {
      return pickName("sound_zombieAttack_dog", 2);
    }
    if (kind === "struggle") {
      return null;
    }
    return kind === "death" ? "sound_zombieDeath_dog" : DOG_VOICE;
  }
  const sex = zombie.sex;
  switch (kind) {
    case "idle":
      return pickName(`sound_zombieIdle_${sex}`, 3);
    case "alert":
      return pickName(`sound_zombieAlert_${sex}`, 3);
    case "attack":
      return pickName(`sound_zombieAttack_${sex}`, 3);
    case "struggle":
      return pickName(`sound_zombieStruggle_${sex}`, 3);
    case "death":
      return sex === "male" ? pickName("sound_zombieDead_", 5) : pickName("sound_zombieDeath_female", 4);
    default:
      return pickName("sound_zombie_", 2);
  }
}

// Whether the roll the original makes before this sound lets it through: an attack groans 86 times in 100 and a death
// is silent one time in 20 (playZombieAttackSound F4:5302, playZombieDeadSound F4:5502). Every other sound is made
function allowed(zombie, kind) {
  if (kind === "attack") {
    return rng.random(100) <= constant("zomAttackSoundChance");
  }
  if (kind === "death" && zombie.type !== "zombieDog") {
    return rng.random(constant("zomChancePlayNoDeathSound")) > 0;
  }
  return true;
}

// A zombie makes a sound at its place. Returns the name played, or null
export function zombieSound(zombie, kind) {
  const name = allowed(zombie, kind) ? soundNameFor(zombie, kind) : null;
  if (name) {
    sound.play(name, { x: zombie.x });
  }
  return name;
}

// ---------- Targets and waking ----------

// A living zombie made by spawnZombie, with its type's table and its art. A bare stand-in body has no rules
function hasAI(zombie) {
  return zombie?.side === "zombie" && Boolean(zombie.def) && zombie.alive === true && !zombie.clip?.destroyed;
}

// What each kind of alert adds to a zombie's alert chance, out of 500 (alertedZombie F4:9106-9124)
const ALERT_BONUS = { meleeHit: 300, gunshotHit: 300, gunshotNear: 20, sensed: 100, sighted: 300 };
const CRAWLER = "zombieCrawl";
const RISER = "zombieRiser";
// A weapon's noise adds this much to the roll for each point (alertedZombie F4:9104)
const NOISE_FACTOR = 15;
// Kills of unaware enemies by the player, and who hears of each
let unawareKills = 0;
const unawareListeners = [];
// The states of a zombie that is after someone; one that loses its target in these goes back to wandering
const AWAKE_STATES = new Set(["chase", "climb", "attack", "grab"]);

// Everyone a zombie could go after or hit: the player, companions and the other humans
function nonZombies() {
  const all = [...world.companions, ...world.humans];
  if (world.player) {
    all.unshift(world.player);
  }
  return all;
}

// Whether a zombie may pick someone: living, not a zombie, not down, not the partner, and not a companion while the
// director's ending rush on Union Island is on (world.endingRush, F4:1460)
function huntable(each) {
  if (each.alive !== true || each.side === "zombie" || each.zombie === true) {
    return false;
  }
  if (each.down === true || each.partner === true) {
    return false;
  }
  return !(world.endingRush === true && each.companion === true);
}

// A zombie picks the nearest one it may go after, by the distance across the floor now (findZombieTarget F4:9036).
// Nobody there leaves it without a target
export function findZombieTarget(zombie) {
  let best = null;
  let bestDist = FAR;
  for (const each of nonZombies()) {
    const dist = Math.abs(zombie.x - each.x);
    if (huntable(each) && dist < bestDist) {
      best = each;
      bestDist = dist;
    }
  }
  zombie.target = best;
  zombie.closeHum = bestDist;
  return best;
}

// A zombie wakes (the success of alertedZombie F4:9132-9154): a crawler gets up off the floor to crawl, a riser that
// is lying starts its rise (the rise's end sets it chasing), and the rest pick a target and chase it, with an alert
// groan one time in five
export function wakeZombie(zombie) {
  if (zombie.type === CRAWLER) {
    zombie.laying = false;
  }
  if (zombie.type === RISER && zombie.rising !== true && zombie.dropZombie !== true) {
    zombie.rising = true;
    zombie.laying = false;
    gotoPlay(zombie.clip, "rise");
  }
  if (zombie.rising === true) {
    return;
  }
  zombie.alerted = true;
  zombie.animWalk = false;
  findZombieTarget(zombie);
  zombie.state = "chase";
  if (rng.random(constant("zomAlertSoundChance")) === 0) {
    zombieSound(zombie, "alert");
  }
}

// An unalerted zombie that is not falling rolls to wake (alertedZombie F4:9096): its alert chance plus bonus out of
// 500, never while stumbling or attacking; reason "seen" always wakes it. Only zombies are woken. Returns true when it
// woke
export function alertZombie(zombie, bonus = 0, reason = "") {
  if (!hasAI(zombie) || zombie.alerted === true || zombie.falling === true) {
    return false;
  }
  const roll = rng.random(constant("alertRandRange"));
  const busy = zombie.state === "stumble" || zombie.state === "attack";
  if (reason !== "seen" && (roll >= zombie.alertChance + bonus || busy)) {
    return false;
  }
  wakeZombie(zombie);
  return true;
}

// A hit (a round, a swing, a shove, a grenade's bump) rolls to wake the zombie it struck
function alertOnHit(target, attacker, condition) {
  alertZombie(target, ALERT_BONUS[condition] ?? 0, condition);
}

// A gunshot's noise reaches every unalerted zombie in the room: the roll adds the weapon's noise x 15 (F4:9101-9105,
// 21309-21317), so a shotgun wakes them all and a pistol about a third
function alertOnNoise(target, shooter, condition, noise) {
  alertZombie(target, noise * NOISE_FACTOR, condition ?? "noise");
}

// Whether the player is within range px of a zombie across the floor, on either side but not on the same spot
function within(zombie, range) {
  const dx = zombie.x - player.x;
  return dx !== 0 && Math.abs(dx) < range;
}

// The once-a-second check (checkZombieMovementAlerts F4:9069): each unalerted zombie rolls for sensing the player
// within its sense range, then again for seeing them when it faces them within its sight. Sight is cut by the light
// and goes further with the flashlight on. Sneaking changes nothing
export function checkZombieMovementAlerts() {
  if (world.player !== player || player.alive !== true) {
    return;
  }
  const lit = light.sightMod() * light.sightBonus();
  for (const zombie of [...world.zombies]) {
    if (!hasAI(zombie) || zombie.alerted !== false) {
      continue;
    }
    if (within(zombie, zombie.sense)) {
      alertZombie(zombie, ALERT_BONUS.sensed, "sensed");
    }
    const facesPlayer = zombie.x > player.x ? zombie.facing < 0 : zombie.facing > 0;
    if (zombie.alerted === false && within(zombie, zombie.sight * lit) && facesPlayer) {
      alertZombie(zombie, ALERT_BONUS.sighted, "sighted");
    }
  }
}

// Registers fn(target) for each enemy the player kills while it is unaware of them ("Without a Sound")
export function onUnawareKill(fn) {
  unawareListeners.push(fn);
}

// A kill by the player's round or swing of an enemy that never woke counts as unaware (F4:5754, 6447). Blasts do not
function countUnaware({ target, owner, blast }) {
  if (owner !== player || blast === true || target === player || target.alerted === true) {
    return;
  }
  unawareKills += 1;
  for (const fn of unawareListeners) {
    fn(target);
  }
}

// A rise's last frame (S6800 frame 267): the riser goes after the player (alertRisingZombie F4:9160)
function alertRisingZombie({ owner }) {
  if (!hasAI(owner)) {
    return;
  }
  Object.assign(owner, { alerted: true, animWalk: false, target: world.player ?? null, state: "chase" });
  if (rng.random(constant("zomAlertSoundChance")) === 0) {
    zombieSound(owner, "alert");
  }
}

// Whether a zombie's target is still there to go after: alive and still in the room
function targetHere(zombie) {
  const target = zombie.target;
  return Boolean(target) && target.alive === true && !target.clip?.destroyed;
}

// A zombie whose target died or went away forgets it and wanders, no longer alerted, so it can be woken again. A
// zombie that never woke keeps its state, so the lying and the idle stay as they are (F4:9179)
function dropLostTarget(zombie) {
  if (!AWAKE_STATES.has(zombie.state) || targetHere(zombie)) {
    return;
  }
  Object.assign(zombie, { target: null, alerted: false, attacking: false, grabbing: false, animWalk: false });
  zombie.state = "wander";
}

// ---------- Moving ----------

// The art each type plays for a walk, a climb, a stand and an attack where it differs from the rest
const WANDER_WALK = { zombieCrawl: "crawl", zombieRiotShield: "walkShield" };
const STAND_POSE = { zombieRiotShield: "idleShield" };
const CLIMB_ANIM = { zombieRiotShield: "climbShield", zombieCrawl: "climbCrawl" };
const OWN_ATTACK = { zombieCrawl: "crawlerAttack", zombieRiotShield: "attackShield" };
const DIRECTIONS = ["left", "right", "none"];
// The longest climb, in frames: a climb whose clip has left it was cut short (a stumble took its art)
const CLIMB_LONGEST = 25;
// A riot-shield zombie rolls for a pause once a second while chasing
const PAUSE_ROLL_EVERY = 30;

// One step toward dir at speed, unless something blocks that side; a blocked side stops it and its walk timer runs
// out (F4:9294-9330, 9424-9490). walk is the art it starts when it sets off
function stepToward(zombie, dir, speed, walk) {
  const left = dir === "left";
  if (left ? zombie.collideLeft : zombie.collideRight) {
    zombie.dirChangeCount = 0;
    zombie.dir = "none";
    return;
  }
  if (left) {
    zombie.collideRight = false;
  } else {
    zombie.collideLeft = false;
  }
  faceZombie(zombie, left ? -1 : 1);
  zombie.x += left ? -speed : speed;
  zombie.animIdle = false;
  if (zombie.animWalk === false) {
    zombie.animWalk = true;
    gotoPlay(zombie.clip, walk);
  }
}

// Standing still in wander: a crawler lies still in its crawl pose, the shield zombie holds its shield up
function standStill(zombie) {
  if (zombie.animIdle !== false) {
    return;
  }
  if (zombie.type === CRAWLER) {
    goto(zombie.clip, "crawl");
  } else {
    gotoPlay(zombie.clip, STAND_POSE[zombie.type] ?? "idle");
  }
  zombie.animIdle = true;
  zombie.animWalk = false;
}

// Wander (F4:9407-9505): a groan one time in 200, a new way (left, right or stand) one time in 100 once the walk timer
// has run out, and the room's edges count as a block to turn at
function wander(zombie) {
  if (rng.random(constant("zombieIdleSoundChance")) === 0) {
    zombieSound(zombie, "idle");
  }
  zombie.dirChangeCount -= 1;
  if (rng.random(constant("dirChangeChance")) === 0 && zombie.dirChangeCount < 0) {
    zombie.dir = DIRECTIONS[rng.random(DIRECTIONS.length)];
    zombie.dirChangeCount = constant("dirChangeMax");
  }
  const edge = constant("moveEdgeBuffer");
  if (zombie.x < room.edges.left + edge) {
    zombie.collideLeft = true;
  }
  if (zombie.x > room.edges.right - edge) {
    zombie.collideRight = true;
  }
  if (zombie.dir === "none") {
    standStill(zombie);
  } else if (zombie.dir === "left" || zombie.dir === "right") {
    stepToward(zombie, zombie.dir, zombie.wanderSpeed, WANDER_WALK[zombie.type] ?? "walk");
  }
}

// A riot-shield zombie on the chase rolls once a second: 30 times in 100 it drops back behind its shield for 3 s,
// wandering unalerted until something wakes it again (F4:9278-9284, 9196-9201)
function shieldPause(zombie) {
  if (zombie.type !== SHIELD_TYPE) {
    return;
  }
  zombie.pauseRoll = (zombie.pauseRoll ?? PAUSE_ROLL_EVERY) - 1;
  if (zombie.pauseRoll > 0) {
    return;
  }
  zombie.pauseRoll = PAUSE_ROLL_EVERY;
  if (rng.random(1000) < constant("zombieRiotPause") && !(zombie.pausing > 0)) {
    zombie.pausing = constant("zombieRiotPauseLength");
  }
}

// In reach, a zombie mostly attacks. One time in ten it tries a grab instead, when its target is the player, standing
// on the ground and not held already, within 40 px up or down, and its type can grab (F4:9332-9346)
function closeIn(zombie) {
  const target = zombie.target;
  const free = target.grabbed !== true && target.falling !== true && target.jumping !== true;
  const grabs = rng.random(1000) < constant("zombieGrabChance") && free;
  const near = Math.abs(zombie.y - target.y) < constant("grabYRange");
  zombie.state = grabs && zombie.canGrab === true && near && target === world.player ? "grab" : "attack";
}

// Chase (F4:9262-9349): a groan one time in 90, the way to its target, the shield's pause, a climb at a block it has
// run into, a step at its chase speed, and an attack or a grab once in reach
function chase(zombie) {
  if (rng.random(constant("zomChaseSoundChance")) === 0) {
    zombieSound(zombie, "alert");
  }
  Object.assign(zombie, { grabbing: false, attacking: false, restNext: false });
  const target = zombie.target;
  if (target.x !== zombie.x) {
    zombie.dir = target.x > zombie.x ? "right" : "left";
  }
  shieldPause(zombie);
  if (startsClimb(zombie)) {
    return;
  }
  if (zombie.dir !== "none") {
    stepToward(zombie, zombie.dir, zombie.chaseSpeed, zombie.def.walkAnim);
  }
  if (Math.abs(target.x - zombie.x) <= zombie.attackRange) {
    closeIn(zombie);
  }
}

// ---------- Climbing ----------

function blockNamed(name) {
  return roomBlocks().find((each) => each.name === name) ?? null;
}

// A chasing zombie held up by the block it last touched tries to climb it. True when it started a climb
function startsClimb(zombie) {
  const blocked = zombie.collideLeft || zombie.collideRight;
  if (!blocked || !zombie.lastCollision || zombie.climbing) {
    return false;
  }
  climbBlock(zombie);
  return zombie.state === "climb";
}

// A zombie up against a block climbs it when it is at most 180 px tall (climbBlock F4:15737); a taller one just stops
// it. The climb's art ends on the endclimb hook, which puts it on top
export function climbBlock(zombie) {
  const block = blockNamed(zombie.lastCollision);
  if (zombie.climbing || !(block?.box.h > 0) || block.box.h > constant("highClimbHeight")) {
    return;
  }
  zombie.animWalk = false;
  zombie.currClimbHeight = block.box.h;
  zombie.climbing = true;
  const anim = CLIMB_ANIM[zombie.type] ?? "climb";
  zombie.climbFrame = frameFor(zombie.clip, anim);
  gotoPlay(zombie.clip, anim);
  zombie.state = "climb";
}

// The climb's end (endClimb F4:15786): the zombie stands (a crawler crawls on) 40 px further on and the block's height
// less 15 px higher, free of the block, and goes on with the chase
export function endClimb(zombie) {
  if (zombie.type === CRAWLER) {
    gotoPlay(zombie.clip, "crawl");
  } else {
    goto(zombie.clip, "stand");
  }
  zombie.x += zombie.facing < 0 ? -constant("climbXShift") : constant("climbXShift");
  zombie.y -= (zombie.currClimbHeight ?? 0) - constant("climbBuffer");
  Object.assign(zombie, { climbing: false, collideLeft: false, collideRight: false, animWalk: false });
  if (zombie.state === "climb") {
    zombie.state = "chase";
  }
}

// While the climb plays the zombie does nothing else. A climb cut short (a stumble took over its art) goes back to
// the chase
function climb(zombie) {
  const frame = zombie.clip.frame;
  if (zombie.climbing && frame >= zombie.climbFrame && frame <= zombie.climbFrame + CLIMB_LONGEST) {
    return;
  }
  zombie.climbing = false;
  zombie.state = "chase";
}

// ---------- Attacks and grabs ----------

// The blow a zombie swings: the crawler's and the shield zombie's own, attack3 at a target that is down, otherwise
// attack1 or attack2 (F4:9391-9403)
function attackAnim(zombie) {
  const own = OWN_ATTACK[zombie.type];
  const pick = own ?? `attack${rng.random(constant("numZombieAttacks")) + 1}`;
  return zombie.target?.down === true && zombie.type !== CRAWLER ? "attack3" : pick;
}

// Attack (F4:9372-9405): once a blow's art has ended the zombie swings again while its target stays in reach, and
// chases it once it is out of reach. The original's loop ran before the clip's own frame script, so it saw a blow's
// end one step after the art marked it: the zombie rests that one step, and attack1 comes round every 38 frames
function attack(zombie) {
  if (zombie.attacking) {
    zombie.restNext = true;
    return;
  }
  if (zombie.restNext) {
    zombie.restNext = false;
    return;
  }
  if (Math.abs(zombie.target.x - zombie.x) > zombie.attackRange && zombie.attackCount > 0) {
    Object.assign(zombie, { attackCount: 0, animWalk: false });
    zombie.state = "chase";
    return;
  }
  zombieSound(zombie, "attack");
  zombie.attackCount += 1;
  zombie.attacking = true;
  zombie.animWalk = false;
  zombie.attackAnim = attackAnim(zombie);
  gotoPlay(zombie.clip, zombie.attackAnim);
}

// Grab (F4:9351-9370): a target that moved out of grab reach is chased again; otherwise the zombie plays its grab,
// whose frame 622 checks whether it caught the player
function grab(zombie) {
  const target = zombie.target;
  const free = target.grabbed !== true && target.falling !== true && target.jumping !== true;
  if (Math.abs(target.x - zombie.x) > zombie.grabRange && zombie.grabbing === false && free) {
    Object.assign(zombie, { attacking: false, animWalk: false });
    zombie.state = "chase";
  }
  if (zombie.grabbing !== false || !free || target !== world.player) {
    return;
  }
  if (zombie.canGrab !== true) {
    zombie.state = "attack";
    return;
  }
  zombie.grabbing = true;
  zombie.animWalk = false;
  gotoPlay(zombie.clip, "grab");
}

// A blow lands on the step its clip shows the attack box: everyone not a zombie within 90 px across the floor takes
// it, after the zombie's miss roll, as a swing at the chest (meleeCollisions F4:6560-6598)
function landBlows(zombie) {
  if (!partAt(zombie.clip, "attackCollision")) {
    return;
  }
  const reach = Math.min(constant("meleeCollCheckBuffer"), constant("zomMeleeHitRange"));
  for (const target of nonZombies()) {
    if (target.alive !== true || !target.clip || target.clip.destroyed || Math.abs(zombie.x - target.x) >= reach) {
      continue;
    }
    if (checkMiss(zombie, target, "zombie")) {
      missText(target);
      continue;
    }
    damageMelee(zombie, target, "swing", "Chest");
    effects.bloodPack(target, "Chest", zombie);
    const chest = boxOf(target.clip, "collisionChest");
    if (chest) {
      effects.blood(chest.x + chest.w / 2, chest.y + chest.h / 2, target.x >= zombie.x ? 1 : -1, 1);
    }
  }
}

function zombieBlows() {
  for (const zombie of [...world.zombies]) {
    if (hasAI(zombie) && zombie.clip) {
      landBlows(zombie);
    }
  }
}

// ---------- Grabs and the struggle ----------

// The struggle prompt's art ("struggleHud"), and how far above the player's head it sits
const STRUGGLE_HUD = 5580;
const PROMPT_ABOVE = 30;
// The shove out of a struggle knocks the zombie back as a hit of 50 would: 30 + 50 = 80 px (endStruggle F4:15958)
const STRUGGLE_SHOVE = 50;
// The prompt's ring starts at 1% and grows to 25% more than the share of presses made (F4:15901, 15954)
const RING_START = 0.01;
const RING_EXTRA = 25;
// The keys that count toward a struggle, by the side the zombie holds from. Keys are read by their place, so an
// AZERTY keyboard's Q is KeyA
const STRUGGLE_KEYS = { left: ["KeyA", "ArrowLeft"], right: ["KeyD", "ArrowRight"] };

// The struggle under way: the zombie holding the player (null when there is none), the presses made and needed, the
// side it holds from ("left" or "right") and the prompt's clip
export const struggle = { zombie: null, count: 0, needed: 0, side: null, hud: null };
let hudReady = false;

// Presses needed to break free: round(level x 2 - Strength x 2), 3 to 8 (F4:15881-15890). Strength carries the
// hunger penalty
function pressesNeeded() {
  const strength = story.player ? attributeOf(player, "strength") : 0;
  const needed = Math.round(player.level * constant("struggleCountMultiplier") - strength * 2);
  return Math.min(constant("struggleMax"), Math.max(constant("struggleMin"), needed));
}

function removePrompt() {
  if (struggle.hud && !struggle.hud.destroyed) {
    struggle.hud.destroy({ children: true });
  }
  struggle.hud = null;
}

// The prompt over the player's head: the key to press in the pulsing box and the ring that fills (F4:15891-15918)
function showPrompt(key) {
  removePrompt();
  if (!hudReady) {
    return;
  }
  const hud = page.lib.make(STRUGGLE_HUD);
  hud.label = "struggleHud";
  hud.eventMode = "none";
  hud.x = player.x;
  hud.y = player.y - ((player.clip?.height ?? 0) + PROMPT_ABOVE);
  hud.child("fill")?.scale.set(RING_START);
  const field = partAt(hud, "anim.txt");
  if (field) {
    field.text = key;
  }
  layers.effects.addChild(hud);
  struggle.hud = hud;
}

// The zombie snaps 65 px in front of the player, who turns to face it; the prompt asks for A (Q with the AZERTY
// setting) when it holds from the left, D from the right (F4:15903-15928)
function placeGrab(zombie) {
  const fromLeft = player.x > zombie.x;
  struggle.side = fromLeft ? "left" : "right";
  face(fromLeft ? -1 : 1);
  zombie.y = player.y;
  zombie.x = player.x + (fromLeft ? -constant("zombieGrabRange") : constant("zombieGrabRange"));
  const leftKey = story.settings?.azerty ? "Q" : "A";
  showPrompt(fromLeft ? leftKey : "D");
}

// The player's body gives up what it was doing and plays the struggle in one full-body pose (F4:15929-15942)
function playerStruggles(zombie) {
  const arm = partAt(player.clip, "arms.lowerArm_backFront");
  if (arm) {
    arm.visible = false;
  }
  player.rig?.setAnimMode("full");
  gotoPlay(player.clip, "struggle");
  player.grabber = zombie;
  zombie.grabbed = true;
  Object.assign(player, { firing: false, firingAnim: false, meleeSwing: false, walkAnim: false });
  Object.assign(player, { reloading: false, shoving: false });
}

// A struggle starts (startStruggle F4:15872). A zombie that died in the meantime ends it at once
export function startStruggle(zombie) {
  if (zombie.alive !== true) {
    endStruggle(true);
    return;
  }
  Object.assign(struggle, { zombie, count: 0, needed: pressesNeeded() });
  player.struggling = true;
  placeGrab(zombie);
  playerStruggles(zombie);
}

// The grab frame of the zombie's grab (S6800 frame 622, checkForGrab F4:15849): the player within its attack range
// and not shoving, jumping, falling or held already is grabbed, and their controls lock. Otherwise a player in reach
// gets an attack and one out of reach a chase
function checkForGrab({ owner: zombie }) {
  if (!hasAI(zombie) || !zombie.target) {
    return;
  }
  const target = zombie.target;
  if (Math.abs(target.x - zombie.x) >= zombie.attackRange) {
    zombie.state = "chase";
    return;
  }
  const free = !target.grabbed && !target.shoving && !target.jumping && !target.falling;
  if (!free || target !== player || player.alive !== true) {
    zombie.state = "attack";
    return;
  }
  player.grabbed = true;
  player.controlsLocked = true;
  startStruggle(zombie);
}

// The struggle ends (endStruggle F4:15961). While the player lives (or when forced, as when the zombie died) the
// hold breaks, the player stands from a crouch and shoves the zombie back 80 px; the prompt always goes. The shove's
// art gives the controls back as it ends (S4925 frame 203)
export function endStruggle(forced = false) {
  const zombie = player.grabber ?? struggle.zombie;
  if (player.alive === true || forced) {
    Object.assign(player, { struggleAnim: false, struggling: false, grabbed: false });
    if (zombie) {
      Object.assign(zombie, { grabbing: false, struggling: false, grabbed: false });
    }
    if (player.crouched === true) {
      releaseCrouch();
    }
    player.shoving = true;
    if (zombie) {
      stumble(zombie, STRUGGLE_SHOVE, { from: player.x });
    }
    player.grabber = null;
    gotoPlay(player.clip, "struggleShove");
  }
  struggle.zombie = null;
  removePrompt();
}

// One press toward breaking free (struggle F4:15944): a grunt nearly every time, a press counted and the ring grown,
// and free at the count. A zombie that died meanwhile lets go at once
function strugglePress() {
  if (player.grabber?.alive !== true) {
    endStruggle(true);
    return;
  }
  if (rng.random(101) < constant("struggleSoundChance")) {
    sound.play(`sound_struggle${rng.random(4) + 1}`);
  }
  struggle.count += 1;
  const fill = struggle.hud?.child("fill");
  if (fill) {
    fill.scale.set((Math.round((struggle.count / struggle.needed) * 100) + RING_EXTRA) / 100);
  }
  if (struggle.count >= struggle.needed) {
    endStruggle();
  }
}

// The keys of a struggle, read each step (playerControls F4:12249-12254, struggleControls F4:15821): a held player
// whose zombie died is let go; each new press of the key toward the zombie (or its arrow), of Space, or of the touch
// struggle button counts once. Space counts although the controls are locked
function struggleControls() {
  if (world.player !== player) {
    return;
  }
  if (player.grabbed === true && player.grabber?.alive !== true) {
    endStruggle();
  }
  if (player.struggling !== true) {
    return;
  }
  const keys = STRUGGLE_KEYS[struggle.side] ?? [];
  const presses = [keys.some((code) => input.keys.pressed(code)), input.shovePressed, input.struggleTap === true];
  for (const pressed of presses) {
    if (pressed && player.struggling === true) {
      strugglePress();
    }
  }
}

// Once a second the zombie holding the player bites, for half its damage, with its struggle groan and blood
// (struggleDamage F4:15930; the half is in the damage sum)
function struggleDamage() {
  const zombie = player.grabber;
  if (player.struggling !== true || !zombie || world.player !== player) {
    return;
  }
  zombieSound(zombie, "struggle");
  damageMelee(zombie, player, "swing", "Chest");
  effects.bounce("blood", player, { type: "Chest" });
}

// A dead player's prompt goes; the hold stays as it was, as the original's death screen leaves it (F4:19890)
function playerDied() {
  if (struggle.zombie || struggle.hud) {
    endStruggle();
  }
}

// ---------- Deaths ----------

// The wound a zone shows on a body that died of it, and the body parts a big hit tears off (F4:5766-5830)
const WOUNDS = { Head: "head.deathDamage", Chest: "torso.deathDamageChest", Belly: "torso.deathDamageBelly" };
const EXPLODE_PARTS = [
  "neck.damage",
  "head.damage",
  "upperArm_front.damage",
  "torso.deathDamageBelly",
  "torso.deathDamageChest",
  "torso.bisected",
];
// The counter the shell of the killing gun adds to (F4:5712-5731)
const SHELL_COUNTERS = { pistol: "killPistol", smg: "killSMG", assaultRifle: "killAssaultRifle" };
const DOG = "zombieDog";

const countListeners = [];
const killListeners = [];
const tally = {};
// Bodies still falling to the floor after a kill in the air
let fallingBodies = [];
// Bodies whose death may still be playing. Once it has played out, a body is one still picture until it fades
let restlessBodies = [];

// Registers fn(key, amount) for each counter a zombie's death adds to. The keys are the names the original's checkAch
// takes: killZombie, killMelee, killPistol, killSMG, killAssaultRifle, killJumping, legKill, headKill, headKillCrit,
// killRiser, explodeEnemy and escapeFullRoom. Kills of unaware enemies come from onUnawareKill
export function onZombieCount(fn) {
  countListeners.push(fn);
}

// Registers fn({ zombie, cause, counters }) for each zombie that dies, whoever killed it: what the quest engine and the
// director read. counters lists the counter keys the player earned from it
export function onZombieKill(fn) {
  killListeners.push(fn);
}

function count(key, amount = 1) {
  tally[key] = (tally[key] ?? 0) + amount;
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function lowViolence() {
  return story.settings?.lowViolence === true;
}

function show(clip, path, on = true) {
  const part = partAt(clip, path);
  if (part) {
    part.visible = on;
  }
}

// A random one of a kind of death, 1 to count. Which one plays is picture only
function variant(name) {
  return Math.floor(Math.random() * constant(name)) + 1;
}

// A hit that tears the body: a critical hit, or one over the damage threshold
function bigHit(cause) {
  return cause.crit === true || cause.damage > constant("damageThreshold");
}

// The counter keys a kill earns the player (F4:5703-5738, 6428-6454, 7042-7060). The player's own kills only; each
// weapon class adds its own
function killCounters(cause) {
  if (cause.by !== player) {
    return [];
  }
  const names = ["killZombie"];
  if (cause.melee) {
    names.push("killMelee");
  } else if (cause.blast) {
    names.push("explodeEnemy");
  } else {
    names.push(SHELL_COUNTERS[cause.shell] ?? "");
    if (cause.zone === "Legs") {
      names.push("legKill");
    } else if (cause.zone === "Head") {
      names.push("headKill", bigHit(cause) ? "headKillCrit" : "");
    }
  }
  if (cause.airborne) {
    names.push("killJumping");
  }
  return names.filter((name) => name);
}

// A big hit tears something off the part it landed on: the head comes off, the front arm goes. Low violence keeps the
// body whole and throws nothing
const GORE = {
  Head(zombie) {
    show(zombie.clip, "head", false);
    show(zombie.clip, "neck.damage");
    for (const kind of ["meatChunk", "meatChunk", "meatChunk", "blood", "blood"]) {
      effects.bounce(kind, zombie, { type: "Head" });
    }
  },
  Chest(zombie) {
    if (lowViolence()) {
      return;
    }
    show(zombie.clip, "torso.upperArmLost");
    for (const path of ["hand_front", "lowerArm_front", "upperArm_front"]) {
      show(zombie.clip, path, false);
    }
    effects.bounce("blood", zombie, { type: "Chest" });
    effects.bounce("armChunk", zombie, { type: "Belly" });
    effects.bounce("meatChunk", zombie, { type: "Chest" });
  },
  Belly(zombie) {
    if (lowViolence()) {
      return;
    }
    show(zombie.clip, "upperArm_front.damage");
    for (const path of ["hand_front", "lowerArm_front"]) {
      show(zombie.clip, path, false);
    }
    effects.bounce("blood", zombie, { type: "Belly" });
    effects.bounce("armChunk", zombie, { type: "Belly" });
    effects.bounce("meatChunk", zombie, { type: "Belly" });
  },
};

// The death a hit calls for: legs, and any hit over the damage threshold, the leg death; the head its head death;
// chest and belly the body death. The wound shows on the part. Returns the label to play
function zoneDeath(zombie, cause) {
  show(zombie.clip, WOUNDS[cause.zone] ?? "");
  if (cause.melee !== true && bigHit(cause)) {
    GORE[cause.zone]?.(zombie);
  }
  if (cause.zone === "Legs" || cause.damage > constant("damageThreshold")) {
    return `death_leg${variant("zombieLegDeaths")}`;
  }
  if (cause.zone === "Head") {
    return `death_head${variant("zombieHeadDeaths")}`;
  }
  return `death_body${variant("zombieBodyDeaths")}`;
}

// A blast tears the body apart: every wound shows, meat and blood fly, and one of the explode deaths plays. Low
// violence plays the body death with nothing torn (applyDamageSplash F4:7004-7090)
function blastDeath(zombie) {
  if (lowViolence()) {
    return `death_body${variant("zombieBodyDeaths")}`;
  }
  for (const path of EXPLODE_PARTS) {
    show(zombie.clip, path);
  }
  for (const [kind, type] of [
    ["meatChunk", "Chest"],
    ["meatChunk", "Chest"],
    ["blood", "Chest"],
    ["blood", "Head"],
  ]) {
    effects.bounce(kind, zombie, { type });
  }
  return `death_explode${variant("zombieExplodeDeaths")}`;
}

// Deaths that depend on the body, not the wound (playSpecialDeath F4:10556): a crawler dies on its face; a riser still
// lying or rising dies lying ("Stay Down"); one standing at a wall falls away from it; a dog dies as its state says.
// lying is whether it was down when the hit came. Returns the label to play
function specialDeath(zombie, label, lying) {
  let out = label;
  if (zombie.startPos === "deadFront") {
    show(zombie.clip, "head.deathDamage");
    out = "death_crawler";
  } else if (zombie.startPos === "deadBack" && lying) {
    out = "deadBack_death";
    count("killRiser");
  }
  if (!lying && zombie.type !== CRAWLER && zombie.type !== DOG) {
    const bounds = room.markers.bounds ?? { x: 0, w: room.width };
    const edge = constant("moveEdgeBuffer") * 2;
    const nearRight = zombie.x > bounds.x + bounds.w - edge;
    const nearLeft = zombie.x < bounds.x + edge;
    const faceLeft = zombie.facing < 0;
    out = (nearRight && faceLeft) || (nearLeft && !faceLeft) ? "death_head2" : out;
    out = (nearLeft && faceLeft) || (nearRight && !faceLeft) ? "death_head1" : out;
  }
  if (zombie.type === DOG) {
    out = zombie.state === "chase" ? "death_head1" : "death_body1";
  }
  return out;
}

function takeOutOfRoom(zombie) {
  const at = world.zombies.indexOf(zombie);
  if (at >= 0) {
    world.zombies.splice(at, 1);
  }
}

// A zombie dies (the death half of applyDamageProjectiles F4:5657-5856, applyDamageMelee F4:6428-6500 and
// applyDamageSplash F4:7040-7100). cause is { by, zone, crit, melee, blast, airborne, damage, shell }: who dealt the
// killing blow, the body part, whether it was critical, the kind of blow, whether the killer was off the ground, the
// damage and the shell of the gun. The zombie leaves the room's list, its backpack drops if it carries one, its death
// plays, and the body is taken away after the body fade time. Dying twice does nothing
export function killZombie(zombie, cause = {}) {
  if (zombie.killed === true) {
    return;
  }
  const lying = zombie.laying === true || zombie.rising === true;
  Object.assign(zombie, { alive: false, killed: true });
  takeOutOfRoom(zombie);
  const counters = killCounters(cause);
  if (zombie.dropper === true) {
    dropBackPack(zombie);
  }
  zombieSound(zombie, "death");
  const clip = zombie.clip;
  if (clip && !clip.destroyed) {
    if (zombie.type === SHIELD_TYPE) {
      effects.bounce("riotShield", zombie);
    }
    const label = cause.blast === true ? blastDeath(zombie) : zoneDeath(zombie, cause);
    zombie.deathLabel = specialDeath(zombie, label, lying);
    gotoPlay(clip, zombie.deathLabel);
    clip.zIndex = constant("depth_world_zombiesDead") - constant("depth_world_player") + (zombie.serial % DEPTH_SLOTS);
    effects.expire(clip, "body");
  }
  Object.assign(zombie, { state: "dead", laying: false, rising: false, attacking: false, animWalk: false });
  if (zombie.falling === true) {
    fallingBodies.push(zombie);
  }
  restlessBodies.push(zombie);
  counters.forEach((key) => count(key));
  for (const fn of killListeners) {
    try {
      fn({ zombie, cause, counters });
    } catch (e) {
      console.warn("Union City: a zombie kill listener failed", e);
    }
  }
}

// What a hit that emptied a zombie's health tells killZombie. The combat events carry the blow as an entry
function killedByHit(entry) {
  const { target } = entry;
  if (target?.side !== "zombie") {
    return;
  }
  killZombie(target, {
    by: entry.owner,
    zone: entry.zone,
    crit: entry.crit === true,
    melee: entry.melee === true,
    blast: entry.blast === true,
    airborne: entry.airborne === true,
    damage: entry.damage,
    shell: entry.round?.shell ?? null,
  });
}

// Once a second a falling zombie that has gone outside the room is taken away (clearOutSideRoom F4:1107). The list is
// copied first, so none is skipped and none removed twice
function clearOutsideRoom() {
  for (const zombie of [...world.zombies]) {
    if ((zombie.x < 0 || zombie.x > room.width) && zombie.falling === true) {
      zombie.clip?.destroy({ children: true });
      takeOutOfRoom(zombie);
    }
  }
}

// Once a second, each body on the floor whose death has played out is drawn from one picture and no longer stepped,
// as a room in the ending rush can hold a score of them
function stillBodies() {
  const resolution = page.app.renderer.resolution * page.scale;
  restlessBodies = restlessBodies.filter((body) => {
    if (!body.clip || body.clip.destroyed) {
      return false;
    }
    return fallingBodies.includes(body) || !body.clip.freeze(resolution);
  });
}

// A zombie killed in the air goes on falling to the floor, its death playing as it drops
function dropBodies() {
  for (const body of [...fallingBodies]) {
    if (!body.clip || body.clip.destroyed) {
      fallingBodies = fallingBodies.filter((each) => each !== body);
      continue;
    }
    body.y -= body.jumpHeight;
    body.jumpHeight -= constant("gravity");
    if (body.y >= body.floor) {
      body.y = body.floor;
      fallingBodies = fallingBodies.filter((each) => each !== body);
    }
    body.clip.y = body.y;
  }
}

// ---------- The memory ring ----------

// Ten memories, each a room and the zombies that were alive in it when the player left, newest by its number. Not part
// of a saved slot (F4:27031-27040)
const MEMORY_SLOTS = 10;
const ring = Array.from({ length: MEMORY_SLOTS }, () => ({ room: null, order: 0, zombies: [] }));
let ringAt = 0;
let ringOrder = 0;
// Five infected in a room left earns "Smart Move" (F4:9608)
const SMART_MOVE_CROWD = 5;
// What a zombie coming back wakes with: not after anyone, not in the middle of anything
const CALM = {
  alerted: false,
  animWalk: false,
  target: null,
  collideLeft: false,
  collideRight: false,
  climbing: false,
  jumping: false,
  falling: false,
  crouched: false,
  stumbling: false,
  stumbleMoving: false,
  rising: false,
  attacking: false,
  grabbing: false,
  grabbed: false,
  struggling: false,
  animIdle: false,
  attackCount: 0,
  pausing: 0,
};

function isNode(value) {
  return typeof value === "object" && value !== null && typeof value.destroy === "function";
}

// A zombie as the ring keeps it: every field but its art and who it was after. A zombie in a stumble is kept standing
function snapshot(zombie) {
  const fields = {};
  for (const [name, value] of Object.entries(zombie)) {
    if (name !== "target" && name !== "grabber" && !isNode(value)) {
      fields[name] = value;
    }
  }
  fields.state = fields.state === "stumble" ? "idle" : fields.state;
  return { ...fields, x: zombie.x, y: zombie.y, facing: zombie.facing };
}

// How many enemies are in the room: zombies and the hostile people
function enemiesHere() {
  return world.zombies.length + world.humans.filter((each) => each.side === "enemy" && each.alive === true).length;
}

// Leaving a room keeps its living zombies in the next memory, a whole room's worth of infected earning "Smart Move"
// indoors. Those still falling in from a roof are not kept
function saveZombies(roomId) {
  if (!roomId) {
    return;
  }
  const memory = ring[ringAt];
  ringAt = (ringAt + 1) % MEMORY_SLOTS;
  ringOrder += 1;
  Object.assign(memory, {
    room: roomId,
    order: ringOrder,
    zombies: world.zombies.filter((each) => hasAI(each) && each.falling !== true).map(snapshot),
  });
  if (enemiesHere() >= SMART_MOVE_CROWD && room.def?.outside !== true) {
    count("escapeFullRoom");
  }
}

// A kept zombie back in the room, in the pose it had, unalerted. One that was lying still lies; a crawler that was up
// crawls; the rest stand in their start pose
function revive(saved) {
  const def = zombieType(saved.type);
  if (!def) {
    return null;
  }
  const zombie = { ...saved, ...CALM, def };
  attachClip(zombie);
  faceZombie(zombie, saved.facing);
  decorateZombie(zombie, { predef: true });
  if (zombie.laying === true) {
    goto(zombie.clip, zombie.startPos);
  } else if (zombie.type === CRAWLER) {
    goto(zombie.clip, "crawl");
  } else {
    gotoPlay(zombie.clip, zombie.type === RISER ? "idle" : zombie.startPos);
  }
  zombie.charHeight = zombie.clip.height;
  placeClip(zombie);
  world.zombies.push(zombie);
  return zombie;
}

// Entering a room brings back the latest memory of it, if there is one. Returns the zombies restored
function restoreZombies(roomId) {
  const latest = ring.filter((each) => each.room === roomId).sort((a, b) => b.order - a.order)[0];
  return (latest?.zombies ?? []).map(revive).filter((each) => each);
}

// Forgets one room's zombies (the player died and came back there) or every room's (a new story)
function forgetZombies(roomId = null) {
  for (const memory of ring) {
    if (roomId === null || memory.room === roomId) {
      Object.assign(memory, { room: null, order: 0, zombies: [] });
    }
  }
}

export const zombieMemory = {
  saveZombies,
  restoreZombies,
  forget: forgetZombies,
  ring,
};

// ---------- The step ----------

const STATES = { wander, chase, climb, attack, grab };

// One zombie's step: a lost target first, then the shield's pause, then its state's rule. idle does nothing, stumble
// is combat.js's slide, and dead belongs to the deaths
function think(zombie) {
  dropLostTarget(zombie);
  if (zombie.pausing > 0) {
    zombie.pausing -= 1;
    zombie.alerted = false;
    zombie.state = "wander";
  }
  STATES[zombie.state]?.(zombie);
}

function zombieAI() {
  for (const zombie of [...world.zombies]) {
    if (hasAI(zombie) && zombie.clip) {
      think(zombie);
    }
  }
}

// ---------- Falling and blocks ----------

// A falling zombie drops at the world's gravity until it reaches its floor, and lands there; one dropped from the roof
// wakes as it lands (zombieGravity F4:9512)
function fall(zombie) {
  if (zombie.falling !== true) {
    return;
  }
  goto(zombie.clip, "fall");
  zombie.y -= zombie.jumpHeight;
  zombie.jumpHeight -= constant("gravity");
  zombie.animWalk = false;
  if (zombie.y < zombie.floor) {
    return;
  }
  zombie.y = zombie.floor;
  Object.assign(zombie, { jumping: false, standing: true, crouched: false, falling: false, jumpAnim: false });
  gotoPlay(zombie.clip, "land");
  if (zombie.dropZombie === true && zombie.alerted !== true) {
    alertZombie(zombie, 0, "seen");
  }
}

function zombieGravity() {
  for (const zombie of world.zombies) {
    if (hasAI(zombie) && zombie.clip) {
      fall(zombie);
    }
  }
}

// The test point is 20 px ahead of the feet, toward the block (charPointMod F4:6830)
const BLOCK_POINT = 20;

// A falling zombie lands on a block's top and plays its landing
function landOnBlock(zombie) {
  zombie.jumpHeight = constant("jumpHeightBase");
  gotoPlay(zombie.clip, "land");
  Object.assign(zombie, { jumpAnim: false, jumping: false, landed: true, standing: true, crouched: false });
  zombie.falling = false;
}

// A block a zombie is near, as moveCollisions does for everyone (F4:6825-6876): it stops the zombie moving into its
// side unless the zombie is above its top less 15 px, a falling zombie lands on it, and one that walks off the block it
// stood on starts to fall
function touchBlock(zombie, block) {
  const top = block.y - block.box.h;
  const away = zombie.x - block.x;
  if (!inside(block.box, zombie.x + (away > 0 ? -BLOCK_POINT : BLOCK_POINT), zombie.y)) {
    if (zombie.lastCollision === block.name && !zombie.climbing && !zombie.jumping) {
      goto(zombie.clip, "fall");
      Object.assign(zombie, { lastCollision: null, jumpHeight: 0, falling: true });
    }
    return;
  }
  zombie.lastCollision = block.name;
  if (zombie.y > top) {
    zombie.collideLeft ||= away > 0;
    zombie.collideRight ||= away < 0;
  }
  if (zombie.y < top + constant("collTopBuffer")) {
    if (zombie.falling) {
      landOnBlock(zombie);
    }
    zombie.collideLeft = false;
    zombie.collideRight = false;
  }
}

function zombieBlocks() {
  const reach = constant("moveCollBuffer");
  for (const zombie of world.zombies) {
    if (!hasAI(zombie) || !zombie.clip) {
      continue;
    }
    for (const block of roomBlocks()) {
      if (Math.abs(zombie.x - block.x) <= block.box.w / 2 + reach) {
        touchBlock(zombie, block);
      }
    }
  }
}

// ---------- The art's hooks ----------

// Hooks of the zombie clip (S6800 frames 151 and 409): the climb pose hides the shield on every type that has none
export const ZOMBIE_HOOKS = {
  hideshield(arg, clip) {
    const zombie = ownerOf(clip);
    zombie.animating = true;
    if (zombie.type !== SHIELD_TYPE) {
      const shield = clip.child("shield");
      if (shield) {
        shield.visible = false;
      }
    }
    return true;
  },
  // A body hits the floor (S6800 frames 859, 886, 1004 and 1021): the thud, at the body's place
  bodyfall(arg, clip) {
    sound.play(`sound_bodyFall${Math.floor(Math.random() * 2) + 1}`, { x: ownerOf(clip).x });
    return true;
  },
  // The climb's last frame (S6800 frames 170, 430 and 452, S5302 frame 116)
  endclimb(arg, clip) {
    const zombie = ownerOf(clip);
    if (hasAI(zombie)) {
      endClimb(zombie);
    }
    return true;
  },
};

// The load handler of the zombie head's hat (S5180 frame 2): a zombie with no hat of its own wears one at random. The
// pick is kept on the zombie, so a zombie dressed again wears the same
export const ZOMBIE_LOAD_ACTIONS = {
  hatPick(node) {
    const zombie = ownerOf(node.parentClip?.parentClip);
    if (!zombie || zombie.hat !== undefined) {
      return;
    }
    zombie.hatFrame ??= 5 + Math.floor(page.lib.random() * node.totalFrames);
    node.gotoAndStop(zombie.hatFrame);
  },
};

// S6800 frame 39: the end of the fall and landing runs into the start pose
function zombieScript(clip, frame) {
  if (frame === START_FRAME) {
    goto(clip, ownerOf(clip).startPos);
  }
}

// ---------- Setup ----------

// Zombies whose art went with the room are gone from the list, and so is a struggle's prompt
function dropGone() {
  world.zombies.length = 0;
  fallingBodies = [];
  restlessBodies = [];
  struggle.zombie = null;
  struggle.hud = null;
}

// Leaving a room keeps its living zombies, and coming into one brings the latest of them back. Once the new room
// stands, the zombies of the old are gone from the list, so the restore comes after
function rememberRoom() {
  zombieMemory.saveZombies(room.id);
}

function recallRoom() {
  zombieMemory.restoreZombies(room.id);
}

function placeClips() {
  world.zombies.forEach(placeClip);
}

export function initZombies(owner) {
  page = owner;
  page.lib.scripts.set(ZOMBIE_SPRITE, zombieScript);
  layers.actors.sortableChildren = true;
  onRoom("leave", rememberRoom);
  onRoom("build", dropGone);
  onRoom("build", recallRoom);
  world.onReset(() => zombieMemory.forget());
  page.steppers.push(placeClips);
  onRigCall("alertRisingZombie", alertRisingZombie);
  onRigCall("checkForGrab", checkForGrab);
  onCombat("alert", alertOnHit);
  onCombat("kill", countUnaware);
  onCombat("kill", killedByHit);
  onCombat("playerDead", playerDied);
  onNoise(alertOnNoise);
  world.stage("controls", struggleControls);
  world.stage("slow", checkZombieMovementAlerts);
  world.stage("slow", struggleDamage);
  world.stage("slow", clearOutsideRoom);
  world.stage("slow", stillBodies);
  page.lib
    .need([STRUGGLE_HUD])
    .then(() => {
      hudReady = true;
    })
    .catch((e) => console.warn("Union City: the struggle prompt's art couldn't load", e));
  world.stage("gravity", zombieGravity);
  world.stage("gravity", dropBodies);
  world.stage("collisions", zombieBlocks);
  world.stage("melee", zombieBlows);
  world.stage("zombies", zombieAI);
}

// Rolls a wake n times on a sleeping zombie, putting it back to sleep after each. Returns how many woke it
function rollOdds(zombie, n, roll) {
  const saved = { state: zombie.state, target: zombie.target, animWalk: zombie.animWalk, alerted: false };
  let woke = 0;
  for (let i = 0; i < n; i += 1) {
    Object.assign(zombie, saved);
    roll();
    woke += zombie.alerted === true ? 1 : 0;
  }
  Object.assign(zombie, saved);
  return woke;
}

// Helpers for page.py checks
export const zombiesDebug = {
  // One zombie of a type at x (see spawnZombie for the options)
  spawnZombie(type, x, options) {
    return spawnZombie(type, x, options);
  },

  // The types the director spawns, in the original's order
  zombieTypes() {
    return Object.keys(data.actors.zombies);
  },

  // Wakes a zombie as one that was seen: it picks the nearest target and chases it (a riser rises first)
  wake(zombie) {
    wakeZombie(zombie);
    return zombie.state;
  },

  // The fields of a zombie the AI reads and writes, for reading back in checks
  zombieState(zombie) {
    const fields = ["state", "x", "y", "dir", "facing", "alerted", "attacking", "climbing", "falling", "pausing"];
    const out = Object.fromEntries(fields.map((name) => [name, zombie[name]]));
    return { ...out, target: zombie.target?.name ?? zombie.target?.kind ?? null, frame: zombie.clip?.frame };
  },

  // Runs the once-a-second wake check n times on one zombie, putting it back to sleep after each, and returns how
  // many of the n woke it. The zombie is left asleep as it was
  wakeOdds(zombie, n = 1000) {
    return rollOdds(zombie, n, () => checkZombieMovementAlerts());
  },

  // The same for one gunshot's noise from the gun in the player's hands
  noiseOdds(zombie, n = 1000) {
    const noise = weaponOf(player)?.weaponNoise ?? 0;
    return { noise, woke: rollOdds(zombie, n, () => weaponNoise(player)) };
  },

  // The struggle under way and the player's hold flags
  struggleState() {
    const { count, needed, side } = struggle;
    const flags = { grabbed: player.grabbed, struggling: player.struggling, controlsLocked: player.controlsLocked };
    return { zombie: struggle.zombie?.name ?? null, count, needed, side, prompt: Boolean(struggle.hud), ...flags };
  },

  // Kills of unaware enemies by the player so far
  unawareKills() {
    return unawareKills;
  },

  // Takes every zombie out of the room
  clearSpawned() {
    for (const each of world.zombies) {
      each.clip?.destroy({ children: true });
    }
    world.zombies.length = 0;
  },

  // The player's round of that damage lands on a zombie's body part and empties its health, as a shot of the gun in
  // the hands would (options: crit, shell). Returns the zombie's state and the label it plays
  shoot(zombie, zone = "Chest", damage = 50, { crit = false, shell = "pistol" } = {}) {
    zombie.health = 1;
    const round = { owner: player, damage, skill: "pistols", crit, shell, weaponRef: "M9", piercing: null };
    damageRanged(zombie, round, zone);
    return { alive: zombie.alive, state: zombie.state, frame: zombie.clip?.frame };
  },

  // The counters the deaths have added to so far
  killCounts() {
    return { ...tally };
  },

  // The ring's rooms and how many zombies each holds, newest last
  memory() {
    return ring
      .filter((each) => each.room)
      .sort((a, b) => a.order - b.order)
      .map((each) => ({ room: each.room, order: each.order, zombies: each.zombies.length }));
  },

  // Leaves the room's zombies in the ring and brings them back, as a trip out of the room and in again would
  roundTrip() {
    zombieMemory.saveZombies(room.id);
    for (const each of [...world.zombies]) {
      each.clip?.destroy({ children: true });
    }
    world.zombies.length = 0;
    return zombieMemory.restoreZombies(room.id);
  },
};

export const zombies = {
  spawn: spawnZombie,
  decorate: decorateZombie,
  health: zombieHealth,
  damage: zombieDamage,
  face: faceZombie,
  sound: zombieSound,
  type: zombieType,
  findTarget: findZombieTarget,
  wake: wakeZombie,
  alert: alertZombie,
  checkAlerts: checkZombieMovementAlerts,
  startStruggle,
  endStruggle,
  struggle,
  climb: climbBlock,
  kill: killZombie,
  memory: zombieMemory,
  onCount: onZombieCount,
  onKill: onZombieKill,
};
