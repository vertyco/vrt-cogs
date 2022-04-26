import logging

import discord
from redbot.core import commands, Config
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .scraper import get_profile_data

log = logging.getLogger("red.vrt.halostats")

LOADING = "https://i.imgur.com/Ar7duFt.gif"


class HaloStats(commands.Cog):
    """View your Halo Infinite stats"""
    __author__ = "Vertyco#0117"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" \
               f"Cog Version: {self.__version__}\n" \
               f"Author: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        full = await self.config.all_guilds()
        for guild_id in full:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            async with self.config.guild(guild).all() as conf:
                users = conf["users"]
                if str(user_id) in users:
                    del users[str(user_id)]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_global = {"users": {}}
        self.config.register_global(**default_global)

    async def run_scraper(self, gamertag: str) -> list:
        def exe():
            try:
                data = get_profile_data(gamertag)
                return data
            except Exception as e:
                log.warning(f"Web scraping error: {e}")

        result = await self.bot.loop.run_in_executor(None, exe)
        return result

    @commands.command(name="setmygt")
    async def set_gamertag(self, ctx, *, gamertag: str):
        """Set your Gamertag"""
        user_id = str(ctx.author.id)
        async with self.config.users() as users:
            if user_id not in users:
                users[user_id] = gamertag
                await ctx.tick()
            else:
                users[user_id] = gamertag
                await ctx.send("Your Gamertag has been overwritten!")

    @commands.command(name="halostats", aliases=["hstats", "hstat"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def view_halo_stats(self, ctx, *, gamertag: str = None):
        """View yours or another person's Halo stats"""
        user_id = str(ctx.author.id)
        if not gamertag:
            users = await self.config.users()
            if user_id in users:
                gamertag = users[user_id]
            else:
                return await ctx.send(f"Please include a Gamertag or type `{ctx.prefix}setmygt`")
        async with ctx.typing():
            embed = discord.Embed(
                description="Gathering Data..."
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            pages = await self.run_scraper(gamertag)
            await msg.delete()
            if pages:
                await menu(ctx, pages, DEFAULT_CONTROLS)
            else:
                await ctx.send(f"Couldnt find stats for {gamertag}")

