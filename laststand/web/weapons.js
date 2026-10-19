// Aiming: where the arm points, the crosshair that follows the mouse, and how wide a shot can stray (aimWeapon
// F4:12731, the crosshair F4:17790-17852, the spread F4:21443-21463). The arm, head and torso turn together toward the
// target, and the character faces whichever way the arm points. Only the angle matters, so a shot goes the same way
// however far the mouse is.
//
// Rules here work on any actor with a rig (the player, and later the zombies and survivors that shoot): the player
// aims at the mouse, anyone else at the point in their `aimTarget` ({ x, y } in room pixels). The skill, the stance and
// the shots in a row are always the shooter's own.
//
// Firing, reloading and swapping (F4:20885-21662) run on the arms' timeline (sprite 4911): a press starts the weapon
// type's fire animation, the animation calls fireWeapon on the frame a round leaves and loops back while the trigger is
// held, and a reload animation calls reloadWeapon on its last frame. So the fire rate and the reload time of every gun
// are the lengths of its animations, never numbers in the weapon table.
//
// The player's loaded rounds live in the backpack row of the weapon in the hands and the rounds held in story.ammo, as
// the original keeps them in inventory[currentWeaponID].ammo and _root.ammo<type>. Anyone else who shoots (survivors,
// enemies) never runs out, as the original's survivor flag gives them.
import { data } from "./data.js";
import { effects } from "./effects.js";
import { help } from "./help.js";
import { input } from "./input.js";
import { light } from "./light.js";
import { adjustedSkill, face, player, reduceStamina } from "./player.js";
import { goto, gotoPlay, onRigCall, ownerOf, partAt, rigCall, rootFlags, takeOver } from "./rig.js";
import { rng } from "./rng.js";
import { camera, onRoom, toWorld } from "./rooms.js";
import { shots } from "./shots.js";
import { sound } from "./sound.js";
import { addRow, story } from "./story.js";
import { world } from "./world.js";

// The crosshair's clip (sprite 5372): four arms named for the side they sit on
const CROSSHAIR_CHARACTER = 5372;
const CROSSHAIR_ARMS = {
  top: { axis: "y", sign: -1 },
  right: { axis: "x", sign: 1 },
  bottom: { axis: "y", sign: 1 },
  left: { axis: "x", sign: -1 },
};
// An arm slides to its place in half a second, easing out (xSlideTo with no animation type, F4:17846)
const SLIDE_STEPS = 15;
// The crosshair never closes tighter than this gap
const LEAST_GAP = 5;
// The most the arm turns down: 60 degrees facing right, and the same mirrored facing left (F4:12806, 12850)
const MOST_DOWN = 60;
const LEFT_LOWEST = -120;
// Shots in a row that still widen the spread
const CONSEC_CAP = 70;
const SHOULDER_HEIGHT = 0.82;
const CROUCH_DROP = 0.25;
// The arms' sprite and the backpack weapon's (the weapon carried on the back)
const ARMS_SPRITE = 4911;
const BACKPACK_WEAPON_SPRITE = 4799;
// The pistol's loop frame, and the backpack weapon's RPG frame
const PISTOL_LOOP_FRAME = 303;
const BACKPACK_RPG_FRAME = 8;
// Used until the converted constants load
const FIRE_DEFAULTS = {
  autoReload: true,
  knockbackChance: 100,
  showSmokeChance: 2,
  exertSoundChance: 20,
  roundLife: 1400,
  roundLife_chainsaw: 5,
  roundGravity: 4,
  screenShakeDelay: 50,
};
// A screen shake from a shot lasts two pulses (F4:21351)
const SHOT_SHAKE_PULSES = 2;
// Recoil lasts recoil x 5 ms (F4:21390)
const RECOIL_MS = 5;
// Where returnRecoil puts the neck and head across (F4:21673-21676, setupPlayer F4:11902-11904)
const NECK_REST_X = 0;
const HEAD_REST_X = 10;
// A hand grenade leaves 100 px above the arms (F4:21419)
const GRENADE_LIFT = 100;
// Weapon types that throw no casing when they fire: the pump and bolt throw theirs from the animation, the revolver
// when it reloads
const NO_CASING_TYPES = new Set(["pumpAction", "revolver", "boltAction"]);
const MELEE_TYPES = new Set(["oneHand", "twoHand", "fists"]);
// A revolver's reload throws out its spent cases: two for the sawn off, four for the others (S4911 frame 82)
const REVOLVER_CASES = { shotgun: 2 };
const REVOLVER_CASES_DEFAULT = 4;
// The sounds the arms' animation asks for by name (playPumpActionSound and the others, F4:5464-5479)
const WEAPON_SOUNDS = {
  pump: "sound_shotgunPump",
  bolt: "sound_rifle_boltCycle",
  shellload: "sound_shotgunShellLoad",
  bow: "sound_compoundBow_draw",
};
// Extra reload sounds a weapon type plays on top of its own (startReload F4:20901-20908)
const EXTRA_RELOAD_SOUNDS = { boltAction: "sound_assaultRifle_reload", bullpup: "sound_smg_reload" };
// The most reloads kept for a check to read
const MOST_RELOADS = 50;

let page = null;
let crosshairClip = null;
let crosshairLoading = null;
let depth = 0;
let cursorHidden = false;
// Arm name -> the slide it is on: { from, to, step }
const slides = {};
// Whether the player's trigger is down, and whether this press only clicked an empty gun (dryFired, F4:21225)
let triggerDown = false;
let dryFired = false;
// fn(target, shooter, condition, noise) for each enemy a gun's noise may wake (alertedZombie F4:9096)
const noiseListeners = [];
// { weapon, start, end } in world steps for the player's latest reloads, for checks
const reloads = [];
let reloadingBefore = false;

function constant(name) {
  return data.actors?.constants?.[name] ?? FIRE_DEFAULTS[name];
}

function degrees(radians) {
  return (radians * 180) / Math.PI;
}

function radians(value) {
  return (value * Math.PI) / 180;
}

// Flash keeps a clip's _rotation between -180 and 180
function flashRotation(value) {
  let turned = value % 360;
  if (turned > 180) {
    turned -= 360;
  } else if (turned <= -180) {
    turned += 360;
  }
  return turned;
}

