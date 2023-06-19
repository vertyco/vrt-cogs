import functools
import logging
from io import BytesIO
from typing import List, Literal, Optional, Tuple, Union
from zipfile import ZIP_DEFLATED, ZipFile

import discord
import pandas as pd
from aiocache import cached
from discord import app_commands
from discord.app_commands.commands import Command as SlashCommand
from discord.ext.commands.hybrid import HybridAppCommand
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.commands import HybridCommand, HybridGroup
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
    __version__ = "0.6.0"

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
        embedding_style: bool = False,
    ) -> Tuple[str, pd.DataFrame]:
        columns = [_("name"), _("text")]
        rows = []
        cog_name = cog.qualified_name
        docs = f"# {cog_name} {HELP}\n\n"
        cog_help = cog.help if cog.help else None
        if not embedding_style and cog_help:
            cog_help = cog_help.replace("\n", "<br/>")
        if cog_help:
            docs += f"{cog_help}\n\n"
            entry_name = _("{} cog description").format(cog_name)
            rows.append([entry_name, f"{entry_name}\n{cog_help}"])

        for cmd in cog.walk_app_commands():
            c = CustomCmdFmt(
                self.bot,
                cmd,
                prefix,
                replace_botname,
                extended_info,
                privilege_level,
                embedding_style,
            )
            doc = c.get_doc()
            if not doc:
                continue
            docs += doc
            csv_name = f"{c.name} command for {cog_name} cog"
            rows.append([csv_name, f"{csv_name}\n{doc}"])

        ignored = []
        for cmd in cog.walk_commands():
            if cmd.hidden and not include_hidden:
                continue
            c = CustomCmdFmt(
                self.bot,
                cmd,
                prefix,
                replace_botname,
                extended_info,
                privilege_level,
                embedding_style,
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
            csv_name = f"{c.name} command for {cog_name} cog"
            rows.append([csv_name, f"{csv_name}\n{doc}"])
        df = pd.DataFrame(rows, columns=columns)
        return docs, df

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
        csv_export=_("Include a csv with each command isolated per row"),
    )
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def makedocs(
        self,
        ctx: commands.Context,
        cog_name: str,
        replace_prefix: Optional[bool] = False,
        replace_botname: Optional[bool] = False,
        extended_info: Optional[bool] = False,
        include_hidden: Optional[bool] = False,
        privilege_level: Literal["user", "mod", "admin", "guildowner", "botowner"] = "botowner",
        csv_export: Optional[bool] = False,
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:           `(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:     `(bool) If True, replaces the `prefix` placeholder with the bots prefix
        `replace_botname:    `(bool) If True, replaces the `botname` placeholder with the bots name
        `extended_info:      `(bool) If True, include extra info like converters and their docstrings
        `include_hidden:     `(bool) If True, includes hidden commands
        `privilege_level:    `(str) Hide commands above specified privilege level
        - (user, mod, admin, guildowner, botowner)
        `csv_export:         `(bool) Include a csv with each command isolated per row for use as embeddings

        **Note** If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for
        them and sent in a zip file
        """
        prefix = (
            (await self.bot.get_valid_prefixes(ctx.guild))[0].strip() if replace_prefix else ""
        )
        async with ctx.typing():
            if cog_name == "all":
                buffer = BytesIO()
                folder_name = _("AllCogDocs")
                with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
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
                            csv_export,
                        )
                        docs, df = await self.bot.loop.run_in_executor(None, partial_func)
                        filename = f"{folder_name}/{cog.qualified_name}.md"

                        if csv_export:
                            tmp = BytesIO()
                            df.to_csv(tmp, index=False)
                            arc.writestr(
                                filename.replace(".md", ".csv"),
                                tmp.getvalue(),
                                compress_type=ZIP_DEFLATED,
                                compresslevel=9,
                            )
                        else:
                            arc.writestr(
                                filename,
                                docs,
                                compress_type=ZIP_DEFLATED,
                                compresslevel=9,
                            )

                buffer.name = f"{folder_name}.zip"
                buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are the docs for all of your currently loaded cogs!")
            else:
                cog = self.bot.get_cog(cog_name)
                if not cog:
                    return await ctx.send(_("I could not find that cog, maybe it is not loaded?"))
                partial_func = functools.partial(
                    self.generate_readme,
                    cog,
                    prefix,
                    replace_botname,
                    extended_info,
                    include_hidden,
                    privilege_level,
                    csv_export,
                )
                docs, df = await self.bot.loop.run_in_executor(None, partial_func)
                if csv_export:
                    buffer = BytesIO()
                    df.to_csv(buffer, index=False)
                    buffer.name = f"{cog.qualified_name}.csv"
                    buffer.seek(0)
                else:
                    buffer = BytesIO(docs.encode())
                    buffer.name = f"{cog.qualified_name}.md"
                    buffer.seek(0)
                file = discord.File(buffer)
                txt = _("Here are your docs for {}!").format(cog.qualified_name)
            if file.__sizeof__() > ctx.guild.filesize_limit:
                await ctx.send("File size too large!")
            else:
                await ctx.send(txt, file=file)

    @cached(ttl=8)
    async def get_coglist(self, string: str) -> List[app_commands.Choice]:
        cogs = set("all")
        for cmd in self.bot.walk_commands():
            cogs.add(str(cmd.cog_name).strip())
        return [app_commands.Choice(name=i, value=i) for i in cogs if string.lower() in i.lower()][
            :25
        ]

    @makedocs.autocomplete("cog_name")
    async def get_cog_names(self, inter: discord.Interaction, current: str):
        return await self.get_coglist(current)

    async def get_command_doc(
        self,
        guild: discord.Guild,
        command: Union[
            HybridGroup,
            HybridCommand,
            HybridAppCommand,
            SlashCommand,
            commands.Command,
        ],
    ):
        prefixes = await self.bot.get_valid_prefixes(guild)
        c = CustomCmdFmt(self.bot, command, prefixes[0], True, False, "guildowner", True)
        return c.get_doc()

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        """Registers a command with Assistant enabling it to access to command docs"""

        async def get_command_info(
            bot: Red, guild: discord.Guild, command_name: str, *args, **kwargs
        ) -> str:
            cog = bot.get_cog("AutoDocs")
            if not cog:
                return "Cog not loaded!"
            command = bot.get_command(command_name)
            if not command:
                return "Command not found, try running the get_command_names function to get valid commands"
            doc = await cog.get_command_doc(guild, command)
            if not doc:
                return "Failed to fetch info for that command!"
            return f"Cog name: {cog.qualified_name}\nCommand:\n{doc}"

        schema = {
            "name": "get_command_info",
            "description": "Get info about a specific discord bot command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command_name": {
                        "type": "string",
                        "description": "the name of the command (Hint: Use the get_command_names function first to fetch valid names)",
                    },
                },
                "required": ["command_name"],
            },
        }

        await cog.register_function(self, schema, get_command_info)

        async def get_command_names(bot: Red, cog_name: str = None, *args, **kwargs):
            from redbot.core.utils.chat_formatting import humanize_list

            if cog_name:
                cog = bot.get_cog(cog_name)
                if not cog:
                    return "Could not find that cog, try searching a different cog or not including a cog name when searching"
                names = [i.qualified_name for i in cog.walk_app_commands()] + [
                    i.qualified_name for i in cog.walk_commands()
                ]
            else:
                names = [i.qualified_name for i in bot.walk_commands()]
            return humanize_list(names)

        schema = {
            "name": "get_command_names",
            "description": "Get a list of available discord bot commands, (Hint: Use this before using the get_command_info function)",
            "parameters": {
                "type": "object",
                "properties": {
                    "cog_name": {
                        "type": "string",
                        "description": "the name of the cog, case sensitive (Hint: Use the get_cog_list function to get valid cog names)",
                    }
                },
            },
        }

        await cog.register_function(self, schema, get_command_names)

        async def get_cog_list(bot: Red, *args, **kwargs):
            from redbot.core.utils.chat_formatting import humanize_list

            return humanize_list([i for i in bot.cogs])

        schema = {
            "name": "get_cog_list",
            "description": "Get a list of currently loaded cogs, use this to help search for commands",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }

        await cog.register_function(self, schema, get_cog_list)
