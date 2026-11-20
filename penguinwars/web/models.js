// Every shape in the game, built in one place so a Blender model can replace any of them without touching scene.js.
// Round penguins and grey seals with collars, made of simple rounded shapes.

// One color per seat: the ring on the ice under its penguin, and its seal's collar
export const SEAT_COLORS = ["#ffcf33", "#ff5a5f", "#2ec4b6", "#9b6bff", "#ff8c42", "#5bd16f"];
// Penguins are drawn this much bigger than their shapes' sizes below
export const PENGUIN_SCALE = 1.3;
// The middle of a penguin's head, where a hat sits, in the same sizes as the shapes below
export const HEAD_HEIGHT = 0.88;
// The middle of a penguin's back, on its skin, where a pack or a cape hangs
const BACK_SPOT = [0, 0.45, -0.27];
// The middle of a penguin's neck, level with the crease where its head meets its body, which a scarf goes round
const NECK_SPOT = [0, 0.74, 0];
const SEAL_SCALE = 1.1;
// The game's camera looks down at this angle. Particles never turn, so flat ones are built leaning toward it
const CAMERA_PITCH = 52;
const TAU = Math.PI * 2;
// Sixteen numbers place one copy of a shape, and no ice reaches further from the middle than this
const MATRIX = 16;
// How far the largest floe reaches from its middle, tile edges included
const FLOE_REACH = 5;

export function paint(hex, options = {}) {
  const material = new pc.StandardMaterial();
  material.diffuse = new pc.Color().fromString(hex);
  material.useMetalness = true;
  material.metalness = 0;
  material.gloss = options.gloss ?? 0.3;
  if (options.emissive) {
    material.emissive = new pc.Color().fromString(options.emissive);
  }
  if (options.opacity !== undefined) {
    material.opacity = options.opacity;
    material.blendType = pc.BLEND_NORMAL;
    material.depthWrite = false;
  }
  material.update();
  return material;
}

export function shape(parent, type, material, position, scale, rotation, shadow = true) {
  const entity = new pc.Entity();
  entity.addComponent("render", { type, material, castShadows: shadow, receiveShadows: true });
  if (position) {
    entity.setLocalPosition(position[0], position[1], position[2]);
  }
  if (typeof scale === "number") {
    entity.setLocalScale(scale, scale, scale);
  } else if (scale) {
    entity.setLocalScale(scale[0], scale[1], scale[2]);
  }
  if (rotation) {
    entity.setLocalEulerAngles(rotation[0], rotation[1], rotation[2]);
  }
  parent.addChild(entity);
  return entity;
}

export function meshShape(parent, mesh, material, shadow = true) {
  const entity = new pc.Entity();
  entity.addComponent("render", {
    meshInstances: [new pc.MeshInstance(mesh, material)],
    castShadows: shadow,
    receiveShadows: true,
  });
  parent.addChild(entity);
  return entity;
}

// Unit shapes, the same ones the engine draws for a render component's "sphere", "cone", "torus" and "box"
const PART_SHAPES = {
  sphere: () => new pc.SphereGeometry({ radius: 0.5 }),
  // The same ball in many more faces, for two big shapes that cross each other: with few faces the line where they
  // cross is jagged
  fine: () => new pc.SphereGeometry({ radius: 0.5, latitudeBands: 40, longitudeBands: 40 }),
  cone: () => new pc.ConeGeometry({ baseRadius: 0.5, peakRadius: 0, height: 1 }),
  torus: () => new pc.TorusGeometry({ tubeRadius: 0.2, ringRadius: 0.3 }),
  box: () => new pc.BoxGeometry(),
};

const sides = (make) => [make(-1), make(1)];

// A model's parts that never move against each other become one mesh per material, so they cost one draw each. These
// tables hold them by material as [shape, spot, size, turn]. A penguin's flippers move, so they stay shapes of their own.
// Nothing covers the line where the belly comes out of the body, so those two are the fine shape
const PENGUIN_PIECES = {
  dark: [
    ["fine", [0, 0.42, 0], [0.62, 0.8, 0.56]],
    ["sphere", [0, 0.88, 0], 0.44],
  ],
  white: [
    ["fine", [0, 0.38, 0.12], [0.48, 0.62, 0.36]],
    ["sphere", [0, 0.86, 0.1], [0.32, 0.28, 0.26]],
    ...sides((side) => ["sphere", [side * 0.062, 0.945, 0.236], 0.024]),
  ],
  orange: [
    ...sides((side) => ["sphere", [side * 0.1, 0.03, 0.1], [0.16, 0.06, 0.24]]),
    ["cone", [0, 0.85, 0.27], [0.12, 0.16, 0.12], [90, 0, 0]],
  ],
  eye: sides((side) => ["sphere", [side * 0.075, 0.93, 0.205], 0.07]),
};

const SEAL_PIECES = {
  grey: [
    ["sphere", [0, 0, -0.1], [0.62, 0.46, 1.15]],
    ["sphere", [0, 0.16, 0.42], 0.44],
    ...sides((side) => ["sphere", [side * 0.33, -0.08, 0.12], [0.34, 0.06, 0.2], [0, side * 25, side * -15]]),
    ["sphere", [0, -0.02, -0.7], [0.42, 0.06, 0.22]],
  ],
  light: [["sphere", [0, 0.1, 0.62], [0.26, 0.18, 0.2]]],
  eye: [
    ["sphere", [0, 0.15, 0.72], 0.07],
    ...sides((side) => ["sphere", [side * 0.11, 0.27, 0.58], 0.08]),
  ],
  white: sides((side) => ["sphere", [side * 0.1, 0.29, 0.615], 0.025]),
  collar: [["torus", [0, 0.12, 0.28], [0.62, 0.5, 0.62], [70, 0, 0]]],
};

const FISH_PIECES = {
  orange: [
    ["sphere", [0, 0, 0], [0.24, 0.22, 0.56]],
    ["cone", [0, 0, -0.36], [0.06, 0.22, 0.34], [90, 0, 0]],
  ],
  belly: [["sphere", [0, -0.04, 0.03], [0.18, 0.13, 0.42]]],
  eye: sides((side) => ["sphere", [side * 0.09, 0.05, 0.17], 0.05]),
};

const BEAK_FISH_PIECES = [
  ["sphere", [0, 0, 0], [0.11, 0.1, 0.27]],
  ["cone", [0, 0, -0.17], [0.03, 0.1, 0.15], [90, 0, 0]],
];

function placement(spot, size, turn) {
  const sizes = typeof size === "number" ? [size, size, size] : size;
  return new pc.Mat4().setTRS(
    new pc.Vec3(...spot),
    new pc.Quat().setFromEulerAngles(...(turn ?? [0, 0, 0])),
    new pc.Vec3(...sizes),
  );
}

// Adds one shape, moved by `place`, to the lists a mesh is made from
function addShape(lists, { positions, normals, indices }, place) {
  const facing = place.clone().invert().transpose();
  const start = lists.positions.length / 3;
  const point = new pc.Vec3();
  for (let i = 0; i < positions.length; i += 3) {
    point.set(positions[i], positions[i + 1], positions[i + 2]);
    place.transformPoint(point, point);
    lists.positions.push(point.x, point.y, point.z);
    point.set(normals[i], normals[i + 1], normals[i + 2]);
    facing.transformVector(point, point).normalize();
    lists.normals.push(point.x, point.y, point.z);
  }
  lists.indices.push(...indices.map((index) => index + start));
}

// A mesh from those lists. It stays made with nobody wearing it, as hats come and go and penguins are rebuilt when a
// player changes seats
function finishMesh(device, lists) {
  const mesh = new pc.Mesh(device);
  mesh.setPositions(lists.positions);
  mesh.setNormals(lists.normals);
  if (lists.colors) {
    mesh.setColors(lists.colors);
  }
  mesh.setIndices(lists.indices);
  mesh.update();
  mesh.incRefCount();
  return mesh;
}

function mergedMesh(device, pieces) {
  const lists = { positions: [], normals: [], indices: [] };
  for (const [kind, spot, size, turn] of pieces) {
    addShape(lists, PART_SHAPES[kind](), placement(spot, size, turn));
  }
  return finishMesh(device, lists);
}

// One merged mesh for each material in a table
function mergedShapes(device, table) {
  return Object.fromEntries(Object.entries(table).map(([name, pieces]) => [name, mergedMesh(device, pieces)]));
}

// Many copies of one shape, each in a slot of its own, drawn in one go. An empty slot draws nothing
export class Copies {
  constructor(app, mesh, material, slots, shadow) {
    const device = app.graphicsDevice;
    this.buffer = new pc.VertexBuffer(device, pc.VertexFormat.getDefaultInstancingFormat(device), slots, {
      usage: pc.BUFFER_DYNAMIC,
    });
    this.cells = new Float32Array(this.buffer.lock());
    this.cells.fill(0);
    this.changed = true;
    const instance = new pc.MeshInstance(mesh, material);
    instance.setInstancing(this.buffer);
    instance.instancingCount = slots;
    instance.cull = false;
    const root = new pc.Entity();
    root.addComponent("render", { meshInstances: [instance], castShadows: shadow, receiveShadows: true });
    // The copies are anywhere, whatever box the one shape has. The sun fits its shadow depth to the boxes of what casts
    // one, so this box holds the whole floe. It goes on last: handing over the mesh above clears any box set before it
    root.render.customAabb = new pc.BoundingBox(pc.Vec3.ZERO, new pc.Vec3(FLOE_REACH, 1, FLOE_REACH));
    app.root.addChild(root);
    // Switched off while no slot is in use, the copies cost no draw at all
    this.root = root;
  }

  place(slot, matrix) {
    this.cells.set(matrix.data, slot * MATRIX);
    this.changed = true;
  }

  empty(slot) {
    this.cells.fill(0, slot * MATRIX, (slot + 1) * MATRIX);
    this.changed = true;
  }

  // Sends this frame's changes to the graphics card
  flush() {
    if (this.changed) {
      this.buffer.unlock();
      this.changed = false;
    }
  }
}

// Materials and meshes every model shares. Made on first use, once the engine has a graphics device
let sharedKit = null;

