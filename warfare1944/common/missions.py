"""Warfare 1944's 16 campaign missions and the Custom Battle's nine maps.

Every mission is a plain `Mission`. The campaign rows are copied from the original's mission objects (`british_mapN`
and `german_mapN`, F6:11040-11614); the Custom Battle is built from its screen's picks (F6:8903-9478). The American
side is `british` in code and data, as in the original.
"""

from dataclasses import dataclass, field

from .data import SIDES, SUPPORT_KINDS, UNIT_KINDS

CUSTOM_MORALE = 500  # skirmishMap.friendlyMorale / enemyMorale, F6:8911-8912
CUSTOM_RATES = {"easy": (7, 50), "medium": (5, 40), "hard": (2, 30)}  # (squad rate, support rate), F6:9349-9363


@dataclass
class Mission:
    """One battle's setup.

    side: the human side in a campaign, the opener's side in custom and versus. number: 1 to 8 in a campaign, else None.
    title / description: the battle title and the map screen's briefing, as the original writes them.
    section: the campaign map section this mission lights (the same number on both sides).
    art / midground: the map's export and its strip exports (`midground_<art>1..3`, y 195, 275, 375).
    width: the field's width (`world.bg._width`). rain: the rain effect is on.
    morale / rp: per side; `rp` is both the start and the cap.
    covers: `(lane, x, kind)` in the original's order (lane 1's, then lane 2's, then lane 3's).
    wires: x of each wire line. mines: keyed by the side that laid them, as (spots, count).
    units: per side, 8 flags in UNIT_KINDS order (the slots that side may deploy; the CPU's are all off).
    orders: per side, the order buttons unlocked from the start (Custom Battle only; a campaign's come from upgrades).
    cpu_pool: the CPU's squad kinds, repeats kept (each entry is one thing it can draw).
    cpu_supports: its fire support list (artillery, airSupport, mortarAI). cpu_rate: seconds between its deploy tries
    (R). support_rate: slow ticks between its support calls (S). mood: aggressive, balanced, defensive or static.
    random_supports: the CPU draws its next support at random instead of walking the list (Custom Battle).
    bunker: (lane, x) of the CPU's bunker. prespawns: (lane, kind) squads the CPU gets free at the start.
    presets: (seconds, kind, lane) squads the CPU gets free at a fixed time.
    The bunker, the pre-placed squads and the presets all belong to the CPU's side.
    objective: "bunker", ("preset", index into `presets`) or None; wiping that squad out wins the battle.
    timed: (minutes, seconds) of a defend countdown, or None. time_bonus: seconds of the faster-win XP bonus.
    new: the unlock keys this mission brings, in the original's order.
    """

    side: str
    number: int | None
    title: str
    description: str
    section: int
    art: str
    midground: tuple[str, ...]
    width: float
    rain: bool
    morale: dict[str, int]
    rp: dict[str, int]
    covers: list[tuple[int, int, str]]
    wires: list[int]
    mines: dict[str, tuple[list[int], int]]
    units: dict[str, list[bool]]
    orders: dict[str, list[str]]
    cpu_pool: list[str]
    cpu_supports: list[str]
    cpu_rate: int
    support_rate: int
    mood: str
    bunker: tuple[int, int] | None = None
    prespawns: list[tuple[int, str]] = field(default_factory=list)
    presets: list[tuple[int, str, int]] = field(default_factory=list)
    objective: str | tuple[str, int] | None = None
    timed: tuple[int, int] | None = None
    time_bonus: int = 0
    random_supports: bool = False
    new: list[str] = field(default_factory=list)


@dataclass
class CustomMap:
    """One of the Custom Battle's nine maps. text is the line the screen shows when the map is picked."""

    title: str
    text: str
    art: str
    width: float
    covers: list[tuple[int, int, str]]
    no_tanks: bool


def slot_flags(kinds: tuple[str, ...], picked: tuple[str, ...] | list[str]) -> list[bool]:
    return [kind in picked for kind in kinds]


def other_side(side: str) -> str:
    return SIDES[1] if side == SIDES[0] else SIDES[0]


def strips(art: str, count: int) -> tuple[str, ...]:
    """The map's midground strip exports. American missions 2 and 3 have two (the third attach does nothing)."""
    return tuple(f"midground_{art}{n}" for n in range(1, count + 1))


