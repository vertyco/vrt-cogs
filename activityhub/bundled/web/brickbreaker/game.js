import { startArcade } from "activityhub/arcade.js";

// Logical playfield size; the canvas is scaled to fit whatever frame Discord gives us
const W = 480;
const H = 640;
const TOP_WALL = 52;
// Thick enough to see against Discord's dark background, and thin enough to clear the brick grid
const SIDE_WALL = 6;
const COLS = 10;
const BRICK_W = 42;
const BRICK_H = 18;
const GAP = 4;
const GRID_LEFT = (W - (COLS * BRICK_W + (COLS - 1) * GAP)) / 2;
const GRID_TOP = 76;
const PADDLE_W = 84;
const WIDE_PADDLE_W = 128;
const PADDLE_H = 12;
const PADDLE_Y = H - 48;
const PADDLE_KEY_SPEED = 620;
const BALL_R = 6;
const TRAIL_LENGTH = 6;
const MAX_BALLS = 9;
const LIVES = 3;
const MAX_LIVES = 5;
const BASE_SPEED = 320;
const SPEED_PER_LEVEL = 25;
const MAX_SPEED = 620;
const MAX_BOUNCE = (60 * Math.PI) / 180;
const MIN_VERTICAL = 0.3;
const READY_HINT = "Click, tap or press Space to launch";

// Score values, mirrored in bundled/bricks.py
const POINTS_PER_BRICK = 10;
const POINTS_PER_LEVEL = 100;

// Power-ups fall as capsules from some broken bricks and work when the paddle catches them
const DROP_CHANCE = 1 / 8;
const CAPSULE_W = 36;
const CAPSULE_H = 16;
const CAPSULE_SPEED = 140;
const WIDE_SECONDS = 15;
const SLOW_SECONDS = 10;
const SLOW_FACTOR = 0.7;
// How far each extra ball from a multi-ball turns away from the ball it splits from, in radians
const SPLIT_ANGLE = 0.45;
// weight: how often a kind drops compared to the others
const POWERS = {
  wide: { letter: "W", color: "#63b3ed", weight: 3, title: "Wide paddle" },
  multi: { letter: "M", color: "#b794f4", weight: 3, title: "Multi-ball", subtitle: "+2 balls" },
  slow: { letter: "S", color: "#68d391", weight: 2, title: "Slow ball" },
  life: { letter: "+", color: "#fc8181", weight: 1, title: "Extra life" },
};

// The middle color of each brick, used for its particles
const COLORS = { 1: "#4fd1c5", 2: "#f6ad55", 3: "#f56565", solid: "#8a97ab" };

const stage = document.getElementById("stage");
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
// The background, grid and walls never change, so they are painted once per size and copied each frame
const backdrop = document.createElement("canvas");
const back = backdrop.getContext("2d");

const game = {
  mode: "idle", // idle | ready | playing | paused | over
  levels: [],
  level: 0,
  levelsCleared: 0,
  bricks: 0,
  score: 0,
  lives: LIVES,
  speed: BASE_SPEED,
  grid: [],
  paddle: { x: W / 2, w: PADDLE_W },
  balls: [],
  capsules: [],
  effects: { wide: 0, slow: 0 }, // seconds left on each timed power-up
  particles: [],
  keys: { left: false, right: false },
  combo: 0, // bricks broken since a ball last touched the paddle; raises the break sound's pitch
  pausedFrom: "ready", // the mode to go back to after a pause
};

// ---------- Paints ----------

// Gradients are made once in each shape's own coordinates, and each shape is drawn after moving there
function verticalGradient(height, colors) {
  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  colors.forEach((color, i) => gradient.addColorStop(i / (colors.length - 1), color));
  return gradient;
}

function glowGradient(radius, color) {
  const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, radius);
  gradient.addColorStop(0, color);
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  return gradient;
}

