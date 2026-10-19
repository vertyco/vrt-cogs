// Feature 17, Rockets: a rocket split in two lies on the picture, its white finned rear (the start part) and its red nose
// with a porthole (the end part) joined by a crackling cyan light path (the original's
// `models/features/split_object_feature.glb`: Model_Rocket_1 is the nose, Model_Rocket_2 the rear; the prefab holds no
// materials, so the paint is the look's choice, taken from the feature's picture). Each part rests on its slice of the
// path, facing along it, and slides one slice along the path when a shot moves it, swelling a little (0.3 s, the
// prefab's clipPercentDuration). The light path is drawn per cell, a glowing glass block with a flickering core on
// every cell the simulation's path covers; cells the parts pass shrink away. When the rocket's health runs out the parts
// slide together (0.35 s to 60 percent, then a 0.1 s snap), the joined rocket swells, turns nose up, shakes, rises 3
// units and boosts 50 units away, as the prefab's rocketMerge*, rocketPunch*, rocketLift*, rocketShake*, rocketFlyUp*
// and rocketBoost* fields time it. Sounds: the rear's and the nose's hits, the merge, the lift-off and the boost, as
// the prefab pairs them. Everything comes from the simulation's rocket records (sim/features/rocket.js) and never
// changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { play as sound } from "../sound.js";
import { END, NUMBER, START } from "../sim/features/rocket.js";
import { L_PER_UNIT } from "../sim/numbers.js";

export { NUMBER };

const MODEL = "models/features/split_object_feature.glb";
// The most rockets one level holds is 14 (level 1243); the most light path cells 608 (level 692)
const ROCKETS = 16;
const TILES = 768;
const FADING = 256;
// The parts' size against their area, across the rocket's body
const FIT = 0.92;
// Light path blocks: share of a cell they fill, their height and their core's height against the part's width
const TILE_FILL = 1;
const TILE_TALL = 0.55;
const CORE_FILL = 0.3;
const CORE_TALL = 0.5;
const CORE_FLICKER = 0.35;
// Timings in ticks (60 a second), from the prefab: a slide, a hit's swell, a path cell sinking away
const SLIDE_TICKS = 18;
const PUNCH = 0.12;
const PUNCH_TICKS = 9;
const SINK_TICKS = 18;
// The launch: merge approach (to 60 percent) and snap, the joined rocket's punch, the wait before lift-off, the lift,
// the shake, the fly up (after a delay) and the boost (after the fly up's length), all from the lift-off
const MERGE_APPROACH = 21;
const MERGE_SHARE = 0.6;
const MERGE_SNAP = 6;
const MERGE_PUNCH = 0.4;
const MERGE_PUNCH_TICKS = 18;
const LIFT_AT = MERGE_APPROACH + MERGE_SNAP + 6;
const LIFT_TICKS = 12;
const LIFT_RISE = 0.3;
const SHAKE_TICKS = 60;
const SHAKE = 0.15;
const FLY_DELAY = 18;
const FLY_TICKS = 30;
const FLY_HEIGHT = 3;
const BOOST_DELAY = 30;
const BOOST_TICKS = 36;
const BOOST_HEIGHT = 50;
const LAUNCH_TICKS = LIFT_AT + BOOST_DELAY + BOOST_TICKS;
// Painting (the look's choice, from the feature's picture)
const RED = new THREE.Color(0xe32b2f);
const NOSE_TIP = new THREE.Color(0xf4e9ee);
const RIM = new THREE.Color(0xb9c3cc);
const GLASS = new THREE.Color(0x5fe6ff);
const WHITE = new THREE.Color(0xf6f6f8);
const FIN = new THREE.Color(0x9ba4ae);
const PORTHOLE_AT = 0.42;
const GLASS_RADIUS = 0.15;
const RIM_RADIUS = 0.28;
const NOSE_TIP_FROM = 0.86;
const FIN_FROM = 0.49;
const LIGHT = 0x22c4f0;
const CORE = 0xb8fbff;
const TILE_OPACITY = 0.3;
const CORE_OPACITY = 0.55;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const turn = new THREE.Quaternion();
const tilt = new THREE.Quaternion();
const STRAIGHT = new THREE.Quaternion();
const UP = new THREE.Vector3(0, 1, 0);
const SIDE = new THREE.Vector3(0, 0, 1);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

function outQuart(u) {
  return 1 - (1 - u) ** 4;
}

function outQuad(u) {
  return 1 - (1 - u) * (1 - u);
}

function inQuart(u) {
  return u ** 4;
}

