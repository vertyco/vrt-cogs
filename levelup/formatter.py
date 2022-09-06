import math
import random
import typing

import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

if discord.__version__ > "1.7.3":
    DPY2 = True
else:
    DPY2 = False

_ = Translator("LevelUp", __file__)


# Get a level that would be achieved from the amount of XP
def get_level(xp: int, base: int, exp: int) -> int:
    return int((xp / base) ** (1 / exp))


# Get how much XP is needed to reach a level
def get_xp(level: int, base: int, exp: int) -> int:
    return math.ceil(base * (level ** exp))


# Estimate how much time it would take to reach a certain level based on curent algorithm
def time_to_level(level: int, base: int, exp: typing.Union[int, float], cooldown: int, xp_range: list) -> int:
    xp_needed = get_xp(level, base, exp)
    xp_obtained = 0
    time_to_reach_level = 0  # Seconds
    while True:
        xp = random.choice(range(xp_range[0], xp_range[1]))
        xp_obtained += xp
        time_to_reach_level += cooldown
        if xp_obtained >= xp_needed:
            return time_to_reach_level


# Convert a hex color to an RGB tuple
def hex_to_rgb(color: str) -> tuple:
    if color.isdigit():
        rgb = int_to_rgb(int(color))
    else:
        color = color.strip("#")
        rgb = tuple(int(color[i: i + 2], 16) for i in (0, 2, 4))
    return rgb


def int_to_rgb(color: int) -> tuple:
    r = color & 255
    g = (color >> 8) & 255
    b = (color >> 16) & 255
    rgb = (r, g, b)
    return rgb


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds) -> str:
    time_in_seconds = int(time_in_seconds)  # Some time differences get sent as a float so just handle it the dumb way
    minutes, seconds = divmod(time_in_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    if not any([seconds, minutes, hours, days, years]):
        tstring = _("None")
    elif not any([minutes, hours, days, years]):
        if seconds == 1:
            tstring = _(f"{seconds} second")
        else:
            tstring = _(f"{seconds} seconds")
    elif not any([hours, days, years]):
        if minutes == 1:
            tstring = _(f"{minutes} minute")
        else:
            tstring = _(f"{minutes} minutes")
    elif hours and not days and not years:
        tstring = f"{hours}h {minutes}m"
    elif days and not years:
        tstring = f"{days}d {hours}h {minutes}m"
    else:
        tstring = f"{years}y {days}d {hours}h {minutes}m"
    return tstring


async def get_user_position(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    prestige_req = conf["prestige"]
    leaderboard = {}
    total_xp = 0
    user_xp = 0
    for user, data in conf["users"].items():
        xp = int(data["xp"])
        prestige = int(data["prestige"])
        if prestige:
            add_xp = get_xp(prestige_req, base, exp)
            xp = int(xp + (prestige * add_xp))
        leaderboard[user] = xp
        total_xp += xp
        if user == user_id:
            user_xp = xp
    sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    for i in sorted_users:
        if i[0] == user_id:
            if total_xp:
                percent = round((user_xp / total_xp) * 100, 2)
            else:
                percent = 100
            pos = sorted_users.index(i) + 1
            pos_data = {"p": pos, "pr": percent}
            return pos_data


async def get_user_stats(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    users = conf["users"]
    user = users[user_id]
    xp = int(user["xp"])  # XP is float in config
    messages = user["messages"]
    voice = user["voice"]
    voice = time_formatter(voice)
    level = user["level"]
    prestige = user["prestige"]
    emoji = user["emoji"]
    if "stars" in user:
        stars = user["stars"]
    else:
        stars = 0
    if "background" in user:
        bg = user["background"]
    else:
        bg = None
    next_level = level + 1
    xp_needed = get_xp(next_level, base, exp)
    ratio = xp / xp_needed
    lvlpercent = int(ratio * 100)
    blocks = int(30 * ratio)
    blanks = int(30 - blocks)
    lvlbar = "〘"
    for _ in range(blocks):
        lvlbar += "█"
    for _ in range(blanks):
        lvlbar += "-"
    lvlbar += "〙"
    stats = {
        "l": level,
        "m": messages,
        "v": voice,
        "xp": xp,
        "goal": xp_needed,
        "lb": lvlbar,
        "lp": lvlpercent,
        "e": emoji,
        "pr": prestige,
        "stars": stars,
        "bg": bg
    }
    return stats


async def profile_embed(
        user: discord.Member,
        position: str,
        percentage: float,
        level: int,
        messages: str,
        voice: str,
        progress: str,
        lvlbar: str,
        lvlpercent: int,
        emoji: str,
        prestige: int,
        stars: str
) -> discord.Embed:
    msg = f"🎖｜Level {level}\n"
    if prestige:
        msg += f"🏆｜Prestige {prestige} {emoji}\n"
    msg += f"⭐｜{stars} stars\n" \
           f"💬｜{messages} messages sent\n" \
           f"🎙｜{voice} in voice\n" \
           f"💡｜{progress} XP"
    embed = discord.Embed(
        title=f"{user.name}'s {_('Profile')}",
        description=_(msg),
        color=user.colour
    )
    embed.add_field(name=_("Progress"), value=box(f"{lvlbar} {lvlpercent} %", lang="python"))
    if DPY2:
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
    else:
        embed.set_thumbnail(url=user.avatar_url)
    if position:
        embed.set_footer(text=_(f"Rank {position}, with {percentage}% of global server XP"))
    return embed
