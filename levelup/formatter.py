import typing
import math
import discord
from redbot.core.utils.chat_formatting import box


# Get level from XP
def get_level(xp: int, base: int, exp: typing.Union[int, float]) -> int:
    return int((xp / base) ** (1 / exp))


# Get XP from level
def get_xp(level: int, base: int, exp: typing.Union[int, float]) -> int:
    return math.ceil(base * (level ** exp))


def hex_to_rgb(color: str):
    color = color.strip("#")
    rgb = tuple(int(color[i: i + 2], 16) for i in (0, 2, 4))
    return rgb


async def get_user_position(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    prestige_req = conf["prestige"]
    leaderboard = {}
    total_xp = 0
    user_xp = 0
    for user, data in conf["users"].items():
        xp = int(data["xp"])
        prestige = data["prestige"]
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
            percent = round((user_xp / total_xp) * 100, 2)
            pos = sorted_users.index(i) + 1
            pos_data = {"p": pos, "pr": percent}
            return pos_data


async def get_user_stats(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    users = conf["users"]
    user = users[user_id]
    xp = int(user["xp"])
    messages = user["messages"]
    voice = user["voice"]
    voice = int(voice / 60)
    level = user["level"]
    prestige = user["prestige"]
    emoji = user["emoji"]
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
        "pr": prestige
    }
    return stats


async def profile_embed(
        user,
        position,
        percentage,
        level,
        messages,
        voice,
        progress,
        lvlbar,
        lvlpercent,
        emoji,
        prestige
) -> discord.Embed:
    msg = f"🎖｜Level {level}\n"
    if prestige:
        msg += f"🏆｜Prestige {prestige} {emoji}\n"
    msg += f"💬｜{messages} messages sent\n" \
           f"🎙｜{voice} minutes in voice\n" \
           f"💡｜{progress} XP"
    embed = discord.Embed(
        title=f"{user.name}'s Profile",
        description=msg,
        color=user.colour
    )
    embed.add_field(name="Progress", value=box(f"{lvlbar} {lvlpercent} %", lang="python"))
    embed.set_thumbnail(url=user.avatar_url)
    if position:
        embed.set_footer(text=f"Rank: {position} with {percentage}% of global server XP")
    return embed

