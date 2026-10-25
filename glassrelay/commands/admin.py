import itertools
import logging
from decimal import Decimal

import discord
from redbot.core import bank, commands
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from ..common.api import Client, parse_time
from ..common.utils import API_ERRORS, buyer_pages, error_text, format_amount, init_record
from ..views.dynamic_menu import DynamicMenu
from ..views.key_entry import KeyEntry
from ..views.product_picker import ProductPicker, product_option

log = logging.getLogger("red.vrt.glassrelay.commands.admin")


class Admin(MixinMeta):
    @commands.group()
    @commands.guild_only()
    @commands.guildowner()
    async def glassrelay(self, ctx: commands.Context):
        """GlassRelay settings"""

    @glassrelay.command()
    async def key(self, ctx: commands.Context):
        """Connect your GlassRelay store with an API key

        Opens a form to paste the key into, so the key never shows in the channel.
        """
        steps = (
            "1. Open the API keys page in your GlassRelay dashboard.\n"
            "2. Make a key with **Include customer data** ticked.\n"
            "3. Press the button below and paste the key.\n"
            "-# Keep guest checkout off on your store. Guests have no Discord account, "
            "so their payments can't be credited."
        )

        async def check_key(api_key: str) -> tuple[bool, str]:
            client = Client(self.session, api_key)
            try:
                store = await client.get_storefront()
                await client.check_customers_scope()
            except API_ERRORS as e:
                return False, error_text(e, ctx.clean_prefix)
            await self.db.set_api_key(ctx.guild.id, api_key)
            return True, f"Connected to the GlassRelay store **{discord.utils.escape_markdown(store['name'])}**."

        view = KeyEntry(ctx, steps, check_key)
        view.message = await ctx.send(view=view)

    @glassrelay.command()
    async def ratio(self, ctx: commands.Context, credit_worth: commands.Range[int, 1, None]):
        """Set how many credits 1 unit of your store's currency buys

        For example, if `credit_worth` is 1000, then $1 = 1000 credits.
        """
        await self.db.set_ratio(ctx.guild.id, credit_worth)
        await ctx.tick()

    @glassrelay.command()
    async def message(self, ctx: commands.Context, *, claim_message: str):
        """Set the message the bot sends when a buyer gets their credits

        Valid placeholders:
        {mention} - mention the user
        {username} - the user's Discord name
        {displayname} - the user's nickname (if they have one)
        {uid} - the user's Discord ID
        {guild} - server name
        {creditsname} - name of the currency in your server
        {amount} - the amount of credits the user got

        Set to `default` to use the default message.
        """
        value = None if claim_message.lower() == "default" else claim_message
        await self.db.set_claim_message(ctx.guild.id, value)
        await ctx.tick()

    @glassrelay.command()
    async def logchannel(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        """Set the channel where credited payments are logged

        Leave the channel out to turn logging off.
        """
        await self.db.set_log_channel(ctx.guild.id, channel.id if channel else 0)
        if channel:
            await ctx.send(f"Credited payments will be logged in {channel.mention}.")
        else:
            await ctx.send("Logging is off.")

    @glassrelay.command()
    async def addproduct(self, ctx: commands.Context):
        """Add a product from your GlassRelay store

        Opens a menu of your store's products.
        Buyers get `amount paid * ratio` credits for each payment on the product you pick.
        Each payment is credited once.
        Run `[p]glassrelay init` right after, so payments made before now aren't credited.
        """
        settings = await self.db.get_guild(ctx.guild.id)
        if not settings or not settings["api_key"]:
            return await ctx.send(f"Connect your store first with `{ctx.clean_prefix}glassrelay key`.")
        async with ctx.typing():
            try:
                store_products = [p async for p in Client(self.session, settings["api_key"]).iter_products()]
            except API_ERRORS as e:
                return await ctx.send(error_text(e, ctx.clean_prefix))
        added = {p["product_id"] for p in await self.db.get_products(ctx.guild.id)}
        live = {p["id"]: p["name"] for p in store_products if p["archived_at"] is None}
        names = {product_id: name for product_id, name in live.items() if product_id not in added}
        if not live:
            return await ctx.send("Your GlassRelay store has no products yet.")
        if not names:
            return await ctx.send("Every product on your store is already added.")

        async def add(product_id: int) -> str:
            await self.db.add_product(ctx.guild.id, product_id, names[product_id])
            return (
                f"Added **{discord.utils.escape_markdown(names[product_id])}**. "
                f"Run `{ctx.clean_prefix}glassrelay init` next, so payments made before now aren't credited."
            )

        choices = [product_option(product_id, name) for product_id, name in names.items()]
        view = ProductPicker(ctx, "Add a product", choices, add)
        view.message = await ctx.send(view=view)

    @glassrelay.command()
    async def delproduct(self, ctx: commands.Context):
        """Remove a product

        Opens a menu of the products you added.
        Removing one also deletes its payment records, so if you add it again, run `[p]glassrelay init` again too.
        """
        names = {p["product_id"]: p["name"] for p in await self.db.get_products(ctx.guild.id)}
        if not names:
            return await ctx.send("No products are added.")

        async def remove(product_id: int) -> str:
            await self.db.remove_product(ctx.guild.id, product_id)
            return f"Removed **{discord.utils.escape_markdown(names[product_id])}**."

        choices = [product_option(product_id, name) for product_id, name in names.items()]
        view = ProductPicker(ctx, "Remove a product", choices, remove)
        view.message = await ctx.send(view=view)

    @glassrelay.command(aliases=["initialize"])
    async def init(self, ctx: commands.Context):
        """Mark a product's past payments as done, so they are never credited

        Opens a menu of the products you added.
        Run this right after adding a product. Payments made after this are credited as normal.
        Each past payment still shows in purchase history under its buyer, worth `amount paid * ratio` at
        today's ratio.
        """
        settings = await self.db.get_guild(ctx.guild.id)
        if not settings or not settings["api_key"]:
            return await ctx.send(f"Connect your store first with `{ctx.clean_prefix}glassrelay key`.")
        names = {p["product_id"]: p["name"] for p in await self.db.get_products(ctx.guild.id)}
        if not names:
            return await ctx.send(f"Add a product first with `{ctx.clean_prefix}glassrelay addproduct`.")

        async def mark(product_id: int) -> str:
            marked = 0
            try:
                async for payment in Client(self.session, settings["api_key"]).iter_payments():
                    if payment["product_id"] != product_id:
                        continue
                    user_id, credits = init_record(payment, settings["ratio"])
                    if await self.db.record_payment(
                        ctx.guild.id,
                        payment["id"],
                        user_id,
                        product_id,
                        payment["amount"],
                        credits,
                        parse_time(payment["created_at"]),
                    ):
                        marked += 1
            except API_ERRORS as e:
                return (
                    f"{error_text(e, ctx.clean_prefix)}\n"
                    f"Marked {humanize_number(marked)} payments before that. Run this again to finish."
                )
            name = discord.utils.escape_markdown(names[product_id])
            return f"Marked {humanize_number(marked)} past payments for **{name}**. They won't be credited."

        choices = [product_option(product_id, name) for product_id, name in names.items()]
        view = ProductPicker(ctx, "Mark past payments", choices, mark)
        view.message = await ctx.send(view=view)

    @glassrelay.command()
    @commands.bot_has_permissions(embed_links=True)
    async def purchases(self, ctx: commands.Context, *, member: discord.Member | int | None = None):
        """View purchase history, one buyer per page

        Give a member or user id to open their page first.
        """
        payments = await self.db.get_guild_payments(ctx.guild.id)
        if not payments:
            return await ctx.send("No purchases have been credited yet.")
        user_id = member.id if isinstance(member, discord.Member) else member
        currency = await bank.get_currency_name(ctx.guild)
        color = await self.bot.get_embed_color(ctx)
        pages: list[discord.Embed] = []
        start = None
        for buyer_id, group in itertools.groupby(payments, key=lambda payment: payment["user_id"]):
            if buyer_id == user_id:
                start = len(pages)
            pages.extend(buyer_pages(ctx.guild, buyer_id, list(group), currency, color))
        if user_id is not None and start is None:
            return await ctx.send("That user has no purchases.")
        await DynamicMenu(ctx, pages, page=start or 0).refresh()

    @glassrelay.command()
    @commands.bot_has_permissions(embed_links=True)
    async def view(self, ctx: commands.Context):
        """View the settings"""
        settings = await self.db.get_guild(ctx.guild.id)
        if settings is None:
            return await ctx.send(f"Nothing is set up yet. Start with `{ctx.clean_prefix}glassrelay key`.")
        products = await self.db.get_products(ctx.guild.id)
        payments = await self.db.get_guild_payments(ctx.guild.id)
        currency = await bank.get_currency_name(ctx.guild)
        total = sum((Decimal(payment["amount"]) for payment in payments), Decimal(0))
        buyers = len({payment["user_id"] for payment in payments})
        log_channel = f"<#{settings['log_channel']}>" if settings["log_channel"] else "Off"
        product_text = "\n".join(f"{p['product_id']}: {p['name']}" for p in products) or "None added"
        desc = (
            f"**Store:** {'Connected' if settings['api_key'] else 'Not connected'}\n"
            f"**Ratio:** 1 = {humanize_number(settings['ratio'])} {currency}\n"
            f"**Log channel:** {log_channel}\n"
            f"**Buyers:** {humanize_number(buyers)}\n"
            f"**Purchases:** {humanize_number(len(payments))}\n"
            f"**Total spent:** {format_amount(total)}\n"
            f"**Products**\n{box(product_text)}"
        )
        embed = discord.Embed(title="GlassRelay settings", description=desc, color=await self.bot.get_embed_color(ctx))
        embed.add_field(name="Claim message", value=(settings["claim_message"] or "Default")[:1024], inline=False)
        await ctx.send(embed=embed)
