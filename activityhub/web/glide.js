// How the Orb ring glides under a finger on a touch screen, like an iPhone picker wheel: it follows the finger,
// stretches a little past either end, keeps spinning after a flick, and comes to rest with a whole game in the
// middle. Places are in games: 0 puts the first game in the middle, 1.5 is halfway from the second to the third.

// How hard the ring resists a pull past its ends: the stretch grows ever slower and never reaches a whole game
const STRETCH = 0.55;
// The finger's speed counts over its last moments only, and a finger that rested this long before letting go
// flicked nothing
const SPEED_WINDOW_MS = 100;
const RESTED_MS = 80;
// How far a flick carries for each unit of speed: an iPhone list's ordinary slowdown, which loses 0.2% of its speed
// every millisecond
const COAST_MS = 500;
// The shortest and longest a glide to rest takes
const GLIDE_MIN_MS = 180;
const GLIDE_MAX_MS = 1400;

const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

// Past either end the ring moves less and less than the finger, up to almost one game
export function stretch(place, last) {
  const end = clamp(place, 0, last);
  const over = place - end;
  return end + Math.sign(over) * (1 - 1 / (1 + Math.abs(over) * STRETCH));
}

// The finger's speed in games per millisecond from its moves, each [time, place], or 0 when it had stopped
export function speed(moves, now) {
  const recent = moves.filter(([time]) => now - time <= SPEED_WINDOW_MS);
  if (recent.length < 2 || now - recent[recent.length - 1][0] > RESTED_MS) {
    return 0;
  }
  const [[start, from], [end, to]] = [recent[0], recent[recent.length - 1]];
  return end > start ? (to - from) / (end - start) : 0;
}

// The whole game a let-go ring comes to rest on: where the flick would carry it, or the nearest when it was too slow
// to count as a flick
export function restingPlace(place, velocity, last, slowest) {
  const carried = Math.abs(velocity) >= slowest ? place + velocity * COAST_MS : place;
  return clamp(Math.round(carried), 0, last);
}

// A glide from one place to another, as the place at each moment, easing to a stop in a set time. A flick's glide
// starts at about the finger's speed (exactly, unless its time is cut to fit the shortest or longest glide); a ring
// let go slowly, or past an end, eases back the short way
export function glide(from, to, velocity) {
  const distance = to - from;
  const along = velocity && Math.sign(velocity) === Math.sign(distance);
  // An ease-out curve starts at three times its average speed, so this duration starts it at the finger's
  const duration = along
    ? clamp((3 * Math.abs(distance)) / Math.abs(velocity), GLIDE_MIN_MS, GLIDE_MAX_MS)
    : clamp(200 + 150 * Math.abs(distance), GLIDE_MIN_MS, 450);
  return {
    duration,
    at: (time) => from + distance * (1 - (1 - clamp(time / duration, 0, 1)) ** 3),
  };
}
