// Penguin Wars' world, drawn with PlayCanvas. The bot sends where everything is 30 times a second. This draws it at
// the screen's own frame rate, a moment behind the newest update, so small changes in when updates arrive never show.
import {
  buildCrate,
  buildFish,
  buildPenguin,
  buildSeal,
  buildWarmUp,
  Copies,
  HEAD_HEIGHT,
  hatTop,
  meshShape,
  paint,
  paintSkin,
  PENGUIN_SCALE,
  putOn,
  SEAT_COLORS,
  setRingReady,
  setShown,
  shape,
  thinCap,
} from "./models.js";
import {
  addFrame,
  ALIVE,
  BRACING,
  CRACK,
  CRACK_SECONDS,
  CRATE_FALL_SECONDS,
  decided,
  DIVE_SECONDS,
  DRAW_DELAY,
  FISH,
  FROZEN,
  LEAP_SECONDS,
  newClock,
  Prediction,
  sampleFrames,
  SHIELD,
  SHIELD_SECONDS,
  SINK_SECONDS,
  SNOWBALL_REACH,
  stepClock,
  TICK_RATE,
  TILE_SIZE,
  tileAt,
  tileList,
  WALRUS_REACH,
} from "./motion.js";
import { cheerLook, createFx, WARM_DEPTH } from "./fx.js";
import { createHazards } from "./hazards.js";
import { NameTags } from "./tags.js";

const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const TAU = Math.PI * 2;
export const ICE_Y = 0.09;
// One drawn step never covers more time than this, however long the page was away
const MAX_STEP = 1 / 20;
// Tile states, as the bot sends them
const ICE = 0;
const SINK = 2;
const GONE = 3;
const SEAL_OFF = 0;
// How far along a tile already sinking is drawn when a snapshot is the first the page hears of it. Far enough to look
// sunken while still showing above the water
const SINK_SEEN_LATE = 0.3 * SINK_SECONDS;
const FALL_SECONDS = 1.4;
const SWIM_Y = -0.12;
// A seal with ice over it swims this deep, out of sight, until it is clear of the ice again
const SWIM_UNDER = -0.8;
// A thin tile's bare cap lies just over the top of a tile's body
const THIN_Y = 0.056;
const CHUNKS = 9;
// Speeds that start and end a belly slide, and the speed under which a penguin stops turning. Positions come in
// hundredths, so slower than this the direction between two frames is mostly rounding
const SLIDE_ON = 2.4;
const SLIDE_OFF = 1.0;
const TURN_SPEED = 0.8;
// How high a penguin's name sits, and the gap it keeps above a hat that reaches past that
const NAME_HEIGHT = 1.32;
const NAME_OVER_HAT = 0.04;
// A hat lying flat has width as well as length, so its crown's rim reaches a little past the tip's middle on the screen
const NAME_OVER_TIP = 0.08;
// A penguin's lean eases back toward 0 and never lands on it, so under this it counts as standing
const STILL_LEANING = 0.02;

// The winner's cheer starts this long after the round is decided, so the last splash is seen first. Then it hops this
// many times, each taking this long and going this high
const CHEER_DELAY = 0.25;
const HOPS = 4;
const HOP_SECONDS = 0.42;
const HOP_HEIGHT = REDUCED ? 0.15 : 0.6;
// How hard a cheering hop's landing squashes the penguin, and how fast any squash dies away
const LANDING = 0.6;
const SQUASH_FADE = 8;
// A twirl's turns on the spot, the seconds they take and the small hops it makes meanwhile
const TWIRL_TURNS = 2;
const TWIRL_SECONDS = 1.5;
const TWIRL_HOP_SECONDS = 0.5;
const TWIRL_HOP_HEIGHT = 0.3;
// A backflip's crouch, then its time in the air and how high that goes
const CROUCH_SECONDS = 0.2;
const FLIP_SECONDS = 0.8;
const FLIP_HEIGHT = 1.2;
// A belly spin's drop onto the ice, its turns, the seconds they take and the time to stand up again
const DROP_SECONDS = 0.22;
const SPIN_TURNS = 3;
const SPIN_SECONDS = 1.5;
const RISE_SECONDS = 0.25;
// How far ahead of its feet the middle of a penguin lying on its belly is, which a belly spin turns about
const LYING_MIDDLE = 0.23;
// A crate comes down a line that leans away from the camera, this far back for each unit up, so it drops straight
// down the screen and grows only a little on the way. It starts where the line passes this many pixels above the top
// of the screen, and no further along it than this
const CRATE_LEAN = 1;
const CRATE_ABOVE = 40;
const CRATE_SKY = 18;
// How far through its fall a crate is drawn when a snapshot is the first the page hears of it
const CRATE_SEEN_LATE = 0.6 * CRATE_FALL_SECONDS;
// How big a crate is drawn, how hard its landing squashes it, and how high over the ice its name sits
const CRATE_SIZE = 1.1;
const CRATE_THUMP = 0.9;
const CRATE_NAME_HEIGHT = 1.08;
// A crate on the ice hops this high, this many times every 2 pi seconds, so it reads as there for the taking
const CRATE_HOP = REDUCED ? 0 : 0.1;
const CRATE_BEAT = 5;
// How fast a crate with no tile under it speeds up into the sea, how fast one that was still falling goes in, how far
// under it splashes and how far under it is out of sight
const CRATE_GRAVITY = 3.6;
const CRATE_PLUNGE = -8;
const CRATE_WET = -0.2;
const CRATE_SUNK = -1.5;
// The mark under a falling crate starts this many times its size at rest, which is this against the mesh's own
const MARK_WIDE = 2.6;
const MARK_SIZE = 1.05;
const MARK_LIFT = 0.012;
// A shield's bubble against the penguin inside it, the seconds it takes to swell and, when its time runs out, to
// fade, and how it beats: slowly, then fast for its last seconds, so everyone sees it about to go
const BUBBLE_SIZE = 1.5;
const BUBBLE_IN = 0.18;
const BUBBLE_OUT = 0.3;
const SHIELD_WARNING = 2;
const BUBBLE_BREATH = 3;
const BUBBLE_BLINK = 22;
// A frost's ice takes this long to close round a penguin, and to fall away
const ICE_IN = 0.12;
const ICE_OUT = 0.25;
// What a penguin wears on its body, as the look's kind and the part of the penguin it hangs from
const WORN_SPOTS = [
  ["hat", "head"],
  ["face", "face"],
  ["neck", "neck"],
  ["back", "back"],
];
// The looks of a seat with nothing worn
const BARE = Object.freeze({});
// The ring under the player's penguin swells by this share as the next move comes ready, and how fast that dies away
const RING_POP = REDUCED ? 0 : 0.3;
const RING_SETTLE = 10;
// With no round on show only bits of ice bob behind the title card, so the page draws this many times a second and a
// phone left in the lobby stays cool. A little under the gap between two draws counts, so a 60 Hz screen draws every
// second frame instead of now and then waiting for a third
const IDLE_RATE = 30;
const IDLE_SLACK = 0.004;
// The round's last knockout plays this slowly for this many seconds, with the camera this much closer and this share of
// the way over to where the penguin went in. Then the drawing runs this fast until it is back beside the bot's updates,
// which keep coming at their own speed all along. People who asked for less motion get neither the slow motion nor the
// camera's move: for them the moment only lasts as long, for the page's banner
const FINALE_SLOW = 0.35;
const FINALE_SLOW_SECONDS = 1.2;
const FINALE_FAST = 2;
const FINALE_CLOSER = 0.3;
const FINALE_TOWARD = 0.6;
const FINALE_EASE = 5;
// With a winner left on the ice the camera looks halfway between it and where the penguin went in, and only comes as
// close as keeps both this far inside the picture, which leaves room for the winner's name. While it is in close, a
// name whose owner is nearer the screen's edge than this many pixels is not shown
const FINALE_ROOM = 1.5;
const FINALE_EDGE = 48;
// Whatever happens to the updates, the moment is over by now
const FINALE_LIMIT = 3;

const rand = (low, high) => low + Math.random() * (high - low);
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

const lerp = (from, to, k) => from + (to - from) * k;
// Eases from 0 to 1, slow at both ends
const smooth = (k) => k * k * (3 - 2 * k);
const degrees = (radians) => (radians * 180) / Math.PI;

function turnTo(from, to, k) {
  let difference = to - from;
  while (difference > Math.PI) {
    difference -= TAU;
  }
  while (difference < -Math.PI) {
    difference += TAU;
  }
  return from + difference * k;
}

// One cheering hop, `since` seconds after leaving the ice
function hop(pen, since) {
  pen.cheering = true;
  pen.hop = HOP_HEIGHT * Math.sin((Math.PI * since) / HOP_SECONDS);
}

// Back on the ice `since` seconds ago, for the `count`th time this cheer
function land(pen, count, since) {
  pen.landed = count;
  pen.squash = LANDING * Math.exp(-SQUASH_FADE * since);
}

