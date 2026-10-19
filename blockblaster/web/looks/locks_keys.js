// Feature 4, Locks and Keys: a golden padlock stands in a lock's queue place instead of a cat, and a golden key lies
// on its cells in the picture. When the simulation frees a key it rises (0.2 s), jumps to its lock (0.35 s) and turns
// in it with a punch (0.3 s) while the shackle springs open; then the lock's entry vanishes like a pig (fx.js).
// The meshes are the original's `models/features/key_feature.glb` and `lock_feature.glb` (ASSETS.md), colored here.
// Everything comes from the simulation's lock list and flights (sim/features/locks_keys.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { centerX, centerY } from "../sim/grid.js";
import { NUMBER } from "../sim/features/locks_keys.js";
import { KEY_FLIGHT, L_PER_UNIT } from "../sim/numbers.js";
import { play as sound } from "../sound.js";

export { NUMBER };

const KEY_MODEL = "models/features/key_feature.glb";
const LOCK_MODEL = "models/features/lock_feature.glb";
// The most keys (and locks) one level holds is 8
const CAPACITY = 16;

const GOLD = new THREE.Color("#f6bd1e");
const SHACKLE = new THREE.Color("#ffd75a");
const KEYHOLE = new THREE.Color("#3a2414");
const KEY_GOLD = new THREE.Color("#ffc928");

// The flight, in ticks: KEY_FLIGHT is 0.2 s rise + 0.35 s jump + 0.3 s punch (KeyFeature$$DetachInternal)
const RISE_TICKS = 12;
const JUMP_TICKS = 21;
const PUNCH_TICKS = KEY_FLIGHT - RISE_TICKS - JUMP_TICKS;
// How high the key rises, how high its jump arcs, how much it grows while rising, and the punch's swell
const RISE_HEIGHT = 1.1;
const JUMP_ARC = 1.6;
const RISE_GROW = 1.35;
const PUNCH_SWELL = 0.35;
// The key's length as a share of its cells' longer side, and as a share of the lock's width when it reaches the lock
const KEY_FIT = 1.05;
const KEY_AT_LOCK = 0.9;
// The key lies this far above the picture's floor. At the lock it lies over the padlock's face (the top the camera
// looks down on, this high in lock widths) with its tip on the keyhole and its bow up the screen, and pushes in this
// far as it turns. The mesh's tip is its -x end
const KEY_LIFT = 0.04;
const LOCK_TOP = 0.65;
const KEY_PUSH = 0.12;
const KEY_AT_LOCK_YAW = Math.PI / 2;
// The padlock's width next to a cat's (the cat's body is 0.86 wide at scale 1)
const LOCK_SIZE = 1.0;
// The open shackle slides out this far (lock units) and swings this far round
const SHACKLE_LIFT = 0.16;
const SHACKLE_SWING = 0.5;

const UP = new THREE.Vector3(0, 1, 0);
const ALONG = new THREE.Vector3(1, 0, 0);
const turn = new THREE.Quaternion();
const twist = new THREE.Quaternion();
const from = new THREE.Vector3();
const to = new THREE.Vector3();

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

function easeOut(u) {
  return 1 - (1 - u) * (1 - u);
}

// A part of a face-less mesh with one color
function painted(mesh, color) {
  mesh.material = new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.35 });
  return mesh;
}

