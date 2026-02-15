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
    __version__ = "1.2.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: MockAssistantCog):
        # Discord info tools
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_LIST)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_INFO)
        await cog.register_function(self.qualified_name, schemas.GET_USER_INFO)
        await cog.register_function(self.qualified_name, schemas.GET_ROLE_INFO)
        await cog.register_function(self.qualified_name, schemas.GET_SERVER_INFO)
        # Web/utility tools
        await cog.register_function(self.qualified_name, schemas.SEARCH_INTERNET)
        await cog.register_function(self.qualified_name, schemas.FETCH_URL)
        await cog.register_function(self.qualified_name, schemas.FETCH_CHANNEL_HISTORY)
        # Datetime tools
        await cog.register_function(self.qualified_name, schemas.CONVERT_DATETIME_TIMESTAMP)
        await cog.register_function(self.qualified_name, schemas.GET_DISCORD_TIMESTAMP_FORMAT)
        # Action tools
        await cog.register_function(self.qualified_name, schemas.CREATE_AND_SEND_FILE)
        await cog.register_function(self.qualified_name, schemas.ADD_REACTION)
        await cog.register_function(self.qualified_name, schemas.SEARCH_MESSAGES)
        await cog.register_function(self.qualified_name, schemas.RUN_COMMAND)
        # Moderation tools
        await cog.register_function(self.qualified_name, schemas.GET_MODLOG_CASES, permission_level="mod")
        log.info("Functions have been registered")