const PAINT = {
  bricks: {
    1: verticalGradient(BRICK_H, ["#9decdf", "#4fd1c5", "#2a9d92"]),
    2: verticalGradient(BRICK_H, ["#fcd9a0", "#f6ad55", "#c97a26"]),
    3: verticalGradient(BRICK_H, ["#fdbcbc", "#f56565", "#c43838"]),
    solid: verticalGradient(BRICK_H, ["#e2e8f0", "#8a97ab", "#4a5568"]),
  },
  paddle: verticalGradient(PADDLE_H, ["#ffffff", "#cbd5e0", "#718096"]),
  ballGlow: glowGradient(BALL_R * 3, "rgba(254,252,191,0.6)"),
  slowGlow: glowGradient(BALL_R * 3, "rgba(104,211,145,0.75)"),
  capsuleGlow: glowGradient(CAPSULE_W * 0.8, "rgba(255,255,255,0.22)"),
};

// ---------- Sound ----------

const sounds = {
  launch: () => arcade.tone(330, 0.12, { type: "triangle", slide: 2 }),
  wall: () => arcade.tone(300, 0.04, { type: "triangle", volume: 0.05 }),
  paddle: () => arcade.tone(220, 0.07, { volume: 0.07 }),
  solid: () => arcade.tone(140, 0.08, { type: "sawtooth", volume: 0.05 }),
  crack: () => arcade.tone(600, 0.05, { volume: 0.05 }),
  // Each break in a row climbs one semitone, so long rallies sound like a rising scale
  break: () => arcade.tone(523 * 2 ** (Math.min(game.combo, 24) / 12), 0.1, { type: "triangle", volume: 0.1 }),
  power: () => arcade.tune([659, 880, 1319], 0.05, 0.1),
  lose: () => arcade.tone(330, 0.45, { type: "sawtooth", slide: 0.35, volume: 0.07 }),
  level: () => arcade.tune([523, 659, 784, 1047], 0.09),
  over: () => arcade.tune([392, 330, 262, 196], 0.2, 0.28),
};

// ---------- Rounds ----------

function proof() {
  return { bricks: game.bricks, levels_cleared: game.levelsCleared };
}

function play() {
  game.level = 0;
  game.levelsCleared = 0;
  game.bricks = 0;
  game.score = 0;
  game.lives = LIVES;
  game.particles = [];
  buildGrid();
  endPowers();
  enterReady();
}

function pause() {
  game.pausedFrom = game.mode;
  game.mode = "paused";
}

function resume() {
  game.mode = game.pausedFrom;
  wake();
}

function stop() {
  game.mode = "over";
  arcade.hint("");
  return { score: game.score, proof: proof() };
}

// ---------- Game state ----------

function buildGrid() {
  const layout = game.levels[game.level % game.levels.length];
  game.grid = [];
  layout.forEach((row, r) => {
    [...row].forEach((char, c) => {
      if (char === ".") {
        return;
      }
      const solid = char === "#";
      const hp = solid ? 0 : Number(char);
      game.grid.push({
        x: GRID_LEFT + c * (BRICK_W + GAP),
        y: GRID_TOP + r * (BRICK_H + GAP),
        solid,
        hp,
        maxHp: hp,
        dead: false,
        flash: 0,
        cracks: [],
      });
    });
  });
  game.speed = Math.min(MAX_SPEED, BASE_SPEED + game.level * SPEED_PER_LEVEL);
}

function newBall(x, y, vx = 0, vy = 0) {
  return { x, y, vx, vy, trail: [] };
}

// One ball resting on the paddle
function resetBall() {
  game.combo = 0;
  game.balls = [newBall(game.paddle.x, PADDLE_Y - BALL_R - 1)];
}

function enterReady() {
  resetBall();
  game.mode = "ready";
  arcade.hint(READY_HINT);
  wake();
}

function launch() {
  const angle = (Math.random() - 0.5) * 0.6;
  const ball = game.balls[0];
  ball.vx = ballSpeed() * Math.sin(angle);
  ball.vy = -ballSpeed() * Math.cos(angle);
  game.mode = "playing";
  arcade.hint("");
  sounds.launch();
  wake();
}

