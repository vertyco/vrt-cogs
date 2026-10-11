"""A player's career and the shop's rules, as the original's shop (frame_4) and arena list (frame_10) apply them.
Every action checks first, then changes the career in place and returns the info monitor's prompt. A refused action
raises ShopError and changes nothing"""

import re
import typing as t

from .arenas import ARENAS, FINAL, WEIGHT_CLASSES, Arena
from .parts import CHASSIS, PLATINGS, PRIZE_PLATING, PRIZE_WEAPON, Chassis, Plating, find, for_sale

START_CASH = 8200
MAX_ROBOTS = 5
COLORS = 8
COMPUTER_COLOR = 9
# The original's challenge mode starts a fresh level 1 career, whose team color is 1
CHALLENGE_COLOR = 1
NEW_NAME = "ROBOT NAME"
# The original's name box takes capitals, numbers and spaces, 17 at most
NAME = re.compile(r"[A-Z0-9 ]{0,17}")
# The original's win screen sets this level
BEATEN_LEVEL = 18

NO_ROBOTS = "YOU HAVE NO BOTS."
ALL_DISABLED = "ALL OF YOUR BOTS ARE DISABLED."
UNPLATED = "ONE OF YOUR ENABLED BOTS HAS NO PLATING. IT IS USELESS TO SEND AN UN-PROTECTED BOT INTO BATTLE. YOU NEED TO EITHER DISABLE IT, OR ATTACH PLATING TO IT."
CANT_FIGHT_BECAUSE = "YOU CANNOT ENGAGE IN BATTLE AT THE MOMENT BECAUSE:"

BOUGHT = "ITEM PURCHASE SUCCESSFUL!"
SOLD = "ITEM SOLD SUCCESSFULLY!"
MOUNTED = "ITEM MOUNTED SUCCESSFULLY!"
DISMOUNTED = "ITEM DISMOUNTED SUCCESSFULLY!"
ROBOT_SOLD = "BOT SOLD SUCCESSFULLY!"
ENABLED = "ROBOT NOW ENABLED!"
DISABLED = "ROBOT NOW DISABLED!"
# The color picker's own words (its sprite's script, not the shop frame's)
COLOR_CHANGED = "TEAM COLOR CHANGED!"

GONE = "THAT IS NOT THERE ANY MORE."
NOT_SOLD_HERE = "THE SHOP DOES NOT SELL THAT."
TOO_POOR = "YOU CANNOT AFFORD THAT."
TOO_MANY = "YOU ALREADY HAVE 5 ROBOTS."
WONT_FIT = "THAT CANNOT BE MOUNTED ON THIS ROBOT."
NOTHING_MOUNTED = "THIS ROBOT HAS NOTHING MOUNTED."
BAD_NAME = "NAMES USE CAPITALS, NUMBERS AND SPACES, 17 AT MOST."
BAD_COLOR = "THAT IS NOT A TEAM COLOR."
NO_TEAM = "START A CAREER AND BUILD A TEAM FIRST."
NOT_READY = "YOUR TEAM CANNOT FIGHT YET. CHECK IT IN THE SHOP."
ARENA_CLOSED = "YOU CANNOT FIGHT IN THAT ARENA RIGHT NOW."


class ShopError(Exception):
    """A request the original's greyed-out buttons wouldn't have allowed"""


def new_career() -> dict:
    return {"cash": START_CASH, "level": 1, "color": 1, "won": False, "robots": [], "inventory": [], "fee": 0}


def whole(value: t.Any) -> bool:
    # bool is an int in Python, but a page sending true for an index is a broken page
    return type(value) is int


def pick(items: t.Sequence, index: t.Any) -> t.Any:
    if not whole(index) or not 0 <= index < len(items):
        raise ShopError(GONE)
    return items[index]


def robot_load(robot: dict) -> int:
    """The chassis's own weight counts toward its load, as in the original"""
    names = (robot["chassis"], robot["plating"], robot["weapon"])
    return sum(find(name).weight for name in names if name)


def team_weight(career: dict) -> int:
    return sum(robot_load(robot) for robot in career["robots"] if robot["enabled"])


def problems(career: dict) -> list[str]:
    robots = career["robots"]
    enabled = [robot for robot in robots if robot["enabled"]]
    found = []
    if not robots:
        found.append(NO_ROBOTS)
    if robots and not enabled:
        found.append(ALL_DISABLED)
    if any(robot["plating"] is None for robot in enabled):
        found.append(UNPLATED)
    return found


def can_mount(robot: dict, name: str) -> bool:
    if find(name).weight > CHASSIS[robot["chassis"]].max_load - robot_load(robot):
        return False
    if name in PLATINGS:
        return robot["plating"] is None
    return robot["plating"] is not None and robot["weapon"] is None


def kind_of(part: t.Any) -> str | None:
    if isinstance(part, Chassis):
        return "chassis"
    if isinstance(part, Plating):
        return "plating"
    return "weapon" if part is not None else None


def buy(career: dict, name: t.Any) -> str:
    part = find(name) if isinstance(name, str) else None
    kind = kind_of(part)
    if kind is None or part not in for_sale(kind, career["level"]):
        raise ShopError(NOT_SOLD_HERE)
    if part.cost > career["cash"]:
        raise ShopError(TOO_POOR)
    if kind == "chassis":
        if len(career["robots"]) >= MAX_ROBOTS:
            raise ShopError(TOO_MANY)
        career["robots"].append(
            {"name": NEW_NAME, "chassis": part.name, "plating": None, "weapon": None, "enabled": True}
        )
    else:
        career["inventory"].append(part.name)
    career["cash"] -= part.cost
    return BOUGHT


