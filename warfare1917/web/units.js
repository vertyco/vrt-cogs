// Soldiers and tanks on the field: one soldier clip (sprite 626) or tank clip (sprite 820) for each member the bot
// sends, dressed the way createSoldier and decorateSoldier dressed them (F5:1130-1250), their bodies after death, the
// depth sorting, and the squad's ring, health bar and officer star.
//
// The bot decides every animation. Each member's row carries the frame the bot last jumped its timeline to, whether
// it played or stopped there, and the step it happened on. When the field's drawing reaches that step the clip makes
// the same jump, and between jumps it steps one frame a drawn step, running the same frame scripts the bot runs, so
// both stay on the same frame. A jump the drawing reaches late is played forward by the steps it missed. Deaths are
// the page's to play (the bot drops the member from its squad): the "die" event starts the body's death animation.
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const FPS = 35;
const SIDES = ["british", "german"];
// common/data.py SOLDIER_TYPES and common/squads.py STATES, in the bot's order: the rows send their positions
const SOLDIER_TYPES = ["rifleman", "grenadier", "machineGunner", "mgAssist", "sharpShooter", "lieutenant", "tankMarkIV"];
const STATES = [
  "moving",
  "engaging",
  "assaultTrench",
  "stopped",
  "entrench",
  "exitTrench",
  "gasMasksOn",
  "gasMasksOff",
  "tankMoving",
  "tankDead",
  "tankEngaging",
  "victory",
  "defeated",
];
const SOLDIER_SPRITE = 626;
const TANK_SLOT = 6;
const OFFICER_SLOT = 5;
// Each soldier type's mainWeapon (F5:7020-7230), a frame label of the weapon part (sprite 449). The snipers' labels
// aren't in it, so their weapon stays on its first frame, as in the original
export const MAIN_WEAPON = {
  british: {
    rifleman: "enfield",
    grenadier: "enfield",
    machineGunner: "lewis",
    mgAssist: "pistol",
    sharpShooter: "enfieldSniper",
    lieutenant: "pistol",
  },
  german: {
    rifleman: "mauser",
    grenadier: "mauser",
    machineGunner: "lewis",
    mgAssist: "pistol",
    sharpShooter: "mauserSniper",
    lieutenant: "pistol",
  },
};
// decorateSoldier (F5:1130-1142): each of these parts goes to its "<side>_<type>" frame
const BODY_PARTS = [
  "helmet",
  "torso",
  "front_upperArm",
  "front_lowerArm",
  "front_upperLeg",
  "front_lowerLeg",
  "back_upperArm",
  "back_lowerArm",
  "back_upperLeg",
  "back_lowerLeg",
];
// The soldier's position, which its frame scripts set as each pose settles (S626 frames 195, 239, 340, 784, 816, 1011,
// 1030): its death animation is "<position>_death". Frames 175-194 and 769-783 are still standing, on the way down
const POSITION_RANGES = [
  ["trench", 195, 339],
  ["trench", 353, 767],
  ["prone", 784, 815],
  ["prone", 821, 1002],
  ["crouch", 1011, 1029],
  ["crouch", 1038, 1248],
];
// sortSoldierDepths runs on the slow tick, every 40 steps from the first (F5:6828-6842)
const SORT_EVERY = 40;
// clearDeadSoldierTime (F5:7274): a body fades over a second, 15 seconds after death (fadeDeadSoldier F5:3079-3087)
const CLEAR_DEAD_STEPS = (15000 * FPS) / 1000;
const BODY_FADE = 1;
// createSoldier's gotoAndPlay(20 + random(15)) (F5:1244): the only jump into these frames
const SPAWN_FRAMES = [20, 34];
// The run cycle (labels rifle_run to frame 38, where S626/frame_38 loops it) and the exit from a trench: a soldier
// starting either calls "advance" (F5:1369, 1915)
const RUN_CYCLE = [19, 38];
const EXIT_TRENCH = 319;
// A jump the drawing reaches late is played forward by at most this many frames (a rejoin long after it)
const MOST_CATCH_UP = 600;
// A member gone from every update without a "die" event (an update lost to a jump) is dropped this many steps later
const GONE_AFTER = 4;
const HOW_BLAST = 1;
// The tank's whole health (F5:7099, 7229), for its health bar (F5:1288-1292)
const TANK_HEALTH = 850;
// The health bar turns amber below 60 % and red below 30 % (F5:1293-1300)
const BAR_AMBER = 60;
const BAR_RED = 30;
const AMBER = 16763904;
const RED = 10027008;
const BAR_COLOR_SECONDS = 0.4;
// The officer star sits beside a leader in a trench and above one in the open (F5:1301-1310)
const STAR_TRENCH = [32, -26];
const STAR_OPEN = [0, -48];
const STAR_FADE = 0.3;
// soldierRollOvers (F5:4155-4188): the ring comes up to 30 % and the leader's health bar to full in 0.2 seconds, and
// both go out over half a second after a second
const RING_ALPHA = 30;
const SHOW_SECONDS = 0.2;
const HIDE_SECONDS = 0.5;
const HIDE_DELAY = 1;
const DEATH_FADE = 0.3;
// The tank wreck (F5:2956-2995): the damage clip fades in over 3 seconds, and each fire burns from a random frame and
// goes out over 6 seconds, 5 to 14 seconds on
const WRECK_IN = 3;
const FIRE_OUT = 6;
const FIRE_DELAY = 5;
const FIRE_DELAY_SPREAD = 10;
const FIRE_FRAMES = 45;
const ENGINE_FADE = 2;
// The tank's painted number (F5:1221)
const TAG_LOW = 10;
const TAG_SPREAD = 40;

