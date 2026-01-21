"""
Bot Arena 3 - Parts Constants

All chassis, plating, and component definitions.
Values are based on the original Bot Arena 3 game mechanics.

Reference: https://flashgaming.fandom.com/wiki/Bot_Arena_3
"""

import typing as t

from ..common.models import (
    Chassis,
    Component,
    ComponentType,
    Plating,
    ProjectileType,
    WeightClass,
)

if t.TYPE_CHECKING:
    from ..common.models import PartsRegistry

# ─────────────────────────────────────────────────────────────────────────────
# CHASSIS DEFINITIONS
# Based on original Bot Arena 3 wiki stats
# Stats: Class, Cost, Shield, Max Weight, Self Weight, Availability
# Speed/Agility/Intelligence are extrapolated for our engine
# ─────────────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════
# LIGHT CHASSIS - Fast, low capacity, cheap, high agility
# ═══════════════════════════════════════════════════════════════════════
DLZ_100 = Chassis(
    name="DLZ-100",  # Light - Available at start
    weight_class=WeightClass.LIGHT,
    speed=55,
    rotation_speed=13,
    cost=3000,
    weight_capacity=16,
    self_weight=5,
    shielding=50,
    intelligence=5,
    agility=0.85,
    description="The classic starter chassis. Nimble and cost-effective for quick skirmishes.",
    center_x=-0.2,
    center_y=-0.8,
)

# ═══════════════════════════════════════════════════════════════════════
# MEDIUM CHASSIS - Balanced stats, moderate agility
# ═══════════════════════════════════════════════════════════════════════
DLZ_250 = Chassis(
    name="DLZ-250",  # Medium - Available at battle 3
    weight_class=WeightClass.MEDIUM,
    speed=50,
    rotation_speed=11,
    cost=4000,
    weight_capacity=22,
    self_weight=8,
    shielding=100,
    intelligence=5,
    agility=0.80,
    description="Upgraded chassis with better capacity and shielding.",
    center_x=0.0,
    center_y=-1.2,
)

# ═══════════════════════════════════════════════════════════════════════
# HEAVY CHASSIS - Slow but powerful, low agility
# ═══════════════════════════════════════════════════════════════════════
SMARTMOVE = Chassis(
    name="Smartmove",  # Heavy - Available at battle 5
    weight_class=WeightClass.HEAVY,
    speed=42,
    rotation_speed=9,
    cost=5500,
    weight_capacity=30,
    self_weight=10,
    shielding=200,
    intelligence=7,
    agility=0.65,
    description="A well-rounded heavy chassis with superior AI targeting systems.",
    center_x=-0.8,
    center_y=-1.5,
)

# ═══════════════════════════════════════════════════════════════════════
# ULTRA/ASSAULT CHASSIS - Maximum firepower platforms
# ═══════════════════════════════════════════════════════════════════════
CLR_Z050 = Chassis(
    name="CLR-Z050",  # Ultra - Available at battle 7
    weight_class=WeightClass.ASSAULT,
    speed=35,
    rotation_speed=8,
    cost=7500,
    weight_capacity=50,
    self_weight=15,
    shielding=400,
    intelligence=6,
    agility=0.55,
    description="Heavy-duty ultra chassis with excellent weight capacity.",
)

ELECTRON = Chassis(
    name="Electron",  # Ultra - Available at battle 10
    weight_class=WeightClass.ASSAULT,
    speed=33,
    rotation_speed=7,
    cost=8000,
    weight_capacity=64,
    self_weight=19,
    shielding=550,
    intelligence=8,
    agility=0.50,
    description="Top-tier ultra chassis with massive capacity and advanced AI.",
    center_x=-1.5,
    center_y=0.8,
)

DURICHAS = Chassis(
    name="Durichas",  # Ultra - Available at battle 11
    weight_class=WeightClass.ASSAULT,
    speed=24,
    rotation_speed=5,
    cost=12000,
    weight_capacity=70,
    self_weight=26,
    shielding=1200,
    intelligence=6,
    agility=0.30,
    description="Heavily armored assault platform. Built like a fortress.",
    center_x=-0.5,
    center_y=-1.0,
)

DELIVERANCE = Chassis(
    name="Deliverance",  # Ultra - Available at battle 14
    weight_class=WeightClass.ASSAULT,
    speed=22,
    rotation_speed=4,
    cost=13000,
    weight_capacity=85,
    self_weight=30,
    shielding=1000,
    intelligence=7,
    agility=0.25,
    description="The ultimate war machine. Unmatched weight capacity for maximum firepower.",
    center_x=0.5,
    center_y=-0.2,
)

# Collect all chassis into a list
CHASSIS: list[Chassis] = [
    DLZ_100,
    DLZ_250,
    SMARTMOVE,
    CLR_Z050,
    ELECTRON,
    DURICHAS,
    DELIVERANCE,
]

