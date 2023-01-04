import logging
from io import BytesIO
from typing import Optional
from zipfile import ZIP_DEFLATED, ZipFile

import discord
from discord import app_commands
from discord.ext.commands.hybrid import HybridAppCommand
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

log = logging.getLogger("red.vrt.autodocs")
_ = Translator("AutoDocs", __file__)


# redgettext -D autodocs.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "Vertyco"
    __version__ = "0.0.4"

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
        self.h = _("Help")
        self.u = _("Usage")
        self.a = _("Aliases")
        self.r = _("Required")
        self.o = _("Optional")
        self.s = _("Slash")
        self.hb = _("Hybrid")
        self.c = _("Command")

    def generate_readme(
        self,
        cog: commands.Cog,
        prefix: Optional[str] = None,
        include_hidden: Optional[bool] = False,
    ) -> str:
        docs = f"# {cog.qualified_name} {self.h}\n\n{cog.help}\n\n"

        # Put hybrids in with normal commands
        hybrids = {}
        for cmd in self.bot.tree.walk_commands():
            # If command is hybrid it will show up for regular commands too
            is_hybrid = isinstance(cmd, HybridAppCommand)
            name = cmd.qualified_name
            desc = cmd.description
            options = cmd.to_dict()["options"]
            level = len(name.split(" "))
            hashes = level * "#"

            # Get params
            param_string = ""
            param_info = ""
            for i in options:
                param_name = i["name"]
                param_desc = i["description"]
                required = i.get("required", False)
                if required:
                    param_string += f"<{param_name}> "
                    param_info += f" - `{param_name}:` ({self.r}) {param_desc}\n"
                else:
                    param_string += f"[{param_name}] "
                    param_info += f" - `{param_name}:` ({self.o}) {param_desc}\n"
            param_string = param_string.strip()

            usage = f"/{name}"
            if param_string:
                usage += f" {param_string}"

            if is_hybrid:
                hybrids[name] = {
                    "desc": desc,
                    "pstring": param_string,
                    "pinfo": param_info,
                }
            else:
                docs += f"{hashes} {name} ({self.s} {self.c})\n - {self.u}: `{usage}`"
                if param_info:
                    docs += f"\n{param_info}\n\n"
                else:
                    docs += "\n\n"
                docs += f"{desc}\n\n"

        for cmd in cog.walk_commands():
            name = cmd.qualified_name
            level = len(name.split(" "))
            hashes = level * "#"
            if cmd.hidden and not include_hidden:
                continue

            aliases = cmd.aliases

            # Get params
            params = cmd.clean_params
            param_string = ""
            for k, v in params.items():
                arg = v.name
                default = v.default
                if default == v.empty:
                    param_string += f"<{arg}> "
                elif v.kind == v.KEYWORD_ONLY:
                    param_string += f"[{arg}] "
                else:
                    param_string += f"[{arg}={default}] "
            param_string = param_string.strip()

            hlp = cmd.help

            if prefix:
                hlp = hlp.replace("[p]", prefix)
                usage = f"{prefix}{name}"
            else:
                usage = f"[p]{name}"

            if param_string:
                usage += f" {param_string}"

            hybrid = hybrids.get(name, None)
            if hybrid:
                d2 = hybrid.get("desc", None)
                pstring = hybrid.get("pstring", None)
                pinfo = hybrid.get("pinfo", None)
                otherusage = f"/{name}"
                if pstring:
                    otherusage += f" {pstring}"
                docs += (
                    f"{hashes} {name} ({self.hb} {self.c})\n"
                    f" - {self.u}: `{usage}`\n"
                    f" - {self.s} {self.u}: `{otherusage}`\n"
                )

                if aliases:
                    docs += f" - {self.a}: `{humanize_list(aliases)}`\n"
                if pinfo:
                    docs += f"{pinfo}\n"

                if hlp:
                    docs += f"\n{hlp}\n\n"
                elif d2:
                    docs += f"\n{d2}\n\n"

            else:
                docs += f"{hashes} {name}\n - {self.u}: `{usage}`\n"
                if aliases:
                    docs += f" - {self.a}: `{humanize_list(aliases)}`\n\n"
                if hlp:
                    docs += f"\n{hlp}\n\n"

        return docs

    @commands.hybrid_command(name="makedocs", description=_("Create docs for a cog"))
    @app_commands.describe(
        cog_name=_("The name of the cog you want to make docs for (Case Sensitive)"),
        replace_prefix=_("Replace prefix placeholder with the bots prefix"),
        include_hidden=_("Include hidden commands"),
    )
    @commands.is_owner()
    async def makedocs(
        self,
        ctx: commands.Context,
        cog_name: str,
        replace_prefix: Optional[bool] = False,
        include_hidden: Optional[bool] = False,
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:`(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:`(bool) If True, replaces the prefix placeholder [] with the bots prefix
        `include_hidden:`(bool) If True, includes hidden commands

        **Warning**
        If `all` is specified for cog_name, and you have a lot of cogs loaded, prepare for a spammed channel
        """
        async with ctx.typing():
            p = ctx.prefix if replace_prefix else None
            if cog_name == "all":
                buffer = BytesIO()
                folder_name = _("AllCogDocs")
                with ZipFile(
                    buffer, "w", compression=ZIP_DEFLATED, compresslevel=9
                ) as arc:
                    arc.mkdir(folder_name, mode=755)
                    for cog in self.bot.cogs:
                        cog = self.bot.get_cog(cog)
                        res = self.generate_readme(cog, p, include_hidden)
                        filename = f"{folder_name}/{cog.qualified_name}.md"
                        arc.writestr(
                            filename, res, compress_type=ZIP_DEFLATED, compresslevel=9
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

                res = self.generate_readme(cog, p, include_hidden)
                buffer = BytesIO(res.encode())
                buffer.name = f"{cog.qualified_name}.md"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are your docs for {}!").format(cog.qualified_name)

            await ctx.send(txt, file=file)
