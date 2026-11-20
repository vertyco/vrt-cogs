// The ice's layout and the page's clock. Nothing here touches PlayCanvas or the page, so Node can check it against
// the bot.

// The same numbers as penguinwars/common/floe.py and round.py (tests/test_page.py checks they match)
export const TICK_RATE = 30;
export const CRACK_SECONDS = 1.3;
export const SINK_SECONDS = 1.0;
export const DIVE_SECONDS = 0.6;
export const LEAP_SECONDS = 0.42;
export const TILE_SIZE = 0.62;
export const RINGS = 4;
export const MIN_POWER = 0.08;
export const PLAYER_SEAL_COOLDOWN = 0.8;
export const TOUCH = 0.94;
export const HIT_REL = 2;
export const HIT_PUSH = 1.9;
export const HEAVY_MASS = 2.2;
export const BRACE_MASS = 50;
export const CRATE_FALL_SECONDS = 1.2;
export const SHIELD_SECONDS = 8;
export const FEAST_SLIDES = 3;
export const BOUNCE_REL = 1.5;
// How far apart a seal's aim tries the ice, how far out it looks, and how far past the ice it lands
const EDGE_STEP = 0.12;
const EDGE_LIMIT = 9;
const EDGE_PAST = 0.35;
// Wind: a warning, then a gust that moves every penguin `wind_push` in a straight line, and a braced one this share
export const WIND_WARN_SECONDS = 1.5;
export const WIND_GUST_SECONDS = 2;
export const WIND_BRACE_SHARE = 0.1;
// The walrus: how close a penguin's middle gets to its middle, how long it rears up before a slam, and how far from
// its middle a slam reaches
export const WALRUS_RADIUS = 0.55;
export const WALRUS_TOUCH = 1.02;
export const WALRUS_REAR_SECONDS = 1;
export const WALRUS_REACH = 1.6;
// A watcher's snowball: its time in the air, how far from its landing it shoves, and how far from the middle of the
// ice one can be aimed
export const SNOWBALL_SECONDS = 0.7;
export const SNOWBALL_REACH = 0.9;
export const SNOWBALL_RANGE = 6;
export const SNOWBALLS = 6;
const SQ3 = Math.sqrt(3);
// A tile this state or lower holds a penguin up
export const CRACK = 1;
// Penguin flags, as the bot sends them
export const ALIVE = 1;
export const BRACING = 2;
export const FISH = 4;
export const HEAVY = 8;
export const SHIELD = 16;
export const FROZEN = 32;

export const TICK = 1 / TICK_RATE;
// The page draws this far behind the newest frame, so small changes in when frames arrive never show
export const DRAW_DELAY = 2 * TICK;
// With nothing new for this long, the old frames are history: the page jumps instead of gliding through them
export const SNAP_GAP = 0.5;
// How fast the delay left by a late frame shrinks back, in seconds per frame
const DRIFT = 0.0005;
// A frame is timed at most this far after it arrived. A burst of frames gets squeezed closer together to fit, so it
// plays through quickly and a long backlog can't keep the page behind for good
const MAX_AHEAD = 4 * TICK;
// The drawing sits DRAW_DELAY plus up to MAX_LAG behind the newest frame, and a late frame sits later still. Twelve
// frames still lost some in a run of hits with 60 ms of jitter, and 14 lost none. It fills up when a stall of about
// 0.47 s is let go at once, or while nothing is being drawn
const MAX_FRAMES = 14;
// After a hit holds the drawing, it runs this much faster than the clock until it has caught up. The most it falls
// behind is MAX_LAG: a run of hits can't push the drawing past frames the buffer has kept
export const CATCH_UP = 0.5;
export const MAX_LAG = 0.15;
// A press that moves less than this is not an aim, and it is a tap if it lifts in time
export const TAP_PIXELS = 16;
export const TAP_MS = 300;
// How far the finger goes before the pull counts, and the pull for full power, as a share of the screen's short side
const PULL_FREE = 10;
const PULL_FULL = 0.32;
// How long the drawing takes to go from the ghost back to the bot's stream
export const BLEND_SECONDS = 0.12;
// The ghost hands back this long after a slide, or once stopped this close to the bot's place
const GHOST_SECONDS = 2.5;
const SETTLED_WITHIN = 0.15;
// A hit this close counts as hitting the player's penguin. A hit names only who was hit, not who did the hitting
const HIT_WITHIN = 1.2;
// A walrus slam or a snowball counts as shoving the player's penguin this far past its reach, as the ghost runs a
// little ahead of where the bot had the penguin
const SHOVE_SLACK = 0.3;
// How long the bot has to answer a slide, or a brace, a dive or a touch, before the page stops showing it
const SLIDE_ANSWER = 0.6;
const TAP_ANSWER = 0.3;
// How long after its own touch the page still skips the bot's word on the same hit: a slow connection's round trip
const ECHO_SECONDS = 1;
// What the page counts down, in seconds
const COUNTDOWNS = [
  "echoLeft",
  "bumpLeft",
  "wait",
  "sealWait",
  "blendLeft",
  "slideLeft",
  "braceLeft",
  "diveLeft",
  "touchLeft",
];

