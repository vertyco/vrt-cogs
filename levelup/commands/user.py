import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)

@cog_i18n(_)
class User(MixinMeta):
    @commands.hybrid_command(name="profile", aliases=["pf"])
    @commands.guild_only()
    async def profile(self, ctx: commands.Context, *, user: discord.Member = None) -> None:
        """View User Profile"""
        pass

    @commands.hybrid_group(name="setprofile", aliases=["myprofile", "mypf", "pfset"])
    @commands.guild_only()
    async def setprofile(self, ctx: commands.Context) -> None:
        """Customize your profile"""
        pass

    @commands.hybrid_command(name="prestige")
    @commands.guild_only()
    async def prestige(self, ctx: commands.Context) -> None:
        """Prestige your profile"""
        pass
