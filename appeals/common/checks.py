from contextlib import suppress

import discord
from discord.ext.commands.core import check
from redbot.core import commands

from ..db.tables import AppealGuild


def ensure_db_connection():
    """Decorator to ensure a database connection is active.

    Example:
    ```python
    @ensure_db_connection()
    @commands.command()
    async def mycommand(self, ctx):
        await ctx.send("Database connection is active")
    ```
    """

    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.cog.db:
            txt = "Database connection is not active, try again later"
            with suppress(discord.HTTPException):
                await ctx.send(txt, ephemeral=True)
            return False
        return True

    return check(predicate)


def ensure_appeal_system_ready():
    async def predicate(ctx: commands.Context) -> bool:
        txt = (
            "This hasn't been set up for the appeal system yet!\n"
            f"Type `{ctx.clean_prefix}appeal help` to get started."
        )
        if not await AppealGuild.exists().where(AppealGuild.id == ctx.guild.id):
            with suppress(discord.HTTPException):
                await ctx.send(txt, ephemeral=True)
            return False
        return True

    return check(predicate)
