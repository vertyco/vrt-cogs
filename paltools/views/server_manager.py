from contextlib import suppress

import discord
from discord import ui
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.api import PalApiError, PalClient, ServerUnreachable, Unauthorized
from ..db.tables import Server
from ..db.utils import close_open_sessions

_ = Translator("PalTools", __file__)


class ServerModal(ui.Modal):
    def __init__(self, server: Server | None = None):
        super().__init__(title=_("PalWorld Server"), timeout=240)
        self.data: dict | None = None
        self.name = ui.TextInput(label=_("Display Name"), max_length=50, default=server.name if server else None)
        # Capped: the host is interpolated into the manager's TextDisplays, and one giant pasted
        # blob would push the list view past the 4000 char Components V2 budget, locking the
        # manager out of the very panel needed to fix the row
        self.host = ui.TextInput(label=_("Host / IP"), max_length=100, default=server.host if server else None)
        self.port = ui.TextInput(label=_("REST API Port"), max_length=5, default=str(server.port) if server else "8212")
        self.password = ui.TextInput(
            label=_("AdminPassword"), max_length=100, default=server.admin_password if server else None
        )
        for item in (self.name, self.host, self.port, self.password):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        # The host goes straight into a URL, so a pasted scheme, port, path or stray space would
        # make every request to this server raise InvalidURL with nothing to show for it
        host = self.host.value.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if host.startswith("[") and "]" in host:
            # Bracketed IPv6 literal: keep the brackets (the URL needs them), drop any pasted :port
            host = host[: host.index("]") + 1]
        elif host.count(":") == 1:
            # A bare IPv6 literal has multiple colons, so a single one can only be a pasted port
            host = host.split(":")[0]
        name = self.name.value.strip()
        # isdecimal, not isdigit: isdigit accepts superscripts and other numerals that int() rejects
        if not self.port.value.isdecimal() or not 1 <= int(self.port.value) <= 65535:
            # Stop as well, otherwise the caller's modal.wait() blocks until the 240s timeout
            self.stop()
            return await interaction.response.send_message(_("Port must be a number from 1 to 65535"), ephemeral=True)
        if not host or any(c.isspace() for c in host):
            self.stop()
            return await interaction.response.send_message(_("Host must be a hostname or IP"), ephemeral=True)
        if not name:
            # A blank name yields an unselectable option and Discord rejects the whole panel,
            # which would leave the row unreachable through this menu
            self.stop()
            return await interaction.response.send_message(_("Display name cannot be blank"), ephemeral=True)
        await interaction.response.defer()
        self.data = {
            "name": name,
            "host": host,
            "port": int(self.port.value),
            "admin_password": self.password.value,
        }
        self.stop()


