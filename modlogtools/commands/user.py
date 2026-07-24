from __future__ import annotations

from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number, pagify

from ..abc import MixinMeta


class User(MixinMeta):
    """User-facing commands."""

    @commands.command(name="mywarnings", aliases=["mywarns"])
    @commands.guild_only()
    async def mywarnings(self, ctx: commands.Context):
        """View your own active warnings and when they expire."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        await self.sync_guild_records(ctx.guild)

        records = [
            record
            for record in self.db.get_conf(ctx.guild).records.values()
            if record.user_id == ctx.author.id and record.is_active
        ]
        if not records:
            return await ctx.send("You have no active warnings.")

        records.sort(key=lambda record: record.created_at, reverse=True)
        total_points = sum(record.points for record in records)
        lines = [
            f"Active warnings: {humanize_number(len(records))}",
            f"Active points: {humanize_number(total_points)}",
        ]
        next_expiry = min((record.expires_at for record in records if record.expires_at), default=None)
        if next_expiry is not None:
            lines.append(f"Next expiry: <t:{int(next_expiry.timestamp())}:R>")

        for record in records:
            reason = record.description or "No reason provided"
            if len(reason) > 100:
                reason = reason[:97] + "..."
            expires = f" | expires <t:{record.expires_ts}:R>" if record.expires_at else ""
            lines.append(f"- <t:{record.created_ts}:d> | {record.points} pts{expires} | {reason}")

        for page in pagify("\n".join(lines)):
            await ctx.send(page)
