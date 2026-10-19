// The dialog panel and the NPC state machines (dialog F4:19561, displayDialog F4:19806, closeDialog F4:19792,
// changeNPCState F4:23232, sizeButtons F4:19548).
//
// Each NPC is a numbered state machine (story.npcs[key].state). In state N the box shows one of three texts, by where
// the state's quest stands: the offer (content) before it is accepted, the in-progress text (contentActive) while it is
// active and the finished text (contentComplete) once it is done. A state with no quest shows its one text with OK.
// The buttons follow the same three cases:
//   offer:    ACCEPT (starts the quest and closes) and DECLINE (closes).
//   active:   the "met" button when the quest can be finished (fetch: the items are in the backpack), which finishes it
//             and shows the finished text; otherwise the "not met" button, which closes.
//   finished: the finished button, which moves the NPC to the next state (when it has one) and closes.
// A state with a "next" and no quest (Jack's first talk) moves to that state on OK and leaves the box showing, and its
// next OK closes.
//
// Opening the box first lets the talk quests that name this person finish (Q1), so the box reads the state they leave.
// The words type at 4 characters a step, in the interface stage that runs while the world is held still, with the
// writing sound looping. The portrait is the person's head in their skin and hair colours. The reward
// panel under the words lists the quest's items, companion and XP. A box taller than its 230 px window scrolls by its
// bar, the wheel or a finger dragging the words.
import { data } from "./data.js";
import { TextField } from "./flash.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { npcs, setNPCState } from "./npcs.js";
import { closePanel, finger, openPanel, panelOpen, wheelStep } from "./panels.js";
import { quests, startQuest } from "./quests.js";
import { colourOf, goto, paintFlat, partAt, takeOver } from "./rig.js";
import { savePoint } from "./save.js";
import { lookup } from "./search.js";
import { sound } from "./sound.js";
import { fillText, story } from "./story.js";
import { Container, Rectangle } from "./vendor/pixi.min.mjs";
import { world } from "./world.js";

const PANEL = "dialog";
const WRITING = "writing";
// The box sits on the left when the person stands to the right of this stage x, otherwise 300 px from the right edge
const SIDE_SPLIT = 500;
const LEFT_X = 20;
const RIGHT_MARGIN = 300;
const BOX_Y = 90;
// The words show 230 px at a time; the thumb runs from 0 to 190 down the bar
const VIEW_HEIGHT = 230;
const BAR_TOP = 0;
const BAR_BOTTOM = 190;
// The words the box types a step (displayDialog)
const CHARS_PER_STEP = 4;
// The reward panel hangs this far under the invisible text that measures the words
const REWARD_GAP = 20;
// The height of the field the words are measured in; any height gives the same answer
const PROBE_HEIGHT = 20;
// The words, over the box's window: x and width of the part a finger can drag
const DRAG_AREA = { x: 46, y: 0, width: 208, height: VIEW_HEIGHT };
// The far button sits this far from the box's right side (sizeButtons)
const RIGHT_BUTTON_EDGE = 245;
// A button's face is its words plus dialogBtnSpace wide and its base plus dialogBtnBaseSpace; used until the converted
// constants load
const DEFAULT_CONSTANTS = { dialogBtnSpace: 30, dialogBtnBaseSpace: 40 };
// Flash's autoSize wraps the words in a 2 px gutter each side
const AUTO_SIZE_GUTTER = 4;
const MOST_RECORDED = 100;

const measure = document.createElement("canvas").getContext("2d");

let page = null;
// The open box: { key, clip, state, content, field, text, chars, typing, writing, offset, range, bar, buttons }
let view = null;
// What was opened, pressed and moved, newest last, for checks
const log = [];

