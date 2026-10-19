// The player in the world: walking, sprinting, crouching, jumping, what blocks them and what their load does to it
// (playerControls F4:12244, playerMove F4:12572, calcMoveSpeed F4:12676, characterGravity F4:12168, moveCollisions
// F4:6743-6890), and what keeps them alive: health, stamina, hunger, sleep, XP and levels (F4:11705-11729,
// 13239-13810). `player` is the actor every rule reads; the rig drawn for it is built again in each room, and the
// story keeps what a save holds (health, stamina, skills, carry weight, XP).
//
// The original reads its keys with lock flags that clear when the key goes up (upKeyLocked, downKeyLocked,
// sprintLocked, F4:18694); the same flags here clear when the input state says the key is no longer held, so a touch
// button that fills the same fields behaves like the key.
import { boxOf, inside } from "./collide.js";
import { data } from "./data.js";
import { help } from "./help.js";
import { hud } from "./hud.js";
import { input } from "./input.js";
import { frameFor, goto, makeHuman, onRigCall, rootFlags, storyLook } from "./rig.js";
import { rng } from "./rng.js";
import { camera, layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { findItem, story } from "./story.js";
import { world } from "./world.js";

// Used until the converted constants load
const DEFAULTS = {
  runSpeedMod: 1.5,
  walkBackwards: 1.5,
  walkCrouched: 2,
  walkCrouchedBackwards: 3,
  jumpHeightBase: 11,
  gravity: 1.5,
  moveCollBuffer: 45,
  collTopBuffer: 15,
  staminaRun: 1,
  staminaShove: 1,
  staminaJump: 5,
  stamRegenDelay: 15,
  staminaBase: 56,
  healthBase: 20,
  attributeMod: 1.6,
  attributeBase: 5,
  carryWeightMultiplier: 20,
  minStamRegen: 0.1,
  regenTimeMax: 15,
  permHealthDmgMod: 1.85,
  hurtSoundChance: 60,
  hungerRate: 0.15,
  levelXPMult: 20,
  levelCap: 30,
  playerAttPoints: 1,
  playerSkillPoints: 10,
  XPcutOff: 4,
  xpRespawnPen: 2,
  xpRespawnPenOutside: 4,
  xpSmartsBonusDiv: 30,
  skillUse_search: 5,
  skillUse_security: 25,
};
// Speed and jump height each point of Fitness adds (setMoveSpeed F4:12150, setJumpHeight F4:12163)
const FITNESS_SPEED = 0.02;
const FITNESS_JUMP = 0.04;
// Over the carry weight the move penalty is larger than any speed, so the player can't move (F4:12154)
const WEIGHT_PENALTY = 50;
// The fastest a jump comes down, in pixels a step (F4:12185)
const FALL_MOST = 10;
// How far ahead of the character's feet a block is tested (F4:6838)
const BLOCK_REACH = 20;
// A player who arrives further into the room than this faces left (setupPlayer F4:11843)
const FACE_LEFT_PAST = 100;
// The stamina each action costs before Fitness cuts it
const STAMINA_COSTS = { run: "staminaRun", shove: "staminaShove", jump: "staminaJump" };
const LOW_STAMINA = "LOW STAMINA";
// Health percent below which the heartbeat sounds (F4:5270)
const HEARTBEAT_BELOW = 40;
// Health percent below which each heartbeat gap applies: the gap is in medium steps (half a second each), F4:5251
const HEART_GAPS = [
  [10, 0],
  [20, 1],
  [30, 2],
  [40, 3],
];
// The hurt voice and shake the first time health falls below its lowest since the last full heal (F4:18030): a 5 px
// shake for two 50 ms pulses
const HURT_SHAKE_PX = 5;
const HURT_SHAKE_MS = 100;
// A vital above this starts to cost attributes, a third of the excess each (applyAttrPenalty F4:13263)
const PENALTY_FROM = 70;
const PENALTY_DIVISOR = 3;
// Which vital costs which attribute: sleep dulls the mind, hunger weakens the body
const PENALTY_VITAL = { precision: "sleep", intellect: "sleep", strength: "hunger", endurance: "hunger" };
const VITAL_MOST = 100;
// Sleep's need falls ten times as fast as the amount asked for (adjustVital F4:13308)
const SLEEP_REST_MULTIPLE = 10;
// How much sleep need rises each game minute (degradeVitals F4:13358)
const SLEEP_RATE = 0.15;
// The names for a vital by round(value / 25) (F4:27456-27459)
const VITAL_STATES = {
  hunger: ["V.Well Fed", "Well Fed", "Satisfied", "Hungry", "Starving"],
  sleep: ["V.Well Rested", "Well Rested", "Rested", "Tired", "Exhausted"],
};
const VITAL_STEP = 25;
const TOO_HEAVY = "TOO MUCH WEIGHT";
const NO_OPEN_GRABBED = "CANNOT OPEN WHILE BEING ATTACKED";
// The enemy kinds that block, and the one that blocks while lying down (it crawls)
const ENEMY_SIDES = new Set(["zombie", "enemy"]);
const CRAWLER = "zombieCrawl";

let page = null;
// The key locks of the original: a held key acts once until it goes up
const locks = { up: false, down: false, sprint: false };
// What the input held on the last step, to hear a key go up
const before = { left: false, right: false, crouch: false, up: false, sprint: false };
// The room's blocks with their collision boxes, worked out once the room stands
let blocks = [];
// Steps spent sprinting since the player last stood still, for the sprint achievement
let sprintCount = 0;
const sprintListeners = [];
const levelListeners = [];
// The lowest health percent reached since the last full heal, for the hurt voice and shake
let lowestPercent = 100;
// Medium steps since the last heartbeat
let heartCount = 0;

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

// The player as every rule reads them (actor, shared interfaces B). Health and stamina live in the story, which a save
// keeps; the rest is the body in this room
export const player = {
  kind: "player",
  name: "player",
  side: "player",
  clip: null,
  rig: null,
  x: 0,
  y: 0,
  // The jump's upward speed this step (the original's jumpHeight on the clip)
  jumpHeight: 0,
  facing: 1,
  // "left" or "right": the way the player last moved
  dir: "",
  speed: 7.5,
  currentSpeed: 0,
  fitnessMoveBonus: 0,
  jumpHeightBase: 11,
  weightPenalty: 0,
  overweight: false,
  sprinting: false,
  stamAlert: false,
  stamRegenCount: 0,

  get vy() {
    return this.jumpHeight;
  },

  // In the air: jumping, or falling off a block
  get airborne() {
    return this.jumping || this.falling;
  },

  get stamina() {
    return story.player?.stamina ?? 0;
  },

  set stamina(value) {
    story.player.stamina = value;
  },

  get staminaMax() {
    return story.player?.staminaMax ?? 0;
  },

  get health() {
    return story.player?.health ?? 0;
  },

  get healthMax() {
    return story.player?.healthMax ?? 0;
  },

  get skills() {
    return story.player?.skills;
  },

  get attributes() {
    return story.player?.attributes;
  },

  get level() {
    return story.player?.level ?? 1;
  },

  // Health under the heartbeat line (40 percent of the most)
  get lowHealth() {
    return story.player ? healthPercent() < HEARTBEAT_BELOW : false;
  },

  get weapon() {
    return story.player?.slots[story.player.holding];
  },
};

// The body's flags as setupPlayer leaves them on entering a room (F4:11856-11899)
function standUp() {
  Object.assign(player, {
    alive: true,
    alerted: true,
    controlsLocked: false,
    aimLocked: false,
    crouched: false,
    standing: true,
    moving: false,
    jumping: false,
    falling: false,
    landed: true,
    jumpAnim: false,
    firing: false,
    firingAnim: false,
    grabbed: false,
    struggling: false,
    shoving: false,
    meleeSwing: false,
    climbing: false,
    collideLeft: false,
    collideRight: false,
    lastCollision: null,
    transitioning: false,
    sprinting: false,
    dir: "",
  });
  player.jumpHeight = player.jumpHeightBase;
  player.currentSpeed = player.speed;
  rootFlags.playerMoveForwardAnim = false;
  rootFlags.playerMoveBackwardAnim = false;
}

// ---------- Numbers from the stats ----------

// How much of an attribute the player's hunger or sleep takes off. Run & Gun has no penalties (spec 2.13)
export function penalty(attribute) {
  const vital = PENALTY_VITAL[attribute];
  if (!vital || story.mode !== "survivor" || !story.player) {
    return 0;
  }
  const value = story.player[vital];
  return value > PENALTY_FROM ? Math.round((value - PENALTY_FROM) / PENALTY_DIVISOR) : 0;
}

// An attribute as the rules read it: the player's carry the penalties, never below 1 (F4:13263)
export function attributeOf(who, attribute) {
  const value = who.attributes[attribute];
  return who === player || who === story.player ? Math.max(1, value - penalty(attribute)) : value;
}

// A skill with its attribute's share (adjustedSkill: round(skill + attribute x 1.6 - 5))
export function adjustedSkill(who, skill) {
  const attribute = (data.actors.skills[skill] ?? data.actors.hiddenSkills?.[skill])?.attribute;
  const base = who.skills[skill] ?? 0;
  const share = attribute ? attributeOf(who, attribute) * constant("attributeMod") : 0;
  return Math.round(base + share - constant("attributeBase"));
}

// Max health: round(20 + Endurance squared + level x 10), with the unpenalised Endurance (setPlayerHealthMax F4:11712)
function healthMaxOf(who) {
  return Math.round(constant("healthBase") + who.attributes.endurance ** 2 + who.level * 10);
}

// Max stamina: round(level + Endurance + adjusted Fitness + 56), the unpenalised Endurance (calculateStamina F4:13389)
function staminaMaxOf(who) {
  return Math.round(who.level + who.attributes.endurance + adjustedSkill(who, "fitness") + constant("staminaBase"));
}

// What stamina gives back each quick step once it has rested, never less than 0.1 (calculateStamina F4:13396)
function staminaRegenRate() {
  const who = story.player;
  const rate = Math.round((attributeOf(who, "endurance") + adjustedSkill(who, "fitness")) / 20);
  return Math.max(constant("minStamRegen"), rate);
}

// Max health from the level and Endurance. Health and permanent health stay where they are, cut to the new most
export function setHealthMax() {
  const who = story.player;
  who.healthMax = healthMaxOf(who);
  who.health = Math.min(who.health, who.healthMax);
  who.permHealth = Math.min(who.permHealth, who.healthMax);
}

// Max stamina from the level, Endurance and Fitness. Stamina stays where it is, cut to the new most
export function setStaminaMax() {
  const who = story.player;
  who.staminaMax = staminaMaxOf(who);
  who.stamina = Math.min(who.stamina, who.staminaMax);
}

// The chance out of 100 that a hit is critical: round(Luck / 7 + adjusted skill of the weapon / 11) (setCritChance
// F4:2236). Worked out from the shooter's own stats each time it is asked
export function critChance(who, skill) {
  const luck = who.attributes.luck / constant("critLuckReduction");
  return Math.round(luck + adjustedSkill(who, skill) / constant("critSkillReduction"));
}

// What the backpack weighs, to a tenth of a pound (getTotalWeight F4:7131); nothing when it is empty
export function carriedWeight() {
  let total = 0;
  for (const row of story.inventory ?? []) {
    total += findItem(row.ref)?.item.weight ?? 0;
  }
  return Math.round(total * 10) / 10;
}

// The move penalty for the player's load. The alert shows once each time the player goes over the limit
function checkWeight() {
  const over = carriedWeight() > story.player.carryWeight;
  player.weightPenalty = over ? WEIGHT_PENALTY : 0;
  if (over && !player.overweight) {
    hud.alert(TOO_HEAVY);
  }
  player.overweight = over;
}

// Speed, jump height and the load's penalty from the current stats; called whenever the stats or the backpack change.
// Each is set outright from Fitness, so running it twice changes nothing
export function recalcMovement() {
  if (!story.player) {
    return;
  }
  const fitness = story.player.skills.fitness;
  player.speed = story.player.speed;
  player.fitnessMoveBonus = fitness * FITNESS_SPEED;
  player.jumpHeightBase = constant("jumpHeightBase") + fitness * FITNESS_JUMP;
  if (!player.airborne) {
    player.jumpHeight = player.jumpHeightBase;
  }
  checkWeight();
}

// Everything that follows from the stats: carry weight (from the unpenalised Strength), max health, max stamina, speed
// and jump. Called when a story starts, on entering a room and whenever the points are confirmed
export function recalcStats() {
  if (!story.player) {
    return;
  }
  story.player.carryWeight = story.player.attributes.strength * constant("carryWeightMultiplier");
  setHealthMax();
  setStaminaMax();
  recalcMovement();
}

// Stamina spent on a sprint step, a shove or a jump, cut by adjusted Fitness / 10 percent (reduceStamina F4:13412).
// It never drops below 0; reaching 0 says so once, gasps and ends the sprint
export function reduceStamina(kind) {
  const cost = constant(STAMINA_COSTS[kind]) ?? 0;
  const cut = adjustedSkill(story.player, "fitness") / 10;
  story.player.stamina = Math.max(0, story.player.stamina - (cost - (cost / 100) * cut));
  if (story.player.stamina <= 0 && !player.stamAlert) {
    player.stamAlert = true;
    hud.alert(LOW_STAMINA);
    const voice = story.player.sex === "male" ? "sound_playerBreath" : "sound_playerBreath_female";
    sound.play(`${voice}${rng.random(2) + 1}`);
    endSprint();
  }
  player.stamRegenCount = constant("stamRegenDelay");
}

// ---------- Health ----------

// Health as a percent of the most, to a whole number (the health bar's scale, F4:18268)
function healthPercent() {
  return Math.round((story.player.health / story.player.healthMax) * 100);
}

// The red edges follow health
export function showHealth() {
  hud.damage(healthPercent());
}

// The wait before health starts coming back begins again (resetRegenTimer F4:13239)
export function resetRegenTimer() {
  player.regenTimer = constant("regenTimeMax");
}

// The voice and the shake of a hit that takes health lower than it has been since the last full heal (hudDamageDisplay
// F4:18014)
function hurt() {
  const percent = healthPercent();
  if (percent >= lowestPercent) {
    return;
  }
  lowestPercent = percent;
  hud.hurt();
  if (rng.random(101) < constant("hurtSoundChance")) {
    const male = story.player.sex === "male";
    sound.play(`${male ? "sound_playerHurt" : "sound_playerHurt_female"}${rng.random(male ? 3 : 2) + 1}`);
  }
  camera.shake(HURT_SHAKE_PX, HURT_SHAKE_MS);
}

// A hit takes its damage from health and a share of it from permanent health (F4:5636). Returns true when health ran
// out; what follows from that belongs to the caller
export function damagePlayer(damage) {
  const who = story.player;
  resetRegenTimer();
  who.permHealth = Math.max(0, who.permHealth - Math.round(damage / constant("permHealthDmgMod")));
  who.health = Math.max(0, who.health - damage);
  showHealth();
  hurt();
  return who.health <= 0;
}

// Raises permanent health by n, to the most. With health: true health rises by n too (Run & Gun food, F4:8452)
export function healPerm(n, { health = false } = {}) {
  const who = story.player;
  who.permHealth = Math.min(who.healthMax, who.permHealth + n);
  if (health) {
    who.health = Math.min(who.healthMax, who.health + n);
  }
  showHealth();
}

// Health and permanent health both full (fullHealth F4:11705)
export function fullHealth() {
  const who = story.player;
  lowestPercent = 100;
  who.health = who.healthMax;
  who.permHealth = who.healthMax;
  showHealth();
}

// After the wait, each quick step gives back healthMax / 200 x ((Endurance + Survival / 5) / 2) up to permanent health
// (playerHealthRegen F4:13243)
function regenHealth() {
  const who = story.player;
  if (player.alive !== true || who.health >= who.permHealth) {
    return;
  }
  player.regenTimer -= 1;
  if (player.regenTimer > 0) {
    return;
  }
  const strength = (attributeOf(who, "endurance") + Math.round(who.skills.survival / 5)) / 2;
  who.health = Math.min(who.permHealth, who.health + (who.healthMax / 200) * strength);
  showHealth();
}

// Under 40 percent a heartbeat sounds every few medium steps, closer together the lower health goes, and louder (50
// minus the percent; the sound's cut-off keeps it silent until health is under 30, F4:5270)
function heartbeat() {
  const percent = healthPercent();
  if (player.alive !== true || percent >= HEARTBEAT_BELOW) {
    return;
  }
  const gap = HEART_GAPS.find(([below]) => percent < below)[1];
  heartCount += 1;
  if (heartCount > gap) {
    heartCount = 0;
    sound.play(`sound_heartBeat${rng.random(2) + 1}`, { volume: 50 - percent });
  }
}

// ---------- Stamina ----------

// Once stamina has gone unused for the delay, each quick step gives back its rate up to the most (staminaRegen
// F4:13440)
function regenStamina() {
  const who = story.player;
  player.stamRegenCount = Math.max(-1, player.stamRegenCount - 1);
  if (player.stamRegenCount < 0 && who.stamina < who.staminaMax) {
    who.stamina = Math.min(who.staminaMax, who.stamina + staminaRegenRate());
    player.stamAlert = false;
  }
}

// ---------- Hunger and sleep ----------

// Raises ("incNeed") or lowers ("decNeed") a vital, between 0 and 100. Resting takes off ten times the amount
// (adjustVital F4:13308)
export function adjustVital(vital, change, amount) {
  const who = story.player;
  if (change === "incNeed" && who[vital] < VITAL_MOST) {
    who[vital] = Math.min(VITAL_MOST, who[vital] + amount);
  }
  if (change === "decNeed" && who[vital] > 0) {
    const taken = vital === "sleep" ? Math.round(amount * SLEEP_REST_MULTIPLE) : amount;
    who[vital] = Math.max(0, who[vital] - taken);
  }
}

// Both need more each game minute, in every mode; Run & Gun just never shows or feels them (degradeVitals F4:13358)
function degradeVitals() {
  adjustVital("sleep", "incNeed", SLEEP_RATE);
  adjustVital("hunger", "incNeed", constant("hungerRate"));
}

// The name of how hungry or sleepy the player is, with its place in the list of five
export function vitalState(vital) {
  const index = Math.min(4, Math.max(0, Math.round(story.player[vital] / VITAL_STEP)));
  return { index, name: VITAL_STATES[vital][index] };
}

// ---------- XP and levels ----------

// What it takes to leave a level: 100 x level squared (setupExperience F4:13595)
function levelXPFor(level) {
  return Math.round((constant("levelXPMult") * level * (level * 5)) / 100) * 100;
}

// The danger of the room the player is in, which a kill's XP is worked out from. A safe house has none
function roomDanger() {
  return room.def?.safeHouse ? 0 : (room.def?.danger ?? 0);
}

// Registers fn({ level, gained, forgot }) for when the player levels up. forgot is true when points from before were
// still unspent (the "Forgetful" achievement)
export function onLevelUp(fn) {
  levelListeners.push(fn);
}

function showXP(amount, kill) {
  if (!story.settings.showXPText) {
    return;
  }
  if (amount > 0) {
    hud.xpText(`+${amount} XP`);
  } else if (kill) {
    hud.xpText("NO XP - ENEMY LEVEL TOO LOW", true);
  }
}

// Adds XP. A kill counts only when the player is at most 4 levels above the room's danger (adjustXP F4:13616). Returns
// what was added
export function addXP(amount, { reason = "quest", danger = roomDanger() } = {}) {
  const who = story.player;
  const kill = reason === "kill";
  const gained = kill && who.level - danger > constant("XPcutOff") ? 0 : amount;
  who.xp += gained;
  showXP(gained, kill);
  return gained;
}

// XP for a kill: round((round(danger x 5) + 5) x the target's bonus), from the room the player is in now
export function killXP(target) {
  const danger = roomDanger();
  return addXP(Math.round((Math.round(danger * 5) + 5) * (target.xpBonus ?? 1)), { reason: "kill", danger });
}

// round(base + level) + ceil(adjusted Smarts / 30): what a first search and a lock give
function smartsXP(base) {
  const who = story.player;
  const smarts = Math.ceil(adjustedSkill(who, "smarts") / constant("xpSmartsBonusDiv"));
  return Math.round(base + who.level) + smarts;
}

// XP for the first search of a container
export function searchXP() {
  return smartsXP(constant("skillUse_search"));
}

// XP for picking or forcing a lock
export function lockXP() {
  return smartsXP(constant("skillUse_security"));
}

// Dying where the player stands costs half the XP; coming back outside costs a quarter
export function loseXP({ outside = false } = {}) {
  const who = story.player;
  const share = constant(outside ? "xpRespawnPenOutside" : "xpRespawnPen");
  who.xp = Math.max(0, who.xp - Math.round(who.xp / share));
}

// Takes the player up every level their XP pays for. Each level costs its XP and leaves the rest; each gives an
// attribute point and 10 skill points. Run twice a second (levelUp F4:13484)
export function levelUpCheck() {
  const who = story.player;
  if (who.xp < who.levelXP || who.level >= constant("levelCap")) {
    return;
  }
  const forgot = who.points.attribute > 0 || who.points.skill > 0;
  const from = who.level;
  while (who.xp >= who.levelXP && who.level < constant("levelCap")) {
    who.xp -= who.levelXP;
    who.level += 1;
    who.levelXP = levelXPFor(who.level);
    who.points.attribute += constant("playerAttPoints");
    who.points.skill += constant("playerSkillPoints");
  }
  sound.play("sound_levelUp");
  hud.banner("level", `LEVEL ${who.level}`);
  help.show("levelUp");
  for (const fn of levelListeners) {
    fn({ level: who.level, gained: who.level - from, forgot });
  }
}

// ---------- The rig's poses ----------

function play(label) {
  const frame = frameFor(player.clip, label);
  if (frame) {
    player.clip.gotoAndPlay(frame);
  }
}

function setAnims(forward, backward) {
  rootFlags.playerMoveForwardAnim = forward;
  rootFlags.playerMoveBackwardAnim = backward;
}

// 1 faces right, -1 left. The aim turns the player; walking away from it is walking backwards
export function face(dir) {
  player.facing = dir < 0 ? -1 : 1;
  player.rig?.setFacing(player.facing);
}

// Registers fn(n) for when the player stops: n is a third of the steps sprinted since the last stop
export function onSprintDone(fn) {
  sprintListeners.push(fn);
}

function endSprint() {
  player.rig?.setAnimMode("upper");
  player.sprinting = false;
}

// The player stops: standing or crouched, and a sprint ends (idlePlayerPosition F4:12705)
function idle() {
  if (player.alive !== true) {
    return;
  }
  const sprinted = Math.round(sprintCount / 3);
  sprintCount = 0;
  for (const fn of sprintListeners) {
    fn(sprinted);
  }
  player.moving = false;
  setAnims(false, false);
  if (player.sprinting) {
    endSprint();
  }
  if (!player.shoving && !player.grabbed) {
    goto(player.clip, player.crouched ? "crouched" : "standing");
  }
}

// A panel the player opens with a key stays shut while a zombie holds them, with a red alert (addNoOpenStruggleAlert
// F4:15817). Returns true when the opening is refused
export function refuseOpen() {
  if (player.struggling !== true) {
    return false;
  }
  hud.alert(NO_OPEN_GRABBED, "red");
  return true;
}

// The art calls idlePlayerPosition when the shove out of a struggle ends (S4925 frame 203)
function idleCall({ owner }) {
  if (owner === player) {
    idle();
  }
}

// ---------- Controls ----------

// The speed for this step (calcMoveSpeed F4:12676). Only forward walking sprints, and each sprint step costs stamina
function moveSpeed(crouched, backwards) {
  const { speed, fitnessMoveBonus: bonus, weightPenalty: penalty } = player;
  if (player.stamina <= 0) {
    player.sprinting = false;
  }
  if (!crouched && !backwards) {
    player.currentSpeed = speed + bonus - penalty;
    if (player.sprinting) {
      reduceStamina("run");
      player.currentSpeed = (speed + bonus - penalty) * constant("runSpeedMod");
      sprintCount += 1;
    }
  } else if (!crouched) {
    player.currentSpeed = speed / constant("walkBackwards") - penalty;
  } else if (!backwards) {
    player.currentSpeed = speed / constant("walkCrouched") + bonus - penalty;
  } else {
    player.currentSpeed = speed / constant("walkCrouchedBackwards") + bonus - penalty;
  }
  player.currentSpeed = Math.max(0, player.currentSpeed);
}

// One step toward dir (-1 left, 1 right), kept inside the room's edges (playerMove F4:12572)
function move(dir) {
  player.dir = dir < 0 ? "left" : "right";
  if (player.shoving) {
    return;
  }
  if (dir < 0) {
    player.collideRight = false;
  } else {
    player.collideLeft = false;
  }
  player.moving = true;
  moveSpeed(player.crouched, player.facing !== dir);
  const { left, right } = room.edges;
  player.x = Math.min(right, Math.max(left, player.x + dir * player.currentSpeed));
}

// The walk the legs play for the way the player moves: forward, backward, crouched or sprinting. Turning to walk
// backwards ends a sprint
function walkAnim(dir) {
  if (player.jumping || player.currentSpeed <= 0) {
    return;
  }
  if (player.facing !== dir) {
    if (!rootFlags.playerMoveBackwardAnim) {
      setAnims(false, true);
      if (player.crouched) {
        play("crouchWalkBackward");
      } else {
        play("walkBackward");
        if (player.sprinting) {
          endSprint();
        }
      }
    }
  } else if (!rootFlags.playerMoveForwardAnim) {
    setAnims(true, false);
    if (player.crouched) {
      play("crouchWalk");
    } else {
      play(player.sprinting ? "sprint" : "walk");
    }
  }
}

function moveKeys() {
  if (input.left && !player.collideLeft && !player.shoving) {
    help.did("left");
    move(-1);
    walkAnim(-1);
  } else if (input.right && !player.collideRight && !player.shoving) {
    help.did("right");
    move(1);
    walkAnim(1);
  }
}

// Shift starts a sprint while walking forward with stamina, standing up; it stays off until Shift is let go
function sprintKey() {
  if (!input.sprintHeld || locks.sprint || locks.down) {
    return;
  }
  const going = player.stamina > 0 && player.currentSpeed > 0 && player.moving;
  if (going && !rootFlags.playerMoveBackwardAnim && !player.crouched) {
    player.rig.setAnimMode("full");
    player.reloading = false;
    player.firing = false;
    player.firingAnim = false;
    locks.sprint = true;
    rootFlags.playerMoveForwardAnim = false;
    player.sprinting = true;
    help.did("sprint");
  }
}

// W jumps when standing with stamina and not over the carry weight; crouched, it stands up instead
function jumpKey() {
  if (!(input.upHeld || input.jumpPressed) || locks.up) {
    return;
  }
  locks.up = true;
  const ready = !player.jumping && player.standing && !player.crouched && !player.overweight;
  if (ready && player.stamina > 0) {
    reduceStamina("jump");
    player.standing = false;
    player.crouched = false;
    player.jumping = true;
    setAnims(false, false);
  }
  if (player.crouched) {
    player.rig.setCrouch(false);
    setAnims(false, false);
  }
}

// S, Down or Ctrl crouches, unless Shift is held; with Toggle Crouch on, the next press stands up
function crouchKey() {
  if (!input.crouchHeld || player.shoving || input.sprintHeld) {
    return;
  }
  const free = !player.jumping && !player.falling && !player.grabbed;
  if (!locks.down && !player.crouched && free) {
    locks.down = true;
    setAnims(false, false);
    player.rig.setCrouch(true);
  }
  if (!locks.down && player.crouched && story.settings.toggleCrouch && !player.grabbed) {
    locks.down = true;
    player.rig.setCrouch(false);
    setAnims(false, false);
  }
}

// Letting go of crouch stands the player up when Toggle Crouch is off (releaseCrouch F4:12531)
export function releaseCrouch() {
  if (!story.settings.toggleCrouch && !player.grabbed && !player.sprinting && player.crouched) {
    setAnims(false, false);
    player.rig.setCrouch(false);
  }
}

// The keys that went up since the last step (keyUpDetection F4:18694)
function keysUp() {
  const now = {
    left: input.left,
    right: input.right,
    crouch: input.crouchHeld,
    up: input.upHeld,
    sprint: input.sprintHeld,
  };
  if (before.crouch && !now.crouch) {
    locks.down = false;
    releaseCrouch();
  }
  if (!now.up) {
    locks.up = false;
  }
  if ((before.left && !now.left) || (before.right && !now.right)) {
    idle();
  }
  if (before.sprint && !now.sprint) {
    endSprint();
    rootFlags.playerMoveForwardAnim = false;
    locks.sprint = false;
  }
  Object.assign(before, now);
}

function controls() {
  if (world.player !== player || !player.rig) {
    return;
  }
  checkWeight();
  if (player.alive === true) {
    keysUp();
  }
  if (player.alive !== true || player.controlsLocked) {
    return;
  }
  moveKeys();
  sprintKey();
  jumpKey();
  crouchKey();
}

// ---------- Gravity ----------

// Feet back on the ground or a block: the walk picks up again if the player is still moving
function land() {
  player.jumpHeight = player.jumpHeightBase;
  Object.assign(player, { jumping: false, landed: true, standing: true, crouched: false, falling: false });
  player.jumpAnim = false;
  if (!player.moving) {
    goto(player.clip, "standing");
  } else if (player.dir === (player.facing > 0 ? "right" : "left")) {
    play("walk");
  } else {
    play("walkBackward");
  }
}

// A jump rises by its speed and slows by gravity each step, falling at most 10 a step; walking off a block drops the
// same way. Either lands exactly on the floor (characterGravity F4:12168)
function gravity() {
  if (world.player !== player || !player.rig) {
    return;
  }
  if (player.jumping) {
    player.landed = false;
    if (!player.jumpAnim) {
      player.jumpAnim = true;
      play("jump");
    }
    player.y -= player.jumpHeight;
    player.jumpHeight -= constant("gravity");
    player.falling ||= player.jumpHeight < 0;
    player.jumpHeight = Math.max(-FALL_MOST, player.jumpHeight);
    if (player.y >= room.floorY && player.falling) {
      player.y = room.floorY;
      setAnims(false, false);
      land();
    }
  } else if (player.falling) {
    player.y -= player.jumpHeight;
    player.jumpHeight -= constant("gravity");
    if (player.y >= room.floorY) {
      player.y = room.floorY;
      land();
    }
  }
}

// ---------- What blocks the player ----------

// A living enemy standing (or a crawler) blocks
function blocksPlayer(enemy) {
  return ENEMY_SIDES.has(enemy.side) && enemy.alive === true && (enemy.laying !== true || enemy.type === CRAWLER);
}

// The first enemy within 45 px stops the player moving toward it, and stops them (F4:6743-6775)
function enemyCollide() {
  const reach = constant("moveCollBuffer");
  player.collideLeft = false;
  player.collideRight = false;
  for (const enemy of [...world.zombies, ...world.humans]) {
    if (!blocksPlayer(enemy) || Math.abs(enemy.x - player.x) > reach) {
      continue;
    }
    if (player.x <= enemy.x) {
      player.collideRight = true;
    } else {
      player.collideLeft = true;
    }
    idle();
    return;
  }
}

// The room's blocks, each with its collision box in world pixels
export function roomBlocks() {
  if (blocks.roomId !== room.id) {
    blocks = room.blocks
      .map((each) => ({ ...each, box: boxOf(room.markers[each.name]?.clip, "collision") }))
      .filter((each) => each.box);
    blocks.roomId = room.id;
  }
  return blocks;
}

// A character on a block's top: the jump or fall ends where they are
function landOnBlock(actor) {
  actor.jumpHeight = actor.jumpHeightBase;
  goto(actor.clip, "standing");
  Object.assign(actor, { jumpAnim: false, jumping: false, landed: true, standing: true, crouched: false });
  actor.falling = false;
}

// A character walking off the block they stood on starts to fall
function walkOff(actor) {
  goto(actor.clip, actor.crouched ? "crouchFall" : "falling");
  actor.lastCollision = null;
  actor.jumpHeight = 0;
  actor.falling = true;
}

// A block stops a character moving into its side unless they are above its top minus 15, and a character falling onto
// it lands on it (F4:6811-6878). The test point is 20 px ahead of the feet, toward the block
export function blockCollide(actor) {
  const reach = constant("moveCollBuffer");
  const topBuffer = constant("collTopBuffer");
  for (const block of roomBlocks()) {
    const away = actor.x - block.x;
    if (Math.abs(away) > block.box.w / 2 + reach) {
      continue;
    }
    const top = block.y - block.box.h;
    if (!inside(block.box, actor.x + (away > 0 ? -BLOCK_REACH : BLOCK_REACH), actor.y)) {
      if (actor.lastCollision === block.name && !actor.climbing && !actor.jumping) {
        walkOff(actor);
      }
      continue;
    }
    actor.lastCollision = block.name;
    if (actor.y > top) {
      actor.collideLeft ||= away > 0;
      actor.collideRight ||= away < 0;
    }
    if (actor.y < top + topBuffer) {
      if (actor.falling) {
        landOnBlock(actor);
      }
      actor.collideLeft = false;
      actor.collideRight = false;
    }
  }
}

function collisions() {
  if (world.player !== player || !player.rig) {
    return;
  }
  enemyCollide();
  blockCollide(player);
  placeClip();
}

// The rig stands where the player is
function placeClip() {
  if (player.clip && !player.clip.destroyed) {
    player.clip.x = player.x;
    player.clip.y = player.y;
  }
}

// ---------- Entering a room ----------

// A story's first room: the key locks start open and stamina starts full
function startStory() {
  Object.assign(locks, { up: false, down: false, sprint: false });
  Object.assign(before, { left: false, right: false, crouch: false, up: false, sprint: false });
  sprintCount = 0;
  player.overweight = false;
  player.stamAlert = false;
  player.stamRegenCount = constant("stamRegenDelay");
  resetRegenTimer();
  lowestPercent = 100;
  heartCount = 0;
  if (!story.player.staminaMax) {
    story.player.staminaMax = staminaMaxOf(story.player);
    story.player.stamina = story.player.staminaMax;
  }
  showHealth();
}

// Each room attaches the player again, dressed from the story, on the floor at the arrival place, facing into the
// room (setupPlayer F4:11823)
function buildPlayer() {
  if (!world.active || !story.player) {
    return;
  }
  if (world.player !== player) {
    startStory();
    world.player = player;
  }
  recalcStats();
  standUp();
  const made = makeHuman(storyLook());
  player.clip = null;
  made.bind(player);
  player.clip = made.clip;
  player.x = room.arrivalX;
  player.y = room.floorY;
  face(room.arrivalX > FACE_LEFT_PAST ? -1 : 1);
  layers.actors.addChild(made.clip);
  placeClip();
}

// ---------- Setup and checks ----------

export function initPlayer(owner) {
  page = owner;
  world.stage("controls", controls);
  world.stage("gravity", gravity);
  world.stage("collisions", collisions);
  world.stage("quick", regenHealth);
  world.stage("quick", regenStamina);
  world.stage("medium", heartbeat);
  world.stage("medium", levelUpCheck);
  world.onMinute(degradeVitals);
  onRoom("build", buildPlayer);
  onRigCall("idlePlayerPosition", idleCall);
  page.steppers.push(placeClip);
}

// Helpers for page.py checks
export const playerDebug = {
  // Sets skills and attributes by name ({ fitness: 100, strength: 10 }), then the numbers that follow from them
  stats(values) {
    for (const [name, value] of Object.entries(values)) {
      if (name in story.player.attributes) {
        story.player.attributes[name] = value;
      } else {
        story.player.skills[name] = value;
      }
    }
    recalcStats();
    return playerDebug.player();
  },

  // Adds XP as a quest reward would and takes the player up the levels it pays for. Returns the level and what is left
  xp(n) {
    addXP(n);
    levelUpCheck();
    const { level, xp, levelXP, points } = story.player;
    return { level, xp, levelXP, points: { ...points } };
  },

  // Sets hunger, sleep, health and permanent health (any of them), then reads back what follows from them
  vitals(values = {}) {
    for (const name of ["hunger", "sleep", "health", "permHealth"]) {
      if (name in values) {
        story.player[name] = values[name];
      }
    }
    showHealth();
    const who = story.player;
    const penalties = Object.fromEntries(Object.keys(PENALTY_VITAL).map((name) => [name, penalty(name)]));
    return {
      hunger: who.hunger,
      sleep: who.sleep,
      states: { hunger: vitalState("hunger").name, sleep: vitalState("sleep").name },
      penalties,
      health: who.health,
      permHealth: who.permHealth,
      healthMax: who.healthMax,
      healthPercent: healthPercent(),
      lowHealth: player.lowHealth,
      stamina: who.stamina,
      staminaMax: who.staminaMax,
      staminaRegen: staminaRegenRate(),
      regenTimer: player.regenTimer,
      edges: { ...hud.edges },
    };
  },

  // A hit of that much damage on the player
  damage(n) {
    return damagePlayer(n);
  },

  face,

  // Whether a panel would be refused now (held by a zombie), with its alert
  refuseOpen,

  // The player's movement state
  player() {
    const fields = ["x", "y", "facing", "dir", "currentSpeed", "jumpHeight", "jumpHeightBase", "fitnessMoveBonus"];
    const flags = ["crouched", "standing", "jumping", "falling", "moving", "sprinting", "overweight", "controlsLocked"];
    flags.push("grabbed", "struggling", "shoving");
    const state = Object.fromEntries([...fields, ...flags].map((name) => [name, player[name]]));
    return { ...state, stamina: player.stamina, staminaMax: player.staminaMax, frame: player.clip?.frame };
  },
};
