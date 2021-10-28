import math
import discord
import re
import datetime
import pytz
import io

from redbot.core import commands

from redbot.core.utils.chat_formatting import box, pagify
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator


# Format time from total seconds
def time_format(time_played: int):
    minutes, _ = divmod(time_played, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return days, hours, minutes


# Microsoft's timestamp end digits are fucked up and random so we iteratively try fixing them by stripping digits
def fix_timestamp(time: str):
    try:
        time = datetime.datetime.fromisoformat(time)
    except ValueError:
        stripping_that_shit = True
        strip = -1
        while stripping_that_shit:
            try:
                time = datetime.datetime.fromisoformat(time[:strip])
                stripping_that_shit = False
            except ValueError:
                strip -= 1
                if strip < -10:
                    stripping_that_shit = False  # idfk then
    return time


def lseen_format(d: int, h: int, m: int):
    if int(d) == 0 and h == 0 and m == 0:
        last_seen = f"Last Seen: `Just now`"
    elif int(d) == 0 and h == 0:
        last_seen = f"Last Seen: `{m} minutes ago`"
    elif int(d) == 0 and h >= 0:
        last_seen = f"Last Seen: `{h}h {m}m ago`"
    elif int(d) > 5:
        last_seen = f"Last Seen: `{d} days ago`"
    else:
        last_seen = f"Last Seen: `{d}d {h}h {m}m ago`"
    return last_seen


# Handles tribe log formatting/itemizing
async def tribelog_format(server: dict, msg: str):
    if "froze" in msg:
        regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): (.+)\)'
    else:
        regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): .+>(.+)<'
    tribe = re.findall(regex, msg)
    if not tribe:
        return
    name = tribe[0][0]
    tribe_id = tribe[0][1]
    time = tribe[0][2]
    action = tribe[0][3]
    if "was killed" in action.lower():
        color = discord.Color.from_rgb(255, 13, 0)  # bright red
    elif "tribe killed" in action.lower():
        color = discord.Color.from_rgb(246, 255, 0)  # gold
    elif "starved" in action.lower():
        color = discord.Color.from_rgb(140, 7, 0)  # dark red
    elif "demolished" in action.lower():
        color = discord.Color.from_rgb(133, 86, 5)  # brown
    elif "destroyed" in action.lower():
        color = discord.Color.from_rgb(115, 114, 112)  # grey
    elif "tamed" in action.lower():
        color = discord.Color.from_rgb(0, 242, 117)  # lime
    elif "froze" in action.lower():
        color = discord.Color.from_rgb(0, 247, 255)  # cyan
    elif "claimed" in action.lower():
        color = discord.Color.from_rgb(255, 0, 225)  # pink
    elif "unclaimed" in action.lower():
        color = discord.Color.from_rgb(102, 0, 90)  # dark purple
    elif "uploaded" in action.lower():
        color = discord.Color.from_rgb(255, 255, 255)  # white
    elif "downloaded" in action.lower():
        color = discord.Color.from_rgb(2, 2, 117)  # dark blue
    else:
        color = discord.Color.purple()
    embed = discord.Embed(
        title=f"{server['cluster'].upper()} {server['name'].capitalize()}: {name}",
        color=color,
        description=f"```py\n{action}\n```"
    )
    embed.set_footer(text=f"{time} | Tribe ID: {tribe_id}")
    return tribe_id, embed


# Format profile data
def profile_format(data: dict):
    gt, gs, pfp = None, None, None
    user = data["profile_users"][0]
    xuid = user['id']
    for setting in user["settings"]:
        if setting["id"] == "Gamertag":
            gt = setting["value"]
        if setting["id"] == "Gamerscore":
            gs = "{:,}".format(int(setting['value']))
        if setting["id"] == "GameDisplayPicRaw":
            pfp = setting['value']

    return gt, xuid, gs, pfp


# Returns players that havent been on any server in X days
async def expired_players(stats: dict, time: datetime.datetime, unfriendtime: int, timezone: datetime.timezone):
    expired = []
    for xuid, data in stats.items():
        user = data["username"]
        lastseen = data["lastseen"]["time"]
        if data["lastseen"]["map"]:
            timestamp = datetime.datetime.fromisoformat(lastseen)
            timestamp = timestamp.astimezone(timezone)
            timedifference = time - timestamp
            if timedifference.days >= unfriendtime:
                expired.append((xuid, user))
    return expired


