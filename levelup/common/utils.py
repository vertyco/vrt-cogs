import asyncio
import json
import logging
import math
import random
import re
import sys
import typing as t
from datetime import datetime, timedelta
from io import StringIO

import aiohttp
import discord
import plotly.graph_objects as go
from aiocache import cached
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.predicates import MessagePredicate
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .const import COLORS

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.formatter")


IMAGE_LINKS: t.Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?P<extension>png|jpg|jpeg|gif)"
    r"(?P<extras>\?(?:ex=(?P<expires>\w+)&)(?:is=(?P<issued>\w+)&)(?:hm=(?P<token>\w+)&))?)",  # Discord CDN info
    flags=re.I,
)
TENOR_REGEX: t.Pattern[str] = re.compile(r"https:\/\/tenor\.com\/view\/(?P<image_slug>[a-zA-Z0-9-]+-(?P<image_id>\d+))")
EMOJI_REGEX: t.Pattern = re.compile(r"(<(?P<animated>a)?:[a-zA-Z0-9\_]+:([0-9]+)>)")
MENTION_REGEX: t.Pattern = re.compile(r"<@!?([0-9]+)>")
ID_REGEX: t.Pattern = re.compile(r"[0-9]{17,}")

VALID_CONTENT_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/gif")


def string_to_rgb(color: str, as_discord_color: bool = False) -> t.Union[t.Tuple[int, int, int], discord.Color]:
    if not color:
        # Return white
        if as_discord_color:
            return discord.Color.from_rgb(255, 255, 255)
        return 255, 255, 255
    if color.isdigit():
        color = int(color)
        r = color & 255
        g = (color >> 8) & 255
        b = (color >> 16) & 255
        if as_discord_color:
            return discord.Color.from_rgb(r, g, b)
        return r, g, b
    elif color in COLORS:
        color = COLORS[color]
    color = color.strip("#")
    r = int(color[:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:], 16)
    if as_discord_color:
        return discord.Color.from_rgb(r, g, b)
    return r, g, b


def get_bar(progress, total, perc=None, width: int = 15) -> str:
    fill = "▰"
    space = "▱"
    if perc is not None:
        ratio = perc / 100
    else:
        ratio = progress / total
    bar = fill * round(ratio * width) + space * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


# Format time from total seconds and format into readable string
def humanize_delta(delta: t.Union[int, timedelta]) -> str:
    """Format time in seconds into a human readable string"""
    # Some time differences get sent as a float so just handle it the dumb way
    time_in_seconds = delta.total_seconds() if isinstance(delta, timedelta) else int(delta)
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


def get_twemoji(emoji: str) -> str:
    """Fetch the url of unicode emojis from Twemoji CDN"""
    emoji_unicode = []
    for char in emoji:
        char = hex(ord(char))[2:]
        emoji_unicode.append(char)
    if "200d" not in emoji_unicode:
        emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
    emoji_unicode = "-".join(emoji_unicode)
    return f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{emoji_unicode}.png"


def get_next_reset(weekday: int, hour: int):
    now = datetime.now()
    reset = now + timedelta((weekday - now.weekday()) % 7)
    return int(reset.replace(hour=hour, minute=0, second=0).timestamp())


def get_attachments(ctx: commands.Context) -> t.List[discord.Attachment]:
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


def deep_getsizeof(obj: t.Any, seen: t.Optional[set] = None) -> int:
    """Recursively finds the size of an object in memory"""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return 0
    # Mark object as seen
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        # If the object is a dictionary, recursively add the size of keys and values
        size += sum([deep_getsizeof(k, seen) + deep_getsizeof(v, seen) for k, v in obj.items()])
    elif hasattr(obj, "__dict__"):
        # If the object has a __dict__, it's likely an object. Find size of its dictionary
        size += deep_getsizeof(obj.__dict__, seen)
    elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
        # If the object is an iterable (not a string or bytes), iterate through its items
        size += sum([deep_getsizeof(i, seen) for i in obj])
    elif hasattr(obj, "model_dump"):
        # If the object is a pydantic model, get the size of its dictionary
        size += deep_getsizeof(obj.model_dump(), seen)
    elif hasattr(obj, "dict"):
        # If the object is a pydantic model, get the size of its dictionary
        size += deep_getsizeof(obj.dict(), seen)
    return size


def humanize_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1024.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1024.0
    return "{0:.1f}{1}".format(num, "YB")


def abbreviate_number(num: int) -> str:
    if num < 1000:
        return str(num)
    for unit in ["", "K", "M", "B", "T", "Q"]:
        if abs(num) < 1000.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1000.0
    return "{0:.1f}{1}".format(num, "E")


def get_day_name(day: int) -> str:
    daymap = {
        0: _("Monday"),
        1: _("Tuesday"),
        2: _("Wednesday"),
        3: _("Thursday"),
        4: _("Friday"),
        5: _("Saturday"),
        6: _("Sunday"),
    }
    return daymap[day]


