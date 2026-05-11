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

try:
    from ..common import constants
except ImportError:
    from common import constants

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

    notify_players = Array(base_column=BigInt(), default=list)  # List of user IDs to notify on rock spawn

    # When bot is using per-guild bank (amount // convert_rate = economy credits)
    conversion_enabled = Boolean(default=False)  # Whether conversion is enabled
    stone_convert_rate = Float(default=20.0)  # Stone to gems conversion rate
    iron_convert_rate = Float(default=5.0)  # Iron to gems conversion rate
    gems_convert_rate = Float(default=1.0)  # Gems to gems conversion rate


class GlobalSettings(TableMixin, Table):
    id = Serial(primary_key=True)
    key = SmallInt(unique=True, default=1)  # Always 1

    # Global spawn pacing settings
    spawn_cooldown_seconds = Integer(default=constants.DEFAULT_SPAWN_COOLDOWN_SECONDS)

    # When bot is using global bank (amount // convert_rate = economy credits)
    conversion_enabled = Boolean(default=False)  # Whether conversion is enabled
    stone_convert_rate = Float(default=20.0)  # Stone to gems conversion rate
    iron_convert_rate = Float(default=5.0)  # Iron to gems conversion rate
    gems_convert_rate = Float(default=1.0)  # Gems to gems conversion rate


class Player(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord User ID

    tool = Text(required=True, default="wood")  # Tool tier
    durability = BigInt(required=True)  # Current tool durability

    # Resources used for crafting
    stone = BigInt()
    iron = BigInt()
    gems = BigInt()


class PlayerAchievement(TableMixin, Table):
    id = Serial(primary_key=True)

    lookup_key = Text(required=True, unique=True)
    player = ForeignKey(required=True, references=Player)
    key = Text(required=True, index=True)


class PlayerAchievementStats(TableMixin, Table):
    id = Serial(primary_key=True)

    player = ForeignKey(required=True, references=Player, unique=True)

    rocks_mined_total = BigInt(default=0)
    group_sessions_total = BigInt(default=0)
    modifier_rocks_mined_total = BigInt(default=0)
    mined_small = Boolean(default=False)
    mined_medium = Boolean(default=False)
    mined_large = Boolean(default=False)
    mined_meteor = Boolean(default=False)
    mined_geode = Boolean(default=False)

    clean_streak_current = BigInt(default=0)
    clean_streak_best = BigInt(default=0)
    perf_max_streak_current = BigInt(default=0)
    perf_max_streak_best = BigInt(default=0)
    shatter_recovery_stage = SmallInt(default=0)

    role_breaker_total = BigInt(default=0)
    role_stabilizer_total = BigInt(default=0)
    role_finisher_total = BigInt(default=0)

    best_solo_small_seconds = Float(default=0.0)
    best_solo_medium_seconds = Float(default=0.0)
    best_solo_large_seconds = Float(default=0.0)
    best_solo_meteor_seconds = Float(default=0.0)
    best_solo_geode_seconds = Float(default=0.0)


class ResourceLedger(Table):
    id: Serial
    created_on = Timestamptz(index=True)
    player = ForeignKey(required=True, references=Player)
    resource = Text(required=True, index=True)
    amount = BigInt(required=True, index=True)


class ActiveChannel(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Channel ID
    guild = ForeignKey(required=True, references=GuildSettings)


TABLES: list[Table] = sort_table_classes(
    [
        Player,
        GuildSettings,
        GlobalSettings,
        ResourceLedger,
        ActiveChannel,
        PlayerAchievement,
        PlayerAchievementStats,
    ]
)
