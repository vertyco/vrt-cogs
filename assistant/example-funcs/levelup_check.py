# Check player level/stats
import json

import discord
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_number, humanize_timedelta


async def get_user_profile(bot: Red, user: discord.Member, *args, **kwargs):
    cog = bot.get_cog("LevelUp")
    if not cog:
        return "LevelUp cog not loaded!"
    if user.guild.id not in cog.data:
        return "The LevelUp cog has been loaded but doesnt have any data yet"
    cog.init_user(user.guild.id, str(user.id))
    user_data = cog.data[user.guild.id]["users"][str(user.id)].copy()
    extracted = {
        "experience points": user_data["xp"],
        "voice time": humanize_timedelta(seconds=int(user_data["voice"])),
        "message count": humanize_number(user_data["messages"]),
        "user level": user_data["level"],
        "prestige level": user_data["prestige"],
        "profile emoji": user_data["emoji"],
        "good noodle stars": humanize_number(user_data["stars"]),
    }
    return json.dumps(extracted)


schema = {
    "name": "get_user_profile",
    "description": "Use this function to get a user's level, xp, voice time and other stats about their profile.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
