import asyncio
import datetime
import logging

import discord
from discord.ext import tasks
from dislash import ActionRow, Button, ButtonStyle, InteractionClient, ResponseType
from dislash.interactions.message_interaction import MessageInteraction
from redbot.core import Config, commands

from .base import BaseCommands
from .commands import SupportCommands

log = logging.getLogger("red.vrt.support")


# Shoutout to Neuro Assassin#4779 for having a nice ass support ticket cog I could get ideas from


class Support(BaseCommands, SupportCommands, commands.Cog):
    """
    Support ticket system with buttons/logging
    """

    __author__ = "Vertyco"
    __version__ = "1.2.6"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_guild = {
            # Ticket category
            "category": None,
            # Support button message data
            "message_id": None,
            "channel_id": None,
            "content": None,
            # Settings
            "enabled": False,
            "log": None,
            "support": [],
            "blacklist": [],
            "max_tickets": 1,
            "bcolor": "red",
            "embeds": False,
            "inactive": 0,  # Auto close tickets with X hours of inactivity
            # Ticket data
            "opened": {},
            "num": 1,
            # Content
            "button_content": "Click To Open A Ticket!",
            "emoji": None,
            "message": "{default}",
            "ticket_name": "{default}",
            # Toggles
            "dm": False,
            "user_can_rename": False,
            "user_can_close": True,
            "user_can_manage": False,
            "transcript": False,
            "auto_close": False,
        }
        self.config.register_guild(**default_guild)
        self.check_listener.start()
        self.auto_close.start()
        # Dislash monkeypatch
        InteractionClient(bot, sync_commands=False)

        self.valid = []  # Valid tickets that owner has typed in(so don't auto-close)

    def cog_unload(self):
        self.check_listener.cancel()
        self.auto_close.cancel()
        # Cancel all guild tasks
        # Hope nobody else is using asyncio task names!
        # Tasks are named guild.id for each guild so if you are plz DM me and ill make a diff naming scheme
        for task in asyncio.all_tasks():
            if task.get_name().isdigit():
                task.cancel()

    # Just checks if guild has been added to the listener
    @tasks.loop(seconds=10)
    async def check_listener(self):
        await self.add_components()

    @check_listener.before_loop
    async def before_listener(self):
        await self.bot.wait_until_red_ready()
        await self.cleanup()

    # Add button components to support message and determine if a listener task needs to be created
    async def add_components(self):
        for guild in self.bot.guilds:
            conf = await self.config.guild(guild).all()
            if not conf["category"]:
                continue
            if not conf["message_id"]:
                continue
            if not conf["channel_id"]:
                continue
            channel = self.bot.get_channel(conf["channel_id"])
            if not channel:
                continue
            message = await channel.fetch_message(conf["message_id"])
            if not message:
                continue
            bcolor = conf["bcolor"]
            if bcolor == "red":
                style = ButtonStyle.red
            elif bcolor == "blue":
                style = ButtonStyle.blurple
            elif bcolor == "green":
                style = ButtonStyle.green
            else:
                style = ButtonStyle.grey

            # Check if listener task is running for guild
            guild_id = str(guild.id)
            running = [task.get_name() for task in asyncio.all_tasks()]
            if guild_id not in running:
                button_content = conf["button_content"]
                emoji = conf["emoji"]
                if emoji:
                    button = ActionRow(
                        Button(
                            style=style,
                            label=button_content,
                            custom_id=f"{guild.id}",
                            emoji=emoji,
                        )
                    )
                else:
                    button = ActionRow(
                        Button(
                            style=style, label=button_content, custom_id=f"{guild.id}"
                        )
                    )
                try:
                    await message.edit(components=[button])
                except Exception as e:
                    if "Invalid emoji" in str(e):
                        log.warning(f"Button emoji in {guild.name} is bad")
                        button = ActionRow(
                            Button(
                                style=style,
                                label=button_content,
                                custom_id=f"{guild.id}",
                            )
                        )
                        await message.edit(components=[button])
                    else:
                        button = ActionRow(
                            Button(
                                style=style,
                                label="Click to open a ticket",
                                custom_id=f"{guild.id}",
                            )
                        )
                        await message.edit(components=[button])
                        log.warning(f"Error applying button: {e}")
                if str(guild.id) not in [
                    task.get_name() for task in asyncio.all_tasks()
                ]:
                    asyncio.create_task(self.listen(message), name=str(guild.id))

    # Clean up any ticket data that comes from a deleted channel or unknown user
    async def cleanup(self):
        for guild in self.bot.guilds:
            t = await self.config.guild(guild).opened()
            current_tickets = {}
            count = 0
            for uid, tickets in t.items():
                if not guild.get_member(int(uid)):
                    count += 1
                    continue
                new_tickets = {}
                for cid, data in tickets.items():
                    if not guild.get_channel(int(cid)):
                        count += 1
                        continue
                    else:
                        new_tickets[cid] = data
                if new_tickets:
                    current_tickets[uid] = new_tickets
            await self.config.guild(guild).opened.set(current_tickets)
            if count:
                log.info(f"{count} tickets pruned from {guild.name}")

    # Listen for a button click on a message
    async def listen(self, message: discord.Message):
        if isinstance(
            message, str
        ):  # If for some reason message is not a discord.Message object
            #  Edit: Pretty sure i found the issue
            log.warning(f"Message isn't an object for some reason: {message}")
            return await self.add_components()
        inter = await message.wait_for_button_click()
        try:
            await inter.reply(type=ResponseType.DeferredUpdateMessage)
        except Exception as e:
            log.warning(f"Listener Error: {e}")
        return await self.create_ticket(inter, message)

    # Create a ticket channel for the user
    async def create_ticket(self, inter: MessageInteraction, message: discord.Message):
        button_guild = inter.clicked_button.id
        guild = self.bot.get_guild(int(button_guild))
        if not guild:
            if str(guild.id) not in [task.get_name() for task in asyncio.all_tasks()]:
                asyncio.create_task(self.listen(message), name=str(guild.id))
            return
        user = inter.author
        pfp = user.avatar_url
        conf = await self.config.guild(guild).all()
        if str(inter.author.id) in conf["opened"]:
            tickets = len(conf["opened"][str(inter.author.id)].keys())
            if tickets >= conf["max_tickets"]:
                if str(guild.id) not in [
                    task.get_name() for task in asyncio.all_tasks()
                ]:
                    asyncio.create_task(self.listen(message), name=str(guild.id))
                return
        category = self.bot.get_channel(conf["category"])
        if not category:
            asyncio.create_task(
                inter.reply("The ticket category hasn't been set yet!", ephemeral=True)
            )
            if str(guild.id) not in [task.get_name() for task in asyncio.all_tasks()]:
                asyncio.create_task(self.listen(message), name=str(guild.id))
            return
        can_read = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True
        )
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_channels=True,
            manage_permissions=True,
        )
        support = [
            guild.get_role(role_id)
            for role_id in conf["support"]
            if guild.get_role(role_id)
        ]
        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read,
        }
        for role in support:
            overwrite[role] = can_read
        num = conf["num"]

        now = datetime.datetime.now()
        name_fmt = conf["ticket_name"]
        if name_fmt == "{default}":
            channel_name = f"{user.name}"
        else:
            params = {
                "num": str(num),
                "user": user.name,
                "id": str(user.id),
                "shortdate": now.strftime("%m-%d"),
                "longdate": now.strftime("%m-%d-%Y"),
                "time": now.strftime("%I-%M-%p"),
            }
            channel_name = name_fmt.format(**params)
        channel = await category.create_text_channel(channel_name, overwrites=overwrite)
        # Ticket message setup
        embeds = conf["embeds"]
        color = user.color
        if conf["message"] == "{default}":
            if conf["user_can_close"]:
                text = (
                    "Welcome to your ticket channel\nTo close this, "
                    "You or an Administrator may run `[p]sclose`."
                )
                if embeds:
                    msg = await channel.send(
                        user.mention, embed=discord.Embed(description=text, color=color)
                    )
                else:
                    msg = await channel.send(f"{user.mention}, {text}")
            else:
                text = "Welcome to your ticket channel"
                if embeds:
                    msg = await channel.send(
                        user.mention, embed=discord.Embed(description=text, color=color)
                    )
                else:
                    msg = await channel.send(f"{user.mention}, {text}")
        else:
            mentions = discord.AllowedMentions(users=True, roles=True)
            try:
                params = {
                    "username": user.name,
                    "mention": user.mention,
                    "id": str(user.id),
                }
                tmessage = conf["message"].format(**params)
                if embeds:
                    if "mention" in conf["message"]:
                        msg = await channel.send(
                            user.mention,
                            embed=discord.Embed(description=tmessage, color=color),
                        )
                    else:
                        msg = await channel.send(
                            embed=discord.Embed(description=tmessage, color=color)
                        )
                else:
                    msg = await channel.send(tmessage, allowed_mentions=mentions)
            except Exception as e:
                log.warning(f"An error occurred while sending a ticket message: {e}")
                # Revert to default message
                if conf["user_can_close"]:
                    text = (
                        "Welcome to your ticket channel\nTo close this, "
                        "You or an Administrator may run `[p]sclose`."
                    )
                    if embeds:
                        msg = await channel.send(
                            user.mention,
                            embed=discord.Embed(description=text, color=color),
                        )
                    else:
                        msg = await channel.send(
                            f"{user.mention}, {text}", allowed_mentions=mentions
                        )
                else:
                    text = "Welcome to your ticket channel"
                    if embeds:
                        msg = await channel.send(
                            user.mention,
                            embed=discord.Embed(description=text, color=color),
                        )
                    else:
                        msg = await channel.send(
                            f"{user.mention}, {text}", allowed_mentions=mentions
                        )

        async with self.config.guild(guild).all() as settings:
            settings["num"] += 1
            opened = settings["opened"]
            if str(user.id) not in opened:
                opened[str(user.id)] = {}
            opened[str(user.id)][str(channel.id)] = {
                "opened": now.isoformat(),
                "pfp": str(pfp),
                "logmsg": None,
            }
            if conf["log"]:
                log_channel = self.bot.get_channel(conf["log"])
                if log_channel:
                    embed = discord.Embed(
                        title="Ticket Opened",
                        description=f"Ticket created by **{user.name}-{user.id}** has been opened\n"
                        f"To view this ticket, **[Click Here]({msg.jump_url})**",
                        color=discord.Color.red(),
                    )
                    embed.set_thumbnail(url=pfp)
                    log_msg = await log_channel.send(embed=embed)
                    opened[str(user.id)][str(channel.id)]["logmsg"] = str(log_msg.id)
        if str(guild.id) not in [task.get_name() for task in asyncio.all_tasks()]:
            asyncio.create_task(self.listen(message), name=str(guild.id))
        return

    @tasks.loop(minutes=20)
    async def auto_close(self):
        actasks = []
        for guild in self.bot.guilds:
            conf = await self.config.guild(guild).all()
            inactive = conf["inactive"]
            if not inactive:
                continue
            opened = conf["opened"]
            if not opened:
                continue
            for uid, tickets in opened.items():
                member = guild.get_member(int(uid))
                if not member:
                    continue
                for channel_id, data in tickets.items():
                    if channel_id in self.valid:
                        continue
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        continue
                    now = datetime.datetime.now()
                    opened_on = datetime.datetime.fromisoformat(data["opened"])
                    hastyped = await self.ticket_owner_hastyped(channel, member)
                    if hastyped:
                        if channel_id not in self.valid:
                            self.valid.append(channel_id)
                        continue
                    td = (now - opened_on).total_seconds() / 3600
                    if td < inactive:
                        continue
                    time = "hours" if inactive != 1 else "hour"
                    actasks.append(
                        self.close_ticket(
                            member,
                            channel,
                            conf,
                            f"(Auto-Close) Opened ticket with no response for {inactive} {time}",
                            self.bot.user.name,
                        )
                    )
                    log.info(
                        f"Ticket opened by {member.name} has been auto-closed.\n"
                        f"Has typed: {hastyped}\n"
                        f"Hours elapsed: {td}"
                    )
        if tasks:
            await asyncio.gather(*actasks)

    @auto_close.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(30)

    # Will automatically close/cleanup any tickets if a member leaves that has an open ticket
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        conf = await self.config.guild(member.guild).all()
        if not conf["auto_close"]:
            return
        opened = conf["opened"]
        if str(member.id) not in opened:
            return
        tickets = opened[str(member.id)]
        if not tickets:
            return
        actasks = []
        for cid, ticket in tickets.items():
            chan = self.bot.get_channel(int(cid))
            if not chan:
                continue
            actasks.append(
                self.close_ticket(
                    member,
                    chan,
                    conf,
                    "User left guild(Auto-Close)",
                    self.bot.user.name,
                )
            )
        if actasks:
            await asyncio.gather(*actasks)
