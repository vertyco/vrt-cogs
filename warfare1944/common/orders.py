"""Orders a player gives to one of its squads: Advance, Suppressing Fire, Throw Grenade, Throw Smoke, Call Air Support,
Call Artillery and Smoke Rounds (showUnitControls F6:6199-6399, showFireSupportArea F6:6419-6507,
throwGrenadeCommand F6:8547-8555).

The page picks a squad, a button and, for the buttons that aim, a point; the Red bot runs `order` on that finished
request and refuses anything the INTEL panel would not have let the player do. Nothing here runs by itself: an order
is one call between two steps (common/battle.py), and what follows (the leader's throw, the strike clips, the
mortar's rounds) runs in the step order the other modules describe.
"""

import math
import typing as t

from .blasts import call_strike
from .boxes import Box
from .data import ORDER_COSTS, ORDER_UNLOCKS, UNITS
from .smoke import throw_smoke
from .squads import Soldier, fully_in_cover, leave_cover
from .teams import start_smoke_rounds, throw_grenade

if t.TYPE_CHECKING:
    from .battle import Battle, Side
    from .squads import Squad

# The range of a fire support order (specialAttackRange, F6:6419-6424): 2,500 wide and centred on the squad's leader,
# y 112 to 353 on the field. Left and right are measured from the leader's x; top and bottom are field y.
SUPPORT_BOX: Box = (-1250.0, 112.0, 1250.0, 353.0)
# The smoke grenade's range (specialAttackRange_smokeGrenade, sprite 1891): the box around the leader, x and y both
# measured from the leader.
SMOKE_BOX: Box = (-228.75, -107.35, 228.75, 107.4)
# The buttons that need no upgrade
FREE = frozenset({"advance", "suppress"})
# The orders that aim at a point, and the box each aims inside
AIMED = {"smoke": SMOKE_BOX, "smokeRounds": SUPPORT_BOX, "airSupport": SUPPORT_BOX, "artillery": SUPPORT_BOX}
SUPPRESS_SHOTS = 50  # unit.suppressionCounter = 50, F6:6374


def unlocked(side: "Side") -> frozenset[str]:
    """The buttons this side's squads may use. A campaign side owns them as upgrades (slots 12, 14, 16, 17 and 18,
    F6:6247-6299); a Custom Battle side has the screen's four toggles, which never include Smoke Rounds (W11)."""
    if side.campaign:
        gated = {kind for kind, slot in ORDER_UNLOCKS.items() if slot in side.upgrades}
    else:
        gated = set(side.custom_orders)
    return FREE | gated


def greyed(squad: "Squad", button: str) -> bool:
    """Whether the INTEL panel shows this button greyed for the squad now (updateSelectedUnitInfo F6:6538-6656).
    Advance needs the whole squad behind its cover; Throw Smoke and Smoke Rounds wait while the squad is moving. The
    other buttons are never greyed (Throw Grenade only needs a target, which `order` checks)."""
    if button == "advance":
        return not (squad.state == "entrench" and fully_in_cover(squad))
    if button in ("smoke", "smokeRounds"):
        return squad.state == "moving"
    return False


def number(value: t.Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def inside(box: Box, origin_x: float, origin_y: float, x: float, y: float) -> bool:
    left, top, right, bottom = box
    return origin_x + left <= x <= origin_x + right and origin_y + top <= y <= origin_y + bottom


def short(battle: "Battle", side: str, cost: int) -> bool:
    """Whether the side can't pay `cost`; the player is told what the order needs (F6:6492-6495)"""
    owner = battle.sides[side]
    if owner.rp >= cost:
        return False
    battle.event("msg", "rp", owner.index, cost)
    return True


def aimed(battle: "Battle", squad: "Squad", leader: Soldier, button: str, x: t.Any, y: t.Any) -> bool:
    """Throw Smoke, Smoke Rounds, Call Air Support and Call Artillery: the tapped point must be inside the button's
    box, and the side must hold the cost. The strikes and Smoke Rounds charge it now; Throw Smoke's 50 RP leaves when
    the grenade does (common/smoke.py `release`)."""
    if not number(x) or not number(y):
        return False
    box = AIMED[button]
    origin_y = leader.y if button == "smoke" else 0.0
    if not inside(box, leader.x, origin_y, x, y):
        return False
    cost = ORDER_COSTS[button]
    if short(battle, squad.side, cost):
        return False
    if button == "smoke":
        throw_smoke(battle, leader, x, y)
        return True
    battle.adjust_rp(squad.side, -cost)
    if button == "smokeRounds":
        start_smoke_rounds(battle, squad, x, y)
    else:
        call_strike(battle, button, x, y, squad.side)
    return True


def order(battle: "Battle", side: str, squad_id: int, button: str, x: t.Any = None, y: t.Any = None) -> bool:
    """Give `button` to the side's squad `squad_id`, aimed at (x, y) when the button aims. True when it was taken.
    Refused, with nothing changed: a side that is not a player, a battle that is over or paused, a squad that is not
    the side's or has no leader alive, a button the squad's kind does not have, a locked or greyed button, too few RP,
    and a point outside the button's box (spec 3.5b)."""
    owner = battle.sides.get(side)
    if owner is None or not owner.human or battle.state != "playing" or battle.paused:
        return False
    squad = next((found for found in owner.squads if found.id == squad_id), None)
    if squad is None or not isinstance(button, str):
        return False
    leader = squad.leader
    if not isinstance(leader, Soldier):
        return False
    if button not in UNITS[side].get(squad.kind, {}).get("orders", ()) or button not in owner.orders:
        return False
    if greyed(squad, button):
        return False
    if button == "advance":
        leave_cover(battle, squad)
    elif button == "suppress":
        squad.suppress = SUPPRESS_SHOTS
    elif button == "grenade":
        if owner.rp < ORDER_COSTS["grenade"]:
            return False
        return throw_grenade(battle, leader, squad.target if squad.target and squad.target.members else None)
    else:
        return aimed(battle, squad, leader, button, x, y)
    return True
