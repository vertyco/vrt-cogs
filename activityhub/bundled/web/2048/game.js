import { startArcade } from "activityhub/arcade.js";
import { Board, SIZE } from "./rules.js";

const KEYS = { arrowup: "U", arrowdown: "D", arrowleft: "L", arrowright: "R", w: "U", s: "D", a: "L", d: "R" };
const SWIPE_DISTANCE = 30;
const SLIDE_MS = 100;
const GAIN_MS = 800;
const GOAL = 2048;

const stage = document.getElementById("stage");
const boardEl = document.getElementById("board");
const tilesEl = document.getElementById("tiles");

const state = {
  board: new Board(GOAL),
  moves: "",
  running: false,
  settle: null, // finishes the slide in progress
  reachedGoal: false,
  tiles: new Map(), // cell index -> its tile element
  gain: null,
  swipe: null,
};

// ---------- Drawing ----------

function place(node, cell) {
  node.style.setProperty("--col", cell % SIZE);
  node.style.setProperty("--row", Math.floor(cell / SIZE));
}

function makeTile(cell, value, kind) {
  const tile = document.createElement("div");
  const digits = String(value).length;
  tile.className = "tile";
  tile.classList.add(value > GOAL ? "vbig" : `v${value}`);
  if (digits === 3) {
    tile.classList.add("long");
  } else if (digits > 3) {
    tile.classList.add("longer");
  }
  if (kind) {
    tile.classList.add(kind);
  }
  tile.textContent = value;
  place(tile, cell);
  tilesEl.append(tile);
  state.tiles.set(cell, tile);
}

function drawAll() {
  tilesEl.replaceChildren();
  state.tiles.clear();
  state.board.cells.forEach((value, cell) => {
    if (value) {
      makeTile(cell, value, "new");
    }
  });
}

// Slide the old tiles to where they end up, then swap in the merged and new tiles
function animate({ slides, merged, spawned }) {
  const moving = slides.map(([from, to]) => [state.tiles.get(from), to]);
  for (const [tile, to] of moving) {
    place(tile, to);
  }
  const settle = () => {
    clearTimeout(timer);
    state.settle = null;
    for (const [tile] of moving) {
      tile.remove();
    }
    state.tiles.clear();
    state.board.cells.forEach((value, cell) => {
      if (value) {
        makeTile(cell, value, cell === spawned ? "new" : merged.includes(cell) ? "merged" : "");
      }
    });
  };
  const timer = setTimeout(settle, SLIDE_MS);
  state.settle = settle;
}

// "+36" floats up off the board when tiles merge. A new one replaces the last, so fast moves don't stack
function showGain(points) {
  if (state.gain) {
    state.gain.remove();
  }
  const gain = document.createElement("span");
  gain.className = "gain";
  gain.textContent = `+${points.toLocaleString()}`;
  boardEl.append(gain);
  state.gain = gain;
  setTimeout(() => gain.remove(), GAIN_MS);
}

// ---------- Playing ----------

function move(direction) {
  if (!state.running) {
    return;
  }
  // A move pressed mid-slide finishes the slide at once, so fast players never lose a key press
  if (state.settle) {
    state.settle();
  }
  const before = state.board.score;
  const result = state.board.move(direction);
  if (!result) {
    return;
  }
  state.moves += direction;
  arcade.setScore(state.board.score);
  animate(result);
  if (result.merged.length) {
    const biggest = Math.max(...result.merged.map((cell) => state.board.cells[cell]));
    arcade.tone(220 * Math.log2(biggest), 0.09, { type: "triangle", volume: 0.09 });
    showGain(state.board.score - before);
  } else {
    arcade.tone(180, 0.04, { type: "triangle", volume: 0.04 });
  }
  if (!state.reachedGoal && state.board.cells.includes(GOAL)) {
    state.reachedGoal = true;
    arcade.banner("2048!", "Keep going for an even bigger tile");
    arcade.tune([523, 659, 784, 1047], 0.09);
  }
  if (!state.board.canMove()) {
    state.running = false;
    boardEl.classList.add("over");
    // The player may end this round and start another during the wait, and this one's results must not end that
    const ended = state.board;
    setTimeout(() => {
      if (state.board === ended) {
        arcade.tune([392, 330, 262, 196], 0.2, 0.28);
        arcade.over(ended.score, proof());
      }
    }, SLIDE_MS * 4);
  }
}

function proof() {
  return { moves: state.moves };
}

function play(seed) {
  if (state.settle) {
    state.settle();
  }
  state.board = new Board(seed);
  state.moves = "";
  state.reachedGoal = false;
  state.running = true;
  boardEl.classList.remove("over");
  drawAll();
}

function stop() {
  state.running = false;
  return { score: state.board.score, proof: proof() };
}

// ---------- Input ----------

window.addEventListener("keydown", (event) => {
  const direction = KEYS[event.key.toLowerCase()];
  if (direction) {
    event.preventDefault();
    move(direction);
  }
});

stage.addEventListener("pointerdown", (event) => {
  state.swipe = { x: event.clientX, y: event.clientY };
});

// A swipe the browser took over (a scroll or a system gesture) must not finish as a move later
window.addEventListener("pointercancel", () => {
  state.swipe = null;
});

window.addEventListener("pointerup", (event) => {
  if (!state.swipe) {
    return;
  }
  const dx = event.clientX - state.swipe.x;
  const dy = event.clientY - state.swipe.y;
  state.swipe = null;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_DISTANCE) {
    return;
  }
  move(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "R" : "L") : dy > 0 ? "D" : "U");
});

// ---------- Setup ----------

function resize() {
  const room = Math.min(stage.clientWidth, stage.clientHeight) - 24;
  boardEl.style.setProperty("--size", `${Math.max(120, Math.min(room, 560))}px`);
}

function drawEmptyCells() {
  const cells = document.getElementById("cells");
  for (let cell = 0; cell < SIZE * SIZE; cell++) {
    const span = document.createElement("span");
    place(span, cell);
    cells.append(span);
  }
}

drawEmptyCells();
// A first board sits behind the title screen until the first round starts
drawAll();
const arcade = await startArcade({
  title: "2048",
  icon: "icon.svg",
  accent: "#805ad5",
  help: "Slide the tiles. Two tiles with the same number merge into one, and you score its new value. Reach 2048, then keep going.",
  controls: [
    ["Arrow keys / WASD", "Slide"],
    ["Swipe", "Slide on a touch screen"],
  ],
  // Nothing moves until the player does, so the game never needs to stop by itself
  autoPause: false,
  play,
  pause: () => {
    state.running = false;
  },
  resume: () => {
    state.running = true;
  },
  stop,
});

// Follows the play area, which also changes when the window or the Discord frame does
new ResizeObserver(resize).observe(stage);
