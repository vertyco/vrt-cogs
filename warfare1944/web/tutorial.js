// The tutorial: sprite 1141 ("bootCamp"), a part of the menu clip that plays a 1,989-frame narrated film with its
// captions in the timeline and a SKIP button, ported from loadTutorial and hideTutorial (F6:578-606). The narration is
// the sprite's sound stream, which Flash keeps the playhead in step with by dropping frames. Here the narration's clock
// sets the frame: a page that falls behind jumps ahead to where the voice is, and one that runs ahead waits for it.
//
// It is offered at the first New Campaign (and then goes on to side select) and from the Instructions page's WATCH
// TUTORIAL (and then goes back there); page.fromInstructions says which, as the original's fromInstructions does.
import * as menus from "./menus.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const PART = "bootCamp";
const SPRITE = 1141;
// Frame 1 stops and waits; the film and its sound stream start on frame 2. Frame 1989 hides the tutorial
const FIRST_FRAME = 2;
const LAST_FRAME = 1989;
const FPS = 30;
// The SKIP button's placement (sprite 1101 at depth 22)
const SKIP_DEPTH = 22;
const EASE = "easeOutSine";
// How long the film waits on frame 2 for the narration to load before it plays without it
const LOAD_WAIT_MS = 4000;

let page = null;
// The film playing now: its clip, when it started on this page's clock (for a silent film), and whether it ends
const run = { clip: null, playing: false, startedAt: 0, ending: false };

export function bindPage(owner) {
  page = owner;
}

function menuClip() {
  return page.root.children.find((child) => child.label === "menu" && !child.destroyed) ?? null;
}

// loadTutorial (F6:578-593): the menu music stops, the main menu fades out, and the film fades in on its first frame
// and starts once it is in. Instructions, when the film comes from there, stays under it
async function enter() {
  const menu = menuClip() ?? (await menus.loadMenu("tutorial"));
  sound.stopMenuMusic(0);
  sound.preload([sound.NARRATION]);
  menus.swap(menu, menus.PARTS.main, null);
  const clip = menu.child(PART);
  tweens.stopTween(clip);
  clip.gotoAndStop(1);
  clip.alpha = 0;
  clip.visible = true;
  Object.assign(run, { clip, playing: false, ending: false });
  setupSkip(clip);
  tweens.alphaTo(clip, 100, 0.6, EASE, 0.8, () => begin(clip));
}

// The SKIP button's clip action (sprite 1141, placement 1101): the film stops and the tutorial hides
function setupSkip(clip) {
  const skip = clip.at(SKIP_DEPTH);
  skip.child("buttonText").text = "SKIP";
  skip.setHandler("onRelease", () => {
    clip.stop();
    hide();
  });
}

// gotoAndPlay(2) once the film is in, with the narration starting on the same frame
function begin(clip) {
  if (run.clip !== clip || page.screen !== "tutorial" || run.ending) {
    return;
  }
  clip.gotoAndStop(FIRST_FRAME);
  sound.narration(true);
  run.playing = true;
  run.startedAt = performance.now();
}

// The frame the film should show now, or null while it waits for the narration to load. With no narration (sound
// effects off, or a file that couldn't load or took too long) the page's own clock sets it
function targetFrame() {
  let clock = sound.narrationClock();
  if (clock?.loading) {
    if (performance.now() - run.startedAt < LOAD_WAIT_MS) {
      return null;
    }
    // The voice came too late to match the film, so the film plays silent from where it waited
    sound.narration(false);
    run.startedAt = performance.now();
    clock = null;
  }
  const seconds = clock ? clock.seconds : (performance.now() - run.startedAt) / 1000;
  return Math.min(LAST_FRAME, FIRST_FRAME + Math.max(0, Math.floor(seconds * FPS)));
}

// Each step of the page's clock the playhead moves to the narration's frame. One frame on is a normal step; more is a
// page that fell behind, which skips the frames between as the original's stream does. Reaching frame 1989 runs its
// script, which hides the tutorial
function step() {
  if (!run.playing || run.clip?.destroyed) {
    return;
  }
  const frame = targetFrame();
  if (frame !== null && frame > run.clip.frame) {
    run.clip.gotoAndStop(frame);
  }
}

// hideTutorial (F6:594-606): the film fades out and the player goes on to side select, or back to Instructions
function hide() {
  if (run.ending || !run.clip) {
    return;
  }
  run.ending = true;
  run.playing = false;
  sound.narration(false);
  tweens.alphaTo(run.clip, 0, 0.6, EASE, 0, (clip) => {
    clip.visible = false;
  });
  page.show(page.fromInstructions ? "instructions" : "select");
}

// Leaving any other way (a press that reached the menu under the film) stops the film and the narration at once
function leave(owner, next) {
  sound.narration(false);
  if (!run.ending && run.clip && !run.clip.destroyed) {
    tweens.stopTween(run.clip);
    run.clip.stop();
    run.clip.visible = false;
    if (page.fromInstructions && next !== "instructions") {
      const instructions = menuClip()?.child(menus.PARTS.instructions);
      if (instructions) {
        instructions.visible = false;
      }
    }
  }
  Object.assign(run, { clip: null, playing: false, ending: false });
  page.fromInstructions = false;
  menus.keepMenu(next);
}

// Where the film is, for checking from outside: the playhead and the narration's clock
export function state() {
  const clock = sound.narrationClock();
  return { frame: run.clip?.frame ?? null, playing: run.playing, seconds: clock?.seconds ?? null };
}

export const screens = {
  tutorial: {
    scripts: {
      [SPRITE]: (owner, clip, frame) => {
        if (frame === LAST_FRAME) {
          clip.stop();
          hide();
        }
      },
    },
    enter,
    leave,
    step,
  },
};