function shared(app) {
  if (!sharedKit) {
    sharedKit = {
      device: app.graphicsDevice,
      dark: paint("#1b2230", { gloss: 0.35 }),
      white: paint("#f4f8fb", { gloss: 0.25 }),
      orange: paint("#ff9a1f", { gloss: 0.4 }),
      eye: paint("#06080c", { gloss: 0.8 }),
      sealGrey: paint("#6d7d8a", { gloss: 0.6 }),
      sealLight: paint("#9aa8b3", { gloss: 0.5 }),
      fish: paint("#ff8a3d", { gloss: 0.7, emissive: "#3a1a00" }),
      fishBelly: paint("#ffe2b8", { gloss: 0.5 }),
      gold: paint("#000000", { emissive: "#ffd23f" }),
      ringReady: paint("#000000", { emissive: "#ffcf33" }),
      ringWait: paint("#000000", { emissive: "#4d5c66" }),
      ringMesh: pc.Mesh.fromGeometry(
        app.graphicsDevice,
        new pc.TorusGeometry({ tubeRadius: 0.045, ringRadius: 0.56, segments: 40 }),
      ),
      penguin: mergedShapes(app.graphicsDevice, PENGUIN_PIECES),
      seal: mergedShapes(app.graphicsDevice, SEAL_PIECES),
      fishBody: mergedShapes(app.graphicsDevice, FISH_PIECES),
      beakFish: mergedMesh(app.graphicsDevice, BEAK_FISH_PIECES),
      crate: bakedMesh(app.graphicsDevice, CRATE_PIECES),
      mark: flatRings(app.graphicsDevice, MARK_RINGS),
      bubble: bakedMesh(app.graphicsDevice, BUBBLE_PIECES),
      ice: bakedMesh(app.graphicsDevice, ICE_PIECES),
      glass: glassMaterial(),
      markGlow: markMaterial(),
      colorRings: new Map(),
    };
  }
  return sharedKit;
}

// The flippers take the body's color, so each one's shape joins `coat`, the list a skin repaints
function buildFlippers(body, material, coat) {
  return [-1, 1].map((side) => {
    const flipper = new pc.Entity();
    flipper.setLocalPosition(side * 0.27, 0.6, 0);
    body.addChild(flipper);
    coat.push(shape(flipper, "sphere", material, [side * 0.04, -0.17, 0], [0.1, 0.42, 0.22]));
    return flipper;
  });
}

// A little fish held crosswise in the beak while a fish is saved up
function buildBeakFish(body, kit) {
  const beakFish = new pc.Entity("beak-fish");
  beakFish.setLocalPosition(0, 0.82, 0.36);
  beakFish.setLocalEulerAngles(0, 90, 0);
  body.addChild(beakFish);
  meshShape(beakFish, kit.beakFish, kit.fish, false);
  beakFish.enabled = false;
  return beakFish;
}

function buildRing(root, kit) {
  const ring = meshShape(root, kit.ringMesh, kit.ringReady, false);
  ring.name = "ring";
  ring.setLocalPosition(0, 0.01, 0);
  return ring;
}

// The ring on the ice that shows whose penguin this is: flat, see-through and a third as wide as the ring under the
// player's own penguin, so that one still stands out. Rings from the middle out, each [how far out, how solid]. It
// has no shadow under it and no bright color of its own, which a crate's mark and a snowball's have
const COLOR_RING = [
  [0.505, "00"],
  [0.52, "b8"],
  [0.55, "b8"],
  [0.565, "00"],
];

// One mesh for each seat color, made when the first penguin of that color is built
function buildColorRing(root, kit, color) {
  if (!kit.colorRings.has(color)) {
    const rings = COLOR_RING.map(([far, solid]) => [far, color, solid]);
    kit.colorRings.set(color, flatRings(kit.device, rings, 40));
  }
  const ring = meshShape(root, kit.colorRings.get(color), groundMaterial(), false);
  ring.name = "color-ring";
  ring.setLocalPosition(0, 0.012, 0);
  return ring;
}

// Only the player's own penguin (`mine`) has the thin ring under it that shows when its next move is ready. Every
// other penguin on the ice has a fainter ring in its seat's `color`, and one with no `color` has none: the wardrobe's
// penguin stands on no ice. The moving parts come back for scene.js to pose
export function buildPenguin(app, color, mine) {
  const kit = shared(app);
  const root = new pc.Entity();
  root.setLocalScale(PENGUIN_SCALE, PENGUIN_SCALE, PENGUIN_SCALE);
  app.root.addChild(root);
  const tilt = new pc.Entity();
  tilt.setLocalPosition(0, 0.32, 0);
  root.addChild(tilt);
  const body = new pc.Entity();
  body.setLocalPosition(0, -0.32, 0);
  tilt.addChild(body);
  // The shapes a skin repaints, by the part of the skin's palette each takes
  const coat = {
    body: [meshShape(body, kit.penguin.dark, kit.dark)],
    belly: [meshShape(body, kit.penguin.white, kit.white)],
    beak: [meshShape(body, kit.penguin.orange, kit.orange)],
  };
  meshShape(body, kit.penguin.eye, kit.eye, false);
  const flippers = buildFlippers(body, kit.dark, coat.body);
  const beakFish = buildBeakFish(body, kit);
  // A hat and a face item both hang from the middle of the head, each on its own spot so one swaps without the other
  const head = wornSpot(body, "hat", [0, HEAD_HEIGHT, 0]);
  const face = wornSpot(body, "face", [0, HEAD_HEIGHT, 0]);
  const neck = wornSpot(body, "neck", NECK_SPOT);
  const back = wornSpot(body, "back", BACK_SPOT);
  const shieldMat = paint("#c4ecff", { opacity: 0.3, emissive: "#3d7d99" });
  const shield = shape(root, "sphere", shieldMat, [0, 0.5, 0], [1.25, 1.15, 1.25], null, false);
  shield.name = "shield";
  shield.enabled = false;
  // A crate's shield is a bubble round the whole penguin, and its frost a block of ice on the body, lying down with it
  const bubble = meshShape(root, kit.bubble, kit.glass, false);
  bubble.name = "bubble";
  bubble.setLocalPosition(0, BUBBLE_HEIGHT, 0);
  bubble.enabled = false;
  const ice = meshShape(body, kit.ice, kit.glass, false);
  ice.name = "ice";
  ice.enabled = false;
  const ring = mine ? buildRing(root, kit) : null;
  const colorRing = color && !mine ? buildColorRing(root, kit, color) : null;
  const worn = { head, face, neck, back };
  return { root, tilt, body, flippers, ring, colorRing, beakFish, shield, shieldMat, bubble, ice, ...worn, coat };
}

// ---------- Skins ----------

// A penguin's own colors by the id the bot knows each skin by: its body and flippers, its belly and face, and its beak
// and feet. `gloss` shines the body, and `glow` and `bellyGlow` light the body and the belly a little from inside
export const SKINS = {
  emperor: { body: "#2f4468", belly: "#ffe08a", beak: "#ff6b4a", gloss: 0.45 },
  snowy: { body: "#b3d3ee", belly: "#ffffff", beak: "#ffa53d", gloss: 0.5 },
  bubblegum: { body: "#ff5fa8", belly: "#ffe3f1", beak: "#ffd23f", gloss: 0.6 },
  midnight: { body: "#33248f", belly: "#b3bdff", beak: "#ffd76a", gloss: 0.6, glow: "#150c4a" },
  ember: { body: "#4f1a10", belly: "#ff8a2a", beak: "#ffd23f", glow: "#4a0f00", bellyGlow: "#8a3200" },
  steel: { body: "#8795a8", belly: "#dfe6ee", beak: "#566173", gloss: 0.9 },
  golden: { body: "#f2b21a", belly: "#ffeaa3", beak: "#ff7b1a", gloss: 0.85, glow: "#4a3000" },
};

// A skin's three materials, made the first time anyone wears it and shared by everyone who does
const skinMaterials = new Map();
// The classic black and white, in the materials every penguin is built with
let classicSkin = null;

function skinOf(id) {
  if (!Object.hasOwn(SKINS, id ?? "")) {
    classicSkin ??= { body: sharedKit.dark, belly: sharedKit.white, beak: sharedKit.orange };
    return classicSkin;
  }
  if (!skinMaterials.has(id)) {
    const { body, belly, beak, gloss, glow, bellyGlow } = SKINS[id];
    skinMaterials.set(id, {
      body: paint(body, { gloss: gloss ?? 0.35, emissive: glow }),
      belly: paint(belly, { gloss: 0.25, emissive: bellyGlow }),
      beak: paint(beak, { gloss: 0.4 }),
    });
  }
  return skinMaterials.get(id);
}

const COAT_PARTS = ["body", "belly", "beak"];

// Recolors a built penguin. `id` is a skin, or null for the classic black and white
export function paintSkin(parts, id) {
  const skin = skinOf(id);
  for (const part of COAT_PARTS) {
    for (const entity of parts.coat[part]) {
      const instance = entity.render.meshInstances[0];
      if (instance.material !== skin[part]) {
        instance.material = skin[part];
      }
    }
  }
}

// The ring under the player's penguin shows when the next slide or brace is ready
export function setRingReady(ring, ready) {
  const instance = ring.render.meshInstances[0];
  const material = ready ? sharedKit.ringReady : sharedKit.ringWait;
  if (instance.material !== material) {
    instance.material = material;
  }
}

// The arrow that shows where the player's slide goes. input.js sets its length and color
export function buildArrow(app) {
  const root = new pc.Entity("arrow");
  app.root.addChild(root);
  const material = paint("#000000", { emissive: "#ffcf33" });
  const shaft = shape(root, "box", material, [0, 0, 0.5], [0.16, 0.03, 1], null, false);
  const head = shape(root, "cone", material, [0, 0, 1], [0.44, 0.34, 0.06], [90, 0, 0], false);
  root.enabled = false;
  return { root, material, shaft, head };
}

