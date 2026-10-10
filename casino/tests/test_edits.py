from casino.common.catalog import game_key
from casino.common.edits import clean_casino, clean_game, parse_duration, whole


def test_cooldowns_read_seconds_or_clock_times_like_the_original():
    assert parse_duration("90") == 90
    assert parse_duration("1:30") == 90
    assert parse_duration("01:00:00") == 3600
    assert parse_duration("1:00:00:00") == 86400
    assert parse_duration("-5") is None and parse_duration("soon") is None


def test_game_changes_are_checked():
    assert clean_game("poker", {}, 1, 2)[1] == "That isn't one of the casino's games."
    assert clean_game("dice", {"min_bet": 200}, 25, 100)[1] == "The minimum bet can't be higher than the maximum."
    assert clean_game("dice", {"min_bet": 200, "max_bet": 300}, 25, 100) == ({"min_bet": 200, "max_bet": 300}, None)
    assert clean_game("double", {"multiplier": 2}, 10, 250)[1].startswith("This game's payout is set by the player")
    assert clean_game("dice", {"multiplier": "nan"}, 25, 100)[1].startswith("The multiplier must be between")
    assert clean_game("dice", {"access": -1}, 25, 100)[1] == "That must be a whole number, 0 or more."
    assert clean_game("dice", {"is_open": "yes"}, 25, 100)[1] == "That switch must be on or off."
    assert clean_game("dice", {"cooldown": "0:30", "multiplier": 0}, 25, 100) == (
        {"cooldown": 30, "multiplier": 0.0},
        None,
    )


def test_casino_changes_are_checked():
    assert clean_casino({"name": "x" * 31})[1] == "The casino's name must be 1 to 30 characters."
    assert clean_casino({"limit_amount": True})[1] == "The payout limit must be a whole number, 0 or more."
    assert clean_casino({"name": " Lucky ", "limit_on": True}) == ({"name": "Lucky", "limit_on": True}, None)


def test_game_names_accept_the_originals_spellings():
    assert [game_key(name) for name in ("BJ", "21", "hi-lo", "x2", "all in", "Craps")] == [
        "blackjack",
        "blackjack",
        "hilo",
        "double",
        "allin",
        "craps",
    ]
    assert game_key("poker") is None


def test_bad_numbers_give_a_problem_instead_of_crashing():
    for bad in ("--5", "²", "9" * 5000, "", "1.5", "abc"):
        assert whole(bad) is None
    for bad in ("--5", "²", "9" * 5000, "1:2:3:4:5", "abc", ""):
        assert parse_duration(bad) is None
    assert clean_game("dice", {"access": "²"}, 25, 100)[1] == "That must be a whole number, 0 or more."
    assert clean_game("dice", {"access": "9" * 5000}, 25, 100)[1] == "That must be a whole number, 0 or more."


def test_bad_cooldowns_name_the_rule():
    for bad in ("abc", "1:2:3:4:5", "²"):
        assert clean_game("dice", {"cooldown": bad}, 25, 100) == ({}, "Enter the cooldown as seconds or as HH:MM:SS.")
    assert clean_game("dice", {"cooldown": -1}, 25, 100)[1] == "That must be a whole number, 0 or more."


def test_multiplier_refuses_booleans():
    assert clean_game("dice", {"multiplier": True}, 25, 100) == ({}, "The multiplier must be a number.")


def test_casino_name_edges():
    assert clean_casino({"name": "x" * 30}) == ({"name": "x" * 30}, None)
    assert clean_casino({"name": "x" * 31})[1] is not None
    for bad in (None, 5, "   "):
        fields, problem = clean_casino({"name": bad})
        assert fields == {} and problem == "The casino's name must be 1 to 30 characters."


def test_all_in_has_no_range_or_multiplier():
    assert "no minimum or maximum" in clean_game("allin", {"min_bet": 5}, None, None)[1]
    assert "no minimum or maximum" in clean_game("allin", {"max_bet": 5}, None, None)[1]
    assert clean_game("allin", {"multiplier": 2}, None, None)[1].startswith("This game's payout is set")
    assert clean_game("allin", {"cooldown": 5}, None, None) == ({"cooldown": 5}, None)


def test_fields_a_game_does_not_have_are_ignored_and_problems_return_no_fields():
    assert clean_game("dice", {"colour": "red"}, 25, 100) == ({}, None)
    fields, problem = clean_game("dice", {"is_open": True, "access": -1}, 25, 100)
    assert fields == {} and problem
