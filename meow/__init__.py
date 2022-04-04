from .meow import Meow

___red_end_user_data_statement__ = (
    "This cog does not persistently store data about users right meow."
)


def setup(bot):
    cog = Meow(bot)
    bot.add_cog(cog)
