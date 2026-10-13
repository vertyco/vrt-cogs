// Soldiers, tanks and the bunker on the field: one soldier clip (sprite 666), tank clip (sprite 913) or bunker clip
// (sprite 929) for each member the bot sends, dressed the way createSoldier and decorateSoldier dressed them
// (F6:1619-1776), their bodies after death, the depth sorting, and the squad's ring, health bar, cover icon and
// officer star.
//
// The bot decides every animation. Each member's row carries the frame the bot last jumped its timeline to, whether
// it played or stopped there, and the step it happened on. When the field's drawing reaches that step the clip makes
// the same jump, and between jumps it steps one frame a drawn step, running the same frame scripts the bot runs, so
// both stay on the same frame. A jump the drawing reaches late is played forward by the steps it missed. Deaths are
// the page's to play (the bot drops the member from its squad): the "die" event starts the body's death animation.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const FPS = 30;
const SIDES = ["british", "german"];
// common/data.py SOLDIER_TYPES and common/squads.py STATES, in the bot's order: the rows send their positions
const SOLDIER_TYPES = [
  "rifleman",
  "carbine",
  "thompson",
  "BAR",
  "volksgrenadier",
  "grenadier",
  "machineGunner",
  "sharpShooter",
  "bazookaMan",
  "mortarCarrier",
  "lieutenant",
  "tankMarkIV",
  "bunkerBase",
];
export const STATES = [
  "moving",
  "engaging",
  "assaultTrench",
  "entrench",
  "exitTrench",
  "bunkerIdle",
  "bunkerEngaging",
  "tankMoving",
  "tankDead",
  "tankEngaging",
  "victory",
  "defeated",
];
const SOLDIER_SPRITE = 666;
const OFFICER_SLOT = 7;
const TANK_SLOT = 8;
const BUNKER_SLOT = 9;
// Each soldier type's mainWeapon (F6:10290-10700), a frame label of the weapon part (sprite 594). The snipers' labels
// aren't in it, so their weapon stays on its first frame, as in the original
export const MAIN_WEAPON = {
  british: {
    rifleman: "garand",
    carbine: "garand",
    thompson: "thompson",
    BAR: "BAR",
    machineGunner: "30Cal",
    sharpShooter: "enfieldSniper",
    bazookaMan: "bazooka",
    mortarCarrier: "mortarTube",
    lieutenant: "garand",
    tankMarkIV: "tankMG",
  },
  german: {
    rifleman: "mauser",
    grenadier: "mauser",
    volksgrenadier: "mp40",
    machineGunner: "mg34",
    sharpShooter: "mauserSniper",
    bazookaMan: "panzershreck",
    mortarCarrier: "mortarTube",
    lieutenant: "mp40",
    tankMarkIV: "tankMG",
    bunkerBase: "tankMG",
  },
};
// decorateSoldier (F6:1619-1633): each of these parts goes to its "<side>_<type>" frame
const BODY_PARTS = [
  "helmet",
  "torso",
  "front_upperArm",
  "front_lowerArm",
  "front_upperLeg",
  "front_lowerLeg",
  "front_foot",
  "back_upperArm",
  "back_lowerArm",
  "back_upperLeg",
  "back_lowerLeg",
  "back_foot",
];
// The frames whose scripts set the soldier's position as a pose settles (S666 frames 61, 128, 160, 470, 501, 521,
// 1103, 1404). Its death animation is "<position>_death" (F6:4460, 4738); createSoldier starts it standing (F6:1670)
const POSITION_SETS = {
  61: "standing",
  128: "prone",
  160: "standing",
  470: "crouch",
  501: "crouch",
  521: "standing",
  1103: "standing",
  1404: "standing",
};
// A soldier first seen part way through an animation (a rejoin) never passed those frames on the page: its position is
// guessed from the animation it is in. The suppressed animation (162-230) is drawn crouching
const POSITION_RANGES = [
  ["prone", 128, 159],
  ["crouch", 162, 230],
  ["prone", 231, 455],
  ["crouch", 470, 491],
  ["crouch", 501, 520],
  ["crouch", 529, 1097],
];
// sortSoldierDepths runs on the really-slow tick, every 120 steps from the first (F6:10042-10051)
const SORT_EVERY = 120;
// clearDeadSoldierTime (F6:10925): a body fades over a second, 15 seconds after death (fadeDeadSoldier F6:4811-4815).
// sortDeadDelay (F6:10920): a second after death the body goes below the living (sortDeadSoldiers F6:7933-7936)
const CLEAR_DEAD_STEPS = (15000 * FPS) / 1000;
const SORT_DEAD_STEPS = (1000 * FPS) / 1000;
const BODY_FADE = 1;
// createSoldier's gotoAndPlay(20 + random(15)) (F6:1769): the only jump into these frames
const SPAWN_FRAMES = [20, 34];
// The exit from cover (the exitTrench label): a squad's leader starting it is the moment the original calls "advance"
// (F6:3000-3010)
const EXIT_COVER = 36;
// A squad row's flag bit 6: the squad has Suppressing Fire shots left
const SUPPRESSING_FLAG = 64;

