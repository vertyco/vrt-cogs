import asyncio
import datetime
import json
import os
import platform
import sys
import typing as t
from time import perf_counter

import cpuinfo
import discord
import psutil
import speedtest
from discord import app_commands
from redbot.cogs.downloader.converters import InstalledCog
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import (
    box,
    humanize_number,
    humanize_timedelta,
    pagify,
    text_to_file,
)

from ..abc import MixinMeta
from ..common.dpymenu import DEFAULT_CONTROLS, confirm, menu
from ..common.utils import do_shell_command, get_bar, get_bitsize, get_size


class BotInfo(MixinMeta):
    @app_commands.command(name="latency", description="Return the bot's latency.")
    async def get_latency(self, interaction: discord.Interaction):
        """
        Return the bot's latency.
        """
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! `{latency}ms`", ephemeral=True)

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

    @commands.command()
    @commands.is_owner()
    async def pip(self, ctx, *, command: str):
        """Run a pip command from within your bots venv"""
        async with ctx.typing():
            command = f"pip {command}"
            res = await do_shell_command(command)
            embeds = []
            pages = [p for p in pagify(res)]
            for idx, p in enumerate(pages):
                embed = discord.Embed(title="Pip Command Results", description=box(p))
                embed.set_footer(text=f"Page {idx + 1}/{len(pages)}")
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
            res = await do_shell_command(command)
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
    @commands.guild_only()
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
            created = f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            time_elapsed = f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
            try:
                joined_at = guild.me.joined_at
            except AttributeError:
                joined_at = discord.utils.utcnow()
            bot_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            since_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"

            humans = sum(1 for x in guild.members if not x.bot)
            bots = sum(1 for x in guild.members if x.bot)
            idle = sum(1 for x in guild.members if x.status is discord.Status.idle)
            online = sum(1 for x in guild.members if x.status is discord.Status.online)
            dnd = sum(1 for x in guild.members if x.status is discord.Status.do_not_disturb)
            offline = sum(1 for x in guild.members if x.status is discord.Status.offline)
            streaming = sum(
                1 for x in guild.members if x.activity is not None and x.activity.type is discord.ActivityType.streaming
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

            owner = guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
            verlevel = guild.verification_level
            nitro = guild.premium_tier
            boosters = guild.premium_subscription_count
            filelimit = get_size(guild.filesize_limit)
            elimit = guild.emoji_limit
            bits = get_bitsize(guild.bitrate_limit)
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
            field = f"`Text:  `{text_channels}\n" f"`Voice: `{voice_channels}\n" f"`NSFW:  `{nsfw_channels}"
            em.add_field(name="Channels", value=field)

            elevated_roles = [r for r in guild.roles if any([p[0] in elevated_perms for p in r.permissions if p[1]])]
            normal_roles = [r for r in guild.roles if not any([p[0] in elevated_perms for p in r.permissions if p[1]])]
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
            if not guild:
                await instance.respond(interaction, "I could not find that guild")
            else:
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
                index=embed.fields.index(field),
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
        ram_total = get_size(ram.total)
        ram_used = get_size(ram.used)
        disk = psutil.disk_usage(os.getcwd())
        disk_total = get_size(disk.total)
        disk_used = get_size(disk.used)
        bot_ram_used = get_size(process.memory_info().rss)

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
        sent = get_size(net.bytes_sent)
        recv = get_size(net.bytes_recv)

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
        embed.set_footer(text=f"System: {ostype}\nUptime: {sys_uptime}", icon_url=self.bot.user.display_avatar)

        botstats = (
            f"Servers:  {servers} ({shards} {'shard' if shards == 1 else 'shards'})\n"
            f"Users:    {users}\n"
            f"Channels: {channels}\n"
            f"Emojis:   {emojis}\n"
            f"Cogs:     {cogs}\n"
            f"Commands: {commandcount}\n"
            f"Uptime:   {uptime}\n"
            f"Red:      {red_version}\n"
            f"DPy:      {discord.__version__}\n"
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
            bar = get_bar(0, 0, perc, width=14)
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

        rambar = get_bar(0, 0, ram.percent, width=18)
        diskbar = get_bar(0, 0, disk.percent, width=18)
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

        disk_usage_bar = get_bar(0, 0, disk_usage, width=18)
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

    @commands.command(name="shared")
    @commands.is_owner()
    async def shared_guilds(self, ctx: commands.Context, server: t.Union[discord.Guild, int]):
        """
        View members in a specified server that are also in this server
        """
        if isinstance(server, int):
            server = self.bot.get_guild(server)
            if not server:
                return await ctx.send("I am not in a server with that ID.")
        local_members = set(i.id for i in ctx.guild.members)
        txt = ""
        for member in server.members:
            if member.id in local_members:
                txt += f"{member.name} (`{member.id}`)\n"
        if not txt:
            return await ctx.send("That server has no members that are also in this one.")

        pages = [p for p in pagify(txt)]
        embeds = []
        for idx, i in enumerate(pages):
            embed = discord.Embed(title="Shared Members", description=i, color=ctx.author.color)
            embed.set_footer(text=f"Page {idx + 1}/{len(pages)}")
            embeds.append(embed)

        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="botshared")
    @commands.is_owner()
    async def shared_guilds_with_bot(self, ctx: commands.Context, *, user: t.Union[discord.Member, discord.User]):
        """View servers that the bot and a user are both in together

        Does not include the server this command is run in
        """
        txt = ""
        for guild in self.bot.guilds:
            if guild.get_member(user.id):
                txt += f"{guild.name} (`{guild.id}`)\n"
        if not txt:
            return await ctx.send("I am not in any servers with that user.")
        pages = [p for p in pagify(txt)]
        embeds = []
        for idx, i in enumerate(pages):
            embed = discord.Embed(title="Shared Servers", description=i, color=ctx.author.color)
            embed.set_footer(text=f"Page {idx + 1}/{len(pages)}")
            embeds.append(embed)

        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="viewapikeys")
    @commands.is_owner()
    async def view_api_keys(self, ctx: commands.Context):
        """
        DM yourself the bot's API keys
        """
        bot: Red = self.bot
        data = await bot.get_shared_api_tokens()
        dump = json.dumps(data, indent=4)
        file = text_to_file(dump, "apikeys.json")
        try:
            await ctx.author.send("Here are the bot's API keys", file=file)
        except discord.Forbidden:
            await ctx.send("I cannot DM you, please enable DMs and try again.")