// The weapon the actor holds in its hand (the player's comes from the slot in use)
export function weaponOf(actor) {
  const ref = actor.weapon ?? actor.rig?.weapon ?? "hands";
  return data.items?.weapons?.[ref] ?? data.items?.weapons?.hands ?? {};
}

// ---------- Where the arm points ----------

// The point the arm turns from, in room pixels: 82 percent of the way up the character, lower when crouched
export function shoulder(actor) {
  const height = actor.charHeight ?? actor.clip?.height ?? 0;
  const drop = actor.crouched === true ? height * CROUCH_DROP : 0;
  return { x: actor.x, y: actor.y - height * SHOULDER_HEIGHT + drop };
}

// What the actor aims at, in room pixels: the player's mouse, anyone else's chosen target
function targetOf(actor) {
  if (actor === player) {
    return toWorld(input.aim.x, input.aim.y);
  }
  return actor.aimTarget ?? null;
}

// The part of the aim that sets the pose, in Flash's own terms (aimWeapon F4:12791-12872): the arm's turn, the torso's and
// the head's counter turns, the scales that mirror them, and the way the character faces. `before` is the last pose; a
// turn of exactly straight up or down leaves the facing and scales as they were
function poseFor(angle, before) {
  const pose = { ...before };
  let current = Math.round(angle - constant("aimAdjust"));
  if (current === -180) {
    current = -179;
  }
  if (current === -270) {
    current = -269;
  }
  pose.arms = flashRotation(current);
  pose.head = flashRotation(current - 180);
  pose.torso = flashRotation(-current);
  if (pose.arms >= -90 && pose.arms < 90) {
    pose.facing = 1;
    pose.armsScale = 1;
    pose.headScale = -1;
    if (pose.arms > MOST_DOWN) {
      Object.assign(pose, { arms: MOST_DOWN, torso: -MOST_DOWN, head: MOST_DOWN, headScale: 1 });
    }
  }
  if ((pose.arms > 90 && pose.arms < 180) || (pose.arms > -180 && pose.arms < -90)) {
    pose.facing = -1;
    pose.armsScale = -1;
    pose.headScale = -1;
    pose.arms = flashRotation(-current);
    pose.torso = flashRotation(current - 180);
    pose.head = flashRotation(-current);
    if (pose.arms > LEFT_LOWEST && pose.arms < 0) {
      Object.assign(pose, { arms: LEFT_LOWEST, torso: -MOST_DOWN, head: LEFT_LOWEST });
    }
  }
  return pose;
}

// Turns a part. A scale of null leaves the part's own size and shear alone, as the original only sets its _rotation
function setTurn(node, rotation, scale = null) {
  if (!node || node.destroyed) {
    return;
  }
  if (scale !== null) {
    node.skew.set(0, 0);
    node.scale.set(scale, scale);
  }
  node.rotation = radians(rotation);
}

// Turns the arm, torso and head to a pose. The timeline puts them back each time it moves them, so this runs after
// every step that advanced the clips
export function showPose(actor) {
  const { rig, pose } = actor;
  if (!rig || !pose || rig.clip.destroyed) {
    return;
  }
  const arms = rig.arms;
  setTurn(arms, pose.arms, pose.armsScale);
  setTurn(arms?.child("torso"), pose.torso);
  setTurn(rig.clip.child("head"), pose.head, pose.headScale);
}

// The flashlight's beam leaves the arm's flashlight point, along the arm (F4:12879-12893)
function aimBeam(actor) {
  const point = actor.rig?.arms?.child("flashLightPoint");
  if (!point || point.destroyed) {
    return;
  }
  const spot = point.getGlobalPosition();
  const scale = page.root.scale;
  const place = toWorld(spot.x / scale.x, spot.y / scale.y);
  const turn = actor.pose.arms + degrees(point.rotation);
  light.placeBeam(place.x, place.y, actor.facing < 0 ? -turn : turn);
}

// The arm points at the target (aimWeapon F4:12731). The world angle it leaves in is `actor.aimDegrees`, clockwise from
// straight right, which is what a shot leaves along before the spread is added
export function aimWeapon(actor) {
  const target = targetOf(actor);
  if (!actor.rig || !target || actor.aimLocked !== false || actor.alive !== true || actor.controlsLocked) {
    return;
  }
  if (actor === player) {
    crosshairSize(actor);
  }
  const from = shoulder(actor);
  const angle = degrees(Math.atan2(from.y - target.y, from.x - target.x));
  actor.pose = poseFor(angle, actor.pose ?? { arms: 0, torso: 0, head: 0, armsScale: 1, headScale: 1, facing: 1 });
  if (actor.rig.facing !== actor.pose.facing || actor.facing !== actor.pose.facing) {
    if (actor === player) {
      face(actor.pose.facing);
    } else {
      actor.facing = actor.pose.facing;
      actor.rig.setFacing(actor.facing);
    }
  }
  actor.aimDegrees = actor.facing < 0 ? -actor.pose.arms : actor.pose.arms;
  showPose(actor);
  // Only the player carries the flashlight (F4:12877)
  if (actor === player) {
    aimBeam(actor);
  }
}

// The way the arm points in the world, in degrees clockwise from straight right (0 right, 90 down, -90 up)
export function aimAngle(actor) {
  return actor.aimDegrees ?? (actor.facing < 0 ? 180 : 0);
}

// ---------- Spread ----------

// The weapon skill the shot is made with: the shooter's own adjusted skill, a steadier hand crouched, a shakier one
// moving or in the air (F4:27966-27969)
function stanceSkill(actor, weapon) {
  let skill = adjustedSkill(actor, weapon.skill);
  if (actor.crouched === true) {
    skill += constant("crouchBonus");
  }
  if (actor.moving === true) {
    skill -= constant("movingPenalty");
  }
  if (actor.jumping === true) {
    skill -= constant("jumpingPenalty");
  }
  return skill;
}

// How far a shot can stray each way from the arm, in degrees (F4:21443-21463). Never below zero, and only the last 70
// shots in a row count
export function spread(actor) {
  const weapon = weaponOf(actor);
  const skill = stanceSkill(actor, weapon);
  const loose = (Math.max(0, constant("skillMax") - skill) / constant("accuracyModifier")) * (weapon.accuracy ?? 0);
  return loose + Math.min(actor.consecRounds ?? 0, CONSEC_CAP) / constant("consecShotAccuracyAdjust");
}

