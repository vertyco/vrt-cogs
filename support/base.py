import datetime
import logging
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.mod import is_admin_or_superior

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.support.base")
_ = Translator("Support", __file__)


class BaseCommands(commands.Cog):
    @commands.command(name="add")
    async def add_user_to_ticket(self, ctx: commands.Context, *, user: discord.Member):
        """Add a user to your ticket"""
        guild = ctx.guild
        chan = ctx.channel
        conf = await self.config.guild(guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(chan.id))
        if not owner_id:
            return await ctx.send(
                "This is not a ticket channel, or it has been removed from config"
            )
        # If a mod tries
        can_add = False
        for role in ctx.author.roles:
            if role.id in conf["support"]:
                can_add = True
        if ctx.author.id == guild.owner_id:
            can_add = True
        if await is_admin_or_superior(self.bot, ctx.author):
            can_add = True
        if owner_id == str(ctx.author.id) and conf["user_can_manage"]:
            can_add = True
        if not can_add:
            return await ctx.send(
                "You do not have permissions to add users to this ticket"
            )
        await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
        await ctx.send(f"**{user.name}** has been added to this ticket!")

    @commands.command(name="srename")
    async def rename_ticket(self, ctx: commands.Context, *, new_name: str):
        """Rename your ticket channel"""
        guild = ctx.guild
        chan = ctx.channel
        conf = await self.config.guild(guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(chan.id))
        if not owner_id:
            return await ctx.send(
                "This is not a ticket channel, or it has been removed from config"
            )
        can_rename = False
        for role in ctx.author.roles:
            if role.id in conf["support"]:
                can_rename = True
        if ctx.author.id == guild.owner_id:
            can_rename = True
        if await is_admin_or_superior(self.bot, ctx.author):
            can_rename = True
        if owner_id == str(ctx.author.id) and conf["user_can_rename"]:
            can_rename = True
        if not can_rename:
            return await ctx.send("You do not have permissions to rename this ticket")
        await ctx.channel.edit(name=new_name)
        await ctx.send("Ticket has been renamed")

    @commands.command(name="sclose")
    async def close_a_ticket(self, ctx: commands.Context, *, reason: str = None):
        """Close your ticket"""
        user = ctx.author
        guild = ctx.guild
        chan = ctx.channel
        conf = await self.config.guild(guild).all()
        opened = conf["opened"]
        owner_id = self.get_ticket_owner(opened, str(chan.id))
        if not owner_id:
            return await ctx.send(
                "This is not a ticket channel, or it has been removed from config"
            )
        can_close = False
        for role in user.roles:
            if role.id in conf["support"]:
                can_close = True
        if user.id == guild.owner_id:
            can_close = True
        if await is_admin_or_superior(self.bot, user):
            can_close = True
        if owner_id == str(user.id) and conf["user_can_close"]:
            can_close = True
        if not can_close:
            return await ctx.send("You do not have permissions to close this ticket")
        else:
            owner = guild.get_member(int(owner_id))
            if not owner:
                owner = await self.bot.fetch_user(int(owner_id))
        await self.close_ticket(owner, chan, conf, reason, ctx.author.name)

    async def close_ticket(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        conf: dict,
        reason: str,
        closedby: str,
    ):
        opened = conf["opened"]
        if not opened:
            return
        uid = str(member.id)
        cid = str(channel.id)
        if uid not in opened:
            return
        if cid not in opened[uid]:
            return
        ticket = opened[uid][cid]
        pfp = ticket["pfp"]
        opened = ticket["opened"]
        opened = datetime.datetime.fromisoformat(opened)
        opened = opened.strftime("%m/%d/%y at %I:%M %p")
        closed = datetime.datetime.now().strftime("%m/%d/%y at %I:%M %p")
        embed = discord.Embed(
            title="Ticket Closed",
            description=f"Ticket created by **{member.name}-{member.id}** has been closed.\n"
            f"`Opened on: `{opened}\n"
            f"`Closed on: `{closed}\n"
            f"`Closed by: `{closedby}\n"
            f"`Reason:    `{reason}",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=pfp)
        log_chan = conf["log"]
        if log_chan:
            log_chan = self.bot.get_channel(log_chan)

        if conf["transcript"]:
            em = discord.Embed(
                description="Archiving channel...", color=discord.Color.magenta()
            )
            em.set_footer(text="This channel will be deleted once complete")
            em.set_thumbnail(url=LOADING)
            await channel.send(embed=em)
            history = await self.fetch_channel_history(channel)
            filename = f"{member.name}-{member.id}.txt"
            filename = filename.replace("/", "")
            text = ""
            for msg in history:
                if msg.author.id == self.bot.user.id:
                    continue
                if not msg:
                    continue
                if not msg.content:
                    continue
                text += f"{msg.author.name}: {msg.content}\n"
            if log_chan:
                temp = StringIO(text)
                file = discord.File(temp, filename=filename)
                await log_chan.send(embed=embed, file=file)
            if conf["dm"]:
                try:
                    temp = StringIO(text)
                    file = discord.File(temp, filename=filename)
                    await member.send(embed=embed, file=file)
                except discord.Forbidden:
                    pass
        else:
            # Send off new messages
            if log_chan:
                await log_chan.send(embed=embed)
            if conf["dm"]:
                try:
                    await member.send(embed=embed)
                except discord.Forbidden:
                    pass

        # Delete old log msg
        if log_chan:
            log_msg_id = ticket["logmsg"]
            try:
                log_msg = await log_chan.fetch_message(log_msg_id)
            except discord.NotFound:
                log.warning("Failed to get log channel message")
                log_msg = None
            if log_msg:
                try:
                    await log_msg.delete()
                except Exception as e:
                    log.warning(f"Failed to auto-delete log message: {e}")

        # Delete ticket channel
        try:
            await channel.delete()
        except Exception as e:
            log.warning(f"Failed to delete ticket channel: {e}")

        async with self.config.guild(member.guild).opened() as tickets:
            if uid not in tickets:
                return
            if cid not in tickets[uid]:
                return
            del tickets[uid][cid]

    @staticmethod
    async def fetch_channel_history(channel: discord.TextChannel):
        history = []
        async for msg in channel.history(oldest_first=True):
            history.append(msg)
        return history

    @staticmethod
    async def ticket_owner_hastyped(channel: discord.TextChannel, user: discord.Member):
        async for msg in channel.history(limit=50, oldest_first=True):
            if msg.author.id == user.id:
                return True

    @staticmethod
    def get_ticket_owner(opened: dict, channel_id: str):
        for uid, tickets in opened.items():
            for cid in tickets:
                if cid == channel_id:
                    return uid
