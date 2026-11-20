from penguinwars.common.leaderboard import MEMBER_DEFAULTS, TOP, Result, add_result, rank


def entry(wins=0, knockouts=0, rounds=1, name="Ann"):
    return {"wins": wins, "knockouts": knockouts, "rounds": rounds, "name": name}


def test_rank_orders_by_wins_then_knockouts_then_lower_id():
    members = {5: entry(2, 1), 3: entry(2, 4), 9: entry(5, 0), 1: entry(2, 4)}
    board = rank(members, 3)
    assert [row["id"] for row in board["top"]] == ["9", "1", "3", "5"]
    assert board["you"]["rank"] == 3 and board["dm"] is False


def test_rank_keeps_ten_but_still_knows_where_you_stand():
    members = {n: entry(wins=100 - n) for n in range(1, 16)}
    board = rank(members, 15)
    assert len(board["top"]) == TOP and board["you"]["rank"] == 15


def test_players_with_no_counted_rounds_are_not_ranked():
    board = rank({1: entry(rounds=0), 2: entry(1)}, 1)
    assert [row["id"] for row in board["top"]] == ["2"] and board["you"] is None


def test_add_result_adds_a_round_and_renames():
    start = dict(MEMBER_DEFAULTS, name="Old")
    won = add_result(start, Result(1, "New", 3, True))
    assert won == {"wins": 1, "knockouts": 3, "rounds": 1, "name": "New"}
    assert add_result(won, Result(1, "New", 0, False)) == {"wins": 1, "knockouts": 3, "rounds": 2, "name": "New"}
