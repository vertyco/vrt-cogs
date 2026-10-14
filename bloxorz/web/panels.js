// Bloxorz's pause panel and the number boxes on it and on the end screen. The pause panel is the original's
// DefineSprite_1179, placed on the stage's root when play starts and kept on top; the HUD's Menu button plays it open.
// It does not pause anything: rolls and the clock go on with it open (the original never set `pauseness` to true).
// Its stats box is DefineSprite_1178, and the end screen's is DefineSprite_196 (placed by the menu's timeline), both
// drawn from the counters the bot sent. The clock shows real seconds as h.mm.ss, where the original's showed 1.2 times
// that.
import { toggleSound, wireButtons } from "./menu.js";

const PAUSE = 1179;
const PAUSE_STATS = 1178;
const END_STATS = 196;
// The root's frame and depth that place the panel (frame_50/PlaceObject2_1179_99)
const PLAY_FRAME = 50;
const PAUSE_DEPTH = 99;
// Quit to Menu (B1173) plays the panel out from here, and its last frame (S1179/f38) quits
const QUIT_FRAME = 26;
// The digit pictures: a digit d is frame d + 1, and 12 is blank
const BLANK_FRAME = 12;
const HOURS_MOST = 99;
const SECONDS_IN_HOUR = 3600;
const SECONDS_IN_MINUTE = 60;
const TIME_DIGITS = ["digit1", "digit2", "digit3", "digit4", "digit5", "digit6"];
const FALLS_DIGITS = ["digitw", "digitx", "digity", "digitz"];
const MOVES_DIGITS = ["digita", "digitb", "digitc", "digitd", "digite", "digitf"];
const STAGE_DIGITS = ["digita", "digitb"];

// ---------- Number boxes ----------

function digit(clip, name, value) {
  clip.child(name)?.gotoAndStop(value === null ? BLANK_FRAME : value + 1);
}

// A whole number in these digits, most significant first, with blanks before the first one that isn't zero. The
// last digit always shows, so zero reads 0
function count(clip, names, value) {
  const text = String(Math.max(0, Math.floor(value))).padStart(names.length, "0").slice(-names.length);
  let leading = true;
  names.forEach((name, index) => {
    leading = leading && text[index] === "0" && index < names.length - 1;
    digit(clip, name, leading ? null : Number(text[index]));
  });
}

// Seconds as h.mm.ss in digit1 to digit6 (the dots are in the picture); the hours' tens digit is blank at zero
function clock(clip, seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.min(Math.floor(whole / SECONDS_IN_HOUR), HOURS_MOST);
  const minutes = Math.floor(whole / SECONDS_IN_MINUTE) % SECONDS_IN_MINUTE;
  const rest = whole % SECONDS_IN_MINUTE;
  const tens = Math.floor(hours / 10);
  const values = [
    tens === 0 ? null : tens,
    hours % 10,
    Math.floor(minutes / 10),
    minutes % 10,
    Math.floor(rest / 10),
    rest % 10,
  ];
  TIME_DIGITS.forEach((name, index) => digit(clip, name, values[index]));
}

// S1178/f1: the time so far, this stage's number and the failed attempts. Runs every tick the panel is placed
function pauseStats(page, clip) {
  clock(clip, page.seconds + (performance.now() - page.secondsAt) / 1000);
  const stage = page.stageMsg?.n ?? 1;
  STAGE_DIGITS.forEach((name, index) => digit(clip, name, index === 0 ? Math.floor(stage / 10) : stage % 10));
  count(clip, FALLS_DIGITS, page.falls);
}

// S196/f2: the run's totals from the bot's `done`
function endStats(page, clip) {
  const done = page.done;
  if (!done) {
    return;
  }
  clock(clip, done.seconds);
  count(clip, FALLS_DIGITS, done.falls);
  count(clip, MOVES_DIGITS, done.moves);
}

// ---------- The pause panel ----------

// S1179/f38: Quit to Menu. The run goes to the bot, the pieces leave, and the root plays on into the scatter, which
// ends at the menu. A win already under way is left alone: the bot has moved on to the next stage
function quit(page, clip) {
  const root = page.board.root;
  clip.removeMovieClip();
  if (!root || root.get("winning")) {
    return;
  }
  page.send({ quit: true });
  page.pieces.quit();
  root.set("exiting", true);
  page.board.restart();
}

// Called as the root reaches its play frame: the panel goes on top, closed, with its three buttons wired
function place(page) {
  const panel = page.board.place(PLAY_FRAME, PAUSE_DEPTH, page.board.depths.menuness);
  wireButtons(page, panel, {
    // B1169 Return to Game: plays the panel out
    1169: (clip) => clip.play(),
    // B150 Toggle Sound
    150: () => toggleSound(page),
    // B1173 Quit to Menu
    1173: (clip) => clip.gotoAndPlay(QUIT_FRAME),
  });
  return panel;
}

// The HUD's Menu button (B342, in sky.menu) plays the panel open
function openPause(page) {
  page.board.root?.child("menuness")?.play();
}

// The run is over: the root goes to the menu's end screen (R53:21-28), which reads the totals from `done`
function showEnd(page, totals) {
  page.done = totals;
  page.skiptoend = true;
  page.go("menu");
}

// The panels' frame scripts and what the board calls: place when play starts, openPause from the HUD, showEnd when
// the board has unloaded after the run's last stage
export function setupPanels(page) {
  page.panels = {
    place: () => place(page),
    openPause: () => openPause(page),
    showEnd: (totals) => showEnd(page, totals),
  };
  return {
    scripts: [
      [PAUSE, (clip) => quit(page, clip)],
      [PAUSE_STATS, (clip) => pauseStats(page, clip)],
      [END_STATS, (clip) => endStats(page, clip)],
    ],
  };
}
