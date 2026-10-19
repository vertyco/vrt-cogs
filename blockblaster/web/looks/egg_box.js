// Feature 10, the Egg Box: a cardboard tray stands on the box's cells with the eggs sitting in it, each egg tinted to
// its color. An egg cracks as it is shot (a dark crack drawing laid over the shell at 0.1%, 50% and 80% of its health
// gone, the original's `eggBreakMaterialByPercents`), hops when a shot lands (jump 0.3, 0.2 s) and pops away when it
// breaks; the tray gives a small punch on every hit (0.05 over 0.1 s) and shrinks away when the last egg is gone.
// The three prefabs are `models/features/egg_box_model_4_2x2_variant.glb` (four eggs), `..._6_3x2_variant.glb` and
// `..._6_2x3_variant.glb` (six), picked by the box's EggArea. The prefabs come with no textures, so the tray is
// cardboard-colored and the cracks are drawn here; each egg's own node (`Egg_i`, in file order) is where egg i sits.
// The prefabs are in the original's left-handed numbers, so z is flipped on the way in. Everything comes from the
// simulation's egg box records (sim/features/egg_box.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { COLORS } from "../picture.js";
import { NUMBER } from "../sim/features/egg_box.js";
import { L_PER_UNIT } from "../sim/numbers.js";
import { play as sound } from "../sound.js";

export { NUMBER };

// [EggArea x, EggArea y] -> model, shadow
const VARIANTS = [
  { area: [2, 2], model: "models/features/egg_box_model_4_2x2_variant.glb", shadow: "art/effects/Shadow_Eggbox2x2.png" },
  { area: [3, 2], model: "models/features/egg_box_model_6_3x2_variant.glb", shadow: "art/effects/Shadow_Eggbox3x2.png" },
  { area: [2, 3], model: "models/features/egg_box_model_6_2x3_variant.glb", shadow: "art/effects/Shadow_Eggbox2x3.png" },
];
// The most boxes one level holds is 16 and the most eggs 64
const BOXES = 16;
const EGGS = 96;

// A cell is 0.5 wide in the prefabs, a box covers its EggArea in cells. The tray's height grows by this share of each
// extra EggArea it spans, the original's `areaScaleIncrement`
const MESH_CELL = 0.5;
const AREA_INCREMENT = 0.5;
// How much of an egg's health must be gone before each crack drawing shows (EggBoxModel.eggBreakMaterialByPercents)
const STAGE_FROM = [0.001, 0.5, 0.8];
// The crack overlay is a shell a hair larger than the egg (the prefab's EggBreak nodes, 0.49 against 0.4837)
const SHELL = 0.49 / 0.4837445;
const CARDBOARD = new THREE.Color(0xc79a62);
// Timings in ticks: an egg's hop after a hit (0.2 s), the tray's punch (0.1 s), an egg's pop when it breaks, and the
// tray shrinking away when its last egg is gone
const HOP_TICKS = 12;
const HOP_HEIGHT = 0.3;
const PUNCH_TICKS = 6;
const PUNCH = 0.05;
const POP_TICKS = 9;
const GONE_TICKS = 12;
// The shadow: its size against the tray's footprint, how far its middle sits toward the lower right (shares of its
// size), and how dark it is
const SHADOW_WIDE = 1.12;
const SHADOW_SHIFT_X = 0.08;
const SHADOW_SHIFT_Z = 0.1;
const SHADOW_OPACITY = 0.28;
const SHADOW_LIFT = 0.004;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const STRAIGHT = new THREE.Quaternion();
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);
const WHITE = new THREE.Color(0xffffff);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The crack drawing an egg of this color count shows: 0 whole, 1 to 3 more cracked
export function stageOf(health, count) {
  const gone = (count - health) / count;
  let stage = 0;
  for (let i = 0; i < STAGE_FROM.length; i++) {
    if (gone >= STAGE_FROM[i]) {
      stage = i + 1;
    }
  }
  return stage;
}

// The same geometry in the page's right-handed world: z flipped, triangles turned back to face outward
function flipZ(geometry) {
  const at = geometry.attributes.position;
  const normal = geometry.attributes.normal;
  for (let i = 0; i < at.count; i++) {
    at.setZ(i, -at.getZ(i));
    normal.setZ(i, -normal.getZ(i));
  }
  const index = geometry.index;
  for (let i = 0; i < index.count; i += 3) {
    const second = index.getX(i + 1);
    index.setX(i + 1, index.getX(i + 2));
    index.setX(i + 2, second);
  }
  at.needsUpdate = true;
  normal.needsUpdate = true;
  index.needsUpdate = true;
  return geometry;
}

