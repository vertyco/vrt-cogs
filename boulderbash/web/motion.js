// Boulder Bash's motion: how blocks hop, fall, slide and rain in, tick by tick, with the same whole-pixel maths as
// boulderbash/common/timing.py. The bot counts these ticks to know how long a board is busy; the page plays them,
// so its animation ends as the board takes taps again.

// The same numbers as boulderbash/common/rules.py (tests/test_page.py checks they match)
export const TICK_MS = 1000 / 60;
export const RAIN_STEP_MS = 1000 / 120;
export const MAX_COLORS = 9;
export const STONE = 10;
export const BASE = 11;
export const COUNTDOWN = 2;
export const BOMB = 4;
export const WIPE = 5;
export const SHIFTER = 6;
export const WILD = 7;
export const UNDO = 8;
export const SHUFFLE = 9;
export const HOLD = 10;
export const TRIPLE = 3;
export const REFILL = 1;
export const COUNTDOWN_SHOWN = 15;
export const COUNTDOWN_WARNING = 5;
export const EXTREME_FIRST_ROW = 6;
export const HOP_SPEED = -2;
export const HOP_ACCEL = 2;
export const DROP_SPEED = 6;
export const DROP_ACCEL = 3;
export const SLIDE_SPEED = 1;
export const SLIDE_ACCEL = 4;
export const RAIN_TRIGGER_Y = 10;
export const RAIN_NEXT_TRIGGER = 30;
export const CLEAR_ROW_MS = 25;
export const UNDO_FIRST_FRAME = 2;
export const UNDO_REWIND_FRAME = 25;
export const UNDO_STOMP_FRAME = 45;
export const UNDO_LAST_FRAME = 70;
export const UNDO_FRAME_TICKS = 2;
export const FLYER_START = 140;
export const FLYER_END = 1130;
export const FLYER_SPEED = 6;
export const CHUNK_SCALE = [0.4, 0.35, 0.3, 0.25];
export const CHUNK_VX = [-15, -12, -10, -8, -5, 5, 8, 10, 12, 15];
export const CHUNK_VY = [-14, -15, -18, -17, -16, -13, -12, -19];
export const CHUNK_VY_ADD = 2;
export const CHUNK_DRAG = 0.9;
export const CHUNK_GRAVITY = 1.25;
export const CHUNK_FLOOR = 600;
export const CHUNKS_PER_BLOCK = 2;
// rows, one-board columns, tile width, tile height, board x, board y, two-board columns, right board x
export const ZOOMS = [
  [12, 14, 48, 32, 64, 96, 6, 448],
  [13, 15, 44, 29, 70, 103, 7, 422],
  [14, 16, 42, 28, 64, 88, 7, 442],
  [16, 18, 37, 24, 67, 96, 8, 437],
];
export const EXTREMES = [2, 4];
export const TWO_BOARDS = [3, 4];

export function zoomFor(mode, level) {
  if (EXTREMES.includes(mode) || level <= 2) {
    return 0;
  }
  if (level <= 5) {
    return 1;
  }
  return level <= 9 ? 2 : 3;
}

// Where a board sits on the 800 x 600 stage, and its tile size
export function boardGeometry(mode, level, side) {
  const zoom = zoomFor(mode, level);
  const [rows, cols, tileW, tileH, x, y, twoCols, rightX] = ZOOMS[zoom];
  const two = TWO_BOARDS.includes(mode);
  return { zoom, rows, cols: two ? twoCols : cols, tileW, tileH, x: side ? rightX : x, y };
}

function advance(pos, target, speed, accel, direction) {
  if (direction === 0) {
    return [target, speed, true];
  }
  pos += speed * direction;
  speed += accel;
  if ((direction === 1 && pos >= target) || (direction === -1 && pos <= target)) {
    return [target, speed, true];
  }
  return [pos, speed, false];
}

// One block's motion, as the original kept it: whole pixels, and a speed and a per-tick speed-up on each axis.
// x is from the board's left edge and y is on the stage, as in the original
export class Mover {
  constructor(x, y, view) {
    this.x = this.tx = x;
    this.y = this.ty = y;
    this.vx = this.ax = this.dx = 0;
    this.vy = this.ay = this.dy = 0;
    this.atX = this.atY = true;
    this.moving = false;
    this.killed = false;
    this.view = view;
  }

