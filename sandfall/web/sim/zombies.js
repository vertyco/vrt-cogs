// The zombies and the Hand tool: Hell of Sand's stick figures, 11 points tied by 10 springs and moved by Verlet steps
// (a point's speed is where it is minus where it was). They stand on any filled cell, walk toward the slug, cling to
// it, catch fire and are reborn. The Hand grabs slug and zombie points and drags them; letting go throws them.
//
// Positions are in 256ths of a cell, scale in 1000ths. Lengths are a third of the original's (its world was three
// times wider). The original's walking pushes are fractions of a 256th, so they are kept in 100ths of a 256th and
// spread over the steps (see nudge), which keeps their size instead of rounding them away.
import { EL } from "./elements.js";
import { put } from "./helpers.js";
import { isqrt } from "./trig.js";
import { H, W } from "./world.js";
import { GRAB_MAX, SLUG_REFS, ZOMBIE_MAX, ZOMBIE_POINTS } from "./zombiebytes.js";

export { packGrabs, packZombies, unpackGrabs, unpackZombies, ZOMBIE_POINTS } from "./zombiebytes.js";

const ONE = 256;
// The original's body size of 2, a third as long
const SIZE = 171;
// The original scales every push by 5 x size
const F4 = 5 * SIZE;
const FULL = 1000;
// A new zombie starts small and grows 0.03 a step, about a third of a second at normal speed. The original starts at
// a thousandth; in whole 256ths a body that small loses which way is up, so this starts one growing step later.
const BORN = 30;
const GROW = 30;
// Each point sitting on fire takes 0.009 off its scale a step
const BURN = 9;
// 0.999 of the speed stays each step: a 1024th is lost
const DAMP_LOSS = 1024;
const WALK_CYCLE = 200;
// When a point hits the world's edge it keeps a tenth of its sideways move (a half at the bottom)
const EDGE_SLIDE = 102;
const FLOOR_SLIDE = 512;
// Slug points within this of a zombie's hand or foot can be clung to: the original's 8, a third as long
const CLING = Math.trunc((8 * ONE) / 3);
// The Hand reaches 8 cells
const REACH = 8 * ONE;
const NO_GLUE = 255;
const SLUG_MOVE = 0;
const SPOT_TRIES = 8;
// Points 6 to 10 (a knee, the hands and the feet) are the ones that cling, as in the original
const FIRST_CLINGER = 6;

// Head-chest, chest-hip, chest to each elbow, hip to each knee, elbow to hand, knee to foot
const LINK_A = [0, 1, 1, 1, 2, 2, 3, 4, 5, 6];
const LINK_B = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// A push in 100ths of a 256th, from a number in millionths of the original's 5 x size
function amount(millionths) {
  return Math.trunc((millionths * F4) / 10000);
}

const STAND = amount(1000);
const ARM_OUT = amount(100);
const FOOT_DOWN = amount(20000);
const BALANCE = amount(5000);
// The walking pushes include the original's 0.8 toward the slug
const STEP_UP = amount(8000);
const STEP_BACK = amount(4000);
const LEAN = amount(16000);
const WALK = amount(800);

/**
 * Adds a push of hundredths (100ths of a 256th) to arr[p]. Over any 100 steps the whole 256ths added sum to exactly
 * hundredths, so a push of 0.68 lands as 1 on 68 steps in 100 rather than rounding to 1 or 0 every step.
 */
function nudge(arr, p, hundredths, t) {
  const a = Math.abs(hundredths);
  const v = Math.trunc(((t + 1) * a) / 100) - Math.trunc((t * a) / 100);
  arr[p] += hundredths < 0 ? -v : v;
}

// The resting body around (0, 0), from its arm length f and leg length f2 (both in 256ths)
function bodyPoints(f, f2) {
  const arm = Math.trunc((f * SIZE) / ONE);
  const leg = Math.trunc((f2 * SIZE) / ONE);
  const xs = [0, 0, 0, -arm, arm, -SIZE, SIZE, -2 * arm, 2 * arm, -SIZE, SIZE];
  const ys = [-4 * SIZE, -SIZE, 2 * SIZE, 0, 0, leg, leg, 0, 0, 2 * leg, 2 * leg];
  return [xs, ys];
}

