// Bloxorz's block and the two small cubes: the original's DefineSprite_1152 (block) and DefineSprite_829 (block2 is
// cube "a", block3 is cube "b"), with the landing sound pickers DefineSprite_1165 (clonk, clonk2), placed on root
// frame 50 as the original placed them.
//
// A roll's animation starts the moment its key is down and the roll goes to the bot. The bot decides how it lands:
// on the roll's landing frame (the frames that called overair2) the page applies the bot's step for it, and holds the
// piece on that frame if the answer hasn't come yet. Applying a step draws what the original's overair2 did: the
// pose or the fall, the switch presses with their flashes and the bridges they turn, the win, the split, the join
// and the landing sounds, which the page picks from the step and the tiles as the original did (BL:339-437,
// CL:161-172). A step that started a bridge closing asks the bot for the close check on the next frame, after that
// frame's input (a held key's new roll starts first, then the tile's check runs).
//
// Comments point at the original's code: BL is the block's onClipEvent(load) (frame_50/PlaceObject3_1152_84), BE its
// onClipEvent(enterFrame), BK its onClipEvent(keyDown); CL and CE the same for cube a (frame_50/PlaceObject2_829_78).

const BLOCK = 1152;
const CUBE = 829;
// Where root frame 50 places each piece and sound picker: [frame, depth]
const PLAY_FRAME = 50;
const PLACES = { block: [PLAY_FRAME, 84], a: [PLAY_FRAME, 78], b: [PLAY_FRAME, 89] };
const CLONKS = [
  [PLAY_FRAME, 95],
  [PLAY_FRAME, 97],
];
const CLONK_DEPTH = 95;
// The pieces by the bot's names, with their names on the root and their shadows (DefineSprite_704)
const CLIP_NAMES = { block: "block", a: "block2", b: "block3" };
const SHADOWS = { block: "blockshadow", a: "blockshadow2", b: "blockshadow3" };
const DIRS = ["left", "up", "right", "down"];
const KEYS = { ArrowLeft: "left", ArrowUp: "up", ArrowRight: "right", ArrowDown: "down" };
const SPACE = " ";
// The block's resting frames by pose, and the frame each key starts a roll on from each of them (BE:47-118)
const REST = { up: 1, far: 41, long: 81 };
const BLOCK_STARTS = {
  left: { 1: 2, 41: 42, 81: 82 },
  up: { 1: 12, 41: 52, 81: 92 },
  right: { 1: 22, 41: 62, 81: 102 },
  down: { 1: 32, 41: 72, 81: 112 },
};
// The cube rests on frame 1 and rolls from these (CE:21-58)
const CUBE_REST = 1;
const CUBE_STARTS = { left: 2, up: 12, right: 22, down: 32 };
// Frames whose script sets `dir` (S1152/f2 and so on, S829/f2 and so on)
const BLOCK_DIR_FRAMES = { 2: "left", 12: "up", 22: "right", 32: "down", 42: "left", 52: "up", 62: "right" };
Object.assign(BLOCK_DIR_FRAMES, { 72: "down", 82: "left", 92: "up", 102: "right", 112: "down" });
const CUBE_DIR_FRAMES = { 2: "left", 12: "up", 22: "right", 32: "down" };
// Frames that call overair2 at the end of a roll
const BLOCK_LANDINGS = new Set([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 121]);
const CUBE_LANDINGS = new Set([10, 20, 30, 40]);
// S1152/f267 (the won block drops away), f282 (the split's end), f290 and f310 (the joined block lands)
const WIN_DROP = 267;
const SPLIT_DONE = 282;
const JOIN_LANDINGS = new Set([290, 310]);
const WIN_DROP_SPEED = 100;
// S829/f83: a cube appears
const CUBE_APPEARS = 83;
// CE:13-20: the other cube's fade when one falls away
const PHASE = 105;
// S1179/f38: the block's Quit to Menu frames
const QUIT_FRAME = 350;
// Launch speeds per frame, x then y (BL:6-9, CL:7), and gravity added to the fall speed each frame
const SPEEDS = {
  roll: { up: [-3, 3], down: [3, 8], left: [-6, 5], right: [6, 0] },
  half: { up: [-3, 3], down: [3, 8], left: [-6, 5], right: [6, 0] },
  full: { up: [-3, 3], down: [3, 8], left: [0, 5], right: [1, 0] },
  tall: { up: [-3, 3], down: [3, 8], left: [-3, 5], right: [3, 0] },
  cube: { up: [-3, 3], down: [3, 8], left: [-6, 5], right: [6, 0] },
};
const GRAVITY = 2;
// Falls that turn the deptheriser's one-square reach off (BL:142, 202, 257, 280)
const NO_DETRACTOR = new Set(["full", "tall", "fragile"]);
const FALLEN = 1000;
// A bridge holds only at rest open (BL:27-45)
const DOORS = "lkrq";
const DOOR_OPEN = new Set([40, 130]);
// The flasher's frames (DefineSprite_269): being closed, being opened
const FLASHES = { close: 2, open: 22 };
// The selection ring (DefineSprite_710): plays in from 2, out from 30
const RING_IN = 2;
const RING_OUT = 30;
// The sound picker labels (DefineSprite_1165) for a full landing and for half of one
const FULL_SOUNDS = { stone: "clonk", metal: "metal", hollow: "hollow" };
const HALF_SOUNDS = { stone: "half", metal: "halfmetal", hollow: "hollow" };
const SWITCH_SOUNDS = { soft: "smallswitch", heavy: "bigswitch" };

