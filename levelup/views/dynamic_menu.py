import typing as t
from contextlib import suppress
from io import BytesIO

import discord
from rapidfuzz import fuzz
from redbot.core import commands


class SearchModal(discord.ui.Modal):
    def __init__(self, current: str):
        super().__init__(title="Search", timeout=240)
        self.query = current
        self.input = discord.ui.TextInput(label="Enter Search Query or Page", default=current)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.input.value
        await interaction.response.defer()
        self.stop()


class DynamicMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        pages: t.List[t.Union[discord.Embed, str]],
        message: t.Union[discord.Message, discord.InteractionMessage, None] = None,
        page: int = 0,
        timeout: t.Union[int, float, None] = 300,
        image_bytes: bytes = None,
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.author = ctx.author
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.pages = self.check_pages(pages)
        self.message = message
        self.page = page
        self.image_bytes = image_bytes
        self.page_count = len(pages)

    def check_pages(self, pages: t.List[t.Union[discord.Embed, str]]):
        # Ensure pages are either all embeds or all strings
        if isinstance(pages[0], discord.Embed):
            if not all(isinstance(page, discord.Embed) for page in pages):
                raise TypeError("All pages must be Embeds or strings.")
            for idx in range(len(pages)):
                if not isinstance(pages[idx], discord.Embed):
                    embed = discord.Embed(description=str(pages[idx]))
                    embed.set_footer(text=f"Page {idx + 1}/{len(pages)}")
                    pages[idx] = embed
                elif not pages[idx].footer.text:
                    pages[idx].set_footer(text=f"Page {idx + 1}/{len(pages)}")
        else:
            if not all(isinstance(page, str) for page in pages):
                raise TypeError("All pages must be Embeds or strings.")

        return pages

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await self.message.edit(view=None)
        await self.ctx.tick()

    async def refresh(self):
        self.clear_items()
        single = [self.close]
        small = [self.left] + single + [self.right]
        large = small + [self.left10, self.select, self.right10]

        buttons = large if self.page_count > 10 else small if self.page_count > 1 else single
        for button in buttons:
            self.add_item(button)

        if len(buttons) == 1:
            for embed in self.pages:
                embed.set_footer(text=None)

        attachments = []
        file = None
        if self.image_bytes:
            file = discord.File(BytesIO(self.image_bytes), filename="image.webp")
            attachments.append(file)

        kwargs = {"view": self}
        if isinstance(self.pages[self.page], discord.Embed):
            kwargs["embed"] = self.pages[self.page]
            kwargs["content"] = None
        else:
            kwargs["content"] = self.pages[self.page]
        if self.message and attachments:
            kwargs["attachments"] = attachments
        elif not self.message and file:
            kwargs["file"] = file

        if self.message:
            try:
                await self.message.edit(**kwargs)
            except discord.HTTPException:
                kwargs.pop("attachments", None)
                kwargs["file"] = file
                self.message = await self.ctx.send(**kwargs)
        else:
            self.message = await self.ctx.send(**kwargs)
        return self

    @discord.ui.button(
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self.page < 10:
            self.page = self.page + self.page_count - 10
        else:
            self.page -= 10
        await self.refresh()

    @discord.ui.button(
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page -= 1
        self.page %= self.page_count
        await self.refresh()

    @discord.ui.button(
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self.message:
            with suppress(discord.NotFound):
                await self.message.delete()
        await self.ctx.tick()
        self.stop()

    @discord.ui.button(
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 1
        self.page %= self.page_count
        await self.refresh()

    @discord.ui.button(
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self.page >= self.page_count - 10:
            self.page = 10 - (self.page_count - self.page)
        else:
            self.page += 10
        await self.refresh()

    @discord.ui.button(
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def select(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(str(self.page + 1))
        await interaction.response.send_modal(modal)
        await modal.wait()

        if modal.query is None:
            return

        if modal.query.isdigit():
            self.page = int(modal.query) - 1
            self.page %= self.page_count
            return await self.refresh()

        # Iterate through page content to find closest match
        matches: list[tuple[int, int]] = []
        for i, page in enumerate(self.pages):
            if isinstance(page, discord.Embed):
                if modal.query.lower() in page.description.lower():
                    self.page = i
                    return await self.refresh()
                contentmatch = fuzz.ratio(modal.query.lower(), page.description.lower())
                matches.append((contentmatch, i))

        # Sort by title match
        best = sorted(matches, key=lambda x: x[0], reverse=True)[0][1]

        self.page = best
        self.page %= self.page_count
        await self.refresh()
