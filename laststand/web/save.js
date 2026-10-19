// Saving and loading (spec 2.16, 5). A save is one JSON object, { v, summary, data }, gzip-compressed in the page and
// kept by the bot in one of three slots per Discord user (hub.api "slots", "load", "save" and "wipe").
//
// `data` holds the original's own save keys, named as the original names them in currentSave.data, so each one can be
// checked against its function below. The values are the page's live `story` in those names: inventory and storage
// rows keep the page's row shape, and a container's contents are the { ref, lucky } list search.js keeps. `summary` is
// what the slot panels show, and the only part the bot reads.
//
// The keys, by the original function that writes them:
//   saveGame (F4:1286): primaryWeapon, secondaryWeapon, primaryAmmo, secondaryAmmo, health, permHealth, stamina,
//     currentWeapon, storedWeapon, currentTimeMin, currentTimeHrs, currentTimeMin24, currentTimeHrs24,
//     currentLighting, currentDayNumber, dayNameCount, meridiem, gameTime, lastRushTime, hoursPassed, lastDropTime,
//     savedLoc, savedSt, savedBld, savedFloor, savedRoom, headShotsOnly, gameMode, hardcore, playerStartX
//   savePlayer (F4:13211): player { premium, charName, health, permHealth, maxHealth, level, attPoints, skillPoints,
//     speed, strength, endurance, intellect, precision, luck, strengthBase, enduranceBase, intellectBase,
//     precisionBase, luckBase, stamina, staminaMax, sleep, hunger, carryWeight, follower, partner, blunt, blades,
//     pistols, longGuns, automatics, specialWeapons, traps, sneak, smarts, security, searching, speech, firstAid,
//     fitness, survival, sex, skinColour, clothesTop, torsoAccessory, headAccessory, faceAccessory, eyesAccessory,
//     clothesBottom, clothesShoe, hair, facialHair, hairColour, XP }
//   saveInventory (F4:7176): inventory, lastItemID, totalMoney
//   saveStorage (F4:16783): storage
//   saveAmmo (F4:20792): ammo<type> for the 11 ammo types (ammo556 ... ammo50cal)
//   saveNPCStates (F4:23249): <npc>state for the 49 people (Partnerstate, Kowalskistate ...)
//   saveNotes (F4:4536): no<n>rd for the notes in the tables
//   saveQuestStates (F4:2854): <quest>started, <quest>active, <quest>completed, <quest>tracking, <quest>count for
//     the 33 quests (900started ...)
//   saveTriggers (F4:17261): trig<n>Off for the triggers that have a state
//   saveCompanion (F4:5244): compPrimaryWeapon, compSecondaryWeapon, compCurrentWeapon, compStoredWeapon
//   saveAchievements (F4:340): <ach>Cnt, <ach>Comp for the 54 achievements; unlockAchievement (F4:382): <ach> once
//     done; saveAchPrizes (F4:525): achPrizeGiven1, achPrizeGiven2, achPrizeGiven3
//   saveGameSettings (F4:794): settingSoundOn, settingMusicOn, lowViolence, lowEffects, lowFlashlight,
//     settingShowDamageText, settingShowXPText, settingBodyFade, settingDecalFade, settingFilmGrain,
//     settingScreenShake, settingBrightness, settingAchUpdates, settingKeyboardAzerty, settingToggleCrouch
//   saveMapLocations (F4:4338): section<n>Locked for the 16 sections; unlockEndLoc (F4:4329): endLoc<n>
//   saveHelp (F4:20403): help_<hint> for every hint (the page's sleep and storage hints too)
//   saveClearRoom (F4:1280): <room>_clr; changeRooms (F4:14488): <room>_lastTime
//   searchContainer (F4:13855): <room>_<container> (what is left inside), <room>_<container>_ul,
//     <room>_<container>_br; breakLock (F4:16545) sets _br
//   checkIfDoorLocked, unlockDoor, lockDoor (F4:14853-14892): <room>_<door> (true while locked)
//   the slot panel's name (F4:3632): name
// Kept by the page beside them, for state the original rebuilt from code at load: currentSlot (the weapon slot in the
// hands, since both slots may hold the same weapon) and <npc>place (where a moved person stands). storyId names the
// story, the same in all its saves, so a Hardcore death's wipe knows the slot still holds that story.
// Not saved: qualitySetting (the quality setting is gone), settingKeyboardLefty and zombiesOff (no setting shows
// them), socialShown, facebookRewardGiven and twitterRewardGiven (the social links are gone), <skill>_used
// (saveSkillTrack is never called), questKillCount (only ever read), the zombies in rooms, humans and the zombie
// memory ring. The armour is worked out from what is worn, never saved.
//
// Saves go out at the original's save points (savePoint). One save is in flight at a time; a save point reached
// meanwhile sends the newest state once it is done. The HUD's save icon shows while one is sent and says SAVE FAILED
// when it did not go through; the next save point tries again. The state is turned into text the moment the save
// point is reached, so a room change or a quit right after it never changes what is sent. On pagehide the newest
// packed copy goes out with keepalive when it fits the browser's limit; that copy is packed again each game minute,
// so it is never far behind. A story that is dead is never saved.
//
// Each slot has a revision on the bot that every save and wipe moves on. A story's saves send the revision its load or
// creation started from, moved on only by its own acknowledged saves, and the bot refuses a save or wipe from a page
// that fell behind (another device saved or wiped the slot since). A refused save whose slot holds this story token's
// own last save (one that went through but whose answer was lost) goes again on the slot's revision; one refused
// because another writer saved sends the player back to the menu, which says so, and Continue there loads the newer
// save. A request with no answer in 15 seconds counts as failed. A Hardcore death keeps its slot as dead on this
// device until the bot has emptied it or holds another story there, and a dead slot never loads.
import { backToMenu } from "activityhub";
import { data } from "./data.js";
import { hud } from "./hud.js";
import { input } from "./input.js";
import { light } from "./light.js";
import { applySettings, quitToMenu } from "./pause.js";
import { player } from "./player.js";
import { rng } from "./rng.js";
import { room } from "./rooms.js";
import { deviceToggleCrouch, newStory, story } from "./story.js";
import { START_ROOM, START_X, world } from "./world.js";

