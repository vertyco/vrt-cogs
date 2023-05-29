import asyncio
import logging

import discord
from piccolo.engine.postgres import PostgresEngine
from red_postgres import create_database_and_tables, register_cog, run_migrations
from redbot.core import commands
from redbot.core.bot import Red

from .db.tables import MyTable
from .views.api_modal import SetConnectionView

log = logging.getLogger("red.vrt.piccolotemplate")


class PiccoloTemplate(commands.Cog):
    """
    This cog is a template for using Piccolo/Postgresql with Red
    """

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.db: PostgresEngine = None

    async def cog_load(self):
        asyncio.create_task(self.setup())

    async def setup(self):
        await self.bot.wait_until_red_ready()
        config = await self.bot.get_shared_api_tokens("piccolo")
        try:
            self.db, _ = await register_cog(self, config, [MyTable])
        except Exception as e:
            log.error("Failed to connect and initialize database", exc_info=e)
            return
        log.info("Initialized")

    async def cog_unload(self):
        if self.db:
            await self.db.close_connection_pool()

    @commands.command(name="configure")
    async def configure_connection_info(self, ctx: commands.Context):
        """Configure your postgres connection"""
        current = await self.bot.get_shared_api_tokens("piccolo")
        view = SetConnectionView(ctx.author, current)
        embed = discord.Embed(
            description="Click to configure your settings", color=ctx.author.color
        )
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        if not view.data:
            return await msg.edit(content="No data was entered", embed=None, view=None)

        if not view.data["port"].isdigit():
            return await ctx.send("Port must be a valid integer")

        await self.bot.set_shared_api_tokens("piccolo", **view.data)
        await msg.edit(content="Postgres configuration has been set!", embed=None, view=None)
        await self.setup()

    @commands.command(name="getdb")
    async def get_db_connection_test(self, ctx: commands.Context):
        """Refresh database connection"""
        current = await self.bot.get_shared_api_tokens("piccolo")
        self.db = await create_database_and_tables(self, current, [MyTable], max_size=20)
        await ctx.send(f"Running postgres version {await self.db.get_version()}")

    @commands.command(name="migrate")
    async def migrate_test(self, ctx: commands.Context):
        """Run migrations"""
        current = await self.bot.get_shared_api_tokens("piccolo")
        res = await run_migrations(self, current)
        await ctx.send(res)
