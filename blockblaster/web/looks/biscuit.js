// Feature 16, Biscuits: an orange biscuit slab stands over its cubes, topped with a swirl of pink cream, a blueberry
// and a leaf (the original's `models/features/biscuit_feature.glb`: the slab, its broken twin, the cream, the berry,
// the berry's flower and the leaf; the prefab holds no materials, so the paint is the look's choice, taken from the
// feature's picture). The pool of LayerCount x LayerHealth hits is drawn as LayerCount stacked slabs, of which
// ceil(health / LayerHealth) stand, and each time one goes it breaks into the broken slab that rises, spins and
// shrinks away. Every hit makes the biscuit swell a little and ring (`biscuit_hit_no_click`), a layer breaking sounds `berry_explode_2`. The cream, berry and leaf ride
// on the top slab and shrink away when the biscuit is gone. Everything comes from the simulation's biscuit records
// (sim/features/biscuit.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { play as sound } from "../sound.js";
import { NUMBER } from "../sim/features/biscuit.js";
import { L_PER_UNIT } from "../sim/numbers.js";

export { NUMBER };

const MODEL = "models/features/biscuit_feature.glb";
const SHADOW = "art/effects/Shadow_IceBlock.png";
// The most biscuits one level holds is 33 (level 1355), each with at most 3 layers
const BISCUITS = 40;
const LAYERS = 128;
const DEBRIS = 96;
// The bottom layer is this many cube heights tall, so it covers the cubes under it; every layer above it is this many
const BASE_TALL = 1.1;
const UPPER_TALL = 0.3;
const FIT = 0.97;
// Each layer above the bottom one is this much narrower than the one under it, so the stack reads as tiers
const TAPER = 0.05;
// The cream, berry and leaf: how much of their true size against the slab they keep
const TOP_SHARE = 0.6;
// Painting (the look's choice): the slab's top, its sides, and the toppings
const SLAB_TOP = new THREE.Color(0xf6a24f);
const SLAB_SIDE = new THREE.Color(0xd9732b);
const CREAM = 0xf7c6e4;
const BERRY = 0x2f63e0;
const FLOWER = 0x2548c9;
const LEAF = 0x47c23a;
// A hit makes the biscuit swell this much and settle over this many ticks
const PUNCH = 0.05;
const PUNCH_TICKS = 9;
// A broken layer: how long it flies in ticks, how high it rises in cube heights, how far it swells and turns
const BREAK_TICKS = 30;
const BREAK_RISE = 1.6;
const BREAK_SWELL = 0.18;
const BREAK_TURN = 0.9;
// The shadow: against the biscuit's width, how far its middle sits toward the lower right (a share of its width), how
// dark it is
const SHADOW_WIDE = 1.12;
const SHADOW_SHIFT = 0.1;
const SHADOW_OPACITY = 0.22;
const SHADOW_LIFT = 0.004;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const turn = new THREE.Quaternion();
const spin = new THREE.Euler();
const STRAIGHT = new THREE.Quaternion();
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The six meshes with their node transforms baked in
function piecesOf(gltf) {
  gltf.scene.updateMatrixWorld(true);
  const geometries = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      geometries.push(node.geometry.clone().applyMatrix4(node.matrixWorld));
    }
  });
  return geometries;
}

