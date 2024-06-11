from __future__ import annotations

import logging
import math
import os
import typing as t
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

import discord
import orjson
from pydantic import VERSION, BaseModel, Field
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.levelup.models")


class Base(BaseModel):
    """Custom BaseModel with additional methods for loading and saving settings safely"""

    @classmethod
    def load(cls, obj: t.Dict[str, t.Any]) -> Base:
        if VERSION >= "2.0.1":
            return cls.model_validate(obj)
        return cls.parse_obj(obj)

    @classmethod
    def loadjson(cls, obj: t.Union[str, bytes]) -> Base:
        if VERSION >= "2.0.1":
            return cls.model_validate_json(obj)
        return cls.parse_raw(obj)

    def dump(self, exclued_defaults: bool = True) -> t.Dict[str, t.Any]:
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclued_defaults)
        return orjson.loads(self.json(exclude_defaults=exclued_defaults))

    def dumpjson(self, exclude_defaults: bool = True, pretty: bool = False) -> str:
        kwargs = {"exclude_defaults": exclude_defaults}
        if pretty:
            kwargs["indent"] = 2
        if VERSION >= "2.0.1":
            return self.model_dump_json(**kwargs)
        return self.json(**kwargs)

    @classmethod
    def from_file(cls, path: Path) -> Base:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Path is not a file: {path}")
        if VERSION >= "2.0.1":
            return cls.model_validate_json(path.read_text())
        return cls.parse_file(path)

    def to_file(self, path: Path) -> None:
        if VERSION >= "2.0.1":
            dump = self.model_dump_json(indent=2, exclude_defaults=True)
        else:
            dump = self.json(exclude_defaults=True)
        # We want to write the file as safely as possible
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/_drivers/json.py#L224
        tmp_path = path.parent / f"{path.stem}-{round(perf_counter())}.tmp"
        with tmp_path.open(encoding="utf-8", mode="w") as fs:
            fs.write(dump)
            fs.flush()  # This does get closed on context exit, ...
            os.fsync(fs.fileno())  # but that needs to happen prior to this line

        tmp_path.replace(path)
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


class Profile(Base):
    xp: float = 0  # Experience points
    voice: float = 0  # Voice time in seconds
    messages: int = 0  # Message count
    level: int = 0  # Level
    prestige: int = 0  # Prestige level
    stars: int = 0
    last_active: datetime = Field(
        default_factory=datetime.now,
        description="Last time the user was active in the guild (message sent or voice activity)",
    )

    # For image profiles
    style: str = "default"  # Can be default, runescape... (WIP)
    background: str = "default"  # Can be default, random, filename, or URL
    namecolor: t.Union[str, None] = None  # Hex color
    statcolor: t.Union[str, None] = None  # Hex color
    barcolor: t.Union[str, None] = None  # Hex color
    font: t.Union[str, None] = None  # Font name (must match font file)
    blur: bool = True  # Blur background of stat area
    show_displayname: bool = False  # Show display name instead of username on profile

    def add_message(self) -> Profile:
        self.messages += 1
        self.last_active = datetime.now()
        return self


class ProfileWeekly(Base):
    xp: float = 0
    voice: float = 0
    messages: int = 0
    stars: int = 0

    def add_message(self) -> ProfileWeekly:
        self.messages += 1
        return self


class WeeklySettings(Base):
    on: bool = False  # Weekly stats are being tracked for this guild or not
    autoreset: bool = False  # Whether to auto reset once a week or require manual reset
    reset_hour: int = 0  # 0 - 23 hour (Server's system time)
    reset_day: int = 0  # 0 = sun, 1 = mon, 2 = tues, 3 = wed, 4 = thur, 5 = fri, 6 = sat
    last_reset: int = 0  # Timestamp of when weekly was last reset
    count: int = 3  # How many users to show in weekly winners
    channel: int = 0  # Announce the weekly winners (top 3 by default)
    role: int = 0  # Role awarded to top member(s) for that week
    role_all: bool = False  # If True, all winners get the role
    last_winners: t.List[int] = []  # IDs of last members that won if role_all is enabled
    remove: bool = True  # Whether to remove the role from the previous winner when a new one is announced
    bonus: int = 0  # Bonus exp to award the top X winners
    last_embed: t.Dict[str, t.Any] = {}  # Dict repr of last winner embed

    @property
    def next_reset(self) -> int:
        now = datetime.now()
        reset = now + timedelta((self.reset_day - now.weekday()) % 7)
        return int(reset.replace(hour=self.reset_hour, minute=0, second=0).timestamp())

    def refresh(self):
        self.last_reset = int(datetime.now().timestamp())