const state = {
  page: null,
  // The board root the pieces sit on; a new one means a new attempt
  root: null,
  // name -> { name, clip, xp, yp, dir, rolling, falling, deptherised, xs, ys, landedAt, split }
  pieces: {},
  // The piece the keys move (the original's _global.selectedness)
  selected: "block",
  // The attempt ended (a fall or a win), so the keys do nothing more
  over: false,
  // The pieces of the rolls sent and not yet answered, oldest first
  sent: [],
  // A roll's answer that came before its landing frame, by piece; pieces held on their landing frame
  ready: new Map(),
  holding: new Set(),
  // The joined block's landing, applied on its join frame
  joinStep: null,
  // Counts the ticks; a close check goes out on the first tick after this one
  ticks: 0,
  checkAfter: null,
  // Directions pressed since the last tick (a key down and up between two frames still counts once)
  tapped: new Set(),
  // The label each sound picker was sent to by the landing being applied
  clonked: new Map(),
};

// ---------- The board ----------

function board() {
  return state.page.board;
}

function live() {
  const root = board().root;
  return Boolean(root && root === state.root && !state.pieces.block?.clip.destroyed);
}

function letterAt(x, y) {
  return board().stage?.rows[y]?.[x] ?? " ";
}

// BL:21-126 and CL:51-101: what a square sounds like under a landing piece. The goal is silent under the block
function soundKind(x, y, cube) {
  const letter = letterAt(x, y);
  if (letter === " ") {
    return "none";
  }
  if (DOORS.includes(letter)) {
    return DOOR_OPEN.has(board().tileAt(x, y)?.frame) ? "metal" : "none";
  }
  if (letter === "f") {
    return "hollow";
  }
  if (letter === "e") {
    return cube ? "stone" : "none";
  }
  return "stone";
}

// A picker sent again to the label one landing already sent it to stays put: in the original the label's script (its
// random pick) waits for the landing's script to end, so the second jump lands on the frame already showing and changes
// nothing. A long block rolling sideways onto stone calls "clonk" twice in one landing (BL:133, BL:358), and so do cube
// b and the block it joins (the joined block lands within cube b's landing): one sound each time
function clonk(name, label) {
  if (state.clonked.get(name) === label) {
    return;
  }
  state.clonked.set(name, label);
  board().root?.child(name)?.gotoAndPlay(label);
}

