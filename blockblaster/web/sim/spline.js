// The Dreamteck path Snakes and Dragons lie along, and the cells their bodies cover.
//
// A snake is a nest square and a run of corner squares (2 x 2 or 3 x 3 cells). Its body is the cells swept by moving
// each square straight to the next, grouped into cross-sections from the nest outward (SnakeFeature$$
// UpdateObstacleGridPoints, RVA 0x57BAFEC). How much of the body is left at a given health comes from a point on the
// drawn spline: SnakeFeature$$SyncSplinePoints (RVA 0x57B8570) lays control points through the square centers, with
// extra points every straightLinePointDistance along long runs (AddInterpolatedPoints, RVA 0x57BACB8) and three
// points around every corner, reversed so the spline runs tail to nest. The spline is a Dreamteck BSpline (type 1,
// sample rate 10) sampled evenly by distance (SampleMode Uniform: Spline$$EvaluateUniform RVA 0x5E0B558, Travel RVA
// 0x5E09A34, CalculateLength RVA 0x5E0B8B8, ComputeCatPoints RVA 0x5E069F4, CalculateBSplinePosition RVA
// 0x5E07B78), and a percent is read by blending the two nearest samples (SampleCollection$$EvaluatePosition, RVA
// 0x5DFDAA8). The cell under that point names the cross-section (UpdateCurrentObstaclePointIndex, RVA 0x57BBD1C).
//
// Everything here works in cells (one cube is 1.0 across; the original's units are the cube size, so every distance
// setting is in cubes already: PixelGridController spacing is 0). The original works in float32; this port uses
// doubles with add, subtract, multiply, divide and square root only, so common/sim/spline.py gives the very same
// numbers. It can land one cell away from the original at rare points.

// The spline's control points and its distance settings, in cubes (SnakeFeature fields on resources.assets #11640)
export const STRAIGHT_DISTANCE = 3.0;
export const SAMPLE_RATE = 10;
// splinePointDistanceRange: a corner's run length is scaled between these two
const CORNER_RUN = [0.5, 1.0];
// splineCornerOffsetScalingMinMax: how far before and after a corner its extra points sit
const CORNER_OFFSET = [0.5, 2.0];
// A corner point never sits farther along a run than this share of it
const CORNER_SHARE = 0.49;
const SAME_POINT = 1e-6;
const NO_LENGTH = 1e-5;
const STRAIGHT_DOT = 0.9999;

export function clamp01(value) {
  if (value > 1.0) {
    return 1.0;
  }
  if (value < 0.0) {
    return 0.0;
  }
  return value;
}

// Round to the nearest whole number, halves to the even one (Math.Round in the world-to-grid lookup)
export function roundEven(value) {
  const low = Math.floor(value);
  const rest = value - low;
  if (rest > 0.5) {
    return low + 1;
  }
  if (rest === 0.5 && low % 2 !== 0) {
    return low + 1;
  }
  return low;
}

// The middle of a square's cells (PixelGridController$$GridPointsToWorldPoint, RVA 0x54BF888)
export function center(square) {
  let totalX = 0.0;
  let totalY = 0.0;
  for (const [x, y] of square) {
    totalX += x;
    totalY += y;
  }
  return [totalX / square.length, totalY / square.length];
}

export function distance(a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  return Math.sqrt(dx * dx + dy * dy);
}

// Extra points on a long run: floor(length / step) of them, evenly between start and end
export function interpolate(out, start, end, step) {
  const count = Math.floor(distance(start, end) / step);
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  for (let k = 1; k <= count; k++) {
    const share = clamp01(k / (count + 1));
    out.push([start[0] + dx * share, start[1] + dy * share]);
  }
}

export function cornerOffset(length) {
  let share = 0.0;
  if (CORNER_RUN[0] !== CORNER_RUN[1]) {
    share = clamp01((length - CORNER_RUN[0]) / (CORNER_RUN[1] - CORNER_RUN[0]));
  }
  const offset = CORNER_OFFSET[0] + share * (CORNER_OFFSET[1] - CORNER_OFFSET[0]);
  return Math.min(offset, length * CORNER_SHARE);
}

export function unit(dx, dy, length) {
  if (length > NO_LENGTH) {
    return [dx / length, dy / length];
  }
  return [0.0, 0.0];
}