class Prestige(Base):
    role: int
    emoji_string: str
    emoji_url: str


class RoleBonus(Base):
    msg: t.Dict[int, t.List[int]] = {}  # Role_ID: [Min, Max]
    voice: t.Dict[int, t.List[int]] = {}  # Role_ID: [Min, Max]


class ChannelBonus(Base):
    msg: t.Dict[int, t.List[int]] = {}  # Channel_ID: [Min, Max]
    voice: t.Dict[int, t.List[int]] = {}  # Channel_ID: [Min, Max]


class Algorithm(Base):
    base: int = 100  # Base denominator for level algorithm, higher takes longer to level
    exp: float = 2.0  # Exponent for level algorithm, higher is a more exponential/steeper curve

    def get_level(self, xp: t.Union[int, float]) -> int:
        """Calculate the level that corresponds to the given XP amount"""
        return int((xp / self.base) ** (1 / self.exp))

    def get_xp(self, level: int) -> int:
        """Calculate XP required to reach specified level"""
        return math.ceil(self.base * (level**self.exp))


class Emojis(Base):
    level: t.Union[str, int] = "\N{SPORTS MEDAL}"
    trophy: t.Union[str, int] = "\N{TROPHY}"
    star: t.Union[str, int] = "\N{WHITE MEDIUM STAR}"
    chat: t.Union[str, int] = "\N{SPEECH BALLOON}"
    mic: t.Union[str, int] = "\N{STUDIO MICROPHONE}\N{VARIATION SELECTOR-16}"
    bulb: t.Union[str, int] = "\N{ELECTRIC LIGHT BULB}"
    money: t.Union[str, int] = "\N{MONEY BAG}"

    def get(self, name: str, bot: Red) -> t.Union[str, discord.Emoji, discord.PartialEmoji]:
        if not hasattr(self, name):
            raise AttributeError(f"Emoji {name} not found")
        emoji = getattr(self, name)
        if isinstance(emoji, str) and emoji.isdigit():
            emoji_obj = bot.get_emoji(int(emoji))
        elif isinstance(emoji, int):
            emoji_obj = bot.get_emoji(emoji)
        else:
            emoji_obj = emoji
        return emoji_obj or Emojis().dump(False)[name]


class GuildSettings(Base):
    users: t.Dict[int, Profile] = {}  # User_ID: Profile
    users_weekly: t.Dict[int, ProfileWeekly] = {}  # User_ID: ProfileWeekly
    weeklysettings: WeeklySettings = WeeklySettings()
    emojis: Emojis = Emojis()

    # Leveling
    enabled: bool = False  # Toggle leveling on/off
    algorithm: Algorithm = Algorithm()
    levelroles: t.Dict[int, int] = {}  # Level: Role_ID
    role_groups: t.Dict[int, float] = {}  # Role_ID: Exp
    use_embeds: bool = True  # Use Embeds instead of generated images for leveling
    showbal: bool = False  # Show economy balance
    autoremove: bool = False  # Remove previous role on level up

    # Messages
    xp: t.List[int] = [3, 6]  # Min/Max XP per message
    command_xp: bool = False  # Whether to give XP for using commands
    cooldown: int = 60  # Only gives XP every 60 seconds
    min_length: int = 0  # Minimum length of message to be considered eligible for XP gain

    # Voice
    voicexp: int = 2  # XP per minute in voice
    ignore_muted: bool = True  # Ignore XP while being muted in voice
    ignore_solo: bool = True  # Ignore XP while in a voice chat alone (Bots dont count)
    ignore_deafened: bool = True  # Ignore XP while deafened in a voice chat
    ignore_invisible: bool = True  # Ignore XP while status is invisible in voice chat

    # Bonuses
    streambonus: t.List[int] = []  # Bonus voice XP for streaming in voice Example: [2, 5]
    rolebonus: RoleBonus = RoleBonus()
    channelbonus: ChannelBonus = ChannelBonus()

    # Ignored
    ignoredchannels: t.List[int] = []  # Channels that dont gain XP
    ignoredroles: t.List[int] = []  # Roles that dont gain XP
    ignoredusers: t.List[int] = []  # Ignored users won't gain XP

    # Prestige
    prestigelevel: int = 0  # Level required to prestige, 0 is disabled
    prestigedata: t.Dict[int, Prestige] = {}  # Level: Prestige
    stackprestigeroles: bool = True  # Toggle whether to stack prestige roles

    # Alerts
    notify: bool = False  # Toggle whether to notify member of levelups if notify log channel is not set
    notifylog: int = 0  # Notify member of level up in a set channel
    notifydm: bool = False  # Notify member of level up in DMs
    notifymention: bool = False  # Mention the user when sending a level up message
    role_awarded_dm: str = ""  # Role awarded message in DM
    levelup_dm: str = ""  # Level up message in DM
    role_awarded_msg: str = ""  # Role awarded message in guild
    levelup_msg: str = ""  # Level up message in guild

    # Stars
    starcooldown: int = 3600  # Cooldown in seconds for users to give each other stars
    starmention: bool = False  # Mention when users add a star
    starmentionautodelete: int = 0  # Auto delete star mention reactions (0 to disable)

    def get_profile(self, user: t.Union[discord.Member, int]) -> Profile:
        uid = user if isinstance(user, int) else user.id
        return self.users.setdefault(uid, Profile())

    def get_weekly_profile(self, user: t.Union[discord.Member, int]) -> ProfileWeekly:
        uid = user if isinstance(user, int) else user.id
        return self.users_weekly.setdefault(uid, ProfileWeekly())


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    ignored_guilds: t.List[int] = []
    cache_seconds: int = 0
    render_gifs: bool = False
    force_embeds: bool = False  # Globally force embeds for leveling
    migrations: t.List[str] = []
    internal_api_port: int = 0  # If specified, starts internal api subprocess
    external_api_url: str = ""  # If specified, overrides internal api
    auto_cleanup: bool = False  # If True, will clean up configs of old guilds

    def get_conf(self, guild: t.Union[discord.Guild, int]) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())


