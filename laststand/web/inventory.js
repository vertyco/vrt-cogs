// The inventory: what the player carries, what it weighs, using things, wearing and wielding them, armour and throwing
// them away (addToInventory F4:8243, destroyItem F4:8350, sortInventory F4:8386, useItem F4:8421, equipClothing
// F4:7740, equipWeapon F4:7673, unEquipWeapon F4:7699, getTotalWeight F4:7131).
//
// The backpack is story.inventory: one row for every item, except weapons' ammo and the player's cash, which are plain
// counts (story.ammo, story.player.cash) that rowsFor() shows as one row each, in the places the original's rows sit.
// Only weight limits what is carried. The panels that draw the list live in panels.js and backpack.js; this file is the
// rules.
import { data } from "./data.js";
import { adjustVital, adjustedSkill, carriedWeight, healPerm, player, recalcMovement } from "./player.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { addRow, byRow, findItem, story, takeOff, wear } from "./story.js";
import { returnRounds, swapTo } from "./weapons.js";

// "ammo556_50" is 50 rounds of 5.56, "ammo556" a count's worth of them; "cash_10" is $10, "cash" a count's worth
const AMMO_REF = /^ammo(.+?)(?:_(\d+))?$/;
const CASH_REF = /^cash(?:_(\d+))?$/;
// The types a filter lets through (buildInventory F4:8134)
const FILTERS = {
  all: ["junk", "books", "weapon", "clothing", "ammo", "food", "meds", "money", "questItem"],
  weapons: ["weapon"],
  aid: ["food", "meds", "books"],
  clothing: ["clothing"],
  ammo: ["ammo"],
  junk: ["money", "junk"],
  quest: ["questItem"],
};
// Where a worn item's armour is read from, by the zone a hit lands on. Only the head and the armour slot protect
const ARMOUR_SLOTS = { head: "head", chest: "torso" };
const SLOTS = { 1: "primary", 2: "secondary", primary: "primary", secondary: "secondary" };
const DRINKS = new Set(["sodaBottle", "sodaCan", "water"]);
const CASH_ROW = { ref: "cash", type: "money", id: 0, eqd: false, virtual: true };
// The sleep need a No ZZZ takes off is shown ten times the item's number, as adjustVital takes it off
const SLEEP_SHOWN_FACTOR = 10;

const countListeners = [];

function constant(name) {
  return data.actors.constants[name];
}

// Registers fn(key, amount) for each counter the inventory adds to. The keys are the names the original's checkAch
// takes: pickupJunk, cash (the dollars), eatFood, useHeal, usePills, readBook, skillful and masterful
export function onInventoryCount(fn) {
  countListeners.push(fn);
}

function count(key, amount = 1) {
  for (const fn of countListeners) {
    try {
      fn(key, amount);
    } catch (e) {
      console.warn(`Union City: a counter listener failed for ${key}`, e);
    }
  }
}

function slotName(slot) {
  const name = SLOTS[slot];
  if (!name) {
    throw new Error(`Union City: no weapon slot called ${slot}`);
  }
  return name;
}

// ---------- Rows ----------

// The backpack in the original's order (sortInventory F4:8386)
export function sortInventory() {
  story.inventory.sort(byRow);
}

// What a row is, as the item tables hold it: an item, an ammo type or the cash
export function definition(row) {
  if (row.type === "money") {
    return data.items.cash;
  }
  if (row.type === "ammo") {
    return data.items.ammo[row.ammoType];
  }
  return findItem(row.ref).item;
}

export function weightOf(row) {
  return definition(row).weight ?? 0;
}

// The words on a row, in capitals: the name, or for ammo and cash the name and how much is held
export function label(row) {
  if (row.type === "money") {
    return `CASH [ $${row.count} ]`;
  }
  if (row.type === "ammo") {
    return `${definition(row).invName} [ ${row.count} ]`.toUpperCase();
  }
  return definition(row).name.toUpperCase();
}

