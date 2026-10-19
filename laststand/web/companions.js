// The people who come along: a companion (Hank with his Hunter Compact, or Kelly with her kitchen knife, one at a time,
// both quest rewards) and the partner (the quest 915 reward). Each is an actor (spec 5 B) of side "friend" built with
// makeHuman, dressed as the person's NPC is, and placed again in every room near where the player arrives
// (setupSurvivor F4:4682). Which ones are along lives in the story: story.player.follower (the companion's NPC key)
// and story.player.partner, and the companion's weapons in story.companionWeapons (the original's compPrimaryWeapon,
// compSecondaryWeapon, compCurrentWeapon and compStoredWeapon).
//
// A companion's step (survivorAIRoutine F4:4881) looks over everyone in the room for alerted zombies and hostile
// humans and takes the nearest: a gun attacks within 400 px, a melee weapon chases until it is within 80 px. An
// attack aims for 40 steps, then pulls the trigger whenever the weapon is ready for 50 steps and starts over; a
// target within 60 px of a gun gets a shove; straying 400 px from the player walks it back. With nobody to fight it
// follows the player, sprinting when they sprint or when it is 300 px behind. Its own skills (30 in everything), its
// own crouch and its own shot count steer its aim; it never runs out of rounds.
//
// Its health is half the player's and its down-health the player's max x4 (F4:4728-4730). At 0 health, from a bite
// or a bullet, it goes down and cries for help; while down, hits come off the down-health, and at 0 it dies, drops
// its weapon and is gone. G next to a down companion helps it up to full health and down-health; G next to a
// standing one swaps the weapon in the player's hands for theirs. Leaving the room with it down loses it.
//
// The partner follows, never fights, never dies, and zombies leave it alone. The story's triggers and cutscenes send
// it away at the docks and bring it back for the breakout (joinPartner, leavePartner).
import { onCombat } from "./combat.js";
import { originOf } from "./collide.js";
import { data } from "./data.js";
import { dropItem } from "./drops.js";
import { hud } from "./hud.js";
import { humanGravity } from "./humans.js";
import { input } from "./input.js";
import { blockCollide, player, roomBlocks } from "./player.js";
import { goto, gotoPlay, makeHuman, onRigCall, partAt } from "./rig.js";
import { rng } from "./rng.js";
import { layers, onRoom, room } from "./rooms.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { addRow, story } from "./story.js";
import { aimWeapon, characterShove, showPose, swapTo, swing, weaponOf } from "./weapons.js";
import { world } from "./world.js";

// Used until the converted constants load (F4:26111-26126, 26292, 36300-36302)
const DEFAULTS = {
  survivorRange: 400,
  survivorMeleeRange: 80,
  chainsawRange: 100,
  stayCloseDistance: 400,
  catchUpDistance: 300,
  wpSetCountMax: 35,
  survivorHelpSoundChance: 30,
  compInteractRange: 100,
  compIndDist: 530,
  runSpeedMod: 1.5,
  companionWeaponSkill: 30,
  chestHeadOffset: 10,
  jumpHeightBase: 11,
  depth_world_survivor: 115100,
  depth_world_player: 115000,
};
// The steps an attack aims before the trigger, and the steps the trigger cycle lasts (F4:5013-5056)
const AIM_STEPS = 40;
const BURST_STEPS = 50;
// A gun's target this close gets a shove (F4:5052-5055)
const SHOVE_RANGE = 60;
// Each companion's walking point sits 50 px further along than the one before it in the list
const SPACING = 50;
// A follower jumps only over a block lower than this (F4:5226)
const LOW_BLOCK = 200;
// The arms' hand-over runs from its label to the frame that calls giveWeapon, 6 frames on (S4911 frames 18-24)
const HANDOFF_FRAMES = 6;
// The cry for help waits 3 seconds before another may start (F4:4994-4998)
const HELP_QUIET_SECONDS = 3;
// A survivor is placed up to 40 px either side of where the player arrives (F4:4699)
const PLACE_SPREAD = 80;
// The partner walks in 30 px past the player (addPartner F4:16564)
const PARTNER_OFFSET = 30;
// The partner can't be hurt in any way that counts (F4:4733-4735)
const PARTNER_HEALTH = 999999999;
// Survivors are counted up to 10 for their depths, then the count starts over (F4:4684-4688)
const MOST_SURVIVORS = 10;
// The player faces into the room past this x, and so does a survivor (F4:4714)
const FACE_LEFT_PAST = 100;
const FAR = 9999999;
// The aim points at a zombie's chest, a riot zombie's legs, a helmetless riot zombie's head and a crawler's legs, each
// 10 px higher except the riot zombies' (aimWeapon F4:12750-12769)
const AIM_PARTS = {
  zombieRiotShield: ["collisionLegs", false],
  zombieRiot: ["collisionLegs", false],
  zombieRiotNoHelmet: ["collisionHead", false],
  zombieCrawl: ["collisionLegs", true],
};
const DEFAULT_AIM = ["collisionChest", true];
// The dialogs the original shows (F4:20207-20238), for the dialog panel to draw
const REPLACE_DIALOG = {
  heading: "NEW COMPANION?",
  body: "WOULD YOU LIKE TO REPLACE\nYOUR CURRENT COMPANION WITH\nTHIS PERSON?",
  yes: "YES",
  no: "NO",
};
const DOWN_DIALOG = {
  heading: "COMPANION DOWN!",
  body: "YOUR COMPANION NEEDS RESCUING.\nLEAVING THEM WILL RESULT\nIN THEIR DEATH.",
  ok: "OK",
};
const MOST_LOGGED = 300;

