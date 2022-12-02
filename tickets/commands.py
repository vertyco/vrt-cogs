from typing import Union

import discord
from discord import Embed
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from .menu import menu, SMALL_CONTROLS
from .views import wait_reply, confirm, TestButton

_ = Translator("TicketsCommands", __file__)


class TicketCommands(commands.Cog):
    @commands.group(aliases=["tset"])
    @commands.guild_only()
    @commands.admin()
    async def tickets(self, ctx: commands.Context):
        """Base support ticket settings"""
        pass

    @tickets.command()
    async def setuphelp(self, ctx: commands.Context):
        """Ticket Setup Guide"""
        desc = _("To create a support ticket panel, type ") + f"`{ctx.prefix}tickets addpanel" + _(" <panel_name>`")
        em = Embed(
            title=_("Ticket Setup Guide"),
            description=desc,
            color=ctx.author.color
        )
        step1 = _("Set the category ID that new tickets will be created under.\n")
        step1 += f"`{ctx.prefix}tickets category " + _("<panel_name> <category_id>`")
        em.add_field(
            name=_("Step 1"),
            value=step1,
            inline=False
        )
        step2 = _("Set the channel that the bots ticket panel will be located in.\n")
        step2 += f"`{ctx.prefix}tickets channel " + _("<panel_name> <channel_id>`")
        em.add_field(
            name=_("Step 2"),
            value=step2,
            inline=False
        )
        step3 = _("Set the ID of the bots ticket panel message.\n")
        step3 += f"`{ctx.prefix}tickets panelmessage " + _("<panel_name> <message_id>`\n")
        step3 += _("At this point the ticket panel will be activated, "
                   "all following steps are for extra customization.\n")
        step3 += _("If the bot is having trouble finding the message, run the command in the same channel as it.")
        em.add_field(
            name=_("Step 3"),
            value=step3,
            inline=False
        )
        step4 = _("Set the text of the ticket panel button.\n")
        step4 += f"`{ctx.prefix}tickets buttontext " + _("<panel_name> <button_text>`")
        em.add_field(
            name=_("Button Text"),
            value=step4,
            inline=False
        )
        step5 = _("Set the ticket panel button color.\n")
        step5 += _("Valid colors are ") + "`red`, `blue`, `green`, and `grey`.\n"
        step5 += f"`{ctx.prefix}tickets buttoncolor " + _("<panel_name> <button_color>`")
        em.add_field(
            name=_("Button Color"),
            value=step5,
            inline=False
        )
        step6 = _("Set the button emoji for the ticket panel.\n")
        step6 += f"`{ctx.prefix}tickets buttonemoji " + _("<panel_name> <emoji>`")
        em.add_field(
            name=_("Button Emoji"),
            value=step6,
            inline=False
        )
        step7 = _("Add a message the bot sends to the user in their ticket.\n")
        step7 += f"`{ctx.prefix}tickets addmessage " + _("<panel_name>`")
        em.add_field(
            name=_("Ticket Messages"),
            value=step7,
            inline=False
        )
        step8 = _("View and remove a messages the bot sends to the user in their ticket.\n")
        step8 += f"`{ctx.prefix}tickets viewmessages " + _("<panel_name>`")
        em.add_field(
            name=_("Remove/View Ticket Messages"),
            value=step8,
            inline=False
        )
        step9 = _("Set the naming format for ticket channels that are opened.\n")
        step9 += f"`{ctx.prefix}tickets ticketname " + _("<panel_name> <name_format>`")
        em.add_field(
            name=_("Ticket Channel Name"),
            value=step9,
            inline=False
        )
        step10 = _("Set log channel for a ticket panel.\n")
        step10 += f"`{ctx.prefix}tickets logchannel " + _("<panel_name> <channel>`")
        em.add_field(
            name=_("Log Channel"),
            value=step10,
            inline=False
        )
        tip = _("Tip: you can create multiple support panels using the same message for a multi-button panel")
        em.set_footer(text=tip)
        await ctx.send(embed=em)

    @tickets.command()
    async def addpanel(self, ctx: commands.Context, panel_name: str):
        """Add a support ticket panel"""
        panel_name = panel_name.lower()
        em = Embed(
            title=panel_name + _(" Panel Saved"),
            description=_("Your panel has been added and will need to be configured."),
            color=ctx.author.color
        )
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name in panels:
                return await ctx.send(_("Panel already exists!"))
            panels[panel_name] = self.ticket_panel_schema
        await ctx.send(embed=em)

    @tickets.command()
    async def category(self, ctx: commands.Context, panel_name: str, category: discord.CategoryChannel):
        """Set the category ID for a ticket panel"""
        panel_name = panel_name.lower()
        if not category.permissions_for(ctx.me).manage_channels:
            return await ctx.send(_("I need the `manage channels` permission to set this category"))
        if not category.permissions_for(ctx.me).manage_permissions:
            return await ctx.send(_("I need the `manage roles` permission to set this category"))
        if not category.permissions_for(ctx.me).attach_files:
            return await ctx.send(_("I need the `attach files` permission to set this category"))
        if not category.permissions_for(ctx.me).view_channel:
            return await ctx.send(_("I cannot see that category!"))
        if not category.permissions_for(ctx.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that category!"))
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["category_id"] = category.id
            await ctx.tick()
            await ctx.send(_("New tickets will now be opened under that category!"))

    @tickets.command()
    async def channel(self, ctx: commands.Context, panel_name: str, channel: discord.TextChannel):
        """Set the channel ID where a ticket panel is located"""
        panel_name = panel_name.lower()
        if not channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send(_("I cannot see that channel!"))
        if not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(_("I cannot see message history in that channel!"))
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["channel_id"] = channel.id
            await ctx.tick()

    @tickets.command()
    async def panelmessage(self, ctx: commands.Context, panel_name: str, message: int):
        """
        Set the message ID of a ticket panel
        Run this command in the same channel as the ticket panel message
        """
        panel_name = panel_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            if not panels[panel_name]["category_id"]:
                return await ctx.send(_("Category ID must be set for this panel first!"))
            if not panels[panel_name]["channel_id"]:
                return await ctx.send(_("Channel ID must be set for this panel first!"))
            channel: discord.TextChannel = self.bot.get_channel(panels[panel_name]["channel_id"])
            if not channel:
                return await ctx.send(_("Cannot find channel associated with this panel!"))
            try:
                found = await channel.fetch_message(message)
            except discord.NotFound:
                return await ctx.send(_("I cannot find that message!"))
            if found.author.id != self.bot.user.id:
                return await ctx.send(_("I can only add buttons to my own messages!"))
            panels[panel_name]["message_id"] = found.id
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttontext(self, ctx: commands.Context, panel_name: str, *, button_text: str):
        """Set the button text for a support ticket panel"""
        panel_name = panel_name.lower()
        if len(button_text) > 80:
            return await ctx.send(_("The text content of a button must be less than 80 characters!"))
        butt = TestButton(label=button_text)  # hehe, butt
        await ctx.send(_("This is what your button will look like with this text!"), view=butt)
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_text"] = button_text
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
        await ctx.send(_("This is what your button will look like with this color!"), view=butt)
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_color"] = button_color
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def buttonemoji(self, ctx: commands.Context, panel_name: str, *,
                          emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """Set the button emoji for a support ticket panel"""
        panel_name = panel_name.lower()
        try:
            butt = TestButton(emoji=emoji)  # hehe, butt
            await ctx.send(_("This is what your button will look like with this emoji!"), view=butt)
        except Exception as e:
            return await ctx.send(_("Failed to create test button. Error:\n") + f"{box(str(e), lang='python')}")
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["button_emoji"] = str(emoji)
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def ticketname(self, ctx: commands.Context, panel_name: str, *, ticket_name: str):
        """
        Set the default ticket channel name for a panel

        You can include the following in the name
        `{num}` - Ticket number
        `{user}` - user's name
        `{id}` - user's ID
        `{shortdate}` - mm-dd
        `{longdate}` - mm-dd-yyyy
        `{time}` - hh-mm AM/PM according to bot host system time

        You can set this to {default} to use default "Ticket-Username
        """
        panel_name = panel_name.lower()
        ticket_name = ticket_name.lower()
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["ticket_name"] = ticket_name
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def logchannel(self, ctx: commands.Context, panel_name: str, channel: discord.TextChannel):
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
        async with self.config.guild(ctx.guild).panels() as panels:
            if panel_name not in panels:
                return await ctx.send(_("Panel does not exist!"))
            panels[panel_name]["log_channel"] = channel.id
            await ctx.tick()
        await self.initialize(ctx.guild)

    @tickets.command()
    async def addmessage(self, ctx: commands.Context, panel_name: str):
        """
        Add a message embed to be sent when a ticket is opened

        You can include any of these in the embed to be replaced by their value when the message is sent
        `{username}` - Person's Discord username
        `{mention}` - This will mention the user
        `{id}` - This is the ID of the user that created the ticket

        The bot will walk you through a few steps to set up the embed
        """
        panel_name = panel_name.lower()
        panels = await self.config.guild(ctx.guild).panels()
        if panel_name not in panels:
            return await ctx.send(_("Panel does not exist!"))
        foot = _("type 'cancel' to cancel the setup")
        color = ctx.author.color
        # TITLE
        em = Embed(description=_("Would you like this ticket embed to have a title?"), color=color)
        msg = await ctx.send(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your desired title below"))
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            title = await wait_reply(ctx, 300)
            if title and title.lower().strip() == "cancel":
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            title = None
        # BODY
        em = Embed(description=_("Type your desired ticket message below"))
        em.set_footer(text=foot)
        await msg.edit(embed=em)
        desc = await wait_reply(ctx, 600)
        if desc and desc.lower().strip() == _("cancel"):
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        if desc is None:
            em = Embed(description=_("Ticket message addition cancelled"))
            return await msg.edit(embed=em)
        # FOOTER
        em = Embed(description=_("Would you like this ticket embed to have a footer?"))
        em.set_footer(text=foot)
        await msg.edit(embed=em)
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if yes:
            em = Embed(description=_("Type your footer"))
            em.set_footer(text=foot)
            await msg.edit(embed=em)
            footer = await wait_reply(ctx, 300)
            if footer and footer.lower().strip() == _("cancel"):
                em = Embed(description=_("Ticket message addition cancelled"))
                return await msg.edit(embed=em)
        else:
            footer = None

        embed = {"title": title, "desc": desc, "footer": footer}

        async with self.config.guild(ctx.guild).panels() as panels:
            panels[panel_name]["ticket_messages"].append(embed)
            await ctx.tick()
            em = Embed(description=_("Your ticket message has been added!"))
            await msg.edit(embed=em)
        await self.initialize(ctx.guild)

    @tickets.command()
    async def viewmessages(self, ctx: commands.Context, panel_name: str):
        """View/Delete a ticket message for a support ticket panel"""
        panel_name = panel_name.lower()
        panels = await self.config.guild(ctx.guild).panels()
        if panel_name not in panels:
            return await ctx.send(_("Panel does not exist!"))
        messages = panels[panel_name]["ticket_messages"]
        if not messages:
            return await ctx.send(_("This panel does not have any messages added!"))
        embeds = []
        for i, msg in enumerate(messages):
            desc = _("**Title**\n") + box(msg["title"]) + "\n"
            desc += _("**Description**\n") + box(msg["desc"]) + "\n"
            desc += _("**Footer**\n") + box(msg["footer"])
            em = Embed(
                title=_("Ticket Messages for: ") + panel_name,
                description=desc,
                color=ctx.author.color
            )
            em.set_footer(text=_("Page") + f" {i + 1}/{len(messages)}")
            embeds.append(em)

        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel_message
        await menu(ctx, embeds, controls)

    async def delete_panel_message(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title.replace(_("Ticket Messages for: "), "")
        async with self.config.guild(interaction.guild).panels() as panels:
            del panels[panel_name]["ticket_messages"][index]
            em = Embed(description=_("Ticket message has been deleted from ") + f"{panel_name}!")
            await interaction.response.send_message(embed=em, ephemeral=True)
            del instance.view.pages[index]
            instance.view.page += 1
            instance.view.page %= len(instance.view.pages)
            for i, embed in enumerate(instance.view.pages):
                embed.set_footer(text=f"{i + 1}/{len(instance.view.pages)}")
            await instance.view.handle_page(interaction.response.edit_message)

    @tickets.command()
    async def panels(self, ctx: commands.Context):
        """View/Delete currently configured support ticket panels"""
        panels = await self.config.guild(ctx.guild).panels()
        if not panels:
            return await ctx.send(
                _("There are no panels available!\nUse ") + f"`{ctx.prefix}sset addpanel` " + _("to create one.")
            )
        embeds = []
        pages = len(panels.keys())
        page = 1
        for panel_name, info in panels.items():
            cat = self.bot.get_channel(info["category_id"]) if info["category_id"] else "None"
            channel = self.bot.get_channel(info["channel_id"]) if info["channel_id"] else "None"
            logchannel = self.bot.get_channel(info["log_channel"]) if info["log_channel"] else "None"

            desc = _("`Category:       `") + f"{cat}\n"
            desc += _("`Channel:        `") + f"{channel}\n"
            desc += _("`MessageID:      `") + f"{info['message_id']}\n"
            desc += _("`ButtonText:     `") + f"{info['button_text']}\n"
            desc += _("`ButtonColor:    `") + f"{info['button_color']}\n"
            desc += _("`ButtonEmoji:    `") + f"{info['button_emoji']}\n"
            desc += _("`TicketNum:      `") + f"{info['ticket_num']}\n"
            desc += _("`TicketMessages: `") + f"{len(info['ticket_messages'])}\n"
            desc += _("`TicketName:     `") + f"{info['ticket_name']}\n"
            desc += _("`LogChannel:     `") + f"{logchannel}"

            em = Embed(
                title=_("Panel: ") + panel_name,
                description=desc,
                color=ctx.author.color
            )
            em.set_footer(text=_("Page ") + f"{page}/{pages}")
            page += 1
            embeds.append(em)
        controls = SMALL_CONTROLS.copy()
        controls["\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"] = self.delete_panel
        await menu(ctx, embeds, controls)

    async def delete_panel(self, instance, interaction: discord.Interaction):
        index = instance.view.page
        panel_name = instance.view.pages[index].title.replace("Panel: ", "")
        async with self.config.guild(interaction.guild).panels() as panels:
            del panels[panel_name]
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
        conf = await self.config.guild(ctx.guild).all()
        inactive = conf["inactive"]
        plural = _("hours")
        singular = _("hour")
        no_resp = f"{inactive} {singular if inactive == 1 else plural}"
        if not inactive:
            no_resp = _("Disabled")
        msg = _("`Max Tickets:      `") + f"{conf['max_tickets']}\n"
        msg += _("`DM Alerts:        `") + f"{conf['dm']}\n"
        msg += _("`Users can Rename: `") + f"{conf['user_can_rename']}\n"
        msg += _("`Users can Close:  `") + f"{conf['user_can_close']}\n"
        msg += _("`Users can Manage: `") + f"{conf['user_can_manage']}\n"
        msg += _("`Save Transcripts: `") + f"{conf['transcript']}\n"
        msg += _("`Auto Close:       `") + (_("On") if inactive else _("Off")) + "\n"
        msg += _("`NoResponseDelete: `") + no_resp

        support = conf["support_roles"]
        suproles = ""
        if support:
            for role_id in support:
                role = ctx.guild.get_role(role_id)
                if role:
                    suproles += f"{role.mention}\n"
        blacklist = conf["blacklist"]
        busers = ""
        if blacklist:
            for user_id in blacklist:
                user = ctx.guild.get_member(user_id)
                if user:
                    busers += f"{user.name}-{user.id}\n"
                else:
                    busers += _("LeftGuild") + f"-{user_id}\n"
        embed = discord.Embed(
            title=_("Tickets Core Settings"),
            description=msg,
            color=discord.Color.random()
        )
        if suproles:
            embed.add_field(
                name=_("Support Roles"),
                value=suproles,
                inline=False
            )
        if busers:
            embed.add_field(
                name=_("Blacklisted Users"),
                value=busers,
                inline=False
            )
        await ctx.send(embed=embed)

    @tickets.command()
    async def maxtickets(self, ctx: commands.Context, amount: int):
        """Set the max tickets a user can have open at one time of any kind"""
        if not amount:
            return await ctx.send(_("Max ticket amount must be greater than 0!"))
        await self.config.guild(ctx.guild).max_tickets.set(amount)
        await ctx.tick()

    @tickets.command(name="supportrole")
    async def set_support_role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove ticket support roles (one at a time)

        To remove a role, simply run this command with it again to remove it
        """
        async with self.config.guild(ctx.guild).support_roles() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(role.name + _(" has been removed from support roles"))
            else:
                roles.append(role.id)
                await ctx.send(role.name + _(" has been added to support roles"))

    @tickets.command(name="blacklist")
    async def set_user_blacklist(self, ctx: commands.Context, *, user: discord.Member):
        """
        Add/Remove users from the blacklist

        Users in the blacklist will not be able to create a ticket
        """
        async with self.config.guild(ctx.guild).blacklist() as bl:
            if user.id in bl:
                bl.remove(user.id)
                await ctx.send(user.name + _("has been removed from the blacklist"))
            else:
                bl.append(user.id)
                await ctx.send(user.name + _("has been added to the blacklist"))

    @tickets.command(name="noresponse")
    async def no_response_close(self, ctx: commands.Context, hours: int):
        """
        Auto-close ticket if opener doesn't say anything after X hours of opening

        Set to 0 to disable this
        """
        await self.config.guild(ctx.guild).inactive.set(hours)
        await ctx.tick()

    @tickets.command(name="cleanup")
    async def cleanup_tickets(self, ctx: commands.Context):
        """Cleanup tickets that no longer exist"""
        opened = await self.config.guild(ctx.guild).opened()
        if not opened:
            return await ctx.send(_("No old tickets to clean."))
        cleaned = 0
        async with self.config.guild(ctx.guild).opened() as op:
            for uid, tickets in opened.items():
                if not ctx.guild.get_member(int(uid)):
                    cleaned += len(tickets.keys())
                    del op[uid]
                    continue
                for channel_id, t_info in opened[uid].items():
                    if not ctx.guild.get_channel(int(channel_id)):
                        cleaned += 1
                        del op[uid][channel_id]
        if cleaned:
            txt = _("Pruned `") + str(cleaned) + _("` invalid ") + f"{_('ticket') if cleaned == 1 else _('tickets')}."
            await ctx.send(txt)
        else:
            await ctx.send(_("There were no tickets to prune."))

    # TOGGLES --------------------------------------------------------------------------------
    @tickets.command(name="dm")
    async def toggle_dms(self, ctx: commands.Context):
        """(Toggle) The bot sending DM's for ticket alerts"""
        toggle = await self.config.guild(ctx.guild).dm()
        if toggle:
            await self.config.guild(ctx.guild).dm.set(False)
            await ctx.send(_("DM alerts have been **Disabled**"))
        else:
            await self.config.guild(ctx.guild).dm.set(True)
            await ctx.send(_("DM alerts have been **Enabled**"))

    @tickets.command(name="selfrename")
    async def toggle_rename(self, ctx: commands.Context):
        """(Toggle) If users can rename their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_rename()
        if toggle:
            await self.config.guild(ctx.guild).user_can_rename.set(False)
            await ctx.send(_("User can no longer rename their support channel"))
        else:
            await self.config.guild(ctx.guild).user_can_rename.set(True)
            await ctx.send(_("User can now rename their support channel"))

    @tickets.command(name="selfclose")
    async def toggle_selfclose(self, ctx: commands.Context):
        """(Toggle) If users can close their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_close()
        if toggle:
            await self.config.guild(ctx.guild).user_can_close.set(False)
            await ctx.send(_("User can no longer close their support ticket channel"))
        else:
            await self.config.guild(ctx.guild).user_can_close.set(True)
            await ctx.send(_("User can now close their support ticket channel"))

    @tickets.command(name="selfmanage")
    async def toggle_selfmanage(self, ctx: commands.Context):
        """
        (Toggle) If users can manage their own tickets

        Users will be able to add/remove others to their support ticket
        """
        toggle = await self.config.guild(ctx.guild).user_can_manage()
        if toggle:
            await self.config.guild(ctx.guild).user_can_manage.set(False)
            await ctx.send(_("User can no longer manage their support ticket channel"))
        else:
            await self.config.guild(ctx.guild).user_can_manage.set(True)
            await ctx.send(_("User can now manage their support ticket channel"))

    @tickets.command(name="transcript")
    async def toggle_transcript(self, ctx: commands.Context):
        """
        (Toggle) Ticket transcripts

        Closed tickets will have their transcripts uploaded to the log channel
        """
        toggle = await self.config.guild(ctx.guild).transcript()
        if toggle:
            await self.config.guild(ctx.guild).transcript.set(False)
            await ctx.send(_("Transcripts of closed tickets will no longer be saved"))
        else:
            await self.config.guild(ctx.guild).transcript.set(True)
            await ctx.send(_("Transcripts of closed tickets will now be saved"))
