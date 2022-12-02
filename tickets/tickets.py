import asyncio
import datetime
import logging

import discord
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.i18n import Translator, cog_i18n

from .base import BaseCommands
from .commands import TicketCommands
from .views import PanelView

log = logging.getLogger("red.vrt.tickets")
_ = Translator("Tickets", __file__)


# redgettext tickets.py base.py commands.py views.py --command-docstring
@cog_i18n(_)
class Tickets(BaseCommands, TicketCommands, commands.Cog):
    """
    Support ticket system with multi-panel functionality
    """
    __author__ = "Vertyco"
    __version__ = "1.1.10"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" \
               f"Cog Version: {self.__version__}\n" \
               f"Author: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_guild = {
            # Settings
            "support_roles": [],  # Role ids
            "blacklist": [],  # User ids
            "max_tickets": 1,  # Max amount of tickets a user can have open at a time of any kind
            "inactive": 0,  # Auto close tickets with X hours of inactivity (0 = disabled)
            # Ticket data
            "opened": {},  # All opened tickets
            "panels": {},  # All ticket panels
            # Toggles
            "dm": False,
            "user_can_rename": False,
            "user_can_close": True,
            "user_can_manage": False,
            "transcript": False
        }
        self.config.register_guild(**default_guild)

        self.ticket_panel_schema = {  # "panel_name" will be the key for the schema
            # Panel settings
            "category_id": 0,
            "channel_id": 0,
            "message_id": 0,
            "button_text": "Open a Ticket",
            "button_color": "blue",
            "button_emoji": None,  # either None or an emoji for the button
            # Ticket settings
            "ticket_num": 1,
            "ticket_messages": [],  # A list of messages to be sent
            "ticket_name": None,  # Name format for the ticket channel
            "log_channel": 0
        }

        self.valid = []  # Valid ticket channels

        self.auto_close.start()

    async def cog_load(self) -> None:
        asyncio.create_task(self.startup())

    async def cog_unload(self) -> None:
        self.auto_close.cancel()

    async def startup(self) -> None:
        await self.bot.wait_until_red_ready()
        await self.initialize()

    async def initialize(self, target_guild: discord.Guild = None) -> None:
        conf = await self.config.all_guilds()
        for gid, data in conf.items():
            if not data:
                continue
            if target_guild and target_guild.id != int(gid):
                continue
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            panels = data["panels"]
            to_deploy = {}  # Message ID keys for multi-button support
            for panel_name, panel in panels.items():
                catid = panel["category_id"]
                cid = panel["channel_id"]
                mid = panel["message_id"]
                if any([not catid, not cid, not mid]):
                    continue

                cat = guild.get_channel(catid)
                chan = guild.get_channel(cid)
                if any([not cat, not chan]):
                    continue

                try:
                    await chan.fetch_message(mid)
                except discord.NotFound:
                    continue

                panel["name"] = panel_name
                key = f"{cid}-{mid}"
                if key in to_deploy:
                    to_deploy[key].append(panel)
                else:
                    to_deploy[key] = [panel]

            if not to_deploy:
                continue

            for panels in to_deploy.values():
                panelview = PanelView(guild, self.config, panels)
                await panelview.start()

    # Clean up any ticket data that comes from a deleted channel or unknown user
    async def cleanup(self):
        for guild in self.bot.guilds:
            t = await self.config.guild(guild).opened()
            if not t:
                continue
            current_tickets = {}
            count = 0
            for uid, tickets in t.items():
                if not guild.get_member(int(uid)):
                    count += 1
                    continue
                new_tickets = {}
                for cid, data in tickets.items():
                    if not guild.get_channel(int(cid)):
                        count += 1
                        continue
                    else:
                        new_tickets[cid] = data
                if new_tickets:
                    current_tickets[uid] = new_tickets

            if current_tickets and count:
                await self.config.guild(guild).opened.set(current_tickets)
                log.info(f"{count} tickets pruned from {guild.name}")

    @tasks.loop(minutes=20)
    async def auto_close(self):
        actasks = []
        for guild in self.bot.guilds:
            conf = await self.config.guild(guild).all()
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
                for channel_id, data in tickets.items():
                    if channel_id in self.valid:
                        continue
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        continue
                    now = datetime.datetime.now()
                    opened_on = datetime.datetime.fromisoformat(data["opened"])
                    hastyped = await self.ticket_owner_hastyped(channel, member)
                    if hastyped:
                        if channel_id not in self.valid:
                            self.valid.append(channel_id)
                        continue
                    td = (now - opened_on).total_seconds() / 3600
                    if td < inactive:
                        continue
                    time = "hours" if inactive != 1 else "hour"
                    try:
                        await self.close_ticket(
                            member, channel, conf,
                            _("(Auto-Close) Opened ticket with no response for ") + f"{inactive} {time}",
                            self.bot.user.name
                        )
                        log.info(f"Ticket opened by {member.name} has been auto-closed.\n"
                                 f"Has typed: {hastyped}\n"
                                 f"Hours elapsed: {td}")
                    except Exception as e:
                        log.error(f"Failed to auto-close ticket for {member} in {guild.name}\nException: {e}")

        if tasks:
            await asyncio.gather(*actasks)
        await self.cleanup()

    @auto_close.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(30)

    # Will automatically close/cleanup any tickets if a member leaves that has an open ticket
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        conf = await self.config.guild(member.guild).all()
        opened = conf["opened"]
        if str(member.id) not in opened:
            return
        tickets = opened[str(member.id)]
        if not tickets:
            return

        for cid, ticket in tickets.items():
            chan = self.bot.get_channel(int(cid))
            if not chan:
                continue
            try:
                await self.close_ticket(
                    member, chan, conf, _("User left guild(Auto-Close)"), self.bot.user.display_name)
            except Exception as e:
                log.error(f"Failed to auto-close ticket for {member} leaving {member.guild}\nException: {e}")