function hitBrick(brick) {
  brick.flash = 0.12;
  if (brick.solid) {
    sounds.solid();
    return;
  }
  brick.hp -= 1;
  if (brick.hp > 0) {
    addCrack(brick);
    sounds.crack();
    return;
  }
  game.combo += 1;
  sounds.break();
  brick.dead = true;
  game.bricks += 1;
  game.score += POINTS_PER_BRICK;
  arcade.setScore(game.score);
  burst(brick.x + BRICK_W / 2, brick.y + BRICK_H / 2, COLORS[brick.maxHp], 14);
  if (Math.random() < DROP_CHANCE) {
    game.capsules.push({ x: brick.x + BRICK_W / 2, y: brick.y + BRICK_H / 2, kind: pickPower() });
  }
  if (game.grid.every((b) => b.solid || b.dead)) {
    levelClear();
  }
}

// A jagged line across the brick, so a brick that took a hit looks damaged
function addCrack(brick) {
  let x = 8 + Math.random() * (BRICK_W - 16);
  const points = [[x, 0]];
  for (let y = 4; y < BRICK_H; y += 4) {
    x += (Math.random() - 0.5) * 9;
    points.push([x, y]);
  }
  points.push([x, BRICK_H]);
  brick.cracks.push(points);
}

function levelClear() {
  game.levelsCleared += 1;
  game.score += POINTS_PER_LEVEL;
  arcade.setScore(game.score);
  game.level += 1;
  sounds.level();
  arcade.banner("Level cleared!", `+${POINTS_PER_LEVEL} points. Level ${game.level + 1} is next.`);
  arcade.shake();
  buildGrid();
  endPowers();
  enterReady();
}

function loseLife() {
  game.lives -= 1;
  endPowers();
  arcade.shake();
  if (game.lives > 0) {
    sounds.lose();
    enterReady();
    return;
  }
  game.mode = "over";
  arcade.hint("");
  sounds.over();
  arcade.over(game.score, proof());
}

function burst(x, y, color, count) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 60 + Math.random() * 160;
    const size = 2 + Math.random() * 3;
    game.particles.push({ x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, life: 0.6, color, size });
  }
}

// ---------- Power-ups ----------

function ballSpeed() {
  return game.speed * (game.effects.slow > 0 ? SLOW_FACTOR : 1);
}

function setBallSpeeds() {
  const speed = ballSpeed();
  for (const ball of game.balls) {
    const now = Math.hypot(ball.vx, ball.vy);
    if (now > 0) {
      ball.vx *= speed / now;
      ball.vy *= speed / now;
    }
  }
}

function pickPower() {
  const kinds = Object.keys(POWERS).filter((kind) => kind !== "life" || game.lives < MAX_LIVES);
  let roll = Math.random() * kinds.reduce((sum, kind) => sum + POWERS[kind].weight, 0);
  for (const kind of kinds) {
    roll -= POWERS[kind].weight;
    if (roll < 0) {
      return kind;
    }
  }
  return kinds[0];
}

function catchPower(kind) {
  const power = POWERS[kind];
  sounds.power();
  arcade.banner(power.title, power.subtitle);
  burst(game.paddle.x, PADDLE_Y, power.color, 10);
  if (kind === "wide") {
    game.effects.wide = WIDE_SECONDS;
  } else if (kind === "slow") {
    game.effects.slow = SLOW_SECONDS;
    setBallSpeeds();
  } else if (kind === "life") {
    game.lives = Math.min(MAX_LIVES, game.lives + 1);
  } else {
    splitBalls();
  }
}

// Two more balls leave from the first one, turned to either side of its path
function splitBalls() {
  const from = game.balls[0];
  for (const turn of [-SPLIT_ANGLE, SPLIT_ANGLE]) {
    if (game.balls.length >= MAX_BALLS) {
      return;
    }
    const cos = Math.cos(turn);
    const sin = Math.sin(turn);
    const ball = newBall(from.x, from.y, from.vx * cos - from.vy * sin, from.vx * sin + from.vy * cos);
    keepVertical(ball);
    game.balls.push(ball);
  }
}

