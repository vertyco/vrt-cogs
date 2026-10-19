// The belt: the original's pieces merged into one mesh, the machine at its entrance, the soft shadow under it and the
// arrows that move along it.
import * as THREE from "./vendor/three.module.min.js";
import { mergeGeometries } from "./vendor/BufferGeometryUtils.js";
import { GLTFLoader } from "./vendor/GLTFLoader.js";
import { L_PER_UNIT } from "./sim/numbers.js";
import { flipPosition, flipRotation, worldFromPicture } from "./space.js";

const MODELS = "models/features/";
const SHADOW_TEXTURE = "art/ui/Texture_ConveyorShadow.png";
const MACHINE = "belt_starter_machine";
// The corner the level scene keeps at the entrance's left lane. The phone recordings draw the lane ending at its ramp
// above the machine, with no corner below it
const NOT_DRAWN = ["Model_ConveyorTurn (2)"];
// The machine the art stage made is smaller and paler than the one in the recordings, so the page enlarges it and
// colors its three parts to match
const MACHINE_SCALE = 1.4;
const MACHINE_COLORS = { StarterSteel: 0x565d9a, StarterPanel: 0x7886c4, StarterRim: 0x434b8b };

// The belt moves its arrows at the belt's own speed (ConveyorController speed 5.0 units a second)
export const BELT_UNITS_PER_SECOND = 5;
export const ARROW_SPACING = 1.2;
const ARROW_STRIP_WIDTH = 0.5;
// Just above the lane's floor, which stands about 0.65 units off the ground
const ARROW_HEIGHT = 0.668;

// The shadow picture only gives the shape; this is the color and strength it is drawn in
const SHADOW_COLOR = 0x14153a;
const SHADOW_OPACITY = 0.3;
// A picture drawn at scale 1 is its size in pixels over this many to the unit (Unity's default for sprites)
const SPRITE_PIXELS_PER_UNIT = 100;
const SHADOW_HEIGHT = 0.01;

// The belt's colors, read off the phone recordings: the lane's floor, the walls' top edge, and their sides. The
// pieces' own picture would give a floor that is too light and different on each piece, so the faces are colored by
// where they face instead
const FLOOR = new THREE.Color("#464868");
const RIM_TOP = new THREE.Color("#9db3f5");
const RIM_SIDE = new THREE.Color("#a3afe4");
const RAMP = new THREE.Color("#9aaae6");
// Raw heights in a piece's file: the floor is at 1.0 and the rims above 1.03
const RIM_FROM = 1.03;
const FLAT = 0.7;

function gltfMeshes(gltf) {
  const found = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      node.updateMatrix();
      found.push(node);
    }
  });
  return found;
}

// A belt piece is stretched by the level scene's own scale, so the file's node scale is left out. A second mesh in
// the same file (the end piece's roller) keeps its place inside the piece. The converted files have the original's
// meshes mirrored left to right, which a half turn about the up axis undoes once z is flipped too
function pieceGeometries(gltf, matrix, ramp) {
  return gltfMeshes(gltf).map((node, i) => {
    const geometry = node.geometry.clone();
    if (i > 0) {
      geometry.applyMatrix4(node.matrix);
    }
    paint(geometry, ramp);
    geometry.scale(-1, 1, -1);
    geometry.applyMatrix4(matrix);
    return geometry.index ? geometry.toNonIndexed() : geometry;
  });
}

