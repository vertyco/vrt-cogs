// The world's own dialog boxes (showDialogBox F4:20000): "YOU CANNOT SLEEP HERE", "COMPANION DOWN!" (F4:20208) and
// "NEW COMPANION?" (F4:20221). The rules that raise them leave them waiting, on interact.dialog and on
// companions.question; this draws the one waiting and sends its button to the rule's answer. The box hides the play
// parts of the HUD while it is up and the HUD comes back when it closes (hideHUD, closeDialogBox F4:20045). It holds
// the world still while it is up: NEW COMPANION? opens over the person's chat, and Esc can shut the chat under it.

import { answerReplace, companions } from "./companions.js";
import { hud, setText } from "./hud.js";
import { input } from "./input.js";
import { answerDialog, interact } from "./interact.js";
import { fadeInBox, fadeOutBox, finger, setAlpha } from "./panels.js";
import { sound } from "./sound.js";
import { world } from "./world.js";

const CLIP = "worldDialog";
// The box sits mid-stage over a black-out at 60, and fades in over 0.6 s and out over 0.1 s (F4:20005, F4:20041)
const DIALOG = { x: 380, y: 200, fade: 0.6, shade: 0.6, out: 0.1 };
const PAUSE = "box";

let page = null;
let depth = 0;
// The box up now and the question it shows
let box = null;
let showing = null;

function close() {
  const old = box;
  box = null;
  showing = null;
  if (!old) {
    return;
  }
  hud.hidePlay(false);
  world.resume(PAUSE);
  fadeOutBox(old, DIALOG.out);
}

function button(clip, name, words, action) {
  const each = clip.child(name);
  each.visible = true;
  setText(each.child("buttonText"), words);
  each.setHandler("onPress", () => {
    input.swallowPress();
    sound.play("sound_interfaceClick");
  });
  each.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  each.setHandler("onRelease", () => {
    input.swallowPress();
    action();
  });
}

// "NEW COMPANION?" answers YES or NO (button1, button2); the others have one OK (button3)
function buttonsOf(question) {
  if (question.kind === "replace") {
    return [
      ["button1", question.yes, () => answerReplace(true)],
      ["button2", question.no, () => answerReplace(false)],
    ];
  }
  return [["button3", question.ok, answerDialog]];
}

function open(question) {
  const clip = page.attach("dialogBox", depth, CLIP);
  clip.position.set(DIALOG.x, DIALOG.y);
  box = clip;
  showing = question;
  world.pause(PAUSE);
  hud.hidePlay(true);
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    clip.child(name).visible = false;
  }
  const shade = clip.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(clip.child("textBoxes").child("headingText"), question.heading);
  setText(clip.child("textBoxes").child("bodyText"), question.body);
  for (const [name, words, action] of buttonsOf(question)) {
    button(clip, name, words, action);
  }
  fadeInBox(clip, DIALOG.fade);
}

// Each frame: the box follows whichever question is waiting, and goes once it has been answered
function step() {
  const waiting = interact.dialog ?? companions.question ?? null;
  if (waiting === showing) {
    return;
  }
  close();
  if (waiting) {
    open(waiting);
  }
}

export function initBoxes(owner, band) {
  page = owner;
  depth = band;
  page.steppers.push(step);
}

// Helpers for page.py checks
export const boxesDebug = {
  // The box up now: its kind, heading and the words on its buttons
  boxState() {
    if (!box || !showing) {
      return null;
    }
    return {
      kind: showing.kind,
      heading: showing.heading,
      buttons: buttonsOf(showing).map(([name, words]) => [name, words]),
    };
  },
};