// The hops that end every cheer: `hops` of them, `since` seconds in, after `before` earlier landings
function hopsFrom(pen, since, before, hops) {
  const count = Math.min(hops, Math.floor(since / HOP_SECONDS));
  if (before + count > 0) {
    land(pen, before + count, since - count * HOP_SECONDS);
  }
  if (count < hops) {
    hop(pen, since % HOP_SECONDS);
  }
  return count < hops;
}

// The winner's moves, by the name a cheer in fx.js gives its own. Each poses the penguin `t` seconds into the cheer,
// from a rest pose, and says whether the cheer is still going
const MOVES = {
  hops: (pen, t, look) => hopsFrom(pen, t, 0, look.hops ?? HOPS),

  // Turns on the spot with small hops, then one big hop
  twirl(pen, t) {
    if (t >= TWIRL_SECONDS) {
      return hopsFrom(pen, t - TWIRL_SECONDS, TWIRL_SECONDS / TWIRL_HOP_SECONDS, 1);
    }
    const count = Math.floor(t / TWIRL_HOP_SECONDS);
    if (count > 0) {
      land(pen, count, t - count * TWIRL_HOP_SECONDS);
    }
    pen.cheering = true;
    pen.hop = TWIRL_HOP_HEIGHT * Math.sin((Math.PI * (t % TWIRL_HOP_SECONDS)) / TWIRL_HOP_SECONDS);
    pen.twirl = TAU * TWIRL_TURNS * smooth(t / TWIRL_SECONDS);
    return true;
  },

  // Crouches, goes over backward in one high jump, then two hops
  backflip(pen, t) {
    const air = (t - CROUCH_SECONDS) / FLIP_SECONDS;
    if (air >= 1) {
      return hopsFrom(pen, t - CROUCH_SECONDS - FLIP_SECONDS, 1, 2);
    }
    if (air < 0) {
      pen.squash = smooth(t / CROUCH_SECONDS);
      return true;
    }
    pen.cheering = true;
    pen.squash = 0;
    pen.hop = FLIP_HEIGHT * Math.sin(Math.PI * air);
    pen.flip = -360 * smooth(air);
    return true;
  },

  // Drops onto its belly, spins like a top, stands up and hops once
  spin(pen, t) {
    const turned = (t - DROP_SECONDS) / SPIN_SECONDS;
    const up = (t - DROP_SECONDS - SPIN_SECONDS) / RISE_SECONDS;
    if (up >= 1) {
      pen.slide = 0;
      return hopsFrom(pen, (up - 1) * RISE_SECONDS, 0, 1);
    }
    const down = turned < 0 ? smooth(t / DROP_SECONDS) : 1 - smooth(Math.max(0, up));
    pen.slide = down;
    pen.center = down;
    pen.twirl = TAU * SPIN_TURNS * smooth(clamp(turned, 0, 1));
    return true;
  },
};

function startApp(canvas) {
  const app = new pc.Application(canvas, {});
  app.setCanvasFillMode(pc.FILLMODE_FILL_WINDOW);
  app.setCanvasResolution(pc.RESOLUTION_AUTO);
  app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  // A new size clears the canvas, so it is drawn again at once, even while the lobby draws slowly
  window.addEventListener("resize", () => {
    app.resizeCanvas();
    app.renderNextFrame = true;
  });
  app.scene.ambientLight = new pc.Color(0.5, 0.58, 0.68);
  return app;
}

function buildCamera(app) {
  const camera = new pc.Entity("camera");
  camera.addComponent("camera", {
    // The sea as it comes out lit, so a tall screen that sees past the far end of the sea shows no line
    clearColor: new pc.Color().fromString("#13567a"),
    fov: 44,
    nearClip: 0.5,
    farClip: 120,
  });
  app.root.addChild(camera);
  return camera;
}

function buildSun(app) {
  const sun = new pc.Entity("sun");
  sun.addComponent("light", {
    type: "directional",
    color: new pc.Color(1, 0.97, 0.92),
    intensity: 1.15,
    castShadows: true,
    shadowDistance: 30,
    shadowResolution: 1024,
    shadowBias: 0.25,
    normalOffsetBias: 0.04,
  });
  sun.setEulerAngles(52, 28, 0);
  app.root.addChild(sun);
}

function buildSea(app) {
  shape(app.root, "plane", paint("#14587a", { gloss: 0.75 }), [0, -0.14, 0], [140, 1, 140], null, false);
  const mesh = pc.Mesh.fromGeometry(
    app.graphicsDevice,
    new pc.CylinderGeometry({ radius: 1, height: 0.02, capSegments: 48 }),
  );
  const shallows = meshShape(app.root, mesh, paint("#1f7192", { gloss: 0.6 }), false);
  shallows.setLocalPosition(0, -0.13, 0);
  return shallows;
}

// A hexagon at its height on a tile
function hexMesh(app, radius, height, y) {
  const geometry = new pc.CylinderGeometry({ radius, height, capSegments: 6 });
  for (let i = 1; i < geometry.positions.length; i += 3) {
    geometry.positions[i] += y;
  }
  return pc.Mesh.fromGeometry(app.graphicsDevice, geometry);
}

function iceKit(app) {
  return {
    tileMesh: hexMesh(app, TILE_SIZE * 0.95, 0.34, -0.12),
    capMesh: hexMesh(app, TILE_SIZE * 0.86, 0.06, 0.06),
    ice: paint("#bfe6f5", { gloss: 0.7 }),
    snow: paint("#f7fcff", { gloss: 0.35 }),
    crack: paint("#7fb4cc", { gloss: 0.5 }),
  };
}

// Each tile says where it is, and the copies draw every tile in one go: a cap in the snow or the crack color, on a
// body. A thin tile has a bare cap in place of its snow, and those are only drawn on a map that has some
function buildFloe(app, kit, count) {
  const bare = thinCap(app, TILE_SIZE * 0.9, THIN_Y);
  const thin = new Copies(app, bare.mesh, bare.material, count, false);
  thin.root.enabled = false;
  return {
    body: new Copies(app, kit.tileMesh, kit.ice, count, true),
    snow: new Copies(app, kit.capMesh, kit.snow, count, true),
    crack: new Copies(app, kit.capMesh, kit.crack, count, true),
    thin,
  };
}

function buildTile(app, spot, index) {
  const root = new pc.Entity(`tile-${index}`);
  app.root.addChild(root);
  root.setLocalPosition(spot.x, 0, spot.z);
  return { ...spot, root, state: ICE, t: 0, tilt: rand(-1, 1), thin: false };
}

// Bits of ice floating around the floe
function buildChunk(app) {
  const root = new pc.Entity();
  app.root.addChild(root);
  const angle = rand(0, TAU);
  const distance = rand(8, 12);
  const size = rand(0.35, 0.75);
  root.setLocalScale(size, size, size);
  return { root, x: Math.cos(angle) * distance, z: Math.sin(angle) * distance, spin: rand(0, 360), ph: rand(0, 6) };
}

class Scene {
  constructor(canvas, tagLayer, sound) {
    this.canvas = canvas;
    this.app = startApp(canvas);
    this.buffer = [];
    this.round = null;
    this.rules = null;
    this.mySeat = null;
    this.prediction = new Prediction();
    this.listeners = [];
    this.time = 0;
    this.frameDt = 0;
    // Seconds since the lobby was last drawn, and whether the wardrobe's preview is on show, which draws at full speed
    this.idleFor = 0;
    this.previewing = false;
    // The drawing's clock, which a hit holds still for a moment
    this.clock = newClock();
    // The last knockout's slow motion: seconds into it (-1 for none), where the penguin went in, how far the camera
    // has closed in on that, from 0 to 1, and the round it played for, as a round gets one. Then the spot the camera
    // moves over to and the share of its distance it comes closer, which aimFinale works out
    this.finale = { t: -1, x: 0, z: 0, zoom: 0, round: null, aimX: 0, aimZ: 0, closer: 0 };
    this.camDist = 14;
    this.floeRadius = 0;
    this.tagPos = new pc.Vec3();
    this.tagScreen = new pc.Vec3();
    this.camera = buildCamera(this.app);
    buildSun(this.app);
    this.shallows = buildSea(this.app);
    this.ice = iceKit(this.app);
    this.tiles = tileList().map((spot, index) => buildTile(this.app, spot, index));
    this.floe = buildFloe(this.app, this.ice, this.tiles.length);
    this.caps = [this.floe.snow, this.floe.crack, this.floe.thin];
    this.tiles.forEach((tile, index) => this.placeTile(tile, index));
    this.chunks = Array.from({ length: CHUNKS }, () => buildChunk(this.app));
    this.chunkBodies = new Copies(this.app, this.ice.tileMesh, this.ice.ice, CHUNKS, false);
    this.chunkCaps = new Copies(this.app, this.ice.capMesh, this.ice.snow, CHUNKS, false);
    this.pens = SEAT_COLORS.map((color, seat) => this.buildPen(seat));
    this.fish = { ...buildFish(this.app), active: false, x: 0, z: 0, fall: -1 };
    this.fish.root.name = "fish";
    this.fx = createFx(this.app, sound, this.clock);
    this.hazards = createHazards(this, ICE_Y);
    this.onEvent((event) => this.fx.hear(event, this.mySeat, this));
    this.tags = new NameTags(tagLayer, SEAT_COLORS.length);
    // The screen point for each seat's name and then the crate's, filled in again every frame
    this.tagSpots = new Array(SEAT_COLORS.length + 1).fill(null);
    // The crate: "off", or in its "fall", at "rest" on the ice or in its "sink" after its tile. `t` is the seconds
    // in that state, `sky` how far up its fall line it starts, and `doomed` says its tile went while it was falling
    this.crate = {
      ...buildCrate(this.app),
      state: "off",
      x: 0,
      z: 0,
      t: 0,
      sky: 0,
      squash: 0,
      doomed: false,
      // A sinking crate's height, speed, whether it has splashed yet and which way it tips
      y: 0,
      vy: 0,
      wet: false,
      tip: 1,
      spot: { x: 0, y: 0, seal: false, wait: false },
    };
    this.warmUp();
    this.eventActions = this.buildEventActions();
    // The seat cheering its win (-1 for none yet this round), seconds into the cheer, and the landings it has made
    this.cheer = { seat: -1, t: 0, hops: 0 };
    this.measureFloe();
    this.app.on("update", this.update, this);
    // Names are placed once the camera has moved for the frame, or a shake would leave them a frame behind
    this.app.on("prerender", this.drawTags, this);
    this.app.start();
  }

