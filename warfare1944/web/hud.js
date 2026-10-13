// The battle's HUD and the bars along the top: the eight unit portraits with their timer dials and rings, deploying into
// a lane, the resource points counter with its refill dial, the Upgrades dial, the Menu button, the ground-taken and
// morale bars with their tooltip, the clocks, the quick messages the battle sends, and the tooltips (buildGameInterface
// F6:5616-5631, updateProgressBar F6:5705-5811, checkUnitNames F6:5812-5828, buttonSetup F6:5829-5916, buttonTimer
// F6:5917-5962, updateResourcesInterface F6:1438-1485, deploySquad F6:1801-1839, setupDeployButtons F6:1840-1951,
// cancelDeploy F6:1952-1966, updateMoraleBar F6:8411-8470, timerTick and updateTimer F6:9665-9717).
//
// The bot runs every timer, price, ground and morale number and decides every deploy. The page draws what each update
// says: the dials fill from the fills in the update (state "h"), the bars from "f" and "m", the counter and its refill
// dial from "r", the clocks from "t". Picking a unit and a lane is the page's own business until the lane is pressed:
// that sends `deploy` with the slot and the lane, and the bot answers with the squad, the dial starting over and, if it
// said no, a "msg" event that shows here. The HUD shows the side the viewer plays, or the side a watcher watches, and a
// watcher presses nothing.
import { TextField } from "./flash.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";
import { openUpgrades } from "./upgrades.js";

