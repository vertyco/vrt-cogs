from .nobot import NoBot

___red_end_user_data_statement__ = (
    "This cog was made for educational purposes and is 100% up to the bot owner to use it according to the other bot's ToS that they choose to filter."
)


def setup(bot):
    cog = NoBot(bot)
    bot.add_cog(cog)
