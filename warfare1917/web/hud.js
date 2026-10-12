// The battle's HUD and top bars: the six unit portraits with their timer dials, the four fire support slots and the red
// ground target, the Upgrades dial, the Menu button, the ground-taken and morale bars with their tooltip, and the
// tooltips (buildGameInterface F5:3721-3733, setupProgressBar and updateProgressBar F5:3790-3869, checkUnitNames
// F5:3870-3884, buttonSetup and buttonTimer F5:3885-4025, buttonSetup_fireSupport and buttonTimer_supportButtons
// F5:4026-4154, updateMoraleBar F5:5674-5735, updateExperience and setupInterfaceExperience F5:5969-6097).
//
// The bot runs every timer, ground and morale number. The page draws what each update says: the dials fill from the
// fills in the update (state "h"), the bars from "f" and "m". A press only asks the bot: a deploy sends the slot, a fire
// support sends the slot and the field x of the red target, and the dials start over when the bot's next update says
// so. The HUD shows the side the viewer plays, or the side a watcher watches, and a watcher presses nothing.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { openUpgrades } from "./upgrades.js";

const DEPTH_HUD = 900000;
const EASE = "easeOutSine";
const LINEAR = "linear";
const UNIT_SLOTS = 6;
const SUPPORT_SLOTS = 4;
// A dial that is full is ready. The bot's fills run 0 to 1000
const FULL = 1000;
const HALF = FULL / 2;
// A dial is two half discs: the right one turns from -180 to 0 over the first half of the wait, the left one from 0 to
// 180 over the second (buttonTimer F5:3989-4006)
const HALF_TURN = 180;
const DIAL_START = -179;
// The colors the slots flash as they fill or empty (F5:3897, 4000)
const READY_FLASH = 12566199;
const CHARGED_FLASH = 10460563;
const HIGHLIGHT_READY = 55;
const HIGHLIGHT_HOVER = 95;
// A press waits this long for the bot's word that it took, then the dials draw what the bot says again
const ASK_WAIT_MS = 2000;
// The tooltip follows the pointer, 10 right and 30 up, and flips to the left past x 750 (the placement script of 1492)
const TIP_OFFSET_X = 10;
const TIP_OFFSET_Y = -30;
const TIP_FLIP_X = 750;
const TIP_FLIP_SHIFT = -100;
const TIP_MARGIN = 20;
const TIP_HEADER_MARGIN = 10;
// The red ground target stands on the ground line 60 below the ground (F5:4080-4107)
const GROUND = 170;
const TARGET_OFFSET_Y = 60;
const TARGET_DEPTH = 900000;
const TARGET_FADE_SECONDS = 8;
const TARGET_FLASH = 16777215;
// A finger resting on a slot lifts the tooltip this many screen pixels higher, so the finger doesn't cover it
const TIP_FINGER_LIFT_PX = 44;
const HUD_TOP = 340;
// updateMoraleBar's colors (F5:5711-5731)
const MORALE_LOW = 3342336;
const MORALE_LOW_AT = 35;
const MORALE_BREAKING = 10027008;
const MORALE_BREAKING_AT = 15;
const MORALE_OK_AT = 30;
const BAR_SLIDE_SECONDS = 5;
const LEVELS = [
  15, 45, 90, 150, 225, 315, 420, 540, 675, 825, 990, 1170, 1390, 1615, 1855, 2110, 2880, 3165, 3465,
];
// What the tooltips of the six unit slots and four fire support slots say (F5:7310-7339, 7363-7390). The names of
// slots 2, 3 and 6 change with the side (checkUnitNames)
const UNITS = [
  { name: "Riflemen", desc: "Good vs Infantry. \rWeak vs Armor." },
  { name: "Assault Team", german: "Sturmtruppen", desc: "Strong vs Entrenched.\rAverage vs Armor." },
  { name: "Lewis Gunners", german: "Machine Gun Team", desc: "Good vs Infantry \rwhen entrenched." },
  { name: "Sharpshooter", desc: "Strong vs Infantry \rat long range." },
  { name: "Officer", desc: "Adds morale. \rDamage bonus to soldiers." },
  { name: "Mark IV Tank", german: "A7V Tank", desc: "Strong vs All. Weak vs Fire support." },
];
const SUPPORTS = [
  { name: "Mortar Strike", desc: "Medium explosive.\rGood vs exposed infantry." },
  { name: "Artillery Strike", desc: "Heavy bombardment.\rGood vs All units." },
  { name: "Gas", desc: "Poison gas attack.\rGood vs Infantry." },
  { name: "Anti-Tank", desc: "Anti-tank cannon.\rDirect fire." },
];
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";

