"""Warfare 1944's numbers: units, soldiers, costs, covers, fire support, orders, upgrades, XP, morale and the engine's
constants.

Every value is copied from the original game's main script (written F6 below, with line numbers). A "step" is one
frame of the original's 30 frames a second. Plain tables: the rules that use them live in the battle code. The
American side is called `british` everywhere, as in the original's code.
"""

FPS = 30  # swf frameRate
FIND_TICK = 18  # findEFcountMax, F6:10104
MEDIUM_TICK = 5  # mediumEFcountMax, F6:10102
SLOW_TICK = 30  # slowEFcountMax, F6:10100
SECOND_TICK = 30  # secondEFcountMax, F6:10105
REALLY_SLOW_TICK = 120  # rslowEFcountMax, F6:10098

SIDES = ("british", "german")

# Deploy slots 1..8 in the HUD's order (setButtonSlotValues, F6:5765-5811). The unit's squad kind is its key.
UNIT_KINDS = ("riflemen", "assault", "machineGun", "sniper", "bazooka", "mortarTeam", "officer", "tank")

# The four support toggles of a Custom Battle, in the order of the settings dict: Throw Grenade, Throw Smoke, Call Air
# Support and Call Artillery (skirmishUpgrade12active, 16, 14 and 18, F6:11830-11833 and showUnitControls, F6:6224-6246).
SUPPORT_KINDS = ("grenade", "smoke", "airSupport", "artillery")

# Engine constants (F6:10835-10952, listed in the order the script declares them)
LANES = (145, 230, 316)  # deploymentZone1..3, F6:10835-10837: each lane's centre line
LANE_HEIGHT = 70  # deployZoneHeight, F6:10844
SMOKED = 0.3  # smokedEffect, F6:10850: a smoked squad's bullets do x0.3
CONQUER_AREA = 150  # conquerWinArea, F6:10851
SLOW_BURST = 210  # slowBurstRate, F6:10855
MED_BURST = 160  # medBurstRate, F6:10856
HIGH_BURST = 60  # highBurstRate, F6:10857
MIN_WAIT = 90  # minWait, F6:10858
MOVE_MODIFIER = 0.75  # moveModifier, F6:10860: a soldier walks at speed x 0.75
TARGETING_BUFFER = 30  # targetingBuffer, F6:10862
OFFICER_REACH = 150  # officerInfluence, F6:10864
COVER_REACH = 100  # trenchBoundary, F6:10866: a cover 1 to 100 px ahead of the leader is near
WIRE_SPEED = 1.5  # wireSpeedMod, F6:10867: a squad in wire moves at speed / 1.5
MINE_BOUNDARY = 60  # mineBoundary, F6:10868
MINE_CHANCE = 16  # mineDeathChance, F6:10870: one chance in 16
DAMAGE_MODIFIER = 1.3  # damageModifier, F6:10916: the pool loss of a bullet
OFFICER_BONUS = 1.5  # officerBonus, F6:10923: damage multiplier near an own officer
BODY_FADE_MS = 15000  # clearDeadSoldierTime, F6:10925
SURVIVAL_CHANCE = 9  # explosionSurvivalChanceBase, F6:10926: a squad in reach is hit unless random(9) is 0
BLAST_REACH = 80  # a squad whose leader is within 80 px in x and in y of a blast is in reach, F6:4551-4553
SUPPLY = 200  # startingSupplyPoints, F6:10185: the RP each side gets at a refill
SUPPLY_TICKS = 8  # supplyTimerMax 7, F6:10195: the timer fires below 0, so every 8th slow tick
TANK_DAMAGE_CHANCE = 100  # tankDamageChance, F6:11837: out of 1000
ENGINE_BROKEN = 2  # tankEngineBrokenEffect, F6:11838: a broken engine divides the speed by 2

# Morale. moraleCost F6:11727-11735, adjustMorale F6:8212-8381, moraleRegen F6:8382-8410. A soldier killed by a bullet
# costs its side `soldier`, and the other side gains soldier x BULLET_GAIN; by a blast it costs the same and the other
# side gains soldier x BLAST_GAIN. An officer costs `officer` (a blast: officer x OFFICER_BLAST) and gives the other
# side nothing. `friendly_fire` is lost on top when a side's own blast kills its own soldier. `officer_bonus` and
# `tank_bonus` are gained by the deploying side.
MORALE_COST = {
    "soldier": 2,
    "officer": 5,
    "tank": 40,
    "tank_killed": 20,
    "bunker": 100,
    "bunker_killed": 100,
    "friendly_fire": 10,
    "officer_bonus": 10,
    "tank_bonus": 10,
}
OFFICER_BLAST = 1.3  # F6:8228
BULLET_GAIN = 0.5  # soldier / 2, F6:8334
BLAST_GAIN = 1.0  # F6:8343
REGEN_PLUS = 1.01  # moraleRegenPlus, F6:11703
REGEN_MINUS = 0.99  # moraleRegenMinus, F6:11704
FLANK_LOSS = 0.2  # moraleHitFlanked, F6:11705: a share of the flanked side's maximum
MESSAGE_COOLDOWN_S = 15  # the quick messages' setTimeout of 15000 ms, F6:8329-8380
OBJECTIVE_DELAY_MS = 3000  # an objective squad's wipe-out ends the battle 3 s later, F6:4703
BONUS_XP_RATE = 5  # bonus XP per covers held, kill lead and mission number, F6:7059, 7072