// How far each crosshair arm stands from the centre (F4:17809): the skill gap times accuracy, and half the shots in a row
function crosshairGap(actor) {
  const weapon = weaponOf(actor);
  const skill = stanceSkill(actor, weapon);
  const base = Math.round((constant("skillMax") - skill) * (weapon.accuracy ?? 0) * constant("crosshairAdjust"));
  return Math.max(LEAST_GAP, base + (actor.consecRounds ?? 0) / constant("consecRoundDiv"));
}

// ---------- The crosshair ----------

// Sends the crosshair's arms toward the gap, and lets the shots in a row cool off a step (setCrosshairScale F4:17812).
// Every step starts the slide again from where the arm is, so each arm closes about a third of the way a step
function crosshairSize(actor) {
  if (actor.firing === false || actor.firing === undefined) {
    actor.consecRounds = Math.max(0, (actor.consecRounds ?? 0) - 1);
  }
  const gap = crosshairGap(actor);
  for (const [name, { axis, sign }] of Object.entries(CROSSHAIR_ARMS)) {
    const arm = crosshairClip?.child(name);
    if (arm) {
      slides[name] = { from: arm[axis], to: sign * gap, step: 0, axis };
    }
  }
}

function easeOutExpo(step) {
  return step >= SLIDE_STEPS ? 1 : 1 - 2 ** ((-10 * step) / SLIDE_STEPS);
}

function slideArms() {
  for (const [name, slide] of Object.entries(slides)) {
    const arm = crosshairClip?.child(name);
    if (!arm || arm.destroyed) {
      continue;
    }
    slide.step = Math.min(SLIDE_STEPS, slide.step + 1);
    arm[slide.axis] = slide.from + (slide.to - slide.from) * easeOutExpo(slide.step);
    if (slide.step >= SLIDE_STEPS) {
      delete slides[name];
    }
  }
}

function inPlay() {
  return world.active && world.player === player && Boolean(story.player);
}

// Whether the crosshair shows: in play, not paused, and not within 50 px of the top or bottom edge, where the
// original's interface sits (interfaceBounds F4:27618)
function crosshairShown() {
  const edge = constant("interfaceBounds");
  const high = input.aim.y < edge || input.aim.y > page.height - edge;
  return inPlay() && !world.paused && !high;
}

function setCursorHidden(hidden) {
  if (hidden !== cursorHidden) {
    cursorHidden = hidden;
    input.cursorShown = !hidden;
  }
}

// The crosshair stands under the mouse, with the system cursor swapped for it
export const crosshair = {
  get clip() {
    return crosshairClip;
  },

  get visible() {
    return Boolean(crosshairClip?.visible);
  },

  // Once a step, paused or not
  update() {
    if (!crosshairClip || crosshairClip.destroyed) {
      return;
    }
    const shown = crosshairShown();
    crosshairClip.visible = shown;
    crosshairClip.x = input.aim.x;
    crosshairClip.y = input.aim.y;
    setCursorHidden(shown);
    slideArms();
  },

  // The playfield is gone (a menu is showing): the system cursor is back
  hide() {
    if (crosshairClip) {
      crosshairClip.visible = false;
    }
    setCursorHidden(false);
  },
};

function makeCrosshair() {
  crosshairLoading ??= page.lib
    .need([CROSSHAIR_CHARACTER])
    .then(() => {
      crosshairClip = page.lib.make(CROSSHAIR_CHARACTER);
      crosshairClip.label = "crosshair";
      crosshairClip.zIndex = depth;
      crosshairClip.eventMode = "none";
      crosshairClip.visible = false;
      page.root.addChild(crosshairClip);
    })
    .catch((e) => console.warn("Union City: the crosshair couldn't be drawn", e));
}

// ---------- Rounds in the gun ----------

// Whether the actor never runs out: everyone but the player, as the original's survivor flag gives companions and
// enemies (F4:4739, 24720)
function endless(actor) {
  return actor !== player || actor.survivor === true;
}

// The backpack row of the player's weapon in a slot ("primary" or "secondary"), or null for bare hands
function slotRow(slot) {
  const ref = story.player?.slots[slot];
  const found = story.inventory?.find(
    (row) => row.eqd && row.type === "weapon" && row.slot === slot && row.ref === ref,
  );
  return found ?? null;
}

function heldRow() {
  return story.player ? slotRow(story.player.holding) : null;
}

function otherSlot(slot) {
  return slot === "primary" ? "secondary" : "primary";
}

// Rounds loaded in the gun in the actor's hands
function loadedOf(actor) {
  return endless(actor) ? Infinity : (heldRow()?.ammo ?? 0);
}

// Rounds held for the gun in the actor's hands
function reserveOf(actor) {
  if (endless(actor)) {
    return Infinity;
  }
  const type = weaponOf(actor).ammoType;
  return type ? (story.ammo?.[type] ?? 0) : 0;
}

// What the HUD's ammo counter shows: the weapon in the player's hands, the rounds loaded in it, and the rounds held for
// it (null for a weapon that takes none)
export function heldAmmo() {
  const weapon = weaponOf(player);
  const type = weapon.ammoType;
  return { weapon, loaded: heldRow()?.ammo ?? 0, reserve: type ? (story.ammo?.[type] ?? 0) : null };
}

// A weapon taken out of a slot gives its loaded rounds back to the rounds held (unEquipWeapon F4:7711)
export function returnRounds(row) {
  const type = data.items?.weapons?.[row?.ref]?.ammoType;
  if (type && row.ammo) {
    story.ammo[type] = (story.ammo[type] ?? 0) + row.ammo;
  }
  if (row) {
    row.ammo = 0;
  }
}

// ---------- Sounds ----------

function soundAt(actor, name) {
  sound.play(name, { x: actor.x });
}

// The shot's sound: a suppressed gun's by its icon, a built copy's by its base model, the others by their own name,
// one of two takes (F4:21357-21369)
function fireSound(actor, weapon) {
  const take = rng.random(2) + 1;
  if (weapon.mod === "suppressed" || weapon.mod === "specOps") {
    soundAt(actor, `sound_${weapon.icon}_suppressed${take}`);
  } else if (weapon.mod) {
    soundAt(actor, `sound_${weapon.weaponBase}_fire${take}`);
  } else {
    soundAt(actor, `sound_${weapon.ref}_fire${take}`);
  }
}

