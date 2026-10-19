// The human rig: the original's `human` clip (4925) with its arms (4911) and the weapon in hand (`weapons`, 4885),
// dressed by frame label and tinted for skin and hair, and the parts of its timelines' scripts the timeline player
// leaves to the page. The player, companions, hostile humans, NPCs and the menu heads are all built with makeHuman.
//
// A rig's flags (animating, crouched, struggling, alive ...) belong to whoever owns it: the rig itself until an actor
// is bound to it (bind), then the actor, so the art's own lines (`this.shoving = false;`) write straight into the
// actor the rules read. A clip that is not a rig's root owns its own flags, as in the original, where `this.animating`
// in the arms is the arms' variable.
//
// The art's script lines that reach the page as hooks (port.json's art.hooks) are dispatched here; the functions they
// call by name (checkForGrab, reloadWeapon ...) belong to the systems that own them, which register them with
// onRigCall(name, fn).
import { CanvasSource, Sprite, Texture } from "./vendor/pixi.min.mjs";
import { data } from "./data.js";
import { applyColor } from "./flash.js";
import { story } from "./story.js";
import { world } from "./world.js";

const HUMAN = "human";
// The arms' sprite and the sprite a one-hand or two-hand swing places inside them (head and neck offsets)
const HUMAN_SPRITE = 4925;
const SWING_SPRITE = 4906;
// The player's size, and a woman's: one size on both axes, so a woman is never squashed (F4:11841-11847)
const MALE_SCALE = 55;
const FEMALE_SCALE = 52;
// A new character's skin and hair colour (F4:27392)
const DEFAULT_SKIN = 0xd3965f;
const DEFAULT_HAIR_COLOUR = 0xa39a74;
// The parts the original tints with Color.setRGB (decoratePlayer, F4:12079-12146): a flat colour over the picture
const SKIN_PARTS = [
  "head.skin.skin",
  "headAnim.skin.skin",
  "neck.skin",
  "neckAnim.skin",
  "arms.torso.torso.skin",
  "torsoAnim.torso.skin",
  "arms.hand_front.skin",
  "arms.hand_back.skin",
  "hand_frontAnim.skin",
  "hand_backAnim.skin",
  "arms.upperArm_front.skin",
  "arms.upperArm_back.skin",
  "upperArm_frontAnim.skin",
  "upperArm_backAnim.skin",
  "arms.lowerArm_front.skin",
  "arms.lowerArm_back.skin",
  "arms.lowerArm_backFront.skin",
  "lowerArm_frontAnim.skin",
  "lowerArm_backAnim.skin",
  "lowerArm_backFrontAnim.skin",
  "upperLeg_front.skin",
  "upperLeg_back.skin",
  "lowerLeg_front.skin",
  "lowerLeg_back.skin",
  "foot_front.skin",
  "foot_back.skin",
];
const HAIR_PARTS = ["head.hair.base", "head.facialHair.base", "headAnim.hair.base", "headAnim.facialHair.base"];
// The names a tinted part goes by, so a newly placed part is checked only when it could be one
const TINTED_NAMES = new Set(["skin", "base"]);
// The arm parts dressed by the top's label, in the upper-body arms and in the full-body copy
const ARM_PARTS = ["lowerArm_front", "lowerArm_back", "upperArm_front", "upperArm_back"];
const ANIM_ARM_PARTS = ["lowerArm_frontAnim", "lowerArm_backAnim", "upperArm_frontAnim", "upperArm_backAnim"];
// What toggleAnimMode shows for the full-body animation and hides for upper-body aiming (F4:11655-11702). The torso
// is torsoAnim's inner torso, as the original hides only that
const UPPER_PARTS = ["head", "arms", "neck"];
const FULL_PARTS = [
  "animWeapon",
  "headAnim",
  "torsoAnim.torso",
  "hand_frontAnim",
  "hand_backAnim",
  "upperArm_frontAnim",
  "upperArm_backAnim",
  "lowerArm_frontAnim",
  "lowerArm_backAnim",
  "lowerArm_backFrontAnim",
  "neckAnim",
];
// Hands for a weapon's class, then for its type (playerWeaponSetup F4:11821-11830, swapWeapons F4:21177-21197). Bare
// hands are type "fists" and take the melee hands
const CLASS_HANDS = {
  firearm: { back: "holdHand", front: "triggerHand" },
  melee: { back: "meleeBackHand", front: "meleeFrontHand" },
};
const TYPE_HANDS = {
  bullpup: { back: "meleeBackHand" },
  oneHand: CLASS_HANDS.melee,
  twoHand: CLASS_HANDS.melee,
  fists: CLASS_HANDS.melee,
  bow: {},
  RPG: {},
};
const DEFAULT_TYPE_HANDS = { back: "holdHand" };
// Which weapon add-ons a mod shows (F4:21125-21141)
const MOD_PARTS = { scope: ["scope"], suppressed: ["suppressor"], specOps: ["scope", "suppressor"] };
// A shove's head and neck places on S4925 frames 207-215 and 225-234 ([head x, head y, neck x, neck y]), and where they
// sit when crouched ([head y, neck y]), standing and crouched shoves
const SHOVE = {
  poses: {
    207: [0, -211, -10, -208],
    210: [-5, -210.6, -12, -207],
    213: [-2.5, -210.6, -4, -207],
    215: [8, -211, 0, -208],
  },
  low: [-170, -170],
};
const SHOVE_CROUCHED = {
  poses: {
    225: [0, -211, -10, -208],
    228: [-5, -210.6, -12, -207],
    231: [-2.5, -210.6, -4, -207],
    234: [12, -211, 0, -208],
  },
  low: [-160, -159],
};
// The last frame of each shove puts the head back and returns to standing or crouched (S4925 frames 219 and 239)
const SHOVE_ENDS = { 219: [SHOVE, [6, -207.6, -4, -208]], 239: [SHOVE_CROUCHED, [8, -207.6, 0, -208]] };
// A swing's head and neck x on S4906 frames 4-12 ([head x, neck x]); frame 4 leaves the head where it is (its head
// line reaches one clip too far in the original). Crouched, both sit at y -160
const SWING_POSES = { 4: [null, -5], 7: [-2, -12], 10: [-2.5, -4], 12: [4, 0] };
const SWING_LOW = -160;
// The flags a rig hands to the actor it is bound to, unless the actor already has its own
const BOUND_FLAGS = [
  "alive",
  "crouched",
  "standing",
  "struggling",
  "grabbed",
  "shoving",
  "firing",
  "firingAnim",
  "reloading",
  "meleeSwing",
];
// The idle animation picks a head scratch or hands on hips one time in 40 each (S4925 frame 498)
const IDLE_ODDS = 40;

