// The picture: every cube of a level in one instanced batch, and the chips that fly off a broken cube.
// A cube is the original's beveled `Pixel 1x1` mesh (0.5 wide, 1.5 tall) scaled to its cells. Cubes are never created
// or freed during play: a broken cube's instance shrinks to nothing, a refill brings it back, and chips come from a
// fixed pool whose paths are worked out from the time each one was thrown.
import * as THREE from "./vendor/three.module.min.js";
import { GLTFLoader } from "./vendor/GLTFLoader.js";
import { PICTURE_HEIGHT } from "./camera.js";
import { BOMB_SIZE, L_PER_UNIT } from "./sim/numbers.js";
import { centerX, centerY } from "./sim/grid.js";

const MODEL = "models/features/pixel_1x1.glb";
const BOMB_MODEL = "models/features/demolish_bomb.glb";
const SUPER_MODEL = "models/pig_super_shooter.glb";
const UNICORN_MODEL = "models/unicorn.glb";
// The mesh's own size: its width and depth, and its height
const MESH_WIDTH = 0.5;
const MESH_HEIGHT = 1.5;
// The biggest picture holds 3,530 cubes (level 1099); features add cubes later, so room is left for them
const CAPACITY = 4096;
// The unit 1x1 box the chips are drawn with, and how many fly at once
const CHIP_POOL = 256;
const CHIPS_PER_BURST = 6;
const CHIP_LIFE = 0.5;
const CHIP_SIZE = 0.28;
const CHIP_GRAVITY = 14;
const CHIP_SPREAD = 1.6;
const CHIP_LIFT = 3.2;
// A broken cube shrinks away this fast, and this many can be shrinking at once
const POP_LIFE = 0.1;
const POP_POOL = 128;
// A hit that doesn't break a cube squashes it for PUNCH_LIFE seconds (at most PUNCH_POOL at once) and throws a few chips
const PUNCH_LIFE = 0.14;
const PUNCH_POOL = 64;
const PUNCH_SQUASH = 0.22;
const PUNCH_SWELL = 0.06;
// Cubes leaping onto the picture at once (a Pixel Pipe refill every 0.07 s, the leap 0.3 s)
const JUMP_POOL = 64;
const HIT_CHIPS = 3;
// A cube that takes several hits stands shorter with every hit, down to this share of its height at no health
const WEAR_LOW = 0.6;

// The Demolish bomb's drop runs in real time, because the game's clock is held for it (DemolishPowerupController.
// <DropBomb>d__26, RVA 0x52DDC08): it grows over the first 0.4 s (ease out) and falls between 0.2 s and 1.0 s (ease in).
// The blast's flash over the cross that follows lasts BOMB_FLASH_MS
export const BOMB_DROP_MS = 1000;
export const BOMB_FLASH_MS = 200;
const BOMB_GROW_MS = 400;
const BOMB_FALL_FROM_MS = 200;
// The bomb's width in cells, and how high it starts, in picture widths
const BOMB_CELLS = 2.4;
const BOMB_START_HEIGHT = 0.7;
const BOMB_FLASH_COLOR = 0xffe6a0;
const BOMB_FLASH_OPACITY = 0.85;

// The Super Shooter's pig and volley run in real time too, because the game's clock is held for all of it
// (SuperShooterPowerupController.<PlayAppearAnimation>d__38, RVA 0x52D26B8: a 0.5 s punch, then a 0.3 s move; then the
// 0.8 s wind-up before the shots, <ShootPixels>, RVA 0x52D4D5C: SUPER_BATCH cubes every SUPER_GAP_MS, each shot flying
// SUPER_SPEED units a second). The pig stands SUPER_STANDOFF units past the picture's lowest row and appears further
// out. The tap that applies the volley lands SUPER_LEAD_MS after the pick
export const SUPER_LEAD_MS = 1600;
const SUPER_PUNCH_MS = 500;
const SUPER_MOVE_MS = 300;
const SUPER_BATCH = 5;
const SUPER_GAP_MS = 30;
const SUPER_SPEED = 30;
const SUPER_EXIT_MS = 200;
const SUPER_PIG_SCALE = 1.3;
const SUPER_STANDOFF = 1.6;
const SUPER_APPEAR_OFFSET = 3;
const SUPER_OVERSHOOT = 1.3;
// The Super Unicorn stands where the Super Shooter's pig does and comes in the same way. Its shots leave
// UNICORN_GAP_MS apart, or closer so the last leaves within UNICORN_SPREAD_MS, and fly UNICORN_SPEED units a second
// (#887 shootInterval 0.06, maxShootDuration 1.5; level3 #1010 speed 60; GetEffectiveShootInterval, RVA 0x515F4BC).
// Its tap lands UNICORN_LEAD_MS after the press, once it stands
export const UNICORN_LEAD_MS = 800;
const UNICORN_GAP_MS = 60;
const UNICORN_SPREAD_MS = 1500;
const UNICORN_SPEED = 60;
const SHOT_POOL = 512;
const SHOT_LENGTH = 0.8;
const SHOT_WIDTH = 0.07;
const SHOT_TARGET_HEIGHT = 0.15;
const SHOT_MUZZLE_HEIGHT = 0.9;
const UNIT_Z = new THREE.Vector3(0, 0, 1);