// The soldier's frame scripts the page runs itself: the run cycle's loop (34), the mortar's shot (829, which only
// flashes the muzzle here: the round is the bot's "round" event) and the mortar cycle's end (905, which only stops:
// the bot's jump restarts a smoke round). Frame 1436's grenade is the bot's "grenade" event, and frame 486 (a medic's
// pickup) is never reached (W1)
const RUN_LOOP = 34;
const MORTAR_FIRE = 829;
const MORTAR_END = 905;
// Frames 1 to 63 are standing, running or leaving cover, and 1117 is stop_idle: a leader on any other frame in its
// cover has taken its pose there (inTrench, set as the pose starts, F6:3385-3388)
const UPRIGHT_LAST = 63;
const STOP_IDLE = 1117;
// A jump the drawing reaches late is played forward by at most this many frames (a rejoin long after it)
const MOST_CATCH_UP = 600;
// A member gone from every update without a "die" event (an update lost to a jump) is dropped this many steps later
const GONE_AFTER = 4;
const HOW_BLAST = 1;
// A tank's or the bunker's whole health is its HP (createSoldier's totalHealth, F6:1658; 950 F6:10461, 1000
// F6:10695, 1200 F6:10725). German Heavy's x1.15 raises the health but not that, so its bar starts past full
const ARMOUR_HEALTH = { british: 950, german: 1000, bunker: 1200 };
// The health bar turns amber below 60 % and red below 30 % (F6:2019-2026)
const BAR_AMBER = 60;
const BAR_RED = 30;
const AMBER = 16763904;
const RED = 10027008;
const BAR_COLOR_SECONDS = 0.4;
// checkCoverRating (F6:1777-1787): the cover icon is yellow on 0.7 cover and green on 0.5 cover
// (common/data.py COVER_TYPES)
const STRONG_COVER = new Set([
  "stoneWall",
  "logPile",
  "sandBags",
  "sandBagsUS",
  "townWall",
  "sandBagsUrban",
  "sandBagsUrban_german",
]);
const GREEN = 6723840;
const YELLOW = 16763904;
const STAR_FADE = 0.3;
// soldierRollOvers (F6:6106-6173): the rings come up to 30 % and the leader's health bar and cover icon to full in
// 0.2 seconds; on the way out the ring and bar go over 0.3 seconds and the icon over 0.2
const RING_ALPHA = 30;
const SHOW_SECONDS = 0.2;
const HIDE_SECONDS = 0.3;
const ICON_HIDE_SECONDS = 0.2;
const DEATH_FADE = 0.3;
// The wreck (F6:4626-4706): the damage clip fades in over 3 seconds, and each fire goes out over 6 seconds, 5 to 14
// seconds on; the first two burn from a random frame, a tank's other two 1 in 2 each
const WRECK_IN = 3;
const FIRE_OUT = 6;
const FIRE_DELAY = 5;
const FIRE_DELAY_SPREAD = 10;
const FIRE_FRAMES = 45;
const ENGINE_FADE = 2;
// rotateTankWheels (F6:9932-9941, tankWheelSpeed F6:11839): the big wheels turn half as fast as the small ones, and a
// tank creeping while engaging turns them at half speed (F6:3220, 3237)
const WHEEL_SPEED = 10;
const BIG_WHEELS = ["frontWheel", "backWheel"];
const SMALL_WHEELS = [1, 2, 3, 4, 5, 6].map((k) => `smallWheel${k}`);

// Flash's random(n): a whole number from 0 to n - 1. Only for what the page draws
function random(n) {
  return Math.floor(Math.random() * n);
}

function hide(node) {
  node.visible = false;
}

function pick(count) {
  return (node) => node.gotoAndStop(random(count) + 1);
}

// The 1 in 2 tracer streak of sprites 644 and 648, frame 2: visible, stretched and tilted a little at random
function tracerStreak(node) {
  node.visible = false;
  if (random(2) === 0) {
    node.visible = true;
    node.scale.x = (random(90) + 130) / 100;
    node.angle += random(4) - 2;
  }
}

// A damage smoke (sprite 870 in the damage clips 871, 912 and 928): moved a little and sized at random
function smoke(shift, offset, spread, low) {
  return (node) => {
    node.x += shift ? random(shift) - offset : 0;
    node.scale.set((random(spread) + low) / 100, (random(spread) + low) / 100);
  };
}

function moveY(spread) {
  return (node) => {
    node.y += random(spread) - spread / 2;
  };
}

// The parts' onClipEvent(load) placement scripts, by "parent sprite:part character:depth@frame it was placed on"
const PLACEMENTS = {
  // S666: the collision box and backing, ring and health bar hidden or see-through; on the deaths the range finder
  // hidden, the blood pool moved a little, and the helmet and weapon gone on the exploded and flat deaths
  "666:23:131@1": hide,
  "666:23:137@1": (node) => {
    node.alpha = 0;
  },
  "666:596:129@1": hide,
  "666:601:139@1": hide,
  "666:23:133@439": hide,
  "666:23:133@1065": hide,
  "666:23:133@1463": hide,
  "666:649:135@1065": moveY(10),
  "666:649:135@1676": moveY(20),
  "666:501:35@1463": hide,
  "666:594:65@1463": hide,
  "666:501:35@1704": hide,
  "666:594:65@1704": hide,
  // The head (483) at one of its 10 faces with its blood hidden, the helmet's (501) badge at one of 4, the torso's
  // (545) blood hidden and its cloth at one of 2
  "483:479:5@1": pick(10),
  "483:481:7@1": hide,
  "501:489:2@1": pick(4),
  "501:492:2@15": pick(4),
  "501:489:2@29": pick(4),
  "501:489:2@46": pick(4),
  "545:481:10@1": hide,
  "545:528:1@1": pick(2),
  "545:537:1@83": pick(2),
  // The muzzle flashes (555, 571, 575, 576) and tracers (644, 648): their collision part hidden, the flash at one of
  // 5 pictures, a tracer a streak 1 time in 2
  "555:548:1@1": hide,
  "555:554:1@2": pick(5),
  "571:548:1@1": hide,
  "575:548:1@1": hide,
  "576:548:1@1": hide,
  "644:548:1@1": hide,
  "648:548:1@1": hide,
  "644:643:1@2": tracerStreak,
  "648:647:1@2": tracerStreak,
  // The tank (913): collision box, health bar and damage clip hidden, the ricochets' (718) sparks hidden until a hit
  "913:23:33@1": hide,
  "913:601:35@1": hide,
  "913:871:73@1": hide,
  "913:912:73@18": hide,
  "718:406:1@1": hide,
  "871:870:1@1": smoke(60, 20, 60, 70),
  "871:870:3@1": smoke(60, 20, 60, 70),
  "912:870:2@1": smoke(60, 20, 60, 70),
  "912:870:5@1": smoke(60, 20, 60, 70),
  // The bunker (929): collision box, health bar and damage clip hidden; the damage clip's (928) three smokes
  "929:23:39@1": hide,
  "929:601:41@1": hide,
  "929:928:80@1": hide,
  "928:870:1@1": smoke(0, 0, 90, 70),
  "928:870:3@1": smoke(60, 30, 60, 90),
  "928:870:5@1": smoke(60, 20, 90, 70),
};