let page = null;
// The original's _root variables the art sets (playerMoveForwardAnim, raisingWeapon ...), for the rules that read them
export const rootFlags = {};
// Name -> fn(target, ...args) for the functions the art calls by name; target is { clip, owner, rig }
const rigCalls = new Map();
// Names the art called that nothing has registered yet, so a check can see what is still unbuilt
const missingCalls = new Set();
// Shape pieces turned into flat white silhouettes, so a tint gives Color.setRGB's flat colour without a filter
const silhouettes = new Map();

// ---------- Paths, labels and owners ----------

// A part by a dotted path from a clip, as the original's `this.arms.torso.torso` or `_parent._parent.head`
export function partAt(clip, path) {
  if (!path || path === "this") {
    return clip;
  }
  let node = clip;
  for (const name of path.split(".")) {
    if (name === "this") {
      continue;
    }
    node = name === "_parent" ? node?.parentClip : node?.child?.(name);
    if (!node) {
      return null;
    }
  }
  return node;
}

// The frame a label names. Flash's frame labels are not case sensitive, and the art relies on it (the backpack's
// "ak47" for the weapon "AK47", the hair "ponyTail1" for "ponytail1")
export function frameFor(clip, label) {
  const labels = clip?.def?.labels;
  if (!labels || typeof label !== "string") {
    return null;
  }
  if (labels[label]) {
    return labels[label];
  }
  const lower = label.toLowerCase();
  const found = Object.keys(labels).find((name) => name.toLowerCase() === lower);
  return found ? labels[found] : null;
}

