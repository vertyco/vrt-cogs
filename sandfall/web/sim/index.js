// The simulation in one import. Nothing under sim/ touches the page, the clock or Math.random.
export { Dice, mix } from "./dice.js";
export { EL, ELEMENT_COUNT, ELEMENTS, TABS } from "./elements.js";
export {
  burnPlus,
  emit,
  fall,
  fallStraight,
  layer,
  near,
  paintCell,
  put,
  rise,
  sink,
  slideSideways,
  swap,
  touching,
} from "./helpers.js";
export { newSlug, packSlug, SLUG_BYTES, SLUG_POINTS, stepSlug, unpackSlug } from "./slug.js";
export { decodeWorld, encodeWorld, hashWorld, packWorld, unpackWorld } from "./snapshot.js";
export { starterWorld } from "./starter.js";
export { stepWorld } from "./step.js";
export { applyStroke, SHAPE, STROKE, strokeCells } from "./strokes.js";
export { cos256, isqrt, SIN, sin256 } from "./trig.js";
export { createWorld, H, HEAT_MAX, HEAT_MIN, N, ROOM, W } from "./world.js";
export {
  handStroke,
  packGrabs,
  packZombies,
  stepZombies,
  unpackGrabs,
  unpackZombies,
  ZOMBIE_POINTS,
} from "./zombies.js";
