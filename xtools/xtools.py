from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord

class XTools(commands.Cog):
    """
    Xbox API Tools, inspiration from flare's ApiTools :)
    """

    __author__ = "Vertyco"
    __version__ = "0.0.7"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_guild = {"apikey": None}
        self.config.register_guild(**default_guild)


    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def get_gamertag(self, command, gtag):
        # define what happens when the 'xprofile' command is run
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(int(guildID))
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            apikey = settings["apikey"]
            async with self.session.get(f'{command}{gtag}',
                                        headers={"X-Authorization": apikey}) as resp:
                # make request using that session and define its output as a 'resp'
                try:
                    data = await resp.json()
                    status = resp.status
                    remaining = resp.headers['X-RateLimit-Remaining']
                    ratelimit = resp.headers['X-RateLimit-Limit']
                except ContentTypeError:
                    ctx.send("The API failed to pull the data for some reason. Please try again.")

                return data, status, remaining, ratelimit
                # return the api stuff for use in the command

    @commands.command(name="setapikey", alias="xtools")
    async def setkey(self, ctx, key: str):
        """
        Set an api key so you can view your info.
        To get an api key, visit https://xbl.io/
        """
        await self.config.guild(ctx.guild).apikey.set(str(key))
        await ctx.send(f"API key has been set!")

    @commands.command()
    async def xprofile(self, ctx, *, gtag):
        """Type your gamertag in and pull your profile info"""
        data = await self.config.guild(ctx.guild).all()
        if data["apikey"] is None:
            await ctx.send(f"You need to set a valid API key with `{ctx.clean_prefix}setapikey`"
                           f" before you can use that command.")
            await ctx.send("To obtain a key, visit https://xbl.io/ and register your microsoft account.")
            return

        async with ctx.typing():
            command = "https://xbl.io/api/v2/friends/search?gt="
            data, status, remaining, ratelimit = await self.get_gamertag(command, gtag)
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