function shadow(name) {
  return board().shadows?.child(SHADOWS[name]) ?? null;
}

function reposition(piece) {
  const at = board().square(piece.xp, piece.yp);
  piece.clip.position.set(at.x, at.y);
}

// ---------- Placing the pieces (root frame 50) ----------

function makePiece(name) {
  const clip = board().place(...PLACES[name], board().depths[CLIP_NAMES[name]]);
  const start = board().stage.start;
  return { name, clip, xp: start[0], yp: start[1], dir: null, rolling: false, falling: false, landedAt: -1 };
}

function placePieces() {
  const page = state.page;
  Object.assign(state, { root: board().root, selected: "block", over: false, sent: [], joinStep: null });
  state.ready.clear();
  state.holding.clear();
  state.tapped.clear();
  state.checkAfter = null;
  state.pieces = {};
  // Placed in the original's depth order: block2, block, block3
  for (const name of ["a", "block", "b"]) {
    state.pieces[name] = makePiece(name);
  }
  for (const at of CLONKS) {
    board().place(...at, CLONK_DEPTH);
  }
  for (const name of ["a", "b"]) {
    const cube = state.pieces[name];
    // CL:2-5 and S829/f1: hidden and still until the split
    cube.clip.visible = false;
    cube.clip.stop();
    reposition(cube);
  }
  const stage = board().stage;
  if (stage.resume) {
    resumePieces(stage.piece);
  } else {
    // BL:2-11: the block drops in (S1152/f240 to f257)
    board().root.set("detractor", true);
    reposition(state.pieces.block);
    state.pieces.block.clip.gotoAndStop("land");
    state.pieces.block.clip.play();
  }
  page.report();
  window.focus();
}

// A resumed attempt: the pieces at rest where the bot says, without the drop-in
function resumePieces(piece) {
  const block = state.pieces.block;
  board().root.set("detractor", true);
  if (piece.pose) {
    [block.xp, block.yp] = piece.at;
    reposition(block);
    block.clip.gotoAndStop(REST[piece.pose]);
    return;
  }
  block.clip.visible = false;
  block.clip.stop();
  const blockShadow = shadow("block");
  if (blockShadow) {
    blockShadow.visible = false;
  }
  state.selected = piece.selected;
  for (const name of ["a", "b"]) {
    const cube = state.pieces[name];
    [cube.xp, cube.yp] = piece[name];
    cube.clip.visible = true;
    reposition(cube);
    const cubeShadow = shadow(name);
    if (cubeShadow) {
      cubeShadow.visible = true;
    }
  }
}

// ---------- Input ----------

function atRest(piece) {
  if (piece.name === "block") {
    return Object.values(REST).includes(piece.clip.frame);
  }
  return piece.clip.frame === CUBE_REST;
}

// A key pressed or released (or a swipe, from touch.js). Only keys down count, as the original's Key.isDown
function press(dir, down) {
  if (!DIRS.includes(dir)) {
    return;
  }
  if (down) {
    state.page.held.add(dir);
    state.tapped.add(dir);
  } else {
    state.page.held.delete(dir);
  }
}

// BE:47-118, CE:21-58: the selected piece at rest rolls the first held way of left, up, right, down. Not on the
// frame it landed, so a held key rolls again on the frame after, as the original's 9 frames a roll
function readKeys() {
  if (state.over || board().root.frame !== PLAY_FRAME) {
    return;
  }
  const piece = state.pieces[state.selected];
  if (!piece || piece.landedAt === state.ticks || !atRest(piece)) {
    return;
  }
  const dir = DIRS.find((way) => state.page.held.has(way) || state.tapped.has(way));
  if (dir) {
    startRoll(piece, dir);
  }
}

