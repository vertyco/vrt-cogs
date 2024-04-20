import asyncio
import logging
from pathlib import Path

from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from .abc import CompositeMetaClass
from .overrides import bank as custombank
from .overrides.bank import init
from .overrides.economy import PaydayOverride

log = logging.getLogger("red.vrt.bankevents")
_ = Translator("BankEvents", __file__)


class BankEvents(PaydayOverride, commands.Cog, metaclass=CompositeMetaClass):
    """
    Dispatches listener events for Red bank transactions and payday claims.
    - red_bank_set_balance
    - red_bank_transfer_credits
    - red_bank_wipe
    - red_bank_prune
    - red_bank_set_global
    - red_economy_payday_claim

    Shoutout to YamiKaitou for starting the work on this 2+ years ago with a PR.
    Maybe one day it will be merged into core.
    https://github.com/Cog-Creators/Red-DiscordBot/pull/5325
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "2.1.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        init(self.bot)
        # Original methods
        self.set_balance_coro = None
        self.transfer_credits_coro = None
        self.wipe_bank_coro = None
        self.bank_prune_coro = None
        self.set_global_coro = None
        self.payday_callback = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}\nContributors: YamiKaitou".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *args, **kwargs):
        return

    async def red_get_data_for_user(self, *args, **kwargs):
        return

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        # Save original methods
        self.set_balance_coro = bank.set_balance
        self.transfer_credits_coro = bank.transfer_credits
        self.wipe_bank_coro = bank.wipe_bank
        self.bank_prune_coro = bank.bank_prune
        self.set_global_coro = bank.set_global
        self.is_gobal_coro = bank.is_global

        # Wrap methods
        setattr(bank, "set_balance", custombank.set_balance)
        setattr(bank, "transfer_credits", custombank.transfer_credits)
        setattr(bank, "wipe_bank", custombank.wipe_bank)
        setattr(bank, "bank_prune", custombank.bank_prune)
        setattr(bank, "set_global", custombank.set_global)
        setattr(bank, "is_global", custombank.is_global)

        payday: commands.Command = self.bot.get_command("payday")
        if payday:
            self.payday_callback = payday.callback
            payday.callback = self.payday_override.callback

        log.info("Methods wrapped")

    async def cog_unload(self) -> None:
        if self.set_balance_coro is not None:
            setattr(bank, "set_balance", self.set_balance_coro)
        if self.transfer_credits_coro is not None:
            setattr(bank, "transfer_credits", self.transfer_credits_coro)
        if self.wipe_bank_coro is not None:
            setattr(bank, "wipe_bank", self.wipe_bank_coro)
        if self.bank_prune_coro is not None:
            setattr(bank, "bank_prune", self.bank_prune_coro)
        if self.set_global_coro is not None:
            setattr(bank, "set_global", self.set_global_coro)
        if self.is_gobal_coro is not None:
            setattr(bank, "is_global", self.is_gobal_coro)

        payday: commands.Command = self.bot.get_command("payday")
        if payday and self.payday_callback:
            payday.callback = self.payday_callback

        log.info("Methods restored")

    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        if cog.qualified_name != "Economy":
            return
        command: commands.Command = self.bot.get_command("payday")
        if command:
            self.payday_callback = command.callback
            command.callback = self.payday_override.callback

    @commands.command()
    @commands.is_owner()
    async def bankevents(self, ctx: commands.Context):
        """Get help using the BankEvents cog"""
        txt = _(
            "This cog allows you to add listeners for Red bank transactions in your own cogs "
            "by dispatching the following events:\n"
            "- red_bank_set_balance\n"
            "- red_bank_transfer_credits\n"
            "- red_bank_wipe\n"
            "- red_bank_prune\n"
            "- red_bank_set_global\n"
            "- red_economy_payday_claim\n"
            "Here are the implementations you can use in your cogs that will work when this cog is loaded:\n"
        )

        examples = Path(__file__).parent / "examples.txt"
        await ctx.send(txt)
        await ctx.send(box(examples.read_text(), "python"))
