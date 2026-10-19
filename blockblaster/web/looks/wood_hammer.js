// Feature 13, Woods and Hammers: a wood block is a grid of wooden crates over its cubes, each the original's
// `pixel_wood_block_model_default.glb` crate as wide as the block's BlockSize, with two nailed planks on top. Every hit
// breaks planks off the end of the block's plank list, at least one, so that floor((health - 1) / start x planks)
// stay (PixelWoodBlockFeature$$BreakWoodPlanks, RVA 0x5825F38), with a punch that runs out from the block's middle;
// at 0 the crates burst all at once (BreakAllWoodBlocks). A hammer (`hammer_feature.glb`, its head silver and its
// handle orange as in the New Feature picture) stands in its queue place instead of a cat. A strike lifts it 1 unit
// while it swells to 1.3 (0.3 s), jumps it to the wood (0.35 s, arc 5 units) while it tips back, smashes it down
// (0.2 s) as the damage lands, and swings it back while it shrinks away (0.4 s) (HammerFeature$$Hit, RVA 0x5822274).
// Everything comes from the simulation's records (sim/features/wood_hammer.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { mergeGeometries } from "../vendor/BufferGeometryUtils.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { play as sound } from "../sound.js";
import { NUMBER } from "../sim/features/wood_hammer.js";
import { HAMMER_DONE, HAMMER_LIFT, L_PER_UNIT, STRIKE_LANDS } from "../sim/numbers.js";

export { NUMBER };

const WOOD_MODEL = "models/features/pixel_wood_block_model_default.glb";
const HAMMER_MODEL = "models/features/hammer_feature.glb";
const SHADOW = "art/effects/Shadow_WoodBlock.png";
// The most crates one level holds is 238 (level 573), each with two planks; the most hammers is 30
const CRATES = 256;
const PLANKS = CRATES * 2;
const HAMMERS = 32;

const WOOD = new THREE.Color("#b8692f");
const PLANK = new THREE.Color("#d27a3c");
const NAIL = new THREE.Color("#5b331c");
const HEAD = new THREE.Color("#dcdcf4");
const HANDLE = new THREE.Color("#e8743a");
// The hammer mesh's head spans this much of its own x axis; the rest is the handle
const HEAD_FROM = -0.46;
const HEAD_TO = 0.06;

// A crate is as wide as its cells (a hair less) and this many cubes tall, planks included
const TILE_FIT = 0.96;
const WOOD_TALL = 1.6;
// A hit punches every crate out this much, starting at the block's middle and reaching its edge this many ticks
// later, each crate's punch lasting PUNCH_TICKS
const PUNCH = 0.12;
const PUNCH_TICKS = 12;
const WAVE_TICKS = 8;
// A broken plank flies off for this many ticks: sideways and upward speed per tick (crate widths), gravity
const PLANK_TICKS = 36;
const PLANK_SPREAD = 0.07;
const PLANK_UP = 0.06;
const PLANK_GRAVITY = 0.004;
// The crates of a broken block burst: they rise, spin and shrink over this many ticks
const BURST_TICKS = 24;
// The shadow, as the ice blocks lay theirs
const SHADOW_WIDE = 1.1;
const SHADOW_LONG = 1.3;
const SHADOW_SHIFT_X = 0.2;
const SHADOW_SHIFT_Z = 0.4;
const SHADOW_OPACITY = 0.3;
const SHADOW_LIFT = 0.004;

