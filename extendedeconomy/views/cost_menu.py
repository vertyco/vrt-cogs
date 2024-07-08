import contextlib
import logging
import math
import typing as t
from contextlib import suppress

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.models import CommandCost
from ..common.utils import format_command_txt, format_settings

log = logging.getLogger("red.vrt.extendedeconomy.admin")
_ = Translator("ExtendedEconomy", __file__)
PER_PAGE = 2
LEFT = "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
LEFT10 = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}"
RIGHT = "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"
RIGHT10 = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}"
UP = "\N{UPWARDS BLACK ARROW}"
DOWN = "\N{DOWNWARDS BLACK ARROW}"
CLOSE = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"
ADD = "\N{HEAVY PLUS SIGN}"
REMOVE = "\N{HEAVY MINUS SIGN}"
EDIT = "\N{PENCIL}"


class CostModal(discord.ui.Modal):
    def __init__(self, title: str, data: t.Optional[dict] = None, add: t.Optional[bool] = False):
        super().__init__(title=title, timeout=120)
        if data is None:
            data = {}
        self.add = add
        if add:
            self.command = discord.ui.TextInput(
                label=_("Command Name"),
                placeholder="ping",
                default=data.get("command"),
            )
            self.add_item(self.command)
        self.cost = discord.ui.TextInput(
            label=_("Cost"),
            placeholder="100",
            default=data.get("cost"),
        )
        self.add_item(self.cost)
        self.duration = discord.ui.TextInput(
            label=_("Duration (Seconds)"),
            placeholder="3600",
            default=data.get("duration", "3600"),
        )
        self.add_item(self.duration)
        self.details = discord.ui.TextInput(
            label=_("level, prompt, modifier (Comma separated)"),
            placeholder="all, notify, static",
            default=data.get("details", "all, notify, static"),
        )
        self.add_item(self.details)
        self.value = discord.ui.TextInput(
            label=_("Value (Decimal)[Optional]"),
            placeholder="0.0",
            default=data.get("value", "0.0"),
            required=False,
        )
        self.add_item(self.value)
        self.data = {}

    async def try_respond(self, interaction: discord.Interaction, content: str):
        try:
            await interaction.response.send_message(content, ephemeral=True)
        except discord.HTTPException:
            with suppress(discord.NotFound):
                await interaction.followup.send(content, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.data["cost"] = int(self.cost.value)
        except ValueError:
            return await self.try_respond(interaction, _("Cost must be an integer!"))
        try:
            self.data["duration"] = int(self.duration.value)
        except ValueError:
            return await self.try_respond(interaction, _("Duration must be an integer!"))
        try:
            self.data["value"] = float(self.value.value)
        except ValueError:
            return await self.try_respond(interaction, _("Value must be a decimal!"))
        txt = self.details.value
        if "," in txt:
            i = [x.strip() for x in txt.split(",")]
        else:
            i = [x.strip() for x in txt.split()]
        if len(i) != 3:
            txt = _("Invalid details! Must be 3 values separated by commas.")
            txt += _("\nExample: `user, notify, static`")
            return await self.try_respond(interaction, txt)
        level, prompt, modifier = i
        if level not in ["admin", "mod", "all", "user", "global"]:
            return await self.try_respond(
                interaction, _("Invalid level! You must use one of: admin, mod, all, user, global")
            )
        if prompt not in ["text", "reaction", "button", "silent", "notify"]:
            return await self.try_respond(
                interaction, _("Invalid prompt! You must use one of: text, reaction, button, silent, notify")
            )
        if modifier not in ["static", "percent", "exponential", "linear"]:
            return await self.try_respond(
                interaction, _("Invalid modifier! You must use one of: static, percent, exponential, linear")
            )
        self.data["level"] = level
        self.data["prompt"] = prompt
        self.data["modifier"] = modifier
        if self.add:
            self.data["command"] = self.command.value
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        self.stop()
        return await super().on_timeout()

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        txt = f"Modal failed for {interaction.user.name}!\n" f"Guild: {interaction.guild}\n" f"Title: {self.title}\n"
        log.error(txt, exc_info=error)


class MenuButton(discord.ui.Button):
    def __init__(
        self,
        func: t.Callable,
        emoji: t.Optional[t.Union[str, discord.Emoji, discord.PartialEmoji]] = None,
        style: t.Optional[discord.ButtonStyle] = discord.ButtonStyle.primary,
        label: t.Optional[str] = None,
        disabled: t.Optional[bool] = False,
        row: t.Optional[int] = None,
    ):
        super().__init__(style=style, label=label, disabled=disabled, emoji=emoji, row=row)
        self.func = func

    async def callback(self, interaction: discord.Interaction):
        await self.func(interaction, self)


class CostMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog: MixinMeta, global_bank: bool, check: t.Callable):
        super().__init__(timeout=240)
        self.ctx = ctx
        self.author = ctx.author
        self.cog = cog
        self.bot: Red = cog.bot
        self.db = cog.db
        self.global_bank = global_bank
        self.check = check

        self.message: discord.Message = None
        self.page: int = 0
        self.selected: int = 0  # Which command cost field is currently selected
        self.pages: t.List[discord.Embed] = self.get_pages()

        self.b = {
            "add": MenuButton(self.add, ADD, style=discord.ButtonStyle.success, row=1),
            "up": MenuButton(self.up, UP, row=1),
            "remove": MenuButton(self.remove, REMOVE, style=discord.ButtonStyle.danger, row=1),
            "left": MenuButton(self.left, LEFT, row=2),
            "edit": MenuButton(self.edit, EDIT, style=discord.ButtonStyle.secondary, row=2),
            "right": MenuButton(self.right, RIGHT, row=2),
            "left10": MenuButton(self.left10, LEFT10, row=3),
            "down": MenuButton(self.down, DOWN, row=3),
            "right10": MenuButton(self.right10, RIGHT10, row=3),
            "close": MenuButton(self.close, CLOSE, style=discord.ButtonStyle.danger, row=4),
        }

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with contextlib.suppress(Exception):
                await self.message.edit(view=None)
        await self.ctx.tick()

    def get_costs(self) -> t.Dict[str, CommandCost]:
        if self.global_bank:
            return self.db.command_costs
        return self.db.get_conf(self.ctx.guild).command_costs

    def get_command_name(self) -> str:
        page = self.pages[self.page]
        field = page.fields[self.selected]
        return field.name.replace("➣ ", "")

    def get_cost_obj(self) -> t.Union[CommandCost, None]:
        costs = self.get_costs()
        command_name = self.get_command_name()
        cost_obj = costs.get(command_name)
        return cost_obj

    async def refresh(self):
        self.pages = self.get_pages()

        self.clear_items()
        if self.get_costs():
            for b in self.b.values():
                b.disabled = False
                self.add_item(b)
        else:
            for k, b in self.b.items():
                if k in ["add", "close"]:
                    self.add_item(b)
                else:
                    b.disabled = True
                    self.add_item(b)

        page: discord.Embed = self.pages[self.page]
        if self.selected >= len(page.fields) and page.fields:
            # Place the arrow on the last field if selected is out of bounds
            self.selected = len(page.fields) - 1
            page.set_field_at(
                self.selected,
                name=f"➣ {page.fields[self.selected].name}",
                value=page.fields[self.selected].value,
                inline=False,
            )

        if self.message:
            await self.message.edit(embed=page, view=self)
        else:
            self.message = await self.ctx.send(embed=page, view=self)

    def get_pages(self):
        guildconf = self.db.get_conf(self.ctx.guild)
        conf = self.db if self.global_bank else guildconf
        itemized: t.List[t.Tuple[str, CommandCost]] = list(conf.command_costs.items())
        itemized.sort(key=lambda x: x[0])
        start, stop = 0, PER_PAGE
        pages = []
        page_count = math.ceil(len(conf.command_costs) / PER_PAGE)
        base_embed = format_settings(
            self.db,
            guildconf,
            self.global_bank,
            self.author.id in self.bot.owner_ids,
            self.db.delete_after,
        )
        for p in range(page_count):
            embed = base_embed.copy()
            embed.set_footer(text=_("Page {}/{}").format(p + 1, page_count))
            stop = min(stop, len(conf.command_costs))
            for i in range(start, stop):
                command_name, cost_obj = itemized[i]
                txt = format_command_txt(cost_obj)
                is_selected = i % PER_PAGE == self.selected
                name = f"➣ {command_name}" if is_selected else command_name
                embed.add_field(name=name, value=txt, inline=False)
            pages.append(embed)
            start += PER_PAGE
            stop += PER_PAGE
        if not pages:
            pages.append(base_embed)
        return pages

    # ROW 1
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CostModal(_("Add Command Cost"), add=True)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.data:
            return
        command_name = modal.data["command"]
        if command_name in self.get_costs():
            return await interaction.followup.send(_("Command already has a cost!"), ephemeral=True)
        command_obj = self.bot.get_command(command_name)
        if not command_obj:
            command_obj = self.bot.tree.get_command(command_name)
        if not command_obj:
            return await interaction.followup.send(_("Command not found!"), ephemeral=True)
        if isinstance(command_obj, commands.commands._AlwaysAvailableCommand):
            txt = _("You can't add a cost to a command that is always available!")
            return await interaction.followup.send(txt, ephemeral=True)
        if isinstance(command_obj, (commands.Command, commands.HybridCommand)):
            if (command_obj.requires.privilege_level or 0) > await commands.requires.PrivilegeLevel.from_ctx(self.ctx):
                txt = _("You can't add costs to commands you don't have permission to run!")
                return await interaction.followup.send(txt, ephemeral=True)

        cost_obj = CommandCost(
            cost=modal.data["cost"],
            duration=modal.data["duration"],
            level=modal.data["level"],
            prompt=modal.data["prompt"],
            modifier=modal.data["modifier"],
            value=modal.data["value"],
        )
        if self.global_bank:
            self.cog.db.command_costs[command_name] = cost_obj
        else:
            conf = self.cog.db.get_conf(self.ctx.guild)
            conf.command_costs[command_name] = cost_obj
        msg = await interaction.followup.send(_("Command cost added!"), ephemeral=True)
        if msg:
            await msg.delete(delay=10)
        await self.refresh()
        await self.cog.save()

    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        page = self.pages[self.page]
        self.selected -= 1
        self.selected %= len(page.fields)
        await self.refresh()

    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        command_name = self.get_command_name()
        costs = self.get_costs()
        if command_name not in costs:
            return await interaction.response.send_message(_("Command not found!"), ephemeral=True, delete_after=10)
        if self.global_bank:
            del self.db.command_costs[command_name]
        else:
            conf = self.db.get_conf(self.ctx.guild)
            del conf.command_costs[command_name]
        await interaction.response.send_message(_("Command cost removed!"), ephemeral=True)
        await self.refresh()
        await self.cog.save()

    # ROW 2
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        await self.refresh()

    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        cost_obj = self.get_cost_obj()
        if not cost_obj:
            return await interaction.response.send_message(_("Command not found!"), ephemeral=True)
        data = {
            "cost": str(cost_obj.cost),
            "duration": str(cost_obj.duration),
            "details": f"{cost_obj.level}, {cost_obj.prompt}, {cost_obj.modifier}",
            "value": str(cost_obj.value),
        }
        title = _("Edit Cost: {}").format(self.get_command_name())
        modal = CostModal(title, data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.data:
            return
        cost_obj.cost = int(modal.data["cost"])
        cost_obj.duration = int(modal.data["duration"])
        cost_obj.level = modal.data["level"]
        cost_obj.prompt = modal.data["prompt"]
        cost_obj.modifier = modal.data["modifier"]
        cost_obj.value = float(modal.data["value"])
        if self.global_bank:
            self.db.command_costs[self.get_command_name()] = cost_obj
        else:
            conf = self.db.get_conf(self.ctx.guild)
            conf.command_costs[self.get_command_name()] = cost_obj

        msg = await interaction.followup.send(_("Command cost updated!"), ephemeral=True)
        if msg:
            await msg.delete(delay=10)
        await self.refresh()
        await self.cog.save()

    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        await self.refresh()

    # ROW 3
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        await self.refresh()

    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        page = self.pages[self.page]
        self.selected += 1
        self.selected %= len(page.fields)
        await self.refresh()

    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        await self.refresh()

    # ROW 4
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if msg := self.message:
            with suppress(discord.NotFound):
                await msg.delete()
        self.stop()
        await self.ctx.tick()
