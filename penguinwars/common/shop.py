"""The looks a penguin can wear: the catalog, the credit shop that sells half of it, and what play earns. Also who
a player's nemesis is.

Nothing worn changes how a penguin plays, and no credits are ever paid out: buying only takes credits out of the
economy. Until an admin saves their own prices, every credit item is sold at its catalog price. A saved set of prices
that lacks an item means that item is not sold. The other half of the catalog is never sold: each of those items is
the player's once one of their play counts reaches a number. One item is neither: the scarf, which every penguin has
and wears on its neck until its player picks something else or takes it off.

With a per-server bank each server sets its own prices. With a global bank one balance is shared by every server, so
only the bot owner sets the prices, once for everywhere. The settings dialog also shows what was spent today.
"""

import asyncio
import logging
import typing as t
from dataclasses import dataclass
from datetime import datetime, timezone

from redbot.core import bank

log = logging.getLogger("red.vrt.penguinwars.shop")

# The kinds the page draws as a 3D shape or an effect. Only their items have a picture in web/looks.webp
DRAWN_KINDS = ("skin", "hat", "face", "neck", "back", "trail", "cheer", "splash")
# What a penguin wears one of at a time, in the wardrobe's tab order. A title is a short line under the player's name,
# and a name style is how their name tag looks. Both are text and CSS on the page
KINDS = (*DRAWN_KINDS, "title", "name")


def sold(kind: str, name: str, price: int) -> dict:
    return {"kind": kind, "name": name, "price": price}


def earned(kind: str, name: str, stat: str, need: int) -> dict:
    return {"kind": kind, "name": name, "earn": (stat, need)}


def given(kind: str, name: str) -> dict:
    """An item every player has from the start, and wears until they pick another of its kind or take it off"""
    return {"kind": kind, "name": name, "given": True}


# The ids are what the page's models.js (skins and things worn) and fx.js (trails, cheers and splashes) look up. The
# order is the wardrobe's, and the order of the pictures in web/looks.webp, so the drawn kinds come first and a new
# drawn item goes before the first title. A title's name is the line shown under the player's name
ITEMS: dict[str, dict] = {
    "emperor": sold("skin", "Emperor", 2500),
    "snowy": sold("skin", "Snowy", 2500),
    "bubblegum": sold("skin", "Bubblegum", 5000),
    "midnight": earned("skin", "Midnight", "wins", 5),
    "ember": earned("skin", "Ember", "knockouts", 150),
    "steel": earned("skin", "Steel", "rounds", 100),
    "golden": earned("skin", "Golden", "wins", 40),
    "beanie": sold("hat", "Beanie", 1000),
    "party": sold("hat", "Party hat", 1000),
    "tophat": sold("hat", "Top hat", 2500),
    "flower": sold("hat", "Flower", 2500),
    "cowboy": sold("hat", "Cowboy hat", 2500),
    "crown": sold("hat", "Crown", 5000),
    "iceblock": sold("hat", "Ice block", 5000),
    "propeller": earned("hat", "Propeller cap", "rounds", 5),
    "chef": earned("hat", "Chef hat", "fish", 10),
    "viking": earned("hat", "Viking helmet", "knockouts", 50),
    "wizard": earned("hat", "Wizard hat", "wins", 15),
    "halo": earned("hat", "Halo", "bounce", 5),
    "shades": sold("face", "Shades", 1000),
    "glasses": sold("face", "Round glasses", 1000),
    "monocle": earned("face", "Monocle", "wins", 1),
    "eyepatch": earned("face", "Eye patch", "knockouts", 10),
    "moustache": earned("face", "Moustache", "rounds", 25),
    "snorkel": earned("face", "Snorkel", "seal", 5),
    "scarf": given("neck", "Scarf"),
    "bowtie": sold("neck", "Bow tie", 1000),
    "bandana": sold("neck", "Bandana", 1000),
    "necktie": sold("neck", "Necktie", 2500),
    "pearls": sold("neck", "Pearl necklace", 5000),
    "stripes": earned("neck", "Striped scarf", "rounds", 50),
    "medal": earned("neck", "Medal", "wins", 3),
    "lei": earned("neck", "Flower lei", "party", 5),
    "bell": earned("neck", "Bell collar", "fish", 15),
    "backpack": sold("back", "Backpack", 1000),
    "cape": sold("back", "Cape", 2500),
    "jetpack": sold("back", "Jetpack", 5000),
    "wings": earned("back", "Wings", "streak", 3),
    "balloon": earned("back", "Balloon", "party", 1),
    "fin": earned("back", "Shark fin", "seal", 25),
    "sparkle": sold("trail", "Sparkle trail", 2500),
    "hearts": sold("trail", "Hearts trail", 2500),
    "bubbles": sold("trail", "Bubbles trail", 2500),
    "flames": sold("trail", "Flames trail", 5000),
    "snowflakes": earned("trail", "Snowflake trail", "knockouts", 25),
    "leaves": earned("trail", "Leaf trail", "fish", 40),
    "gems": earned("trail", "Gem trail", "trick", 3),
    "twirl": sold("cheer", "Twirl", 1000),
    "backflip": sold("cheer", "Backflip", 2500),
    "fireworks": earned("cheer", "Fireworks", "wins", 25),
    "spin": earned("cheer", "Belly spin", "streak", 5),
    "lovesplash": sold("splash", "Heart splash", 1000),
    "bubblebath": sold("splash", "Bubble bath", 1000),
    "sizzle": earned("splash", "Sizzle", "bounce", 20),
    "starburst": earned("splash", "Star burst", "knockouts", 300),
    "chilly": sold("title", "Chill Penguin", 1000),
    "waddler": sold("title", "Pro Waddler", 1000),
    "icebreaker": sold("title", "Ice Breaker", 2500),
    "bigfish": sold("title", "Big Fish", 2500),
    "royalty": sold("title", "Ice Royalty", 5000),
    "regular": earned("title", "Ice Regular", "rounds", 10),
    "fishfan": earned("title", "Fish Fanatic", "fish", 25),
    "bouncer": earned("title", "The Bouncer", "bounce", 10),
    "sealslayer": earned("title", "Seal Slayer", "seal", 10),
    "champion": earned("title", "Champion", "wins", 10),
    "rose": sold("name", "Rose", 1000),
    "ice": sold("name", "Ice blue", 1000),
    "sunset": sold("name", "Sunset", 2500),
    "neon": sold("name", "Neon glow", 5000),
    "mint": earned("name", "Mint", "fish", 5),
    "aurora": earned("name", "Aurora", "party", 3),
    "lava": earned("name", "Lava", "knockouts", 100),
    "gold": earned("name", "Gold shine", "wins", 20),
}
# The items sold for credits, which are the only ones with prices to set
PRICED: dict[str, dict] = {item: info for item, info in ITEMS.items() if "price" in info}
# The items everyone has, as {kind: item}. A penguin wears each until its player picks another or takes it off
GIVEN: dict[str, str] = {info["kind"]: item for item, info in ITEMS.items() if "given" in info}
# Things paid for each time they are used. They are not looks, so nobody owns or wears them
EXTRAS: dict[str, dict] = {
    "crate": {"name": "Crate drop", "price": 100},
    "twist": {"name": "Party round", "price": 250},
    "snowball": {"name": "Snowball", "price": 2},
}
# Everything with a credit price for an admin to set
SOLD: dict[str, dict] = {**EXTRAS, **PRICED}

