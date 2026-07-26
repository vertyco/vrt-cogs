import asyncio
import logging
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from io import BytesIO

import discord
from discord import ui
from discord.ext import tasks
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.api import PalApiError, PalClient, ServerUnreachable, Unauthorized
from ..common.graph import render_player_graph
from ..common.models import PalPlayer, ServerStatus
from ..common.utils import (
    chunk_lines,
    diff_snapshots,
    format_playtime,
    snapshot_from_players,
)
from ..db.tables import GuildSettings, Server
from ..db.utils import (
    close_open_sessions,
    close_session,
    get_create_guild_settings,
    mark_servers_online,
    open_session,
    player_count_series,
    touch_players,
    upsert_player,
    upsert_player_ip,
)

log = logging.getLogger("red.vrt.paltools.tasks.playerpoll")
_ = Translator("PalTools", __file__)

# A LayoutView rejects more than 4000 display characters, with a little left for markdown padding
MAX_VIEW_CHARS = 3900
# A single TextDisplay is capped at 4000 too, so server lines are split well below that
TEXT_ITEM_CHARS = 1500
# Rough allowance for the header, footer and overflow notice around the server lines
PANEL_CHROME = 300
# How far back the panel graph looks, how finely it samples, and how often it is re-rendered
GRAPH_SPAN = timedelta(hours=12)
GRAPH_STEP = timedelta(minutes=5)
GRAPH_INTERVAL = timedelta(minutes=10)
# Discord's message content limit, which the batched join log lines are packed against
MAX_MESSAGE_CHARS = 2000


