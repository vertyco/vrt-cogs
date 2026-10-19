// Feature 7, the Surprise Pixel: a hidden cube stands pale with a dark "?" on its top (the cube in
// `FeatureImage_SurprisePixel.png`); when it is revealed it flashes white into its own color while the "?" shrinks away.
// The original plays no sound for it. The "?" is the original's `art/ui/SurprisePixelQuestionMark.png` (white on clear),
// tinted dark; a cube that takes several hits shows its hits-left number there instead (looks/hard_pixels.js), so it
// stays pale without a "?". The hidden list comes from the simulation (sim/features/surprise_pixel.js) and never changes a rule: a
// hidden cube is still shot by its real color.
import * as THREE from "../vendor/three.module.min.js";
import { BLANK, COLORS, startHealth } from "../picture.js";
import { NUMBER } from "../sim/features/surprise_pixel.js";
import { L_PER_UNIT } from "../sim/numbers.js";
import { centerX, centerY } from "../sim/grid.js";

export { NUMBER };

const MARK = "art/ui/SurprisePixelQuestionMark.png";
const MARK_INK = 0x3b4484;
// The most Surprise Pixels one level lists is 412 (level 790)
const CAPACITY = 512;
// The "?" is this share of the cube's shorter side tall, and floats this far above its top
const MARK_SHARE = 0.68;
const LIFT = 0.03;
// The glyph's picture is 115 x 121
const MARK_ASPECT = 115 / 121;
// The reveal: a white flash fading into the cube's color over this many ticks; the "?" shrinks to nothing over them
const FLASH_TICKS = 10;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();
const tint = new THREE.Color();
const WHITE = new THREE.Color(0xffffff);

// The bounding cells of a target as [x0, y0, x1, y1]
function cellRange(width, target) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const cell of target.cells) {
    const x = cell % width;
    const y = Math.floor(cell / width);
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return [x0, y0, x1, y1];
}

// How far a reveal has come, 0 to 1, or -1 when none is running at this time
function flashOf(record, now) {
  const u = (now - record.flashAt) / FLASH_TICKS;
  return u >= 0 && u < 1 ? u : -1;
}

class SurprisePixelLook {
  constructor(mesh, picture) {
    this.mesh = mesh;
    this.picture = picture;
    // Per listed cube: where its "?" stands and how big, whether it has one, whether it is drawn hidden now, the
    // health its mark was drawn at, and the tick its reveal began (-Infinity for none)
    this.records = [];
    this.state = null;
    this.hiddenCount = -1;
    this.now = 0;
    this.dirty = false;
  }

  // A new level: every cube still hidden gets its pale color and its "?"
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    const cell = grid.size / L_PER_UNIT;
    for (const cubeId of mine.hidden.slice(0, CAPACITY)) {
      const target = grid.targets[cubeId];
      const [x0, y0, x1, y1] = cellRange(grid.width, target);
      this.records.push({
        target,
        x: (centerX(grid, x0) + centerX(grid, x1)) / 2 / L_PER_UNIT,
        z: -(centerY(grid, y0) + centerY(grid, y1)) / 2 / L_PER_UNIT,
        height: Math.min(x1 - x0 + 1, y1 - y0 + 1) * cell * MARK_SHARE,
        marked: startHealth(state, target) === 1,
        hidden: true,
        shownHealth: -1,
        flashAt: -Infinity,
      });
      this.picture.recolor(target, BLANK);
    }
    this.state = state;
    this.hiddenCount = mine.hidden.length;
    this.dirty = true;
  }

  clear() {
    this.records = [];
    this.state = null;
    this.hiddenCount = -1;
    this.mesh.count = 0;
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k !== "pixel_revealed") {
        continue;
      }
      const record = this.records.find((r) => r.target.id === event.cube);
      if (record) {
        record.flashAt = event.t;
      }
    }
  }

  // Bring every cube's color and "?" to the simulation's hidden list, then draw the marks
  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    const mine = state.features[NUMBER];
    if (!mine || !this.records.length) {
      return;
    }
    if (state !== this.state || mine.hidden.length !== this.hiddenCount) {
      this.sync(state, mine.hidden);
    }
    let moving = this.dirty;
    for (const record of this.records) {
      moving = this.paint(record) || moving;
    }
    if (moving) {
      this.write(state);
      this.dirty = false;
    }
  }

  // A cube's state differs from what is drawn: paint it pale, or in its color (a reveal's flash starts from its event)
  sync(state, hidden) {
    for (const record of this.records) {
      const nowHidden = hidden.includes(record.target.id);
      if (nowHidden !== record.hidden) {
        record.hidden = nowHidden;
        this.picture.recolor(record.target, nowHidden ? BLANK : COLORS[record.target.color]);
      }
    }
    this.state = state;
    this.hiddenCount = hidden.length;
    this.dirty = true;
  }

  // The flash on a revealed cube, and whether the mark needs drawing again (a flash running or a hit changed the
  // cube's height)
  paint(record) {
    const { target } = record;
    if (target.dead) {
      return record.shownHealth !== 0;
    }
    let again = record.shownHealth !== target.health;
    if (!record.hidden) {
      const u = flashOf(record, this.now);
      if (u >= 0) {
        this.picture.recolor(target, tint.copy(WHITE).lerp(COLORS[target.color], u));
        again = true;
      } else if (record.flashAt !== -Infinity) {
        this.picture.recolor(target, COLORS[target.color]);
        record.flashAt = -Infinity;
        again = true;
      }
    }
    return again;
  }

  // The "?" on every hidden cube's top, and on a cube just revealed while it shrinks
  write(state) {
    let count = 0;
    for (const record of this.records) {
      const { target } = record;
      record.shownHealth = target.dead ? 0 : target.health;
      if (target.dead || !record.marked) {
        continue;
      }
      let grow = 1;
      if (!record.hidden) {
        const u = flashOf(record, this.now);
        if (u < 0) {
          continue;
        }
        grow = 1 - u * u;
      }
      place.set(record.x, this.picture.topOf(target, state) + LIFT, record.z);
      size.set(record.height * MARK_ASPECT * grow, 1, record.height * grow);
      matrix.compose(place, turn.identity(), size);
      this.mesh.setMatrixAt(count++, matrix);
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}

// Load the "?" and make its mesh
export async function create(scene, picture) {
  const map = await new THREE.TextureLoader().loadAsync(MARK);
  map.colorSpace = THREE.SRGBColorSpace;
  map.anisotropy = 4;
  const material = new THREE.MeshBasicMaterial({
    map,
    color: MARK_INK,
    transparent: true,
    depthWrite: false,
    toneMapped: false,
  });
  const geometry = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const mesh = new THREE.InstancedMesh(geometry, material, CAPACITY);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  mesh.renderOrder = 3;
  mesh.count = 0;
  scene.add(mesh);
  return new SurprisePixelLook(mesh, picture);
}
