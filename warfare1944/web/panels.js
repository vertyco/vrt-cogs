// The battle's panels over the field and the HUD: the help tips (setupHelp and showHelp F6:9604-9659) and the
// in-battle menu (loadInGameMenu, hideInGameMenu and buttonSetup_inGameMenu F6:9479-9603).
//
// The bot decides everything. The page draws what each update says and sends only requests: pause and resume,
// surrender, quit. A watcher presses none of these.
import { Rectangle } from "./vendor/pixi.min.mjs";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const EASE = "easeOutSine";
const LINEAR = "linear";
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const NOT_CONNECTED = "Not connected. Try again in a moment.";
const HOVER = [220, 0, 220, 0, 220, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// The help panels in the original's order (helpArray), shown one at a time
const HELP_KEY = "warfare1944:help";
const HELP_TIPS = ["progressBar", "morale", "upgrades", "support"];
const HELP_COUNTDOWN = 4;
const HELP_SECONDS = 30;
const HELP_FADE = 0.8;
const HELP_CLOSE_FADE = 0.6;
// The INTEL panel tip waits for mission 2, when squads first have orders
const SUPPORT_TIP_FROM = 2;
const HELP_WORDS = {
  unitHelp: [
    "CREATE UNITS HERE",
    "Click the portraits to create units. Deploying units cost resource points and will need time to resupply.",
  ],
  progressBar: [
    "GROUND TAKEN",
    "This bar shows ground taken. Move your men to the center of the enemy's end of the battlefield to win.",
  ],
  morale: [
    "MORALE BAR",
    "Seeing men die around them will make your army lose morale. Lose enough morale and your army may surrender.",
  ],
  upgrades: [
    "UPGRADES",
    "Killing enemies and winning battles will earn you XP. Earn enough XP and you'll be awarded an upgrade point.",
  ],
  support: ["INTEL PANEL", "Use HotKeys 1 - 4 to activate these abilities."],
};
// The in-battle menu sits in the middle of the stage, 25 above centre (loadInGameMenu, F6:9482-9484)
const MENU_X = 400;
const MENU_Y = 225;
const MENU_BACKING = 60;
const MENU_FADE = 1;
const QUALITY_LABEL = 1427;
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
    console.warn("Warfare 1944: couldn't read the help tips' progress", e);
  }
  return { index: 0, enabled: true };
}

function saveHelp(help) {
  try {
    localStorage.setItem(HELP_KEY, JSON.stringify(help));
  } catch (e) {
    console.warn("Warfare 1944: couldn't save the help tips' progress", e);
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
    this.menu = null;
    this.help = readHelp();
    // Deploys left before the next tip (helpCountdown, F6:11792-11793). It starts over each time the page opens
    this.countdown = HELP_COUNTDOWN;
    field.onLoad((battle) => this.load(battle));
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
    return ["inGameMenu"];
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
    if (!this.interactive) {
      this.hud.clip.child("help").visible = false;
      return;
    }
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
    Object.assign(this, { world: null, battle: null, menu: null });
  }

  // ---------- Help tips ----------

  // setupHelp (F6:9604-9638): the first tip is up from the first battle and the others wait for their turn
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

  // showHelp (F6:9639-9659), called on each deploy: every 4th one brings the next tip up for 30 seconds
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

  // loadInGameMenu (F6:9479-9525): a solo battle pauses while the menu is up; a versus battle and a watcher's keep
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

  // buttonSetup_inGameMenu (F6:9526-9603) for each button that is left
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

  // hideInGameMenu (F6:9503-9515): the menu fades over a second, and the battle goes on when it is gone. Quit Battle
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

  // Quit to Main Menu (F6:9583-9591): the battle is gone with no result, and the main menu comes up
  quitToMenu() {
    // A watcher leaves the battle's audience; a player ends the battle
    this.page.send(this.battle.you !== null ? { quit: true } : { unwatch: true });
    sound.stopAll();
    this.page.battle = null;
    this.page.show("main");
  }
}
