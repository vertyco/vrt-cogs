// Death and respawn (showDeath F4:19883, hideDeath, deathRespawnHere, deathRespawnOutside, deathButtonSetup
// F4:19955-19999; sprite int_death, 6200, with its panel 6199 and its two restart buttons 6198). The player's last hit
// makes them fall in the full-body death pose, the world stops, and after two seconds the red screen fades in with the
// panel: a random word, how many days they survived, RESTART HERE, RESTART OUTSIDE and QUIT.
//
// RESTART HERE costs half the XP and starts the room again where the player came in, with its zombies forgotten.
// RESTART OUTSIDE costs a quarter and puts them at the entrance of the building they died in, on the street's first
// room; a death already on a street keeps that street room. Health is full either way, and items, cash, quests and the
// clock stay. QUIT goes back to the main menu without saving, after asking, except in Hardcore. A Hardcore death wipes
// the slot at once and offers only QUIT. While the screen is up nothing opens: the world holds a "death" pause, which
// no panel, the pause menu or a save point gets past (S22).
import { onCombat } from "./combat.js";
import { data } from "./data.js";
import { director, musicDirector } from "./director.js";
import { hud, setText, stopTweens, tween } from "./hud.js";
import { input } from "./input.js";
import { closePanel, fadeInBox, fadeOutBox, finger, setAlpha } from "./panels.js";
import { quitToMenu } from "./pause.js";
import { fullHealth, loseXP, player } from "./player.js";
import { gotoPlay } from "./rig.js";
import { rng } from "./rng.js";
import { camera, enterRoom, onRoom, room } from "./rooms.js";
import { endStory } from "./save.js";
import { sound } from "./sound.js";
import { story } from "./story.js";
import { world } from "./world.js";
import { endStruggle, zombieMemory } from "./zombies.js";

const PAUSE = "death";
const ART = "int_death";
const EASE = "easeOutSine";
const DEFAULT_DELAY = 2;
const DEFAULT_SHAKE_MS = 50;
// The red screen's blood splat comes in 0.3 s after the screen is up, and the panel 0.5 s after it
const SPLAT = { delay: 0.3, from: 20, seconds: 0.1 };
const PANEL = { delay: 0.5, from: 50, seconds: 0.1 };
const QUIT_ASK = {
  heading: "QUIT",
  body: "ALL PROGRESS SINCE YOUR LAST\r SAVE WILL BE LOST.\r\rDO YOU WANT TO QUIT?",
  yes: "YES",
  no: "NO",
};
const DIALOG = { fade: 0.6, shade: 0.6, out: 0.1 };
const HARDCORE_LINES = "\rSADLY, BECAUSE YOU WERE PLAYING\rHARDCORE YOUR STORY IS OVER";
const FALLBACK_MESSAGE = "YOU DIED";
const MOST_RECORDED = 50;

let page = null;
let depth = 0;
// The death screen up now: { clip, panel, hardcore, dialog }
let view = null;
// The room whose zombies are forgotten as the player leaves it (RESTART HERE), until that change has run
let forgetRoom = null;
// What was shown, pressed and chosen, newest last, for checks
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

// ---------- Falling ----------

// A man's death cry, now and then the Wilhelm scream; a woman's own (playHumanDeadSound F4:5369)
function deathCry() {
  const sex = story.player?.sex;
  let name = `sound_humanDead${rng.random(4) + 1}`;
  if (sex === "male") {
    name = rng.random(100) === 0 ? "sound_humanDeadWilhelm" : `sound_humanDead${rng.random(3) + 1}`;
  } else if (sex === "female") {
    name = `sound_humanDeadFemale${rng.random(2) + 1}`;
  }
  sound.play(name, { x: player.x });
}

// The last hit: the cry, then a standing death in the full-body pose with the weapon hidden (F4:5679-5686)
function fall() {
  deathCry();
  if (player.clip && !player.clip.destroyed) {
    player.rig?.setAnimMode("full");
    const held = player.rig?.animWeapon;
    if (held) {
      held.visible = false;
    }
    gotoPlay(player.clip, `death_standing${rng.random(2) + 1}`);
  }
  showDeath();
}

// ---------- The screen ----------

function daysWords() {
  const days = world.day;
  return `AFTER SURVIVING ${days} DAY${days <= 1 ? "" : "S"}, YOU HAVE DIED.`;
}

// What a restart costs, shown under its button: the XP now over the share the original divides it by
function penaltyWords(name, fallback) {
  return `-${Math.round(story.player.xp / constant(name, fallback))} XP`;
}

