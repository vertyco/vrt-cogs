import datetime
import io
import math
import re
import unicodedata

import discord
import pytz
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator
import logging

log = logging.getLogger("red.vrt.arktools")

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
    # Convert any unicode characters in member name to normal text
    author = message.author
    normalizedname = unicodedata.normalize('NFKD', author.name).encode('ascii', 'ignore').decode()
    validname = normalizedname.strip()
    if not validname:
        normalizedname = unicodedata.normalize('NFKD', author.nick).encode('ascii', 'ignore').decode()
    return normalizedname, msg


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds):
    time_in_seconds = int(time_in_seconds)  # Some time differences get sent as a float so just handle it the dumb way
    minutes, seconds = divmod(time_in_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    if not any([seconds, minutes, hours, days, years]):
        tstring = "None"
    elif not any([minutes, hours, days, years]):
        if seconds == 1:
            tstring = f"{seconds} second"
        else:
            tstring = f"{seconds} seconds"
    elif not any([hours, days, years]):
        if minutes == 1:
            tstring = f"{minutes} minute"
        else:
            tstring = f"{minutes} minutes"
    elif hours and not days and not years:
        tstring = f"{hours}h {minutes}m"
    elif days and not years:
        tstring = f"{days}d {hours}h {minutes}m"
    else:
        tstring = f"{years}y {days}d {hours}h {minutes}m"
    return tstring


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
    global_playtime = time_formatter(global_time)
    sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    # Figure out how many pages the lb menu will be
    pages = math.ceil(len(sorted_players) / 10)
    start = 0
    stop = 10
    for p in range(pages):
        embed = discord.Embed(
            title="Playtime Leaderboard",
            description=f"Global Cumulative Playtime: `{global_playtime}`\n\n"
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
                    playtime = time_formatter(timeplayed)
                    maps += f"{mapname.capitalize()}: `{playtime}`\n"
            total = sorted_players[i][1]
            total_playtime = time_formatter(total)
            tz = pytz.timezone(timezone)
            time = datetime.datetime.now(tz)
            last_seen = stats[xuid]['lastseen']["time"]
            if stats[xuid]['lastseen']["map"] == "None":
                print(username, "NO TIME")
            timestamp = datetime.datetime.fromisoformat(last_seen)
            timestamp = timestamp.astimezone(tz)
            timedifference = time - timestamp
            td = int(timedifference.total_seconds())
            lseen = time_formatter(td)
            embed.add_field(
                name=f"{i + 1}. {username}",
                value=f"Total: `{total_playtime}`\n"
                      f"{maps}"
                      f"Last Seen: `{lseen} ago`"
            )
        embed.set_footer(text=f"Pages {p + 1}/{pages}")
        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


# Leaderboard embed tribe formatter
def tribe_lb_format(tribes: dict, guild: discord.guild):
    embeds = []
    leaderboard = {}
    global_kills = 0
    for tribe_id, data in tribes.items():
        if "kills" in data:  # Just in case
            if data["kills"]:
                global_kills += data["kills"]
                leaderboard[tribe_id] = data["kills"]

    sorted_tribes = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    pages = math.ceil(len(sorted_tribes) / 10)
    start = 0
    stop = 10
    for p in range(pages):
        embed = discord.Embed(
            title="Tribe Leaderboard",
            description=f"Global Cumulative Kills: `{global_kills}`\n\n",
            color=discord.Color.random()
        )
        embed.set_thumbnail(url=guild.icon_url)
        # Put 10 players per page, adding 10 to the start and stop values after each loop
        if stop > len(sorted_tribes):
            stop = len(sorted_tribes)
        for i in range(start, stop, 1):
            tribe_id = sorted_tribes[i][0]
            kills = sorted_tribes[i][1]
            tribename = tribes[tribe_id]["tribename"]
            servername = tribes[tribe_id]["servername"]
            owner = guild.get_member(tribes[tribe_id]["owner"])
            if owner:
                owner = owner.mention
            else:
                owner = tribes[tribe_id]["owner"]
                if not owner:
                    owner = "Unknown/Not Set"
            members = tribes[tribe_id]["allowed"]
            tribe_members = ""
            if members:
                for member in members:
                    if guild.get_member(member):
                        tribe_members += f"{guild.get_member(member).mention}, "
            msg = f"`Server: `{servername}\n" \
                  f"`Owner:  `{owner}\n" \
                  f"`Kills:  `{kills}"
            if tribe_members:
                tribe_members.rstrip(",")
                msg += f"\n`Members:  `{tribe_members}"
            if "members" in tribes[tribe_id]:
                if tribes[tribe_id]["members"]:
                    members = ""
                    for member in tribes[tribe_id]["members"]:
                        members += f"{member}, "
                    if members:
                        members.rstrip(",")
                        msg += f"\n`In-Game:  `{members}"
            embed.add_field(
                name=f"{i + 1}. {tribename}",
                value=msg
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
            total_playtime = sorted_maps[i][1]
            total_time_played = time_formatter(total_playtime)

            top_player = max(total_playtimes[mapname], key=total_playtimes[mapname].get)
            top_player_time = total_playtimes[mapname][top_player]
            top_player_playtime = time_formatter(top_player_time)

            embed.add_field(
                name=f"{count}. {mapname.capitalize()} - {len(total_playtimes[mapname].keys())} Players",
                value=f"Total Time Played: `{total_time_played}`\n"
                      f"Top Player: `{top_player}` - `{top_player_playtime}`",
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
            total_playtime = data["playtime"]["total"]
            for i in sorted_players:
                if i[0] == xuid:
                    pos = sorted_players.index(i)
                    position = f"{pos + 1}/{len(sorted_players)}"
            timestamp = datetime.datetime.fromisoformat(data["lastseen"]["time"])
            timestamp = timestamp.astimezone(pytz.timezone("UTC"))
            timedifference = current_time - timestamp
            td = int(timedifference.total_seconds())
            td = abs(td)  # shouldnt matter any more since config setup was changed
            # Last seen dhm
            last_seen = time_formatter(td)
            lastmap = data["lastseen"]["map"]
            if lastmap:
                last_seen = f"`{last_seen} ago on {lastmap}`"
            else:
                last_seen = f"`{last_seen} ago`"
            # Time played dhm
            total_playtime_string = time_formatter(total_playtime)
            registration = "Not Registered"
            in_server = True
            color = discord.Color.random()
            pfp = None
            if "discord" in data:
                member = guild.get_member(data["discord"])
                if member:
                    color = member.colour
                    pfp = member.avatar_url
                    registration = f"{member.mention}"
                else:
                    registration = f"{data['discord']}"
                    in_server = False
            claimed = "Unclaimed"
            if xuid in kit["claimed"]:
                claimed = "Claimed"
            desc = f"`Discord:     `{registration}\n" \
                   f"`Game ID:     `{xuid}\n" \
                   f"`Time Played: `{total_playtime_string}\n" \
                   f"`Starter Kit: `{claimed}"
            if "rank" in data:
                r = data["rank"]
                r = guild.get_role(r)
                if r:
                    desc += f"\n`Player Rank: `{r.mention}"
            embed = discord.Embed(
                title=f"Player Stats for {data['username']}",
                description=desc,
                color=color
            )
            if pfp:
                embed.set_thumbnail(url=pfp)
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
                    ptime = time_formatter(playtime)
                    if playtime > 0:
                        embed.add_field(
                            name=f"Time on {mapname.capitalize()}",
                            value=f"`{ptime}`"
                        )
            pstats = ""
            for mapid, info in data["ingame"].items():
                channel = guild.get_channel(int(mapid))
                if channel:
                    mapid = channel.mention

                implant = info["implant"]
                name = info["name"]
                if not implant and not name:
                    continue
                pk = info["stats"]["pvpkills"]
                pd = info["stats"]["pvpdeaths"]
                ped = info["stats"]["pvedeaths"]
                tamed = info["stats"]["tamed"]
                prev_names = info["previous_names"]
                pstats += f"{mapid}\n"
                if implant:
                    pstats += f"`Implant:        `{implant}\n"
                if name:
                    pstats += f"`Character Name: `{name}\n"
                if any([pk, pd, ped]):
                    pstats += f"`PvE Deaths:  `{ped}\n" \
                              f"`PvP Kills:   `{pk}\n" \
                              f"`PVP Deaths:  `{pd}\n"
                    if pk > 0 and pd > 0:
                        kd_ratio = round(pk / pd, 2)
                        pstats += f"`PvP K/D:     `{kd_ratio}\n"
                if tamed:
                    pstats += f"`Dinos Tamed: `{tamed}\n"
                if prev_names:
                    names = ""
                    for name in prev_names:
                        if name:
                            names += f"{name}, "
                    if names:
                        names = names.rstrip(", ")
                        pstats += f"`Previous Names: `{names}\n"
            if pstats:
                embed.add_field(
                    name="In-Game Stats",
                    value=pstats,
                    inline=False
                )
            if position != "":
                percent = round((total_playtime / global_time) * 100, 2)
                embed.set_footer(text=f"Rank: {position} with {percent}% of global playtime")
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


# Takes config and removes funky stuff from it
async def cleanup_config(settings: dict):
    cleanup_status = ""
    # First off, fix any old cluster data for the server graph
    newgraphdata = {}
    count = 0
    for cname, countlist in settings["serverstats"].items():
        # Just add these to the newdata dict
        if cname == "dates" or cname == "counts" or cname == "expiration":
            newgraphdata[cname] = countlist
        # Only adds the player count list to the newdata if the cluster exists in main settings still
        else:
            if cname in settings["clusters"]:
                newgraphdata[cname] = countlist
            else:
                count += 1
    if count > 0:
        cleanup_status += f"Deleted {count} old clusters from graph data\n"
    count = 0
    settings["serverstats"] = newgraphdata

    # Next is fixing players that have old map data in their player stats
    current_names = []
    for cname, data in settings["clusters"].items():  # Go through all clusters
        servers = data["servers"]
        for server in servers:  # Then go through all servers in that cluster
            name = f"{server.lower()} {cname.lower()}"
            current_names.append(name)  # Append that name to the current names list
    updated_players = {}
    for uid, player in settings["players"].items():  # NOW go through every player in the database
        if "playtime" in player:  # If the player actually has playtime logged
            updated_player = {}
            for k, v in player.items():
                if k == "playtime":
                    new_playtime = {"total": player["playtime"]["total"]}
                    # Iterate through the existing map names and only add the ones that still exist
                    for n in current_names:
                        if n in player["playtime"]:  # If the map string still exists, add it to the new dict
                            new_playtime[n] = player["playtime"][n]
                    updated_player["playtime"] = new_playtime
                    if len(player["playtime"]) != len(new_playtime):  # See if old and new data is different
                        count += 1
                else:
                    updated_player[k] = v  # Add other not relevant data back to the updated player by default
            updated_players[uid] = updated_player  # Add the single updated player to the updated players dict
        else:
            updated_players[uid] = player  # If they dont have playtime data just add them to the new dict
    if count > 0:
        cleanup_status += f"Removed old maps from {count} players\n"
    count = 0
    settings["players"] = updated_players

    # Rehash player data to make sure user ID's are valid and config is up-to-data
    rehashed_players = {}
    fixed = 0
    for xuid, playerdata in settings["players"].items():
        if xuid.isdigit():
            if 20 > len(xuid) > 15:
                if "ingame" not in playerdata:
                    playerdata["ingame"] = {}
                    fixed += 1
                if playerdata["ingame"]:
                    old = True
                    for value in playerdata["ingame"].values():
                        if isinstance(value, dict):  # Only newer config has dict in it, so config is not old
                            old = False
                            break
                    if old:
                        fixed_stats = {}
                        for channel, implant in playerdata["ingame"].items():
                            fixed_stats[channel] = {
                                "implant": implant,
                                "name": None,
                                "previous_names": [],
                                "stats": {
                                    "pvpkills": 0,
                                    "pvpdeaths": 0,
                                    "pvedeaths": 0,
                                    "tamed": 0
                                }
                            }
                        playerdata["ingame"] = fixed_stats
                        fixed += 1
                    else:  # Make sure everything else is straight
                        keys_to_delete = []
                        for channel, data in playerdata["ingame"].items():
                            if channel == "stats":  # Supposed to be channel ID's not channel, cleanup from oopsie
                                keys_to_delete.append(channel)
                        if keys_to_delete:
                            for key in keys_to_delete:
                                del playerdata["ingame"][key]
                                fixed += 1
                rehashed_players[xuid] = playerdata
            else:
                count += 1
        else:
            count += 1
    if count > 0 or fixed > 0:
        cleanup_status += f"Removed {count} players from the database with invalid ID's and fixed {fixed} of them\n"
    count = 0
    settings["players"] = rehashed_players

    # Fix any tribe issues
    tribes = settings["tribes"]
    newtribedata = {}
    for tribe_id, data in tribes.items():
        if "kills" not in data:
            log.warning(f"TribeID {tribe_id}: {data}")
            newtribedata[tribe_id] = {
                "tribename": None,
                "owner": data["owner"],
                "channel": data["channel"],
                "allowed": data["allowed"],
                "kills": 0,
                "servername": None
            }
            count += 1
        else:
            newtribedata[tribe_id] = data
    settings["tribes"] = newtribedata
    if count:
        cleanup_status += f"Fixed {count} Tribe configs with old data\n"
        count = 0

    # Make sure players have a username for whatever reason they wouldnt maybe bot crash while registering idk
    no_username = []
    for xuid, data in settings["players"].items():
        if "username" not in data:
            no_username.append(xuid)
            count += 1
    for xuid in no_username:
        del settings["players"][xuid]
    if count > 0:
        cleanup_status += f"Removed {count} players that for whatever reason had no username attached to their ID"
    else:
        cleanup_status = cleanup_status.rstrip("\n")
    return settings, cleanup_status


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
