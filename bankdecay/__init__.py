# redgettext base.py generator.py levelup.py utils/formatter.py --command-docstring

from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .main import BankDecay

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    cog = BankDecay(bot)
    await bot.add_cog(cog)
