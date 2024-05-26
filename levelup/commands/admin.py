from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)

@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(name="levelset", aliases=["lvlset"])
    @commands.guild_only()
    async def levelset(self, ctx: commands.Context) -> None:
        """Configure LevelUp Settings"""
        pass
