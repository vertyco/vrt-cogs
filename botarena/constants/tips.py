"""
Bot Arena - Game Tips

Random tips shown during battle rendering and loading screens.
"""

import random

# Tips shown during battle rendering
BATTLE_TIPS: list[str] = [
    "💡 **Tip:** Heavier bots move slower but can carry bigger weapons!",
    "💡 **Tip:** Use defensive stance for ranged bots to keep distance.",
    "💡 **Tip:** Aggressive stance works best for close-range weapons.",
    "💡 **Tip:** Tactical bots circle side-on and can roll out of the way of slow shells.",
    "💡 **Tip:** Focus Fire makes your bots gang up on one enemy at a time.",
    "💡 **Tip:** Light chassis have higher agility for better maneuverability.",
    "💡 **Tip:** Healers can keep your team alive longer in tough fights!",
    "💡 **Tip:** Watch the weight limit - overweight teams can't enter missions.",
    "💡 **Tip:** Higher intelligence means better aim, faster reactions and smarter positioning.",
    "💡 **Tip:** Unlock new parts by completing campaign missions!",
    "💡 **Tip:** PvP battles don't cost credits but don't give rewards either.",
    "💡 **Tip:** Use 'Set Your Bet' in a PvP challenge to wager against other players!",
    "💡 **Tip:** Each chassis can only equip one plating and one weapon.",
    "💡 **Tip:** Shielding = HP in battle. More shielding = more survivability.",
    "💡 **Tip:** Fire rate matters! High RPM weapons deal consistent damage.",
    "💡 **Tip:** Some weapons have a minimum range - get right next to a sniper and it can't shoot you!",
    "💡 **Tip:** Shooting while strafing sideways is less accurate - planted bots aim best.",
    "💡 **Tip:** The Garage lets you name your bots and configure tactics.",
    "💡 **Tip:** Sell unwanted parts for 50% of their purchase price.",
    "💡 **Tip:** Change your team color in your Profile!",
    "💡 **Tip:** Laser weapons are fast and accurate but may lack punch.",
    "💡 **Tip:** Cannon shells hit hard but fly slowly - agile bots can dodge them at range.",
    "💡 **Tip:** Missile weapons explode on impact and hurt nearby enemies!",
    "💡 **Tip:** Low-accuracy weapons miss more at long range. Get close!",
    "💡 **Tip:** Shockwave weapons are devastating at close range.",
    "💡 **Tip:** Target Priority affects which enemy your bot attacks first.",
    "💡 **Tip:** 'Weakest' targeting goes for whoever your weapon can finish off soonest.",
    "💡 **Tip:** 'Closest' targeting fights whatever it can hit soonest and shoots back at attackers.",
    "💡 **Tip:** 'Support First' targeting hunts down enemy healers before anything else.",
    "💡 **Tip:** Match your tactics to your weapon's strengths!",
]


def get_random_tip() -> str:
    """Get a random gameplay tip."""
    return random.choice(BATTLE_TIPS)


def get_random_tips(count: int = 3) -> list[str]:
    """Get multiple random unique tips."""
    return random.sample(BATTLE_TIPS, min(count, len(BATTLE_TIPS)))