function restLengths(zombie) {
  const [xs, ys] = bodyPoints(zombie.f, zombie.f2);
  const rest = new Int32Array(LINK_A.length);
  for (let l = 0; l < LINK_A.length; l++) {
    const dx = xs[LINK_B[l]] - xs[LINK_A[l]];
    const dy = ys[LINK_B[l]] - ys[LINK_A[l]];
    rest[l] = isqrt(dx * dx + dy * dy);
  }
  return rest;
}

// Whether every point of the body placed at (cx, cy) (256ths) sits in an empty cell inside the world
function spotFree(w, xs, ys, cx, cy) {
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    const x = (cx + xs[p]) >> 8;
    const y = (cy + ys[p]) >> 8;
    if (x < 1 || x > W - 2 || y < 1 || y > H - 2 || w.el[y * W + x] !== 0) {
      return false;
    }
  }
  return true;
}

// A random spot (256ths) where the whole body is in empty cells, if one turns up in a few tries
function pickSpot(w, xs, ys, d) {
  let cx = 0;
  let cy = 0;
  for (let t = 0; t < SPOT_TRIES; t++) {
    cx = (4 + d.roll(W - 8)) * ONE + (ONE >> 1);
    cy = (4 + d.roll(H - 12)) * ONE + (ONE >> 1);
    if (spotFree(w, xs, ys, cx, cy)) {
      break;
    }
  }
  return [cx, cy];
}

// Born tiny at a random spot; its springs pull it to a dot at once, then it grows
function spawn(w, d, zombie) {
  zombie.f = 512 + d.roll(256);
  zombie.f2 = 1024 + d.roll(256);
  zombie.scale = BORN;
  zombie.walk = 0;
  zombie.on = 0;
  zombie.glue = NO_GLUE;
  zombie.to = 0;
  const [xs, ys] = bodyPoints(zombie.f, zombie.f2);
  const [cx, cy] = pickSpot(w, xs, ys, d);
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    zombie.x[p] = zombie.lx[p] = cx + xs[p];
    zombie.y[p] = zombie.ly[p] = cy + ys[p];
  }
  return zombie;
}

function newZombie(w, d) {
  const zombie = {
    x: new Int32Array(ZOMBIE_POINTS),
    y: new Int32Array(ZOMBIE_POINTS),
    lx: new Int32Array(ZOMBIE_POINTS),
    ly: new Int32Array(ZOMBIE_POINTS),
  };
  return spawn(w, d, zombie);
}

// The world menu's zombie count: new ones are born, extra ones go (and any hand holding them lets go)
function matchCount(w, d) {
  const want = Math.min(ZOMBIE_MAX, w.settings.zombies);
  while (w.zombies.length < want) {
    w.zombies.push(newZombie(w, d));
  }
  if (w.zombies.length > want) {
    w.zombies.length = want;
    dropRefs(w, (ref) => ref >= SLUG_REFS + want * ZOMBIE_POINTS);
  }
}

// The leg that is up this part of the cycle steps toward the slug while the body leans; the arms swing back
function walkPushes(zombie, dir, t) {
  const { x, y } = zombie;
  const leg = zombie.walk < 50 ? [5, 9] : zombie.walk >= 100 && zombie.walk < 150 ? [6, 10] : null;
  if (leg !== null) {
    for (const p of leg) {
      nudge(y, p, -STEP_UP * dir, t);
      nudge(x, p, -STEP_BACK * dir, t);
    }
    nudge(y, 1, -LEAN * dir, t);
    nudge(y, 2, LEAN * dir, t);
  }
  for (const p of [3, 4, 7, 8]) {
    nudge(x, p, -WALK * dir, t);
  }
  for (const p of [0, 1, 2]) {
    nudge(x, p, WALK * dir, t);
  }
  zombie.walk = zombie.walk >= WALK_CYCLE ? 1 : zombie.walk + 1;
}

// A push of hundredths along the line from point a to point b, as [x, y]
function along(zombie, a, b, hundredths) {
  const { x, y } = zombie;
  const dx = x[b] - x[a];
  const dy = y[b] - y[a];
  const length = isqrt(dx * dx + dy * dy);
  if (length === 0) {
    return [0, 0];
  }
  return [Math.trunc((dx * hundredths) / length), Math.trunc((dy * hundredths) / length)];
}