@cached(ttl=60 * 60 * 24)  # 24 hours
async def get_content_from_url(url: str) -> t.Union[bytes, None]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status == 404:
                return None
            return await resp.content.read()


async def confirm_msg(ctx: t.Union[commands.Context, discord.Interaction]) -> t.Union[bool, None]:
    """Wait for user to respond yes or no"""
    if isinstance(ctx, discord.Interaction):
        pred = MessagePredicate.yes_or_no(channel=ctx.channel, user=ctx.user)
        bot = ctx.client
    else:
        pred = MessagePredicate.yes_or_no(ctx)
        bot = ctx.bot
    try:
        await bot.wait_for("message", check=pred, timeout=30)
    except asyncio.TimeoutError:
        return None
    else:
        return pred.result


@retry(
    retry=retry_if_exception_type(json.JSONDecodeError),
    wait=wait_random_exponential(min=120, max=600),
    stop=stop_after_attempt(6),
    reraise=True,
)
async def fetch_amari_payload(guild_id: int, page: int, key: str):
    url = f"https://amaribot.com/api/v1/guild/leaderboard/{guild_id}?page={page}&limit=1000"
    headers = {"Accept": "application/json", "Authorization": key, "User-Agent": "Mozilla/5.0"}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as res:
            status = res.status
            if status == 429:
                log.warning("amari import is being rate limited!")
            data = await res.json(content_type=None)
            return data, status


@retry(
    retry=retry_if_exception_type(json.JSONDecodeError),
    wait=wait_random_exponential(min=120, max=600),
    stop=stop_after_attempt(6),
    reraise=True,
)
async def fetch_polaris_payload(guild_id: int, page: int):
    url = f"https://gdcolon.com/polaris/api/leaderboard/{guild_id}?page={page}"
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}) as res:
            status = res.status
            if status == 429:
                log.warning("polaris import is being rate limited!")
            data = await res.json(content_type=None)
            return data, status


@retry(
    retry=retry_if_exception_type(json.JSONDecodeError),
    wait=wait_random_exponential(min=120, max=600),
    stop=stop_after_attempt(6),
    reraise=True,
)
async def fetch_mee6_payload(guild_id: int, page: int):
    url = f"https://mee6.xyz/api/plugins/levels/leaderboard/{guild_id}?page={page}&limit=1000"
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}) as res:
            status = res.status
            if status == 429:
                log.warning("mee6 import is being rate limited!")
            data = await res.json(content_type=None)
            return data, status


def get_level(xp: int, base: int, exp: int) -> int:
    """Get a level that would be achieved from the amount of XP"""
    return int((xp / base) ** (1 / exp))


def get_xp(level: int, base: int, exp: int) -> int:
    """Get how much XP is needed to reach a level"""
    return math.ceil(base * (level**exp))


# Estimate how much time it would take to reach a certain level based on current algorithm
def time_to_level(
    xp_needed: int,
    xp_range: list,
    cooldown: int,
) -> int:
    xp_obtained = 0
    time_to_reach_level = 0  # Seconds
    while xp_obtained < xp_needed:
        xp_obtained += random.randint(xp_range[0], xp_range[1] + 1)
        mod = (60, 7200) if random.random() < 0.20 else (0, 60)
        wait = cooldown + random.randint(*mod)
        time_to_reach_level += wait
    return time_to_reach_level


def plot_levels(
    base: int, exponent: float, cooldown: int, xp_range: t.Tuple[int, int]
) -> t.Tuple[str, t.Optional[bytes]]:
    buffer = StringIO()
    x, y = [], []
    for level in range(1, 21):
        xp_required = get_xp(level, base, exponent)
        seconds_required = time_to_level(xp_required, xp_range, cooldown)
        time = humanize_delta(seconds_required)
        buffer.write(_("• lvl {}, {} xp, {}\n").format(level, xp_required, time))
        x.append(level)
        y.append(xp_required)
    try:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Total"))
        fig.update_layout(
            title={
                "text": _("XP Curve"),
                "x": 0.5,  # Set the x position to center
                "y": 0.95,  # Set the y position to top
                "xanchor": "center",  # Set the x anchor to center
                "yanchor": "top",  # Set the y anchor to top
            },
            xaxis_title=_("Level"),
            yaxis_title=_("Experience Required"),
            autosize=False,
            width=500,
            height=500,
            margin=dict(l=50, r=50, b=100, t=100, pad=4),
            plot_bgcolor="black",  # Set the background color to black
            paper_bgcolor="black",  # Set the paper color to black
            font=dict(color="white"),  # Set the font color to white
        )
        img_bytes = fig.to_image(format="PNG")
        return buffer.getvalue(), img_bytes
    except Exception as e:
        log.error("Failed to plot levels", exc_info=e)
        return buffer.getvalue(), None
