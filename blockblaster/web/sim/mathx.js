// Whole-number math both simulations share. common/sim/mathx.py gives the same answers.

// Floor division for b > 0. The float quotient can land one off for big numbers, so it is corrected exactly
export function idiv(a, b) {
  let q = Math.floor(a / b);
  if (q * b > a) {
    q -= 1;
  } else if ((q + 1) * b <= a) {
    q += 1;
  }
  return q;
}

// Exact integer square root of n >= 0
export function isqrt(n) {
  let r = Math.floor(Math.sqrt(n));
  while (r * r > n) {
    r -= 1;
  }
  while ((r + 1) * (r + 1) <= n) {
    r += 1;
  }
  return r;
}

export function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

// Round to the nearest float32, as the original's float math does
export function f32(x) {
  return Math.fround(x);
}

export function secondsToTicks(seconds) {
  return Math.floor(seconds * 60 + 0.5);
}
