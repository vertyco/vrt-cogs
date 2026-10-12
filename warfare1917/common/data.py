"""Warfare 1917's numbers: units, soldiers, fire support, upgrades, XP, morale and the engine's constants.

Every value is copied from the original game's main script (written F5 below, with line numbers). A "step" is one
frame of the original's 35 frames a second. Plain tables: the rules that use them live in the battle code.
"""

FPS = 35  # swf frameRate
SLOW_TICK = 40  # slowEFcountMax, F5:6903
MEDIUM_TICK = 4  # mediumEFcountMax, F5:6905

SIDES = ("british", "german")

# Engine constants, F5:7232-7309 (defaults in the order the script declares them).
CONQUER_AREA = 150  # conquerWinArea, F5:7240
TARGETING_BUFFER = 120  # targetingBuffer, F5:7245
OFFICER_REACH = 150  # officerInfluence, F5:7246
OFFICER_RALLY_REACH = 250  # officerInfluence under British Officer Rally, F5:2288-2291
TRENCH_BOUNDARY = 120  # trenchBoundary, F5:7248
WIRE_SPEED = 1.5  # wireSpeedMod, F5:7249: a squad in wire moves at speed / 1.5
MINE_BOUNDARY = 60  # mineBoundary, F5:7250
MINE_CHANCE = 16  # mineDeathChance, F5:7252: one chance in 16
TRENCH_DEFENCE = 0.2  # trenchDefence, F5:7270: damage multiplier against an entrenched squad
TRENCH_BONUS = 1.3  # trenchBonus, F5:7271: damage multiplier for a shooter in a trench
OFFICER_BONUS = 1.5  # officerBonus, F5:7272: damage multiplier near an own officer
SURVIVAL_CHANCE = 10  # explosionSurvivalChance, F5:7275: one blast in 10 spares a squad in reach
BODY_FADE_MS = 15000  # clearDeadSoldierTime, F5:7274
GAS_DAMAGE = 0.4  # gasDamage, F5:7298: pool lost per step in a cloud
GAS_DETECT = 400  # gasDetectRange, F5:7300: a gas round this close lets the player's squads put masks on

# Soldier types in the order the page's type index uses (the original's type names, F5:7010-7231).
SOLDIER_TYPES = ("rifleman", "grenadier", "machineGunner", "mgAssist", "sharpShooter", "lieutenant", "tankMarkIV")

# Squad kinds in deploy slot order 1..6 (F5:7310-7360) and fire support kinds in HUD slot order 1..4.
UNIT_KINDS = ("riflemen", "assault", "machineGun", "sniper", "officer", "tank")
SUPPORT_KINDS = ("mortar", "artillery", "gas", "antiTank")