def run_migrations(settings: dict[str, t.Any]) -> DB:
    """Sanitize old config data to be validated by the new schema"""
    root: dict = settings["117117117"]
    global_settings: dict = root["GLOBAL"]
    guild_settings: dict = root["GUILD"]

    data = {"configs": guild_settings, **global_settings}
    migrated = 0
    for conf in data["configs"].values():
        if not conf:
            continue
        # Migrate weekly settings
        if weekly := conf.get("weekly"):
            conf["users_weekly"] = weekly.get("users", {})
            conf["weeklysettings"] = weekly
        # Migrate prestige data
        if "prestigedata" in conf:
            for level, pdata in conf["prestigedata"].items():
                conf["prestigedata"][level] = {
                    "role": pdata["role"],
                    "emoji_string": pdata["emoji"]["str"],
                    "emoji_url": pdata["emoji"]["url"],
                }
        # Migrate profiles
        if "users" in conf:
            for profile in conf["users"].values():
                colors = profile.pop("colors", {})
                profile["namecolor"] = colors.get("name")
                profile["statcolor"] = colors.get("stat")
                profile["barcolor"] = colors.get("bar")

                if not profile["background"]:
                    profile["background"] = "default"

        conf["role_awarded_dm"] = conf.get("lvlup_dm_role", "") or ""
        conf["levelup_dm"] = conf.get("lvlup_dm", "") or ""
        conf["role_awarded_msg"] = conf.get("lvlup_msg_role", "") or ""
        conf["levelup_msg"] = conf.get("lvlup_msg", "") or ""
        if conf.get("nofifylog") is None:
            conf["notifylog"] = 0
        if conf.get("mention") is not None:
            conf["notifymention"] = conf["mention"]
        if conf.get("usepics") is not None:
            conf["use_embeds"] = not conf["usepics"]
        if conf.get("prestige") is not None:
            conf["prestigelevel"] = conf["prestige"]
        if conf.get("rolebonuses") is not None:
            conf["rolebonus"] = conf["rolebonuses"]
        if conf.get("channelbonuses") is not None:
            conf["channelbonus"] = conf["channelbonuses"]
        if conf.get("muted") is not None:
            conf["ignore_muted"] = conf["muted"]
        if conf.get("solo") is not None:
            conf["ignore_solo"] = conf["solo"]
        if conf.get("deafened") is not None:
            conf["ignore_deafened"] = conf["deafened"]
        if conf.get("invisible") is not None:
            conf["ignore_invisible"] = conf["invisible"]
        if conf.get("length") is not None:
            conf["min_length"] = conf["length"]
        migrated += 1

    log.warning(f"Migrated {migrated} guilds to new schema")
    db: DB = DB.load(data)
    return db
