// Whole-number helpers. The rules divide and take square roots only through these, so every browser and the bot's
// check round the same way.

/** a divided by b, rounded down (toward minus infinity) */
export function div(a, b) {
  return Math.floor(a / b);
}

/** The whole-number square root of n, rounded down */
export function isqrt(n) {
  if (n <= 0) {
    return 0;
  }
  let x = n;
  let y = Math.trunc((x + 1) / 2);
  while (y < x) {
    x = y;
    y = Math.trunc((x + Math.trunc(n / x)) / 2);
  }
  return x;
}

/** The squared distance between two points */
export function dist2(ax, ay, bx, by) {
  const dx = ax - bx;
  const dy = ay - by;
  return dx * dx + dy * dy;
}
