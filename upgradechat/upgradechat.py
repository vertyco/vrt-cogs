import logging
from datetime import datetime

import discord
from discord.ext.commands.cooldowns import BucketType
from redbot.core import Config, VersionInfo, bank, commands, version_info
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .api import API

DPY2 = True if version_info >= VersionInfo.from_str("3.5.0") else False

log = logging.getLogger("red.vrt.upgradechat")


class UpgradeChat(commands.Cog):
    """
    Upgrade.Chat API integration for buying economy credits directly instead of roles

    https://upgrade.chat/
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.2.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        default_guild = {
            "id": None,
            "secret": None,
            "bearer_token": None,  # API token created in upgrade.chat portal
            "last_refreshed": None,
            "conversion_ratio": 1000,  # If ratio == 100, then 1 USD = 1000 credits
            "claim_msg": "default",  # Reply when a user claims a purchase
            "products": {},  # Upgrade.Chat products added by UUID
            "log": 0,  # Log channel
            "users": {},  # Claimed purchases stored here with str(user.id) as keys
        }
        self.config.register_guild(**default_guild)

        self._lock = set()

    @commands.group(aliases=["upchat"])
    @commands.guild_only()
    @commands.guildowner()
    async def upgradechat(self, ctx: commands.Context):
        """Base command for cog settings"""

    @upgradechat.command()
    async def tokens(self, ctx: commands.Context, client_id: str, client_secret: str):
        """
        Set your Upgrade.Chat api tokens
        By using this feature it is assumed that you are already familiar with Upgrade.Chat

        1. Create your api keys here: https://upgrade.chat/developers

        2. Copy your client ID and Client Secret

        3. Run this command with your credentials

        **Enjoy!**
        """
        async with ctx.typing():
            await ctx.message.delete()
            token = await API().get_auth(client_id, client_secret)
            if not token:
                return await ctx.send("Failed to authorize your tokens!")
            async with self.config.guild(ctx.guild).all() as conf:
                conf["id"] = client_id
                conf["secret"] = client_secret
                conf["bearer_token"] = token
            await ctx.send("Your API tokens have been set!")

    @upgradechat.command()
    async def ratio(self, ctx: commands.Context, credit_worth: int):
        """
        Set the worth of 1 unit of real currency to economy credits

        for example, if `credit_worth` is 100, then $1 = 100 Credits
        """
        async with ctx.typing():
            await self.config.guild(ctx.guild).conversion_ratio.set(credit_worth)
            await ctx.tick()

    @upgradechat.command()
    async def message(self, ctx: commands.Context, *, claim_message: str):
        """
        Set the message the bot sends when a user claims a purchase

        Valid placeholders:
        {mention} - mention the user
        {username} - the users discord name
        {displayname} - the users nickname(if they have one)
        {uid} - the users Discord ID
        {guild} - guild name
        {creditsname} - name of the currency in your guild
        {amount} - the amount of credits the user has claimed

        set to `default` to use the default message
        """
        await self.config.guild(ctx.guild).claim_msg.set(claim_message)
        await ctx.tick()

    @upgradechat.command()
    async def addproduct(self, ctx: commands.Context, uuid: str):
        """
        Add an Upgrade.Chat product by UUID

        This can be any type of product, either subscription or one-time purchase.
        Users will be accredited based on `amount spend * conversion ratio`.
        Transactions can only be claimed once.
        """
        async with ctx.typing():
            conf = await self.config.guild(ctx.guild).all()
            if not conf["id"] or not conf["secret"]:
                return await ctx.send("UpgradeChat API credentials have not been set yet!")
            status, results, newtoken = await API().get_product(conf, uuid)
            if status != 200:
                return await ctx.send(f"I could not find any products with that UUID!\n" f"`status {status}`")
            product = results["data"]
            async with self.config.guild(ctx.guild).products() as products:
                products[uuid] = product
            await ctx.send(f"Your product with the title `{product['name']}` has been added!")
            await ctx.tick()
            if newtoken:
                await self.config.guild(ctx.guild).bearer_token.set(newtoken)

    @upgradechat.command()
    async def delproduct(self, ctx: commands.Context, uuid: str):
        """Delete an Upgrade.Chat product by UUID"""
        async with ctx.typing():
            async with self.config.guild(ctx.guild).products() as products:
                if uuid not in products:
                    text = ""
                    for pid, data in products.items():
                        text += f"`{pid}: `{data['name']}\n"
                    return await ctx.send(
                        "UUID not found in existing products. Here are the current products you have set.\n" f"{text}"
                    )
                await ctx.send(f"Product with title `{products[uuid]['name']}` has been deleted!")
                del products[uuid]

    @upgradechat.command()
    async def logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set log channel for claims"""
        async with ctx.typing():
            await self.config.guild(ctx.guild).log.set(channel.id)
            await ctx.send(f"Claim log channel has been set to `{channel.name}`")

    @upgradechat.command()
    async def purchases(self, ctx: commands.Context, *, member: discord.Member | int = None):
        """View user purchase history"""
        users = await self.config.guild(ctx.guild).users()

        embeds = []
        page = 0
        pages = len(list(users.keys()))
        for index, user_id in enumerate(users.keys()):
            purchases = users[user_id]
            user = ctx.guild.get_member(int(user_id))
            if member:
                if isinstance(member, int):
                    uid = member
                else:
                    uid = member.id
                if uid == int(user_id):
                    page = index

            name = f"{user.name} ({user.id})" if user else user_id

            em = discord.Embed(color=await self.bot.get_embed_color(ctx))
            em.set_author(
                name=f"{name}'s Purchases",
                icon_url=user.display_avatar if user else None,
            )

            total = 0
            desc = ""
            for transaction_id, purchase in purchases.items():
                price = purchase["price"]
                date = int(datetime.fromisoformat(purchase["date"]).timestamp())
                total += price
                desc += f"`${price}`|`{transaction_id}:`<t:{date}:D>(<t:{date}:R>)\n"

            em.description = desc
            em.set_footer(text=f"Page {index + 1}/{pages} | ${total} total")
            embeds.append(em)

        if not embeds:
            return await ctx.send("There are no purchases saved!")
        await menu(ctx, embeds, DEFAULT_CONTROLS, page=page)

    @upgradechat.command()
    async def view(self, ctx: commands.Context):
        """View your current products"""
        conf = await self.config.guild(ctx.guild).all()
        users = conf["users"]
        total = sum([sum([p["price"] for p in purchases.values()]) for purchases in users.values()])
        purchases = sum([len(purchases) for purchases in users.values()])
        currency_name = await bank.get_currency_name(ctx.guild)
        token = conf["bearer_token"] if conf["bearer_token"] else "Not Authorized Yet"
        cid = conf["id"]
        secret = conf["secret"]
        txt = (
            f"UpgradeChat secrets\n"
            f"`client_id:     `{cid}\n"
            f"`client_secret: `{secret}\n"
            f"`bearer_token:  `{token}"
        )
        try:
            await ctx.author.send(txt)
        except discord.Forbidden:
            await ctx.send("I was unable to DM your api credentials")
        ratio = conf["conversion_ratio"]
        producs = conf["products"]
        desc = (
            f"`Conversion Ratio: `{ratio} ($1 = {ratio} {currency_name})\n" f"`Claim Message:    `{conf['claim_msg']}\n"
        )
        if producs:
            text = ""
            for uuid, data in producs.items():
                text += f"{uuid}: {data['name']}\n"
        else:
            text = "None Added"

        em = discord.Embed(
            title="UpgradeChat Settings",
            description=f"{desc}\n"
            f"`Users:     `{len(users)}\n"
            f"`Purchases:  `{purchases}\n"
            f"`TotalSpent: `{total}\n"
            f"**Products**\n{box(text)}",
        )
        await ctx.send(embed=em)

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(1, 60, BucketType.user)
    async def claim(self, ctx: commands.Context):
        """Claim your Upgrade.Chat purchases!"""
        uid = ctx.author.id
        if uid in self._lock:
            return
        try:
            self._lock.add(uid)
            await self.do_claim(ctx)
        finally:
            self._lock.discard(uid)

    async def do_claim(self, ctx: commands.Context):
        async with ctx.typing():
            conf = await self.config.guild(ctx.guild).all()
            if not conf["id"] or not conf["secret"]:
                return await ctx.send("The owner of this guild has not set up their API tokens for Upgrade.Chat yet!")
            status, purchases, newtoken = await API().get_user_purchases(conf, ctx.author.id)
            if newtoken:
                await self.config.guild(ctx.guild).bearer_token.set(newtoken)
                await self.config.guild(ctx.guild).last_refreshed.set(datetime.now().isoformat())
            if status != 200:
                return await ctx.send("I could not find any users associated with your ID!")
            if not purchases:
                return await ctx.send("I could not find any valid purchases for your account!")

            products = conf["products"]
            users = conf["users"]
            uid = str(ctx.author.id)
            amount_spent = 0.0
            valid_purchases = 0
            purchase_data = {}
            for purchase in purchases:
                transaction_id = purchase["uuid"]
                if uid in users and transaction_id in users[uid]:
                    continue
                ordered_on = purchase["purchased_at"]
                if not purchase["order_items"]:
                    continue
                first_order_item = purchase["order_items"][0]
                product_id = first_order_item["product"]["uuid"]
                price = first_order_item["price"]
                if product_id in products:
                    purchase_data[transaction_id] = {"price": price, "date": ordered_on}
                    amount_spent += float(price)
                    valid_purchases += 1

            if not valid_purchases:
                return await ctx.send("I could not find any valid purchases for your account!")

            async with self.config.guild(ctx.guild).users() as users:
                if uid not in users:
                    users[uid] = {}
                for transaction_id, details in purchase_data.items():
                    users[uid][transaction_id] = details

            currency_name = await bank.get_currency_name(ctx.guild)
            ratio = conf["conversion_ratio"]
            amount_to_give = int(amount_spent * ratio)
            try:
                await bank.deposit_credits(ctx.author, amount_to_give)
            except BalanceTooHigh as e:
                await bank.set_balance(ctx.author, e.max_balance)

            title = "🎉Purchase claimed successfully!" if valid_purchases == 1 else "🎉Purchases claimed successfully!"
            desc = f"{ctx.author.display_name}, you have claimed {'{:,}'.format(amount_to_give)} {currency_name}!"
            claim_msg = conf["claim_msg"]
            if "default" not in claim_msg:
                params = {
                    "mention": ctx.author.mention,
                    "username": ctx.author.name,
                    "displayname": ctx.author.display_name,
                    "uid": ctx.author.id,
                    "guild": ctx.guild.name,
                    "creditsname": currency_name,
                    "amount": "{:,}".format(amount_to_give),
                }
                desc = claim_msg.format(**params)

            em = discord.Embed(title=title, description=desc, color=discord.Color.green())
            bal = await bank.get_balance(ctx.author)
            em.set_footer(text=f"Your new balance is {'{:,}'.format(bal)}!")
            await ctx.send(embed=em)

            logchan = self.bot.get_channel(conf["log"]) if conf["log"] else None
            if not logchan:
                return

            cluster = ""
            # If bot has ArkShop installed, get the user's registered cluster
            try:
                if arkshop := self.bot.get_cog("ArkShop"):
                    # For old versions
                    ashopusers = await arkshop.config.guild(ctx.guild).users()
                    if uid in ashopusers:
                        cluster = ashopusers[uid]["cluster"]
                elif arktools := self.bot.get_cog("ArkTools"):
                    # For arktools rewrite, which include shop
                    if pref_cluster := await arktools.db_utils.get_user_cluster(ctx.author):
                        cluster = pref_cluster
            except Exception as e:
                log.error("Failed to fetch cluster from Arktools", exc_info=e)

            desc = f"`Spent:   `${amount_spent}\n" f"`Awarded: `{'{:,}'.format(amount_to_give)} {currency_name}"

            if cluster:
                desc += f"\n`Cluster: `{cluster}"

            em = discord.Embed(
                title=f"{ctx.author.name} - {ctx.author.id} has claimed a purchase!",
                description=desc,
                color=ctx.author.color,
            )
            if DPY2:
                pfp = ctx.author.display_avatar.url
            else:
                pfp = ctx.author.avatar_url

            if pfp:
                em.set_thumbnail(url=pfp)
            await logchan.send(embed=em)