let page = null;
let numSurvivors = 0;
let helpSoundPlaying = false;
// The player is in the middle of handing over a weapon or helping a companion up
let givingWeapon = false;
let helpingCompanion = false;
// The companion the player is near, from the last range check (currentCompanion F4:16618)
let currentCompanion = null;
// Counters (achievement keys) and who hears of each
const tally = {};
const countListeners = [];
const partnerListeners = [];

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
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

function log(entry) {
  companions.fireLog.push({ ...entry, frame: world.frame });
  if (companions.fireLog.length > MOST_LOGGED) {
    companions.fireLog.shift();
  }
}

// ---------- Who they are ----------

// A value the NPC table keeps per player sex ({ m, f }) as it reads for this player
function bySex(value) {
  if (value && typeof value === "object") {
    return story.player?.sex === "female" ? value.f : value.m;
  }
  return value;
}

function npcDef(key) {
  return data.story?.npcs?.[key];
}

// The head and clothes of the person's NPC (F4:4823-4848), for a companion and for the NPC standing in a room. The
// partner has the player's skin
export function dressOf(key) {
  const def = npcDef(key) ?? {};
  const dress = def.dress ?? {};
  const look = {
    sex: bySex(def.sex),
    skin: def.skinFromPlayer ? story.player?.look?.skin : dress.skinColour,
    hairColour: dress.hairColour,
    hair: bySex(dress.hair),
    facialHair: bySex(dress.facialHair),
  };
  const clothes = {
    top: bySex(dress.clothesTop),
    bottom: bySex(dress.clothesBottom),
    shoes: bySex(dress.clothesShoe),
    torso: bySex(dress.torsoAccessory),
    head: bySex(dress.headAccessory),
    face: bySex(dress.faceAccessory),
  };
  return { look, clothes, backpack: dress.backpack !== false, weapon: dress.weapon };
}

// A companion's own skills: every skill at 30, the level the original gives companions (F4:26702), with no
// attributes to add to them
function ownStats() {
  const level = constant("companionWeaponSkill");
  const skills = Object.fromEntries(Object.keys(data.actors?.skills ?? {}).map((name) => [name, level]));
  const attributes = Object.fromEntries((data.actors?.lists?.allAttributes ?? []).map((name) => [name, 0]));
  return { skills, attributes };
}

// The companion's weapons (F4:4793-4812): the saved pair only when both slots were saved (a companion that never
// took a spare saves none, so the next one starts with its own weapon), the saved weapon in hand whenever there is
// one, or the NPC's own weapon in hand and nothing spare
function weaponsOf(key) {
  const saved = story.companionWeapons;
  const own = dressOf(key).weapon;
  const pair = saved?.primary != null && saved?.secondary != null;
  return {
    primary: pair ? saved.primary : own,
    secondary: pair ? saved.secondary : null,
    current: saved?.current ?? own,
    stored: saved?.stored ?? "none",
  };
}

// The companion's weapons go into the story (saveCompanion F4:5240)
function saveCompanion(companion) {
  story.companionWeapons = {
    primary: companion.primaryWeapon,
    secondary: companion.secondaryWeapon,
    current: companion.weapon,
    stored: companion.storedWeapon,
  };
}

// ---------- Setup ----------

function withinEdges(x) {
  return Math.min(room.edges.right, Math.max(room.edges.left, x));
}

// The flags a survivor starts with (setupSurvivor F4:4724-4795): health half the player's, down-health the player's
// max x4, and the partner's beyond reach
function makeActor(name, key, x) {
  const vitals = story.player ?? { health: 1, healthMax: 1 };
  const partner = name === "partner";
  const health = partner ? PARTNER_HEALTH : Math.round(vitals.health / 2);
  const healthMax = partner ? PARTNER_HEALTH : Math.round(vitals.healthMax / 2);
  const downHealth = Math.round(vitals.healthMax * 4);
  const actor = { kind: partner ? "partner" : "companion", name, key, side: "friend", ...ownStats() };
  Object.assign(actor, { health, healthMax, lastHealth: health, downHealth, downHealthMax: downHealth });
  Object.assign(actor, { companion: true, survivor: true, partner, alive: true, down: false, state: "follow" });
  Object.assign(actor, { x, y: room.floorY, facing: 1, sex: npcDef(key) ? bySex(npcDef(key).sex) : "male" });
  Object.assign(actor, { wp: world.player?.x ?? x, wpSet: false, wpReached: false, wpSetCount: 0 });
  Object.assign(actor, { shotCount: 0, burstCount: 0, waitCount: 0, curTarget: null, closeZom: FAR });
  Object.assign(actor, { crouched: false, standing: true, moving: false, jumping: false, falling: false });
  Object.assign(actor, { landed: true, jumpAnim: false, walkForwardAnim: false, walkBackwardAnim: false });
  const jump = player.jumpHeightBase ?? constant("jumpHeightBase");
  Object.assign(actor, { jumpHeight: jump, jumpHeightBase: jump, aimLocked: false, controlsLocked: false });
  Object.assign(actor, { firing: false, firingAnim: false, reloading: false, shoving: false, meleeSwing: false });
  Object.assign(actor, { collideLeft: false, collideRight: false, climbing: false, lastCollision: null });
  Object.assign(actor, { transitioning: false, animating: false, grabbed: false, struggling: false });
  return actor;
}

