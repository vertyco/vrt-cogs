import asyncio
import contextlib
import functools
import logging
from typing import List, Union

import discord
from redbot.core import commands

log = logging.getLogger("red.vrt.utils.bmenu")


# A red-menu like button menu for dpy2 to support cross-dpy functionality


async def interaction_check(ctx, interaction):
    if interaction.user.id != ctx.author.id:
        await interaction.response.send_message(
            content=_("You are not allowed to interact with this button."),
            ephemeral=True
        )
        return False
    return True


class Confirm(discord.ui.View):
    def __init__(self, ctx):
        self.ctx = ctx
        self.value = None
        super().__init__(timeout=60)

    @discord.ui.button(label='Yes', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await interaction_check(self.ctx, interaction):
            return
        self.value = True
        self.stop()

    @discord.ui.button(label='No', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await interaction_check(self.ctx, interaction):
            return

        self.value = False
        self.stop()


async def confirm(ctx, msg: discord.Message):
    try:
        view = Confirm(ctx)
        await msg.edit(view=view)
        await view.wait()
        if view.value is None:
            await msg.delete()
        else:
            await msg.edit(view=None)
        return view.value
    except Exception as e:
        log.warning(f"Confirm Error: {e}")
        return None


class MenuButton(discord.ui.Button):
    def __init__(self, emoji: str):
        super().__init__(style=discord.ButtonStyle.primary, emoji=emoji)
        self.emoji = emoji

    async def callback(self, inter: discord.Interaction):
        await inter.response.defer()
        self.view.stop()
        await self.view.controls[self.emoji.name](
            self.view.ctx,
            self.view.pages,
            self.view.controls,
            self.view.message,
            self.view.page,
            self.view.timeout
        )


class MenuView(discord.ui.View):
    def __init__(
            self,
            ctx: commands.Context,
            pages: Union[List[str], List[discord.Embed]],
            controls: dict,
            message: discord.Message = None,
            page: int = 0,
            timeout: float = 60.0
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.pages = pages
        self.controls = controls
        self.message = message
        self.page = page
        self.timeout = timeout

        for emoji in self.controls:
            self.add_item(MenuButton(emoji))

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
        timeout: float = 60.0
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


async def close_menu(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float
):
    with contextlib.suppress(discord.NotFound):
        await message.delete()


async def left(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
):
    page -= 1
    page %= len(pages)
    await menu(ctx, pages, controls, message, page, timeout)


async def left10(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
):
    if page < 10:
        page = page + len(pages) - 10
    else:
        page -= 10
    await menu(ctx, pages, controls, message, page, timeout)


async def right(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
):
    page += 1
    page %= len(pages)
    await menu(ctx, pages, controls, message, page, timeout)


async def right10(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float,
):
    if page >= len(pages) - 10:
        page = 10 - (len(pages) - page)
    else:
        page += 10
    await menu(ctx, pages, controls, message, page, timeout)


DEFAULT_CONTROLS = {
    "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}": left10,
    "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": left,
    "\N{CROSS MARK}": close_menu,
    "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": right,
    "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}": right10,
}