  step() {
    if (!this.atX) {
      [this.x, this.vx, this.atX] = advance(this.x, this.tx, this.vx, this.ax, this.dx);
    }
    if (!this.atY) {
      [this.y, this.vy, this.atY] = advance(this.y, this.ty, this.vy, this.ay, this.dy);
    }
    if (this.atX && this.atY) {
      this.moving = false;
    }
  }
}

// A board's blocks as the original moved them. It lasts the whole level, so blocks still sliding when a move ends
// carry on into the next one, as they did in the original
export class Motion {
  constructor(rows, cols, tileW, tileH, top) {
    this.rows = rows;
    this.cols = cols;
    this.tileW = tileW;
    this.tileH = tileH;
    this.top = top;
    this.grid = Array.from({ length: rows }, () => new Array(cols).fill(null));
    this.onRemove = () => {};
  }

  place(row, col, view) {
    const mover = new Mover(col * this.tileW, this.top + row * this.tileH, view);
    this.grid[row][col] = mover;
    return mover;
  }

  // Remove smashed blocks and step every moving one. True once nothing is moving
  redraw() {
    let still = false;
    for (let col = 0; col < this.cols; col += 1) {
      for (let row = this.rows - 1; row >= 0; row -= 1) {
        const mover = this.grid[row][col];
        if (!mover) {
          continue;
        }
        if (mover.killed) {
          this.grid[row][col] = null;
          this.onRemove(mover);
        } else if (mover.moving) {
          mover.step();
          still = still || mover.moving;
        }
      }
    }
    return !still;
  }

  // Doom a block and make every block above it hop, the nearest at -2 px a tick, the next at -3, and so on
  smash(row, col) {
    const doomed = this.grid[row][col];
    doomed.killed = true;
    let hop = HOP_SPEED;
    for (let above = row - 1; above >= 0; above -= 1) {
      const mover = this.grid[above][col];
      if (mover) {
        mover.moving = true;
        mover.atY = false;
        mover.ty = mover.y;
        mover.dy = 1;
        mover.vy = hop;
        mover.ay = HOP_ACCEL;
        hop -= 1;
      }
    }
    return doomed;
  }

  // Retarget each block to the lowest empty cell below it
  drop(col) {
    for (let row = this.rows - 1; row >= 0; row -= 1) {
      const mover = this.grid[row][col];
      if (mover) {
        if (row === 0 && mover.y < this.top) {
          mover.ty = this.top;
          mover.atY = false;
          mover.moving = true;
        }
        continue;
      }
      for (let above = row - 1; above >= 0; above -= 1) {
        const falling = this.grid[above][col];
        if (falling) {
          this.grid[row][col] = falling;
          this.grid[above][col] = null;
          falling.ty = this.top + row * this.tileH;
          falling.atY = false;
          falling.moving = true;
          break;
        }
      }
    }
  }

  // A Refill block dropping in from above the stage
  dropIn(col, view) {
    const mover = new Mover(col * this.tileW, -this.tileH, view);
    mover.ty = this.top;
    mover.atY = false;
    mover.dy = 1;
    mover.vy = DROP_SPEED;
    mover.ay = DROP_ACCEL;
    mover.moving = true;
    this.grid[0][col] = mover;
    this.drop(col);
    return mover;
  }

  // A whole column moving across, starting slow and speeding up
  slide(src, dst) {
    const direction = dst > src ? 1 : -1;
    for (let row = 0; row < this.rows; row += 1) {
      const mover = this.grid[row][src];
      if (mover) {
        this.grid[row][src] = null;
        this.grid[row][dst] = mover;
        mover.tx = dst * this.tileW;
        mover.dx = direction;
        mover.vx = SLIDE_SPEED;
        mover.ax = SLIDE_ACCEL;
        mover.atX = false;
        mover.moving = true;
      }
    }
  }
}

// FINISHDROP and FINISHMOVE: a tick at a time until everything has landed
function* settle(motion) {
  while (true) {
    yield TICK_MS;
    if (motion.redraw()) {
      return;
    }
  }
}

