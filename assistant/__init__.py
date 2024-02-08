from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .assistant import Assistant

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    cog = Assistant(bot)
    await bot.add_cog(cog)
