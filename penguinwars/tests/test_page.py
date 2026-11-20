import json
import random
import re
import shutil
import subprocess
from dataclasses import asdict
from math import atan2, ceil, hypot
from pathlib import Path

import pytest
from PIL import Image
from pytest import approx

from penguinwars.common.floe import CRACK, CRACK_SECONDS, GONE, SINK, SINK_SECONDS, Floe
from penguinwars.common.round import (
    BRACE_MASS,
    DIVE_SECONDS,
    DT,
    HEAVY_MASS,
    HIT_PUSH,
    HIT_REL,
    LEAP_SECONDS,
    MIN_POWER,
    PLAYER_SEAL_COOLDOWN,
    RADIUS,
    TICK_RATE,
    Round,
    friction,
)
from penguinwars.common.shop import DRAWN_KINDS, ITEMS
from penguinwars.common.tuning import Tuning

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))


def node_json(code):
    """Run module code in Node, where "motion" and "tags" stand for the page's own files, and read the JSON it prints"""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the page's code can't be run")
    for module in ("motion", "tags"):
        code = code.replace(f'"{module}"', json.dumps((WEB / f"{module}.js").as_uri()))
    result = subprocess.run(
        [node, "--input-type=module", "-e", code], capture_output=True, encoding="utf-8", timeout=60
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_nothing_loads_from_outside():
    for path in [*WEB.glob("*.html"), *WEB.glob("*.css"), *WEB.glob("*.js")]:
        assert "https://" not in path.read_text(encoding="utf-8"), path.name


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


def test_the_page_and_the_bot_agree_on_every_tile():
    page = node_json('import { tileList } from "motion"; console.log(JSON.stringify(tileList()))')
    bot = Floe(Tuning(), random.Random(1)).tiles
    assert [(t["q"], t["r"]) for t in page] == [(t.q, t.r) for t in bot]
    assert [t["ring"] for t in page] == [t.ring for t in bot]
    assert [t["x"] for t in page] == approx([t.x for t in bot])
    assert [t["z"] for t in page] == approx([t.z for t in bot])


def test_the_page_and_the_bot_agree_on_their_timings():
    page = node_json(
        'import { CRACK_SECONDS, DIVE_SECONDS, LEAP_SECONDS, SINK_SECONDS, TICK_RATE } from "motion";'
        "console.log(JSON.stringify([TICK_RATE, CRACK_SECONDS, SINK_SECONDS, DIVE_SECONDS, LEAP_SECONDS]))"
    )
    assert page == [TICK_RATE, CRACK_SECONDS, SINK_SECONDS, DIVE_SECONDS, LEAP_SECONDS]


STREAM = """
import { addFrame, sampleFrames, DRAW_DELAY, SNAP_GAP, TICK } from "motion";
const buffer = [];
const skipped = [];
const add = (n, now) => skipped.push(...addFrame(buffer, { n }, now));
const pick = (now) => {
  const { a, b, k } = sampleFrames(buffer, now, DRAW_DELAY);
  return { a: a.frame.n, b: b.frame.n, k };
};
const onTheBeat = (count) => {
  for (let n = 0; n < count; n += 1) {
    add(n, n * TICK);
  }
};
const show = (value) => console.log(JSON.stringify(value));
"""


def test_nothing_to_sample_before_the_first_frame():
    assert node_json(STREAM + "show(sampleFrames(buffer, 5, DRAW_DELAY));") is None


def test_two_updates_behind_sits_between_two_frames():
    picked = node_json(STREAM + "onTheBeat(6); show(pick(5.5 * TICK));")
    assert (picked["a"], picked["b"]) == (3, 4)
    assert picked["k"] == approx(0.5, abs=0.05)


def test_a_late_frame_holds_the_newest_and_keeps_its_movement():
    # Out of frames, but not for long: the penguin waits where it is and still counts as moving
    assert node_json(STREAM + "onTheBeat(6); show(pick(5 * TICK + 0.2));") == {"a": 4, "b": 5, "k": 1}


def test_a_long_gap_snaps_instead_of_gliding():
    # Back from the background: nothing arrived for over SNAP_GAP, so sampleFrames gives the newest frame alone
    picked = node_json(STREAM + "onTheBeat(6); show(pick(5 * TICK + SNAP_GAP + 0.01));")
    assert picked == {"a": 5, "b": 5, "k": 0}


def test_sampling_across_a_long_gap_gives_the_frame_after_it():
    code = "buffer.push({ at: 0, frame: { n: 0 } }, { at: 3, frame: { n: 1 } }); show(pick(3.01));"
    assert node_json(STREAM + code) == {"a": 1, "b": 1, "k": 0}


def test_the_first_frame_after_a_long_gap_drops_the_old_ones():
    seen = node_json(
        STREAM + "add(0, 0); add(1, TICK); add(2, 5);"
        "show({ left: buffer.map((e) => e.frame.n), skipped: skipped.map((e) => e.frame.n), picked: pick(5.01) });"
    )
    assert seen == {"left": [2], "skipped": [0, 1], "picked": {"a": 2, "b": 2, "k": 0}}


def test_a_pile_of_frames_lands_near_the_newest():
    # Back from the background with the socket still open: a few seconds of frames arrive at once. Only the last few
    # are kept, and the ones skipped are handed back so their tile changes still happen
    seen = node_json(
        STREAM + "for (let n = 0; n < 300; n += 1) { add(n, 10 + n * 0.0001); }"
        "show({ left: buffer.map((e) => e.frame.n), skipped: skipped.map((e) => e.frame.n),"
        "first: pick(10.03), soon: pick(10.03 + DRAW_DELAY + 4 * TICK + 0.001) });"
    )
    assert len(seen["left"]) <= 14
    assert seen["left"][-1] == 299
    assert seen["skipped"] + seen["left"] == list(range(300))
    assert seen["first"]["a"] >= 286
    assert seen["soon"]["b"] == 299 and seen["soon"]["k"] == 1


def test_a_page_not_drawing_keeps_only_a_few_frames():
    # A hidden page draws nothing, but frames keep arriving on the beat
    seen = node_json(
        STREAM + "onTheBeat(300);"
        "show({ left: buffer.map((e) => e.frame.n), skipped: skipped.map((e) => e.frame.n), picked: pick(299 * TICK) });"
    )
    assert len(seen["left"]) <= 14
    assert seen["skipped"] + seen["left"] == list(range(300))
    assert seen["picked"]["b"] >= 297


def test_frames_keep_their_arrival_order_whatever_their_numbers():
    # The frame number starts over every round, so a smaller number can be the newer frame
    picked = node_json(
        """
        import { addFrame, sampleFrames, DRAW_DELAY, TICK } from "motion";
        const buffer = [];
        [900, 901, 3, 4, 1, 2].forEach((f, index) => addFrame(buffer, { f, index }, index * TICK));
        const { a, b } = sampleFrames(buffer, 5.5 * TICK, DRAW_DELAY);
        console.log(JSON.stringify([buffer.at(-1).frame.index, a.frame.index, b.frame.index]));
        """
    )
    assert picked == [5, 3, 4]


def test_a_burst_of_frames_is_squeezed_not_dropped():
    # Held up for a moment by the network, then all arriving at once: every frame still plays, a little closer together
    seen = node_json(
        STREAM + "add(0, 0); for (let n = 1; n < 7; n += 1) { add(n, 0.2); }"
        "show({ left: buffer.map((e) => e.frame.n), skipped: skipped.length, last: buffer.at(-1).at, ahead: 4 * TICK });"
    )
    assert seen["left"] == list(range(7))
    assert seen["skipped"] == 0
    assert seen["last"] <= 0.2 + seen["ahead"] + 1e-9


@pytest.mark.parametrize("wobble, late_chance", [(0.015, 0), (0.025, 0), (0.04, 0), (0.015, 0.01)])
def test_ordinary_network_wobble_skips_nothing_and_stays_smooth(wobble, late_chance):
    # A frame held back holds back the ones behind it, since the connection keeps them in order. The drawing runs at
    # 60 a second and throws away what it has passed, as the scene does
    seen = node_json(
        STREAM
        + f"""
        let seed = 7;
        const random = () => {{
          seed = (seed * 1664525 + 1013904223) >>> 0;
          return seed / 2 ** 32;
        }};
        const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
        const arrivals = [];
        let held = 0;
        for (let n = 0; n < 9000; n += 1) {{
          const late = Math.abs(gauss()) * {wobble} + (random() < {late_chance} ? 0.12 : 0);
          held = Math.max(held, n * TICK + late);
          arrivals.push(held);
        }}
        let next = 0;
        let biggest = 0;
        let drawn = null;
        for (let now = 0; now < arrivals.at(-1); now += 1 / 60) {{
          while (next < 9000 && arrivals[next] <= now) {{
            add(next, arrivals[next]);
            next += 1;
          }}
          const sample = sampleFrames(buffer, now, DRAW_DELAY);
          if (sample) {{
            const at = sample.a.frame.n + (sample.b.frame.n - sample.a.frame.n) * sample.k;
            biggest = drawn === null ? 0 : Math.max(biggest, at - drawn);
            drawn = at;
            buffer.splice(0, buffer.indexOf(sample.a));
          }}
        }}
        show({{ skipped: skipped.length, biggest }});
        """
    )
    assert seen["skipped"] == 0
    # A draw at 60 a second covers half a frame. Wiping the buffer jumped about five
    assert seen["biggest"] < 1.5


def test_one_late_frame_never_shows_and_adds_no_delay_for_good():
    late_by = node_json(
        STREAM
        + """
        const lateBy = [];
        for (let n = 0; n < 200; n += 1) {
          add(n, n * TICK + (n === 5 ? 0.02 : 0));
          lateBy.push(buffer.at(-1).at - n * TICK);
        }
        show(lateBy);
        """
    )
    # The frames after the late one wait for it, so they stay evenly spaced and a moving penguin doesn't stutter
    assert late_by[6] == approx(0.02, abs=0.002)
    # And the delay it caused shrinks back
    assert late_by[-1] < 0.002


NAME_SPOTS = (0, 0), (390, 0), (0, 844), (390, 844), (195, 400)


@pytest.mark.parametrize("corner", NAME_SPOTS)
def test_names_never_overlap_or_leave_the_screen(corner):
    # six boxes bunched in a corner of a 390 px field, each 80 wide: every box inside the field, no two touching
    x, y = corner
    boxes = [{"x": x + n, "y": y + n, "width": 80, "height": 20} for n in range(6)]
    placed = node_json(
        f'import {{ layoutNames }} from "tags"; console.log(JSON.stringify(layoutNames({json.dumps(boxes)}, 390, 844)))'
    )
    rects = []
    for box, spot in zip(boxes, placed):
        left, top = spot["x"] - box["width"] / 2, box["y"] - spot["rise"]
        rects.append((left, top, left + box["width"], top + box["height"]))
    for left, top, right, bottom in rects:
        assert left >= 0 and top >= 0 and right <= 390 and bottom <= 844, rects
    for index, a in enumerate(rects):
        for b in rects[index + 1 :]:
            assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1], rects


