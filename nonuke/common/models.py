
import discord

from . import Base


class GuildSettings(Base):
    enabled: bool = False
    log: int = 0  # Log channel
    cooldown: int = 10  # Seconds between actions
    overload: int = 3  # Actions within cooldown time
    dm: bool = False  # Whether to DM the user the bot takes action on
    action: str = "notify"  # Valid types are 'kick', 'ban', 'strip', and 'notify'
    ignore_bots: bool = False  # Whether to ignore other bots
    whitelist: list[int] = []  # Whitelist of trusted users(or bots)


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