// A dial's right and left half discs for a fill of 0 to 1000
function dialTurns(fill) {
  if (fill <= HALF) {
    return [-HALF_TURN + (fill / HALF) * HALF_TURN, 0];
  }
  return [0, ((fill - HALF) / HALF) * HALF_TURN];
}

// A fill drawn between two updates: it climbs smoothly toward the next one, and a drop (a timer that started over)
// waits for the update that holds it
function smoothFill(now, next, t) {
  return next >= now && next < FULL ? now + (next - now) * t : now;
}

export class Hud {
  constructor(field) {
    this.field = field;
    this.clip = null;
    this.world = null;
    this.side = "british";
    this.battle = null;
    // The unit slots, then the fire support slots: { name, index, clip, icon, ..., unlocked, ready, waiting }
    this.units = [];
    this.supports = [];
    this.tip = null;
    // The red ground target waiting for the player to fire it: { clip, entry } or null
    this.target = null;
    this.targets = 0;
    // The ground and morale numbers drawn last, so a bar slides only when its number moves
    this.last = null;
    this.xp = { points: 0, level: 0, xp: 0 };
    // Where the last press on the stage went down, to tell a tap from a drag
    this.downAt = null;
    // Set by the panels: called when the Menu button is pressed, and after each deploy the bot may take
    this.onMenu = null;
    this.onDeploy = null;
    this.stageListeners = [];
    field.onLoad((battle) => this.load(battle));
    field.onDraw(() => this.draw());
    field.onClear(() => this.reset());
    field.onEvent("xp", (event) => this.gainXp(event[4]));
  }

  get page() {
    return this.field.page;
  }

  // True when the viewer plays and so may press the HUD
  get interactive() {
    return Boolean(this.battle) && this.battle.you !== null;
  }

  // The clips this module attaches, loaded with the battlefield's
  static art() {
    return ["hud", "interface_groundTarget"];
  }

  // ---------- Building ----------

  load(battle) {
    this.battle = battle;
    if (this.world === this.field.world) {
      // A rejoin: the bars settle where the bot says at once
      this.last = null;
      return;
    }
    this.reset();
    this.battle = battle;
    this.world = this.field.world;
    this.side = battle.you ?? battle.map.side;
    this.last = null;
    this.clip = this.page.attach("hud", DEPTH_HUD, "hud");
    this.setupParts();
    this.setupExperience(battle);
    this.setupBars();
    this.units = Array.from({ length: UNIT_SLOTS }, (_, index) => this.setupUnit(index, battle.units[this.side][index]));
    this.supports = Array.from({ length: SUPPORT_SLOTS }, (_, index) =>
      this.setupSupport(index, battle.supports[this.side][index]),
    );
    this.listenToStage();
  }

  reset() {
    this.disarm();
    for (const [name, fn] of this.stageListeners) {
      this.page.app?.stage.off(name, fn);
    }
    this.stageListeners = [];
    this.page.detach("hud");
    Object.assign(this, { clip: null, world: null, battle: null, units: [], supports: [], tip: null, last: null });
  }

  // The hud clip's own parts: the side's frames, the tooltips hidden until they are wanted, the Menu button, and the
  // help panels, which panels.js shows when a player's battle is built
  setupParts() {
    const clip = this.clip;
    clip.child("hudBG").gotoAndStop(this.side);
    clip.child("progressBar").child("casing").gotoAndStop(this.side);
    clip.child("progressBarToolTip").visible = false;
    clip.child("help").visible = false;
    this.tip = clip.child("toolTip");
    this.tip.visible = false;
    for (const name of ["header", "desc"]) {
      const field = this.tip.child(name);
      field.anchor = { x: field.x, box: field.box.x };
      field.autoSizeCenter(name === "desc");
    }
    this.setupMenuButton(clip.child("menuButton"));
  }