// Flash's gotoAndStop by label, doing nothing when the clip has no such label (as Flash does)
export function goto(clip, label) {
  const frame = frameFor(clip, label);
  if (frame) {
    clip.gotoAndStop(frame);
  }
  return Boolean(frame);
}

// Flash's gotoAndPlay by label, doing nothing when the clip has no such label
export function gotoPlay(clip, label) {
  const frame = frameFor(clip, label);
  if (frame) {
    clip.gotoAndPlay(frame);
  }
}

function setShown(clip, path, on) {
  const part = partAt(clip, path);
  if (part) {
    part.visible = on;
  }
}

// Who keeps a clip's flags: the actor or rig bound to a rig's root, or the clip itself
export function ownerOf(clip) {
  return clip?.owner ?? clip;
}

// In Flash, once a script moves a part the timeline placed, the timeline stops moving it. The part keeps the place
// scripts give it from now on (the head and neck offsets, the arms' aim)
export function takeOver(node) {
  if (!node.scripted) {
    node.scripted = true;
    node.setFromMatrix = keepScriptPlace;
  }
}

function keepScriptPlace() {}

function moveTo(node, x, y) {
  if (!node) {
    return;
  }
  takeOver(node);
  if (x !== null) {
    node.x = x;
  }
  if (y !== null) {
    node.y = y;
  }
}

// ---------- Colours ----------

// A colour from a number, "0xD3965F", "D3965F" or a name from the appearance lists ("White", "Blonde")
export function colourOf(value, fallback) {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value !== "string" || !value) {
    return fallback;
  }
  const named = [...(data.actors?.appearance?.skins ?? []), ...(data.actors?.appearance?.hairColours ?? [])].find(
    (each) => each.name === value,
  );
  const hex = (named?.colour ?? value).replace(/^0x|^#/i, "");
  const parsed = Number.parseInt(hex, 16);
  return Number.isNaN(parsed) ? fallback : parsed;
}

// A white copy of a shape piece with its own see-through edges, cut once per piece and shared by every rig
function silhouette(texture) {
  const { source, frame } = texture;
  const key = `${source.uid}:${frame.x},${frame.y},${frame.width},${frame.height}`;
  let flat = silhouettes.get(key);
  if (flat) {
    return flat;
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.ceil(frame.width));
  canvas.height = Math.max(1, Math.ceil(frame.height));
  const context = canvas.getContext("2d");
  context.drawImage(source.resource, frame.x, frame.y, frame.width, frame.height, 0, 0, frame.width, frame.height);
  context.globalCompositeOperation = "source-in";
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  flat = new Texture({ source: new CanvasSource({ resource: canvas }) });
  silhouettes.set(key, flat);
  return flat;
}

function eachPicture(node, fn) {
  for (const child of node.children ?? []) {
    if (child instanceof Sprite) {
      fn(child);
    } else {
      eachPicture(child, fn);
    }
  }
}

// Color.setRGB: the part drawn in one flat colour, keeping its outline and alpha. The world's light still tints it,
// since a parent's tint multiplies a child's. A colour the art placed the part in (the hair's dark base) is replaced,
// as the original's colour call replaced it
export function paintFlat(node, colour) {
  if (!node || node.destroyed) {
    return;
  }
  node.flatColour = colour;
  if (node.placementCx) {
    node.placementCx = null;
    node.scriptColor = null;
    applyColor(node, null);
  }
  eachPicture(node, (picture) => {
    if (!picture.flat) {
      picture.texture = silhouette(picture.texture);
      picture.flat = true;
    }
    picture.tint = colour;
  });
}

// The colour a part of a rig takes by its path, or null when the original leaves it as drawn
function tintFor(rig, path) {
  if (SKIN_PARTS.includes(path)) {
    return rig.skinColour;
  }
  return HAIR_PARTS.includes(path) ? rig.hairColour : null;
}

