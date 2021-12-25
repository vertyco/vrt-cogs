import math
import discord
import re
import datetime
import pytz
import io
import unicodedata

from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator


# Hard coded item blueprint paths for the imstuck command
IMSTUCK_BLUEPRINTS = [
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Resources/PrimalItemResource_Polymer_Organic.PrimalItemResource_Polymer_Organic'" 8 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItemAmmo_GrapplingHook.PrimalItemAmmo_GrapplingHook'" 3 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_WeaponCrossbow.PrimalItem_WeaponCrossbow'" 1 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Structures/Thatch/PrimalItemStructure_ThatchFloor.PrimalItemStructure_ThatchFloor'" 1 0 0""",
    f""""Blueprint'/Game/Aberration/CoreBlueprints/Weapons/PrimalItem_WeaponClimbPick.PrimalItem_WeaponClimbPick'" 1 0 0"""
]


# Filter unicode, emojis, and links out of messages and user names
async def decode(message: discord.Message):
    # Strip links, emojis, and unicode characters from message content before sending to server
    nolinks = re.sub(r'https?:\/\/[^\s]+', '', message.content)
    noemojis = re.sub(r'<:\w*:\d*>', '', nolinks)
    nocustomemojis = re.sub(r'<a:\w*:\d*>', '', noemojis)
    msg = unicodedata.normalize('NFKD', nocustomemojis).encode('ascii', 'ignore').decode()
    if not msg:
        return
    if msg == " ":
        return

    # Convert any unicode characters in member name to normal text
    author = message.author
    normalizedname = unicodedata.normalize('NFKD', author.name).encode('ascii', 'ignore').decode()
    validname = normalizedname.strip()
    if not validname:
        normalizedname = unicodedata.normalize('NFKD', author.nick).encode('ascii', 'ignore').decode()
    return normalizedname, msg


