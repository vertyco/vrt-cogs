import asyncio

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .formatting import backup_str
from .models import DB, GuildSettings
from .serializers import GuildBackup

_ = Translator("Cartographer", __file__)


e_left10 = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}"
e_left = "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
e_right = "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"
e_right10 = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}"
e_restore = "\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}"
e_search = "\N{LEFT-POINTING MAGNIFYING GLASS}"
e_delete = "\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"


class IntModal(discord.ui.Modal):
    def __init__(self, title: str, label: str, placeholder: str):
        self.entry: int | None = None
        super().__init__(title=title, timeout=120)
        self.field = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.short,
            required=True,
            placeholder=placeholder,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.field.value.isdigit():
            txt = _("That is not a number!")
            return await interaction.response.send_message(txt, ephemeral=True)
        self.entry = self.field.value
        await interaction.response.defer()
        self.stop()


class Confirm(discord.ui.Modal):
    def __init__(self):
        self.confirm: bool | None = None
        super().__init__(title=_("Confirmation"), timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Are you SURE?"),
            style=discord.TextStyle.short,
            required=True,
            placeholder="(y/n) " + _("THIS CANNOT BE UNDONE!"),
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        if self.field.value.isdigit():
            bad_resp = "(y/n) " + _("response must be a string!")
            return await interaction.response.send_message(bad_resp, ephemeral=True)
        self.confirm = True if self.field.value.lower().startswith("y") else False
        await interaction.response.defer()
        self.stop()


class BackupMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, db: DB):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.db = db
        self.guild = ctx.guild
        self.conf: GuildSettings = self.db.get_conf(self.guild)

        self.message: discord.Message = None
        self.page = 0
        self.close.label = _("Close")

    def get_page(self) -> discord.Embed:
        self.page = self.page % len(self.conf.backups) if self.conf.backups else 0
        c_name = _("Controls")
        controls = _(
            "- Backup Current Server: 📥\n"
            "- Restore Here: \N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}\n"
            "- Switch Servers: 🔍\n"
            "- Set AutoBackup Interval: ⌛\n"
            "- Delete Backup: 🗑️\n"
        )
        s_name = _("Settings")
        settings = _("- Auto Backup Interval Hours: {}\n- Last Backup: {}").format(
            self.conf.auto_backup_interval_hours, f"{self.conf.last_backup_f} ({self.conf.last_backup_r})"
        )
        title = _("Cartographer Backups for {}").format(self.guild.name)
        if not self.conf.backups:
            txt = _("There are no backups for this server yet!")
            embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
            embed.add_field(name=s_name, value=settings, inline=False)
            embed.add_field(name=c_name, value=controls, inline=False)
        else:
            txt = backup_str(self.conf.backups[self.page])
            embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
            embed.add_field(name=s_name, value=settings, inline=False)
            embed.add_field(name=c_name, value=controls, inline=False)
            embed.set_footer(text=_("Page {}").format(f"{self.page + 1}/{len(self.conf.backups)}"))
        return embed

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        await self.message.edit(view=None)
        return await super().on_timeout()

    async def start(self):
        self.message = await self.ctx.send(embed=self.get_page(), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left10)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 10
        await interaction.response.edit_message(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right10)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        await interaction.response.edit_message(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{INBOX TRAY}", row=1)
    async def backup(self, interaction: discord.Interaction, button: discord.Button):
        txt = _("Backing up {}!\n-# This may take a while...").format(self.guild.name)
        await interaction.response.send_message(txt, ephemeral=True, delete_after=30)
        self.conf = self.db.get_conf(interaction.guild)
        await self.conf.backup(self.guild)
        txt = _("Backup created!")
        await interaction.followup.send(txt, ephemeral=True)
        await self.message.edit(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji=e_restore, row=1)
    async def restore(self, interaction: discord.Interaction, button: discord.Button):
        # Check if bot has administator permissions
        if not self.guild.me.guild_permissions.administrator:
            txt = _("I need administrator permissions to restore a backup in this server!")
            return await interaction.response.send_message(txt, ephemeral=True)

        if not self.conf.backups:
            txt = _("No backups to restore!")
            return await interaction.response.send_message(txt, ephemeral=True)

        modal = Confirm()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.confirm is None:
            return

        if not modal.confirm:
            txt = _("Restore has been cancelled!")
            return await interaction.followup.send(txt, ephemeral=True)

        self.page %= len(self.conf.backups)
        backup: GuildBackup = await asyncio.to_thread(self.conf.backups[self.page].model_copy, deep=True)

        txt = _("Your backup is being restored!")
        await interaction.followup.send(txt, ephemeral=True)

        async with self.ctx.typing():
            await backup.restore(self.guild, interaction.channel)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji=e_search, row=1)
    async def switch(self, interaction: discord.Interaction, button: discord.Button):
        modal = IntModal(_("Switch Servers"), _("Server ID"), _("Enter the ID of the server"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.entry is None:
            return
        guild: discord.Guild = self.ctx.bot.get_guild(int(modal.entry))
        if not guild:
            txt = _("I am not in that server!")
            return await interaction.followup.send(txt, ephemeral=True)
        guild_member = guild.get_member(interaction.user.id)
        if not guild_member:
            txt = _("You do not appear to be in that server!")
            return await interaction.followup.send(txt, ephemeral=True)
        if not guild_member.guild_permissions.administrator:
            txt = _("You can only switch to servers that you are an administrator of!")
            return await interaction.followup.send(txt, ephemeral=True)
        self.conf = self.db.get_conf(guild)
        await self.message.edit(embed=self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{HOURGLASS}", row=1)
    async def interval(self, interaction: discord.Interaction, button: discord.Button):
        if not self.db.allow_auto_backups:
            txt = _("Auto backups have been disabled by the bot owner!")
            return await interaction.response.send_message(txt, ephemeral=True)
        modal = IntModal(_("Auto Backup Interval"), _("Interval Hours"), _("Hours in-between backups"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.entry is None:
            return
        self.conf.auto_backup_interval_hours = modal.entry
        txt = _("Auto-backup interval hours has been set to {}").format(modal.entry)
        await interaction.followup.send(txt, ephemeral=True)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji=e_delete, row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.Button):
        if not self.conf.backups:
            txt = _("No backups to delete!")
            return await interaction.response.send_message(txt, ephemeral=True)

        txt = _("Backup deleted!")
        await interaction.response.send_message(txt, ephemeral=True, delete_after=30)

        del self.conf.backups[self.page]
        await self.message.edit(embed=self.get_page())