function armActor(actor) {
  if (actor.partner) {
    Object.assign(actor, { weapon: "hands", primaryWeapon: "hands", secondaryWeapon: null, storedWeapon: "hands" });
    return;
  }
  const weapons = weaponsOf(actor.key);
  actor.primaryWeapon = weapons.primary;
  actor.secondaryWeapon = weapons.secondary;
  actor.weapon = weapons.current;
  actor.storedWeapon = weapons.stored;
}

// A weapon ref the rig can show: "none" and empty ones are bare hands
function shownRef(ref) {
  return ref && ref !== "none" && data.items?.weapons?.[ref] ? ref : "hands";
}

function placeClip(actor) {
  if (actor.clip && !actor.clip.destroyed) {
    actor.clip.x = actor.x;
    actor.clip.y = actor.y;
  }
}

// A survivor joins the room: "follower" (the companion) or "partner". Without x it stands up to 40 px either side of
// where the player arrived, kept inside the room's edges; it faces left when the player came in past x 100
// (setupSurvivor F4:4682-4723). Returns the actor
function setupSurvivor(name, x = null) {
  numSurvivors = numSurvivors > MOST_SURVIVORS ? 1 : numSurvivors + 1;
  const key = name === "partner" ? story.player.partner : story.player.follower;
  const startX = x ?? withinEdges(room.arrivalX + (rng.random(PLACE_SPREAD) - PLACE_SPREAD / 2));
  const actor = makeActor(name, key, startX);
  armActor(actor);
  const dress = dressOf(key);
  const made = makeHuman({
    sex: actor.sex,
    look: dress.look,
    clothes: dress.clothes,
    weapon: shownRef(actor.weapon),
    stored: shownRef(actor.storedWeapon),
    backpack: dress.backpack,
  });
  made.bind(actor);
  actor.facing = room.arrivalX > FACE_LEFT_PAST ? -1 : 1;
  made.setFacing(actor.facing);
  goto(made.clip, "standing");
  made.clip.zIndex = constant("depth_world_survivor") - constant("depth_world_player") + numSurvivors;
  layers.actors.addChild(made.clip);
  placeClip(actor);
  actor.charHeight = made.clip.height;
  world.companions.push(actor);
  if (!actor.partner) {
    saveCompanion(actor);
  }
  return actor;
}

// The companion now in the room, or null
function follower() {
  return world.companions.find((each) => !each.partner && each.alive === true) ?? null;
}

function partnerActor() {
  return world.companions.find((each) => each.partner) ?? null;
}

// Each room places the companion and the partner again (checkCompanionSetup F4:4668). The partner's placement is
// what sets off trigger 32 (F4:4678), so whoever runs the triggers hears of each one
function placeSurvivors() {
  world.companions.length = 0;
  currentCompanion = null;
  companions.near = null;
  givingWeapon = false;
  helpingCompanion = false;
  if (!world.active || !story.player) {
    return;
  }
  if (story.player.follower) {
    setupSurvivor("follower");
  }
  if (story.player.partner) {
    setupSurvivor("partner");
    for (const fn of partnerListeners) {
      try {
        fn(partnerActor());
      } catch (e) {
        console.warn("Union City: a partner listener failed", e);
      }
    }
  }
}

// Leaving a room with the companion down loses them (changeRooms F4:14469-14473)
function leaveRoom() {
  companions.downAck = false;
  const companion = world.companions.find((each) => !each.partner);
  if (companion?.down === true && companion.alive === true) {
    removeCompanion();
  }
}

// The NPC who joins leaves the room's people and is switched off for good (F4:16582-16586)
function switchOffNPC(key) {
  const index = world.npcs.findIndex((each) => each.key === key);
  let x = null;
  if (index >= 0) {
    const npc = world.npcs[index];
    x = npc.x ?? null;
    npc.clip?.destroy({ children: true });
    world.npcs.splice(index, 1);
  }
  story.npcs ??= {};
  story.npcs[key] = { ...story.npcs[key], state: "off" };
  return x;
}

// ---------- Joining and leaving ----------

// Hank or Kelly joins at their NPC's place (addCompanion F4:16573). With a companion already along, the player is asked
// first: the answer goes to answerReplace. Returns "joined" or "ask"
export function addCompanion(key) {
  if (!story.player) {
    return null;
  }
  if (story.player.follower) {
    companions.question = { kind: "replace", key, ...REPLACE_DIALOG };
    return "ask";
  }
  count("companion");
  story.player.follower = key;
  const x = switchOffNPC(key);
  setupSurvivor("follower", x === null ? null : withinEdges(x));
  savePoint("companion");
  return "joined";
}

// The answer to "NEW COMPANION?": yes lets the current one go and the new one join (F4:20228-20237)
export function answerReplace(yes) {
  const asked = companions.question;
  companions.question = null;
  if (!yes || asked?.kind !== "replace") {
    return null;
  }
  removeCompanion();
  return addCompanion(asked.key);
}

