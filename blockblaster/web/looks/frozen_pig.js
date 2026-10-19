// Feature 14, the Frozen Pig: the cat stands inside a shell of pale blue ice with three crystal spikes, and a white tag
// on top of the shell shows how many pigs must still run dry before the ice melts. Every pig that vanishes knocks the
// shell with a small punch and a crack sound; at 0 the shell bursts into shards that fly out, fall and shrink, with the
// shatter sound, and the cat stands free. The shell is `models/overlay_frozen.glb` (ASSETS.md), placed on the cat like
// every overlay. The sounds are the ice block's (the prefab holds no audio field). Everything comes from the
// simulation's ice records (sim/features/frozen_pig.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { NUMBER } from "../sim/features/frozen_pig.js";
import { play as sound } from "../sound.js";

export { NUMBER };

const MODEL = "models/overlay_frozen.glb";
// The most frozen pigs one level holds is 42 (level 1028)
const CAPACITY = 48;
// A knock: the shell swells this much and settles over this many ticks
const KNOCK_TICKS = 10;
const KNOCK_GROWTH = 0.07;
// The shell's top, where the tag floats, and the tag's width as a share of the shell
const SHELL_TOP = 1.14;
const LABEL_LIFT = 0.02;
// The tag sits toward the camera so the cat's own ammo number stays readable behind it
const LABEL_FORWARD = 0.34;
const LABEL_WIDE = 0.62;
// The tag: a white pill with dark digits
const LABEL_W = 128;
const LABEL_H = 80;
const LABEL_FONT = '"Inter Black", "Segoe UI", sans-serif';
const LABEL_INK = "#1f3a68";
const LABEL_SHARE = 0.78;
// A burst throws this many shards; this many fit on screen at once
const SHARDS = 10;
const SHARD_CAPACITY = 160;
const SHARD_TICKS = 36;
const SHARD_SIZE = 0.2;
const SHARD_SPREAD = 0.028;
const SHARD_UP = 0.05;
const SHARD_GRAVITY = 0.0034;
// Shards fly out at golden-angle steps, a little different for every pig
const GOLDEN = 2.399963;
const SHARD_COLOR = "#8fd3ff";

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();
const euler = new THREE.Euler();

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

class FrozenLook {
  constructor(parts, shards) {
    this.parts = parts;
    this.shards = shards;
    this.now = 0;
    this.mine = null;
    // Per pig id: its drawn pose this frame ({x, y, z, yaw, sx, sy}), and the last one it had when it was shown
    this.poses = new Map();
    this.lastSeen = new Map();
    // Per pig id: when it was last knocked, and the bursts still flying ({t0, id, x, y, z, s})
    this.knocked = new Map();
    this.bursts = [];
    // The count each pool part's tag shows now (null: not drawn)
    this.shown = parts.map(() => null);
  }

  build(state) {
    this.clear();
    this.mine = state.features[NUMBER] || null;
    this.now = state.tick;
  }

  clear() {
    this.mine = null;
    this.poses.clear();
    this.lastSeen.clear();
    this.knocked.clear();
    this.bursts = [];
    this.shown.fill(null);
    for (const part of this.parts) {
      part.group.visible = false;
    }
    this.shards.count = 0;
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "frozen_hit" && event.health > 0) {
        this.knocked.set(event.pig, event.t);
        sound("ice_hit");
      } else if (event.k === "frozen_thaw") {
        const at = this.lastSeen.get(event.pig);
        if (at) {
          this.bursts.push({ t0: event.t, id: event.pig, ...at });
        }
        sound("ice_shatter");
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
  }

  begin(state) {
    this.mine = state.features[NUMBER] || null;
    this.poses.clear();
  }

  // Every frozen pig that is drawn: remember where its cat stands, so the shell goes over it
  shape(id, pig, pose) {
    if (!this.mine || !pose.shown) {
      return;
    }
    const entry = this.mine.ice.find((ice) => ice.pig === id);
    if (!entry) {
      return;
    }
    const at = { x: pose.x, y: pose.y + pose.air, z: pose.z, yaw: pose.yaw, sx: pose.scale * pose.sx, sy: pose.scale * pose.sy };
    this.lastSeen.set(id, at);
    if (entry.health > 0) {
      this.poses.set(id, { ...at, health: entry.health });
    }
  }

  end() {
    if (!this.mine) {
      return;
    }
    let used = 0;
    for (const [id, at] of this.poses) {
      if (used >= this.parts.length) {
        break;
      }
      this.write(used, id, at);
      used += 1;
    }
    for (let i = used; i < this.parts.length; i++) {
      this.parts[i].group.visible = false;
      this.shown[i] = null;
    }
    this.writeShards();
  }