# ─────────────────────────────────────────────────────────────────────────────
# PLATING DEFINITIONS
# Based on original Bot Arena 3 wiki stats
# Stats: Material, Cost, Shield, Weight, Availability
# ─────────────────────────────────────────────────────────────────────────────

SANTRIN = Plating(
    name="Santrin",  # Fiberglass - Available at start
    shielding=200,
    cost=300,
    weight=3,
    description="Lightweight fiberglass plating. Decent protection without compromising speed.",
    center_x=-3.5,
    center_y=-3.0,
    weapon_mount_x=-3.8,
    weapon_mount_y=-3.2,
)

CHROMITREX = Plating(
    name="Chromitrex",  # Deflector - Available at start
    shielding=300,
    cost=550,
    weight=4,
    description="Deflector-class plating with superior energy dispersion.",
    center_x=-0.5,
    center_y=-2.8,
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
)

OVERWATCH_R200 = Plating(
    name="Overwatch R200",  # Deflector - Available at battle 1
    shielding=500,
    cost=800,
    weight=6,
    description="Military-grade deflector armor with excellent damage absorption.",
    center_x=-0.2,
    center_y=0.2,
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
)

GAIACORP_LB_MK2 = Plating(
    name="Gaiacorp LB-MK2",  # Deflector - Available at battle 3
    shielding=700,
    cost=1200,
    weight=8,
    description="Heavy deflector plating from Gaiacorp's defense line.",
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
    center_x=-0.2,
    center_y=-1.2,
)

OVERWATCH_R760 = Plating(
    name="Overwatch R760",  # Shielding - Available at battle 5
    shielding=900,
    cost=1600,
    weight=9,
    description="Advanced shielding technology with reactive armor layers.",
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
)

GAIACORP_SC_RS = Plating(
    name="Gaiacorp SC-RS",  # Shielding - Available at battle 7
    shielding=1300,
    cost=3000,
    weight=12,
    description="Premium shielding system for serious combatants.",
    weapon_mount_x=-1.2,
    weapon_mount_y=-0.2,
    center_x=-1.5,
    center_y=0.2,
)

GAIACORP_EG_PR = Plating(
    name="Gaiacorp EG-PR",  # Sentinel - Available at battle 9
    shielding=1700,
    cost=4500,
    weight=15,
    description="Sentinel-class armor. The choice of professional arena fighters.",
    weapon_mount_x=0.8,
    weapon_mount_y=-0.2,
    center_x=1.0,
    center_y=-0.2,
)

OVERWATCH_Z = Plating(
    name="Overwatch Z",  # Sentinel - Available at battle 11
    shielding=2000,
    cost=6000,
    weight=19,
    description="Top-of-the-line sentinel armor from Overwatch Industries.",
    center_x=0.0,
    center_y=0.0,
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
)

GAIACORP_EG_SR = Plating(
    name="Gaiacorp EG-SR",  # Guardian - Available at battle 12
    shielding=2450,
    cost=7800,
    weight=22,
    description="Guardian-class armor. Near-impenetrable defensive system.",
    weapon_mount_x=-4.5,
    weapon_mount_y=-0.8,
    center_x=-5.0,
    center_y=-1.0,
)

SHRED_MK3 = Plating(
    name="Shred-MK3",  # Guardian - Available at battle 14
    shielding=2950,
    cost=9500,
    weight=25,
    description="The ultimate in personal armor technology. Nothing hits harder.",
    center_x=-0.2,
    center_y=-0.8,
    weapon_mount_x=0.0,
    weapon_mount_y=0.0,
)

# Collect all plating into a list
PLATING: list[Plating] = [
    SANTRIN,
    CHROMITREX,
    OVERWATCH_R200,
    GAIACORP_LB_MK2,
    OVERWATCH_R760,
    GAIACORP_SC_RS,
    GAIACORP_EG_PR,
    OVERWATCH_Z,
    GAIACORP_EG_SR,
    SHRED_MK3,
]

# ─────────────────────────────────────────────────────────────────────────────
# COMPONENT DEFINITIONS (WEAPONS)
# Based on original Bot Arena 3 wiki stats
# Stats: Type, Cost, APM, DPS, DPM, Range, Weight, Availability
# DPM = Damage Per Minute = (APM * DPS)
# ─────────────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════
# STARTER WEAPONS - Available at start
# ═══════════════════════════════════════════════════════════════════════
ZINTEK = Component(
    name="Zintek",  # Basic gun - Available at start
    component_type=ComponentType.WEAPON,
    cost=250,
    weight=2,
    shots_per_minute=99,
    damage_per_shot=10,
    min_range=25,
    max_range=170,
    projectile_type=ProjectileType.LASER,
    description="Reliable starter weapon. High accuracy, moderate damage. DPM: 990",
    mount_x=-13.5,
    mount_y=-1.0,
)

