// The cutscenes (startCutScene F4:2113, the table F4:26174-26390): short lists of timed lines and actions, 11 of them in
// use. data.story.cutscenes holds each one as steps { at, action, args }, with `at` in game steps (30 a second) from
// the moment it starts. The original ran them on real-time timers; here every step is a game-clock timer, so a pause
// holds the next line where it is (S31).
//
// The actions are the ones the table uses:
//   displayWorldSpeech(target, text)  a bubble over "player", "partner" or "npc_<key>" (nothing when that person is not
//                                     here, as the original did nothing)
//   turnOnNPC(key), turnOffNPC(key)   a person switched on or off
//   setupAnNPCDirect(n)               the person at place n in this room's list stands in the room now
//   removePartner()                   the partner leaves
//   animateCharacter(name, label)     a placed part of the room plays a label (the dock wall's blast)
// Cutscene 6 runs its third action twice over: the docks partner is switched on, set up, and then the partner goes (Q7).
//
// A cutscene with lockControls (none of the used ones) locks the player's controls and hides the HUD until its last
// step has run. Nothing is saved: a cutscene cut short by a load is simply not played again.
import { partner } from "./companions.js";
import { data } from "./data.js";
import { hud } from "./hud.js";
import { npcs, npcsForRoom, turnOffNPC, turnOnNPC } from "./npcs.js";
import { player } from "./player.js";
import { gotoPlay } from "./rig.js";
import { room } from "./rooms.js";
import { quests } from "./quests.js";
import { world } from "./world.js";

const MOST_RECORDED = 100;

// What ran, newest last, for checks
const log = [];
// How many steps are still waiting, per cutscene run
let waiting = 0;
let locks = 0;

// True from the moment a cutscene starts until its last step has run
export let cutsceneActive = false;

function note(kind, n, extra = {}) {
  log.push({ kind, n, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// A placed part of the room, such as the wall blast, plays a label (animateCharacter F4:2205)
function animateCharacter(name, label) {
  const clip = room.markers[name]?.clip;
  if (clip) {
    gotoPlay(clip, label);
  } else {
    note("silent", null, { action: "animateCharacter", target: name });
  }
}

function speak(target, text) {
  if (!npcs.say(target, text)) {
    note("silent", null, { action: "displayWorldSpeech", target });
  }
}

// The person at that place in this room's list stands in the room now (setupAnNPCDirect F4:23130)
function setupAnNPCDirect(place) {
  const entry = npcsForRoom(room)[Number(place)];
  if (entry) {
    npcs.setupDirect(entry.key);
  }
}

const ACTIONS = {
  displayWorldSpeech: speak,
  turnOnNPC,
  turnOffNPC,
  setupAnNPCDirect,
  removePartner: () => partner.leavePartner(),
  animateCharacter,
};

function runStep(n, step) {
  const fn = ACTIONS[step.action];
  if (!fn) {
    note("missing", n, { action: step.action });
    return;
  }
  try {
    fn(...step.args);
    note("step", n, { action: step.action, at: step.at });
  } catch (e) {
    console.warn(`Union City: cutscene ${n} couldn't run ${step.action}`, e);
    note("failed", n, { action: step.action });
  }
}

function finish(def) {
  waiting -= 1;
  if (def.lockControls) {
    locks -= 1;
    if (locks === 0) {
      player.controlsLocked = false;
      hud.show(true);
    }
  }
  if (waiting === 0) {
    cutsceneActive = false;
  }
}

// Starts a cutscene: every step is set to run its number of steps from now. Returns whether it exists
export function playCutscene(n) {
  const number = Number(n);
  const def = data.story?.cutscenes?.[number];
  if (!def) {
    note("missing", number);
    return false;
  }
  note("start", number);
  cutsceneActive = true;
  waiting += 1;
  if (def.lockControls) {
    locks += 1;
    player.controlsLocked = true;
    hud.show(false);
  }
  const last = Math.max(...def.steps.map((step) => step.at));
  for (const step of def.steps) {
    world.later(step.at, () => runStep(number, step));
  }
  world.later(last, () => finish(def));
  return true;
}

export const cutscenes = {
  play: playCutscene,
  get active() {
    return cutsceneActive;
  },
  log,
};

export function initCutscenes() {
  quests.hooks.cutscene = playCutscene;
  world.onReset(() => {
    waiting = 0;
    locks = 0;
    cutsceneActive = false;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const cutscenesDebug = {
  // Plays a cutscene as a quest or trigger would
  cutscenePlay(n) {
    return { ran: playCutscene(n), active: cutsceneActive };
  },

  // Whether one is running, how many steps wait and the latest log lines
  cutsceneState() {
    return { active: cutsceneActive, waiting, log: log.slice(-12) };
  },

  // The numbers of the cutscenes the data holds
  cutsceneList() {
    return Object.keys(data.story.cutscenes).map(Number);
  },
};
