// The quest engine (setActiveQuest F4:3019, completeQuest F4:3067, giveQuestRewards F4:3209, checkForQuestItems F4:3237,
// questStartCompleteAnim F4:3162, the table F4:2368-2853): accepting and finishing the 33 quests of data.story.quests.
//
// Accepting a quest (startQuest) tracks it on the HUD, sets the NPC states it changes, opens the map sections and
// doors it opens, sets off the triggers it names, plays its cutscene, hands over its start items ("YOU GOT ...") and
// shows "TASK ACCEPTED". The cutscene and the start items come only the first time. When a second quest is active the
// journal hint shows.
//
// Finishing a quest (completeQuest) hands over its reward items, a companion or the partner, opens its map sections and
// pays its XP, then sets the NPC states it changes, counts the achievements ("quest900" and its kin, and "finishQuest"
// for "I Can Help" and "Taskmaster"), sets off its finishing trigger and shows "TASK COMPLETE". The three types:
//   talk: finishes only when spoken to at its target NPC (Q1), by questCheck("talk", key) or completeQuest(id, key).
//   fetch: finishes when the backpack holds every item (a worn or wielded one does not count); the items are handed in.
//   triggered: finishes only when it was accepted (Q35), by a trigger's completeQuest.
// The banner shows only when a quest really finished (Q36).
//
// A quest's state is story.quests[id] (story.questState). The systems built after this one plug in with quests.hooks:
// trigger(n) sets off trigger n (Task 55), cutscene(n) plays a cutscene (Task 56), npcState(key, state) redraws an
// NPC whose state changed (Task 53) and finished(id) lets an open dialog show a talk or fetch quest's finished text.
import { achieve } from "./achieve.js";
import { addCompanion, partner } from "./companions.js";
import { unlockSections } from "./citymap.js";
import { data } from "./data.js";
import { help } from "./help.js";
import { hud } from "./hud.js";
import { addItem, removeRow } from "./inventory.js";
import { refreshTracked } from "./journal.js";
import { addXP } from "./player.js";
import { lookup } from "./search.js";
import { fillText, questState, story } from "./story.js";
import { world } from "./world.js";

const MOST_RECORDED = 100;
// A quest id is three characters: "900", "004"
const ID_WIDTH = 3;

// What was accepted, finished and refused, newest last, for checks
const log = [];

