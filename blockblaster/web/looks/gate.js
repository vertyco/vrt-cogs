// Feature 5, the Gate: a cat-eared head of the gate's color stands on its cells, a white ring on the side the bar
// leaves from, a checkered strip runs out from it and a rounded end cap closes the strip. Every hit that shortens the
// bar pulls the far end back toward the head over 0.3 s (the strip is only ever as long as the simulation's bar; the
// pull-back is a look). At no health the strip is gone and the head shrinks away.
// The head, ring and end cap are the original's `models/features/gate_feature.glb` (ASSETS.md); the strip is built
// here from boxes, because the original draws it with a spline mesh. Everything comes from the simulation's gate
// records (sim/features/gate.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { COLORS } from "../picture.js";
import { NUMBER } from "../sim/features/gate.js";
import { L_PER_UNIT } from "../sim/numbers.js";
import { play as sound } from "../sound.js";

export { NUMBER };

const MODEL = "models/features/gate_feature.glb";
// The most gates one level holds is 14; the strips' checks of every gate in a level fit this many boxes
const GATES = 16;
const CHECKS = 4096;

// The pull-back of the bar's far end after a hit (0.3 s), and the head's shrinking once the bar is gone
const PULL_TICKS = 18;
const POP_TICKS = 14;
// The strip's width as a share of the head's side, its height as a share of the end cap's, and how much darker the
// second check of the checkerboard is
const STRIP_WIDTH = 0.62;
const STRIP_HEIGHT = 0.62;
const DARK = 0.8;

// The way each of FacingDirection's four values points on the picture (x right, y up the screen)
const DIRECTIONS = [
  [-1, 0],
  [0, 1],
  [1, 0],
  [0, -1],
];

const WHITE = new THREE.Color(0xffffff);
const UP = new THREE.Vector3(0, 1, 0);
const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const turn = new THREE.Quaternion();
const shade = new THREE.Color();
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

function easeOut(u) {
  return 1 - (1 - u) * (1 - u);
}

// The prefab's three meshes with their node transforms baked in, found by name
function pieces(gltf) {
  gltf.scene.updateMatrixWorld(true);
  const found = {};
  gltf.scene.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    const geometry = node.geometry.clone().applyMatrix4(node.matrixWorld);
    geometry.computeBoundingBox();
    const key = node.name.includes("Front") ? "ring" : node.name.includes("Cap") ? "cap" : "head";
    found[key] = geometry;
  });
  return found;
}