KEDRON = Component(
    name="Kedron",  # Fireworks - Available at start
    component_type=ComponentType.WEAPON,
    cost=450,
    weight=3,
    shots_per_minute=376,
    damage_per_shot=9,
    min_range=0,
    max_range=120,
    projectile_type=ProjectileType.BULLET,
    description="Spray-and-pray flare weapon. Low accuracy but devastating up close. DPM: 3386",
    mount_x=-21.0,
    mount_y=-0.2,
)

RAPTOR_DT_01 = Component(
    name="Raptor DT-01",  # Blaster - Available at start
    component_type=ComponentType.WEAPON,
    cost=500,
    weight=3,
    shots_per_minute=79,
    damage_per_shot=35,
    min_range=50,
    max_range=150,
    projectile_type=ProjectileType.BULLET,
    description="Solid mid-range blaster with good accuracy. DPM: 2772",
    mount_x=-23.8,
    mount_y=-1.5,
)

# ═══════════════════════════════════════════════════════════════════════
# EARLY-MID GAME WEAPONS - Battle 2-6
# ═══════════════════════════════════════════════════════════════════════
RAPTOR_DT_02 = Component(
    name="Raptor DT-02",  # Blaster - Available at battle 2
    component_type=ComponentType.WEAPON,
    cost=700,
    weight=5,
    shots_per_minute=89,
    damage_per_shot=50,
    min_range=50,
    max_range=140,
    projectile_type=ProjectileType.BULLET,
    description="Upgraded Raptor with increased fire rate and damage. DPM: 4455",
    mount_x=-15.2,
    mount_y=-1.8,
)

TORRIKA_KJ_557 = Component(
    name="Torrika KJ-557",  # Jackhammer - Available at battle 2
    component_type=ComponentType.WEAPON,
    cost=900,
    weight=7,
    shots_per_minute=198,
    damage_per_shot=39,
    min_range=0,
    max_range=50,
    projectile_type=ProjectileType.SHOCKWAVE,
    description="Point-blank devastator using a hydraulic ram. Get close and melt them. DPM: 7722",
    mount_x=-12.8,
    mount_y=-4.0,
)

DARSIJ = Component(
    name="Darsij",  # Machine-gun - Available at battle 4
    component_type=ComponentType.WEAPON,
    cost=1100,
    weight=8,
    shots_per_minute=198,
    damage_per_shot=40,
    min_range=25,
    max_range=130,
    projectile_type=ProjectileType.BULLET,
    description="High-volume fire weapon. Hug enemies to maximize hits. DPM: 7920",
    mount_x=-18.2,
    mount_y=-0.8,
)

TORRIKA_KR_2 = Component(
    name="Torrika KR-2",  # Nailgun - Available at battle 6
    component_type=ComponentType.WEAPON,
    cost=1600,
    weight=10,
    shots_per_minute=238,
    damage_per_shot=45,
    min_range=30,
    max_range=140,
    projectile_type=ProjectileType.BULLET,
    description="Enhanced close-quarters weapon with extended range. DPM: 10692",
    mount_x=-18.5,
    mount_y=-2.0,
)

# ═══════════════════════════════════════════════════════════════════════
# MID-LATE GAME WEAPONS - Battle 8-11
# ═══════════════════════════════════════════════════════════════════════
ZENI_PRS = Component(
    name="Zeni PRS",  # Defense/Healer - Available at battle 8
    component_type=ComponentType.HEALER,
    cost=2000,
    weight=10,
    shots_per_minute=119,
    damage_per_shot=-65,  # Negative = healing (matches wiki DPS of 65
    mount_x=-22.5,
    mount_y=-0.8,
    min_range=0,
    max_range=125,
    projectile_type=ProjectileType.HEAL,
    description="Standard repair distributor. Keeps your team fighting. HPM: 7722",
)

DARSIK_B301_1 = Component(
    name="Darsik B301-1",  # Machine-gun - Available at battle 9
    component_type=ComponentType.WEAPON,
    cost=2200,
    weight=11,
    shots_per_minute=277,
    damage_per_shot=48,
    min_range=30,
    max_range=140,
    projectile_type=ProjectileType.BULLET,
    description="Rapid-fire beast. Low accuracy, massive potential. DPM: 13306",
    mount_x=-15.8,
    mount_y=-1.5,
)

PORANTIS = Component(
    name="Porantis",  # Cannon - Available at battle 9
    component_type=ComponentType.WEAPON,
    cost=2500,
    weight=13,
    shots_per_minute=99,
    damage_per_shot=145,
    min_range=40,
    max_range=160,
    projectile_type=ProjectileType.CANNON,
    description="Heavy hitter with solid accuracy at medium range. DPM: 14355",
    mount_x=-25.2,
    mount_y=-0.8,
)

