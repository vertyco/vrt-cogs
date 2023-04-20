
import discord
from redbot.core.utils import get_end_user_data_statement

from .inspire import Inspire

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot):
    cog = Inspire(bot)
    if discord.__version__ > "1.7.3":
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
