import logging

from redbot.core import commands, Config
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .scraper import get_profile_data

log = logging.getLogger("red.vrt.halostats")


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

        stats = await self.bot.loop.run_in_executor(None, exe)
        return stats

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

    @commands.command(name="halostats")
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
            pages = await self.run_scraper(gamertag)
        if pages:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(f"Couldnt find stats for {gamertag}")
