from .arkshop import ArkShop

___red_end_user_data_statement__ = (
    "This cog stores player XUID's and Discord ID's."
)


def setup(bot):
    cog = ArkShop(bot)
    bot.add_cog(cog)