// The two halves with their node transforms baked in, turned so the rocket's nose points along +x and its porthole up
// (+y): in the prefab the nose points along -x and the porthole along +z. Each half is set with its joint face (where
// it meets the other half) at the origin, the body's axis on the x axis, and 1 unit across
function halvesOf(gltf) {
  gltf.scene.updateMatrixWorld(true);
  const geometries = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      geometries.push(node.geometry.clone().applyMatrix4(node.matrixWorld));
    }
  });
  const turnAround = new THREE.Matrix4().set(-1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1);
  const [nose, rear] = geometries.map((geometry) => geometry.applyMatrix4(turnAround));
  // The body's axis: the nose is round, so its width across gives the radius and its underside the axis's height
  const noseBox = new THREE.Box3().setFromBufferAttribute(nose.attributes.position);
  const rearBox = new THREE.Box3().setFromBufferAttribute(rear.attributes.position);
  const across = noseBox.max.z - noseBox.min.z;
  const axisY = noseBox.min.y + across / 2;
  const axisZ = (noseBox.max.z + noseBox.min.z) / 2;
  nose.translate(-noseBox.min.x, -axisY, -axisZ);
  rear.translate(-rearBox.max.x, -axisY, -axisZ);
  nose.scale(1 / across, 1 / across, 1 / across);
  rear.scale(1 / across, 1 / across, 1 / across);
  return { nose: paint(nose, paintNose), rear: paint(rear, paintRear) };
}