// lib.onPlace calls this for every new part: a skin or hair part a timeline places again (a new hand pose, a new
// haircut) takes its rig's colour, where the original set it again after every such change
export function rigPlaced(node) {
  if (!TINTED_NAMES.has(node.label)) {
    return;
  }
  const names = [node.label];
  let up = node.parentClip;
  while (up && !up.rig) {
    names.unshift(up.label);
    up = up.parentClip;
  }
  const colour = up ? tintFor(up.rig, names.join(".")) : null;
  if (colour !== null) {
    paintFlat(node, colour);
  }
}

// ---------- Dressing ----------

// A clothing or hair label carries the sex in front unless the data already has it ("male_bioHazardTop")
function sexed(sex, value) {
  return /^(male|female)_/.test(value) ? value : `${sex}_${value}`;
}

// What decoratePlayer reads, from a look ({ sex, skin, hair, hairColour, facialHair }) and the clothes worn ({ top,
// bottom, shoes, torso, head, face, eyes }, refs or "none")
function dressOf(look, clothes) {
  const sex = look.sex === "female" ? "female" : "male";
  return {
    sex,
    skin: colourOf(look.skin, DEFAULT_SKIN),
    hairColour: colourOf(look.hairColour, DEFAULT_HAIR_COLOUR),
    hair: sexed(sex, look.hair ?? "cropped"),
    facialHair: look.facialHair ?? "none",
    top: sexed(sex, clothes.top ?? "none"),
    bottom: sexed(sex, clothes.bottom ?? "none"),
    shoes: clothes.shoes ?? "none",
    torso: clothes.torso ?? "none",
    head: clothes.head ?? "none",
    face: clothes.face ?? "none",
    eyes: clothes.eyes ?? "none",
  };
}

// The heads, both the aiming one and the full-body one (F4:12002-12077)
function dressHeads(clip, dress) {
  for (const name of ["head", "headAnim"]) {
    const head = clip.child(name);
    goto(head?.child("skin"), dress.sex === "female" ? "head2" : "head1");
    goto(head?.child("accessories"), dress.head);
    goto(head?.child("accessoriesFace"), dress.face);
    goto(head?.child("accessoriesEyes"), dress.eyes);
    goto(head?.child("hair"), dress.hair);
    goto(head?.child("facialHair"), dress.facialHair);
  }
}

// The arms take the top's sleeves over bare male arms: the original sends every arm to "male_none" before the top, so
// a top without sleeves shows the same bare arms on everyone (F4:12020-12046)
function dressArms(clip, dress) {
  const arms = clip.child("arms");
  for (const name of [...ARM_PARTS, "lowerArm_backFront"]) {
    const part = arms?.child(name);
    goto(part, "male_none");
    goto(part, dress.top);
  }
  for (const name of [...ANIM_ARM_PARTS, "lowerArm_backFrontAnim"]) {
    const part = clip.child(name);
    goto(part, "male_none");
    goto(part, dress.top);
  }
  setShown(clip, "arms.lowerArm_backFront", false);
}

function dressTorso(torso, dress, backpack) {
  if (!torso) {
    return;
  }
  goto(torso, dress.top);
  goto(torso.child("accessories"), dress.torso);
  if (backpack === "premium") {
    goto(torso.child("backpack"), "premium");
  }
  for (const name of ["backpack", "strapsFront", "strapsBack"]) {
    setShown(torso, name, backpack !== false);
  }
}

function dressLegs(clip, dress) {
  goto(clip.child("upperLeg_front"), dress.bottom);
  goto(clip.child("upperLeg_back"), `${dress.bottom}Back`);
  goto(clip.child("lowerLeg_front"), dress.bottom);
  goto(clip.child("lowerLeg_back"), dress.bottom);
  goto(clip.child("foot_front"), dress.shoes);
  goto(clip.child("foot_back"), dress.shoes);
}

// The HERC mask hides the hair and shows its neck piece; the HERC jacket shows gloves (HERC_clothingSetup, F4:11635)
function dressHERC(clip, face, top) {
  const mask = face === "HERCmask";
  goto(partAt(clip, "neck.neckAccessories"), mask ? "HERC" : "none");
  goto(partAt(clip, "neckAnim.neckAccessories"), mask ? "HERC" : "none");
  setShown(clip, "head.hair", !mask);
  const gloves = top === "male_HERCtop" || top === "female_HERCtop";
  for (const path of ["hand_backAnim.glove", "hand_frontAnim.glove", "arms.hand_back.glove", "arms.hand_front.glove"]) {
    setShown(clip, path, gloves);
  }
}