  // One of each shape a crate brings shows under the sea until a frame has been drawn, so the graphics card builds
  // what draws them before a round needs it
  warmUp() {
    const warm = buildWarmUp(this.app);
    warm.setLocalPosition(0, WARM_DEPTH, 0);
    this.app.once("postrender", () => {
      warm.enabled = false;
    });
  }

  buildPen(seat) {
    const seal = buildSeal(this.app, SEAT_COLORS[seat]);
    seal.root.name = `seal-${seat}`;
    return {
      seat,
      parts: this.buildParts(seat, false),
      seal: { ...seal, state: "off", t: 0, x: 0, y: 0, z: 0, ang: 0, dir: 1, bub: 0, tx: 0, tz: 0, sx: 0, sz: 0, yaw: 0 },
      row: null,
      x: 0,
      z: 0,
      vx: 0,
      vz: 0,
      yaw: 0,
      slide: 0,
      sliding: false,
      squash: 0,
      // How hard the player is pulling back to aim, from 0 to 1, and which way the penguin turns for it
      windup: 0,
      aimYaw: 0,
      bracing: false,
      braceLeft: 0,
      // Seconds into the fall into the sea, or -1 while on the ice
      fall: -1,
      // A cheer's pose: how high a hop has it off the ice, whether it flaps, how far it has gone over backward (in
      // degrees) and turned on the spot, how far a penguin on its belly is pulled back over its own middle (0 to 1),
      // and the landings made so far
      hop: 0,
      cheering: false,
      flip: 0,
      twirl: 0,
      center: 0,
      landed: 0,
      // Whether its next move was ready when last drawn, and how far its ring is swollen for that
      ready: false,
      ringPop: 0,
      // Whether a shield is up, the seconds since it went up and how much of its bubble shows, from 0 to 1. The same
      // for a frost's ice
      shielded: false,
      shieldFor: 0,
      bubble: 0,
      frozen: false,
      iced: 0,
      ph: rand(0, 6),
      // What its player wears, as {kind: id}, how far the hat reaches past the head, and how far that moves the name up
      looks: BARE,
      hatReach: 0,
      nameRise: 0,
    };
  }

  buildParts(seat, mine) {
    const parts = buildPenguin(this.app, SEAT_COLORS[seat], mine);
    parts.root.name = `penguin-${seat}`;
    parts.root.enabled = false;
    return parts;
  }

  buildEventActions() {
    return {
      crack: (tile) => this.setTile(tile, CRACK),
      sink: (tile) => this.setTile(tile, SINK),
      gone: (tile) => this.setTile(tile, GONE),
      // The player's own penguin squashed when the finger lifted
      slide: (seat) => seat !== this.mySeat && this.squash(seat, 0.5),
      hit: (x, z, strength, victim) => this.squash(victim, 1),
      bounce: (x, z, strength, attacker) => this.squash(attacker, 1),
      splash: (seat, x, z) => this.shovePens(x / 100, z / 100, this.rules.seal_reach),
      // A fall also says who and what did it, and a snowball's thrower, so whether it was seen comes last
      fall: (seat, ...rest) => this.startFall(this.pens[seat], rest[rest.length - 1]),
      seal: (seat) => this.surfaceSeal(this.pens[seat]),
      dive: (seat, x, z) => this.diveSeal(this.pens[seat].seal, x / 100, z / 100),
      fish: (x, z) => this.showFish(x / 100, z / 100),
      fish_gone: (kind) => this.loseFish(kind),
      gulp: () => this.hideFish(),
      crate: (x, z, name, seen) => this.dropCrate(x / 100, z / 100, name, seen ? 0 : CRATE_SEEN_LATE),
      land: (seen) => this.landCrate(seen),
      open: (seat, power, seen) => this.openCrate(seat, power, seen),
      crate_gone: (seen) => this.loseCrate(seen),
      pop: (seat) => this.popShield(this.pens[seat]),
      wind: (deg) => this.hazards.warn(deg),
      gust: (deg) => this.hazards.blow(deg),
      calm: () => this.hazards.calm(),
      rear: () => this.hazards.rear(),
      slam: () => this.slamPens(),
      sit: () => this.hazards.sit(),
      walrus_gone: (seen) => this.hazards.walrusLeaves(seen),
      // One the drawing didn't reach has landed by now
      throw: (x, z, name, seen) => seen && this.hazards.throwBall(x / 100, z / 100),
      snow: (x, z) => this.landSnowball(x / 100, z / 100),
    };
  }

  // ---------- What game.js calls ----------

  // A snapshot's board, or null with no round. The same round just carries on: the board goes in line with the frames,
  // so its events run as theirs do and nothing restarts. A different round starts from clean ice in its map's shape,
  // which is there from the first frame drawn: the tiles its map leaves out never show, sink or splash
  reset(board, round) {
    if (!board || round !== this.round) {
      this.clearRound();
      this.round = board ? round : null;
      if (board) {
        this.shapeIce(board);
      }
    }
    if (board) {
      this.push(board);
    }
  }

  // The ice as a board has it: every tile's state, and which tiles are thin
  shapeIce(board) {
    board.t.forEach((state, index) => this.setTile(index, state, state === SINK ? SINK_SEEN_LATE : 0));
    this.markThin(board.map?.thin);
  }

  // The thin tiles still whole, by number, as a board lists them. Nothing for a map with none
  markThin(numbers = []) {
    this.tiles.forEach((tile, index) => {
      const thin = numbers.includes(index);
      if (thin !== tile.thin) {
        tile.thin = thin;
        this.placeTile(tile, index);
      }
    });
    this.floe.thin.root.enabled = numbers.length > 0;
  }

  push(frame) {
    for (const entry of addFrame(this.buffer, frame, performance.now() / 1000, this.clock.behind)) {
      this.runFrame(entry, false);
    }
  }

  // `nemesis` is the id of this player's nemesis, or null. Their name tag carries a mark on this page alone
  setSeats(seats, mySeat, nemesis = null) {
    this.tags.setSeats(seats, mySeat, nemesis);
    if (mySeat !== this.mySeat) {
      this.moveRing(mySeat);
    }
    seats.forEach((seat, number) => this.dress(this.pens[number], seat.looks));
  }

  // Puts on what a seat wears, `looks` as {kind: id} with only the kinds worn: the skin, the hat and the things on the
  // face, neck and back. The trail, cheer and splash are read from `pen.looks` when they play. Snapshots come often, so only
  // a kind that differs from what is on changes anything. A seal wears the hat alone. The wardrobe dresses its own
  // penguin with this, which has no seal
  dress(pen, looks) {
    const worn = pen.looks ?? BARE;
    pen.looks = looks;
    if (looks.skin !== worn.skin) {
      paintSkin(pen.parts, looks.skin ?? null);
    }
    for (const [kind, part] of WORN_SPOTS) {
      if (looks[kind] !== worn[kind]) {
        putOn(pen.parts[part], looks[kind] ?? null);
      }
    }
    if (looks.hat !== worn.hat) {
      pen.hatReach = looks.hat ? hatTop(looks.hat) + NAME_OVER_HAT : 0;
      pen.nameRise = looks.hat ? Math.max(0, HEAD_HEIGHT + pen.hatReach - NAME_HEIGHT) : 0;
      if (pen.seal) {
        putOn(pen.seal.head, looks.hat ?? null);
      }
    }
  }

