// Drops: which zombie carries a backpack, what a dead one's backpack holds, the bouncing pickups that come out of it
// and taking one with E.
//
// A zombie is a dropper when enough game minutes have passed since the last one (zombieDropPickups F4:1784). On death
// its backpack (dropBackPack F4:15994) is thrown as a pile picture and one pickup per item, which fly from the chest
// away from the way the zombie faces and land on the floor (createBounceObject "backpack" F4:10036, the pickup's own
// step F4:10230). A landed pickup glints and waits to be taken; at most 300 things thrown from bodies exist in a room,
// and the oldest goes when another is thrown.
//
// An item a backpack holds is { kind, ref, count }: kind "item" (ref is the item's key), "ammo" (ref is the ammo type,
// count the rounds) or "cash" (count the dollars). What the backpack holds is rolled with the story's dice; where the
// pickups fly and how they glint is picture only, so it rolls with Math.random.
import { originOf } from "./collide.js";
import { data } from "./data.js";
import { player } from "./player.js";
import { addItem } from "./inventory.js";
import { goto, partAt } from "./rig.js";
import { rng } from "./rng.js";
import { layers, onRoom, room } from "./rooms.js";
import { sound } from "./sound.js";
import { findItem, story } from "./story.js";
import { START_TIME, world } from "./world.js";

// Used until the converted constants load (F4:26135, 27547-27559, 25430-25436)
const DEFAULTS = {
  dropperInterval: 20,
  dropHealthMin: 20,
  dropAmmoMin: 2,
  dropRateAmmoBase: 40,
  dropRateCash: 33,
  runNGunAmmoDropMod: 1.4,
  avgMagDiv: 1.5,
  cashAmountMod: 3.3,
  particleResetNum: 300,
  pickupEdgeBuffer: 100,
  playerScale: 55,
  depth_world_pickups: 12010,
  depth_world_player: 115000,
};
// A backpack's worth is this many items, and a medical item for a hurt player and the rest come out of it
const BUDGET_MIN = 1;
const BUDGET_SPREAD = 3;
// The most tries the ammo rolls and the cash rolls make: the count is 1 to 3, and one more try is made (kept)
const ROLL_SPREAD = 3;
// Luck's share of a backpack: the budget gains up to a seventh of it, the ammo rolls half of it, a rarity a quarter
const LUCK_BUDGET = 7;
const LUCK_AMMO_TABLE = 2;
const LUCK_AMMO_COUNT = 1.5;
const LUCK_RARITY = 4;
// The hurt player's backpack timer runs this many minutes shorter
const HURT_DROP_BONUS = 5;
// The pile picture falls straight down; each pickup after the first flies 3.5 px a step further for each place in line
const FLY_STEP = 3.5;
const FLY_UP = 11;
// A thrown pickup falls 1.5 faster every step and loses 2% of its sideways speed (F4:10236-10237)
const GRAVITY = 1.5;
const FRICTION = 0.98;
// It lands somewhere in this many pixels above the floor
const LAND_BAND = 40;
// Its sideways speed turns round one time in this many (F4:10211)
const TURN_ODDS = 8;
// A landed pickup is taken from a box this wide around it (the collision block it grows, F4:10300-10306)
const PICKUP_BOX = 65;
// The picture a pickup with no frame of its own wears
const GENERIC_PICKUP = "box";
// The glint over a landed pickup is this see-through
const SHINE_ALPHA = 0.75;
const MOST_RECORDED = 200;

let page = null;
let artReady = false;
let serial = 0;
// Everything thrown from bodies that is still in the room, oldest first: { node, item, across, up, angle, stopped }
let thrown = [];

// The pickups waiting on the floor, in the order they landed: the list the interact system reads. Each is the piece
// thrown ({ item, node, glow, mask, name, box }); take one with takePickup
export const pickups = world.drops;
// What was picked up, newest last, for checks
const picked = [];

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULTS[name];
}

function roll(count) {
  return Math.floor(Math.random() * count);
}

