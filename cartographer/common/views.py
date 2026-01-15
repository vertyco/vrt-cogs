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
from .models import DB, GuildSettings, RestoreOptions
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


# ------------------- RESTORE OPTIONS VIEW -------------------


class RestoreSelect(discord.ui.Select):
    """Select menu for choosing what to restore and behavior options."""

    def __init__(self, options_model: RestoreOptions, backup: GuildBackup):
        self.options_model = options_model
        self.backup = backup

        options = [
            discord.SelectOption(
                label=_("Server Settings"),
                value="server_settings",
                description=_("Name, icon, banner, verification, etc."),
                default=options_model.server_settings,
            ),
            discord.SelectOption(
                label=_("Roles ({})").format(len(backup.roles)),
                value="roles",
                description=_("Role definitions and permissions"),
                default=options_model.roles,
            ),
            discord.SelectOption(
                label=_("Emojis ({})").format(len(backup.emojis)),
                value="emojis",
                description=_("Custom emojis"),
                default=options_model.emojis,
            ),
            discord.SelectOption(
                label=_("Stickers ({})").format(len(backup.stickers)),
                value="stickers",
                description=_("Custom stickers"),
                default=options_model.stickers,
            ),
            discord.SelectOption(
                label=_("Categories ({})").format(len(backup.categories)),
                value="categories",
                description=_("Category channels"),
                default=options_model.categories,
            ),
            discord.SelectOption(
                label=_("Text Channels ({})").format(len(backup.text_channels)),
                value="text_channels",
                description=_("Text channels"),
                default=options_model.text_channels,
            ),
            discord.SelectOption(
                label=_("Voice Channels ({})").format(len(backup.voice_channels)),
                value="voice_channels",
                description=_("Voice channels"),
                default=options_model.voice_channels,
            ),
            discord.SelectOption(
                label=_("Forum Channels ({})").format(len(backup.forums)),
                value="forums",
                description=_("Forum channels"),
                default=options_model.forums,
            ),
            discord.SelectOption(
                label=_("Bans ({})").format(len(backup.bans)),
                value="bans",
                description=_("User bans"),
                default=options_model.bans,
            ),
            discord.SelectOption(
                label=_("Restore Member Roles ({} members)").format(len(backup.members)),
                value="restore_member_roles",
                description=_("Assign saved roles to members"),
                default=options_model.restore_member_roles,
            ),
            discord.SelectOption(
                label=_("Delete Unmatched Items"),
                value="delete_unmatched",
                description=_("⚠️ Remove items not in backup"),
                default=options_model.delete_unmatched,
                emoji="⚠️",
            ),
            discord.SelectOption(
                label=_("Only Restore Missing"),
                value="only_missing",
                description=_("Skip existing items, only recreate deleted ones"),
                default=options_model.only_missing,
                emoji="🆕",
            ),
        ]
        super().__init__(
            placeholder=_("Select what to restore..."),
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Reset all to False, then enable selected ones
        self.options_model.server_settings = "server_settings" in self.values
        self.options_model.roles = "roles" in self.values
        self.options_model.emojis = "emojis" in self.values
        self.options_model.stickers = "stickers" in self.values
        self.options_model.categories = "categories" in self.values
        self.options_model.text_channels = "text_channels" in self.values
        self.options_model.voice_channels = "voice_channels" in self.values
        self.options_model.forums = "forums" in self.values
        self.options_model.bans = "bans" in self.values
        self.options_model.restore_member_roles = "restore_member_roles" in self.values
        self.options_model.delete_unmatched = "delete_unmatched" in self.values
        self.options_model.only_missing = "only_missing" in self.values

        # Update the defaults for the select
        for option in self.options:
            option.default = option.value in self.values

        await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)


