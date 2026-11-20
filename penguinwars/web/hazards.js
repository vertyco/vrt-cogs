// What a map puts on the ice besides its shape: the wind and the walrus, and the snowballs that people watching throw.
// The bot says when each acts. This draws them, and tells the page's guess at the player's own penguin about the two
// that move it: a gust and the walrus's round body.
import { WARM_DEPTH } from "./fx.js";
import { buildSnowballs, buildWalrus, buildWind, setShown } from "./models.js";
import {
  SNOWBALL_REACH,
  SNOWBALL_SECONDS,
  SNOWBALLS,
  WALRUS_REACH,
  WALRUS_REAR_SECONDS,
  WIND_GUST_SECONDS,
  WIND_WARN_SECONDS,
} from "./motion.js";

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
// The wind's phases, as the bot numbers them
const CALM = 0;
const WARN = 1;
const BLOW = 2;
const WIND_SECONDS = { [WARN]: WIND_WARN_SECONDS, [BLOW]: WIND_GUST_SECONDS };
// The walrus's poses, as the bot numbers them
const REARED = 2;
// How high over the ice a flat mark lies, so the ice never shows through it
const LIFT = 0.02;
// The wind's arrow and streaks take this long to come and go. The arrow is this long and lies on the middle of the
// ice. It blinks this fast through the warning, and in a gust it sweeps this far downwind this many times a second
const WIND_FADE = 0.25;
const ARROW_LONG = 4.6;
const ARROW_BLINK = 12;
const ARROW_SWEEP = 3;
const ARROW_SWEEPS = 1.3;
// The streaks in the air: how many, how far from the middle of the ice they reach, how thick they are, and for each
// phase how long and fast they are and how much they show. Short and slow says a gust is coming, long and fast is one
const STREAKS = 14;
const STREAK_FIELD = 5.5;
const STREAK_THICK = 0.05;
const STREAK_LOOKS = {
  [WARN]: { long: 0.5, speed: 1.5, shown: 0.55 },
  [BLOW]: { long: 1.8, speed: 10, shown: 0.9 },
};
// The walrus rears up to this angle at this rate and comes down faster. It turns its head this far as it sits
const REAR_PITCH = 34;
const REAR_RISE = 9;
const REAR_DROP = 32;
const REAR_SHAKE = REDUCED ? 0 : 1.5;
const WALRUS_SWAY = 6;
const SQUASH_FADE = 8;
// Leaving, it hops this high and goes down through its cracked tile: the seconds its hop is timed by, the heights at
// which it splashes and is out of sight, and how far its nose tips down
const DIVE_SECONDS = 0.9;
const DIVE_HOP = 0.35;
const DIVE_WET = -0.15;
const DIVE_SUNK = -1.3;
const DIVE_PITCH = -70;
// A snowball is this big, and its dark rim this many times that. It flies this much higher than a straight line, and
// starts this many pixels under the screen, this share of the way from the camera to the ice. Its mark starts this
// many times its size at rest. A ball whose landing the bot never tells of is dropped this long after it was due
const BALL_SIZE = 0.36;
const BALL_RIM = 1.25;
const THROW_ARC = 1.4;
const THROW_BELOW = 40;
const THROW_NEAR = 0.45;
const MARK_WIDE = 1.8;
const LATE_WORD = 0.5;
const SAME_SPOT = 0.006;

const rand = (low, high) => low + Math.random() * (high - low);
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const lerp = (from, to, k) => from + (to - from) * k;
const smooth = (k) => k * k * (3 - 2 * k);
const degrees = (radians) => (radians * 180) / Math.PI;

