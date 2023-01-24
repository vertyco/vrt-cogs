import functools
import logging
from io import BytesIO
from typing import List, Literal, Optional
from zipfile import ZIP_DEFLATED, ZipFile

import discord
from aiocache import SimpleMemoryCache, cached
from discord import app_commands
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n

from .formatter import HELP, IGNORE, CustomCmdFmt

log = logging.getLogger("red.vrt.autodocs")
_ = Translator("AutoDocs", __file__)


# redgettext -D autodocs.py converters.py formatter.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "Vertyco"
    __version__ = "0.4.21"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        txt = _("{}\nCog Version: {}\nAuthor: {}").format(
            helpcmd, self.__version__, self.__author__
        )
        return txt

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    def generate_readme(
        self,
        cog: commands.Cog,
        prefix: str,
        replace_botname: bool,
        extended_info: bool,
        include_hidden: bool,
        privilege_level: str,
    ) -> str:
        docs = f"# {cog.qualified_name} {HELP}\n\n"
        cog_help = cog.help.replace("\n", "<br/>") if cog.help else None
        if cog_help:
            docs += f"{cog_help}\n\n"

        for cmd in cog.walk_app_commands():
            c = CustomCmdFmt(
                self.bot, cmd, prefix, replace_botname, extended_info, privilege_level
            )
            doc = c.get_doc()
            if not doc:
                continue
            docs += doc

        ignored = []
        for cmd in cog.walk_commands():
            if cmd.hidden and not include_hidden:
                continue
            c = CustomCmdFmt(
                self.bot, cmd, prefix, replace_botname, extended_info, privilege_level
            )
            doc = c.get_doc()
            if doc is None:
                ignored.append(cmd.qualified_name)
            if not doc:
                continue
            skip = False
            for i in ignored:
                if i in cmd.qualified_name:
                    skip = True
            if skip:
                continue
            docs += doc

        return docs

    @commands.hybrid_command(name="makedocs", description=_("Create docs for a cog"))
    @app_commands.describe(
        cog_name=_("The name of the cog you want to make docs for (Case Sensitive)"),
        replace_prefix=_("Replace all occurrences of [p] with the bots prefix"),
        replace_botname=_("Replace all occurrences of [botname] with the bots name"),
        extended_info=_("Include extra info like converters and their docstrings"),
        include_hidden=_("Include hidden commands"),
        privilege_level=_(
            "Hide commands above specified privilege level (user, mod, admin, guildowner, botowner)"
        ),
    )
    @commands.is_owner()
    async def makedocs(
        self,
        ctx: commands.Context,
        cog_name: str,
        replace_prefix: Optional[bool] = False,
        replace_botname: Optional[bool] = False,
        extended_info: Optional[bool] = False,
        include_hidden: Optional[bool] = False,
        privilege_level: Literal[
            "user", "mod", "admin", "guildowner", "botowner"
        ] = "botowner",
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:           `(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:     `(bool) If True, replaces the `prefix` placeholder with the bots prefix
        `replace_botname:    `(bool) If True, replaces the `botname` placeholder with the bots name
        `extended_info:      `(bool) If True, include extra info like converters and their docstrings
        `include_hidden:     `(bool) If True, includes hidden commands
        `privilege_level:    `(str) Hide commands above specified privilege level (user, mod, admin, guildowner, botowner)

        **Note**
        If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for them and sent in a zip file
        """
        prefix = (
            (await self.bot.get_valid_prefixes(ctx.guild))[0].strip()
            if replace_prefix
            else ""
        )
        async with ctx.typing():
            if cog_name == "all":
                buffer = BytesIO()
                folder_name = _("AllCogDocs")
                with ZipFile(
                    buffer, "w", compression=ZIP_DEFLATED, compresslevel=9
                ) as arc:
                    arc.mkdir(folder_name, mode=755)
                    for cog in self.bot.cogs:
                        cog = self.bot.get_cog(cog)
                        if cog.qualified_name in IGNORE:
                            continue
                        partial_func = functools.partial(
                            self.generate_readme,
                            cog,
                            prefix,
                            replace_botname,
                            extended_info,
                            include_hidden,
                            privilege_level,
                        )
                        docs = await self.bot.loop.run_in_executor(None, partial_func)
                        filename = f"{folder_name}/{cog.qualified_name}.md"
                        arc.writestr(
                            filename, docs, compress_type=ZIP_DEFLATED, compresslevel=9
                        )

                buffer.name = f"{folder_name}.zip"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are the docs for all of your currently loaded cogs!")
            else:
                cog = self.bot.get_cog(cog_name)
                if not cog:
                    return await ctx.send(
                        _("I could not find that cog, maybe it is not loaded?")
                    )
                partial_func = functools.partial(
                    self.generate_readme,
                    cog,
                    prefix,
                    replace_botname,
                    extended_info,
                    include_hidden,
                    privilege_level,
                )
                docs = await self.bot.loop.run_in_executor(None, partial_func)
                buffer = BytesIO(docs.encode())
                buffer.name = f"{cog.qualified_name}.md"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are your docs for {}!").format(cog.qualified_name)

            await ctx.send(txt, file=file)

    @cached(ttl=8, cache=SimpleMemoryCache)
    async def get_coglist(self, string: str) -> List[app_commands.Choice]:
        cogs = set("all")
        for cmd in self.bot.walk_commands():
            cogs.add(str(cmd.cog_name).strip())
        return [
            app_commands.Choice(name=i, value=i)
            for i in cogs
            if string.lower() in i.lower()
        ][:25]

    @makedocs.autocomplete("cog_name")
    async def get_cog_names(self, inter: discord.Interaction, current: str):
        return await self.get_coglist(current)