export function buildSeal(app, color) {
  const kit = shared(app);
  const root = new pc.Entity();
  root.setLocalScale(SEAL_SCALE, SEAL_SCALE, SEAL_SCALE);
  app.root.addChild(root);
  const pivot = new pc.Entity();
  root.addChild(pivot);
  meshShape(pivot, kit.seal.grey, kit.sealGrey);
  meshShape(pivot, kit.seal.light, kit.sealLight);
  meshShape(pivot, kit.seal.eye, kit.eye, false);
  meshShape(pivot, kit.seal.white, kit.white, false);
  meshShape(pivot, kit.seal.collar, paint(color, { gloss: 0.2 }));
  // Tipped back so the brim clears the eyes, which sit higher on a seal's head than on a penguin's
  const head = wornSpot(pivot, "hat", [0, 0.16, 0.42], [-24, 0, 0]);
  root.enabled = false;
  return { root, pivot, head };
}

export function buildFish(app) {
  const kit = shared(app);
  const root = new pc.Entity();
  app.root.addChild(root);
  const glow = meshShape(root, kit.ringMesh, kit.gold, false);
  glow.setLocalScale(0.85, 1, 0.85);
  const body = new pc.Entity();
  body.setLocalPosition(0, 0.16, 0);
  root.addChild(body);
  meshShape(body, kit.fishBody.orange, kit.fish);
  meshShape(body, kit.fishBody.belly, kit.fishBelly);
  meshShape(body, kit.fishBody.eye, kit.eye, false);
  root.enabled = false;
  return { root, glow, body };
}

// ---------- Things a penguin wears ----------

const TOY_RED = "#e8413c";
const TOY_WHITE = "#fbf7ee";
const TOY_PINK = "#ff4f9e";
const TOY_YELLOW = "#ffd23f";
const TOY_TEAL = "#28c7b7";
const TOY_BLACK = "#2a2e3b";
const TOY_GOLD = "#ffc933";
const TOY_LEAF = "#46b35a";
const TOY_ICE = "#6fcdfb";
const TOY_FISH = "#ff8a3d";
const TOY_TAN = "#cf8f4d";
const TOY_BROWN = "#74401f";
const TOY_BLUE = "#2f7df6";
const TOY_STEEL = "#97a6ba";
const TOY_PURPLE = "#7a48f0";
const TOY_ORANGE = "#ff7a1a";
const TOY_SKY = "#a8e6ff";
const TOY_SHARK = "#4f779f";
const TOY_SHADE = "#c3d0e0";

// How far up the two sides of a rolled brim come, for a brim one across
const BRIM_ROLL = 0.45;
// A fin one tall and one long at its base: how far forward it leans as it leaves the base, how far back it has
// curved by its tip, and how long the tip is beside the base
const FIN_LEAN = 0.45;
const FIN_SWEEP = 0.6;
const FIN_TIP = 0.04;

// Unit shapes the things worn are put together from, each about one across
const TOY_SHAPES = {
  ball: () => new pc.SphereGeometry({ latitudeBands: 10, longitudeBands: 14 }),
  cone: () => new pc.ConeGeometry({ heightSegments: 1, capSegments: 16 }),
  tube: () => new pc.CylinderGeometry({ heightSegments: 1, capSegments: 16 }),
  ring: () => new pc.TorusGeometry({ tubeRadius: 0.1, ringRadius: 0.45, segments: 24, sides: 8 }),
  // A thin ring, one across
  hoop: () => new pc.TorusGeometry({ tubeRadius: 0.03, ringRadius: 0.5, segments: 32, sides: 6 }),
  block: () => new pc.BoxGeometry(),
  // A cone with its point cut off, a little over half as wide on top as underneath
  taper: () => new pc.ConeGeometry({ peakRadius: 0.28, heightSegments: 1, capSegments: 16 }),
  // A shark's back fin, standing along y with its front toward +z. The front edge leans back in a curve, the back
  // edge hollows, and both meet in a narrow tip over the back half of the base
  fin: () => {
    const fin = new pc.CylinderGeometry({ heightSegments: 12, capSegments: 16 });
    const { positions } = fin;
    for (let i = 0; i < positions.length; i += 3) {
      const up = positions[i + 1] + 0.5;
      const across = FIN_TIP + (1 - FIN_TIP) * (1 - up) ** 0.7;
      positions[i] *= across;
      positions[i + 2] = positions[i + 2] * across + FIN_LEAN * up - FIN_SWEEP * up * up;
    }
    fin.calculateNormals();
    return fin;
  },
  // A round hat brim, a tenth as thick as it is wide, whose two sides roll up. It is flat from front to back
  brim: () => {
    const disc = new pc.CylinderGeometry({ heightSegments: 1, capSegments: 24 });
    const { positions } = disc;
    for (let i = 0; i < positions.length; i += 3) {
      positions[i + 1] = positions[i + 1] * 0.1 + BRIM_ROLL * (positions[i] * 2) ** 2;
    }
    disc.calculateNormals();
    return disc;
  },
};

// `n` things evenly around a circle, each from its angle and its number: petals, a crown's points, particle outlines
function around(n, at) {
  return Array.from({ length: n }, (unused, index) => at((index / n) * TAU, index));
}

// Each hat as [shape, color, spot, size, turn], measured from the middle of the head, whose edge is 0.22 away, and a
// `lean` for the whole hat. Eyes reach up to 0.085 on a penguin's head, so everything stays above that at the front.
// A snorkel's tube leans out to the penguin's right, 0.33 from the middle at that height and further as it rises, so a
// brim stays inside that. `glass` makes a hat see-through and `glow` lights it from inside
const HAT_LOOKS = {
  beanie: {
    lean: [-10, 0, 7],
    pieces: [
      ["ball", TOY_RED, [0, 0.17, -0.01], [0.47, 0.4, 0.47]],
      ["tube", TOY_WHITE, [0, 0.135, 0], [0.5, 0.1, 0.5]],
      ["ball", TOY_WHITE, [0, 0.4, -0.01], 0.17],
    ],
  },
  party: {
    lean: [-6, 0, -14],
    pieces: [
      ["cone", TOY_PINK, [0, 0.38, 0], [0.42, 0.5, 0.42]],
      ["ring", TOY_YELLOW, [0, 0.235, 0], [0.34, 0.5, 0.34]],
      ["ring", TOY_TEAL, [0, 0.355, 0], [0.235, 0.42, 0.235]],
      ["ring", TOY_YELLOW, [0, 0.455, 0], [0.145, 0.36, 0.145]],
      ["ball", TOY_YELLOW, [0, 0.64, 0], 0.15],
    ],
  },
  tophat: {
    lean: [-9, 0, 9],
    pieces: [
      ["tube", TOY_BLACK, [0, 0.17, 0], [0.66, 0.035, 0.66]],
      ["tube", TOY_BLACK, [0, 0.37, 0], [0.38, 0.38, 0.38]],
      ["tube", TOY_RED, [0, 0.24, 0], [0.41, 0.1, 0.41]],
    ],
  },
  flower: {
    lean: [24, 0, -12],
    pieces: [
      ...around(6, (angle, index) => [
        "ball",
        TOY_PINK,
        [Math.sin(angle) * 0.15, 0.245, Math.cos(angle) * 0.15],
        [0.17, 0.07, 0.25],
        [0, index * 60, 0],
      ]),
      ["ball", TOY_YELLOW, [0, 0.27, 0], [0.17, 0.1, 0.17]],
      ["ball", TOY_LEAF, [0.22, 0.2, -0.13], [0.11, 0.05, 0.24], [0, 60, 12]],
      ["ball", TOY_LEAF, [-0.22, 0.2, -0.13], [0.11, 0.05, 0.24], [0, -60, -12]],
    ],
  },
  // The brim is one piece whose sides roll up
  cowboy: {
    lean: [-8, 0, 6],
    pieces: [
      ["brim", TOY_TAN, [0, 0.165, 0], [0.72, 0.26, 0.82]],
      ["tube", TOY_TAN, [0, 0.26, 0], [0.38, 0.2, 0.44]],
      ["ball", TOY_TAN, [0, 0.36, 0], [0.38, 0.14, 0.44]],
      ["tube", TOY_BROWN, [0, 0.205, 0], [0.4, 0.06, 0.46]],
      ["ball", TOY_GOLD, [0, 0.205, 0.225], 0.07],
    ],
  },
  crown: {
    lean: [-6, 0, 0],
    pieces: [
      ["ball", TOY_RED, [0, 0.24, 0], [0.36, 0.2, 0.36]],
      ["tube", TOY_GOLD, [0, 0.19, 0], [0.46, 0.11, 0.46]],
      ...around(5, (angle) => [
        "cone",
        TOY_GOLD,
        [Math.sin(angle) * 0.2, 0.32, Math.cos(angle) * 0.2],
        [0.15, 0.2, 0.15],
      ]),
      ...around(5, (angle) => [
        "ball",
        TOY_RED,
        [Math.sin(angle) * 0.232, 0.19, Math.cos(angle) * 0.232],
        0.06,
      ]),
    ],
  },
  // See-through shapes draw in the order they are listed, so the fish comes last and reads clearly inside the ice
  iceblock: {
    lean: [-5, 22, 5],
    glass: true,
    pieces: [
      ["block", TOY_ICE, [0, 0.33, 0], [0.42, 0.34, 0.42]],
      ["block", TOY_WHITE, [0, 0.515, 0], [0.45, 0.04, 0.45]],
      ["ball", TOY_FISH, [0.02, 0.33, 0.05], [0.2, 0.11, 0.08]],
      ["cone", TOY_FISH, [-0.11, 0.33, 0.05], [0.1, 0.12, 0.04], [0, 0, -90]],
    ],
  },
  propeller: {
    lean: [-8, 0, -6],
    pieces: [
      ["ball", TOY_BLUE, [0, 0.17, -0.01], [0.47, 0.4, 0.47]],
      ["ring", TOY_YELLOW, [0, 0.13, -0.01], [0.45, 0.4, 0.45]],
      ["ball", TOY_RED, [0, 0.125, 0.24], [0.3, 0.05, 0.2]],
      ["tube", TOY_YELLOW, [0, 0.41, -0.01], [0.05, 0.1, 0.05]],
      ["ball", TOY_RED, [0.16, 0.47, -0.01], [0.32, 0.04, 0.13], [20, 0, 0]],
      ["ball", TOY_YELLOW, [-0.16, 0.47, -0.01], [0.32, 0.04, 0.13], [-20, 0, 0]],
      ["ball", TOY_YELLOW, [0, 0.47, -0.01], 0.09],
    ],
  },
  chef: {
    lean: [-7, 0, 6],
    pieces: [
      ["tube", TOY_WHITE, [0, 0.24, 0], [0.45, 0.26, 0.45]],
      ["tube", TOY_SHADE, [0, 0.135, 0], [0.47, 0.05, 0.47]],
      ["ball", TOY_WHITE, [0, 0.44, 0], [0.5, 0.26, 0.5]],
      ...around(5, (angle) => [
        "ball",
        TOY_WHITE,
        [Math.sin(angle) * 0.17, 0.45, Math.cos(angle) * 0.17],
        [0.3, 0.26, 0.3],
      ]),
    ],
  },
  viking: {
    lean: [-8, 0, 0],
    pieces: [
      ["ball", TOY_STEEL, [0, 0.15, -0.01], [0.5, 0.44, 0.5]],
      ["tube", TOY_GOLD, [0, 0.145, -0.01], [0.52, 0.09, 0.52]],
      ["ball", TOY_GOLD, [0, 0.2, -0.01], [0.08, 0.38, 0.53]],
      ...sides((side) => ["cone", TOY_WHITE, [side * 0.31, 0.34, -0.01], [0.15, 0.34, 0.15], [0, 0, side * -32]]),
      ...sides((side) => ["ball", TOY_GOLD, [side * 0.235, 0.22, -0.01], 0.15]),
    ],
  },
  wizard: {
    lean: [-10, 0, -8],
    pieces: [
      ["tube", TOY_PURPLE, [0, 0.15, 0], [0.66, 0.035, 0.66]],
      ["cone", TOY_PURPLE, [0, 0.4, 0], [0.42, 0.5, 0.42]],
      ["cone", TOY_PURPLE, [0.035, 0.63, 0], [0.13, 0.22, 0.13], [0, 0, -35]],
      ["tube", TOY_GOLD, [0, 0.2, 0], [0.39, 0.07, 0.39]],
      ["ball", TOY_GOLD, [0.02, 0.36, 0.125], 0.08],
      ["ball", TOY_GOLD, [-0.1, 0.28, 0.13], 0.06],
      ["ball", TOY_GOLD, [0.12, 0.3, -0.08], 0.06],
    ],
  },
  // Tipped toward the face, so its hole shows from in front as well as from above
  halo: {
    lean: [16, 0, 6],
    glow: true,
    pieces: [["ring", TOY_GOLD, [0, 0.44, 0.1], [0.5, 0.5, 0.5]]],
  },
};

