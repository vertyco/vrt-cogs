from .warntransfer import WarnTransfer

___red_end_user_data_statement__ = (
    "This cog does not store any user data"
)


def setup(bot):
    cog = WarnTransfer(bot)
    bot.add_cog(cog)
