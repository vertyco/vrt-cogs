// What makes hits land: sparks, snow and spray, rings on the water, a held breath of the drawing, a camera shake and the
// sounds that go with them. Everything here is made once and reused, so a busy moment adds no work for the phone to
// clean up, and each kind of particle is drawn in one go however many are showing.
import { flatParticle, meshShape, paint, setShown, shape } from "./models.js";
import { FISH, HEAVY, WALRUS_REACH } from "./motion.js";

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const TAU = Math.PI * 2;
// Sixteen numbers per particle, one for each cell of the 4x4 sum that places it
const MATRIX = 16;
const RING_SECONDS = 0.8;
const RING_COUNT = 4;
const SEATS = 6;
// How many cheers and splashes can be throwing their bursts at once: a splash for every seat and the winner's cheer
const SHOWS = 8;
const TRAIL_EVERY = 0.045;
const SPARKLE_EVERY = 0.22;
// A slide must be at least this fast to leave a trail
const TRAIL_SPEED = 3;
// A hit's stars are this wide on the screen whatever the screen, start this far (in world units) from the touch, and
// are drawn over everything so a penguin can't hide them
const STAR_PIXELS = 8;
const STAR_SPREAD = 0.5;
const STAR_HEIGHT = 0.9;
// How far behind a penguin its slide's snow comes up, and how long after a fall's start its splash lands
const BEHIND = 0.45;
const PLUNGE_DELAY = 0.08;
// Out past the edge of the screen and under the sea, where the first frame's warm-up draws can't be seen
export const WARM_DEPTH = -5;
const WARM_FAR = 1000;
// The ring of frost that sweeps over the ice from whoever let a frost out of a crate: how long it runs, how wide it
// gets and how high over the ice it lies. People who asked for less motion get a small one
const WAVE_SECONDS = 0.6;
const WAVE_WIDTH = REDUCED ? 3 : 15;
const WAVE_HEIGHT = 0.13;
// The ring a walrus's slam sends over the ice: how long it runs and how wide it gets, which is as far as the slam
// shoves penguins
const THUMP_SECONDS = 0.35;
const THUMP_WIDTH = 2 * WALRUS_REACH;

const rand = (low, high) => low + Math.random() * (high - low);

// How a slide marks the ice: which particles, seconds between puffs, and the rest as Cloud.emit takes them
const SNOW_PUFF = {
  kind: "snow",
  every: TRAIL_EVERY,
  y: 0.14,
  speed: 0.4,
  up: 0.5,
  life: 0.45,
  size: 0.13,
  gravity: 0,
};
// A fish's heavy slide is something every player needs to see, so it stays gold whatever trail is worn
const GOLD_PUFF = { ...SNOW_PUFF, kind: "star" };
// The trails a penguin can wear, by the id the bot knows each by. One takes the place of its wearer's snow puffs
export const TRAILS = {
  sparkle: {
    kind: "sparkle",
    every: 0.05,
    y: 0.3,
    speed: 0.7,
    up: 1.3,
    life: 0.55,
    size: 0.42,
    gravity: 1.6,
    spread: 0.2,
  },
  hearts: {
    kind: "heart",
    every: 0.075,
    y: 0.3,
    speed: 0.35,
    up: 1.1,
    life: 0.7,
    size: 0.38,
    gravity: 0.3,
    spread: 0.2,
  },
  bubbles: {
    kind: "bubble",
    every: 0.06,
    y: 0.25,
    speed: 0.3,
    up: 0.9,
    life: 0.75,
    size: 0.32,
    gravity: -0.5,
    spread: 0.2,
  },
  flames: {
    kind: "flame",
    every: 0.04,
    y: 0.2,
    speed: 0.3,
    up: 1.5,
    life: 0.42,
    size: 0.42,
    gravity: -2,
    spread: 0.16,
    with: { kind: "flame", y: 0.25, speed: 0.8, up: 2, life: 0.3, size: 0.1, gravity: -1 },
  },
  snowflakes: {
    kind: "snowflake",
    every: 0.06,
    y: 0.3,
    speed: 0.5,
    up: 1,
    life: 0.8,
    size: 0.44,
    gravity: 1.4,
    spread: 0.25,
  },
  leaves: {
    kind: "leaf",
    every: 0.065,
    y: 0.3,
    speed: 0.7,
    up: 1.3,
    life: 0.75,
    size: 0.42,
    gravity: 2.4,
    spread: 0.2,
  },
  gems: {
    kind: "gem",
    every: 0.07,
    y: 0.3,
    speed: 0.5,
    up: 1.7,
    life: 0.6,
    size: 0.38,
    gravity: 4.5,
    spread: 0.18,
  },
};

// A cheer or a splash throws its particles in bursts. A burst is a puff like a trail's, with `n` particles, `at`
// seconds after the start and `dx` and `dz` to the side of it. A list of bursts is kept in the order of its `at`s