// The companion leaves the story (removeCompanion F4:16596): off the room's list, their NPC switched off for good.
// A dead one's body stays where it fell; anyone else's clip goes
export function removeCompanion({ keepBody = false } = {}) {
  const key = story.player?.follower;
  stopHelping();
  for (const companion of world.companions.filter((each) => !each.partner)) {
    world.companions.splice(world.companions.indexOf(companion), 1);
    if (!keepBody) {
      companion.clip?.destroy({ children: true });
    }
    if (currentCompanion === companion) {
      currentCompanion = null;
      companions.near = null;
    }
  }
  if (!key) {
    return;
  }
  switchOffNPC(key);
  story.player.follower = null;
  savePoint("companion");
}

// The partner joins, 30 px past the player (addPartner F4:16561). key is the partner's NPC key
function joinPartner(key = "Partner") {
  if (!story.player) {
    return null;
  }
  story.player.partner = key;
  switchOffNPC(key);
  const x = withinEdges((world.player?.x ?? room.arrivalX) + PARTNER_OFFSET);
  return setupSurvivor("partner", x);
}

// The partner leaves (removePartner F4:16610)
function leavePartner() {
  const actor = partnerActor();
  if (actor) {
    world.companions.splice(world.companions.indexOf(actor), 1);
    actor.clip?.destroy({ children: true });
  }
  if (story.player?.partner) {
    switchOffNPC(story.player.partner);
    story.player.partner = null;
    savePoint("companion");
  }
}

export const partner = { joinPartner, leavePartner };

// ---------- Down, dead and back up ----------

// The companion goes down (companionDown F4:4871): the full-body fall with the weapon hidden and the hand open
export function downCompanion(companion) {
  Object.assign(companion, { down: true, state: "down", firing: false, firingAnim: false, reloading: false });
  companion.curTarget = null;
  if (!companion.rig || companion.clip.destroyed) {
    return;
  }
  companion.rig.setAnimMode("full");
  gotoPlay(companion.clip, "survivorDown");
  const held = companion.rig.animWeapon;
  if (held) {
    held.visible = false;
  }
  goto(partAt(companion.clip, "hand_frontAnim"), "openHand");
}

// A man's death cry, now and then the Wilhelm scream; a woman's own (playHumanDeadSound F4:5369)
function deathSound(actor) {
  let name = `sound_humanDead${rng.random(4) + 1}`;
  if (actor.sex === "male") {
    name = rng.random(100) === 0 ? "sound_humanDeadWilhelm" : `sound_humanDead${rng.random(3) + 1}`;
  } else if (actor.sex === "female") {
    name = `sound_humanDeadFemale${rng.random(2) + 1}`;
  }
  sound.play(name, { x: actor.x });
}

// The companion dies (companionDeath F4:16547): the cry, the fall, the weapon dropped where they lay, and they leave
function companionDeath(companion) {
  Object.assign(companion, { alive: false, state: "dead", firing: false, curTarget: null });
  deathSound(companion);
  if (companion.rig && !companion.clip.destroyed) {
    companion.rig.setAnimMode("full");
    const held = companion.rig.animWeapon;
    if (held) {
      held.visible = false;
    }
    gotoPlay(companion.clip, "death_companion");
  }
  if (companion.weapon && companion.weapon !== "hands" && companion.weapon !== "none") {
    dropItem(companion.weapon, companion);
  }
  removeCompanion({ keepBody: true });
}

// A hit that leaves a companion at 0 health (F4:6372-6390): a standing one goes down, a down one loses the hit from
// the down-health and dies when that runs out. Bullets, blasts and bites all count the same
function companionHurt(entry) {
  const companion = entry.target;
  if (companion?.companion !== true || companion.partner || companion.alive !== true) {
    return;
  }
  if (!companion.down) {
    downCompanion(companion);
    return;
  }
  companion.downHealth -= entry.damage ?? 0;
  if (companion.downHealth <= 0) {
    companionDeath(companion);
  }
}

// The player kneels to help the companion up (startHelpCompanion F4:16718). The art calls helpCompanion when done
export function reviveCompanion(companion = currentCompanion) {
  if (helpingCompanion || !companion?.down || !player.rig) {
    return false;
  }
  helpingCompanion = true;
  companions.helping = companion;
  Object.assign(player, { controlsLocked: true, reloading: false, firing: false, firingAnim: false });
  player.rig.setAnimMode("full");
  gotoPlay(player.clip, "helpUp");
  gotoPlay(companion.clip, "survivorUp");
  return true;
}

// The help-up ends (helpCompanion F4:16731), called by the last frame of the companion's survivorUp (S4925 frame 44):
// the player stands (unless a zombie grabbed them meanwhile, Z52), and the companion is up with full health and full
// down-health, following again
function helpCompanion() {
  if (!helpingCompanion) {
    return;
  }
  helpingCompanion = false;
  playerStands();
  const companion = companions.helping;
  companions.helping = null;
  if (!companion || companion.alive !== true) {
    return;
  }
  goto(companion.clip, "standing");
  companion.rig.setAnimMode("upper");
  Object.assign(companion, { down: false, state: "follow", burstCount: 0, waitCount: 0 });
  Object.assign(companion, { firingAnim: false, firing: false, reloading: false });
  companion.health = companion.healthMax;
  companion.downHealth = companion.downHealthMax;
}

// The player gets up from helping: the controls back and the standing pose (helpCompanion F4:16734-16736). A player
// who died or was grabbed meanwhile keeps that pose, and the struggle gives the controls back as it ends
function playerStands() {
  if (player.alive !== true || player.struggling === true) {
    return;
  }
  player.controlsLocked = false;
  player.rig?.setAnimMode("upper");
  goto(player.clip, "standing");
}

