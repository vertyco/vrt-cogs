// The battle's panels over the field and the HUD: the trench button and its panel (showTrenchButton ..
// checkForEmptyTrench F5:5233-5485), the gas mask button (showGasMask and hideGasMask F5:3753-3789), the help tips
// (setupHelp and showHelp F5:6693-6748) and the in-battle menu (loadInGameMenu, hideInGameMenu and
// buttonSetup_inGameMenu F5:6568-6692).
//
// The bot decides everything. The page draws what each update says and sends only requests: send a squad over the top
// or flip a trench's lock, put the masks on, pause and resume, surrender, quit. The trench button shows while one of
// the player's squads holds a slot and no enemy squad does; the panel closes when that stops being true. A watcher
// presses none of these.
import { Rectangle } from "./vendor/pixi.min.mjs";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const EASE = "easeOutSine";
const LINEAR = "linear";
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const SIDES = ["british", "german"];
const NOT_CONNECTED = "Not connected. Try again in a moment.";
// The trench panel hangs 145 below its trench (showTrenchControls, F5:5333)
const PANEL_DROP = 145;
const TRENCH_SLOTS = 3;
// The squad kinds in deploy slot order, which are the labels of the panel's unit icons
const UNIT_ICONS = ["riflemen", "assault", "machineGun", "sniper", "officer", "tank"];
const EMPTY_ICON = "empty";
const SLOT_BAR_EMPTY = 0.01;
const FULL_PERCENT = 100;
// A press waits this long for the bot's word that it took
const ASK_MS = 2000;
const HOVER = [220, 0, 220, 0, 220, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// The gas mask button: the dialogs' button (sprite 845, 75 wide) made larger to press, over the sky between the top
// bars and the horizon, clear of the edge scroll zones, the quick messages and the help tips
const GAS_BUTTON = 845;
const GAS_SCALE = 1.5;
const GAS_X = 480;
const GAS_Y = 98;
const GAS_WORDS = "GAS MASKS";
const GAS_FADE = 0.3;
// The help panels in the original's order (helpArray), shown one at a time
const HELP_KEY = "warfare1917:help";
const HELP_TIPS = ["progressBar", "morale", "upgrades", "support"];
const HELP_COUNTDOWN = 4;
const HELP_SECONDS = 30;
const HELP_FADE = 0.8;
const HELP_CLOSE_FADE = 0.6;
// The support tip points at slots that only open from mission 2
const SUPPORT_TIP_FROM = 2;
const HELP_WORDS = {
  unitHelp: ["CREATE UNITS HERE", "Click the portraits to create units. Deploying a unit will reset ALL timers."],
  progressBar: [
    "GROUND TAKEN",
    "The top bar shows the ground taken by your army. Move your men to the enemy's end of the battlefield to win.",
  ],
  morale: [
    "MORALE BAR",
    "Seeing men die around them will make your army lose morale. Lose enough morale and your army may surrender.",
  ],
  upgrades: [
    "UPGRADES",
    "Killing enemies and winning battles will earn you XP. Earn enough XP and you'll be awarded an upgrade point.",
  ],
  support: ["FIRE SUPPORT", "To use your fire support items, click the icon, then click the red target on the map."],
};
// The in-battle menu sits in the middle of the stage, 25 above centre (loadInGameMenu, F5:6572-6573)
const MENU_X = 400;
const MENU_Y = 185;
const MENU_BACKING = 60;
const MENU_FADE = 1;
const QUALITY_LABEL = 1227;
const MENU_WORDS = {
  close: "CLOSE",
  sound_on: "ON",
  sound_off: "OFF",
  quitToMenu: "QUIT TO MAIN MENU",
  quitBattle: "QUIT BATTLE",
};

function readHelp() {
  try {
    const saved = JSON.parse(localStorage.getItem(HELP_KEY) ?? "null");
    if (saved && Number.isInteger(saved.index) && saved.index >= 0 && typeof saved.enabled === "boolean") {
      return saved;
    }
  } catch (e) {
    console.warn("Warfare 1917: couldn't read the help tips' progress", e);
  }
  return { index: 0, enabled: true };
}

function saveHelp(help) {
  try {
    localStorage.setItem(HELP_KEY, JSON.stringify(help));
  } catch (e) {
    console.warn("Warfare 1917: couldn't save the help tips' progress", e);
  }
}

// A Flash button (a look for up, over and down, flash.js's Button) takes presses over its own shape, and shows the look
// for the state the pointer puts it in
function pressable(button, onRelease) {
  const bounds = button.getLocalBounds();
  button.eventMode = "static";
  button.cursor = "pointer";
  button.interactiveChildren = false;
  button.hitArea = new Rectangle(bounds.x, bounds.y, bounds.width, bounds.height);
  button.on("pointerover", () => button.show("o"));
  button.on("pointerout", () => button.show("u"));
  button.on("pointerdown", () => button.show("d"));
  button.on("pointerup", () => button.show("o"));
  button.on("pointertap", onRelease);
}

export class Panels {
  constructor(field) {
    this.field = field;
    this.world = null;
    this.battle = null;
    this.side = "british";
    // One per trench: { index, clip, button, panel, locked, asked }
    this.trenches = [];
    this.gas = null;
    this.gasShown = false;
    this.menu = null;
    this.help = readHelp();
    // Deploys left before the next tip (helpCountdown, F5:7963). It starts over each time the page opens
    this.countdown = HELP_COUNTDOWN;
    this.panelCount = 0;
    field.onLoad((battle) => this.load(battle));
    field.onDraw(() => this.draw());
    field.onClear(() => this.reset());
    field.hud.onMenu = () => this.openMenu();
    field.hud.onDeploy = () => this.deployed();
  }

  get page() {
    return this.field.page;
  }

  get hud() {
    return this.field.hud;
  }

  // True when the viewer plays and so may press
  get interactive() {
    return Boolean(this.battle) && this.battle.you !== null;
  }

  // The clips and sprites this module attaches, loaded with the battlefield's
  static art() {
    return ["trenchInterface", "inGameMenu"];
  }

  static sprites() {
    return [GAS_BUTTON];
  }

  // ---------- Building ----------

  load(battle) {
    this.battle = battle;
    if (this.world === this.field.world) {
      this.askToResume();
      return;
    }
    this.reset();
    this.battle = battle;
    this.world = this.field.world;
    this.side = battle.you ?? battle.map.side;
    if (!this.interactive) {
      this.hud.clip.child("help").visible = false;
      return;
    }
    this.setupTrenches(battle.map.trenches);
    this.setupGas();
    this.setupHelp();
    this.askToResume();
  }

  // A solo battle arrives paused when its player's page dropped and came back, and the field would sit frozen with
  // no word why. The menu comes up, and its CLOSE sends the battle on
  askToResume() {
    const battle = this.battle;
    if (this.interactive && battle.kind !== "versus" && battle.paused && !battle.result) {
      this.openMenu();
    }
  }

  reset() {
    if (this.menu && !this.menu.holder.destroyed) {
      this.menu.holder.destroy({ children: true });
    }
    Object.assign(this, { world: null, battle: null, trenches: [], gas: null, gasShown: false, menu: null });
  }

  // ---------- Trenches ----------

  // Each trench's button, as the field built it hidden. Its handlers are the original's showTrenchButton ones
  setupTrenches(positions) {
    const bg = this.field.world.child("bg");
    this.trenches = positions.map((x, index) => {
      const clip = bg.child(`trench${index}`);
      const entry = { index, clip, button: clip.child("mainTrenchButton"), panel: null, locked: null, asked: null };
      this.wireTrenchButton(entry);
      return entry;
    });
  }

  wireTrenchButton(entry) {
    const button = entry.button;
    button.setHandler("onRollOver", () => {
      if (!entry.locked) {
        button.gotoAndStop("on");
      }
      tweens.colorTransformTo(button.child("backing"), ...HOVER, 0.4, EASE);
    });
    button.setHandler("onRollOut", () => {
      if (!entry.locked) {
        button.gotoAndStop("off");
      }
      tweens.colorTransformTo(button.child("backing"), ...NORMAL, 0.6, EASE);
    });
    button.setHandler("onRelease", (e) => {
      if (this.canPress(e)) {
        this.openPanel(entry);
      }
    });
  }

  // True when a press on a control counts: the viewer plays, and the press was not the end of a drag that scrolled
  canPress(e) {
    return this.interactive && !this.menu && !this.hud.dragged(e);
  }

  // The trench's button as showTrenchButton leaves it: no unit picture or health bar, the lock showing when locked
  paintButton(entry, locked) {
    const button = entry.button;
    entry.locked = locked;
    button.gotoAndStop(locked ? "locked" : "on");
    for (const name of ["unitIcon", "healthBar"]) {
      const part = button.child(name);
      if (part) {
        part.visible = false;
      }
    }
    const lock = button.child("lockedIcon");
    if (lock) {
      lock.visible = locked;
    }
  }

  // showTrenchControls (F5:5321-5372): the panel with the three squads' icons, the lock and the close button
  openPanel(entry) {
    if (entry.panel) {
      return;
    }
    const layer = this.field.layer("trenchHUD");
    this.panelCount += 1;
    const panel = this.page.lib.makeExported("trenchInterface");
    panel.label = `trenchControls${this.panelCount}`;
    panel.zIndex = this.panelCount;
    layer.addChild(panel);
    panel.gotoAndStop(this.side);
    panel.position.set(entry.clip.x, entry.clip.y + PANEL_DROP);
    panel.alpha = 0;
    tweens.alphaTo(panel, 100, 0.1);
    entry.panel = panel;
    entry.button.visible = false;
    this.setupPanelButtons(entry, panel);
  }

  setupPanelButtons(entry, panel) {
    for (let n = 1; n <= TRENCH_SLOTS + 2; n += 1) {
      const button = panel.child(`button${n}`);
      const hidden = n > TRENCH_SLOTS ? ["unitIcon", "healthBar", "onSwitch"] : ["lockedIcon", "onSwitch"];
      for (const name of hidden) {
        const part = button.child(name);
        if (part) {
          part.visible = false;
        }
      }
      button.setHandler("onRollOver", () => tweens.colorTransformTo(button, ...HOVER, 0.4, EASE));
      button.setHandler("onRollOut", () => tweens.colorTransformTo(button, ...NORMAL, 0.6, EASE));
    }
    panel.child("button5").child("lockedIcon").gotoAndStop("cancel");
    panel.child("button5").child("lockedIcon").visible = true;
    panel.child("button5").setHandler("onRelease", (e) => {
      if (this.canPress(e)) {
        this.closePanel(entry);
      }
    });
    panel.child("button4").setHandler("onRelease", (e) => {
      if (this.canPress(e)) {
        this.flipLock(entry);
      }
    });
    for (let slot = 0; slot < TRENCH_SLOTS; slot += 1) {
      panel.child(`button${slot + 1}`).setHandler("onRelease", (e) => {
        if (this.canPress(e)) {
          this.page.send({ trench: [entry.index, "go", slot] });
        }
      });
    }
  }

  // The lock asks the bot, and the words come when the bot's word shows the lock changed
  flipLock(entry) {
    if (this.page.send({ trench: [entry.index, "lock"] })) {
      entry.asked = { want: !entry.locked, until: performance.now() + ASK_MS };
    }
  }

  // hideTrenchControls (F5:5468-5477): the panel fades away. It stops taking presses at once
  closePanel(entry) {
    const panel = entry.panel;
    if (!panel) {
      return;
    }
    entry.panel = null;
    panel.eventMode = "none";
    panel.interactiveChildren = false;
    tweens.alphaTo(panel, 0, 0.2, EASE, 0, () => panel.destroy({ children: true }));
  }

  // The trench for the drawn moment: whether the player holds it with no enemy in it decides the button and panel
  paintTrench(entry, row, squads) {
    const [owner, locked, ids] = row;
    const mine = SIDES.indexOf(this.side);
    const held = ids.map((id) => squads.get(id)).filter(Boolean);
    const own = owner === mine || held.some((squad) => squad[1] === mine);
    const enemy = held.some((squad) => squad[1] !== mine);
    const lockedNow = Boolean(locked);
    this.checkAsked(entry, lockedNow);
    if (!own || enemy) {
      this.closePanel(entry);
      entry.button.visible = false;
      entry.locked = lockedNow;
      return;
    }
    if (entry.panel) {
      this.paintPanel(entry, ids, squads, lockedNow);
      entry.locked = lockedNow;
      return;
    }
    if (!entry.button.visible || entry.locked !== lockedNow) {
      entry.button.visible = true;
      this.paintButton(entry, lockedNow);
    }
  }

  // updateTrenchInterface and updateTrenchHealthBars (F5:5281-5320): each slot's unit icon and health bar, and the
  // lock button's icon
  paintPanel(entry, ids, squads, locked) {
    const panel = entry.panel;
    for (let slot = 0; slot < TRENCH_SLOTS; slot += 1) {
      const button = panel.child(`button${slot + 1}`);
      const squad = squads.get(ids[slot]);
      const bar = button.child("healthBar")?.child("bar");
      if (!squad) {
        button.child("unitIcon").gotoAndStop(EMPTY_ICON);
        if (bar) {
          bar.scale.x = SLOT_BAR_EMPTY;
        }
        continue;
      }
      button.child("unitIcon").gotoAndStop(UNIT_ICONS[squad[2] - 1]);
      if (bar) {
        const start = Math.max(1, this.field.units.squadFor(squad[0]).ids.size);
        bar.scale.x = Math.round((squad[7].length / start) * FULL_PERCENT) / FULL_PERCENT;
      }
    }
    panel.child("button4").child("lockedIcon").gotoAndStop(locked ? "lock" : "unlock");
  }

  // The quick message for a lock the bot took: "LOCKED TRENCH" or "UNLOCKED TRENCH"
  checkAsked(entry, locked) {
    const asked = entry.asked;
    if (!asked) {
      return;
    }
    if (locked === asked.want) {
      entry.asked = null;
      this.page.quickMessage(locked ? "LOCKED TRENCH" : "UNLOCKED TRENCH");
    } else if (performance.now() > asked.until) {
      entry.asked = null;
    }
  }

  // ---------- Gas masks ----------

  // The button for the masks: the dialogs' button, hidden until a gas round is out (hud.gasMask, F5:3753-3789)
  setupGas() {
    const button = this.hud.clip.attach(this.page.lib.make(GAS_BUTTON), "gasMask");
    button.position.set(GAS_X, GAS_Y);
    button.scale.set(GAS_SCALE);
    button.child("buttonText").text = GAS_WORDS;
    button.visible = false;
    button.setHandler("onRollOver", () => {
      sound.play(ROLL_OVER);
      tweens.colorTransformTo(button, ...HOVER, 0.4, EASE);
    });
    button.setHandler("onRollOut", () => tweens.colorTransformTo(button, ...NORMAL, 0.4, EASE));
    button.setHandler("onRelease", (e) => {
      if (this.canPress(e) && this.gasShown) {
        sound.play(CLICK);
        this.page.send({ masks: true });
      }
    });
    this.gas = button;
  }

  paintGas(on) {
    if (!this.gas || on === this.gasShown) {
      return;
    }
    this.gasShown = on;
    tweens.stopTween(this.gas);
    if (on) {
      this.gas.alpha = 0;
      this.gas.visible = true;
      tweens.alphaTo(this.gas, 100, GAS_FADE);
    } else {
      tweens.alphaTo(this.gas, 0, GAS_FADE, LINEAR, 0, () => {
        this.gas.visible = false;
      });
    }
  }

  // ---------- Help tips ----------

  // setupHelp (F5:6693-6727): the first tip is up from the first battle and the others wait for their turn
  setupHelp() {
    const help = this.hud.clip.child("help");
    help.visible = true;
    for (const name of Object.keys(HELP_WORDS)) {
      const panel = help.child(name);
      const [header, desc] = HELP_WORDS[name];
      panel.child("header").text = header;
      panel.child("desc").text = desc;
      panel.visible = name === "unitHelp" && this.help.index === 0 && this.help.enabled;
      pressable(panel.child("closeButton"), () => {
        sound.play(CLICK);
        tweens.alphaTo(panel, 0, HELP_CLOSE_FADE, EASE, 0, () => {
          panel.visible = false;
        });
      });
    }
    help.child("progressBar").gotoAndStop("flipped");
    help.child("morale").gotoAndStop("flipped");
  }

  // showHelp (F5:6728-6748), called on each deploy: every 4th one brings the next tip up for 30 seconds
  deployed() {
    this.countdown -= 1;
    if (this.countdown > 0 || !this.help.enabled || !this.interactive) {
      return;
    }
    const index = this.help.index;
    const mission = this.battle.map.mission ?? 0;
    if (index >= HELP_TIPS.length || (HELP_TIPS[index] === "support" && mission < SUPPORT_TIP_FROM)) {
      return;
    }
    const panel = this.hud.clip.child("help").child(HELP_TIPS[index]);
    panel.alpha = 0;
    panel.visible = true;
    tweens.alphaTo(panel, 100, HELP_FADE, EASE);
    tweens.alphaTo(panel, 0, HELP_FADE, EASE, HELP_SECONDS, () => {
      panel.visible = false;
    });
    this.help = { ...this.help, index: index + 1 };
    this.countdown = HELP_COUNTDOWN;
    saveHelp(this.help);
  }

  // ---------- The in-battle menu ----------

  // loadInGameMenu (F5:6568-6601): a solo battle pauses while the menu is up; a versus battle and a watcher's keep
  // running. The sound buttons show what is on
  openMenu() {
    const battle = this.battle;
    if (!battle || this.menu || !this.hud.clip) {
      return;
    }
    const pauses = battle.you !== null && battle.kind !== "versus";
    if (pauses && !this.page.send({ pause: true })) {
      this.page.toast(NOT_CONNECTED);
      return;
    }
    const holder = this.hud.clip.attach(this.page.lib.makeExported("inGameMenu"), "inGameMenu");
    holder.position.set(MENU_X, MENU_Y);
    this.menu = { holder, pauses, closing: false };
    this.hideQuality(holder);
    const backing = holder.child("backing");
    backing.useHandCursor = false;
    backing.setHandler("onRelease", () => {});
    tweens.alphaTo(backing, MENU_BACKING, MENU_FADE);
    this.wireMenuButtons(holder);
    const on = sound.effectsOn();
    this.pick(holder.child(on ? "sound_on" : "sound_off"));
    if (battle.you === null) {
      holder.child("quitBattle").visible = false;
    }
  }

  // The Visual Quality row is gone (spec 8.1): its label and its three buttons stay hidden
  hideQuality(holder) {
    for (const name of ["low", "medium", "high"]) {
      holder.child(name).visible = false;
    }
    for (const slot of holder.slots.values()) {
      if (slot.node.charId === QUALITY_LABEL) {
        slot.node.visible = false;
      }
    }
  }

  // buttonSetup_inGameMenu (F5:6623-6692) for each button that is left
  wireMenuButtons(holder) {
    for (const [name, words] of Object.entries(MENU_WORDS)) {
      const button = holder.child(name);
      button.child("buttonText").text = words;
      button.activated = false;
      button.setHandler("onRollOver", () => {
        sound.play(ROLL_OVER);
        tweens.colorTransformTo(button, ...HOVER, 0.4, EASE);
      });
      button.setHandler("onRollOut", () => {
        if (!button.activated) {
          tweens.colorTransformTo(button, ...NORMAL, 0.4, EASE);
        }
      });
      button.setHandler("onRelease", () => {
        sound.play(CLICK);
        this.menuPress(name, holder);
      });
    }
  }

  // A sound button lit as the chosen one
  pick(button) {
    button.activated = true;
    tweens.colorTransformTo(button, ...HOVER, 0.4, EASE);
  }

  unpick(button) {
    button.activated = false;
    tweens.colorTransformTo(button, ...NORMAL, 0.4, EASE);
  }

  menuPress(name, holder) {
    if (this.menu?.closing) {
      return;
    }
    switch (name) {
      case "sound_on":
      case "sound_off": {
        const on = name === "sound_on";
        sound.setEffects(on);
        this.pick(holder.child(name));
        this.unpick(holder.child(on ? "sound_off" : "sound_on"));
        break;
      }
      case "quitBattle":
        this.page.send({ surrender: true });
        this.closeMenu(false);
        break;
      case "quitToMenu":
        this.quitToMenu();
        break;
      default:
        this.closeMenu(this.menu.pauses);
    }
  }

  // hideInGameMenu (F5:6602-6615): the menu fades over a second, and the battle goes on when it is gone. Quit Battle
  // does not ask the bot to resume, since the surrender does that
  closeMenu(resume) {
    const menu = this.menu;
    menu.closing = true;
    tweens.alphaTo(menu.holder, 0, MENU_FADE, LINEAR, 0, () => {
      menu.holder.destroy({ children: true });
      if (this.menu === menu) {
        this.menu = null;
      }
      if (resume) {
        this.page.send({ pause: false });
      }
    });
  }

  // Quit to Main Menu (F5:6676-6683): the battle is gone with no result, and the main menu comes up
  quitToMenu() {
    // A watcher leaves the battle's audience; a player ends the battle
    this.page.send(this.battle.you !== null ? { quit: true } : { unwatch: true });
    sound.stopAll();
    this.page.battle = null;
    this.page.show("main");
  }

  // ---------- Each drawn moment ----------

  draw() {
    if (!this.interactive || !this.world) {
      return;
    }
    const { a } = this.field.around();
    const state = a.s;
    const squads = new Map(state.q.map((row) => [row[0], row]));
    for (const entry of this.trenches) {
      this.paintTrench(entry, state.t[entry.index], squads);
    }
    this.paintGas(Boolean(state.h[this.side][2]));
  }
}