class Hazards {
  // `iceY` is how high the top of the ice is
  constructor(scene, iceY) {
    this.scene = scene;
    this.fx = scene.fx;
    this.iceY = iceY;
    // What the player's own penguin is told of: see Ghost.step in motion.js
    this.around = scene.prediction.around;
    this.place = new pc.Mat4();
    this.spot = new pc.Vec3();
    this.size = new pc.Vec3();
    this.turn = new pc.Quat();
    // The wind: its phase, the seconds into it, which way it blows, how much of it shows and the phase it shows as
    this.wind = {
      ...buildWind(scene.app, STREAKS),
      phase: CALM,
      t: 0,
      ux: 1,
      uz: 0,
      shown: 0,
      last: WARN,
      // Each streak's place along and across the wind, its height, and its own length and speed against the others'
      streaks: Array.from({ length: STREAKS }, () => ({
        along: rand(-STREAK_FIELD, STREAK_FIELD),
        across: rand(-STREAK_FIELD, STREAK_FIELD),
        y: rand(0.35, 1.3),
        pace: rand(0.7, 1.3),
      })),
    };
    // The walrus: "off", or as it will "sit", "rear" up or "dive" away, the seconds in that state and where it is
    this.walrus = { ...buildWalrus(scene.app), state: "off", t: 0, x: 0, z: 0, pitch: 0, squash: 0, wet: false };
    // The snowballs in the air: where each lands, where it came from and the seconds it has flown
    const ball = () => ({ on: false, drawn: false, x: 0, z: 0, t: 0, from: new pc.Vec3() });
    this.snow = { ...buildSnowballs(scene.app, SNOWBALLS), flying: Array.from({ length: SNOWBALLS }, ball) };
    this.snowCopies = [this.snow.balls, this.snow.rims, this.snow.marks];
    this.warmUp();
  }

  // One of everything here, and a thin tile's cap, shows under the sea until a frame has been drawn, so the graphics
  // card builds what draws them before a round needs it. Copies go under by their slot alone: the engine moves every
  // copy by where its root is as well, so a root moved down here would keep all its copies under the sea for good
  warmUp() {
    const { wind, walrus, scene } = this;
    const copies = [wind.lines, scene.floe.thin, ...this.snowCopies];
    const singles = [wind.arrow, walrus.root, walrus.zone];
    const shown = [...singles, ...copies.map((each) => each.root)];
    this.size.set(0.1, 0.1, 0.1);
    this.place.setTRS(this.spot.set(0, WARM_DEPTH, 0), pc.Quat.IDENTITY, this.size);
    for (const each of copies) {
      each.place(0, this.place);
      each.flush();
    }
    for (const entity of singles) {
      entity.setPosition(0, WARM_DEPTH, 0);
    }
    for (const entity of shown) {
      entity.enabled = true;
    }
    this.warming = true;
    scene.app.once("postrender", () => {
      for (const each of copies) {
        each.empty(0);
        each.flush();
      }
      for (const entity of shown) {
        entity.enabled = false;
      }
      this.warming = false;
    });
  }

  // A round with no hazard on it and nothing in the air
  clear() {
    this.calm();
    this.wind.shown = 0;
    this.hideWalrus();
    for (const ball of this.snow.flying) {
      ball.on = false;
    }
  }

  // What a snapshot says of the hazard and the snowballs. What the events already did matches it and stays as it is,
  // and what differs is what this page missed. `map` is the board's map and `snow` its snowballs in the air
  sync(map, snow) {
    this.syncWind(map?.wind);
    this.syncWalrus(map?.walrus);
    for (const [x, z, left] of snow ?? []) {
      if (!this.ballAt(x / 100, z / 100)) {
        this.throwBall(x / 100, z / 100, left / 100);
      }
    }
  }

  // ---------- Wind ----------

  // The wind as [the way it blows in degrees, its phase, hundredths of a second left in it], or nothing in a calm
  syncWind(row) {
    const { wind } = this;
    if (!row) {
      if (wind.phase !== CALM) {
        this.calm();
      }
    } else if (wind.phase !== row[1]) {
      this.startWind(row[1], row[0]);
      wind.t = Math.max(0, WIND_SECONDS[row[1]] - row[2] / 100);
    }
  }

  // The warning: the wind will blow toward `deg`, as (cos, sin) in (x, z)
  warn(deg) {
    this.startWind(WARN, deg);
  }

