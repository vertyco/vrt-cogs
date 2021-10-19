from .xtools import XTools

___red_end_user_data_statement__ = (
    "This cog uses Microsofts XSAPI endpoints to pull data. It stores your (the bot owner's) client ID and secret for the Azure application for authorization."
)


def setup(bot):
    cog = XTools(bot)
    bot.add_cog(cog)
