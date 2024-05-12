from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import discord
from discord import app_commands
from pydantic import ValidationError
from redbot.core import commands

from ..abc import MixinMeta
from ..common.models import EmailAccount
from ..views.settings import AddEmail, EditEmail


class Admin(MixinMeta):
    def __init__(self):
        super().__init__()
        self.recipient_cache: dict[int, list[str]] = {}

    @app_commands.command(name="email", description="Send an email")
    @app_commands.guild_only()
    async def email_slash(
        self,
        interaction: discord.Interaction,
        sender: str,
        recipient: str,
        subject: str,
        message: str,
        attachment1: discord.Attachment = None,
        attachment2: discord.Attachment = None,
        attachment3: discord.Attachment = None,
    ):
        conf = self.db.get_conf(interaction.guild)
        if not conf.allowed_roles:
            return await interaction.response.send_message("No roles allowed to send emails", ephemeral=True)
        member = interaction.guild.get_member(interaction.user.id)
        for role in member.roles:
            if role.id in conf.allowed_roles:
                break
        else:
            return await interaction.response.send_message("You do not have permission to send emails", ephemeral=True)
        if not conf.accounts:
            return await interaction.response.send_message("No email accounts configured", ephemeral=True)
        for account in conf.accounts:
            if account.email == sender:
                break
        else:
            return await interaction.response.send_message("Invalid email account", ephemeral=True)
        if account.signature:
            message += f"\n\n{account.signature}"
        # Make sure the recipient is a valid email address
        try:
            EmailAccount(email=recipient, password="password")
        except ValidationError:
            return await interaction.response.send_message(
                "The Recipient's email address is not valid!", ephemeral=True
            )
        # Send the email
        await interaction.response.defer()
        attachments = [attachment for attachment in (attachment1, attachment2, attachment3) if attachment]
        await self.send_email(sender, recipient, subject, message, attachments, account.password)
        await interaction.followup.send("Email sent!")
        self.recipient_cache.setdefault(interaction.guild.id, []).append(recipient)

    @email_slash.autocomplete("sender")
    async def email_sender_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice]:
        conf = self.db.get_conf(interaction.guild)
        choices = [
            app_commands.Choice(name=account.email, value=account.email)
            for account in conf.accounts
            if current.lower() in account.email
        ]
        return choices[:25]

    @email_slash.autocomplete("recipient")
    async def email_recipient_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice]:
        history = self.recipient_cache.get(interaction.guild.id, [])
        choices = [
            app_commands.Choice(name=recipient, value=recipient)
            for recipient in history
            if current.lower() in recipient
        ]
        return choices[:25]

    @commands.command(name="email")
    @commands.guild_only()
    async def email_text(self, ctx: commands.Context, sender: str, recipient: str, subject: str, *, message: str):
        """
        Send an email

        Attach files to the command to send them as attachments
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.allowed_roles:
            return await ctx.send("No roles allowed to send emails")
        for role in ctx.author.roles:
            if role.id in conf.allowed_roles:
                break
        else:
            return await ctx.send("You do not have permission to send emails")
        if not conf.accounts:
            return await ctx.send("No email accounts configured")
        for account in conf.accounts:
            if account.email == sender:
                break
        else:
            return await ctx.send("Invalid email account")
        if account.signature:
            message += f"\n\n{account.signature}"
        # Make sure the recipient is a valid email address
        try:
            EmailAccount(email=recipient, password="password")
        except ValidationError:
            return await ctx.send("The Recipient's email address is not valid!")
        attachments = ctx.message.attachments
        if ctx.message.reference:
            if ctx.message.reference.resolved:
                attachments += ctx.message.reference.resolved.attachments
        await self.send_email(sender, recipient, subject, message, attachments, account.password)
        self.recipient_cache.setdefault(ctx.guild.id, []).append(recipient)
        await ctx.tick()

    async def send_email(
        self,
        sender: str,
        recipient: str,
        subject: str,
        message: str,
        attachments: list[discord.Attachment],
        password: str,
    ):
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))
        # Add any attachements to the email
        for attachment in attachments:
            filename = attachment.filename
            file_bytes = await attachment.read()
            # Check if the attachment is an image
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                img = MIMEImage(file_bytes, name=filename)
                msg.attach(img)
            else:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        await aiosmtplib.send(
            msg,
            sender=sender,
            recipients=recipient,
            hostname="smtp.gmail.com",
            port=587,
            username=sender,
            password=password,
        )

    @commands.command(name="addemail", aliases=["addgmail"])
    @commands.guild_only()
    @commands.guildowner()
    async def add_email(self, ctx: commands.Context):
        """Add an email account"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.accounts) >= 25:
            return await ctx.send("You cannot have more than 25 email accounts!")
        embed = discord.Embed(
            title="Add Email Account",
            description="Enter the email address and password for the account you want to add",
            color=await self.bot.get_embed_color(ctx),
        )
        view = AddEmail(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        await msg.delete()
        await ctx.tick()
        await self.save()

    @commands.command(name="editemail", aliases=["editgmail"])
    @commands.guild_only()
    @commands.guildowner()
    async def edit_email(self, ctx: commands.Context, email: str):
        """Edit an email account"""
        conf = self.db.get_conf(ctx.guild)
        for account in conf.accounts:
            if account.email == email:
                break
        else:
            return await ctx.send("Email account not found")
        embed = discord.Embed(
            title="Edit Email Account",
            description="Enter the new email address and password for the account",
            color=await self.bot.get_embed_color(ctx),
        )
        view = EditEmail(self, ctx, account)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        await msg.delete()
        await ctx.tick()
        await self.save()

    @commands.command(name="deleteemail")
    @commands.guild_only()
    @commands.guildowner()
    async def delete_email(self, ctx: commands.Context, email: str):
        """Delete an email account"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.accounts:
            return await ctx.send("No email accounts configured")
        for account in conf.accounts:
            if account.email == email:
                conf.accounts.remove(account)
                await ctx.tick()
                await self.save()
                return
        await ctx.send("Email account not found")

    @commands.command(name="gmailroles")
    @commands.guild_only()
    @commands.guildowner()
    async def allowed_roles(self, ctx: commands.Context, *roles: discord.Role):
        """Set the roles allowed to send emails"""
        conf = self.db.get_conf(ctx.guild)
        conf.allowed_roles = [role.id for role in roles]
        await ctx.tick()
        await self.save()

    @commands.command(name="gmailsettings")
    @commands.guild_only()
    async def view_settings(self, ctx: commands.Context):
        """View the email settings for the server"""
        conf = self.db.get_conf(ctx.guild)
        embed = discord.Embed(
            title="Email Settings",
            description="Email settings for this server\n[*] indicates the email has a signature set",
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name="Email Accounts",
            value="\n".join(
                f"{account.email}*" if account.signature else f"{account.email}" for account in conf.accounts
            )
            if conf.accounts
            else "None",
        )
        embed.add_field(
            name="Allowed Roles",
            value="\n".join(f"<@&{role}>" for role in conf.allowed_roles) if conf.allowed_roles else "None",
        )
        await ctx.send(embed=embed)

    @commands.command(name="gmailhelp", aliases=["gmailsetup"])
    @commands.guild_only()
    async def gmail_instructions(self, ctx: commands.Context):
        """Get instructions for setting up Gmail"""
        embed = discord.Embed(
            title="Gmail Setup Instructions",
            description="Instructions for setting up Gmail to send emails",
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name="Step 1",
            value="Setup 2FA on your **[Google account](https://myaccount.google.com)** if you haven't already",
            inline=False,
        )
        embed.add_field(
            name="Step 2",
            value="Go **[Here](https://myaccount.google.com/apppasswords)** and generate an app password for your bot",
            inline=False,
        )
        embed.add_field(
            name="Step 3",
            value=f"Type `{ctx.clean_prefix}addemail` and use the generated app password as the password for your email account",
            inline=False,
        )
        await ctx.send(embed=embed)
