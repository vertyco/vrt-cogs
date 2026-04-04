import re
import sys
from pathlib import Path

import discord
import matplotlib
from rapidfuzz import fuzz

GuildChannel = (
    discord.ForumChannel
    | discord.TextChannel
    | discord.VoiceChannel
    | discord.Thread
    | discord.CategoryChannel
    | discord.abc.GuildChannel
)


def clean_name(name: str):
    """
    Cleans the function name to ensure it only contains alphanumeric characters,
    underscores, or dashes and is not longer than 64 characters.

    Args:
        name (str): The original function name to clean.

    Returns:
        str: The cleaned function name.
    """
    # Remove any characters that are not alphanumeric, underscore, or dash
    cleaned_name = re.sub(r"[^a-zA-Z0-9_-]", "", name)

    # Truncate the string to 64 characters if it's longer
    cleaned_name = cleaned_name[:64]

    return cleaned_name


def svg_font_dirs() -> list[str]:
    """Collect font directories available for SVG rendering."""
    dirs: list[str] = []
    # Always include matplotlib's bundled fonts (DejaVu + STIX)
    mpl_ttf = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
    if mpl_ttf.is_dir():
        dirs.append(str(mpl_ttf))
    # System font directories for additional variety
    if sys.platform.startswith("linux"):
        candidates = ["/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts")]
    elif sys.platform == "darwin":
        candidates = ["/Library/Fonts", "/System/Library/Fonts", str(Path.home() / "Library/Fonts")]
    else:
        candidates = []
    dirs.extend(d for d in candidates if Path(d).is_dir())
    return dirs


def find_channel(guild: discord.Guild, channel_name_or_id: str) -> GuildChannel | None:
    channel_name_or_id = str(channel_name_or_id).strip()
    channel_name_or_id = channel_name_or_id.replace("#", "").replace("<", "").replace(">", "").strip()
    if channel_name_or_id.isdigit():
        return guild.get_channel_or_thread(int(channel_name_or_id))
    valid_channels = set(
        list(guild.channels)
        + list(guild.threads)
        + list(guild.forums)
        + list(guild.categories)
        + list(guild.voice_channels)
    )
    if channel := discord.utils.get(valid_channels, name=channel_name_or_id):
        return channel
    cleaned_query = clean_name(channel_name_or_id)
    for channel in valid_channels:
        if clean_name(channel.name) == cleaned_query:
            return channel

    # Do fuzzy match for provided channel name
    matches: list[tuple[GuildChannel, int]] = []
    for channel in valid_channels:
        score = fuzz.ratio(clean_name(channel.name), cleaned_query)
        if score > 80:
            matches.append((channel, score))
    if matches:
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]
    return None
