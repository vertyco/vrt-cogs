from __future__ import annotations

import logging
import math
import os
import typing as t
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import discord
import orjson
from pydantic import VERSION, BaseModel, Field
from redbot.core.bot import Red

from .utils import get_twemoji

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
            text = path.read_text()
            try:
                return cls.model_validate_json(text)
            except UnicodeDecodeError as e:
                log.warning(f"Failed to load {path}, attempting to load via json5")
                try:
                    import json5

                    data = json5.loads(text)
                    return cls.model_validate(data)
                except ImportError:
                    log.error("Failed to load via json5")
                    raise e
        try:
            return cls.parse_file(path)
        except UnicodeDecodeError as e:
            log.warning(f"Failed to load {path}, attempting to load via json5")
            try:
                import json5

                data = json5.loads(path.read_text())
                return cls.parse_obj(data)
            except ImportError:
                log.error("Failed to load via json5")
                raise e

    def to_file(self, path: Path, pretty: bool = False) -> None:
        dump = self.dumpjson(exclude_defaults=True, pretty=pretty)
        # We want to write the file as safely as possible
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/_drivers/json.py#L224
        tmp_file = f"{path.stem}-{uuid4().fields[0]}.tmp"
        tmp_path = path.parent / tmp_file
        with tmp_path.open(encoding="utf-8", mode="w") as fs:
            fs.write(dump)
            fs.flush()  # This does get closed on context exit, ...
            os.fsync(fs.fileno())  # but that needs to happen prior to this line

        # Replace the original file with the new content
        tmp_path.replace(path)

        # Ensure directory fsync for better durability
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


class VoiceTracking(Base):
    """Non-config model for tracking voice activity"""

    joined: float  # Time when user joined VC
    not_gaining_xp: bool  # If the user currently shouldnt gain xp (if solo or deafened is ignored ect..)
    not_gaining_xp_time: float  # Total time user wasnt gaining xp
    stopped_gaining_xp_at: t.Union[float, None]  # Time when user last stopped gaining xp


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
    show_tutorial: bool = True  # Init with True, show tutorial on first command usage

    # Profile customization
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

    def all_default(self) -> bool:
        # Check if all settings under the Profile customization section are default
        checks = [
            self.style == "default",
            self.background == "default",
            self.namecolor is None,
            self.statcolor is None,
            self.barcolor is None,
            self.font is None,
            self.blur,
            not self.show_displayname,
        ]
        return all(checks)


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
    reset_day: int = 0  # 0 = mon, 1 = tues, 2 = wed, 3 = thur, 4 = fri, 5 = sat, 6 = sun
    last_reset: int = 0  # Timestamp of when weekly was last reset
    count: int = 3  # How many users to show in weekly winners
    channel: int = 0  # Announce the weekly winners (top 3 by default)
    role: int = 0  # Role awarded to top member(s) for that week
    role_all: bool = False  # If True, all winners get the role instead of only 1st place
    last_winners: t.List[int] = []  # IDs of last members that won if role_all is enabled
    remove: bool = True  # Whether to remove the role from the previous winner when a new one is announced
    bonus: int = 0  # Bonus exp to award the top X winners
    last_embed: t.Dict[str, t.Any] = {}  # Dict repr of last winner embed
    ping_winners: bool = False  # Mention the winners in the announcement

    @property
    def next_reset(self) -> int:
        now = datetime.now()
        current_weekday = now.weekday()

        # Calculate how many days until the next reset day
        days_until_reset: int = (self.reset_day - current_weekday + 7) % 7

        if days_until_reset == 0 and now.hour >= self.reset_hour:
            days_until_reset = 7

        next_reset_time = (now + timedelta(days=days_until_reset)).replace(
            hour=self.reset_hour, minute=0, second=0, microsecond=0
        )

        return int(next_reset_time.timestamp())

    def refresh(self):
        self.last_reset = int(datetime.now().timestamp())


class Prestige(Base):
    role: int
    emoji_string: str
    emoji_url: t.Union[str, None] = None


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
        final = emoji_obj or Emojis().dump(False)[name]
        if isinstance(final, str) and len(final) > 50:
            log.error(f"Something is wrong with the emoji {name}: {final}")
            final = Emojis().dump(False)[name]
            setattr(self, name, final if isinstance(final, str) else final.id)
        return final


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
    style_override: t.Union[str, None] = None  # Override the profile style for this guild

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

    # Allowed
    allowedchannels: t.List[int] = []  # Only channels that gain XP if not empty
    allowedroles: t.List[int] = []  # Only roles that gain XP if not empty

    # Ignored
    ignoredchannels: t.List[int] = []  # Channels that dont gain XP
    ignoredroles: t.List[int] = []  # Roles that dont gain XP
    ignoredusers: t.List[int] = []  # Ignored users won't gain XP

    # Prestige
    prestigelevel: int = 0  # Level required to prestige, 0 is disabled
    prestigedata: t.Dict[int, Prestige] = {}  # Level: Prestige
    stackprestigeroles: bool = True  # Toggle whether to stack prestige roles
    keep_level_roles: bool = False  # Keep level roles after prestiging

    # Alerts
    notify: bool = False  # Toggle whether to notify member of levelups if notify log channel is not set
    notifylog: int = 0  # Notify member of level up in a set channel
    notifydm: bool = False  # Notify member of level up in DMs
    notifymention: bool = False  # Mention the user when sending a level up message
    role_awarded_dm: str = ""  # Role awarded message in DM
    levelup_dm: str = ""  # Level up message in DM
    role_awarded_msg: t.Optional[str] = ""  # Role awarded message in guild
    levelup_msg: t.Optional[str] = ""  # Level up message in guild

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
    configs: t.Dict[int, GuildSettings] = {}
    ignored_guilds: t.List[int] = []
    cache_seconds: int = 0  # How long generated profile images should be cached, 0 to disable
    render_gifs: bool = False  # Whether to render profiles as gifs
    force_embeds: bool = False  # Globally force embeds for leveling
    internal_api_port: int = 0  # If specified, starts internal api subprocess
    external_api_url: str = ""  # If specified, overrides internal api
    auto_cleanup: bool = False  # If True, will clean up configs of old guilds
    ignore_bots: bool = True  # Ignore bots completely

    def get_conf(self, guild: t.Union[discord.Guild, int]) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())


def run_migrations(settings: t.Dict[str, t.Any]) -> DB:
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
                emoji = pdata["emoji"]["str"]
                emoji_url = pdata["emoji"]["url"]
                if isinstance(emoji, str) and emoji_url is None:
                    with suppress(TypeError, ValueError):
                        emoji_url = get_twemoji(emoji)
                conf["prestigedata"][level] = {
                    "role": pdata["role"],
                    "emoji_string": emoji,
                    "emoji_url": emoji_url,
                }
        # Migrate profiles
        if "users" in conf:
            for profile in conf["users"].values():
                colors = profile.pop("colors", {})
                profile["namecolor"] = colors.get("name")
                profile["statcolor"] = colors.get("stat")
                profile["barcolor"] = colors.get("bar")

                if not profile.get("background"):
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
        conf["algorithm"] = {
            "base": conf.get("base", 100),
            "exp": conf.get("exp", 2.0),
        }

        migrated += 1

    log.warning(f"Migrated {migrated} guilds to new schema")
    db: DB = DB.load(data)
    return db