// Flash's random(n): a whole number from 0 to n - 1. Only for what the page draws
function random(n) {
  return Math.floor(Math.random() * n);
}

function hide(node) {
  node.visible = false;
}

// The 1 in 2 tracer streak of sprites 516 and 549, frame 2: visible, stretched and tilted a little at random
function tracerStreak(node) {
  node.visible = false;
  if (random(2) === 0) {
    node.visible = true;
    node.scale.x = (random(90) + 130) / 100;
    node.angle += random(4) - 2;
  }
}

// The tank's damage smoke (sprites 811 and 819): moved a little and sized at random
function smoke(node) {
  node.x += random(60) - 20;
  node.scale.set((random(60) + 70) / 100, (random(60) + 70) / 100);
}

// The parts' onClipEvent(load) placement scripts, by "parent sprite:part character:depth", with "@frame" where the
// same placement on another frame has its own script
const PLACEMENTS = {
  // S626: the collision box, range finder, ring and health bar hidden, the backing see-through, the blood pools
  // moved a little, the helmet and weapon gone on the exploded and flat deaths
  "626:43:69": hide,
  "626:43:71": hide,
  "626:43:75": (node) => {
    node.alpha = 0;
  },
  "626:452:66": hide,
  "626:457:77": hide,
  "626:594:73@1216": (node) => {
    node.y += random(10) - 5;
  },
  "626:594:73@1754": (node) => {
    node.y += random(20) - 10;
  },
  "626:439:48@1541": hide,
  "626:439:48@1782": hide,
  "626:449:52@1541": hide,
  "626:449:52@1782": hide,
  // The head (415) at one of its 10 faces, and the blood on the head and torso hidden until a death shows it
  "415:411:5": (node) => node.gotoAndStop(random(10) + 1),
  "415:413:7": hide,
  "427:413:5": hide,
  "445:442:1": hide,
  "1401:1400:9": hide,
  // The tracers (516, 549): hidden at rest, a streak 1 time in 2 when one plays
  "516:442:1": hide,
  "549:442:1": hide,
  "516:515:1": tracerStreak,
  "549:548:1": tracerStreak,
  // The tank (820): collision box, health bar and damage clip hidden, the ricochets' sparks (657) hidden until a hit
  "820:43:25": hide,
  "820:457:27": hide,
  "820:811:65": hide,
  "820:819:65": hide,
  "657:325:1": hide,
  "811:810:2": smoke,
  "811:810:5": smoke,
  "819:810:2": smoke,
  "819:810:5": smoke,
};

// The position a soldier's frame scripts have set by this frame
export function positionAt(frame) {
  const range = POSITION_RANGES.find(([, from, to]) => frame >= from && frame <= to);
  return range ? range[0] : "standing";
}

// A jump from `before` to `frame` that starts a run (into the cycle from outside it: the cycle's own loop doesn't
// count) or leaves a trench
function startsAdvance(before, frame) {
  const [first, last] = RUN_CYCLE;
  const inCycle = (at) => at >= first && at <= last;
  return (inCycle(frame) && !inCycle(before)) || frame === EXIT_TRENCH;
}