// The hammer next to a cat (a cat's body is 0.86 wide at scale 1), and its strike: the lift's rise (world units)
// and swell, the jump's ticks and arc, the tip back while jumping (ticks, and the two turns), the smash and the swing
// back (ticks and turn), and the shrink's ticks. At the wood its handle rests this far toward the viewer of the
// block's middle (hammer heights) and this high over the crates
const HAMMER_SIZE = 0.9;
const LIFT_RISE = 1;
const LIFT_SWELL = 0.3;
const JUMP_TICKS = 21;
const JUMP_ARC = 5;
const TIP_TICKS = 18;
const TIP_PITCH = (70 * Math.PI) / 180;
const TIP_TURN = (-30 * Math.PI) / 180;
const SMASH_TICKS = STRIKE_LANDS - HAMMER_LIFT - JUMP_TICKS;
const SMASH_TURN = (98 * Math.PI) / 180;
const SWING_BACK_TICKS = 12;
const SHRINK_TICKS = HAMMER_DONE - STRIKE_LANDS;
const REST_TOWARD = 0.35;
const REST_UP = 0.05;

const matrix = new THREE.Matrix4();
const local = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const turn = new THREE.Quaternion();
const spin = new THREE.Euler();
const STRAIGHT = new THREE.Quaternion();
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

function easeOutQuad(u) {
  return 1 - (1 - u) * (1 - u);
}

function easeInOutQuad(u) {
  return u < 0.5 ? 2 * u * u : 1 - 2 * (1 - u) * (1 - u);
}

function easeOutBack(u, overshoot = 3) {
  const v = u - 1;
  return 1 + v * v * ((overshoot + 1) * v + overshoot);
}

function easeInExpo(u) {
  return u <= 0 ? 0 : 2 ** (10 * u - 10);
}

function easeOutExpo(u) {
  return u >= 1 ? 1 : 1 - 2 ** (-10 * u);
}

// The planks standing at this health: every hit breaks at least one, and leaves at most
// floor((health - 1) / start x planks); none once the block is broken
export function planksStanding(total, start, health, dead) {
  if (dead) {
    return 0;
  }
  let standing = total;
  for (let h = start - 1; h >= health; h--) {
    standing = Math.max(0, Math.min(standing - 1, Math.floor(clamp01((h - 1) / start) * total + 1e-6)));
  }
  return standing;
}

// The crates of one block from its cells: BlockSize squares laid from the lowest row and leftmost column, as [x, y]
// of each crate's lower-left cell. Every block in the levels divides into whole squares
function tilesOf(grid, cells, side) {
  const open = new Set(cells);
  const tiles = [];
  const sorted = [...cells].sort((a, b) => Math.floor(a / grid.width) - Math.floor(b / grid.width) || a - b);
  for (const cell of sorted) {
    if (!open.has(cell)) {
      continue;
    }
    const x = cell % grid.width;
    const y = Math.floor(cell / grid.width);
    const square = [];
    for (let j = 0; j < side; j++) {
      for (let i = 0; i < side; i++) {
        square.push((y + j) * grid.width + x + i);
      }
    }
    if (!square.every((c) => open.has(c))) {
      continue;
    }
    square.forEach((c) => open.delete(c));
    tiles.push([x, y]);
  }
  return tiles;
}

// A mesh's geometry in the model's space (its node's place, turn and scale baked in), painted one color
function painted(node, color) {
  const geometry = node.geometry.clone();
  geometry.deleteAttribute("uv");
  geometry.applyMatrix4(local.compose(node.position, node.quaternion, node.scale));
  const colors = new Float32Array(geometry.attributes.position.count * 3);
  for (let i = 0; i < colors.length; i += 3) {
    colors[i] = color.r;
    colors[i + 1] = color.g;
    colors[i + 2] = color.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

// The crate, and one plank with its two nails centered on the plank's own middle, plus the plank's place on the
// crate (model units) and the model's width and height. The model's meshes are the crate, then per plank the
// plank and its two nails
function woodParts(gltf) {
  const nodes = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      nodes.push(node);
    }
  });
  const crate = painted(nodes[0], WOOD);
  const plankAt = [nodes[1].position.clone(), nodes[4].position.clone()];
  const plank = mergeGeometries([painted(nodes[1], PLANK), painted(nodes[2], NAIL), painted(nodes[3], NAIL)]);
  plank.translate(-plankAt[0].x, -plankAt[0].y, -plankAt[0].z);
  const box = new THREE.Box3().setFromObject(gltf.scene);
  return { crate, plank, plankAt, wide: box.max.x - box.min.x, tall: box.max.y - box.min.y };
}