// The rows of the cash and of each kind of ammo held, as the list shows them. Cash is always listed; ammo while any is
// held. They have negative ids (cash 0) so a row can be told from a real one by id as well as by `virtual`
function countRows() {
  const rows = [{ ...CASH_ROW, st: data.items.cash.st, count: story.player.cash }];
  data.items.ammoTypes.forEach((type, place) => {
    const held = story.ammo[type];
    if (held > 0) {
      const info = data.items.ammo[type];
      const row = { ref: info.pickup, type: "ammo", ammoType: type, id: -(place + 1), st: info.st };
      rows.push({ ...row, eqd: false, count: held, virtual: true });
    }
  });
  return rows;
}

// Every row the backpack lists under a filter ("all", "weapons", "aid", "clothing", "ammo", "junk", "quest"), in order
export function rowsFor(filter = "all") {
  const allowed = new Set(FILTERS[filter] ?? FILTERS.all);
  const rows = [...story.inventory, ...countRows()].filter((row) => allowed.has(row.type));
  return rows.sort(byRow);
}

// ---------- Taking things ----------

// Reads a ref and a count into what to add. An item is added `count` times; cash and ammo add `count` times the number
// in their ref (or just `count` without one)
function parseRef(ref, amount) {
  const times = amount ?? 1;
  const cash = CASH_REF.exec(ref);
  if (cash) {
    return { kind: "cash", amount: Number(cash[1] ?? 1) * times };
  }
  const ammo = AMMO_REF.exec(ref);
  if (ammo && data.items.ammoTypes.includes(ammo[1])) {
    return { kind: "ammo", type: ammo[1], amount: Number(ammo[2] ?? 1) * times };
  }
  return { kind: "item", ref, times };
}

function addCash(amount) {
  story.player.cash += amount;
  count("cash", amount);
}

// Ammo of one type, up to the most the game holds of a type
function addAmmo(type, rounds) {
  story.ammo[type] = Math.min(story.ammo[type] + rounds, data.items.ammoMaxAmount);
}

function addCopies(ref, times, { lucky, prize }) {
  let row = null;
  for (let i = 0; i < times; i += 1) {
    row = addRow(ref);
    if (row.type === "junk") {
      count("pickupJunk");
    }
    if (lucky) {
      row.lucky = true;
    }
    if (prize) {
      row.prize = true;
    }
  }
  return row;
}

// Puts an item in the backpack. It always works; the weight may now be over the limit. ref is an item's key ("M16A2",
// "cannedBeans"), an ammo item ("ammo556_50" or "ammo556" with a count) or cash ("cash_10", or "cash" with a count).
// lucky and prize mark the row (a lucky find, an achievement prize). Returns the last row made, or null for cash and
// ammo
export function addItem(ref, { count: amount, lucky = false, prize = false } = {}) {
  const parsed = parseRef(ref, amount);
  let row = null;
  if (parsed.kind === "cash") {
    addCash(parsed.amount);
  } else if (parsed.kind === "ammo") {
    addAmmo(parsed.type, parsed.amount);
  } else {
    row = addCopies(parsed.ref, parsed.times, { lucky, prize });
  }
  savePoint("item");
  recalcMovement();
  return row;
}

// ---------- Weight ----------

// What the backpack weighs, to a tenth of a pound; an empty bag weighs nothing
export function weight() {
  return carriedWeight();
}

// What the player can carry
export function carry() {
  return story.player.carryWeight;
}

// ---------- Clothes and armour ----------

// The player's rig is dressed again in what the story says is worn
function redress() {
  player.rig?.setClothes(story.player.clothes);
}

// How much of a hit's damage gets through on a body part: 1 for none, a smaller number for more protection. zone is
// "head" or "chest". It reads what is worn now, so a room change or a load never loses it. The belly and the legs are
// never armoured (the Survivor Jacket's number sits on a top, which counts for nothing, and stays that way)
export function armour(zone) {
  const slot = ARMOUR_SLOTS[String(zone).toLowerCase()];
  const worn = slot ? story.player?.clothes[slot] : null;
  return (worn && findItem(worn)?.item.bonus) || 1;
}