class RestoreOptionsView(discord.ui.View):
    """View for selecting granular restore options."""

    def __init__(
        self,
        author: discord.Member,
        backup: GuildBackup,
        guild: discord.Guild,
    ):
        super().__init__(timeout=300)
        self.author = author
        self.backup = backup
        self.guild = guild
        self.options = RestoreOptions()
        self.confirmed: bool = False

        # Add the select menu
        self.restore_select = RestoreSelect(self.options, backup)
        self.add_item(self.restore_select)

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=_("Restore Options"),
            description=_("Configure what you want to restore from the backup **{}**").format(self.backup.name),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=_("Selected Options"),
            value=self.options.summary(),
            inline=False,
        )
        if self.options.delete_unmatched:
            embed.add_field(
                name=_("⚠️ Warning"),
                value=_(
                    "**Delete Unmatched Items** is enabled!\n"
                    "This will remove roles, channels, emojis, and stickers that are not in the backup."
                ),
                inline=False,
            )
        embed.set_footer(text=_("Click Confirm to start the restore"))
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if at least something is selected
        has_selection = any(
            [
                self.options.server_settings,
                self.options.roles,
                self.options.emojis,
                self.options.stickers,
                self.options.categories,
                self.options.text_channels,
                self.options.voice_channels,
                self.options.forums,
                self.options.bans,
                self.options.restore_member_roles,
            ]
        )
        if not has_selection:
            await interaction.response.send_message(
                _("Please select at least one thing to restore!"),
                ephemeral=True,
            )
            return

        # Extra confirmation if delete_unmatched is enabled
        if self.options.delete_unmatched:
            confirm_view = DeleteUnmatchedConfirm(interaction.user)
            await interaction.response.send_message(
                _(
                    "⚠️ **WARNING: Delete Unmatched Items is ENABLED!** ⚠️\n\n"
                    "This will **permanently delete** any roles, channels, emojis, and stickers "
                    "that are not in the backup.\n\n"
                    "**This action cannot be undone!**\n\n"
                    "Are you absolutely sure you want to continue?"
                ),
                view=confirm_view,
                ephemeral=True,
            )
            await confirm_view.wait()
            if not confirm_view.confirmed:
                return

        self.confirmed = True
        if not interaction.response.is_done():
            await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Select All", style=discord.ButtonStyle.secondary, row=2)
    async def select_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.options.server_settings = True
        self.options.roles = True
        self.options.emojis = True
        self.options.stickers = True
        self.options.categories = True
        self.options.text_channels = True
        self.options.voice_channels = True
        self.options.forums = True
        self.options.bans = True
        self.options.restore_member_roles = True
        # Update select menu defaults (don't auto-enable delete_unmatched for safety)
        for option in self.restore_select.options:
            option.default = option.value != "delete_unmatched"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Deselect All", style=discord.ButtonStyle.secondary, row=2)
    async def deselect_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.options.server_settings = False
        self.options.roles = False
        self.options.emojis = False
        self.options.stickers = False
        self.options.categories = False
        self.options.text_channels = False
        self.options.voice_channels = False
        self.options.forums = False
        self.options.bans = False
        self.options.restore_member_roles = False
        self.options.delete_unmatched = False
        # Update select menu defaults
        for option in self.restore_select.options:
            option.default = False
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.edit_message(
            content=_("Restore cancelled."),
            embed=None,
            view=None,
        )
        self.stop()


# ------------------- OTHER MODALS/VIEWS -------------------


