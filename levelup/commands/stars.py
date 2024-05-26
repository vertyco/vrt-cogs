import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)

@cog_i18n(_)
class Stars(MixinMeta):
    @commands.command(name="stars", aliases=["givestar", "addstar", "thanks"])
    @commands.guild_only()
    async def stars(self, ctx: commands.Context, *, user: discord.Member) -> None:
        """Reward a good noodle"""
        pass

    @commands.command(name="startop", aliases=["topstars", "starleaderboard", "starlb"])
    @commands.guild_only()
    async def startop(self, ctx: commands.Context) -> None:
        """View the Star Leaderboard"""
        pass

    @commands.group(name="starset")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def starset(self, ctx: commands.Context) -> None:
        """Configure LevelUp Star Settings"""
        pass
