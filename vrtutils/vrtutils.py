import asyncio
import datetime
import json
import logging
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from sys import executable
from typing import Union

import cpuinfo
import discord
import psutil
import speedtest
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    humanize_timedelta,
    humanize_number,
    pagify,
)
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .diskspeed import get_disk_speed

_ = Translator("VrtUtils", __file__)
log = logging.getLogger("red.vrt.vrtutils")
dpy = discord.__version__
if dpy > "1.7.4":
    from .dpymenu import menu, DEFAULT_CONTROLS, confirm

    DPY2 = True
else:
    from .dislashmenu import menu, DEFAULT_CONTROLS, confirm

    DPY2 = False


async def wait_reply(ctx: commands.Context, timeout: int = 60):
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        try:
            await reply.delete()
        except (discord.Forbidden, discord.NotFound, discord.DiscordServerError):
            pass
        return res
    except asyncio.TimeoutError:
        return None


@cog_i18n(_)
class VrtUtils(commands.Cog):
    """
    Random utility commands
    """
    __author__ = "Vertyco"
    __version__ = "1.0.5"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        if not DPY2:
            from dislash import InteractionClient
            InteractionClient(bot, sync_commands=False)
        self.path = cog_data_path(self)
        self.threadpool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vrt_utils")

    # -/-/-/-/-/-/-/-/FORMATTING-/-/-/-/-/-/-/-/
    @staticmethod
    def get_size(num: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
            if abs(num) < 1024.0:
                return "{0:.1f}{1}".format(num, unit)
            num /= 1024.0
        return "{0:.1f}{1}".format(num, "YB")

    @staticmethod
    def get_bitsize(num: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
            if abs(num) < 1000.0:
                return "{0:.1f}{1}".format(num, unit)
            num /= 1000.0
        return "{0:.1f}{1}".format(num, "YB")

    @staticmethod
    def get_bar(progress, total, perc=None, width: int = 20) -> str:
        if perc is not None:
            ratio = perc / 100
        else:
            ratio = progress / total
        bar = "█" * round(ratio * width) + "-" * round(width - (ratio * width))
        return f"|{bar}| {round(100 * ratio, 1)}%"

    async def do_shell_command(self, command: str):
        cmd = f"{executable} -m {command}"

        def exe():
            results = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode("utf-8")
            return results

        res = await self.bot.loop.run_in_executor(self.threadpool, exe)
        return res

    async def run_disk_speed(self, block_count: int = 128, block_size: int = 1048576, passes: int = 1) -> dict:
        reads = []
        writes = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = [
                self.bot.loop.run_in_executor(
                    pool,
                    lambda: get_disk_speed(self.path, block_count, block_size)
                ) for _ in range(passes)
            ]
            results = await asyncio.gather(*futures)
            for i in results:
                reads.append(i["read"])
                writes.append(i["write"])
        results = {
            "read": sum(reads) / len(reads),
            "write": sum(writes) / len(writes)
        }
        return results

    # -/-/-/-/-/-/-/-/COMMANDS-/-/-/-/-/-/-/-/
    @commands.command(aliases=["diskbench"])
    @commands.is_owner()
    async def diskspeed(self, ctx):
        """
        Get disk R/W performance for the server your bot is on

        The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,
        and the file buffering and similar adds too much overhead.
        Still this can give a good idea of where the bot is at I/O wise.
        """

        def diskembed(data: dict) -> discord.Embed:
            if data["write5"] != "Waiting..." and data["write5"] != "Running...":
                embed = discord.Embed(title=_("Disk I/O"), color=discord.Color.green())
                embed.description = _("Disk Speed Check COMPLETE")
            else:
                embed = discord.Embed(title=_("Disk I/O"), color=ctx.author.color)
                embed.description = _("Running Disk Speed Check")
            first = f"Write: {data['write1']}\n" \
                    f"Read:  {data['read1']}"
            embed.add_field(
                name="128 blocks of 1048576 bytes (128MB)",
                value=box(_(first), lang="python"),
                inline=False
            )
            second = f"Write: {data['write2']}\n" \
                     f"Read:  {data['read2']}"
            embed.add_field(
                name="128 blocks of 2097152 bytes (256MB)",
                value=box(_(second), lang="python"),
                inline=False
            )
            third = f"Write: {data['write3']}\n" \
                    f"Read:  {data['read3']}"
            embed.add_field(
                name="256 blocks of 1048576 bytes (256MB)",
                value=box(_(third), lang="python"),
                inline=False
            )
            fourth = f"Write: {data['write4']}\n" \
                     f"Read:  {data['read4']}"
            embed.add_field(
                name="256 blocks of 2097152 bytes (512MB)",
                value=box(_(fourth), lang="python"),
                inline=False
            )
            fifth = f"Write: {data['write5']}\n" \
                    f"Read:  {data['read5']}"
            embed.add_field(
                name="256 blocks of 4194304 bytes (1GB)",
                value=box(_(fifth), lang="python"),
                inline=False
            )
            return embed

        results = {
            "write1": "Running...",
            "read1": "Running...",
            "write2": "Waiting...",
            "read2": "Waiting...",
            "write3": "Waiting...",
            "read3": "Waiting...",
            "write4": "Waiting...",
            "read4": "Waiting...",
            "write5": "Waiting...",
            "read5": "Waiting...",

        }
        msg = None
        for i in range(6):
            stage = i + 1
            em = diskembed(results)
            if not msg:
                msg = await ctx.send(embed=em)
            else:
                await msg.edit(embed=em)
            count = 128
            size = 1048576
            if stage == 2:
                count = 128
                size = 2097152
            elif stage == 3:
                count = 256
                size = 1048576
            elif stage == 4:
                count = 256
                size = 2097152
            elif stage == 6:
                count = 256
                size = 4194304
            res = await self.run_disk_speed(block_count=count, block_size=size, passes=3)
            write = f"{humanize_number(round(res['write'], 2))}MB/s"
            read = f"{humanize_number(round(res['read'], 2))}MB/s"
            results[f"write{stage}"] = write
            results[f"read{stage}"] = read
            if f"write{stage + 1}" in results:
                results[f"write{stage + 1}"] = "Running..."
                results[f"read{stage + 1}"] = "Running..."
            await asyncio.sleep(1)

    # @commands.command()
    # async def latency(self, ctx):
    #     """Check the bots latency"""
    #     try:
    #         socket_latency = round(self.bot.latency * 1000)
    #     except OverflowError:
    #         return await ctx.send("Bot is up but missed had connection issues the last few seconds.")

    @commands.command()
    @commands.is_owner()
    async def pip(self, ctx, *, command: str):
        """Run a pip command from within your bots venv"""
        async with ctx.typing():
            command = f"pip {command}"
            res = await self.do_shell_command(command)
            embeds = []
            page = 1
            for p in pagify(res):
                embed = discord.Embed(
                    title="Pip Command Results",
                    description=box(p)
                )
                embed.set_footer(text=f"Page {page}")
                page += 1
                embeds.append(embed)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                if embeds:
                    await ctx.send(embed=embeds[0])
                else:
                    await ctx.send("Command ran with no results")

    @commands.command()
    @commands.is_owner()
    async def runshell(self, ctx, *, command: str):
        """Run a shell command from within your bots venv"""
        async with ctx.typing():
            command = f"{command}"
            res = await self.do_shell_command(command)
            embeds = []
            page = 1
            for p in pagify(res):
                embed = discord.Embed(
                    title="Shell Command Results",
                    description=box(p)
                )
                embed.set_footer(text=f"Page {page}")
                page += 1
                embeds.append(embed)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                if embeds:
                    await ctx.send(embed=embeds[0])
                else:
                    await ctx.send("Command ran with no results")

    @commands.command()
    @commands.is_owner()
    async def findguildbyid(self, ctx, guild_id: int):
        """Find a guild by ID"""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.Forbidden:
                guild = None
        if not guild:
            return await ctx.send(_("Could not find that guild"))
        await ctx.send(_(f"That ID belongs to the guild `{guild.name}`"))

    # Inspired by kennnyshiwa's imperialtoolkit botstat command
    # https://github.com/kennnyshiwa/kennnyshiwa-cogs
    @commands.command()
    async def botinfo(self, ctx):
        """
        Get info about the bot
        """
        async with ctx.typing():
            # -/-/-/CPU-/-/-/
            cpu_count = psutil.cpu_count()  # Int
            cpu_perc = await self.bot.loop.run_in_executor(
                None, lambda: psutil.cpu_percent(interval=3, percpu=True)
            )  # List of floats
            cpu_freq = psutil.cpu_freq(percpu=True)  # List of Objects
            cpu_info = cpuinfo.get_cpu_info()  # Dict
            cpu_type = cpu_info["brand_raw"] if "brand_raw" in cpu_info else "Unknown"

            # -/-/-/MEM-/-/-/
            ram = psutil.virtual_memory()  # Obj
            ram_total = self.get_size(ram.total)
            ram_used = self.get_size(ram.used)
            disk = psutil.disk_usage(os.getcwd())
            disk_total = self.get_size(disk.total)
            disk_used = self.get_size(disk.used)

            p = psutil.Process()
            io_counters = p.io_counters()
            disk_usage_process = io_counters[2] + io_counters[3]  # read_bytes + write_bytes
            disk_io_counter = psutil.disk_io_counters()
            disk_io_total = disk_io_counter[2] + disk_io_counter[3]  # read_bytes + write_bytes
            disk_usage = (disk_usage_process / disk_io_total) * 100

            # -/-/-/NET-/-/-/
            net = psutil.net_io_counters()  # Obj
            sent = self.get_size(net.bytes_sent)
            recv = self.get_size(net.bytes_recv)

            # -/-/-/OS-/-/-/
            if os.name == "nt":
                osdat = platform.uname()
                ostype = f"{osdat.system} {osdat.release} (version {osdat.version})"
            elif sys.platform == "darwin":
                osdat = platform.mac_ver()
                ostype = f"Mac OS {osdat[0]} {osdat[1]}"
            elif sys.platform == "linux":
                import distro
                ostype = f"{distro.name()} {distro.version()}"
            else:
                ostype = "Unknown"

            td = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(psutil.boot_time())
            sys_uptime = humanize_timedelta(timedelta=td)

            # -/-/-/BOT-/-/-/
            servers = "{:,}".format(len(self.bot.guilds))
            shards = self.bot.shard_count
            users = "{:,}".format(len(self.bot.users))
            channels = "{:,}".format(sum(len(guild.channels) for guild in self.bot.guilds))
            emojis = "{:,}".format(len(self.bot.emojis))
            cogs = "{:,}".format(len(self.bot.cogs))
            commandcount = 0
            for cog in self.bot.cogs:
                for __ in self.bot.get_cog(cog).walk_commands():
                    commandcount += 1
            commandcount = "{:,}".format(commandcount)
            td = datetime.datetime.utcnow() - self.bot.uptime
            uptime = humanize_timedelta(timedelta=td)

            # -/-/-/LIBS-/-/-/
            red_version = version_info
            ver = sys.version_info
            py_version = f"{ver.major}.{ver.minor}.{ver.micro}"

            embed = discord.Embed(
                title=_(f"Stats for {self.bot.user.name}"),
                description=_(f"Below are various stats about the bot and the system it runs on."),
                color=await ctx.embed_color()
            )

            botstats = f"Servers:  {servers} ({shards} {'shard' if shards == 1 else 'shards'})\n" \
                       f"Users:    {users}\n" \
                       f"Channels: {channels}\n" \
                       f"Emojis:   {emojis}\n" \
                       f"Cogs:     {cogs}\n" \
                       f"Commands: {commandcount}\n" \
                       f"Uptime:   {uptime}\n" \
                       f"Red:      {red_version}\n" \
                       f"DPy:      {dpy}\n" \
                       f"Python:   {py_version}"
            embed.add_field(
                name="\N{ROBOT FACE} BOT",
                value=box(_(botstats), lang="python"),
                inline=False
            )

            cpustats = f"CPU:    {cpu_type}\n" \
                       f"Cores:  {cpu_count}\n"
            if len(cpu_freq) == 1:
                cpustats += f"{cpu_freq[0].current}/{cpu_freq[0].max} Mhz\n"
            else:
                for i, obj in enumerate(cpu_freq):
                    maxfreq = f"/{round(obj.max, 2)}" if obj.max else ""
                    cpustats += f"Core {i}: {round(obj.current, 2)}{maxfreq} Mhz\n"
            if isinstance(cpu_perc, list):
                for i, perc in enumerate(cpu_perc):
                    space = " "
                    if i >= 10:
                        space = ""
                    bar = self.get_bar(0, 0, perc)
                    cpustats += f"Core {i}:{space} {bar}\n"
            embed.add_field(
                name="\N{DESKTOP COMPUTER} CPU",
                value=box(_(cpustats), lang="python"),
                inline=False
            )

            rambar = self.get_bar(0, 0, ram.percent, width=30)
            diskbar = self.get_bar(0, 0, disk.percent, width=30)
            memtext = f"RAM ({ram_used}/{ram_total})\n" \
                      f"{rambar}\n" \
                      f"DISK ({disk_used}/{disk_total})\n" \
                      f"{diskbar}\n"
            embed.add_field(
                name=f"\N{FLOPPY DISK} MEM",
                value=box(memtext, lang="python"),
                inline=False
            )

            disk_usage_bar = self.get_bar(0, 0, disk_usage, width=30)
            i_o = f"DISK LOAD\n" \
                  f"{disk_usage_bar}"
            embed.add_field(
                name="\N{GEAR}\N{VARIATION SELECTOR-16} I/O",
                value=box(_(i_o), lang="python"),
                inline=False
            )

            netstat = f"Sent:     {sent}\n" \
                      f"Received: {recv}"
            embed.add_field(
                name="\N{SATELLITE ANTENNA} Network",
                value=box(_(netstat), lang="python"),
                inline=False
            )

            if DPY2:
                bot_icon = self.bot.user.avatar.url.format("png")
            else:
                bot_icon = self.bot.user.avatar_url_as(format="png")
            embed.set_thumbnail(url=bot_icon)
            embed.set_footer(text=_(f"System: {ostype}\nUptime: {sys_uptime}"))
            await ctx.send(embed=embed)

    @commands.command()
    async def getuser(self, ctx, *, user_id: Union[int, discord.User]):
        """Find a user by ID"""
        if isinstance(user_id, int):
            try:
                member = await self.bot.get_or_fetch_user(int(user_id))
            except discord.NotFound:
                return await ctx.send(f"I could not find any users with the ID `{user_id}`")
        else:
            try:
                member = await self.bot.get_or_fetch_user(user_id.id)
            except discord.NotFound:
                return await ctx.send(f"I could not find any users with the ID `{user_id.id}`")
        since_created = f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
        user_created = f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
        created_on = _(
            f"Joined Discord on {user_created}\n"
            f"({since_created})"
        )
        embed = discord.Embed(
            title=f"{member.name} - {member.id}",
            description=created_on,
            color=await ctx.embed_color()
        )
        if DPY2:
            if member.avatar:
                embed.set_image(url=member.avatar.url)
        else:
            embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def botip(self, ctx):
        """Get the bots public IP address (in DMs)"""
        async with ctx.typing():
            test = speedtest.Speedtest(secure=True)
            embed = discord.Embed(
                title=f"{self.bot.user.name}'s public IP",
                description=test.results.dict()["client"]["ip"]
            )
            try:
                await ctx.author.send(embed=embed)
                await ctx.tick()
            except discord.Forbidden:
                await ctx.send("Your DMs appear to be disabled, please enable them and try again.")

    @commands.command()
    @commands.is_owner()
    async def usersjson(self, ctx):
        """Get a json file containing all usernames/ID's in this guild"""
        members = {}
        for member in ctx.guild.members:
            members[str(member.id)] = member.name
        iofile = StringIO(json.dumps(members))
        filename = f"users.json"
        file = discord.File(iofile, filename=filename)
        await ctx.send("Here are all usernames and their ID's for this guild", file=file)

    @commands.command()
    @commands.is_owner()
    async def guilds(self, ctx):
        """View guilds your bot is in"""
        # Just wanted a stripped down version of getguild from Trusty's serverstats cog
        # https://github.com/TrustyJAID/Trusty-cogs
        embeds = []
        guilds = len(self.bot.guilds)
        for i, guild in enumerate(self.bot.guilds):
            if DPY2:
                guild_splash = guild.splash.url if guild.splash else None
                guild_icon = guild.icon.url if guild.icon else None
            else:
                guild_splash = guild.splash_url_as(format="png")
                guild_icon = guild.icon_url_as(format="png")
            created = f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            time_elapsed = f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
            try:
                joined_at = guild.me.joined_at
            except AttributeError:
                joined_at = datetime.datetime.utcnow()
            bot_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            since_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"

            humans = sum(1 for x in guild.members if not x.bot)
            bots = sum(1 for x in guild.members if x.bot)
            idle = sum(1 for x in guild.members if x.status is discord.Status.idle)
            online = sum(1 for x in guild.members if x.status is discord.Status.online)
            dnd = sum(1 for x in guild.members if x.status is discord.Status.do_not_disturb)
            offline = sum(1 for x in guild.members if x.status is discord.Status.offline)
            streaming = sum(1 for x in guild.members
                            if x.activity is not None and x.activity.type is discord.ActivityType.streaming)

            desc = f"{guild.description}\n\n" \
                   f"`GuildCreated: `{created} ({time_elapsed})\n" \
                   f"`BotJoined:    `{bot_joined} ({since_joined})\n" \
                   f"`Humans:    `{humans}\n" \
                   f"`Bots:      `{bots}\n" \
                   f"`Online:    `{online}\n" \
                   f"`Idle:      `{idle}\n" \
                   f"`DND:       `{dnd}\n" \
                   f"`Offline:   `{offline}\n" \
                   f"`Streaming: `{streaming}\n"

            em = discord.Embed(
                title=f"{guild.name} -- {guild.id}",
                description=desc,
                color=ctx.author.color
            )

            if guild_icon:
                em.set_thumbnail(url=guild_icon)

            owner = guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
            verlevel = guild.verification_level
            nitro = guild.premium_tier
            boosters = guild.premium_subscription_count
            filelimit = self.get_size(guild.filesize_limit)
            elimit = guild.emoji_limit
            bits = self.get_bitsize(guild.bitrate_limit)
            field = f"`Owner:        `{owner}\n" \
                    f"`OwnerID:      `{owner.id}\n" \
                    f"`Verification: `{verlevel}\n" \
                    f"`Nitro Tier:   `{nitro}\n" \
                    f"`Boosters:     `{boosters}\n" \
                    f"`File Limit:   `{filelimit}\n" \
                    f"`Emoji Limit:  `{elimit}\n" \
                    f"`Bitrate:      `{bits}"
            em.add_field(name="Details", value=field)

            text_channels = len(guild.text_channels)
            nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
            voice_channels = len(guild.voice_channels)
            field = f"`Text:  `{text_channels}\n" \
                    f"`Voice: `{voice_channels}\n" \
                    f"`NSFW:  `{nsfw_channels}"
            em.add_field(name="Channels", value=field)

            if guild_splash:
                em.set_image(url=guild_splash)

            em.set_footer(text=f"Page {i + 1}/{guilds}")
            embeds.append(em)

        controls = DEFAULT_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.leave_guild
        controls["\N{CHAINS}\N{VARIATION SELECTOR-16}"] = self.get_invite
        await menu(ctx, embeds, controls)

    async def leave_guild(self, instance, interaction):
        ctx = instance.ctx
        data = instance.pages[instance.page].title.split("--")
        guildname = data[0].strip()
        guildid = data[1].strip()
        msg = await ctx.send(f"Are you sure you want me to leave **{guildname}**?")
        yes = await confirm(ctx, msg)
        await msg.delete()
        if yes is None:
            return
        if yes:
            guild = self.bot.get_guild(int(guildid))
            await guild.leave()
            await instance.respond(interaction, f"I have left **{guildname}**")
        else:
            await instance.respond(interaction, f"Not leaving **{guildname}**")
        await menu(ctx, instance.pages, instance.controls, instance.message, instance.page, instance.timeout)

    async def get_invite(self, instance, interaction):
        ctx = instance.ctx
        data = instance.pages[instance.page].title.split("--")
        guildid = data[1].strip()
        guild = self.bot.get_guild(int(guildid))
        invite = None
        my_perms: discord.Permissions = guild.me.guild_permissions
        if my_perms.manage_guild or my_perms.administrator:
            if "VANITY_URL" in guild.features:
                # guild has a vanity url so use it as the one to send
                try:
                    return await guild.vanity_invite()
                except discord.errors.Forbidden:
                    pass
            invites = await guild.invites()
        else:
            invites = []
        for inv in invites:  # Loop through the invites for the guild
            if not (inv.max_uses or inv.max_age or inv.temporary):
                invite = inv
                break
        else:  # No existing invite found that is valid
            channel = None
            if not DPY2:
                channels_and_perms = zip(
                    guild.text_channels, map(guild.me.permissions_in, guild.text_channels)
                )
                channel = next(
                    (channel for channel, perms in channels_and_perms if perms.create_instant_invite),
                    None,
                )
            else:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        break
            try:
                if channel is not None:
                    # Create invite that expires after max_age
                    invite = await channel.create_invite(max_age=3600)
            except discord.HTTPException:
                pass
        if invite:
            await instance.respond(interaction, str(invite))
        else:
            await instance.respond(interaction, "I could not get an invite for that server!")
        await menu(ctx, instance.pages, instance.controls, instance.message, instance.page, instance.timeout)

    @commands.command()
    @commands.guildowner()
    async def wipevcs(self, ctx):
        """
        Clear all voice channels from a guild

        This command was made to recover from Nuked servers that were VC spammed.
        Hopefully it will never need to be used again.
        """
        msg = await ctx.send("Are you sure you want to clear **ALL** Voice Channels from this guild?")
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            return await msg.edit(content="Not deleting all VC's")
        perm = ctx.guild.me.guild_permissions.manage_channels
        if not perm:
            return await msg.edit(content="I dont have perms to manage channels")
        deleted = 0
        for chan in ctx.guild.channels:
            if isinstance(chan, discord.TextChannel):
                continue
            try:
                await chan.delete()
                deleted += 1
            except Exception:
                pass
        if deleted:
            await msg.edit(content=f"Deleted {deleted} VCs!")
        else:
            await msg.edit(content="No VCs to delete!")
