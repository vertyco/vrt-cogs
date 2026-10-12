from redbot.core.utils import get_end_user_data_statement

from .clickcounter import ClickCounter

# [p]mydata 3rdparty shows this. It is read from info.json
__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot):
    await bot.add_cog(ClickCounter(bot))
