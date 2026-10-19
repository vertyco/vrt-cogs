// Everything a save holds, as plain data, live while the story is played. `story` is one object that is emptied and
// refilled when a story starts or a save loads, so a system may keep a reference to it. The keys follow the original's
// own save keys (F4:1286-1341) in a tidier shape; save.js maps between the two.
import { data } from "./data.js";
import { START_TIME } from "./world.js";

// The tables an item may live in. Each holds its items under their refs, with the row's `type` and sort key `st`
const ITEM_TABLES = ["weapons", "clothing", "food", "medical", "books", "junk", "quest"];
// A skill that exists in the original's data and is never shown or used (F4:11531-11544); the others are in actors.json
const SILENT_SKILLS = ["traps"];
// A new character's walking speed (F4:11514)
const START_SPEED = 7.5;
// The clothes a new character wears, by where they are worn (F4:7154)
const START_CLOTHES = { bottom: "jeansBlack", top: "shirtWhite", feet: "shoeBlack" };
const START_CASH = 10;
// Weapons that come with a round of their own ammo
const AMMO_WITH_WEAPON = new Set(["handGrenade", "RPG"]);
// Where the original keeps what a clothing item changes on the player, by where it is worn
const WEAR_FIELDS = {
  top: "top",
  bottom: "bottom",
  feet: "shoes",
  armor: "torso",
  head: "head",
  face: "face",
  eyes: "eyes",
};
// The settings a new slot starts with (F4:26030-26051). Toggle Crouch is off here and starts on for a touch screen
// (newStory, O2)
const START_SETTINGS = {
  soundOn: true,
  musicOn: true,
  lowViolence: false,
  lowEffects: false,
  lowFlashlight: false,
  showDamageText: true,
  showXPText: true,
  bodyFade: "low",
  decalFade: "low",
  filmGrain: false,
  screenShake: true,
  brightness: 3,
  achUpdates: true,
  azerty: false,
  toggleCrouch: false,
};
const SKIN_START = "0xD3965F";
const HAIR_COLOUR_START = "0xa39a74";

export const story = {};

const CROUCH_STORE = "laststand.toggleCrouch";

// Toggle Crouch belongs to the device, not the slot: a slot follows the player to every device, and the thumb that
// needs a toggle on a touch screen is not the one holding Ctrl on a desktop (O2). Unset, it follows the touch screen
export function deviceToggleCrouch(touch) {
  try {
    const stored = localStorage.getItem(CROUCH_STORE);
    if (stored === "true" || stored === "false") {
      return stored === "true";
    }
  } catch (e) {
    console.warn("Union City: couldn't read the Toggle Crouch choice", e);
  }
  return touch === true;
}

export function rememberToggleCrouch(on) {
  try {
    localStorage.setItem(CROUCH_STORE, String(on));
  } catch (e) {
    console.warn("Union City: couldn't keep the Toggle Crouch choice", e);
  }
}

// The table and item a ref names, or null
export function findItem(ref) {
  for (const table of ITEM_TABLES) {
    const item = data.items[table]?.[ref];
    if (item) {
      return { table, item };
    }
  }
  return null;
}

// A quest's state in the save, made the first time it is asked for: started (it was ever accepted), active (accepted
// and not completed), completed, tracking (the one shown on the HUD) and count (kills, for a kill quest)
export function questState(id) {
  story.quests[id] ??= { started: false, active: false, completed: false, tracking: false, count: 0 };
  return story.quests[id];
}

// The words the quest and NPC texts name by key, for a male and a female player (the table at F4:36361). Each also has
// a capitalised "Start" form for the start of a sentence
const WORDS = {
  Partner: ["wife", "husband"],
  PartnerName: ["Bethany", "Matthew"],
  PartnerNameShort: ["Beth", "Matt"],
  PartnerSex: ["she", "he"],
  PartnerSexAddress: ["her", "him"],
  PlayerSexAddress: ["him", "her"],
  Formal: ["sir", "ma'am"],
  Older: ["son", "miss"],
  Friendly: ["buddy", "missy"],
  Young: ["young man", "young lady"],
  Title: ["Mr.", "Mrs."],
  Angry: ["asshole", "bitch"],
  Casual: ["guy", "girl"],
  Sex: ["man", "woman"],
};

// A text with its {Key} words filled in for the player: the pronoun keys above and {first}, {last} and {full} for the
// player's name. A text that differs by sex is { m, f }
export function fillText(text) {
  const female = story.player.sex === "female";
  const source = typeof text === "object" && text !== null ? text[female ? "f" : "m"] : text;
  const [first, ...rest] = story.player.name.split(" ");
  return String(source ?? "").replace(/\{(\w+)\}/g, (match, key) => {
    const base = key.endsWith("Start") ? key.slice(0, -5) : key;
    const word = WORDS[base]?.[female ? 1 : 0];
    if (word !== undefined) {
      return base === key ? word : word[0].toUpperCase() + word.slice(1);
    }
    const name = { first, last: rest.join(" "), full: story.player.name }[key];
    return name ?? match;
  });
}

// The original's sortInventory: sort key, then ref, then id
export function byRow(a, b) {
  return compare(a.st, b.st) || compare(a.ref, b.ref) || a.id - b.id;
}

function compare(a, b) {
  if (a < b) {
    return -1;
  }
  return a > b ? 1 : 0;
}

