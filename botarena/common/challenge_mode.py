"""
Bot Arena - Challenges

Fixed puzzle battles from the original Bot Arena 3. The player is loaned a preset squad
and only chooses each bot's tactical orders; every challenge teaches one tactic.
Rewards pay out on the first clear only, and challenges never touch campaign progress.
"""

import typing as t

from pydantic import Field

from ..constants.parts import (
    CHROMITREX,
    CIRCES,
    CLR_Z050,
    DARSIJ,
    DARSIK_R200,
    DEVENGE,
    DLZ_250,
    DURICHAS,
    ELECTRON,
    GAIACORP_EG_PR,
    GAIACORP_SC_RS,
    KEDRON,
    OVERWATCH_R200,
    OVERWATCH_R760,
    OVERWATCH_Z,
    PLATING,
    PORANTIS,
    PRIZE_DARSIK_R200_Z,
    PRIZE_OVERWATCH_R760,
    RAPTOR_DT_02,
    SANTRIN,
    SMARTMOVE,
    TORRIKA_KJ_557,
    TORRIKA_KR_2,
    ZENI_PRZ_2,
    ZINTEK,
)
from .campaign import NPCBot
from .models import (
    ArenaBaseModel,
    Chassis,
    Component,
    MovementStance,
    Plating,
    PlayerData,
    TacticalOrders,
    TargetPriority,
)


def orders(stance: MovementStance, target: TargetPriority) -> TacticalOrders:
    return TacticalOrders(movement_stance=stance, target_priority=target)


class Challenge(ArenaBaseModel):
    """A fixed puzzle battle with a loaned squad"""

    id: str
    name: str
    description: str
    briefing: str
    loaned_bots: list[NPCBot]
    enemies: list[NPCBot]
    solution: list[TacticalOrders]  # One per loaned bot; the balance simulator checks these orders win
    must_survive: list[str] = Field(default_factory=list)  # Loaned bot names that must be alive at the end
    required_mission: t.Optional[str] = None  # Campaign mission that unlocks this challenge
    credit_reward: int
    prize_part: t.Optional[str] = None
    chapter: int = 1  # Picks the arena background
    victory_text: str = ""
    defeat_text: str = ""


AGGRESSIVE, DEFENSIVE, TACTICAL = MovementStance.AGGRESSIVE, MovementStance.DEFENSIVE, MovementStance.TACTICAL
FOCUS, WEAKEST, CLOSEST = TargetPriority.FOCUS_FIRE, TargetPriority.WEAKEST, TargetPriority.CLOSEST


def npc(
    name: str,
    chassis: Chassis,
    plating: Plating,
    weapon: Component,
    stance: MovementStance = AGGRESSIVE,
    target: TargetPriority = CLOSEST,
) -> NPCBot:
    return NPCBot(
        name=name,
        chassis_name=chassis.name,
        plating_name=plating.name,
        component_name=weapon.name,
        tactical_orders=orders(stance, target),
    )


