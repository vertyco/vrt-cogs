// How the Orb theme looks and moves: its colors, the web behind it, the fins around the orb, the arm that holds
// the info panel, and the turns between menus. menu.js decides what shows; this file draws it.

const SVG = "http://www.w3.org/2000/svg";
const calm = window.matchMedia("(prefers-reduced-motion: reduce)");

// ---------- Colors ----------

// Each tone of the theme in OKLCH, measured from the green it was designed in: its lightness, its chroma as a
// share of the color's, how many degrees its hue leans toward yellow (the bright tones do, like the original's
// highlights), and how far its lightness follows the glow color's own. The dark tones and the text keep their
// lightness for every color, so every color reads as well as the green; the middle ones follow the color, so
// a red glow makes a red orb rather than a pink one
const TONES = {
  ink: [0.139, 0.15, -9, 0],
  deep: [0.239, 0.3, -9, 0],
  dark: [0.427, 0.62, -9, 0.3],
  mid: [0.606, 0.87, -8, 0.7],
  main: [0.814, 1, 0, 1],
  light: [0.914, 0.89, 7, 0.8],
  pale: [0.966, 0.52, 12, 0.45],
  white: [0.989, 0.19, 18, 0.15],
  text: [0.952, 0.4, 12, 0],
  dim: [0.836, 0.57, 4, 0],
};
// The designed green's lightness and chroma, and how vivid a color has to be for a full-strength theme. Grayer
// colors make a grayer theme, down to silver
const BASE_LIGHTNESS = 0.814;
const BASE_CHROMA = 0.212;
const VIVID = 0.16;
const YELLOW = 100;

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toScreen = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function oklch(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const lightness = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  return [lightness, Math.hypot(a, bb), (Math.atan2(bb, a) * 180) / Math.PI];
}

