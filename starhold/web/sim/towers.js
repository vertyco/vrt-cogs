// Towers: building, upgrading, final forms and selling, and every tower's shot. Missiles and the Orbital strike fly
// as shells for a few steps and burst where their target is when they land.
import { div, dist2, isqrt } from "./num.js";
import {
  BLASTER,
  CHAIN_JUMP,
  DRONES,
  MAP,
  MIN_FLIGHT,
  MISSILE,
  MISSILE_SPEED,
  SELL_BACK,
  TESLA,
  TOWERS,
} from "./rules.js";
import { PARKS } from "./road.js";
import { emit } from "./events.js";
import { damage, findRobot, furthest, robotsNear } from "./robots.js";
import { newDrones, releaseHeld } from "./drones.js";

// Each spot's middle, in hundredths
const SPOTS = MAP.spots.map(([x, y]) => [x * 100, y * 100]);

// A missile bursting this wide or wider is a Mortar-sized blast, which shakes the screen
const MORTAR_BLAST = TOWERS[MISSILE].forms[1].blast;

// Each shooting tower's shot, by kind. Drone bays fight through their drones instead
const FIRE = [];
FIRE[BLASTER] = fireBlaster;
FIRE[MISSILE] = fireMissile;
FIRE[TESLA] = fireTesla;

/** A tower's numbers: its final form's, or its level's */
export function stats(tower) {
  const line = TOWERS[tower.kind];
  return tower.form >= 0 ? line.forms[tower.form] : line.levels[tower.level - 1];
}

function isSpot(spot) {
  return Number.isInteger(spot) && spot >= 0 && spot < SPOTS.length;
}

function towerAt(run, spot) {
  return isSpot(spot) ? run.towers[spot] : null;
}

function pay(run, tower, cost) {
  if (run.money < cost) {
    return false;
  }
  run.money -= cost;
  tower.spent += cost;
  return true;
}

// A Drone bay's live drones come back to full health at the bay's new numbers; destroyed ones keep waiting
function refreshDrones(tower) {
  if (tower.kind !== DRONES) {
    return;
  }
  const hp = stats(tower).hp;
  for (const drone of tower.drones) {
    if (drone.backAt === 0) {
      drone.hp = hp;
    }
  }
}

export function build(run, spot, kind) {
  if (!isSpot(spot) || run.towers[spot] !== null || !Number.isInteger(kind) || kind < 0 || kind >= TOWERS.length) {
    return false;
  }
  const cost = TOWERS[kind].levels[0].cost;
  if (run.money < cost) {
    return false;
  }
  run.money -= cost;
  const tower = { kind, level: 1, form: -1, spent: cost, cooldown: 0, park: -1, drones: [], nextHit: 0 };
  if (kind === DRONES) {
    tower.park = PARKS[spot];
    tower.drones = newDrones(stats(tower).hp);
  }
  run.towers[spot] = tower;
  emit(run, "build", { spot });
  return true;
}

export function upgrade(run, spot) {
  const tower = towerAt(run, spot);
  if (tower === null || tower.form >= 0 || tower.level >= 3) {
    return false;
  }
  if (!pay(run, tower, TOWERS[tower.kind].levels[tower.level].cost)) {
    return false;
  }
  tower.level += 1;
  refreshDrones(tower);
  emit(run, "upgrade", { spot });
  return true;
}

export function finalForm(run, spot, which) {
  const tower = towerAt(run, spot);
  if (tower === null || tower.form >= 0 || tower.level !== 3 || (which !== 0 && which !== 1)) {
    return false;
  }
  if (!pay(run, tower, TOWERS[tower.kind].forms[which].cost)) {
    return false;
  }
  tower.level = 4;
  tower.form = which;
  refreshDrones(tower);
  emit(run, "form", { spot });
  return true;
}

/** Selling pays back 70% of everything spent on the tower. Its shells already flying still land */
export function sell(run, spot) {
  const tower = towerAt(run, spot);
  if (tower === null) {
    return false;
  }
  const refund = div(tower.spent * SELL_BACK, 100);
  run.money += refund;
  releaseHeld(run, spot);
  run.towers[spot] = null;
  emit(run, "sell", { spot, refund });
  return true;
}

/** Every shooting tower, in spot order: its cooldown counts down each step; at 0 it fires once it has a target */
export function fireTowers(run) {
  run.towers.forEach((tower, spot) => {
    if (tower === null || tower.kind === DRONES) {
      return;
    }
    if (tower.cooldown > 0) {
      tower.cooldown -= 1;
    }
    if (tower.cooldown === 0 && FIRE[tower.kind](run, tower, spot)) {
      tower.cooldown = stats(tower).every;
    }
  });
}

function fireBlaster(run, tower, spot) {
  const gun = stats(tower);
  const [sx, sy] = SPOTS[spot];
  const target = furthest(robotsNear(run, sx, sy, gun.range, TOWERS[BLASTER].air));
  if (target === null) {
    return false;
  }
  if (gun.beam) {
    fireBeam(run, spot, target, gun);
  } else {
    emit(run, "shot", { spot, id: target.id });
    damage(run, target, gun.damage, TOWERS[BLASTER].armor);
  }
  return true;
}