// ---------- Who carries a backpack ----------

function healthPercent() {
  return player.healthMax > 0 ? Math.round((player.health / player.healthMax) * 100) : 100;
}

// Whether the zombie being made carries a backpack: more than 20 game minutes (15 while the player is at 20% health or
// less) plus up to 6 since the last one. Passing hands out the backpack and starts the wait over. Asked of every zombie
// made, as the original does; crawlers and dogs ask and never carry one (zombieDropPickups F4:1784)
export function rollDropper() {
  const interval = constant("dropperInterval");
  const hurt = healthPercent() <= constant("dropHealthMin") ? HURT_DROP_BONUS : 0;
  const last = story.lastDropTime ?? START_TIME;
  if (world.time - last > Math.round(interval - hurt) + rng.random(interval / 3)) {
    story.lastDropTime = world.time;
    return true;
  }
  return false;
}

// ---------- What a backpack holds ----------

function luck() {
  return story.player?.attributes?.luck ?? 0;
}

// The original's getRandRange: a whole number from min to max, the two ends half as likely as the rest
export function rangeRound(min, max) {
  return Math.round(rng.float() * (max - min)) + min;
}

// Ammo chances: Run & Gun hands out 1.4 times as much (setAmmoDropRate F4:15985)
function ammoRate() {
  const base = constant("dropRateAmmoBase");
  return story.mode === "runAndGun" ? Math.ceil(base * constant("runNGunAmmoDropMod")) : base;
}

function ammoItem(type, count) {
  return { kind: "ammo", ref: type, count };
}

// Rounds for a gun the player carries when they hold under twice its magazine: a magazine's worth and a bit, never more
// than the most of one pile (F4:16024-16041; the second gun's cap applies, as it does for the first)
function topUp(ref) {
  const weapon = data.items.weapons[ref];
  const info = data.items.ammo[weapon?.ammoType];
  if (!info || (story.ammo[weapon.ammoType] ?? 0) >= Math.round(weapon.maxAmmo * constant("dropAmmoMin"))) {
    return null;
  }
  const count = Math.round(rng.random(info.avgMag) + info.avgMag / constant("avgMagDiv"));
  return ammoItem(weapon.ammoType, Math.min(count, info.max));
}

// The guns in both weapon slots, the one in the hands first
function carriedGuns() {
  const slots = story.player.slots;
  const other = story.player.holding === "primary" ? "secondary" : "primary";
  return [slots[story.player.holding], slots[other]];
}

// A pile of ammo from the rarity tables: the table is picked by danger and half the luck, the count between a
// magazine's third and a magazine and a bit
function rarityAmmo(danger) {
  const top = Math.min(Math.round(danger + luck() / LUCK_AMMO_TABLE), data.items.rarityMax);
  const types = data.items.ammoRarityTables[String(rng.random(top) + 1)] ?? [];
  const type = types[rng.random(types.length)];
  const info = data.items.ammo[type];
  if (!info) {
    return null;
  }
  const high = Math.round(info.avgMag + rng.random(luck() / LUCK_AMMO_COUNT));
  const low = Math.round(info.avgMag / constant("avgMagDiv"));
  const count = Math.min(rangeRound(low, high), info.max);
  return count > 0 ? ammoItem(type, count) : null;
}

// A handful of cash: up to the danger x 3.3 plus the luck, at most 1,001
function cashItem(danger) {
  const top = Math.min(Math.round(danger * constant("cashAmountMod") + luck()), data.items.cash.max);
  const count = rangeRound(1, top);
  return count >= 1 ? { kind: "cash", ref: "cash", count } : null;
}

// An item from the rarity tables: the rarity is a roll under the danger plus a roll under a quarter of the luck. A
// container's lucky find rolls the same way (searchContainer F4:13898)
export function rarityItem(danger) {
  const level = Math.round(rng.random(danger) + 1) + Math.round(rng.random(luck() / LUCK_RARITY));
  const rarity = Math.min(level, data.items.rarityMax);
  const table = data.items.rarityTables[String(rarity)] ?? [];
  const ref = table[rng.random(table.length)];
  return ref ? { kind: "item", ref } : null;
}