// The companion being helped up died or left, so their survivorUp never reaches the frame that calls helpCompanion:
// the help-up is called off and the player stands
function stopHelping() {
  if (!helpingCompanion) {
    return;
  }
  helpingCompanion = false;
  companions.helping = null;
  playerStands();
}

// ---------- The Hand Off ----------

// Both raise their weapons to hand over (startGiveWeapon F4:16650). The player's arms call giveWeapon when they meet
export function swapWithCompanion(companion = currentCompanion) {
  if (givingWeapon || !companion || companion.down || !player.rig || !companion.rig) {
    return false;
  }
  givingWeapon = true;
  companions.giving = companion;
  Object.assign(player, { reloading: false, firing: false, firingAnim: false });
  gotoPlay(companion.rig.arms, "handWeapon");
  gotoPlay(player.rig.arms, "handWeapon");
  return true;
}

// Whether arms are in the hand-over, up to and on the frame that hands the weapon across
function handingOver(arms) {
  const start = arms?.frameOf("handWeapon");
  return Boolean(start) && arms.frame >= start && arms.frame <= start + HANDOFF_FRAMES;
}

// A hand-over whose arms were taken for something else first (a swap, a reload, a shove, a shot) never reaches the
// frame that calls giveWeapon: it is called off, so G works again, and the companion lowers their hands
function watchHandoff() {
  if (!givingWeapon || handingOver(player.rig?.arms)) {
    return;
  }
  const companion = companions.giving;
  givingWeapon = false;
  companions.giving = null;
  if (companion?.rig && !companion.clip.destroyed && handingOver(companion.rig.arms)) {
    companion.rig.returnWeapon();
  }
}

// The player's row for the weapon in their hands, gone from the backpack (F4:16667-16674)
function takeHeldRow(ref) {
  const slot = story.player.holding;
  const index = story.inventory.findIndex((row) => row.eqd && row.ref === ref && row.slot === slot);
  if (index >= 0) {
    story.inventory.splice(index, 1);
  }
}

// The weapons change hands (giveWeapon F4:16660-16716): the companion takes the player's weapon with nothing spare,
// and the companion's weapon goes into the backpack, equipped in the slot the player was holding
function giveWeapon({ owner }) {
  const companion = companions.giving;
  if (owner !== player || !companion || !story.player) {
    givingWeapon = false;
    return;
  }
  count("swapWeaponComp");
  const theirs = companion.weapon;
  const slot = story.player.holding;
  const mine = story.player.slots[slot];
  Object.assign(companion, { weapon: mine, primaryWeapon: mine, secondaryWeapon: "none", storedWeapon: "none" });
  Object.assign(companion, { shotCount: 0, firing: false, firingAnim: false, reloading: false });
  companion.rig.setWeapon(shownRef(mine), { stored: "hands" });
  saveCompanion(companion);
  takeHeldRow(mine);
  const given = shownRef(theirs);
  if (given !== "hands") {
    const row = addRow(given);
    Object.assign(row, { eqd: true, slot });
    hud.alert(`GOT ${data.items.weapons[given].name.toUpperCase()}`, "white");
  }
  story.player.slots[slot] = given;
  swapTo(slot);
  log({ name: companion.name, key: companion.key, kind: "handoff", gave: mine, got: given });
  givingWeapon = false;
  companions.giving = null;
}

// ---------- Range and the indicator ----------

// The companion within reach of G (compRangeCheck F4:16618): the prompt to swap weapons with a standing one, or to
// save a down one. The partner is never one
function rangeCheck() {
  const reach = constant("compInteractRange");
  const near = world.companions.find(
    (each) => !each.partner && each.alive === true && world.player && Math.abs(each.x - world.player.x) < reach,
  );
  currentCompanion = near ?? null;
  if (!near) {
    companions.near = null;
    return;
  }
  const name = String(story.player?.follower ?? near.key ?? "").toUpperCase();
  companions.near = { companion: near, text: near.down ? `[G] SAVE ${name}` : "[G] SWAP WEAPONS" };
}

// What the G prompt shows now, or null with nobody in reach: { companion, text }
export function companionNear() {
  return companions.near;
}

// The arrow at the screen's edge toward a companion more than 530 px away, red while they are down
// (companionIndicator F4:16750). The HUD draws it from companions.indicator
function indicator() {
  const companion = follower();
  const shown = Boolean(companion && world.player) && Math.abs(world.player.x - companion.x) > constant("compIndDist");
  companions.indicator = {
    visible: shown,
    side: shown && world.player.x > companion.x ? "left" : "right",
    down: shown && companion.down === true,
  };
}

// G pressed (F4:18512-18523): next to a standing companion the weapons change hands, next to a down one the player
// helps them up
function gKey(pressed) {
  const companion = currentCompanion;
  if (!pressed || player.alive !== true || givingWeapon || companion?.alive !== true) {
    return;
  }
  if (companion.down) {
    reviveCompanion(companion);
  } else {
    swapWithCompanion(companion);
  }
}

// ---------- Choosing a target ----------

function weaponClass(companion) {
  return weaponOf(companion).weaponClass;
}

function pick(companion, other, dist, state) {
  companion.closeZom = dist;
  companion.curTarget = other;
  companion.state = state;
}

