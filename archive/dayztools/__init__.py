from .dayztools import DayZTools

___red_end_user_data_statement__ = (
    "Thank you for installing!"
)


def setup(bot):
    cog = DayZTools(bot)
    bot.add_cog(cog)