// Tries up to 2 to 4 times (the count rolls 1 to 3 and the loop runs one more) to make a pile; ammo piles use up one
// item of the budget each, and the cash rolls use none. Returns the piles and the budget left
function pileRolls(items, budget, rate, make, spend) {
  let left = budget;
  const tries = rng.random(ROLL_SPREAD) + 1;
  for (let n = 0; n <= tries; n += 1) {
    if (rng.random(100) <= rate && left > 0) {
      left -= spend ? 1 : 0;
      const item = make();
      if (item) {
        items.push(item);
      }
    }
  }
  return left;
}

// What a zombie's backpack holds, rolled as dropBackPack does (F4:15994-16113): a budget of 1 to 3 items plus a share
// of the luck; a medical item for a player at 20% health or less; ammo for each gun carried that runs low; food for a
// player above 80 hunger in Survivor; ammo piles, cash, and the rest of the budget from the rarity tables. Returns the
// items in the order they come out
export function rollBackpack(zombie) {
  const danger = zombie.danger ?? 0;
  const items = [];
  let budget = rng.random(BUDGET_SPREAD) + BUDGET_MIN + Math.round(rng.random(luck() / LUCK_BUDGET));
  if (healthPercent() <= constant("dropHealthMin") && budget > 0) {
    items.push({ kind: "item", ref: rng.pick(Object.keys(data.items.medical)) });
  }
  if (rng.random(100) <= ammoRate() * 2) {
    for (const ref of carriedGuns()) {
      const ammo = budget > 0 ? topUp(ref) : null;
      if (ammo) {
        items.push(ammo);
      }
    }
  }
  if (story.player.hunger > 80 && budget > 0 && story.mode === "survivor") {
    items.push({ kind: "item", ref: rng.pick(Object.keys(data.items.food)) });
  }
  budget = pileRolls(items, budget, ammoRate(), () => rarityAmmo(danger), true);
  pileRolls(items, budget, constant("dropRateCash"), () => cashItem(danger), false);
  for (; budget > 0; budget -= 1) {
    const item = rarityItem(danger);
    if (item) {
      items.push(item);
    }
  }
  return items;
}

// ---------- Names and pictures ----------

// What a pickup is called, for prompts: the item's name, with its count where it has one
export function itemName(item) {
  if (item.kind === "cash") {
    return data.items.cash.name.replace("{n}", item.count);
  }
  if (item.kind === "ammo") {
    return data.items.ammo[item.ref].name.replace("{n}", item.count);
  }
  return findItem(item.ref)?.item.name ?? item.ref;
}

// The frame of the pickup picture an item uses, and the weapon part it carries (pickupDrop F4:10050-10097): a weapon
// shows its base gun with the part drawn on
function pictureOf(item) {
  if (item.kind === "cash") {
    return { label: data.items.cash.pickup };
  }
  if (item.kind === "ammo") {
    return { label: data.items.ammo[item.ref].pickup };
  }
  const found = findItem(item.ref);
  const row = found?.item ?? {};
  const label = found?.table === "weapons" ? (row.weaponBase ?? row.pickup) : row.pickup;
  return { label, mod: row.mod, ref: item.ref };
}

function setShown(clip, path, on) {
  const part = partAt(clip, path);
  if (part) {
    part.visible = on;
  }
}

// Dresses a pickupDrop clip as an item: its frame, a scope or a suppressor where the part has one, a hat's shape
export function dressPickup(clip, item) {
  const { label, mod, ref } = pictureOf(item);
  if (!goto(clip, label)) {
    goto(clip, GENERIC_PICKUP);
  }
  setShown(clip, "item.scope", mod === "scope" || mod === "specOps");
  setShown(clip, "item.suppressor", mod === "suppressed" || mod === "specOps");
  if (label === "hat") {
    goto(clip.child("item"), ref);
  }
}

// ---------- Throwing ----------