const SLOTS = [1, 2, 3];
const SAVE_VERSION = 1;
const CREATE_REASON = "create";
// The browser refuses a keepalive request over 64 KB, counting the whole body around the save's text
const KEEPALIVE_MOST = 65536 - 64;
// Characters turned into one string at a time when writing base64, under the engine's argument limit
const CHUNK = 0x8000;
// The most save points and wipes kept for a check to read
const MOST_RECORDED = 50;
const MODE_KEYS = { runAndGun: "runGun", survivor: "survivor" };
const SETTING_KEYS = {
  soundOn: "settingSoundOn",
  musicOn: "settingMusicOn",
  lowViolence: "lowViolence",
  lowEffects: "lowEffects",
  lowFlashlight: "lowFlashlight",
  showDamageText: "settingShowDamageText",
  showXPText: "settingShowXPText",
  bodyFade: "settingBodyFade",
  decalFade: "settingDecalFade",
  filmGrain: "settingFilmGrain",
  screenShake: "settingScreenShake",
  brightness: "settingBrightness",
  achUpdates: "settingAchUpdates",
  azerty: "settingKeyboardAzerty",
  toggleCrouch: "settingToggleCrouch",
};
// The player's fields the original keeps under the same name
const PLAIN_PLAYER = [
  "sex",
  "speed",
  "level",
  "health",
  "permHealth",
  "stamina",
  "staminaMax",
  "sleep",
  "hunger",
  "carryWeight",
  "follower",
  "partner",
];
const LOOK_KEYS = { skin: "skinColour", hair: "hair", hairColour: "hairColour", facialHair: "facialHair" };
const CLOTHES_KEYS = {
  top: "clothesTop",
  torso: "torsoAccessory",
  head: "headAccessory",
  face: "faceAccessory",
  eyes: "eyesAccessory",
  bottom: "clothesBottom",
  shoes: "clothesShoe",
};
const QUEST_FIELDS = { started: "started", active: "active", completed: "completed", tracking: "tracking" };
const COMPANION_KEYS = {
  primary: "compPrimaryWeapon",
  secondary: "compSecondaryWeapon",
  current: "compCurrentWeapon",
  stored: "compStoredWeapon",
};
// A room's own keys and its containers' and doors' keys all start with the room's id
const ROOM_KEY = /^(l\d+_s\d+_b\d+_f\d+_r\d+)_(.+)$/;
const TRIGGER_KEY = /^trig(\d+)Off$/;
const END_KEY = /^endLoc(\d+)$/;
const DAYS_IN_WEEK = 7;
// What a save or a wipe came to: it went through, it didn't reach the bot, or the slot had moved on
export const DONE = "done";
export const FAILED = "failed";
export const STALE = "stale";
// A request to the bot with no answer after this long counts as failed (its answer still counts if it comes later)
const ANSWER_MS = 15000;
// The menu's box after a save the bot refused because the slot had moved on
export const OVERTAKEN = { heading: "SAVED ELSEWHERE", body: "\rTHIS STORY WAS SAVED ON\rANOTHER DEVICE." };
// Where this device keeps a dead slot, one key per Discord user and slot
const DEAD_STORE = "laststand.dead";

