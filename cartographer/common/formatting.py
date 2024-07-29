import sys
import typing as t
from pathlib import Path

from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from .serializers import GuildBackup

_ = Translator("Cartographer", __file__)


def backup_str(filepath: Path) -> str:
    backup = GuildBackup.model_validate_json(filepath.read_text(encoding="utf-8"))
    total_messages = sum(len(channel.messages) for channel in backup.text_channels)
    voice_messages = sum(len(channel.messages) for channel in backup.voice_channels)
    txt = _(
        "## {}\n"
        "`Size:           `{}\n"
        "`Created:        `{}\n"
        "`AFK Channel:    `{}\n"
        "`AFK Timeout:    `{}\n"
        "`Verification:   `{}\n"
        "`Notifications:  `{}\n"
        "`Locale:         `{}\n"
        "`Emojis:         `{}\n"
        "`Stickers:       `{}\n"
        "`Role Count:     `{}\n"
        "`Members Saved:  `{}\n"
        "`Categories:     `{}\n"
        "`Text Channels:  `{} ({} messages)\n"
        "`Voice Channels: `{} ({} messages)\n"
        "`Forums:         `{}\n"
    ).format(
        backup.name,
        humanize_size(filepath.stat().st_size),
        f"{backup.created_fmt('f')} ({backup.created_fmt('R')})",
        backup.afk_channel.id if backup.afk_channel else None,
        backup.afk_timeout,
        backup.verification_level,
        backup.default_notifications,
        backup.preferred_locale,
        len(backup.emojis),
        len(backup.stickers),
        len(backup.roles),
        humanize_number(len(backup.members)),
        len(backup.categories),
        len(backup.text_channels),
        humanize_number(total_messages),
        len(backup.voice_channels),
        humanize_number(voice_messages),
        len(backup.forums),
    )
    return txt


def deep_getsizeof(obj: t.Any, seen: t.Optional[set] = None) -> int:
    """Recursively finds the size of an object in memory"""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return 0
    # Mark object as seen
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        # If the object is a dictionary, recursively add the size of keys and values
        size += sum([deep_getsizeof(k, seen) + deep_getsizeof(v, seen) for k, v in obj.items()])
    elif hasattr(obj, "__dict__"):
        # If the object has a __dict__, it's likely an object. Find size of its dictionary
        size += deep_getsizeof(obj.__dict__, seen)
    elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
        # If the object is an iterable (not a string or bytes), iterate through its items
        size += sum([deep_getsizeof(i, seen) for i in obj])
    elif hasattr(obj, "model_dump"):
        # If the object is a pydantic model, get the size of its dictionary
        size += deep_getsizeof(obj.model_dump(), seen)
    elif hasattr(obj, "dict"):
        # If the object is a pydantic model, get the size of its dictionary
        size += deep_getsizeof(obj.dict(), seen)
    return size


def humanize_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1024.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1024.0
    return "{0:.1f}{1}".format(num, "YB")
