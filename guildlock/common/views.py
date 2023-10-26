import contextlib

import discord
from redbot.core.i18n import Translator

_ = Translator("GuildLock", __file__)


class Confirm(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=60)
        self.author = author
        self.yes.label = _("Yes")
        self.no.label = _("No")

        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()


class SelectModal(discord.ui.Modal):
    def __init__(self, current: str):
        super().__init__(title=_("Select a Page"), timeout=240)
        self.page = current
        self.input = discord.ui.TextInput(
            label=_("Enter Page Number"),
            style=discord.TextStyle.short,
            required=True,
            default=current,
            max_length=50,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.page = self.input.value
        await interaction.response.defer()
        self.stop()


class DynamicMenu(discord.ui.View):
    def __init__(
        self,
        author: discord.Member | discord.User,
        pages: list[discord.Embed],
        channel: discord.TextChannel | discord.Thread | discord.ForumChannel | discord.DMChannel,
        message: discord.Message | discord.InteractionMessage | None = None,
        page: int = 0,
        timeout: int | float = 300,
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.pages = pages
        self.channel = channel
        self.message = message
        self.page = page

        self.guild = author.guild or channel.guild
        self.page_count = len(pages)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with contextlib.suppress(Exception):
                await self.message.edit(view=None)

    async def refresh(self):
        self.clear_items()
        single = [self.close]
        small = [self.left] + single + [self.right]
        large = small + [self.left10, self.select, self.right10]

        buttons = large if self.page_count > 10 else small if self.page_count > 1 else single
        for button in buttons:
            self.add_item(button)

        if len(buttons) == 1:
            for embed in self.pages:
                embed.set_footer(text=None)

        if self.message:
            await self.message.edit(embed=self.pages[self.page], view=self)
        else:
            self.message = await self.channel.send(embed=self.pages[self.page], view=self)
        return self

    @discord.ui.button(
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def left10(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        await interaction.response.defer()
        if self.page < 10:
            self.page = self.page + self.page_count - 10
        else:
            self.page -= 10
        await self.refresh()

    @discord.ui.button(
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def left(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= self.page_count
        await self.refresh()

    @discord.ui.button(
        emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.danger,
    )
    async def close(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        await interaction.response.defer()
        await self.message.delete()
        self.stop()

    @discord.ui.button(
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def right(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= self.page_count
        await self.refresh()

    @discord.ui.button(
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def right10(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        await interaction.response.defer()
        if self.page >= self.page_count - 10:
            self.page = 10 - (self.page_count - self.page)
        else:
            self.page += 10
        await self.refresh()

    @discord.ui.button(
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def select(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        modal = SelectModal(str(self.page + 1))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.page.isdigit():
            return await interaction.followup.send(_("Page must be a number!"), ephemeral=True)
        self.page = int(modal.page) - 1
        self.page %= self.page_count
        await self.refresh()
