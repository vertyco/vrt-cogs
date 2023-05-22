import asyncio
import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.commands import parse_timedelta
from redbot.core.i18n import Translator
from redbot.core.utils.mod import is_admin_or_superior

from ..abc import MixinMeta

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


class BaseCommands(MixinMeta):
    @commands.hybrid_command(name="add", description="Add a user to your ticket")
    @app_commands.describe(user="The Discord user you want to add to your ticket")
    # @commands.command(name="add")
    @commands.guild_only()
    async def add_user_to_ticket(self, ctx: commands.Context, *, user: discord.Member):
        """Add a user to your ticket"""
        conf = await self.config.guild(ctx.guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(
                _("This is not a ticket channel, or it has been removed from config")
            )

        panel_name = opened[owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"]
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])

        # If a mod tries
        can_add = False
        if any(i in support_roles for i in user_roles):
            can_add = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_add = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_add = True
        elif owner_id == str(ctx.author.id) and conf["user_can_manage"]:
            can_add = True

        if not can_add:
            return await ctx.send(_("You do not have permissions to add users to this ticket"))

        channel = ctx.channel
        if isinstance(channel, discord.TextChannel):
            await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
        else:
            await channel.add_user(user)
        await ctx.send(f"**{user.name}** " + _("has been added to this ticket!"))

    @commands.hybrid_command(name="renameticket", description="Rename your ticket")
    @app_commands.describe(new_name="The new name for your ticket")
    # @commands.command(name="renameticket", aliases=["renamet"])
    @commands.guild_only()
    async def rename_ticket(self, ctx: commands.Context, *, new_name: str):
        """Rename your ticket channel"""
        conf = await self.config.guild(ctx.guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(
                _("This is not a ticket channel, or it has been removed from config")
            )

        panel_name = opened[owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"]
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])

        can_rename = False
        if any(i in support_roles for i in user_roles):
            can_rename = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_rename = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_rename = True
        elif owner_id == str(ctx.author.id) and conf["user_can_rename"]:
            can_rename = True

        if not can_rename:
            return await ctx.send(_("You do not have permissions to rename this ticket"))
        await ctx.channel.edit(name=new_name)
        # Threads already alert to name changes
        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.send(_("Ticket has been renamed"))
        elif ctx.interaction:
            await ctx.interaction.response.defer()

    @commands.hybrid_command(name="close", description="Close your ticket")
    @app_commands.describe(reason="Reason for closing the ticket")
    # @commands.command(name="close")
    @commands.guild_only()
    async def close_a_ticket(self, ctx: commands.Context, *, reason: Optional[str] = None):
        """
        Close your ticket

        **Examples**
        `[p]close` - closes ticket with no reason attached
        `[p]close thanks for helping!` - closes with reason "thanks for helping!"
        `[p]close 1h` - closes in 1 hour with no reason attached
        `[p]close 1m thanks for helping!` - closes in 1 minute with reason "thanks for helping!"
        """
        conf = await self.config.guild(ctx.guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(ctx.channel.id))
        if not owner_id:
            return await ctx.send(
                _("Cannot find the owner of this ticket! " "Maybe it was removed from config?")
            )

        panel_name = opened[owner_id][str(ctx.channel.id)]["panel"]
        panel_roles = conf["panels"][panel_name]["roles"]
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf["support_roles"]]
        support_roles.extend([i[0] for i in panel_roles])

        can_close = False
        if any(i in support_roles for i in user_roles):
            can_close = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_close = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_close = True
        elif owner_id == str(ctx.author.id) and conf["user_can_close"]:
            can_close = True

        if not can_close:
            return await ctx.send(_("You do not have permissions to close this ticket"))
        else:
            owner = ctx.guild.get_member(int(owner_id))
            if not owner:
                owner = await self.bot.fetch_user(int(owner_id))

        if reason:
            timestring = reason.split(" ")[0]
            if td := parse_timedelta(timestring):

                def check(m: discord.Message):
                    return m.channel.id == ctx.channel.id and not m.author.bot

                reason = reason.replace(timestring, "")
                if not reason.strip():
                    # User provided delayed close with no reason attached
                    reason = None
                closing_in = int((datetime.datetime.now() + td).timestamp())
                closemsg = _("This ticket will close {}").format(f"<t:{closing_in}:R>")
                msg = await ctx.send(f"{owner.mention}, {closemsg}")
                await asyncio.sleep(1.5)
                try:
                    await ctx.bot.wait_for("message", check=check, timeout=td.total_seconds())
                except asyncio.TimeoutError:
                    pass
                else:
                    cancelled = _("Closing cancelled!")
                    await msg.edit(content=cancelled)
                    return
        if ctx.interaction:
            await ctx.interaction.response.send_message(
                _("Closing..."), ephemeral=True, delete_after=4
            )
        await self.close_ticket(
            member=owner,
            guild=ctx.guild,
            channel=ctx.channel,
            conf=conf,
            reason=reason,
            closedby=ctx.author.display_name,
        )
