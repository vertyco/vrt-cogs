from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .commands.user import referredby_context
from .main import Referrals

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    await bot.add_cog(Referrals(bot))
    bot.tree.add_command(referredby_context)


async def teardown(bot: Red):
    bot.tree.remove_command(referredby_context)
