from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord


class MCTools(commands.Cog):
    """
    Simple minecraft status cog for bedrock servers.
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
        self.config = Config.get_conf(self, identifier=61564189)
        default_guild = {
            "address": []
        }
        self.config.register_guild(**default_guild)


    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        # close session on unload

    async def getserver(self, address):

        async with self.session.get(f'https://api.mcsrvstat.us/bedrock/2/{address}') as resp:
            # make request using that session and define its output as a 'resp'
            data = await resp.json()
            status = resp.status
        return data, status
        # return the api stuff for use in the command

    @commands.command()
    async def mcstatus(self, ctx):
        """Check the status of your Bedrock server."""
        address = await self.config.guild(ctx.guild).address()
        data, status = await self.getserver(address)
        try:
            stat = "Online" if data['online'] == True else "Offline"
            mp = (data['map'])
            ip = (data['ip'])
            port = (data['port'])
            players = (data['players']['online'])
            version = (data['version'])
        except Exception as e:
            if 'map' in str(e).lower():
                await ctx.send("Server has either not been set or is failing to connect.")
            else:
                return await ctx.send("Server may be offline, please contact an admin.")
            return
            # command calls the thing and does the stuff

        color = discord.Color.dark_purple() if status == 200 else discord.Color.dark_red()
        embed = discord.Embed(
            title=f"**{mp} Server**",
            color=color,
            description=box(f"IP: {ip}\nPort: {port}\nVersion: {version}"),
        )
        embed.add_field(name="Status", value=stat)
        embed.add_field(name="Players", value=f"{players}/30")
        await ctx.send(embed=embed)
        # output shows the info in an embed code block box

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def addmcserver(self, ctx, address):
        """Add an MC Bedrock server. format is IP:PORT"""
        await self.config.guild(ctx.guild).address.set(address)
        await ctx.send("Your server has been set!")
