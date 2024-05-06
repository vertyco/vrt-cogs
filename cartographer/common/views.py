import asyncio

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .formatting import backup_menu_embeds
from .models import DB, GuildBackup, GuildSettings

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
        self.rem_old: bool = False
        super().__init__(title=_("Confirmation"), timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Are you SURE?"),
            style=discord.TextStyle.short,
            required=True,
            placeholder="(y/n) " + _("THIS CANNOT BE UNDONE!"),
        )
        self.add_item(self.field)
        self.field2 = discord.ui.TextInput(
            label=_("Remove Old"),
            style=discord.TextStyle.short,
            required=True,
            placeholder="(y/n) " + _("removes unsaved channels/roles"),
        )
        self.add_item(self.field2)

    async def on_submit(self, interaction: discord.Interaction):
        bad_resp = "(y/n) " + _("response must be a string!")
        if self.field.value.isdigit() or self.field2.value.isdigit():
            return await interaction.response.send_message(bad_resp, ephemeral=True)
        self.confirm = True if self.field.value.lower().startswith("y") else False
        self.rem_old = True if self.field2.value.lower().startswith("y") else False
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
        self.pages = backup_menu_embeds(self.conf, self.guild)
        self.page = 0
        self.close.label = _("Close")

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        await self.message.edit(view=None)
        return await super().on_timeout()

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left10)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right10)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{INBOX TRAY}", row=1)
    async def backup(self, interaction: discord.Interaction, button: discord.Button):
        txt = _("Backing up {}!").format(self.guild.name)
        await interaction.response.send_message(txt, ephemeral=True, delete_after=30)
        self.conf = self.db.get_conf(interaction.guild)
        await self.conf.backup(self.guild)
        txt = _("Backup created!")
        backup = self.conf.backups[-1]
        if backup.has_duplcate_roles:
            txt += "\n" + _(
                "- Backup contains roles with duplcate names! Only one role per unique name can be restored!"
            )
        if backup.has_duplcate_categories:
            txt += "\n" + _(
                "- Backup contains categories with duplcate names! Only one category per unique name can be restored!"
            )
        if backup.has_duplcate_text_channels:
            txt += "\n" + _(
                "- Backup contains text channels with duplcate names! Only one text channel per unique name can be restored!"
            )
        if backup.has_duplcate_voice_channels:
            txt += "\n" + _(
                "- Backup contains voice channels with duplcate names! Only one voice channel per unique name can be restored!"
            )
        if backup.has_duplcate_forum_channels:
            txt += "\n" + _(
                "- Backup contains forum channels with duplcate names! Only one forum channel per unique name can be restored!"
            )
        await interaction.followup.send(txt, ephemeral=True)
        self.pages = backup_menu_embeds(self.conf, self.guild)
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji=e_restore, row=1)
    async def restore(self, interaction: discord.Interaction, button: discord.Button):
        if not self.conf.backups:
            txt = _("No backups to restore!")
            return await interaction.response.send_message(txt, ephemeral=True)

        modal = Confirm()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.confirm is None:
            return

        if modal.confirm:
            self.page %= len(self.conf.backups)
            backup: GuildBackup = self.conf.backups[self.page]
            asyncio.create_task(backup.restore(self.guild, interaction.channel, modal.rem_old))
            txt = _("Your backup is being restored!")
            if backup.has_duplcate_roles:
                txt += "\n" + _(
                    "- Backup contains roles with duplcate names! Only one role per unique name will be restored!"
                )
            if backup.has_duplcate_categories:
                txt += "\n" + _(
                    "- Backup contains categories with duplcate names! Only one category per unique name will be restored!"
                )
            if backup.has_duplcate_text_channels:
                txt += "\n" + _(
                    "- Backup contains text channels with duplcate names! Only one text channel per unique name will be restored!"
                )
            if backup.has_duplcate_voice_channels:
                txt += "\n" + _(
                    "- Backup contains voice channels with duplcate names! Only one voice channel per unique name will be restored!"
                )
            if backup.has_duplcate_forum_channels:
                txt += "\n" + _(
                    "- Backup contains forum channels with duplcate names! Only one forum channel per unique name will be restored!"
                )
            return await interaction.followup.send(txt, ephemeral=True)

        txt = _("Restore has been cancelled!")
        return await interaction.followup.send(txt, ephemeral=True)

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
        self.pages = backup_menu_embeds(self.conf, guild)
        self.page = 0
        await self.message.edit(embed=self.pages[self.page])

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
        del self.conf.backups[self.page]
        self.pages = backup_menu_embeds(self.conf, self.guild)
        self.page %= len(self.pages)
        await self.message.edit(embed=self.pages[self.page])
        txt = _("Backup deleted!")
        return await interaction.response.send_message(txt, ephemeral=True, delete_after=30)