CHALLENGES: list[Challenge] = [
    Challenge(
        id="c1",
        name="Introduction",
        description="Three Raptors against three spray guns.",
        briefing=(
            "Their Kedron spray guns shred anything up close, but they can't reach as far as your Raptors. "
            "Pick a stance that keeps the fight at long range."
        ),
        loaned_bots=[
            npc("Ace", DLZ_250, OVERWATCH_R200, RAPTOR_DT_02),
            npc("Blitz", DLZ_250, OVERWATCH_R200, RAPTOR_DT_02),
            npc("Comet", DLZ_250, OVERWATCH_R200, RAPTOR_DT_02),
        ],
        enemies=[
            npc("Spray A", DLZ_250, OVERWATCH_R200, KEDRON),
            npc("Spray B", DLZ_250, OVERWATCH_R200, KEDRON),
            npc("Spray C", DLZ_250, OVERWATCH_R200, KEDRON),
        ],
        solution=[orders(DEFENSIVE, CLOSEST)] * 3,
        credit_reward=500,
        chapter=1,
        victory_text="Stance decides where your bots fight. Out of their reach, their guns can't touch you.",
        defeat_text="Your bots charged into spray range. Try a stance that holds back.",
    ),
    Challenge(
        id="c2",
        name="Evasion",
        description="One sharpshooter against four brawlers.",
        briefing="Puppy has the range, they have the numbers. Never let the brawlers catch you.",
        loaned_bots=[npc("Puppy", DLZ_250, CHROMITREX, RAPTOR_DT_02)],
        enemies=[
            npc("Brute 1", CLR_Z050, SANTRIN, TORRIKA_KJ_557),
            npc("Brute 2", CLR_Z050, SANTRIN, TORRIKA_KJ_557),
            npc("Brute 3", CLR_Z050, SANTRIN, TORRIKA_KJ_557),
            npc("Brute 4", CLR_Z050, SANTRIN, TORRIKA_KJ_557),
        ],
        solution=[orders(DEFENSIVE, CLOSEST)],
        credit_reward=1000,
        chapter=1,
        victory_text="Keep your distance and a short-range bot can never hurt you.",
        defeat_text="The brawlers caught you. Keep Puppy at maximum range.",
    ),
    Challenge(
        id="c3",
        name="Distracting",
        description="A tank and two glass cannons against three jackhammers.",
        briefing=(
            "The raiders smash whatever is closest. Your two Raptors can't take a hit, "
            "so give the raiders something tough to chew on while the Raptors work from a distance."
        ),
        loaned_bots=[
            npc("Bulwark", SMARTMOVE, OVERWATCH_R760, ZINTEK),
            npc("Glass 1", DLZ_250, SANTRIN, RAPTOR_DT_02),
            npc("Glass 2", DLZ_250, SANTRIN, RAPTOR_DT_02),
        ],
        enemies=[
            npc("Raider 1", DLZ_250, OVERWATCH_R200, TORRIKA_KJ_557),
            npc("Raider 2", DLZ_250, OVERWATCH_R200, TORRIKA_KJ_557),
            npc("Raider 3", DLZ_250, OVERWATCH_R200, TORRIKA_KJ_557),
        ],
        solution=[orders(AGGRESSIVE, CLOSEST), orders(DEFENSIVE, CLOSEST), orders(DEFENSIVE, CLOSEST)],
        required_mission="1-3",
        credit_reward=2000,
        chapter=1,
        victory_text="The tank soaked the hammers while your glass cannons worked safely.",
        defeat_text="Your glass cannons got too close. Send the tank in and hold the others back.",
    ),
    Challenge(
        id="c4",
        name="Ranged",
        description="Two cannons against three machine gunners.",
        briefing="They out-gun you up close, but your Porantis cannons reach further than their machine guns.",
        loaned_bots=[
            npc("Longbow", ELECTRON, OVERWATCH_R200, PORANTIS),
            npc("Mortar", ELECTRON, OVERWATCH_R200, PORANTIS),
        ],
        enemies=[
            npc("Brawl 1", SMARTMOVE, OVERWATCH_R760, DARSIJ),
            npc("Brawl 2", CLR_Z050, OVERWATCH_R760, DARSIJ),
            npc("Brawl 3", CLR_Z050, OVERWATCH_R760, DARSIJ),
        ],
        solution=[orders(DEFENSIVE, CLOSEST)] * 2,
        required_mission="2-1",
        credit_reward=3000,
        chapter=2,
        victory_text="Out-ranged and outplayed. Fight where they can't fight back.",
        defeat_text="You let them close the gap. Keep your cannons at their longest range.",
    ),
    Challenge(
        id="c5",
        name="Hammertime",
        description="Their whole team swings jackhammers.",
        briefing=(
            "Four jackhammers are coming. You brought one hammer of your own and two nailguns "
            "that reach much further. Don't let the nailguns walk into hammer range."
        ),
        loaned_bots=[
            npc("Hammer", DLZ_250, OVERWATCH_R200, TORRIKA_KJ_557),
            npc("Nailer 1", SMARTMOVE, OVERWATCH_R200, TORRIKA_KR_2),
            npc("Nailer 2", SMARTMOVE, OVERWATCH_R200, TORRIKA_KR_2),
        ],
        enemies=[
            npc("Smasher", SMARTMOVE, OVERWATCH_R760, TORRIKA_KJ_557),
            npc("Basher", SMARTMOVE, OVERWATCH_R760, TORRIKA_KJ_557),
            npc("Crusher", SMARTMOVE, OVERWATCH_R760, TORRIKA_KJ_557),
            npc("Tapper", DLZ_250, OVERWATCH_R200, TORRIKA_KJ_557),
        ],
        solution=[orders(AGGRESSIVE, CLOSEST), orders(DEFENSIVE, CLOSEST), orders(DEFENSIVE, CLOSEST)],
        required_mission="2-3",
        credit_reward=5000,
        chapter=2,
        victory_text="Hammer up front, nails from afar. Each bot fought at its own best range.",
        defeat_text="Your nailguns wandered into hammer range. Hold them back and let them shoot from afar.",
    ),
    Challenge(
        id="c6",
        name="Protection",
        description="Keep the VIP alive.",
        briefing="The hunters go for your weakest bot. The VIP must survive, or you lose.",
        loaned_bots=[
            npc("VIP", DLZ_250, CHROMITREX, ZINTEK),
            npc("Warden", ELECTRON, OVERWATCH_Z, CIRCES),
            npc("Medic", CLR_Z050, GAIACORP_SC_RS, ZENI_PRZ_2),
        ],
        enemies=[
            npc("Hunter 1", SMARTMOVE, OVERWATCH_R200, TORRIKA_KR_2, AGGRESSIVE, WEAKEST),
            npc("Hunter 2", SMARTMOVE, CHROMITREX, TORRIKA_KR_2, AGGRESSIVE, WEAKEST),
        ],
        solution=[orders(DEFENSIVE, CLOSEST), orders(AGGRESSIVE, CLOSEST), orders(AGGRESSIVE, CLOSEST)],
        must_survive=["VIP"],
        required_mission="4-1",
        credit_reward=8000,
        prize_part=PRIZE_OVERWATCH_R760.name,
        chapter=4,
        victory_text="The VIP walks out without a scratch. The prize armor is yours!",
        defeat_text="The VIP went down. Keep it out of reach and send your fighters at the hunters.",
    ),
    Challenge(
        id="c7",
        name="Strategy",
        description="The final exam: a healer, a tank, and a sniper.",
        briefing=(
            "Everything you've learned. Each of your bots needs a different stance: "
            "one to brawl, one to hang back, one to hold the middle."
        ),
        loaned_bots=[
            npc("Vanguard", DURICHAS, OVERWATCH_Z, DARSIJ),
            npc("Striker", ELECTRON, GAIACORP_EG_PR, CIRCES),
            npc("Marksman", ELECTRON, GAIACORP_EG_PR, DEVENGE),
        ],
        enemies=[
            npc("Mender", CLR_Z050, GAIACORP_SC_RS, ZENI_PRZ_2, DEFENSIVE, CLOSEST),
            npc("Bastion", DURICHAS, OVERWATCH_Z, DARSIK_R200),
            npc("Sniper", ELECTRON, GAIACORP_EG_PR, DEVENGE, DEFENSIVE, CLOSEST),
        ],
        solution=[orders(AGGRESSIVE, CLOSEST), orders(DEFENSIVE, CLOSEST), orders(TACTICAL, CLOSEST)],
        required_mission="5-1",
        credit_reward=15000,
        prize_part=PRIZE_DARSIK_R200_Z.name,
        chapter=5,
        victory_text="Graduated with honors. The prize machine gun is yours!",
        defeat_text="One stance doesn't fit every bot. Match each bot's stance to its weapon's range.",
    ),
]


def get_challenge(challenge_id: str) -> t.Optional[Challenge]:
    return next((c for c in CHALLENGES if c.id == challenge_id), None)


def is_unlocked(challenge: Challenge, completed_missions: set[str]) -> bool:
    return challenge.required_mission is None or challenge.required_mission in completed_missions


def succeeded(challenge: Challenge, result: dict) -> bool:
    """The loaned squad (team 1) won, and every must-survive bot is still alive."""
    if result.get("winner_team") != 1:
        return False
    alive = {s["name"] for s in result.get("bot_stats", {}).values() if s.get("team") == 1 and s.get("survived")}
    return all(name in alive for name in challenge.must_survive)


def grant_challenge_rewards(player: PlayerData, challenge: Challenge) -> list[str]:
    """Pay a first clear: credits, the prize part (if any), and mark it done. Returns the parts granted."""
    if challenge.id in player.completed_challenges:
        return []
    player.completed_challenges.append(challenge.id)
    player.credits += challenge.credit_reward
    if not challenge.prize_part:
        return []
    part_type = "plating" if any(p.name == challenge.prize_part for p in PLATING) else "component"
    player.add_equipment(part_type, challenge.prize_part)
    return [challenge.prize_part]
