from .levelup import LevelUp

___red_end_user_data_statement__ = (
    "This cog stores Discord ID's."
)


async def setup(bot):
    cog = LevelUp(bot)
    bot.add_cog(cog)
    await LevelUp.init_settings(LevelUp(bot))
