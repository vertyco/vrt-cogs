"""
This is a red-like recursive menu for dpy2
"""
import asyncio
import functools
from typing import List, Union

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button, View
from redbot.core import commands

color_map = {
    "\N{CROSS MARK}": ButtonStyle.grey,
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": ButtonStyle.red,
}


async def inter_check(ctx: commands.Context, interaction: Interaction):
    if interaction.user.id != ctx.author.id:
        asyncio.create_task(
            interaction.response.send_message(
                content="You are not allowed to interact with this button.",
                ephemeral=True,
            )
        )
    return interaction.user.id == ctx.author.id


class Confirm(View):
    def __init__(self, ctx):
        self.ctx = ctx
        self.value = None
        super().__init__(timeout=60)

    @discord.ui.button(label="Yes", style=ButtonStyle.grey)
    async def confirm(self, interaction: Interaction, button: Button):
        if not await inter_check(self.ctx, interaction):
            return
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: Button):
        if not await inter_check(self.ctx, interaction):
            return
        self.value = False
        await interaction.response.defer()
        self.stop()


async def confirm(ctx: commands.Context, msg: discord.Message) -> Union[bool, None]:
    """
    A 'yes' or 'no' confirmation menu

    Parameters
    ----------
    ctx: commands.Context
        The command context
    msg: discord.Message
        The buttons will be applied to this message.

    Returns
    ----------
    Union[bool, None]: True if 'Yes', False if 'No', None if timeout
    """
    view = Confirm(ctx)
    await msg.edit(view=view)
    await view.wait()
    if view.value is None:
        await msg.delete()
    else:
        await msg.edit(view=None)
    return view.value


class MenuButton(Button):
    def __init__(self, emoji: str, style: ButtonStyle):
        super().__init__(style=style, emoji=emoji)
        self.emoji = emoji

    async def callback(self, inter: Interaction):
        await self.view.controls[self.emoji.name](self.view, inter)


class MenuView(View):
    def __init__(
        self,
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: dict,
        message: discord.Message = None,
        page: int = 0,
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.controls = controls
        self.message = message
        self.page = page
        self.timeout = timeout

        for emoji in self.controls:
            style = color_map[emoji] if emoji in color_map else ButtonStyle.primary
            self.add_item(MenuButton(emoji, style))

    @staticmethod
    async def defer(interaction: Interaction):
        await interaction.response.defer()

    @staticmethod
    async def respond(interaction: Interaction, text: str):
        await interaction.response.send_message(content=text, ephemeral=True)

    @staticmethod
    async def respond_embed(interaction: Interaction, embed: discord.Embed):
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def interaction_check(self, interaction: Interaction):
        return await inter_check(self.ctx, interaction)

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
    controls: dict,
    message: discord.Message = None,
    page: int = 0,
    timeout: float = 60.0,
):
    """
    An emoji-based dpy2 menu

    note:: All pages should be of the same type

    note:: All functions for handling what a particular emoji does
           should be coroutines (i.e. :code:`async def`). Additionally,
           they must take all the parameters of this function, in
           addition to a string representing the emoji reacted with.
           This parameter should be the last one, and none of the
           parameters in the handling functions are optional

    Parameters
    ----------
    ctx: commands.Context
        The command context
    pages: `list` of `str` or `discord.Embed`
        The pages of the menu.
    controls: dict
        A mapping of emoji to the function which handles the action for the
        emoji.
    message: discord.Message
        The message representing the menu. Usually :code:`None` when first opening
        the menu
    page: int
        The current page number of the menu
    timeout: float
        The time (in seconds) to wait for a reaction

    Raises
    ------
    RuntimeError
        If either of the notes above are violated
    """
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
    if len(pages) <= 10:
        controls = controls.copy()
        if "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}" in controls:
            del controls["\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}"]
        if "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}" in controls:
            del controls["\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}"]
    m = MenuView(ctx, pages, controls, message, page, timeout)
    await m.start()


async def close_menu(instance: MenuView, interaction: Interaction):
    await interaction.response.defer()
    await interaction.message.delete()
    instance.stop()


async def left(instance: MenuView, interaction: Interaction):
    instance.page -= 1
    instance.page %= len(instance.pages)
    await instance.handle_page(interaction.response.edit_message)


async def left10(instance: MenuView, interaction: Interaction):
    if instance.page < 10:
        instance.page = instance.page + len(instance.pages) - 10
    else:
        instance.page -= 10
    await instance.handle_page(interaction.response.edit_message)


async def right(instance: MenuView, interaction: Interaction):
    instance.page += 1
    instance.page %= len(instance.pages)
    await instance.handle_page(interaction.response.edit_message)


async def right10(instance: MenuView, interaction: Interaction):
    if instance.page >= len(instance.pages) - 10:
        instance.page = 10 - (len(instance.pages) - instance.page)
    else:
        instance.page += 10
    await instance.handle_page(interaction.response.edit_message)


DEFAULT_CONTROLS = {
    "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}": left10,
    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": left,
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": close_menu,
    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": right,
    "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}": right10,
}
