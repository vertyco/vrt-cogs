import discord

from rcon.asyncio import rcon
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box


class EcoTools(commands.Cog):
    """
    Simple RCON cog for ECO servers.
    """

    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=117117117, force_registration=True)
        default_guild = {
            "servers": {}
        }
        self.config.register_guild(**default_guild)

    @commands.group(name="ecoset", aliases=["eset"])
    @commands.guild_only()
    @commands.admin()
    async def eco_set(self, ctx):
        """Access ECO server settings"""
        pass

    @eco_set.command(name="add")
    async def addserver(self, ctx, server_name: str, ip_address: str, port: int, password: str):
        """Add an ECO server(Don't use spaces in the server name!)"""
        sname = server_name.lower()
        async with self.config.guild(ctx.guild).servers() as servers:
            if sname in servers:
                overwrite = True
            else:
                overwrite = False
            servers[sname] = {
                "ip": ip_address,
                "port": port,
                "pass": password
            }
            if overwrite:
                await ctx.send("Server has been **Overwritten**")
            else:
                await ctx.send("Server has been **Added**")

    @eco_set.command(name="rem")
    async def remserver(self, ctx, server_name: str):
        """Remove an ECO server"""
        sname = server_name.lower()
        async with self.config.guild(ctx.guild).servers() as servers:
            if sname in servers:
                del servers[sname]
                await ctx.send(f"{server_name} has been deleted!")
            else:
                await ctx.send(f"{server_name} does not exist!")

    @eco_set.command(name="view")
    async def view_settings(self, ctx):
        """View ECO server settings"""
        servers = await self.config.guild(ctx.guild).servers()
        info = ""
        for sname, data in servers.items():
            info += f"**{sname.capitalize()}**\n" \
                    f"`Host: `{data['ip']}\n" \
                    f"`Port: `{data['port']}\n" \
                    f"`Pass: `{data['pass']}\n\n"
        if info:
            embed = discord.Embed(
                title="ECO Servers",
                description=info,
                color=discord.Color.random()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No servers have been added yet!")

    @commands.command(name="ercon", aliases=["erc"])
    @commands.guild_only()
    @commands.admin()
    async def eco_rcon(self, ctx, server_name: str, *, command: str):
        """Execute an RCON command for a server"""
        servers = await self.config.guild(ctx.guild).servers()
        sname = server_name.lower()
        if sname not in servers:
            return await ctx.send(f"Couldn't find {server_name} in the server config")
        server = servers[sname]
        res = await self.run_cmd(server, command)
        await ctx.send(res)

    @staticmethod
    async def run_cmd(server: dict, command: str) -> str:
        try:
            res = await rcon(
                command=command,
                host=server["ip"],
                port=server["port"],
                passwd=server["pass"]
            )
            res = res.strip()
            resp = box(res)
        except Exception as e:
            if "121" in str(e):
                resp = box(f"- Server has timed out and may be down", lang="diff")
            elif "502 Bad Gateway" in str(e) and "Cloudflare" in str(e):
                resp = box(f"- Cloudflare Issue, Discord is borked not my fault.", lang="diff")
            else:
                resp = box(f"- Encountered an unknown error: {e}", lang="diff")
        return resp
