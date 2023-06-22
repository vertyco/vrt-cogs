import asyncio
import inspect
import logging
from multiprocessing.pool import Pool
from time import perf_counter
from typing import Callable, Dict, List, Optional, Union

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .api import API
from .commands import AssistantCommands
from .common.utils import (
    code_string_valid,
    compile_function,
    json_schema_invalid,
    request_embedding,
)
from .listener import AssistantListener
from .models import DB, CustomFunction, Embedding, EmbeddingEntryExists, NoAPIKey

log = logging.getLogger("red.vrt.assistant")


class Assistant(
    AssistantCommands,
    AssistantListener,
    API,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Set up and configure an AI assistant (or chat) cog for your server with one of OpenAI's ChatGPT language models.

    Features include configurable prompt injection, dynamic embeddings, custom function calling, and more!

    - **[p]assistant**: base command for setting up the assistant
    - **[p]chat**: talk with the assistant
    - **[p]convostats**: view a user's token usage/conversation message count for the channel
    - **[p]clearconvo**: reset your conversation with the assistant in the channel
    """

    __author__ = "Vertyco#0117"
    __version__ = "3.4.16"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.re_pool = Pool()
        self.registry: Dict[str, Dict[str, CustomFunction]] = {}

        self.saving = False
        self.first_run = True

    async def cog_load(self) -> None:
        asyncio.create_task(self.init_cog())

    async def cog_unload(self):
        self.save_loop.cancel()
        self.re_pool.close()
        self.bot.dispatch("assistant_cog_remove")

    async def init_cog(self):
        await self.bot.wait_until_red_ready()
        start = perf_counter()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.parse_obj, data)
        log.info(f"Config loaded in {round((perf_counter() - start) * 1000, 2)}ms")
        logging.getLogger("openai").setLevel(logging.WARNING)
        self.bot.dispatch("assistant_cog_add", self)
        await asyncio.sleep(10)
        self.save_loop.start()

    async def save_conf(self):
        if self.saving:
            return
        try:
            self.saving = True
            start = perf_counter()
            if not self.db.persistent_conversations:
                self.db.conversations.clear()
            dump = await asyncio.to_thread(self.db.dict)
            await self.config.db.set(dump)
            if self.first_run:
                log.info(f"Config saved in {round((perf_counter() - start) * 1000, 2)}ms")
                self.first_run = False
        except Exception as e:
            log.error("Failed to save config", exc_info=e)
        finally:
            self.saving = False
        if not self.db.persistent_conversations and self.save_loop.is_running():
            self.save_loop.cancel()

    @tasks.loop(minutes=2)
    async def save_loop(self):
        if not self.db.persistent_conversations:
            return
        await self.save_conf()

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
        function_calls: Optional[List[dict]] = [],
        function_map: Optional[Dict[str, Callable]] = {},
        extend_function_calls: bool = True,
    ) -> str:
        """
        Method for other cogs to call the chat API

        This function uses the assistant's current configuration to respond

        Args:
            message (str): content of question or chat message
            author (Union[discord.Member, int]): user asking the question
            guild (discord.Guild): guild associated with the chat
            channel (Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int]): used for context
            functions (Optional[List[dict]]): custom functions that the api can call (see https://platform.openai.com/docs/guides/gpt/function-calling)
            function_map (Optional[Dict[str, Callable]]): mappings for custom functions {"FunctionName": Callable}
            extend_function_calls (bool=[False]): If True, configured functions are used in addition to the ones provided

        Raises:
            NoAPIKey: If the specified guild has no api key associated with it

        Returns:
            str: the reply from ChatGPT (may need to be pagified)
        """
        conf = self.db.get_conf(guild)
        if not conf.api_key:
            raise NoAPIKey("OpenAI key has not been set for this server!")
        return await self.get_chat_response(
            message,
            author,
            guild,
            channel,
            conf,
            function_calls,
            function_map,
            extend_function_calls,
        )

    async def register_functions(self, cog: commands.Cog, payload: List[dict]) -> None:
        """Quick way to register multiple functions for a cog

        Args:
            cog (commands.Cog)
            payload (List[dict]): List of dicts representing the json schema and function call or string

        Example:
            payload = [{"schema": {ValidJsonSchema}, "function": CallableOrString}, {...}, {...}]
        """
        for i in payload:
            await self.register_function(cog, i["schema"], i["function"])

    async def register_function(
        self, cog: commands.Cog, schema: dict, function: Union[str, Callable]
    ) -> bool:
        """Allow 3rd party cogs to register their functions for the model to use

        Args:
            cog (commands.Cog): the cog registering its commands
            schema (dict): JSON schema representation of the command (see https://json-schema.org/understanding-json-schema/)
            function (Union[str, Callable]): either the raw code string or the actual callable function

        Returns:
            bool: True if function was successfully registered
        """
        cog = cog.qualified_name

        def fail(reason: str):
            return f"Function registry failed for {cog}: {reason}"

        if not schema or not function:
            log.info(fail("Schema or Function not supplied"))
            return False
        if cog not in self.registry:
            self.registry[cog] = {}
        missing = json_schema_invalid(schema)
        if missing:
            log.info(fail(f"Invalid json schema. Reasons:\n{missing}"))
            return False
        function_name = schema["name"]
        for registered_cog, registered_functions in self.registry.items():
            if registered_cog == cog:
                continue
            if function_name in registered_functions:
                err = f"{registered_cog} already registered the function {function_name}"
                log.info(fail(err))
                return False

        if isinstance(function, str):
            if not code_string_valid(function):
                log.info(fail("Code string is invalid!"))
                return False
            function_string = function
            function = compile_function(function_name, function)
            log.info(f"The {cog} cog registered a function string: {function_name}")
        else:
            if function.__name__ != function_name:
                log.info(
                    fail("Function name from json schema does not match function name from code")
                )
                return False
            function_string = inspect.getsource(function)
            log.info(f"The {cog} cog registered a function object: {function_name}")

        self.registry[cog][function_name] = CustomFunction(
            code=function_string.strip(), jsonschema=schema, call=function
        )
        return True

    async def unregister_cog(self, cog: commands.Cog) -> None:
        """Remove a cog from the registry

        Args:
            cog (commands.Cog)
        """
        cog = cog.qualified_name
        if cog not in self.registry:
            return
        del self.registry[cog]
        log.info(f"{cog} cog removed from registry")

    async def unregister_function(self, cog: commands.Cog, function_name: str) -> None:
        """Remove a specific cog's function from the registry

        Args:
            cog (commands.Cog)
            function_name (str)
        """
        cog = cog.qualified_name
        if cog not in self.registry:
            return
        if function_name not in self.registry[cog]:
            return
        del self.registry[cog][function_name]
        log.info(f"{cog} cog removed the function {function_name} from the registry")

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        event = "on_assistant_cog_add"
        funcs = [listener[1] for listener in cog.get_listeners() if listener[0] == event]
        for func in funcs:
            # Thanks AAA3A for pointing out custom listeners!
            self.bot._schedule_event(func, event, self)

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog):
        await self.unregister_cog(cog)
