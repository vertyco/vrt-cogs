// Feature 8, the Snake: a head, body pieces and a tail of the snake's color laid end to end along its path, the tail
// resting in the nest (a dark patch under the nest square) and the head at the body's far end, facing away from the
// nest. Every hit pulls the head back along the path toward the nest over 0.3 s (the original tweens its spline clip
// to the new health with OutBack, SnakeFeature clipPercentDuration 0.3 and clipPercentEase 27); the body pieces keep
// their places behind the head, so the body slides into the nest. At no health the last of it slides in and it is
// gone. The pieces are `models/snake_head.glb`, `snake_body.glb` and `snake_tail.glb` (ASSETS.md), placed about 0.55
// apart. The drawing reads the simulation's snakes (sim/features/snake.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { mergeGeometries } from "../vendor/BufferGeometryUtils.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { COLORS } from "../picture.js";
import { NUMBER, clipPercent, squaresOf } from "../sim/features/snake.js";
import { L_PER_UNIT } from "../sim/numbers.js";
import * as spline from "../sim/spline.js";
import { play as sound } from "../sound.js";

export { NUMBER };

const MODELS = ["models/snake_head.glb", "models/snake_body.glb", "models/snake_tail.glb"];
const NEST = "art/effects/Shadow_2x2_Circle.png";
// A level holds at most 7 snakes and 253 pieces in all (level 2358)
const SNAKES = 8;
const BODIES = 512;

// The clip's tween after a hit (0.3 s, OutBack)
const SHRINK_TICKS = 18;
const BACK = 1.70158;
// The pieces' spacing in model units, the body's width as a share of the nest's side, and how much flatter than round
// it stands (cubes are about one cell tall)
const SPACING = 0.55;
const WIDTH = 0.75;
const FLAT = 0.8;
// The nest patch's size against the nest square, and how dark it is
const NEST_SIZE = 1.25;
const NEST_OPACITY = 0.45;
// The share of the path a tangent is measured over
const STEP = 0.002;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const turn = new THREE.Quaternion();
const UP = new THREE.Vector3(0, 1, 0);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

function outBack(u) {
  const v = u - 1;
  return 1 + (BACK + 1) * v * v * v + BACK * v * v;
}

