from ageofwar.common.leaderboard import TOP, USER_DEFAULTS, Result, add_result, rank


def board(*results: Result) -> dict[int, dict]:
    users: dict[int, dict] = {}
    for result in results:
        users[result.user_id] = add_result(users.get(result.user_id, dict(USER_DEFAULTS)), result)
    return users


def test_a_player_keeps_their_fastest_win_per_difficulty_and_counts_them_all():
    users = board(
        Result(1, "Maya", "normal", 9000), Result(1, "Maya", "normal", 7000), Result(1, "Maya", "normal", 8000)
    )
    assert users[1]["best"] == {"normal": 7000} and users[1]["wins"] == {"normal": 3}


def test_the_name_follows_the_latest_win():
    users = board(Result(1, "Maya", "normal", 9000), Result(1, "Maya B", "harder", 20000))
    assert users[1]["name"] == "Maya B"


def test_each_difficulty_ranks_fastest_first_and_shows_your_place():
    users = board(
        Result(1, "Maya", "normal", 9000),
        Result(2, "Sam", "normal", 7000),
        Result(3, "Ana", "impossible", 30000),
    )
    boards = rank(users, 1)
    assert [row["name"] for row in boards["normal"]["top"]] == ["Sam", "Maya"]
    assert boards["normal"]["you"]["rank"] == 2 and boards["normal"]["you"]["id"] == "1"
    assert boards["harder"] == {"top": [], "you": None}
    assert boards["impossible"]["you"] is None


def test_the_top_list_is_cut_but_your_place_is_not():
    users = board(*(Result(n, f"P{n}", "normal", 1000 + n) for n in range(1, TOP + 5)))
    boards = rank(users, TOP + 3)
    assert len(boards["normal"]["top"]) == TOP
    assert boards["normal"]["you"]["rank"] == TOP + 3


def test_ties_go_to_the_lower_id_so_the_order_is_stable():
    users = board(Result(5, "Late", "normal", 5000), Result(2, "Early", "normal", 5000))
    assert [row["id"] for row in rank(users, 0)["normal"]["top"]] == ["2", "5"]
