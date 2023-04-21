import discord
import orjson
from pydantic import BaseModel


class GuildSettings(BaseModel):
    prompt: str = ""
    channel_id: int = 0
    api_key: str = ""
    endswith_questionmark: bool = False
    max_retention: int = 1


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

    def update_messages(self, conf: GuildSettings, message: str, role: str):
        """Update conversation cache

        Args:
            conf (GuildSettings): guild settings
            message (str): the message
            role (str): 'system' or 'user'
        """
        self.messages.append({"role": role, "content": message})
        self.messages = self.messages[-conf.max_retention :]

    def prepare_chat(self, system_message: str, initial_prompt: str):
        prepared = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": initial_prompt},
        ]
        prepared.extend(self.messages)
        return prepared


class Conversations(BaseModel):
    """Temporary conversation cache"""

    conversations: dict[int, Conversation] = {}

    def get_conversation(self, member: discord.Member):
        key = f"{member.id}{member.guild.id}"
        if key in self.conversations:
            return self.conversations[key]

        self.conversations[key] = Conversation()
        return self.conversations[key]