  setRules(rules) {
    this.rules = rules;
  }

  // Effects listen here for each event, as the drawing reaches it. Events on frames skipped because the page wasn't
  // drawing change the game's state without reaching listeners, so a page coming back doesn't play them all at once.
  // Two events are the scene's own and never come from the bot: ["final", seat] as the last knockout's slow motion
  // begins, and ["final_done"] when it is over
  onEvent(fn) {
    this.listeners.push(fn);
  }

  tell(event) {
    this.listeners.forEach((listen) => listen(event));
  }

  // The player's own penguin has the ring that shows its next move is ready, and every other one a ring in its seat's
  // color, so changing seats rebuilds the two penguins involved
  moveRing(mySeat) {
    const seats = [this.mySeat, mySeat].filter((seat) => seat !== null);
    for (const seat of seats) {
      const pen = this.pens[seat];
      const showing = pen.parts.root.enabled;
      pen.parts.root.destroy();
      pen.parts = this.buildParts(seat, seat === mySeat);
      pen.parts.root.enabled = showing;
      this.dressAgain(pen);
    }
    this.mySeat = mySeat;
    this.prediction.drop();
  }

  // A penguin built anew is bare, so it puts on everything its seat wears
  dressAgain(pen) {
    const { looks } = pen;
    pen.looks = BARE;
    this.dress(pen, looks);
  }

  // ---------- The round's state ----------

  clearRound() {
    this.buffer.length = 0;
    this.endFinale();
    this.prediction.drop();
    this.tiles.forEach((tile, index) => this.setTile(index, ICE));
    this.markThin();
    this.hazards.clear();
    for (const pen of this.pens) {
      Object.assign(pen, {
        vx: 0,
        vz: 0,
        yaw: 0,
        slide: 0,
        sliding: false,
        squash: 0,
        windup: 0,
        bracing: false,
        braceLeft: 0,
        fall: -1,
        hop: 0,
        cheering: false,
        flip: 0,
        twirl: 0,
        center: 0,
        landed: 0,
        ready: false,
        ringPop: 0,
      });
      pen.parts.root.enabled = false;
      this.clearPowers(pen);
      this.hideSeal(pen);
    }
    this.cheer.seat = -1;
    this.hideFish();
    this.hideCrate();
  }

  // The frames the drawing has reached run their events, in order. The frame just before the drawn moment stays in the
  // buffer, since the drawing still reads it
  runDue({ a, b, k }) {
    const last = k === 1 ? b : a;
    for (const entry of this.buffer) {
      this.runFrame(entry, true);
      if (entry === last) {
        break;
      }
    }
    this.buffer.splice(0, this.buffer.indexOf(a));
  }

  // `seen` says the drawing reached this frame, rather than skipping it
  runFrame(entry, seen) {
    if (entry.ran) {
      return;
    }
    entry.ran = true;
    if (!seen) {
      this.prediction.handBack();
      this.placePenguins(entry.frame.p);
    }
    for (const event of entry.frame.e ?? []) {
      this.runEvent(event, seen);
    }
    if (seen) {
      this.watchForFinale(entry.frame);
    } else {
      this.placeSeals();
    }
    if (entry.frame.t) {
      this.syncBoard(entry.frame);
    }
  }

  // A fall that leaves one penguin on the ice, or none, is the round's last knockout, and the drawing has just shown it
  watchForFinale(frame) {
    const falls = (frame.e ?? []).filter((event) => event[0] === "fall");
    if (falls.length && this.finale.round !== this.round && decided(frame.p)) {
      this.startFinale(this.pens[falls[falls.length - 1][1]]);
    }
  }

  startFinale(pen) {
    Object.assign(this.finale, { t: 0, x: pen.x, z: pen.z, round: this.round });
    this.clock.rate = REDUCED ? 1 : FINALE_SLOW;
    this.tell(["final", pen.seat]);
  }

  // Slow while the moment plays, then fast until the drawing is back with the bot's updates, or has shown the last of
  // them, as they stop when the round's results come. It ends there, or at once for a page that was away, and whatever
  // happens it ends in time
  stepFinale(dt) {
    const { finale, clock } = this;
    if (finale.t < 0) {
      return;
    }
    finale.t += dt;
    const slow = finale.t < FINALE_SLOW_SECONDS;
    const back = clock.behind <= 0 || Boolean(this.buffer[this.buffer.length - 1]?.ran);
    if (clock.away || finale.t >= FINALE_LIMIT || (!slow && back)) {
      this.endFinale();
    } else if (!REDUCED) {
      clock.rate = slow ? FINALE_SLOW : FINALE_FAST;
    }
  }

  // Back to full speed, with nothing left to win back. Nothing happens with no finale on
  endFinale() {
    if (this.finale.t < 0) {
      return;
    }
    this.finale.t = -1;
    this.clock.rate = 1;
    this.clock.behind = 0;
    this.tell(["final_done"]);
  }

  // Only drawing keeps a penguin's place up to date, so a skipped frame does it, or its events would start from where
  // the penguin stood when the page stopped drawing
  placePenguins(rows) {
    for (const pen of this.pens) {
      if (pen.fall < 0) {
        const [x, z] = rows[pen.seat];
        Object.assign(pen, { x: x / 100, z: z / 100, vx: 0, vz: 0 });
      }
    }
  }

  // A seal the drawing didn't follow has been swimming out of sight, so it is out on its circle by now
  placeSeals() {
    for (const pen of this.pens) {
      if (pen.seal.state === "swim") {
        this.putOnCircle(pen.seal);
      }
    }
  }

  runEvent(event, seen) {
    const [kind, ...values] = event;
    // The player's own touch has already shown this hit, squash and all
    const shown = seen && this.prediction.echoes(event, this.mySeat);
    if (!shown) {
      this.eventActions[kind]?.(...values, seen);
    }
    this.prediction.hear(event, this.mySeat, this.rules);
    if (seen && !shown) {
      this.listeners.forEach((listen) => listen(event));
    }
  }

  // A snapshot is the whole truth about the round. What the events already did matches it and stays as it is, and
  // what differs is what this page missed: everything for someone arriving mid-round
  syncBoard(board) {
    const missedIce = board.t.some((state, index) => state !== this.tiles[index].state);
    this.shapeIce(board);
    board.seals.forEach((state, seat) => this.syncSeal(this.pens[seat], state, board.p[seat]));
    this.syncFish(board.fish);
    this.syncCrate(board.crate);
    this.hazards.sync(board.map, board.snow);
    // Ice that went while the page wasn't listening moved the seals' circle, and nobody watched them swim to it
    if (missedIce) {
      this.placeSeals();
    }
  }

  syncSeal(pen, state, row) {
    const alive = (row[2] & ALIVE) !== 0;
    if (alive && pen.fall >= 0) {
      pen.fall = -1;
      this.hideSeal(pen);
    } else if (!alive && state !== SEAL_OFF && pen.seal.state === "off") {
      this.surfaceSeal(pen);
      this.putOnCircle(pen.seal);
    }
  }

  syncFish(spot) {
    const fish = this.fish;
    if (!spot) {
      if (fish.active && fish.fall < 0) {
        this.hideFish();
      }
      return;
    }
    const [x, z] = [spot[0] / 100, spot[1] / 100];
    if (!fish.active || fish.x !== x || fish.z !== z) {
      this.showFish(x, z);
    }
  }

  // The board's crate as [x, z, whether it has landed, whose it is], or nothing for none. One this page doesn't show
  // is drawn part of the way down, or standing on the ice
  syncCrate(row) {
    const crate = this.crate;
    const out = crate.state === "rest" || (crate.state === "fall" && !crate.doomed);
    if (!row) {
      if (out) {
        this.hideCrate();
      }
      return;
    }
    const [x, z] = [row[0] / 100, row[1] / 100];
    if (!out || crate.x !== x || crate.z !== z) {
      this.dropCrate(x, z, row[3], CRATE_SEEN_LATE);
    }
    if (row[2] && crate.state === "fall") {
      this.landCrate(false);
    }
  }

  setTile(index, state, t = 0) {
    const tile = this.tiles[index];
    if (tile.state === state) {
      return;
    }
    tile.state = state;
    tile.t = t;
    if (state === ICE) {
      tile.root.setLocalPosition(tile.x, 0, tile.z);
      tile.root.setLocalEulerAngles(0, 0, 0);
    }
    this.placeTile(tile, index);
    this.measureFloe();
  }

  // Puts a tile's body and cap where its entity is, or takes them away once it is gone. A whole tile's cap is snow, or
  // bare on thin ice, and any other tile's is cracked
  placeTile(tile, index) {
    const { body, snow, crack, thin } = this.floe;
    const cap = tile.state !== ICE ? crack : tile.thin ? thin : snow;
    for (const other of this.caps) {
      if (other !== cap) {
        other.empty(index);
      }
    }
    if (tile.state === GONE) {
      body.empty(index);
      cap.empty(index);
    } else {
      const place = tile.root.getWorldTransform();
      body.place(index, place);
      cap.place(index, place);
    }
  }

