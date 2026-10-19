// Achievements (checkAch F4:268, unlockAchievement F4:366, giveAchAwards F4:478, openAchievements F4:20600,
// achButtonSetup F4:20683, the table F4:25501-26013): 54 counters per save slot. A system adds to a counter by its key
// (achieve.add("killZombie"), achieve.add("cash", 40)); every achievement that reads that key moves up. Reaching the
// count unlocks it: it is marked complete and saved at once (Q25), a panel slides down with "+N XP" for 5 seconds and
// the XP is paid. A step of progress on the way shows a small box (the "Achievement updates" setting). At 25, 50 and
// 75 percent unlocked a prize goes to the stash, with a dialog.
//
// The systems that count already hand their counters to listeners; initAchieve wires each of them. The counters that
// belong to systems built later are added by those systems: "quest900" and its kin plus "finishQuest" (the quest
// engine). Sleeping adds "sleep", an hour at a time.
//
// The page (X, or the dock's button) lists all 54 sorted by XP, six to a column and three columns to a page.
// story.achievements: { counts: { ach1: n }, done: { ach1: true }, prizes: [false, false, false] }.
import { data } from "./data.js";
import { hud, setText, tween } from "./hud.js";
import { input } from "./input.js";
import { onCombat } from "./combat.js";
import { onCompanionCount } from "./companions.js";
import { onHumanCount } from "./humans.js";
import { onInventoryCount } from "./inventory.js";
import { onLockCount } from "./locks.js";
import { onNoteCount } from "./notes.js";
import {
  canOpenPanel,
  closePanel,
  fadeInBox,
  fadeOutBox,
  finger,
  openPanel,
  panelOpen,
  setAlpha,
  tint,
} from "./panels.js";
import { addXP, onLevelUp, onSprintDone, player, refuseOpen } from "./player.js";
import { savePoint } from "./save.js";
import { onSearchCount } from "./search.js";
import { onSheetCount } from "./sheet.js";
import { onShopCount } from "./shop.js";
import { onSleepCount } from "./sleep.js";
import { sound } from "./sound.js";
import { addToStorage, onStorageCount } from "./storage.js";
import { story } from "./story.js";
import { world } from "./world.js";
import { onUnawareKill, onZombieCount } from "./zombies.js";

const PANEL = "achievements";
const PRIZE_PAUSE = "achievement prize";
// Seconds an unlock panel stays up before it fades (achievementShowTime F4:25492)
const SHOW_TIME = 5;
// A progress box stays this much longer, as 1.25 times the unlock panel's time
const PROGRESS_TIME = SHOW_TIME * 1.25;
const PROGRESS_AT = { x: 580, y: 271 };
// The unlock panels sit above the open panels and below the dialogs; the progress box over them
const PANELS_BELOW_DIALOGS = 500;
const PROGRESS_ABOVE_PANELS = 60;
const MOST_UNLOCK_PANELS = 50;
// The first panel's y, and the gap each one after it is pushed down by its own height less this (F4:398-402)
const PANEL_Y = 25;
const PANEL_STACK_TRIM = 15;
// The page: six panels to a column (the original's achMaxRows 7 counts the wrapped one), three columns to a page, and
// one page's width for the list to slide by
const PER_COLUMN = 6;
const COLUMNS_PER_PAGE = 3;
const PAGE_SCROLL = 709;
const COLUMN_GAP = 7;
const ROW_GAP = 2;
const LOCKED_SHADE = 0.3;
const STAR_OFF = 0x333333;
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
const PRIZE_HEADING = "ACHIEVEMENT REWARD";
const PRIZE_BODIES = [
  "\rYOU GOT THE\rBIOHAZARD OUTFIT\rCHECK YOUR STORAGE.",
  "\rYOU GOT THE\rBATTLE AXE\rCHECK YOUR STORAGE.",
  "\rYOU GOT THE\rM82 SNIPER RIFLE\rCHECK YOUR STORAGE.",
];
const MOST_RECORDED = 100;