def test_a_name_with_nothing_near_stays_put():
    code = (
        'import { layoutNames } from "tags";'
        "console.log(JSON.stringify(layoutNames([{ x: 200, y: 300, width: 80, height: 20 }], 390, 844)))"
    )
    assert node_json(code) == [{"x": 200, "rise": 0, "aim": 0, "beside": -1}]


def test_long_names_are_cut_by_whole_characters():
    family = "\U0001f468‍\U0001f469‍\U0001f467"
    name = "A" * 10 + family + "BBBB"
    code = (
        'import { fieldName } from "tags";'
        f'console.log(JSON.stringify([fieldName({json.dumps(name)}), fieldName("Captain Slick"), fieldName("ABCDEF", 4)]))'
    )
    assert node_json(code) == ["A" * 10 + family + "B…", "Captain Slick", "ABC…"]


# ---------- The player's own moves ----------

PLAYER = f"""
import {{
  aimFrom, BLEND_SECONDS, BRACE_MASS, edgePoint, Ghost, HEAVY_MASS, HIT_PUSH, HIT_REL, MIN_POWER,
  PLAYER_SEAL_COOLDOWN, Prediction, slideSpeed, stepBody, stopDistance, TICK, TOUCH,
}} from "motion";
const rules = {json.dumps(asdict(Tuning()))};
const SEAT = 2;
const show = (value) => console.log(JSON.stringify(value));
const still = (x, z) => ({{ x, z, vx: 0, vz: 0 }});
const pass = (thing, seconds, step = TICK) => {{
  for (let n = 0; n < Math.round(seconds / step); n += 1) {{
    thing.step(step, rules);
  }}
}};
// Slid from the middle of the ice toward +x, 0.1 seconds ago, with the bot's stream still at the start
const sliding = () => {{
  const mine = new Prediction();
  mine.slide(0, 0, 1, 0, 6, rules);
  pass(mine, 0.1);
  mine.shown(still(0, 0));
  return mine;
}};
"""


