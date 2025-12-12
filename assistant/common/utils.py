import asyncio
import logging
import re
import sys
import typing as t
from datetime import datetime

import discord
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .constants import NO_DEVELOPER_ROLE, SUPPORTS_VISION
from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.utils")
_ = Translator("Assistant", __file__)


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
            missing = "- `properties` in **parameters**\n"
        if "required" in schema["parameters"].get("properties", []):
            missing += "- `required` key needs to be outside of properties!\n"
    return missing


def get_params(
    bot: Red,
    guild: discord.Guild,
    now: datetime,
    author: t.Optional[discord.Member],
    channel: t.Optional[discord.TextChannel | discord.Thread | discord.ForumChannel],
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


async def ensure_message_compatibility(
    messages: list[dict],
    conf: GuildSettings,
    user: t.Optional[discord.Member],
    endpoint_override: t.Optional[str] = None,
    is_ollama_endpoint: t.Optional[bool] = True,
) -> bool:
    cleaned = False

    model = conf.get_chat_model(endpoint_override, user, None, is_ollama_endpoint)
    if model not in NO_DEVELOPER_ROLE:
        return cleaned

    # Change all system messages to user messages
    for idx, message in enumerate(messages):
        if message["role"] in ["system", "developer"]:
            messages[idx]["role"] = "user"
            cleaned = True

    return cleaned


async def ensure_supports_vision(
    messages: list[dict],
    conf: GuildSettings,
    user: t.Optional[discord.Member],
    endpoint_override: t.Optional[str] = None,
    is_ollama_endpoint: t.Optional[bool] = True,
) -> bool:
    """Make sure that if a conversation payload contains images that the model supports vision"""
    cleaned = False

    model = conf.get_chat_model(endpoint_override, user, None, is_ollama_endpoint)
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


async def purge_images(messages: list[dict]) -> bool:
    """Remove all images sourced from URLs from the message payload"""
    cleaned = False
    for idx, message in enumerate(list(messages)):
        if isinstance(message["content"], list):
            for iidx, obj in enumerate(message["content"]):
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


def convert_openai_to_ollama_tool(openai_schema: dict) -> dict:
    """Convert single OpenAI function schema to Ollama tool format."""
    required_fields = ("name", "description", "parameters")
    missing = [field for field in required_fields if field not in openai_schema]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return {"type": "function", "function": openai_schema}


def is_core_tool(function_name: str) -> bool:
    """Check if function is a core tool supported by Ollama."""
    core_tools = {
        "create_memory",
        "search_memories",
        "edit_memory",
        "list_memories",
        "search_web_brave",
    }
    return function_name.lower() in core_tools if function_name else False


def validate_ollama_tool_schema(tool: dict) -> tuple[bool, str]:
    """Validate Ollama tool schema structure."""
    if not isinstance(tool, dict):
        return False, "Tool payload must be a dict"
    if tool.get("type") != "function":
        return False, "Tool type must be 'function'"

    func = tool.get("function")
    if not isinstance(func, dict):
        return False, "Tool missing function definition"

    for key in ("name", "description", "parameters"):
        if key not in func:
            return False, f"Missing function field: {key}"

    params = func.get("parameters")
    if not isinstance(params, dict):
        return False, "Parameters must be a dict"
    if "type" not in params:
        return False, "Parameters missing type"
    if "properties" not in params:
        return False, "Parameters missing properties"

    properties = params.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            if "enum" in prop_schema and not isinstance(prop_schema["enum"], list):
                return False, f"Enum for property '{prop_name}' must be a list"

    required = params.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            return False, "Parameters.required must be a list of strings"

    return True, ""


def convert_functions_to_ollama_tools(openai_schemas: list[dict], core_only: bool = True) -> list[dict]:
    """Convert list of OpenAI schemas to Ollama tools, optionally filtering."""
    converted_tools = []
    for schema in openai_schemas:
        if core_only and not is_core_tool(schema.get("name", "")):
            continue

        try:
            tool = convert_openai_to_ollama_tool(schema)
        except ValueError as exc:
            log.warning("Skipping tool conversion: %s", exc)
            continue

        valid, reason = validate_ollama_tool_schema(tool)
        if not valid:
            log.warning("Skipping invalid Ollama tool for %s: %s", schema.get("name", "<unknown>"), reason)
            continue

        converted_tools.append(tool)

    # Integration note: DB.prep_functions will call this when using an Ollama endpoint override,
    # filtering to core tools and returning the converted payloads.
    return converted_tools