// The key's mesh laid flat: its long side along x, its teeth along z, its thin side up, centered on the origin
function keyGeometry(gltf) {
  let source = null;
  gltf.scene.traverse((node) => {
    source = source || (node.isMesh ? node.geometry : null);
  });
  const geometry = source.clone();
  geometry.applyMatrix4(new THREE.Matrix4().set(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1));
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  geometry.translate(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
  geometry.computeBoundingBox();
  return geometry;
}

// The padlock as the original's prefab lies: keyhole on its top for a camera looking down, shackle reaching away from
// the viewer once turned like a queue cat, centered with its foot on the ground and one unit wide
function lockModel(gltf) {
  const lock = gltf.scene.clone();
  lock.traverse((node) => {
    if (node.isMesh) {
      const name = node.name;
      painted(node, name.startsWith("Circle") ? SHACKLE : name.startsWith("Cube") ? KEYHOLE : GOLD);
    }
  });
  const box = new THREE.Box3().setFromObject(lock);
  const width = box.max.x - box.min.x;
  const inner = new THREE.Group();
  inner.add(lock);
  lock.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
  inner.scale.setScalar(1 / width);
  return inner;
}

class LocksKeysLook {
  constructor(keys, locks) {
    this.keys = keys;
    this.locks = locks;
    this.now = 0;
    this.mine = null;
    // Per key: where it lies and how long it is drawn there
    this.rests = [];
    // Per lock pig id: its drawn pose this frame ({x, y, z, yaw, scale} or null)
    this.poses = new Map();
    // Per key index: its flight {lock, t0, land, sounded}
    this.flights = new Map();
  }

  // A new level: every key on its cells, flights already under way picked up from the simulation
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const grid = state.grid;
    const cell = grid.size / L_PER_UNIT;
    this.rests = mine.cells.slice(0, CAPACITY).map((cells) => this.rest(grid, cells, cell));
    for (const [index, lock, land] of mine.flights) {
      this.flights.set(index, { lock, t0: land - KEY_FLIGHT, land, sounded: false });
    }
    this.now = state.tick;
    this.begin(state);
  }

  // A key's resting spot: the middle of its cells, lying along their longer side
  rest(grid, cells, cell) {
    const xs = cells.map((c) => c % grid.width);
    const ys = cells.map((c) => Math.floor(c / grid.width));
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const across = (x1 - x0 + 1) * cell;
    const down = (y1 - y0 + 1) * cell;
    return {
      x: (centerX(grid, x0) + centerX(grid, x1)) / 2 / L_PER_UNIT,
      z: -(centerY(grid, y0) + centerY(grid, y1)) / 2 / L_PER_UNIT,
      yaw: down > across ? Math.PI / 2 : 0,
      length: Math.max(across, down) * KEY_FIT,
      y: Math.min(KEY_LIFT, PICTURE_HEIGHT),
    };
  }

  clear() {
    this.mine = null;
    this.rests = [];
    this.poses.clear();
    this.flights.clear();
    for (const key of this.keys) {
      key.visible = false;
    }
    for (const lock of this.locks) {
      lock.group.visible = false;
    }
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "key_unlock") {
        this.flights.set(event.key, { lock: event.lock, t0: event.land - KEY_FLIGHT, land: event.land, sounded: false });
      } else if (event.k === "lock_opened") {
        this.flights.delete(event.key);
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

  // A lock's entry is drawn as the padlock: remember where its cat would stand and hide the cat
  shape(id, pig, pose) {
    if (!this.mine || !pose.shown || !this.mine.locks.includes(id)) {
      return;
    }
    this.poses.set(id, { x: pose.x, y: pose.y + pose.air, z: pose.z, yaw: pose.yaw, scale: pose.scale * pose.sx });
    pose.shown = false;
  }

  end() {
    if (!this.mine) {
      return;
    }
    this.writeLocks();
    this.writeKeys();
  }

  // The padlocks where their cats would stand; a lock whose key is turning has its shackle open
  writeLocks() {
    let used = 0;
    for (const [id, at] of this.poses) {
      if (used >= this.locks.length) {
        break;
      }
      const lock = this.locks[used++];
      lock.group.visible = true;
      lock.group.position.set(at.x, at.y, at.z);
      lock.group.rotation.set(0, at.yaw, 0);
      lock.group.scale.setScalar(at.scale * LOCK_SIZE);
      const open = this.opening(id);
      lock.shackle.position.copy(lock.home).addScaledVector(lock.out, SHACKLE_LIFT * open);
      lock.shackle.quaternion.copy(lock.homeTurn).premultiply(twist.setFromAxisAngle(UP, SHACKLE_SWING * open));
    }
    for (let i = used; i < this.locks.length; i++) {
      this.locks[i].group.visible = false;
    }
  }

  // 0 while the lock's key is away, rising to 1 as the key turns in it
  opening(lockId) {
    for (const flight of this.flights.values()) {
      if (flight.lock === lockId) {
        return easeOut(clamp01((this.now - flight.t0 - RISE_TICKS - JUMP_TICKS) / PUNCH_TICKS));
      }
    }
    return 0;
  }

  writeKeys() {
    this.rests.forEach((rest, index) => {
      const key = this.keys[index];
      const flight = this.flights.get(index);
      if (flight) {
        key.visible = this.flyKey(key, rest, flight);
        return;
      }
      key.visible = !this.mine.used[index];
      if (key.visible) {
        key.position.set(rest.x, rest.y, rest.z);
        key.quaternion.setFromAxisAngle(UP, rest.yaw);
        key.scale.setScalar(rest.length / key.userData.length);
      }
    });
  }

  // Where a flying key is drawn: up from its cells, an arc to the front of its lock, then a turn and a punch there.
  // Returns false once the flight is over
  flyKey(key, rest, flight) {
    const age = this.now - flight.t0;
    if (age >= KEY_FLIGHT) {
      return false;
    }
    const lock = this.poses.get(flight.lock);
    const lockScale = lock ? lock.scale * LOCK_SIZE : rest.length;
    from.set(rest.x, rest.y, rest.z);
    if (lock) {
      to.set(lock.x, lock.y + LOCK_TOP * lockScale, lock.z - (KEY_AT_LOCK / 2) * lockScale);
    } else {
      to.copy(from).setY(from.y + RISE_HEIGHT);
    }
    const startLength = rest.length;
    const endLength = lockScale * KEY_AT_LOCK;
    const rise = easeOut(clamp01(age / RISE_TICKS));
    const jump = clamp01((age - RISE_TICKS) / JUMP_TICKS);
    const punch = clamp01((age - RISE_TICKS - JUMP_TICKS) / PUNCH_TICKS);
    if (punch > 0 && !flight.sounded) {
      flight.sounded = true;
      sound("lock_open");
    }
    const lifted = from.y + RISE_HEIGHT * rise;
    key.position.lerpVectors(from, to, jump);
    key.position.y = lifted + (to.y - lifted) * jump + JUMP_ARC * 4 * jump * (1 - jump);
    key.position.z += KEY_PUSH * lockScale * Math.sin((Math.PI / 2) * punch);
    let length = startLength * (1 + (RISE_GROW - 1) * rise);
    length += (endLength - length) * jump;
    length *= 1 + PUNCH_SWELL * Math.sin(Math.PI * punch);
    key.scale.setScalar(length / key.userData.length);
    // The key swings from lying along its cells to pointing at the keyhole, then turns a quarter in it
    turn.setFromAxisAngle(UP, rest.yaw + (KEY_AT_LOCK_YAW - rest.yaw) * easeOut(jump));
    twist.setFromAxisAngle(ALONG, (Math.PI / 2) * easeOut(punch));
    key.quaternion.copy(turn).multiply(twist);
    return true;
  }
}

// Load both meshes and add a pool of keys and padlocks to the scene
export async function create(scene) {
  const loader = new GLTFLoader();
  const [keyGltf, lockGltf] = await Promise.all([loader.loadAsync(KEY_MODEL), loader.loadAsync(LOCK_MODEL)]);
  const geometry = keyGeometry(keyGltf);
  const keyMaterial = new THREE.MeshStandardMaterial({ color: KEY_GOLD, roughness: 0.3, metalness: 0.4 });
  const length = geometry.boundingBox.max.x - geometry.boundingBox.min.x;
  const keys = [];
  const locks = [];
  const source = lockModel(lockGltf);
  for (let i = 0; i < CAPACITY; i++) {
    const key = new THREE.Mesh(geometry, keyMaterial);
    key.userData.length = length;
    key.visible = false;
    scene.add(key);
    keys.push(key);
    const group = source.clone();
    let shackle = null;
    group.traverse((node) => {
      shackle = shackle || (node.isMesh && node.name.startsWith("Circle") ? node : null);
    });
    group.visible = false;
    scene.add(group);
    // The shackle reaches along its parent's +z, away from the viewer
    locks.push({
      group,
      shackle,
      home: shackle.position.clone(),
      homeTurn: shackle.quaternion.clone(),
      out: new THREE.Vector3(0, 0, 1),
    });
  }
  return new LocksKeysLook(keys, locks);
}
