import asyncio
import json
import logging
import typing as t
from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from pydantic import ValidationError
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.views import ConfirmView

from ..abc import MixinMeta
from ..common.api import PalApiError, PalClient, ServerUnreachable, Unauthorized
from ..common.backup import decode, dump_guild, encode, restore_guild
from ..common.utils import format_playtime
from ..db.tables import GuildSettings, Server, ensure_db_connection
from ..db.utils import (
    find_players,
    get_create_guild_settings,
    get_target_servers,
    player_ips,
    player_playtime,
    shared_ip_players,
)
from ..views.postgres_creds import SetConnectionView
from ..views.server_manager import ServerManagerView

log = logging.getLogger("red.vrt.paltools.commands.admin")
_ = Translator("PalTools", __file__)

# The /settings payload runs to well over a hundred fields, so the embed carries the ones staff
# actually ask about and the rest ships as the attached JSON
SETTING_HIGHLIGHTS = (
    ("Difficulty", "Difficulty"),
    ("ServerPlayerMaxNum", "Max Players"),
    ("ExpRate", "EXP Rate"),
    ("PalCaptureRate", "Capture Rate"),
    ("CollectionDropRate", "Gather Rate"),
    ("EnemyDropItemRate", "Drop Rate"),
    ("WorkSpeedRate", "Work Speed"),
    ("DayTimeSpeedRate", "Day Speed"),
    ("NightTimeSpeedRate", "Night Speed"),
    ("DeathPenalty", "Death Penalty"),
    ("bIsPvP", "PvP"),
    ("bEnableFriendlyFire", "Friendly Fire"),
    ("bHardcore", "Hardcore"),
    ("bPalLost", "Pals Lost on Death"),
    ("BaseCampMaxNum", "Max Base Camps"),
    ("GuildPlayerMaxNum", "Max Guild Size"),
)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(name="paltools")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def paltools(self, ctx: commands.Context):
        """Manage PalWorld servers"""
        pass

    @paltools.command(name="postgres")
    @commands.is_owner()
    async def paltools_postgres(self, ctx: commands.Context):
        """Set the Postgres connection info"""
        await SetConnectionView(self, ctx).start()

    @paltools.command(name="servers")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_servers(self, ctx: commands.Context):
        """Open the interactive server manager (add/edit/remove/test servers)"""
        await ServerManagerView(self, ctx).start()

    @paltools.command(name="logchannel")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_logchannel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Set (or clear) the join/leave log channel"""
        settings = await get_create_guild_settings(ctx.guild.id)
        settings.log_channel_id = channel.id if channel else None
        # Only this column: a blanket save would write back a status_message_id read moments
        # ago, clobbering the one the poll tick may have just stored
        await settings.save(columns=[GuildSettings.log_channel_id])
        if channel:
            await ctx.send(_("Log channel set to {}").format(channel.mention))
        else:
            await ctx.send(_("Log channel cleared"))

    @paltools.command(name="statuschannel")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_statuschannel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Set (or clear) the channel holding the live status panel

        The panel is a single message listing every enabled server with its player count and a
        12 hour player graph, edited in place on every poll tick.
        """
        settings = await get_create_guild_settings(ctx.guild.id)
        old_channel = self.bot.get_channel(settings.status_channel_id) if settings.status_channel_id else None
        old_message_id = settings.status_message_id
        settings.status_channel_id = channel.id if channel else None
        settings.status_message_id = None  # the old panel belongs to the old channel
        await settings.save(columns=[GuildSettings.status_channel_id, GuildSettings.status_message_id])
        self.status_messages.pop(ctx.guild.id, None)
        if old_channel is not None and old_message_id:
            # Otherwise the abandoned panel sits there frozen, still looking live. Logged rather
            # than suppressed: missing Manage Messages is exactly the case worth knowing about.
            try:
                await (await old_channel.fetch_message(old_message_id)).delete()
            except discord.HTTPException as e:
                log.warning("Could not remove the old status panel in channel %s", old_channel.id, exc_info=e)
        if channel:
            await ctx.send(_("Status panel moved to {}, it appears on the next poll").format(channel.mention))
        else:
            await ctx.send(_("Status panel disabled"))

    @paltools.command(name="logips")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_logips(self, ctx: commands.Context):
        """Toggle player IP history in `findplayer` (staff-only, in a staff-only channel)

        Addresses are recorded either way. The join log never shows them.
        """
        settings = await get_create_guild_settings(ctx.guild.id)
        settings.log_ips = not settings.log_ips
        await settings.save(columns=[GuildSettings.log_ips])
        state = _("enabled") if settings.log_ips else _("disabled")
        await ctx.send(_("IP display in `findplayer` is now {}").format(state))

    @paltools.command(name="timezone")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_timezone(self, ctx: commands.Context, timezone_name: str | None = None):
        """Set the timezone the status panel graph is labelled in, or show the current one

        Takes an IANA name such as `America/New_York`, `Europe/London` or `UTC`.
        """
        settings = await get_create_guild_settings(ctx.guild.id)
        if timezone_name is None:
            now = datetime.now(ZoneInfo(settings.timezone)) if settings.timezone else datetime.now(timezone.utc)
            return await ctx.send(
                _("Graph timezone is `{}` (currently {}). Set another with `{}paltools timezone <name>`").format(
                    settings.timezone, now.strftime("%I:%M %p %Z"), ctx.clean_prefix
                )
            )
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return await ctx.send(
                _("`{}` is not a known timezone. Use an IANA name like `America/New_York`.").format(timezone_name[:100])
            )
        settings.timezone = timezone_name
        await settings.save(columns=[GuildSettings.timezone])
        # The rendered PNG is cached for ten minutes, so the change would not show up until it
        # expired on its own
        self.status_graphs.pop(ctx.guild.id, None)
        await ctx.send(_("Status panel graph timezone set to `{}`").format(timezone_name))

    @paltools.command(name="backup")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_backup(self, ctx: commands.Context):
        """DM a backup of this server's PalTools data (settings, servers, players, sessions)

        Restore it onto another bot with `[p]paltools restore`.
        """
        async with ctx.typing():
            backup = await dump_guild(ctx.guild.id)
            payload, extension = encode(backup)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        file = discord.File(BytesIO(payload), f"paltools-{ctx.guild.id}-{stamp}{extension}")
        counts = ", ".join(f"{count} {label}" for label, count in backup.counts().items())
        # By DM, never in the channel: the dump carries every server's AdminPassword in plaintext
        warning = _(
            "PalTools backup for **{}**\n{}\n\n"
            "This file contains your servers' AdminPasswords in plain text. Do not share it."
        ).format(ctx.guild.name, counts)
        try:
            await ctx.author.send(warning, file=file)
        except discord.HTTPException as e:
            log.warning("Could not DM the backup to %s", ctx.author.id, exc_info=e)
            return await ctx.send(
                _("I could not DM you the backup. Enable DMs from this server and try again.")
                + _(" It is not posted here because it contains your AdminPasswords.")
            )
        await ctx.send(_("Backup sent to your DMs ({})").format(counts))

    @paltools.command(name="restore")
    @commands.is_owner()
    @ensure_db_connection()
    async def paltools_restore(self, ctx: commands.Context):
        """Restore a backup file onto this server, replacing all of its PalTools data

        Attach the file from `[p]paltools backup` (or reply to the message holding it).
        """
        attachment = self.find_attachment(ctx)
        if attachment is None:
            return await ctx.send(_("Attach a backup file to your message, or reply to the message holding it"))
        try:
            backup = decode(await attachment.read())
        except ValidationError as e:
            log.warning("Rejected a malformed PalTools backup", exc_info=e)
            return await ctx.send(_("That file is not a valid PalTools backup:") + box(str(e)[:1800]))
        except Exception as e:
            log.warning("Could not read the attached backup", exc_info=e)
            return await ctx.send(_("Could not read that file: {}").format(e))

        counts = ", ".join(f"{count} {label}" for label, count in backup.counts().items())
        text = _("Replace **all** PalTools data for this server with this backup?\n\nIt contains {}.").format(counts)
        if backup.guild_id != ctx.guild.id:
            # Channel ids are only meaningful in the guild they came from, so restore_settings
            # drops them; said up front rather than discovered afterwards
            text += _("\n\nIt was taken on a different server, so the log and status channels will not be restored.")
        text += _("\n\nEverything currently stored for this server is deleted first. This cannot be undone.")
        view = ConfirmView(ctx.author, timeout=60)
        view.confirm_button.style = discord.ButtonStyle.danger
        view.message = await ctx.send(text, view=view)
        await view.wait()
        if not view.result:
            return await view.message.edit(content=_("Restore cancelled"), view=None)

        try:
            # The same lock the poll loop holds: a tick interleaving with the wipe would write
            # rows against server ids that no longer exist, and re-cache them afterwards
            async with self.init_lock:
                restored = await restore_guild(backup, ctx.guild.id)
                # Every cache is keyed by row id and the restore reissued all of them, so the
                # cog re-baselines from scratch rather than resolving stale ids to new rows
                self.snapshots.clear()
                self.servers_online.clear()
                self.status_messages.clear()
                self.status_graphs.clear()
        except Exception as e:
            log.error("Restore failed for guild %s", ctx.guild.id, exc_info=e)
            return await view.message.edit(content=_("Restore failed, nothing was changed: {}").format(e), view=None)
        summary = ", ".join(f"{count} {label}" for label, count in restored.items())
        await view.message.edit(content=_("Restored {}").format(summary), view=None)

    @staticmethod
    def find_attachment(ctx: commands.Context) -> discord.Attachment | None:
        if ctx.message.attachments:
            return ctx.message.attachments[0]
        # Replying with the file is how staff will hand a backup around in practice
        reference = ctx.message.reference
        if reference and isinstance(reference.resolved, discord.Message) and reference.resolved.attachments:
            return reference.resolved.attachments[0]
        return None

    @paltools.command(name="findplayer")
    @ensure_db_connection()
    async def paltools_findplayer(self, ctx: commands.Context, *, query: str):
        """Look up a player: identity, name/IP history, playtime, shared-IP overlaps"""
        players = await find_players(ctx.guild.id, query)
        if not players:
            return await ctx.send(_("No players found matching `{}`").format(query))
        if len(players) > 1:
            names = "\n".join(f"- {p.name} (`{p.user_id}`)" for p in players)
            return await ctx.send(_("Multiple matches, narrow it down:\n{}").format(names))
        player = players[0]
        settings = await get_create_guild_settings(ctx.guild.id)
        show_ips = await self.can_show_ips(ctx, settings)
        playtime = await player_playtime(player)
        # Not queried at all when they cannot be shown, rather than fetched and dropped
        shared = await shared_ip_players(player) if show_ips else []
        ips = await player_ips(player) if show_ips else []
        embed = discord.Embed(title=player.name, color=discord.Color.blurple())
        embed.add_field(name=_("User ID"), value=f"`{player.user_id}`", inline=False)
        embed.add_field(name=_("Account"), value=player.account_name or _("Unknown"))
        embed.add_field(name=_("Level"), value=str(player.level))
        embed.add_field(name=_("Buildings"), value=str(player.building_count))
        embed.add_field(name=_("First seen"), value=discord.utils.format_dt(player.first_seen, "R"))
        embed.add_field(name=_("Last seen"), value=discord.utils.format_dt(player.last_seen, "R"))
        embed.add_field(name=_("Playtime"), value=format_playtime(sum(playtime.values())))
        if player.name_history and len(player.name_history) > 1:
            embed.add_field(name=_("Name history"), value=", ".join(player.name_history[-10:])[:1024], inline=False)
        if ips:
            embed.add_field(name=_("IP history"), value="\n".join(f"`{r.ip}`" for r in ips[:10])[:1024], inline=False)
        if shared:
            embed.add_field(name=_("Shares IP with"), value=", ".join(shared[:10])[:1024], inline=False)
        if settings.log_ips and not show_ips:
            # Otherwise a mod in a public channel just sees a dossier with no IP section and
            # assumes nothing was recorded
            embed.set_footer(text=_("IP history hidden: mods only, and only in a staff-only channel"))
        await ctx.send(embed=embed)

    async def can_show_ips(self, ctx: commands.Context, settings: GuildSettings) -> bool:
        """IP history needs all three: the owner's switch, a mod, and a non-public channel.

        Any one alone leaks addresses. logips is a guild wide switch, the command is open to
        anyone with Manage Server, and a channel the default role can read publishes the reply
        to everyone regardless of who ran it.
        """
        if not settings.log_ips:
            return False
        author = ctx.author
        staff = await self.bot.is_mod(author) or author.id == ctx.guild.owner_id or await self.bot.is_owner(author)
        if not staff:
            return False
        # The default role, not the invoker: what matters is who can read the answer, and a
        # channel @everyone can see puts the addresses in front of the whole server
        return not ctx.channel.permissions_for(ctx.guild.default_role).read_messages

    @paltools.command(name="kick")
    @ensure_db_connection()
    async def paltools_kick(self, ctx: commands.Context, target: str, *, reason: str = ""):
        """Kick a player by name or userId (fans out to all enabled servers)"""
        await self.moderate(ctx, "kick", target, reason)

    @paltools.command(name="ban")
    @ensure_db_connection()
    async def paltools_ban(self, ctx: commands.Context, target: str, *, reason: str = ""):
        """Ban a player by name or userId (player may need to be online)"""
        await self.moderate(ctx, "ban", target, reason)

    @paltools.command(name="unban")
    @ensure_db_connection()
    async def paltools_unban(self, ctx: commands.Context, target: str):
        """Unban a player by name or userId (quote names containing spaces)"""
        # Positional like kick/ban, not consume-rest: consume-rest keeps the literal quote
        # characters, so the quoting the help text tells staff to use would break the lookup
        await self.moderate(ctx, "unban", target)

    @staticmethod
    async def fanout(servers: list[Server], call: t.Callable[[PalClient], t.Awaitable]) -> list[str]:
        """Run `call(client)` against every server at once, one status line per server.

        Sequentially this costs the request timeout per unreachable server, so a fleet with a few
        boxes down would keep the invoker waiting a minute or more for a reply.
        """

        async def run(server: Server) -> str:
            client = PalClient(server.host, server.port, server.admin_password)
            try:
                await call(client)
            except Unauthorized:
                return f"❌ {server.name}: " + _("wrong AdminPassword")
            except ServerUnreachable:
                return f"❌ {server.name}: " + _("unreachable: check host/port, RESTAPIEnabled=True, and firewall")
            except PalApiError as e:
                log.warning("Request failed on %s", server.name, exc_info=e)
                return f"❌ {server.name}: {e}"
            return f"✅ {server.name}"

        return await asyncio.gather(*(run(server) for server in servers))

    @staticmethod
    async def send_fanout(ctx: commands.Context, header: str, lines: list[str]) -> None:
        """One status line per server overruns 2000 characters on a real fleet, so it is paged"""
        for page in pagify(f"{header}\n" + "\n".join(lines), delims=["\n"]):
            await ctx.send(page)

    async def moderate(self, ctx: commands.Context, action: str, target: str, reason: str = "") -> None:
        players = await find_players(ctx.guild.id, target)
        if not players:
            # No match in our records: treat the query itself as a literal userId,
            # since the REST API accepts a raw userId directly.
            userid = target
            player_name = target
        elif len(players) > 1:
            names = "\n".join(f"- {p.name} (`{p.user_id}`)" for p in players)
            await ctx.send(_("Multiple matches, use the userId:\n{}").format(names))
            return
        else:
            userid = players[0].user_id
            player_name = players[0].name
        servers = await get_target_servers(ctx.guild.id)
        if not servers:
            await ctx.send(_("No enabled servers configured"))
            return
        args = (userid, reason) if action in ("kick", "ban") and reason else (userid,)
        lines = await self.fanout(servers, lambda client: getattr(client, action)(*args))
        await self.send_fanout(ctx, _("{} `{}` ({}):").format(action.title(), player_name, userid), lines)

    @paltools.command(name="announce")
    @ensure_db_connection()
    async def paltools_announce(self, ctx: commands.Context, *, message: str):
        """Broadcast a message to all enabled servers"""
        servers = await get_target_servers(ctx.guild.id)
        if not servers:
            return await ctx.send(_("No enabled servers configured"))
        lines = await self.fanout(servers, lambda client: client.announce(message))
        await self.send_fanout(ctx, _("Announcement sent:"), lines)

    @paltools.command(name="save")
    @ensure_db_connection()
    async def paltools_save(self, ctx: commands.Context, server_name: str | None = None):
        """Save world on all enabled servers, or one by name"""
        servers = await get_target_servers(ctx.guild.id, server_name)
        if not servers:
            return await ctx.send(_("No matching enabled servers"))
        lines = await self.fanout(servers, lambda client: client.save())
        await self.send_fanout(ctx, _("Save requested:"), lines)

    @paltools.command(name="settings")
    @ensure_db_connection()
    async def paltools_settings(self, ctx: commands.Context, server_name: str | None = None):
        """Show a server's live PalWorld settings, with the full set attached as JSON

        The server name is optional while only one is configured.
        """
        servers = await get_target_servers(ctx.guild.id, server_name)
        if not servers:
            return await ctx.send(_("No matching enabled servers"))
        if len(servers) > 1:
            # Never guess: a 117 field dump per server would be several messages of noise
            names = ", ".join(server.name for server in servers)
            return await ctx.send(_("Name a server, this matches more than one: {}").format(names))
        server = servers[0]
        client = PalClient(server.host, server.port, server.admin_password)
        try:
            data = await client.settings()
        except Unauthorized:
            return await ctx.send(_("❌ {}: wrong AdminPassword").format(server.name))
        except ServerUnreachable:
            return await ctx.send(
                _("❌ {}: unreachable: check host/port, RESTAPIEnabled=True, and firewall").format(server.name)
            )
        except PalApiError as e:
            log.warning("Settings fetch failed on %s", server.name, exc_info=e)
            return await ctx.send(_("❌ {}: {}").format(server.name, e))

        embed = discord.Embed(
            title=data.get("ServerName") or server.name,
            description=data.get("ServerDescription") or None,
            color=discord.Color.blurple(),
        )
        # Rendered even when absent: silently dropping a field looks identical to the server
        # simply not having it, and nobody would think to go looking in the attachment
        missing = [key for key, _label in SETTING_HIGHLIGHTS if key not in data]
        for key, label in SETTING_HIGHLIGHTS:
            value = self.format_setting(data[key]) if key in data else _("not reported")
            embed.add_field(name=_(label), value=value)
        footer = _("{} settings in the attached file").format(len(data))
        if missing:
            # Worth knowing about: a renamed or dropped key means this list needs updating
            log.warning("Server %s did not report settings keys: %s", server.name, ", ".join(missing))
            footer += _(" | {} not reported by this server").format(len(missing))
        embed.set_footer(text=footer)
        # The server name reaches the filesystem through the attachment name
        safe = "".join(c for c in server.name if c.isalnum() or c in " -_").strip() or "server"
        dump = json.dumps(data, indent=2, sort_keys=True).encode()
        await ctx.send(embed=embed, file=discord.File(BytesIO(dump), f"{safe}-settings.json"))

    @staticmethod
    def format_setting(value: t.Any) -> str:
        # bool first: it is a subclass of int, so the numeric branch would render it as 1/0
        if isinstance(value, bool):
            return _("Yes") if value else _("No")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)[:1024] or "-"

    @paltools.command(name="shutdown")
    @ensure_db_connection()
    async def paltools_shutdown(
        self,
        ctx: commands.Context,
        server_name: str,
        seconds: int = 60,
        *,
        message: str = "Server is shutting down",
    ):
        """Gracefully shut down a server (requires confirmation)

        The server name is required: no accidental fleet-wide shutdowns.
        """
        servers = await get_target_servers(ctx.guild.id, server_name)
        if not servers:
            return await ctx.send(_("No enabled server named `{}`").format(server_name))
        if len(servers) > 1:
            # Never guess which box to take down
            names = ", ".join(server.name for server in servers)
            return await ctx.send(_("`{}` matches more than one server: {}").format(server_name, names))
        server = servers[0]
        view = ConfirmView(ctx.author, timeout=60)
        view.confirm_button.style = discord.ButtonStyle.danger
        view.message = await ctx.send(
            _("Shut down **{}** in {} seconds with message: `{}`?").format(server.name, seconds, message),
            view=view,
        )
        await view.wait()
        if not view.result:
            return await view.message.edit(content=_("Shutdown cancelled"), view=None)
        client = PalClient(server.host, server.port, server.admin_password)
        try:
            await client.shutdown(seconds, message)
            await view.message.edit(content=_("Shutdown scheduled for **{}**").format(server.name), view=None)
        except PalApiError as e:
            log.warning("Shutdown failed on %s", server.name, exc_info=e)
            await view.message.edit(content=_("Shutdown failed: {}").format(e), view=None)