// What the winner does and what bursts around it, with no cheer worn. `move` names one of the scene's moves, and the
// stars fly out wide of the winner's name
const DEFAULT_CHEER = {
  move: "hops",
  bursts: [{ at: 0, kind: "cheer", n: 24, y: 0.7, speed: 3.4, up: 3.2, life: 1, size: 0.5, gravity: 5, spread: 0.3 }],
};

// One firework: a puff of `kind` opening out in the air and a few more falling under it, `at` seconds in, `dx` and
// `dz` from the winner and `y` up
function firework(at, kind, dx, dz, y) {
  const ring = { at, kind, n: 16, dx, dz, y, speed: 3, life: 1.1, size: 0.46, gravity: 1.8 };
  return [
    { ...ring, up: 1.4 },
    { ...ring, n: 8, up: -0.3, speed: 1.6 },
  ];
}

// The cheers a penguin can wear, by the id the bot knows each by. One takes the place of its wearer's hops and stars
export const CHEERS = {
  twirl: {
    move: "twirl",
    bursts: [
      { at: 0, kind: "sparkle", n: 10, y: 0.5, speed: 2.2, up: 2.4, life: 0.8, size: 0.42, gravity: 3, spread: 0.3 },
      { at: 0.5, kind: "sparkle", n: 10, y: 0.9, speed: 2.6, up: 2, life: 0.8, size: 0.42, gravity: 3, spread: 0.3 },
      { at: 1, kind: "sparkle", n: 10, y: 1.3, speed: 3, up: 1.6, life: 0.8, size: 0.42, gravity: 3, spread: 0.3 },
      { at: 1.5, kind: "cheer", n: 16, y: 0.7, speed: 3.4, up: 3.2, life: 1, size: 0.5, gravity: 5, spread: 0.3 },
    ],
  },
  backflip: {
    move: "backflip",
    bursts: [
      { at: 0.2, kind: "snow", n: 8, y: 0.14, speed: 1.8, up: 0.6, life: 0.35, size: 0.1, gravity: 0 },
      { at: 0.32, kind: "cheer", n: 20, y: 1, speed: 3.2, up: 2.4, life: 0.9, size: 0.5, gravity: 5, spread: 0.3 },
      { at: 1, kind: "snow", n: 10, y: 0.14, speed: 2.4, up: 0.8, life: 0.4, size: 0.12, gravity: 0 },
      { at: 1, kind: "cheer", n: 10, y: 0.5, speed: 3.6, up: 2.2, life: 0.8, size: 0.44, gravity: 5, spread: 0.3 },
    ],
  },
  fireworks: {
    move: "hops",
    hops: 6,
    bursts: [
      ...firework(0.05, "cheer", -1.1, -0.6, 2.4),
      ...firework(0.4, "sparkle", 1.2, -0.3, 2.9),
      ...firework(0.75, "heart", -0.3, -1, 3.3),
      ...firework(1.1, "gem", 1, 0.5, 2.3),
      ...firework(1.45, "cheer", -1.3, 0.3, 2.8),
      ...firework(1.8, "sparkle", 0.2, -0.8, 3.4),
    ],
  },
  spin: {
    move: "spin",
    bursts: [
      ...[0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5].map((at) => ({
        at,
        kind: "snowflake",
        n: 6,
        y: 0.2,
        speed: 3.4,
        up: 1.4,
        life: 0.5,
        size: 0.36,
        gravity: 4,
        spread: 0.5,
      })),
      { at: 1.95, kind: "cheer", n: 20, y: 0.7, speed: 3.4, up: 3.2, life: 1, size: 0.5, gravity: 5, spread: 0.3 },
    ],
  },
};

// A cheer by its id, or the default for none worn or one this page doesn't know
export function cheerLook(id) {
  return Object.hasOwn(CHEERS, id ?? "") ? CHEERS[id] : DEFAULT_CHEER;
}

// What plays where a knocked-in penguin goes under: plain water, with a ring on the sea under every splash
const DEFAULT_SPLASH = [{ at: 0, kind: "drop", n: 16, y: 0, speed: 2.4, up: 4.5, life: 0.8, size: 0.12, gravity: 12 }];
// A little of that water goes up with every other splash, so it still reads as going under
const SPRAY = { at: 0, kind: "drop", n: 7, y: 0, speed: 2.2, up: 3.6, life: 0.6, size: 0.1, gravity: 12 };