async function loadTexture(url) {
  const texture = await new THREE.TextureLoader().loadAsync(url);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

// Color every vertex of a piece by what it belongs to. The start and end pieces are ramps, light all over
function paint(geometry, ramp) {
  const position = geometry.getAttribute("position");
  const normal = geometry.getAttribute("normal");
  const colors = new Float32Array(position.count * 3);
  for (let i = 0; i < position.count; i++) {
    let color = RIM_SIDE;
    if (normal.getY(i) > FLAT) {
      color = position.getY(i) < RIM_FROM ? (ramp ? RAMP : FLOOR) : RIM_TOP;
    }
    color.toArray(colors, i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

// One faint arrowhead per ARROW_SPACING, pointing the way the belt runs (along the texture's width)
function arrowTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 192;
  canvas.height = 80;
  const g = canvas.getContext("2d");
  g.strokeStyle = "rgba(190, 205, 255, 0.32)";
  g.lineWidth = 9;
  g.lineCap = "round";
  g.lineJoin = "round";
  g.beginPath();
  g.moveTo(84, 12);
  g.lineTo(108, 40);
  g.lineTo(84, 68);
  g.stroke();
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

// The two edge points of the strip at belt point i, and how far along the belt that point is
function stripEdges(points, i, half) {
  const a = points[Math.max(0, i - 1)];
  const b = points[Math.min(points.length - 1, i + 1)];
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  // Picture space has y up the screen, so the left of the way ahead is (-dy, dx)
  const nx = -(b[1] - a[1]) / length;
  const ny = (b[0] - a[0]) / length;
  return [-1, 1].map((side) => [points[i][0] + nx * side * half, points[i][1] + ny * side * half]);
}

// A flat strip laid along the belt's center line, one picture's width of arrows every ARROW_SPACING along it
function arrowStrip(belt, texture) {
  const positions = [];
  const uvs = [];
  const indices = [];
  const half = (ARROW_STRIP_WIDTH * L_PER_UNIT) / 2;
  let along = 0;
  belt.points.forEach((p, i) => {
    stripEdges(belt.points, i, half).forEach(([x, y], side) => {
      const at = worldFromPicture(x, y, ARROW_HEIGHT);
      positions.push(at.x, at.y, at.z);
      uvs.push(along / ARROW_SPACING, side);
    });
    if (i > 0) {
      const last = (i - 1) * 2;
      indices.push(last, last + 1, last + 2, last + 1, last + 3, last + 2);
    }
    if (i + 1 < belt.points.length) {
      const q = belt.points[i + 1];
      along += Math.hypot(q[0] - p[0], q[1] - p[1]) / L_PER_UNIT;
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.renderOrder = 1;
  return mesh;
}

function mergedPieces(pieces, byName) {
  const geometries = [];
  for (const piece of pieces.filter((p) => p.model && p.model !== MACHINE && !NOT_DRAWN.includes(p.name))) {
    const matrix = new THREE.Matrix4().compose(
      flipPosition(piece.position),
      flipRotation(piece.rotation),
      new THREE.Vector3(...piece.scale),
    );
    const ramp = piece.model === "belt_start" || piece.model === "belt_end";
    geometries.push(...pieceGeometries(byName.get(piece.model), matrix, ramp));
  }
  const geometry = mergeGeometries(geometries);
  geometry.computeBoundingBox();
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0 }));
}

function machineMesh(pieces, byName) {
  const piece = pieces.find((p) => p.model === MACHINE);
  const model = byName.get(MACHINE).scene.clone(true);
  model.position.copy(flipPosition(piece.position));
  model.quaternion.copy(flipRotation(piece.rotation));
  model.scale.set(...piece.scale).multiplyScalar(MACHINE_SCALE);
  model.traverse((node) => {
    if (node.isMesh) {
      node.material = node.material.clone();
      node.material.color.set(MACHINE_COLORS[node.material.name]);
    }
  });
  return model;
}

// The baked shadow of the belt, laid flat where the level scene puts it
function shadowMesh(piece, texture) {
  const { width, height } = texture.image;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(width / SPRITE_PIXELS_PER_UNIT, height / SPRITE_PIXELS_PER_UNIT),
    new THREE.MeshBasicMaterial({
      map: texture,
      color: SHADOW_COLOR,
      transparent: true,
      opacity: SHADOW_OPACITY,
      depthWrite: false,
    }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.copy(flipPosition(piece.position));
  mesh.position.y = SHADOW_HEIGHT;
  return mesh;
}

// Returns {group, box, reach, arrows}: everything to add to the scene, the belt's bounding box in world units, the box
// of the belt and its starter machine together, and the arrows' texture, whose offset the page scrolls
export async function buildBelt(board) {
  const loader = new GLTFLoader();
  const pieces = board.anchors.belt_pieces;
  const names = [...new Set(pieces.filter((p) => p.model).map((p) => p.model))];
  const [files, shadow] = await Promise.all([
    Promise.all(names.map((name) => loader.loadAsync(`${MODELS}${name}.glb`))),
    loadTexture(SHADOW_TEXTURE),
  ]);
  const byName = new Map(names.map((name, i) => [name, files[i]]));
  const belt = mergedPieces(pieces, byName);
  const arrows = arrowTexture();
  const group = new THREE.Group();
  const shadowPiece = pieces.find((p) => p.picture);
  const machine = machineMesh(pieces, byName);
  group.add(belt, machine, shadowMesh(shadowPiece, shadow), arrowStrip(board.belt, arrows));
  // The belt and the starter machine beside it: the camera has to fit all of it across the column
  const reach = belt.geometry.boundingBox.clone().union(new THREE.Box3().setFromObject(machine));
  return { group, box: belt.geometry.boundingBox, reach, arrows };
}
