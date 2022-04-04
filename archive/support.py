import asyncio

import discord
import contextlib
import datetime
import dislash
import logging
from discord.ext import tasks
from redbot.core import commands, Config
from dislash import (ActionRow,
                     Button,
                     ButtonStyle,
                     ResponseType,
                     InteractionClient,
                     SelectMenu,
                     SelectOption)
from dislash.interactions.message_interaction import MessageInteraction
# from .commands import SupportCommands
# from .base import BaseCommands
log = logging.getLogger("red.vrt.support")

# BaseCommands, SupportCommands,
class Support(commands.Cog):
    """
    Support ticket system with buttons/logging
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

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
            # Ticket data
            "opened": {},
            "num": 0,
            # Content
            "button_content": "Click To Open A Ticket!",
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
        # Dislash monkeypatch
        self.inter_client = InteractionClient(bot)

    def cog_unload(self):
        self.check_listener.cancel()

    # Just checks if guild has been added to the listener
    # If all guilds are configured it wil self cancel
    @tasks.loop(seconds=10)
    async def check_listener(self):
        await self.add_components()

    @check_listener.before_loop
    async def before_listener(self):
        await self.bot.wait_until_red_ready()
        await self.cleanup()

    async def add_components(self):
        for guild in self.bot.guilds:
            conf = await self.config.guild(guild).all()
            if not conf["category"]:
                continue
            if not conf["message_id"]:
                continue
            if not conf["channel_id"]:
                continue
            message = await self.bot.get_channel(conf["channel_id"]).fetch_message(conf["message_id"])
            if not message:
                continue
            guild_id = str(guild.id)
            running = [task.get_name() for task in asyncio.all_tasks()]
            if guild_id not in running:
                button = ActionRow(
                    Button(
                        style=ButtonStyle.red,
                        label=conf["button_content"],
                        custom_id=f"{guild.id}"
                    )
                )
                await message.edit(components=[button])
                asyncio.create_task(self.listen(message), name=str(guild.id))

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

    async def listen(self, message: discord.Message):
        inter = await message.wait_for_button_click()
        try:
            await inter.reply(type=ResponseType.DeferredUpdateMessage)
        except Exception as e:
            log.warning(f"Listener Error: {e}")
        return await self.create_ticket(inter, message)

    async def create_ticket(self, inter: MessageInteraction, message: discord.Message):
        button_guild = inter.clicked_button.id
        guild = self.bot.get_guild(int(button_guild))
        if not guild:
            return await self.listen(message)
        user = inter.author
        pfp = user.avatar_url
        conf = await self.config.guild(guild).all()
        if str(inter.author.id) in conf["opened"]:
            tickets = len(conf["opened"][str(inter.author.id)].keys())
            if tickets >= conf["max_tickets"]:
                return await self.listen(message)
        category = self.bot.get_channel(conf["category"])
        if not category:
            asyncio.create_task(inter.reply("The ticket category hasn't been set yet!", ephemeral=True))
            return await self.listen(message)
        can_read = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True
        )
        support = [
            guild.get_role(role_id) for role_id in conf["support"] if guild.get_role(role_id)
        ]
        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read
        }
        for role in support:
            overwrite[role] = can_read
        num = conf["num"]

        now = datetime.datetime.now()
        name_fmt = conf["ticket_name"]
        if name_fmt == "{default}":
            channel_name = f"{user.name}"
        else:
            channel_name = (
                name_fmt
                .replace("{num}", str(num))
                .replace("{user}", user.name)
                .replace("{id}", str(user.id))
                .replace("{shortdate}", now.strftime("%m/%d"))
                .replace("{longdate}", now.strftime("%m/%d/%Y"))
                .replace("{time}", now.strftime("%I:%M %p"))
            )
        channel = await category.create_text_channel(channel_name, overwrites=overwrite)
        if conf["message"] == "{default}":
            if conf["user_can_close"]:
                msg = await channel.send(
                    f"{user.mention} welcome to your ticket channel\nTo close this, "
                    f"Administrators or you may run `[p]sclose`."
                )
            else:
                msg = await channel.send(
                    f"{user.mention} welcome to your ticket channel"
                )
        else:
            try:
                message = (
                    conf["message"]
                    .replace("{username}", user.name)
                    .replace("{mention}", user.mention)
                    .replace("{id}", user.id)
                )
                msg = await channel.send(message, allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            except Exception as e:
                log.warning(f"An error occured while sending a ticket message: {e}")
                if conf["user_can_close"]:
                    msg = await channel.send(
                        f"{user.mention} welcome to your ticket channel\nTo close this, "
                        f"Administrators or you may run `[p]sclose`."
                    )
                else:
                    msg = await channel.send(
                        f"{user.mention} welcome to your ticket channel"
                    )

        async with self.config.guild(guild).all() as settings:
            settings["num"] += 1
            opened = settings["opened"]
            if str(user.id) not in opened:
                opened[str(user.id)] = {}
            opened[str(user.id)][str(channel.id)] = {
                "added": [],
                "opened": now.isoformat(),
                "pfp": str(pfp),
                "logmsg": None
            }
            if conf["log"]:
                log_channel = self.bot.get_channel(conf["log"])
                if log_channel:
                    embed = discord.Embed(
                        title="Ticket Opened",
                        description=f"Ticket created by **{user.name}-{user.id}** has been opened\n"
                                    f"To view this ticket, **[Click Here]({msg.jump_url})**",
                        color=discord.Color.red()
                    )
                    log_msg = await log_channel.send(embed=embed)
                    opened[str(user.id)][str(channel.id)]["logmsg"] = str(log_msg.id)
        return await self.listen(message)
