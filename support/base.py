import datetime
import logging
import os

import discord
from redbot.core import commands
from redbot.core.utils.mod import is_admin_or_superior

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.support.base")


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
            return await ctx.send("This is not a ticket channel, or it has been removed from config")
        if owner_id == str(ctx.author.id) and not conf["user_can_manage"] and ctx.author.id != guild.owner_id:
            return await ctx.send("You do not have permissions to add users to your ticket")
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
            return await ctx.send("You do not have permissions to add users to this ticket")
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
            return await ctx.send("This is not a ticket channel, or it has been removed from config")
        if owner_id == str(ctx.author.id) and not conf["user_can_rename"] and ctx.author.id != guild.owner_id:
            return await ctx.send("You do not have permissions to rename your ticket")
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
    async def close_ticket(self, ctx: commands.Context, *, reason: str = None):
        """Close your ticket"""
        user = ctx.author
        guild = ctx.guild
        chan = ctx.channel
        conf = await self.config.guild(guild).all()
        dm = conf["dm"]
        log_chan = conf["log"]
        opened = conf["opened"]
        transcript = conf["transcript"]
        owner_id = self.get_ticket_owner(opened, str(chan.id))
        if not owner_id:
            return await ctx.send("This is not a ticket channel, or it has been removed from config")
        if owner_id == str(user.id) and not conf["user_can_close"] and user.id != guild.owner_id:
            return await ctx.send("Users are not allowed to close their own tickets currently")
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

        ticket = opened[owner_id][str(chan.id)]
        pfp = ticket["pfp"]

        now = datetime.datetime.now()
        now = now.astimezone()

        opened = datetime.datetime.fromisoformat(ticket["opened"])
        opened = opened.astimezone()

        opened = opened.strftime('%m/%d/%y at %I:%M %p %Z')
        closed = now.strftime('%m/%d/%y at %I:%M %p %Z')

        embed = discord.Embed(
            title="Ticket Closed",
            description=f"Ticket created by **{owner.name}-{owner_id}** has been closed.\n"
                        f"`Opened on: `{opened}\n"
                        f"`Closed on: `{closed}\n"
                        f"`Closed by: `{ctx.author.name}\n"
                        f"`Reason:    `{reason}\n",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=pfp)
        async with self.config.guild(ctx.guild).opened() as tickets:
            del tickets[owner_id][str(chan.id)]
        if log_chan:
            log_chan = guild.get_channel(log_chan)
        # If transcript is enabled, gather messages before sending to log
        if transcript:
            tr = discord.Embed(
                description="Archiving channel...",
                color=discord.Color.magenta()
            )
            tr.set_footer(text="This channel will be deleted once complete")
            tr.set_thumbnail(url=LOADING)
            await ctx.send(embed=tr)
            history = await self.fetch_channel_history(chan)
            history.reverse()
            filename = f"{owner.name}-{owner_id}.txt"
            if log_chan:
                with open(filename, "w", encoding="UTF-8") as file:
                    for msg in history:
                        if msg.author.id == self.bot.user.id:
                            continue
                        if not msg:
                            continue
                        if not msg.content:
                            continue
                        try:
                            file.write(f"{msg.author.name}: {msg.content}\n")
                        except Exception as e:
                            log.warning(f"Failed to write on close: {e}")
                            continue
                with open(filename, "rb") as file:
                    await log_chan.send(embed=embed, file=discord.File(file, filename))
                try:
                    os.remove(filename)
                except Exception as e:
                    log.warning(f"Failed to delete txt file: {e}")
            try:
                await chan.delete()
            except Exception as e:
                log.warning(f"Failed to delete ticket channel: {e}")
        # Otherwise just delete the channel and send to log
        else:
            try:
                await chan.delete()
            except Exception as e:
                log.warning(f"Failed to delete ticket channel: {e}")
            if log_chan:
                await log_chan.send(embed=embed)

        # If DM is on, also send log to ticket owner
        if dm and owner:
            try:
                await owner.send(embed=embed)
            except discord.Forbidden:  # Bot is either blocked or user has left
                pass

        # Delete old log message
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
                    log.warning(f"Failed to delete log message: {e}")

    @staticmethod
    async def fetch_channel_history(channel: discord.TextChannel):
        history = []
        async for msg in channel.history():
            history.append(msg)
        return history

    @staticmethod
    def get_ticket_owner(opened: dict, channel_id: str):
        for uid, tickets in opened.items():
            for cid in tickets:
                if cid == channel_id:
                    return uid
