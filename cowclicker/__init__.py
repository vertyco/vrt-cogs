from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .main import CowClicker
from .views.click import CowClickComponent

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    cog = CowClicker(bot)
    await bot.add_cog(cog)
    bot.add_dynamic_items(CowClickComponent)


async def teardown(bot: Red):
    bot.remove_dynamic_items(CowClickComponent)