function startRoll(piece, dir) {
  const page = state.page;
  if (piece.name === "block") {
    piece.clip.gotoAndPlay(BLOCK_STARTS[dir][piece.clip.frame]);
  } else {
    cancelRing(piece);
    piece.clip.gotoAndPlay(CUBE_STARTS[dir]);
  }
  piece.rolling = true;
  page.moves += 1;
  page.playing = true;
  state.sent.push(piece.name);
  page.send({ roll: { piece: piece.name, dir } });
  page.report();
}

// CL:16-22
function cancelRing(piece) {
  const ring = piece.clip.child("selecta");
  if (ring && ring.frame < RING_OUT) {
    ring.gotoAndPlay(RING_OUT);
  }
}

// BK: Space swaps the selected cube at once, even mid-roll, with the selection rings
function swap() {
  if (state.over || !live() || board().root.frame !== PLAY_FRAME || state.selected === "block") {
    return;
  }
  const next = state.selected === "a" ? "b" : "a";
  state.pieces[next].clip.child("selecta")?.gotoAndPlay(RING_IN);
  cancelRing(state.pieces[state.selected]);
  state.selected = next;
  state.page.send({ swap: true });
}

// True while the two small blocks are out and the keys still work, which is when the Switch button shows
function cubesOut() {
  return live() && !state.over && state.selected !== "block";
}

function keyDown(event) {
  if (state.page.screen !== "stage") {
    return;
  }
  if (KEYS[event.key]) {
    event.preventDefault();
    press(KEYS[event.key], true);
  } else if (event.key === SPACE) {
    event.preventDefault();
    swap();
  }
}

function keyUp(event) {
  if (KEYS[event.key]) {
    press(KEYS[event.key], false);
  }
}

// ---------- Applying the bot's steps ----------

// A roll's landing frame: its step if the answer is here, otherwise the piece waits on this frame
function land(name) {
  const piece = state.pieces[name];
  const steps = state.ready.get(name);
  if (!steps) {
    piece.clip.stop();
    state.holding.add(name);
    return;
  }
  state.ready.delete(name);
  applyLanding(name, steps);
}

function applyLanding(name, steps) {
  state.clonked.clear();
  state.holding.delete(name);
  if (name === "block") {
    applyBlock(steps[0], true);
  } else {
    applyCube(name, steps[0], steps[1]);
  }
  if (steps.some((step) => step.closing)) {
    state.checkAfter = state.ticks;
  }
}

// BL:127-283: the block's pose or fall, then the win, the split or the fragile tile breaking
function applyBlock(step, buttoncheck) {
  const piece = state.pieces.block;
  const clip = piece.clip;
  const dir = step.dir ?? piece.dir;
  const end = step.end ?? {};
  [piece.xp, piece.yp] = step.at;
  piece.rolling = false;
  piece.landedAt = state.ticks;
  state.holding.delete("block");
  reposition(piece);
  const kinds = blockKinds(step.pose, step.at);
  if (end.fall && end.fall.kind !== "fragile") {
    blockFall(piece, step.pose, end.fall, dir);
  } else {
    if (step.pose === "long" && (dir === "left" || dir === "right") && !end.fall) {
      clonk("clonk", "clonk");
    }
    clip.gotoAndStop(REST[step.pose]);
  }
  blockEnd(piece, end, dir);
  if (buttoncheck) {
    pressSwitches(step.presses);
    blockSounds(step.pose, kinds);
  }
}

// BL:263-283: a standing block sinks into the goal, splits, or breaks a fragile tile and drops through it
function blockEnd(piece, end, dir) {
  const clip = piece.clip;
  if (end.win) {
    state.over = true;
    clip.gotoAndStop("end");
    clip.play();
  } else if (end.split) {
    piece.split = end.split;
    clip.gotoAndStop("split");
    clip.play();
  } else if (end.fall?.kind === "fragile") {
    clip.gotoAndStop("fallsquare");
    clip.play();
    board().tileAt(piece.xp, piece.yp)?.play();
    startFall(piece, "fragile", [0, 0], dir);
  }
}