// Whether a frame's round is decided, with one penguin or none left on the ice. The bot takes no more moves then
export function decided(rows) {
  let left = 0;
  for (const row of rows) {
    left += row[2] & ALIVE;
  }
  return left <= 1;
}

// Every tile in the bot's order, which is the order the wire's tile numbers count in
export function tileList() {
  const tiles = [];
  for (let q = -RINGS; q <= RINGS; q += 1) {
    for (let r = -RINGS; r <= RINGS; r += 1) {
      const ring = Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r));
      if (ring <= RINGS) {
        tiles.push({ q, r, ring, x: TILE_SIZE * SQ3 * (q + r / 2), z: TILE_SIZE * 1.5 * r });
      }
    }
  }
  return tiles;
}

const TILE_NUMBERS = new Map(tileList().map((tile, index) => [`${tile.q},${tile.r}`, index]));

// The number of the tile under a point, or undefined past the grid. The same sums as Floe.tile_at
export function tileAt(x, z) {
  const q = ((SQ3 / 3) * x - z / 3) / TILE_SIZE;
  const r = ((2 / 3) * z) / TILE_SIZE;
  const s = -q - r;
  let [rq, rr] = [Math.round(q), Math.round(r)];
  const rs = Math.round(s);
  const [dq, dr, ds] = [Math.abs(rq - q), Math.abs(rr - r), Math.abs(rs - s)];
  if (dq > dr && dq > ds) {
    rq = -rr - rs;
  } else if (dr > ds) {
    rr = -rq - rs;
  }
  return TILE_NUMBERS.get(`${rq},${rr}`);
}

// The distances a seal's aim tries, counted up one step at a time the way the bot counts them
const EDGE_MARKS = [0];
while (EDGE_MARKS[EDGE_MARKS.length - 1] < EDGE_LIMIT) {
  EDGE_MARKS.push(EDGE_MARKS[EDGE_MARKS.length - 1] + EDGE_STEP);
}

// Where a seal coming in at `angle` lands, from every tile's state: just past the outermost ice that way, found from
// the outside in, so a hole in the middle never hides the far side. `reach` is how far the ice reaches, 0 for none.
// The same sums as Floe.edge_point
export function edgePoint(angle, states) {
  const [ux, uz] = [Math.cos(angle), Math.sin(angle)];
  let last = EDGE_MARKS.length - 2;
  while (last >= 0 && !(states[tileAt(ux * EDGE_MARKS[last], uz * EDGE_MARKS[last])] <= CRACK)) {
    last -= 1;
  }
  const reach = EDGE_MARKS[last + 1];
  return { x: ux * (reach + EDGE_PAST), z: uz * (reach + EDGE_PAST), reach };
}

// The speed the bot gives a slide of this power, as Round.slide works it out
export function slideSpeed(power, fish, rules) {
  const speed = Math.min(1, Math.max(MIN_POWER, power)) * rules.slide_speed;
  return fish ? speed * rules.fish_boost : speed;
}

