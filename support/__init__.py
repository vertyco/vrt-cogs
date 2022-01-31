from .support import Support

___red_end_user_data_statement__ = (
    "This cog stores Discord ID's"
)


async def setup(bot):
    bot.add_cog(Support(bot))