# Difficulty (F6:4008-4015, 4096-4103, 4406-4416): the player's bullets' share of the pool loss, and the factors on
# the CPU's gap between squads and between fire support calls.
DIFFICULTY = {
    "recruit": {"bullets": 1.1, "squad_gap": 1.3, "support_gap": 1.4},
    "regular": {"bullets": 1.0, "squad_gap": 1.0, "support_gap": 1.0},
    "hardened": {"bullets": 0.91, "squad_gap": 0.75, "support_gap": 0.5},
}

# Soldier types in the order the page's type index uses (the types the 16 squads and the bunker are made of).
SOLDIER_TYPES = (
    "rifleman",
    "carbine",
    "thompson",
    "BAR",
    "volksgrenadier",
    "grenadier",
    "machineGunner",
    "sharpShooter",
    "bazookaMan",
    "mortarCarrier",
    "lieutenant",
    "tankMarkIV",
    "bunkerBase",
)

# The buttons of the INTEL panel (the *_description lines, F6:11006-11012).
ORDER_TEXT = {
    "advance": "Advance",
    "artillery": "Call Artillery Strike - 500 RP",
    "airSupport": "Call Air Support - 300 RP",
    "grenade": "Throw Grenade - 50 RP",
    "smoke": "Throw Smoke Grenade - 50 RP",
    "suppress": "Suppressing Fire",
    "smokeRounds": "Smoke Mortar Rounds - 100 RP",
}
# What an order costs in RP: setUnitCosts F6:1278-1302, S666/frame_1436 for a grenade and a smoke grenade, and 100 for
# a smoke rounds order.
ORDER_COSTS = {"artillery": 500, "airSupport": 300, "grenade": 50, "smoke": 50, "smokeRounds": 100}
# The upgrade slot that unlocks a button (showUnitControls, F6:6247-6299); Advance and Suppressing Fire need none.
ORDER_UNLOCKS = {"grenade": 12, "airSupport": 14, "smoke": 16, "smokeRounds": 17, "artillery": 18}