// The position a soldier first seen on this frame is guessed to hold
function positionAt(frame) {
  const range = POSITION_RANGES.find(([, from, to]) => frame >= from && frame <= to);
  return range ? range[0] : "standing";
}

// A snap's members by id: { row, squad }, made once per snap. A squad row holds its members at 8
function indexOf(snap) {
  if (!snap.index) {
    snap.index = new Map();
    for (const squad of snap.s.q) {
      for (const row of squad[8]) {
        snap.index.set(row[0], { row, squad });
      }
    }
  }
  return snap.index;
}

function isArmour(squad) {
  return squad[2] === TANK_SLOT || squad[2] === BUNKER_SLOT;
}

// A soldier row's newest jump the drawing has reached by step n, as [frame, playing, stamp], or null. The row holds
// the newest jump at 3 to 5 and the jumps of the steps before it from 8 on, three numbers each, newest first, so a
// drawn step between two jumps of one update still gets the earlier one
function jumpAt(row, n) {
  for (let at = 3; at < row.length; at = at === 3 ? 8 : at + 3) {
    if (row[at + 2] <= n) {
      return [row[at], row[at + 1], row[at + 2]];
    }
  }
  return null;
}

// The frame a part was placed on: the first frame of its sprite holding that placement, kept per sprite
const placedFrames = new Map();
function placedOn(clip, depth, pid) {
  const key = `${clip.charId}:${depth}:${pid}`;
  if (!placedFrames.has(key)) {
    const index = clip.lists.findIndex((list) => list.some((entry) => entry.d === depth && entry.pid === pid));
    placedFrames.set(key, index + 1);
  }
  return placedFrames.get(key);
}

// The turret turn a frame belongs to: the turret's label at or before it (sprites 711, 910, 924)
function turnStart(turret, frame) {
  let start = 1;
  for (const at of Object.values(turret.def.labels ?? {})) {
    if (at <= frame && at > start) {
      start = at;
    }
  }
  return start;
}

export class Units {
  constructor(field) {
    this.field = field;
    // Member id -> unit: { id, side, kind, type, squadId, clip, jump, seen, dead, diedAt, ... }
    this.members = new Map();
    // Squad id -> { ever: member ids ever in the drawn update's row, order: its members in it, near, rolled,
    // selected, band, icon }
    this.squads = new Map();
    // Members whose bodies are gone, never made again
    this.gone = new Set();
    this.world = null;
    this.wire = null;
    this.you = null;
    this.ended = false;
    // The step and kind of the newest blast drawn: an air strike's deaths are never thrown (F6:4721)
    this.lastBlast = null;
    this.placed = new WeakSet();
    this.deathListeners = [];
    this.advanceListeners = [];
    this.suppressListeners = [];
    this.selectListeners = [];
    // Where the finger that may become a tap on a soldier went down
    this.touchDown = null;
    // True while the tick being played is one the drawing leapt over or the whole battle on a rejoin: nothing is said
    this.quiet = false;
    field.onLoad((battle) => this.load(battle));
    field.onDrawnStep((n, jumped) => this.tick(n, jumped));
    field.onDraw(() => this.place());
    field.onClear(() => this.reset());
    field.onEvent("blast", (event) => {
      this.lastBlast = [event[0], event[2]];
    });
    field.onEvent("die", (event, quiet) => this.died(event, quiet));
    field.onEvent("tankdie", (event) => this.tankDied(event));
    field.onEvent("end", () => {
      this.ended = true;
    });
  }

  static art() {
    return ["soldier", "tank", "bunker"];
  }

  // ---------- What other modules use ----------

  soldier(id) {
    const unit = this.members.get(id);
    return unit?.kind === "soldier" ? unit.clip : null;
  }

  // A tank's or the bunker's clip
  tank(id) {
    const unit = this.members.get(id);
    return unit?.kind === "tank" ? unit.clip : null;
  }

  // The squad id a member belongs to, or null
  squadOf(memberId) {
    return this.members.get(memberId)?.squadId ?? null;
  }

  // The squad's row in the update the drawing is on (view.py squad_row), or null once it is gone
  squadRow(squadId) {
    return this.field.snaps[0]?.s.q.find((row) => row[0] === squadId) ?? null;
  }

  // A selected squad (showUnitControls' caller, F6:6114-6134) keeps its rings, its leader's health bar and cover icon
  // until it is deselected (deselectAll, F6:6177-6190), whatever the pointer does
  ring(squadId, on) {
    const squad = this.squadFor(squadId);
    squad.selected = on;
    if (on) {
      this.lightSquad(squad);
    } else {
      this.dimSquad(squad);
    }
  }

  // fn(unit, how, exploded, quiet) as a soldier dies, before its death animation starts: how 0 bullet, 1 blast;
  // exploded when it plays the exploded death, whose body flies (bodyRagdoll)
  onDeath(fn) {
    this.deathListeners.push(fn);
  }

