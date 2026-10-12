"""Warfare 1917's 18 campaign missions and the Custom Battle's tables.

Every mission is a plain `Mission`. The campaign rows are copied from the original's mission objects (F5:7385-7848,
`british_mapN` and `german_mapN`); the Custom Battle is built from the settings screen's rules (F5:6093-6567).
"""

import random
from dataclasses import dataclass, field

from .data import SIDES, SUPPORT_KINDS, UNIT_KINDS

CUSTOM_MORALE = 1000  # skirmishMap.friendlyMorale / enemyMorale, F5:6101-6102
CUSTOM_RATES = {"easy": (20, 30), "medium": (15, 25), "hard": (10, 20)}  # (squad rate, support rate), F5:6366-6381

# Map name -> (art export, field width, mine spot range). The widths are the map background's measured `_width`
# (the original reads `world.bg._width`); the range is `skirmishMap.mapWidth`, F5:6396, 6440, 6484.
CUSTOM_MAPS = {
    "short": ("skirmishMap_short", 1218.17, 800),
    "medium": ("skirmishMap_medium", 1599.9, 1300),
    "long": ("skirmishMap_long", 2068.9, 1800),
}

# Trench x positions by map and trench count, F5:6400-6524.
CUSTOM_TRENCHES = {
    "short": {
        1: [600],
        2: [300, 900],
        3: [300, 600, 900],
        4: [300, 500, 700, 900],
        5: [300, 450, 600, 750, 900],
    },
    "medium": {
        1: [750],
        2: [300, 1100],
        3: [300, 650, 1100],
        4: [200, 550, 850, 1100],
        5: [300, 500, 700, 900, 1100],
    },
    "long": {
        1: [1000],
        2: [300, 1700],
        3: [300, 1000, 1700],
        4: [300, 800, 1300, 1700],
        5: [300, 600, 900, 1300, 1700],
    },
}

# The four wire line positions by map and trench count (wire line n takes the nth), F5:6400-6524.
CUSTOM_WIRES = {
    "short": {
        1: [300, 750, 200, 950],
        2: [400, 700, 200, 1000],
        3: [450, 750, 200, 1000],
        4: [400, 800, 600, 1600],
        5: [520, 680, 375, 825],
    },
    "medium": {
        1: [400, 800, 200, 950],
        2: [400, 700, 200, 1000],
        3: [450, 900, 200, 1000],
        4: [400, 800, 600, 1600],
        5: [580, 780, 375, 825],
    },
    "long": {
        1: [800, 1200, 400, 1500],
        2: [450, 1300, 850, 1100],
        3: [450, 1500, 850, 1100],
        4: [400, 1500, 900, 1100],
        5: [400, 1500, 800, 1100],
    },
}

# Mines by setting: (spots each side draws, mines each side holds), F5:6526-6567.
CUSTOM_MINES = {"none": (0, 0), "few": (1, 5), "medium": (2, 12), "many": (4, 30)}


@dataclass
class Mission:
    """One battle's setup.

    side: the human side in a campaign, the opener's side in custom and versus.
    number: 1 to 9 in a campaign, None otherwise.
    section: the campaign map's section number (British missions 1 to 9, German missions 10 down to 2).
    art: the map's export name. width: the field's width (`world.bg._width`).
    morale: starting morale per side. trenches / wires: x positions in the original's order.
    mines: keyed by the side that laid them, as (spots, count). The British ones go off under German squads.
    units / supports: which deploy slots (UNIT_KINDS / SUPPORT_KINDS order) each side may use.
    cpu_squads / cpu_supports: the CPU's lists in its order; empty with no CPU side. cpu_rate / support_rate: the
    seconds between its squads and between its support calls.
    random_picks: the CPU draws from its lists at random instead of walking them (Custom Battle).
    new: the unit and support keys this mission unlocks, in the original's order.
    """

    side: str
    number: int | None
    title: str
    description: str
    section: int
    art: str
    width: float
    rain: bool
    morale: dict[str, int]
    trenches: list[int]
    wires: list[int]
    mines: dict[str, tuple[list[int], int]]
    units: dict[str, list[bool]]
    supports: dict[str, list[bool]]
    cpu_squads: list[str]
    cpu_supports: list[str]
    cpu_rate: int
    support_rate: int
    mood: str
    random_picks: bool = False
    new: list[str] = field(default_factory=list)