# The HUD's names, tooltips and costs are the same for both sides; the German side's names differ for slots 2, 3, 5 and
# 8 (checkUnitNames, F6:5813-5832). Cost: setUnitCosts F6:1278-1302. Cooldown in steps: resupply_*, F6:10200-10207.
# Pool: the squad's shared health, (members + 1) x hp, except a tank's own health (F6:10285, 10322 and siblings).
#   members: soldier types in spawn order. hp: one soldier's health. squad_name: the INTEL panel's name for the squad.
#   intel: the INTEL panel's line. orders: the INTEL buttons (Advance first, F6:1566). kill_xp: updateExperience,
#   F6:8784-8815; a tank pays none (spec 3.18).
UNITS = {
    "british": {
        "riflemen": {  # F6:10276-10288
            "members": ("rifleman",) * 5,
            "hp": 40,
            "pool": 240,
            "speed": 2.2,
            "range": 450,
            "slot": 1,
            "cost": 200,
            "cooldown": 200,
            "name": "Riflemen",
            "squad_name": "Riflemen",
            "tooltip": "Good vs Infantry. \nWeak vs Armor.",
            "intel": "Effective in most situations. Good vs Infantry. Weak vs Armor.",
            "orders": ("advance", "grenade", "smoke"),
            "kill_xp": 1,
        },
        "assault": {  # F6:10313-10325
            "members": ("carbine", "thompson", "BAR", "thompson"),
            "hp": 95,
            "pool": 475,
            "speed": 2.55,
            "range": 450,
            "slot": 2,
            "cost": 300,
            "cooldown": 400,
            "name": "Assault Team",
            "squad_name": "Assault Team",
            "tooltip": "Strong vs Entrenched.\nAverage vs Armor.",
            "intel": "Good vs Infantry in cover. Weak vs Armor.",
            "orders": ("advance", "suppress", "grenade", "smoke"),
            "kill_xp": 2,
        },
        "machineGun": {  # F6:10332-10345
            "members": ("machineGunner", "rifleman"),
            "hp": 70,
            "pool": 210,
            "speed": 1.8,
            "range": 450,
            "slot": 3,
            "cost": 400,
            "cooldown": 800,
            "name": ".30 Cal",
            "squad_name": ".30 cal Team",
            "tooltip": "Good vs Infantry \nwhen entrenched.",
            "intel": "Good vs Infantry when in cover. Weak vs Armor.",
            "orders": ("advance", "suppress"),
            "kill_xp": 5,
        },
        "sniper": {  # F6:10355-10368
            "members": ("sharpShooter",),
            "hp": 70,
            "pool": 140,
            "speed": 2,
            "range": 600,
            "slot": 4,
            "cost": 500,
            "cooldown": 800,
            "name": "Sniper",
            "squad_name": "Sniper",
            "tooltip": "Strong vs Infantry at \nlong range.",
            "intel": "Long range infantry. Strong vs Infantry. Weak vs Armor.",
            "orders": ("advance", "smoke"),
            "kill_xp": 5,
        },
        "bazooka": {  # F6:10432-10442
            "members": ("bazookaMan", "rifleman"),
            "hp": 80,
            "pool": 240,
            "speed": 1.8,
            "range": 400,
            "slot": 5,
            "cost": 400,
            "cooldown": 700,
            "name": "Bazooka Team",
            "squad_name": "Bazooka Team",
            "tooltip": "Anti-tank team. \nStrong vs Armor.",
            "intel": "Anti-tank team. Average vs Infantry. Strong vs Armor.",
            "orders": ("advance",),
            "kill_xp": 5,
        },
        "mortarTeam": {  # F6:10396-10409
            "members": ("mortarCarrier",),
            "hp": 45,
            "pool": 90,
            "speed": 1.8,
            "range": 1600,
            "slot": 6,
            "cost": 500,
            "cooldown": 1100,
            "name": "Mortar Team",
            "squad_name": "Mortar Team",
            "tooltip": "Light Artillery. \nAverage vs All.",
            "intel": "Light artillery. Strong vs Infantry. Average vs Armor.",
            "orders": ("advance", "smokeRounds"),
            "kill_xp": 5,
        },
        "officer": {  # F6:10376-10389
            "members": ("lieutenant",),
            "hp": 115,
            "pool": 230,
            "speed": 1.8,
            "range": 450,
            "slot": 7,
            "cost": 300,
            "cooldown": 900,
            "name": "Officer",
            "squad_name": "Lieutenant",
            "tooltip": "Has fire support. \nProvides morale boost.",
            "intel": "Command unit. Has control of fire support.",
            "orders": ("advance", "airSupport", "artillery", "smoke"),
            "kill_xp": 10,
        },
        "tank": {  # F6:10451-10462
            "members": ("tankMarkIV",),
            "hp": 950,
            "pool": 950,
            "speed": 1,
            "range": 700,
            "slot": 8,
            "cost": 800,
            "cooldown": 2000,
            "name": "Sherman Tank",
            "squad_name": "M4A1 Sherman Tank",
            "tooltip": "Strong vs All. \nWeak vs Fire support.",
            "intel": "Tank. Strong vs Infantry. Strong vs Armor.",
            "orders": (),
            "kill_xp": 0,
        },
    },
    "german": {
        "riflemen": {  # F6:10525-10538
            "members": ("rifleman",) * 4,
            "hp": 45,
            "pool": 225,
            "speed": 2.2,
            "range": 450,
            "slot": 1,
            "cost": 200,
            "cooldown": 200,
            "name": "Riflemen",
            "squad_name": "Riflemen",
            "tooltip": "Good vs Infantry. \nWeak vs Armor.",
            "intel": "Rifle team. Average vs Infantry. Weak vs Armor.",
            "orders": ("advance", "grenade", "smoke"),
            "kill_xp": 1,
        },
        "assault": {  # F6:10544-10556
            "members": ("volksgrenadier", "volksgrenadier", "grenadier", "grenadier"),
            "hp": 95,
            "pool": 475,
            "speed": 2.55,
            "range": 450,
            "slot": 2,
            "cost": 300,
            "cooldown": 400,
            "name": "Sturmtruppen",
            "squad_name": "Assault Team",
            "tooltip": "Strong vs Entrenched.\nAverage vs Armor.",
            "intel": "Assault team. Strong vs Infantry in cover. Weak vs Armor.",
            "orders": ("advance", "suppress", "grenade", "smoke"),
            "kill_xp": 2,
        },
        "machineGun": {  # F6:10569-10582
            "members": ("machineGunner", "rifleman"),
            "hp": 70,
            "pool": 210,
            "speed": 1.8,
            "range": 450,
            "slot": 3,
            "cost": 400,
            "cooldown": 800,
            "name": "MG34 Team",
            "squad_name": "MG34 Team",
            "tooltip": "Good vs Infantry \nwhen entrenched.",
            "intel": "MG34 Team. Strong vs Infantry. Weak vs Armor.",
            "orders": ("advance", "suppress"),
            "kill_xp": 5,
        },
        "sniper": {  # F6:10592-10602
            "members": ("sharpShooter",),
            "hp": 90,
            "pool": 180,
            "speed": 2,
            "range": 600,
            "slot": 4,
            "cost": 500,
            "cooldown": 800,
            "name": "Sniper",
            "squad_name": "Sharpshooter",
            "tooltip": "Strong vs Infantry at \nlong range.",
            "intel": "Long range infantry. Strong vs Infantry. Weak vs Armor.",
            "orders": ("advance", "smoke"),
            "kill_xp": 5,
        },
        "bazooka": {  # F6:10666-10676
            "members": ("bazookaMan", "rifleman"),
            "hp": 80,
            "pool": 240,
            "speed": 1.8,
            "range": 400,
            "slot": 5,
            "cost": 400,
            "cooldown": 700,
            "name": "Panzershreck",
            "squad_name": "Panzershreck Team",
            "tooltip": "Anti-tank team. \nStrong vs Armor.",
            "intel": "Anti-tank team. Average vs Infantry. Strong vs Armor.",
            "orders": ("advance",),
            "kill_xp": 5,
        },
        "mortarTeam": {  # F6:10647-10657
            "members": ("mortarCarrier",),
            "hp": 45,
            "pool": 90,
            "speed": 1.8,
            "range": 1600,
            "slot": 6,
            "cost": 500,
            "cooldown": 1100,
            "name": "Mortar Team",
            "squad_name": "Mortar Team",
            "tooltip": "Light Artillery. \nAverage vs All.",
            "intel": "Light artillery. Strong vs Infantry. Average vs Armor.",
            "orders": ("advance", "smokeRounds"),
            "kill_xp": 5,
        },
        "officer": {  # F6:10610-10626
            "members": ("lieutenant",),
            "hp": 115,
            "pool": 230,
            "speed": 1.8,
            "range": 450,
            "slot": 7,
            "cost": 300,
            "cooldown": 900,
            "name": "Officer",
            "squad_name": "Officer",
            "tooltip": "Has fire support. \nProvides morale boost.",
            "intel": "Command unit. Has access to fire support.",
            "orders": ("advance", "airSupport", "artillery", "smoke"),
            "kill_xp": 10,
        },
        "tank": {  # F6:10685-10696
            "members": ("tankMarkIV",),
            "hp": 1000,
            "pool": 1000,
            "speed": 1,
            "range": 650,
            "slot": 8,
            "cost": 800,
            "cooldown": 2000,
            "name": "Panzer III",
            "squad_name": "Panzer III",
            "tooltip": "Strong vs All. \nWeak vs Fire support.",
            "intel": "Tank. Strong vs Infantry. Strong vs Armor.",
            "orders": (),
            "kill_xp": 0,
        },
    },
}

