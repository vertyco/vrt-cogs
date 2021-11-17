from .sctools import SCTools

___red_end_user_data_statement__ = (
    "This cog only stores an api key from the bot owner"
)


async def setup(bot):
    bot.add_cog(SCTools(bot))