// Power-ups last until their time runs out, a life is lost or the level is cleared
function endPowers() {
  game.effects.wide = 0;
  game.effects.slow = 0;
  game.capsules = [];
}

function tickPowers(dt) {
  game.effects.wide = Math.max(0, game.effects.wide - dt);
  if (game.effects.slow > 0) {
    game.effects.slow = Math.max(0, game.effects.slow - dt);
    if (game.effects.slow === 0) {
      setBallSpeeds();
    }
  }
  const paddle = game.paddle;
  for (const capsule of game.capsules) {
    capsule.y += CAPSULE_SPEED * dt;
    const caught =
      capsule.y + CAPSULE_H / 2 >= PADDLE_Y &&
      capsule.y - CAPSULE_H / 2 <= PADDLE_Y + PADDLE_H &&
      Math.abs(capsule.x - paddle.x) <= paddle.w / 2 + CAPSULE_W / 2;
    if (caught) {
      capsule.done = true;
      catchPower(capsule.kind);
    } else if (capsule.y - CAPSULE_H / 2 > H) {
      capsule.done = true;
    }
  }
  game.capsules = game.capsules.filter((capsule) => !capsule.done);
}

// ---------- Physics ----------

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function paddleLimits() {
  const half = game.paddle.w / 2;
  return [SIDE_WALL + half, W - SIDE_WALL - half];
}

// Keep a ball from settling into a near-flat path that takes forever to come back down
function keepVertical(ball) {
  const speed = ballSpeed();
  const min = speed * MIN_VERTICAL;
  if (Math.abs(ball.vy) >= min) {
    return;
  }
  ball.vy = (Math.sign(ball.vy) || -1) * min;
  ball.vx = (Math.sign(ball.vx) || 1) * Math.sqrt(speed ** 2 - min ** 2);
}

function bounceWalls(ball) {
  if (ball.x < SIDE_WALL + BALL_R) {
    ball.x = SIDE_WALL + BALL_R;
    ball.vx = Math.abs(ball.vx);
    sounds.wall();
  } else if (ball.x > W - SIDE_WALL - BALL_R) {
    ball.x = W - SIDE_WALL - BALL_R;
    ball.vx = -Math.abs(ball.vx);
    sounds.wall();
  }
  if (ball.y < TOP_WALL + BALL_R) {
    ball.y = TOP_WALL + BALL_R;
    ball.vy = Math.abs(ball.vy);
    sounds.wall();
  }
}

function bouncePaddle(ball) {
  const paddle = game.paddle;
  const touching =
    ball.vy > 0 &&
    ball.y + BALL_R >= PADDLE_Y &&
    ball.y - BALL_R <= PADDLE_Y + PADDLE_H &&
    Math.abs(ball.x - paddle.x) <= paddle.w / 2 + BALL_R;
  if (!touching) {
    return;
  }
  // Where the ball lands on the paddle sets the angle it leaves at: edges send it out wide
  const offset = clamp((ball.x - paddle.x) / (paddle.w / 2), -1, 1);
  const angle = offset * MAX_BOUNCE;
  ball.vx = ballSpeed() * Math.sin(angle);
  ball.vy = -ballSpeed() * Math.cos(angle);
  ball.y = PADDLE_Y - BALL_R;
  game.combo = 0;
  sounds.paddle();
}