const SIDES = ["british", "german"];
const DEPTH_HUD = 900000;
const EASE = "easeOutSine";
const LINEAR = "linear";
const UNIT_SLOTS = 8;
const STAGE_WIDTH = 800;
// A dial that is full is ready. The bot's fills run 0 to 1000
const FULL = 1000;
const HALF = FULL / 2;
// A dial is two half discs: the right one turns from -180 to 0 over the first half of the wait, the left one from 0 to
// 180 over the second (buttonTimer F6:5917-5962)
const HALF_TURN = 180;
const DIAL_START = -179;
// The colors the slots flash as they fill or empty (F6:5845-5851, 5958)
const READY_FLASH = 12566199;
const CHARGED_FLASH = 10460563;
const HIGHLIGHT_READY = 55;
const HIGHLIGHT_HOVER = 95;
// The tooltip follows the pointer, 40 up (the placement script of 1791), on a backing 145 wide that is 20 taller than
// the description (buttonSetup F6:5866-5869)
const TIP_OFFSET_Y = -40;
const TIP_WIDTH = 145;
const TIP_MARGIN = 20;
// A finger resting on a slot lifts the tooltip this many screen pixels higher, so the finger doesn't cover it
const TIP_FINGER_LIFT_PX = 44;
// The ground bar goes dark red and back when its side has no front squad, and slides to a new number over 3 seconds
const GROUND_FLASH = 3342336;
const GROUND_SLIDE_SECONDS = 3;
// updateMoraleBar's frames (F6:8452-8469): red at 35 or less, deep red at 15 or less, and its own again above 30
const MORALE_RED_AT = 35;
const MORALE_VERY_RED_AT = 15;
const MORALE_NORMAL_AT = 30;
// The lanes: a click area 70 high, as wide as the field, from 34 above the lane's line (deployBlock, F6:1840-1853), and
// the lit band over it (deployZoneHighlight). A zone under the pointer tints to 15 %, or to deep red for a tank sent
// where there is cover
const ZONE_HEIGHT = 70;
const ZONE_HOVER = 15;
const ZONE_PRESSED = 30;
const ZONE_BLOCKED = 10027008;
const DEPLOY_FADE_SECONDS = 0.5;
const CANCEL_FADE_SECONDS = 0.2;
// The ring round a picked portrait: half there while the unit costs more than there is, then full green
const RING_HALF = 50;
const RING_AFFORDABLE = 8305408;
// The RP counter flashes red for RP spent and green for RP gained, and goes back to its own color (adjustRP)
const RP_SPENT = 10027008;
const RP_GAINED = 6723840;
const RP_NORMAL = 10327418;
// The resupply of RP each side gets (startingSupplyPoints, F6:10185), shown beside the counter and never drained
const SUPPLY = 200;
// The defend countdown shows from the first one-second tick on (timerTick); the mission clock sits beside it
const CLOCK_SHIFT = 64;
const ONE_SECOND_STEPS = 30;
const TANK_SLOT = 8;
// A battle that arrives before this step is a new one, which opens with the hold-the-line message
const HOLD_LINE_UNTIL_STEP = 90;
const LEVELS = [
  15, 45, 90, 150, 225, 315, 420, 540, 675, 825, 990, 1170, 1390, 1615, 1855, 2110, 2880, 3165, 3465,
];
// What the tooltips of the eight unit slots say (setButtonSetValues F6:5733-5779; checkUnitNames changes the names of
// slots 2, 3, 5 and 8 for the German side)
const UNITS = [
  { name: "Riflemen", desc: "Good vs Infantry. \rWeak vs Armor." },
  { name: "Assault Team", german: "Sturmtruppen", desc: "Strong vs Entrenched.\rAverage vs Armor." },
  { name: ".30 Cal", german: "MG34 Team", desc: "Good vs Infantry \rwhen entrenched." },
  { name: "Sniper", desc: "Strong vs Infantry at \rlong range." },
  { name: "Bazooka Team", german: "Panzershreck", desc: "Anti-tank team. \rStrong vs Armor." },
  { name: "Mortar Team", desc: "Light Artillery. \rAverage vs All." },
  { name: "Officer", desc: "Has fire support. \rProvides morale boost." },
  { name: "Sherman Tank", german: "Panzer III", desc: "Strong vs All. \rWeak vs Fire support." },
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

// Seconds as mm:ss, with the zero kept below ten (B61)
export function clockText(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(Math.floor(whole / 60))}:${pad(whole % 60)}`;
}

export class Hud {
  constructor(field) {
    this.field = field;
    this.clip = null;
    this.world = null;
    this.side = "british";
    this.battle = null;
    // The unit slots: { name, index, clip, icon, ..., unlocked, ready }
    this.units = [];
    this.tip = null;
    // The numbers drawn last, so a bar, counter or clock redraws only when its number moves
    this.last = null;
    this.xp = { points: 0, level: 0, xp: 0 };
    // The slot (1 to 8) being deployed, or null. Set by tapping a ready portrait, ended by a lane, Esc, the INTEL
    // panel's Cancel or selecting a squad
    this.deployMode = null;
    // True while the pointer is on a portrait slot: the INTEL panel keeps what it shows (rollingOverDeployButtons)
    this.rolling = false;
    // The lanes' click areas and lit bands, and the ring round the picked portrait
    this.zones = [];
    this.bands = [];
    this.ringGreen = false;
    // The press that may become a lane's deploy, the mission clock's own field beside the defend countdown, and the
    // countdown's value at the start
    this.pressed = null;
    this.missionClock = null;
    this.defendStart = null;
    // Set by the panels: called when the Menu button is pressed, and each time the bot takes a deploy of this side's
    this.onMenu = null;
    this.onDeploy = null;
    field.onLoad((battle) => this.load(battle));
    field.onDraw(() => this.draw());
    field.onClear(() => this.reset());
    field.onEvent("xp", (event) => this.gainXp(event[4]));
    field.onEvent("rp", (event, quiet) => this.rpEvent(event, quiet));
    field.onEvent("msg", (event, quiet) => this.message(event, quiet));
    field.onEvent("flank", (event, quiet) => this.flankMessage(event, quiet));
    field.onEvent("deploy", (event, quiet) => this.deployEvent(event, quiet));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.deployMode !== null && !this.field.paused && !this.field.panels.menu) {
        this.cancelDeploy();
      }
    });
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
    return ["hud", "deployBlock", "deployZoneHighlight"];
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
    this.setupResources();
    this.units = Array.from({ length: UNIT_SLOTS }, (_, index) => this.setupUnit(index, battle.units[this.side][index]));
    this.setupZones(battle);
    this.clearIntel();
    this.announceDefend(battle);
  }

  reset() {
    this.page.detach("hud");
    Object.assign(this, { clip: null, world: null, battle: null, units: [], tip: null, last: null });
    Object.assign(this, { deployMode: null, rolling: false, zones: [], bands: [], ringGreen: false });
    Object.assign(this, { missionClock: null, defendStart: null });
  }

  // The hud clip's own parts: the side's frames, the tooltips hidden until they are wanted, the Menu button, and the
  // help panels, which panels.js shows when a player's battle is built. The four fire support slots of 1917 sit above
  // the stage and are not drawn
  setupParts() {
    const clip = this.clip;
    clip.child("hudBG").gotoAndStop(this.side);
    clip.child("progressBar").child("casing").gotoAndStop(this.side);
    clip.child("upgrades").child("upgradeButton").gotoAndStop(this.side);
    clip.child("progressBarToolTip").visible = false;
    clip.child("help").visible = false;
    for (let n = 1; n <= 4; n += 1) {
      for (const part of ["supportSlot", "lock_supportSlot", "icon_supportSlot"]) {
        clip.child(`${part}${n}`).visible = false;
      }
    }
    this.tip = clip.child("toolTip");
    this.tip.visible = false;
    for (const name of ["header", "desc"]) {
      const field = this.tip.child(name);
      field.anchor = { x: field.x, box: field.box.x };
      field.autoSizeCenter(name === "desc");
    }
    this.setupMenuButton(clip.child("menuButton"));
    clip.child("intel").child("unitType").fit();
  }

  // buttonSetup_hudMenuButton (F6:813-829)
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

  // The dial's placement script (1611): its full block starts hidden
  hideBlock(slot) {
    slot.child("fullBlock").visible = false;
  }

  // buttonSetup (F6:5829-5916) for one portrait slot. A slot the mission allows starts ready; the others show their
  // padlock and no picture. Every ring starts clear (deselectRings)
  setupUnit(index, allowed) {
    const clip = this.clip;
    const number = index + 1;
    const entry = {
      index,
      clip: clip.child(`slot${number}`),
      highlight: clip.child(`highlight_slot${number}`),
      lock: clip.child(`lock_slot${number}`),
      icon: clip.child(`icon_slot${number}`),
      ring: clip.child(`ring_slot${number}`),
      unlocked: allowed,
      ready: allowed,
    };
    this.hideBlock(entry.clip);
    entry.highlight.alpha = 0;
    entry.ring.alpha = 0;
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

  setupSlotHandlers(entry, words) {
    const clip = entry.clip;
    clip.useHandCursor = false;
    clip.setHandler("onRollOver", () => this.slotOver(entry, words));
    clip.setHandler("onRollOut", () => this.slotOut(entry));
    for (const name of ["onPress", "onRelease", "onReleaseOutside"]) {
      clip.setHandler(name, () => this.press(entry));
    }
  }

  // The resource counter and its refill dial (buildGameInterface F6:5625): the dial starts empty, and the supply beside
  // the counter reads its fixed refill
  setupResources() {
    const clip = this.clip;
    const dial = clip.child("resupplyTimer").child("experience");
    this.hideBlock(dial);
    dial.child("rightDial").angle = -HALF_TURN;
    clip.child("supplyPoints").text = `+${SUPPLY}`;
    const timer = clip.child("timer");
    this.missionClock = new TextField({ ...timer.def, text: "" });
    this.missionClock.position.set(timer.x + CLOCK_SHIFT, timer.y);
    this.missionClock.filters = timer.filters ? [...timer.filters] : [];
    clip.addChild(this.missionClock);
    this.defendStart = this.battle.map.timed && this.battle.step < ONE_SECOND_STEPS ? this.battle.s.t[1] : null;
    timer.text = "";
  }

  // ---------- Tooltips ----------

  // The tooltip over a slot: its name, price and words come up after half a second. A slot that isn't allowed has none
  slotOver(entry, words) {
    this.rolling = true;
    if (!entry.unlocked) {
      return;
    }
    const name = (this.side === "german" && words.german) || words.name;
    this.showTip(name, words.desc, this.battle.costs[this.side][entry.index], 0.5);
    if (entry.ready && this.interactive) {
      entry.clip.useHandCursor = true;
      this.glow(entry, HIGHLIGHT_HOVER, 0.8);
    }
  }

  slotOut(entry) {
    this.rolling = false;
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

  // The tooltip is sized to its words: the backing is 145 wide and 20 taller than the description
  showTip(header, desc, cost, delay) {
    const tip = this.tip;
    const [head, words, backing] = [tip.child("header"), tip.child("desc"), tip.child("backing")];
    this.setTipText(head, header);
    this.setTipText(words, desc);
    tip.child("cost").text = cost;
    backing.scale.set(1);
    const size = backing.getLocalBounds();
    backing.scale.set(TIP_WIDTH / size.width, (words.box.height + TIP_MARGIN) / size.height);
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
    this.tip.x = pointer.x;
    this.tip.y = pointer.y + TIP_OFFSET_Y - (pointer.touch ? TIP_FINGER_LIFT_PX / this.page.world.scale.x : 0);
  }

  // ---------- Deploying ----------

  // The press of a slot (onPress, onRelease and onReleaseOutside all do the same): a ready slot becomes the unit to
  // deploy, and a different one picked next swaps it
  press(entry) {
    if (!this.interactive || !entry.unlocked || !entry.ready || this.field.paused) {
      return;
    }
    this.startDeploy(entry);
  }

  // deploySquad (F6:1801-1825): the lanes light up and the picked portrait gets its ring, green once the unit is
  // affordable. No price is checked until a lane is pressed. Picking a unit lets go of the squad selected and of an
  // order being aimed (deselectAll, F6:5906)
  startDeploy(entry) {
    this.field.orders.cancelAim();
    this.deployMode = entry.index + 1;
    this.units.forEach((unit) => {
      if (unit !== entry) {
        this.clearRing(unit);
      }
    });
    tweens.colorTo(entry.ring, null, 0);
    entry.ring.alpha = RING_HALF / 100;
    this.ringGreen = false;
    this.lightBands();
    this.zones.forEach((zone) => {
      zone.eventMode = "static";
    });
    this.field.orders.deselect();
    this.clearIntel();
  }

  clearRing(entry) {
    entry.ring.alpha = 0;
    tweens.colorTo(entry.ring, null, 0);
  }

  // The ring turns green and full as soon as the picked unit's price is at most the RP the side has
  checkRing() {
    const slot = this.deployMode;
    if (slot === null || this.ringGreen || !this.last?.rp) {
      return;
    }
    if (this.battle.costs[this.side][slot - 1] <= this.last.rp) {
      const ring = this.units[slot - 1].ring;
      this.ringGreen = true;
      tweens.alphaTo(ring, 100, 0.2);
      tweens.colorTo(ring, RING_AFFORDABLE, 0.2);
    }
  }

  // setupDeployButtons (F6:1840-1856): a click area for each lane, as wide as the field, between the field's lowest
  // layers. It takes presses only while a unit is picked
  setupZones(battle) {
    this.zones = [];
    if (!this.interactive) {
      return;
    }
    const layer = this.field.layer("deployButtons");
    const lib = this.page.lib;
    battle.map.lanes.forEach((line, index) => {
      const zone = lib.makeExported("deployBlock");
      const size = zone.getLocalBounds();
      zone.label = `deployZone${index + 1}`;
      zone.scale.set(battle.map.width / size.width, ZONE_HEIGHT / size.height);
      zone.position.set(0, line);
      zone.alpha = 0;
      zone.useHandCursor = false;
      zone.setHandler("onRollOver", () => this.zoneOver(zone, index + 1));
      zone.setHandler("onRollOut", () => {
        zone.alpha = 0;
      });
      // Where the press began comes from the press itself: the field's own pointer reading is taken after this
      // handler runs, so on a first touch it still holds the last press's place
      zone.setHandler("onPress", (e) => {
        this.pressed = { x: e.global.x, y: e.global.y };
      });
      zone.setHandler("onRelease", (e) => this.zonePressed(zone, index + 1, e));
      zone.eventMode = "none";
      layer.addChild(zone);
      this.zones.push(zone);
    });
  }

  // deployZone onRollOver (F6:1866-1900): the zone under the pointer tints, deep red when a tank may not go there
  zoneOver(zone, lane) {
    if (this.deployMode === null) {
      zone.useHandCursor = false;
      return;
    }
    const blocked = this.blocked(lane);
    zone.useHandCursor = !blocked;
    zone.alpha = ZONE_HOVER / 100;
    tweens.colorTo(zone, blocked ? ZONE_BLOCKED : null, 0);
    tweens.colorTo(this.bands[lane - 1], blocked ? ZONE_BLOCKED : null, 0);
  }

  // A tank may not go to a lane that has any cover on this map (F6:1872, 1910)
  blocked(lane) {
    return this.deployMode === TANK_SLOT && this.battle.map.covers.some((cover) => cover[0] === lane);
  }

  // A press that lets go on a lane without having scrolled the field sends the deploy. The mouse's press and the
  // finger's tap are the same here. A tank sent where there is cover turns the lane red and ends the deploy; the bot
  // says so too
  zonePressed(zone, lane, e) {
    const moved = this.pressed ? this.field.swept(this.pressed, e) : false;
    this.pressed = null;
    if (this.deployMode === null || !this.interactive || moved) {
      return;
    }
    const blocked = this.blocked(lane);
    const seconds = blocked ? CANCEL_FADE_SECONDS : DEPLOY_FADE_SECONDS;
    zone.alpha = ZONE_PRESSED / 100;
    if (blocked) {
      tweens.colorTo(zone, ZONE_BLOCKED, 0);
    }
    tweens.alphaTo(zone, 0, seconds);
    this.page.send({ deploy: [this.deployMode, lane] });
    this.endDeploy(seconds);
  }

  // The three lanes lit, one band over each, under the soldiers (deployZoneHighlight at depth 1200)
  lightBands() {
    this.removeBands(0);
    const layer = this.field.layer("deployZoneHighlight");
    this.bands = this.battle.map.lanes.map((line) => {
      const band = this.page.lib.makeExported("deployZoneHighlight");
      band.position.set(0, line);
      band.scale.x = this.side === "german" ? -1 : 1;
      layer.addChild(band);
      return band;
    });
    this.followCamera();
  }

  // The bands stay centered on the screen as the field scrolls (the zones' onEnterFrame, F6:1857-1865)
  followCamera() {
    const x = STAGE_WIDTH / 2 - this.field.world.x;
    this.bands.forEach((band) => {
      band.x = x;
    });
  }

  removeBands(seconds) {
    const bands = this.bands;
    this.bands = [];
    for (const band of bands) {
      tweens.alphaTo(band, 0, seconds, LINEAR, 0, () => band.destroy({ children: true }));
    }
  }

  // The deploy is over, sent or not: the bands and rings clear and the lanes stop taking presses
  endDeploy(seconds) {
    if (this.deployMode === null) {
      return;
    }
    this.units.forEach((unit) => this.clearRing(unit));
    this.removeBands(seconds);
    this.zones.forEach((zone) => {
      zone.eventMode = "none";
    });
    this.deployMode = null;
    this.clearIntel();
  }

  // cancelDeploy (F6:1952-1966): Esc, selecting a squad or the INTEL panel's Cancel
  cancelDeploy() {
    this.endDeploy(CANCEL_FADE_SECONDS);
  }

  // clearIntelInterface (F6:6672-6701): the INTEL panel with nothing selected says what to do next
  clearIntel() {
    const intel = this.clip?.child("intel");
    if (!intel) {
      return;
    }
    const deploying = this.deployMode !== null;
    intel.child("unitType").text = deploying ? "Select a Deployment Zone" : "Select a Unit";
    intel.child("unitState").text = deploying ? "Press [ESC] to cancel." : "Click on a squad to select it.";
    const status = intel.child("unitStatus");
    tweens.colorTo(status, 7416872, 0);
    const percent = status.child("perc");
    if (percent) {
      percent.text = "";
    }
    intel.child("icons").gotoAndStop("empty");
    for (let slot = 0; slot < 4; slot += 1) {
      intel.child(`actionSlot${slot}`)?.gotoAndStop("empty");
    }
  }

  // The bot took a deploy of the side this HUD shows: the help tips count it
  deployEvent(event, quiet) {
    if (!quiet && SIDES[event[2]] === this.side) {
      this.onDeploy?.();
    }
  }

  // ---------- The dials ----------

  // resetButtonTimers (F6:5963-5976): the slot goes dark and starts to fill
  discharge(entry) {
    entry.ready = false;
    tweens.stopTween(entry.clip);
    entry.picture.gotoAndStop("bw");
    this.glow(entry, 0, 0.8);
    tweens.alphaTo(entry.clip, 100, 0.1, LINEAR);
    tweens.colorTo(entry.clip, null, 0.1, LINEAR);
    this.turnDial(entry, DIAL_START, 0);
  }

  // The end of buttonTimer (F6:5951-5961): the slot lights and is ready
  charge(entry) {
    entry.ready = true;
    this.turnDial(entry, 0, HALF_TURN);
    entry.picture.gotoAndStop("colour");
    tweens.alphaTo(entry.highlight, HIGHLIGHT_READY, 0.3, LINEAR, 0.5);
    tweens.colorTo(entry.clip, CHARGED_FLASH, 0.5, LINEAR);
    tweens.alphaTo(entry.clip, 0, 0.3, LINEAR, 0.4);
  }

  turnDial(entry, right, left) {
    entry.clip.child("rightDial").angle = right;
    entry.clip.child("leftDial").angle = left;
  }

  // One slot for the drawn moment: ready or not as the bot's fill says, and the dial turned to it
  paintSlot(entry, now, next, t) {
    if (!entry.unlocked) {
      return;
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

  // setupProgressBar (F6:5649-5666): the tooltip with both sides' ground and morale fades in over the bars
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

  // updateProgressBar's numbers (F6:5760-5811): the British ground is the left bar and the German ground the right,
  // whichever side the viewer plays. A bar slides to its number over 3 seconds, and goes straight there on a rejoin.
  // `f` is the bot's ground numbers, then whether each side has no front squad, then the slow ticks run so far: a side
  // with no front squad flashes its bar again on every slow tick, as the original's check does (F6:5733-5750).
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
      tweens.xScaleTo(bar, ground[index], GROUND_SLIDE_SECONDS, EASE);
    });
    return { ground, ticks };
  }

  // A side with no front squad: the bar goes dark red and comes back (F6:5733-5738)
  flashRed(bar) {
    tweens.colorTo(bar, GROUND_FLASH, 0.2);
    tweens.colorTo(bar, null, 0.5, EASE, 1);
  }

  // updateMoraleBar (F6:8411-8470): the two bars, in percent of each side's own maximum, set at once. Each bar takes
  // its frame in the original's order: red at 35 or less, deep red at 15 or less, and its own again above 30, so a
  // bar between 31 and 35 shows its own. Returns the numbers drawn
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
      const value = morale[index];
      bar.scale.x = value / 100;
      if (value <= MORALE_RED_AT) {
        bar.gotoAndStop("red");
      }
      if (value <= MORALE_VERY_RED_AT) {
        bar.gotoAndStop("veryRed");
      }
      if (value > MORALE_NORMAL_AT) {
        bar.gotoAndStop("normal");
      }
    });
    return { morale };
  }

  // ---------- Resources and clocks ----------

  // updateResourcesInterface (F6:1438-1447) and resourceResupplyTimer (F6:1329-1344): the counter shows this side's RP
  // and the dial how far the refill has come. The supply bars are always full, as played. Returns the numbers drawn
  paintResources(r) {
    const rp = r[SIDES.indexOf(this.side)];
    const dial = this.clip.child("resupplyTimer").child("experience");
    if (rp !== this.last?.rp) {
      this.clip.child("resourcePoints").text = rp;
    }
    if (r[4] !== this.last?.refill) {
      const [right, left] = dialTurns(r[4]);
      dial.child("rightDial").angle = right;
      dial.child("leftDial").angle = left;
    }
    return { rp, refill: r[4] };
  }

  // timerTick and updateTimer (F6:9665-9717), missionTimerTick (F6:9718-9743): a defend mission's countdown at the top
  // centre from its first tick, "00:00" once it has run out, and the mission clock counting up beside it. A mission
  // with no countdown shows its clock where the countdown would sit. Returns the numbers drawn
  paintClocks(t) {
    const [seconds, defend] = t;
    const timed = this.battle.map.timed;
    const countdown = timed && defend !== this.defendStart;
    const top = this.clip.child("timer");
    const shown = { seconds, defend: countdown ? defend : null };
    if (seconds === this.last?.seconds && shown.defend === this.last?.defend) {
      return {};
    }
    const mission = clockText(seconds);
    if (timed) {
      top.text = countdown ? clockText(defend) : "";
      this.missionClock.text = mission;
    } else {
      top.text = mission;
      this.missionClock.text = "";
    }
    return shown;
  }

  // ---------- Messages ----------

  // showQuickMessage (F6:380-403) for the lines the battle sends as "msg" events: a deploy the bot refused, the morale
  // warnings and the defend mission's last stand. The words follow whose line it is: the side the HUD shows hears
  // "MORALE IS LOW!" and the other side's is "ENEMY MORALE IS LOW!"
  message(event, quiet) {
    if (quiet || !this.battle) {
      return;
    }
    const [, , key, sideIndex, number] = event;
    const own = SIDES[sideIndex] === this.side;
    const lines = {
      blocked: own && "PATH IS BLOCKED FOR ARMOR.",
      rp: own && `NOT ENOUGH RESOURCES. NEED ${number}.`,
      lowMorale: own ? "MORALE IS LOW!" : "ENEMY MORALE IS LOW!",
      breaking: own ? "OUR UNITS ARE AT BREAKING POINT!" : "ENEMY IS AT BREAKING POINT!",
      depleted: own && "ENEMY REINFORCEMENTS DEPLETED. FINISH THEM OFF!",
    };
    if (lines[key]) {
      this.say(lines[key]);
    }
  }

  // adjustMorale "flanked" (F6:8284-8293): the event names the side that flanked
  flankMessage(event, quiet) {
    if (quiet || !this.battle) {
      return;
    }
    const own = SIDES[event[2]] === this.side;
    this.say(own ? "ENEMY FLANKED! THEIR MORALE HAS DROPPED!" : "FLANKED! LOSING MORALE!");
  }

  say(text) {
    this.page.quickMessage(text).catch((e) => {
      console.warn("Warfare 1944: couldn't show a quick message", e);
    });
  }

  // startBattle (F6:6797-6800): a timed mission opens with how long to hold the line
  announceDefend(battle) {
    if (battle.map.timed && battle.step < HOLD_LINE_UNTIL_STEP) {
      this.say(`HOLD THE LINE FOR ${Math.ceil(battle.s.t[1] / 60)} MINS!`);
    }
  }

  // adjustRP (F6:1345-1412): the counter flashes red for RP this side spent and green for RP it gained, then goes back
  rpEvent(event, quiet) {
    const [, , sideIndex, amount] = event;
    if (quiet || !this.clip || SIDES[sideIndex] !== this.side) {
      return;
    }
    const counter = this.clip.child("resourcePoints");
    tweens.colorTo(counter, amount < 0 ? RP_SPENT : RP_GAINED, 0.2);
    tweens.colorTo(counter, RP_NORMAL, 0.2, LINEAR, 1);
  }

  // ---------- Experience ----------

  // setupInterfaceExperience (F6:8883-8902): the Upgrades dial from the save. It is the campaign player's; a custom or
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

  // updateExperience (F6:8771-8882): XP the bot awarded counts here as it comes. A level reached lights the dial and
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

  // The state around the drawn clock: the dials fill from it, and the bars, counter and clocks show it
  draw() {
    if (!this.clip || !this.battle) {
      return;
    }
    const { a, b, t } = this.field.around();
    this.update(a.s, b.s, t);
    if (this.deployMode !== null) {
      if (this.field.ending || !this.interactive) {
        this.cancelDeploy();
      } else {
        this.followCamera();
        this.checkRing();
      }
    }
  }

  // The HUD for the state `now` the drawing has reached, sliding toward the next update `next` by t (0 to 1)
  update(now, next, t) {
    const own = this.side;
    const dials = now.h[own];
    const ahead = next.h[own];
    this.units.forEach((entry, index) => this.paintSlot(entry, dials[index], ahead[index], t));
    const seen = {
      ...this.paintGround(now.f),
      ...this.paintMorale(now.m),
      ...this.paintResources(now.r),
      ...this.paintClocks(now.t),
    };
    this.last = { ...this.last, ...seen };
    if (this.tip.visible) {
      this.placeTip();
    }
  }
}
