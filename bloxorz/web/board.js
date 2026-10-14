// Bloxorz's stage screen: the original root's frames 46 to 53 as page code. Frame 46 shows the "STAGE NN" splash, 47
// builds the board (the sky with its HUD, a tile per square, a landmask square under each), 48 and 49 raise the tiles
// three a frame, 50 is play, 51 and 52 scatter the tiles while the sky fades out, and 53 unloads it all and starts
// what the bot sent next. The bot decides every landing; this file only draws the board and runs its loops.
//
// The board's parts sit in one clip (the stage root) on an empty timeline, sorted by zIndex the way the original
// sorted them by depth: the sky, then the tiles in build order, then the shadows, then the pieces, then the pause
// panel. A tile in front of a falling piece is lifted over it (raise, the original's deptheriser).
//
// What the pieces (pieces.js) and the panels (panels.js) use, on page.board:
//   tileAt(x, y)            the tile clip on a square, or null
//   square(x, y)            the square's place in stage pixels (R47:27-28)
//   raise(piece, at, dir, otherAt)  lifts the tiles in front of a piece starting to fall ("block", "a" or "b")
//   restart()               a fallen piece passed y 1,000 (or the won block dropped away): the board scatters
//   scatter(winning)        scatters the board, as a win (tiles fly out from the goal) or a fall (tiles drop)
//   onPlay                  called when the root reaches frame 50, the frame the original places the pieces on
//   onTick                  called once a tick before the root's own frame step, while the stage shows
//   place(frame, depth, z)  places what the original root's timeline has at that frame and depth on the stage root
//   root, landmask, shadows, depths, stage (the StageMsg being played)
// Pieces are attached to the root as "block", "block2" (cube a) and "block3" (cube b) at depths.block and so on; the
// pause panel as "menuness". The root's variables (root.get/set) hold the original's winning, exiting and detractor.
import { setMatrix } from "./flash.js";
import { wireButton } from "./menu.js";

// An empty timeline for the stage root, so every part on it is placed by this file
const ROOT = "board-root";
const LOST_GAME = "The game restarted. Press Continue to carry on.";
// The original's root timeline, where the splash, landmask, sky and shadows are placed
const ORIGINAL_ROOT = 0;
const SPLASH = 332;
const SKY = 353;
const TILE = 320;
const LANDMASK = 323;
const MASK_SQUARE = 322;
const SHADOWS = 704;
// The art the stage needs before it shows: the board's parts, the pieces, the landing sound pickers and the pause panel
const STAGE_ART = [SPLASH, SKY, TILE, LANDMASK, SHADOWS, 1152, 829, 1165, 1179];
// The root's frames
const SPLASH_FRAME = 46;
const BUILD = 47;
const RISE = 48;
const RISE_LOOP = 49;
const PLAY = 50;
const SCATTER = 51;
const SCATTER_LOOP = 52;
const UNLOAD = 53;
// Where the root's timeline places its parts: [frame, depth]
const SPLASH_AT = [SPLASH_FRAME, 72];
const LANDMASK_AT = [SPLASH_FRAME, 70];
const SKY_AT = [BUILD, 7];
const SHADOWS_AT = [PLAY, 72];
// The board's slant (R47:1-6)
const X_GAP = 32;
const Y_GAP = 16;
const X_SHIFT = 10;
const Y_SHIFT = 5;
const X_START = 0;
const Y_START = 130;
const COLUMNS = 15;
const ROWS = 10;
// Each letter's tile label (R47:15)
const BLOCK_TYPES = {
  b: "normalblock",
  s: "softswitch",
  h: "hardswitch",
  l: "doorblockl",
  k: "doorblockl",
  r: "doorblockr",
  q: "doorblockr",
  e: "endblock",
  v: "splitswitch",
  f: "fallblock",
};
const BRIDGES = new Set(["l", "k", "r", "q"]);
const GOAL = "e";
// Tiles start rising three a frame, then the root waits 16 more frames (R47:52, R48)
const RISING_A_FRAME = 3;
const COUNTDOWN = 16;
// Each tile's scatter delay is random(6) frames (R47:40)
const SCATTER_DELAYS = 6;
// Depths, as the original's: timeline parts sit far below the tiles, which take their build index (1 to 150); the
// shadows, landmask and pieces sit just above the last tile; the deptheriser lifts a tile 200 over that
const TIMELINE_DEPTH = -16384;
const LAST_TILE = ROWS * COLUMNS;
const DEPTHS = {
  shadows: LAST_TILE + 4,
  landmask: LAST_TILE + 7,
  block: LAST_TILE + 10,
  block2: LAST_TILE + 11,
  block3: LAST_TILE + 12,
  menuness: 10000,
};
const RAISE = 200;
// The pieces' names on the root, by the bot's piece names
const PIECE_CLIPS = { block: "block", a: "block2", b: "block3" };
// Each shadow in sprite 704 and the piece it follows (DefineSprite_704/frame_1 clip events)
const FOLLOW = [
  ["blockshadow", "block"],
  ["blockshadow2", "block2"],
  ["blockshadow3", "block3"],
];
const SHADOW_ALPHA = 0.5;
// The sky's Moves digits show the count 9 frames late, so they tick as the roll lands (frame_47/PlaceObject2_353_7)
const MOVES_DELAY = 9;
const DIGITS = 6;
const BLANK_DIGIT = 12;
// The hint line (S345/f1). On touch screens the stages that name keys say how to play by touch instead
const HINTS = {
  1: "Use the up, down, left and right arrow keys to move your block around.",
  8: "Remember to use the Spacebar to toggle between the two small blocks.",
};
const TOUCH_HINTS = {
  1: "Swipe on the board to roll your block around.",
  8: "Tap Switch to change between the two small blocks.",
};
// The Menu button's depth in sprite 345
const MENU_BUTTON = 3;
// The sky's fade-sound picker (S352/f1): frame 2 plays the fall's sound, frame 4 the win's
const FALL_SOUND_FRAME = 2;
const WIN_SOUND_FRAME = 4;
const AMBIENT_VOLUME = 0.18;

