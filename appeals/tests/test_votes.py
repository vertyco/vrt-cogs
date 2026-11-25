from types import SimpleNamespace

from appeals.common.utils import tally_votes


def reaction(emoji: str, count: int, me: bool = False):
    return SimpleNamespace(emoji=emoji, count=count, me=me)


def test_bot_seed_reactions_are_not_counted():
    assert tally_votes([reaction("✅", 4, me=True), reaction("❌", 2, me=True)]) == (3, 1)


def test_reactions_not_seeded_by_bot_count_fully():
    assert tally_votes([reaction("✅", 2), reaction("❌", 1)]) == (2, 1)


def test_no_votes_cast_is_zero_zero():
    assert tally_votes([reaction("✅", 1, me=True), reaction("❌", 1, me=True)]) == (0, 0)


def test_missing_emoji_counts_as_zero():
    assert tally_votes([reaction("✅", 3, me=True)]) == (2, 0)


def test_other_emojis_are_ignored():
    assert tally_votes([reaction("👍", 5), reaction("❌", 2, me=True)]) == (0, 1)


def test_no_vote_reactions_returns_none():
    assert tally_votes([]) is None
    assert tally_votes([reaction("👍", 5)]) is None
