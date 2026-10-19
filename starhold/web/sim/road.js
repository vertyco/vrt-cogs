// The road's geometry. Robots follow the road by distance walked, in hundredths of a map unit. Every segment runs
// straight across or straight up or down, so every length is a whole number and no square root is needed.
import { dist2 } from "./num.js";
import { DRONE, MAP } from "./rules.js";

// The road's points in hundredths, and how far along the road each point is
const POINTS = MAP.road.map(([x, y]) => [x * 100, y * 100]);
const STARTS = [0];
for (let i = 1; i < POINTS.length; i++) {
  const [ax, ay] = POINTS[i - 1];
  const [bx, by] = POINTS[i];
  STARTS.push(STARTS[i - 1] + Math.abs(bx - ax) + Math.abs(by - ay));
}

export const ROAD_LENGTH = STARTS[STARTS.length - 1];

/** The point d hundredths along the road. Before its start the road runs on backward; past its end is the core */
export function pointAt(d) {
  if (d >= ROAD_LENGTH) {
    const [x, y] = POINTS[POINTS.length - 1];
    return [x, y];
  }
  let i = 1;
  while (i < POINTS.length - 1 && STARTS[i] <= d) {
    i += 1;
  }
  const [ax, ay] = POINTS[i - 1];
  const [bx, by] = POINTS[i];
  const along = d - STARTS[i - 1];
  return [ax + Math.sign(bx - ax) * along, ay + Math.sign(by - ay) * along];
}

/** How far along the road (hundredths) the road point nearest (x, y) is, checking every whole map unit */
export function nearestRoad(x, y) {
  let best = 0;
  let bestGap = -1;
  for (let d = 0; d <= ROAD_LENGTH; d += 100) {
    const [px, py] = pointAt(d);
    const gap = dist2(x, y, px, py);
    if (bestGap < 0 || gap < bestGap) {
      best = d;
      bestGap = gap;
    }
  }
  return best;
}

/** Whether a Drone bay on this spot may park its drones d hundredths along the road */
export function canPark(spot, d) {
  if (d < 0 || d > ROAD_LENGTH) {
    return false;
  }
  const [sx, sy] = MAP.spots[spot];
  const [px, py] = pointAt(d);
  const reach = DRONE.reach * 100;
  return dist2(sx * 100, sy * 100, px, py) <= reach * reach;
}

/** Each spot's first parking point: the road point nearest it */
export const PARKS = MAP.spots.map(([x, y]) => nearestRoad(x * 100, y * 100));
