// The camera: the original's orthographic, tilted view, refitted to the shape of the play column and to each level's
// picture, and the projections the page's elements over the canvas need.
//
// The original draws the board without perspective and shows the same height at every screen shape (board.json,
// `camera`). So a narrower column sees less of the sides and a wider one sees more, and the vertical layout (belt in
// the top 9% to 61%, slots near 71%) never changes.
import * as THREE from "./vendor/three.module.min.js";
import { cubeSize, flipPosition, flipRotation } from "./space.js";

// The belt and its starter machine never get closer to the column's sides than this share of the half width, so a
// narrow phone zooms the board out until both are fully on screen
const REACH_SIDE_LIMIT = 0.95;
// Space a big picture keeps from the column's sides
const PICTURE_SIDE_LIMIT = 0.97;
// Cube tops, for projecting the picture's corners
export const PICTURE_HEIGHT = 0.3;
// How far back the camera stands. With no perspective it only has to keep the whole board between near and far
const STAND_BACK = 40;
const FAR = 120;

export class CameraRig {
  constructor(board, beltBox, reachBox) {
    this.beltBox = beltBox;
    // The belt with the starter machine beside it, which sticks out past the belt's left side
    this.reach = Math.max(-reachBox.min.x, reachBox.max.x);
    this.baseSize = board.camera.size;
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, FAR);
    this.rotation = flipRotation(board.camera.rotation);
    this.forward = new THREE.Vector3(0, 0, -1).applyQuaternion(this.rotation);
    this.up = new THREE.Vector3(0, 1, 0).applyQuaternion(this.rotation);
    // The two marks the measured frames fix: the middle of the belt's far edge and the middle of the slot row. Each
    // sits at the same share of the screen height whatever the picture, so a big picture only zooms the view out
    this.beltTop = this.upward(new THREE.Vector3(0, beltBox.max.y, beltBox.min.z));
    this.slotRow = this.upward(flipPosition([0, 0, board.anchors.slots.origin[2]]));
    const middle = this.upward(flipPosition(board.camera.target));
    this.topShare = (this.beltTop - middle) / this.baseSize;
    this.slotShare = (this.slotRow - middle) / this.baseSize;
    this.width = 1;
    this.height = 1;
    this.aspect = 1;
    this.level = null;
    this.size = this.baseSize;
    this.top = this.beltTop;
    this.place();
  }

  // How far up the screen a world point is, in units
  upward(point) {
    return point.dot(this.up);
  }

  pictureCorners(level) {
    const half = cubeSize(level) / 2;
    return [
      [-1, -1],
      [1, -1],
      [-1, 1],
      [1, 1],
    ].map(([sx, sz]) => new THREE.Vector3(sx * level.width * half, PICTURE_HEIGHT, sz * level.height * half));
  }

  // Half the height the view shows, and the highest thing on screen (it sits at the top mark)
  fitSize(level) {
    let size = Math.max(this.baseSize, this.reach / (REACH_SIDE_LIMIT * this.aspect));
    let top = this.beltTop;
    if (level) {
      const corners = this.pictureCorners(level);
      top = Math.max(top, ...corners.map((c) => this.upward(c)));
      const widest = Math.max(...corners.map((c) => Math.abs(c.x)));
      const tall = (top - this.slotRow) / (this.topShare - this.slotShare);
      size = Math.max(size, widest / (PICTURE_SIDE_LIMIT * this.aspect), tall);
    }
    return { size, top };
  }

  place() {
    const { camera, size, aspect } = this;
    camera.left = -size * aspect;
    camera.right = size * aspect;
    camera.top = size;
    camera.bottom = -size;
    const middle = this.top - this.topShare * size;
    camera.position.copy(this.forward).multiplyScalar(-STAND_BACK).addScaledVector(this.up, middle);
    camera.quaternion.copy(this.rotation);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld(true);
  }

  // Frame this level's picture together with the belt and the slot row: the view zooms out until all of it is on
  // screen (the camera never moves while the level plays). No level frames the belt alone
  fit(level) {
    this.level = level;
    Object.assign(this, this.fitSize(level));
    this.place();
  }

  // The column's size in CSS pixels
  resize(width, height) {
    this.width = width;
    this.height = height;
    this.aspect = width / height;
    this.fit(this.level);
  }

  // A world point as pixels from the column's top left corner
  project(point) {
    const p = point.clone().project(this.camera);
    return { x: ((p.x + 1) / 2) * this.width, y: ((1 - p.y) / 2) * this.height };
  }

  // The smallest box in pixels that holds all of these world points
  boxAround(points) {
    const flat = points.map((p) => this.project(p));
    const x = Math.min(...flat.map((p) => p.x));
    const y = Math.min(...flat.map((p) => p.y));
    return { x, y, w: Math.max(...flat.map((p) => p.x)) - x, h: Math.max(...flat.map((p) => p.y)) - y };
  }
}
