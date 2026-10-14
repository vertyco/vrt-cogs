// Bloxorz's main menu, Load Stage, Credits and the nine instruction pages. They are the original's own timelines
// (sprite 197 holds the menu, Load Stage and Credits as frames of one clip; sprite 265 holds the pages), with each of
// their buttons given the press, hover and sounds the original's button scripts gave it. Continue and Leaderboard are
// new rows under Credits, drawn as page pictures. The bot starts every run: a passcode, Continue or Start New Game
// each send one message, and the stage screen shows when the bot's `stage` answer has arrived.
import { Button, Clip, setMatrix } from "./flash.js";
import { Container, Rectangle, Sprite } from "./vendor/pixi.min.mjs";

// The original's characters
const MENU = 197;
const INSTRUCTIONS = 265;
const END_STATS = 196;
// The original's stage width, which the canvas is scaled from
const STAGE_WIDTH = 550;
// Root frame 30 places the instruction pages here
const INSTRUCTIONS_AT = [1, 0, 0, 1, 8.95, 163];
// Frames of the menu clip (the original's own numbers)
const MENU_READY = 134;
const LOAD_STAGE = 176;
const LOAD_STAGE_PASSED = 187;
const LOAD_STAGE_START = 167;
const LOAD_STAGE_TO_INSTRUCTIONS = 219;
const LOAD_STAGE_TO_CREDITS = 296;
const CREDITS = 251;
// The end screen: its first frame, and the last before the title (S197/f365 plays from the start)
const END_FIRST = 320;
const END_LAST = 364;
// The end stats clip's depth in the menu clip (DefineSprite_196, placed at frame 349), whose Next button (B195) plays
// the menu on to the title
const END_STATS_DEPTH = 6;
// The page stops of the instruction pages: Prev stops walking backwards on reaching one
const PAGE_STOPS = new Set([14, 34, 54, 74, 94, 114, 134, 154, 174]);
const SKIP_INSTRUCTIONS = 186;
// The bc clip's frames: the hover sound and the press sound
const HOVER_SOUND = 2;
const PRESS_SOUND = 4;
// Buttons that play neither (their scripts have no rollOver or press, or reach a `bc` that isn't there: B195 sits in
// the end stats clip, so its `_parent.bc` is the menu clip's, which has none)
const QUIET = new Set([176, 195, 206, 211, 223]);
const PASSCODE_LENGTH = 6;
// The passcode's digit pictures and the number a blank shows (the original's `numberframe`): a digit d is frame d + 1,
// the next free spot shows the cursor frame, the spots after it the blank one
const CURSOR_FRAME = 11;
const BLANK_FRAME = 12;
// The passcode's digits on the stage (the clip at 183.45, 213.45 with digits from x 136 in 10 pixel steps), which the
// phone's number box covers
const INPUT_BOX = { x: 317, y: 214, width: 66, height: 20 };
// Continue and Leaderboard: rows 5 and 6 under Credits at the original's 18 pixel row spacing, with their letters
// starting where the original's start. The pictures are 34 pixels tall with letters about 31 tall, drawn at the
// original's 9 pixel letter height
const ROW_LEFT = 149.5;
const ROW_Y = [249.5, 267.5];
const ROW_HIT = { x: 142.5, width: 133, above: 8, height: 16 };
const ROW_SCALE = 0.29;
const ROW_LETTER_LEFT = 2;
const ROW_LETTER_MIDDLE = 17;
const ROW_HOVER = 0xff6a5a;
const ROW_DIMMED = 0.4;

const state = {
  // The new rows' pictures, loaded when the menu first shows
  labels: null,
  rows: null,
  // The passcode being typed, and the passcode clip it belongs to (a new clip starts empty)
  field: null,
  digits: "",
  boxStyle: "",
  keys: null,
};

// ---------- Buttons ----------

function noise(page, frame) {
  page.bc?.gotoAndPlay(frame);
}

const hitAreas = new Map();

// A button's own press area, from the "h" look the original gives it (the page draws only the up, over and down looks)
function hitAreaOf(button) {
  let area = hitAreas.get(button.charId);
  if (area) {
    return area;
  }
  const record = button.records.find((entry) => entry[2].includes("h"));
  const holder = new Container();
  const node = button.lib.make(record[0]);
  setMatrix(node, record[3]);
  holder.addChild(node);
  const { minX, minY, maxX, maxY } = holder.getLocalBounds();
  holder.destroy({ children: true });
  area = new Rectangle(minX, minY, maxX - minX, maxY - minY);
  hitAreas.set(button.charId, area);
  return area;
}