// Keep straight points; replace each corner by a point before it, the corner and a point after it
export function roundCorners(points) {
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const [a, b, c] = [points[i - 1], points[i], points[i + 1]];
    const [inX, inY] = [b[0] - a[0], b[1] - a[1]];
    const [outX, outY] = [c[0] - b[0], c[1] - b[1]];
    const inLen = Math.sqrt(inX * inX + inY * inY);
    const outLen = Math.sqrt(outX * outX + outY * outY);
    const cross = inX * outY - inY * outX;
    const inDir = unit(inX, inY, inLen);
    const outDir = unit(outX, outY, outLen);
    if (cross * cross < SAME_POINT && inDir[0] * outDir[0] + inDir[1] * outDir[1] > STRAIGHT_DOT) {
      out.push(b);
      continue;
    }
    const before = cornerOffset(inLen);
    const after = cornerOffset(outLen);
    out.push([b[0] - inDir[0] * before, b[1] - inDir[1] * before]);
    out.push(b);
    out.push([b[0] + outDir[0] * after, b[1] + outDir[1] * after]);
  }
  out.push(points[points.length - 1]);
  return out;
}

// The spline's control points, tail first: centers, run points, near-duplicates dropped, corners rounded
export function controlPoints(squares, straightDistance) {
  const raw = [center(squares[0])];
  for (const square of squares.slice(1)) {
    const end = center(square);
    interpolate(raw, raw[raw.length - 1], end, straightDistance);
    raw.push(end);
  }
  const kept = [];
  for (const point of raw) {
    if (kept.length) {
      const dx = point[0] - kept[kept.length - 1][0];
      const dy = point[1] - kept[kept.length - 1][1];
      if (dx * dx + dy * dy <= SAME_POINT) {
        continue;
      }
    }
    kept.push(point);
  }
  const points = kept.length === 1 ? [kept[0], kept[0]] : roundCorners(kept);
  points.reverse();
  return points;
}

export function reflect(point, away) {
  return [point[0] + (point[0] - away[0]), point[1] + (point[1] - away[1])];
}

// The uniform cubic B-spline at percent of the way, open ends mirrored (Spline$$EvaluatePosition)
export function bsplineAt(points, percent) {
  const last = points.length - 1;
  const spot = clamp01(percent) * last;
  const i = Math.floor(spot);
  const t = clamp01(spot - i);
  const p1 = points[i];
  const p0 = i >= 1 ? points[i - 1] : reflect(points[0], points[1]);
  let p2;
  let p3;
  if (i + 1 <= last) {
    p2 = points[i + 1];
    p3 = i + 2 <= last ? points[i + 2] : reflect(p2, p1);
  } else {
    p2 = reflect(points[last], points[last - 1]);
    p3 = reflect(p2, points[last]);
  }
  const out = [];
  for (let k = 0; k < 2; k++) {
    const [a, b, c, d] = [p0[k], p1[k], p2[k], p3[k]];
    const cubic = ((b * 3.0 - a - c * 3.0 + d) * t) / 6.0;
    const square = (a - (b + b) + c) * 0.5 + cubic;
    const line = (c - a) * 0.5 + square * t;
    out.push((a + b * 4.0 + c) / 6.0 + line * t);
  }
  return out;
}

// Spline.iterations for an open BSpline: (sampleRate - 1) x (points - 1) + 1
export function sampleCount(points) {
  return (SAMPLE_RATE - 1) * (points.length - 1) + 1;
}

// The spline's length from 0 to 1, walked in steps of `step` (Spline$$CalculateLength)
export function calculateLength(points, step) {
  let length = 0.0;
  let percent = 0.0;
  let here = bsplineAt(points, percent);
  while (percent !== 1.0) {
    percent = Math.min(percent + step, 1.0);
    const there = bsplineAt(points, percent);
    length += distance(here, there);
    here = there;
  }
  return length;
}

// The percent `length` farther on from `start`, walking sample to sample (Spline$$Travel, forward)
export function travel(points, count, start, length) {
  if (start >= 1.0) {
    return 1.0;
  }
  if (length === 0.0) {
    return clamp01(start);
  }
  const last = count - 1;
  let here = bsplineAt(points, start);
  let index = Math.ceil(start * last);
  let before = start;
  let moved = 0.0;
  let percent;
  let gap;
  while (true) {
    percent = index / last;
    const there = bsplineAt(points, percent);
    gap = distance(here, there);
    here = there;
    moved += gap;
    if (moved >= length) {
      break;
    }
    before = percent;
    if (index === last) {
      break;
    }
    index += 1;
  }
  if (before === percent) {
    return percent;
  }
  return before + (percent - before) * clamp01(1.0 - (moved - length) / gap);
}

