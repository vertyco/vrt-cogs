import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import List, Optional, Tuple, Union

import discord
from redbot.core import commands, version_info
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

log = logging.getLogger("red.vrt.assistant.utils")


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
            await ctx.send("Canceled")
            return None
        return message
    except asyncio.TimeoutError:
        return None


async def can_use(message: discord.Message, blacklist: list, respond: bool = True) -> bool:
    allowed = True
    if message.author.id in blacklist:
        if respond:
            await message.channel.send("You have been blacklisted from using this command!")
        allowed = False
    elif any(role.id in blacklist for role in message.author.roles):
        if respond:
            await message.channel.send("You have a blacklisted role and cannot use this command!")
        allowed = False
    elif message.channel.id in blacklist:
        if respond:
            await message.channel.send("You cannot use that command in this channel!")
        allowed = False
    elif message.channel.category_id in blacklist:
        if respond:
            await message.channel.send(
                "You cannot use that command in any channels under this category"
            )
        allowed = False
    return allowed


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
    content = re.sub(r"```(?:\w+)(.*?)```", "[Code Removed]", content, flags=re.DOTALL).strip()
    return re.sub(r"```(.*?)```", "[Code Removed]", content, flags=re.DOTALL).strip()


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


def compile_messages(messages: List[dict]) -> str:
    system = ""
    context = ""
    prompt = ""
    for message in messages:
        if message["role"] == "system":
            system += message["content"] + "\n"

    for message in messages:
        if message["role"] == "system":
            continue
        content = message["content"].strip()
        if "### Context:" in content:
            context += f"{content.replace('### Context:', '').strip()}\n"
        elif message["role"] == "user":
            prompt += f"### Prompt: {content}\n"
        elif message["role"] == "assistant":
            prompt += f"### Response: {content}\n"

    final = ""
    if system:
        final += f"### Instruction: {system}\n"
    if context:
        final += f"### Context: {context}\n"
    if prompt:
        final += prompt

    final += "\n### Response:"

    return final.strip()


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
    return {
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
    }
