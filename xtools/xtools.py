from redbot.core import commands
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord


class XTools(commands.Cog):
    """
    Xbox API Tools, inspiration from flare's ApiTools :)
    """

    __author__ = "Vertyco"
    __version__ = "0.0.4"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        # init session

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        # close session on unload

    async def get_gamertag(self, gtag):
        # define what happens when the 'xprofile' command is run
        async with self.session.get(f'https://xbl.io/api/v2/friends/search?gt={gtag}',
                                    headers={"X-Authorization": "8cgooossows0880s00kks48wcosw4c04ksk"}) as resp:
            # make request using that session and define its output as a 'resp'
            data = await resp.json()
            status = resp.status
            remaining = resp.headers['X-RateLimit-Remaining']
            ratelimit = resp.headers['X-RateLimit-Limit']
        return data, status, remaining, ratelimit
        # return the api stuff for use in the command

    @commands.command()
    async def xprofile(self, ctx, *, gtag):
        # define gamertag here defined as 'gtag'
        data, status, remaining, ratelimit = await self.get_gamertag(gtag)
        try:
            for user in data["profileUsers"]:
                xuid = (f"**XUID:** {user['id']}")
                for setting in user["settings"]:
                    if setting["id"] == "Gamerscore":
                        gs = (f"**Gamerscore:** {setting['value']}")
                    if setting["id"] == "AccountTier":
                        tier = (f"**AccountTier:** {setting['value']}")
                    if setting["id"] == "XboxOneRep":
                        rep = (f"**Reputation:** {setting['value']}")
                    if setting["id"] == "GameDisplayPicRaw":
                        pfp = (setting['value'])
                    if setting["id"] == "Bio":
                        bio = (setting['value'])
        except KeyError:
            return await ctx.send("Invalid Gamertag, please try again.")
            # command calls the thing and does the stuff

        color = discord.Color.dark_purple() if status == 200 else discord.Color.dark_red()
        stat = "Good" if status == 200 else "Failed"
        embed = discord.Embed(
            title=f"**{gtag}**'s Profile",
            color=color,
            description=str(f"{xuid}\n{gs}\n{tier}\n{rep}"),
        )
        embed.set_image(url=pfp)
        embed.add_field(name="Bio", value=box(bio))
        embed.add_field(name="API Status",
                        value=f"API: {stat}\nRateLimit: {ratelimit}/hour\nRemaining: {remaining}",
                        inline=False
                        )
        await ctx.send(embed=embed)
        # output shows the info in an embed code block box
