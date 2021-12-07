from .atla import ATLA

___red_end_user_data_statement__ = (
    "WIP"
)


def setup(bot):
    cog = ATLA(bot)
    bot.add_cog(cog)
