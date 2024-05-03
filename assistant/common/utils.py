import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import List, Optional, Tuple, Union

import discord
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .constants import SUPPORTS_VISION
from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.utils")
_ = Translator("Assistant", __file__)


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


def get_attachments(message: discord.Message) -> List[discord.Attachment]:
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


async def wait_message(ctx: commands.Context) -> Optional[discord.Message]:
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
    if not message.embeds or message.content is not None:
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


def extract_code_blocks(content: str) -> List[str]:
    code_blocks = re.findall(r"```(?:\w+)(.*?)```", content, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r"```(.*?)```", content, re.DOTALL)
    return [block.strip() for block in code_blocks]


def extract_code_blocks_with_lang(content: str) -> List[Tuple[str, str]]:
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
    if "*args, **kwargs" not in code:
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
            missing = "- `properties` in **parameters**\n"
        if "required" in schema["parameters"].get("properties", []):
            missing += "- `required` key needs to be outside of properties!\n"
    return missing


def get_params(
    bot: Red,
    guild: discord.Guild,
    now: datetime,
    author: Optional[discord.Member],
    channel: Optional[Union[discord.TextChannel, discord.Thread, discord.ForumChannel]],
    extras: dict,
) -> dict:
    roles = [role for role in author.roles if "everyone" not in role.name] if author else []
    display_name = author.display_name if author else ""
    params = {
        **extras,
        "botname": bot.user.name,
        "timestamp": f"<t:{round(now.timestamp())}:F>",
        "day": now.strftime("%A"),
        "date": now.strftime("%B %d, %Y"),
        "time": now.strftime("%I:%M %p"),
        "timetz": now.strftime("%I:%M %p %Z"),
        "members": guild.member_count,
        "username": author.name if author else "",
        "user": author.name if author else "",
        "displayname": display_name,
        "datetime": str(datetime.now()),
        "roles": humanize_list([role.name for role in roles]),
        "rolementions": humanize_list([role.mention for role in roles]),
        "avatar": author.display_avatar.url if author else "",
        "owner": guild.owner.name,
        "servercreated": f"<t:{round(guild.created_at.timestamp())}:F>",
        "server": guild.name,
        "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "dpy": discord.__version__,
        "red": str(version_info),
        "cogs": humanize_list([bot.get_cog(cog).qualified_name for cog in bot.cogs]),
        "channelname": channel.name if channel else "",
        "channelmention": channel.mention if channel else "",
        "topic": channel.topic if channel and isinstance(channel, discord.TextChannel) else "",
        "userjoindate": author.joined_at.strftime("%B %d, %Y") if author else "[unknown date]",
        "userjointime": author.joined_at.strftime("%I:%M %p %Z") if author else "[unknown time]",
    }
    return params


async def ensure_supports_vision(messages: List[dict], conf: GuildSettings, user: Optional[discord.Member]) -> bool:
    """Make sure that if a conversation payload contains images that the model supports vision"""
    cleaned = False

    model = conf.get_user_model(user)
    if model in SUPPORTS_VISION:
        return cleaned

    if model not in SUPPORTS_VISION:
        for idx, message in enumerate(messages):
            if isinstance(message["content"], list):
                for obj in message["content"]:
                    if obj["type"] != "text":
                        continue
                    messages[idx]["content"] = obj["text"]
                    cleaned = True
                    break
    return cleaned


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
    if not response.tool_calls and not response.function_call:
        return False
    modified = False
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
    return modified


async def clean_responses(messages: List[dict]) -> bool:
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


async def ensure_tool_consistency(messages: List[dict]) -> bool:
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
            tool_response_ids.add(message["tool_call_id"])

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
        if message["tool_call_id"] not in tool_call_ids:
            indexes_to_purge.add(idx)
            log.info(f"Purging tool response with no tool call: {message}")

    if indexes_to_purge:
        purged = True
        for idx in sorted(indexes_to_purge, reverse=True):
            messages.pop(idx)

    return purged
