import asyncio
import json
import math
import random
import string
import typing as t
import unicodedata
from contextlib import suppress
from io import StringIO
from time import perf_counter

import aiohttp
import discord
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_timedelta,
    pagify,
    text_to_file,
)

from ..abc import MixinMeta
from ..common import utils
from ..common.dpymenu import DEFAULT_CONTROLS, confirm, menu
from ..common.dynamic_menu import DynamicMenu


class MessageParser:
    def __init__(self, argument):
        if "-" not in argument:
            raise commands.BadArgument("Invalid format, must be `channelID-messageID`")
        try:
            cid, mid = [i.strip() for i in argument.split("-")]
        except ValueError:
            raise commands.BadArgument("Invalid format, must be `channelID-messageID`")
        try:
            self.channel_id = int(cid)
        except ValueError:
            raise commands.BadArgument("Channel ID must be an integer")
        try:
            self.message_id = int(mid)
        except ValueError:
            raise commands.BadArgument("Message ID must be an integer")


class Dcord(MixinMeta):
    def __init__(self):
        super().__init__()
        self.scanning_channels = set()

    @commands.command(name="nohoist")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_nicknames=True)
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(attach_files=True)
    async def no_hoist(self, ctx: commands.Context, confirm: bool):
        """Dehoist all nicknames in the server
        **Arguments**
        `confirm:` (True/False) whether to confirm the action

        Run with confirm **False** to see which nicknames would be reset.

        Users will be dehoisted IF:
        - Their nickname starts with a hoist character (e.g., `!`, `$`, `(`, `)`, `*`)
        - Their nickname starts with a number but not their username

        **Examples**
        `[p]nohoist true`
        """
        hoist_characters = (
            "!",
            "*",
            ":",
            ";",
            "<",
            ">",
            "?",
            "[",
            "]",
            "{",
            "}",
            "|",
            "~",
            "`",
            "^",
            "+",
            "-",
            "=",
            "_",
            ".",
            ",",
        )

        async def rename(member: discord.Member):
            """Reset nickname of a member"""
            tries = 0
            while tries < 3:
                try:
                    await member.edit(nick=member.name, reason="Resetting hoisted nickname")
                    return True
                except discord.Forbidden:
                    return False
                except discord.HTTPException:
                    tries += 1
                    await asyncio.sleep(1)

        buffer = StringIO()
        for member in ctx.guild.members:
            nickname = member.nick
            if not nickname:
                nickname = member.global_name
            if not nickname:
                nickname = member.display_name

            if nickname == member.name:
                continue

            is_number = nickname[0].isdigit() and nickname[0].isalnum()

            if nickname.startswith(hoist_characters):
                if not confirm:
                    buffer.write(f"- {member.name} - {member.id} - {nickname}\n")
                    continue
                if await rename(member):
                    buffer.write(f"- {member.name} - {member.id} - {nickname}\n")
                else:
                    buffer.write(f"- {member.name} - {member.id} - Unable to reset nickname!\n")

            elif is_number and not member.name.startswith(nickname[0]) and nickname[0] in ["0", "1", "2", "3"]:
                if not confirm:
                    buffer.write(f"- {member.name} - {member.id} - {nickname}\n")
                    continue
                if await rename(member):
                    buffer.write(f"- {member.name} - {member.id} - {nickname}\n")
                else:
                    buffer.write(f"- {member.name} - {member.id} - Unable to reset nickname!\n")

        if buffer.tell() == 0:
            return await ctx.send("No nicknames were hoisted or reset.")

        text = buffer.getvalue()
        if confirm:
            text = f"**Hoisted Nicknames Reset:**\n{text}"
        else:
            text = f"**Hoisted Nicknames Found:**\n{text}\n\nRun the command again with `confirm=True` to reset them."

        if len(text) > 2000:
            file = text_to_file(text)
            return await ctx.send("Too many hoisted nicknames to display, sending as a file.", file=file)
        else:
            return await ctx.send(text)

    @commands.command(aliases=["ownerof"])
    @commands.is_owner()
    async def isownerof(self, ctx: commands.Context, user_id: int):
        """Get a list of servers the specified user is the owner of"""
        owner_of = ""
        for guild in self.bot.guilds:
            if guild.owner_id == user_id:
                owner_of += f"- {guild.name} ({guild.id})\n"
        if not owner_of:
            return await ctx.send("That user is not the owner of any servers I am in.")
        for p in pagify(owner_of):
            await ctx.send(p)

    @commands.command(name="setcooldown")
    @commands.guild_only()
    @commands.admin_or_can_manage_channel()
    @commands.has_permissions(manage_channels=True)
    async def set_cooldown(
        self,
        ctx: commands.Context,
        cooldown: str,
        channel: t.Optional[
            t.Union[
                discord.TextChannel,
                discord.ForumChannel,
                discord.StageChannel,
                discord.Thread,
                discord.VoiceChannel,
            ]
        ] = None,
    ):
        """Set a cooldown for the current channel"""
        if not channel:
            channel = ctx.channel
        delta = commands.parse_timedelta(cooldown)
        if not delta:
            await channel.edit(slowmode_delay=0)
            return await ctx.send(f"Cooldown has been removed for {channel.mention}")
        seconds = int(delta.total_seconds())
        if not seconds:
            await channel.edit(slowmode_delay=0)
            return await ctx.send(f"Cooldown has been removed for {channel.mention}")
        await channel.edit(slowmode_delay=seconds)
        await ctx.send(f"Cooldown has been set to {cooldown} for {channel.mention}")

    @commands.command()
    async def closestuser(self, ctx: commands.Context, *, query: str):
        """Find the closest fuzzy match for a user"""
        query = query.lower()
        matches: t.List[t.Tuple[int, discord.User]] = []
        for user in ctx.guild.members:
            username = fuzz.ratio(query, user.name.lower())
            display_name = fuzz.ratio(query, user.display_name.lower())
            matches.append((max(username, display_name), user))
        matches = sorted(matches, key=lambda x: x[0], reverse=True)
        # Get the top 5 matches
        matches = matches[:5]
        buffer = StringIO()
        for score, user in matches:
            buffer.write(f"- {user.name} ({user.id}) - {score:.2f}% match\n")
        await ctx.send(f"Closest matches for `{query}`:\n{buffer.getvalue()}")

    @commands.command(aliases=["findguild"])
    @commands.is_owner()
    async def getguildid(self, ctx: commands.Context, query: t.Union[int, str]):
        """Find a guild by name or ID"""
        if isinstance(query, int):
            guild = self.bot.get_guild(query)
        elif query.isdigit():
            guild = self.bot.get_guild(int(query))
        else:
            guilds = {g.name.lower(): g for g in self.bot.guilds}
            guild = guilds.get(query.lower())
        if not guild:
            return await ctx.send("Could not find that guild")
        txt = (
            f"**Name:** {guild.name}\n"
            f"**ID:** {guild.id}\n"
            f"**Owner:** {guild.owner} ({guild.owner_id})\n"
            f"**Members:** {guild.member_count}\n"
            f"**Created:** <t:{int(guild.created_at.timestamp())}:F> (<t:{int(guild.created_at.timestamp())}:R>)\n"
        )
        # Humanize a list of all the bot's guild permissions
        perms = [p.replace("_", " ").title() for p, v in guild.me.guild_permissions if v]
        txt += f"**Permissions:** {', '.join(perms)}"
        await ctx.send(txt)

    @commands.command(aliases=["findchannel"])
    @commands.is_owner()
    @commands.bot_has_guild_permissions(embed_links=True)
    async def getchannel(self, ctx: commands.Context, channel_id: int):
        """Find a channel by ID"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.Forbidden, discord.NotFound):
                channel = None
        if not channel:
            return await ctx.send("Could not find that channel")
        created = f"<t:{int(channel.created_at.timestamp())}:F> (<t:{int(channel.created_at.timestamp())}:R>)"
        embed = discord.Embed(color=await self.bot.get_embed_color(ctx))
        embed.add_field(name="Name", value=channel.name)
        embed.add_field(name="ID", value=channel.id)
        embed.add_field(name="Server", value=channel.guild.name)
        embed.add_field(name="Created", value=created)
        embed.add_field(name="Members", value=str(len(channel.members)))
        await ctx.send(embed=embed)

    # Find a message by channelID-messageID combo
    @commands.command(aliases=["findmessage"])
    @commands.is_owner()
    @commands.bot_has_guild_permissions(embed_links=True)
    async def getmessage(self, ctx: commands.Context, channel_message: MessageParser):
        """Fetch a channelID-MessageID combo and display the message"""
        channel = self.bot.get_channel(channel_message.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_message.channel_id)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to fetch that channel")
            except discord.NotFound:
                return await ctx.send("I could not find that channel")
        try:
            message = await channel.fetch_message(channel_message.message_id)
        except discord.Forbidden:
            return await ctx.send("I do not have permission to fetch that message")
        except discord.NotFound:
            return await ctx.send(f"I could not find a message with the ID `{channel_message.message_id}`")

        created = f"<t:{int(message.created_at.timestamp())}:F> (<t:{int(message.created_at.timestamp())}:R>)"
        embed = discord.Embed(color=await self.bot.get_embed_color(ctx))
        embed.add_field(name="Author", value=f"{message.author} ({message.author.id})")
        embed.add_field(name="Created", value=created)
        if message.edited_at:
            edited = f"<t:{int(message.edited_at.timestamp())}:F> (<t:{int(message.edited_at.timestamp())}:R>)"
            embed.add_field(name="Edited", value=edited)
        embed.add_field(name="Server", value=message.guild.name)
        await ctx.send(embed=embed)

        kwargs = {"content": message.content, "embeds": message.embeds}
        if message.attachments:
            kwargs["files"] = [await a.to_file() for a in message.attachments]
        await ctx.send(**kwargs)

    @commands.command(aliases=["finduser"])
    async def getuser(self, ctx: commands.Context, user_id: int):
        """Find a user by ID"""
        user: discord.User = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return await ctx.send(f"I could not find any users with the ID `{user_id}`")
        created = f"<t:{int(user.created_at.timestamp())}:F> (<t:{int(user.created_at.timestamp())}:R>)"
        embed = discord.Embed(color=await ctx.embed_color())
        embed.set_image(url=user.display_avatar)
        embed.add_field(name="Username", value=user.name)
        embed.add_field(name="Display Name", value=user.display_name)
        embed.add_field(name="Created", value=created)
        # See if the bot shares any guilds with the user
        mutual_guilds = [g.name for g in self.bot.guilds if user.id in [m.id for m in g.members]]
        if mutual_guilds:
            embed.add_field(name="Mutual Servers", value="\n".join(mutual_guilds))
        await ctx.send(embed=embed)

    async def get_banner(self, user_id: int) -> t.Optional[str]:
        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user_id))
        if banner_id := req.get("banner"):
            return f"https://cdn.discordapp.com/banners/{user_id}/{banner_id}?size=1024"

    @commands.command(name="getbanner")
    @commands.bot_has_permissions(embed_links=True)
    async def get_user_banner(self, ctx: commands.Context, user: t.Optional[t.Union[discord.Member, int]] = None):
        """Get a user's banner"""
        if user is None:
            user = ctx.author

        user_id = user if isinstance(user, int) else user.id
        if ctx.guild:
            member = ctx.guild.get_member(user_id)
        else:
            try:
                member = await self.bot.get_or_fetch_user(user_id)
            except discord.NotFound:
                member = None

        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user_id))
        banner_id = req.get("banner")
        if not banner_id:
            return await ctx.send("This user does not have a banner")

        banner_url = f"https://cdn.discordapp.com/banners/{user_id}/{banner_id}?size=1024"
        embed = discord.Embed(color=await self.bot.get_embed_color(ctx))
        if member:
            embed.set_author(name=f"{member.name}'s banner", icon_url=member.display_avatar)
        else:
            embed.set_author(name=f"Banner for user {user_id}")
        embed.set_image(url=banner_url)
        await ctx.send(embed=embed)

    @commands.command(alias=["findwebhook"])
    async def getwebhook(self, ctx: commands.Context, webhook_id: int):
        """Find a webhook by ID"""
        try:
            webhook = await self.bot.fetch_webhook(webhook_id)
        except discord.NotFound:
            return await ctx.send(f"I could not find any webhooks with the ID `{webhook_id}`")
        created = f"<t:{int(webhook.created_at.timestamp())}:F> (<t:{int(webhook.created_at.timestamp())}:R>)"
        embed = discord.Embed(title="Webhook Info", color=await self.bot.get_embed_color(ctx))
        embed.add_field(name="Name", value=webhook.name)
        embed.add_field(name="Channel", value=webhook.channel.name)
        embed.add_field(name="Created", value=created)
        embed.add_field(name="Guild", value=webhook.guild.name)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def usersjson(self, ctx: commands.Context):
        """Get a json file containing all non-bot usernames/ID's in this guild"""
        members = {str(member.id): member.name for member in ctx.guild.members if not member.bot}
        file = text_to_file(json.dumps(members))
        await ctx.send("Here are all usernames and their ID's for this guild", file=file)

    @commands.command()
    @commands.guild_only()
    async def oldestchannels(self, ctx: commands.Context, amount: int = 10):
        """See which channel is the oldest"""

        def _exe(color: discord.Color):
            pages = []
            channels = [c for c in ctx.guild.channels if not isinstance(c, discord.CategoryChannel)]
            c_sort = sorted(channels, key=lambda x: x.created_at)
            chunks: t.List[t.List[discord.TextChannel]] = list(utils.chunk(c_sort, 10))
            for idx, chunk in enumerate(chunks):
                page = idx + 1
                buffer = StringIO()
                for i, channel in enumerate(chunk):
                    position = i + 1 + (page - 1) * 10
                    ts = int(channel.created_at.timestamp())
                    buffer.write(f"{position}. {channel.mention} created <t:{ts}:f> (<t:{ts}:R>)\n")
                txt = buffer.getvalue()
                embed = discord.Embed(
                    title=f"Oldest Channels in {ctx.guild.name}",
                    description=txt,
                    color=color,
                )
                foot = f"Page {page}/{len(chunks)}"
                embed.set_footer(text=foot)
                pages.append(embed)
            return pages

        async with ctx.typing():
            color = await self.bot.get_embed_color(ctx)
            pages = await asyncio.to_thread(_exe, color)
            await DynamicMenu(ctx, pages).refresh()

    @commands.command(aliases=["oldestusers"])
    @commands.guild_only()
    async def oldestmembers(self, ctx: commands.Context, include_bots: t.Optional[bool] = False):
        """
        See which users have been in the server the longest

        **Arguments**
        `include_bots:` (True/False) whether to include bots
        """

        def _exe(color: discord.Color):
            pages = []
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.joined_at)
            user_pos = {m.id: i + 1 for i, m in enumerate(m_sort)}
            chunks: t.List[t.List[discord.Member]] = list(utils.chunk(m_sort, 10))
            for idx, chunk in enumerate(chunks):
                page = idx + 1
                buffer = StringIO()
                for i, member in enumerate(chunk):
                    position = i + 1 + (page - 1) * 10
                    ts = int(member.joined_at.timestamp())
                    buffer.write(f"{position}. **{member}** joined <t:{ts}:f> (<t:{ts}:R>)\n")
                txt = buffer.getvalue()
                embed = discord.Embed(
                    title=f"Oldest Members in {ctx.guild.name}",
                    description=txt,
                    color=color,
                )
                foot = f"Page {page}/{len(chunks)}"
                if pos := user_pos.get(ctx.author.id):
                    foot += f" | Your position: {pos}"
                embed.set_footer(text=foot)
                pages.append(embed)
            return pages

        async with ctx.typing():
            color = await self.bot.get_embed_color(ctx)
            pages = await asyncio.to_thread(_exe, color)
            await DynamicMenu(ctx, pages).refresh()

    @commands.command()
    @commands.guild_only()
    async def oldestaccounts(self, ctx: commands.Context, include_bots: t.Optional[bool] = False):
        """
        See which users have the oldest Discord accounts

        **Arguments**
        `include_bots:` (True/False) whether to include bots
        """

        def _exe(color: discord.Color):
            pages = []
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.joined_at)
            user_pos = {m.id: i + 1 for i, m in enumerate(m_sort)}
            chunks: t.List[t.List[discord.Member]] = list(utils.chunk(m_sort, 10))
            for idx, chunk in enumerate(chunks):
                page = idx + 1
                buffer = StringIO()
                for i, member in enumerate(chunk):
                    position = i + 1 + (page - 1) * 10
                    ts = int(member.created_at.timestamp())
                    buffer.write(f"{position}. **{member}** created <t:{ts}:f> (<t:{ts}:R>)\n")
                txt = buffer.getvalue()
                embed = discord.Embed(
                    title=f"Oldest Members in {ctx.guild.name}",
                    description=txt,
                    color=color,
                )
                foot = f"Page {page}/{len(chunks)}"
                if pos := user_pos.get(ctx.author.id):
                    foot += f" | Your position: {pos}"
                embed.set_footer(text=foot)
                pages.append(embed)
            return pages

        async with ctx.typing():
            color = await self.bot.get_embed_color(ctx)
            pages = await asyncio.to_thread(_exe, color)
            await DynamicMenu(ctx, pages).refresh()

    @commands.command()
    @commands.guild_only()
    async def rolemembers(self, ctx: commands.Context, role: discord.Role):
        """View all members that have a specific role"""
        members = []
        async for member in AsyncIter(ctx.guild.members, steps=500, delay=0.001):
            if role.id in [r.id for r in member.roles]:
                members.append(member)

        if not members:
            return await ctx.send(f"There are no members with the {role.mention} role")

        members = sorted(members, key=lambda x: x.name)
        start = 0
        stop = 10
        pages = math.ceil(len(members) / 10)
        embeds = []
        for p in range(pages):
            if stop > len(members):
                stop = len(members)

            page = ""
            for i in range(start, stop, 1):
                member = members[i]
                page += f"{member.name} - `{member.id}`\n"
            em = discord.Embed(
                title=f"Members with role {role.name}",
                description=page,
                color=ctx.author.color,
            )
            em.set_footer(text=f"Page {p + 1}/{pages}")
            embeds.append(em)
            start += 10
            stop += 10

        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    async def wipevcs(self, ctx: commands.Context):
        """
        Clear all voice channels from a server
        """
        msg = await ctx.send("Are you sure you want to clear **ALL** Voice Channels from this server?")
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            return await msg.edit(content="Not deleting all VC's")
        perm = ctx.guild.me.guild_permissions.manage_channels
        if not perm:
            return await msg.edit(content="I dont have perms to manage channels")
        deleted = 0
        for chan in ctx.guild.channels:
            if isinstance(chan, discord.TextChannel):
                continue
            try:
                await chan.delete()
                deleted += 1
            except Exception:
                pass
        if deleted:
            await msg.edit(content=f"Deleted {deleted} VCs!")
        else:
            await msg.edit(content="No VCs to delete!")

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    async def wipethreads(self, ctx: commands.Context):
        """
        Clear all threads from a server
        """
        msg = await ctx.send("Are you sure you want to clear **ALL** threads from this server?")
        yes = await confirm(ctx, msg)
        if yes is None:
            return
        if not yes:
            return await msg.edit(content="Not deleting all threads")
        perm = ctx.guild.me.guild_permissions.manage_threads
        if not perm:
            return await msg.edit(content="I dont have perms to manage threads")
        deleted = 0
        for thread in ctx.guild.threads:
            await thread.delete()
            deleted += 1
        if deleted:
            await msg.edit(content=f"Deleted {deleted} threads!")
        else:
            await msg.edit(content="No threads to delete!")

    @commands.command(name="emojidata")
    @commands.bot_has_permissions(embed_links=True)
    async def emoji_info(self, ctx: commands.Context, emoji: t.Union[discord.Emoji, discord.PartialEmoji, str]):
        """Get info about an emoji"""

        def _url():
            emoji_unicode = []
            for char in emoji:
                char = hex(ord(char))[2:]
                emoji_unicode.append(char)
            if "200d" not in emoji_unicode:
                emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
            emoji_unicode = "-".join(emoji_unicode)
            return f"https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{emoji_unicode}.png"

        unescapable = string.ascii_letters + string.digits
        embed = discord.Embed(color=ctx.author.color)
        if isinstance(emoji, str):
            if emoji.startswith("http"):
                return await ctx.send("This is not an emoji!")

            fail = "Unable to get emoji name"
            txt = "\n".join(map(lambda x: unicodedata.name(x, fail), emoji)) + "\n\n"
            unicode = ", ".join(f"\\{i}" if i not in unescapable else i for i in emoji)
            category = ", ".join(unicodedata.category(c) for c in emoji)
            txt += f"`Unicode:   `{unicode}\n"
            txt += f"`Category:  `{category}\n"
            embed.set_image(url=_url())
        else:
            txt = emoji.name + "\n\n"
            txt += f"`ID:        `{emoji.id}\n"
            txt += f"`Animated:  `{emoji.animated}\n"
            txt += f"`Created:   `<t:{int(emoji.created_at.timestamp())}:F>\n"
            embed.set_image(url=emoji.url)

        if isinstance(emoji, discord.PartialEmoji):
            txt += f"`Custom:    `{emoji.is_custom_emoji()}\n"
        elif isinstance(emoji, discord.Emoji):
            txt += f"`Managed:   `{emoji.managed}\n"
            txt += f"`Server:    `{emoji.guild}\n"
            txt += f"`Available: `{emoji.available}\n"
            txt += f"`BotCanUse: `{emoji.is_usable()}\n"
            if emoji.roles:
                mentions = ", ".join([i.mention for i in emoji.roles])
                embed.add_field(name="Roles", value=mentions)

        embed.description = txt
        await ctx.send(embed=embed)

    @commands.command(name="samplevoters", aliases=["choosereact"])
    async def samplevoters(
        self,
        ctx: commands.Context,
        message: discord.Message,
        emoji: t.Union[discord.Emoji, discord.PartialEmoji, str],
        sample_size: int = 10,
        mention: bool = False,
    ):
        """
        Select a random sample of voters from a message

        **Arguments**
        `message:` The message to sample voters from
        `emoji:` The emoji to sample voters from
        `sample_size:` The number of voters to select

        **Examples**
        `[p]samplevoters 1234567890 🎉 5`
        """
        if not message.reactions:
            return await ctx.send("This message has no reactions")
        users_who_voted: t.List[discord.Member] = []
        for reaction in message.reactions:
            if str(reaction.emoji) == str(emoji):
                async for user in reaction.users():
                    users_who_voted.append(user)

        if not users_who_voted:
            return await ctx.send("No users voted with that emoji")

        sample_size = min(sample_size, len(users_who_voted))
        sample = random.sample(users_who_voted, sample_size)
        sample.sort(key=lambda x: x.name)
        if mention:
            txt = ", ".join([u.mention for u in sample])
        else:
            txt = "\n".join([f"{u} - {u.id}" for u in sample])
        await ctx.send(f"Selected {sample_size} random voters:\n{txt}")

    @commands.command(name="filterdelete")
    @commands.admin_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, embed_links=True)
    async def filter_delete(self, ctx: commands.Context, channel: t.Optional[discord.TextChannel], *, filters: str):
        """Delete all messages containing a keyword in a channel

        **Arguments**
        `channel:` The channel to delete messages from
        `filters:` The keywords to filter messages by, separated by new lines
        """
        if not channel:
            channel = ctx.channel
        filters = [i.lower().strip() for i in filters.split("\n") if i.lower().strip()]
        if not filters:
            return await ctx.send("No filters provided")

        if channel.id in self.scanning_channels:
            return await ctx.send("This channel is already being scanned for filters")

        self.scanning_channels.add(channel.id)
        try:
            await self._filter_delete(ctx, channel, filters)
        finally:
            self.scanning_channels.discard(channel.id)

    async def _filter_delete(self, ctx: commands.Context, channel: discord.TextChannel, filters: t.List[str]):
        cancelled = False

        def check_cancel(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "cancel"

        async def listen_for_cancel():
            nonlocal cancelled
            try:
                await self.bot.wait_for("message", check=check_cancel, timeout=None)
                cancelled = True
            except Exception:
                pass

        asyncio.create_task(listen_for_cancel())

        start_time = perf_counter()
        last_update = start_time
        scanned = 0
        deleted = 0
        embed = discord.Embed(title="Filtering Messages", color=ctx.author.color)
        embed.set_footer(text="Type 'cancel' to stop the scan")
        humanized_filters = humanize_list(filters)
        progress_msg = await ctx.send(embed=embed)

        async for message in channel.history(limit=None):
            if cancelled:
                break
            scanned += 1
            if message.content and any(f in message.content.lower() for f in filters):
                await message.delete()
                deleted += 1
            elif message.embeds:
                already_deleted = False
                for msg_embed in message.embeds:
                    if msg_embed.description and any(f in msg_embed.description.lower() for f in filters):
                        await message.delete()
                        deleted += 1
                        break
                    if msg_embed.title and any(f in msg_embed.title.lower() for f in filters):
                        await message.delete()
                        deleted += 1
                        break
                    if msg_embed.fields:
                        for field in msg_embed.fields:
                            if any(f in field.name.lower() for f in filters) or any(
                                f in field.value.lower() for f in filters
                            ):
                                await message.delete()
                                deleted += 1
                                already_deleted = True
                                break
                    if already_deleted:
                        break

            now = perf_counter()
            if now - last_update >= 5:
                rate = scanned / ((now - start_time) / 60)
                embed.description = (
                    f"Currently scanning {channel.mention} for the following filters:\n"
                    f"{box(humanized_filters)}\n"
                    f"Scanned: {scanned}\n"
                    f"Deleted: {deleted}\n"
                    f"Scanning ~{rate:.2f} messages/min"
                )
                with suppress(discord.HTTPException, aiohttp.ClientOSError):
                    await progress_msg.edit(embed=embed)
                last_update = now

        total_time = perf_counter() - start_time
        rate = scanned / (total_time / 60) if total_time else 0
        if cancelled:
            embed.description = (
                f"Scan cancelled in {channel.mention}\n"
                f"Scanned: {scanned}\n"
                f"Deleted: {deleted}\n"
                f"Scanning ~{rate:.2f} messages/min"
            )
            embed.title = "Cancelled Filtering Messages"
        else:
            embed.description = (
                f"Finished scanning: {channel.mention}\n"
                f"Scanned: {scanned}\n"
                f"Deleted: {deleted}\n"
                f"Scanning ~{rate:.2f} messages/min"
            )
            embed.title = "Finished Filtering Messages"
        embed.set_footer(text=f"Scan took {humanize_timedelta(seconds=int(total_time))}")
        await progress_msg.edit(embed=embed)
