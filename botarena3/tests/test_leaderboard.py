from botarena3.common import leaderboard


def test_adding_counts_the_outcome_and_refreshes_the_name():
    entry = leaderboard.add(None, "win", "Maya")
    entry = leaderboard.add(entry, "loss", "Maya B")
    entry = leaderboard.add(entry, "draw", "Maya B")
    assert entry == {"name": "Maya B", "wins": 1, "losses": 1, "draws": 1}


def test_ranking_by_wins_then_fewest_losses():
    users = {
        1: {"pvp": {"name": "A", "wins": 3, "losses": 2, "draws": 0}},
        2: {"pvp": {"name": "B", "wins": 3, "losses": 1, "draws": 0}},
        3: {"pvp": {"name": "C", "wins": 5, "losses": 9, "draws": 1}},
        4: {"pvp": dict(leaderboard.DEFAULTS)},
        5: {"career": None},
    }
    board = leaderboard.rank(users, 1)
    assert [row["name"] for row in board["top"]] == ["C", "B", "A"]
    assert board["you"] == {"rank": 3, "id": "1", "name": "A", "wins": 3, "losses": 2, "draws": 0}
    assert leaderboard.rank(users, 4)["you"] is None
