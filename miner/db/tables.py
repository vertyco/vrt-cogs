import logging

from discord.ext.commands.core import check
from piccolo.columns import BigInt, ForeignKey, Text, Timestamptz
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.table import Table, sort_table_classes
from redbot.core import commands

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


class Player(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord User ID

    tool = Text(required=True, default="wood")  # Tool tier
    durability = BigInt(required=True)  # Current tool durability

    # Resources used for crafting
    stone = BigInt()
    iron = BigInt()
    gems = BigInt()


class ActiveChannel(TableMixin, Table):
    id = BigInt(primary_key=True)  # Discord Channel ID
    guild = ForeignKey(required=True, references=GuildSettings)


TABLES: list[Table] = sort_table_classes([Player, GuildSettings, ActiveChannel])
