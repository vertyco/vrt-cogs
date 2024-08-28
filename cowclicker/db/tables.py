import logging

from discord.ext.commands.core import check
from piccolo.columns import BigInt, Serial, Timestamptz
from piccolo.table import Table, sort_table_classes
from redbot.core import commands

log = logging.getLogger("red.vrt.cowclicker.db.tables")


def ensure_db_connection():
    def predicate(ctx: commands.Context) -> bool:
        if not ctx.cog.db:
            if ctx.author.id not in ctx.bot.owner_ids:
                txt = "Database connection is not active, try again later"
            else:
                txt = f"Database connection is not active, configure with `{ctx.clean_prefix}clickerset postgres`"
            raise commands.UserFeedbackCheckFailure(txt)
        return True

    return check(predicate)


class Click(Table):
    id: Serial
    created_on = Timestamptz()
    author_id = BigInt()


TABLES: list[Table] = sort_table_classes([Click])
