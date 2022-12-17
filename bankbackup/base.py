import json
from io import StringIO

import aiohttp
import discord
from redbot.core import bank, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import box


class BankBackup(commands.Cog):
    """
    Backup bank balances for all members of a guild
    """

    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="bankbackup")
    @commands.guildowner()
    async def backup(self, ctx):
        """Backup your guild's bank balances"""
        if await bank.is_global():
            return await ctx.send("Cannot make backup. Bank is set to global.")
        bank_data = {}
        for member in ctx.guild.members:
            bank_data[str(member.id)] = await bank.get_balance(member)
        raw = json.dumps(bank_data)
        file = discord.File(
            StringIO(raw), filename=f"{ctx.guild.name} bank backup.json"
        )
        await ctx.send("Here's your bank backup file!", file=file)

    @commands.command(name="bankrestore")
    @commands.guildowner()
    async def restore(self, ctx, set_or_add):
        """Restore your guild's bank balances
        Attach your backup file with this command.
        The set_or_add argument is if you want to add the saved bank balances to the user's current balance,
        or 'set' their balance to what is saved
        """
        if await bank.is_global():
            return await ctx.send(
                "Cannot restore backup because bank is set to global."
            )
        if not ctx.message.attachments:
            return await ctx.send(
                "Attach your backup file to the message when using this command."
            )
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
        user_ids = [str(member.id) for member in ctx.guild.members]
        for uid, balance in bank_data.items():
            if uid not in user_ids:
                continue
            member = ctx.guild.get_member(int(uid))
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
