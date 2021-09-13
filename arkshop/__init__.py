from .arkshop import ArkShop

___red_end_user_data_statement__ = (
    "WIP"
)


def setup(bot):
    cog = ArkShop(bot)
    bot.add_cog(cog)