// Sample points evenly spaced by distance along the spline (Spline$$EvaluateUniform)
export function uniformSamples(points) {
  const count = sampleCount(points);
  const step = calculateLength(points, 1.0 / (count - 1)) / (count - 1);
  const samples = [bsplineAt(points, 0.0)];
  let percent = 0.0;
  for (let i = 1; i < count - 1; i++) {
    percent = travel(points, count, percent, step);
    samples.push(bsplineAt(points, percent));
  }
  samples.push(bsplineAt(points, 1.0));
  return samples;
}

// The cells start's square passes moving straight to end's, as cross-sections ordered from start.
// The step is between the two squares' first points; a diagonal step sweeps nothing. Each cell of start steps along,
// cells listed once each; they are grouped by the coordinate along the move (in the order first seen) and the groups
// ordered from start toward end.
export function sweep(start, end) {
  const dx = end[0][0] - start[0][0];
  const dy = end[0][1] - start[0][1];
  if ((dx !== 0 && dy !== 0) || (dx === 0 && dy === 0)) {
    return [];
  }
  const cells = [];
  const seen = new Set();
  const steps = Math.abs(dx) + Math.abs(dy);
  const stepX = Math.sign(dx);
  const stepY = Math.sign(dy);
  for (const [x, y] of start) {
    for (let k = 0; k <= steps; k++) {
      const cell = [x + stepX * k, y + stepY * k];
      const key = `${cell[0]},${cell[1]}`;
      if (!seen.has(key)) {
        seen.add(key);
        cells.push(cell);
      }
    }
  }
  const along = dx !== 0 ? 0 : 1;
  const groups = new Map();
  for (const cell of cells) {
    if (!groups.has(cell[along])) {
      groups.set(cell[along], []);
    }
    groups.get(cell[along]).push(cell);
  }
  const keys = [...groups.keys()].sort((p, q) => p - q);
  if (dx < 0 || dy < 0) {
    keys.reverse();
  }
  return keys.map((key) => groups.get(key));
}

// Every run's cross-sections in turn, nest first; a nest with no corners is one section
export function bodySections(squares) {
  if (squares.length === 1) {
    return [squares[0].map(([x, y]) => [x, y])];
  }
  const sections = [];
  for (let i = 0; i < squares.length - 1; i++) {
    sections.push(...sweep(squares[i], squares[i + 1]));
  }
  return sections;
}

// The path through squares (the nest, then each corner square, as lists of [x, y] cells).
// Holds the control points (tail first), the samples a percent is read from, the body's cross-sections in [x, y]
// cells (nest outward) and `lookup`, each cell's cross-section ("x,y" -> index; a cell in two sections keeps the
// later one).
export function build(points, straightDistance) {
  const squares = points.map((square) => square.map(([x, y]) => [x, y]));
  const spline = controlPoints(squares, straightDistance);
  const sections = bodySections(squares);
  const lookup = {};
  sections.forEach((section, index) => {
    for (const [x, y] of section) {
      lookup[`${x},${y}`] = index;
    }
  });
  return { spline, samples: uniformSamples(spline), sections, lookup };
}

// The body's cross-sections, nest outward, as cell indices on a picture `area` = [width, height] wide
export function crossSections(path, area) {
  const [width, height] = area;
  return path.sections.map((section) =>
    section.filter(([x, y]) => x >= 0 && x < width && y >= 0 && y < height).map(([x, y]) => y * width + x),
  );
}

// The point t of the way along the drawn spline (0 the tail, 1 the nest), blending the two nearest samples
export function positionAt(path, t) {
  const samples = path.samples;
  const spot = t * (samples.length - 1);
  const i = Math.floor(spot);
  let share = spot - i;
  if (share <= 0.0) {
    return samples[i];
  }
  share = clamp01(share);
  const [a, b] = [samples[i], samples[i + 1]];
  return [a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share];
}

// The last cross-section the body keeps when the spline point t of the way along lands: the section of the cell
// under it plus one, at most the last. -1 when that cell is in no section (the body then stays as it was).
export function indexAt(path, t) {
  const [x, y] = positionAt(path, t);
  const key = `${roundEven(x)},${roundEven(y)}`;
  if (!(key in path.lookup)) {
    return -1;
  }
  return Math.min(path.lookup[key] + 1, path.sections.length - 1);
}
