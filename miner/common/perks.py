from __future__ import annotations

import typing as t
from dataclasses import dataclass

from . import constants

LOCKED_TEXT = "Perks unlock at the Iron Pickaxe."
Pending = tuple[t.Literal["add", "remove"], str]


@dataclass(frozen=True, slots=True)
class Loadout:
    """What the Mine button needs about a player's pickaxe, cached between clicks."""

    tool: constants.ToolName
    perks: frozenset[str] = frozenset()


def owned_perks(keys: t.Iterable[str] | None) -> list[str]:
    """Known perk keys from a saved list, in PERKS order. Keys the code no longer knows are dropped."""
    have = set(keys or ())
    return [key for key in constants.PERKS if key in have]


def next_cost(owned: int) -> dict[constants.Resource, int] | None:
    """Price of the next perk for a pickaxe holding `owned` perks, or None past the last price."""
    if owned < len(constants.PERK_COSTS):
        return constants.PERK_COSTS[owned]
    return None


def missing_resources(player: t.Any, cost: dict[constants.Resource, int]) -> dict[constants.Resource, int]:
    """How much of each resource the player is short of `cost`."""
    short = {resource: amount - (getattr(player, resource, 0) or 0) for resource, amount in cost.items()}
    return {resource: amount for resource, amount in short.items() if amount > 0}


def cost_text(cost: dict[constants.Resource, int]) -> str:
    return " ".join(f"{constants.resource_emoji(resource)} `{amount:,}`" for resource, amount in cost.items())


def perk_name(key: str) -> str:
    perk = constants.PERKS[key]
    return f"{perk.emoji} {perk.display_name}"


def summary(owned: list[str]) -> str:
    return ", ".join(perk_name(key) for key in owned)


def buy_problem(player: t.Any, key: str) -> str | None:
    """Why `player` cannot buy perk `key` right now, or None when they can."""
    tool = constants.TOOLS[player.tool]
    owned = owned_perks(player.perks)
    if not tool.perk_slots:
        return LOCKED_TEXT
    if key in owned:
        return f"You already have {perk_name(key)}."
    if len(owned) >= tool.perk_slots:
        return f"Your {tool.display_name} has no free perk slot."
    missing = missing_resources(player, next_cost(len(owned)))
    if missing:
        return f"You need {cost_text(missing)} more to add {perk_name(key)}."
    return None


def header_text(tool: constants.ToolTier, owned: list[str]) -> str:
    """The top of the perk panel."""
    lines = ["## Pickaxe Perks"]
    if tool.perk_slots:
        lines.append(f"{tool.display_name} · {len(owned)}/{tool.perk_slots} slots used")
    else:
        lines.append(tool.display_name)
    lines.append(
        "-# Perks stay through upgrades and repairs. If your pickaxe shatters or wears out, its perks are lost."
    )
    return "\n".join(lines)


def list_text(owned: list[str]) -> str:
    """One line per perk, owned ones ticked."""
    return "\n".join(
        f"{'✅' if key in owned else '▫️'} {perk.emoji} **{perk.display_name}**: {perk.description}"
        for key, perk in constants.PERKS.items()
    )


def footer_text(player: t.Any, pending: Pending | None) -> str:
    """The line above the panel's controls: the next price, or the confirm question."""
    tool = constants.TOOLS[player.tool]
    owned = owned_perks(player.perks)
    if not tool.perk_slots:
        return LOCKED_TEXT
    if pending:
        action, key = pending
        if action == "remove":
            return f"Remove {perk_name(key)}? You get nothing back."
        return buy_problem(player, key) or f"Add {perk_name(key)} for {cost_text(next_cost(len(owned)))}?"
    if len(owned) >= tool.perk_slots:
        return "Every perk slot is full. Remove a perk to make room for another."
    return f"Next perk costs {cost_text(next_cost(len(owned)))}"


def inventory_line(tool: constants.ToolTier, owned: list[str]) -> str | None:
    """The Perks line on the inventory, or None for pickaxes that hold no perks."""
    if not tool.perk_slots:
        return None
    return f"Perks ({len(owned)}/{tool.perk_slots}): {summary(owned) or 'none yet'}"


def upgrade_notes(current: constants.ToolTier, upgraded: constants.ToolTier, owned: list[str]) -> list[str]:
    """Extra lines for the upgrade confirm embed."""
    notes: list[str] = []
    if owned:
        notes.append("Your perks come with you.")
    if upgraded.perk_slots > current.perk_slots:
        notes.append("Opens a new perk slot.")
    return notes


def slots_text() -> str:
    """Perk slots per pickaxe, e.g. "Iron 1, Steel 1, Carbide 2, Diamond 3"."""
    return ", ".join(
        f"{tool.display_name.removesuffix(' Pickaxe')} {tool.perk_slots}"
        for tool in constants.TOOLS.values()
        if tool.perk_slots
    )
