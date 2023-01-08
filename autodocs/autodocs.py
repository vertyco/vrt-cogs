import functools
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
AUTOCOMPLETE = _("Autocomplete")
CHOICES = _("Choices")
OPTIONAL = _("Optional")
DEFAULT = _("Default")
SLASH = _("Slash")
HYBRID = _("Hybrid")
COMMAND = _("Command")
RESTRICTED = _("Restricted to")
GUILDONLY = _("Server Only")
PER = _("per")
SECONDS = _("seconds")
SECOND = _("second")
COOLDOWN = _("Cooldown")
CHECKS = _("Checks")


class CustomCmdFmt:
    """Formats documentation for a single command"""

    def __init__(
        self,
        bot: Red,
        cmd: Union[
            HybridGroup, HybridCommand, HybridAppCommand, SlashCommand, commands.Command
        ],
        prefix: str,
        replace_botname: bool,
        extended_info: bool,
    ):
        self.bot = bot
        self.cmd = cmd
        self.prefix = prefix
        self.replace_botname = replace_botname
        self.extended_info = extended_info

        self.is_slash: bool = isinstance(cmd, SlashCommand)
        self.is_hybrid: bool = any(
            [
                isinstance(cmd, HybridGroup),
                isinstance(cmd, HybridCommand),
                isinstance(cmd, HybridAppCommand),
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
            self.options = cmd.to_dict()["options"]
            self.desc: str = cmd.description.replace("\n", "<br/>")
        else:
            self.desc: str = cmd.help.replace("\n", "<br/>")
            self.perms = self.cmd.requires
            cd = cmd.cooldown
            self.cooldown: str = (
                f"{cd.rate} {PER} {cd.per} {SECOND if int(cd.per) == 1 else SECONDS}"
                if cd
                else None
            )
            self.aliases: str = humanize_list(cmd.aliases) if cmd.aliases else ""

    def get_doc(self) -> str:
        # Get header of command
        if self.is_slash:
            doc = f"{self.hashes} {self.name} ({SLASH} {COMMAND})\n"
        elif self.is_hybrid:
            doc = f"{self.hashes} {self.name} ({HYBRID} {COMMAND})\n"
        else:
            doc = f"{self.hashes} {self.name}\n"

        # Get command usage info
        if self.is_slash:
            usage = f"/{self.name} "
            arginfo = ""
            for i in self.options:
                name = i["name"]
                desc = i["description"]
                required = i.get("required", False)

                if required:
                    usage += f"<{name}> "
                    arginfo += f" - `{name}:` ({REQUIRED}) {desc}\n"
                else:
                    usage += f"[{name}] "
                    arginfo += f" - `{name}:` ({OPTIONAL}) {desc}\n"

            doc += f" - {USAGE}: `{usage}`\n"
            if arginfo:
                doc += f"{arginfo}\n"

            checks = []
            if self.cmd.nsfw:
                checks.append("NSFW")
            if self.cmd.guild_only:
                checks.append(GUILDONLY)
            if self.checks:
                doc += f" - {CHECKS}: `{humanize_list(checks)}\n"
        else:
            usage = f"[p]{self.name} "
            for k, v in self.cmd.clean_params.items():
                arg = v.name

                if v.required:
                    usage += f"<{arg}> "
                elif v.kind == v.KEYWORD_ONLY:
                    usage += f"[{arg}] "
                else:
                    usage += f"[{arg}={v.default}] "

            doc += f" - {USAGE}: `{usage}`\n"
            if self.is_hybrid:
                usage = usage.replace("[p]", "/")
                doc += f" - {SLASH} {USAGE}: `{usage}`\n"

            priv = self.perms.privilege_level
            if priv > 1:
                doc += f" - {RESTRICTED}: `{priv.name}`\n"

            if self.aliases:
                doc += f" - {ALIASES}: `{self.aliases}`\n"
            if self.cooldown:
                doc += f" - {COOLDOWN}: `{self.cooldown}`\n"
            if self.checks:
                doc += f" - {CHECKS}: `{self.checks}`\n"

        # Get command docstring
        if not doc.endswith("\n\n"):
            doc += "\n"
        doc += f"{self.desc}\n\n"

        # Get extended info
        if self.extended_info:
            ext = ""
            if self.is_slash:
                for p in self.cmd.parameters:
                    required = p.required
                    autocomplete = p.autocomplete
                    docstring = CONVERTERS.get(p.type)
                    cls = CLASSCONVERTER.get(p.type, "")

                    if not docstring and not cls:
                        log.warning(
                            f"Could not get docstring or class for {p} converter"
                        )
                        continue
                    elif not docstring:
                        log.warning(f"Could not get docstring for {p} converter")
                        continue
                    elif not cls:
                        log.warning(f"Could not get class for {p} converter")
                        continue

                    cstring = str(cls).replace("<class '", "").replace("'>", "")
                    ext += f"> ### {p.name}: {cstring}\n"
                    ext += f"> - {AUTOCOMPLETE}: {autocomplete}\n"

                    if not required:
                        ext += f"> - {DEFAULT}: {p.default}\n"

                    choices = [i.name for i in p.choices]
                    if choices:
                        ext += f"> - {CHOICES}: {choices}\n"

                    if not ext.endswith("\n\n"):
                        ext += "> \n"

                    if p.description:
                        ext += f"> {p.description}\n"

                    if not ext.endswith("\n\n"):
                        ext += "> \n"

                    if ".." in docstring:
                        docstring = docstring.split("..")[0]

                    split_by = "The lookup strategy is as follows (in order):"
                    if split_by in docstring:
                        docstring = docstring.split(split_by)[1]

                    for line in docstring.split("\n"):
                        if line.strip().startswith(">"):
                            line = line.replace(">", "")
                        ext += f"> {line}\n"
            else:
                for arg, p in self.cmd.clean_params.items():
                    converter = p.converter
                    try:
                        docstring = CONVERTERS.get(converter)
                    except TypeError:
                        log.warning(
                            f"Cant find {p} for the {arg} argument of the {self.name} command"
                        )
                        docstring = None

                    if not docstring and hasattr(converter, "__args__"):
                        docstring = CONVERTERS.get(converter.__args__[0])

                    if not docstring:
                        log.warning(f"Could not get docstring for {p} converter")
                        continue

                    ext += f"> ### {p}\n"

                    if p.description:
                        ext += f"> {p.description}\n"

                    if ".." in docstring:
                        docstring = docstring.split("..")[0]

                    split_by = "The lookup strategy is as follows (in order):"
                    if split_by in docstring:
                        docstring = docstring.split(split_by)[1]

                    for line in docstring.split("\n"):
                        if line.strip().startswith(">"):
                            line = line.replace(">", "")
                        ext += f"> {line}\n"

            if ext:
                doc += _("Extended Arg Info\n") + ext

        if self.prefix:
            doc = doc.replace("[p]", self.prefix)
        if self.replace_botname:
            doc = doc.replace("[botname]", self.bot.user.display_name)
        doc = doc.replace("guild", "server")
        return doc


# redgettext -D autodocs.py converters.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "Vertyco"
    __version__ = "0.3.154"

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
        replace_botname: bool,
        extended_info: bool,
        include_hidden: bool,
    ) -> str:
        docs = f"# {cog.qualified_name} {HELP}\n\n"

        cog_help = cog.help.replace("\n", "<br/>") if cog.help else None
        if cog_help:
            docs += f"{cog_help}\n\n"

        for cmd in cog.walk_app_commands():
            c = CustomCmdFmt(self.bot, cmd, prefix, replace_botname, extended_info)
            doc = c.get_doc()
            if not doc:
                log.warning(
                    f"Could not fetch docs for slash command {cmd.qualified_name}"
                )
                continue
            docs += doc

        for cmd in cog.walk_commands():
            if cmd.hidden and not include_hidden:
                continue
            c = CustomCmdFmt(self.bot, cmd, prefix, replace_botname, extended_info)
            doc = c.get_doc()
            if not doc:
                log.warning(f"Could not fetch docs for command {cmd.qualified_name}")
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
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:           `(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:     `(bool) If True, replaces the `prefix` placeholder with the bots prefix
        `replace_botname:    `(bool) If True, replaces the `botname` placeholder with the bots name
        `extended_info:      `(bool) If True, include extra info like converters and their docstrings
        `include_hidden:     `(bool) If True, includes hidden commands

        **Note**
        If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for them and sent in a zip file
        """
        prefix = (
            (await self.bot.get_valid_prefixes(ctx.guild))[0] if replace_prefix else ""
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
                        if cog.qualified_name in self.ignore:
                            continue
                        partial_func = functools.partial(
                            self.generate_readme,
                            cog,
                            prefix,
                            replace_botname,
                            extended_info,
                            include_hidden,
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
                )
                docs = await self.bot.loop.run_in_executor(None, partial_func)
                buffer = BytesIO(docs.encode())
                buffer.name = f"{cog.qualified_name}.md"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are your docs for {}!").format(cog.qualified_name)

            await ctx.send(txt, file=file)

    @makedocs.autocomplete("cog_name")
    async def get_cog_names(self, inter: discord.Interaction, current: str):
        cogs = set("all")
        for cmd in self.bot.walk_commands():
            cogs.add(str(cmd.cog_name).strip())
        return [
            app_commands.Choice(name=i, value=i) for i in cogs if current.lower() in i.lower()
        ][:25]