// The slide a pull of (px, py) screen pixels aims: the way opposite the pull, stronger the further it goes. Null for a
// pull too short to be an aim
export function aimFrom(px, py, width, height) {
  const length = Math.hypot(px, py);
  if (length < TAP_PIXELS) {
    return null;
  }
  const power = (length - PULL_FREE) / (Math.min(width, height) * PULL_FULL);
  return { dx: -px / length, dz: -py / length, power: Math.min(1, Math.max(MIN_POWER, power)) };
}

// One step of a body sliding on the ice, as Round.physics moves a penguin
export function stepBody(body, dt, rules) {
  // Not Math.hypot, which allocates on every call, and this runs many times a frame
  const speed = Math.sqrt(body.vx * body.vx + body.vz * body.vz);
  if (speed > 0) {
    const left = Math.max(0, speed - (rules.friction_share * speed + rules.friction_fixed) * dt);
    body.vx *= left / speed;
    body.vz *= left / speed;
  }
  body.x += body.vx * dt;
  body.z += body.vz * dt;
}

// What stopDistance walks, kept here as the arrow asks for it on every frame of an aim
const WALKER = { x: 0, z: 0, vx: 0, vz: 0 };

// How far a lone slide at this speed really goes, in the same steps the ghost takes. The arrow shows this, as the smooth
// sum of stop_distance in round.py runs a little long
export function stopDistance(speed, rules) {
  WALKER.x = 0;
  WALKER.vx = speed;
  while (WALKER.vx > 0) {
    stepBody(WALKER, TICK, rules);
  }
  return WALKER.x;
}

// What stands as firm as a brace against a hit: a brace, and a shield bubble, which takes the hit and bursts
const FIRM = BRACING | SHIELD;

// How heavy a penguin is to whatever runs into it, from its flags. The same as Penguin.mass and Round.collide
const massOf = (flags) => (flags & FIRM ? BRACE_MASS : flags & HEAVY ? HEAVY_MASS : 1);

// Ice with no hazard on it: no gust blowing and no walrus
const CALM_ICE = Object.freeze({ gust: null, walrus: null });

// The player's own penguin, moved by the page the moment a slide is made, without waiting for the bot. It moves in the
// bot's own steps, so it stops on the bot's spot at any frame rate. Between steps it carries on at the speed it has
export class Ghost {
  constructor() {
    this.start(0, 0, 0, 0, 0);
    this.active = false;
  }

  start(x, z, dx, dz, speed, mass = 1) {
    this.active = true;
    this.age = 0;
    this.spare = 0;
    this.mass = mass;
    // How fast it was closing on the walrus in its hardest bounce off it that nobody has shown yet, or 0
    this.bumped = 0;
    this.body = { x, z, vx: dx * speed, vz: dz * speed };
    Object.assign(this, this.body);
  }

  // `around` is what else moves a penguin on this ice: `gust`, the way a gust is blowing as { ux, uz }, and `walrus`,
  // where one sits as { x, z }, each null for none
  step(dt, rules, around = CALM_ICE) {
    this.age += dt;
    this.spare += dt;
    while (this.spare >= TICK) {
      this.blow(around.gust, rules);
      stepBody(this.body, TICK, rules);
      this.bump(around.walrus);
      this.spare -= TICK;
    }
    this.x = this.body.x + this.body.vx * this.spare;
    this.z = this.body.z + this.body.vz * this.spare;
    this.vx = this.body.vx;
    this.vz = this.body.vz;
  }

  // One update of a gust, as Round.blow moves a penguin: the same small step every update, whatever its speed
  blow(gust, rules) {
    if (gust) {
      const step = rules.wind_push / (WIND_GUST_SECONDS * TICK_RATE);
      this.body.x += gust.ux * step;
      this.body.z += gust.uz * step;
    }
  }

  // Round.bump for the ghost: kept out of the walrus, and thrown back off it the way a brace would
  bump(walrus) {
    if (!walrus) {
      return;
    }
    const { body } = this;
    const dx = body.x - walrus.x;
    const dz = body.z - walrus.z;
    const d = Math.sqrt(dx * dx + dz * dz);
    if (d >= WALRUS_TOUCH || d < 1e-4) {
      return;
    }
    const nx = dx / d;
    const nz = dz / d;
    body.x = walrus.x + nx * WALRUS_TOUCH;
    body.z = walrus.z + nz * WALRUS_TOUCH;
    const closing = -(body.vx * nx + body.vz * nz);
    if (closing <= 0) {
      return;
    }
    body.vx += HIT_PUSH * closing * nx;
    body.vz += HIT_PUSH * closing * nz;
    if (closing > this.bumped) {
      this.bumped = closing;
      this.contactX = (body.x + walrus.x) / 2;
      this.contactZ = (body.z + walrus.z) / 2;
    }
  }

