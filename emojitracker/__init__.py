from .emojitracker import EmojiTracker

___red_end_user_data_statement__ = (
    "This cog stores Discord ID's."
)


async def setup(bot):
    cog = EmojiTracker(bot)
    bot.add_cog(cog)
