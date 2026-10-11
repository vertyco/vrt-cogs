from dataclasses import fields, is_dataclass

import pytest

from farmcord.db.tables import TABLES, AnimalRow, Player, SpotRow
from farmcord.game.model import Animal, Decoration, Farm, Item, new_farm

NOW = 1_800_000_000.0


def full_farm(user_id: int = 42, name: str = "Vërt 🌻") -> Farm:
    """A farm with something other than the default in every field, and moments with fractions of a second"""
    farm = new_farm(user_id, name, NOW)
    farm.coins, farm.xp, farm.level = 12345, 67890, 23
    farm.storage_tier, farm.can_tier, farm.hoe_tier = 3, 2, 1
    farm.water, farm.rooms, farm.switches = 37, 2, 3
    farm.hat, farm.top, farm.bottom = "straw_hat", "plaid_shirt", "blue_overalls"
    farm.outfits = {"straw_hat", "plaid_shirt", "blue_overalls"}
    farm.sound, farm.music = False, False
    farm.crops_sold, farm.animals_sold, farm.litters = 40, 12, 3
    farm.harvested = {"wildflowers", "wheat", "blueberries"}
    farm.settled_at = NOW + 123.456
    fill_plots(farm)
    farm.animals = animals()
    farm.items = {
        "seed:wildflowers": Item("seed:wildflowers", 4),
        "crop:wheat": Item("crop:wheat", 7, 133),
        "crop:wheat:x": Item("crop:wheat:x", 1, 38),
        "feed:pig": Item("feed:pig", 9),
    }
    farm.achievements = {"first_crop": NOW - 86_400.5, "breed_5": NOW - 3.25}
    farm.decorations = [
        Decoration(item="bench", room="yard", x=0.125, y=0.875),
        Decoration(item="bench", room="room2", x=1.0, y=0.0),
        Decoration(item="lantern"),
    ]
    farm.descriptions = {2: "A cozy den", 3: "Quotes ' and \" and a 🐄"}
    return farm


def fill_plots(farm: Farm) -> None:
    """Plot 1 has a spot in each state and a bush part way through its third cycle; plot 2 is a pen"""
    spots = farm.plots[1].spots
    spots[1].state = "tilled"
    spots[2].state, spots[2].crop = "growing", "wheat"
    spots[2].planted_at, spots[2].stage_len, spots[2].watered = NOW - 1000.5, 1200.25, 0b001
    spots[3].state, spots[3].crop, spots[3].planted_at, spots[3].stage_len = "rotted", "corn", NOW - 9e5, 3600.0
    spots[4].state, spots[4].crop, spots[4].cycle = "growing", "blueberries", 2
    spots[4].planted_at, spots[4].stage_len, spots[4].watered = NOW - 50_000.75, 28_800.0, 0b101
    farm.plots[2].unlocked, farm.plots[2].kind = True, "animals"
    farm.plots[3].unlocked = True


def animals() -> list[Animal]:
    """One animal in each condition: healthy, expecting, sickly, malnourished, a baby in a pen and one waiting"""
    adult = {"adult": True, "arrived_at": NOW - 9e5, "fed_at": NOW - 100.5, "watered_at": NOW - 200.25}
    return [
        Animal(kind="pig", sex="male", plot=2, value=310, exceptional=True, cared_since=NOW - 5e5, **adult),
        Animal(
            kind="pig",
            sex="female",
            plot=2,
            value=155,
            bred=True,
            tried_at=NOW - 600.0,
            pregnant_until=NOW + 3000.0,
            litter=2,
            missed=1,
            missed_young=1,
            cared_since=NOW - 4e5,
            **adult,
        ),
        Animal(kind="pig", sex="female", plot=2, value=150, sickly=True, missed=4, cared_since=NOW - 1e4, **adult),
        Animal(kind="pig", sex="male", plot=2, value=90, sickly=True, malnourished=True, missed=12, **adult),
        Animal(kind="chicken", sex="female", plot=2, arrived_at=NOW - 50.5, fed_at=NOW - 50.5, watered_at=NOW - 50.5),
        Animal(kind="chicken", sex="male", plot=None),
    ]