let page = null;
let depth = 0;
// The page open now: { clip, list, columns, pages, at, size: { w, h }, rows }
let view = null;
let unlockSerial = 0;
let unlockShowing = 0;
// The progress box on screen, or null
let progressBox = null;
// The prize dialog on screen, and the prizes waiting behind it
let dialog = null;
let dialogHidesPlay = false;
let waiting = [];
// What was counted, unlocked and handed out, newest last, for checks
const log = [];

function note(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- The table ----------

function defs() {
  return Object.values(data.story.achievements);
}

function isDone(def) {
  return story.achievements.done[def.key] === true;
}

function countOf(def) {
  return isDone(def) ? def.count : (story.achievements.counts[def.key] ?? 0);
}

function doneCount() {
  return defs().filter(isDone).length;
}

// How much is unlocked, rounded up (giveAchAwards F4:464)
export function percentUnlocked() {
  return Math.ceil((doneCount() / defs().length) * 100);
}

function upper(text) {
  return String(text ?? "").toUpperCase();
}

// ---------- Counting ----------

// Adds to every achievement that reads this counter, and unlocks those that reach their count
export function add(type, amount = 1) {
  if (!story.player || !Number.isFinite(amount) || amount <= 0) {
    return;
  }
  for (const def of defs()) {
    if (def.type !== type || isDone(def)) {
      continue;
    }
    const before = countOf(def);
    const now = Math.min(def.count, before + amount);
    story.achievements.counts[def.key] = now;
    note("count", { key: def.key, type, count: now });
    if (now >= def.count) {
      unlock(def);
    } else {
      stepProgress(def, before, now);
    }
  }
}

// Sets the counter of every achievement that reads this type to a value (at most its count), unlocking those it reaches
export function set(type, value) {
  if (!story.player) {
    return;
  }
  for (const def of defs()) {
    if (def.type !== type || isDone(def)) {
      continue;
    }
    story.achievements.counts[def.key] = Math.min(def.count, Math.max(0, value));
    if (story.achievements.counts[def.key] >= def.count) {
      unlock(def);
    }
  }
}

// A step reached on the way to an achievement whose earlier tier is done: the small progress box (F4:312-336). The
// step is a whole number of the achievement's progress step, and secret ones show nothing
function stepProgress(def, before, now) {
  const wanted = story.settings.achUpdates === true && !def.secret && now > before;
  const open = !def.preReq || isDone(data.story.achievements[def.preReq]);
  const share = now / def.step;
  if (wanted && open && !progressBox && share === Math.round(share) && Math.round(share) > 0) {
    showProgress(def, now);
  }
}

// ---------- The progress box ----------

function showProgress(def, count) {
  const box = page.attach("achievementStatus", depth - PANELS_BELOW_DIALOGS + PROGRESS_ABOVE_PANELS, "achProgress");
  progressBox = box;
  box.position.set(PROGRESS_AT.x, PROGRESS_AT.y);
  box.eventMode = "none";
  setText(box.child("title"), upper(def.name));
  setText(box.child("desc"), upper(def.desc));
  setText(box.child("prog"), `${count} / ${def.count}`);
  box.child("progBar").scale.x = Math.round((count / def.count) * 100) / 100;
  box.alpha = 0;
  note("progress", { key: def.key, count });
  tween(box, "alpha", 100, 0.6);
  tween(box, "alpha", 0, 0.6, {
    delay: PROGRESS_TIME,
    done: () => {
      progressBox = null;
      box.destroy({ children: true });
    },
  });
}

// ---------- Unlocking ----------

// The achievement is complete from this moment and saved so (Q25), then the panel, the XP, the sound and the prizes
function unlock(def) {
  story.achievements.done[def.key] = true;
  story.achievements.counts[def.key] = def.count;
  note("unlock", { key: def.key, name: def.name, xp: def.xp });
  showUnlock(def);
  addXP(def.xp);
  sound.play("sound_achievementUnlocked");
  givePrizes();
  savePoint("achievement");
}

// The panel that slides down from the top for a few seconds. A second one showing at once sits lower
function showUnlock(def) {
  unlockSerial = (unlockSerial % MOST_UNLOCK_PANELS) + 1;
  unlockShowing += 1;
  const box = page.attach(
    "achievementPanel",
    depth - PANELS_BELOW_DIALOGS + unlockSerial,
    `achievementPanel${unlockSerial}`,
  );
  box.eventMode = "none";
  const { width, height } = box.getLocalBounds();
  box.x = (page.width - width) / 2;
  box.child("progBar").visible = false;
  const flasher = box.child("flasher");
  flasher.visible = true;
  flasher.alpha = 1;
  tween(flasher, "alpha", 0, 0.3, { ease: "easeOutSine", delay: 0.4 });
  setText(box.child("title"), upper(def.name));
  setText(box.child("desc"), upper(def.desc));
  setText(box.child("bonus"), `+${def.xp} XP`);
  box.y = unlockShowing > 1 ? height * unlockShowing - PANEL_STACK_TRIM : PANEL_Y;
  box.alpha = 0;
  tween(box, "alpha", 100, 0.2);
  tween(box, "alpha", 0, 0.3, {
    delay: SHOW_TIME,
    done: () => {
      unlockShowing = Math.max(0, unlockShowing - 1);
      box.destroy({ children: true });
    },
  });
}

// ---------- Prizes ----------

// Every prize the percent unlocked has reached and not yet been given goes to the stash, with the dialog (giveAchAwards
// F4:478). A prize is given once for the slot
function givePrizes() {
  const percent = percentUnlocked();
  data.items.prizes.forEach((prize, index) => {
    if (percent < prize.percent || story.achievements.prizes[index]) {
      return;
    }
    story.achievements.prizes[index] = true;
    for (const ref of prize.items) {
      addToStorage(ref, { prize: true });
    }
    note("prize", { index, percent: prize.percent, items: [...prize.items] });
    waiting.push(index);
  });
  nextPrize();
}

function closeDialog() {
  const box = dialog;
  if (!box) {
    return;
  }
  dialog = null;
  if (dialogHidesPlay) {
    hud.hidePlay(false);
  }
  fadeOutBox(box, DIALOG.out);
  world.resume(PRIZE_PAUSE);
  nextPrize();
}

function dialogButton(box, name, words, action) {
  const button = box.child(name);
  button.visible = true;
  setText(button.child("buttonText"), words);
  button.setHandler("onPress", () => {
    input.swallowPress();
    sound.play("sound_interfaceClick");
  });
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

// The next waiting prize's dialog: the world stops, and only OK goes on (dialog_achStar1-3 F4:20124)
function nextPrize() {
  if (dialog || waiting.length === 0) {
    return;
  }
  const index = waiting.shift();
  const box = page.attach("dialogBox", depth, "achievementDialog");
  box.position.set(DIALOG.x, DIALOG.y);
  dialog = box;
  world.pause(PRIZE_PAUSE);
  dialogHidesPlay = !panelOpen();
  if (dialogHidesPlay) {
    hud.hidePlay(true);
  }
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), PRIZE_HEADING);
  setText(box.child("textBoxes").child("bodyText"), PRIZE_BODIES[index]);
  dialogButton(box, "button3", "OK", closeDialog);
  fadeInBox(box, DIALOG.fade);
}

