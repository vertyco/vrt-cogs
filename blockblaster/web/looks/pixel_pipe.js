// Feature 6, the Pixel Pipe: a box on its cells in the color it gives next, with a white tag showing how many cubes it
// still holds and a soft shadow behind it. Each cube it gives leaps from the top of the box to its cell over 0.3 s
// (the cube is on its cell for the rules at once; picture.js draws the leap), and the box punches up a little as it
// gives. An empty pipe stays, grey and without a number.
// The box and the tag are the original's `models/features/pixel_pipe_feature.glb`, the shadow its
// `Shadow_PixelPipe.png` (ASSETS.md). The original gives no sound (its spawnAudio is empty). Everything comes from the
// simulation's pipe records (sim/features/pixel_pipe.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { COLORS } from "../picture.js";
import { NUMBER, front } from "../sim/features/pixel_pipe.js";
import { L_PER_UNIT, TICKS_PER_SECOND } from "../sim/numbers.js";

export { NUMBER };

const MODEL = "models/features/pixel_pipe_feature.glb";
const SHADOW = "art/effects/Shadow_PixelPipe.png";
// The most pipes one level holds is 7
const PIPES = 8;
// The model is made for a 3 x 3 pipe on cells 0.5 units wide; each cell more a side makes it 0.25 bigger
// (PixelPipeFeature #12008 meshSize, baseArea, areaScaleIncrement)
const MESH_CELL = 0.5;
const BASE_SIDE = 3;
const SIDE_STEP = 0.25;
// The box drawn that much smaller, so a 4 x 4 pipe stands about 3.25 cells wide as in the level 84 recording
const FIT = 0.87;
// A given cube's leap: 0.3 s and 5 units high at the model's cell size (spawnJumpDuration, spawnJumpHeight)
const JUMP_SECONDS = 0.3;
const JUMP_HEIGHT = 5.0;
// The box's punch as it gives: 0.07 s, stretching 0.1 across and 0.5 up at its peak (shootDuration, shootPunch)
const PUNCH_TICKS = 4;
const PUNCH_ACROSS = 0.1;
const PUNCH_UP = 0.5;
// The color of an empty pipe
const EMPTY = new THREE.Color(0xc9cad6);
// The tag's number: dark digits as tall as this share of the tag
const LABEL_W = 256;
const LABEL_H = 160;
const LABEL_FONT = '"Inter Black", "Segoe UI", sans-serif';
const LABEL_INK = "#262846";
const LABEL_SHARE = 0.92;
// The shadow's size against the box's footprint, how far it reaches down the screen, and how dark it is
const SHADOW_WIDE = 1.45;
const SHADOW_LONG = 2.05;
const SHADOW_OPACITY = 0.22;
const SHADOW_LIFT = 0.004;

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The prefab's two meshes with their node transforms baked in: the box and the tag
function pieces(gltf) {
  gltf.scene.updateMatrixWorld(true);
  const found = {};
  gltf.scene.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    const geometry = node.geometry.clone().applyMatrix4(node.matrixWorld);
    geometry.computeBoundingBox();
    found[node.name.includes("Pipe") ? "box" : "tag"] = geometry;
  });
  return found;
}

// A pipe's [color, total] as drawn: its front group's color (-1 when empty) and the cubes left in every group
function shownOf(pipe) {
  const group = front(pipe);
  return [group === null ? -1 : group[0], pipe.groups.reduce((sum, g) => sum + g[1], 0)];
}