function blockFall(piece, pose, fall, dir) {
  const way = fall.dir ?? dir;
  const label = way ? `fall${pose}${way}` : null;
  if (label && piece.clip.frameOf(label)) {
    piece.clip.gotoAndPlay(label);
  } else {
    piece.clip.stop();
  }
  startFall(piece, fall.kind, SPEEDS[fall.kind]?.[way] ?? [0, 0], way);
}

function startFall(piece, kind, [xs, ys], dir) {
  Object.assign(piece, { falling: true, deptherised: false, xs, ys, dir, rolling: false });
  state.holding.delete(piece.name);
  state.over = true;
  if (piece.name === "block" && NO_DETRACTOR.has(kind)) {
    board().root.set("detractor", false);
  }
}

// The kinds of the squares under a block: the anchor, then the other square of a lying block
function blockKinds(pose, [x, y]) {
  const kinds = [soundKind(x, y, false)];
  if (pose === "long") {
    kinds.push(soundKind(x + 1, y, false));
  } else if (pose === "far") {
    kinds.push(soundKind(x, y - 1, false));
  }
  return kinds;
}

// BL:339-437: one sound for a block on one kind of tile, a quieter half sound for each square otherwise
function blockSounds(pose, [first, second]) {
  if (pose === "up" || first === second) {
    if (FULL_SOUNDS[first]) {
      clonk("clonk", FULL_SOUNDS[first]);
    }
    return;
  }
  if (HALF_SOUNDS[first]) {
    clonk("clonk", HALF_SOUNDS[first]);
  }
  if (HALF_SOUNDS[second]) {
    clonk("clonk2", HALF_SOUNDS[second]);
  }
}

// BL:284-338, CL:114-140: each switch's sound, then each bridge on its list flashes and the ones that move start
function pressSwitches(presses) {
  for (const pressed of presses ?? []) {
    clonk("clonk", SWITCH_SOUNDS[pressed.kind]);
    for (const bridge of pressed.bridges) {
      const tile = board().tileAt(...bridge.at);
      if (bridge.flash) {
        tile?.child("flasher")?.gotoAndPlay(FLASHES[bridge.flash]);
      }
      if (bridge.turn) {
        tile?.play();
      }
    }
  }
}

// CL:49-172: the cube's rest or fall, its switch, a join, then its landing sound
function applyCube(name, step, joined) {
  const piece = state.pieces[name];
  const end = step.end ?? {};
  [piece.xp, piece.yp] = step.at;
  piece.rolling = false;
  piece.landedAt = state.ticks;
  state.holding.delete(name);
  reposition(piece);
  const kind = soundKind(piece.xp, piece.yp, true);
  if (end.fall) {
    const way = end.fall.dir ?? piece.dir;
    if (way && piece.clip.frameOf(`fall${way}`)) {
      piece.clip.gotoAndPlay(`fall${way}`);
    } else {
      piece.clip.stop();
    }
    // A cube at rest tipping off a bridge keeps no `dir` (CL:141-144), so the deptheriser reaches no further
    startFall(piece, "cube", SPEEDS.cube[way] ?? [0, 0], piece.dir);
  } else {
    piece.clip.gotoAndStop(CUBE_REST);
  }
  pressSwitches(step.presses);
  if (end.join && joined) {
    rejoin(piece, end.join, joined);
  }
  if (FULL_SOUNDS[kind]) {
    clonk(name === "a" ? "clonk2" : "clonk", FULL_SOUNDS[kind]);
  }
}

// CL:23-48: the cubes hide and the block lands across both squares (S1152/f290, f310)
function rejoin(piece, join, joined) {
  const block = state.pieces.block;
  state.selected = "block";
  for (const name of ["a", "b"]) {
    state.pieces[name].clip.visible = false;
    const cubeShadow = shadow(name);
    if (cubeShadow) {
      cubeShadow.visible = false;
    }
  }
  [block.xp, block.yp] = join.at;
  state.joinStep = joined;
  block.clip.gotoAndPlay(join.pose === "long" ? "longjoin" : "farjoin");
}

