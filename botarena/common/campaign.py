"""
Bot Arena 3 - Campaign System

Defines the single-player campaign with arenas, NPC enemies, and progression.
Based on the original Bot Arena 3 wiki structure.

Reference: https://botarena3.fandom.com/wiki/Bot_Arena_3_Wiki

Original Arena Order & Stats (from wiki):
| # | Arena                 | Weight | Cost  | Prize | Enemies |
|---|-----------------------|--------|-------|-------|---------|
| 1 | Roxtan Park Arena     | 35     | 0     | 200   | 2       |
| 2 | Tory's Junkyard       | 35     | 100   | 650   | 2       |
| 3 | Chrometek Alley       | 45     | 300   | 1750  | 2       |
| 4 | Metalmash 2059        | 45     | 750   | 3000  | 2       |
| 5 | Spade's Battle Royale | 45     | 1500  | 4500  | 3       |
| 6 | Gaiacorp Promotion    | 70     | 2000  | 6500  | 3       |
| 7 | The Workshop          | 70     | 3200  | 9250  | 2       |
| 8 | Scraptoria 2059       | 70     | 4800  | 12000 | 3       |
| 9 | The Colosseum         | 95     | 6000  | 15000 | 3       |
| 10| Skirmesh              | 95     | 8000  | 18000 | 3       |
| 11| Vulcandome Arena      | 95     | 10050 | 22000 | 2       |
| 12| The Foundry           | 120    | 12000 | 26000 | 3       |
| 13| The Kamikaze-Dome     | 120    | 14000 | 30000 | 2       |
| 14| Execute 2059          | 120    | 16500 | 35000 | 2       |
| 15| The Final Hour        | 150    | 22000 | 50000 | 2       |
"""

import typing as t
from enum import Enum

from pydantic import Field

from ..constants.parts import (  # Chassis; Plating; Components
    CEREBUS,
    CHROMITREX,
    CIRCES,
    CLR_Z050,
    DARSIJ,
    DARSIK_B301_1,
    DARSIK_R200,
    DELIVERANCE,
    DEVENGE,
    DLZ_100,
    DLZ_250,
    DURICHAS,
    ELECTRON,
    GAIACORP_EG_PR,
    GAIACORP_EG_SR,
    GAIACORP_LB_MK2,
    GAIACORP_SC_RS,
    KEDRON,
    OVERWATCH_R200,
    OVERWATCH_R760,
    OVERWATCH_Z,
    PORANTIS,
    RAPTOR_DT_01,
    RAPTOR_DT_02,
    SANTRIN,
    SCREAM_SHARD,
    SHRED_MK3,
    SMARTMOVE,
    TORRIKA_KJ_557,
    TORRIKA_KR_2,
    ZENI_PRS,
    ZENI_PRZ_2,
    ZINTEK,
)
from .models import ArenaBaseModel, Bot, MovementStance, PartsRegistry, TacticalOrders


class Difficulty(str, Enum):
    """Arena difficulty levels based on progression"""

    TUTORIAL = "Tutorial"  # Battles 1-2
    EASY = "Easy"  # Battles 3-5
    MEDIUM = "Medium"  # Battles 6-8
    HARD = "Hard"  # Battles 9-11
    EXTREME = "Extreme"  # Battles 12-14
    BOSS = "Boss"  # Battle 15


class NPCBot(ArenaBaseModel):
    """An NPC bot configuration for campaign battles"""

    name: str
    chassis_name: str
    plating_name: str
    component_name: str
    tactical_orders: TacticalOrders = TacticalOrders()

    def to_bot(self, registry: PartsRegistry) -> t.Optional[Bot]:
        """Convert to a full Bot object"""
        chassis = registry.get_chassis(self.chassis_name)
        plating = registry.get_plating(self.plating_name)
        component = registry.get_component(self.component_name)

        if not all([chassis, plating, component]):
            return None

        return Bot(
            name=self.name,
            chassis=chassis,
            plating=plating,
            component=component,
            tactical_orders=self.tactical_orders,
        )