// The splashes a penguin can wear, by the id the bot knows each by. One plays for every penguin its wearer knocks in.
// A sizzle's snow is its steam
export const SPLASHES = {
  lovesplash: [
    SPRAY,
    { at: 0, kind: "heart", n: 14, y: 0.1, speed: 1.8, up: 3.6, life: 1.1, size: 0.56, gravity: 4, spread: 0.3 },
    { at: 0.15, kind: "heart", n: 6, y: 0.3, speed: 0.6, up: 1.5, life: 1.2, size: 0.4, gravity: -0.3, spread: 0.5 },
  ],
  bubblebath: [
    SPRAY,
    { at: 0, kind: "bubble", n: 20, y: 0.05, speed: 1.4, up: 2.4, life: 1.2, size: 0.46, gravity: 1, spread: 0.45 },
    { at: 0.2, kind: "bubble", n: 10, y: 0.1, speed: 0.6, up: 1.2, life: 1.3, size: 0.32, gravity: -0.6, spread: 0.6 },
  ],
  sizzle: [
    SPRAY,
    { at: 0, kind: "flame", n: 24, y: 0.05, speed: 1.6, up: 3, life: 0.6, size: 0.5, gravity: -1.5, spread: 0.35 },
    { at: 0.1, kind: "snow", n: 14, y: 0.3, speed: 0.7, up: 1.7, life: 1.1, size: 0.3, gravity: -0.6, spread: 0.4 },
  ],
  starburst: [
    SPRAY,
    { at: 0, kind: "cheer", n: 24, y: 0.1, speed: 3.4, up: 4.4, life: 1, size: 0.56, gravity: 6, spread: 0.3 },
    { at: 0, kind: "sparkle", n: 12, y: 0.3, speed: 2, up: 2.6, life: 0.8, size: 0.4, gravity: 2, spread: 0.3 },
  ],
};

// A crate coming open: bits of it, a few stars and a puff of snow off the ice
const CRATE_BURST = [
  { at: 0, kind: "chip", n: 14, y: 0.45, speed: 3, up: 4.4, life: 0.8, size: 0.36, gravity: 10, spread: 0.2 },
  { at: 0, kind: "cheer", n: 6, y: 0.5, speed: 2.4, up: 3.6, life: 0.8, size: 0.42, gravity: 7, spread: 0.2 },
  { at: 0, kind: "snow", n: 6, y: 0.14, speed: 1.8, up: 0.6, life: 0.35, size: 0.1, gravity: 0 },
];
// A crate thumping down onto the ice
const CRATE_THUMP = [{ at: 0, kind: "snow", n: 12, y: 0.14, speed: 2.4, up: 0.9, life: 0.4, size: 0.13, gravity: 0 }];
// What shows around a penguin for each thing a crate can hold, and as a shield bursts
const POWER_BURSTS = {
  shield: [
    { at: 0, kind: "sparkle", n: 10, y: 0.5, speed: 1.6, up: 2.6, life: 0.7, size: 0.4, gravity: 2, spread: 0.5 },
  ],
  frost: [
    { at: 0, kind: "snowflake", n: 14, y: 0.5, speed: 4.2, up: 1.2, life: 0.6, size: 0.42, gravity: 2, spread: 0.3 },
  ],
  feast: [
    { at: 0, kind: "fish", n: 9, y: 0.7, speed: 3.6, up: 4.8, life: 1.1, size: 0.7, gravity: 9, spread: 0.3 },
    { at: 0, kind: "star", n: 8, y: 0.7, speed: 2.4, up: 3, life: 0.5, size: 0.1, gravity: 5 },
    { at: 0.18, kind: "fish", n: 5, y: 0.9, speed: 2.6, up: 3.8, life: 1, size: 0.6, gravity: 9, spread: 0.3 },
  ],
};
const SHIELD_POP = [
  { at: 0, kind: "sparkle", n: 12, y: 0.75, speed: 3.6, up: 1.6, life: 0.5, size: 0.42, gravity: 3, spread: 0.6 },
  { at: 0, kind: "bubble", n: 8, y: 0.75, speed: 2.4, up: 2.2, life: 0.6, size: 0.26, gravity: 2, spread: 0.6 },
];
// Ice forming round a penguin, and falling off it again
const ICE_OVER = [
  { at: 0, kind: "snowflake", n: 4, y: 0.7, speed: 1.2, up: 1.4, life: 0.6, size: 0.3, gravity: 2, spread: 0.4 },
];
const THAW = [{ at: 0, kind: "drop", n: 7, y: 0.6, speed: 1.6, up: 1.8, life: 0.5, size: 0.1, gravity: 9, spread: 0.3 }];
// A walrus coming down on the ice: snow thrown out low all round it
const SLAM_BURST = [
  { at: 0, kind: "snow", n: 22, y: 0.16, speed: 4.6, up: 1.1, life: 0.45, size: 0.16, gravity: 3, spread: 0.5 },
  { at: 0, kind: "snowflake", n: 8, y: 0.4, speed: 3, up: 2.4, life: 0.6, size: 0.34, gravity: 5, spread: 0.5 },
];
// A snowball bursting where it lands
const SNOW_PUFF_BURST = [
  { at: 0, kind: "snow", n: 14, y: 0.2, speed: 2.2, up: 1.8, life: 0.45, size: 0.15, gravity: 5, spread: 0.1 },
  { at: 0, kind: "snowflake", n: 5, y: 0.3, speed: 1.6, up: 2.2, life: 0.55, size: 0.3, gravity: 5, spread: 0.1 },
];

