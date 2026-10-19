// The intro movie (sprite intro 7033, 1,063 frames = 35.4 s; launchGame F4:25255). Character creation hands over to it
// once the new story is saved. The art plays itself: its frame-timed sounds (6941 from frame 2 with its fade, 6942 at
// 74, 6947 at 177 and 317, 6992 at 490, 7019 at 591, 7020 at 788) start through the sound system, its SKIP button
// jumps to the last frame (load handler on part 71), and the three clips of random start frames (6871, 6898, 6859)
// pick theirs when they are placed. The last frame runs the "launchgame" hook, and that, or SKIP, starts the world on
// the crash street in Pinedale at 12:00 AM; the street's trigger 1 (quest 900 and cutscene 10) fires from its zone as
// the player stands in it. The Armor Games and Con Artist logo intro that came before this one is not in the game (U8).
import { input } from "./input.js";
import { sound } from "./sound.js";
import { START_ROOM, START_TIME, START_X, world } from "./world.js";

const CLIP = "intro";
// The sounds the movie starts on its own timeline, decoded ahead so the first one isn't late
const SOUNDS = ["6941", "6942", "6947", "6992", "7019", "7020"];
const MOST_RECORDED = 50;

let page = null;
let depth = 0;
// The movie on screen: { clip, ended, starting }
let view = null;
// What happened, newest last, for checks
const log = [];

function record(kind, extra = {}) {
  log.push({ kind, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// The movie's last frame, or SKIP: the movie is over, and the next step starts the world
function finish() {
  if (!view || view.ended) {
    return;
  }
  view.ended = true;
  record("end", { frame: view.clip.frame });
}

// launchGame: the movie goes, then the world starts on the crash street
async function begin() {
  view.starting = true;
  record("launch");
  await page.show("world");
  input.own(page.screen);
  world.time = START_TIME;
  world.start();
  await world.enter(START_ROOM, START_X);
}

function leave() {
  if (!view) {
    return;
  }
  view = null;
  sound.stopAll();
  page.detach(CLIP);
  record("close");
}

export const INTRO_HOOKS = {
  launchgame() {
    finish();
    return true;
  },
};

export const INTRO_SCREEN = {
  async enter() {
    sound.stopMusic();
    sound.preload(SOUNDS);
    await page.lib.need([page.lib.exported(CLIP)]);
    // A screen change that came while the art loaded wins
    if (page.screen !== CLIP) {
      return;
    }
    view = { clip: page.attach(CLIP, depth, CLIP), ended: false, starting: false };
    record("open");
  },
  leave,
  step() {
    if (view?.ended && !view.starting) {
      begin().catch((e) => console.error("Union City: the world couldn't start after the intro", e));
    }
  },
};

export function initIntro(owner, band) {
  page = owner;
  depth = band;
}

export const intro = {
  get active() {
    return view !== null;
  },
  log,
};

// The movie's SKIP button, the one part of it that takes a press (part 71, an unnamed clip)
function skipButton() {
  return view.clip.children.find((each) => each.handlers?.onRelease);
}

// Helpers for page.py checks
export const introDebug = {
  // The movie's frame, whether it has ended and the latest log lines
  introState() {
    return {
      showing: view !== null,
      frame: view?.clip.frame ?? null,
      ended: view?.ended ?? null,
      starting: view?.starting ?? null,
      screen: page.screen,
      log: log.slice(-8),
    };
  },

  // Jumps the movie to a frame, as if that much time had gone by
  introGoto(frame) {
    view?.clip.gotoAndPlay(frame);
    return view?.clip.frame ?? null;
  },

  // Where the middle of the SKIP button's part inside the stage is on the window, for a click (its art runs past the
  // stage's right edge)
  introPoint() {
    const box = skipButton().getBounds();
    const canvas = page.app.canvas.getBoundingClientRect();
    const right = Math.min(box.x + box.width, page.app.screen.width);
    const ratio = canvas.width / page.app.screen.width;
    return {
      x: canvas.left + ((box.x + right) / 2) * ratio,
      y: canvas.top + (box.y + box.height / 2) * ratio,
    };
  },

  // Presses SKIP as a mouse would
  introSkip() {
    skipButton().handlers.onRelease({ pointerType: "mouse", button: 0 });
    return introDebug.introState();
  },
};
