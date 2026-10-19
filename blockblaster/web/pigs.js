// Pigs, trays and the slot row: every pig of a level in a few instanced batches, the ammo numbers on their backs, and
// the boxes a press is checked against.
// A pig is drawn as a cat, `pig.glb` (ASSETS.md): its `Tint_*` parts take the pig's color, the marks (nose, inner ears,
// cheeks, whiskers) keep their own colors, and the face plate shows one frame of the face sheet. Each part is one InstancedMesh, so 157 pigs cost three draw calls.
// Pigs are never created or freed during play: a pig that is gone shrinks to nothing.
import * as THREE from "./vendor/three.module.min.js";
import { mergeGeometries } from "./vendor/BufferGeometryUtils.js";
import { GLTFLoader } from "./vendor/GLTFLoader.js";
import { HOP_HEIGHT } from "./fx.js";
import { COLORS } from "./picture.js";
import * as belt from "./sim/belt.js";
import { HOP, L_PER_UNIT } from "./sim/numbers.js";
import { worldFromPicture } from "./space.js";

const PIG_MODEL = "models/pig.glb";
const TRAY_MODEL = "models/features/conveyor_item_slot.glb";
const SLOT_PICTURE = "art/ui/Slot.png";
const SHADOW_PICTURE = "art/effects/Shadow_1x1_Circle.png";
const DIGIT_FONT = '"Inter Black", "Segoe UI", sans-serif';

// The pig's face sheet has five frames side by side
const FACE_OPEN = 0;
const FACE_EMPTY = 3;
const FACE_FRAMES = 5;

// Room for the biggest level's pigs (157) and the pigs its features hold, each with up to three digits of ammo
const PIG_CAPACITY = 384;
const DIGITS_PER_PIG = 3;
const TRAY_CAPACITY = 64;
const SLOT_CAPACITY = 8;

// Where the ammo number sits on a pig (`AmmoAnchor`), and how big its digits are, in units at pig scale 1
const AMMO_ANCHOR = { y: 0.955, z: -0.04 };
const DIGIT_SIZE = 0.38;
const DIGIT_ADVANCE = 0.235;
// Pigs behind the front one of a queue show their number faded (ShooterQueueVisuals #12079)
const BEHIND_FADE = 0.25;
// A number lies just above the pig's back
const DIGIT_LIFT = 0.02;
const DIGIT_CELL = 128;
// The digit sheet holds 0 to 9 and then "?", the number of a hidden Surprise pig
const DIGIT_GLYPHS = "0123456789?";
const DIGIT_OUTLINE = "#262846";

// The tray is a flat plate: its geometry spans y -0.026 to 0.122, 0.59 square
const TRAY_BOTTOM = 0.026;
const TRAY_TOP = 0.122;
const TRAY_COLOR = 0xe3e7fb;
// The free trays wait on edge in a stack beside the entrance (board.json `tray_stack`)
const STACK_STEP = 0.13;
// Pigs on the belt are smaller than the ones waiting below it
const BELT_PIG_SCALE = 0.7;
// Pigs waiting at the belt's exit stand in a line going down from the lap's end, this far apart
const EXIT_GAP = 1;

const SLOT_COLOR = 0x33355c;
// A slot flashes toward this when the row is full and a pig is about to run out of room
const SLOT_ALARM = 0x9c2c40;
// Pigs waiting in queues, slots and the rescue row stand with their backs to the camera, as the original's do: ears
// up the screen, tail toward the viewer
const BACK_TO_CAMERA = Math.PI;
const SLOT_LIFT = 0.005;
const SHADOW_COLOR = 0x14153a;
const SHADOW_OPACITY = 0.25;
const SHADOW_LIFT = 0.012;
const SHADOW_GROW = 1.05;
const SHADOW_AIR_SHRINK = 0.12;
// Fingers need at least this much to press, in CSS pixels
const MIN_HIT = 44;

const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

// The one pig group that `buildPigs`, `syncPigs` and `hitTest` work with: the scene's
const active = { pigs: null };

// Remember which scene's pigs are in use and put this level's pigs up
export function buildPigs(scene, state) {
  active.pigs = scene.pigs;
  active.pigs.build(state);
}

