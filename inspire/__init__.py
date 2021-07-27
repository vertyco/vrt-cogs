from .inspire import Inspire

___red_end_user_data_statement__ = (
    "This cog uses the zenquotes.io API and does not persistently store data about users."
)


def setup(bot):
    cog = Inspire(bot)
    bot.add_cog(cog)
