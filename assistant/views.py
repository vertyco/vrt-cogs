import asyncio
import inspect
import json
import logging
from contextlib import suppress
from typing import Callable, Dict, List, Tuple

import discord
import json5
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify, text_to_file

from .common.models import DB, CustomFunction, Embedding, GuildSettings
from .common.utils import (
    code_string_valid,
    extract_code_blocks,
    get_attachments,
    json_schema_invalid,
    wait_message,
)

log = logging.getLogger("red.vrt.assistant.views")
_ = Translator("Assistant", __file__)
ON_EMOJI = "\N{ON WITH EXCLAMATION MARK WITH LEFT RIGHT ARROW ABOVE}"
OFF_EMOJI = "\N{MOBILE PHONE OFF}"


class APIModal(discord.ui.Modal):
    def __init__(self, key: str = None):
        self.key = key
        super().__init__(title=_("Set API Key"), timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Enter your API Key below"),
            style=discord.TextStyle.short,
            default=self.key,
            required=False,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.key = self.field.value
        await interaction.response.defer()
        self.stop()


class SetAPI(discord.ui.View):
    def __init__(self, author: discord.Member, key: str = None):
        self.author = author
        self.key = key
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set API Key", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        modal = APIModal(key=self.key)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.key = modal.key
        if modal.key:
            self.stop()


class EmbeddingModal(discord.ui.Modal):
    def __init__(self, title: str, name: str = None, text: str = None):
        super().__init__(title=title, timeout=None)
        self.name = ""
        self.text = ""

        self.name_field = discord.ui.TextInput(
            label=_("Entry name"),
            style=discord.TextStyle.short,
            default=name,
            required=True,
            max_length=250,
        )
        self.add_item(self.name_field)
        self.text_field = discord.ui.TextInput(
            label=_("Training context"),
            style=discord.TextStyle.paragraph,
            default=text,
            required=True,
        )
        self.add_item(self.text_field)

    async def on_submit(self, interaction: discord.Interaction):
        self.name = self.name_field.value
        self.text = self.text_field.value
        await interaction.response.defer()
        self.stop()


class SearchModal(discord.ui.Modal):
    def __init__(self, title: str, current: str = None):
        self.query = None
        super().__init__(title=title, timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Search Query"),
            style=discord.TextStyle.short,
            required=True,
            default=current,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.field.value
        await interaction.response.defer()
        self.stop()


class EmbeddingMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        conf: GuildSettings,
        save_func: Callable,
        fetch_pages: Callable,
        embed_method: Callable,
    ):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.conf = conf
        self.save = save_func
        self.fetch_pages = fetch_pages
        self.embed_method = embed_method

        self.has_skip = True
        self.place = 0
        self.page = 0
        self.pages: List[discord.Embed] = []
        self.message: discord.Message = None
        self.tasks: List[asyncio.Task] = []

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        with suppress(discord.HTTPException):
            await self.message.edit(view=None)
        for task in self.tasks:
            await task
        return await super().on_timeout()

    async def get_pages(self) -> None:
        self.pages = await self.fetch_pages(self.conf, self.place)
        if len(self.pages) > 30 and not self.has_skip:
            self.add_item(self.left10)
            self.add_item(self.right10)
            self.has_skip = True
        elif len(self.pages) <= 30 and self.has_skip:
            self.remove_item(self.left10)
            self.remove_item(self.right10)
            self.has_skip = False

    def change_place(self, inc: int):
        current = self.pages[self.page]
        if not current.fields:
            return
        old_place = self.place
        self.place += inc
        self.place %= len(current.fields)
        for embed in self.pages:
            # Cleanup old place
            if len(embed.fields) > old_place:
                embed.set_field_at(
                    old_place,
                    name=embed.fields[old_place].name.replace("➣ ", "", 1),
                    value=embed.fields[old_place].value,
                    inline=False,
                )
            # Add new place
            if len(embed.fields) > self.place:
                embed.set_field_at(
                    self.place,
                    name="➣ " + embed.fields[self.place].name.replace("➣ ", "", 1),
                    value=embed.fields[self.place].value,
                    inline=False,
                )

    async def add_embedding(self, name: str, text: str):
        embedding = await self.embed_method(text, self.conf)
        if not embedding:
            return await self.ctx.send(_("Failed to process embedding `{}`\nContent: ```\n{}\n```").format(name, text))
        if name in self.conf.embeddings:
            return await self.ctx.send(_("An embedding with the name `{}` already exists!").format(name))
        self.conf.embeddings[name] = Embedding(
            text=text,
            embedding=embedding,
            model=self.conf.get_embed_model(
                self.db.endpoint_override, self.db.ollama_models or None, self.db.endpoint_is_ollama
            ),
        )
        await asyncio.to_thread(self.conf.sync_embeddings, self.ctx.guild.id)
        await self.get_pages()
        with suppress(discord.NotFound):
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)
        await self.ctx.send(_("Your embedding labeled `{}` has been processed!").format(name))
        await self.save()

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.primary,
        emoji="\N{PRINTER}\N{VARIATION SELECTOR-16}",
    )
    async def view(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to inspect!"), ephemeral=True)
        await interaction.response.defer()
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        embedding = self.conf.embeddings[name]
        for p in pagify(embedding.text, page_length=4000):
            embed = discord.Embed(description=p)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{UPWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.pages[self.page].fields:
            self.change_place(-1)
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{MEMO}")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to edit!"), ephemeral=True)
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        embedding_obj = self.conf.embeddings[name]
        modal = EmbeddingModal(title="Edit embedding", name=name, text=embedding_obj.text[:4000])
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        embedding = await self.embed_method(modal.text, self.conf)
        if not embedding:
            return await interaction.followup.send(
                _("Failed to edit that embedding, please try again later"), ephemeral=True
            )
        embedding_obj.text = modal.text
        embedding_obj.embedding = embedding
        embedding_obj.update()
        self.conf.embeddings[modal.name] = embedding_obj
        if modal.name != name:
            del self.conf.embeddings[name]
        await asyncio.to_thread(self.conf.sync_embeddings, self.ctx.guild.id)
        await self.get_pages()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await interaction.followup.send(_("Your embedding has been modified!"), ephemeral=True)
        await self.save()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        row=1,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        new_place = min(self.place, len(self.pages[self.page].fields) - 1)
        if place_change := self.place - new_place:
            self.change_place(-place_change)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{CROSS MARK}", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
        for task in self.tasks:
            await task
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        row=1,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        new_place = min(self.place, len(self.pages[self.page].fields) - 1)
        if place_change := self.place - new_place:
            self.change_place(-place_change)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{SQUARED NEW}", row=2)
    async def new_embedding(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbeddingModal(title=_("Add an embedding"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        self.tasks.append(asyncio.create_task(self.add_embedding(modal.name, modal.text)))
        await interaction.followup.send(_("Your embedding is processing and will appear when ready!"), ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{DOWNWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        row=2,
    )
    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.pages[self.page].fields:
            self.change_place(1)
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to delete!"), ephemeral=True)
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        await interaction.response.send_message(_("Deleted `{}` embedding.").format(name), ephemeral=True)
        del self.conf.embeddings[name]
        await self.get_pages()
        self.page %= len(self.pages)
        self.message = await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}",
        row=3,
    )
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        self.place = min(self.place, len(self.pages[self.page].fields) - 1)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
        row=3,
    )
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.conf.embeddings:
            return await interaction.response.send_message(_("No embeddings to search!"), ephemeral=True)
        modal = SearchModal(_("Search for an embedding"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return
        query = modal.query.lower()

        def _get_matches():
            matches: List[Tuple[int, int]] = []
            for name, embedding in self.conf.embeddings.items():
                if query == name.lower():
                    matches.append((name, 100))
                    break
                if query in embedding.text.lower():
                    matches.append((name, 98))
                    continue
                matches.append((name, fuzz.ratio(query, name.lower())))
                matches.append((name, fuzz.ratio(query, embedding.text.lower())))
            if len(matches) > 1:
                matches.sort(key=lambda x: x[1], reverse=True)

            return matches

        sorted_embeddings = await asyncio.to_thread(_get_matches)
        embedding_name = sorted_embeddings[0][0]
        await interaction.followup.send(_("Search result: **{}**").format(embedding_name), ephemeral=True)
        for page_index, embed in enumerate(self.pages):
            found = False
            for place_index, field in enumerate(embed.fields):
                name = field.name.replace("➣ ", "", 1)
                if name == embedding_name:
                    self.page = page_index
                    self.place = place_index
                    found = True
                    break
            if found:
                break
        await self.get_pages()
        self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        row=3,
    )
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        self.place = min(self.place, len(self.pages[self.page].fields) - 1)
        await self.message.edit(embed=self.pages[self.page], view=self)


class CodeModal(discord.ui.Modal):
    def __init__(self, schema: str, code: str, permission_level: str = None):
        super().__init__(title=_("Function Edit"), timeout=None)

        self.schema = ""
        self.code = ""
        self.permission_level = ""

        self.schema_field = discord.ui.TextInput(
            label=_("JSON Schema"),
            style=discord.TextStyle.paragraph,
            default=schema,
        )
        self.add_item(self.schema_field)
        self.code_field = discord.ui.TextInput(
            label=_("Code"),
            style=discord.TextStyle.paragraph,
            default=code,
        )
        self.add_item(self.code_field)
        self.perm_field = discord.ui.TextInput(
            label=_("Permission Level"),
            placeholder=_("User, Mod, Admin, or Owner"),
            style=discord.TextStyle.short,
            default=permission_level,
        )
        self.add_item(self.perm_field)

    async def on_submit(self, interaction: discord.Interaction):
        self.schema = self.schema_field.value
        self.code = self.code_field.value
        if self.perm_field.value.lower() not in ("user", "mod", "admin", "owner"):
            return await interaction.response.send_message(
                _("Invalid permission level, must be one of `User`, `Mod`, `Admin`, or `Owner`"),
                ephemeral=True,
            )
        self.permission_level = self.perm_field.value.lower()
        await interaction.response.defer()
        self.stop()


class CodeMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        registry: Dict[str, Dict[str, dict]],
        save_func: Callable,
        fetch_pages: Callable,
    ):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.db = db
        self.conf = db.get_conf(ctx.guild)
        self.registry = registry
        self.save = save_func
        self.fetch_pages = fetch_pages

        self.has_skip = True

        self.page = 0
        self.pages: List[discord.Embed] = []
        self.message: discord.Message = None

        if ctx.author.id not in ctx.bot.owner_ids:
            self.remove_item(self.new_function)
            self.remove_item(self.delete)
            self.remove_item(self.edit)
            self.remove_item(self.view_function)

            # Let users see but not touch
            if not ctx.author.guild_permissions.manage_guild:
                self.remove_item(self.toggle)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        with suppress(discord.HTTPException):
            await self.message.edit(view=None)
        return await super().on_timeout()

    async def get_pages(self) -> None:
        self.pages = await self.fetch_pages(self.ctx.author)
        self.update_button()
        if len(self.pages) > 30 and not self.has_skip:
            self.add_item(self.left10)
            self.add_item(self.right10)
            self.close.row = 2
            self.has_skip = True
        elif len(self.pages) <= 30 and self.has_skip:
            self.remove_item(self.left10)
            self.remove_item(self.right10)
            self.close.row = 0
            self.has_skip = False

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    def test_func(self, function_string: str) -> bool:
        try:
            compile(function_string, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def schema_valid(self, schema: dict) -> str:
        missing = ""
        if "name" not in schema:
            missing += "- `name`\n"
        if "description" not in schema:
            missing += "- `description`\n"
        if "parameters" not in schema:
            missing += "- `parameters`\n"
        if "parameters" in schema:
            if "type" not in schema["parameters"]:
                missing += "- `type` in **parameters**\n"
            if "properties" not in schema["parameters"]:
                missing = "- `properties` in **parameters**\n"
        return missing

    def update_button(self):
        if not self.pages:
            return
        if not self.pages[self.page].fields:
            return
        function_name = self.pages[self.page].description
        enabled = self.conf.function_statuses.get(function_name, False)
        if enabled:
            self.toggle.emoji = ON_EMOJI
            self.toggle.style = discord.ButtonStyle.success
        else:
            self.toggle.emoji = OFF_EMOJI
            self.toggle.style = discord.ButtonStyle.secondary

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}")
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{CROSS MARK}")
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}")
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{PRINTER}\N{VARIATION SELECTOR-16}", row=1)
    async def view_function(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to inspect!"), ephemeral=True)
        function_name = self.pages[self.page].description
        if function_name in self.db.functions:
            function_schema = self.db.functions[function_name].jsonschema
            function_code = self.db.functions[function_name].code
        else:
            # Registered function
            for cog_name, functions in self.registry.items():
                cog = self.ctx.bot.get_cog(cog_name)
                if not cog:
                    continue
                if function_name in functions:
                    function_schema = functions[function_name]
                    function_obj = getattr(cog, function_name, None)
                    if not function_obj:
                        continue
                    function_code = inspect.getsource(function_obj)
                    break
            else:
                return await interaction.response.send_message("Cannot find function!")
        files = [
            text_to_file(function_code, f"{function_name}.py"),
            text_to_file(json.dumps(function_schema, indent=2), f"{function_name}.json"),
        ]
        await interaction.response.send_message(_("Here are your custom functions"), files=files)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{SQUARED NEW}", row=1)
    async def new_function(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=_(
                "Reply to this message with the json schema for your function\n"
                "- [Example Functions](https://github.com/vertyco/vrt-cogs/tree/main/assistant/example-funcs)"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)
        message = await wait_message(self.ctx)
        if not message:
            return
        attachments = get_attachments(message)
        try:
            if attachments:
                text = (await attachments[0].read()).decode()
            else:
                text = message.content
            if extracted := extract_code_blocks(text):
                schema: dict = json5.loads(extracted[0].strip())
            else:
                schema: dict = json5.loads(text.strip())
        except Exception as e:
            return await interaction.followup.send(_("SchemaError\n{}").format(box(str(e), "py")))
        if not schema:
            return await interaction.followup.send(_("Empty schema!"))

        if missing := json_schema_invalid(schema):
            return await interaction.followup.send(_("Invalid schema!\n**Missing**\n{}").format(missing))

        function_name = schema["name"]
        embed = discord.Embed(
            description=_("Reply to this message with the custom code"),
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed)
        message = await wait_message(self.ctx)
        if not message:
            return
        attachments = get_attachments(message)
        if attachments:
            code = (await attachments[0].read()).decode()
        else:
            code = message.content.strip()
        if extracted := extract_code_blocks(code):
            code = extracted[0]
        if not code_string_valid(code):
            return await interaction.followup.send(_("Invalid function"))

        entry = CustomFunction(code=code, jsonschema=schema)
        if function_name in self.db.functions:
            await interaction.followup.send(_("`{}` has been overwritten!").format(function_name))
        else:
            await interaction.followup.send(_("`{}` has been created!").format(function_name))
        self.db.functions[function_name] = entry
        await self.get_pages()
        self.page = len(self.pages) - 1
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{MEMO}")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to edit!"), ephemeral=True)

        function_name = self.pages[self.page].description
        if function_name not in self.db.functions:
            for cog, functions in self.registry.items():
                if function_name in functions:
                    break
            else:
                return await interaction.response.send_message(_("Could not find function!"), ephemeral=True)
            return await interaction.response.send_message(
                _("This function is managed by the `{}` cog and cannot be edited").format(cog),
                ephemeral=True,
            )
        entry = self.db.functions[function_name]
        if len(json.dumps(entry.jsonschema, indent=2)) > 4000:
            return await interaction.response.send_message(
                _("The json schema for this function is too long, you'll need to re-upload it to modify"),
                ephemeral=True,
            )
        if len(entry.code) > 4000:
            return await interaction.response.send_message(
                _("The code for this function is too long, you'll need to re-upload it to modify"),
                ephemeral=True,
            )

        modal = CodeModal(json.dumps(entry.jsonschema, indent=2), entry.code, entry.permission_level)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.schema or not modal.code:
            return
        text = modal.schema
        try:
            schema: dict = json5.loads(text.strip())
        except Exception as e:
            return await interaction.followup.send(_("SchemaError\n{}").format(box(str(e), "py")), ephemeral=True)
        if not schema:
            return await interaction.followup.send(_("Empty schema!"))
        if missing := json_schema_invalid(schema):
            return await interaction.followup.send(
                _("Invalid schema!\n**Missing**\n{}").format(missing), ephemeral=True
            )
        new_name = schema["name"]

        code = modal.code
        if not code_string_valid(code):
            return await interaction.followup.send(_("Invalid function"), ephemeral=True)

        if function_name != new_name:
            self.db.functions[new_name] = CustomFunction(code=code, jsonschema=schema)
            del self.db.functions[function_name]
        else:
            self.db.functions[function_name].code = code
            self.db.functions[function_name].jsonschema = schema
            self.db.functions[function_name].permission_level = modal.permission_level
        await interaction.followup.send(_("`{}` function updated!").format(function_name), ephemeral=True)
        await self.get_pages()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to delete!"), ephemeral=True)
        function_name = self.pages[self.page].description
        if function_name not in self.db.functions:
            for cog, functions in self.registry.items():
                if function_name in functions:
                    break
            else:
                return await interaction.response.send_message(_("Could not find function!"), ephemeral=True)
            return await interaction.response.send_message(
                _("This function is managed by the `{}` cog and cannot be deleted").format(cog),
                ephemeral=True,
            )
        del self.db.functions[function_name]
        await self.get_pages()
        self.page %= len(self.pages)
        self.update_button()
        await interaction.response.send_message(_("`{}` has been deleted!").format(function_name), ephemeral=True)
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.success, emoji=ON_EMOJI, row=2)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to toggle!"), ephemeral=True)
        await interaction.response.defer()
        function_name = self.pages[self.page].description
        enabled = self.conf.function_statuses.get(function_name, False)
        if enabled:
            self.conf.function_statuses[function_name] = False
        else:
            self.conf.function_statuses[function_name] = True
        self.update_button()
        await self.message.edit(view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{LEFT-POINTING MAGNIFYING GLASS}", row=2)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(_("Search for a function"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return
        if modal.query.isdigit():
            self.page = int(modal.query) - 1
            self.page %= len(self.pages)
            return await self.message.edit(embed=self.pages[self.page], view=self)

        query = modal.query.lower()
        # Search by
        # Description
        # Field 0 (json schema)
        # Field 1 (code)

        def _get_matches():
            matches: List[Tuple[int, int]] = []
            for i, embed in enumerate(self.pages):
                code_field = embed.fields[-1]
                schema_field = embed.fields[-2]

                if query == embed.description.lower():
                    matches.append((100, i))
                    break
                if query in code_field.value.lower():
                    matches.append((98, i))
                    continue
                if query in schema_field.value.lower():
                    matches.append((98, i))
                    continue

                matches.append((fuzz.ratio(query, embed.description.lower()), i))

            if len(matches) > 1:
                matches.sort(key=lambda x: x[0], reverse=True)

            return matches

        sorted_functions = await asyncio.to_thread(_get_matches)
        best = sorted_functions[0][1]

        self.page = best
        self.page %= len(self.pages)

        self.update_button()

        await self.message.edit(embed=self.pages[self.page], view=self)
