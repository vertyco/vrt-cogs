"""Hit boxes. Flash compares two clips' boxes with `hitTest`; the blasts and the gas clouds do the same here."""

import typing as t

from . import anims

if t.TYPE_CHECKING:
    from .squads import Soldier, Tank

Box = tuple[float, float, float, float]


def member_box(member: "Soldier | Tank") -> Box:
    """A soldier's or tank's `collision` child on the field: scaled by its size, and for a German the size's width is
    replaced by the mirror (F5:1156, 1233)"""
    left, top, right, bottom = anims.BOXES["tank" if member.type == "tankMarkIV" else "soldier"]
    if member.squad.side == "british":
        left, right = left * member.scale, right * member.scale
    else:
        left, right = -right, -left
    top, bottom = top * member.scale, bottom * member.scale
    return (member.x + left, member.y + top, member.x + right, member.y + bottom)


def overlap(a: Box, b: Box) -> bool:
    """hitTest of two clips: their boxes on the field overlap"""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]