// The words of the panel: a random word, the days survived and what each restart costs
function fillPanel(panel, hardcore) {
  const messages = data.story?.deathMessages ?? [FALLBACK_MESSAGE];
  setText(panel.child("deathMsg"), messages[rng.random(messages.length)]);
  const field = panel.child("deathText");
  field.def = { ...field.def, multiline: true };
  setText(field, daysWords() + (hardcore ? HARDCORE_LINES : ""));
  const buttons = panel.child("restartButtons");
  setText(buttons.child("xpPenalty"), penaltyWords("xpRespawnPen", 2));
  setText(buttons.child("xpPenaltyOutside"), penaltyWords("xpRespawnPenOutside", 4));
  buttons.visible = !hardcore;
}

// The red screen fades in over the delay; its blood splat and then its panel pop in behind it (F4:19899-19921). The
// panel's buttons take no press until it has faded in: it shows half a second after the screen, and a press on it
// before then would restart from a screen that looks empty (P41)
function fadeIn(clip, panel) {
  const delay = constant("deathShowDelay", DEFAULT_DELAY);
  const splat = clip.child("bloodSplat");
  clip.alpha = 0;
  panel.visible = false;
  panel.interactiveChildren = false;
  tween(clip, "alpha", 100, delay, {
    ease: EASE,
    done: () => {
      panel.visible = true;
    },
  });
  splat.alpha = 0;
  splat.scale.set(SPLAT.from / 100);
  tween(splat, "scale", 100, SPLAT.seconds, { ease: EASE, delay: delay + SPLAT.delay });
  tween(splat, "alpha", 100, SPLAT.seconds, {
    ease: EASE,
    delay: delay + SPLAT.delay,
    done: () => sound.play("sound_bodyHit3"),
  });
  panel.alpha = 0;
  panel.scale.set(PANEL.from / 100);
  tween(panel, "scale", 100, PANEL.seconds, { ease: EASE, delay: delay + PANEL.delay });
  tween(panel, "alpha", 100, PANEL.seconds, {
    ease: EASE,
    delay: delay + PANEL.delay,
    done: () => {
      panel.interactiveChildren = true;
      sound.play("sound_openInterface");
    },
  });
}

// The player has died: the rush and the music end, panels and a struggle close, the world stops and the screen comes
// up. A Hardcore death wipes the slot now (showDeath F4:19883)
export function showDeath() {
  if (view) {
    return;
  }
  director.rushActive = false;
  musicDirector.loop(true);
  closePanel();
  endStruggle();
  const hardcore = story.hardcore === true;
  const clip = page.attach(ART, depth, "death");
  clip.position.set(page.width / 2, page.height / 2);
  const panel = clip.child("deathPanel");
  view = { clip, panel, hardcore, dialog: null };
  if (hardcore) {
    // The slot is dead on this device at once; a wipe that fails is tried again at every slot listing
    const slot = story.slot;
    record("wipe", { slot });
    endStory().then((wiped) => record("wiped", { slot, wiped }));
  }
  fillPanel(panel, hardcore);
  fadeIn(clip, panel);
  const shade = clip.child("redOut");
  shade.hand = false;
  shade.setHandler("onPress", () => {});
  world.pause(PAUSE);
  hud.hidePlay(true);
  record("show", { hardcore, text: panel.child("deathText").text });
}

// The screen goes and the world's pieces of the HUD come back (hideDeath). The world comes back under the pointer, so
// the second click of a double click on TRY AGAIN or RESTART OUTSIDE is no shot
function closeScreen() {
  const gone = view;
  view = null;
  if (gone && !gone.clip.destroyed) {
    stopTweens(gone.clip);
    gone.clip.destroy({ children: true });
  }
  hud.hidePlay(false);
  input.shutByClick();
}

// ---------- Restarting ----------

// Where RESTART OUTSIDE lands: the building's entrance on the street's first room; on a street, the same room's start
function outsideTarget() {
  const def = room.def;
  const building = Number(def.building.slice(1));
  const street = `${def.loc}_${def.street}_b0_f0_r1`;
  if (building === 0 || !data.world.rooms[street]) {
    return { id: room.id, arrival: "start" };
  }
  return { id: street, arrival: `entr${building}` };
}

// A restart: the XP it costs goes, health is full, the player enters the room and the world goes on once it is built
function respawn(outside) {
  const go = outside ? outsideTarget() : { id: room.id, arrival: room.arrivalX };
  loseXP({ outside });
  fullHealth();
  forgetRoom = outside ? null : room.id;
  record("restart", { outside, to: go.id, arrival: go.arrival });
  closeScreen();
  enterRoom(go.id, go.arrival)
    .then(() => camera.shake(1, constant("screenShakeDelay", DEFAULT_SHAKE_MS)))
    .catch((e) => console.warn("Union City: the respawn couldn't enter its room", e))
    .finally(() => {
      forgetRoom = null;
      world.resume(PAUSE);
    });
}

// Zombies that were in the room when the player died there are forgotten, after the room saved them as it was left
// (resetZombieSaveAtLoc F4:14513)
function forgetZombies() {
  if (forgetRoom) {
    zombieMemory.forget(forgetRoom);
    forgetRoom = null;
  }
}

