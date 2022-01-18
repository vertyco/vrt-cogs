from .halostats import HaloStats

___red_end_user_data_statement__ = (
    "This cog stores Discord ID's and Gamertags and uses Selenium to web-scrape the halotracker.com site for Halo Infinite stats"
)


async def setup(bot):
    cog = HaloStats(bot)
    bot.add_cog(cog)
