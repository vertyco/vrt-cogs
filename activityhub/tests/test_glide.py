"""The touch screen picker's motion (web/glide.js), run through Node with set times instead of a browser's clock"""

import json
import shutil
import subprocess

import pytest

from activityhub.common.server import HUB_WEB_DIR

# Each case's answer from glide.js, printed as JSON
NODE_SCRIPT = """
const { glide, restingPlace, speed, stretch } = await import(process.argv[2]);
const path = glide(2, 9, 0.02);
const back = glide(4.6, 4, 0.02);
const slow = glide(3.2, 3, 0);
const steps = Array.from({ length: 41 }, (_, i) => path.at((path.duration * i) / 40));
console.log(JSON.stringify({
  stretched: [-3, -1, -0.2, 0, 2, 5, 5.2, 6, 9].map((place) => stretch(place, 5)),
  speeds: {
    moving: speed([[0, 1], [16, 1.2], [32, 1.4], [48, 1.6]], 50),
    rested: speed([[0, 1], [16, 1.2], [32, 1.4]], 200),
    oneMove: speed([[40, 1]], 50),
    sameTime: speed([[40, 1], [40, 2]], 50),
    oldMovesOnly: speed([[0, 0], [10, 3], [200, 3.1], [210, 3.2]], 220),
  },
  resting: [
    restingPlace(2.4, 0, 9, 0.005),
    restingPlace(2.4, 0.004, 9, 0.005),
    restingPlace(2.4, 0.01, 9, 0.005),
    restingPlace(2.4, 0.1, 9, 0.005),
    restingPlace(2.4, -0.1, 9, 0.005),
  ],
  along: { duration: path.duration, start: path.at(0), end: path.at(path.duration), after: path.at(path.duration * 2),
    early: path.at(-30), firstSpeed: (path.at(1) - path.at(0)) / 1, steps },
  back: { duration: back.duration, start: back.at(0), end: back.at(back.duration) },
  slow: { duration: slow.duration, end: slow.at(slow.duration) },
}));
"""


@pytest.fixture(scope="module")
def answers(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so glide.js can't be run")
    script = tmp_path_factory.mktemp("node") / "glide.mjs"
    script.write_text(NODE_SCRIPT, encoding="utf-8")
    args = [node, str(script), (HUB_WEB_DIR / "glide.js").as_uri()]
    return json.loads(subprocess.run(args, capture_output=True, text=True, check=True, timeout=60).stdout)


def test_the_picker_stretches_less_and_less_past_its_ends(answers):
    below_3, below_1, below_02, first, inside, last, above_02, above_1, above_4 = answers["stretched"]
    # Inside the games it follows the finger exactly
    assert (first, inside, last) == (0, 2, 5)
    # Past either end it moves less than the finger, more for a longer pull, and never a whole game
    assert -1 < below_3 < below_1 < below_02 < 0
    assert below_02 > -0.2
    assert 5 < above_02 < above_1 < above_4 < 6
    assert above_02 - 5 == pytest.approx(-below_02)


def test_the_fingers_speed_comes_from_its_last_moments(answers):
    speeds = answers["speeds"]
    assert speeds["moving"] == pytest.approx(0.6 / 48)
    # A finger that stopped before lifting, or one move to go by, flicks nothing
    assert speeds["rested"] == 0
    assert speeds["oneMove"] == 0
    assert speeds["sameTime"] == 0
    # A quick start long before the finger lifts doesn't count, only the slow end does
    assert speeds["oldMovesOnly"] == pytest.approx(0.1 / 10)


def test_a_let_go_picker_rests_on_a_whole_game(answers):
    still, too_slow, flicked, hard, hard_back = answers["resting"]
    # Too slow to be a flick: the nearest game
    assert still == 2 and too_slow == 2
    # A flick carries on as far as an iPhone list would coast, and never past the ends
    assert flicked == 7
    assert hard == 9 and hard_back == 0


def test_a_glide_starts_at_the_fingers_speed_and_ends_on_the_game(answers):
    along = answers["along"]
    assert along["start"] == 2 and along["end"] == 9 and along["after"] == 9 and along["early"] == 2
    assert along["firstSpeed"] == pytest.approx(0.02, rel=0.01)
    # It only ever slows down, and never goes past the game
    steps = along["steps"]
    gaps = [b - a for a, b in zip(steps, steps[1:])]
    assert all(gap >= 0 for gap in gaps)
    assert all(later <= earlier + 1e-9 for earlier, later in zip(gaps, gaps[1:]))
    # Going back the other way from past an end, or letting go slowly, eases there in a short time
    assert answers["back"]["start"] == 4.6 and answers["back"]["end"] == 4
    assert answers["back"]["duration"] <= 450 and answers["slow"]["duration"] <= 450
    assert answers["slow"]["end"] == 3