function paintRig(clip, rig) {
  for (const path of SKIN_PARTS) {
    paintFlat(partAt(clip, path), rig.skinColour);
  }
  for (const path of HAIR_PARTS) {
    paintFlat(partAt(clip, path), rig.hairColour);
  }
}

// Dresses a human clip as decoratePlayer does (F4:11979): heads, sleeves, torso, legs and shoes by frame label, then
// skin and hair tinted flat. options.backpack is true (the plain one), "premium" (the Survival Kit's) or false (none).
// Returns what it dressed with
export function decorate(clip, look = {}, clothes = {}, options = {}) {
  const dress = dressOf(look, clothes);
  const backpack = options.backpack ?? true;
  const rig = clip.rig ?? {};
  rig.skinColour = dress.skin;
  rig.hairColour = dress.hairColour;
  dressHeads(clip, dress);
  dressArms(clip, dress);
  dressTorso(partAt(clip, "arms.torso.torso"), dress, backpack);
  dressTorso(partAt(clip, "torsoAnim.torso"), dress, backpack);
  dressLegs(clip, dress);
  paintRig(clip, rig);
  dressHERC(clip, dress.face, dress.top);
  return dress;
}

// ---------- Weapons ----------

function weaponDef(ref) {
  return data.items?.weapons?.[ref] ?? data.items?.weapons?.hands ?? { ref: "hands", weaponType: "fists" };
}

// The weapon's art: its own label, or its base model's for built copies (a dull or sharpened knife)
function weaponLook(def) {
  return def.weaponBase ?? def.ref;
}

function showMods(item, mod) {
  const shown = MOD_PARTS[mod] ?? [];
  for (const name of ["scope", "suppressor"]) {
    setShown(item, name, shown.includes(name));
  }
}

function setHands(arms, def) {
  const byClass = CLASS_HANDS[def.weaponClass] ?? {};
  const byType = TYPE_HANDS[def.weaponType] ?? DEFAULT_TYPE_HANDS;
  for (const side of ["back", "front"]) {
    const pose = byType[side] ?? byClass[side];
    if (pose) {
      goto(arms.child(`hand_${side}`), pose);
    }
  }
}

// ---------- The rig ----------

export class Human {
  constructor(options) {
    this.clip = page.lib.makeExported(HUMAN);
    this.clip.rig = this;
    this.clip.owner = this;
    this.owner = this;
    this.sex = options.sex === "female" ? "female" : "male";
    this.scale = (this.sex === "female" ? FEMALE_SCALE : MALE_SCALE) / 100;
    this.facing = 1;
    this.look = { ...options.look, sex: this.sex };
    this.backpack = options.backpack ?? true;
    this.weapon = "hands";
    this.stored = "hands";
    this.mode = "upper";
    // The owner's starting flags (setupPlayer, F4:11866-11898)
    Object.assign(this, { alive: true, crouched: false, standing: true, struggling: false, grabbed: false });
    Object.assign(this, { shoving: false, firing: false, firingAnim: false, reloading: false, animating: false });
    this.meleeSwing = false;
    this.setFacing(1);
    this.setAnimMode("upper");
    goto(this.clip, "standing");
    this.setClothes(options.clothes ?? {});
    this.setWeapon(options.weapon ?? "hands", { stored: options.stored ?? "hands" });
  }

  get arms() {
    return this.clip.child("arms");
  }

  // The weapon in the upper-body arms
  get weaponClip() {
    return this.arms?.child("weapon") ?? null;
  }

  // The weapon the full-body animation holds
  get animWeapon() {
    return this.clip.child("animWeapon");
  }

  // From now on the art's flags and the rules' reads go to this actor, which gets the rig as actor.rig
  bind(actor) {
    for (const name of BOUND_FLAGS) {
      actor[name] ??= this[name];
    }
    actor.rig = this;
    actor.clip ??= this.clip;
    this.owner = actor;
    this.clip.owner = actor;
    return this;
  }