// ---------- The page ----------

// One achievement's panel on the page: its name, what it asks and what it pays, and how far along it is. A secret one
// hides what it asks until it is done, and three hide their names too
function dressRow(panel, def) {
  const done = isDone(def);
  const count = countOf(def);
  const secret = def.secret && !done;
  setText(panel.child("title"), secret && def.hiddenName ? "SECRET" : upper(def.name));
  const asks = secret ? "THIS IS A SECRET ACHIEVEMENT" : upper(def.desc);
  setText(panel.child("desc"), `${asks} - ${def.xp} XP`);
  setText(panel.child("bonus"), secret ? "" : `${count} / ${def.count}`);
  const bar = panel.child("progBar");
  bar.visible = true;
  bar.scale.x = Math.round((count / def.count) * 100) / 100;
  if (!done) {
    setAlpha(panel.child("blackOut"), LOCKED_SHADE);
    panel.child("achIcon").gotoAndStop("lock");
  }
}

// The panels in the original's order (smallest XP first), down a column of six and then along
function fillList(list) {
  const sorted = defs().sort((a, b) => a.sort - b.sort);
  let size = null;
  let rows = 0;
  let column = 0;
  const made = [];
  sorted.forEach((def, index) => {
    const panel = page.lib.makeExported("achievementPanel");
    list.attach(panel, `ach${index}`);
    size ??= panel.getLocalBounds();
    let y = Math.round((size.height + ROW_GAP) * rows);
    rows += 1;
    if (rows === PER_COLUMN + 1) {
      rows = 1;
      column += 1;
      y = 0;
    }
    panel.position.set(Math.round(column * (size.width + COLUMN_GAP)), y);
    dressRow(panel, def);
    made.push({ key: def.key, panel });
  });
  return { rows: made, columns: column + 1 };
}