// Gives one of the original's buttons its looks (over, down), its sounds and what letting go of it does. Like Flash,
// the press has to start on the button
export function wireButton(page, button, release, sounds = true) {
  if (button.wired) {
    return;
  }
  button.wired = true;
  button.eventMode = "static";
  button.cursor = "pointer";
  button.hitArea = hitAreaOf(button);
  let pressed = false;
  // A finger has no hover: its over arrives with the press, and drawing a look then would rebuild the button's parts
  // under the finger
  button.on("pointerover", (event) => {
    if (event.pointerType === "touch") {
      return;
    }
    button.show("o");
    if (sounds) {
      noise(page, HOVER_SOUND);
    }
  });
  button.on("pointerout", () => button.show("u"));
  button.on("pointerdown", () => {
    pressed = true;
    button.show("d");
    if (sounds) {
      noise(page, PRESS_SOUND);
    }
  });
  button.on("pointerup", (event) => {
    button.show(event.pointerType === "touch" ? "u" : "o");
    if (pressed) {
      pressed = false;
      release();
    }
  });
  button.on("pointerupoutside", () => {
    pressed = false;
    button.show("u");
  });
}

// Wires every button the clip's timeline shows now that has an action. actions: button character -> fn(clip).
// Called once a tick, since a frame that places a button makes a new one
export function wireButtons(page, clip, actions) {
  for (const slot of clip.slots.values()) {
    const node = slot.node;
    if (node instanceof Button && !node.wired && actions[node.charId]) {
      wireButton(
        page,
        node,
        () => actions[node.charId](clip),
        !QUIET.has(node.charId),
      );
    }
  }
}

// ---------- What the buttons do ----------

export function toggleSound(page) {
  const wasMuted = page.sound.muted;
  page.sound.toggle();
  // Turning the sound back on plays the press sound the press itself couldn't (B150)
  if (wasMuted) {
    noise(page, PRESS_SOUND);
  }
}

function jump(frame) {
  return (clip) => clip.gotoAndPlay(frame);
}

function play(clip) {
  clip.play();
}

// Prev: the pages play backwards a frame a tick (the clip's enterFrame below)
function back(clip) {
  clip.set("reverseplay", true);
  clip.stop();
}

// Next
function next(clip) {
  clip.set("reverseplay", false);
  clip.play();
}

function menuActions(page) {
  return {
    150: () => toggleSound(page),
    171: () => toggleSound(page),
    151: jump(LOAD_STAGE_START),
    152: play,
    153: jump(CREDITS),
    170: jump(LOAD_STAGE_TO_CREDITS),
    172: () => submitPasscode(page),
    173: jump(LOAD_STAGE_TO_INSTRUCTIONS),
    174: play,
    176: play,
    183: play,
  };
}

const INSTRUCTION_ACTIONS = {
  206: back,
  211: next,
  212: back,
  213: jump(SKIP_INSTRUCTIONS),
  214: next,
  223: back,
  224: back,
  264: next,
};

// ---------- Starting a run ----------

// Asks the bot to start a run: "new" (Start New Game), "passcode" (value is the six digits) or "continue". False when
// the bot can't be reached, with the player told why
function startRun(page, kind, value) {
  if (!page.needBot()) {
    return false;
  }
  page.requested = kind;
  if (kind === "new") {
    return page.send({ new: true });
  }
  return page.send(kind === "passcode" ? { passcode: value } : { continue: true });
}

function submitPasscode(page) {
  // Fewer digits is a wrong code, which does nothing, as in the original
  if (state.digits.length === PASSCODE_LENGTH) {
    startRun(page, "passcode", state.digits);
  }
}

// The bot's answer to a request for a run. A new run goes straight to the stage; a passcode or Continue plays the
// menu's way out first (its newgame hook shows the stage)
function receiveStage(page) {
  const kind = page.requested;
  page.requested = null;
  const clip = page.menu;
  if (kind === "new") {
    page.go("stage");
  } else if (kind === "passcode" && clip?.frame === LOAD_STAGE) {
    clip.gotoAndPlay(LOAD_STAGE_PASSED);
  } else if (kind === "continue" && clip?.frame === MENU_READY) {
    clip.gotoAndPlay(LOAD_STAGE_PASSED);
  }
}

// The original's script hooks that end the menu's and the pages' timelines. The clip stops where it is, as the
// original's root left it behind, so it can't run on into other frames while the next screen loads
function setupHooks(page) {
  page.onHook("instructions", (argument, clip) => {
    clip.stop();
    page.go("instructions");
  });
  page.onHook("newgame", (argument, clip) => {
    clip.stop();
    if (clip.charId === MENU) {
      page.go("stage");
      return;
    }
    if (!startRun(page, "new")) {
      // The pages can't start a run, so they go back to the menu
      page.skiptomenu = true;
      page.go("menu");
    }
  });
}

// ---------- Frame scripts ----------

