import math
import typing as t
from datetime import datetime
from io import StringIO

import discord
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..common import utils
from ..common.models import DB, GuildSettings, Profile, ProfileWeekly, WeeklySettings

_ = Translator("LevelUp", __file__)


def get_user_position(
    guild: discord.Guild,
    conf: GuildSettings,
    lbtype: t.Literal["lb", "weekly"],
    target_user: int,
    key: str,
) -> dict:
    """Get the position of a user in the leaderboard

    Args:
        lb (t.Dict[int, t.Union[Profile, ProfileWeekly]]): The leaderboard
        target_user (int): The user's ID
        key (str): The key to sort by

    Returns:
        int: The user's position
    """
    if lbtype == "weekly":
        lb: t.Dict[int, ProfileWeekly] = conf.users_weekly
    elif not conf.prestigedata:
        lb: t.Dict[int, Profile] = conf.users
    else:
        lb: t.Dict[int, Profile] = {}
        for user_id in list(conf.users.keys()):
            profile = (
                conf.users[user_id].model_copy()
                if hasattr(conf.users[user_id], "model_copy")
                else conf.users[user_id].copy()
            )
            if profile.prestige and conf.prestigelevel:
                profile.xp += profile.prestige * conf.algorithm.get_xp(conf.prestigelevel)
                profile.level += profile.prestige * conf.prestigelevel
            lb[user_id] = profile

    valid_users = {k: v for k, v in lb.items() if guild.get_member(k)}
    sorted_users = sorted(valid_users.items(), key=lambda x: getattr(x[1], key), reverse=True)
    for idx, (uid, _) in enumerate(sorted_users):
        if uid == target_user:
            position = idx + 1
            break
    else:
        position = -1
    total = sum([getattr(x[1], key) for x in sorted_users])
    percent = getattr(lb[target_user], key) / total * 100 if total else 0
    return {"position": position, "total": total, "percent": percent}


def get_role_leaderboard(rolegroups: t.Dict[int, float], color: discord.Color) -> t.List[discord.Embed]:
    """Format and return the role leaderboard

    Args:
        rolegroups (t.Dict[int, float]): The role leaderboard

    Returns:
        t.List[discord.Embed]: A list of embeds
    """
    sorted_roles = sorted(rolegroups.items(), key=lambda x: x[1], reverse=True)
    filtered_roles = [x for x in sorted_roles if x[1] > 0]

    embeds = []
    count = len(filtered_roles)
    pages = math.ceil(count / 10)
    start = 0
    stop = 10
    for idx in range(pages):
        stop = min(count, stop)
        buffer = StringIO()
        for i, (role_id, xp) in enumerate(filtered_roles[start:stop], start=start):
            buffer.write(f"**{i + 1}.** <@&{role_id}> `{humanize_number(int(xp))}`xp\n")

        embed = discord.Embed(
            title=_("Role Leaderboard"),
            description=buffer.getvalue(),
            color=color,
        ).set_footer(text=_("Page {}").format(f"{idx + 1}/{pages}"))

        embeds.append(embed)
        start += 10
        stop += 10

    return embeds


