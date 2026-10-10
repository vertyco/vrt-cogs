"""Animation timings and hit boxes from the original's art, written by the art build script. Do not edit by hand.

Each timeline is (sprite id, {"frames": count, "actions": {frame: [action, ...]}}). Actions: ("stop",),
("play", frame), ("pick", (frame, frame)), ("rstop", first, last), ("rplay", first, last), ("remove",), and the
original's game hooks ("hit",), ("rhit",) and ("shoot",)
"""

# Unit type -> state label -> timeline
UNIT_ANIMS = {
    1: {
        "idle": (230, {"frames": 50, "actions": {}}),
        "walk": (231, {"frames": 43, "actions": {43: [("play", 1)]}}),
        "attack": (237, {"frames": 40, "actions": {20: [("hit",)]}}),
        "die": (245, {"frames": 24, "actions": {24: [("stop",)]}}),
    },
    2: {
        "idle": (259, {"frames": 50, "actions": {}}),
        "walk": (260, {"frames": 43, "actions": {43: [("play", 1)]}}),
        "attack": (263, {"frames": 40, "actions": {20: [("hit",)]}}),
        "die": (264, {"frames": 24, "actions": {24: [("stop",)]}}),
        "shoot": (278, {"frames": 32, "actions": {26: [("rhit",)], 32: [("play", 1)]}}),
        "shootwalk": (280, {"frames": 43, "actions": {30: [("rhit",)], 43: [("play", 1)]}}),
    },
    3: {
        "idle": (310, {"frames": 48, "actions": {}}),
        "walk": (311, {"frames": 40, "actions": {40: [("play", 1)]}}),
        "attack": (315, {"frames": 45, "actions": {21: [("hit",)]}}),
        "die": (317, {"frames": 50, "actions": {50: [("stop",)]}}),
    },
    4: {
        "idle": (334, {"frames": 55, "actions": {}}),
        "walk": (335, {"frames": 40, "actions": {}}),
        "attack": (
            348,
            {
                "frames": 99,
                "actions": {
                    1: [("pick", (2, 50))],
                    33: [("hit",)],
                    48: [("play", 1)],
                    76: [("hit",)],
                    99: [("play", 1)],
                },
            },
        ),
        "die": (349, {"frames": 44, "actions": {44: [("stop",)]}}),
    },
    5: {
        "idle": (369, {"frames": 55, "actions": {}}),
        "walk": (370, {"frames": 40, "actions": {}}),
        "attack": (
            380,
            {
                "frames": 99,
                "actions": {
                    1: [("pick", (2, 50))],
                    38: [("hit",)],
                    48: [("play", 1)],
                    49: [("play", 1)],
                    79: [("hit",)],
                    99: [("play", 1)],
                },
            },
        ),
        "die": (381, {"frames": 44, "actions": {44: [("stop",)]}}),
        "shoot": (393, {"frames": 40, "actions": {15: [("rhit",)]}}),
        "shootwalk": (404, {"frames": 40, "actions": {16: [("rhit",)]}}),
    },
    6: {
        "idle": (448, {"frames": 120, "actions": {}}),
        "walk": (449, {"frames": 40, "actions": {}}),
        "attack": (450, {"frames": 52, "actions": {23: [("hit",)]}}),
        "die": (452, {"frames": 22, "actions": {22: [("stop",)]}}),
    },
    7: {
        "idle": (468, {"frames": 125, "actions": {}}),
        "walk": (469, {"frames": 47, "actions": {}}),
        "attack": (
            471,
            {
                "frames": 84,
                "actions": {
                    1: [("pick", (2, 39))],
                    19: [("hit",)],
                    37: [("play", 1)],
                    62: [("hit",)],
                    84: [("play", 1)],
                },
            },
        ),
        "die": (472, {"frames": 70, "actions": {27: [("stop",)]}}),
    },
    8: {
        "idle": (478, {"frames": 85, "actions": {}}),
        "walk": (479, {"frames": 47, "actions": {}}),
        "attack": (482, {"frames": 46, "actions": {13: [("rhit",)]}}),
        "die": (483, {"frames": 70, "actions": {70: [("stop",)]}}),
        "shoot": (482, {"frames": 46, "actions": {13: [("rhit",)]}}),
        "shootwalk": (484, {"frames": 48, "actions": {1: [("rhit",)]}}),
    },
    9: {
        "idle": (494, {"frames": 110, "actions": {}}),
        "walk": (495, {"frames": 48, "actions": {}}),
        "attack": (497, {"frames": 78, "actions": {27: [("hit",)]}}),
        "die": (498, {"frames": 65, "actions": {65: [("stop",)]}}),
    },
    10: {
        "idle": (514, {"frames": 129, "actions": {}}),
        "walk": (515, {"frames": 49, "actions": {}}),
        "attack": (516, {"frames": 30, "actions": {14: [("hit",)]}}),
        "die": (517, {"frames": 90, "actions": {26: [("stop",)]}}),
    },
    11: {
        "idle": (521, {"frames": 94, "actions": {}}),
        "walk": (522, {"frames": 47, "actions": {}}),
        "attack": (532, {"frames": 21, "actions": {7: [("hit",)]}}),
        "die": (533, {"frames": 90, "actions": {26: [("stop",)]}}),
        "shoot": (542, {"frames": 21, "actions": {7: [("rhit",)]}}),
        "shootwalk": (551, {"frames": 48, "actions": {3: [("rhit",)]}}),
    },
    12: {
        "idle": (568, {"frames": 1, "actions": {}}),
        "walk": (569, {"frames": 10, "actions": {10: [("play", 1)]}}),
        "attack": (573, {"frames": 63, "actions": {30: [("hit",)]}}),
        "die": (607, {"frames": 105, "actions": {42: [("stop",)]}}),
    },
    13: {
        "idle": (630, {"frames": 58, "actions": {}}),
        "walk": (631, {"frames": 47, "actions": {}}),
        "attack": (639, {"frames": 37, "actions": {23: [("hit",)]}}),
        "die": (640, {"frames": 65, "actions": {65: [("stop",)]}}),
    },
    14: {
        "idle": (646, {"frames": 94, "actions": {}}),
        "walk": (647, {"frames": 34, "actions": {}}),
        "attack": (
            654,
            {
                "frames": 56,
                "actions": {
                    1: [("pick", (2, 33))],
                    21: [("hit",)],
                    32: [("play", 1)],
                    44: [("hit",)],
                    56: [("play", 1)],
                },
            },
        ),
        "die": (655, {"frames": 75, "actions": {46: [("stop",)]}}),
        "shoot": (661, {"frames": 14, "actions": {6: [("rhit",)]}}),
        "shootwalk": (662, {"frames": 38, "actions": {21: [("rhit",)]}}),
    },
    15: {
        "idle": (676, {"frames": 28, "actions": {}}),
        "walk": (676, {"frames": 28, "actions": {}}),
        "attack": (681, {"frames": 90, "actions": {13: [("hit",)]}}),
        "die": (685, {"frames": 55, "actions": {34: [("stop",)]}}),
    },
    16: {
        "idle": (646, {"frames": 94, "actions": {}}),
        "walk": (647, {"frames": 34, "actions": {}}),
        "attack": (
            654,
            {
                "frames": 56,
                "actions": {
                    1: [("pick", (2, 33))],
                    21: [("hit",)],
                    32: [("play", 1)],
                    44: [("hit",)],
                    56: [("play", 1)],
                },
            },
        ),
        "die": (655, {"frames": 75, "actions": {46: [("stop",)]}}),
        "shoot": (661, {"frames": 14, "actions": {6: [("rhit",)]}}),
        "shootwalk": (662, {"frames": 38, "actions": {21: [("rhit",)]}}),
    },
}

