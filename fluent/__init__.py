from .fluent import Fluent

___red_end_user_data_statement__ = (
    "This cog does not persistently store data about users. This cog uses google's free translator api"
)


def setup(bot):
    cog = Fluent(bot)
    bot.add_cog(cog)