// A weapon type with its own reach (the chainsaw): attack within it, chase beyond, and chase a target that is already
// out of it (F4:4933-4967)
function typeReach(companion, other, dist, current) {
  const type = weaponOf(companion).weaponType;
  if (type !== "chainsaw") {
    return;
  }
  const reach = constant("chainsawRange");
  if (dist < companion.closeZom) {
    pick(companion, other, dist, dist <= reach ? "attack" : "chase");
  }
  if (current > reach) {
    companion.state = "chase";
  }
}

// One alerted enemy the look found (F4:4911-4967): someone nearer than any picked since the target was last lost
// becomes the target. A gun attacks within 400 px; a melee weapon attacks within 80 px and chases beyond, and chases
// a target already out of reach
function weigh(companion, other, current) {
  const dist = Math.abs(companion.x - other.x);
  const melee = constant("survivorMeleeRange");
  const kind = weaponClass(companion);
  if (kind === "firearm" && dist < companion.closeZom && dist <= constant("survivorRange")) {
    pick(companion, other, dist, "attack");
  }
  if (kind === "melee") {
    if (dist < companion.closeZom) {
      pick(companion, other, dist, dist > melee ? "chase" : "attack");
    }
    if (current > melee) {
      companion.state = "chase";
    }
  }
  typeReach(companion, other, dist, current);
}

function isEnemy(other) {
  if (other === player || other.companion === true) {
    return false;
  }
  return other.zombie === true || other.side === "zombie" || (other.humanEnemy === true && other.friendly !== true);
}

// The companion looks over everyone in the room every step for alerted enemies (F4:4895-4970)
function scan(companion) {
  const current = companion.curTarget ? Math.abs(companion.x - companion.curTarget.x) : NaN;
  for (const other of [...world.humans, ...world.zombies]) {
    if (other.alive === true && other.alerted === true && isEnemy(other)) {
      weigh(companion, other, current);
    }
  }
}

// ---------- Aiming and the trigger ----------

function chestOf(actor, path, lift) {
  const node = partAt(actor.clip, path);
  if (!node) {
    return { x: actor.x, y: actor.y };
  }
  const point = originOf(node);
  return { x: point.x, y: point.y - (lift ? constant("chestHeadOffset") : 0) };
}

// Where the arm points (aimWeapon F4:12748-12781): at the target's chest or the part its kind calls for, or, with no
// target, at the player's chest, as the original aims anyone who is not a friendly guard
function aimAt(companion) {
  const target = companion.curTarget;
  if (target?.alive === true && target.clip && partAt(target.clip, "collisionHead")) {
    const [path, lift] = AIM_PARTS[target.type] ?? DEFAULT_AIM;
    companion.aimTarget = chestOf(target, path, lift);
  } else if (world.player?.clip && !world.player.clip.destroyed) {
    companion.aimTarget = chestOf(world.player, DEFAULT_AIM[0], true);
  }
  aimWeapon(companion);
}

// The trigger (F4:5022-5048): a gun plays its fire until the magazine's worth of shots is out, then reloads; a melee
// weapon swings
function pullTrigger(companion) {
  const weapon = weaponOf(companion);
  if (weapon.weaponClass === "melee") {
    swing(companion, weapon);
    log({ name: companion.name, key: companion.key, kind: "swing", target: companion.curTarget?.name });
    return;
  }
  if (companion.shotCount < (weapon.maxAmmo ?? 0)) {
    companion.firing = true;
    gotoPlay(companion.rig.arms, `${weapon.weaponType}_fire`);
    companion.shotCount += 1;
    log({ name: companion.name, key: companion.key, kind: "fire", target: companion.curTarget?.name });
    return;
  }
  companion.shotCount = 0;
  companion.reloading = true;
  companion.reloadCount = 0;
  gotoPlay(companion.rig.arms, `${weapon.reloadClip ?? weapon.weaponType}_reload`);
  log({ name: companion.name, key: companion.key, kind: "reload" });
}

// After the aim, the trigger is pulled whenever the weapon is ready for 50 steps, standing still in the upper-body
// pose, then the cycle starts over (F4:5013-5050)
function burst(companion) {
  companion.burstCount += 1;
  if (companion.burstCount <= BURST_STEPS && !companion.firingAnim && !companion.reloading) {
    companion.rig.setAnimMode("upper");
    goto(companion.clip, "standing");
    companion.walkForwardAnim = false;
    pullTrigger(companion);
  }
  if (companion.burstCount > BURST_STEPS) {
    companion.burstCount = 0;
    companion.waitCount = 0;
    companion.firing = false;
  }
}

// ---------- Walking ----------

// A new walking point every so often, while none is set (F4:5060-5068, 5117-5126, 5167-5176)
function setWaypoint(companion, odds, x) {
  const most = constant("wpSetCountMax");
  companion.wpSetCount -= 1;
  if (companion.wpSetCount > rng.random(Math.floor(most / odds))) {
    return;
  }
  companion.wpSetCount = most;
  if (!companion.wpSet && x !== null) {
    aimAt(companion);
    companion.wpReached = false;
    companion.wpSet = true;
    companion.wp = x;
  }
}

function stand(companion) {
  companion.wpReached = true;
  companion.wpSet = false;
  companion.wp = null;
  companion.walkForwardAnim = false;
  goto(companion.clip, "standing");
}