// The grunt of a swing, one time in five (playerExertSound F4:5526)
function exertSound(actor) {
  if (rng.random(101) >= constant("exertSoundChance")) {
    return;
  }
  const sex = actor === player ? story.player?.sex : actor.rig?.sex;
  soundAt(actor, `${sex === "female" ? "sound_playerExert_female" : "sound_playerExert"}${rng.random(3) + 1}`);
}

function isChainsaw(weapon) {
  return weapon.weaponType === "chainsaw";
}

// ---------- Recoil ----------

function recoilParts(actor) {
  return [actor.rig?.arms?.child("torso"), actor.rig?.clip.child("neck"), actor.rig?.clip.child("head")];
}

// Where the torso, neck and head rest, for the recoil to push from and come back to (setupPlayer F4:11900-11905)
function setOrigins(actor) {
  const [torso, neck, head] = recoilParts(actor);
  if (!torso || !neck || !head) {
    return;
  }
  Object.assign(torso, { originX: torso.x, originY: torso.y });
  Object.assign(neck, { originX: NECK_REST_X, originY: neck.y });
  Object.assign(head, { originX: HEAD_REST_X, originY: head.y });
}

// Torso, neck and head pushed back along the arm by the weapon's recoil, and put back recoil x 5 ms of game time later
// (F4:21371-21390). A recoil of 0 still puts them back
function recoil(actor, weapon) {
  const parts = recoilParts(actor);
  if (actor.transitioning === true || parts.some((part) => !part || part.destroyed)) {
    return;
  }
  if (parts[0].originX === undefined) {
    setOrigins(actor);
  }
  const turn = radians(actor.pose?.arms ?? 0);
  const push = weapon.recoil ?? 0;
  const side = actor.facing < 0 ? -1 : 1;
  const dx = Math.cos(turn) * push * side;
  const dy = Math.sin(turn) * push * side;
  for (const part of parts) {
    takeOver(part);
    part.x -= dx;
    part.y -= dy;
  }
  const frames = Math.round((push * RECOIL_MS * page.lib.fps) / 1000);
  world.later(frames, () => returnRecoil(actor));
}

// returnRecoil (F4:21666)
function returnRecoil(actor) {
  const [torso, neck, head] = recoilParts(actor);
  if (actor.transitioning === true || !torso || torso.destroyed || !neck || !head || torso.originX === undefined) {
    return;
  }
  torso.x = torso.originX;
  torso.y = torso.originY;
  neck.x = NECK_REST_X;
  neck.y = neck.originY;
  head.x = HEAD_REST_X;
  head.y = head.originY;
}

// ---------- Firing ----------

// A point in a clip's own pixels, in room pixels
function roomPoint(clip, x, y) {
  const spot = clip.toGlobal({ x, y });
  const scale = page.root.scale;
  return toWorld(spot.x / scale.x, spot.y / scale.y);
}

// How long a round lives, in steps: far enough to cover roundLife pixels, the chainsaw's short reach, or a grenade's
// fuse (F4:21488-21497)
function roundLife(weapon, speed) {
  if (isChainsaw(weapon)) {
    return constant("roundLife_chainsaw");
  }
  if (weapon.grenade) {
    return weapon.life;
  }
  return Math.round(constant("roundLife") / speed);
}

// One round as it leaves the gun, carrying everything it needs from the weapon that fired it (F4:21412-21510).
// Knockback is rolled for every shot
function makeRound(actor, weapon, knockback) {
  const arms = actor.rig.arms;
  const lift = weapon.weaponType === "handGrenade" ? GRENADE_LIFT : 0;
  const from = roomPoint(actor.rig.clip, arms.x, arms.y - lift);
  let stray = rng.float() * spread(actor);
  if (rng.random(2) < 1) {
    stray = -stray;
  }
  const speed = weapon.roundSpeed - Math.round(rng.random((weapon.roundSpeed ?? 0) / 10));
  return {
    owner: actor,
    kind: roundKind(weapon),
    weaponRef: weapon.ref,
    weaponType: weapon.weaponType,
    weaponClass: weapon.weaponClass,
    projectile: weapon.projectile,
    decal: weapon.decal,
    x: from.x,
    y: from.y,
    angle: aimAngle(actor) + stray,
    speed,
    life: roundLife(weapon, speed),
    damage: weapon.damage,
    piercing: weapon.piercing ?? null,
    skill: weapon.skill,
    ammo: weapon.ammoType ?? null,
    shell: weapon.shell ?? null,
    crit: null,
    knockback,
    splashDamage: weapon.splashDamage,
    splashSize: weapon.splashSize,
    gravity: constant("roundGravity"),
  };
}

// What a round is, for how it flies: a hand grenade, an M79 shell, a rocket, an arrow or a bullet (F4:21483-21485,
// 5922)
function roundKind(weapon) {
  if (weapon.grenade) {
    return "grenade";
  }
  if (weapon.grenade40mm) {
    return "m79";
  }
  if (weapon.hitGrenade) {
    return "rocket";
  }
  return weapon.ammoType === "arrow" ? "arrow" : "bullet";
}

// What a shot does besides its rounds: the shake and the round out of the magazine for the player, the sound, the kick,
// the flash and the casing, each from the shooter's own weapon (F4:21343-21408)
function shotEffects(actor, weapon) {
  if (actor === player) {
    if (weapon.noShake !== true) {
      camera.shake(Math.round(weapon.damage / 5), SHOT_SHAKE_PULSES * constant("screenShakeDelay"));
    }
    const row = heldRow();
    if (row) {
      row.ammo -= 1;
    }
  }
  fireSound(actor, weapon);
  recoil(actor, weapon);
  if (weapon.noFlash !== true) {
    effects.muzzleFlash(actor, weapon);
    const smoke = actor.rig.arms?.child("smoke");
    if (smoke) {
      smoke.visible = rng.random(constant("showSmokeChance")) !== 0;
    }
  }
  if (!NO_CASING_TYPES.has(weapon.weaponType)) {
    effects.bounce("shellCasing", actor);
  }
}

