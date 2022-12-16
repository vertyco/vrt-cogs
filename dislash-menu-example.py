"""
This is a red-like recursive menu for dislahs
"""
import asyncio
import contextlib
import functools
from typing import List, Union

import discord
from dislash import ActionRow, Button, ButtonStyle, ResponseType
from dislash.interactions import ButtonInteraction
from redbot.core import commands

color_map = {
    "\N{CROSS MARK}": ButtonStyle.grey,
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": ButtonStyle.red,
}


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
    action_row = [
        ActionRow(
            Button(style=ButtonStyle.grey, label="Yes"),
            Button(style=ButtonStyle.grey, label="No"),
        )
    ]
    try:
        await msg.edit(components=action_row)
    except discord.NotFound:
        return

    def check(interaction: ButtonInteraction):
        if interaction.author != ctx.author:
            asyncio.create_task(
                interaction.reply(
                    "You are not the author of this command", ephemeral=True
                )
            )
        return interaction.author == ctx.author

    try:
        inter = await msg.wait_for_button_click(check, timeout=60)
    except asyncio.TimeoutError:
        await msg.delete()
        return None
    try:
        await inter.reply(type=ResponseType.DeferredUpdateMessage)
    except (discord.NotFound, discord.HTTPException):
        pass
    try:
        await msg.edit(components=[])
    except discord.NotFound:
        pass
    if inter.clicked_button.label == "Yes":
        value = True
    else:
        value = False
    return value


class MenuView:
    def __init__(
        self,
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: dict,
        message: discord.Message = None,
        page: int = 0,
        timeout: float = 60.0,
    ):
        self.ctx = ctx
        self.pages = pages
        self.controls = controls
        self.message = message
        self.page = page
        self.timeout = timeout

        self.action_rows = []
        row = []
        rowbreak = 5
        for i, emoji in enumerate(self.controls.keys()):
            style = color_map[emoji] if emoji in color_map else ButtonStyle.primary
            button = Button(style=style, emoji=emoji)
            row.append(button)
            if (i + 1) % rowbreak == 0:
                self.action_rows.append(ActionRow(*row))
                row = []
        if row:
            self.action_rows.append(ActionRow(*row))

    async def handle_page(self, edit_func):
        try:
            if isinstance(self.pages[0], discord.Embed):
                await edit_func(embed=self.pages[self.page])
            else:
                await edit_func(content=self.pages[self.page])
        except discord.NotFound:
            return await self.resume()

    async def defer(self, interaction: ButtonInteraction):
        try:
            await interaction.reply(type=ResponseType.DeferredUpdateMessage)
        except (discord.NotFound, discord.HTTPException):
            return await self.resume()

    @staticmethod
    async def respond(interaction: ButtonInteraction, text: str):
        await interaction.reply(text, ephemeral=True)

    @staticmethod
    async def respond_embed(interaction: ButtonInteraction, embed: discord.Embed):
        await interaction.reply(embed=embed, ephemeral=True)

    async def start(self):
        current_page = self.pages[self.page]
        if not self.message:
            if isinstance(current_page, discord.Embed):
                self.message = await self.ctx.send(
                    embed=current_page, components=self.action_rows
                )
            else:
                self.message = await self.ctx.send(
                    current_page, components=self.action_rows
                )
        else:
            try:
                if isinstance(current_page, discord.Embed):
                    await self.message.edit(
                        embed=current_page, components=self.action_rows
                    )
                else:
                    await self.message.edit(
                        content=current_page, components=self.action_rows
                    )
            except discord.NotFound:
                pass
        await self.resume()

    async def resume(self):
        def check(interaction: ButtonInteraction):
            if interaction.author != self.ctx.author:
                asyncio.create_task(
                    interaction.reply(
                        "You are not the author of this command", ephemeral=True
                    )
                )
            return interaction.author == self.ctx.author

        try:
            inter: ButtonInteraction = await self.message.wait_for_button_click(
                check, timeout=self.timeout
            )
        except asyncio.TimeoutError:
            with contextlib.suppress(discord.NotFound):
                await self.message.delete()
            return
        except discord.NotFound:
            return await menu(
                self.ctx,
                self.pages,
                self.controls,
                self.message,
                self.page,
                self.timeout,
            )

        emoji = inter.clicked_button.emoji
        return await self.controls[emoji.name](self, inter)


async def menu(
    ctx: commands.Context,
    pages: Union[List[str], List[discord.Embed], List[tuple]],
    controls: dict,
    message: discord.Message = None,
    page: int = 0,
    timeout: float = 60.0,
):
    """
    An emoji-based dislash menu

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


async def close_menu(instance: MenuView, interaction: ButtonInteraction):
    await instance.defer(interaction)
    with contextlib.suppress(discord.NotFound):
        await instance.message.delete()


async def left(instance: MenuView, interaction: ButtonInteraction):
    await instance.defer(interaction)
    instance.page -= 1
    instance.page %= len(instance.pages)
    await instance.handle_page(interaction.edit)
    return await instance.resume()


async def left10(instance: MenuView, interaction: ButtonInteraction):
    await instance.defer(interaction)
    if instance.page < 10:
        instance.page = instance.page + len(instance.pages) - 10
    else:
        instance.page -= 10
    await instance.handle_page(interaction.edit)
    return await instance.resume()


async def right(instance: MenuView, interaction: ButtonInteraction):
    await instance.defer(interaction)
    instance.page += 1
    instance.page %= len(instance.pages)
    await instance.handle_page(interaction.edit)
    return await instance.resume()


async def right10(instance: MenuView, interaction: ButtonInteraction):
    await instance.defer(interaction)
    if instance.page >= len(instance.pages) - 10:
        instance.page = 10 - (len(instance.pages) - instance.page)
    else:
        instance.page += 10
    await instance.handle_page(interaction.edit)
    return await instance.resume()


DEFAULT_CONTROLS = {
    "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}": left10,
    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": left,
    "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}": close_menu,
    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": right,
    "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}": right10,
}