// Every particle of one kind and look. They share one shape that the graphics card draws once per frame for all of them
class Cloud {
  constructor(app, material, size, layer = null, particle = null) {
    this.size = size;
    this.next = 0;
    this.x = new Float32Array(size);
    this.y = new Float32Array(size);
    this.z = new Float32Array(size);
    this.vx = new Float32Array(size);
    this.vy = new Float32Array(size);
    this.vz = new Float32Array(size);
    this.gravity = new Float32Array(size);
    this.big = new Float32Array(size);
    this.life = new Float32Array(size);
    this.max = new Float32Array(size);
    const device = app.graphicsDevice;
    const mesh =
      particle ?? pc.Mesh.fromGeometry(device, new pc.SphereGeometry({ latitudeBands: 6, longitudeBands: 12 }));
    this.buffer = new pc.VertexBuffer(device, pc.VertexFormat.getDefaultInstancingFormat(device), size, {
      usage: pc.BUFFER_DYNAMIC,
    });
    this.cells = new Float32Array(this.buffer.lock());
    this.cells.fill(0);
    const instance = new pc.MeshInstance(mesh, material);
    instance.setInstancing(this.buffer);
    instance.instancingCount = 0;
    // The particles are anywhere, whatever box the one shape has
    instance.cull = false;
    this.root = new pc.Entity();
    this.root.addComponent("render", { meshInstances: [instance], castShadows: false, receiveShadows: false });
    if (layer) {
      this.root.render.layers = [layer.id];
    }
    this.root.enabled = false;
    this.instance = instance;
    app.root.addChild(this.root);
  }

  // Shows one particle under the sea for a frame, so the graphics card builds what it draws with before it is needed
  warm() {
    this.cells[0] = 0.1;
    this.cells[5] = 0.1;
    this.cells[10] = 0.1;
    this.cells[12] = WARM_FAR;
    this.cells[13] = WARM_DEPTH;
    this.cells[15] = 1;
    this.buffer.unlock();
    this.instance.instancingCount = 1;
    this.root.enabled = true;
  }

  emit(x, y, z, n, speed, up, life, size, gravity, spread = 0) {
    for (let i = 0; i < n; i += 1) {
      const slot = this.next;
      this.next = (this.next + 1) % this.size;
      const angle = rand(0, TAU);
      const sp = speed * rand(0.4, 1);
      const away = spread * Math.sqrt(Math.random());
      const around = rand(0, TAU);
      this.x[slot] = x + Math.cos(around) * away;
      this.y[slot] = y;
      this.z[slot] = z + Math.sin(around) * away;
      this.vx[slot] = Math.cos(angle) * sp;
      this.vz[slot] = Math.sin(angle) * sp;
      this.vy[slot] = up * rand(0.5, 1.2);
      this.life[slot] = life * rand(0.7, 1.2);
      this.max[slot] = this.life[slot];
      this.gravity[slot] = gravity;
      this.big[slot] = size * rand(0.7, 1.3);
    }
  }

  // Moves the particles that are alive, packing them to the front of the picture buffer. Shrinks them as they die
  update(dt) {
    const { cells } = this;
    let live = 0;
    for (let i = 0; i < this.size; i += 1) {
      if (this.life[i] <= 0) {
        continue;
      }
      this.life[i] -= dt;
      if (this.life[i] <= 0) {
        continue;
      }
      this.vy[i] -= this.gravity[i] * dt;
      this.x[i] += this.vx[i] * dt;
      this.y[i] += this.vy[i] * dt;
      this.z[i] += this.vz[i] * dt;
      const scale = this.big[i] * (0.3 + 0.7 * (this.life[i] / this.max[i]));
      const at = live * MATRIX;
      cells[at] = scale;
      cells[at + 5] = scale;
      cells[at + 10] = scale;
      cells[at + 12] = this.x[i];
      cells[at + 13] = this.y[i];
      cells[at + 14] = this.z[i];
      cells[at + 15] = 1;
      live += 1;
    }
    if (live || this.instance.instancingCount) {
      this.buffer.unlock();
    }
    this.instance.instancingCount = live;
    this.root.enabled = live > 0;
  }
}

// A drawing layer after everything else, which the camera draws too
function buildOverLayer(app) {
  const layer = new pc.Layer({ name: "Hit stars" });
  app.scene.layers.push(layer);
  const { camera } = app.root.findByName("camera");
  camera.layers = camera.layers.concat(layer.id);
  return layer;
}

// A trail's particles of their own kind. Only drawn while some are alive, once for every penguin wearing it
function flatCloud(app, kind, size) {
  const { mesh, material } = flatParticle(app, kind);
  return new Cloud(app, material, size, null, mesh);
}

// A ring that spreads over the water where something splashed in
function buildRing(app) {
  const material = paint("#e6f8ff", { opacity: 0.8, emissive: "#6aa9c0" });
  const entity = shape(app.root, "torus", material, [0, -0.1, 0], 1, null, false);
  entity.enabled = false;
  return { entity, material, t: -1 };
}