const board = {
  page: null,
  root: null,
  // The StageMsg the board is playing
  stage: null,
  // Squares whose tiles haven't started rising, the frames left after the last one, and the frames scattered so far
  landable: [],
  countdown: 0,
  blockfalltime: 0,
  // The Moves digits' 9 frames of counts, newest first, and the count they show
  movesSeen: [],
  movesShown: 0,
  // What the bot sent while the board was playing ({ kind: "stage" | "done", value }); the board takes it at frame 53
  next: null,
  // True once the board unloaded with nothing yet from the bot to start
  waiting: false,
  onPlay: null,
  onTick: null,
};

// ---------- Parts ----------

function square(x, y) {
  return { x: X_START + x * X_GAP + y * X_SHIFT, y: Y_START - x * Y_SHIFT + y * Y_GAP };
}

// The original's own counter for each square, in build order: rows top to bottom, each row right to left
function buildIndex(x, y) {
  return y * COLUMNS + (COLUMNS - 1 - x) + 1;
}

function tileAt(x, y) {
  return board.root?.child(`stone${x},${y}`) ?? null;
}

// A part the original's root timeline places, at its place and with its name, on the stage root
function placeFromRoot(page, [frame, depth], zIndex) {
  const entry = page.lib.frames(ORIGINAL_ROOT)[frame - 1].find((item) => item.d === depth);
  const node = page.lib.create(entry.c);
  setMatrix(node, entry.m);
  node.zIndex = zIndex;
  return board.root.attach(node, entry.n || null);
}

function makeRoot(page) {
  page.lib.data.sprites[ROOT] ??= { n: 1, f: [[]] };
  const root = page.lib.make(ROOT);
  root.sortableChildren = true;
  root.frame = 0;
  root.playing = false;
  page.root.addChild(root);
  board.root = root;
  return root;
}

function dropRoot() {
  board.root?.destroy({ children: true });
  board.root = null;
}

// ---------- The root's frames ----------

// Arrives on a root frame the way the original's playhead did: the frame's sound, then its script
function enterFrame(frame) {
  const root = board.root;
  root.frame = frame;
  root.playing = true;
  const sound = board.page.lib.data.sprites[ORIGINAL_ROOT].a?.[frame];
  if (sound) {
    board.page.lib.onSound?.(sound[0], sound[1]);
  }
  FRAMES[frame]?.(board.page, root);
}

