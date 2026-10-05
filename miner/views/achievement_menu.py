from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import discord
from discord import ui
from redbot.core import commands

from ..common import achievements, constants
from .rock_layout import clean_name

log = logging.getLogger("red.vrt.miner.views.achievement_menu")

# The pictures in data/achievements, linked from the repo so they load from a fixed address instead of being
# re-uploaded on every click (and Discord's app keeps them cached between pages)
ICON_URL = "https://raw.githubusercontent.com/vertyco/vrt-cogs/main/miner/data/achievements/"
# One message holds at most 40 components; each picture row takes 3
CATEGORIES_PER_PAGE = 6
RECENT_SHOWN = 5
LEFT_EMOJI = "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
RIGHT_EMOJI = "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"
CLOSE_EMOJI = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"


@dataclass(slots=True)
class CategoryCard:
    """One category's progress and the text for each of its achievements."""

    name: achievements.AchievementCategory
    lines: list[str]
    unlocked: int
    total: int


def icon_name(category: str) -> str:
    return f"{category.lower().replace(' ', '_')}.webp"


def icon(category: str) -> ui.Thumbnail:
    return ui.Thumbnail(media=ICON_URL + icon_name(category))


def progress_text(done: int, total: int) -> str:
    """'`▰▰▰▱▱▱▱▱▱▱` `3/10`', with a check mark once everything is unlocked."""
    filled = round(constants.HP_BAR_SEGMENTS * done / total) if total else 0
    bar = constants.HP_BAR_FILLED * filled + constants.HP_BAR_EMPTY * (constants.HP_BAR_SEGMENTS - filled)
    text = f"`{bar}` `{done}/{total}`"
    return f"{text} ✅" if total and done >= total else text


def page_count(cards: list[CategoryCard]) -> int:
    return max(1, math.ceil(len(cards) / CATEGORIES_PER_PAGE))


def page_cards(cards: list[CategoryCard], page: int) -> list[CategoryCard]:
    start = page * CATEGORIES_PER_PAGE
    return cards[start : start + CATEGORIES_PER_PAGE]


def recent_text(unlocked_rows: list) -> str:
    """The newest unlocks. `unlocked_rows` comes sorted newest first."""
    lines = ["**Recent unlocks**"]
    for row in unlocked_rows:
        definition = achievements.ACHIEVEMENTS_BY_KEY.get(row.key)
        if definition is None:
            continue
        lines.append(f"-# {definition.name} · {discord.utils.format_dt(row.created_on, style='R')}")
        if len(lines) > RECENT_SHOWN:
            break
    if len(lines) == 1:
        lines.append("-# No achievements unlocked yet.")
    return "\n".join(lines)


def build_overview(
    name: str,
    avatar_url: str | None,
    recent: str | None,
    cards: list[CategoryCard],
    page: int,
    controls: list[ui.Item],
    color: discord.Colour,
) -> ui.Container:
    """One page of categories, each row with its picture on the right like the rock results."""
    unlocked = sum(card.unlocked for card in cards)
    total = sum(card.total for card in cards)
    box = ui.Container(accent_colour=color)
    head = ui.TextDisplay(f"## {clean_name(name)}'s Achievements\n{progress_text(unlocked, total)}")
    box.add_item(ui.Section(head, accessory=ui.Thumbnail(media=avatar_url)) if avatar_url else head)
    if recent:
        box.add_item(ui.TextDisplay(recent))
    box.add_item(ui.Separator())
    for card in page_cards(cards, page):
        text = ui.TextDisplay(f"**{card.name}**\n{progress_text(card.unlocked, card.total)}")
        box.add_item(ui.Section(text, accessory=icon(card.name)))
    box.add_item(ui.Separator())
    for item in controls:
        box.add_item(item)
    box.add_item(ui.TextDisplay(f"-# Page {page + 1}/{page_count(cards)}"))
    return box