// A thin ring lying on the ice, which a frost spreads from where it was let out
function buildWave(app) {
  const mesh = pc.Mesh.fromGeometry(
    app.graphicsDevice,
    new pc.TorusGeometry({ tubeRadius: 0.03, ringRadius: 0.5, segments: 48, sides: 6 }),
  );
  const entity = meshShape(app.root, mesh, paint("#000000", { opacity: 0.9, emissive: "#d2f4ff" }), false);
  entity.enabled = false;
  return { entity, t: -1 };
}

class Fx {
  constructor(app, sound, clock) {
    this.sound = sound;
    this.clock = clock;
    const over = buildOverLayer(app);
    const burst = paint("#000000", { emissive: "#ffd23f" });
    burst.depthTest = false;
    burst.update();
    // Pixels across one world unit of the ice, which the scene keeps up to date
    this.unit = 30;
    this.clouds = {
      burst: new Cloud(app, burst, 32, over),
      star: new Cloud(app, paint("#000000", { emissive: "#ffd23f" }), 64),
      drop: new Cloud(app, paint("#d9f4ff", { gloss: 0.8, emissive: "#3a6f86" }), 96),
      snow: new Cloud(app, paint("#ffffff", { emissive: "#8a99a3" }), 96),
      sparkle: flatCloud(app, "sparkle", 64),
      heart: flatCloud(app, "heart", 64),
      flame: flatCloud(app, "flame", 128),
      bubble: flatCloud(app, "bubble", 64),
      cheer: flatCloud(app, "star", 64),
      snowflake: flatCloud(app, "snowflake", 64),
      leaf: flatCloud(app, "leaf", 64),
      gem: flatCloud(app, "gem", 64),
      fish: flatCloud(app, "fish", 32),
      chip: flatCloud(app, "chip", 32),
    };
    this.cloudList = Object.values(this.clouds);
    this.rings = Array.from({ length: RING_COUNT }, () => buildRing(app));
    this.ringNext = 0;
    this.wave = buildWave(app);
    this.thump = buildWave(app);
    // How hard the camera shakes now, and the nudge it gives this frame
    this.shake = 0;
    this.kick = { x: 0, y: 0, z: 0 };
    this.trailLeft = new Float32Array(SEATS);
    // A fall's splash waits a moment after the penguin starts to go: seconds left (-1 for none) and where, per seat
    this.plungeLeft = new Float32Array(SEATS).fill(-1);
    this.plungeAt = Array.from({ length: SEATS }, () => ({ x: 0, z: 0, mine: false, splash: null }));
    // The cheers and splashes with bursts still to come: the list of bursts (null for none), where, the seconds since
    // it began and the next burst to go
    this.shows = Array.from({ length: SHOWS }, () => ({ bursts: null, x: 0, z: 0, t: 0, next: 0 }));
    this.showNext = 0;
    this.actions = this.buildActions();
    // The warm-up stays on show until a frame has been drawn. The lobby draws only some of its frames
    this.warming = true;
    app.once("postrender", () => {
      this.warming = false;
    });
    this.cloudList.forEach((cloud) => cloud.warm());
    this.rings[0].entity.setLocalPosition(0, WARM_DEPTH, 0);
    this.rings[0].entity.enabled = true;
    this.rings[0].t = RING_SECONDS - 0.001;
    this.wave.entity.setLocalPosition(0, WARM_DEPTH, 0);
    this.wave.entity.enabled = true;
    this.wave.t = WAVE_SECONDS - 0.001;
  }

  // Seconds the drawing still holds for after a hit. The scene's clock counts it down
  get freeze() {
    return this.clock.freeze;
  }

  set freeze(seconds) {
    this.clock.freeze = seconds;
  }

  emit(kind, x, y, z, n, speed, up, life, size, gravity, spread) {
    this.clouds[kind].emit(x, y, z, n, speed, up, life, size, gravity, spread);
  }

  // One puff of `look`, one of the trail settings or bursts above
  puff(look, x, z) {
    const { kind, y, speed, up, life, size, gravity } = look;
    const px = x + (look.dx ?? 0);
    const pz = z + (look.dz ?? 0);
    this.emit(kind, px, y, pz, look.n ?? 1, speed, up, life, size, gravity, look.spread ?? 0);
    if (look.with) {
      this.puff(look.with, x, z);
    }
  }

  // Starts a list of bursts at a spot. Those due at once go now, and update sends the rest as their time comes
  play(bursts, x, z) {
    const show = this.shows[this.showNext];
    this.showNext = (this.showNext + 1) % this.shows.length;
    show.bursts = bursts;
    show.x = x;
    show.z = z;
    show.t = 0;
    show.next = 0;
    this.runShow(show, 0);
  }