// _root.fireWeapon(owner), called by the arms' animation on the frame a round leaves (F4:21322). An empty gun stops the
// trigger and starts a reload instead; anyone who never runs out has the trigger let go after every shot, so their own
// rules press it again
export function fireWeapon(actor) {
  if (!actor?.rig) {
    return;
  }
  const weapon = weaponOf(actor);
  const loaded = loadedOf(actor);
  if (loaded <= 0 || endless(actor)) {
    actor.firing = false;
    if (constant("autoReload") && !endless(actor)) {
      startReload(actor);
    }
  }
  if (loaded <= 0) {
    return;
  }
  shotEffects(actor, weapon);
  actor.consecRounds = (actor.consecRounds ?? 0) + 1;
  const knockback = rng.random(constant("knockbackChance")) < (weapon.knockback ?? 0);
  for (let i = 0; i < (weapon.roundsPerShot ?? 1); i += 1) {
    shots.spawn(makeRound(actor, weapon, knockback));
  }
}

// ---------- Reloading ----------

// The reload animation starts, when the gun needs rounds and some are held (startReload F4:20885). The UZI and its
// built copies use the pistol reload, as the UZI's own clip is shaped for it
export function startReload(actor) {
  const weapon = weaponOf(actor);
  const full = loadedOf(actor) >= (weapon.maxAmmo ?? 0);
  const need = !full && reserveOf(actor) > 0;
  if (actor.reloading === true || !need || actor.shoving === true) {
    return false;
  }
  soundAt(actor, `sound_${weapon.weaponType}_reload`);
  if (EXTRA_RELOAD_SOUNDS[weapon.weaponType]) {
    soundAt(actor, EXTRA_RELOAD_SOUNDS[weapon.weaponType]);
  }
  Object.assign(actor, { meleeSwing: false, shoving: false, firing: false, firingAnim: false, reloading: true });
  const arms = actor.rig.arms;
  gotoPlay(arms, `${weapon.reloadClip ?? weapon.weaponType}_reload`);
  arms.animating = true;
  return true;
}

// Rounds go from the rounds held into the gun (reloadWeapon F4:20926). "full" fills the magazine as far as the rounds
// held go, keeping what was loaded; "1" and "shotgun" load one round, and "shotgun" leaves the reload running for the
// next shell
export function reloadWeapon(kind, actor) {
  if (!actor) {
    return;
  }
  if (kind !== "shotgun") {
    actor.reloading = false;
  }
  if (endless(actor)) {
    return;
  }
  const row = heldRow();
  const weapon = weaponOf(actor);
  if (!row || !weapon.ammoType) {
    return;
  }
  const held = story.ammo[weapon.ammoType] ?? 0;
  const take = kind === "full" ? Math.min(held, (weapon.maxAmmo ?? 0) - row.ammo) : 1;
  row.ammo += take;
  story.ammo[weapon.ammoType] = held - take;
}

// ---------- Swapping ----------

// The chainsaw's motor stops when it leaves the hands and idles when it comes in (F4:21029-21033, 21204-21208)
function swapSounds(before, after) {
  sound.stopLoop("chainsaw");
  sound.stopLoop("chainsawIdle");
  if (isChainsaw(before)) {
    sound.play("sound_chainsaw_off");
  }
  if (isChainsaw(after)) {
    sound.loop("sound_chainsaw_idle", "chainsawIdle");
  }
}

// The slot a swap lands on: "primary", "secondary", or the other one for a plain swap (F4:21041-21088)
function swapTarget(to, holding) {
  if (to === 1 || to === "primary") {
    return "primary";
  }
  if (to === 2 || to === "secondary") {
    return "secondary";
  }
  return otherSlot(holding);
}

// The player's weapons change hands at once (swapWeapons F4:21003): a reload is cancelled, the new weapon shows in the
// hands with its mods and the other goes on the back. Nothing happens mid-trigger. A bow, grenade or RPG reloads as it
// comes out. to is 1, 2, "primary", "secondary" or "swap"
export function swapTo(to) {
  if (!player.rig || !story.player) {
    return;
  }
  if (player.firing !== true) {
    const before = weaponOf(player);
    Object.assign(player, { reloading: false, firingAnim: false, shoving: false });
    const slot = swapTarget(to, story.player.holding);
    story.player.holding = slot;
    const after = weaponOf(player);
    swapSounds(before, after);
    player.rig.setWeapon(story.player.slots[slot], { stored: story.player.slots[otherSlot(slot)] });
    player.weaponType = after.weaponType;
    player.weaponSkill = after.skill;
    const { primary, secondary } = story.player.slots;
    if (primary !== "hands" && secondary !== "hands") {
      help.show("weaponSwitch");
    }
  }
  if (weaponOf(player).reloadOnSwap === true) {
    startReload(player);
  }
}

// ---------- The fire button ----------

function dryClick() {
  if (weaponOf(player).weaponType !== "bow") {
    sound.play("sound_dryFire");
    dryFired = true;
  }
}

// An empty gun: a reload if rounds are held, and the dry click (F4:21239-21255). A pump being reloaded with a shell in
// it raises the gun to fire instead (F4:21256-21261)
function emptyGun(weapon) {
  const loaded = loadedOf(player);
  if (loaded <= 0 && player.firingAnim === false && player.reloading !== true && reserveOf(player) > 0) {
    startReload(player);
    dryClick();
  }
  if (loaded <= 0 && weapon.weaponClass === "firearm" && player.reloading !== true) {
    dryClick();
  }
  const pumping = player.reloading === true && weapon.weaponType === "pumpAction";
  if (pumping && loaded > 0 && rootFlags.raisingWeapon !== true) {
    rootFlags.raisingWeapon = true;
    gotoPlay(player.rig.arms, "pumpAction_raise");
    dryFired = true;
  }
}

function pullTrigger(weapon) {
  player.firing = true;
  gotoPlay(player.rig.arms, `${weapon.weaponType}_fire`);
  if (isChainsaw(weapon)) {
    sound.play("sound_chainsaw_start");
    sound.loop("sound_chainsaw_work", "chainsaw");
  }
}

// A swing: one of the two swings at random, the body leaning in for a held weapon, a grunt and the swish
// (F4:21275-21291, 5020-5034). The swing starts with no hit and no miss of its own; whether it lands is the melee
// stage's to say, and the knockback is rolled when it does
export function swing(actor, weapon = weaponOf(actor)) {
  Object.assign(actor, { firing: true, shoving: false, meleeSwing: true, hitThisSwing: false, missedThisSwing: false });
  const arms = actor.rig.arms;
  gotoPlay(arms, `${weapon.weaponType}_fire${rng.random(2) + 1}`);
  if (weapon.weaponType !== "fists") {
    gotoPlay(arms.child("torso"), "shove");
  }
  exertSound(actor);
  sound.play(`sound_${weapon.swing}_swing${rng.random(2) + 1}`, actor === player ? {} : { x: actor.x });
}