// Colors on the slab: its top lighter than its sides
function paintSlab(geometry) {
  const normal = geometry.attributes.normal;
  const colors = new Float32Array(normal.count * 3);
  for (let i = 0; i < normal.count; i++) {
    const color = normal.getY(i) > 0.5 ? SLAB_TOP : SLAB_SIDE;
    colors.set([color.r, color.g, color.b], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

// The slab and its broken twin set on the floor with the middle of their footprint at the origin and one unit wide, deep
// and tall; the toppings set on the slab's top with their own middle at the origin, in the slab's own scale
function shapePieces(geometries) {
  const slabBox = new THREE.Box3().setFromBufferAttribute(geometries[0].attributes.position);
  const wide = slabBox.max.x - slabBox.min.x;
  const deep = slabBox.max.z - slabBox.min.z;
  const tall = slabBox.max.y - slabBox.min.y;
  const cx = (slabBox.max.x + slabBox.min.x) / 2;
  const cz = (slabBox.max.z + slabBox.min.z) / 2;
  const slabs = [geometries[0], geometries[1]].map((source) => {
    const geometry = source.clone();
    geometry.translate(-cx, -slabBox.min.y, -cz);
    geometry.scale(1 / wide, 1 / tall, 1 / deep);
    return geometry;
  });
  const toppings = geometries.slice(2);
  const topBox = new THREE.Box3();
  for (const geometry of toppings) {
    topBox.union(new THREE.Box3().setFromBufferAttribute(geometry.attributes.position));
  }
  const tx = (topBox.max.x + topBox.min.x) / 2;
  const tz = (topBox.max.z + topBox.min.z) / 2;
  const heaped = toppings.map((source) => {
    const geometry = source.clone();
    geometry.translate(-tx, -slabBox.max.y, -tz);
    geometry.scale(1 / wide, 1 / wide, 1 / wide);
    return geometry;
  });
  return { slabs: slabs.map(paintSlab), toppings: heaped };
}

// The layers still standing at this health: the pool is LayerCount slabs of LayerHealth hits each
function standingOf(record, health, dead) {
  if (dead) {
    return 0;
  }
  return Math.min(record.layers, Math.ceil(health / record.layerHealth));
}

// Where layer k of a biscuit starts and how thick it is
function layerStart(record, k) {
  return k === 0 ? 0 : record.base + (k - 1) * record.upper;
}

function layerThick(record, k) {
  return k === 0 ? record.base : record.upper;
}

class BiscuitLook {
  constructor(pieces, shadow, scene) {
    this.records = [];
    this.byTarget = new Map();
    this.debris = [];
    this.now = 0;
    this.cell = 0;
    this.height = 0;
    const slab = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0 });
    this.layers = new THREE.InstancedMesh(pieces.slabs[0], slab, LAYERS);
    this.broken = new THREE.InstancedMesh(pieces.slabs[1], slab, DEBRIS);
    this.toppings = [CREAM, BERRY, FLOWER, LEAF].map((color, index) => {
      const material = new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0 });
      return new THREE.InstancedMesh(pieces.toppings[index], material, BISCUITS);
    });
    this.shadows = new THREE.InstancedMesh(
      new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI),
      new THREE.MeshBasicMaterial({
        map: shadow,
        color: 0x000000,
        transparent: true,
        opacity: SHADOW_OPACITY,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1,
      }),
      BISCUITS,
    );
    this.meshes = [this.layers, this.broken, ...this.toppings, this.shadows];
    for (const mesh of this.meshes) {
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(mesh);
    }
  }

  // A new level: every biscuit laid over its cells, none of them broken
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    this.cell = grid.size / L_PER_UNIT;
    this.height = Math.min(this.cell, PICTURE_HEIGHT);
    this.now = state.tick;
    for (const biscuit of mine.biscuits.slice(0, BISCUITS)) {
      const body = grid.targets[biscuit.target];
      const xs = body.cells.map((c) => c % grid.width);
      const ys = body.cells.map((c) => Math.floor(c / grid.width));
      const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
      const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
      const record = {
        biscuit,
        layers: biscuit.layers,
        layerHealth: biscuit.layerHealth,
        w: maxX - minX + 1,
        h: maxY - minY + 1,
        x: ((minX + maxX) / 2 - (grid.width - 1) / 2) * this.cell,
        z: -((minY + maxY) / 2 - (grid.height - 1) / 2) * this.cell,
        base: this.height * BASE_TALL,
        upper: this.height * UPPER_TALL,
        shown: standingOf({ layers: biscuit.layers, layerHealth: biscuit.layerHealth }, body.health, body.dead),
        punchAt: -1e9,
        goneAt: body.dead ? -1e9 : null,
      };
      this.records.push(record);
      this.byTarget.set(biscuit.target, record);
    }
  }

  clear() {
    this.records = [];
    this.byTarget = new Map();
    this.debris = [];
    for (const mesh of this.meshes) {
      mesh.count = 0;
    }
  }

  onEvents(events, state) {
    for (const event of events) {
      if (event.k !== "hit") {
        continue;
      }
      const record = this.byTarget.get(event.target);
      if (record && state.grid.targets[event.target].owner === NUMBER && event.health > 0) {
        record.punchAt = event.t;
        sound("biscuit_hit");
      }
    }
  }

  // Layers that went since the last frame break off, the top one first
  breakLayers(record, standing) {
    if (standing >= record.shown) {
      return;
    }
    for (let k = record.shown - 1; k >= standing; k--) {
      this.debris.push({ t0: this.now, record, k, flip: (record.x * 7 + record.z * 3 + k) % 2 ? 1 : -1 });
    }
    if (this.debris.length > DEBRIS) {
      this.debris.splice(0, this.debris.length - DEBRIS);
    }
    sound("biscuit_break");
    record.shown = standing;
  }

  // The standing layers, the toppings and the shadow of one biscuit this frame; returns where the next instance goes
  drawBiscuit(record, state, at) {
    const body = state.grid.targets[record.biscuit.target];
    const standing = standingOf(record, body.health, body.dead);
    this.breakLayers(record, standing);
    if (standing === 0 && record.goneAt === null) {
      record.goneAt = this.now;
    }
    const swell = 1 + PUNCH * Math.sin(Math.PI * clamp01((this.now - record.punchAt) / PUNCH_TICKS));
    const wide = record.w * this.cell * FIT;
    const deep = record.h * this.cell * FIT;
    for (let k = 0; k < standing; k++) {
      place.set(record.x, layerStart(record, k) * swell, record.z);
      const narrow = 1 - TAPER * k;
      size.set(wide * narrow * swell, layerThick(record, k) * swell, deep * narrow * swell);
      this.layers.setMatrixAt(at.layers, matrix.compose(place, STRAIGHT, size));
      at.layers += 1;
    }
    const gone = record.goneAt === null ? 0 : clamp01((this.now - record.goneAt) / BREAK_TICKS);
    if (gone < 1) {
      const top = (layerStart(record, Math.max(standing, 1) - 1) + layerThick(record, Math.max(standing, 1) - 1)) * swell;
      const lift = gone * this.height * BREAK_RISE * 0.5;
      const scale = (Math.min(record.w, record.h) * this.cell * TOP_SHARE * swell * (1 - gone));
      place.set(record.x, top + lift, record.z);
      size.set(scale, scale, scale);
      matrix.compose(place, STRAIGHT, size);
      this.toppings.forEach((mesh) => mesh.setMatrixAt(at.toppings, matrix));
      at.toppings += 1;
    }
    const across = record.w * this.cell * SHADOW_WIDE;
    const length = record.h * this.cell * SHADOW_WIDE;
    const fade = standing > 0 ? 1 : 1 - gone;
    place.set(record.x + across * SHADOW_SHIFT, SHADOW_LIFT, record.z + length * SHADOW_SHIFT);
    size.set(across * fade, 1, length * fade);
    this.shadows.setMatrixAt(at.shadows, matrix.compose(place, STRAIGHT, size));
    at.shadows += 1;
  }

  // The broken layers in flight: each rises, swells, turns and shrinks away
  drawDebris(at) {
    this.debris = this.debris.filter((piece) => this.now - piece.t0 < BREAK_TICKS);
    for (const piece of this.debris) {
      const u = clamp01((this.now - piece.t0) / BREAK_TICKS);
      const { record } = piece;
      const rise = 1 - (1 - u) * (1 - u);
      const swell = 1 + BREAK_SWELL * u;
      const fade = u < 0.5 ? 1 : 1 - (u - 0.5) / 0.5;
      place.set(record.x, layerStart(record, piece.k) + rise * this.height * BREAK_RISE, record.z);
      turn.setFromEuler(spin.set(0.25 * piece.flip * rise, BREAK_TURN * piece.flip * rise, 0));
      size.set(
        record.w * this.cell * FIT * (1 - TAPER * piece.k) * swell * fade,
        layerThick(record, piece.k) * swell * fade,
        record.h * this.cell * FIT * (1 - TAPER * piece.k) * swell * fade,
      );
      this.broken.setMatrixAt(at.broken, matrix.compose(place, turn, size));
      at.broken += 1;
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.records.length) {
      return;
    }
    const at = { layers: 0, toppings: 0, shadows: 0, broken: 0 };
    for (const record of this.records) {
      this.drawBiscuit(record, state, at);
    }
    this.drawDebris(at);
    this.layers.count = at.layers;
    this.broken.count = at.broken;
    this.shadows.count = at.shadows;
    for (const mesh of this.toppings) {
      mesh.count = at.toppings;
    }
    for (const mesh of this.meshes) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  }
}

// Load the model and the shadow, and add the pool of biscuits to the scene
export async function create(scene) {
  const [gltf, shadow] = await Promise.all([new GLTFLoader().loadAsync(MODEL), new THREE.TextureLoader().loadAsync(SHADOW)]);
  shadow.colorSpace = THREE.SRGBColorSpace;
  return new BiscuitLook(shapePieces(piecesOf(gltf)), shadow, scene);
}
