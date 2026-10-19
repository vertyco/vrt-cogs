// Feature 11, the Pig Pipe: a periwinkle tunnel stands in the queue place of the pipe's entry, with a white tag on its
// top showing how many cats are still inside. Each time a cat leaves the queue ahead of it, a cat pops out of the
// tunnel and hops to the place in front of it (fx.js draws the hop from the pipe's spot) while the tunnel punches up a
// little; the last cat out takes the tunnel with it, which vanishes like a cat (fx.js). The tunnel is the original's
// `models/features/shooter_pipe_feature.glb` (ASSETS.md), one color like the New Feature popup's picture. The
// original's prefab holds no sound, so the pop is a cartoon pop from ASSETS.md's list. Everything comes from the
// simulation's pipe records (sim/features/pig_pipe.js) and never changes a rule.
import * as THREE from "../vendor/three.module.min.js";
import { GLTFLoader } from "../vendor/GLTFLoader.js";
import { NUMBER } from "../sim/features/pig_pipe.js";
import { play as sound } from "../sound.js";

export { NUMBER };

const MODEL = "models/features/shooter_pipe_feature.glb";
// The most pipes one level holds is 5
const CAPACITY = 6;
const PIPE_BLUE = new THREE.Color("#7d95ff");
// The tunnel's width next to a cat's (the cat's body is 0.86 wide at scale 1)
const PIPE_SIZE = 1.0;
// The tunnel's punch as a cat leaves: 0.2 s, stretching 0.08 across and 0.25 up at its peak
const PUNCH_TICKS = 12;
const PUNCH_ACROSS = 0.08;
const PUNCH_UP = 0.25;
// The tag on the tunnel's top: a white pill with dark digits
const LABEL_W = 256;
const LABEL_H = 160;
const LABEL_FONT = '"Inter Black", "Segoe UI", sans-serif';
const LABEL_INK = "#262846";
const LABEL_SHARE = 0.78;
// The tag's width as a share of the tunnel's, and how far it floats over the top
const LABEL_WIDE = 0.6;
const LABEL_LIFT = 0.012;

function clamp01(u) {
  return Math.min(1, Math.max(0, u));
}

// The tunnel as the prefab lies: its opening toward +z like a cat's face, centered with its foot on the ground and one
// unit wide. `top` is how high it stands after that scaling
function tunnelModel(gltf) {
  const tunnel = gltf.scene.clone();
  tunnel.traverse((node) => {
    if (node.isMesh) {
      node.material = new THREE.MeshStandardMaterial({ color: PIPE_BLUE, roughness: 0.5, metalness: 0.05 });
    }
  });
  const box = new THREE.Box3().setFromObject(tunnel);
  const width = box.max.x - box.min.x;
  const inner = new THREE.Group();
  inner.add(tunnel);
  tunnel.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
  inner.scale.setScalar(1 / width);
  inner.userData.top = (box.max.y - box.min.y) / width;
  return inner;
}

class PigPipeLook {
  constructor(parts) {
    this.parts = parts;
    this.now = 0;
    this.mine = null;
    // Per pipe entry id: its drawn pose this frame ({x, y, z, yaw, scale}) and when it last punched
    this.poses = new Map();
    this.punched = new Map();
    // The count each pool part's tag shows now (null: not drawn)
    this.shown = parts.map(() => null);
  }

  build(state) {
    this.clear();
    this.mine = state.features[NUMBER] || null;
    this.now = state.tick;
  }

  clear() {
    this.mine = null;
    this.poses.clear();
    this.punched.clear();
    this.shown.fill(null);
    for (const part of this.parts) {
      part.group.visible = false;
    }
  }

  onEvents(events) {
    for (const event of events) {
      if (event.k === "pipe_release") {
        this.punched.set(event.pipe, event.t);
        sound("pipe_out");
      }
    }
  }

  frame(alpha, state) {
    this.now = state.tick - 1 + alpha;
  }

  begin(state) {
    this.mine = state.features[NUMBER] || null;
    this.poses.clear();
  }

  // A pipe entry is drawn as the tunnel: remember where its cat would stand and hide the cat
  shape(id, pig, pose) {
    if (!this.mine || !pose.shown || !this.mine.pipes.some((pipe) => pipe.pig === id)) {
      return;
    }
    this.poses.set(id, { x: pose.x, y: pose.y + pose.air, z: pose.z, yaw: pose.yaw, scale: pose.scale * pose.sx });
    pose.shown = false;
  }

  end() {
    if (!this.mine) {
      return;
    }
    let used = 0;
    for (const [id, at] of this.poses) {
      if (used >= this.parts.length) {
        break;
      }
      this.write(used, id, at);
      used += 1;
    }
    for (let i = used; i < this.parts.length; i++) {
      this.parts[i].group.visible = false;
      this.shown[i] = null;
    }
  }

  // One tunnel where its entry stands, punching up while a cat leaves, with the count on its tag
  write(index, id, at) {
    const part = this.parts[index];
    const pipe = this.mine.pipes.find((entry) => entry.pig === id);
    const u = clamp01((this.now - (this.punched.get(id) ?? -Infinity)) / PUNCH_TICKS);
    const k = u < 1 ? Math.sin(Math.PI * u) : 0;
    const size = at.scale * PIPE_SIZE;
    part.group.visible = true;
    part.group.position.set(at.x, at.y, at.z);
    part.group.rotation.set(0, at.yaw, 0);
    part.group.scale.set(size * (1 + PUNCH_ACROSS * k), size * (1 + PUNCH_UP * k), size * (1 + PUNCH_ACROSS * k));
    if (this.shown[index] !== pipe.inside.length) {
      this.shown[index] = pipe.inside.length;
      this.paint(part, pipe.inside.length);
    }
  }

  // The tag's number, redrawn only when it changed
  paint(part, count) {
    const g = part.canvas.getContext("2d");
    g.clearRect(0, 0, LABEL_W, LABEL_H);
    part.label.visible = count > 0;
    if (count <= 0) {
      part.map.needsUpdate = true;
      return;
    }
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.roundRect(4, 4, LABEL_W - 8, LABEL_H - 8, LABEL_H / 2 - 4);
    g.fill();
    g.font = `900 ${Math.round(LABEL_H * LABEL_SHARE)}px ${LABEL_FONT}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = LABEL_INK;
    g.fillText(String(count), LABEL_W / 2, LABEL_H * 0.54, LABEL_W * 0.8);
    part.map.needsUpdate = true;
  }
}

// Load the prefab and add a pool of tunnels with their tags to the scene
export async function create(scene) {
  const gltf = await new GLTFLoader().loadAsync(MODEL);
  const source = tunnelModel(gltf);
  const parts = [];
  for (let i = 0; i < CAPACITY; i++) {
    const group = new THREE.Group();
    group.add(source.clone());
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
    label.position.set(0, source.userData.top + LABEL_LIFT, 0);
    label.scale.setScalar(LABEL_WIDE);
    label.renderOrder = 3;
    // The tunnel is turned to face up the screen like a cat, which would put the digits upside down
    const upright = new THREE.Group();
    upright.rotation.y = Math.PI;
    upright.add(label);
    group.add(upright);
    group.visible = false;
    scene.add(group);
    parts.push({ group, canvas, map, label });
  }
  return new PigPipeLook(parts);
}