  // fn(unit) when a squad's leader climbs out of cover: the moment the original calls "advance"
  onAdvance(fn) {
    this.advanceListeners.push(fn);
  }

  // fn(side) when a squad of that side starts Suppressing Fire (its flag turns on in the update)
  onSuppress(fn) {
    this.suppressListeners.push(fn);
  }

  // fn(squadId) when the player presses one of their own soldiers: a mouse selects on the press (soldierRollOvers'
  // onPress, F6:6111), a finger on its lift, unless it was a drag that scrolled the field
  onSelect(fn) {
    this.selectListeners.push(fn);
  }

  // The squad's leader as a unit (its first living member), or null
  leader(squadId) {
    const squad = this.squads.get(squadId);
    return squad ? (this.squadUnits(squad)[0] ?? null) : null;
  }

  // The leader's health bar in percent, as the INTEL panel reads it (updateSelectedUnitInfo F6:6531), or null
  health(squadId) {
    const bar = this.leader(squadId)?.clip.child("healthBar")?.child("bar");
    return bar ? Math.round(bar.scale.x * 100) : null;
  }

  // ---------- The battle ----------

  get lib() {
    return this.field.page.lib;
  }

  load(battle) {
    if (this.world !== this.field.world) {
      this.reset();
      this.world = this.field.world;
    }
    this.you = battle.you;
    this.covers = battle.map.covers;
    this.ended = battle.result !== null && battle.result !== undefined;
    this.lib.scripts.set(SOLDIER_SPRITE, (clip, frame) => this.frameScript(clip, frame));
    // The full battle is the state after its step's last tick: the members it holds come at once
    this.tick(battle.step - 1, true);
    this.place();
  }

  reset() {
    for (const unit of this.members.values()) {
      if (unit.engine) {
        sound.stopLoop(unit.engine);
      }
    }
    this.members.clear();
    this.squads.clear();
    this.gone.clear();
    this.world = null;
    this.wire = null;
    this.lastBlast = null;
  }

  // ---------- Each drawn step ----------

  // The bot's tick n, after the world's clips stepped: members arrive, the jumps of tick n play, bodies fade and
  // sink, wheels turn, the depth sort and the squads' bars, icons and stars follow
  tick(n, jumped = false) {
    if (!this.world || this.world !== this.field.world) {
      return;
    }
    this.quiet = jumped;
    for (const unit of this.members.values()) {
      this.loopLater(unit);
    }
    const [latest, seen] = this.latestRows(n);
    for (const [id, found] of latest) {
      this.follow(id, found, n);
    }
    for (const [id, step] of seen) {
      const unit = this.members.get(id);
      if (unit) {
        unit.seen = step;
      }
    }
    for (const unit of [...this.members.values()]) {
      this.settle(unit.clip);
      this.age(unit, n);
      if (unit.kind === "tank" && !unit.bunker && !unit.wrecked) {
        this.turnWheels(unit);
      }
    }
    this.squadLooks();
    if (n % SORT_EVERY === 0 && !this.ended) {
      this.sortDepths();
    }
    this.quiet = false;
  }

  // Each member's newest row the drawing has reached (a soldier's with the newest jump it holds by step n, a tank's
  // whose first gun stamp has come), and the newest update each member is in, from the oldest update kept to the
  // newest
  latestRows(n) {
    const latest = new Map();
    const seen = new Map();
    for (const snap of this.field.snaps) {
      for (const [id, found] of indexOf(snap)) {
        seen.set(id, snap.step);
        if (isArmour(found.squad)) {
          if (Math.min(found.row[4], found.row[5]) <= n) {
            latest.set(id, found);
          }
          continue;
        }
        const jump = jumpAt(found.row, n);
        if (jump && jump[2] >= (latest.get(id)?.jump[2] ?? -Infinity)) {
          latest.set(id, { ...found, jump });
        }
      }
    }
    return [latest, seen];
  }

  follow(id, found, n) {
    if (this.gone.has(id)) {
      return;
    }
    let unit = this.members.get(id);
    if (!unit) {
      unit = this.make(id, found, n);
    }
    if (unit.dead) {
      return;
    }
    unit.squadId = found.squad[0];
    unit.state = STATES[found.squad[3]];
    if (unit.kind === "tank") {
      this.followTank(unit, found.row, n);
    } else {
      this.followSoldier(unit, found.jump, n);
    }
  }

  // A bot jump the clip hasn't made yet: made now, then played forward by the ticks since it happened
  followSoldier(unit, jump, n) {
    const [frame, playing, stamp] = jump;
    const key = `${stamp}:${frame}:${playing}`;
    if (unit.jump === key) {
      return;
    }
    unit.jump = key;
    const clip = unit.clip;
    unit.jumping = true;
    if (playing) {
      clip.gotoAndPlay(frame);
    } else {
      clip.gotoAndStop(frame);
    }
    unit.jumping = false;
    this.settle(clip);
    this.catchUp(clip, n - stamp);
    if (playing && !this.quiet && frame === EXIT_COVER && this.squads.get(unit.squadId)?.order?.[0] === unit.id) {
      this.advanceListeners.forEach((fn) => fn(unit));
    }
  }

  // The bot's tick runs a new clip's first frame for a whole tick, and steps every other clip once a tick: the steps
  // a jump missed play now, stopping early once the clip stops
  catchUp(clip, steps) {
    const count = Math.min(steps, MOST_CATCH_UP);
    for (let k = 0; k < count && (clip.playing || clip.fresh || clip.unit?.loopDue); k += 1) {
      clip.advance();
      this.loopLater(clip.unit);
      this.settle(clip);
    }
  }

