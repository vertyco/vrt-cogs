import discord
from redbot.core.utils.chat_formatting import humanize_list


async def get_user_role_names(user: discord.Member, *args, **kwargs) -> str:
    return humanize_list([role.name for role in user.roles])


FUNCTIONS = [
    {
        "name": "get_user_role_names",
        "description": "Get a list of roles that the current discord user has",
        "parameters": {"type": "object", "properties": {}},
    }
]
FUNCTION_MAP = {"get_user_role_names": get_user_role_names}
