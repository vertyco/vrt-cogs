import aiohttp
import discord
import asyncio
import re
import json

from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box
from math import remainder


class XTools(commands.Cog):
    """
    Cool Tools for Xbox
    """

    __author__ = "Vertyco"
    __version__ = "2.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117117117, force_registration=True)
        default_guild = {"users": {}}
        self.config.register_guild(**default_guild)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    # Master API Requests function for xbl.io
    async def get_req_xblio(self, ctx, command):
        xblio_api = await self.bot.get_shared_api_tokens("xbl.io")
        if xblio_api.get("api_key") is None:
            instructions = discord.Embed(
                title="XBL.IO API key not set",
                description="Before you can use this cog, you must complete the following steps:",
                color=await ctx.embed_color()
            )
            instructions.add_field(
                name="1. Sign in with your Microsoft account",
                value="Visit https://xbl.io/ and login with your account by clicking `Login with Xbox Live`."
                      "If you don't have an account go ahead and create one.",
                inline=False
            )
            instructions.add_field(
                name="2. Get your API key",
                value="After signing in, on your profile page there will be an area named `API Keys`, click `Create+`.",
                inline=False
            )
            instructions.add_field(
                name="3. Set your API key on your bot",
                value=f"Use `{ctx.clean_prefix}set api xbl.io api_key,<key>` to set the API key you created.",
                inline=False
            )
            return await ctx.send(embed=instructions)

        async with self.session.get(command, headers={"X-Authorization": xblio_api["api_key"]}) as resp:
            data = await resp.json(content_type=None)
            status = resp.status
            remaining = resp.headers['X-RateLimit-Remaining']
            ratelimit = resp.headers['X-RateLimit-Limit']
            return data, status, remaining, ratelimit

    # Master API Requests function for xapi.us
    async def get_req_xapi(self, ctx, command):
        xapi_api = await self.bot.get_shared_api_tokens("xapi.us")
        if xapi_api.get("api_key") is None:
            instructions = discord.Embed(
                title="XAPI.US API key not set",
                description="Before you can use this command(which uses both xbl.io and xapi.us),"
                            " you must complete the following steps:",
                color=await ctx.embed_color()
            )
            instructions.add_field(
                name="1. Create your Xapi acccount",
                value="Visit https://xapi.us/ and create a free account by clicking `Sign in`.",
                inline=False
            )
            instructions.add_field(
                name="2. Sign in with your Microsoft account",
                value="After verifying your email and signing in, you will go to your profile page and click:"
                      "`Sign into Xbox LIVE`.",
                inline=False
            )
            instructions.add_field(
                name="3. Get your API key from your profile page",
                value="After signing in with your Microsoft account, Your key should be ready to use.",
                inline=False
            )
            instructions.add_field(
                name="4. Set your API key on your bot",
                value=f"Use `{ctx.clean_prefix}set api xapi.us api_key,<key>` to set the API key you created.",
                inline=False
            )
            return await ctx.send(embed=instructions)

        async with self.session.get(command, headers={"X-Auth": xapi_api["api_key"]}) as resp:
            try:
                data = await resp.json()
                status = resp.status
                remaining = resp.headers['X-RateLimit-Remaining']
                ratelimit = resp.headers['X-RateLimit-Limit']
            except aiohttp.ContentTypeError:
                ctx.send("The API failed to pull the data. Please try again.")
            return data, status, remaining, ratelimit

    # Helper function for trying to get xuid
    async def get_xuid(self, ctx, gamertag):
        if gamertag is not None:
            gamertag_req = f"https://xbl.io/api/v2/friends/search?gt={gamertag}"
            async with ctx.typing():
                data, _, _, _ = await self.get_req_xblio(ctx, gamertag_req)
            try:
                xuid, xuid_str, gs, tier, rep, pfp, bio = await self.profile_format(data)
                return xuid, xuid_str, gs, tier, rep, pfp, bio, gamertag
            except KeyError:
                embed = discord.Embed(title=":warning:Error:warning:",
                                      color=discord.Color.dark_red(),
                                      description="Gamertag is invalid or does not exist.")
                return await ctx.send(embed=embed)
        else:
            data = await self.config.guild(ctx.guild).users()
            if data:
                for user in data:
                    if int(user) == int(ctx.author.id):
                        gamertag = data[user][0]
                        gt_request = f"https://xbl.io/api/v2/friends/search?gt={gamertag}"
                        async with ctx.typing():
                            data, _, _, _ = await self.get_req_xblio(ctx, gt_request)
                        xuid, xuid_str, gs, tier, rep, pfp, bio = await self.profile_format(data)
                        return xuid, xuid_str, gs, tier, rep, pfp, bio, gamertag

    # Helper function for formatting xbox timestamps
    async def time_format(self, timestamp_raw):
        regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
        if timestamp_raw:
            list = re.findall(regex, timestamp_raw)
            parts = list[0]
            timestamp_formatted = f"{parts[1]}-{parts[2]}-{parts[0]} at {parts[3]} GMT"
            return timestamp_formatted

    # Helper function for formatting profile data
    async def profile_format(self, data):
        xuid, xuid_str, gs, tier, rep, pfp, bio = None, None, None, None, None, None, None
        for user in data["profileUsers"]:
            xuid = user['id']
            xuid_str = f"**XUID:** {user['id']}"
            for setting in user["settings"]:
                if setting["id"] == "Gamerscore":
                    gsformat = "{:,}".format(int(setting['value']))
                    gs = f"**Gamerscore:** {gsformat}"
                if setting["id"] == "AccountTier":
                    tier = f"**AccountTier:** {setting['value']}"
                if setting["id"] == "XboxOneRep":
                    rep = f"**Reputation:** {setting['value']}"
                if setting["id"] == "GameDisplayPicRaw":
                    pfp = (setting['value'])
                if setting["id"] == "Bio":
                    bio = (setting['value'])
        return xuid, xuid_str, gs, tier, rep, pfp, bio

    # Helper function for formatting presence data
    async def presence_format(self, data):
        state = f"{data['state']}"
        if "lastSeen" in data:
            game = data['lastSeen']['titleName']
            device = data['lastSeen']['deviceType']
            raw_time = data['lastSeen']['timestamp']
        elif "devices" in data:
            device = data["devices"][0]["type"]
            raw_time = data["devices"][0]["titles"][0]["lastModified"]
            gamelist = ""
            for game in data["devices"][0]["titles"]:
                game = game["name"]
                gamelist += f"\n{game}"
            game = gamelist
        else:
            game = None
            device = None
            raw_time = None

        if device == "Durango":
            device = "1st Gen XboxOne"
        if device == "Scarlett":
            device = "Xbox Series S"
        if device == "WindowsOneCore":
            device = "Windows"

        return state, device, game, raw_time

    # Embed helper function for reaction menu
    async def embed_handler(self, cur_page, pages, gamertag, data, type):
        if type == "friends":
            gsformat = "{:,}".format(int(data[cur_page - 1]['gamerScore']))
            status = data[cur_page - 1]['presenceState']
            activity = data[cur_page - 1]['presenceText']
            embed = discord.Embed(
                title=f"**{gamertag}**'s Profile",
                color=discord.Color.green(),
                description=str(f"**XIUD:** {data[cur_page - 1]['xuid']}\n"
                                f"**Status:** {status}\n"
                                f"**Activity:** {activity if status == 'Online' else None}\n"
                                f"**Gamerscore:** {gsformat}\n"
                                f"**Player Rep:** {data[cur_page - 1]['xboxOneRep']}\n")
            )
            embed.set_image(url=data[cur_page - 1]["displayPicRaw"])
            embed.set_footer(text=f"Page {cur_page}/{pages}")
            return embed
        if type == "screenshots":
            timestamp = await self.time_format(data[cur_page - 1]["date"])
            embed = discord.Embed(
                title=f"{gamertag}'s Screenshots",
                color=discord.Color.green(),
                description=str(f"**Name:** {data[cur_page - 1]['screenshotName']}\n"
                                f"**Caption:** {data[cur_page - 1]['shortDescription']}\n"
                                f"**Views:** {data[cur_page - 1]['viewCount']}\n"
                                f"**Game:** {data[cur_page - 1]['itemText']}\n"
                                f"**Date Taken:** {timestamp}")
            )
            embed.set_image(url=data[cur_page - 1]["itemImage"])
            embed.set_footer(text=f"Page {cur_page}/{pages}")
            return embed
        if type == "clips":
            timestamp = await self.time_format(data[cur_page - 1]["dateRecorded"])
            duration = data[cur_page - 1]['durationInSeconds']
            min, sec = divmod(duration, 60)
            embed = discord.Embed(
                title=f"{gamertag}'s Game Clips",
                color=discord.Color.green(),
                description=str(f"**Name:** {data[cur_page - 1]['clipName']}\n"
                                f"**Caption:** {data[cur_page - 1]['clipCaption']}\n"
                                f"**Views:** {data[cur_page - 1]['viewCount']}\n"
                                f"**Game:** {data[cur_page - 1]['contentTitle']}\n"
                                f"**Date Taken:** {timestamp}\n"
                                f"**Duration:** {min}:{sec}\n\n"
                                f"[CLICK HERE TO WATCH]({data[cur_page - 1]['downloadUri']})\n\n")
            )
            embed.set_image(url=data[cur_page - 1]["clipThumbnail"])
            embed.set_thumbnail(url=data[cur_page - 1]["contentImageUri"])
            embed.set_footer(text=f"Page {cur_page}/{pages}")
            return embed
        if type == "games":
            timestamp = await self.time_format(data["titles"][cur_page - 1]["titleHistory"]["lastTimePlayed"])
            gs = data['titles'][cur_page - 1]['achievement']['currentGamerscore']
            totalgs = data['titles'][cur_page - 1]['achievement']['totalGamerscore']
            embed = discord.Embed(
                title=f"{gamertag}'s Games",
                color=discord.Color.green(),
                description=str(f"**Game:** {data['titles'][cur_page - 1]['name']}\n"
                                f"**Platform:** {data['titles'][cur_page - 1]['devices'][0]}\n"
                                f"**Achievements Earned:** "
                                f"{data['titles'][cur_page - 1]['achievement']['currentAchievements']}\n"
                                f"**Gamerscore:** {gs}/{totalgs}\n"
                                f"**Progress:** {data['titles'][cur_page - 1]['achievement']['progressPercentage']}%\n"
                                f"**Last Played:** {timestamp}\n")
            )
            if data['titles'][cur_page - 1]['displayImage'] is not None:
                embed.set_thumbnail(url=data['titles'][cur_page - 1]['displayImage'])
            embed.set_footer(text=f"Page {cur_page}/{pages}")
            return embed
        if type == "achievements":
            stats = []
            status = False
            completed = False
            days, hours, minutes = 0, 0, 0
            if not data["a"]["achievements"]:
                embed = discord.Embed(title="No Achievements",
                                      color=discord.Color.green(),
                                      description=f"This game has no achievements for it.")
                return embed
            if data["s"]["statlistscollection"]:
                time_played = data["s"]["statlistscollection"][0]["stats"][0]["value"]
                days, minutes = divmod(time_played, 1440)
                hours, minutes = divmod(minutes, 60)
            if data["s"]["groups"][0]["statlistscollection"]:
                stats = data["s"]["groups"][0]["statlistscollection"][0]["stats"]

            time = data["a"]["achievements"][cur_page - 1]["progression"]["timeUnlocked"]
            timestamp = await self.time_format(time)
            if data['a']['achievements'][cur_page - 1]['progressState'] == "Achieved":
                status = True
                completed = f"Completed on: {timestamp}\n"
            old_page = data["cur_page"]
            title = data['old_data']['titles'][old_page - 1]['name']
            embed = discord.Embed(
                title=f"{gamertag}'s achievements for {title}",
                color=discord.Color.green())

            for items in stats:
                if "value" in items:
                    if items["groupproperties"]["DisplayFormat"] == "Percentage":
                        item = f"{int(items['value'])}%"
                    else:
                        item = items['value']
                    embed.add_field(name=items["properties"]["DisplayName"], value=item)
            embed.add_field(name="Achievement Details",
                            value=box(f"Name: {data['a']['achievements'][cur_page - 1]['name']}\n"
                                      f"Description: {data['a']['achievements'][cur_page - 1]['lockedDescription']}\n"
                                      f"Status: {data['a']['achievements'][cur_page - 1]['progressState']}\n"
                                      f"{completed if status is True else ''}"
                                      f"Gamerscore: {data['a']['achievements'][cur_page - 1]['rewards'][0]['value']}"),
                            inline=False)
            if data['a']['achievements'][cur_page - 1]['mediaAssets'][0]['url'] is not None:
                embed.set_image(url=data['a']['achievements'][cur_page - 1]['mediaAssets'][0]['url'])
            embed.set_footer(text=f"Page {cur_page}/{pages} | Time Played: {days}d {hours}h {minutes}m")
            return embed

    # Reaction menu logic for all commands
    async def basic_menu(self, ctx, gamertag, xuid, data, pages, type, cur_page=None):
        if type == "friends":
            if pages == 0:
                embed = discord.Embed(title="Friend List Empty",
                                      description=f"Looks like **{gamertag}** has no friends. :smiling_face_with_tear:")
                return await ctx.send(embed=embed)

        if not cur_page:
            cur_page = 1
        embed = await self.embed_handler(cur_page, pages, gamertag, data, type)
        message = await ctx.send(embed=embed)

        await message.add_reaction("⏪")
        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")
        await message.add_reaction("⏩")
        if type == "games":
            await message.add_reaction("⬆")
        if type == "achievements":
            await message.add_reaction("⬇")

        def check(reaction, user):
            if type == "games":
                return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩", "⬆"]
            elif type == "achievements":
                return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩", "⬇"]
            else:
                return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)

                if str(reaction.emoji) == "⏩" and cur_page + 10 <= pages:
                    cur_page += 10
                    embed = await self.embed_handler(cur_page, pages, gamertag, data, type)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "▶️" and cur_page != pages:
                    cur_page += 1
                    embed = await self.embed_handler(cur_page, pages, gamertag, data, type)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⏪" and cur_page - 10 >= 1:
                    cur_page -= 10
                    embed = await self.embed_handler(cur_page, pages, gamertag, data, type)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    embed = await self.embed_handler(cur_page, pages, gamertag, data, type)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return await ctx.send(embed=discord.Embed(description="Menu closed."))

                elif type == "games":
                    if str(reaction.emoji) == "⬆":
                        cached_data = data
                        cached_cur_page = cur_page
                        titleid = data["titles"][cur_page - 1]["titleId"]
                        achievement_req = f"https://xbl.io/api/v2/achievements/player/{xuid}/title/{titleid}"
                        stats_req = f"https://xapi.us/v2/{xuid}/game-stats/{titleid}"
                        async with ctx.typing():
                            achievements, _, _, _ = await self.get_req_xblio(ctx, achievement_req)
                            stats, _, _, _ = await self.get_req_xapi(ctx, stats_req)
                            data = {
                                "old_data": cached_data,
                                "cur_page": cached_cur_page,
                                "a": achievements,
                                "s": stats,
                            }
                            await message.delete()
                        pages = len(data["a"]["achievements"])
                        return await self.basic_menu(ctx, gamertag, xuid, data, pages, "achievements")

                elif type == "achievements":
                    if str(reaction.emoji) == "⬇":
                        await message.delete()
                        cur_page = data["cur_page"]
                        data = data["old_data"]
                        await self.basic_menu(ctx, gamertag, xuid, data, pages, "games", cur_page)

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                await message.clear_reactions()
                return await ctx.send(embed=discord.Embed(description="Menu timed out."))

    @commands.group()
    async def xtools(self, ctx):
        """XTools base command"""
        pass

    @xtools.command()
    async def setgt(self, ctx, *, gamertag):
        """Set your Gamertag to use commands without entering it"""
        async with ctx.typing():
            gamertag_req = f"https://xbl.io/api/v2/friends/search?gt={gamertag}"
            data, _, _, _ = await self.get_req_xblio(ctx, gamertag_req)
            try:
                for user in data["profileUsers"]:
                    xuid = user['id']
            except KeyError:
                embed = discord.Embed(title="Error",
                                      color=discord.Color.dark_red(),
                                      description="Gamertag is invalid or does not exist.")
                return await ctx.send(embed=embed)
        async with self.config.guild(ctx.guild).users() as user:
            user[ctx.author.id] = [gamertag, xuid]
            embed = discord.Embed(title="Success",
                                  color=discord.Color.green(),
                                  description=f"Gamertag set to `{gamertag}`")
            return await ctx.send(embed=embed)

    @xtools.command()
    async def status(self, ctx, member: discord.Member = None):
        """Check the Gamertag you have registered"""
        member = ctx.author if member is None else member
        data = await self.config.guild(ctx.guild).users()
        if data:
            for user in data:
                if int(user) == int(member.id):
                    embed = discord.Embed(description=f"**GT:** `{data[user][0]}`\n**XUID:** `{data[user][1]}`")
                    await ctx.send(embed=embed)
                else:
                    embed = discord.Embed(description=f"No Gamertag set for **{member.name}**!\n"
                                                      f"Set a Gamertag with `{ctx.clean.prefix}xtools setgt <Gamertag>`")
                    return await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description=f"No Gamertag set for **{member.name}**!\n"
                                              f"Set a Gamertag with `{ctx.prefix}xtools setgt <Gamertag>`")
            return await ctx.send(embed=embed)

    @xtools.command()
    async def profile(self, ctx, *, gamertag=None):
        """Get your profile information"""
        try:
            xuid, xuid_str, gs, tier, rep, pfp, bio, gamertag = await self.get_xuid(ctx, gamertag)
        except Exception as e:
            if "NoneType" in str(e):
                embed = discord.Embed(description=f"You haven't set a Gamertag for yourself yet!")
                return await ctx.send(embed=embed)
            else:
                print(f"ERROR: {e}")
                return

        presence_req = f"https://xbl.io/api/v2/{xuid}/presence"
        data, status, remaining, ratelimit = await self.get_req_xblio(ctx, presence_req)
        data = data[0]
        state, device, game, raw_time = await self.presence_format(data)
        timestamp = await self.time_format(raw_time)
        color = discord.Color.green() if status == 200 else discord.Color.dark_red()
        stat = "Good" if status == 200 else "Failed"

        embed = discord.Embed(
            title=f"**{gamertag}**'s Profile ({state})",
            color=color,
            description=f"{gs}\n{tier}\n{rep}\n{xuid_str}")
        embed.set_image(url=pfp)
        if "lastSeen" in data or "devices" in data:
            embed.add_field(name="Last Seen",
                            value=f"**Device:** {device}\n**Activity:** {game}\n**Time:** {timestamp}",
                            inline=False)
        if bio != "":
            embed.add_field(name="Bio", value=box(bio))
        embed.add_field(name="API Status",
                        value=f"API: {stat}\nRateLimit: {ratelimit}/hour\nRemaining: {remaining}",
                        inline=False)
        return await ctx.send(embed=embed)

    @xtools.command()
    async def friends(self, ctx, *, gamertag=None):
        """Get yours or a Gamertag's friends list"""
        try:
            xuid, _, _, _, _, _, _, gamertag = await self.get_xuid(ctx, gamertag)
        except Exception as e:
            if "NoneType" in str(e):
                embed = discord.Embed(description=f"You haven't set a Gamertag for yourself yet!")
                return await ctx.send(embed=embed)

        friends_req = f"https://xbl.io/api/v2/friends?xuid={xuid}"
        data, _, _, _ = await self.get_req_xblio(ctx, friends_req)

        if data:
            pages = len(data["people"])
            return await self.basic_menu(ctx, gamertag, xuid, data["people"], pages, "friends")
        else:
            embed = discord.Embed(title="Friend List Unavailable",
                                  description=f"**{gamertag}** might have their profile set to private.")
            return await ctx.send(embed=embed)

    @xtools.command()
    async def screenshots(self, ctx, *, gamertag=None):
        """Get a yours or a Gamertag's screenshot gallery"""
        try:
            xuid, _, _, _, _, _, _, gamertag = await self.get_xuid(ctx, gamertag)
        except Exception as e:
            if "NoneType" in str(e):
                embed = discord.Embed(description=f"You haven't set a Gamertag for yourself yet!")
                return await ctx.send(embed=embed)
        screenshot_req = f"https://xapi.us/v2/{xuid}/alternative-screenshots"
        data, _, _, _ = await self.get_req_xapi(ctx, screenshot_req)

        if data:
            pages = len(data)
            return await self.basic_menu(ctx, gamertag, xuid, data, pages, "screenshots")
        else:
            embed = discord.Embed(title="No Screenshots",
                                  description=f"**{gamertag}** has no screenshots available.")
            return await ctx.send(embed=embed)

    @xtools.command()
    async def clips(self, ctx, *, gamertag=None):
        """Get yours or a Gamertag's recorded game clips"""
        try:
            xuid, _, _, _, _, _, _, gamertag = await self.get_xuid(ctx, gamertag)
        except Exception as e:
            if "NoneType" in str(e):
                embed = discord.Embed(description=f"You haven't set a Gamertag for yourself yet!")
                return await ctx.send(embed=embed)
        gameclip_req = f"https://xapi.us/v2/{xuid}/alternative-game-clips"
        data, _, _, _ = await self.get_req_xapi(ctx, gameclip_req)

        if data:
            pages = len(data)
            return await self.basic_menu(ctx, gamertag, xuid, data, pages, "clips")
        else:
            embed = discord.Embed(title="No Clips",
                                  description=f"**{gamertag}** has no clips available.")
            return await ctx.send(embed=embed)

    @xtools.command()
    async def games(self, ctx, *, gamertag=None):
        """View details about games you or a Gamertag have played"""
        try:
            xuid, _, _, _, _, _, _, gamertag = await self.get_xuid(ctx, gamertag)
        except Exception as e:
            if "NoneType" in str(e):
                embed = discord.Embed(description=f"You haven't set a Gamertag for yourself yet!")
                return await ctx.send(embed=embed)
        game_req = f"https://xbl.io/api/v2/achievements/player/{xuid}"
        data, _, _, _ = await self.get_req_xblio(ctx, game_req)

        titles = []
        if data:
            for game in data["titles"]:
                if "Win32" not in game["devices"]:
                    titles.append(game)
                    continue
            pages = len(titles)
            data = {
                "xuid": xuid,
                "titles": titles
            }
            await self.basic_menu(ctx, gamertag, xuid, data, pages, "games")
        else:
            embed = discord.Embed(title="No Games",
                                  description=f"**{gamertag}** has no games available.")
            return await ctx.send(embed=embed)

