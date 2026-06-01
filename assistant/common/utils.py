import asyncio
import logging
import re
import sys
import typing as t
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from tempfile import NamedTemporaryFile

import discord
import pandas as pd
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta

from .constants import NO_DEVELOPER_ROLE, SUPPORTS_VISION
from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.utils")
_ = Translator("Assistant", __file__)

# Cap trigger pattern length so the translated regex stays cheap to evaluate.
MAX_TRIGGER_LEN = 200


def wildcard_to_regex(pattern: str) -> str:
    """Translate a simple wildcard trigger phrase into a SAFE, linear regex string.

    Only ``*`` (any run of characters, including none) is honored as a metacharacter;
    everything else is escaped via ``re.escape``. This means staff of a public bot can
    paste arbitrary text — including real regex like ``(a+)+`` — and it can never inject
    catastrophic backtracking (ReDoS): the output contains only literals, ``.*`` and ``\\b``,
    which the engine matches in linear time, so no multiprocessing timeout guard is needed.

    A phrase with no leading/trailing ``*`` is anchored on word boundaries, so ``idiot``
    hits the whole word ``idiot`` but not ``idiotic``. Add ``*`` to loosen it:
    ``idiot*`` (prefix), ``*idiot`` (suffix), ``*idiot*`` (substring anywhere).
    """
    collapsed = re.sub(r"\*+", "*", pattern.strip())[:MAX_TRIGGER_LEN]
    body = re.escape(collapsed).replace(r"\*", ".*")
    prefix = "" if collapsed.startswith("*") else r"\b"
    suffix = "" if collapsed.endswith("*") else r"\b"
    return f"{prefix}{body}{suffix}"


def get_activity_type_label(activity: object) -> str:
    activity_type = getattr(activity, "type", None)
    labels = {
        discord.ActivityType.playing: _("Playing"),
        discord.ActivityType.streaming: _("Streaming"),
        discord.ActivityType.listening: _("Listening"),
        discord.ActivityType.watching: _("Watching"),
        discord.ActivityType.custom: _("Custom status"),
        discord.ActivityType.competing: _("Competing"),
    }
    if activity_type in labels:
        return labels[activity_type]
    name = getattr(activity_type, "name", "")
    return name.replace("_", " ").title() if name else _("Activity")


def join_activity_parts(*parts: object) -> list[str]:
    rendered: list[str] = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if not text or text == "None" or text in rendered:
            continue
        rendered.append(text)
    return rendered


def format_activity(activity: object) -> str:
    if isinstance(activity, discord.Spotify):
        title = activity.title or activity.name or _("Unknown track")
        artist = activity.artist or _("Unknown artist")
        album = activity.album
        parts = join_activity_parts(
            title,
            _("by {artist}").format(artist=artist),
            _("album: {album}").format(album=album) if album else None,
        )
        return _("Listening to Spotify: {details}").format(details=" | ".join(parts))

    if isinstance(activity, discord.CustomActivity):
        status = str(activity).strip()
        return _("Custom status: {status}").format(status=status) if status and status != "None" else _("Custom status")

    if isinstance(activity, discord.Streaming):
        parts = join_activity_parts(
            activity.name or activity.details,
            _("game: {game}").format(game=activity.game) if activity.game else None,
            _("platform: {platform}").format(platform=activity.platform) if activity.platform else None,
        )
        return _("Streaming: {details}").format(details=" | ".join(parts)) if parts else _("Streaming")

    if isinstance(activity, discord.Game):
        parts = join_activity_parts(
            activity.name,
            _("platform: {platform}").format(platform=activity.platform) if activity.platform else None,
        )
        return _("Playing: {details}").format(details=" | ".join(parts)) if parts else _("Playing")

    if isinstance(activity, discord.Activity):
        label = get_activity_type_label(activity)
        buttons = humanize_list(activity.buttons) if activity.buttons else ""
        parts = join_activity_parts(
            activity.name,
            activity.details if activity.details != activity.name else None,
            activity.state,
            _("platform: {platform}").format(platform=activity.platform) if activity.platform else None,
            _("buttons: {buttons}").format(buttons=buttons) if buttons else None,
        )
        return f"{label}: {' | '.join(parts)}" if parts else label

    label = get_activity_type_label(activity)
    parts = join_activity_parts(str(activity))
    return f"{label}: {' | '.join(parts)}" if parts else label


