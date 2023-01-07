import logging
from io import BytesIO
from typing import Optional, Union
from zipfile import ZIP_DEFLATED, ZipFile

import discord
from discord import app_commands
from discord.app_commands.commands import Command as SlashCommand
from discord.ext.commands.hybrid import HybridAppCommand
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.commands import HybridCommand, HybridGroup
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .converters import CLASSCONVERTER, CONVERTERS

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
    def __init__(
        self,
        cmd: Union[
            HybridGroup, HybridCommand, HybridAppCommand, SlashCommand, commands.Command
        ],
    ):
        self.cmd = cmd

        self.is_slash: bool = isinstance(cmd, SlashCommand)
        self.is_hybrid: bool = any(
            [
                isinstance(cmd, HybridCommand),
                isinstance(cmd, HybridAppCommand),
                isinstance(cmd, HybridGroup),
            ]
        )

        try:
            self.checks: str = humanize_list(
                [i.__qualname__.split(".")[0] for i in cmd.checks]
            ).strip()
        except AttributeError:
            self.checks = ""
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

    def fmt(
        self, adv: Optional[bool] = True, include_docs: Optional[bool] = True
    ) -> str:
        docs = ""
        if adv or include_docs:
            docs += _("Parameter Breakdown\n")

        if self.is_slash:
            for p in self.cmd.parameters:
                doc = CONVERTERS.get(p.type)

                if adv:
                    cls = CLASSCONVERTER.get(p.type)
                    if cls:
                        cls = str(cls).replace("<class '", "").replace("'>", "")
                        docs += f"> ### {p.name}: {cls}\n"
                    else:
                        log.warning(
                            f"Cannot find class {p}\nPlease report to Cog Developer"
                        )

                if doc and include_docs:
                    if ".." in doc:
                        doc = doc.split("..")[0]
                    for line in doc.split("\n"):
                        if line.strip().startswith(">"):
                            line = line.replace(">", "")
                        docs += f"> {line}\n"
        else:
            for arg, ptype in self.cmd.clean_params.items():
                string = str(ptype)

                converter = ptype.converter
                try:
                    doc = CONVERTERS.get(converter)
                except TypeError:
                    log.warning(
                        f"Cant find {ptype} for the {arg} argument of the {self.name} command"
                    )
                    doc = None
                if not doc and hasattr(converter, "__args__"):
                    doc = CONVERTERS.get(converter.__args__[0])

                if adv:
                    docs += f"> ### {string}\n"
                if doc and include_docs:
                    if ".." in doc:
                        doc = doc.split("..")[0]
                    for line in doc.split("\n"):
                        if line.strip().startswith(">"):
                            line = line.replace(">", "")
                        docs += f"> {line}\n"

        if docs:
            return _("Parameter Breakdown\n") + docs


