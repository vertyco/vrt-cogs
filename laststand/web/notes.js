// Notes (openNote F4:4410, closeNote F4:4436, setNoteContents F4:4452, saveNotes F4:4537): 36 papers left in the rooms,
// each "[E] INSPECT" when the player stands by it. A note opens over the world in one of five looks, which are the
// frame labels of the art (int_note, sprite 6225): notePad (a ruled pad), file (a typed page), herc (a notice on
// letterhead), wall (writing on the wall) and book (a diary page). The words of a wall, pad or book note are drawn in
// capitals; a file or HERC note keeps its own case. E, Esc or the CLOSE button shuts it.
//
// Reading a note the first time remembers it in story.notes ({ n: { read: true } }), saves, and adds one to the
// "readNote" counter ("Noted" and "I Know"). Closing note 5, 33 or 34 fires a story trigger (10, 22 and 27); the trigger
// engine plugs in with notes.hooks.trigger. Notes 23, 35 and 37 are never placed in a room and are not in the tables.
import { data } from "./data.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { register } from "./interact.js";
import { closePanel, openPanel, panelOpen, restButtons } from "./panels.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { fillText, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "note";
const KIND = "note";
const PROMPT = "[E] INSPECT";
// A note marker in the room's art is named "note" and its number
const MARKER_NAME = /^note(\d+)$/;
// The looks whose words are drawn in capitals (openNote F4:4426)
const CAPITALS = new Set(["wall", "notePad", "book"]);
const MOST_RECORDED = 100;
// CLOSE takes no press for this long after the note opens: on a phone it sits under the action button, and the second
// tap of a double tap on INSPECT would shut the note at once
const CLOSE_REST_SECONDS = 0.5;

// Registers fn(key, amount) for each counter a note adds to: "readNote" for a note read for the first time (checkAch
// F4:4424)
const countListeners = [];
// What was opened and closed, newest last, for checks
const log = [];
// The open note: { clip, n, def }
let view = null;

export function onNoteCount(fn) {
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

function record(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- The words ----------

// What a note says for this player: the names fill in, then a wall, pad or book note goes to capitals
function wordsOf(def) {
  const words = fillText(def.text);
  return def.upper && CAPITALS.has(def.style) ? words.toUpperCase() : words;
}

// ---------- Reading ----------

function wasRead(n) {
  return story.notes?.[n]?.read === true;
}

// The first reading is remembered and counted (openNote F4:4420)
function markRead(n) {
  if (wasRead(n)) {
    return;
  }
  story.notes[n] = { read: true };
  savePoint("notes");
  count("readNote");
}

function build(clip) {
  const { n, def } = view;
  view.clip = clip;
  hud.hidePlay(true);
  clip.gotoAndStop(def.style);
  setText(clip.child("contents"), wordsOf(def));
  clip.child("exitBtn").setHandler("onPress", () => input.swallowPress());
  clip.child("exitBtn").setHandler("onRelease", () => closePanel());
  restButtons([clip.child("exitBtn")], CLOSE_REST_SECONDS);
  markRead(n);
  record("open", { n, style: def.style });
}

// Closing fires the note's trigger, if it has one (closeNote F4:4441)
function finish() {
  const { n, def } = view;
  view = null;
  hud.hidePlay(false);
  sound.play("sound_closeInterface");
  record("close", { n, trigger: def.trigger ?? null });
  if (def.trigger !== null && def.trigger !== undefined) {
    notes.hooks.trigger?.(def.trigger);
  }
}

// Opens note n over the world. Returns whether there is such a note
export function openNote(n) {
  const def = data.story.notes[n];
  if (!def) {
    return false;
  }
  view = { clip: null, n, def };
  openPanel(PANEL, { art: "int_note", setup: build, close: finish });
  sound.play("sound_openInterface");
  return true;
}

// ---------- The note in the room ----------

function numberOf(thing) {
  return Number(MARKER_NAME.exec(thing.name)?.[1]);
}

function inspect(thing) {
  openNote(numberOf(thing));
}

// A marker of a note nobody wrote offers nothing
function available(thing) {
  return Boolean(data.story.notes[numberOf(thing)]);
}

export const notes = {
  open: openNote,
  close: closePanel,
  isRead: wasRead,
  onCount: onNoteCount,
  // The trigger engine's fireTrigger(n), called when a note with a trigger closes
  hooks: { trigger: null },
  get isOpen() {
    return panelOpen(PANEL);
  },
  log,
};

export function initNotes() {
  register(KIND, { prompt: () => PROMPT, use: inspect, available, look: { icon: "inspectIcon" } });
  world.onReset(() => {
    if (view) {
      hud.hidePlay(false);
    }
    view = null;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const notesDebug = {
  // Opens a note wherever the player stands and says what it shows
  noteOpen(n) {
    openNote(n);
    return notesDebug.noteState();
  },

  // What the open note shows; null when none is open
  noteState() {
    if (!view?.clip) {
      return null;
    }
    const { clip, n, def } = view;
    return {
      n,
      style: def.style,
      frame: clip.frame,
      text: clip.child("contents").text,
      paused: world.paused,
      read: wasRead(n),
    };
  },

  // A press and release on the CLOSE button
  noteClose() {
    view.clip.child("exitBtn").handlers.onRelease?.();
    return notesDebug.noteState();
  },

  // What was opened and closed so far
  noteLog() {
    return log.map((each) => ({ ...each }));
  },
};
