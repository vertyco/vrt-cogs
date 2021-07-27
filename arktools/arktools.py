from redbot.core.utils.chat_formatting import box, pagify
from redbot.core import commands, Config
from discord.ext import tasks
from rcon import Client
import rcon
import discord
import datetime
import pytz
import unicodedata
import asyncio
import os
import json
import re

class ArkTools(commands.Cog):
    """
    RCON tools and crosschat for Ark: Survival Evolved!
    """
    __author__ = "Vertyco"
    __version__ = "1.0.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "statuschannel": None,
            "statusmessage": None,
            "clusters": {},
            "servers": {},
            "servername": {},
            "ip": {},
            "port": {},
            "password": {},
            "chatchannel": {},
            "modroles": [],
            "modcommands": [],
            "badnames": [],
            "fullaccessrole": None,
            "tribelogchannels": {},
            "apikeys": {},
            "crosschattoggle": False,
            "joinchannel": {},
            "leavechannel": {},
            "adminlogchannel": {},
            "globalchatchannel": {}
        }
        self.config.register_guild(**default_guild)

        # Cache
        self.taskdata = []
        self.playerlist = {}

        # Loops
        self.chat_executor.start()
        self.playerlist_executor.start()
        self.status_channel.start()

    def cog_unload(self):
        self.chat_executor.cancel()
        self.playerlist_executor.cancel()
        self.status_channel.cancel()



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

    @_setarktools.group(name="server")
    @commands.guildowner()
    async def _serversettings(self, ctx: commands.Context):
        """Server setup."""
        pass


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


    # SERVER SETTINGS COMMANDS
    @_serversettings.command(name="addcluster")
    async def _addcluster(self, ctx: commands.Context,
                          clustername: str,
                          joinchannel: discord.TextChannel,
                          leavechannel: discord.TextChannel,
                          adminlogchannel: discord.TextChannel,
                          globalchatchannel: discord.TextChannel):
        """Add a cluster with specified log channels."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                await ctx.send("Cluster already exists")
            else:
                clusters[clustername] = {
                    "joinchannel": joinchannel.id,
                    "leavechannel": leavechannel.id,
                    "adminlogchannel": adminlogchannel.id,
                    "globalchatchannel": globalchatchannel.id,
                    "servers": {}
                }
                await ctx.send(f"**{clustername}** has been added to the list of clusters.")

    @_serversettings.command(name="delcluster")
    async def _delcluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername]
                await ctx.send(f"{clustername} cluster has been deleted")


    @_serversettings.command(name="addserver")
    async def _addserver(self, ctx: commands.Context, clustername: str, servername: str, ip: str,
                         port: int, password: str, channel: discord.TextChannel):
        """Add a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                if servername in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server was **overwritten** in the **{clustername}** cluster!")
                if servername not in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")
            clusters[clustername]["servers"][servername] = {
                "name": servername,
                "ip": ip,
                "port": port,
                "password": password,
                "chatchannel": channel.id
            }
            if clustername not in clusters.keys():
                await ctx.send(f"The cluster {clustername} does not exist!")

    @_serversettings.command(name="delserver")
    async def _delserver(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            server = clusters[clustername]["servers"]
            if servername in server.keys():
                del clusters[clustername]["servers"][servername]
                await ctx.send(f"{servername} server has been removed from {clustername}")
            else:
                await ctx.send(f"{servername} server not found.")

    @_serversettings.command(name="setstatuschannel")
    async def _setstatuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a channel for a server status embed."""
        await self.config.guild(ctx.guild).statuschannel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    # VIEW SETTINGSs
    @_permissions.command(name="view")
    async def _viewperms(self, ctx: commands.Context):
        """View current permission settings."""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        statuschannel = ctx.guild.get_channel(settings['statuschannel'])
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
        except Exception:
            await ctx.send(f"Setup permissions first.")

    @_serversettings.command(name="view")
    async def _viewsettings(self, ctx: commands.Context):
        """View current server settings."""
        settings = await self.config.guild(ctx.guild).all()
        serversettings = ""
        for pv in settings["clusters"]:
            serversettings += f"**{pv.upper()} Cluster**\n"
            for k, v in settings["clusters"][pv].items():
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
            for server in settings["clusters"][pv]["servers"]:
                for k, v in settings["clusters"][pv]["servers"][server].items():
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
                serversettings += "\n"

        color = discord.Color.dark_purple()
        embed = discord.Embed(
            title=f"**Server Settings**",
            color=color,
            description=f"{serversettings}"
        )
        await ctx.send(embed=embed)


    #####################################################################RCON
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
                        if command.lower() == cmd:
                            userallowed = True
        if not userallowed:
            if ctx.guild.owner != ctx.author:
                return await ctx.send("You do not have the required permissions to run that command.")

        # data setup logic to send commands to task loop
        serverlist = []
        if clustername != "all":
            if clustername not in settings["clusters"]:
                return await ctx.send("Cluster name not found.")
            if servername == "all":
                for server in settings["clusters"][clustername]["servers"]:
                    settings["clusters"][clustername]["servers"][server]["cluster"] = clustername
                    serverlist.append(settings["clusters"][clustername]["servers"][server])
            if servername != "all":
                settings["clusters"][clustername]["servers"][servername]["cluster"] = clustername
                if servername not in settings["clusters"][clustername]["servers"]:
                    return await ctx.send("Server name not found.")
                serverlist.append(settings["clusters"][clustername]["servers"][servername])
        if clustername == "all":
            for cluster in settings["clusters"]:
                if servername == "all":
                    for server in settings["clusters"][cluster]["servers"]:
                        settings["clusters"][cluster]["servers"][server]["cluster"] = cluster
                        serverlist.append(settings["clusters"][cluster]["servers"][server])
                if servername != "all":
                    settings["clusters"][cluster]["servers"][servername]["cluster"] = cluster
                    if servername not in settings["clusters"][cluster]["servers"]:
                        return await ctx.send("Server name not found.")
                    serverlist.append(settings["clusters"][cluster]["servers"][servername])

        # sending manual commands off to the task loop
        try:
            tasks = []
            for server in serverlist:
                tasks.append(self.manual_rcon(ctx, server, command))
            await asyncio.gather(*tasks)
        except WindowsError as e:
            if e.winerror == 121:
                await ctx.send(f"The **{server['name']}** **{cluster} server has timed out and is probably down.")
        await ctx.send(f"Executed `{command}` command on `{len(serverlist)}` servers for `{clustername}` clusters.")

    # RCON manual command logic
    async def manual_rcon(self, ctx, serverlist, command):
        map = serverlist['name'].capitalize()
        cluster = serverlist['cluster'].upper()
        res = await rcon.asyncio.rcon(
            command=command,
            host=serverlist['ip'],
            port=serverlist['port'],
            passwd=serverlist['password']
        )
        res = res.rstrip()
        if command.lower() == "listplayers":
            await ctx.send(f"**{map} {cluster}**\n"
                           f"{box(res, lang='python')}")
        else:
            await ctx.send(box(f"{map} {cluster}\n{res}", lang="python"))

    # Cache the config into the task data on cog load
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
                    self.taskdata.append([guild.id, server])
        print("ArkTools config initialized.")

    # Message listener to send chat to designated servers
    @commands.Cog.listener("on_message")
    async def chat_toserver(self, message: discord.Message):
        if message.author.bot:
            return
        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@!{mention.id}>",
                                                          "@"+str(mention.name)).replace(f"<@{mention.id}>",
                                                                                         "@"+str(mention.name))
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
            await self.chat_toserver_rcon(map, message)

    # Send chat to server(converts any unicode discord names)
    async def chat_toserver_rcon(self, server, message):
        for data in server:
            normalizedname = unicodedata.normalize('NFKD', message.author.name).encode('ascii', 'ignore').decode()
            await rcon.asyncio.rcon(
                command=f"serverchat {normalizedname}: {message.content}",
                host=data['ip'],
                port=data['port'],
                passwd=data['password']
            )
    # Returns all channels and servers related to the message
    async def globalchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        clusterchannels = []
        allservers = []
        for cluster in settings["clusters"]:
            if settings["clusters"][cluster]["globalchatchannel"] == channel.id:
                clusterchannels.append(settings["clusters"][cluster]["globalchatchannel"])
                for server in settings["clusters"][cluster]["servers"]:
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

    # Executes all loops
    @tasks.loop(seconds=6)
    async def chat_executor(self):
        for data in self.taskdata:
            guild = data[0]
            server = data[1]
            await self.process_handler(guild, server, "getchat")

    @tasks.loop(seconds=30)
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

            if channel not in self.playerlist:
                self.playerlist[channel] = newplayerlist

            playerjoin = self.checkplayerjoin(channel, newplayerlist)
            if playerjoin:
                await joinlog.send(f":green_circle: `{playerjoin[0]}, {playerjoin[1]}` joined {mapname} {clustername}")

            playerleft = self.checkplayerleave(channel, newplayerlist)
            if playerleft:
                await leavelog.send(f":red_circle: `{playerleft[0]}, {playerleft[1]}` left {mapname} {clustername}")

            self.playerlist[channel] = newplayerlist

    def checkplayerjoin(self, channel, playerlist):
        for player in playerlist:
            if player not in self.playerlist[channel]:
                return player

    def checkplayerleave(self, channel, playerlist):
        for player in self.playerlist[channel]:
            if player not in playerlist:
                return player

    # Maintains an embed of all active servers and player counts
    @tasks.loop(seconds=60)
    async def status_channel(self):
        data = await self.config.all_guilds()
        for guildID in data:
            guild = self.bot.get_guild(int(guildID))
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
                    channel = guild.get_channel(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    channelid = settings["clusters"][cluster]["servers"][server]["chatchannel"]
                    if not channel:
                        continue
                    if not channelid:
                        continue

                    # Get cached player count
                    playercount = self.playerlist[channelid]

                    if playercount == []:
                        status += f"{channel.mention}: 0 Players\n"
                        continue
                    if playercount == None:
                        status += f"{channell.mention}: Offline...\n"
                        continue

                    playercount = len(playercount)
                    clustertotal += playercount
                    totalplayers += playercount
                    if playercount == 1:
                        status += f"{channel.mention}: {playercount} player\n"
                    else:
                        status += f"{channel.mention}: {playercount} players\n"

                if clustertotal == 1:
                    status += f"`{clustertotal}` player in the cluster\n"
                else:
                    status += f"`{clustertotal}` players in the cluster\n"

            messagedata = await self.config.guild(guild).statusmessage()
            channeldata = await self.config.guild(guild).statuschannel()
            if not channeldata:
                continue
            if not messagedata:
                continue

            # Embed setup
            thumbnail = guild.icon_url
            eastern = pytz.timezone('US/Eastern')
            time = datetime.datetime.now(eastern)
            embed = discord.Embed(
                timestamp=time,
                title="Server Status",
                description=status
            )
            embed.add_field(name="Total Players", value=f"`{totalplayers}`")
            embed.set_thumbnail(url=thumbnail)
            destinationchannel = guild.get_channel(channeldata)
            msgtoedit = None

            if messagedata:
                try:
                    msgtoedit = await destinationchannel.fetch_message(messagedata)
                except discord.NotFound:
                    print(f"ArkTools Status message not found. Creating new message.")

            if not msgtoedit:
                await self.config.guild(guild).statusmessage.set(None)
                message = await destinationchannel.send(embed=embed)
                await self.config.guild(guild).statusmessage.set(message.id)
            if msgtoedit:
                await msgtoedit.edit(embed=embed)


    # Runs synchronous rcon commands in another thread to not block heartbeat
    async def process_handler(self, guild, server, command):
        def rcon():
            with Client(server['ip'], server['port'], passwd=server['password']) as client:
                result = client.run(command)
                return result

        res = await self.bot.loop.run_in_executor(None, rcon)
        if res:
            if command == "getchat":
                await self.message_handler(guild, server, res)
            if command == "listplayers":
                regex = r"(?:[0-9]+\. )(.+), ([0-9]+)"
                playerlist = re.findall(regex, res)
                return playerlist


    # Sends messages to their designated channels from the in-game chat
    async def message_handler(self, guild, server, res):
        if "Server received, But no response!!" in res:
            return
        guild = self.bot.get_guild(int(guild))
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        msgs = res.split("\n")
        messages = []
        settings = await self.config.guild(guild).all()
        badnames = settings["badnames"]
        for msg in msgs:
            if msg.startswith("AdminCmd:"):
                adminmsg = msg
                await adminlog.send(f"**{server['name'].capitalize()}**\n{box(adminmsg, lang='python')}")
            if "): " not in msg:
                continue
            if "tribe" and ", ID" in msg.lower():
                continue
            else:
                if not msg.startswith('SERVER:'):
                    messages.append(msg)
            for names in badnames:
                if f"({names.lower()}): " in msg.lower():
                    reg = r"(.+)\s\("
                    regname = re.findall(reg, msg)
                    for name in regname:
                        await self.process_handler(guild, server, f'renameplayer "{names.lower()}" {name}')
                        await chatchannel.send(f"A player named `{names}` has been renamed to `{name}`.")
        for msg in messages:
            await chatchannel.send(msg)
            await globalchat.send(f"{chatchannel.mention}: {msg}")


    @chat_executor.before_loop
    async def before_chat_executor(self):
        await self.bot.wait_until_red_ready()
        await self.initialize()
        print("Chat executor is ready.")

    @playerlist_executor.before_loop
    async def before_playerlist_executor(self):
        await self.bot.wait_until_red_ready()
        print("Playerlist executor is ready.")

    @status_channel.before_loop
    async def before_status_channel(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(15)
        print("Status channel monitor is ready.")

    # @commands.command(name="test")
    # async def mytestcom(self, ctx):
    #     await ctx.send(self.playerlist)




