"""The casino's fixed facts: its games, their default settings, and membership colors"""

from redbot.core.i18n import Translator

_ = Translator("Casino", __file__)

CREDIT = "Rebuilt for ActivityHub from Redjumpman's Casino: https://github.com/Redjumpman/Jumper-Plugins"

# In the original's order. The keys are stored in the database and sent to the page, so they never change
GAMES = ("allin", "blackjack", "coin", "craps", "cups", "dice", "hilo", "war", "double")

GAME_NAMES = {
    "allin": "All In",
    "blackjack": "Blackjack",
    "coin": "Coin",
    "craps": "Craps",
    "cups": "Cups",
    "dice": "Dice",
    "hilo": "Hi-Lo",
    "war": "War",
    "double": "Double or Nothing",
}

# The original's defaults. None means the game has no such setting
GAME_DEFAULTS = {
    "allin": {"access": 0, "cooldown": 43200, "min_bet": None, "max_bet": None, "multiplier": None},
    "blackjack": {"access": 0, "cooldown": 5, "min_bet": 50, "max_bet": 500, "multiplier": 2.0},
    "coin": {"access": 0, "cooldown": 5, "min_bet": 10, "max_bet": 10, "multiplier": 1.5},
    "craps": {"access": 0, "cooldown": 5, "min_bet": 50, "max_bet": 500, "multiplier": 2.0},
    "cups": {"access": 0, "cooldown": 5, "min_bet": 25, "max_bet": 100, "multiplier": 1.8},
    "dice": {"access": 0, "cooldown": 5, "min_bet": 25, "max_bet": 100, "multiplier": 1.8},
    "hilo": {"access": 0, "cooldown": 5, "min_bet": 25, "max_bet": 75, "multiplier": 1.7},
    "war": {"access": 0, "cooldown": 5, "min_bet": 25, "max_bet": 75, "multiplier": 1.5},
    "double": {"access": 0, "cooldown": 5, "min_bet": 10, "max_bet": 250, "multiplier": None},
}

# Games whose bets have no min and max, and games whose wins skip the multiplier and membership bonus
NO_BET_RANGE = ("allin",)
NO_MULTIPLIER = ("allin", "double")

CASINO_DEFAULTS = {"name": "Redjumpman's", "is_open": True, "limit_on": False, "limit_amount": 10000}
NAME_LIMIT = 30

# Membership colors, as the original named them, with the colors the page and embeds show
COLORS = {
    "blue": 0x3366FF,
    "red": 0xFF0000,
    "green": 0x00CC33,
    "orange": 0xFF6600,
    "purple": 0xA220BD,
    "yellow": 0xFFFF00,
    "turquoise": 0x00FFFF,
    "teal": 0x009999,
    "magenta": 0xBA2586,
    "pink": 0xFE01D1,
    "white": 0xFFFFFF,
}
BASIC_COLOR = 0x666666

# What players and admins may type for a game in commands, as the original accepted them
ALIASES = {
    "allin": "allin",
    "all in": "allin",
    "blackjack": "blackjack",
    "bj": "blackjack",
    "21": "blackjack",
    "coin": "coin",
    "craps": "craps",
    "cups": "cups",
    "dice": "dice",
    "hilo": "hilo",
    "hi-lo": "hilo",
    "hl": "hilo",
    "war": "war",
    "double": "double",
    "don": "double",
    "x2": "double",
}


def game_key(text: str) -> str | None:
    """The game a typed name means, or None"""
    return ALIASES.get(text.strip().lower())


def global_bank_needed(prefix: str) -> str:
    return _(
        "You can't make the casino global while the bank is per server. "
        "Make the bank global first with `{prefix}bankset toggleglobal`."
    ).format(prefix=prefix)
