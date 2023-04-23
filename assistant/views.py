import discord


class APIModal(discord.ui.Modal):
    def __init__(self):
        self.key = ""
        super().__init__(title="Set OpenAI Key", timeout=120)
        self.field = discord.ui.TextInput(
            label="Enter your OpenAI Key below",
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, inter: discord.Interaction):
        self.key = self.field.value
        await inter.response.defer()
        self.stop()


class SetAPI(discord.ui.View):
    def __init__(self, author: discord.Member):
        self.author = author
        self.key = ""
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="Set OpenAI Key", style=discord.ButtonStyle.primary
    )
    async def confirm(
            self, interaction: discord.Interaction, b: discord.ui.Button
    ):
        modal = APIModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.key = modal.key
        if modal.key:
            self.stop()
