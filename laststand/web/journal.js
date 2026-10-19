// The journal (questJournal, sprite 5848; openJournal F4:3326, updateQuestInfo F4:3378, trackQuest F4:3443,
// setTrackQuestText F4:3486): the quests the player has accepted and not finished, down the left page, and the picked
// one's name, story and reward on the right. A star beside each quest tracks it: that quest's short objective, or for a
// fetch quest "count / need - ITEM" for each item, shows at the top right of the HUD. Only one quest is tracked at a
// time, and a press on its star again stops tracking it. J and the dock's journal button open and close it.
//
// A row picks its quest when the pointer or finger comes up on it without having dragged. The original picked on the
// press and never scrolled; the page also scrolls the list with the wheel and by dragging, so a press can start a drag.
//
// A quest's state is story.quests[id] (story.questState): active while accepted, completed when finished, tracking
// for the star. The quest engine sets them and calls trackQuest when a quest is accepted (setActiveQuest F4:3022).
import { data } from "./data.js";
import { help } from "./help.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { canOpenPanel, closePanel, finger, openPanel, panelOpen, setAlpha, setColor, wheelStep } from "./panels.js";
import { refuseOpen } from "./player.js";
import { lookup } from "./search.js";
import { sound } from "./sound.js";
import { fillText, questState, story } from "./story.js";
import { world } from "./world.js";

const PANEL = "journal";
const WHITE = "#ffffff";
const BLACK = "#000000";
// A row is invItemYDist tall, and the list's mask shows 243 px (the art's 189 px mask at a y scale of 1.2857)
const ROW_HEIGHT = 22;
const VIEW_HEIGHT = 243;
// How far a press has to move before it is a drag and not a tap
const SWIPE = 8;
const LEFT_BUTTON = 0;
// The art is drawn around its middle, which sits at the stage's middle, 7 px up (openJournal F4:3341)
const CENTRE = { x: 380, y: 193 };

// The journal open now: { clip, rows: [{ id, clip }], container, pos, drag }
let view = null;
// The tracked quest's lines last drawn on the HUD, so the HUD is only touched when they change
let drawn = null;

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

// ---------- The quests ----------

// The quests accepted and not completed, in the original's order
function activeIds() {
  return Object.keys(data.story.quests).filter((id) => {
    const state = story.quests[id];
    return state?.active && !state.completed;
  });
}

// The quest the HUD tracks: one marked tracking that is not finished (setTrackQuestText F4:3489)
function trackedId() {
  const ids = Object.keys(story.quests ?? {}).filter((id) => story.quests[id].tracking && !story.quests[id].completed);
  return ids.at(-1) ?? null;
}

// How many of a fetch item the backpack holds, up to the count the quest needs. Worn items do not count
function held(ref, need) {
  return Math.min(need, story.inventory.filter((row) => row.ref === ref && !row.eqd).length);
}

// The HUD's lines for the tracked quest: its title, then its objectives (setTrackQuestText F4:3486)
function trackedLines() {
  const id = trackedId();
  const def = id && data.story.quests[id];
  if (!def) {
    return null;
  }
  const lines = [fillText(def.desc)];
  if (def.type === "fetch") {
    for (const { ref, count } of def.items) {
      lines.push(`${held(ref, count)} / ${count} - ${(lookup(ref)?.name ?? ref).toUpperCase()}`);
    }
  } else if (def.shortDesc) {
    lines.push(fillText(def.shortDesc));
  }
  return lines;
}

// Puts the tracked quest on the HUD, or clears it when none is tracked. Skipped when the lines are what they were
export function refreshTracked(force = false) {
  const lines = story.quests ? trackedLines() : null;
  const key = JSON.stringify(lines);
  if (!force && key === drawn) {
    return;
  }
  drawn = key;
  hud.trackedQuest(lines);
}

// A star press: this quest is tracked and every other stops, or if it was tracked it stops (trackQuest F4:3443)
export function trackQuest(id) {
  const state = questState(id);
  const on = !state.tracking;
  for (const other of Object.values(story.quests)) {
    other.tracking = false;
  }
  state.tracking = on;
  refreshTracked();
  if (view) {
    showStars();
  }
}

// ---------- Painting ----------

// The picked quest's name, story and reward on the right page (updateQuestInfo F4:3378). Nothing picked shows nothing
function showInfo(id) {
  const clip = view.clip;
  const def = id && data.story.quests[id];
  const panel = clip.child("rewardPanel");
  panel.visible = Boolean(def);
  setText(clip.child("name"), def ? fillText(def.desc).toUpperCase() : "");
  setText(clip.child("content"), def ? fillText(def.longDesc).toUpperCase() : "");
  setText(panel.child("rewardText"), def ? rewardLine(def) : "");
  setText(panel.child("XPrewardText"), def ? `${def.xp} XP` : "");
}

// The items a quest gives, or who joins the player. A partner shows no items (F4:3417)
function rewardLine(def) {
  if (def.partner) {
    return "";
  }
  const names = def.rewards.map((ref) => lookup(ref)?.name ?? ref);
  if (def.follower) {
    names.push(`${def.owner} WILL BECOME YOUR COMPANION`);
  }
  return names.join(", ").toUpperCase();
}

// The row for a quest lit red with white words, and the others plain (selectQuestInList F4:3424)
function select(id) {
  for (const row of view.rows) {
    const on = row.id === id;
    row.clip.child("selected").visible = on;
    setColor(row.clip.child("questName"), on ? WHITE : BLACK);
  }
  view.picked = id;
  showInfo(id);
}

// A star on each tracked quest's row. The tracked quest is the one picked (setupTrackedQuest F4:3468)
function showStars() {
  let tracked = null;
  for (const row of view.rows) {
    const on = Boolean(story.quests[row.id]?.tracking);
    row.clip.child("star").visible = on;
    tracked = on ? row.id : tracked;
  }
  if (tracked) {
    select(tracked);
  }
}

