import functools
import logging
from io import BytesIO
from typing import List, Literal, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

import discord
import pandas as pd
from aiocache import cached
from discord import app_commands
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n, set_contextual_locales_from_guild
from redbot.core.utils.mod import is_admin_or_superior, is_mod_or_superior

from .formatter import IGNORE, CustomCmdFmt

log = logging.getLogger("red.vrt.autodocs")
_ = Translator("AutoDocs", __file__)


# redgettext -D autodocs.py converters.py formatter.py
@cog_i18n(_)
class AutoDocs(commands.Cog):
    """
    Document your cogs with ease!

    Easily create documentation for any cog in Markdown format.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.0.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        txt = _("{}\nCog Version: {}\nAuthor: {}").format(helpcmd, self.__version__, self.__author__)
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
        include_help: bool,
        max_privilege_level: str,
        min_privilage_level: str = "user",
        embedding_style: bool = False,
    ) -> Tuple[str, pd.DataFrame]:
        columns = [_("name"), _("text")]
        rows = []
        cog_name = cog.qualified_name
        if include_help:
            helptxt = _("Help")
            docs = f"# {cog_name} {helptxt}\n\n"
            cog_help = cog.help if cog.help else None
            if not embedding_style and cog_help:
                cog_help = cog_help.replace("\n", "<br/>")
            if cog_help:
                docs += f"{cog_help}\n\n"
                entry_name = _("{} cog description").format(cog_name)
                rows.append([entry_name, f"{entry_name}\n{cog_help}"])
        else:
            docs = ""

        for cmd in cog.walk_app_commands():
            c = CustomCmdFmt(
                self.bot,
                cmd,
                prefix,
                replace_botname,
                extended_info,
                max_privilege_level,
                embedding_style,
                min_privilage_level,
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
                max_privilege_level,
                embedding_style,
                min_privilage_level,
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
        max_privilege_level=_("Hide commands above specified privilege level (user, mod, admin, guildowner, botowner)"),
        min_privilage_level=_("Hide commands below specified privilege level (user, mod, admin, guildowner, botowner)"),
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
        include_help: Optional[bool] = True,
        max_privilege_level: Literal["user", "mod", "admin", "guildowner", "botowner"] = "botowner",
        min_privilage_level: Literal["user", "mod", "admin", "guildowner", "botowner"] = "user",
        csv_export: Optional[bool] = False,
    ):
        """
        Create a Markdown docs page for a cog and send to discord

        **Arguments**
        `cog_name:            `(str) The name of the cog you want to make docs for (Case Sensitive)
        `replace_prefix:      `(bool) If True, replaces the `prefix` placeholder with the bots prefix
        `replace_botname:     `(bool) If True, replaces the `botname` placeholder with the bots name
        `extended_info:       `(bool) If True, include extra info like converters and their docstrings
        `include_hidden:      `(bool) If True, includes hidden commands
        `include_help:        `(bool) If True, includes the cog help text at the top of the docs
        `max_privilege_level: `(str) Hide commands above specified privilege level
        `min_privilage_level: `(str) Hide commands below specified privilege level
        - (user, mod, admin, guildowner, botowner)
        `csv_export:          `(bool) Include a csv with each command isolated per row for use as embeddings

        **Note** If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for
        them and sent in a zip file
        """
        await set_contextual_locales_from_guild(self.bot, ctx.guild)
        prefix = (await self.bot.get_valid_prefixes(ctx.guild))[0].strip() if replace_prefix else ""
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
                            include_help,
                            max_privilege_level,
                            min_privilage_level,
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
                    include_help,
                    max_privilege_level,
                    min_privilage_level,
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
        return [app_commands.Choice(name=i, value=i) for i in cogs if string.lower() in i.lower()][:25]

    @makedocs.autocomplete("cog_name")
    async def get_cog_names(self, inter: discord.Interaction, current: str):
        return await self.get_coglist(current)

    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # ------------------- ASSISTANT FUNCTION REGISTRATION --------------------
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
    async def get_command_info(
        self, guild: discord.Guild, user: discord.Member, command_name: str, *args, **kwargs
    ) -> str:
        command = self.bot.get_command(command_name)
        if not command:
            return "Command not found, check valid commands for this cog first"

        prefixes = await self.bot.get_valid_prefixes(guild)

        if user.id in self.bot.owner_ids:
            level = "botowner"
        elif user.id == guild.owner_id or user.guild_permissions.manage_guild:
            level = "guildowner"
        elif (await is_admin_or_superior(self.bot, user)) or user.guild_permissions.manage_roles:
            level = "admin"
        elif (await is_mod_or_superior(self.bot, user)) or user.guild_permissions.manage_messages:
            level = "mod"
        else:
            level = "user"

        c = CustomCmdFmt(self.bot, command, prefixes[0], True, False, level, True)
        doc = c.get_doc()
        if not doc:
            return "The user you are chatting with does not have the required permissions to use that command"

        return f"Cog name: {command.cog.qualified_name}\nCommand:\n{doc}"

    async def get_command_names(self, cog_name: str, *args, **kwargs):
        cog = self.bot.get_cog(cog_name)
        if not cog:
            return "Could not find that cog, check loaded cogs first"
        names = [i.qualified_name for i in cog.walk_app_commands()] + [i.qualified_name for i in cog.walk_commands()]
        joined = "\n".join(names)
        return f"Available commands for the {cog_name} cog:\n{joined}"

    async def get_cog_info(self, cog_name: str, *args, **kwargs):
        cog = self.bot.get_cog(cog_name)
        if not cog:
            return "Could not find that cog, check loaded cogs first"
        if desc := cog.help:
            return f"Description of the {cog_name} cog: {desc}"
        return "This cog has no description"

    async def get_cog_list(self, *args, **kwargs):
        joined = "\n".join([i for i in self.bot.cogs])
        return f"Currently loaded cogs:\n{joined}"

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        """Registers a command with Assistant enabling it to access to command docs"""
        schemas = []

        schema = {
            "name": "get_command_info",
            "description": "Get info about a specific command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command_name": {
                        "type": "string",
                        "description": "name of the command",
                    },
                },
                "required": ["command_name"],
            },
        }
        schemas.append(schema)

        schema = {
            "name": "get_command_names",
            "description": "Get a list of commands for a cog",
            "parameters": {
                "type": "object",
                "properties": {
                    "cog_name": {
                        "type": "string",
                        "description": "name of the cog, case sensitive",
                    }
                },
                "required": ["cog_name"],
            },
        }
        schemas.append(schema)

        schema = {
            "name": "get_cog_info",
            "description": "Get the description for a cog",
            "parameters": {
                "type": "object",
                "properties": {
                    "cog_name": {
                        "type": "string",
                        "description": "name of the cog, case sensitive",
                    }
                },
                "required": ["cog_name"],
            },
        }
        schemas.append(schema)

        schema = {
            "name": "get_cog_list",
            "description": "Get a list of currently loaded cogs by name",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
        schemas.append(schema)

        await cog.register_functions(self.qualified_name, schemas)
