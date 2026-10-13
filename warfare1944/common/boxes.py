"""Hit boxes. Flash compares two clips' boxes with `hitTest`; the blasts do the same here."""

import typing as t

from . import anims

if t.TYPE_CHECKING:
    from .squads import Soldier, Tank

Box = tuple[float, float, float, float]
# The collision child each member type carries: the tank (sprite 913) and the bunker (sprite 929); every soldier
# type carries the soldier's (sprite 666)
MEMBER_BOX = {"tankMarkIV": "tank", "bunkerBase": "bunker"}


def member_box(member: "Soldier | Tank") -> Box:
    """A soldier's, tank's or bunker's `collision` child on the field, scaled by its size. A German is mirrored and
    keeps its size (`_xscale = -_xscale`, F6:1754)"""
    left, top, right, bottom = anims.BOXES[MEMBER_BOX.get(member.type, "soldier")]
    left, right = left * member.scale, right * member.scale
    if member.squad.side != "british":
        left, right = -right, -left
    top, bottom = top * member.scale, bottom * member.scale
    return (member.x + left, member.y + top, member.x + right, member.y + bottom)


def overlap(a: Box, b: Box) -> bool:
    """hitTest of two clips: their boxes on the field overlap"""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]