let page = null;
// The story being played: { slot, rev, id, writer }. rev is the slot's revision its load or creation started from,
// moved on only by its own saves the bot acknowledged; id is the story's own, the same in all its saves; writer is
// this token's own, new at each load or creation, so a refused save can tell its own last save from another device's
let current = null;
// Each slot's revision as the newest request's answer gave it, for starting a story: { slot: revision }, and the order
// of the request that set it
const listed = {};
const listedAt = {};
let asked = 0;
// The states waiting to go out, oldest first, the newest of each story only: [{ story, text }]
let waiting = [];
// Settles when the save in flight and any waiting after it are done, with whether the last one went through
let pumping = Promise.resolve(true);
let sending = false;
// The newest packed copy of the story being played, for pagehide: { story, packed, order }
let prepared = null;
let packOrder = 0;
// The story was saved by the back button and the page is going: pagehide sends nothing more
let leaving = false;
// The back button's save failed: the next press leaves without one, until a later save goes through
let backFailed = false;
// The back button's save is on its way
let backSaving = false;
// The dead slots this page marked, for when the browser's storage can't be used: { slot: { rev, id } }
const deadHere = {};
// Settles when the dead slots' wipes in progress are done
let burying = Promise.resolve();

// { reason, frame, sent } for the latest save points, oldest first
export const saves = [];
// { slot, frame } for each slot wiped, oldest first
export const wipes = [];
// What the sends did, for checks: { slot, ok, size, error }
const sends = [];

function keep(list, entry) {
  list.push(entry);
  if (list.length > MOST_RECORDED) {
    list.shift();
  }
}

// ---------- Building a save ----------

function number(part) {
  return Number(part.slice(1));
}

function saveGameKeys(out) {
  const who = story.player;
  const held = who.holding;
  const other = held === "primary" ? "secondary" : "primary";
  const loaded = (slot) => story.inventory.find((row) => row.slot === slot)?.ammo ?? 0;
  Object.assign(out, {
    name: `Save Game ${story.slot}`,
    primaryWeapon: who.slots.primary,
    secondaryWeapon: who.slots.secondary,
    primaryAmmo: loaded("primary"),
    secondaryAmmo: loaded("secondary"),
    health: who.health,
    permHealth: who.permHealth,
    stamina: who.stamina,
    currentWeapon: who.slots[held],
    storedWeapon: who.slots[other],
    currentSlot: held,
    headShotsOnly: story.headshots,
    gameMode: MODE_KEYS[story.mode],
    hardcore: story.hardcore,
  });
}

// The clock's keys. Only gameTime is read back; the rest follow from it, as the page works them out
function saveTime(out) {
  const hours = world.hour;
  Object.assign(out, {
    currentTimeMin: world.minute,
    currentTimeHrs: hours % 12 || 12,
    currentTimeMin24: world.minute,
    currentTimeHrs24: hours,
    currentLighting: light.level(),
    currentDayNumber: world.day,
    dayNameCount: (((world.day - 1) % DAYS_IN_WEEK) + DAYS_IN_WEEK) % DAYS_IN_WEEK,
    meridiem: hours < 12 ? "AM" : "PM",
    gameTime: world.time,
    lastRushTime: story.lastRushTime,
    hoursPassed: hours % 12,
    lastDropTime: story.lastDropTime,
  });
}

// Where the story stands: the room it is in, or the start for a story that has only been made (character creation
// saves before the world and its first room exist, and the room left by an earlier story is not this one's)
function placeOf(fresh) {
  if (fresh) {
    return { def: data.world.rooms[START_ROOM], x: START_X };
  }
  return { def: room.def, x: world.player?.x ?? room.arrivalX };
}

function saveLocation(out, fresh) {
  const { def, x } = placeOf(fresh);
  Object.assign(out, {
    savedLoc: number(def.loc),
    savedSt: number(def.street),
    savedBld: number(def.building),
    savedFloor: number(def.floor),
    savedRoom: number(def.room),
    playerStartX: x,
  });
}

function savePlayer(out) {
  const who = story.player;
  const saved = {
    premium: true,
    charName: who.name,
    maxHealth: who.healthMax,
    XP: who.xp,
    attPoints: who.points.attribute,
    skillPoints: who.points.skill,
  };
  for (const key of PLAIN_PLAYER) {
    saved[key] = who[key];
  }
  for (const [mine, theirs] of Object.entries(LOOK_KEYS)) {
    saved[theirs] = who.look[mine];
  }
  for (const [mine, theirs] of Object.entries(CLOTHES_KEYS)) {
    saved[theirs] = who.clothes[mine];
  }
  for (const [name, value] of Object.entries(who.attributes)) {
    saved[name] = value;
    saved[`${name}Base`] = value;
  }
  Object.assign(saved, who.skills);
  out.player = saved;
}

function saveInventory(out) {
  out.inventory = story.inventory;
  out.lastItemID = story.itemId;
  out.totalMoney = story.player.cash;
  out.storage = story.storage;
  for (const [type, count] of Object.entries(story.ammo)) {
    out[`ammo${type}`] = count;
  }
  if (story.companionWeapons) {
    for (const [mine, theirs] of Object.entries(COMPANION_KEYS)) {
      out[theirs] = story.companionWeapons[mine];
    }
  }
}

