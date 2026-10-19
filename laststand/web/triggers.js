// The story's triggers (defineTriggers F4:17365, hitTrigger F4:17348, triggerCollisions F4:17332, turnOnTrigger
// F4:17321): invisible zones in the rooms that run a short list of story functions the first time the player stands in
// them. data.story.triggers holds each one: its number, whether it starts armed and the functions it runs in order,
// each [name, ...arguments] with the original's arguments as text.
//
// A zone is a "trig" marker in the room's art, named trig<number>. Every step the player's x is checked against the
// markers of the room, and the first armed one whose centre is closer than half its width fires (one a step, as the
// original breaks after the first). A trigger fires once: story.triggers[n] = { triggered } is set after its functions
// ran, and a trigger that starts unarmed begins with triggered true until another trigger arms it (armTrigger). A
// trigger with no zone in any room (the ones quests, notes and the partner set off) fires through fireTrigger:
// quests.hooks.trigger and notes.hooks.trigger are this file's fireTrigger, and the partner being placed in a room
// fires trigger 32.
//
// The functions a trigger names are in a table by the original's names. The ones whose system is built later register
// themselves with triggers.register(name, fn): showEnding (the ending) is the one still waiting. startCutScene goes to
// quests.hooks.cutscene, which a quest's start cutscene uses as well. Trigger 60 also switches on Jane and Shawn's
// pair, who stand in the monument room's list of humans but are never switched on in the original's data.
import { unlockSection } from "./citymap.js";
import { onPartnerPlaced, partner } from "./companions.js";
import { data } from "./data.js";
import { director } from "./director.js";
import { help } from "./help.js";
import { humanTurnHostile, spawnHuman } from "./humans.js";
import { unlockDoor } from "./interact.js";
import { notes } from "./notes.js";
import { npcs, say, setNPCState, stateOf as npcState, turnOffNPC, turnOnNPC } from "./npcs.js";
import { completeQuest, quests, startQuest } from "./quests.js";
import { room } from "./rooms.js";
import { story } from "./story.js";
import { world } from "./world.js";

const MOST_RECORDED = 100;
// A zone marker's name is "trig" and the trigger's number
const ZONE_NAME = /^trig(\d+)$/;
const SPEAKER_NAME = /^human\d+$/;
// The pair trigger 60 switches on in the monument room
const SACRIFICE = new Set(["JaneSacrifice", "ShawnSacrifice"]);
// Jack's state after the dock warehouse, in place of the one that skips his offer (fixJack F4:23598)
const JACK_SKIPPED = 5;
const JACK_FIXED = 4;
// The triggers that do more than their list says
const SPECIALS = { 60: switchOnSacrifice };

// What fired, was refused or had no system to run it, newest last, for checks
const log = [];
// The functions by the original's names: fn(...arguments) with the arguments as the data holds them
const functions = new Map();
// The triggers whose functions are running now, so one that sets itself off again does not loop
const running = new Set();
// The humans the running trigger set up (Jeb and Paul turned hostile)
let turned = [];