  get stopped() {
    return this.vx === 0 && this.vz === 0;
  }

  settled(botX, botZ) {
    return this.stopped && Math.hypot(this.x - botX, this.z - botZ) <= SETTLED_WITHIN;
  }

  // The moving penguin's half of Round.collide, with the target standing still. Gives whether it counted as a hit. The
  // same share of the mass moves it back and takes its speed, so a plain hit mostly stops it, a heavy one rolls on and
  // a brace throws it back
  hit(x, z, mass) {
    const ax = x - this.x;
    const az = z - this.z;
    const d = Math.sqrt(ax * ax + az * az);
    if (d >= TOUCH) {
      return false;
    }
    const nx = ax / d;
    const nz = az / d;
    const closing = this.vx * nx + this.vz * nz;
    // Asked this way round, as a penguin exactly on top gives no direction and so no number to compare
    if (!(closing > HIT_REL)) {
      return false;
    }
    this.contactX = (this.x + x) / 2;
    this.contactZ = (this.z + z) / 2;
    this.closing = closing;
    const share = mass / (mass + this.mass);
    const back = (TOUCH - d) * share;
    const push = HIT_PUSH * closing * share;
    const { body } = this;
    body.x = this.x - nx * back;
    body.z = this.z - nz * back;
    body.vx = this.vx - nx * push;
    body.vz = this.vz - nz * push;
    this.spare = 0;
    return true;
  }
}

// Whether `left` seconds run out during this step
function runsOut(left, dt) {
  return left > 0 && left <= dt;
}

// What the page shows of the player's own moves before the bot has answered them
export class Prediction {
  constructor() {
    this.ghost = new Ghost();
    // The round's hazard as the ghost needs it, which the scene keeps up to date: see Ghost.step
    this.around = { gust: null, walrus: null };
    this.drop();
  }

  // Forgets every guess, so the drawing goes straight to where the bot's stream is
  drop() {
    this.ghost.active = false;
    // The bot's stream as last drawn, and where the blend back to it started
    this.bot = null;
    this.from = null;
    this.blendLeft = 0;
    // The page's own countdowns to the next move and the seal's next dive
    this.wait = 0;
    this.sealWait = 0;
    // Seconds each move has left to hear from the bot. The brace's bubble shows for as long as this runs
    this.slideLeft = 0;
    this.braceLeft = 0;
    this.diveLeft = 0;
    this.touchLeft = 0;
    this.braceHeard = false;
    this.seal = null;
    // Seconds the bot's word on the touch the ghost just reported may still take to come, and what the touch was. The
    // same for its word on the ghost's bounce off the walrus
    this.echoLeft = 0;
    this.bumpLeft = 0;
    this.touch = { x: 0, z: 0, strength: 0, bracing: false, seat: 0 };
    // The power slides a feast still gives after the one its fish is held for, by the page's own count, and whether
    // the slide on show left a fish in the beak that way
    this.feast = 0;
    this.fishKept = false;
  }

  get bracing() {
    return this.braceLeft > 0;
  }

  // Whether the slide on show has used up the penguin's fish, before the bot's word on it. Once the bot has answered,
  // its own flag says whether a fish is left. A feast leaves one after every slide but its last
  get fishSpent() {
    return this.slideLeft > 0 && this.ghost.active && this.ghost.mass === HEAVY_MASS && !this.fishKept;
  }

  // Seconds until the next move, given the bot's own count: the page's right after a move, the bot's after that
  waitOn(botWait) {
    return this.wait > 0 ? this.wait : botWait;
  }