  runShow(show, dt) {
    const { bursts } = show;
    show.t += dt;
    while (show.next < bursts.length && bursts[show.next].at <= show.t) {
      this.puff(bursts[show.next], show.x, show.z);
      show.next += 1;
    }
    if (show.next === bursts.length) {
      show.bursts = null;
    }
  }

  // Drops the bursts still to come at this `x`, which is where the wardrobe's preview stands. Its cheer or splash stops
  // with the tab that was playing it
  dropShows(x) {
    for (const show of this.shows) {
      if (show.x === x) {
        show.bursts = null;
      }
    }
  }

  // Lets the wardrobe's preview, with a camera of its own, see the particles and the rings on the water
  drawEffectsIn(layer) {
    for (const [kind, cloud] of Object.entries(this.clouds)) {
      if (kind !== "burst") {
        cloud.root.render.layers = [pc.LAYERID_WORLD, layer.id];
      }
    }
    for (const ring of this.rings) {
      ring.entity.render.layers = [pc.LAYERID_WORLD, layer.id];
    }
  }

  splashRing(x, z) {
    const ring = this.rings[this.ringNext];
    this.ringNext = (this.ringNext + 1) % this.rings.length;
    ring.t = 0;
    ring.entity.setLocalPosition(x, -0.1, z);
    ring.entity.enabled = true;
  }

  // `strength` is how hard the hit was, from 0.2 to 1. The victim's squash is the scene's business
  hit(x, z, strength) {
    this.freeze = 0.045 + 0.05 * strength;
    this.shake = Math.max(this.shake, 0.12 + 0.3 * strength);
    const count = 6 + Math.round(8 * strength);
    this.emit("burst", x, STAR_HEIGHT, z, count, 3 + 4 * strength, 2.5, 0.35, STAR_PIXELS / this.unit, 6, STAR_SPREAD);
    this.sound.play("bonk", strength);
  }

  bounce(x, z, strength) {
    this.freeze = 0.06 + 0.05 * strength;
    this.shake = Math.max(this.shake, 0.15 + 0.25 * strength);
    this.emit("drop", x, 0.6, z, 10 + Math.round(8 * strength), 3 + 3 * strength, 2, 0.4, 0.12, 5);
    this.sound.play("bounce", strength);
  }

  // A seal landing: spray, a ring and a thump of the camera
  splash(x, z) {
    this.splashRing(x, z);
    this.emit("drop", x, 0, z, 14, 2.2, 4, 0.7, 0.11, 12);
    this.shake = Math.max(this.shake, 0.18);
    this.sound.play("splash");
  }

  // A penguin starting to fall: the splash comes a moment on, as it goes under. `splash` is the splash worn by whoever
  // knocked it in, or nothing for plain water
  plungeSoon(pen, mine, splash) {
    this.plungeLeft[pen.seat] = PLUNGE_DELAY;
    const at = this.plungeAt[pen.seat];
    at.x = pen.x;
    at.z = pen.z;
    at.mine = mine;
    at.splash = splash;
  }

  plunge(x, z, mine, splash) {
    this.knockout(splash, x, z);
    this.sound.play("splash");
    if (mine) {
      this.sound.play("lose");
    }
  }

  // What shows where a penguin goes under: a ring on the water and the bursts of a splash, by its id, or of plain water
  // for none worn or one this page doesn't know. It makes no sound, so the wardrobe can play it over and over
  knockout(splashId, x, z) {
    this.splashRing(x, z);
    this.play(Object.hasOwn(SPLASHES, splashId ?? "") ? SPLASHES[splashId] : DEFAULT_SPLASH, x, z);
  }

  flick(x, z, heavy, power) {
    this.emit("snow", x, 0.15, z, 6, 1.2, 0.8, 0.4, 0.12, 0);
    this.sound.play(heavy ? "heavy" : "flick", power);
  }

  // Another player's slide, which puffs behind them the way they are going
  slideOf(pen, heavy) {
    const speed = Math.sqrt(pen.vx * pen.vx + pen.vz * pen.vz);
    const back = speed > 0.1 ? BEHIND / speed : 0;
    this.flick(pen.x - pen.vx * back, pen.z - pen.vz * back, heavy, 0.6);
  }

  brace(x, z) {
    this.emit("snow", x, 0.14, z, 8, 1.8, 0.6, 0.35, 0.1, 0);
    this.sound.play("brace");
  }

  // What bursts around the winner as its cheer begins and goes on, by the cheer's id, or the default's stars
  cheerBurst(cheerId, x, z) {
    this.play(cheerLook(cheerId).bursts, x, z);
  }

  // A cheering hop coming back down on the ice
  land(x, z) {
    this.emit("snow", x, 0.14, z, 5, 1.1, 0.5, 0.35, 0.1, 0);
  }

  gulp(x, z) {
    this.emit("star", x, 0.6, z, 12, 2.5, 2.5, 0.45, 0.1, 5);
    this.sound.play("gulp");
  }

