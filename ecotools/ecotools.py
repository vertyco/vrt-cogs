import discord
from rcon.source import rcon
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import box


class EcoTools(commands.Cog):
    """
    Simple RCON cog for ECO servers.
    """

    __author__ = "Vertyco"
    __version__ = "1.0.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=117117117, force_registration=True
        )
        default_guild = {"servers": {}, "allow": []}
        self.config.register_guild(**default_guild)

    @commands.group(name="ecoset", aliases=["eset"])
    @commands.guild_only()
    @commands.admin()
    async def eco_set(self, ctx):
        """Access ECO server settings"""
        pass

    @eco_set.command(name="add")
    async def addserver(
        self, ctx, server_name: str, ip_address: str, port: int, password: str
    ):
        """Add an ECO server(Don't use spaces in the server name!)"""
        sname = server_name.lower()
        async with self.config.guild(ctx.guild).servers() as servers:
            if sname in servers:
                overwrite = True
            else:
                overwrite = False
            servers[sname] = {"ip": ip_address, "port": port, "pass": password}
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
        conf = await self.config.guild(ctx.guild).all()

        allowlist = conf["allow"]
        allowed = ""
        if allowlist:
            for role_id in allowlist:
                role = ctx.guild.get_role(role_id)
                if role:
                    allowed += f"{role.mention}\n"
        if not allowed:
            allowed = "None Set\n"

        servers = conf["servers"]
        info = ""
        if servers:
            for sname, data in servers.items():
                info += (
                    f"➣{sname.capitalize()}\n"
                    f"`Host: `{data['ip']}\n"
                    f"`Port: `{data['port']}\n"
                    f"`Pass: `{data['pass']}\n\n"
                )
        if not info:
            info = "No Servers Configured\n"

        embed = discord.Embed(
            title="ECOTools Settings",
            description=f"**RCON Access Roles**\n"
            f"{allowed}"
            f"**ECO Servers**\n"
            f"{info}",
            color=discord.Color.random(),
        )
        await ctx.send(embed=embed)

    @eco_set.command(name="allow")
    async def allow_list(self, ctx, *, role: discord.Role):
        """
        Add/Remove roles from the allow list to use RCON commands

        To remove a role, simply mention it again in the command
        """
        async with self.config.guild(ctx.guild).allow() as allow:
            if role.id in allow:
                allow.remove(role.id)
                await ctx.send(f"**{role.name}** has been removed from the allow list")
            else:
                allow.append(role.id)
                await ctx.send(f"**{role.name}** has been added to the allow list")

    @commands.command(name="ercon", aliases=["erc"])
    @commands.guild_only()
    async def eco_rcon(self, ctx, server_name: str, *, command: str):
        """Execute an RCON command for a server"""
        conf = await self.config.guild(ctx.guild).all()
        servers = conf["servers"]
        sname = server_name.lower()
        if sname not in conf["servers"]:
            return await ctx.send(f"Couldn't find {server_name} in the server config")

        for role in ctx.author.roles:
            if role.id in conf["allow"]:
                break
        else:
            return await ctx.send("You do not have permissions to run that command.")

        server = servers[sname]
        async with ctx.typing():
            res = await self.run_cmd(server, command)
            if res == "tick":
                await ctx.tick()
            else:
                await ctx.send(res)

    @staticmethod
    async def run_cmd(server: dict, command: str) -> str:
        try:
            res = await rcon(
                command=command,
                host=server["ip"],
                port=server["port"],
                passwd=server["pass"],
            )
            res = res.strip()
            if not res:
                resp = "tick"
            else:
                resp = box(res)
        except Exception as e:
            if "121" in str(e):
                resp = box("- Server has timed out and may be down", lang="diff")
            elif "502 Bad Gateway" in str(e) and "Cloudflare" in str(e):
                resp = box(
                    "- Cloudflare Issue, Discord is borked not my fault.", lang="diff"
                )
            else:
                resp = box(f"- Encountered an unknown error: {e}", lang="diff")
        return resp