  // One shell where its cat stands, swelling a little after a knock, with the count on its tag
  write(index, id, at) {
    const part = this.parts[index];
    const u = clamp01((this.now - (this.knocked.get(id) ?? -Infinity)) / KNOCK_TICKS);
    const k = u < 1 ? Math.sin(Math.PI * u) : 0;
    const grow = 1 + KNOCK_GROWTH * k;
    part.group.visible = true;
    part.group.position.set(at.x, at.y, at.z);
    part.group.rotation.set(0, at.yaw, 0);
    part.group.scale.set(at.sx * grow, at.sy * grow, at.sx * grow);
    if (this.shown[index] !== at.health) {
      this.shown[index] = at.health;
      this.paint(part, at.health);
    }
  }

  // The tag's number, redrawn only when it changed
  paint(part, count) {
    const g = part.canvas.getContext("2d");
    g.clearRect(0, 0, LABEL_W, LABEL_H);
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.roundRect(2, 2, LABEL_W - 4, LABEL_H - 4, LABEL_H / 2 - 2);
    g.fill();
    g.font = `900 ${Math.round(LABEL_H * LABEL_SHARE)}px ${LABEL_FONT}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = LABEL_INK;
    g.fillText(String(count), LABEL_W / 2, LABEL_H * 0.54, LABEL_W * 0.8);
    part.map.needsUpdate = true;
  }

  // The shards of every recent burst, flying out, falling and shrinking
  writeShards() {
    let count = 0;
    this.bursts = this.bursts.filter((burst) => this.now - burst.t0 < SHARD_TICKS);
    for (const burst of this.bursts) {
      const age = Math.max(0, this.now - burst.t0);
      const u = age / SHARD_TICKS;
      for (let k = 0; k < SHARDS && count < SHARD_CAPACITY; k++) {
        const angle = (burst.id + k) * GOLDEN;
        const reach = SHARD_SPREAD * (0.6 + (k % 3) * 0.3) * age * burst.sx;
        const rise = burst.sy * (0.35 + 0.15 * (k % 4)) + (SHARD_UP * (1 + (k % 2)) * age - SHARD_GRAVITY * age * age) * burst.sy;
        place.set(burst.x + Math.cos(angle) * reach, burst.y + Math.max(0.02, rise), burst.z + Math.sin(angle) * reach);
        euler.set(age * 0.21 + k, age * 0.17 + angle, k);
        turn.setFromEuler(euler);
        const shrink = (1 - u * u) * SHARD_SIZE * burst.sx * (0.7 + 0.5 * ((k * 7) % 5) / 4);
        matrix.compose(place, turn, size.setScalar(Math.max(0.001, shrink)));
        this.shards.setMatrixAt(count++, matrix);
      }
    }
    this.shards.count = count;
    this.shards.instanceMatrix.needsUpdate = true;
  }
}

// Load the shell and add a pool of shells with their tags and the shard mesh to the scene
export async function create(scene) {
  const gltf = await new GLTFLoader().loadAsync(MODEL);
  const parts = [];
  for (let i = 0; i < CAPACITY; i++) {
    const group = new THREE.Group();
    const shell = gltf.scene.clone();
    shell.traverse((node) => {
      if (node.isMesh) {
        node.renderOrder = 2;
        node.material = node.material.clone();
        node.material.depthWrite = false;
      }
    });
    group.add(shell);
    const canvas = document.createElement("canvas");
    canvas.width = LABEL_W;
    canvas.height = LABEL_H;
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = 4;
    const label = new THREE.Mesh(
      new THREE.PlaneGeometry(1, LABEL_H / LABEL_W),
      new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false }),
    );
    label.rotation.x = -Math.PI / 2;
    label.position.set(0, SHELL_TOP + LABEL_LIFT, LABEL_FORWARD);
    label.scale.setScalar(LABEL_WIDE);
    label.renderOrder = 4;
    // The cat faces up the screen, which would put the digits upside down
    const upright = new THREE.Group();
    upright.rotation.y = Math.PI;
    upright.add(label);
    group.add(upright);
    group.visible = false;
    scene.add(group);
    parts.push({ group, canvas, map, label });
  }
  const shards = new THREE.InstancedMesh(
    new THREE.TetrahedronGeometry(1),
    new THREE.MeshStandardMaterial({
      color: SHARD_COLOR,
      roughness: 0.1,
      metalness: 0,
      transparent: true,
      opacity: 0.85,
    }),
    SHARD_CAPACITY,
  );
  shards.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  shards.frustumCulled = false;
  shards.renderOrder = 3;
  shards.count = 0;
  scene.add(shards);
  return new FrozenLook(parts, shards);
}
