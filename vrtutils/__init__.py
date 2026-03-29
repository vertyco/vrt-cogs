from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .commands.todo import mock_edit_message
from .commands.updates import monkeypatch_repo, revert_monkeypatch_repo
from .vrtutils import VrtUtils

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)


async def setup(bot: Red):
    await bot.add_cog(VrtUtils(bot))
    bot.tree.add_command(mock_edit_message)
    monkeypatch_repo()


async def teardown(bot: Red):
    bot.tree.remove_command(mock_edit_message)
    revert_monkeypatch_repo()
