import json
import typing as t

import aiohttp
from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import box, text_to_file


class BankBackup(commands.Cog):
    """
    Backup bank balances for all members of a guild
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot: Red = bot

    @commands.command(name="bankbackup")
    @commands.guildowner()
    async def backup(self, ctx: commands.Context):
        """Backup your guild's bank balances"""
        if await bank.is_global():
            return await ctx.send("Cannot make backup. Bank is set to global.")

        _bank_members = await bank._config.all_members(ctx.guild)
        bank_members: t.Dict[str, int] = {str(k): v["balance"] for k, v in _bank_members.items()}
        raw = json.dumps(bank_members, indent=2)
        file = text_to_file(raw, filename=f"bank_backup_{ctx.guild.id}.json")
        await ctx.send("Here's your bank backup file!", file=file)

    @commands.command(name="bankrestore")
    @commands.guildowner()
    async def restore(self, ctx: commands.Context, set_or_add: str):
        """
        Restore your guild's bank balances.
        Attach your backup file with this command.

        **Arguments**
        - `<set_or_add>`: Whether you want to `add` or `set` balances from the backup.
        """
        if await bank.is_global():
            return await ctx.send("Cannot restore backup because bank is set to global.")
        if not ctx.message.attachments:
            return await ctx.send("Attach your backup file to the message when using this command.")
        if "a" not in set_or_add.lower() and "s" not in set_or_add.lower():
            return await ctx.send(
                "Specify whether you want to `add` or `set` balances from the backup.\n"
                "Add: adds the backed up balance to the user's current balance\n"
                "Set: sets the backup balance as the user's new balance.\n"
                "You just type in 'set' or 'add' for this argument."
            )
        attachment_url = ctx.message.attachments[0].url
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    bank_data = await resp.json()
        except Exception as e:
            return await ctx.send(f"Error:{box(str(e), lang='python')}")

        for uid, balance in bank_data.items():
            member = ctx.guild.get_member(int(uid))
            if not member:
                continue
            if "a" in set_or_add.lower():
                try:
                    await bank.deposit_credits(member, balance)
                except BalanceTooHigh as e:
                    await bank.set_balance(member, e.max_balance)
            else:
                await bank.set_balance(member, balance)

        if "a" in set_or_add.lower():
            await ctx.send("Saved balances have been added to user's current balance!")
        else:
            await ctx.send("Balances have been restored from the backup!")