// The two arms of a pair of glasses, as [shape, color, spot, size, turn] like every piece. Each runs from a hinge at
// the outer edge of its lens back along the side of the head, bends in round the back of it and ends in a tip that
// hooks down. `hinge` is how far out and how far forward the hinge is
function glassesArms(color, [out, forward]) {
  // Where an arm meets the widest part of the head, just outside its skin
  const ear = [0.229, 0.02];
  const [long, turn] = [Math.hypot(ear[0] - out, forward - ear[1]), Math.atan2(out - ear[0], forward - ear[1])];
  return sides((side) => [
    [
      "block",
      color,
      [(side * (out + ear[0])) / 2, 0.045, (forward + ear[1]) / 2],
      [0.02, 0.026, long + 0.02],
      [0, (side * turn * 180) / Math.PI, 0],
    ],
    ["block", color, [side * 0.223, 0.045, -0.025], [0.02, 0.026, 0.1], [0, side * 7.5, 0]],
    ["ball", color, [side * 0.214, 0.03, -0.075], [0.024, 0.055, 0.03]],
  ]).flat();
}

// A round rim about one eye, wide enough to show the whole eye through it. The game's camera looks down from in front,
// and from there anything standing in front of an eye is seen below it. So the rim sits at the eye's own depth, with
// the eye bulging through it, and its top tips back toward the head, which keeps it round from above
function eyeRim(side, color) {
  return ["ring", color, [side * 0.08, 0.05, 0.222], [0.135, 0.14, 0.135], [70, side * 18, 0]];
}

// Each face item the same way, from the same middle of the head, where the face looks along +z. The eyes are 0.075
// to each side, 0.05 up and 0.07 across, and their fronts are 0.24 forward. In front of the face no hat comes lower
// than 0.11, so nothing here reaches far above that in front. A strap may rise higher round the head, where a hat
// covers it. A snorkel's tube is the one thing that rises clear, leaning out wide of every brim
const FACE_LOOKS = {
  // Each lens turns a little round the face, so its outer edge sits near the head
  shades: {
    lean: [0, 0, 0],
    pieces: [
      ...sides((side) => ["block", TOY_BLACK, [side * 0.105, 0.035, 0.245], [0.16, 0.11, 0.04], [0, side * 14, 0]]),
      ["block", TOY_BLACK, [0, 0.07, 0.255], [0.08, 0.035, 0.04]],
      ...glassesArms(TOY_BLACK, [0.18, 0.225]),
      ...sides((side) => [
        "block",
        TOY_WHITE,
        [side * 0.105 - 0.03, 0.055, 0.266 + side * 0.008],
        [0.06, 0.02, 0.014],
        [0, side * 14, 35],
      ]),
    ],
  },
  // A round rim about each eye, wide enough to show the whole eye through it
  glasses: {
    lean: [0, 0, 0],
    pieces: [
      ...sides((side) => eyeRim(side, TOY_RED)),
      ["tube", TOY_RED, [0, 0.068, 0.234], [0.022, 0.05, 0.022], [0, 0, 90]],
      ...glassesArms(TOY_RED, [0.145, 0.201]),
    ],
  },
  // A rim on the penguin's left eye, and a chain of beads from it that hangs down the cheek and ends on the shoulder,
  // where a band round the neck covers its last beads
  monocle: {
    lean: [0, 0, 0],
    pieces: [
      eyeRim(1, TOY_GOLD),
      ...[
        [0.146, -0.01, 0.208],
        [0.162, -0.043, 0.194],
        [0.176, -0.073, 0.177],
        [0.187, -0.099, 0.158],
        [0.195, -0.121, 0.138],
        [0.2, -0.14, 0.118],
        [0.203, -0.158, 0.098],
        [0.204, -0.176, 0.078],
      ].map((spot) => ["ball", TOY_GOLD, spot, 0.028]),
    ],
  },
  // The patch covers the penguin's left eye. Its strap is a band round the head that tips up over the other eye, so
  // it crosses the forehead and comes back low behind the patch
  eyepatch: {
    lean: [0, 0, 0],
    pieces: [
      ["ball", TOY_BLACK, [0.08, 0.04, 0.228], [0.135, 0.125, 0.06]],
      ["tube", TOY_BROWN, [0.028, 0.053, 0], [0.45, 0.028, 0.45], [0, 0, -28]],
    ],
  },
  // Thick beside the beak, thinning as it sweeps back round each cheek to a curled tip
  moustache: {
    lean: [0, 0, 0],
    pieces: [
      ...sides((side) => [
        "ball",
        TOY_BROWN,
        [side * 0.075, -0.065, 0.235],
        [0.16, 0.09, 0.08],
        [0, side * 20, side * 8],
      ]),
      ...sides((side) => [
        "ball",
        TOY_BROWN,
        [side * 0.17, -0.048, 0.18],
        [0.15, 0.058, 0.06],
        [0, side * 46, side * 26],
      ]),
      ...sides((side) => ["ball", TOY_BROWN, [side * 0.208, -0.012, 0.143], 0.052]),
    ],
  },
  // The eyes show on the glass, as the mask hides the penguin's own
  snorkel: {
    lean: [0, 0, 0],
    pieces: [
      ["ball", TOY_YELLOW, [0, 0.03, 0.225], [0.4, 0.14, 0.09]],
      ["ball", TOY_SKY, [0, 0.03, 0.25], [0.34, 0.1, 0.07]],
      ...sides((side) => ["ball", TOY_BLACK, [side * 0.075, 0.035, 0.275], [0.05, 0.06, 0.03]]),
      ["tube", TOY_YELLOW, [0, 0.03, 0], [0.455, 0.03, 0.455]],
      ["tube", TOY_ORANGE, [-0.39, 0.1, 0.05], [0.07, 0.42, 0.07], [0, 0, 33]],
      ["tube", TOY_WHITE, [-0.482, 0.243, 0.05], [0.085, 0.07, 0.085], [0, 0, 33]],
      ["ball", TOY_ORANGE, [-0.275, -0.075, 0.05], 0.085],
      ["ball", TOY_ORANGE, [-0.2, -0.075, 0.14], 0.075],
      ["ball", TOY_ORANGE, [-0.12, -0.07, 0.21], 0.07],
    ],
  },
};

const degreesOf = (radians) => (radians * 180) / Math.PI;
const mix = (from, to, k) => from + (to - from) * k;

// The round shapes that make a penguin's skin about its neck and chest: its body, its head and its belly, each as its
// middle and how far it reaches from there
const SKIN_SHAPES = [PENGUIN_PIECES.dark[0], PENGUIN_PIECES.dark[1], PENGUIN_PIECES.white[0]].map(([, spot, size]) => ({
  spot,
  reach: (typeof size === "number" ? [size, size, size] : size).map((across) => across / 2),
}));

// How far out from the line down through the neck's middle a penguin's skin is, `down` below the neck and `turn`
// degrees round from the front toward the penguin's left
function skinReach(turn, down) {
  const [sin, cos] = [Math.sin((turn * Math.PI) / 180), Math.cos((turn * Math.PI) / 180)];
  let far = 0;
  for (const { spot, reach } of SKIN_SHAPES) {
    // A round shape cut level is an oval, this share of its full size
    const level = 1 - ((NECK_SPOT[1] - down - spot[1]) / reach[1]) ** 2;
    if (level <= 0) {
      continue;
    }
    const [wide, deep] = [reach[0] ** 2 * level, reach[2] ** 2 * level];
    const a = sin ** 2 / wide + cos ** 2 / deep;
    const b = (spot[2] * cos) / deep;
    const inside = b * b - a * (spot[2] ** 2 / deep - 1);
    if (inside >= 0) {
      far = Math.max(far, (b + Math.sqrt(inside)) / a);
    }
  }
  return far;
}