// The 34 colors' base colors, by id (levels/palette.json, sRGB)
const PALETTE = [
  "#0073ff", "#0e39cc", "#2f2f2f", "#3fac1d", "#ff6200", "#c04983", "#7829e1", "#a00d0d", "#2faacf", "#d2a626",
  "#cccccc", "#613e23", "#046000", "#1d6553", "#bf83e2", "#959d67", "#c37b7c", "#878ec0", "#8d404d", "#c4aa70",
  "#b2544a", "#888795", "#474652", "#39205d", "#aa1d62", "#cf8ab2", "#d2914f", "#6f0f0f", "#7b730a", "#5c8782",
  "#9f6a44", "#7b4827", "#9328a7", "#666476",
]; // prettier-ignore
// The original's cube shader brightens and saturates these (the phone frames show a pink of #ec60c3 where the base is
// #c04983), so each color is lifted the same way
const LIFT_VALUE = 1.25;
const LIFT_SATURATION = 1.08;
export const COLORS = PALETTE.map((hex) => lifted(new THREE.Color(hex)));
// The pale cube of a hidden Surprise Pixel (the one in FeatureImage_SurprisePixel.png)
export const BLANK = new THREE.Color("#d3daf6");
// How much a cube's brightness may differ from its neighbors' (the frames show faint patches)
const JITTER = 0.05;
// A cube's brightness by how high a point is on the mesh: the top is full, the walls below the rounded top edge are
// darker, and the foot is darkest. That puts a dark line around every cube where two meet
const WALL_SHADE = 0.5;
const WALL_TOP = 1.3;
const MESH_TOP = 1.5;
const FOOT_HEIGHT = 0.15;
const FOOT_SHADE = 0.6;

const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

// How tall a cube stands as a share of its full height, given its health now and at the start
// A cube's health when it first stood on the picture: the level file's for its own cubes, 1 for a cube a feature put
// there during play (a Pixel Pipe refill)
export function startHealth(state, target) {
  return target.id < state.level.cubes.length ? state.level.cubes[target.id][5] : 1;
}

export function wornHeight(health, full) {
  if (full <= 1) {
    return 1;
  }
  return WEAR_LOW + (1 - WEAR_LOW) * (Math.max(0, health) / full);
}

function lifted(color) {
  const hsl = { h: 0, s: 0, l: 0 };
  color.getHSL(hsl, THREE.SRGBColorSpace);
  const hsv = { v: hsl.l + hsl.s * Math.min(hsl.l, 1 - hsl.l) };
  hsv.s = hsv.v === 0 ? 0 : 2 * (1 - hsl.l / hsv.v);
  const v = Math.min(1, hsv.v * LIFT_VALUE);
  const s = Math.min(1, hsv.s * LIFT_SATURATION);
  const l = v * (1 - s / 2);
  const sl = l === 0 || l === 1 ? 0 : (v - l) / Math.min(l, 1 - l);
  return color.setHSL(hsl.h, sl, l, THREE.SRGBColorSpace);
}

// The cube's mesh with its light baked in
function shadedGeometry(source) {
  const geometry = source.clone();
  const position = geometry.getAttribute("position");
  const shades = new Float32Array(position.count * 3);
  for (let i = 0; i < position.count; i++) {
    const up = THREE.MathUtils.smoothstep(position.getY(i), WALL_TOP, MESH_TOP);
    let shade = WALL_SHADE + (1 - WALL_SHADE) * up;
    if (position.getY(i) < FOOT_HEIGHT) {
      shade *= FOOT_SHADE;
    }
    shades.fill(shade, i * 3, i * 3 + 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(shades, 3));
  return geometry;
}

// Cubes carry their light in the vertices, so no light or tone curve changes their colors
function cubeMaterial() {
  return new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false });
}

function chipMaterial() {
  return new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0 });
}

// A cube's color with its own small brightness change, the same every time for the same cube
function jittered(color, id) {
  const hash = Math.imul(id + 1, 2654435761) >>> 0;
  return color.clone().multiplyScalar(1 + (hash / 2 ** 32 - 0.5) * 2 * JITTER);
}

// The bounding cells of a target as [x0, y0, x1, y1] (a cube covers a rectangle of cells)
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

