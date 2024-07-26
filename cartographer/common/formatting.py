from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from .serializers import GuildBackup

_ = Translator("Cartographer", __file__)


def backup_str(backup: GuildBackup) -> str:
    total_messages = sum(len(channel.messages) for channel in backup.text_channels)
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
        "`Text Channels:  `{} ({} messages)\n"
        "`Voice Channels: `{}\n"
        "`Forums:         `{}\n"
    ).format(
        f"{backup.created_fmt('f')} ({backup.created_fmt('R')})",
        backup.name,
        backup.afk_channel.id if backup.afk_channel else None,
        backup.afk_timeout,
        backup.verification_level,
        backup.default_notifications,
        backup.preferred_locale,
        len(backup.roles),
        humanize_number(len(backup.members)),
        len(backup.categories),
        len(backup.text_channels),
        humanize_number(total_messages),
        len(backup.voice_channels),
        len(backup.forums),
    )
    return txt
