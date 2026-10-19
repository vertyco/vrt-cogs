"""A player's saved progress: plain functions over the dict the cog keeps for each player in its Config.

Nothing here touches Red or the disk, so the live session and the page's actions share it. Every function returns a
new dict and leaves the one it was given alone.
"""

import copy
import typing as t

from .levels import LEVEL_COUNT

Progress = dict[str, t.Any]

START_COINS = 1000
WIN_COINS = 40
# What one purchase of three costs, in coins (the original's defaults)
PRICES = {"tray": 300, "hand": 1900, "shuffle": 1500, "super": 1900, "bomb": 1900}
# The level at which each booster unlocks (PowerupSettingsDataService defaults; Demolish is the remake's own fifth)
UNLOCK_LEVELS = {"tray": 6, "hand": 8, "shuffle": 14, "super": 18, "bomb": 17}
# Boosters in one purchase (TryToPurchasePowerup, RVA 0x5C49FB8)
PACK = 3
REVIVE_PRICE = 900
# The Super Unicorn (UnipigService #10538): its button shows from IconRevealLevel, wins count from UnlockLevel, and
# ActivationLevelAmount of them make it active until the first fail
UNICORN_ICON_LEVEL = 111
UNICORN_UNLOCK_LEVEL = 121
UNICORN_WINS = 10
# More popup and tutorial ids than the game has, so a page can't grow the saved list without end
MAX_SHOWN = 200


class Refused(Exception):
    """An action the player can't do, worded in plain words for the page to show."""


def defaults() -> Progress:
    """The progress of a player who has never played. Config registers these as its user defaults."""
    return {
        "level": 1,
        "coins": START_COINS,
        "stock": {booster: 0 for booster in PRICES},
        "claimed": [],
        "used": [],
        "shown": [],
        "unicorn": {"wins": 0, "active": False},
        "best": 1,
        # True once level 2,600 is won: the level picker opens and wins stop moving `level`
        "cleared": False,
    }


def win(progress: Progress, n: int) -> Progress:
    """The progress after winning level n: 40 more coins, and the next level when n was the player's current one.

    Winning level 2,600 marks every level cleared, and from then on a win only pays coins, whatever level was
    picked.
    """
    after = copy.deepcopy(progress)
    after["coins"] += WIN_COINS
    count_unicorn_win(after)
    if after["cleared"] or n != after["level"]:
        return after
    if n >= LEVEL_COUNT:
        after["cleared"] = True
    else:
        after["level"] = n + 1
        after["best"] = max(after["best"], after["level"])
    return after


def count_unicorn_win(progress: Progress) -> None:
    """A win counts toward the Super Unicorn once the player has reached its unlock level, until it is active; the
    tenth makes it active (UnipigLogic$$SyncOnWin, RVA 0x9C095F4; CompleteProgressStep, RVA 0x9C08034). The wins need
    not be in a row. Changes `progress` in place."""
    unicorn = progress["unicorn"]
    if unicorn["active"] or (not progress["cleared"] and progress["level"] < UNICORN_UNLOCK_LEVEL):
        return
    unicorn["wins"] += 1
    if unicorn["wins"] >= UNICORN_WINS:
        unicorn["active"] = True


def give_up(progress: Progress) -> Progress:
    """The progress after the player left a failed level without reviving it (by Retry or by leaving the fail panel):
    an active Super Unicorn is lost and its wins start again from 0; before it is active a fail changes nothing
    (UnipigLogic$$SyncOnLose, RVA 0x9C07D70, called when the level's life is let go, not on the fail itself)."""
    after = copy.deepcopy(progress)
    if after["unicorn"]["active"]:
        after["unicorn"] = {"wins": 0, "active": False}
    return after


