import discord
from redbot.core import bank, commands
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..views.dynamic_menu import DynamicMenu


class User(MixinMeta):
    @commands.group(name="swearjar", invoke_without_command=True)
    @commands.guild_only()
    async def swearjar(self, ctx: commands.Context):
        """View the server's swear jar."""
        jar_total = await self.config.guild(ctx.guild).jar_total()
        currency = await bank.get_currency_name(ctx.guild)
        await ctx.send(f"💰 The swear jar holds {humanize_number(jar_total)} {currency}.")

    @swearjar.command(name="leaderboard", aliases=["lb"])
    @commands.guild_only()
    async def swearjar_leaderboard(self, ctx: commands.Context):
        """Top swear jar payers in this server."""
        members = await self.config.all_members(ctx.guild)
        payers = [(uid, data.get("paid", 0)) for uid, data in members.items() if data.get("paid", 0) > 0]
        if not payers:
            await ctx.send("Nobody has paid into the swear jar yet.")
            return
        payers.sort(key=lambda pair: pair[1], reverse=True)
        currency = await bank.get_currency_name(ctx.guild)
        pages = []
        per_page = 10
        total_pages = (len(payers) + per_page - 1) // per_page
        for page_index in range(total_pages):
            chunk = payers[page_index * per_page : (page_index + 1) * per_page]
            lines = []
            for position, (uid, paid) in enumerate(chunk, start=page_index * per_page + 1):
                member = ctx.guild.get_member(uid)
                name = member.display_name if member else f"Unknown member ({uid})"
                lines.append(f"**{position}.** {name}: {humanize_number(paid)}")
            embed = discord.Embed(
                title="Swear Jar Leaderboard",
                description=f"{currency} fined.\n" + "\n".join(lines),
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"Page {page_index + 1}/{total_pages}")
            pages.append(embed)
        await DynamicMenu(ctx, pages).refresh()