// ---------- Scrolling ----------

function scrollRoom() {
  return Math.max(0, view.rows.length * ROW_HEIGHT - VIEW_HEIGHT);
}

function scrollTo(position) {
  view.pos = Math.min(0, Math.max(position, -scrollRoom()));
  view.container.y = view.pos;
}

// The pointer's height in the list's own pixels, which stay still while the rows scroll
function pointerY() {
  return view.container.parent.toLocal(view.clip.lib.pointer).y;
}

// Every step the panel is open: the wheel turns the list, and a press that has moved far enough drags it
function step() {
  if (!view) {
    return;
  }
  if (input.wheel) {
    scrollTo(view.pos - wheelStep());
  }
  const drag = view.drag;
  if (drag) {
    const moved = pointerY() - drag.y;
    drag.swiping ||= Math.abs(moved) >= SWIPE;
    if (drag.swiping) {
      scrollTo(drag.from + moved);
    }
  }
}

// A press on a row or its star: it may become a drag, and is a tap when it comes up without one
function press(id, star, event) {
  if (finger(event) || event?.button === LEFT_BUTTON) {
    view.drag = { id, star, y: pointerY(), from: view.pos, swiping: false };
  }
}

function release(id, star) {
  const drag = view.drag;
  view.drag = null;
  if (!drag || drag.swiping || drag.id !== id || drag.star !== star) {
    return;
  }
  if (star) {
    sound.play("sound_interfacePage3");
    trackQuest(id);
  } else {
    sound.play("sound_interfacePage1");
    select(id);
  }
}

function addRow(container, id, index) {
  const clip = view.clip.lib.makeExported("questListItem");
  container.attach(clip, `item${id}`);
  clip.y = index * ROW_HEIGHT;
  const backing = clip.child("backing");
  setAlpha(backing, index % 2 === 1 ? 0 : constant("itemGreyAlpha", 15) / 100);
  setText(clip.child("questName"), fillText(data.story.quests[id].desc).toUpperCase(), BLACK);
  clip.child("selected").visible = false;
  clip.child("star").visible = false;
  for (const [part, star] of [
    [backing, false],
    [clip.child("trackButton"), true],
  ]) {
    part.setHandler("onPress", (event) => press(id, star, event));
    part.setHandler("onRelease", () => release(id, star));
    part.setHandler("onReleaseOutside", () => {
      view.drag = null;
    });
  }
  view.rows.push({ id, clip });
}

// ---------- Opening and closing ----------

function build(clip) {
  const container = clip.child("scrollPanel").child("scrollContainer");
  view = { clip, container, rows: [], pos: 0, drag: null, picked: null };
  hud.hidePlay(true);
  clip.position.set(CENTRE.x, CENTRE.y);
  clip.child("exitBtn").setHandler("onPress", () => input.swallowPress());
  clip.child("exitBtn").setHandler("onRelease", () => closePanel());
  activeIds().forEach((id, index) => addRow(container, id, index));
  select(null);
  showStars();
}

function finish() {
  view = null;
  hud.hidePlay(false);
  sound.play("sound_closeInterface");
  hud.refresh();
}

// Opens the journal (openJournal F4:3326)
export function openJournal() {
  openPanel(PANEL, { art: "questJournal", setup: build, close: finish });
  sound.play("sound_openInterface");
  help.did("journal");
}

function toggle() {
  if (panelOpen(PANEL)) {
    closePanel();
  } else if (canOpenPanel()) {
    openJournal();
  }
}

// J. A zombie's hold refuses the opening with its alert
function keys() {
  if (!input.journalPressed) {
    return;
  }
  input.journalPressed = false;
  if (panelOpen(PANEL) || !canOpenPanel() || !refuseOpen()) {
    toggle();
  }
}

export const journal = {
  open: openJournal,
  close: closePanel,
  toggle,
  track: trackQuest,
  refresh: refreshTracked,
  get isOpen() {
    return panelOpen(PANEL);
  },
};

export function initJournal() {
  world.stage("interface", keys);
  world.stage("interface", step);
  // A fetch quest's counts follow the backpack, which changes anywhere
  world.stage("slow", () => refreshTracked());
  hud.onOpen("journal", toggle);
  world.onReset(() => {
    view = null;
    refreshTracked(true);
  });
}

// Helpers for page.py checks
export const journalDebug = {
  // Opens the journal and says what it shows
  journal() {
    openJournal();
    return journalDebug.journalState();
  },

  // What the open journal shows, in words and numbers; null when it is shut
  journalState() {
    if (!view) {
      return null;
    }
    const clip = view.clip;
    const panel = clip.child("rewardPanel");
    return {
      paused: world.paused,
      rows: view.rows.map((row) => ({
        id: row.id,
        name: row.clip.child("questName").text,
        star: row.clip.child("star").visible,
        selected: row.clip.child("selected").visible,
        y: row.clip.y,
      })),
      picked: view.picked,
      name: clip.child("name").text,
      content: clip.child("content").text,
      reward: panel.visible ? panel.child("rewardText").text : null,
      xp: panel.visible ? panel.child("XPrewardText").text : null,
      scroll: view.container.y,
      hud: drawn,
    };
  },

  // A tap on a row or on its star, as a press and a release
  journalTap(id, star = false) {
    const row = view.rows.find((each) => each.id === id);
    const part = star ? row.clip.child("trackButton") : row.clip.child("backing");
    part.handlers.onPress({ pointerType: "mouse", button: LEFT_BUTTON });
    part.handlers.onRelease({ pointerType: "mouse", button: LEFT_BUTTON });
    return journalDebug.journalState();
  },
};