// Loads the cube mesh and makes the batches. `group` is where they are added; `rig` is the camera rig (for boxes)
export async function createPicture(group, rig) {
  const gltf = await new GLTFLoader().loadAsync(MODEL);
  let source = null;
  gltf.scene.traverse((node) => {
    if (node.isMesh && !source) {
      source = node;
    }
  });
  const bombGltf = await new GLTFLoader().loadAsync(BOMB_MODEL);
  const superGltf = await new GLTFLoader().loadAsync(SUPER_MODEL);
  const unicornGltf = await new GLTFLoader().loadAsync(UNICORN_MODEL);
  const cubes = new THREE.InstancedMesh(shadedGeometry(source.geometry), cubeMaterial(), CAPACITY);
  cubes.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  cubes.frustumCulled = false;
  cubes.count = 0;
  const chips = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), chipMaterial(), CHIP_POOL);
  chips.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  chips.frustumCulled = false;
  chips.count = 0;
  group.add(cubes, chips);

  const flat = new THREE.Matrix4();
  const spin = new THREE.Quaternion();
  const unit = new THREE.Vector3();
  const here = new THREE.Vector3();
  const grown = new THREE.Vector3();
  // The level on screen: its grid and the cube size in units, and the cube height
  const current = { grid: null, size: 0, height: 0 };
  // Chips in flight: where each started, how fast it left, when, and how big it is. `last` is the latest drawn time
  const flying = Array.from({ length: CHIP_POOL }, () => ({
    born: -Infinity,
    p: new THREE.Vector3(),
    v: new THREE.Vector3(),
    size: 0,
  }));
  const clock = {
    last: 0,
    next: 0,
    any: false,
    nextPop: 0,
    anyPop: false,
    nextPunch: 0,
    anyPunch: false,
    nextJump: 0,
    anyJump: false,
  };
  // Cubes shrinking away: which cube, when it broke, and where it stood and how big it was
  const shrinking = Array.from({ length: POP_POOL }, () => ({
    id: -1,
    born: -Infinity,
    p: new THREE.Vector3(),
    s: new THREE.Vector3(),
  }));

  // A cell's center on the ground, in world units
  function cellCenter(x, y) {
    return new THREE.Vector3(centerX(current.grid, x) / L_PER_UNIT, 0, -centerY(current.grid, y) / L_PER_UNIT);
  }

  // Stand the target's cube on its cells, in this color (-1 leaves it as it was), `tall` of its full height
  function place(target, color, tall = 1) {
    const [x0, y0, x1, y1] = cellRange(current.grid.width, target);
    const a = cellCenter(x0, y0);
    const b = cellCenter(x1, y1);
    const across = ((x1 - x0 + 1) * current.size) / MESH_WIDTH;
    const down = ((y1 - y0 + 1) * current.size) / MESH_WIDTH;
    flat.compose(
      here.set((a.x + b.x) / 2, 0, (a.z + b.z) / 2),
      spin.identity(),
      grown.set(across, (current.height * tall) / MESH_HEIGHT, down),
    );
    cubes.setMatrixAt(target.id, flat);
    if (color >= 0) {
      cubes.setColorAt(target.id, jittered(COLORS[color], target.id));
    }
    cubes.count = Math.max(cubes.count, target.id + 1);
    cubes.instanceMatrix.needsUpdate = true;
    if (cubes.instanceColor) {
      cubes.instanceColor.needsUpdate = true;
    }
  }

  // Put this level's cubes up. Instance n is target n, so the simulation's ids find their cube
  function build(state) {
    current.grid = state.grid;
    current.size = state.grid.size / L_PER_UNIT;
    current.height = Math.min(current.size, PICTURE_HEIGHT);
    // Instances past this level's targets may still hold the last level's cubes (refills add targets during play)
    for (let i = 0; i < Math.max(cubes.count, state.grid.targets.length); i++) {
      cubes.setMatrixAt(i, HIDDEN);
    }
    cubes.count = 0;
    for (const target of state.grid.targets) {
      if (target.owner === 0 && target.cells.length > 0) {
        place(target, target.color, wornHeight(target.health, startHealth(state, target)));
      }
    }
    cubes.count = state.grid.targets.length;
    chips.count = 0;
    clock.any = false;
    clock.anyPop = false;
    clock.anyPunch = false;
    clock.anyJump = false;
    for (const punch of punching) {
      punch.born = -Infinity;
    }
    for (const jump of jumping) {
      jump.born = -Infinity;
    }
    drop.live = false;
    flash.live = false;
    bomb.visible = false;
    stopSuper();
    bands.forEach((band) => (band.visible = false));
    for (const chip of flying) {
      chip.born = -Infinity;
    }
    for (const pop of shrinking) {
      pop.born = -Infinity;
    }
  }

  // Cubes squashing from a hit: which cube, when, and the matrix parts it goes back to
  const punching = Array.from({ length: PUNCH_POOL }, () => ({
    id: -1,
    born: -Infinity,
    p: new THREE.Vector3(),
    s: new THREE.Vector3(),
  }));

  // Cubes leaping in: which cube, when, from where (a world point), how long and how high the leap is, and the matrix
  // parts it lands on
  const jumping = Array.from({ length: JUMP_POOL }, () => ({
    id: -1,
    born: -Infinity,
    life: 0,
    height: 0,
    from: new THREE.Vector3(),
    p: new THREE.Vector3(),
    s: new THREE.Vector3(),
  }));

  // Put a squashing cube back to its normal shape at once. A cube still leaping in stops where it was last drawn
  function settle(id) {
    for (const jump of jumping) {
      if (jump.id === id) {
        jump.born = -Infinity;
      }
    }
    for (const punch of punching) {
      if (punch.id === id && punch.born !== -Infinity) {
        flat.compose(punch.p, spin.identity(), punch.s);
        cubes.setMatrixAt(id, flat);
        cubes.instanceMatrix.needsUpdate = true;
        punch.born = -Infinity;
      }
    }
  }

  // A hit that leaves the cube standing: it stands as tall as its health says, squashes briefly and throws a few
  // chips. `full` is its health at the start, `health` what is left, `cell` where it was hit (-1 for no cell)
  function hitCube(target, full, health, cell, seconds) {
    settle(target.id);
    place(target, -1, wornHeight(health, full));
    const punch = punching[clock.nextPunch];
    clock.nextPunch = (clock.nextPunch + 1) % PUNCH_POOL;
    cubes.getMatrixAt(target.id, flat);
    flat.decompose(punch.p, spin, punch.s);
    punch.id = target.id;
    punch.born = seconds;
    clock.anyPunch = true;
    burst(cell >= 0 ? cell : target.cells[0], target.color, seconds, HIT_CHIPS);
  }

  // Squash every punched cube to where it is at this time, and put the finished ones back
  function squash(seconds) {
    let alive = false;
    for (const punch of punching) {
      if (punch.born === -Infinity) {
        continue;
      }
      const age = seconds - punch.born;
      if (age < 0) {
        alive = true;
        continue;
      }
      if (age >= PUNCH_LIFE) {
        flat.compose(punch.p, spin.identity(), punch.s);
        punch.born = -Infinity;
      } else {
        const k = Math.sin(Math.PI * (age / PUNCH_LIFE));
        grown.set(punch.s.x * (1 + PUNCH_SWELL * k), punch.s.y * (1 - PUNCH_SQUASH * k), punch.s.z * (1 + PUNCH_SWELL * k));
        flat.compose(punch.p, spin.identity(), grown);
        alive = true;
      }
      cubes.setMatrixAt(punch.id, flat);
    }
    cubes.instanceMatrix.needsUpdate = true;
    clock.anyPunch = alive;
  }

  // A broken cube: its instance shrinks to nothing at once
  function hideCube(target) {
    settle(target.id);
    cubes.setMatrixAt(target.id, HIDDEN);
    cubes.instanceMatrix.needsUpdate = true;
  }

  // Paint a standing cube this color (a THREE.Color) with its own small brightness change, leaving its shape alone
  function recolor(target, color) {
    cubes.setColorAt(target.id, jittered(color, target.id));
    if (cubes.instanceColor) {
      cubes.instanceColor.needsUpdate = true;
    }
  }

  // The cube's top height now as the drawing stands it, in world units
  function topOf(target, state) {
    return current.height * wornHeight(target.health, startHealth(state, target));
  }

  // A cube comes back (a Pixel Pipe refill) on the target's cells in this color
  function showCube(target, color) {
    settle(target.id);
    for (const pop of shrinking) {
      if (pop.id === target.id) {
        pop.born = -Infinity;
      }
    }
    place(target, color);
  }

  // A cube a feature has just put on its cell (it is there at once for the rules) leaps there from `from`, a world
  // point, starting at `seconds` (the page's clock) for `life` seconds, `height` units over the straight line at the
  // middle (the original's DOLocalJump)
  function jumpCube(target, color, from, seconds, life, height) {
    settle(target.id);
    place(target, color);
    const jump = jumping[clock.nextJump];
    clock.nextJump = (clock.nextJump + 1) % JUMP_POOL;
    cubes.getMatrixAt(target.id, flat);
    flat.decompose(jump.p, spin, jump.s);
    jump.id = target.id;
    jump.born = seconds;
    jump.life = life;
    jump.height = height;
    jump.from.copy(from);
    clock.anyJump = true;
    leap(clock.last);
  }

  // Move every leaping cube to where it is at this time; one not yet started waits at its start
  function leap(seconds) {
    let alive = false;
    for (const jump of jumping) {
      if (jump.born === -Infinity) {
        continue;
      }
      const u = Math.min(1, Math.max(0, (seconds - jump.born) / jump.life));
      if (u >= 1) {
        flat.compose(jump.p, spin.identity(), jump.s);
        jump.born = -Infinity;
      } else {
        here.lerpVectors(jump.from, jump.p, u);
        here.y += 4 * jump.height * u * (1 - u);
        flat.compose(here, spin.identity(), jump.s);
        alive = true;
      }
      cubes.setMatrixAt(jump.id, flat);
    }
    cubes.instanceMatrix.needsUpdate = true;
    clock.anyJump = alive;
  }

  // A cube breaks at this time (the page's clock, in seconds): it shrinks away over POP_LIFE and throws chips
  function breakCube(target, color, seconds) {
    settle(target.id);
    const pop = shrinking[clock.nextPop];
    clock.nextPop = (clock.nextPop + 1) % POP_POOL;
    cubes.getMatrixAt(target.id, flat);
    flat.decompose(pop.p, spin, pop.s);
    pop.id = target.id;
    pop.born = seconds;
    clock.anyPop = true;
    burstAt(here.copy(pop.p).setY(current.height / 2), color, seconds);
  }

  // Shrink every breaking cube to where it is at this time, and hide the ones that are done
  function shrink(seconds) {
    let alive = false;
    for (const pop of shrinking) {
      const age = seconds - pop.born;
      if (age < 0 || pop.born === -Infinity) {
        alive = alive || pop.born !== -Infinity;
        continue;
      }
      if (age >= POP_LIFE) {
        cubes.setMatrixAt(pop.id, HIDDEN);
        pop.born = -Infinity;
      } else {
        const left = 1 - age / POP_LIFE;
        flat.compose(pop.p, spin.identity(), grown.copy(pop.s).multiplyScalar(left * left));
        cubes.setMatrixAt(pop.id, flat);
        alive = true;
      }
    }
    cubes.instanceMatrix.needsUpdate = true;
    clock.anyPop = alive;
  }

  // The box a cell takes on screen, in pixels from the column's top left corner: the top face of its cube
  function cellBox(x, y) {
    const half = current.size / 2;
    const middle = cellCenter(x, y);
    const corners = [
      [-1, -1],
      [1, -1],
      [-1, 1],
      [1, 1],
    ].map(([sx, sz]) => new THREE.Vector3(middle.x + sx * half, current.height, middle.z + sz * half));
    return rig.boxAround(corners);
  }

  // The bomb: the model stands on a holder (its foot on the holder's origin, its width worked out once) that grows and
  // falls
  const bomb = new THREE.Group();
  const bombBody = bombGltf.scene;
  const bombBox = new THREE.Box3().setFromObject(bombBody);
  const bombSize = bombBox.getSize(new THREE.Vector3());
  const bombMiddle = bombBox.getCenter(new THREE.Vector3());
  bombBody.position.set(-bombMiddle.x, -bombBox.min.y, -bombMiddle.z);
  bomb.add(bombBody);
  bomb.visible = false;
  group.add(bomb);
  const drop = { live: false, t0: 0, x: 0, y: 0 };
  // The flash over the cross: a flat band over the rows and one over the columns
  const flashMaterial = new THREE.MeshBasicMaterial({
    color: BOMB_FLASH_COLOR,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    toneMapped: false,
  });
  const bands = [0, 1].map(() => new THREE.Mesh(new THREE.PlaneGeometry(1, 1), flashMaterial));
  for (const band of bands) {
    band.rotation.x = -Math.PI / 2;
    band.renderOrder = 3;
    band.visible = false;
    band.frustumCulled = false;
    group.add(band);
  }
  const flash = { live: false, t0: 0 };

  // The Super Shooter's pig (its foot on the holder's origin, facing the picture) and the pool of shots in flight.
  // `sup.pig`: the pig stands (`t0` is when it was picked); `sup.volley`: the shots fly (`vt0` is when the tap landed,
  // `base` the page's clock then, `end` when the clock lets go, `plan` each shot's start and landing in ms)
  const superPig = new THREE.Group();
  const superBody = superGltf.scene;
  const superBox = new THREE.Box3().setFromObject(superBody);
  const superMiddle = superBox.getCenter(new THREE.Vector3());
  superBody.position.set(-superMiddle.x, -superBox.min.y, -superMiddle.z);
  superPig.add(superBody);
  const unicornBody = unicornGltf.scene;
  const unicornBox = new THREE.Box3().setFromObject(unicornBody);
  const unicornMiddle = unicornBox.getCenter(new THREE.Vector3());
  unicornBody.position.set(-unicornMiddle.x, -unicornBox.min.y, -unicornMiddle.z);
  unicornBody.visible = false;
  superPig.add(unicornBody);
  superPig.rotation.y = Math.PI;
  superPig.visible = false;
  group.add(superPig);
  const shots = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }),
    SHOT_POOL,
  );
  shots.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  shots.frustumCulled = false;
  shots.renderOrder = 4;
  shots.count = 0;
  group.add(shots);
  const sup = { pig: false, t0: 0, volley: false, vt0: 0, base: 0, end: 0, plan: null, popped: 0 };
  const aimAt = new THREE.Vector3();
  const middle = new THREE.Vector3();
  const heading = new THREE.Quaternion();
  const barSize = new THREE.Vector3();

  // The cell under a press at these pixels (from the column's top left), as [x, y], or null off the picture
  function cellAt(px, py) {
    if (!current.grid) {
      return null;
    }
    const ndc = new THREE.Vector2((px / rig.width) * 2 - 1, 1 - (py / rig.height) * 2);
    const caster = new THREE.Raycaster();
    caster.setFromCamera(ndc, rig.camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -current.height);
    const spot = caster.ray.intersectPlane(plane, new THREE.Vector3());
    if (!spot) {
      return null;
    }
    const x = Math.floor(spot.x / current.size + current.grid.width / 2);
    const y = Math.floor(-spot.z / current.size + current.grid.height / 2);
    if (x < 0 || y < 0 || x >= current.grid.width || y >= current.grid.height) {
      return null;
    }
    return [x, y];
  }

  // The bomb starts falling onto cell (x, y) now
  function dropBomb(x, y) {
    drop.live = true;
    drop.t0 = performance.now();
    drop.x = x;
    drop.y = y;
    bomb.visible = true;
    animate();
  }

  // The cross through cell (x, y) flashes now
  function flashCross(x, y) {
    const grid = current.grid;
    const half = (BOMB_SIZE > 0 ? BOMB_SIZE - 1 : BOMB_SIZE) >> 1;
    const rows = [Math.max(0, y - half), Math.min(grid.height - 1, y + half)];
    const columns = [Math.max(0, x - half), Math.min(grid.width - 1, x + half)];
    const lowRow = cellCenter(0, rows[0]);
    const highRow = cellCenter(0, rows[1]);
    const lowColumn = cellCenter(columns[0], 0);
    const highColumn = cellCenter(columns[1], 0);
    const lift = current.height + 0.03;
    bands[0].position.set(0, lift, (lowRow.z + highRow.z) / 2);
    bands[0].scale.set(grid.width * current.size, (rows[1] - rows[0] + 1) * current.size, 1);
    bands[1].position.set((lowColumn.x + highColumn.x) / 2, lift, 0);
    bands[1].scale.set((columns[1] - columns[0] + 1) * current.size, grid.height * current.size, 1);
    bands[0].visible = true;
    bands[1].visible = true;
    flash.live = true;
    flash.t0 = performance.now();
    animate();
  }

  // Where the Super Shooter's pig stands to shoot: in the middle, past the picture's lowest row
  function superSpot() {
    return new THREE.Vector3(0, 0, (current.grid.height * current.size) / 2 + SUPER_STANDOFF);
  }

  // The Super Shooter's pig appears for a pick made now (`instant`: already standing, for a friend's view). `unicorn`:
  // the Super Unicorn comes instead
  function showSuper(instant = false, unicorn = false) {
    superBody.visible = !unicorn;
    unicornBody.visible = unicorn;
    sup.pig = true;
    sup.t0 = performance.now() - (instant ? SUPER_PUNCH_MS + SUPER_MOVE_MS : 0);
    superPig.visible = true;
    animate();
  }

  function superShown() {
    return sup.pig;
  }

  // The volley at these cubes (target ids, in shooting order): when each shot leaves and lands, in ms after the tap,
  // and where it lands. SUPER_BATCH cubes leave every SUPER_GAP_MS. `ms` is how long the clock stays held
  function planVolley(ids) {
    const from = superSpot().setY(SHOT_MUZZLE_HEIGHT);
    const planned = ids.map((id, index) => {
      cubes.getMatrixAt(id, flat);
      const to = new THREE.Vector3().setFromMatrixPosition(flat).setY(SHOT_TARGET_HEIGHT);
      const start = Math.floor(index / SUPER_BATCH) * SUPER_GAP_MS;
      return { id, start, land: start + (from.distanceTo(to) / SUPER_SPEED) * 1000, to, color: -1, kills: false, done: false };
    });
    const last = planned.reduce((most, shot) => Math.max(most, shot.land), 0);
    return { from, shots: planned, ms: last + CHIP_LIFE * 1000 + SUPER_EXIT_MS };
  }

  // How long a volley at these cubes holds the clock, in ms after its tap lands
  function volleyMs(ids) {
    return planVolley(ids).ms;
  }

  // The Super Unicorn's run from its unicorn_shot events, in shooting order: one shot leaves each gap, at the shot's
  // cell. A shot at a Pixel Pipe's queue (no target) throws chips off the pipe where it lands
  function planUnicorn(events) {
    const from = superSpot().setY(SHOT_MUZZLE_HEIGHT);
    const gap = Math.min(UNICORN_GAP_MS, UNICORN_SPREAD_MS / Math.max(1, events.length));
    const width = current.grid.width;
    const planned = events.map((event, index) => {
      const to = cellCenter(event.cell % width, Math.floor(event.cell / width)).setY(SHOT_TARGET_HEIGHT);
      const start = index * gap;
      const land = start + (from.distanceTo(to) / UNICORN_SPEED) * 1000;
      const pop = event.target < 0;
      return { id: event.target, start, land, to, color: event.color, kills: false, done: false, pop, cell: event.cell };
    });
    const last = planned.reduce((most, shot) => Math.max(most, shot.land), 0);
    return { from, shots: planned, ms: last + CHIP_LIFE * 1000 + SUPER_EXIT_MS };
  }

  // How long the Super Unicorn's run holds the clock, in ms after its tap lands
  function unicornMs(events) {
    return planUnicorn(events).ms;
  }

  // The Unicorn's tap landed: it shoots now (`events` its unicorn_shot events)
  function startUnicorn(events) {
    startPlan(planUnicorn(events), true);
  }

  // The tap landed: the pig shoots these cubes now
  function startVolley(ids) {
    startPlan(planVolley(ids), false);
  }

  function startPlan(plan, unicorn) {
    sup.plan = plan;
    sup.volley = true;
    sup.vt0 = performance.now();
    sup.base = clock.last;
    sup.end = sup.vt0 + sup.plan.ms;
    sup.popped = 0;
    if (!sup.pig) {
      showSuper(true, unicorn);
    }
    animate();
  }

  // A cube the volley killed pops when its shot lands, not when the tap does. False for a cube it isn't shooting
  function volleyKills(id, color) {
    // A cube that takes several shots breaks with the last one at it
    const shot = sup.plan && sup.plan.shots.findLast((entry) => entry.id === id);
    if (!shot) {
      return false;
    }
    shot.color = color;
    shot.kills = true;
    return true;
  }

  // How many cubes the volley popped since the last call (for their sound)
  function takePopped() {
    const count = sup.popped;
    sup.popped = 0;
    return count;
  }

  function stopSuper() {
    sup.pig = false;
    sup.volley = false;
    sup.plan = null;
    superPig.visible = false;
    shots.count = 0;
  }

  // True while the pig stands or the shots fly
  function supering() {
    return sup.pig || sup.volley;
  }

  // Pop the cubes whose shots have landed by `elapsed` ms
  function runVolley(elapsed, seconds) {
    for (const shot of sup.plan.shots) {
      if (shot.done || elapsed < shot.land) {
        continue;
      }
      shot.done = true;
      if (shot.pop) {
        burst(shot.cell, shot.color, seconds);
        sup.popped += 1;
      }
      if (shot.kills) {
        breakCube(current.grid.targets[shot.id], shot.color, seconds);
        sup.popped += 1;
      }
    }
  }

  // Draw the shots in flight at `elapsed` ms
  function drawShots(elapsed) {
    let count = 0;
    for (const shot of sup.plan.shots) {
      if (elapsed < shot.start || elapsed >= shot.land || count >= SHOT_POOL) {
        continue;
      }
      const f = (elapsed - shot.start) / Math.max(1, shot.land - shot.start);
      aimAt.copy(shot.to).sub(sup.plan.from);
      const distance = aimAt.length();
      aimAt.normalize();
      const head = f * distance;
      const back = Math.max(0, head - SHOT_LENGTH);
      middle.copy(sup.plan.from).addScaledVector(aimAt, (head + back) / 2);
      heading.setFromUnitVectors(UNIT_Z, aimAt);
      flat.compose(middle, heading, barSize.set(SHOT_WIDTH, SHOT_WIDTH, Math.max(head - back, 0.05)));
      shots.setMatrixAt(count, flat);
      count += 1;
    }
    shots.count = count;
    shots.instanceMatrix.needsUpdate = true;
  }

  // The pig punches in, moves to its spot, stands, and shrinks away as the volley ends
  function animateSuper(now) {
    const spot = superSpot();
    const age = now - sup.t0;
    let scale = 1;
    let at = spot;
    if (age < SUPER_PUNCH_MS + SUPER_MOVE_MS) {
      const appear = spot.clone();
      appear.z += SUPER_APPEAR_OFFSET;
      if (age < SUPER_PUNCH_MS) {
        const u = Math.max(0, age) / SUPER_PUNCH_MS;
        scale = u < 0.6 ? (u / 0.6) * SUPER_OVERSHOOT : SUPER_OVERSHOOT - ((u - 0.6) / 0.4) * (SUPER_OVERSHOOT - 1);
        at = appear;
      } else {
        const u = (age - SUPER_PUNCH_MS) / SUPER_MOVE_MS;
        at = appear.lerp(spot, u * u * (3 - 2 * u));
      }
    }
    if (sup.volley && now > sup.end - SUPER_EXIT_MS) {
      scale *= Math.max(0, 1 - (now - (sup.end - SUPER_EXIT_MS)) / SUPER_EXIT_MS);
    }
    superPig.position.copy(at);
    superPig.scale.setScalar(Math.max(scale * SUPER_PIG_SCALE, 1e-4));
  }

  // True while the bomb falls or the flash shows
  function bombing() {
    return drop.live || flash.live;
  }

  // Move the bomb and the flash to where they are now (real time)
  function animate() {
    const now = performance.now();
    if (drop.live) {
      const age = now - drop.t0;
      if (age >= BOMB_DROP_MS) {
        drop.live = false;
        bomb.visible = false;
      } else {
        const grow = Math.min(1, age / BOMB_GROW_MS);
        const fall = Math.min(1, Math.max(0, (age - BOMB_FALL_FROM_MS) / (BOMB_DROP_MS - BOMB_FALL_FROM_MS)));
        const width = Math.max(bombSize.x, 1e-6);
        const scale = ((BOMB_CELLS * current.size) / width) * (1 - (1 - grow) * (1 - grow));
        const start = Math.max(current.grid.width, current.grid.height) * current.size * BOMB_START_HEIGHT + 4;
        const spot = cellCenter(drop.x, drop.y);
        bomb.position.set(spot.x, current.height + (start - current.height) * (1 - fall * fall), spot.z);
        bomb.scale.setScalar(Math.max(scale, 1e-4));
      }
    }
    if (sup.pig) {
      animateSuper(now);
    }
    if (sup.volley) {
      if (now >= sup.end) {
        stopSuper();
      } else {
        drawShots(now - sup.vt0);
      }
    }
    if (flash.live) {
      const left = 1 - (now - flash.t0) / BOMB_FLASH_MS;
      if (left <= 0) {
        flash.live = false;
        bands.forEach((band) => (band.visible = false));
      } else {
        flashMaterial.opacity = BOMB_FLASH_OPACITY * left * left;
      }
    }
  }

  // Throw chips off the cell in this color. `seconds` is the page's clock; left out, it is the last drawn time
  function burst(cell, color, seconds = clock.last, count = CHIPS_PER_BURST) {
    const width = current.grid.width;
    const middle = cellCenter(cell % width, Math.floor(cell / width));
    burstAt(middle.setY(current.height / 2), color, seconds, count);
  }

  // Throw chips off a world point
  function burstAt(middle, color, seconds, count = CHIPS_PER_BURST) {
    for (let i = 0; i < count; i++) {
      const slot = clock.next;
      const chip = flying[slot];
      clock.next = (slot + 1) % CHIP_POOL;
      chip.born = seconds;
      chip.p.copy(middle);
      chip.v.set(
        (Math.random() - 0.5) * CHIP_SPREAD,
        CHIP_LIFT * (0.6 + Math.random() * 0.6),
        (Math.random() - 0.5) * CHIP_SPREAD,
      );
      chip.size = current.size * CHIP_SIZE * (0.7 + Math.random() * 0.6);
      chips.setColorAt(slot, COLORS[color]);
    }
    if (chips.instanceColor) {
      chips.instanceColor.needsUpdate = true;
    }
    clock.any = true;
    chips.count = CHIP_POOL;
  }

  // Move every chip to where it is at this time, and report whether any is still in the air
  function frame(page) {
    // A volley runs the clock itself while the game's is held
    let seconds = page;
    if (sup.volley) {
      const elapsed = performance.now() - sup.vt0;
      seconds = sup.base + elapsed / 1000;
      runVolley(elapsed, seconds);
    }
    clock.last = seconds;
    if (clock.anyPunch) {
      squash(seconds);
    }
    if (clock.anyPop) {
      shrink(seconds);
    }
    if (clock.anyJump) {
      leap(seconds);
    }
    if (!clock.any) {
      return false;
    }
    let alive = false;
    flying.forEach((chip, i) => {
      const age = seconds - chip.born;
      if (age < 0 || age > CHIP_LIFE) {
        chips.setMatrixAt(i, HIDDEN);
        return;
      }
      alive = true;
      here.set(
        chip.p.x + chip.v.x * age,
        chip.p.y + chip.v.y * age - 0.5 * CHIP_GRAVITY * age * age,
        chip.p.z + chip.v.z * age,
      );
      const shrink = chip.size * (1 - age / CHIP_LIFE);
      spin.setFromAxisAngle(unit.set(1, 1, 0).normalize(), age * 9);
      flat.compose(here, spin, grown.set(shrink, shrink, shrink));
      chips.setMatrixAt(i, flat);
    });
    chips.instanceMatrix.needsUpdate = true;
    if (!alive) {
      clock.any = false;
      chips.count = 0;
    }
    return alive;
  }

  return {
    cubes,
    chips,
    build,
    hideCube,
    recolor,
    topOf,
    showCube,
    jumpCube,
    breakCube,
    hitCube,
    cellBox,
    burst,
    frame,
    cellAt,
    dropBomb,
    flashCross,
    bombing,
    showSuper,
    superShown,
    volleyMs,
    startVolley,
    unicornMs,
    startUnicorn,
    volleyKills,
    takePopped,
    stopSuper,
    supering,
    animate,
  };
}
