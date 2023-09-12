import asyncio
import datetime
import inspect
import json
import logging
import math
import os
import platform
import random
import string
import subprocess
import sys
import typing as t
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from sys import executable
from time import perf_counter
from zipfile import ZIP_DEFLATED, ZipFile

import cpuinfo
import discord
import psutil
import speedtest
from redbot.cogs.downloader.converters import InstalledCog
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import (
    box,
    humanize_number,
    humanize_timedelta,
    pagify,
    text_to_file,
)

from .diskspeed import get_disk_speed
from .dpymenu import DEFAULT_CONTROLS, confirm, menu

log = logging.getLogger("red.vrt.vrtutils")
DPY = discord.__version__


async def wait_reply(ctx: commands.Context, timeout: int = 60):
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        try:
            await reply.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.DiscordServerError,
        ):
            pass
        return res
    except asyncio.TimeoutError:
        return None


def get_attachments(message: discord.Message) -> t.List[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [a for a in message.reference.resolved.attachments]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments


class VrtUtils(commands.Cog):
    """
    A collection of utility commands for getting info about various things.
    """

    __author__ = "Vertyco"
    __version__ = "1.12.0"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.path = cog_data_path(self)

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
        fill = "▰"
        space = "▱"
        if perc is not None:
            ratio = perc / 100
        else:
            ratio = progress / total
        bar = fill * round(ratio * width) + space * round(width - (ratio * width))
        return f"{bar} {round(100 * ratio, 1)}%"

    async def do_shell_command(self, command: str):
        cmd = f"{executable} -m {command}"

        def exe():
            results = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
            )
            return results.stdout.decode("utf-8") or results.stderr.decode("utf-8")

        res = await asyncio.to_thread(exe)
        return res

    async def run_disk_speed(
        self,
        block_count: int = 128,
        block_size: int = 1048576,
        passes: int = 1,
    ) -> dict:
        reads = []
        writes = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = [
                self.bot.loop.run_in_executor(
                    pool,
                    lambda: get_disk_speed(self.path, block_count, block_size),
                )
                for _ in range(passes)
            ]
            results = await asyncio.gather(*futures)
            for i in results:
                reads.append(i["read"])
                writes.append(i["write"])
        results = {
            "read": sum(reads) / len(reads),
            "write": sum(writes) / len(writes),
        }
        return results

    # -/-/-/-/-/-/-/-/COMMANDS-/-/-/-/-/-/-/-/
    @commands.command(name="pull")
    @commands.is_owner()
    async def update_cog(self, ctx, *cogs: InstalledCog):
        """Auto update & reload cogs"""
        cog_update_command = ctx.bot.get_command("cog update")
        if cog_update_command is None:
            return await ctx.send(
                f"Make sure you first `{ctx.clean_prefix}load downloader` before you can use this command."
            )
        await ctx.invoke(cog_update_command, True, *cogs)

    @commands.command(aliases=["diskbench"])
    @commands.is_owner()
    async def diskspeed(self, ctx: commands.Context):
        """
        Get disk R/W performance for the server your bot is on

        The results of this test may vary, Python isn't fast enough for this kind of byte-by-byte writing,
        and the file buffering and similar adds too much overhead.
        Still this can give a good idea of where the bot is at I/O wise.
        """

        def diskembed(data: dict) -> discord.Embed:
            if data["write5"] != "Waiting..." and data["write5"] != "Running...":
                embed = discord.Embed(title="Disk I/O", color=discord.Color.green())
                embed.description = "Disk Speed Check COMPLETE"
            else:
                embed = discord.Embed(title="Disk I/O", color=ctx.author.color)
                embed.description = "Running Disk Speed Check"
            first = f"Write: {data['write1']}\n" f"Read:  {data['read1']}"
            embed.add_field(
                name="128 blocks of 1048576 bytes (128MB)",
                value=box(first, lang="python"),
                inline=False,
            )
            second = f"Write: {data['write2']}\n" f"Read:  {data['read2']}"
            embed.add_field(
                name="128 blocks of 2097152 bytes (256MB)",
                value=box(second, lang="python"),
                inline=False,
            )
            third = f"Write: {data['write3']}\n" f"Read:  {data['read3']}"
            embed.add_field(
                name="256 blocks of 1048576 bytes (256MB)",
                value=box(third, lang="python"),
                inline=False,
            )
            fourth = f"Write: {data['write4']}\n" f"Read:  {data['read4']}"
            embed.add_field(
                name="256 blocks of 2097152 bytes (512MB)",
                value=box(fourth, lang="python"),
                inline=False,
            )
            fifth = f"Write: {data['write5']}\n" f"Read:  {data['read5']}"
            embed.add_field(
                name="256 blocks of 4194304 bytes (1GB)",
                value=box(fifth, lang="python"),
                inline=False,
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
                embed = discord.Embed(title="Pip Command Results", description=box(p))
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
                embed = discord.Embed(title="Shell Command Results", description=box(p))
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
            return await ctx.send("Could not find that guild")
        await ctx.send(f"That ID belongs to the guild `{guild.name}`")

    # Inspired by kennnyshiwa's imperialtoolkit botstat command
    # https://github.com/kennnyshiwa/kennnyshiwa-cogs
    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def botinfo(self, ctx: commands.Context):
        """
        Get info about the bot
        """
        async with ctx.typing():
            latency = self.bot.latency * 1000

            latency_ratio = max(0.0, min(1.0, latency / 100))

            # Calculate RGB values based on latency ratio
            green = 255 - round(255 * latency_ratio) if latency_ratio > 0.5 else 255
            red = 255 if latency_ratio > 0.5 else round(255 * latency_ratio)

            color = discord.Color.from_rgb(red, green, 0)

            embed = await asyncio.to_thread(self.get_bot_info_embed, color)

            latency_txt = f"Websocket: {humanize_number(round(latency, 2))} ms"
            embed.add_field(
                name="\N{HIGH VOLTAGE SIGN} Latency",
                value=box(latency_txt, lang="python"),
                inline=False,
            )

            start = perf_counter()
            message = await ctx.send(embed=embed)
            end = perf_counter()

            field = embed.fields[-1]
            latency_txt += f"\nMessage:   {humanize_number(round((end - start) * 1000, 2))} ms"
            embed.set_field_at(
                index=5,
                name=field.name,
                value=box(latency_txt, lang="python"),
                inline=False,
            )
            await message.edit(embed=embed)

    def get_bot_info_embed(self, color: discord.Color) -> discord.Embed:
        process = psutil.Process(os.getpid())
        bot_cpu_used = process.cpu_percent(interval=3)

        # -/-/-/CPU-/-/-/
        cpu_count = psutil.cpu_count()  # Int
        cpu_perc: t.List[float] = psutil.cpu_percent(interval=3, percpu=True)
        cpu_avg = round(sum(cpu_perc) / len(cpu_perc), 1)
        cpu_freq: list = psutil.cpu_freq(percpu=True)  # t.List of Objects
        if not cpu_freq:
            freq = psutil.cpu_freq(percpu=False)
            if freq:
                cpu_freq = [freq]
        cpu_info: dict = cpuinfo.get_cpu_info()  # Dict
        cpu_type = cpu_info.get("brand_raw", "Unknown")

        # -/-/-/MEM-/-/-/
        ram = psutil.virtual_memory()  # Obj
        ram_total = self.get_size(ram.total)
        ram_used = self.get_size(ram.used)
        disk = psutil.disk_usage(os.getcwd())
        disk_total = self.get_size(disk.total)
        disk_used = self.get_size(disk.used)
        bot_ram_used = self.get_size(process.memory_info().rss)

        io_counters = process.io_counters()
        disk_usage_process = io_counters[2] + io_counters[3]  # read_bytes + write_bytes
        # Disk load
        disk_io_counter = psutil.disk_io_counters()
        if disk_io_counter:
            disk_io_total = disk_io_counter[2] + disk_io_counter[3]  # read_bytes + write_bytes
            disk_usage = (disk_usage_process / disk_io_total) * 100
        else:
            disk_usage = 0

        # -/-/-/NET-/-/-/
        net = psutil.net_io_counters()  # Obj
        sent = self.get_size(net.bytes_sent)
        recv = self.get_size(net.bytes_recv)

        # -/-/-/OS-/-/-/
        ostype = "Unknown"
        if os.name == "nt":
            osdat = platform.uname()
            ostype = f"{osdat.system} {osdat.release} (version {osdat.version})"
        elif sys.platform == "darwin":
            osdat = platform.mac_ver()
            ostype = f"Mac OS {osdat[0]} {osdat[1]}"
        elif sys.platform == "linux":
            import distro

            ostype = f"{distro.name()} {distro.version()}"

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
            title=f"Stats for {self.bot.user.display_name}",
            description="Below are various stats about the bot and the system it runs on.",
            color=color,
        )
        embed.set_footer(
            text=f"System: {ostype}\nUptime: {sys_uptime}", icon_url=self.bot.user.display_avatar
        )

        botstats = (
            f"Servers:  {servers} ({shards} {'shard' if shards == 1 else 'shards'})\n"
            f"Users:    {users}\n"
            f"Channels: {channels}\n"
            f"Emojis:   {emojis}\n"
            f"Cogs:     {cogs}\n"
            f"Commands: {commandcount}\n"
            f"Uptime:   {uptime}\n"
            f"Red:      {red_version}\n"
            f"DPy:      {DPY}\n"
            f"Python:   {py_version}"
        )
        embed.add_field(
            name="\N{ROBOT FACE} BOT",
            value=box(botstats, lang="python"),
            inline=False,
        )

        cpustats = f"CPU: {cpu_type}\n"
        cpustats += f"Bot: {bot_cpu_used}%\nOverall: {cpu_avg}%\nCores: {cpu_count}"
        if cpu_freq:
            clock, clockmax = round(cpu_freq[0].current), round(cpu_freq[0].max)
            if clockmax:
                cpustats += f" @ {clock}/{clockmax} MHz\n"
            else:
                cpustats += f" @ {clock} MHz\n"
        else:
            cpustats += "\n"

        preformat = []
        for i, perc in enumerate(cpu_perc):
            space = "" if i >= 10 or len(cpu_perc) < 10 else " "
            bar = self.get_bar(0, 0, perc, width=14)
            speed_text = None
            if cpu_freq:
                index = i if len(cpu_freq) > i else 0
                speed = round(cpu_freq[index].current)
                speed_text = f"{speed} MHz"
            preformat.append((f"c{i}:{space} {bar}", speed_text))

        max_width = max([len(i[0]) for i in preformat])
        for usage, speed in preformat:
            space = (max_width - len(usage)) * " " if len(usage) < max_width else ""
            if speed is not None:
                cpustats += f"{usage}{space} @ {speed}\n"
            else:
                cpustats += f"{usage}{space}\n"

        for p in pagify(cpustats, page_length=1024):
            embed.add_field(
                name="\N{DESKTOP COMPUTER} CPU",
                value=box(p, lang="python"),
                inline=False,
            )

        rambar = self.get_bar(0, 0, ram.percent, width=18)
        diskbar = self.get_bar(0, 0, disk.percent, width=18)
        memtext = (
            f"RAM {ram_used}/{ram_total} (Bot: {bot_ram_used})\n"
            f"{rambar}\n"
            f"DISK {disk_used}/{disk_total}\n"
            f"{diskbar}\n"
        )
        embed.add_field(
            name="\N{FLOPPY DISK} MEM",
            value=box(memtext, lang="python"),
            inline=False,
        )

        disk_usage_bar = self.get_bar(0, 0, disk_usage, width=18)
        i_o = f"DISK LOAD\n" f"{disk_usage_bar}"
        embed.add_field(
            name="\N{GEAR}\N{VARIATION SELECTOR-16} I/O",
            value=box(i_o, lang="python"),
            inline=False,
        )

        netstat = f"Sent:     {sent}\n" f"Received: {recv}"
        embed.add_field(
            name="\N{SATELLITE ANTENNA} Network",
            value=box(netstat, lang="python"),
            inline=False,
        )

        return embed

    @commands.command()
    async def getuser(self, ctx, *, user_id: t.Union[int, discord.User]):
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
        since_created = (
            f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
        )
        user_created = (
            f"<t:{int(member.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
        )
        created_on = f"Joined Discord on {user_created}\n({since_created})"
        embed = discord.Embed(
            title=f"{member.name} - {member.id}",
            description=created_on,
            color=await ctx.embed_color(),
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def botip(self, ctx: commands.Context):
        """Get the bots public IP address (in DMs)"""
        async with ctx.typing():
            test = speedtest.Speedtest(secure=True)
            embed = discord.Embed(
                title=f"{self.bot.user.name}'s public IP",
                description=test.results.dict()["client"]["ip"],
            )
            try:
                await ctx.author.send(embed=embed)
                await ctx.tick()
            except discord.Forbidden:
                await ctx.send("Your DMs appear to be disabled, please enable them and try again.")

    @commands.command()
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def usersjson(self, ctx: commands.Context):
        """Get a json file containing all usernames/ID's in this guild"""
        members = {str(member.id): member.name for member in ctx.guild.members}
        file = text_to_file(json.dumps(members))
        await ctx.send("Here are all usernames and their ID's for this guild", file=file)

    @commands.command()
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        """View guilds your bot is in"""
        # Just wanted a stripped down version of getguild from Trusty's serverstats cog
        # https://github.com/TrustyJAID/Trusty-cogs
        elevated_perms = [
            "administrator",
            "ban_members",
            "kick_members",
            "manage_channels",
            "manage_guild",
            "manage_emojis",
            "manage_messages",
            "manage_roles",
            "manage_webhooks",
            "manage_nicknames",
            "mute_members",
            "moderate_members",
            "move_members",
            "deafen_members",
        ]
        embeds = []
        guilds = len(self.bot.guilds)
        page = 0
        for i, guild in enumerate(self.bot.guilds):
            guild: discord.Guild = guild
            if guild.id == ctx.guild.id:
                page = i
            guild_splash = guild.splash.url if guild.splash else None
            guild_icon = guild.icon.url if guild.icon else None
            created = (
                f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            )
            time_elapsed = (
                f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
            )
            try:
                joined_at = guild.me.joined_at
            except AttributeError:
                joined_at = discord.utils.utcnow()
            bot_joined = (
                f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            )
            since_joined = (
                f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
            )

            humans = sum(1 for x in guild.members if not x.bot)
            bots = sum(1 for x in guild.members if x.bot)
            idle = sum(1 for x in guild.members if x.status is discord.Status.idle)
            online = sum(1 for x in guild.members if x.status is discord.Status.online)
            dnd = sum(1 for x in guild.members if x.status is discord.Status.do_not_disturb)
            offline = sum(1 for x in guild.members if x.status is discord.Status.offline)
            streaming = sum(
                1
                for x in guild.members
                if x.activity is not None and x.activity.type is discord.ActivityType.streaming
            )

            desc = (
                f"{guild.description}\n\n"
                f"`GuildCreated: `{created} ({time_elapsed})\n"
                f"`BotJoined:    `{bot_joined} ({since_joined})\n"
                f"`Humans:    `{humans}\n"
                f"`Bots:      `{bots}\n"
                f"`Online:    `{online}\n"
                f"`Idle:      `{idle}\n"
                f"`DND:       `{dnd}\n"
                f"`Offline:   `{offline}\n"
                f"`Streaming: `{streaming}\n"
            )

            em = discord.Embed(
                title=f"{guild.name} -- {guild.id}",
                description=desc,
                color=ctx.author.color,
            )

            if guild_icon:
                em.set_thumbnail(url=guild_icon)

            owner = (
                guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
            )
            verlevel = guild.verification_level
            nitro = guild.premium_tier
            boosters = guild.premium_subscription_count
            filelimit = self.get_size(guild.filesize_limit)
            elimit = guild.emoji_limit
            bits = self.get_bitsize(guild.bitrate_limit)
            field = (
                f"`Owner:        `{owner}\n"
                f"`OwnerID:      `{owner.id}\n"
                f"`Verification: `{verlevel}\n"
                f"`Nitro Tier:   `{nitro}\n"
                f"`Boosters:     `{boosters}\n"
                f"`File Limit:   `{filelimit}\n"
                f"`Emoji Limit:  `{elimit}\n"
                f"`Bitrate:      `{bits}"
            )
            em.add_field(name="Details", value=field)

            text_channels = len(guild.text_channels)
            nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
            voice_channels = len(guild.voice_channels)
            field = (
                f"`Text:  `{text_channels}\n"
                f"`Voice: `{voice_channels}\n"
                f"`NSFW:  `{nsfw_channels}"
            )
            em.add_field(name="Channels", value=field)

            elevated_roles = [
                r
                for r in guild.roles
                if any([p[0] in elevated_perms for p in r.permissions if p[1]])
            ]
            normal_roles = [
                r
                for r in guild.roles
                if not any([p[0] in elevated_perms for p in r.permissions if p[1]])
            ]
            field = (
                f"`Elevated: `{len(elevated_roles)}\n"
                f"`Normal:   `{len(normal_roles)}\n"
                f"`Total:    `{len(elevated_roles) + len(normal_roles)}"
            )
            em.add_field(name="Roles", value=field)

            if guild_splash:
                em.set_image(url=guild_splash)

            em.set_footer(text=f"Page {i + 1}/{guilds}")
            embeds.append(em)

        controls = DEFAULT_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.leave_guild
        controls["\N{CHAINS}\N{VARIATION SELECTOR-16}"] = self.get_invite
        await menu(ctx, embeds, controls, page=page)

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
        await menu(
            ctx,
            instance.pages,
            instance.controls,
            instance.message,
            instance.page,
            instance.timeout,
        )

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
        await menu(
            ctx,
            instance.pages,
            instance.controls,
            instance.message,
            instance.page,
            instance.timeout,
        )

    @commands.command()
    @commands.guild_only()
    async def oldestchannels(self, ctx, amount: int = 10):
        """See which channel is the oldest"""
        async with ctx.typing():
            channels = [
                c for c in ctx.guild.channels if not isinstance(c, discord.CategoryChannel)
            ]
            c_sort = sorted(channels, key=lambda x: x.created_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {c.mention} "
                    f"created <t:{int(c.created_at.timestamp())}:f> (<t:{int(c.created_at.timestamp())}:R>)"
                    for i, c in enumerate(c_sort[:amount])
                ]
            )
            for p in pagify(txt, page_length=4000):
                em = discord.Embed(description=p, color=ctx.author.color)
                await ctx.send(embed=em)

    @commands.command(aliases=["oldestusers"])
    @commands.guild_only()
    async def oldestmembers(
        self,
        ctx,
        amount: t.Optional[int] = 10,
        include_bots: t.Optional[bool] = False,
    ):
        """
        See which users have been in the server the longest

        **Arguments**
        `amount:` how many members to display
        `include_bots:` (True/False) whether to include bots
        """
        async with ctx.typing():
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.joined_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {m} "
                    f"joined <t:{int(m.joined_at.timestamp())}:f> (<t:{int(m.joined_at.timestamp())}:R>)"
                    for i, m in enumerate(m_sort[:amount])
                ]
            )
            for p in pagify(txt, page_length=4000):
                em = discord.Embed(description=p, color=ctx.author.color)
                await ctx.send(embed=em)

    @commands.command()
    @commands.guild_only()
    async def oldestaccounts(
        self,
        ctx,
        amount: t.Optional[int] = 10,
        include_bots: t.Optional[bool] = False,
    ):
        """
        See which users have the oldest Discord accounts

        **Arguments**
        `amount:` how many members to display
        `include_bots:` (True/False) whether to include bots
        """
        async with ctx.typing():
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.created_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {m} "
                    f"created <t:{int(m.created_at.timestamp())}:f> (<t:{int(m.created_at.timestamp())}:R>)"
                    for i, m in enumerate(m_sort[:amount])
                ]
            )
            for p in pagify(txt, page_length=4000):
                em = discord.Embed(description=p, color=ctx.author.color)
                await ctx.send(embed=em)

    @commands.command()
    @commands.guild_only()
    async def rolemembers(self, ctx, role: discord.Role):
        """View all members that have a specific role"""
        members = []
        async for member in AsyncIter(ctx.guild.members, steps=500, delay=0.001):
            if role.id in [r.id for r in member.roles]:
                members.append(member)

        if not members:
            return await ctx.send(f"There are no members with the {role.mention} role")

        members = sorted(members, key=lambda x: x.name)
        start = 0
        stop = 10
        pages = math.ceil(len(members) / 10)
        embeds = []
        for p in range(pages):
            if stop > len(members):
                stop = len(members)

            page = ""
            for i in range(start, stop, 1):
                member = members[i]
                page += f"{member.name} - `{member.id}`\n"
            em = discord.Embed(
                title=f"Members with role {role.name}",
                description=page,
                color=ctx.author.color,
            )
            em.set_footer(text=f"Page {p + 1}/{pages}")
            embeds.append(em)
            start += 10
            stop += 10

        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    async def wipevcs(self, ctx: commands.Context):
        """
        Clear all voice channels from a server
        """
        msg = await ctx.send(
            "Are you sure you want to clear **ALL** Voice Channels from this server?"
        )
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

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    async def wipethreads(self, ctx: commands.Context):
        """
        Clear all threads from a server
        """
        msg = await ctx.send("Are you sure you want to clear **ALL** threads from this server?")
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            return await msg.edit(content="Not deleting all threads")
        perm = ctx.guild.me.guild_permissions.manage_threads
        if not perm:
            return await msg.edit(content="I dont have perms to manage threads")
        deleted = 0
        for thread in ctx.guild.threads:
            await thread.delete()
            deleted += 1
        if deleted:
            await msg.edit(content=f"Deleted {deleted} threads!")
        else:
            await msg.edit(content="No threads to delete!")

    @commands.command(name="text2binary")
    async def text2binary(self, ctx: commands.Context, *, text: str):
        """Convert text to binary"""
        # binary_string = ''.join(format(ord(c), 'b') for c in text)
        try:
            binary_string = "".join(format(ord(i), "08b") for i in text)
            for p in pagify(binary_string):
                await ctx.send(p)
        except ValueError:
            await ctx.send("I could not convert that text to binary :(")

    @commands.command(name="binary2text")
    async def binary2text(self, ctx: commands.Context, *, binary_string: str):
        """Convert a binary string to text"""
        try:
            text = "".join(
                chr(int(binary_string[i * 8 : i * 8 + 8], 2))
                for i in range(len(binary_string) // 8)
            )
            await ctx.send(text)
        except ValueError:
            await ctx.send("I could not convert that binary string to text :(")

    @commands.command(name="randomnum", aliases=["rnum"])
    async def random_number(self, ctx: commands.Context, minimum: int = 1, maximum: int = 100):
        """Generate a random number between the numbers specified"""
        if minimum >= maximum:
            return await ctx.send("Minimum needs to be lower than maximum!")
        num = random.randint(minimum, maximum)
        await ctx.send(f"Result: `{num}`")

    @commands.command(name="emojidata")
    @commands.bot_has_permissions(embed_links=True)
    async def emoji_info(
        self, ctx: commands.Context, emoji: t.Union[discord.Emoji, discord.PartialEmoji, str]
    ):
        """Get info about an emoji"""

        def _url():
            emoji_unicode = []
            for char in emoji:
                char = hex(ord(char))[2:]
                emoji_unicode.append(char)
            if "200d" not in emoji_unicode:
                emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
            emoji_unicode = "-".join(emoji_unicode)
            return f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_unicode}.png"

        unescapable = string.ascii_letters + string.digits
        embed = discord.Embed(color=ctx.author.color)
        if isinstance(emoji, str):
            if emoji.startswith("http"):
                return await ctx.send("This is not an emoji!")

            fail = "Unable to get emoji name"
            txt = "\n".join(map(lambda x: unicodedata.name(x, fail), emoji)) + "\n\n"
            unicode = ", ".join(f"\\{i}" if i not in unescapable else i for i in emoji)
            category = ", ".join(unicodedata.category(c) for c in emoji)
            txt += f"`Unicode:   `{unicode}\n"
            txt += f"`Category:  `{category}\n"
            embed.set_image(url=_url())
        else:
            txt = emoji.name + "\n\n"
            txt += f"`ID:        `{emoji.id}\n"
            txt += f"`Animated:  `{emoji.animated}\n"
            txt += f"`Created:   `<t:{int(emoji.created_at.timestamp())}:F>\n"
            embed.set_image(url=emoji.url)

        if isinstance(emoji, discord.PartialEmoji):
            txt += f"`Custom:    `{emoji.is_custom_emoji()}\n"
        elif isinstance(emoji, discord.Emoji):
            txt += f"`Managed:   `{emoji.managed}\n"
            txt += f"`Server:    `{emoji.guild}\n"
            txt += f"`Available: `{emoji.available}\n"
            txt += f"`BotCanUse: `{emoji.is_usable()}\n"
            if emoji.roles:
                mentions = ", ".join([i.mention for i in emoji.roles])
                embed.add_field(name="Roles", value=mentions)

        embed.description = txt
        await ctx.send(embed=embed)

    @commands.command(name="getsource")
    @commands.is_owner()
    async def get_sourcecode(self, ctx: commands.Context, *, command: str):
        """
        Get the source code of a command
        """
        command = self.bot.get_command(command)
        if command is None:
            return await ctx.send("Command not found!")
        try:
            source_code = inspect.getsource(command.callback)
            if comments := inspect.getcomments(command.callback):
                source_code = comments + "\n" + source_code
        except OSError:
            return await ctx.send("Failed to pull source code")
        pagified = [p for p in pagify(source_code, escape_mass_mentions=True, page_length=1900)]
        pages = []
        for index, p in enumerate(pagified):
            pages.append(box(p, lang="python") + f"\nPage {index + 1}/{len(pagified)}")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="zip")
    @commands.is_owner()
    async def zip_file(self, ctx: commands.Context, *, archive_name: str = "archive.zip"):
        """
        zip a file or files
        """
        if not archive_name.endswith(".zip"):
            archive_name += ".zip"
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                "Please attach your files to the command or reply to a message with attachments"
            )

        def zip_files(prepped: list) -> discord.File:
            zip_buffer = BytesIO()
            zip_buffer.name = archive_name
            with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
                for name, bytefile in prepped:
                    arc.writestr(
                        zinfo_or_arcname=name,
                        data=bytefile,
                        compress_type=ZIP_DEFLATED,
                        compresslevel=9,
                    )
            zip_buffer.seek(0)
            return discord.File(zip_buffer)

        async with ctx.typing():
            prepped = [(i.filename, await i.read()) for i in attachments]
            file = await asyncio.to_thread(zip_files, prepped)
            if file.__sizeof__() > ctx.guild.filesize_limit:
                return await ctx.send("ZIP file too large to send!")
            try:
                await ctx.send("Here is your zip file!", file=file)
            except discord.HTTPException:
                await ctx.send("File is too large!")

    @commands.command(name="unzip")
    @commands.is_owner()
    async def unzip_file(self, ctx: commands.Context):
        """
        Unzips a zip file and sends the extracted files in the channel
        """
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                "Please attach a zip file to the command or reply to a message with a zip file"
            )

        def unzip_files(prepped: list) -> t.List[discord.File]:
            files = []
            for bytefile in prepped:
                with ZipFile(BytesIO(bytefile), "r") as arc:
                    for file_info in arc.infolist():
                        if file_info.is_dir():
                            continue
                        with arc.open(file_info) as extracted:
                            files.append(
                                discord.File(
                                    BytesIO(extracted.read()),
                                    filename=extracted.name,
                                )
                            )
            return files

        def group_files(files: list) -> t.List[t.List[discord.File]]:
            grouped_files = []
            total_size = 0
            current_group = []

            for file in files:
                file_size = file.__sizeof__()

                if total_size + file_size > ctx.guild.filesize_limit or len(current_group) == 9:
                    grouped_files.append(current_group)
                    current_group = []
                    total_size = 0

                current_group.append(file)
                total_size += file_size

            if current_group:
                grouped_files.append(current_group)

            return grouped_files

        async with ctx.typing():
            prepped = [await i.read() for i in attachments]
            files = await asyncio.to_thread(unzip_files, prepped)
            to_group = []
            for file in files:
                if file.__sizeof__() > ctx.guild.filesize_limit:
                    await ctx.send(f"File **{file.filename}** is too large to send!")
                    continue
                to_group.append(file)

            grouped = group_files(to_group)
            for file_list in grouped:
                names = ", ".join(f"`{i.filename}`" for i in file_list)
                try:
                    await ctx.send(names[:2000], files=file_list)
                except discord.HTTPException:
                    await ctx.send(f"Failed to dump the following files: {names}")
