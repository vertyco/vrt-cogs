import asyncio
import logging
from io import BytesIO
from typing import Callable, List

import discord
import pandas as pd
from redbot.core import commands

from .common.utils import embedding_embeds, get_attachments, get_embedding_async
from .models import Embedding, GuildSettings

log = logging.getLogger("red.vrt.assistant.views")


class APIModal(discord.ui.Modal):
    def __init__(self):
        self.key = ""
        super().__init__(title="Set OpenAI Key", timeout=120)
        self.field = discord.ui.TextInput(
            label="Enter your OpenAI Key below",
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.key = self.field.value
        await interaction.response.defer()
        self.stop()


class SetAPI(discord.ui.View):
    def __init__(self, author: discord.Member):
        self.author = author
        self.key = ""
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set OpenAI Key", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        modal = APIModal()
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
            label="Entry name",
            style=discord.TextStyle.short,
            default=name,
            required=True,
        )
        self.add_item(self.name_field)
        self.text_field = discord.ui.TextInput(
            label="Training context",
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


class EmbeddingMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, conf: GuildSettings, save_func: Callable):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.conf = conf
        self.save = save_func

        self.place = 0
        self.page = 0
        self.pages = self.get_pages()
        self.message: discord.Message = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        await self.message.edit(view=None)
        return await super().on_timeout()

    def get_pages(self) -> List[discord.Embed]:
        return embedding_embeds(
            embeddings={k: v.dict() for k, v in self.conf.embeddings.items()}, place=self.place
        )

    async def process_embeddings(self, df: pd.DataFrame):
        for row in df.values:
            name = row[0]
            text = row[1]
            embedding = await get_embedding_async(text, self.conf.api_key)
            if not embedding:
                await self.ctx.send(f"Failed to process {name} embedding")
                continue
            self.conf.embeddings[name] = Embedding(text=text, embedding=embedding)
        await self.ctx.send("Your embeddings upload has finished processing!")
        self.pages = self.get_pages()
        self.message = await self.message.edit(embed=self.pages[self.page])
        await self.save()

    async def add_embedding(self, name: str, text: str):
        embedding = await get_embedding_async(text, self.conf.api_key)
        if not embedding:
            return await self.ctx.send(
                f"Failed to process embedding `{name}`\nContent: ```\n{text}\n```"
            )
        if name in self.conf.embeddings:
            return await self.ctx.send(f"An embedding with the name `{name}` already exists!")
        self.conf.embeddings[name] = Embedding(text=text, embedding=embedding)
        self.pages = self.get_pages()
        self.message = await self.message.edit(embed=self.pages[self.page])
        await self.ctx.send(f"Your embedding labeled `{name}` has been processed!")
        await self.save()

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.primary,
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
    )
    async def view(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.message.embeds[0].fields:
            return await interaction.response.send_message(
                "No embeddings to inspect!", ephemeral=True
            )
        name = self.message.embeds[0].fields[self.place].name.replace("➣ ", "", 1)
        embedding = self.conf.embeddings[name]
        await interaction.response.send_message(f"```\n{embedding.text}\n```", ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{UPWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if fields := self.message.embeds[0].fields:
            self.place -= 1
            self.place %= len(fields)
            self.pages = self.get_pages()
            self.message = await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{MEMO}")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.message.embeds[0].fields:
            return await interaction.response.send_message(
                "No embeddings to edit!", ephemeral=True
            )
        name = self.message.embeds[0].fields[self.place].name.replace("➣ ", "", 1)
        embedding_obj = self.conf.embeddings[name]
        modal = EmbeddingModal(title="Edit embedding", name=name, text=embedding_obj.text)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        async with self.ctx.typing():
            embedding = await get_embedding_async(modal.text, self.conf.api_key)
            if not embedding:
                return await interaction.followup.send(
                    "Failed to edit that embedding, please try again later", ephemeral=True
                )
        self.conf.embeddings[modal.name] = Embedding(
            nickname=modal.name, text=modal.text, embedding=embedding
        )
        if modal.name != name:
            del self.conf.embeddings[name]
        self.pages = self.get_pages()
        await self.message.edit(embed=self.pages[self.page])
        await interaction.followup.send("Your embedding has been modified!", ephemeral=True)
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
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{CROSS MARK}", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
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
        await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{SQUARED NEW}", row=2)
    async def new_embedding(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbeddingModal(title="Add an embedding")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        asyncio.create_task(self.add_embedding(modal.name, modal.text))
        await interaction.followup.send(
            "Your embedding is processing and will appear when ready!", ephemeral=True
        )

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{DOWNWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        row=2,
    )
    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if fields := self.message.embeds[0].fields:
            self.place += 1
            self.place %= len(fields)
            self.pages = self.get_pages()
            self.message = await self.message.edit(embed=self.pages[self.page])

    @discord.ui.button(
        style=discord.ButtonStyle.danger, emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}", row=2
    )
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.message.embeds[0].fields:
            return await interaction.response.send_message(
                "No embeddings to delete!", ephemeral=True
            )
        name = self.message.embeds[0].fields[self.place].name.replace("➣ ", "", 1)
        await interaction.response.send_message(f"Deleted `{name}` embedding.")
        del self.conf.embeddings[name]
        self.pages = self.get_pages()
        self.page %= len(self.pages)
        self.message = await self.message.edit(embed=self.pages[self.page])
        await self.save()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        label="Import",
        emoji="\N{OUTBOX TRAY}",
        row=3,
    )
    async def upload(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Upload a **.csv** file containing embeddings", ephemeral=True
        )

        def check(message: discord.Message):
            return message.author == self.ctx.author and message.channel == self.ctx.channel

        try:
            reply = await self.ctx.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await interaction.followup.send("Embedding upload cancelled", ephemeral=True)

        if reply.content == "cancel":
            return await interaction.followup.send("Import cancelled.", ephemeral=True)

        attachments = get_attachments(reply)
        if not attachments:
            return await interaction.followup.send(
                "You must attach a **.csv** file to your message, or reply to the message that has it!",
                ephemeral=True,
            )

        att = attachments[0]
        if not att.filename.endswith(".csv"):
            return await interaction.followup.send(
                "Your upload **MUST** be a .csv file!",
                ephemeral=True,
            )
        file_bytes = await att.read()
        try:
            df = pd.read_csv(BytesIO(file_bytes))
        except Exception as e:
            log.error("Error reading uploaded file", exc_info=e)
            return await interaction.followup.send(
                f"Error reading file: ```\n{e}\n```", ephemeral=True
            )

        invalid = ["name" not in df.columns, "text" not in df.columns]
        if any(invalid):
            return await interaction.followup.send(
                "The .csv file you uploaded contains invalid formatting, columns must be ['name', 'text']",
                ephemeral=True,
            )
        asyncio.create_task(self.process_embeddings(df))
        await interaction.followup.send(
            "Your embeddings have been imported and are processing in the background, come back later to view them!",
            ephemeral=True,
        )

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        label="Export",
        emoji="\N{INBOX TRAY}",
        row=3,
    )
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = [[name, em.text] for name, em in self.conf.embeddings.items()]
        df = pd.DataFrame(rows, columns=["name", "text"])
        buffer = BytesIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        file = discord.File(buffer, filename="embeddings.csv")
        if file.__sizeof__() > interaction.guild.filesize_limit:
            return await interaction.response.send_message(
                "File size is too large to send to discord!", ephemeral=True
            )
        await interaction.response.send_message(
            "Here is your embeddings export!", file=file, ephemeral=True
        )
