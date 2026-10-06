from __future__ import annotations

import typing as t
from dataclasses import dataclass, field

import discord
from discord import ui

from ..common import constants
from ..common.rock_session import RockSession, Spot

MEDALS: tuple[str, ...] = ("🥇", "🥈", "🥉")
REPAIR_HINT = '-# Run the "miner repair" command to repair your tools.'
ALSO_MINED_RESERVE = 60  # Text kept free for the "Also mined" heading and its "and N more" line
# Emoji, label and color of the claim button for each kind of spot
SPOT_BUTTONS: dict[str, tuple[str, str, discord.ButtonStyle]] = {
    "weak_spot": (constants.WEAK_SPOT_EMOJI, "Strike", discord.ButtonStyle.danger),
    "gem_vein": (constants.GEM_EMOJI, "Grab", discord.ButtonStyle.primary),
}


@dataclass(slots=True)
class MinerResult:
    """One paid miner's row on the results card."""

    name: str
    avatar_url: str | None
    role: str | None
    damage: int
    hits: int
    score: int
    overswings: int
    bonus_pct: float
    loot: dict[constants.Resource, int]
    tool_lines: list[str] = field(default_factory=list)


def rock_color(session: RockSession) -> discord.Color:
    """White at full HP, turning red as HP drops."""
    shade = max(0, min(255, int((255 / session.max_hp) * session.current_hp)))
    return discord.Color.from_rgb(255, shade, shade)


def hp_line(session: RockSession) -> str:
    ratio = max(0.0, session.current_hp / session.max_hp)
    filled = round(ratio * constants.HP_BAR_SEGMENTS)
    bar = constants.HP_BAR_FILLED * filled + constants.HP_BAR_EMPTY * (constants.HP_BAR_SEGMENTS - filled)
    return f"**HP** `{bar}` {round(100 * ratio, 1)}%"


def active_title(session: RockSession) -> str:
    """Modifier emojis, modifier names, rock name: '⚡ Electrified Large Rock'."""
    emojis = [mod.emoji for mod in session.modifiers]
    names = [mod.display_name for mod in session.modifiers]
    return " ".join([*emojis, *names, session.rocktype.display_name])


def short_title(session: RockSession) -> str:
    """Modifier emojis and rock name: '⚡ Large Rock'."""
    return " ".join([*(mod.emoji for mod in session.modifiers), session.rocktype.display_name])


def modifier_text(session: RockSession) -> str:
    if not session.modifiers:
        return "-# No modifiers"
    return "\n".join(f"{mod.emoji} **{mod.display_name}**\n-# {mod.description}" for mod in session.modifiers)


def synergy_line(synergy: dict[str, t.Any]) -> str | None:
    roles = " + ".join(name for name, __ in synergy["roles"])
    if not roles:
        return None
    if synergy["active"]:
        bonus = f"+{synergy['loot_bonus_pct'] * 100:.0f}% stone and iron"
        return f"-# 🤝 {roles}: {bonus}, -{synergy['durability_discount']} durability"
    return f"-# 🤝 {roles}: one more role activates the crew bonus"


def activity_text(session: RockSession, synergy: dict[str, t.Any]) -> str:
    lines = [f"-# {action.strip()}" for action in session.actions]
    crew = synergy_line(synergy)
    if crew:
        lines.append(crew)
    return "\n".join(lines)


def spot_text(spot: Spot) -> str:
    if spot.kind == "gem_vein":
        head = f"{constants.GEM_EMOJI} **Gem vein!** First click grabs {spot.gems} bonus gems."
    else:
        head = f"{constants.WEAK_SPOT_EMOJI} **Weak spot!** First click lands a big hit."
    return f"{head}\n-# Gone <t:{round(spot.closes_at)}:R>"


def spot_section(spot: Spot, button: ui.Button) -> ui.Section:
    """The open spot's line, with its claim button styled for the kind of spot."""
    button.emoji, button.label, button.style = SPOT_BUTTONS[spot.kind]
    return ui.Section(ui.TextDisplay(spot_text(spot)), accessory=button)


def clean_name(name: str) -> str:
    """A display name that can't ping anyone or break the formatting around it."""
    return discord.utils.escape_markdown(discord.utils.escape_mentions(name))


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def loot_text(loot: dict[constants.Resource, int]) -> str:
    return " ".join(f"+`{amount}` {constants.resource_emoji(resource)}" for resource, amount in loot.items())


def gallery(url: str) -> ui.MediaGallery:
    media = ui.MediaGallery()
    media.add_item(media=url)
    return media


def with_ping(session: RockSession, box: ui.Container) -> list[ui.Item]:
    return [ui.TextDisplay(session.ping), box] if session.ping else [box]


def text_size(item: ui.Item) -> int:
    return len(item.content) if isinstance(item, ui.TextDisplay) else item.content_length()


def layout_text(view: ui.LayoutView) -> str:
    """All text in a layout, used to skip redraws that would change nothing."""
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, ui.TextDisplay))