class Mission(ArenaBaseModel):
    """A single arena battle (called "Mission" for UI consistency)"""

    id: str
    name: str
    description: str
    difficulty: Difficulty
    chapter: int = 1

    # Enemy configuration
    enemies: list[NPCBot]

    # Rewards - based on original game's prize values
    credit_reward: int = 500
    unlock_parts: list[str] = Field(default_factory=list)  # Part names to unlock

    # Requirements
    required_mission: t.Optional[str] = None  # Mission ID that must be completed first

    # Entry cost - player pays this to attempt (win or lose)
    entry_fee: int = 0

    # Weight class restriction (0 = no limit)
    weight_limit: int = 0

    # Flavor text
    briefing: str = ""
    victory_text: str = ""
    defeat_text: str = ""

    # Theme for arena background (e.g., "junkyard", "colosseum")
    # If empty, falls back to chapter-based or default arena
    arena_theme: str = ""


class Chapter(ArenaBaseModel):
    """A campaign chapter containing multiple arenas"""

    id: int
    name: str
    description: str
    missions: list[Mission]


# ═══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN DEFINITION
# Based on original Bot Arena 3 wiki - 15 battles across 5 chapters
# ═══════════════════════════════════════════════════════════════════════════════

CAMPAIGN_CHAPTERS: list[Chapter] = [
    # ───────────────────────────────────────────────────────────────────────────
    # CHAPTER 1: ROOKIE CIRCUIT (Battles 1-5, Weight 35-45)
    # Entry-level arenas to learn the game
    # ───────────────────────────────────────────────────────────────────────────
    Chapter(
        id=1,
        name="Rookie Circuit",
        description="Prove yourself in the beginner arenas. Learn to fight, earn your upgrades.",
        missions=[
            # Battle 1: Roxtan Park Arena
            # Weight: 35, Cost: 0, Prize: 200
            # Enemies: (Santrin/Zintek) + (Chromitrex/Zintek)
            # Player should have Chromitrex + Raptor DT-01 to win
            # Unlocks: Overwatch R200
            Mission(
                id="1-1",
                name="Roxtan Park Arena",
                description="Your first arena battle. Face two basic opponents.",
                difficulty=Difficulty.TUTORIAL,
                chapter=1,
                weight_limit=35,
                enemies=[
                    NPCBot(
                        name="Rookie-1",
                        chassis_name=DLZ_100.name,
                        plating_name=SANTRIN.name,
                        component_name=ZINTEK.name,
                    ),
                    NPCBot(
                        name="Rookie-2",
                        chassis_name=DLZ_100.name,
                        plating_name=CHROMITREX.name,
                        component_name=ZINTEK.name,
                    ),
                ],
                credit_reward=200,
                entry_fee=0,
                unlock_parts=[OVERWATCH_R200.name],
                briefing="Welcome to Roxtan Park! Your opponents have basic gear. Show them what you've got!",
                victory_text="First victory! Overwatch R200 plating is now available in the shop!",
                defeat_text="Everyone loses sometimes. Upgrade your gear and try again.",
            ),
            # Battle 2: Tory's Junkyard
            # Weight: 35, Cost: 100, Prize: 650
            # Enemies: (Chromitrex/Raptor DT-01) + (Chromitrex/Kedron)
            # Unlocks: Raptor DT-02, Torrika KJ-557
            Mission(
                id="1-2",
                name="Tory's Junkyard",
                description="Scrapyard showdown with tougher opponents.",
                difficulty=Difficulty.TUTORIAL,
                chapter=1,
                weight_limit=35,
                enemies=[
                    NPCBot(
                        name="Scrapper",
                        chassis_name=DLZ_100.name,
                        plating_name=CHROMITREX.name,
                        component_name=RAPTOR_DT_01.name,
                    ),
                    NPCBot(
                        name="Junkrat",
                        chassis_name=DLZ_100.name,
                        plating_name=CHROMITREX.name,
                        component_name=KEDRON.name,
                        # Junkrat with Kedron: Close-range ambusher
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.AGGRESSIVE),
                    ),
                ],
                credit_reward=650,
                entry_fee=100,
                required_mission="1-1",
                unlock_parts=[RAPTOR_DT_02.name, TORRIKA_KJ_557.name],
                briefing="Tory's Junkyard - where scrap becomes weapons. Watch out for the Kedron up close!",
                victory_text="Junkyard champion! Raptor DT-02 and Torrika KJ-557 are now available!",
                defeat_text="That Kedron shredded you. Try staying at range.",
            ),
            # Battle 3: Chrometek Alley
            # Weight: 45, Cost: 300, Prize: 1750
            # Enemies: (Chromitrex/Raptor DT-02) + (Overwatch R200/Raptor DT-02)
            # Unlocks: DLZ-250, Gaiacorp LB-MK2
            # First encounter with DLZ-250!
            Mission(
                id="1-3",
                name="Chrometek Alley",
                description="Face upgraded opponents with better weapons.",
                difficulty=Difficulty.EASY,
                chapter=1,
                weight_limit=45,
                enemies=[
                    NPCBot(
                        name="Chrome",
                        chassis_name=DLZ_250.name,  # DLZ-250: 8+4+5=17 (cap 22)
                        plating_name=CHROMITREX.name,
                        component_name=RAPTOR_DT_02.name,
                        # Chrome: Defensive, stays at optimal range
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Tek",
                        chassis_name=DLZ_100.name,  # DLZ-100: 5+6+5=16 (cap 16)
                        plating_name=OVERWATCH_R200.name,
                        component_name=RAPTOR_DT_02.name,
                        # Tek: Aggressive harasser
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                ],
                credit_reward=1750,
                entry_fee=300,
                required_mission="1-2",
                unlock_parts=[DLZ_250.name, GAIACORP_LB_MK2.name],
                briefing="Chrometek Alley - where the serious fighters hang out. Watch out for Chrome's upgraded chassis!",
                victory_text="Impressive! DLZ-250 chassis and Gaiacorp LB-MK2 plating are now available!",
                defeat_text="Those Raptors hit hard. Consider upgrading your armor.",
            ),
            # Battle 4: Metalmash 2059
            # Weight: 45, Cost: 750, Prize: 3000
            # Enemies: (Overwatch R200/Darsij) + (Overwatch R200/Raptor DT-02)
            # Unlocks: Darsij
            Mission(
                id="1-4",
                name="Metalmash 2059",
                description="Heavy firepower awaits in the Metalmash arena.",
                difficulty=Difficulty.EASY,
                chapter=1,
                weight_limit=45,
                enemies=[
                    NPCBot(
                        name="Masher",
                        chassis_name=DLZ_250.name,  # DLZ-250: 8+6+8=22 (cap 22, maxed!)
                        plating_name=OVERWATCH_R200.name,
                        component_name=DARSIJ.name,
                        # Masher: Defensive machine gunner, stays at range
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Crusher",
                        chassis_name=DLZ_100.name,  # DLZ-100: 5+6+5=16 (cap 16)
                        plating_name=OVERWATCH_R200.name,
                        component_name=RAPTOR_DT_02.name,
                    ),
                ],
                credit_reward=3000,
                entry_fee=750,
                required_mission="1-3",
                unlock_parts=[DARSIJ.name],
                briefing="Metalmash 2059 - pure destruction. Masher's DLZ-250 packs a brutal Darsij machine gun!",
                victory_text="You survived the mash! Darsij is now available in the shop!",
                defeat_text="That Darsij is brutal. Try keeping your distance.",
            ),
            # Battle 5: Spade's Battle Royale
            # Weight: 45, Cost: 1500, Prize: 4500
            # Enemies: 3x mixed chassis with varied weapons
            # Unlocks: Smartmove, Overwatch R760
            # First encounter with Smartmove!
            Mission(
                id="1-5",
                name="Spade's Battle Royale",
                description="Three-on-one odds. Can you handle it?",
                difficulty=Difficulty.EASY,
                chapter=1,
                weight_limit=45,
                enemies=[
                    NPCBot(
                        name="Diamond",
                        chassis_name=DLZ_100.name,  # DLZ-100: 5+6+3=14 (cap 16)
                        plating_name=OVERWATCH_R200.name,
                        component_name=RAPTOR_DT_01.name,
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Spade",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+6+8=24 (cap 30)
                        plating_name=OVERWATCH_R200.name,
                        component_name=DARSIJ.name,
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Club",
                        chassis_name=DLZ_100.name,  # DLZ-100: 5+6+3=14 (cap 16)
                        plating_name=OVERWATCH_R200.name,
                        component_name=RAPTOR_DT_01.name,
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                ],
                credit_reward=4500,
                entry_fee=1500,
                required_mission="1-4",
                unlock_parts=[SMARTMOVE.name, OVERWATCH_R760.name],
                briefing="Spade's Battle Royale - the deadly trio! Watch out for Spade's heavy Smartmove chassis!",
                victory_text="Rookie Circuit complete! Smartmove chassis and Overwatch R760 are now available!",
                defeat_text="Outnumbered and outgunned. Focus on one target at a time!",
            ),
        ],
    ),
    # ───────────────────────────────────────────────────────────────────────────
    # CHAPTER 2: LOCAL CIRCUIT (Battles 6-8, Weight 70)
    # Tougher opponents, bigger rewards
    # ───────────────────────────────────────────────────────────────────────────
    Chapter(
        id=2,
        name="Local Circuit",
        description="The real arena circuit begins. Bigger stakes, tougher fights.",
        missions=[
            # Battle 6: Gaiacorp Promotion
            # Weight: 70, Cost: 2000, Prize: 6500
            # Enemies: Mixed heavy chassis with upgraded armor
            # Unlocks: Torrika KR-2
            Mission(
                id="2-1",
                name="Gaiacorp Promotion",
                description="Gaiacorp sponsors this arena. Heavy armor awaits.",
                difficulty=Difficulty.MEDIUM,
                chapter=2,
                weight_limit=70,
                enemies=[
                    NPCBot(
                        name="Gaia-1",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+8+5=23 (cap 30)
                        plating_name=GAIACORP_LB_MK2.name,
                        component_name=RAPTOR_DT_02.name,
                    ),
                    NPCBot(
                        name="Watcher",
                        chassis_name=DLZ_250.name,  # DLZ-250: 8+9+3=20 (cap 22)
                        plating_name=OVERWATCH_R760.name,
                        component_name=RAPTOR_DT_01.name,
                    ),
                    NPCBot(
                        name="Gaia-2",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+8+5=23 (cap 30)
                        plating_name=GAIACORP_LB_MK2.name,
                        component_name=RAPTOR_DT_02.name,
                    ),
                ],
                credit_reward=6500,
                entry_fee=2000,
                required_mission="1-5",
                unlock_parts=[TORRIKA_KR_2.name],
                briefing="Gaiacorp sponsors this fight. Those Smartmoves pack heavy Gaiacorp armor!",
                victory_text="Gaiacorp impressed! Torrika KR-2 is now available!",
                defeat_text="Heavy armor requires heavy firepower. Upgrade your weapons.",
            ),
            # Battle 7: The Workshop
            # Weight: 70, Cost: 3200, Prize: 9250
            # Enemies: Heavy chassis with close-combat weapons
            # Unlocks: CLR-Z050, Gaiacorp SC-RS
            # First encounter with CLR-Z050!
            Mission(
                id="2-2",
                name="The Workshop",
                description="Where bots are built and destroyed. High-powered close combat.",
                difficulty=Difficulty.MEDIUM,
                chapter=2,
                weight_limit=70,
                enemies=[
                    NPCBot(
                        name="Mechanic",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+9+10=34 (cap 50)
                        plating_name=OVERWATCH_R760.name,
                        component_name=TORRIKA_KR_2.name,
                        # Mechanic: Heavy brawler, aggressive combat (Torrika KR-2 min_range=30)
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.TACTICAL),
                    ),
                    NPCBot(
                        name="Welder",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+8+10=28 (cap 30)
                        plating_name=GAIACORP_LB_MK2.name,
                        component_name=TORRIKA_KR_2.name,
                        # Welder: Aggressive assassin, targets weak (Torrika KR-2 min_range=30)
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                ],
                credit_reward=9250,
                entry_fee=3200,
                required_mission="2-1",
                unlock_parts=[CLR_Z050.name, GAIACORP_SC_RS.name],
                briefing="The Workshop - Mechanic's CLR-Z050 is a serious threat. Both have Torrika KR-2!",
                victory_text="Workshop mastered! CLR-Z050 chassis and Gaiacorp SC-RS plating are now available!",
                defeat_text="Those Torrikas hit hard. Try heavier armor.",
            ),
            # Battle 8: Scraptoria 2059
            # Weight: 70, Cost: 4800, Prize: 12000
            # Enemies: Mixed chassis with healer support
            # Unlocks: Zeni PRS
            Mission(
                id="2-3",
                name="Scraptoria 2059",
                description="The infamous scrapyard arena. Many enter, few leave.",
                difficulty=Difficulty.MEDIUM,
                chapter=2,
                weight_limit=70,
                enemies=[
                    NPCBot(
                        name="Scrap-1",
                        chassis_name=DLZ_250.name,  # DLZ-250: 8+6+8=22 (cap 22, maxed!) - aggressive threat
                        plating_name=OVERWATCH_R200.name,
                        component_name=DARSIJ.name,
                        # Scrap-1: Aggressive damage dealer with machine gun
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Scrapper",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+12+10=37 (cap 50) - main threat
                        plating_name=GAIACORP_SC_RS.name,
                        component_name=TORRIKA_KR_2.name,
                        # Scrapper: Main threat, aggressive finisher (Torrika KR-2 min_range=30)
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Scrap-2",
                        chassis_name=DLZ_250.name,  # DLZ-250: 8+4+10=22 (cap 22, maxed!) - healer
                        plating_name=CHROMITREX.name,
                        component_name=ZENI_PRS.name,
                        # Scrap-2: Healer support, stays back and keeps team alive
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                ],
                credit_reward=12000,
                entry_fee=4800,
                required_mission="2-2",
                unlock_parts=[ZENI_PRS.name],
                briefing="Scraptoria 2059 - Scrapper's CLR-Z050 is brutal, but watch out for their healer! Take it out first!",
                victory_text="Local Circuit complete! Zeni PRS healer is now available!",
                defeat_text="That healer kept them alive too long. Focus fire on Scrap-2 first!",
            ),
        ],
    ),
    # ───────────────────────────────────────────────────────────────────────────
    # CHAPTER 3: REGIONAL TOURNAMENT (Battles 9-11, Weight 95)
    # Serious competition
    # ───────────────────────────────────────────────────────────────────────────
    Chapter(
        id=3,
        name="Regional Tournament",
        description="The regional circuit. Only skilled pilots survive here.",
        missions=[
            # Battle 9: The Colosseum
            # Weight: 95, Cost: 6000, Prize: 15000
            # Enemies: Heavy chassis with healer support
            # Unlocks: Gaiacorp EG-PR, Darsik B301-1, Porantis
            Mission(
                id="3-1",
                name="The Colosseum",
                description="The legendary Colosseum. Gladiators await.",
                difficulty=Difficulty.HARD,
                chapter=3,
                weight_limit=95,
                enemies=[
                    NPCBot(
                        name="Medic",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+12+10=37 (cap 50) - healer
                        plating_name=GAIACORP_SC_RS.name,
                        component_name=ZENI_PRS.name,
                        # Medic: Defensive stance, stays with team
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Gladiator-1",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+9+7=26 (cap 30)
                        plating_name=OVERWATCH_R760.name,
                        component_name=TORRIKA_KJ_557.name,
                        # Gladiator-1: Aggressive brawler
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Gladiator-2",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+9+7=31 (cap 50)
                        plating_name=OVERWATCH_R760.name,
                        component_name=TORRIKA_KJ_557.name,
                        # Gladiator-2: Aggressive bruiser
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.AGGRESSIVE,
                        ),
                    ),
                ],
                credit_reward=15000,
                entry_fee=6000,
                required_mission="2-3",
                unlock_parts=[GAIACORP_EG_PR.name, DARSIK_B301_1.name, PORANTIS.name],
                briefing="The Colosseum - their CLR-Z050 Medic keeps them fighting. Eliminate it first!",
                victory_text="Colosseum champion! Gaiacorp EG-PR, Darsik B301-1, and Porantis are now available!",
                defeat_text="That healer kept them alive. Focus fire on the Medic!",
            ),
            # Battle 10: Skirmesh
            # Weight: 95, Cost: 8000, Prize: 18000
            # Enemies: Tactical mixed chassis
            # Unlocks: Electron, Circes
            # First encounter with Electron!
            Mission(
                id="3-2",
                name="Skirmesh",
                description="Tactical skirmish arena. Smart opponents await.",
                difficulty=Difficulty.HARD,
                chapter=3,
                weight_limit=95,
                enemies=[
                    NPCBot(
                        name="Tactician-1",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+12+5=32 (cap 50)
                        plating_name=GAIACORP_SC_RS.name,
                        component_name=RAPTOR_DT_02.name,
                        # Tactician-1: Defensive support, focus fire
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Tactician-2",
                        chassis_name=SMARTMOVE.name,  # Smartmove: 10+12+5=27 (cap 30)
                        plating_name=GAIACORP_SC_RS.name,
                        component_name=RAPTOR_DT_02.name,
                        # Tactician-2: Defensive anchor
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Heavy",
                        chassis_name=ELECTRON.name,  # Electron: 19+9+11=39 (cap 64) - first Electron!
                        plating_name=OVERWATCH_R760.name,
                        component_name=DARSIK_B301_1.name,
                        # Heavy: Massive firepower (Darsik B301-1 min_range=30)
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                ],
                credit_reward=18000,
                entry_fee=8000,
                required_mission="3-1",
                unlock_parts=[ELECTRON.name, CIRCES.name],
                briefing="Skirmesh - Heavy's Electron chassis is a beast. That Darsik B301-1 shreds armor!",
                victory_text="Tactical victory! Electron chassis and Circes weapon are now available!",
                defeat_text="Outmaneuvered. Try splitting their attention.",
            ),
            # Battle 11: Vulcandome Arena
            # Weight: 95, Cost: 10050, Prize: 22000
            # Enemies: Heavy chassis introducing Durichas - player just unlocked Electron/Circes
            # Unlocks: Durichas, Overwatch Z, Zeni PRZ-2
            # First encounter with Overwatch Z!
            Mission(
                id="3-3",
                name="Vulcandome Arena",
                description="The volcanic arena. Heat and heavy firepower.",
                difficulty=Difficulty.HARD,
                chapter=3,
                weight_limit=95,
                enemies=[
                    NPCBot(
                        name="Vulcan-1",
                        chassis_name=ELECTRON.name,  # Electron: 19+19+15=53 (cap 64)
                        plating_name=OVERWATCH_Z.name,  # First Overwatch Z!
                        component_name=CIRCES.name,
                    ),
                    NPCBot(
                        name="Vulcan-2",
                        chassis_name=ELECTRON.name,  # Electron: 19+12+15=46 (cap 64)
                        plating_name=GAIACORP_EG_PR.name,  # Matching player progression
                        component_name=CIRCES.name,  # Player just unlocked this
                    ),
                ],
                credit_reward=22000,
                entry_fee=10050,
                required_mission="3-2",
                unlock_parts=[DURICHAS.name, OVERWATCH_Z.name, ZENI_PRZ_2.name],
                briefing="Vulcandome Arena - Vulcan-1's Durichas is a fortress with heavy cannon! Watch for Vulcan-2's flanking plasma!",
                victory_text="Regional Tournament complete! Durichas, Overwatch Z, and Zeni PRZ-2 are now available!",
                defeat_text="That Durichas is tough. Focus fire to bring it down!",
            ),
        ],
    ),
    # ───────────────────────────────────────────────────────────────────────────
    # CHAPTER 4: NATIONAL LEAGUE (Battles 12-14, Weight 120)
    # Elite competition
    # ───────────────────────────────────────────────────────────────────────────
    Chapter(
        id=4,
        name="National League",
        description="The national circuit. The best pilots in the country.",
        missions=[
            # Battle 12: The Foundry
            # Weight: 120, Cost: 12000, Prize: 26000
            # Enemies: Elite assault chassis with healer support
            # Unlocks: Gaiacorp EG-SR, Devenge
            Mission(
                id="4-1",
                name="The Foundry",
                description="Where legends are forged. Heavy armor and healing.",
                difficulty=Difficulty.EXTREME,
                chapter=4,
                weight_limit=120,
                enemies=[
                    NPCBot(
                        name="Healer",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+12+18=45 (cap 50)
                        plating_name=GAIACORP_SC_RS.name,
                        component_name=ZENI_PRZ_2.name,  # Upgraded healer - serious threat
                        # Healer: Defensive stance, stays behind Forge and heals
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Forge",
                        chassis_name=DURICHAS.name,  # Durichas: 26+15+15=56 (cap 70)
                        plating_name=GAIACORP_EG_PR.name,  # Good armor
                        component_name=CIRCES.name,  # Hard-hitting weapon (min_range=50)
                        # Forge: Aggressive tank, draws fire while healer supports
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.TACTICAL),
                    ),
                ],  # Reduced from 3 to 2 - Durichas with Circes + healer is plenty
                credit_reward=26000,
                entry_fee=12000,
                required_mission="3-3",
                unlock_parts=[GAIACORP_EG_SR.name, DEVENGE.name],
                briefing="The Foundry - Forge's Durichas has devastating Circes! Take out the healer first!",
                victory_text="Foundry conquered! Gaiacorp EG-SR plating and Devenge sniper are now available!",
                defeat_text="That healer is the key. Focus fire on it!",
            ),
            # Battle 13: The Kamikaze-Dome
            # Weight: 120, Cost: 14000, Prize: 30000
            # Enemies: Twin assault chassis - pure aggression
            # Unlocks: Darsik R200, Cerebus
            Mission(
                id="4-2",
                name="The Kamikaze-Dome",
                description="No retreat, no surrender. Pure aggression.",
                difficulty=Difficulty.EXTREME,
                chapter=4,
                weight_limit=120,
                enemies=[
                    NPCBot(
                        name="Kamikaze-1",
                        chassis_name=DURICHAS.name,  # Durichas: 26+19+15=60 (cap 70)
                        plating_name=OVERWATCH_Z.name,  # Good but not best armor
                        component_name=CIRCES.name,  # High damage plasma (min_range=50)
                        # Kamikaze-1: All-out aggression, no retreat
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.TACTICAL),
                    ),
                    NPCBot(
                        name="Kamikaze-2",
                        chassis_name=ELECTRON.name,  # Electron: 19+15+11=45 (cap 64)
                        plating_name=GAIACORP_EG_PR.name,  # Slightly weaker armor
                        component_name=DARSIK_B301_1.name,  # Rapid fire (min_range=30)
                        # Kamikaze-2: Aggressive flanker, spray and pray
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.TACTICAL),
                    ),
                ],
                credit_reward=30000,
                entry_fee=14000,
                required_mission="4-1",
                unlock_parts=[DARSIK_R200.name, CEREBUS.name],
                briefing="The Kamikaze-Dome - two assault chassis with heavy firepower. Plasma and bullets!",
                victory_text="Kamikaze-Dome mastered! Darsik R200 and Cerebus teslacoil are now available!",
                defeat_text="Pure firepower required. Bring your best weapons.",
            ),
            # Battle 14: Execute 2059
            # Weight: 120, Cost: 16500, Prize: 35000
            # Enemies: Elite executioners with top-tier weapons
            # Unlocks: Deliverance, Shred-MK3
            # First encounter with Deliverance!
            Mission(
                id="4-3",
                name="Execute 2059",
                description="The executioner awaits. No mercy.",
                difficulty=Difficulty.EXTREME,
                chapter=4,
                weight_limit=120,
                enemies=[
                    NPCBot(
                        name="Executioner",
                        chassis_name=DELIVERANCE.name,  # Deliverance: 30+15+20=65 (cap 85) - first Deliverance!
                        plating_name=GAIACORP_EG_PR.name,
                        component_name=DEVENGE.name,  # Player just unlocked this - fair fight
                        # Executioner: Defensive sniper, methodical kills
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Headsman",
                        chassis_name=DURICHAS.name,  # Durichas: 26+19+15=60 (cap 70)
                        plating_name=OVERWATCH_Z.name,  # Good armor, not max
                        component_name=CIRCES.name,  # min_range=50
                        # Headsman: Aggressive enforcer, protects Executioner
                        tactical_orders=TacticalOrders(movement_stance=MovementStance.TACTICAL),
                    ),
                ],
                credit_reward=35000,
                entry_fee=16500,
                required_mission="4-2",
                unlock_parts=[DELIVERANCE.name, SHRED_MK3.name],
                briefing="Execute 2059 - the Executioner's Deliverance is the ultimate war machine. Devenge sniper and Circes plasma!",
                victory_text="National League complete! Deliverance chassis and Shred-MK3 plating are now available!",
                defeat_text="The elite fighters live up to their names. Bring maximum firepower.",
            ),
        ],
    ),
    # ───────────────────────────────────────────────────────────────────────────
    # CHAPTER 5: CHAMPIONSHIP (Battle 15, Weight 150)
    # The final battle
    # ───────────────────────────────────────────────────────────────────────────
    Chapter(
        id=5,
        name="Championship",
        description="The final challenge. Only one will be champion.",
        missions=[
            # Battle 15: The Final Hour
            # Weight: 150, Cost: 22000, Prize: 50000
            # Enemies: Ultimate boss fight - maxed out chassis
            # Unlocks: Scream Shard
            Mission(
                id="5-1",
                name="The Final Hour",
                description="The championship final. Everything has led to this moment.",
                difficulty=Difficulty.BOSS,
                chapter=5,
                weight_limit=150,
                enemies=[
                    NPCBot(
                        name="Champion",
                        chassis_name=DELIVERANCE.name,  # Deliverance: 30+25+30=85 (cap 85, MAXED!)
                        plating_name=SHRED_MK3.name,
                        component_name=SCREAM_SHARD.name,  # The ultimate weapon - this is the FINAL boss
                        # Champion: Elite defensive master, methodical destruction
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Herald",
                        chassis_name=CLR_Z050.name,  # CLR-Z050: 15+22+18=55 (cap 50, over!)
                        plating_name=GAIACORP_EG_SR.name,  # Heavy armor
                        component_name=ZENI_PRZ_2.name,  # Healer support - keeps Champion alive
                        # Herald: Dedicated healer, stays back and supports
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                    NPCBot(
                        name="Guardian",
                        chassis_name=DURICHAS.name,  # Durichas: 26+22+22=70 (cap 70, maxed!)
                        plating_name=GAIACORP_EG_SR.name,  # Best available armor
                        component_name=DARSIK_R200.name,  # High DPM suppressive fire
                        # Guardian: Protector stance, stays near team and suppresses
                        tactical_orders=TacticalOrders(
                            movement_stance=MovementStance.DEFENSIVE,
                        ),
                    ),
                ],
                credit_reward=50000,
                entry_fee=22000,
                required_mission="4-3",
                unlock_parts=[SCREAM_SHARD.name],
                briefing="The Final Hour - the Champion wields the legendary Scream Shard! Herald's healing keeps them fighting while Guardian suppresses!",
                victory_text="CHAMPION! You are the greatest bot arena fighter of all time! The legendary Scream Shard is yours!",
                defeat_text="The Champion remains undefeated. Take out the Herald healer first, then focus the Guardian!",
            ),
        ],
    ),
]


