import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from time import perf_counter

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_timedelta, text_to_file

from .formatting import backup_str, humanize_size
from .models import DB, GuildSettings
from .serializers import GuildBackup

log = logging.getLogger("red.vrt.cartographer.views")
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
    def __init__(self, include_limits: bool = False):
        self.confirm: bool | None = None
        self.limit: int = 0
        super().__init__(title=_("Confirmation"), timeout=120)
        placeholder = "(y/n)"
        if not include_limits:
            placeholder += " " + _("THIS CANNOT BE UNDONE!")
        self.field = discord.ui.TextInput(
            label=_("Are you SURE?"),
            style=discord.TextStyle.short,
            required=True,
            placeholder=placeholder,
        )
        self.add_item(self.field)

        self.field2 = discord.ui.TextInput(
            label=_("How many messages to backup? (0 = None)"),
            style=discord.TextStyle.short,
            required=True,
            placeholder="0",
        )
        if include_limits:
            self.add_item(self.field2)

    async def on_submit(self, interaction: discord.Interaction):
        if self.field.value.isdigit():
            bad_resp = "(y/n) " + _("response must be a string!")
            return await interaction.response.send_message(bad_resp, ephemeral=True)
        if self.field2.value and not self.field2.value.isdigit():
            bad_resp = _("Message backup limit must be a number!")
            return await interaction.response.send_message(bad_resp, ephemeral=True)
        self.confirm = True if self.field.value.lower().startswith("y") else False
        self.limit = int(self.field2.value) if self.field2.value else 0
        await interaction.response.defer()
        self.stop()


class BackupMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, db: DB, backup_dir: Path):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.db = db
        self.backup_dir = backup_dir
        self.backups: list[Path] = sorted(self.backup_dir.iterdir(), key=lambda x: x.stat().st_ctime)

        self.guild = ctx.guild
        self.conf: GuildSettings = self.db.get_conf(self.guild)

        self.message: discord.Message = None
        self.page = 0
        self.close.label = _("Close")

    async def get_page(self) -> discord.Embed:
        title = _("Cartographer Backups")
        c_name = _("Controls")
        controls = _(
            "- Backup Current Server: 📥\n"
            "- Restore Here: 🔄\n"
            "- Switch Servers: 🔍\n"
            "- Set AutoBackup Interval: ⌛\n"
            "- Delete Backup: 🗑️\n"
            "- Print Details: ℹ️\n"
        )
        s_name = _("Settings")
        settings = _(
            "- Auto Backup Interval Hours: {}\n"
            "- Last Backup: {}\n"
            "**Global Settings**\n"
            "-# The following settings are configured by the bot owner\n"
            "- Max Backups Per Guild: {}\n"
            "- Backup Message Limit: {}\n"
            "- Backup Members: {}\n"
            "- Backup Roles: {}\n"
            "- Backup Emojis: {}\n"
            "- Backup Stickers: {}\n"
        ).format(
            self.conf.auto_backup_interval_hours,
            f"{self.conf.last_backup_f} ({self.conf.last_backup_r})",
            self.db.max_backups_per_guild,
            self.db.message_backup_limit,
            self.db.backup_members,
            self.db.backup_roles,
            self.db.backup_emojis,
            self.db.backup_stickers,
        )

        self.backups: list[Path] = sorted(self.backup_dir.iterdir(), key=lambda x: x.stat().st_ctime)

        if self.backups:
            self.page = self.page % len(self.backups)
            file: Path = self.backups[self.page]
            txt = _("## {}\n" "`Size:    `{}\n" "`Created: `{}\n").format(
                file.stem,
                humanize_size(file.stat().st_size),
                f"<t:{int(file.stat().st_ctime)}:f> (<t:{int(file.stat().st_ctime)}:R>)",
            )
            embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
            embed.add_field(name=s_name, value=settings, inline=False)
            embed.add_field(name=c_name, value=controls, inline=False)
            embed.set_footer(text=_("Page {}").format(f"{self.page + 1}/{len(self.backups)}"))
        else:
            txt = _("There are no backups for this server yet!")
            embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
            embed.add_field(name=s_name, value=settings, inline=False)
            embed.add_field(name=c_name, value=controls, inline=False)

        return embed

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.edit(view=None)
        return await super().on_timeout()

    async def start(self):
        self.message = await self.ctx.send(embed=await self.get_page(), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left10)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 10
        await interaction.response.edit_message(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_left)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await interaction.response.edit_message(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await interaction.response.edit_message(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji=e_right10)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        await interaction.response.edit_message(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{INBOX TRAY}", row=1)
    async def backup(self, interaction: discord.Interaction, button: discord.Button):
        # Check if bot has administrator permissions
        if not self.guild.me.guild_permissions.administrator:
            txt = _("I need administrator permissions to restore a backup in this server!")
            return await interaction.response.send_message(txt, ephemeral=True)

        modal = Confirm(include_limits=True)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.confirm is None:
            return

        if not modal.confirm:
            txt = _("Restore has been cancelled!")
            return await interaction.followup.send(txt, ephemeral=True)

        if modal.limit > self.db.message_backup_limit:
            txt = _("The maximum amount of messages that can be backed up per channel is {}!").format(
                self.db.message_backup_limit
            )
            return await interaction.followup.send(txt, ephemeral=True)

        if self.db.backup_roles and self.guild.roles:
            highest_guild_role = max(self.guild.roles, key=lambda r: r.position)
            highest_bot_role = max(self.guild.me.roles, key=lambda r: r.position)
            if highest_guild_role > highest_bot_role:
                txt = _("Warning! I need to have the highest role in the server to restore roles properly!")
                await interaction.followup.send(txt, ephemeral=True)

        txt = _("Backing up {}!\n-# This may take a while...").format(self.guild.name)
        thumbnail = "https://i.imgur.com/l3p6EMX.gif"
        embed = discord.Embed(title=_("Backup in Progress"), description=txt, color=discord.Color.blue())
        embed.set_thumbnail(url=thumbnail)
        message = await interaction.channel.send(embed=embed)
        self.conf = self.db.get_conf(interaction.guild)
        start = perf_counter()
        try:
            await self.conf.backup(
                guild=self.guild,
                backups_dir=self.backup_dir.parent,
                limit=modal.limit,
                backup_members=self.db.backup_members,
                backup_roles=self.db.backup_roles,
                backup_emojis=self.db.backup_emojis,
                backup_stickers=self.db.backup_stickers,
            )
        except Exception as e:
            log.error("An error occurred while backing up the server!", exc_info=e)
            txt = _("An error occurred while backing up the server!\n{}").format(box(str(e)))
            return await message.edit(content=txt, embed=None)

        delta = humanize_timedelta(seconds=perf_counter() - start)
        txt = _("Backup created in {}!").format(delta if delta else _("0 seconds"))
        embed = discord.Embed(title=_("Backup Created"), description=txt, color=discord.Color.green())
        await message.edit(embed=embed)
        await self.message.edit(embed=await self.get_page())
        self.db.cleanup(self.guild, self.backup_dir.parent)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji=e_restore, row=1)
    async def restore(self, interaction: discord.Interaction, button: discord.Button):
        # Check if bot has administrator permissions
        if not self.guild.me.guild_permissions.administrator:
            txt = _("I need administrator permissions to restore a backup in this server!")
            return await interaction.response.send_message(txt, ephemeral=True)

        if not self.backups:
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

        self.page %= len(self.backups)
        backup_file = self.backups[self.page]
        backup: GuildBackup = await asyncio.to_thread(
            GuildBackup.model_validate_json, backup_file.read_text(encoding="utf-8")
        )

        txt = _("Your backup is being restored!")
        await interaction.followup.send(txt, ephemeral=True)

        async with self.ctx.typing():
            results = await backup.restore(self.guild, interaction.channel)
            if results:
                txt = _("The following errors occurred while restoring the backup")
                await interaction.channel.send(txt, file=text_to_file(results, "restore_results.txt"))

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
        self.backup_dir = self.backup_dir.parent / modal.entry
        # self.conf = self.db.get_conf(guild)
        await self.message.edit(embed=await self.get_page())

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
        if not self.backups:
            txt = _("No backups to delete!")
            return await interaction.response.send_message(txt, ephemeral=True)

        backup_file = self.backups[self.page]
        backup_file.unlink()
        del self.backups[self.page]

        txt = _("Backup deleted!")
        await interaction.response.send_message(txt, ephemeral=True, delete_after=30)
        await self.message.edit(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="ℹ️", row=2)
    async def print_details(self, interaction: discord.Interaction, button: discord.Button):
        """Load the backup and show details"""
        if not self.backups:
            txt = _("No backups to get info for!")
            return await interaction.response.send_message(txt, ephemeral=True)
        await interaction.response.defer()
        backup_file = self.backups[self.page]
        txt = await asyncio.to_thread(backup_str, backup_file)
        await interaction.followup.send(txt, ephemeral=True)
