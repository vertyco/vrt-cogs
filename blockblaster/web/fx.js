// Motion and effects: how the simulation's events look on screen. The simulation only says what happened and in which
// tick (play.js stamps each event with its tick `t`); this module starts each look at that tick and never changes a
// rule. Pigs hop, slide, squash, recoil and vanish; shots fly as short white streaks; cubes shrink away and throw
// chips; the slots pulse red when the row is full. Nothing is created during play: streaks come from a fixed pool and
// every pig's look is a small record kept by id.
// The page's clock here is in ticks: `now` is the tick being drawn, with a fraction between ticks.
import * as THREE from "./vendor/three.module.min.js";
import { startHealth } from "./picture.js";
import { HOP, L_PER_UNIT, TICKS_PER_SECOND } from "./sim/numbers.js";
import { play as sound } from "./sound.js";

// A pig's hop between places: 0.25 s and 3.0 high, peaking at the half (the original's jump tween)
export const HOP_HEIGHT = 3.0;
// Features whose look rings their own hit sound, so the generic one is left out (the biscuit 16, the rocket 17)
const OWN_HIT_SOUND = new Set([16, 17]);
// A pig sliding to its new spot in a queue or the slot row takes about 0.3 s
const SLIDE_TICKS = 18;
// The Shuffle booster's animation: 0.4 s in real time (the game's clock is held meanwhile), each moved pig arcing this
// high to its new spot
export const SHUFFLE_MS = 400;
// The Demolish bomb: it falls for BOMB_DROP_MS before its tap lands, and the flash over the cross lasts BOMB_FLASH_MS
// (both in real time, the game's clock is held)
export { BOMB_DROP_MS, BOMB_FLASH_MS } from "./picture.js";
// The Super Shooter: its pig shows from the pick and its tap lands SUPER_LEAD_MS later (the clock is held all that time)
export { SUPER_LEAD_MS } from "./picture.js";
// The Super Unicorn: it shows from the press and its tap lands UNICORN_LEAD_MS later (the clock is held all that time)
export { UNICORN_LEAD_MS } from "./picture.js";
const SHUFFLE_ARC = 2.2;
// The vanish: 0.35 s, one spin, rising 7
const VANISH_TICKS = 21;
const VANISH_RISE = 7;
// Landing squash: 0.08 s down, 0.06 s back up
const SQUASH_DOWN = 5;
const SQUASH_UP = 4;
const SQUASH_DEPTH = 0.22;
const SQUASH_WIDEN = 0.1;
// A pig's recoil after a shot lasts 0.07 s and pushes it back this far (units at pig scale 1)
const RECOIL_TICKS = 4;
const RECOIL_DISTANCE = 0.1;
// A pig that just fired shows its happy face for this long
const HAPPY_TICKS = 15;
// The small bob of a pig riding the belt
const BOB_HEIGHT = 0.04;
const BOB_SPEED = 0.35;
// The slots pulse red twice for 0.3 s each
const PULSE_TICKS = 18;
const PULSE_COUNT = 2;

const FACE_HAPPY = 2;

// Shot streaks: a short white bar from the muzzle to the cell, as long as this and as thick as this
const STREAK_POOL = 768;
const STREAK_LENGTH = 0.8;
const STREAK_WIDTH = 0.07;
// A shot ends this high above the ground, on the cube's side
const STREAK_TARGET_HEIGHT = 0.15;
const STREAK_COLOR = 0xffffff;

const UNIT_Z = new THREE.Vector3(0, 0, 1);
// The one effects group `onEvents` and `frame` work with: the scene's
const active = { fx: null };

// Start the looks for the simulation's events of the last frame. `events` carry their tick in `t`
export function onEvents(events, state) {
  if (active.fx) {
    active.fx.onEvents(events, state);
  }
}

// Move everything to the tick being drawn. `alpha` (0 to 1) is how far the clock is toward the next tick
export function frame(alpha, state) {
  if (active.fx) {
    active.fx.frame(alpha, state);
  }
}

// True while the Shuffle animation, the Demolish bomb or the Super Shooter is playing, so a held clock still gets its
// frames drawn
export function animating() {
  return Boolean(active.fx) && (active.fx.shuffling() || active.fx.picture.bombing() || active.fx.picture.supering());
}