class PipeLook {
  constructor(geometry, shadowMap, scene, picture) {
    this.picture = picture;
    this.records = [];
    this.now = 0;
    this.boxTop = geometry.box.boundingBox.max.y;
    const tag = geometry.tag.boundingBox;
    // The number lies on the tag's top face, as wide as the tag
    this.tagTop = tag.max.y;
    this.tagMiddle = tag.getCenter(new THREE.Vector3());
    this.tagWide = tag.max.x - tag.min.x;
    const tagMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.5 });
    const shadowMaterial = new THREE.MeshBasicMaterial({
      map: shadowMap,
      color: 0x000000,
      transparent: true,
      opacity: SHADOW_OPACITY,
      depthWrite: false,
    });
    this.parts = [];
    for (let i = 0; i < PIPES; i++) {
      const holder = new THREE.Group();
      const tint = new THREE.MeshStandardMaterial({ roughness: 0.45 });
      const box = new THREE.Mesh(geometry.box, tint);
      const tagMesh = new THREE.Mesh(geometry.tag, tagMaterial);
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
      label.position.set(this.tagMiddle.x, this.tagTop + 0.01, this.tagMiddle.z);
      label.scale.setScalar(this.tagWide * 1.05);
      holder.add(box, tagMesh, label);
      const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), shadowMaterial);
      shadow.rotation.x = -Math.PI / 2;
      holder.visible = false;
      shadow.visible = false;
      scene.add(holder, shadow);
      this.parts.push({ holder, box, tint, canvas, map, label, shadow });
    }
  }

  // A new level: every pipe stood on its cells in its colors
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    const cell = grid.size / L_PER_UNIT;
    mine.pipes.slice(0, PIPES).forEach((pipe, index) => {
      this.records.push(this.layout(grid, cell, pipe, index));
    });
    for (const record of this.records) {
      this.paint(record);
    }
    this.now = state.tick;
  }

  // One pipe's fixed numbers: the middle of its cells, how big the box stands and where its cubes leave from
  layout(grid, cell, pipe, index) {
    const xs = pipe.cells.map((c) => c % grid.width);
    const ys = pipe.cells.map((c) => Math.floor(c / grid.width));
    const side = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 1;
    const unit = cell / MESH_CELL;
    const scale = unit * FIT * (1 + SIDE_STEP * (side - BASE_SIDE));
    const midX = ((Math.min(...xs) + Math.max(...xs)) / 2 - (grid.width - 1) / 2) * cell;
    const midZ = -((Math.min(...ys) + Math.max(...ys)) / 2 - (grid.height - 1) / 2) * cell;
    const part = this.parts[index];
    part.holder.position.set(midX, 0, midZ);
    part.holder.scale.setScalar(scale);
    part.holder.visible = true;
    const foot = scale * BASE_SIDE * MESH_CELL;
    part.shadow.scale.set(foot * SHADOW_WIDE, foot * SHADOW_LONG, 1);
    part.shadow.position.set(midX + (foot * (SHADOW_WIDE - 1)) / 2, SHADOW_LIFT, midZ + (foot * (SHADOW_LONG - 1)) / 2);
    part.shadow.visible = true;
    return {
      pipe,
      index,
      scale,
      from: new THREE.Vector3(midX, this.boxTop * scale, midZ),
      jump: JUMP_HEIGHT * unit,
      color: null,
      total: null,
      punchAt: -Infinity,
    };
  }

  // The box in the color it gives next and the tag's number, redrawn only when either changed
  paint(record) {
    const [color, total] = shownOf(record.pipe);
    if (color === record.color && total === record.total) {
      return;
    }
    const part = this.parts[record.index];
    part.tint.color.copy(color < 0 ? EMPTY : COLORS[color]);
    if (total !== record.total) {
      const g = part.canvas.getContext("2d");
      g.clearRect(0, 0, LABEL_W, LABEL_H);
      if (total > 0) {
        g.font = `900 ${Math.round(LABEL_H * LABEL_SHARE)}px ${LABEL_FONT}`;
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillStyle = LABEL_INK;
        g.fillText(String(total), LABEL_W / 2, LABEL_H * 0.54, LABEL_W * 0.98);
      }
      part.map.needsUpdate = true;
    }
    record.color = color;
    record.total = total;
  }

  clear() {
    this.records = [];
    for (const part of this.parts) {
      part.holder.visible = false;
      part.shadow.visible = false;
    }
  }

  onEvents(events, state) {
    for (const event of events) {
      if (event.k !== "pipe_spawn") {
        continue;
      }
      const record = this.records[event.pipe];
      if (!record) {
        continue;
      }
      this.paint(record);
      record.punchAt = event.t;
      const target = state.grid.targets[event.cube];
      if (!target.dead) {
        this.picture.jumpCube(target, event.color, record.from, event.t / TICKS_PER_SECOND, JUMP_SECONDS, record.jump);
      }
    }
  }

  // The punch, and the colors and numbers again after the page rebuilt its simulation under the look
  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    for (const record of this.records) {
      this.paint(record);
      const u = clamp01((this.now - record.punchAt) / PUNCH_TICKS);
      const k = u < 1 ? Math.sin(Math.PI * u) : 0;
      const box = this.parts[record.index].box;
      box.scale.set(1 + PUNCH_ACROSS * k, 1 + PUNCH_UP * k, 1 + PUNCH_ACROSS * k);
    }
  }
}

// Load the prefab and the shadow, and add the pool of pipes to the scene
export async function create(scene, picture) {
  const [gltf, shadowMap] = await Promise.all([
    new GLTFLoader().loadAsync(MODEL),
    new THREE.TextureLoader().loadAsync(SHADOW),
  ]);
  shadowMap.colorSpace = THREE.SRGBColorSpace;
  return new PipeLook(pieces(gltf), shadowMap, scene, picture);
}