// The pieces move and read the keys first, then the root steps (a fallen piece plays it on into the scatter)
function stepStage() {
  board.onTick?.();
  stepRoot();
}

function stepRoot() {
  if (board.root?.playing) {
    enterFrame(board.root.frame + 1);
  }
}

// R46: the ambient music and the "STAGE NN" splash. Its digits and centring come from its load script
// (frame_46/PlaceObject2_332_72); the splash's own end (S331/f75, splashdone) plays the root on
function splashFrame(page, root) {
  root.playing = false;
  page.sound.music("ambient", AMBIENT_VOLUME);
  const splash = placeFromRoot(page, SPLASH_AT, TIMELINE_DEPTH + SPLASH_AT[1]);
  splash.label = "splash";
  const tens = Math.floor(board.stage.n * 0.1);
  const ones = board.stage.n - tens * 10;
  const first = splash.child("digit1");
  const second = splash.child("digit2");
  first.gotoAndStop(tens + 1);
  second.gotoAndStop(ones + 1);
  second.x = tens !== 1 ? first.x + 33 : first.x + 18;
  const wideness = ones !== 1 ? second.x + 33 : second.x + 18;
  splash.x = 270 - wideness * 0.5;
}

// R47: the sky with the passcode, a tile and a landmask square on every square, each tile waiting on its label
function buildFrame(page, root) {
  root.child("splash")?.removeMovieClip();
  root.set("winning", false);
  root.set("exiting", false);
  board.landable = [];
  board.blockfalltime = 0;
  board.countdown = COUNTDOWN;
  const landmask = root.child("landmask") ?? placeFromRoot(page, LANDMASK_AT, DEPTHS.landmask);
  // The original hides it (frame_46/PlaceObject2_323_70); it only cuts out the shadows once play starts
  landmask.visible = false;
  const open = new Set(board.stage.open.map(([x, y]) => `${x},${y}`));
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = COLUMNS - 1; x >= 0; x -= 1) {
      const letter = board.stage.rows[y]?.[x] ?? " ";
      if (letter !== " ") {
        placeTile(page, root, landmask, letter, x, y, open.has(`${x},${y}`));
      }
    }
  }
  placeSky(page, root);
}

function placeTile(page, root, landmask, letter, x, y, open) {
  const at = square(x, y);
  const tile = page.lib.create(TILE);
  tile.position.set(at.x, at.y);
  tile.zIndex = buildIndex(x, y);
  root.attach(tile, `stone${x},${y}`);
  tile.gotoAndStop(BLOCK_TYPES[letter] ?? BLOCK_TYPES.b);
  // A bridge starts as the bot says it is, so a resumed board has its bridges where they were
  if (BRIDGES.has(letter)) {
    tile.set("starton", open);
  }
  tile.blockfall = Math.floor(page.lib.random() * SCATTER_DELAYS);
  board.landable.push([x, y]);
  if (letter !== GOAL) {
    const mask = page.lib.create(MASK_SQUARE);
    mask.position.set(at.x, at.y);
    landmask.attach(mask, `maskstone${x},${y}`);
  }
}

function placeSky(page, root) {
  board.movesSeen = [];
  board.movesShown = page.moves;
  const sky = placeFromRoot(page, SKY_AT, TIMELINE_DEPTH + SKY_AT[1]);
  const code = board.stage.code;
  for (let spot = 1; spot <= DIGITS; spot += 1) {
    sky.child(`digit${spot}`)?.gotoAndStop(Number(code[spot - 1]) + 1);
  }
  sky.onEnterFrame = () => showMoves(page, sky);
  showMoves(page, sky, false);
}

// frame_47/PlaceObject2_353_7: the Moves digits read the count from 9 frames ago, with blanks for leading zeros
function showMoves(page, sky, step = true) {
  if (step) {
    if (board.movesSeen.length >= MOVES_DELAY) {
      board.movesShown = board.movesSeen[MOVES_DELAY - 1];
    }
    board.movesSeen.unshift(page.moves);
    board.movesSeen.length = Math.min(board.movesSeen.length, MOVES_DELAY);
  }
  const text = String(Math.max(0, Math.floor(board.movesShown))).padStart(DIGITS, "0").slice(-DIGITS);
  let leading = true;
  for (let spot = 1; spot <= DIGITS; spot += 1) {
    // The last digit always shows, so no moves reads 0
    leading = leading && text[spot - 1] === "0" && spot < DIGITS;
    sky.child(`digit${spot}a`)?.gotoAndStop(leading ? BLANK_DIGIT : Number(text[spot - 1]) + 1);
  }
}

