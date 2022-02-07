import math

import discord
import tabulate
from redbot.core import commands, Config
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS


class EmojiTracker(commands.Cog):
    """
    Track emojis and view leaderboards/most emojis used ect..
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        default_global = {"blacklist": []}
        default_guild = {"users": {}}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        blacklist = await self.config.blacklist()
        if guild.id in blacklist:
            return
        user = guild.get_member(payload.user_id)
        if not user:
            return
        if user.bot:
            return
        async with self.config.guild(guild).users() as users:
            user_id = str(user.id)
            emoji = str(payload.emoji)
            if user_id not in users:
                users[user_id] = {}
            if emoji not in users[user_id]:
                users[user_id][emoji] = 1
            else:
                users[user_id][emoji] += 1

    @commands.command(name="ingoreguild")
    @commands.is_owner()
    async def blacklist_guild(self, ctx, guild_id: int):
        """
        Add/Remove a guild from the blacklist

        Enter a Guild ID to add it to the blacklist, to remove, simply enter it again
        """
        async with self.config.blacklist() as bl:
            if guild_id in bl:
                bl.remove(guild_id)
                await ctx.send(f"Guild {guild_id} removed from the blacklist")
            else:
                bl.append(guild_id)
                await ctx.send(f"Guild {guild_id} added to the blacklist")

    @commands.command(name="viewblacklist")
    @commands.is_owner()
    async def view_settings(self, ctx):
        """View EmojiTracker Blacklist"""
        bl = await self.config.blacklist()
        blacklist = ""
        for guild_id in bl:
            blacklist += f"{guild_id}"
        if not blacklist:
            return await ctx.send("No guild ID's have been added to the blacklist")
        embed = discord.Embed(
            title="Emoji Tracker Blacklist",
            description=f"```py\b{blacklist}\n```"
        )
        await ctx.send(embed=embed)

    @commands.command(name="emojilb")
    @commands.guild_only()
    async def emoji_lb(self, ctx):
        """View the emoji leaderboard"""
        users = await self.config.guild(ctx.guild).users()
        emojis = {}
        total_emojis = 0
        for data in users.values():
            for emoji, count in data.items():
                if emoji not in emojis:
                    emojis[emoji] = count
                else:
                    emojis[emoji] += count
                total_emojis += count
        sorted_emojis = sorted(emojis.items(), key=lambda x: x[1], reverse=True)
        pages = math.ceil(len(sorted_emojis) / 10)
        start = 0
        stop = 10
        color = discord.Color.random()
        embeds = []
        for p in range(pages):
            if stop > len(sorted_emojis):
                stop = len(sorted_emojis)
            top = ""
            for i in range(start, stop, 1):
                emoji = sorted_emojis[i][0]
                count = sorted_emojis[i][1]
                top += f"{emoji} - `{count}`\n"
            embed = discord.Embed(
                title="Emoji Leaderboard",
                description=f"Total Reactions: {'{:,}'.format(total_emojis)}\n{top}",
                color=color
            )
            embed.set_footer(text=f"Pages {p + 1}/{pages}")
            embeds.append(embed)
            start += 10
            stop += 10
        if not embeds:
            return await ctx.send("No reactions saved yet!")
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="reactlb")
    @commands.guild_only()
    async def reaction_lb(self, ctx):
        """View user leaderboard for most emojis added"""
        users = await self.config.guild(ctx.guild).users()
        lb = {}
        total_reactions = 0
        for uid, data in users.items():
            user = ctx.guild.get_member(int(uid))
            if not user:
                continue
            user = user.name
            if user not in lb:
                lb[user] = 0
            for count in data.values():
                lb[user] += count
                total_reactions += count
        sorted_reactions = sorted(lb.items(), key=lambda x: x[1], reverse=True)
        pages = math.ceil(len(sorted_reactions) / 10)
        start = 0
        stop = 10
        color = discord.Color.random()
        embeds = []
        for p in range(pages):
            if stop > len(sorted_reactions):
                stop = len(sorted_reactions)
            table = []
            for i in range(start, stop, 1):
                user = sorted_reactions[i][0]
                count = sorted_reactions[i][1]
                table.append([count, user])
            top = tabulate.tabulate(table, tablefmt="presto")
            embed = discord.Embed(
                title="Reaction Leaderboard",
                description=f"Total Reactions: {'{:,}'.format(total_reactions)}\n```py\n{top}\n```",
                color=color
            )
            embed.set_footer(text=f"Pages {p + 1}/{pages}")
            embeds.append(embed)
            start += 10
            stop += 10
        if not embeds:
            return await ctx.send("No reactions saved yet!")
        await menu(ctx, embeds, DEFAULT_CONTROLS)