# Turret type -> timeline of its firing animation
TURRET_ANIMS = {
    1: (725, {"frames": 32, "actions": {1: [("stop",)], 6: [("shoot",)]}}),
    2: (737, {"frames": 10, "actions": {1: [("stop",)], 6: [("shoot",)]}}),
    3: (752, {"frames": 55, "actions": {1: [("stop",)], 8: [("shoot",)]}}),
    4: (780, {"frames": 99, "actions": {1: [("stop",)], 20: [("shoot",)]}}),
    5: (800, {"frames": 99, "actions": {1: [("stop",)], 20: [("shoot",)]}}),
    6: (811, {"frames": 77, "actions": {1: [("stop",)], 21: [("shoot",)]}}),
    7: (820, {"frames": 45, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    8: (828, {"frames": 80, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    9: (836, {"frames": 80, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    10: (850, {"frames": 45, "actions": {1: [("stop",)], 3: [("shoot",)]}}),
    11: (853, {"frames": 40, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    12: (
        864,
        {"frames": 40, "actions": {1: [("stop",), ("stop",)], 2: [("shoot",)], 20: [("stop",)], 21: [("shoot",)]}},
    ),
    13: (869, {"frames": 40, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    14: (876, {"frames": 3, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
    15: (880, {"frames": 3, "actions": {1: [("stop",)], 2: [("shoot",)]}}),
}

# Unit type -> hit box [left, top, right, bottom] around its feet, before facing
HITZONES = {
    1: [-15.8, -43.8, 15.8, 0.5],
    2: [-15.8, -43.8, 15.8, 0.5],
    3: [-40.7, -61.8, 40.7, 0.5],
    4: [-15.8, -43.8, 15.8, 0.5],
    5: [-15.8, -43.8, 15.8, 0.5],
    6: [-49.2, -68.55, 49.2, 0.45],
    7: [-16.75, -50.8, 16.75, 0.5],
    8: [-16.75, -50.8, 16.75, 0.5],
    9: [-16.75, -50.8, 16.75, 0.5],
    10: [-16.75, -50.8, 16.75, 0.5],
    11: [-16.75, -50.8, 16.75, 0.5],
    12: [-86.75, -56.8, 86.75, 0.5],
    13: [-22.25, -68.55, 22.25, 0.5],
    14: [-22.25, -68.55, 22.25, 0.5],
    15: [-58.25, -56.55, 58.25, 0.5],
    16: [-22.25, -68.55, 22.25, 0.5],
}

# Side -> the base's hit box relative to the base's position
BASE_BOXES = {1: [-67.35, -75.5, 119.45, 1.0], 2: [-95.24, -75.5, 106.01, 1.0]}