// A spot on that skin, measured from the neck's middle as every neck piece is, standing `lift` clear of it
function onSkin(turn, down, lift = 0) {
  const far = skinReach(turn, down) + lift;
  return [Math.sin((turn * Math.PI) / 180) * far, -down, Math.cos((turn * Math.PI) / 180) * far];
}

// A long shape laid from one spot to another: its length runs from `to` up to `from`, and its flat face is turned
// out from the neck's middle. `wide` and `thick` are its other two sizes
function laid(kind, color, from, to, wide, thick) {
  const middle = from.map((value, axis) => (value + to[axis]) / 2);
  const long = Math.hypot(...from.map((value, axis) => value - to[axis]));
  const along = from.map((value, axis) => (value - to[axis]) / long);
  // Straight out from the middle, with any lean along the shape taken off it
  const lean = middle[0] * along[0] + middle[2] * along[2];
  const flat = [middle[0] - lean * along[0], -lean * along[1], middle[2] - lean * along[2]];
  const out = flat.map((value) => value / Math.hypot(...flat));
  const across = [
    along[1] * out[2] - along[2] * out[1],
    along[2] * out[0] - along[0] * out[2],
    along[0] * out[1] - along[1] * out[0],
  ];
  const turn = [Math.atan2(along[2], out[2]), Math.asin(-across[2]), Math.atan2(across[1], across[0])];
  return [kind, color, middle, [wide, long, thick], turn.map(degreesOf)];
}

// Cloth lying on the skin from one spot to another, each [degrees round, how far down]: one block for each color in
// `colors`, end to end, so it bends with the body and can be striped
function draped(colors, from, to, wide, lift = 0.012) {
  const at = (k) => onSkin(mix(from[0], to[0], k), mix(from[1], to[1], k), lift);
  return colors.map((color, part) =>
    laid("block", color, at(part / colors.length), at((part + 1) / colors.length), wide, 0.03),
  );
}

// How many degrees round the chest one unit across it is, where a scarf's ends hang
const CHEST_TURN = 210;

// One hanging end of a scarf: the cloth, and three short threads of `fringe` past its tip, a third of its width apart
function scarfEnd(colors, fringe, from, to, wide = 0.085) {
  const apart = (wide / 3) * CHEST_TURN;
  const tip = (side, k) => onSkin(mix(from[0], to[0], k) + side * apart, mix(from[1], to[1], k), 0.012);
  return [
    ...draped(colors, from, to, wide),
    ...[-1, 0, 1].map((side) => laid("block", fringe, tip(side, 1), tip(side, 1.13), 0.018, 0.02)),
  ];
}

// The band of a scarf or a collar round the neck, `tall` up and down, tipped a little so it sits lower in front. It
// lies in the crease between the head and the body, where its inside is hidden in both
function neckBand(color, tall) {
  return ["ring", color, [0, -0.005, 0], [0.45, tall, 0.42], [5, 0, 0]];
}

const LEI_COLORS = [TOY_PINK, TOY_YELLOW, TOY_WHITE, TOY_PURPLE];

// Each neck piece the same way, from the middle of the neck, where the chest faces +z. The crease between the head
// and the body is level with that middle and 0.18 out from it, and the body widens fast under it, so everything below
// the band is placed on the skin with onSkin. The beak's underside is 0.05 up in front and a moustache's 0.03, so a
// band stays under those. A snorkel's mouthpiece comes down the penguin's right cheek, so a knot sits on its left
const NECK_LOOKS = {
  // A band wrapped once, a knot on the penguin's left, and two ends of different lengths with a stripe near each tip
  scarf: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_RED, 0.6),
      ["ball", TOY_RED, onSkin(27, 0.03, 0.03), [0.13, 0.11, 0.1], [0, 27, 0]],
      ...scarfEnd([TOY_RED, TOY_RED, TOY_RED, TOY_WHITE, TOY_RED], TOY_WHITE, [22, 0.05], [9, 0.34]),
      ...scarfEnd([TOY_RED, TOY_RED, TOY_WHITE, TOY_RED], TOY_WHITE, [31, 0.05], [35, 0.23]),
    ],
  },
  // Each wing is a cone lying on its side with its point under the knot
  bowtie: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_PURPLE, 0.3),
      ...sides((side) => laid("cone", TOY_PURPLE, onSkin(0, 0.03, 0.035), onSkin(side * 40, 0.03, 0.035), 0.16, 0.07)),
      ["ball", TOY_GOLD, onSkin(0, 0.03, 0.045), [0.065, 0.075, 0.06]],
    ],
  },
  // A folded cloth: its point hangs down the chest, and its two corners are tied behind the neck
  bandana: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_TEAL, 0.45),
      laid("cone", TOY_TEAL, onSkin(0, 0.25, 0.006), onSkin(0, -0.01, 0.02), 0.32, 0.045),
      ...sides((side) => ["ball", TOY_WHITE, onSkin(side * 13, 0.07, 0.03), [0.04, 0.04, 0.025]]),
      ["ball", TOY_WHITE, onSkin(0, 0.14, 0.026), [0.04, 0.04, 0.025]],
      ["ball", TOY_TEAL, onSkin(180, 0, 0.05), [0.1, 0.08, 0.08]],
      ...sides((side) => laid("cone", TOY_TEAL, onSkin(180 + side * 16, 0.12, 0.012), onSkin(180, 0, 0.04), 0.07, 0.03)),
    ],
  },
  // A white collar, a knot, and a blade that widens down the belly to a point
  necktie: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_WHITE, 0.4),
      ["ball", TOY_BLUE, onSkin(0, 0.04, 0.03), [0.08, 0.07, 0.05]],
      laid("taper", TOY_BLUE, onSkin(0, 0.05, 0.02), onSkin(0, 0.27, 0.02), 0.13, 0.035),
      laid("cone", TOY_BLUE, onSkin(0, 0.34, 0.02), onSkin(0, 0.27, 0.02), 0.13, 0.035),
      ...[0.13, 0.21].map((down) =>
        laid("block", TOY_YELLOW, onSkin(-7, down, 0.027), onSkin(7, down + 0.035, 0.027), 0.022, 0.03),
      ),
    ],
  },
  // Beads resting on the shoulders, lower in front, with one pink stone in the middle
  pearls: {
    lean: [0, 0, 0],
    pieces: [
      ...around(20, (angle) => [
        "ball",
        TOY_WHITE,
        onSkin(degreesOf(angle), 0.045 + 0.04 * Math.cos(angle), 0.012),
        0.055,
      ]),
      ["ball", TOY_PINK, onSkin(0, 0.125, 0.02), [0.075, 0.085, 0.06]],
    ],
  },
  // Knitted in two colors all the way: a band of sixteen flat lengths, a knot in front and an end down each side of
  // the chest
  stripes: {
    lean: [0, 0, 0],
    pieces: [
      ...around(16, (angle, index) => [
        "block",
        index % 2 ? TOY_WHITE : TOY_LEAF,
        onSkin(degreesOf(angle), 0.022 + 0.012 * Math.cos(angle), 0.012),
        [0.102, 0.095, 0.09],
        [0, degreesOf(angle), 0],
      ]),
      ["ball", TOY_LEAF, onSkin(0, 0.04, 0.035), [0.12, 0.1, 0.09]],
      ...scarfEnd(
        [TOY_WHITE, TOY_LEAF, TOY_WHITE, TOY_LEAF, TOY_WHITE, TOY_LEAF],
        TOY_WHITE,
        [-5, 0.06],
        [-22, 0.4],
      ),
      ...scarfEnd([TOY_WHITE, TOY_LEAF, TOY_WHITE, TOY_LEAF], TOY_WHITE, [5, 0.06], [20, 0.28]),
    ],
  },
  // A ribbon from each side of the neck down to a gold disc in the middle of the chest
  medal: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_RED, 0.25),
      ...sides((side) => draped([TOY_RED, TOY_RED, TOY_RED], [side * 34, 0.01], [0, 0.2], 0.055, 0.008)).flat(),
      ["tube", TOY_GOLD, onSkin(0, 0.235, 0.014), [0.15, 0.035, 0.15], [77, 0, 0]],
      ["ball", TOY_YELLOW, onSkin(0, 0.235, 0.03), [0.08, 0.08, 0.03], [-13, 0, 0]],
    ],
  },
  // Twelve flowers resting on the shoulders, lower in front. Each is a flat round bloom that faces out and a little
  // up, with its middle showing
  lei: {
    lean: [0, 0, 0],
    pieces: around(12, (angle, index) => {
      const [turn, down] = [degreesOf(angle), 0.06 + 0.05 * Math.cos(angle)];
      const petals = LEI_COLORS[index % LEI_COLORS.length];
      return [
        ["ball", petals, onSkin(turn, down, 0.02), [0.15, 0.14, 0.07], [-35, turn, 0]],
        ["ball", petals === TOY_YELLOW ? TOY_ORANGE : TOY_YELLOW, onSkin(turn, down - 0.02, 0.048), 0.05],
      ];
    }).flat(),
  },
  // A thin collar with a round bell under the chin, which has a slot along its underside
  bell: {
    lean: [0, 0, 0],
    pieces: [
      neckBand(TOY_PINK, 0.4),
      ["ball", TOY_GOLD, onSkin(0, 0.015, 0.045), 0.05],
      ["ball", TOY_GOLD, onSkin(0, 0.07, 0.04), [0.12, 0.12, 0.11]],
      ["ball", TOY_BROWN, onSkin(0, 0.118, 0.045), [0.075, 0.03, 0.07]],
    ],
  },
};

