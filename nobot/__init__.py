from .nobot import NoBot

___red_end_user_data_statement__ = (
    "This cog only listens for other bots, it is probably not a good idea to use this on large or public bots."
)


def setup(bot):
    cog = NoBot(bot)
    bot.add_cog(cog)