def tick_by_tick(speed, tuning):
    """What a lone body does on the bot, as [place, speed] after each of 90 updates"""
    place, rows = 0.0, []
    for _ in range(90):
        speed = friction(speed, DT, tuning)
        place += speed * DT
        rows.append([place, speed])
    return rows


def test_the_pages_slide_matches_the_bots_tick_for_tick():
    page = node_json(
        PLAYER
        + """
        const ghost = new Ghost();
        ghost.start(0, 0, 1, 0, 11);
        const rows = [];
        for (let n = 0; n < 90; n += 1) {
          ghost.step(TICK, rules);
          rows.push([ghost.x, ghost.vx]);
        }
        show(rows);
        """
    )
    for ours, theirs in zip(page, tick_by_tick(11.0, Tuning())):
        assert ours == approx(theirs, abs=0.001)


def test_step_body_matches_the_rounds_own_physics():
    game = Round(Tuning(), random.Random(1))
    for penguin in game.penguins[1:]:
        penguin.alive = False
    first = game.penguins[0]
    first.vx, first.vz = 6.0, -8.0
    start = [first.x, first.z]
    bot = []
    for _ in range(40):
        game.physics()
        bot.append([first.x, first.z, first.vx, first.vz])
    page = node_json(
        PLAYER
        + f"""
        const body = {{ x: {start[0]}, z: {start[1]}, vx: 6, vz: -8 }};
        const rows = [];
        for (let n = 0; n < 40; n += 1) {{
          stepBody(body, TICK, rules);
          rows.push([body.x, body.z, body.vx, body.vz]);
        }}
        show(rows);
        """
    )
    for ours, theirs in zip(page, bot):
        assert ours == approx(theirs, abs=1e-6)


@pytest.mark.parametrize("rate", [24, 30, 60, 90, 120, 144])
def test_the_ghost_stops_where_the_bot_stops_at_any_frame_rate(rate):
    code = f"const ghost = new Ghost(); ghost.start(0, 0, 1, 0, 11); pass(ghost, 3, 1 / {rate}); show(ghost.x);"
    assert node_json(PLAYER + code) == approx(tick_by_tick(11.0, Tuning())[-1][0], abs=0.001)


def test_the_ghost_moves_smoothly_between_the_bots_updates():
    steps = node_json(
        PLAYER
        + """
        const ghost = new Ghost();
        ghost.start(0, 0, 1, 0, 11);
        const steps = [];
        for (let n = 0; n < 40; n += 1) {
          const before = ghost.x;
          ghost.step(1 / 120, rules);
          steps.push(ghost.x - before);
        }
        show(steps);
        """
    )
    # The first drawn frame already moves it, and no frame stands still or steps back while it is going this fast
    assert steps[0] > 0.05
    assert all(step > 0.02 for step in steps), steps


def lone_slide(power, fish):
    """How far a penguin with nothing in its way really goes. It sets off from the edge of the ice, as a long slide from
    the middle would leave the ice, and one other penguin stands well clear so the round doesn't end"""
    game = Round(Tuning(), random.Random(1))
    first, other = game.penguins[:2]
    for penguin in game.penguins[2:]:
        penguin.alive = False
    other.x, other.z = 0.0, 4.0
    first.x, first.z, first.cd, first.fish = -4.6, 0.0, 0.0, fish
    assert game.slide(0, 1, 0, power)
    for _ in range(60):
        game.step()
    assert first.alive and first.vx == 0
    return first.x + 4.6


@pytest.mark.parametrize("fish", [False, True])
@pytest.mark.parametrize("power", [MIN_POWER, 0.2, 0.4, 0.6, 0.8, 1.0])
def test_the_aim_arrow_ends_where_a_lone_penguin_really_stops(power, fish):
    page = node_json(PLAYER + f"show(stopDistance(slideSpeed({power}, {json.dumps(fish)}, rules), rules));")
    assert page == approx(lone_slide(power, fish), abs=0.02)


def test_the_stop_distance_starts_fresh_each_time():
    page = node_json(PLAYER + "show([stopDistance(5, rules), stopDistance(0, rules), stopDistance(5, rules)]);")
    assert page[0] == page[2] > 0 and page[1] == 0


def test_a_short_press_is_not_an_aim():
    assert node_json(PLAYER + "show(aimFrom(5, 5, 390, 844));") is None


def test_an_aim_points_away_from_the_finger_and_grows_with_the_pull():
    # Upright, a full pull is 32% of the 390 px width past the 10 px the finger gets for free
    page = node_json(
        PLAYER
        + """
        show([
          aimFrom(-30, 40, 390, 844),
          aimFrom(0, 134.8, 390, 844),
          aimFrom(0, 900, 844, 390),
          aimFrom(0, 16, 844, 390),
        ]);
        """
    )
    assert page[0]["dx"] == approx(0.6) and page[0]["dz"] == approx(-0.8) and page[0]["power"] == approx(40 / 124.8)
    assert page[1]["dz"] == approx(-1) and page[1]["power"] == approx(1)
    assert page[2]["power"] == 1
    assert page[3]["power"] == approx(MIN_POWER)


def test_the_page_and_the_bot_agree_on_the_other_round_numbers():
    page = node_json(PLAYER + "show([MIN_POWER, PLAYER_SEAL_COOLDOWN, HIT_REL, HIT_PUSH, HEAVY_MASS, BRACE_MASS]);")
    assert page == [MIN_POWER, PLAYER_SEAL_COOLDOWN, HIT_REL, HIT_PUSH, HEAVY_MASS, BRACE_MASS]


def test_the_page_and_the_bot_agree_on_when_two_penguins_touch():
    assert node_json(PLAYER + "show(TOUCH);") == approx(RADIUS * 2)


@pytest.mark.parametrize("fish", [False, True])
@pytest.mark.parametrize("power", [0.0, 0.05, MIN_POWER, 0.5, 1.0, 3.0])
def test_the_pages_starting_speed_matches_the_bots(power, fish):
    game = Round(Tuning(), random.Random(1))
    penguin = game.penguins[0]
    penguin.cd, penguin.fish = 0.0, fish
    assert game.slide(0, 1, 0, power)
    page = node_json(PLAYER + f"show(slideSpeed({power}, {json.dumps(fish)}, rules));")
    assert page == approx(hypot(penguin.vx, penguin.vz))


