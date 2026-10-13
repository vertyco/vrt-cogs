// Giving orders to a squad: pressing one of your soldiers selects its squad (soldierRollOvers F6:6106-6173), the INTEL
// panel shows its name, health, state and up to four order buttons (showUnitControls F6:6199-6399,
// updateSelectedUnitInfo F6:6508-6656, showIntelDeathMessage F6:6657-6671, clearIntelInterface F6:6672-6723), and an
// order that aims shows its range box, cursor and ground target (showFireSupportArea F6:6419-6507,
// cancelSpecialAttack F6:6501-6507). Keys 1 to 4 press the buttons (hotKeySetup F6:356-379).
//
// The bot checks every order: the squad is the player's, the button is unlocked and not greyed, the RP is there and the
// point is inside the box. The page only picks the squad, the button and the point, and draws what the bot's state says
// about the squad. Selecting, aiming and cancelling never reach the bot. A watcher and the other versus player never
// select a squad: only the player's own soldiers take the press.
//
// A mouse fires an aimed order with a click inside the box. A finger taps inside the box to put the red ground target
// down, and taps the target to fire. The INTEL panel's Cancel button ends deploying or aiming with nothing sent.
import { TextField } from "./flash.js";
import { Container, Graphics } from "./vendor/pixi.min.mjs";
import * as tweens from "./tween.js";
import { STATES } from "./units.js";

