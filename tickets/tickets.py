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
from .common.constants import DEFAULT_GUILD
from .common.functions import Functions
from .common.utils import (
    close_ticket,
    prune_invalid_tickets,
    ticket_owner_hastyped,
    update_active_overview,
)
from .common.views import CloseView, LogView, PanelView

log = logging.getLogger("red.vrt.tickets")
_ = Translator("Tickets", __file__)


# redgettext -D tickets.py commands/base.py commands/admin.py views.py menu.py utils.py
@cog_i18n(_)
class Tickets(TicketCommands, Functions, commands.Cog, metaclass=CompositeMetaClass):
    """
    Support ticket system with multi-panel functionality
    """

    __author__ = "Vertyco"
    __version__ = "2.7.3"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" f"Cog Version: {self.__version__}\n" f"Author: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        return

    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        self.config.register_guild(**DEFAULT_GUILD)

        # Cache
        self.valid = []  # Valid ticket channels
        self.views = []  # Saved views to end on reload
        self.view_cache: t.Dict[int, t.List[discord.ui.View]] = {}  # Saved views to end on reload
        self.initializing = False

        self.auto_close.start()

    async def cog_load(self) -> None:
        asyncio.create_task(self._startup())

    async def cog_unload(self) -> None:
        self.auto_close.cancel()
        for view in self.views:
            view.stop()

    async def _startup(self) -> None:
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(6)
        await self.initialize()

    async def initialize(self, target_guild: discord.Guild = None) -> None:
        if target_guild:
            data = await self.config.guild(target_guild).all()
            return await self._init_guild(target_guild, data)

        t1 = perf_counter()
        conf = await self.config.all_guilds()
        for gid, data in conf.items():
            if not data:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            try:
                await self._init_guild(guild, data)
            except Exception as e:
                log.error(f"Failed to initialize tickets for {guild.name}", exc_info=e)

        td = (perf_counter() - t1) * 1000
        log.info(f"Tickets initialized in {round(td, 1)}ms")

    async def _init_guild(self, guild: discord.Guild, data: dict) -> None:
        # Stop and clear guild views from cache
        views = self.view_cache.setdefault(guild.id, [])
        for view in views:
            view.stop()
        self.view_cache[guild.id].clear()

        pruned = await prune_invalid_tickets(guild, data, self.config)
        if pruned:
            data = await self.config.guild(guild).all()

        # Refresh overview panel
        new_id = await update_active_overview(guild, data)
        if new_id:
            await self.config.guild(guild).overview_msg.set(new_id)

        # v1.14.0 Migration, new support role schema
        cleaned = []
        for i in data["support_roles"]:
            if isinstance(i, int):
                cleaned.append([i, False])
        if cleaned:
            await self.config.guild(guild).support_roles.set(cleaned)

        # Refresh buttons for all panels
        migrations = False
        all_panels = data["panels"]
        prefetched = []
        to_deploy = {}  # Message ID keys for multi-button support
        for panel_name, panel in all_panels.items():
            category_id = panel["category_id"]
            channel_id = panel["channel_id"]
            message_id = panel["message_id"]
            if any([not category_id, not channel_id, not message_id]):
                continue

            category = guild.get_channel(category_id)
            channel_obj = guild.get_channel(channel_id)
            if any([not category, not channel_obj]):
                continue

            if message_id not in prefetched:
                try:
                    await channel_obj.fetch_message(message_id)
                    prefetched.append(message_id)
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    log.info(f"I can no longer see a set panel channel in {guild.name}")
                    continue

            # v1.3.10 schema update (Modals)
            if "modals" not in panel:
                panel["modals"] = {}
                migrations = True
            # Schema update (Sub support roles)
            if "roles" not in panel:
                panel["roles"] = []
                migrations = True
            # v1.14.0 Schema update (Mentionable support roles + alt channel)
            cleaned = []
            for i in panel["roles"]:
                if isinstance(i, int):
                    cleaned.append([i, False])
            if cleaned:
                panel["roles"] = cleaned
                migrations = True
            if "alt_channel" not in panel:
                panel["alt_channel"] = 0
                migrations = True
            # v1.15.0 schema update (Button priority and rows)
            if "row" not in panel or "priority" not in panel:
                panel["row"] = None
                panel["priority"] = 1
                migrations = True
            # v2.4.0 schema update (Disable panels)
            if "disabled" not in panel:
                panel["disabled"] = False
                migrations = True

            panel["name"] = panel_name
            key = f"{channel_id}-{message_id}"
            if key in to_deploy:
                to_deploy[key].append(panel)
            else:
                to_deploy[key] = [panel]

        if not to_deploy:
            return

        # Update config for any migrations
        if migrations:
            await self.config.guild(guild).panels.set(all_panels)

        try:
            for panels in to_deploy.values():
                sorted_panels = sorted(panels, key=lambda x: x["priority"])
                panelview = PanelView(self.bot, guild, self.config, sorted_panels)
                # Panels can change so we want to edit every time
                await panelview.start()
                self.view_cache[guild.id].append(panelview)
        except discord.NotFound:
            log.warning(f"Failed to refresh panels in {guild.name}")

        # Refresh view for logs of opened tickets (v1.8.18 update)
        for uid, opened_tickets in data["opened"].items():
            member = guild.get_member(int(uid))
            if not member:
                continue
            for ticket_channel_id, ticket_info in opened_tickets.items():
                ticket_channel = guild.get_channel_or_thread(int(ticket_channel_id))
                if not ticket_channel:
                    continue

                # v2.0.0 stores message id for close button to re-init views on reload
                if message_id := ticket_info.get("message_id"):
                    view = CloseView(self.bot, self.config, int(uid), ticket_channel)
                    self.bot.add_view(view, message_id=message_id)
                    self.view_cache[guild.id].append(view)

                if not ticket_info["logmsg"]:
                    continue

                panel_name = ticket_info["panel"]
                if panel_name not in all_panels:
                    continue
                panel = all_panels[panel_name]
                if not panel["log_channel"]:
                    continue
                log_channel = guild.get_channel(int(panel["log_channel"]))
                if not log_channel:
                    log.warning(f"Log channel no longer exits for {member.display_name}'s ticket in {guild.name}")
                    continue

                max_claims = ticket_info.get("max_claims", 0)
                logview = LogView(guild, ticket_channel, max_claims)
                self.bot.add_view(logview, message_id=ticket_info["logmsg"])
                self.view_cache[guild.id].append(logview)

    @tasks.loop(minutes=20)
    async def auto_close(self):
        actasks = []
        conf = await self.config.all_guilds()
        for gid, conf in conf.items():
            if not conf:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            inactive = conf["inactive"]
            if not inactive:
                continue
            opened = conf["opened"]
            if not opened:
                continue
            for uid, tickets in opened.items():
                member = guild.get_member(int(uid))
                if not member:
                    continue
                for channel_id, ticket in tickets.items():
                    has_response = ticket.get("has_response")
                    if has_response and channel_id not in self.valid:
                        self.valid.append(channel_id)
                        continue
                    if channel_id in self.valid:
                        continue
                    channel = guild.get_channel_or_thread(int(channel_id))
                    if not channel:
                        continue
                    now = datetime.datetime.now().astimezone()
                    opened_on = datetime.datetime.fromisoformat(ticket["opened"])
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
                            self.bot,
                            member,
                            guild,
                            channel,
                            conf,
                            _("(Auto-Close) Opened ticket with no response for ") + f"{inactive} {time}",
                            self.bot.user.name,
                            self.config,
                        )
                        log.info(
                            f"Ticket opened by {member.name} has been auto-closed.\n"
                            f"Has typed: {hastyped}\n"
                            f"Hours elapsed: {td}"
                        )
                    except Exception as e:
                        log.error(f"Failed to auto-close ticket for {member} in {guild.name}\nException: {e}")

        if tasks:
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
        guild = member.guild
        if not guild:
            return
        conf = await self.config.guild(guild).all()
        opened = conf["opened"]
        if str(member.id) not in opened:
            return
        tickets = opened[str(member.id)]
        if not tickets:
            return

        for cid in tickets:
            chan = guild.get_channel_or_thread(int(cid))
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
                    closedby=self.bot.user.display_name,
                    config=self.config,
                )
            except Exception as e:
                log.error(f"Failed to auto-close ticket for {member} leaving {member.guild}\nException: {e}")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if not thread:
            return
        guild = thread.guild
        conf = await self.config.guild(guild).all()
        pruned = await prune_invalid_tickets(guild, conf, self.config)
        if pruned:
            log.info("Pruned old ticket threads")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not channel:
            return
        guild = channel.guild
        conf = await self.config.guild(guild).all()
        pruned = await prune_invalid_tickets(guild, conf, self.config)
        if pruned:
            log.info("Pruned old ticket channels")