# Unit stats. members: soldier types in spawn order. hp: one soldier's health. pool: the squad's shared health
# (members + 1) x hp, except a tank's own health. speed: pixels a step. timer: deploy timer in steps.
# name: the HUD's name (checkUnitNames, F5:3870-3884). tooltip: F5:7310-7339 (\r there, \n here).
UNITS = {
    "british": {
        "riflemen": {  # F5:7010-7018
            "members": ("rifleman",) * 6,
            "hp": 40,
            "pool": 280,
            "speed": 1.8,
            "range": 450,
            "slot": 1,
            "name": "Riflemen",
            "tooltip": "Good vs Infantry. \nWeak vs Armor.",
            "timer": 300,
        },
        "assault": {  # F5:7024-7032
            "members": ("grenadier",) * 4,
            "hp": 150,
            "pool": 750,
            "speed": 2.1,
            "range": 450,
            "slot": 2,
            "name": "Assault Team",
            "tooltip": "Strong vs Entrenched.\nAverage vs Armor.",
            "timer": 420,
        },
        "machineGun": {  # F5:7039-7048
            "members": ("machineGunner", "rifleman", "rifleman"),
            "hp": 70,
            "pool": 280,
            "speed": 1.5,
            "range": 450,
            "slot": 3,
            "name": "Lewis Gunners",
            "tooltip": "Good vs Infantry \nwhen entrenched.",
            "timer": 600,
        },
        "sniper": {  # F5:7057-7066
            "members": ("sharpShooter",),
            "hp": 90,
            "pool": 180,
            "speed": 1.65,
            "range": 600,
            "slot": 4,
            "name": "Sharpshooter",
            "tooltip": "Strong vs Infantry \nat long range.",
            "timer": 800,
        },
        "officer": {  # F5:7074-7083
            "members": ("lieutenant",),
            "hp": 115,
            "pool": 230,
            "speed": 1.5,
            "range": 450,
            "slot": 5,
            "name": "Officer",
            "tooltip": "Adds morale. \nDamage bonus to soldiers.",
            "timer": 600,
        },
        "tank": {  # F5:7088-7098
            "members": ("tankMarkIV",),
            "hp": 850,
            "pool": 850,
            "speed": 0.5,
            "range": 650,
            "slot": 6,
            "name": "Mark IV Tank",
            "tooltip": "Strong vs All. Weak vs Fire support.",
            "timer": 1800,
        },
    },
    "german": {
        "riflemen": {  # F5:7139-7148
            "members": ("rifleman",) * 5,
            "hp": 45,
            "pool": 270,
            "speed": 1.8,
            "range": 450,
            "slot": 1,
            "name": "Riflemen",
            "tooltip": "Good vs Infantry. \nWeak vs Armor.",
            "timer": 300,
        },
        "assault": {  # F5:7154-7162
            "members": ("grenadier",) * 4,
            "hp": 165,
            "pool": 825,
            "speed": 2.1,
            "range": 450,
            "slot": 2,
            "name": "Sturmtruppen",
            "tooltip": "Strong vs Entrenched.\nAverage vs Armor.",
            "timer": 420,
        },
        "machineGun": {  # F5:7169-7178
            "members": ("machineGunner", "rifleman", "rifleman"),
            "hp": 70,
            "pool": 280,
            "speed": 1.5,
            "range": 450,
            "slot": 3,
            "name": "Machine Gun Team",
            "tooltip": "Good vs Infantry \nwhen entrenched.",
            "timer": 600,
        },
        "sniper": {  # F5:7187-7196
            "members": ("sharpShooter",),
            "hp": 90,
            "pool": 180,
            "speed": 1.65,
            "range": 600,
            "slot": 4,
            "name": "Sharpshooter",
            "tooltip": "Strong vs Infantry \nat long range.",
            "timer": 800,
        },
        "officer": {  # F5:7204-7213
            "members": ("lieutenant",),
            "hp": 115,
            "pool": 230,
            "speed": 1.5,
            "range": 450,
            "slot": 5,
            "name": "Officer",
            "tooltip": "Adds morale. \nDamage bonus to soldiers.",
            "timer": 600,
        },
        "tank": {  # F5:7218-7228
            "members": ("tankMarkIV",),
            "hp": 850,
            "pool": 850,
            "speed": 0.5,
            "range": 650,
            "slot": 6,
            "name": "A7V Tank",
            "tooltip": "Strong vs All. Weak vs Fire support.",
            "timer": 1800,
        },
    },
}

# Soldier types. damage: one shot (a machine gun's burst shot, a tank's machine gun shot). weapon: the sound stem
# (the original plays "sound_<weapon>_fire1" or "_fire2", F5:1580). xp: kill XP of the squad kind the type is built
# for; a kill's XP follows the dead soldier's squad (F5:2839, 3030), so use KILL_XP[squad kind] when scoring.
# mgAssist is declared but no squad spawns one; the German one has no damage in the original, so it is 0 here.
SOLDIERS = {
    "british": {
        "rifleman": {"damage": 15, "weapon": "enfield", "xp": 1},  # F5:7019-7023
        "grenadier": {"damage": 12, "weapon": "enfield", "xp": 2},  # F5:7033-7038
        "machineGunner": {"damage": 5, "weapon": "lewis", "xp": 5},  # F5:7049-7052
        "mgAssist": {"damage": 1.25, "weapon": "pistol", "xp": 5},  # F5:7053-7056
        "sharpShooter": {"damage": 70, "weapon": "enfieldSniper", "xp": 5},  # F5:7067-7073
        "lieutenant": {"damage": 6, "weapon": "pistol", "xp": 10},  # F5:7084-7087
        "tankMarkIV": {"damage": 4, "weapon": "tankMG", "xp": 15},  # F5:7099-7102
    },
    "german": {
        "rifleman": {"damage": 15, "weapon": "mauser", "xp": 1},  # F5:7149-7153
        "grenadier": {"damage": 15, "weapon": "mauser", "xp": 2},  # F5:7163-7168
        "machineGunner": {"damage": 6, "weapon": "lewis", "xp": 5},  # F5:7179-7183
        "mgAssist": {"damage": 0, "weapon": "pistol", "xp": 5},  # F5:7184-7186
        "sharpShooter": {"damage": 70, "weapon": "mauserSniper", "xp": 5},  # F5:7197-7203
        "lieutenant": {"damage": 6, "weapon": "pistol", "xp": 10},  # F5:7214-7217
        "tankMarkIV": {"damage": 4, "weapon": "tankMG", "xp": 15},  # F5:7229-7231
    },
}

