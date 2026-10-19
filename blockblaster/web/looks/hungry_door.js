// Feature 15, Hungry Doors: a double wooden door stands over its cubes, a golden frame in the color of the cubes it eats
// and a white tag on its top showing how many more it wants. When a single-cell cube of its color dies, a copy of the
// cube leaps from where it stood into the door over 0.3 s (CUBE_FLY_IN), and the door swells with a knock as it lands. At
// 0 the door shakes, its two halves fold open and the whole door sinks and shrinks away (PixelColorDoorModel$$Open,
// RVA 0x56C9ABC: scale punches, a shake, the halves' DOScaleX and a DOMoveY of -2), while its cells are already free for
// the rules. The door is one of the original's `models/features/pixel_color_door_model_*.glb` (three meshes: the box
// and its two halves), the closest size to the door's cells stretched to cover them, with the soft `Shadow_*Door.png`
// of the same size under it. The prefab holds no materials, so the wood, the frame and the shake are the look's
// choice. Everything comes from the simulation's door records (sim/features/hungry_door.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "../camera.js";
import { COLORS } from "../picture.js";
import { play as sound } from "../sound.js";
import { NUMBER } from "../sim/features/hungry_door.js";
import { CUBE_FLY_IN, DOOR_OPEN, L_PER_UNIT } from "../sim/numbers.js";

export { NUMBER };

// The four prefabs by the cells they are made for (across x down); the closest one to a door's cells is stretched to fit
const SIZES = [
  [10, 10],
  [12, 10],
  [14, 14],
  [18, 18],
];
const modelPath = ([w, h]) => `models/features/pixel_color_door_model_${w}x${h}.glb`;
const shadowPath = ([w, h]) => `art/effects/Shadow_${w}x${h}Door.png`;
// The most doors one level holds is 8
const DOORS = 8;
// How tall the door stands, in cube heights
const DOOR_TALL = 1.5;
// Painting: a half's raised frame is its top within this far of its highest point (model units; the sunk panel inside
// lies 0.2 lower), then the wood and the sides
const RIM_DEPTH = 0.1;
const WOOD = new THREE.Color(0xb86a2e);
const WOOD_SIDE = new THREE.Color(0x7a4020);
const BOX_TOP = new THREE.Color(0x70391b);
const BOX_SIDE = new THREE.Color(0x5a2c14);
// A knock as a cube lands: the door swells this much and settles over this many ticks
const KNOCK = 0.05;
const KNOCK_TICKS = 8;
// The opening: the shake lasts this many ticks, the halves fold and the door sinks over the ticks after
const SHAKE_TICKS = 28;
const SHAKE_TURN = 0.05;
const FOLD_START = 22;
// The share of the fold after which the door starts to sink
const SINK_FROM = 0.35;
// The flying copies: most alive at once, their size against a cell, how high they arc in cube heights, and the share
// of their size they have left when they land
const COPIES = 256;
const COPY_SIZE = 0.9;
const COPY_ARC = 6;
const COPY_END = 0.4;
// The tag: a white pill with dark digits, as wide as this share of the door's shorter side
const LABEL_W = 192;
const LABEL_H = 112;
const LABEL_FONT = '"Inter Black", "Segoe UI", sans-serif';
const LABEL_INK = "#4a2810";
const LABEL_SHARE = 0.8;
const LABEL_WIDE = 0.5;
const LABEL_LIFT = 0.02;
// The shadow: against the door's footprint, how far its middle sits toward the lower right, how dark it is
const SHADOW_WIDE = 1.3;
const SHADOW_SHIFT = 0.12;
const SHADOW_OPACITY = 0.3;
const SHADOW_LIFT = 0.004;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const size = new THREE.Vector3();
const STRAIGHT = new THREE.Quaternion();

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The model nearest a door's cells: the smallest sum of how far each side is off, as a ratio
function nearestSize(w, h) {
  let best = 0;
  let bestScore = Infinity;
  SIZES.forEach(([mw, mh], index) => {
    const score = Math.abs(Math.log(w / mw)) + Math.abs(Math.log(h / mh));
    if (score < bestScore) {
      bestScore = score;
      best = index;
    }
  });
  return best;
}