  // buttonSetup_hudMenuButton (F5:606-622)
  setupMenuButton(button) {
    button.setHandler("onRollOver", () => {
      sound.play(ROLL_OVER);
      tweens.colorTransformTo(button, 220, 0, 220, 0, 220, 0, 100, 0, 0.4, EASE);
    });
    button.setHandler("onRollOut", () => tweens.colorTransformTo(button, 100, 0, 100, 0, 100, 0, 100, 0, 0.4, EASE));
    button.setHandler("onRelease", () => {
      sound.play(CLICK);
      this.onMenu?.();
    });
  }

  // The dial's placement script (1401): its full block starts hidden
  hideBlock(slot) {
    slot.child("fullBlock").visible = false;
  }

  // buttonSetup (F5:3885-3963) for one portrait slot. A slot the mission allows starts ready; the others show their
  // padlock and no picture
  setupUnit(index, allowed) {
    const clip = this.clip;
    const number = index + 1;
    const entry = {
      kind: "unit",
      index,
      clip: clip.child(`slot${number}`),
      highlight: clip.child(`highlight_slot${number}`),
      lock: clip.child(`lock_slot${number}`),
      icon: clip.child(`icon_slot${number}`),
      unlocked: allowed,
      ready: allowed,
      waiting: 0,
    };
    this.hideBlock(entry.clip);
    entry.highlight.alpha = 0;
    entry.icon.gotoAndStop(this.side);
    entry.picture = entry.icon.child("icon");
    entry.picture.alpha = 0;
    entry.clip.child("rightDial").angle = -HALF_TURN;
    entry.clip.alpha = 0;
    if (allowed) {
      entry.lock.alpha = 0;
      entry.picture.alpha = 1;
      entry.picture.gotoAndStop("colour");
      tweens.alphaTo(entry.highlight, HIGHLIGHT_READY, 0);
      tweens.colorTo(entry.clip, READY_FLASH, 0.5, LINEAR);
      tweens.alphaTo(entry.clip, 0, 0.3, LINEAR, 0.4);
    }
    this.setupSlotHandlers(entry, UNITS[index]);
    return entry;
  }

  // buttonSetup_fireSupport (F5:4026-4115) for one slot. A slot that is not allowed keeps its padlock and no picture
  setupSupport(index, allowed) {
    const clip = this.clip;
    const number = index + 1;
    const entry = {
      kind: "support",
      index,
      clip: clip.child(`supportSlot${number}`),
      highlight: null,
      lock: clip.child(`lock_supportSlot${number}`),
      icon: clip.child(`icon_supportSlot${number}`),
      unlocked: allowed,
      ready: false,
      waiting: 0,
    };
    entry.picture = entry.icon;
    this.hideBlock(entry.clip);
    entry.clip.child("rightDial").angle = -HALF_TURN;
    entry.icon.visible = allowed;
    if (allowed) {
      entry.lock.alpha = 0;
    }
    this.setupSlotHandlers(entry, SUPPORTS[index]);
    return entry;
  }

  setupSlotHandlers(entry, words) {
    const clip = entry.clip;
    clip.useHandCursor = false;
    clip.setHandler("onRollOver", () => this.slotOver(entry, words));
    clip.setHandler("onRollOut", () => this.slotOut(entry));
    for (const name of ["onPress", "onRelease", "onReleaseOutside"]) {
      clip.setHandler(name, (e) => this.press(entry, e));
    }
  }

  // ---------- Tooltips ----------

  // The tooltip over a slot: its name and words come up after half a second. A slot that isn't allowed has none
  slotOver(entry, words) {
    if (!entry.unlocked) {
      return;
    }
    const name = (this.side === "german" && words.german) || words.name;
    this.showTip(name, words.desc, 0.5);
    if (entry.ready && this.interactive) {
      entry.clip.useHandCursor = true;
      this.glow(entry, HIGHLIGHT_HOVER, 0.8);
    }
  }