function linearRgb(lightness, chroma, hue) {
  const h = (hue * Math.PI) / 180;
  const [a, b] = [chroma * Math.cos(h), chroma * Math.sin(h)];
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

// A color the screen can't show loses chroma until it can, which keeps its lightness and hue
function screenColor(lightness, chroma, hue) {
  const fits = (c) => linearRgb(lightness, c, hue).every((v) => v >= -0.0005 && v <= 1.0005);
  let [low, high] = [0, chroma];
  if (!fits(high)) {
    for (let i = 0; i < 14; i++) {
      const mid = (low + high) / 2;
      [low, high] = fits(mid) ? [mid, high] : [low, mid];
    }
    chroma = low;
  }
  return linearRgb(lightness, chroma, hue).map((v) => Math.round(Math.min(Math.max(toScreen(v), 0), 1) * 255));
}

// Sets --orb-<tone> on the page as "r g b", for CSS to use as rgb(var(--orb-main) / 0.5)
export function applyGlow(hex) {
  const [glowLightness, chroma, hue] = oklch(hex);
  const strength = Math.min(1, chroma / VIVID);
  // Yellow lies this way round the color wheel from the color, the shorter way
  const toward = Math.sign(Math.sin(((YELLOW - hue) * Math.PI) / 180));
  const lift = Math.min(Math.max(glowLightness - BASE_LIGHTNESS, -0.25), 0.1);
  const root = document.documentElement.style;
  const tones = {};
  for (const [name, [lightness, share, lean, follow]] of Object.entries(TONES)) {
    const own = Math.min(lightness + lift * follow, 0.99);
    tones[name] = screenColor(own, BASE_CHROMA * share * strength, hue + toward * lean);
    root.setProperty(`--orb-${name}`, tones[name].join(" "));
  }
  return tones;
}

// ---------- The web behind the orb ----------

// The same web on every visit and every redraw
function seeded(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// The web is a honeycomb of uneven cells wrapped around the orb. It is laid out by distance (as a log) and angle,
// which keeps every cell's shape while it grows with its distance, like the inside of a sphere seen from its
// middle. CELL is a cell's size for its distance, and each row of cells sits half a cell round from the last
const CELL = 0.12;
const ACROSS = Math.round((Math.PI * 2) / CELL);
const ROW = CELL * 0.866;
const TURN = Math.PI * 2;

function lattice(rows, random) {
  return Array.from({ length: rows }, (_, j) =>
    Array.from({ length: ACROSS }, (_, i) => [
      (j + (random() - 0.5) * 0.5) * ROW,
      ((i + j / 2 + (random() - 0.5) * 0.5) * TURN) / ACROSS,
    ]),
  );
}

// A lattice point, where a column past either end wraps round to the other side of the circle
function point(grid, i, j) {
  const k = ((i % ACROSS) + ACROSS) % ACROSS;
  const [u, v] = grid[j][k];
  return [u, v + ((i - k) / ACROSS) * TURN];
}

// The middle of the circle through three lattice points, where three cells meet
function corner([ax, ay], [bx, by], [cx, cy]) {
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  const [a, b, c] = [ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy];
  return [(a * (by - cy) + b * (cy - ay) + c * (ay - by)) / d, (a * (cx - bx) + b * (ax - cx) + c * (bx - ax)) / d];
}

// The corners of the two triangles of points to the upper right of point i, j. Every cell wall joins the corners
// of the two triangles on either side of one pair of neighboring points
function upper(grid, i, j) {
  return corner(point(grid, i, j), point(grid, i + 1, j), point(grid, i, j + 1));
}

function lower(grid, i, j) {
  return corner(point(grid, i + 1, j), point(grid, i + 1, j + 1), point(grid, i, j + 1));
}

export function drawWeb(canvas, [cx, cy], radius, rgb) {
  if (radius <= 0) {
    return;
  }
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  const [w, h] = [window.innerWidth, window.innerHeight];
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  const far = Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
  const start = radius * 0.8;
  const rows = Math.ceil(Math.log((far * 1.3) / start) / ROW) + 2;
  const grid = lattice(rows, seeded(2001));
  const screen = ([u, v]) => [cx + start * Math.exp(u) * Math.cos(v), cy + start * Math.exp(u) * Math.sin(v)];
  // A wall curves with the rings round the orb: it is drawn through its middle's place on the screen
  const wall = (a, b) => {
    const [[x1, y1], [x2, y2]] = [screen(a), screen(b)];
    const [mx, my] = screen([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    ctx.moveTo(x1, y1);
    ctx.quadraticCurveTo(2 * mx - (x1 + x2) / 2, 2 * my - (y1 + y2) / 2, x2, y2);
  };
  // Walls fade in away from the orb and grow thicker further out, as if closer
  for (let j = 0; j < rows - 1; j++) {
    const r = start * Math.exp(j * ROW);
    ctx.beginPath();
    for (let i = 0; i < ACROSS; i++) {
      const cell = upper(grid, i, j);
      wall(cell, lower(grid, i, j));
      wall(cell, lower(grid, i - 1, j));
      if (j > 0) {
        wall(cell, lower(grid, i, j - 1));
      }
    }
    ctx.lineWidth = 0.6 + Math.min(1, r / far) * 1.3;
    ctx.strokeStyle = `rgb(${rgb.join(" ")} / ${0.05 + Math.min(1, Math.max(0, r - radius * 1.1) / radius) * 0.17})`;
    ctx.stroke();
  }
}

// ---------- The fins and goo around the orb ----------

// A round hole to punch through a shape drawn with the even-odd fill rule
function hole([x, y], r) {
  return ` M${(x + r).toFixed(1)} ${y.toFixed(1)} a${r} ${r} 0 1 0 ${-2 * r} 0 a${r} ${r} 0 1 0 ${2 * r} 0 Z`;
}

// A crescent along a circle of the given radius from one angle to another, thickest in the middle, with round
// holes punched through it at the given places along it
function crescent(from, to, radius, thick, holes = []) {
  const at = (r, deg) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)];
  const width = (t) => thick * Math.sin(Math.PI * t) ** 0.7;
  const outer = [];
  const inner = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24;
    const deg = from + (to - from) * t;
    outer.push(at(radius + width(t), deg));
    inner.push(at(radius - width(t) * 0.15, deg));
  }
  let d = `M${[...outer, ...inner.reverse()].map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")} Z`;
  for (const [t, r] of holes) {
    d += hole(at(radius + width(t) * 0.42, from + (to - from) * t), r);
  }
  return d;
}

function svgNode(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, value);
  }
  return node;
}

function shapeLayer(className, paths) {
  const svg = svgNode("svg", { class: className, viewBox: "-100 -100 200 200" });
  for (const [kind, d] of paths) {
    svg.append(svgNode("path", { class: kind, d, "fill-rule": "evenodd" }));
  }
  return svg;
}