function saveStoryStates(out) {
  for (const id of Object.keys(data.story.quests)) {
    const state = story.quests[id] ?? {};
    for (const [mine, theirs] of Object.entries(QUEST_FIELDS)) {
      out[`${id}${theirs}`] = state[mine] === true;
    }
    out[`${id}count`] = state.count ?? 0;
  }
  for (const [key, def] of Object.entries(data.story.npcs)) {
    const mine = story.npcs[key];
    out[`${key}state`] = mine?.state ?? def.state;
    if (mine?.place) {
      out[`${key}place`] = mine.place;
    }
  }
  for (const [n, state] of Object.entries(story.triggers)) {
    out[`trig${n}Off`] = state.triggered;
  }
  for (const n of Object.keys(data.story.notes)) {
    out[`no${n}rd`] = story.notes[n]?.read === true;
  }
  for (const name of Object.keys(data.story.help.hints)) {
    out[`help_${name}`] = story.help[name] === true;
  }
}

function saveAchievements(out) {
  const mine = story.achievements;
  for (const key of Object.keys(data.story.achievements)) {
    out[`${key}Cnt`] = mine.counts[key] ?? 0;
    out[`${key}Comp`] = mine.done[key] === true;
    if (mine.done[key] === true) {
      out[key] = true;
    }
  }
  mine.prizes.forEach((given, index) => {
    out[`achPrizeGiven${index + 1}`] = given;
  });
}

function saveWorldStates(out) {
  for (const n of Object.keys(data.world.sections)) {
    out[`section${n}Locked`] = !story.map.unlocked.includes(Number(n));
  }
  for (const n of story.map.ends ?? []) {
    out[`endLoc${n}`] = true;
  }
  for (const [key, value] of Object.entries(story.settings)) {
    out[SETTING_KEYS[key] ?? key] = value;
  }
  for (const [id, each] of Object.entries(story.rooms)) {
    if (each.clr !== undefined) {
      out[`${id}_clr`] = each.clr;
    }
    if (each.lastTime !== undefined) {
      out[`${id}_lastTime`] = each.lastTime;
    }
  }
  for (const [key, each] of Object.entries(story.containers)) {
    if (each.items) {
      out[key] = each.items;
    }
    out[`${key}_ul`] = each.unlocked;
    out[`${key}_br`] = each.broken;
  }
  Object.assign(out, story.doors);
}

// What the slot panels show: the bot reads this alone
function buildSummary(fresh) {
  const who = story.player;
  const { def } = placeOf(fresh);
  return {
    name: who.name,
    level: who.level,
    area: def?.areaName ?? "",
    street: def?.streetName ?? "",
    day: world.day,
    mode: story.mode,
    hardcore: story.hardcore,
    headshots: story.headshots,
    look: {
      sex: who.sex,
      skin: who.look.skin,
      hair: who.look.hair,
      hairColour: who.look.hairColour,
      facialHair: who.look.facialHair,
      hat: who.clothes.head,
      face: who.clothes.face,
      eyes: who.clothes.eyes,
    },
  };
}

// The save of the story as it stands. Its lists are the live ones: turn it into text before the story moves on. fresh
// is a story just made by character creation, which stands at the start of the game
export function buildSave(fresh = false) {
  const out = {};
  saveGameKeys(out);
  saveTime(out);
  saveLocation(out, fresh);
  savePlayer(out);
  saveInventory(out);
  saveStoryStates(out);
  saveAchievements(out);
  saveWorldStates(out);
  out.storyId = current?.id ?? null;
  out.writerId = current?.writer ?? null;
  return { v: SAVE_VERSION, summary: buildSummary(fresh), data: out };
}

// ---------- Applying a save ----------

function loadPlayer(saved) {
  const who = story.player;
  const from = saved.player;
  for (const key of PLAIN_PLAYER) {
    who[key] = from[key];
  }
  who.name = from.charName;
  who.healthMax = from.maxHealth;
  who.xp = from.XP;
  who.points = { attribute: from.attPoints, skill: from.skillPoints };
  for (const [mine, theirs] of Object.entries(LOOK_KEYS)) {
    who.look[mine] = from[theirs];
  }
  for (const [mine, theirs] of Object.entries(CLOTHES_KEYS)) {
    who.clothes[mine] = from[theirs];
  }
  for (const name of Object.keys(who.attributes)) {
    who.attributes[name] = from[`${name}Base`];
  }
  for (const name of Object.keys(who.skills)) {
    who.skills[name] = from[name];
  }
  // setupExperience (F4:13595): the next level's XP follows from the level
  const level = who.level;
  who.levelXP = Math.round((data.actors.constants.levelXPMult * level * (level * 5)) / 100) * 100;
  who.lastLevelXP = 0;
  // loadGame takes health and stamina from saveGame's own keys (F4:11716, 13392)
  Object.assign(who, { health: saved.health, permHealth: saved.permHealth, stamina: saved.stamina });
  who.slots = { primary: saved.primaryWeapon, secondary: saved.secondaryWeapon };
  who.holding = saved.currentSlot;
  who.cash = saved.totalMoney;
}

