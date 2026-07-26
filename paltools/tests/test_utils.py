from paltools.common.models import PalPlayer
from paltools.common.utils import diff_snapshots, format_playtime, snapshot_from_players


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


def test_format_playtime():
    assert format_playtime(30) == "<1m"
    assert format_playtime(2700) == "45m"
    assert format_playtime(3660) == "1h 1m"
    assert format_playtime(273120) == "3d 3h 52m"
