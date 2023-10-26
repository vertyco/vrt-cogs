import asyncio
import logging
import math
import typing as t

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number, text_to_file

from ..common import get_bot_percentage
from ..common.abc import MixinMeta
from ..common.views import Confirm, DynamicMenu

log = logging.getLogger("red.vrt.guildlock.commands")
_ = Translator("GuildLock", __file__)


@cog_i18n(_)
class Base(MixinMeta):
    @commands.group(aliases=["glock"])
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def guildlock(self, ctx: commands.Context):
        """View GuildLock settings"""
        disabled = _("Disabled")
        if ctx.invoked_subcommand is None:
            title = _("GuildLock Settings")
            desc = _("Tools for managing guild joins and leaves.")
            embed = discord.Embed(title=title, description=desc, color=ctx.author.color)

            n = _("Log Channel")
            v = f"<#{self.db.log_channel}>" if self.db.log_channel else _("Not Set")
            embed.add_field(name=n, value=v, inline=False)

            n = _("Guild Limit")
            v = _("Bot will auto-leave new guilds if in more than {} servers already.").format(f"**{self.db.limit}**")
            if not self.db.limit:
                v = disabled
            embed.add_field(name=n, value=v, inline=False)

            n = _("Minimum Member Requirement")
            v = _("Bot will auto-leave guilds with less than {} members.").format(f"**{self.db.min_members}**")
            if not self.db.min_members:
                v = disabled
            embed.add_field(name=n, value=v, inline=False)

            n = _("Bot Farm Detection")
            v = _("Bot will auto-leave guilds where more than {}% of the members are bots.").format(
                f"**{self.db.bot_ratio}**"
            )
            if not self.db.bot_ratio:
                v = disabled
            embed.add_field(name=n, value=v, inline=False)

            n = _("Guild Whitelist")
            v = ""
            for guild_id in self.db.whitelist:
                guild = self.bot.get_guild(guild_id)
                v += f"{guild.name} ({guild.id})\n" if guild else _("Not in Guild ({})\n").format(guild_id)
            embed.add_field(name=n, value=v or _("None Set"), inline=False)

            n = _("Guild Blacklist")
            v = "\n".join(self.db.blacklist)
            embed.add_field(name=n, value=v or _("None Set"), inline=False)
            await ctx.send(embed=embed)

    @guildlock.command(aliases=["chan"])
    async def channel(self, ctx: commands.Context, *, channel: discord.TextChannel | discord.Thread = None):
        """Set the log channel for the bot"""
        if not channel:
            channel = ctx.channel
        self.db.log_channel = channel.id
        self.db.log_guild = ctx.guild.id
        txt = _("Guild events will be logged to {}").format(channel.mention)
        await ctx.send(txt)
        await self.save()

    @guildlock.command(aliases=["lim"])
    async def limit(self, ctx: commands.Context, limit: int):
        """
        Set the maximum amount of guilds the bot can be in.

        Set to **0** to disable the guild limit.
        """
        self.db.limit = limit
        if limit:
            txt = _("Guild limit set to {}").format(f"**{limit}**")
        else:
            txt = _("Guild limit **Disabled**")
        await ctx.send(txt)
        await self.save()

    @guildlock.command(aliases=["mm"])
    async def minmembers(self, ctx: commands.Context, minimum_members: int):
        """
        Set the minimum number of members a server should have for the bot to stay in it.

        Set to **0** to disable.
        """
        self.db.min_members = minimum_members
        if minimum_members:
            txt = _("Minimum members required for bot to stay has been set to {}").format(f"**{minimum_members}**")
        else:
            txt = _("Minimum member requirement **Disabled**")
        await ctx.send(txt)
        await self.save()

    @guildlock.command(aliases=["br"])
    async def botratio(self, ctx: commands.Context, bot_ratio: int):
        """
        Set the the threshold percentage of bots-to-members for the bot to auto-leave.

        **Example**
        If bot ratio is 60% and it joins a guild with 10 members (7 bots and 3 members) it will auto-leave since that ratio is 70%.

        Set to **0** to disable.
        """
        self.db.bot_ratio = bot_ratio
        if bot_ratio:
            txt = _("The bot will now leave servers that have more than {}% bots").format(f"**{bot_ratio}**")
        else:
            txt = _("Bot percentage threshold for auto-leaving has been **Disabled**")
        await ctx.send(txt)
        await self.save()

    @guildlock.command(aliases=["bl"])
    async def blacklist(self, ctx: commands.Context, guild_id: int):
        """
        Add/Remove a guild from the blacklist.

        To remove a guild from the blacklist, specify it again.
        """
        if guild_id in self.db.blacklist:
            self.db.blacklist.remove(guild_id)
            txt = _("Guild removed from blacklist")
        else:
            self.db.blacklist.append(guild_id)
            txt = _("Guild added to the blacklist")
        await ctx.send(txt)
        await self.save()

    @guildlock.command(aliases=["wl"])
    async def whitelist(self, ctx: commands.Context, guild_id: int):
        """
        Add/Remove a guild from the whitelist.

        To remove a guild from the whitelist, specify it again.
        """
        if guild_id in self.db.whitelist:
            self.db.whitelist.remove(guild_id)
            txt = _("Guild removed from whitelist")
        else:
            self.db.whitelist.append(guild_id)
            txt = _("Guild added to the whitelist")
        await ctx.send(txt)
        await self.save()

    async def type_check(self, ctx: commands.Context, check: str) -> bool | None:
        if check == "botfarms" and not self.db.bot_ratio:
            await ctx.send(_("there is no bot ratio set!"))
            return
        elif check == "minmembers" and not self.db.min_members:
            await ctx.send(_("Minimum member requirement has not been set!"))
            return
        elif check == "blacklist" and not self.db.blacklist:
            await ctx.send(_("There are no guild IDs in the blacklist!"))
            return
        elif check == "whitelist" and not self.db.whitelist:
            await ctx.send(_("There are no guild IDs in the whitelist!"))
            return
        return True

    async def get_guilds_type(self, check: str) -> list[discord.Guild]:
        guilds: list[discord.Guild] = []
        for guild in self.bot.guilds:
            if guild.id in self.db.whitelist:
                continue
            if check == "botfarms":
                ratio = await asyncio.to_thread(get_bot_percentage, guild)
                if ratio > self.db.bot_ratio:
                    guilds.append(guild)
            elif check == "minmembers":
                count = guild.member_count or len(guild.members)
                if count < self.db.min_members:
                    guilds.append(guild)
            elif check == "blacklist" and guild.id in self.db.blacklist:
                guilds.append(guild)
        return guilds

    def guild_embeds(self, guilds: list[discord.Guild], title: str, color: discord.Color) -> list[discord.Embed]:
        embeds = []
        start = 0
        stop = 5
        pages = math.ceil(len(guilds) / 5)
        for p in range(pages):
            embed = discord.Embed(title=title, color=color)
            if stop > len(guilds):
                stop = len(guilds)
            for i in range(start, stop):
                guild: discord.Guild = guilds[i]
                bots = sum(i.bot for i in guild.members)
                members = (guild.member_count or len(guild.members)) - bots
                fname = guild.name
                fval = _("- Members: {}\n- Bots: {}").format(f"**{humanize_number(members)}**", f"**{bots}**")
                embed.add_field(name=fname, value=fval, inline=False)
            embed.set_footer(text=_("Page {}").format(f"{p + 1}/{pages}"))
            start += 5
            stop += 5
            embeds.append(embed)
        return embeds

    @guildlock.command()
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def leave(
        self,
        ctx: commands.Context,
        check: t.Literal["botfarms", "minmembers", "blacklist", "whitelist"],
    ):
        """
        Make the bot leave certain servers.


        **Leave Arguments**
        - `botfarms`: leave servers with a bot ratio above the set percentage.
        - `minmembers`: leave servers with a member count below the set amount.
        - `blacklist`: leave any servers in the blacklist.
        - `whitelist`: leave any server not in the whitelist.
        """
        if not await self.type_check(ctx, check):
            return
        guilds = await self.get_guilds_type(check)

        texts = {
            "botfarms": _("There are no guilds to leave with a bot ratio higher than {}%").format(self.db.bot_ratio),
            "minmembers": _("There are no guilds to leave that have less than {} members").format(self.db.min_members),
            "blacklist": _("There are no guilds to leave that are in the blacklist"),
            "whitelist": _("There are no guilds to leave that are in the whitelist"),
        }
        if not guilds:
            return await ctx.send(texts[check])

        grammar = _("guild") if len(guilds) == 1 else _("guilds")
        txt = _("Are you sure you want to leave {}?").format(f"**{len(guilds)}** {grammar}")
        joined = "\n".join(f"- {i.name} ({i.id}) [{i.owner.name}]" for i in guilds)

        if len(joined) > 3900:
            file = text_to_file(joined, filename=_("Guilds to Leave") + ".txt")
        else:
            txt += f"\n{box(joined)}"
            file = None

        view = Confirm(ctx.author)
        msg = await ctx.send(embed=discord.Embed(description=txt, color=discord.Color.red()), view=view, file=file)
        await view.wait()
        if not view.value:
            txt = _("Not leaving {}").format(f"**{len(guilds)}** {grammar}")
            return await msg.edit(embed=None, content=txt, view=None)

        txt = _("Leaving {}, one moment...").format(f"**{len(guilds)}** {grammar}")
        await msg.edit(embed=None, content=txt, view=None)

        async with ctx.typing():
            for guild in guilds:
                if not guild:
                    continue
                await self.notify_guild(log_type=check, guild=guild)
                await guild.leave()

        txt = _("I have left {}!").format(f"**{len(guilds)}** {grammar}")
        await msg.edit(content=txt)

    @guildlock.command()
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def view(
        self,
        ctx: commands.Context,
        check: t.Literal["botfarms", "minmembers", "blacklist", "whitelist"],
    ):
        """
        View servers that fall under the auto-leave thresholds.


        **Arguments**
        - `botfarms`: show servers with a bot ratio above the set percentage.
        - `minmembers`: show servers with a member count below the set amount.
        - `blacklist`: show any servers in the blacklist.
        - `whitelist`: show any server not in the whitelist.
        """
        if not await self.type_check(ctx, check):
            return
        guilds = await self.get_guilds_type(check)
        if not guilds:
            return await ctx.send(_("No guilds found!"))
        titles = {
            "botfarms": _("Guilds with {}% or more bots").format(self.db.bot_ratio),
            "minmembers": _("Guilds with less than {} members").format(self.db.min_members),
            "blacklist": _("Blacklisted guilds"),
            "whitelist": _("Un-Whitelisted guilds"),
        }
        title = titles[check]
        embeds = await asyncio.to_thread(self.guild_embeds, guilds, title, ctx.author.color)
        await DynamicMenu(ctx.author, embeds, ctx.channel).refresh()