class DeleteUnmatchedConfirm(discord.ui.View):
    """Extra confirmation view for delete_unmatched option."""

    def __init__(self, author: discord.Member | discord.User):
        super().__init__(timeout=60)
        self.author = author
        self.confirmed: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Delete Unmatched Items", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.edit_message(content=_("Proceeding with restore..."), view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.edit_message(content=_("Restore cancelled."), view=None)
        self.stop()


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
        self.entry = int(self.field.value)
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
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backups: list[Path] = sorted(self.backup_dir.iterdir(), key=lambda x: x.stat().st_ctime)

        self.guild = ctx.guild
        self.conf: GuildSettings = self.db.get_conf(self.guild)
        # Track which guild's backups we're viewing (may differ from self.guild after switching)
        self.viewing_guild_id: int = ctx.guild.id

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
            "- Download Backup: 📤\n"
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

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backups: list[Path] = sorted(self.backup_dir.iterdir(), key=lambda x: x.stat().st_ctime)

        # Show which guild's backups we're viewing if different from current
        viewing_note = ""
        if self.viewing_guild_id != self.guild.id:
            viewing_guild = self.ctx.bot.get_guild(self.viewing_guild_id)
            viewing_name = viewing_guild.name if viewing_guild else str(self.viewing_guild_id)
            viewing_note = _("\n-# Viewing backups from: **{}**").format(viewing_name)

        if self.backups:
            self.page = self.page % len(self.backups)
            file: Path = self.backups[self.page]
            txt = _("## {}\n`Size:    `{}\n`Created: `{}\n{}").format(
                file.stem,
                humanize_size(file.stat().st_size),
                f"<t:{int(file.stat().st_ctime)}:f> (<t:{int(file.stat().st_ctime)}:R>)",
                viewing_note,
            )
            embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
            embed.add_field(name=s_name, value=settings, inline=False)
            embed.add_field(name=c_name, value=controls, inline=False)
            embed.set_footer(text=_("Page {}").format(f"{self.page + 1}/{len(self.backups)}"))
        else:
            txt = _("There are no backups for this server yet!{}").format(viewing_note)
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

        # If viewing another guild's backups, only the owner of that guild can restore from it
        if self.viewing_guild_id != self.guild.id:
            viewing_guild = self.ctx.bot.get_guild(self.viewing_guild_id)
            if not viewing_guild:
                txt = _("The server you're viewing backups for no longer exists!")
                return await interaction.response.send_message(txt, ephemeral=True)
            if viewing_guild.owner_id != interaction.user.id:
                txt = _("Only the owner of **{}** can restore its backups to another server!").format(
                    viewing_guild.name
                )
                return await interaction.response.send_message(txt, ephemeral=True)

        # Load the backup first to show options
        self.page %= len(self.backups)
        backup_file = self.backups[self.page]
        backup: GuildBackup = await asyncio.to_thread(
            GuildBackup.model_validate_json, backup_file.read_text(encoding="utf-8")
        )

        # Show the restore options view
        options_view = RestoreOptionsView(
            author=interaction.user,
            backup=backup,
            guild=self.guild,
        )
        await interaction.response.send_message(
            embed=options_view.get_embed(),
            view=options_view,
            ephemeral=True,
        )
        await options_view.wait()

        if not options_view.confirmed:
            return

        txt = _("Your backup is being restored with the selected options!")
        await interaction.followup.send(txt, ephemeral=True)

        async with self.ctx.typing():
            results = await backup.restore(self.guild, interaction.channel, options_view.options)
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
        # Update to view the other guild's backups
        self.backup_dir = self.backup_dir.parent / str(modal.entry)
        self.viewing_guild_id = guild.id
        self.conf = self.db.get_conf(guild)
        self.page = 0  # Reset to first page
        await self.message.edit(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{HOURGLASS}", row=1)
    async def interval(self, interaction: discord.Interaction, button: discord.Button):
        if not self.db.allow_auto_backups:
            txt = _("Auto backups have been disabled by the bot owner!")
            return await interaction.response.send_message(txt, ephemeral=True)
        # Can only modify settings for the current server
        if self.viewing_guild_id != self.guild.id:
            txt = _("You can only modify auto-backup settings for the server you're currently in!")
            return await interaction.response.send_message(txt, ephemeral=True)
        modal = IntModal(_("Auto Backup Interval"), _("Interval Hours"), _("Hours in-between backups"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.entry is None:
            return
        self.conf.auto_backup_interval_hours = modal.entry
        txt = _("Auto-backup interval hours has been set to {}").format(modal.entry)
        await interaction.followup.send(txt, ephemeral=True)
        await self.message.edit(embed=await self.get_page())

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
        # Can only delete backups for the current server
        if self.viewing_guild_id != self.guild.id:
            txt = _("You can only delete backups for the server you're currently in!")
            return await interaction.response.send_message(txt, ephemeral=True)

        backup_file = self.backups[self.page]
        backup_file.unlink()
        del self.backups[self.page]

        # Adjust page index if we deleted the last backup in the list
        if self.backups and self.page >= len(self.backups):
            self.page = len(self.backups) - 1

        txt = _("Backup deleted!")
        await interaction.response.send_message(txt, ephemeral=True, delete_after=30)
        await self.message.edit(embed=await self.get_page())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="📤", row=2)
    async def download(self, interaction: discord.Interaction, button: discord.Button):
        """Download the backup file"""
        if not self.backups:
            txt = _("No backups to download!")
            return await interaction.response.send_message(txt, ephemeral=True)
        # Can only download backups for the current server
        if self.viewing_guild_id != self.guild.id:
            txt = _("You can only download backups for the server you're currently in!")
            return await interaction.response.send_message(txt, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        backup_file = self.backups[self.page]
        await interaction.followup.send(
            _("Here is your backup file:"),
            file=discord.File(backup_file, filename=backup_file.name),
            ephemeral=True,
        )

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="ℹ️", row=2)
    async def print_details(self, interaction: discord.Interaction, button: discord.Button):
        """Load the backup and show details"""
        if not self.backups:
            txt = _("No backups to get info for!")
            return await interaction.response.send_message(txt, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        backup_file = self.backups[self.page]
        txt = await asyncio.to_thread(backup_str, backup_file)
        await interaction.followup.send(txt, ephemeral=True)
