import asyncio
import contextlib
import functools
import logging
from typing import List, Union

import discord
from dislash import ActionRow, Button, ButtonStyle, ResponseType
from redbot.core import commands

from .menus import menu, DEFAULT_CONTROLS

log = logging.getLogger("red.vrt.arktools.buttonmenu")


# Red menus, but with buttons :D


async def buttonmenu(
        ctx: commands.Context,
        pages: Union[List[str], List[discord.Embed]],
        controls: dict,
        message: discord.Message = None,
        page: int = 0,
        timeout: float = 60.0,
):
    if not isinstance(pages[0], (discord.Embed, str)):
        raise RuntimeError("Pages must be of type discord.Embed or str")
    if not all(isinstance(x, discord.Embed) for x in pages) and not all(
            isinstance(x, str) for x in pages
    ):
        raise RuntimeError("All pages must be of the same type")
    current_page = pages[page]
    buttons = controls["buttons"]
    actions = controls["actions"]

    for key, value in actions.items():
        maybe_coro = value
        if isinstance(value, functools.partial):
            maybe_coro = value.func
        if not asyncio.iscoroutinefunction(maybe_coro):
            raise RuntimeError("Function must be a coroutine")

    if not message:
        try:
            if isinstance(current_page, discord.Embed):
                message = await ctx.send(embed=current_page, components=buttons)
            else:
                message = await ctx.send(current_page, components=buttons)
        except TypeError:
            log.warning("Failed to add components, using normal menu instead")
            return await menu(ctx, pages, DEFAULT_CONTROLS)
    else:
        try:
            if isinstance(current_page, discord.Embed):
                await message.edit(embed=current_page, components=buttons)
            else:
                await message.edit(content=current_page, components=buttons)
        except discord.NotFound:
            return

    def check(inter):
        if inter.author != ctx.author:
            asyncio.create_task(inter.reply("You are not the author of this command", ephemeral=True))
        return inter.author == ctx.author

    try:
        inter = await message.wait_for_button_click(check, timeout=timeout)
    except asyncio.TimeoutError:
        return await message.edit(components=[])
    try:
        await inter.reply(type=ResponseType.DeferredUpdateMessage)
    except Exception as e:
        log.warning(f"inter.reply failure: {e}")
        return await menu(ctx, pages, controls, None, page, timeout)
    button_action = inter.clicked_button.id
    if button_action not in actions:
        raise RuntimeError("Button ID must match action coro key name")
    action = actions[button_action]
    return await action(ctx, pages, controls, message, page, timeout)


async def next_page(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float
):
    if page == len(pages) - 1:
        page = 0  # Loop around to the first item
    else:
        page = page + 1
    return await buttonmenu(ctx, pages, controls, message=message, page=page, timeout=timeout)


async def skip_ten(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float
):
    if len(pages) < 10:
        page = page  # Do nothing if there aren't enough pages
    elif page >= len(pages) - 10:
        page = 10 - (len(pages) - page)  # Loop around to the first item
    else:
        page = page + 10
    return await buttonmenu(ctx, pages, controls, message=message, page=page, timeout=timeout)


async def prev_page(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float
):
    if page == 0:
        page = len(pages) - 1  # Loop around to the last item
    else:
        page = page - 1
    return await buttonmenu(ctx, pages, controls, message=message, page=page, timeout=timeout)


async def back_ten(
        ctx: commands.Context,
        pages: list,
        controls: dict,
        message: discord.Message,
        page: int,
        timeout: float
):
    if len(pages) < 10:
        page = page  # Do nothing if there arent enough pages
    elif page < 10:
        page = page + len(pages) - 10  # Loop around to the last item
    else:
        page = page - 10
    return await buttonmenu(ctx, pages, controls, message=message, page=page, timeout=timeout)


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


DEFAULT_BUTTON_CONTROLS = {
    # List of ActionRows
    "buttons": [
        ActionRow(
            Button(
                style=ButtonStyle.grey,
                custom_id="prev10",
                emoji="⏪"
            ),
            Button(
                style=ButtonStyle.gray,
                custom_id="prev",
                emoji="◀"
            ),
            Button(
                style=ButtonStyle.grey,
                custom_id="exit",
                emoji="❌"
            ),
            Button(
                style=ButtonStyle.grey,
                custom_id="next",
                emoji="▶"
            ),
            Button(
                style=ButtonStyle.grey,
                custom_id="next10",
                emoji="⏩"
            )
        )
    ],
    # Dict of coros
    "actions": {
        "prev10": back_ten,
        "prev": prev_page,
        "exit": close_menu,
        "next": next_page,
        "next10": skip_ten
    }
}
