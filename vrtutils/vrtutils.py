import subprocess
from pathlib import Path
from io import StringIO, BytesIO
import json
import datetime
import speedtest
import os
import sys
import platform
import cpuinfo
import logging

import discord
import pkg_resources
import psutil
from redbot.cogs.downloader.repo_manager import Repo
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from typing import Dict, List, Literal, Optional, Tuple, Union, cast
from redbot.core.utils.chat_formatting import (
    bold,
    box,
    escape,
    humanize_list,
    humanize_number,
    humanize_timedelta,
    pagify,
)
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

_ = Translator("VrtUtils", __file__)
log = logging.getLogger("red.vrt.vrtutils")
dpy = discord.__version__
if dpy > "1.7.3":
    DPY2 = True
else:
    DPY2 = False


class VrtUtils(commands.Cog):
    """
    Utility commands inspired or recycled from various utility cogs.

    **Cog creators whos' code I either took inspiration or recycled functions from**
    TrustyJAID's Serverstats cog: https://github.com/TrustyJAID/Trusty-cogs
    Kennnyshiwa's imperialtoolkit cog: https://github.com/kennnyshiwa/kennnyshiwa-cogs
    PhasecoreX's netspeed cog: https://github.com/PhasecoreX/PCXCogs

    This cog was created to condense the amount of cogs I had loaded and to only have the commands I wanted.
    """
    __author__ = "Vertyco and friends"
    __version__ = "1.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.LIB_PATH = cog_data_path(self) / "lib"

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
            ratio = float(perc) / 100
        else:
            ratio = progress / total
        bar = "█" * int(ratio * width) + "-" * int(width - (ratio * width))
        return f"|{bar}| {round(100 * ratio)}%"

    @staticmethod
    def speedtest_embed(step: int, results_dict):
        """Generate the embed."""
        measuring = ":mag: Measuring..."
        waiting = ":hourglass: Waiting..."
        color = discord.Color.dark_orange()
        title = "Measuring network speed..."
        message_ping = measuring
        message_down = waiting
        message_up = waiting
        if step > 0:
            message_ping = f"**{results_dict['ping']}** ms"
            message_down = measuring
            color = discord.Color.red()
        if step > 1:
            message_down = f"**{round(results_dict['download'] / 1000000, 2)}** mbps"
            message_up = measuring
            color = discord.Color.orange()
        if step > 2:
            message_up = f"**{round(results_dict['upload'] / 1000000, 2)}** mbps"
            title = "Speedtest Results"
            color = discord.Color.green()
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Ping", value=message_ping)
        embed.add_field(name="Download", value=message_down)
        embed.add_field(name="Upload", value=message_up)
        return embed

    async def get_invite(self, guild: discord.Guild, max_age: int = 3600):
        # Yoinked from Trusty with love
        my_perms: discord.Permissions = guild.me.guild_permissions
        if my_perms.manage_guild or my_perms.administrator:
            if "VANITY_URL" in guild.features:
                # guild has a vanity url so use it as the one to send
                try:
                    return await guild.vanity_invite()
                except discord.errors.Forbidden:
                    invites = []
            invites = await guild.invites()
        else:
            invites = []
        for inv in invites:  # Loop through the invites for the guild
            if not (inv.max_uses or inv.max_age or inv.temporary):
                # Invite is for the guild's default channel,
                # has unlimited uses, doesn't expire, and
                # doesn't grant temporary membership
                # (i.e. they won't be kicked on disconnect)
                return inv
        else:  # No existing invite found that is valid
            if not DPY2:
                channels_and_perms = zip(
                    guild.text_channels, map(guild.me.permissions_in, guild.text_channels)
                )
                channel = next(
                    (channel for channel, perms in channels_and_perms if perms.create_instant_invite),
                    None,
                )
                if channel is None:
                    return
            else:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        break
                else:
                    return
            try:
                # Create invite that expires after max_age
                return await channel.create_invite(max_age=max_age)
            except discord.HTTPException:
                return

    async def guild_embed(self, guild: discord.Guild) -> discord.Embed:
        # Yoinked from Trusty's serverstats cog with love
        # https://github.com/TrustyJAID/Trusty-cogs
        invite = await self.get_invite(guild)
        if DPY2:
            print(guild.name)
            print(guild.splash)
            print(guild.banner)
            if guild.splash:
                guild_splash = guild.splash.url
            else:
                guild_splash = None

            if guild.icon:
                guild_icon = guild.icon.url
            else:
                guild_icon = None
        else:
            guild_splash = guild.splash_url_as(format="png")
            guild_icon = guild.icon_url_as(format="png")
        created_at = _("Created on {date}. That's over {num}!").format(
            date=bold(
                f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
            ),
            num=bold(
                f"<t:{int(guild.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
            ),
        )
        total_users = humanize_number(guild.member_count)
        try:
            joined_at = guild.me.joined_at
        except AttributeError:
            joined_at = datetime.datetime.utcnow()
        bot_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:D>"
        since_joined = f"<t:{int(joined_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>"
        joined_on = _(
            "**{bot_name}** joined this server on **{bot_join}**.\n"
            "That's over **{since_join}**!"
        ).format(bot_name=self.bot.user.name, bot_join=bot_joined, since_join=since_joined)
        shard = (
            _("\nShard ID: **{shard_id}/{shard_count}**").format(
                shard_id=humanize_number(guild.shard_id + 1),
                shard_count=humanize_number(self.bot.shard_count),
            )
            if self.bot.shard_count > 1
            else ""
        )
        colour = guild.roles[-1].colour

        online_stats = {
            _("Humans: "): lambda x: not x.bot,
            _(" • Bots: "): lambda x: x.bot,
            "\N{LARGE GREEN CIRCLE}": lambda x: x.status is discord.Status.online,
            "\N{LARGE ORANGE CIRCLE}": lambda x: x.status is discord.Status.idle,
            "\N{LARGE RED CIRCLE}": lambda x: x.status is discord.Status.do_not_disturb,
            "\N{MEDIUM WHITE CIRCLE}": lambda x: x.status is discord.Status.offline,
            "\N{LARGE PURPLE CIRCLE}": lambda x: (
                x.activity is not None and x.activity.type is discord.ActivityType.streaming
            ),
        }
        member_msg = _("Total Users: {}\n").format(bold(total_users))
        count = 1
        for emoji, value in online_stats.items():
            try:
                num = len([m for m in guild.members if value(m)])
            except Exception as error:
                print(error)
                continue
            else:
                member_msg += f"{emoji} {bold(humanize_number(num))} " + (
                    "\n" if count % 2 == 0 else ""
                )
            count += 1

        text_channels = len(guild.text_channels)
        nsfw_channels = len([c for c in guild.text_channels if c.is_nsfw()])
        voice_channels = len(guild.voice_channels)

        verif = {
            "none": _("0 - None"),
            "low": _("1 - Low"),
            "medium": _("2 - Medium"),
            "high": _("3 - High"),
            "extreme": _("4 - Extreme"),
        }

        features = {
            "ANIMATED_ICON": _("Animated Icon"),
            "BANNER": _("Banner Image"),
            "COMMERCE": _("Commerce"),
            "COMMUNITY": _("Community"),
            "DISCOVERABLE": _("Server Discovery"),
            "FEATURABLE": _("Featurable"),
            "INVITE_SPLASH": _("Splash Invite"),
            "MEMBER_LIST_DISABLED": _("Member list disabled"),
            "MEMBER_VERIFICATION_GATE_ENABLED": _("Membership Screening enabled"),
            "MORE_EMOJI": _("More Emojis"),
            "NEWS": _("News Channels"),
            "PARTNERED": _("Partnered"),
            "PREVIEW_ENABLED": _("Preview enabled"),
            "PUBLIC_DISABLED": _("Public disabled"),
            "VANITY_URL": _("Vanity URL"),
            "VERIFIED": _("Verified"),
            "VIP_REGIONS": _("VIP Voice Servers"),
            "WELCOME_SCREEN_ENABLED": _("Welcome Screen enabled"),
        }
        guild_features_list = [
            f"✅ {name}" for feature, name in features.items() if feature in guild.features
        ]

        desc = f""
        if guild.description:
            desc += f"{_(guild.description)}\n\n"
        if invite:
            desc += f"{_('Invite')}: {invite}\n\n"
        desc += f"{created_at}\n{joined_on}"
        em = discord.Embed(
            description=desc,
            colour=colour,
        )
        if "VERIFIED" in guild.features:
            auth_icon = "https://cdn.discordapp.com/emojis/457879292152381443.png"
        elif "PARTNERED" in guild.features:
            auth_icon = "https://cdn.discordapp.com/emojis/508929941610430464.png"
        else:
            auth_icon = None

        if not guild_icon:
            guild_icon = "https://cdn.discordapp.com/embed/avatars/1.png"
        if auth_icon and guild_icon:
            em.set_author(
                name=guild.name,
                icon_url=auth_icon,
                url=guild_icon
            )
        elif guild_icon and not auth_icon:
            em.set_author(
                name=guild.name,
                url=guild_icon
            )
        else:
            em.set_author(
                name=guild.name
            )
        em.set_thumbnail(
            url=guild_icon
            if guild_icon
            else "https://cdn.discordapp.com/embed/avatars/1.png"
        )
        em.add_field(name=_("Members:"), value=member_msg)
        em.add_field(
            name=_("Channels:"),
            value=_(
                "\N{SPEECH BALLOON} Text: {text}\n{nsfw}"
                "\N{SPEAKER WITH THREE SOUND WAVES} Voice: {voice}"
            ).format(
                text=bold(humanize_number(text_channels)),
                nsfw=_("\N{NO ONE UNDER EIGHTEEN SYMBOL} Nsfw: {}\n").format(
                    bold(humanize_number(nsfw_channels))
                )
                if nsfw_channels
                else "",
                voice=bold(humanize_number(voice_channels)),
            ),
        )
        owner = guild.owner if guild.owner else await self.bot.get_or_fetch_user(guild.owner_id)
        em.add_field(
            name=_("Utility:"),
            value=_(
                "Owner: {owner_mention}\n{owner}\nVerif. level: {verif}\nServer ID: {id}{shard}"
            ).format(
                owner_mention=bold(str(owner.mention)),
                owner=bold(str(owner)),
                verif=bold(verif[str(guild.verification_level)]),
                id=bold(str(guild.id)),
                shard=shard,
            ),
            inline=False,
        )
        em.add_field(
            name=_("Misc:"),
            value=_(
                "AFK channel: {afk_chan}\nAFK timeout: {afk_timeout}\nCustom emojis: {emojis}\nRoles: {roles}"
            ).format(
                afk_chan=bold(str(guild.afk_channel)) if guild.afk_channel else bold(_("Not set")),
                afk_timeout=bold(humanize_timedelta(seconds=guild.afk_timeout)),
                emojis=bold(humanize_number(len(guild.emojis))),
                roles=bold(humanize_number(len(guild.roles))),
            ),
            inline=False,
        )
        if guild_features_list:
            em.add_field(name=_("Server features:"), value="\n".join(guild_features_list))
        if guild.premium_tier != 0:
            nitro_boost = _(
                "Tier {boostlevel} with {nitroboosters} boosters\n"
                "File size limit: {filelimit}\n"
                "Emoji limit: {emojis_limit}\n"
                "VCs max bitrate: {bitrate}"
            ).format(
                boostlevel=bold(str(guild.premium_tier)),
                nitroboosters=bold(humanize_number(guild.premium_subscription_count)),
                filelimit=bold(self.get_size(guild.filesize_limit)),
                emojis_limit=bold(str(guild.emoji_limit)),
                bitrate=bold(self.get_bitsize(guild.bitrate_limit)),
            )
            em.add_field(name=_("Nitro Boost:"), value=nitro_boost)
        if guild.splash:
            em.set_image(url=guild_splash)
        return em

    # -/-/-/-/-/-/-/-/COMMANDS-/-/-/-/-/-/-/-/
    @commands.command()
    @commands.is_owner()
    async def getlibs(self, ctx):
        """Get all current installed packages on the bots venv"""
        packages = [str(p) for p in pkg_resources.working_set]
        packages = sorted(packages, key=str.lower)
        text = ""
        for package in packages:
            text += f"{package}\n"
        embeds = []
        page = 1
        for p in pagify(text):
            embed = discord.Embed(
                description=box(p)
            )
            embed.set_footer(text=f"Page {page}")
            page += 1
            embeds.append(embed)
        if len(embeds) > 1:
            await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def updatelibs(self, ctx):
        """Update all installed packages on the bots venv"""
        async with ctx.typing():
            packages = [dist.project_name for dist in pkg_resources.working_set]
            deps = ' '.join(packages)
            repo = Repo("", "", "", "", Path.cwd())
            async with ctx.typing():
                success = await repo.install_raw_requirements(deps, self.LIB_PATH)

            if success:
                await ctx.send(_("Libraries updated."))
            else:
                await ctx.send(_("Some libraries failed to update. Check your logs for details."))

    @commands.command()
    @commands.is_owner()
    async def pip(self, ctx, *, command: str):
        """Run a pip command"""
        async with ctx.typing():
            command = f"pip {command}"

            def pipexe():
                results = subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8")
                return results

        res = await self.bot.loop.run_in_executor(None, pipexe)
        embeds = []
        page = 1
        for p in pagify(res):
            embed = discord.Embed(
                title="Packages Updated",
                description=box(p)
            )
            embed.set_footer(text=f"Page {page}")
            page += 1
            embeds.append(embed)
        if len(embeds) > 1:
            await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def findguild(self, ctx, guild_id: int):
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

    @commands.command()
    @commands.is_owner()
    async def botstats(self, ctx):
        """
        Get info about the bot

        Inspired by kennnyshiwa's imperialtoolkit botstat command
        https://github.com/kennnyshiwa/kennnyshiwa-cogs
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

            embed = discord.Embed(
                title=_(f"Status for {self.bot.user.name}"),
                description=_(f"Below are various stats about the bot and the server it runs on."),
                color=await ctx.embed_color()
            )

            botstats = f"Servers:     {servers} ({shards} {'shard' if shards == 1 else 'shards'})\n" \
                       f"Users:       {users}\n" \
                       f"Channels:    {channels}\n" \
                       f"Emojis:      {emojis}\n" \
                       f"Cogs:        {cogs}\n" \
                       f"Commands:    {commandcount}\n" \
                       f"Uptime:      {uptime}\n" \
                       f"Red Version: {red_version}\n" \
                       f"dpy Version: {dpy}"
            embed.add_field(
                name="\N{ROBOT FACE} Bot",
                value=box(_(botstats), lang="python"),
                inline=False
            )

            cpustats = f"CPU:   {cpu_type}\n" \
                       f"Cores: {cpu_count}\n"
            if len(cpu_freq) == 1:
                cpustats += f"{cpu_freq[0].current}/{cpu_freq[0].max} Mhz\n"
            else:
                for i, obj in enumerate(cpu_freq):
                    cpustats += f"Core {i}: {obj.current}/{obj.max} Mhz\n"
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
                      f"{diskbar}"
            embed.add_field(
                name=f"\N{FLOPPY DISK} MEM",
                value=box(memtext, lang="python"),
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
    @commands.is_owner()
    async def guilds(self, ctx):
        """
        View info about guilds the bot is in

        Pulled mostly from Trusty's Serverstats cog with love
        https://github.com/TrustyJAID/Trusty-cogs
        """
        async with ctx.typing():
            embeds = []
            page = 0
            guilds = len(self.bot.guilds)
            for i, guild in enumerate(self.bot.guilds):
                em = await self.guild_embed(guild)
                if guild.id == ctx.guild.id:
                    page = i
                em.set_footer(text=f"Page {i + 1}/{guilds}")
                embeds.append(em)
            await menu(ctx, embeds, DEFAULT_CONTROLS, page=page, timeout=120)

    @commands.command()
    async def getuser(self, ctx, *, user_id: Union[int, discord.Member, discord.User]):
        """Find a user by ID"""
        member = await self.bot.get_or_fetch_user(int(user_id))
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
            embed.set_image(url=member.avatar.url)
        else:
            embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def speedtest(self, ctx):
        """
        Test the bot's internet speed

        Pulled from PhasecoreX's netspeed cog with love
        https://github.com/PhasecoreX/PCXCogs
        """
        speed_test = speedtest.Speedtest(secure=True)
        msg = await ctx.send(embed=self.speedtest_embed(0, speed_test.results.dict()))
        await self.bot.loop.run_in_executor(None, speed_test.get_servers)
        await self.bot.loop.run_in_executor(None, speed_test.get_best_server)
        await msg.edit(embed=self.speedtest_embed(1, speed_test.results.dict()))
        await self.bot.loop.run_in_executor(None, speed_test.download)
        await msg.edit(embed=self.speedtest_embed(2, speed_test.results.dict()))
        await self.bot.loop.run_in_executor(None, speed_test.upload)
        await msg.edit(embed=self.speedtest_embed(3, speed_test.results.dict()))