  measureFloe() {
    let longest = 0;
    for (const tile of this.tiles) {
      if (tile.state === ICE || tile.state === CRACK) {
        longest = Math.max(longest, Math.hypot(tile.x, tile.z) + TILE_SIZE);
      }
    }
    this.floeRadius = Math.max(longest, TILE_SIZE);
  }

  squash(seat, amount) {
    this.pens[seat].squash = amount;
  }

  // A seal's landing, a walrus's slam and a snowball shove the penguins within `reach` of them, unless they are bracing
  shovePens(x, z, reach) {
    for (const pen of this.pens) {
      const near = Math.hypot(pen.x - x, pen.z - z);
      if (pen.fall < 0 && !pen.bracing && near <= reach && near >= 0.05) {
        this.squash(pen.seat, 0.7);
      }
    }
  }

  slamPens() {
    const { walrus } = this.hazards;
    if (this.hazards.slam()) {
      this.shovePens(walrus.x, walrus.z, WALRUS_REACH);
    }
  }

  landSnowball(x, z) {
    this.hazards.landBall(x, z);
    this.shovePens(x, z, SNOWBALL_REACH);
  }

  // Whether a tile is over this spot on the water, whole, cracked or still going down
  iceOver(x, z) {
    const tile = this.tiles[tileAt(x, z)];
    return Boolean(tile) && tile.state !== GONE;
  }

  // A fall the drawing didn't reach was over before the player could see it
  startFall(pen, seen) {
    pen.fall = seen ? 0 : FALL_SECONDS;
    pen.parts.root.enabled = pen.parts.root.enabled && seen;
    pen.parts.beakFish.enabled = false;
    pen.parts.shield.enabled = false;
    // The ring that says whose penguin this is lies on the ice, so it goes as the penguin leaves it
    this.showColorRing(pen, false);
    this.clearPowers(pen);
  }

  showColorRing({ parts }, shown) {
    if (parts.colorRing) {
      parts.colorRing.enabled = shown;
    }
  }

  // A penguin with no shield and no frost on it
  clearPowers(pen) {
    Object.assign(pen, { shielded: false, shieldFor: 0, bubble: 0, frozen: false, iced: 0 });
    pen.parts.bubble.enabled = false;
    pen.parts.ice.enabled = false;
  }

  // A hit or a seal's splash bursts the bubble at once. One whose time ran out fades instead, as its flag goes
  popShield(pen) {
    pen.bubble = 0;
    pen.parts.bubble.enabled = false;
  }

  // A seal comes up where its penguin went in
  surfaceSeal(pen) {
    pen.parts.root.enabled = false;
    pen.fall = Math.max(pen.fall, FALL_SECONDS);
    const dir = Math.random() < 0.5 ? -1 : 1;
    Object.assign(pen.seal, { state: "swim", x: pen.x, z: pen.z, y: -0.7, ang: Math.atan2(pen.z, pen.x), dir });
    pen.seal.root.enabled = true;
  }

  swimRadius() {
    return this.floeRadius + 0.8;
  }

  putOnCircle(seal) {
    const radius = this.swimRadius();
    Object.assign(seal, { x: Math.cos(seal.ang) * radius, z: Math.sin(seal.ang) * radius, y: SWIM_Y });
  }

  hideSeal(pen) {
    pen.seal.state = "off";
    pen.seal.root.enabled = false;
  }

  // The bot only says where a seal is going, and each page's seal swims on its own clock. So it swims round to just
  // past the target, dives and leaps at it. The player's own seal is already diving when the bot's answer lands, so it
  // keeps its time and only takes the bot's spot
  diveSeal(seal, x, z) {
    const angle = Math.atan2(z, x);
    Object.assign(seal, {
      t: seal.state === "dive" ? seal.t : 0,
      bub: seal.state === "dive" ? seal.bub : 0,
      state: "dive",
      tx: x,
      tz: z,
      sx: x + Math.cos(angle) * 1.1,
      sz: z + Math.sin(angle) * 1.1,
    });
  }

  showFish(x, z) {
    Object.assign(this.fish, { active: true, x, z, fall: -1 });
    this.fish.root.enabled = true;
  }

  hideFish() {
    this.fish.active = false;
    this.fish.root.enabled = false;
  }

  loseFish(kind) {
    if (kind === "sank" && this.fish.active) {
      this.fish.fall = 0;
    } else {
      this.hideFish();
    }
  }

  // A crate starts down toward a tile, `into` seconds into its fall, with its name over the spot from the first moment
  dropCrate(x, z, name, into) {
    Object.assign(this.crate, { state: "fall", x, z, t: into, sky: this.skyOver(x, z), squash: 0, doomed: false });
    this.tags.nameCrate(name);
  }

  // How far up its fall line a crate over this spot is out of sight above the screen
  skyOver(x, z) {
    let far = 4;
    while (far < CRATE_SKY && this.screenOf(this.tagPos.set(x, ICE_Y + far, z - far * CRATE_LEAN)).y > -CRATE_ABOVE) {
      far += 1;
    }
    return far;
  }

  // The bot says when a crate lands, and it can be opened from then. `seen` says the drawing reached the landing
  landCrate(seen) {
    Object.assign(this.crate, { state: "rest", t: 0, squash: seen ? CRATE_THUMP : 0 });
  }

  // An opened crate is gone at once, and the word for what was in it floats up over whoever opened it
  openCrate(seat, power, seen) {
    this.hideCrate();
    if (seen) {
      this.tags.say(seat, power);
    }
  }

  // Its tile sank from under it. A crate on the ice tips into the sea, and one still falling carries on down into it
  loseCrate(seen) {
    const crate = this.crate;
    if (!seen || crate.state === "off") {
      this.hideCrate();
    } else if (crate.state === "fall") {
      crate.doomed = true;
    } else {
      this.sinkCrate(0);
    }
    this.tags.nameCrate(null);
    crate.mark.enabled = false;
  }

  // `speed` is how fast it is going down as it starts
  sinkCrate(speed) {
    const tip = Math.random() < 0.5 ? -1 : 1;
    Object.assign(this.crate, { state: "sink", t: 0, y: ICE_Y, vy: speed, wet: false, tip });
  }

  hideCrate() {
    const crate = this.crate;
    crate.state = "off";
    crate.root.enabled = false;
    crate.mark.enabled = false;
    this.tags.nameCrate(null);
  }

  // ---------- Drawing ----------

  // Whether this frame is drawn. A round, its results and the wardrobe's preview draw every frame
  pace(rawDt) {
    const idle = this.round === null && !this.previewing;
    this.app.autoRender = !idle;
    this.idleFor = idle ? this.idleFor + rawDt : 0;
    if (this.idleFor >= 1 / IDLE_RATE - IDLE_SLACK) {
      this.idleFor = 0;
      this.app.renderNextFrame = true;
    }
  }

  update(rawDt) {
    this.pace(rawDt);
    const realDt = Math.min(rawDt, MAX_STEP);
    this.frameDt = realDt;
    // Slow motion slows everything drawn: the sway of things and the effects as well as the bot's updates
    const paced = realDt * this.clock.rate;
    this.time += paced;
    const now = performance.now() / 1000;
    const clockDt = stepClock(this.clock, rawDt, now);
    this.stepFinale(realDt);
    const dt = Math.min(clockDt, MAX_STEP);
    this.stepPrediction(clockDt);
    const sample = sampleFrames(this.buffer, now - this.clock.lag - this.clock.behind, DRAW_DELAY);
    if (sample) {
      this.pens.forEach((pen) => this.readSeat(pen, sample));
      this.runDue(sample);
      this.findWinner(sample);
      this.pens.forEach((pen) => this.drawPenguin(pen, dt));
    }
    this.pens.forEach((pen) => this.drawSeal(pen, dt));
    this.drawTiles(dt, Boolean(sample) && decided(sample.b.frame.p));
    this.drawFish(dt);
    this.drawCrate(dt);
    this.hazards.update(dt);
    this.drawChunks();
    this.drawCamera(realDt);
    // Particles stand still while the drawing is held, then run at real time, not the catching-up clock
    this.fx.update(clockDt > 0 ? paced : 0);
  }

  // A long gap between two draws means the page was away, and its guesses are old news. The ghost gets the engine's own
  // time, which runs past the drawing's short step, so it keeps up with the bot through a few slow frames. A touch on
  // another penguin shows its hit at once, without waiting for the bot
  stepPrediction(clockDt) {
    const { prediction } = this;
    if (this.clock.away) {
      prediction.drop();
    }
    const touch = prediction.meet(this.pens, this.mySeat, this.rules);
    if (touch) {
      this.squash(touch.bracing ? this.mySeat : touch.seat, 1);
      this.fx[touch.bracing ? "bounce" : "hit"](touch.x, touch.z, touch.strength);
    }
    prediction.step(clockDt, this.rules);
    // The walrus throws the player's penguin back like a brace, and that shows at once as well
    const bump = prediction.bumped(this.mySeat, this.rules);
    if (bump) {
      this.squash(this.mySeat, 1);
      this.fx.bounce(bump.x, bump.z, bump.strength);
    }
  }

