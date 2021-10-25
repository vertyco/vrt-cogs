from .arktools import ArkTools

___red_end_user_data_statement__ = (
    "Thank you for installing! Use `[p]arktools` and `[p]help ArkTools` for more info.\n**Disclosure:** This cog may use considerable network traffic over time depending on how many servers you have.\nThis cog stores Gamertag Names, time played per map, and optional token data for Xbox self-host accounts."
)


async def setup(bot):
    bot.add_cog(ArkTools(bot))