def slot_flags(kinds: tuple[str, ...], picked: tuple[str, ...] | list[str]) -> list[bool]:
    return [kind in picked for kind in kinds]


def other_side(side: str) -> str:
    return SIDES[1] if side == SIDES[0] else SIDES[0]


def campaign_mission(
    side: str,
    number: int,
    title: str,
    description: str,
    section: int,
    art: str,
    width: float,
    rain: bool,
    morale: tuple[int, int],
    trenches: list[int],
    wires: list[int],
    british_mines: tuple[list[int], int],
    german_mines: tuple[list[int], int],
    available: tuple[str, ...],
    new: tuple[str, ...],
    cpu_rate: int,
    cpu_squads: tuple[str, ...],
    cpu_supports: tuple[str, ...],
    support_rate: int,
    mood: str,
) -> Mission:
    """One campaign row. `morale` is (the human side's, the CPU's): friendlyMorale and enemyMorale."""
    foe = other_side(side)
    return Mission(
        side=side,
        number=number,
        title=title,
        description=description,
        section=section,
        art=art,
        width=width,
        rain=rain,
        morale={side: morale[0], foe: morale[1]},
        trenches=trenches,
        wires=wires,
        mines={"british": british_mines, "german": german_mines},
        units={side: slot_flags(UNIT_KINDS, available), foe: slot_flags(UNIT_KINDS, ())},
        supports={side: slot_flags(SUPPORT_KINDS, available), foe: slot_flags(SUPPORT_KINDS, ())},
        cpu_squads=list(cpu_squads),
        cpu_supports=list(cpu_supports),
        cpu_rate=cpu_rate,
        support_rate=support_rate,
        mood=mood,
        new=list(new),
    )