// The hammer as the original's prefab stands it (handle down), its head silver and its handle orange, centered over
// the origin with its foot on it and one unit tall
function hammerModel(gltf) {
  let node = null;
  gltf.scene.traverse((child) => {
    node = node || (child.isMesh ? child : null);
  });
  const geometry = node.geometry.clone();
  const positions = geometry.attributes.position;
  const colors = new Float32Array(positions.count * 3);
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const color = x >= HEAD_FROM && x <= HEAD_TO ? HEAD : HANDLE;
    colors.set([color.r, color.g, color.b], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.applyMatrix4(local.compose(node.position, node.quaternion, node.scale));
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  geometry.translate(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
  geometry.scale(1 / (box.max.y - box.min.y), 1 / (box.max.y - box.min.y), 1 / (box.max.y - box.min.y));
  return geometry;
}

// One hammer: the root stands where it is, `move` tips it back, `rot` turns it for the smash
function hammerRig(geometry, material, scene) {
  const root = new THREE.Group();
  const move = new THREE.Group();
  const rot = new THREE.Group();
  root.add(move);
  move.add(rot);
  rot.add(new THREE.Mesh(geometry, material));
  root.visible = false;
  scene.add(root);
  return { root, move, rot };
}

class WoodHammerLook {
  constructor(parts, hammerGeometry, shadowMap, scene) {
    this.parts = parts;
    this.records = [];
    this.flights = [];
    this.mine = null;
    this.now = 0;
    this.cell = 0;
    this.height = 0;
    // Per hammer: its queue pose this frame (null when it isn't in a queue) and the last one it had there
    this.poses = new Map();
    this.last = new Map();
    // Per strike (hammer id): whether its smash has sounded
    this.swung = new Set();
    const woodMaterial = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, metalness: 0 });
    this.crates = new THREE.InstancedMesh(parts.crate, woodMaterial, CRATES);
    this.planks = new THREE.InstancedMesh(parts.plank, woodMaterial, PLANKS);
    const flat = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI);
    const shadowMaterial = new THREE.MeshBasicMaterial({
      map: shadowMap,
      color: 0x000000,
      transparent: true,
      opacity: SHADOW_OPACITY,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
    });
    this.shadows = new THREE.InstancedMesh(flat, shadowMaterial, CRATES);
    for (const mesh of [this.crates, this.planks, this.shadows]) {
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(mesh);
    }
    const hammerMaterial = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0.15 });
    this.hammers = Array.from({ length: HAMMERS }, () => hammerRig(hammerGeometry, hammerMaterial, scene));
  }

  // A new level: every block's crates and planks laid out in world units, the planks standing as its health says
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    this.cell = grid.size / L_PER_UNIT;
    this.height = Math.min(this.cell, PICTURE_HEIGHT) * WOOD_TALL;
    const listed = state.level.features.pixelWoodBlocks.WoodBlocks;
    let used = 0;
    mine.woods.forEach((wood, index) => {
      const body = grid.targets[wood.target];
      const side = Math.max(1, wood.size);
      // From the level's list, so a block already broken (its cells off the grid) still knows its crates
      const cells = listed[index].GridPoints.filter(
        (point) => point.X >= 0 && point.X < grid.width && point.Y >= 0 && point.Y < grid.height,
      ).map((point) => point.Y * grid.width + point.X);
      const tiles = tilesOf(grid, cells, side).map(([x, y]) => ({
        x: x + (side - 1) / 2,
        y: y + (side - 1) / 2,
        wx: (x + (side - 1) / 2 - (grid.width - 1) / 2) * this.cell,
        wz: -(y + (side - 1) / 2 - (grid.height - 1) / 2) * this.cell,
      }));
      if (used + tiles.length <= CRATES) {
        this.records.push(this.record(wood, body, side, tiles, used));
        used += tiles.length;
      }
    });
    this.crates.count = used;
    this.shadows.count = used;
    this.planks.count = used * 2;
    this.now = state.tick;
  }

  record(wood, body, side, tiles, first) {
    const xs = tiles.map((tile) => tile.wx);
    const zs = tiles.map((tile) => tile.wz);
    const middle = { x: (Math.min(...xs) + Math.max(...xs)) / 2, z: (Math.min(...zs) + Math.max(...zs)) / 2 };
    const reach = Math.max(1e-6, ...tiles.map((tile) => Math.hypot(tile.wx - middle.x, tile.wz - middle.z)));
    return {
      wood,
      side,
      tiles,
      first,
      middle,
      reach,
      planks: planksStanding(tiles.length * 2, wood.start, body.health, body.dead),
      dead: body.dead,
      punchAt: -1e9,
      burstAt: body.dead ? -1e9 : null,
    };
  }

  clear() {
    this.records = [];
    this.flights = [];
    this.poses.clear();
    this.last.clear();
    this.swung.clear();
    this.crates.count = 0;
    this.shadows.count = 0;
    this.planks.count = 0;
    for (const rig of this.hammers) {
      rig.root.visible = false;
    }
  }

  onEvents(events, state) {
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    for (const event of events) {
      if (event.k === "wood_hit") {
        const record = this.records.find((r) => r.wood === mine.woods[event.wood]);
        if (record) {
          record.punchAt = event.t;
        }
        sound("hammer_hit");
        sound(event.health > 0 ? "wood_hit" : "wood_break");
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.records.length) {
      return;
    }
    this.settle(state);
    this.drawWoods();
    this.drawFlights();
  }

  // Planks that broke since the last frame fly off; a block that broke bursts
  settle(state) {
    for (const record of this.records) {
      const body = state.grid.targets[record.wood.target];
      const standing = planksStanding(record.tiles.length * 2, record.wood.start, body.health, body.dead);
      for (let k = standing; k < record.planks; k++) {
        this.flights.push({ record, plank: k, t0: this.now });
      }
      record.planks = Math.min(record.planks, standing);
      if (body.dead && record.burstAt === null) {
        record.burstAt = this.now;
      }
    }
  }

  // Where a plank of a crate rests: the crate's matrix times the plank's place on it
  plankMatrix(tile, k, wide, tall, swell) {
    const at = this.parts.plankAt[k % 2];
    place.set(tile.wx + at.x * wide * swell, at.y * tall * swell, tile.wz + at.z * wide * swell);
    return matrix.compose(place, STRAIGHT, size.set(wide * swell, tall * swell, wide * swell));
  }

  // Every crate, its standing planks and its shadow at their sizes now
  drawWoods() {
    for (const record of this.records) {
      const wide = (this.cell * record.side * TILE_FIT) / this.parts.wide;
      const tall = this.height / this.parts.tall;
      const burst = record.burstAt === null ? 0 : clamp01((this.now - record.burstAt) / BURST_TICKS);
      record.tiles.forEach((tile, t) => {
        const slot = record.first + t;
        if (burst >= 1) {
          this.crates.setMatrixAt(slot, HIDDEN);
          this.shadows.setMatrixAt(slot, HIDDEN);
          return;
        }
        const swell = this.swellOf(record, tile) * (1 - easeOutQuad(burst));
        const lift = this.height * burst;
        turn.setFromEuler(spin.set(burst * (t % 2 ? 1.5 : -1.5), 0, burst * (t % 3 ? 1 : -1)));
        place.set(tile.wx, lift, tile.wz);
        this.crates.setMatrixAt(slot, matrix.compose(place, turn, size.set(wide * swell, tall * swell, wide * swell)));
        const across = this.cell * record.side * SHADOW_WIDE * (1 - burst);
        const length = this.cell * record.side * SHADOW_LONG * (1 - burst);
        place.set(tile.wx + across * SHADOW_SHIFT_X, PICTURE_HEIGHT + SHADOW_LIFT, tile.wz + length * SHADOW_SHIFT_Z);
        this.shadows.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(across, 1, length)));
        for (let k = 0; k < 2; k++) {
          const index = t * 2 + k;
          const flying = this.flights.some((f) => f.record === record && f.plank === index);
          if (!flying) {
            const shown = index < record.planks && burst === 0;
            this.planks.setMatrixAt(slot * 2 + k, shown ? this.plankMatrix(tile, k, wide, tall, swell) : HIDDEN);
          }
        }
      });
    }
    for (const mesh of [this.crates, this.planks, this.shadows]) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  }

  // A crate's punch: a bump that reaches it later the farther it stands from the block's middle
  swellOf(record, tile) {
    const delay = (Math.hypot(tile.wx - record.middle.x, tile.wz - record.middle.z) / record.reach) * WAVE_TICKS;
    const u = (this.now - record.punchAt - delay) / PUNCH_TICKS;
    return u < 0 || u > 1 ? 1 : 1 + PUNCH * Math.sin(Math.PI * u);
  }

  // Broken planks tumble up and away, shrinking as they fall
  drawFlights() {
    this.flights = this.flights.filter((flight) => {
      const { record, plank } = flight;
      const slot = (record.first + Math.floor(plank / 2)) * 2 + (plank % 2);
      const age = this.now - flight.t0;
      if (age >= PLANK_TICKS || age < 0) {
        this.planks.setMatrixAt(slot, HIDDEN);
        return age < 0;
      }
      const tile = record.tiles[Math.floor(plank / 2)];
      const wide = (this.cell * record.side * TILE_FIT) / this.parts.wide;
      const tall = this.height / this.parts.tall;
      const at = this.parts.plankAt[plank % 2];
      const angle = (plank * 2.399963) % (2 * Math.PI);
      const step = this.cell * record.side;
      const k = 1 - clamp01(age / PLANK_TICKS);
      place.set(
        tile.wx + at.x * wide + Math.cos(angle) * PLANK_SPREAD * step * age,
        Math.max(0, at.y * tall + (PLANK_UP * age - PLANK_GRAVITY * age * age) * step),
        tile.wz + at.z * wide + Math.sin(angle) * PLANK_SPREAD * step * age,
      );
      turn.setFromEuler(spin.set(age * 0.2, angle, age * 0.12));
      this.planks.setMatrixAt(slot, matrix.compose(place, turn, size.set(wide * k, tall * k, wide * k)));
      return true;
    });
    this.planks.instanceMatrix.needsUpdate = true;
  }

  begin(state) {
    this.mine = state.features[NUMBER] || null;
    this.poses.clear();
  }

  // A hammer's entry is drawn as the hammer: remember where its cat would stand and hide the cat. A used hammer's
  // later poses (an old snapshot while it vanishes) are not its own, so only queue poses are kept for it
  shape(id, pig, pose) {
    if (!this.mine || !this.mine.hammers.includes(id)) {
      return;
    }
    const used = this.mine.used.includes(id);
    if (pose.shown && (!used || pig.place === "queue")) {
      const at = { x: pose.x, y: pose.y + pose.air, z: pose.z, yaw: pose.yaw, scale: pose.scale * pose.sx };
      this.poses.set(id, at);
      if (pig.place === "queue") {
        this.last.set(id, at);
      }
    }
    pose.shown = false;
  }

  end() {
    if (!this.mine) {
      return;
    }
    let used = 0;
    for (const id of this.mine.hammers) {
      if (used >= this.hammers.length) {
        break;
      }
      const rig = this.hammers[used];
      if (this.drawHammer(rig, id)) {
        used += 1;
      }
    }
    for (let i = used; i < this.hammers.length; i++) {
      this.hammers[i].root.visible = false;
    }
  }

  // One hammer: standing in its place, or on its strike. Returns false when it isn't drawn
  drawHammer(rig, id) {
    const strike = this.mine.strikes.find((entry) => entry[0] === id);
    const pose = this.poses.get(id);
    if (!strike) {
      if (!pose || this.mine.used.includes(id)) {
        return false;
      }
      this.stand(rig, pose, 0, 0, 0, 1);
      return true;
    }
    const from = pose || this.last.get(id);
    const age = this.now - strike[2];
    if (!from || age >= HAMMER_DONE) {
      return false;
    }
    if (age < 0) {
      this.stand(rig, from, 0, 0, 0, 1);
      return true;
    }
    this.strikeHammer(rig, id, from, this.restOf(strike[1], from), age);
    return true;
  }

  // Where the hammer's foot rests at the wood: by the block's middle, a little toward the viewer, over the crates
  restOf(woodIndex, from) {
    const record = this.records.find((r) => r.wood === this.mine.woods[woodIndex]);
    if (!record) {
      return { x: from.x, y: from.y, z: from.z };
    }
    const height = HAMMER_SIZE * from.scale * (1 + LIFT_SWELL);
    return { x: record.middle.x, y: this.height + REST_UP, z: record.middle.z + REST_TOWARD * height };
  }

  // The strike at this age: lift, jump with the tip back, smash, swing back while shrinking
  strikeHammer(rig, id, from, rest, age) {
    const lift = easeOutBack(clamp01(age / HAMMER_LIFT));
    const startY = from.y + LIFT_RISE * lift;
    const scale = 1 + LIFT_SWELL * lift;
    const jump = clamp01((age - HAMMER_LIFT) / JUMP_TICKS);
    const glide = easeOutQuad(jump);
    const at = {
      x: from.x + (rest.x - from.x) * glide,
      y: startY + (rest.y - startY) * glide + JUMP_ARC * 4 * jump * (1 - jump),
      z: from.z + (rest.z - from.z) * glide,
      yaw: from.yaw,
      scale: from.scale,
    };
    const tip = easeInOutQuad(clamp01((age - HAMMER_LIFT) / TIP_TICKS));
    const smashAge = age - HAMMER_LIFT - JUMP_TICKS;
    if (smashAge >= 0 && !this.swung.has(id)) {
      this.swung.add(id);
      sound("hammer_swing");
    }
    const smash = easeInExpo(clamp01(smashAge / SMASH_TICKS));
    const back = easeOutExpo(clamp01((age - STRIKE_LANDS) / SWING_BACK_TICKS));
    const shrink = 1 - easeOutQuad(clamp01((age - STRIKE_LANDS) / SHRINK_TICKS));
    this.stand(rig, at, TIP_PITCH * tip, TIP_TURN * tip, SMASH_TURN * (back - smash), scale * shrink);
  }

  // Put a hammer at a pose with its tip back (pitch), its turn and its smash turn, at a share of its size
  stand(rig, at, pitch, yaw, smash, grow) {
    rig.root.visible = grow > 0.001;
    rig.root.position.set(at.x, at.y, at.z);
    rig.root.rotation.set(0, at.yaw, 0);
    rig.root.scale.setScalar(at.scale * HAMMER_SIZE * grow);
    rig.move.rotation.set(pitch, 0, 0);
    rig.rot.rotation.set(0, yaw, smash);
  }
}

// Load the meshes and the shadow, and add the pools to the scene
export async function create(scene) {
  const loader = new GLTFLoader();
  const [woodGltf, hammerGltf, shadow] = await Promise.all([
    loader.loadAsync(WOOD_MODEL),
    loader.loadAsync(HAMMER_MODEL),
    new THREE.TextureLoader().loadAsync(SHADOW),
  ]);
  shadow.colorSpace = THREE.SRGBColorSpace;
  return new WoodHammerLook(woodParts(woodGltf), hammerModel(hammerGltf), shadow, scene);
}