// A shove (characterShove F4:12542): when not already swinging, shoving, firing or jumping, the body and arms play
// the 22-frame push, a grunt and the swish. It stops a reload. The player's shove costs stamina; whom it touches is
// the melee stage's to say, each one once a shove
export function characterShove(shover) {
  const busy = [shover.meleeSwing, shover.shoving, shover.firing, shover.firingAnim, shover.jumping];
  if (busy.some((flag) => flag === true) || !shover.rig) {
    return false;
  }
  if (shover === player) {
    help.did("shove");
    reduceStamina("shove");
    rootFlags.playerMoveBackwardAnim = false;
    rootFlags.playerMoveForwardAnim = false;
  }
  Object.assign(shover, { reloading: false, shoving: true, meleeSwing: false, firing: false, firingAnim: false });
  shover.shoveHits = new Set();
  gotoPlay(shover.rig.clip, shover.crouched === true ? "shoveCrouched" : "shove");
  const arms = shover.rig.arms;
  gotoPlay(arms, "shove");
  gotoPlay(arms.child("torso"), "shove");
  exertSound(shover);
  soundAt(shover, "sound_wood_swing1");
  return true;
}

// The mouse goes down on the playfield (fireButton.onPress F4:21223). Nothing while the controls are locked or a sprint
// is on; the world's step does not run while paused
function pressTrigger() {
  dryFired = false;
  if (player.controlsLocked || player.sprinting) {
    return;
  }
  help.did("mouse");
  const weapon = weaponOf(player);
  emptyGun(weapon);
  const ready = loadedOf(player) > 0 && player.reloading !== true && player.shoving !== true;
  if (ready && player.firingAnim === false && weapon.weaponClass === "firearm") {
    pullTrigger(weapon);
  }
  if (player.shoving !== true && player.firingAnim === false && MELEE_TYPES.has(weapon.weaponType)) {
    swing(player, weapon);
  }
}

// The mouse comes up (fireButton.onRelease F4:21294): the trigger lets go, the chainsaw drops to idle, and a shot that
// was not a dry click wakes the enemies in the room
function releaseTrigger() {
  player.firing = false;
  const weapon = weaponOf(player);
  if (isChainsaw(weapon)) {
    sound.stopLoop("chainsaw");
    sound.loop("sound_chainsaw_idle", "chainsawIdle");
    sound.play("sound_chainsaw_end");
  }
  if (!dryFired) {
    weaponNoise(player);
  }
}

// The noise a weapon makes: melee weapons make none (F4:21688)
function noiseOf(weapon) {
  return weapon.weaponClass === "melee" ? 0 : (weapon.weaponNoise ?? 0);
}

// Registers fn(target, shooter, condition, noise) for an enemy a weapon's noise may wake
export function onNoise(fn) {
  noiseListeners.push(fn);
}

// Every unalerted enemy in the room rolls to wake, with the weapon's noise added (the roll adds it x 15), however far
// away it is (F4:21309-21317). Returns how many rolled
export function weaponNoise(actor) {
  const noise = noiseOf(weaponOf(actor));
  const enemies = [...world.zombies, ...world.humans.filter((each) => each.side === "enemy")];
  const waking = enemies.filter((each) => each.alerted === false && each.alive !== false);
  for (const target of waking) {
    for (const fn of noiseListeners) {
      fn(target, actor, null, noise);
    }
  }
  return waking.length;
}

// Space shoves while there is stamina (playerControls F4:12452-12465). While grabbed, the press counts toward the
// struggle instead, which the struggle reads for itself
function shoveKey() {
  if (input.shovePressed && player.shoving !== true && player.struggling !== true && player.stamina > 0) {
    characterShove(player);
  }
}

// The weapon keys: R reloads, 1 and 2 take a slot, Q swaps (playerControls F4:12466-12514)
function weaponKeys() {
  if (input.slotPressed !== null && player.firingAnim === false) {
    help.did("weaponSwitch");
    swapTo(input.slotPressed);
  }
  if (input.reloadPressed && player.reloading !== true) {
    startReload(player);
  }
}

// The controls stage's part: the trigger's press and release, then the weapon keys. A press and release inside one
// step still fires once
export function fireButton() {
  if (world.player !== player || !player.rig) {
    return;
  }
  if (!triggerDown && (input.fireHeld || input.mouse.pressed)) {
    triggerDown = true;
    pressTrigger();
  }
  if (triggerDown && !input.fireHeld) {
    triggerDown = false;
    releaseTrigger();
  }
  if (player.alive === true && !player.controlsLocked) {
    shoveKey();
    weaponKeys();
  }
}

// ---------- The arms' frame scripts ----------

// The actor whose arms these are
function armsOwner(arms) {
  return ownerOf(arms.parentClip);
}

// The fire frame of the revolver and the pistol (frames 52 and 301): the round leaves, and the smoke puffs if the gun
// fired
function fireFrame(arms) {
  const owner = armsOwner(arms);
  owner.firingAnim = true;
  fireWeapon(owner);
  if (owner.firingAnim === true) {
    arms.child("smoke")?.play?.();
  }
  arms.play();
}

// The pistol and rifles loop while the trigger is held, a burst gun only until its burst is out (frames 303, 355 and
// 409). The pistol's frame also needs an automatic gun; the original read the player's gun for that, this reads the
// shooter's. The rifles hold the gun once the trigger is let go; the pistol plays out its slide
function autoFrame(arms, type, frame) {
  const owner = armsOwner(arms);
  const weapon = weaponOf(owner);
  const pistol = frame === PISTOL_LOOP_FRAME;
  if (!pistol) {
    owner.firingAnim = false;
  }
  if (owner.firing !== true || (pistol && weapon.fireMode !== "auto")) {
    if (!pistol) {
      goto(arms, type);
    }
    return;
  }
  const burstOut = weapon.burst === true && (owner.consecRounds ?? 0) >= weapon.roundsPerBurst;
  if (burstOut) {
    goto(arms, type);
  } else {
    gotoPlay(arms, `${type}_fire`);
  }
}

