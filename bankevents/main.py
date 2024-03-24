import functools
import logging
import typing as t
from pathlib import Path

from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

log = logging.getLogger("red.vrt.bankevents")


class BankEvents(commands.Cog):
    """
    Dispatches listener events for Red bank transactions
    - bank_set_balance
    - bank_withdraw_credits
    - bank_deposit_credits
    - bank_transfer_credits
    """

    __author__ = "Vertyco#0117"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        # Original methods
        self.set_balance = None
        self.withdraw_credits = None
        self.deposit_credits = None
        self.transfer_credits = None

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *args, **kwargs):
        return

    async def red_get_data_for_user(self, *args, **kwargs):
        return

    async def cog_load(self) -> None:
        # Save original methods
        self.set_balance = bank.set_balance
        self.withdraw_credits = bank.withdraw_credits
        self.deposit_credits = bank.deposit_credits
        self.transfer_credits = bank.transfer_credits

        # Wrap methods
        setattr(bank, "set_balance", self.bank_wrapper(bank.set_balance, "bank_set_balance"))
        setattr(bank, "withdraw_credits", self.bank_wrapper(bank.withdraw_credits, "bank_withdraw_credits"))
        setattr(bank, "deposit_credits", self.bank_wrapper(bank.deposit_credits, "bank_deposit_credits"))
        setattr(bank, "transfer_credits", self.bank_wrapper(bank.transfer_credits, "bank_transfer_credits"))

        log.info("Bank methods wrapped")

    async def cog_unload(self) -> None:
        if self.set_balance is not None:
            setattr(bank, "set_balance", self.set_balance)
        if self.withdraw_credits is not None:
            setattr(bank, "withdraw_credits", self.withdraw_credits)
        if self.deposit_credits is not None:
            setattr(bank, "deposit_credits", self.deposit_credits)
        if self.transfer_credits is not None:
            setattr(bank, "transfer_credits", self.transfer_credits)

        log.info("Bank methods restored")

    def bank_wrapper(self, coro: t.Callable, event: str):
        async def wrapped(*args, **kwargs):
            self.bot.dispatch(event, *args, **kwargs)
            # log.debug(f"Dispatched {event} - args: {args}, kwargs: {kwargs}")
            return await coro(*args, **kwargs)

        functools.update_wrapper(wrapped, coro)
        return wrapped

    @commands.command()
    @commands.is_owner()
    async def bankevents(self, ctx: commands.Context):
        """Get help using the BankEvents cog"""
        examples = Path(__file__).parent / "examples.txt"
        txt = (
            "This cog allows you to add listeners for Red bank transactions in your own cogs "
            "by dispatching the following events:\n"
            "- bank_set_balance\n"
            "- bank_withdraw_credits\n"
            "- bank_deposit_credits\n"
            "- bank_transfer_credits\n"
            "Here are the implementations you can use in your cogs that will work when this cog is loaded:\n"
            f"{box(examples.read_text(), 'python')}"
        )
        return await ctx.send(txt)