// Wears the clothing in a row, or takes it off if it is worn
function toggleClothing(row) {
  if (row.eqd) {
    takeOff(row);
    sound.play("sound_inventoryClothingOff");
  } else {
    wear(row);
    sound.play("sound_inventoryClothingOn");
  }
  redress();
}

// ---------- Weapons ----------

// Empties a weapon slot: the weapon in it gives its loaded rounds back and goes back to the pack
function clearSlot(slot) {
  for (const row of story.inventory) {
    if (row.type === "weapon" && row.slot === slot) {
      returnRounds(row);
      Object.assign(row, { eqd: false, slot: "none" });
    }
  }
  story.player.slots[slot] = "hands";
}

// Puts a weapon row in a slot (1, 2, "primary" or "secondary") and into the hands. What was in the slot goes back to
// the pack. A weapon already in a slot stays where it is. Returns whether it was equipped
export function equip(slot, row) {
  const place = slotName(slot);
  if (row.type !== "weapon" || row.eqd || !story.inventory.includes(row)) {
    return false;
  }
  clearSlot(place);
  Object.assign(row, { eqd: true, slot: place });
  story.player.slots[place] = row.ref;
  sound.play("sound_inventoryEquipConfirm");
  swapTo(place);
  return true;
}

// Empties a slot and takes the other weapon in hand
export function unequip(slot) {
  const place = slotName(slot);
  clearSlot(place);
  swapTo(place === "primary" ? "secondary" : "primary");
}

// ---------- Throwing away ----------

// Takes a row out of the backpack for good, first taking it off or out of its slot (destroyItem F4:8350). A thrown
// grenade or RPG keeps the round it added when it was picked up. Returns whether the row was there
export function removeRow(row) {
  const place = story.inventory.indexOf(row);
  if (place < 0) {
    return false;
  }
  if (row.eqd && row.type === "clothing") {
    takeOff(row);
    redress();
  }
  if (row.eqd && row.type === "weapon") {
    unequip(row.slot);
  }
  story.inventory.splice(place, 1);
  recalcMovement();
  return true;
}

function needsConfirm(row) {
  const item = definition(row);
  return item.premium === true || item.reward === true || row.prize === true;
}

// The trash can on a row. Cash, ammo and quest items can't be thrown away ("refused"). A premium or prize item, which
// can't be got again, is "confirm" until it is asked again with confirmed true. Otherwise it is "deleted"
export function deleteRow(row, confirmed = false) {
  if (!story.inventory.includes(row) || row.type === "questItem") {
    return "refused";
  }
  if (needsConfirm(row) && !confirmed) {
    return "confirm";
  }
  sound.play("sound_trash");
  removeRow(row);
  return "deleted";
}

// ---------- Using things ----------

// Raises a skill by n, to the most. A skill at 50 or 100 counts toward its achievement (addSkillPoints F4:13500)
export function addSkillPoints(skill, n) {
  const skills = story.player.skills;
  const most = constant("skillMax");
  skills[skill] = Math.min(most, skills[skill] + n);
  if (skills[skill] >= 50) {
    count("skillful");
  }
  if (skills[skill] >= 100) {
    count("masterful");
  }
}

function eat(row) {
  const food = definition(row);
  const amount = Math.round(food.bonus + adjustedSkill(story.player, "survival") / 5);
  const survivor = story.mode === "survivor";
  if (survivor) {
    adjustVital("hunger", "decNeed", amount);
  } else {
    healPerm(amount, { health: true });
  }
  sound.play(DRINKS.has(row.ref) ? "sound_use_drink" : "sound_use_food");
  count("eatFood");
  removeRow(row);
  return survivor ? { icon: "food", text: `-${amount} HUNGER` } : { icon: "health", text: `+${amount} HEALTH` };
}

function read(row) {
  const book = definition(row);
  const smarts = Math.ceil(adjustedSkill(story.player, "smarts") / constant("bookSmartsMod"));
  const gained = book.bonus + smarts;
  addSkillPoints(row.ref, gained);
  removeRow(row);
  sound.play("sound_use_book");
  count("readBook");
  return { icon: "book", text: `+${gained} TO ${data.actors.skills[row.ref].title} SKILL` };
}