MAX_PRICE = 1_000_000_000
# The menu card's currency line fits this many characters, counted as ActivityHub counts them
LINE_LIMIT = 40

NO_SERVER = "Buying only works in a server."

# ---------- What play earns ----------

# A player's play counts, the same in every server. `streak` is the run of wins they are on now
STATS = {
    "rounds": 0,
    "wins": 0,
    "knockouts": 0,
    "fish": 0,
    "seal": 0,
    "bounce": 0,
    "streak": 0,
    "best_streak": 0,
    "best_round": 0,
    "party_wins": 0,
}
# The saved count an achievement reads, where that isn't the count of its own name
COUNT_OF = {"streak": "best_streak", "trick": "best_round", "party": "party_wins"}
# A win counts as a party win when this many people started the round
PARTY_PEOPLE = 3
# What a player is told to do for each kind of achievement, for one and for more
EARN_LINES = {
    "rounds": ("Play a round", "Play {n} rounds"),
    "wins": ("Win a round", "Win {n} rounds"),
    "knockouts": ("Knock out a penguin", "Knock out {n} penguins"),
    "fish": ("Eat a fish", "Eat {n} fish"),
    "seal": ("As a seal, splash a penguin in", "As a seal, splash {n} penguins in"),
    "bounce": (
        "Bounce a penguin into the sea with your brace",
        "Bounce {n} penguins into the sea with your brace",
    ),
    "streak": ("Win a round", "Win {n} rounds in a row"),
    "trick": ("Knock out a penguin", "Knock out {n} penguins in one round"),
    "party": (
        f"Win a round with {PARTY_PEOPLE} or more people playing",
        f"Win {{n}} rounds with {PARTY_PEOPLE} or more people playing",
    ),
}


@dataclass(frozen=True)
class Played:
    """One person's part in a finished round, for their play counts. `people` is how many people started it. `by` is
    the user id of the person who knocked them out, with that person's name, or None when no person did"""

    user_id: int
    won: bool
    knockouts: int
    fish: int
    seal: int
    bounce: int
    people: int
    by: int | None = None
    by_name: str = ""