// A step toward the walking point at the player's speed, walking backward when facing away (F4:5069-5099). A block in
// the way makes it jump
function stepToward(companion, speed, backward) {
  const wp = companion.wp;
  if (wp === null || wp === undefined) {
    return;
  }
  const right = companion.x < wp && !companion.collideLeft;
  const left = companion.x > wp && !companion.collideRight;
  if (right || left) {
    if (!companion.walkForwardAnim) {
      companion.walkForwardAnim = true;
      gotoPlay(companion.clip, "walk");
    }
    const away = right ? companion.facing < 0 : companion.facing > 0;
    if (backward && away && !companion.walkBackwardAnim) {
      companion.walkBackwardAnim = true;
      gotoPlay(companion.clip, "walkBackward");
    }
    companion.x = withinEdges(companion.x + (right ? speed : -speed));
  }
}

// Too far from the player in a fight: walk back to them and fight from there (F4:5058-5113)
function stayClose(companion, index) {
  setWaypoint(companion, 20, world.player.x + Math.round(SPACING * index));
  stepToward(companion, player.speed, true);
  if (companion.collideLeft || companion.collideRight) {
    companion.jumping = true;
  }
  if (companion.wp !== null && Math.abs(companion.x - companion.wp) <= constant("survivorMeleeRange")) {
    if (!companion.wpReached) {
      stand(companion);
      companion.state = "attack";
    }
  }
}

// ---------- States ----------

// Down: now and then a cry for help, never two at once (F4:4989-5000)
function downState(companion) {
  if (rng.random(constant("survivorHelpSoundChance")) !== 0 || helpSoundPlaying) {
    return;
  }
  helpSoundPlaying = true;
  const count = companion.sex === "female" ? 3 : 4;
  sound.play(`sound_survivorHelp_${companion.sex}${rng.random(count) + 1}`, { x: companion.x });
  companions.cries += 1;
  world.later(HELP_QUIET_SECONDS * page.lib.fps, () => {
    helpSoundPlaying = false;
  });
}

// Attack (F4:5007-5114): aim every step, the trigger cycle after 40 steps, a shove for a gun's target within 60 px,
// and a walk back toward a player who got 400 px away
function attack(companion, index) {
  companion.waitCount += 1;
  aimAt(companion);
  if (companion.waitCount >= AIM_STEPS) {
    burst(companion);
  }
  const target = companion.curTarget;
  if (weaponClass(companion) === "firearm" && target && Math.abs(companion.x - target.x) < SHOVE_RANGE) {
    companion.state = "shove";
  }
  if (world.player && Math.abs(companion.x - world.player.x) > constant("stayCloseDistance")) {
    stayClose(companion, index);
  }
}

// Chase (F4:5115-5164): a walking point just past the target; within 80 px of it the companion attacks
function chase(companion, index) {
  const target = companion.curTarget;
  setWaypoint(companion, 20, target ? target.x + Math.round(SPACING * index) : null);
  stepToward(companion, player.speed, false);
  if (companion.collideLeft || companion.collideRight) {
    companion.jumping = true;
  }
  if (companion.wp !== null && Math.abs(companion.x - companion.wp) <= constant("survivorMeleeRange")) {
    if (!companion.wpReached) {
      stand(companion);
      companion.state = "attack";
    }
  }
  if (target?.alive === undefined) {
    companion.state = "follow";
  }
}

// The block the companion last ran into is low enough to jump (F4:5224-5230)
function lowBlock(companion) {
  const block = roomBlocks().find((each) => each.name === companion.lastCollision);
  return !block || block.box.h < LOW_BLOCK;
}

// The follow's walk: a sprint in the full-body pose when the player sprints or is 300 px away, a walk otherwise
// (F4:5177-5222)
function followStep(companion) {
  const wp = companion.wp;
  const right = wp !== null && companion.x < wp && !companion.collideLeft;
  const left = wp !== null && companion.x > wp && !companion.collideRight;
  if (!right && !left) {
    return;
  }
  const sprint = player.sprinting === true || Math.abs(companion.x - world.player.x) > constant("catchUpDistance");
  if (!companion.walkForwardAnim) {
    companion.walkForwardAnim = true;
    if (sprint) {
      companion.rig.setAnimMode("full");
    }
    gotoPlay(companion.clip, sprint ? "sprint" : "walk");
  }
  const speed = sprint ? player.speed * constant("runSpeedMod") : player.speed;
  companion.x = withinEdges(companion.x + (right ? speed : -speed));
}

// Follow (F4:5165-5233): while the player walks, a walking point by them now and then, each companion further back
// than the one before; it stops a little short, back in the upper-body pose
function follow(companion, index) {
  setWaypoint(companion, 3, world.player.moving === true ? world.player.x + Math.round(SPACING * index) : null);
  followStep(companion);
  if ((companion.collideLeft || companion.collideRight) && lowBlock(companion)) {
    companion.jumping = true;
  }
  const near = rng.random(SPACING) + Math.round(index * SPACING);
  if (companion.wp !== null && Math.abs(companion.x - companion.wp) <= near && !companion.wpReached) {
    stand(companion);
    companion.rig.setAnimMode("upper");
  }
}

const STATES = {
  down: downState,
  shove(companion) {
    characterShove(companion);
    companion.state = "attack";
  },
  attack,
  chase,
  follow,
};

