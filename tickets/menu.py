import asyncio
import functools
from typing import List, Optional, Union

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from redbot.core import commands
from redbot.core.i18n import Translator

_ = Translator("SupportViews", __file__)

mapping = {
    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": (
        ButtonStyle.primary,
        1,
        None,
    ),
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": (ButtonStyle.red, 1, None),
    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": (
        ButtonStyle.primary,
        1,
        None,
    ),
    "\N{WASTEBASKET}\N{VARIATION SELECTOR-16}": (ButtonStyle.grey, 2, "Delete"),
    "\N{MEMO}": (ButtonStyle.green, 2, "Edit"),
}


class MenuButton(Button):
    def __init__(
        self, emoji: str, style: ButtonStyle, row: int, label: Optional[str] = None
    ):
        super().__init__(emoji=emoji, style=style, row=row, label=label)
        self.emoji = emoji

    async def callback(self, inter: Interaction):
        await self.view.controls[self.emoji.name](self, inter)


class MenuView(View):
    def __init__(
        self,
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: dict,
        message: discord.Message = None,
        page: int = 0,
        timeout: int = 60,
    ):
        self.ctx = ctx
        self.pages = pages
        self.controls = controls
        self.message = message
        self.page = page
        super().__init__(timeout=timeout)

        for emoji in self.controls:
            style, row, label = mapping[emoji]
            self.add_item(MenuButton(str(emoji), style, row, label))

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                content=_("You are not allowed to interact with this button."),
                ephemeral=True,
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
    pages: Union[List[str], List[discord.Embed], List[tuple]],
    controls: dict,
    message: discord.Message = None,
    page: int = 0,
    timeout: int = 60,
):
    if len(pages) < 1:
        raise RuntimeError("Must provide at least 1 page.")
    if not isinstance(pages[0], (discord.Embed, str)):
        raise RuntimeError("Pages must be of type discord.Embed or str")
    if not all(isinstance(x, discord.Embed) for x in pages) and not all(
        isinstance(x, str) for x in pages
    ):
        raise RuntimeError("All pages must be of the same type")
    for key, value in controls.items():
        maybe_coro = value
        if isinstance(value, functools.partial):
            maybe_coro = value.func
        if not asyncio.iscoroutinefunction(maybe_coro):
            raise RuntimeError("Function must be a coroutine")
    m = MenuView(ctx, pages, controls, message, page, timeout)
    await m.start()


async def close_menu(instance, interaction: discord.Interaction):
    await interaction.response.defer()
    await interaction.message.delete()
    instance.view.stop()


async def left(instance, interaction: discord.Interaction):
    instance.view.page -= 1
    instance.view.page %= len(instance.view.pages)
    await instance.view.handle_page(interaction.response.edit_message)


async def left10(instance, interaction: discord.Interaction):
    if instance.view.page < 10:
        instance.view.page = instance.view.page + len(instance.view.pages) - 10
    else:
        instance.view.page -= 10
    await instance.view.handle_page(interaction.response.edit_message)


async def right(instance, interaction: discord.Interaction):
    instance.view.page += 1
    instance.view.page %= len(instance.view.pages)
    await instance.view.handle_page(interaction.response.edit_message)


async def right10(instance, interaction: discord.Interaction):
    if instance.view.page >= len(instance.view.pages) - 10:
        instance.view.page = 10 - (len(instance.view.pages) - instance.view.page)
    else:
        instance.view.page += 10
    await instance.view.handle_page(interaction.response.edit_message)


SMALL_CONTROLS = {
    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": left,
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": close_menu,
    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": right,
}
