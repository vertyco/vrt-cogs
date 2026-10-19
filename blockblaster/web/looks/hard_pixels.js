// Feature 3, Hard Pixels: a cube that takes several hits shows its remaining hits as a number on its top and stands
// shorter with every hit (the squash and chips of a hit are picture.js's `hitCube`, the ring of metal is sound.js's
// `metal`). The rules are the core's (a target with more than one health), so this look has no simulation module and
// never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { startHealth, wornHeight } from "../picture.js";
import { L_PER_UNIT } from "../sim/numbers.js";
import { centerX, centerY } from "../sim/grid.js";

export const NUMBER = 3;

const FONT = '"Inter Black", "Segoe UI", sans-serif';
const OUTLINE = "#262846";
const GLYPHS = "0123456789";
const CELL = 128;
// A number shows up to three digits (health 100), each quad this wide apart as a share of its height
const DIGITS = 3;
const ADVANCE = 0.6;
// The most cubes with several hits one level holds is 61
const CAPACITY = 128;
// The number's height as a share of the cube's shorter side, and the widest share of the cube's width it may take
const HEIGHT_SHARE = 0.7;
const WIDTH_SHARE = 0.92;
const LIFT = 0.03;
// A hit makes the number swell for this long in ms and by this much
const POP_MS = 160;
const POP_SWELL = 0.35;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();

// The digits side by side, white with a dark outline
function digitTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = CELL * GLYPHS.length;
  canvas.height = CELL;
  const g = canvas.getContext("2d");
  g.font = `900 ${Math.round(CELL * 0.8)}px ${FONT}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.lineJoin = "round";
  g.lineWidth = CELL * 0.14;
  g.strokeStyle = OUTLINE;
  g.fillStyle = "#ffffff";
  for (let d = 0; d < GLYPHS.length; d++) {
    const x = CELL * d + CELL / 2;
    const y = CELL * 0.54;
    g.strokeText(GLYPHS[d], x, y);
    g.fillText(GLYPHS[d], x, y);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

// A quad shows cell `digit` of the digit sheet
function digitMaterial(map) {
  const material = new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, toneMapped: false });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute float digit;")
      .replace("#include <uv_vertex>", `#include <uv_vertex>\nvMapUv.x = (vMapUv.x + digit) / ${GLYPHS.length}.0;`);
  };
  return material;
}

// The bounding cells of a target as [x0, y0, x1, y1]
function cellRange(width, target) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const cell of target.cells) {
    const x = cell % width;
    const y = Math.floor(cell / width);
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return [x0, y0, x1, y1];
}

class HardPixelsLook {
  constructor(mesh, digit) {
    this.mesh = mesh;
    this.digit = digit;
    // Per cube with several hits: where it stands, its number's height, and the hits shown now (-1 before the first draw)
    this.labels = [];
    this.height = 0;
    this.dirty = false;
  }

  // A new level: a label for every cube that takes more than one hit
  build(state) {
    this.clear();
    const grid = state.grid;
    const cell = grid.size / L_PER_UNIT;
    this.height = Math.min(cell, PICTURE_HEIGHT);
    for (const target of grid.targets) {
      const full = target.owner === 0 && target.cells.length > 0 ? startHealth(state, target) : 1;
      if (full > 1 && this.labels.length < CAPACITY) {
        this.labels.push(this.makeLabel(grid, target, full, cell));
      }
    }
    this.dirty = true;
  }

  makeLabel(grid, target, full, cell) {
    const [x0, y0, x1, y1] = cellRange(grid.width, target);
    const across = (x1 - x0 + 1) * cell;
    const down = (y1 - y0 + 1) * cell;
    const digits = String(full).length;
    const fit = (across * WIDTH_SHARE) / (ADVANCE * (digits - 1) + 0.7);
    return {
      target,
      full,
      x: (centerX(grid, x0) + centerX(grid, x1)) / 2 / L_PER_UNIT,
      z: -(centerY(grid, y0) + centerY(grid, y1)) / 2 / L_PER_UNIT,
      height: Math.min(Math.min(across, down) * HEIGHT_SHARE, fit),
      shown: -1,
      popped: -Infinity,
    };
  }

  clear() {
    this.labels = [];
    this.mesh.count = 0;
  }

  // Notice each cube's new health and write the numbers when one changed or one is still swelling
  frame() {
    const now = performance.now();
    let swelling = false;
    for (const label of this.labels) {
      const hits = label.target.dead ? 0 : label.target.health;
      if (hits !== label.shown) {
        if (label.shown > 0 && hits > 0) {
          label.popped = now;
        }
        label.shown = hits;
        this.dirty = true;
      }
      swelling = swelling || now - label.popped < POP_MS;
    }
    if (this.dirty || swelling) {
      this.write(now);
      this.dirty = false;
    }
  }

  write(now) {
    let count = 0;
    for (const label of this.labels) {
      if (label.shown > 0) {
        count += this.writeLabel(count, label, now);
      }
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    this.digit.needsUpdate = true;
  }

  // The label's digits side by side on the cube's top, at the height its health leaves it. Returns the quads used
  writeLabel(first, label, now) {
    const text = String(label.shown);
    const u = Math.min(1, Math.max(0, (now - label.popped) / POP_MS));
    const height = label.height * (1 + POP_SWELL * Math.sin(Math.PI * u));
    const top = this.height * wornHeight(label.shown, label.full) + LIFT;
    for (let d = 0; d < text.length; d++) {
      place.set(label.x + (d - (text.length - 1) / 2) * ADVANCE * height, top, label.z);
      matrix.compose(place, turn.identity(), size.setScalar(height));
      this.mesh.setMatrixAt(first + d, matrix);
      this.digit.setX(first + d, Number(text[d]));
    }
    return text.length;
  }
}

// Make the numbers' mesh and add it to the scene
export async function create(scene) {
  const geometry = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const digit = new THREE.InstancedBufferAttribute(new Float32Array(CAPACITY * DIGITS), 1);
  digit.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute("digit", digit);
  const mesh = new THREE.InstancedMesh(geometry, digitMaterial(digitTexture()), CAPACITY * DIGITS);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  mesh.renderOrder = 3;
  mesh.count = 0;
  scene.add(mesh);
  return new HardPixelsLook(mesh, digit);
}