  slotOut(entry) {
    tweens.stopTween(this.tip);
    tweens.alphaTo(this.tip, 0, 0.2);
    entry.clip.useHandCursor = false;
    if (entry.ready && entry.unlocked && this.interactive) {
      this.glow(entry, HIGHLIGHT_READY, 0.8);
    }
  }

  glow(entry, alpha, seconds) {
    if (entry.highlight) {
      tweens.alphaTo(entry.highlight, alpha, seconds);
    }
  }

  // The tooltip is sized to its words: the backing is 20 wider and taller than the description, or 10 wider than the
  // heading when that is the wider
  showTip(header, desc, delay) {
    const tip = this.tip;
    const [head, words, backing] = [tip.child("header"), tip.child("desc"), tip.child("backing")];
    this.setTipText(head, header);
    this.setTipText(words, desc);
    const width = words.box.width <= head.box.width ? head.box.width + TIP_HEADER_MARGIN : words.box.width + TIP_MARGIN;
    backing.scale.set(1);
    const size = backing.getLocalBounds();
    backing.scale.set(width / size.width, (words.box.height + TIP_MARGIN) / size.height);
    tip.alpha = 0;
    tip.visible = true;
    this.placeTip();
    tweens.alphaTo(tip, 100, 0.4, EASE, delay);
  }

  // A field that grows to its words from its left edge, as autoSize "left" does
  setTipText(field, text) {
    field.text = text;
    field.x = field.anchor.x + field.anchor.box - field.box.x;
  }

  placeTip() {
    const pointer = this.field.pointer;
    this.tip.x = pointer.x > TIP_FLIP_X ? pointer.x + TIP_FLIP_SHIFT : pointer.x + TIP_OFFSET_X;
    this.tip.y = pointer.y + TIP_OFFSET_Y - (pointer.touch ? TIP_FINGER_LIFT_PX / this.page.world.scale.x : 0);
  }

  // ---------- Deploying and calling fire support ----------

  // The press of a slot (onPress, onRelease and onReleaseOutside all do the same): a ready slot asks the bot, and
  // every dial it empties starts over on the page at once. A fire support slot puts out the red target instead
  press(entry, e) {
    const now = performance.now();
    if (!this.interactive || !entry.unlocked || !entry.ready || now < entry.waiting) {
      return;
    }
    if (entry.kind === "support") {
      if (this.target?.entry !== entry) {
        this.arm(entry, e);
      }
      return;
    }
    if (this.page.send({ deploy: entry.index + 1 })) {
      for (const unit of this.units.filter((one) => one.unlocked)) {
        this.discharge(unit);
        unit.waiting = now + ASK_WAIT_MS;
      }
      this.onDeploy?.();
    }
  }

  // The red target (interface_groundTarget) follows the pointer along the ground line and is pressed to fire. A touch
  // has no pointer to follow: the target stays hidden until a tap on the ground puts it down
  arm(entry, e) {
    this.disarm();
    const layer = this.field.layer("target");
    if (!layer) {
      return;
    }
    const clip = this.page.lib.makeExported("interface_groundTarget");
    this.targets += 1;
    clip.zIndex = TARGET_DEPTH + this.targets;
    const scale = this.page.world.scale.x;
    clip.position.set(this.field.toField(e.global.x / scale, 0).x, GROUND + TARGET_OFFSET_Y);
    clip.visible = e.pointerType !== "touch";
    layer.addChild(clip);
    clip.setHandler("onPress", (e) => {
      this.downAt = { x: e.global.x, y: e.global.y };
    });
    clip.setHandler("onRelease", (e) => this.fire(entry, clip, e));
    this.target = { clip, entry };
  }

  disarm() {
    if (this.target) {
      this.target.clip.destroy({ children: true });
      this.target = null;
    }
  }