// A snap's members by id: { row, squad }, made once per snap
function indexOf(snap) {
  if (!snap.index) {
    snap.index = new Map();
    for (const squad of snap.s.q) {
      for (const row of squad[7]) {
        snap.index.set(row[0], { row, squad });
      }
    }
  }
  return snap.index;
}

function isTankSquad(squad) {
  return squad[2] === TANK_SLOT;
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

export class Units {
  constructor(field) {
    this.field = field;
    // Member id -> unit: { id, side, kind, type, squadId, clip, jump, seen, dead, diedAt, ... }
    this.members = new Map();
    // Squad id -> { ids: member ids ever seen, near: officer star shown, rows: the squad's latest row }
    this.squads = new Map();
    // Members whose bodies are gone, never made again
    this.gone = new Set();
    this.world = null;
    this.wire = null;
    this.you = null;
    this.ended = false;
    this.placed = new WeakSet();
    this.deathListeners = [];
    this.advanceListeners = [];
    // True while the tick being played is one the drawing leapt over or the whole battle on a rejoin: nothing is said
    this.quiet = false;
    field.onLoad((battle) => this.load(battle));
    field.onDrawnStep((n) => this.tick(n));
    field.onDraw(() => this.place());
    field.onClear(() => this.reset());
    field.onEvent("die", (event, quiet) => this.died(event, quiet));
    field.onEvent("tankdie", (event) => this.tankDied(event));
    field.onEvent("end", () => {
      this.ended = true;
    });
  }

  // ---------- What other modules use ----------

  soldier(id) {
    const unit = this.members.get(id);
    return unit?.kind === "soldier" ? unit.clip : null;
  }

  tank(id) {
    const unit = this.members.get(id);
    return unit?.kind === "tank" ? unit.clip : null;
  }

  // The squad id a member belongs to, or null
  squadOf(memberId) {
    return this.members.get(memberId)?.squadId ?? null;
  }

  // fn(unit, how, exploded, quiet) as a soldier dies, before its death animation starts: how 0 bullet, 1 blast, 2 gas;
  // exploded when it plays the exploded death, whose body flies (bodyRagdoll, F5:3204-3318)
  onDeath(fn) {
    this.deathListeners.push(fn);
  }

  // fn(unit) when a soldier starts running or climbs out of a trench: the moments the original calls "advance"
  onAdvance(fn) {
    this.advanceListeners.push(fn);
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
    this.ended = battle.result !== null && battle.result !== undefined;
    // S626/frame_38, the end of the run cycle, is the page's to decide between the bot's jumps
    this.lib.scripts.set(SOLDIER_SPRITE, (clip, frame) => this.runLoop(clip, frame));
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
  }

  // ---------- Each drawn step ----------

  // The bot's tick n, after the world's clips stepped: members arrive, the jumps of tick n play, bodies fade, the
  // depth sort and the squads' bars and stars follow
  tick(n, jumped = false) {
    if (!this.world || this.world !== this.field.world) {
      return;
    }
    this.quiet = jumped;
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
        if (isTankSquad(found.squad)) {
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
    const before = clip.frame;
    if (playing) {
      clip.gotoAndPlay(frame);
    } else {
      clip.gotoAndStop(frame);
    }
    this.settle(clip);
    this.catchUp(clip, n - stamp);
    if (playing && !this.quiet && startsAdvance(before, frame)) {
      this.advanceListeners.forEach((fn) => fn(unit));
    }
  }

  // The bot's tick runs a new clip's first frame for a whole tick, and steps every other clip once a tick: the steps
  // a jump missed play now, stopping early once the clip stops
  catchUp(clip, steps) {
    const count = Math.min(steps, MOST_CATCH_UP);
    for (let k = 0; k < count && (clip.playing || clip.fresh); k += 1) {
      clip.advance();
      this.settle(clip);
    }
  }

  // The guns play from the bot's stamps: the main gun's firing is its reload (sprite 650), the machine gun's a shot
  // (sprite 647, F5:2074-2113)
  followTank(unit, row, n) {
    unit.health = row[3] / 10;
    // Each gun keeps its own stamp, so each takes the newest one the drawing has reached from any update kept
    const stamps = { mainGun: unit.guns.mainGun, secondGun: unit.guns.secondGun };
    for (const snap of this.field.snaps) {
      const kept = indexOf(snap).get(unit.id)?.row;
      for (const [name, index] of [
        ["mainGun", 4],
        ["secondGun", 5],
      ]) {
        if (kept && kept[index] <= n && kept[index] > stamps[name]) {
          stamps[name] = kept[index];
        }
      }
    }
    for (const [name, stamp] of Object.entries(stamps)) {
      if (stamp <= unit.guns[name]) {
        continue;
      }
      unit.guns[name] = stamp;
      const gun = unit.clip.child(name);
      if (gun) {
        gun.gotoAndPlay("firing");
        this.catchUp(gun, n - stamp);
      }
    }
    if (unit.state === "tankMoving" && !unit.engine) {
      // The engine starts on the tank's first moving step and runs until it is destroyed (F5:2025-2029)
      unit.engine = `tank${unit.id}`;
      sound.loop("sound_tankMoving", unit.engine);
    }
  }

  // Dead bodies fade 15 seconds on and go; a member that left every update without dying is dropped
  age(unit, n) {
    if (unit.dead) {
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
    const tank = slot === TANK_SLOT;
    const row = found.row;
    const unit = {
      id,
      side,
      kind: tank ? "tank" : "soldier",
      type: tank ? "tankMarkIV" : SOLDIER_TYPES[row[7]],
      squadId,
      slot,
      clip: null,
      jump: null,
      seen: -1,
      dead: false,
      diedAt: 0,
      fading: false,
      depth: row[2] / 10,
      x: row[1] / 10,
      y: row[2] / 10,
      // Where a soldier first stood: the ground a thrown body comes down on (F5:1224)
      ground: row[2] / 10,
    };
    unit.clip = tank ? this.makeTank(unit, row, n) : this.makeSoldier(unit, row);
    // A new member's timeline holds its first frame for a whole tick, and its first jump into the run cycle (frames
    // 20 to 34, createSoldier F5:1244) comes on that tick. A member first seen on a later jump (a rejoin) is past that
    if (!tank && !(found.jump[1] && found.jump[0] >= SPAWN_FRAMES[0] && found.jump[0] <= SPAWN_FRAMES[1])) {
      unit.clip.fresh = false;
    }
    unit.clip.unit = unit;
    unit.clip.position.set(unit.x, unit.y);
    this.field.layer("soldiers").addChild(unit.clip);
    unit.clip.zIndex = id;
    this.members.set(id, unit);
    const squad = this.squadFor(squadId);
    squad.ids.add(id);
    if (side === this.you) {
      this.rollOvers(unit);
    }
    return unit;
  }

  squadFor(squadId) {
    let squad = this.squads.get(squadId);
    if (!squad) {
      squad = { ids: new Set(), near: false };
      this.squads.set(squadId, squad);
    }
    return squad;
  }

  // createSoldier (F5:1143-1250): sized 105 to 111 %, the German one turned around at its own width, its officer
  // star only on an officer (the German's own star), its weapon and uniform
  makeSoldier(unit, row) {
    const clip = this.lib.make(SOLDIER_SPRITE);
    const size = row[6] / 100;
    clip.scale.set(unit.side === "german" ? -1 : size, size);
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
    return clip;
  }

  // The tank at its side's frame, sized like a soldier, the German one turned around at its own width, with a
  // painted number. A tank already wrecked (a rejoin) shows its wreck at once
  makeTank(unit, row, n) {
    const clip = this.lib.make(this.lib.exported("tank"));
    clip.gotoAndStop(unit.side);
    // The bot draws the tank's size too, but doesn't send it: only the picture uses it
    const size = (random(7) + 105) / 100;
    clip.scale.set(unit.side === "german" ? -1 : size, size);
    const tag = clip.child("tag")?.child("tagNumber");
    if (tag) {
      tag.text = `C${random(TAG_SPREAD) + TAG_LOW}`;
    }
    this.settle(clip);
    const created = Math.min(row[4], row[5]);
    unit.guns = { mainGun: created, secondGun: created };
    unit.health = row[3] / 10;
    unit.engine = null;
    unit.wrecked = false;
    this.catchUp(clip, n - created);
    if (row[6]) {
      unit.wrecked = true;
      this.wreck(unit, true);
    }
    return clip;
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
        const key = `${clip.charId}:${node.charId}:${depth}`;
        (PLACEMENTS[`${key}@${clip.frame}`] ?? PLACEMENTS[key])?.(node);
      }
      if (node.slots) {
        this.settle(node);
      }
    }
  }

  // S626/frame_38: at the end of a run cycle a living soldier runs on, unless the battle is over. The bot jumps the
  // soldier here too, and that jump replaces this guess on the same tick. A soldier stopping to fire or getting into
  // a trench never reaches this frame on the page: the bot's jump to that animation comes on the same tick
  runLoop(clip, frame) {
    const unit = clip.unit;
    if (frame !== 38 || !unit) {
      return;
    }
    if (!unit.dead && !this.ended) {
      clip.gotoAndStop("rifle_run");
      clip.play();
    } else {
      clip.stop();
    }
  }

  // ---------- Deaths and wrecks ----------

  // A soldier died on this step: its death animation by its position, or half of blast deaths the exploded one; the
  // ring, bar and star fade, and the body drops below the living (F5:2848-2861, 3014-3062)
  died(event, quiet = false) {
    const [step, , id, how] = event;
    const unit = this.members.get(id);
    if (!unit || unit.dead || unit.kind !== "soldier") {
      return;
    }
    unit.dead = true;
    unit.diedAt = step;
    const clip = unit.clip;
    // A death whose moment has passed (a jump) is a body lying where it fell: nothing flies
    const exploded = how === HOW_BLAST && !quiet && random(2) > 0;
    // Blood and limbs come before the animation, as the original sets them (F5:2848-2857, 3030-3048)
    for (const fn of this.deathListeners) {
      fn(unit, how, exploded, quiet);
    }
    clip.gotoAndPlay(exploded ? "exploded_death" : `${positionAt(clip.frame)}_death`);
    this.settle(clip);
    for (const name of ["selectedRing", "healthBar", "officerStar"]) {
      const part = clip.child(name);
      if (part) {
        tweens.alphaTo(part, 0, DEATH_FADE);
      }
    }
    // sortDeadSoldiers (F5:5229-5232)
    this.field.layer("deadSoldiers").addChild(clip);
    clip.zIndex = unit.depth;
  }

  tankDied(event) {
    const unit = this.members.get(event[2]);
    if (unit?.kind === "tank" && !unit.wrecked) {
      unit.wrecked = true;
      this.wreck(unit, false);
    }
  }

  // The burning wreck (F5:2956-2995): the body at "destroyed", the damage clip fading in, two fires burning and the
  // other two 1 in 2 each, each fire going out after a while; the engine fades out over 2 seconds
  wreck(unit, now) {
    const clip = unit.clip;
    clip.child("tankBody")?.gotoAndStop("destroyed");
    const health = clip.child("healthBar");
    if (health) {
      tweens.alphaTo(health, 0, DEATH_FADE);
    }
    const damage = clip.child("damageClip");
    if (damage) {
      damage.visible = true;
      damage.alpha = 0;
      tweens.alphaTo(damage, 100, now ? 0 : WRECK_IN);
      this.burn(damage);
    }
    if (unit.engine) {
      sound.stopLoop(unit.engine, ENGINE_FADE);
      unit.engine = null;
    }
  }

  burn(damage) {
    for (let k = 1; k <= 4; k += 1) {
      const fire = damage.child(`fireAnim${k}`);
      if (!fire) {
        continue;
      }
      if (k > 2 && random(2) === 0) {
        fire.visible = false;
        continue;
      }
      fire.child("fireAnim")?.gotoAndPlay(random(FIRE_FRAMES) + 1);
      tweens.alphaTo(fire, 0, FIRE_OUT, "easeOutSine", FIRE_DELAY + random(FIRE_DELAY_SPREAD), () =>
        fire.removeMovieClip(),
      );
    }
  }

  // ---------- Squad looks ----------

  // Every squad on the field now: its leader's health bar and officer star (squadAI F5:1287-1310), and the silver
  // star while it is near an officer (findOfficers F5:2297-2321, flags bit 0)
  squadLooks() {
    const snap = this.field.snaps[0];
    if (!snap) {
      return;
    }
    for (const row of snap.s.q) {
      const leader = row[7].map((member) => this.members.get(member[0])).find((unit) => unit && !unit.dead);
      if (!leader) {
        continue;
      }
      const squad = this.squadFor(row[0]);
      squad.order = row[7].map((member) => member[0]);
      this.healthBar(leader, row, squad);
      if (leader.kind === "soldier") {
        this.officerStar(leader, row, squad);
      }
    }
  }

  healthBar(leader, row, squad) {
    const bar = leader.clip.child("healthBar")?.child("bar");
    if (!bar) {
      return;
    }
    const percent =
      leader.kind === "tank"
        ? Math.round((leader.health / TANK_HEALTH) * 100)
        : Math.round((row[7].length / Math.max(1, squad.ids.size)) * 100);
    bar.scale.x = percent / 100;
    // F5:1291 also writes the tank's health into healthBar.healthNumber, but the bar (sprite 457) has no such field,
    // so the original never showed a number
    const band = percent < BAR_RED ? RED : percent < BAR_AMBER ? AMBER : null;
    if (band !== null && squad.band !== band) {
      squad.band = band;
      tweens.colorTo(bar, band, BAR_COLOR_SECONDS);
    }
  }

  officerStar(leader, row, squad) {
    const star = leader.clip.child("officerStar");
    if (!star) {
      return;
    }
    const [x, y] = positionAt(leader.clip.frame) === "trench" ? STAR_TRENCH : STAR_OPEN;
    star.position.set(x, y);
    const near = (row[4] & 1) === 1;
    if (row[2] === OFFICER_SLOT || near === squad.near) {
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

  // sortSoldierDepths (F5:5174-5228): every living member, British squads then German, each walked newest first,
  // then the wire and the wrecks, ordered by y with ties kept in that order, onto the sorted layer
  sortDepths() {
    const snap = this.field.snaps[0];
    // The wire pieces in the order they were made, kept once they leave their own layer
    this.wire ??= [...this.field.layer("wire").children];
    const living = [];
    const wrecks = [];
    for (const sideIndex of [0, 1]) {
      const rows = snap.s.q.filter((row) => row[1] === sideIndex).reverse();
      for (const row of rows) {
        for (const member of [...row[7]].reverse()) {
          const unit = this.members.get(member[0]);
          if (unit && !unit.dead && !unit.wrecked) {
            living.push(unit.clip);
          }
        }
      }
    }
    for (const row of snap.s.q) {
      const unit = this.members.get(row[7][0]?.[0]);
      if (unit?.wrecked) {
        wrecks.push(unit.clip);
      }
    }
    const list = [...living, ...[...this.wire].reverse(), ...wrecks.reverse()].filter((node) => !node.destroyed);
    const sorted = list.map((node) => [node, node.y]);
    sorted.sort((a, b) => a[1] - b[1]);
    const layer = this.field.layer("soldiersSorted");
    sorted.forEach(([node], index) => {
      if (node.unit) {
        node.unit.depth = node.y;
      }
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

  // soldierRollOvers (F5:4155-4188): over one of your own soldiers or tanks, its squad's rings come up and its
  // leader's health bar shows. A finger resting on it does the same
  rollOvers(unit) {
    const clip = unit.clip;
    clip.useHandCursor = false;
    clip.setHandler("onRollOver", () => this.showSquad(unit.squadId, true));
    clip.setHandler("onRollOut", () => this.showSquad(unit.squadId, false));
    clip.setHandler("onPress", (e) => {
      if (e.pointerType === "touch") {
        this.showSquad(unit.squadId, true);
      }
    });
    const lift = (e) => {
      if (e.pointerType === "touch") {
        this.showSquad(unit.squadId, false);
      }
    };
    clip.setHandler("onRelease", lift);
    clip.setHandler("onReleaseOutside", lift);
  }

  showSquad(squadId, on) {
    const order = this.squads.get(squadId)?.order ?? [];
    order.forEach((id, index) => {
      const unit = this.members.get(id);
      if (!unit || unit.clip.destroyed) {
        return;
      }
      const parts = [unit.clip.child("selectedRing"), index === 0 ? unit.clip.child("healthBar") : null];
      parts.forEach((part, which) => {
        if (!part) {
          return;
        }
        if (on) {
          part.visible = true;
          tweens.alphaTo(part, which === 0 ? RING_ALPHA : 100, SHOW_SECONDS);
        } else {
          tweens.alphaTo(part, 0, HIDE_SECONDS, "linear", HIDE_DELAY);
        }
      });
    });
  }
}
