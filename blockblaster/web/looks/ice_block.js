// Feature 12, Ice Blocks: a block is a grid of pale blue ice tiles standing over its cubes, each tile the original's
// `pixel_ice_block_model_default.glb` slab as wide as the block's BlockSize (the cubes show through it). Every hit
// (a single-cell cube died) takes tiles away, last in the block's own scatter order first, so that
// floor((health - 1) / startHealth x tiles) stand (PixelIceBlockFeature$$DamageIceBlocks, RVA 0x56D3AB8); a tile that
// goes breaks into three ice shards that fly off, and the block's last tiles shatter all at once when it breaks at 0
// (ShatterAllIceBlocks). A hit makes the whole block punch out a little. Soft shadows fall to the lower right of
// tiles with nothing standing there. Everything comes from the simulation's block records (sim/features/ice_block.js)
// and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { play as sound } from "../sound.js";
import { NUMBER } from "../sim/features/ice_block.js";
import { L_PER_UNIT } from "../sim/numbers.js";

export { NUMBER };

const MODEL = "models/features/pixel_ice_block_model_default.glb";
const SHADOW = "art/effects/Shadow_IceBlock.png";
const TEXTURE = "art/ui/Texture_Ice_2.png";
// The most tiles one level holds is 322 (level 2423)
const TILES = 384;
// The model is one wide and two tall; a tile is as wide as its cells and as tall as this many cubes
const MESH_HEIGHT = 2;
const ICE_TALL = 1.35;
const TILE_FIT = 0.97;
const ICE = new THREE.Color(0xa8e2ff);
const ICE_GLOW = new THREE.Color(0x0e3550);
const ICE_OPACITY = 0.8;
// A hit makes every tile of the block swell this much and settle over this many ticks
const PUNCH = 0.06;
const PUNCH_TICKS = 9;
// The shards (meshes of the model's ten loose pieces): how many at most are alive, how long one flies in ticks, its
// size against its tile's width, and its flight in world units: sideways speed and upward speed per tick, gravity
const SHARD_MESHES = [2, 4, 7];
const SHARDS = 480;
const SHARD_TICKS = 42;
const SHARD_SIZE = 0.5;
const SHARD_SPREAD = 0.012;
const SHARD_UP = 0.02;
const SHARD_GRAVITY = 0.0011;
// The shadow: its width against the tile's, its length against the tile's width, how far its middle sits from the
// tile's middle toward the lower right (shares of its width and length), and how dark it is
const SHADOW_WIDE = 1.1;
const SHADOW_LONG = 1.3;
const SHADOW_SHIFT_X = 0.2;
const SHADOW_SHIFT_Z = 0.4;
const SHADOW_OPACITY = 0.2;
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

// Whole numbers in a fixed scatter from a seed, the same each time (the order tiles leave in is only a look)
function scatter(count, seed) {
  const order = Array.from({ length: count }, (_, i) => i);
  let s = (seed * 2654435761 + 12345) >>> 0;
  for (let i = count - 1; i > 0; i--) {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    const j = s % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

// The tiles of one block from its cells: BlockSize squares laid from the lowest row and leftmost column, as
// [x, y] of each tile's lower-left cell. Every block in the levels divides into whole squares
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

// The tiles of a block standing at this health: all of them until the first hit, then floor((health - 1) / start x
// tiles); none once it is gone
function standingOf(count, health, start, dead) {
  if (dead) {
    return 0;
  }
  if (health >= start) {
    return count;
  }
  return Math.floor(clamp01((health - 1) / start) * count + 1e-9);
}

// One model piece's geometry with its node's turn baked in, centered on itself
function pieceGeometry(gltf, index) {
  const nodes = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      nodes.push(node);
    }
  });
  const geometry = nodes[index].geometry.clone();
  geometry.applyQuaternion(nodes[index].quaternion);
  geometry.center();
  return geometry;
}