def campaign_mission(
    side: str,
    number: int,
    title: str,
    description: str,
    art: str,
    width: float,
    rain: bool,
    morale: tuple[int, int],
    rp: tuple[int, int],
    covers: list[tuple[int, int, str]],
    units: tuple[str, ...],
    new: tuple[str, ...],
    cpu_pool: tuple[str, ...],
    cpu_supports: tuple[str, ...],
    cpu_rate: int,
    support_rate: int,
    mood: str,
    time_bonus: int,
    wires: list[int] | None = None,
    british_mines: tuple[list[int], int] = ([], 0),
    german_mines: tuple[list[int], int] = ([], 0),
    bunker: tuple[int, int] | None = None,
    prespawns: list[tuple[int, str]] | None = None,
    presets: list[tuple[int, str, int]] | None = None,
    objective: str | tuple[str, int] | None = None,
    timed: tuple[int, int] | None = None,
    strip_count: int = 3,
) -> Mission:
    """One campaign row. `morale` and `rp` are (the human side's, the CPU's): friendlyMorale / enemyMorale and
    resourcePointsPlayer / resourcePointsEnemy."""
    foe = other_side(side)
    return Mission(
        side=side,
        number=number,
        title=title,
        description=description,
        section=number,
        art=art,
        midground=strips(art, strip_count),
        width=width,
        rain=rain,
        morale={side: morale[0], foe: morale[1]},
        rp={side: rp[0], foe: rp[1]},
        covers=covers,
        wires=wires or [],
        mines={"british": british_mines, "german": german_mines},
        units={side: slot_flags(UNIT_KINDS, units), foe: slot_flags(UNIT_KINDS, ())},
        orders={side: [], foe: []},
        cpu_pool=list(cpu_pool),
        cpu_supports=list(cpu_supports),
        cpu_rate=cpu_rate,
        support_rate=support_rate,
        mood=mood,
        bunker=bunker,
        prespawns=prespawns or [],
        presets=presets or [],
        objective=objective,
        timed=timed,
        time_bonus=time_bonus,
        new=list(new),
    )


