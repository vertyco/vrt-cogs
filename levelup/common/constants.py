default_guild = {
    "schema": "v1",
    "users": {},  # All user level data
    "levelroles": {},  # Roles associated with levels
    "ignoredchannels": [],  # Channels that dont gain XP
    "ignoredroles": [],  # Roles that dont gain XP
    "ignoredusers": [],  # Ignored users won't gain XP
    "prestige": 0,  # Level required to prestige, 0 is disabled
    "prestigedata": {},  # Prestige tiers, the role associated with them, and emoji for them
    "xp": [3, 6],  # Min/Max XP per message
    "voicexp": 2,  # XP per minute in voice
    "rolebonuses": {
        "msg": {},
        "voice": {},
    },  # Roles that give a bonus range of XP
    "channelbonuses": {
        "msg": {},
        "voice": {},
    },  # ChannelID keys, list values for bonus xp range
    "streambonus": [],  # Bonus voice XP for streaming in voice
    "cooldown": 60,  # Only gives XP every 60 seconds
    "base": 100,  # Base denominator for level algorithm, higher takes longer to level
    "exp": 2,  # Exponent for level algorithm, higher is a more exponential/steeper curve
    "length": 0,  # Minimum length of message to be considered eligible for XP gain
    "starcooldown": 3600,  # Cooldown in seconds for users to give each other stars
    "starmention": False,  # Mention when users add a star
    "starmentionautodelete": 0,  # Auto delete star mention reactions (0 to disable)
    "usepics": False,  # Use Pics instead of embeds for leveling, Embeds are default
    "barlength": 15,  # Progress bar length for embed profiles
    "autoremove": False,  # Remove previous role on level up
    "stackprestigeroles": True,  # Toggle whether to stack prestige roles
    "muted": True,  # Ignore XP while being muted in voice
    "solo": True,  # Ignore XP while in a voice chat alone
    "deafened": True,  # Ignore XP while deafened in a voice chat
    "invisible": True,  # Ignore XP while status is invisible in voice chat
    "notifydm": False,  # Toggle notify member of level up in DMs
    "mention": False,  # Toggle whether to mention the user
    "notifylog": None,  # Notify member of level up in a set channel
    "notify": False,  # Toggle whether to notify member of levelups if notify log channel is not set,
    "showbal": False,  # Show economy balance
    "weekly": {  # Weekly tracking
        "users": {},  # Wiped weekly
        "on": False,  # Weekly stats are being tracked for this guild or not
        "autoreset": False,  # Whether to auto reset once a week or require manual reset
        "reset_hour": 0,  # 0 - 23 hour (UTC time)
        "reset_day": 0,  # 0 = sun, 1 = mon, 2 = tues, 3 = wed, 4 = thur, 5 = fri, 6 = sat
        "last_reset": 0,  # Timestamp of when weekly was last reset
        "count": 3,  # How many users to show in weekly winners
        "channel": 0,  # Announce the weekly winners(top 3 by default)
        "role": 0,  # Role awarded to top member(s) for that week
        "role_all": False,  # If True, all winners get the role
        "last_winners": [],  # IDs of last members that won if role_all is enabled
        "remove": True,  # Whether to remove the role from the previous winner when a new one is announced
        "bonus": 0,  # Bonus exp to award the top X winners
        "last_embed": {},  # Dict repr of last winner embed
    },
    "emojis": {  # For embed profiles only
        "level": "\N{SPORTS MEDAL}",
        "trophy": "\N{TROPHY}",
        "star": "\N{WHITE MEDIUM STAR}",
        "chat": "\N{SPEECH BALLOON}",
        "mic": "\N{STUDIO MICROPHONE}\N{VARIATION SELECTOR-16}",
        "bulb": "\N{ELECTRIC LIGHT BULB}",
        "money": "\N{MONEY BAG}",
    },
}

default_global = {
    "ignored_guilds": [],
    "cache_seconds": 15,
    "render_gifs": False,
}
