from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class Weekly(MixinMeta):
    @commands.command(name="weekly", aliases=["week"])
    @commands.guild_only()
    async def weekly(self, ctx: commands.Context) -> None:
        """View Weekly Leaderboard"""
        pass

    @commands.command(name="lastweekly")
    @commands.guild_only()
    async def lastweekly(self, ctx: commands.Context) -> None:
        """View Last Week's Leaderboard"""
        pass

    @commands.group(name="weeklyset", aliases=["wset"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def weeklyset(self, ctx: commands.Context) -> None:
        """Configure Weekly LevelUp Settings"""
        pass
