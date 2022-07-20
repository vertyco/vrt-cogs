import subprocess
from pathlib import Path
from io import StringIO
import json

import discord
import pkg_resources
from redbot.cogs.downloader.repo_manager import Repo
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

_ = Translator("VrtUtils", __file__)


class VrtUtils(commands.Cog):
    """
    Small assortment of utility commands for bot owners
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.LIB_PATH = cog_data_path(self) / "lib"

    @commands.command()
    @commands.is_owner()
    async def getlibs(self, ctx):
        """Get all current installed packages on the bots venv"""
        packages = [str(p) for p in pkg_resources.working_set]
        packages = sorted(packages, key=str.lower)
        text = ""
        for package in packages:
            text += f"{package}\n"
        embeds = []
        page = 1
        for p in pagify(text):
            embed = discord.Embed(
                description=box(p)
            )
            embed.set_footer(text=f"Page {page}")
            page += 1
            embeds.append(embed)
        if len(embeds) > 1:
            await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def updatelibs(self, ctx):
        """Update all installed packages on the bots venv"""
        async with ctx.typing():
            packages = [dist.project_name for dist in pkg_resources.working_set]
            deps = ' '.join(packages)
            repo = Repo("", "", "", "", Path.cwd())
            async with ctx.typing():
                success = await repo.install_raw_requirements(deps, self.LIB_PATH)

            if success:
                await ctx.send(_("Libraries updated."))
            else:
                await ctx.send(_("Some libraries failed to update. Check your logs for details."))

    @commands.command()
    @commands.is_owner()
    async def pip(self, ctx, *, command: str):
        """Run a pip command"""
        async with ctx.typing():
            command = f"pip {command}"

            def pipexe():
                results = subprocess.run(command, stdout=subprocess.PIPE).stdout.decode("utf-8")
                return results

        res = await self.bot.loop.run_in_executor(None, pipexe)
        embeds = []
        page = 1
        for p in pagify(res):
            embed = discord.Embed(
                title="Packages Updated",
                description=box(p)
            )
            embed.set_footer(text=f"Page {page}")
            page += 1
            embeds.append(embed)
        if len(embeds) > 1:
            await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embeds[0])

    @commands.command()
    @commands.is_owner()
    async def findguild(self, ctx, guild_id: int):
        """Find a guild by ID"""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.Forbidden:
                guild = None
        if not guild:
            return await ctx.send("Could not find that guild")
        await ctx.send(f"That ID belongs to the guild `{guild.name}`")

    @commands.command()
    @commands.is_owner()
    async def getusernames(self, ctx):
        """Get all usernames of this guild in a json file"""
        members = {}
        for member in ctx.guild.members:
            members[str(member.id)] = member.name

        iofile = StringIO(json.dumps(members))
        filename = f"users.json"
        file = discord.File(iofile, filename=filename)
        await ctx.send("Here are all usersnames for this guild", file=file)
