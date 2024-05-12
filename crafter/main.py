import json
import logging
import typing as t
from dataclasses import dataclass
from io import StringIO

import discord
from discord import app_commands
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.chat_formatting import box

log = logging.getLogger("red.vrt.arkcrafting")


@dataclass
class Item:
    name: str
    stack_size: int
    weight: float
    link: str
    img_small: str
    img_large: str
    category: str
    class_name: str
    blueprint_path: str
    ingredients: t.Dict[str, int]


def get_item_breakdown(
    item: Item,
    items: t.Dict[str, Item],
    quantity: int = 1,
    buffer: StringIO = None,
    depth: int = 0,
    prefix="",
):
    """Recursively get all ingredients for an item"""
    if buffer is None:
        buffer = StringIO()

    # Define prefix components:
    space = "    "
    branch = "│   "
    # pointers:
    tee = "├── "
    last = "└── "

    sub_items = list(item.ingredients.items())
    for index, (ingredient, base_amount) in enumerate(sub_items, start=1):
        # Calculate the required amount of each ingredient
        required_amount = base_amount * quantity
        # Determine the pointer type: `tee` or `last`
        pointer = last if index == len(sub_items) else tee
        # Format the line to be written
        line = f"{prefix}{pointer}{required_amount} x {ingredient}\n"
        buffer.write(line)

        # Determine new prefix for sub-items
        if index == len(sub_items):
            new_prefix = prefix + space  # Last item
        else:
            new_prefix = prefix + branch
        # Recursive call to process sub-ingredients, if any
        # Fetch the ingredient item
        if ingredient_item := items.get(ingredient):
            if ingredient_item.ingredients:
                get_item_breakdown(ingredient_item, items, required_amount, buffer, depth + 1, new_prefix)

    return buffer.getvalue()


class Crafter(commands.Cog):
    """Get crafting information for Ark items"""

    __author__ = "vertyco"
    __version__ = "0.0.6"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.data: t.Dict[str, dict] = json.loads((bundled_data_path(self) / "items.json").read_text())
        self.items: t.Dict[str, Item] = {k: Item(**v) for k, v in self.data.items()}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *args, **kwargs):
        return

    async def red_get_data_for_user(self, *args, **kwargs):
        return

    @commands.hybrid_command(name="craft", description="Get crafting information for an item")
    @app_commands.describe(item="The item to get crafting information for")
    async def craft(self, ctx: commands.Context, *, item: str):
        """Get crafting information for an item"""
        item = item.lower()
        item = max(self.items, key=lambda x: fuzz.ratio(x.lower(), item.lower()))
        item: Item = self.items[item]
        desc = (
            f"`Stack Size: `{item.stack_size}\n"
            f"`Weight:     `{item.weight}\n"
            f"`Category:   `{item.category}\n"
            f"`Class Name: `[{item.class_name}]({item.link})\n"
        )
        embed = discord.Embed(description=desc, color=await self.bot.get_embed_color(ctx))
        embed.set_author(name=item.name, icon_url=item.img_small, url=item.link)
        embed.set_image(url=item.img_large)
        if item.ingredients:
            # Break it down like this example:
            # 1 x Gunpowder
            #   ├── 2 x Sparkpowder
            #   │   ├── 1 x Flint
            #   │   └── 1 x Stone
            #   └── 1 x Charcoal
            breakdown = await self.bot.loop.run_in_executor(None, get_item_breakdown, item, self.items)
            embed.add_field(name="Ingredients", value=box(breakdown, lang="python"), inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @craft.autocomplete("item")
    async def craft_autocomplete(self, interaction: discord.Interaction, current: str) -> t.List[app_commands.Choice]:
        choices = []
        for item in self.items.values():
            if current and current.lower() not in item.name.lower():
                continue
            choices.append(app_commands.Choice(name=item.name, value=item.name))
            if len(choices) >= 25:
                break
        return choices

    async def get_crafting_info(self, item_name: str, **kwargs):
        item_name = item_name.lower()
        item_name = max(self.items, key=lambda x: fuzz.ratio(x.lower(), item_name.lower()))
        item: Item = self.items[item_name]
        desc = (
            f"`Item:       `{item.name}\n"
            f"`Stack Size: `{item.stack_size}\n"
            f"`Weight:     `{item.weight}\n"
            f"`Category:   `{item.category}\n"
            f"`Class Name: `[{item.class_name}]({item.link})\n"
        )
        if item.ingredients:
            breakdown = await self.bot.loop.run_in_executor(None, get_item_breakdown, item, self.items)
            desc += box(breakdown, lang="python")
        return desc

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_crafting_info",
            "description": "Get crafting information for an item in Ark Survival Evolved",
            "parameters": {
                "type": "object",
                "properties": {"item_name": {"type": "string"}},
                "required": ["item_name"],
            },
        }
        await cog.register_function(self.qualified_name, schema)
