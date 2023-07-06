import logging
from datetime import datetime
from typing import Callable, Dict, List, Literal, Optional, Tuple, Union

import discord
from openai.embeddings_utils import cosine_similarity
from pydantic import BaseModel
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.assistant.models")


class Embedding(BaseModel):
    text: str
    embedding: List[float]
    ai_created: bool = False


class CustomFunction(BaseModel):
    """Functions added by bot owner via string"""

    code: str
    jsonschema: dict

    def prep(self) -> Callable:
        """Prep function for execution"""
        exec(self.code, globals())
        return globals()[self.jsonschema["name"]]


class GuildSettings(BaseModel):
    system_prompt: str = "You are a helpful discord assistant named {botname}"
    prompt: str = "Current time: {timestamp}\nDiscord server you are chatting in: {server}"
    embeddings: Dict[str, Embedding] = {}
    blacklist: List[int] = []  # Channel/Role/User IDs
    tutors: List[int] = []  # Role or user IDs
    top_n: int = 3
    min_relatedness: float = 0.75
    embed_method: Literal["dynamic", "static", "hybrid"] = "dynamic"
    channel_id: Optional[int] = 0
    api_key: Optional[str] = None
    endswith_questionmark: bool = False
    min_length: int = 7
    max_retention: int = 0
    max_retention_time: int = 1800
    max_tokens: int = 4000
    mention: bool = False
    enabled: bool = True
    model: str = "gpt-3.5-turbo"
    endpoint_override: Optional[str] = None

    timezone: str = "UTC"
    temperature: float = 0.0
    regex_blacklist: List[str] = [r"^As an AI language model,"]
    block_failed_regex: bool = False

    max_token_role_override: Dict[int, int] = {}
    max_retention_role_override: Dict[int, int] = {}
    model_role_overrides: Dict[int, str] = {}
    max_time_role_override: Dict[int, int] = {}

    image_tools: bool = True
    image_size: Literal["256x256", "512x512", "1024x1024"] = "1024x1024"
    use_function_calls: bool = False
    max_function_calls: int = 10  # Max calls in a row
    disabled_functions: List[str] = []

    def get_related_embeddings(self, query_embedding: List[float]) -> List[Tuple[str, str, float]]:
        if not self.top_n or len(query_embedding) == 0 or not self.embeddings:
            return []
        strings_and_relatedness = []
        for name, em in self.embeddings.items():
            if len(query_embedding) != len(em.embedding):
                continue
            try:
                score = cosine_similarity(query_embedding, em.embedding)
            except ValueError as e:
                log.error(
                    f"Failed to match '{name}' embedding {len(query_embedding)} - {len(em.embedding)}",
                    exc_info=e,
                )
                continue
            strings_and_relatedness.append((name, em.text, score, len(em.embedding)))

        strings_and_relatedness = [
            i for i in strings_and_relatedness if i[2] >= self.min_relatedness
        ]
        strings_and_relatedness.sort(key=lambda x: x[2], reverse=True)
        return strings_and_relatedness[: self.top_n]

    def get_user_model(self, member: Optional[discord.Member] = None) -> str:
        if not member or not self.model_role_overrides:
            return self.model
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.model_role_overrides:
                return self.model_role_overrides[role.id]
        return self.model

    def get_user_max_tokens(self, member: Optional[discord.Member] = None) -> int:
        if not member or not self.max_token_role_override:
            return self.max_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_token_role_override:
                return self.max_token_role_override[role.id]
        return self.max_tokens

    def get_user_max_retention(self, member: Optional[discord.Member] = None) -> int:
        if not member or not self.max_retention_role_override:
            return self.max_retention
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_retention_role_override:
                return self.max_retention_role_override[role.id]
        return self.max_retention

    def get_user_max_time(self, member: Optional[discord.Member] = None) -> int:
        if not member or not self.max_time_role_override:
            return self.max_retention_time
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_time_role_override:
                return self.max_time_role_override[role.id]
        return self.max_retention_time