def get_all_missions() -> list[Mission]:
    """Get all missions from all chapters"""
    missions = []
    for chapter in CAMPAIGN_CHAPTERS:
        missions.extend(chapter.missions)
    return missions


def get_mission_by_id(mission_id: str) -> t.Optional[Mission]:
    """Find a mission by its ID"""
    for chapter in CAMPAIGN_CHAPTERS:
        for mission in chapter.missions:
            if mission.id == mission_id:
                return mission
    return None


def get_chapter_for_mission(mission_id: str) -> t.Optional[Chapter]:
    """Get the chapter that contains a mission"""
    for chapter in CAMPAIGN_CHAPTERS:
        for mission in chapter.missions:
            if mission.id == mission_id:
                return chapter
    return None


def get_available_missions(completed_missions: set[str]) -> list[Mission]:
    """Get missions that are available based on completed missions"""
    available = []
    for chapter in CAMPAIGN_CHAPTERS:
        for mission in chapter.missions:
            if mission.id in completed_missions:
                continue  # Already completed
            if mission.required_mission is None:
                available.append(mission)
            elif mission.required_mission in completed_missions:
                available.append(mission)
    return available


def get_chapter_progress(chapter_id: int, completed_missions: set[str]) -> tuple[int, int]:
    """Get (completed, total) mission count for a chapter"""
    for chapter in CAMPAIGN_CHAPTERS:
        if chapter.id == chapter_id:
            total = len(chapter.missions)
            completed = sum(1 for m in chapter.missions if m.id in completed_missions)
            return completed, total
    return 0, 0