// R48: three tiles that haven't risen start to, picked at random; once all have, the countdown runs
function riseFrame(page, root) {
  if (board.landable.length === 0) {
    board.countdown -= 1;
  }
  for (let count = 0; count < RISING_A_FRAME && board.landable.length; count += 1) {
    const pick = Math.floor(page.lib.random() * board.landable.length);
    const [x, y] = board.landable.splice(pick, 1)[0];
    tileAt(x, y)?.play();
  }
}

// R49
function riseLoopFrame() {
  enterFrame(board.countdown === 0 ? PLAY : RISE);
}

// R50: play. The shadows go over the tiles, cut out by the landmask so they show only on standing tiles
// (frame_50/PlaceObject2_704_72); the pieces come from pieces.js
function playFrame(page, root) {
  root.playing = false;
  const landmask = root.child("landmask");
  const shadows = placeFromRoot(page, SHADOWS_AT, DEPTHS.shadows);
  for (const [name, piece] of FOLLOW) {
    const shadow = shadows.child(name);
    shadow.alpha = SHADOW_ALPHA;
    shadow.visible = piece === "block";
  }
  if (landmask) {
    landmask.visible = true;
    shadows.mask = landmask;
  }
  shadows.onEnterFrame = () => followPieces(root, shadows);
  page.panels.place();
  board.onPlay?.();
}

function followPieces(root, shadows) {
  for (const [name, piece] of FOLLOW) {
    const shadow = shadows.child(name);
    const clip = root.child(piece);
    if (shadow && clip) {
      shadow.position.set(clip.x, clip.y);
      shadow.gotoAndStop(clip.frame);
    }
  }
}

// R51: the sky fades out while each tile past its delay drops and fades (a fall) or flies out from the goal (a win)
function scatterFrame(page, root) {
  const sky = root.child("sky");
  sky?.play();
  if (board.blockfalltime === 0 && (root.get("winning") || root.get("exiting"))) {
    page.playing = false;
    page.report();
  }
  const winning = root.get("winning");
  const goal = winning ? goalPoint() : null;
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = COLUMNS - 1; x >= 0; x -= 1) {
      const tile = tileAt(x, y);
      if (tile && board.blockfalltime > tile.blockfall) {
        scatterTile(tile, goal);
      }
    }
  }
  board.blockfalltime += 1;
}

// R51:2-5: the middle of the goal square, where the won block sank
function goalPoint() {
  const rows = board.stage.rows;
  const y = rows.findIndex((row) => row.includes(GOAL));
  const x = y === -1 ? 0 : rows[y].indexOf(GOAL);
  return square(x + 0.5, y - 0.5);
}

// Flash keeps _alpha as a multiple of 1/256, so each step of the fade loses a little, as the original's did
function flashAlpha(tile) {
  return tile.flashAlpha ?? 100;
}

function setFlashAlpha(tile, value) {
  tile.flashAlpha = (Math.trunc((value / 100) * 256) / 256) * 100;
  tile.alpha = Math.max(0, Math.min(1, tile.flashAlpha / 100));
}

function scatterTile(tile, goal) {
  if (goal) {
    const theta = Math.atan2(tile.y - goal.y, goal.x - tile.x);
    setFlashAlpha(tile, flashAlpha(tile) - 5);
    const gone = 100 - flashAlpha(tile);
    tile.x -= gone * Math.sin(theta) * 0.5;
    tile.y -= gone * Math.cos(theta) * 0.5;
    return;
  }
  setFlashAlpha(tile, flashAlpha(tile) - 10);
  tile.y += (100 - flashAlpha(tile)) * 0.5;
}

// R52
function scatterLoopFrame() {
  enterFrame(SCATTER);
}

