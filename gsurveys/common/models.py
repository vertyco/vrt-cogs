import discord
from pydantic import BaseModel


class Survey(BaseModel):
    name: str
    guild_id: int
    channel_id: int
    webhook_id: int
    webhook_url: str
    reward: int = 100
    discord_field: str = "Discord User ID"
    enabled: bool = True
    # Set of user IDs that have completed this survey
    completions: set[int] = set()


class GuildSettings(BaseModel):
    surveys: dict[str, Survey] = {}
    log_channel: int = 0
    notify_channel: int = 0


class DB(BaseModel):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def find_survey_by_webhook(self, guild_id: int, webhook_id: int) -> tuple[str, Survey] | None:
        conf = self.configs.get(guild_id)
        if not conf:
            return None
        for survey_id, survey in conf.surveys.items():
            if survey.webhook_id == webhook_id:
                return survey_id, survey
        return None