def sell(career: dict, item: t.Any) -> str:
    name = pick(career["inventory"], item)
    career["cash"] += find(name).cost // 2
    del career["inventory"][item]
    return SOLD


def mount(career: dict, robot: t.Any, item: t.Any) -> str:
    target = pick(career["robots"], robot)
    name = pick(career["inventory"], item)
    if not can_mount(target, name):
        raise ShopError(WONT_FIT)
    target["plating" if name in PLATINGS else "weapon"] = name
    del career["inventory"][item]
    return MOUNTED


def dismount(career: dict, robot: t.Any) -> str:
    target = pick(career["robots"], robot)
    slot = "weapon" if target["weapon"] else "plating" if target["plating"] else None
    if slot is None:
        raise ShopError(NOTHING_MOUNTED)
    career["inventory"].append(target[slot])
    target[slot] = None
    return DISMOUNTED


def sell_robot(career: dict, robot: t.Any) -> str:
    target = pick(career["robots"], robot)
    names = (target["chassis"], target["plating"], target["weapon"])
    career["cash"] += sum(find(name).cost // 2 for name in names if name)
    del career["robots"][robot]
    return ROBOT_SOLD


def toggle(career: dict, robot: t.Any) -> str:
    target = pick(career["robots"], robot)
    target["enabled"] = not target["enabled"]
    return ENABLED if target["enabled"] else DISABLED


def rename(career: dict, robot: t.Any, name: t.Any) -> str:
    target = pick(career["robots"], robot)
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ShopError(BAD_NAME)
    target["name"] = name
    return ""


def set_color(career: dict, color: t.Any) -> str:
    if not whole(color) or not 1 <= color <= COLORS:
        raise ShopError(BAD_COLOR)
    career["color"] = color
    return COLOR_CHANGED


def arena_status(career: dict, arena: Arena) -> str:
    """What the arena list shows: good, locked, poor (can't pay the fee), bad (team too heavy) or both"""
    if career["level"] < arena.level:
        return "locked"
    heavy = team_weight(career) > WEIGHT_CLASSES[arena.weight_class]
    poor = arena.fee > career["cash"]
    if heavy and poor:
        return "both"
    if heavy:
        return "bad"
    return "poor" if poor else "good"


def enter_arena(career: dict, index: t.Any) -> Arena:
    """Pays the entry fee and holds it, so a battle stopped before it ends can give it back"""
    arena = pick(ARENAS, index)
    if problems(career) or arena_status(career, arena) != "good":
        raise ShopError(ARENA_CLOSED)
    career["cash"] -= arena.fee
    career["fee"] = arena.fee
    return arena


def finish_arena(career: dict, arena: Arena, won: bool) -> bool:
    """The battle's result. True when this win beat the game: the first time a career reaches the final's level"""
    career["fee"] = 0
    if not won:
        return False
    career["cash"] += arena.prize
    career["level"] = max(career["level"], arena.win_level)
    if career["won"] or career["level"] < FINAL.win_level:
        return False
    career["won"] = True
    career["inventory"] += [PRIZE_WEAPON, PRIZE_PLATING]
    career["level"] = BEATEN_LEVEL
    return True


def refund(career: dict) -> None:
    career["cash"] += career.get("fee", 0)
    career["fee"] = 0


def team(career: dict) -> list[dict]:
    keys = ("name", "chassis", "plating", "weapon")
    return [{key: robot[key] for key in keys} for robot in career["robots"] if robot["enabled"]]


def fight_problem(career: dict | None, weight: str | None) -> str | None:
    """Why this career can't take its team into a PvP fight with this weight limit, or None"""
    if career is None:
        return NO_TEAM
    if problems(career):
        return NOT_READY
    if weight is not None and team_weight(career) > WEIGHT_CLASSES[weight]:
        return f"YOUR TEAM WEIGHS {team_weight(career)}, OVER THE {weight} LIMIT OF {WEIGHT_CLASSES[weight]}."
    return None


def view(career: dict | None) -> dict | None:
    if career is None:
        return None
    robots = [
        {**robot, "load": robot_load(robot), "max": CHASSIS[robot["chassis"]].max_load} for robot in career["robots"]
    ]
    return {
        "cash": career["cash"],
        "level": career["level"],
        "color": career["color"],
        "won": career["won"],
        "robots": robots,
        "inventory": list(career["inventory"]),
        "weight": team_weight(career),
        "problems": problems(career),
        "arenas": [arena_status(career, arena) for arena in ARENAS],
    }


def pair(value: t.Any, first: type, second: type) -> bool:
    return isinstance(value, list) and len(value) == 2 and type(value[0]) is first and type(value[1]) is second


ONE_INDEX = {"sell": sell, "dismount": dismount, "sellRobot": sell_robot, "toggle": toggle, "color": set_color}


def action(kind: str, value: t.Any) -> t.Callable[[dict], str] | None:
    """The shop action a page's message asks for, or None when the message isn't a well-formed one"""
    if kind == "buy" and isinstance(value, str):
        return lambda career: buy(career, value)
    if kind in ONE_INDEX and whole(value):
        return lambda career: ONE_INDEX[kind](career, value)
    if kind == "mount" and pair(value, int, int):
        return lambda career: mount(career, value[0], value[1])
    if kind == "rename" and pair(value, int, str):
        return lambda career: rename(career, value[0], value[1])
    return None
