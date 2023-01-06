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

# Static words
HELP = _("Help")
USAGE = _("Usage")
ALIASES = _("Aliases")
REQUIRED = _("Required")
OPTIONAL = _("Optional")
SLASH = _("Slash")
HYBRID = _("Hybrid")
COMMAND = _("Command")
PER = _("per")
SECONDS = _("seconds")
SECOND = _("second")
COOLDOWN = _("Cooldown")
CHECKS = _("Checks")


class CustomCmdFmt:
    def __init__(self, cmd):
        self.cmd = cmd
        self.is_slash: bool = not isinstance(cmd, commands.Command)
        self.is_hybrid: bool = isinstance(cmd, HybridAppCommand)
        self.checks: str = humanize_list(
            [i.__qualname__.split(".")[0] for i in cmd.checks]
        ).strip()
        self.name: str = cmd.qualified_name
        self.hashes: str = len(self.name.split(" ")) * "#"
        if self.is_slash:
            self.desc: str = cmd.description.replace("\n", "<br/>")
            self.options = cmd.to_dict()["options"]
        else:
            self.desc: str = cmd.help.replace("\n", "<br/>")
            cd = cmd.cooldown
            self.cooldown: str = (
                f"{cd.rate} {PER} {cd.per} {SECOND if int(cd.per) == 1 else SECONDS}"
                if cd
                else None
            )
            self.aliases: str = humanize_list(cmd.aliases) if cmd.aliases else ""


# redgettext -D autodocs.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.6"

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
        prefix: Optional[str] = None,
        include_hidden: Optional[bool] = False,
    ) -> str:
        docs = f"# {cog.qualified_name} {HELP}\n\n"

        cog_help = cog.help.replace("\n", "<br/>") if cog.help else None
        if cog_help:
            docs += f"{cog_help}\n\n"

        # Put hybrids in with normal commands
        hybrids = {}
        for cmd in self.bot.tree.walk_commands():
            c = CustomCmdFmt(cmd)
            name = c.name

            # Get params
            params = ""
            param_info = ""
            for i in c.options:
                param_name = i["name"]
                param_desc = i["description"]
                required = i.get("required", False)
                if required:
                    params += f"<{param_name}> "
                    param_info += f" - `{param_name}:` ({REQUIRED}) {param_desc}\n"
                else:
                    params += f"[{param_name}] "
                    param_info += f" - `{param_name}:` ({OPTIONAL}) {param_desc}\n"
            params = params.strip()

            usage = f"/{name}"
            if params:
                usage += f" {params}"

            if c.is_hybrid:
                hybrids[name] = {
                    "desc": c.desc,
                    "params": params,
                    "param_info": param_info,
                }
            else:
                docs += (
                    f"{c.hashes} {name} ({SLASH} {COMMAND})\n"
                    f" - {USAGE}: `{usage}`\n"
                )
                if param_info:
                    docs += f"{param_info}"

                if c.checks:
                    docs += f" - {CHECKS}: {c.checks}\n"
                if not docs.endswith("\n\n"):
                    docs += "\n"
                docs += f"{c.desc}\n\n"

        # Normal + Hybrid commands
        for cmd in cog.walk_commands():
            if cmd.hidden and not include_hidden:
                continue

            c = CustomCmdFmt(cmd)
            name = c.name
            desc = c.desc
            checks = c.checks
            cooldown = c.cooldown
            aliases = c.aliases

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

            if prefix:
                desc = desc.replace("[p]", prefix)
                usage = f"{prefix}{name}"
            else:
                usage = f"[p]{name}"

            if param_string:
                usage += f" {param_string}"

            hybrid = hybrids.get(name, None)
            if hybrid:
                d2 = hybrid.get("desc", None)
                params = hybrid.get("params", None)
                param_info = hybrid.get("param_info", None)
                otherusage = f"/{name}"
                if params:
                    otherusage += f" {params}"

                docs += (
                    f"{c.hashes} {name} ({HYBRID} {COMMAND})\n"
                    f" - {USAGE}: `{usage}`\n"
                    f" - {SLASH} {USAGE}: `{otherusage}`\n"
                )
                if aliases:
                    docs += f" - {ALIASES}: `{aliases}`\n"
                if param_info:
                    docs += f"{param_info}\n"
                if cooldown:
                    docs += f" - {COOLDOWN}: {cooldown}\n"
                if checks:
                    docs += f" - {CHECKS}: {checks.strip()}\n"

                if not docs.endswith("\n\n"):
                    docs += "\n"
                docs += f"{desc}\n\n"
                if d2:
                    docs += f"{d2}\n\n"

            else:
                docs += f"{c.hashes} {name}\n" f" - {USAGE}: `{usage}`\n"
                if aliases:
                    docs += f" - {ALIASES}: `{aliases}`\n"
                if cooldown:
                    docs += f" - {COOLDOWN}: {cooldown}\n"
                if checks:
                    docs += f" - {CHECKS}: {checks.strip()}\n"

                if not docs.endswith("\n\n"):
                    docs += "\n"
                docs += f"{desc}\n\n"

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