// Place every pig for the state's current tick. `alpha` (0 to 1) slides belt riders from where the last tick had them
// toward this tick's place, so motion stays smooth between ticks; left out, they stand at this tick's place
export function syncPigs(state, alpha = 1) {
  active.pigs.alpha = alpha;
  active.pigs.sync(state);
}

// Note where every tray on the belt is, just before the simulation steps, for the next syncs to slide from
export function rememberPigs(state) {
  if (active.pigs) {
    active.pigs.remember(state);
  }
}

// The tap a press at x, y (pixels from the column's top left) lands on: ["q", queue], ["s", slot], ["r", index], or
// null when it lands on no pig
export function hitTest(x, y) {
  return active.pigs ? active.pigs.hit(x, y) : null;
}

// The queue pig (queue, index) a Hand pick at x, y lands on, or null: the nearest of the pigs whose boxes hold the press.
// Slot and rescue pigs are no targets
export function pickTest(x, y) {
  return active.pigs ? active.pigs.pick(x, y) : null;
}

// The most pigs the rescue row can hold: one per tray on the belt and one per slot
function rescueCapacity(state) {
  return state.trayTotal + state.slots.length;
}

function loadFont() {
  return document.fonts.load(`900 ${DIGIT_CELL}px ${DIGIT_FONT}`).catch((e) => {
    console.warn("Block Blaster: couldn't load the number font", e);
  });
}

// The digits and "?" side by side, white with a dark outline
function digitTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = DIGIT_CELL * DIGIT_GLYPHS.length;
  canvas.height = DIGIT_CELL;
  const g = canvas.getContext("2d");
  g.font = `900 ${Math.round(DIGIT_CELL * 0.8)}px ${DIGIT_FONT}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.lineJoin = "round";
  g.lineWidth = DIGIT_CELL * 0.14;
  g.strokeStyle = DIGIT_OUTLINE;
  g.fillStyle = "#ffffff";
  for (let d = 0; d < DIGIT_GLYPHS.length; d++) {
    const x = DIGIT_CELL * d + DIGIT_CELL / 2;
    const y = DIGIT_CELL * 0.54;
    g.strokeText(DIGIT_GLYPHS[d], x, y);
    g.fillText(DIGIT_GLYPHS[d], x, y);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

async function loadPicture(url) {
  const texture = await new THREE.TextureLoader().loadAsync(url);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
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

// A model's meshes as geometries in the file's own space, grouped by what the page does with them
function pigParts(gltf) {
  const parts = { body: [], marks: [], face: [], map: null };
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((node) => {
    if (!node.isMesh) {
      return;
    }
    const geometry = node.geometry.clone().toNonIndexed();
    geometry.applyMatrix4(node.matrixWorld);
    if (node.name === "FacePlate") {
      parts.face.push(geometry);
      parts.map = node.material.map;
    } else if (node.name.startsWith("Tint_")) {
      geometry.deleteAttribute("uv");
      parts.body.push(geometry);
    } else {
      geometry.deleteAttribute("uv");
      paint(geometry, node.material.color);
      parts.marks.push(geometry);
    }
  });
  return parts;
}

// The face plate shows frame `face` of the sheet: its texture coordinates slide right by that many frames
function faceMaterial(map) {
  const material = new THREE.MeshBasicMaterial({ map, toneMapped: false, alphaToCoverage: true, alphaTest: 0.3 });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute float face;")
      .replace("#include <uv_vertex>", `#include <uv_vertex>\n#ifdef USE_MAP\nvMapUv.x += face / ${FACE_FRAMES}.0;\n#endif`);
  };
  return material;
}