// R53: everything goes, then the board starts what the bot sent: the next stage, the restart after a fall, or the end.
// After Quit to Menu it goes back to the menu without the title
function unloadFrame(page, root) {
  const winning = root.get("winning");
  const exiting = root.get("exiting");
  dropRoot();
  if (exiting && !winning) {
    board.next = null;
    page.skiptomenu = true;
    page.go("menu");
    return;
  }
  startNext(page);
}

const FRAMES = {
  [SPLASH_FRAME]: splashFrame,
  [BUILD]: buildFrame,
  [RISE]: riseFrame,
  [RISE_LOOP]: riseLoopFrame,
  [PLAY]: playFrame,
  [SCATTER]: scatterFrame,
  [SCATTER_LOOP]: scatterLoopFrame,
  [UNLOAD]: unloadFrame,
};

// ---------- What the bot sends ----------

// Builds a stage from the bot's StageMsg: with its splash for a new stage, straight to the build otherwise
function begin(page, stage) {
  board.stage = stage;
  board.waiting = false;
  dropRoot();
  makeRoot(page);
  enterFrame(stage.splash ? SPLASH_FRAME : BUILD);
}

function startNext(page) {
  const next = board.next;
  board.next = null;
  if (!next) {
    board.waiting = true;
    return;
  }
  board.waiting = false;
  if (next.kind === "done") {
    // The end screen is the menu clip's last part (R53:24-28)
    page.panels.showEnd(next.value);
    return;
  }
  page.takeStage(next.value);
  begin(page, next.value);
  page.report();
}

// A stage or the end the bot sent while the board shows. It waits for frame 53, as the original's root decided what
// came next only there. A resync (resume) rebuilds the board at once. False when the board isn't showing, so the
// message is the menu's to take
function hold(kind, value) {
  const page = board.page;
  if (page.screen !== "stage") {
    return false;
  }
  if (kind === "stage" && value.resume) {
    board.next = null;
    page.takeStage(value);
    begin(page, value);
    return true;
  }
  board.next = { kind, value };
  if (board.waiting) {
    startNext(page);
  }
  return true;
}

// A live attempt the bot kept for this player (a reconnect) goes straight back on the board. When the bot no longer
// has the game (a restart, a reload, a long absence) a board still showing is left for the menu, where Continue picks
// up the saved run
function receiveHello(page, value) {
  const game = value?.game;
  if (!game) {
    if (page.screen === "stage") {
      board.next = null;
      page.skiptomenu = true;
      page.go("menu");
      page.toast(LOST_GAME);
    }
    return;
  }
  if (!hold("stage", game)) {
    page.takeStage(game);
    page.go("stage");
  }
}

// ---------- Scattering ----------

// A fallen piece passed y 1,000, or the won block dropped away (BE:119-122, CE:13-20): the root plays on into the
// scatter
function restart() {
  if (board.root?.frame === PLAY) {
    board.root.playing = true;
  }
}

function scatter(winning) {
  if (board.root?.frame === PLAY) {
    board.root.set("winning", Boolean(winning));
    restart();
  }
}

// The deptheriser (BL:440-470, CL:174-206): tiles nearer the viewer than a piece starting to fall are lifted over it.
// The block reaches one square further the way it falls while `detractor` is on; a cube reaches a row further down,
// and lifts the other cube (with the shadows) when that one sits on a lifted square
function raise(piece, at, dir, otherAt = null) {
  const root = board.root;
  if (!root) {
    return;
  }
  const [reachX, reachY] = reach(piece, at, dir);
  const other = piece === "a" ? root.child("block3") : piece === "b" ? root.child("block2") : null;
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = COLUMNS - 1; x >= 0; x -= 1) {
      if (y <= reachY && x >= reachX) {
        continue;
      }
      const tile = tileAt(x, y);
      if (tile) {
        tile.zIndex += RAISE;
      }
      if (other && otherAt && otherAt[0] === x && otherAt[1] === y) {
        other.zIndex += RAISE;
        const shadows = root.child("shadowsandglow");
        if (shadows) {
          shadows.zIndex += RAISE;
        }
      }
    }
  }
}

function reach(piece, [x, y], dir) {
  if (piece === "block") {
    const detractor = board.root.get("detractor") !== false;
    if (!detractor) {
      return [x, y];
    }
    return { up: [x, y - 1], down: [x, y + 1], left: [x - 1, y] }[dir] ?? [x, y];
  }
  return { up: [x, y - 1], down: [x, y + 2] }[dir] ?? [x, y];
}

