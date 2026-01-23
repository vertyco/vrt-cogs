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
    "💡 **Tip:** Tactical stance balances range with smart repositioning!",
    "💡 **Tip:** Focus Fire targeting helps your team coordinate attacks.",
    "💡 **Tip:** Light chassis have higher agility for better maneuverability.",
    "💡 **Tip:** Healers can keep your team alive longer in tough fights!",
    "💡 **Tip:** Watch the weight limit - overweight teams can't enter missions.",
    "💡 **Tip:** Higher intelligence means smarter AI decision-making.",
    "💡 **Tip:** Unlock new parts by completing campaign missions!",
    "💡 **Tip:** PvP battles don't cost credits but don't give rewards either.",
    "💡 **Tip:** Stakes challenges let you bet credits against other players!",
    "💡 **Tip:** Each chassis can only equip one plating and one weapon.",
    "💡 **Tip:** Shielding = HP in battle. More shielding = more survivability.",
    "💡 **Tip:** Fire rate matters! High RPM weapons deal consistent damage.",
    "💡 **Tip:** Some weapons have minimum range - don't get too close!",
    "💡 **Tip:** The Garage lets you name your bots and configure tactics.",
    "💡 **Tip:** Sell unwanted parts for 50% of their purchase price.",
    "💡 **Tip:** Change your team color in your Profile!",
    "💡 **Tip:** Laser weapons are fast and accurate but may lack punch.",
    "💡 **Tip:** Cannon weapons hit hard but fire slowly.",
    "💡 **Tip:** Missiles track targets and deal splash damage!",
    "💡 **Tip:** Shockwave weapons are devastating at close range.",
    "💡 **Tip:** Target Priority affects which enemy your bot attacks first.",
    "💡 **Tip:** 'Weakest' targeting helps finish off damaged enemies quickly.",
    "💡 **Tip:** 'Closest' targeting is reactive - engage the nearest threat.",
    "💡 **Tip:** Match your tactics to your weapon's strengths!",
]


def get_random_tip() -> str:
    """Get a random gameplay tip."""
    return random.choice(BATTLE_TIPS)


def get_random_tips(count: int = 3) -> list[str]:
    """Get multiple random unique tips."""
    return random.sample(BATTLE_TIPS, min(count, len(BATTLE_TIPS)))