# Wire lines are laid only where the mission gives a position. German missions 3 and 4 name a second line but
# position only one (the second `wire1Pos` line replaces the first), and German 7 and 9 name a fourth without one.
CAMPAIGNS = {
    "british": [
        campaign_mission(  # F5:7385-7410
            "british",
            number=1,
            title="TO THE TRENCHES",
            description="The stretch of open ground beyond our trench should lead to a swift victory.",
            section=1,
            art="map_british_1",
            width=1216.15,
            rain=False,
            morale=(100, 35),
            trenches=[200],
            wires=[],
            british_mines=([], 0),
            german_mines=([], 0),
            available=("riflemen",),
            new=(),
            cpu_rate=12,
            cpu_squads=("riflemen", "riflemen", "riflemen", "assault"),
            cpu_supports=(),
            support_rate=20,
            mood="defensive",
        ),
        campaign_mission(  # F5:7411-7431
            "british",
            number=2,
            title="DOWNPOUR",
            description="The enemy is dug in here, use our assault teams to drive Fritz out!",
            section=2,
            art="map_british_2",
            width=1348.7,
            rain=True,
            morale=(80, 50),
            trenches=[300, 1048],
            wires=[],
            british_mines=([], 0),
            german_mines=([], 0),
            available=("riflemen", "assault", "mortar"),
            new=("assault", "mortar"),
            cpu_rate=12,
            cpu_squads=("machineGun", "riflemen", "riflemen", "assault", "riflemen"),
            cpu_supports=("mortar", "mortar"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7432-7452
            "british",
            number=3,
            title="TAKE COVER!",
            description="The rain has cleared but now it's raining shells. Fritz has started bombarding us.",
            section=3,
            art="map_british_3",
            width=1673.55,
            rain=False,
            morale=(90, 90),
            trenches=[290, 1360],
            wires=[800],
            british_mines=([], 0),
            german_mines=([], 0),
            available=("riflemen", "assault", "mortar", "machineGun"),
            new=("machineGun",),
            cpu_rate=15,
            cpu_squads=("machineGun", "riflemen", "riflemen", "assault", "riflemen", "riflemen", "riflemen"),
            cpu_supports=("mortar", "mortar"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7453-7478
            "british",
            number=4,
            title="NO MAN'S LAND",
            description="Fritz has started entrenching heavily. Wire and mines are deadly, be careful.",
            section=4,
            art="map_british_4",
            width=1679.83,
            rain=False,
            morale=(100, 100),
            trenches=[540, 1360],
            wires=[1150, 850],
            british_mines=([], 0),
            german_mines=([900, 960], 5),
            available=("riflemen", "assault", "machineGun", "mortar"),
            new=(),
            cpu_rate=15,
            cpu_squads=("machineGun", "riflemen", "riflemen", "riflemen", "assault", "sniper"),
            cpu_supports=("mortar", "mortar"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7479-7503
            "british",
            number=5,
            title="HEAVY GUNS",
            description="Our fire support is in place now. Hit them with everything we've got.",
            section=5,
            art="map_british_5",
            width=1628.22,
            rain=False,
            morale=(90, 90),
            trenches=[230, 800, 1380],
            wires=[660],
            british_mines=([400, 450], 10),
            german_mines=([900, 1000], 10),
            available=("riflemen", "assault", "machineGun", "mortar", "artillery", "sniper"),
            new=("artillery", "sniper"),
            cpu_rate=10,
            cpu_squads=("machineGun", "riflemen", "riflemen", "riflemen", "assault", "sniper"),
            cpu_supports=("mortar", "artillery"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7504-7529
            "british",
            number=6,
            title="YELLOW CROSS",
            description="Our fire support is in place now. Hit them with everything we've got.",
            section=6,
            art="map_british_6",
            width=1599.9,
            rain=False,
            morale=(90, 90),
            trenches=[230, 950, 1380],
            wires=[800, 1100],
            british_mines=([800, 850], 5),
            german_mines=([1100, 1100], 5),
            available=("riflemen", "assault", "machineGun", "mortar", "artillery", "sniper", "officer", "gas"),
            new=("officer", "gas"),
            cpu_rate=13,
            cpu_squads=("machineGun", "riflemen", "riflemen", "riflemen", "assault", "sniper", "officer"),
            cpu_supports=("mortar", "artillery", "gas"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7530-7556
            "british",
            number=7,
            title="LAND-SHIPS",
            description="Our fire support is in place now. Hit them with everything we've got.",
            section=7,
            art="map_british_7",
            width=2031.15,
            rain=True,
            morale=(80, 80),
            trenches=[],
            wires=[800, 1100],
            british_mines=([], 0),
            german_mines=([], 0),
            available=("riflemen", "assault", "machineGun", "mortar", "artillery", "sniper", "officer", "gas", "tank"),
            new=("tank",),
            cpu_rate=12,
            cpu_squads=("tank", "assault", "riflemen", "assault", "riflemen", "assault", "assault", "officer"),
            cpu_supports=("mortar", "artillery", "gas"),
            support_rate=25,
            mood="balanced",
        ),
        campaign_mission(  # F5:7557-7584
            "british",
            number=8,
            title="EXPLODING GROUND",
            description="There is a mess of trenches and mines between us and the German line.",
            section=8,
            art="map_british_8",
            width=2071.4,
            rain=False,
            morale=(70, 110),
            trenches=[410, 800, 1150, 1505],
            wires=[500, 950, 1250, 1400],
            british_mines=([], 0),
            german_mines=([1250, 1200], 10),
            available=(
                "riflemen",
                "assault",
                "machineGun",
                "mortar",
                "artillery",
                "sniper",
                "officer",
                "gas",
                "tank",
                "antiTank",
            ),
            new=("antiTank",),
            cpu_rate=12,
            cpu_squads=("tank", "assault", "assault", "riflemen", "riflemen", "assault"),
            cpu_supports=("mortar", "artillery", "gas"),
            support_rate=20,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7585-7612
            "british",
            number=9,
            title="THE LAST STAND",
            description="Take this ground and we have won this once and for all.",
            section=9,
            art="map_british_9",
            width=1593.9,
            rain=False,
            morale=(70, 160),
            trenches=[1130, 1376],
            wires=[400, 550, 750, 900],
            british_mines=([], 0),
            german_mines=([500, 800, 1000], 20),
            available=(
                "riflemen",
                "assault",
                "machineGun",
                "mortar",
                "artillery",
                "sniper",
                "officer",
                "gas",
                "tank",
                "antiTank",
            ),
            new=(),
            cpu_rate=10,
            cpu_squads=("assault", "riflemen", "assault", "tank", "sniper", "assault", "machineGun", "officer", "tank"),
            cpu_supports=("antiTank", "mortar", "artillery", "gas", "antiTank"),
            support_rate=25,
            mood="aggressive",
        ),
    ],
    "german": [
        campaign_mission(  # F5:7613-7637
            "german",
            number=1,
            title="FORWARD!",
            description="Make your way across this open field and take that trench.",
            section=10,
            art="map_german_1",
            width=1208,
            rain=True,
            morale=(150, 60),
            trenches=[300],
            wires=[500],
            british_mines=([450, 455], 4),
            german_mines=([1100, 1150], 5),
            available=("riflemen", "assault"),
            new=("assault",),
            cpu_rate=20,
            cpu_squads=("riflemen", "riflemen", "riflemen", "assault"),
            cpu_supports=(),
            support_rate=10,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7638-7662
            "german",
            number=2,
            title="TOMMY'S LONG RUN",
            description="Hold the line here, Tommy has a long way to come.",
            section=9,
            art="map_german_2",
            width=1430.05,
            rain=True,
            morale=(90, 110),
            trenches=[1050],
            wires=[850],
            british_mines=([], 1),
            german_mines=([700, 750], 10),
            available=("riflemen", "assault", "machineGun"),
            new=("machineGun",),
            cpu_rate=11,
            cpu_squads=("riflemen", "assault", "riflemen", "assault", "machineGun"),
            cpu_supports=("mortar", "mortar"),
            support_rate=20,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7663-7688
            "german",
            number=3,
            title="HEAVY DEFENCE",
            description="We have the advantage, stem the flow of attacks and force them to quit.",
            section=8,
            art="map_german_3",
            width=1599.05,
            rain=False,
            morale=(100, 100),
            trenches=[220, 1130, 1360],
            wires=[850],
            british_mines=([], 1),
            german_mines=([700, 750], 5),
            available=("riflemen", "assault", "machineGun", "officer"),
            new=("officer",),
            cpu_rate=10,
            cpu_squads=("riflemen", "assault", "officer", "riflemen", "assault", "machineGun"),
            cpu_supports=("mortar", "artillery"),
            support_rate=22,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7689-7714
            "german",
            number=4,
            title="CLOSE LINES",
            description="The lines here are tight. Be careful not to hit our own with mortars.",
            section=7,
            art="map_german_4",
            width=1599.05,
            rain=False,
            morale=(90, 100),
            trenches=[625, 950],
            wires=[850],
            british_mines=([300, 350], 5),
            german_mines=([700, 750], 5),
            available=("riflemen", "assault", "machineGun", "officer", "mortar"),
            new=("mortar",),
            cpu_rate=14,
            cpu_squads=("riflemen", "assault", "officer", "riflemen", "sniper", "assault", "machineGun"),
            cpu_supports=("mortar", "artillery"),
            support_rate=22,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7715-7740
            "german",
            number=5,
            title="IMPENETRABLE",
            description="Our two lines must not be broken!",
            section=6,
            art="map_german_5",
            width=2012.85,
            rain=False,
            morale=(80, 100),
            trenches=[350, 1345, 1642],
            wires=[500, 850],
            british_mines=([400, 450], 10),
            german_mines=([500, 750], 5),
            available=("riflemen", "assault", "machineGun", "officer", "mortar", "artillery"),
            new=("artillery",),
            cpu_rate=13,
            cpu_squads=("riflemen", "assault", "riflemen", "sniper", "assault", "officer", "machineGun"),
            cpu_supports=("mortar", "artillery", "gas"),
            support_rate=22,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7741-7766
            "german",
            number=6,
            title="GAINING GROUND",
            description="Our command has demanded that we take more ground.",
            section=5,
            art="map_german_6",
            width=1830.85,
            rain=False,
            morale=(80, 100),
            trenches=[220, 460, 1332],
            wires=[520, 850],
            british_mines=([650, 850, 950], 10),
            german_mines=([1500, 1550], 5),
            available=("riflemen", "assault", "machineGun", "officer", "mortar", "artillery", "sniper"),
            new=("sniper",),
            cpu_rate=10,
            cpu_squads=("riflemen", "assault", "riflemen", "sniper", "assault", "officer", "machineGun"),
            cpu_supports=("mortar", "artillery"),
            support_rate=25,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7767-7793
            "german",
            number=7,
            title="METAL GIANTS",
            description="The ground shakes. Distant rumbling.",
            section=4,
            art="map_german_7",
            width=2012.85,
            rain=False,
            morale=(80, 100),
            trenches=[1650],
            wires=[500, 900, 1300],
            british_mines=([650, 850, 950], 5),
            german_mines=([750, 1150], 10),
            available=(
                "riflemen",
                "assault",
                "machineGun",
                "officer",
                "mortar",
                "artillery",
                "sniper",
                "gas",
                "antiTank",
            ),
            new=("gas", "antiTank"),
            cpu_rate=13,
            cpu_squads=("assault", "tank", "riflemen", "officer", "machineGun", "assault", "assault", "riflemen"),
            cpu_supports=("mortar", "artillery"),
            support_rate=22,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7794-7821
            "german",
            number=8,
            title="CLASH OF TITANS",
            description="We have a response to the British Land Ships now.",
            section=3,
            art="map_german_8",
            width=2012.85,
            rain=True,
            morale=(80, 150),
            trenches=[],
            wires=[500, 900, 1300, 1700],
            british_mines=([450, 850, 1500], 15),
            german_mines=([750, 1150, 1400], 15),
            available=(
                "riflemen",
                "assault",
                "machineGun",
                "officer",
                "mortar",
                "artillery",
                "sniper",
                "tank",
                "antiTank",
                "gas",
            ),
            new=("tank",),
            cpu_rate=8,
            cpu_squads=("tank", "assault", "tank", "assault", "assault", "machineGun"),
            cpu_supports=("mortar", "artillery", "gas", "antiTank"),
            support_rate=22,
            mood="aggressive",
        ),
        campaign_mission(  # F5:7822-7848
            "german",
            number=9,
            title="THE LAST LINE",
            description="Hold off the Tommies here and we will have won.",
            section=2,
            art="map_german_9",
            width=1599.05,
            rain=False,
            morale=(80, 160),
            trenches=[1300],
            wires=[500, 900, 1000],
            british_mines=([], 0),
            german_mines=([750, 1150], 10),
            available=(
                "riflemen",
                "assault",
                "machineGun",
                "officer",
                "mortar",
                "artillery",
                "sniper",
                "tank",
                "gas",
                "antiTank",
            ),
            new=(),
            cpu_rate=8,
            cpu_squads=("tank", "assault", "assault", "assault", "assault"),
            cpu_supports=("artillery", "antiTank", "mortar", "antiTank", "gas"),
            support_rate=22,
            mood="aggressive",
        ),
    ],
}


def custom_mines(kind: str, spot_range: int, rng: random.Random) -> dict[str, tuple[list[int], int]]:
    """Random mine spots, `random(range) + 200` each, British spots drawn before German ones (F5:6526-6567)."""
    spots, count = CUSTOM_MINES.get(kind, CUSTOM_MINES["none"])
    british = [rng.randrange(spot_range) + 200 for _ in range(spots)]
    german = [rng.randrange(spot_range) + 200 for _ in range(spots)]
    return {"british": (british, count), "german": (german, count)}


def custom_mission(settings: dict, rng: random.Random, versus: bool) -> Mission:
    """The Custom Battle (or a versus game) from its settings.

    `rng` is the battle's own generator: the mine spots come from it, so a seed repeats the same battle. A versus
    game has no CPU side and no difficulty. A trench or wire count out of range counts as 0 (F5:6385-6393), and wire
    with no trenches uses the map's 1-trench positions.
    """
    side = settings["side"]
    foe = other_side(side)
    art, width, spot_range = CUSTOM_MAPS[settings["map"]]
    trench_count = settings["trenches"] if settings["trenches"] in range(1, 6) else 0
    wire_count = settings["wire"] if settings["wire"] in range(1, 5) else 0
    units = list(settings["units"])
    supports = list(settings["supports"])
    cpu_rate, support_rate = (0, 0) if versus else CUSTOM_RATES[settings["difficulty"]]
    none_units = [False] * len(UNIT_KINDS)
    none_supports = [False] * len(SUPPORT_KINDS)
    return Mission(
        side=side,
        number=None,
        title="SKIRMISH",
        description="",
        section=1,
        art=art,
        width=width,
        rain=False,
        morale={"british": CUSTOM_MORALE, "german": CUSTOM_MORALE},
        trenches=list(CUSTOM_TRENCHES[settings["map"]].get(trench_count, [])),
        wires=CUSTOM_WIRES[settings["map"]][trench_count or 1][:wire_count],
        mines=custom_mines(settings["mines"], spot_range, rng),
        units={side: units, foe: units if versus else none_units},
        supports={side: supports, foe: supports if versus else none_supports},
        cpu_squads=[] if versus else [kind for kind, on in zip(UNIT_KINDS, units) if on],
        cpu_supports=[] if versus else [kind for kind, on in zip(SUPPORT_KINDS, supports) if on],
        cpu_rate=cpu_rate,
        support_rate=support_rate,
        mood=settings["mood"],
        random_picks=not versus,
    )
