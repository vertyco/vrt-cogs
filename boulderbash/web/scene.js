// Boulder Bash's drawing, with PixiJS: the backdrop, the boards and their blocks, flying chunks, "+N" pop-ups and the
// characters. The bot decides everything; this plays what it sends, with the original's motion (motion.js), on the
// original's 800 x 600 stage scaled to the screen.
import { Application, Assets, Container, Graphics, Sprite, Text } from "./vendor/pixi.min.mjs";
import {
  CHUNK_DRAG,
  CHUNK_FLOOR,
  CHUNK_GRAVITY,
  CHUNK_SCALE,
  CHUNK_VX,
  CHUNK_VY,
  CHUNK_VY_ADD,
  CHUNKS_PER_BLOCK,
  CLEAR_ROW_MS,
  COUNTDOWN,
  COUNTDOWN_SHOWN,
  COUNTDOWN_WARNING,
  EXTREME_FIRST_ROW,
  EXTREMES,
  FLYER_END,
  FLYER_SPEED,
  FLYER_START,
  MAX_COLORS,
  Motion,
  REFILL,
  SHUFFLE,
  STONE,
  TICK_MS,
  TRIPLE,
  UNDO,
  UNDO_FIRST_FRAME,
  UNDO_LAST_FRAME,
  UNDO_REWIND_FRAME,
  UNDO_STOMP_FRAME,
  WILD,
  WIPE,
  boardGeometry,
  playMove,
  rainIn,
  shuffleTicks,
  undoFrameTick,
  undoTicks,
} from "./motion.js";

const STAGE_W = 800;
const STAGE_H = 600;
// Where the play backdrop's ledge is, which the boards stand on, and the span every board size fits inside
const LEDGE_Y = 477;
const BOARD_SPAN = [60, 740];
const BOARD_TOP = 88;
const BOARD_BOTTOM = 480;
// The chunks' colors, one per block color (the same as the block art's)
const CHUNK_COLORS = [
  0xff9a1f, 0xefe7d2, 0x2b97f5, 0x58c33a, 0xffe13a, 0x3e5866, 0xe0302a, 0x99592a, 0x9da3a7, 0x9da3a7, 0x767c80, 0x232526,
];
const INK = 0x2a1a0e;
const FLOAT_MS = 1000;
const FLOAT_RISE = 46;
// The menu entrance: 50 frames, one every 25 ms, with the crash on frame 12
const ENTRANCE_FRAMES = 50;
const ENTRANCE_FRAME_MS = 25;
const CRASH_FRAME = 12;
const LAUGH_MS = 850;
const LAUGH_EVERY = [20000, 30000];
// The sky flyover: 450 frames, one every 33 ms, every 15 to 25 seconds
const FLYOVER_MS = 450 * 33;
const FLYOVER_EVERY = [15000, 25000];
const CAMEO_MS = 2000;
// Spots on the menu backdrop, given where they are when the picture fills the stage exactly: the ledge the mascot
// stands on, the cliff face it head-butts, the cave paintings that hide the cameo, and where the caveman pops out
const MASCOT_HOME = [140, 515];
const CLIFF_X = 440;
const PAINTINGS = [700, 393];
const PAINTINGS_REACH = 45;
const CAVEMAN_HOME = [700, 417];
const MAMMOTH_HOME = [150, 600];
const SHUFFLE_FLYER_Y = 260;
const FLAP_MS = 140;