CAMPAIGNS = {
    "british": [
        campaign_mission(  # F6:11040-11087
            "british",
            number=1,
            title="BLOOD ON THE SAND",
            description="BRIEFING: The objective is the enemy emplacement at the end of this beach. Clear the lower defenses, then push your BAZOOKA TEAMS up to clear the bunker.",
            art="map_british_1",
            width=1599.95,
            rain=False,
            morale=(1500, 1000),
            rp=(800, 0),
            covers=[(1, 1140, "sandBagsUrban_german"), (3, 1140, "sandBagsUrban_german")],
            wires=[975],
            units=("riflemen", "assault", "bazooka"),
            new=("objective",),
            cpu_pool=(),
            cpu_supports=("artillery", "mortarAI"),
            cpu_rate=20,
            support_rate=15,
            mood="static",
            time_bonus=240,
            bunker=(2, 1420),
            prespawns=[(1, "riflemen"), (3, "riflemen")],
            objective="bunker",
        ),
        campaign_mission(  # F6:11088-11117
            "british",
            number=2,
            title="ON THE RAILS",
            description="BRIEFING: Follow the railway to the nearby village, clear any enemy resistance en route.",
            art="map_british_2",
            width=1216.75,
            rain=False,
            morale=(100, 90),
            rp=(500, 500),
            covers=[(1, 475, "barrels"), (2, 930, "sandBagsUrban_german"), (3, 495, "hedgerow")],
            units=("riflemen", "assault", "machineGun"),
            new=("machineGun", "conquer", "flanking"),
            cpu_pool=("assault", "riflemen", "riflemen"),
            cpu_supports=(),
            cpu_rate=15,
            support_rate=25,
            mood="static",
            time_bonus=180,
            prespawns=[(2, "machineGun")],
            strip_count=2,
        ),
        campaign_mission(  # F6:11118-11149
            "british",
            number=3,
            title="MUNITIONS",
            description="BRIEFING: At the end of the road is a small munitions dump just outside of our next objective. Hit it hard and fast from the flanks. Recon has reported mortar fire coming from the position so keep your men moving.",
            art="map_british_3",
            width=1597.95,
            rain=False,
            morale=(100, 100),
            rp=(500, 500),
            covers=[
                (1, 304, "stoneWall"),
                (1, 937, "woodFence"),
                (1, 1250, "barrels"),
                (2, 1050, "logPile"),
                (3, 304, "stoneWall"),
                (3, 937, "woodFenceOvergrown"),
                (3, 1300, "urban2"),
            ],
            units=("riflemen", "assault", "machineGun", "sniper", "officer"),
            new=("sniper", "officer"),
            cpu_pool=("assault", "riflemen", "riflemen", "riflemen", "machineGun"),
            cpu_supports=(),
            cpu_rate=14,
            support_rate=25,
            mood="aggressive",
            time_bonus=180,
            prespawns=[(3, "mortarTeam")],
            strip_count=2,
        ),
        campaign_mission(  # F6:11150-11189
            "british",
            number=4,
            title="ARMOR CONVOY",
            description="BRIEFING: The Germans are said to be moving their armor and infantry through this town. Use your Bazooka Teams to ambush the convoy and destroy the enemy armor.",
            art="map_british_4",
            width=1599.2,
            rain=False,
            morale=(150, 800),
            rp=(800, 300),
            covers=[
                (1, 450, "townWall"),
                (1, 850, "barrels"),
                (1, 1350, "sandBagsUrban_german"),
                (3, 310, "urban1"),
                (3, 590, "urban2"),
                (3, 720, "townWall"),
                (3, 1350, "sandBagsUrban_german"),
            ],
            units=("riflemen", "assault", "machineGun", "sniper", "bazooka", "officer"),
            new=("bazooka",),
            cpu_pool=("riflemen", "riflemen", "riflemen", "assault"),
            cpu_supports=(),
            cpu_rate=28,
            support_rate=25,
            mood="defensive",
            time_bonus=180,
            presets=[(32, "tank", 2), (107, "tank", 2), (187, "tank", 2)],
            objective=("preset", 2),
        ),
        campaign_mission(  # F6:11190-11220
            "british",
            number=5,
            title="HEDGEROWS",
            description="BRIEFING: These dense hedgerows are a nightmare to fight in, but we can use them to our advantage. Slip around the flanks and advance your line with support.",
            art="map_british_5",
            width=1599.95,
            rain=False,
            morale=(100, 120),
            rp=(600, 600),
            covers=[
                (1, 300, "sandBagsUrban"),
                (1, 650, "hedgerow"),
                (1, 900, "hedgerow"),
                (1, 1250, "woodFenceOvergrown"),
                (2, 1000, "barrels"),
                (3, 300, "townWall"),
                (3, 550, "hedgerow"),
                (3, 1350, "hedgerow"),
            ],
            units=("riflemen", "assault", "machineGun", "bazooka", "sniper", "mortarTeam", "officer"),
            new=("mortarTeam",),
            cpu_pool=("assault", "assault", "riflemen", "riflemen", "riflemen", "sniper", "machineGun"),
            cpu_supports=(),
            cpu_rate=11,
            support_rate=25,
            mood="aggressive",
            time_bonus=220,
            prespawns=[(3, "machineGun")],
        ),
        campaign_mission(  # F6:11221-11251
            "british",
            number=6,
            title="OPEN RANGE",
            description="BRIEFING: Armored Corps has come to the party. Recon reports enemy armor movement in these areas across the open fields. Make sure you keep our Shermans supported with infantry.",
            art="map_british_6",
            width=2012.1,
            rain=True,
            morale=(500, 500),
            rp=(800, 1200),
            covers=[],
            units=("riflemen", "assault", "machineGun", "bazooka", "sniper", "mortarTeam", "officer", "tank"),
            new=("tank",),
            cpu_pool=("assault", "riflemen", "tank", "tank", "tank", "tank", "bazooka", "bazooka"),
            cpu_supports=(),
            cpu_rate=9,
            support_rate=25,
            mood="aggressive",
            time_bonus=240,
        ),
        campaign_mission(  # F6:11252-11282
            "british",
            number=7,
            title="CLEAR THE WAY",
            description="BRIEFING: This town and outlying cemetary is littered with infantry and anti-tank. We need to clear a path for our armor. Control the cemetary, then move on the bunker at the edge of town. Expect enemy artillery.",
            art="map_british_7",
            width=2018.6,
            rain=False,
            morale=(100, 110),
            rp=(800, 800),
            covers=[
                (1, 920, "townWall"),
                (1, 1095, "headstones"),
                (1, 1360, "headstones"),
                (1, 1540, "townWall"),
                (2, 1105, "headstones"),
                (2, 1410, "headstones"),
                (2, 1745, "sandBagsUrban_german"),
                (3, 920, "townWall"),
                (3, 1095, "headstones"),
                (3, 1365, "headstones"),
                (3, 1540, "townWall"),
            ],
            units=("riflemen", "assault", "machineGun", "bazooka", "sniper", "mortarTeam", "officer"),
            new=(),
            cpu_pool=("assault", "riflemen", "riflemen", "officer", "mortarTeam", "sniper", "machineGun"),
            cpu_supports=("airSupport", "artillery"),
            cpu_rate=10,
            support_rate=80,
            mood="balanced",
            time_bonus=300,
        ),
        campaign_mission(  # F6:11283-11313
            "british",
            number=8,
            title="THE LAST STEP",
            description="BRIEFING: The Krauts have this town locked down. It's crawling with infantry and armor. Secure it and we'll have secured the region.",
            art="map_british_8",
            width=1943.7,
            rain=False,
            morale=(1500, 1500),
            rp=(800, 1800),
            covers=[(2, 410, "townWall"), (2, 820, "urban2"), (2, 1650, "urban1")],
            units=("riflemen", "assault", "machineGun", "bazooka", "sniper", "mortarTeam", "officer", "tank"),
            new=(),
            cpu_pool=(
                "assault",
                "riflemen",
                "bazooka",
                "bazooka",
                "mortarTeam",
                "sniper",
                "machineGun",
                "bazooka",
                "tank",
                "tank",
                "tank",
            ),
            cpu_supports=("airSupport", "mortarAI", "artillery"),
            cpu_rate=6,
            support_rate=20,
            mood="static",
            time_bonus=300,
            prespawns=[(3, "tank")],
        ),
    ],
    "german": [
        campaign_mission(  # F6:11314-11350
            "german",
            number=1,
            title="INVASION",
            description="BRIEFING: The Allies have mounted a huge offensive along the coast with assistance from their Navy. Hold this position to delay their attack! We must stop them here!",
            art="map_german_1",
            width=1280.9,
            rain=False,
            morale=(200, 200),
            rp=(800, 1000),
            covers=[(1, 945, "sandBags"), (2, 920, "sandBags"), (3, 945, "sandBags")],
            wires=[675],
            german_mines=([450], 5),
            units=("riflemen", "assault", "machineGun", "sniper"),
            new=(),
            cpu_pool=("assault", "riflemen", "riflemen", "bazooka"),
            cpu_supports=("mortarAI", "artillery"),
            cpu_rate=5,
            support_rate=40,
            mood="aggressive",
            time_bonus=100,
            timed=(2, 0),
        ),
        campaign_mission(  # F6:11351-11386
            "german",
            number=2,
            title="HIGH ROAD",
            description="BRIEFING: Delaying the enemy movement along this road is paramount to our defence in this region. Push them out of this area forcing them to find another route.",
            art="map_german_2",
            width=1615.9,
            rain=False,
            morale=(125, 125),
            rp=(600, 600),
            covers=[
                (1, 700, "barrels"),
                (2, 350, "hedgerow"),
                (2, 800, "hedgerow"),
                (2, 1150, "hedgerow"),
                (3, 375, "hedgerow"),
                (3, 1000, "hedgerow"),
            ],
            units=("riflemen", "assault", "machineGun"),
            new=("flanking",),
            cpu_pool=("assault", "riflemen", "riflemen", "machineGun"),
            cpu_supports=(),
            cpu_rate=5,
            support_rate=600,
            mood="aggressive",
            time_bonus=180,
        ),
        campaign_mission(  # F6:11387-11423
            "german",
            number=3,
            title="HOLD THE LINE",
            description="BRIEFING: Defend the entrance to this town. Our engineers need time for defensive emplacements to be setup within the town itself to stop the allies pushing their armor through here.",
            art="map_german_3",
            width=1602.95,
            rain=False,
            morale=(125, 125),
            rp=(800, 1100),
            covers=[
                (1, 1310, "urban1"),
                (1, 1200, "sandBagsUrban_german"),
                (1, 300, "hedgerow"),
                (1, 650, "hedgerow"),
                (2, 1150, "sandBagsUrban_german"),
                (3, 1310, "urban2"),
                (3, 1200, "sandBagsUrban_german"),
                (3, 300, "hedgerow"),
                (3, 650, "hedgerow"),
            ],
            wires=[1050],
            units=("riflemen", "assault", "machineGun", "sniper", "mortarTeam"),
            new=("mortarTeam",),
            cpu_pool=("assault", "riflemen", "riflemen", "machineGun", "sniper", "bazooka"),
            cpu_supports=("airSupport", "mortarAI"),
            cpu_rate=4,
            support_rate=40,
            mood="aggressive",
            time_bonus=200,
            timed=(3, 0),
        ),
        campaign_mission(  # F6:11424-11460
            "german",
            number=4,
            title="URBAN WARFARE",
            description="BRIEFING: This town is ours! Drive the Americans out, do not lose any ground to them or we are bound to fail. Use your officers to call any support you need.",
            art="map_german_4",
            width=1560.45,
            rain=False,
            morale=(125, 125),
            rp=(800, 1000),
            covers=[
                (1, 350, "barrels"),
                (1, 1150, "sandBagsUrban_german"),
                (2, 275, "townWall"),
                (2, 511, "townWall"),
                (2, 1300, "townWall"),
                (3, 550, "urban1"),
                (3, 800, "urban2"),
                (3, 1150, "sandBagsUrban_german"),
            ],
            units=("riflemen", "assault", "machineGun", "sniper", "mortarTeam", "officer"),
            new=("officer",),
            cpu_pool=("assault", "riflemen", "riflemen", "machineGun", "sniper", "bazooka", "mortarTeam"),
            cpu_supports=("airSupport", "artillery"),
            cpu_rate=4,
            support_rate=40,
            mood="aggressive",
            time_bonus=210,
        ),
        campaign_mission(  # F6:11461-11501
            "german",
            number=5,
            title="LINE OF COMMAND",
            description="BRIEFING: An American battalion and it's officers are planning to move through this town. We only have a handful of infantry to defend it. KILL the OFFICERS and the remaining troops should surrender out of fear.",
            art="map_german_5",
            width=1599.95,
            rain=False,
            morale=(125, 300),
            rp=(500, 800),
            covers=[
                (1, 275, "barrels"),
                (1, 1005, "rubble2"),
                (1, 1265, "townWall"),
                (3, 290, "urban2"),
                (3, 1015, "rubble1"),
                (3, 1272, "townWall"),
            ],
            units=("machineGun", "sniper", "riflemen", "assault", "officer"),
            new=(),
            cpu_pool=("assault", "riflemen", "riflemen"),
            cpu_supports=("mortarAI",),
            cpu_rate=4,
            support_rate=40,
            mood="aggressive",
            time_bonus=210,
            presets=[(27, "officer", 2), (67, "officer", 3), (137, "officer", 1)],
            objective=("preset", 2),
        ),
        campaign_mission(  # F6:11502-11538
            "german",
            number=6,
            title="COUNTER ATTACK",
            description="BRIEFING: After delaying the Americans through the town, they have found another route and are hitting it with full force. We have no armor to spare, but our anti-tank teams should be able to handle theirs.",
            art="map_german_6",
            width=2016.9,
            rain=True,
            morale=(450, 450),
            rp=(800, 1000),
            covers=[],
            units=("riflemen", "assault", "machineGun", "sniper", "mortarTeam", "officer", "bazooka"),
            new=("bazooka",),
            cpu_pool=(
                "assault",
                "riflemen",
                "riflemen",
                "machineGun",
                "sniper",
                "bazooka",
                "mortarTeam",
                "tank",
                "tank",
                "tank",
            ),
            cpu_supports=("airSupport", "mortarAI", "artillery"),
            cpu_rate=3,
            support_rate=30,
            mood="aggressive",
            time_bonus=210,
        ),
        campaign_mission(  # F6:11539-11576
            "german",
            number=7,
            title="OUTSKIRTS",
            description="BRIEFING: Push your armor into this town and decimate the Americans holding it.",
            art="map_german_7",
            width=2060.9,
            rain=False,
            morale=(250, 250),
            rp=(800, 1400),
            covers=[
                (1, 350, "sandBagsUrban"),
                (1, 700, "sandBagsUrban"),
                (1, 1200, "urban1"),
                (1, 1650, "hedgerow"),
                (3, 400, "sandBagsUrban"),
                (3, 590, "sandBagsUrban"),
                (3, 1100, "urban2"),
                (3, 1650, "hedgerow"),
            ],
            units=("riflemen", "assault", "machineGun", "sniper", "mortarTeam", "officer", "bazooka", "tank"),
            new=("tank",),
            cpu_pool=(
                "assault",
                "riflemen",
                "riflemen",
                "machineGun",
                "sniper",
                "bazooka",
                "bazooka",
                "bazooka",
                "mortarTeam",
                "tank",
                "tank",
                "tank",
            ),
            cpu_supports=("artillery",),
            cpu_rate=3,
            support_rate=60,
            mood="aggressive",
            time_bonus=210,
            prespawns=[(2, "tank")],
        ),
        campaign_mission(  # F6:11577-11614
            "german",
            number=8,
            title="LAST STOP",
            description="BRIEFING: Defence of this town is imperitive to slowing the advance of the allies. They will throw everything they have at you and you will do the same. To the last man!",
            art="map_german_8",
            width=2323.9,
            rain=False,
            morale=(800, 500),
            rp=(800, 1600),
            covers=[
                (1, 450, "barrels"),
                (1, 650, "urban2"),
                (1, 1500, "rubble1"),
                (1, 1950, "urban1"),
                (3, 450, "urban1"),
                (3, 1350, "rubble2"),
                (3, 1950, "barrels"),
            ],
            units=("riflemen", "assault", "machineGun", "sniper", "mortarTeam", "officer", "bazooka", "tank"),
            new=(),
            cpu_pool=(
                "assault",
                "riflemen",
                "riflemen",
                "machineGun",
                "sniper",
                "bazooka",
                "bazooka",
                "bazooka",
                "mortarTeam",
                "tank",
                "tank",
                "tank",
            ),
            cpu_supports=("airSupport", "mortarAI", "artillery"),
            cpu_rate=2,
            support_rate=40,
            mood="aggressive",
            time_bonus=300,
            prespawns=[(2, "tank")],
            timed=(4, 0),
        ),
    ],
}