  // 1 faces right, -1 left; the size stays the same on both axes
  setFacing(dir) {
    this.facing = dir < 0 ? -1 : 1;
    this.clip.scale.set(this.facing * this.scale, this.scale);
  }

  // Dresses the rig in clothes ({ top, bottom, shoes, torso, head, face, eyes }), keeping its look
  setClothes(clothes) {
    this.clothes = { ...clothes };
    this.dress = decorate(this.clip, this.look, this.clothes, { backpack: this.backpack });
  }

  // A new look ({ skin, hair, hairColour, facialHair }) with the same clothes
  setLook(look) {
    this.look = { ...this.look, ...look, sex: this.sex };
    this.setClothes(this.clothes);
  }

  // The weapon in hand and, with stored, the one on the backpack (swapWeapons, F4:21003-21212). ref is a weapon's ref
  setWeapon(ref, { stored } = {}) {
    const def = weaponDef(ref);
    const arms = this.arms;
    this.weapon = def.ref;
    this.weaponType = def.weaponType;
    setShown(arms, "lowerArm_backFront", false);
    goto(arms, def.weaponType);
    goto(this.weaponClip, weaponLook(def));
    goto(this.animWeapon, weaponLook(def));
    setShown(this.weaponClip, "collision", false);
    showMods(this.weaponClip?.child("item"), def.mod);
    showMods(this.animWeapon?.child("item"), def.mod);
    setHands(arms, def);
    dressHERC(this.clip, this.dress.face, this.dress.top);
    if (stored !== undefined) {
      this.setStored(stored);
    }
  }

  // The weapon carried on the backpack
  setStored(ref) {
    const def = weaponDef(ref);
    this.stored = def.ref;
    for (const path of ["arms.torso.torso.backpackWeapon", "torsoAnim.torso.backpackWeapon"]) {
      const holder = partAt(this.clip, path);
      goto(holder, weaponLook(def));
      showMods(holder?.child("item"), def.mod);
    }
  }

  // The arms back in the weapon's hold pose (returnWeaponPosition, F4:21213)
  returnWeapon() {
    const def = weaponDef(this.weapon);
    goto(this.arms, def.weaponType);
    goto(this.weaponClip, weaponLook(def));
  }

  // "upper": the arms aim and the legs walk (the original's "default"); "full": one full-body animation for sprints,
  // shoves, struggles and deaths ("anim"). toggleAnimMode, F4:11655-11702
  setAnimMode(mode) {
    const full = mode === "full";
    this.mode = full ? "full" : "upper";
    if (full) {
      goto(this.arms, this.weaponType);
    }
    for (const path of UPPER_PARTS) {
      setShown(this.clip, path, !full);
    }
    for (const path of FULL_PARTS) {
      setShown(this.clip, path, full);
    }
    if (this.dress) {
      dressHERC(this.clip, this.dress.face, this.dress.top);
    }
  }

  // Crouching down or standing up through the art's transition (F4:12436-12446); instant jumps to the end pose
  setCrouch(on, { instant = false } = {}) {
    const owner = this.owner;
    owner.crouched = Boolean(on);
    owner.standing = !on;
    if (instant) {
      goto(this.clip, on ? "crouched" : "standing");
    } else {
      gotoPlay(this.clip, on ? "crouch" : "stand");
    }
  }

  destroy() {
    this.clip.destroy({ children: true });
  }
}

// A dressed human: { sex, look, clothes, weapon, stored, backpack }. Its clip is not yet in the world
export function makeHuman(options = {}) {
  return new Human(options);
}

// The player's makeHuman options, from the story: the look, the clothes worn, the weapons in the slots and the Survival
// Kit's backpack (premium is on for everyone)
export function storyLook(player = story.player) {
  const holding = player.slots[player.holding];
  const other = player.slots[player.holding === "primary" ? "secondary" : "primary"];
  return {
    sex: player.sex,
    look: player.look,
    clothes: player.clothes,
    weapon: holding,
    stored: other,
    backpack: "premium",
  };
}

// ---------- The art's hooks ----------

