import copy
import logging
import math
import random
from datetime import datetime, timedelta
from typing import List, Union

import discord
from aiocache import SimpleMemoryCache, cached
from aiohttp import ClientSession
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number
from tabulate import tabulate

DPY2 = True if discord.__version__ > "1.7.3" else False
_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.formatter")


# Get a level that would be achieved from the amount of XP
def get_level(xp: int, base: int, exp: int) -> int:
    return int((xp / base) ** (1 / exp))


# Get how much XP is needed to reach a level
def get_xp(level: int, base: int, exp: int) -> int:
    return math.ceil(base * (level**exp))


# Estimate how much time it would take to reach a certain level based on current algorithm
def time_to_level(
    level: int,
    base: int,
    exp: Union[int, float],
    cooldown: int,
    xp_range: list,
) -> int:
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
        rgb = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
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
    time_in_seconds = int(
        time_in_seconds
    )  # Some time differences get sent as a float so just handle it the dumb way
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


def get_leaderboard(
    ctx: commands.Context, conf: dict, stat: str, lbtype: str
) -> Union[List[discord.Embed], str]:
    conf = dict(copy.deepcopy(conf))
    if lbtype == "weekly":
        lb = conf["weekly"]["users"]
        title = _("Weekly ")
    else:
        lb = conf["users"]
        title = _("LevelUp ")

        prestige_req = conf["prestige"]
        for uid, data in lb.items():
            prestige = data["prestige"]
            if prestige:
                data["xp"] += prestige * get_xp(
                    prestige_req, conf["base"], conf["exp"]
                )

    if "v" in stat.lower():
        sorted_users = sorted(
            lb.items(), key=lambda x: x[1]["voice"], reverse=True
        )
        title += _("Voice Leaderboard")
        key = "voice"
        statname = _("Voicetime")
        col = "🎙️"
        total = time_formatter(sum(v["voice"] for v in lb.values()))
    elif "m" in stat.lower():
        sorted_users = sorted(
            lb.items(), key=lambda x: x[1]["messages"], reverse=True
        )
        title += _("Message Leaderboard")
        key = "messages"
        statname = _("Messages")
        col = "💬"
        total = humanize_number(round(sum(v["messages"] for v in lb.values())))
    elif "s" in stat.lower():
        sorted_users = sorted(
            lb.items(), key=lambda x: x[1]["stars"], reverse=True
        )
        title += _("Star Leaderboard")
        key = "stars"
        statname = _("Stars")
        col = "⭐"
        total = humanize_number(round(sum(v["stars"] for v in lb.values())))
    else:  # Exp
        sorted_users = sorted(
            lb.items(), key=lambda x: x[1]["xp"], reverse=True
        )
        title += _("Exp Leaderboard")
        key = "xp"
        statname = _("Exp")
        col = "💡"
        total = humanize_number(round(sum(v["xp"] for v in lb.values())))

    if lbtype == "weekly":
        w = conf["weekly"]
        desc = _("Total ") + f"{statname}: `{total}`\n"
        desc += _("Last Reset: ") + f"<t:{w['last_reset']}:d>\n"
        if w["autoreset"]:
            tl = get_next_reset(w["reset_day"], w["reset_hour"])
            desc += _("Next Reset: ") + f"<t:{tl}:d> (<t:{tl}:R>)\n"
    else:
        desc = _("Total") + f" {statname}: `{total}`\n"

    for i in sorted_users.copy():
        if not i[1][key]:
            sorted_users.remove(i)

    if not sorted_users:
        if lbtype == "weekly":
            txt = (
                _("There is no data for the weekly ")
                + statname.lower()
                + _(" leaderboard yet")
            )
        else:
            txt = (
                _("There is no data for the ")
                + statname.lower()
                + _(" leaderboard yet")
            )
        return txt

    you = ""
    for i in sorted_users:
        if i[0] == str(ctx.author.id):
            you = (
                _("You: ")
                + f"{sorted_users.index(i) + 1}/{len(sorted_users)}\n"
            )

    pages = math.ceil(len(sorted_users) / 10)
    start = 0
    stop = 10
    embeds = []
    for p in range(pages):
        if stop > len(sorted_users):
            stop = len(sorted_users)

        table = []
        for i in range(start, stop, 1):
            uid = sorted_users[i][0]
            user = ctx.guild.get_member(int(uid))
            user = user.name if user else uid
            data = sorted_users[i][1]

            place = i + 1
            if key == "voice":
                stat = time_formatter(data[key])
            else:
                v = data[key]
                if v > 999999999:
                    stat = f"{round(v / 1000000000, 1)}B"
                elif v > 999999:
                    stat = f"{round(v / 1000000, 1)}M"
                elif v > 9999:
                    stat = f"{round(v / 1000, 1)}K"
                else:
                    stat = str(round(v))

            if lbtype != "weekly" and key == "xp":
                table.append([place, str(data["level"]), stat, user])
            else:
                table.append([place, stat, user])

        headers = ["#", col, "Name"]
        if lbtype != "weekly" and key == "xp":
            headers = ["#", "🎖", col, "Name"]

        msg = tabulate(
            tabular_data=table,
            headers=headers,
            numalign="left",
            stralign="left",
        )
        embed = discord.Embed(
            title=title,
            description=desc + f"{box(msg, lang='python')}",
            color=discord.Color.random(),
        )
        if DPY2:
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
        else:
            embed.set_thumbnail(url=ctx.guild.icon_url)

        if you:
            embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages} ｜ {you}")
        else:
            embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages}")

        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


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
    sorted_users = sorted(
        leaderboard.items(), key=lambda x: x[1], reverse=True
    )
    for i in sorted_users:
        if i[0] == user_id:
            if total_xp:
                percent = round((user_xp / total_xp) * 100, 2)
            else:
                percent = 100
            pos = sorted_users.index(i) + 1
            pos_data = {"p": pos, "pr": percent}
            return pos_data
