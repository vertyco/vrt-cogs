// Draws the slug, its burst drops and the zombies on the 2D canvas over the world. Reads the world only.
import { PART } from "../sim/particles.js";
import { SLUG_POINTS } from "../sim/slugbytes.js";
import { PART_FIELDS } from "../sim/world.js";
import { ZOMBIE_POINTS } from "../sim/zombiebytes.js";
import { addLayer } from "./overlay.js";

const ONE = 256;
const RING = SLUG_POINTS - 1;
const SLUG_GONE = 2;
const PALE = "255, 238, 144";
const DROP = "rgb(255, 238, 146)";
const ZOMBIE = "rgb(204, 204, 204)";
const ZOMBIE_EDGE = "rgba(20, 20, 24, 0.55)";
// A zombie's head radius at full size, in cells (its body size of 2 in the original, a third as long)
const HEAD_CELLS = 2 / 3;
// Head-chest, chest-hip, chest to each elbow, hip to each knee, elbow to hand, knee to foot
const BONES = [
  [0, 1],
  [1, 2],
  [1, 3],
  [1, 4],
  [2, 5],
  [2, 6],
  [3, 7],
  [4, 8],
  [5, 9],
  [6, 10],
];

/** Adds the creature layer (order 40) to the overlay */
export function addCreatureLayer() {
  addLayer(40, (ctx, view, state) => {
    const world = state.world;
    drawBursts(ctx, view, world);
    if (world.slug !== null && world.settings.slug !== SLUG_GONE) {
      drawSlug(ctx, view, world.slug);
    }
  });
  addLayer(50, (ctx, view, state) => {
    for (const zombie of state.world.zombies) {
      if (zombie.scale > 0) {
        drawZombie(ctx, view, zombie);
      }
    }
  });
}

// A pale grey stick figure with a round head, over a dark edge so it reads on pale sand too
function drawZombie(ctx, view, zombie) {
  const points = [];
  for (let p = 0; p < ZOMBIE_POINTS; p++) {
    points.push(view.toScreen(zombie.x[p] / ONE, zombie.y[p] / ONE));
  }
  const width = Math.max(1, view.scale * 0.3);
  const head = Math.max(1.5, ((HEAD_CELLS * zombie.scale) / 1000) * view.scale);
  ctx.beginPath();
  for (const [a, b] of BONES) {
    ctx.moveTo(points[a][0], points[a][1]);
    ctx.lineTo(points[b][0], points[b][1]);
  }
  ctx.lineCap = "round";
  ctx.lineWidth = width + 2;
  ctx.strokeStyle = ZOMBIE_EDGE;
  ctx.stroke();
  ctx.lineWidth = width;
  ctx.strokeStyle = ZOMBIE;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(points[0][0], points[0][1], head, 0, Math.PI * 2);
  ctx.fillStyle = ZOMBIE;
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = ZOMBIE_EDGE;
  ctx.stroke();
}

function screenPoint(view, slug, p) {
  return view.toScreen(slug.x[p] / ONE, slug.y[p] / ONE);
}

// A smooth closed outline through the midpoints of the ring, each ring point a curve's control point
function outlinePath(ctx, points) {
  ctx.beginPath();
  const last = points[points.length - 1];
  ctx.moveTo((last[0] + points[0][0]) / 2, (last[1] + points[0][1]) / 2);
  for (let p = 0; p < points.length; p++) {
    const next = points[(p + 1) % points.length];
    ctx.quadraticCurveTo(points[p][0], points[p][1], (points[p][0] + next[0]) / 2, (points[p][1] + next[1]) / 2);
  }
  ctx.closePath();
}

function drawSlug(ctx, view, slug) {
  const points = [];
  for (let p = 1; p <= RING; p++) {
    points.push(screenPoint(view, slug, p));
  }
  const [cx, cy] = screenPoint(view, slug, 0);
  let radius = 0;
  for (const [x, y] of points) {
    radius += Math.hypot(x - cx, y - cy);
  }
  radius = Math.max(1, radius / RING);
  // Lit from the upper left: a bright spot there, the body's own yellow, and a darker rim
  const shade = ctx.createRadialGradient(cx - radius * 0.35, cy - radius * 0.4, radius * 0.1, cx, cy, radius * 1.1);
  shade.addColorStop(0, "rgb(255, 252, 220)");
  shade.addColorStop(0.45, `rgb(${PALE})`);
  shade.addColorStop(1, "rgb(214, 186, 92)");
  outlinePath(ctx, points);
  ctx.fillStyle = shade;
  ctx.fill();
  ctx.lineWidth = Math.max(1, radius * 0.06);
  ctx.strokeStyle = "rgba(120, 96, 30, 0.55)";
  ctx.stroke();
  drawEyes(ctx, cx, cy, radius, slug.right ? 1 : -1);
}

// Two eyes high on the side it rolls toward, looking that way
function drawEyes(ctx, cx, cy, radius, facing) {
  const eye = radius * 0.17;
  const y = cy - radius * 0.32;
  for (const offset of [0.12, 0.5]) {
    const x = cx + facing * radius * offset;
    ctx.beginPath();
    ctx.arc(x, y, eye, 0, Math.PI * 2);
    ctx.fillStyle = "rgb(255, 255, 255)";
    ctx.fill();
    ctx.lineWidth = Math.max(0.75, eye * 0.18);
    ctx.strokeStyle = "rgba(90, 70, 20, 0.6)";
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x + facing * eye * 0.35, y + eye * 0.1, eye * 0.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgb(30, 24, 16)";
    ctx.fill();
  }
}

function drawBursts(ctx, view, world) {
  const { n, rec } = world.parts;
  ctx.fillStyle = DROP;
  for (let k = 0; k < n; k++) {
    const at = k * PART_FIELDS;
    if (rec[at] !== PART.BURST) {
      continue;
    }
    const [x, y] = view.toScreen(rec[at + 1] / ONE, rec[at + 2] / ONE);
    const r = Math.max(1, ((rec[at + 5] / ONE) * view.scale) / 2);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
}