CIRCES = Component(
    name="Circes",  # Plasma gun - Available at battle 10
    component_type=ComponentType.WEAPON,
    cost=3300,
    weight=15,
    shots_per_minute=59,
    damage_per_shot=260,
    min_range=50,
    max_range=200,
    projectile_type=ProjectileType.MISSILE,
    description="Slow but devastating plasma gun. Each shot counts. DPM: 15444",
    mount_x=-28.2,
    mount_y=-1.8,
)

ZENI_PRZ_2 = Component(
    name="Zeni PRZ-2",  # Defense/Healer - Available at battle 11
    component_type=ComponentType.HEALER,
    cost=4000,
    weight=18,
    shots_per_minute=158,
    damage_per_shot=-80,  # Negative = healing (matches wiki DPS of 80)
    min_range=10,
    max_range=135,
    projectile_type=ProjectileType.HEAL,
    description="Advanced repair distributor. Superior healing output. HPM: 12672",
    mount_x=-5.0,
    mount_y=-2.0,
)

# ═══════════════════════════════════════════════════════════════════════
# END GAME WEAPONS - Battle 12-15
# ═══════════════════════════════════════════════════════════════════════
DEVENGE = Component(
    name="Devenge",  # Rifle - Available at battle 12
    component_type=ComponentType.WEAPON,
    cost=5000,
    weight=20,
    shots_per_minute=59,
    damage_per_shot=320,
    min_range=70,
    max_range=200,
    projectile_type=ProjectileType.LASER,
    description="Precision strike rifle. High accuracy, massive damage. DPM: 19008",
    mount_x=-17.0,
    mount_y=-2.0,
)

DARSIK_R200 = Component(
    name="Darsik R200",  # Assault rifle - Available at battle 13
    component_type=ComponentType.WEAPON,
    cost=6100,
    weight=22,
    shots_per_minute=297,
    damage_per_shot=65,
    min_range=30,
    max_range=140,
    projectile_type=ProjectileType.BULLET,
    description="Massive fire rate weapon. Get close to maximize hits. DPM: 19305",
    mount_x=-15.8,
    mount_y=-3.0,
)

CEREBUS = Component(
    name="Cerebus",  # Teslacoil - Available at battle 13
    component_type=ComponentType.WEAPON,
    cost=7500,
    weight=25,
    shots_per_minute=99,
    damage_per_shot=220,
    min_range=5,
    max_range=220,
    projectile_type=ProjectileType.LASER,
    description="Legendary teslacoil weapon. Extreme accuracy and range. DPM: 21780",
    mount_x=-16.2,
    mount_y=-1.5,
)

SCREAM_SHARD = Component(
    name="Scream Shard",  # Laser - Available at battle 15
    component_type=ComponentType.WEAPON,
    cost=10000,
    weight=30,
    shots_per_minute=238,
    damage_per_shot=105,
    min_range=5,
    max_range=200,
    projectile_type=ProjectileType.MISSILE,
    description="The ultimate laser weapon. Unmatched damage output. DPM: 24948",
    mount_x=-12.5,
    mount_y=-1.0,
)

# Collect all components into a list
COMPONENTS: list[Component] = [
    ZINTEK,
    KEDRON,
    RAPTOR_DT_01,
    RAPTOR_DT_02,
    TORRIKA_KJ_557,
    DARSIJ,
    TORRIKA_KR_2,
    ZENI_PRS,
    DARSIK_B301_1,
    PORANTIS,
    CIRCES,
    ZENI_PRZ_2,
    DEVENGE,
    DARSIK_R200,
    CEREBUS,
    SCREAM_SHARD,
]


def get_starter_parts() -> tuple[list[str], list[str], list[str]]:
    """Return the names of parts that new players can purchase from the start.

    In original BA3, you start with one DLZ-100 chassis already equipped.
    Early game you can buy: Zintek, Kedron, Raptor DT-01, Santrin, Chromitrex
    """
    starter_chassis = ["DLZ-100"]
    starter_plating = ["Santrin", "Chromitrex"]
    starter_components = ["Zintek", "Kedron", "Raptor DT-01"]
    return starter_chassis, starter_plating, starter_components


def is_starter_part(part_name: str) -> bool:
    """Check if a part is available from the start (doesn't need to be unlocked)"""
    chassis, plating, components = get_starter_parts()
    return part_name in chassis or part_name in plating or part_name in components


def build_registry() -> "PartsRegistry":
    """Build and return a fully populated PartsRegistry with all parts."""
    from ..common.models import PartsRegistry  # noqa: F811

    registry = PartsRegistry()
    for chassis in CHASSIS:
        registry.register_chassis(chassis)
    for plating in PLATING:
        registry.register_plating(plating)
    for component in COMPONENTS:
        registry.register_component(component)
    return registry
