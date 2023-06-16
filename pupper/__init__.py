from redbot.core import VersionInfo, version_info
from redbot.core.utils import get_end_user_data_statement

from .pupper import Pupper

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot):
    cog = Pupper(bot)
    if version_info >= VersionInfo.from_str("3.5.0"):
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
