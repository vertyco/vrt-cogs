// Where the slots, the queues and the rescue row stand on the ground below the belt, and the boxes they take on screen.
// Spots are in world units, from board.json's anchors (the original's layout objects).
import * as THREE from "./vendor/three.module.min.js";
import { PICTURE_HEIGHT } from "./camera.js";
import { cubeSize } from "./space.js";

// The column shape board.json's anchors were laid out for
const REFERENCE_ASPECT = 450 / 720;
// A pig is about 0.86 wide, 0.8 deep and 1.03 tall at scale 1 (ASSETS.md); a slot is a 1 x 1 square on the ground
const PIG_SIZE = { w: 0.86, d: 0.8, h: 1.03 };
const SLOT_SIZE = 1;
// Slots and queue columns stand this far apart, by how many there are (the original's layout objects). From six
// slots on they pack closer and shrink
const COLUMN_STEP = 1.3;
const COLUMN_STEP_MANY = 1.22;
const MANY = 6;
const SLOT_SCALE_MANY = 0.92;
// The rescue row is one line of at most this many pigs. It starts at the board's first position and, when the pigs
// would pass RESCUE_RIGHT_EDGE (the belt's outer edge, at spread 1), closes up and shrinks to fit instead of wrapping
const RESCUE_ROW_COUNT = 24;
const RESCUE_RIGHT_EDGE = 3.2;
// The free-tray counter's text is this many font sizes wide on each side of its middle (style.css: the font is the
// larger of 15 px and 5% of the column's width). The first rescue pig stands this many pixels clear of it
const COUNTER_HALF_EM = 0.85;
const COUNTER_FONT_MIN = 15;
const COUNTER_FONT_SHARE = 0.05;
const COUNTER_GAP = 6;

export class Layout {
  constructor(board, rig, beltBox) {
    this.board = board;
    this.rig = rig;
    this.beltBox = beltBox;
    // Returns the y (pixels from the column's top) the queues must end above, or null when nothing covers them
    this.floor = () => null;
    this.rowsKey = "";
    this.rows = [];
  }

  // How many pigs of each queue fit above the floor: the original draws only the rows that fit. The answer is kept
  // until the camera, the floor or the number of queues changes
  queueRows(count) {
    const floor = this.floor();
    const key = `${this.rig.width}x${this.rig.height}:${this.rig.size}:${floor}:${count}`;
    if (key !== this.rowsKey) {
      this.rowsKey = key;
      this.rows = this.queueSpots(count).map((spot) => {
        if (floor === null) {
          return Infinity;
        }
        let rows = 1;
        while (rows < 60) {
          const box = this.pigBox(spot.x, spot.z + rows * spot.step, spot.scale);
          if (box.y + box.h > floor) {
            break;
          }
          rows += 1;
        }
        return rows;
      });
    }
    return this.rows;
  }

  // A wider column spreads the slots and queues across it and draws bigger pigs; a narrower one keeps the
  // original's spacing
  spread() {
    return Math.max(1, this.rig.aspect / REFERENCE_ASPECT);
  }

  // Board space has z up the screen, the world's z runs the other way
  boardZ(z) {
    return -z;
  }

  columnX(count, index) {
    return (index - (count - 1) / 2) * (count < MANY ? COLUMN_STEP : COLUMN_STEP_MANY) * this.spread();
  }

  slotSpots(count) {
    const { slots } = this.board.anchors;
    const size = SLOT_SIZE * slots.item_scale * (count < MANY ? 1 : SLOT_SCALE_MANY) * this.spread();
    const z = this.boardZ(slots.origin[2]);
    return Array.from({ length: count }, (_, i) => ({ x: this.columnX(count, i), z, size }));
  }

  // Each queue column's front pig, and the distance from one pig to the next one back (toward the viewer)
  queueSpots(count) {
    const { queues } = this.board.anchors;
    const scale = this.spread();
    const z = this.boardZ(queues.origin[2]) - queues.pigs.first * scale;
    const step = -queues.pigs.step * scale;
    return Array.from({ length: count }, (_, i) => ({ x: this.columnX(count, i), z, step, scale }));
  }

  // Pixels the camera draws one world unit wide along the rescue row's line on the ground
  pixelsPerUnit(z) {
    const a = this.rig.project(new THREE.Vector3(0, 0, z));
    const b = this.rig.project(new THREE.Vector3(1, 0, z));
    return b.x - a.x;
  }