  // Where seat N is drawn now and how fast it is going. Everything that shows a penguin gets its place from here
  drawnAt(seat, { a, b, k }) {
    const [ax, az] = a.frame.p[seat];
    const [bx, bz] = b.frame.p[seat];
    const spot = {
      x: lerp(ax, bx, k) / 100,
      z: lerp(az, bz, k) / 100,
      vx: ((bx - ax) / 100) * TICK_RATE,
      vz: ((bz - az) / 100) * TICK_RATE,
    };
    return seat === this.mySeat ? this.prediction.shown(spot) : spot;
  }

  // Once the drawing reaches the frame that decided the round, its one penguin left gets ready to cheer
  findWinner({ a }) {
    const rows = a.frame.p;
    if (this.cheer.seat !== -1 || !decided(rows)) {
      return;
    }
    const seat = rows.findIndex((row) => row[2] & ALIVE);
    if (seat !== -1) {
      Object.assign(this.cheer, { seat, t: -CHEER_DELAY, hops: 0 });
    }
  }

  // A penguin's row comes from the newest frame whose events have run, so its flags never trail what an event said
  readSeat(pen, sample) {
    pen.row = (sample.k === 1 ? sample.b : sample.a).frame.p[pen.seat];
    if (pen.fall < 0) {
      Object.assign(pen, this.drawnAt(pen.seat, sample));
    }
  }

  drawPenguin(pen, dt) {
    const parts = pen.parts;
    if (pen.fall >= 0) {
      if (parts.root.enabled) {
        this.drawFall(pen, dt);
      }
      return;
    }
    const flags = pen.row[2];
    if (!(flags & ALIVE)) {
      // It fell before this page heard of it, so there's nothing to show until its seal comes up
      pen.fall = FALL_SECONDS;
      parts.root.enabled = false;
      return;
    }
    parts.root.enabled = true;
    this.showColorRing(pen, true);
    this.stepPowers(pen, flags, dt);
    this.stepBrace(pen, (flags & BRACING) !== 0 || (pen.seat === this.mySeat && this.prediction.bracing), dt);
    this.stepPose(pen, dt);
    this.stepCheer(pen, dt);
    this.posePenguin(pen);
    this.fx.trail(pen, dt);
    const spent = pen.seat === this.mySeat && this.prediction.fishSpent;
    parts.beakFish.enabled = (flags & FISH) !== 0 && !spent;
    if (parts.ring) {
      this.drawRing(pen, this.prediction.waitOn(pen.row[3]) === 0, dt);
    }
  }

  // The ring greys while the player waits for the next move, and swells for a moment as it comes ready
  drawRing(pen, ready, dt) {
    const { ring } = pen.parts;
    setRingReady(ring, ready);
    if (ready && !pen.ready) {
      pen.ringPop = RING_POP;
    }
    pen.ready = ready;
    pen.ringPop *= Math.exp(-RING_SETTLE * dt);
    const size = 1 + pen.ringPop;
    ring.setLocalScale(size, 1, size);
  }

  stepBrace(pen, bracing, dt) {
    if (bracing && !pen.bracing) {
      pen.braceLeft = this.rules.brace_seconds;
    }
    pen.bracing = bracing;
    pen.braceLeft = Math.max(0, pen.braceLeft - dt);
  }

  // What a crate's powers put on a penguin, from its flags: a bubble for as long as its shield is up, and ice while
  // a frost holds it. The page times the shield itself, from when its flag first shows
  stepPowers(pen, flags, dt) {
    const shielded = (flags & SHIELD) !== 0;
    if (shielded && !pen.shielded) {
      pen.shieldFor = 0;
    }
    pen.shielded = shielded;
    pen.shieldFor += dt;
    pen.bubble = clamp(pen.bubble + (shielded ? dt / BUBBLE_IN : -dt / BUBBLE_OUT), 0, 1);
    const frozen = (flags & FROZEN) !== 0;
    if (frozen !== pen.frozen) {
      pen.frozen = frozen;
      this.fx[frozen ? "iceOver" : "thaw"](pen.x, pen.z);
    }
    pen.iced = clamp(pen.iced + (frozen ? dt / ICE_IN : -dt / ICE_OUT), 0, 1);
    this.drawBubble(pen);
    this.drawIce(pen);
  }

  drawBubble({ parts, bubble, shieldFor }) {
    const shell = parts.bubble;
    shell.enabled = bubble > 0;
    if (!shell.enabled) {
      return;
    }
    const ending = shieldFor > SHIELD_SECONDS - SHIELD_WARNING;
    const beat = Math.sin(shieldFor * (ending ? BUBBLE_BLINK : BUBBLE_BREATH));
    const size = BUBBLE_SIZE * (0.5 + 0.5 * smooth(bubble)) * (1 + beat * (ending ? 0.05 : 0.025));
    shell.setLocalScale(size, size, size);
    // Its rim and glint are built facing the camera, whichever way the penguin turns
    shell.setRotation(pc.Quat.IDENTITY);
    setShown(shell, bubble * (ending ? 0.6 + 0.4 * beat : 1));
  }

  drawIce({ parts, iced }) {
    const { ice } = parts;
    ice.enabled = iced > 0;
    if (ice.enabled) {
      const size = 0.7 + 0.3 * smooth(iced);
      ice.setLocalScale(size, size, size);
      setShown(ice, iced);
    }
  }

  // The penguin's slide and facing, from how it moves between frames. One bracing or shut in ice stands as it is
  stepPose(pen, dt) {
    const speed = Math.hypot(pen.vx, pen.vz);
    const held = pen.bracing || pen.frozen;
    if (held) {
      pen.sliding = false;
    } else if (speed > SLIDE_ON) {
      pen.sliding = true;
    } else if (speed < SLIDE_OFF) {
      pen.sliding = false;
    }
    const want = pen.sliding ? 1 : 0;
    pen.slide += (want - pen.slide) * Math.min(1, dt * (want ? 14 : 7));
    if (pen.windup > 0 && !pen.frozen) {
      pen.yaw = turnTo(pen.yaw, pen.aimYaw, Math.min(1, dt * 18));
    } else if (speed > TURN_SPEED && !held) {
      pen.yaw = turnTo(pen.yaw, Math.atan2(pen.vx, pen.vz), Math.min(1, dt * 12));
    }
    pen.squash *= Math.exp(-SQUASH_FADE * dt);
  }

  // The winner, once it has stopped sliding and bracing, turns to the camera and does the cheer it wears: hops and
  // flapping with nothing worn. The cheer's bursts start as it begins, and each landing puffs snow. It waits for the
  // last knockout's slow motion to end, so it plays at its own speed
  stepCheer(pen, dt) {
    const cheer = this.cheer;
    this.restPose(pen);
    if (cheer.seat !== pen.seat || pen.sliding || pen.bracing || this.finale.t >= 0) {
      return;
    }
    const before = cheer.t;
    cheer.t += dt;
    if (cheer.t < 0) {
      return;
    }
    if (before < 0) {
      this.fx.cheerBurst(pen.looks.cheer, pen.x, pen.z);
    }
    pen.yaw = turnTo(pen.yaw, 0, Math.min(1, dt * 10));
    this.cheerPose(pen, cheer.t);
    if (pen.landed > cheer.hops) {
      cheer.hops = pen.landed;
      this.fx.land(pen.x, pen.z);
    }
  }

  // A penguin that isn't cheering
  restPose(pen) {
    pen.cheering = false;
    pen.hop = 0;
    pen.flip = 0;
    pen.twirl = 0;
    pen.center = 0;
    pen.landed = 0;
  }

  // Poses a penguin `t` seconds into the cheer it wears (`pen.looks.cheer`, or the hops with none), for posePenguin
  // to draw. It depends on `t` alone, so the wardrobe can play a cheer over and over. Says whether the cheer is still
  // going. People who asked for less motion get the hops in place of every other move
  cheerPose(pen, t) {
    this.restPose(pen);
    const look = cheerLook(pen.looks.cheer);
    return MOVES[REDUCED ? "hops" : look.move](pen, t, look);
  }

