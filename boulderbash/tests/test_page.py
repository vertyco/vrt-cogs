import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from boulderbash.common import rules, timing
from boulderbash.common.board import Board
from boulderbash.common.rules import (
    EXTREME,
    EXTREME_FIRST_ROW,
    EXTREMES,
    MODES,
    NORMAL,
    NORMAL2,
    ZEN,
    board_origin,
    grid_size,
    tile_size,
)

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))
# The page plays the bot's motion and counts Countdowns down with the same numbers the bot uses
SHARED = [
    "TICK_MS",
    "RAIN_STEP_MS",
    "MAX_COLORS",
    "STONE",
    "BASE",
    "REFILL",
    "COUNTDOWN",
    "TRIPLE",
    "BOMB",
    "WIPE",
    "SHIFTER",
    "WILD",
    "UNDO",
    "SHUFFLE",
    "HOLD",
    "COUNTDOWN_SHOWN",
    "COUNTDOWN_WARNING",
    "EXTREME_FIRST_ROW",
    "HOP_SPEED",
    "HOP_ACCEL",
    "DROP_SPEED",
    "DROP_ACCEL",
    "SLIDE_SPEED",
    "SLIDE_ACCEL",
    "RAIN_TRIGGER_Y",
    "RAIN_NEXT_TRIGGER",
    "CLEAR_ROW_MS",
    "UNDO_FIRST_FRAME",
    "UNDO_REWIND_FRAME",
    "UNDO_STOMP_FRAME",
    "UNDO_LAST_FRAME",
    "UNDO_FRAME_TICKS",
    "FLYER_START",
    "FLYER_END",
    "FLYER_SPEED",
    "CHUNK_SCALE",
    "CHUNK_VX",
    "CHUNK_VY",
    "CHUNK_VY_ADD",
    "CHUNK_DRAG",
    "CHUNK_GRAVITY",
    "CHUNK_FLOOR",
    "CHUNKS_PER_BLOCK",
    "ZOOMS",
    "EXTREMES",
    "TWO_BOARDS",
]
RUNNER = """
import { readFileSync } from "node:fs";
import { Motion, playMove, rainIn, shuffleTicks, undoTicks } from "./motion.mjs";

const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
const quiet = { smash() {}, newBlock: () => ({}), sound() {}, hide() {}, show() {} };

function total(steps) {
  let ms = 0;
  for (const wait of steps) {
    ms += wait;
  }
  return ms;
}

function motion(c) {
  const board = new Motion(c.rows, c.cols, c.tileW, c.tileH, c.top);
  c.before.forEach(([row, col]) => board.place(row, col, {}));
  return board;
}

console.log(JSON.stringify({
  moves: cases.moves.map((c) => total(playMove(motion(c), c.move, c.extreme, quiet))),
  rains: cases.rains.map((c) => total(rainIn(motion(c), c.firstRow, c.extreme, quiet))),
  undo: undoTicks(),
  shuffles: cases.walks.map((walk) => shuffleTicks(walk)),
}));
"""


def js_value(text: str):
    """A constant's value as written in motion.js: a number, a division, or a list of them"""
    division = re.fullmatch(r"([0-9.]+) / ([0-9.]+)", text)
    if division:
        return float(division.group(1)) / float(division.group(2))
    return json.loads(re.sub(r",(\s*[\]}])", r"\1", text))


def test_the_page_uses_the_bots_numbers():
    motion = (WEB / "motion.js").read_text(encoding="utf-8")
    for name in SHARED:
        found = re.search(rf"^export const {name} = (.+?);$", motion, re.M | re.S)
        assert found, f"motion.js has no const {name}"
        expected = getattr(rules, name)
        if isinstance(expected, tuple):
            assert js_value(found.group(1)) == json.loads(json.dumps(expected)), name
        else:
            assert js_value(found.group(1)) == pytest.approx(expected), name


def test_the_bomb_sounds_once():
    # The original played its explosion twice in the same tick, a bug the remake fixes
    scene = (WEB / "scene.js").read_text(encoding="utf-8")
    assert scene.count('this.sound("boom")') == 1


@pytest.mark.parametrize("name", SCRIPTS)
def test_page_scripts_parse(name, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the scripts can't be checked")
    # As a module, the way the browser loads it
    module = tmp_path / f"{name}.mjs"
    module.write_text((WEB / name).read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([node, "--check", str(module)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def find_tap(board: Board) -> tuple[int, int] | None:
    for row, col, cell in board.cells():
        if cell.special == rules.BOMB:
            return row, col
        for r, c in ((row, col + 1), (row + 1, col)):
            other = board.grid[r][c] if r < board.rows and c < board.cols else None
            if other is not None and cell.color < rules.MAX_COLORS and other.color == cell.color:
                return row, col
    return None


def move_cases(mode: int, seed: int, count: int) -> list[dict]:
    """Real moves from a seeded board, each with the board before it and the bot's busy ticks"""
    board = Board(mode, 0, random.Random(seed))
    board.start_level()
    tile_w, tile_h = tile_size(mode, board.level)
    top = board_origin(mode, board.level, 0)[1]
    cases = []
    for _ in range(count):
        found = find_tap(board)
        if found is None:
            break
        tap = board.tap(*found)
        if tap.move is None:
            tap = board.tap(*found)
        move = tap.move
        case = {"rows": board.rows, "cols": board.cols, "tileW": tile_w, "tileH": tile_h, "top": top}
        case.update(before=sorted(move.before), move=move.to_json(), extreme=mode in EXTREMES)
        case["busy"] = timing.board_ticks(board, move).busy
        cases.append(case)
    return cases


def rain_cases() -> list[dict]:
    cases = []
    for mode, level in ((NORMAL, 1), (NORMAL, 3), (NORMAL, 6), (NORMAL, 10), (NORMAL2, 1), (EXTREME, 1)):
        rows, cols = grid_size(mode, level)
        tile_w, tile_h = tile_size(mode, level)
        first = EXTREME_FIRST_ROW if mode in EXTREMES else 0
        before = [[row, col] for row in range(first, rows) for col in range(cols)]
        case = {"rows": rows, "cols": cols, "tileW": tile_w, "tileH": tile_h}
        case.update(top=board_origin(mode, level, 0)[1], before=before, firstRow=first, extreme=mode in EXTREMES)
        case["playable"] = timing.level_start_ms(mode, level)[1]
        cases.append(case)
    return cases


def test_the_page_animates_each_move_for_exactly_the_bots_busy_time(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the page's motion can't be checked")
    moves = [case for mode in MODES if mode != ZEN for seed in range(4) for case in move_cases(mode, seed, 30)]
    assert any(case["move"]["slides"] for case in moves)
    assert any(case["move"]["refill"] for case in moves)
    rains = rain_cases()
    walks = [0, 40, 165, 166, 200]
    (tmp_path / "motion.mjs").write_text((WEB / "motion.js").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "runner.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps({"moves": moves, "rains": rains, "walks": walks}), encoding="utf-8")
    result = subprocess.run(
        [node, str(tmp_path / "runner.mjs"), str(tmp_path / "cases.json")], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    page = json.loads(result.stdout)
    assert [round(ms / rules.TICK_MS) for ms in page["moves"]] == [case["busy"] for case in moves]
    assert page["rains"] == pytest.approx([case["playable"] for case in rains])
    assert page["undo"] == timing.undo_ticks()
    assert page["shuffles"] == [timing.shuffle_ticks(walk) for walk in walks]
