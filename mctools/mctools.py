import discord

from mcstats import mcstats
from redbot.core import commands, Config


class MCTools(commands.Cog):
    """
    Simple status cog for Minecraft bedrock servers.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=61564189)
        default_guild = {
            "servers": {}
        }
        self.config.register_guild(**default_guild)

    async def getserver(self, host: str, port: int):
        def exe():
            try:
                with mcstats(host, port=port, timeout=10) as mc:
                    return mc
            except Exception as e:
                if "timed out" in str(e):
                    return "timeout"
        data = await self.bot.loop.run_in_executor(None, exe)
        return data

    @commands.command()
    @commands.guild_only()
    async def mcstatus(self, ctx):
        """Check the status of your Bedrock server."""
        servers = await self.config.guild(ctx.guild).servers()
        embed = discord.Embed(
            color=discord.Color.random(),
            description="**Minecraft Bedrock Server Status**",
        )
        for name, server in servers.items():
            host = server["host"]
            port = server["port"]
            data = await self.getserver(host, port)
            if data == "timeout" or not data:
                embed.add_field(
                    name=name,
                    value="Timed Out (Offline)"
                )
            else:
                ver = data.game_version
                nump = data.num_players
                maxp = data.max_players
                motd = data.motd
                mode = data.gamemode
                embed.add_field(
                    name=name,
                    value=f"`Version: `{ver}\n"
                          f"`Mode:    `{mode}\n"
                          f"`MotD:    `{motd}\n"
                          f"`Players: `{nump}/{maxp}"
                )
        await ctx.send(embed=embed)
        # output shows the info in an embed code block box

    @commands.command()
    @commands.guild_only()
    @commands.admin()
    async def addserver(self, ctx, address: str, port: int):
        """Add an MC Bedrock server. format is IP:PORT"""
        async with ctx.typint():
            data = await self.getserver(address, port)
        if data == "timeout":
            return await ctx.send("Unable to obtain server data, it may be offline.")
        if not data:
            return await ctx.send("Error: Unable to communicate with server.")
        name = data.server_name
        async with self.config.guild(ctx.guild).servers() as servers:
            servers[name] = {
                "host": address,
                "port": port,
            }
        await ctx.send(f"{name} server has been added!")

