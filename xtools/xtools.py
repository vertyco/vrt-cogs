from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box
from math import remainder
import aiohttp
import discord
import asyncio
import re


class XTools(commands.Cog):
    """
    Tools for Xbox
    """

    __author__ = "Vertyco"
    __version__ = "1.4.15"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


    # Requests for xbl.io
    async def get_req_xblio(self, ctx, command):
        xblio_api = await self.bot.get_shared_api_tokens("xbl.io")

        async with self.session.get(f'{command}', headers={"X-Authorization": xblio_api["api_key"]}) as resp:
            try:
                data = await resp.json()
                status = resp.status
                remaining = resp.headers['X-RateLimit-Remaining']
                ratelimit = resp.headers['X-RateLimit-Limit']
            except aiohttp.ContentTypeError:
                ctx.send("The API failed to pull the data. Please try again.")

            return data, status, remaining, ratelimit

    # Requests for xapi.us
    async def get_req_xapi(self, ctx, command):
        xapi_api = await self.bot.get_shared_api_tokens("xapi.us")

        async with self.session.get(f'{command}', headers={"X-Auth": xapi_api["api_key"]}) as resp:
            try:
                data = await resp.json()
                status = resp.status
                remaining = resp.headers['X-RateLimit-Remaining']
                ratelimit = resp.headers['X-RateLimit-Limit']
            except aiohttp.ContentTypeError:
                ctx.send("The API failed to pull the data. Please try again.")

            return data, status, remaining, ratelimit

    # Pulls profile data and formats for an embed
    # Purposely left out the 'real name' and 'location' data for privacy reasons,
    # Since some people have their profile info public and may not know it
    @commands.command()
    async def xprofile(self, ctx, *, gtag):
        """Pull your profile info from Xbox"""
        xblio_api = await self.bot.get_shared_api_tokens("xbl.io")
        if xblio_api.get("api_key") is None:
            await ctx.send(f"This cog needs a valid API key with `{ctx.clean_prefix}set api xbl.io api_key,<key>`"
                           f" before you can use this command.")
            await ctx.send("To obtain a key, visit https://xbl.io/ and register your microsoft account.")
            return
        async with ctx.typing():
            gtrequest = f"https://xbl.io/api/v2/friends/search?gt={gtag}"
            data, _, _, _ = await self.get_req_xblio(ctx, gtrequest)
            try:
                for user in data["profileUsers"]:
                    xbox_id = user['id']
                    xuid = f"**XUID:** {user['id']}"
                    for setting in user["settings"]:
                        if setting["id"] == "Gamerscore":
                            gs = f"**Gamerscore:** {setting['value']}"
                        if setting["id"] == "AccountTier":
                            tier = f"**AccountTier:** {setting['value']}"
                        if setting["id"] == "XboxOneRep":
                            rep = f"**Reputation:** {setting['value']}"
                        if setting["id"] == "GameDisplayPicRaw":
                            pfp = (setting['value'])
                        if setting["id"] == "Bio":
                            bio = (setting['value'])
            except KeyError:
                return await ctx.send("Invalid Gamertag, please try again.")
                # command calls the thing and does the stuff
            presence = f"https://xbl.io/api/v2/{xbox_id}/presence"
            data, status, remaining, ratelimit = await self.get_req_xblio(ctx, presence)
            data = data[0]
            state = f"{data['state']}"

            if "lastSeen" in data:
                device = data['lastSeen']['deviceType']
                if device == "Durango":
                    device = "1st Gen XboxOne"
                if device == "Scarlett":
                    device = "Xbox Series S"
                if device == "WindowsOneCore":
                    device = "Windows"
                game = data['lastSeen']['titleName']
                raw_time = data['lastSeen']['timestamp']
            if "devices" in data:
                gamelist = ""
                device = data["devices"][0]["type"]
                if device == "Durango":
                    device = "1st Gen XboxOne"
                if device == "Scarlett":
                    device = "Xbox Series S"
                if device == "WindowsOneCore":
                    device = "Windows"
                for game in data["devices"][0]["titles"]:
                    game = game["name"]
                    gamelist += f"\n{game}"
                game = gamelist
                raw_time = data["devices"][0]["titles"][0]["lastModified"]

            if "lastSeen" in data or "devices" in data:
                time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                timestamp = re.findall(time_regex, raw_time)
                timestamp = timestamp[0]
                timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]}"

            color = discord.Color.green() if status == 200 else discord.Color.dark_red()
            stat = "Good" if status == 200 else "Failed"
            embed = discord.Embed(
                title=f"**{gtag}**'s Profile ({state})",
                color=color,
                description=str(f"{gs}\n{tier}\n{rep}\n{xuid}"),
            )
            embed.set_image(url=pfp)
            if "lastSeen" in data or "devices" in data:
                embed.add_field(name="Last Seen",
                                value=f"**Device:** {device}\n**Activity:** {game}\n**Time:** {timestamp} GMT",
                                inline=False
                                )
            if bio != "":
                embed.add_field(name="Bio", value=box(bio))
            embed.add_field(name="API Status",
                            value=f"API: {stat}\nRateLimit: {ratelimit}/hour\nRemaining: {remaining}",
                            inline=False
                            )
            await ctx.send(embed=embed)

    # Get friends list of a gamertag in an interactive menu
    @commands.command()
    async def getfriends(self, ctx, *, gtag):
        """Pull a Gamertag's friends list"""
        xblio_api = await self.bot.get_shared_api_tokens("xbl.io")
        if xblio_api.get("api_key") is None:
            await ctx.send(f"This cog needs a valid API key with `{ctx.clean_prefix}set api xbl.io api_key,<key>`"
                           f" before you can use this command.")
            await ctx.send("To obtain a key, visit https://xbl.io/ and register your microsoft account.")
            return
        async with ctx.typing():
            gtrequest = f"https://xbl.io/api/v2/friends/search?gt={gtag}"
            data, status, remaining, ratelimit = await self.get_req_xblio(ctx, gtrequest)
            try:
                for user in data["profileUsers"]:
                    xuid = user['id']
            except KeyError:
                return await ctx.send("Invalid Gamertag, please try again.")
            friendsrequest = f"https://xbl.io/api/v2/friends?xuid={xuid}"
            data, status, remaining, ratelimit = await self.get_req_xblio(ctx, friendsrequest)

            pages = 0
            for friend in data["people"]:
                if friend:
                    pages += 1
            await self.pagify_friends(ctx, data["people"], pages)

    async def pagify_friends(self, ctx, content, pages):
        cur_page = 1
        embed = discord.Embed(
            title=f"**{content[cur_page - 1]['displayName']}**'s Profile",
            color=discord.Color.green(),
            description=str(f"**XIUD:** {content[cur_page - 1]['xuid']}\n"
                            f"**Status:** {content[cur_page - 1]['presenceState']}\n"
                            f"**Activity:** {content[cur_page - 1]['presenceText']}\n"
                            f"**Gamerscore:** {content[cur_page - 1]['gamerScore']}\n"
                            f"**Player Rep:** {content[cur_page - 1]['xboxOneRep']}\n")
        )
        embed.set_image(url=content[cur_page - 1]["displayPicRaw"])
        embed.set_footer(text=f"Page {cur_page}/{pages}")
        message = await ctx.send(embed=embed)

        await message.add_reaction("⏪")
        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")
        await message.add_reaction("⏩")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                # waiting for a reaction to be added - times out after x seconds

                if str(reaction.emoji) == "⏩" and cur_page + 10 <= pages:
                    cur_page += 10
                    embed = discord.Embed(
                        title=f"**{content[cur_page - 1]['displayName']}**'s Profile",
                        color=discord.Color.green(),
                        description=str(f"**XIUD:** {content[cur_page - 1]['xuid']}\n"
                                        f"**Status:** {content[cur_page - 1]['presenceState']}\n"
                                        f"**Activity:** {content[cur_page - 1]['presenceText']}\n"
                                        f"**Gamerscore:** {content[cur_page - 1]['gamerScore']}\n"
                                        f"**Player Rep:** {content[cur_page - 1]['xboxOneRep']}\n"),
                    )
                    embed.set_image(url=content[cur_page - 1]["displayPicRaw"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "▶️" and cur_page != pages:
                    cur_page += 1
                    embed = discord.Embed(
                        title=f"**{content[cur_page - 1]['displayName']}**'s Profile",
                        color=discord.Color.green(),
                        description=str(f"**XIUD:** {content[cur_page - 1]['xuid']}\n"
                                        f"**Status:** {content[cur_page - 1]['presenceState']}\n"
                                        f"**Activity:** {content[cur_page - 1]['presenceText']}\n"
                                        f"**Gamerscore:** {content[cur_page - 1]['gamerScore']}\n"
                                        f"**Player Rep:** {content[cur_page - 1]['xboxOneRep']}\n"),
                    )
                    embed.set_image(url=content[cur_page - 1]["displayPicRaw"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⏪" and cur_page - 10 >= 1:
                    cur_page -= 10
                    embed = discord.Embed(
                        title=f"**{content[cur_page - 1]['displayName']}**'s Profile",
                        color=discord.Color.green(),
                        description=str(f"**XIUD:** {content[cur_page - 1]['xuid']}\n"
                                        f"**Status:** {content[cur_page - 1]['presenceState']}\n"
                                        f"**Activity:** {content[cur_page - 1]['presenceText']}\n"
                                        f"**Gamerscore:** {content[cur_page - 1]['gamerScore']}\n"
                                        f"**Player Rep:** {content[cur_page - 1]['xboxOneRep']}\n"),
                    )
                    embed.set_image(url=content[cur_page - 1]["displayPicRaw"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    embed = discord.Embed(
                        title=f"**{content[cur_page - 1]['displayName']}**'s Profile",
                        color=discord.Color.green(),
                        description=str(f"**XIUD:** {content[cur_page - 1]['xuid']}\n"
                                        f"**Status:** {content[cur_page - 1]['presenceState']}\n"
                                        f"**Activity:** {content[cur_page - 1]['presenceText']}\n"
                                        f"**Gamerscore:** {content[cur_page - 1]['gamerScore']}\n"
                                        f"**Player Rep:** {content[cur_page - 1]['xboxOneRep']}\n"),
                    )
                    embed.set_image(url=content[cur_page - 1]["displayPicRaw"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return

                else:
                    await message.remove_reaction(reaction, user)
                    # removes reactions if the user tries to go forward on the last page or
                    # backwards on the first page
            except asyncio.TimeoutError:
                await message.clear_reactions()
                return

    @commands.command()
    async def getscreenshots(self, ctx, *, gtag):
        """Pull up your screenshot gallery"""
        xapi_api = await self.bot.get_shared_api_tokens("xapi.us")
        if xapi_api.get("api_key") is None:
            await ctx.send(f"This cog needs a valid API key with `{ctx.clean_prefix}set api xapi.us api_key,<key>`"
                           f" before you can use this command.")
            await ctx.send("To obtain a key, visit https://xapi.us/ and register your microsoft account.")
            return
        async with ctx.typing():
            gtrequest = f"https://xbl.io/api/v2/friends/search?gt={gtag}"
            data, _, _, _ = await self.get_req_xblio(ctx, gtrequest)
            try:
                for user in data["profileUsers"]:
                    xuid = user['id']
            except KeyError:
                return await ctx.send("Invalid Gamertag, please try again.")
            screenshotrequest = f"https://xapi.us/v2/{xuid}/alternative-screenshots"
            data, status, remaining, ratelimit = await self.get_req_xapi(ctx, screenshotrequest)

            pages = 0
            for screenshot in data:
                if screenshot:
                    pages += 1
            await self.pagify_screenshots(ctx, data, pages, gtag)

    async def pagify_screenshots(self, ctx, content, pages, gtag):
        cur_page = 1
        time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
        timestamp = re.findall(time_regex, content[cur_page - 1]["date"])
        timestamp = timestamp[0]
        timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
        embed = discord.Embed(
            title=f"{gtag}'s Screenshots",
            color=discord.Color.green(),
            description=str(f"**Name:** {content[cur_page - 1]['screenshotName']}\n"
                            f"**Caption:** {content[cur_page - 1]['shortDescription']}\n"
                            f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                            f"**Game:** {content[cur_page - 1]['itemText']}\n"
                            f"**Date Taken:** {timestamp}")
        )
        embed.set_image(url=content[cur_page - 1]["itemImage"])
        embed.set_footer(text=f"Page {cur_page}/{pages}")
        message = await ctx.send(embed=embed)

        await message.add_reaction("⏪")
        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")
        await message.add_reaction("⏩")


        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                # waiting for a reaction to be added - times out after x seconds

                if str(reaction.emoji) == "⏩" and cur_page + 10 <= pages:
                    cur_page += 10
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["date"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    embed = discord.Embed(
                        title=f"{gtag}'s Screenshots",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['screenshotName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['shortDescription']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['itemText']}\n"
                                        f"**Date Taken:** {timestamp}")
                    )
                    embed.set_image(url=content[cur_page - 1]["itemImage"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "▶️" and cur_page != pages:
                    cur_page += 1
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["date"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    embed = discord.Embed(
                        title=f"{gtag}'s Screenshots",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['screenshotName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['shortDescription']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['itemText']}\n"
                                        f"**Date Taken:** {timestamp}")
                    )
                    embed.set_image(url=content[cur_page - 1]["itemImage"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["date"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    embed = discord.Embed(
                        title=f"{gtag}'s Screenshots",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['screenshotName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['shortDescription']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['itemText']}\n"
                                        f"**Date Taken:** {timestamp}")
                    )
                    embed.set_image(url=content[cur_page - 1]["itemImage"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⏪" and cur_page - 10 >= 1:
                    cur_page -= 10
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["date"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    embed = discord.Embed(
                        title=f"{gtag}'s Screenshots",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['screenshotName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['shortDescription']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['itemText']}\n"
                                        f"**Date Taken:** {timestamp}")
                    )
                    embed.set_image(url=content[cur_page - 1]["itemImage"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                await message.clear_reactions()
                return

    @commands.command()
    async def getgameclips(self, ctx, *, gtag):
        """Pull up your screenshot gallery"""
        xapi_api = await self.bot.get_shared_api_tokens("xapi.us")
        if xapi_api.get("api_key") is None:
            await ctx.send(f"This cog needs a valid API key with `{ctx.clean_prefix}set api xapi.us api_key,<key>`"
                           f" before you can use this command.")
            await ctx.send("To obtain a key, visit https://xapi.us/ and register your microsoft account.")
            return
        async with ctx.typing():
            gtrequest = f"https://xbl.io/api/v2/friends/search?gt={gtag}"
            data, _, _, _ = await self.get_req_xblio(ctx, gtrequest)
            try:
                for user in data["profileUsers"]:
                    xuid = user['id']
            except KeyError:
                return await ctx.send("Invalid Gamertag, please try again.")
            gameclipsrequest = f"https://xapi.us/v2/{xuid}/alternative-game-clips"
            data, status, remaining, ratelimit = await self.get_req_xapi(ctx, gameclipsrequest)

            pages = 0
            for screenshot in data:
                if screenshot:
                    pages += 1
            await self.pagify_gameclips(ctx, data, pages, gtag)

    async def pagify_gameclips(self, ctx, content, pages, gtag):
        cur_page = 1
        time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
        timestamp = re.findall(time_regex, content[cur_page - 1]["dateRecorded"])
        timestamp = timestamp[0]
        timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
        duration = content[cur_page - 1]['durationInSeconds']
        min, sec = divmod(duration, 60)
        embed = discord.Embed(
            title=f"{gtag}'s Game Clips",
            color=discord.Color.green(),
            description=str(f"**Name:** {content[cur_page - 1]['clipName']}\n"
                            f"**Caption:** {content[cur_page - 1]['clipCaption']}\n"
                            f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                            f"**Game:** {content[cur_page - 1]['contentTitle']}\n"
                            f"**Date Taken:** {timestamp}\n"
                            f"**Duration:** {min}:{sec}\n\n"
                            f"[CLICK HERE TO WATCH]({content[cur_page - 1]['downloadUri']})\n\n")
        )
        embed.set_image(url=content[cur_page - 1]["clipThumbnail"])
        embed.set_thumbnail(url=content[cur_page - 1]["contentImageUri"])
        embed.set_footer(text=f"Page {cur_page}/{pages}")
        message = await ctx.send(embed=embed)

        await message.add_reaction("⏪")
        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")
        await message.add_reaction("⏩")


        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⏪", "◀️", "❌", "▶️", "⏩"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)
                # waiting for a reaction to be added - times out after x seconds

                if str(reaction.emoji) == "⏩" and cur_page + 10 <= pages:
                    cur_page += 10
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["dateRecorded"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    duration = content[cur_page - 1]['durationInSeconds']
                    min, sec = divmod(duration, 60)
                    embed = discord.Embed(
                        title=f"{gtag}'s Game Clips",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['clipName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['clipCaption']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['contentTitle']}\n"
                                        f"**Date Recorded:** {timestamp}\n"
                                        f"**Duration:** {min}:{sec}\n\n"
                                        f"[CLICK HERE TO WATCH]({content[cur_page - 1]['downloadUri']})\n\n")
                    )
                    embed.set_image(url=content[cur_page - 1]["clipThumbnail"])
                    embed.set_thumbnail(url=content[cur_page - 1]["contentImageUri"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "▶️" and cur_page != pages:
                    cur_page += 1
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["dateRecorded"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    duration = content[cur_page - 1]['durationInSeconds']
                    min, sec = divmod(duration, 60)
                    embed = discord.Embed(
                        title=f"{gtag}'s Game Clips",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['clipName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['clipCaption']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['contentTitle']}\n"
                                        f"**Date Recorded:** {timestamp}\n"
                                        f"**Duration:** {min}:{sec}\n\n"
                                        f"[CLICK HERE TO WATCH]({content[cur_page - 1]['downloadUri']})\n\n")
                    )
                    embed.set_image(url=content[cur_page - 1]["clipThumbnail"])
                    embed.set_thumbnail(url=content[cur_page - 1]["contentImageUri"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["dateRecorded"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    duration = content[cur_page - 1]['durationInSeconds']
                    min, sec = divmod(duration, 60)
                    embed = discord.Embed(
                        title=f"{gtag}'s Game Clips",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['clipName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['clipCaption']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['contentTitle']}\n"
                                        f"**Date Recorded:** {timestamp}\n"
                                        f"**Duration:** {min}:{sec}\n\n"
                                        f"[CLICK HERE TO WATCH]({content[cur_page - 1]['downloadUri']})\n\n")
                    )
                    embed.set_image(url=content[cur_page - 1]["clipThumbnail"])
                    embed.set_thumbnail(url=content[cur_page - 1]["contentImageUri"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⏪" and cur_page - 10 >= 1:
                    cur_page -= 10
                    time_regex = r'(\d{4})-(\d\d)-(\d\d).(\d\d:\d\d)'
                    timestamp = re.findall(time_regex, content[cur_page - 1]["dateRecorded"])
                    timestamp = timestamp[0]
                    timestamp = f"{timestamp[1]}-{timestamp[2]}-{timestamp[0]} at {timestamp[3]} GMT"
                    duration = content[cur_page - 1]['durationInSeconds']
                    min, sec = divmod(duration, 60)
                    embed = discord.Embed(
                        title=f"{gtag}'s Game Clips",
                        color=discord.Color.green(),
                        description=str(f"**Name:** {content[cur_page - 1]['clipName']}\n"
                                        f"**Caption:** {content[cur_page - 1]['clipCaption']}\n"
                                        f"**Views:** {content[cur_page - 1]['viewCount']}\n"
                                        f"**Game:** {content[cur_page - 1]['contentTitle']}\n"
                                        f"**Date Recorded:** {timestamp}\n"
                                        f"**Duration:** {min}:{sec}\n\n"
                                        f"[CLICK HERE TO WATCH]({content[cur_page - 1]['downloadUri']})\n\n")
                    )
                    embed.set_image(url=content[cur_page - 1]["clipThumbnail"])
                    embed.set_thumbnail(url=content[cur_page - 1]["contentImageUri"])
                    embed.set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                await message.clear_reactions()
                return