// A cape hangs from high on the back, this far up it and this far behind it, and comes this far down. It tips
// back a little, so its hem swings clear of the body
const CAPE_TOP = [0.16, -0.04];
const CAPE_LONG = 0.6;
const CAPE_TIPS_BACK = 8;
// Its folds of cloth, side by side from one edge to the other, as [how far along the shoulders it hangs from, how
// many degrees it fans out sideways]
const CAPE_FOLDS = [-2, -1, 0, 1, 2].map((fold) => [fold * 0.05, fold * 12]);

// A spot on the cape, `across` from its middle and `down` from its top
function capeSpot(across, down) {
  const tip = (CAPE_TIPS_BACK * Math.PI) / 180;
  return [across, CAPE_TOP[0] - down * Math.cos(tip), CAPE_TOP[1] - down * Math.sin(tip)];
}

// One fold, a long round ridge from the top to the hem
function capeFold([across, fan]) {
  const [sideways, down] = [Math.sin((fan * Math.PI) / 180), Math.cos((fan * Math.PI) / 180)];
  const long = CAPE_LONG / down;
  return [
    "ball",
    TOY_RED,
    capeSpot(across + (sideways * long) / 2, CAPE_LONG / 2),
    [0.24, long, 0.11],
    [CAPE_TIPS_BACK, 0, fan],
  ];
}

// A wing's long feathers, from the top one down, as [degrees up from straight out to the side, how long, color]. They
// fan out from the shoulder
const WING_FEATHERS = [
  [42, 0.44, TOY_WHITE],
  [24, 0.52, TOY_WHITE],
  [6, 0.5, TOY_WHITE],
  [-14, 0.42, TOY_GOLD],
  [-34, 0.32, TOY_GOLD],
];
// Where a wing grows from, as [how far from the middle of the back, how far up, how far behind]
const WING_ROOT = [0.1, 0.14, -0.09];

function wingFeather(side, [rise, long, color], index) {
  const [out, up] = [Math.cos((rise * Math.PI) / 180), Math.sin((rise * Math.PI) / 180)];
  const reach = long / 2 + 0.02;
  return [
    "ball",
    color,
    // Each feather lies a little behind the one above it, so no two share a face
    [side * (WING_ROOT[0] + out * reach), WING_ROOT[1] + up * reach, WING_ROOT[2] - index * 0.008],
    [long, 0.15, 0.05],
    [0, 0, side * rise],
  ];
}

// Each back item the same way, from the middle of the back, which faces -z. The back curves away to the sides and up,
// so pieces start a little inside it. The back of the head is 0.43 up and the lowest brim 0.5 up, so nothing rises
// past 0.42 but the balloon and the tips of the wings, which are out wide of every brim. The game's camera looks down
// from the front, so what shows of an item on a standing penguin is what sticks out past its sides and shoulders or
// stands out behind its head. On a slide the back faces up and all of it shows
const BACK_LOOKS = {
  backpack: {
    lean: [0, 0, 0],
    pieces: [
      ["block", TOY_BLUE, [0, -0.04, -0.1], [0.42, 0.44, 0.26]],
      ["ball", TOY_BLUE, [0, 0.16, -0.1], [0.42, 0.14, 0.26]],
      ["block", TOY_SKY, [0, -0.13, -0.24], [0.28, 0.18, 0.06]],
      ["ball", TOY_YELLOW, [0, -0.07, -0.27], 0.06],
      ["tube", TOY_YELLOW, [0, 0.25, -0.12], [0.15, 0.62, 0.15], [0, 0, 90]],
      ...sides((side) => ["tube", TOY_RED, [side * 0.315, 0.25, -0.12], [0.165, 0.03, 0.165], [0, 0, 90]]),
      ...sides((side) => ["ring", TOY_BROWN, [side * 0.14, 0.06, 0.27], [0.49, 0.5, 0.6], [0, 0, 90]]),
    ],
  },
  // Cloth over the shoulders, a sheet down the back that widens to a gold hem, and folds standing a little proud of it
  cape: {
    lean: [0, 0, 0],
    pieces: [
      ["ball", TOY_RED, [0, 0.12, 0.02], [0.64, 0.2, 0.2]],
      ["taper", TOY_RED, capeSpot(0, CAPE_LONG / 2), [0.86, CAPE_LONG, 0.07], [CAPE_TIPS_BACK, 0, 0]],
      ...CAPE_FOLDS.map(capeFold),
      ["ball", TOY_GOLD, capeSpot(0, CAPE_LONG), [0.88, 0.05, 0.1], [CAPE_TIPS_BACK, 0, 0]],
    ],
  },
  jetpack: {
    lean: [0, 0, 0],
    pieces: [
      ["block", TOY_BLACK, [0, 0.03, -0.06], [0.46, 0.22, 0.1]],
      ...sides((side) => ["tube", TOY_STEEL, [side * 0.21, 0.03, -0.15], [0.2, 0.4, 0.2]]),
      ...sides((side) => ["cone", TOY_RED, [side * 0.21, 0.31, -0.15], [0.2, 0.16, 0.2]]),
      ...sides((side) => ["tube", TOY_RED, [side * 0.21, 0.05, -0.15], [0.215, 0.06, 0.215]]),
      ...sides((side) => ["cone", TOY_BLACK, [side * 0.21, -0.2, -0.15], [0.18, 0.1, 0.18]]),
      ...sides((side) => ["cone", TOY_ORANGE, [side * 0.21, -0.33, -0.15], [0.15, 0.2, 0.15], [180, 0, 0]]),
    ],
  },
  // Each wing is a fan of long feathers, white above and gold below, with a round white shoulder over where they meet
  wings: {
    lean: [0, 0, 0],
    pieces: sides((side) => [
      ...WING_FEATHERS.map((feather, index) => wingFeather(side, feather, index)),
      ["ball", TOY_WHITE, [side * 0.17, 0.17, -0.075], [0.26, 0.2, 0.07], [0, 0, side * 20]],
    ]).flat(),
  },
  // It floats beside the head, low enough to stay under the penguin's name and behind a lifted flipper
  balloon: {
    lean: [0, 0, 0],
    pieces: [
      ["ball", TOY_RED, [0.5, 0.27, -0.05], [0.32, 0.38, 0.32]],
      ["cone", TOY_RED, [0.5, 0.065, -0.05], [0.07, 0.05, 0.07]],
      ["tube", TOY_WHITE, [0.29, 0.02, -0.035], [0.016, 0.43, 0.016], [-4, 0, -79]],
    ],
  },
  // It stands straight out of the back with its front edge under the neck and its tip swept toward the tail, so on a
  // slide it stands up and sweeps back, as a shark's does out of the water. Its base is sunk a little into the body.
  // It is short and sits between the shoulders, with its tip above the waist: any longer or lower and a standing
  // penguin seems to have a tail
  fin: {
    lean: [0, 0, 0],
    pieces: [["fin", TOY_SHARK, [0, 0.02, -0.12], [0.15, 0.38, 0.3], [-90, 0, 0]]],
  },
};

// Everything worn by the id the bot knows it by, which no two things share, with the name its shape goes by
const WORN = new Map();
const WORN_LOOKS = { hat: HAT_LOOKS, face: FACE_LOOKS, neck: NECK_LOOKS, back: BACK_LOOKS };
for (const [kind, looks] of Object.entries(WORN_LOOKS)) {
  for (const [id, look] of Object.entries(looks)) {
    WORN.set(id, { ...look, name: `${kind}-${id}` });
  }
}

// Baked meshes by id, made when their first wearer needs them
const wornMeshes = new Map();
let wornMaterials = null;

// A white material that shows the colors baked into a mesh
function colorMaterial(options) {
  const material = paint("#ffffff", options);
  material.diffuseVertexColor = true;
  material.update();
  return material;
}

// The three materials everything worn shares, so a new thing to wear never needs a new one
function wornMaterial({ glass, glow }) {
  if (!wornMaterials) {
    const lit = colorMaterial({ gloss: 0.5, emissive: "#b8b8b8" });
    lit.emissiveVertexColor = true;
    lit.update();
    wornMaterials = {
      plain: colorMaterial({ gloss: 0.3 }),
      glass: colorMaterial({ gloss: 0.85, opacity: 0.86 }),
      glow: lit,
    };
  }
  return wornMaterials[glass ? "glass" : glow ? "glow" : "plain"];
}

// Adds one piece to the lists a mesh is made from. Colors go in as the engine's linear light, as materials do. A color
// with eight digits ends in how solid it is, which only a see-through material shows
function bakePiece(lists, [kind, hex, spot, size, turn], lean) {
  const geometry = TOY_SHAPES[kind]();
  addShape(lists, geometry, new pc.Mat4().mul2(lean, placement(spot, size, turn)));
  const color = new pc.Color().fromString(hex).linear();
  for (let i = 0; i < geometry.positions.length; i += 3) {
    lists.colors.push(color.r, color.g, color.b, color.a);
  }
}

// Pieces become one mesh, so they are one draw however many there are. `lean` turns the whole thing
function bakedMesh(device, pieces, lean) {
  const lists = { positions: [], normals: [], colors: [], indices: [] };
  const whole = placement([0, 0, 0], 1, lean);
  pieces.forEach((piece) => bakePiece(lists, piece, whole));
  return finishMesh(device, lists);
}

function wornMesh(id) {
  if (!wornMeshes.has(id)) {
    const { lean, pieces } = WORN.get(id);
    wornMeshes.set(id, bakedMesh(sharedKit.device, pieces, lean));
  }
  return wornMeshes.get(id);
}

// A spot on a body that one thing at a time hangs from. It is a part of the posed body, so what it wears moves along
function wornSpot(parent, name, spot, turn) {
  const entity = new pc.Entity(name);
  entity.setLocalPosition(...spot);
  if (turn) {
    entity.setLocalEulerAngles(...turn);
  }
  parent.addChild(entity);
  return entity;
}

// Swaps what a spot wears: a penguin's `head` (a hat), `face`, `neck` or `back`, or a seal's `head`. `id` is the thing, or
// null for a bare spot. An id this page has no shape for shows nothing
export function putOn(spot, id) {
  for (const worn of [...spot.children]) {
    worn.destroy();
  }
  const look = WORN.get(id);
  if (look) {
    meshShape(spot, wornMesh(id), wornMaterial(look), false).name = look.name;
  }
}