// The orb's radius is 50 in these drawings. The fins are the mechanical frame that turns a notch with every move;
// the goo is the glowing jelly slowly sliding over the orb's surface
export function buildOrbParts() {
  const fins = shapeLayer("fins-shape", [
    ["fin", crescent(196, 292, 55, 22, [[0.36, 4.2], [0.62, 3.2]])],
    ["fin", crescent(68, 158, 55, 19, [[0.45, 3.8]])],
    ["fin thin", crescent(300, 346, 56, 9)],
    ["fin-line", crescent(170, 330, 79, 1.2)],
  ]);
  // The fins catch the orb's light where they pass close to it
  fins.insertAdjacentHTML(
    "afterbegin",
    `<defs><radialGradient id="fin-light" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="80">
      <stop class="fin-near" offset="0.62" /><stop class="fin-far" offset="1" />
    </radialGradient></defs>`,
  );
  document.getElementById("orb-fins").append(fins);
  const goo = shapeLayer("goo-shape", [
    ["goo", crescent(-40, 70, 44, 14)],
    ["goo", crescent(20, 95, 47, 9)],
    ["goo", crescent(110, 200, 45, 11)],
    ["goo", crescent(150, 240, 49, 6)],
    ["goo", crescent(225, 300, 46, 8)],
  ]);
  document.getElementById("orb-goo").append(goo);
}

// ---------- The arm that holds the info panel ----------

// A plate from a to b, half as wide as wa at a and wb at b, with round ends and round holes at the given places
// along it, like the fins
function limb([ax, ay], [bx, by], wa, wb, holes = []) {
  const length = Math.hypot(bx - ax, by - ay);
  const [nx, ny] = [-(by - ay) / length, (bx - ax) / length];
  const p = (x, y) => `${x.toFixed(1)} ${y.toFixed(1)}`;
  let d = `M${p(ax + nx * wa, ay + ny * wa)} L${p(bx + nx * wb, by + ny * wb)}`;
  d += ` A${wb} ${wb} 0 0 0 ${p(bx - nx * wb, by - ny * wb)} L${p(ax - nx * wa, ay - ny * wa)}`;
  d += ` A${wa} ${wa} 0 0 0 ${p(ax + nx * wa, ay + ny * wa)} Z`;
  return d + holes.map(([t, r]) => hole([ax + (bx - ax) * t, ay + (by - ay) * t], r)).join("");
}

// A disc with a ring of holes and one in the middle, for the joints
function joint([x, y], r, count) {
  const ring = Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2;
    return hole([x + Math.cos(angle) * r * 0.62, y + Math.sin(angle) * r * 0.62], r * 0.13);
  });
  return hole([x, y], r) + ring.join("") + hole([x, y], r * 0.28);
}

// Drawn with the panel's top edge at y = 0 and the wrist just above it. The forearm reaches up and out to the
// elbow, and the upper arm runs on out of sight, so the panel hangs off a machine beyond the screen. The wrist
// is the part that turns in place
const WRIST = [0, -24];
const ELBOW = [128, -152];
const SHOULDER = [300, -800];
const CLAMP = "M-36 8 V-4 Q-36 -10 -30 -10 H30 Q36 -10 36 -4 V8 H28 V-2 H-28 V8 Z";

export function buildArm() {
  const svg = svgNode("svg", { class: "screen-arm", viewBox: "-60 -260 360 280", "aria-hidden": "true" });
  const chain = svgNode("g", { class: "arm-chain" });
  chain.append(
    svgNode("path", { class: "arm-plate", d: limb(ELBOW, SHOULDER, 22, 30, [[0.09, 8], [0.2, 6], [0.3, 5]]) }),
    svgNode("path", { class: "arm-line", d: "M150 -172 L270 -660 M110 -160 L230 -650" }),
    svgNode("path", { class: "arm-plate", d: limb(WRIST, ELBOW, 12, 17, [[0.42, 5], [0.7, 6]]) }),
    svgNode("path", { class: "arm-piston", d: "M-14 -46 L92 -160" }),
    svgNode("path", { class: "arm-cable", d: "M18 -10 C 70 -20, 150 -80, 150 -128" }),
    svgNode("path", { class: "arm-plate", d: joint(ELBOW, 28, 6) }),
  );
  const wrist = svgNode("g", { class: "arm-wrist" });
  wrist.append(
    svgNode("path", { class: "arm-plate", d: joint(WRIST, 19, 4) }),
    svgNode("path", { class: "arm-line", d: "M0 -40 V-31 M0 -17 V-8 M-16 -24 H-9 M9 -24 H16" }),
  );
  svg.append(chain, svgNode("path", { class: "arm-plate", d: CLAMP }), wrist);
  return svg;
}