// Standing: head up, feet down, arms out, legs apart
function standPushes(zombie, t) {
  const { x, y } = zombie;
  nudge(y, 0, -STAND, t);
  nudge(y, 1, -STAND, t);
  nudge(x, 5, -STAND, t);
  nudge(x, 6, STAND, t);
  nudge(y, 9, FOOT_DOWN, t);
  nudge(y, 10, FOOT_DOWN, t);
  nudge(y, 3, STAND, t);
  nudge(y, 4, STAND, t);
  nudge(x, 3, -ARM_OUT, t);
  nudge(x, 4, ARM_OUT, t);
  nudge(y, 7, -STAND, t);
  nudge(y, 8, -STAND, t);
  legs(zombie, 1, t);
}

// Falling: every point drops a little, and the legs draw together
function fallPushes(zombie, t) {
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    nudge(zombie.y, p, STAND, t);
  }
  legs(zombie, -1, t);
}

// Knees and feet apart (sign 1) or together (-1)
function legs(zombie, sign, t) {
  const { x, y } = zombie;
  const [ux, uy] = along(zombie, 5, 6, STAND * sign);
  for (const [p, s] of [
    [6, 1],
    [5, -1],
    [9, -1],
    [10, 1],
  ]) {
    nudge(x, p, ux * s, t);
    nudge(y, p, uy * s, t);
  }
}

// The chest leans over the hip, away from the feet
function balance(zombie, t) {
  const { x, y } = zombie;
  const dx = 2 * x[2] - x[5] - x[6];
  const dy = 2 * y[2] - y[5] - y[6];
  const length = isqrt(dx * dx + dy * dy);
  if (length > 0) {
    nudge(x, 1, Math.trunc((dx * BALANCE) / length), t);
    nudge(y, 1, Math.trunc((dy * BALANCE) / length), t);
  }
}

// Every spring pulls or pushes its two points, half each, toward its rest length times scale
function springs(zombie) {
  const { x, y, scale } = zombie;
  const rest = restLengths(zombie);
  for (let l = 0; l < LINK_A.length; l++) {
    const a = LINK_A[l];
    const b = LINK_B[l];
    const dx = x[b] - x[a];
    const dy = y[b] - y[a];
    const length = isqrt(dx * dx + dy * dy);
    if (length === 0) {
      continue;
    }
    const diff = Math.trunc((rest[l] * scale) / FULL) - length;
    const mx = Math.trunc((dx * diff) / (2 * length));
    const my = Math.trunc((dy * diff) / (2 * length));
    x[a] -= mx;
    y[a] -= my;
    x[b] += mx;
    y[b] += my;
  }
}

// Holds point p inside the world. Returns true when it touched an edge.
function edge(zombie, p) {
  const { x, y, lx, ly } = zombie;
  if (x[p] < ONE) {
    x[p] = ONE;
    y[p] = ly[p] + Math.trunc(((y[p] - ly[p]) * EDGE_SLIDE) / 1024);
  } else if (x[p] >= (W - 1) * ONE) {
    x[p] = (W - 1) * ONE - 1;
    y[p] = ly[p] + Math.trunc(((y[p] - ly[p]) * EDGE_SLIDE) / 1024);
  } else if (y[p] < 0) {
    y[p] = 0;
    x[p] = lx[p] + Math.trunc(((x[p] - lx[p]) * EDGE_SLIDE) / 1024);
  } else if (y[p] >= (H - 1) * ONE) {
    y[p] = (H - 1) * ONE - 1;
    x[p] = lx[p] + Math.trunc(((x[p] - lx[p]) * FLOOR_SLIDE) / 1024);
  } else {
    return false;
  }
  return true;
}

// Fire under a point spreads to the empty cells beside it and burns the zombie a little
function burn(w, zombie, i, d) {
  for (const j of [i - 1, i + 1, i - W, i + W]) {
    const x = j % W;
    if (x >= 1 && x <= W - 2 && j >= W && j < (H - 1) * W && w.el[j] === 0) {
      put(w, j, EL.fire, d);
    }
  }
  zombie.scale -= BURN;
}

