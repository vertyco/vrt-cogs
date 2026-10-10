"""Buttons that replace the original's typed answers: yes or no, and picking one of a few options"""

import discord
from redbot.core.i18n import Translator

_ = Translator("Casino", __file__)


class Choose(discord.ui.View):
    """One button per option; only the person who ran the command can press them. choice stays None on timeout"""

    def __init__(self, author_id: int, options: list[tuple[str, str]], danger: tuple[str, ...] = ()):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.choice: str | None = None
        for value, label in options:
            style = discord.ButtonStyle.danger if value in danger else discord.ButtonStyle.secondary
            button = discord.ui.Button(label=label, style=style)
            button.callback = self.picker(value)
            self.add_item(button)

    def picker(self, value: str):
        async def pick(interaction: discord.Interaction):
            self.choice = value
            await interaction.response.edit_message(view=None)
            self.stop()

        return pick

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(_("This isn't your menu."), ephemeral=True)
            return False
        return True


async def ask(ctx, text: str, options: list[tuple[str, str]], danger: tuple[str, ...] = ()) -> str | None:
    """Posts the question with its buttons, waits, and returns the value picked, or None when nobody picked"""
    view = Choose(ctx.author.id, options, danger)
    message = await ctx.send(text, view=view)
    if await view.wait():
        await message.edit(content=text + "\n" + _("No answer, so nothing changed."), view=None)
        return None
    return view.choice


async def confirm(ctx, text: str) -> bool:
    return await ask(ctx, text, [("yes", _("Yes")), ("no", _("No"))], danger=("yes",)) == "yes"