# Leaderboard embed formatter
def lb_format(stats: dict, guild: discord.guild, timezone: str):
    embeds = []
    leaderboard = {}
    global_time = 0
    # Global cumulative time
    for xuid, data in stats.items():
        time = data["playtime"]["total"]
        leaderboard[xuid] = time
        global_time = global_time + time
    gd, gh, gm = time_format(global_time)
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    pages = math.ceil(len(sorted_players) / 10)
    start = 0
    stop = 10
    for p in range(pages):
        embed = discord.Embed(
            title="Playtime Leaderboard",
            description=f"Global Cumulative Playtime: `{gd}d {gh}h {gm}m`\n\n"
                        f"**Top Players by Playtime** - `{len(sorted_players)} in Database`\n",
            color=discord.Color.random()
        )
        embed.set_thumbnail(url=guild.icon_url)
        if stop > len(sorted_players):
            stop = len(sorted_players)
        for i in range(start, stop, 1):
            xuid = sorted_players[i][0]
            maps = ""
            username = stats[xuid]["username"]
            for mapname, timeplayed in stats[xuid]["playtime"].items():
                if mapname != "total":
                    d, h, m = time_format(timeplayed)
                    if d == 0 and h == 0:
                        maps += f"{mapname.capitalize()}: `{m}m`\n"
                    elif d == 0 and h > 0:
                        maps += f"{mapname.capitalize()}: `{h}h {m}m`\n"
                    else:
                        maps += f"{mapname.capitalize()}: `{d}d {h}h {m}m`\n"
            total = sorted_players[i][1]
            days, hours, minutes = time_format(total)
            tz = pytz.timezone(timezone)
            time = datetime.datetime.now(tz)
            last_seen = stats[xuid]['lastseen']["time"]
            if stats[xuid]['lastseen']["map"] == "None":
                print(username, "NO TIME")
            timestamp = datetime.datetime.fromisoformat(last_seen)
            timestamp = timestamp.astimezone(tz)
            timedifference = time - timestamp
            td = int(timedifference.total_seconds())
            d, h, m = time_format(td)
            last_seen = lseen_format(d, h, m)
            embed.add_field(
                name=f"{i + 1}. {username}",
                value=f"Total: `{days}d {hours}h {minutes}m`\n"
                      f"{maps}"
                      f"{last_seen}"
            )
        embed.set_footer(text=f"Pages {p + 1}/{pages}")
        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


def cstats_format(stats: dict, guild: discord.guild):
    embeds = []
    maps = {}
    total_playtimes = {}
    for data in stats.values():
        for mapname, playtime in data["playtime"].items():
            if mapname != "total":
                total_playtimes[mapname] = {}
                maps[mapname] = 0
    for xuid, data in stats.items():
        for mapn, playtime in data["playtime"].items():
            if mapn != "total":
                player = data["username"]
                total_playtimes[mapn][player] = playtime
                maps[mapn] += playtime
    sorted_maps = sorted(maps.items(), key=lambda x: x[1], reverse=True)
    count = 1
    pages = math.ceil(len(sorted_maps) / 10)
    start = 0
    stop = 10
    for p in range(pages):
        embed = discord.Embed(
            title="Cluster Stats",
            description=f"Showing maps for all clusters:",
            color=discord.Color.random()
        )
        embed.set_thumbnail(url=guild.icon_url)
        if stop > len(sorted_maps):
            stop = len(sorted_maps)
        for i in range(start, stop, 1):
            mapname = sorted_maps[i][0]
            playtime = sorted_maps[i][1]
            top_player = max(total_playtimes[mapname], key=total_playtimes[mapname].get)
            top_player_time = total_playtimes[mapname][top_player]
            md, mh, mm = time_format(top_player_time)
            d, h, m = time_format(playtime)
            embed.add_field(
                name=f"{count}. {mapname.capitalize()} - {len(total_playtimes[mapname].keys())} Players",
                value=f"Total Time Played: `{d}d {h}h {m}m`\n"
                      f"Top Player: `{top_player}` - `{md}d {mh}h {mm}m`",
                inline=False
            )
            count += 1
        embed.set_footer(text=f"Pages {p + 1}/{pages}")
        start += 10
        stop += 10
        embeds.append(embed)
    return embeds