function note(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

function constant(name) {
  return data.actors?.constants?.[name] ?? DEFAULT_CONSTANTS[name];
}

function defOf(key) {
  return data.story?.npcs?.[key] ?? null;
}

function bySex(value) {
  if (value && typeof value === "object") {
    return story.player?.sex === "female" ? value.f : value.m;
  }
  return value;
}

// ---------- What the box says ----------

// The state of the person's table the story holds them in, or null when they are off or have no such state
function stateDef(key) {
  const state = npcs.stateOf(key);
  return defOf(key)?.states?.find((each) => each.n === state) ?? null;
}

// Where a state's quest stands: "none" with no quest, then "offer", "active" or "done"
function questStand(state) {
  if (!state?.quest) {
    return "none";
  }
  if (quests.isDone(state.quest)) {
    return "done";
  }
  return quests.isActive(state.quest) ? "active" : "offer";
}

// The words for a state: the offer, the in-progress text or the finished text, which falls back to the in-progress text
// when a state has none of its own
function wordsOf(state, stand) {
  if (!state) {
    return "";
  }
  if (stand === "done") {
    return state.contentComplete || state.contentActive || "";
  }
  return stand === "active" ? (state.contentActive ?? "") : (state.content ?? "");
}

// What the reward panel lists for a quest: its items by name, then "<NAME> WILL BECOME YOUR COMPANION" for a follower.
// A quest that brings the partner lists no items
function rewardLine(quest) {
  if (quest.partner) {
    return "";
  }
  const names = quest.rewards.map((ref) => lookup(ref)?.name ?? ref);
  if (quest.follower) {
    names.push(`${defOf(quest.owner)?.name ?? quest.owner} WILL BECOME YOUR COMPANION`);
  }
  return names.join(", ").toUpperCase();
}

// ---------- The person's face ----------

// The head and neck in the person's skin and hair colours and pieces (the head's frames from the NPC table)
function dressHead(clip, def) {
  const look = def.portrait;
  const head = clip.child("head");
  goto(head?.child("skin"), bySex(look.head));
  goto(head?.child("accessories"), look.headAccessory);
  goto(head?.child("accessoriesFace"), look.faceAccessory);
  goto(head?.child("hair"), bySex(look.hair));
  goto(head?.child("facialHair"), look.facialHair);
  const skin = colourOf(def.skinFromPlayer ? story.player?.look?.skin : def.dress.skinColour, null);
  const hair = colourOf(look.hairColour, null);
  if (skin !== null) {
    paintFlat(partAt(clip, "head.skin.skin"), skin);
    paintFlat(partAt(clip, "neck.skin"), skin);
  }
  if (hair !== null) {
    paintFlat(partAt(clip, "head.hair.base"), hair);
    paintFlat(partAt(clip, "head.facialHair.base"), hair);
  }
}

// ---------- Words and buttons ----------

// How tall a field's words are in its own font and width, however short the field is
function heightOf(def, text) {
  const [left, top, right] = def.bounds;
  const probe = new TextField({ ...def, html: null, bounds: [left, top, right, top + PROBE_HEIGHT] });
  probe.text = text;
  const height = probe.contentHeight;
  probe.destroy();
  return height;
}

// A field of the same look as the art's, as tall as the words need, standing where the art's did (Flash's autoSize
// grows a field downward). The art's own field is hidden
function tallField(content, base, text) {
  const [left, top, right] = base.def.bounds;
  const height = Math.max(PROBE_HEIGHT, Math.ceil(heightOf(base.def, text)));
  const field = new TextField({ ...base.def, html: null, bounds: [left, top, right, top + height] });
  field.position.copyFrom(base.position);
  field.text = "";
  content.addChildAt(field, content.getChildIndex(base));
  base.visible = false;
  return field;
}

// A button's words as Flash's autoSize "left" measures them
function textWidth(field, text) {
  const def = field.def;
  measure.font = `${def.bold ? "bold " : ""}${def.size}px ${def.font}`;
  return measure.measureText(text).width + AUTO_SIZE_GUTTER;
}

// The button's words in a field as wide as they are (autoSize "left" grows a field to the right), still carrying the
// glow the art put on it
function widenLabel(field, words, wide) {
  const [left, top, , bottom] = field.baseBounds ??= field.def.bounds;
  field.def = { ...field.def, html: null, bounds: [left, top, left + wide, bottom] };
  field.box.width = wide;
  field.width0 = field.box.width;
  field.redraw();
  field.shown = null;
  field.text = words;
}

// A button shows its words, and its face and its base stretch to fit them (sizeButtons)
function dressButton(button, words) {
  const label = button.child("btnText");
  const wide = textWidth(label, words);
  widenLabel(label, words, wide);
  for (const [name, space] of [
    ["btnTop", constant("dialogBtnSpace")],
    ["btnBottom", constant("dialogBtnBaseSpace")],
  ]) {
    const part = button.child(name);
    takeOver(part);
    part.width = wide + space;
  }
}

// Which of the three buttons show and what each says and does. button1 and button2 are the offer's pair and button3 is
// the lone one
function setButtons(clip, spec) {
  const [first, second, lone] = ["button1", "button2", "button3"].map((name) => clip.child(name));
  const pair = Boolean(spec.pair);
  first.visible = pair;
  second.visible = pair;
  lone.visible = !pair;
  const shown = pair ? [first, second] : [lone];
  const buttons = pair ? spec.pair : [spec.lone];
  shown.forEach((button, i) => {
    dressButton(button, buttons[i].words.toUpperCase());
    button.setHandler("onPress", () => input.swallowPress());
    button.setHandler("onRelease", () => press(buttons[i]));
  });
  if (pair) {
    second.x = RIGHT_BUTTON_EDGE - second.width;
  }
  view.buttons = buttons;
}

// Every press moves the box to its next page and buttons or shuts it, so the second click of a double click lands on a
// button nobody has read yet: it presses nothing
function press(button) {
  note("press", { key: view?.key, words: button.words });
  button.act();
  input.shutByClick();
}

// ---------- What the buttons do ----------

// changeNPCState with no number: the next state, when the table has one
function advance(key) {
  const state = npcs.stateOf(key);
  if (typeof state === "number" && defOf(key).states.some((each) => each.n === state + 1)) {
    setNPCState(key, state + 1);
  }
}

// The offer: ACCEPT starts the quest and closes, DECLINE closes
function offerButtons(state) {
  return {
    pair: [
      {
        words: state.confirm,
        act() {
          startQuest(state.quest);
          closeDialog();
        },
      },
      { words: state.decline, act: closeDialog },
    ],
  };
}

// In progress: the "met" button finishes the quest when it can be (the box then shows the finished text), the "not met"
// button closes
function activeButtons(state, key) {
  if (quests.fetchReady(state.quest)) {
    return {
      lone: {
        words: state.reqMet,
        act() {
          quests.complete(state.quest, key);
        },
      },
    };
  }
  return { lone: { words: state.reqNotMet, act: closeDialog } };
}

// Finished: the finished button moves the person on and closes
function doneButtons(state, key) {
  return {
    lone: {
      words: state.compResp,
      act() {
        advance(key);
        closeDialog();
      },
    },
  };
}

// No quest: OK, which follows the state's "next" without closing, and closes when there is none
function plainButtons(key) {
  return {
    lone: {
      words: "OK",
      act() {
        const next = stateDef(key)?.next;
        if (next === undefined || next === null) {
          closeDialog();
        } else {
          setNPCState(key, next);
        }
      },
    },
  };
}

function buttonsFor(key, state, stand) {
  if (stand === "offer") {
    return offerButtons(state);
  }
  if (stand === "active") {
    return activeButtons(state, key);
  }
  return stand === "done" ? doneButtons(state, key) : plainButtons(key);
}

// ---------- Typing ----------

function stopWriting() {
  if (view?.writing) {
    view.writing = false;
    sound.stopLoop(WRITING);
  }
}

// One step of the typewriter: 4 more letters, until the words are all there (displayDialog)
function type() {
  if (!view?.typing) {
    return;
  }
  if (!view.writing) {
    view.writing = true;
    sound.loop("sound_writing", WRITING);
  }
  view.chars = Math.min(view.text.length, view.chars + CHARS_PER_STEP);
  view.field.text = view.text.slice(0, view.chars);
  if (view.chars >= view.text.length) {
    view.typing = false;
    stopWriting();
  }
}

// ---------- Scrolling ----------

function placeBar() {
  const { bar, range, offset } = view;
  bar.visible = range > 0;
  if (range > 0) {
    bar.y = BAR_TOP + (offset / range) * (BAR_BOTTOM - BAR_TOP);
  }
}

// The words move up by offset, as far as they go
function scrollTo(offset) {
  view.offset = Math.min(view.range, Math.max(0, offset));
  view.content.y = -view.offset;
  placeBar();
}

// A finger drags the words up and down; the thumb is dragged along its bar
function followBar() {
  const { bar, range } = view;
  const share = (bar.y - BAR_TOP) / (BAR_BOTTOM - BAR_TOP);
  view.offset = Math.min(range, Math.max(0, share * range));
  view.content.y = -view.offset;
}

function swipe() {
  const touch = view.touch;
  const at = view.content.parent.toLocal(page.lib.pointer).y;
  scrollTo(touch.from - (at - touch.y));
}

function stepScroll() {
  if (!view || view.range <= 0) {
    return;
  }
  if (view.dragging) {
    followBar();
  } else if (view.touch) {
    swipe();
  } else if (input.wheel) {
    scrollTo(view.offset + wheelStep());
  }
}

// The bar's thumb takes presses; a finger dragging the words scrolls them
function wireScroll(clip) {
  const bar = view.bar;
  bar.setHandler("onPress", () => {
    view.dragging = true;
    bar.startDrag(false, [bar.x, BAR_TOP, bar.x, BAR_BOTTOM]);
  });
  const drop = () => {
    if (view) {
      view.dragging = false;
    }
    bar.stopDrag();
  };
  bar.setHandler("onRelease", drop);
  bar.setHandler("onReleaseOutside", drop);
  const area = new Container();
  area.hitArea = new Rectangle(DRAG_AREA.x, DRAG_AREA.y, DRAG_AREA.width, DRAG_AREA.height);
  area.eventMode = "static";
  area.on("pointerdown", (event) => {
    if (finger(event) && view?.range > 0) {
      view.touch = { y: view.content.parent.toLocal(event.global).y, from: view.offset };
    }
  });
  const lift = () => {
    if (view) {
      view.touch = null;
    }
  };
  area.on("pointerup", lift);
  area.on("pointerupoutside", lift);
  area.on("pointercancel", lift);
  clip.addChild(area);
}

// ---------- Building the box ----------

// The box beside the person: on the left when they stand to the right of the middle, on the right otherwise
function placeBox(clip, key) {
  const person = npcs.npc(key);
  const at = person?.clip ? page.root.toLocal(person.clip.toGlobal({ x: 0, y: 0 })).x : 0;
  clip.x = at > SIDE_SPLIT ? LEFT_X : page.width - RIGHT_MARGIN;
  clip.y = BOX_Y;
}

// The words, the buttons, the reward panel and the bar for the person's state now. Typing starts from nothing. A person
// who switched off while the box was up (Hank, who joins as the companion the moment his quest is done) keeps the
// state the box was showing, so it shows that state's finished text and not an empty box (Q56, as U35)
function render() {
  const { key, clip, content } = view;
  const def = defOf(key);
  const state = stateDef(key) ?? view.state ?? null;
  view.state = state;
  const stand = questStand(state);
  const text = fillText(wordsOf(state, stand));
  setText(clip.child("name"), fillText(def.fullName).toUpperCase());
  setText(clip.child("title"), fillText(def.title).toUpperCase());
  dressHead(clip, def);
  view.field?.destroy();
  view.field = tallField(content, view.base, text);
  Object.assign(view, { text, chars: 0, typing: text.length > 0 });
  stopWriting();
  const invisible = content.child("invisTxt");
  setText(invisible, text);
  invisible.visible = false;
  const reward = rewardPanel(content, state, invisible.contentHeight);
  const height = reward ? reward.y + reward.getLocalBounds().height : invisible.contentHeight;
  view.range = Math.max(0, height - VIEW_HEIGHT);
  scrollTo(0);
  setButtons(clip, state ? buttonsFor(key, state, stand) : { lone: { words: "OK", act: closeDialog } });
  note("render", { key, state: npcs.stateOf(key), stand, words: text.length });
}

// The panel of rewards under the words: the items, the companion and the XP of the state's quest. Returns the panel
// when it shows
function rewardPanel(content, state, textHeight) {
  const panel = content.child("rewardPanel");
  const quest = state?.quest ? data.story.quests[state.quest] : null;
  const shown = Boolean(quest) && (quest.rewards.length > 0 || quest.follower || quest.partner || quest.xp > 0);
  panel.visible = shown;
  setText(panel.child("rewardText"), shown ? rewardLine(quest) : "");
  setText(panel.child("XPrewardText"), shown && quest.xp > 0 ? `${quest.xp} XP` : "");
  panel.y = textHeight + REWARD_GAP;
  return shown ? panel : null;
}

function build(clip, key) {
  const content = clip.child("dialogContent");
  view = { key, clip };
  view.content = content;
  view.base = content.child("txt");
  view.bar = clip.child("scrollBar");
  view.offset = 0;
  view.range = 0;
  hud.hidePlay(true);
  placeBox(clip, key);
  wireScroll(clip);
  render();
  sound.play("sound_openInterface");
}

// Closing saves the people's and the quests' states (closeDialog F4:19792)
function finish() {
  stopWriting();
  const key = view?.key;
  view = null;
  hud.hidePlay(false);
  sound.play("sound_closeInterface");
  savePoint("dialog");
  note("close", { key });
}

function closeDialog() {
  closePanel();
}

// ---------- Opening ----------

// Talks to a person: the talk quests that name them finish first, then the box opens at their state. Returns whether a
// box opened
export function openDialog(key) {
  if (!defOf(key)) {
    return false;
  }
  quests.check("talk", key);
  openPanel(PANEL, { art: "dialog", setup: (clip) => build(clip, key), close: finish });
  note("open", { key, state: npcs.stateOf(key) });
  return true;
}

// A quest finished at this person's box (the "met" button): the box shows the quest's finished text, before the quest's
// own changes to the people's states land (completeQuest F4:3067)
function questFinished() {
  if (view?.clip) {
    render();
  }
}

export const dialog = {
  open: openDialog,
  close: closeDialog,
  advance,
  get isOpen() {
    return panelOpen(PANEL);
  },
  log,
};

export function initDialog(owner) {
  page = owner;
  npcs.hooks.dialog = openDialog;
  quests.hooks.finished = questFinished;
  world.stage("interface", type);
  world.stage("interface", stepScroll);
  world.onReset(() => {
    stopWriting();
    view = null;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const dialogDebug = {
  // Talks to a person wherever the player stands, and says what the box shows
  dialogOpen(key) {
    openDialog(key);
    return dialogDebug.dialogState();
  },

  // What the open box shows; null when none is open
  dialogState() {
    if (!view?.clip) {
      return null;
    }
    const { clip, content, key } = view;
    const shown = (name) => clip.child(name);
    return {
      key,
      state: npcs.stateOf(key),
      name: shown("name").text,
      title: shown("title").text,
      typed: view.field.text,
      full: view.text,
      typing: view.typing,
      buttons: ["button1", "button2", "button3"]
        .filter((name) => shown(name).visible)
        .map((name) => {
          const button = shown(name);
          return [name, button.child("btnText").text, Math.round(button.x), Math.round(button.width)];
        }),
      reward: content.child("rewardPanel").visible
        ? {
            items: content.child("rewardPanel").child("rewardText").text,
            xp: content.child("rewardPanel").child("XPrewardText").text,
            y: Math.round(content.child("rewardPanel").y),
          }
        : null,
      scroll: { bar: view.bar.visible, offset: view.offset, range: view.range, touching: view.touch ?? false },
      x: clip.x,
      paused: world.paused,
    };
  },

  // Types the rest of the words at once
  dialogFinish() {
    while (view?.typing) {
      type();
    }
    return dialogDebug.dialogState();
  },

  // A press and release on button 1, 2 or 3 (the box acts and may close)
  dialogPress(which) {
    const button = view.buttons[which === 3 ? 0 : which - 1];
    press(button);
    return dialogDebug.dialogState();
  },

  // A finger's or the wheel's scroll to an offset
  dialogScroll(offset) {
    scrollTo(offset);
    return dialogDebug.dialogState();
  },

  dialogLog() {
    return log.map((each) => ({ ...each }));
  },
};