// How far above the middle of the head a hat reaches, or 0 with no hat
export function hatTop(id) {
  return Object.hasOwn(HAT_LOOKS, id ?? "") ? wornMesh(id).aabb.getMax().y : 0;
}

// ---------- Crates and what comes out of them ----------

const CRATE_LID = "#b3202c";
const MARK_SHADE = "#0a2c40";
const MARK_RING = "#ff2d6f";
// How high on a penguin the middle of its shield bubble sits, in the penguin's own sizes
const BUBBLE_HEIGHT = 0.56;

// A gift crate standing on the ice, about 0.7 across: red with a yellow ribbon and bow, which nothing else on the ice
// is. One mesh, colors and all
const CRATE_PIECES = [
  ["block", TOY_RED, [0, 0.26, 0], [0.62, 0.52, 0.62]],
  ["block", CRATE_LID, [0, 0.56, 0], [0.7, 0.12, 0.7]],
  ["block", TOY_YELLOW, [0, 0.315, 0], [0.17, 0.63, 0.72]],
  ["block", TOY_YELLOW, [0, 0.315, 0], [0.72, 0.63, 0.17]],
  ...sides((side) => ["ball", TOY_YELLOW, [side * 0.14, 0.7, 0], [0.28, 0.17, 0.17], [0, 0, side * 24]]),
  ["ball", TOY_GOLD, [0, 0.67, 0], 0.13],
];

// The mark a crate falls toward and then stands on, flat on the ice: a soft shadow with a bright ring round it. Rings
// from the middle out, each [how far out, color, how solid from 00 to ff]
const MARK_RINGS = [
  [0, MARK_SHADE, "70"],
  [0.3, MARK_SHADE, "5c"],
  [0.47, MARK_SHADE, "00"],
  [0.5, MARK_RING, "00"],
  [0.53, MARK_RING, "f2"],
  [0.62, MARK_RING, "f2"],
  [0.66, MARK_RING, "00"],
];

// A shield's bubble, one across: a see-through ball, a bright rim turned to face the game's camera, which never
// moves round the ice, and a glint on the side the camera sees. See-through shapes draw in the order listed
const BUBBLE_PIECES = [
  ["ball", "#9a66ff38", [0, 0, 0], 1],
  ["hoop", "#a36bfff2", [0, 0, 0], 1, [90 - CAMERA_PITCH, 0, 0]],
  ["ball", "#ffffffe6", [-0.19, 0.37, 0.05], [0.17, 0.11, 0.11], [0, 0, 32]],
];

// The ice a frost shuts a penguin in, in the penguin's own sizes from its feet up: a blue skin over all of it, a ring
// of crystals leaning out round its feet, tall and short by turns, and a cap of frost on its head
const ICE_PIECES = [
  ["ball", "#3aa8ff80", [0, 0.52, 0.01], [0.82, 1.16, 0.76]],
  ...around(7, (angle, index) => {
    const tall = index % 2 ? 0.4 : 0.62;
    return [
      "cone",
      index % 2 ? "#eaf8ffeb" : "#7fd0ffeb",
      [Math.sin(angle) * 0.4, tall / 2 - 0.02, Math.cos(angle) * 0.4],
      [0.24, tall, 0.24],
      [Math.cos(angle) * 26, 0, -Math.sin(angle) * 26],
    ];
  }),
  ["ball", "#f4fbffe6", [0, 1.08, 0], [0.42, 0.16, 0.42]],
];

// Shows the colors baked into a mesh, each as see-through as its color says. Lit, glossy and a little bright of its
// own, for the bubble and the ice. Each shape wearing it sets how much of it shows with setShown
function glassMaterial() {
  const material = colorMaterial({ gloss: 0.85, opacity: 1, emissive: "#707070" });
  material.emissiveVertexColor = true;
  material.opacityVertexColor = true;
  material.opacityVertexColorChannel = "a";
  material.update();
  return material;
}

// The same for the mark, which glows in its own colors whatever the light
function markMaterial() {
  const material = paint("#000000", { emissive: "#ffffff", opacity: 1 });
  material.emissiveVertexColor = true;
  material.opacityVertexColor = true;
  material.opacityVertexColorChannel = "a";
  material.update();
  return material;
}

// A flat round mesh lying on the ground, shaded from one ring of points to the next
function flatRings(device, rings, points = 32) {
  const lists = { positions: [], normals: [], colors: [], indices: [] };
  rings.forEach(([far, hex, solid], ring) => {
    const color = new pc.Color().fromString(hex + solid).linear();
    for (let i = 0; i < points; i += 1) {
      const angle = (i / points) * TAU;
      lists.positions.push(Math.sin(angle) * far, 0, Math.cos(angle) * far);
      lists.normals.push(0, 1, 0);
      lists.colors.push(color.r, color.g, color.b, color.a);
      if (ring > 0) {
        const here = (ring - 1) * points + i;
        const next = (ring - 1) * points + ((i + 1) % points);
        lists.indices.push(here, here + points, next, next, here + points, next + points);
      }
    }
  });
  return finishMesh(device, lists);
}

// A crate and the mark under it, each one draw. The mark is its shadow, so the crate casts none. scene.js moves them
export function buildCrate(app) {
  const kit = shared(app);
  const root = new pc.Entity("crate");
  app.root.addChild(root);
  const box = meshShape(root, kit.crate, wornMaterial({}), false);
  const mark = meshShape(app.root, kit.mark, kit.markGlow, false);
  mark.name = "crate-mark";
  root.enabled = false;
  mark.enabled = false;
  return { root, box, mark };
}

// One of each shape a crate brings. Shown out of sight for a frame, it has the graphics card build what draws them
// before a round needs it
export function buildWarmUp(app) {
  const kit = shared(app);
  const root = new pc.Entity("warm-up");
  app.root.addChild(root);
  meshShape(root, kit.crate, wornMaterial({}), false);
  meshShape(root, kit.mark, kit.markGlow, false);
  meshShape(root, kit.bubble, kit.glass, false);
  return root;
}

// How much of a bubble, a block of ice or a mark shows, from 0 to 1
export function setShown(entity, amount) {
  entity.render.meshInstances[0].setParameter("material_opacity", amount);
}

// ---------- Maps: thin ice, the wind, the walrus and snowballs ----------

// Thin ice has no snow on it: a flat cap cut in two blues by turns, with a pale middle
const THIN_BLUES = ["#3fb2e6", "#8ddcfa"];
const THIN_MIDDLE = "#e4f8ff";
const WIND_BLUE = "#2f9bff";
const WALRUS_BROWN = "#9a6646";
const WALRUS_SHADE = "#774a30";
const WALRUS_MUZZLE = "#e6c4a0";
const WALRUS_TUSK = "#fff8e6";
// How far behind its middle a walrus's haunches are, which it rears up on, and how much bigger than its shapes' sizes
// it is drawn: as big as fits a penguin standing against the bot's round body for it
const WALRUS_HAUNCH = 0.45;
const WALRUS_SCALE = 1.2;

// A thin tile's cap, flat at `y` on a tile `radius` across to its corners. Its corners point the way a tile's do
export function thinCap(app, radius, y) {
  const lists = { positions: [], normals: [], colors: [], indices: [] };
  const middle = new pc.Color().fromString(THIN_MIDDLE).linear();
  for (let side = 0; side < 6; side += 1) {
    const edge = new pc.Color().fromString(THIN_BLUES[side % 2]).linear();
    const start = lists.positions.length / 3;
    lists.positions.push(0, y, 0);
    lists.colors.push(middle.r, middle.g, middle.b, 1);
    for (const corner of [side, side + 1]) {
      const angle = (corner / 6) * TAU;
      lists.positions.push(Math.sin(angle) * radius, y, Math.cos(angle) * radius);
      lists.colors.push(edge.r, edge.g, edge.b, 1);
    }
    lists.normals.push(0, 1, 0, 0, 1, 0, 0, 1, 0);
    lists.indices.push(start, start + 1, start + 2);
  }
  return { mesh: finishMesh(app.graphicsDevice, lists), material: colorMaterial({ gloss: 0.9 }) };
}

// The wind's arrow, lying flat and pointing along +z, one long: faint at its tail and solid at its head, over a dark
// edge that keeps it clear on white ice. Each point is [across, along, color, how solid from 00 to ff], and the edge's
// points come first, so it is drawn under the arrow
const WIND_ARROW = [
  [-0.14, -0.5, MARK_SHADE, "10"],
  [0.14, -0.5, MARK_SHADE, "10"],
  [-0.14, 0.08, MARK_SHADE, "b0"],
  [0.14, 0.08, MARK_SHADE, "b0"],
  [-0.36, 0.08, MARK_SHADE, "b0"],
  [0.36, 0.08, MARK_SHADE, "b0"],
  [0, 0.57, MARK_SHADE, "b0"],
  [-0.1, -0.5, WIND_BLUE, "18"],
  [0.1, -0.5, WIND_BLUE, "18"],
  [-0.1, 0.12, WIND_BLUE, "f2"],
  [0.1, 0.12, WIND_BLUE, "f2"],
  [-0.28, 0.12, WIND_BLUE, "f2"],
  [0.28, 0.12, WIND_BLUE, "f2"],
  [0, 0.5, WIND_BLUE, "ff"],
];
const WIND_ARROW_FACES = [0, 2, 1, 1, 2, 3, 4, 6, 5, 7, 9, 8, 8, 9, 10, 11, 13, 12];

let groundGlow = null;

// The mark's material seen from both sides, so the order of a flat shape's points never matters. One for every flat
// shape that lies on the ice
function groundMaterial() {
  if (!groundGlow) {
    groundGlow = markMaterial();
    groundGlow.cull = pc.CULLFACE_NONE;
    groundGlow.update();
  }
  return groundGlow;
}