  // `heavy` says the slide used up a fish, which makes the penguin heavy on the bot
  slide(x, z, dx, dz, speed, rules, heavy = false) {
    this.ghost.start(x, z, dx, dz, speed, heavy ? HEAVY_MASS : 1);
    this.fishKept = heavy && this.feast > 0;
    this.feast -= this.fishKept ? 1 : 0;
    this.blendLeft = 0;
    this.touchLeft = 0;
    this.wait = rules.slide_wait;
    this.slideLeft = SLIDE_ANSWER;
  }

  // The bot damps a bracing penguin to a stop, which the ghost doesn't do
  brace(rules) {
    this.handBack();
    this.wait = rules.brace_wait;
    this.braceLeft = TAP_ANSWER;
    this.braceHeard = false;
  }

  // The bot counts the seal's wait from its splash, at the end of the dive and leap
  startSealWait(rules) {
    this.sealWait = DIVE_SECONDS + LEAP_SECONDS + rules.seal_wait;
  }

  dive(seal, rules) {
    this.seal = seal;
    this.startSealWait(rules);
    this.diveLeft = TAP_ANSWER;
  }

  // With no answer the seal comes back up and swims on from where it is
  callOffDive() {
    const { seal } = this;
    this.sealWait = 0;
    if (seal.state === "dive") {
      Object.assign(seal, { state: "swim", ang: Math.atan2(seal.z, seal.x) });
    }
  }

  handBack() {
    if (this.ghost.active) {
      this.ghost.active = false;
      this.from = { x: this.ghost.x, z: this.ghost.z };
      this.blendLeft = BLEND_SECONDS;
    }
  }

  // A frost makes the bot refuse the slide or brace it hasn't answered yet: every move it took before the frost was
  // heard before it. So that move stops showing now, and the wait is the bot's own, which the frost has made longer
  frozen() {
    if (this.slideLeft > 0 || (this.braceLeft > 0 && !this.braceHeard)) {
      this.handBack();
      this.slideLeft = 0;
      this.braceLeft = 0;
      this.wait = 0;
    }
  }

  // A penguin drawn in the ghost's way stops it the way the bot's penguin will be stopped. Only the first touch counts,
  // since the target stays drawn where it stood until the bot moves it. Gives where and how hard it hit, to show the hit
  // now, or null with no touch
  meet(pens, seat, rules) {
    if (this.ghost.active && this.touchLeft === 0) {
      for (const pen of pens) {
        if (pen.seat !== seat && pen.fall < 0 && this.ghost.hit(pen.x, pen.z, massOf(pen.row[2]))) {
          this.touchLeft = TAP_ANSWER;
          this.echoLeft = ECHO_SECONDS;
          const { touch, ghost } = this;
          touch.x = ghost.contactX;
          touch.z = ghost.contactZ;
          touch.strength = Math.min(1, Math.max(0.2, ghost.closing / rules.slide_speed));
          touch.bracing = (pen.row[2] & FIRM) !== 0;
          touch.seat = pen.seat;
          return touch;
        }
      }
    }
    return null;
  }

  // The ghost's bounce off the walrus, to show now: where and how hard, as meet gives a touch. Null with none hard
  // enough for the bot to send word of, or one already shown
  bumped(seat, rules) {
    const { ghost, touch } = this;
    const closing = ghost.bumped;
    ghost.bumped = 0;
    if (!ghost.active || !(closing > BOUNCE_REL)) {
      return null;
    }
    this.echoLeft = ECHO_SECONDS;
    this.bumpLeft = ECHO_SECONDS;
    touch.x = ghost.contactX;
    touch.z = ghost.contactZ;
    touch.strength = Math.min(1, Math.max(0.2, closing / rules.slide_speed));
    touch.bracing = true;
    touch.seat = seat;
    return touch;
  }

  // Whether this event from the bot is the hit that meet has already shown, found by who it names: a hit names the
  // penguin struck, a bounce the one that bounced. Said once while the touch is live, so another player's hit still shows
  echoes([kind, , , , who], seat) {
    const mine = kind === "hit" ? who === this.touch.seat : kind === "bounce" && who === seat;
    if (this.echoLeft <= 0 || !mine) {
      return false;
    }
    this.echoLeft = 0;
    return true;
  }

