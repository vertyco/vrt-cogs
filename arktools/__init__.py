from .arktools import ArkTools

___red_end_user_data_statement__ = (
    "This is probably one of the more I/O heavy cogs available and is NOT intended to be run on extremely small devices/VMs due to the sheer amount of socket connections, API calls, and task loops it utilizes.\nThis cog stores Gamertag Names, XUIDs, Discord IDs, time played per map, and optional token data for Xbox self-host accounts."
)


async def setup(bot):
    bot.add_cog(ArkTools(bot))