function loadInventory(saved) {
  story.inventory = saved.inventory;
  story.storage = saved.storage;
  story.itemId = saved.lastItemID;
  for (const type of Object.keys(story.ammo)) {
    story.ammo[type] = saved[`ammo${type}`];
  }
  story.companionWeapons = null;
  if (saved.compPrimaryWeapon !== undefined) {
    story.companionWeapons = Object.fromEntries(
      Object.entries(COMPANION_KEYS).map(([mine, theirs]) => [mine, saved[theirs]]),
    );
  }
  story.lastDropTime = saved.lastDropTime;
  if (saved.lastRushTime !== undefined) {
    story.lastRushTime = saved.lastRushTime;
  }
  story.mode = saved.gameMode === MODE_KEYS.runAndGun ? "runAndGun" : "survivor";
  story.hardcore = saved.hardcore;
  story.headshots = saved.headShotsOnly;
}

function loadQuestsAndPeople(saved) {
  for (const id of Object.keys(data.story.quests)) {
    const state = {};
    for (const [mine, theirs] of Object.entries(QUEST_FIELDS)) {
      state[mine] = saved[`${id}${theirs}`] === true;
    }
    state.count = saved[`${id}count`] ?? 0;
    if (Object.values(state).some(Boolean)) {
      story.quests[id] = state;
    }
  }
  for (const [key, def] of Object.entries(data.story.npcs)) {
    const state = saved[`${key}state`];
    const place = saved[`${key}place`];
    if (state !== undefined && state !== def.state) {
      story.npcs[key] = { state };
    }
    if (place) {
      story.npcs[key] = { ...story.npcs[key], place };
    }
  }
}

function loadFlags(saved) {
  story.triggers = {};
  story.map.ends = [];
  for (const [key, value] of Object.entries(saved)) {
    const trigger = TRIGGER_KEY.exec(key);
    const end = END_KEY.exec(key);
    if (trigger) {
      story.triggers[trigger[1]] = { triggered: value };
    } else if (end && value === true) {
      story.map.ends.push(Number(end[1]));
    }
  }
  story.map.unlocked = Object.keys(data.world.sections)
    .filter((n) => saved[`section${n}Locked`] === false)
    .map(Number);
  for (const n of Object.keys(data.story.notes)) {
    if (saved[`no${n}rd`] === true) {
      story.notes[n] = { read: true };
    }
  }
  for (const name of Object.keys(data.story.help.hints)) {
    if (saved[`help_${name}`] === true) {
      story.help[name] = true;
    }
  }
  for (const [mine, theirs] of Object.entries(SETTING_KEYS)) {
    story.settings[mine] = saved[theirs];
  }
  story.settings.toggleCrouch = deviceToggleCrouch(page.touch);
}

function loadAchievements(saved) {
  const mine = story.achievements;
  for (const key of Object.keys(data.story.achievements)) {
    if (saved[`${key}Cnt`]) {
      mine.counts[key] = saved[`${key}Cnt`];
    }
    if (saved[`${key}Comp`] === true) {
      mine.done[key] = true;
    }
  }
  mine.prizes = mine.prizes.map((given, index) => saved[`achPrizeGiven${index + 1}`] === true);
}

function containerRecord(key) {
  story.containers[key] ??= { items: null, unlocked: false, broken: false };
  return story.containers[key];
}

// Rooms, containers and doors, from the keys that start with a room's id
function loadRoomKeys(saved) {
  for (const [key, value] of Object.entries(saved)) {
    const found = ROOM_KEY.exec(key);
    if (!found) {
      continue;
    }
    const [, id, rest] = found;
    if (rest === "clr" || rest === "lastTime") {
      story.rooms[id] = { ...story.rooms[id], [rest]: value };
    } else if (rest.endsWith("_ul")) {
      containerRecord(key.slice(0, -3)).unlocked = value;
    } else if (rest.endsWith("_br")) {
      containerRecord(key.slice(0, -3)).broken = value;
    } else if (Array.isArray(value)) {
      containerRecord(key).items = value;
    } else {
      story.doors[key] = value;
    }
  }
}

function roomOf(saved) {
  const { savedLoc, savedSt, savedBld, savedFloor, savedRoom } = saved;
  return `l${savedLoc}_s${savedSt}_b${savedBld}_f${savedFloor}_r${savedRoom}`;
}

// A save becomes the story being played (loadGame F4:1386, postLoadCommands F4:1422): the story, settings, help flags,
// achievements and map, the clock, then the saved room at the saved place. rev is the slot's revision the save came
// with. Returns the room change's promise
export function applySave(save, slot = story.slot, rev = listed[slot] ?? 0) {
  const saved = structuredClone(save.data);
  rng.seed();
  input.clear();
  world.reset();
  current = { slot, rev, id: saved.storyId ?? newStoryId(), writer: newStoryId() };
  input.own(page.screen);
  light.reset();
  newStory({ touch: page.touch, slot });
  loadPlayer(saved);
  loadInventory(saved);
  loadQuestsAndPeople(saved);
  loadFlags(saved);
  loadAchievements(saved);
  loadRoomKeys(saved);
  world.time = saved.gameTime;
  applySettings();
  leaving = false;
  backFailed = false;
  world.start();
  return world.enter(roomOf(saved), saved.playerStartX);
}

