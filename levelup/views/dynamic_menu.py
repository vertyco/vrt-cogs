import asyncio
import logging
import typing as t
from contextlib import suppress
from io import BytesIO

import discord
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.i18n import Translator

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.dynamic_menu")


class SearchModal(discord.ui.Modal):
    def __init__(self, current: t.Optional[str] = None):
        super().__init__(title="Search", timeout=240)
        self.query = current
        self.input = discord.ui.TextInput(label=_("Enter Search Query or Page"), default=current)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.input.value
        await interaction.response.defer()
        self.stop()


class DynamicMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        pages: t.Union[t.List[discord.Embed], t.List[str]],
        message: t.Optional[t.Union[discord.Message, discord.InteractionMessage, None]] = None,
        page: int = 0,
        timeout: t.Union[int, float, None] = 300,
        image_bytes: t.Optional[bytes] = None,
    ):
        super().__init__(timeout=timeout)
        self.check_pages(pages)  # Modifies pages in place

        self.ctx = ctx
        self.author = ctx.author
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.pages = pages
        self.message = message
        self.page = page
        self.image_bytes = image_bytes
        self.page_count = len(pages)

    def check_pages(self, pages: t.List[t.Union[discord.Embed, str]]):
        # Ensure pages are either all embeds or all strings
        if isinstance(pages[0], discord.Embed):
            if not all(isinstance(page, discord.Embed) for page in pages):
                raise TypeError("All pages must be Embeds or strings.")
            # If the first page has no footer, add one to all pages for page number
            if pages[0].footer:
                return
            page_count = len(pages)
            for idx in range(len(pages)):
                pages[idx].set_footer(text=f"Page {idx + 1}/{page_count}")
        else:
            if not all(isinstance(page, str) for page in pages):
                raise TypeError("All pages must be Embeds or strings.")

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

    async def refresh(self, interaction: discord.Interaction = None):
        """Call this to start and refresh the menu."""
        try:
            await self._refresh(interaction)
        except Exception as e:
            current_page = self.pages[self.page]
            if isinstance(current_page, discord.Embed):
                content = current_page.description or current_page.title
                if not content:
                    content = ""
                    for field in current_page.fields:
                        content += f"{field.name}\n{field.value}\n"
            else:
                content = current_page
            log.error(f"Error refreshing menu, current page: {content}", exc_info=e)

    async def _refresh(self, interaction: discord.Interaction = None):
        self.clear_items()
        single = [self.close]
        small = [self.left] + single + [self.right]
        large = small + [self.left10, self.search, self.right10]

        buttons = large if self.page_count > 10 else small if self.page_count > 1 else single
        for button in buttons:
            self.add_item(button)

        if len(buttons) == 1 and isinstance(self.pages[self.page], discord.Embed):
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

        if (self.message or interaction) and attachments:
            kwargs["attachments"] = attachments
        elif (not self.message and not interaction) and file:
            kwargs["file"] = file  # Need to send new message

        if interaction and self.message is not None:
            # We are refreshing due to a button press
            if not interaction.response.is_done():
                try:
                    await interaction.response.edit_message(**kwargs)
                    return self
                except discord.HTTPException:
                    try:
                        await self.message.edit(**kwargs)
                    except discord.HTTPException:
                        kwargs.pop("attachments", None)
                        kwargs["file"] = file
                        self.message = await self.ctx.send(**kwargs)
            else:
                try:
                    await interaction.edit_original_response(**kwargs)
                    return self
                except discord.HTTPException:
                    try:
                        await self.message.edit(**kwargs)
                    except discord.HTTPException:
                        kwargs.pop("attachments", None)
                        kwargs["file"] = file
                        self.message = await self.ctx.send(**kwargs)
            return self

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
        self.page -= 10
        self.page %= self.page_count
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self.page %= self.page_count
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.HTTPException):
            await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            if self.message:
                with suppress(discord.HTTPException):
                    await self.message.delete()
        self.stop()

    @discord.ui.button(
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self.page %= self.page_count
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        self.page %= self.page_count
        await self.refresh(interaction)

    @discord.ui.button(
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(str(self.page + 1))
        await interaction.response.send_modal(modal)
        await modal.wait()

        if modal.query is None:
            return

        if modal.query.isnumeric():
            self.page = int(modal.query) - 1
            self.page %= self.page_count
            return await self.refresh(interaction)

        if isinstance(self.pages[self.page], str):
            for i, page in enumerate(self.pages):
                if modal.query.casefold() in page.casefold():
                    self.page = i
                    return await self.refresh(interaction)
            with suppress(discord.HTTPException):
                await interaction.followup.send(_("No page found matching that query."), ephemeral=True)
            return

        # Pages are embeds
        for i, embed in enumerate(self.pages):
            if embed.title and modal.query.casefold() in embed.title.casefold():
                self.page = i
                return await self.refresh(interaction)
            if modal.query.casefold() in embed.description.casefold():
                self.page = i
                return await self.refresh(interaction)
            if embed.footer and modal.query.casefold() in embed.footer.text.casefold():
                self.page = i
                return await self.refresh(interaction)
            for field in embed.fields:
                if modal.query.casefold() in field.name.casefold():
                    self.page = i
                    return await self.refresh(interaction)
                if modal.query.casefold() in field.value.casefold():
                    self.page = i
                    return await self.refresh(interaction)

        # No results found, resort to fuzzy matching
        def _fuzzymatch() -> t.List[t.Tuple[int, int]]:
            # [(match, index)]
            matches: t.List[t.Tuple[int, int]] = []
            for i, embed in enumerate(self.pages):
                matches.append((fuzz.ratio(modal.query.lower(), embed.title.lower()), i))
                matches.append((fuzz.ratio(modal.query.lower(), embed.description.lower()), i))
                if embed.footer:
                    matches.append((fuzz.ratio(modal.query.lower(), embed.footer.text.lower()), i))
                for field in embed.fields:
                    matches.append((fuzz.ratio(modal.query.lower(), field.name.lower()), i))
                    matches.append((fuzz.ratio(modal.query.lower(), field.value.lower()), i))
            if matches:
                matches.sort(key=lambda x: x[0], reverse=True)
            return matches

        matches = await asyncio.to_thread(_fuzzymatch)

        # Sort by best match
        best_score, best_index = matches[0]
        if best_score < 50:
            with suppress(discord.HTTPException):
                await interaction.followup.send(_("No page found matching that query."), ephemeral=True)
            return
        self.page = best_index
        await self.refresh(interaction)
        await interaction.followup.send(_("Found closest match of {}%").format(int(best_score)), ephemeral=True)
