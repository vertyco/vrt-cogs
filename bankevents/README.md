This cog allows you to add listeners for Red bank transactions in your own cogs by dispatching the following events:

- bank_set_balance
- bank_withdraw_credits
- bank_deposit_credits
- bank_transfer_credits

Here are the implementations you can use in your cogs that will work when this cog is loaded:

```python
@commands.Cog.listener()
async def on_bank_set_balance(self, member: typing.Union[discord.Member, discord.User], amount: int):
    print(f"{member.name}'s balance was set to {amount}")

@commands.Cog.listener()
async def on_bank_withdraw_credits(self, member: discord.Member, amount: int):
    print(f"{member.name} had {amount} credits withdrawn from their account")

@commands.Cog.listener()
async def on_bank_deposit_credits(self, member: discord.Member, amount: int):
    print(f"{member.name} had {amount} credits deposited into their account")

@commands.Cog.listener()
async def on_bank_transfer_credits(
    self,
    from_: typing.Union[discord.Member, discord.User],
    to: typing.Union[discord.Member, discord.User],
    amount: int,
):
    print(f"{from_.name} transferred {amount} credits to {to.name}")
```