// A check's step: a piece that stops mid-roll (snap) or falls, applied at once
function applyChecked(steps) {
  if (!live()) {
    return;
  }
  state.clonked.clear();
  const { a, b } = state.pieces;
  if (!a.clip.visible && !b.clip.visible) {
    for (const step of steps) {
      applyBlock(step, false);
    }
    return;
  }
  // S320/f41: both cubes land again, so each one that stays plays its landing sound
  for (const name of ["a", "b"]) {
    const step = steps.find((item) => item.piece === name);
    if (step) {
      applyCube(name, step, null);
    } else {
      const cube = state.pieces[name];
      const kind = soundKind(cube.xp, cube.yp, true);
      if (FULL_SOUNDS[kind]) {
        clonk(name === "a" ? "clonk2" : "clonk", FULL_SOUNDS[kind]);
      }
    }
  }
}

function receiveRolled(value) {
  if (!live()) {
    return;
  }
  state.sent.shift();
  // Rolls started since this one was sent are already counted on the page
  state.page.moves = value.moves + state.sent.length;
  const steps = value.steps ?? [];
  if (!steps.length) {
    return;
  }
  const name = steps[0].piece;
  if (state.holding.has(name)) {
    applyLanding(name, steps);
  } else {
    state.ready.set(name, steps);
  }
}

// S1179/f38: Quit to Menu. The block leaves if it is the selected piece, the cubes always do, and the keys stop
function quit() {
  if (!live()) {
    return;
  }
  state.over = true;
  if (state.selected === "block") {
    state.pieces.block.clip.gotoAndPlay(QUIT_FRAME);
  }
  state.pieces.a.clip.gotoAndPlay(PHASE);
  state.pieces.b.clip.gotoAndPlay(PHASE);
}

// ---------- Each tick ----------

// BE:1-15, CE:1-12: a falling piece flies on, pulled down by gravity, lifting the tiles in front of it once
function fly(piece) {
  if (!piece.falling) {
    return;
  }
  if (!piece.deptherised) {
    piece.deptherised = true;
    const other = piece.name === "a" ? state.pieces.b : piece.name === "b" ? state.pieces.a : null;
    board().raise(piece.name, [piece.xp, piece.yp], piece.dir, other ? [other.xp, other.yp] : null);
  }
  piece.clip.x += piece.xs;
  piece.clip.y += piece.ys;
  piece.ys += GRAVITY;
}

// BE:119-122, CE:13-20: a piece far enough down ends the attempt, and the other cube fades
function fallen(piece) {
  if (piece.clip.y <= FALLEN) {
    return;
  }
  if (piece.name !== "block" && board().root.frame === PLAY_FRAME) {
    state.pieces[piece.name === "a" ? "b" : "a"].clip.gotoAndPlay(PHASE);
  }
  board().restart();
}

// BE:16-46: the nearer cube draws over the farther one, judged by where each is rolling to
function sortCubes() {
  const { a, b } = state.pieces;
  const near = (cube) => {
    const frame = cube.clip.frame;
    return cube.yp - (frame > 11 && frame < 21 ? 1 : 0) + (frame > 31 && frame < 41 ? 1 : 0);
  };
  const ay = near(a);
  const by = near(b);
  const aAbove = a.clip.zIndex > b.clip.zIndex;
  if (ay !== by ? ay < by === aAbove : a.xp > b.xp === aAbove) {
    [a.clip.zIndex, b.clip.zIndex] = [b.clip.zIndex, a.clip.zIndex];
  }
}