// The wind: its arrow, and `streaks` thin bright lines in the air, drawn in one go. hazards.js moves them
export function buildWind(app, streaks) {
  const lists = { positions: [], normals: [], colors: [], indices: [...WIND_ARROW_FACES] };
  for (const [across, along, hex, solid] of WIND_ARROW) {
    const color = new pc.Color().fromString(hex + solid).linear();
    lists.positions.push(across, 0, along);
    lists.normals.push(0, 1, 0);
    lists.colors.push(color.r, color.g, color.b, color.a);
  }
  const arrow = meshShape(app.root, finishMesh(app.graphicsDevice, lists), groundMaterial(), false);
  arrow.name = "wind-arrow";
  arrow.enabled = false;
  const line = pc.Mesh.fromGeometry(app.graphicsDevice, new pc.BoxGeometry());
  const lines = new Copies(app, line, paint("#000000", { emissive: "#ffffff", opacity: 1 }), streaks, false);
  lines.root.name = "wind-streaks";
  lines.root.enabled = false;
  return { arrow, lines };
}

// A walrus sitting on the ice and facing +z, about one across. One mesh, colors and all
const WALRUS_PIECES = [
  ["ball", WALRUS_BROWN, [0, 0.4, -0.08], [1.02, 0.8, 1.12]],
  ["ball", WALRUS_BROWN, [0, 0.74, 0.3], [0.64, 0.6, 0.6]],
  ...sides((side) => ["ball", WALRUS_MUZZLE, [side * 0.12, 0.64, 0.56], [0.28, 0.24, 0.2]]),
  ["ball", TOY_BLACK, [0, 0.75, 0.62], [0.11, 0.08, 0.08]],
  ...sides((side) => ["cone", WALRUS_TUSK, [side * 0.1, 0.4, 0.6], [0.08, 0.36, 0.08], [180, 0, 0]]),
  ...sides((side) => ["ball", TOY_BLACK, [side * 0.17, 0.88, 0.52], 0.075]),
  ...sides((side) => ["ball", WALRUS_SHADE, [side * 0.46, 0.07, 0.3], [0.44, 0.12, 0.34], [0, side * -25, 0]]),
  ["ball", WALRUS_SHADE, [0, 0.06, -0.62], [0.56, 0.1, 0.3]],
];

// The ring that shows how far a walrus's slam reaches, one across to its edge, flat on the ice
const ZONE_RINGS = [
  [0, MARK_RING, "00"],
  [0.6, MARK_RING, "12"],
  [0.92, MARK_RING, "5c"],
  [0.93, MARK_RING, "f2"],
  [1, MARK_RING, "f2"],
  [1.03, MARK_RING, "00"],
];

// The walrus and the ring its slam fills. `pivot` rears it up on its haunches and `body` takes a squash
export function buildWalrus(app) {
  const kit = shared(app);
  const root = new pc.Entity("walrus");
  root.setLocalScale(WALRUS_SCALE, WALRUS_SCALE, WALRUS_SCALE);
  app.root.addChild(root);
  const pivot = new pc.Entity();
  pivot.setLocalPosition(0, 0, -WALRUS_HAUNCH);
  root.addChild(pivot);
  const body = meshShape(pivot, bakedMesh(kit.device, WALRUS_PIECES), wornMaterial({}));
  body.setLocalPosition(0, 0, WALRUS_HAUNCH);
  const zone = meshShape(app.root, flatRings(kit.device, ZONE_RINGS, 48), groundMaterial(), false);
  zone.name = "walrus-zone";
  root.enabled = false;
  zone.enabled = false;
  return { root, pivot, body, zone };
}

// The mark a snowball flies toward, one across at the edge of its ring: a soft shadow with a blue ring round it
const SNOW_MARK_RINGS = [
  [0, MARK_SHADE, "60"],
  [0.5, MARK_SHADE, "40"],
  [0.86, MARK_SHADE, "00"],
  [0.88, WIND_BLUE, "00"],
  [0.92, WIND_BLUE, "f2"],
  [1, WIND_BLUE, "f2"],
  [1.04, WIND_BLUE, "00"],
];

// Up to `slots` snowballs in the air, the dark rims that keep them clear against white ice, and the marks they fly
// toward, each kind drawn in one go. A rim is the ball's own shape a little bigger, showing only its far side
export function buildSnowballs(app, slots) {
  const kit = shared(app);
  const ball = pc.Mesh.fromGeometry(kit.device, new pc.SphereGeometry({ latitudeBands: 8, longitudeBands: 12 }));
  const dark = paint("#000000", { emissive: MARK_SHADE });
  dark.cull = pc.CULLFACE_FRONT;
  dark.update();
  const made = {
    balls: new Copies(app, ball, paint("#ffffff", { gloss: 0.2, emissive: "#a9bcc9" }), slots, false),
    rims: new Copies(app, ball, dark, slots, false),
    marks: new Copies(app, flatRings(kit.device, SNOW_MARK_RINGS), groundMaterial(), slots, false),
  };
  for (const [name, copies] of Object.entries(made)) {
    copies.root.name = `snowball-${name}`;
    copies.root.enabled = false;
  }
  return made;
}

// ---------- Flat particles ----------

// One arm of a snowflake's outline, as [how far round from the arm's middle, how far out], going round one way
const FLAKE_ARM = [
  [-30, 0.14],
  [-11, 0.2],
  [-10, 0.44],
  [-5, 0.36],
  [-4, 0.62],
  [4, 0.62],
  [5, 0.36],
  [10, 0.44],
  [11, 0.2],
].map(([degrees, far]) => [(degrees * Math.PI) / 180, far]);

// Outlines about one across, going counter-clockwise so their fronts face the camera, and the color of their middle
// and their edge
const FLATS = {
  heart: {
    middle: "#ffb3d4",
    edge: "#ff2f7e",
    outline: around(24, (t) => [
      (-16 * Math.sin(t) ** 3) / 32,
      (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 32 + 0.03,
    ]),
  },
  flame: {
    middle: "#ffe45c",
    edge: "#ff4a12",
    outline: around(20, (t) => [-0.42 * Math.sin(t) * Math.sqrt((1 - Math.cos(t)) / 2) ** 1.4, 0.55 * Math.cos(t)]),
  },
  sparkle: {
    middle: "#ffffff",
    edge: "#a24dff",
    outline: around(8, (t, index) => [-Math.sin(t) * (index % 2 ? 0.2 : 0.62), Math.cos(t) * (index % 2 ? 0.2 : 0.62)]),
  },
  bubble: {
    middle: "#effcff",
    edge: "#2aa5f5",
    outline: around(16, (t) => [-Math.sin(t) * 0.5, Math.cos(t) * 0.5]),
  },
  // The winner's stars, with five points
  star: {
    middle: "#fffbe0",
    edge: "#ffbf1a",
    outline: around(10, (t, index) => [-Math.sin(t) * (index % 2 ? 0.25 : 0.62), Math.cos(t) * (index % 2 ? 0.25 : 0.62)]),
  },
  // Six arms, each a thin spike with a barb on either side
  snowflake: {
    middle: "#cfe8ff",
    edge: "#2f8cf5",
    outline: around(6, (t) =>
      FLAKE_ARM.map(([turn, far]) => [-Math.sin(t + turn) * far, Math.cos(t + turn) * far]),
    ).flat(),
  },
  // Pointed at both ends and tipped to one side, as a leaf falls
  leaf: {
    middle: "#d6f76a",
    edge: "#2f9e3f",
    outline: around(16, (t) => {
      const [x, y] = [-0.36 * Math.sin(t) * Math.sqrt(Math.abs(Math.sin(t))), 0.62 * Math.cos(t)];
      return [x * 0.87 - y * 0.5, x * 0.5 + y * 0.87];
    }),
  },
  // A fish out of a crate's feast, nose to the right, with a forked tail
  fish: {
    middle: "#ffe2b8",
    edge: "#ff7a1a",
    outline: [
      [0.56, 0],
      [0.44, 0.15],
      [0.24, 0.25],
      [0.02, 0.26],
      [-0.18, 0.18],
      [-0.32, 0.07],
      [-0.6, 0.17],
      [-0.5, 0],
      [-0.6, -0.17],
      [-0.32, -0.07],
      [-0.18, -0.18],
      [0.02, -0.26],
      [0.24, -0.25],
      [0.44, -0.15],
    ],
  },
  // A bit of a burst crate: a square of its red with the ribbon's yellow in the middle, tipped over
  chip: {
    middle: "#ffd23f",
    edge: "#e8413c",
    outline: [
      [0.42, 0.26],
      [-0.26, 0.42],
      [-0.42, -0.26],
      [0.26, -0.42],
    ],
  },
  // A cut stone: a flat top, wide shoulders and a point underneath
  gem: {
    middle: "#b9fff2",
    edge: "#00b89e",
    outline: [
      [0.3, 0.42],
      [-0.3, 0.42],
      [-0.58, 0.14],
      [0, -0.58],
      [0.58, 0.14],
    ],
  },
};

let flatMaterial = null;

// One flat particle's mesh, a fan from its middle to its outline, with the two colors shaded between them. Unlit, and
// shared by every kind, so all of them draw the same way
export function flatParticle(app, kind) {
  const { outline, middle, edge } = FLATS[kind];
  const pitch = (CAMERA_PITCH * Math.PI) / 180;
  const [up, out] = [Math.cos(pitch), Math.sin(pitch)];
  const positions = [0, 0, 0];
  const normals = [0, out, up];
  const [inner, outer] = [middle, edge].map((hex) => new pc.Color().fromString(hex).linear());
  const colors = [inner.r, inner.g, inner.b, 1];
  const indices = [];
  outline.forEach(([x, y], index) => {
    positions.push(x, y * up, -y * out);
    normals.push(0, out, up);
    colors.push(outer.r, outer.g, outer.b, 1);
    indices.push(0, index + 1, ((index + 1) % outline.length) + 1);
  });
  const mesh = new pc.Mesh(app.graphicsDevice);
  mesh.setPositions(positions);
  mesh.setNormals(normals);
  mesh.setColors(colors);
  mesh.setIndices(indices);
  mesh.update();
  if (!flatMaterial) {
    flatMaterial = paint("#000000", { emissive: "#ffffff" });
    flatMaterial.emissiveVertexColor = true;
    flatMaterial.update();
  }
  return { mesh, material: flatMaterial };
}
