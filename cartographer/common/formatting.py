import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from .models import GuildBackup, GuildSettings

_ = Translator("Cartographer", __file__)


def backup_str(backup: GuildBackup) -> str:
    txt = _(
        "`Created:        `{}\n"
        "`Name:           `{}\n"
        "`AFK Channel:    `{}\n"
        "`AFK Timeout:    `{}\n"
        "`Verification:   `{}\n"
        "`Notifications:  `{}\n"
        "`Locale:         `{}\n"
        "`Role Count:     `{}\n"
        "`Members Saved:  `{}\n"
        "`Categories:     `{}\n"
        "`Text Channels:  `{}\n"
        "`Voice Channels: `{}\n"
        "`Forums:         `{}\n"
    ).format(
        f"{backup.created_f} ({backup.created_r})",
        backup.name,
        backup.afk_channel_id,
        backup.afk_timeout,
        backup.verification_level,
        backup.default_notifications,
        backup.preferred_locale,
        len(backup.roles),
        humanize_number(len(backup.members)),
        len(backup.categories),
        len(backup.text_channels),
        len(backup.voice_channels),
        len(backup.forums),
    )
    return txt


def backup_menu_embeds(conf: GuildSettings, guild: discord.Guild) -> list[discord.Embed]:
    embeds = []
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
        conf.auto_backup_interval_hours, f"{conf.last_backup_f} ({conf.last_backup_r})"
    )
    title = _("Cartographer Backups for {}").format(guild.name)
    pages = len(conf.backups)
    for index, backup in enumerate(conf.backups):
        txt = backup_str(backup)
        embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
        embed.add_field(name=s_name, value=settings, inline=False)
        embed.add_field(name=c_name, value=controls, inline=False)
        embed.set_footer(text=_("Page {}").format(f"{index + 1}/{pages}"))
        embeds.append(embed)
    if not embeds:
        txt = _("There are no backups for this server yet!")
        embed = discord.Embed(title=title, description=txt, color=discord.Color.blue())
        embed.add_field(name=s_name, value=settings, inline=False)
        embed.add_field(name=c_name, value=controls, inline=False)
        embeds.append(embed)
    return embeds