def format_activities(author: t.Optional[discord.Member]) -> str:
    if not author or not author.activities:
        return ""

    rendered = []
    for activity in author.activities:
        if activity is None:
            continue
        formatted = format_activity(activity)
        if formatted and formatted not in rendered:
            rendered.append(formatted)

    return " ; ".join(rendered)


def is_question(text: str):
    text_stripped = text.strip()

    # Quick check for question mark - most reliable indicator
    if text_stripped.endswith("?"):
        return True

    lower_text = text_stripped.lower()

    # More statement indicators that suggest not a question
    statement_indicators = [
        "i think",
        "i believe",
        "i know",
        "i understand",
        "i guess",
        "i assume",
        "therefore",
        "thus",
        "hence",
        "consequently",
        "because",
        "since",
        "as a result",
        "so",
        "i want",
        "i need",
        "i would like",
        "please",
        "maybe",
        "perhaps",
        "possibly",
        "it seems",
        "it appears",
        "apparently",
    ]

    if any(indicator in lower_text for indicator in statement_indicators):
        return False

    # Stricter patterns for question starts that require proper sentence structure
    start_patterns = [
        r"^(what|who|when|where|why|how|which)\s+(is|are|was|were|do|does|did|would|could|should|can|will|have|has)\s+\w+",
        r"^(do|does|did|would|could|should|can|will|have|has)\s+(you|we|they|it|he|she|the)\s+\w+",
        r"^(isn't|aren't|won't|wouldn't|couldn't|shouldn't|can't|haven't|hasn't)\s+(it|there|that|this|he|she|they)\s+\w+",
        r"^(isnt|arent|wont|wouldnt|couldnt|shouldnt|cant|havent|hasnt)\s+(it|there|that|this|he|she|they)\s+\w+",
    ]

    if any(re.match(pattern, lower_text) for pattern in start_patterns):
        return True

    # Specific question patterns that require clear question structure
    question_patterns = [
        r"\b(can|could|would|will)\s+you\s+(please\s+)?(tell|help|explain|show|give)\b",
        r"\b(do|does|did)\s+(you|anyone|somebody|anybody)\s+(know|think|have|want)\b",
        r"\b(is|are)\s+there\s+(any|some|many|much)\b",
        r"\b(what|who|when|where|why|how)\s+(exactly|specifically|do|does|would|could|should)\s+\w+",
        r"\bhas\s+anyone\s+(ever|here|tried|seen|heard)\b",
    ]

    # Require at least one clear question pattern
    return any(re.search(pattern, lower_text) for pattern in question_patterns)


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