// The Railgun's beam runs from the tower through its target to the end of its range, and hits every robot (flying
// ones too) within `beam` map units of that line. In whole numbers: the cross product `px * by - py * bx` is a
// robot's distance from the line times the line's length, so it is compared with the beam's width times that length
function fireBeam(run, spot, target, gun) {
  const [sx, sy] = SPOTS[spot];
  const dx = target.x - sx;
  const dy = target.y - sy;
  const length = isqrt(dx * dx + dy * dy);
  if (length === 0) {
    emit(run, "rail", { spot, x: target.x, y: target.y });
    damage(run, target, gun.damage, TOWERS[BLASTER].armor);
    return;
  }
  const reach = gun.range * 100;
  const bx = div(dx * reach, length);
  const by = div(dy * reach, length);
  emit(run, "rail", { spot, x: sx + bx, y: sy + by });
  const span = isqrt(bx * bx + by * by);
  const width = gun.beam * 100;
  for (const robot of robotsNear(run, sx, sy, gun.range + gun.beam, true)) {
    const px = robot.x - sx;
    const py = robot.y - sy;
    const along = px * bx + py * by;
    if (along >= 0 && along <= bx * bx + by * by && Math.abs(px * by - py * bx) <= width * span) {
      damage(run, robot, gun.damage, TOWERS[BLASTER].armor);
    }
  }
}

function byFurthest(a, b) {
  return b.d - a.d || a.id - b.id;
}

function fireMissile(run, tower, spot) {
  const pod = stats(tower);
  const [sx, sy] = SPOTS[spot];
  const near = robotsNear(run, sx, sy, pod.range, TOWERS[MISSILE].air);
  if (near.length === 0) {
    return false;
  }
  if (pod.missiles) {
    const order = near.slice().sort(byFurthest);
    for (let i = 0; i < pod.missiles; i++) {
      launch(run, spot, order[i % order.length], pod);
    }
  } else {
    launch(run, spot, furthest(near), pod);
  }
  return true;
}

// A missile homes on its target: it flies for a time set by the distance (a Mortar shell always takes its fixed
// flight) and bursts wherever the target is when it lands, or where the target last was if it died first
function launch(run, spot, target, pod) {
  const [sx, sy] = SPOTS[spot];
  const flight = pod.flight || Math.max(MIN_FLIGHT, div(isqrt(dist2(sx, sy, target.x, target.y)), MISSILE_SPEED));
  const shell = {
    kind: "missile",
    target: target.id,
    x: target.x,
    y: target.y,
    fromX: sx,
    fromY: sy,
    firedAt: run.step,
    landAt: run.step + flight,
    damage: pod.damage,
    blast: pod.blast,
    air: TOWERS[MISSILE].air,
    armor: TOWERS[MISSILE].armor,
    spot,
  };
  run.shells.push(shell);
  emit(run, "launch", { spot, shell });
}

// The nearest robot within CHAIN_JUMP of the last one zapped that hasn't been zapped yet, ties to the lower id
function nextZap(run, chain) {
  const last = chain[chain.length - 1];
  let best = null;
  let bestGap = 0;
  for (const robot of robotsNear(run, last.x, last.y, CHAIN_JUMP, TOWERS[TESLA].air)) {
    if (chain.includes(robot)) {
      continue;
    }
    const gap = dist2(last.x, last.y, robot.x, robot.y);
    if (best === null || gap < bestGap || (gap === bestGap && robot.id < best.id)) {
      best = robot;
      bestGap = gap;
    }
  }
  return best;
}

function fireTesla(run, tower, spot) {
  const coil = stats(tower);
  const [sx, sy] = SPOTS[spot];
  const first = furthest(robotsNear(run, sx, sy, coil.range, TOWERS[TESLA].air));
  if (first === null) {
    return false;
  }
  const chain = [first];
  while (chain.length < coil.chain) {
    const next = nextZap(run, chain);
    if (next === null) {
      break;
    }
    chain.push(next);
  }
  emit(run, "zap", { spot, ids: chain.map((robot) => robot.id) });
  for (const robot of chain) {
    damage(run, robot, coil.damage, TOWERS[TESLA].armor);
    if (coil.slow) {
      robot.slow = coil.slow;
      robot.slowUntil = run.step + coil.slowFor;
    }
  }
  return true;
}

// Mortar shells and Orbital strikes are the big blasts, which shake the screen
function explode(run, shell) {
  const strike = shell.kind === "strike";
  emit(run, "boom", { x: shell.x, y: shell.y, r: shell.blast, big: strike || shell.blast >= MORTAR_BLAST, strike });
  for (const robot of robotsNear(run, shell.x, shell.y, shell.blast, shell.air)) {
    damage(run, robot, shell.damage, shell.armor);
  }
}

/** Shells follow their live targets, and those whose time has come burst */
export function landShells(run) {
  const flying = [];
  for (const shell of run.shells) {
    const target = shell.target === -1 ? null : findRobot(run, shell.target);
    if (target !== null) {
      shell.x = target.x;
      shell.y = target.y;
    }
    if (shell.landAt > run.step) {
      flying.push(shell);
    } else {
      explode(run, shell);
    }
  }
  run.shells = flying;
}