class ServerManagerView(ui.LayoutView):
    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        super().__init__(timeout=600)
        self.cog = cog
        self.ctx = ctx
        self.message: discord.Message | None = None
        self.selected: Server | None = None  # None = list mode
        self.remove_armed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.edit(view=None)

    async def start(self):
        await self.build_list()
        self.message = await self.ctx.send(view=self)

    async def refresh_message(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def refresh_after_modal(self):
        """Repaint the panel after a modal, editing the message rather than the interaction.

        A button that opens a modal has spent its response on send_modal, and a modal is not a
        message, so edit_original_response on that interaction is rejected as an empty message.
        The modal submit was already acknowledged in on_submit, which leaves the panel message
        itself as the thing to update.
        """
        if self.message:
            # Reassigned, not edited in place: edit returns the new message object
            self.message = await self.message.edit(view=self)

    async def build_list(self):
        # Components V2 caps a LayoutView at 40 children and 10 top-level components, so the server
        # list is one text block plus a select rather than a container per server.
        self.clear_items()
        self.selected = None
        self.remove_armed = False
        servers = await Server.objects().where(Server.guild_id == self.ctx.guild.id).order_by(Server.name)
        container = ui.Container(accent_color=discord.Color.blurple().value)
        container.add_item(ui.TextDisplay(_("## PalWorld Servers ({})").format(len(servers))))
        if servers:
            lines = []
            for server in servers[:25]:
                online = self.cog.servers_online.get(server.id)
                status = "🟢" if online else ("🔴" if online is False else "⚪")
                enabled = "" if server.enabled else _(" (disabled)")
                lines.append(f"{status} **{server.name}**{enabled}\n-# {server.host}:{server.port}")
            if len(servers) > 25:
                lines.append(_("-# Showing the first 25 of {} servers").format(len(servers)))
            container.add_item(ui.TextDisplay("\n".join(lines)))
        else:
            container.add_item(ui.TextDisplay(_("-# No servers configured yet")))
        self.add_item(container)
        if servers:
            select_row = ui.ActionRow()
            select_row.add_item(ServerSelect(servers[:25]))
            self.add_item(select_row)
        row = ui.ActionRow()
        row.add_item(AddServerButton())
        row.add_item(RefreshButton())
        self.add_item(row)

    async def build_detail(self, server: Server):
        self.clear_items()
        self.selected = server
        online = self.cog.servers_online.get(server.id)
        status = _("🟢 Online") if online else (_("🔴 Offline") if online is False else _("⚪ Unknown"))
        container = ui.Container(accent_color=discord.Color.blurple().value)
        container.add_item(
            ui.TextDisplay(
                f"## {server.name}\n{status}\n"
                + _("**Host:** {}\n**Enabled:** {}\n-# ID: {}").format(
                    f"{server.host}:{server.port}", server.enabled, server.id
                )
            )
        )
        self.add_item(container)
        row = ui.ActionRow()
        row.add_item(TestButton())
        row.add_item(EditButton())
        row.add_item(ToggleButton(server.enabled))
        row.add_item(RemoveButton(self.remove_armed))
        row.add_item(BackButton())
        self.add_item(row)

    async def require_selected(self, interaction: discord.Interaction) -> Server | None:
        """The detail buttons stay dispatchable after a rebuild, so they can fire in list mode"""
        if self.selected is None:
            await interaction.response.send_message(_("That server is no longer selected"), ephemeral=True)
            return None
        return self.selected

    async def show_detail(self, interaction: discord.Interaction, server: Server):
        self.remove_armed = False
        await self.build_detail(server)
        await self.refresh_message(interaction)


class ServerSelect(ui.Select[ServerManagerView]):
    def __init__(self, servers: list[Server]):
        super().__init__(
            placeholder=_("Manage a server..."),
            options=[
                discord.SelectOption(
                    label=server.name[:100],
                    value=str(server.id),
                    description=f"{server.host}:{server.port}"[:100],
                )
                for server in servers
            ],
        )
        self.servers = {str(server.id): server for server in servers}

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_detail(interaction, self.servers[self.values[0]])


class AddServerButton(ui.Button[ServerManagerView]):
    def __init__(self):
        super().__init__(label=_("Add Server"), style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        # Held in a local: rebuilding the panel clears this button off the view, and clear_items
        # nulls the view reference of every item it removes, this one included
        view = self.view
        modal = ServerModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.data:
            return
        server = Server(guild_id=interaction.guild.id, enabled=True, **modal.data)
        await server.save()
        await view.build_list()
        await view.refresh_after_modal()


class RefreshButton(ui.Button[ServerManagerView]):
    def __init__(self):
        super().__init__(label=_("Refresh"), style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        # Ack first: the rebuild hits the database, and a slow query would otherwise
        # outlive the three second interaction window
        await interaction.response.defer()
        await view.build_list()
        await view.refresh_message(interaction)


class TestButton(ui.Button[ServerManagerView]):
    def __init__(self):
        super().__init__(label=_("Test Connection"), style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        server = await self.view.require_selected(interaction)
        if server is None:
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        client = PalClient(server.host, server.port, server.admin_password)
        try:
            info = await client.info()
            txt = _("✅ Connected: **{}** ({})").format(info.servername, info.version)
        except Unauthorized:
            txt = _("❌ 401 Unauthorized: wrong AdminPassword")
        except ServerUnreachable:
            txt = _("❌ Unreachable: check host/port, RESTAPIEnabled=True, and firewall")
        except PalApiError as e:
            txt = _("❌ Bad response: {}").format(e)
        await interaction.followup.send(txt, ephemeral=True)


class EditButton(ui.Button[ServerManagerView]):
    def __init__(self):
        super().__init__(label=_("Edit"), style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        server = await view.require_selected(interaction)
        if server is None:
            return
        modal = ServerModal(server)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.data:
            return
        endpoint_changed = (server.host, server.port) != (modal.data["host"], modal.data["port"])
        for attr, value in modal.data.items():
            setattr(server, attr, value)
        # Only the edited columns: this row was read when the list was built, up to 10 minutes ago,
        # and a blanket save would rewind last_online and clobber another admin's toggle
        await server.save(columns=[Server.name, Server.host, Server.port, Server.admin_password])
        if endpoint_changed:
            # The row now points at a different box, so everything learned from the old one is
            # invalid: close its sessions and force a silent re-baseline, same as a disable,
            # otherwise the next tick diffs the new box's roster against the old box's snapshot
            await close_open_sessions(server.id)
            view.cog.snapshots.pop(server.id, None)
            view.cog.servers_online.pop(server.id, None)
        await view.build_detail(server)
        await view.refresh_after_modal()


class ToggleButton(ui.Button[ServerManagerView]):
    def __init__(self, enabled: bool):
        label = _("Disable") if enabled else _("Enable")
        super().__init__(label=label, style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        server = await view.require_selected(interaction)
        if server is None:
            return
        await interaction.response.defer()
        server.enabled = not server.enabled
        await server.save(columns=[Server.enabled])
        if not server.enabled:
            view.cog.snapshots.pop(server.id, None)
            # Both, like RemoveButton: leaving the reachability entry behind keeps this panel
            # painting a status for a server the poll loop no longer touches
            view.cog.servers_online.pop(server.id, None)
            # The poll loop skips disabled servers, so close the sessions here or playtime accrues
            # forever. A tick already mid-poll on this server can undo both of these; the poll
            # loop's purge_stale_servers sweep re-closes and re-pops on the next tick.
            await close_open_sessions(server.id)
        await view.build_detail(server)
        await view.refresh_message(interaction)


class RemoveButton(ui.Button[ServerManagerView]):
    def __init__(self, armed: bool):
        label = _("CONFIRM REMOVE") if armed else _("Remove")
        super().__init__(label=label, style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        server = await view.require_selected(interaction)
        if server is None:
            return
        if not view.remove_armed:
            view.remove_armed = True
            await view.build_detail(server)
            await view.refresh_message(interaction)
            return
        await interaction.response.defer()
        # Session.server is ON DELETE CASCADE, so the sessions go with the server
        await Server.delete().where(Server.id == server.id)
        view.cog.snapshots.pop(server.id, None)
        view.cog.servers_online.pop(server.id, None)
        await view.build_list()
        await view.refresh_message(interaction)


class BackButton(ui.Button[ServerManagerView]):
    def __init__(self):
        super().__init__(label=_("Back"), style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        # Ack first, same as RefreshButton: the rebuild queries the database
        await interaction.response.defer()
        await view.build_list()
        await view.refresh_message(interaction)
