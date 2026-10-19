// Feature 2, the Connected Pig: a rope ties each member of a group to the next one, in queues, slots, the rescue row
// and on the belt (reference frames linked-pairs-queue.png, level1000-linked-pairs-slots.png). Each half of the rope
// takes the color of the pig it starts from, blending only in the middle, and it arcs over the pigs standing between two
// members of one queue. The members hop on one after another 0.05 s apart, which the placing already does. The groups
// come from the simulation (sim/features/connected.js); the rope never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { COLORS } from "../picture.js";
import { NUMBER } from "../sim/features/connected.js";

export { NUMBER };

// Pieces per rope between two pigs, and room for every rope of the busiest level
const SEGMENTS = 10;
const ROPE_CAPACITY = 1024;
const ROPE_RADIUS = 0.11;
// Each half of a rope is its own pig's color; they blend over this share of the rope's length in the middle
const BLEND = 0.2;
// Where the rope leaves a pig, as a share of its height at pig scale 1, and how high it arcs: a share of the span
// between the two pigs, at most ROPE_ARC_MOST
const ROPE_HOLD = 0.6;
const ROPE_ARC = 0.22;
const ROPE_ARC_MOST = 1.1;

const matrix = new THREE.Matrix4();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();
const from = new THREE.Vector3();
const to = new THREE.Vector3();
const mid = new THREE.Vector3();
const a = new THREE.Vector3();
const b = new THREE.Vector3();
const step = new THREE.Vector3();
const shade = new THREE.Color();
const UP = new THREE.Vector3(0, 1, 0);

class ConnectedLook {
  constructor(mesh) {
    this.mesh = mesh;
    this.groups = [];
    // Per member id: {x, y, z, s, color} where it is drawn this frame; `seen` is false while it isn't drawn
    this.ends = new Map();
  }

  // A new level: a place to note each member, made once
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    for (const members of mine ? mine.groups : []) {
      for (const id of members) {
        this.ends.set(id, { x: 0, y: 0, z: 0, s: 1, color: new THREE.Color(), seen: false });
      }
    }
    this.begin(state);
  }

  clear() {
    this.ends.clear();
    this.groups = [];
    this.mesh.count = 0;
  }

  begin(state) {
    const mine = state.features[NUMBER];
    this.groups = mine ? mine.groups : [];
    for (const end of this.ends.values()) {
      end.seen = false;
    }
  }

  // Note where each member is drawn this frame, after every other look has dressed it
  shape(id, pig, pose) {
    if (!pose.shown || pose.scale <= 0.01) {
      return;
    }
    const end = this.ends.get(id);
    if (!end) {
      return;
    }
    end.seen = true;
    end.x = pose.x;
    end.y = pose.y + pose.air + ROPE_HOLD * pose.scale * pose.sy;
    end.z = pose.z;
    end.s = pose.scale;
    end.color.copy(pose.tint || COLORS[pig.color]);
  }

  // Draw a rope between every two linked members that are both on screen
  end() {
    let count = 0;
    for (const members of this.groups) {
      for (let k = 0; k + 1 < members.length; k++) {
        const first = this.ends.get(members[k]);
        const second = this.ends.get(members[k + 1]);
        if (first.seen && second.seen && count + SEGMENTS <= ROPE_CAPACITY) {
          count += this.writeRope(count, first, second);
        }
      }
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) {
      this.mesh.instanceColor.needsUpdate = true;
    }
  }

  // One rope: a curve from one pig to the other lifted in the middle, drawn as short pieces of tube
  writeRope(at, first, second) {
    from.set(first.x, first.y, first.z);
    to.set(second.x, second.y, second.z);
    const span = from.distanceTo(to);
    const lift = Math.min(ROPE_ARC_MOST, ROPE_ARC * span);
    mid.addVectors(from, to).multiplyScalar(0.5);
    mid.y += lift * 2;
    const thick = ROPE_RADIUS * Math.min(first.s, second.s);
    for (let k = 0; k < SEGMENTS; k++) {
      curvePoint(k / SEGMENTS, a);
      curvePoint((k + 1) / SEGMENTS, b);
      step.subVectors(b, a);
      const length = step.length();
      turn.setFromUnitVectors(UP, length > 1e-6 ? step.divideScalar(length) : UP);
      matrix.compose(a.lerp(b, 0.5), turn, size.set(thick, length * 1.05, thick));
      this.mesh.setMatrixAt(at + k, matrix);
      const u = Math.min(1, Math.max(0, ((k + 0.5) / SEGMENTS - 0.5) / BLEND + 0.5));
      this.mesh.setColorAt(at + k, shade.copy(first.color).lerp(second.color, u));
    }
    return SEGMENTS;
  }
}

// A point of the curve from `from` to `to` through the lifted middle (a quadratic Bezier)
function curvePoint(u, out) {
  const v = 1 - u;
  return out
    .copy(from)
    .multiplyScalar(v * v)
    .addScaledVector(mid, 2 * u * v)
    .addScaledVector(to, u * u);
}

// Make the rope mesh and add it to the scene
export async function create(scene) {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 8, 1, true);
  const material = new THREE.MeshStandardMaterial({ roughness: 0.7 });
  const mesh = new THREE.InstancedMesh(geometry, material, ROPE_CAPACITY);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.setColorAt(0, shade.set(0xffffff));
  mesh.frustumCulled = false;
  mesh.count = 0;
  scene.add(mesh);
  return new ConnectedLook(mesh);
}