function paint(geometry, colorOf) {
  const position = geometry.attributes.position;
  const colors = new Float32Array(position.count * 3);
  const point = new THREE.Vector3();
  for (let i = 0; i < position.count; i++) {
    point.fromBufferAttribute(position, i);
    const color = colorOf(point);
    colors.set([color.r, color.g, color.b], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

// The nose: red with a pale tip, and on top a porthole, a grey rim round cyan glass (in the nose's units: the body is
// 1 across, the porthole's middle 0.42 from the joint)
function paintNose(point) {
  const fromPorthole = Math.hypot(point.x - PORTHOLE_AT, point.z);
  if (point.y > 0.3 && fromPorthole < GLASS_RADIUS) {
    return GLASS;
  }
  if (point.y > 0.3 && fromPorthole < RIM_RADIUS && Math.hypot(point.y, point.z) > 0.5) {
    return RIM;
  }
  return point.x > NOSE_TIP_FROM ? NOSE_TIP : RED;
}

// The rear: a white body with a red band at the joint and a red base, its three fins (whatever stands out of the round
// body away from the joint) grey
function paintRear(point) {
  if (point.x < -0.25 && Math.hypot(point.y, point.z) > FIN_FROM) {
    return FIN;
  }
  if (point.x > -0.12 || point.x < -0.86) {
    return RED;
  }
  return WHITE;
}

class RocketLook {
  constructor(halves, scene) {
    this.records = [];
    this.fading = [];
    this.now = 0;
    this.cell = 0;
    this.grid = null;
    const body = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0.05 });
    this.noses = new THREE.InstancedMesh(halves.nose, body, ROCKETS);
    this.rears = new THREE.InstancedMesh(halves.rear, body, ROCKETS);
    const block = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
    const glow = (color, opacity) =>
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
    this.tiles = new THREE.InstancedMesh(block, glow(LIGHT, TILE_OPACITY), TILES + FADING);
    this.cores = new THREE.InstancedMesh(block, glow(CORE, CORE_OPACITY), TILES + FADING);
    this.meshes = [this.noses, this.rears, this.tiles, this.cores];
    for (const mesh of this.meshes) {
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(mesh);
    }
    this.tiles.renderOrder = 2;
    this.cores.renderOrder = 1;
  }

  // A new level (or a rebuild partway through one): every rocket as it stands now
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    this.grid = grid;
    this.cell = grid.size / L_PER_UNIT;
    this.now = state.tick;
    mine.rockets.slice(0, ROCKETS).forEach((rocket, index) => {
      const corners = rocket.slices.map((cells) => this.middleOf(cells));
      this.records.push({
        index,
        rocket,
        corners,
        width: Math.sqrt(rocket.area) * this.cell,
        start: { from: rocket.start, to: rocket.start, t0: -1e9, punchAt: -1e9 },
        end: { from: rocket.end, to: rocket.end, t0: -1e9, punchAt: -1e9 },
        path: new Set(state.grid.targets[rocket.path].cells),
        launchAt: rocket.launched ? -1e9 : null,
      });
    });
  }

  // A slice's middle on the picture, in world units
  middleOf(cells) {
    const { grid } = this;
    let x = 0;
    let y = 0;
    for (const cell of cells) {
      x += cell % grid.width;
      y += Math.floor(cell / grid.width);
    }
    x /= cells.length;
    y /= cells.length;
    return new THREE.Vector2((x - (grid.width - 1) / 2) * this.cell, -(y - (grid.height - 1) / 2) * this.cell);
  }

  clear() {
    this.records = [];
    this.fading = [];
    for (const mesh of this.meshes) {
      mesh.count = 0;
    }
  }

  onEvents(events, state) {
    for (const event of events) {
      if (event.k === "rocket_move") {
        this.moved(event, state);
      } else if (event.k === "rocket_launch") {
        this.launched(event);
      }
    }
  }

  moved(event, state) {
    const record = this.records[event.rocket];
    if (!record) {
      return;
    }
    for (const [key, part] of [
      ["start", START],
      ["end", END],
    ]) {
      const shown = record[key];
      if (shown.to !== event[key]) {
        shown.from = this.indexOf(shown);
        shown.to = event[key];
        shown.t0 = event.t;
      }
      if (event.part === part) {
        shown.punchAt = event.t;
      }
    }
    sound(event.part === END ? "rocket_front_hit" : "rocket_rear_hit");
    this.sinkPath(record, new Set(state.grid.targets[record.rocket.path].cells), event.t);
  }

  launched(event) {
    const record = this.records[event.rocket];
    if (!record) {
      return;
    }
    record.start.from = this.indexOf(record.start);
    record.end.from = this.indexOf(record.end);
    record.start.to = event.start;
    record.end.to = event.end;
    record.launchAt = event.t;
    this.sinkPath(record, new Set(), event.t);
    sound("rocket_merge");
  }

  // Path cells the simulation no longer covers shrink away where they stood
  sinkPath(record, cells, t) {
    for (const cell of record.path) {
      if (!cells.has(cell)) {
        this.fading.push({ record, cell, t0: t });
      }
    }
    if (this.fading.length > FADING) {
      this.fading.splice(0, this.fading.length - FADING);
    }
    record.path = cells;
  }

  // Where along the path a part is drawn now, in slices (fractions between two)
  indexOf(shown) {
    const u = outQuart(clamp01((this.now - shown.t0) / SLIDE_TICKS));
    return shown.from + (shown.to - shown.from) * u;
  }

  // A point and the heading along the path at a fractional slice index
  along(record, index) {
    const { corners } = record;
    const last = corners.length - 1;
    const at = Math.min(last, Math.max(0, index));
    const low = Math.floor(at);
    const high = Math.min(last, low + 1);
    const point = corners[low].clone().lerp(corners[high], at - low);
    const before = corners[Math.max(0, Math.min(low, high - 1))];
    const after = corners[Math.max(high, Math.min(last, low + 1))];
    const heading = after.clone().sub(before);
    if (heading.lengthSq() === 0 && last > 0) {
      heading.copy(corners[last]).sub(corners[0]);
    }
    return { point, yaw: Math.atan2(-heading.y, heading.x) };
  }

  // One half's matrix: at a slice, facing along the path, its joint face half the part's width toward the other half
  halfMatrix(record, index, toward, swell) {
    const { point, yaw } = this.along(record, index);
    const reach = (record.width / 2) * toward;
    const scale = record.width * FIT * swell;
    place.set(point.x + Math.cos(yaw) * reach, scale / 2, point.y - Math.sin(yaw) * reach);
    turn.setFromAxisAngle(UP, yaw);
    size.set(scale, scale, scale);
    return matrix.compose(place, turn, size);
  }

  // A rocket before its launch: both halves where their slide has them
  drawResting(record, at) {
    const swellOf = (shown) => 1 + PUNCH * Math.sin(Math.PI * clamp01((this.now - shown.punchAt) / PUNCH_TICKS));
    this.rears.setMatrixAt(at.parts, this.halfMatrix(record, this.indexOf(record.start), 1, swellOf(record.start)));
    this.noses.setMatrixAt(at.parts, this.halfMatrix(record, this.indexOf(record.end), -1, swellOf(record.end)));
    at.parts += 1;
  }

  // The launch: the halves slide together along the path, the joined rocket swells, turns nose up, shakes, rises and
  // boosts away
  drawLaunch(record, at) {
    const t = this.now - record.launchAt;
    if (t >= LAUNCH_TICKS) {
      return;
    }
    const merge = t < MERGE_APPROACH
      ? MERGE_SHARE * outQuad(t / MERGE_APPROACH)
      : MERGE_SHARE + (1 - MERGE_SHARE) * outQuad(clamp01((t - MERGE_APPROACH) / MERGE_SNAP));
    const gap = Math.sqrt(record.rocket.area);
    const middle = (record.start.to + record.end.to) / 2;
    const rearIndex = record.start.from + (middle - gap / 2 - record.start.from) * merge;
    const noseIndex = record.end.from + (middle + gap / 2 - record.end.from) * merge;
    const punch = 1 + MERGE_PUNCH * Math.sin(Math.PI * clamp01((t - MERGE_APPROACH - MERGE_SNAP) / MERGE_PUNCH_TICKS)) *
      (1 - clamp01((t - MERGE_APPROACH - MERGE_SNAP) / MERGE_PUNCH_TICKS));
    const rear = this.halfMatrix(record, rearIndex, 1, punch).clone();
    const nose = this.halfMatrix(record, noseIndex, -1, punch).clone();
    if (t >= LIFT_AT) {
      this.lift(record, middle, t - LIFT_AT, punch, rear, nose);
    }
    this.rears.setMatrixAt(at.parts, rear);
    this.noses.setMatrixAt(at.parts, nose);
    at.parts += 1;
  }

  // After the merge: both halves turn about the joint until the nose points up, then the rocket rises
  lift(record, middle, t, punch, rear, nose) {
    const { point, yaw } = this.along(record, middle);
    const scale = record.width * FIT * punch;
    const shake = t < SHAKE_TICKS ? SHAKE * scale * (1 - t / SHAKE_TICKS) : 0;
    const rise =
      LIFT_RISE * outQuad(clamp01(t / LIFT_TICKS)) +
      FLY_HEIGHT * inQuart(clamp01((t - FLY_DELAY) / FLY_TICKS)) +
      BOOST_HEIGHT * clamp01((t - BOOST_DELAY) / BOOST_TICKS);
    const jitter = Math.sin(t * 2.7) * shake;
    turn.setFromAxisAngle(UP, yaw);
    tilt.setFromAxisAngle(SIDE, (Math.PI / 2) * outQuad(clamp01(t / LIFT_TICKS)));
    turn.multiply(tilt);
    size.set(scale, scale, scale);
    place.set(point.x + jitter, scale / 2 + rise, point.y + Math.cos(t * 3.1) * shake);
    rear.compose(place, turn, size);
    nose.compose(place, turn, size);
  }

  // The light path: a glowing block and a flickering core on every cell it covers, and the cells shrinking away
  drawPath(at) {
    const { grid } = this;
    const cell = this.cell;
    const block = (record, index, height) => {
      const x = (index % grid.width) - (grid.width - 1) / 2;
      const y = Math.floor(index / grid.width) - (grid.height - 1) / 2;
      const tall = record.width * TILE_TALL * height;
      place.set(x * cell, 0, -y * cell);
      size.set(cell * TILE_FILL * height, tall, cell * TILE_FILL * height);
      this.tiles.setMatrixAt(at.tiles, matrix.compose(place, STRAIGHT, size));
      at.tiles += 1;
      const flicker = 1 - CORE_FLICKER * (0.5 + 0.5 * Math.sin(this.now * 0.9 + index * 2.3));
      size.set(cell * CORE_FILL * height, tall * CORE_TALL * flicker + tall * 0.05, cell * CORE_FILL * height);
      place.y = tall * 0.25;
      this.cores.setMatrixAt(at.cores, matrix.compose(place, STRAIGHT, size));
      at.cores += 1;
    };
    for (const record of this.records) {
      const covered = this.partCellsShown(record);
      for (const index of record.path) {
        if (at.tiles < TILES && !covered.has(index)) {
          block(record, index, 1);
        }
      }
    }
    this.fading = this.fading.filter((piece) => this.now - piece.t0 < SINK_TICKS);
    for (const piece of this.fading) {
      block(piece.record, piece.cell, 1 - clamp01((this.now - piece.t0) / SINK_TICKS));
    }
  }

  // The parts' cells as the simulation has them, where the path never draws (a rocket whose path is only its parts)
  partCellsShown(record) {
    const parts = this.grid.targets[record.rocket.parts];
    return new Set(parts.cells);
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.records.length) {
      return;
    }
    const at = { parts: 0, tiles: 0, cores: 0 };
    for (const record of this.records) {
      if (record.launchAt === null) {
        this.drawResting(record, at);
      } else {
        this.drawLaunch(record, at);
      }
      this.soundLaunch(record);
    }
    this.drawPath(at);
    this.noses.count = at.parts;
    this.rears.count = at.parts;
    this.tiles.count = at.tiles;
    this.cores.count = at.cores;
    for (const mesh of this.meshes) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  }

  // The lift-off and the boost sound when the launch reaches them
  soundLaunch(record) {
    if (record.launchAt === null) {
      return;
    }
    const t = this.now - record.launchAt;
    const step = record.soundStep ?? 0;
    if (step === 0 && t >= LIFT_AT && t < LIFT_AT + SINK_TICKS) {
      sound("rocket_lift_off");
      record.soundStep = 1;
    } else if (step <= 1 && t >= LIFT_AT + BOOST_DELAY && t < LIFT_AT + BOOST_DELAY + SINK_TICKS) {
      sound("rocket_boost");
      record.soundStep = 2;
    }
  }
}

// Load the model and add the pool of rockets and light path blocks to the scene
export async function create(scene) {
  const gltf = await new GLTFLoader().loadAsync(MODEL);
  return new RocketLook(halvesOf(gltf), scene);
}