// The end of a pistol or UZI reload (frame 350): the rounds go in and the arms hold the gun again, the UZI's own pose
// for an UZI or one of its built copies
function pistolReloadEnd(arms) {
  const owner = armsOwner(arms);
  arms.stop();
  arms.animating = false;
  reloadWeapon("full", owner);
  goto(arms, weaponOf(owner).weaponType);
}

// A pump loads a shell each pass, then raises the gun when full or out of shells (frame 563). Someone who never runs
// out counts shells with reloadCount
function pumpFrame(arms) {
  const owner = armsOwner(arms);
  const weapon = weaponOf(owner);
  reloadWeapon("shotgun", owner);
  let done;
  if (endless(owner)) {
    done = (owner.reloadCount ?? 0) >= weapon.maxAmmo;
    if (!done) {
      owner.reloadCount = (owner.reloadCount ?? 0) + 1;
    }
  } else {
    done = loadedOf(owner) >= weapon.maxAmmo || reserveOf(owner) < 1;
  }
  gotoPlay(arms, done ? "pumpAction_raise" : "pumpAction_loop");
}

// The bow draws again while the trigger is held, or nocks the next arrow (frame 749)
function bowFrame(arms) {
  const owner = armsOwner(arms);
  owner.firingAnim = false;
  if (owner.firing === true) {
    gotoPlay(arms, "bow_fire");
  } else {
    reloadWeapon("full", owner);
    goto(arms, "bow");
  }
}

// The RPG's rocket shows only while one is loaded (frame 755)
function rpgFrame(arms) {
  arms.animating = false;
  const magazine = arms.child("weapon")?.child("magazine");
  if (magazine) {
    magazine.visible = loadedOf(armsOwner(arms)) >= 1;
  }
}

// With no rockets held, the RPG stays empty instead of reloading (frame 774)
function rpgEmptyFrame(arms) {
  const owner = armsOwner(arms);
  if (reserveOf(owner) <= 0) {
    owner.firingAnim = false;
    arms.stop();
  }
}

// A revolver's reload drops its spent cases (frame 82)
function revolverCases(arms) {
  const owner = armsOwner(arms);
  const count = REVOLVER_CASES[weaponOf(owner).shell] ?? REVOLVER_CASES_DEFAULT;
  for (let i = 0; i < count; i += 1) {
    effects.bounce("shellCasing", owner);
  }
}

// The hand-weapon pose stops, and the player hands their weapon to the companion (frame 24)
function handWeaponFrame(arms) {
  arms.stop();
  const owner = armsOwner(arms);
  if (owner === player && owner.changingWeapons !== true) {
    rigCall("giveWeapon", arms.parentClip);
  }
}

// The end of the struggle pose reads _root.struggling, which nothing in the original sets, so the arms always go on
// (frame 17)
function struggleFrame(arms) {
  if (rootFlags.struggling) {
    gotoPlay(arms, "struggle");
  }
}

const ARMS_SCRIPTS = {
  17: struggleFrame,
  24: handWeaponFrame,
  52: fireFrame,
  82: revolverCases,
  301: fireFrame,
  303: (arms) => autoFrame(arms, "pistolAutomatic", PISTOL_LOOP_FRAME),
  350: pistolReloadEnd,
  355: (arms) => autoFrame(arms, "assaultRifle", 355),
  409: (arms) => autoFrame(arms, "assaultRifleSlow", 409),
  563: pumpFrame,
  749: bowFrame,
  755: rpgFrame,
  774: rpgEmptyFrame,
};

function armsScript(arms, frame) {
  ARMS_SCRIPTS[frame]?.(arms);
}

// The rig a part belongs to, or null
function rigClipOf(node) {
  let up = node.parentClip;
  while (up && !up.rig) {
    up = up.parentClip;
  }
  return up ?? null;
}

// The weapon on the back hides its rocket when the player's stored RPG is empty (S4799 frame 8). A rig not yet bound
// to the player is checked again once it is
function backpackScript(holder, frame) {
  if (frame !== BACKPACK_RPG_FRAME) {
    return;
  }
  const rigClip = rigClipOf(holder);
  const owner = rigClip ? ownerOf(rigClip) : null;
  const row = owner === player && story.player ? slotRow(otherSlot(story.player.holding)) : null;
  const magazine = holder.child("magazine");
  if (row && magazine && row.ammo <= 0) {
    magazine.visible = false;
  }
}

function checkBackpackWeapon() {
  for (const path of ["arms.torso.torso.backpackWeapon", "torsoAnim.torso.backpackWeapon"]) {
    const holder = partAt(player.rig?.clip, path);
    if (holder?.frame) {
      backpackScript(holder, holder.frame);
    }
  }
}

// ---------- The arms' hooks ----------

// "fire" is _root.fireWeapon(this._parent); the others are the arms' sounds, casings, magazines and loops
export const WEAPON_HOOKS = {
  fire(arg, arms) {
    fireWeapon(armsOwner(arms));
    return true;
  },
  // ["bounce", "shellCasing"] or ["bounce", "mag", kind]: the magazine leaves from the arms' magPoint
  bounce(kind, arms, [type]) {
    const options = kind === "mag" ? { type: type ?? null, point: arms.child("magPoint") } : {};
    effects.bounce(kind, armsOwner(arms), options);
    return true;
  },
  // The magazine in the hand during a reload shows the gun's own (magazine.gotoAndStop(currentWeapon)); a built copy
  // with no frame of its own shows its base model's
  magframe(arg, arms) {
    const weapon = weaponOf(armsOwner(arms));
    const magazine = arms.child("magazine");
    if (!goto(magazine, weapon.ref) && weapon.weaponBase) {
      goto(magazine, weapon.weaponBase);
    }
    return true;
  },
  weaponsound(name, arms) {
    if (WEAPON_SOUNDS[name]) {
      soundAt(armsOwner(arms), WEAPON_SOUNDS[name]);
    }
    return true;
  },
  // Loop the fire animation while the trigger is held, or hold the gun (frames 131, 261, 471 ... 1021)
  fireloop(fireLabel, arms, [idleLabel]) {
    const owner = armsOwner(arms);
    owner.firingAnim = false;
    if (owner.firing === true) {
      gotoPlay(arms, fireLabel);
    } else {
      goto(arms, idleLabel);
    }
    return true;
  },
  // The last frame of a reload: the rounds go in, the magazine shows again where the art says so, and the arms hold
  // the gun
  reloaddone(idleLabel, arms, [magazineLine]) {
    arms.stop();
    arms.animating = false;
    reloadWeapon("full", armsOwner(arms));
    if (magazineLine) {
      const magazine = arms.child("weapon")?.child("magazine");
      if (magazine) {
        magazine.visible = true;
      }
    }
    goto(arms, idleLabel);
    return true;
  },
};