  // launchSpecialAttack's call (F5:4091-4106): the strike is asked of the bot at the target's x. The target flashes
  // and fades away over 8 seconds, and that slot starts over
  fire(entry, clip, e) {
    if (!this.interactive || this.target?.clip !== clip || this.dragged(e)) {
      return;
    }
    const width = this.battle.map.width;
    const x = Math.round(Math.min(Math.max(clip.x, 0), width) * 10) / 10;
    if (!this.page.send({ support: [entry.index + 1, x] })) {
      return;
    }
    this.target = null;
    clip.setHandler("onRelease", null);
    tweens.colorTo(clip, TARGET_FLASH, 0.5, LINEAR);
    tweens.colorTo(clip, null, 0.5, LINEAR, 0.5);
    tweens.alphaTo(clip, 0, TARGET_FADE_SECONDS, LINEAR, 0, () => clip.destroy({ children: true }));
    this.discharge(entry);
    entry.waiting = performance.now() + ASK_WAIT_MS;
  }

  // On a touch screen a tap on the ground (not on the target, not a drag) puts the target down there
  listenToStage() {
    const stage = this.page.app.stage;
    const down = (e) => {
      this.downAt = { x: e.global.x, y: e.global.y };
    };
    const up = (e) => this.tapped(e);
    stage.on("pointerdown", down);
    stage.on("pointerup", up);
    this.stageListeners = [
      ["pointerdown", down],
      ["pointerup", up],
    ];
  }

  tapped(e) {
    const target = this.target;
    if (!target || e.pointerType !== "touch" || e.target === target.clip || this.dragged(e)) {
      return;
    }
    const scale = this.page.world.scale.x;
    const at = { x: e.global.x / scale, y: e.global.y / scale };
    if (at.y > HUD_TOP) {
      return;
    }
    target.clip.x = this.field.toField(at.x, at.y).x;
    target.clip.visible = true;
  }

  // True when the press now ending moved far enough to be a drag that scrolls the field, not a tap
  dragged(e) {
    const scale = this.page.world.scale.x;
    const from = this.downAt;
    return !from || Math.hypot(e.global.x - from.x, e.global.y - from.y) / scale > this.field.slop();
  }

  // ---------- The dials ----------

  // resetButtonTimers and resetSupportButtonTimers (F5:4009-4025, 4144-4154): the slot goes dark and starts to fill
  discharge(entry) {
    entry.ready = false;
    tweens.stopTween(entry.clip);
    entry.picture.gotoAndStop("bw");
    this.glow(entry, 0, 0.8);
    tweens.alphaTo(entry.clip, 100, 0.1, LINEAR);
    tweens.colorTo(entry.clip, null, 0.1, LINEAR);
    this.turnDial(entry, DIAL_START, 0);
  }

  // The end of buttonTimer and buttonTimer_supportButtons (F5:3990-4006, 4125-4142): the slot lights and is ready
  charge(entry) {
    entry.ready = true;
    this.turnDial(entry, 0, HALF_TURN);
    entry.picture.gotoAndStop("colour");
    if (entry.kind === "unit") {
      tweens.alphaTo(entry.highlight, HIGHLIGHT_READY, 0.3, LINEAR, 0.5);
    }
    tweens.colorTo(entry.clip, CHARGED_FLASH, 0.5, LINEAR);
    tweens.alphaTo(entry.clip, 0, 0.3, LINEAR, 0.4);
  }

  turnDial(entry, right, left) {
    entry.clip.child("rightDial").angle = right;
    entry.clip.child("leftDial").angle = left;
  }

  // One slot for the drawn moment: ready or not as the bot's fill says, and the dial turned to it. A slot waiting on
  // the bot's word that a press took keeps its empty dial until the fill shows it, or the wait runs out
  paintSlot(entry, now, next, t) {
    if (!entry.unlocked) {
      return;
    }
    if (entry.waiting) {
      if (now < FULL || performance.now() > entry.waiting) {
        entry.waiting = 0;
      } else {
        return;
      }
    }
    if (now >= FULL) {
      if (!entry.ready) {
        this.charge(entry);
      }
      return;
    }
    if (entry.ready) {
      this.discharge(entry);
    }
    const [right, left] = dialTurns(smoothFill(now, next, t));
    this.turnDial(entry, right, left);
  }

  // ---------- The bars ----------

