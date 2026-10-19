// The ending and the credits (showEnding F4:2109-2235, endingCredits F4:1962, rollEndingCredits, compileCredits,
// openCredits; sprites ending 6904, menu_credits 6573). Reaching the monument pier (trigger 61) saves, stops the world
// and plays the ending movie: 816 frames (27.2 s) of a boat leaving across the water with the player, the partner and
// the follower (if one is along) sitting on it. The movie's last frame runs the "endingcredits" hook, which shows the
// ending panel: ROLL CREDITS and BACK TO MENU, over the skyline. ROLL CREDITS scrolls the credits; BACK TO MENU, or the
// credits ending or being closed, goes back to the main menu (Q41). The save stays at the end: there is no new game
// plus.
//
// The three on the boat are dressed as the original dresses them: the player as they are, the partner and the follower
// as their NPCs are, at 40 percent, in the full-body pose. The partner and the follower sit on a crate; "tinker", the
// label the original sends the player to, is not in the person's timeline, so the player stays on the first frame as
// the original does. The movie's own Facebook promo (6916) is not in the art; the panel is the skyline of the credits'
// backing, darkened, with the two buttons.
//
// The credits (menu_credits) scroll at 65 px a second from the bottom of the window up and off the top. The 42 names
// of the advertising list and the 37 of the notes list are text fields filled whole; the 751 beta testers sit two to a
// row, 24 px apart, and only the rows near the window have a clip, so the long list never holds 751 text pictures.
// showCredits(true) is the main menu's CREDITS: the same scroll without the ending's bars, and it leaves the menu where
// it is. It returns a promise that resolves when the credits close.
import { Container, Graphics } from "./vendor/pixi.min.mjs";
import { applyColor } from "./flash.js";
import { data } from "./data.js";
import { hud, setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { closePanel, finger } from "./panels.js";
import { quitToMenu } from "./pause.js";
import { goto, makeHuman, storyLook } from "./rig.js";
import { clearRoom } from "./rooms.js";
import { savePoint } from "./save.js";
import { sound } from "./sound.js";
import { dressOf } from "./companions.js";
import { story } from "./story.js";
import { triggers } from "./triggers.js";
import { world } from "./world.js";

const PAUSE = "ending";
const DEFAULT_SCALE = 40;
const DEFAULT_SPEED = 65;
// The pieces drawn here: the credits' skyline backing and border, and the dialog boxes' button
const BACKING = 6545;
const BORDER = 6128;
const BUTTON = 6204;
// Where the credits' skyline and border sit in a window centred on the stage, and how far the window reaches up
const BACKING_AT = { x: 0, y: -195.05 };
const BORDER_AT = { x: -379.65, y: -201.15 };
const WINDOW_TOP = 201;
const DARKEN = { mult: [156, 156, 156, 256] };
// The panel fades in over its first two seconds, ROLL CREDITS after 2.2 s and BACK TO MENU after 4.6 s (the movie's
// own timing, in frames 2-60, 67-100 and 139-152)
const PANEL_FADE = 2;
const BUTTON_FADE = 1;
const ROLL_AT = 2.2;
const BACK_AT = 4.6;
const BUTTON_Y = 330;
const ROLL_X = 320;
const BACK_X = 440;
const WORDS = { roll: "ROLL CREDITS", back: "BACK TO MENU" };
const MENU_TRACK = "music_menu";
const MENU_LOOPS = 5;
// The scrolling text starts 120 px below the window's middle, its beta list 120 px under the advertising list, and the
// beta names sit two to a row from 20 px down, 300 px apart
const TEXT_START = 120;
const LIST_GAP = 120;
const BETA_TOP = 20;
const BETA_ROW = 24;
const BETA_COLUMN = 300;
const BETA_REACH = 40;
const MOST_RECORDED = 50;
// The ending's actors: the placeholder each stands in on the boat, and its pose label ("tinker" is not a label)
const ACTORS = [
  { name: "player", pose: "tinker" },
  { name: "partner", pose: "sitCrate" },
  { name: "follower", pose: "sitCrate" },
];

let page = null;
let depth = 0;
// True from the moment the ending is asked for until the stage is cleared for it
let starting = false;
// What the story looked like as the ending began: { name: makeHuman options }
let looks = null;
// The ending on screen: { clip, panel, buttons }
let view = null;
// The credits on screen: { clip, text, beta, rows, bottom, ending, resolve }
let credits = null;
// What happened, newest last, for checks
const log = [];

function constant(name, fallback) {
  return data.actors?.constants?.[name] ?? fallback;
}

function record(kind, extra = {}) {
  log.push({ kind, frame: world.frame, ...extra });
  if (log.length > MOST_RECORDED) {
    log.shift();
  }
}

// ---------- The three on the boat ----------

// What each person on the boat looks like, taken while the story is still in the world: the player as dressed, the
// partner and the follower as their NPCs are. The follower is left out when no one is along
function captureLooks() {
  const found = { player: { ...storyLook(), weapon: "hands", stored: "hands" } };
  for (const [name, key] of [
    ["partner", story.player.partner ?? "Partner"],
    ["follower", story.player.follower],
  ]) {
    if (key) {
      const dress = dressOf(key);
      found[name] = { sex: dress.look.sex, look: dress.look, clothes: dress.clothes, backpack: dress.backpack };
    }
  }
  return found;
}

// Each person is a human in the boat's placeholder for them, small, in the full-body pose
function seatActors(movie) {
  const boat = movie.child("boat");
  const scale = constant("endingScale", DEFAULT_SCALE) / 100;
  for (const { name, pose } of ACTORS) {
    const holder = boat?.child(name);
    if (!looks[name] || !holder) {
      continue;
    }
    const made = makeHuman(looks[name]);
    made.setAnimMode("full");
    made.clip.scale.set(scale);
    holder.attach(made.clip, name);
    if (!goto(made.clip, pose)) {
      made.clip.gotoAndStop(1);
    }
  }
}

// ---------- Starting ----------

// The ending is asked for (trigger 61): the world stops where it is, and the next step clears the stage for the movie
export function playEnding() {
  if (view || starting || !story.player) {
    return false;
  }
  starting = true;
  looks = captureLooks();
  world.pause(PAUSE);
  record("ask");
  return true;
}

// The save, then the world's room and sounds go and the movie starts
async function begin() {
  closePanel();
  savePoint("ending");
  sound.stopAll();
  world.stop();
  world.reset();
  clearRoom();
  await page.lib.need([page.lib.exported("ending"), page.lib.exported("human")]);
  const clip = page.attach("ending", depth, "ending");
  view = { clip, panel: null, buttons: {} };
  seatActors(clip);
  record("start", { actors: Object.keys(looks) });
}

// ---------- The ending panel ----------

function wire(button, action) {
  button.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

function addButton(panel, name, x, delay, action) {
  const button = page.lib.make(BUTTON);
  button.position.set(x, BUTTON_Y);
  button.alpha = 0;
  setText(button.child("buttonText"), WORDS[name]);
  wire(button, action);
  panel.addChild(button);
  tween(button, "alpha", 100, BUTTON_FADE, { delay });
  return button;
}

// The black ground, the darkened skyline, its border and the two buttons, fading in
function buildPanel() {
  const panel = new Container();
  panel.zIndex = depth + 1;
  panel.label = "endingPanel";
  panel.advance = () => panel.children.forEach((each) => each.advance?.());
  panel.addChild(new Graphics().rect(0, 0, page.width, page.height).fill(0x000000));
  const backing = page.lib.make(BACKING);
  backing.position.set(page.width / 2 + BACKING_AT.x, page.height / 2 + BACKING_AT.y);
  applyColor(backing, DARKEN);
  panel.addChild(backing);
  const border = page.lib.make(BORDER);
  border.position.set(page.width / 2 + BORDER_AT.x, page.height / 2 + BORDER_AT.y);
  panel.addChild(border);
  view.buttons = {
    roll: addButton(panel, "roll", ROLL_X, ROLL_AT, () => showCredits(false)),
    back: addButton(panel, "back", BACK_X, BACK_AT, leave),
  };
  panel.alpha = 0;
  tween(panel, "alpha", 100, PANEL_FADE);
  page.root.addChild(panel);
  return panel;
}

// The movie's last frame (endingcredits): the menu music, then the panel
function showPanel() {
  if (!view || view.panel) {
    return;
  }
  sound.music(MENU_TRACK, { loops: MENU_LOOPS });
  view.panel = buildPanel();
  record("panel");
}

// ---------- Leaving ----------

function clearView() {
  if (!view) {
    return;
  }
  const gone = view;
  view = null;
  for (const part of [gone.panel, ...Object.values(gone.buttons)]) {
    if (part && !part.destroyed) {
      stopTweens(part);
    }
  }
  gone.panel?.destroy({ children: true });
  page.detach("ending");
}

// Back to the main menu: the movie and the panel go, and the story is left at the end
function leave() {
  if (!view) {
    return;
  }
  record("leave");
  clearView();
  quitToMenu();
}

// ---------- The credits ----------

function upper(text) {
  return String(text).toUpperCase();
}

// A list's field says every name on a line and grows to hold them (autoSize "left")
function fillList(list, names) {
  const field = list.child("txt");
  field.def = { ...field.def, multiline: true };
  setText(field, names.map((name) => `${upper(name)}\r`).join(""));
  const height = Math.ceil(field.contentHeight);
  if (height > field.box.height) {
    field.box = { ...field.box, height };
    field.redraw();
  }
}

function heightOf(node) {
  const bounds = node.getLocalBounds();
  return bounds.maxY - bounds.minY;
}

// The beta testers' rows with a clip now: the ones near the window have one, the rest none
function stepRows() {
  const { text, beta, rows, names } = credits;
  const first = (-WINDOW_TOP - BETA_REACH - text.y - beta.y - BETA_TOP) / BETA_ROW;
  const last = (WINDOW_TOP + BETA_REACH - text.y - beta.y - BETA_TOP) / BETA_ROW;
  const from = Math.max(0, Math.floor(first));
  const to = Math.min(Math.ceil(names.length / 2) - 1, Math.ceil(last));
  for (const [row, clips] of rows) {
    if (row < from || row > to) {
      clips.forEach((each) => each.destroy({ children: true }));
      rows.delete(row);
    }
  }
  for (let row = from; row <= to; row += 1) {
    if (!rows.has(row)) {
      rows.set(row, [0, 1].filter((side) => names[row * 2 + side] !== undefined).map((side) => addName(row, side)));
    }
  }
}

function addName(row, side) {
  const { beta, names } = credits;
  const node = page.lib.makeExported("creditsBetaTester");
  node.position.set(side * BETA_COLUMN, BETA_TOP + row * BETA_ROW);
  setText(node.child("txt"), upper(names[row * 2 + side]));
  beta.attach(node, `bt${row * 2 + side}`);
  return node;
}

// One step of the scroll
function stepCredits() {
  const speed = constant("creditsScrollSpeed", DEFAULT_SPEED) / page.lib.fps;
  credits.text.y -= speed;
  stepRows();
  if (credits.text.y + credits.bottom <= -WINDOW_TOP) {
    closeCredits();
  }
}

function closeCredits() {
  if (!credits) {
    return;
  }
  const done = credits;
  credits = null;
  stopTweens(done.clip);
  stopTweens(done.clip.child("backing"));
  page.detach("credits");
  input.shutByClick();
  record("creditsClosed", { ending: done.ending });
  if (done.ending) {
    leave();
  }
  done.resolve();
}

// A button of the window that goes back: it clicks, rolls over with a sound for a mouse and closes on release
function wireBack(clip) {
  const back = clip.child("back");
  back.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  back.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  back.setHandler("onRelease", closeCredits);
}

// Rolls the credits. From the ending (fromMenu false) the window has its bars, the skyline fades in over two minutes
// and closing goes back to the main menu; from the menu it stays over the menu. Resolves when they close
export async function showCredits(fromMenu = false) {
  if (credits) {
    return credits.done;
  }
  // BACK may sit where CREDITS was, and the menu comes back under the pointer when it closes: the second click of a
  // double click presses nothing either way
  input.shutByClick();
  await page.lib.need([page.lib.exported("menu_credits"), page.lib.exported("creditsBetaTester")]);
  const ending = !fromMenu;
  if (ending) {
    view?.panel?.destroy({ children: true });
    if (view) {
      view.panel = null;
      view.buttons = {};
    }
  }
  const clip = page.attach("menu_credits", depth + 2, "credits");
  clip.position.set(page.width / 2, page.height / 2);
  clip.child("endingBars").visible = ending;
  const text = clip.child("creditsText");
  const ads = text.child("fakeAdList");
  const beta = text.child("betaTesterList");
  const creditsData = data.story.credits;
  fillList(ads, creditsData.advertising);
  fillList(text.child("notesList"), creditsData.notes);
  text.y = TEXT_START;
  beta.y = ads.y + heightOf(ads) + LIST_GAP;
  const names = creditsData.beta;
  const bottom = beta.y + BETA_TOP + Math.ceil(names.length / 2) * BETA_ROW;
  const done = new Promise((resolve) => {
    credits = { clip, text, beta, rows: new Map(), names, bottom, ending, resolve };
  });
  credits.done = done;
  wireBack(clip);
  if (ending) {
    clip.alpha = 0;
    tween(clip, "alpha", 100, 1);
    const backing = clip.child("backing");
    backing.alpha = 0;
    tween(backing, "alpha", 100, 120, { ease: "easeInSine" });
  }
  record("credits", { ending });
  return done;
}

// ---------- Setup and checks ----------

export const ENDING_HOOKS = {
  endingcredits() {
    showPanel();
    return true;
  },
};

function step() {
  if (starting) {
    starting = false;
    begin().catch((e) => console.error("Union City: the ending couldn't start", e));
  }
  if (credits) {
    stepCredits();
  }
}

export function initEnding(owner, band) {
  page = owner;
  depth = band;
  hud.noOverlay.add(PAUSE);
  triggers.hooks.ending = playEnding;
  page.steppers.push(step);
  world.onReset(() => {
    log.length = 0;
  });
}

export const ending = {
  play: playEnding,
  credits: showCredits,
  get active() {
    return view !== null || starting;
  },
  // The credits are scrolling, from the menu or after the ending
  get creditsShowing() {
    return credits !== null;
  },
  log,
};

// Helpers for page.py checks
export const endingDebug = {
  // Asks for the ending as trigger 61 does
  endingPlay() {
    return { asked: playEnding(), ...endingDebug.endingState() };
  },

  // What shows now: the movie's frame, whether its panel and buttons are up and where the credits have got to
  endingState() {
    return {
      starting,
      showing: view !== null,
      frame: view?.clip.frame ?? null,
      panel: Boolean(view?.panel),
      panelAlpha: view?.panel?.alpha ?? null,
      boat: view
        ? ACTORS.map(({ name }) => ({ name, seated: Boolean(view.clip.child("boat")?.child(name)?.child(name)) }))
        : null,
      credits: credits
        ? {
            ending: credits.ending,
            y: credits.text.y,
            bottom: credits.bottom,
            rows: credits.rows.size,
            alpha: credits.clip.alpha,
            backingAlpha: credits.clip.child("backing").alpha,
          }
        : null,
      paused: world.paused,
      reasons: [...world.reasons],
      log: log.slice(-8),
    };
  },

  // Jumps the movie to a frame, as if that much time had gone by
  endingGoto(frame) {
    view?.clip.gotoAndPlay(frame);
    return view?.clip.frame ?? null;
  },

  // Presses a button of the panel ("roll", "back") or the credits' back button ("close") as a mouse would
  endingPress(name) {
    const event = { pointerType: "mouse", button: 0 };
    if (name === "close") {
      credits?.clip.child("back").handlers.onRelease(event);
    } else {
      view?.buttons[name]?.handlers.onRelease(event);
    }
    return endingDebug.endingState();
  },

  // Moves the credits' text so its top is at y (the window's middle is 0)
  endingScrollTo(y) {
    if (credits) {
      credits.text.y = y;
      stepRows();
    }
    return endingDebug.endingState();
  },
};