def profile(progress: Progress, user_id: int) -> Progress:
    """What the page is told about a player: their progress, the booster prices and the level count.

    Discord ids are 64-bit, which a page's numbers cannot hold exactly, so the id goes out as text.
    """
    return {
        **copy.deepcopy(progress),
        "user": str(user_id),
        "prices": dict(PRICES),
        "unlocks": dict(UNLOCK_LEVELS),
        "pack": PACK,
        "revive_price": REVIVE_PRICE,
        "levels": LEVEL_COUNT,
        "unicorn_levels": {"icon": UNICORN_ICON_LEVEL, "unlock": UNICORN_UNLOCK_LEVEL, "wins": UNICORN_WINS},
    }


def check_booster(booster: t.Any) -> str:
    """The booster's name, or Refused when the page sent something that isn't one of the five bar boosters."""
    if type(booster) is not str or booster not in PRICES:
        raise Refused("That isn't a booster.")
    return booster


def unlocked(progress: Progress, booster: str) -> bool:
    """True once the player's level has reached the booster's unlock level (every booster, after level 2,600)."""
    return progress["cleared"] or progress["level"] >= UNLOCK_LEVELS[booster]


def claim(progress: Progress, booster: str) -> Progress:
    """Take the free one in a booster's unlock popup (PowerupChannel$$ClaimFirstTime, RVA 0x5C4A200): the booster
    counts as claimed and its stock goes up by 1. Refused when it isn't unlocked yet or was already claimed."""
    check_booster(booster)
    if not unlocked(progress, booster):
        raise Refused(f"That booster unlocks at level {UNLOCK_LEVELS[booster]}.")
    if booster in progress["claimed"]:
        raise Refused("You already took that one.")
    after = copy.deepcopy(progress)
    after["claimed"].append(booster)
    after["stock"][booster] += 1
    return after


def can_use(progress: Progress, booster: str) -> bool:
    """A booster works once it is unlocked and claimed, when the player has stock or the first use is still free
    (`PowerupSystemSettings` FirstTimeUseFree, StartPowerup RVA 0x5C49C9C)."""
    if booster not in PRICES or booster not in progress["claimed"] or not unlocked(progress, booster):
        return False
    return progress["stock"][booster] > 0 or booster not in progress["used"]


def use(progress: Progress, booster: str) -> Progress:
    """The progress after a booster started: the first use is free, every later one takes 1 from the stock."""
    if not can_use(progress, booster):
        raise Refused("You can't use that booster yet.")
    after = copy.deepcopy(progress)
    if booster not in after["used"]:
        after["used"].append(booster)
    else:
        after["stock"][booster] -= 1
    return after


def add_pack(progress: Progress, booster: str) -> Progress:
    """The progress after a pack of 3 of a booster was paid for (with credits, taken by the shop). Refused when the
    booster isn't unlocked yet."""
    check_booster(booster)
    if not unlocked(progress, booster):
        raise Refused(f"That booster unlocks at level {UNLOCK_LEVELS[booster]}.")
    after = copy.deepcopy(progress)
    after["stock"][booster] += PACK
    return after


def buy(progress: Progress, booster: str) -> Progress:
    """The progress after buying a pack of 3 with coins."""
    after = add_pack(progress, booster)
    price = PRICES[booster]
    if progress["coins"] < price:
        raise Refused(f"You need {price:,} coins for that.")
    after["coins"] -= price
    return after


def revive(progress: Progress) -> Progress:
    """The progress after a revive: 900 coins, every time."""
    if progress["coins"] < REVIVE_PRICE:
        raise Refused(f"You need {REVIVE_PRICE:,} coins for that.")
    after = copy.deepcopy(progress)
    after["coins"] -= REVIVE_PRICE
    return after


def see(progress: Progress, shown_id: t.Any) -> Progress:
    """The progress after the player saw a popup or tutorial, which then never shows again."""
    if type(shown_id) is not str or not 1 <= len(shown_id) <= 64:
        raise Refused("That isn't a popup.")
    after = copy.deepcopy(progress)
    if shown_id not in after["shown"]:
        if len(after["shown"]) >= MAX_SHOWN:
            raise Refused("That isn't a popup.")
        after["shown"].append(shown_id)
    return after
