import asyncio
from typing import Union

import discord
from dislash import ActionRow, Button, ButtonStyle
from redbot.core import commands
from redbot.core.utils.chat_formatting import box


class SupportCommands(commands.Cog):
    @commands.group(name="supportset", aliases=["sset"])
    @commands.guild_only()
    @commands.admin()
    async def support(self, ctx: commands.Context):
        """Base support settings"""
        pass

    # Check running button tasks and update guild task if exists
    async def refresh_tasks(self, guild_id: str):
        for task in asyncio.all_tasks():
            if guild_id == task.get_name():
                task.cancel()
                await self.add_components()

    @support.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View support settings"""
        conf = await self.config.guild(ctx.guild).all()
        category = self.bot.get_channel(conf["category"])
        if not category:
            category = conf["category"]
        button_channel = self.bot.get_channel(conf["channel_id"])
        if button_channel:
            button_channel = button_channel.mention
        else:
            button_channel = conf["channel_id"]
        inactive = conf["inactive"]
        no_resp = f"{inactive} {'hours' if inactive != 1 else 'hour'}"
        if not inactive:
            no_resp = "Disabled"
        msg = (
            f"`Ticket Category:  `{category}\n"
            f"`Button MessageID: `{conf['message_id']}\n"
            f"`Button Channel:   `{button_channel}\n"
            f"`Max Tickets:      `{conf['max_tickets']}\n"
            f"`Button Content:   `{conf['button_content']}\n"
            f"`Button Emoji:     `{conf['emoji']}\n"
            f"`DM Alerts:        `{conf['dm']}\n"
            f"`Users can Rename: `{conf['user_can_rename']}\n"
            f"`Users can Close:  `{conf['user_can_close']}\n"
            f"`Users can Manage: `{conf['user_can_manage']}\n"
            f"`Save Transcripts: `{conf['transcript']}\n"
            f"`Auto Close:       `{conf['auto_close']}\n"
            f"`Ticket Name:      `{conf['ticket_name']}\n"
            f"`NoResponseDelete: `{no_resp}\n"
        )
        log = conf["log"]
        if log:
            lchannel = ctx.guild.get_channel(log)
            if lchannel:
                msg += f"`Log Channel:      `{lchannel.mention}\n"
            else:
                msg += f"`Log Channel:      `{log}\n"
        support = conf["support"]
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
                    busers += f"LeftGuild-{user_id}\n"
        embed = discord.Embed(
            title="Support Settings", description=msg, color=discord.Color.random()
        )
        if suproles:
            embed.add_field(name="Support Roles", value=suproles, inline=False)
        if busers:
            embed.add_field(name="Blacklisted Users", value=busers, inline=False)
        if conf["message"] != "{default}":
            embed.add_field(
                name="Ticket Message", value=box(conf["message"]), inline=False
            )
        await ctx.send(embed=embed)

    @support.command(name="category")
    async def category(self, ctx: commands.Context, category: discord.CategoryChannel):
        """Set the category ticket channels will be created in"""
        if not category.permissions_for(ctx.guild.me).manage_channels:
            return await ctx.send(
                "I do not have 'Manage Channels' permissions in that category"
            )
        await self.config.guild(ctx.guild).category.set(category.id)
        await ctx.send(f"Tickets will now be created in the {category.name} category")

    @support.command(name="supportmessage")
    async def set_support_button_message(
        self, ctx: commands.Context, message_id: discord.Message
    ):
        """
        Set the support ticket message

        The support button will be added to this message
        """
        if not message_id.channel.permissions_for(ctx.guild.me).view_channel:
            return await ctx.send("I cant see that channel")
        if not message_id.channel.permissions_for(ctx.guild.me).read_messages:
            return await ctx.send("I cant read messages in that channel")
        if not message_id.channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send("I cant read message history in that channel")
        if message_id.author.id != self.bot.user.id:
            return await ctx.send("I can only add buttons to my own messages!")
        await self.config.guild(ctx.guild).message_id.set(message_id.id)
        await self.config.guild(ctx.guild).channel_id.set(message_id.channel.id)
        await ctx.send("Support ticket message has been set!")
        await self.refresh_tasks(str(ctx.guild.id))

    @support.command(name="ticketmessage")
    async def set_support_ticket_message(self, ctx: commands.Context, *, message: str):
        """
        Set the message sent when a ticket is opened

        You can include any of these in the message to be replaced by their value when the message is sent
        `{username}` - Person's Discord username
        `{mention}` - This will mention the user
        `{id}` - This is the ID of the user that created the ticket

        You can set this to {default} to restore original settings
        """
        if len(message) > 1024:
            return await ctx.send(
                "Message length is too long! Must be less than 1024 chars"
            )
        await self.config.guild(ctx.guild).message.set(message)
        if message.lower() == "default":
            await ctx.send("Message has been reset to default")
        else:
            await ctx.send("Message has been set!")

    @support.command(name="supportrole")
    async def set_support_role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove ticket support roles (one at a time)

        To remove a role, simply run this command with it again to remove it
        """
        async with self.config.guild(ctx.guild).support() as roles:
            if role.id in roles:
                roles.remove(role.id)
                await ctx.send(f"{role.name} has been removed from support roles")
            else:
                roles.append(role.id)
                await ctx.send(f"{role.name} has been added to support roles")

    @support.command(name="blacklist")
    async def set_user_blacklist(self, ctx: commands.Context, *, user: discord.Member):
        """
        Add/Remove users from the blacklist

        Users in the blacklist will not be able to create a ticket
        """
        async with self.config.guild(ctx.guild).blacklist() as bl:
            if user.id in bl:
                bl.remove(user.id)
                await ctx.send(f"{user.name} has been removed from the blacklist")
            else:
                bl.append(user.id)
                await ctx.send(f"{user.name} has been added to the blacklist")

    @support.command(name="maxtickets")
    async def set_max_tickets(self, ctx: commands.Context, max_tickets: int):
        """Set the max amount of tickets a user can have opened"""
        await self.config.guild(ctx.guild).max_tickets.set(max_tickets)
        await ctx.tick()

    @support.command(name="logchannel")
    async def set_log_channel(
        self, ctx: commands.Context, *, log_channel: discord.TextChannel
    ):
        """Set the log channel"""
        await self.config.guild(ctx.guild).log.set(log_channel.id)
        await ctx.tick()

    @support.command(name="buttoncontent")
    async def set_button_content(self, ctx: commands.Context, *, button_content: str):
        """Set what you want the support button to say"""
        if len(button_content) <= 80:
            await self.config.guild(ctx.guild).button_content.set(button_content)
            await ctx.tick()
            await self.refresh_tasks(str(ctx.guild.id))
        else:
            await ctx.send(
                "Button content is too long! Must be less than 80 characters"
            )

    @support.command(name="buttoncolor")
    async def set_button_color(self, ctx: commands.Context, button_color: str):
        """Set button color(red/blue/green/grey only)"""
        c = button_color.lower()
        valid = ["red", "blue", "green", "grey", "gray"]
        if c not in valid:
            return await ctx.send(
                "That is not a valid color, must be red, blue, green, or grey"
            )
        await self.config.guild(ctx.guild).bcolor.set(c)
        await ctx.tick()
        await self.refresh_tasks(str(ctx.guild.id))

    @support.command(name="buttonemoji")
    async def set_button_emoji(
        self,
        ctx: commands.Context,
        emoji: Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """
        Set a button emoji

        Currently does NOT support unicode emojis so if using a mobile device, use discord emoji panel
        """
        conf = await self.config.guild(ctx.guild).all()
        bcolor = conf["bcolor"]
        if bcolor == "red":
            style = ButtonStyle.red
        elif bcolor == "blue":
            style = ButtonStyle.blurple
        elif bcolor == "green":
            style = ButtonStyle.green
        else:
            style = ButtonStyle.grey
        button_content = conf["button_content"]
        button = ActionRow(
            Button(
                style=style,
                label=button_content,
                custom_id=f"{ctx.guild.id}",
                emoji=str(emoji),
            )
        )
        try:
            await ctx.send(
                "This is what your button now looks like!", components=[button]
            )
        except Exception as e:
            if "Invalid emoji" in str(e):
                return await ctx.send("Unable to use that emoji, try again")
            else:
                return await ctx.send(
                    f"Cant use that emoji for some reason\nError: {e}"
                )
        await self.config.guild(ctx.guild).emoji.set(str(emoji))
        await ctx.tick()
        await self.refresh_tasks(str(ctx.guild.id))

    @support.command(name="tname")
    async def set_def_ticket_name(self, ctx: commands.Context, *, default_name: str):
        """
        Set the default ticket channel name

        You can include the following in the name
        `{num}` - Ticket number
        `{user}` - user's name
        `{id}` - user's ID
        `{shortdate}` - mm-dd
        `{longdate}` - mm-dd-yyyy
        `{time}` - hh-mm AM/PM according to bot host system time

        You can set this to {default} to use the default "Ticket-Username"
        """
        await self.config.guild(ctx.guild).ticket_name.set(default_name)
        await ctx.tick()

    @support.command(name="noresponse")
    async def no_response_close(self, ctx: commands.Context, hours: int):
        """
        Auto-close ticket if opener doesn't say anything after X hours of opening

        Set to 0 to disable this
        """
        await self.config.guild(ctx.guild).inactive.set(hours)
        await ctx.tick()

    # TOGGLES --------------------------------------------------------------------------------
    @support.command(name="ticketembed")
    async def toggle_ticket_embed(self, ctx: commands.Context):
        """
        (Toggle) Ticket message as an embed

        When user opens a ticket, the formatted message will be an embed instead
        """
        toggle = await self.config.guild(ctx.guild).embeds()
        if toggle:
            await self.config.guild(ctx.guild).embeds.set(False)
            await ctx.send("Ticket message embeds have been **Disabled**")
        else:
            await self.config.guild(ctx.guild).embeds.set(True)
            await ctx.send("Ticket message embeds have been **Enabled**")

    @support.command(name="dm")
    async def toggle_dms(self, ctx: commands.Context):
        """(Toggle) The bot sending DM's for ticket alerts"""
        toggle = await self.config.guild(ctx.guild).dm()
        if toggle:
            await self.config.guild(ctx.guild).dm.set(False)
            await ctx.send("DM alerts have been **Disabled**")
        else:
            await self.config.guild(ctx.guild).dm.set(True)
            await ctx.send("DM alerts have been **Enabled**")

    @support.command(name="selfrename")
    async def toggle_rename(self, ctx: commands.Context):
        """(Toggle) If users can rename their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_rename()
        if toggle:
            await self.config.guild(ctx.guild).user_can_rename.set(False)
            await ctx.send("User can no longer rename their support channel")
        else:
            await self.config.guild(ctx.guild).user_can_rename.set(True)
            await ctx.send("User can now rename their support channel")

    @support.command(name="selfclose")
    async def toggle_selfclose(self, ctx: commands.Context):
        """(Toggle) If users can close their own tickets"""
        toggle = await self.config.guild(ctx.guild).user_can_close()
        if toggle:
            await self.config.guild(ctx.guild).user_can_close.set(False)
            await ctx.send("User can no longer close their support channel")
        else:
            await self.config.guild(ctx.guild).user_can_close.set(True)
            await ctx.send("User can now close their support channel")

    @support.command(name="selfmanage")
    async def toggle_selfmanage(self, ctx: commands.Context):
        """
        (Toggle) If users can manage their own tickets

        Users will be able to add/remove others to their support ticket
        """
        toggle = await self.config.guild(ctx.guild).user_can_manage()
        if toggle:
            await self.config.guild(ctx.guild).user_can_manage.set(False)
            await ctx.send("User can no longer manage their support channel")
        else:
            await self.config.guild(ctx.guild).user_can_manage.set(True)
            await ctx.send("User can now manage their support channel")

    @support.command(name="autoclose")
    async def toggle_autoclose(self, ctx: commands.Context):
        """(Toggle) Auto ticket close if user leaves guild"""
        toggle = await self.config.guild(ctx.guild).auto_close()
        if toggle:
            await self.config.guild(ctx.guild).auto_close.set(False)
            await ctx.send(
                "Tickets will no longer be closed if a user leaves the guild"
            )
        else:
            await self.config.guild(ctx.guild).auto_close.set(True)
            await ctx.send("Tickets will now be closed if a user leaves the guild")

    @support.command(name="transcript")
    async def toggle_transcript(self, ctx: commands.Context):
        """
        (Toggle) Ticket transcripts

        Closed tickets will have their transcripts uploaded to the log channel
        """
        toggle = await self.config.guild(ctx.guild).transcript()
        if toggle:
            await self.config.guild(ctx.guild).transcript.set(False)
            await ctx.send("Transcripts of closed tickets will no longer be saved")
        else:
            await self.config.guild(ctx.guild).transcript.set(True)
            await ctx.send("Transcripts of closed tickets will now be saved")
