import discord
from pydantic import ValidationError
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import EmailAccount
from . import BaseView


class EmailModal(discord.ui.Modal):
    def __init__(self, parent: BaseView, existing: EmailAccount = None):
        super().__init__(timeout=600, title="Edit" if existing else "Add" + " Email Account")
        self.parent = parent
        self.existing = existing
        email_kwargs = {"label": "Email", "placeholder": "user@gmail.com", "min_length": 11}
        if existing:
            email_kwargs["default"] = existing.email
        pass_kwargs = {"label": "Password", "placeholder": "1234"}
        if existing:
            pass_kwargs["default"] = existing.password
        signature_kwargs = {"label": "Signature", "placeholder": "Yours truly, user", "required": False}
        if existing:
            signature_kwargs["default"] = existing.signature
        self.email = discord.ui.TextInput(**email_kwargs)
        self.password = discord.ui.TextInput(**pass_kwargs)
        self.signature = discord.ui.TextInput(**signature_kwargs, style=discord.TextStyle.paragraph)
        self.add_item(self.email)
        self.add_item(self.password)
        self.add_item(self.signature)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            EmailAccount(email=self.email.value, password=self.password.value)
        except ValidationError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if self.existing is None:
            for account in self.parent.conf.accounts:
                if account.email == self.email.value.lower():
                    return await interaction.response.send_message("Email account already exists", ephemeral=True)
            account = EmailAccount(
                email=self.email.value.lower(),
                password=self.password.value,
                signature=self.signature.value,
            )
            self.parent.conf.accounts.append(account)
            await interaction.response.send_message("Email account added", ephemeral=True)
        else:
            account = EmailAccount(
                email=self.email.value.lower(),
                password=self.password.value,
                signature=self.signature.value,
            )
            self.parent.conf.accounts.remove(self.existing)
            self.parent.conf.accounts.append(account)
            await interaction.response.send_message("Email account edited", ephemeral=True)
        self.stop()


class AddEmail(BaseView):
    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        super().__init__(cog=cog, ctx=ctx)

    @discord.ui.button(label="Add Email", style=discord.ButtonStyle.primary)
    async def add_email(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Throw modal
        modal = EmailModal(self)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.email.value:
            self.stop()


class EditEmail(BaseView):
    def __init__(self, cog: MixinMeta, ctx: commands.Context, account: EmailAccount):
        super().__init__(cog=cog, ctx=ctx)
        self.account = account

    @discord.ui.button(label="Edit Email", style=discord.ButtonStyle.primary)
    async def edit_email(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmailModal(self, existing=self.account)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.email.value:
            self.stop()
