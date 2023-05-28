from redbot.core.bot import Red

from .piccolotemplate import PiccoloTemplate


async def setup(bot: Red):
    await bot.add_cog(PiccoloTemplate(bot))
