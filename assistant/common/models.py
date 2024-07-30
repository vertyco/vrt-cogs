import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import discord
import numpy as np
import orjson
from pydantic import VERSION, BaseModel, Field
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.assistant.models")


class AssistantBaseModel(BaseModel):
    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = True):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults))


class Embedding(AssistantBaseModel):
    text: str
    embedding: List[float]
    ai_created: bool = False
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    modified: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    model: str = "text-embedding-ada-002"

    def created_at(self, relative: bool = False):
        t_type = "R" if relative else "F"
        return f"<t:{int(self.created.timestamp())}:{t_type}>"

    def modified_at(self, relative: bool = False):
        t_type = "R" if relative else "F"
        return f"<t:{int(self.modified.timestamp())}:{t_type}>"

    def update(self):
        self.modified = datetime.now(tz=timezone.utc)

    def __str__(self) -> str:
        return self.text


class CustomFunction(AssistantBaseModel):
    """Functions added by bot owner via string"""

    code: str
    jsonschema: dict
    permission_level: str = "user"  # user, mod, admin, owner

    def prep(self) -> Callable:
        """Prep function for execution"""
        exec(self.code, globals())
        return globals()[self.jsonschema["name"]]


class Usage(AssistantBaseModel):
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class GuildSettings(AssistantBaseModel):
    system_prompt: str = "You are a discord bot named {botname}, and are chatting with {username}."
    prompt: str = ""
    channel_prompts: Dict[int, str] = {}
    allow_sys_prompt_override: bool = False  # Per convo system prompt
    embeddings: Dict[str, Embedding] = {}
    usage: Dict[str, Usage] = {}
    blacklist: List[int] = []  # Channel/Role/User IDs
    tutors: List[int] = []  # Role or user IDs
    top_n: int = 3
    min_relatedness: float = 0.78
    embed_method: str = "dynamic"  # hybrid, dynamic, static, user
    question_mode: bool = False  # If True, only the first message and messages that end with ? will have emebddings
    channel_id: Optional[int] = 0
    api_key: Optional[str] = None
    endswith_questionmark: bool = False
    min_length: int = 7
    max_retention: int = 50
    max_retention_time: int = 1800
    max_response_tokens: int = 0
    max_tokens: int = 4000
    mention: bool = False
    mention_respond: bool = True
    enabled: bool = True  # Auto-reply channel
    model: str = "gpt-3.5-turbo"
    embed_model: str = "text-embedding-3-small"  # Or text-embedding-3-large, text-embedding-ada-002
    collab_convos: bool = False

    timezone: str = "UTC"
    temperature: float = 0.0  # 0.0 - 2.0
    frequency_penalty: float = 0.0  # -2.0 - 2.0
    presence_penalty: float = 0.0  # -2.0 - 2.0
    seed: Union[int, None] = None

    regex_blacklist: List[str] = [r"^As an AI language model,"]
    block_failed_regex: bool = False

    max_response_token_override: Dict[int, int] = {}
    max_token_role_override: Dict[int, int] = {}
    max_retention_role_override: Dict[int, int] = {}
    role_overrides: Dict[int, str] = Field(default_factory=dict, alias="model_role_overrides")
    max_time_role_override: Dict[int, int] = {}

    vision_detail: str = "auto"  # high, low, auto

    use_function_calls: bool = False
    max_function_calls: int = 20  # Max calls in a row
    disabled_functions: List[str] = []
    functions_called: int = 0

    def get_related_embeddings(
        self,
        query_embedding: List[float],
        top_n_override: Optional[int] = None,
        relatedness_override: Optional[float] = None,
    ) -> List[Tuple[str, str, float, int]]:
        def cosine_similarity(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        if not query_embedding:
            return []

        # Name, text, score, dimensions
        q_length = len(query_embedding)
        top_n = top_n_override or self.top_n
        min_relatedness = relatedness_override or self.min_relatedness

        if not top_n or q_length == 0 or not self.embeddings:
            return []

        strings_and_relatedness = []
        for name, em in self.embeddings.items():
            if q_length != len(em.embedding):
                continue
            try:
                score = cosine_similarity(query_embedding, em.embedding)
                if score >= min_relatedness:
                    strings_and_relatedness.append((name, em.text, score, len(em.embedding)))
            except ValueError as e:
                log.error(
                    f"Failed to compare '{name}' embedding {q_length} - {len(em.embedding)}",
                    exc_info=e,
                )

        if not strings_and_relatedness:
            return []

        strings_and_relatedness.sort(key=lambda x: x[2], reverse=True)
        return strings_and_relatedness[:top_n]

    def update_usage(
        self,
        model: str,
        total_tokens: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if model not in self.usage:
            self.usage[model] = Usage()
        if total_tokens:
            self.usage[model].total_tokens += total_tokens
        if input_tokens:
            self.usage[model].input_tokens += input_tokens
        if output_tokens:
            self.usage[model].output_tokens += output_tokens

    def get_user_model(self, member: Optional[discord.Member] = None) -> str:
        if not member or not self.role_overrides:
            return self.model
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.role_overrides:
                return self.role_overrides[role.id]
        return self.model

    def get_user_max_tokens(self, member: Optional[discord.Member] = None) -> int:
        if not member or not self.max_token_role_override:
            return self.max_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_token_role_override:
                return self.max_token_role_override[role.id]
        return self.max_tokens

    def get_user_max_response_tokens(self, member: Optional[discord.Member] = None) -> int:
        if not member or not self.max_response_token_override:
            return self.max_response_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_response_token_override:
                return self.max_response_token_override[role.id]
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


class Conversation(AssistantBaseModel):
    messages: List[dict] = []
    last_updated: float = 0.0
    system_prompt_override: Optional[str] = None

    def function_count(self) -> int:
        if not self.messages:
            return 0
        return sum(i["role"] in ["function", "tool"] for i in self.messages)

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
        self.refresh()
        self.messages.clear()

    def refresh(self):
        self.last_updated = datetime.now().timestamp()

    def overwrite(self, messages: List[dict]):
        self.refresh()
        self.messages = [i for i in messages if i["role"] != "system"]

    def update_messages(
        self,
        message: str,
        role: str,
        name: str = None,
        tool_id: str = None,
        position: int = None,
    ) -> None:
        """Update conversation cache

        Args:
            message (str): the message
            role (str): 'system', 'user' or 'assistant'
            name (str): the name of the bot or user
            position (int): the index to place the message in
        """
        message: dict = {"role": role, "content": message}
        if name:
            message["name"] = name
        if tool_id:
            message["tool_call_id"] = tool_id
        if position:
            self.messages.insert(position, message)
        else:
            self.messages.append(message)
        self.refresh()

    def prepare_chat(
        self,
        user_message: str,
        initial_prompt: str,
        system_prompt: str,
        name: str = None,
        images: List[str] = None,
        resolution: str = "auto",
    ) -> List[dict]:
        """Pre-appends the prmompts before the user's messages without motifying them"""
        prepared = []
        if system_prompt.strip():
            prepared.append({"role": "system", "content": system_prompt})
        if initial_prompt.strip():
            prepared.append({"role": "user", "content": initial_prompt})
        prepared.extend(self.messages)

        if images:
            content = [{"type": "text", "text": user_message}]
            for img in images:
                if img.lower().startswith("http"):
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img, "detail": resolution},
                        }
                    )
                else:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img}", "detail": resolution},
                        }
                    )

        else:
            content = user_message

        user_message_payload = {"role": "user", "content": content}
        if name:
            user_message_payload["name"] = name
        prepared.append(user_message_payload)
        self.messages.append(user_message_payload)
        self.refresh()
        return prepared


