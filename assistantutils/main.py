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
        category: t.Optional[str] = None,
        requires_user_approval: bool = False,
    ) -> bool:
        raise NotImplementedError("This is a mock class for testing purposes.")


class AssistantUtils(Functions, commands.Cog, metaclass=CompositeMetaClass):
    """
    Assistant Utils adds pre-baked functions to the Assistant cog, allowing extended functionality.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.7.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: MockAssistantCog):
        grouped_registrations = (
            ("discord", "user", schemas.DISCORD_INFO_TOOLS),
            ("discord_search", "user", schemas.DISCORD_SEARCH_TOOLS),
            ("discord", "user", schemas.DISCORD_MESSAGE_TOOLS_USER),
            ("discord", "mod", schemas.DISCORD_MESSAGE_TOOLS_MOD),
            ("discord_admin", "admin", schemas.DISCORD_ADMIN_TOOLS),
            ("web", "user", (schemas.FETCH_URL,)),
            ("time", "user", (schemas.CONVERT_DATETIME_TIMESTAMP, schemas.GET_DISCORD_TIMESTAMP_FORMAT)),
            ("files", "user", (schemas.CREATE_AND_SEND_FILE, schemas.RENDER_SVG)),
            ("utility", "user", (schemas.RUN_COMMAND,)),
            ("moderation", "mod", (schemas.GET_MODLOG_CASES,)),
        )

        for category, permission_level, registered_schemas in grouped_registrations:
            for schema in registered_schemas:
                await cog.register_function(
                    self.qualified_name,
                    schema,
                    permission_level=permission_level,
                    category=category,
                    requires_user_approval=permission_level == "admin",
                )
        log.info("Functions have been registered")
