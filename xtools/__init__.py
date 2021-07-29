from .xtools import XTools
___red_end_user_data_statement__ = (
    "This cog uses the xbl.io API and does not persistently store data about users.\n**Note:**\nThis cog will NOT pull xbox profile's 'real name' or 'location data' just gamerscore, pfp, xuid and bio ect.."
)


def setup(bot):
    cog = XTools(bot)
    bot.add_cog(cog)