  blow(deg) {
    this.startWind(BLOW, deg);
  }

  startWind(phase, deg) {
    const angle = (deg * Math.PI) / 180;
    Object.assign(this.wind, { phase, last: phase, t: 0, ux: Math.cos(angle), uz: Math.sin(angle) });
    this.around.gust = phase === BLOW ? { ux: this.wind.ux, uz: this.wind.uz } : null;
  }

  calm() {
    this.wind.phase = CALM;
    this.around.gust = null;
  }

  drawWind(dt) {
    const { wind } = this;
    wind.shown = clamp(wind.shown + (wind.phase === CALM ? -dt : dt) / WIND_FADE, 0, 1);
    const showing = wind.shown > 0;
    wind.arrow.enabled = showing;
    wind.lines.root.enabled = showing && !REDUCED;
    if (!showing) {
      return;
    }
    wind.t += dt;
    this.turn.setFromEulerAngles(0, degrees(Math.atan2(wind.ux, wind.uz)), 0);
    this.drawArrow(wind);
    if (!REDUCED) {
      this.drawStreaks(wind, dt);
    }
  }

  // The arrow blinks where it lies through the warning, then sweeps downwind over and over while the gust blows.
  // People who asked for less motion get one that lies still, and no streaks
  drawArrow(wind) {
    let along = 0;
    let shown = wind.shown;
    let long = ARROW_LONG;
    if (REDUCED) {
      shown *= 0.85;
    } else if (wind.last === WARN) {
      const beat = 0.5 + 0.5 * Math.sin(wind.t * ARROW_BLINK);
      shown *= 0.5 + 0.5 * beat;
      long *= 1 + 0.05 * beat;
    } else {
      const sweep = (wind.t * ARROW_SWEEPS) % 1;
      along = (sweep - 0.5) * ARROW_SWEEP;
      shown *= Math.sin(Math.PI * sweep);
    }
    wind.arrow.setPosition(wind.ux * along, this.iceY + LIFT, wind.uz * along);
    wind.arrow.setRotation(this.turn);
    wind.arrow.setLocalScale(long, 1, long);
    setShown(wind.arrow, shown);
  }

  // Each streak flies downwind and comes back in upwind, at a new place across the wind
  drawStreaks(wind, dt) {
    const look = STREAK_LOOKS[wind.last];
    wind.streaks.forEach((streak, slot) => {
      streak.along += look.speed * streak.pace * dt;
      if (streak.along > STREAK_FIELD) {
        streak.along -= STREAK_FIELD * 2;
        streak.across = rand(-STREAK_FIELD, STREAK_FIELD);
      }
      const x = wind.ux * streak.along - wind.uz * streak.across;
      const z = wind.uz * streak.along + wind.ux * streak.across;
      this.spot.set(x, streak.y, z);
      this.size.set(STREAK_THICK, STREAK_THICK * 0.4, look.long * streak.pace);
      wind.lines.place(slot, this.place.setTRS(this.spot, this.turn, this.size));
    });
    wind.lines.flush();
    setShown(wind.lines.root, wind.shown * look.shown);
  }

  // ---------- Walrus ----------

  // The walrus as [its tile, its pose, hundredths of a second left in the pose], or nothing with none on the ice
  syncWalrus(row) {
    const { walrus } = this;
    const here = walrus.state === "sit" || walrus.state === "rear";
    if (!row) {
      if (here) {
        this.hideWalrus();
      }
      return;
    }
    if (!here) {
      this.seatWalrus(this.scene.tiles[row[0]]);
    }
    const reared = row[1] === REARED;
    if (reared && walrus.state !== "rear") {
      this.rear();
      walrus.t = Math.max(0, WALRUS_REAR_SECONDS - row[2] / 100);
    } else if (!reared) {
      walrus.state = "sit";
    }
  }

