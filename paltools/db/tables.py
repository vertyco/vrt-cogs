from piccolo.columns import (
    BigInt,
    Boolean,
    ForeignKey,
    Integer,
    Serial,
    Text,
    Timestamptz,
)
from piccolo.columns.column_types import JSONB
from piccolo.table import Table, sort_table_classes
from redbot.core import commands
from redbot.core.commands import check


def ensure_db_connection():
    async def predicate(ctx: commands.Context) -> bool:
        if not getattr(ctx.cog, "db", None):
            if ctx.author.id in ctx.bot.owner_ids:
                txt = f"Database is not configured! Set it up with `{ctx.clean_prefix}paltools postgres`"
            else:
                txt = "Database connection is not active, try again later"
            raise commands.UserFeedbackCheckFailure(txt)
        return True

    return check(predicate)


class GuildSettings(Table):
    id: Serial
    guild_id = BigInt(unique=True, index=True)
    log_channel_id = BigInt(null=True, default=None)
    log_ips = Boolean(default=False)
    status_channel_id = BigInt(null=True, default=None)
    status_message_id = BigInt(null=True, default=None)  # the panel embed the poll loop edits in place
    timezone = Text(default="UTC")  # IANA name the panel graph's x axis is drawn in


class Server(Table):
    id: Serial
    guild_id = BigInt(index=True)
    name = Text()
    host = Text()
    port = Integer(default=8212)
    admin_password = Text()  # plaintext by design, same stance as arktools; documented in README
    enabled = Boolean(default=True)
    last_online = Timestamptz(null=True, default=None)  # drives the "Offline <relative>" panel line


class Player(Table):
    id: Serial
    lookup_key = Text(unique=True, index=True)  # f"{guild_id}-{user_id}"
    guild_id = BigInt(index=True)
    user_id = Text(index=True)  # PalWorld userId, e.g. steam_765611...
    name = Text(default="")
    account_name = Text(default="")
    name_history = JSONB(default=list)
    first_seen = Timestamptz()
    last_seen = Timestamptz()
    level = Integer(default=0)
    building_count = Integer(default=0)


class PlayerIp(Table):
    id: Serial
    lookup_key = Text(unique=True, index=True)  # f"{player_id}-{ip}"
    player = ForeignKey(required=True, references=Player)
    ip = Text(index=True)
    first_seen = Timestamptz()
    last_seen = Timestamptz()


class Session(Table):
    id: Serial
    # Indexed: every poll tick looks up open sessions by player+server, and the playtime
    # aggregates scan by player/server on a table that grows forever
    player = ForeignKey(required=True, references=Player, index=True)
    server = ForeignKey(required=True, references=Server, index=True)
    joined_at = Timestamptz()
    left_at = Timestamptz(null=True, default=None)  # null = currently online


TABLES: list[Table] = sort_table_classes([GuildSettings, Server, Player, PlayerIp, Session])
