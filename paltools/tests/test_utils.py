from paltools.common.models import PalPlayer
from paltools.common.utils import chunk_lines, diff_snapshots, format_playtime, snapshot_from_players


def make(pid: str, name: str = "p") -> PalPlayer:
    return PalPlayer(name=name, playerId=pid, userId=f"steam_{pid}")


def test_snapshot_filters_placeholders():
    players = [make("AAA"), make("00000000000000000000000000000000"), make("")]
    snap = snapshot_from_players(players)
    assert list(snap) == ["AAA"]


def test_diff_join_and_leave():
    prev = snapshot_from_players([make("AAA"), make("BBB")])
    curr = snapshot_from_players([make("BBB"), make("CCC")])
    joined, left = diff_snapshots(prev, curr)
    assert [p.player_id for p in joined] == ["CCC"]
    assert [p.player_id for p in left] == ["AAA"]


def test_diff_no_changes():
    snap = snapshot_from_players([make("AAA")])
    joined, left = diff_snapshots(snap, snap)
    assert joined == [] and left == []


def test_chunk_lines_packs_into_one_block():
    assert chunk_lines(["a", "b", "c"], 2000) == ["a\nb\nc"]


def test_chunk_lines_splits_on_budget():
    lines = ["x" * 40 for _ in range(3)]
    blocks = chunk_lines(lines, 90)
    # 40 + 1 + 40 fits, a third would not
    assert blocks == ["\n".join(lines[:2]), lines[2]]
    assert all(len(block) <= 90 for block in blocks)


def test_chunk_lines_truncates_an_oversized_line():
    blocks = chunk_lines(["y" * 50], 10)
    assert blocks == ["y" * 9 + "…"]


def test_chunk_lines_empty():
    assert chunk_lines([], 2000) == []


def test_format_playtime():
    assert format_playtime(30) == "<1m"
    assert format_playtime(2700) == "45m"
    assert format_playtime(3660) == "1h 1m"
    assert format_playtime(273120) == "3d 3h 52m"