def build_category(
    name: str,
    card: CategoryCard,
    index: int,
    count: int,
    controls: list[ui.Item],
    color: discord.Colour,
) -> ui.Container:
    """One category: its picture and progress, then every achievement in it."""
    box = ui.Container(accent_colour=color)
    head = ui.TextDisplay(
        f"## {card.name}\n-# {clean_name(name)}'s progress\n{progress_text(card.unlocked, card.total)}"
    )
    box.add_item(ui.Section(head, accessory=icon(card.name)))
    box.add_item(ui.Separator())
    box.add_item(ui.TextDisplay("\n\n".join(card.lines)))
    box.add_item(ui.Separator())
    for item in controls:
        box.add_item(item)
    box.add_item(ui.TextDisplay(f"-# Category {index + 1}/{count}"))
    return box


class AchievementMenu(ui.LayoutView):
    """Achievement browser: overview pages of categories, and one page per category."""

    def __init__(
        self,
        author_id: int,
        name: str,
        avatar_url: str | None,
        recent: str,
        cards: list[CategoryCard],
        color: discord.Colour,
    ):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.name = name
        self.avatar_url = avatar_url
        self.recent = recent
        self.cards = cards
        self.color = color
        self.page = 0
        self.category: int | None = None  # None shows the overview
        self.message: discord.Message | None = None

        self.picker = ui.Select(placeholder="Open a category")
        self.picker.callback = self.on_pick
        self.back_button = ui.Button(emoji=LEFT_EMOJI, style=discord.ButtonStyle.primary)
        self.back_button.callback = self.on_back
        self.overview_button = ui.Button(label="All categories", style=discord.ButtonStyle.secondary)
        self.overview_button.callback = self.on_overview
        self.close_button = ui.Button(emoji=CLOSE_EMOJI, style=discord.ButtonStyle.danger)
        self.close_button.callback = self.on_close
        self.next_button = ui.Button(emoji=RIGHT_EMOJI, style=discord.ButtonStyle.primary)
        self.next_button.callback = self.on_next

    def controls(self) -> list[ui.Item]:
        self.picker.options = [
            discord.SelectOption(
                label=card.name,
                value=str(index),
                description=f"{card.unlocked}/{card.total} unlocked",
                default=index == self.category,
            )
            for index, card in enumerate(self.cards)
        ]
        buttons = [self.back_button, self.close_button, self.next_button]
        if self.category is not None:
            buttons.insert(1, self.overview_button)
        return [ui.ActionRow(self.picker), ui.ActionRow(*buttons)]

    def draw(self, controls: bool = True) -> None:
        self.clear_items()
        items = self.controls() if controls else []
        if self.category is None:
            recent = self.recent if self.page == 0 else None
            self.add_item(build_overview(self.name, self.avatar_url, recent, self.cards, self.page, items, self.color))
            return
        card = self.cards[self.category]
        self.add_item(build_category(self.name, card, self.category, len(self.cards), items, self.color))

    async def start(self, ctx: commands.Context) -> None:
        self.draw()
        self.message = await ctx.send(view=self)

    async def show(self, interaction: discord.Interaction) -> None:
        self.draw()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.message:
            return
        self.draw(controls=False)
        try:
            await self.message.edit(view=self)
        except discord.HTTPException as e:
            log.warning("Could not remove the achievement menu controls after it timed out", exc_info=e)

    async def on_pick(self, interaction: discord.Interaction) -> None:
        self.category = int(self.picker.values[0])
        await self.show(interaction)

    async def on_back(self, interaction: discord.Interaction) -> None:
        self.step(-1)
        await self.show(interaction)

    async def on_next(self, interaction: discord.Interaction) -> None:
        self.step(1)
        await self.show(interaction)

    def step(self, offset: int) -> None:
        """Arrows flip overview pages on the overview, and categories on a category page."""
        if self.category is None:
            self.page = (self.page + offset) % page_count(self.cards)
        else:
            self.category = (self.category + offset) % len(self.cards)

    async def on_overview(self, interaction: discord.Interaction) -> None:
        # Return to the overview page that lists the category being viewed
        self.page = (self.category or 0) // CATEGORIES_PER_PAGE
        self.category = None
        await self.show(interaction)

    async def on_close(self, interaction: discord.Interaction) -> None:
        self.stop()
        try:
            await interaction.response.defer()
            if self.message:
                await self.message.delete()
        except discord.HTTPException as e:
            log.warning("Could not close the achievement menu", exc_info=e)