function between([low, high]) {
  return low + Math.random() * (high - low);
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function sprite(texture, anchorX = 0.5, anchorY = 0.5) {
  const node = new Sprite(texture);
  node.anchor.set(anchorX, anchorY);
  return node;
}

// One block on a board: its stone, its special block icon and, for a Countdown, its number
class BlockView extends Container {
  constructor(art, color, special, tileW, tileH) {
    super();
    this.art = art;
    this.tileW = tileW;
    this.tileH = tileH;
    this.stone = new Sprite(art.blocks[color]);
    this.stone.width = tileW;
    this.stone.height = tileH;
    this.addChild(this.stone);
    this.icon = null;
    this.count = null;
    this.color = color;
    this.special = 0;
    // When a Countdown or Shifter next fires, on the page's clock
    this.due = null;
    this.shown = null;
    this.setSpecial(special);
  }

  setColor(color) {
    if (color !== this.color) {
      this.color = color;
      this.stone.texture = this.art.blocks[color];
    }
  }

  setSpecial(special) {
    if (special === this.special) {
      return;
    }
    this.special = special;
    this.icon?.destroy();
    this.count?.destroy();
    this.icon = this.count = null;
    this.shown = null;
    if (!special) {
      return;
    }
    const size = this.tileH * 1.25;
    this.icon = sprite(this.art.specials[special]);
    this.icon.width = this.icon.height = size;
    this.icon.position.set(this.tileW / 2, this.tileH / 2);
    this.addChild(this.icon);
    if (special === COUNTDOWN) {
      this.count = new Text({ text: "", style: { ...COUNT_STYLE, fontSize: Math.round(this.tileH * 0.55) } });
      this.count.anchor.set(0.5);
      this.count.position.set(this.tileW / 2, this.tileH * 0.56);
      this.addChild(this.count);
    }
  }
}

const COUNT_STYLE = { fontFamily: "Grandstander", fontWeight: "800", fill: "#2a1a0e" };
const FLOAT_STYLE = {
  fontFamily: "Grandstander",
  fontSize: 30,
  fontWeight: "800",
  fill: "#ffffff",
  stroke: { color: "#2a1a0e", width: 6 },
};

// One board: its blocks, the original's motion for them, and a queue of what to play next. A board takes taps only
// once its queue is empty, as the bot's copy takes them only once idle
class BoardView {
  constructor(scene, side) {
    this.scene = scene;
    this.side = side;
    this.root = new Container();
    this.shadow = new Graphics();
    this.blocks = new Container();
    this.critters = new Container();
    this.root.addChild(this.shadow, this.blocks, this.critters);
    this.motion = null;
    this.geometry = null;
    this.extreme = false;
    this.queue = [];
    this.run = null;
    this.at = 0;
    this.selection = [];
    this.pauseUntil = 0;
    this.holdCritters = [];
  }

  // Rebuild the board from the bot's view of it, at once
  build(mode, view, now) {
    this.extreme = EXTREMES.includes(mode);
    this.geometry = boardGeometry(mode, view.level, this.side);
    const { rows, cols, tileW, tileH, x, y } = this.geometry;
    this.blocks.removeChildren().forEach((child) => child.destroy({ children: true }));
    this.root.position.set(x, 0);
    this.motion = new Motion(rows, cols, tileW, tileH, y);
    this.motion.onRemove = (mover) => mover.view.destroy({ children: true });
    view.grid.forEach((line, row) =>
      line.forEach((cell, col) => {
        if (cell) {
          this.motion.place(row, col, this.newBlock(cell[0], cell[1]));
        }
      }),
    );
    this.setTimers(view.timers, now);
    this.setSelection(view.selection);
    this.setCritters(view.critters);
    this.sync();
  }

  newBlock(color, special = 0) {
    const { tileW, tileH } = this.geometry;
    const view = new BlockView(this.scene.art, color, special, tileW, tileH);
    this.blocks.addChild(view);
    return view;
  }

  cell(row, col) {
    return this.motion?.grid[row]?.[col] || null;
  }

  // Make the drawing match the bot's grid, in case anything drifted. Normally nothing changes
  reconcile(grid) {
    grid.forEach((line, row) =>
      line.forEach((cell, col) => {
        const mover = this.motion.grid[row][col];
        if (!cell && mover) {
          this.motion.grid[row][col] = null;
          mover.view.destroy({ children: true });
        } else if (cell && !mover) {
          this.motion.place(row, col, this.newBlock(cell[0], cell[1]));
        } else if (cell) {
          mover.view.setColor(cell[0]);
          mover.view.setSpecial(cell[1]);
          if (!mover.moving) {
            mover.x = col * this.motion.tileW;
            mover.y = this.motion.top + row * this.motion.tileH;
          }
        }
      }),
    );
  }

  setTimers(timers, now) {
    for (const [row, col, , left] of timers || []) {
      const mover = this.cell(row, col);
      if (mover) {
        mover.view.due = now + left;
      }
    }
  }

  // Undo and Shuffle hold every Countdown and Shifter still while they play, as the bot's copy does
  pauseTimers(ms, now) {
    this.pauseUntil = now + ms;
    this.forEachBlock((mover) => {
      if (mover.view.due !== null) {
        mover.view.due += ms;
      }
    });
  }

  setSelection(cells) {
    this.selection = cells || [];
    const chosen = new Set(this.selection.map(([row, col]) => `${row},${col}`));
    this.forEachBlock((mover, row, col) => {
      mover.view.alpha = chosen.has(`${row},${col}`) ? 0.5 : 1;
    });
  }

  setCritters(critters) {
    this.holdCritters = critters || [];
  }

  forEachBlock(fn) {
    this.motion?.grid.forEach((line, row) => line.forEach((mover, col) => mover && fn(mover, row, col)));
  }

  idle(now) {
    return !this.run && !this.queue.length && now >= this.at;
  }

  // What to play next. `at` is when it may start, on the page's clock
  enqueue(at, run) {
    this.queue.push({ at, run });
  }

  // Step whatever is playing up to now. Blocks still sliding after a move carry on a tick at a time
  pump(now) {
    for (;;) {
      if (!this.run) {
        const next = this.queue.shift();
        if (!next) {
          while (this.motion && this.at + TICK_MS <= now && !this.motion.redraw()) {
            this.at += TICK_MS;
          }
          this.at = Math.max(this.at, now - TICK_MS);
          return;
        }
        this.at = Math.max(this.at, next.at);
        this.run = next.run();
      }
      if (this.at > now) {
        return;
      }
      const step = this.run.next();
      if (step.done) {
        this.run = null;
      } else {
        this.at += step.value;
      }
    }
  }

  // Put every block where its mover is, and count Countdowns down
  sync(now = performance.now()) {
    if (!this.motion) {
      return;
    }
    this.forEachBlock((mover) => {
      mover.view.position.set(mover.x, mover.y);
      if (mover.view.special === COUNTDOWN && mover.view.due !== null) {
        this.showCount(mover.view, now);
      }
    });
    this.drawCritters();
  }

  // A Countdown shows whole seconds left, from 15. Undo and Shuffle freeze it while they play
  showCount(view, now) {
    const left = view.due - Math.max(now, this.pauseUntil);
    const shown = Math.max(0, Math.min(COUNTDOWN_SHOWN, Math.floor(left / 1000)));
    if (shown !== view.shown) {
      if (view.shown !== null && shown < view.shown && shown < COUNTDOWN_WARNING) {
        this.scene.sound("warning");
      }
      view.shown = shown;
      view.count.text = String(shown);
    }
  }

  drawShadow() {
    this.shadow.clear();
    if (!this.motion) {
      return;
    }
    const { rows, cols, tileW, top, tileH } = this.motion;
    const filled = [...Array(cols).keys()].filter((col) => this.motion.grid[rows - 1][col]);
    if (!filled.length) {
      return;
    }
    const left = filled[0] * tileW;
    const right = (filled[filled.length - 1] + 1) * tileW;
    const y = top + rows * tileH;
    this.shadow.ellipse((left + right) / 2, y + 2, (right - left) / 2 + 10, 9).fill({ color: 0x000000, alpha: 0.32 });
  }

  // A tortoise sits on top of each held column
  drawCritters() {
    const { tileW, tileH, rows, top } = this.motion;
    const want = this.holdCritters.map((on, col) => (on ? col : null)).filter((col) => col !== null);
    while (this.critters.children.length < want.length) {
      const critter = sprite(this.scene.art.tortoise, 0.5, 1);
      critter.width = tileW * 1.1;
      critter.scale.y = critter.scale.x;
      this.critters.addChild(critter);
    }
    while (this.critters.children.length > want.length) {
      this.critters.children[this.critters.children.length - 1].destroy();
    }
    want.forEach((col, i) => {
      let y = top + rows * tileH;
      for (let row = 0; row < rows; row += 1) {
        const mover = this.motion.grid[row][col];
        if (mover) {
          y = mover.y;
          break;
        }
      }
      this.critters.children[i].position.set(col * tileW + tileW / 2, y + 2);
    });
  }

  // Which cell a point on the stage is over, or null
  cellAt(x, y) {
    if (!this.geometry) {
      return null;
    }
    const { rows, cols, tileW, tileH, y: top } = this.geometry;
    const col = Math.floor((x - this.geometry.x) / tileW);
    const row = Math.floor((y - top) / tileH);
    return row >= 0 && row < rows && col >= 0 && col < cols ? [row, col] : null;
  }

  center() {
    const { cols, rows, tileW, tileH, x, y } = this.geometry;
    return [x + (cols * tileW) / 2, y + (rows * tileH) / 2];
  }
}

// Chunks thrown by smashed blocks, with the original's numbers: a random push sideways and up, slowing sideways and
// falling under gravity until they drop off the stage
class Chunks {
  constructor(scene) {
    this.scene = scene;
    this.root = new Container();
    this.live = [];
    this.at = 0;
  }

  burst(x, y, color, zoom) {
    const texture = this.scene.art.chunks[color] || this.scene.art.chunks[0];
    for (let i = 0; i < CHUNKS_PER_BLOCK; i += 1) {
      const chunk = sprite(texture);
      chunk.scale.set(CHUNK_SCALE[zoom] * 1.4);
      chunk.position.set(x, y);
      chunk.rotation = Math.random() * Math.PI * 2;
      this.root.addChild(chunk);
      this.live.push({ chunk, vx: pick(CHUNK_VX), vy: pick(CHUNK_VY) + CHUNK_VY_ADD, spin: (Math.random() - 0.5) * 0.5 });
    }
  }

  step(now) {
    if (!this.live.length) {
      this.at = now;
      return;
    }
    while (this.at + TICK_MS <= now) {
      this.at += TICK_MS;
      for (const piece of this.live) {
        piece.chunk.x += piece.vx;
        piece.vx *= CHUNK_DRAG;
        piece.chunk.y += piece.vy;
        piece.vy += CHUNK_GRAVITY;
        piece.chunk.rotation += piece.spin;
      }
      this.live = this.live.filter((piece) => {
        if (piece.chunk.y > CHUNK_FLOOR) {
          piece.chunk.destroy();
          return false;
        }
        return true;
      });
    }
  }
}

class Scene {
  constructor(app, art) {
    this.app = app;
    this.art = art;
    this.backdrop = sprite(art.menu, 0, 0);
    this.world = new Container();
    this.boardLayer = new Container();
    this.chunks = new Chunks(this);
    this.floats = new Container();
    this.cast = new Container();
    this.sky = new Container();
    // The Undo mammoth and the Shuffle pterodactyl pass in front of the blocks, as in the original
    this.front = new Container();
    this.world.addChild(this.sky, this.cast, this.boardLayer, this.chunks.root, this.floats, this.front);
    app.stage.addChild(this.backdrop, this.world);
    this.boards = [];
    this.mode = 0;
    this.screen = "title";
    this.tall = false;
    this.effects = true;
    this.onTap = () => {};
    this.onSound = () => {};
    this.onCameo = () => {};
    this.idleWaiters = [];
    this.makeCast();
    app.stage.eventMode = "static";
    app.stage.hitArea = app.screen;
    app.stage.on("pointerdown", (event) => this.pointer(event));
    app.ticker.add(() => this.frame(performance.now()));
  }

  sound(name, options) {
    this.onSound(name, options);
  }

  // ---------- Layout ----------

  // Wide screens show the whole 800 x 600 stage. A phone held upright fits the boards to its width, between the
  // bars above and below them
  layout({ tall, screen, safe, playArea }) {
    // Pixi follows the window a frame late, so it is sized now, before anything is measured
    this.app.resize();
    this.tall = tall;
    this.screen = screen;
    const width = this.app.screen.width;
    const height = this.app.screen.height;
    const playing = screen === "play";
    let scale;
    let x;
    let y;
    if (!tall) {
      const roomW = width - safe.left - safe.right;
      const roomH = height - safe.top - safe.bottom;
      scale = Math.min(roomW / STAGE_W, roomH / STAGE_H);
      x = safe.left + (roomW - STAGE_W * scale) / 2;
      y = safe.top + (roomH - STAGE_H * scale) / 2;
    } else if (playing) {
      const spanW = BOARD_SPAN[1] - BOARD_SPAN[0];
      const spanH = BOARD_BOTTOM - BOARD_TOP;
      scale = Math.min(width / spanW, playArea.height / spanH);
      x = width / 2 - (scale * (BOARD_SPAN[0] + BOARD_SPAN[1])) / 2;
      // Low in the room left, so the blocks stand near the bottom bar with the sky above them
      const room = playArea.height - spanH * scale;
      y = playArea.top + playArea.height - room * 0.2 - BOARD_BOTTOM * scale;
    } else {
      scale = Math.min(width / 380, height / 700);
      x = width * 0.26 - MASCOT_HOME[0] * scale;
      y = height - safe.bottom - 14 - MASCOT_HOME[1] * scale;
    }
    this.world.scale.set(scale);
    this.world.position.set(x, y);
    this.placeBackdrop(playing ? [STAGE_W / 2, LEDGE_Y] : tall ? MASCOT_HOME : null, scale);
    if (!playing) {
      this.placeCast();
    }
    this.showCast();
  }

  // The backdrop covers the screen. In play and on an upright phone it lines up with the stage at one point (the
  // boards' ledge, or the mascot's spot). Other menus show the bottom of the picture, where the mascot's ledge is,
  // and crop the sky
  placeBackdrop(anchor, scale) {
    const texture = this.screen === "play" ? this.art.play : this.art.menu;
    this.backdrop.texture = texture;
    const width = this.app.screen.width;
    const height = this.app.screen.height;
    if (anchor) {
      const [ax, ay] = anchor;
      const sx = this.world.x + ax * scale;
      const sy = this.world.y + ay * scale;
      this.cover = Math.max(scale, sx / ax, (width - sx) / (STAGE_W - ax), sy / ay, (height - sy) / (STAGE_H - ay));
      this.backdrop.position.set(sx - ax * this.cover, sy - ay * this.cover);
    } else {
      this.cover = Math.max(width / STAGE_W, height / STAGE_H);
      this.backdrop.position.set((width - STAGE_W * this.cover) / 2, height - STAGE_H * this.cover);
    }
    this.backdrop.scale.set((this.cover * STAGE_W) / texture.width);
  }

  // Where a spot on the backdrop is on the stage, given where it is when the picture fills the stage exactly
  onBackdrop([x, y]) {
    const scale = this.world.scale.x;
    return [
      (this.backdrop.x + x * this.cover - this.world.x) / scale,
      (this.backdrop.y + y * this.cover - this.world.y) / scale,
    ];
  }

  // The menu characters follow the backdrop, which grows to cover screens of other shapes than the stage. The
  // mascot moves right if the screen's edge would cut it off, and its leap stops at the screen's edge
  placeCast() {
    const scale = this.world.scale.x;
    const left = -this.world.x / scale;
    const right = (this.app.screen.width - this.world.x) / scale;
    const half = (this.art.triceratops.width * this.mascot.scale.x) / 2;
    const [x, y] = this.onBackdrop(MASCOT_HOME);
    this.mascotHome = [Math.max(x, left + half), y];
    this.cliffX = Math.min(this.onBackdrop([CLIFF_X, 0])[0], right - half);
    this.paintings = this.onBackdrop(PAINTINGS);
    this.paintingsReach = (PAINTINGS_REACH * this.cover) / scale;
    this.caveman.position.set(...this.onBackdrop(CAVEMAN_HOME));
  }

  toStage(event) {
    return this.world.toLocal(event.global);
  }

  pointer(event) {
    const point = this.toStage(event);
    const [px, py] = this.paintings;
    if (this.screen === "title" && Math.hypot(point.x - px, point.y - py) < this.paintingsReach) {
      this.onCameo();
      return;
    }
    if (this.screen !== "play") {
      return;
    }
    for (const board of this.boards) {
      const cell = board.cellAt(point.x, point.y);
      if (cell) {
        this.onTap(board.side, cell[0], cell[1], point);
        return;
      }
    }
  }

  // ---------- The game ----------

  // A whole game from a snapshot: on start, on reconnect, and on a new level. `rain` plays the level's rain-in
  setGame(snapshot, now, rain) {
    this.mode = snapshot.mode;
    this.clearGame();
    for (const view of snapshot.boards) {
      const board = new BoardView(this, view.board);
      this.boards.push(board);
      this.boardLayer.addChild(board.root);
      board.at = now;
      this.startLevel(board, view, now, rain && view.idle > 0);
    }
  }

  startLevel(board, view, now, rain) {
    // The bot keeps a finished board's last blocks, but the page cleared them when it finished
    board.build(this.mode, view.phase === "done" ? { ...view, grid: [] } : view, now);
    if (view.phase === "ending") {
      board.enqueue(now, () => this.clearRows(board, false));
    } else if (rain) {
      board.enqueue(now, () => this.rainBoard(board));
    } else {
      board.at = now + view.idle;
      board.drawShadow();
    }
  }

  *rainBoard(board) {
    const firstRow = board.extreme ? EXTREME_FIRST_ROW : 0;
    yield* rainIn(board.motion, firstRow, board.extreme, {
      hide: (mover) => (mover.view.visible = false),
      show: (mover) => (mover.view.visible = true),
      sound: (name) => this.sound(name),
    });
    board.drawShadow();
  }

  newLevel(view, now) {
    const board = this.boards[view.board];
    board.enqueue(now, () => {
      board.build(this.mode, view, now);
      return this.rainBoard(board);
    });
  }

  // Anything still waiting on the old boards goes with them, and an Undo or Shuffle cut short is put away
  clearGame() {
    while (this.boards.length) {
      this.boards.pop().root.destroy({ children: true });
    }
    this.idleWaiters = [];
    this.mammoth.visible = false;
    this.flyer.visible = false;
    this.onSound("shuffle-stop");
  }

  canTap(side, now) {
    const board = this.boards[side];
    return Boolean(board) && board.idle(now);
  }

  select(side, cells, now) {
    const board = this.boards[side];
    board?.enqueue(now, function* () {
      board.setSelection(cells);
    });
  }

  // Shown at once when the player taps, before the bot answers: the page can work the group out from the board
  previewSelection(side, cells) {
    this.boards[side]?.setSelection(cells);
  }

  groupAt(side, row, col) {
    const board = this.boards[side];
    const start = board?.cell(row, col);
    if (!start || start.view.color >= MAX_COLORS) {
      return [];
    }
    const color = start.view.color;
    const found = [[row, col]];
    const seen = new Set([`${row},${col}`]);
    const stack = [[row, col]];
    while (stack.length) {
      const [r, c] = stack.pop();
      for (const [nr, nc] of [[r, c - 1], [r, c + 1], [r - 1, c], [r + 1, c]]) {
        const key = `${nr},${nc}`;
        const mover = board.cell(nr, nc);
        if (seen.has(key) || !mover) {
          continue;
        }
        seen.add(key);
        if (mover.view.color === color || mover.view.special === WILD) {
          found.push([nr, nc]);
          stack.push([nr, nc]);
        }
      }
    }
    return found;
  }

  blockAt(side, row, col) {
    return this.boards[side]?.cell(row, col)?.view || null;
  }

  move(message, now) {
    const board = this.boards[message.board];
    board.enqueue(now, () => this.playMove(board, message, now));
    this.afterAction(board, message, now);
  }

  *playMove(board, message, now) {
    board.setSelection([]);
    this.moveSounds(message);
    const [row, col] = message.tapped;
    const { tileW, tileH, x, y, zoom } = board.geometry;
    if (message.points && this.mode !== 0) {
      this.float(`+${message.points}`, x + col * tileW + tileW / 2, y + row * tileH);
    }
    const color = message.color;
    yield* playMove(board.motion, message, board.extreme, {
      smash: (mover) => {
        mover.view.visible = false;
        if (this.effects) {
          const chunkColor = color < MAX_COLORS ? color : mover.view.color;
          this.chunks.burst(x + mover.x + tileW / 2, mover.y + tileH / 2, chunkColor, zoom);
        }
      },
      newBlock: (blockColor) => board.newBlock(blockColor),
      sound: (name) => this.sound(name),
    });
    board.reconcile(message.grid);
    board.setTimers(message.timers, now);
    board.setCritters(message.critters);
    board.drawShadow();
  }

  // The original's sounds for what a smash held, at the moment it starts. The tap's own click played on the tap
  moveSounds(message) {
    if (message.bomb) {
      // Once: the original played it twice in the same tick
      this.sound("boom");
    }
    if (message.special === WIPE) {
      this.sound("wipe");
    } else if (message.special === REFILL) {
      this.sound("refill");
    } else if (message.special === TRIPLE) {
      this.sound("bonus");
    }
    if (message.held.length) {
      this.sound("hold");
    }
    if (message.pickups.includes(UNDO)) {
      this.sound("roar", { pan: -0.4 });
    }
    if (message.pickups.includes(SHUFFLE)) {
      this.sound("squawk");
    }
  }

  // A level's end, once the move, timer, Undo or Shuffle that caused it has played
  afterAction(board, message, now) {
    if (message.clear !== null && message.clear !== undefined) {
      board.enqueue(now + message.clear, () => this.clearRows(board, false));
    }
  }

  // The board clears a row every 25 ms from the top. An Extreme overflow blows apart instead, twice as slowly
  *clearRows(board, overflow) {
    if (overflow) {
      this.sound("overflow");
    }
    const { rows, cols, tileW, tileH, x, zoom } = board.geometry;
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const mover = board.motion.grid[row][col];
        if (!mover) {
          continue;
        }
        board.motion.grid[row][col] = null;
        if (overflow && this.effects) {
          this.chunks.burst(x + mover.x + tileW / 2, mover.y + tileH / 2, mover.view.color, zoom);
        }
        mover.view.destroy({ children: true });
      }
      board.setCritters([]);
      board.drawShadow();
      yield overflow ? CLEAR_ROW_MS * 2 : CLEAR_ROW_MS;
    }
    this.sound("popup");
  }

  undo(message, now) {
    const board = this.boards[message.board];
    board.enqueue(now, () => this.playUndo(board, message, now));
    this.afterAction(board, message, now);
  }

  // The mammoth rises, the board rewinds on its frame 25, it stomps on frame 45 and sinks back by frame 70
  *playUndo(board, message, now) {
    board.pauseTimers(message.busy, now);
    this.sound("roar", { pan: -0.4 });
    const total = undoTicks();
    const rewindTick = Math.round(message.rewind / TICK_MS);
    for (let tick = 0; tick < total; tick += 1) {
      const frame = Math.min(UNDO_LAST_FRAME, UNDO_FIRST_FRAME + Math.floor(tick / 2));
      this.poseMammoth(frame);
      if (tick === rewindTick) {
        this.sound("stomp");
        board.reconcile(message.grid);
        board.setSelection([]);
        board.setTimers(message.timers, now);
        board.setCritters(message.critters);
        board.drawShadow();
      }
      if (tick === undoFrameTick(UNDO_STOMP_FRAME)) {
        this.sound("stomp");
        this.shake = 10;
      }
      yield TICK_MS;
    }
    this.mammoth.visible = false;
  }

  poseMammoth(frame) {
    const rise = Math.min(1, (frame - UNDO_FIRST_FRAME) / (UNDO_REWIND_FRAME - UNDO_FIRST_FRAME));
    const sink = Math.max(0, (frame - 60) / (UNDO_LAST_FRAME - 60));
    const stomp = frame >= UNDO_STOMP_FRAME - 6 && frame < UNDO_STOMP_FRAME ? -(UNDO_STOMP_FRAME - frame) * 4 : 0;
    this.mammoth.visible = true;
    this.mammoth.y = MAMMOTH_HOME[1] + 40 - 220 * rise * (1 - sink) + stomp;
  }

  shuffle(message, now) {
    const board = this.boards[message.board];
    board.enqueue(now, () => this.playShuffle(board, message, now));
    this.afterAction(board, message, now);
  }

  // The pterodactyl flies across at 6 px a tick while the swap pass walks one cell a tick
  *playShuffle(board, message, now) {
    board.pauseTimers(message.busy, now);
    board.setSelection([]);
    this.sound("squawk");
    this.onSound("shuffle-start");
    const { cols } = board.motion;
    const swaps = message.swaps;
    const first = swaps.length ? swaps[0][0] * cols + swaps[0][1] : 0;
    const walk = swaps.length ? board.motion.rows * cols - first : 0;
    const total = shuffleTicks(walk);
    let next = 0;
    this.flyer.visible = true;
    for (let tick = 0; tick < total; tick += 1) {
      const x = FLYER_START + FLYER_SPEED * tick;
      this.flyer.position.set(x, SHUFFLE_FLYER_Y + Math.sin(tick / 9) * 10);
      this.flyer.visible = x <= FLYER_END;
      while (next < swaps.length && swaps[next][0] * cols + swaps[next][1] - first === tick) {
        this.swapBlocks(board, swaps[next]);
        next += 1;
      }
      if (tick === walk) {
        this.onSound("shuffle-stop");
      }
      yield TICK_MS;
    }
    this.flyer.visible = false;
    board.reconcile(message.grid);
    board.setTimers(message.timers, now);
    board.drawShadow();
  }

  swapBlocks(board, [row, col, r, c]) {
    const a = board.motion.grid[row][col];
    const b = board.motion.grid[r][c];
    if (a && b) {
      [a.view, b.view] = [b.view, a.view];
    }
  }

  timer(message, now) {
    const board = this.boards[message.board];
    board.enqueue(now, function* () {
      for (const event of message.events) {
        for (const [row, col] of event.cells) {
          const view = board.cell(row, col)?.view;
          if (view && event.kind === "stone") {
            view.setColor(STONE);
            view.setSpecial(0);
            view.due = null;
          } else if (view) {
            view.setColor(event.color);
          }
        }
      }
      board.scene.sound("morph");
      board.reconcile(message.grid);
      board.setSelection(message.selection);
      board.setTimers(message.timers, now);
    });
    this.afterAction(board, message, now);
  }

  // Extreme: every column without a hold moves up a row and a new row fills the bottom
  rise(message, now) {
    const board = this.boards[message.board];
    board.enqueue(now, () => this.playRise(board, message, now));
    if (message.end !== null) {
      board.enqueue(now, () => this.clearRows(board, true));
    }
  }

  *playRise(board, message, now) {
    const motion = board.motion;
    const held = new Set(message.held);
    for (let col = 0; col < motion.cols; col += 1) {
      if (held.has(col)) {
        continue;
      }
      const top = motion.grid[0][col];
      if (top) {
        top.view.destroy({ children: true });
      }
      for (let row = 0; row < motion.rows - 1; row += 1) {
        const mover = motion.grid[row + 1][col];
        motion.grid[row][col] = mover;
        if (mover) {
          mover.y -= motion.tileH;
          mover.ty -= motion.tileH;
        }
      }
      motion.grid[motion.rows - 1][col] = null;
    }
    for (const [col, color, special] of message.new) {
      motion.place(motion.rows - 1, col, board.newBlock(color, special));
    }
    this.sound("rise");
    if (message.bonus) {
      const [cx, cy] = board.center();
      this.float(`+${message.bonus}`, cx, cy);
      this.sound("bonus");
    }
    board.reconcile(message.grid);
    board.setTimers(message.timers, now);
    board.setCritters(message.critters);
    board.drawShadow();
    yield TICK_MS;
  }

  // Runs `fn` once every board has played everything it was sent
  whenIdle(fn) {
    this.idleWaiters.push(fn);
  }

  allIdle(now) {
    return this.boards.every((board) => board.idle(now));
  }

  float(text, x, y) {
    const label = new Text({ text, style: FLOAT_STYLE });
    label.anchor.set(0.5, 1);
    label.position.set(x, y);
    label.born = performance.now();
    label.startY = y;
    this.floats.addChild(label);
  }

  // ---------- The characters ----------

  makeCast() {
    const art = this.art;
    this.mascot = sprite(art.triceratops, 0.5, 1);
    this.mascot.scale.set(0.9);
    this.mascot.position.set(...MASCOT_HOME);
    this.mascotHome = MASCOT_HOME;
    this.cliffX = CLIFF_X;
    this.paintings = PAINTINGS;
    this.paintingsReach = PAINTINGS_REACH;
    this.mascotLaughUntil = 0;
    this.nextLaugh = performance.now() + between(LAUGH_EVERY);
    this.entranceStart = null;
    this.mammoth = sprite(art.mammoth, 0.5, 0);
    this.mammoth.scale.set(0.85);
    this.mammoth.position.set(...MAMMOTH_HOME);
    this.mammoth.visible = false;
    this.flyer = sprite(art.pteroUp);
    this.flyer.scale.set(0.8);
    this.flyer.visible = false;
    this.flock = new Container();
    for (let i = 0; i < 3; i += 1) {
      const bird = sprite(art.pteroUp);
      bird.scale.set(0.32 - i * 0.04);
      bird.position.set(i * 46, i % 2 ? 18 : -6);
      this.flock.addChild(bird);
    }
    this.flock.visible = false;
    this.flyoverStart = null;
    this.nextFlyover = performance.now() + between(FLYOVER_EVERY);
    this.caveman = sprite(art.caveman, 0.5, 1);
    this.caveman.scale.set(0.45);
    this.caveman.position.set(...CAVEMAN_HOME);
    this.caveman.visible = false;
    this.cameoStart = null;
    this.shake = 0;
    this.sky.addChild(this.flock);
    this.cast.addChild(this.caveman, this.mascot);
    this.front.addChild(this.mammoth, this.flyer);
  }

  showCast() {
    const menu = this.screen !== "play";
    this.mascot.visible = menu;
    this.caveman.visible = this.screen === "title" && this.cameoStart !== null;
  }

  // The mascot leaps at the cliff and head-butts it, on the title, mode select and game over screens
  entrance() {
    if (!this.effects) {
      this.entranceStart = null;
      return;
    }
    this.entranceStart = performance.now();
    this.crashed = false;
  }

  cameo() {
    if (this.cameoStart !== null) {
      return false;
    }
    this.cameoStart = performance.now();
    this.caveman.visible = true;
    return true;
  }

  animateMascot(now) {
    const [homeX, homeY] = this.mascotHome;
    const cliff = this.cliffX;
    let x = homeX;
    let y = homeY;
    let turn = 0;
    if (this.entranceStart !== null) {
      const frame = (now - this.entranceStart) / ENTRANCE_FRAME_MS;
      if (frame >= ENTRANCE_FRAMES) {
        this.entranceStart = null;
      } else if (frame < CRASH_FRAME) {
        // Crouch, then leap at the cliff
        const t = Math.max(0, (frame - 3) / (CRASH_FRAME - 3));
        x += (cliff - x) * t;
        y -= Math.sin(t * Math.PI * 0.8) * 120;
        turn = t * 0.3;
      } else {
        if (!this.crashed) {
          this.crashed = true;
          this.sound("crash");
          this.onSound("crash-shake");
        }
        // Bounce back down to the ledge, a little dizzy
        const t = (frame - CRASH_FRAME) / (ENTRANCE_FRAMES - CRASH_FRAME);
        x = cliff + (homeX - cliff) * t;
        y = homeY - 120 * Math.sin((1 - t) * Math.PI * 0.6) * (1 - t);
        turn = 0.3 * (1 - t) * Math.cos(frame);
      }
    } else if (this.mascot.visible && now >= this.nextLaugh) {
      this.nextLaugh = now + between(LAUGH_EVERY);
      this.mascotLaughUntil = now + LAUGH_MS;
      this.sound("laugh", { pan: -0.3 });
    }
    const laughing = now < this.mascotLaughUntil;
    this.mascot.texture = laughing ? this.art.triceratopsLaugh : this.art.triceratops;
    if (laughing) {
      y -= Math.abs(Math.sin(now / 60)) * 5;
    }
    this.mascot.position.set(x, y);
    this.mascot.rotation = turn;
  }

  // A small flock of pterodactyls crosses the sky every 15 to 25 seconds, on every screen
  animateFlock(now) {
    if (this.flyoverStart === null) {
      if (this.effects && now >= this.nextFlyover) {
        this.flyoverStart = now;
        this.sound("flock", { pan: 0.7 });
      }
      this.flock.visible = false;
      return;
    }
    const t = (now - this.flyoverStart) / FLYOVER_MS;
    if (t >= 1) {
      this.flyoverStart = null;
      this.nextFlyover = now + between(FLYOVER_EVERY);
      this.flock.visible = false;
      return;
    }
    this.flock.visible = true;
    this.flock.position.set(900 - t * 1100, 45 + Math.sin(t * 9) * 12);
    this.flock.scale.x = -1;
    this.flapAll(this.flock.children, now);
  }

  flapAll(birds, now) {
    birds.forEach((bird, i) => {
      bird.texture = Math.floor((now + i * 50) / FLAP_MS) % 2 ? this.art.pteroUp : this.art.pteroDown;
    });
  }

  animateCameo(now) {
    if (this.cameoStart === null) {
      return;
    }
    const t = (now - this.cameoStart) / CAMEO_MS;
    if (t >= 1 || this.screen !== "title") {
      this.cameoStart = null;
      this.caveman.visible = false;
      return;
    }
    const pop = Math.sin(Math.min(1, t * 1.15) * Math.PI);
    this.caveman.scale.set(0.45 * pop);
    this.caveman.rotation = Math.sin(t * 30) * 0.12 * pop;
  }

  // ---------- Every frame ----------

  frame(now) {
    for (const board of this.boards) {
      board.pump(now);
      board.sync(now);
    }
    if (this.idleWaiters.length && this.allIdle(now)) {
      const waiters = this.idleWaiters;
      this.idleWaiters = [];
      waiters.forEach((fn) => fn());
    }
    this.chunks.step(now);
    for (const label of [...this.floats.children]) {
      const t = (now - label.born) / FLOAT_MS;
      if (t >= 1) {
        label.destroy();
      } else {
        label.y = label.startY - FLOAT_RISE * t;
        label.alpha = Math.min(1, (1 - t) * 3);
      }
    }
    this.animateMascot(now);
    this.animateFlock(now);
    this.animateCameo(now);
    if (this.flyer.visible) {
      this.flapAll([this.flyer], now);
    }
    if (this.shake > 0) {
      this.boardLayer.y = (Math.random() - 0.5) * this.shake;
      this.shake = Math.max(0, this.shake - 0.6);
    } else {
      this.boardLayer.y = 0;
    }
  }
}