  // A fish that sinks splashes. One that was eaten is already gone by the time anything says so, and splashes nothing
  fishGone(fish, kind) {
    if (kind === "sank" && fish.active) {
      this.splashRing(fish.x, fish.z);
      this.emit("drop", fish.x, 0, fish.z, 8, 1.5, 3, 0.5, 0.08, 10);
    } else if (kind === "timeout") {
      this.emit("snow", fish.x, 0.2, fish.z, 8, 1.2, 1, 0.4, 0.1, 0);
    }
  }

  // A crate on its way down, landing, and coming open at `crate` for the penguin `pen`, with what was in it
  crateFalls() {
    this.sound.play("crate");
  }

  crateLands(crate) {
    this.play(CRATE_THUMP, crate.x, crate.z);
    this.shake = Math.max(this.shake, 0.1);
    this.sound.play("land");
  }

  crateOpens(crate, pen, power) {
    this.play(CRATE_BURST, crate.x, crate.z);
    this.sound.play("open");
    if (Object.hasOwn(POWER_BURSTS, power)) {
      this.play(POWER_BURSTS[power], pen.x, pen.z);
      this.sound.play(power);
    }
    if (power === "frost") {
      this.frostFrom(pen.x, pen.z);
    }
  }

  // A crate whose tile sank from under it, going into the sea
  crateSinks(crate) {
    this.splashRing(crate.x, crate.z);
    this.emit("drop", crate.x, 0, crate.z, 12, 2, 3.6, 0.7, 0.11, 12);
    this.sound.play("splash");
  }

  frostFrom(x, z) {
    this.startWave(this.wave, x, z);
  }

  startWave(wave, x, z) {
    wave.t = 0;
    wave.entity.setLocalPosition(x, WAVE_HEIGHT, z);
    wave.entity.enabled = true;
  }

  // A walrus's slam: a ring out to as far as it shoves, snow off the ice and a thump of the camera
  slam(x, z) {
    this.startWave(this.thump, x, z);
    this.play(SLAM_BURST, x, z);
    this.shake = Math.max(this.shake, 0.3);
    this.sound.play("slam");
  }

  // The walrus going under, as its tile cracks
  walrusDives(x, z) {
    this.splashRing(x, z);
    this.emit("drop", x, 0, z, 16, 2.4, 4.2, 0.75, 0.12, 12);
    this.sound.play("splash");
  }

  // A watcher's snowball bursting on the ice
  snowLands(x, z) {
    this.play(SNOW_PUFF_BURST, x, z);
    this.shake = Math.max(this.shake, 0.06);
    this.sound.play("snowhit");
  }

  // A shield's bubble bursting on a hit or a seal's splash
  shieldPops(pen) {
    this.play(SHIELD_POP, pen.x, pen.z);
    this.sound.play("pop");
  }

  // Ice closing round a penguin, and falling off it again
  iceOver(x, z) {
    this.play(ICE_OVER, x, z);
  }

  thaw(x, z) {
    this.play(THAW, x, z);
  }

  sinkTile(tile) {
    this.emit("drop", tile.x, 0, tile.z, 5, 1.2, 1.8, 0.6, 0.09, 9);
    this.sound.play("sink");
  }

  dive() {
    this.sound.play("bubble");
  }

  // The bubbles a diving seal blows, one burst every 0.07 s of its dive
  bubbles(seal, dt) {
    seal.bub -= dt;
    if (seal.bub <= 0) {
      seal.bub = 0.07;
      this.emit("drop", seal.tx + rand(-0.3, 0.3), -0.05, seal.tz + rand(-0.3, 0.3), 1, 0.2, 1.2, 0.35, 0.08, 2);
    }
  }

  // What a sliding penguin kicks up, or the sparkle a penguin holding a fish leaves
  trail(pen, dt) {
    this.trailLeft[pen.seat] -= dt;
    if (this.trailLeft[pen.seat] > 0) {
      return;
    }
    const speed = Math.sqrt(pen.vx * pen.vx + pen.vz * pen.vz);
    if (pen.sliding && speed > TRAIL_SPEED) {
      const look = pen.row[2] & HEAVY ? GOLD_PUFF : (TRAILS[pen.looks.trail] ?? SNOW_PUFF);
      this.trailLeft[pen.seat] = look.every;
      this.puff(look, pen.x - (pen.vx / speed) * BEHIND, pen.z - (pen.vz / speed) * BEHIND);
    } else if (pen.row[2] & FISH) {
      this.trailLeft[pen.seat] = SPARKLE_EVERY;
      this.emit("star", pen.x + rand(-0.4, 0.4), rand(0.5, 1.2), pen.z + rand(-0.4, 0.4), 1, 0.2, 0.6, 0.5, 0.07, 0);
    }
  }

