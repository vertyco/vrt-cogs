import logging
from typing import Optional, Union

from discord.app_commands.commands import Command as SlashCommand
from discord.ext.commands.hybrid import HybridAppCommand
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.commands import HybridCommand, HybridGroup
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .converters import CLASSCONVERTER, CONVERTERS, PRIVILEGES

log = logging.getLogger("red.vrt.autodocs.formatter")
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

# Core cog ignore list
IGNORE = [
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
        privilege_level: str,
    ):
        self.bot = bot
        self.cmd = cmd
        self.prefix = prefix
        self.replace_botname = replace_botname
        self.extended_info = extended_info
        self.privilege_level = privilege_level

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
            self.desc: str = cmd.description.replace("\n", "<br/>").replace("`", "")
        else:
            try:
                self.desc: str = cmd.help.replace("\n", "<br/>").replace("`", "")
            except AttributeError:
                self.desc: str = cmd.description.replace("\n", "<br/>").replace("`", "")

            self.perms = self.cmd.requires
            cd = cmd.cooldown
            self.cooldown: str = (
                f"{cd.rate} {PER} {cd.per} {SECOND if int(cd.per) == 1 else SECONDS}"
                if cd
                else None
            )
            self.aliases: str = humanize_list(cmd.aliases) if cmd.aliases else ""

    def get_doc(self) -> Optional[str]:
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

            limit = PRIVILEGES[self.privilege_level]
            priv = self.perms.privilege_level
            if priv:
                if priv.value > limit:
                    return None
                if priv.value > 1:
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
                        err = _(
                            "Could not get docstring or class for {} converter"
                        ).format(str(p))
                        log.warning(err)
                        continue
                    elif not docstring:
                        err = _("Could not get docstring for {} converter").format(
                            str(p)
                        )
                        log.warning(err)
                        continue
                    elif not cls:
                        err = _("Could not get class for {} converter").format(str(p))
                        log.warning(err)
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
                        err = _(
                            "Could not find {} for the {} argument of the {} command"
                        ).format(p, arg, self.name)
                        log.warning(err)
                        docstring = None

                    if not docstring and hasattr(converter, "__args__"):
                        docstring = CONVERTERS.get(converter.__args__[0])

                    if not docstring:
                        err = _("Could not get docstring for {} converter").format(
                            str(p)
                        )
                        log.warning(err)
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
