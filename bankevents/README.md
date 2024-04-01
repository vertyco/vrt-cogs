This cog allows you to add listeners for Red bank transactions in your own cogs by dispatching the following events:

- red_bank_set_balance
- red_bank_transfer_credits
- red_bank_withdraw_credits
- red_bank_deposit_credits
- red_bank_wipe
- red_bank_prune_accounts
- red_bank_set_global
- red_economy_payday_claim

Here are the implementations you can use in your cogs that will work when this cog is loaded:
All payload objects have a `to_dict` and `to_json` method that will serialize the payload object into a dictionary or JSON string respectively.

```python
@commands.Cog.listener()
async def on_red_bank_set_balance(self, payload: BankSetBalanceInformation):
    """Payload attributes:
    - recipient: Union[discord.Member, discord.User]
    - guild: Union[discord.Guild, None]
    - recipient_old_balance: int
    - recipient_new_balance: int
    """

@commands.Cog.listener()
async def on_red_bank_transfer_credits(self, payload: BankTransferInformation):
    """Payload attributes:
    - sender: Union[discord.Member, discord.User]
    - recipient: Union[discord.Member, discord.User]
    - guild: Union[discord.Guild, None]
    - transfer_amount: int
    - sender_new_balance: int
    - recipient_new_balance: int
    """

@commands.Cog.listener()
async def on_red_bank_wipe(self, scope: Union[int, None]):
    """scope: int (-1 for global, None for all members, guild_id for server bank)"""

@commands.Cog.listener()
async def on_red_bank_prune_accounts(self, payload: BankPruneInformation):
    """Payload attributes:
    - guild: Union[discord.Guild, None]
    - user_id: Union[int, None]
    - scope: int (1 for global, 2 for server, 3 for user)
    - pruned_users: list[int(user_id)] or dict[int(guild_id), list[int(user_id)]]
    """

@commands.Cog.listener()
async def on_red_bank_set_global(self, is_global: bool):
    """is_global: True if global bank, False if server bank"""

@commands.Cog.listener()
async def on_red_bank_withdraw_credits(self, payload: BankWithdrawDepositInformation):
    """Payload attributes:
    - member: discord.Member
    - guild: Union[discord.Guild, None]
    - amount: int
    - old_balance: int
    - new_balance: int
    """

@commands.Cog.listener()
async def on_red_bank_deposit_credits(self, payload: BankWithdrawDepositInformation):
    """Payload attributes:
    - member_id: int
    - guild_id: int (0 if global bank)
    - amount: int
    - old_balance: int
    - new_balance: int
    """

@commands.Cog.listener()
async def on_red_economy_payday_claim(self, payload: PaydayClaimInformation):
    """Payload attributes:
    - member: discord.Member
    - channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel]
    - amount: int
    - old_balance: int
    - new_balance: int
    """
```

This cog was written with the intention of being a placeholder until the following PR gets merged:
https://github.com/Cog-Creators/Red-DiscordBot/pull/5325