class IceLook {
  constructor(gltf, maps, scene) {
    this.records = [];
    this.now = 0;
    this.cell = 0;
    this.height = 0;
    this.dirty = true;
    this.wasPunching = false;
    this.next = 0;
    this.shards = [];
    const material = new THREE.MeshStandardMaterial({
      map: maps.ice,
      color: ICE,
      emissive: ICE_GLOW,
      roughness: 0.25,
      metalness: 0,
      transparent: true,
      opacity: ICE_OPACITY,
    });
    this.tiles = new THREE.InstancedMesh(pieceGeometryOf(gltf), material, TILES);
    const flat = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI);
    this.shadows = new THREE.InstancedMesh(
      flat,
      new THREE.MeshBasicMaterial({
        map: maps.shadow,
        color: 0x000000,
        transparent: true,
        opacity: SHADOW_OPACITY,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1,
      }),
      TILES,
    );
    const pieces = SHARD_MESHES.map((index) => new THREE.InstancedMesh(pieceGeometry(gltf, index), material, SHARDS));
    for (const mesh of [this.tiles, this.shadows, ...pieces]) {
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(mesh);
    }
    this.pieces = pieces;
    for (const mesh of pieces) {
      mesh.count = SHARDS;
      for (let i = 0; i < SHARDS; i++) {
        mesh.setMatrixAt(i, HIDDEN);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
  }

  // A new level: every block's tiles laid out in world units, none of them breaking
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    this.cell = grid.size / L_PER_UNIT;
    this.height = Math.min(this.cell, PICTURE_HEIGHT);
    let used = 0;
    for (const block of mine.blocks) {
      const body = grid.targets[block.target];
      const side = Math.max(1, block.size);
      const found = tilesOf(grid, block.cells, side);
      const tiles = found.map(([x, y]) => ({
        x: x + (side - 1) / 2,
        y: y + (side - 1) / 2,
        wx: (x + (side - 1) / 2 - (grid.width - 1) / 2) * this.cell,
        wz: -(y + (side - 1) / 2 - (grid.height - 1) / 2) * this.cell,
      }));
      if (used + tiles.length > TILES) {
        break;
      }
      const order = scatter(tiles.length, block.target + 1);
      const record = {
        block,
        side,
        tiles,
        order,
        first: used,
        shown: standingOf(tiles.length, body.health, block.start, body.dead),
        punchAt: -1e9,
      };
      this.records.push(record);
      used += tiles.length;
    }
    this.tiles.count = used;
    this.shadows.count = used;
    this.now = state.tick;
    this.dirty = true;
  }

  clear() {
    this.records = [];
    this.tiles.count = 0;
    this.shadows.count = 0;
    this.dirty = true;
    for (const mesh of this.pieces) {
      for (let i = 0; i < SHARDS; i++) {
        mesh.setMatrixAt(i, HIDDEN);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
    this.shards = [];
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "ice_hit") {
        this.punch(event);
      } else if (event.k === "ice_gone") {
        this.shatter(event);
      }
    }
  }

  recordOf(target) {
    return this.records.find((r) => r.block.target === target);
  }

  punch(event) {
    const record = this.recordOf(event.target);
    if (record) {
      record.punchAt = event.t;
      sound("ice_hit");
    }
  }

  shatter(event) {
    if (this.recordOf(event.target)) {
      sound("ice_shatter");
    }
  }

  // The tiles standing now: the first `shown` of the block's scatter order
  standing(record, state) {
    const body = state.grid.targets[record.block.target];
    return standingOf(record.tiles.length, body.health, record.block.start, body.dead);
  }

  // Three shards fly out of a tile that just went
  burst(record, tile, slot) {
    for (let i = 0; i < this.pieces.length; i++) {
      const angle = ((slot * 3 + i) * 2.399963) % (2 * Math.PI);
      const sideways = SHARD_SPREAD * (0.5 + ((slot * 7 + i * 5) % 10) / 10);
      this.shards[this.next % SHARDS] = {
        kind: i,
        slot: this.next % SHARDS,
        t0: this.now,
        x: tile.wx,
        y: this.height * ICE_TALL * 0.6,
        z: tile.wz,
        vx: Math.cos(angle) * sideways,
        vz: Math.sin(angle) * sideways,
        vy: SHARD_UP * (0.6 + ((slot + i) % 5) / 5),
        turn: angle,
        wide: this.cell * record.side * SHARD_SIZE,
      };
      this.next += 1;
    }
  }

  // Tiles that left since the last frame break into shards; the shown count follows the simulation
  settle(state) {
    for (const record of this.records) {
      const stand = this.standing(record, state);
      if (stand >= record.shown) {
        record.shown = stand;
        continue;
      }
      for (let k = stand; k < record.shown; k++) {
        this.burst(record, record.tiles[record.order[k]], record.first + record.order[k]);
      }
      record.shown = stand;
      this.dirty = true;
    }
  }

