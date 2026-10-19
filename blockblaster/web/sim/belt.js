// The belt: its trays, how they move and keep apart, where a pig on one stands, and which side of the picture it
// faces.
// A tray's pos is how far it has run along the lap from the start point, in L. board.json's belt table holds a point
// every 100 L of the lap in picture space, so neither side ever evaluates the curve. common/sim/belt.py mirrors this.
import * as base from "./base.js";
import { idiv } from "./mathx.js";
import { BELT_SPEED, BELT_SPEED_FINISH, TRAY_PUSH_MAX, TRAY_SPACING } from "./numbers.js";

// Sides of the picture a pig can face (ShootersOffenseController.Side)
export const LEFT = 0;
export const RIGHT = 1;
export const BOTTOM = 2;
export const TOP = 3;
// The way a pig on each side faces: straight into the picture, picture space
export const INWARD = {
  [LEFT]: [1, 0],
  [RIGHT]: [-1, 0],
  [BOTTOM]: [0, 1],
  [TOP]: [0, -1],
};

// Trays the belt carries: the level's ConveyorLimit plus one per Tray booster used
export function trayTotal(state) {
  return state.trayTotal;
}

// Trays neither reserved nor carrying a pig (ConveyorController$$CanReceiveItemCount, RVA 0x58A8FFC)
export function freeTrays(state) {
  return state.trayTotal - state.belt.length;
}

// Hold a tray for a pig about to hop on. It waits off the lap until startTray
export function reserve(state, pigId) {
  const tray = { id: state.traySeq, pos: 0, started: false, pig: pigId };
  state.traySeq += 1;
  // Started trays stay at the front of the list, newest first; reserved ones wait behind them
  state.belt.push(tray);
  return tray;
}

export function findTray(state, trayId) {
  for (const tray of state.belt) {
    if (tray.id === trayId) {
      return tray;
    }
  }
  return null;
}

// Timer: the tray enters the lap at the start point and becomes the newest tray
// (ConveyorController$$TryActivateSlot, RVA 0x58A8C10). It first moves on the next tick
export function startTray(state, trayId) {
  const tray = findTray(state, trayId);
  if (tray === null) {
    return;
  }
  state.belt.splice(state.belt.indexOf(tray), 1);
  tray.started = true;
  tray.pos = 0;
  state.belt.unshift(tray);
  addShooter(state, tray.pig);
  base.emit(state, "tray_started", { tray: tray.id, pig: tray.pig });
}

// A pig whose tray just started joins the shooters, its fire timer fresh so it may fire at once
// (ShootersOffenseController$$AddShooterFromGameObject, RVA 0x5453274)
export function addShooter(state, pigId) {
  state.shooters.push(pigId);
  state.pigs[pigId].nextFire = 0;
}

export function removeShooter(state, pigId) {
  const index = state.shooters.indexOf(pigId);
  if (index >= 0) {
    state.shooters.splice(index, 1);
  }
}

// Take a pig's tray off the belt, started or still reserved; the tray is free again at once
// (ConveyorController$$Remove, RVA 0x58A6FC0)
export function remove(state, pigId) {
  const index = state.belt.findIndex((tray) => tray.pig === pigId);
  if (index >= 0) {
    state.belt.splice(index, 1);
  }
  removeShooter(state, pigId);
}

export function startedTrays(state) {
  return state.belt.filter((tray) => tray.started);
}

// Phase 2 (ConveyorController$$Update, RVA 0x58A5CC0): every started tray runs on, the spacing pushes trays that sit
// too close, then trays at the lap's end loop (auto-finisher) or leave. Returns the pigs that passed the fail-warning
// checkpoint and the pigs that left, both in list order
export function moveTrays(state) {
  const trays = startedTrays(state);
  if (!trays.length) {
    return [[], []];
  }
  if (state.finishing) {
    // Looping trays wrap to the start, so the list is put back in lap order first (newest, lowest pos, first)
    trays.sort((a, b) => a.pos - b.pos);
    state.belt = trays.concat(state.belt.filter((tray) => !tray.started));
  }
  const end = state.beltPath.end;
  const speed = state.finishing ? BELT_SPEED_FINISH : BELT_SPEED;
  const ran = trays.map((tray) => Math.min(end, tray.pos + speed));
  const pushed = pushTargets(ran, end);
  const checkpoint = state.beltPath.checkpoint;
  const crossed = [];
  trays.forEach((tray, index) => {
    const old = tray.pos;
    tray.pos = settle(tray.pos, ran[index], pushed[index]);
    if (old < checkpoint && checkpoint <= tray.pos) {
      crossed.push(tray.pig);
    }
  });
  return [crossed, reachEnd(state, end)];
}

