import json
import math
import string
import typing as t
import unicodedata

import discord
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import pagify, text_to_file

from ..abc import MixinMeta
from ..common.dpymenu import DEFAULT_CONTROLS, confirm, menu


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
    @commands.command()
    async def closestuser(self, ctx: commands.Context, *, query: str):
        """Find the closest fuzzy match for a user"""
        query = query.lower()
        matches: t.List[t.Tuple[int, discord.User]] = []
        for user in ctx.guild.members:
            matches.append((fuzz.ratio(query, user.name.lower()), user))
            matches.append((fuzz.ratio(query, user.display_name.lower()), user))
        matches = sorted(matches, key=lambda x: x[0], reverse=True)
        user = matches[0][1]
        await ctx.send(f"Closest match: {user.name} ({user.id}) with a score of {matches[0][0]:.2f}")

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
            f"**Owner:** {guild.owner}\n"
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
    async def get_user_banner(self, ctx: commands.Context, user: t.Union[discord.Member, int] = None):
        """Get a user's banner"""
        if user is None:
            user = ctx.author
        user_id = user if isinstance(user, int) else user.id
        member = user if isinstance(user, discord.Member) else ctx.guild.get_member(user_id)
        if not member:
            try:
                member = await self.bot.get_or_fetch_user(user_id)
            except discord.NotFound:
                pass
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
        async with ctx.typing():
            channels = [c for c in ctx.guild.channels if not isinstance(c, discord.CategoryChannel)]
            c_sort = sorted(channels, key=lambda x: x.created_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {c.mention} "
                    f"created <t:{int(c.created_at.timestamp())}:f> (<t:{int(c.created_at.timestamp())}:R>)"
                    for i, c in enumerate(c_sort[:amount])
                ]
            )
            for p in pagify(txt, page_length=4000):
                em = discord.Embed(description=p, color=ctx.author.color)
                await ctx.send(embed=em)

    @commands.command(aliases=["oldestusers"])
    @commands.guild_only()
    async def oldestmembers(
        self,
        ctx: commands.Context,
        amount: t.Optional[int] = 10,
        include_bots: t.Optional[bool] = False,
    ):
        """
        See which users have been in the server the longest

        **Arguments**
        `amount:` how many members to display
        `include_bots:` (True/False) whether to include bots
        """
        async with ctx.typing():
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.joined_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {m} "
                    f"joined <t:{int(m.joined_at.timestamp())}:f> (<t:{int(m.joined_at.timestamp())}:R>)"
                    for i, m in enumerate(m_sort[:amount])
                ]
            )

        embeds = [discord.Embed(description=p, color=ctx.author.color) for p in pagify(txt, page_length=2000)]
        pages = len(embeds)
        for idx, i in enumerate(embeds):
            i.set_footer(text=f"Page {idx + 1}/{pages}")
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command()
    @commands.guild_only()
    async def oldestaccounts(
        self,
        ctx: commands.Context,
        amount: t.Optional[int] = 10,
        include_bots: t.Optional[bool] = False,
    ):
        """
        See which users have the oldest Discord accounts

        **Arguments**
        `amount:` how many members to display
        `include_bots:` (True/False) whether to include bots
        """
        async with ctx.typing():
            if include_bots:
                members = [m for m in ctx.guild.members]
            else:
                members = [m for m in ctx.guild.members if not m.bot]
            m_sort = sorted(members, key=lambda x: x.created_at)
            txt = "\n".join(
                [
                    f"{i + 1}. {m} "
                    f"created <t:{int(m.created_at.timestamp())}:f> (<t:{int(m.created_at.timestamp())}:R>)"
                    for i, m in enumerate(m_sort[:amount])
                ]
            )

        embeds = [discord.Embed(description=p, color=ctx.author.color) for p in pagify(txt, page_length=2000)]
        pages = len(embeds)
        for idx, i in enumerate(embeds):
            i.set_footer(text=f"Page {idx + 1}/{pages}")
        await menu(ctx, embeds, DEFAULT_CONTROLS)

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
            return f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_unicode}.png"

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
