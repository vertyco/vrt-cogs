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
from ..common.analytics import record_ticket_claimed
from ..common.utils import can_close, close_ticket, get_ticket_owner

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


class BaseCommands(MixinMeta):
    @commands.hybrid_command(name="add", description="Add a user to your ticket")
    @app_commands.describe(user="The Discord user you want to add to your ticket")
    @commands.guild_only()
    async def add_user_to_ticket(self, ctx: commands.Context, *, user: discord.Member):
        """Add a user to your ticket"""
        conf = self.db.get_conf(ctx.guild)
        opened = conf.opened
        owner_id = get_ticket_owner(opened, ctx.channel.id)
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel, or it has been removed from config"))

        panel_name = opened[owner_id][ctx.channel.id].panel
        panel_roles = conf.panels[panel_name].roles
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf.support_roles]
        support_roles.extend([i[0] for i in panel_roles])

        # If a mod tries
        can_add = False
        if any(i in support_roles for i in user_roles):
            can_add = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_add = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_add = True
        elif owner_id == ctx.author.id and conf.user_can_manage:
            can_add = True

        if not can_add:
            return await ctx.send(_("You do not have permissions to add users to this ticket"))

        channel = ctx.channel
        try:
            if isinstance(channel, discord.TextChannel):
                await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
            else:
                await channel.add_user(user)
        except Exception as e:
            log.exception(f"Failed to add {user.name} to ticket", exc_info=e)
            txt = _("Failed to add user to ticket: {}").format(str(e))
            return await ctx.send(txt)
        await ctx.send(f"**{user.name}** " + _("has been added to this ticket!"))

    @commands.hybrid_command(name="renameticket", description="Rename your ticket")
    @app_commands.describe(new_name="The new name for your ticket")
    @commands.guild_only()
    async def rename_ticket(self, ctx: commands.Context, *, new_name: str):
        """Rename your ticket channel"""
        conf = self.db.get_conf(ctx.guild)
        opened = conf.opened
        owner_id = get_ticket_owner(opened, ctx.channel.id)
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel, or it has been removed from config"))

        panel_name = opened[owner_id][ctx.channel.id].panel
        panel_roles = conf.panels[panel_name].roles
        user_roles = [r.id for r in ctx.author.roles]

        support_roles = [i[0] for i in conf.support_roles]
        support_roles.extend([i[0] for i in panel_roles])

        can_rename = False
        if any(i in support_roles for i in user_roles):
            can_rename = True
        elif ctx.author.id == ctx.guild.owner_id:
            can_rename = True
        elif await is_admin_or_superior(self.bot, ctx.author):
            can_rename = True
        elif owner_id == ctx.author.id and conf.user_can_rename:
            can_rename = True

        if not can_rename:
            return await ctx.send(_("You do not have permissions to rename this ticket"))
        if not ctx.channel.permissions_for(ctx.me).manage_channels:
            return await ctx.send(_("I no longer have permission to edit this channel"))

        if isinstance(ctx.channel, discord.TextChannel):
            txt = _("Renaming channel to {}").format(f"**{new_name}**")
            if ctx.interaction:
                await ctx.interaction.response.send_message(txt)
            else:
                await ctx.send(txt)
        else:
            # Threads already alert to name changes
            await ctx.tick()

        await ctx.channel.edit(name=new_name)

    @commands.hybrid_command(name="escalate", description="Escalate a ticket to admins only")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def escalate_ticket(self, ctx: commands.Context):
        """Escalate a ticket to admins only

        Removes support/moderator roles from the ticket while keeping
        the ticket owner and any users that were manually added.
        Only admin roles (set via Red's admin role config) will retain access.
        """
        conf = self.db.get_conf(ctx.guild)
        opened = conf.opened
        owner_id = get_ticket_owner(opened, ctx.channel.id)
        if not owner_id:
            return await ctx.send(_("This is not a ticket channel, or it has been removed from config"))

        ticket = opened[owner_id][ctx.channel.id]
        panel = conf.panels.get(ticket.panel)
        support_role_ids = conf.get_support_role_ids(panel)
        if not support_role_ids:
            return await ctx.send(_("There are no support roles configured to remove"))

        admin_role_ids = await self.bot.get_admin_role_ids(ctx.guild)

        # Only remove support roles that are NOT admin roles
        roles_to_remove = support_role_ids - admin_role_ids
        if not roles_to_remove:
            return await ctx.send(_("All support roles are also admin roles, nothing to escalate"))

        channel = ctx.channel
        removed = []
        if isinstance(channel, discord.TextChannel):
            for role_id in roles_to_remove:
                role = ctx.guild.get_role(role_id)
                if not role:
                    continue
                overwrite = channel.overwrites_for(role)
                if overwrite.is_empty():
                    continue
                try:
                    await channel.set_permissions(role, overwrite=None)
                    removed.append(role.name)
                except discord.Forbidden:
                    log.warning(f"Missing permissions to remove {role.name} from ticket {channel.id}")
                except Exception as e:
                    log.error(f"Failed to remove {role.name} from ticket", exc_info=e)
        elif isinstance(channel, discord.Thread):
            # For threads, remove individual members who belong to support roles but not admin roles
            try:
                thread_members = await channel.fetch_members()
            except Exception:
                thread_members = []
            for tm in thread_members:
                member = ctx.guild.get_member(tm.id)
                if not member or member.id == owner_id or member.id == ctx.guild.me.id:
                    continue
                member_role_ids = {r.id for r in member.roles}
                is_support = bool(member_role_ids & support_role_ids)
                is_admin = bool(member_role_ids & admin_role_ids) or await is_admin_or_superior(self.bot, member)
                if is_support and not is_admin:
                    try:
                        await channel.remove_user(member)
                        removed.append(member.display_name)
                    except Exception as e:
                        log.error(f"Failed to remove {member} from thread ticket", exc_info=e)

        if removed:
            names = ", ".join(f"**{n}**" for n in removed)
            await ctx.send(_("Ticket escalated to admins. Removed: {}").format(names))
        else:
            await ctx.send(_("Ticket escalated to admins. No support staff needed to be removed"))

    @commands.hybrid_command(name="close", description="Close your ticket")
    @app_commands.describe(reason="Reason for closing the ticket")
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
        conf = self.db.get_conf(ctx.guild)
        owner_id = get_ticket_owner(conf.opened, ctx.channel.id)
        if not owner_id:
            return await ctx.send(
                _(
                    "Cannot find the owner of this ticket! Maybe it is not a ticket channel or was cleaned from the config?"
                )
            )

        user_can_close = await can_close(self.bot, ctx.guild, ctx.channel, ctx.author, owner_id, conf)
        if not user_can_close:
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

                conf = self.db.get_conf(ctx.guild)
                owner_id = get_ticket_owner(conf.opened, ctx.channel.id)
                if not owner_id:
                    # Ticket already closed...
                    return

        if ctx.interaction:
            await ctx.interaction.response.send_message(_("Closing..."), ephemeral=True, delete_after=4)
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=ctx.guild,
            channel=ctx.channel,
            conf=conf,
            reason=reason,
            closedby=ctx.author.id,
            cog=self,
        )

    @commands.hybrid_command(name="claimticket", description="Claim a ticket as your responsibility")
    @app_commands.describe(channel="The ticket channel to claim (defaults to current channel)")
    @commands.guild_only()
    async def claim_ticket(
        self,
        ctx: commands.Context,
        channel: discord.abc.GuildChannel | None = None,
    ):
        """
        Claim a ticket as your responsibility.

        The first support staff member to send a message in a ticket is auto-claimed.
        Use this command to manually claim a ticket (or take over an existing claim).

        **Examples:**
        `[p]claimticket` - claim the current ticket channel
        `[p]claimticket #channel` - claim a specific ticket channel
        """
        conf = self.db.get_conf(ctx.guild)
        target_channel = channel or ctx.channel

        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            return await ctx.send(_("That is not a valid ticket channel."))

        owner_id = get_ticket_owner(conf.opened, target_channel.id)
        if not owner_id:
            return await ctx.send(_("That channel is not an open ticket."))

        ticket = conf.opened[owner_id][target_channel.id]
        panel = conf.panels.get(ticket.panel)

        # Check caller is support staff or admin
        if not conf.is_support_staff(ctx.author, panel) and not await is_admin_or_superior(self.bot, ctx.author):
            return await ctx.send(_("You do not have permission to claim tickets."))

        previous_claimer_id = ticket.claimed_by
        ticket.claimed_by = ctx.author.id
        record_ticket_claimed(conf, ctx.author.id, target_channel.id, ticket.panel)
        await self.save()

        if previous_claimer_id and previous_claimer_id != ctx.author.id:
            previous_claimer = ctx.guild.get_member(previous_claimer_id)
            prev_name = previous_claimer.display_name if previous_claimer else str(previous_claimer_id)
            await ctx.send(
                _("✅ {claimer} has claimed {channel} (previously claimed by {prev}).").format(
                    claimer=ctx.author.display_name,
                    channel=target_channel.mention,
                    prev=prev_name,
                )
            )
        else:
            await ctx.send(
                _("✅ {claimer} has claimed {channel}.").format(
                    claimer=ctx.author.display_name,
                    channel=target_channel.mention,
                )
            )
