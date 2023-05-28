import discord


class ConfigModal(discord.ui.Modal):
    def __init__(self, current: dict):
        self.data = None
        super().__init__(title="Set Postgres Info", timeout=240)
        self.host = discord.ui.TextInput(
            label="POSTGRES HOST",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("host"),
        )
        self.add_item(self.host)
        self.port = discord.ui.TextInput(
            label="POSTGRES PORT",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("port"),
        )
        self.add_item(self.port)
        self.user = discord.ui.TextInput(
            label="POSTGRES USER",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("user"),
        )
        self.add_item(self.user)
        self.password = discord.ui.TextInput(
            label="POSTGRES PASSWORD",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("password"),
        )
        self.add_item(self.password)
        self.database = discord.ui.TextInput(
            label="POSTGRES DATABASE",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("database", "postgres"),
        )
        self.add_item(self.database)

    async def on_submit(self, interaction: discord.Interaction):
        self.data = {
            "host": self.host.value,
            "port": self.port.value,
            "user": self.user.value,
            "password": self.password.value,
            "database": self.database.value,
        }
        await interaction.response.defer()
        self.stop()


class SetConnectionView(discord.ui.View):
    def __init__(self, author: discord.Member, current: dict):
        self.author = author
        self.current = current
        self.data = None
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Configure", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        modal = ConfigModal(self.current)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.data:
            self.data = modal.data
            self.stop()