// Every vertex of a fixed-color part carries its material's color, so all of them share one batch
function paint(geometry, color) {
  const count = geometry.attributes.position.count;
  const colors = new Float32Array(count * 3);
  for (let v = 0; v < count; v++) {
    color.toArray(colors, v * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

// A model's meshes in the file's own space: the `Tint_*` parts merged into one geometry, the rest into another
function parts(gltf) {
  const tint = [];
  const marks = [];
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    const geometry = node.geometry.clone().toNonIndexed();
    geometry.applyMatrix4(node.matrixWorld);
    geometry.deleteAttribute("uv");
    if (node.name.startsWith("Tint_")) {
      tint.push(geometry);
    } else {
      paint(geometry, node.material.color);
      marks.push(geometry);
    }
  });
  const merged = { tint: mergeGeometries(tint), marks: marks.length ? mergeGeometries(marks) : null };
  merged.tint.computeBoundingBox();
  return merged;
}

function instanced(geometry, material, capacity) {
  const mesh = new THREE.InstancedMesh(geometry, material, capacity);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  mesh.count = 0;
  return mesh;
}

class SnakeLook {
  constructor(models, nestMap, scene) {
    this.now = 0;
    this.snakes = [];
    const capacities = [SNAKES, BODIES, SNAKES];
    // One batch pair per piece kind: head, body, tail
    this.kinds = models.map((model, i) => {
      const tint = instanced(model.tint, new THREE.MeshStandardMaterial({ roughness: 0.45 }), capacities[i]);
      tint.setColorAt(0, new THREE.Color(0xffffff));
      scene.add(tint);
      let marks = null;
      if (model.marks) {
        const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4 });
        marks = instanced(model.marks, material, capacities[i]);
        scene.add(marks);
      }
      // The models are centered; this lifts a piece so its bottom rests on the ground
      return { tint, marks, lift: -model.tint.boundingBox.min.y, used: 0 };
    });
    const nestMaterial = new THREE.MeshBasicMaterial({
      map: nestMap,
      color: 0x000000,
      transparent: true,
      opacity: NEST_OPACITY,
      depthWrite: false,
    });
    this.nests = [];
    for (let i = 0; i < SNAKES; i++) {
      const nest = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), nestMaterial);
      nest.rotation.x = -Math.PI / 2;
      nest.visible = false;
      scene.add(nest);
      this.nests.push(nest);
    }
  }

  // A new level: every snake's path laid out and drawn at its simulation's health
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    const cell = grid.size / L_PER_UNIT;
    const listed = state.level.features.snakes.Snakes;
    mine.snakes.slice(0, SNAKES).forEach((snake, index) => {
      const record = this.layout(grid, cell, snake, listed[index], index);
      this.snakes.push(record);
      this.settle(record, state);
    });
    this.now = state.tick;
    this.write();
  }

  // One snake's fixed numbers: its drawn path, how long it is, how big its pieces are and where its nest is
  layout(grid, cell, snake, data, index) {
    const squares = squaresOf(data);
    const path = spline.build(squares, spline.STRAIGHT_DISTANCE);
    let length = 0;
    for (let i = 1; i < path.samples.length; i++) {
      length += spline.distance(path.samples[i - 1], path.samples[i]);
    }
    const side = Math.sqrt(squares[0].length);
    const scale = (WIDTH * side * cell) / (this.kinds[1].tint.geometry.boundingBox.max.x * 2);
    const nest = spline.center(squares[0]);
    const record = {
      snake,
      index,
      path,
      cell,
      length: length * cell,
      scale,
      spacing: SPACING * scale,
      worldX: (x) => (x - (grid.width - 1) / 2) * cell,
      worldZ: (y) => -(y - (grid.height - 1) / 2) * cell,
      shown: 0,
      from: 0,
      to: 0,
      t0: -Infinity,
      dead: false,
    };
    const patch = this.nests[index];
    patch.position.set(record.worldX(nest[0]), 0.002, record.worldZ(nest[1]));
    patch.scale.set(side * cell * NEST_SIZE, side * cell * NEST_SIZE, 1);
    return record;
  }

  // Take the simulation's health as it is, with no tween
  settle(record, state) {
    const target = state.grid.targets[record.snake.target];
    record.to = clipPercent(target.health, record.snake.count);
    record.from = record.to;
    record.shown = record.to;
    record.t0 = -Infinity;
    record.dead = target.dead;
    record.color = COLORS[target.color];
  }

  clear() {
    this.snakes = [];
    for (const kind of this.kinds) {
      kind.tint.count = 0;
      if (kind.marks) {
        kind.marks.count = 0;
      }
    }
    for (const nest of this.nests) {
      nest.visible = false;
    }
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "snake_shrink") {
        sound("snake_pull");
      } else if (event.k === "target_died" && event.owner === NUMBER) {
        sound("snake_gone");
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.snakes.length) {
      return;
    }
    let moving = false;
    for (const record of this.snakes) {
      const target = state.grid.targets[record.snake.target];
      const to = clipPercent(target.health, record.snake.count);
      if (to !== record.to) {
        // A hit (or a rebuilt simulation): pull the head from where it is drawn to the new clip
        record.from = record.shown;
        record.to = to;
        record.t0 = this.now;
      }
      record.dead = target.dead;
      const u = clamp01((this.now - record.t0) / SHRINK_TICKS);
      record.shown = record.from + (record.to - record.from) * outBack(u);
      // One more drawing after the pull ends puts the head exactly at its clip (or hides a dead snake)
      moving = moving || this.now - record.t0 <= SHRINK_TICKS + 1;
    }
    if (moving) {
      this.write();
    }
  }

  // A point and the outward heading (away from the nest) t of the way along the path, in world units
  pose(record, t) {
    const [x, y] = spline.positionAt(record.path, clamp01(t));
    const [ax, ay] = spline.positionAt(record.path, clamp01(t - STEP));
    const [bx, by] = spline.positionAt(record.path, clamp01(t + STEP));
    place.set(record.worldX(x), 0, record.worldZ(y));
    // Picture y runs up the screen, world z down it
    return Math.atan2(ax - bx, -(ay - by));
  }

  write() {
    for (const kind of this.kinds) {
      kind.used = 0;
    }
    for (const record of this.snakes) {
      this.writeSnake(record);
    }
    for (const kind of this.kinds) {
      kind.tint.count = kind.used;
      kind.tint.instanceMatrix.needsUpdate = true;
      if (kind.tint.instanceColor) {
        kind.tint.instanceColor.needsUpdate = true;
      }
      if (kind.marks) {
        kind.marks.count = kind.used;
        kind.marks.instanceMatrix.needsUpdate = true;
      }
    }
  }

  // Head at the clip point, body pieces at fixed steps behind it while they are still out of the nest, tail in the
  // nest; a dead snake is drawn until its last pull ends
  writeSnake(record) {
    const gone = record.dead && this.now - record.t0 >= SHRINK_TICKS;
    this.nests[record.index].visible = !gone;
    if (gone) {
      return;
    }
    const out = (1 - record.shown) * record.length;
    this.piece(0, record, record.shown);
    for (let d = record.spacing; d < out - record.spacing * 0.5; d += record.spacing) {
      this.piece(1, record, record.shown + d / record.length);
    }
    this.piece(2, record, 1);
  }

  piece(kindIndex, record, t) {
    const kind = this.kinds[kindIndex];
    if (kind.used >= kind.tint.instanceMatrix.count) {
      return;
    }
    const yaw = this.pose(record, t);
    place.y = kind.lift * record.scale * FLAT;
    matrix.compose(place, turn.setFromAxisAngle(UP, yaw), size.set(record.scale, record.scale * FLAT, record.scale));
    kind.tint.setMatrixAt(kind.used, matrix);
    kind.tint.setColorAt(kind.used, record.color);
    if (kind.marks) {
      kind.marks.setMatrixAt(kind.used, matrix);
    }
    kind.used += 1;
  }
}

async function loadModel(url) {
  return parts(await new GLTFLoader().loadAsync(url));
}

// Load the three pieces and the nest patch, and add their pools to the scene
export async function create(scene) {
  const [models, nestMap] = await Promise.all([
    Promise.all(MODELS.map(loadModel)),
    new THREE.TextureLoader().loadAsync(NEST),
  ]);
  return new SnakeLook(models, nestMap, scene);
}