def get_leaderboard(
    bot: Red,
    guild: discord.Guild,
    db: DB,
    stat: str,
    lbtype: str,
    is_global: bool,
    member: discord.Member = None,
    use_displayname: bool = True,
    dashboard: bool = False,
    color: discord.Color = discord.Color.random(),
    query: str = None,
) -> t.Union[t.List[discord.Embed], t.Dict[str, t.Any], str]:
    """Format and return the leaderboard

    Args:
        bot (Red)
        guild (discord.Guild)
        db (DB)
        stat (str): The stat to display (xp, messages, voice, stars)
        lbtype (str): The type of leaderboard (weekly, lb)
        is_global (bool): Whether to display global stats
        member (discord.Member, optional): Person running the command. Defaults to None.
        use_displayname (bool, optional): If false, uses username. Defaults to True.
        dashboard (bool, optional): True when called by the dashboard integration. Defaults to False.
        color (discord.Color, optional): Defaults to discord.Color.random().

    Returns:
        t.Union[t.List[discord.Embed], t.Dict[str, t.Any], str]: If called from dashboard returns a dict, else returns a list of embeds or a string
    """
    stat = stat.lower()
    color = member.color if member else color
    conf = db.get_conf(guild)
    lb: t.Dict[int, t.Union[Profile, ProfileWeekly]]
    weekly: WeeklySettings = None
    if lbtype == "weekly":
        title = _("Weekly ")
        lb = db.get_conf(guild).users_weekly
        weekly = db.get_conf(guild).weeklysettings
    elif lbtype == "lb" and is_global:
        title = _("Global LevelUp ")
        # Add up all the guilds
        lb: t.Dict[int, Profile] = {}
        for guild_id in db.configs.keys():
            guild_conf: GuildSettings = db.configs[guild_id]
            for user_id in guild_conf.users.keys():
                profile: Profile = guild_conf.users[user_id]
                if user_id not in lb:
                    lb[user_id] = profile.model_copy() if hasattr(profile, "model_copy") else profile.copy()
                else:
                    lb[user_id].xp += profile.xp
                    lb[user_id].messages += profile.messages
                    lb[user_id].voice += profile.voice
                    lb[user_id].stars += profile.stars

                if "xp" in stat and profile.prestige and guild_conf.prestigelevel:
                    lb[user_id].xp += profile.prestige * guild_conf.algorithm.get_xp(guild_conf.prestigelevel)
                    lb[user_id].level += profile.prestige * guild_conf.prestigelevel
    elif "xp" in stat and conf.prestigelevel and conf.prestigedata:
        title = _("LevelUp ")
        lb = {}
        for user_id in conf.users.keys():
            profile: Profile = conf.users[user_id]
            lb[user_id] = profile.model_copy() if hasattr(profile, "model_copy") else profile.copy()
            if profile.prestige:
                lb[user_id].xp += profile.prestige * conf.algorithm.get_xp(conf.prestigelevel)
                lb[user_id].level += profile.prestige * conf.prestigelevel
    else:
        title = _("LevelUp ")
        lb = db.get_conf(guild).users.copy()

    if "v" in stat:
        title += _("Voice Leaderboard")
        key = "voice"
        emoji = conf.emojis.get("mic", bot)
        statname = _("Voicetime")
    elif "m" in stat:
        title += _("Message Leaderboard")
        key = "messages"
        emoji = conf.emojis.get("chat", bot)
        statname = _("Messages")
    elif "s" in stat:
        title += _("Star Leaderboard")
        key = "stars"
        emoji = conf.emojis.get("star", bot)
        statname = _("Stars")
    else:
        title += _("Exp Leaderboard")
        key = "xp"
        emoji = conf.emojis.get("bulb", bot)
        statname = _("Experience")

    if is_global:
        valid_users: t.Dict[int, t.Union[Profile, ProfileWeekly]] = {k: v for k, v in lb.items() if bot.get_user(k)}
    else:
        valid_users: t.Dict[int, t.Union[Profile, ProfileWeekly]] = {k: v for k, v in lb.items() if guild.get_member(k)}

    filtered_users: t.Dict[int, t.Union[Profile, ProfileWeekly]] = {
        k: v for k, v in valid_users.items() if getattr(v, key) > 0
    }
    if not filtered_users and not dashboard:
        txt = _("There is no data for the {} leaderboard yet").format(
            _("weekly {}").format(statname) if lbtype == "weekly" else statname
        )
        return txt

    sorted_users = sorted(filtered_users.items(), key=lambda x: getattr(x[1], key), reverse=True)
    usercount = len(sorted_users)
    func = utils.humanize_delta if "v" in stat else humanize_number
    total: str = func(round(sum([getattr(x, key) for x in filtered_users.values()])))

    for idx, (user_id, stats) in enumerate(sorted_users):
        if member and user_id == member.id:
            you = _(" | You: {}").format(f"{idx + 1}/{len(sorted_users)}")
            break
    else:
        you = ""

    if lbtype == "weekly":
        if dashboard:
            desc = _("➣ Total {}: {}\n").format(statname, f"`{total}`{emoji}")
        else:
            desc = _("➣ **Total {}:** {}\n").format(statname, f"`{total}`{emoji}")
        if dashboard:
            if weekly.last_reset:
                ts = datetime.fromtimestamp(weekly.last_reset).strftime("%m/%d/%Y @ %I:%M:%S %p")
                desc += _("➣ Last Reset: {}\n").format(ts)
            if weekly.autoreset:
                ts = datetime.fromtimestamp(weekly.next_reset).strftime("%m/%d/%Y @ %I:%M:%S %p")
                delta = utils.humanize_delta(weekly.next_reset - int(datetime.now().timestamp()))
                desc += _("➣ Next Reset: {} ({})\n").format(ts, delta)
        else:
            if weekly.last_reset:
                ts = weekly.last_reset
                desc += _("➣ **Last Reset:** {}\n").format(f"<t:{ts}:d> (<t:{ts}:R>)")
            if weekly.autoreset:
                ts = weekly.next_reset
                desc += _("➣ **Next Reset:** {}\n").format(f"<t:{ts}:d> (<t:{ts}:R>)")

        desc += "\n"
    else:
        if dashboard:
            desc = _("Total {}: {}\n").format(statname, f"`{total}`{emoji}")
        else:
            desc = _("**Total {}:** {}\n\n").format(statname, f"`{total}`{emoji}")

    if dashboard:
        # Format for when dashboard integration calls this function
        payload = {
            "title": title,
            "description": desc.strip(),
            "stat": statname,
            "total": total,
            "type": lbtype,
            "user_position": you,
            "stats": [],
        }
        for idx, (user_id, stats) in enumerate(sorted_users):
            user_obj = bot.get_user(user_id) if is_global else guild.get_member(user_id)
            user = (user_obj.display_name if use_displayname else user_obj.name) if user_obj else user_id
            if query:
                if query.startswith("#"):
                    # User search by position
                    position_query = query[1:]
                    if idx + 1 != int(position_query):
                        continue
                elif query.isdigit():
                    # User search by ID or position
                    if user_id != int(query) and idx + 1 != int(query):
                        continue
                else:
                    # User search by name
                    if query.lower() not in str(user).lower():
                        continue
            place = idx + 1
            if key == "voice":
                stat = utils.humanize_delta(round(getattr(stats, key)))
            else:
                stat = utils.abbreviate_number(round(getattr(stats, key)))

                if key == "xp" and lbtype != "weekly" and not is_global:
                    stat += f" 🎖{stats.level}"

            entry = {"position": place, "name": user, "id": user_id, "stat": stat}
            payload["stats"].append(entry)
        return payload

    embeds = []
    pages = math.ceil(len(sorted_users) / 10)
    start = 0
    stop = 10
    for idx in range(pages):
        stop = min(usercount, stop)
        buffer = StringIO()
        for i in range(start, stop):
            user_id, stats = sorted_users[i]
            user_obj = bot.get_user(user_id) if is_global else guild.get_member(user_id)
            name = (user_obj.display_name if use_displayname else user_obj.name) if user_obj else user_id
            place = i + 1
            if key == "voice":
                stat = utils.humanize_delta(round(getattr(stats, key)))
            else:
                stat = utils.abbreviate_number(round(getattr(stats, key)))
                if key == "xp" and lbtype != "weekly" and not is_global:
                    stat += f" 🎖{stats.level}"

            buffer.write(f"**{place}**. {name} (`{stat}`)\n")

        embed = discord.Embed(
            title=title,
            description=desc + buffer.getvalue(),
            color=color,
        ).set_footer(text=_("Page {}").format(f"{idx + 1}/{pages}{you}"), icon_url=guild.icon)

        embeds.append(embed)
        start += 10
        stop += 10

    return embeds
