from datetime import datetime

import discord
import pytz
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from ..models import GuildSettings


async def get_user_role_names(user: discord.Member, *args, **kwargs) -> str:
    if not user:
        return ""
    return humanize_list([role.name for role in user.roles if "everyone" not in role.name])


async def get_bot_created(bot: Red, conf: GuildSettings, *args, **kwargs) -> str:
    created = bot.user.created_at.astimezone(pytz.timezone(conf.timezone))
    return created.strftime("%A, %B %d, %Y at %I:%M %p %Z")


async def get_user_created(user: discord.Member, conf: GuildSettings, *args, **kwargs) -> str:
    if not user:
        return ""
    created = user.created_at.astimezone(pytz.timezone(conf.timezone))
    return created.strftime("%A, %B %d, %Y at %I:%M %p %Z")


async def get_user_joined(user: discord.Member, conf: GuildSettings, *args, **kwargs) -> str:
    if not user:
        return ""
    joined = user.joined_at.astimezone(pytz.timezone(conf.timezone))
    return joined.strftime("%A, %B %d, %Y at %I:%M %p %Z")


async def get_date(conf: GuildSettings, *args, **kwargs) -> str:
    now = datetime.now().astimezone(pytz.timezone(conf.timezone))
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")


FUNCTIONS = [
    # {
    #     "name": "get_user_role_names",
    #     "description": "Get a list of roles that the current discord user has",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "get_bot_created",
    #     "description": "Get the creation date of the bot running this cog",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "get_user_created",
    #     "description": "Get the creation date of the current discord users account",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "get_user_joined",
    #     "description": "Get the date that the current discord member joined the server",
    #     "parameters": {"type": "object", "properties": {}},
    # },
    # {
    #     "name": "get_date",
    #     "description": "Get todays date",
    #     "parameters": {"type": "object", "properties": {}},
    # },
]
FUNCTION_MAP = {
    # "get_user_role_names": get_user_role_names,
    # "get_bot_created": get_bot_created,
    # "get_user_created": get_user_created,
    # "get_user_joined": get_user_joined,
    # "get_date": get_date,
}