def get_attachments(message: discord.Message) -> list[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [a for a in message.reference.resolved.attachments]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments


async def wait_message(ctx: commands.Context) -> t.Optional[discord.Message]:
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        message = await ctx.bot.wait_for("message", timeout=600, check=check)
        if message.content == "cancel":
            await ctx.send(_("Canceled"))
            return None
        return message
    except asyncio.TimeoutError:
        return None


async def can_use(message: discord.Message, blacklist: list, respond: bool = True) -> bool:
    if message.webhook_id is not None:
        return True
    allowed = True
    if message.author.id in blacklist:
        if respond:
            await message.channel.send(_("You have been blacklisted from using this command!"))
        allowed = False
    elif any(role.id in blacklist for role in message.author.roles):
        if respond:
            await message.channel.send(_("You have a blacklisted role and cannot use this command!"))
        allowed = False
    elif message.channel.id in blacklist:
        if respond:
            await message.channel.send(_("You cannot use that command in this channel!"))
        allowed = False
    elif message.channel.category_id in blacklist:
        if respond:
            await message.channel.send(_("You cannot use that command in any channels under this category"))
        allowed = False
    return allowed


def embed_to_content(message: discord.Message) -> None:
    if not message.embeds and not message.content:
        return
    extracted = ""
    embed = message.embeds[0]
    if title := embed.title:
        extracted += f"# {title}\n"
    if desc := embed.description:
        extracted += f"{desc}\n"
    for field in embed.fields:
        extracted += f"## {field.name}\n{field.value}\n"
    message.content = extracted


def extract_code_blocks(content: str) -> list[str]:
    code_blocks = re.findall(r"```(?:\w+)(.*?)```", content, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r"```(.*?)```", content, re.DOTALL)
    return [block.strip() for block in code_blocks]


def extract_code_blocks_with_lang(content: str) -> list[tuple[str, str]]:
    code_blocks = re.findall(r"```(\w+)(.*?)```", content, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r"```(.*?)```", content, re.DOTALL)
        return [("", block.strip()) for block in code_blocks]
    return [(block[0], block[1].strip()) for block in code_blocks]


def remove_code_blocks(content: str) -> str:
    content = re.sub(r"```(?:\w+)(.*?)```", _("[Code Removed]"), content, flags=re.DOTALL).strip()
    return re.sub(r"```(.*?)```", _("[Code Removed]"), content, flags=re.DOTALL).strip()


def code_string_valid(code: str) -> bool:
    # True if function is good
    if "*args" not in code or "**kwargs" not in code:
        return False
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def json_schema_invalid(schema: dict) -> str:
    # String will be empty if function is good
    missing = ""
    if "name" not in schema:
        missing += "- `name`\n"
    if "description" not in schema:
        missing += "- `description`\n"
    if "parameters" not in schema:
        missing += "- `parameters`\n"
    if "parameters" in schema:
        if "type" not in schema["parameters"]:
            missing += "- `type` in **parameters**\n"
        if "properties" not in schema["parameters"]:
            missing += "- `properties` in **parameters**\n"
        if "required" in schema["parameters"]:
            if not isinstance(schema["parameters"]["required"], list):
                missing += "- `required` must be a list in **parameters**\n"
    return missing


# ---------------------------------------------------------------------------
# Prompt template variable groupings for cache-safe context handling.
#
# DYNAMIC_VARIABLE_GROUPS: Variables that change per-request or per-user
# (time, user balance, activities, etc.). If injected into the system/initial
# prompt, they break provider-side prompt caching. They can optionally be moved
# into a trailing system-context message to keep the prefix stable.
#
# STABLE_VARIABLE_GROUPS: Variables that are cache-safe and do not change
# per-request (user profile, bot info, server info, etc.). These are always
# substituted into the prompt. Admins can ADDITIONALLY surface them in the
# floating context block via `[p]floatingcontext`.
# ---------------------------------------------------------------------------
DYNAMIC_VARIABLE_GROUPS: t.Dict[str, t.List[str]] = {
    "time": ["timestamp", "day", "date", "time", "timetz", "datetime"],
    "balance": ["balance"],
    "activities": ["activities"],
    "session": ["last_interaction"],
}

# Stable / cache-safe builtin variables. The cog hard-codes these as stable -
# they are always substituted into the prompt regardless of any admin toggle.
# Admins can ADDITIONALLY surface them in the floating context block via
# `[p]floatingcontext` (useful e.g. when they want the model to see the
# variable's value as a reminder without writing a placeholder into the prompt).
STABLE_VARIABLE_GROUPS: t.Dict[str, t.List[str]] = {
    "bot": ["botname", "model", "modelinfo", "prefix", "prefixes", "botowner"],
    "server": ["server", "servercreated", "owner"],
    "channel": ["channelname", "channelmention", "topic"],
    "bank": ["banktype", "currency", "bank"],
    "user_info": [
        "username",
        "displayname",
        "user",
        "roles",
        "rolementions",
        "avatar",
        "userjoindate",
        "userjointime",
    ],
    "system": ["py", "dpy", "red", "cogs", "uptime", "members"],
}

DYNAMIC_VARIABLE_NAMES: t.Set[str] = {name for names in DYNAMIC_VARIABLE_GROUPS.values() for name in names}
STABLE_VARIABLE_NAMES: t.Set[str] = {name for names in STABLE_VARIABLE_GROUPS.values() for name in names}

DYNAMIC_VARIABLE_GROUP_LABELS: t.Dict[str, str] = {
    "time": "Dynamic - Time & Date",
    "balance": "Dynamic - Balance",
    "activities": "Dynamic - Activities",
    "session": "Dynamic - Session",
}

STABLE_VARIABLE_GROUP_LABELS: t.Dict[str, str] = {
    "bot": "Stable - Bot",
    "server": "Stable - Server",
    "channel": "Stable - Channel",
    "bank": "Stable - Bank",
    "user_info": "Stable - User Info",
    "system": "Stable - System",
}

# Self-encapsulated narrative templates for the cache-safe trailing context
# block. The model should be able to understand each variable's meaning
# without the admin having to write a prompt referencing it - toggling a
# dynamic variable on is enough. ``{value}`` is replaced with the rendered
# variable value at runtime.
#
# Variables not listed here fall back to a generic ``{name}: {value}`` line.
VARIABLE_NARRATIVES: t.Dict[str, str] = {
    # Dynamic
    "timestamp": "The current timestamp is {value}.",
    "day": "Today is {value}.",
    "date": "The current date is {value}.",
    "time": "The current local time is {value}.",
    "timetz": "The current local time (with timezone) is {value}.",
    "datetime": "The current datetime is {value}.",
    "username": "You are talking to a user whose Discord username is {value}.",
    "displayname": "Their server display name is {value}.",
    "user": "Their handle is {value}.",
    "roles": "Their roles are: {value}.",
    "rolementions": "Their role mentions are: {value}.",
    "avatar": "Their avatar URL is {value}.",
    "userjoindate": "They joined this server on {value}.",
    "userjointime": "Their join time was {value}.",
    "balance": "Their current balance is {value}.",
    "activities": "They are currently: {value}.",
    "last_interaction": "Time since their last message in this conversation: {value}.",
    "uptime": "Bot uptime: {value}.",
    "members": "The server currently has {value} members.",
    "py": "Python runtime version: {value}.",
    "dpy": "discord.py version: {value}.",
    "red": "Red-DiscordBot version: {value}.",
    "cogs": "Loaded cogs: {value}.",
    # Stable
    "botname": "Your name is {value}.",
    "model": "You are running on the {value} model.",
    "modelinfo": "Model info:\n{value}",
    "prefix": "The bot's primary command prefix is {value}.",
    "prefixes": "All valid command prefixes: {value}.",
    "botowner": "The bot is owned by {value}.",
    "server": "You are in the {value} Discord server.",
    "servercreated": "The server was created on {value}.",
    "owner": "The server is owned by {value}.",
    "channelname": "The current channel name is {value}.",
    "channelmention": "The current channel mention is {value}.",
    "topic": "The current channel's topic is: {value}.",
    "banktype": "Bank type: {value}.",
    "currency": "The currency name is {value}.",
    "bank": "The bank name is {value}.",
}

# Back-compat alias (still imported by chat.py)
DYNAMIC_VARIABLE_NARRATIVES = VARIABLE_NARRATIVES


def format_template(text: str, params: dict) -> str:
    """Substitute ``{key}`` placeholders in ``text`` from ``params``.

    Uses ``str.replace`` rather than ``str.format`` so prompts containing
    code blocks with curly braces don't raise ``KeyError``.
    """
    for key, value in params.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def get_base_params(
    bot: Red,
    guild: discord.Guild,
    author: t.Optional[discord.Member],
    channel: t.Optional[discord.TextChannel | discord.Thread | discord.ForumChannel],
    extras: dict,
    model: str,
    modelinfo: str,
    prefix: str,
    prefixes: str,
) -> dict:
    """Stable, cache-safe prompt template variables.

    These values do not change per-request and are safe to inject into the
    `system_prompt` and `initial_prompt` without invalidating provider-side
    prompt caching.

    The `extras` dict is expected to only contain stable values (e.g. bank
    type, currency, bank name). Per-user balances belong in
    `get_dynamic_params()`.
    """
    owner_ids = list(bot.owner_ids)

    bot_owners = []
    for owner_id in owner_ids:
        owner = bot.get_user(owner_id) or guild.get_member(owner_id)
        if owner is None:
            continue
        bot_owners.append(owner.display_name)

    botowner = humanize_list(bot_owners) if bot_owners else guild.owner.name

    params = {
        **extras,
        "botname": bot.user.name,
        "model": model,
        "modelinfo": modelinfo,
        "prefix": prefix,
        "prefixes": prefixes,
        "owner": guild.owner.name,
        "botowner": botowner,
        "servercreated": f"<t:{round(guild.created_at.timestamp())}:F>",
        "server": guild.name,
        "channelname": channel.name if channel else "",
        "channelmention": channel.mention if channel else "",
        "topic": channel.topic if channel and isinstance(channel, discord.TextChannel) else "",
    }
    return params


def get_dynamic_params(
    bot: Red,
    guild: discord.Guild,
    now: datetime,
    author: t.Optional[discord.Member],
    dynamic_extras: t.Optional[dict] = None,
    last_interaction_seconds: t.Optional[float] = None,
) -> dict:
    """Per-request prompt template variables that change frequently.

    These values are kept separate from `get_base_params()` so callers can
    choose to inject them into a trailing system-context block (preserving
    prompt prefix stability for caching) rather than into the system/initial
    prompts.

    `dynamic_extras` may carry per-user dynamic values (such as the bank
    balance) that need to be grouped with the other dynamic variables.

    `last_interaction_seconds` is the elapsed time (in seconds) since the
    user's previous message in the active conversation. Pass ``None`` if
    this is the user's first message - the resulting value is the literal
    string "first message".
    """
    roles = [role for role in author.roles if "everyone" not in role.name] if author else []
    display_name = author.display_name if author else ""

    uptime_delta = datetime.now() - bot.uptime
    if uptime_delta.total_seconds() > 60:
        uptime = humanize_timedelta(timedelta=timedelta(minutes=round(uptime_delta.total_seconds() / 60)))
    else:
        uptime = humanize_timedelta(timedelta=uptime_delta)

    if last_interaction_seconds is None or last_interaction_seconds <= 0:
        last_interaction = "first message in this conversation"
    else:
        # Round to nearest minute for cache stability (sub-minute differences
        # would otherwise change the cache-safe block on every request).
        if last_interaction_seconds < 60:
            last_interaction = "less than a minute ago"
        else:
            rounded = timedelta(minutes=round(last_interaction_seconds / 60))
            last_interaction = humanize_timedelta(timedelta=rounded) + " ago"

    params: dict = {
        "timestamp": f"<t:{round(now.timestamp())}:F>",
        "day": now.strftime("%A"),
        "date": now.strftime("%B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "timetz": now.strftime("%I:%M %p %Z"),
        "datetime": str(datetime.now()),
        "members": guild.member_count,
        "username": author.name if author else "",
        "user": author.name if author else "",
        "displayname": display_name,
        "activities": format_activities(author),
        "roles": humanize_list([role.name for role in roles]),
        "rolementions": humanize_list([role.mention for role in roles]),
        "avatar": author.display_avatar.url if author else "",
        "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "dpy": discord.__version__,
        "red": str(version_info),
        "cogs": humanize_list([bot.get_cog(cog).qualified_name for cog in bot.cogs]),
        "userjoindate": author.joined_at.strftime("%B %d, %Y") if author else "[unknown date]",
        "userjointime": author.joined_at.strftime("%I:%M %p %Z") if author else "[unknown time]",
        "uptime": uptime,
        "last_interaction": last_interaction,
    }
    if dynamic_extras:
        params.update(dynamic_extras)
    return params


def get_params(
    bot: Red,
    guild: discord.Guild,
    now: datetime,
    author: t.Optional[discord.Member],
    channel: t.Optional[discord.TextChannel | discord.Thread | discord.ForumChannel],
    extras: dict,
    model: str,
    modelinfo: str,
    prefix: str,
    prefixes: str,
) -> dict:
    """Combined stable + dynamic prompt template variables.

    Convenience helper that merges `get_base_params()` with
    `get_dynamic_params()` for callers that don't care about cache-safe
    separation. Cache-aware code paths should call the two split helpers
    directly.
    """
    base = get_base_params(
        bot=bot,
        guild=guild,
        author=author,
        channel=channel,
        extras=extras,
        model=model,
        modelinfo=modelinfo,
        prefix=prefix,
        prefixes=prefixes,
    )
    dynamic = get_dynamic_params(bot=bot, guild=guild, now=now, author=author)
    base.update(dynamic)
    return base


async def ensure_message_compatibility(
    messages: list[dict],
    conf: GuildSettings,
    user: t.Optional[discord.Member],
) -> bool:
    cleaned = False

    model = conf.get_user_model(user)
    if model not in NO_DEVELOPER_ROLE:
        return cleaned

    # Change all system messages to user messages
    for idx, message in enumerate(messages):
        if message["role"] in ["system", "developer"]:
            messages[idx]["role"] = "user"
            cleaned = True

    return cleaned


async def ensure_supports_vision(messages: list[dict], conf: GuildSettings, user: t.Optional[discord.Member]) -> bool:
    """Make sure that if a conversation payload contains images that the model supports vision"""
    cleaned = False

    model = conf.get_user_model(user)
    supports_vision = model in SUPPORTS_VISION
    if supports_vision:
        return cleaned

    for idx, message in enumerate(messages):
        if isinstance(message["content"], list):
            for obj in message["content"]:
                if obj["type"] != "text":
                    continue
                messages[idx]["content"] = obj["text"]
                cleaned = True
                break
    return cleaned


async def purge_images(messages: list[dict]) -> bool:
    """Remove all images sourced from URLs from the message payload"""
    cleaned = False
    for idx in range(len(messages) - 1, -1, -1):
        message = messages[idx]
        if isinstance(message.get("content"), list):
            for iidx in range(len(message["content"]) - 1, -1, -1):
                obj = message["content"][iidx]
                if obj["type"] != "image_url":
                    continue
                if "data:image/jpeg;base64" in obj["image_url"]["url"]:
                    continue
                messages[idx]["content"].pop(iidx)
                cleaned = True
            if not messages[idx]["content"]:
                messages.pop(idx)
                cleaned = True
    return cleaned


def clean_text_content(text: str) -> tuple[str, bool]:
    """Remove invisible Unicode characters that AI detectors might flag.

    Returns: (cleaned_text, was_modified)
    """
    if not text:
        return text, False

    original_length = len(text)
    to_clean = [
        "\u200b",  # Zero-width space
        "\u200c",  # Zero-width non-joiner
        "\u200d",  # Zero-width joiner
        "\u2060",  # Invisible separator
        "\u2061",  # Invisible times
        "\u00ad",  # Soft hyphen
        "\u180e",  # Mongolian vowel separator
        "\u200b-",  # Zero-width space (non-breaking)
        "\u200f",  # Right-to-left mark
        "\u202a-",  # Left-to-right embedding
        "\u202e",  # Right-to-left embedding
        "\u2066-",  # Left-to-right override
        "\u2069",  # Pop directional formatting
        "\ufeff",  # Zero-width no-break space (BOM)
    ]
    for char in to_clean:
        text = text.replace(char, "")
    return text, len(text) != original_length


async def clean_response(response: ChatCompletionMessage) -> bool:
    """Clean the model response since its stupid and breaks itself

    Example
    ```
    {
        "id": "call_JhCP7H8Mv768cXbFiupO4lxQ",
        "function": {
          "arguments": "{\"panel_name\":\"pve\",\"answer1\":\"Unknown\",\"answer2\":\"I am experiencing an issue where the game is not allowing me to demolish a structure even though it says I can. It seems to be a bug.\",\"answer3\":\"N/A\",\"answer4\":\"N/A\",\"answer5\":\"N/A\"}",
          "name": "multi_tool_use.create_ticket_for_user"
        },
        "type": "function"
      }
    ```
    Will return: Bad Request Error(400): 'multi_tool_use.create_ticket_for_user' does not match '^[a-zA-Z0-9_-]{1,64}$' - 'messages.16.tool_calls.0.function.name'
    """
    modified = False

    # Clean function/tool names
    if response.tool_calls:
        for tool_call in response.tool_calls:
            original = tool_call.function.name
            cleaned = clean_name(original)
            if cleaned != original:
                tool_call.function.name = cleaned
                modified = True
    elif response.function_call:
        original = response.function_call.name
        cleaned = clean_name(original)
        if cleaned != original:
            response.function_call.name = cleaned
            modified = True

    # Clean content from invisible Unicode characters
    if response.content:
        if isinstance(response.content, str):
            cleaned_content, was_cleaned = clean_text_content(response.content)
            if was_cleaned:
                response.content = cleaned_content
                modified = True
        elif isinstance(response.content, list):
            # Handle multi-modal content (list of content items)
            for item in response.content:
                if item.get("type") == "text" and "text" in item:
                    cleaned_text, was_cleaned = clean_text_content(item["text"])
                    if was_cleaned:
                        item["text"] = cleaned_text
                        modified = True

    return modified


async def clean_responses(messages: list[dict]) -> bool:
    """Same as clean_response but cleans the whole message payload"""
    modified = False
    for message in messages:
        if "tool_calls" not in message:
            continue
        for tool_call in message["tool_calls"]:
            original = tool_call["function"]["name"]
            cleaned = clean_name(original)
            if cleaned != original:
                tool_call["function"]["name"] = cleaned
                modified = True
    return modified


async def ensure_tool_consistency(messages: list[dict]) -> bool:
    """
    Ensure all tool calls satisfy schema requirements, modifying the messages payload in-place.

    The "messages" param is a list of message payloads.

    ## Schema
    - Messages with they key "tool_calls" are calling a tool or tools.
    - The "tool_calls" value is a list of tool call dicts, each containing an "id" key that maps to a tool response
    - Messages with the role "tool" are tool call responses, each with a "tool_call_id" key that corresponds to a tool call "id"
    - More than one message can contain the same tool call id within the same conversation payload, which is a pain in the ass

    ## Tool Call Message Payload Example
    {
        "content": None,
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_HRdAUGb9xMM0jfqF2MajDMrA",
                "type": "function",
                "function": {
                    "arguments": {},
                    "name": "function_name",
                }
            }
        ]
    }

    ## Tool Response Message Payload Example
    {
        "role": "tool",
        "name": "function_name",
        "content": "The results of the function in text",
        "tool_call_id": "call_HRdAUGb9xMM0jfqF2MajDMrA",
    }

    ## Rules
    - A message payload can contain multiple tool calls, each with their own id
    - A message with tool_calls must be followed up with messages containing the role "tool" with the corresponding "tool_call_id"
    - All messages with "tool_calls" must be followed by messages with the tool responses
    - All tool call responses must have a preceeding tool call.

    Returns: boolean, True if any tool calls or responses were purged.
    """
    tool_call_ids = set()
    tool_response_ids = set()
    purged = False

    # First pass: Collect all tool call ids and tool response ids
    for message in messages:
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                # if tool_call["id"] in tool_call_ids:
                #     log.error("Message payload contains duplicate tool call ids!")
                tool_call_ids.add(tool_call["id"])
        elif message.get("role") == "tool":
            # if message["tool_call_id"] in tool_response_ids:
            #     log.error("Message payload contains duplicate tool response ids!")
            tool_response_ids.add(message.get("tool_call_id", "unknown"))

    if len(tool_call_ids) != len(tool_response_ids):
        log.warning(f"Collected {len(tool_call_ids)} tool call IDs and {len(tool_response_ids)} tool response IDs.")

    indexes_to_purge = set()
    # Second pass: Remove tool calls without a corresponding response
    for idx, message in enumerate(messages):
        if "tool_calls" in message:
            original_tool_calls = message["tool_calls"].copy()
            if len(original_tool_calls) == 1 and original_tool_calls[0]["id"] not in tool_response_ids:
                # Drop the message
                indexes_to_purge.add(idx)
                log.info(f"Purging tool call message with no response: {message}")
                purged = True
                continue
            message["tool_calls"] = [
                tool_call for tool_call in original_tool_calls if tool_call["id"] in tool_response_ids
            ]
            if len(message["tool_calls"]) != len(original_tool_calls):
                diff = len(original_tool_calls) - len(message["tool_calls"])
                purged = True
                log.info(f"Purged {diff} tool calls without response from message with tool calls: {message}")

    # Third pass: Remove tool responses without a preceding tool call
    for idx, message in enumerate(messages):
        if message["role"] != "tool":
            continue
        if message.get("tool_call_id", "unknown") not in tool_call_ids:
            indexes_to_purge.add(idx)
            log.info(f"Purging tool response with no tool call: {message}")

    if indexes_to_purge:
        purged = True
        for idx in sorted(indexes_to_purge, reverse=True):
            messages.pop(idx)

    return purged


# -------------------------------------------------------
# ------------------- DOCUMENT EXTRACTION ---------------
# -------------------------------------------------------
DOCUMENT_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".xls"]


def is_document(filename: str) -> bool:
    """Check if a file is a supported document type"""
    return any(filename.lower().endswith(ext) for ext in DOCUMENT_EXTENSIONS)


def get_file_extension(filename: str) -> str:
    """Get the lowercase file extension from a filename"""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


async def extract_document_text(filename: str, file_bytes: bytes) -> str:
    """Extract text content from PDF, Word, or Excel files

    Args:
        filename: The name of the file (used to determine type)
        file_bytes: The raw bytes of the file

    Returns:
        Extracted text content or error message
    """
    ext = get_file_extension(filename).lower()

    try:
        if ext == ".pdf":
            return await asyncio.to_thread(_extract_pdf_text, filename, file_bytes)
        elif ext in (".docx"):
            return await asyncio.to_thread(_extract_word_text, filename, file_bytes)
        elif ext in (".xlsx", ".xls"):
            return await asyncio.to_thread(_extract_excel_text, filename, file_bytes, ext)
        else:
            return f"[Unsupported document type: {ext}]"
    except Exception as e:
        log.error(f"Failed to extract text from {filename}", exc_info=e)
        return f"[Failed to read document: {filename} - {e}]"


def _extract_pdf_text(filename: str, file_bytes: bytes) -> str:
    """Extract text from PDF files using PyMuPDF"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.warning("PyMuPDF is not installed; PDF extraction is unavailable.")
        return "[PDF support not available - PyMuPDF not installed]"

    content = StringIO()
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.is_encrypted:
            return f"[Encrypted PDF '{filename}' is not supported]"

        # Check if PDF is scanned (image-based)
        sample_size = min(3, len(doc))
        scanned_count = sum(
            1 for i in range(sample_size) if (p := doc.load_page(i)).get_images() and len(p.get_text().strip()) < 100
        )
        if sample_size and scanned_count / sample_size > 0.5:
            return f"[Scanned PDF '{filename}' detected - OCR not supported]"

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_content = str(page.get_text())

            # Extract and format tables
            tables = page.find_tables()
            for table in tables:
                unformatted_table: str = page.get_text(clip=table.bbox)
                df = table.to_pandas()
                formatted_table = df.to_markdown(index=False)
                page_content = page_content.replace(unformatted_table, formatted_table)

            content.write(page_content + "\n\n")

    return content.getvalue()


def _extract_word_text(filename: str, file_bytes: bytes) -> str:
    """Extract text from Word documents using pypandoc"""
    try:
        import pypandoc
    except ImportError:
        log.warning("pypandoc is not installed; Word document extraction is unavailable.")
        return "[Word document support not available - pypandoc not installed]"

    content = StringIO()
    with NamedTemporaryFile(delete=True, suffix=".docx") as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        output = pypandoc.convert_file(
            source_file=tmp.name,
            to="plain",
            format="docx",
        )
        content.write(output)
    return content.getvalue()


def _extract_excel_text(filename: str, file_bytes: bytes, ext: str) -> str:
    """Extract text from Excel files using pandas"""
    content = StringIO()
    engine = "openpyxl" if ext == ".xlsx" else "xlrd"
    excel_file = BytesIO(file_bytes)
    try:
        sheets = pd.read_excel(excel_file, sheet_name=None, engine=engine)
    except ImportError as e:
        return f"[Excel support not available - {e}]"

    for sheet_name, df in sheets.items():
        content.write(f"\n\n===== Sheet: {sheet_name} =====\n\n")
        content.write(df.to_markdown(index=False))
        content.write("\n")
    return content.getvalue()
