from piccolo.columns import JSON, BigInt, Boolean, Integer, Real, Serial, Text, Varchar
from piccolo.table import Table, sort_table_classes

# Farms are global, so every row belongs to a Discord user id and there is no server column. Column names match the
# fields of the game's dataclasses (farmcord/game/model.py), so the store copies them across by name. Moments are
# unix seconds. The other tables keep a Serial id so a farm's lists load back in the order they were saved, which is
# why an animal's or decoration's own uuid id goes in animal_id or decoration_id


class Player(Table):
    """One row per farm: every Farm field that doesn't need rows of its own"""

    user_id = BigInt(primary_key=True)
    name = Varchar(length=32, default="", help_text="Discord display name, for the leaderboard")
    coins = BigInt(default=0)
    xp = BigInt(default=0)
    level = Integer(default=1)
    storage_tier = Integer(default=0)
    can_tier = Integer(default=0)
    hoe_tier = Integer(default=0)
    water = Integer(default=0, help_text="Water in the can")
    rooms = Integer(default=0, help_text="Extra farmhouse rooms owned")
    switches = Integer(default=0, help_text="Plot switches paid for")
    hat = Varchar(length=32, null=True, default=None)
    top = Varchar(length=32, null=True, default=None)
    bottom = Varchar(length=32, null=True, default=None)
    outfits = JSON(default="[]", help_text="Owned outfit keys")
    sound = Boolean(default=True)
    music = Boolean(default=True)
    crops_sold = Integer(default=0)
    animals_sold = Integer(default=0)
    litters = Integer(default=0)
    harvested = JSON(default="[]", help_text="Crop keys ever harvested")
    settled_at = Real(default=0.0)


class PlotRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    number = Integer()
    unlocked = Boolean(default=False)
    kind = Varchar(length=16, default="crops")


class SpotRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    plot = Integer()
    index = Integer(help_text="0 to 8, rows being 0-2, 3-5 and 6-8")
    state = Varchar(length=16, default="untilled")
    crop = Varchar(length=32, null=True, default=None)
    planted_at = Real(default=0.0)
    stage_len = Real(default=0.0, help_text="Seconds one growth stage lasts")
    watered = Integer(default=0, help_text="Bit k is set when stage k was watered by hand")
    cycle = Integer(default=0, help_text="Bush harvests so far")


class AnimalRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    animal_id = Varchar(length=32, help_text="The animal's own uuid hex id")
    kind = Varchar(length=16)
    sex = Varchar(length=8)
    plot = Integer(null=True, default=None, help_text="None while the baby waits in the farmhouse")
    arrived_at = Real(default=0.0)
    fed_at = Real(default=0.0)
    watered_at = Real(default=0.0)
    missed = Integer(default=0)
    missed_young = Integer(default=0)
    adult = Boolean(default=False)
    value = BigInt(default=0)
    exceptional = Boolean(default=False)
    bred = Boolean(default=False)
    tried_at = Real(default=0.0)
    pregnant_until = Real(default=0.0)
    litter = Integer(default=0)
    sickly = Boolean(default=False)
    malnourished = Boolean(default=False)
    cared_since = Real(default=0.0)


class ItemRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    key = Varchar(length=32)
    quantity = Integer(default=0)
    worth = BigInt(default=0, help_text="What the whole stack sells for (crops only)")


class AchievementRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    key = Varchar(length=32)
    earned_at = Real(default=0.0)


class DecorationRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    decoration_id = Varchar(length=32, help_text="The decoration's own uuid hex id")
    item = Varchar(length=32)
    room = Varchar(length=16, null=True, default=None, help_text="None while it is not placed")
    x = Real(default=0.0)
    y = Real(default=0.0)


class RoomRow(Table):
    id: Serial
    user_id = BigInt(index=True)
    room = Integer(help_text="Extra room number, 2 or 3")
    description = Text(default="")


TABLES: list[type[Table]] = sort_table_classes(
    [Player, PlotRow, SpotRow, AnimalRow, ItemRow, AchievementRow, DecorationRow, RoomRow]
)