# Damage a blast does to a tank, before upgrades (F5:6976-7009 and the German copies F5:7106-7138).
BLAST_TANK_DAMAGE = {
    side: {"mortar": 250, "artillery": 500, "antiTank": 450, "grenade": 65, "tankShell": 200, "mine": 150}
    for side in SIDES
}

# Fire support. rounds: base rounds a strike fires (F5:7288-7291). gap: spacing between rounds, in steps
# (gas: milliseconds), F5:3453-3622. first_gap: a round's random extra delay is random(first_gap) (steps; gas
# milliseconds). scatter: a round lands at the target x + random(2 x scatter) - scatter (F5:3456-3604).
# tank_damage: what one round does to a tank. timer: recharge in steps (F5:7345-7360). cloud_steps: how long a gas
# cloud lasts (F5:6999, 7128). The first support is never ready at the start (F5:4028).
SUPPORTS = {
    side: {
        "mortar": {  # F5:3513-3569
            "rounds": 8,
            "gap": 70,
            "first_gap": 20,
            "scatter": 125,
            "tank_damage": BLAST_TANK_DAMAGE[side]["mortar"],
            "timer": 2000,
            "name": "Mortar Strike",
            "tooltip": "Medium explosive.\nGood vs exposed infantry.",
        },
        "artillery": {  # F5:3453-3511
            "rounds": 8,
            "gap": 90,
            "first_gap": 30,
            "scatter": 125,
            "tank_damage": BLAST_TANK_DAMAGE[side]["artillery"],
            "timer": 4000,
            "name": "Artillery Strike",
            "tooltip": "Heavy bombardment.\nGood vs All units.",
        },
        "gas": {  # F5:3612-3629
            "rounds": 2,
            "gap": 1100,
            "first_gap": 800,
            "scatter": 125,
            "tank_damage": 0,
            "timer": 2500,
            "name": "Gas",
            "tooltip": "Poison gas attack.\nGood vs Infantry.",
            "cloud_steps": 450 if side == "british" else 350,
        },
        "antiTank": {  # F5:3570-3609
            "rounds": 5,
            "gap": 70,
            "first_gap": 20,
            "scatter": 125,
            "tank_damage": BLAST_TANK_DAMAGE[side]["antiTank"],
            "timer": 1500,
            "name": "Anti-Tank",
            "tooltip": "Anti-tank cannon.\nDirect fire.",
        },
    }
    for side in SIDES
}

# The 22 upgrades (F5:4688-5007): number, name, text (what the details panel shows under the name), effect (the
# panel's "Effect:" line) and cost. row and column place the button in the upgrade screen's grid (sprite 1180):
# rows 1 and 2 hold 4 buttons each, row 3 holds 3 that sit between the columns above them. Numbers 1 to 11 are the
# Infantry & Armour tree, 12 to 22 the Fire Support tree.
UPGRADE_GRID = {
    1: (1, 1),
    2: (1, 2),
    3: (1, 3),
    4: (1, 4),
    5: (2, 1),
    6: (2, 2),
    7: (2, 3),
    8: (2, 4),
    9: (3, 1),
    10: (3, 2),
    11: (3, 3),
    12: (1, 1),
    13: (1, 2),
    14: (1, 3),
    15: (1, 4),
    16: (2, 1),
    17: (2, 2),
    18: (2, 3),
    19: (2, 4),
    20: (3, 1),
    21: (3, 2),
    22: (3, 3),
}