// The player's reloads, start and end in world steps, for checks
function trackReloads() {
  const now = player.reloading === true;
  if (now && !reloadingBefore) {
    reloads.push({ weapon: weaponOf(player).ref, start: world.frame, end: null });
    if (reloads.length > MOST_RELOADS) {
      reloads.shift();
    }
  } else if (!now && reloadingBefore && reloads.length) {
    reloads[reloads.length - 1].end = world.frame;
  }
  reloadingBefore = now;
}

// ---------- Setup and checks ----------

// The character's height, measured once a room has dressed the player standing, and the weapon state a new room
// starts with: no reload running, the trigger up and the resting places the recoil comes back to (setupPlayer
// F4:11854-11906)
function measurePlayer() {
  if (player.clip && !player.clip.destroyed) {
    player.charHeight = player.clip.height;
    player.pose = null;
    Object.assign(player, { reloading: false, meleeSwing: false, firing: false, firingAnim: false });
    player.weaponType = weaponOf(player).weaponType;
    player.weaponSkill = weaponOf(player).skill;
    rootFlags.raisingWeapon = false;
    triggerDown = false;
    setOrigins(player);
    checkBackpackWeapon();
  }
}

// The functions the art calls by name that firing owns
function registerCalls() {
  onRigCall("reloadWeapon", (target, kind) => reloadWeapon(kind, target.owner));
}

export function initWeapons(owner, band) {
  page = owner;
  depth = band;
  makeCrosshair();
  page.lib.scripts.set(ARMS_SPRITE, armsScript);
  page.lib.scripts.set(BACKPACK_WEAPON_SPRITE, backpackScript);
  registerCalls();
  world.stage("interface", () => {
    crosshair.update();
    showPose(player);
    trackReloads();
  });
  world.stage("controls", fireButton);
  world.stage("aim", () => aimWeapon(player));
  page.steppers.push(() => {
    if (!world.active) {
      crosshair.hide();
    }
  });
  onRoom("build", measurePlayer);
}

// Helpers for page.py checks
export const weaponsDebug = {
  // Puts the mouse at a stage point
  aim(x, y) {
    input.aim.x = x;
    input.aim.y = y;
    input.mouse.x = x;
    input.mouse.y = y;
  },

  // Where the arm points now
  arm() {
    const { pose } = player;
    return {
      arms: pose?.arms,
      torso: pose?.torso,
      head: pose?.head,
      facing: player.facing,
      degrees: aimAngle(player),
      shoulder: shoulder(player),
      charHeight: player.charHeight,
    };
  },

  // The crosshair: whether it shows, where, how far its arms stand from the centre, and the system cursor
  crosshair() {
    const gaps = Object.fromEntries(
      Object.keys(CROSSHAIR_ARMS).map((name) => {
        const arm = crosshairClip?.child(name);
        return [name, arm ? Math.abs(arm.x || arm.y) : null];
      }),
    );
    return {
      visible: crosshair.visible,
      x: crosshairClip?.x,
      y: crosshairClip?.y,
      gaps,
      target: crosshairGap(player),
      spread: spread(player),
      consecRounds: player.consecRounds ?? 0,
      cursor: page.app.canvas.style.cursor,
    };
  },

  // Sets the shots in a row
  consec(n) {
    player.consecRounds = n;
  },

  // Puts a weapon in a slot (1 or "primary", 2 or "secondary") and takes it in hand, loaded with `loaded` rounds (a
  // full magazine by default) and `reserve` rounds held for it (left as they are by default)
  equip(ref, slot = "primary", { loaded = null, reserve = null } = {}) {
    const place = swapTarget(slot, "secondary");
    const weapon = data.items.weapons[ref];
    for (const old of story.inventory.filter((row) => row.eqd && row.type === "weapon" && row.slot === place)) {
      returnRounds(old);
      Object.assign(old, { eqd: false, slot: "none" });
    }
    const row = addRow(ref);
    Object.assign(row, { eqd: true, slot: place, ammo: loaded ?? weapon.maxAmmo ?? 0 });
    story.player.slots[place] = ref;
    if (reserve !== null && weapon.ammoType) {
      story.ammo[weapon.ammoType] = reserve;
    }
    Object.assign(player, { firing: false, firingAnim: false, reloading: false });
    triggerDown = false;
    swapTo(place);
    return weaponsDebug.weapon();
  },

  // Holds the trigger down (a press this step) or lets it go
  trigger(on = true) {
    input.fireHeld = on;
    input.mouse.down = on;
    if (on) {
      input.mouse.pressed = true;
    }
  },

  // A click: the trigger pressed and let go within one step
  click() {
    input.mouse.pressed = true;
  },

  // The weapon in hand: rounds loaded and held, the arms' frame and label, and the firing flags
  weapon() {
    const weapon = weaponOf(player);
    const arms = player.rig?.arms;
    const labels = Object.entries(arms?.def?.labels ?? {}).filter(([, frame]) => frame <= (arms?.frame ?? 0));
    labels.sort((a, b) => b[1] - a[1]);
    return {
      ref: weapon.ref,
      type: weapon.weaponType,
      holding: story.player?.holding,
      slots: { ...story.player?.slots },
      loaded: heldRow()?.ammo ?? null,
      reserve: weapon.ammoType ? story.ammo[weapon.ammoType] : null,
      armsFrame: arms?.frame,
      armsLabel: labels[0]?.[0] ?? null,
      firing: player.firing,
      firingAnim: player.firingAnim,
      reloading: player.reloading,
      consecRounds: player.consecRounds ?? 0,
      shotsFired: shots.fired.length,
    };
  },

  // The player's latest reloads, { weapon, start, end } in world steps
  reloads,

  // Takes a shove, as Space does when the player can
  shove() {
    return characterShove(player);
  },

  // Starts a swing of the melee weapon in an actor's hands (the player's by default), as a click does
  swing(actor = player) {
    swing(actor);
    return actor.meleeSwing;
  },

  swapTo,
  startReload,
};