// The owner, clip and rig a called function works on
function targetOf(clip) {
  let up = clip;
  while (up && !up.rig) {
    up = up.parentClip;
  }
  return { clip, owner: ownerOf(clip), rig: up?.rig ?? null };
}

function callRig(name, target, args) {
  const fn = rigCalls.get(name);
  if (!fn) {
    missingCalls.add(name);
    return;
  }
  fn(target, ...args);
}

// Calls a function the art calls by name, for a frame script the page ports itself: on clip's owner and rig
export function rigCall(name, clip, ...args) {
  callRig(name, targetOf(clip), args);
}

// Registers a function the art calls by name: fn({ clip, owner, rig }, ...args)
export function onRigCall(name, fn) {
  rigCalls.set(name, fn);
}

// The hook kinds of port.json's art.hooks and art.patterns the rigs need, as game.js's onHook takes them: fn(arg,
// clip, values) returning true when done. golabel and go serve every clip
export const RIG_HOOKS = {
  go(arg, clip) {
    clip.play();
    return true;
  },
  golabel(label, clip) {
    goto(clip, label);
    return true;
  },
  childpos(path, clip, [axis, value]) {
    moveTo(partAt(clip, path), axis === "x" ? value : null, axis === "y" ? value : null);
    return true;
  },
  // "this.neck.originX = this.neck._x;": where the part rests, for the recoil to push from
  origin(name, clip, [axis]) {
    const part = clip.child(name);
    if (part) {
      part[axis === "x" ? "originX" : "originY"] = part[axis];
    }
    return true;
  },
  childvis(path, clip, [on]) {
    setShown(clip, path, Boolean(on));
    return true;
  },
  childgoto(path, clip, [label, playing]) {
    const part = partAt(clip, path);
    if (part) {
      if (playing) {
        gotoPlay(part, label);
      } else {
        goto(part, label);
      }
    }
    return true;
  },
  childplay(path, clip) {
    partAt(clip, path)?.play?.();
    return true;
  },
  set(path, clip, [name, value]) {
    if (path === "_root") {
      rootFlags[name] = value;
    } else {
      const owner = ownerOf(partAt(clip, path));
      if (owner) {
        owner[name] = value;
      }
    }
    return true;
  },
  inc(path, clip, [name]) {
    const owner = ownerOf(partAt(clip, path));
    if (owner) {
      owner[name] = (owner[name] ?? 0) + 1;
    }
    return true;
  },
  call(name, clip, args) {
    callRig(name, targetOf(clip), args);
    return true;
  },
  callparent(name, clip, args) {
    const parent = clip.parentClip;
    if (parent) {
      callRig(name, targetOf(parent), args);
    }
    return true;
  },
  callplayer(name, clip, args) {
    const playerClip = world.player?.clip;
    if (playerClip) {
      callRig(name, targetOf(playerClip), args);
    }
    return true;
  },
  // "if(this.alive == true) { gotoAndStop(label); play(); }"
  ifalive(label, clip) {
    if (ownerOf(clip).alive === true) {
      gotoPlay(clip, label);
    }
    return true;
  },
  // The same on stumbleMoving or grabbed. The grabbed one also clears grabbing first (S6800 frame 639), a line the
  // pattern folds in
  ifflag(flag, clip, [op, value, label]) {
    const owner = ownerOf(clip);
    if (flag === "grabbed") {
      owner.grabbing = false;
    }
    const same = owner[flag] === (value === "true");
    if (op === "==" ? same : !same) {
      gotoPlay(clip, label);
    }
    return true;
  },
  ifgrabbedplay(arg, clip) {
    const owner = ownerOf(clip);
    if (owner.grabbed === true) {
      owner.animating = true;
      clip.play();
    }
    return true;
  },
};

// The headMask load handler on a head's blood (S4770, depth 28): the spray is cut to the head's outline
export const RIG_LOAD_ACTIONS = {
  headMask(node, [exportName]) {
    const spray = node.child?.("bloodSpray");
    if (!spray) {
      return;
    }
    const mask = node.attach(page.lib.makeExported(exportName), "headMask");
    spray.mask = mask;
  },
};

