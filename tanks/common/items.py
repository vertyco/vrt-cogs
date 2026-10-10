"""The shop: weapons and extras with the original's prices and pack sizes, and what each seat owns for a match"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    """One thing in the shop. `key` names its icon in web/art"""

    key: str
    name: str
    price: int
    pack: int


# In the original's order, which the page and the messages use as each item's number
WEAPONS = (
    Item("bmissile", "Small missile", 0, 0),
    Item("missile", "Missile", 2000, 10),
    Item("bnuke", "Small atom bomb", 5000, 2),
    Item("nuke", "Atom bomb", 13000, 1),
    Item("funky", "Volcano bomb", 8000, 2),
    Item("mirv", "Shower", 9000, 2),
    Item("death", "Hot shower", 30000, 1),
    Item("broller", "Small ball", 5000, 5),
    Item("roller", "Ball", 6000, 2),
    Item("hroller", "Large ball", 15000, 1),
    Item("broller2", "Small ball V2", 6500, 5),
    Item("roller2", "Ball V2", 7500, 2),
    Item("hroller2", "Large ball V2", 18000, 1),
    Item("astrike", "Air strike", 25000, 1),
)
EXTRAS = (
    Item("par", "Parachutes", 5000, 5),
    Item("repair", "Repair kit", 4000, 5),
    Item("fuel", "Fuel", 3000, 50),
    Item("sshield", "Weak shield", 5000, 2),
    Item("shield", "Shield", 10000, 1),
    Item("stshield", "Strong shield", 15000, 1),
    Item("spshield", "Super shield", 20000, 1),
    Item("teleport", "Teleport", 15000, 1),
    Item("upenergy", "Upgrade energy", 5000, 1),
    Item("uparmor", "Upgrade armor", 10000, 1),
    Item("upmove", "Upgrade engine", 7000, 1),
    Item("uphill", "Upgrade hill move", 5000, 1),
)

SMALL_MISSILE = 0
AIR_STRIKE = 13
PARACHUTES, REPAIR, FUEL, WEAK_SHIELD, SHIELD, STRONG_SHIELD, SUPER_SHIELD = range(7)
TELEPORT, UP_ENERGY, UP_ARMOR, UP_ENGINE, UP_HILL = range(7, 12)
# The four shields, numbered 1 to 4 in messages as the original's panel numbers them, and how much each absorbs
SHIELDS = (WEAK_SHIELD, SHIELD, STRONG_SHIELD, SUPER_SHIELD)
SHIELD_STRENGTH = {WEAK_SHIELD: 100, SHIELD: 200, STRONG_SHIELD: 400, SUPER_SHIELD: 600}

START_MONEY = 5000
# The original's starting kit was a test loadout (100 volcano bombs, 8 of every shield). The port starts lean
START_MISSILES = 99
START_FUEL = 500
REPAIR_AMOUNT = 10
ENERGY_PER_UPGRADE = 10

NOT_ENOUGH_MONEY = "Not enough money."


@dataclass
class Kit:
    """What one seat owns for the whole match. Money is what's left to spend; score is the running total"""

    guns: list[int] = field(default_factory=lambda: [START_MISSILES] + [0] * (len(WEAPONS) - 1))
    extras: list[int] = field(default_factory=lambda: [0] * FUEL + [START_FUEL] + [0] * (len(EXTRAS) - FUEL - 1))
    money: float = START_MONEY
    score: float = 0
    kills: int = 0
    # The weapon picked last, kept between rounds as the original keeps it
    weapon: int = SMALL_MISSILE

    @property
    def max_energy(self) -> int:
        return 100 + ENERGY_PER_UPGRADE * self.extras[UP_ENERGY]

    def owns(self, weapon: int) -> bool:
        return weapon == SMALL_MISSILE or self.guns[weapon] > 0

    def buy(self, kind: str, number: int) -> str | None:
        """Buy one pack. Returns a notice when the seat can't afford it"""
        item = (WEAPONS if kind == "weapon" else EXTRAS)[number]
        if self.money < item.price:
            return NOT_ENOUGH_MONEY
        self.money -= item.price
        if kind == "weapon":
            self.guns[number] += item.pack
        else:
            self.extras[number] += item.pack
        return None

    def spend_shot(self) -> int:
        """Use up the picked weapon for one shot, and fall back to the free missile when it runs out"""
        weapon = self.weapon
        if weapon != SMALL_MISSILE:
            self.guns[weapon] -= 1
            if self.guns[weapon] == 0:
                self.weapon = SMALL_MISSILE
        return weapon

    def view(self) -> dict:
        return {
            "money": round(self.money),
            "score": round(self.score),
            "kills": self.kills,
            "guns": list(self.guns),
            "extras": list(self.extras),
            "weapon": self.weapon,
        }
