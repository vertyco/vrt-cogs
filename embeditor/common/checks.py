import discord
from redbot.core.bot import Red


async def edit_error(interaction: discord.Interaction, message: discord.Message) -> str | None:
    """Return an error string if the user cannot edit this message, else None."""
    if not interaction.guild:
        return "This command can only be used in a server."
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return "You must be in the server to use this command."
    bot: Red = interaction.client
    if message.author.id != bot.user.id:
        return "I can only edit messages that I sent myself."
    if member.id not in bot.owner_ids and not await bot.is_admin(member):
        return "You must be an admin to edit my messages."
    if not message.channel.permissions_for(member).manage_messages:
        return "You need the manage messages permission in this channel to edit my messages here."
    return None
