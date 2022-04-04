from .support import Support

___red_end_user_data_statement__ = (
    "This cog does not persistently store data about users."
)


async def setup(bot):
    bot.add_cog(Support(bot))
