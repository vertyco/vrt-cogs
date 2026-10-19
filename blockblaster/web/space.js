// Moving between the original's numbers and the page's world.
// The world is picture space (origin at the picture's center, x to the right, y up the screen) laid flat: world x is
// picture x, world y is height above the ground, world z is minus picture y. board.json keeps the original's
// left-handed Unity numbers (z up the screen), so z and the rotations are flipped on the way in.
import * as THREE from "./vendor/three.module.min.js";
import { L_PER_UNIT } from "./sim/numbers.js";

export function flipPosition(p) {
  return new THREE.Vector3(p[0], p[1], -p[2]);
}

export function flipRotation(q) {
  return new THREE.Quaternion(-q[0], -q[1], q[2], q[3]);
}

// A picture-space point in L (and a height in units) as a world point
export function worldFromPicture(x, y, height = 0) {
  return new THREE.Vector3(x / L_PER_UNIT, height, -y / L_PER_UNIT);
}

// A cube's side in units: `s` of the simulation's rules, a whole number of L, over the grid's longer side
export function cubeSize(level) {
  return Math.floor(level.pw / Math.max(level.width, level.height)) / L_PER_UNIT;
}