  // The guns and the turret play from the bot's stamps: the main gun's firing is its reload (sprite 700), the machine
  // gun's a shot (sprite 696, the bunker's 923), and the turret a turn (sprites 711, 910, 924). All sit in the turret
  followTank(unit, row, n) {
    unit.health = row[3] / 10;
    const turret = unit.clip.child("turret");
    for (const [name, index] of [
      ["mainGun", 4],
      ["secondGun", 5],
    ]) {
      const [stamp] = this.newestStamp(unit, index, n);
      if (stamp > unit.guns[name]) {
        unit.guns[name] = stamp;
        const gun = turret?.child(name);
        if (gun) {
          gun.gotoAndPlay("firing");
          this.catchUp(gun, n - stamp);
        }
      }
    }
    this.followTurret(unit, turret, n);
    if (unit.state === "tankMoving" && !unit.engine) {
      // The engine starts on the tank's first moving step and runs until it is destroyed (F6:3168-3172)
      unit.engine = `tank${unit.id}`;
      sound.loop("sound_tankMoving", unit.engine);
    }
  }

  // The newest stamp at `index` of the member's rows that the drawing has reached by step n, from any update kept,
  // with the row and the step of the update it came in
  newestStamp(unit, index, n) {
    let best = [-Infinity, null, null];
    for (const snap of this.field.snaps) {
      const row = indexOf(snap).get(unit.id)?.row;
      if (row && row[index] <= n && row[index] > best[0]) {
        best = [row[index], row, snap.step];
      }
    }
    return best;
  }

  // A turret turn the bot started: the row says the frame the turret was on when the update was taken, which lies in
  // the turn it started at the stamp, so the turn's label is the one at or before that frame
  followTurret(unit, turret, n) {
    const [stamp, row] = this.newestStamp(unit, 9, n);
    if (!turret || stamp <= unit.turretStamp) {
      return;
    }
    unit.turretStamp = stamp;
    turret.gotoAndPlay(turnStart(turret, row[7]));
    this.settle(turret);
    this.catchUp(turret, n - stamp);
  }

  // rotateTankWheels (F6:9932-9941): every step a tank moves, its wheels turn. It always moves while in tankMoving, and
  // creeps at half speed in tankEngaging (only the picture turns, so a creep shows where the tank moved)
  turnWheels(unit) {
    let speed = 0;
    if (unit.state === "tankMoving") {
      speed = WHEEL_SPEED;
    } else if (unit.state === "tankEngaging" && unit.wheelX !== undefined && unit.x !== unit.wheelX) {
      speed = WHEEL_SPEED / 2;
    }
    unit.wheelX = unit.x;
    const body = unit.clip.child("tankBody");
    if (!speed || !body) {
      return;
    }
    BIG_WHEELS.forEach((name) => {
      const wheel = body.child(name);
      if (wheel) {
        wheel.angle += speed / 2;
      }
    });
    SMALL_WHEELS.forEach((name) => {
      const wheel = body.child(name);
      if (wheel) {
        wheel.angle += speed;
      }
    });
  }

  // A second after death a body goes below the living, and 15 seconds after it fades and goes; a member that left
  // every update without dying is dropped
  age(unit, n) {
    if (unit.dead) {
      if (!unit.sunk && n >= unit.diedAt + SORT_DEAD_STEPS) {
        unit.sunk = true;
        this.sink(unit);
      }
      if (!unit.fading && n >= unit.diedAt + CLEAR_DEAD_STEPS) {
        unit.fading = true;
        tweens.alphaTo(unit.clip, 0, BODY_FADE, "linear", 0, () => this.drop(unit));
      }
      return;
    }
    if (n > unit.seen + GONE_AFTER && !unit.wrecked) {
      this.drop(unit);
    }
  }

  // sortDeadSoldiers (F6:7933-7936): the body, or the wreck, at the depth it last had among the living
  sink(unit) {
    if (unit.clip.destroyed) {
      return;
    }
    this.field.layer("deadSoldiers").addChild(unit.clip);
    unit.clip.zIndex = unit.depth;
  }

  drop(unit) {
    if (unit.engine) {
      sound.stopLoop(unit.engine);
    }
    if (!unit.clip.destroyed) {
      unit.clip.destroy({ children: true });
    }
    this.members.delete(unit.id);
    this.gone.add(unit.id);
  }

  // ---------- Making members ----------

  make(id, found, n) {
    const [squadId, sideIndex, slot] = found.squad;
    const side = SIDES[sideIndex];
    const armour = slot === TANK_SLOT || slot === BUNKER_SLOT;
    const row = found.row;
    const unit = {
      id,
      side,
      kind: armour ? "tank" : "soldier",
      bunker: slot === BUNKER_SLOT,
      type: armour ? (slot === BUNKER_SLOT ? "bunkerBase" : "tankMarkIV") : SOLDIER_TYPES[row[7]],
      squadId,
      slot,
      clip: null,
      jump: null,
      seen: -1,
      dead: false,
      diedAt: 0,
      fading: false,
      sunk: false,
      depth: row[2] / 10,
      x: row[1] / 10,
      y: row[2] / 10,
      // Where a soldier first stood: the ground a thrown body comes down on (F6:1752)
      ground: row[2] / 10,
    };
    unit.clip = armour ? this.makeTank(unit, row, n) : this.makeSoldier(unit, row, found.jump);
    unit.clip.unit = unit;
    unit.clip.position.set(unit.x, unit.y);
    this.field.layer("soldiers").addChild(unit.clip);
    unit.clip.zIndex = id;
    this.members.set(id, unit);
    if (unit.wrecked) {
      this.sink(unit);
    } else if (side === this.you) {
      this.rollOvers(unit);
    }
    return unit;
  }

  squadFor(squadId) {
    let squad = this.squads.get(squadId);
    if (!squad) {
      squad = { ever: new Set(), order: [], near: false, rolled: false, selected: false, band: null, icon: null };
      this.squads.set(squadId, squad);
    }
    return squad;
  }

