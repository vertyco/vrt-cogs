from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .main import EmbEditor, full_edit_message, quick_edit_message

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    await bot.add_cog(EmbEditor(bot))
    bot.tree.add_command(quick_edit_message)
    bot.tree.add_command(full_edit_message)


async def teardown(bot: Red):
    bot.tree.remove_command(quick_edit_message)
    bot.tree.remove_command(full_edit_message)
