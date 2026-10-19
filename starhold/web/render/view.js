// Which way the map is drawn. Upright, it is drawn as the rules lay it out. Turned, for wide screens, it is mirrored
// across its top-left to bottom-right diagonal: the road still starts at the top left, its long side runs across the
// screen and the core sits on the right. Only the drawing turns: the rules, moves and replays always use the map's own
// units, and everything in the scene's world is placed in view units, so robots, towers and text stay upright.
import { MAP } from "../sim/rules.js";

export const view = { turned: false };

/** A point (or a direction) in map units, in view units. Turning is a mirror, so the same swap goes back again */
export function toView(x, y) {
  return view.turned ? [y, x] : [x, y];
}

/** A point in map units as { x, y } in view units */
export function viewPoint(x, y) {
  const [vx, vy] = toView(x, y);
  return { x: vx, y: vy };
}

/** The map's size in view units */
export function viewSize(turned = view.turned) {
  return turned ? { width: MAP.height, height: MAP.width } : { width: MAP.width, height: MAP.height };
}