function smooth(u) {
  return u * u * (3 - 2 * u);
}

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The way round from one yaw to another that is under half a turn
function turnBetween(from, to) {
  let d = (to - from) % (2 * Math.PI);
  if (d > Math.PI) {
    d -= 2 * Math.PI;
  } else if (d < -Math.PI) {
    d += 2 * Math.PI;
  }
  return d;
}

function copyLook(into, from) {
  into.x = from.x;
  into.y = from.y;
  into.z = from.z;
  into.yaw = from.yaw;
  into.scale = from.scale;
  into.fade = from.fade;
  return into;
}

// A pose with its parts each `u` of the way from one look to another
function blendLook(out, from, to, u) {
  out.x = from.x + (to.x - from.x) * u;
  out.y = from.y + (to.y - from.y) * u;
  out.z = from.z + (to.z - from.z) * u;
  out.yaw = from.yaw + turnBetween(from.yaw, to.yaw) * u;
  out.scale = from.scale + (to.scale - from.scale) * u;
  out.fade = from.fade + (to.fade - from.fade) * u;
}

function makeLook() {
  return { x: 0, y: 0, z: 0, yaw: 0, scale: 1, fade: 1 };
}

class Effects {
  // `scene` is the THREE scene the streaks are added to; `picture` is picture.js's handle (cubes and chips)
  constructor(scene, picture) {
    this.picture = picture;
    this.now = 0;
    // Per pig id: what it is doing now (wait, hop, slide, vanish), where it was last drawn, where its place wanted it
    // last time, when it landed from a hop and when it last fired
    this.anims = new Map();
    this.drawn = new Map();
    this.wanted = new Map();
    this.landed = new Map();
    this.lastShot = new Map();
    this.pulseStart = -Infinity;
    // Cubes a Super Unicorn shot popped out of a Pixel Pipe: they break at once in the rules, and their shot's landing
    // throws the chips
    this.popped = new Set();
    // When the Shuffle animation ends, in performance.now() milliseconds
    this.shuffleEnd = 0;
    this.streaks = Array.from({ length: STREAK_POOL }, () => ({
      live: false,
      t: 0,
      length: 1,
      from: new THREE.Vector3(),
      to: new THREE.Vector3(),
      turn: new THREE.Quaternion(),
      tail: 0,
    }));
    this.nextStreak = 0;
    this.mesh = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshBasicMaterial({ color: STREAK_COLOR, toneMapped: false }),
      STREAK_POOL,
    );
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 4;
    this.mesh.count = 0;
    scene.add(this.mesh);
    this.matrix = new THREE.Matrix4();
    this.place = new THREE.Vector3();
    this.size = new THREE.Vector3();
    this.head = new THREE.Vector3();
    this.target = makeLook();
    // The feature looks (looks/index.js); the scene sets it
    this.looks = null;
  }

  // A new level: nothing is moving
  build(state) {
    this.anims.clear();
    this.drawn.clear();
    this.wanted.clear();
    this.landed.clear();
    this.lastShot.clear();
    this.pulseStart = -Infinity;
    this.shuffleEnd = 0;
    for (const streak of this.streaks) {
      streak.live = false;
    }
    this.mesh.count = 0;
    this.now = state.tick;
  }

  // The camera or the column changed: places moved without anything happening, so nothing should glide
  forget() {
    this.wanted.clear();
  }

  seconds(tick) {
    return tick / TICKS_PER_SECOND;
  }

  // A copy of where the pig was last drawn, or null before it was drawn at all
  snapshot(id) {
    const at = this.drawn.get(id);
    return at ? copyLook(makeLook(), at) : null;
  }

  onEvents(events, state) {
    // The Super Unicorn's run is planned from all its shots, which come in the same batch as its start
    if (events.some((event) => event.k === "unicorn_start")) {
      this.picture.startUnicorn(events.filter((event) => event.k === "unicorn_shot"));
    }
    for (const event of events) {
      const handler = EVENTS[event.k];
      if (handler) {
        handler(this, event, state);
      }
    }
    if (this.looks) {
      this.looks.onEvents(events, state);
    }
  }

  // The pig leaves its place now and hops to wherever its new place is
  startHop(id, t, from = this.snapshot(id)) {
    if (from) {
      this.anims.set(id, { kind: "hop", from, t0: t, t1: t + HOP });
    }
  }

  // The pigs of a Shuffle leave their drawn spots for their new ones: an arc in real time, because the clock is held
  startShuffle(ids) {
    const t0 = performance.now();
    for (const id of ids) {
      const from = this.snapshot(id);
      if (from) {
        this.anims.set(id, { kind: "shuffle", from, t0, t1: t0 + SHUFFLE_MS });
      }
    }
    this.shuffleEnd = t0 + SHUFFLE_MS;
  }

  shuffling() {
    return performance.now() < this.shuffleEnd;
  }

  // A shot leaves a pig for a cell. It lands in phase 5 of tick `land`, so the streak takes until then
  shoot(event) {
    const streak = this.streaks[this.nextStreak];
    this.nextStreak = (this.nextStreak + 1) % STREAK_POOL;
    const [fx, fy, fz] = event.from;
    const [tx, ty] = event.to;
    streak.from.set(fx / L_PER_UNIT, fz / L_PER_UNIT, -fy / L_PER_UNIT);
    streak.to.set(tx / L_PER_UNIT, STREAK_TARGET_HEIGHT, -ty / L_PER_UNIT);
    const distance = streak.from.distanceTo(streak.to);
    streak.turn.setFromUnitVectors(UNIT_Z, this.head.copy(streak.to).sub(streak.from).normalize());
    streak.t = event.t;
    streak.length = Math.max(1, event.land - event.t);
    streak.tail = distance > 0 ? Math.min(1, STREAK_LENGTH / distance) : 1;
    streak.live = true;
    this.lastShot.set(event.pig, event.t);
  }

  // Draw every streak in flight at this time
  drawStreaks() {
    let count = 0;
    for (const streak of this.streaks) {
      if (!streak.live) {
        continue;
      }
      const f = (this.now - streak.t) / streak.length;
      if (f >= 1) {
        streak.live = false;
        continue;
      }
      if (f < 0) {
        continue;
      }
      const tail = Math.max(0, f - streak.tail);
      this.head.copy(streak.from).lerp(streak.to, f);
      this.place.copy(streak.from).lerp(streak.to, tail);
      const length = this.head.distanceTo(this.place);
      this.place.add(this.head).multiplyScalar(0.5);
      this.matrix.compose(this.place, streak.turn, this.size.set(STREAK_WIDTH, STREAK_WIDTH, Math.max(length, 0.05)));
      this.mesh.setMatrixAt(count, this.matrix);
      count += 1;
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    this.drawStreaks();
    // The cubes the Super Shooter's shots have reached since the last frame break with their sound
    if (this.picture.takePopped() > 0) {
      sound("break");
    }
    if (this.looks) {
      this.looks.frame(alpha, state);
    }
  }

  // How red the slot row is right now, 0 to 1: it pulses PULSE_COUNT times
  slotAlarm() {
    const age = this.now - this.pulseStart;
    if (age < 0 || age >= PULSE_TICKS * PULSE_COUNT) {
      return 0;
    }
    return Math.sin(Math.PI * ((age % PULSE_TICKS) / PULSE_TICKS));
  }

  // Where a pig is in the middle of a hop, slide or vanish. `pose` holds where its place wants it and is changed to
  // where it is drawn. Returns false when the pig is not drawn
  move(id, pig, pose, anim) {
    const now = this.now;
    if (anim.kind === "vanish") {
      const u = clamp01((now - anim.t0) / (anim.t1 - anim.t0));
      if (u >= 1) {
        this.anims.delete(id);
        return false;
      }
      copyLook(pose, anim.from);
      pose.yaw += 2 * Math.PI * u;
      pose.scale *= 1 - u * u * u;
      pose.air = VANISH_RISE * u * u;
      pose.digits = false;
      pose.shown = true;
      return true;
    }
    if (!pose.shown) {
      this.anims.delete(id);
      return false;
    }
    const from = anim.from;
    if (anim.kind === "wait") {
      copyLook(pose, from);
      return true;
    }
    if (anim.kind === "shuffle") {
      return this.moveShuffle(id, pose, anim);
    }
    const u = clamp01((now - anim.t0) / (anim.t1 - anim.t0));
    copyLook(this.target, pose);
    blendLook(pose, from, this.target, anim.kind === "slide" ? smooth(u) : u);
    if (anim.kind === "hop") {
      pose.air = HOP_HEIGHT * 4 * u * (1 - u);
    }
    if (u >= 1) {
      this.anims.delete(id);
      if (anim.kind === "hop") {
        this.landed.set(id, anim.t1);
      }
    }
    return true;
  }

  // A pig of the Shuffle on its arc from where it stood to where it stands now
  moveShuffle(id, pose, anim) {
    const u = clamp01((performance.now() - anim.t0) / (anim.t1 - anim.t0));
    copyLook(this.target, pose);
    blendLook(pose, anim.from, this.target, smooth(u));
    pose.air = SHUFFLE_ARC * 4 * u * (1 - u);
    if (u >= 1) {
      this.anims.delete(id);
    }
    return true;
  }

  // A pig standing in a queue, slot or the rescue row whose spot changed slides to the new one
  watchSpot(id, pig, pose) {
    const old = this.wanted.get(id);
    const was = this.drawn.get(id);
    if (old && was && old.place === pig.place && (old.x !== pose.x || old.z !== pose.z || old.scale !== pose.scale)) {
      this.anims.set(id, { kind: "slide", from: copyLook(makeLook(), was), t0: this.now, t1: this.now + SLIDE_TICKS });
      return this.anims.get(id);
    }
    return null;
  }

  // The squash after a landing, as a height factor (1 is none)
  squash(id) {
    const landed = this.landed.get(id);
    if (landed === undefined) {
      return 0;
    }
    const age = this.now - landed;
    if (age < 0) {
      return 0;
    }
    if (age < SQUASH_DOWN) {
      return age / SQUASH_DOWN;
    }
    if (age < SQUASH_DOWN + SQUASH_UP) {
      return 1 - (age - SQUASH_DOWN) / SQUASH_UP;
    }
    this.landed.delete(id);
    return 0;
  }

  // Shape one pig's pose for the tick being drawn: `pose` comes in with where the pig's place puts it and goes out
  // with where it is drawn, plus `air` (height above its spot), `sx`, `sy` (squash), `face` and `digits`
  shape(id, pig, pose) {
    pose.air = 0;
    pose.face = -1;
    pose.digits = true;
    let anim = this.anims.get(id);
    if (!anim && pose.shown && pig.place !== "belt") {
      anim = this.watchSpot(id, pig, pose);
    }
    if (pose.shown) {
      this.wanted.set(id, { x: pose.x, z: pose.z, scale: pose.scale, place: pig.place });
    }
    if (anim && !this.move(id, pig, pose, anim)) {
      pose.shown = false;
    }
    if (!pose.shown) {
      return;
    }
    const baseX = pose.x;
    const baseZ = pose.z;
    this.drawn.set(id, copyLook(this.drawn.get(id) || makeLook(), pose));
    this.drawn.get(id).y += pose.air;
    if (pig.place === "belt" && !anim) {
      pose.air = BOB_HEIGHT * Math.abs(Math.sin(this.now * BOB_SPEED + id));
    }
    this.look(id, pig, pose, baseX, baseZ);
  }

  // The squash, the recoil and the face of a drawn pig
  look(id, pig, pose, baseX, baseZ) {
    const squash = this.squash(id);
    pose.sy = 1 - SQUASH_DEPTH * squash;
    pose.sx = 1 + SQUASH_WIDEN * squash;
    const fired = this.now - (this.lastShot.get(id) ?? -Infinity);
    if (fired >= 0 && fired < RECOIL_TICKS && pig.place === "belt") {
      const back = RECOIL_DISTANCE * pose.scale * (1 - fired / RECOIL_TICKS);
      pose.x = baseX - Math.sin(pose.yaw) * back;
      pose.z = baseZ - Math.cos(pose.yaw) * back;
    }
    if (pig.ammo > 0 && fired >= 0 && fired < HAPPY_TICKS) {
      pose.face = FACE_HAPPY;
    }
  }
}

