import asyncio
from datetime import datetime, timezone
from pathlib import Path

from redbot.core import Config, bank, commands, errors

DAILY_LIMIT = 100


class ClickCounter(commands.Cog):
    """Click a button, earn a credit"""

    def __init__(self, bot):
        self.bot = bot
        # Pick your own random number for identifier, so your data never mixes with another cog's
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.register_member(day="", clicks=0)
        self.lock = asyncio.Lock()

    async def activityhub_game(self) -> dict:
        return {
            "key": "clickcounter",
            "name": "Click Counter",
            "description": "One click, one credit",
            "web_dir": Path(__file__).parent / "web",
            "actions": {"click": self.click},
            # The oldest ActivityHub this game works with
            "requires": "0.8.0",
        }

    async def click(self, ctx, data: dict) -> dict:
        if ctx.guild is None:
            return {"error": "Open this in a server to earn credits."}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Fast clicks arrive together; the lock stops two of them reading the same count
        async with self.lock:
            ledger = self.config.member(ctx.author)
            clicks = await ledger.clicks() if await ledger.day() == today else 0
            if clicks >= DAILY_LIMIT:
                return {"error": "That's all the clicks for today. Come back tomorrow!"}
            try:
                await bank.deposit_credits(ctx.author, 1)
            except errors.BalanceTooHigh:
                return {"error": "Your balance is already at this server's maximum."}
            await ledger.day.set(today)
            await ledger.clicks.set(clicks + 1)
        return {"clicks": clicks + 1, "balance": await bank.get_balance(ctx.author)}

    async def red_delete_data_for_user(self, *, requester, user_id):
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