def count_for(stats: dict[str, int], stat: str) -> int:
    """The saved count that an achievement of this kind is measured by"""
    return stats[COUNT_OF[stat] if stat in COUNT_OF else stat]


def stats_of(saved: t.Any) -> dict[str, int]:
    """A player's play counts, with zero for any that were never saved"""
    saved = saved if isinstance(saved, dict) else {}
    return {name: saved.get(name, zero) for name, zero in STATS.items()}


def add_round(saved: t.Any, played: Played) -> dict[str, int]:
    """A player's play counts with one more finished round added"""
    stats = stats_of(saved)
    streak = stats["streak"] + 1 if played.won else 0
    return {
        "rounds": stats["rounds"] + 1,
        "wins": stats["wins"] + int(played.won),
        "knockouts": stats["knockouts"] + played.knockouts,
        "fish": stats["fish"] + played.fish,
        "seal": stats["seal"] + played.seal,
        "bounce": stats["bounce"] + played.bounce,
        "streak": streak,
        "best_streak": max(stats["best_streak"], streak),
        "best_round": max(stats["best_round"], played.knockouts),
        "party_wins": stats["party_wins"] + int(played.won and played.people >= PARTY_PEOPLE),
    }


def earn_state(item: str, saved: t.Any) -> dict | None:
    """How an earned item is unlocked and how far the player is, or None for an item sold for credits"""
    earn = ITEMS[item].get("earn")
    if earn is None:
        return None
    stat, need = earn
    one, many = EARN_LINES[stat]
    have = count_for(stats_of(saved), stat)
    return {"text": one if need == 1 else many.format(n=f"{need:,}"), "have": min(have, need), "need": need}


def earned_items(saved: t.Any) -> list[str]:
    """The earned items these play counts have unlocked, in catalog order"""
    stats = stats_of(saved)
    unlocked = []
    for item, info in ITEMS.items():
        stat, need = info.get("earn", (None, 0))
        if stat is not None and count_for(stats, stat) >= need:
            unlocked.append(item)
    return unlocked


def achievements(saved: t.Any) -> list[dict]:
    """Every earned item with how it is unlocked and how far these play counts are, in catalog order. One is unlocked
    when its `have` reaches its `need`"""
    return [
        {"id": item, "kind": info["kind"], "name": info["name"], **earn_state(item, saved)}
        for item, info in ITEMS.items()
        if "earn" in info
    ]


def clean_wear(saved: t.Any) -> dict[str, str]:
    """What a player wears, as {kind: item}, without anything that is no longer an item of that kind. A kind with a
    given item is saved as None once the player takes it off. With anything else saved for it, or nothing, the
    given item is worn"""
    saved = saved if isinstance(saved, dict) else {}
    worn = {}
    for kind in KINDS:
        item = saved.get(kind, GIVEN.get(kind))
        if type(item) is str and item in ITEMS and ITEMS[item]["kind"] == kind:
            worn[kind] = item
        elif item is not None and kind in GIVEN:
            worn[kind] = GIVEN[kind]
    return worn


def wear_to_save(worn: dict[str, str]) -> dict[str, str | None]:
    """What is saved for a player who wears this: a given item's kind with nothing worn is saved as None, which tells
    a player who took it off from one who never chose"""
    return {**{kind: None for kind in GIVEN if kind not in worn}, **worn}


# ---------- Nemesis ----------

# A player's nemesis is the person who knocked them out most, once that is this many times
NEMESIS_KNOCKOUTS = 3
# A player's count of who knocked them out holds this many people: the ones with the most knockouts
FOES_KEPT = 50


def foes_of(saved: t.Any) -> dict[str, dict]:
    """Who knocked a player out, as {user id as text: {"count", "name"}}, the same in every server"""
    return dict(saved) if isinstance(saved, dict) else {}


def add_foe(saved: t.Any, user_id: int, name: str) -> dict[str, dict]:
    """A player's foes with one more knockout by this person. The name is refreshed, since people rename. Past
    FOES_KEPT people, the one with the fewest knockouts is dropped. That is never the person just counted, so a new
    rival can still build up a count"""
    foes = foes_of(saved)
    key = str(user_id)
    count = foes[key]["count"] + 1 if key in foes else 1
    foes[key] = {"count": count, "name": name}
    if len(foes) > FOES_KEPT:
        del foes[min((foe for foe in foes if foe != key), key=lambda foe: (foes[foe]["count"], -int(foe)))]
    return foes