CUSTOM_MAPS = {
    1: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - BEACH LANDING",
        text="BEACH LANDING: MEDIUM size beach landing. LIGHT COVER.",
        art="map_skirmish_1",
        width=1599.95,
        covers=[(1, 1140, "sandBagsUrban_german"), (3, 1140, "sandBagsUrban_german")],
        no_tanks=False,
    ),
    2: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - OPEN PLAINS",
        text="OPEN PLAINS: LONG open Map with NO COVER.",
        art="map_skirmish_2",
        width=2012.1,
        covers=[],
        no_tanks=False,
    ),
    3: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - DESERTED TOWN",
        text="DESERTED TOWN:  LONG open town Map with NO COVER.",
        art="map_skirmish_3",
        width=2060.9,
        covers=[],
        no_tanks=False,
    ),
    4: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - TOWN",
        text="TOWN: MEDIUM town Map. MEDIUM COVER. NO TANKS!",
        art="map_skirmish_4",
        width=1599.2,
        covers=[
            (1, 450, "townWall"),
            (1, 850, "barrels"),
            (1, 1350, "sandBagsUrban_german"),
            (2, 875, "urban1"),
            (3, 310, "urban1"),
            (3, 590, "urban2"),
            (3, 720, "townWall"),
            (3, 1350, "sandBagsUrban_german"),
        ],
        no_tanks=True,
    ),
    5: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - HIGH LOW",
        text="HIGH LOW: MEDIUM length. Two open roads, one high one low. LIGHT COVER.",
        art="map_skirmish_5",
        width=1605.45,
        covers=[(2, 300, "stoneWall"), (2, 640, "hedgerow"), (2, 925, "woodFenceOvergrown"), (2, 1300, "sandBags")],
        no_tanks=False,
    ),
    6: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - HEDGEROWS",
        text="HEDGEROWS: MEDIUM length. HEAVY COVER. NO TANKS!",
        art="map_skirmish_6",
        width=1615.9,
        covers=[
            (1, 300, "hedgerow"),
            (1, 750, "hedgerow"),
            (1, 1250, "woodFenceOvergrown"),
            (2, 500, "hedgerow"),
            (2, 925, "woodFenceOvergrown"),
            (2, 1300, "hedgerow"),
            (3, 300, "woodFenceOvergrown"),
            (3, 850, "hedgerow"),
            (3, 1250, "hedgerow"),
        ],
        no_tanks=True,
    ),
    7: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - RAILWAY",
        text="RAILWAY: LONG Map. Dense hedgerows lining a railway track.",
        art="map_skirmish_7",
        width=2016.9,
        covers=[
            (1, 300, "sandBags"),
            (1, 650, "hedgerow"),
            (1, 900, "hedgerow"),
            (1, 1250, "woodFenceOvergrown"),
            (1, 1720, "hedgerow"),
            (3, 300, "barrels"),
            (3, 550, "hedgerow"),
            (3, 1350, "hedgerow"),
            (3, 1650, "hedgerow"),
        ],
        no_tanks=False,
    ),
    8: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - TOWN SQUARE",
        text="TOWN SQUARE: LONG Map. HEAVY COVER. NO TANKS!",
        art="map_skirmish_8",
        width=2323.9,
        covers=[
            (1, 310, "townWall"),
            (1, 790, "urban1"),
            (1, 1170, "barrels"),
            (1, 1425, "townWall"),
            (1, 1800, "rubble2"),
            (2, 475, "barrels"),
            (2, 1000, "sandBagsUS"),
            (2, 1345, "urban2"),
            (2, 1800, "sandBagsUrban_german"),
            (3, 310, "townWall"),
            (3, 725, "rubble1"),
            (3, 1170, "urban1"),
            (3, 1480, "townWall"),
            (3, 2105, "townWall"),
        ],
        no_tanks=True,
    ),
    9: CustomMap(  # F6:9330-9440, 11780-11788
        title="SKIRMISH - CEMETARY",
        text="CEMETARY: MEDIUM Map. HEAVY COVER.",
        art="map_skirmish_9",
        width=2043.25,
        covers=[
            (1, 335, "stoneWall"),
            (1, 745, "townWall"),
            (1, 900, "headstones"),
            (1, 1095, "headstones"),
            (1, 1260, "headstones"),
            (1, 1360, "townWall"),
            (1, 1695, "sandBagsUrban_german"),
            (3, 334, "stoneWall"),
            (3, 740, "townWall"),
            (3, 900, "headstones"),
            (3, 1095, "headstones"),
            (3, 1260, "headstones"),
            (3, 1360, "townWall"),
            (3, 1695, "sandBagsUrban_german"),
        ],
        no_tanks=False,
    ),
}