function bounceBricks(ball) {
  for (const brick of game.grid) {
    if (brick.dead) {
      continue;
    }
    const nearX = clamp(ball.x, brick.x, brick.x + BRICK_W);
    const nearY = clamp(ball.y, brick.y, brick.y + BRICK_H);
    if ((ball.x - nearX) ** 2 + (ball.y - nearY) ** 2 > BALL_R ** 2) {
      continue;
    }
    // Push the ball out along whichever side it dug into least, and flip that direction
    const dx = ball.x - (brick.x + BRICK_W / 2);
    const dy = ball.y - (brick.y + BRICK_H / 2);
    const overlapX = BALL_R + BRICK_W / 2 - Math.abs(dx);
    const overlapY = BALL_R + BRICK_H / 2 - Math.abs(dy);
    if (overlapX < overlapY) {
      ball.vx = (Math.sign(dx) || 1) * Math.abs(ball.vx);
      ball.x += (Math.sign(dx) || 1) * overlapX;
    } else {
      ball.vy = (Math.sign(dy) || 1) * Math.abs(ball.vy);
      ball.y += (Math.sign(dy) || 1) * overlapY;
    }
    keepVertical(ball);
    hitBrick(brick);
    return;
  }
}

function stepBall(ball, dt) {
  ball.x += ball.vx * dt;
  ball.y += ball.vy * dt;
  bounceWalls(ball);
  bouncePaddle(ball);
  bounceBricks(ball);
}

// A ball that fell past the paddle is gone; the life is only lost with the last one
function dropFallen() {
  const kept = game.balls.filter((ball) => ball.y - BALL_R <= H);
  if (kept.length === game.balls.length) {
    return;
  }
  game.balls = kept;
  if (!kept.length) {
    loseLife();
  }
}

function moveBalls(dt) {
  // Move in small slices so a fast ball can't skip through a brick between frames
  const steps = Math.ceil((ballSpeed() * dt) / (BALL_R * 0.5));
  for (let i = 0; i < steps && game.mode === "playing"; i++) {
    for (const ball of game.balls) {
      stepBall(ball, dt / steps);
      if (game.mode !== "playing") {
        return;
      }
    }
    dropFallen();
  }
  for (const ball of game.balls) {
    ball.trail.push([ball.x, ball.y]);
    if (ball.trail.length > TRAIL_LENGTH) {
      ball.trail.shift();
    }
  }
}

function movePaddle(dt) {
  const paddle = game.paddle;
  // The paddle grows and shrinks over a moment instead of jumping
  const width = game.effects.wide > 0 ? WIDE_PADDLE_W : PADDLE_W;
  paddle.w += (width - paddle.w) * Math.min(1, dt * 12);
  const keyDir = (game.keys.right ? 1 : 0) - (game.keys.left ? 1 : 0);
  const [low, high] = paddleLimits();
  paddle.x = clamp(paddle.x + keyDir * PADDLE_KEY_SPEED * dt, low, high);
}

function update(dt) {
  if (game.mode === "paused") {
    return;
  }
  if (game.mode === "ready" || game.mode === "playing") {
    movePaddle(dt);
  }
  if (game.mode === "ready") {
    game.balls[0].x = game.paddle.x;
  } else if (game.mode === "playing") {
    tickPowers(dt);
    moveBalls(dt);
  }
  for (const brick of game.grid) {
    brick.flash = Math.max(0, brick.flash - dt);
  }
  for (const p of game.particles) {
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    p.vy += 400 * dt;
    p.life -= dt;
  }
  game.particles = game.particles.filter((p) => p.life > 0);
}

// ---------- Drawing ----------

