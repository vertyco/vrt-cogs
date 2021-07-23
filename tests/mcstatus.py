from redbot.core import commands
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord


class MCStatus(commands.Cog):
    """
    Minecraft status, works with bedrock!
    """

    __author__ = "Vertyco"
    __version__ = "0.0.1"

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

    async def getserver(self):

        async with self.session.get(f'https://api.mcsrvstat.us/bedrock/2/{ip}') as resp:
            # make request using that session and define its output as a 'resp'
            data = await resp.json()
            status = resp.status
        return data, status
        # return the api stuff for use in the command

    @commands.command()
    async def mcstatus(self, ctx):

        data, status = await self.getserver()
        try:
            stat = "Online" if data['online'] == True else "Offline"
            map = (data['map'])
            ip = (data['ip'])
            port = (data['port'])
            players = (data['players']['online'])
            version = (data['version'])
        except KeyError:
            return await ctx.send("Server may be offline, please contact an admin.")
            # command calls the thing and does the stuff

        color = discord.Color.dark_purple() if status == 200 else discord.Color.dark_red()
        embed = discord.Embed(
            title=f"**{gtag}**'s Profile",
            color=color,
            description=str(f"Map: {map}\nStatus: {stat}\nIP: {ip}\nPort: {port}\nPlayers: {players}/30\nVersion: {version}"),
        )

        await ctx.send(embed=embed)
        # output shows the info in an embed code block box
