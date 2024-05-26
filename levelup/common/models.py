import logging
import math
import typing as t
from datetime import datetime

import discord
from pydantic import Field

from . import Base

log = logging.getLogger("red.vrt.levelup.models")


class Profile(Base):
    xp: float = 0  # Experience points
    voice: float = 0  # Voice XP
    messages: int = 0  # Message count
    level: int = 0  # Level
    prestige: int = 0  # Prestige level
    stars: int = 0
    last_active: datetime = Field(
        default_factory=datetime.now,
        description="Last time the user was active in the guild (message sent or voice activity)",
    )

    # For image profiles
    format: int = 1  # 1 = Full, 2 = Slim
    background: str = "default"  # Can be default, random, filename, or URL
    namecolor: t.Union[str, None] = None  # Hex color
    statcolor: t.Union[str, None] = None  # Hex color
    barcolor: t.Union[str, None] = None  # Hex color
    font: t.Union[str, None] = None  # Font name (must match font file)
    blur: bool = True  # Blur background of stat area


class ProfileWeekly(Base):
    xp: float = 0
    voice: float = 0
    messages: int = 0
    stars: int = 0


class WeeklySettings(Base):
    on: bool = False  # Weekly stats are being tracked for this guild or not
    autoreset: bool = False  # Whether to auto reset once a week or require manual reset
    reset_hour: int = 0  # 0 - 23 hour (Server's system time)
    reset_day: int = 0  # 0 = sun, 1 = mon, 2 = tues, 3 = wed, 4 = thur, 5 = fri, 6 = sat
    last_reset: datetime = Field(default_factory=datetime.now)  # Timestamp of when weekly was last reset
    count: int = 3  # How many users to show in weekly winners
    channel: int = 0  # Announce the weekly winners (top 3 by default)
    role: int = 0  # Role awarded to top member(s) for that week
    role_all: bool = False  # If True, all winners get the role
    last_winners: t.List[int] = []  # IDs of last members that won if role_all is enabled
    remove: bool = True  # Whether to remove the role from the previous winner when a new one is announced
    bonus: int = 0  # Bonus exp to award the top X winners
    last_embed: t.Dict[str, t.Any] = {}  # Dict repr of last winner embed


class Prestige(Base):
    role: int
    emoji_string: str
    emoji_url: str


class RoleBonus(Base):
    msg: t.Dict[int, int] = {}  # Role_ID: Bonus
    voice: t.Dict[int, int] = {}  # Role_ID: Bonus


class ChannelBonus(Base):
    msg: t.Dict[int, t.List[int]] = {}  # Channel_ID: [Min, Max]
    voice: t.Dict[int, t.List[int]] = {}  # Channel_ID: [Min, Max]


class Algorithm(Base):
    base: int = 100  # Base denominator for level algorithm, higher takes longer to level
    exp: float = 2.0  # Exponent for level algorithm, higher is a more exponential/steeper curve

    def get_level(self, xp: int) -> int:
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


class GuildSettings(Base):
    users: t.Dict[int, Profile] = {}  # User_ID: Profile
    users_weekly: t.Dict[int, ProfileWeekly] = {}  # User_ID: ProfileWeekly
    weeklysettings: WeeklySettings = WeeklySettings()

    # Leveling
    algorithm: Algorithm = Algorithm()
    levelroles: t.Dict[int, int] = {}  # Level: Role_ID
    use_images: bool = False  # Use Pics instead of embeds for leveling, Embeds are default
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
    cache_seconds: int = 60
    render_gifs: bool = False
    migrations: t.List[str] = []

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
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
            if weekly.get("last_reset"):
                weekly["last_reset"] = datetime.fromtimestamp(weekly["last_reset"])
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
                profile["format"] = 1 if profile["full"] else 2
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
        migrated += 1

    log.warning(f"Migrated {migrated} guilds to new schema")
    return DB.load(data)