  // createSoldier (F6:1634-1776): sized 125 to 134 %, the German one turned around, its cover icon hidden, its
  // officer star only on an officer (the German's own star), its weapon and uniform. A new member's timeline holds its
  // first frame for a whole tick, and its first jump into the run cycle (frames 20 to 34) comes on that tick. A member
  // first seen on a later jump (a rejoin) is past that
  makeSoldier(unit, row, jump) {
    const clip = this.lib.make(SOLDIER_SPRITE);
    this.trackPosition(unit, clip);
    const size = row[6] / 100;
    clip.scale.set(unit.side === "german" ? -size : size, size);
    const icon = clip.child("coverIcon");
    if (icon) {
      icon.visible = false;
    }
    const star = clip.child("officerStar");
    if (star && unit.slot !== OFFICER_SLOT) {
      star.visible = false;
    } else if (star && unit.side === "german") {
      star.gotoAndStop("german_officer");
    }
    clip.child("weapon")?.gotoAndStop(MAIN_WEAPON[unit.side][unit.type]);
    for (const name of BODY_PARTS) {
      clip.child(name)?.gotoAndStop(`${unit.side}_${unit.type}`);
    }
    this.settle(clip);
    const spawning = jump[1] && jump[0] >= SPAWN_FRAMES[0] && jump[0] <= SPAWN_FRAMES[1];
    if (!spawning) {
      clip.fresh = false;
    }
    unit.position = spawning ? "standing" : positionAt(jump[0]);
    return clip;
  }

  // The tank at its side's frame or the bunker, at full size, the German one turned around (F6:1641-1650, 1756). A
  // tank already wrecked (a rejoin) shows its wreck at once
  makeTank(unit, row, n) {
    const clip = this.lib.make(this.lib.exported(unit.bunker ? "bunker" : "tank"));
    if (!unit.bunker) {
      clip.gotoAndStop(unit.side);
    }
    clip.scale.set(unit.side === "german" ? -1 : 1, 1);
    this.settle(clip);
    const created = Math.min(row[4], row[5]);
    unit.guns = { mainGun: created, secondGun: created };
    // The turret's newest turn plays forward from its stamp on the first update the tank is followed in
    unit.turretStamp = created;
    unit.health = row[3] / 10;
    unit.engine = null;
    unit.wrecked = false;
    this.catchUp(clip, n - created);
    if (row[6]) {
      unit.wrecked = true;
      this.wreck(unit, clip, true);
    }
    return clip;
  }

  // The soldier's position follows the frames that set it, however the playhead arrives on them (a step, a jump or a
  // frame script's own jump), set before the rest of that frame's script runs
  trackPosition(unit, clip) {
    const enter = clip.enter.bind(clip);
    clip.enter = (frame) => {
      if (POSITION_SETS[frame]) {
        unit.position = POSITION_SETS[frame];
      }
      enter(frame);
    };
  }

  // Runs each placed part's placement script once, the tick it first shows, all the way down
  settle(clip) {
    for (const [depth, slot] of clip.slots ?? []) {
      const node = slot.node;
      if (node.destroyed) {
        continue;
      }
      if (!this.placed.has(node)) {
        this.placed.add(node);
        const key = `${clip.charId}:${node.charId}:${depth}@${placedOn(clip, depth, slot.pid)}`;
        PLACEMENTS[key]?.(node);
      }
      if (node.slots) {
        this.settle(node);
      }
    }
  }

  // S666's frame scripts that are the page's to run (the bot runs its own copy of each)
  frameScript(clip, frame) {
    if (frame === RUN_LOOP) {
      this.runLoop(clip);
    } else if (frame === MORTAR_FIRE) {
      clip.child("weapon")?.child("muzzleFlash")?.play();
    } else if (frame === MORTAR_END) {
      clip.stop();
    }
  }

  // S666/frame_34: at the end of a run cycle a living soldier runs on. The bot jumps the soldier here too, and that
  // jump replaces this guess on the same tick; a soldier stopping to fire or getting into cover stops here, and the
  // bot's stop comes on the same tick. Once the battle is over the frame does nothing and the playhead runs on
  runLoop(clip) {
    const unit = clip.unit;
    if (this.ended || !unit) {
      return;
    }
    if (unit.jumping) {
      unit.loopDue = true;
      return;
    }
    if (!unit.dead) {
      clip.gotoAndStop("rifle_run");
      clip.play();
    } else {
      clip.stop();
    }
  }

  // The bot runs a frame hook its timeline reached by a jump on the timeline's next step (common/timeline.py
  // advance), so a jump onto frame 34 loops the run on the next drawn step, after the clip stepped, wherever it stepped to
  loopLater(unit) {
    if (unit?.loopDue) {
      unit.loopDue = false;
      if (!unit.dead) {
        this.runLoop(unit.clip);
      }
    }
  }

  // ---------- Deaths and wrecks ----------

  // A soldier died on this step: its death animation by its position, or half of blast deaths (never an air strike's)
  // the exploded one; the ring, bar, icon and star fade, and the pointer lets go of it (F6:4448-4470, 4709-4760)
  died(event, quiet = false) {
    const [step, , id, how] = event;
    const unit = this.members.get(id);
    if (!unit || unit.dead || unit.kind !== "soldier") {
      return;
    }
    unit.dead = true;
    unit.diedAt = step;
    const clip = unit.clip;
    const air = this.lastBlast?.[0] === step && this.lastBlast[1] === "airSupport";
    // A death whose moment has passed (a jump) is a body lying where it fell: nothing flies
    const exploded = how === HOW_BLAST && !quiet && !air && random(2) > 0;
    // Blood and limbs come before the animation, as the original sets them
    for (const fn of this.deathListeners) {
      fn(unit, how, exploded, quiet);
    }
    clip.gotoAndPlay(exploded ? "exploded_death" : `${unit.position}_death`);
    this.settle(clip);
    for (const name of ["selectedRing", "healthBar", "coverIcon", "officerStar"]) {
      const part = clip.child(name);
      if (part) {
        tweens.alphaTo(part, 0, DEATH_FADE);
      }
    }
    this.letGo(clip);
  }