  // The first rescue pig's x: the board's first position, moved right when the free-tray counter would cover it
  rescueStart(z, pigHalf) {
    const { rescue, free_tray_counter: counter } = this.board.anchors;
    const first = (rescue.origin[0] + rescue.positions[7][0]) * this.spread();
    const font = Math.max(COUNTER_FONT_MIN, this.rig.width * COUNTER_FONT_SHARE);
    const clear = (COUNTER_HALF_EM * font + COUNTER_GAP) / this.pixelsPerUnit(z);
    return Math.max(first, counter.position[0] + clear + pigHalf);
  }

  // The rescue row starts at the left (clear of the free-tray counter) and fills to the right in one line. `count` is
  // the most pigs it can hold (the belt's trays plus the slots); when they would pass the right edge the pigs stand
  // closer and smaller, so the row never wraps down onto the slots
  rescueSpots(count) {
    const { rescue } = this.board.anchors;
    const spread = this.spread();
    const z = this.boardZ(rescue.origin[2]);
    const first = this.rescueStart(z, (PIG_SIZE.w * rescue.item_scale * spread) / 2);
    const natural = rescue.step * spread;
    const fit = (RESCUE_RIGHT_EDGE * spread - first) / Math.max(1, count - 1);
    const step = Math.min(natural, fit);
    const scale = rescue.item_scale * spread * (step / natural);
    return Array.from({ length: RESCUE_ROW_COUNT }, (_, i) => ({ x: first + i * step, z, scale }));
  }

  // The box a pig standing at a world point takes on screen, from its feet to the top of its head
  pigBox(x, z, scale) {
    const w = (PIG_SIZE.w * scale) / 2;
    const d = (PIG_SIZE.d * scale) / 2;
    const points = [];
    for (const y of [0, PIG_SIZE.h * scale]) {
      for (const [sx, sz] of [
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ]) {
        points.push(new THREE.Vector3(x + sx * w, y, z + sz * d));
      }
    }
    return this.rig.boxAround(points);
  }

  groundBox(x, z, size) {
    const half = size / 2;
    return this.rig.boxAround(
      [
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ].map(([sx, sz]) => new THREE.Vector3(x + sx * half, 0, z + sz * half)),
    );
  }

  pictureBox(level) {
    const half = cubeSize(level) / 2;
    return this.rig.boxAround(
      [
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1],
      ].map(([sx, sz]) => new THREE.Vector3(sx * level.width * half, PICTURE_HEIGHT, sz * level.height * half)),
    );
  }

  beltBoxOnScreen() {
    const { min, max } = this.beltBox;
    return this.rig.boxAround([
      new THREE.Vector3(min.x, 0, min.z),
      new THREE.Vector3(max.x, 0, min.z),
      new THREE.Vector3(min.x, 0, max.z),
      new THREE.Vector3(max.x, 0, max.z),
    ]);
  }

  // The box of every queue pig a Hand pick can land on, queue by queue, front pig first: the rows the screen holds (the
  // others aren't drawn), never more than the level's pigs. Pixels from the column's top left corner, like screenBoxes
  pickBoxes() {
    const level = this.rig.level;
    if (!level) {
      return [];
    }
    const rows = this.queueRows(level.queues.length);
    return this.queueSpots(level.queues.length).map((spot, q) => {
      const count = Math.min(rows[q], level.queues[q].length);
      return Array.from({ length: count }, (_, k) => this.pigBox(spot.x, spot.z + k * spot.step, spot.scale));
    });
  }

  // Every place a tap can land that no page button covers, as boxes in pixels from the column's top left corner:
  // the belt, the picture, each slot, each queue column (its front pig, and the whole column down to the bottom of the
  // screen) and each rescue pig. Worked out from the camera, so ask again after a resize
  screenBoxes(rescueCount = 0) {
    const level = this.rig.level;
    const { width, height } = this.rig;
    const queues = this.queueSpots(level ? level.queues.length : 0).map((spot) => {
      const front = this.pigBox(spot.x, spot.z, spot.scale);
      return { front, column: { x: front.x, y: front.y, w: front.w, h: height - front.y } };
    });
    return {
      width,
      height,
      belt: this.beltBoxOnScreen(),
      picture: level ? this.pictureBox(level) : null,
      slots: this.slotSpots(level ? level.slotCount : 5).map((s) => this.groundBox(s.x, s.z, s.size)),
      queues,
      rescue: this.rescueSpots(rescueCount).map((s) => this.pigBox(s.x, s.z, s.scale)),
    };
  }
}