// ---------- Packing ----------

async function streamBytes(bytes, transform) {
  const stream = new Blob([bytes]).stream().pipeThrough(transform);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function toBase64(bytes) {
  let text = "";
  for (let at = 0; at < bytes.length; at += CHUNK) {
    text += String.fromCharCode.apply(null, bytes.subarray(at, at + CHUNK));
  }
  return btoa(text);
}

function fromBase64(text) {
  const raw = atob(text);
  const bytes = new Uint8Array(raw.length);
  for (let k = 0; k < raw.length; k += 1) {
    bytes[k] = raw.charCodeAt(k);
  }
  return bytes;
}

// A save's text, gzipped and in base64. The newest packed copy is kept for pagehide while its story is still the one
// being played, so a pack finishing after a load or a new story can't bring an older story's copy back
async function pack(owner, text) {
  packOrder += 1;
  const order = packOrder;
  const packed = toBase64(await streamBytes(new TextEncoder().encode(text), new CompressionStream("gzip")));
  if (owner === current && (!prepared || order > prepared.order)) {
    prepared = { story: owner, packed, order, raw: text.length };
  }
  return packed;
}

async function unpack(packed) {
  const bytes = await streamBytes(fromBase64(packed), new DecompressionStream("gzip"));
  return JSON.parse(new TextDecoder().decode(bytes));
}

// ---------- Sending ----------

// A story is open in the world, in a slot the bot keeps, and its room is in (world.room is empty from a reset until
// the loaded room is built, while room.def still names the last story's room)
function storyOpen() {
  return world.active && Boolean(story.player) && SLOTS.includes(story.slot) && Boolean(world.room);
}

function canSave() {
  return storyOpen() && player.alive !== false;
}

function newStoryId() {
  return Array.from(crypto.getRandomValues(new Uint32Array(4)), (n) => n.toString(16).padStart(8, "0")).join("");
}

// The story being played, made at its first save when it was not loaded (a new story starts from the slot's listing)
function playing() {
  current ??= { slot: story.slot, rev: listed[story.slot] ?? 0, id: newStoryId(), writer: newStoryId() };
  return current;
}

// A slot's revision as an answer gave it. An answer only counts when its request went out after the one that last
// set the slot, so a listing answered late can't undo a wipe's answer
function heard(slot, rev, order) {
  if (Number.isInteger(rev) && order >= (listedAt[slot] ?? 0)) {
    listed[slot] = rev;
    listedAt[slot] = order;
  }
}

// The revisions an answer tells, whenever it comes
function noteRevs(name, data, reply, order) {
  if (name === "slots") {
    SLOTS.forEach((slot, index) => heard(slot, reply.revs?.[index], order));
  } else {
    heard(data.slot, reply?.rev, order);
  }
}

// A request to the bot that counts as failed when no answer comes within ANSWER_MS. The request itself goes on:
// whenever its answer comes, the revisions it tells are kept and onReply is told it
function ask(name, data, onReply = null) {
  asked += 1;
  const order = asked;
  const call = page.hub.api(name, data).then((reply) => {
    noteRevs(name, data, reply, order);
    onReply?.(reply);
    return reply;
  });
  let timer = null;
  const late = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`No answer from the bot to ${name} in time`)), ANSWER_MS);
  });
  return Promise.race([call, late]).finally(() => clearTimeout(timer));
}

// What a slot's save on the bot is: { id, writer, rev }, the story and the story token that wrote it (null for an
// empty slot) and the slot's revision
async function saveIn(slot) {
  const reply = await ask("load", { slot });
  const saved = reply.save ? await unpack(reply.save) : null;
  return { id: saved ? (saved.data?.storyId ?? "") : null, writer: saved?.data?.writerId ?? null, rev: reply.rev };
}

// After a refusal: whether the slot holds this story token's own save, as when a save went through but its answer was
// lost. If so the story takes the slot's revision
async function ownSlot(owner) {
  const found = await saveIn(owner.slot);
  if (found.writer !== owner.writer) {
    return false;
  }
  owner.rev = found.rev;
  return true;
}