function keep(entry) {
  picked.push({ ...entry, frame: world.frame });
  if (picked.length > MOST_RECORDED) {
    picked.shift();
  }
}

function facingOf(owner) {
  return (owner.clip?.scale.x ?? owner.facing ?? 1) < 0 ? -1 : 1;
}

function drawable() {
  return artReady && Boolean(page.lib.exported("pickupDrop"));
}

// Takes a piece out of the room: its picture, its glint and its place in the lists
function remove(piece) {
  thrown = thrown.filter((each) => each !== piece);
  const at = pickups.indexOf(piece);
  if (at >= 0) {
    pickups.splice(at, 1);
  }
  for (const node of [piece.glow, piece.mask, piece.node]) {
    if (node && !node.destroyed) {
      node.destroy({ children: true });
    }
  }
}

// Throws the pile picture (item null) or one item's pickup from a body's chest: sideways away from the way the body
// faces, 3.5 px a step for each place in line, and up. Returns the piece, or null when the art isn't in
function throwPiece(owner, item, place) {
  if (!drawable()) {
    return null;
  }
  const clip = page.lib.makeExported(item ? "pickupDrop" : "backpack");
  if (item) {
    dressPickup(clip, item);
  }
  const chest = owner.clip ? partAt(owner.clip, "collisionChest") : null;
  const start = chest ? originOf(chest) : { x: owner.x, y: owner.y };
  const side = facingOf(owner);
  const size = constant("playerScale") / 100;
  clip.eventMode = "none";
  clip.x = start.x;
  clip.y = start.y;
  clip.scale.set(side * size, size);
  serial += 1;
  const depth = constant("depth_world_pickups") - constant("depth_world_player");
  clip.zIndex = depth + (serial % constant("particleResetNum"));
  layers.actors.addChild(clip);
  const across = side * Math.round(FLY_STEP * place);
  const piece = {
    node: clip,
    item,
    across: roll(TURN_ODDS) === 0 ? -across : across,
    up: -FLY_UP + (Math.random() * FLY_UP) / 2,
    angle: ((roll(2) > 0 ? roll(60) : roll(60) + 300) * Math.PI) / 180,
    stopped: false,
    name: item ? itemName(item) : "backpack",
    // Where E takes it from: a box 65 px across around it
    get box() {
      const half = PICKUP_BOX / 2;
      return { x: this.node.x - half, y: this.node.y - half, w: PICKUP_BOX, h: PICKUP_BOX };
    },
  };
  thrown.push(piece);
  while (thrown.length > constant("particleResetNum")) {
    remove(thrown[0]);
  }
  return piece;
}

// A landed pickup glints: the sweep of light is cut to the shape of the item by a copy of the pickup (itemShine
// F4:10308-10360). The glint keeps the room's light off it, so it shows in the dark
function addShine(piece) {
  if (!page.lib.exported("itemShine")) {
    return;
  }
  const mask = page.lib.makeExported("pickupDrop");
  dressPickup(mask, piece.item);
  mask.eventMode = "none";
  mask.x = piece.node.x;
  mask.y = piece.node.y;
  mask.scale.set(piece.node.scale.x, piece.node.scale.y);
  const glow = page.lib.makeExported("itemShine");
  glow.eventMode = "none";
  glow.x = piece.node.x;
  glow.y = piece.node.y;
  glow.alpha = SHINE_ALPHA;
  layers.shots.addChild(mask);
  layers.shots.addChild(glow);
  glow.mask = mask;
  piece.glow = glow;
  piece.mask = mask;
}

// A pickup comes to rest and waits for E. The pile picture just lies where it fell
function land(piece) {
  piece.stopped = true;
  if (!piece.item) {
    return;
  }
  addShine(piece);
  pickups.push(piece);
}

