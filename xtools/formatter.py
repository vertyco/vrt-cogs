import json
import math
import re
import traceback
from datetime import datetime
from typing import List

import discord
import pytz
import tabulate
from redbot.core.utils.chat_formatting import box, humanize_timedelta, pagify


# Check if an object is None
def check(data):
    if data:
        return data
    return "¯\\_(ツ)_/¯"


# Time Converter
def time_format(time):
    minutes, _ = divmod(time, 60)
    hours, minutes = divmod(minutes, 60)
    return hours, minutes


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds) -> str:
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


# Microsoft's timestamp end digits are fucked up and random, so we iteratively try fixing them by stripping digits
def fix_timestamp(time: str, timezone: str = "UTC"):
    try:
        res = re.search(r"(.+:\d\d)[.Z]\d*([+-].+)*", time)
        string = "".join(g for g in res.groups() if g)
        return datetime.fromisoformat(string).astimezone(pytz.timezone(timezone))
    except ValueError:
        raise ValueError(f"{traceback.format_exc()}\nOriginal String: {time}")


# Format profile data
def profile(data):
    # Main profile data
    gt, xuid, bio, location, gs, pfp, tenure, tier, rep = (
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    user = data["profile_users"][0]
    xuid = user["id"]
    for setting in user["settings"]:
        if setting["id"] == "Gamertag":
            gt = setting["value"]
        if setting["id"] == "Bio":
            bio = setting["value"]
        if setting["id"] == "Location":
            location = setting["value"]
        if setting["id"] == "Gamerscore":
            gs = "{:,}".format(int(setting["value"]))
        if setting["id"] == "GameDisplayPicRaw":
            pfp = setting["value"]
        if setting["id"] == "TenureLevel":
            tenure = setting["value"]
        if setting["id"] == "AccountTier":
            tier = setting["value"]
        if setting["id"] == "XboxOneRep":
            rep = setting["value"]
    return gt, xuid, bio, location, gs, pfp, tenure, tier, rep


# Format profile embed
def profile_embed(data) -> discord.Embed:
    gt, xuid, bio, location, gs, pfp, tenure, tier, rep = profile(data)
    state = data["presence"]["state"]
    if state == "Online":
        color = discord.Color.green()
    else:
        color = discord.Color.dark_grey()
    title = f"{gt}'s Profile ({state})"
    embed = discord.Embed(
        title=title,
        color=color,
        description="Any field with `¯\\_(ツ)_/¯` is due to account privacy settings, you can manage that "
        "**[here](https://account.xbox.com/en-gb/Settings)**",
    )
    following = data["friends"]["target_following_count"]
    followers = data["friends"]["target_follower_count"]
    account_info = (
        f"`Gamerscore:  `{gs}\n"
        f"`Followers:   `{followers}\n"
        f"`Following:   `{following}\n"
        f"`AccountTier: `{tier}\n"
        f"`Player Rep:  `{rep}\n"
        f"`Location:    `{check(location)}\n"
        f"`Member For:  `{tenure} years\n"
        f"`XUID:        `{xuid}"
    )
    embed.set_thumbnail(url=pfp)
    embed.add_field(name="Account Info", value=account_info)

    presence = data["presence"]

    # Rename devices according to their code name
    def device_check(device):
        if device == "Durango":
            device = "1st Gen XboxOne"
        elif device == "Scarlett":
            device = "Xbox Series S"
        elif device == "WindowsOneCore":
            device = "Windows"
        elif device == "Win32":
            device = "Steam"
        elif device == "Anaconda":
            device = "Xbox Series X"
        return device

    # Format field depending on if user is offline or not
    current_time = datetime.now().astimezone(pytz.timezone("UTC"))
    if "lastSeen" in presence:
        game = presence["lastSeen"]["titleName"]
        device = presence["lastSeen"]["deviceType"]
        device = device_check(device)
        time = fix_timestamp(presence["lastSeen"]["timestamp"])
        tdiff = current_time - time
        tstring = humanize_timedelta(seconds=tdiff.total_seconds())
        lseen = f"{tstring} ago on {device}:\n{game}"
        embed.add_field(name="Last Seen", value=lseen)
    if "devices" in presence:
        device = presence["devices"][0]["type"]
        device = device_check(device)
        gamelist = ""
        for game in presence["devices"][0]["titles"]:
            gamelist += f"{game['name']}\n"
        embed.add_field(name="Active Now", value=f"{gamelist}on {device}")

    # Format activity field
    activitylist = ""
    for activity in data["activity"]:
        desc = activity["description"]
        desc = desc[:1].upper() + desc[1:]
        time = fix_timestamp(activity["date"])
        diff = current_time - time
        tstring = humanize_timedelta(seconds=diff.total_seconds())
        event = f"{tstring} ago"
        activitylist += f"{desc} - {event}\n"
    if activitylist == "":
        activitylist = "`¯\\_(ツ)_/¯`"
    embed.add_field(name="Recent Activity", value=activitylist, inline=False)

    if bio != "":
        embed.add_field(name="Bio", value=box(bio), inline=False)
    return embed


# Format screnshot json for sending to the menu
def screenshot_embeds(data, gamertag):
    pages = []
    length = len(data["screenshots"])
    cur_page = 1
    for pic in data["screenshots"]:
        game = pic["title_name"]
        name = pic["screenshot_name"]
        if name == "":
            name = "Untitled"
        caption = pic["user_caption"]
        if caption == "":
            caption = "Uncaptioned"
        views = pic["views"]
        ss = pic["screenshot_uris"][0]["uri"]
        ss = ss.split("?")[0]
        timestamp = (datetime.fromisoformat(pic["date_taken"])).strftime("%m/%d/%Y, %H:%M:%S")
        embed = discord.Embed(color=discord.Color.random(), description=f"**{gamertag}'s Screenshots**")
        embed.set_image(url=ss)
        embed.add_field(
            name="Info",
            value=f"Game: `{check(game)}`\n"
            f"Screenshot Name: `{check(name)}`\n"
            f"Views: `{views}`\n"
            f"Taken on: `{check(timestamp)}`\n"
            f"Caption: `{check(caption)}`\n",
        )
        embed.set_footer(text=f"Pages: {cur_page}/{length}")
        cur_page += 1
        pages.append(embed)
    return pages


# Format game info
def game_embeds(gamertag, gamename, gs, data):
    embeds = []
    # List setup
    stats = []
    if len(data["stats"]["groups"][0]["statlistscollection"]) > 0:
        stats = data["stats"]["groups"][0]["statlistscollection"][0]["stats"]
    achievements = data["achievements"]["achievements"]

    # Main data setup
    minutes_played = 0
    if len(data["stats"]["statlistscollection"][0]["stats"]) > 0:
        minutes_played = int(data["stats"]["statlistscollection"][0]["stats"][0]["value"])
    title_pic = data["info"]["titles"][0]["display_image"]

    count = 1
    for ach in achievements:
        name = ach["name"]
        status = ach["progress_state"]
        desc = ach["locked_description"]
        icon = ach["media_assets"][0]["url"]
        worth = ach["rewards"][0]["value"]
        if status == "Achieved":
            timestamp = ach["progression"]["time_unlocked"]
            time = fix_timestamp(timestamp)
            time = time.strftime("%m/%d/%Y, %H:%M:%S")
            desc = ach["description"]
            info = f"{name}\nStatus: Unlocked on {time}\n{desc}\n{worth} Gamerscore"
        else:
            info = f"{name}\nStatus: {status}\n{desc}\n{worth} Gamerscore"

        embed = discord.Embed(description=f"**{gamertag}'s Achievements for {gamename}**\n{gs} Gamerscore")

        # See if stat value is a float for a percentage or something
        def check_float(number):
            try:
                float(number)
                return True
            except ValueError:
                return False

        for stat in stats:
            statname = stat["groupproperties"]["DisplayName"]
            stype = "Integer"
            if "DisplayFormat" in stat["groupproperties"]:
                stype = stat["groupproperties"]["DisplayFormat"]
            value = "--"
            if "value" in stat:
                if stat["value"].isdigit() or check_float(stat["value"]):
                    value = int(float(stat["value"]))
                else:
                    value = stat["value"]
            if stype == "Percentage":
                value = f"{value}%"
            embed.add_field(name=statname, value=value)
        embed.add_field(name="Achievement Info", value=info, inline=False)
        embed.set_thumbnail(url=title_pic)
        embed.set_image(url=icon)
        hours, minutes = divmod(minutes_played, 60)
        days, hours = divmod(hours, 24)
        embed.set_footer(text=f"Page {count}/{len(achievements)} | Total time played: {days}d {hours}h {minutes}m")
        embeds.append(embed)
        count += 1
    return embeds


# Format friend list
def friend_embeds(friend_data, main_gamertag):
    embeds = []
    count = 1
    friends = friend_data["people"]
    for friend in friends:
        xuid = friend["xuid"]
        # followed_by = friend["is_following_caller"]  # Only useful for authorized user
        name = friend["gamertag"]
        pfp = friend["display_pic_raw"]
        gs = friend["gamer_score"]
        rep = friend["xbox_one_rep"]
        tier = friend["detail"]["account_tier"]
        state = friend["presence_state"]
        account_info = (
            f"Gamerscore: `{gs}`\n"
            f"AccountTier: `{tier}`\n"
            f"Player Rep: `{rep}`\n"
            f"XUID: `{xuid}`\n"
        )  # f"Is Following {main_gamertag}: `{followed_by}`" guess this only works for token owner

        game = None
        color = discord.Color.random()
        if state == "Online":
            color = discord.Color.green()
            game = friend["presence_text"]

        session = friend["multiplayer_summary"]["in_multiplayer_session"]
        party = friend["multiplayer_summary"]["in_party"]

        bio = friend["detail"]["bio"]

        embed = discord.Embed(color=color, description=f"**{main_gamertag}'s Friends**")
        embed.set_thumbnail(url=pfp)
        embed.add_field(name=f"{name} ({state})", value=account_info, inline=False)
        if state == "Online":
            embed.add_field(name="Playing", value=game)
        if int(session) > 0 or int(party) > 0:
            embed.add_field(
                name="Session Info",
                value=f"Game Session: {session} players\nParty Chat: {party}",
            )
        if bio != "":
            embed.add_field(name="Bio", value=box(bio), inline=False)
        embed.set_footer(text=f"Page {count}/{len(friends)}")
        count += 1
        embeds.append(embed)
    return embeds


def gameclip_embeds(clip_data, gamertag):
    embeds = []
    count = 1
    clips = clip_data["game_clips"]
    for clip in clips:
        state = clip["state"]
        recorded_on = fix_timestamp(clip["date_recorded"]).strftime("%m/%d/%Y, %H:%M:%S")
        published = False
        if state == "Published":
            published = True
        duration = int(clip["duration_in_seconds"])
        m, s = divmod(duration, 60)
        views = clip["views"]
        title = clip["clip_name"]
        if title == "":
            title = "Untitled"
        thumbnail = clip["thumbnails"][0]["uri"]
        clip_uri = clip["game_clip_uris"][0]["uri"]
        game = clip["title_name"]
        embed = discord.Embed(description=f"**{gamertag}'s Game Clips**", color=discord.Color.random())
        embed.set_image(url=thumbnail)
        clip_info = (
            f"Title: `{title}`\n"
            f"Game: `{game}`\n"
            f"Duration: `{m}m {s}s`\n"
            f"Views: `{views}`\n"
            f"State: `{state}`\n"
            f"Recorded on: `{recorded_on}`\n"
        )
        if published:
            published_on = fix_timestamp(clip["date_published"]).strftime("%m/%d/%Y, %H:%M:%S")
            clip_info += f"Published on `{published_on}`\n"
        clip_info += f"**[Click Here To Watch]({clip_uri})**"
        embed.add_field(name="Clip Info", value=clip_info)
        embed.set_footer(text=f"Pages {count}/{len(clips)}")
        count += 1
        embeds.append(embed)
    return embeds


# Format microsoft service data
def ms_status(data: dict) -> List[discord.Embed]:
    timezone = "UTC"
    up = "✅"
    limited = "⚠️"
    down = "⛔"

    ss = data["ServiceStatus"]

    status_data = ss["Status"]["Overall"]
    overall = status_data["State"]
    last_updated = fix_timestamp(status_data["LastUpdated"], timezone).strftime("%m/%d/%y at %I:%M %p %Z")
    # If nothing is impacted then just return embed
    if overall == "None":
        color = discord.Color.green()
        embed = discord.Embed(description="✅ All Microsoft services are up and running!", color=color)
        embed.set_footer(text=f"Last Updated: {last_updated}")
        return [embed]

    # Something must be impacted
    # Iterate through service categories and find what is wrong
    out = 0
    core_svc = ss["CoreServices"]
    for service in core_svc["Category"]:
        status = service["Status"]["Name"]
        if status != "Impacted":
            continue
        out += 1

    title_svc = ss["Titles"]
    for service in title_svc["Category"]:
        status = service["Status"]["Name"]
        if status != "Impacted":
            continue
        out += 1

    service_statuses = ""

    for i in core_svc["Category"]:
        service_name = i["Name"]
        status = i["Status"]

        # Skip if the status is impacted
        sname = status["Name"]
        if sname != "Impacted":
            continue

        # Get status emoji based on status ID
        sid = status["Id"]
        if sid == "1":
            indicator = up
        elif sid == "2":
            indicator = down
        else:
            indicator = limited

        service_statuses += f"**{indicator} {service_name}**\n"
        info = ""
        scenarios = i["Scenarios"]["Scenario"]
        for scenario in scenarios:
            if scenario["Status"]["Name"] != "Impacted":
                continue

            name = scenario["Name"]
            service_info = scenario["Description"]
            info += f"➣ {name.upper()}\n{service_info}\n"
        service_statuses += f"{box(info.strip())}\n"

    for i in title_svc["Category"]:
        service_name = i["Name"]
        status = i["Status"]

        sname = status["Name"]
        if sname != "Impacted":
            continue

        # Get status emoji based on status ID
        sid = status["Id"]
        if sid == "1":
            indicator = up
        elif sid == "2":
            indicator = down
        else:
            indicator = limited

        service_statuses += f"**{indicator} {service_name}**\n"
        info = ""
        scenarios = i["Scenarios"]["Scenario"]
        for scenario in scenarios:
            if scenario["Status"]["Name"] != "Impacted":
                continue

            name = scenario["Name"]
            service_info = scenario["Description"]
            info += f"➣ {name.upper()}\n{service_info}\n"
        service_statuses += f"{box(info.strip())}\n"

    grammar = f"{out} {'service is' if out == 1 else 'services are'}"
    title = f"{grammar} affected at this time"
    text = f"{limited} Limited\n{down} Major outage"

    desc = f"{text}\n\n{service_statuses.strip()}"

    if len(desc) > 4096:
        embeds = []
        for p in pagify(desc):
            embed = discord.Embed(title=title, description=p, color=discord.Color.orange())
            embed.set_footer(text=f"Last Updated: {last_updated}")
            embeds.append(embed)
            return embeds

    embed = discord.Embed(title=title, description=desc, color=discord.Color.orange())
    embed.set_footer(text=f"Last Updated: {last_updated}")
    return [embed]


# Format games with gold products
def gwg_embeds(products):
    embeds = []
    count = 1
    for game in products:
        dev_name = game["localized_properties"][0]["developer_name"]
        game_name = game["localized_properties"][0]["product_title"]
        desc = game["localized_properties"][0]["short_description"]
        for image in game["localized_properties"][0]["images"]:
            if image["image_purpose"] == "BoxArt":
                icon = f"https:{image['uri']}"
                break
        else:
            for image in game["localized_properties"][0]["images"]:
                if image["image_purpose"] != "Screenshot":
                    icon = f"https:{image['uri']}"
                    break
            else:
                icon = None

        categories = ""
        for category in game["properties"]["categories"]:
            categories += f"{category}\n"
        if categories == "":
            categories = "--"
        price = game["display_sku_availabilities"][0]["availabilities"][0]["order_management_data"]["price"][
            "list_price"
        ]
        release_date = game["display_sku_availabilities"][0]["availabilities"][0]["properties"]["original_release_date"]
        timestamp = fix_timestamp(release_date).strftime("%m/%d/%Y")
        embed = discord.Embed(title=f"{game_name}", description=f"**Description**\n{box(desc)}")
        embed.add_field(
            name="Info",
            value=f"`Developer:` {dev_name}\n`Release Date:` {timestamp}\n`Price:` ~~${price}~~ FREE",
            inline=False,
        )
        embed.add_field(name="Categories", value=categories)
        embed.set_image(url=icon)
        embed.set_footer(text=f"Page {count}/{len(products)}")
        embeds.append(embed)
        count += 1
    return embeds


# Format most played list
def mostplayed(data, gt):
    embeds = []
    sorted_playtime = sorted(data.items(), key=lambda x: x[1], reverse=True)

    total_playtime = 0
    for game in sorted_playtime:
        total_playtime += int(game[1])

    pages = math.ceil(len(sorted_playtime) / 10)
    start = 0
    stop = 10
    for p in range(int(pages)):
        mostplayedlist = ""
        if stop > len(sorted_playtime):
            stop = len(sorted_playtime)

        table = []
        for i in range(start, stop, 1):
            game = sorted_playtime[i][0]
            minutes_played = int(sorted_playtime[i][1])
            tstring = time_formatter(minutes_played * 60)
            table.append([i + 1, tstring, game])

        mostplayedlist += tabulate.tabulate(table, tablefmt="presto")
        start += 10
        stop += 10
        embed = discord.Embed(
            title=f"{gt}'s Most Played Games",
            description=box(mostplayedlist, lang="python"),
            color=discord.Color.random(),
        )
        hours, minutes = divmod(total_playtime, 60)
        days, hours = divmod(hours, 24)
        embed.set_footer(text=f"Page {p + 1}/{int(pages)} | Total Playtime: {days}d {hours}h {minutes}m")
        embeds.append(embed)
    return embeds


# Formatting for game stats api call
def stats_api_format(token, title_id, xuid):
    header = {
        "x-xbl-contract-version": "2",
        "Authorization": token,
        "Accept": "application/json",
        "Accept-Language": "en-US",
        "Content-Type": "application/json",
    }
    url = "https://userstats.xboxlive.com/batch"
    payload = json.dumps(
        {
            "arrangebyfield": "xuid",
            "xuids": [xuid],
            "groups": [{"name": "Hero", "titleId": title_id}],
            "stats": [{"name": "MinutesPlayed", "titleId": title_id}],
        }
    )
    return url, header, payload
