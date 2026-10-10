"""Checking a settings change before it is saved. The page's settings panel and the chat commands both use these"""

import logging
import re
import typing as t

from redbot.core.i18n import Translator

from .catalog import GAMES, NAME_LIMIT, NO_BET_RANGE, NO_MULTIPLIER

_ = Translator("Casino", __file__)
log = logging.getLogger("red.vrt.casino.edits")

TIME_PATTERN = re.compile(r"[0-9]{1,18}(:[0-9]{1,18}){0,3}")
WHOLE_PATTERN = re.compile(r"-?[0-9]{1,18}")
MAX_NUMBER = 2**63 - 1


def parse_duration(text: str) -> int | None:
    """Seconds, or DD:HH:MM:SS, HH:MM:SS or MM:SS as the original took them. None when it isn't either"""
    text = str(text).strip()
    if not TIME_PATTERN.fullmatch(text):
        return None
    sizes = (1, 60, 3600, 86400)
    return sum(int(part) * size for part, size in zip(reversed(text.split(":")), sizes))


def whole(value: t.Any) -> int | None:
    """A whole number from the page or a command, or None. True and False don't count"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and WHOLE_PATTERN.fullmatch(value.strip()):
        return int(value.strip())
    return None


def clean_casino(data: dict) -> tuple[dict, str | None]:
    """The casino-wide fields present in data, checked"""
    fields: dict = {}
    if "name" in data:
        name = data["name"].strip() if isinstance(data["name"], str) else ""
        if not 1 <= len(name) <= NAME_LIMIT:
            return {}, _("The casino's name must be 1 to {limit} characters.").format(limit=NAME_LIMIT)
        fields["name"] = name
    for key in ("is_open", "limit_on"):
        if key in data:
            if not isinstance(data[key], bool):
                return {}, _("That switch must be on or off.")
            fields[key] = data[key]
    if "limit_amount" in data:
        amount = whole(data["limit_amount"])
        if amount is None or not 0 <= amount <= MAX_NUMBER:
            return {}, _("The payout limit must be a whole number, 0 or more.")
        fields["limit_amount"] = amount
    return fields, None


def clean_game(key: str, data: dict, current_min: int | None, current_max: int | None) -> tuple[dict, str | None]:
    """The game fields present in data, checked against the game and its current min and max"""
    if key not in GAMES:
        return {}, _("That isn't one of the casino's games.")
    fields: dict = {}
    if "is_open" in data:
        if not isinstance(data["is_open"], bool):
            return {}, _("That switch must be on or off.")
        fields["is_open"] = data["is_open"]
    for clean in (clean_numbers, clean_multiplier):
        found, problem = clean(key, data)
        if problem:
            return {}, problem
        fields.update(found)
    low = fields.get("min_bet", current_min)
    high = fields.get("max_bet", current_max)
    if low is not None and high is not None and low > high:
        return {}, _("The minimum bet can't be higher than the maximum.")
    return fields, None


def clean_numbers(key: str, data: dict) -> tuple[dict, str | None]:
    fields = {}
    for name in ("access", "cooldown", "min_bet", "max_bet"):
        if name not in data:
            continue
        if name in ("min_bet", "max_bet") and key in NO_BET_RANGE:
            return {}, _("All In has no minimum or maximum bet: it always bets everything.")
        if name == "cooldown" and isinstance(data[name], str):
            value = parse_duration(data[name])
            if value is None:
                return {}, _("Enter the cooldown as seconds or as HH:MM:SS.")
        else:
            value = whole(data[name])
        if value is None or not 0 <= value <= MAX_NUMBER:
            return {}, _("That must be a whole number, 0 or more.")
        fields[name] = value
    return fields, None


def clean_multiplier(key: str, data: dict) -> tuple[dict, str | None]:
    if "multiplier" not in data:
        return {}, None
    if key in NO_MULTIPLIER:
        return {}, _("This game's payout is set by the player, so it has no multiplier.")
    if isinstance(data["multiplier"], bool):
        return {}, _("The multiplier must be a number.")
    try:
        multiplier = float(data["multiplier"])
    except (TypeError, ValueError) as e:
        log.debug("Multiplier %r isn't a number: %s", data["multiplier"], e)
        return {}, _("The multiplier must be a number.")
    if not 0 <= multiplier <= 1_000_000:
        return {}, _("The multiplier must be between 0 and 1,000,000.")
    return {"multiplier": multiplier}, None