// A digit quad shows cell `digit` of the digit sheet, at opacity `fade`
function digitMaterial(map) {
  const material = new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, toneMapped: false });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute float digit;\nattribute float fade;\nvarying float vFade;")
      .replace(
        "#include <uv_vertex>",
        `#include <uv_vertex>\nvMapUv.x = (vMapUv.x + digit) / ${DIGIT_GLYPHS.length}.0;\nvFade = fade;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vFade;")
      .replace("#include <color_fragment>", "#include <color_fragment>\ndiffuseColor.a *= vFade;");
  };
  return material;
}

function instanced(geometry, material, capacity) {
  const mesh = new THREE.InstancedMesh(geometry, material, capacity);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.frustumCulled = false;
  mesh.count = 0;
  return mesh;
}

function addAttribute(geometry, name, capacity) {
  const attribute = new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1);
  attribute.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute(name, attribute);
  return attribute;
}

// A flat square lying on the ground, facing up, whose picture's top points up the screen
function groundSquare() {
  return new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
}

function groundBatch(material, capacity, renderOrder) {
  const mesh = instanced(groundSquare(), material, capacity);
  mesh.renderOrder = renderOrder;
  return mesh;
}

// The model's meshes: the pig's three batches and the tray
async function loadModels() {
  const loader = new GLTFLoader();
  const [pig, tray] = await Promise.all([loader.loadAsync(PIG_MODEL), loader.loadAsync(TRAY_MODEL)]);
  const parts = pigParts(pig);
  let flat = null;
  tray.scene.traverse((node) => {
    if (node.isMesh && !flat) {
      flat = node.geometry;
    }
  });
  return { parts, tray: flat };
}

// One batch of every pig part, plus the numbers, shadows, slots and trays
async function makeBatches(scene) {
  await loadFont();
  const [models, slotPicture, shadowPicture] = await Promise.all([
    loadModels(),
    loadPicture(SLOT_PICTURE),
    loadPicture(SHADOW_PICTURE),
  ]);
  const { parts } = models;
  const bodyGeometry = mergeGeometries(parts.body);
  const markGeometry = mergeGeometries(parts.marks);
  const faceGeometry = mergeGeometries(parts.face);
  const face = addAttribute(faceGeometry, "face", PIG_CAPACITY);
  const digitGeometry = groundSquare();
  const digit = addAttribute(digitGeometry, "digit", PIG_CAPACITY * DIGITS_PER_PIG);
  const fade = addAttribute(digitGeometry, "fade", PIG_CAPACITY * DIGITS_PER_PIG);
  const batches = {
    body: instanced(bodyGeometry, new THREE.MeshStandardMaterial({ roughness: 0.55 }), PIG_CAPACITY),
    marks: instanced(markGeometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6 }), PIG_CAPACITY),
    face: instanced(faceGeometry, faceMaterial(parts.map), PIG_CAPACITY),
    digits: instanced(digitGeometry, digitMaterial(digitTexture()), PIG_CAPACITY * DIGITS_PER_PIG),
    shadows: groundBatch(
      new THREE.MeshBasicMaterial({
        map: shadowPicture,
        color: SHADOW_COLOR,
        opacity: SHADOW_OPACITY,
        transparent: true,
        depthWrite: false,
      }),
      PIG_CAPACITY,
      1,
    ),
    slots: groundBatch(
      new THREE.MeshBasicMaterial({ map: slotPicture, transparent: true, depthWrite: false }),
      SLOT_CAPACITY,
      0,
    ),
    trays: instanced(
      models.tray,
      new THREE.MeshStandardMaterial({ color: TRAY_COLOR, roughness: 0.5 }),
      TRAY_CAPACITY,
    ),
  };
  batches.digits.renderOrder = 3;
  scene.add(...Object.values(batches));
  return { batches, attributes: { face, digit, fade } };
}

// Where each pig is, by place, looked up once per sync. A queue pig maps to [queue, index], a slot pig to its slot,
// a belt pig to its tray
function lookups(state) {
  const found = { queue: new Map(), slot: new Map(), rescue: new Map(), exit: new Map(), belt: new Map() };
  state.queues.forEach((ids, q) => ids.forEach((id, k) => found.queue.set(id, [q, k])));
  state.slots.forEach((id, i) => id !== null && found.slot.set(id, i));
  state.rescue.forEach((id, i) => found.rescue.set(id, i));
  state.entrance.forEach(([id], i) => found.exit.set(id, i));
  state.belt.forEach((tray) => found.belt.set(tray.pig, tray));
  return found;
}

function grown(box, least) {
  const w = Math.max(box.w, least);
  const h = Math.max(box.h, least);
  return { x: box.x - (w - box.w) / 2, y: box.y - (h - box.h) / 2, w, h };
}

function inside(box, x, y) {
  return x >= box.x && x <= box.x + box.w && y >= box.y && y <= box.y + box.h;
}

function distanceToMiddle(box, x, y) {
  return Math.hypot(x - (box.x + box.w / 2), y - (box.y + box.h / 2));
}


// Scratch objects the placing code reuses, so a sync allocates nothing
const tint = new THREE.Color();
const slotTint = new THREE.Color();
const slotAlarm = new THREE.Color(SLOT_ALARM);
const slotBase = new THREE.Color(SLOT_COLOR);
const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);
const ON_EDGE = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2);
const PIG_BATCHES = ["body", "marks", "face", "shadows"];

// The pigs and trays, as the scene's other modules see them. `layout` is the scene's ground layout and `board` is
// board.json
class PigGroup {
  constructor(made, layout, board) {
    this.batches = made.batches;
    this.attributes = made.attributes;
    this.layout = layout;
    this.board = board;
    // The level on screen, the instance of each pig id, and the press boxes (worked out again after a resize)
    this.state = null;
    this.order = new Map();
    this.pressBoxes = null;
    // Each started tray's lap position one tick back, and how far the drawing is toward the current tick
    this.before = new Map();
    this.alpha = 1;
    this.surface = board.belt.height / L_PER_UNIT;
    this.trayY = this.surface + TRAY_BOTTOM;
    // Where the pig being written stands. `shown` is false for a pig that is gone or held inside a feature. `air` is
    // its height above that spot (a hop), `sx` and `sy` stretch it (a landing squash), `face` is a face frame (-1
    // leaves it to the ammo), `digits` is false while its number is hidden, `tint` is a color for its body (null for
    // its own) and `text` is what its number shows (null for its ammo)
    this.pose = {
      x: 0,
      y: 0,
      z: 0,
      yaw: 0,
      scale: 1,
      fade: 1,
      shown: false,
      air: 0,
      sx: 1,
      sy: 1,
      face: -1,
      digits: true,
      tint: null,
      text: null,
    };
    // The feature looks (looks/index.js) that dress pigs; the scene sets it
    this.looks = null;
    // The effects (fx.js) that move pigs and trays between ticks; the scene sets it
    this.fx = null;
    // Trays that came off the belt and are hopping back to the stack, and where each belt tray was last drawn
    this.homing = [];
    this.trayAt = new Map();
  }

  setPose(x, y, z, yaw, scale, fade = 1) {
    Object.assign(this.pose, { x, y, z, yaw, scale, fade, shown: true });
  }

  // The belt's lap point at `pos` as a world point on the belt's surface
  beltPoint(state, pos) {
    const [px, py] = belt.point(state, pos);
    return worldFromPicture(px, py, this.surface);
  }

  // A tray's drawn lap position: slid from one tick back by `alpha`, or the entrance for a tray not yet started
  trayPos(tray) {
    if (!tray.started) {
      return 0;
    }
    const from = this.before.get(tray.id);
    return from === undefined ? tray.pos : from + (tray.pos - from) * this.alpha;
  }

  remember(state) {
    this.before.clear();
    for (const tray of state.belt) {
      if (tray.started) {
        this.before.set(tray.id, tray.pos);
      }
    }
  }

  poseQueue(spots, [q, k]) {
    const spot = spots.queues[q];
    if (k >= spots.rows[q]) {
      this.pose.shown = false;
      return;
    }
    this.setPose(spot.x, 0, spot.z + k * spot.step, BACK_TO_CAMERA, spot.scale, k === 0 ? 1 : BEHIND_FADE);
  }

  poseSlot(spots, index) {
    const spot = spots.slots[index];
    this.setPose(spot.x, 0, spot.z, BACK_TO_CAMERA, spot.size);
  }

  poseRescue(spots, index) {
    const spot = spots.rescue[Math.min(index, spots.rescue.length - 1)];
    this.setPose(spot.x, 0, spot.z, BACK_TO_CAMERA, spot.scale);
  }

  // A pig on the belt stands on its tray and faces straight into the picture from its side
  poseBelt(state, tray) {
    const at = this.beltPoint(state, this.trayPos(tray));
    const [ix, iy] = belt.INWARD[belt.side(state, tray)];
    this.setPose(at.x, this.trayY + TRAY_TOP, at.z, Math.atan2(ix, -iy), BELT_PIG_SCALE);
  }

  poseExit(state, index) {
    const at = this.beltPoint(state, state.beltPath.end);
    this.setPose(at.x, 0, at.z + (index + 1) * EXIT_GAP, BACK_TO_CAMERA, BELT_PIG_SCALE);
  }

  poseOf(state, pig, spots, found) {
    this.pose.shown = false;
    const table = found[pig.place];
    if (!table || !table.has(pig.id)) {
      return;
    }
    const at = table.get(pig.id);
    if (pig.place === "queue") {
      this.poseQueue(spots, at);
    } else if (pig.place === "slot") {
      this.poseSlot(spots, at);
    } else if (pig.place === "rescue") {
      this.poseRescue(spots, at);
    } else if (pig.place === "belt") {
      this.poseBelt(state, at);
    } else {
      this.poseExit(state, at);
    }
  }

  writePig(i, pig) {
    const { batches, pose } = this;
    if (!pose.shown) {
      for (const name of PIG_BATCHES) {
        batches[name].setMatrixAt(i, HIDDEN);
      }
      return;
    }
    place.set(pose.x, pose.y + pose.air, pose.z);
    turn.setFromAxisAngle(UP, pose.yaw);
    matrix.compose(place, turn, size.set(pose.scale * pose.sx, pose.scale * pose.sy, pose.scale * pose.sx));
    batches.body.setMatrixAt(i, matrix);
    batches.body.setColorAt(i, pose.tint || COLORS[pig.color]);
    batches.marks.setMatrixAt(i, matrix);
    batches.face.setMatrixAt(i, matrix);
    let face = pose.face;
    if (pig.ammo === 0) {
      face = FACE_EMPTY;
    } else if (face < 0) {
      face = FACE_OPEN;
    }
    this.attributes.face.setX(i, face);
    // The shadow stays on the ground under a hopping pig and shrinks as the pig rises
    place.set(pose.x, pose.y + SHADOW_LIFT, pose.z);
    const shadow = (pose.scale * SHADOW_GROW) / (1 + pose.air * SHADOW_AIR_SHRINK);
    matrix.compose(place, turn.identity(), size.setScalar(shadow));
    batches.shadows.setMatrixAt(i, matrix);
  }

  // The ammo number stays upright on screen whichever way the pig faces. Returns how many digit quads it used
  writeDigits(first, pig) {
    const { pose } = this;
    const text = pose.text === null ? String(pig.ammo) : pose.text;
    const s = pose.scale;
    const lift = pose.y + pose.air + AMMO_ANCHOR.y * s * pose.sy + DIGIT_LIFT;
    const behindX = AMMO_ANCHOR.z * s * Math.sin(pose.yaw);
    const behindZ = AMMO_ANCHOR.z * s * Math.cos(pose.yaw);
    for (let d = 0; d < text.length; d++) {
      const at = first + d;
      place.set(pose.x + behindX + (d - (text.length - 1) / 2) * DIGIT_ADVANCE * s, lift, pose.z + behindZ);
      matrix.compose(place, turn.identity(), size.setScalar(DIGIT_SIZE * s));
      this.batches.digits.setMatrixAt(at, matrix);
      this.attributes.digit.setX(at, DIGIT_GLYPHS.indexOf(text[d]));
      this.attributes.fade.setX(at, pose.fade);
    }
    return text.length;
  }

  spotsFor(state) {
    return {
      queues: this.layout.queueSpots(state.queues.length),
      rows: this.layout.queueRows(state.queues.length),
      slots: this.layout.slotSpots(state.slots.length),
      rescue: this.layout.rescueSpots(rescueCapacity(state)),
    };
  }

  writeSlots(spots) {
    slotTint.copy(slotBase).lerp(slotAlarm, this.fx ? this.fx.slotAlarm() : 0);
    spots.slots.forEach((spot, i) => {
      place.set(spot.x, SLOT_LIFT, spot.z);
      matrix.compose(place, turn.identity(), size.setScalar(spot.size));
      this.batches.slots.setMatrixAt(i, matrix);
      this.batches.slots.setColorAt(i, slotTint);
    });
    this.batches.slots.count = spots.slots.length;
    this.batches.slots.instanceMatrix.needsUpdate = true;
    this.batches.slots.instanceColor.needsUpdate = true;
  }

  putTray(i, x, y, z, rotation) {
    place.set(x, y, z);
    matrix.compose(place, rotation, size.setScalar(1));
    this.batches.trays.setMatrixAt(i, matrix);
  }

  // Trays that left the belt since the last sync start hopping back to the stack. `trayAt` holds where each tray on the
  // belt was last drawn
  watchTrays(state, drawn) {
    const onBelt = new Set(state.belt.map((tray) => tray.id));
    for (const [id, spot] of this.trayAt) {
      if (!onBelt.has(id)) {
        this.trayAt.delete(id);
        if (this.fx) {
          this.homing.push({ x: spot[0], z: spot[1], t0: this.fx.now });
        }
      }
    }
    for (const [id, x, z] of drawn) {
      this.trayAt.set(id, [x, z]);
    }
    this.homing = this.homing.filter((tray) => this.fx.now - tray.t0 < HOP);
  }

  // Where the stack holds its tray number `index` of `total`: along the stack's line, on edge
  stackSpot(total, index) {
    const stack = this.board.anchors.tray_stack;
    const offsets = stack.positions[String(total)];
    const along = offsets ? offsets[index] : -STACK_STEP / 2 - STACK_STEP * index;
    return [stack.origin[0] + along, stack.origin[1], -stack.origin[2]];
  }

  // Trays carrying pigs ride the belt; the free ones wait on edge in a stack beside the entrance, and a tray that just
  // came off the belt hops there in an arc
  writeTrays(state) {
    let used = 0;
    const drawn = [];
    for (const tray of state.belt) {
      const at = this.beltPoint(state, this.trayPos(tray));
      this.putTray(used++, at.x, this.trayY, at.z, turn.identity());
      drawn.push([tray.id, at.x, at.z]);
    }
    this.watchTrays(state, drawn);
    const resting = Math.max(0, state.trayTotal - state.belt.length - this.homing.length);
    for (let i = 0; i < resting; i++) {
      const [x, y, z] = this.stackSpot(state.trayTotal, i);
      this.putTray(used++, x, y, z, ON_EDGE);
    }
    this.homing.forEach((tray, j) => {
      const u = (this.fx.now - tray.t0) / HOP;
      const [x, y, z] = this.stackSpot(state.trayTotal, resting + j);
      place.set(tray.x + (x - tray.x) * u, this.trayY + (y - this.trayY) * u + HOP_HEIGHT * 4 * u * (1 - u), tray.z + (z - tray.z) * u);
      turn.identity().slerp(ON_EDGE, u);
      matrix.compose(place, turn, size.setScalar(1));
      this.batches.trays.setMatrixAt(used++, matrix);
    });
    this.batches.trays.count = used;
    this.batches.trays.instanceMatrix.needsUpdate = true;
  }

  // Put every pig where this tick has it
  sync(state = this.state) {
    if (!state) {
      return;
    }
    this.state = state;
    const spots = this.spotsFor(state);
    const found = lookups(state);
    let digits = 0;
    if (this.looks) {
      this.looks.begin(state);
    }
    for (const [id, i] of this.order) {
      const pig = state.pigs[id];
      this.poseOf(state, pig, spots, found);
      this.pose.tint = null;
      this.pose.text = null;
      if (this.fx) {
        this.fx.shape(id, pig, this.pose);
      }
      if (this.looks) {
        this.looks.shape(id, pig, this.pose);
      }
      this.writePig(i, pig);
      if (this.pose.shown && this.pose.digits) {
        digits += this.writeDigits(digits, pig);
      }
    }
    this.batches.digits.count = digits;
    for (const name of [...PIG_BATCHES, "digits"]) {
      this.batches[name].instanceMatrix.needsUpdate = true;
    }
    for (const name of ["face", "digit", "fade"]) {
      this.attributes[name].needsUpdate = true;
    }
    if (this.batches.body.instanceColor) {
      this.batches.body.instanceColor.needsUpdate = true;
    }
    if (this.looks) {
      this.looks.end();
    }
    this.writeSlots(spots);
    this.writeTrays(state);
  }

  // A new level: one instance per pig, in id order, tinted by the pig's color
  build(state) {
    this.order = new Map();
    this.before.clear();
    this.trayAt.clear();
    this.homing = [];
    this.alpha = 1;
    if (this.fx) {
      this.fx.build(state);
    }
    if (this.looks) {
      this.looks.build(state);
    }
    const ids = Object.keys(state.pigs).map(Number).sort((a, b) => a - b);
    ids.forEach((id, i) => {
      this.order.set(id, i);
      this.batches.body.setColorAt(i, tint.copy(COLORS[state.pigs[id].color]));
    });
    for (const name of PIG_BATCHES) {
      this.batches[name].count = ids.length;
    }
    if (this.batches.body.instanceColor) {
      this.batches.body.instanceColor.needsUpdate = true;
    }
    this.forgetBoxes();
    this.sync(state);
  }

  // The camera moved: the press boxes are worked out again on the next press
  forgetBoxes() {
    this.pressBoxes = null;
  }

  // The floor the queues end above moved: the rows that fit change, so the boxes are worked out again, and the pigs are
  // drawn again
  relimit() {
    this.forgetBoxes();
    this.sync();
  }

  // The column changed shape: the boxes and every pig's place are worked out again
  refresh() {
    this.forgetBoxes();
    if (this.fx) {
      this.fx.forget();
    }
    this.sync();
  }

  // The boxes of everything a press can land on, grown to a finger's size, from the camera once per resize
  boxes() {
    const capacity = this.state ? rescueCapacity(this.state) : 0;
    if (!this.pressBoxes || this.pressBoxes.capacity !== capacity) {
      const raw = this.layout.screenBoxes(capacity);
      this.pressBoxes = {
        capacity,
        slots: raw.slots.map((box) => grown(box, MIN_HIT)),
        rescue: raw.rescue.map((box) => grown(box, MIN_HIT)),
        queues: raw.queues.map((q) => grown(q.column, MIN_HIT)),
        rows: this.layout.pickBoxes().map((list) => list.map((box) => grown(box, MIN_HIT))),
      };
    }
    return this.pressBoxes;
  }

  // The queue pig nearest the press among the pigs drawn there (the Hand's pick), as [queue, index]
  pick(x, y) {
    const { state } = this;
    if (!state) {
      return null;
    }
    const { rows } = this.boxes();
    let best = null;
    let bestDistance = Infinity;
    state.queues.forEach((ids, q) => {
      const count = Math.min(ids.length, rows[q] ? rows[q].length : 0);
      for (let k = 0; k < count; k++) {
        const distance = inside(rows[q][k], x, y) ? distanceToMiddle(rows[q][k], x, y) : Infinity;
        if (distance < bestDistance) {
          bestDistance = distance;
          best = [q, k];
        }
      }
    });
    return best;
  }

  // The occupied slot or rescue pig nearest the press, else the queue column it is in
  hit(x, y) {
    const { state } = this;
    if (!state) {
      return null;
    }
    const b = this.boxes();
    const near = [];
    state.slots.forEach((id, i) => id !== null && inside(b.slots[i], x, y) && near.push([["s", i], b.slots[i]]));
    state.rescue.forEach((id, i) => {
      const box = b.rescue[Math.min(i, b.rescue.length - 1)];
      if (inside(box, x, y)) {
        near.push([["r", i], box]);
      }
    });
    if (near.length) {
      near.sort((a, c) => distanceToMiddle(a[1], x, y) - distanceToMiddle(c[1], x, y));
      return near[0][0];
    }
    const column = b.queues.findIndex((box, q) => state.queues[q].length > 0 && inside(box, x, y));
    return column < 0 ? null : ["q", column];
  }
}

// Load the models and pictures and make the pig group. `scene` is the THREE scene its batches are added to
export async function createPigs(scene, layout, board) {
  return new PigGroup(await makeBatches(scene), layout, board);
}
