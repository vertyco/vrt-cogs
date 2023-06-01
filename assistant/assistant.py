import asyncio
import logging
from time import perf_counter
from typing import List, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .api import API
from .commands import AssistantCommands
from .common.utils import request_embedding
from .listener import AssistantListener
from .models import DB, Conversations, Embedding, EmbeddingEntryExists, NoAPIKey

log = logging.getLogger("red.vrt.assistant")


class Assistant(
    AssistantCommands,
    AssistantListener,
    API,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Advanced full featured Chat GPT integration, with all the tools needed to configure a knowledgable Q&A or chat bot!
    """

    __author__ = "Vertyco#0117"
    __version__ = "2.4.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.chats: Conversations = Conversations()

        self.saving = False

    async def cog_load(self) -> None:
        asyncio.create_task(self.init_cog())

    async def init_cog(self):
        await self.bot.wait_until_red_ready()
        start = perf_counter()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.parse_obj, data)
        log.info(f"Config loaded in {round((perf_counter() - start) * 1000, 2)}ms")

    async def save_conf(self):
        if self.saving:
            return
        try:
            self.saving = True
            start = perf_counter()
            dump = await asyncio.to_thread(self.db.dict)
            await self.config.db.set(dump)
            log.info(f"Config saved in {round((perf_counter() - start) * 1000, 2)}ms")
        except Exception as e:
            log.error("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    async def add_embedding(
        self, guild: discord.Guild, name: str, text: str, overwrite: bool = False
    ) -> Optional[List[float]]:
        """
        Method for other cogs to access and add embeddings

        Args:
            guild (discord.Guild): guild to pull config for
            name (str): the entry name for the embedding
            text (str): the text to be embedded
            overwrite (bool): whether to overwrite if entry exists

        Raises:
            NoAPIKey: If the specified guild has no api key associated with it
            EmbeddingEntryExists: If overwrite is false and entry name exists

        Returns:
            Optional[List[float]]: List of embedding weights if successfully generated
        """

        conf = self.db.get_conf(guild)
        if not conf.api_key:
            raise NoAPIKey("OpenAI key has not been set for this server!")
        if name in conf.embeddings and not overwrite:
            raise EmbeddingEntryExists(f"The entry name '{name}' already exists!")
        embedding = await request_embedding(text, conf.api_key)
        if not embedding:
            return None
        conf.embeddings[name] = Embedding(text=text, embedding=embedding)
        asyncio.create_task(self.save_conf())
        return embedding

    async def get_chat(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
    ) -> str:
        """Method for other cogs to call the chat API

        Args:
            message (str): content of question or chat message
            author (Union[discord.Member, int]): user asking the question
            guild (discord.Guild): guild associated with the chat
            channel (Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int]): used for context

        Raises:
            NoAPIKey: If the specified guild has no api key associated with it

        Returns:
            str: the reply from ChatGPT (may need to be pagified)
        """
        conf = self.db.get_conf(guild)
        if not conf.api_key:
            raise NoAPIKey("OpenAI key has not been set for this server!")
        return await self.get_chat_response(message, author, guild, channel, conf)