// ---------- Turns between menus ----------

// The arm brightens out of nothing, its wrist spins in place, and it settles back to a ghost of itself. The
// brightening starts from however bright the arm already is, and each spin and sway adds to any still under way,
// so quick moves keep it going instead of snapping it back. The wrist looks the same every quarter turn, so a
// spin that ends never shows a jump
export function turnArm(arm, big) {
  if (calm.matches || !arm) {
    return;
  }
  const time = big ? 900 : 520;
  arm.animate([{ opacity: 1, offset: 0.3 }, { opacity: 0.4 }], { duration: time + 500 });
  arm.querySelector(".arm-wrist").animate(
    [{ transform: "rotate(0deg)" }, { transform: `rotate(${big ? 360 : 180}deg)` }],
    { duration: time, easing: "cubic-bezier(0.6, 0, 0.3, 1)", composite: "add" },
  );
  const sway = `rotate(${big ? -14 : -7}deg)`;
  arm.querySelector(".arm-chain").animate(
    [{ transform: "rotate(0deg)" }, { transform: sway, offset: 0.4 }, { transform: "rotate(0deg)" }],
    { duration: time, easing: "ease-in-out", composite: "add" },
  );
}

// The panel turns edge-on to the player, and the new one turns back to face them. The old panel goes once it
// has turned away. A panel still turning in when the next move comes gives its place to the new one, which
// carries on turning in from the same angle
export function turnPanels(leaving, coming, big) {
  if (calm.matches) {
    leaving?.remove();
    return;
  }
  const half = big ? 300 : 150;
  const easing = "cubic-bezier(0.1, 0.5, 0.5, 1)";
  if (leaving && leaving.getAnimations().length) {
    const { transform, opacity } = getComputedStyle(leaving);
    leaving.remove();
    coming.animate([{ transform, opacity }, { transform: "rotateY(0deg)", opacity: 1 }], { duration: half, easing });
    return;
  }
  if (leaving) {
    const away = leaving.animate(
      [{ transform: "rotateY(0deg)", opacity: 1 }, { transform: "rotateY(80deg)", opacity: 0.2 }],
      { duration: half, easing: "cubic-bezier(0.5, 0, 0.9, 0.5)", fill: "forwards" },
    );
    away.finished.then(
      () => leaving.remove(),
      () => leaving.remove(),
    );
  }
  coming.animate(
    [{ transform: "rotateY(-80deg)", opacity: 0.2 }, { transform: "rotateY(0deg)", opacity: 1 }],
    { duration: half, delay: leaving ? half : 0, easing, fill: "backwards" },
  );
}

// The first look at the menu: each pod pops onto the ring in turn and its tab slides out of it. Each ends where
// the stylesheet puts it, so the selected pod and tab land in their raised places
export function introPills(pills) {
  if (calm.matches) {
    return;
  }
  pills.forEach((pill, i) => {
    const delay = 80 + i * 45;
    pill.querySelector(".pod").animate(
      [{ transform: "scale(0)", opacity: 0, offset: 0 }, { transform: "scale(1.2)", opacity: 1, offset: 0.7 }],
      { duration: 380, delay, easing: "ease-out", fill: "backwards" },
    );
    pill.querySelector(".plate").animate([{ transform: "translateX(-40px) scaleX(0.4)", opacity: 0, offset: 0 }], {
      duration: 360,
      delay: delay + 120,
      easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      fill: "backwards",
    });
  });
}

// A cog for the Settings pod
export function gearIcon() {
  const svg = svgNode("svg", { class: "gear-icon", viewBox: "-12 -12 24 24", "aria-hidden": "true" });
  const tooth = (i) => `<path d="M-2.6 -11.2 H2.6 L3.4 -7 H-3.4 Z" transform="rotate(${i * 45})" />`;
  const teeth = Array.from({ length: 8 }, (_, i) => tooth(i));
  svg.innerHTML = `${teeth.join("")}<circle r="8" /><circle class="gear-hole" r="3.4" />`;
  return svg;
}