  // Draws a penguin as its pose fields say. The wardrobe poses its own penguin with this
  posePenguin(pen) {
    const { root, tilt, body, flippers, shield, shieldMat } = pen.parts;
    const t = this.time;
    const squash = pen.squash * 0.28;
    // Shut in ice, a penguin neither moves on its own nor leans into an aim
    const lively = pen.frozen ? 0 : 1;
    const windup = pen.windup * lively;
    const crouch = windup * 0.12;
    const brace = pen.bracing ? 1 : 0;
    const breathe = lively * (1 - pen.slide) * Math.sin(t * 3 + pen.ph) * 0.02;
    const wobble = lively * (1 - pen.slide) * (1 - brace) * Math.sin(t * 2.2 + pen.ph) * 3;
    // A cheering hop stretches the body as it rises
    const stretch = (pen.hop / HOP_HEIGHT) * 0.08;
    root.setPosition(pen.x, ICE_Y + pen.hop, pen.z);
    root.setEulerAngles(0, degrees(pen.yaw + pen.twirl), 0);
    tilt.setLocalPosition(0, 0.32 - pen.slide * 0.05, -pen.center * LYING_MIDDLE);
    tilt.setLocalEulerAngles(pen.slide * 78 - windup * 12 + pen.flip, 0, wobble);
    const wide = 1 + squash + crouch + brace * 0.14;
    body.setLocalScale(wide, 1 - squash - crouch * 1.4 - brace * 0.2 + breathe + stretch, wide);
    const flap = pen.cheering
      ? 40 + 50 * Math.abs(Math.sin(t * 14))
      : lively * Math.pow(Math.max(0, Math.sin(t * 1.7 + pen.ph)), 10) * 28;
    const spread = 12 + pen.slide * 62 + flap + windup * 20 + brace * 70;
    flippers.forEach((flipper, side) => flipper.setLocalEulerAngles(0, 0, (side ? 1 : -1) * spread));
    shield.enabled = pen.bracing;
    if (pen.bracing) {
      const size = 1.25 + Math.sin(t * 30) * 0.04;
      shield.setLocalScale(size, size * 0.92, size);
      shieldMat.opacity = 0.15 + 0.3 * (pen.braceLeft / this.rules.brace_seconds);
      shieldMat.update();
    }
  }

  drawFall(pen, dt) {
    const { root, tilt, flippers } = pen.parts;
    const t = this.time;
    pen.fall += dt;
    pen.x += pen.vx * dt * 0.4;
    pen.z += pen.vz * dt * 0.4;
    if (pen.fall > FALL_SECONDS) {
      root.enabled = false;
      return;
    }
    root.setPosition(pen.x, ICE_Y - pen.fall * pen.fall * 2.2, pen.z);
    tilt.setLocalEulerAngles(30 + pen.fall * 40, 0, Math.sin(t * 30) * 8);
    const spread = 60 + Math.sin(t * 40) * 35;
    flippers.forEach((flipper, side) => flipper.setLocalEulerAngles(0, 0, (side ? 1 : -1) * spread));
  }

  drawSeal(pen, dt) {
    const seal = pen.seal;
    if (seal.state === "off") {
      return;
    }
    const { pitch, roll } = this.stepSeal(seal, pen.ph, dt);
    seal.root.setPosition(seal.x, seal.y, seal.z);
    seal.root.setEulerAngles(0, degrees(seal.yaw), 0);
    seal.pivot.setLocalEulerAngles(-pitch, 0, roll);
  }

  stepSeal(seal, ph, dt) {
    if (seal.state === "swim") {
      return this.swimSeal(seal, ph, dt);
    }
    return seal.state === "dive" ? this.sinkSeal(seal, dt) : this.leapSeal(seal, dt);
  }

  swimSeal(seal, ph, dt) {
    const t = this.time;
    const radius = this.swimRadius();
    seal.ang += (dt * 0.35 * seal.dir * 4) / Math.max(radius, 2);
    seal.x += (Math.cos(seal.ang) * radius - seal.x) * Math.min(1, dt * 2);
    seal.z += (Math.sin(seal.ang) * radius - seal.z) * Math.min(1, dt * 2);
    // One that came up in a hole in the ice goes under it on its way out to the circle
    const level = this.iceOver(seal.x, seal.z) ? SWIM_UNDER : SWIM_Y + Math.sin(t * 2 + ph) * 0.04;
    seal.y += (level - seal.y) * Math.min(1, dt * (level < seal.y ? 12 : 4));
    const heading = Math.atan2(-Math.sin(seal.ang) * seal.dir, Math.cos(seal.ang) * seal.dir);
    seal.yaw = turnTo(seal.yaw, heading, Math.min(1, dt * 6));
    return { pitch: 0, roll: Math.sin(t * 2.4 + ph) * 6 };
  }

  sinkSeal(seal, dt) {
    seal.t += dt;
    const k = Math.min(1, seal.t / DIVE_SECONDS);
    seal.y = SWIM_Y - k * 0.9;
    seal.x += (seal.sx - seal.x) * Math.min(1, dt * 6);
    seal.z += (seal.sz - seal.z) * Math.min(1, dt * 6);
    seal.yaw = turnTo(seal.yaw, Math.atan2(seal.tx - seal.sx, seal.tz - seal.sz), Math.min(1, dt * 10));
    this.fx.bubbles(seal, dt);
    if (k >= 1) {
      Object.assign(seal, { state: "leap", t: 0, x: seal.sx, z: seal.sz });
      this.fx.sound.play("seal");
    }
    return { pitch: 30 * k, roll: 0 };
  }

  leapSeal(seal, dt) {
    seal.t += dt;
    const k = Math.min(1, seal.t / LEAP_SECONDS);
    seal.x = lerp(seal.sx, seal.tx, k);
    seal.z = lerp(seal.sz, seal.tz, k);
    seal.y = lerp(-1.0, -0.05, k) + 1.4 * Math.sin(Math.PI * k);
    if (k >= 1) {
      Object.assign(seal, { state: "swim", ang: Math.atan2(seal.tz, seal.tx) });
    }
    return { pitch: lerp(-45, 50, k), roll: 0 };
  }

  // `still` says the round is decided. The bot stops the ice then, so a cracked tile rests instead of shaking
  drawTiles(dt, still) {
    for (let index = 0; index < this.tiles.length; index += 1) {
      const tile = this.tiles[index];
      if (tile.state === CRACK) {
        tile.t = Math.min(CRACK_SECONDS, tile.t + dt);
        const shake = still ? 0 : (0.02 + tile.t * 0.035) * (REDUCED ? 0.3 : 1);
        tile.root.setLocalPosition(tile.x + rand(-shake, shake), 0, tile.z + rand(-shake, shake));
        this.placeTile(tile, index);
      } else if (tile.state === SINK) {
        tile.t += dt;
        const k = Math.min(1, tile.t / SINK_SECONDS);
        tile.root.setLocalPosition(tile.x, -k * k * 1.6, tile.z);
        tile.root.setLocalEulerAngles(tile.tilt * 25 * k, 0, -tile.tilt * 18 * k);
        this.placeTile(tile, index);
      }
    }
    this.floe.body.flush();
    this.caps.forEach((cap) => cap.flush());
  }

  drawFish(dt) {
    const fish = this.fish;
    if (!fish.active) {
      return;
    }
    if (fish.fall >= 0) {
      fish.fall += dt;
      fish.root.setPosition(fish.x, ICE_Y - fish.fall * fish.fall * 3, fish.z);
      if (fish.fall > 0.8) {
        this.hideFish();
      }
      return;
    }
    const t = this.time;
    fish.root.setPosition(fish.x, ICE_Y + Math.abs(Math.sin(t * 4.5)) * 0.14, fish.z);
    fish.body.setLocalEulerAngles(0, t * 40, Math.sin(t * 9) * 30);
    const size = 0.85 + Math.sin(t * 6) * 0.08;
    fish.glow.setLocalScale(size, 1, size);
  }

  drawCrate(dt) {
    const crate = this.crate;
    if (crate.state === "off") {
      return;
    }
    crate.t += dt;
    crate.squash *= Math.exp(-SQUASH_FADE * dt);
    crate.root.enabled = true;
    if (crate.state === "fall") {
      this.fallCrate(crate);
    } else if (crate.state === "rest") {
      this.restCrate(crate);
    } else {
      this.sinkingCrate(crate, dt);
    }
  }

  // On its way down, turning as it comes, with the mark closing in under it. It falls by the page's own clock, and
  // waits just over the ice if the bot's word that it landed is late. One with no tile left to land on goes on in
  fallCrate(crate) {
    const k = Math.min(1, crate.t / CRATE_FALL_SECONDS);
    if (k === 1 && crate.doomed) {
      this.sinkCrate(CRATE_PLUNGE);
      return;
    }
    // Faster the further it has fallen
    const up = crate.sky * (1 - k * (0.45 + 0.55 * k));
    crate.root.setPosition(crate.x, ICE_Y + up, crate.z - up * CRATE_LEAN);
    crate.root.setEulerAngles(0, up * 30, 0);
    crate.box.setLocalScale(CRATE_SIZE, CRATE_SIZE, CRATE_SIZE);
    if (!crate.doomed) {
      this.drawMark(crate, lerp(MARK_WIDE, 1, k), 0.55 + 0.45 * k);
    }
  }