def test_ghost_settles_only_when_stopped_and_close():
    seen = node_json(
        PLAYER
        + """
        const ghost = new Ghost();
        ghost.start(1, 2, 1, 0, 3);
        const moving = ghost.settled(1, 2);
        pass(ghost, 2);
        show({
          moving,
          stopped: [ghost.vx, ghost.vz],
          here: ghost.settled(ghost.x, ghost.z),
          near: ghost.settled(ghost.x + 0.1, ghost.z - 0.1),
          far: ghost.settled(ghost.x + 0.2, ghost.z),
        });
        """
    )
    assert seen == {"moving": False, "stopped": [0, 0], "here": True, "near": True, "far": False}


def test_a_new_slide_draws_from_the_ghost_at_once():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(1, 2, 0, -1, 6, rules);
        const first = mine.shown(still(1, 2));
        mine.step(1 / 60, rules);
        show([first, mine.shown(still(1, 2))]);
        """
    )
    assert seen[0] == {"x": 1, "z": 2, "vx": 0, "vz": -6}
    assert seen[1]["x"] == 1 and seen[1]["z"] < 1.92 and seen[1]["vz"] < -5.5


@pytest.mark.parametrize(
    "event, hands_back",
    [
        # A hit names only the one who was hit
        (["hit", 9000, 0, 50, 2], True),
        (["hit", 9000, 0, 50, 0], False),
        # Within 1.2 of the ghost, which is about 0.5 along
        (["hit", 160, 0, 50, 0], True),
        (["hit", 180, 0, 50, 0], False),
        # Within 1.2 of where the bot's stream draws the penguin: the ghost is past the spot by the time the news lands
        (["hit", -100, 0, 50, 0], True),
        (["bounce", 9000, 0, 50, 2], True),
        (["bounce", 50, 0, 50, 0], False),
        # A splash pushes every penguin in reach. Its seat is the seal's
        (["splash", 0, 200, 0], True),
        (["splash", 0, 300, 0], False),
        (["splash", 2, 9000, 0], False),
        (["crack", 2], False),
        (["fish", 50, 0], False),
    ],
)
def test_what_touches_this_seat_hands_the_ghost_back(event, hands_back):
    seen = node_json(
        PLAYER
        + f"""
        const mine = sliding();
        const at = mine.ghost.x;
        mine.hear({json.dumps(event)}, SEAT, rules);
        show({{ active: mine.ghost.active, shown: mine.shown(still(0, 0)).x, at }});
        """
    )
    assert seen["active"] is not hands_back
    # Handing back never moves it on the frame it happens: the blend starts where the ghost was
    assert seen["shown"] == approx(seen["at"])


def test_a_fall_ends_the_ghost_where_it_is_with_no_blend():
    seen = node_json(
        PLAYER
        + """
        const mine = sliding();
        mine.hear(["fall", SEAT], SEAT, rules);
        show([mine.ghost.active, mine.shown(still(-3, -3))]);
        """
    )
    assert seen == [False, {"x": -3, "z": -3, "vx": 0, "vz": 0}]


def test_someone_elses_fall_leaves_the_ghost_alone():
    assert node_json(PLAYER + 'const mine = sliding(); mine.hear(["fall", 0], SEAT, rules); show(mine.ghost.active);')


def test_the_ghost_hands_back_once_it_has_stopped_by_the_bot():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 3, rules);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        pass(mine, 2);
        const end = mine.ghost.x;
        const away = mine.shown({ ...still(end - 1, 0), vx: 1 }).x;
        const stillGhost = mine.ghost.active;
        mine.shown({ ...still(end - 0.1, 0), vx: 1 });
        show({ end, away, stillGhost, after: mine.ghost.active });
        """
    )
    assert seen["away"] == seen["end"]
    assert seen["stillGhost"] is True
    assert seen["after"] is False


def test_the_ghost_gives_up_after_two_and_a_half_seconds():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 3, rules);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        const moving = { ...still(-9, -9), vx: 1 };
        pass(mine, 2.4);
        mine.shown(moving);
        const before = mine.ghost.active;
        pass(mine, 0.2);
        mine.shown(moving);
        show([before, mine.ghost.active]);
        """
    )
    assert seen == [True, False]


def test_a_slide_the_bot_never_answers_hands_back_and_clears_the_wait():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 6, rules);
        pass(mine, 0.55);
        const before = [mine.ghost.active, mine.waitOn(0)];
        pass(mine, 0.1);
        show({ before, after: [mine.ghost.active, mine.waitOn(0)] });
        """
    )
    assert seen["before"][0] is True and seen["before"][1] > 0
    assert seen["after"] == [False, 0]


def test_a_slide_the_bot_answers_keeps_its_ghost_past_the_wait_for_an_answer():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 6, rules);
        pass(mine, 0.3);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        pass(mine, 0.5);
        show(mine.ghost.active);
        """
    )
    assert seen is True


def test_the_blend_runs_from_the_ghost_to_the_moving_stream_with_no_jump():
    seen = node_json(
        PLAYER
        + """
        const mine = sliding();
        mine.hear(["hit", 9000, 0, 50, SEAT], SEAT, rules);
        const shown = [];
        for (let n = 0; n < 12; n += 1) {
          mine.step(1 / 60, rules);
          shown.push(mine.shown(still(n * 0.01, 0)).x);
        }
        show({ shown, blend: BLEND_SECONDS, from: mine.from.x });
        """
    )
    assert seen["blend"] == 0.12
    shown = seen["shown"]
    # Gets there in 120 ms, a 60th of a second at a time, in steps of the same size or close to it
    assert shown[7:] == approx([n * 0.01 for n in range(7, 12)])
    steps = [abs(later - earlier) for earlier, later in zip([seen["from"], *shown], shown)]
    assert max(steps[:7]) < 2 * seen["from"] / 7


def test_a_new_slide_ends_a_blend():
    seen = node_json(
        PLAYER
        + """
        const mine = sliding();
        mine.hear(["bounce", 0, 0, 50, SEAT], SEAT, rules);
        mine.step(1 / 60, rules);
        mine.slide(2, 3, 0, 1, 5, rules);
        show(mine.shown(still(0, 0)));
        """
    )
    assert seen == {"x": 2, "z": 3, "vx": 0, "vz": 5}


def test_the_local_countdown_runs_the_ring_then_the_bots_takes_over():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const before = mine.waitOn(0.4);
        mine.slide(0, 0, 1, 0, 6, rules);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        const first = mine.waitOn(0);
        pass(mine, 0.5);
        const later = mine.waitOn(0);
        pass(mine, 0.5);
        show({ before, first, later, done: mine.waitOn(0.2) });
        """
    )
    assert seen["before"] == 0.4
    assert seen["first"] == Tuning().slide_wait
    assert seen["later"] == approx(Tuning().slide_wait - 0.5)
    assert seen["done"] == 0.2


