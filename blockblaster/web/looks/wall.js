// Feature 9, the Wall: wooden posts with a cream pointed top stand on the wall's cells, each leaning a little toward
// the player, with a soft shadow falling toward the lower right. A wall is one post (1x1, 2x2, 3x3) or two side by side
// (2x1, 4x2, 6x3), the way the original's six prefabs lay them out: every prefab is `wall_model_1x1.glb`'s post at a
// scale of 0.8 per cell of the post's side, centered on its footprint (the other five prefabs differ only in those
// node scales and offsets, so this one model is loaded). When the simulation removes a wall the posts shrink away over
// a few ticks. The original gives no sound. Everything comes from the simulation's wall records
// (sim/features/wall.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { NUMBER } from "../sim/features/wall.js";
import { L_PER_UNIT } from "../sim/numbers.js";

export { NUMBER };

const MODEL = "models/features/wall_model_1x1.glb";
const SHADOW = "art/effects/Shadow_Wall.png";
// The most posts one level holds is 86 (43 walls of two posts)
const POSTS = 128;
// The model's own size: a cell is 0.5 wide and a cube 1.5 tall, and the prefab scales the post by 0.8 per cell
const MESH_CELL = 0.5;
const MESH_HEIGHT = 1.5;
const POST_FIT = 0.8;
// The post is sunk this far into the ground by the prefab (its node sits at y = -0.2)
const SUNK = 0.2;
// The post is 2.34 model units tall and stands that high over a cube's 1.5
const POST_TALL = 2.34;
// Where the pointed top starts, as model heights: wood below the first, cream above the second, a blend between
const TOP_FROM = 1.7;
const TOP_TO = 2.25;
const WOOD = new THREE.Color(0x9a5238);
const CREAM = new THREE.Color(0xf7dcae);
// A removed wall's posts shrink over this many ticks
const GONE_TICKS = 12;
// The shadow: its width against the post's, its length against the post's height, how far its middle sits from the
// post's middle toward the lower right (shares of its width and length), and how dark it is
const SHADOW_WIDE = 1.0;
const SHADOW_LONG = 1.0;
const SHADOW_SHIFT_X = 0.2;
const SHADOW_SHIFT_Z = 0.45;
const SHADOW_OPACITY = 0.2;
const SHADOW_LIFT = 0.004;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const STRAIGHT = new THREE.Quaternion();
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The prefab's mesh with its node transform's lean baked in (the scale and the position are the look's), painted by
// height: wood below the point, cream on it
function postGeometry(gltf) {
  let geometry = null;
  gltf.scene.traverse((node) => {
    if (node.isMesh && geometry === null) {
      geometry = node.geometry.clone();
      geometry.applyQuaternion(node.quaternion);
    }
  });
  const at = geometry.attributes.position;
  const colors = new Float32Array(at.count * 3);
  const mix = new THREE.Color();
  for (let i = 0; i < at.count; i++) {
    mix.copy(WOOD).lerp(CREAM, clamp01((at.getY(i) - TOP_FROM) / (TOP_TO - TOP_FROM)));
    mix.toArray(colors, i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

// The posts of one wall from its cells: [middle x, middle y, side] in cells, the short side being each post's side
function postsOf(grid, cells) {
  const xs = cells.map((c) => c % grid.width);
  const ys = cells.map((c) => Math.floor(c / grid.width));
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  const wide = Math.max(...xs) - x0 + 1;
  const high = Math.max(...ys) - y0 + 1;
  const side = Math.min(wide, high);
  const count = Math.max(1, Math.round(Math.max(wide, high) / side));
  const middleX = x0 + (wide - 1) / 2;
  const middleY = y0 + (high - 1) / 2;
  const found = [];
  for (let i = 0; i < count; i++) {
    const along = (i - (count - 1) / 2) * side;
    found.push(wide >= high ? [middleX + along, middleY, side] : [middleX, middleY + along, side]);
  }
  return found;
}

class WallLook {
  constructor(geometry, shadowMap, scene) {
    this.records = [];
    this.now = 0;
    this.cell = 0;
    this.height = 0;
    this.shown = "";
    this.posts = new THREE.InstancedMesh(
      geometry,
      new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55 }),
      POSTS,
    );
    const flat = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI);
    this.shadows = new THREE.InstancedMesh(
      flat,
      new THREE.MeshBasicMaterial({
        map: shadowMap,
        color: 0x000000,
        transparent: true,
        opacity: SHADOW_OPACITY,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1,
      }),
      POSTS,
    );
    for (const mesh of [this.posts, this.shadows]) {
      mesh.frustumCulled = false;
      mesh.count = 0;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(mesh);
    }
  }

  // A new level: every wall's posts laid out in world units
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
    for (const wall of mine.walls) {
      const body = grid.targets[wall.target];
      const posts = postsOf(grid, body.cells).map(([x, y, side]) => ({
        x: (x - (grid.width - 1) / 2) * this.cell,
        z: -(y - (grid.height - 1) / 2) * this.cell,
        side,
      }));
      if (used + posts.length > POSTS) {
        break;
      }
      this.records.push({ wall, posts, first: used, goneAt: null });
      used += posts.length;
    }
    this.posts.count = used;
    this.shadows.count = used;
    this.now = state.tick;
  }

  clear() {
    this.records = [];
    this.posts.count = 0;
    this.shadows.count = 0;
    this.shown = "";
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k !== "wall_gone") {
        continue;
      }
      const record = this.records.find((r) => r.wall.target === event.target);
      if (record && record.goneAt === null) {
        record.goneAt = event.t;
      }
    }
  }

  // How much of the wall is left standing: 1, shrinking to 0 once it is gone (a wall already gone when the page
  // rebuilt its simulation under the look is simply not drawn)
  standing(record, state) {
    if (!state.grid.targets[record.wall.target].dead) {
      return 1;
    }
    if (record.goneAt === null) {
      return 0;
    }
    const u = clamp01((this.now - record.goneAt) / GONE_TICKS);
    return 1 - u * u;
  }

  // One post and its shadow at a share k of their size
  setPost(slot, one, k) {
    if (k <= 0) {
      this.posts.setMatrixAt(slot, HIDDEN);
      this.shadows.setMatrixAt(slot, HIDDEN);
      return;
    }
    const wide = (this.cell / MESH_CELL) * POST_FIT * one.side * k;
    const tall = (this.height / MESH_HEIGHT) * k;
    place.set(one.x, -SUNK * tall, one.z);
    this.posts.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(wide, tall, wide)));
    const across = this.cell * one.side * k * SHADOW_WIDE;
    const length = POST_TALL * tall * SHADOW_LONG;
    place.set(one.x + across * SHADOW_SHIFT_X, this.height + SHADOW_LIFT, one.z + length * SHADOW_SHIFT_Z);
    this.shadows.setMatrixAt(slot, matrix.compose(place, STRAIGHT, size.set(across, 1, length)));
  }

  // The posts and shadows at their sizes now, written only when a size changed
  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    const sizes = this.records.map((record) => this.standing(record, state));
    const key = sizes.join(",");
    if (key === this.shown) {
      return;
    }
    this.shown = key;
    this.records.forEach((record, r) => {
      record.posts.forEach((one, i) => this.setPost(record.first + i, one, sizes[r]));
    });
    this.posts.instanceMatrix.needsUpdate = true;
    this.shadows.instanceMatrix.needsUpdate = true;
  }
}

// Load the post and the shadow, and add the pool to the scene
export async function create(scene) {
  const [gltf, shadowMap] = await Promise.all([
    new GLTFLoader().loadAsync(MODEL),
    new THREE.TextureLoader().loadAsync(SHADOW),
  ]);
  shadowMap.colorSpace = THREE.SRGBColorSpace;
  return new WallLook(postGeometry(gltf), shadowMap, scene);
}
