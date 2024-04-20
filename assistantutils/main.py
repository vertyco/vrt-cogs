import logging

from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .common import schemas
from .common.functions import Functions

log = logging.getLogger("red.vrt.assistantutils")


class AssistantUtils(Functions, commands.Cog, metaclass=CompositeMetaClass):
    """
    Assistant Utils adds pre-baked functions to the Assistant cog, allowing extended functionality.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_ID)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_NAMED)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_MENTION)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_LIST)
        await cog.register_function(self.qualified_name, schemas.GET_CHANNEL_TOPIC)

        await cog.register_function(self.qualified_name, schemas.GET_SEARCH_URL)
        log.info("Functions have been registered")
