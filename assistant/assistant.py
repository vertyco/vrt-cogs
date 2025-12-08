import asyncio
import logging
from multiprocessing.pool import Pool
from time import perf_counter
from typing import Callable, Dict, List, Literal, Optional, Union

import discord
from discord.ext import tasks
from pydantic import ValidationError
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import AssistantCommands
from .common.api import API
from .common.chat import ChatHandler
from .common.constants import (
    CREATE_MEMORY,
    EDIT_IMAGE,
    EDIT_MEMORY,
    GENERATE_IMAGE,
    LIST_MEMORIES,
    RESPOND_AND_CONTINUE,
    SEARCH_INTERNET,
    SEARCH_MEMORIES,
)
from .common.functions import AssistantFunctions
from .common.models import DB, Embedding, EmbeddingEntryExists, NoAPIKey
from .common.utils import json_schema_invalid
from .listener import AssistantListener

log = logging.getLogger("red.vrt.assistant")


# redgettext -D views.py commands/admin.py commands/base.py common/api.py common/chat.py common/utils.py --command-docstring


class Assistant(
    API,
    AssistantCommands,
    AssistantFunctions,
    AssistantListener,
    ChatHandler,
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

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "6.18.13"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        for key in self.db.conversations.copy():
            if key.split("-")[0] == str(user_id):
                del self.db.conversations[key]

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.mp_pool = Pool()

        # {cog_name: {function_name: {"permission_level": "user", "schema": function_json_schema}}}
        self.registry: Dict[str, Dict[str, dict]] = {}

        self.saving = False
        self.first_run = True

    async def cog_load(self) -> None:
        asyncio.create_task(self.init_cog())

    async def cog_unload(self):
        self.save_loop.cancel()
        if self.endpoint_health_loop.is_running():
            self.endpoint_health_loop.cancel()
        self.mp_pool.close()
        self.bot.dispatch("assistant_cog_remove")

    async def init_cog(self):
        await self.bot.wait_until_red_ready()
        start = perf_counter()
        data = await self.config.db()
        try:
            self.db = await asyncio.to_thread(DB.model_validate, data)
        except ValidationError:
            # Try clearing conversations
            if "conversations" in data:
                del data["conversations"]
            self.db = await asyncio.to_thread(DB.model_validate, data)

        log.info(f"Config loaded in {round((perf_counter() - start) * 1000, 2)}ms")
        await asyncio.to_thread(self._cleanup_db)

        # Register internal functions
        await self.register_function(self.qualified_name, GENERATE_IMAGE)
        await self.register_function(self.qualified_name, EDIT_IMAGE)
        await self.register_function(self.qualified_name, SEARCH_INTERNET)
        await self.register_function(self.qualified_name, CREATE_MEMORY)
        await self.register_function(self.qualified_name, SEARCH_MEMORIES)
        await self.register_function(self.qualified_name, EDIT_MEMORY)
        await self.register_function(self.qualified_name, LIST_MEMORIES)
        await self.register_function(self.qualified_name, RESPOND_AND_CONTINUE)

        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("aiocache").setLevel(logging.WARNING)
        logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
        logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.bot.dispatch("assistant_cog_add", self)

        await asyncio.sleep(30)
        self.save_loop.start()
        if self.db.endpoint_override and self.db.endpoint_health_check:
            self.endpoint_health_loop.change_interval(seconds=self.db.endpoint_health_interval)
            self.endpoint_health_loop.start()

    async def save_conf(self):
        if self.saving:
            return
        try:
            self.saving = True
            start = perf_counter()
            if not self.db.persistent_conversations:
                self.db.conversations.clear()
            dump = await asyncio.to_thread(self.db.model_dump)
            await self.config.db.set(dump)
            txt = f"Config saved in {round((perf_counter() - start) * 1000, 2)}ms"
            if self.first_run:
                log.info(txt)
                self.first_run = False
        except Exception as e:
            log.error("Failed to save config", exc_info=e)
        finally:
            self.saving = False
        if not self.db.persistent_conversations and self.save_loop.is_running():
            self.save_loop.cancel()

    def _cleanup_db(self):
        cleaned = False
        # Cleanup registry if any cogs no longer exist
        for cog_name, cog_functions in self.registry.copy().items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                log.debug(f"{cog_name} no longer loaded. Unregistering its functions")
                del self.registry[cog_name]
                cleaned = True
                continue
            for function_name in cog_functions:
                if not hasattr(cog, function_name):
                    log.debug(f"{cog_name} no longer has function named {function_name}, removing")
                    del self.registry[cog_name][function_name]
                    cleaned = True

        # Clean up any stale channels
        for guild_id in self.db.configs.copy().keys():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                log.debug("Cleaning up guild")
                del self.db.configs[guild_id]
                cleaned = True
                continue
            conf = self.db.get_conf(guild_id)
            for role_id in conf.max_token_role_override.copy():
                if not guild.get_role(role_id):
                    log.debug("Cleaning deleted max token override role")
                    del conf.max_token_role_override[role_id]
                    cleaned = True
            for role_id in conf.max_retention_role_override.copy():
                if not guild.get_role(role_id):
                    log.debug("Cleaning deleted max retention override role")
                    del conf.max_retention_role_override[role_id]
                    cleaned = True
            for role_id in conf.role_overrides.copy():
                if not guild.get_role(role_id):
                    log.debug("Cleaning deleted model override role")
                    del conf.role_overrides[role_id]
                    cleaned = True
            for role_id in conf.max_time_role_override.copy():
                if not guild.get_role(role_id):
                    log.debug("Cleaning deleted max time override role")
                    del conf.max_time_role_override[role_id]
                    cleaned = True
            for obj_id in conf.blacklist.copy():
                discord_obj = guild.get_role(obj_id) or guild.get_member(obj_id) or guild.get_channel_or_thread(obj_id)
                if not discord_obj:
                    log.debug("Cleaning up invalid blacklisted ID")
                    conf.blacklist.remove(obj_id)
                    cleaned = True

            # Ensure embedding entry names arent too long
            new_embeddings = {}
            for entry_name, embedding in conf.embeddings.items():
                if len(entry_name) > 100:
                    log.debug(f"Embed entry more than 100 characters, truncating: {entry_name}")
                    cleaned = True
                new_embeddings[entry_name[:100]] = embedding
            conf.embeddings = new_embeddings
            conf.sync_embeddings(guild_id)

        health = "BAD (Cleaned)" if cleaned else "GOOD"
        log.info(f"Config health: {health}")

    @tasks.loop(minutes=30)
    async def save_loop(self):
        if not self.db.persistent_conversations:
            return
        await self.save_conf()

    @tasks.loop(seconds=60)
    async def endpoint_health_loop(self):
        """Monitor endpoint health and update bot presence"""
        if not self.db.endpoint_override or not self.db.endpoint_health_check:
            return

        # Set status to idle (yellow) during check
        await self.bot.change_presence(status=discord.Status.idle)

        # Validate endpoint using the extracted method
        valid, message = await self._validate_endpoint(self.db.endpoint_override)

        if valid:
            # Set status to online (green) when healthy
            await self.bot.change_presence(status=discord.Status.online)
            log.debug(f"Endpoint health check passed: {self.db.endpoint_override}")
        else:
            # Set status to DND (red) when unreachable
            await self.bot.change_presence(status=discord.Status.dnd)
            log.warning(f"Endpoint health check failed: {message}")

    @endpoint_health_loop.before_loop
    async def before_endpoint_health_loop(self):
        """Wait for bot to be ready before starting health checks"""
        await self.bot.wait_until_red_ready()

    # ------------------ 3rd PARTY ACCESSIBLE METHODS ------------------
    async def add_embedding(
        self,
        guild: discord.Guild,
        name: str,
        text: str,
        overwrite: bool = False,
        ai_created: bool = False,
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

        if name in conf.embeddings and not overwrite:
            raise EmbeddingEntryExists(f"The entry name '{name}' already exists!")

        embedding = await self.request_embedding(text, conf)
        if not embedding:
            return None
        conf.embeddings[name] = Embedding(
            text=text,
            embedding=embedding,
            ai_created=ai_created,
            model=conf.get_embed_model(self.db.endpoint_override),
        )
        await asyncio.to_thread(conf.sync_embeddings, guild.id)
        asyncio.create_task(self.save_conf())
        return embedding

    async def get_chat(
        self,
        message: str,
        author: Union[discord.Member, int],
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, int],
        function_calls: Optional[List[dict]] = None,
        function_map: Optional[Dict[str, Callable]] = None,
        extend_function_calls: bool = True,
        message_obj: Optional[discord.Message] = None,
    ) -> Union[str, None]:
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
            message_obj (Optional[discord.Message]): actual message object associated with the question

        Raises:
            NoAPIKey: If the specified guild has no api key associated with it

        Returns:
            str: the reply from ChatGPT (may need to be pagified)
        """
        conf = self.db.get_conf(guild)
        if not await self.can_call_llm(conf):
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
            message_obj,
        )

    # ------------------ 3rd PARTY FUNCTION REGISTRY ------------------
    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        event = "on_assistant_cog_add"
        funcs = [func for event_name, func in cog.get_listeners() if event_name == event]
        for func in funcs:
            self.bot._schedule_event(func, event, self)

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog):
        await self.unregister_cog(cog.qualified_name)

    async def register_functions(self, cog_name: str, schemas: List[dict]) -> None:
        """Quick way to register multiple functions for a cog

        Args:
            cog_name (str): the name of the cog registering the functions
            schemas (List[dict]): List of dicts representing the json schemas of the functions
        """
        for schema in schemas:
            await self.register_function(cog_name, schema)

    async def register_function(
        self,
        cog_name: str,
        schema: dict,
        permission_level: Literal["user", "mod", "admin", "owner"] = "user",
    ) -> bool:
        """Allow 3rd party cogs to register their functions for the model to use

        Args:
            cog_name (str): the name of the cog registering the function
            schema (dict): JSON schema representation of the command (see https://json-schema.org/understanding-json-schema/)
            permission_level (str): the permission level required to call the function (user, mod, admin, owner)

        Returns:
            bool: True if function was successfully registered
        """

        def fail(reason: str):
            return f"Function registry failed for {cog_name}: {reason}"

        cog = self.bot.get_cog(cog_name)
        if not cog:
            log.info(fail("Cog is not loaded or does not exist"))
            return False

        if not schema:
            log.info(fail("Empty schema dict provided!"))
            return False

        missing = json_schema_invalid(schema)
        if missing:
            log.info(fail(f"Invalid json schema!\nMISSING\n{missing}"))
            return False

        function_name = schema["name"]
        for registered_cog_name, registered_functions in self.registry.items():
            if registered_cog_name == cog_name:
                continue
            if function_name in registered_functions:
                err = f"{registered_cog_name} already registered the function {function_name}"
                log.info(fail(err))
                return False

        if not hasattr(cog, function_name):
            log.info(fail(f"Cog does not have a function called {function_name}"))
            return False

        if cog_name not in self.registry:
            self.registry[cog_name] = {}

        log.info(f"The {cog_name} cog registered a function object: {function_name}")
        self.registry[cog_name][function_name] = {"permission_level": permission_level, "schema": schema}
        return True

    async def unregister_function(self, cog_name: str, function_name: str) -> None:
        """Remove a specific cog's function from the registry

        Args:
            cog_name (str): name of the cog
            function_name (str): name of the function
        """
        if cog_name not in self.registry:
            log.debug(f"{cog_name} not in registry")
            return
        if function_name not in self.registry[cog_name]:
            log.debug(f"{function_name} not in {cog_name}'s registry")
            return
        del self.registry[cog_name][function_name]
        log.info(f"{cog_name} cog removed the function {function_name} from the registry")

    async def unregister_cog(self, cog_name: str) -> None:
        """Remove a cog from the registry

        Args:
            cog_name (str): name of the cog
        """
        if cog_name not in self.registry:
            log.debug(f"{cog_name} not in registry")
            return
        del self.registry[cog_name]
        log.info(f"{cog_name} cog removed from registry")