// One chunk shape per block color, drawn once
function makeChunks(app) {
  return CHUNK_COLORS.map((color) => {
    const shape = new Graphics()
      .poly([0, 6, 9, 0, 22, 3, 26, 13, 17, 22, 5, 19])
      .fill(color)
      .stroke({ color: INK, width: 3, join: "round" });
    return app.renderer.generateTexture(shape);
  });
}

async function loadArt(app) {
  const load = (name, resolution = 2) => Assets.load({ src: `art/${name}.svg`, data: { resolution } });
  // The characters are drawings saved at three times their size on the stage
  const drawing = (name) => Assets.load({ src: `art/${name}.png`, data: { resolution: 3 } });
  // The bot's color numbers: 0-8 the colors, 10 Stone, 11 the black base under Bombs and Wilds
  const colors = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11];
  const [blocks, specials, backdrops, cast] = await Promise.all([
    Promise.all(colors.map((n) => load(`block${n}`))),
    Promise.all([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => load(`special${n}`))),
    Promise.all([Assets.load("art/menu.jpg"), Assets.load("art/play.jpg")]),
    Promise.all(
      ["triceratops", "triceratops-laugh", "mammoth", "ptero-up", "ptero-down", "tortoise", "caveman"].map(drawing),
    ),
  ]);
  return {
    blocks: Object.fromEntries(blocks.map((texture, i) => [colors[i], texture])),
    specials: Object.fromEntries(specials.map((texture, i) => [i + 1, texture])),
    menu: backdrops[0],
    play: backdrops[1],
    triceratops: cast[0],
    triceratopsLaugh: cast[1],
    mammoth: cast[2],
    pteroUp: cast[3],
    pteroDown: cast[4],
    tortoise: cast[5],
    caveman: cast[6],
    chunks: makeChunks(app),
  };
}

async function loadFonts() {
  try {
    await Promise.all([document.fonts.load('800 30px "Grandstander"'), document.fonts.load('400 16px "Nunito"')]);
  } catch (e) {
    console.warn("Boulder Bash: the fonts didn't load, so text uses a fallback", e);
  }
}

export async function createScene(host) {
  const app = new Application();
  await app.init({
    resizeTo: host,
    backgroundAlpha: 0,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  });
  host.append(app.canvas);
  const [art] = await Promise.all([loadArt(app), loadFonts()]);
  return new Scene(app, art);
}
