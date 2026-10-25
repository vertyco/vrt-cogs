import asyncio
import logging
from decimal import Decimal

import aiohttp
import aiosqlite
import discord
from redbot.core.utils.chat_formatting import humanize_number

from .api import APIError

log = logging.getLogger("red.vrt.glassrelay.utils")

# Everything a GlassRelay call can raise
API_ERRORS = (APIError, aiohttp.ClientError, asyncio.TimeoutError)
PURCHASES_PER_PAGE = 10


def credits_for(amount: str, ratio: int) -> int:
    """Credits a payment is worth: amount paid * ratio, rounded down"""
    return int(Decimal(amount) * ratio)


def init_record(payment: dict, ratio: int) -> tuple[int, int]:
    """The buyer and credits init saves for a payment it marks, never paid out.

    A completed payment by a Discord buyer is filed under them at today's ratio, so purchase history
    and totals cover it. Anything else (a guest, or a payment that never completed) is saved as buyer 0,
    which the history screens skip.
    """
    buyer = payment.get("discord_uid")
    if not buyer or payment["status"] != "completed":
        return 0, 0
    return int(buyer), credits_for(payment["amount"], ratio)


def error_text(error: Exception, prefix: str) -> str:
    """What to tell the server owner when a GlassRelay call fails"""
    if not isinstance(error, APIError):
        log.warning("Couldn't reach GlassRelay", exc_info=error)
        return "I couldn't reach GlassRelay. Try again in a minute."
    log.info(f"GlassRelay call failed with status {error.status}")
    if error.status == 401:
        return (
            "GlassRelay turned the key away. It may have expired or been revoked, or the store was archived. "
            f"Set a new key with `{prefix}glassrelay key`."
        )
    if error.status == 403:
        return (
            "The key can't see your customers. "
            "Make a new key on your GlassRelay API keys page with **Include customer data** ticked."
        )
    if error.status == 404:
        return "Your GlassRelay store has nothing with that id."
    if error.status == 429:
        return f"GlassRelay is limiting how often this store can be checked. Try again in {error.retry_after} seconds."
    return f"GlassRelay ran into a problem (status {error.status}). Try again later."


def buyer_error_text(error: Exception) -> str:
    """What to tell a buyer when a GlassRelay call fails during a claim"""
    if not isinstance(error, APIError):
        log.warning("Couldn't reach GlassRelay", exc_info=error)
        return "I couldn't reach GlassRelay. Try again in a minute."
    log.info(f"GlassRelay call failed with status {error.status}")
    if error.status in (401, 403):
        return "This server's GlassRelay connection isn't working. Let a server admin know."
    if error.status == 429:
        return f"GlassRelay is busy right now. Try again in {error.retry_after} seconds."
    return f"GlassRelay ran into a problem (status {error.status}). Try again later."


def claim_text(template: str | None, member: discord.Member, amount: int, currency: str) -> str:
    """The thank-you text, using the server's own message if it set one"""
    if template is None:
        return f"{member.display_name}, you have claimed {humanize_number(amount)} {currency}!"
    params = {
        "mention": member.mention,
        "username": member.name,
        "displayname": member.display_name,
        "uid": member.id,
        "guild": member.guild.name,
        "creditsname": currency,
        "amount": humanize_number(amount),
    }
    try:
        return template.format(**params)
    except (AttributeError, IndexError, KeyError, ValueError) as e:
        # An unknown placeholder or a stray brace, so send the message as written
        log.warning(f"Bad claim message in {member.guild.id}: {e!r}")
        return template


def format_amount(amount: str | Decimal) -> str:
    return f"{Decimal(amount):,.2f}"


def buyer_pages(
    guild: discord.Guild,
    user_id: int,
    payments: list[aiosqlite.Row],
    currency: str,
    color: discord.Color,
) -> list[discord.Embed]:
    """One buyer's purchases, newest first, split into pages"""
    member = guild.get_member(user_id)
    name = f"{member.name} ({user_id})" if member else str(user_id)
    total = sum((Decimal(payment["amount"]) for payment in payments), Decimal(0))
    title = f"{len(payments)} purchases, {format_amount(total)} spent"
    pages = []
    for start in range(0, len(payments), PURCHASES_PER_PAGE):
        lines = [
            f"<t:{payment['paid_at']}:R> **{discord.utils.escape_markdown(payment['name'])}**: "
            f"{format_amount(payment['amount'])} for {humanize_number(payment['credits'])} {currency}"
            for payment in payments[start : start + PURCHASES_PER_PAGE]
        ]
        embed = discord.Embed(title=title, description="\n".join(lines), color=color)
        embed.set_author(name=f"{name}'s purchases", icon_url=member.display_avatar.url if member else None)
        pages.append(embed)
    return pages