// One save, with its story's revision: DONE, FAILED or STALE. A refusal where the slot holds this story's own last
// save sends the job once more on the slot's revision, so only another writer's save counts as STALE
async function sendOne(job, again = true) {
  const owner = job.story;
  let size = 0;
  try {
    const packed = await pack(owner, job.text);
    size = packed.length;
    const reply = await ask("save", { slot: owner.slot, save: packed, rev: owner.rev }, (answer) => {
      if (!answer.stale) {
        owner.rev = Math.max(owner.rev, answer.rev);
      }
    });
    keep(sends, { slot: owner.slot, ok: !reply.stale, size, stale: Boolean(reply.stale) });
    if (!reply.stale) {
      return DONE;
    }
    if (again && (await ownSlot(owner))) {
      return sendOne(job, false);
    }
    return STALE;
  } catch (e) {
    console.warn("Union City: couldn't save the game", e);
    keep(sends, { slot: owner.slot, ok: false, size, error: String(e?.message ?? e) });
    return FAILED;
  }
}

// The bot refused a story's save because another device saved or wiped its slot since. Nothing more of it is sent,
// and the story, when it is still the one being played, goes back to the menu, which says why
function overtaken(owner) {
  waiting = waiting.filter((each) => each.story !== owner);
  if (prepared?.story === owner) {
    prepared = null;
  }
  if (world.active && owner === current) {
    quitToMenu(OVERTAKEN);
  }
}

// Sends what is waiting, and whatever arrives while it goes, oldest story first
async function pump() {
  sending = true;
  hud.saveIcon("saving");
  let result = DONE;
  let refused = null;
  while (waiting.length) {
    const job = waiting.shift();
    result = await sendOne(job);
    if (result === STALE) {
      refused = job.story;
      waiting = waiting.filter((each) => each.story !== refused);
    }
  }
  sending = false;
  hud.saveIcon(result === FAILED ? "failed" : null);
  if (refused) {
    overtaken(refused);
  } else if (result === DONE) {
    backFailed = false;
  }
  return result !== FAILED;
}

// A save point of the original (spec 2.16): the story as it stands now goes to its slot. Returns a promise that
// settles once it and any save after it are done, false when the last one didn't reach the bot (no answer within
// ANSWER_MS counts). A save the bot refused because the slot moved on has already sent the story back to the menu
// when it settles. Each story keeps only its newest waiting state, and a story left behind still has its own sent
export function savePoint(reason) {
  // Character creation's is the one save point reached before a world is open
  const fresh = reason === CREATE_REASON;
  const sent = fresh ? SLOTS.includes(story.slot) && Boolean(story.player) : canSave();
  keep(saves, { reason, frame: world.frame, sent });
  if (!sent) {
    return pumping;
  }
  const owner = playing();
  const job = { story: owner, text: JSON.stringify(buildSave(fresh)) };
  if (waiting.at(-1)?.story === owner) {
    waiting[waiting.length - 1] = job;
  } else {
    waiting.push(job);
  }
  if (!sending) {
    pumping = pump();
  }
  return pumping;
}

// The pause menu's SAVE GAME
export function saveNow() {
  return savePoint("save game");
}

// The back button: a story open in the world is saved first, then the hub's menu comes back. When that save fails the
// player stays, with SAVE FAILED showing, and a second press leaves without it. A second press while the save is
// still on its way leaves at once, and the page closing sends the newest packed copy
export async function saveOnLeave() {
  if (backSaving) {
    backToMenu();
    return;
  }
  if (canSave() && !backFailed) {
    backSaving = true;
    const ok = await savePoint("leave");
    backSaving = false;
    if (!ok) {
      backFailed = true;
      return;
    }
  }
  leaving = true;
  backToMenu();
}

// The page is going: the newest packed copy goes with keepalive when the browser allows its size
function onPageHide() {
  if (leaving || !canSave() || !page.hub || !prepared || prepared.story !== current) {
    return;
  }
  if (prepared.packed.length > KEEPALIVE_MOST) {
    return;
  }
  const { slot, rev } = current;
  page.hub
    .api("save", { slot, save: prepared.packed, rev }, { keepalive: true })
    .catch((e) => console.warn("Union City: couldn't save as the page closed", e));
}

// Each game minute the pagehide copy is packed again from the story as it stands
function refreshPrepared() {
  if (canSave()) {
    const owner = playing();
    pack(owner, JSON.stringify(buildSave())).catch((e) => console.warn("Union City: couldn't pack a save", e));
  }
}

// ---------- Slots ----------

// The three slots' summaries (null for an empty one, and for a dead one). This page's saves still on their way land
// first, and the dead slots' wipes are tried again
export async function listSlots() {
  await pumping;
  await buryDead();
  const reply = await ask("slots", {});
  return reply.slots.map((summary, index) => (deadOf(SLOTS[index]) ? null : summary));
}

// Loads a slot and plays it, once this page's saves still on their way have landed. Resolves false when the slot is
// empty or its story died in Hardcore
export async function loadSlot(n) {
  await pumping;
  if (deadOf(n)) {
    return false;
  }
  const reply = await ask("load", { slot: n });
  if (!reply.save) {
    return false;
  }
  await applySave(await unpack(reply.save), n, reply.rev);
  return true;
}

// One wipe with a revision: DONE, FAILED or STALE
async function sendWipe(slot, rev) {
  try {
    const reply = await ask("wipe", { slot, rev });
    return reply.stale ? STALE : DONE;
  } catch (e) {
    console.warn(`Union City: couldn't empty slot ${slot}`, e);
    return FAILED;
  }
}

