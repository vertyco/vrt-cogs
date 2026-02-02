import asyncio
import datetime
import logging
import typing as t
from time import perf_counter

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .abc import CompositeMetaClass
from .commands import TicketCommands
from .common.functions import Functions
from .common.models import DB, GuildSettings, migrate_from_old_config, run_migrations
from .common.utils import (
    close_ticket,
    get_ticket_owner,
    prune_invalid_tickets,
    record_response_time,
    ticket_owner_hastyped,
    update_active_overview,
)
from .common.views import CloseView, LogView, PanelView

log = logging.getLogger("red.vrt.tickets")
_ = Translator("Tickets", __file__)


# redgettext -D tickets.py commands/base.py commands/admin.py common/views.py common/menu.py common/utils.py
@cog_i18n(_)
class Tickets(TicketCommands, Functions, commands.Cog, metaclass=CompositeMetaClass):
    """
    Support ticket system with multi-panel functionality
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "3.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        return

    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        self.config.register_global(db={})

        # Pydantic DB
        self.db: DB = DB()
        self.saving: bool = False
        self.initialized: bool = False

        # Cache
        self.valid = []  # Valid ticket channels
        self.views = []  # Saved views to end on reload
        self.view_cache: t.Dict[int, t.List[discord.ui.View]] = {}  # Saved views to end on reload
        self.initializing = False
        self.closing_channels: set[int] = set()  # Channels currently being closed (to avoid race conditions)

        self.auto_close.start()

    async def save(self) -> None:
        """Save the Pydantic DB to Config."""
        if self.saving:
            return
        try:
            self.saving = True
            dump = self.db.model_dump(mode="json")
            await self.config.db.set(dump)
        finally:
            self.saving = False

    async def cog_load(self) -> None:
        asyncio.create_task(self._startup())

    async def cog_unload(self) -> None:
        for view in self.views:
            view.stop()
        self.auto_close.cancel()

    async def _startup(self) -> None:
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(6)
        await self.initialize()

    async def initialize(self, target_guild: discord.Guild | None = None) -> None:
        if target_guild:
            conf = self.db.get_conf(target_guild)
            return await self._init_guild(target_guild, conf)

        t1 = perf_counter()

        # Load data from Config
        data = await self.config.db()
        migrated = False

        if not data:
            # No data in new format, check for old per-guild config data
            log.info("No data or first load, checking for old config to migrate from")
            self.db, migrated = await migrate_from_old_config(self.config)
        else:
            # Data exists, run any pending migrations
            self.db, migrated = await run_migrations(data, self.config)

        if migrated:
            log.info("Migration completed, saving config")
            await self.save()

        for gid, guild_conf in self.db.configs.items():
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            try:
                await self._init_guild(guild, guild_conf)
            except Exception as e:
                log.error(f"Failed to initialize tickets for {guild.name}", exc_info=e)

        self.initialized = True
        td = (perf_counter() - t1) * 1000
        log.info(f"Tickets initialized in {round(td, 1)}ms")

    async def _init_guild(self, guild: discord.Guild, conf: GuildSettings) -> None:
        """Initialize a guild's ticket system.

        Args:
            guild: The Discord guild
            conf: GuildSettings model (from self.db.get_conf(guild))
        """
        # Stop and clear guild views from cache
        views = self.view_cache.setdefault(guild.id, [])
        for view in views:
            view.stop()
        self.view_cache[guild.id].clear()

        # Prune invalid tickets
        await prune_invalid_tickets(guild, conf)
        await self.save()

        # Refresh overview panel
        new_id = await update_active_overview(guild, conf)
        if new_id:
            conf.overview_msg = new_id
            await self.save()

        # Refresh buttons for all panels
        prefetched = []
        to_deploy = {}  # Message ID keys for multi-button support
        for panel_name, panel in conf.panels.items():
            category_id = panel.category_id
            channel_id = panel.channel_id
            message_id = panel.message_id
            if any([not category_id, not channel_id, not message_id]):
                # Panel does not have all channels set
                continue

            category = guild.get_channel(category_id)
            channel_obj = guild.get_channel(channel_id)
            if isinstance(channel_obj, discord.ForumChannel) or isinstance(channel_obj, discord.CategoryChannel):
                log.error(f"Invalid channel type for panel {panel_name} in {guild.name}")
                continue
            if any([not category, not channel_obj]):
                if not category:
                    log.error(f"Invalid category for panel {panel_name} in {guild.name}")
                if not channel_obj:
                    log.error(f"Invalid channel for panel {panel_name} in {guild.name}")
                continue

            if message_id not in prefetched:
                try:
                    await channel_obj.fetch_message(message_id)
                    prefetched.append(message_id)
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    log.error(f"I can no longer see the {panel_name} panel's channel in {guild.name}")
                    continue

            key = f"{channel_id}-{message_id}"
            if key in to_deploy:
                to_deploy[key].append((panel_name, panel))
            else:
                to_deploy[key] = [(panel_name, panel)]

        if not to_deploy:
            return

        try:
            for panels in to_deploy.values():
                sorted_panels = sorted(panels, key=lambda x: x[1].priority)
                panelview = PanelView(self.bot, guild, self, sorted_panels)
                # Panels can change so we want to edit every time
                await panelview.start()
                self.view_cache[guild.id].append(panelview)
        except discord.NotFound:
            log.warning(f"Failed to refresh panels in {guild.name}")

        # Refresh view for logs of opened tickets
        for uid, opened_tickets in conf.opened.items():
            member = guild.get_member(uid)
            if not member:
                continue
            for ticket_channel_id, ticket_info in opened_tickets.items():
                ticket_channel = guild.get_channel_or_thread(ticket_channel_id)
                if not ticket_channel:
                    continue

                # v2.0.0 stores message id for close button to re-init views on reload
                if message_id := ticket_info.message_id:
                    view = CloseView(self.bot, self, uid, ticket_channel)
                    self.bot.add_view(view, message_id=message_id)
                    self.view_cache[guild.id].append(view)

                if not ticket_info.logmsg:
                    continue

                panel_name = ticket_info.panel
                if panel_name not in conf.panels:
                    continue
                panel = conf.panels[panel_name]
                if not panel.log_channel:
                    continue
                log_channel = guild.get_channel(panel.log_channel)
                if not log_channel:
                    log.warning(f"Log channel no longer exits for {member.name}'s ticket in {guild.name}")
                    continue

                max_claims = ticket_info.max_claims
                logview = LogView(guild, ticket_channel, max_claims, cog=self)
                self.bot.add_view(logview, message_id=ticket_info.logmsg)
                self.view_cache[guild.id].append(logview)

    @tasks.loop(minutes=20)
    async def auto_close(self):
        if not self.initialized:
            return
        actasks = []
        for gid, conf in self.db.configs.items():
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            inactive = conf.inactive
            if not inactive:
                continue
            opened = conf.opened
            if not opened:
                continue
            for uid, tickets in opened.items():
                member = guild.get_member(uid)
                if not member:
                    continue
                for channel_id, ticket in tickets.items():
                    has_response = ticket.has_response
                    if has_response and channel_id not in self.valid:
                        self.valid.append(channel_id)
                        continue
                    if channel_id in self.valid:
                        continue
                    channel = guild.get_channel_or_thread(channel_id)
                    if not channel:
                        continue
                    now = datetime.datetime.now().astimezone()
                    opened_on = ticket.opened
                    hastyped = await ticket_owner_hastyped(channel, member)
                    if hastyped and channel_id not in self.valid:
                        self.valid.append(channel_id)
                        continue
                    td = (now - opened_on).total_seconds() / 3600
                    next_td = td + 0.33
                    if td < inactive <= next_td:
                        # Ticket hasn't expired yet but will in the next loop
                        warning = _(
                            "If you do not respond to this ticket "
                            "within the next 20 minutes it will be closed automatically."
                        )
                        await channel.send(f"{member.mention}\n{warning}")
                        continue
                    elif td < inactive:
                        continue

                    time = "hours" if inactive != 1 else "hour"
                    try:
                        await close_ticket(
                            bot=self.bot,
                            member=member,
                            guild=guild,
                            channel=channel,
                            conf=conf,
                            reason=_("(Auto-Close) Opened ticket with no response for ") + f"{inactive} {time}",
                            closedby=self.bot.user.id,
                            cog=self,
                        )
                        log.info(
                            f"Ticket opened by {member.name} has been auto-closed.\n"
                            f"Has typed: {hastyped}\n"
                            f"Hours elapsed: {td}"
                        )
                    except Exception as e:
                        log.error(f"Failed to auto-close ticket for {member} in {guild.name}\nException: {e}")

        if actasks:
            await asyncio.gather(*actasks)

    @auto_close.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(300)

    # Will automatically close/cleanup any tickets if a member leaves that has an open ticket
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        if not self.initialized:
            return
        guild = member.guild
        if not guild:
            return
        conf = self.db.get_conf(guild)
        opened = conf.opened
        member_id = member.id
        if member_id not in opened:
            return
        tickets = opened[member_id]
        if not tickets:
            return

        for channel_id in tickets:
            chan = guild.get_channel_or_thread(channel_id)
            if not chan:
                continue
            try:
                await close_ticket(
                    bot=self.bot,
                    member=member,
                    guild=guild,
                    channel=chan,
                    conf=conf,
                    reason=_("User left guild(Auto-Close)"),
                    closedby=self.bot.user.id,
                    cog=self,
                )
            except Exception as e:
                log.error(f"Failed to auto-close ticket for {member} leaving {member.guild}\nException: {e}")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if not thread:
            return
        if not self.initialized:
            return
        # Skip if this thread is being closed by close_ticket()
        if thread.id in self.closing_channels:
            return
        guild = thread.guild
        conf = self.db.get_conf(guild)
        pruned = await prune_invalid_tickets(guild, conf)
        if pruned:
            await self.save()
            log.info("Pruned old ticket threads")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not channel:
            return
        if not self.initialized:
            return
        # Skip if this channel is being closed by close_ticket()
        if channel.id in self.closing_channels:
            return
        guild = channel.guild
        conf = self.db.get_conf(guild)
        pruned = await prune_invalid_tickets(guild, conf)
        if pruned:
            await self.save()
            log.info("Pruned old ticket channels")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track staff first response time in tickets."""
        if not message.guild:
            return
        if message.author.bot:
            return
        if not self.initialized:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        guild = message.guild
        conf = self.db.get_conf(guild)
        opened = conf.opened
        if not opened:
            return

        # Check if this channel is a ticket
        channel_id = message.channel.id
        owner_id = get_ticket_owner(opened, channel_id)
        if not owner_id:
            return

        ticket = opened[owner_id].get(channel_id)
        if not ticket:
            return

        # Don't track if this is the ticket owner
        if message.author.id == owner_id:
            log.debug("Response time: Skipping - author is ticket owner")
            return

        # Check if already responded
        if ticket.first_response is not None:
            # Already has a response time recorded
            log.debug(f"Response time: Skipping - already has first_response: {ticket.first_response}")
            return

        # Check if author is a support staff member or has admin perms
        panel_name = ticket.panel
        if not panel_name or panel_name not in conf.panels:
            log.debug(f"Response time: Skipping - panel not found: {panel_name}")
            return

        panel = conf.panels[panel_name]
        support_role_ids = {r[0] for r in conf.support_roles}
        panel_role_ids = {r[0] for r in panel.roles}
        all_support_roles = support_role_ids | panel_role_ids

        author_role_ids = {r.id for r in message.author.roles}
        is_staff = bool(author_role_ids & all_support_roles)

        log.debug(
            f"Response time: support_roles={support_role_ids}, panel_roles={panel_role_ids}, author_roles={author_role_ids}, is_staff={is_staff}"
        )

        # Also count as staff if they have admin permissions or are guild owner
        if not is_staff:
            member = message.author
            if isinstance(member, discord.Member):
                is_staff = member.guild_permissions.administrator or member.id == guild.owner_id
                log.debug(
                    f"Response time: Checking admin - is_admin={member.guild_permissions.administrator}, is_owner={member.id == guild.owner_id}"
                )

        if not is_staff:
            log.debug("Response time: Skipping - author is not staff")
            return

        # Record the first response time
        log.info(f"Response time: Recording response time for ticket {channel_id}")
        await record_response_time(
            cog=self,
            guild=guild,
            channel_id=channel_id,
            ticket=ticket,
            staff_id=message.author.id,
        )