const SIDES = ["british", "german"];
const DEPTH_HUD = 900000;
const DEPTH_HUD_SUPPORT_CURSOR = 1050;
const EASE = "easeOutSine";
const INTEL_SLOTS = 4;
// Each slot of the eight unit kinds, by the slot number the squad rows carry (1 to 8): the INTEL panel's name for it
// on each side, the frame of the panel's picture, and its buttons, Advance first (common/data.py UNITS, F6:1566). The
// picture has no frame for the bazooka team or the tank, so theirs stays empty
const NAMES = {
  british: [
    "Riflemen",
    "Assault Team",
    ".30 cal Team",
    "Sniper",
    "Bazooka Team",
    "Mortar Team",
    "Lieutenant",
    "M4A1 Sherman Tank",
  ],
  german: [
    "Riflemen",
    "Assault Team",
    "MG34 Team",
    "Sharpshooter",
    "Panzershreck Team",
    "Mortar Team",
    "Officer",
    "Panzer III",
  ],
};
const PICTURES = ["riflemen", "assault", "machineGun", "sniper", "bazooka", "mortarTeam", "officer", "tank"];
const BUTTONS = [
  ["advance", "grenade", "smoke"],
  ["advance", "suppress", "grenade", "smoke"],
  ["advance", "suppress"],
  ["advance", "smoke"],
  ["advance"],
  ["advance", "smokeRounds"],
  ["advance", "airSupport", "artillery", "smoke"],
  [],
];
// The frame of an action slot for each button, and the words under the panel while the pointer is on it (the
// *_description lines, F6:11006-11012)
const FRAMES = {
  advance: "advance",
  grenade: "throwGrenade",
  smoke: "throwSmoke",
  suppress: "suppressingFire",
  artillery: "callArtillery",
  airSupport: "callAirSupport",
  smokeRounds: "smokeRounds",
};
const WORDS = {
  advance: "Advance",
  artillery: "Call Artillery Strike - 500 RP",
  airSupport: "Call Air Support - 300 RP",
  grenade: "Throw Grenade - 50 RP",
  smoke: "Throw Smoke Grenade - 50 RP",
  suppress: "Suppressing Fire",
  smokeRounds: "Smoke Mortar Rounds - 100 RP",
};
const SMOKE_COST = 50;
// What "In cover behind ..." calls each cover (the cover_* descriptions, F6:10783-10829)
const COVER_WORDS = {
  stoneWall: "stone wall",
  woodFence: "wood fence",
  logPile: "log pile",
  sandBags: "sandbags",
  sandBagsUS: "sandbagsUS",
  barrels: "barrels",
  hedgerow: "hedgerow",
  rubble1: "rubble",
  rubble2: "rubble",
  urban1: "barricade",
  urban2: "barricade",
  sandDune: "sand dune",
  woodFenceOvergrown: "wood fence",
  headstones: "headstones",
  townWall: "stone wall",
  sandBagsUrban: "sandbags",
  sandBagsUrban_german: "sandbags",
};
// A squad row's flag bits: every member is in its cover and Advance is allowed (bit 3), and the squad has an enemy
// squad it is engaging (bit 7)
const IN_COVER_FLAG = 8;
const TARGET_FLAG = 128;
// updateSelectedUnitInfo's health words (F6:6513-6530): over 60 healthy, 36 to 59 taking casualties, 35 and under
// needing support. A squad at exactly 60 gets none, and its panel keeps the colour it had
const HEALTHY_OVER = 60;
const CASUALTIES_FROM = 36;
const CASUALTIES_TO = 59;
const NEEDS_SUPPORT_UNDER = 35;
const AMBER = 15325829;
const RED = 7416872;
// The fire support range box (specialAttackRange, F6:6419-6424): 2,500 wide, centred on the squad's leader, drawn at y
// 240. The smoke grenade's (sprite 1891) is its own size, centred on the leader
const SUPPORT_WIDTH = 2500;
const SUPPORT_Y = 240;
// The cursor goes dim and red outside the box (F6:6451-6458), and the ground target is put down where a finger taps
const CURSOR_OUT_ALPHA = 0.5;
const CURSOR_OUT_COLOR = 10027008;
// A pressed button's colour lift on rolling over it, and the ease (F6:6304)
const HOVER = [150, 0, 150, 0, 150, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// The Cancel button in the INTEL panel, beside the four slots (panel pixels from the panel's corner)
const CANCEL_BOX = { x: 176, y: 6, width: 40, height: 26 };
const CANCEL_FILL = 0x1d241b;
const CANCEL_EDGE = 0x6d7a5c;
const CANCEL_HOVER = 0x2f3a2b;
// The keys that press the panel's buttons: 1 to 4 (F6:356-379)
const KEYS = ["1", "2", "3", "4"];
const TOUCH = "touch";

// The percent a squad's health shows as, and the words and colour that go with it
function healthLine(percent) {
  if (percent > HEALTHY_OVER) {
    return { words: "Healthy.", color: null };
  }
  if (percent >= CASUALTIES_FROM && percent <= CASUALTIES_TO) {
    return { words: "Taking casualties.", color: AMBER };
  }
  if (percent <= NEEDS_SUPPORT_UNDER) {
    return { words: "Needs support.", color: RED };
  }
  return { words: "", color: undefined };
}

export class Orders {
  constructor(field, hud) {
    this.field = field;
    this.hud = hud;
    this.world = null;
    this.battle = null;
    this.intel = null;
    // The squad selected (its id) or null, and the four action slots: { action, disabled } or null for an empty one
    this.selected = null;
    this.buttons = [];
    // What the panel shows now, so a word or colour is drawn only when it changes
    this.shown = {};
    // The buttons the player's side has unlocked
    this.unlocked = new Set();
    // The order being aimed: { id, button, leader (member id), box, cursor, target, inside, down }, or null
    this.aim = null;
    this.cancelButton = null;
    this.touchDown = null;
    field.onLoad((battle) => this.load(battle));
    field.onDraw(() => this.draw());
    field.onClear(() => this.reset());
    field.onEvent("gone", (event) => this.gone(event[2]));
    field.units.onSelect((squadId) => this.select(squadId));
    document.addEventListener("keydown", (e) => this.keyDown(e));
  }

  get page() {
    return this.field.page;
  }

  // True when the viewer plays and so may give orders
  get interactive() {
    return Boolean(this.battle) && this.battle.you !== null;
  }

  // True while an order waits for its point
  get aiming() {
    return this.aim !== null;
  }

  // True when an order may go to the bot now: not a watcher, not paused or over, not under the in-battle menu
  get ready() {
    return this.interactive && !this.field.paused && !this.field.ending && !this.field.panels.menu;
  }

  // The clips this module attaches, loaded with the battlefield's
  static art() {
    return ["specialAttackRange", "specialAttackRange_smokeGrenade", "cursorSupport", "interface_groundTarget"];
  }

  // ---------- Building ----------

  load(battle) {
    this.battle = battle;
    if (this.world === this.field.world) {
      return;
    }
    this.reset();
    this.battle = battle;
    this.world = this.field.world;
    this.intel = this.hud.clip?.child("intel") ?? null;
    if (!this.interactive || !this.intel) {
      return;
    }
    this.unlocked = new Set(battle.orders[battle.you]);
    this.setupSlots();
    this.setupBackground();
    this.setupCancel();
  }

  reset() {
    this.cancelAim();
    if (this.cancelButton && !this.cancelButton.destroyed) {
      this.cancelButton.destroy({ children: true });
    }
    Object.assign(this, { world: null, battle: null, intel: null, selected: null, buttons: [], shown: {} });
    Object.assign(this, { unlocked: new Set(), cancelButton: null, touchDown: null });
  }

  // The four action slots take the pointer for whatever button they hold now (setupUnitControls, F6:6196)
  setupSlots() {
    for (let index = 0; index < INTEL_SLOTS; index += 1) {
      const slot = this.intel.child(`actionSlot${index}`);
      slot.useHandCursor = false;
      slot.setHandler("onRollOver", () => this.slotOver(index));
      slot.setHandler("onRollOut", () => this.slotOut(index));
      slot.setHandler("onPress", () => this.press(index));
    }
  }

  // The field's background lets go of the squad (world.bg.onPress, F6:7279-7282). A finger lets go on its lift, unless
  // the press scrolled the field
  setupBackground() {
    const background = this.world.child("bg");
    if (!background) {
      return;
    }
    background.useHandCursor = false;
    background.setHandler("onPress", (e) => {
      if (e.pointerType !== TOUCH) {
        this.deselect();
        return;
      }
      this.touchDown = { x: e.global.x, y: e.global.y };
    });
    background.setHandler("onRelease", (e) => {
      if (e.pointerType === TOUCH && this.touchDown && !this.field.swept(this.touchDown, e)) {
        this.deselect();
      }
      this.touchDown = null;
    });
  }

  // The INTEL panel's Cancel button, shown while a unit is being deployed or an order aimed
  setupCancel() {
    const { x, y, width, height } = CANCEL_BOX;
    const button = new Graphics();
    const paint = (fill) => {
      button.clear();
      button.roundRect(0, 0, width, height, 4).fill(fill).stroke({ width: 1, color: CANCEL_EDGE });
    };
    paint(CANCEL_FILL);
    const text = new TextField({
      ...this.intel.child("unitState").def,
      bounds: [0, 0, width, height],
      align: "center",
      html: null,
      var: "",
      wrap: false,
      multiline: false,
      text: "Cancel",
    });
    text.position.set(0, 5);
    text.draw();
    const holder = this.intel.attach(new Container(), "cancelButton");
    holder.addChild(button, text);
    holder.position.set(x, y);
    holder.visible = false;
    holder.eventMode = "static";
    holder.cursor = "pointer";
    holder.on("pointerover", () => paint(CANCEL_HOVER));
    holder.on("pointerout", () => paint(CANCEL_FILL));
    holder.on("pointerdown", () => this.cancel());
    this.cancelButton = holder;
  }

  // ---------- Selecting ----------

  // soldierRollOvers' press (F6:6111-6134): the squad lets go of what was selected, deploying and aiming end, its rings
  // and its leader's health bar stay up, and the INTEL panel takes it over
  select(squadId) {
    const row = this.field.units.squadRow(squadId);
    if (!this.ready || !row || SIDES[row[1]] !== this.battle.you || row[2] > BUTTONS.length) {
      return;
    }
    this.hud.cancelDeploy();
    this.deselect();
    this.selected = squadId;
    this.field.units.ring(squadId, true);
    this.showControls(row);
    this.paint(row);
  }

  // deselectAll (F6:6174-6198): the selected squad's rings and health bar fade, and the panel says to select a unit.
  // An order being aimed was the squad's, so it ends too
  deselect() {
    this.cancelAim();
    this.release();
    this.shown = {};
    this.hud.clearIntel();
  }

  // The squad is no longer selected, the panel's words aside
  release() {
    if (this.selected !== null) {
      this.field.units.ring(this.selected, false);
    }
    this.selected = null;
    this.buttons = [];
  }

  // showUnitControls (F6:6199-6399): the squad's name, its picture and the buttons it has that the side has unlocked,
  // each in its place with the gaps left by the locked ones. The German advance arrow faces the other way
  showControls(row) {
    const side = SIDES[row[1]];
    const kind = row[2] - 1;
    const intel = this.intel;
    intel.child("unitType").text = NAMES[side][kind];
    intel.child("unitCost").text = "";
    intel.child("unitRP").text = "";
    const pictures = intel.child("icons");
    pictures.gotoAndStop(pictures.frameOf(PICTURES[kind]) ? PICTURES[kind] : "empty");
    this.buttons = Array.from({ length: INTEL_SLOTS }, (_, index) => {
      const slot = intel.child(`actionSlot${index}`);
      const action = BUTTONS[kind][index];
      slot.gotoAndStop("empty");
      slot.useHandCursor = false;
      if (!action || !this.unlocked.has(action)) {
        return null;
      }
      slot.gotoAndStop(FRAMES[action]);
      slot.child("icon").child("bw").alpha = 0;
      if (index === 0 && side === "german") {
        slot.child("icon").scale.x = -1;
      }
      return { action, disabled: false };
    });
  }

  // ---------- The panel's buttons ----------

  slotOver(index) {
    const button = this.buttons[index];
    if (!button) {
      return;
    }
    const slot = this.intel.child(`actionSlot${index}`);
    tweens.colorTransformTo(slot, ...HOVER, 0.4, EASE);
    this.intel.child("controlDesc").text = WORDS[button.action];
  }

  // The words go with the pointer, which the original leaves behind on the panel (it clears a field the panel doesn't
  // have, F6:6315)
  slotOut(index) {
    const slot = this.intel.child(`actionSlot${index}`);
    tweens.colorTransformTo(slot, ...NORMAL, 0.5, EASE);
    this.intel.child("controlDesc").text = "";
  }

  // The press of a button (F6:6317-6398): Advance, Throw Grenade and Suppressing Fire go to the bot at once; Throw
  // Smoke, Smoke Rounds, Call Artillery and Call Air Support show their range box
  press(index) {
    const button = this.buttons[index];
    const row = this.selected === null ? null : this.field.units.squadRow(this.selected);
    if (!button || !row || !this.ready || button.disabled) {
      return;
    }
    const id = this.selected;
    const slot = this.intel.child(`actionSlot${index}`);
    switch (button.action) {
      case "advance":
      case "suppress":
        slot.child("pressedAnim")?.play();
        this.send(id, button.action);
        return;
      case "grenade":
        if ((row[4] & TARGET_FLAG) !== 0) {
          slot.child("pressedAnim")?.play();
          this.send(id, "grenade");
        }
        return;
      case "smoke":
        if ((this.hud.last?.rp ?? 0) >= SMOKE_COST) {
          slot.child("pressedAnim")?.play();
          this.startAim(button.action, id);
        }
        return;
      default:
        slot.child("pressedAnim")?.play();
        this.startAim(button.action, id);
    }
  }

  send(id, action, x = null, y = null) {
    return this.page.send({ order: [id, action, x, y] });
  }

  keyDown(e) {
    if (this.page.screen !== "battle" || e.repeat) {
      return;
    }
    if (e.key === "Escape") {
      this.cancelAim();
      return;
    }
    const index = KEYS.indexOf(e.key);
    if (index >= 0) {
      this.press(index);
    }
  }

  // ---------- Aiming ----------

  // showFireSupportArea (F6:6419-6507): the box on the leader (its y fixed at 240 for the support box), the cursor
  // that stands in for the pointer, and the red ground target that follows it inside the box
  startAim(action, id) {
    this.cancelAim();
    const leader = this.field.units.leader(id);
    if (!leader) {
      return;
    }
    const lib = this.page.lib;
    const smoke = action === "smoke";
    const box = lib.makeExported(smoke ? "specialAttackRange_smokeGrenade" : "specialAttackRange");
    box.label = "specAttack";
    if (!smoke) {
      box.scale.x = SUPPORT_WIDTH / box.getLocalBounds().width;
      box.y = SUPPORT_Y;
    }
    const target = lib.makeExported("interface_groundTarget");
    target.visible = false;
    const cursor = this.page.attach("cursorSupport", DEPTH_HUD + DEPTH_HUD_SUPPORT_CURSOR, "supportCursor");
    cursor.visible = false;
    this.field.layer("specialAttackRange").addChild(box);
    this.field.layer("target").addChild(target);
    this.aim = { id, action, leader: leader.id, smoke, box, target, cursor, inside: false, down: null };
    this.wireAim();
    document.body.dataset.aiming = "true";
    this.follow();
  }

  // The box and the target take the pointer. A mouse fires on its press. A finger puts the target down on a tap inside
  // the box, and fires on a tap of the target
  wireAim() {
    const { box, target } = this.aim;
    box.useHandCursor = false;
    target.useHandCursor = false;
    box.setHandler("onRollOver", () => this.boxOver(true));
    box.setHandler("onRollOut", () => this.boxOver(false));
    for (const clip of [box, target]) {
      clip.setHandler("onPress", (e) => this.aimPress(e));
    }
    box.setHandler("onRelease", (e) => this.aimLift(e, false));
    target.setHandler("onRelease", (e) => this.aimLift(e, true));
    // The target under a mouse's pointer would take the pointer from the box and flicker; a finger's target is pressed
    target.eventMode = "none";
  }

  // The cursor is bright inside the box and dim red outside it (F6:6451-6458)
  boxOver(inside) {
    const aim = this.aim;
    if (!aim) {
      return;
    }
    aim.inside = inside;
    aim.cursor.alpha = inside ? 1 : CURSOR_OUT_ALPHA;
    tweens.colorTo(aim.cursor, inside ? null : CURSOR_OUT_COLOR, 0);
  }

  aimPress(e) {
    if (e.pointerType !== TOUCH) {
      this.fire(this.pointOf(e));
      return;
    }
    this.aim.down = { x: e.global.x, y: e.global.y };
  }

  aimLift(e, onTarget) {
    const aim = this.aim;
    if (!aim || e.pointerType !== TOUCH || !aim.down || this.field.swept(aim.down, e)) {
      return;
    }
    aim.down = null;
    if (onTarget) {
      this.fire({ x: aim.target.x, y: aim.target.y });
      return;
    }
    const point = this.pointOf(e);
    aim.target.position.set(point.x, point.y);
    aim.target.visible = true;
    aim.target.eventMode = "static";
  }

  // Where a pointer event is on the field
  pointOf(e) {
    const point = this.field.world.toLocal(e.global);
    return { x: point.x, y: point.y };
  }

  // launchSpecialAttack's call (F6:6459-6498): the order goes to the bot, which charges it and says no if the RP isn't
  // there or the point is outside the box. Aiming is over either way
  fire(point) {
    const aim = this.aim;
    if (!aim || !this.ready) {
      return;
    }
    const round = (value) => Math.round(value * 10) / 10;
    this.send(aim.id, aim.action, round(point.x), round(point.y));
    this.cancelAim();
  }

  // The box follows the squad's leader along the field, the cursor follows the mouse, and the target follows it inside
  // the box. The aim ends when its leader is no longer the squad's first living member
  follow() {
    const aim = this.aim;
    const units = this.field.units;
    const leader = units.leader(aim.id);
    if (!leader || leader.id !== aim.leader) {
      this.cancelAim();
      return;
    }
    aim.box.x = leader.x;
    if (aim.smoke) {
      aim.box.y = leader.y;
    }
    const pointer = this.field.pointer;
    const mouse = pointer.inside && !pointer.touch;
    aim.cursor.visible = mouse;
    aim.cursor.position.set(pointer.x, pointer.y);
    if (mouse) {
      const spot = this.field.toField(pointer.x, pointer.y);
      aim.target.visible = aim.inside;
      aim.target.position.set(spot.x, spot.y);
    }
  }

  // cancelSpecialAttack (F6:6501-6507): the box, the cursor and the target go, and the mouse comes back
  cancelAim() {
    const aim = this.aim;
    if (!aim) {
      return;
    }
    this.aim = null;
    for (const clip of [aim.box, aim.target]) {
      clip.destroy({ children: true });
    }
    this.page.detach("supportCursor");
    delete document.body.dataset.aiming;
  }

  // The INTEL panel's Cancel button and Esc: deploying and aiming both end, with nothing sent
  cancel() {
    this.cancelAim();
    this.hud.cancelDeploy();
  }

  // ---------- Each drawn moment ----------

  draw() {
    if (!this.interactive || !this.intel) {
      return;
    }
    if (this.field.ending || this.field.panels.menu) {
      this.cancelAim();
    }
    if (this.aim) {
      this.follow();
    }
    if (this.selected !== null && !this.hud.rolling) {
      const row = this.field.units.squadRow(this.selected);
      if (row) {
        this.paint(row);
      }
    }
    if (this.cancelButton) {
      this.cancelButton.visible = this.hud.deployMode !== null || this.aim !== null;
    }
  }

  // updateSelectedUnitInfo (F6:6508-6656): the squad's health, what it is doing, and which buttons are greyed. Each
  // word, colour and grey is drawn only when it changes
  paint(row) {
    const percent = this.field.units.health(row[0]);
    if (percent === null) {
      return;
    }
    const intel = this.intel;
    const line = healthLine(percent);
    const state = STATES[row[3]];
    const text = this.stateText(row, state, line.words);
    this.show("state", text, () => {
      intel.child("unitState").text = text;
    });
    this.show("health", percent, () => {
      intel.child("unitStatus").child("perc").text = `${percent}%`;
    });
    if (line.color !== undefined) {
      this.show("color", line.color, () => tweens.colorTo(intel.child("unitStatus"), line.color, 0));
    }
    this.grey(row, state);
  }

  show(key, value, draw) {
    if (this.shown[key] !== value) {
      this.shown[key] = value;
      draw();
    }
  }

  // What the panel says the squad is doing, with the health words after it
  stateText(row, state, words) {
    const engaging = (row[4] & TARGET_FLAG) !== 0 ? "Engaging. " : "";
    const kind = this.battle.map.covers[row[7]]?.[2];
    const cover = COVER_WORDS[kind] ?? kind;
    const lines = {
      tankMoving: `Moving. ${words}`,
      tankEngaging: `Engaging. ${words}`,
      exitTrench: `Leaving cover. ${words}`,
      assaultTrench: `Engaging enemy in cover. ${words}`,
      engaging: `Engaging. ${words}`,
      entrench: `${engaging}In cover behind ${cover}. ${words}`,
      moving: `Moving out. ${words}`,
      victory: "Celebrating victory!",
      defeated: "Surrendering.",
    };
    return lines[state] ?? `State: ${state}`;
  }

  // Advance is greyed until the whole squad is in its cover, and Throw Smoke and Smoke Rounds while it moves
  // (common/orders.py greyed)
  grey(row, state) {
    const moving = state === "moving";
    const off = { advance: (row[4] & IN_COVER_FLAG) === 0, smoke: moving, smokeRounds: moving };
    this.buttons.forEach((button, index) => {
      const disabled = Boolean(button && off[button.action]);
      if (!button || button.disabled === disabled) {
        return;
      }
      button.disabled = disabled;
      this.intel.child(`actionSlot${index}`).child("icon").child("bw").alpha = disabled ? 1 : 0;
    });
  }

  // ---------- A squad gone ----------

  // A gone squad that was selected: the panel says it was killed and its buttons go dead, and nothing is selected any
  // more (showIntelDeathMessage F6:6657-6671, then deselectAll)
  gone(squadId) {
    if (squadId !== this.selected) {
      return;
    }
    this.cancelAim();
    this.release();
    const intel = this.intel;
    tweens.colorTo(intel.child("unitStatus"), RED, 0);
    intel.child("unitStatus").child("perc").text = "KIA";
    intel.child("icons").gotoAndStop("dead");
    intel.child("unitState").text = "Killed in Action.";
    for (let index = 0; index < INTEL_SLOTS; index += 1) {
      const bw = intel.child(`actionSlot${index}`).child("icon")?.child("bw");
      if (bw) {
        bw.alpha = 1;
      }
    }
    this.shown = {};
  }
}