function note(kind, id, extra = {}) {
  log.push({ kind, id, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

function idOf(id) {
  return String(id).padStart(ID_WIDTH, "0");
}

function defOf(id) {
  return data.story.quests[idOf(id)] ?? null;
}

function isActive(id) {
  const state = story.quests?.[idOf(id)];
  return Boolean(state?.active && !state.completed);
}

function isDone(id) {
  return story.quests?.[idOf(id)]?.completed === true;
}

function activeCount() {
  return Object.values(story.quests).filter((state) => state.active && !state.completed).length;
}

// ---------- Fetching ----------

// The rows of the backpack that count toward one needed item: that item, not worn or wielded
function heldRows(ref) {
  return story.inventory.filter((row) => row.ref === ref && !row.eqd);
}

// Whether the backpack holds everything a fetch quest asks for (checkForQuestItems F4:3237 with checking set)
export function fetchReady(id) {
  const def = defOf(id);
  return def?.type === "fetch" && def.items.every(({ ref, count }) => heldRows(ref).length >= count);
}

// Takes the quest's items out of the backpack, as many of each as it asks for
function handIn(def) {
  for (const { ref, count } of def.items) {
    for (const row of heldRows(ref).slice(0, count)) {
      removeRow(row);
    }
  }
}

// ---------- NPCs, doors and triggers ----------

// An NPC's state set to a number (changeNPCState F4:23232), even one switched off. The NPC system redraws it
function setNpcState(key, state) {
  story.npcs[key] = { ...story.npcs[key], state };
  quests.hooks.npcState?.(key, state);
}

// A door of a room opens for good, with no alert: the player is usually elsewhere (unlockDoor F4:14873 with a remote id)
function openDoor(key) {
  story.doors[key] = false;
}

// ---------- Accepting ----------

function giveStartRewards(def) {
  for (const ref of def.startRewards) {
    addItem(ref);
    hud.banner("gotItem", lookup(ref)?.name ?? ref);
  }
}

// Accepts a quest. Returns whether it was accepted: a quest already active or finished is left as it is
export function startQuest(id) {
  const def = defOf(id);
  if (!def || !story.quests) {
    return false;
  }
  const state = questState(def.id);
  if (state.active || state.completed) {
    note("refused", def.id, { why: state.completed ? "done" : "active" });
    return false;
  }
  state.active = true;
  for (const other of Object.values(story.quests)) {
    other.tracking = false;
  }
  state.tracking = true;
  for (const { npc, state: npcState } of def.startStates) {
    setNpcState(npc, npcState);
  }
  unlockSections(def.startUnlocks);
  for (const trigger of def.startTriggers) {
    quests.hooks.trigger?.(trigger);
  }
  if (!state.started) {
    state.started = true;
    if (def.startCutscene !== null) {
      quests.hooks.cutscene?.(def.startCutscene);
    }
    giveStartRewards(def);
  }
  def.startDoors.forEach(openDoor);
  if (activeCount() > 1) {
    help.show("journal");
  }
  hud.banner("accepted", fillText(def.desc));
  refreshTracked(true);
  note("start", def.id);
  return true;
}

// ---------- Finishing ----------

// The quest can finish now: talk at its NPC, fetch with the items in the bag, triggered once it was accepted
function canComplete(def, npcKey) {
  if (!isActive(def.id)) {
    return false;
  }
  if (def.type === "talk") {
    return npcKey === def.talk;
  }
  return def.type === "fetch" ? fetchReady(def.id) : true;
}

// The reward items, then the companion or partner, the map sections and the XP (giveQuestRewards F4:3209)
function giveRewards(def) {
  for (const ref of def.rewards) {
    addItem(ref);
  }
  if (def.follower) {
    addCompanion(def.owner);
  }
  if (def.partner) {
    partner.joinPartner(def.owner);
  }
  unlockSections(def.unlocks);
  addXP(def.xp);
}

// Finishes a quest. npcKey is who the player spoke to, for a talk quest. Returns whether it finished
export function completeQuest(id, npcKey = null) {
  const def = defOf(id);
  if (!def || !story.quests || !canComplete(def, npcKey)) {
    note("refused", idOf(id), { why: "not ready" });
    return false;
  }
  if (def.type === "fetch") {
    handIn(def);
  }
  giveRewards(def);
  const state = questState(def.id);
  state.completed = true;
  state.active = false;
  // An open dialog redraws at the finished text before the quest changes the people's states (F4:3067)
  if (def.type !== "triggered") {
    quests.hooks.finished?.(def.id);
  }
  for (const { npc, state: npcState } of def.completeStates) {
    setNpcState(npc, npcState);
  }
  achieve.add(`quest${def.id}`);
  achieve.add("finishQuest");
  for (const trigger of def.completeTriggers) {
    quests.hooks.trigger?.(trigger);
  }
  hud.banner("complete", fillText(def.desc));
  refreshTracked(true);
  note("complete", def.id);
  return true;
}

// ---------- Checking ----------

// The ids of the active quests that a thing the player did finishes
function finishing(match) {
  return Object.keys(data.story.quests).filter((id) => isActive(id) && match(data.story.quests[id]));
}

// Something happened that may finish quests. kind is "talk" (value: the NPC's key), "trigger" (a trigger number: the
// triggered quests it finishes) or "note" (a note number, as its closing trigger). Returns the ids that finished
export function questCheck(kind, value) {
  let ids = [];
  if (kind === "talk") {
    ids = finishing((def) => def.type === "talk" && def.talk === value);
  } else if (kind === "trigger") {
    const named = (data.story.triggers[value]?.funcs ?? []).filter(([name]) => name === "completeQuest");
    ids = named.map(([, id]) => id).filter((id) => isActive(id) && defOf(id).type === "triggered");
  } else if (kind === "note") {
    const trigger = data.story.notes[value]?.trigger;
    return trigger === null || trigger === undefined ? [] : questCheck("trigger", trigger);
  }
  return ids.filter((id) => completeQuest(id, kind === "talk" ? value : null));
}

export const quests = {
  start: startQuest,
  complete: completeQuest,
  check: questCheck,
  fetchReady,
  isActive,
  isDone,
  // Where the systems built later plug in: trigger(n), cutscene(n), npcState(key, state) and finished(id)
  hooks: { trigger: null, cutscene: null, npcState: null, finished: null },
  log,
};

export function initQuests() {
  world.onReset(() => {
    log.length = 0;
  });
}

// Helpers for page.py checks
export const questsDebug = {
  // Accepts a quest and says where it stands
  questStart(id) {
    return { accepted: startQuest(id), ...questsDebug.questState() };
  },

  // Finishes a quest (npcKey for a talk quest) and says where it stands
  questComplete(id, npcKey = null) {
    return { completed: completeQuest(id, npcKey), ...questsDebug.questState() };
  },

  // questCheck, with the ids it finished
  questCheck(kind, value) {
    return { finished: questCheck(kind, value), ...questsDebug.questState() };
  },

  // The quests that were ever touched (their flags), the HUD's tracked lines, the map and NPC states
  questState() {
    const flags = {};
    for (const [id, state] of Object.entries(story.quests ?? {})) {
      flags[id] = ["started", "active", "completed", "tracking"].filter((key) => state[key]).join(" ");
    }
    return {
      quests: flags,
      hud: {
        title: hud.part("activeQuestText")?.child("txt")?.text,
        objectives: hud.part("activeQuestText")?.child("objectives")?.text,
      },
      banner: hud.banners.at(-1) ?? null,
      alerts: hud.alerts.map((each) => each.text),
      map: [...story.map.unlocked],
      npcs: Object.fromEntries(Object.entries(story.npcs).map(([key, each]) => [key, each.state])),
      doors: { ...story.doors },
      backpack: story.inventory.map((row) => row.ref),
      xp: story.player.xp,
      follower: story.player.follower,
      partner: story.player.partner,
    };
  },

  questLog() {
    return log.map((each) => ({ ...each }));
  },
};