def build_active(
    session: RockSession,
    synergy: dict[str, t.Any],
    mine_button: ui.Button,
    inspect_button: ui.Button,
    spot_button: ui.Button | None = None,
) -> list[ui.Item]:
    """The live rock: title, picture, recent actions, open spot, HP with Mine, modifiers with Inspect."""
    box = ui.Container(accent_colour=rock_color(session))
    box.add_item(ui.TextDisplay(f"## {active_title(session)}"))
    # The picture uploaded with the message, never a link. Discord fetches a linked picture in the background after
    # each edit, then writes that edit's whole layout back when the fetch ends; a slow fetch from one redraw can land
    # after the results and put the live rock back on screen.
    box.add_item(gallery(f"attachment://{session.image_file}"))
    recent = activity_text(session, synergy)
    if recent:
        box.add_item(ui.TextDisplay(recent))
        box.add_item(ui.Separator())
    # Mine sits below the growing feed and the spot line: Discord pins the newest message to the bottom
    # of the chat, so only what is under the button can move it, and everything under it has a fixed height
    if session.spot_open and spot_button is not None:
        box.add_item(spot_section(session.spot, spot_button))
        box.add_item(ui.Separator())
    ends = round(session.end_time.timestamp()) if session.end_time else 0
    hp_text = f"{hp_line(session)}\n-# The mineshaft collapses <t:{ends}:R>"
    box.add_item(ui.Section(ui.TextDisplay(hp_text), accessory=mine_button))
    box.add_item(ui.Separator())
    box.add_item(ui.Section(ui.TextDisplay(modifier_text(session)), accessory=inspect_button))
    return with_ping(session, box)


def summary_line(session: RockSession, synergy: dict[str, t.Any], duration: float) -> str:
    count = len(session.participants)
    miners = f"{count} miner" if count == 1 else f"{count} miners"
    if not session.depleted:
        return f"-# `{session.current_hp}` HP left · {miners} split the collapse loot"
    line = f"-# Mined out in {format_duration(duration)} by {miners}"
    if synergy["active"]:
        roles = " + ".join(name for name, __ in synergy["roles"])
        line += f" · 🤝 {roles}, +{synergy['loot_bonus_pct'] * 100:.0f}% stone and iron"
    return line


def miner_row(rank: int, row: MinerResult) -> ui.Item:
    mark = MEDALS[rank - 1] if rank <= len(MEDALS) else f"{rank}."
    head = f"{mark} **{clean_name(row.name)}**" + (f" · {row.role}" if row.role else "")
    stats = (
        f"-# `{row.damage}` dmg in `{row.hits}` hits · score `{row.score}`"
        f" · overswings `{row.overswings}` · bonus `+{row.bonus_pct * 100:.0f}%`"
    )
    lines = [head, stats, loot_text(row.loot), *(f"-# {line}" for line in row.tool_lines)]
    text = ui.TextDisplay("\n".join(lines))
    if row.avatar_url:
        return ui.Section(text, accessory=ui.Thumbnail(media=row.avatar_url))
    return text


def also_mined(rows: list[MinerResult], first_rank: int, used: int) -> str:
    """Compact lines for miners past the full rows, cut off before the text budget runs out."""
    lines = ["**Also mined**"]
    for offset, row in enumerate(rows):
        line = f"-# {first_rank + offset}. **{clean_name(row.name)}** · `{row.damage}` dmg · {loot_text(row.loot)}"
        more = f"-# and {len(rows) - offset} more"
        if used + len("\n".join([*lines, line, more])) > constants.LAYOUT_TEXT_BUDGET:
            lines.append(more)
            break
        lines.append(line)
    return "\n".join(lines)


def result_image(session: RockSession) -> str:
    """File name of the results card's picture, uploaded with the results edit."""
    return session.rocktype.mined_out_file if session.depleted else constants.COLLAPSED_MINESHAFT_FILE


def build_results(
    session: RockSession,
    synergy: dict[str, t.Any],
    rows: list[MinerResult],
    duration: float,
) -> list[ui.Item]:
    """The finished rock: outcome, picture, summary, one row per paid miner, repair reminder."""
    outcome = "depleted" if session.depleted else "collapsed"
    image = f"attachment://{result_image(session)}"
    box = ui.Container(accent_colour=rock_color(session))
    box.add_item(ui.TextDisplay(f"## {short_title(session)} {outcome}"))
    box.add_item(gallery(image))
    box.add_item(ui.TextDisplay(summary_line(session, synergy, duration)))
    box.add_item(ui.Separator())
    used = len(session.ping or "") + box.content_length() + len(REPAIR_HINT)
    shown = 0
    for rank, row in enumerate(rows[: constants.RESULT_ROWS_MAX], start=1):
        item = miner_row(rank, row)
        if used + text_size(item) > constants.LAYOUT_TEXT_BUDGET - ALSO_MINED_RESERVE:
            break
        box.add_item(item)
        used += text_size(item)
        shown += 1
    if rows[shown:]:
        box.add_item(ui.TextDisplay(also_mined(rows[shown:], shown + 1, used)))
    box.add_item(ui.TextDisplay(REPAIR_HINT))
    return with_ping(session, box)


def build_nobody(session: RockSession) -> list[ui.Item]:
    """A rock nobody hit: one small line, no box, no buttons."""
    return [ui.TextDisplay(f"-# {short_title(session)}: the mineshaft collapsed before anyone mined it.")]