class GateLook {
  constructor(geometry, scene) {
    this.geometry = geometry;
    this.now = 0;
    this.gates = [];
    this.dirty = false;
    // Where the strip starts: the head's front face, so the head and ring are moved to put it at x = 0
    const front = geometry.head.boundingBox.max.x;
    geometry.head.translate(-front, 0, 0);
    geometry.ring.translate(-front, 0, 0);
    geometry.cap.computeBoundingBox();
    const cap = geometry.cap.boundingBox;
    this.capBack = cap.min.x - front;
    this.capMiddle = (cap.min.y + cap.max.y) / 2;
    this.capHeight = cap.max.y - cap.min.y;
    geometry.cap.translate(-front, 0, 0);
    this.ringMaterial = new THREE.MeshStandardMaterial({ color: WHITE, roughness: 0.45 });
    this.parts = [];
    for (let i = 0; i < GATES; i++) {
      const tint = new THREE.MeshStandardMaterial({ roughness: 0.4 });
      const head = new THREE.Mesh(geometry.head, tint);
      const ring = new THREE.Mesh(geometry.ring, this.ringMaterial);
      const cap = new THREE.Mesh(geometry.cap, tint);
      for (const mesh of [head, ring, cap]) {
        mesh.visible = false;
        scene.add(mesh);
      }
      this.parts.push({ head, ring, cap, tint });
    }
    this.checks = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ roughness: 0.5 }),
      CHECKS,
    );
    this.checks.count = 0;
    this.checks.frustumCulled = false;
    this.checks.setColorAt(0, WHITE);
    scene.add(this.checks);
  }

  // A new level: every gate laid out and drawn at its simulation's bar
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    const cell = grid.size / L_PER_UNIT;
    let used = 0;
    mine.gates.slice(0, GATES).forEach((gate, index) => {
      const record = this.layout(grid, cell, gate, index, used);
      used += record.reach * record.lanes;
      this.gates.push(record);
      this.paint(record, state);
    });
    this.checks.count = used;
    this.checks.instanceColor.needsUpdate = true;
    this.dirty = true;
    this.now = state.tick;
  }

  // One gate's fixed numbers: where its root stands (the middle of the head's front face), which way it points, how
  // wide its lanes are, and which boxes of the strip's pool are its own
  layout(grid, cell, gate, index, first) {
    const [dx, dy] = DIRECTIONS[gate.direction];
    const yaw = Math.atan2(dy, dx);
    const lanes = gate.points.length;
    // A cell's center in world units (the cells are numbered from the picture's lower left, y up the screen)
    const worldX = (x) => (x - (grid.width - 1) / 2) * cell;
    const worldZ = (y) => -(y - (grid.height - 1) / 2) * cell;
    const midX = gate.points.reduce((sum, point) => sum + point[0], 0) / lanes;
    const midY = gate.points.reduce((sum, point) => sum + point[1], 0) / lanes;
    const drawable = gate.layers.filter((layer) => layer.length).length;
    const pitch = STRIP_WIDTH * cell;
    const record = {
      gate,
      index,
      first,
      cell,
      lanes,
      drawable,
      pitch,
      reach: Math.ceil((drawable * cell) / pitch) + 1,
      // The model is made for a head two cells wide
      scale: (cell * lanes) / 2,
      yaw,
      // Each lane's place across the strip, in the gate's own frame
      lane: gate.points.map(
        (point) =>
          (worldX(point[0]) - worldX(midX)) * Math.sin(yaw) + (worldZ(point[1]) - worldZ(midY)) * Math.cos(yaw),
      ),
      shown: gate.bar,
      from: gate.bar,
      to: gate.bar,
      t0: -Infinity,
      diedAt: -1,
    };
    record.front = new THREE.Vector3(worldX(midX) + (dx * cell) / 2, 0, worldZ(midY) - (dy * cell) / 2);
    record.root = new THREE.Matrix4().compose(record.front, turn.setFromAxisAngle(UP, yaw), size.set(1, 1, 1));
    return record;
  }

  // The head, ring and cap in the gate's color; the strip's boxes in two shades
  paint(record, state) {
    const part = this.parts[record.index];
    const color = COLORS[state.grid.targets[record.gate.target].color];
    part.tint.color.copy(color);
    for (let i = 0; i < record.reach; i++) {
      for (let lane = 0; lane < record.lanes; lane++) {
        const check = shade.copy(color).multiplyScalar((i + lane) % 2 ? DARK : 1);
        this.checks.setColorAt(record.first + i * record.lanes + lane, check);
      }
    }
    const dead = state.grid.targets[record.gate.target].dead;
    record.diedAt = dead ? -Infinity : -1;
    record.shown = dead ? 0 : record.gate.bar;
    record.from = record.shown;
    record.to = record.shown;
  }

  clear() {
    this.gates = [];
    this.checks.count = 0;
    for (const part of this.parts) {
      part.head.visible = false;
      part.ring.visible = false;
      part.cap.visible = false;
    }
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "gate_pull") {
        sound("gate_pull");
        const record = this.gates.find((r) => r.gate.target === event.target);
        if (record) {
          record.from = record.shown;
          record.to = event.bar;
          record.t0 = event.t;
          this.dirty = true;
        }
      } else if (event.k === "target_died" && event.owner === NUMBER) {
        sound("gate_open");
        const record = this.gates.find((r) => r.gate.target === event.target);
        if (record) {
          record.diedAt = event.t;
          this.dirty = true;
        }
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.gates.length) {
      return;
    }
    for (const record of this.gates) {
      const dead = state.grid.targets[record.gate.target].dead;
      if (record.to !== record.gate.bar && !(record.diedAt >= 0 && dead)) {
        // The page was rebuilt or resynced under the look: take the simulation's bar as it is
        record.from = record.gate.bar;
        record.to = record.gate.bar;
        record.t0 = -Infinity;
      }
      const pulled = easeOut(clamp01((this.now - record.t0) / PULL_TICKS));
      const shown = record.to + (record.from - record.to) * (1 - pulled);
      if (shown !== record.shown || pulled < 1 || record.diedAt >= 0) {
        this.dirty = true;
      }
      record.shown = shown;
    }
    if (this.dirty) {
      this.write();
    }
    this.dirty = this.gates.some((r) => r.diedAt >= 0 && this.now - r.diedAt < PULL_TICKS + POP_TICKS);
  }

  // How big the head stands: full while the gate lives, then shrinking once its bar has been pulled in
  headScale(record) {
    if (record.diedAt === -Infinity) {
      return 0;
    }
    if (record.diedAt < 0) {
      return 1;
    }
    const u = clamp01((this.now - record.diedAt - PULL_TICKS) / POP_TICKS);
    return 1 - u * u;
  }

  write() {
    for (const record of this.gates) {
      this.writeGate(record, this.parts[record.index]);
    }
    this.checks.instanceMatrix.needsUpdate = true;
  }

  writeGate(record, part) {
    const grow = this.headScale(record);
    const visible = grow > 0;
    const length = Math.min(record.shown, record.drawable) * record.cell;
    const edge = record.scale * grow;
    for (const mesh of [part.head, part.ring]) {
      mesh.visible = visible;
      mesh.position.copy(record.front);
      mesh.rotation.set(0, record.yaw, 0);
      mesh.scale.setScalar(Math.max(edge, 1e-4));
    }
    const strip = visible && length > 1e-3;
    part.cap.visible = strip;
    if (strip) {
      part.cap.rotation.set(0, record.yaw, 0);
      part.cap.scale.setScalar(record.scale);
      place.set(length - this.capBack * record.scale, 0, 0).applyMatrix4(record.root);
      part.cap.position.copy(place);
    }
    this.writeChecks(record, strip ? length : 0);
  }

  // The strip's boxes: square checks of the lane width along the strip, the last one cut to the strip's end
  writeChecks(record, length) {
    const middle = this.capMiddle * record.scale;
    const thick = this.capHeight * record.scale * STRIP_HEIGHT;
    for (let i = 0; i < record.reach; i++) {
      const start = i * record.pitch;
      const span = Math.min(record.pitch, length - start);
      for (let lane = 0; lane < record.lanes; lane++) {
        const slot = record.first + i * record.lanes + lane;
        if (span <= 1e-4) {
          this.checks.setMatrixAt(slot, HIDDEN);
          continue;
        }
        place.set(start + span / 2, middle, record.lane[lane] * STRIP_WIDTH);
        matrix.compose(place, turn.identity(), size.set(span, thick, record.pitch));
        matrix.premultiply(record.root);
        this.checks.setMatrixAt(slot, matrix);
      }
    }
  }
}

// Load the prefab and add the pools of heads, rings, caps and strip boxes to the scene
export async function create(scene) {
  const gltf = await new GLTFLoader().loadAsync(MODEL);
  return new GateLook(pieces(gltf), scene);
}
