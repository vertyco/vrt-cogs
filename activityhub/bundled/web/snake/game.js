import { startArcade } from "activityhub/arcade.js";
import { OPPOSITE, SIZE, SnakeGame, tickMs } from "./rules.js";

const KEYS = { arrowup: "U", arrowdown: "D", arrowleft: "L", arrowright: "R", w: "U", s: "D", a: "L", d: "R" };
// Turns pressed faster than the snake steps wait in line, so a quick U-turn (up then left) isn't lost
const QUEUE_LIMIT = 3;
const SWIPE_DISTANCE = 24;
// A crash stays on screen this long before the results, so the player sees what happened
const CRASH_MS = 500;
const COLORS = {
  board: "#10132a",
  boardAlt: "#141936",
  head: [154, 230, 180],
  tail: [39, 103, 73],
  dead: [113, 128, 150],
  eye: "#0b0d17",
  apple: "#f56565",
  appleDark: "#c53030",
  appleLight: "#feb2b2",
  leaf: "#68d391",
};

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const stage = document.getElementById("stage");
// The checkered board never changes, so it is drawn once per resize and copied in each frame
const backdrop = document.createElement("canvas");

const state = {
  game: new SnakeGame(1),
  mode: "idle", // idle | waiting | running | paused | over
  pausedFrom: "waiting",
  queue: [],
  moves: [],
  tick: 0,
  wait: 0,
  last: 0,
  stepped: false,
  crashed: false,
  body: [], // the cells drawn, head first
  left: null, // the cell the tail just left, so the tail slides out of it smoothly
  particles: [],
  swipe: null,
};
state.body = state.game.body;
let frameId = 0;

// ---------- Drawing ----------

function center([x, y], size) {
  return [(x + 0.5) * size, (y + 0.5) * size];
}

