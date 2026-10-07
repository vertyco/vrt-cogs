import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageSequence

# Import the generator standalone (like profile_runner does) so the whole cog isn't loaded
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator"))
import imgtools  # noqa: E402


def layer_sequence(timeline, layer):
    """Frame indexes a layer shows across the timeline, with repeats collapsed"""
    seq = []
    for _, indexes in timeline:
        if not seq or seq[-1] != indexes[layer]:
            seq.append(indexes[layer])
    return seq


def make_gif(durations, size=(8, 8)):
    frames = [Image.new("RGB", size, (i * 20 % 256, 0, 0)) for i in range(len(durations))]
    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0)
    return Image.open(BytesIO(buffer.getvalue()))


def test_frame_durations_treat_tiny_delays_like_browsers():
    assert imgtools.get_frame_durations(make_gif([0, 10, 20, 70])) == [100, 100, 20, 70]


def test_single_layer_keeps_its_own_timing():
    durations = [100, 40, 40, 200, 60]
    timeline = imgtools.sync_animations(durations, None)
    assert [d for d, _ in timeline] == durations
    assert [indexes for _, indexes in timeline] == [(i, 0) for i in range(5)]


def test_layers_with_dividing_loops_sync_exactly():
    # 1000ms background and a 500ms avatar: the avatar loops twice per background loop
    timeline = imgtools.sync_animations([100] * 10, [50] * 10)
    assert sum(d for d, _ in timeline) == 1000
    assert layer_sequence(timeline, 0) == list(range(10))
    assert layer_sequence(timeline, 1) == list(range(10)) * 2
    elapsed = 0
    for duration, (bg, pfp) in timeline:
        middle = elapsed + duration / 2
        assert bg == int(middle // 100) % 10
        assert pfp == int(middle // 50) % 10
        elapsed += duration


def test_uneven_loops_play_whole_loops_with_small_stretch():
    # 1000ms and 700ms loops: 2 and 3 loops line up within a few percent
    timeline = imgtools.sync_animations([100] * 10, [70] * 10)
    total = sum(d for d, _ in timeline)
    assert layer_sequence(timeline, 0) == list(range(10)) * 2
    assert layer_sequence(timeline, 1) == list(range(10)) * 3
    for loop in (2 * 1000, 3 * 700):
        assert abs(total / loop - 1) <= imgtools.MAX_SYNC_STRETCH


def test_frame_delays_are_gif_friendly():
    timeline = imgtools.sync_animations([33] * 30, [45] * 17)
    for duration, _ in timeline:
        assert duration % 10 == 0
        assert duration >= imgtools.GIF_MIN_FRAME_MS


def test_frame_budget_keeps_speed():
    timeline = imgtools.sync_animations([20] * 300, max_frames=50)
    assert len(timeline) <= 50
    assert sum(d for d, _ in timeline) == 6000
    seq = layer_sequence(timeline, 0)
    assert seq == sorted(seq)


def decode(data):
    return [frame.convert("RGBA") for frame in ImageSequence.Iterator(Image.open(BytesIO(data)))]


def assert_frames_match(expected, data):
    decoded = decode(data)
    assert len(decoded) == len(expected)
    for want, got in zip(expected, decoded):
        assert want.getchannel("A").tobytes() == got.getchannel("A").tobytes()
        opaque = want.getchannel("A")
        diff = ImageChops.difference(want.convert("RGB"), got.convert("RGB"))
        diff = Image.composite(diff, Image.new("RGB", diff.size), opaque)
        assert max(high for _, high in diff.getextrema()) <= 24


def test_save_gif_patches_against_previous_frame():
    base = Image.new("RGBA", (200, 100), (30, 90, 160, 255))
    frames = []
    for box in [(10, 10, 40, 40), (120, 10, 150, 40), (120, 10, 150, 40)]:
        frame = base.copy()
        ImageDraw.Draw(frame).rectangle(box, fill=(240, 200, 20, 255))
        frames.append(frame)
    # Only a small spot changes in the last frame, the square must stay where it moved to
    ImageDraw.Draw(frames[2]).rectangle((90, 80, 95, 85), fill=(240, 200, 20, 255))
    data = imgtools.save_gif(iter(frames), [100, 100, 100])
    assert_frames_match(frames, data)


def test_save_gif_keeps_black_opaque_next_to_transparency():
    frames = []
    for x in (10, 60):
        # Mostly transparent, so the transparent color takes the first palette slot ahead of black
        frame = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 15, 99, 35), fill=(0, 0, 0, 255))
        draw.rectangle((x, 20, x + 10, 30), fill=(250, 250, 250, 255))
        frames.append(frame)
    assert_frames_match(frames, imgtools.save_gif(iter(frames), [100, 100]))


@pytest.mark.parametrize("hole_x", [0, 40])
def test_save_gif_handles_moving_transparency(hole_x):
    frames = []
    for x in (hole_x, 70):
        frame = Image.new("RGBA", (100, 50), (200, 50, 50, 255))
        ImageDraw.Draw(frame).rectangle((x, 0, x + 20, 20), fill=(0, 0, 0, 0))
        frames.append(frame)
    assert_frames_match(frames, imgtools.save_gif(iter(frames), [100, 100]))
