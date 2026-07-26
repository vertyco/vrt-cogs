from datetime import datetime, timedelta, timezone

from discord import ui

from paltools.common.graph import render_player_graph, resolve_zone
from paltools.common.models import PalPlayer, ServerStatus
from paltools.common.utils import format_player_lines
from paltools.tasks.playerpoll import MAX_VIEW_CHARS, PlayerPoll


def player(name: str, level: int = 10, ping: float = 25.0) -> PalPlayer:
    return PalPlayer(name=name, playerId=name, userId=f"steam_{name}", level=level, ping=ping)


def texts(view: ui.LayoutView) -> list[str]:
    return [item.content for item in view.walk_children() if isinstance(item, ui.TextDisplay)]


def test_format_player_lines_truncates_to_budget():
    value = format_player_lines([player(f"Player{i:03}") for i in range(100)])
    assert len(value) <= 1024
    assert value.endswith("more")


def test_format_player_lines_full_roster_has_no_suffix():
    value = format_player_lines([player("Bob"), player("Alice")])
    assert value == "Bob (lvl 10, 25ms)\nAlice (lvl 10, 25ms)"


def test_status_view_without_servers():
    blocks = texts(PlayerPoll.status_view([]))
    assert "No enabled servers configured" in blocks[0]


def test_status_view_counts_players_not_names():
    offline_since = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
    statuses = [
        ServerStatus(name="Beta", online=False, last_online=offline_since),
        ServerStatus(name="Alpha", online=True, players=[player("Bob"), player("Alice")], max_players=32),
    ]
    blocks = texts(PlayerPoll.status_view(statuses))
    assert "Total Players: **2**" in blocks[0]
    # Padded to the longest name so the counts line up, and no player names anywhere
    assert blocks[1] == f"`Alpha:` **2**/32\n`Beta: ` Offline <t:{int(offline_since.timestamp())}:R>"
    assert "Bob" not in "".join(blocks)
    assert blocks[-1].startswith("-# Last Updated <t:")


def test_status_view_offline_without_history_says_offline():
    blocks = texts(PlayerPoll.status_view([ServerStatus(name="Alpha", online=False)]))
    assert blocks[1] == "`Alpha:` Offline"


def test_status_view_attaches_the_graph():
    view = PlayerPoll.status_view([ServerStatus(name="Alpha", online=True)], "players_1.png")
    galleries = [item for item in view.walk_children() if isinstance(item, ui.MediaGallery)]
    assert galleries[0].items[0].media.url == "attachment://players_1.png"


def test_status_view_never_truncates_a_full_fleet():
    """A roster panel starts dropping names at four full servers, counts do not"""
    statuses = [
        ServerStatus(
            name=f"Server With A Very Long Display Name {i:02}",
            online=True,
            players=[player(f"LongPlayerName{n:03}") for n in range(32)],
            max_players=32,
        )
        for i in range(30)
    ]
    view = PlayerPoll.status_view(statuses, "players_1.png")
    assert view.content_length() <= MAX_VIEW_CHARS
    assert view._total_children <= 40
    rendered = "".join(texts(view))
    for status in statuses:
        assert status.name in rendered


def test_render_player_graph_returns_a_png():
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    rows = [
        {"bucket": start + timedelta(minutes=5 * i), "server_name": name, "players": i % 7}
        for i in range(24)
        for name in ("Alpha", "Beta")
    ]
    png = render_player_graph(rows, 12)
    assert png.startswith(b"\x89PNG")


def test_render_player_graph_accepts_a_timezone():
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    rows = [{"bucket": start + timedelta(minutes=5 * i), "server_name": "Alpha", "players": i} for i in range(12)]
    assert render_player_graph(rows, 12, "America/New_York").startswith(b"\x89PNG")


def test_resolve_zone_falls_back_to_utc():
    # A name dropped from the tz database must not take the whole panel down with it
    zone, label = resolve_zone("Mars/Olympus_Mons")
    assert zone.key == "UTC"
    assert label


def test_resolve_zone_labels_with_the_abbreviation():
    zone, label = resolve_zone("America/New_York")
    assert zone.key == "America/New_York"
    # EST or EDT depending on when the suite runs, never the raw IANA name
    assert label in ("EST", "EDT")
