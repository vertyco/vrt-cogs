"""The embeds the chat commands post, built from the same facts the page shows"""

import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

from ..common.catalog import BASIC_COLOR, COLORS
from ..common.money import fmt_seconds

_ = Translator("Casino", __file__)


def tiers_explained() -> str:
    return _(
        "Memberships are given automatically to players who meet their requirements. A player who meets several "
        "gets the one with the highest access level. A membership given by hand stays until it is revoked."
    )


def color_of(name: str) -> int:
    return COLORS.get(name, BASIC_COLOR)


def money(amount) -> str:
    return humanize_number(amount) if amount is not None else "-"


def yes_no(value: bool) -> str:
    return _("yes") if value else _("no")


def stats_embed(stats: dict, casino_name: str) -> discord.Embed:
    perks = _(
        "Membership: {name}\nAccess level: {access}\nCooldown reduction: {reduction}\nBonus multiplier: {bonus}x"
    ).format(
        name=stats["membership"]["name"],
        access=stats["access"],
        reduction=fmt_seconds(stats["reduction"]),
        bonus=stats["bonus"],
    )
    if stats["pending"]:
        perks += "\n" + _("Held winnings: {amount}").format(amount=money(stats["pending"]))
    rows = [f"{_('Game'):<18}{_('Played'):>7}{_('Won'):>6}  {_('Ready')}"]
    for game in stats["games"]:
        ready = _("Ready to play!") if game["ready_in"] <= 0 else fmt_seconds(game["ready_in"])
        rows.append(f"{game['name']:<18}{game['played']:>7}{game['won']:>6}  {ready}")
    embed = discord.Embed(
        title=_("{name} Casino").format(name=casino_name),
        description=perks,
        color=color_of(stats["membership"]["color"]),
    )
    embed.set_author(name=stats["name"], icon_url=stats["avatar"])
    embed.add_field(name=_("Games"), value=box("\n".join(rows), lang="md"), inline=False)
    embed.set_footer(text=_("Wins don't count pushes or surrenders."))
    return embed


def info_embed(info: dict) -> discord.Embed:
    header = (_("Game"), _("On"), _("Access"), _("Min"), _("Max"), _("Payout"), _("Cooldown"))
    rows = ["{:<18}{:<4}{:>6}{:>8}{:>8}{:>8}  {}".format(*header)]
    for game in info["games"].values():
        payout = f"{game['multiplier']}x" if game["multiplier"] is not None else "-"
        rows.append(
            f"{game['name']:<18}{yes_no(game['open']):<4}{game['access']:>6}"
            f"{money(game['min']):>8}{money(game['max']):>8}{payout:>8}  {fmt_seconds(game['cooldown'])}"
        )
    casino = _("Open: {open}\nMode: {mode}\nPayout limit: {limit}").format(
        open=yes_no(info["open"]),
        mode=_("global") if info["global"] else _("this server"),
        limit=money(info["limit_amount"]) if info["limit_on"] else _("off"),
    )
    embed = discord.Embed(title=_("{name} Casino").format(name=info["name"]), description=casino, color=0x0B4424)
    embed.add_field(name=_("Games"), value=box("\n".join(rows)), inline=False)
    return embed


def tier_embed(tier: dict) -> discord.Embed:
    perks = _("Access level: {access}\nCooldown reduction: {reduction}\nBonus multiplier: {bonus}x\nColor: {color}")
    perks = perks.format(
        access=tier["access"], reduction=fmt_seconds(tier["reduction"]), bonus=tier["bonus"], color=tier["color"]
    )
    needs = []
    if tier["req_credits"]:
        needs.append(_("Credits: {amount}").format(amount=money(tier["req_credits"])))
    if tier["req_role_id"]:
        needs.append(_("Role: {role}").format(role=tier["req_role"] or tier["req_role_id"]))
    if tier["req_days"]:
        needs.append(_("Days: {days}").format(days=tier["req_days"]))
    embed = discord.Embed(title=tier["name"], description=perks, color=color_of(tier["color"]))
    embed.add_field(name=_("Playable games"), value="\n".join(tier["games"]) or _("None"))
    embed.add_field(name=_("Requirements"), value="\n".join(needs) or _("None: open to everyone"))
    embed.set_footer(text=tiers_explained())
    return embed
