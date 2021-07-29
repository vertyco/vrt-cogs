from .arktools import ArkTools

___red_end_user_data_statement__ = (
    "Thank you for installing! Use `[p]arktools` for more info.\n**Disclosure:** For large clusters with many servers, this cog may use considerable network traffic over time, especially with all features enabled."
)


def setup(bot):
    cog = ArkTools(bot)
    bot.add_cog(cog)
