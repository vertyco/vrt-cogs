from .arktools import ArkTools

___red_end_user_data_statement__ = (
    "Thank you for installing! Use `[p]arktools` for more info.\nBe sure to run the refresh command after adding/removing clusters and servers.\n**Disclosure:** This cog may use considerable network traffic over time depending on how many servers you have.\nThis cog stores Gamertag Names, time played per map, and API keys for Xbox self-host accounts."
)


def setup(bot):
    cog = ArkTools(bot)
    bot.add_cog(cog)