  seatWalrus(tile) {
    Object.assign(this.walrus, { state: "sit", t: 0, x: tile.x, z: tile.z, pitch: 0, squash: 0 });
    this.walrus.root.enabled = true;
    this.around.walrus = { x: tile.x, z: tile.z };
  }

  // It rears up, which warns of the slam
  rear() {
    if (this.walrus.state === "sit") {
      Object.assign(this.walrus, { state: "rear", t: 0 });
    }
  }

  // It sits back down with no slam, as the bot has it do when the round is decided while it is up
  sit() {
    if (this.walrus.state === "rear") {
      Object.assign(this.walrus, { state: "sit", t: 0 });
    }
  }

  // It comes down. Gives whether a walrus was there to slam
  slam() {
    const { walrus } = this;
    const here = walrus.state === "sit" || walrus.state === "rear";
    if (here) {
      Object.assign(walrus, { state: "sit", t: 0, squash: 1 });
    }
    return here;
  }

  // Its tile cracked. `seen` says the drawing reached that, so it is shown diving away
  walrusLeaves(seen) {
    const { walrus } = this;
    if (!seen || walrus.state === "off") {
      this.hideWalrus();
      return;
    }
    Object.assign(walrus, { state: "dive", t: 0, wet: false });
    walrus.zone.enabled = false;
    this.around.walrus = null;
  }

  hideWalrus() {
    const { walrus } = this;
    walrus.state = "off";
    walrus.root.enabled = false;
    walrus.zone.enabled = false;
    this.around.walrus = null;
  }

  drawWalrus(dt) {
    const { walrus } = this;
    if (walrus.state === "off") {
      return;
    }
    walrus.t += dt;
    walrus.squash *= Math.exp(-SQUASH_FADE * dt);
    const rearing = walrus.state === "rear";
    const diving = walrus.state === "dive";
    const want = rearing ? REAR_PITCH : diving ? DIVE_PITCH : 0;
    walrus.pitch += (want - walrus.pitch) * Math.min(1, dt * (want > walrus.pitch ? REAR_RISE : REAR_DROP));
    const y = diving ? this.diveWalrus(walrus) : 0;
    if (walrus.state === "off") {
      return;
    }
    const time = this.scene.time;
    const still = rearing || diving;
    const shake = rearing ? Math.sin(walrus.t * 38) * REAR_SHAKE : 0;
    const small = diving ? 1 - 0.5 * clamp(walrus.t / DIVE_SECONDS, 0, 1) : 1;
    const wide = small * (1 + walrus.squash * 0.22);
    walrus.root.setPosition(walrus.x, this.iceY + y, walrus.z);
    walrus.root.setEulerAngles(0, still ? 0 : Math.sin(time * 1.1) * WALRUS_SWAY, 0);
    walrus.pivot.setLocalEulerAngles(-walrus.pitch + shake, 0, 0);
    walrus.body.setLocalScale(wide, small * (1 - walrus.squash * 0.3 + Math.sin(time * 2.2) * 0.015), wide);
    this.drawZone(walrus, rearing);
  }

  // How high the leaving walrus is now. It splashes as it meets the water, and is gone once out of sight
  diveWalrus(walrus) {
    const k = walrus.t / DIVE_SECONDS;
    const y = DIVE_HOP * (1 - ((k - 0.2) / 0.2) ** 2);
    if (!walrus.wet && y < DIVE_WET) {
      walrus.wet = true;
      this.fx.walrusDives(walrus.x, walrus.z);
    }
    if (y < DIVE_SUNK) {
      this.hideWalrus();
    }
    return y;
  }

  // The ring a slam will fill shows for as long as the walrus is reared up, blinking faster as the slam nears
  drawZone(walrus, rearing) {
    walrus.zone.enabled = rearing;
    if (!rearing) {
      return;
    }
    const k = clamp(walrus.t / WALRUS_REAR_SECONDS, 0, 1);
    const size = WALRUS_REACH * (0.6 + 0.4 * smooth(clamp(k * 5, 0, 1)));
    walrus.zone.setPosition(walrus.x, this.iceY + LIFT, walrus.z);
    walrus.zone.setLocalScale(size, 1, size);
    setShown(walrus.zone, 0.65 + 0.35 * Math.sin(walrus.t * (10 + 16 * k)));
  }