// One step of a thrown pickup (the clip's onEnterFrame, F4:10230-10321)
function stepPiece(piece) {
  const node = piece.node;
  piece.across *= FRICTION;
  node.x -= Math.cos(piece.angle) * piece.across;
  piece.up += GRAVITY;
  node.y += piece.up;
  if (node.y > room.floorY - roll(LAND_BAND)) {
    land(piece);
    return;
  }
  const bounds = room.markers.bounds ?? { x: 0, w: room.width };
  const edge = constant("pickupEdgeBuffer");
  if (node.x <= bounds.x + edge || node.x >= bounds.x + bounds.w - edge) {
    piece.across = 0;
  }
}

function stepDrops() {
  for (const piece of [...thrown]) {
    if (piece.node.destroyed) {
      remove(piece);
    } else if (!piece.stopped) {
      stepPiece(piece);
    }
  }
}

// A dead dropper's backpack: its own backpack leaves its back, the pile picture and one pickup per item fly out of its
// chest. Returns the items
export function dropBackPack(zombie) {
  setShown(zombie.clip, "torso.backpack", false);
  const items = rollBackpack(zombie);
  throwPiece(zombie, null, 0);
  items.forEach((item, place) => throwPiece(zombie, item, place));
  return items;
}

// An item thrown from someone's chest as a pickup, as a dying companion drops their weapon (dropItem F4:16160)
export function dropItem(ref, owner) {
  return throwPiece(owner, { kind: "item", ref, count: 1 }, 0);
}

// ---------- Taking ----------

// A pickup goes into the backpack: cash and ammo are counts, everything else a row of its own
function putAway(item) {
  if (item.kind === "cash") {
    addItem("cash", { count: item.count });
  } else if (item.kind === "ammo") {
    addItem(`ammo${item.ref}`, { count: item.count });
  } else {
    addItem(item.ref);
  }
}

// E on a pickup: its sound, the item in the backpack, and the pickup, its glint and the glint's shape gone
// (pickupItem F4:16149). Returns false for one already taken
export function takePickup(piece) {
  if (!pickups.includes(piece)) {
    return false;
  }
  sound.play(`sound_pickupItem${roll(2) + 1}`);
  putAway(piece.item);
  keep({ ...piece.item, name: piece.name });
  remove(piece);
  return true;
}

// ---------- Setup ----------

function clearRoom() {
  thrown = [];
  pickups.length = 0;
}

export function initDrops(owner) {
  page = owner;
  page.lib
    .need(["pickupDrop", "backpack", "itemShine"].map((name) => page.lib.exported(name)))
    .then(() => {
      artReady = true;
    })
    .catch((e) => console.warn("Union City: the pickups' art didn't load", e));
  onRoom("build", clearRoom);
  world.stage("shots", stepDrops);
}

// Helpers for page.py checks
export const dropsDebug = {
  // What n backpacks would hold, rolled for a zombie of that danger: a list of readable names for each
  rollBackpacks(n = 5, danger = 10) {
    return Array.from({ length: n }, () => rollBackpack({ danger }).map((item) => itemName(item)));
  },

  // Throws a backpack from a zombie as it dies would, whatever its own flag says. Returns the names of the items
  dropFrom(zombie) {
    return dropBackPack(zombie).map((item) => itemName(item));
  },

  // The pickups on the floor, with where they are
  pickups() {
    return pickups.map((piece) => ({ name: piece.name, x: Math.round(piece.node.x), y: Math.round(piece.node.y) }));
  },

  // Takes the pickup at that place in the list
  take(place = 0) {
    return takePickup(pickups[place]);
  },

  // What has been picked up, and how many things are thrown or waiting
  dropState() {
    return { picked: picked.map((each) => each.name), thrown: thrown.length, waiting: pickups.length };
  },

  lastDropTime(value) {
    if (value !== undefined) {
      story.lastDropTime = value;
    }
    return story.lastDropTime;
  },

  rollDropper,
};

export const drops = {
  rollDropper,
  rollBackpack,
  dropBackPack,
  takePickup,
  itemName,
  pickups,
  get lastDropTime() {
    return story.lastDropTime ?? START_TIME;
  },
  set lastDropTime(value) {
    story.lastDropTime = value;
  },
};