# The bunker (CPU only, German side in American mission 1; made by createSquad with squad type "bunker"), F6:10703-10728
# and bunkerEngaging F6:3059-3161. A bullet at it does damage / 4 (hitEnemy, F6:4296). Its machine gun fires 3-step
# shots while its burst count is at most `random(12) + 6`, rests until a fresh `random(160) + 60`, and after 200
# rounds sets its burst count to 100 and its rest count to -300, which is a rest of 360 to 519 steps.
BUNKER = {
    "hp": 1200,  # german.bunker.health
    "range": 1200,  # german.bunker.range
    "speed": 0,
    "damage": 0.8,  # german.bunkerBase.damage
    "bullet_divisor": 4,
    "rounds": 200,
    "burst": (12, 6),
    "rest": (160, 60),
    "reload_burst": 100,
    "reload_rest": -300,
}

# Soldier types. damage: one shot (a machine gun's burst shot, a tank's machine gun shot). weapon: the sound stem (the
# original plays "sound_<weapon>_fire1" or "_fire2", F6:2514). fire_pose: the animation label's stem
# ("<pose>_fire_<position>"). fire_type: slowBurst, medBurst, burst, or None for a single shot at every chance
# (section 3.7). Soldiers that never call a bullet hit have damage 0 (F6:2592): the bazooka man and the mortar carrier
# (the American carrier's 1e-8 is the same, a mortar team takes no bullet hits, F6:4290).
SOLDIERS = {
    "british": {
        "rifleman": {"damage": 9, "weapon": "garand", "fire_pose": "semiAuto", "fire_type": "slowBurst"},  # 10289-10294
        "thompson": {"damage": 1.5, "weapon": "thompson", "fire_pose": "smg", "fire_type": "medBurst"},  # 10295-10300
        "BAR": {"damage": 2, "weapon": "BAR", "fire_pose": "smg", "fire_type": "medBurst"},  # 10301-10306
        "carbine": {"damage": 9, "weapon": "garand", "fire_pose": "semiAuto", "fire_type": "slowBurst"},  # 10307-10312
        "machineGunner": {
            "damage": 7,
            "weapon": "30Cal",
            "fire_pose": "machineGun",
            "fire_type": "burst",
        },  # 10346-10354
        "sharpShooter": {
            "damage": 40,
            "weapon": "enfieldSniper",
            "fire_pose": "sniper",
            "fire_type": None,
        },  # 10369-10375
        "lieutenant": {
            "damage": 5,
            "weapon": "garand",
            "fire_pose": "semiAuto",
            "fire_type": "slowBurst",
        },  # 10390-10395
        "mortarCarrier": {"damage": 0, "weapon": "mortarTube", "fire_pose": "mortar", "fire_type": None},  # 10410-10414
        "bazookaMan": {"damage": 0, "weapon": "bazooka", "fire_pose": "bazooka", "fire_type": None},  # 10443-10450
        "tankMarkIV": {"damage": 4, "weapon": "tankMG", "fire_pose": None, "fire_type": None},  # 10463-10465
    },
    "german": {
        "rifleman": {"damage": 12, "weapon": "mauser", "fire_pose": "rifle", "fire_type": None},  # 10539-10543
        "grenadier": {
            "damage": 6,
            "weapon": "mauser",
            "fire_pose": "semiAuto",
            "fire_type": "slowBurst",
        },  # 10557-10562
        "volksgrenadier": {"damage": 1.5, "weapon": "mp40", "fire_pose": "smg", "fire_type": "medBurst"},  # 10563-10568
        "machineGunner": {
            "damage": 7,
            "weapon": "mg34",
            "fire_pose": "machineGun",
            "fire_type": "burst",
        },  # 10583-10591
        "sharpShooter": {
            "damage": 40,
            "weapon": "mauserSniper",
            "fire_pose": "sniper",
            "fire_type": None,
        },  # 10603-10609
        "lieutenant": {"damage": 5, "weapon": "mp40", "fire_pose": "semiAuto", "fire_type": "slowBurst"},  # 10627-10632
        "mortarCarrier": {"damage": 0, "weapon": "mortarTube", "fire_pose": "mortar", "fire_type": None},  # 10658-10661
        "bazookaMan": {"damage": 0, "weapon": "panzershreck", "fire_pose": "bazooka", "fire_type": None},  # 10677-10681
        "tankMarkIV": {"damage": 4, "weapon": "tankMG", "fire_pose": None, "fire_type": None},  # 10697-10700
        "bunkerBase": {"damage": BUNKER["damage"], "weapon": "tankMG", "fire_pose": None, "fire_type": None},
    },
}