  step(dt, rules) {
    if (this.ghost.active) {
      this.ghost.step(dt, rules, this.around);
    }
    if (runsOut(this.slideLeft, dt)) {
      this.handBack();
      this.wait = 0;
    }
    if (runsOut(this.touchLeft, dt)) {
      this.handBack();
    }
    if (runsOut(this.braceLeft, dt) && !this.braceHeard) {
      this.wait = 0;
    }
    if (runsOut(this.diveLeft, dt)) {
      this.callOffDive();
    }
    for (const count of COUNTDOWNS) {
      this[count] = Math.max(0, this[count] - dt);
    }
  }

  // Where to draw the player's penguin, given `spot`, where the bot's stream puts it now
  shown(spot) {
    this.bot = spot;
    const { ghost } = this;
    // Once the bot has taken the slide and both have stopped, any gap left is the ghost's mistake
    const bothStopped = this.slideLeft === 0 && ghost.stopped && spot.vx === 0 && spot.vz === 0;
    if (ghost.active && (ghost.age >= GHOST_SECONDS || bothStopped || ghost.settled(spot.x, spot.z))) {
      this.handBack();
    }
    if (ghost.active) {
      return { x: ghost.x, z: ghost.z, vx: ghost.vx, vz: ghost.vz };
    }
    if (this.blendLeft <= 0) {
      return spot;
    }
    const k = 1 - this.blendLeft / BLEND_SECONDS;
    return { ...spot, x: this.from.x + (spot.x - this.from.x) * k, z: this.from.z + (spot.z - this.from.z) * k };
  }

  near(x, z, reach) {
    return [this.ghost, this.bot].some((spot) => spot && Math.hypot(spot.x - x, spot.z - z) <= reach);
  }

  // Whether this event pushed the player's penguin in a way the ghost can't know about. A hit is checked against the
  // bot's stream too: by the time the news arrives, a fast ghost has run on well past the spot
  touches([kind, ...values], seat, rules) {
    if (kind === "bounce") {
      return values[3] === seat;
    }
    if (kind === "hit") {
      return values[3] === seat || this.near(values[0] / 100, values[1] / 100, HIT_WITHIN);
    }
    if (kind === "snow") {
      return this.near(values[0] / 100, values[1] / 100, SNOWBALL_REACH + SHOVE_SLACK);
    }
    if (kind === "slam") {
      const { walrus } = this.around;
      return Boolean(walrus) && this.near(walrus.x, walrus.z, WALRUS_REACH + SHOVE_SLACK);
    }
    return kind === "splash" && this.near(values[1] / 100, values[2] / 100, rules.seal_reach);
  }

  // An event from the bot, as the drawing reaches it. `seat` is the player's own
  hear(event, seat, rules) {
    // The ghost came off the walrus by the bot's own rule, so the bot's word on that bounce leaves it sliding
    const ownBump = event[0] === "bounce" && event[4] === seat && this.bumpLeft > 0;
    if (ownBump) {
      this.bumpLeft = 0;
    } else if (this.ghost.active && this.touches(event, seat, rules)) {
      this.handBack();
    }
    const [kind, who, what] = event;
    if (who !== seat) {
      // Someone else's frost freezes this player's penguin. A seal has no slide or brace waiting, so nothing changes
      if (kind === "open" && what === "frost") {
        this.frozen();
      }
      return;
    }
    if (kind === "slide") {
      this.slideLeft = 0;
    } else if (kind === "brace") {
      this.braceHeard = true;
    } else if (kind === "dive") {
      this.diveLeft = 0;
      this.startSealWait(rules);
    } else if (kind === "seal") {
      this.sealWait = PLAYER_SEAL_COOLDOWN;
    } else if (kind === "open" && what === "feast") {
      this.feast = FEAST_SLIDES - 1;
    } else if (kind === "fall") {
      // It falls from where it is drawn, so there is nothing to blend, and takes any feast into the sea with it
      this.ghost.active = false;
      this.feast = 0;
    }
  }
}