// ---------- Quitting ----------

function quit() {
  if (!view) {
    return;
  }
  record("quit");
  closeScreen();
  quitToMenu();
}

function closeDialog() {
  const box = view?.dialog;
  if (!box) {
    return;
  }
  view.dialog = null;
  fadeOutBox(box, DIALOG.out, { ease: EASE });
}

// A button of the box: it clicks when pressed, rolls over with a sound for a mouse and does its action on release
function dialogButton(box, name, words, action) {
  const button = box.child(name);
  button.visible = true;
  setText(button.child("buttonText"), words);
  button.setHandler("onPress", () => sound.play("sound_interfaceClick"));
  button.setHandler("onRollOver", (event) => {
    if (!finger(event)) {
      sound.play("sound_interfaceOver");
    }
  });
  button.setHandler("onRelease", action);
}

// The box over the screen that asks whether to quit (dialog_quitNoSave F4:20260): everything behind it is shut off
function askQuit() {
  const box = view.clip.lib.makeExported("dialogBox");
  view.clip.attach(box, "dialogBox");
  view.dialog = box;
  sound.play("sound_interfaceOver");
  for (const name of ["button1", "button2", "button3"]) {
    box.child(name).visible = false;
  }
  const shade = box.child("blackOut");
  setAlpha(shade, DIALOG.shade);
  shade.hand = false;
  setText(box.child("textBoxes").child("headingText"), QUIT_ASK.heading);
  setText(box.child("textBoxes").child("bodyText"), QUIT_ASK.body);
  dialogButton(box, "button1", QUIT_ASK.yes, quit);
  dialogButton(box, "button2", QUIT_ASK.no, closeDialog);
  // YES and NO take no press while the box fades in, so the second click of a double click on QUIT can't answer NO,
  // which sits over it
  fadeInBox(box, DIALOG.fade, { ease: EASE });
}

// ---------- Pressing ----------

// A button of the panel was released (deathButtonSetup F4:19955): the two restarts, or QUIT
function press(name) {
  if (!view || view.dialog || !view.panel.visible) {
    return;
  }
  if (name === "here" || name === "outside") {
    respawn(name === "outside");
  } else if (name === "quitBtn") {
    if (view.hardcore) {
      quit();
    } else {
      askQuit();
    }
  }
}

export const DEATH_LOAD_CALLS = {
  deathButtonSetup(node, name) {
    node.setHandler?.("onRelease", () => press(name));
  },
};

// ---------- Setup and checks ----------

export function initDeath(owner, band) {
  page = owner;
  depth = band;
  hud.noOverlay.add(PAUSE);
  onCombat("playerDead", fall);
  onRoom("leave", forgetZombies);
  world.onReset(() => {
    if (view && !view.clip.destroyed) {
      view.clip.destroy({ children: true });
    }
    view = null;
    forgetRoom = null;
    log.length = 0;
  });
}

export const death = {
  get isOpen() {
    return view !== null;
  },
  log,
};

// Helpers for page.py checks
export const deathDebug = {
  // The player's last hit, as combat ends it: no health, dead, controls locked, then the fall
  deathDie() {
    story.player.health = 0;
    player.alive = false;
    player.controlsLocked = true;
    fall();
    return deathDebug.deathState();
  },

  // Releases a button of the panel ("here", "outside", "quitBtn") as a mouse would
  deathPress(name) {
    const buttons = view.panel.child("restartButtons");
    const button = name === "quitBtn" ? view.panel.child(name) : buttons.child(name);
    button.handlers.onRelease({ pointerType: "mouse", button: 0 });
    return deathDebug.deathState();
  },

  // Releases a button of the quit box ("button1" is YES, "button2" is NO)
  deathAnswer(name) {
    view.dialog.child(name).handlers.onRelease({ pointerType: "mouse", button: 0 });
    return deathDebug.deathState();
  },

  // What the screen shows now
  deathState() {
    const open = view !== null;
    const panel = view?.panel;
    const buttons = panel?.child("restartButtons");
    return {
      open,
      alpha: open ? view.clip.alpha : null,
      panelShown: open ? panel.visible : null,
      message: panel?.child("deathMsg").text ?? null,
      text: panel?.child("deathText").text ?? null,
      restartShown: open ? buttons.visible : null,
      penalty: buttons?.child("xpPenalty").text ?? null,
      penaltyOutside: buttons?.child("xpPenaltyOutside").text ?? null,
      hardcore: view?.hardcore ?? null,
      dialog: Boolean(view?.dialog),
      paused: world.paused,
      reasons: [...world.reasons],
      overlay: hud.overlayShown,
      alive: player.alive,
      xp: story.player?.xp ?? null,
      health: story.player?.health ?? null,
      room: room.id,
    };
  },

  deathLog() {
    return log.map((each) => ({ ...each }));
  },
};
