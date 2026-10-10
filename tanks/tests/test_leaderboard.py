from tanks.common.leaderboard import TOP, USER_DEFAULTS, Result, add_result, rank


def test_a_match_adds_to_a_players_numbers():
    entry = add_result(dict(USER_DEFAULTS), Result(1, "Maya", 3, True))
    assert entry == {"wins": 1, "kills": 3, "matches": 1, "name": "Maya"}
    entry = add_result(entry, Result(1, "Maya B", 2, False))
    assert entry == {"wins": 1, "kills": 5, "matches": 2, "name": "Maya B"}


def test_blowing_yourself_up_never_takes_kills_away():
    entry = add_result(dict(USER_DEFAULTS, kills=4), Result(1, "Maya", -2, False))
    assert entry["kills"] == 4 and entry["matches"] == 1


def test_the_board_ranks_by_wins_then_kills():
    users = {
        1: {"wins": 3, "kills": 10, "matches": 5, "name": "A"},
        2: {"wins": 5, "kills": 4, "matches": 9, "name": "B"},
        3: {"wins": 3, "kills": 12, "matches": 4, "name": "C"},
    }
    board = rank(users, 1)
    assert [row["name"] for row in board["top"]] == ["B", "C", "A"]
    assert board["you"] == {"rank": 3, "id": "1", "name": "A", "wins": 3, "kills": 10, "matches": 5}


def test_the_board_shows_the_top_ten_and_your_place_below_them():
    users = {uid: {"wins": 100 - uid, "kills": 0, "matches": 1, "name": f"P{uid}"} for uid in range(1, 16)}
    board = rank(users, 15)
    assert len(board["top"]) == TOP
    assert board["you"]["rank"] == 15


def test_a_player_with_no_matches_has_no_place():
    assert rank({}, 1) == {"top": [], "you": None}


def test_a_missing_name_still_shows_something():
    board = rank({7: dict(USER_DEFAULTS, wins=1)}, 7)
    assert board["top"][0]["name"] == "Unknown player"