// One prefab: the tray's geometry (node transform baked), the egg geometry (rotation and scale baked, its own spot
// left to the instance) and where each egg sits
function readModel(gltf) {
  gltf.scene.updateMatrixWorld(true);
  let tray = null;
  let egg = null;
  const spots = [];
  gltf.scene.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    if (node.name.startsWith("Eggbox")) {
      tray = flipZ(node.geometry.clone().applyMatrix4(node.matrixWorld));
    } else if (node.name.startsWith("Egg_")) {
      spots.push([node.position.x, node.position.y, -node.position.z]);
      if (egg === null) {
        const turn = new THREE.Matrix4().compose(new THREE.Vector3(), node.quaternion, node.scale);
        egg = flipZ(node.geometry.clone().applyMatrix4(turn));
      }
    }
  });
  tray.deleteAttribute("uv");
  tray.computeBoundingBox();
  egg.computeBoundingBox();
  return { tray, egg, spots };
}

// A canvas of cracks laid over the egg's own picture (the egg's UVs are a flat front view of it), growing with the
// stage; the same drawing on every egg
function crackMap(stage) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  let seed = 7 + stage * 31;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  const crack = (x, y, angle, length, width) => {
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(x, y);
    const steps = Math.max(3, Math.round(length / 14));
    for (let i = 0; i < steps; i++) {
      angle += (random() - 0.5) * 1.3;
      x += Math.cos(angle) * (length / steps);
      y += Math.sin(angle) * (length / steps);
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  };
  const starts = [
    [128, 118],
    [92, 92],
    [168, 150],
    [112, 176],
    [158, 84],
    [130, 214],
    [70, 140],
    [186, 110],
  ];
  const counts = [0, 3, 6, 8];
  const lengths = [0, 44, 66, 84];
  const widths = [0, 3.2, 4.2, 5.2];
  for (let i = 0; i < counts[stage]; i++) {
    const [x, y] = starts[i];
    ctx.strokeStyle = "rgba(48, 30, 22, 0.92)";
    crack(x, y, random() * Math.PI * 2, lengths[stage] * (0.7 + random() * 0.6), widths[stage]);
    ctx.strokeStyle = "rgba(255, 244, 228, 0.55)";
    crack(x + 1.5, y + 1.5, random() * Math.PI * 2, lengths[stage] * 0.4, widths[stage] * 0.4);
  }
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  return map;
}

function instanced(geometry, material, capacity) {
  const mesh = new THREE.InstancedMesh(geometry, material, capacity);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  mesh.count = 0;
  return mesh;
}

// The shadow's rectangle and its card geometry are shared; this makes one batch of cards for one variant
function shadowBatch(map) {
  const flat = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI);
  return instanced(
    flat,
    new THREE.MeshBasicMaterial({
      map,
      color: 0x000000,
      transparent: true,
      opacity: SHADOW_OPACITY,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
    }),
    BOXES,
  );
}

class EggBoxLook {
  constructor(variants, eggGeometry, scene) {
    this.variants = variants;
    this.records = [];
    this.now = 0;
    this.shown = "";
    // Every variant has its own tray geometry and shadow; the eggs and their crack shells are shared
    for (const variant of variants) {
      variant.trays = instanced(variant.tray, new THREE.MeshStandardMaterial({ color: CARDBOARD, roughness: 0.8 }), BOXES);
      variant.shadows = shadowBatch(variant.shadow);
      scene.add(variant.trays, variant.shadows);
    }
    this.eggs = instanced(eggGeometry, new THREE.MeshStandardMaterial({ roughness: 0.32 }), EGGS);
    this.eggs.setColorAt(0, WHITE);
    scene.add(this.eggs);
    // One shell batch per crack drawing
    this.shells = [1, 2, 3].map((stage) => {
      const material = new THREE.MeshStandardMaterial({
        map: crackMap(stage),
        transparent: true,
        roughness: 0.4,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
      });
      const mesh = instanced(eggGeometry, material, EGGS);
      scene.add(mesh);
      return mesh;
    });
  }