# Damage a blast does to a tank or bunker, before upgrades (F6:10233-10275 American, F6:10484-10524 German).
BLAST_ARMOUR = {
    "british": {
        "mortar": 250,
        "artillery": 500,
        "shell": 350,
        "bazooka": 350,
        "airSupport": 120,
        "grenade": 65,
        "mine": 150,
    },
    "german": {
        "mortar": 250,
        "artillery": 500,
        "shell": 350,
        "bazooka": 500,
        "airSupport": 120,
        "grenade": 65,
        "mine": 150,
    },
}

# How long a smoke screen lasts, in steps, by the side that made it (british.gas.duration F6:10265, german F6:10514).
CLOUD_STEPS = {"british": 450, "german": 350}

# Fire support, the same for both sides. A strike calls `rounds` rounds. Round n waits first + random(wait) + n x gap
# steps (counted on unpaused steps), then plays and lands `land` steps later. A round lands at the target's x plus
# random(x_range) - x_offset and y plus random(y_range) - y_offset, and y is kept inside y_limits. Air support rounds
# line up instead: x target - 150 + 50n for the American side, mirrored for the German (F6:5286-5337).
#   artillery: artilleryStrike F6:5228-5268, numArtilleryRounds F6:10946, sprite 410 frame 152
#   airSupport: airStrike F6:5286-5337, numAirSupportRounds F6:10950, sprite 437 frame 7
#   mortar: mortarStrike F6:5355-5368 and mortarRound F6:5369-5410, numMortarRounds F6:10947, sprite 427 frame 101.
#     With the owner's Mortar Accuracy the x spread is random(80) - 45 times 0.75 (F6:5383). A smoked mortar team
#     scatters wider, x random(200) - 100 and y random(150) - 75 (F6:5388-5393). A y above y_min is raised to it.
#   mortarAI: mortarStrikeAI F6:5340-5354, six rounds, called by the CPU only
#   smoke: smokeStrike F6:5467-5500, numSmokeRounds F6:10952, sprite 415 frame 100; each call waits random(800) ms and
#     a round x target + random(50) - 25, in the lane of the aimed y at its centre + random(70) - 35
SUPPORTS = {
    "artillery": {
        "rounds": 8,
        "first": 0,
        "wait": 30,
        "gap": 90,
        "land": 151,
        "x_range": 250,
        "x_offset": 125,
        "y_range": 100,
        "y_offset": 50,
        "y_limits": (140, 340),
    },
    "airSupport": {
        "rounds": 15,
        "first": 220,
        "wait": 5,
        "gap": 3,
        "land": 6,
        "x_start": -150,
        "x_step": 50,
        "y_range": 30,
        "y_offset": 15,
        "y_limits": (140, 340),
    },
    "mortar": {
        "rounds": 1,
        "first": 0,
        "wait": 20,
        "gap": 70,
        "land": 100,
        "x_range": 100,
        "x_offset": 50,
        "x_accurate": (80, 45),
        "y_range": 100,
        "y_offset": 50,
        "smoked": {"x_range": 200, "x_offset": 100, "y_range": 150, "y_offset": 75},
        "y_min": 111,
    },
    "mortarAI": {
        "rounds": 6,
        "first": 0,
        "wait": 20,
        "gap": 70,
        "land": 100,
        "x_range": 100,
        "x_offset": 50,
        "x_accurate": (80, 45),
        "y_range": 100,
        "y_offset": 50,
        "smoked": {"x_range": 200, "x_offset": 100, "y_range": 150, "y_offset": 75},
        "y_min": 111,
    },
    "smoke": {
        "rounds": 1,
        "wait_ms": 800,
        "gap_ms": 1100,
        "land": 99,
        "x_range": 50,
        "x_offset": 25,
        "y_range": 70,
        "y_offset": 35,
    },
}

