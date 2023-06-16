import discord
from redbot.core import bank


async def get_member_balance(guild: discord.Guild, name: str, *args, **kwargs) -> str:
    user = guild.get_member_named(name)
    if not user:
        return "Could not find that user"
    bal = await bank.get_balance(user)
    return f"{bal} VC"


schema = {
    "name": "get_member_balance",
    "description": "Get a member's VC balance by name",
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "the name of the member"}},
        "required": ["name"],
    },
}
