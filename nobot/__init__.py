from .nobot import NoBot

___red_end_user_data_statement__ = (
    "."
)


def setup(bot):
    cog = NoBot(bot)
    bot.add_cog(cog)