  letGo(clip) {
    for (const name of ["onPress", "onRelease", "onReleaseOutside", "onRollOver", "onRollOut"]) {
      if (clip.handlers[name]) {
        clip.setHandler(name, null);
      }
    }
  }

  tankDied(event) {
    const unit = this.members.get(event[2]);
    if (unit?.kind === "tank" && !unit.wrecked) {
      unit.wrecked = true;
      this.wreck(unit, unit.clip, false);
      this.sink(unit);
    }
  }

  // The burning wreck (F6:4626-4706): the body at "destroyed", the turret off, the bar and icon gone, the damage clip
  // fading in with its fires; the engine fades out over 2 seconds and the pointer lets go of it
  wreck(unit, clip, now) {
    clip.child("tankBody")?.gotoAndStop("destroyed");
    clip.child("turret")?.gotoAndStop("off");
    for (const name of ["healthBar", "coverIcon"]) {
      const part = clip.child(name);
      if (part) {
        part.alpha = 0;
      }
    }
    const damage = clip.child("damageClip");
    if (damage) {
      damage.visible = true;
      damage.alpha = 0;
      tweens.alphaTo(damage, 100, now ? 0 : WRECK_IN);
      this.burn(damage, !unit.bunker);
    }
    if (unit.engine) {
      sound.stopLoop(unit.engine, ENGINE_FADE);
      unit.engine = null;
    }
    this.letGo(clip);
  }

  // Each fire goes out after a while; the first two burn from a random frame, and a tank's other two 1 in 2 each
  // (the bunker's third keeps its own frame)
  burn(damage, tank) {
    for (let k = 1; k <= 4; k += 1) {
      const fire = damage.child(`fireAnim${k}`);
      if (!fire) {
        continue;
      }
      const delay = FIRE_DELAY + random(FIRE_DELAY_SPREAD);
      tweens.alphaTo(fire, 0, FIRE_OUT, "easeOutSine", delay, () => fire.removeMovieClip());
      if (k <= 2 || (tank && random(2) > 0)) {
        fire.child("fireAnim")?.gotoAndPlay(random(FIRE_FRAMES) + 1);
      } else if (tank) {
        fire.visible = false;
      }
    }
  }

  // ---------- Squad looks ----------

  // Every squad on the field now: its leader's health bar (squadAI F6:2010-2027), the cover icon's colour while the
  // leader is in its cover (F6:2028-2031), and the silver star while it is near an officer (findOfficer F6:3606-3645,
  // flags bit 0)
  squadLooks() {
    const snap = this.field.snaps[0];
    if (!snap) {
      return;
    }
    for (const row of snap.s.q) {
      const leader = row[8].map((member) => this.members.get(member[0])).find((unit) => unit && !unit.dead);
      if (!leader || leader.wrecked) {
        continue;
      }
      const squad = this.squadFor(row[0]);
      squad.order = row[8].map((member) => member[0]);
      squad.order.forEach((id) => squad.ever.add(id));
      this.suppressing(squad, row, leader);
      this.healthBar(leader, row, squad);
      if (leader.kind === "soldier") {
        leader.inCover = this.inCover(leader, row);
        this.coverIcon(leader, row, squad);
        this.officerStar(leader, row, squad);
      }
    }
  }

  // A squad's Suppressing Fire flag (bit 6) turning on is its order being given; the first update a squad is seen in
  // only sets the flag it was found with
  suppressing(squad, row, leader) {
    const on = (row[4] & SUPPRESSING_FLAG) !== 0;
    if (on && squad.suppressing === false && !this.quiet) {
      this.suppressListeners.forEach((fn) => fn(leader.side));
    }
    squad.suppressing = on;
  }

  // The leader is in its cover once it has taken its pose there (the squad In cover and holding a cover)
  inCover(leader, row) {
    const frame = leader.clip.frame;
    return STATES[row[3]] === "entrench" && row[7] >= 0 && frame > UPRIGHT_LAST && frame !== STOP_IDLE;
  }

  healthBar(leader, row, squad) {
    const bar = leader.clip.child("healthBar")?.child("bar");
    if (!bar) {
      return;
    }
    let percent = Math.round((row[8].length / Math.max(1, squad.ever.size)) * 100);
    if (leader.kind === "tank" && !leader.bunker) {
      percent = Math.round((leader.health / ARMOUR_HEALTH[leader.side]) * 100);
    }
    bar.scale.x = percent / 100;
    const band = percent < BAR_RED ? RED : percent < BAR_AMBER ? AMBER : null;
    if (band !== null && squad.band !== band) {
      squad.band = band;
      tweens.colorTo(bar, band, BAR_COLOR_SECONDS);
    }
  }

  // checkCoverRating (F6:1777-1787)
  coverIcon(leader, row, squad) {
    const kind = this.covers?.[row[7]]?.[2];
    if (!leader.inCover || kind === undefined) {
      return;
    }
    const colour = STRONG_COVER.has(kind) ? GREEN : YELLOW;
    const icon = leader.clip.child("coverIcon")?.child("icon");
    if (icon && squad.icon !== `${leader.id}:${colour}`) {
      squad.icon = `${leader.id}:${colour}`;
      tweens.colorTo(icon, colour);
    }
  }