# Format time from total seconds
def time_format(time_played: int):
    minutes, _ = divmod(time_played, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return int(days), int(hours), int(minutes)


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
async def expired_players(stats: dict, unfriendtime: int):
    expired = []
    tz = pytz.timezone("UTC")
    now = datetime.datetime.now(tz)
    for xuid, data in stats.items():
        user = data["username"]
        lastseen = data["lastseen"]["time"]
        if data["lastseen"]["map"]:
            timestamp = datetime.datetime.fromisoformat(lastseen)
            timestamp = timestamp.astimezone(tz)
            timedifference = now - timestamp
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
        if "playtime" in data:
            time = data["playtime"]["total"]
            leaderboard[xuid] = time
            global_time = global_time + time
    gd, gh, gm = time_format(global_time)
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    # Figure out how many pages the lb menu will be
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
        # Put 10 players per page, adding 10 to the start and stop values after each loop
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


# Same thing as ark leaderboard but cluster specific
def cstats_format(stats: dict, guild: discord.guild):
    embeds = []
    maps = {}
    total_playtimes = {}
    for data in stats.values():
        if "playtime" in data:
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


# Format stats for an individual player
def player_stats(settings: dict, guild: discord.guild, gamertag: str):
    kit = settings["kit"]
    stats = settings["players"]
    leaderboard = {}
    global_time = 0
    # Global cumulative time
    for xuid, data in stats.items():
        if "playtime" in data:
            ptime = data["playtime"]["total"]
            leaderboard[xuid] = ptime
            global_time = global_time + ptime

    position = ""
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    current_time = datetime.datetime.now(pytz.timezone("UTC"))
    for xuid, data in stats.items():
        if gamertag.lower() == data["username"].lower():
            ptime = data["playtime"]["total"]
            for i in sorted_players:
                if i[0] == xuid:
                    pos = sorted_players.index(i)
                    position = f"{pos + 1}/{len(sorted_players)}"

            timestamp = datetime.datetime.fromisoformat(data["lastseen"]["time"])
            timestamp = timestamp.astimezone(pytz.timezone("UTC"))
            timedifference = current_time - timestamp
            td = int(timedifference.total_seconds())
            td = abs(td)
            # Last seen dhm
            ld, lh, lm = time_format(td)
            lastmap = data["lastseen"]["map"]
            # Time played dhm
            d, h, m = time_format(ptime)
            t = f"{d}d {h}h {m}m"
            if ptime == 0:
                t = "None"
            registration = "Not Registered"
            in_server = True
            if "discord" in data:
                member = guild.get_member(data["discord"])
                if member:
                    registration = f"{member.mention}"
                else:
                    registration = f"{data['discord']}"
                    in_server = False
            claimed = "Unclaimed"
            if xuid in kit["claimed"]:
                claimed = "Claimed"
            desc = f"`Discord:     `{registration}\n" \
                   f"`Game ID:     `{xuid}\n" \
                   f"`Time Played: `{t}\n" \
                   f"`Starter Kit: `{claimed}"
            if "rank" in data:
                r = data["rank"]
                r = guild.get_role(r)
                if r:
                    desc += f"\n`Player Rank: `{r.mention}"
            embed = discord.Embed(
                title=f"Player Stats for {data['username']}",
                description=desc
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
            if "leftdiscordon" in data and not in_server:
                left_on = data["leftdiscordon"]
                left_on = datetime.datetime.fromisoformat(left_on)
                timezone = settings["timezone"]
                timezone = pytz.timezone(timezone)
                left_on = left_on.astimezone(timezone)
                embed.add_field(
                    name="Left Discord",
                    value=f"`{left_on.strftime('%m/%d/%y at %I:%M %p')}`"
                )
            for mapname, playtime in data["playtime"].items():
                if mapname != "total":
                    d, h, m = time_format(playtime)
                    if playtime > 0:
                        embed.add_field(
                            name=f"Time on {mapname.capitalize()}",
                            value=f"`{d}d {h}h {m}m`"
                        )
            if "ingame" in data:
                implant_ids = ""
                for mapid, implant in data["ingame"].items():
                    channel = guild.get_channel(int(mapid))
                    if channel:
                        mapid = channel.mention
                    implant_ids += f"{mapid}: {implant}\n"
                embed.add_field(
                    name="Registered Implant IDs",
                    value=implant_ids,
                    inline=False
                )
            if position != "":
                percent = round((ptime / global_time) * 100, 2)
                embed.set_footer(text=f"Rank: {position} with {percent}% of the total playtime")
            return embed


# Detect recent followers and return list of people to add back
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


# Detect if a user account is suspicious based on owner's settings
def detect_sus(alt: dict, profile: dict, friends: dict):
    reasons = ""
    sus = False
    tier = None
    gs = None
    user = profile["profile_users"][0]
    for setting in user["settings"]:
        if setting["id"] == "AccountTier":
            tier = setting["value"]
        if setting["id"] == "Gamerscore":
            gs = int(setting["value"])

    following = int(friends["target_following_count"])
    followers = int(friends["target_follower_count"])
    if alt["silver"]:
        if tier == "Silver":
            sus = True
            reasons += "Using a Silver account\n"
    if gs < alt["mings"]:
        sus = True
        reasons += f"Only has {gs} Gamerscore\n"
    if following < alt["minfollowing"]:
        sus = True
        reasons += f"Only following {following} users\n"
    if followers < alt["minfollowers"]:
        sus = True
        reasons += f"Only has {followers} followers"
    return sus, reasons


# Plot player count for each cluster
# Instead of relying on matplotlibs date formatter, the data points are selected manually with set ticks
async def get_graph(settings: dict, hours: int):
    lim = hours * 60
    days = int(hours / 24)
    times = settings["serverstats"]["dates"]
    counts = settings["serverstats"]["counts"]
    timezone = settings['timezone']
    tz = pytz.timezone(timezone)
    if len(counts) == 0 or len(times) == 0:
        return None
    title = f"Player Count Over the Past {int(hours)} Hours"
    if days > 5:
        title = f"Player Count Over the Past {days} Days"
    if len(times) < lim:  # Time input is greater of equal to available time recorded
        hours = int(len(times) / 60)
        days = int(hours / 24)
        if days > 5:
            title = f"Player Count Over Lifetime ({days} Days)"
        else:
            title = f"Player Count Over Lifetime ({hours} Hours)"
        lim = len(times)
    if hours == 1:
        title = f"Player Count Over the Last Hour"
    stagger = math.ceil(lim * 0.001)
    c = {}
    for cname, countlist in settings["serverstats"].items():
        cname = str(cname.lower())
        if cname != "dates" and cname != "counts" and cname != "expiration":
            cl = countlist[:-lim:-stagger]
            cl.reverse()
            c[cname] = cl
    dates = times[:-lim:-stagger]
    x = []
    y = counts[:-lim:-stagger]
    for d in dates:
        d = datetime.datetime.fromisoformat(d)
        d = d.astimezone(tz)
        if days > 1:
            d = d.strftime('%m/%d %I:%M %p')
        else:
            d = d.strftime('%I:%M %p')
        x.append(d)

    if days > 20:
        locator = 20
    else:
        locator = "auto"

    x.reverse()
    y.reverse()
    if len(y) < 3:
        return None
    clist = ["red",
             "cyan",
             "gold",
             "white",
             "magenta",
             "wheat",
             "yellow",
             "salmon",
             "darkblue",
             "aqua",
             "plum",
             "purple"]
    cindex = 0
    with plt.style.context("dark_background"):
        fig, ax = plt.subplots()
        clusters = len(c.keys())
        if len(clist) >= clusters:
            usecolors = True
        else:
            usecolors = False
        for cname, countlist in c.items():
            if len(countlist) < len(y):
                countlist.reverse()
                n = 0
                while n == 0:
                    countlist.append(0)
                    if len(countlist) == len(y):
                        countlist.reverse()
                        n += 1
                        break
            if len(clist) >= cindex - 1 and usecolors:
                color = f"xkcd:{clist[cindex]}"
                plt.plot(x, countlist, label=cname, color=color, linewidth=0.7)
            else:
                plt.plot(x, countlist, label=cname, linewidth=0.7)
            cindex += 1
        plt.plot(x, y, color="xkcd:green", label="Total", linewidth=0.7)
        plt.ylim([0, max(y) + 2])
        plt.xlabel(f"Time ({timezone})", fontsize=10)
        maxplayers = max(y)
        plt.ylabel(f"Player Count (Max: {maxplayers})", fontsize=10)
        plt.title(title)
        plt.tight_layout()
        plt.legend(loc=3)
        plt.xticks(rotation=30, fontsize=9)
        plt.yticks(fontsize=10)
        plt.subplots_adjust(bottom=0.2)
        plt.grid(axis="y")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=locator, integer=True, min_n_ticks=10))
        result = io.BytesIO()
        plt.savefig(result, format="png", dpi=200)
        plt.close()
        result.seek(0)
        file = discord.File(result, filename="plot.png")
        result.close()
        return file





