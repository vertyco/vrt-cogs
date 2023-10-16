import discord


def get_bot_percentage(guild: discord.Guild) -> int:
    bots = sum(1 for i in guild.members if i.bot)
    return round((bots / (guild.member_count or len(guild.members))) * 100)
