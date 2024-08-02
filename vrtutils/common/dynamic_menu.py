import typing as t
from contextlib import suppress
from io import BytesIO

import discord
from rapidfuzz import fuzz


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
        author: t.Union[discord.Member, discord.User],
        pages: t.List[t.Union[discord.Embed, str]],
        channel: t.Union[discord.TextChannel, discord.Thread, discord.ForumChannel, discord.DMChannel],
        message: t.Union[discord.Message, discord.InteractionMessage, None] = None,
        page: int = 0,
        timeout: t.Union[int, float, None] = 300,
        image_bytes: bytes = None,
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.pages = self.check_pages(pages)
        self.channel = channel
        self.message = message
        self.page = page
        self.image_bytes = image_bytes

        self.guild = author.guild or channel.guild
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

    async def refresh(self, interaction: t.Optional[discord.Interaction] = None, followup: bool = False):
        self.pages %= self.page_count
        self.clear_items()
        single = [self.close]
        small = [self.left] + single + [self.right]
        large = small + [self.left10, self.select, self.right10]

        buttons = large if self.page_count > 10 else small if self.page_count > 1 else single
        for button in buttons:
            self.add_item(button)

        if len(buttons) == 1 and isinstance(self.pages[0], discord.Embed):
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

        if interaction and followup:
            await interaction.edit_original_response(**kwargs)
        elif interaction:
            await interaction.response.edit_message(**kwargs)
        elif self.message:
            try:
                await self.message.edit(**kwargs)
            except discord.HTTPException:
                kwargs.pop("attachments", None)
                kwargs["file"] = file
                self.message = await self.channel.send(**kwargs)
        else:
            self.message = await self.channel.send(**kwargs)
        return self

    @discord.ui.button(
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pages -= 10
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await self.refresh(interaction)

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
        self.stop()

    @discord.ui.button(
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        await self.refresh(interaction)

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
            return await self.refresh(followup=True)

        # Iterate through page content to find closest match
        matches: list[tuple[int, int]] = []
        for i, page in enumerate(self.pages):
            if isinstance(page, discord.Embed):
                if modal.query.lower() == page.title.lower():
                    self.page = i
                    return await self.refresh()
                titlematch = fuzz.ratio(modal.query.lower(), page.title.lower())
                if titlematch > 90:
                    self.page = i
                    return await self.refresh()
                if modal.query.lower() in page.description.lower():
                    titlematch += 50
                elif any(modal.query.lower() in field.value.lower() for field in page.fields):
                    titlematch += 50
                elif any(modal.query.lower() in field.name.lower() for field in page.fields):
                    titlematch += 80
                matches.append((titlematch, i))
                continue
            if modal.query.lower() in page.lower():
                matches.append((fuzz.ratio(modal.query.lower(), page.lower()), i))

        if not matches:
            return await interaction.followup.send("No matches found.", ephemeral=True)

        # Sort by title match
        best = sorted(matches, key=lambda x: x[0], reverse=True)[0][1]

        self.page = best
        await self.refresh(interaction, followup=True)