  // setupProgressBar (F5:3790-3806): the tooltip with both sides' ground and morale fades in over the bars
  setupBars() {
    const bar = this.clip.child("progressBar");
    const tip = this.clip.child("progressBarToolTip");
    bar.setHandler("onRollOver", () => {
      tip.alpha = 0;
      tip.visible = true;
      tweens.alphaTo(tip, 100, 0.6);
    });
    bar.setHandler("onRollOut", () => {
      tweens.alphaTo(tip, 0, 0.6, EASE, 0, () => {
        tip.visible = false;
      });
    });
  }

  // updateProgressBar's numbers (F5:3850-3868): the British ground is the left bar and the German ground the right,
  // whichever side the viewer plays. A bar slides to its number over 5 seconds, and goes straight there on a rejoin.
  // `f` is the bot's ground numbers, then whether each side has no front squad, then the slow ticks run so far: a side
  // with no front squad flashes its bar again on every slow tick, as the original's check does (F5:3827-3838).
  // Returns the numbers drawn
  paintGround(f) {
    const ground = [f[0], f[1]];
    const ticks = f[4];
    const bars = this.clip.child("progressBar");
    const tip = this.clip.child("progressBarToolTip");
    tip.child("britishGroundTaken").text = `${ground[0]}%`;
    tip.child("germanGroundTaken").text = `${ground[1]}%`;
    const pair = [bars.child("playerTeamProgBar"), bars.child("compTeamProgBar")];
    if (ticks !== this.last?.ticks) {
      pair.forEach((bar, index) => f[index + 2] && this.flashRed(bar));
    }
    const last = this.last?.ground;
    if (last && ground[0] === last[0] && ground[1] === last[1]) {
      return { ticks };
    }
    pair.forEach((bar, index) => {
      if (!last) {
        bar.scale.x = ground[index] / 100;
        return;
      }
      tweens.xScaleTo(bar, ground[index], BAR_SLIDE_SECONDS, EASE);
    });
    return { ground, ticks };
  }

  // A side with no front squad: the bar goes dark red and comes back (F5:3832-3838)
  flashRed(bar) {
    tweens.colorTo(bar, MORALE_LOW, 0.2);
    tweens.colorTo(bar, null, 2, EASE, 1);
  }

  // updateMoraleBar (F5:5692-5735): the two grey bars, in percent of each side's own maximum. Returns the numbers drawn
  paintMorale(m) {
    const morale = [0, 1].map((i) => Math.round((m[i] / (m[i + 2] || 1)) * 100));
    const tip = this.clip.child("progressBarToolTip");
    tip.child("britishMorale").text = `${morale[0]}%`;
    tip.child("germanMorale").text = `${morale[1]}%`;
    const last = this.last?.morale;
    if (last && morale[0] === last[0] && morale[1] === last[1]) {
      return {};
    }
    const bars = this.clip.child("progressBar");
    [bars.child("britishMoraleBar"), bars.child("germanMoraleBar")].forEach((bar, index) => {
      if (!last) {
        bar.scale.x = morale[index] / 100;
        return;
      }
      tweens.xScaleTo(bar, morale[index], BAR_SLIDE_SECONDS, LINEAR);
      this.tintMorale(bar, morale[index]);
    });
    return { morale };
  }

  // The bar reddens as morale drops, in the original's order: below 35 dark red, below 15 deep red, above 30 its own
  tintMorale(bar, value) {
    if (value <= MORALE_LOW_AT) {
      tweens.colorTo(bar, MORALE_LOW, 2);
    }
    if (value <= MORALE_BREAKING_AT) {
      tweens.colorTo(bar, MORALE_BREAKING, 2);
    }
    if (value > MORALE_OK_AT) {
      tweens.colorTo(bar, null, 2);
    }
  }

  // ---------- Experience ----------