// The title animation's first frame: it jumps ahead when the player is coming back to the menu (skiptomenu) or
// finishing the game (skiptoend)
function menuScript(page, clip, frame) {
  if (frame !== 1) {
    return;
  }
  if (page.skiptoend) {
    // The original clears it at the end screen's last frame (S197/f365), which only the title follows
    page.skiptoend = false;
    clip.gotoAndPlay(END_FIRST);
  } else if (page.skiptomenu) {
    clip.gotoAndPlay(105);
  }
}

// The pages' first frame: reaching it while walking backwards leaves for the menu, which skips its title
function instructionsScript(page, clip, frame) {
  if (frame === 1 && clip.get("reverseplay")) {
    page.skiptomenu = true;
    page.go("menu");
  }
}

// ---------- Main menu ----------

async function loadMenu(page) {
  // Drawn about a third of their size, so they get mipmaps
  state.labels ??= await Promise.all([page.picture("menu-continue.png", true), page.picture("menu-leaderboard.png", true)]);
}

function makeRow(page, texture, y, press) {
  const row = new Container();
  const sprite = new Sprite(texture);
  sprite.scale.set(ROW_SCALE);
  sprite.position.set(ROW_LEFT - ROW_LETTER_LEFT * ROW_SCALE, y + 0.5 - ROW_LETTER_MIDDLE * ROW_SCALE);
  row.addChild(sprite);
  row.hitArea = new Rectangle(ROW_HIT.x, y - ROW_HIT.above, ROW_HIT.width, ROW_HIT.height);
  row.cursor = "pointer";
  row.sprite = sprite;
  let pressed = false;
  row.on("pointerover", (event) => {
    if (event.pointerType !== "touch") {
      sprite.tint = ROW_HOVER;
      noise(page, HOVER_SOUND);
    }
  });
  row.on("pointerout", () => {
    sprite.tint = 0xffffff;
  });
  row.on("pointerdown", () => {
    pressed = true;
    noise(page, PRESS_SOUND);
  });
  row.on("pointerup", () => {
    if (pressed) {
      pressed = false;
      press();
    }
  });
  row.on("pointerupoutside", () => {
    pressed = false;
  });
  return row;
}

function pressContinue(page) {
  startRun(page, "continue");
}

function pressLeaderboard(page) {
  page.go("leaderboard");
}

function addRows(page) {
  const presses = [() => pressContinue(page), () => pressLeaderboard(page)];
  const box = new Container();
  const [continueRow, leaderboardRow] = state.labels.map((texture, index) =>
    makeRow(page, texture, ROW_Y[index], presses[index]),
  );
  box.addChild(continueRow, leaderboardRow);
  box.visible = false;
  state.rows = { box, continueRow, leaderboardRow };
  page.root.addChild(box);
}

function enterMenu(page) {
  page.sound.music("menu", 1);
  page.menu = page.lib.make(MENU);
  page.root.addChild(page.menu);
  addRows(page);
  state.keys = (event) => typeDigit(page, event);
  window.addEventListener("keydown", state.keys);
}

function leaveMenu(page) {
  window.removeEventListener("keydown", state.keys);
  state.keys = null;
  state.field = null;
  state.digits = "";
  hideInput();
  page.requested = null;
  state.rows?.box.destroy({ children: true });
  state.rows = null;
  page.menu?.destroy({ children: true });
  page.menu = null;
  page.ending = false;
}

// The new rows show with the original's four items, which stand still on one frame, and Continue waits for a saved run
function stepRows(page, clip) {
  const ready = clip.frame === MENU_READY;
  const { box, continueRow, leaderboardRow } = state.rows;
  box.visible = ready;
  const saved = page.saved !== null;
  continueRow.eventMode = ready && saved ? "static" : "none";
  continueRow.sprite.alpha = saved ? 1 : ROW_DIMMED;
  leaderboardRow.eventMode = ready ? "static" : "none";
}

// ---------- Load Stage ----------

function passcodeInput() {
  return document.getElementById("passcode-input");
}

function hideInput() {
  const input = passcodeInput();
  input.hidden = true;
  input.blur();
  input.value = "";
  state.boxStyle = "";
}

function typeDigit(page, event) {
  if (!state.field || event.ctrlKey || event.metaKey || event.altKey) {
    return;
  }
  if (event.key === "Enter") {
    submitPasscode(page);
    return;
  }
  // The number box on a phone types for itself
  if (event.target === passcodeInput()) {
    return;
  }
  if (/^[0-9]$/.test(event.key)) {
    if (state.digits.length < PASSCODE_LENGTH) {
      state.digits += event.key;
    }
  } else if (event.key === "Backspace" || event.key === "Delete") {
    // One digit a press, however long the key is held (the original's `pusheded`)
    if (!event.repeat) {
      state.digits = state.digits.slice(0, -1);
    }
  }
}