  officerStar(leader, row, squad) {
    const star = leader.clip.child("officerStar");
    const near = (row[4] & 1) === 1;
    if (!star || row[2] === OFFICER_SLOT || near === squad.near) {
      return;
    }
    squad.near = near;
    if (near) {
      star.visible = true;
      star.gotoAndStop("silver");
      star.alpha = 0;
      tweens.alphaTo(star, 100, STAR_FADE);
    } else {
      tweens.alphaTo(star, 0, STAR_FADE);
    }
  }

  // ---------- Depths ----------

  // sortSoldierDepths (F6:7866-7932): the midground strips, every living member (American squads then German, each
  // walked newest first), the cover and the wire, ordered by depth with ties kept in that order, onto the sorted layer.
  // A member's depth is its y now, the map's clips keep the y they were made at. Wrecks are left where they lie: the
  // original pushes their squads, which hold no depth to sort by
  sortDepths() {
    const snap = this.field.snaps[0];
    // The wire pieces in the order they were made, kept once they leave their own layer
    this.wire ??= [...this.field.layer("wire").children];
    const living = [];
    for (const sideIndex of [0, 1]) {
      const rows = snap.s.q.filter((row) => row[1] === sideIndex).reverse();
      for (const row of rows) {
        for (const member of [...row[8]].reverse()) {
          const unit = this.members.get(member[0]);
          if (unit && !unit.dead && !unit.wrecked) {
            unit.depth = unit.clip.y;
            living.push(unit.clip);
          }
        }
      }
    }
    const field = this.field;
    const before = [...field.midGround].reverse();
    const after = [...[...field.covers].reverse(), ...[...this.wire].reverse()];
    const list = [...before, ...living, ...after].filter((node) => !node.destroyed);
    const sorted = list.map((node) => [node, node.unit ? node.unit.depth : (node.depth ?? node.y)]);
    sorted.sort((a, b) => a[1] - b[1]);
    const layer = field.layer("soldiersSorted");
    sorted.forEach(([node], index) => {
      if (node.parent !== layer) {
        layer.addChild(node);
      }
      node.zIndex = index;
    });
  }

  // ---------- Positions ----------

  // Each living member slides between the two updates around the drawn clock
  place() {
    const { a, b, t } = this.field.around();
    if (!a) {
      return;
    }
    const from = indexOf(a);
    const to = indexOf(b);
    for (const unit of this.members.values()) {
      if (unit.dead || unit.wrecked) {
        continue;
      }
      const start = from.get(unit.id)?.row ?? to.get(unit.id)?.row;
      if (!start) {
        continue;
      }
      const end = to.get(unit.id)?.row ?? start;
      unit.x = (start[1] + (end[1] - start[1]) * t) / 10;
      unit.y = (start[2] + (end[2] - start[2]) * t) / 10;
      unit.clip.position.set(unit.x, unit.y);
    }
  }

  // ---------- The pointer ----------

  // soldierRollOvers (F6:6106-6173): over one of your own soldiers or tanks, its squad's rings come up and its
  // leader's health bar shows, with the cover icon while the leader is in cover. A finger resting on it does the same.
  // Pressing it selects the squad
  rollOvers(unit) {
    const clip = unit.clip;
    clip.useHandCursor = false;
    clip.setHandler("onRollOver", () => this.showSquad(unit.squadId, true));
    clip.setHandler("onRollOut", () => this.showSquad(unit.squadId, false));
    clip.setHandler("onPress", (e) => {
      if (e.pointerType !== "touch") {
        this.select(unit.squadId);
        return;
      }
      this.touchDown = { x: e.global.x, y: e.global.y };
      this.showSquad(unit.squadId, true);
    });
    clip.setHandler("onRelease", (e) => {
      if (e.pointerType !== "touch") {
        return;
      }
      if (this.touchDown && !this.field.swept(this.touchDown, e)) {
        this.select(unit.squadId);
      }
      this.touchDown = null;
      this.showSquad(unit.squadId, false);
    });
    clip.setHandler("onReleaseOutside", (e) => {
      if (e.pointerType === "touch") {
        this.touchDown = null;
        this.showSquad(unit.squadId, false);
      }
    });
  }

  select(squadId) {
    this.selectListeners.forEach((fn) => fn(squadId));
  }

  showSquad(squadId, on) {
    const squad = this.squadFor(squadId);
    squad.rolled = on;
    if (on) {
      this.lightSquad(squad);
    } else if (!squad.selected) {
      this.dimSquad(squad);
    }
  }

  // The squad's members now, leader first, as their units
  squadUnits(squad) {
    return squad.order
      .map((id) => this.members.get(id))
      .filter((unit) => unit && !unit.dead && !unit.clip.destroyed);
  }

  lightSquad(squad) {
    this.squadUnits(squad).forEach((unit, index) => {
      if (index === 0) {
        const parts = [unit.clip.child("healthBar"), unit.inCover ? unit.clip.child("coverIcon") : null];
        parts.filter(Boolean).forEach((part) => {
          part.visible = true;
          tweens.alphaTo(part, 100, SHOW_SECONDS);
        });
      }
      const ring = unit.clip.child("selectedRing");
      if (ring) {
        ring.visible = true;
        tweens.alphaTo(ring, RING_ALPHA, SHOW_SECONDS);
      }
    });
  }

  dimSquad(squad) {
    this.squadUnits(squad).forEach((unit, index) => {
      const clip = unit.clip;
      if (index === 0) {
        const bar = clip.child("healthBar");
        const icon = clip.child("coverIcon");
        if (bar) {
          tweens.alphaTo(bar, 0, HIDE_SECONDS, "linear");
        }
        if (icon) {
          tweens.alphaTo(icon, 0, ICON_HIDE_SECONDS);
        }
      }
      const ring = clip.child("selectedRing");
      if (ring) {
        tweens.alphaTo(ring, 0, HIDE_SECONDS, "linear");
      }
    });
  }
}