  // setupInterfaceExperience (F5:6073-6097): the Upgrades dial from the save. It is the campaign player's; a custom or
  // versus battle and a watcher have none
  setupExperience(battle) {
    const dial = this.clip.child("upgrades");
    const save = this.page.save;
    if (battle.kind !== "campaign" || battle.you === null || !save) {
      dial.visible = false;
      this.xp = null;
      return;
    }
    this.xp = { points: save.points, level: save.level, xp: save.xp };
    const experience = dial.child("experience");
    this.hideBlock(experience);
    dial.child("upgradePointsText").text = save.points;
    const interval = LEVELS[save.level];
    if (interval === undefined) {
      this.turnExperience(0, HALF_TURN);
    } else {
      const turn = (360 * save.xp) / interval - HALF_TURN;
      this.turnExperience(Math.min(turn, 0), Math.max(0, turn));
    }
    dial.child("upgradeButton").setHandler("onRelease", () => {
      if (this.interactive) {
        openUpgrades({ inBattle: true });
      }
    });
  }

  turnExperience(right, left) {
    const experience = this.clip.child("upgrades").child("experience");
    experience.child("rightDial").angle = right;
    experience.child("leftDial").angle = left;
  }

  // updateExperience (F5:6035-6070): XP the bot awarded counts here as it comes. A level reached lights the dial and
  // the button and starts the dial over. The upgrade points themselves are the bot's word (setPoints): its save for
  // the level reaches the page before the kill plays out here, so counting the point again would show it twice
  gainXp(amount) {
    const xp = this.xp;
    if (!xp || !this.clip) {
      return;
    }
    xp.xp += amount;
    const dial = this.clip.child("upgrades");
    while (xp.level < LEVELS.length && xp.xp > LEVELS[xp.level]) {
      xp.level += 1;
      this.levelUp(dial);
    }
    const interval = LEVELS[xp.level];
    if (interval === undefined) {
      return;
    }
    const experience = dial.child("experience");
    const step = Math.round((HALF_TURN / (interval / 2)) * amount);
    let right = experience.child("rightDial").angle;
    let left = experience.child("leftDial").angle;
    if (right < 0) {
      right += step;
    }
    if (right >= 0) {
      left += step;
    }
    this.turnExperience(Math.min(right, 0), Math.min(left, HALF_TURN));
  }

  // The bot's save in a campaign battle: its points are the Upgrades dial's, so a purchase, or a level the bot has
  // counted, shows on the dial whatever order the saves came in
  setPoints(points) {
    if (!this.xp || !this.clip) {
      return;
    }
    this.xp.points = points;
    this.clip.child("upgrades").child("upgradePointsText").text = points;
  }

  levelUp(dial) {
    const white = dial.child("experience").child("whiteOut");
    const button = dial.child("upgradeButton");
    tweens.colorTo(white, 13030847, 0);
    tweens.alphaTo(white, 100, 1, EASE);
    tweens.alphaTo(white, 0, 2, EASE, 3);
    tweens.colorTransformTo(button, 220, 0, 220, 0, 220, 0, 100, 0, 1);
    tweens.colorTransformTo(button, 100, 0, 100, 0, 100, 0, 100, 0, 1, EASE, 2);
    this.turnExperience(-HALF_TURN, 0);
  }

  // ---------- Each drawn moment ----------

  // The state around the drawn clock: the dials fill from it, and the bars and tooltip numbers show it
  draw() {
    if (!this.clip || !this.battle) {
      return;
    }
    const { a, b, t } = this.field.around();
    this.update(a.s, b.s, t);
  }

  // The HUD for the state `now` the drawing has reached, sliding toward the next update `next` by t (0 to 1)
  update(now, next, t) {
    const own = this.side;
    const dials = now.h[own];
    const ahead = next.h[own];
    this.units.forEach((entry, index) => this.paintSlot(entry, dials[0][index], ahead[0][index], t));
    this.supports.forEach((entry, index) => this.paintSlot(entry, dials[1][index], ahead[1][index], t));
    const seen = { ...this.paintGround(now.f), ...this.paintMorale(now.m) };
    this.last = { ...this.last, ...seen };
    this.followTarget();
    if (this.tip.visible) {
      this.placeTip();
    }
  }

  // The target follows the pointer along the ground line; a touch puts it down by tapping, and leaves it there
  followTarget() {
    const target = this.target;
    const pointer = this.field.pointer;
    if (target && !pointer.touch) {
      target.clip.x = this.field.toField(pointer.x, pointer.y).x;
    }
  }
}
