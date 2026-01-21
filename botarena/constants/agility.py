"""
Bot Arena - Agility Constants

Defines agility quirk mappings for chassis display.
"""

# Agility quirk descriptions based on agility value ranges
# Format: (min, max): (short_name, description)
AGILITY_QUIRKS: dict[tuple[float, float], tuple[str, str]] = {
    (0.9, 1.0): ("⚡ Lightning Agility", "Can turn at full speed with almost no penalty"),
    (0.7, 0.9): ("🏃 High Agility", "Excellent maneuverability while moving"),
    (0.5, 0.7): ("🔄 Moderate Agility", "Decent turning while in motion"),
    (0.3, 0.5): ("🐢 Low Agility", "Must slow significantly to turn"),
    (0.0, 0.3): ("🧱 Tank Turning", "Nearly stops to change direction"),
}


def get_agility_quirk(agility: float) -> str:
    """Get the short quirk name for an agility value (e.g. '⚡ Lightning Agility')"""
    for (low, high), (name, _) in AGILITY_QUIRKS.items():
        if low <= agility < high:
            return name
    return "🔄 Normal Agility"


def get_agility_quirk_detailed(agility: float) -> tuple[str, str]:
    """Get the quirk name and description for an agility value"""
    for (low, high), quirk in AGILITY_QUIRKS.items():
        if low <= agility < high:
            return quirk
    return ("🔄 Normal Agility", "Standard turning ability")
