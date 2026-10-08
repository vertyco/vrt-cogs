import json
import shutil
import subprocess

import pytest

from activityhub.bundled import bricks, snake, twenty48
from activityhub.bundled.games import WEB_DIR
from activityhub.bundled.rng import Rng

SEEDS = [0, 1, 7, 123456789, 2**32 - 1, 3141592653]

# Plays rounds with the page's own rules.js files and prints what happened, so the Python replay can be
# checked against the exact code players run. The snake player is greedy: it heads for the apple and avoids
# crashing when it can, so rounds get long enough to place many apples
NODE_SCRIPT = """
const snakeRules = await import(process.argv[2]);
const rules2048 = await import(process.argv[3]);
const seeds = JSON.parse(process.argv[4]);

function rolls(seed) {
  const rng = snakeRules.makeRng(seed);
  return Array.from({ length: 50 }, () => rng.next());
}

function playSnake(seed) {
  const game = new snakeRules.SnakeGame(seed);
  const moves = [];
  const chooser = snakeRules.makeRng(seed ^ 0x5bd1e995);
  let tick = 0;
  while (!game.over && tick < 20000) {
    const [hx, hy] = game.body[0];
    const safe = Object.keys(snakeRules.DIRECTIONS).filter((h) => {
      if (h !== game.heading && !game.canTurn(h)) return false;
      const [dx, dy] = snakeRules.DIRECTIONS[h];
      const [x, y] = [hx + dx, hy + dy];
      const tail = game.body[game.body.length - 1];
      const hitsBody = game.body.some(([bx, by]) => bx === x && by === y) && !(tail[0] === x && tail[1] === y);
      return x >= 0 && x < snakeRules.SIZE && y >= 0 && y < snakeRules.SIZE && !hitsBody;
    });
    const toward = safe.filter((h) => {
      const [dx, dy] = snakeRules.DIRECTIONS[h];
      const before = Math.abs(game.food[0] - hx) + Math.abs(game.food[1] - hy);
      return Math.abs(game.food[0] - hx - dx) + Math.abs(game.food[1] - hy - dy) < before;
    });
    const options = toward.length ? toward : safe.length ? safe : [game.heading];
    const pick = options[chooser.pick(options.length)];
    if (pick !== game.heading && game.turn(pick)) moves.push([tick, pick]);
    game.step();
    tick += 1;
  }
  return { moves, ticks: tick, apples: game.apples };
}

function play2048(seed) {
  const board = new rules2048.Board(seed);
  const chooser = rules2048.makeRng(seed ^ 0x27d4eb2d);
  let moves = "";
  while (board.canMove()) {
    const direction = "ULDR"[chooser.pick(4)];
    if (board.move(direction)) moves += direction;
  }
  return { moves, score: board.score };
}

console.log(JSON.stringify(seeds.map((seed) => ({ seed, rolls: rolls(seed), snake: playSnake(seed), g2048: play2048(seed) }))));
"""


@pytest.fixture(scope="module")
def page_rounds(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the page rules can't be run")
    script = tmp_path_factory.mktemp("node") / "play.mjs"
    script.write_text(NODE_SCRIPT, encoding="utf-8")
    args = [
        node,
        str(script),
        (WEB_DIR / "snake" / "rules.js").as_uri(),
        (WEB_DIR / "2048" / "rules.js").as_uri(),
        json.dumps(SEEDS),
    ]
    output = subprocess.run(args, capture_output=True, text=True, check=True, timeout=60).stdout
    return json.loads(output)


def test_rng_matches_the_page(page_rounds):
    for case in page_rounds:
        rng = Rng(case["seed"])
        assert [rng.next() for _ in range(50)] == case["rolls"]


def test_snake_replay_matches_the_page(page_rounds):
    longest = 0
    for case in page_rounds:
        played = case["snake"]
        result = snake.replay(case["seed"], played["moves"], played["ticks"])
        assert result is not None, case["seed"]
        assert result[0] == played["apples"]
        longest = max(longest, played["apples"])
    # The greedy player has to get far enough for the check to mean something
    assert longest >= 20


def test_2048_replay_matches_the_page(page_rounds):
    for case in page_rounds:
        played = case["g2048"]
        assert len(played["moves"]) > 50
        assert twenty48.replay(case["seed"], played["moves"]) == played["score"]


def test_snake_replay_counts_the_least_time():
    assert snake.replay(5, [], 3) == (0, pytest.approx(0.42))


def test_snake_refuses_impossible_rounds():
    # Heading right from x=10, the 10th step hits the wall, so there can't be an 11th
    assert snake.replay(5, [], 10) is not None
    assert snake.replay(5, [], 11) is None
    assert snake.replay(5, [], 6) is not None  # ending early, before a crash, is fine
    assert snake.replay(5, [[0, "L"]], 5) is None  # straight back isn't a turn
    assert snake.replay(5, [[0, "R"]], 5) is None  # the way it's already going isn't a turn
    assert snake.replay(5, [[2, "U"], [1, "D"]], 5) is None  # out of order
    assert snake.replay(5, [[4, "U"]], 4) is None  # a turn after the last step
    assert snake.replay(5, [[0, "X"]], 5) is None
    assert snake.replay(5, "nope", 5) is None
    assert snake.replay(5, [], -1) is None
    assert snake.replay(5, [], True) is None
    assert snake.replay(5, [[True, "U"]], 5) is None


def test_2048_refuses_impossible_rounds():
    # A seed whose first board can't slide some way, so that move is one the page would never send
    seed, stuck = next((s, d) for s in range(1000) for d in "ULDR" if not twenty48.Board(s).move(d))
    assert twenty48.replay(seed, stuck) is None
    assert twenty48.replay(9, "X") is None
    assert twenty48.replay(9, ["U"]) is None
    assert twenty48.replay(9, "") == 0


def test_2048_merges_each_tile_once():
    board = twenty48.Board(1)
    board.cells = [2, 2, 2, 2, 4, 4, 8, 0, 0, 0, 0, 0, 2, 0, 0, 2]
    assert board.move("L")
    # The new tile only lands in an empty cell, so the merged ones are where the slide left them
    assert board.cells[0:2] == [4, 4] and board.cells[4:6] == [8, 8] and board.cells[12] == 4
    assert board.score == 4 + 4 + 8 + 4


LEVELS = bricks.load_levels(WEB_DIR / "brickbreaker" / "levels.json")


def test_brick_rounds_need_matching_bricks_and_time():
    first = bricks.breakable_count(LEVELS[0])
    assert bricks.run_is_plausible(LEVELS, first, 1, 60)
    assert not bricks.run_is_plausible(LEVELS, first - 1, 1, 60)  # a cleared level broke every brick
    assert not bricks.run_is_plausible(LEVELS, first, 1, 2)  # too fast
    assert not bricks.run_is_plausible(LEVELS, -1, 0, 60)
    assert not bricks.run_is_plausible(LEVELS, "5", 0, 60)
    assert not bricks.run_is_plausible(LEVELS, 5, None, 60)
    assert bricks.run_score(first, 1) == first * 10 + 100