# The 17 cover types (cover_* objects, F6:10783-10833): the name the INTEL panel shows (the object's `desc`, kept as the
# original spells it), the share of a bullet's damage that gets through, and the colour of the cover icon on the leader
# (checkCoverRating, F6:1777-1787: 0.7 is 16763904 yellow, 0.5 is 6723840 green).
YELLOW = 0xFFCC00
GREEN = 0x669900
COVER_TYPES = {
    "stoneWall": {"name": "stone wall", "defence": 0.5, "colour": GREEN},
    "woodFence": {"name": "wood fence", "defence": 0.7, "colour": YELLOW},
    "logPile": {"name": "log pile", "defence": 0.5, "colour": GREEN},
    "sandBags": {"name": "sandbags", "defence": 0.5, "colour": GREEN},
    "sandBagsUS": {"name": "sandbagsUS", "defence": 0.5, "colour": GREEN},
    "barrels": {"name": "barrels", "defence": 0.7, "colour": YELLOW},
    "hedgerow": {"name": "hedgerow", "defence": 0.7, "colour": YELLOW},
    "rubble1": {"name": "rubble", "defence": 0.7, "colour": YELLOW},
    "rubble2": {"name": "rubble", "defence": 0.7, "colour": YELLOW},
    "urban1": {"name": "barricade", "defence": 0.7, "colour": YELLOW},
    "urban2": {"name": "barricade", "defence": 0.7, "colour": YELLOW},
    "sandDune": {"name": "sand dune", "defence": 0.7, "colour": YELLOW},
    "woodFenceOvergrown": {"name": "wood fence", "defence": 0.7, "colour": YELLOW},
    "headstones": {"name": "headstones", "defence": 0.7, "colour": YELLOW},
    "townWall": {"name": "stone wall", "defence": 0.5, "colour": GREEN},
    "sandBagsUrban": {"name": "sandbags", "defence": 0.5, "colour": GREEN},
    "sandBagsUrban_german": {"name": "sandbags", "defence": 0.5, "colour": GREEN},
}

