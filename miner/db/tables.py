import logging

from piccolo.columns import (
    Array,
    BigInt,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Serial,
    SmallInt,
    Text,
    Timestamptz,
)
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.table import Table, sort_table_classes
from redbot.core import commands
from redbot.core.commands import check

log = logging.getLogger("red.vrt.miner.db.tables")


def ensure_db_connection():
    async def predicate(ctx: commands.Context) -> bool:
        if not getattr(ctx.cog, "db", None):
            raise commands.UserFeedbackCheckFailure("Database connection is not active, try again later")
        return True

    return check(predicate)


class TableMixin:
    created_on = Timestamptz()
    updated_on = Timestamptz(auto_update=TimestamptzNow().python)


class GuildSettings(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Guild ID
    per_channel_activity_trigger = Boolean(default=False)  # Whether to use per-channel activity tracking

    notify_players = Array(base_column=BigInt(), default=list)  # List of user IDs to notify on rock spawn
    time_between_spawns = Integer()  # Min time between spawns in seconds

    # When bot is using per-guild bank (amount // convert_rate = economy credits)
    conversion_enabled = Boolean(default=False)  # Whether conversion is enabled
    stone_convert_rate = Float(default=20.0)  # Stone to gems conversion rate
    iron_convert_rate = Float(default=5.0)  # Iron to gems conversion rate
    gems_convert_rate = Float(default=1.0)  # Gems to gems conversion rate


class GlobalSettings(TableMixin, Table):
    id = Serial(primary_key=True)
    key = SmallInt(unique=True, default=1)  # Always 1

    # When bot is using global bank (amount // convert_rate = economy credits)
    conversion_enabled = Boolean(default=False)  # Whether conversion is enabled
    stone_convert_rate = Float(default=20.0)  # Stone to gems conversion rate
    iron_convert_rate = Float(default=5.0)  # Iron to gems conversion rate
    gems_convert_rate = Float(default=1.0)  # Gems to gems conversion rate

    # Global rock spawn timing configuration (in seconds)
    # These control the minimum and maximum time between rock spawns globally.
    # If unset, they fall back to the constants defined in miner.common.constants.
    min_spawn_interval = Integer(null=True)
    max_spawn_interval = Integer(null=True)


class Player(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord User ID

    tool = Text(required=True, default="wood")  # Tool tier
    durability = BigInt(required=True)  # Current tool durability

    # Resources used for crafting
    stone = BigInt()
    iron = BigInt()
    gems = BigInt()


class ResourceLedger(Table):
    id: Serial
    created_on = Timestamptz(index=True)
    player = ForeignKey(required=True, references=Player)
    resource = Text(required=True, index=True)
    amount = BigInt(required=True, index=True)


class ActiveChannel(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Channel ID
    guild = ForeignKey(required=True, references=GuildSettings)


TABLES: list[Table] = sort_table_classes([Player, GuildSettings, GlobalSettings, ResourceLedger, ActiveChannel])
