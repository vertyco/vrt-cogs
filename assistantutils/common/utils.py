import re
import sys
from pathlib import Path
from typing import Literal

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

ChannelType = Literal["text", "voice", "stage", "forum", "category"]

CHANNEL_TYPE_ALIASES: dict[str, ChannelType] = {
    "text": "text",
    "text_channel": "text",
    "textchannel": "text",
    "voice": "voice",
    "voice_channel": "voice",
    "voicechannel": "voice",
    "stage": "stage",
    "stage_channel": "stage",
    "stagechannel": "stage",
    "forum": "forum",
    "forum_channel": "forum",
    "forumchannel": "forum",
    "category": "category",
    "category_channel": "category",
    "categorychannel": "category",
}


def normalize_discord_reference(value: str) -> str:
    return (
        str(value)
        .strip()
        .replace("<", "")
        .replace(">", "")
        .replace("#", "")
        .replace("@", "")
        .replace("&", "")
        .replace("!", "")
        .strip()
    )


def normalize_channel_type(channel_type: str) -> ChannelType | None:
    normalized = str(channel_type).strip().lower().replace("-", "_").replace(" ", "_")
    return CHANNEL_TYPE_ALIASES.get(normalized)


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
    channel_name_or_id = normalize_discord_reference(channel_name_or_id)
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


def find_category(guild: discord.Guild, category_name_or_id: str) -> discord.CategoryChannel | None:
    channel = find_channel(guild, category_name_or_id)
    if isinstance(channel, discord.CategoryChannel):
        return channel
    return None


def find_member(guild: discord.Guild, user_name_or_id: str) -> discord.Member | None:
    user_name_or_id = normalize_discord_reference(user_name_or_id)
    if not user_name_or_id:
        return None
    if user_name_or_id.isdigit():
        return guild.get_member(int(user_name_or_id))

    lowered_query = user_name_or_id.lower()
    if member := discord.utils.get(guild.members, name=user_name_or_id):
        return member
    if member := discord.utils.get(guild.members, display_name=user_name_or_id):
        return member

    cleaned_query = clean_name(lowered_query)
    for member in guild.members:
        if clean_name(member.name.lower()) == cleaned_query:
            return member
        if clean_name(member.display_name.lower()) == cleaned_query:
            return member

    matches: list[tuple[discord.Member, int]] = []
    for member in guild.members:
        scores = [
            fuzz.ratio(clean_name(member.name.lower()), cleaned_query),
            fuzz.ratio(member.name.lower(), lowered_query),
        ]
        if member.display_name != member.name:
            scores.extend(
                [
                    fuzz.ratio(clean_name(member.display_name.lower()), cleaned_query),
                    fuzz.ratio(member.display_name.lower(), lowered_query),
                ]
            )
        best_score = max(scores)
        if best_score > 80:
            matches.append((member, best_score))

    if matches:
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]
    return None


def find_role(guild: discord.Guild, role_name_or_id: str) -> discord.Role | None:
    role_name_or_id = normalize_discord_reference(role_name_or_id)
    if not role_name_or_id:
        return None
    if role_name_or_id.isdigit():
        return guild.get_role(int(role_name_or_id))

    lowered_query = role_name_or_id.lower()
    if role := discord.utils.get(guild.roles, name=role_name_or_id):
        return role

    cleaned_query = clean_name(lowered_query)
    for role in guild.roles:
        if clean_name(role.name.lower()) == cleaned_query:
            return role

    matches: list[tuple[discord.Role, int]] = []
    for role in guild.roles:
        scores = [
            fuzz.ratio(clean_name(role.name.lower()), cleaned_query),
            fuzz.ratio(role.name.lower(), lowered_query),
        ]
        best_score = max(scores)
        if best_score > 80:
            matches.append((role, best_score))

    if matches:
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]
    return None


def split_permission_overwrite(overwrite: discord.PermissionOverwrite) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    denied: list[str] = []
    for permission_name, value in overwrite:
        if value is True:
            allowed.append(permission_name)
        elif value is False:
            denied.append(permission_name)
    return allowed, denied
