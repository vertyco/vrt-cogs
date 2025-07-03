import logging
import typing as t

from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .common import schemas
from .common.functions import Functions

log = logging.getLogger("red.vrt.assistantutils")


class MockAssistantCog:
    async def register_function(
        self,
        cog_name: str,
        schema: dict,
        permission_level: t.Literal["user", "mod", "admin", "owner"] = "user",
    ) -> bool:
        raise NotImplementedError("This is a mock class for testing purposes.")


class AssistantUtils(Functions, commands.Cog, metaclass=CompositeMetaClass):
    """
    Assistant Utils adds pre-baked functions to the Assistant cog, allowing extended functionality.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: MockAssistantCog):
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_LIST)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_INFO)
        await cog.register_function(self.qualified_name, schemas.GET_USER_INFO)
        await cog.register_function(self.qualified_name, schemas.SEARCH_INTERNET)
        await cog.register_function(self.qualified_name, schemas.FETCH_CHANNEL_HISTORY)
        await cog.register_function(self.qualified_name, schemas.CONVERT_DATETIME_TIMESTAMP)
        await cog.register_function(self.qualified_name, schemas.GET_DISCORD_TIMESTAMP_FORMAT)
        log.info("Functions have been registered")