// A healing item heals a share of the most health, and only when permanent health has been lost; No ZZZ takes sleep
// need off when there is some. Each does only its own part. Returns null when there is nothing to do
function medicate(row) {
  const item = definition(row);
  const who = story.player;
  if (item.bonusStat === "health") {
    if (who.permHealth >= who.healthMax) {
      return null;
    }
    const percent = Math.round(item.bonus + adjustedSkill(who, "firstAid") / 2);
    const healed = Math.round((percent / 100) * who.healthMax);
    healPerm(healed, { health: true });
    sound.play(`sound_use_${row.ref}`);
    removeRow(row);
    count("useHeal");
    if (row.ref === "pills") {
      count("usePills");
    }
    return { icon: "health", text: `+${healed} HEALTH` };
  }
  if (who.sleep <= 0) {
    return null;
  }
  adjustVital("sleep", "decNeed", item.bonus);
  sound.play(`sound_use_${row.ref}`);
  removeRow(row);
  const text = story.mode === "runAndGun" ? "NO EFFECT" : `-${item.bonus * SLEEP_SHOWN_FACTOR} TIREDNESS`;
  return { icon: "sleep", text };
}

// One press on a row. Food, healing, books and clothing do their thing; a weapon needs a slot (equip) and does nothing
// here. Returns the popup to show, { icon, text }, or null when there is none (clothing, weapons, items that do
// nothing, a healing item that isn't needed)
export function useRow(row) {
  if (!story.inventory.includes(row)) {
    return null;
  }
  switch (row.type) {
    case "clothing":
      toggleClothing(row);
      return null;
    case "food":
      return eat(row);
    case "books":
      return read(row);
    case "meds":
      return medicate(row);
    default:
      return null;
  }
}

// ---------- Setup and checks ----------

// The player's armour as the damage rules read it, from what is worn when the hit lands
export function initInventory() {
  Object.defineProperties(player, {
    armorHead: { get: () => armour("head"), configurable: true },
    armorChest: { get: () => armour("chest"), configurable: true },
  });
}

export const inventory = {
  addItem,
  removeRow,
  useRow,
  equip,
  unequip,
  deleteRow,
  weight,
  carry,
  armour,
  sortInventory,
  rowsFor,
  label,
  onInventoryCount,
};

function rowById(id) {
  return rowsFor("all").find((row) => row.id === id);
}

// Helpers for page.py checks
export const inventoryDebug = {
  // n of an item, or of ammo by its type ("9mm") or ammo item ("ammo9mm_100"), or cash ("cash"), in the backpack as a
  // pickup would put it there. Returns the weight
  give(ref, n = 1) {
    const ammo = data.items.ammoTypes.includes(ref) ? `ammo${ref}` : ref;
    addItem(ammo, { count: n });
    return weight();
  },

  // The rows a filter lists: id, ref, words, type, whether worn or wielded, weight and the count (cash, ammo)
  rows(filter = "all") {
    return rowsFor(filter).map((row) => ({
      id: row.id,
      ref: row.ref,
      label: label(row),
      type: row.type,
      eqd: row.eqd,
      weight: weightOf(row),
      count: row.count,
    }));
  },

  // Weight, the limit and whether the player is over it
  load() {
    return { weight: weight(), carry: carry(), over: weight() > carry(), penalty: player.weightPenalty };
  },

  // One press on the row with an id (from rows())
  use(id) {
    const row = rowById(id);
    return row ? useRow(row) : null;
  },

  equip(slot, id) {
    const row = rowById(id);
    return row ? equip(slot, row) : false;
  },

  unequip,

  // The trash can on the row with an id (cash and ammo rows too, which are refused)
  trash(id, confirmed = false) {
    const row = rowById(id);
    return row ? deleteRow(row, confirmed) : "refused";
  },

  armour() {
    const worn = { head: armour("head"), chest: armour("chest") };
    return { ...worn, playerHead: player.armorHead, playerChest: player.armorChest };
  },
};