// ---------- Frame scripts ----------

// S320/f32 and f122: a bridge waits until the root reaches play, then opens (starton) or stays shut
function waitBridge(clip, opens, shut, again) {
  if (clip.parentClip?.frame !== PLAY) {
    clip.gotoAndPlay(again);
  } else if (clip.get("starton")) {
    clip.gotoAndPlay(opens);
  } else {
    clip.gotoAndStop(shut);
  }
}

// The tile's frame scripts. A closing bridge (f41, f131) takes its square out of the landmask; the check for the
// pieces on it is the bot's, sent by pieces.js
function tileScript(clip, frame) {
  if (frame === 32) {
    waitBridge(clip, 34, 33, 31);
  } else if (frame === 122) {
    waitBridge(clip, 124, 123, 121);
  } else if (frame === 96) {
    // S320/f96: the goal waits for play too
    clip.gotoAndPlay(clip.parentClip?.frame === PLAY ? 97 : 95);
  } else if (frame === 41 || frame === 131) {
    clip.lib.onHook?.("mask", 0, clip);
  }
}

// S345/f1: the hint line, and the Menu button (B342), which opens the pause panel
function hudScript(page, clip) {
  const touch = window.matchMedia("(pointer: coarse)").matches;
  const typey = clip.child("typey");
  if (typey) {
    typey.text = (touch ? TOUCH_HINTS : HINTS)[board.stage?.n] ?? "";
  }
  const button = clip.at(MENU_BUTTON);
  if (button) {
    wireButton(page, button, () => page.panels.openPause());
  }
}

// S352/f1: the sky's fade sound, the win's whoosh or the fall's
function fadeSoundScript(clip) {
  clip.gotoAndPlay(board.root?.get("winning") ? WIN_SOUND_FRAME : FALL_SOUND_FRAME);
}

// ---------- The screen ----------

function enterStage(page) {
  page.sound.music("ambient", AMBIENT_VOLUME);
  if (!page.stageMsg) {
    page.go("menu");
    return;
  }
  board.next = null;
  begin(page, page.stageMsg);
}

function leaveStage() {
  dropRoot();
  board.stage = null;
  board.next = null;
  board.waiting = false;
}

function setupHooks(page) {
  // S331/f75: the splash's end plays the root on into the build
  page.onHook("splashdone", () => {
    if (board.root?.frame === SPLASH_FRAME) {
      board.root.playing = true;
    }
  });
  // S353/f57: the sky's fade-out ends, and the root's next frame unloads the board
  page.onHook("skydone", (argument, clip) => {
    if (board.root && clip === board.root.child("sky")) {
      board.root.frame = UNLOAD - 1;
      board.root.playing = true;
    }
  });
}

// The stage screen, its frame scripts and hooks, and page.board for the pieces and panels
export function setupBoard(page) {
  board.page = page;
  setupHooks(page);
  page.onMessage("hello", (value) => receiveHello(page, value));
  page.onMessage("done", (value) => {
    if (!hold("done", value)) {
      page.done = value;
    }
  });
  page.board = {
    hold,
    tileAt,
    square,
    raise,
    restart,
    scatter,
    depths: DEPTHS,
    pieceClips: PIECE_CLIPS,
    get root() {
      return board.root;
    },
    get stage() {
      return board.stage;
    },
    get landmask() {
      return board.root?.child("landmask") ?? null;
    },
    get shadows() {
      return board.root?.child("shadowsandglow") ?? null;
    },
    get onPlay() {
      return board.onPlay;
    },
    set onPlay(fn) {
      board.onPlay = fn;
    },
    set onTick(fn) {
      board.onTick = fn;
    },
    place: (frame, depth, zIndex) => placeFromRoot(page, [frame, depth], zIndex),
  };
  return {
    screens: {
      stage: { art: STAGE_ART, enter: enterStage, leave: leaveStage, step: stepStage },
    },
    scripts: [
      [TILE, tileScript],
      [345, (clip) => hudScript(page, clip)],
      [352, (clip) => fadeSoundScript(clip)],
    ],
  };
}