function paintTop() {
  const clip = view.clip;
  const percent = percentUnlocked();
  setText(clip.child("unlocked"), `${percent}% UNLOCKED`);
  clip.child("achBar").scale.x = percent / 100;
  data.items.prizes.forEach((prize, index) => {
    tint(clip.child(`star${index + 1}`), percent >= prize.percent ? null : STAR_OFF);
  });
  setText(clip.child("pageNum"), `${view.at} / ${view.pages}`);
}

function turn(step) {
  const to = view.at + step;
  if (to < 1 || to > view.pages) {
    return;
  }
  view.at = to;
  view.list.x = view.listX - PAGE_SCROLL * (to - 1);
  sound.play(step > 0 ? "sound_interfacePage1" : "sound_interfacePage2");
  setText(view.clip.child("pageNum"), `${view.at} / ${view.pages}`);
}

function build(clip) {
  const list = clip.child("achList");
  hud.hidePlay(true);
  const { rows, columns } = fillList(list);
  view = {
    clip,
    list,
    listX: list.x,
    rows,
    columns,
    pages: Math.ceil(columns / COLUMNS_PER_PAGE),
    at: 1,
  };
  paintTop();
  givePrizes();
}

function finish() {
  view = null;
  hud.hidePlay(false);
  sound.play("sound_closeInterface");
  hud.refresh();
}

// Opens the achievements page (openAchievements F4:20600)
export function openAchievements() {
  openPanel(PANEL, { art: "int_achievementPage", setup: build, close: finish, overlay: false });
  sound.play("sound_openInterface");
}

function toggle() {
  if (panelOpen(PANEL)) {
    closePanel();
  } else if (canOpenPanel()) {
    openAchievements();
  }
}

// X. A zombie's hold refuses the opening with its alert
function keys() {
  if (!input.achievementsPressed) {
    return;
  }
  input.achievementsPressed = false;
  if (panelOpen(PANEL) || !canOpenPanel() || !refuseOpen()) {
    toggle();
  }
}

// The page's three buttons (achButtonSetup F4:20683): the arrows turn the page and the cross closes it
const BUTTONS = {
  nextBtn: () => turn(1),
  prevBtn: () => turn(-1),
  exitBtn: () => closePanel(),
};

export const ACHIEVE_LOAD_CALLS = {
  achButtonSetup(node, name) {
    node.setHandler?.("onPress", () => view && BUTTONS[name]?.());
  },
};

// ---------- Wiring ----------

function forward(key, amount = 1) {
  add(key, amount);
}

export const achieve = {
  add,
  set,
  open: openAchievements,
  close: closePanel,
  toggle,
  percent: percentUnlocked,
  isDone: (key) => story.achievements?.done[key] === true,
  get isOpen() {
    return panelOpen(PANEL);
  },
  get unlocked() {
    return doneCount();
  },
  log,
};