# The 22 upgrades (setUpgradesInfantry/Support and the German pair, F6:7380-7699): number, name, text (the details
# panel's description), effect (its "Effect:" line) and cost. row and column place the button in the upgrade screen's
# grid (sprite 1378): rows 1 and 2 hold 4 buttons each, row 3 holds 3 that sit between the columns above them.
# Numbers 1 to 11 are the infantry tree, 12 to 22 the support tree.
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
AMERICAN_UPGRADE_ROWS = (
    (1, "BALLISTICS", "All Infantry armed with rifles & sub-machine guns will inflict more damage.", "+15% Damage", 1),
    (2, "TAKE COVER", "All Infantry soldiers gain a slight defensive bonus.", "+10% to Defence", 1),
    (3, "RED WHITE AND BLUE", "Morale boost to our fighting men.", "+10% to Starting Morale", 1),
    (4, "POST HASTE", "Decreases the reinforcment time for all units.", "10% faster reinforcement", 1),
    (5, "ASSAULT TACTICS", "Assault teams are highly trained and deal more damage.", "+10% Damage for Assault", 2),
    (6, "HIT 'EM HARD", "Our units will do more damage when attacking from flanks.", "+10% Damage on Flank Attack", 2),
    (
        7,
        "SECURE FLANKS",
        "Our flanks and support are secure, the men aren't worried.",
        "-20% from Morale loss when Flanked",
        2,
    ),
    (8, "RESUPPLY INBOUND", "Reinforcements arrive much quicker.", "15% faster reinforcement", 2),
    (
        9,
        "FIRE SUPPORT",
        "Your Machine Gun Teams have spent time training on the range.",
        "+40% Damage for Machine Gun Team",
        3,
    ),
    (10, "GO! GO! GO!", "Time doing long runs has increased their endurance.", "+20% to Infantry Movement", 3),
    (11, "IN GOOD SUPPLY", "Resources needed for all infantry units is reduced.", "-20% Resource Point Costs", 3),
)
GERMAN_UPGRADE_ROWS = (
    (1, "BALLISTICS", "All Infantry armed with rifles will inflict more damage.", "+15% Damage to Rifles", 1),
    (2, "TAKE COVER", "Our defensive capability has been improved.", "+10% to Defence", 1),
    (3, "FOR THE FUHRER", "Our men are inspired by the Fuhrer.", "15% boost to Morale", 1),
    (4, "REINFORCEMENTS", "Additional reinforcements have been allotted to our fight", "10% faster reinforcement", 1),
    (
        5,
        "MACHINE GUN TRAINING",
        "Our Machine Gun teams have been in training.",
        "+15% Damage to Machine Gun Teams",
        2,
    ),
    (
        6,
        "SECURE FLANKS",
        "Our men take less damage when attacked from either flank.",
        "+10% Defence when Flanked",
        2,
    ),
    (7, "FOR THE FATHERLAND", "Our men will die for our country.", "20% boost to Morale", 2),
    (8, "RAPID DEPLOYMENT", "Reinforcements arrive even faster.", "15% faster reinforcement", 2),
    (9, "SCHARFSCHÜTZE", "Our sharpshooters are a tool of destruction.", "+20% Damage for Snipers", 3),
    (10, "FORTIFIED", "Our engineers have reinforced our defences.", "+15% defence to all units", 3),
    (
        11,
        "CONSCRIPTS",
        "Drawing from the ranks of captured armies, riflemen are now 50% cheaper to train.",
        "Riflemen at half cost",
        3,
    ),
)
# The support tree: the American rows are F6:7554 on from setUpgradesSupport, the German ones differ in slot 15 (HEAVY
# instead of ENGINE UPGRADE), slot 19 (ENGINE UPGRADE instead of ANTI INFANTRY) and its cost.
AMERICAN_SUPPORT_ROWS = (
    (12, "GRENADES", "Riflemen and Assault Teams have been supplied grenades.", "Grenades added to Units", 1),
    (13, "MORTAR ACCURACY", "Mortar crews fire more accurately on designated targets.", "+25% more Accurate", 1),
    (14, "AIR SUPPORT", "Officers will have aircraft support available.", "Air Support", 1),
    (15, "ENGINE UPGRADE", "Our tanks now roll significantly faster.", "+25% Tank Movement Speed", 1),
    (
        16,
        "SMOKE GRENADES",
        "Snipers and Assault Teams have been supplied smoke grenades.",
        "Smoke Grenades added to Units",
        2,
    ),
    (17, "SMOKE MORTAR", "Mortar teams have been issued smoke rounds.", "Smoke Rounds", 2),
    (18, "ARTILLERY", "Officers now have access to call in Artillery Barrages.", "Artillery available", 2),
    (19, "ANTI INFANTRY", "Our tank MG crew have been trained in anti-personnel tactics.", "+30% Tank MG Damage", 2),
    (20, "EXPLOSIVES", "All infantry based explosives do more damage.", "+25% Explosives Damage", 3),
    (
        21,
        "BARRAGE OF FIRE",
        "Makes artillery strikes long and intense barrages which will decimate the enemy.",
        "Additional Rounds",
        3,
    ),
    (
        22,
        "ARMOR PRODUCTION",
        "Our industry has been working overtime to supply more tanks.",
        "-25% Resupply Time for Tanks",
        3,
    ),
)
GERMAN_SUPPORT_ROWS = (
    AMERICAN_SUPPORT_ROWS[:3]
    + (
        (
            15,
            "HEAVY",
            "Increased armor on our Panzers should protect against enemy fire.",
            "+15% Armor to Panzer III",
            1,
        ),
    )
    + AMERICAN_SUPPORT_ROWS[4:7]
    + ((19, "ENGINE UPGRADE", "Our tanks now roll significantly faster.", "+25% Tank Movement Speed", 1),)
    + AMERICAN_SUPPORT_ROWS[8:]
)