# redgettext -D autodocs.py converters.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "Vertyco"
    __version__ = "0.2.13"

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

        # Ignored core cogs when using the 'all' argument
        self.ignore = [
            "Admin",
            "Alias",
            "Audio",
            "Cleanup",
            "Economy",
            "Filter",
            "General",
            "Image",
            "Mod",
            "Modlog",
            "Mutes",
            "Permissions",
            "Reports",
            "Streams",
            "Trivia",
            "Warnings",
        ]

    def generate_readme(
        self,
        cog: commands.Cog,
        prefix: str,
        include_hidden: bool,
        advanced_docs: bool,
        include_docstrings: bool,
        replace_botname: bool,
    ) -> str:
        docs = f"# {cog.qualified_name} {HELP}\n\n"

        cog_help = cog.help.replace("\n", "<br/>") if cog.help else None
        if cog_help:
            docs += f"{cog_help}\n\n"
        # Put hybrids in with normal commands
        hybrids = {}

        for cmd in cog.walk_app_commands():
            c = CustomCmdFmt(cmd)
            name = c.name

            # Get params
            arg_string = ""
            arg_descriptions = ""

            for i in c.options:
                param_name = i["name"]
                param_desc = i["description"]
                required = i.get("required", False)
                if required:
                    arg_string += f"<{param_name}> "
                    arg_descriptions += (
                        f" - `{param_name}:` ({REQUIRED}) {param_desc}\n"
                    )
                else:
                    arg_string += f"[{param_name}] "
                    arg_descriptions += (
                        f" - `{param_name}:` ({OPTIONAL}) {param_desc}\n"
                    )

            arg_string = arg_string.strip()

            usage = f"/{name}"
            if arg_string:
                usage += f" {arg_string}"

            if c.is_hybrid:
                hybrids[name] = {
                    "desc": c.desc,
                    "arg_string": arg_string,
                    "arg_descriptions": arg_descriptions,
                }
            else:
                docs += (
                    f"{c.hashes} {name} ({SLASH} {COMMAND})\n"
                    f" - {USAGE}: `{usage}`\n"
                )
                if arg_descriptions:
                    docs += f"{arg_descriptions}"

                if c.checks:
                    docs += f" - {CHECKS}: {c.checks}\n"
                if not docs.endswith("\n\n"):
                    docs += "\n"
                docs += f"{c.desc}\n\n"

                extended = c.fmt(advanced_docs, include_docstrings)
                if extended:
                    docs += extended

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
                arg_info = hybrid.get("arg_info", None)
                arg_descriptions = hybrid.get("arg_descriptions", None)
                otherusage = f"/{name}"
                if arg_info:
                    otherusage += f" {arg_info}"

                docs += (
                    f"{c.hashes} {name} ({HYBRID} {COMMAND})\n"
                    f" - {USAGE}: `{usage}`\n"
                    f" - {SLASH} {USAGE}: `{otherusage}`\n"
                )
                if aliases:
                    docs += f" - {ALIASES}: `{aliases}`\n"
                if arg_descriptions:
                    docs += f"{arg_descriptions}\n"
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

            extended = c.fmt(advanced_docs, include_docstrings)
            if extended:
                docs += extended

        if replace_botname:
            docs = docs.replace("[botname]", self.bot.user.display_name)
        docs = docs.replace("guild", _("server"))
        return docs

    @commands.hybrid_command(name="makedocs", description=_("Create docs for a cog"))
    @app_commands.describe(
        cog_name=_("The name of the cog you want to make docs for (Case Sensitive)"),
        replace_prefix=_("Replace all occurrences of [p] with the bots prefix"),
        include_hidden=_("Include hidden commands"),
        advanced_docs=_("Generate advanced docs including converter types"),
        include_docstrings=_("Include converter docstrings"),
        replace_botname=_("Replace all occurrences of [botname] with the bots name"),
    )
    @commands.is_owner()
    async def makedocs(
        self,
        ctx: commands.Context,
        cog_name: str,
        replace_prefix: Optional[bool] = False,
        include_hidden: Optional[bool] = False,
        advanced_docs: Optional[bool] = False,
        include_docstrings: Optional[bool] = False,
        replace_botname: Optional[bool] = False,
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:           `(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:     `(bool) If True, replaces the prefix placeholder [] with the bots prefix
        `include_hidden:     `(bool) If True, includes hidden commands
        `advanced_docs:      `(bool) If True, include converters from command arguments,
        `include_docstrings: `(bool) if True, include docstrings from command argument converters

        **Warning**
        If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for them and sent in a zip file
        """
        p = ctx.prefix if replace_prefix else ""
        if p == "/":
            p = (await self.bot.get_valid_prefixes(ctx.guild))[0]
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
                        if cog.qualified_name in self.ignore:
                            continue
                        res = self.generate_readme(
                            cog,
                            p,
                            include_hidden,
                            advanced_docs,
                            include_docstrings,
                            replace_botname,
                        )
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

                res = self.generate_readme(
                    cog,
                    p,
                    include_hidden,
                    advanced_docs,
                    include_docstrings,
                    replace_botname,
                )
                buffer = BytesIO(res.encode())
                buffer.name = f"{cog.qualified_name}.md"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are your docs for {}!").format(cog.qualified_name)

            await ctx.send(txt, file=file)