def custom_mission(settings: dict, versus: bool) -> Mission:
    """The Custom Battle (or a versus game) from its settings.

    A versus game has no CPU side and no difficulty. Both sides get the same RP and the same picks. On a NO TANKS
    map the tank is off for both sides. The CPU's pool is the picked units and its support list the picked
    AIR SUPPORT and ARTILLERY (F6:9250-9292, 9322-9345); Smoke Rounds has no toggle and is off.
    """
    side = settings["side"]
    foe = other_side(side)
    custom = CUSTOM_MAPS[settings["map"]]
    units = list(settings["units"])
    if custom.no_tanks:
        units[UNIT_KINDS.index("tank")] = False
    orders = [kind for kind, on in zip(SUPPORT_KINDS, settings["supports"]) if on]
    cpu_supports = [kind for kind in orders if kind in ("airSupport", "artillery")]
    cpu_rate, support_rate = (0, 0) if versus else CUSTOM_RATES[settings["difficulty"]]
    rp = settings["rp"]
    return Mission(
        side=side,
        number=None,
        title=custom.title,
        description="",
        section=1,
        art=custom.art,
        midground=strips(custom.art, 3),
        width=custom.width,
        rain=False,
        morale={"british": CUSTOM_MORALE, "german": CUSTOM_MORALE},
        rp={"british": rp, "german": rp},
        covers=list(custom.covers),
        wires=[],
        mines={"british": ([], 0), "german": ([], 0)},
        units={side: units, foe: list(units) if versus else slot_flags(UNIT_KINDS, ())},
        orders={side: orders, foe: list(orders) if versus else []},
        cpu_pool=[] if versus else [kind for kind, on in zip(UNIT_KINDS, units) if on],
        cpu_supports=[] if versus else cpu_supports,
        cpu_rate=cpu_rate,
        support_rate=support_rate,
        mood="balanced" if versus else settings["mood"],
        random_supports=not versus,
    )