// A phone's number keyboard types into the page's own box over the digits, which drives the same digits
function placeInput(page, input) {
  const box = page.app.canvas.getBoundingClientRect();
  const k = box.width / STAGE_WIDTH;
  const style = `${box.left + INPUT_BOX.x * k}|${box.top + INPUT_BOX.y * k}|${k}`;
  if (style === state.boxStyle) {
    return;
  }
  state.boxStyle = style;
  input.style.left = `${box.left + INPUT_BOX.x * k}px`;
  input.style.top = `${box.top + INPUT_BOX.y * k}px`;
  input.style.width = `${INPUT_BOX.width * k}px`;
  input.style.height = `${INPUT_BOX.height * k}px`;
  input.style.fontSize = `${14 * k}px`;
}

function openInput(page) {
  const input = passcodeInput();
  if (!window.matchMedia("(pointer: coarse)").matches) {
    return;
  }
  input.hidden = false;
  input.value = "";
  input.oninput = () => {
    state.digits = input.value.replace(/\D/g, "").slice(0, PASSCODE_LENGTH);
    input.value = state.digits;
  };
  placeInput(page, input);
  input.focus({ preventScroll: true });
}

// The passcode clip is on the stage only on the Load Stage frame. Each tick its six digit pictures show the digits
// typed so far (the original's `numberframe`)
function stepPasscode(page, clip) {
  const field = clip.frame === LOAD_STAGE ? clip.child("passcoder") : null;
  if (field !== state.field) {
    state.field = field;
    state.digits = "";
    if (field) {
      openInput(page);
    } else {
      hideInput();
    }
  }
  if (!field) {
    return;
  }
  const input = passcodeInput();
  if (!input.hidden) {
    placeInput(page, input);
    // A key press the number box didn't hear (a hardware keyboard) still counts
    input.value = state.digits;
  }
  for (let spot = 1; spot <= PASSCODE_LENGTH; spot += 1) {
    const typed = state.digits.length;
    let frame = BLANK_FRAME;
    if (spot <= typed) {
      frame = Number(state.digits[spot - 1]) + 1;
    } else if (spot === typed + 1) {
      frame = CURSOR_FRAME;
    }
    field.child(`digit${spot}`)?.gotoAndStop(frame);
  }
}

function stepMenu(page) {
  const clip = page.menu;
  if (!clip || !state.rows) {
    return;
  }
  wireButtons(page, clip, menuActions(page));
  stepRows(page, clip);
  stepPasscode(page, clip);
  stepEnd(page, clip);
}

// The end screen: its Next button, and the status line "Finished Bloxorz!" while it shows
function stepEnd(page, clip) {
  const ending = clip.frame >= END_FIRST && clip.frame <= END_LAST;
  if (ending !== page.ending) {
    page.ending = ending;
    page.report();
  }
  const stats = clip.at(END_STATS_DEPTH);
  if (stats instanceof Clip && stats.charId === END_STATS) {
    wireButtons(page, stats, { 195: () => clip.play() });
  }
}

// ---------- Instructions ----------

function enterInstructions(page) {
  const clip = page.lib.make(INSTRUCTIONS);
  setMatrix(clip, INSTRUCTIONS_AT);
  clip.set("reverseplay", false);
  // Prev walks the pages back a frame a tick (the original's enterFrame on the pages), and a page's stop frame ends it
  clip.onEnterFrame = () => {
    if (clip.get("reverseplay") && clip.frame > 1) {
      clip.gotoAndStop(clip.frame - 1);
      if (PAGE_STOPS.has(clip.frame)) {
        clip.set("reverseplay", false);
      }
    }
  };
  page.instructions = clip;
  page.root.addChild(clip);
}

function leaveInstructions(page) {
  page.instructions?.destroy({ children: true });
  page.instructions = null;
}

function stepInstructions(page) {
  if (page.instructions) {
    wireButtons(page, page.instructions, INSTRUCTION_ACTIONS);
  }
}

// ---------- Setup ----------

// The screens, frame scripts, hooks and messages this file owns. game.js shows the screens and ticks them
export function setupMenus(page) {
  setupHooks(page);
  page.onMessage("stage", () => receiveStage(page));
  page.onMessage("saved", () => {
    // Continue found nothing to resume
    page.requested = page.requested === "continue" ? null : page.requested;
  });
  page.startRun = (kind, value) => startRun(page, kind, value);
  return {
    screens: {
      menu: { art: [MENU], load: loadMenu, enter: enterMenu, leave: leaveMenu, step: stepMenu },
      instructions: {
        art: [INSTRUCTIONS],
        enter: enterInstructions,
        leave: leaveInstructions,
        step: stepInstructions,
      },
    },
    scripts: [
      [MENU, (clip, frame) => menuScript(page, clip, frame)],
      [INSTRUCTIONS, (clip, frame) => instructionsScript(page, clip, frame)],
    ],
  };
}
