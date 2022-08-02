from typing import List, Union

import discord
from redbot.core import commands


class BackTenButton(discord.ui.Button):
    """Button which moves the menu back 10 pages."""

    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, emoji=emoji)

    async def callback(self, interaction):
        if self.view.page < 10:
            self.view.page = self.view.page + len(self.view.pages) - 10
        else:
            self.view.page -= 10
        await self.view.handle_page(interaction.response.edit_message)


class LeftPageButton(discord.ui.Button):
    """Button which moves the menu back a page."""

    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, emoji=emoji)

    async def callback(self, interaction):
        self.view.page -= 1
        self.view.page %= len(self.view.pages)
        await self.view.handle_page(interaction.response.edit_message)


class CloseMenuButton(discord.ui.Button):
    """Button which closes the menu, deleting the menu message."""

    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.danger, emoji=emoji)

    async def callback(self, interaction):
        await interaction.response.defer()
        await interaction.message.delete()
        self.view.stop()


class RightPageButton(discord.ui.Button):
    """Button which moves the menu forward a page."""

    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, emoji=emoji)

    async def callback(self, interaction):
        self.view.page += 1
        self.view.page %= len(self.view.pages)
        await self.view.handle_page(interaction.response.edit_message)


class SkipTenButton(discord.ui.Button):
    """Button which moves the menu to the next 10 pages ."""

    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, emoji=emoji)

    async def callback(self, interaction):
        if self.view.page >= len(self.view.pages) - 10:
            self.view.page = 10 - (len(self.view.pages) - self.view.page)
        else:
            self.view.page += 10
        await self.view.handle_page(interaction.response.edit_message)


class MenuView(discord.ui.View):
    """View that creates a menu using the List[str] or List[embed] provided."""

    def __init__(
            self,
            ctx: commands.Context,
            pages: List[Union[str, discord.Embed]],
            message: discord.Message = None,
            page: int = 0,
            timeout: int = 60
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.message = message
        self.page = page
        if len(self.pages) > 10:
            self.add_item(BackTenButton("\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}"))
        if len(self.pages) > 1:
            self.add_item(LeftPageButton("\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"))
        self.add_item(CloseMenuButton("\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"))
        if len(self.pages) > 1:
            self.add_item(RightPageButton("\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"))
        if len(self.pages) > 10:
            self.add_item(SkipTenButton("\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                content="You are not allowed to interact with this button.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        try:
            await self.message.edit(view=None)
        except discord.NotFound:
            pass

    async def handle_page(self, edit_func):
        if isinstance(self.pages[0], discord.Embed):
            await edit_func(embed=self.pages[self.page])
        else:
            await edit_func(content=self.pages[self.page])

    async def start(self):
        current_page = self.pages[self.page]
        if not self.message:
            if isinstance(current_page, discord.Embed):
                self.message = await self.ctx.send(embed=current_page, view=self)
            else:
                self.message = await self.ctx.send(current_page, view=self)
        else:
            try:
                if isinstance(current_page, discord.Embed):
                    await self.message.edit(embed=current_page, view=self)
                else:
                    await self.message.edit(content=current_page, view=self)
            except discord.NotFound:
                raise RuntimeError("Menu message not found.")
        return self.message


async def menu(
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: dict = None,
        message: discord.Message = None,
        page: int = 0,
        timeout: int = 60
):
    if len(pages) < 1:
        raise RuntimeError("Must provide at least 1 page.")
    if not isinstance(pages[0], (discord.Embed, str)):
        raise RuntimeError("Pages must be of type discord.Embed or str")
    if not all(isinstance(x, discord.Embed) for x in pages) and not all(
            isinstance(x, str) for x in pages
    ):
        raise RuntimeError("All pages must be of the same type")
    m = MenuView(ctx, pages, message, page, timeout)
    await m.start()
