import logging
from decimal import Decimal

import discord
from redbot.core import bank, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common.api import Client, parse_time
from ..common.utils import API_ERRORS, buyer_error_text, claim_text, credits_for, format_amount

log = logging.getLogger("red.vrt.glassrelay.commands.user")


class User(MixinMeta):
    """Buyer commands"""

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True)
    async def claim(self, ctx: commands.Context):
        """Claim the credits for your GlassRelay purchases"""
        settings = await self.db.get_guild(ctx.guild.id)
        product_ids = {p["product_id"] for p in await self.db.get_products(ctx.guild.id)}
        if not settings or not settings["api_key"] or not product_ids:
            return await ctx.send("This server hasn't set up GlassRelay purchases yet.")
        credited: list[tuple[dict, int]] = []
        async with ctx.typing():
            client = Client(self.session, settings["api_key"])
            try:
                payments = [
                    p async for p in client.iter_buyer_payments(ctx.author.id) if p["product_id"] in product_ids
                ]
            except API_ERRORS as e:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(buyer_error_text(e))
            for payment in payments:
                credits = credits_for(payment["amount"], settings["ratio"])
                # Saved before the deposit: a crash in between loses one credit instead of paying it twice
                if await self.db.record_payment(
                    ctx.guild.id,
                    payment["id"],
                    ctx.author.id,
                    payment["product_id"],
                    payment["amount"],
                    credits,
                    parse_time(payment["created_at"]),
                ):
                    credited.append((payment, credits))
        if not credited:
            return await ctx.send(
                "I couldn't find any new purchases for your account. "
                "Make sure your GlassRelay login is linked to this Discord account."
            )
        awarded = sum(credits for _, credits in credited)
        try:
            await bank.deposit_credits(ctx.author, awarded)
        except BalanceTooHigh as e:
            await bank.set_balance(ctx.author, e.max_balance)
        currency = await bank.get_currency_name(ctx.guild)
        purchases = [payment for payment, _ in credited]
        await self.send_thanks(ctx, settings["claim_message"], len(purchases), awarded, currency)
        await self.send_claim_log(ctx, settings["log_channel"], purchases, awarded, currency)
        self.bot.dispatch(
            "glassrelay_claim",
            ctx.author,
            {
                "guild": ctx.guild,
                "channel": ctx.channel,
                "amount_spent": sum((Decimal(p["amount"]) for p in purchases), Decimal(0)),
                "amount_awarded": awarded,
                "valid_purchases": len(purchases),
                "currency_name": currency,
                "purchases": purchases,
            },
        )

    async def send_thanks(
        self, ctx: commands.Context, template: str | None, count: int, awarded: int, currency: str
    ) -> None:
        title = "🎉Purchase claimed successfully!" if count == 1 else "🎉Purchases claimed successfully!"
        embed = discord.Embed(
            title=title,
            description=claim_text(template, ctx.author, awarded, currency),
            color=discord.Color.green(),
        )
        balance = await bank.get_balance(ctx.author)
        embed.set_footer(text=f"Your new balance is {humanize_number(balance)}!")
        await ctx.send(embed=embed)

    async def send_claim_log(
        self, ctx: commands.Context, channel_id: int, purchases: list[dict], awarded: int, currency: str
    ) -> None:
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        spent: dict[str, Decimal] = {}
        for payment in purchases:
            spent[payment["currency"]] = spent.get(payment["currency"], Decimal(0)) + Decimal(payment["amount"])
        spent_text = ", ".join(f"{format_amount(total)} {code}" for code, total in spent.items())
        desc = f"`Spent:   `{spent_text}\n`Awarded: `{humanize_number(awarded)} {currency}"
        if cluster := await self.get_cluster(ctx.author):
            desc += f"\n`Cluster: `{cluster}"
        embed = discord.Embed(
            title=f"{ctx.author.name} - {ctx.author.id} has claimed a purchase!",
            description=desc,
            color=ctx.author.color,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            log.warning(f"Couldn't post the claim log in {ctx.guild.id}", exc_info=e)

    async def get_cluster(self, member: discord.Member) -> str:
        """The member's ARK cluster from ArkShop or ArkTools, if either is loaded"""
        try:
            if arkshop := self.bot.get_cog("ArkShop"):
                users = await arkshop.config.guild(member.guild).users()
                if str(member.id) in users:
                    return users[str(member.id)]["cluster"]
            elif arktools := self.bot.get_cog("ArkTools"):
                return await arktools.db_utils.get_user_cluster(member) or ""
        except Exception as e:
            log.error("Failed to fetch cluster from ArkShop or ArkTools", exc_info=e)
        return ""
