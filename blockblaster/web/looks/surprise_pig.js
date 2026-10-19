// Feature 1, the Surprise Pig: while hidden a pig stands purple with a "?" where its number goes and the question
// face; when it is revealed it flashes white into its own color, pops up in size and throws a few sparkles.
// The meshes are pig.glb's: models/pig_surprise.glb is the same pig in purple with a floating "?", which only the New
// Feature popup shows, so the page tints the pig it already has. The hidden list comes from the simulation
// (sim/features/surprise_pig.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { COLORS } from "../picture.js";
import { NUMBER } from "../sim/features/surprise_pig.js";
import { play as sound } from "../sound.js";

export { NUMBER };

// The Surprise material of models/pig_surprise.glb
const HIDDEN_COLOR = new THREE.Color("#7b5fd6");
const WHITE = new THREE.Color(0xffffff);
const FACE_QUESTION = 4;
const SPARKLE_PICTURE = "art/effects/fx_star_white.png";

// The reveal: a white flash fading into the pig's color, and a pop of size that peaks at the middle
const POP_TICKS = 15;
const POP_GROWTH = 0.3;
// Each reveal throws this many sparkles; this many fit on screen at once
const SPARKLES = 5;
const SPARKLE_CAPACITY = 128;
const SPARKLE_TICKS = 24;
const SPARKLE_RISE = 0.9;
const SPARKLE_REACH = 1.1;
const SPARKLE_SIZE = 0.5;
// Sparkles fly out at golden-angle steps, a little different for every pig
const GOLDEN = 2.399963;

const matrix = new THREE.Matrix4();
const place = new THREE.Vector3();
const turn = new THREE.Quaternion();
const size = new THREE.Vector3();
const tint = new THREE.Color();
const glow = new THREE.Color();
const UP = new THREE.Vector3(0, 1, 0);

class SurpriseLook {
  constructor(mesh) {
    this.mesh = mesh;
    this.now = 0;
    this.hidden = [];
    // Per pig id: {t0, x, y, z, s} for a pig revealed lately; x stays null until the pig has been drawn once
    this.pops = new Map();
  }

  // A new level: nothing is popping
  build(state) {
    this.clear();
    this.begin(state);
    this.now = state.tick;
  }

  clear() {
    this.pops.clear();
    this.mesh.count = 0;
  }

  begin(state) {
    const mine = state.features[NUMBER];
    this.hidden = mine ? mine.hidden : [];
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "pig_revealed") {
        sound("reveal");
        this.pops.set(event.pig, { t0: event.t, x: null, y: 0, z: 0, s: 1 });
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
  }

  // Dress one pig for drawing: `pose` comes in with its place and goes out with the look (`tint`, `text`, `face`,
  // `scale`)
  shape(id, pig, pose) {
    if (!pose.shown) {
      return;
    }
    if (this.hidden.includes(id)) {
      pose.tint = HIDDEN_COLOR;
      pose.text = "?";
      pose.fade = 1;
      pose.face = FACE_QUESTION;
      return;
    }
    const pop = this.pops.get(id);
    if (!pop) {
      return;
    }
    if (pop.x === null) {
      Object.assign(pop, { x: pose.x, y: pose.y, z: pose.z, s: pose.scale });
    }
    const u = Math.min(1, Math.max(0, (this.now - pop.t0) / POP_TICKS));
    pose.scale *= 1 + POP_GROWTH * Math.sin(Math.PI * u);
    pose.tint = tint.copy(WHITE).lerp(COLORS[pig.color], u);
  }

  // Draw the sparkles of every recent reveal, once all pigs are placed
  end() {
    let count = 0;
    for (const [id, pop] of this.pops) {
      const age = this.now - pop.t0;
      if (age >= SPARKLE_TICKS) {
        this.pops.delete(id);
        continue;
      }
      if (pop.x === null || age < 0 || count + SPARKLES > SPARKLE_CAPACITY) {
        continue;
      }
      count += this.writeSparkles(count, id, pop, age / SPARKLE_TICKS);
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) {
      this.mesh.instanceColor.needsUpdate = true;
    }
  }

  writeSparkles(first, id, pop, u) {
    for (let k = 0; k < SPARKLES; k++) {
      const angle = (id + k) * GOLDEN;
      const reach = SPARKLE_REACH * pop.s * Math.sqrt(u);
      place.set(
        pop.x + Math.cos(angle) * reach,
        pop.y + pop.s * SPARKLE_RISE + u * 0.4,
        pop.z + Math.sin(angle) * reach,
      );
      turn.setFromAxisAngle(UP, angle + u * 2);
      matrix.compose(place, turn, size.setScalar(SPARKLE_SIZE * pop.s * (1 - u)));
      this.mesh.setMatrixAt(first + k, matrix);
      // Added to what is behind, so a darker color is a fainter sparkle
      this.mesh.setColorAt(first + k, glow.setScalar(1 - u));
    }
    return SPARKLES;
  }
}

// Load the sparkle picture and add the sparkle mesh to the scene
export async function create(scene) {
  const texture = await new THREE.TextureLoader().loadAsync(SPARKLE_PICTURE);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), material, SPARKLE_CAPACITY);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  mesh.setColorAt(0, WHITE);
  mesh.frustumCulled = false;
  mesh.renderOrder = 5;
  mesh.count = 0;
  scene.add(mesh);
  return new SurpriseLook(mesh);
}