class PlayerPoll(MixinMeta):
    @tasks.loop(seconds=30)
    async def player_poll(self):
        # tasks.loop awaits the body, so ticks never overlap by construction.
        # It also stops the loop for good on any exception it does not recognize, so a single
        # database hiccup here would silently end join/leave logging until the cog is reloaded.
        try:
            # connect() holds the same lock: a reconnect swaps the engine and clears the caches,
            # and a tick interleaving with that would repopulate them against the wrong database
            async with self.init_lock:
                await self.poll_once()
        except Exception as e:
            log.error("Poll tick failed", exc_info=e)

    async def poll_once(self) -> None:
        if not self.db:
            return
        servers = await Server.objects().where(Server.enabled == True)  # noqa: E712
        await self.purge_stale_servers(servers)
        settings = await self.tick_settings(servers)
        results = await asyncio.gather(
            *[self.poll_server(s, settings[s.guild_id]) for s in servers], return_exceptions=True
        )
        statuses: dict[int, list[ServerStatus]] = defaultdict(list)
        reachable = []
        for server, res in zip(servers, results, strict=True):
            if isinstance(res, BaseException):
                log.error("Unhandled poll error for server %s", server.name, exc_info=res)
                continue
            statuses[server.guild_id].append(res)
            if res.online:
                reachable.append(server.id)
        # One bulk write per tick rather than a save() per server
        await mark_servers_online(reachable, datetime.now(timezone.utc))
        # Concurrently: each panel edit is a Discord round trip in its own ratelimit bucket,
        # and doing them one at a time would stretch the tick by that latency per guild
        panel_results = await asyncio.gather(
            *(self.update_status_panel(conf, statuses[guild_id]) for guild_id, conf in settings.items()),
            return_exceptions=True,
        )
        for res in panel_results:
            if isinstance(res, BaseException):
                log.error("Status panel update failed", exc_info=res)

    async def purge_stale_servers(self, servers: list[Server]) -> None:
        """Sweep cached state and open sessions of servers no longer polled.

        Disabling or removing a server can interleave with a tick already mid-poll on it: the
        button closes the sessions and pops the caches, then the in-flight tick re-opens and
        re-adds them. Nothing would ever touch that server again, so the leftovers are swept
        here, with the tick's own server list, before every poll.
        """
        enabled = {server.id for server in servers}
        for sid in (set(self.snapshots) | set(self.servers_online)) - enabled:
            closed = await close_open_sessions(sid)
            if closed:
                log.warning("Closed %s stale sessions on disabled/removed server %s", closed, sid)
            self.snapshots.pop(sid, None)
            self.servers_online.pop(sid, None)

    @staticmethod
    async def tick_settings(servers: list[Server]) -> dict[int, GuildSettings]:
        """One settings row per guild polled this tick, plus any guild running a status panel.

        The panel guilds are fetched even with no enabled servers left, otherwise the panel of a
        guild whose last server was disabled would sit there forever showing a roster from then.
        """
        guild_ids = {server.guild_id for server in servers}
        where = GuildSettings.status_channel_id.is_not_null()
        if guild_ids:
            # One query for every guild this tick touches, not a get_or_create per guild per tick
            where = where | GuildSettings.guild_id.is_in(list(guild_ids))
        settings = {conf.guild_id: conf for conf in await GuildSettings.objects().where(where)}
        for guild_id in guild_ids - settings.keys():
            settings[guild_id] = await get_create_guild_settings(guild_id)
        return settings

    @player_poll.before_loop
    async def before_player_poll(self):
        await self.bot.wait_until_red_ready()

    async def poll_server(self, server: Server, settings: GuildSettings) -> ServerStatus:
        client = PalClient(server.host, server.port, server.admin_password)
        try:
            players = await client.players()
        except Unauthorized as e:
            # A wrong AdminPassword is a configuration fault, not an outage. Reported as one it
            # would look identical to a dead box and nobody would think to check the credentials.
            log.error("Poll rejected by %s: %s", server.name, e)
            await self.set_reachability(server, settings, online=False, reason=_("the AdminPassword is wrong"))
            return ServerStatus(name=server.name, online=False, last_online=server.last_online)
        except ServerUnreachable:
            await self.set_reachability(server, settings, online=False)
            return ServerStatus(name=server.name, online=False, last_online=server.last_online)
        except PalApiError as e:
            log.warning("Poll failed for %s: %s", server.name, e)
            await self.set_reachability(server, settings, online=False)
            return ServerStatus(name=server.name, online=False, last_online=server.last_online)
        await self.set_reachability(server, settings, online=True)

        status = ServerStatus(name=server.name, online=True, players=[p for p in players if not p.is_placeholder])
        if settings.status_channel_id:
            # A second request per server per tick for the panel's "9/32", so only guilds
            # actually running a panel pay for it
            try:
                status.max_players = (await client.metrics()).maxplayernum
            except PalApiError as e:
                log.debug("Metrics failed for %s: %s", server.name, e)
        await self.track_players(server, settings, players)
        return status

    async def track_players(self, server: Server, settings: GuildSettings, players: list[PalPlayer]) -> None:
        sid = server.id
        now = datetime.now(timezone.utc)
        current = snapshot_from_players(players)
        prev = self.snapshots.get(sid)

        channel = self.bot.get_channel(settings.log_channel_id) if settings.log_channel_id else None

        if prev is None:
            # Silent baseline after (re)load: record everyone, no embeds
            for pal in current.values():
                player = await upsert_player(server.guild_id, pal, now)
                await upsert_player_ip(player, pal.ip, now)
                await open_session(player, server.id, now)
            self.snapshots[sid] = current
            return

        joined, left = diff_snapshots(prev, current)
        # Leaves before joins: a same-tick relog (same userId, new playerId) resolves to one
        # player row, and the join processed first would keep the old session open only for the
        # leave to close it, stranding an online player with no open session
        lines: list[str] = []
        for pal in left:
            player = await upsert_player(server.guild_id, pal, now)
            seconds = await close_session(player, server.id, now)
            lines.append(self.leave_line(server, pal, seconds))
        for pal in joined:
            player = await upsert_player(server.guild_id, pal, now)
            await upsert_player_ip(player, pal.ip, now)
            await open_session(player, server.id, now)
            lines.append(self.join_line(server, pal))
        # One send for the whole tick: a restart lands a dozen joins at once, and a message each
        # would be a dozen round trips and an unreadable channel
        await self.send_log(channel, server.guild_id, lines)

        # Everyone who stayed: full upsert only when a persisted field actually moved,
        # otherwise a single bulk last_seen bump instead of a read+write per player per tick.
        joined_ids = {pal.player_id for pal in joined}
        unchanged = []
        for pid, pal in current.items():
            if pid in joined_ids:
                continue
            before = prev.get(pid)
            if before and self.persisted_fields(before) == self.persisted_fields(pal):
                unchanged.append(pal)
            else:
                await upsert_player(server.guild_id, pal, now)
        await touch_players(server.guild_id, unchanged, now)
        # Advanced last, not before the writes: a failure above must leave the old baseline in
        # place so the next tick retries the diff, rather than silently dropping these joins
        self.snapshots[sid] = current

    @staticmethod
    def persisted_fields(pal: PalPlayer) -> tuple:
        return (pal.name, pal.account_name, pal.level, pal.building_count)

    async def update_status_panel(self, settings: GuildSettings, statuses: list[ServerStatus]) -> None:
        """Keep one message in the status channel current, editing it in place rather than reposting"""
        if not settings.status_channel_id:
            return
        channel = self.bot.get_channel(settings.status_channel_id)
        if channel is None:
            return
        filename, png, is_new = await self.panel_graph(settings.guild_id, settings.timezone)
        view = self.status_view(statuses, filename)
        message = self.status_messages.get(settings.guild_id)
        if message is not None and message.channel.id != settings.status_channel_id:
            # The panel was moved by [p]paltools statuschannel while a tick was in flight: the
            # cached message lives in the old channel and editing it would keep the panel there
            # forever. Delete the stray and fall through to posting in the right channel.
            self.status_messages.pop(settings.guild_id, None)
            with suppress(discord.HTTPException):
                await message.delete()
            message = None
        if message is None and settings.status_message_id:
            message = await self.fetch_status_message(channel, settings.status_message_id)
        if message is not None:
            if filename is None:
                # No graph in this view, so drop the old one rather than leaving an attachment
                # that no component references
                attachments = []
            elif is_new or not any(a.filename == filename for a in message.attachments):
                # Re-rendered, or a failed edit left the cached filename ahead of what is actually
                # attached: upload the cached PNG rather than referencing a file Discord lacks
                attachments = [discord.File(BytesIO(png), filename)]
            else:
                # Re-uploading the graph on every tick would push the same PNG every 30 seconds,
                # so the existing attachment is handed back untouched until a fresh one is rendered
                attachments = list(message.attachments)
            try:
                # Message.edit is not in place, it returns the new message. Caching the old object
                # would leave message.attachments frozen at the PNG the last render replaced.
                self.status_messages[settings.guild_id] = await message.edit(view=view, attachments=attachments)
                return
            except discord.NotFound:
                self.status_messages.pop(settings.guild_id, None)  # deleted by hand, post a fresh one
            except discord.HTTPException as e:
                log.warning("Failed to edit the status panel in guild %s", settings.guild_id, exc_info=e)
                return
        # Posting is rare, so re-read the row first: this tick's settings can be seconds stale,
        # and posting against a channel the admin just changed or cleared would strand a live
        # panel there with nothing left pointing at it
        current = await GuildSettings.objects().get(GuildSettings.guild_id == settings.guild_id)
        if current is None or current.status_channel_id != settings.status_channel_id:
            return
        try:
            file = discord.File(BytesIO(png), filename) if png else None
            message = await channel.send(view=view, file=file) if file else await channel.send(view=view)
        except discord.HTTPException as e:
            log.warning("Failed to post the status panel in guild %s", settings.guild_id, exc_info=e)
            return
        self.status_messages[settings.guild_id] = message
        settings.status_message_id = message.id
        # Only this column: the row was read at the top of the tick, and a blanket save would
        # revert any settings command an admin ran while the tick was in flight
        await settings.save(columns=[GuildSettings.status_message_id])

    async def panel_graph(self, guild_id: int, tz: str = "UTC") -> tuple[str | None, bytes | None, bool]:
        """Cached (filename, png, is_new) for the panel graph.

        Rendering is far too expensive for a 30 second tick, so it happens on its own interval
        and every tick in between reuses the PNG already attached to the message.
        """
        now = datetime.now(timezone.utc)
        cached = self.status_graphs.get(guild_id)
        if cached and now - cached[0] < GRAPH_INTERVAL:
            return cached[1], cached[2], False
        filename, png = None, None
        try:
            rows = await player_count_series(guild_id, now - GRAPH_SPAN, now, GRAPH_STEP)
            if rows:
                png = await asyncio.to_thread(render_player_graph, rows, int(GRAPH_SPAN.total_seconds() // 3600), tz)
                # Discord caches attachment URLs, so a new render needs a name it has not seen
                filename = f"players_{int(now.timestamp())}.png"
        except Exception as e:
            log.error("Failed to render the status graph for guild %s", guild_id, exc_info=e)
            if cached:
                # Hold onto the last good render instead of caching the failure as a result,
                # which would blank the graph for a whole interval over one transient error
                self.status_graphs[guild_id] = (now, cached[1], cached[2])
                return cached[1], cached[2], False
            # No prior render to fall back on: leave the cache empty so the next tick retries
            # instead of pinning a graphless panel for a whole interval
            return None, None, False
        self.status_graphs[guild_id] = (now, filename, png)
        return filename, png, png is not None

    @staticmethod
    async def fetch_status_message(channel: discord.abc.Messageable, message_id: int) -> discord.Message | None:
        # Only NotFound means "post a fresh panel". Anything else (429, 5xx, missing history
        # permission) must propagate and skip the tick, or every transient fetch hiccup after a
        # reload would post a duplicate panel and orphan the old one.
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound as e:
            log.debug("Status panel message %s is gone: %s", message_id, e)
            return None

    @classmethod
    def status_view(cls, statuses: list[ServerStatus], graph_filename: str | None = None) -> ui.LayoutView:
        online = [status for status in statuses if status.online]
        header = f"## {_('PalWorld Server Status')}\n"
        if statuses:
            header += _("Total Players: **{}**").format(sum(len(status.players) for status in online))
        else:
            header += _("-# No enabled servers configured")

        container = ui.Container(accent_color=discord.Color.green() if online else discord.Color.red())
        container.add_item(ui.TextDisplay(header))
        if statuses:
            container.add_item(ui.Separator())
            for block in cls.server_blocks(statuses):
                container.add_item(ui.TextDisplay(block))
        if graph_filename:
            container.add_item(ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{graph_filename}")))
        container.add_item(ui.Separator())
        # A relative stamp rather than a fixed time: the client counts it up between poll ticks,
        # so a panel that has stopped refreshing is obvious at a glance
        container.add_item(
            ui.TextDisplay(_("-# Last Updated {}").format(discord.utils.format_dt(datetime.now(timezone.utc), "R")))
        )
        view = ui.LayoutView(timeout=None)
        view.add_item(container)
        return view

    @classmethod
    def server_blocks(cls, statuses: list[ServerStatus]) -> list[str]:
        """Server lines split into text items that fit the view budget.

        One line per server rather than per player, so the panel is bounded by how many servers
        exist instead of how many people are on them. That is the whole point: a roster would
        start dropping names exactly when the panel matters most.
        """
        shown = sorted(statuses, key=lambda status: status.name)
        width = max(len(status.name) for status in shown)
        lines = [cls.server_line(status, width) for status in shown]
        budget = MAX_VIEW_CHARS - PANEL_CHROME
        blocks: list[str] = []
        current: list[str] = []
        current_len = 0  # what "\n".join(current) would cost
        used = 0  # every line accepted so far, whether or not its block has been flushed
        for index, line in enumerate(lines):
            cost = len(line) + 1
            if used + cost > budget:
                # Checked against the running total, not just the block being filled, so the
                # panel cannot walk past the view budget one full text item at a time
                if current:
                    blocks.append("\n".join(current))
                blocks.append(_("-# {} more servers do not fit in one message").format(len(lines) - index))
                log.warning("Status panel in a guild with %s servers hit the Discord size limit", len(lines))
                return blocks
            if current_len + cost > TEXT_ITEM_CHARS:
                blocks.append("\n".join(current))
                current, current_len = [], 0
            current.append(line)
            current_len += cost
            used += cost
        if current:
            blocks.append("\n".join(current))
        return blocks

    @staticmethod
    def server_line(status: ServerStatus, width: int) -> str:
        label = f"`{status.name}:{' ' * (width - len(status.name))}`"
        if not status.online:
            if status.last_online:
                return f"{label} " + _("Offline {}").format(discord.utils.format_dt(status.last_online, "R"))
            return f"{label} " + _("Offline")
        count = f"**{len(status.players)}**"
        return f"{label} {count}/{status.max_players}" if status.max_players else f"{label} {count}"

    async def set_reachability(
        self, server: Server, settings: GuildSettings, online: bool, reason: str | None = None
    ) -> None:
        sid = server.id
        previous = self.servers_online.get(sid)
        if previous is None or previous == online:
            self.servers_online[sid] = online
            return
        if not online:
            self.snapshots.pop(sid, None)  # force a silent baseline on recovery, no fake join spam
            # Close the sessions now, otherwise playtime keeps accruing for the whole outage.
            # The transition is recorded only after this succeeds: a raise here leaves the old
            # state in place so the next tick retries the close instead of losing it for good.
            closed = await close_open_sessions(server.id)
            log.warning("Server %s is unreachable, closed %s open sessions", server.name, closed)
        else:
            log.info("Server %s is back online", server.name)
        self.servers_online[sid] = online
        channel = self.bot.get_channel(settings.log_channel_id) if settings.log_channel_id else None
        if channel is None:
            return
        if online:
            line = ":full_moon: " + _("**{}** came online").format(server.name)
        elif reason is None:
            line = ":new_moon: " + _("**{}** went offline").format(server.name)
        else:
            line = ":new_moon: " + _("**{}** went offline: {}").format(server.name, reason)
        await self.send_log(channel, server.guild_id, [line])

    @classmethod
    def join_line(cls, server: Server, pal: PalPlayer) -> str:
        return ":green_circle: " + _("`{}` joined **{}** (Lvl {}, {:.0f}ms)").format(
            cls.identity(pal), server.name, pal.level, pal.ping
        )

    @classmethod
    def leave_line(cls, server: Server, pal: PalPlayer, seconds: int) -> str:
        line = ":red_circle: " + _("`{}` left **{}**").format(cls.identity(pal), server.name)
        # No open session to close means no playtime worth quoting, rather than a "<1m" that
        # reads like the player really was on for seconds
        return f"{line} ({format_playtime(seconds)})" if seconds else line

    @staticmethod
    def identity(pal: PalPlayer) -> str:
        # Backticks are the one character a player can put in their name that breaks out of the
        # code span, and the account name is not fully under their control but is not guaranteed
        # clean either
        parts = [pal.name, pal.account_name or _("Unknown"), pal.user_id]
        return ", ".join(part.replace("`", "") for part in parts)

    @staticmethod
    async def send_log(channel: discord.abc.Messageable | None, guild_id: int, lines: list[str]) -> None:
        if channel is None or not lines:
            return
        for block in chunk_lines(lines, MAX_MESSAGE_CHARS):
            try:
                # Player names reach this as message content rather than embed text, so an
                # everyone/here/role mention in one would ping the whole server
                await channel.send(block, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException as e:
                log.warning("Failed to send %s log lines in guild %s", len(lines), guild_id, exc_info=e)
                return
