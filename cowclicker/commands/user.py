import asyncio
import math
import typing as t
from datetime import timedelta
from io import StringIO

import discord
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.query import OrderByRaw
from piccolo.query.functions.aggregate import Count
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number, humanize_timedelta

from ..abc import MixinMeta
from ..common import const
from ..db.tables import Click, ensure_db_connection
from ..views.click import DynamicButton
from ..views.dynamic_menu import DynamicMenu


class User(MixinMeta):
    @commands.hybrid_command(name="click", description="Click the cow!")
    @commands.cooldown(1, 15, commands.BucketType.channel)
    @ensure_db_connection()
    async def start_click_menu(self, ctx: commands.Context):
        """Click the button!"""
        view = discord.ui.View(timeout=None).add_item(DynamicButton())
        color = await self.bot.get_embed_color(ctx)
        embed = discord.Embed(color=color).set_image(url=const.COW_IMAGE)
        embed.set_author(name="Cow Clicker!", url="https://en.wikipedia.org/wiki/Cow_Clicker")
        await ctx.send(embed=embed, view=view)

    @commands.command(name="clicks")
    @ensure_db_connection()
    async def show_user_clicks(
        self,
        ctx: commands.Context,
        member: t.Optional[discord.Member] = None,
        delta: t.Optional[str] = None,
    ):
        """Show the number of clicks you have"""
        if member is None:
            member = ctx.author
        query = Click.count().where(Click.author_id == member.id)
        if delta:
            delta_obj = commands.parse_timedelta(delta, minimum=timedelta(minutes=1))
            query = query.where(Click.created_on > TimestamptzNow().python() - delta_obj)

        count = await query
        if member.id == ctx.author.id:
            txt = f"You have clicked {count} times"
        else:
            txt = f"{member.display_name} has clicked {count} times"
        if delta:
            txt += f" over the last {humanize_timedelta(timedelta=delta_obj)}"

        await ctx.send(f"{txt}!")

    @commands.command(name="topclickers", aliases=["clicklb"])
    @ensure_db_connection()
    async def show_top_clickers(
        self,
        ctx: commands.Context,
        show_global: bool = False,
        delta: t.Optional[str] = None,
    ):
        """Show the top clickers

        **Arguments:**
        - `show_global`: Show global top clickers instead of server top clickers.
        - `delta`: Show top clickers within a time delta. (e.g. 1d, 1h, 1m)
        """

        async with ctx.typing():
            query = Click.select(Click.author_id, Count())
            delta_obj = None
            if delta:
                delta_obj = commands.parse_timedelta(delta, minimum=timedelta(minutes=1))
                query = query.where(Click.created_on > TimestamptzNow().python() - delta_obj)
            if not show_global:
                query = query.where(Click.author_id.is_in([m.id for m in ctx.guild.members]))
            query = query.group_by(Click.author_id).order_by(OrderByRaw("COUNT(*)"), ascending=False)

            top_clickers: list[dict] = await query
            if not top_clickers:
                return await ctx.send("No one has clicked yet!")

            total_clicks = sum(click["count"] for click in top_clickers)

            color = await self.bot.get_embed_color(ctx)
            title = "Top Clickers (Global)" if show_global else f"Top Clickers in {ctx.guild.name}"

            def _prep():
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
                    buffer.write("**Total Clicks:** `{}`\n".format(humanize_number(total_clicks)))
                    if delta_obj:
                        buffer.write(f"Over the last {humanize_timedelta(timedelta=delta_obj)}\n")
                    buffer.write("\n")
                    for i in range(start, stop):
                        click = top_clickers[i]
                        member = ctx.guild.get_member(click["author_id"]) or self.bot.get_user(click["author_id"])
                        if member:
                            buffer.write(f"**{i+1}**. {member.display_name} (`{click['count']}`)\n")
                        else:
                            buffer.write(f"**{i+1}**. {click['author_id']} (`{click['count']}`)\n")

                    embed = discord.Embed(description=buffer.getvalue(), color=color)
                    embed.set_footer(text=f"Page {idx+1}/{pages}{foot}")
                    embed.set_author(name=title, icon_url=const.COW_IMAGE)
                    start += 10
                    stop += 10
                    embeds.append(embed)
                return embeds

        embeds = await asyncio.to_thread(_prep)

        await DynamicMenu(ctx.author, embeds, ctx.channel).refresh()