  // ---------- Snowballs ----------

  // The snowball in the air that lands on this spot, the one longest in the air of several, or undefined
  ballAt(x, z) {
    let found;
    for (const ball of this.snow.flying) {
      const here = ball.on && Math.abs(ball.x - x) < SAME_SPOT && Math.abs(ball.z - z) < SAME_SPOT;
      if (here && (!found || ball.t > found.t)) {
        found = ball;
      }
    }
    return found;
  }

  // A snowball leaves for a spot on the ice, with `left` seconds still to fly. It comes in from under the bottom of
  // the screen, on the target's side of it, so it reads as thrown by someone watching
  throwBall(x, z, left = SNOWBALL_SECONDS) {
    const { flying } = this.snow;
    const { camera, canvas, camDist } = this.scene;
    const ball = flying.find((one) => !one.on) ?? flying[0];
    const target = camera.camera.worldToScreen(this.spot.set(x, this.iceY, z), this.size);
    const across = canvas.clientWidth / 2 + (target.x - canvas.clientWidth / 2) * 0.6;
    camera.camera.screenToWorld(across, canvas.clientHeight + THROW_BELOW, camDist * THROW_NEAR, ball.from);
    Object.assign(ball, { on: true, x, z, t: clamp(SNOWBALL_SECONDS - left, 0, SNOWBALL_SECONDS) });
  }

  // The bot's word that a snowball landed takes it out of the air
  landBall(x, z) {
    const ball = this.ballAt(x, z);
    if (ball) {
      ball.on = false;
    }
  }

  drawSnow(dt) {
    const { flying } = this.snow;
    let live = 0;
    flying.forEach((ball, slot) => {
      ball.t += dt;
      ball.on = ball.on && ball.t < SNOWBALL_SECONDS + LATE_WORD;
      if (ball.on) {
        live += 1;
        this.placeBall(ball, slot);
      }
      for (const copies of this.snowCopies) {
        if (!ball.on && ball.drawn) {
          copies.empty(slot);
        }
      }
      ball.drawn = ball.on;
    });
    for (const copies of this.snowCopies) {
      copies.flush();
      copies.root.enabled = live > 0;
    }
  }

  // The ball on its arc, with its rim, and its mark closing in on the size of the snowball's shove
  placeBall(ball, slot) {
    const { balls, rims, marks } = this.snow;
    const k = Math.min(1, ball.t / SNOWBALL_SECONDS);
    const { from } = ball;
    const up = THROW_ARC * Math.sin(Math.PI * k);
    this.spot.set(lerp(from.x, ball.x, k), lerp(from.y, this.iceY + BALL_SIZE / 2, k) + up, lerp(from.z, ball.z, k));
    this.size.set(BALL_SIZE, BALL_SIZE, BALL_SIZE);
    balls.place(slot, this.place.setTRS(this.spot, pc.Quat.IDENTITY, this.size));
    this.size.mulScalar(BALL_RIM);
    rims.place(slot, this.place.setTRS(this.spot, pc.Quat.IDENTITY, this.size));
    const wide = SNOWBALL_REACH * lerp(MARK_WIDE, 1, k);
    this.spot.set(ball.x, this.iceY + LIFT, ball.z);
    this.size.set(wide, 1, wide);
    marks.place(slot, this.place.setTRS(this.spot, pc.Quat.IDENTITY, this.size));
  }

  // `dt` is the drawing's time, which stands still while a hit holds it. Nothing moves until the warm-up has been drawn
  update(dt) {
    if (this.warming) {
      return;
    }
    this.drawWind(dt);
    this.drawWalrus(dt);
    this.drawSnow(dt);
  }
}

export function createHazards(scene, iceY) {
  return new Hazards(scene, iceY);
}
