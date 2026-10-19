// The Drone bay: three drones park on the road and wall it off. While any of them is up, ground robots that walk up
// to the parking point stop there in a pile. Every second each drone hits a robot in the pile and every robot in the
// pile bites the drones, so a big crowd breaks through sooner. Once the last drone is destroyed the pile walks on one
// by one, and each drone comes back after a while. Guardians heal while nothing is piled up. Flying robots pass over.
import { DRONE, DRONES, ROBOTS, TOWERS } from "./rules.js";
import { canPark } from "./road.js";
import { emit } from "./events.js";
import { damage } from "./robots.js";

// A bay's drone numbers: its final form's, or its level's. towers.js has the same lookup, but it imports this file
function bay(tower) {
  const line = TOWERS[DRONES];
  return tower.form >= 0 ? line.forms[tower.form] : line.levels[tower.level - 1];
}

function isUp(drone) {
  return drone.backAt === 0;
}

export function newDrones(hp) {
  const drones = [];
  for (let i = 0; i < DRONE.count; i++) {
    drones.push({ hp, holding: -1, backAt: 0 });
  }
  return drones;
}

/**
 * Let go of every robot piled at the bay on this spot, as when it is sold, its drones move or its last drone falls.
 * They leave in the order they came, DRONE.drain steps apart
 */
export function releaseHeld(run, spot) {
  let leaving = 0;
  for (const robot of run.robots) {
    if (robot.heldBy === spot) {
      robot.heldBy = -1;
      robot.leaveAt = run.step + leaving * DRONE.drain;
      leaving += 1;
    }
  }
  for (const drone of run.towers[spot].drones) {
    drone.holding = -1;
  }
}

/** Move a bay's parking point to d hundredths along the road, within reach of the bay. The pile goes free */
export function parkDrones(run, spot, d) {
  const tower = Number.isInteger(spot) && spot >= 0 && spot < run.towers.length ? run.towers[spot] : null;
  if (tower === null || tower.kind !== DRONES || !Number.isInteger(d) || !canPark(spot, d)) {
    return false;
  }
  releaseHeld(run, spot);
  tower.park = d;
  emit(run, "park", { spot });
  return true;
}

/** Where each bay with a drone up stops ground robots this step: DRONE.grab map units short of its parking point */
export function wallLines(run) {
  const lines = [];
  for (const tower of run.towers) {
    if (tower !== null && tower.kind === DRONES && tower.drones.some(isUp)) {
      lines.push(tower.park - DRONE.grab * 100);
    }
  }
  return lines;
}

// The pile: ground robots within DRONE.grab map units of the parking point that no other bay holds. Each robot joining
// it makes a clank
function gather(run, tower, spot) {
  const reach = DRONE.grab * 100;
  const pile = [];
  for (const robot of run.robots) {
    if (robot.gone !== "" || ROBOTS[robot.type].flies || Math.abs(robot.d - tower.park) > reach) {
      continue;
    }
    if (robot.heldBy === -1) {
      robot.heldBy = spot;
      emit(run, "grab", { spot, id: robot.id });
    }
    if (robot.heldBy === spot) {
      pile.push(robot);
    }
  }
  return pile;
}

function down(run, tower, spot, index) {
  const drone = tower.drones[index];
  drone.hp = 0;
  drone.holding = -1;
  drone.backAt = run.step + DRONE.back;
  emit(run, "droneDown", { spot, drone: index });
  if (!tower.drones.some(isUp)) {
    releaseHeld(run, spot);
  }
}

// Each drone up hits its own robot in the pile, then every robot still standing bites the first drone up, and the
// next once that one is down
function blows(run, tower, spot, pile) {
  const info = bay(tower);
  for (const drone of tower.drones) {
    if (drone.holding !== -1) {
      damage(run, pile.find((robot) => robot.id === drone.holding), info.damage, false);
    }
  }
  for (const robot of pile) {
    const index = tower.drones.findIndex(isUp);
    if (index === -1) {
      return;
    }
    if (robot.gone === "") {
      tower.drones[index].hp -= ROBOTS[robot.type].bite;
      if (tower.drones[index].hp <= 0) {
        down(run, tower, spot, index);
      }
    }
  }
}

function runBay(run, tower, spot) {
  const info = bay(tower);
  tower.drones.forEach((drone, index) => {
    if (drone.backAt !== 0 && run.step >= drone.backAt) {
      drone.backAt = 0;
      drone.hp = info.hp;
      emit(run, "droneBack", { spot, drone: index });
    }
  });
  if (!tower.drones.some(isUp)) {
    return;
  }
  const fresh = tower.drones.every((drone) => drone.holding === -1);
  const pile = gather(run, tower, spot);
  let up = 0;
  for (const drone of tower.drones) {
    drone.holding = isUp(drone) && pile.length > 0 ? pile[up++ % pile.length].id : -1;
    if (pile.length === 0 && isUp(drone) && info.heal && run.step % DRONE.every === 0) {
      drone.hp = Math.min(info.hp, drone.hp + info.heal);
    }
  }
  if (pile.length === 0) {
    return;
  }
  // The first blows come a second after the pile starts. A blow already pending stays, so letting go and stopping
  // robots again quickly can't push the next blow back
  if (fresh && tower.nextHit <= run.step) {
    tower.nextHit = run.step + DRONE.every;
  }
  if (run.step >= tower.nextHit) {
    tower.nextHit = run.step + DRONE.every;
    blows(run, tower, spot, pile);
  }
}

/** Every bay, in spot order: drones coming back, the pile gathering, blows, bites and healing */
export function runDrones(run) {
  run.towers.forEach((tower, spot) => {
    if (tower !== null && tower.kind === DRONES) {
      runBay(run, tower, spot);
    }
  });
}
