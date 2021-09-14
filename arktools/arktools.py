import aiohttp
import discord
import datetime
import pytz
import asyncio
import json
import math
import re

from redbot.core.utils.chat_formatting import box, pagify
from redbot.core import commands, Config
from discord.ext import tasks

import rcon
from rcon import Client
import unicodedata

import logging
log = logging.getLogger("red.vrt.arktools")

LOADING = "https://i.imgur.com/l3p6EMX.gif"
STATUS = "https://i.imgur.com/LPzCcgU.gif"
FAILED = "https://i.imgur.com/TcnAyVO.png"
SUCCESS = "https://i.imgur.com/NrLAEpq.gif"


class ArkTools(commands.Cog):
    """
    RCON/API tools and cross-chat for Ark: Survival Evolved!
    """
    __author__ = "Vertyco"
    __version__ = "1.8.42"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "welcomemsg": None,
            "statuschannel": None,
            "statusmessage": None,
            "masterlog": None,
            "fullaccessrole": None,
            "servertoserverchat": False,
            "autowelcome": False,
            "autofriend": False,
            "datalogs": False,
            "unfriendafter": 15,
            "clusters": {},
            "modroles": [],
            "modcommands": [],
            "badnames": [],
            "tribes": {},
            "playerstats": {},
        }
        self.config.register_guild(**default_guild)

        # Cache on cog load
        self.logs = {}
        self.servercount = 0
        self.taskdata = []
        self.channels = []
        self.alerts = {}
        self.playerlist = {}
        self.time = ""

        # Loops
        self.loop_refresher.start()
        self.chat_executor.start()
        self.playerlist_executor.start()
        self.status_channel.start()
        self.playerstats.start()

    def cog_unload(self):
        self.loop_refresher.cancel()
        self.chat_executor.cancel()
        self.playerlist_executor.cancel()
        self.status_channel.cancel()
        self.playerstats.cancel()

    # GROUPS
    @commands.group(name="arktools")
    async def _setarktools(self, ctx: commands.Context):
        """Ark Tools base command."""
        pass

    @_setarktools.group(name="permissions")
    @commands.guildowner()
    async def _permissions(self, ctx: commands.Context):
        """Permission specific role settings for rcon commands."""
        pass

    @_setarktools.group(name="api")
    async def _api(self, ctx: commands.Context):
        """
        (CROSSPLAY ONLY) API tools for the host gamertags.
        Get API keys for each host Gamertag from https://xbl.io/
        """
        pass

    @_setarktools.group(name="server")
    @commands.guildowner()
    async def _serversettings(self, ctx: commands.Context):
        """Server setup."""
        pass

    @_setarktools.group(name="tribe")
    async def _tribesettings(self, ctx: commands.Context):
        """Tribe commands."""
        pass

    # EXTRA LOGS SENT TO THE JOIN LOG CHANNELS IF ENABLED
    @_setarktools.command(name="datalog")
    @commands.guildowner()
    async def _datalog(self, ctx):
        """
        (TOGGLE): Send extra data logs to join log channels

        Says when new player is registered in the database.
        If an API key is set for the server they joined, it will include whether or not they were
        DM'd and friend requested if AutoFriend or AutoWelcome is enabled.
        """
        dlog = await self.config.guild(ctx.guild).datalogs()
        if dlog:
            await self.config.guild(ctx.guild).datalogs.set(False)
            return await ctx.send("Extra data logs **Disabled**")
        else:
            await self.config.guild(ctx.guild).datalogs.set(True)
            return await ctx.send("Extra data logs **Enabled**")

    # PERMISSIONS COMMANDS
    @_permissions.command(name="setfullaccessrole")
    async def _setfullaccessrole(self, ctx: commands.Context, role: discord.Role):
        """Set a full RCON access role."""
        await self.config.guild(ctx.guild).fullaccessrole.set(role.id)
        await ctx.send(f"Full rcon access role has been set to {role}")

    @_permissions.command(name="addmodrole")
    async def _addmodrole(self, ctx: commands.Context, *, role: discord.Role):
        """Add a role to allow limited command access for."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                await ctx.send("That role already exists.")
            else:
                modroles.append(role.id)
                await ctx.send(f"The **{role}** role has been added.")

    @_permissions.command(name="delmodrole")
    async def _delmodrole(self, ctx: commands.Context, role: discord.Role):
        """Delete a mod role."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                modroles.remove(role.id)
                await ctx.send(f"{role} role has been removed.")
            else:
                await ctx.send("That role isn't in the list.")

    @_permissions.command(name="addbadname")
    async def _addbadname(self, ctx: commands.Context, *, badname: str):
        """Blacklisted a player name."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                await ctx.send("That name already exists.")
            else:
                badnames.append(badname)
                await ctx.send(f"**{badname}** has been added to the blacklist.")

    @_permissions.command(name="delbadname")
    async def _delbadname(self, ctx: commands.Context, badname: str):
        """Delete a blacklisted name."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                badnames.remove(badname)
                await ctx.send(f"{badname} has been removed from the blacklist.")
            else:
                await ctx.send("That name doesnt exist")

    @_permissions.command(name="addmodcommand")
    async def _addmodcommand(self, ctx: commands.Context, *, modcommand: str):
        """Add allowable commands for the mods to use."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                await ctx.send("That command already exists!")
            else:
                modcommands.append(modcommand)
                await ctx.send(f"The command **{modcommand}** has been added to the list.")

    @_permissions.command(name="delmodcommand")
    async def _delmodcommand(self, ctx: commands.Context, modcommand: str):
        """Delete an allowed mod command."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                modcommands.remove(modcommand)
                await ctx.send(f"The {modcommand} command has been removed.")
            else:
                await ctx.send("That command doesnt exist")

    # API SETTINGS
    @_api.command(name="addkey")
    async def _addkey(self, ctx, clustername, servername, apikey):
        """
        Add an API key for a server.

        Get API keys for each host Gamertag from https://xbl.io/
        """
        async with self.config.guild(ctx.guild).clusters() as clusters:
            for cluster in clusters:
                if cluster.lower() == clustername.lower():
                    cname = cluster
                    break
            else:
                color = discord.Color.red()
                embed = discord.Embed(description=f"Could not find {clustername}!", color=color)
                return await ctx.send(embed=embed)
            for server in clusters[cname]["servers"]:
                if server.lower() == servername.lower():
                    sname = server
                    break
            else:
                color = discord.Color.red()
                embed = discord.Embed(description=f"Could not find {servername}!", color=color)
                return await ctx.send(embed=embed)
            async with ctx.typing():
                # pull host gamertag name
                data, status = await self.apicall("https://xbl.io/api/v2/account", apikey)
            if status == 200:
                for user in data["profileUsers"]:
                    for setting in user["settings"]:
                        if setting["id"] == "Gamertag":
                            gtag = setting["value"]
                clusters[cname]["servers"][sname]["gamertag"] = gtag
                clusters[cname]["servers"][sname]["api"] = apikey
                color = discord.Color.green()
                embed = discord.Embed(
                    description=f"✅ Your token has been set for {gtag}!",
                    color=color
                )
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    return await ctx.send("Failed to delete your key because bot doesn't have permissions.")
                return await ctx.send(embed=embed)
            else:
                color = discord.Color.red()
                embed = discord.Embed(description=f"Failed to collect data!\n"
                                                  f"Key may be Invalid or API might be down.", color=color)
                return await ctx.send(embed=embed)

    # Delete a key from a server
    @_api.command(name="delkey")
    async def _delkey(self, ctx, clustername, servername):
        """
        Delete an API key from a server.
        """
        async with self.config.guild(ctx.guild).clusters() as clusters:
            found = False
            for cluster in clusters:
                if cluster.lower() == clustername.lower():
                    for server in clusters[cluster]["servers"]:
                        if server.lower() == servername.lower():
                            if "api" in clusters[cluster]["servers"][server]:
                                del clusters[cluster]["servers"][server]["gamertag"]
                                del clusters[cluster]["servers"][server]["api"]
                                found = True
                                await ctx.send(f"API key deleted for {server} {cluster}")
            if not found:
                await ctx.send("Server not found.")

    # Toggle the host gamertag sending an automated welcome message when it detects a new player in the database
    @_api.command(name="welcome")
    async def _welcometoggle(self, ctx):
        """(Toggle) Automatic server welcome messages"""
        welcometoggle = await self.config.guild(ctx.guild).autowelcome()
        if welcometoggle:
            await self.config.guild(ctx.guild).autowelcome.set(False)
            await ctx.send("Auto Welcome Message **Disabled**")
        else:
            await self.config.guild(ctx.guild).autowelcome.set(True)
            await ctx.send("Auto Welcome Message **Enabled**")

    # Toggle the host gamertag sending an automated friend request when it detects a new player in the database
    @_api.command(name="autofriend")
    async def _autofriendtoggle(self, ctx):
        """(Toggle) Automatic maintenance of gamertag friend lists"""
        autofriendtoggle = await self.config.guild(ctx.guild).autofriend()
        if autofriendtoggle:
            await self.config.guild(ctx.guild).autofriend.set(False)
            await ctx.send("Autofriend Message **Disabled**")
        else:
            await self.config.guild(ctx.guild).autofriend.set(True)
            await ctx.send("Autofriend Message **Enabled**")

    # Time (in days) of a player not being detected online that the host gamertag unfriends them
    @_api.command(name="unfriendtime")
    async def _unfriendtime(self, ctx, days: int):
        """
        Set number of days of inactivity for the host Gamertags to unfriend a player.

        This keep xbox host Gamertag friends lists clean since the max you can have is 1000.
        """
        await self.config.guild(ctx.guild).unfriendafter.set(days)
        await ctx.send(f"Inactivity days till auto unfriend is {days} days.")

    # Set the welcome message to send to new players if autowelcome is enabled
    @_api.command(name="setwelcome")
    async def _welcome(self, ctx, *, welcome_message: str):
        """
        Set a welcome message to be used instead of the default.
        When the bot detects a new gamertag that isnt in the database, it sends it a welcome DM with
        an invite to the server.


        Variables that can be used in the welcome message are:
        {discord} - Discord name
        {gamertag} - Persons Gamertag
        {link} - Discord link
        Put "Default" in welcome string to revert to default message.
        """
        params = {
            "discord": ctx.guild.name,
            "gamertag": "gamertag",
            "link": "channel invite"
        }
        if "default" in welcome_message.lower():
            await ctx.send("Welcome message reverted to Default!")
            return await self.config.guild(ctx.guild).welcomemsg.set(None)
        try:
            to_send = welcome_message.format(**params)
        except KeyError as e:
            await ctx.send(f"The welcome message cannot be formatted, because it contains an "
                           f"invalid placeholder `{{{e.args[0]}}}`. See `{ctx.prefix}arktools api setwelcome` "
                           f"for a list of valid placeholders.")
        else:
            await self.config.guild(ctx.guild).welcomemsg.set(welcome_message)
            await ctx.send(f"Welcome message set as:\n{to_send}")

    # API COMMANDS
    # Register a gamertag in the database
    @_setarktools.command(name="register")
    async def _register(self, ctx):
        """
        (CROSSPLAY ONLY)Set your Gamertag

        This command requires api keys to be set for the servers
        """
        apipresent = False
        clusters = await self.config.guild(ctx.guild).clusters()
        for cname in clusters:
            for sname in clusters[cname]["servers"]:
                if "api" in clusters[cname]["servers"][sname]:
                    apipresent = True
                    break
        if not apipresent:
            embed = discord.Embed(
                description="❌ API key has not been set!."
            )
            embed.set_thumbnail(url=FAILED)
            return await ctx.send(embed=embed)
        embed = discord.Embed(
            description=f"**Type your Gamertag (or ID if Steam) in chat.**"
        )
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.isdigit():
            async with self.config.guild(ctx.guild).playerstats() as stats:
                current_time = datetime.datetime.utcnow()
                for name in stats:
                    if reply.content in stats[name]["xuid"] and ctx.author.id == stats[name]["discord"]:
                        embed = discord.Embed(
                            description="You are already in the system 👍"
                        )
                        return await ctx.send(embed=embed)
                else:
                    sid = reply.content
                    embed = discord.Embed(
                        description=f"**Type your Steam Username.**"
                    )
                    await msg.edit(embed=embed)
                    try:
                        reply = await self.bot.wait_for("message", timeout=60, check=check)
                    except asyncio.TimeoutError:
                        return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

                    steamname = reply.content
                    stats[steamname]["discord"] = ctx.author.id
                    stats[steamname] = {"playtime": {"total": 0}}
                    stats[steamname]["xuid"] = sid
                    stats[steamname]["lastseen"] = {
                        "time": current_time.isoformat(),
                        "map": "None"
                    }
                    embed = discord.Embed(
                        description=f"Your ID `{sid}` has been registered under `{steamname}` for `{ctx.author.name}`."
                    )
                    return await msg.edit(embed=embed)

        gamertag = reply.content
        async with ctx.typing():
            embed = discord.Embed(color=discord.Color.green(),
                                  description=f"Searching...")
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            command = f"https://xbl.io/api/v2/friends/search?gt={gamertag}"
            settings = await self.config.guild(ctx.guild).all()
            apikey = await self.pullkey(settings)
            data, status = await self.apicall(command, apikey)
            if status != 200:
                embed = discord.Embed(title="Error",
                                      color=discord.Color.dark_red(),
                                      description="API failed, please try again in a few minutes.")
                embed.set_thumbnail(url=FAILED)
                return await ctx.send(embed=embed)
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            try:
                if data:
                    for user in data["profileUsers"]:
                        xuid = user['id']
                        pfp = SUCCESS
                        gs = 0
                        for setting in user["settings"]:
                            if setting["id"] == "GameDisplayPicRaw":
                                pfp = (setting['value'])
                            if setting["id"] == "Gamerscore":
                                gs = "{:,}".format(int(setting['value']))
                else:
                    embed = discord.Embed(title="Error",
                                          color=discord.Color.dark_red(),
                                          description="Failed to parse player data.\n"
                                                      "This may be due to player's privacy settings.")
                    embed.set_thumbnail(url=FAILED)
                    return await ctx.send(embed=embed)
            except KeyError:
                embed = discord.Embed(title="Error",
                                      color=discord.Color.dark_red(),
                                      description="Gamertag is invalid or does not exist.")
                embed.set_thumbnail(url=FAILED)
                return await msg.edit(embed=embed)
        async with self.config.guild(ctx.guild).playerstats() as stats:
            current_time = datetime.datetime.utcnow()
            if gamertag not in stats:
                stats[gamertag] = {"playtime": {"total": 0}}
            stats[gamertag]["xuid"] = xuid
            stats[gamertag]["lastseen"] = {
                "time": current_time.isoformat(),
                "map": "None"
            }
            stats[gamertag]["discord"] = ctx.author.id
            embed = discord.Embed(color=discord.Color.green(),
                                  description=f"✅ Gamertag set to `{gamertag}`\n"
                                              f"XUID: `{xuid}`\n"
                                              f"Gamerscore: `{gs}`\n\n"
                                              f"**Would you like to add yourself to a gamertag as well?**")
            embed.set_footer(text="Reply with 'yes' to go to the next step.")
            embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
            embed.set_thumbnail(url=pfp)
            await msg.edit(embed=embed)

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
        rep = reply.content.lower()
        if "y" in rep:
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            return await self._addme(ctx)
        elif "n" in rep:
            return await msg.edit(embed=discord.Embed(description="Menu closed."))
        else:
            return await msg.edit(embed=discord.Embed(description="Invalid response. Menu closed."))

    # Pull nearest api key
    async def pullkey(self, settings):
        for clustername in settings["clusters"]:
            for mapname in settings["clusters"][clustername]["servers"]:
                if "api" in settings["clusters"][clustername]["servers"][mapname]:
                    return settings["clusters"][clustername]["servers"][mapname]["api"]

    # Make host gamertags add you as a friend
    @_setarktools.command(name="addme")
    async def _addme(self, ctx):
        """
        (CROSSPLAY ONLY)Add yourself as a friend from the host gamertags

        This command requires api keys to be set for the servers
        """
        registered = False
        xuid = None
        ptag = None
        settings = await self.config.guild(ctx.guild).all()
        for player in settings["playerstats"]:
            if "discord" in settings["playerstats"][player]:
                if settings["playerstats"][player]["discord"] == ctx.author.id:
                    registered = True
                    xuid = settings["playerstats"][player]["xuid"]
                    ptag = player
                    break
        if not registered:
            embed = discord.Embed(description=f"No Gamertag set for **{ctx.author.mention}**!\n\n"
                                              f"Set a Gamertag with `{ctx.prefix}arktools register`")
            embed.set_thumbnail(url=FAILED)
            return await ctx.send(embed=embed)
        else:
            map_options, serverlist = await self.enumerate_maps_api(ctx)
            embed = discord.Embed(
                title=f"Add Yourself as a Friend",
                description=f"**TYPE THE NUMBER that corresponds with the server you want.**\n\n"
                            f"{map_options}"
            )
            embed.set_footer(text="Type your reply below")
            msg = await ctx.send(embed=embed)

            def check(message: discord.Message):
                return message.author == ctx.author and message.channel == ctx.channel

            try:
                reply = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

            if reply.content.lower() == "all":
                embed = discord.Embed(
                    description="Gathering Data..."
                )
                embed.set_thumbnail(url=LOADING)
                await msg.edit(embed=embed)
                async with ctx.typing():
                    try:
                        await reply.delete()
                    except discord.NotFound:
                        pass
                    for clustername in settings["clusters"]:
                        for servername in settings["clusters"][clustername]["servers"]:
                            if "api" in settings["clusters"][clustername]["servers"][servername]:
                                gt = settings["clusters"][clustername]["servers"][servername]["gamertag"]
                                apikey = settings["clusters"][clustername]["servers"][servername]["api"]
                                command = f"https://xbl.io/api/v2/friends/add/{xuid}"
                                async with self.session.get(command, headers={"X-Authorization": apikey}) as resp:
                                    await resp.text()
                                    if resp.status == 200:
                                        color = discord.Color.random()
                                        embed = discord.Embed(color=color,
                                                              description=f"Sending friend request from... `{gt}`")
                                        embed.set_thumbnail(url=LOADING)
                                    else:
                                        embed = discord.Embed(color=color,
                                                              description=f"⚠ `{gt}` Failed to add you!")
                                        embed.set_thumbnail(url=FAILED)
                                    await msg.edit(embed=embed)
                    embed = discord.Embed(color=discord.Color.green(),
                                          description=f"✅ `All Gamertags` Successfully added `{ptag}`\n"
                                                      f"You should now be able to join from the Gamertag's"
                                                      f" profile page.")
                    embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
                    embed.set_thumbnail(url=SUCCESS)
                    return await msg.edit(embed=embed)
            elif reply.content.isdigit():
                embed = discord.Embed(
                    description="Gathering Data..."
                )
                embed.set_thumbnail(url=LOADING)
                await msg.edit(embed=embed)
                async with ctx.typing():
                    try:
                        await reply.delete()
                    except discord.NotFound:
                        pass
                    for data in serverlist:
                        if int(reply.content) == data[0]:
                            gt = data[1]
                            key = data[2]
                            break
                    else:
                        color = discord.Color.red()
                        embed = discord.Embed(description=f"Could not find the server corresponding to {reply.content}!",
                                              color=color)
                        return await ctx.send(embed=embed)
                    embed = discord.Embed(
                        description=f"Sending freind request from {gt}..."
                    )
                    embed.set_thumbnail(url=LOADING)
                    await msg.edit(embed=embed)
                    command = f"https://xbl.io/api/v2/friends/add/{xuid}"
                    async with self.session.get(command, headers={"X-Authorization": key}) as resp:
                        await resp.text()
                        if resp.status == 200:
                            embed = discord.Embed(color=discord.Color.green(),
                                                  description=f"✅ `{gt}` Successfully added `{ptag}`\n"
                                                              f"You should now be able to join from the Gamertag's"
                                                              f" profile page.\n\n"
                                                              f"**TO ADD MORE:** type `{ctx.prefix}arktools addme`")
                            embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
                            embed.set_thumbnail(url=SUCCESS)
                        else:
                            embed = discord.Embed(title="Unsuccessful",
                                                  color=discord.Color.green(),
                                                  description=f"⚠ `{gt}` Failed to add `{ptag}`")
                    await msg.edit(embed=embed)
            else:
                color = discord.Color.red()
                return await msg.edit(embed=discord.Embed(description="Incorrect Reply, menu closed.", color=color))

    # Purge host gamertag friends list of anyone not in the cog's database
    @_api.command(name="prune")
    @commands.guildowner()
    async def _prune(self, ctx):
        """Prune any host gamertag friends that are not in the database."""
        tokens = []
        playerdb = []
        settings = await self.config.guild(ctx.guild).all()
        for member in settings["playerstats"]:
            if "xuid" in settings["playerstats"][member]:
                xuid = settings["playerstats"][member]["xuid"]
                playerdb.append(xuid)
        for cname in settings["clusters"]:
            for sname in settings["clusters"][cname]["servers"]:
                if "api" in settings["clusters"][cname]["servers"][sname]:
                    api = settings["clusters"][cname]["servers"][sname]["api"]
                    gt = settings["clusters"][cname]["servers"][sname]["gamertag"]
                    tokens.append((api, gt))
        if tokens:
            embed = discord.Embed(
                description=f"Gathering Data..."
            )
            embed.set_footer(text="This may take a while, sit back and relax.")
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            friendreq = "https://xbl.io/api/v2/friends"
            for host in tokens:
                purgelist = []
                key = host[0]
                gt = host[1]
                embed = discord.Embed(
                    description=f"Gathering data for {gt}..."
                )
                embed.set_thumbnail(url=LOADING)
                await msg.edit(embed=embed)
                data, status = await self.apicall(friendreq, key)
                if status == 200:
                    embed = discord.Embed(
                        description=f"Pruning players from {gt}..."
                    )
                    embed.set_footer(text="This may take a while, sit back and relax.")
                    embed.set_thumbnail(url=LOADING)
                    await msg.edit(embed=embed)
                    async with ctx.typing():
                        for friend in data["people"]:
                            xuid = friend["xuid"]
                            playertag = friend["gamertag"]
                            if xuid not in playerdb:
                                purgelist.append((xuid, playertag))
                        trash = len(purgelist)
                        cur_member = 1
                        for xuid in purgelist:
                            status, remaining = await self._purgewipe(xuid[0], key)
                            if int(remaining) < 30:
                                await ctx.send(f"`{gt}` low on remaining API calls `(30)`. Skipping for now.")
                                break
                            elif int(status) != 200:
                                await msg.edit(f"`{gt}` failed to unfriend `{xuid[1]}`.")
                                continue
                            else:
                                embed = discord.Embed(
                                    description=f"Pruning `{xuid[1]}` from {gt}...\n"
                                                f"`{cur_member}/{trash}` pruned."
                                )
                                embed.set_footer(text="This may take a while, sit back and relax.")
                                embed.set_thumbnail(url=LOADING)
                                await msg.edit(embed=embed)
                                cur_member += 1

            embed = discord.Embed(
                description=f"Purge Complete",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=SUCCESS)
            await msg.edit(embed=embed)

    # Purge and Wipe friend tasks
    async def _purgewipe(self, xuid, key):
        command = f"https://xbl.io/api/v2/friends/remove/{xuid}"
        remaining = 0
        async with self.session.get(command, headers={"X-Authorization": key}) as resp:
            await resp.text()
            status = resp.status
            if status == 200:
                remaining = resp.headers['X-RateLimit-Remaining']
            return status, remaining

    # SERVER SETTINGS COMMANDS
    @_serversettings.command(name="addcluster")
    async def _addcluster(self, ctx: commands.Context,
                          clustername,
                          joinchannel: discord.TextChannel,
                          leavechannel: discord.TextChannel,
                          adminlogchannel: discord.TextChannel,
                          globalchatchannel: discord.TextChannel):
        """
        Add a cluster with specified log channels. (Use all lower case letters for cluster name)


        Include desired join, leave, admin log, and global chat channel.
        """
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                await ctx.send("Cluster already exists")
            else:
                clusters[clustername.lower()] = {
                    "joinchannel": joinchannel.id,
                    "leavechannel": leavechannel.id,
                    "adminlogchannel": adminlogchannel.id,
                    "globalchatchannel": globalchatchannel.id,
                    "servertoserver": False,
                    "servers": {}
                }
                await ctx.send(f"**{clustername}** has been added to the list of clusters.")

    # Delete an entire cluster
    @_serversettings.command(name="delcluster")
    async def _delcluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername]
                await ctx.send(f"{clustername} cluster has been deleted")

    # Add a server to a cluster
    @_serversettings.command(name="addserver")
    async def _addserver(self, ctx: commands.Context, clustername: str, servername: str, ip: str,
                         port: int, password: str, channel: discord.TextChannel):
        """Add a server. (Use all lower case letters for server name and cluster name)"""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters:
                return await ctx.send(f"The cluster {clustername} does not exist!")
            elif servername not in clusters[clustername]["servers"]:
                return await ctx.send(f"The server {servername} does not exist!")
            elif servername in clusters[clustername]["servers"].keys():
                await ctx.send(f"The **{servername}** server was **overwritten** in the **{clustername}** cluster!")
            elif servername not in clusters[clustername]["servers"].keys():
                await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")
            clusters[clustername]["servers"][servername] = {
                "name": servername.lower(),
                "ip": ip,
                "port": port,
                "password": password,
                "chatchannel": channel.id
            }
            await self.initialize()

    # Delete a server from a cluster
    @_serversettings.command(name="delserver")
    async def _delserver(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            server = clusters[clustername]["servers"]
            if servername in server.keys():
                del clusters[clustername]["servers"][servername]
                await ctx.send(f"{servername} server has been removed from {clustername}")
                await self.initialize()
            else:
                await ctx.send(f"{servername} server not found.")

    # Set a channel for the server status to be displayed
    @_serversettings.command(name="setstatuschannel")
    async def _setstatuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a channel for a server status embed."""
        """This embed will be created if not exists, and updated every 60 seconds."""
        await self.config.guild(ctx.guild).statuschannel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    # Toggle map-to-map chat for a specific cluster
    @_serversettings.command(name="toggle")
    async def _servertoservertoggle(self, ctx: commands.Context, clustername):
        """Toggle server to server chat so maps can talk to eachother"""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if "servertoserver" not in clusters[clustername].keys():
                clusters[clustername]["servertoserver"] = False
                return await ctx.send(
                    f"Server to server chat for {clustername.upper()} has been initialized as **Disabled**.")
            if clusters[clustername]["servertoserver"] is False:
                clusters[clustername]["servertoserver"] = True
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Enabled**.")
            if clusters[clustername]["servertoserver"] is True:
                clusters[clustername]["servertoserver"] = False
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Disabled**.")

    # TRIBE COMMANDS
    @_tribesettings.command(name="setmasterlog")
    async def _setmasterlog(self, ctx, channel: discord.TextChannel):
        """Set global channel for all unassigned tribe logs."""
        await self.config.guild(ctx.guild).masterlog.set(channel.id)
        await ctx.send(f"Master tribe log channel has been set to {channel.mention}")

    @_tribesettings.command(name="addtribe")
    async def _addtribe(self, ctx, tribe_id, owner: discord.Member, channel: discord.TextChannel):
        """Add a tribe to be managed by it's owner."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id in tribes.keys():
                await ctx.send("Tribe ID already exists!")
            else:
                tribes[tribe_id] = {
                    "owner": owner.id,
                    "channel": channel.id,
                    "allowed": []
                }
                await channel.set_permissions(owner, read_messages=True)
                await ctx.send(f"Tribe ID `{tribe_id}` has been set for {owner.mention} in {channel.mention}.")

    @_tribesettings.command(name="deltribe")
    async def _deltribe(self, ctx, tribe_id):
        """Delete a tribe."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id in tribes.keys():
                await ctx.send(f"Tribe with ID: {tribe_id} has been deleted")
                del tribes[tribe_id]
            else:
                await ctx.send("Tribe ID doesn't exist!")

    @_tribesettings.command(name="mytribe")
    async def _viewtribe(self, ctx):
        """View your tribe(if you've been granted ownership of one"""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes != {}:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"] or ctx.author.id in tribes[tribe]["allowed"]:
                        owner = ctx.guild.get_member(tribes[tribe]['owner']).mention
                        embed = discord.Embed(
                            title=f"{ctx.author.name}'s Tribe",
                            description=f"Tribe ID: {tribe}\nOwner: {owner}"
                        )
                        members = ""
                        for member in tribes[tribe]["allowed"]:
                            members += f"{ctx.guild.get_member(member).mention}\n"
                        if members == "":
                            members = "None Added"
                        embed.add_field(
                            name=f"Tribe Members",
                            value=f"{members}"
                        )
                    else:
                        await ctx.send("You don't have access any tribes.")
                    await ctx.send(embed=embed)
            else:
                await ctx.send(f"There are no tribes set for this server.")

    @_tribesettings.command(name="add")
    async def _addmember(self, ctx, member: discord.Member):
        """Add a member to your tribe logs."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"]:
                        tribes[tribe]["allowed"].append(member.id)
                        channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                        await channel.set_permissions(member, read_messages=True)
                        await ctx.send(f"{member.mention} has been added to the tribe logs")
                    else:
                        await ctx.send(f"You arent set as owner of any tribes to add people on.")
            else:
                await ctx.send("No tribe data available")

    @_tribesettings.command(name="remove")
    async def _removemember(self, ctx, member: discord.Member):
        """Remove a member from your tribe logs"""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"]:
                        memberlist = tribes[tribe]["allowed"]
                        if member.id in memberlist:
                            memberlist.remove(member.id)
                            channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                            await channel.set_permissions(member, read_messages=False)
                            await ctx.send(f"{member.mention} has been remove from tribe log access.")
                        else:
                            await ctx.send("Member does not exist in tribe log access.")
                    else:
                        await ctx.send("You do not have ownership of any tribes")
            else:
                await ctx.send("No tribe data available")

    # PLAYER STAT COMMANDS
    # Get the top 10 players in the cluster, browse pages to see them all
    @_setarktools.command(name="leaderboard")
    async def _leaderboard(self, ctx):
        """
        View time played leaderboard
        """

        stats = await self.config.guild(ctx.guild).playerstats()
        leaderboard = {}
        global_time = 0

        # Global cumulative time
        for player in stats:
            time = stats[player]["playtime"]["total"]
            leaderboard[player] = time
            global_time = global_time + time
        globaldays, globalhours, globalminutes = await self.time_formatter(global_time)
        sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)

        if len(sorted_players) >= 10:
            pages = math.ceil(len(sorted_players) / 10)
            embedlist = []
            start = 0
            stop = 10
            for page in range(int(pages)):
                embed = discord.Embed(
                    title="Playtime Leaderboard",
                    description=f"Global Cumulative Playtime: `{globaldays}d {globalhours}h {globalminutes}m`\n\n"
                                f"**Top Players by Playtime** - `{len(sorted_players)} in Database`\n",
                    color=discord.Color.random()
                )
                embed.set_thumbnail(url=ctx.guild.icon_url)
                if stop > len(sorted_players):
                    stop = len(sorted_players)
                for i in range(start, stop, 1):

                    playername = sorted_players[i][0]
                    maps = ""
                    for smap in stats[playername]["playtime"]:
                        if smap != "total":
                            time = stats[playername]["playtime"][smap]
                            days, hours, minutes = await self.time_formatter(time)
                            maps += f"{smap.capitalize()}: `{days}d {hours}h {minutes}m`\n"
                    time_played = sorted_players[i][1]
                    days, hours, minutes = await self.time_formatter(time_played)
                    current_time = datetime.datetime.utcnow()
                    timestamp = datetime.datetime.fromisoformat(stats[playername]['lastseen']["time"])
                    timedifference = current_time - timestamp
                    _, h, m = await self.time_formatter(timedifference.seconds)
                    time = f"Last Seen: `{timedifference.days}d {h}h {m}m ago`"
                    if timedifference.days >= 5:
                        time = f"Last Seen: `{timedifference.days} days ago`"

                    embed.add_field(name=f"{i + 1}. {playername}",
                                    value=f"Total: `{days}d {hours}h {minutes}m`\n"
                                          f"{maps}"
                                          f"{time}")
                embedlist.append(embed)
                start += 10
                stop += 10
            msg = False
            return await self.paginate(ctx, embedlist, msg)
        else:
            remaining = 10 - len(sorted_players)
            await ctx.send(embed=discord.Embed(description=f"Not enough player data to establish a leaderboard.\n"
                                                           f"Need {remaining} more players in database."))

    # Menu for doing menu things
    async def paginate(self, ctx, embeds, msg):
        pages = len(embeds)
        cur_page = 1
        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
        if not msg:
            message = await ctx.send(embed=embeds[cur_page - 1])
        else:
            message = msg
            await msg.edit(embed=embeds[cur_page - 1])

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

                if str(reaction.emoji) == "⏩" and cur_page + 10 <= pages:
                    cur_page += 10
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "▶️" and cur_page + 1 <= pages:
                    cur_page += 1
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⏪" and cur_page - 10 >= 1:
                    cur_page -= 10
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return await message.edit(embed=discord.Embed(description="Menu closed."))

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                try:
                    return await message.clear_reactions()
                except discord.NotFound:
                    return

    # Get a specific player's stats
    @_setarktools.command(name="playerstats", aliases=["pstats, stats"])
    async def _playerstats(self, ctx, *, gamertag):
        """View stats for a Gamertag"""
        stats = await self.config.guild(ctx.guild).playerstats()
        current_time = datetime.datetime.utcnow()
        for player in stats:
            if player.lower() == gamertag.lower():
                time = stats[player]["playtime"]["total"]
                timestamp = datetime.datetime.fromisoformat(stats[player]["lastseen"]["time"])
                timedifference = current_time - timestamp
                _, h, m = await self.time_formatter(timedifference.seconds)
                lastmap = stats[player]["lastseen"]["map"]
                days, hours, minutes = await self.time_formatter(time)
                embed = discord.Embed(
                    title=f"Playerstats for {player}",
                    description=f"Total Time Played: `{days}d {hours}h {minutes}m`\n"
                                f"Last Seen: `{timedifference.days}d {h}h {m}m` ago on `{lastmap}`",
                    color=discord.Color.random()
                )
                for mapn in stats[player]["playtime"]:
                    if mapn != "total":
                        raw_time = stats[player]["playtime"][mapn]
                        days, hours, minutes = await self.time_formatter(raw_time)
                        embed.add_field(
                            name=f"{mapn}",
                            value=f"`{days}d {hours}h {minutes}m`"
                        )
                return await ctx.send(embed=embed)
            else:
                continue
        await ctx.send(embed=discord.Embed(description=f"No player data found for {gamertag}"))

    # Get stats for all maps in a cluster showing top player for each map
    @_setarktools.command(name="clusterstats")
    async def _clusterstats(self, ctx):
        """View statistics for all servers"""
        stats = await self.config.guild(ctx.guild).playerstats()
        maps = {}
        t = {}
        for player in stats:
            for mapn in stats[player]["playtime"]:
                if mapn != "total":
                    t[mapn] = {}
                    maps[mapn] = 0
        for player in stats:
            for mapn in stats[player]["playtime"]:
                if mapn != "total":
                    t[mapn][player] = stats[player]["playtime"][mapn]
                    time = stats[player]["playtime"][mapn]
                    maps[mapn] += time
        sorted_maps = sorted(maps.items(), key=lambda x: x[1], reverse=True)
        mstats = ""
        count = 1
        for map in sorted_maps:
            max_p = max(t[map[0]], key=t[map[0]].get)
            maxptime = t[map[0]][max_p]
            md, mh, mm = await self.time_formatter(maxptime)
            name = map[0]
            time = map[1]
            d, h, m = await self.time_formatter(time)
            mstats += f"**{count}. {name.upper()}** - `{len(t[map[0]].keys())} Players`\n" \
                      f"Total Time Played: `{d}d {h}h {m}m`\n" \
                      f"Top Player: `{max_p}` - `{md}d {mh}h {mm}m`\n\n"
            count += 1
        color = discord.Color.random()
        embed = discord.Embed(title="Map Stats",
                              description=f"{mstats}",
                              color=color)
        embed.set_thumbnail(url=ctx.guild.icon_url)
        await ctx.send(embed=embed)

    # Get stats by map, shows everyone in a selected map
    @_setarktools.command(name="mapstats")
    async def _mapstats(self, ctx):
        """View stats for a particular server"""
        map_options, serverlist = await self.enumerate_maps_all(ctx)
        embed = discord.Embed(
            title="Select a map to see stats",
            description=f"**Type the Number that corresponds with the server you want.**\n\n"
                        f"{map_options}"
        )
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.isdigit():
            async with ctx.typing():
                try:
                    await reply.delete()
                except discord.NotFound:
                    pass
                for data in serverlist:
                    if int(reply.content) == data[0]:
                        sname = data[1]
                        cname = data[2]
                        break
                else:
                    color = discord.Color.red()
                    embed = discord.Embed(description=f"Could not find the server corresponding to {reply.content}!",
                                          color=color)
                    return await ctx.send(embed=embed)
                stats = await self.config.guild(ctx.guild).playerstats()
                leaderboard = {}
                lastseen = {}
                global_time = 0
                for player in stats:
                    if f"{sname} {cname}" in stats[player]["playtime"]:
                        time = stats[player]["playtime"][f"{sname} {cname}"]
                        leaderboard[player] = time
                        lastseen[player] = stats[player]["lastseen"]["time"]
                        global_time = global_time + time
                gd, gh, gm = await self.time_formatter(global_time)
                sorted_players = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)

                current_time = datetime.datetime.utcnow()
                if len(sorted_players) >= 10:
                    pages = math.ceil(len(sorted_players) / 10)
                    embedlist = []
                    start = 0
                    stop = 10
                    for page in range(int(pages)):
                        embed = discord.Embed(
                            title=f"Stats for {sname.capitalize()} {cname.upper()}",
                            description=f"Global Cumulative Playtime: `{gd}d {gh}h {gm}m`\n\n"
                                        f"**Top Players by Playtime** - `{len(sorted_players)} Total`\n",
                            color=discord.Color.random()
                        )
                        embed.set_thumbnail(url=STATUS)
                        if stop > len(sorted_players):
                            stop = len(sorted_players)
                        for i in range(start, stop, 1):
                            playername = sorted_players[i][0]
                            playertime = sorted_players[i][1]
                            timestamp = datetime.datetime.fromisoformat(lastseen[playername])
                            timedifference = current_time - timestamp
                            dt, ht, mt = await self.time_formatter(playertime)
                            _, h, m = await self.time_formatter(timedifference.seconds)
                            embed.add_field(
                                name=f"{i + 1}. {playername}",
                                value=f"Time Played: `{dt}d {ht}h {mt}m`\n"
                                      f"Last Seen: `{timedifference.days}d {h}h {m}m ago`"
                            )
                        embedlist.append(embed)
                        start += 10
                        stop += 10
                    return await self.paginate(ctx, embedlist, msg)
                else:
                    embed = discord.Embed(
                        title=f"Stats for {sname.capitalize()} {cname.upper()}",
                        description=f"Global Cumulative Playtime: `{gd}d {gh}h {gm}m`\n\n"
                                    f"**Top Players by Playtime** - `{len(sorted_players)} Total`\n",
                        color=discord.Color.random()
                    )
                    embed.set_thumbnail(url=ctx.guild.icon_url)
                    for i in range(0, len(sorted_players), 1):
                        playername = sorted_players[i][0]
                        playertime = sorted_players[i][1]
                        timestamp = datetime.datetime.fromisoformat(lastseen[playername])
                        timedifference = current_time - timestamp
                        dt, ht, mt = await self.time_formatter(playertime)
                        _, h, m = await self.time_formatter(timedifference.seconds)
                        embed.add_field(
                            name=f"{i + 1}. playername",
                            value=f"Time Played: `{dt}d {ht}h {mt}m`\n"
                                  f"Last Seen: `{timedifference.days}d {h}h {m}m ago`"
                        )
                    return await msg.edit(embed=embed)

    # Resets all player playtime data back to 0 in the config
    @_setarktools.command(name="resetlb")
    @commands.guildowner()
    async def _resetlb(self, ctx: commands.Context):
        """Reset all playtime stats in the leaderboard."""
        async with self.config.guild(ctx.guild).playerstats() as stats:
            async with ctx.typing():
                for gamertag in stats:
                    for key in stats[gamertag]["playtime"]:
                        stats[gamertag]["playtime"][key] = 0
                await ctx.send(embed=discord.Embed(description="Player Stats have been reset."))

    # Deletes all player data in the config
    @_setarktools.command(name="wipestats")
    @commands.guildowner()
    async def _wipestats(self, ctx: commands.Context):
        """Wipe all player stats including last seen data."""
        async with self.config.guild(ctx.guild).all() as data:
            async with ctx.typing():
                del data["playerstats"]
            await ctx.send(embed=discord.Embed(description="Player Stats have been wiped."))

    # Time Converter
    async def time_formatter(self, time_played):
        minutes,_ = divmod(time_played, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        return days, hours, minutes

    # HARDCODED ITEM SEND
    @_setarktools.command(name="imstuck")
    @commands.cooldown(1, 7200, commands.BucketType.user)
    async def imstuck(self, ctx):
        """
        For those tough times when Ark is being Ark

        Sends you tools to get unstuck, or off yourself.
        """
        embed = discord.Embed(
            description=f"**Type your Implant ID in chat.**"
        )
        embed.set_footer(text="Hint: your implant id can be seen by hovering over it in your inventory!")
        embed.set_thumbnail(url="https://i.imgur.com/kfanq99.png")
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="Ok guess ya didn't need help then."))

        if reply.content.isdigit():
            implant_id = reply.content
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            embed = discord.Embed(
                description=f"Sit tight, your care package is on the way!"
            )
            embed.set_thumbnail(url="https://i.imgur.com/8ofOx6X.png")
            await msg.edit(embed=embed)
            settings = await self.config.guild(ctx.guild).all()
            serverlist = []
            for cluster in settings["clusters"]:
                for server in settings["clusters"][cluster]["servers"]:
                    settings["clusters"][cluster]["servers"][server]["cluster"] = cluster.lower()
                    serverlist.append(settings["clusters"][cluster]["servers"][server])
            commands = [
                f"""GiveItemToPlayer {implant_id} "Blueprint'/Game/PrimalEarth/CoreBlueprints/Resources/PrimalItemResource_Polymer_Organic.PrimalItemResource_Polymer_Organic'" 10 0 0""",
                f"""GiveItemToPlayer {implant_id} "Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItemAmmo_GrapplingHook.PrimalItemAmmo_GrapplingHook'" 2 0 0""",
                f"""GiveItemToPlayer {implant_id} "Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_WeaponCrossbow.PrimalItem_WeaponCrossbow'" 1 0 0""",
                f"""GiveItemToPlayer {implant_id} "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Structures/Thatch/PrimalItemStructure_ThatchFloor.PrimalItemStructure_ThatchFloor'" 1 0 0""",
                f"""GiveItemToPlayer {implant_id} "Blueprint'/Game/Aberration/CoreBlueprints/Weapons/PrimalItem_WeaponClimbPick.PrimalItem_WeaponClimbPick'" 2 0 0"""
            ]

            stucktasks = []
            for server in serverlist:
                for command in commands:
                    stucktasks.append(self.imstuck_rcon(server, command))

            async with ctx.typing():
                await asyncio.gather(*stucktasks)
            return
        else:
            return await msg.edit(embed=discord.Embed(description="Ok guess ya didn't need help then."))

    async def imstuck_rcon(self, serverlist, command):
        try:
            await rcon.asyncio.rcon(
                command=command,
                host=serverlist['ip'],
                port=serverlist['port'],
                passwd=serverlist['password']
            )
            return
        except WindowsError as e:
            if e.winerror == 121:
                clustername = serverlist['cluster']
                servername = serverlist['name']
                log.warning(f"IMSTUCK COMAMND: The **{servername}** **{clustername}** server has timed out and is probably down.")
                return

    # VIEW SETTINGSs
    @_api.command(name="view")
    async def _viewapi(self, ctx):
        """View current API settings"""
        settings = await self.config.guild(ctx.guild).all()
        autofriend = settings["autofriend"]
        autowelcome = settings["autowelcome"]
        unfriendtime = settings["unfriendafter"]
        welcomemsg = settings["welcomemsg"]
        if welcomemsg is None:
            welcomemsg = f"Welcome to {ctx.guild.name}!\nThis is an automated message:\n" \
                                                  f"You appear to be a new player, " \
                                                  f"here is an invite to the Discord server:\n\n*Invite Link*"
        color = discord.Color.random()
        embed = discord.Embed(
            title="API Settings",
            description=f"**AutoFriend System:** `{'Enabled' if autofriend else 'Disabled'}`\n"
                        f"**AutoWelcome System:** `{'Enabled' if autowelcome else 'Disabled'}`\n"
                        f"**AutoUnfriend Days:** `{unfriendtime}`\n",
            color=color
        )
        embed.add_field(
            name="Welcome Message",
            value=box(welcomemsg)
        )
        await ctx.send(embed=embed)

    @_permissions.command(name="view")
    async def _viewperms(self, ctx: commands.Context):
        """View current permission settings."""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        statuschannel = ctx.guild.get_channel(settings['statuschannel'])
        if settings['statuschannel']:
            statuschannel = statuschannel.mention
        if not settings['statuschannel']:
            statuschannel = "Not Set"
        try:
            embed = discord.Embed(
                title=f"Permission Settings",
                color=color,
                description=f"**Full Access Role:** {settings['fullaccessrole']}\n"
                            f"**Mod Roles:** {settings['modroles']}\n"
                            f"**Mod Commands:** {settings['modcommands']}\n"
                            f"**Blacklisted Names:** {settings['badnames']}\n"
                            f"**Status Channel:** {statuschannel}"
            )
            return await ctx.send(embed=embed)
        except KeyError:
            await ctx.send(f"Setup permissions first.")

    @_serversettings.command(name="view")
    async def _viewsettings(self, ctx: commands.Context):
        """View current server settings."""

        settings = await self.config.guild(ctx.guild).all()
        if not settings["clusters"]:
            await ctx.send("No servers have been added yet.")
            return
        for cname in settings["clusters"]:
            embed = discord.Embed(
                description=f"Gathering Server Data for `{cname.upper()}` Cluster..."
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(1)
            serversettings = ""
            serversettings += f"**{cname.upper()} Cluster**\n"
            if settings["clusters"][cname]["servertoserver"] is True:
                serversettings += f"`Map-to-Map Chat:` **Enabled**\n"
            if settings["clusters"][cname]["servertoserver"] is False:
                serversettings += f"`Map-to-Map Chat:` **Disabled**\n"
            for k, v in settings["clusters"][cname].items():
                if k == "globalchatchannel":
                    serversettings += f"`GlobalChat:` {ctx.guild.get_channel(v).mention}\n"
                if k == "adminlogchannel":
                    serversettings += f"`AdminLog:` {ctx.guild.get_channel(v).mention}\n"
                if k == "joinchannel":
                    serversettings += f"`JoinChannel:` {ctx.guild.get_channel(v).mention}\n"
                if k == "leavechannel":
                    serversettings += f"`LeaveChannel:` {ctx.guild.get_channel(v).mention}\n"
                else:
                    continue
            for server in settings["clusters"][cname]["servers"]:
                for k, v in settings["clusters"][cname]["servers"][server].items():
                    if k == "name":
                        serversettings += f"**Map:** `{v.capitalize()}`\n"
                    if k != "chatchannel":
                        if k != "name":
                            if k != "ip":
                                serversettings += f"**{k.capitalize()}:** `{v}`\n"
                            if k == "ip":
                                serversettings += f"**{k.upper()}:** `{v}`\n"
                    if k == "chatchannel":
                        serversettings += f"**Channel:** {ctx.guild.get_channel(v).mention}\n"
                if "api" in settings["clusters"][cname]["servers"][server]:
                    async with ctx.typing():
                        apikey = settings["clusters"][cname]["servers"][server]["api"]
                        getfriends = "https://xbl.io/api/v2/friends"
                        header = {"X-Authorization": apikey}
                        data = None
                        async with self.session.get(url=getfriends, headers=header) as resp:
                            pages = "Unknown"
                            remaining = 0
                            if int(resp.status) == 200:
                                remaining = resp.headers['X-RateLimit-Remaining']
                                data = await resp.json(content_type=None)
                            if data:
                                if "people" in data:
                                    pages = len(data["people"])
                        serversettings += f"**Friend Count:** `{pages}`\n"
                        serversettings += f"**API Calls Remaining:** `{str(remaining)}`\n"
                serversettings += "\n"
            try:
                await msg.delete()
            except discord.NotFound:
                pass
            for p in pagify(serversettings):
                color = discord.Color.dark_purple()
                embed = discord.Embed(
                    color=color,
                    description=f"{p}"
                )
                await ctx.send(embed=embed)

    @_tribesettings.command(name="view")
    @commands.guildowner()
    async def _viewtribesettings(self, ctx):
        """Overview of all tribes and settings"""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        masterlog = settings["masterlog"] if "masterlog" in settings else None
        masterlog = ctx.guild.get_channel(masterlog).mention if not None else "Not Set"
        tribes = settings["tribes"] if "tribes" in settings else None
        embed = discord.Embed(
            title="Tribe Settings Overview",
            color=color,
            description=f"**Master Tribe Log Channel**: {masterlog}"
        )
        if tribes is not None:
            for tribe in tribes:
                channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                if channel is not None:
                    channel = channel.mention
                else:
                    channel = "Channel has been deleted :("
                owner = ctx.guild.get_member(tribes[tribe]["owner"])
                if not tribes[tribe]["allowed"]:
                    allowedmembers = "None Set"
                else:
                    allowedmembers = ""
                    for member in tribes[tribe]["allowed"]:
                        allowedmembers += f"{ctx.guild.get_member(member).mention}\n"
                embed.add_field(
                    name=f"Tribe: {tribe}",
                    value=f"Owner: {owner.mention}\nChannel: {channel}\nAllowed Members: {allowedmembers}"
                )
        await ctx.send(embed=embed)

    # Manual RCON commands
    @_setarktools.command(name="rcon")
    async def rcon(self, ctx: commands.Context, clustername: str, servername: str, *, command: str):
        """Perform an RCON command."""
        settings = await self.config.guild(ctx.guild).all()
        # Check whether user has perms
        userallowed = False
        for role in ctx.author.roles:
            if role.id == settings['fullaccessrole']:
                userallowed = True
            for modrole in settings['modroles']:
                if role.id == modrole:
                    modcmds = settings['modcommands']
                    for cmd in modcmds:
                        if str(cmd.lower()) in command.lower():
                            userallowed = True
        if not userallowed:
            if ctx.guild.owner != ctx.author:
                return await ctx.send("You do not have the required permissions to run that command.")

        # Pull data to send with command to task loop depending on what user designated
        serverlist = []
        clustername = clustername.lower()
        servername = servername.lower()
        if clustername == "all":
            for cluster in settings["clusters"]:
                if servername == "all":
                    for server in settings["clusters"][cluster]["servers"]:
                        settings["clusters"][cluster]["servers"][server]["cluster"] = cluster.lower()
                        serverlist.append(settings["clusters"][cluster]["servers"][server])
                else:
                    if servername in settings["clusters"][cluster]["servers"]:
                        settings["clusters"][cluster]["servers"][servername]["cluster"] = cluster.lower()
                        if not settings["clusters"][cluster]["servers"][servername]:
                            return await ctx.send("Server name not found.")
                        serverlist.append(settings["clusters"][cluster]["servers"][servername])
                    else:
                        return await ctx.send("Server name not found.")
        else:
            if clustername not in settings["clusters"]:
                return await ctx.send("Cluster name not found.")
            elif servername == "all":
                for server in settings["clusters"][clustername]["servers"]:
                    settings["clusters"][clustername]["servers"][server]["cluster"] = clustername
                    serverlist.append(settings["clusters"][clustername]["servers"][server])
            else:
                if servername in settings["clusters"][clustername]["servers"]:
                    settings["clusters"][clustername]["servers"][servername]["cluster"] = clustername
                    if not settings["clusters"][clustername]["servers"][servername]:
                        return await ctx.send("Server name not found.")
                    serverlist.append(settings["clusters"][clustername]["servers"][servername])
                else:
                    return await ctx.send("Server name not found.")

        # Sending manual commands off to the task loop
        mtasks = []
        if command.lower() == "doexit":  # Count down, save world, exit - for clean shutdown
            await ctx.send("Beginning reboot countdown...")
            for i in range(10, 0, -1):
                for server in serverlist:
                    mapchannel = ctx.guild.get_channel(server["chatchannel"])
                    await mapchannel.send(f"Reboot in {i}")
                    await self.process_handler(ctx.guild, server, f"serverchat Reboot in {i}")
                await asyncio.sleep(1)
            await ctx.send("Saving maps...")
            for server in serverlist:
                mapchannel = ctx.guild.get_channel(server["chatchannel"])
                await mapchannel.send(f"Saving map...")
                await self.process_handler(ctx.guild, server, "saveworld")
            await asyncio.sleep(5)
            await ctx.send("Running DoExit...")
            for server in serverlist:
                await self.process_handler(ctx.guild, server, "doexit")

        else:
            for server in serverlist:
                mtasks.append(self.manual_rcon(ctx, server, command))

            async with ctx.typing():
                try:
                    await asyncio.gather(*mtasks)
                except Exception as e:
                    log.exception(f"MANUAL RCON GATHER: {e}")
                    return await ctx.send(f"Command failed to gather")

        if command.lower() == "doexit":
            await ctx.send(f"Saved and rebooted `{len(serverlist)}` servers for `{clustername}` clusters.")
        else:
            await ctx.send(f"Executed `{command}` command on `{len(serverlist)}` servers for `{clustername}` clusters.")

        if "banplayer" in command.lower():
            player_id = int(re.search(r'(\d+)', command).group(1))
            callcommand = f"https://xbl.io/api/v2/friends/remove/{player_id}"
            unfriend = ""
            async with ctx.typing():
                for server in serverlist:
                    if "api" in server:
                        apikey = server["api"]
                        gamertag = server["gamertag"]
                        data, status = await self.apicall(callcommand, apikey)
                        if status == 200:
                            unfriend += f"{gamertag.capitalize()} Successfully unfriended XUID: {player_id}\n"
                        else:
                            unfriend += f"{gamertag.capitalize()} Failed to unfriend XUID: {player_id}\n"
            await ctx.send(box(unfriend, lang="python"))

    # RCON function for manual commands
    async def manual_rcon(self, ctx, serverlist, command):
        try:
            mapn = serverlist['name'].capitalize()
            cluster = serverlist['cluster'].upper()
            res = await rcon.asyncio.rcon(
                command=command,
                host=serverlist['ip'],
                port=serverlist['port'],
                passwd=serverlist['password']
            )
            res = res.rstrip()
            if command.lower() == "listplayers":
                await ctx.send(f"**{mapn} {cluster}**\n"
                               f"{box(res, lang='python')}")
            else:
                await ctx.send(box(f"{mapn} {cluster}\n{res}", lang="python"))
        except WindowsError as e:
            if e.winerror == 121:
                clustername = serverlist['cluster']
                servername = serverlist['name']
                await ctx.send(f"The **{servername}** **{clustername}** server has timed out and is probably down.")
                return
            else:
                log.exception(f"MANUAL RCON WINERROR: {e}")
                return
        except Exception as e:
            if "WinError" not in str(e):
                log.exception(f"MANUAL RCON: {e}")

    # Cache the config on cog load for the task loops to use
    async def initialize(self):
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(int(guildID))
            if not guild:
                continue
            guildsettings = await self.config.guild(guild).clusters()
            if not guildsettings:
                continue
            for cluster in guildsettings:
                if not guildsettings[cluster]:
                    continue
                guildsettings[cluster]["servertoserver"] = False
                globalchatchannel = guildsettings[cluster]["globalchatchannel"]
                adminlogchannel = guildsettings[cluster]["adminlogchannel"]
                joinchannel = guildsettings[cluster]["joinchannel"]
                leavechannel = guildsettings[cluster]["leavechannel"]
                for server in guildsettings[cluster]["servers"]:
                    guildsettings[cluster]["servers"][server]["joinchannel"] = joinchannel
                    guildsettings[cluster]["servers"][server]["leavechannel"] = leavechannel
                    guildsettings[cluster]["servers"][server]["adminlogchannel"] = adminlogchannel
                    guildsettings[cluster]["servers"][server]["globalchatchannel"] = globalchatchannel
                    guildsettings[cluster]["servers"][server]["cluster"] = cluster
                    server = guildsettings[cluster]["servers"][server]
                    self.servercount += 1
                    self.alerts[server["chatchannel"]] = 0
                    self.playerlist[server["chatchannel"]] = []
                    self.taskdata.append([guild.id, server])
                    self.channels.append(server["globalchatchannel"])
                    self.channels.append(server["chatchannel"])
        time = datetime.datetime.utcnow()
        self.time = time.isoformat()
        log.info("Config initialized.")  # If this doesnt log then something is fucky...
        return

    # Xbox API call handler
    async def apicall(self, command, apikey):
        async with self.session.get(command, headers={"X-Authorization": apikey}) as resp:
            status = resp.status
            try:
                data = await resp.json(content_type=None)
            except json.decoder.JSONDecodeError:
                return None, status
            return data, status

    async def apipost(self, url, payload, apikey):
        async with self.session.post(url=url, data=json.dumps(payload),
                                     headers={"X-Authorization": str(apikey)}) as resp:
            status = resp.status
            return status

    async def enumerate_maps_api(self, ctx):
        settings = await self.config.guild(ctx.guild).all()
        map_options = "**Gamertag** - `Map/Cluster`\n"
        servernum = 1
        serverlist = []
        for clustername in settings["clusters"]:
            for servername in settings["clusters"][clustername]["servers"]:
                if "api" in settings["clusters"][clustername]["servers"][servername]:
                    key = settings["clusters"][clustername]["servers"][servername]["api"]
                    gametag = str(settings["clusters"][clustername]["servers"][servername]["gamertag"])
                    cname = clustername.upper()
                    sname = servername.capitalize()
                    map_options += f"**{servernum}.** `{gametag.capitalize()}` - `{sname} {cname}`\n"
                    serverlist.append((servernum, gametag, key))
                    servernum += 1
        map_options += f"**All** - `Adds All Servers`\n"
        return map_options, serverlist

    async def enumerate_maps_all(self, ctx):
        settings = await self.config.guild(ctx.guild).all()
        map_options = "**Map/Cluster**\n"
        servernum = 1
        serverlist = []
        for clustername in settings["clusters"]:
            for servername in settings["clusters"][clustername]["servers"]:
                    cname = clustername.upper()
                    sname = servername.capitalize()
                    map_options += f"**{servernum}.** `{sname} {cname}`\n"
                    serverlist.append((servernum, sname.lower(), cname.lower()))
                    servernum += 1
        return map_options, serverlist

    # Message listener to detect channel message is sent in and sends ServerChat command to designated server
    @commands.Cog.listener("on_message")
    async def chat_toserver(self, message: discord.Message):

        if not message.guild:
            return

        if not message:
            return

        if message.author.bot:
            return

        if message.channel.id not in self.channels:
            return

        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@!{mention.id}>", f"@{mention.name}")
        if message.channel_mentions:
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        if message.role_mentions:
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        clusterchannels, allservers = await self.globalchannelchecker(message.channel)

        chatchannels, map = await self.mapchannelchecker(message.channel)

        if message.channel.id in clusterchannels:
            await self.chat_toserver_rcon(allservers, message)
        if message.channel.id in chatchannels:
            return await self.chat_toserver_rcon(map, message)
        else:
            return

    # Send chat to server(filters any unicode characters or custom discord emojis before hand)
    async def chat_toserver_rcon(self, server, message):
        author = message.author.name
        nolinks = re.sub(r'https?:\/\/[^\s]+', '', message.content)
        noemojis = re.sub(r'<:\w*:\d*>', '', nolinks)
        nocustomemojis = re.sub(r'<a:\w*:\d*>', '', noemojis)
        message = unicodedata.normalize('NFKD', nocustomemojis).encode('ascii', 'ignore').decode()
        normalizedname = unicodedata.normalize('NFKD', author).encode('ascii', 'ignore').decode()
        for data in server:
            try:
                await rcon.asyncio.rcon(
                    command=f"serverchat {normalizedname}: {message}",
                    host=data['ip'],
                    port=data['port'],
                    passwd=data['password'])
                continue
            except Exception as e:
                if "semaphor" in str(e):
                    log.warning("chat_toserver_rcon: Server is probably offline")
                else:
                    log.exception(f"chat_toserver_rcon: {e}")
                continue

    # Returns all channels and servers related to the message
    async def globalchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        clusterchannels = []
        allservers = []
        for cluster in settings["clusters"]:
            if settings["clusters"][cluster]["globalchatchannel"] == channel.id:
                clusterchannels.append(settings["clusters"][cluster]["globalchatchannel"])
                for server in settings["clusters"][cluster]["servers"]:
                    globalchat = settings["clusters"][cluster]["globalchatchannel"]
                    settings["clusters"][cluster]["servers"][server]["globalchatchannel"] = globalchat
                    clusterchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    allservers.append(settings["clusters"][cluster]["servers"][server])
        return clusterchannels, allservers

    # Returns the channel and server related to the message
    async def mapchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        chatchannels = []
        map = []
        for cluster in settings["clusters"]:
            for server in settings["clusters"][cluster]["servers"]:
                if settings["clusters"][cluster]["servers"][server]["chatchannel"] == channel.id:
                    chatchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    map.append(settings["clusters"][cluster]["servers"][server])
        return chatchannels, map

    # Initiates the GetChat loop
    @tasks.loop(seconds=5)
    async def chat_executor(self):
        for data in self.taskdata:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            await self.process_handler(guild, server, "getchat")

    # Initiates the ListPlayers loop for both join/leave logs and status message to use
    @tasks.loop(seconds=60)
    async def playerlist_executor(self):
        for data in self.taskdata:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            channel = server["chatchannel"]
            joinlog = guild.get_channel(server["joinchannel"])
            leavelog = guild.get_channel(server["leavechannel"])
            mapname = server["name"].capitalize()
            clustername = server["cluster"].upper()
            newplayerlist = await self.process_handler(guild, server, "listplayers")

            playerjoin = self.checkplayerjoin(channel, newplayerlist)
            if playerjoin:
                await joinlog.send(
                    f":green_circle: `{playerjoin[0]}, {playerjoin[1]}` joined {mapname} {clustername}")
            playerleft = self.checkplayerleave(channel, newplayerlist)
            if playerleft:
                await leavelog.send(f":red_circle: `{playerleft[0]}, {playerleft[1]}` left {mapname} {clustername}")
            self.playerlist[channel] = newplayerlist

    # For the Discord join log
    def checkplayerjoin(self, channel, newplayerlist):
        if newplayerlist:
            for player in newplayerlist:
                if player not in self.playerlist[channel]:
                    return player

    # For the Discord leave log
    def checkplayerleave(self, channel, newplayerlist):
        if self.playerlist[channel] is not None:
            for player in self.playerlist[channel]:
                if newplayerlist is None:
                    return player
                if player not in newplayerlist:
                    return player

    # Player stat handler
    @tasks.loop(minutes=2)
    async def playerstats(self):
        current_time = datetime.datetime.utcnow()
        last_ran = datetime.datetime.fromisoformat(str(self.time))
        timedifference_raw = current_time - last_ran
        timedifference = timedifference_raw.seconds
        for data in self.taskdata:
            guild = self.bot.get_guild(data[0])
            settings = await self.config.guild(guild).all()
            autofriend = settings["autofriend"]
            autowelcome = settings["autowelcome"]
            server = data[1]
            channel = server["chatchannel"]
            channel_obj = guild.get_channel(channel)
            mapname = server["name"]
            clustername = server["cluster"]
            map_cluster = f"{mapname} {clustername}"
            extralog = await self.config.guild(guild).datalogs()
            async with self.config.guild(guild).playerstats() as stats:
                if self.playerlist[channel]:
                    for player in self.playerlist[channel]:
                        if player[0] not in stats:  # New Player
                            newplayermessage = ""
                            jchannel = settings["clusters"][clustername]["joinchannel"]
                            jchannel = guild.get_channel(jchannel)
                            log.info(f"New Player - {player[0]}")
                            if extralog:
                                newplayermessage += f"**{player[0]}** added to the database.\n"
                            stats[player[0]] = {"playtime": {"total": 0}}
                            stats[player[0]]["xuid"] = player[1]
                            stats[player[0]]["lastseen"] = {
                                "time": current_time.isoformat(),
                                "map": map_cluster
                            }
                            if "api" in settings["clusters"][clustername]["servers"][mapname]:
                                apikey = settings["clusters"][clustername]["servers"][mapname]["api"]
                                gt = settings["clusters"][clustername]["servers"][mapname]["gamertag"]
                                if autowelcome:
                                    link = await channel_obj.create_invite(unique=False, reason="New Player")
                                    if settings["welcomemsg"]:
                                        params = {
                                            "discord": guild.name,
                                            "gamertag": player[0],
                                            "link": link
                                        }
                                        welcome_raw = settings["welcomemsg"]
                                        welcome = welcome_raw.format(**params)
                                    else:
                                        welcome = f"Welcome to {guild.name}!\nThis is an automated message:\n" \
                                                  f"You appear to be a new player, " \
                                                  f"here is an invite to the Discord server:\n\n{link}"
                                    xuid = player[1]
                                    url = "https://xbl.io/api/v2/conversations"
                                    payload = {"xuid": str(xuid), "message": welcome}
                                    log.info(f"Sending DM to XUID - {player[0]}")
                                    status = await self.apipost(url, payload, apikey)
                                    if status == 200:
                                        log.info("New Player DM Successful")
                                        if extralog:
                                            newplayermessage += f"DM sent: ✅\n"
                                    else:
                                        log.warning("New Player DM FAILED")
                                        if extralog:
                                            newplayermessage += f"DM sent: ❌\n"
                                if autofriend:
                                    xuid = player[1]
                                    command = f"https://xbl.io/api/v2/friends/add/{xuid}"
                                    data, status = await self.apicall(command, apikey)
                                    if status == 200:
                                        log.info(f"{gt} Successfully added {player[0]}")
                                        newplayermessage += f"Added by {gt}: ✅\n"
                                    else:
                                        log.warning(f"{gt} FAILED to add {player[0]}")
                                        if extralog:
                                            newplayermessage += f"Added by {gt}: ❌\n"
                            embed = discord.Embed(
                                description=newplayermessage,
                                color=discord.Color.green()
                            )
                            try:
                                await jchannel.send(embed=embed)
                            except discord.HTTPException:
                                log.warning("New Player Message Failed.")
                                pass

                        if map_cluster not in stats[player[0]]["playtime"]:
                            stats[player[0]]["playtime"][map_cluster] = 0
                            continue
                        else:
                            current_map_playtime = stats[player[0]]["playtime"][map_cluster]
                            current_total_playtime = stats[player[0]]["playtime"]["total"]
                            new_map_playtime = int(current_map_playtime) + int(timedifference)
                            new_total = int(current_total_playtime) + int(timedifference)
                            stats[player[0]]["playtime"][map_cluster] = new_map_playtime
                            stats[player[0]]["playtime"]["total"] = new_total
                            stats[player[0]]["lastseen"] = {
                                "time": current_time.isoformat(),
                                "map": map_cluster
                            }
        self.time = current_time.isoformat()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        stats = await self.config.guild(member.guild).playerstats()
        unfriendtasks = []
        for gt in stats:
            if "discord" in stats[gt]:
                if member.id == stats[gt]["discord"]:
                    xuid = stats[gt]["xuid"]
                    clusters = await self.config.guild(member.guild).clusters()
                    for cname in clusters:
                        for sname in clusters[cname]["servers"]:
                            if "api" in clusters[cname]["servers"][sname]:
                                apikey = clusters[cname]["servers"][sname]["api"]
                                mapgt = clusters[cname]["servers"][sname]["api"]
                                command = f"https://xbl.io/api/v2/friends/remove/{xuid}"
                                unfriendtasks.append(self.leaveunfriend(command, apikey, gt, mapgt))
        await asyncio.gather(*unfriendtasks)

    async def leaveunfriend(self, command, apikey, gt, mapgt):
        async with self.session.get(command, headers={"X-Authorization": apikey}) as resp:
            if resp.status == 200:
                log.info(f"{mapgt} successfully unfriended {gt}")

    # Unfriends gamertags if they havent been seen on any server after a certain period of time
    @tasks.loop(hours=2)
    async def player_maintenance(self):
        current_time = datetime.datetime.utcnow()
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(int(guildID))
            if not guild:
                continue
            extralog = await self.config.guild(guild).datalogs()
            async with self.config.guild(guild).all() as settings:
                if settings["autofriend"]:
                    days = settings["unfriendafter"]
                    for gamertag in settings["playerstats"]:
                        xuid = settings["playerstats"][gamertag]["xuid"]
                        rawtime = settings["playerstats"][gamertag]["lastseen"]["time"]
                        if rawtime is None:
                            continue
                        timestamp = datetime.datetime.fromisoformat(rawtime)
                        timedifference_raw = current_time - timestamp
                        timedifference = timedifference_raw.days
                        if timedifference >= days - 2:
                            unfriendmsg = f"Hello {gamertag}, long time no see!\nThis is an automated message:\n" \
                                          f"We noticed you have not been detected on any of the servers  in {days - 2} days.\n" \
                                          f"If you are not detected in the server within 2 days, You will be " \
                                          f"automatically unfriended by the host Gamertags.\n" \
                                          f"Once unfriended, you will need to re-register your Gamertag in our Discord" \
                                          f" to play on the servers.\n" \
                                          f"Hope to see you back soon :)"
                            url = "https://xbl.io/api/v2/conversations"
                            payload = {"xuid": str(xuid), "message": unfriendmsg}
                            apikey = await self.pullkey(settings)
                            log.info(f"Sending DM to XUID - {xuid}")
                            status = await self.apipost(url, payload, apikey)
                            if status == 200:
                                log.info(f"Successfully warned {gamertag}")
                            else:
                                log.warning(f"Failed to warn {gamertag}")

                        if timedifference >= days:
                            settings["playerstats"][gamertag]["lastseen"]["time"] = None
                            command = f"https://xbl.io/api/v2/friends/remove/{xuid}"
                            for cluster in settings["clusters"]:
                                lchannel = settings["clusters"][cluster]["leavechannel"]
                                lchannel = guild.get_channel(lchannel)
                                for server in settings["clusters"][cluster]["servers"]:
                                    if "api" in settings["clusters"][cluster]["servers"][server]:
                                        apikey = settings["clusters"][cluster]["servers"][server]["api"]
                                        gt = settings["clusters"][cluster]["servers"][server]["gamertag"]
                                        data, status = await self.apicall(command, apikey)
                                        color = discord.Color.red()
                                        if status == 200:
                                            embed = discord.Embed(
                                                description=f"{gt} unfriended {gamertag}"
                                                            f" for not being active for {days}days",
                                                color=color
                                            )
                                            if extralog:
                                                await lchannel.send(embed=embed)
                                            log.info(f"{gt} Successfully unfriended {gamertag}")
                                        else:
                                            embed = discord.Embed(
                                                description=f"{gt} Failed to unfriend {gamertag}"
                                                            f" for not being active for {days}days",
                                                color=color
                                            )
                                            if extralog:
                                                await lchannel.send(embed=embed)
                                            log.warning(f"{gt} Failed to unfriend {gamertag}")

    # Creates and maintains an embed of all active servers and player counts
    @tasks.loop(seconds=60)
    async def status_channel(self):
        data = await self.config.all_guilds()
        for guildID in data:
            guild = self.bot.get_guild(int(guildID))
            thumbnail = STATUS
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            if not settings:
                continue
            status = ""
            totalplayers = 0
            for cluster in settings["clusters"]:
                clustertotal = 0
                clustername = cluster.upper()
                if not settings["clusters"]:
                    continue
                status += f"**{clustername}**\n"
                for server in settings["clusters"][cluster]["servers"]:
                    channel = settings["clusters"][cluster]["servers"][server]["chatchannel"]
                    if not channel:
                        continue

                    # Get cached player count data
                    playercount = self.playerlist[channel]

                    count = self.alerts[channel]
                    if playercount is None:
                        thumbnail = FAILED
                        inc = "Minutes."
                        if count >= 60:
                            count = count / 60
                            inc = "Hours."
                            count = int(count)

                        status += f"{guild.get_channel(channel).mention}: Offline for {count} {inc}\n"
                        alertmsg = guild.get_channel(settings["clusters"][cluster]["adminlogchannel"])
                        mentions = discord.AllowedMentions(roles=True)
                        pingrole = guild.get_role(settings['fullaccessrole'])
                        if count == 5:
                            await alertmsg.send(f"{pingrole.mention}, "
                                                f"The **{server}** server has been offline for 5 minutes now!!!",
                                                allowed_mentions=mentions)
                            self.alerts[channel] += 1
                            continue
                        else:
                            self.alerts[channel] += 1
                            continue

                    if playercount is []:
                        status += f"{guild.get_channel(channel).mention}: 0 Players\n"
                        if count > 0:
                            self.alerts[channel] = 0
                        continue

                    playercount = len(playercount)
                    clustertotal += playercount
                    totalplayers += playercount
                    if playercount == 1:
                        status += f"{guild.get_channel(channel).mention}: {playercount} player\n"
                    else:
                        status += f"{guild.get_channel(channel).mention}: {playercount} players\n"

                if clustertotal == 1:
                    status += f"`{clustertotal}` player in the cluster\n\n"
                else:
                    status += f"`{clustertotal}` players in the cluster\n\n"

            messagedata = await self.config.guild(guild).statusmessage()
            channeldata = await self.config.guild(guild).statuschannel()
            if not channeldata:
                continue

            # Embed setup
            eastern = pytz.timezone('US/Eastern')  # Might make this configurable in the future
            time = datetime.datetime.now(eastern)
            embed = discord.Embed(
                timestamp=time,
                color=discord.Color.random(),
                description=status
            )
            embed.set_author(name="Server Status", icon_url=guild.icon_url)
            embed.add_field(name="Total Players", value=f"`{totalplayers}`")
            embed.set_thumbnail(url=thumbnail)
            destinationchannel = guild.get_channel(channeldata)
            msgtoedit = None

            if messagedata:
                try:
                    msgtoedit = await destinationchannel.fetch_message(messagedata)
                except discord.NotFound:
                    log.info(f"Status message not found. Creating new message.")

            if not msgtoedit:
                await self.config.guild(guild).statusmessage.set(None)
                message = await destinationchannel.send(embed=embed)
                await self.config.guild(guild).statusmessage.set(message.id)
            if msgtoedit:
                try:
                    return await msgtoedit.edit(embed=embed)
                except discord.Forbidden:  # Probably imported config from another bot and cant edit the message
                    await self.config.guild(guild).statusmessage.set(None)
                    message = await destinationchannel.send(embed=embed)
                    await self.config.guild(guild).statusmessage.set(message.id)

    # Executes all task loop RCON commands synchronously in another thread
    # Process is synchronous for easing network buffer and keeping network traffic manageable
    async def process_handler(self, guild, server, command):
        if command == "getchat":
            timeout = 1
        elif command == "listplayers":
            timeout = 10
        else:
            timeout = 3

        def rcon():
            try:
                with Client(server['ip'], server['port'], passwd=server['password'], timeout=timeout) as client:
                    result = client.run(command)
                    return result
            except WindowsError as e:
                if e.winerror == 121:
                    log.exception(f"PROCESS HANDLER 121: {e}")
                if e.winerror == 10038:
                    log.exception(f"PROCESS HANDLER 10038: {e}")
                return None

        res = await self.bot.loop.run_in_executor(None, rcon)
        if res:
            if "getchat" in command:
                await self.message_handler(guild, server, res)
            if "listplayers" in command:
                regex = r"(?:[0-9]+\. )(.+), ([0-9]+)"
                playerlist = re.findall(regex, res)
                return playerlist
        else:
            return None

    # Sends messages to their designated channels from the in-game chat
    async def message_handler(self, guild, server, res):
        if "Server received, But no response!!" in res:  # Common response from an Online server with no new messages
            return
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        sourcename = server["name"]
        msgs = res.split("\n")
        messages = []
        settings = await self.config.guild(guild).all()
        badnames = settings["badnames"]
        for msg in msgs:
            if msg.startswith("AdminCmd:"):
                adminmsg = msg
                await adminlog.send(f"**{server['name'].capitalize()}**\n{box(adminmsg, lang='python')}")
            elif "Tribe" and ", ID" in msg:
                await self.tribelog_formatter(guild, server, msg)
            elif msg.startswith('SERVER:'):
                continue
            elif ":" not in msg:
                continue
            else:
                messages.append(msg)
                for names in badnames:
                    if f"({names.lower()}): " in msg.lower():
                        reg = r"(.+)\s\("
                        regname = re.findall(reg, msg)
                        for name in regname:
                            await self.process_handler(guild, server, f'renameplayer "{names.lower()}" {name}')
                            await chatchannel.send(f"A player named `{names}` has been renamed to `{name}`.")
        for msg in messages:
            if msg == ' ':
                continue
            elif msg == '':
                continue
            elif msg is None:
                continue
            else:
                if "discord" in msg.lower() or "discordia" in msg.lower():
                    try:
                        link = await chatchannel.create_invite(unique=False, max_age=3600, reason="Ark Auto Response")
                        await self.process_handler(guild, server, f"serverchat {link}")
                    except Exception as e:
                        log.exception(f"INVITE CREATION FAILED: {e}")

                await chatchannel.send(msg)
                await globalchat.send(f"{chatchannel.mention}: {msg}")
                clustername = server["cluster"]
                if settings["clusters"][clustername]["servertoserver"] is True:  # maps can talk to each other if true
                    for data in self.taskdata:
                        mapn = data[1]
                        if mapn["cluster"] is server["cluster"] and mapn["name"] is not sourcename:
                            await self.process_handler(guild, mapn, f"serverchat {sourcename.capitalize()}: {msg}")

    # Handles tribe log formatting/itemizing
    async def tribelog_formatter(self, guild, server, msg):
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
            description=f"{box(action)}"
        )
        embed.set_footer(text=f"{time} | Tribe ID: {tribe_id}")
        await self.tribe_handler(guild, tribe_id, embed)

    # Handles sending off tribe logs to their designated channels
    async def tribe_handler(self, guild, tribe_id, embed):
        settings = await self.config.guild(guild).all()
        if "masterlog" in settings.keys():
            masterlog = guild.get_channel(settings["masterlog"])
            await masterlog.send(embed=embed)
        if "tribes" in settings.keys():
            for tribes in settings["tribes"]:
                if tribe_id == tribes:
                    tribechannel = guild.get_channel(settings["tribes"][tribes]["channel"])
                    await tribechannel.send(embed=embed)

    # Refresh all task loops
    @tasks.loop(seconds=3600)
    async def loop_refresher(self):
        self.chat_executor.cancel()
        self.playerlist_executor.cancel()
        await asyncio.sleep(5)
        self.chat_executor.start()
        self.playerlist_executor.start()

    # Initialize the config before the chat loop starts
    @loop_refresher.before_loop
    async def before_loop_refresher(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(3600)
        log.info("Loop refresher ready.")

    # Initialize the config before the chat loop starts
    @chat_executor.before_loop
    async def before_chat_executor(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(3)
        log.info("Chat executor ready.")

    # Nothing special before playerlist executor
    @playerlist_executor.before_loop
    async def before_playerlist_executor(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(2)
        log.info("Playerlist executor ready.")

    # Initialize cache before logging playerstats
    @playerstats.before_loop
    async def before_playerstatst(self):
        await self.bot.wait_until_red_ready()
        await self.initialize()
        await asyncio.sleep(1)
        log.info("Player stat tracking ready.")

    # Sleep before starting so playerlist executor has time to gather the player list
    @status_channel.before_loop
    async def before_status_channel(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(15)  # Gives playerlist executor time to gather player count
        log.info("Status monitor ready.")

    # More of a test command to make sure a unicode discord name can be properly filtered with the unicodedata lib
    @_setarktools.command(name="checkname")
    async def _checkname(self, ctx):
        """
        View what your name looks like In-game.
        If your name looks fine and there are no errors then you're good to go.
        """
        try:
            normalizedname = unicodedata.normalize('NFKD', ctx.message.author.name).encode('ascii', 'ignore').decode()
            await ctx.send(f"Filtered name: {normalizedname}")
            await ctx.send(f"Unfiltered name: {ctx.message.author.name}")
        except Exception as e:
            await ctx.send(f"Looks like your name broke the code, please pick a different name.\nError: {e}")

    # Sends guild config to the channel the command was invoked from as a json file
    @commands.command(name="backup")
    @commands.guildowner()
    async def _backup(self, ctx):
        """Create backup of config and send to Discord."""
        settings = await self.config.guild(ctx.guild).all()
        settings = json.dumps(settings)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(settings)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}.json"))

    # Restore config from a json file attached to command message
    @commands.command(name="restore")
    @commands.guildowner()
    async def _restore(self, ctx):
        """Upload a backup file to restore config."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.guild(ctx.guild).set(config)
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    # Refreshes the main task loops if needed for some reason.
    @commands.command(name="refresh")
    async def _refresh(self, ctx):
        """Refresh the task loops"""
        settings = await self.config.guild(ctx.guild).all()
        # Check whether user has perms
        userallowed = False
        for role in ctx.author.roles:
            if role.id == settings['fullaccessrole']:
                userallowed = True
            for modrole in settings['modroles']:
                if role.id == modrole:
                    userallowed = True

        if not userallowed:
            if ctx.guild.owner != ctx.author:
                return await ctx.send("You do not have the required permissions to run that command.")
        async with ctx.typing():
            self.chat_executor.cancel()
            self.playerlist_executor.cancel()
            self.status_channel.cancel()
            await asyncio.sleep(5)
            self.chat_executor.start()
            self.playerlist_executor.start()
            self.status_channel.start()
            return await ctx.send("Task loops refreshed")
