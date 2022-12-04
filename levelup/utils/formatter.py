import logging
import math
import random
from datetime import datetime, timedelta
from typing import Union

import discord
from aiocache import cached, SimpleMemoryCache
from aiohttp import ClientSession
from redbot.core.i18n import Translator

DPY2 = True if discord.__version__ > "1.7.3" else False
_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.formatter")


# Get a level that would be achieved from the amount of XP
def get_level(xp: int, base: int, exp: int) -> int:
    return int((xp / base) ** (1 / exp))


# Get how much XP is needed to reach a level
def get_xp(level: int, base: int, exp: int) -> int:
    return math.ceil(base * (level ** exp))


# Estimate how much time it would take to reach a certain level based on curent algorithm
def time_to_level(level: int, base: int, exp: Union[int, float], cooldown: int, xp_range: list) -> int:
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


def get_bar(progress, total, perc=None, width: int = 20) -> str:
    if perc is not None:
        ratio = perc / 100
    else:
        ratio = progress / total
    bar = "█" * round(ratio * width) + "-" * round(width - (ratio * width))
    return f"|{bar}| {round(100 * ratio, 1)}%"


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
            tstring = str(seconds) + _(" second")
        else:
            tstring = str(seconds) + _(" seconds")
    elif not any([hours, days, years]):
        if minutes == 1:
            tstring = str(minutes) + _(" minute")
        else:
            tstring = str(minutes) + _(" minutes")
    elif hours and not days and not years:
        tstring = f"{hours}h {minutes}m"
    elif days and not years:
        tstring = f"{days}d {hours}h {minutes}m"
    else:
        tstring = f"{years}y {days}d {hours}h {minutes}m"
    return tstring


def get_next_reset(weekday: int, hour: int):
    now = datetime.utcnow()
    reset = now + timedelta((weekday - now.weekday()) % 7)
    return int(reset.replace(hour=hour, minute=0, second=0).timestamp())


def get_attachments(ctx) -> list:
    """Get all attachments from context"""
    content = []
    if ctx.message.attachments:
        atchmts = [a for a in ctx.message.attachments]
        content.extend(atchmts)
    if hasattr(ctx.message, "reference"):
        try:
            atchmts = [a for a in ctx.message.reference.resolved.attachments]
            content.extend(atchmts)
        except AttributeError:
            pass
    return content


@cached(ttl=3600, cache=SimpleMemoryCache)
async def get_content_from_url(url: str):
    try:
        async with ClientSession() as session:
            async with session.get(url) as resp:
                file = await resp.content.read()
                return file
    except Exception as e:
        log.error(f"Could not get file content from url: {e}", exc_info=True)
        return None


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