// Stops what is still to go to a slot about to be emptied
function dropSends(slot) {
  keep(wipes, { slot, frame: world.frame });
  waiting = waiting.filter((each) => each.story.slot !== slot);
  if (prepared?.story.slot === slot) {
    prepared = null;
  }
}

// Empties a slot (New Story over it). A save still on its way goes first, so it can't land after. Resolves DONE,
// FAILED, or STALE when another device saved or wiped the slot since this page last listed it
export async function wipeSlot(slot) {
  dropSends(slot);
  await pumping;
  return sendWipe(slot, listed[slot] ?? 0);
}

// ---------- Dead slots ----------

// A slot whose story died in Hardcore stays dead on this device, under its own key, until the bot has emptied it or
// holds another story there. The key is read again at every listing and load, so another tab's changes count

function deadKey(slot) {
  return `${DEAD_STORE}.${page.hub?.player?.id ?? "offline"}.${slot}`;
}

// { rev, id } for a dead slot: the revision its wipe sends and the story that died. null for a living one
function deadOf(slot) {
  try {
    const text = localStorage.getItem(deadKey(slot));
    if (text) {
      return JSON.parse(text);
    }
  } catch (e) {
    console.warn(`Union City: couldn't read whether slot ${slot} is dead`, e);
  }
  return deadHere[slot] ?? null;
}

function markDead(slot, dead) {
  deadHere[slot] = dead;
  try {
    localStorage.setItem(deadKey(slot), JSON.stringify(dead));
  } catch (e) {
    console.warn(`Union City: couldn't keep slot ${slot} as dead`, e);
  }
}

function forgetDead(slot) {
  delete deadHere[slot];
  try {
    localStorage.removeItem(deadKey(slot));
  } catch (e) {
    console.warn(`Union City: couldn't forget that slot ${slot} is dead`, e);
  }
}

// Empties a dead slot. True once it is done with: the bot emptied it, or the slot holds nothing or another story. A
// refusal means the slot moved on, as when this story's last save went through but its answer was lost: the slot is
// looked at and emptied when it still holds the story that died
async function bury(slot, dead) {
  const result = await sendWipe(slot, dead.rev);
  if (result !== STALE) {
    return result === DONE;
  }
  try {
    const found = await saveIn(slot);
    if (found.id !== dead.id) {
      return true;
    }
    return (await sendWipe(slot, found.rev)) === DONE;
  } catch (e) {
    console.warn(`Union City: couldn't look at slot ${slot} to empty it`, e);
    return false;
  }
}

async function sendDeadWipes() {
  for (const slot of SLOTS) {
    const dead = deadOf(slot);
    if (dead && (await bury(slot, dead))) {
      forgetDead(slot);
    }
  }
}

function buryDead() {
  burying = burying.then(sendDeadWipes);
  return burying;
}

// A Hardcore death (showDeath): the story's slot is dead on this device at once, so it never loads again, then it is
// emptied once the story's last save on its way has landed. A wipe that fails is tried again at every slot listing.
// Resolves whether the bot emptied it
export async function endStory() {
  const owner = playing();
  dropSends(owner.slot);
  markDead(owner.slot, { rev: owner.rev, id: owner.id });
  await pumping;
  markDead(owner.slot, { rev: owner.rev, id: owner.id });
  await buryDead();
  return !deadOf(owner.slot);
}

export function initSave(owner) {
  page = owner;
  world.onMinute(refreshPrepared);
  // Another story begins, or a save loads: the last one's packed copy and revision are done with
  world.onReset(() => {
    current = null;
    prepared = null;
  });
  window.addEventListener("pagehide", onPageHide);
}

// Helpers for page.py checks
export const saveDebug = {
  buildSave,
  applySave,
  saveNow,
  saveOnLeave,
  loadSlot,
  listSlots,
  wipeSlot,

  // The sizes of the story's save now: the text and the packed base64
  async saveSize() {
    const text = JSON.stringify(buildSave());
    const packed = toBase64(await streamBytes(new TextEncoder().encode(text), new CompressionStream("gzip")));
    return { raw: text.length, packed: packed.length, keys: Object.keys(buildSave().data).length };
  },

  saveState() {
    return {
      open: storyOpen(),
      sending,
      waiting: waiting.length,
      prepared: prepared && { slot: prepared.story.slot, size: prepared.packed.length, raw: prepared.raw },
      sends: sends.map((each) => ({ ...each })),
      wipes: wipes.map((each) => ({ ...each })),
      leaving,
      backFailed,
      story: current && { ...current },
      listed: { ...listed },
      dead: Object.fromEntries(SLOTS.map((slot) => [slot, deadOf(slot)]).filter(([, dead]) => dead)),
    };
  },

  // Runs what the page does as it closes
  pageHide: onPageHide,
};