// A point with a filled cell under it stands there: it goes back to where it was
function collide(w, zombie, d) {
  const { x, y, lx, ly } = zombie;
  zombie.on = 0;
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    if (edge(zombie, p)) {
      zombie.on = 1;
      continue;
    }
    const i = ((y[p] >> 8) + 1) * W + (x[p] >> 8);
    const below = w.el[i];
    if (below === 0) {
      continue;
    }
    zombie.on = 1;
    x[p] = lx[p];
    y[p] = ly[p];
    if (below === EL.fire) {
      burn(w, zombie, i, d);
    }
  }
}

// Verlet: each point keeps 1023/1024 of its last move. The lost part is taken off rather than the kept part rounded
// down, which would cost a slow point a whole 256th every step and stop it.
function coast(zombie) {
  const { x, y, lx, ly } = zombie;
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    const vx = x[p] - lx[p] - Math.trunc((x[p] - lx[p]) / DAMP_LOSS);
    const vy = y[p] - ly[p] - Math.trunc((y[p] - ly[p]) / DAMP_LOSS);
    lx[p] = x[p];
    ly[p] = y[p];
    x[p] += vx;
    y[p] += vy;
  }
}

// One zombie's step. Burnt away, it is reborn at a random spot, and anything holding it lets go.
function stepOne(w, z, d, goalX, t) {
  const zombie = w.zombies[z];
  zombie.scale = Math.min(FULL, zombie.scale + GROW);
  if (zombie.scale < 0) {
    spawn(w, d, zombie);
    const first = SLUG_REFS + z * ZOMBIE_POINTS;
    dropRefs(w, (ref) => ref >= first && ref < first + ZOMBIE_POINTS);
  }
  if (zombie.on) {
    walkPushes(zombie, zombie.x[0] < goalX ? 1 : -1, t);
    standPushes(zombie, t);
  } else {
    fallPushes(zombie, t);
  }
  balance(zombie, t);
  springs(zombie);
  collide(w, zombie, d);
  coast(zombie);
}

// A clinging zombie's point rides on its slug point
function ride(slug, zombie) {
  const { glue: p, to: q } = zombie;
  zombie.x[p] = slug.x[q];
  zombie.y[p] = slug.y[q];
  zombie.lx[p] = slug.lx[q];
  zombie.ly[p] = slug.ly[q];
}

// A zombie whose head is inside the slug grabs it with the first hand or foot near one of its outline points
function cling(slug, zombie) {
  const { x, y } = zombie;
  const reach = Math.trunc((slug.scale * 5 * ONE) / 3000);
  const hx = x[0] - slug.x[0];
  const hy = y[0] - slug.y[0];
  if (hx * hx + hy * hy >= reach * reach) {
    return;
  }
  for (let q = 1; q < slug.x.length; q++) {
    for (let p = FIRST_CLINGER; p < ZOMBIE_POINTS; p++) {
      const dx = x[p] - slug.x[q];
      const dy = y[p] - slug.y[q];
      if (dx * dx + dy * dy < CLING * CLING) {
        zombie.glue = p;
        zombie.to = q;
        return;
      }
    }
  }
}

function letGo(w) {
  for (const zombie of w.zombies) {
    zombie.glue = NO_GLUE;
  }
}

// Removes every grabbed point whose ref passes test
function dropRefs(w, test) {
  for (const grab of w.grabs.values()) {
    grab.refs = grab.refs.filter((ref) => !test(ref));
  }
}

/** The slug burst (or went away): clinging zombies fall off and hands holding it let go */
export function dropSlugHolds(w) {
  letGo(w);
  dropRefs(w, (ref) => ref < SLUG_REFS);
}

// The arrays holding a point ref, or null when the creature isn't there
function pointOf(w, ref) {
  if (ref < SLUG_REFS) {
    const slug = w.slug;
    return slug !== null && ref < slug.x.length ? [slug, ref] : null;
  }
  const z = Math.trunc((ref - SLUG_REFS) / ZOMBIE_POINTS);
  return z < w.zombies.length ? [w.zombies[z], (ref - SLUG_REFS) % ZOMBIE_POINTS] : null;
}