// Where each tray must be to stay TRAY_SPACING ahead of the tray behind it, working from the newest tray forward
// (ConveyorController$$EnforceSpacing, RVA 0x58A622C). Nothing is pushed past the lap's end
export function pushTargets(ran, end) {
  const pushed = [...ran];
  for (let index = 0; index < ran.length - 1; index++) {
    const need = Math.min(end, pushed[index] + TRAY_SPACING);
    pushed[index + 1] = Math.min(end, Math.max(pushed[index + 1], need, ran[index + 1]));
  }
  return pushed;
}

// A pushed tray closes on its pushed spot at most TRAY_PUSH_MAX a tick from where it was, never falling behind where
// the belt alone would take it (the second pass of ConveyorController$$Update)
export function settle(old, ran, pushed) {
  if (ran >= pushed) {
    return ran;
  }
  if (pushed - old > TRAY_PUSH_MAX) {
    return Math.max(ran, old + TRAY_PUSH_MAX);
  }
  return pushed;
}

// While the auto-finisher runs a tray goes back to the start instead of leaving, unless a feature says its pig must
// leave (ConveyorStayInInfiniteLoopCondition$$Call, RVA 0x5908258)
export function keepsLooping(state, pigId) {
  for (const module of base.MODULES) {
    if (module.keepLooping && !module.keepLooping(state, state.pigs[pigId])) {
      return false;
    }
  }
  return true;
}

// Trays at the lap's end, in list order: while the auto-finisher runs they loop unless a feature holds them to the
// normal exit. A leaving tray is taken out of the list at once and the walk moves on to the
// next index, so the tray behind it in the list waits a tick, as the original's loop does. Returns the pigs that left
export function reachEnd(state, end) {
  const exited = [];
  let index = 0;
  while (index < state.belt.length) {
    const tray = state.belt[index];
    if (tray.started && tray.pos >= end) {
      if (state.finishing && keepsLooping(state, tray.pig)) {
        tray.pos = 0;
      } else {
        state.belt.splice(index, 1);
        removeShooter(state, tray.pig);
        base.emit(state, "lap_end", { tray: tray.id, pig: tray.pig });
        exited.push(tray.pig);
      }
    }
    index += 1;
  }
  return exited;
}

// The lap point pos L from the start point, picture space, and the index of the table segment it sits on
export function point(state, pos) {
  const path = state.beltPath;
  const points = path.points;
  const step = path.step;
  const seg = Math.min(points.length - 2, idiv(pos, step));
  const part = pos - seg * step;
  const [x0, y0] = points[seg];
  const [x1, y1] = points[seg + 1];
  return [x0 + idiv((x1 - x0) * part, step), y0 + idiv((y1 - y0) * part, step), seg];
}

// Where the pig on this tray shoots from, picture space, L. Before every shot the pig turns to face straight into the
// picture from its side (ShootersOffenseController$$LookAtDirection, RVA 0x5452BE0), so its shoot point (board.json
// weapon, [right, up, forward]) sits forward along that side's inward direction. Its height is muzzleHeight
export function position(state, tray) {
  const [x, y] = point(state, tray.pos);
  const [fx, fy] = INWARD[side(state, tray)];
  const [right, , forward] = state.weapon;
  // Seen from above, the pig's right is its forward turned a quarter clockwise
  return [x + right * fy + forward * fx, y - right * fx + forward * fy];
}

// The shoot point's height above the picture, L: the belt's surface plus the shoot point's height on the pig
export function muzzleHeight(state) {
  return state.beltPath.height + state.weapon[1];
}

// The side of the picture the pig on this tray shoots from, by where the pig stands
// (ShootersOffenseController$$GetShooterSide, RVA 0x54520C4): Left or Right when |x| >= |y|, else Bottom or Top
export function side(state, tray) {
  const [x, y] = point(state, tray.pos);
  if (Math.abs(x) >= Math.abs(y)) {
    return x >= 0 ? RIGHT : LEFT;
  }
  return y < 0 ? BOTTOM : TOP;
}