def upgrade_table(rows: tuple[tuple, ...]) -> dict[int, dict]:
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
    "british": upgrade_table(AMERICAN_UPGRADE_ROWS + AMERICAN_SUPPORT_ROWS),
    "german": upgrade_table(GERMAN_UPGRADE_ROWS + GERMAN_SUPPORT_ROWS),
}

# What it takes to open an upgrade (checkUpgrades, F6:7771-7840). Numbers not listed are open from the start. Each
# entry is a list of alternatives, and one alternative is a set of upgrades that must all be owned: a second-row
# upgrade needs the one above it, a third-row upgrade needs either full column above it. The German Engine Upgrade
# (19) is open from the start (german_slot19_upgrade.unlocked, F6:7674-7676). The buy check (buyUpgrade, F6:7843-7857)
# also needs the upgrade unowned and enough points.
COLUMN_NEEDS = {
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
UPGRADE_NEEDS = {
    "british": COLUMN_NEEDS,
    "german": {number: needs for number, needs in COLUMN_NEEDS.items() if number != 19},
}

# Every multiplier or amount an upgrade brings, by what it does (spec 3.19). numbers: which upgrade number gives it,
# per side (a side missing from numbers cannot get it). value: the amount. Where it reads as a multiplier it
# multiplies the thing it names. The rules read these only for the side that owns the upgrade. types: the soldier
# types the effect works on, by side.
UPGRADE_EFFECTS = {
    "timer_10": {"numbers": {"british": 4, "german": 4}, "value": 0.9},  # slots 1 to 7 cooldown
    "timer_15": {"numbers": {"british": 8, "german": 8}, "value": 0.85},  # slots 1 to 7 cooldown
    "tank_timer": {"numbers": {"british": 22, "german": 22}, "value": 0.75},  # slot 8 cooldown
    "rifle_damage": {  # shots of the listed soldier types
        "numbers": {"british": 1, "german": 1},
        "value": 1.15,
        "types": {
            "british": ("rifleman", "carbine", "thompson", "BAR", "lieutenant"),
            "german": ("rifleman", "grenadier"),
        },
    },
    "defence": {"numbers": {"british": 2, "german": 2}, "value": 0.9},  # enemy shots at this side's squads
    "morale_us": {"numbers": {"british": 3}, "value": 1.1},  # morale maximum
    "morale_fuhrer": {"numbers": {"german": 3}, "value": 1.15},  # morale maximum
    "morale_fatherland": {"numbers": {"german": 7}, "value": 1.2},  # morale maximum, stacks with morale_fuhrer
    "assault_damage": {"numbers": {"british": 5}, "value": 1.1},  # assault squad shots
    "flank_damage": {"numbers": {"british": 6}, "value": 1.1},  # assault squad shots at a target in another lane
    "flank_defence": {"numbers": {"german": 6}, "value": 0.9},  # enemy shots fired from another lane
    "flank_morale": {"numbers": {"british": 7}, "value": 0.8},  # morale lost when flanked
    "machine_gun_damage": {"numbers": {"british": 9}, "value": 1.4},  # machine gunner shots
    "machine_gun_training": {"numbers": {"german": 5}, "value": 1.15},  # machine gunner shots
    "sniper_damage": {"numbers": {"german": 9}, "value": 1.2},  # sniper shots
    "fortified": {"numbers": {"german": 10}, "value": 0.87},  # enemy shots at this side's squads in cover
    "move_speed": {"numbers": {"british": 10}, "value": 1.2},  # squads in the Moving state
    "good_supply": {"numbers": {"british": 11}, "value": 0.8},  # infantry deploy cost, rounded
    "conscripts": {"numbers": {"german": 11}, "value": 100},  # riflemen's deploy cost
    "mortar_scatter": {"numbers": {"british": 13, "german": 13}, "value": 0.75},  # mortar team round scatter
    "tank_speed": {"numbers": {"british": 15, "german": 19}, "value": 1.25},  # own tanks
    "tank_health": {"numbers": {"german": 15}, "value": 1.15},  # own tanks
    "tank_mg_damage": {"numbers": {"british": 19}, "value": 1.3},  # tank machine gun shots
    "explosives": {"numbers": {"british": 20, "german": 20}, "value": 1.25},  # own grenades and rockets on armour
    "barrage_rounds": {"numbers": {"british": 21, "german": 21}, "value": 10},  # own artillery rounds added
}

# XP. A level is reached when XP goes above the threshold (updateExperience, F6:8845-8850); each level gives one
# upgrade point. experienceIntervals, F6:11760.
LEVELS = (15, 45, 90, 150, 225, 315, 420, 540, 675, 825, 990, 1170, 1390, 1615, 1855, 2110, 2880, 3165, 3465)
# Kill XP by the dead soldier's squad kind (updateExperience, F6:8784-8815).
KILL_XP = {kind: UNITS["british"][kind]["kill_xp"] for kind in UNIT_KINDS}