class DB(AssistantBaseModel):
    configs: Dict[int, GuildSettings] = {}
    conversations: Dict[str, Conversation] = {}
    persistent_conversations: bool = False
    functions: Dict[str, CustomFunction] = {}
    listen_to_bots: bool = False
    brave_api_key: Optional[str] = None

    def get_conf(self, guild: Union[discord.Guild, int]) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def get_conversation(
        self,
        member_id: int,
        channel_id: int,
        guild_id: int,
    ) -> Conversation:
        key = f"{member_id}-{channel_id}-{guild_id}"
        return self.conversations.setdefault(key, Conversation())

    async def prep_functions(
        self,
        bot: Red,
        conf: GuildSettings,
        registry: Dict[str, Dict[str, dict]],
        member: discord.Member = None,
        showall: bool = False,
    ) -> Tuple[List[dict], Dict[str, Callable]]:
        """Prep custom and registry functions for use with the API

        Args:
            bot (Red): Red instance
            conf (GuildSettings): current guild settings
            registry (Dict[str, Dict[str, dict]]): 3rd party cog registry dict

        Returns:
            Tuple[List[dict], Dict[str, Callable]]: List of json function schemas and a dict mapping to their callables
        """

        async def can_use(perm_level: str) -> bool:
            if perm_level == "user":
                return True
            if member is None:
                return False
            if perm_level == "mod":
                perms = [
                    member.guild_permissions.manage_messages,
                    await bot.is_mod(member),
                ]
                return any(perms)
            if perm_level == "admin":
                perms = [
                    member.guild_permissions.administrator,
                    await bot.is_admin(member),
                ]
                return any(perms)
            if perm_level == "owner":
                return await bot.is_owner(member)
            return False

        function_calls = []
        function_map = {}

        # Prep bot owner functions first
        for function_name, func in self.functions.items():
            if func.jsonschema["name"] in conf.disabled_functions:
                continue
            if not await can_use(func.permission_level) and not showall:
                continue
            function_calls.append(func.jsonschema)
            function_map[function_name] = func.prep()

        # Next prep registry functions
        for cog_name, function_schemas in registry.items():
            cog = bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, data in function_schemas.items():
                if function_name in conf.disabled_functions:
                    continue
                if function_name in function_map:
                    continue
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    log.error(f"{cog_name} doesnt have a function called {function_name}!")
                    continue
                if not await can_use(data["permission_level"]) and not showall:
                    log.debug(
                        f"{member.name} cannot use {function_name} with {data['permission_level']} permission level."
                    )
                    continue
                function_calls.append(data["schema"])
                function_map[function_name] = function_obj

        log.debug(f"Prepped: {function_map.keys()}")
        return function_calls, function_map


class NoAPIKey(Exception):
    """OpenAI Key no set"""


class EmbeddingEntryExists(Exception):
    """Entry name for embedding exits"""