def same_types(a, b) -> bool:
    """True when every value in `a` has the same type as the one in the same place in `b` (1 == True and 1 == 1.0
    in Python, so equality alone would miss a column handing back the wrong type)"""
    if is_dataclass(a):
        return type(a) is type(b) and all(same_types(getattr(a, f.name), getattr(b, f.name)) for f in fields(a))
    if isinstance(a, dict):
        return type(b) is dict and list(a) == list(b) and all(same_types(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return type(b) is list and len(a) == len(b) and all(same_types(x, y) for x, y in zip(a, b))
    return type(a) is type(b)


async def row_counts(user_id: int) -> dict[str, int]:
    return {table.__name__: await table.count().where(table.user_id == user_id) for table in TABLES}


@pytest.mark.asyncio
async def test_a_new_player_has_no_farm(store):
    assert await store.load(42) is None


@pytest.mark.asyncio
async def test_a_new_farm_saves_and_loads_equal(store):
    farm = new_farm(42, "Vert", NOW)
    await store.save(farm)
    loaded = await store.load(42)
    assert loaded == farm
    assert same_types(loaded, farm)


@pytest.mark.asyncio
async def test_a_farm_with_something_in_every_field_saves_and_loads_equal(store):
    farm = full_farm()
    await store.save(farm)
    loaded = await store.load(42)
    assert loaded == farm
    assert same_types(loaded, farm)
    # Lists come back in the order they were saved
    assert [animal.id for animal in loaded.animals] == [animal.id for animal in farm.animals]
    assert [d.id for d in loaded.decorations] == [d.id for d in farm.decorations]


@pytest.mark.asyncio
async def test_saving_again_replaces_the_rows_instead_of_adding_to_them(store):
    farm = full_farm()
    await store.save(farm)
    farm.animals.pop()
    farm.items["seed:wheat"] = Item("seed:wheat", 2)
    farm.plots[1].spots[1].state = "untilled"
    farm.descriptions.pop(3)
    farm.coins = 1
    await store.save(farm)
    await store.save(farm)
    assert await store.load(42) == farm
    counts = await row_counts(42)
    assert counts == {
        "Player": 1,
        "PlotRow": 7,
        "SpotRow": 63,
        "AnimalRow": 5,
        "ItemRow": 5,
        "AchievementRow": 2,
        "DecorationRow": 3,
        "RoomRow": 1,
    }


@pytest.mark.asyncio
async def test_a_save_that_fails_part_way_leaves_the_last_saved_farm(store):
    farm = full_farm()
    await store.save(farm)
    broken = full_farm()
    # Decorations are written after the player, plots, spots and animals, and this one can't be written at all
    broken.decorations[0].x = object()
    with pytest.raises(Exception):
        await store.save(broken)
    assert await store.load(42) == farm


@pytest.mark.asyncio
async def test_deleting_a_user_removes_every_row_of_theirs_and_nobody_elses(store):
    mine, theirs = full_farm(42), full_farm(43, "Someone")
    await store.save(mine)
    await store.save(theirs)
    await store.delete_user(42)
    assert await store.load(42) is None
    assert set((await row_counts(42)).values()) == {0}
    assert await store.load(43) == theirs
    assert await SpotRow.count().where(SpotRow.user_id == 43) == 63
    assert await AnimalRow.count().where(AnimalRow.user_id == 43) == 6


async def save_players(store, *players: tuple[int, int, int]) -> None:
    for user_id, level, xp in players:
        farm = new_farm(user_id, f"Player {user_id}", NOW)
        farm.level, farm.xp = level, xp
        await store.save(farm)


@pytest.mark.asyncio
async def test_the_leaderboard_goes_by_level_then_xp(store):
    # Saved out of order on purpose; the two level 5 farms with 300 XP tie, and the lower user id comes first
    await save_players(store, (14, 5, 300), (11, 7, 500), (13, 5, 300), (12, 7, 600), (10, 2, 20))
    top, rank = await store.leaderboard(11)
    assert [row["user_id"] for row in top] == [12, 11, 13, 14, 10]
    assert top[0] == {"user_id": 12, "name": "Player 12", "level": 7, "xp": 600}
    assert rank == 2
    assert (await store.leaderboard(13))[1] == 3
    assert (await store.leaderboard(14))[1] == 4


@pytest.mark.asyncio
async def test_the_leaderboard_keeps_to_its_limit_and_still_ranks_the_player(store):
    await save_players(store, *((user_id, 10 + user_id, 0) for user_id in range(1, 31)))
    top, rank = await store.leaderboard(3)
    assert len(top) == 25
    assert [row["user_id"] for row in top[:3]] == [30, 29, 28]
    assert rank == 28
    top, rank = await store.leaderboard(3, limit=2)
    assert [row["user_id"] for row in top] == [30, 29]
    assert rank == 28


@pytest.mark.asyncio
async def test_a_player_without_a_farm_has_no_rank(store):
    await save_players(store, (1, 5, 0))
    top, rank = await store.leaderboard(99)
    assert [row["user_id"] for row in top] == [1]
    assert rank is None
    assert await Player.count() == 1
