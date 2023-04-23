from datetime import datetime

import discord
import orjson
from pydantic import BaseModel

from .common.utils import num_tokens_from_string


class GuildSettings(BaseModel):
    system_prompt: str = "You are a helpful discord assistant named {botname}"
    prompt: str = "Current time: {timestamp}\nDiscord server you are chatting in: {server}"
    channel_id: int = 0
    api_key: str = ""
    endswith_questionmark: bool = False
    max_retention: int = 0
    max_retention_time: int = 1800
    min_length: int = 7
    mention: bool = False
    enabled: bool = True


class DB(BaseModel):
    configs: dict[int, GuildSettings] = {}

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson.dumps

    def get_conf(self, guild: discord.Guild) -> GuildSettings:
        if guild.id in self.configs:
            return self.configs[guild.id]

        self.configs[guild.id] = GuildSettings()
        return self.configs[guild.id]


class Conversation(BaseModel):
    messages: list[dict[str, str]] = []
    last_updated: float = 0.0

    def user_token_count(self) -> int:
        messages = "".join(message["content"] for message in self.messages)
        return num_tokens_from_string(messages)

    def token_count(self, conf: GuildSettings, message: str) -> int:
        initial = conf.system_prompt + conf.prompt + message
        return num_tokens_from_string(initial) + self.user_token_count()

    def is_expired(self, conf: GuildSettings):
        return (
            datetime.now().timestamp() - self.last_updated
        ) > conf.max_retention_time

    def cleanup(self, conf: GuildSettings):
        clear = [
            self.is_expired(conf),
            not conf.max_retention,
        ]
        if any(clear):
            self.messages.clear()
        elif conf.max_retention:
            self.messages = self.messages[-conf.max_retention :]

    def update_messages(
        self, conf: GuildSettings, message: str, role: str
    ) -> None:
        """Update conversation cache

        Args:
            conf (GuildSettings): guild settings
            message (str): the message
            role (str): 'system', 'user' or 'assistant'
            name (str): the name of the bot or user
        """
        while self.token_count(conf, message) > 4096 and self.messages:
            self.messages.pop(0)

        self.messages.append({"role": role, "content": message})
        self.last_updated = datetime.now().timestamp()

    def prepare_chat(
        self, system_prompt: str = "", initial_prompt: str = ""
    ) -> list[dict]:
        prepared = []
        if system_prompt:
            prepared.append({"role": "system", "content": system_prompt})
        if initial_prompt:
            prepared.append({"role": "user", "content": initial_prompt})
        prepared.extend(self.messages)
        return prepared


class Conversations(BaseModel):
    """Temporary conversation cache"""

    conversations: dict[int, Conversation] = {}

    def get_conversation(self, member: discord.Member) -> Conversation:
        key = f"{member.id}{member.guild.id}"
        if key in self.conversations:
            return self.conversations[key]

        self.conversations[key] = Conversation()
        return self.conversations[key]
