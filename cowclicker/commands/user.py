import math
from io import StringIO
from uuid import uuid4

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common import const
from ..db.tables import Click, SavedView, ensure_db_connection
from ..views.click import ClickView
from ..views.dynamic_menu import DynamicMenu


class User(MixinMeta):
    @commands.hybrid_command(name="click", description="Click the cow!")
    @ensure_db_connection()
    async def start_click_menu(self, ctx: commands.Context):
        """Click the button!"""
        custom_id = str(uuid4())
        view = ClickView(self, custom_id)
        color = await self.bot.get_embed_color(ctx)
        embed = discord.Embed(title="Cow Clicker!", color=color)
        embed.set_image(url=const.COW_IMAGE)
        msg = await ctx.send(embed=embed, view=view)
        await SavedView(author_id=ctx.author.id, message_id=msg.id, custom_id=custom_id).save()

    @commands.command(name="clicks")
    @ensure_db_connection()
    async def show_user_clicks(self, ctx: commands.Context, member: discord.Member | None = None):
        """Show the number of clicks you have"""
        if member is None:
            member = ctx.author
        count = await Click.count().where(Click.author_id == ctx.author.id)
        if member.id == ctx.author.id:
            await ctx.send(f"You have clicked {count} times!")
        else:
            await ctx.send(f"{member.display_name} has clicked {count} times!")

    @commands.command(name="topclickers", aliases=["clicklb"])
    @ensure_db_connection()
    async def show_top_clickers(self, ctx: commands.Context, amount: int = 10):
        """Show the top clickers"""
        if amount < 1:
            return await ctx.send("Amount must be greater than 0.")
        assert isinstance(amount, int), "Amount must be an integer."
        top_clickers: list[dict] = await Click.raw(
            "SELECT author_id, COUNT(*) FROM click GROUP BY author_id ORDER BY COUNT(*) DESC LIMIT {}",
            amount,
        )
        if not top_clickers:
            return await ctx.send("No one has clicked yet!")

        color = await self.bot.get_embed_color(ctx)
        embeds = []
        pages = math.ceil(len(top_clickers) / 10)

        # Find the user's position before pagifying
        foot = ""
        for idx, click in enumerate(top_clickers):
            if click["author_id"] == ctx.author.id:
                foot = f" | Your position: {idx+1}"
                break

        start = 0
        stop = 10

        for idx in range(pages):
            stop = min(stop, len(top_clickers))
            buffer = StringIO()
            for i in range(start, stop):
                click = top_clickers[i]
                member = ctx.guild.get_member(click["author_id"])
                if member:
                    buffer.write(f"{i+1}. {member.display_name} - {click['count']}\n")
                else:
                    buffer.write(f"{i+1}. {click['author_id']} - {click['count']}\n")

            embed = discord.Embed(description=buffer.getvalue(), color=color)
            embed.set_footer(text=f"Page {idx+1}/{pages}{foot}")
            embed.set_author(name="Top Clickers", icon_url=const.COW_IMAGE)
            start += 10
            stop += 10
            embeds.append(embed)

        await DynamicMenu(ctx.author, embeds, ctx.channel).refresh()