// One smash, through the original's states from PREPAREKILL back to play. It yields the time to wait before each
// next step, and calls `on` for what the player sees and hears along the way. Mirrors timing.py's move_ticks
export function* playMove(motion, move, extreme, on) {
  yield TICK_MS; // PREPAREKILL
  for (let col = move.first; col < motion.cols; col += 1) {
    yield TICK_MS; // KILLTILES, one column a tick
    for (const [row, c] of move.kills) {
      if (c === col && motion.grid[row][col]) {
        on.smash(motion.smash(row, col), row, col);
      }
    }
    motion.redraw();
    motion.drop(col);
  }
  yield* settle(motion);
  if (move.falls.length) {
    on.sound("drop");
  }
  yield TICK_MS; // AFTERDROP
  if (move.refill.length) {
    const colors = new Map(move.refill.map(([, col, color]) => [col, color]));
    for (let col = 0; col < motion.cols; col += 1) {
      yield TICK_MS;
      motion.redraw();
      if (!motion.grid[0][col] && colors.has(col)) {
        motion.dropIn(col, on.newBlock(colors.get(col)));
      }
    }
    yield* settle(motion);
    on.sound("slide");
    yield TICK_MS; // AFTERDROP again
  }
  if (move.gap) {
    for (const [src, dst] of move.slides) {
      yield TICK_MS; // MOVECOLS, one column a tick
      if (src === move.slides[0][0]) {
        on.sound("slide");
      }
      motion.slide(src, dst);
      motion.redraw();
    }
    yield TICK_MS; // MOVECOLS finds no gap left
    motion.redraw();
    if (extreme) {
      return;
    }
    yield* settle(motion);
  }
  if (!extreme) {
    yield TICK_MS; // CHECKMOVES
  }
}

// A new level's blocks raining in, column by column, bottom to top, at 120 steps a second. When a falling block
// passes y = 10 the block above it starts; one step later the bottom block of the next column starts. Mirrors
// timing.py's rain_in_steps
export function* rainIn(motion, firstRow, extreme, on) {
  const { rows, cols, tileH, top } = motion;
  const drops = new Map();
  for (let row = firstRow; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const mover = motion.grid[row][col];
      if (mover) {
        mover.y = -tileH;
        const drop = { mover, speed: DROP_SPEED, moving: false, passed: false, done: false, landed: false };
        drops.set(`${row},${col}`, { ...drop, trigger: RAIN_TRIGGER_Y });
        on.hide(mover);
      }
    }
  }
  const start = drops.get(`${rows - 1},0`);
  if (!start) {
    return;
  }
  start.moving = true;
  on.sound("level");
  yield TICK_MS; // NEXTLEVEL
  yield TICK_MS; // CREATELEVEL
  yield TICK_MS; // the first step comes a tick later
  while (true) {
    let still = false;
    for (let col = 0; col < cols; col += 1) {
      for (let row = rows - 1; row >= firstRow; row -= 1) {
        still = rainStep(drops, row, col, rows, cols, top + row * tileH, on) || still;
      }
    }
    if (!still) {
      break;
    }
    yield RAIN_STEP_MS;
  }
  if (!extreme) {
    yield TICK_MS; // PREPARELEVEL's move check before play
  }
}

function rainStep(drops, row, col, rows, cols, target, on) {
  const drop = drops.get(`${row},${col}`);
  if (!drop || !drop.moving) {
    return false;
  }
  if (!drop.landed) {
    drop.mover.y += drop.speed;
    drop.speed += DROP_ACCEL;
    if (drop.mover.y >= target) {
      drop.mover.y = target;
      drop.landed = true;
    }
    if (drop.mover.y >= drop.trigger) {
      drop.passed = true;
    }
    on.show(drop.mover);
  }
  drop.moving = !drop.landed;
  if (drop.passed && !drop.done) {
    if (drop.trigger === RAIN_TRIGGER_Y) {
      drop.trigger = RAIN_NEXT_TRIGGER;
      const above = drops.get(`${row - 1},${col}`);
      if (above) {
        above.moving = true;
      }
    } else {
      const next = drops.get(`${rows - 1},${col + 1}`);
      if (col < cols - 1 && next) {
        next.moving = true;
      }
      drop.done = true;
    }
  }
  return drop.moving;
}

// The tick an Undo animation frame lands on, counted from the press
export function undoFrameTick(frame) {
  return (frame - UNDO_FIRST_FRAME) * UNDO_FRAME_TICKS;
}

export function undoTicks() {
  return (UNDO_LAST_FRAME - UNDO_FIRST_FRAME) * UNDO_FRAME_TICKS + 2;
}

// One cell a tick, or the flyer's crossing if that is longer, then the move check
export function shuffleTicks(walk) {
  const crossing = Math.floor((FLYER_END - FLYER_START) / FLYER_SPEED) + 1;
  return Math.max(walk + 1, crossing) + 1;
}