function note(kind, n, extra = {}) {
  log.push({ kind, n, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

function defOf(n) {
  return data.story?.triggers?.[n] ?? null;
}

// A trigger's number from a number or its name, "trig14"
function numberOf(ref) {
  return Number(String(ref).replace(/^trig/, ""));
}

// A trigger's state in the save: triggered is true once it fired, and for one that has not been armed yet
function stateOf(n) {
  story.triggers[n] ??= { triggered: defOf(n)?.armed !== true };
  return story.triggers[n];
}

function isArmed(n) {
  return Boolean(defOf(n)) && !stateOf(n).triggered;
}

// Arms a trigger, so its zone fires the next time the player stands in it (turnOnTrigger)
export function armTrigger(ref) {
  const n = numberOf(ref);
  if (!defOf(n) || !story.triggers) {
    return false;
  }
  stateOf(n).triggered = false;
  note("arm", n);
  return true;
}

// ---------- The functions ----------

// A person who says a line: "human<number>" names a human in the room. The original's numbering runs on from room to
// room, so the name stands for whoever the trigger itself just set up (Jeb and Paul), else the human with that name,
// else the first one still standing. "player", "partner" and "npc_<key>" are the speech bubbles' own names
function speakerFor(target) {
  if (!SPEAKER_NAME.test(target)) {
    return target;
  }
  const standing = world.humans.filter((each) => each.alive !== false);
  const fresh = standing.find((each) => turned.includes(each));
  return fresh ?? standing.find((each) => each.name === target) ?? standing[0] ?? null;
}

function speak(target, text) {
  const speaker = speakerFor(target);
  if (!speaker || !say(speaker, text)) {
    note("silent", null, { target });
  }
}

// The map section a name such as "section11" stands for
function sectionOf(name) {
  return Number(String(name).replace(/^section/, ""));
}

// Jane and Shawn stand where the monument room lists them
function switchOnSacrifice() {
  for (const entry of room.def?.enemies ?? []) {
    if (SACRIFICE.has(entry.key)) {
      turnOnNPC(entry.key);
      if (!world.humans.some((each) => each.key === entry.key)) {
        spawnHuman(entry.key, entry.x);
      }
    }
  }
}

// The quest-giving state of Jack is put right if the dock warehouse left it at the one that skips his offer
function fixJack() {
  const state = npcState("Jack");
  if (state === JACK_SKIPPED || state === undefined) {
    setNPCState("Jack", JACK_FIXED);
  }
}

function startCutScene(n) {
  if (quests.hooks.cutscene) {
    quests.hooks.cutscene(Number(n));
  } else {
    note("missing", null, { fn: "startCutScene", n });
  }
}

const BUILT_IN = {
  setActiveQuest: startQuest,
  completeQuest,
  displayWorldSpeech: speak,
  showHelp: (name, seconds) => help.show(name, seconds === undefined ? null : Number(seconds)),
  unlockAreas: (quest, section) => unlockSection(sectionOf(section)),
  unlockArea: (section) => unlockSection(sectionOf(section)),
  unlockEndLoc: (n) => unlockSection(Number(n), true),
  unlockDoor,
  turnOnNPC,
  turnOffNPC,
  removeNPC: (key) => npcs.remove(key),
  turnOnTrigger: armTrigger,
  addPartner: (key) => partner.joinPartner(key),
  startCutScene,
  startEndingRush: () => director.endingRush(true),
  triggerJebAndPaul: () => {
    turned = [humanTurnHostile("Jeb"), humanTurnHostile("Paul")].filter(Boolean);
  },
  fixJack,
};

for (const [name, fn] of Object.entries(BUILT_IN)) {
  functions.set(name, fn);
}

// Gives a function a system built later owns (showEnding): fn(...arguments)
export function registerTriggerFunction(name, fn) {
  functions.set(name, fn);
}

function call(n, [name, ...args]) {
  const fn = functions.get(name);
  if (!fn) {
    note("missing", n, { fn: name });
    return;
  }
  try {
    fn(...args);
  } catch (e) {
    console.warn(`Union City: trigger ${n} couldn't run ${name}`, e);
    note("failed", n, { fn: name });
  }
}

// ---------- Firing ----------

// Runs a trigger's functions in order, then marks it fired. A trigger already fired does nothing unless forced
// (hitTrigger). Returns whether it ran
export function fireTrigger(ref, forced = false) {
  const n = numberOf(ref);
  const def = defOf(n);
  if (!def || !story.triggers || running.has(n) || (!forced && !isArmed(n))) {
    return false;
  }
  running.add(n);
  turned = [];
  try {
    note("fire", n);
    def.funcs.forEach((each) => call(n, each));
    SPECIALS[n]?.();
    stateOf(n).triggered = true;
  } finally {
    running.delete(n);
    turned = [];
  }
  return true;
}

// The zones of the room as { n, x, w }, in the order the art placed them
function zonesHere() {
  const zones = [];
  for (const marker of Object.values(room.markers)) {
    const match = marker.kind === "trig" ? ZONE_NAME.exec(marker.name) : null;
    if (match) {
      zones.push({ n: Number(match[1]), x: marker.x, w: marker.w });
    }
  }
  return zones;
}

// Fires the first armed zone the player stands inside (triggerCollisions F4:17332), every step
function check() {
  const x = world.player?.x;
  if (!world.active || !story.triggers || !room.id || typeof x !== "number") {
    return;
  }
  const hit = zonesHere().find((zone) => isArmed(zone.n) && Math.abs(x - zone.x) < zone.w / 2);
  if (hit) {
    fireTrigger(hit.n);
  }
}

export const triggers = {
  fire: fireTrigger,
  arm: armTrigger,
  register: registerTriggerFunction,
  isArmed,
  // Where the later systems plug in: ending() plays the ending when trigger 61 fires
  hooks: { ending: null },
  log,
};

registerTriggerFunction("showEnding", () => {
  if (triggers.hooks.ending) {
    triggers.hooks.ending();
  } else {
    note("missing", 61, { fn: "showEnding" });
  }
});

export function initTriggers() {
  quests.hooks.trigger = fireTrigger;
  notes.hooks.trigger = fireTrigger;
  onPartnerPlaced(() => fireTrigger(32));
  world.stage("collisions", check);
  world.onReset(() => {
    log.length = 0;
    running.clear();
  });
}

// Helpers for page.py checks
export const triggersDebug = {
  // Fires a trigger by number as a quest or note would (forced fires it again) and says what it did
  triggerFire(n, forced = false) {
    return { ran: fireTrigger(n, forced), ...triggersDebug.triggerState() };
  },

  // Arms a trigger
  triggerArm(n) {
    return { armed: armTrigger(n), ...triggersDebug.triggerState() };
  },

  // The armed triggers, the fired ones, the zones of this room and the latest log lines
  triggerState() {
    const numbers = Object.keys(data.story?.triggers ?? {}).map(Number);
    return {
      armed: numbers.filter((n) => story.triggers && isArmed(n)),
      fired: Object.entries(story.triggers ?? {})
        .filter(([, each]) => each.triggered)
        .map(([n]) => Number(n)),
      zones: zonesHere(),
      log: log.slice(-10),
    };
  },

  triggerLog() {
    return log.map((each) => ({ ...each }));
  },

  // Every trigger's number, its room and the names of its functions
  triggerList() {
    return Object.values(data.story.triggers).map((def) => ({
      n: def.n,
      room: def.room,
      armed: def.armed,
      funcs: def.funcs.map(([name]) => name),
    }));
  },
};