def test_a_brace_shows_at_once_and_goes_with_no_answer():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.brace(rules);
        const first = [mine.bracing, mine.waitOn(0)];
        pass(mine, 0.25);
        const soon = mine.bracing;
        pass(mine, 0.1);
        show({ first, soon, after: [mine.bracing, mine.waitOn(0)] });
        """
    )
    assert seen["first"] == [True, Tuning().brace_wait]
    assert seen["soon"] is True
    assert seen["after"] == [False, 0]


def test_an_answered_brace_keeps_its_waiting_ring():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.brace(rules);
        pass(mine, 0.1);
        mine.hear(["brace", SEAT], SEAT, rules);
        pass(mine, 0.3);
        show([mine.bracing, mine.waitOn(0) > 0.5]);
        """
    )
    assert seen == [False, True]


def test_a_brace_stops_a_ghost_since_the_bot_stops_a_bracing_penguin():
    assert node_json(PLAYER + "const mine = sliding(); mine.brace(rules); show(mine.ghost.active);") is False


def test_a_dive_with_no_answer_is_called_off():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const seal = { state: "dive", x: 3, z: 4 };
        mine.dive(seal, rules);
        const ready = mine.sealWait;
        pass(mine, 0.25);
        const soon = seal.state;
        pass(mine, 0.1);
        show({ ready, soon, seal, wait: mine.sealWait });
        """
    )
    assert seen["ready"] == approx(DIVE_SECONDS + LEAP_SECONDS + Tuning().seal_wait)
    assert seen["soon"] == "dive"
    assert seen["seal"]["state"] == "swim"
    # It swims on around the ice from where it was, not from wherever its circle last had it
    assert seen["seal"]["ang"] == approx(atan2(4, 3))
    assert seen["wait"] == 0


def test_a_dive_called_off_leaves_a_seal_that_has_moved_on_alone():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const seal = { state: "dive", x: 3, z: 4 };
        mine.dive(seal, rules);
        seal.state = "leap";
        pass(mine, 0.4);
        show(seal.state);
        """
    )
    assert seen == "leap"


def test_an_answered_dive_carries_on_and_keeps_the_seal_waiting():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const seal = { state: "dive", x: 3, z: 4 };
        mine.dive(seal, rules);
        pass(mine, 0.1);
        mine.hear(["dive", SEAT, 100, 100], SEAT, rules);
        pass(mine, 1);
        show([seal.state, mine.sealWait]);
        """
    )
    assert seen[0] == "dive"
    # Counted again from the answer, which is nearer the bot's own count than the tap was
    assert seen[1] == approx(DIVE_SECONDS + LEAP_SECONDS + Tuning().seal_wait - 1)


def test_a_late_answer_to_a_called_off_dive_keeps_the_seal_waiting():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const seal = { state: "dive", x: 3, z: 4 };
        mine.dive(seal, rules);
        pass(mine, 0.4);
        const calledOff = mine.sealWait;
        mine.hear(["dive", SEAT, 100, 100], SEAT, rules);
        show([calledOff, mine.sealWait]);
        """
    )
    assert seen == [0, approx(DIVE_SECONDS + LEAP_SECONDS + Tuning().seal_wait)]


def test_a_new_seal_waits_as_the_bot_makes_it_wait():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.hear(["seal", 0], SEAT, rules);
        const others = mine.sealWait;
        mine.hear(["seal", SEAT], SEAT, rules);
        show([others, mine.sealWait]);
        """
    )
    assert seen == [0, PLAYER_SEAL_COOLDOWN]


def test_dropping_forgets_everything_at_once():
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        const seal = { state: "dive", x: 3, z: 4 };
        mine.slide(0, 0, 1, 0, 6, rules);
        pass(mine, 0.1);
        mine.brace(rules);
        mine.dive(seal, rules);
        mine.drop();
        pass(mine, 1);
        show({
          active: mine.ghost.active,
          bracing: mine.bracing,
          wait: mine.waitOn(0),
          seal: seal.state,
          shown: mine.shown(still(4, 4)),
        });
        """
    )
    assert seen == {
        "active": False,
        "bracing": False,
        "wait": 0,
        "seal": "dive",
        "shown": {"x": 4, "z": 4, "vx": 0, "vz": 0},
    }


@pytest.mark.parametrize("cracked", [False, True])
@pytest.mark.parametrize("sunk", [(), (60, 59, 58, 57, 56, 55, 54), tuple(range(0, 61, 2))])
def test_the_page_finds_the_same_edge_as_the_bot(sunk, cracked):
    floe = Floe(Tuning(), random.Random(1))
    if cracked:
        for tile in floe.tiles:
            tile.state = CRACK
    for index in sunk:
        floe.tiles[index].state = GONE if index % 4 else SINK
    angles = [n * 0.37 for n in range(20)]
    states = [tile.state for tile in floe.tiles]
    code = f"show({json.dumps(angles)}.map((angle) => edgePoint(angle, {json.dumps(states)})));"
    for angle, spot in zip(angles, node_json(PLAYER + code)):
        x, z, reach = floe.edge_point(angle)
        assert (spot["x"], spot["z"], spot["reach"]) == approx((x, z, reach))


# ---------- The ghost meets a penguin ----------

ALIVE_ONLY = 1


def pen_in_the_way(x, z, flags=ALIVE_ONLY, seat=1, fall=-1):
    return {"seat": seat, "x": x, "z": z, "fall": fall, "row": [0, 0, flags, 0]}


def meeting(pen, speed=8, fish="false"):
    """A ghost at the middle of the ice going +x meets this pen: what it is left with, and whether the wait began"""
    return node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, {speed}, rules, {fish});
        mine.meet([{json.dumps(pen)}], SEAT, rules);
        show({{ ...mine.ghost.body, waiting: mine.touchLeft > 0 }});
        """
    )


@pytest.mark.parametrize("fish", [False, True])
@pytest.mark.parametrize("target", ["plain", "heavy", "bracing"])
def test_the_ghosts_half_of_a_hit_matches_the_bots(fish, target):
    game = Round(Tuning(), random.Random(1))
    first, other = game.penguins[:2]
    first.x, first.z, first.vx, first.vz, first.heavy = 0.0, 0.0, 6.0, 7.0, fish
    other.x, other.z, other.heavy = 0.55, 0.6, target == "heavy"
    other.brace = 1.0 if target == "bracing" else 0.0
    flags = game.rows()[1][2]
    game.collide(0, 1)
    speed = hypot(6, 7)
    page = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 6 / {speed}, 7 / {speed}, {speed}, rules, {json.dumps(fish)});
        mine.meet([{json.dumps(pen_in_the_way(0.55, 0.6, flags))}], SEAT, rules);
        show(mine.ghost.body);
        """
    )
    assert page == approx({"x": first.x, "z": first.z, "vx": first.vx, "vz": first.vz})