# (number, name, text, effect, cost)
BRITISH_UPGRADE_ROWS = (
    (1, "RALLY", "Reinforcements will arrive quicker for all infantry.", "10% faster reinforcement", 1),  # F5:4688-4767
    (2, "BALLISTICS", "All Infantry armed with rifles will inflict more damage.", "+15% Damage to Rifles", 1),
    (3, "HARD HEADED", "All Infantry soldiers gain a slight defensive bonus.", "+10% to Defence", 1),
    (4, "MORALE BOOST", "Your men recieve an extra ration of rum before each fight.", "15% boost to Morale", 1),
    (5, "POST HASTE", "Decreases the reinforcment time for all units even further.", "15% faster reinforcement", 2),
    (
        6,
        "HIGH EXPLOSIVE",
        "Our engineers have tweaked the Mills bomb to pack more of a punch.",
        "Larger area of effect for grenades.",
        2,
    ),
    (
        7,
        "ENTRENCHED",
        "Infantry have been trained in defending themselves better in the trenches.",
        "+10% Defence when Entrenched",
        2,
    ),
    (8, "OFFICER RALLY", "Your officers will take command over larger numbers of men.", "Larger bonus area", 2),
    (
        9,
        "RANGE TRAINING",
        "Your Sharpshooters have spent time training on the range.",
        "+50% Damage for Sharpshooters",
        3,
    ),
    (
        10,
        "FIRE SUPPORT",
        "Gunner crews are trained together to provide more deadly fire support.",
        "+30% Damage for Lewis Gunners",
        3,
    ),
    (11, "TANK COMMAND", "Tanks deal more damage and take less.", "+25% Damage and Defence", 3),
)
GERMAN_UPGRADE_ROWS = (
    (
        1,
        "BALLISTICS",
        "All Infantry armed with rifles will inflict more damage.",
        "+15% Damage to Rifles",
        1,
    ),  # F5:4848-4927
    (
        2,
        "TRENCH ARMOUR",
        "Our engineers have designed armor to protect our men better.",
        "+10% to Defence",
        1,
    ),
    (3, "REINFORCEMENTS", "Additional reinforcements have been allotted to our fight", "10% faster reinforcement", 1),
    (4, "FOR THE KAISER", "Our men are inspired by the Kaiser.", "15% boost to Morale", 1),
    (
        5,
        "MACHINE GUN TRENCH",
        "Our Machine Gun teams have been training in operating in trenches.",
        "+15% Damage when Entrenched",
        2,
    ),
    (6, "ENTRENCH", "Trenches are more secure now providing better cover.", "+10% Defence when Entrenched", 2),
    (7, "RAPID DEPLOYMENT", "Reinforcements arrive even faster.", "15% faster reinforcement", 2),
    (8, "FOR THE FATHERLAND", "Our men will die for our country.", "20% boost to Morale", 2),
    (9, "STURMTRUPPEN", "Our Sturmtruppen are a tool of destruction.", "+30% Damage for Sturmtruppen", 3),
    (
        10,
        "INDUSTRIAL ACTION",
        "Our engineers are able to supply us with Tanks much faster.",
        "+25% faster reinforcement of Tanks",
        3,
    ),
    (
        11,
        "GREAT LEADER",
        "Our Officers provide great leadership to our men.",
        "+30% Damage bonus to surrounding men",
        3,
    ),
)
# The Fire Support tree is the same for both sides (F5:4768-4847 British, F5:4928-5007 German).
SUPPORT_UPGRADE_ROWS = (
    (
        12,
        "MORTAR ACCURACY",
        "Mortar crews will fire far more accurately at designated targets.",
        "+25% more Accurate",
        1,
    ),
    (13, "MORTAR BARRAGE", "Increases the amount of rounds fired in a single mortar strike.", "Additional Rounds", 1),
    (14, "HEAVY MORTAR", "Mortar shells are far more effective against tanks.", "+30% Damage to Tanks", 1),
    (15, "TOXIC GAS", "Our gas make up has been altered to be more effective.", "+25% Damage", 1),
    (
        16,
        "ARTILLERY ACCURACY",
        "Artillery crews fire more accurately on designated targets.",
        "+25% more Accurate",
        2,
    ),
    (
        17,
        "ARTILLERY BARRAGE",
        "Increases the amount of rounds fired in a single artillery strike.",
        "Additional Rounds",
        2,
    ),
    (
        18,
        "HEAVY ARTILLERY",
        "Artillery and Anti-Tank shells are more effective against hard targets.",
        "+30% Damage to Tanks",
        2,
    ),
    (19, "LINGERING GAS", "Our gas has been reformulated to hang longer in the air.", "+30% Duration", 2),
    (20, "RESUPPLY", "All types of fire support resupply are shortened significantly.", "+40% faster Resupply", 3),
    (
        21,
        "BARRAGE OF FIRE",
        "Makes artillery strikes long and intense barrages which will decimate the enemy.",
        "Additional Rounds",
        3,
    ),
    (22, "ANTI-TANK BARRAGE", "Anti-tank batteries will fire more rounds at enemy tanks.", "Additional Rounds", 3),
)


