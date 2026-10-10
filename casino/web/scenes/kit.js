// What every table scene shares: animation helpers, and fitting a scene drawn at a fixed size into the space it gets.
// The art kit (cards, chips, dice, coins) lives in scenes/art.js; this file stays the generic helpers.
import { Container } from "../vendor/pixi.min.mjs";

export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export const ease = {
  linear: (t) => t,
  out: (t) => 1 - (1 - t) ** 3,
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  back: (t) => 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
};

// Moves an object's numeric properties (x, y, alpha, rotation, or scale.x through "scale") to new values over ms.
// Resolves when done. A destroyed object stops the tween at once
export function tween(target, to, ms, curve = ease.out) {
  const from = {};
  for (const key of Object.keys(to)) {
    from[key] = key === "scale" ? target.scale.x : target[key];
  }
  const start = performance.now();
  return new Promise((resolve) => {
    const step = (now) => {
      if (target.destroyed) {
        resolve();
        return;
      }
      const t = Math.min(1, (now - start) / ms);
      const k = curve(t);
      for (const [key, end] of Object.entries(to)) {
        const value = from[key] + (end - from[key]) * k;
        if (key === "scale") {
          target.scale.set(value);
        } else {
          target[key] = value;
        }
      }
      if (t < 1) {
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    };
    requestAnimationFrame(step);
  });
}

// A scene drawn at width x height, scaled to fit inside the space it gets and centered there
export function fitted(width, height) {
  const root = new Container();
  root.design = { width, height };
  return root;
}

export function fit(root, spaceWidth, spaceHeight) {
  const { width, height } = root.design;
  const scale = Math.min(spaceWidth / width, spaceHeight / height);
  root.scale.set(scale);
  root.position.set((spaceWidth - width * scale) / 2, (spaceHeight - height * scale) / 2);
}