export function initAchieve(owner, band) {
  page = owner;
  depth = band;
  world.stage("interface", keys);
  hud.onOpen("achievements", toggle);
  onZombieCount(forward);
  onUnawareKill(() => add("killNoAlert"));
  onHumanCount(forward);
  onCompanionCount(forward);
  onInventoryCount(forward);
  onSearchCount(forward);
  onShopCount(forward);
  onStorageCount(forward);
  onSheetCount(forward);
  onLockCount(forward);
  onNoteCount(forward);
  onSleepCount(forward);
  onSprintDone((feet) => add("sprint", feet));
  onLevelUp(({ forgot }) => {
    if (forgot) {
      add("forgetLevel");
    }
  });
  onCombat("shove", (entry) => {
    if (entry.owner === player) {
      add("shove");
    }
  });
  world.onReset(() => {
    view = null;
    dialog?.destroy({ children: true });
    dialog = null;
    progressBox?.destroy({ children: true });
    progressBox = null;
    waiting = [];
    unlockShowing = 0;
    log.length = 0;
  });
}

// Helpers for page.py checks
export const achieveDebug = {
  // What the page shows now, in words and numbers; null when it is shut
  achState() {
    if (!view) {
      return null;
    }
    const clip = view.clip;
    return {
      paused: world.paused,
      unlocked: clip.child("unlocked").text,
      bar: clip.child("achBar").scale.x,
      page: clip.child("pageNum").text,
      stars: [1, 2, 3].map((n) => Boolean(!clip.child(`star${n}`).scriptColor)),
      listX: view.list.x,
      size: view.rows.length,
      columns: view.columns,
      rows: view.rows.map(({ key, panel }) => ({
        key,
        title: panel.child("title").text,
        desc: panel.child("desc").text,
        bonus: panel.child("bonus").text,
        x: panel.x,
        y: panel.y,
        locked: panel.child("blackOut").alpha > 0,
      })),
    };
  },

  // The unlock panels, the progress box and the prize dialog on screen now
  achShown() {
    const panels = page.root.children
      .filter((child) => child.label?.startsWith("achievementPanel"))
      .map((child) => ({
        x: child.x,
        y: child.y,
        alpha: child.alpha,
        title: child.child("title").text,
        desc: child.child("desc").text,
        bonus: child.child("bonus").text,
      }));
    const box = progressBox && {
      x: progressBox.x,
      y: progressBox.y,
      alpha: progressBox.alpha,
      title: progressBox.child("title").text,
      desc: progressBox.child("desc").text,
      prog: progressBox.child("prog").text,
      bar: progressBox.child("progBar").scale.x,
    };
    const words = (name) => dialog.child("textBoxes").child(name).text;
    return {
      panels,
      progress: box,
      dialog: dialog && { heading: words("headingText"), body: words("bodyText") },
      waiting: [...waiting],
      paused: world.paused,
      width: page.width,
    };
  },

  // The counts so far, by key, and who is done
  achCounts() {
    return {
      counts: { ...story.achievements.counts },
      done: Object.keys(story.achievements.done),
      prizes: [...story.achievements.prizes],
      percent: percentUnlocked(),
      storage: story.storage.filter((row) => row.prize).map((row) => row.ref),
    };
  },

  // Unlocks the first n achievements in the table at once (the caller then reads the prizes)
  achUnlockMany(n) {
    for (const def of defs().filter((each) => !isDone(each)).slice(0, n)) {
      unlock(def);
    }
    return achieveDebug.achCounts();
  },

  // The prize dialog's OK
  achOk() {
    dialog?.child("button3").handlers.onRelease?.();
    return achieveDebug.achShown();
  },

  // A press on the page's arrows or cross, by name
  achPress(name) {
    view.clip.child(name).handlers.onPress?.();
    return achieveDebug.achState();
  },

  achLog() {
    return log.map((each) => ({ ...each }));
  },
};