  // A new level: every box laid out in world units
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    const cell = grid.size / L_PER_UNIT;
    const listed = state.level.features.eggBoxes.EggBoxes;
    const used = new Map(this.variants.map((variant) => [variant, 0]));
    let eggs = 0;
    mine.boxes.forEach((box, index) => {
      const data = listed[index];
      const variant = this.variants.find((v) => v.area[0] === data.EggArea.X && v.area[1] === data.EggArea.Y);
      if (!variant || box.cells.length === 0 || used.get(variant) >= BOXES || eggs + box.eggs.length > EGGS) {
        return;
      }
      const record = this.layout(grid, cell, box, data, variant);
      record.slot = used.get(variant);
      record.first = eggs;
      used.set(variant, record.slot + 1);
      eggs += box.eggs.length;
      this.records.push(record);
    });
    this.now = state.tick;
    for (const record of this.records) {
      record.eggs.forEach((egg) => {
        const target = grid.targets[egg.id];
        egg.stage = stageOf(target.health, egg.count);
        egg.heard = egg.stage;
        egg.dead = target.dead;
        egg.hitAt = -Infinity;
        egg.deadAt = target.dead ? -Infinity : null;
      });
      record.goneAt = record.box.gone ? -Infinity : null;
    }
    this.shown = "";
    this.write(state, true);
  }

  // One box's fixed numbers: the world position and scale of its tray and where each egg sits
  layout(grid, cell, box, data, variant) {
    const xs = data.GridPoints.map((p) => p.X);
    const ys = data.GridPoints.map((p) => p.Y);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys);
    const wide = x1 - x0 + 1;
    const high = y1 - y0 + 1;
    const bounds = variant.tray.boundingBox;
    const sx = (wide * cell) / (bounds.max.x - bounds.min.x);
    const sz = (high * cell) / (bounds.max.z - bounds.min.z);
    const k = Math.max(wide / variant.area[0], high / variant.area[1]);
    const sy = (cell / MESH_CELL) * (1 + (k - 1) * AREA_INCREMENT);
    const centerX = ((x0 + x1) / 2 - (grid.width - 1) / 2) * cell;
    const centerZ = -((y0 + y1) / 2 - (grid.height - 1) / 2) * cell;
    // The prefab's own middle, so a tray that is not centered on its origin still lands on its cells
    const middleX = (bounds.min.x + bounds.max.x) / 2;
    const middleZ = (bounds.min.z + bounds.max.z) / 2;
    return {
      box,
      variant,
      sx,
      sy,
      sz,
      baseX: centerX - middleX * sx,
      baseZ: centerZ - middleZ * sz,
      centerX,
      centerZ,
      wide: wide * cell,
      high: high * cell,
      eggScale: Math.min(sx, sz),
      eggs: box.eggs.map((id, i) => ({ id, count: data.Eggs[i].Count, spot: variant.spots[i] || variant.spots[0] })),
      punchAt: -Infinity,
      goneAt: null,
    };
  }

  clear() {
    this.records = [];
    for (const variant of this.variants) {
      variant.trays.count = 0;
      variant.shadows.count = 0;
    }
    this.eggs.count = 0;
    for (const shell of this.shells) {
      shell.count = 0;
    }
    this.shown = "";
  }

  onEvents(events, state) {
    for (const event of events) {
      if (event.k === "hit") {
        this.onHit(event, state);
      } else if (event.k === "target_died" && event.owner === NUMBER) {
        this.onBreak(event);
      } else if (event.k === "egg_box_gone") {
        const record = this.records.find((r) => r.box.cells[0] === event.cells[0]);
        if (record && record.goneAt === null) {
          record.goneAt = event.t;
        }
      }
    }
  }

  find(targetId) {
    for (const record of this.records) {
      const egg = record.eggs.find((e) => e.id === targetId);
      if (egg) {
        return [record, egg];
      }
    }
    return null;
  }

  onHit(event) {
    const found = this.find(event.target);
    if (!found) {
      return;
    }
    const [record, egg] = found;
    egg.hitAt = event.t;
    record.punchAt = event.t;
    const stage = stageOf(event.health, egg.count);
    if (event.health > 0 && stage !== egg.heard) {
      sound("egg_change");
    }
    egg.heard = stage;
  }

  onBreak(event) {
    const found = this.find(event.target);
    if (!found) {
      return;
    }
    const egg = found[1];
    egg.dead = true;
    egg.deadAt = event.t;
    sound("egg_break");
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.records.length) {
      return;
    }
    this.write(state, false);
  }

  // How big an egg is now (1 whole, a short swell and shrink as it breaks, 0 once gone) and how high it has hopped
  eggPose(egg) {
    if (egg.dead) {
      if (egg.deadAt === null) {
        return [0, 0];
      }
      const u = clamp01((this.now - egg.deadAt) / POP_TICKS);
      return [u >= 1 ? 0 : u < 0.3 ? 1 + 0.25 * (u / 0.3) : 1.25 * (1 - (u - 0.3) / 0.7), 0];
    }
    const u = clamp01((this.now - egg.hitAt) / HOP_TICKS);
    return [1, u >= 1 ? 0 : Math.sin(Math.PI * u) * HOP_HEIGHT];
  }

  // The tray's size now: 1, a small punch after a hit, shrinking to 0 once the box is gone
  trayScale(record) {
    if (record.goneAt !== null) {
      const u = clamp01((this.now - record.goneAt) / GONE_TICKS);
      return 1 - u * u;
    }
    const u = clamp01((this.now - record.punchAt) / PUNCH_TICKS);
    return u >= 1 ? 1 : 1 + PUNCH * Math.sin(Math.PI * u);
  }

  // Take the simulation's eggs as they are, so a simulation rebuilt under the look still draws right
  sync(state, record) {
    for (const egg of record.eggs) {
      const target = state.grid.targets[egg.id];
      egg.stage = stageOf(target.health, egg.count);
      if (target.dead && !egg.dead) {
        egg.dead = true;
        egg.deadAt = -Infinity;
      } else if (!target.dead && egg.dead) {
        egg.dead = false;
        egg.deadAt = null;
      }
    }
    if (!record.box.gone) {
      record.goneAt = null;
    } else if (record.goneAt === null) {
      record.goneAt = -Infinity;
    }
  }

  // Everything at its pose now. Nothing moves in a long still stretch, so the batches are written only while
  // something animates or a stage or a death changed
  write(state, force) {
    let moving = false;
    const key = [];
    for (const record of this.records) {
      this.sync(state, record);
      moving = moving || this.now - record.punchAt <= PUNCH_TICKS + 1;
      moving = moving || (record.goneAt !== null && this.now - record.goneAt <= GONE_TICKS + 1);
      for (const egg of record.eggs) {
        moving = moving || this.now - egg.hitAt <= HOP_TICKS + 1;
        moving = moving || (egg.deadAt !== null && this.now - egg.deadAt <= POP_TICKS + 1);
        key.push(egg.stage * 2 + (egg.dead ? 1 : 0));
      }
    }
    const shown = key.join("");
    if (!force && !moving && shown === this.shown) {
      return;
    }
    this.shown = shown;
    this.fill(state);
  }

  fill(state) {
    for (const variant of this.variants) {
      variant.trays.count = 0;
      variant.shadows.count = 0;
    }
    let eggCount = 0;
    const shellCount = [0, 0, 0];
    for (const record of this.records) {
      const variant = record.variant;
      const grow = this.trayScale(record);
      const slot = variant.trays.count;
      variant.trays.count += 1;
      variant.shadows.count += 1;
      if (grow <= 0) {
        variant.trays.setMatrixAt(slot, HIDDEN);
        variant.shadows.setMatrixAt(slot, HIDDEN);
      } else {
        place.set(record.baseX, 0, record.baseZ);
        variant.trays.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(record.sx * grow, record.sy * grow, record.sz * grow)));
        const across = record.wide * SHADOW_WIDE * grow;
        const along = record.high * SHADOW_WIDE * grow;
        place.set(
          record.centerX + across * SHADOW_SHIFT_X,
          SHADOW_LIFT,
          record.centerZ + along * SHADOW_SHIFT_Z,
        );
        variant.shadows.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(across, 1, along)));
      }
      for (const egg of record.eggs) {
        const [scale, hop] = this.eggPose(egg);
        const index = eggCount++;
        if (scale <= 0 || grow <= 0) {
          this.eggs.setMatrixAt(index, HIDDEN);
          continue;
        }
        place.set(
          record.baseX + egg.spot[0] * record.sx * grow,
          (egg.spot[1] + hop) * record.sy * grow,
          record.baseZ + egg.spot[2] * record.sz * grow,
        );
        const big = record.eggScale * grow * scale;
        const tall = record.sy * grow * scale;
        this.eggs.setMatrixAt(index, matrix.compose(place, STRAIGHT, size.set(big, tall, big)));
        this.eggs.setColorAt(index, COLORS[state.grid.targets[egg.id].color]);
        if (egg.stage > 0) {
          const shell = egg.stage - 1;
          this.shells[shell].setMatrixAt(shellCount[shell]++, matrix.compose(place, STRAIGHT, size.set(big * SHELL, tall * SHELL, big * SHELL)));
        }
      }
    }
    for (const variant of this.variants) {
      variant.trays.instanceMatrix.needsUpdate = true;
      variant.shadows.instanceMatrix.needsUpdate = true;
    }
    this.eggs.count = eggCount;
    this.eggs.instanceMatrix.needsUpdate = true;
    if (this.eggs.instanceColor) {
      this.eggs.instanceColor.needsUpdate = true;
    }
    this.shells.forEach((shell, i) => {
      shell.count = shellCount[i];
      shell.instanceMatrix.needsUpdate = true;
    });
  }
}

// Load the three prefabs and their shadows, and add the pools to the scene
export async function create(scene) {
  const loader = new GLTFLoader();
  const textures = new THREE.TextureLoader();
  const variants = await Promise.all(
    VARIANTS.map(async (variant) => {
      const [gltf, shadow] = await Promise.all([loader.loadAsync(variant.model), textures.loadAsync(variant.shadow)]);
      shadow.colorSpace = THREE.SRGBColorSpace;
      return { ...variant, ...readModel(gltf), shadow };
    }),
  );
  // The eggs are the same mesh in every prefab, so the first one's serves them all
  return new EggBoxLook(variants, variants[0].egg, scene);
}