function lerp(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function mix(a, b, t) {
  return `rgb(${a.map((value, i) => Math.round(value + (b[i] - value) * t)).join(",")})`;
}

function circle(x, y, radius, fill) {
  ctx.fillStyle = fill;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
}

function paintBackdrop() {
  backdrop.width = canvas.width;
  backdrop.height = canvas.height;
  const paint = backdrop.getContext("2d");
  const size = canvas.width / SIZE;
  const edge = (i) => Math.round(i * size);
  paint.fillStyle = COLORS.board;
  paint.fillRect(0, 0, backdrop.width, backdrop.height);
  paint.fillStyle = COLORS.boardAlt;
  for (let y = 0; y < SIZE; y++) {
    for (let x = (y + 1) % 2; x < SIZE; x += 2) {
      paint.fillRect(edge(x), edge(y), edge(x + 1) - edge(x), edge(y + 1) - edge(y));
    }
  }
}

// How far the last step has played out on screen, from 0 (just stepped) to 1 (arrived)
function progress() {
  if (!state.stepped || state.mode === "over") {
    return 1;
  }
  return Math.min(1, state.wait / tickMs(state.game.apples));
}

// The body's path through the middle of its cells, with the head and tail slid part of the way along
function snakePoints(size) {
  const body = state.body;
  const t = progress();
  const points = [lerp(body[1], body[0], t), ...body.slice(1)];
  if (state.left) {
    points.push(lerp(state.left, body[body.length - 1], t));
  }
  return points.map((cell) => center(cell, size));
}

function drawSnake(size) {
  const points = snakePoints(size);
  const last = Math.max(1, points.length - 2);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  // Tail first, so each piece nearer the head is drawn over the one behind it
  for (let i = points.length - 2; i >= 0; i--) {
    const along = i / last;
    ctx.strokeStyle = mix(state.crashed ? COLORS.dead : COLORS.head, COLORS.tail, along);
    ctx.lineWidth = size * (0.76 - 0.22 * along);
    ctx.beginPath();
    ctx.moveTo(...points[i]);
    ctx.lineTo(...points[i + 1]);
    ctx.stroke();
  }
  drawEyes(points[0], size);
}

function drawEyes([hx, hy], size) {
  const [head, neck] = state.body;
  const [dx, dy] = [head[0] - neck[0], head[1] - neck[1]];
  for (const side of [-1, 1]) {
    const ex = hx + (dx * 0.1 - dy * 0.2 * side) * size;
    const ey = hy + (dy * 0.1 + dx * 0.2 * side) * size;
    circle(ex, ey, size * 0.14, "#ffffff");
    circle(ex + dx * size * 0.05, ey + dy * size * 0.05, size * 0.075, state.crashed ? "#e53e3e" : COLORS.eye);
  }
}

function drawApple(size, now) {
  const food = state.game.food;
  if (!food) {
    return;
  }
  const [x, y] = center(food, size);
  const lively = state.mode === "running" || state.mode === "waiting";
  const r = size * 0.34 * (lively ? 1 + 0.06 * Math.sin(now / 160) : 1);
  const glow = ctx.createRadialGradient(x, y, r * 0.4, x, y, r * 2.4);
  glow.addColorStop(0, "rgba(245, 101, 101, 0.32)");
  glow.addColorStop(1, "rgba(245, 101, 101, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(x - r * 2.4, y - r * 2.4, r * 4.8, r * 4.8);
  const shine = ctx.createRadialGradient(x - r * 0.35, y - r * 0.3, r * 0.1, x, y, r);
  shine.addColorStop(0, COLORS.appleLight);
  shine.addColorStop(0.35, COLORS.apple);
  shine.addColorStop(1, COLORS.appleDark);
  circle(x, y + r * 0.06, r, shine);
  ctx.fillStyle = COLORS.leaf;
  ctx.beginPath();
  ctx.ellipse(x + r * 0.32, y - r * 0.92, r * 0.36, r * 0.17, -0.6, 0, Math.PI * 2);
  ctx.fill();
}

function drawParticles(size) {
  for (const p of state.particles) {
    ctx.globalAlpha = Math.max(0, p.life / p.span);
    circle(p.x * size, p.y * size, size * 0.1, p.color);
  }
  ctx.globalAlpha = 1;
}

function draw(now = performance.now()) {
  const size = canvas.width / SIZE;
  ctx.drawImage(backdrop, 0, 0);
  drawApple(size, now);
  drawSnake(size);
  drawParticles(size);
}

// ---------- Animation ----------

function burst([x, y]) {
  for (let i = 0; i < 12; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 4;
    const span = 0.35 + Math.random() * 0.2;
    const color = i % 3 ? COLORS.apple : COLORS.leaf;
    state.particles.push({ x: x + 0.5, y: y + 0.5, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: span, span, color });
  }
}

function moveParticles(seconds) {
  for (const p of state.particles) {
    p.x += p.vx * seconds;
    p.y += p.vy * seconds;
    p.life -= seconds;
  }
  state.particles = state.particles.filter((p) => p.life > 0);
}

// The loop only runs while something moves; a paused or finished board is drawn once and left alone
function wake() {
  if (!frameId) {
    state.last = performance.now();
    frameId = requestAnimationFrame(frame);
  }
}

function frame(now) {
  frameId = 0;
  // Capping the build-up stops a stalled frame from replaying a burst of steps the player never saw
  const elapsed = Math.min(now - state.last, 250);
  state.last = now;
  if (state.mode === "running") {
    state.wait += elapsed;
    while (state.mode === "running" && state.wait >= tickMs(state.game.apples)) {
      state.wait -= tickMs(state.game.apples);
      step();
    }
  }
  moveParticles(elapsed / 1000);
  draw(now);
  if (state.mode === "running" || state.mode === "waiting" || state.particles.length) {
    frameId = requestAnimationFrame(frame);
  }
}

// ---------- Playing ----------

function nextTurn() {
  while (state.queue.length) {
    const heading = state.queue.shift();
    if (state.game.canTurn(heading)) {
      return heading;
    }
  }
  return null;
}

function step() {
  const game = state.game;
  const heading = nextTurn();
  if (heading) {
    game.turn(heading);
    state.moves.push([state.tick, heading]);
  }
  const tail = game.body[game.body.length - 1];
  const { ate, died } = game.step();
  state.tick += 1;
  state.stepped = true;
  if (died) {
    // The rules already moved the tail along, so it goes back for the picture of the crash
    state.body = [...game.body, tail];
    state.left = null;
    crash();
    return;
  }
  state.body = game.body;
  state.left = ate ? null : tail;
  if (ate) {
    arcade.setScore(game.apples);
    arcade.tone(660 + Math.min(game.apples, 30) * 20, 0.08, { type: "triangle", volume: 0.1 });
    burst(game.body[0]);
  }
  if (game.over) {
    // Every cell is snake: the board is full and the round is won
    arcade.banner("You filled the board!");
    arcade.tune([523, 659, 784, 1047], 0.09);
    finish();
  }
}

function crash() {
  state.crashed = true;
  arcade.shake();
  arcade.tone(330, 0.45, { type: "sawtooth", slide: 0.35, volume: 0.07 });
  finish();
}

function finish() {
  state.mode = "over";
  draw();
  // The player may end this round and start another during the wait, and this one's results must not end that
  const ended = state.game;
  setTimeout(() => {
    if (state.game === ended) {
      arcade.over(ended.apples, proof());
    }
  }, CRASH_MS);
}

function proof() {
  return { moves: state.moves, ticks: state.tick };
}

function play(seed) {
  state.game = new SnakeGame(seed);
  Object.assign(state, {
    mode: "waiting",
    queue: [],
    moves: [],
    tick: 0,
    wait: 0,
    stepped: false,
    crashed: false,
    body: state.game.body,
    left: null,
    particles: [],
  });
  arcade.hint("Press an arrow key or swipe to start");
  wake();
}

function pause() {
  if (state.mode === "waiting" || state.mode === "running") {
    state.pausedFrom = state.mode;
    state.mode = "paused";
  }
}

function resume() {
  if (state.mode === "paused") {
    state.mode = state.pausedFrom;
    wake();
  }
}

function stop() {
  state.mode = "over";
  return { score: state.game.apples, proof: proof() };
}

// The snake waits for the player's first direction, so a round never starts before they're ready.
// Only real turns wait in line: a held key or a long swipe repeats the same direction, and those repeats
// would otherwise fill the line and push out the turn that comes after them
function steer(heading) {
  if (state.mode === "waiting") {
    state.mode = "running";
    state.wait = 0;
    arcade.hint("");
  } else if (state.mode !== "running" || state.queue.length >= QUEUE_LIMIT) {
    return;
  }
  const facing = state.queue.length ? state.queue[state.queue.length - 1] : state.game.heading;
  if (heading !== facing && heading !== OPPOSITE[facing]) {
    state.queue.push(heading);
  }
}

// ---------- Input ----------

window.addEventListener("keydown", (event) => {
  const heading = KEYS[event.key.toLowerCase()];
  if (heading) {
    event.preventDefault();
    steer(heading);
  }
});

stage.addEventListener("pointerdown", (event) => {
  state.swipe = { x: event.clientX, y: event.clientY };
});

window.addEventListener("pointermove", (event) => {
  if (!state.swipe) {
    return;
  }
  const dx = event.clientX - state.swipe.x;
  const dy = event.clientY - state.swipe.y;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_DISTANCE) {
    return;
  }
  steer(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "R" : "L") : dy > 0 ? "D" : "U");
  // Keep tracking from here, so one long swipe can turn twice (right, then down)
  state.swipe = { x: event.clientX, y: event.clientY };
});

window.addEventListener("pointerup", () => {
  state.swipe = null;
});

// ---------- Setup ----------

function resize() {
  const room = Math.min(stage.clientWidth, stage.clientHeight) - 24;
  const cells = Math.max(8, Math.floor(room / SIZE));
  const px = cells * SIZE;
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${px}px`;
  canvas.style.height = `${px}px`;
  canvas.width = Math.round(px * dpr);
  canvas.height = Math.round(px * dpr);
  paintBackdrop();
  draw();
}

const arcade = await startArcade({
  title: "Snake",
  icon: "icon.svg",
  accent: "#2f855a",
  help: "Eat apples to grow longer and faster. Hitting a wall or your own tail ends the round.",
  controls: [
    ["Arrow keys / WASD", "Steer"],
    ["Swipe", "Steer on a touch screen"],
  ],
  play,
  pause,
  resume,
  stop,
});

// Follows the play area, which also changes when the window or the Discord frame does
new ResizeObserver(resize).observe(stage);
