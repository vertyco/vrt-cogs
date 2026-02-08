import logging
from typing import Optional, Union

from discord.app_commands.commands import Command as SlashCommand
from discord.ext.commands.hybrid import HybridAppCommand
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.commands import HybridCommand, HybridGroup
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .converters import CLASSCONVERTER, PRIVILEGES, get_converter_docstring

log = logging.getLogger("red.vrt.autodocs.formatter")
_ = Translator("AutoDocs", __file__)


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


def _is_block_start_or_end(line: str) -> bool:
    return line.startswith("```")


class CustomCmdFmt:
    """Formats documentation for a single command"""

    def __init__(
        self,
        bot: Red,
        cmd: Union[
            HybridGroup,
            HybridCommand,
            HybridAppCommand,
            SlashCommand,
            commands.Command,
        ],
        prefix: str,
        replace_botname: bool,
        extended_info: bool,
        privilege_level: str,
        embedding_style: bool = False,
        min_privilege_level: str = "user",
    ):
        self.bot = bot
        self.cmd = cmd
        self.prefix = prefix
        self.replace_botname = replace_botname
        self.extended_info = extended_info
        self.privilege_level = privilege_level
        self.embedding_style = embedding_style
        self.min_privilege_level = min_privilege_level

        self.is_slash: bool = isinstance(cmd, SlashCommand)
        self.is_hybrid: bool = isinstance(cmd, (HybridGroup, HybridCommand, HybridAppCommand))

        try:
            self.checks: str = humanize_list([i.__qualname__.split(".")[0] for i in cmd.checks]).strip()
        except AttributeError:
            self.checks = ""

        self.name: str = cmd.qualified_name
        self.hashes: str = (len(self.name.split(" ")) + 1) * "#"

        if self.is_slash:
            try:
                self.options = cmd.to_dict()["options"]
            except TypeError:
                self.options = cmd.to_dict(self.bot.tree)["options"]
            self.desc: str = cmd.description or ""
        else:
            try:
                self.desc: str = cmd.help or ""
            except AttributeError:
                self.desc: str = cmd.description or ""
            try:
                self.perms = self.cmd.requires
                cd = cmd.cooldown
                aliases = cmd.aliases
            except AttributeError:
                self.perms = None
                cd = None
                aliases = None
            PER = _("per")
            SECONDS = _("seconds")
            SECOND = _("second")
            self.cooldown: str = f"{cd.rate} {PER} {cd.per} {SECOND if int(cd.per) == 1 else SECONDS}" if cd else None
            self.aliases: str = humanize_list(aliases) if aliases else ""

        if not self.embedding_style:
            # Replace any newlines NOT inside a code block with <br/>
            lines = self.desc.split("\n")
            inside_code_block = False
            for i, line in enumerate(lines):
                if _is_block_start_or_end(line):
                    inside_code_block = not inside_code_block
                elif not inside_code_block and line:
                    lines[i] = line + "<br/>"
            self.desc = "\n".join(lines)

    def get_doc(self) -> Optional[str]:
        # Get header of command
        SLASH = _("Slash")
        COMMAND = _("Command")
        prefix = self.prefix if self.prefix else "[p]"
        if self.is_slash:
            doc = f"{self.hashes} /{self.name} ({SLASH} {COMMAND})\n\n"
        elif self.is_hybrid:
            HYBRID = _("Hybrid")
            doc = f"{self.hashes} {prefix}{self.name} ({HYBRID} {COMMAND})\n\n"
        else:
            doc = f"{self.hashes} {prefix}{self.name}\n\n"

        if self.embedding_style:
            doc = doc.lstrip("#").strip() + "\n"

        # Get command docstring
        if self.desc.strip():
            doc += f"{self.desc.strip()}\n\n"

        USAGE = _("Usage")
        CHECKS = _("Checks")

        # Get command usage info
        if self.is_slash:
            usage = f"/{self.name}"
            arginfo = ""
            for i in self.options:
                name = i["name"]
                desc = f" {i['description']}" if i["description"] != "..." else ""
                required = i.get("required", False)

                if required:
                    REQUIRED = _("Required")
                    usage += f" <{name}>"
                    arginfo += f" - `{name}:` ({REQUIRED}){desc}\n"
                else:
                    OPTIONAL = _("Optional")
                    usage += f" [{name}]"
                    arginfo += f" - `{name}:` ({OPTIONAL}){desc}\n"

            doc += f" - {USAGE}: `{usage}`\n"
            if arginfo:
                doc += f"{arginfo}\n"

            checks = []
            if self.cmd.nsfw:
                checks.append("NSFW")
            if self.cmd.guild_only:
                GUILDONLY = _("Server Only")
                checks.append(GUILDONLY)
            if checks:
                doc += f" - {CHECKS}: `{humanize_list(checks)}`\n"
        else:
            usage = f"[p]{self.name}"
            try:
                for k, v in self.cmd.clean_params.items():
                    arg = v.name

                    if v.required:
                        usage += f" <{arg}>"
                    elif v.kind == v.KEYWORD_ONLY:
                        usage += f" [{arg}]"
                    else:
                        usage += f" [{arg}={v.default}]"
            except AttributeError:
                pass

            doc += f" - {USAGE}: `{usage}`\n"
            if self.is_hybrid:
                usage = usage.replace("[p]", "/")
                doc += f" - {SLASH} {USAGE}: `{usage}`\n"

            limit = PRIVILEGES[self.privilege_level]
            minimum = PRIVILEGES[self.min_privilege_level]
            if perms := self.perms:
                priv = perms.privilege_level
                if priv:
                    if priv.value > limit:
                        return None
                    if priv.value < minimum:
                        return None
                    if priv.value > 1:
                        RESTRICTED = _("Restricted to")
                        doc += f" - {RESTRICTED}: `{priv.name}`\n"

            if self.aliases:
                ALIASES = _("Aliases")
                doc += f" - {ALIASES}: `{self.aliases}`\n"
            if self.cooldown:
                COOLDOWN = _("Cooldown")
                doc += f" - {COOLDOWN}: `{self.cooldown}`\n"
            if self.checks.strip():
                doc += f" - {CHECKS}: `{self.checks.strip()}`\n"

        # Get extended info
        if self.extended_info:
            ext = ""
            if self.is_slash:
                for p in self.cmd.parameters:
                    required = p.required
                    autocomplete = p.autocomplete
                    docstring = get_converter_docstring(p.type)
                    cls = CLASSCONVERTER.get(p.type, "")

                    if not docstring and not cls:
                        err = _("Could not get docstring or class for {} converter").format(str(p))
                        log.warning(err)
                        continue
                    elif not docstring:
                        err = _("Could not get docstring for {} converter").format(str(p))
                        log.warning(err)
                        continue
                    elif not cls:
                        err = _("Could not get class for {} converter").format(str(p))
                        log.warning(err)
                        continue

                    cstring = str(cls).replace("<class '", "").replace("'>", "")
                    if self.embedding_style:
                        ext += f"> {p.name}: {cstring}\n"
                    else:
                        ext += f"> ### {p.name}: {cstring}\n"
                    AUTOCOMPLETE = _("Autocomplete")
                    ext += f"> - {AUTOCOMPLETE}: {autocomplete}\n"

                    if not required:
                        DEFAULT = _("Default")
                        ext += f"> - {DEFAULT}: {p.default}\n"

                    choices = [i.name for i in p.choices]
                    if choices:
                        CHOICES = _("Choices")
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
                try:
                    for arg, p in self.cmd.clean_params.items():
                        converter = p.converter
                        try:
                            docstring = get_converter_docstring(converter)
                        except TypeError:
                            err = _("Could not find {} for the {} argument of the {} command").format(p, arg, self.name)
                            log.warning(err)
                            docstring = None

                        if not docstring and hasattr(converter, "__args__"):
                            docstring = get_converter_docstring(converter.__args__[0])

                        if not docstring:
                            err = _("Could not get docstring for {} converter").format(str(p))
                            log.warning(err)
                            continue

                        if self.embedding_style:
                            ext += f"> {p}\n"
                        else:
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
                except AttributeError:
                    pass

            if ext:
                EXTENDED = _("Extended Arg Info")
                doc += f"\n{EXTENDED}\n\n{ext}"

        if self.prefix:
            doc = doc.replace("[p]", self.prefix)
        if self.replace_botname:
            doc = doc.replace("[botname]", self.bot.user.display_name)

        # Ensure spacing between commands
        if not doc.endswith("\n\n"):
            doc += "\n"

        return doc
