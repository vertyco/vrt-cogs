import logging
import typing as t
from datetime import datetime, timezone
from time import perf_counter

import chromadb
import discord
import numpy as np
import orjson
from chromadb.errors import ChromaError
from pydantic import VERSION, BaseModel, Field
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.assistant.models")

_chroma_client = chromadb.Client()


class AssistantBaseModel(BaseModel):
    @classmethod
    def model_validate(cls, obj: t.Any, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = True, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults, **kwargs)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults, **kwargs))


class Embedding(AssistantBaseModel):
    text: str
    embedding: t.List[float]
    ai_created: bool = False
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    modified: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    model: str = "text-embedding-3-small"

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

    def prep(self) -> t.Callable:
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
    channel_prompts: t.Dict[int, str] = {}
    allow_sys_prompt_override: bool = False  # Per convo system prompt
    embeddings: t.Dict[str, Embedding] = {}
    usage: t.Dict[str, Usage] = {}
    blacklist: t.List[int] = []  # Channel/Role/User IDs
    tutors: t.List[int] = []  # Role or user IDs
    top_n: int = 3
    min_relatedness: float = 0.78
    embed_method: str = "dynamic"  # hybrid, dynamic, static, user
    question_mode: bool = False  # If True, only the first message and messages that end with ? will have emebddings
    channel_id: t.Optional[int] = 0  # The main auto-response channel ID
    listen_channels: t.List[int] = []  # Channels to listen to for auto-reply
    api_key: t.Optional[str] = None
    endswith_questionmark: bool = False
    min_length: int = 7
    max_retention: int = 50
    max_retention_time: int = 1800
    max_response_tokens: int = 0
    max_tokens: int = 4000
    mention: bool = False
    mention_respond: bool = True
    enabled: bool = True  # Auto-reply channel
    model: str = "gpt-5.1"
    embed_model: str = "text-embedding-3-small"  # Or text-embedding-3-large, text-embedding-ada-002
    collab_convos: bool = False
    reasoning_effort: str = "low"  # low, medium, high (or minimal for gpt-5)
    verbosity: str = "low"  # low, medium, high (gpt-5 only)

    # Auto-answer
    auto_answer: bool = False  # Answer questions anywhere if one is detected and embedding is found for it
    auto_answer_threshold: float = 0.7  # 0.0 - 1.0  # Confidence threshold for auto-answer
    auto_answer_ignored_channels: t.List[int] = []  # Channel IDs to ignore auto-answer
    auto_answer_model: str = "gpt-5.1"  # Model to use for auto-answer

    # Trigger words - reply to messages containing specific keywords/regex patterns
    trigger_enabled: bool = False  # Whether trigger word feature is enabled
    trigger_phrases: t.List[str] = []  # List of regex patterns to match
    trigger_prompt: str = ""  # Custom prompt to use when triggered
    trigger_ignore_channels: t.List[int] = []  # Channels to ignore trigger words

    image_command: bool = True  # Allow image commands

    timezone: str = "UTC"
    temperature: float = 0.0  # 0.0 - 2.0
    frequency_penalty: float = 0.0  # -2.0 - 2.0
    presence_penalty: float = 0.0  # -2.0 - 2.0
    seed: t.Union[int, None] = None

    regex_blacklist: t.List[str] = [r"^As an AI language model,"]
    block_failed_regex: bool = False

    max_response_token_override: t.Dict[int, int] = {}
    max_token_role_override: t.Dict[int, int] = {}
    max_retention_role_override: t.Dict[int, int] = {}
    role_overrides: t.Dict[int, str] = Field(default_factory=dict, alias="model_role_overrides")
    max_time_role_override: t.Dict[int, int] = {}

    vision_detail: str = "auto"  # high, low, auto

    use_function_calls: bool = False
    max_function_calls: int = 20  # Max calls in a row
    function_statuses: t.Dict[str, bool] = {}  # {"function_name": True/False for enabled/disabled}
    functions_called: int = 0

    def sync_embeddings(self, guild_id: int):
        try:
            collection = _chroma_client.get_collection(f"assistant-{guild_id}")
        except ChromaError as e:
            log.info(f"Failed to get collection for guild {guild_id}: {e}")
            collection = None

        if not collection:
            collection = _chroma_client.create_collection(
                f"assistant-{guild_id}",
                configuration={"hnsw": {"space": "cosine"}},
            )
            # Populate the collection with existing embeddings
            ids = list(self.embeddings.keys())
            if ids:  # Only add if there are embeddings
                log.info(f"Populating collection with {len(ids)} existing embeddings for guild {guild_id}")
                embeddings = [em.embedding for em in self.embeddings.values()]
                metadatas = [i.model_dump(exclude=["embedding"]) for i in self.embeddings.values()]
                collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
        else:
            # Make sure everything in self.embeddings is in the collection
            ids = list(self.embeddings.keys())
            collection_data = collection.get()
            existing_ids = collection_data["ids"] if collection_data["ids"] else []
            new_ids = [i for i in ids if i not in existing_ids]
            if new_ids:
                log.info(f"Adding {len(new_ids)} new embeddings to collection for guild {guild_id}")
                embeddings = [self.embeddings[i].embedding for i in new_ids]
                metadatas = [self.embeddings[i].model_dump(exclude=["embedding"]) for i in new_ids]
                collection.add(ids=new_ids, embeddings=embeddings, metadatas=metadatas)

            # See if there are any embeddings in the collection that are not in self.embeddings
            missing_ids = [i for i in existing_ids if i not in ids]
            if missing_ids:
                log.info(f"Removing {len(missing_ids)} old embeddings from collection for guild {guild_id}")
                collection.delete(ids=list(set(missing_ids)))

            # Make sure that all embeddings match the current text and vector (check for updates)
            for embed_name, em in self.embeddings.items():
                if embed_name not in existing_ids:
                    continue
                # Get the embedding by ID instead of text for more reliable matching
                result = collection.get(ids=[embed_name])

                if not result["ids"] or not result["embeddings"]:
                    log.warning(f"Embedding {embed_name} not found in collection for guild {guild_id}. Adding it.")
                    collection.add(
                        ids=[embed_name],
                        embeddings=[em.embedding],
                        metadatas=[em.model_dump(exclude=["embedding"])],
                    )
                else:
                    existing_embedding = result["embeddings"][0] if result["embeddings"] else []
                    if existing_embedding != em.embedding:
                        log.info(f"Updating embedding {embed_name} in collection for guild {guild_id}.")
                        collection.update(
                            ids=[embed_name],
                            embeddings=[em.embedding],
                            metadatas=[em.model_dump(exclude=["embedding"])],
                        )
                    else:
                        log.debug(f"Embedding {embed_name} is already up-to-date in collection for guild {guild_id}.")
        log.info(f"Synced embeddings for guild {guild_id} with {len(self.embeddings)} embeddings.")

    def get_related_embeddings(
        self,
        guild_id: int,
        query_embedding: t.List[float],
        top_n_override: t.Optional[int] = None,
        relatedness_override: t.Optional[float] = None,
    ) -> t.List[t.Tuple[str, str, float, int]]:
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

        if not all(q_length == len(em.embedding) for em in self.embeddings.values()):
            log.warning(
                f"Query embedding length {q_length} does not match all stored embeddings in guild {guild_id}. "
                "Skipping related embeddings search."
            )
            return []

        try:
            collection = _chroma_client.get_collection(f"assistant-{guild_id}")
        except ChromaError as e:
            log.info(f"Failed to get collection for guild {guild_id}: {e}")
            collection = None

        if not collection:
            collection = _chroma_client.create_collection(
                f"assistant-{guild_id}",
                metadata={"hnsw:space": "cosine", "guild_id": guild_id},
            )
            # Populate the collection with existing embeddings
            ids = list(self.embeddings.keys())
            log.info(f"Populating collection with {len(ids)} existing embeddings for guild {guild_id}")
            embeddings = [em.embedding for em in self.embeddings.values()]
            metadatas = [i.model_dump(exclude=["embedding"]) for i in self.embeddings.values()]
            collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas)

        start = perf_counter()
        results = collection.query(query_embeddings=[query_embedding], n_results=top_n_override or self.top_n)
        # print(results)
        strings_and_relatedness = []
        for idx in range(len(results["ids"][0])):
            embed_name = results["ids"][0][idx]
            embed_obj = self.embeddings.get(embed_name)
            if not embed_obj:
                # In collection but not config, remove it
                collection.delete(ids=[embed_name])
                continue
            embedding = self.embeddings[embed_name].embedding
            metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
            distance = results["distances"][0][idx] if results["distances"] else 0.0
            relatedness = 1 - distance
            if relatedness >= min_relatedness:
                strings_and_relatedness.append((embed_name, metadata["text"], relatedness, len(embedding)))

        end = perf_counter()
        iter_time = end - start
        log.debug(
            f"Got {len(strings_and_relatedness)} related embeddings in {iter_time:.2f} seconds for guild {guild_id}."
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

    def get_user_model(self, member: t.Optional[discord.Member] = None) -> str:
        if not member or not self.role_overrides:
            return self.model
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.role_overrides:
                return self.role_overrides[role.id]
        return self.model

    def get_user_max_tokens(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_token_role_override:
            return self.max_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_token_role_override:
                return self.max_token_role_override[role.id]
        return self.max_tokens

    def get_user_max_response_tokens(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_response_token_override:
            return self.max_response_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_response_token_override:
                return self.max_response_token_override[role.id]
        return self.max_tokens

    def get_user_max_retention(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_retention_role_override:
            return self.max_retention
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_retention_role_override:
                return self.max_retention_role_override[role.id]
        return self.max_retention

    def get_user_max_time(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_time_role_override:
            return self.max_retention_time
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_time_role_override:
                return self.max_time_role_override[role.id]
        return self.max_retention_time

    def get_embed_model(self, endpoint_override: t.Optional[str] = None) -> str:
        """Return the configured embed model, falling back to Ollama defaults on custom endpoints."""
        if endpoint_override and self.embed_model == "text-embedding-3-small":
            return "nomic-embed-text"
        return self.embed_model


class Conversation(AssistantBaseModel):
    messages: t.List[dict] = []
    last_updated: float = 0.0
    system_prompt_override: t.Optional[str] = None

    def get_images(self) -> t.List[str]:
        """Get all image b64 strings in the conversation
        Each string looks like "data:image/jpeg;base64,..." so we need to extract the base64 part

        """
        images = []
        for message in self.messages:
            if isinstance(message.get("content"), list):
                for item in message["content"]:
                    if item.get("type") == "image_url":
                        images.append(item["image_url"]["url"])
        if images:
            log.info(f"Found {len(images)} images in conversation.")
        return images

    def function_count(self) -> int:
        if not self.messages:
            return 0
        return sum(i["role"] in ["function", "tool"] for i in self.messages)

    def is_expired(self, conf: GuildSettings, member: t.Optional[discord.Member] = None):
        if not conf.get_user_max_time(member):
            return False
        return (datetime.now().timestamp() - self.last_updated) > conf.get_user_max_time(member)

    def cleanup(self, conf: GuildSettings, member: t.Optional[discord.Member] = None):
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

    def overwrite(self, messages: t.List[dict]):
        self.refresh()
        self.messages = [i for i in messages if i["role"] not in ["system", "developer"]]

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
        images: t.List[str] = None,
        resolution: str = "auto",
    ) -> t.List[dict]:
        """Pre-appends the prmompts before the user's messages without motifying them"""
        prepared = []
        if system_prompt.strip():
            prepared.append({"role": "developer", "content": system_prompt})
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
                    if img.startswith("data:image/"):
                        image_string = img
                    else:
                        image_string = f"data:image/png;base64,{img}"
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image_string, "detail": resolution},
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
    configs: t.Dict[int, GuildSettings] = {}
    conversations: t.Dict[str, Conversation] = {}
    persistent_conversations: bool = False
    functions: t.Dict[str, CustomFunction] = {}
    listen_to_bots: bool = False
    brave_api_key: t.Optional[str] = None
    endpoint_override: t.Optional[str] = None
    endpoint_health_check: bool = False
    endpoint_health_interval: int = 60

    def get_conf(self, guild: t.Union[discord.Guild, int]) -> GuildSettings:
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
        registry: t.Dict[str, t.Dict[str, dict]],
        member: discord.Member = None,
        showall: bool = False,
    ) -> t.Tuple[t.List[dict], t.Dict[str, t.Callable]]:
        """Prep custom and registry functions for use with the API

        Args:
            bot (Red): Red instance
            conf (GuildSettings): current guild settings
            registry (t.Dict[str, t.Dict[str, dict]]): 3rd party cog registry dict

        Returns:
            t.Tuple[t.List[dict], t.Dict[str, t.Callable]]: t.List of json function schemas and a dict mapping to their callables
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
            if not conf.function_statuses.get(function_name, False):
                # Function is disabled
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
                if not conf.function_statuses.get(function_name, False):
                    # Function is disabled
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