function grabTarget(grab) {
  return [
    grab.fx + Math.trunc(((grab.tx - grab.fx) * grab.k) / grab.n),
    grab.fy + Math.trunc(((grab.ty - grab.fy) * grab.k) / grab.n),
  ];
}

// Each grabbed point is put on its hand's spot, which slides from the last spot to the new one over the batch. Only
// the position moves, so the point keeps the speed of the drag and flies on when let go.
function pin(w, grab) {
  const [tx, ty] = grabTarget(grab);
  for (const ref of grab.refs) {
    const found = pointOf(w, ref);
    if (found !== null) {
      found[0].x[found[1]] = tx;
      found[0].y[found[1]] = ty;
    }
  }
}

function holdGrabs(w) {
  for (const grab of w.grabs.values()) {
    if (grab.k < grab.n) {
      grab.k += 1;
    }
    pin(w, grab);
  }
}

/** One step of the zombies and the hands, after the slug */
export function stepZombies(w, d) {
  const slug = w.slug;
  const moving = slug !== null && w.settings.slug === SLUG_MOVE;
  if (!moving) {
    dropSlugHolds(w);
  }
  matchCount(w, d);
  const t = w.step % 100;
  const goalX = slug !== null ? slug.x[0] : (W * ONE) >> 1;
  for (let z = 0; z < w.zombies.length; z++) {
    const zombie = w.zombies[z];
    if (moving && zombie.glue !== NO_GLUE) {
      ride(slug, zombie);
    }
    stepOne(w, z, d, goalX, t);
    if (moving && zombie.glue === NO_GLUE) {
      cling(slug, zombie);
    }
  }
  holdGrabs(w);
}

// The point of a creature nearest (cx, cy) within the Hand's reach, from point first on, or -1
function nearest(xs, ys, cx, cy, first) {
  let best = -1;
  let bestDist = REACH * REACH;
  for (let p = first; p < xs.length; p++) {
    const dx = xs[p] - cx;
    const dy = ys[p] - cy;
    const dist = dx * dx + dy * dy;
    if (dist < bestDist) {
      best = p;
      bestDist = dist;
    }
  }
  return best;
}

// One point from each creature in reach (the slug first, then the zombies in order), at most GRAB_MAX
function pickPoints(w, cx, cy) {
  const refs = [];
  if (w.slug !== null && w.settings.slug === SLUG_MOVE) {
    // Its outline, never its centre: held by the centre, the body and eyes would trail behind the hand
    const p = nearest(w.slug.x, w.slug.y, cx, cy, 1);
    if (p >= 0) {
      refs.push(p);
    }
  }
  for (let z = 0; z < w.zombies.length && refs.length < GRAB_MAX; z++) {
    const zombie = w.zombies[z];
    const p = nearest(zombie.x, zombie.y, cx, cy, 0);
    if (p >= 0) {
      refs.push(SLUG_REFS + z * ZOMBIE_POINTS + p);
    }
  }
  return refs;
}

/**
 * A HAND stroke [7, phase, 0, 0, 0, 0, x, y] from player: phase 0 grabs what is in reach of (x, y), 1 drags it toward
 * (x, y) over the next `steps` steps, 2 lets go. Each player's grab is their own.
 */
export function handStroke(w, player, phase, cell, steps) {
  const cx = cell[0] * ONE + (ONE >> 1);
  const cy = cell[1] * ONE + (ONE >> 1);
  const grab = w.grabs.get(player);
  if (phase === 0) {
    w.grabs.delete(player);
    const refs = pickPoints(w, cx, cy);
    if (refs.length > 0) {
      const fresh = { refs, fx: cx, fy: cy, tx: cx, ty: cy, k: 1, n: 1 };
      w.grabs.set(player, fresh);
      pin(w, fresh);
    }
  } else if (phase === 1 && grab !== undefined) {
    [grab.fx, grab.fy] = grabTarget(grab);
    grab.tx = cx;
    grab.ty = cy;
    grab.k = 0;
    grab.n = Math.min(255, Math.max(1, steps));
  } else if (phase === 2) {
    w.grabs.delete(player);
  }
}
