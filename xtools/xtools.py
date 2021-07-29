from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord


class XTools(commands.Cog):
    """
    Xbox API Tools, inspiration from flare's ApiTools :)
    """

    __author__ = "Vertyco"
    __version__ = "0.1.10"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def get_gamertag(self, ctx, apikey, command, gtag):
        async with self.session.get(f'{command}{gtag}',
                                    headers={"X-Authorization": apikey}) as resp:
            try:
                data = await resp.json()
                status = resp.status
                remaining = resp.headers['X-RateLimit-Remaining']
                ratelimit = resp.headers['X-RateLimit-Limit']
            except ContentTypeError:
                ctx.send("The API failed to pull the data. Please try again.")

            return data, status, remaining, ratelimit

    # Pulls profile data and formats for an embed
    # Purposely left out the 'real name' and 'location' data for privacy reasons,
    # Since some people have their profile info public and may not know it
    @commands.command()
    async def xprofile(self, ctx, *, gtag):
        """Type your gamertag in and pull your profile info"""
        xtools_api = await self.bot.get_shared_api_tokens("xtools")
        if xtools_api.get("api_key") is None:
            await ctx.send(f"This cog needs a valid API key with `{ctx.clean_prefix}set api xtools api_key,<key>`"
                           f" before you can use this command.")
            await ctx.send("To obtain a key, visit https://xbl.io/ and register your microsoft account.")
            return

        async with ctx.typing():
            command = "https://xbl.io/api/v2/friends/search?gt="
            data, status, remaining, ratelimit = await self.get_gamertag(ctx, xtools_api["api_key"], command, gtag)
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