// What each event of the simulation starts. Each takes (effects, event, state). The sounds start with the looks
const EVENTS = {
  // Pigs tapped out of their places wait where they stand until their hop
  pigs_placed(fx, event) {
    sound("tap");
    for (const id of event.ids) {
      const from = fx.snapshot(id);
      if (from) {
        fx.anims.set(id, { kind: "wait", from });
      }
    }
  },
  pig_hop(fx, event) {
    sound("hop");
    const waiting = fx.anims.get(event.pig);
    fx.startHop(event.pig, event.t, waiting ? waiting.from : undefined);
  },
  to_slot(fx, event) {
    sound("slot");
    fx.startHop(event.pig, event.t);
  },
  to_exit_line(fx, event) {
    sound("pop");
    fx.startHop(event.pig, event.t);
  },
  // A cat leaves a Pig Pipe tunnel: it hops from where the pipe stands to its place in the queue
  pipe_release(fx, event) {
    fx.startHop(event.pig, event.t, fx.snapshot(event.pipe));
  },
  to_rescue(fx, event) {
    sound("hop");
    fx.startHop(event.pig, event.t);
  },
  // A pig held inside a feature (a hammer on its way to the wood) has no spot of its own to vanish from; its feature's
  // look draws its end
  pig_vanishing(fx, event) {
    if (event.place === "held") {
      return;
    }
    sound("vanish");
    const from = fx.snapshot(event.pig);
    if (from) {
      fx.anims.set(event.pig, { kind: "vanish", from, t0: event.t, t1: event.t + VANISH_TICKS });
    }
  },
  shot(fx, event) {
    sound("shot");
    fx.shoot(event);
  },
  // The hit that breaks a cube sounds as its break. A cube that takes more hits rings, squashes and stands shorter.
  // Parts no shot can take (a wood block under a hammer) and features that ring their own hit (the biscuit) sound
  // through their own look
  hit(fx, event, state) {
    if (event.health <= 0) {
      return;
    }
    const target = state.grid.targets[event.target];
    if (target.owner !== 0) {
      if (target.hittable && !OWN_HIT_SOUND.has(target.owner)) {
        sound("hit");
      }
      return;
    }
    sound("metal");
    if (!target.dead) {
      fx.picture.hitCube(target, startHealth(state, target), event.health, event.cell, fx.seconds(event.t));
    }
  },
  cube_died(fx, event, state) {
    if (fx.popped.delete(event.cube)) {
      return;
    }
    // A cube the Super Shooter or the Super Unicorn killed breaks when its shot lands (the picture times it and the
    // sound with it)
    if (fx.picture.volleyKills(event.cube, event.color)) {
      return;
    }
    sound("break", { big: !event.single });
    fx.picture.breakCube(state.grid.targets[event.cube], event.color, fx.seconds(event.t));
  },
  won() {
    sound("clear");
  },
  tray_added() {
    sound("tray");
  },
  shuffled(fx, event) {
    sound("shuffle");
    fx.startShuffle(event.ids);
  },
  // The bomb has landed: the cross through its cell flashes
  bombed(fx, event) {
    sound("bomb");
    fx.picture.flashCross(event.x, event.y);
  },
  // The Super Shooter's tap landed: the pig shoots every cube of the color (the cubes it kills follow as cube_died)
  super_shot(fx, event) {
    sound("volley");
    fx.picture.startVolley(event.ids);
  },
  // The Super Unicorn's tap landed: it shoots every color of the merged pigs (the run was planned above)
  unicorn_start() {
    sound("volley");
  },
  pipe_pop(fx, event) {
    fx.popped.add(event.cube);
  },
  revive_done() {
    sound("revive");
  },
  slot_warning(fx, event) {
    if (fx.now - fx.pulseStart >= PULSE_TICKS * PULSE_COUNT) {
      fx.pulseStart = event.t;
    }
  },
};

// Make the effects group for a scene: `scene` is the THREE scene, `picture` the picture's handle
export function createFx(scene, picture) {
  active.fx = new Effects(scene, picture);
  return active.fx;
}
