import asyncio
import datetime
import json
import re

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box


class DayZTools(commands.Cog):
    """
    Tools for DayZ!
    """
    __author__ = "Vertyco"
    __version__ = "0.1.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117117117117, force_registration=True)
        default_guild = {
            "ntoken": None,
            "killfeed": None,
            "statuschannel": None,
            "statusmessage": None,
            "playerlog": None,
            "playerstats": {}
        }
        self.config.register_guild(**default_guild)

        # Cached data
        self.playerlist = {}
        self.servercache = {}
        self.killfeed = {}

        # Start da loops broother
        self.server_cache.start()
        self.server_logs.start()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        self.server_cache.cancel()
        self.server_logs.cancel()

    # Cache server data every 60 seconds
    @tasks.loop(seconds=60)
    async def server_cache(self, ctx=None):
        data = await self.config.all_guilds()
        for guild_id in data:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            if not settings:
                continue
            if not settings["ntoken"]:
                continue
            ntoken = settings["ntoken"]
            header = {"Authorization": f"Bearer {ntoken}"}
            services_req = "https://api.nitrado.net/services"
            # Make get request to services with token header
            async with self.session.get(services_req, headers=header) as service:
                service_data = await service.json()
                if service_data["status"] == "error":
                    return service_data
                # Save service ID
                self.servercache[guild_id] = {}
                self.playerlist[guild.id] = {}
                self.killfeed[guild.id] = {}
                for item in service_data["data"]["services"]:
                    service_id = item["id"]
                    info_req = f"https://api.nitrado.net/services/{service_id}:id/gameservers"
                    # Make another request to get game server info with id
                    async with self.session.get(info_req, headers=header) as info:
                        info_data = await info.json()
                        # save username, user id, ip, port, query_port, memory_mb,
                        # game_raw(dayzxb or dayzps), game_human,
                        # last update, version, player_current, Player_max
                        server = info_data["data"]["gameserver"]
                        if "version" in server["query"]:
                            version = server["query"]["version"]
                        else:
                            version = "Unknown"
                        if "player_current" in server["query"]:
                            players = server["query"]["player_current"]
                        else:
                            players = "None"
                        if "player_max" in server["query"]:
                            playermax = server["query"]["player_max"]
                        else:
                            playermax = "Unknown"
                        self.servercache[guild_id][service_id] = {
                            "user": server["username"],
                            "user_id": server["user_id"],
                            "ip": server["ip"],
                            "port": server["port"],
                            "query": server["query_port"],
                            "memory": server["memory_mb"],
                            "game_raw": server["game"],
                            "game_name": server["game_human"],
                            "status": server["status"],
                            "location": server["location"],
                            "version": version,
                            "last_update": server["game_specific"]["last_update"],
                            "players": players,
                            "playermax": playermax,
                            "service_id": server["service_id"],
                            "ntoken": ntoken
                        }
            await self.server_status(guild)
            return service_data

    # Maintains an embed of server info
    async def server_status(self, guild):
        channeldata = await self.config.guild(guild).statuschannel()
        messagedata = await self.config.guild(guild).statusmessage()
        if not channeldata:
            return
        embed = discord.Embed(
            timestamp=datetime.datetime.utcnow(),
            title=f"Server Status",
            color=discord.Color.random(),
            description=f"{guild.name}'s servers\n"
        )
        for item in self.servercache[guild.id]:
            server = self.servercache[guild.id][item]
            memory = server["memory"]
            game_name = server["game_name"]
            version = server["version"]
            last_update = server["last_update"]
            if last_update is not None:
                time = datetime.datetime.fromisoformat(last_update)
                time = time.strftime('%m/%d/%Y at %H:%M:%S')
            else:
                time = "Unknown"
            players = server["players"]
            playermax = server["playermax"]
            status = server["status"]
            location = server["location"]

            # Embed setup
            embed.set_thumbnail(url=guild.icon_url)
            embed.add_field(
                name=f"{game_name} Info",
                value=f"**Players:** `{players}/{playermax}`"
                      f"Server Status: `{status}`\n"
                      f"Current Version: `{version}`\n"
                      f"Last Updated: `{time}`\n"
                      f"Location: `{location}`\n"
                      f"Memory: `{memory} MB`",
                inline=False
            )
        channel = guild.get_channel(channeldata)

        msgtoedit = None

        if messagedata:
            try:
                msgtoedit = await channel.fetch_message(messagedata)
            except discord.NotFound:
                print(f"DayZ Tools Status message not found. Creating new message.")

        if not msgtoedit:
            await self.config.guild(guild).statusmessage.set(None)
            message = await channel.send(embed=embed)
            await self.config.guild(guild).statusmessage.set(message.id)
        if msgtoedit:
            await msgtoedit.edit(embed=embed)

    @server_cache.before_loop
    async def before_server_cache(self):
        await self.bot.wait_until_red_ready()
        print(f"DayZ server cache ready...")

    @tasks.loop(seconds=40)
    async def server_logs(self):
        data = await self.config.all_guilds()
        for guild_id in data:
            guild = self.bot.get_guild(int(guild_id))
            settings = await self.config.guild(guild).all()
            if guild_id in self.servercache:
                servers = self.servercache[guild_id]
            else:
                continue
            for server in servers:
                user = servers[server]["user"]
                sid = servers[server]["service_id"]
                ntoken = servers[server]["ntoken"]
                header = {"Authorization": f"Bearer {ntoken}"}
                game = servers[server]["game_raw"]
                if game == "dayzxb":
                    logpath = "dayzxb/config/DayZServer_X1_x64.ADM"
                else:
                    logpath = "dayzps/config/DayZServer_PS4_x64.ADM"
                log_req = f"https://api.nitrado.net/services/{sid}:id/gameservers/file_server/download?file=/games/{user}/noftp/{logpath}"
                async with self.session.get(log_req, headers=header) as geturl:
                    data = await geturl.json()
                    if "data" in data:
                        url = data["data"]["token"]["url"]
                        async with self.session.get(url, headers=header) as logs:
                            logs_raw = await logs.text()
                            await self.log_handler(logs_raw, guild, settings, server)

    @server_logs.before_loop
    async def before_server_logs(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)

    # Handles logs and sends to respective channel
    async def log_handler(self, logs_raw, guild, settings, server):
        logs = logs_raw.split("\n")
        newkillfeed = ""
        newplayerlist = ""
        for log in logs:
            if "connected" in log or "disconnected" in log:
                newplayerlist += f"{log}\n"
            if "(DEAD)" in log or "committed suicide" in log:
                newkillfeed += f"{log}\n"
        await self.playerlogging(newplayerlist, guild, settings, server)
        await self.killfeeder(newkillfeed, guild, settings, server)

    # Handles killfeed
    async def killfeeder(self, newkillfeed, guild, settings, server):
        klog = guild.get_channel(settings["killfeed"])
        klogs = newkillfeed.split("\n")
        if server not in self.killfeed[guild.id]:
            self.killfeed[guild.id][server] = newkillfeed
            return
        else:
            for line in klogs:
                if not line:
                    continue
                timestamp = str(re.search(r'(..:..:..)', line).group(1))
                victim = str(re.search(r'"(.+?)"', line).group(1))

                if "committed suicide" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        embed = discord.Embed(
                            title=f"💀 Suicide | {timestamp}",
                            description=f"**{victim}** took the cowards way out.",
                            color=discord.Color.dark_grey()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "hit by explosion" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        explosion = str(re.search(r'n \((.+?)\)$', line).group(1))
                        embed = discord.Embed(
                            title=f"💀 Exploded | {timestamp}",
                            description=f"**{victim}** died from explosion ({explosion})",
                            color=discord.Color.orange()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "killed by Player" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        killer = str(re.search(r'killed by Player "(.*?)"', line).group(1))
                        coords = str(re.search(r'pos=<(.*?)>', line).group(1))
                        weapon = str(re.search(r' with (.*) from', line).group(1))
                        try:
                            distance = round(float(re.search(r'from ([0-9.]+) meters', line).group(1)), 2)
                        except AttributeError as e:
                            distance = 0.0
                            print("Distance of killer failed to calculate")

                        embed = discord.Embed(
                            title=f"💀 PvP Kill | {timestamp}",
                            description=f"**{killer}** killed **{victim}**\n**Weapon**: `{weapon}` ({distance}m)\n**Location**: {coords}",
                            color=discord.Color.red()
                        )
                        embed.set_thumbnail(url="https://i.imgur.com/bH8tA1v.png")
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "bled out" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        embed = discord.Embed(
                            title=f"🩸 Bleed Out | {timestamp}",
                            description=f"**{victim}** ran out of blood",
                            color=discord.Color.dark_red()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "Animal_CanisLupus_Grey" in line or "Animal_CanisLupus_White" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        embed = discord.Embed(
                            title=f"🐺 Wolf Kill | {timestamp}",
                            description=f"**{victim}** was killed by a Wolf!",
                            color=discord.Color.light_grey()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "Animal_UrsusArctos" in line or "Brown Bear" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        embed = discord.Embed(
                            title=f"🐻 Beary Unfortunate | {timestamp}",
                            description=f"**{victim}** was killed by a Bear!",
                            color=discord.Color.dark_purple()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                elif "hit by FallDamage" in line:
                    k = self.checkfeed(guild, line, server)
                    if k:
                        embed = discord.Embed(
                            title=f"💀 Splattered | {timestamp}",
                            description=f"**{victim}** tried to fly!",
                            color=discord.Color.magenta()
                        )
                        await klog.send(embed=embed)
                        await asyncio.sleep(2)
                else:
                    continue

            self.killfeed[guild.id][server] = newkillfeed

    def checkfeed(self, guild, line, server):
        if line not in self.killfeed[guild.id][server]:
            return line

    # Handles player join/leaves
    async def playerlogging(self, newplayerlist, guild, settings, server):
        plog = guild.get_channel(settings["playerlog"])
        regex = r'(..:..:..).+"(.+)".+(\bconnected|disconnected)'
        newplayerlist = re.findall(regex, newplayerlist)
        if server not in self.playerlist[guild.id]:
            self.playerlist[guild.id][server] = newplayerlist
            return
        else:
            for player in newplayerlist:
                if player[2] == "connected":
                    p = self.checkplayers(guild, player, server)
                    if p:
                        await plog.send(f":green_circle: `{p[1]}` has connected to the server. - `{p[0]}`")
                        await asyncio.sleep(2)

                elif player[2] == "disconnected":
                    p = self.checkplayers(guild, player, server)
                    if p:
                        await plog.send(f":red_circle: `{p[1]}` has left the server. - `{p[0]}`")
                        await asyncio.sleep(2)

            self.playerlist[guild.id][server] = newplayerlist

    def checkplayers(self, guild, player, server):
        if player not in self.playerlist[guild.id]:
            return player

    # GROUPS
    @commands.group(name="dayztools", aliases=["dzt", "dz"])
    async def dayz_tools(self, ctx):
        """DayZ Tools base command"""
        pass

    # Save nitrado token
    @dayz_tools.command()
    @commands.guildowner()
    async def tokenset(self, ctx, nitrado_token=None):
        """Set your Nitrado token"""
        if nitrado_token is None:
            embed = discord.Embed(
                title="How to obtain your Nitrado Token",
                description="Before you can use this cog, you must set a token obtained from Nitrado's dev portal."
            )
            embed.add_field(
                name="Get Token",
                value="**[CLICK HERE TO GO TO THE DEV PORTAL](https://server.nitrado.net/usa/developer/tokens)**",
                inline=False
            )
            embed.add_field(
                name="Step 1",
                value="Sign into the portal with your Nitrado account",
                inline=False
            )
            embed.add_field(
                name="Step 2",
                value="Check the `service` and `user_info` boxes, then click the `Create` button",
                inline=False
            )
            embed.add_field(
                name="Step 3",
                value=f"Set your token with `{ctx.prefix}dayztools tokenset <YourToken>`",
                inline=False
            )
            return await ctx.send(embed=embed)
        else:
            async with ctx.typing():
                await self.config.guild(ctx.guild).ntoken.set(nitrado_token)
                data = await self.server_cache(ctx)
                if data["status"] == "error":
                    message = data["message"]
                    color = discord.Color.red()
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        print("Couldnt find message to delete")
                    return await ctx.send(embed=discord.Embed(description=f"❌ {message}", color=color))
                else:
                    try:
                        await ctx.message.delete()
                    except discord.NotFound:
                        print("Couldnt find message to delete")
                    color = discord.Color.green()
                    await ctx.send(embed=discord.Embed(description=f"✅ Your token has been set!", color=color))

    @dayz_tools.command()
    @commands.guildowner()
    async def setstatuschannel(self, ctx, channel: discord.TextChannel):
        """Set a channel for server status to be shown."""
        await self.config.guild(ctx.guild).statuschannel.set(channel.id)
        color = discord.Color.green()
        await ctx.send(embed=discord.Embed(description=f"✅ Status channel has been set!", color=color))

    @dayz_tools.command()
    @commands.guildowner()
    async def setplayerlog(self, ctx, channel: discord.TextChannel):
        """Set a channel for player joins/leaves to be logged."""
        await self.config.guild(ctx.guild).playerlog.set(channel.id)
        color = discord.Color.green()
        await ctx.send(embed=discord.Embed(description=f"✅ Playerlog has been set!", color=color))

    @dayz_tools.command()
    @commands.guildowner()
    async def setkillfeed(self, ctx, channel: discord.TextChannel):
        """Set a channel for the KillFeed to be logged."""
        await self.config.guild(ctx.guild).killfeed.set(channel.id)
        color = discord.Color.green()
        await ctx.send(embed=discord.Embed(description=f"✅ KillFeed has been set!", color=color))

    # For testing or visual purposes
    @dayz_tools.command()
    @commands.guildowner()
    async def dzcache(self, ctx):
        """Get the bot's raw cached server info from nitrado"""
        guild = ctx.guild.id
        server = self.servercache[guild]
        msg = json.dumps(server, indent=4, sort_keys=True)[:2030]
        await ctx.send(box(f"{msg}", lang="json"))

    # Setting overview
    @dayz_tools.command()
    @commands.guildowner()
    async def view(self, ctx):
        """View current cog settings"""
        settings = await self.config.guild(ctx.guild).all()
        if settings["ntoken"]:
            ntoken = "Set!"
        else:
            ntoken = "Not Set"
        if settings["killfeed"]:
            killfeed = ctx.guild.get_channel(settings["killfeed"]).mention
        else:
            killfeed = "Not Set"
        if settings["playerlog"]:
            playerlog = ctx.guild.get_channel(settings["playerlog"]).mention
        else:
            playerlog = "Not Set"
        if settings["statuschannel"]:
            statuschannel = ctx.guild.get_channel(settings["statuschannel"]).mention
        else:
            statuschannel = "Not Set"
        embed = discord.Embed(
            title="Cog settings",
            description=f"**Nitrado Token:** {ntoken}\n"
                        f"**KillFeed Channel:** {killfeed}\n"
                        f"**Playerlog Channel:** {playerlog}\n"
                        f"**Status Channel:** {statuschannel}\n"
        )
        await ctx.send(embed=embed)

    # GET REQUESTS
    async def apiget(self, req, header):
        pass

    # POST REQUESTS
    async def apipost(self, req, header):
        async with self.session.post(req, headers=header) as resp:
            data = await resp.text()
            data = json.loads(data)
            return data

    # SERVER COMMANDS
    @dayz_tools.command()
    @commands.admin()
    async def restart(self, ctx):
        """Restart the server"""
        async with ctx.typing():
            settings = await self.config.guild(ctx.guild).all()
            ntoken = settings["ntoken"]
            if not ntoken:
                return await ctx.send("No API token has been set!")
            else:
                for server in self.servercache[ctx.guild.id]:
                    sid = server["service_id"]
                    restart = f"https://api.nitrado.net/services/{sid}:id/gameservers/restart"
                    header = {"Authorization": f"Bearer {ntoken}"}
                    res = await self.apipost(restart, header)
                    status = res["status"]
                    if status == "success":
                        return await ctx.send(f"Server reboot initiated for id: {server}...")
                    else:
                        return await ctx.send(f"Server failed to reboot for id: {server}...")

    @dayz_tools.command()
    @commands.admin()
    async def stop(self, ctx):
        """Stop the server"""
        async with ctx.typing():
            settings = await self.config.guild(ctx.guild).all()
            ntoken = settings["ntoken"]
            if not ntoken:
                return await ctx.send("No API token has been set!")
            else:
                for server in self.servercache[ctx.guild.id]:
                    sid = server["service_id"]
                    stop = f"https://api.nitrado.net/services/{sid}:id/gameservers/stop"
                    header = {"Authorization": f"Bearer {ntoken}"}
                    res = await self.apipost(stop, header)
                    status = res["status"]
                    if status == "success":
                        return await ctx.send(f"Server stopped for id: {server}...")
                    else:
                        return await ctx.send(f"Server failed to stop for id: {server}...")
