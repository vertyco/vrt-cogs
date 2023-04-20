
import discord
from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .pixl import Pixl

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    cog = Pixl(bot)
    if discord.version_info.major >= 2:
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