  // The tiles and their shadows at their sizes now
  drawTiles() {
    const open = new Map();
    for (const record of this.records) {
      const set = new Set();
      for (let k = 0; k < record.shown; k++) {
        const tile = record.tiles[record.order[k]];
        set.add(`${tile.x},${tile.y}`);
      }
      open.set(record, set);
    }
    for (const record of this.records) {
      const standing = new Set(record.order.slice(0, record.shown));
      const swell = 1 + PUNCH * (1 - clamp01((this.now - record.punchAt) / PUNCH_TICKS));
      record.tiles.forEach((tile, t) => {
        const slot = record.first + t;
        if (!standing.has(t)) {
          this.tiles.setMatrixAt(slot, HIDDEN);
          this.shadows.setMatrixAt(slot, HIDDEN);
          return;
        }
        const wide = this.cell * record.side * TILE_FIT * swell;
        const tall = ((this.height * ICE_TALL) / MESH_HEIGHT) * swell;
        this.tiles.setMatrixAt(slot, matrix.compose(place.set(tile.wx, 0, tile.wz), STRAIGHT, size.set(wide, tall, wide)));
        const set = open.get(record);
        const covered = set.has(`${tile.x + record.side},${tile.y}`) || set.has(`${tile.x},${tile.y - record.side}`);
        if (covered) {
          this.shadows.setMatrixAt(slot, HIDDEN);
          return;
        }
        const across = this.cell * record.side * SHADOW_WIDE;
        const length = this.cell * record.side * SHADOW_LONG;
        place.set(tile.wx + across * SHADOW_SHIFT_X, this.height + SHADOW_LIFT, tile.wz + length * SHADOW_SHIFT_Z);
        this.shadows.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(across, 1, length)));
      });
    }
    this.tiles.instanceMatrix.needsUpdate = true;
    this.shadows.instanceMatrix.needsUpdate = true;
  }

  // The flying shards, each shrinking over its flight
  drawShards() {
    const touched = new Set();
    for (let i = 0; i < this.shards.length; i++) {
      const shard = this.shards[i];
      if (!shard) {
        continue;
      }
      const mesh = this.pieces[shard.kind];
      const age = this.now - shard.t0;
      touched.add(mesh);
      if (age >= SHARD_TICKS || age < 0) {
        mesh.setMatrixAt(shard.slot, HIDDEN);
        this.shards[i] = null;
        continue;
      }
      const k = 1 - clamp01(age / SHARD_TICKS) ** 2;
      place.set(
        shard.x + shard.vx * age,
        Math.max(0, shard.y + shard.vy * age - SHARD_GRAVITY * age * age),
        shard.z + shard.vz * age,
      );
      turn.setFromEuler(spin.set(age * 0.15 + shard.turn, age * 0.1, age * 0.2));
      const scale = shard.wide * k;
      mesh.setMatrixAt(shard.slot, matrix.compose(place, turn, size.set(scale, scale, scale)));
    }
    for (const mesh of touched) {
      mesh.instanceMatrix.needsUpdate = true;
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.records.length) {
      return;
    }
    this.settle(state);
    const punching = this.records.some((r) => this.now - r.punchAt < PUNCH_TICKS);
    if (this.dirty || punching || this.wasPunching) {
      this.dirty = false;
      this.drawTiles();
    }
    this.wasPunching = punching;
    this.drawShards();
  }
}

// The slab's geometry: the model's first piece (the block itself), with its node's scale baked in
function pieceGeometryOf(gltf) {
  let geometry = null;
  gltf.scene.traverse((node) => {
    if (node.isMesh && geometry === null) {
      geometry = node.geometry.clone();
      geometry.scale(node.scale.x, node.scale.y, node.scale.z);
    }
  });
  return geometry;
}

// Load the model, the ice picture and the shadow, and add the pools to the scene
export async function create(scene) {
  const textures = new THREE.TextureLoader();
  const [gltf, ice, shadow] = await Promise.all([
    new GLTFLoader().loadAsync(MODEL),
    textures.loadAsync(TEXTURE),
    textures.loadAsync(SHADOW),
  ]);
  ice.colorSpace = THREE.SRGBColorSpace;
  ice.wrapS = THREE.RepeatWrapping;
  ice.wrapT = THREE.RepeatWrapping;
  shadow.colorSpace = THREE.SRGBColorSpace;
  return new IceLook(gltf, { ice, shadow }, scene);
}
