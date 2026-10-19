"""The Dreamteck path Snakes and Dragons lie along, and the cells their bodies cover.

A snake is a nest square and a run of corner squares (2 x 2 or 3 x 3 cells). Its body is the cells swept by moving
each square straight to the next, grouped into cross-sections from the nest outward (SnakeFeature$$
UpdateObstacleGridPoints, RVA 0x57BAFEC). How much of the body is left at a given health comes from a point on the
drawn spline: SnakeFeature$$SyncSplinePoints (RVA 0x57B8570) lays control points through the square centers, with
extra points every straightLinePointDistance along long runs (AddInterpolatedPoints, RVA 0x57BACB8) and three points
around every corner, reversed so the spline runs tail to nest. The spline is a Dreamteck BSpline (type 1, sample rate
10) sampled evenly by distance (SampleMode Uniform: Spline$$EvaluateUniform RVA 0x5E0B558, Travel RVA 0x5E09A34,
CalculateLength RVA 0x5E0B8B8, ComputeCatPoints RVA 0x5E069F4, CalculateBSplinePosition RVA 0x5E07B78), and a
percent is read by blending the two nearest samples (SampleCollection$$EvaluatePosition, RVA 0x5DFDAA8). The cell
under that point names the cross-section (UpdateCurrentObstaclePointIndex, RVA 0x57BBD1C).

Everything here works in cells (one cube is 1.0 across; the original's units are the cube size, so every distance
setting is in cubes already: PixelGridController spacing is 0). The original works in float32; this port uses
doubles with add, subtract, multiply, divide and square root only, so web/sim/spline.js gives the very same numbers.
It can land one cell away from the original at rare points.
"""

from __future__ import annotations

import math

# The spline's control points and its distance settings, in cubes (SnakeFeature fields on resources.assets #11640)
STRAIGHT_DISTANCE = 3.0
SAMPLE_RATE = 10
# splinePointDistanceRange: a corner's run length is scaled between these two
CORNER_RUN = (0.5, 1.0)
# splineCornerOffsetScalingMinMax: how far before and after a corner its extra points sit
CORNER_OFFSET = (0.5, 2.0)
# A corner point never sits farther along a run than this share of it
CORNER_SHARE = 0.49
SAME_POINT = 1e-6
NO_LENGTH = 1e-5
STRAIGHT_DOT = 0.9999


def clamp01(value: float) -> float:
    if value > 1.0:
        return 1.0
    if value < 0.0:
        return 0.0
    return value


def round_even(value: float) -> int:
    """Round to the nearest whole number, halves to the even one (Math.Round in the world-to-grid lookup)."""
    low = math.floor(value)
    rest = value - low
    if rest > 0.5:
        return low + 1
    if rest == 0.5 and low % 2 != 0:
        return low + 1
    return low


def center(square: list[list[int]]) -> list[float]:
    """The middle of a square's cells (PixelGridController$$GridPointsToWorldPoint, RVA 0x54BF888)."""
    total_x = 0.0
    total_y = 0.0
    for x, y in square:
        total_x += x
        total_y += y
    return [total_x / len(square), total_y / len(square)]


def distance(a: list[float], b: list[float]) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def interpolate(out: list[list[float]], start: list[float], end: list[float], step: float) -> None:
    """Extra points on a long run: floor(length / step) of them, evenly between start and end."""
    count = math.floor(distance(start, end) / step)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    for k in range(1, count + 1):
        share = clamp01(k / (count + 1))
        out.append([start[0] + dx * share, start[1] + dy * share])


def corner_offset(length: float) -> float:
    share = 0.0
    if CORNER_RUN[0] != CORNER_RUN[1]:
        share = clamp01((length - CORNER_RUN[0]) / (CORNER_RUN[1] - CORNER_RUN[0]))
    offset = CORNER_OFFSET[0] + share * (CORNER_OFFSET[1] - CORNER_OFFSET[0])
    return min(offset, length * CORNER_SHARE)


def unit(dx: float, dy: float, length: float) -> list[float]:
    if length > NO_LENGTH:
        return [dx / length, dy / length]
    return [0.0, 0.0]