def player_stats(stats: dict, timezone: datetime.timezone, guild: discord.guild, gamertag: str):
    current_time = datetime.datetime.now(timezone)
    for xuid, data in stats.items():
        if gamertag.lower() == data["username"].lower():
            time = data["playtime"]["total"]
            timestamp = datetime.datetime.fromisoformat(data["lastseen"]["time"])
            timestamp = timestamp.astimezone(timezone)
            timedifference = current_time - timestamp
            td = int(timedifference.total_seconds())
            # Last seen dhm
            ld, lh, lm = time_format(td)
            lastmap = data["lastseen"]["map"]
            # Time played dhm
            d, h, m = time_format(time)
            registration = "Not Registered"
            if "discord" in data:
                member = guild.get_member(data["discord"])
                if member:
                    registration = f"Registered as {member.mention}"
                else:
                    registration = f"Registered as ID: {data['discord']} `(No longer in server)`"
            embed = discord.Embed(
                title=f"Player Stats for {data['username']}",
                description=f"Discord: {registration}\n"
                            f"Player ID: {xuid}"
            )
            if not (d and h and m) == 0:
                embed.add_field(
                    name="Total Time Played",
                    value=f"`{d}d {h}h {m}m`"
                )
            if lastmap:
                last_seen = f"{lseen_format(ld, lh, lm)} on `{lastmap}`"
            else:
                last_seen = f"{lseen_format(ld, lh, lm)}"
            embed.add_field(
                name="Last Seen",
                value=last_seen,
                inline=False
            )
            if "leftdiscordon" in data:
                left_on = data["leftdiscordon"]
                left_on = datetime.datetime.fromisoformat(left_on)
                left_on = left_on.astimezone(timezone)
                embed.add_field(
                    name="Left Discord",
                    value=f"`{left_on.strftime('%m/%d/%y at %I:%M %p')}`"
                )
            for mapname, playtime in data["playtime"].items():
                if mapname != "total":
                    d, h, m = time_format(playtime)
                    if not (d and h and m) == 0:
                        embed.add_field(
                            name=mapname,
                            value=f"`{d}d {h}h {m}m`"
                        )
            return embed


async def detect_friends(friends: list, followers: list):
    people_to_add = []
    xuids = []
    for friend in friends:
        xuids.append(friend["xuid"])

    for follower in followers:
        if follower["xuid"] not in xuids:
            followed_back = follower["isFollowedByCaller"]
            if not followed_back:
                date_followed = follower["follower"]["followedDateTime"]
                date_followed = fix_timestamp(date_followed)
                time = datetime.datetime.utcnow()
                timedifference = time - date_followed
                if int(timedifference.total_seconds()) < 3600:
                    people_to_add.append((follower["xuid"], follower["gamertag"]))
    return people_to_add


# Plot player count for each cluster
async def get_graph(settings: dict, hours: int):
    lim = hours * 60
    times = settings["serverstats"]["dates"]
    counts = settings["serverstats"]["counts"]
    if len(counts) == 0 or len(times) == 0:
        return None
    x = []
    y = []
    c = {}

    if len(times) < lim:
        hours = lim / 60
        lim = len(times)
    start = len(times) - 1
    stop = len(times) - lim

    for cname, countlist in settings["serverstats"].items():
        cname = str(cname.lower())
        if cname != "dates" and cname != "counts" and cname != "expiration":
            if cname not in c:
                c[cname] = []
            for i in range(start, stop, -1):
                try:
                    c[cname].append(countlist[i])
                except IndexError:
                    return None

    for i in range(start, stop, -1):
        try:
            timestamp = datetime.datetime.fromisoformat(times[i])
            timestamp = timestamp.strftime('%m/%d %I:%M %p')
            x.append(timestamp)
            y.append(counts[i])
        except IndexError:
            return None

    if len(y) < 3:
        return None
    x.reverse()
    y.reverse()

    title = f"Player Count Over the Past {int(hours)} Hours"
    if hours == 1:
        title = f"Player Count Over the Last Hour"
    clist = ["red", "cyan", "gold", "ghostwhite", "magenta"]
    cindex = 0
    with plt.style.context("dark_background"):
        fig, ax = plt.subplots()

        for cname, countlist in c.items():
            countlist.reverse()
            if len(clist) >= cindex - 1:
                plt.plot(x, countlist, label=cname, color=f"xkcd:{clist[cindex]}")
            else:
                plt.plot(x, countlist, label=cname)
            cindex += 1

        plt.plot(x, y, color="xkcd:green", label="Total")
        plt.ylim([0, max(y) + 2])
        plt.xlabel(f"Time ({settings['timezone']})")
        plt.ylabel("Player Count")
        plt.title(title)
        plt.tight_layout()
        plt.legend(loc=3)
        plt.xticks(rotation=30)
        plt.subplots_adjust(bottom=0.2)
        plt.grid(axis="y")

        ax.xaxis.set_major_locator(MaxNLocator(10))

        result = io.BytesIO()
        plt.savefig(result, format="png", dpi=200)
        plt.close()
        result.seek(0)
        file = discord.File(result, filename="plot.png")
        result.close()
        return file







