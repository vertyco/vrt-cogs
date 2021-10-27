from .arksave import ArkSave

___red_end_user_data_statement__ = (
    "This cog just moves files on the bot host server"
)


async def setup(bot):
    bot.add_cog(ArkSave(bot))