def round_corners(points: list[list[float]]) -> list[list[float]]:
    """Keep straight points; replace each corner by a point before it, the corner and a point after it."""
    out = [points[0]]
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1], points[i], points[i + 1]
        in_x, in_y = b[0] - a[0], b[1] - a[1]
        out_x, out_y = c[0] - b[0], c[1] - b[1]
        in_len = math.sqrt(in_x * in_x + in_y * in_y)
        out_len = math.sqrt(out_x * out_x + out_y * out_y)
        cross = in_x * out_y - in_y * out_x
        in_dir = unit(in_x, in_y, in_len)
        out_dir = unit(out_x, out_y, out_len)
        if cross * cross < SAME_POINT and in_dir[0] * out_dir[0] + in_dir[1] * out_dir[1] > STRAIGHT_DOT:
            out.append(b)
            continue
        before = corner_offset(in_len)
        after = corner_offset(out_len)
        out.append([b[0] - in_dir[0] * before, b[1] - in_dir[1] * before])
        out.append(b)
        out.append([b[0] + out_dir[0] * after, b[1] + out_dir[1] * after])
    out.append(points[-1])
    return out


def control_points(squares: list[list[list[int]]], straight_distance: float) -> list[list[float]]:
    """The spline's control points, tail first: centers, run points, near-duplicates dropped, corners rounded."""
    raw = [center(squares[0])]
    for square in squares[1:]:
        end = center(square)
        interpolate(raw, raw[-1], end, straight_distance)
        raw.append(end)
    kept: list[list[float]] = []
    for point in raw:
        if kept:
            dx = point[0] - kept[-1][0]
            dy = point[1] - kept[-1][1]
            if dx * dx + dy * dy <= SAME_POINT:
                continue
        kept.append(point)
    if len(kept) == 1:
        points = [kept[0], kept[0]]
    else:
        points = round_corners(kept)
    points.reverse()
    return points


def reflect(point: list[float], away: list[float]) -> list[float]:
    return [point[0] + (point[0] - away[0]), point[1] + (point[1] - away[1])]


def bspline_at(points: list[list[float]], percent: float) -> list[float]:
    """The uniform cubic B-spline at percent of the way, open ends mirrored (Spline$$EvaluatePosition)."""
    last = len(points) - 1
    spot = clamp01(percent) * last
    i = math.floor(spot)
    t = clamp01(spot - i)
    p1 = points[i]
    p0 = points[i - 1] if i >= 1 else reflect(points[0], points[1])
    if i + 1 <= last:
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 <= last else reflect(p2, p1)
    else:
        p2 = reflect(points[last], points[last - 1])
        p3 = reflect(p2, points[last])
    out = []
    for k in range(2):
        a, b, c, d = p0[k], p1[k], p2[k], p3[k]
        cubic = (b * 3.0 - a - c * 3.0 + d) * t / 6.0
        square = (a - (b + b) + c) * 0.5 + cubic
        line = (c - a) * 0.5 + square * t
        out.append((a + b * 4.0 + c) / 6.0 + line * t)
    return out


def sample_count(points: list[list[float]]) -> int:
    """Spline.iterations for an open BSpline: (sampleRate - 1) x (points - 1) + 1."""
    return (SAMPLE_RATE - 1) * (len(points) - 1) + 1


def calculate_length(points: list[list[float]], step: float) -> float:
    """The spline's length from 0 to 1, walked in steps of `step` (Spline$$CalculateLength)."""
    length = 0.0
    percent = 0.0
    here = bspline_at(points, percent)
    while percent != 1.0:
        percent = min(percent + step, 1.0)
        there = bspline_at(points, percent)
        length += distance(here, there)
        here = there
    return length


def travel(points: list[list[float]], count: int, start: float, length: float) -> float:
    """The percent `length` farther on from `start`, walking sample to sample (Spline$$Travel, forward)."""
    if start >= 1.0:
        return 1.0
    if length == 0.0:
        return clamp01(start)
    last = count - 1
    here = bspline_at(points, start)
    index = math.ceil(start * last)
    before = start
    moved = 0.0
    while True:
        percent = index / last
        there = bspline_at(points, percent)
        gap = distance(here, there)
        here = there
        moved += gap
        if moved >= length:
            break
        before = percent
        if index == last:
            break
        index += 1
    if before == percent:
        return percent
    return before + (percent - before) * clamp01(1.0 - (moved - length) / gap)


