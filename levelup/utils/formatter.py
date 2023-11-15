import logging
import math
import random
from datetime import datetime, timedelta
from io import StringIO
from typing import List, Union

import discord
from aiocache import cached
from aiohttp import ClientSession
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

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
        xp = random.choice(range(xp_range[0], xp_range[1] + 1))
        xp_obtained += xp

        if random.random() < 0.5:
            # Wait up to an hour after cooldown for a little more realism
            wait = cooldown + random.randint(30, 3600)
        else:
            wait = cooldown + random.randint(5, 300)

        time_to_reach_level += wait
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
    fill = "▰"
    space = "▱"
    if perc is not None:
        ratio = perc / 100
    else:
        ratio = progress / total
    bar = fill * round(ratio * width) + space * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds) -> str:
    # Some time differences get sent as a float so just handle it the dumb way
    time_in_seconds = int(time_in_seconds)
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


def get_twemoji(emoji: str):
    # Thanks Fixator!
    emoji_unicode = []
    for char in emoji:
        char = hex(ord(char))[2:]
        emoji_unicode.append(char)
    if "200d" not in emoji_unicode:
        emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
    emoji_unicode = "-".join(emoji_unicode)
    return f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_unicode}.png"


def get_next_reset(weekday: int, hour: int):
    now = datetime.utcnow()
    reset = now + timedelta((weekday - now.weekday()) % 7)
    return int(reset.replace(hour=hour, minute=0, second=0).timestamp())


def get_attachments(ctx) -> List[discord.Attachment]:
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
    ctx: commands.Context,
    settings: dict,
    stat: str,
    lbtype: str,
    is_global: bool,
) -> Union[List[discord.Embed], str]:
    if lbtype == "weekly":
        lb = settings["weekly"]["users"]
        title = _("Global Weekly ") if is_global else _("Weekly ")
    else:
        lb = settings["users"]
        title = _("Global LevelUp ") if is_global else _("LevelUp ")

        if "xp" in stat.lower():
            lb = {uid: data.copy() for uid, data in settings["users"].items()}
            if prestige_req := settings.get("prestige"):
                # If this isnt pulled its global lb
                for uid, data in lb.items():
                    if prestige := data["prestige"]:
                        data["xp"] += prestige * get_xp(prestige_req, settings["base"], settings["exp"])

    if "v" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["voice"], reverse=True)
        title += _("Voice Leaderboard")
        key = "voice"
        col = "🎙️"
        statname = _("Voicetime")
        total = time_formatter(sum(v["voice"] for v in lb.values()))
    elif "m" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["messages"], reverse=True)
        title += _("Message Leaderboard")
        key = "messages"
        col = "💬"
        statname = _("Messages")
        total = humanize_number(round(sum(v["messages"] for v in lb.values())))
    elif "s" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["stars"], reverse=True)
        title += _("Star Leaderboard")
        key = "stars"
        col = "⭐"
        statname = _("Stars")
        total = humanize_number(round(sum(v["stars"] for v in lb.values())))
    else:  # Exp
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["xp"], reverse=True)
        title += _("Exp Leaderboard")
        key = "xp"
        col = "💡"
        statname = _("Exp")
        total = humanize_number(round(sum(v["xp"] for v in lb.values())))

    if lbtype == "weekly":
        w = settings["weekly"]
        desc = _("Total ") + f"{statname}: `{total}`{col}\n"
        if last_reset := w.get("last_reset"):
            # If not global
            desc += _("Last Reset: ") + f"<t:{last_reset}:d>\n"
            if w["autoreset"]:
                tl = get_next_reset(w["reset_day"], w["reset_hour"])
                desc += _("Next Reset: ") + f"<t:{tl}:d> (<t:{tl}:R>)\n"
    else:
        desc = _("Total") + f" {statname}: `{total}`{col}\n"

    for i in sorted_users.copy():
        if not i[1][key]:
            sorted_users.remove(i)

    if not sorted_users:
        if lbtype == "weekly":
            txt = _("There is no data for the weekly ") + statname.lower() + _(" leaderboard yet")
        else:
            txt = _("There is no data for the ") + statname.lower() + _(" leaderboard yet")
        return txt

    you = ""
    for i in sorted_users:
        if i[0] == str(ctx.author.id):
            you = _("You: ") + f"{sorted_users.index(i) + 1}/{len(sorted_users)}\n"

    pages = math.ceil(len(sorted_users) / 10)
    start = 0
    stop = 10
    embeds = []
    for p in range(pages):
        if stop > len(sorted_users):
            stop = len(sorted_users)

        buf = StringIO()
        for i in range(start, stop, 1):
            uid = sorted_users[i][0]
            user_obj = ctx.guild.get_member(int(uid)) or ctx.bot.get_user(int(uid))
            user = user_obj.name if user_obj else uid
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

                if key == "xp" and lbtype != "weekly":
                    if lvl := data.get("level"):
                        stat += f" 🎖{lvl}"

            buf.write(f"{place}. {user} ({stat})\n")

        embed = discord.Embed(
            title=title,
            description=desc + box(buf.getvalue(), lang="python"),
            color=discord.Color.random(),
        )
        if DPY2:
            icon = ctx.guild.icon
        else:
            icon = ctx.guild.icon_url

        if you:
            embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages} | {you}", icon_url=icon)
        else:
            embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages}", icon_url=icon)

        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


@cached(ttl=3600)
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
