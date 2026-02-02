import asyncio
import logging
import re
from typing import Optional, Union

import discord
import pytz
from discord import Embed
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common.menu import SMALL_CONTROLS, MenuButton, menu
from ..common.models import DayHours, ModalField, Panel, TicketMessage
from ..common.utils import prune_invalid_tickets, update_active_overview
from ..common.views import PanelView, TestButton, confirm, wait_reply

log = logging.getLogger("red.vrt.admincommands")
_ = Translator("TicketsCommands", __file__)


class AdminCommands(MixinMeta):
    @commands.group(aliases=["tset"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def tickets(self, ctx: commands.Context):
        """Base support ticket settings"""
        pass

    @tickets.command()
    async def setuphelp(self, ctx: commands.Context):
        """Ticket Setup Guide"""
        desc = (
            _("To create a support ticket panel, type ") + f"`{ctx.clean_prefix}tickets addpanel" + _(" <panel_name>`")
        )
        em = Embed(
            title=_("Ticket Setup Guide"),
            description=desc,
            color=ctx.author.color,
        )
        step1 = _("Set the category ID that new tickets will be created under if using channel tickets.\n")
        step1 += f"`{ctx.clean_prefix}tickets category " + _("<panel_name> <category_id>`")
        em.add_field(name=_("Step 1"), value=step1, inline=False)
        step2 = _("Set the channel that the bots ticket panel will be located in.\n")
        step2 += f"`{ctx.clean_prefix}tickets channel " + _("<panel_name> <channel_id>`")
        em.add_field(name=_("Step 2"), value=step2, inline=False)
        step3 = _("Set the ID of the bots ticket panel message.\n")
        step3 += f"`{ctx.clean_prefix}tickets panelmessage " + _("<panel_name> <message_id>`\n")
        step3 += _(
            "At this point the ticket panel will be activated, "
            "all following steps are for extra customization.\n"
            "If you need a message to add the buttons to, you can use the `{}tickets embed` command.\n"
        ).format(ctx.clean_prefix)
        step3 += _("If the bot is having trouble finding the message, run the command in the same channel as it.")
        em.add_field(name=_("Step 3"), value=step3, inline=False)
        step4 = _("Set the text of the ticket panel button.\n")
        step4 += f"`{ctx.clean_prefix}tickets buttontext " + _("<panel_name> <button_text>`")
        em.add_field(name=_("Button Text"), value=step4, inline=False)
        step5 = _("Set the ticket panel button color.\n")
        step5 += _("Valid colors are ") + "`red`, `blue`, `green`, and `grey`.\n"
        step5 += f"`{ctx.clean_prefix}tickets buttoncolor " + _("<panel_name> <button_color>`")
        em.add_field(name=_("Button Color"), value=step5, inline=False)
        step6 = _("Set the button emoji for the ticket panel.\n")
        step6 += f"`{ctx.clean_prefix}tickets buttonemoji " + _("<panel_name> <emoji>`")
        em.add_field(name=_("Button Emoji"), value=step6, inline=False)

        step7 = _("Use threads instead of channels for tickets\n")
        step7 += f"`{ctx.clean_prefix}tickets usethreads " + _("<panel_name>`")
        em.add_field(name=_("Thread Tickets"), value=step7, inline=False)

        step8 = _("Add a message the bot sends to the user in their ticket.\n")
        step8 += f"`{ctx.clean_prefix}tickets addmessage " + _("<panel_name>`")
        em.add_field(name=_("Ticket Messages"), value=step8, inline=False)

        step9 = _("View and remove a messages the bot sends to the user in their ticket.\n")
        step9 += f"`{ctx.clean_prefix}tickets viewmessages " + _("<panel_name>`")
        em.add_field(name=_("Remove/View Ticket Messages"), value=step9, inline=False)

        step10 = _("Set the naming format for ticket channels that are opened.\n")
        step10 += f"`{ctx.clean_prefix}tickets ticketname " + _("<panel_name> <name_format>`")
        em.add_field(name=_("Ticket Channel Name"), value=step10, inline=False)
        step11 = _("Set log channel for a ticket panel.\n")
        step11 += f"`{ctx.clean_prefix}tickets logchannel " + _("<panel_name> <channel>`")
        em.add_field(name=_("Log Channel"), value=step11, inline=False)

        tip = _("Tip: you can create multiple support panels using the same message for a multi-button panel")
        em.set_footer(text=tip)
        await ctx.send(embed=em)

    @tickets.command()
    async def suspend(self, ctx: commands.Context, *, message: Optional[str] = None):
        """
        Suspend the ticket system
        If a suspension message is set, any user that tries to open a ticket will receive this message
        """
        conf = self.db.get_conf(ctx.guild)
        if message is None and conf.suspended_msg is None:
            return await ctx.send_help()
        if not message:
            conf.suspended_msg = None
            await self.save()
            return await ctx.send(_("Ticket system is no longer suspended!"))
        if len(message) > 900:
            return await ctx.send(_("Message is too long! Must be less than 900 characters"))
        conf.suspended_msg = message
        await self.save()
        embed = discord.Embed(
            title=_("Ticket System Suspended"),
            description=message,
            color=discord.Color.yellow(),
        )
        await ctx.send(
            _("Ticket system is now suspended! Users trying to open a ticket will be met with this message"),
            embed=embed,
        )

    @tickets.command()
    async def addpanel(self, ctx: commands.Context, panel_name: str):
        """Add a support ticket panel"""
        panel_name = panel_name.lower()
        em = Embed(
            title=panel_name + _(" Panel Saved"),
            description=_("Your panel has been added and will need to be configured."),
            color=ctx.author.color,
        )
        conf = self.db.get_conf(ctx.guild)
        if panel_name in conf.panels:
            return await ctx.send(_("Panel already exists!"))
        conf.panels[panel_name] = Panel()
        await self.save()
        await ctx.send(embed=em)

    @tickets.command()
    async def category(
        self,
        ctx: commands.Context,
        panel_name: str,
        category: discord.CategoryChannel,
    ):
        """Set the category ID for a ticket panel"""
        panel_name = panel_name.lower()
        if not category.permissions_for(ctx.me).manage_channels:
            return await ctx.send(_("I need the `manage channels` permission to set this category"))
        if not category.permissions_for(ctx.me).manage_permissions:
            return await ctx.send(_("I need `manage roles` enabled in this category"))
        if not category.permissions_for(ctx.me).attach_files:
            return await ctx.send(_("I need the `attach files` permission to set this category"))
        if not category.permissions_for(ctx.me).view_channel:
            return await ctx.send(_("I cannot see that category!"))
        if not category.permissions_for(ctx.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that category!"))
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].category_id = category.id
        await self.save()
        await ctx.tick()
        await ctx.send(_("New tickets will now be opened under that category!"))

    @tickets.command()
    async def channel(
        self,
        ctx: commands.Context,
        panel_name: str,
        channel: discord.TextChannel,
    ):
        """Set the channel ID where a ticket panel is located"""
        panel_name = panel_name.lower()
        if not channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send(_("I cannot see that channel!"))
        if not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that channel!"))
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].channel_id = channel.id
        await self.save()
        await ctx.tick()

    @tickets.command()
    async def panelmessage(self, ctx: commands.Context, panel_name: str, message: discord.Message):
        """
        Set the message ID of a ticket panel
        Run this command in the same channel as the ticket panel message
        """
        if message.author.id != self.bot.user.id:
            return await ctx.send(_("I cannot add buttons to messages sent by other users!"))
        if isinstance(
            message.channel,
            (discord.Thread, discord.VoiceChannel, discord.ForumChannel),
        ):
            return await ctx.send(_("Channel of message must be a TEXT CHANNEL!"))
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        if not panel.category_id:
            return await ctx.send(_("Category ID must be set for this panel first!"))
        if panel.channel_id and panel.channel_id != message.channel.id:
            return await ctx.send(_("This message is part of a different channel from the one you set!"))
        panel.message_id = message.id
        panel.channel_id = message.channel.id
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttontext(self, ctx: commands.Context, panel_name: str, *, button_text: str):
        """Set the button text for a support ticket panel"""
        panel_name = panel_name.lower()
        if len(button_text) > 80:
            return await ctx.send(_("The text content of a button must be less than 80 characters!"))
        butt = TestButton(label=button_text)  # hehe, butt
        await ctx.send(
            _("This is what your button will look like with this text!"),
            view=butt,
        )
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].button_text = button_text
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttoncolor(self, ctx: commands.Context, panel_name: str, *, button_color: str):
        """Set the button color for a support ticket panel"""
        panel_name = panel_name.lower()
        button_color = button_color.lower()
        valid = ["red", "blue", "green", "grey", "gray"]
        if button_color not in valid:
            return await ctx.send(button_color + _(" is not valid, must be one of the following\n") + f"`{valid}`")
        butt = TestButton(style=button_color)  # hehe, butt
        await ctx.send(
            _("This is what your button will look like with this color!"),
            view=butt,
        )
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].button_color = button_color
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttonemoji(
        self,
        ctx: commands.Context,
        panel_name: str,
        *,
        emoji: Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """Set the button emoji for a support ticket panel"""
        panel_name = panel_name.lower()
        try:
            butt = TestButton(emoji=emoji)  # hehe, butt
            await ctx.send(
                _("This is what your button will look like with this emoji!"),
                view=butt,
            )
        except Exception as e:
            return await ctx.send(_("Failed to create test button. Error:\n") + f"{box(str(e), lang='python')}")
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].button_emoji = str(emoji)
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def toggle(
        self,
        ctx: commands.Context,
        panel_name: str,
    ):
        """
        Toggle a panel on/off

        Disabled panels will still show the button but it will be disabled
        """
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        if panel.disabled:
            panel.disabled = False
            txt = _("Panel **Enabled**")
        else:
            panel.disabled = True
            txt = _("Panel **Disabled**")
        await self.save()
        await ctx.send(txt)
        await asyncio.sleep(3)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def ticketname(self, ctx: commands.Context, panel_name: str, *, ticket_name: str):
        """
        Set the default ticket channel name for a panel

        You can include the following in the name
        `{num}` - Ticket number
        `{user}` - user's name
        `{displayname}` - user's display name
        `{id}` - user's ID
        `{shortdate}` - mm-dd
        `{longdate}` - mm-dd-yyyy
        `{time}` - hh-mm AM/PM according to bot host system time

        You can set this to {default} to use default "Ticket-Username
        """
        panel_name = panel_name.lower()
        ticket_name = ticket_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].ticket_name = ticket_name
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def usethreads(self, ctx: commands.Context, panel_name: str):
        """Toggle whether a certain panel uses threads or channels"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        if not panel.channel_id:
            return await ctx.send(_("Set a panel channel first!"))
        channel = ctx.guild.get_channel(panel.channel_id)
        if not channel.permissions_for(ctx.guild.me).create_private_threads:
            return await ctx.send(_("I am missing the `Create Private Threads` permission!"))
        if not channel.permissions_for(ctx.guild.me).send_messages_in_threads:
            return await ctx.send(_("I am missing the `Send Messages in Threads` permission!"))
        if panel.threads:
            panel.threads = False
            await ctx.send(_("The {} panel will no longer use threads").format(panel_name))
        else:
            panel.threads = True
            await ctx.send(_("The {} panel will now use threads").format(panel_name))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def closemodal(self, ctx: commands.Context, panel_name: str):
        """Throw a modal when the close button is clicked to enter a reason"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        if panel.close_reason:
            panel.close_reason = False
            await ctx.send(_("The {} panel will no longer show a close reason modal").format(panel_name))
        else:
            panel.close_reason = True
            await ctx.send(_("The {} panel will now show a close reason modal").format(panel_name))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def logchannel(
        self,
        ctx: commands.Context,
        panel_name: str,
        channel: discord.TextChannel,
    ):
        """Set the logging channel for each panel's tickets"""
        panel_name = panel_name.lower()
        if not channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send(_("I cannot see that channel!"))
        if not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that channel!"))
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send(_("I cannot send messages in that channel!"))
        if not channel.permissions_for(ctx.guild.me).embed_links:
            return await ctx.send(_("I cannot embed links in that channel!"))
        if not channel.permissions_for(ctx.guild.me).attach_files:
            return await ctx.send(_("I cannot attach files in that channel!"))
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].log_channel = channel.id
        await self.save()
        await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def modaltitle(self, ctx: commands.Context, panel_name: str, *, title: str = ""):
        """Set a title for a ticket panel's modal"""
        if len(title) > 45:
            return await ctx.send(_("The max length is 45!"))
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        if title:
            conf.panels[panel_name].modal_title = title
            await ctx.send(_("Modal title set!"))
        else:
            conf.panels[panel_name].modal_title = ""
            await ctx.send(_("Modal title removed!"))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def addmodal(self, ctx: commands.Context, panel_name: str, field_name: str):
        """
        Add a modal field a ticket panel

        Ticket panels can have up to 5 fields per modal for the user to fill out before opening a ticket.
        If modal fields are added and have required fields,
        the user will have to fill them out before they can open a ticket.

        There is no toggle for modals, if a panel has them it will use them, if they don't then it just opens the ticket
        When the ticket is opened, it sends the modal field responses in an embed below the ticket message

        **Note**
        `field_name` is just the name of the field stored in config,
        it won't be shown in the modal and should not have spaces in it


        Specify an existing field name to delete a modal field (non-case-sensitive)
        """
        panel_name = panel_name.lower()
        field_name = field_name.lower()
        await self.create_or_edit_modal(ctx, panel_name, field_name)

    async def create_or_edit_modal(
        self,
        ctx: commands.Context,
        panel_name: str,
        field_name: str,
        existing_modal: Optional[dict] = None,
        preview: Optional[discord.Message] = None,
    ):
        if not existing_modal:
            # User wants to add or delete a field
            conf = self.db.get_conf(ctx.guild)
            if panel_name not in conf.panels:
                return await ctx.send(_("Panel does not exist!"))

            existing = conf.panels[panel_name].modal
            if field_name in existing:
                # Delete field
                del conf.panels[panel_name].modal[field_name]
                await self.save()
                return await ctx.send(_("Field for {} panel has been removed!").format(panel_name))

            if len(existing) >= 5:
                txt = _("The most fields a modal can have is 5!")
                return await ctx.send(txt)

        async def make_preview(m, mm: discord.Message):
            txt = ""
            for k, v in m.items():
                if k == "answer":
                    continue
                txt += f"{k}: {v}\n"
            title = "Modal Preview"
            await mm.edit(
                embed=discord.Embed(title=title, description=box(txt), color=color),
                view=None,
            )

        async def cancel(m):
            await m.edit(embed=discord.Embed(description=_("Modal field addition cancelled"), color=color))

        foot = _("type 'cancel' to cancel at any time")
        color = ctx.author.color

        modal = ModalField(label="").model_dump() if not existing_modal else existing_modal
        if preview:
            await make_preview(modal, preview)

        # Label
        em = Embed(
            description=_("What would you like the field label to be? (45 chars or less)"),
            color=color,
        )
        em.set_footer(text=foot)
        msg = await ctx.send(embed=em)
        label = await wait_reply(ctx, 300, False)
        if not label:
            return await cancel(msg)
        if len(label) > 45:
            em = Embed(
                description=_("Modal field labels must be 45 characters or less!"),
                color=color,
            )
            return await msg.edit(embed=em)
        modal["label"] = label

        if not preview:
            preview = msg

        await make_preview(modal, preview)

        # Style
        em = Embed(
            description=_("What style would you like the text box to be? (long/short)"),
            color=color,
        )
        em.set_footer(text=foot)
        msg = await ctx.send(embed=em)
        style = await wait_reply(ctx, 300, False)
        if not style:
            return await cancel(msg)
        if style not in ["long", "short"]:
            em = Embed(
                description=_("Style must be long or short!"),
                color=color,
            )
            return await msg.edit(embed=em)
        modal["style"] = style
        await make_preview(modal, preview)

        # Placeholder
        em = Embed(
            description=_(
                "Would you like to set a placeholder for the text field?\n"
                "This is text that shows up in the box before the user types."
            ),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_("Type your desired placeholder below (100 chars max)"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            placeholder = await wait_reply(ctx, 300, False)
            if not placeholder:
                return await cancel(msg)
            if len(placeholder) > 100:
                em = Embed(
                    description=_("Placeholders must be 100 characters or less!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            modal["placeholder"] = placeholder
            await make_preview(modal, preview)

        # Default
        em = Embed(
            description=_("Would you like to set a default value for the text field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_("Type your desired default value below"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            default = await wait_reply(ctx, 300, False)
            if not default:
                return await cancel(msg)
            modal["default"] = default
            await make_preview(modal, preview)

        # Required?
        em = Embed(
            description=_("Would you like to make this field required?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            modal["required"] = False
            await make_preview(modal, preview)

        # Min length
        em = Embed(
            description=_("Would you like to set a minimum length for this field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        min_length = 0
        if yes:
            em = Embed(
                description=_("Type the minimum length for this field below (less than 1024)"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            min_length = await wait_reply(ctx, 300, False)
            if not min_length:
                return await cancel(msg)
            if not min_length.isdigit():
                em = Embed(
                    description=_("That is not a number!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            min_length = min(1023, int(min_length))  # Make sure answer is between 0 and 1023
            modal["min_length"] = min_length
            await make_preview(modal, preview)

        # Max length
        em = Embed(
            description=_("Would you like to set a maximum length for this field?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(
                description=_("Type the maximum length for this field below (up to 1024)"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            maxlength = await wait_reply(ctx, 300, False)
            if not maxlength:
                return await cancel(msg)
            if not maxlength.isdigit():
                em = discord.Embed(
                    description=_("That is not a number!"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)
            max_length = max(min(1024, int(maxlength)), 1)  # Make sure answer is between 1 and 1024
            if max_length < min_length:
                em = Embed(
                    description=_("Max length cannot be less than the minimum length 😑"),
                    color=discord.Color.red(),
                )
                return await msg.edit(embed=em)

            modal["max_length"] = max_length  # Make sure answer is between 1 and 1024
            await make_preview(modal, preview)

        conf = self.db.get_conf(ctx.guild)
        conf.panels[panel_name].modal[field_name] = ModalField.load(modal)
        await self.save()

        await ctx.tick()
        desc = _("Your modal field has been added!")
        if existing_modal:
            desc = _("Your modal field has been edited!")
        em = Embed(
            description=desc,
            color=discord.Color.green(),
        )
        await msg.edit(embed=em)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def viewmodal(self, ctx: commands.Context, panel_name: str):
        """View/Delete a ticket message for a support ticket panel"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        modal = conf.panels[panel_name].modal
        if not modal:
            return await ctx.send(_("This panel does not have any modal fields set!"))
        embeds = []
        for i, fieldname in enumerate(list(modal.keys())):
            info = modal[fieldname]
            txt = _("`Label: `{}\n").format(info.label)
            txt += _("`Style: `{}\n").format(info.style)
            txt += _("`Placeholder: `{}\n").format(info.placeholder)
            txt += _("`Default:     `{}\n").format(info.default)
            txt += _("`Required:    `{}\n").format(info.required)
            txt += _("`Min Length:  `{}\n").format(info.min_length)
            txt += _("`Max Length:  `{}\n").format(info.max_length)

            desc = f"**{fieldname}**\n{txt}\n"
            desc += _("Page") + f" `{i + 1}/{len(list(modal.keys()))}`"

            em = Embed(
                title=_("Modal Fields for {}").format(panel_name),
                description=desc,
                color=ctx.author.color,
            )
            em.set_footer(text=f"{panel_name}|{fieldname}")
            embeds.append(em)

        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_modal_field
        controls["\N{MEMO}"] = self.edit_modal_field
        await menu(ctx, embeds, controls)

    async def edit_modal_field(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        em: Embed = instance.view.pages[index]
        panel_name, fieldname = em.footer.text.split("|")
        conf = self.db.get_conf(interaction.guild)
        modal = conf.panels[panel_name].modal[fieldname].dump()
        em = Embed(description=_("Editing {} modal field for {}!").format(fieldname, panel_name))
        await interaction.response.send_message(embed=em, ephemeral=True)
        instance.view.stop()
        await self.create_or_edit_modal(instance.view.ctx, panel_name, fieldname, modal)

    async def delete_modal_field(self, instance: MenuButton, interaction: discord.Interaction):
        index = instance.view.page
        em: Embed = instance.view.pages[index]
        panel_name, fieldname = em.footer.text.split("|")
        conf = self.db.get_conf(interaction.guild)
        del conf.panels[panel_name].modal[fieldname]
        await self.save()

        em = Embed(description=_("Modal field has been deleted from ") + f"{panel_name}!")
        await interaction.response.send_message(embed=em, ephemeral=True)
        del instance.view.pages[index]
        if not len(instance.view.pages):
            em = Embed(description="There are no more modal fields for this panel")
            await interaction.followup.send(embed=em, ephemeral=True)
            instance.view.stop()
            return await instance.view.message.delete()
        instance.view.page += 1
        instance.view.page %= len(instance.view.pages)
        for i, embed in enumerate(instance.view.pages):
            embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
        return await menu(
            instance.view.ctx,
            instance.view.pages,
            instance.view.controls,
            instance.view.message,
            instance.view.page,
        )

    @tickets.command()
    async def addmessage(self, ctx: commands.Context, panel_name: str):
        """
        Add a message embed to be sent when a ticket is opened

        You can include any of these in the embed to be replaced by their value when the message is sent
        `{username}` - Person's Discord username
        `{mention}` - This will mention the user
        `{id}` - This is the ID of the user that created the ticket

        The bot will walk you through a few steps to set up the embed including:
        - Title (optional)
        - Description (required)
        - Footer (optional)
        - Custom color (optional) - hex color code like #FF0000
        - Image (optional) - URL to an image
        """
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        foot = _("type 'cancel' to cancel the setup")
        color = ctx.author.color
        # TITLE
        em = Embed(
            description=_("Would you like this ticket embed to have a title?"),
            color=color,
        )
        msg = await ctx.send(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your desired title below"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            title = await wait_reply(ctx, 300)
            if title and title.lower().strip() == "cancel":
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            title = None
        # BODY
        em = Embed(
            description=_("Type your desired ticket message below"),
            color=color,
        )
        em.set_footer(text=foot)
        await msg.edit(embed=em)
        desc = await wait_reply(ctx, 600)
        if desc and desc.lower().strip() == "cancel":
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        if desc is None:
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        # FOOTER
        em = Embed(
            description=_("Would you like this ticket embed to have a footer?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your footer"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            footer = await wait_reply(ctx, 300)
            if footer and footer.lower().strip() == _("cancel"):
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            footer = None

        # CUSTOM COLOR
        em = Embed(
            description=_("Would you like this ticket embed to have a custom color?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        embed_color = None
        if yes:
            em = Embed(
                description=_("Enter a hex color code (e.g., #FF0000 for red, #00FF00 for green)"),
                color=color,
            )
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            color_input = await wait_reply(ctx, 300)
            if color_input and color_input.lower().strip() == _("cancel"):
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
            if color_input:
                # Parse the hex color
                color_input = color_input.strip().lstrip("#")
                try:
                    embed_color = int(color_input, 16)
                    # Validate it's a valid color value
                    if embed_color < 0 or embed_color > 0xFFFFFF:
                        em = Embed(description=_("Invalid color value! Using default color."), color=color)
                        await ctx.send(embed=em, delete_after=5)
                        embed_color = None
                except ValueError:
                    em = Embed(description=_("Invalid hex color format! Using default color."), color=color)
                    await ctx.send(embed=em, delete_after=5)
                    embed_color = None

        # IMAGE
        em = Embed(
            description=_("Would you like this ticket embed to have an image?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        image = None
        if yes:
            em = Embed(description=_("Enter the image URL"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            image = await wait_reply(ctx, 300)
            if image and image.lower().strip() == _("cancel"):
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)

        embed = {"title": title, "desc": desc, "footer": footer, "color": embed_color, "image": image}

        conf = self.db.get_conf(ctx.guild)
        conf.panels[panel_name].ticket_messages.append(TicketMessage.load(embed))
        await self.save()
        await ctx.tick()
        em = Embed(description=_("Your ticket message has been added!"))
        await msg.edit(embed=em)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def viewmessages(self, ctx: commands.Context, panel_name: str):
        """View/Delete a ticket message for a support ticket panel"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if not conf.panels:
            return await ctx.send(
                _("There are no panels available!\nUse ") + f"`{ctx.clean_prefix}tset addpanel` " + _("to create one.")
            )
        if panel_name not in conf.panels:
            valid = _("Valid panels are: ") + f"`{', '.join(list(conf.panels.keys()))}`"
            return await ctx.send(_("Panel does not exist!") + "\n" + valid)
        messages = conf.panels[panel_name].ticket_messages
        if not messages:
            return await ctx.send(_("This panel does not have any messages added!"))
        embeds = []
        for i, msg in enumerate(messages):
            desc = _("**Title**\n") + box(msg.title) + "\n"
            desc += _("**Description**\n") + box(msg.desc) + "\n"
            desc += _("**Footer**\n") + box(msg.footer) + "\n"
            # Display color as hex if it exists and is valid
            color_val = msg.color
            if color_val is not None and isinstance(color_val, int):
                desc += _("**Color**\n") + box(f"#{color_val:06X}") + "\n"
            else:
                desc += _("**Color**\n") + box(_("Default (user's color)")) + "\n"
            # Display image if it exists
            image_val = msg.image
            desc += _("**Image**\n") + box(image_val if image_val else _("None"))
            em = Embed(
                title=_("Ticket Messages for: ") + panel_name,
                description=desc,
                color=discord.Color(color_val)
                if color_val is not None and isinstance(color_val, int)
                else ctx.author.color,
            )
            # Show image preview if available
            if image_val:
                em.set_image(url=image_val)
            em.set_footer(text=_("Page") + f" {i + 1}/{len(messages)}")
            embeds.append(em)

        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel_message
        await menu(ctx, embeds, controls)

    async def delete_panel_message(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title.replace(_("Ticket Messages for: "), "")
        conf = self.db.get_conf(interaction.guild)
        del conf.panels[panel_name].ticket_messages[index]
        await self.save()
        em = Embed(description=_("Ticket message has been deleted from ") + f"{panel_name}!")
        await interaction.response.send_message(embed=em, ephemeral=True)
        del instance.view.pages[index]
        if not len(instance.view.pages):
            em = Embed(description="There are no more messages for this panel")
            return await interaction.followup.send(embed=em, ephemeral=True)
        instance.view.page += 1
        instance.view.page %= len(instance.view.pages)
        for i, embed in enumerate(instance.view.pages):
            embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
        await instance.view.handle_page(interaction.response.edit_message)

    @tickets.command()
    async def panels(self, ctx: commands.Context):
        """View/Delete currently configured support ticket panels"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.panels:
            return await ctx.send(
                _("There are no panels available!\nUse ") + f"`{ctx.clean_prefix}tset addpanel` " + _("to create one.")
            )
        embeds = []
        pages = len(conf.panels.keys())
        page = 1
        for panel_name, panel in conf.panels.items():
            cat = self.bot.get_channel(panel.category_id) if panel.category_id else "None"
            channel = self.bot.get_channel(panel.channel_id) if panel.channel_id else "None"
            extra = ""
            if panel.alt_channel:
                if alt := self.bot.get_channel(panel.alt_channel):
                    channel = alt
                    extra = _("(alt)")
            logchannel = self.bot.get_channel(panel.log_channel) if panel.log_channel else "None"

            panel_roles = ""
            for role_id, mention_toggle in panel.roles:
                role = ctx.guild.get_role(role_id)
                if not role:
                    continue
                panel_roles += f"{role.mention}({mention_toggle})\n"

            open_roles = ""
            for role_id in panel.required_roles:
                role = ctx.guild.get_role(role_id)
                if not role:
                    continue
                open_roles += f"{role.mention}\n"

            desc = _("`Disabled:       `") + f"{panel.disabled}\n"
            desc += _("`Category:       `") + f"{cat}\n"
            desc += _("`Channel:        `") + f"{channel}{extra}\n"
            desc += _("`MessageID:      `") + f"{panel.message_id}\n"
            desc += _("`ButtonText:     `") + f"{panel.button_text}\n"
            desc += _("`ButtonColor:    `") + f"{panel.button_color}\n"
            desc += _("`ButtonEmoji:    `") + f"{panel.button_emoji}\n"
            desc += _("`TicketNum:      `") + f"{panel.ticket_num}\n"
            desc += _("`Use Threads:    `") + f"{panel.threads}\n"
            desc += _("`TicketMessages: `") + f"{len(panel.ticket_messages)}\n"
            desc += _("`TicketName:     `") + f"{panel.ticket_name}\n"
            desc += _("`Modal Fields:   `") + f"{len(panel.modal)}\n"
            desc += _("`Modal Title:    `") + f"{panel.modal_title or 'None'}\n"
            desc += _("`LogChannel:     `") + f"{logchannel}\n"
            desc += _("`Priority:       `") + f"{panel.priority}\n"
            desc += _("`Button Row:     `") + f"{panel.row}\n"
            desc += _("`Reason Modal:   `") + f"{panel.close_reason}\n"
            desc += _("`Max Claims:     `") + f"{panel.max_claims}\n"

            # Working hours info
            has_working_hours = bool(panel.working_hours)
            desc += _("`Working Hours:  `") + (_("Configured") if has_working_hours else _("Not Set")) + "\n"
            if has_working_hours:
                desc += _("`Timezone:       `") + f"{panel.timezone}\n"
                desc += _("`Block Outside:  `") + f"{panel.block_outside_hours}"

            em = Embed(
                title=panel_name,
                description=desc,
                color=ctx.author.color,
            )
            if panel_roles:
                em.add_field(name=_("Panel Roles(Mention)"), value=panel_roles)
            if open_roles:
                em.add_field(name=_("Required Roles to Open"), value=open_roles)
            em.set_footer(text=_("Page ") + f"{page}/{pages}")
            page += 1
            embeds.append(em)
        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel
        await menu(ctx, embeds, controls)

    async def delete_panel(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title
        conf = self.db.get_conf(interaction.guild)
        del conf.panels[panel_name]
        await self.save()
        em = Embed(description=panel_name + _(" panel has been deleted!"))
        await interaction.response.send_message(embed=em, ephemeral=True)
        del instance.view.pages[index]
        instance.view.page += 1
        instance.view.page %= len(instance.view.pages)
        for i, embed in enumerate(instance.view.pages):
            embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
        if not instance.view.pages:
            em = Embed(description=_("There are no more panels configured!"))
            await interaction.response.edit_message(embed=em, view=None)
            await interaction.response.defer()
            instance.view.stop()

    @tickets.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View support ticket settings"""
        conf = self.db.get_conf(ctx.guild)
        inactive = conf.inactive
        plural = _("hours")
        singular = _("hour")
        no_resp = f"{inactive} {singular if inactive == 1 else plural}"
        if not inactive:
            no_resp = _("Disabled")

        transcript_type = _("Detailed") if conf.detailed_transcript else _("Simple")

        msg = _("`Max Tickets:      `") + f"{conf.max_tickets}\n"
        msg += _("`DM Alerts:        `") + f"{conf.dm}\n"
        msg += _("`Users can Rename: `") + f"{conf.user_can_rename}\n"
        msg += _("`Users can Close:  `") + f"{conf.user_can_close}\n"
        msg += _("`Users can Manage: `") + f"{conf.user_can_manage}\n"
        msg += _("`Save Transcripts: `") + f"{conf.transcript} ({transcript_type})\n"
        msg += _("`Show Resp. Time:  `") + f"{conf.show_response_time}\n"
        msg += _("`Auto Close:       `") + (_("On") if inactive else _("Off")) + "\n"
        msg += _("`NoResponseDelete: `") + no_resp

        suproles = ""
        if conf.support_roles:
            for role_id, mention_toggle in conf.support_roles:
                role = ctx.guild.get_role(role_id)
                if role:
                    suproles += f"{role.mention}({mention_toggle})\n"
        blacklisted = ""
        if conf.blacklist:
            for uid_or_rid in conf.blacklist:
                user_or_role = ctx.guild.get_member(uid_or_rid) or ctx.guild.get_role(uid_or_rid)
                if user_or_role:
                    blacklisted += f"{user_or_role.mention}-{user_or_role.id}\n"
                else:
                    blacklisted += _("Invalid") + f"-{uid_or_rid}\n"
        embed = Embed(
            title=_("Tickets Core Settings"),
            description=msg,
            color=discord.Color.random(),
        )
        if suproles:
            embed.add_field(name=_("Support Roles(Mention)"), value=suproles, inline=False)
        if blacklisted:
            embed.add_field(name=_("Blacklist"), value=blacklisted, inline=False)

        if conf.thread_close:
            txt = _("Thread tickets will be closed/archived rather than deleted")
        else:
            txt = _("Thread tickets will be deleted instead of closed/archived")
        embed.add_field(name=_("Thread Tickets"), value=txt, inline=False)

        embed.add_field(
            name=_("Thread Ticket Auto-Add"),
            value=_("Auto-add support and panel roles to tickets that use threads: **{}**").format(str(conf.auto_add)),
        )
        if conf.suspended_msg:
            embed.add_field(
                name=_("Suspended Message"),
                value=_("Tickets are currently suspended, users will be met with the following message\n{}").format(
                    box(conf.suspended_msg)
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @tickets.command()
    async def maxtickets(self, ctx: commands.Context, amount: int):
        """Set the max tickets a user can have open at one time of any kind"""
        if not amount:
            return await ctx.send(_("Max ticket amount must be greater than 0!"))
        conf = self.db.get_conf(ctx.guild)
        conf.max_tickets = amount
        await self.save()
        await ctx.tick()

    @tickets.command()
    async def supportrole(
        self,
        ctx: commands.Context,
        role: discord.Role,
        mention: Optional[bool] = False,
    ):
        """
        Add/Remove ticket support roles (one at a time)

        **Optional**: include `true` for mention to have that role mentioned when a ticket is opened

        To remove a role, simply run this command with it again to remove it
        """
        conf = self.db.get_conf(ctx.guild)
        entry = (role.id, mention)
        for i, (rid, _mention) in enumerate(conf.support_roles):
            if rid == role.id:
                conf.support_roles.pop(i)
                await ctx.send(_("{} has been removed from support roles").format(role.name))
                break
        else:
            conf.support_roles.append(entry)
            await ctx.send(role.name + _(" has been added to support roles"))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def panelrole(
        self,
        ctx: commands.Context,
        panel_name: str,
        role: discord.Role,
        mention: Optional[bool] = False,
    ):
        """
        Add/Remove roles for a specific panel

        To remove a role, simply run this command with it again to remove it

        **Optional**: include `true` for mention to have that role mentioned when a ticket is opened

        These roles are a specialized subset of the main support roles.
        Use this role type if you want to isolate specific groups to a certain panel.
        """
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        entry = (role.id, mention)
        for i, (rid, _mention) in enumerate(panel.roles):
            if rid == role.id:
                panel.roles.pop(i)
                await ctx.send(_("{} has been removed from the {} panel roles").format(role.name, panel_name))
                break
        else:
            panel.roles.append(entry)
            await ctx.send(role.name + _(" has been added to the {} panel roles").format(panel_name))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def maxclaims(self, ctx: commands.Context, panel_name: str, amount: commands.positive_int):
        """Set how many staff members can claim/join a ticket before the join button is disabled (If using threads)"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].max_claims = amount
        await self.save()
        await ctx.send(_("Up to {} staff member(s) can claim a single ticket").format(amount))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def workinghours(self, ctx: commands.Context, panel_name: str, day: str, start_time: str, end_time: str):
        """
        Set working hours for a specific day on a panel

        Times should be in 24-hour format (HH:MM), e.g., 09:00 or 17:30
        Days: monday, tuesday, wednesday, thursday, friday, saturday, sunday

        **Examples**
        `[p]tickets workinghours support monday 09:00 17:00`
        `[p]tickets workinghours support friday 10:00 18:00`

        To remove working hours for a day, use `[p]tickets workinghours <panel> <day> off`
        """
        panel_name = panel_name.lower()
        day = day.lower()

        valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if day not in valid_days:
            return await ctx.send(_("Invalid day! Must be one of: {}").format(", ".join(valid_days)))

        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]

        # Check if removing hours
        if start_time.lower() == "off":
            if day in panel.working_hours:
                del panel.working_hours[day]
                await self.save()
                return await ctx.send(
                    _("Working hours for {} on {} have been removed.").format(day.capitalize(), panel_name)
                )
            else:
                return await ctx.send(_("No working hours were set for {} on {}.").format(day.capitalize(), panel_name))

        # Validate time format
        time_pattern = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$")

        if not time_pattern.match(start_time):
            return await ctx.send(_("Invalid start time format! Use HH:MM (24-hour format), e.g., 09:00 or 17:30"))
        if not time_pattern.match(end_time):
            return await ctx.send(_("Invalid end time format! Use HH:MM (24-hour format), e.g., 09:00 or 17:30"))

        # Normalize times to ensure consistent HH:MM format
        start_parts = start_time.split(":")
        end_parts = end_time.split(":")
        start_time = f"{int(start_parts[0]):02d}:{start_parts[1]}"
        end_time = f"{int(end_parts[0]):02d}:{end_parts[1]}"

        panel.working_hours[day] = DayHours(start=start_time, end=end_time)
        await self.save()

        await ctx.send(
            _("Working hours for {} on {}: {} to {}").format(day.capitalize(), panel_name, start_time, end_time)
        )

    @tickets.command()
    async def timezone(self, ctx: commands.Context, panel_name: str, *, timezone_str: str):
        """
        Set the timezone for a panel's working hours

        Use IANA timezone names (e.g., America/New_York, Europe/London, Asia/Tokyo)
        Default is UTC if not set.

        **Examples**
        `[p]tickets timezone support America/New_York`
        `[p]tickets timezone support Europe/London`
        `[p]tickets timezone support UTC`
        """
        panel_name = panel_name.lower()

        # Validate timezone
        try:
            pytz.timezone(timezone_str)
        except Exception:
            return await ctx.send(
                _("Invalid timezone! Use IANA timezone names like `America/New_York`, `Europe/London`, or `UTC`.")
            )

        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].timezone = timezone_str
        await self.save()

        await ctx.send(_("Timezone for {} panel set to {}").format(panel_name, timezone_str))

    @tickets.command()
    async def blockoutside(self, ctx: commands.Context, panel_name: str):
        """
        Toggle blocking ticket creation outside working hours

        When enabled, users cannot create tickets outside of the configured working hours.
        When disabled (default), users can still create tickets but will see a notice about delayed responses.
        """
        panel_name = panel_name.lower()

        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        panel.block_outside_hours = not panel.block_outside_hours
        await self.save()

        if panel.block_outside_hours:
            await ctx.send(_("Ticket creation is now **blocked** outside of working hours for {}").format(panel_name))
        else:
            await ctx.send(
                _("Ticket creation is now **allowed** outside of working hours for {} (with notice)").format(panel_name)
            )

    @tickets.command()
    async def outsidehoursmsg(self, ctx: commands.Context, panel_name: str, *, message: str = ""):
        """
        Set a custom message to display when a ticket is created outside working hours

        Leave message empty to reset to default.
        The default message will inform users that response times may be delayed.

        **Example**
        `[p]tickets outsidehoursmsg support Our team is currently offline. We'll respond during business hours!`
        """
        panel_name = panel_name.lower()

        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]

        if message:
            if len(message) > 1000:
                return await ctx.send(_("Message must be 1000 characters or less!"))
            panel.outside_hours_message = message
            await ctx.send(_("Custom outside hours message has been set!"))
        else:
            panel.outside_hours_message = ""
            await ctx.send(_("Outside hours message has been reset to default."))
        await self.save()

    @tickets.command()
    async def viewhours(self, ctx: commands.Context, panel_name: str):
        """View the configured working hours for a panel"""
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)

        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))

        panel = conf.panels[panel_name]
        working_hours = panel.working_hours

        if not working_hours:
            return await ctx.send(
                _("No working hours have been configured for {}. Tickets can be opened at any time.").format(panel_name)
            )

        # Build embed
        em = Embed(
            title=_("Working Hours for {}").format(panel_name),
            color=ctx.author.color,
        )

        days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        hours_text = ""
        for day in days_order:
            day_hours = working_hours.get(day)
            if day_hours:
                hours_text += f"**{day.capitalize()}:** `{day_hours.start}` - `{day_hours.end}`\n"
            else:
                hours_text += f"**{day.capitalize()}:** _Closed_\n"

        em.add_field(name=_("Schedule"), value=hours_text, inline=False)
        em.add_field(name=_("Timezone"), value=f"`{panel.timezone}`", inline=True)
        em.add_field(
            name=_("Block Outside Hours"),
            value=_("Yes") if panel.block_outside_hours else _("No"),
            inline=True,
        )

        if panel.outside_hours_message:
            em.add_field(
                name=_("Custom Message"),
                value=panel.outside_hours_message[:200] + ("..." if len(panel.outside_hours_message) > 200 else ""),
                inline=False,
            )

        await ctx.send(embed=em)

    @tickets.command()
    async def openrole(self, ctx: commands.Context, panel_name: str, *, role: discord.Role):
        """
        Add/Remove roles required to open a ticket for a specific panel

        Specify the same role to remove it
        """
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]

        if role.id in panel.required_roles:
            panel.required_roles.remove(role.id)
            await ctx.send(
                _("{} has been removed from the {} panel's required open roles").format(role.name, panel_name)
            )
        else:
            panel.required_roles.append(role.id)
            await ctx.send(role.name + _(" has been added to the {} panel's required open roles").format(panel_name))
        await self.save()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def altchannel(
        self,
        ctx: commands.Context,
        panel_name: str,
        *,
        channel: Union[discord.TextChannel, discord.CategoryChannel],
    ):
        """
        Set an alternate channel that tickets will be opened under for a panel

        If the panel uses threads, this needs to be a normal text channel.
        If the panel uses channels, this needs to be a category.

        If the panel is a channel type and a channel is used, the bot will use the category associated with the channel.

        To remove the alt channel, specify the existing one
        """
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        if panel.alt_channel == channel.id:
            panel.alt_channel = 0
            await self.save()
            return await ctx.send(_("Alt channel has been removed for this panel!"))
        panel.alt_channel = channel.id
        await self.save()
        await ctx.send(_("Alt channel has been set to {}!").format(channel.name))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def priority(self, ctx: commands.Context, panel_name: str, priority: int):
        """Set the priority order of a panel's button"""
        if priority < 1 or priority > 25:
            return await ctx.send(_("Priority needs to be between 1 and 25"))
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        conf.panels[panel_name].priority = priority
        await self.save()
        await ctx.send(_("Priority for this panel has been set to {}!").format(priority))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def row(self, ctx: commands.Context, panel_name: str, row: int):
        """Set the row of a panel's button (0 - 4)"""
        if row < 0 or row > 4:
            return await ctx.send(_("Row needs to be between 0 and 4"))
        panel_name = panel_name.lower()
        conf = self.db.get_conf(ctx.guild)
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))

        panel = conf.panels[panel_name]
        panel_key = f"{panel.channel_id}{panel.message_id}"
        count = 0
        for p in conf.panels.values():
            panel_key2 = f"{p.channel_id}{p.message_id}"
            if panel_key != panel_key2:
                continue
            if not p.row:
                continue
            if p.row == row:
                count += 1

        if count > 4:
            return await ctx.send(_("This panel message already has the max amount of buttons for that specific row"))
        panel.row = row
        await self.save()
        await ctx.send(_("The row number for this panel has been set to {}!").format(row))
        await self.initialize(ctx.guild)

    @tickets.command()
    async def blacklist(
        self,
        ctx: commands.Context,
        *,
        user_or_role: Union[discord.Member, discord.Role],
    ):
        """
        Add/Remove users or roles from the blacklist

        Users and roles in the blacklist will not be able to create a ticket
        """
        conf = self.db.get_conf(ctx.guild)
        if user_or_role.id in conf.blacklist:
            conf.blacklist.remove(user_or_role.id)
            await ctx.send(user_or_role.name + _(" has been removed from the blacklist"))
        else:
            conf.blacklist.append(user_or_role.id)
            await ctx.send(user_or_role.name + _(" has been added to the blacklist"))
        await self.save()

    @tickets.command()
    async def noresponse(self, ctx: commands.Context, hours: int):
        """
        Auto-close ticket if opener doesn't say anything after X hours of opening

        Set to 0 to disable this

        If using thread tickets, this translates to the thread's "Hide after inactivity" setting.
        Your options are:
        - 1 hour
        - 24 hours (1 day)
        - 72 hours (3 days)
        - 168 hours (1 week)
        Tickets will default to the closest value you select.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.inactive = hours
        await self.save()
        await ctx.tick()

    @tickets.command()
    async def overview(
        self,
        ctx: commands.Context,
        *,
        channel: Optional[discord.TextChannel] = None,
    ):
        """
        Set a channel for the live overview message

        The overview message shows all active tickets across all configured panels for a server.
        """
        conf = self.db.get_conf(ctx.guild)
        if not channel:
            await ctx.send(_("Overview channel has been **Disabled**"))
            conf.overview_channel = 0
        else:
            await ctx.send(_("Overview channel has been set to {}").format(channel.mention))
            conf.overview_channel = channel.id
            new_id = await update_active_overview(ctx.guild, conf, self)
            if new_id:
                conf.overview_msg = new_id
        await self.save()

    @tickets.command()
    async def overviewmention(self, ctx: commands.Context):
        """Toggle whether channels are mentioned in the active ticket overview"""
        conf = self.db.get_conf(ctx.guild)
        conf.overview_mention = not conf.overview_mention
        await self.save()
        if not conf.overview_mention:
            txt = _("Ticket channels will no longer be mentioned in the active ticket channel")
        else:
            txt = _("Ticket channels now be mentioned in the active ticket channel")
        await ctx.send(txt)

    @tickets.command()
    async def cleanup(self, ctx: commands.Context):
        """Cleanup tickets that no longer exist"""
        async with ctx.typing():
            conf = self.db.get_conf(ctx.guild)
            await prune_invalid_tickets(ctx.guild, conf, self, ctx)

    @tickets.command()
    async def getlink(self, ctx: commands.Context, message: discord.Message):
        """
        Get a direct download link for a ticket transcript

        The HTML transcript can be downloaded and opened in any web browser.
        """
        notrans = _("This message does not have a transcript attached!")
        if not message.attachments:
            return await ctx.send(notrans)
        attachment = message.attachments[0]
        if not attachment.filename.endswith(".html"):
            return await ctx.send(notrans)
        user_id = attachment.filename.split("-")[-1].split(".")[0]
        if not user_id.isdigit():
            return await ctx.send(notrans)

        # Provide direct download link - the HTML is self-contained with embedded images
        embed = discord.Embed(
            title=_("Transcript Download"),
            description=_(
                "Click the button below to download the transcript.\nThe HTML file can be opened in any web browser."
            ),
            color=discord.Color.blue(),
        )
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label=_("Download Transcript"),
                style=discord.ButtonStyle.link,
                url=attachment.url,
            )
        )
        await ctx.send(embed=embed, view=view, delete_after=3600)

    # TOGGLES --------------------------------------------------------------------------------
    @tickets.command()
    async def dm(self, ctx: commands.Context):
        """(Toggle) The bot sending DM's for ticket alerts"""
        conf = self.db.get_conf(ctx.guild)
        conf.dm = not conf.dm
        await self.save()
        if conf.dm:
            await ctx.send(_("DM alerts have been **Enabled**"))
        else:
            await ctx.send(_("DM alerts have been **Disabled**"))

    @tickets.command()
    async def threadclose(self, ctx: commands.Context):
        """(Toggle) Thread tickets being closed & archived instead of deleted"""
        conf = self.db.get_conf(ctx.guild)
        conf.thread_close = not conf.thread_close
        await self.save()
        if conf.thread_close:
            await ctx.send(_("Closed ticket threads will be **Closed & Archived**"))
        else:
            await ctx.send(_("Closed ticket threads will be **Deleted**"))

    @tickets.command()
    async def selfrename(self, ctx: commands.Context):
        """(Toggle) If users can rename their own tickets"""
        conf = self.db.get_conf(ctx.guild)
        conf.user_can_rename = not conf.user_can_rename
        await self.save()
        if conf.user_can_rename:
            await ctx.send(_("User can now rename their support channel"))
        else:
            await ctx.send(_("User can no longer rename their support channel"))

    @tickets.command()
    async def selfclose(self, ctx: commands.Context):
        """(Toggle) If users can close their own tickets"""
        conf = self.db.get_conf(ctx.guild)
        conf.user_can_close = not conf.user_can_close
        await self.save()
        if conf.user_can_close:
            await ctx.send(_("User can now close their support ticket channel"))
        else:
            await ctx.send(_("User can no longer close their support ticket channel"))

    @tickets.command()
    async def selfmanage(self, ctx: commands.Context):
        """
        (Toggle) If users can manage their own tickets

        Users will be able to add/remove others to their support ticket
        """
        conf = self.db.get_conf(ctx.guild)
        conf.user_can_manage = not conf.user_can_manage
        await self.save()
        if conf.user_can_manage:
            await ctx.send(_("User can now manage their support ticket channel"))
        else:
            await ctx.send(_("User can no longer manage their support ticket channel"))

    @tickets.command()
    async def autoadd(self, ctx: commands.Context):
        """
        (Toggle) Auto-add support and panel roles to thread tickets

        Adding a user to a thread pings them, so this is off by default
        """
        conf = self.db.get_conf(ctx.guild)
        conf.auto_add = not conf.auto_add
        await self.save()
        if conf.auto_add:
            await ctx.send(_("Support and panel roles will be auto-added to thread tickets"))
        else:
            await ctx.send(_("Support and panel roles will no longer be auto-added to thread tickets"))

    @tickets.command()
    async def showresponsetime(self, ctx: commands.Context):
        """(Toggle) Show average response time to users when they open a ticket"""
        conf = self.db.get_conf(ctx.guild)
        conf.show_response_time = not conf.show_response_time
        await self.save()
        if conf.show_response_time:
            await ctx.send(_("Average response time will now be shown to users"))
        else:
            await ctx.send(_("Average response time will no longer be shown to users"))

    @tickets.command()
    async def transcript(self, ctx: commands.Context):
        """
        (Toggle) Ticket transcripts

        Closed tickets will have their transcripts uploaded to the log channel
        """
        conf = self.db.get_conf(ctx.guild)
        conf.transcript = not conf.transcript
        await self.save()
        if conf.transcript:
            await ctx.send(_("Transcripts of closed tickets will now be saved"))
        else:
            await ctx.send(_("Transcripts of closed tickets will no longer be saved"))

    @tickets.command(aliases=["intertrans", "itrans", "itranscript"])
    async def interactivetranscript(self, ctx: commands.Context):
        """
        (Toggle) Interactive transcripts

        Transcripts will be an interactive html file to visualize the conversation from your browser.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.detailed_transcript = not conf.detailed_transcript
        await self.save()
        if conf.detailed_transcript:
            await ctx.send(_("Transcripts of closed tickets will now be interactive"))
        else:
            await ctx.send(_("Transcripts of closed tickets will no longer be interactive"))

    @tickets.command()
    async def updatemessage(
        self,
        ctx: commands.Context,
        source: discord.Message,
        target: discord.Message,
    ):
        """Update a message with another message (Target gets updated using the source)"""
        try:
            await target.edit(
                embeds=source.embeds,
                content=target.content,
                attachments=target.attachments,
            )
            await ctx.tick()
        except discord.HTTPException as e:
            if txt := e.text:
                await ctx.send(txt)
            else:
                await ctx.send(_("Failed to update message!"))

    @tickets.command()
    async def embed(
        self,
        ctx: commands.Context,
        color: Optional[discord.Color],
        channel: Optional[discord.TextChannel],
        title: str,
        *,
        description: str,
    ):
        """Create an embed for ticket panel buttons to be added to"""
        foot = _("type 'cancel' to cancel")
        channel = channel or ctx.channel
        color = color or ctx.author.color
        # FOOTER
        em = Embed(
            description=_("Would you like this embed to have a footer?"),
            color=color,
        )
        msg = await ctx.send(embed=em)
        yes = await confirm(ctx, msg)
        if yes:
            em = Embed(description=_("Enter the desired footer"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            footer = await wait_reply(ctx, 300)
            if footer and footer.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            footer = None

        # Thumbnail
        em = Embed(
            description=_("Would you like this embed to have a thumbnail?"),
            color=color,
        )
        try:
            await msg.edit(embed=em)
        except discord.NotFound:
            # Message was deleted. Just cancel.
            return
        yes = await confirm(ctx, msg)
        if yes is None:
            return

        if yes:
            em = Embed(description=_("Enter a url for the thumbnail"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            thumbnail = await wait_reply(ctx, 300)
            if thumbnail and thumbnail.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            thumbnail = None

        # Image
        em = Embed(
            description=_("Would you like this embed to have an image?"),
            color=color,
        )
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes:
            em = Embed(description=_("Enter a url for the image"), color=color)
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            image = await wait_reply(ctx, 300)
            if image and image.lower().strip() == _("cancel"):
                em = Embed(description=_("Embed creation cancelled"))
                return await msg.edit(embed=em)
        else:
            image = None

        embed = discord.Embed(title=title, description=description, color=color)
        if footer:
            embed.set_footer(text=footer)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)

        fields = 0
        while fields < 25:
            if not fields:
                em = Embed(
                    description=_("Would you like to add a field to this embed?"),
                    color=color,
                )
            else:
                em = Embed(
                    description=_(
                        "Would you like to add another field to this embed?\n*There are currently {} fields*"
                    ).format(fields),
                    color=color,
                )
            await msg.edit(embed=em)
            yes = await confirm(ctx, msg)
            if yes:
                em = Embed(description=_("Enter the name of the field"), color=color)
                em.set_footer(text=foot)
                await msg.edit(embed=em)
                name = await wait_reply(ctx, 300)
                if name and name.lower().strip() == "cancel":
                    break
                em = Embed(description=_("Enter the value of the field"), color=color)
                em.set_footer(text=foot)
                await msg.edit(embed=em)
                value = await wait_reply(ctx, 300)
                if value and value.lower().strip() == "cancel":
                    break
                em = Embed(
                    description=_("Do you want this field to be inline?"),
                    color=color,
                )
                await msg.edit(embed=em)
                yes = await confirm(ctx, msg)
                inline = True if yes else False
                embed.add_field(name=name, value=value, inline=inline)
                fields += 1
            else:
                break

        try:
            await channel.send(embed=embed)
            await msg.edit(content=_("Your embed has been sent!"), embed=None)
        except Exception as e:
            await ctx.send(_("Failed to send embed!\nException: {}").format(box(str(e), "py")))

    @commands.hybrid_command(name="openfor")
    @commands.mod_or_permissions(manage_messages=True)
    async def openfor(self, ctx: commands.Context, user: discord.Member, *, panel_name: str):
        """Open a ticket for another user"""
        conf = self.db.get_conf(ctx.guild)
        panel_name = panel_name.lower()
        if panel_name not in conf.panels:
            return await ctx.send(_("Panel does not exist!"))
        panel = conf.panels[panel_name]
        # Create a custom temp view by manipulating the panel
        view = PanelView(self.bot, ctx.guild, self, [(panel_name, panel)], mock_user=user)
        desc = _(
            "Click the button below to open a {} ticket for {}\nThis message will self-cleanup in 2 minutes."
        ).format(panel_name, user.name)
        embed = discord.Embed(description=desc, color=await self.bot.get_embed_color(ctx))
        await ctx.send(embed=embed, view=view, delete_after=120)
        await asyncio.sleep(120)
        if not ctx.interaction:
            await ctx.tick()