// A prefab's three meshes with their node transforms baked in (the box, then the two halves), and the box's size
function piecesOf(gltf) {
  gltf.scene.updateMatrixWorld(true);
  const geometries = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      geometries.push(node.geometry.clone().applyMatrix4(node.matrixWorld));
    }
  });
  const box = new THREE.Box3().setFromBufferAttribute(geometries[0].attributes.position);
  const top = Math.max(...geometries.map((g) => new THREE.Box3().setFromBufferAttribute(g.attributes.position).max.y));
  return { geometries, width: box.max.x - box.min.x, depth: box.max.z - box.min.z, top };
}

// Colors on a geometry: the box is dark wood; a half is wood in its sunk panel with the raised rim in the frame color
function paint(geometry, frame, rim) {
  const at = geometry.attributes.position;
  const normal = geometry.attributes.normal;
  const colors = new Float32Array(at.count * 3);
  const rimFrom = new THREE.Box3().setFromBufferAttribute(at).max.y - RIM_DEPTH;
  const color = new THREE.Color();
  for (let i = 0; i < at.count; i++) {
    const up = normal.getY(i) > 0.5;
    if (!rim) {
      color.copy(up ? BOX_TOP : BOX_SIDE);
    } else if (up) {
      color.copy(at.getY(i) > rimFrom ? frame : WOOD);
    } else {
      color.copy(WOOD_SIDE);
    }
    colors.set([color.r, color.g, color.b], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

class DoorLook {
  constructor(models, shadows, scene) {
    this.models = models;
    this.shadows = shadows;
    this.slots = [];
    this.doors = [];
    this.now = 0;
    this.copies = [];
    this.copyMesh = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0 }),
      COPIES,
    );
    this.copyMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.copyMesh.frustumCulled = false;
    this.copyMesh.count = 0;
    scene.add(this.copyMesh);
    for (let i = 0; i < DOORS; i++) {
      this.slots.push(this.makeSlot(scene));
    }
  }

  makeSlot(scene) {
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0 });
    const parts = [0, 1, 2].map(() => {
      const mesh = new THREE.Mesh(new THREE.BufferGeometry(), material);
      group.add(mesh);
      return mesh;
    });
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
    label.renderOrder = 4;
    group.add(label);
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2).rotateY(Math.PI),
      new THREE.MeshBasicMaterial({
        color: 0x000000,
        transparent: true,
        opacity: SHADOW_OPACITY,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1,
      }),
    );
    group.visible = false;
    shadow.visible = false;
    scene.add(group, shadow);
    return { group, parts, canvas, map, label, shadow, material };
  }

  // A new level: every door's model chosen and painted, laid over its cells
  build(state) {
    this.clear();
    const mine = state.features[NUMBER];
    if (!mine) {
      return;
    }
    const { grid } = state;
    this.cell = grid.size / L_PER_UNIT;
    this.height = Math.min(this.cell, PICTURE_HEIGHT);
    this.grid = grid;
    this.now = state.tick;
    mine.doors.slice(0, DOORS).forEach((record, index) => this.setup(index, record, grid));
  }

  // One door: the footprint of its cells, the model that fits, and what it takes to stretch the model over the footprint
  setup(index, record, grid) {
    const xs = record.cells.map((c) => c % grid.width);
    const ys = record.cells.map((c) => Math.floor(c / grid.width));
    const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
    const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
    const w = maxX - minX + 1;
    const h = maxY - minY + 1;
    const choice = nearestSize(w, h);
    const model = this.models[choice];
    const slot = this.slots[index];
    const frame = COLORS[record.color];
    model.geometries.forEach((source, part) => {
      const geometry = source.clone();
      paint(geometry, frame, part > 0);
      slot.parts[part].geometry.dispose();
      slot.parts[part].geometry = geometry;
    });
    slot.shadow.material.map = this.shadows[choice];
    slot.shadow.material.needsUpdate = true;
    this.doors[index] = {
      record,
      slot,
      w,
      h,
      choice,
      x: ((minX + maxX) / 2 - (grid.width - 1) / 2) * this.cell,
      z: -((minY + maxY) / 2 - (grid.height - 1) / 2) * this.cell,
      sx: (w * this.cell) / model.width,
      sz: (h * this.cell) / model.depth,
      sy: (this.height * DOOR_TALL) / model.top,
      top: this.height * DOOR_TALL,
      hinge: model.width / 2,
      hitAt: -1e9,
      openAt: null,
      shown: null,
    };
  }

  clear() {
    this.doors = [];
    this.copies = [];
    this.copyMesh.count = 0;
    for (const slot of this.slots) {
      slot.group.visible = false;
      slot.shadow.visible = false;
    }
  }

  onEvents(events, state) {
    for (const event of events) {
      if (event.k === "door_feed") {
        this.feed(event, state);
      } else if (event.k === "door_hit") {
        this.knock(event);
      } else if (event.k === "door_open") {
        this.open(event);
      }
    }
  }

  // A cube of the door's color died: its copy leaps from the cell it stood on to the middle of the door's top
  feed(event, state) {
    const door = this.doors[event.door];
    if (!door) {
      return;
    }
    const grid = state.grid;
    this.copies.push({
      t0: event.t,
      fx: ((event.cell % grid.width) - (grid.width - 1) / 2) * this.cell,
      fz: -(Math.floor(event.cell / grid.width) - (grid.height - 1) / 2) * this.cell,
      door,
      color: COLORS[event.color],
    });
    if (this.copies.length > COPIES) {
      this.copies.shift();
    }
  }

  knock(event) {
    const door = this.doors[event.door];
    if (door) {
      door.hitAt = event.t;
      sound("door_hit");
    }
  }

  open(event) {
    const door = this.doors[event.door];
    if (door) {
      door.openAt = event.t;
      sound("door_open");
    }
  }

  // The tag's number, redrawn only when it changed
  paintLabel(door, count) {
    const { canvas, map } = door.slot;
    const g = canvas.getContext("2d");
    g.clearRect(0, 0, LABEL_W, LABEL_H);
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.roundRect(2, 2, LABEL_W - 4, LABEL_H - 4, LABEL_H / 2 - 2);
    g.fill();
    g.font = `900 ${Math.round(LABEL_H * LABEL_SHARE)}px ${LABEL_FONT}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = LABEL_INK;
    g.fillText(String(count), LABEL_W / 2, LABEL_H * 0.54, LABEL_W * 0.84);
    map.needsUpdate = true;
  }

  // One door at its place this frame: standing (with a knock), opening, or gone
  drawDoor(door, state) {
    const { slot } = door;
    const body = state.grid.targets[door.record.target];
    const age = door.openAt === null ? -1 : this.now - door.openAt;
    const gone = body.dead && (door.openAt === null || age >= DOOR_OPEN);
    slot.group.visible = !gone;
    if (gone) {
      slot.shadow.visible = false;
      return;
    }
    let swell = 1;
    let turn = 0;
    let opened = 0;
    let sink = 0;
    if (body.dead) {
      const shake = clamp01(age / SHAKE_TICKS);
      turn = Math.sin(shake * Math.PI * 6) * SHAKE_TURN * (1 - shake);
      swell = 1 + KNOCK * Math.sin(Math.PI * shake);
      opened = clamp01((age - FOLD_START) / (DOOR_OPEN - FOLD_START));
      sink = clamp01((opened - SINK_FROM) / (1 - SINK_FROM)) ** 2;
    } else {
      const u = clamp01((this.now - door.hitAt) / KNOCK_TICKS);
      swell = 1 + KNOCK * Math.sin(Math.PI * u) * (u < 1 ? 1 : 0);
    }
    const out = 1 - sink;
    slot.group.position.set(door.x, -sink * door.top * 1.2, door.z);
    slot.group.rotation.set(0, 0, turn);
    slot.group.scale.set(door.sx * swell * out, door.sy * swell * out, door.sz * swell * out);
    // The halves fold toward their outer hinges (DOScaleX to 0 in the original), the model's half width away from the middle
    const fold = 1 - opened;
    slot.parts[1].scale.x = fold;
    slot.parts[1].position.x = -opened * door.hinge;
    slot.parts[2].scale.x = fold;
    slot.parts[2].position.x = opened * door.hinge;
    slot.label.visible = !body.dead;
    this.drawTag(door, body);
    this.drawShadow(door, 1 - opened);
  }

  // The tag on the door's top, in world units, with the number it shows
  drawTag(door, body) {
    const { slot } = door;
    const wide = Math.min(door.w, door.h) * this.cell * LABEL_WIDE;
    // The group's scale stretches the tag, so it is sized and lifted back in the group's own units
    slot.label.scale.set(wide / door.sx, wide / door.sz, 1);
    slot.label.position.set(0, door.top / door.sy + LABEL_LIFT, 0);
    if (!body.dead && door.shown !== body.health) {
      door.shown = body.health;
      this.paintLabel(door, body.health);
    }
  }

  drawShadow(door, fade) {
    const { shadow } = door.slot;
    shadow.visible = fade > 0;
    const across = door.w * this.cell * SHADOW_WIDE;
    const length = door.h * this.cell * SHADOW_WIDE;
    shadow.position.set(door.x + across * SHADOW_SHIFT, this.height + SHADOW_LIFT, door.z + length * SHADOW_SHIFT);
    shadow.scale.set(across * fade, 1, length * fade);
    shadow.material.opacity = SHADOW_OPACITY * fade;
  }

  // The cube copies in flight: an arc from where the cube stood to the door's top, shrinking as they go
  drawCopies() {
    this.copies = this.copies.filter((copy) => this.now - copy.t0 < CUBE_FLY_IN);
    let count = 0;
    for (const copy of this.copies) {
      const u = clamp01((this.now - copy.t0) / CUBE_FLY_IN);
      const lift = this.height * 0.5 + (copy.door.top - this.height * 0.5) * u;
      const arc = Math.sin(Math.PI * u) * this.height * COPY_ARC;
      place.set(copy.fx + (copy.door.x - copy.fx) * u, lift + arc, copy.fz + (copy.door.z - copy.fz) * u);
      const edge = this.cell * COPY_SIZE * (1 - (1 - COPY_END) * u);
      this.copyMesh.setMatrixAt(count, matrix.compose(place, STRAIGHT, size.set(edge, edge * 0.8, edge)));
      this.copyMesh.setColorAt(count, copy.color);
      count += 1;
    }
    this.copyMesh.count = count;
    this.copyMesh.instanceMatrix.needsUpdate = true;
    if (this.copyMesh.instanceColor) {
      this.copyMesh.instanceColor.needsUpdate = true;
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
    if (!this.doors.length) {
      return;
    }
    for (const door of this.doors) {
      this.drawDoor(door, state);
    }
    this.drawCopies();
  }
}

// Load the four prefabs and their shadows, and add the pool of doors to the scene
export async function create(scene) {
  const textures = new THREE.TextureLoader();
  const loader = new GLTFLoader();
  const [gltfs, shadows] = await Promise.all([
    Promise.all(SIZES.map((s) => loader.loadAsync(modelPath(s)))),
    Promise.all(SIZES.map((s) => textures.loadAsync(shadowPath(s)))),
  ]);
  for (const shadow of shadows) {
    shadow.colorSpace = THREE.SRGBColorSpace;
  }
  return new DoorLook(gltfs.map(piecesOf), shadows, scene);
}
