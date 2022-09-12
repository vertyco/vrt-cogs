import discord
from redbot.core import commands, Config, bank
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import box

from .api import API


class UpgradeChat(commands.Cog):
    """
    Upgrade.Chat API integration for buying economy credits directly instead of roles

    https://upgrade.chat/
    """
    __author__ = "Vertyco"
    __version__ = "0.0.4"

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
            "bearer_token": None,  # API token created in upgrade.chat portal
            "conversion_ratio": 1000,  # If ratio == 100, then 1 USD = 1000 credits
            "claim_msg": "default",  # Reply when a user claims a purchase
            "products": {},  # Upgrade.Chat products added by UUID
            "log": 0,  # Log channel
            "users": {}  # Claimed purchases stored here with str(user.id) as keys
        }
        self.config.register_guild(**default_guild)

        if discord.__version__ > "1.7.3":
            self.dpy2 = True
        else:
            self.dpy2 = False

    @commands.group(aliases=["upchat"])
    @commands.guild_only()
    @commands.guildowner()
    async def upgradechat(self, ctx: commands.Context):
        """Base command for cog settings"""

    @upgradechat.command()
    async def token(self, ctx: commands.Context, bearer_token: str):
        """
        Set your Upgrade.Chat bearer token

        1. Create your api keys here: https://upgrade.chat/developers

        2. Then head here: https://upgrade.chat/developers/documentation

        3. Click the `Authorize` button and then confirm by clicking authorize again

        4. Get your bearer token by clicking one of the endpoint dropdowns and click `Try it out`

        5. Click `Execute` and copy your bearer token from the `Curl` example below it

        6. You now have your token
        """
        async with ctx.typing():
            await ctx.message.delete()
            await self.config.guild(ctx.guild).bearer_token.set(bearer_token)
            await ctx.send("Your API token has been set!")
            await ctx.tick()

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
            token = await self.config.guild(ctx.guild).bearer_token()
            if not token:
                return await ctx.send("API token has not been set yet!")
            status, results = await API().get_product(token, uuid)
            if status != 200:
                return await ctx.send("I could not find any products with that UUID!")
            product = results["data"]
            async with self.config.guild(ctx.guild).products() as products:
                products[uuid] = product
            await ctx.send(f"Your product with the title `{product['name']}` has been added!")
            await ctx.tick()

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
                        "UUID not found in existing products. Here are the current products you have set.\n"
                        f"{text}"
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
    async def view(self, ctx: commands.Context):
        """View your current products"""
        conf = await self.config.guild(ctx.guild).all()
        currency_name = await bank.get_currency_name(ctx.guild)
        ratio = conf["conversion_ratio"]
        producs = conf["products"]
        desc = f"`Conversion Ratio: `{ratio} ($1 = {ratio} {currency_name})\n" \
               f"`Claim Message:    `{conf['claim_msg']}\n"
        if producs:
            text = ""
            for uuid, data in producs.items():
                text += f"{uuid}: {data['name']}\n"
        else:
            text = "None Added"

        em = discord.Embed(
            title="UpgradeChat Settings",
            description=f"{desc}\n**Products**\n{box(text)}"
        )
        await ctx.send(embed=em)

    @commands.command()
    @commands.guild_only()
    async def claim(self, ctx: commands.Context):
        """Claim your Upgrade.Chat purchases!"""
        async with ctx.typing():
            conf = await self.config.guild(ctx.guild).all()
            token = conf["bearer_token"]
            if not token:
                return await ctx.send("The owner of this guild has not set up their API tokens for Upgrade.Chat yet!")
            status, purchases = await API().get_user_purchases(token, ctx.author.id)
            if status != 200:
                return await ctx.send("I could not find any users associated with your ID!")
            if not purchases:
                return await ctx.send("I could not find any purchases for your account!")

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

            title = "🎉Purchase claimed successfully!🎉" if valid_purchases == 1 else "🎉Purchases claimed successfully!🎉"
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
                    "amount": "{:,}".format(amount_to_give)
                }
                desc = claim_msg.format(**params)

            em = discord.Embed(
                title=title,
                description=desc,
                color=discord.Color.green()
            )
            bal = await bank.get_balance(ctx.author)
            em.set_footer(text=f"Your new balance is {'{:,}'.format(bal)}!")
            await ctx.send(embed=em)

            logchan = self.bot.get_channel(conf['log']) if conf['log'] else None
            if not logchan:
                return

            # If bot has ArkShop installed, get the user's registered cluster
            arkshop = self.bot.get_cog("ArkShop")
            cluster = ""
            if arkshop:
                ashopusers = await arkshop.config.guild(ctx.guild).users()
                if uid in ashopusers:
                    cluster = ashopusers[uid]["cluster"]

            desc = f"`Spent:   `${amount_spent}\n" \
                   f"`Awarded: `{'{:,}'.format(amount_to_give)} {currency_name}"

            if cluster:
                desc += f"\n`Cluster: `{cluster}"

            em = discord.Embed(
                title=f"{ctx.author.name} - {ctx.author.id} has claimed a purchase!",
                description=desc,
                color=ctx.author.color
            )
            if self.dpy2:
                if ctx.author.avatar:
                    em.set_thumbnail(url=ctx.author.avatar.url)
            else:
                em.set_thumbnail(url=ctx.author.avatar_url)
            await logchan.send(embed=em)