def upgrade_table(rows):
    return {
        number: {
            "number": number,
            "name": name,
            "text": text,
            "effect": effect,
            "cost": cost,
            "row": UPGRADE_GRID[number][0],
            "column": UPGRADE_GRID[number][1],
        }
        for number, name, text, effect, cost in rows
    }


UPGRADES = {
    "british": upgrade_table(BRITISH_UPGRADE_ROWS + SUPPORT_UPGRADE_ROWS),
    "german": upgrade_table(GERMAN_UPGRADE_ROWS + SUPPORT_UPGRADE_ROWS),
}

# What it takes to open an upgrade (checkUpgrades, F5:5079-5150). Numbers not listed are open from the start. Each
# entry is a list of alternatives, and one alternative is a set of upgrades that must all be owned: a second-row
# upgrade needs the one above it, a third-row upgrade needs either full column above it. The buy check (F5:5151-5163)
# also needs the upgrade unowned and enough points.
UPGRADE_NEEDS = {
    5: ((1,),),
    6: ((2,),),
    7: ((3,),),
    8: ((4,),),
    9: ((1, 5), (2, 6)),
    10: ((2, 6), (3, 7)),
    11: ((3, 7), (4, 8)),
    16: ((12,),),
    17: ((13,),),
    18: ((14,),),
    19: ((15,),),
    20: ((12, 16), (13, 17)),
    21: ((13, 17), (14, 18)),
    22: ((14, 18), (15, 19)),
}

