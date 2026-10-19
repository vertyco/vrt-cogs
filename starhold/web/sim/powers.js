// The two tap-aimed powers. Both are ready when the run starts. The Orbital strike is a shell that lands a second
// after the tap; the Stasis field acts at once.
import { MAP, POWERS } from "./rules.js";
import { emit } from "./events.js";
import { robotsNear } from "./robots.js";

function inside(x, y) {
  return Number.isInteger(x) && Number.isInteger(y) && x >= 0 && x <= MAP.width && y >= 0 && y <= MAP.height;
}

/** A beam on (x, y) in map units: it burns every robot within reach, flying ones too, one second from now */
export function strike(run, x, y) {
  if (run.step < run.strikeReady || !inside(x, y)) {
    return false;
  }
  const power = POWERS.strike;
  run.shells.push({
    kind: "strike",
    target: -1,
    x: x * 100,
    y: y * 100,
    fromX: x * 100,
    fromY: y * 100,
    firedAt: run.step,
    landAt: run.step + power.delay,
    damage: power.base + power.perWave * run.wave,
    blast: power.radius,
    air: true,
    armor: false,
    spot: -1,
  });
  run.strikeReady = run.step + power.cooldown;
  emit(run, "strike", { x: x * 100, y: y * 100 });
  return true;
}

/** Freezes every robot within reach of (x, y) for a while. Robots walking in afterward aren't caught */
export function stasis(run, x, y) {
  if (run.step < run.stasisReady || !inside(x, y)) {
    return false;
  }
  const power = POWERS.stasis;
  for (const robot of robotsNear(run, x * 100, y * 100, power.radius, true)) {
    robot.frozenUntil = run.step + power.length;
  }
  run.stasisReady = run.step + power.cooldown;
  emit(run, "stasis", { x: x * 100, y: y * 100 });
  return true;
}
