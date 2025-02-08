from datetime import datetime

import discord
from redbot.core.i18n import Translator

_ = Translator("Referrals", __file__)


def chunk(obj_list: list, chunk_size: int):
    for i in range(0, len(obj_list), chunk_size):
        yield obj_list[i : i + chunk_size]


def referral_embed(
    referrer: discord.Member,  # The member who referred the user
    referred: discord.Member,  # The member who was referred
    referrer_reward: int,  # Reward for person who referred the user
    referred_reward: int,  # Reward for the person who was referred
    currency: str,
):
    referrer_name = f"{referrer.name} ({referrer.id})"
    referred_name = f"{referred.name} ({referred.id})"
    embed = discord.Embed(color=discord.Color.green(), timestamp=datetime.now())
    embed.add_field(name=_("Referred User"), value=referred_name, inline=False)
    if referred_reward:
        embed.add_field(
            name=_("Referred Reward"),
            value=f"`{referred_reward}` {currency} -> {referred_name}",
            inline=False,
        )
    if referrer_reward:
        embed.add_field(
            name=_("Referrer Reward"),
            value=f"`{referrer_reward}` {currency} -> {referrer_name}",
            inline=False,
        )
    embed.set_author(name=_("Referral Claimed"), icon_url=referred.display_avatar)
    embed.set_footer(text=_("Referred by {}").format(referrer_name), icon_url=referrer.display_avatar)
    return embed


def referral_error(
    referrer: discord.Member,  # The member who referred the user
    referred: discord.Member,  # The member who was referred
    error: str,
):
    referrer_name = f"{referrer.name} ({referrer.id})"
    referred_name = f"{referred.name} ({referred.id})"
    embed = discord.Embed(color=discord.Color.red(), timestamp=datetime.now())
    embed.add_field(name=_("Referred User"), value=referred_name, inline=False)
    embed.add_field(
        name=_("Error"),
        value=error,
        inline=False,
    )
    embed.set_author(name=_("Referral Error"), icon_url=referred.display_avatar)
    embed.set_footer(text=_("Referred by {}").format(referrer_name), icon_url=referrer.display_avatar)
    return embed