def test_a_plain_hit_mostly_stops_and_a_fish_rolls_on_and_a_brace_throws_back():
    plain = meeting(pen_in_the_way(0.9, 0), speed=10)
    fish = meeting(pen_in_the_way(0.9, 0), speed=10, fish="true")
    brace = meeting(pen_in_the_way(0.9, 0, flags=ALIVE_ONLY + 2), speed=10)
    assert plain["vx"] == approx(0.5)
    assert fish["vx"] > 4
    assert brace["vx"] < -8


@pytest.mark.parametrize(
    "pen, speed",
    [
        # Not touching yet
        (pen_in_the_way(0.95, 0), 8),
        # Exactly on top of it, with no way to tell which way it lies
        (pen_in_the_way(0, 0), 8),
        # The player's own penguin, and one already falling
        (pen_in_the_way(0.9, 0, seat=2), 8),
        (pen_in_the_way(0.9, 0, fall=0.1), 8),
        # Closing exactly at the bot's limit, where it sends no hit
        (pen_in_the_way(0.9, 0), 2),
        # Behind the ghost, and a glancing touch that is hardly closing at all
        (pen_in_the_way(-0.9, 0), 8),
        (pen_in_the_way(0.1, 0.9), 8),
    ],
)
def test_what_the_ghost_slides_past(pen, speed):
    seen = meeting(pen, speed)
    assert seen == {"x": 0, "z": 0, "vx": speed, "vz": 0, "waiting": False}


def test_only_the_first_touch_counts():
    # The target stays drawn where it stood until the bot moves it, so a fish rolling on must not hit it again and again
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        const pens = [{json.dumps(pen_in_the_way(0.9, 0))}];
        mine.slide(0, 0, 1, 0, 10, rules, true);
        mine.meet(pens, SEAT, rules);
        mine.step(TICK, rules);
        const after = mine.ghost.vx;
        mine.meet(pens, SEAT, rules);
        show([after, mine.ghost.body.vx]);
        """
    )
    assert seen[0] > 3 and seen[0] == seen[1]


def test_a_touch_the_bot_never_answers_hands_back():
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 8, rules);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        mine.meet([{json.dumps(pen_in_the_way(0.9, 0))}], SEAT, rules);
        pass(mine, 0.25);
        mine.shown({{ ...still(5, 5), vx: 1 }});
        const soon = mine.ghost.active;
        pass(mine, 0.1);
        show([soon, mine.ghost.active, mine.blendLeft > 0]);
        """
    )
    assert seen == [True, False, True]


def test_a_new_slide_starts_clean_after_a_touch():
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        const pens = [{json.dumps(pen_in_the_way(0.9, 0))}];
        mine.slide(0, 0, 1, 0, 8, rules);
        mine.meet(pens, SEAT, rules);
        mine.slide(0, 0, 1, 0, 8, rules);
        const left = mine.touchLeft;
        mine.meet(pens, SEAT, rules);
        show([left, mine.ghost.body.vx < 1]);
        """
    )
    assert seen == [0, True]


def test_a_dropped_prediction_forgets_a_touch():
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 8, rules);
        mine.meet([{json.dumps(pen_in_the_way(0.9, 0))}], SEAT, rules);
        mine.drop();
        show(mine.touchLeft);
        """
    )
    assert seen == 0


def test_a_ghost_that_has_handed_back_touches_nothing():
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 8, rules);
        mine.handBack();
        mine.meet([{json.dumps(pen_in_the_way(0.9, 0))}], SEAT, rules);
        show(mine.touchLeft);
        """
    )
    assert seen == 0


def test_a_touch_takes_over_from_the_drawn_spot():
    # The time carried between updates is already on the drawn spot, so the body starting there must not run it again
    seen = node_json(
        PLAYER
        + f"""
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 10, rules, true);
        mine.step(0.02, rules);
        mine.meet([{json.dumps(pen_in_the_way(1.0, 0))}], SEAT, rules);
        const landed = mine.ghost.body.x;
        mine.step(0, rules);
        show([landed, mine.ghost.x]);
        """
    )
    assert seen[0] == approx(seen[1])


# ---------- A ghost gone wrong with no event from the bot ----------


def record_a_round(game, updates):
    """What the bot sends for its first seat over these updates, as [[x, z], events] in units"""
    rows = []
    for _ in range(updates):
        game.step()
        frame = game.frame()
        rows.append([[frame["p"][0][0] / 100, frame["p"][0][1] / 100], frame.get("e", [])])
    return rows


def replay(rows, start, direction, speed):
    """Feed those updates to the page's prediction, as the scene does, for a slide started from `start`. The page draws
    5 updates behind the bot, so each frame is one it would be drawing then. Gives the update the ghost handed back on,
    where the ghost's own sums stopped, and where the penguin was drawn at the end"""
    return node_json(
        PLAYER
        + f"""
        const rows = {json.dumps(rows)};
        const mine = new Prediction();
        mine.slide({start[0]}, {start[1]}, {direction[0]}, {direction[1]}, {speed}, rules);
        const ghostAlone = new Ghost();
        ghostAlone.start({start[0]}, {start[1]}, {direction[0]}, {direction[1]}, {speed});
        pass(ghostAlone, 3);
        let handedBack = null;
        let shown = null;
        let last = rows[0][0];
        rows.forEach(([[x, z], events], update) => {{
          mine.step(TICK, rules);
          events.forEach((event) => mine.hear(event, 0, rules));
          shown = mine.shown({{ x, z, vx: (x - last[0]) / TICK, vz: (z - last[1]) / TICK }});
          last = [x, z];
          if (handedBack === null && !mine.ghost.active) {{
            handedBack = update;
          }}
        }});
        show({{ handedBack, ghost: [ghostAlone.x, ghostAlone.z], shown: [shown.x, shown.z] }});
        """
    )


