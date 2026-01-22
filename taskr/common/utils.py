import os
import random
import typing as t
from copy import copy
from datetime import datetime, timezone

import discord
import pytz
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redbot.core import commands
from redbot.core.bot import Red


def get_scheduler(start: bool = True) -> AsyncIOScheduler:
    if "TZ" not in os.environ:
        os.environ["TZ"] = "UTC"
    scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()})
    scheduler.configure(timezone=pytz.utc)
    if start:
        scheduler.start()
    return scheduler


async def invoke_command(
    bot: Red,
    author: discord.User,
    channel: discord.TextChannel | discord.Thread,
    command: str,
    prefix: t.Optional[str] = None,
    message: t.Optional[discord.Message] = None,
    invoke: t.Optional[bool] = True,
    **kwargs,
) -> commands.Context:
    """
    This is a slightly modified version of the function from AAA3A's 'AAA3A_utils' repo.
    Shoutout to AAA3A for this function :p
    https://github.com/AAA3A-AAA3A/AAA3A_utils/blob/cb454feeecc6d417cfbdfb4acbe63bf1b7078108/AAA3A_utils/cogsutils.py#L507
    """
    created_at = datetime.now(tz=timezone.utc)
    message_id = discord.utils.time_snowflake(created_at)
    if prefix == "/":  # For hybrid and slash commands.
        prefix = None
    if prefix is None:
        prefixes = await bot.get_valid_prefixes(guild=channel.guild)
        prefix = prefixes[0] if len(prefixes) < 3 else prefixes[2]
    old_content = f"{command}"
    content = f"{prefix}{old_content}"

    if message is None:
        author_dict = {
            "id": f"{author.id}",
            "username": author.display_name,
            "avatar": author.avatar,
            "avatar_decoration": None,
            "discriminator": f"{author.discriminator}",
            "public_flags": author.public_flags,
            "bot": author.bot,
        }
        data = {
            "id": message_id,
            "type": 0,
            "content": content,
            "channel_id": f"{channel.id}",
            "author": author_dict,
            "attachments": [],
            "embeds": [],
            "mentions": [],
            "mention_roles": [],
            "pinned": False,
            "mention_everyone": False,
            "tts": False,
            "timestamp": str(created_at).replace(" ", "T") + "+00:00",
            "edited_timestamp": None,
            "flags": 0,
            "components": [],
            "referenced_message": None,
        }
        message: discord.Message = discord.Message(channel=channel, state=bot._connection, data=data)
    else:
        message = copy(message)
        message.author = author
        message.channel = channel
        message.content = content

    context: commands.Context = await bot.get_context(message)
    context.author = author
    context.guild = channel.guild
    context.channel = channel

    if (  # Red's Alias
        not context.valid
        and context.prefix is not None
        and (alias_cog := bot.get_cog("Alias")) is not None
        and not await bot.cog_disabled_in_guild(alias_cog, context.guild)
    ):
        alias_cog = t.cast(t.Any, alias_cog)  # Dynamic cog attributes
        alias = await alias_cog._aliases.get_alias(context.guild, context.invoked_with)
        if alias is not None:

            async def command_callback(__, ctx: commands.Context):
                await alias_cog.call_alias(ctx.message, ctx.prefix, alias)

            context.command = commands.command(name=command)(command_callback)
            context.command.cog = alias_cog
            context.command.params.clear()
            context.command.requires.ready_event.set()
    if (  # Red's CustomCommands
        not context.valid
        and context.prefix is not None
        and (custom_commands_cog := bot.get_cog("CustomCommands")) is not None
        and not await bot.cog_disabled_in_guild(custom_commands_cog, context.guild)
    ):
        custom_commands_cog = t.cast(t.Any, custom_commands_cog)  # Dynamic cog attributes
        try:
            raw_response, cooldowns = await custom_commands_cog.commandobj.get(
                message=message, command=context.invoked_with
            )
            if isinstance(raw_response, list):
                raw_response = random.choice(raw_response)
            elif isinstance(raw_response, str):
                pass
        except Exception:
            pass
        else:

            async def command_callback(__, ctx: commands.Context):
                # await custom_commands_cog.cc_callback(ctx)  # fake callback
                try:
                    if cooldowns:
                        custom_commands_cog.test_cooldowns(context, context.invoked_with, cooldowns)
                except Exception:
                    return
                del ctx.args[0]
                await custom_commands_cog.cc_command(*ctx.args, **ctx.kwargs, raw_response=raw_response)

            context.command = commands.command(name=command)(command_callback)
            context.command.cog = custom_commands_cog
            context.command.requires.ready_event.set()
            context.command.params = custom_commands_cog.prepare_args(raw_response)
    if (  # Phen/Lemon's Tags
        not context.valid
        and context.prefix is not None
        and (tags_cog := bot.get_cog("Tags")) is not None
        and not await bot.cog_disabled_in_guild(tags_cog, context.guild)
    ):
        tags_cog = t.cast(t.Any, tags_cog)  # Dynamic cog attributes
        tag = tags_cog.get_tag(context.guild, context.invoked_with, check_global=True)
        if tag is not None:
            message.content = f"{context.prefix}invoketag {command}"
            context: commands.Context = await bot.get_context(message)
            context.author = author
            context.guild = channel.guild
            context.channel = channel

    context.__dict__.update(**kwargs)
    if not invoke:
        return context
    if context.valid:
        await bot.invoke(context)
    return context


async def get_openai_token(bot: Red) -> str | None:
    """Retrieve OpenAI API token from Red's shared API tokens.

    Checks multiple possible key names and service name variations.

    Returns:
        The OpenAI API token if found, None otherwise.
    """
    # Try the standard openai service first
    keys = await bot.get_shared_api_tokens("openai")
    if keys:
        if token := keys.get("api_key") or keys.get("key"):
            return token

    # Fallback: search all tokens for services containing "openai"
    all_tokens = await bot.get_shared_api_tokens()
    for service_name, tokens in all_tokens.items():
        tokens: dict = tokens
        if "openai" in service_name.lower():
            if token := tokens.get("api_key") or tokens.get("key"):
                return token

    return None
