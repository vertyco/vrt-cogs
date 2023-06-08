from datetime import datetime
from typing import Dict, List, Literal, Tuple, Union

import discord
import orjson
from openai.embeddings_utils import cosine_similarity
from pydantic import BaseModel

from .common.utils import num_tokens_from_string

MODELS = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "code-davinci-002": 8001,
    "text-davinci-003": 4097,
    "text-davinci-002": 4097,
    "text-curie-001": 2049,
    "text-babbage-001": 2049,
    "text-ada-001": 2049,
}
CHAT = [
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-32k",
    "code-davinci-002",
]
COMPLETION = [
    "text-davinci-003",
    "text-davinci-002",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",
]
READ_EXTENSIONS = [
    ".txt",
    ".py",
    ".json",
    ".xml",
    ".html",
    ".ini",
    ".css",
    ".toml",
    ".md",
    ".ini",
    ".conf",
    ".go",
    ".cfg",
    ".java",
    ".c",
    ".php",
    ".swift",
    ".vb",
    ".xhtml",
    ".rss",
    ".css",
    ".asp",
    ".js",
    ".ts",
    ".cs",
    ".c++",
    ".cc",
    ".ps1",
    ".bat",
    ".batch",
    ".shell",
]


class Embedding(BaseModel):
    text: str
    embedding: List[float]

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson.dumps


class GuildSettings(BaseModel):
    system_prompt: str = "You are a helpful discord assistant named {botname}"
    prompt: str = "Current time: {timestamp}\nDiscord server you are chatting in: {server}"
    embeddings: Dict[str, Embedding] = {}
    top_n: int = 3
    min_relatedness: float = 0.75
    embed_method: Literal["dynamic", "static", "hybrid"] = "dynamic"
    channel_id: int = 0
    api_key: str = ""
    endswith_questionmark: bool = False
    max_retention: int = 0
    max_retention_time: int = 1800
    max_tokens: int = 4000
    min_length: int = 7
    mention: bool = False
    enabled: bool = True
    model: str = "gpt-3.5-turbo"
    timezone: str = "UTC"
    temperature: float = 0.0
    regex_blacklist: List[str] = [r"^As an AI language model,"]
    blacklist: List[int] = []  # Channel/Role/User IDs
    image_tools: bool = True
    image_size: Literal["256x256", "512x512", "1024x1024"] = "1024x1024"

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson.dumps

    def get_related_embeddings(self, query_embedding: List[float]) -> List[Tuple[str, float]]:
        if not self.top_n or not query_embedding or not self.embeddings:
            return []
        strings_and_relatedness = [
            (name, i.text, cosine_similarity(query_embedding, i.embedding))
            for name, i in self.embeddings.items()
        ]
        strings_and_relatedness = [
            i for i in strings_and_relatedness if i[2] >= self.min_relatedness
        ]
        strings_and_relatedness.sort(key=lambda x: x[2], reverse=True)
        return strings_and_relatedness[: self.top_n]


class Conversation(BaseModel):
    messages: list[dict[str, str]] = []
    last_updated: float = 0.0

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson.dumps

    def token_count(self) -> int:
        return num_tokens_from_string("".join(message["content"] for message in self.messages))

    def user_token_count(self, message: str = "") -> int:
        messages = "".join(message["content"] for message in self.messages)
        if not self.messages:
            messages = ""
        messages += message
        return num_tokens_from_string(messages)

    def conversation_token_count(self, conf: GuildSettings) -> int:
        initial = conf.system_prompt + conf.prompt
        return num_tokens_from_string(initial) + self.user_token_count()

    def is_expired(self, conf: GuildSettings):
        if not conf.max_retention_time:
            return False
        return (datetime.now().timestamp() - self.last_updated) > conf.max_retention_time

    def cleanup(self, conf: GuildSettings):
        clear = [
            self.is_expired(conf),
            not conf.max_retention,
        ]
        if any(clear):
            self.messages.clear()
        elif conf.max_retention:
            self.messages = self.messages[-conf.max_retention :]

    def reset(self):
        self.last_updated = datetime.now().timestamp()
        self.messages.clear()

    def update_messages(self, message: str, role: str) -> None:
        """Update conversation cache

        Args:
            message (str): the message
            role (str): 'system', 'user' or 'assistant'
            name (str): the name of the bot or user
        """
        self.messages.append({"role": role, "content": message})
        self.last_updated = datetime.now().timestamp()

    def prepare_chat(
        self, user_message: str, initial_prompt: str, system_prompt: str
    ) -> List[dict]:
        prepared = []
        if initial_prompt:
            prepared.append({"role": "user", "content": initial_prompt})
        prepared.extend(self.messages)
        if system_prompt:
            prepared.append({"role": "system", "content": system_prompt})
        user_message = {"role": "user", "content": user_message}
        prepared.append(user_message)
        self.messages.append(user_message)
        return prepared


class DB(BaseModel):
    configs: dict[int, GuildSettings] = {}
    conversations: dict[str, Conversation] = {}
    persistent_conversations: bool = False

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson.dumps

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


class NoAPIKey(Exception):
    """OpenAI Key no set"""


class EmbeddingEntryExists(Exception):
    """Entry name for embedding exits"""