def test_gentle_contact_with_no_event_hands_back_once_both_have_stopped():
    # The bot's penguin mostly stops on a touch too soft for it to send a hit, while the ghost's sums slide on
    game = Round(Tuning(), random.Random(1))
    first, other = game.penguins[:2]
    for penguin in game.penguins[2:]:
        penguin.alive = False
    first.x, first.z, first.cd = 0.0, 0.0, 0.0
    other.x, other.z = 1.5, 0.0
    assert game.slide(0, 1, 0, 0.3)
    rows = record_a_round(game, 90)
    kinds = {event[0] for _, events in rows for event in events}
    assert kinds == {"slide"}
    seen = replay(rows, (0, 0), (1, 0), 0.3 * Tuning().slide_speed)
    assert seen["ghost"][0] == approx(1.07, abs=0.03)
    assert rows[-1][0][0] == approx(0.57, abs=0.03)
    # Long before the 2.5 seconds, the moment the ghost stops
    assert seen["handedBack"] < 35
    assert seen["shown"] == approx(rows[-1][0])


def test_a_ghost_that_stops_before_the_bots_answer_waits_for_it():
    # On a slow connection a short slide can be over before the bot's penguin has set off
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 1.2, rules);
        pass(mine, 0.55);
        const { stopped, x } = mine.ghost;
        mine.shown(still(0, 0));
        const waiting = mine.ghost.active;
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        mine.shown(still(0, 0));
        show({ stopped, away: x > 0.15, waiting, after: mine.ghost.active });
        """
    )
    assert seen == {"stopped": True, "away": True, "waiting": True, "after": False}


def test_a_ghost_still_moving_stays_when_the_stream_stands_still():
    # A long stall in the bot's frames holds the stream still, which says nothing about where the slide is going
    seen = node_json(
        PLAYER
        + """
        const mine = new Prediction();
        mine.slide(0, 0, 1, 0, 8, rules);
        mine.hear(["slide", SEAT, 0], SEAT, rules);
        pass(mine, 0.1);
        mine.shown(still(0, 0));
        show(mine.ghost.active);
        """
    )
    assert seen is True


def test_a_slide_started_while_knocked_hands_back_once_both_have_stopped():
    # The drawn spot trails the bot's by 5 updates at full speed, so the two slides run side by side, well apart. One
    # other penguin stands well clear, so the round isn't decided and the bot takes the slide
    game = Round(Tuning(), random.Random(1))
    first, other = game.penguins[:2]
    for penguin in game.penguins[2:]:
        penguin.alive = False
    other.x, other.z = 0.0, -4.0
    first.x, first.z, first.vx, first.cd = -2.0, 0.0, 9.0, 0.0
    drawn = record_a_round(game, 5)
    first.cd = 0.0
    assert game.slide(0, 0, 1, 0.3)
    rows = drawn + record_a_round(game, 75)
    seen = replay(rows[5:], drawn[0][0], (0, 1), 0.3 * Tuning().slide_speed)
    assert abs(seen["ghost"][0] - rows[-1][0][0]) > 0.5
    assert seen["handedBack"] < 40
    assert seen["shown"] == approx(rows[-1][0])


CLOCK = """
import { addFrame, sampleFrames, stepClock, newClock, DRAW_DELAY, TICK } from "motion";
let seed = 11;
const random = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 2 ** 32;
};
const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
"""


@pytest.mark.parametrize("rate", [30, 60])
def test_a_run_of_hits_with_jittery_frames_loses_no_frame(rate):
    # Three hits in 0.3 s, each freezing the drawing for its longest hold, with frames arriving up to 60 ms off the
    # beat. The drawing falls behind during each hold, and none of the bot's frames may be pushed out unseen
    seen = node_json(
        CLOCK
        + f"""
        let lost = 0;
        let worst = 0;
        for (let run = 0; run < 200; run += 1) {{
          const buffer = [];
          const clock = newClock();
          const arrivals = [];
          let held = 0;
          for (let n = 0; n < 120; n += 1) {{
            held = Math.max(held, n * TICK + Math.abs(gauss()) * 0.06);
            arrivals.push(held);
          }}
          let next = 0;
          let skipped = 0;
          let hit = 0;
          const hits = [0.5, 0.65, 0.8];
          for (let now = 0.01; now < 3.5; now += 1 / {rate}) {{
            while (next < 120 && arrivals[next] <= now) {{
              skipped += addFrame(buffer, {{ n: next }}, arrivals[next]).length;
              next += 1;
            }}
            if (hit < 3 && now >= hits[hit]) {{
              clock.freeze = 0.095;
              hit += 1;
            }}
            stepClock(clock, 1 / {rate}, now);
            worst = Math.max(worst, clock.lag);
            const sample = sampleFrames(buffer, now - clock.lag, DRAW_DELAY);
            if (sample) {{
              buffer.splice(0, buffer.indexOf(sample.a));
            }}
          }}
          lost += skipped > 0 ? 1 : 0;
        }}
        console.log(JSON.stringify({{ lost, worst }}));
        """
    )
    assert seen["lost"] == 0
    assert seen["worst"] <= 0.15 + 1e-9


def test_a_freeze_holds_the_clock_then_catches_up_and_a_long_gap_clears_it():
    seen = node_json(
        CLOCK
        + """
        const clock = newClock();
        stepClock(clock, 1 / 60, 10);
        clock.freeze = 0.095;
        const held = [stepClock(clock, 1 / 60, 10.0167), stepClock(clock, 1 / 60, 10.0333)];
        const lagAfterHold = clock.lag;
        clock.freeze = 0;
        const fast = stepClock(clock, 1 / 60, 10.05);
        clock.freeze = 0.09;
        const apart = stepClock(clock, 1 / 60, 12);
        console.log(JSON.stringify({ held, lagAfterHold, fast, apart, lag: clock.lag, freeze: clock.freeze, away: clock.away }));
        """
    )
    assert seen["held"] == [0, 0]
    assert seen["lagAfterHold"] == approx(0.0333, abs=0.001)
    assert seen["fast"] == approx(1.5 / 60)
    assert seen["apart"] == approx(1 / 60)
    assert seen["lag"] == 0 and seen["freeze"] == 0 and seen["away"] is True


TOUCH_RULES = (
    "const rules = { slide_speed: 11, friction_share: 1.7, friction_fixed: 1.4, slide_wait: 0.9, brace_wait: 1.2 };"
)


def run_a_touch(flags):
    return node_json(
        'import { Prediction } from "motion";'
        + TOUCH_RULES
        + f"""
        const prediction = new Prediction();
        prediction.slide(0, 0, 1, 0, 11, rules, false);
        const pens = [{{ seat: 1, fall: -1, x: 1.2, z: 0, row: [0, 0, {flags}, 0] }}];
        let touch = null;
        for (let i = 0; i < 60 && !touch; i += 1) {{
          prediction.step(1 / 60, rules);
          touch = prediction.meet(pens, 0, rules);
          if (touch) {{
            touch = {{ ...touch }};
          }}
        }}
        const near = prediction.echoes(["hit", 70, 0, 100, 1], 0);
        const again = prediction.echoes(["hit", 70, 0, 100, 1], 0);
        console.log(JSON.stringify({{ touch, near, again }}));
        """
    )


def test_the_ghost_reports_a_touch_with_its_contact_point_and_strength():
    seen = run_a_touch(0)
    touch = seen["touch"]
    assert touch["bracing"] is False and touch["seat"] == 1
    assert 0.4 < touch["x"] < 1.0 and touch["z"] == approx(0, abs=1e-6)
    assert touch["strength"] == approx(1.0, abs=0.1)
    # The bot's own word on that same hit is skipped, once
    assert seen["near"] is True and seen["again"] is False


def test_a_touch_on_a_bracing_penguin_is_a_bounce():
    assert run_a_touch(2)["touch"]["bracing"] is True


def test_the_bots_word_on_someone_elses_hit_is_not_skipped_even_beside_the_touch():
    seen = node_json(
        'import { Prediction } from "motion";'
        + TOUCH_RULES
        + """
        const prediction = new Prediction();
        prediction.slide(0, 0, 1, 0, 11, rules, false);
        const pens = [{ seat: 1, fall: -1, x: 1.2, z: 0, row: [0, 0, 0, 0] }];
        for (let i = 0; i < 60; i += 1) {
          prediction.step(1 / 60, rules);
          prediction.meet(pens, 0, rules);
        }
        console.log(JSON.stringify({ stranger: prediction.echoes(["hit", 70, 0, 100, 4], 0), other: prediction.echoes(["crack", 3], 0) }));
        """
    )
    assert seen == {"stranger": False, "other": False}


def test_the_bots_word_on_the_touch_is_found_by_who_it_names_wherever_it_lands():
    seen = node_json(
        'import { Prediction } from "motion";'
        + TOUCH_RULES
        + """
        const prediction = new Prediction();
        prediction.slide(0, 0, 1, 0, 11, rules, false);
        const pens = [{ seat: 1, fall: -1, x: 1.2, z: 0, row: [0, 0, 0, 0] }];
        for (let i = 0; i < 60; i += 1) {
          prediction.step(1 / 60, rules);
          prediction.meet(pens, 0, rules);
        }
        console.log(JSON.stringify({
          bounce: prediction.echoes(["bounce", 900, 0, 100, 3], 0),
          hit: prediction.echoes(["hit", 900, 0, 100, 1], 0),
        }));
        """
    )
    # A bounce names the player as its attacker, so one naming someone else isn't the player's. A hit names the struck
    # penguin, and the page may draw it a unit or more from where the bot has it
    assert seen == {"bounce": False, "hit": True}


@pytest.mark.parametrize("stall", [0.3, 0.45, 0.49])
def test_a_stall_then_a_burst_never_makes_a_penguin_leap(stall):
    # Frames held back by the network arrive all at once. The drawing, at 60 a second, crosses them smoothly instead of
    # in one step. Steps are in ticks of the bot's frames
    seen = node_json(
        STREAM
        + f"""
        let drawn = null;
        let biggest = 0;
        let n = 0;
        const send = (now) => {{
          while (n * TICK <= now) {{
            add(n, now);
            n += 1;
          }}
        }};
        for (let now = 0; now < 3; now += 1 / 60) {{
          if (now < 1 || now >= 1 + {stall}) {{
            send(now);
          }}
          const sample = sampleFrames(buffer, now, DRAW_DELAY);
          if (sample) {{
            const at = sample.a.frame.n + (sample.b.frame.n - sample.a.frame.n) * sample.k;
            biggest = drawn === null || now < 1.2 ? 0 : Math.max(biggest, at - drawn);
            drawn = at;
            buffer.splice(0, buffer.indexOf(sample.a));
          }}
        }}
        show({{ biggest, skipped: skipped.length }});
        """
    )
    assert seen["biggest"] <= 3.5, seen


# The page's table for each kind of look, as the file it is in and its name there
LOOK_TABLES = {
    "skin": ("models.js", "SKINS"),
    "hat": ("models.js", "HAT_LOOKS"),
    "face": ("models.js", "FACE_LOOKS"),
    "neck": ("models.js", "NECK_LOOKS"),
    "back": ("models.js", "BACK_LOOKS"),
    "trail": ("fx.js", "TRAILS"),
    "cheer": ("fx.js", "CHEERS"),
    "splash": ("fx.js", "SPLASHES"),
}


def test_every_item_on_sale_has_a_shape():
    assert set(LOOK_TABLES) == set(DRAWN_KINDS)
    for kind, (file, name) in LOOK_TABLES.items():
        source = (WEB / file).read_text(encoding="utf-8")
        table = re.search(rf"^(?:export )?const {name} = \{{\n(.*?)^\}};", source, re.S | re.M)
        assert table, name
        # A table's own keys are the lines indented once, in the catalog's order
        ids = re.findall(r"^  (\w+): ", table.group(1), re.M)
        assert ids == [item for item, info in ITEMS.items() if info["kind"] == kind], (name, ids)


# A card's picture is one tile of looks.webp, found by the item's place in the catalog
LOOKS_ACROSS = 8
LOOKS_TILE = 96


def test_the_looks_sheet_holds_a_picture_for_every_drawn_item():
    across = re.search(r"^const THUMBS_ACROSS = (\d+);", (WEB / "panels.js").read_text(encoding="utf-8"), re.M)
    assert int(across.group(1)) == LOOKS_ACROSS
    # Titles and name styles are text, so they have no picture. They come after every drawn item in the catalog
    drawn = [item for item, info in ITEMS.items() if info["kind"] in DRAWN_KINDS]
    assert drawn == list(ITEMS)[: len(drawn)]
    with Image.open(WEB / "looks.webp") as sheet:
        assert sheet.size == (LOOKS_ACROSS * LOOKS_TILE, ceil(len(drawn) / LOOKS_ACROSS) * LOOKS_TILE)
        for place, item in enumerate(drawn):
            left, top = place % LOOKS_ACROSS * LOOKS_TILE, place // LOOKS_ACROSS * LOOKS_TILE
            tile = sheet.crop((left, top, left + LOOKS_TILE, top + LOOKS_TILE))
            # An empty tile is one flat color
            assert len(tile.getcolors(LOOKS_TILE * LOOKS_TILE)) > 100, item