def uniform_samples(points: list[list[float]]) -> list[list[float]]:
    """Sample points evenly spaced by distance along the spline (Spline$$EvaluateUniform)."""
    count = sample_count(points)
    step = calculate_length(points, 1.0 / (count - 1)) / (count - 1)
    samples = [bspline_at(points, 0.0)]
    percent = 0.0
    for _ in range(1, count - 1):
        percent = travel(points, count, percent, step)
        samples.append(bspline_at(points, percent))
    samples.append(bspline_at(points, 1.0))
    return samples


def sweep(start: list[list[int]], end: list[list[int]]) -> list[list[list[int]]]:
    """The cells start's square passes moving straight to end's, as cross-sections ordered from start.

    The step is between the two squares' first points; a diagonal step sweeps nothing. Each cell of start steps
    along, cells listed once each; they are grouped by the coordinate along the move (in the order first seen) and
    the groups ordered from start toward end."""
    dx = end[0][0] - start[0][0]
    dy = end[0][1] - start[0][1]
    if (dx != 0 and dy != 0) or (dx == 0 and dy == 0):
        return []
    cells: list[list[int]] = []
    seen: set[tuple[int, int]] = set()
    steps = abs(dx) + abs(dy)
    step_x = (dx > 0) - (dx < 0)
    step_y = (dy > 0) - (dy < 0)
    for x, y in start:
        for k in range(steps + 1):
            cell = (x + step_x * k, y + step_y * k)
            if cell not in seen:
                seen.add(cell)
                cells.append([cell[0], cell[1]])
    along = 0 if dx != 0 else 1
    groups: dict[int, list[list[int]]] = {}
    for cell in cells:
        groups.setdefault(cell[along], []).append(cell)
    keys = sorted(groups, reverse=(dx < 0 or dy < 0))
    return [groups[key] for key in keys]


def body_sections(squares: list[list[list[int]]]) -> list[list[list[int]]]:
    """Every run's cross-sections in turn, nest first; a nest with no corners is one section."""
    if len(squares) == 1:
        return [[[x, y] for x, y in squares[0]]]
    sections = []
    for i in range(len(squares) - 1):
        sections.extend(sweep(squares[i], squares[i + 1]))
    return sections


def build(points: list[list[list[int]]], straight_distance: float) -> dict:
    """The path through squares (the nest, then each corner square, as lists of [x, y] cells).

    Holds the control points (tail first), the samples a percent is read from, the body's cross-sections in [x, y]
    cells (nest outward) and `lookup`, each cell's cross-section ("x,y" -> index; a cell in two sections keeps the
    later one)."""
    squares = [[[x, y] for x, y in square] for square in points]
    spline = control_points(squares, straight_distance)
    sections = body_sections(squares)
    lookup = {}
    for index, section in enumerate(sections):
        for x, y in section:
            lookup[f"{x},{y}"] = index
    return {"spline": spline, "samples": uniform_samples(spline), "sections": sections, "lookup": lookup}


def cross_sections(path: dict, area: tuple[int, int]) -> list[list[int]]:
    """The body's cross-sections, nest outward, as cell indices on a picture `area` = (width, height) wide."""
    width, height = area
    return [[y * width + x for x, y in section if 0 <= x < width and 0 <= y < height] for section in path["sections"]]


def position_at(path: dict, t: float) -> list[float]:
    """The point t of the way along the drawn spline (0 the tail, 1 the nest), blending the two nearest samples."""
    samples = path["samples"]
    spot = t * (len(samples) - 1)
    i = math.floor(spot)
    share = spot - i
    if share <= 0.0:
        return samples[i]
    share = clamp01(share)
    a, b = samples[i], samples[i + 1]
    return [a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share]


def index_at(path: dict, t: float) -> int:
    """The last cross-section the body keeps when the spline point t of the way along lands: the section of the
    cell under it plus one, at most the last. -1 when that cell is in no section (the body then stays as it was)."""
    x, y = position_at(path, t)
    key = f"{round_even(x)},{round_even(y)}"
    if key not in path["lookup"]:
        return -1
    return min(path["lookup"][key] + 1, len(path["sections"]) - 1)