// ---------- Frame scripts ----------

function placeHeadNeck(clip, [headX, headY, neckX, neckY]) {
  moveTo(clip.child("head"), headX, headY);
  moveTo(clip.child("neck"), neckX, neckY);
}

function lowerHeadNeck(clip, [headY, neckY]) {
  moveTo(clip.child("head"), null, headY);
  moveTo(clip.child("neck"), null, neckY);
}

// A shove's head and neck offsets, lower when crouched (S4925 frames 204-239)
function shoveFrame(clip, frame) {
  const owner = ownerOf(clip);
  const shove = frame < 220 ? SHOVE : SHOVE_CROUCHED;
  const end = SHOVE_ENDS[frame];
  if (end) {
    clip.stop();
    placeHeadNeck(clip, end[1]);
    if (owner.crouched) {
      lowerHeadNeck(clip, end[0].low);
    }
    goto(clip, owner.crouched ? "crouched" : "standing");
    return;
  }
  if (shove.poses[frame]) {
    placeHeadNeck(clip, shove.poses[frame]);
  }
  if (owner.crouched) {
    lowerHeadNeck(clip, shove.low);
  }
}

// A struggle's start waits for the grab (frame 155) and its end loops on or shoves free (frame 185)
function struggleFrame(clip, frame) {
  const owner = ownerOf(clip);
  if (frame === 155) {
    owner.struggleAnim = true;
    if (owner.struggling === true) {
      clip.play();
    }
    return;
  }
  gotoPlay(clip, owner.struggling === true ? "struggleLoop" : "struggleShove");
}

// The sprint loops while there is stamina, and drops to a walk in the upper-body pose when it runs out (frames 333
// and 338). The original read the player's stamina for every rig; a rig whose owner has its own reads that
function sprintFrame(clip) {
  const owner = ownerOf(clip);
  const stamina = owner.stamina ?? world.player?.stamina ?? 0;
  if (owner.alive === true && stamina > 0) {
    gotoPlay(clip, "sprint");
    return;
  }
  clip.rig?.setAnimMode("upper");
  gotoPlay(clip, "walk");
}

function idleFrame(clip) {
  const pick = Math.floor(page.lib.random() * IDLE_ODDS);
  gotoPlay(clip, ["idleHeadScratch", "idleHandsOnHips"][pick] ?? "idle");
}

// S4925's frame scripts
function humanScript(clip, frame) {
  if (frame === 155 || frame === 185) {
    struggleFrame(clip, frame);
  } else if (frame >= 204 && frame <= 239) {
    shoveFrame(clip, frame);
  } else if (frame === 333 || frame === 338) {
    sprintFrame(clip);
  } else if (frame === 498) {
    idleFrame(clip);
  }
}

// S4906, placed in the arms for a one-hand or two-hand swing: the head and neck of the human two clips up follow the
// swing, lower when crouched
function swingScript(clip, frame) {
  const human = clip.parentClip?.parentClip;
  if (!human) {
    return;
  }
  const pose = SWING_POSES[frame];
  if (pose) {
    if (pose[0] !== null) {
      moveTo(human.child("head"), pose[0], null);
    }
    moveTo(human.child("neck"), pose[1], null);
  }
  if (ownerOf(human).crouched) {
    lowerHeadNeck(human, [SWING_LOW, SWING_LOW]);
  }
}

// Hangs the rig's frame scripts and its own called functions on the page's library. Sprite 4888 frame 15 and 6865
// frame 22 are empty `if` blocks in the original, so nothing is registered for them
export function initRig(owner) {
  page = owner;
  page.lib.scripts.set(HUMAN_SPRITE, humanScript);
  page.lib.scripts.set(SWING_SPRITE, swingScript);
  onRigCall("toggleAnimMode", (target, state) => target.rig?.setAnimMode(state === "anim" ? "full" : "upper"));
  onRigCall("returnWeaponPosition", (target) => target.rig?.returnWeapon());
}

// The rig's state for checks
export const rig = { makeHuman, decorate, storyLook, rootFlags, missingCalls, partAt, frameFor, takeOver, paintFlat };
