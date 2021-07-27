from .mctools import MCTools

___red_end_user_data_statement__ = (
    "This cog uses the api.mcsrvstat.us API and does not persistently store data about users."
)


def setup(bot):
    cog = MCTools(bot)
    bot.add_cog(cog)