function tick() {
  if (!live()) {
    return;
  }
  for (const piece of Object.values(state.pieces)) {
    fly(piece);
  }
  sortCubes();
  for (const piece of Object.values(state.pieces)) {
    fallen(piece);
  }
  readKeys();
  if (state.checkAfter !== null && state.ticks > state.checkAfter) {
    state.checkAfter = null;
    state.page.send({ check: { rolling: rolling() } });
  }
  state.tapped.clear();
  state.ticks += 1;
}

// The pieces mid-roll now, or waiting on a landing frame for the bot
function rolling() {
  return Object.values(state.pieces)
    .filter((piece) => piece.rolling)
    .map((piece) => piece.name);
}

// ---------- Frame scripts ----------

function blockScript(clip, frame) {
  const piece = state.pieces.block;
  if (!piece || piece.clip !== clip) {
    return;
  }
  if (Object.values(REST).includes(frame)) {
    clip.stop();
    piece.dir = null;
  } else if (BLOCK_DIR_FRAMES[frame]) {
    piece.dir = BLOCK_DIR_FRAMES[frame];
  } else if (BLOCK_LANDINGS.has(frame)) {
    land("block");
  } else if (frame === WIN_DROP) {
    board().root.set("winning", true);
    clip.y += WIN_DROP_SPEED;
  } else if (frame === SPLIT_DONE) {
    split(piece);
  } else if (JOIN_LANDINGS.has(frame)) {
    joinLanding(piece);
  }
}

// S1152/f282: the cubes appear on the split table's squares, cube a selected. Their squares are set before they
// jump, since the original's jumps ran the cubes' frame scripts only after this one
function split(piece) {
  piece.clip.stop();
  const { a, b } = state.pieces;
  state.selected = "a";
  [a.xp, a.yp] = piece.split.a;
  [b.xp, b.yp] = piece.split.b;
  a.clip.gotoAndPlay("spawn");
  b.clip.gotoAndPlay("spawn2");
  a.clip.child("selecta")?.gotoAndPlay(RING_IN);
  if (a.clip.zIndex > b.clip.zIndex) {
    [a.clip.zIndex, b.clip.zIndex] = [b.clip.zIndex, a.clip.zIndex];
  }
}

// S1152/f290, f310: the joined block shows and lands. The landing's own jump to its resting frame ends the join at
// once (the original's play() after it ran before that frame's stop())
function joinLanding(piece) {
  const step = state.joinStep;
  state.joinStep = null;
  piece.clip.visible = true;
  const blockShadow = shadow("block");
  if (blockShadow) {
    blockShadow.visible = true;
  }
  reposition(piece);
  if (step) {
    applyBlock(step, true);
  }
}

function cubeScript(clip, frame) {
  const piece = Object.values(state.pieces).find((item) => item.clip === clip);
  if (!piece) {
    return;
  }
  if (frame === CUBE_REST) {
    clip.stop();
    piece.dir = null;
  } else if (CUBE_DIR_FRAMES[frame]) {
    piece.dir = CUBE_DIR_FRAMES[frame];
  } else if (CUBE_LANDINGS.has(frame)) {
    land(piece.name);
  } else if (frame === CUBE_APPEARS) {
    clip.visible = true;
    reposition(piece);
    clip.play();
  }
}

// ---------- Setup ----------

// The pieces, their frame scripts, and page.pieces for touch.js and the pause panel: press(dir, down), swap(),
// cubesOut(), rolling(), quit()
export function setupPieces(page) {
  state.page = page;
  page.board.onPlay = placePieces;
  page.board.onTick = tick;
  page.onMessage("rolled", receiveRolled);
  page.onMessage("checked", (value) => applyChecked(value?.steps ?? []));
  window.addEventListener("keydown", keyDown);
  window.addEventListener("keyup", keyUp);
  window.addEventListener("blur", () => page.held.clear());
  page.pieces = { press, swap, cubesOut, rolling, quit };
  return {
    scripts: [
      [BLOCK, blockScript],
      [CUBE, cubeScript],
    ],
  };
}