function roundRect(x, y, w, h, r, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

function text(value, x, y, size, color = "#e2e8f0", align = "center") {
  ctx.font = `700 ${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.fillText(value, x, y);
}

// The background, a faint grid, a red glow under the paddle where balls are lost, and the three walls.
// The walls have a bright inner edge where the ball bounces, so the playfield's edge is easy to see
function paintBackdrop() {
  backdrop.width = canvas.width;
  backdrop.height = canvas.height;
  back.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
  const sky = back.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, "#161b36");
  sky.addColorStop(1, "#07080f");
  back.fillStyle = sky;
  back.fillRect(0, 0, W, H);
  back.fillStyle = "rgba(0,0,0,0.35)";
  back.fillRect(0, 0, W, TOP_WALL - 2);

  back.strokeStyle = "rgba(160,174,192,0.05)";
  back.lineWidth = 1;
  back.beginPath();
  for (let x = SIDE_WALL + 24; x < W - SIDE_WALL; x += 24) {
    back.moveTo(x, TOP_WALL);
    back.lineTo(x, H);
  }
  for (let y = TOP_WALL + 24; y < H; y += 24) {
    back.moveTo(SIDE_WALL, y);
    back.lineTo(W - SIDE_WALL, y);
  }
  back.stroke();

  const danger = back.createLinearGradient(0, H - 40, 0, H);
  danger.addColorStop(0, "rgba(245,101,101,0)");
  danger.addColorStop(1, "rgba(245,101,101,0.12)");
  back.fillStyle = danger;
  back.fillRect(SIDE_WALL, H - 40, W - SIDE_WALL * 2, 40);

  // Each side wall is darker at the outside and lighter toward the playfield
  const wall = back.createLinearGradient(0, 0, SIDE_WALL, 0);
  wall.addColorStop(0, "#2d3748");
  wall.addColorStop(1, "#5a6578");
  back.fillStyle = "#4a5568";
  back.fillRect(0, TOP_WALL - 2, W, 2);
  back.fillStyle = wall;
  back.fillRect(0, TOP_WALL - 2, SIDE_WALL, H);
  back.save();
  back.translate(W, 0);
  back.scale(-1, 1);
  back.fillRect(0, TOP_WALL - 2, SIDE_WALL, H);
  back.restore();
  back.fillStyle = "#a0aec0";
  back.fillRect(SIDE_WALL - 1, TOP_WALL, 1, H);
  back.fillRect(W - SIDE_WALL, TOP_WALL, 1, H);
  back.fillRect(SIDE_WALL - 1, TOP_WALL - 1, W - SIDE_WALL * 2 + 2, 1);
}

function glow(x, y, paint, radius) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = paint;
  ctx.fillRect(-radius, -radius, radius * 2, radius * 2);
  ctx.restore();
}

function drawHud() {
  text(`LEVEL ${game.level + 1}`, 16, 26, 14, "#e2e8f0", "left");
  // Lives as small balls, from the right edge in
  for (let i = 0; i < game.lives; i++) {
    const x = W - 18 - i * 16;
    glow(x, 26, PAINT.ballGlow, BALL_R * 3);
    ctx.fillStyle = "#fefcbf";
    ctx.beginPath();
    ctx.arc(x, 26, 5, 0, Math.PI * 2);
    ctx.fill();
  }
  drawTimers();
}

// A shrinking bar for each timed power-up, in the middle of the top strip
function drawTimers() {
  const timers = [
    ["wide", WIDE_SECONDS],
    ["slow", SLOW_SECONDS],
  ].filter(([kind]) => game.effects[kind] > 0);
  timers.forEach(([kind, total], i) => {
    const y = timers.length === 1 ? 26 : 18 + i * 16;
    const power = POWERS[kind];
    roundRect(W / 2 - 74, y - 6, 18, 12, 6, power.color);
    text(power.letter, W / 2 - 65, y + 0.5, 9, "#1a202c");
    roundRect(W / 2 - 50, y - 3, 124, 6, 3, "rgba(255,255,255,0.1)");
    roundRect(W / 2 - 50, y - 3, 124 * (game.effects[kind] / total), 6, 3, power.color);
  });
}

function drawBrick(brick) {
  ctx.save();
  ctx.translate(brick.x, brick.y);
  roundRect(0, 0, BRICK_W, BRICK_H, 4, brick.solid ? PAINT.bricks.solid : PAINT.bricks[brick.hp]);
  roundRect(3, 2, BRICK_W - 6, 5, 2.5, "rgba(255,255,255,0.25)");
  ctx.fillStyle = "rgba(0,0,0,0.22)";
  ctx.fillRect(4, BRICK_H - 3, BRICK_W - 8, 2);
  if (brick.solid) {
    // A sheen stripe and two rivets read as metal that can't be broken
    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.beginPath();
    ctx.moveTo(14, 2);
    ctx.lineTo(22, 2);
    ctx.lineTo(15, BRICK_H - 2);
    ctx.lineTo(7, BRICK_H - 2);
    ctx.fill();
    roundRect(BRICK_W - 9, BRICK_H / 2 - 2, 4, 4, 2, "rgba(26,32,44,0.6)");
    roundRect(5, BRICK_H / 2 - 2, 4, 4, 2, "rgba(26,32,44,0.6)");
  } else {
    drawDamage(brick);
  }
  if (brick.flash > 0) {
    roundRect(0, 0, BRICK_W, BRICK_H, 4, `rgba(255,255,255,${brick.flash * 5})`);
  }
  ctx.restore();
}

// Pips count the hits a brick still takes, and cracks show the hits it already took
function drawDamage(brick) {
  if (brick.maxHp > 1) {
    for (let i = 0; i < brick.hp; i++) {
      roundRect(BRICK_W - 10 - i * 7, BRICK_H / 2 - 2, 4, 4, 2, "rgba(26,32,44,0.45)");
    }
  }
  if (!brick.cracks.length) {
    return;
  }
  ctx.strokeStyle = "rgba(26,16,16,0.6)";
  ctx.lineWidth = 1.3;
  ctx.lineJoin = "round";
  ctx.beginPath();
  for (const crack of brick.cracks) {
    crack.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  }
  ctx.stroke();
}

function drawCapsule(capsule) {
  const power = POWERS[capsule.kind];
  ctx.save();
  ctx.translate(capsule.x, capsule.y);
  ctx.fillStyle = PAINT.capsuleGlow;
  ctx.fillRect(-CAPSULE_W, -CAPSULE_W, CAPSULE_W * 2, CAPSULE_W * 2);
  roundRect(-CAPSULE_W / 2, -CAPSULE_H / 2, CAPSULE_W, CAPSULE_H, CAPSULE_H / 2, power.color);
  roundRect(-CAPSULE_W / 2 + 4, -CAPSULE_H / 2 + 2, CAPSULE_W - 8, 4, 2, "rgba(255,255,255,0.45)");
  ctx.strokeStyle = "rgba(255,255,255,0.7)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(-CAPSULE_W / 2 + 0.5, -CAPSULE_H / 2 + 0.5, CAPSULE_W - 1, CAPSULE_H - 1, CAPSULE_H / 2);
  ctx.stroke();
  text(power.letter, 0, 1, 11, "#1a202c");
  ctx.restore();
}

function drawPaddle() {
  const paddle = game.paddle;
  const left = paddle.x - paddle.w / 2;
  const caps = game.effects.wide > 0 ? POWERS.wide.color : "#ed8936";
  ctx.save();
  ctx.shadowColor = caps;
  ctx.shadowBlur = 14;
  ctx.translate(left, PADDLE_Y);
  roundRect(0, 0, paddle.w, PADDLE_H, 6, PAINT.paddle);
  ctx.restore();
  roundRect(left, PADDLE_Y, 12, PADDLE_H, 6, caps);
  roundRect(left + paddle.w - 12, PADDLE_Y, 12, PADDLE_H, 6, caps);
  roundRect(left + 10, PADDLE_Y + 2, paddle.w - 20, 2, 1, "rgba(255,255,255,0.8)");
}

function drawBall(ball) {
  ball.trail.forEach(([x, y], i) => {
    const share = (i + 1) / (ball.trail.length + 1);
    ctx.globalAlpha = share * 0.35;
    ctx.fillStyle = "#fefcbf";
    ctx.beginPath();
    ctx.arc(x, y, BALL_R * share, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
  glow(ball.x, ball.y, game.effects.slow > 0 ? PAINT.slowGlow : PAINT.ballGlow, BALL_R * 3);
  ctx.fillStyle = "#fefcbf";
  ctx.beginPath();
  ctx.arc(ball.x, ball.y, BALL_R, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(ball.x - 2, ball.y - 2, 2, 0, Math.PI * 2);
  ctx.fill();
}

function draw() {
  ctx.drawImage(backdrop, 0, 0, W, H);
  drawHud();
  for (const brick of game.grid) {
    if (!brick.dead) {
      drawBrick(brick);
    }
  }
  game.capsules.forEach(drawCapsule);
  for (const p of game.particles) {
    ctx.globalAlpha = Math.max(0, p.life / 0.6);
    ctx.fillStyle = p.color;
    ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
  }
  ctx.globalAlpha = 1;
  drawPaddle();
  game.balls.forEach(drawBall);
}

// ---------- Loop ----------

// Frames only run while something moves, so a paused, finished or waiting game costs nothing
let looping = false;
let last = 0;

// Waiting to launch, the paddle only moves while a key is held, it is still growing or shrinking, or the
// pointer moves (which wakes the loop itself)
function moving() {
  if (game.mode === "playing") {
    return true;
  }
  if (game.mode === "paused") {
    return false;
  }
  const settling = Math.abs(game.paddle.w - (game.effects.wide > 0 ? WIDE_PADDLE_W : PADDLE_W)) > 0.5;
  const steering = game.mode === "ready" && (game.keys.left || game.keys.right || settling);
  return steering || game.particles.length > 0;
}

function wake() {
  if (!looping) {
    looping = true;
    last = performance.now();
    requestAnimationFrame(frame);
  }
}

function frame(now) {
  update(Math.min((now - last) / 1000, 1 / 30));
  last = now;
  draw();
  if (moving()) {
    requestAnimationFrame(frame);
  } else {
    looping = false;
  }
}

// ---------- Input ----------

function act() {
  if (game.mode === "ready") {
    launch();
  }
}

function aim(event) {
  if (game.mode !== "ready" && game.mode !== "playing") {
    return;
  }
  const rect = canvas.getBoundingClientRect();
  const [low, high] = paddleLimits();
  game.paddle.x = clamp(((event.clientX - rect.left) / rect.width) * W, low, high);
  wake();
}

window.addEventListener("pointermove", aim);
canvas.addEventListener("pointerdown", (event) => {
  aim(event);
  act();
});

window.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (key === "arrowleft" || key === "a") {
    game.keys.left = true;
    wake();
  } else if (key === "arrowright" || key === "d") {
    game.keys.right = true;
    wake();
  } else if (key === " " || key === "enter") {
    act();
  }
});

window.addEventListener("keyup", (event) => {
  const key = event.key.toLowerCase();
  if (key === "arrowleft" || key === "a") {
    game.keys.left = false;
  } else if (key === "arrowright" || key === "d") {
    game.keys.right = false;
  }
});

// A key held while the frame loses focus never sends its keyup
window.addEventListener("blur", () => {
  game.keys.left = false;
  game.keys.right = false;
});

// ---------- Setup ----------

function resize() {
  const scale = Math.min(stage.clientWidth / W, stage.clientHeight / H);
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${W * scale}px`;
  canvas.style.height = `${H * scale}px`;
  canvas.width = Math.max(1, Math.round(W * scale * dpr));
  canvas.height = Math.max(1, Math.round(H * scale * dpr));
  ctx.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
  paintBackdrop();
  draw();
}

const levelsResp = await fetch(new URL("./levels.json", import.meta.url));
game.levels = await levelsResp.json();
buildGrid();
resetBall();
const arcade = await startArcade({
  title: "Brick Breaker",
  icon: "icon.svg",
  accent: "#c05621",
  help: "Bounce the ball off your paddle and break every brick to clear the level. Catch falling power-ups. You have 3 balls.",
  controls: [
    ["Mouse / finger", "Move the paddle"],
    ["Arrow keys / A D", "Move the paddle"],
    ["Space / click", "Launch the ball"],
  ],
  play,
  pause,
  resume,
  stop,
});
// Follows the play area, which also changes when the window or the Discord frame does
new ResizeObserver(resize).observe(stage);