// A new row for an item, with the next item id. A weapon row also holds the rounds loaded in it
export function itemRow(ref) {
  const found = findItem(ref);
  if (!found) {
    throw new Error(`Union City: no item called ${ref}`);
  }
  story.itemId += 1;
  const row = { ref, type: found.item.type, id: story.itemId, slot: "none", st: found.item.st, eqd: false };
  if (found.item.type === "weapon") {
    row.ammo = 0;
  }
  return row;
}

// Adds a row to the backpack, or to the stash, and keeps the backpack in the original's order. A hand grenade or an RPG
// (or a built copy of one) also adds one round to its ammo, which stays when the weapon is deleted (F4:8250-8257)
export function addRow(ref, toStorage = false) {
  const row = itemRow(ref);
  const weapon = data.items.weapons?.[ref];
  if (AMMO_WITH_WEAPON.has(weapon?.weaponBase) && weapon.ammoType in story.ammo) {
    story.ammo[weapon.ammoType] += 1;
  }
  if (toStorage) {
    story.storage.push(row);
  } else {
    story.inventory.push(row);
    story.inventory.sort(byRow);
  }
  return row;
}

// Puts on the clothing item a row holds, taking off what was worn there
export function wear(row) {
  const place = findItem(row.ref).item.wearLocation;
  for (const other of story.inventory) {
    if (other.eqd && other.type === "clothing" && findItem(other.ref).item.wearLocation === place) {
      other.eqd = false;
    }
  }
  row.eqd = true;
  story.player.clothes[WEAR_FIELDS[place]] = row.ref;
}

// Takes off the clothing item a row holds, leaving nothing worn there
export function takeOff(row) {
  const place = findItem(row.ref).item.wearLocation;
  row.eqd = false;
  story.player.clothes[WEAR_FIELDS[place]] = "none";
}

function startPlayer(options) {
  const constants = data.actors.constants;
  const skills = {};
  const skillNames = [...Object.keys(data.actors.skills), ...Object.keys(data.actors.hiddenSkills), ...SILENT_SKILLS];
  for (const name of skillNames) {
    skills[name] = options.skills?.[name] ?? constants.skillBase;
  }
  const attributes = {};
  for (const name of Object.keys(data.actors.attributes)) {
    attributes[name] = options.attributes?.[name] ?? constants.attributeBase;
  }
  const level = 1;
  // Max health, F4:11712; the new character starts at it, with both bars full
  const healthMax = Math.round(constants.healthBase + attributes.endurance ** 2 + level * 10);
  return {
    name: options.name ?? "John Smith",
    sex: options.sex ?? "male",
    look: {
      skin: options.look?.skin ?? SKIN_START,
      hair: options.look?.hair ?? "cropped",
      hairColour: options.look?.hairColour ?? HAIR_COLOUR_START,
      facialHair: options.look?.facialHair ?? "none",
    },
    clothes: { top: "none", torso: "none", head: "none", face: "none", eyes: "none", bottom: "none", shoes: "none" },
    attributes,
    skills,
    speed: START_SPEED,
    level,
    xp: 0,
    levelXP: Math.round((constants.levelXPMult * level * (level * 5)) / 100) * 100,
    lastLevelXP: 0,
    points: { attribute: 0, skill: 0 },
    health: healthMax,
    permHealth: healthMax,
    healthMax,
    // Worked out by the vitals when the story starts
    stamina: 0,
    staminaMax: 0,
    hunger: 0,
    sleep: 0,
    cash: START_CASH,
    carryWeight: attributes.strength * constants.carryWeightMultiplier,
    // What is in each weapon slot, and which one is in the hands
    slots: { primary: "hands", secondary: "hands" },
    holding: "primary",
    // The companion's NPC key and the partner's, while they are along
    follower: null,
    partner: null,
  };
}

// A new character as the original makes one (newCharacter, F4:11499): "John Smith" unless options say otherwise, the
// black jeans, white shirt and black shoes worn, $10, empty hands, and the Survival Kit in the stash. options may hold
// name, sex, look, attributes, skills, mode, hardcore, headshots, slot and touch (a touch screen turns Toggle Crouch on)
export function newStory(options = {}) {
  if (!data.items || !data.actors || !data.world) {
    throw new Error("Union City: the game's data hasn't loaded yet");
  }
  for (const key of Object.keys(story)) {
    delete story[key];
  }
  Object.assign(story, {
    itemId: 0,
    // The game minute the last zombie backpack was handed out (F4:26136); the next waits for the interval
    lastDropTime: START_TIME,
    slot: options.slot ?? 0,
    mode: options.mode ?? "survivor",
    hardcore: options.hardcore ?? false,
    headshots: options.headshots ?? false,
    player: startPlayer(options),
    inventory: [],
    storage: [],
    // Rounds held, by ammo type
    ammo: Object.fromEntries(data.items.ammoTypes.map((type) => [type, 0])),
    quests: {},
    npcs: {},
    triggers: {},
    notes: {},
    // Counts by achievement key, the keys done, and the three prizes given
    achievements: { counts: {}, done: {}, prizes: [false, false, false] },
    // The map sections open to travel (the start's, and the Survival Kit's) and the sections whose far end is open too
    map: { unlocked: [...data.world.unlocks.initial, ...data.world.unlocks.premium], ends: [] },
    help: {},
    containers: {},
    doors: {},
    rooms: {},
    settings: { ...START_SETTINGS, toggleCrouch: deviceToggleCrouch(options.touch) },
    // The companion's weapons, once one has joined: { primary, secondary, current, stored }
    companionWeapons: null,
  });
  for (const ref of Object.values(START_CLOTHES)) {
    wear(addRow(ref));
  }
  for (const ref of data.items.premiumKit) {
    addRow(ref, true);
  }
  return story;
}