  // What each event from the bot does, as (scene, the player's seat, ...the event's values). A player's own slide, brace
  // and dive play when the finger lifts, so the bot's word on them is left alone
  buildActions() {
    const hundredths = (fn) => (world, mine, x, z, strength) => fn.call(this, x / 100, z / 100, strength / 100);
    return {
      hit: hundredths(this.hit),
      bounce: hundredths(this.bounce),
      slide: (world, mine, seat, heavy) => seat !== mine && this.slideOf(world.pens[seat], Boolean(heavy)),
      brace: (world, mine, seat) => seat !== mine && this.brace(world.pens[seat].x, world.pens[seat].z),
      // `by` is the seat that knocked this one in, or -1, and the splash is the one that seat wears
      fall: (world, mine, seat, by) => this.plungeSoon(world.pens[seat], seat === mine, world.pens[by]?.looks.splash),
      dive: (world, mine, seat) => seat !== mine && this.dive(),
      splash: (world, mine, seat, x, z) => this.splash(x / 100, z / 100),
      gulp: (world) => this.gulp(world.fish.x, world.fish.z),
      crack: () => this.sound.play("crack"),
      sink: (world, mine, tile) => this.sinkTile(world.tiles[tile]),
      fish: (world, mine, x, z) => this.emit("star", x / 100, 0.4, z / 100, 8, 2, 2, 0.4, 0.09, 5),
      fish_gone: (world, mine, kind) => this.fishGone(world.fish, kind),
      // The scene splashes a sinking crate itself, as it meets the water
      crate: () => this.crateFalls(),
      land: (world) => this.crateLands(world.crate),
      open: (world, mine, seat, power) => this.crateOpens(world.crate, world.pens[seat], power),
      pop: (world, mine, seat) => this.shieldPops(world.pens[seat]),
      // The scene draws the wind, the walrus and the snowballs (hazards.js). Here are their sounds and bursts
      wind: () => this.sound.play("gustwarn"),
      gust: () => this.sound.play("gust"),
      rear: () => this.sound.play("rear"),
      slam: (world) => this.slam(world.hazards.walrus.x, world.hazards.walrus.z),
      throw: () => this.sound.play("throw"),
      snow: (world, mine, x, z) => this.snowLands(x / 100, z / 100),
      // The scene's own word that the round's last knockout is going into slow motion
      final: () => this.sound.play("final"),
    };
  }

  // The effects for an event the drawing has reached. `world` is the scene
  hear([kind, ...values], mySeat, world) {
    this.actions[kind]?.(world, mySeat, ...values);
  }

  // `dt` is the drawing's time, which stands still during a freeze
  update(dt) {
    // The first frame drawn shows the warm-up, and the update after it clears it
    if (this.warming) {
      return;
    }
    for (let seat = 0; seat < SEATS; seat += 1) {
      if (this.plungeLeft[seat] >= 0) {
        this.plungeLeft[seat] -= dt;
        if (this.plungeLeft[seat] < 0) {
          const { x, z, mine, splash } = this.plungeAt[seat];
          this.plunge(x, z, mine, splash);
        }
      }
    }
    for (const show of this.shows) {
      if (show.bursts) {
        this.runShow(show, dt);
      }
    }
    for (const cloud of this.cloudList) {
      cloud.update(dt);
    }
    for (const ring of this.rings) {
      if (ring.t < 0) {
        continue;
      }
      ring.t += dt;
      const k = ring.t / RING_SECONDS;
      if (k >= 1) {
        ring.t = -1;
        ring.entity.enabled = false;
        continue;
      }
      const size = 0.8 + k * 2.6;
      ring.entity.setLocalScale(size, 0.25, size);
      ring.material.opacity = 0.8 * (1 - k);
      ring.material.update();
    }
    this.spreadWave(this.wave, dt, WAVE_SECONDS, WAVE_WIDTH);
    this.spreadWave(this.thump, dt, THUMP_SECONDS, THUMP_WIDTH);
  }

  // A ring on the ice growing to `width` across over `seconds`
  spreadWave(wave, dt, seconds, width) {
    if (wave.t < 0) {
      return;
    }
    wave.t += dt;
    const k = wave.t / seconds;
    if (k >= 1) {
      wave.t = -1;
      wave.entity.enabled = false;
      return;
    }
    // Fast at first and slowing, as a puff of cold air would
    const size = 0.8 + (width - 0.8) * (1 - (1 - k) * (1 - k));
    wave.entity.setLocalScale(size, 1, size);
    setShown(wave.entity, 0.9 * (1 - k * k));
  }

  // The camera's nudge for this frame, from `dt` seconds of real time. It dies away quickly
  tremor(dt) {
    const { kick } = this;
    kick.x = 0;
    kick.y = 0;
    kick.z = 0;
    if (this.shake > 0.002) {
      const k = this.shake * (REDUCED ? 0.25 : 1);
      kick.x = rand(-1, 1) * k;
      kick.y = rand(-1, 1) * k * 0.5;
      kick.z = rand(-1, 1) * k;
      this.shake *= Math.exp(-14 * dt);
    }
    return kick;
  }
}

export function createFx(app, sound, clock) {
  return new Fx(app, sound, clock);
}