class Conversation(BaseModel):
    messages: list[dict[str, str]] = []
    last_updated: float = 0.0

    def function_count(self) -> int:
        if not self.messages:
            return 0
        return sum(i["role"] == "function" for i in self.messages)

    def is_expired(self, conf: GuildSettings, member: Optional[discord.Member] = None):
        if not conf.get_user_max_time(member):
            return False
        return (datetime.now().timestamp() - self.last_updated) > conf.get_user_max_time(member)

    def cleanup(self, conf: GuildSettings, member: Optional[discord.Member] = None):
        clear = [
            self.is_expired(conf, member),
            not conf.get_user_max_retention(member),
        ]
        if any(clear):
            self.messages.clear()
        elif conf.max_retention:
            self.messages = self.messages[-conf.get_user_max_retention(member) :]

    def reset(self):
        self.last_updated = datetime.now().timestamp()
        self.messages.clear()

    def overwrite(self, messages: List[dict]):
        self.reset()
        for i in messages:
            if i["role"] == "system":
                continue
            self.messages.append(i)

    def update_messages(self, message: str, role: str, name: str = None) -> None:
        """Update conversation cache

        Args:
            message (str): the message
            role (str): 'system', 'user' or 'assistant'
            name (str): the name of the bot or user
        """
        message = {"role": role, "content": message}
        if name:
            message["name"] = name
        self.messages.append(message)
        self.last_updated = datetime.now().timestamp()

    def prepare_chat(
        self, user_message: str, initial_prompt: str, system_prompt: str
    ) -> List[dict]:
        """Pre-appends the prmompts before the user's messages without motifying them"""
        prepared = []
        if system_prompt:
            prepared.append({"role": "system", "content": system_prompt})
        if initial_prompt:
            prepared.append({"role": "user", "content": initial_prompt})
        prepared.extend(self.messages)
        user_message = {"role": "user", "content": user_message}
        prepared.append(user_message)
        self.messages.append(user_message)
        self.last_updated = datetime.now().timestamp()
        return prepared


class DB(BaseModel):
    configs: dict[int, GuildSettings] = {}
    conversations: dict[str, Conversation] = {}
    persistent_conversations: bool = False
    functions: Dict[str, CustomFunction] = {}

    endpoint_override: Optional[str] = None

    def get_conf(self, guild: Union[discord.Guild, int]) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id

        if gid in self.configs:
            return self.configs[gid]

        self.configs[gid] = GuildSettings()
        return self.configs[gid]

    def get_conversation(
        self,
        member_id: int,
        channel_id: int,
        guild_id: int,
    ) -> Conversation:
        key = f"{member_id}-{channel_id}-{guild_id}"
        if key in self.conversations:
            return self.conversations[key]

        self.conversations[key] = Conversation()
        return self.conversations[key]

    def prep_functions(
        self,
        bot: Red,
        conf: GuildSettings,
        registry: Dict[str, Dict[str, dict]],
    ) -> Tuple[List[dict], Dict[str, Callable]]:
        """Prep custom and registry functions for use with the API

        Args:
            bot (Red): Red instance
            conf (GuildSettings): current guild settings
            registry (Dict[str, Dict[str, dict]]): 3rd party cog registry dict

        Returns:
            Tuple[List[dict], Dict[str, Callable]]: List of json function schemas and a dict mapping to their callables
        """
        function_calls = []
        function_map = {}

        # Prep bot owner functions first
        for function_name, func in self.functions.items():
            if func.jsonschema["name"] in conf.disabled_functions:
                continue
            function_calls.append(func.jsonschema)
            function_map[function_name] = func.prep()

        # Next prep registry functions
        for cog_name, function_schemas in registry.items():
            cog = bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, function_schema in function_schemas.items():
                if function_name in conf.disabled_functions:
                    continue
                if function_name in function_map:
                    continue
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    continue
                function_calls.append(function_schema)
                function_map[function_name] = function_obj

        return function_calls, function_map


class NoAPIKey(Exception):
    """OpenAI Key no set"""


class EmbeddingEntryExists(Exception):
    """Entry name for embedding exits"""