// A pile of frames let go at once would all be timed at the same moment, and the drawing would cross them in one step.
// This gives the ones the drawing hasn't reached their own moments between the first of them and the latest allowed
function spreadPile(buffer, now) {
  const first = Math.max(
    0,
    buffer.findIndex((entry) => entry.at > now - DRAW_DELAY),
  );
  const count = buffer.length - 1 - first;
  if (count < 1) {
    return;
  }
  const gap = Math.max(0, (now + MAX_AHEAD - buffer[first].at) / count);
  for (let index = first + 1; index < buffer.length; index += 1) {
    buffer[index].at = buffer[first].at + gap * (index - first);
  }
}

// Add a frame or a snapshot's board to the buffer, in arrival order, timed by the arrival clock `now` in seconds. Its
// number `f` plays no part, since that starts over every round. A frame waits for the one before it to keep the
// spacing even, as the delay from a late frame drifts away. Gives back the frames this pushed out of the buffer
// without being drawn, oldest first. `behind` is how many seconds slow motion has the drawing behind, and the buffer
// keeps that many more seconds of frames for it
export function addFrame(buffer, frame, now, behind = 0) {
  const newest = buffer[buffer.length - 1];
  const due = newest ? newest.at + TICK - DRIFT : now;
  const fresh = !newest || now - newest.at > SNAP_GAP;
  const skipped = fresh ? buffer.splice(0) : [];
  buffer.push({ at: fresh ? now : Math.min(Math.max(now, due), now + MAX_AHEAD), frame, ran: false });
  if (!fresh && due > now + MAX_AHEAD) {
    spreadPile(buffer, now);
  }
  const room = MAX_FRAMES + Math.ceil(behind * TICK_RATE);
  if (buffer.length > room) {
    skipped.push(...buffer.splice(0, buffer.length - room));
  }
  return skipped;
}

// What to draw at `now`: frames `a` and `b` and how far `k` the drawing is from one to the other, `delay` seconds
// behind the arrival clock. Null with no frames at all
export function sampleFrames(buffer, now, delay) {
  if (!buffer.length) {
    return null;
  }
  const newest = buffer[buffer.length - 1];
  if (now - newest.at > SNAP_GAP) {
    return { a: newest, b: newest, k: 0 };
  }
  const clock = now - delay;
  const index = buffer.findIndex((entry) => entry.at > clock);
  if (index === 0) {
    return { a: buffer[0], b: buffer[0], k: 0 };
  }
  if (index === -1) {
    // Out of frames for a moment: wait at the newest, and keep its movement so a late frame doesn't stop a slide
    return { a: buffer[buffer.length - 2] ?? newest, b: newest, k: 1 };
  }
  const a = buffer[index - 1];
  const b = buffer[index];
  if (b.at - a.at > SNAP_GAP) {
    return { a: b, b, k: 0 };
  }
  return { a, b, k: (clock - a.at) / (b.at - a.at) };
}

// The clock the drawing runs on. A hit sets `freeze`, the seconds to hold it for. While held, nothing moves and the bot's
// frames keep arriving, so `lag` grows; afterwards the clock runs faster until the lag is gone. `now` is the arrival
// clock in seconds and `rawDt` the engine's step. Gives how far the clock moves this frame, and sets `away` when the
// page was away long enough that its old guesses are history. Slow motion sets `rate`: under 1 the clock runs that much
// slower and the drawing falls `behind` by the rest, and over 1 it runs faster and wins that back. A page that was
// away comes back at full speed with nothing to win back
export function newClock() {
  return { lag: 0, freeze: 0, last: 0, away: false, rate: 1, behind: 0 };
}

export function stepClock(clock, rawDt, now) {
  const gap = now - clock.last;
  clock.last = now;
  clock.away = gap > SNAP_GAP;
  if (clock.away) {
    clock.lag = 0;
    clock.freeze = 0;
    clock.rate = 1;
    clock.behind = 0;
  } else if (clock.lag >= MAX_LAG) {
    clock.freeze = 0;
  }
  if (clock.freeze > 0) {
    clock.freeze -= rawDt;
    clock.lag = Math.min(MAX_LAG, clock.lag + gap);
    return 0;
  }
  const extra = Math.min(clock.lag, rawDt * CATCH_UP);
  clock.lag -= extra;
  const step = rawDt + extra;
  clock.behind = Math.max(0, clock.behind + step * (1 - clock.rate));
  return step * clock.rate;
}