def nemesis_of(saved: t.Any) -> dict | None:
    """A player's nemesis as {id, name, count}, or None while nobody has knocked them out often enough. Between two
    people with the same count it is the one with the lower id"""
    foes = foes_of(saved)
    if not foes:
        return None
    key = max(foes, key=lambda foe: (foes[foe]["count"], -int(foe)))
    if foes[key]["count"] < NEMESIS_KNOCKOUTS:
        return None
    # Discord ids go out as text, since JavaScript rounds whole numbers this big
    return {"id": key, "name": foes[key]["name"], "count": foes[key]["count"]}


def nemesis_id(saved: t.Any) -> str | None:
    nemesis = nemesis_of(saved)
    return nemesis["id"] if nemesis is not None else None


# ---------- The credit shop ----------


class SettingsError(ValueError):
    """A settings change refused, worded for the admin"""


class ShopRefused(Exception):
    """A purchase that can't go through, worded for the player"""


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def clean_prices(value: t.Any) -> dict[str, int]:
    """The prices the admin sent, as {item: price} for the items that have one.

    Expected: an object with every look sold for credits and every extra, each a whole number from 1 to MAX_PRICE, or None (or an empty
    string) for an item that is not sold.
    """
    if not isinstance(value, dict) or set(value) != set(SOLD):
        raise SettingsError("Expected a price for each item, or empty for none.")
    prices = {}
    for item, info in SOLD.items():
        price = value[item]
        if price is None or price == "":
            continue
        if type(price) is not int or not 1 <= price <= MAX_PRICE:
            raise SettingsError(
                f"The {info['name']} price must be a whole number from 1 to {MAX_PRICE:,}, or empty to not sell it."
            )
        prices[item] = price
    return prices


class Shop:
    """The credit prices where a player is, what was spent today, and taking the credits"""

    def __init__(self, config: t.Any, money: t.Any = bank, today: t.Callable[[], str] = utc_today):
        self.config = config
        self.bank = money
        self.today = today
        self.lock = asyncio.Lock()

    async def group(self, guild: t.Any) -> t.Any:
        """Where the prices live: the server's own, or the owner's for every server when the bank is global"""
        return self.config if await self.bank.is_global() else self.config.guild(guild)

    async def prices(self, guild: t.Any) -> dict[str, int]:
        """The credit price of each look and extra that is sold. Nothing outside a server"""
        if guild is None:
            return {}
        saved = await (await self.group(guild)).prices()
        if saved is None:
            return {item: info["price"] for item, info in SOLD.items()}
        return {item: saved[item] for item in SOLD if item in saved}

    async def save(self, guild: t.Any, value: t.Any) -> dict[str, int]:
        prices = clean_prices(value)
        await (await self.group(guild)).prices.set(prices)
        return prices

    async def currency(self, guild: t.Any) -> str:
        return await self.bank.get_currency_name(guild)

    async def today_spent(self, guild: t.Any) -> dict:
        """What was spent today where these prices apply, and by how many players"""
        tally = await (await self.group(guild)).tally()
        if tally.get("day") != self.today():
            return {"spent": 0, "players": 0}
        return {"spent": tally.get("spent", 0), "players": len(tally.get("players", []))}

    async def buy(self, member: t.Any, item: str) -> int:
        """Take the item's credit price from the player's balance. Returns the price. Raises
        ShopRefused, with nothing taken, when the player can't pay it here"""
        guild = getattr(member, "guild", None)
        if guild is None:
            raise ShopRefused(NO_SERVER)
        price = (await self.prices(guild)).get(item)
        if price is None:
            raise ShopRefused(f"That isn't sold for {await self.currency(guild)} here.")
        if await self.bank.get_balance(member) < price:
            raise ShopRefused(f"You need {price:,} {await self.currency(guild)} for that.")
        try:
            await self.bank.withdraw_credits(member, price)
        except ValueError as e:
            raise ShopRefused(f"You need {price:,} {await self.currency(guild)} for that.") from e
        return price

    async def count(self, member: t.Any, price: int) -> None:
        """Add a delivered purchase to today's tally. It only feeds the settings dialog, so a failure is logged and the
        player keeps what they bought"""
        try:
            await self.add_to_tally(member, member.guild, price)
        except Exception as e:
            log.error("Couldn't count a Penguin Wars purchase by user %s", member.id, exc_info=e)

    async def refund(self, member: t.Any, price: int) -> None:
        """Give back a price taken by `buy` when the item could not be saved"""
        await self.bank.deposit_credits(member, price)

    async def add_to_tally(self, member: t.Any, guild: t.Any, price: int) -> None:
        group = await self.group(guild)
        async with self.lock:
            tally, today = await group.tally(), self.today()
            if tally.get("day") != today:
                tally = {"day": today, "spent": 0, "players": []}
            tally["spent"] = tally.get("spent", 0) + price
            if member.id not in tally["players"]:
                tally["players"].append(member.id)
            await group.tally.set(tally)