  // Standing on the ice: squashed by its landing, then hopping and swaying a little
  restCrate(crate) {
    const beat = Math.sin(crate.t * CRATE_BEAT);
    const hop = CRATE_HOP * Math.max(0, beat) ** 2;
    crate.root.setPosition(crate.x, ICE_Y + hop, crate.z);
    crate.root.setEulerAngles(0, Math.sin(crate.t * CRATE_BEAT * 0.5) * 9, 0);
    const wide = CRATE_SIZE * (1 + crate.squash * 0.3 - beat * 0.02);
    crate.box.setLocalScale(wide, CRATE_SIZE * (1 - crate.squash * 0.4 + beat * 0.04), wide);
    this.drawMark(crate, 1, 1);
  }

  // The mark breathes, so it catches the eye on white ice. `wide` is its size against the one at rest
  drawMark({ mark, x, z }, wide, shown) {
    const size = MARK_SIZE * wide * (1 + Math.sin(this.time * 8) * 0.05);
    mark.enabled = true;
    mark.setLocalPosition(x, ICE_Y + MARK_LIFT, z);
    mark.setLocalScale(size, 1, size);
    setShown(mark, shown);
  }

  // Tipping over and going under, with a splash as it meets the water
  sinkingCrate(crate, dt) {
    crate.vy -= CRATE_GRAVITY * dt;
    crate.y += crate.vy * dt;
    if (!crate.wet && crate.y < CRATE_WET) {
      crate.wet = true;
      this.fx.crateSinks(crate);
    }
    if (crate.y < CRATE_SUNK) {
      this.hideCrate();
      return;
    }
    crate.root.setPosition(crate.x, crate.y, crate.z);
    crate.root.setEulerAngles(crate.tip * crate.t * 60, 0, crate.tip * crate.t * 40);
  }

  drawChunks() {
    const t = this.time;
    for (let slot = 0; slot < this.chunks.length; slot += 1) {
      const chunk = this.chunks[slot];
      chunk.root.setLocalPosition(chunk.x, Math.sin(t * 1.1 + chunk.ph) * 0.05 - 0.04, chunk.z);
      chunk.root.setLocalEulerAngles(Math.sin(t * 0.9 + chunk.ph) * 3, chunk.spin + t * 4, 0);
      const place = chunk.root.getWorldTransform();
      this.chunkBodies.place(slot, place);
      this.chunkCaps.place(slot, place);
    }
    this.chunkBodies.flush();
    this.chunkCaps.flush();
  }

  // Keeps the whole floe in view, closing in as it shrinks
  drawCamera(dt) {
    const camera = this.camera;
    const portrait = this.canvas.clientWidth < this.canvas.clientHeight;
    camera.camera.horizontalFov = portrait;
    camera.camera.fov = portrait ? 52 : 40;
    const want = clamp((this.floeRadius + 1.6) / Math.tan((camera.camera.fov * Math.PI) / 360), 7, 30);
    this.camDist += (want - this.camDist) * Math.min(1, dt * 1.5);
    const pitch = (52 * Math.PI) / 180;
    // The last knockout's slow motion brings the camera in toward where the penguin went, and lets it back out after
    const { dist, overX, overZ } = this.finaleView(dt);
    // How many screen pixels one world unit of the ice is drawn across, so effects can keep a size on the screen
    const across = portrait ? this.canvas.clientWidth : this.canvas.clientHeight;
    this.fx.unit = across / (2 * dist * Math.tan((camera.camera.fov * Math.PI) / 360));
    const shake = this.fx.tremor(dt);
    const [x, y, z] = [shake.x + overX, shake.y, shake.z + overZ];
    camera.setPosition(x, Math.sin(pitch) * dist + y, Math.cos(pitch) * dist + 0.3 + z);
    camera.lookAt(x, y, 0.3 + z);
    const wanted = this.floeRadius + 0.2;
    const size = this.shallows.getLocalScale().x;
    const next = size + (wanted - size) * Math.min(1, dt * 3);
    this.shallows.setLocalScale(next, 1, next);
  }

  // How far off the camera is and the spot on the ice it looks toward, with the last knockout's slow motion easing it
  // in and out again. `dt` is real time, so the camera moves at its own speed through the slow motion
  finaleView(dt) {
    const { finale } = this;
    const closing = !REDUCED && finale.t >= 0 && finale.t < FINALE_SLOW_SECONDS;
    finale.zoom += ((closing ? 1 : 0) - finale.zoom) * Math.min(1, dt * FINALE_EASE);
    if (closing) {
      this.aimFinale();
    }
    const zoom = smooth(finale.zoom);
    return {
      dist: this.camDist * (1 - finale.closer * zoom),
      overX: finale.aimX * zoom,
      overZ: finale.aimZ * zoom,
    };
  }

  // Where the last knockout's camera looks and how much closer it comes. With nobody left on the ice that is most of
  // the way over to where the penguin went in. With a winner it keeps both in the picture
  aimFinale() {
    const { finale } = this;
    const winner = this.pens.find((pen) => pen.fall < 0 && pen.parts.root.enabled);
    if (!winner) {
      Object.assign(finale, { aimX: finale.x * FINALE_TOWARD, aimZ: finale.z * FINALE_TOWARD, closer: FINALE_CLOSER });
      return;
    }
    const apart = Math.hypot(winner.x - finale.x, winner.z - finale.z);
    // How far the picture reaches from its middle across the screen's narrow side, before the camera comes closer
    const reach = this.camDist * Math.tan((this.camera.camera.fov * Math.PI) / 360);
    finale.aimX = (winner.x + finale.x) / 2;
    finale.aimZ = (winner.z + finale.z) / 2;
    finale.closer = clamp(1 - (apart / 2 + FINALE_ROOM) / reach, 0, FINALE_CLOSER);
  }

  // A name whose owner the last knockout's camera has left out of the picture, or half out at its edge, goes with it.
  // Pulled inside the screen as names are, it would pile up at the edge with the others left out
  outOfShot(spot) {
    const { clientWidth, clientHeight } = this.canvas;
    const [x, y] = [spot.x - FINALE_EDGE, spot.y - FINALE_EDGE];
    const inside = x > 0 && x < clientWidth - 2 * FINALE_EDGE && y > 0 && y < clientHeight - 2 * FINALE_EDGE;
    return this.finale.zoom > 0.02 && !inside;
  }

  drawTags() {
    const { pens, tagSpots } = this;
    for (const pen of pens) {
      const spot = this.tagSpot(pen);
      tagSpots[pen.seat] = spot && this.outOfShot(spot) ? null : spot;
    }
    tagSpots[pens.length] = this.crateTagSpot();
    this.tags.place(tagSpots, this.frameDt);
  }

  // The screen point the crate's name sits on, over where it stands or will land, or null with no crate to name
  crateTagSpot() {
    const { crate } = this;
    if (crate.state !== "rest" && (crate.state !== "fall" || crate.doomed)) {
      return null;
    }
    const { x, y } = this.screenOf(this.tagPos.set(crate.x, ICE_Y + CRATE_NAME_HEIGHT, crate.z));
    crate.spot.x = x;
    crate.spot.y = y;
    return crate.spot;
  }

  screenOf(point) {
    return this.camera.camera.worldToScreen(point, this.tagScreen);
  }

  // How high on the screen a penguin's hat reaches. Lying on its belly, a hat points the way the penguin slides
  hatTipY({ parts, hatReach }) {
    const head = parts.head.getPosition();
    const reach = (hatReach + NAME_OVER_TIP) * PENGUIN_SCALE;
    const tip = this.tagPos.copy(parts.head.up).mulScalar(reach).add(head);
    return this.screenOf(tip).y;
  }

  // The point in the world that a standing penguin's name sits on, over whatever hat it wears. The wardrobe names its
  // own penguin with this, through its own camera
  namePoint(pen) {
    return this.tagPos.set(pen.x, ICE_Y + pen.hop + (NAME_HEIGHT + pen.nameRise) * PENGUIN_SCALE, pen.z);
  }

  // The screen point a seat's name sits on, or null with nothing of theirs to name. `wait` says the player's own seal
  // can't dive yet
  tagSpot(pen) {
    const seal = pen.seal.state !== "off";
    if (seal) {
      this.tagPos.set(pen.seal.x, pen.seal.y + 0.85 + pen.nameRise, pen.seal.z);
    } else if (pen.parts.root.enabled && pen.fall < 0) {
      const height = NAME_HEIGHT + pen.nameRise * (1 - pen.slide) - pen.slide * 0.62;
      this.tagPos.set(pen.x, ICE_Y + pen.hop + height * PENGUIN_SCALE, pen.z);
    } else {
      return null;
    }
    const { x, y } = this.screenOf(this.tagPos);
    const clear = !seal && pen.looks.hat && pen.slide > STILL_LEANING ? Math.min(y, this.hatTipY(pen)) : y;
    const wait = seal && pen.seat === this.mySeat && (pen.seal.state !== "swim" || this.prediction.sealWait > 0);
    return { x, y: clear, seal, wait };
  }
}

export function createScene(canvas, tagLayer, sound) {
  return new Scene(canvas, tagLayer, sound);
}
