// Robots: spawning, walking the road, taking damage, dying, bursting into Skitters and leaking into the core.
import { div, dist2 } from "./num.js";
import { POWERS, ROBOTS, SKITTER, WAVES } from "./rules.js";
import { pointAt, ROAD_LENGTH } from "./road.js";
import { emit } from "./events.js";

// Health growth per wave, in per mille, worked out from wave 1 in order so a wave always gets the same number. Index
// 0 stands in for anything that comes before the first wave
const SCALES = [1000, 1000];

/** How much tougher wave n's robots are than wave 1's, in per mille: 10% more a wave, compounding */
export function healthScale(wave) {
  while (SCALES.length <= wave) {
    SCALES.push(div(SCALES[SCALES.length - 1] * WAVES.growth, 100));
  }
  return SCALES[wave < 0 ? 0 : wave];
}

export function robotHp(type, wave) {
  return div(ROBOTS[type].hp * healthScale(wave), 1000);
}

export function placeRobot(robot) {
  const [x, y] = pointAt(robot.d);
  robot.x = x;
  robot.y = y;
}

/** A new robot d hundredths along the road. `wave` is the wave whose points multiplier it carries */
export function spawn(run, type, wave, d) {
  const hp = robotHp(type, wave);
  const robot = {
    id: run.nextId,
    type,
    wave,
    hp,
    maxHp: hp,
    d,
    x: 0,
    y: 0,
    slowUntil: 0,
    slow: 0,
    frozenUntil: 0,
    heldBy: -1,
    leaveAt: 0,
    nextDrop: run.step + (ROBOTS[type].drops || 0),
    gone: "",
  };
  run.nextId += 1;
  placeRobot(robot);
  run.robots.push(robot);
  emit(run, "enter", { id: robot.id, type });
  return robot;
}

/** Hundredths this robot walks this step: slowed by a Disruptor, stopped by Stasis (which only slows a boss) */
function speedOf(run, robot) {
  const info = ROBOTS[robot.type];
  let speed = info.speed;
  if (robot.slowUntil > run.step) {
    speed = div(speed * (100 - robot.slow), 100);
  }
  if (robot.frozenUntil > run.step) {
    speed = info.boss ? div(speed * POWERS.stasis.bossSpeed, 100) : 0;
  }
  return speed;
}

// The Colossus drops a Skitter where it walks, every `drops` steps; a drop that comes due while it is held waits for
// its next walking step. Stasis only slows it, so it keeps dropping
function dropSkitter(run, robot) {
  const every = ROBOTS[robot.type].drops;
  if (!every || run.step < robot.nextDrop) {
    return;
  }
  robot.nextDrop = run.step + every;
  spawn(run, SKITTER, robot.wave, robot.d);
}

function leak(run, robot) {
  const lives = ROBOTS[robot.type].lives;
  robot.gone = "leaked";
  run.lives = Math.max(0, run.lives - lives);
  emit(run, "leak", { id: robot.id, lives });
  if (run.lives === 0 && !run.over) {
    run.over = true;
    emit(run, "over", {});
  }
}

// A ground robot walking up to a Drone bay's wall stops at it. `lines` are the walls' road distances
function wallAhead(robot, to, lines) {
  if (ROBOTS[robot.type].flies) {
    return to;
  }
  for (const line of lines) {
    if (robot.d < line && to > line) {
      to = line;
    }
  }
  return to;
}

/**
 * Every robot on the road walks one step, and ground robots stop at the first Drone bay wall ahead (`lines`, road
 * distances). Robots dropped during this step start walking on the next
 */
export function moveRobots(run, lines) {
  const count = run.robots.length;
  for (let i = 0; i < count; i++) {
    const robot = run.robots[i];
    if (robot.gone !== "" || robot.heldBy !== -1 || robot.leaveAt > run.step) {
      continue;
    }
    const speed = speedOf(run, robot);
    robot.d = wallAhead(robot, robot.d + speed, lines);
    placeRobot(robot);
    // Nothing drops at the core: the Colossus leaks this step
    if (speed > 0 && robot.d < ROAD_LENGTH) {
      dropSkitter(run, robot);
    }
    if (robot.d >= ROAD_LENGTH) {
      leak(run, robot);
    }
  }
}

/**
 * Damage a robot still on the road. Armored robots halve damage from weapons armor stops. A robot dies once: it pays
 * its bounty, scores its points times its wave, and a Splitter bursts into Skitters where it fell
 */
export function damage(run, robot, amount, halvedByArmor) {
  if (robot.gone !== "") {
    return;
  }
  const info = ROBOTS[robot.type];
  robot.hp -= halvedByArmor && info.armored ? div(amount, 2) : amount;
  emit(run, "hit", { id: robot.id });
  if (robot.hp > 0) {
    return;
  }
  robot.gone = "dead";
  run.money += info.bounty;
  run.score += info.points * robot.wave;
  emit(run, "die", { id: robot.id, type: robot.type, x: robot.x, y: robot.y });
  if (info.splits) {
    emit(run, "split", { id: robot.id });
    for (let i = 0; i < info.splits; i++) {
      spawn(run, SKITTER, robot.wave, robot.d);
    }
  }
}

/** The robot with this id, while it is still on the road */
export function findRobot(run, id) {
  for (const robot of run.robots) {
    if (robot.id === id) {
      return robot.gone === "" ? robot : null;
    }
  }
  return null;
}

/** Robots still on the road within `radius` map units of (x, y) in hundredths. Flying ones only when `air` */
export function robotsNear(run, x, y, radius, air) {
  const reach = radius * 100;
  const found = [];
  for (const robot of run.robots) {
    if (robot.gone !== "" || (!air && ROBOTS[robot.type].flies)) {
      continue;
    }
    if (dist2(x, y, robot.x, robot.y) <= reach * reach) {
      found.push(robot);
    }
  }
  return found;
}

/** The robot furthest along the road, ties going to the lower id, or null for none */
export function furthest(robots) {
  let best = null;
  for (const robot of robots) {
    if (best === null || robot.d > best.d || (robot.d === best.d && robot.id < best.id)) {
      best = robot;
    }
  }
  return best;
}

/** Robots that died or leaked this step leave the road */
export function removeGone(run) {
  run.robots = run.robots.filter((robot) => robot.gone === "");
}
