"""Saving and loading whole farms. A farm is one Player row plus its plot, spot, animal, item, achievement,
decoration and room rows, all keyed by the Discord user id since farms are global"""

from collections import defaultdict
from dataclasses import fields

from piccolo.engine.sqlite import TransactionType

from ..db.tables import AchievementRow, AnimalRow, DecorationRow, ItemRow, Player, PlotRow, RoomRow, SpotRow
from ..game.model import Animal, Decoration, Farm, Item, Plot, Spot

# Every table that holds rows of one farm besides its Player row
FARM_TABLES = (PlotRow, SpotRow, AnimalRow, ItemRow, AchievementRow, DecorationRow, RoomRow)
# Farm fields that live in those tables rather than on the Player row
NESTED = ("plots", "animals", "items", "achievements", "decorations", "descriptions")


def columns(obj: object, *skip: str) -> dict:
    """A dataclass's fields by name, which are also its table's column names"""
    return {f.name: getattr(obj, f.name) for f in fields(obj) if f.name not in skip}


def build(cls: type, row: dict, **given):
    """A dataclass from the row's columns of the same names, with `given` fields filled in by the caller. A field
    with no column raises KeyError, so a model field the tables forgot can't load quietly as its default"""
    return cls(**{f.name: row[f.name] for f in fields(cls) if f.name not in given}, **given)


def player_row(farm: Farm) -> Player:
    row = columns(farm, *NESTED)
    # Sorted so the same farm always writes the same text
    row["outfits"] = sorted(farm.outfits)
    row["harvested"] = sorted(farm.harvested)
    return Player(**row)


def farm_rows(farm: Farm) -> list[list]:
    """The farm's rows for each of FARM_TABLES, in that order. Lists keep their order through the Serial ids"""
    user_id = farm.user_id
    plots = farm.plots.values()
    return [
        [PlotRow(user_id=user_id, **columns(plot, "spots")) for plot in plots],
        [SpotRow(user_id=user_id, plot=plot.number, **columns(spot)) for plot in plots for spot in plot.spots],
        [AnimalRow(user_id=user_id, animal_id=a.id, **columns(a, "id")) for a in farm.animals],
        [ItemRow(user_id=user_id, **columns(item)) for item in farm.items.values()],
        [AchievementRow(user_id=user_id, key=key, earned_at=at) for key, at in farm.achievements.items()],
        [DecorationRow(user_id=user_id, decoration_id=d.id, **columns(d, "id")) for d in farm.decorations],
        [RoomRow(user_id=user_id, room=room, description=text) for room, text in farm.descriptions.items()],
    ]


def farm_from_rows(player: dict, rows: dict) -> Farm:
    """A Farm from its Player row and the rows of each of FARM_TABLES (keyed by table), as select() dicts"""
    spots = defaultdict(list)
    for row in rows[SpotRow]:
        spots[row["plot"]].append(build(Spot, row))
    return build(
        Farm,
        player,
        outfits=set(player["outfits"]),
        harvested=set(player["harvested"]),
        plots={row["number"]: build(Plot, row, spots=spots[row["number"]]) for row in rows[PlotRow]},
        animals=[build(Animal, row, id=row["animal_id"]) for row in rows[AnimalRow]],
        items={row["key"]: build(Item, row) for row in rows[ItemRow]},
        achievements={row["key"]: row["earned_at"] for row in rows[AchievementRow]},
        decorations=[build(Decoration, row, id=row["decoration_id"]) for row in rows[DecorationRow]],
        descriptions={row["room"]: row["description"] for row in rows[RoomRow]},
    )


class Store:
    async def load(self, user_id: int) -> Farm | None:
        """The player's farm, or None when they have never played"""
        player = await Player.select().where(Player.user_id == user_id).output(load_json=True).first()
        if player is None:
            return None
        rows = {}
        for table in FARM_TABLES:
            rows[table] = await table.select().where(table.user_id == user_id).order_by(table.id)
        return farm_from_rows(player, rows)

    async def save(self, farm: Farm) -> None:
        """Write the whole farm in one transaction, replacing every row it had. If any write fails, none happen"""
        async with Player._meta.db.transaction(TransactionType.immediate):
            await self.delete_rows(farm.user_id)
            await Player.insert(player_row(farm))
            for rows in farm_rows(farm):
                if rows:
                    await type(rows[0]).insert(*rows)

    async def delete_user(self, user_id: int) -> None:
        async with Player._meta.db.transaction(TransactionType.immediate):
            await self.delete_rows(user_id)

    async def delete_rows(self, user_id: int) -> None:
        for table in (Player, *FARM_TABLES):
            await table.delete().where(table.user_id == user_id)

    async def leaderboard(self, user_id: int, limit: int = 25) -> tuple[list[dict], int | None]:
        """The top farms by level, then XP, as dicts of user_id, name, level and xp, and the player's own rank
        (None without a farm). Ties go to the lower user id, the table's own order, so the rank matches the list"""
        top = (
            await Player.select(Player.user_id, Player.name, Player.level, Player.xp)
            .order_by(Player.level, Player.xp, ascending=False)
            .order_by(Player.user_id)
            .limit(limit)
        )
        me = await Player.select(Player.level, Player.xp).where(Player.user_id == user_id).first()
        if me is None:
            return top, None
        level, xp = me["level"], me["xp"]
        ahead = (
            (Player.level > level)
            | ((Player.level == level) & (Player.xp > xp))
            | ((Player.level == level) & (Player.xp == xp) & (Player.user_id < user_id))
        )
        return top, await Player.count().where(ahead) + 1