// One survivor's step (survivorAIRoutine F4:4889-4986): the partner only follows; a companion looks for a target,
// drops a lost one, and runs its state
function think(companion, index) {
  if (!companion.partner) {
    scan(companion);
  }
  if (companion.curTarget?.alive !== true) {
    companion.state = "follow";
    companion.closeZom = FAR;
    companion.curTarget = null;
    companion.firing = false;
  }
  if (companion.down) {
    companion.state = "down";
  }
  STATES[companion.state]?.(companion, index);
  placeClip(companion);
}

function living() {
  return world.companions.filter((each) => each.alive === true && each.clip && !each.clip.destroyed);
}

function companionAI() {
  if (!world.player) {
    return;
  }
  world.companions.forEach((companion, index) => {
    if (companion.alive === true && companion.rig && !companion.clip.destroyed) {
      think(companion, index);
    }
  });
}

// The room's blocks stop a survivor walking into their sides and catch it falling onto their tops (moveCollisions
// F4:6815-6878)
function companionBlocks() {
  for (const companion of living()) {
    companion.collideLeft = false;
    companion.collideRight = false;
    blockCollide(companion);
  }
}

// The arm, torso and head keep their aim after the timeline moved them, unless the full-body pose is showing
function holdPoses() {
  for (const companion of living()) {
    if (companion.rig.mode === "upper") {
      showPose(companion);
    }
  }
}

export function initCompanions(owner) {
  page = owner;
  onRoom("leave", leaveRoom);
  onRoom("build", placeSurvivors);
  onCombat("down", companionHurt);
  onRigCall("helpCompanion", helpCompanion);
  onRigCall("giveWeapon", giveWeapon);
  world.onReset(() => {
    helpSoundPlaying = false;
    givingWeapon = false;
    helpingCompanion = false;
    currentCompanion = null;
    numSurvivors = 0;
    Object.assign(companions, { near: null, question: null, downAck: false, helping: null, giving: null });
  });
  world.stage("interface", holdPoses);
  world.stage("controls", () => {
    watchHandoff();
    gKey(input.gPressed);
  });
  world.stage("gravity", () => living().forEach(humanGravity));
  world.stage("collisions", companionBlocks);
  world.stage("companions", companionAI);
  world.stage("quick", indicator);
  world.stage("medium", rangeCheck);
  page.steppers.push(() => world.companions.forEach(placeClip));
}

// Registers fn(key, amount) for each counter the companions add to: "companion" when one joins and "swapWeaponComp"
// for a weapon handed over (checkAch F4:16575, 16662)
export function onCompanionCount(fn) {
  countListeners.push(fn);
}

// Registers fn(partner) for each room the partner is placed in, which is what sets off trigger 32 (F4:4678)
export function onPartnerPlaced(fn) {
  partnerListeners.push(fn);
}

export const companions = {
  addCompanion,
  answerReplace,
  removeCompanion,
  downCompanion,
  reviveCompanion,
  swapWithCompanion,
  companionNear,
  partner,
  onCompanionCount,
  onPartnerPlaced,
  tally,
  // The G prompt: { companion, text } for the companion within reach, from the last range check
  near: null,
  // The edge arrow toward a far companion: { visible, side ("left" or "right"), down }
  indicator: { visible: false, side: "right", down: false },
  // A question waiting for the dialog panel: { kind: "replace", key, heading, body, yes, no }
  question: null,
  // The "COMPANION DOWN!" dialog the doors show before leaving with a down companion; downAck is its OK, until the
  // room changes
  downDialog: DOWN_DIALOG,
  downAck: false,
  // Whether a door should stop for the dialog: the companion is down and the player hasn't said OK yet
  leaveWarning() {
    const companion = world.companions.find((each) => !each.partner);
    return companion?.down === true && companion.alive === true && !companions.downAck;
  },
  ackDown() {
    companions.downAck = true;
  },
  helping: null,
  giving: null,
  // Cries for help so far
  cries: 0,
  // { name, key, kind ("fire", "swing", "reload" or "handoff"), frame, target } for each, oldest first
  fireLog: [],
};

// Helpers for page.py checks
export const companionsDebug = {
  addCompanion,
  answerReplace,
  removeCompanion,
  joinPartner,
  leavePartner,
  reviveCompanion,
  swapWithCompanion,

  // Puts the companion down at once, as a hit to 0 health would
  downCompanion(companion = follower()) {
    if (companion) {
      companion.health = 0;
      downCompanion(companion);
    }
    return Boolean(companion);
  },

  // The survivors in the room now
  companionList() {
    return world.companions.map((each) => ({
      name: each.name,
      key: each.key,
      partner: each.partner,
      x: Math.round(each.x),
      y: Math.round(each.y),
      facing: each.facing,
      state: each.state,
      alive: each.alive,
      down: each.down,
      health: each.health,
      healthMax: each.healthMax,
      downHealth: each.downHealth,
      downHealthMax: each.downHealthMax,
      weapon: each.weapon,
      target: each.curTarget?.name ?? each.curTarget?.kind ?? null,
      waitCount: each.waitCount,
      burstCount: each.burstCount,
      shotCount: each.shotCount,
      firingAnim: each.firingAnim,
      reloading: each.reloading,
      jumping: each.jumping,
    }));
  },

  // The trigger pulls and hand-offs since the given world step
  companionFireLog(since = 0) {
    return companions.fireLog.filter((each) => each.frame >= since);
  },
};