# Every multiplier or amount an upgrade brings, by what it does. numbers: which upgrade number gives it, per side
# (a side missing from numbers cannot get it). value: the amount. The rules read these only for the side that owns
# the upgrade (spec 3.19). Where an effect's value reads as a multiplier it multiplies the thing it names.
UPGRADE_EFFECTS = {
    "timer_10": {"numbers": {"british": 1, "german": 3}, "value": 0.9},  # unit timers x0.9, never the tank's
    "timer_15": {"numbers": {"british": 5, "german": 7}, "value": 0.85},  # unit timers x0.85, never the tank's
    "tank_timer": {"numbers": {"german": 10}, "value": 0.75},  # the tank's timer x0.75
    "rifle_damage": {"numbers": {"british": 2, "german": 1}, "value": 1.15},  # rifle soldiers' shots
    "defence": {"numbers": {"british": 3, "german": 2}, "value": 0.9},  # enemy shots at this side's squads
    "entrenched_defence": {"numbers": {"british": 7, "german": 6}, "value": 0.9},  # shots at its entrenched squads
    "morale_15": {"numbers": {"british": 4, "german": 4}, "value": 1.15},  # morale maximum
    "morale_20": {"numbers": {"german": 8}, "value": 1.2},  # morale maximum, stacks with morale_15
    "grenade_width": {"numbers": {"british": 6}, "value": 3},  # British grenades' blast box width
    "officer_reach": {"numbers": {"british": 8}, "value": OFFICER_RALLY_REACH},  # replaces OFFICER_REACH
    "sniper_damage": {"numbers": {"british": 9}, "value": 1.5},  # sharpshooters' shots
    "machine_gun_damage": {"numbers": {"british": 10}, "value": 1.3},  # machine gunners' shots
    "tank_damage": {"numbers": {"british": 11}, "value": 1.25},  # tank machine gun shots and tank shells on tanks
    "tank_defence": {"numbers": {"british": 11}, "value": 0.8},  # damage this side's tanks take from bullets and blasts
    "machine_gun_trench": {"numbers": {"german": 5}, "value": 1.15},  # machine gunner's shots from a trench
    "assault_damage": {"numbers": {"german": 9}, "value": 1.3},  # assault soldiers' shots
    "great_leader": {"numbers": {"german": 11}, "value": 1.3},  # shots near an officer, on top of OFFICER_BONUS
    "mortar_scatter": {"numbers": {"british": 12, "german": 12}, "value": 0.75},  # mortar and anti-tank scatter
    "mortar_rounds": {"numbers": {"british": 13, "german": 13}, "value": 5},  # extra mortar rounds
    "mortar_tank_damage": {"numbers": {"british": 14, "german": 14}, "value": 1.3},  # mortar damage to tanks
    "toxic_gas": {"numbers": {"british": 15, "german": 15}, "value": 1.25},  # GAS_DAMAGE x1.25, once
    "artillery_scatter": {"numbers": {"british": 16, "german": 16}, "value": 0.75},
    "artillery_rounds": {"numbers": {"british": 17, "german": 17}, "value": 3},  # extra artillery rounds
    "artillery_tank_damage": {"numbers": {"british": 18, "german": 18}, "value": 1.3},  # artillery and anti-tank
    "gas_time": {"numbers": {"british": 19, "german": 19}, "value": 1.3},  # gas cloud duration
    "resupply": {"numbers": {"british": 20, "german": 20}, "value": 0.6},  # support recharge
    "barrage_rounds": {"numbers": {"british": 21, "german": 21}, "value": 10},  # extra artillery rounds
    "anti_tank_rounds": {"numbers": {"british": 22, "german": 22}, "value": 5},  # extra anti-tank rounds
}

# XP. A level is reached when XP goes above the threshold (F5:7946); each level gives one upgrade point.
LEVELS = (15, 45, 90, 150, 225, 315, 420, 540, 675, 825, 990, 1170, 1390, 1615, 1855, 2110, 2880, 3165, 3465)
# Kill XP by the dead soldier's squad kind (updateExperience, F5:5969-6005).
KILL_XP = {"riflemen": 1, "assault": 2, "machineGun": 5, "sniper": 5, "officer": 10, "tank": 15}

# Morale (moraleCost F5:7917-7924, adjustMorale F5:5508-5625). A soldier killed by a bullet or gas costs its side
# `soldier`, and the other side gains soldier x BULLET_GAIN; by a blast it costs soldier x BLAST_LOSS and the other
# side gains soldier x BLAST_GAIN. An officer costs officer (a blast: officer x BLAST_LOSS) and gives the other side
# nothing. A destroyed tank costs `tank` and gives the other side `tank_killed`. `friendly_fire` is lost on top when
# a side's own blast kills its own soldier. `officer_bonus` and `tank_bonus` are gained by the deploying side.
MORALE_COST = {
    "soldier": 2,
    "officer": 5,
    "tank": 40,
    "tank_killed": 20,
    "friendly_fire": 10,
    "officer_bonus": 10,
    "tank_bonus": 10,
}
BLAST_LOSS = 1.3  # F5:5535-5540, 5590-5596
BULLET_GAIN = 0.5  # F5:5579, 5585: soldier / 2
BLAST_GAIN = 1.0
GROUND_FACTOR = 1.05  # a side's morale x1.05 each time its front passes a ground mark, F5:5555-5560
# Percent of the field a side's front must pass for its morale boost, each once (groundMorale, F5:7927).
GROUND_MARKS = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95)
# Morale regeneration per slow tick by ground held: (lowest percent held, rate), F5:5636-5671, with the original's
# holes closed upward.
REGEN_RATES = (
    (0, 1.005),
    (10, 1.0075),
    (20, 1.01),
    (30, 1.0125),
    (40, 1.015),
    (50, 1.02),
    (60, 1.025),
    (70, 1.03),
    (80, 1.035),
)


def regen_rate(ground):
    rate = REGEN_RATES[0][1]
    for low, value in REGEN_RATES:
        if ground >= low:
            rate = value
    return rate
