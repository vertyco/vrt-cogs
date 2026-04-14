CLOCK = "\N{ALARM CLOCK}"
BELL = "\N{BELL}"
BELL_OFF = "\N{BELL WITH CANCELLATION STROKE}"
CALENDAR = "\N{CALENDAR}"
CHECK = "\N{WHITE HEAVY CHECK MARK}"
CROSS = "\N{CROSS MARK}"
GEAR = "\N{GEAR}"
PENCIL = "\N{PENCIL}"
PLUS = "\N{HEAVY PLUS SIGN}"
TRASH = "\N{WASTEBASKET}"
LEFT = "\N{BLACK LEFT-POINTING TRIANGLE}"
RIGHT = "\N{BLACK RIGHT-POINTING TRIANGLE}"
INFO = "\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}"
SHIELD = "\N{SHIELD}"

DAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

DAY_EMOJI = {
    0: "\N{REGIONAL INDICATOR SYMBOL LETTER M}",
    1: "\N{REGIONAL INDICATOR SYMBOL LETTER T}",
    2: "\N{REGIONAL INDICATOR SYMBOL LETTER W}",
    3: "\N{REGIONAL INDICATOR SYMBOL LETTER R}",
    4: "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
    5: "\N{REGIONAL INDICATOR SYMBOL LETTER S}",
    6: "\N{REGIONAL INDICATOR SYMBOL LETTER U}",
}

TUTORIAL_PAGES = [
    {
        "title": "Welcome to NoPing!",
        "description": (
            "NoPing lets you **opt out of being pinged** in a server. "
            "When enabled, Discord's AutoMod will automatically block messages "
            "that try to mention you.\n\n"
            "**How it works:**\n"
            "The bot manages AutoMod keyword filter rules that match your user mention pattern. "
            "When someone tries to ping you, AutoMod blocks their message before it's sent."
        ),
    },
    {
        "title": "Quick Toggle",
        "description": (
            "Use `[p]noping` to instantly toggle your ping protection on or off.\n\n"
            "- **On**: Messages containing your @mention will be blocked\n"
            "- **Off**: You can be pinged normally\n\n"
            "If you have a schedule set, toggling will override it until your next "
            "scheduled transition."
        ),
    },
    {
        "title": "Schedules",
        "description": (
            "You can set **availability windows** for each day of the week. "
            "During these windows, you CAN be pinged. Outside of them, pings are blocked.\n\n"
            "**Example:** Mon-Fri 9:00-17:00\n"
            "This means you're available (can be pinged) during work hours, "
            "and pings are blocked evenings, nights, and weekends.\n\n"
            "Use `[p]noping schedule` to open the schedule editor."
        ),
    },
    {
        "title": "Multiple Windows",
        "description": (
            "Each day can have **multiple availability windows**.\n\n"
            "**Example:** Monday has two windows:\n"
            "- 09:00 - 12:00 (morning)\n"
            "- 14:00 - 17:00 (afternoon)\n\n"
            "This means pings are blocked 00:00-09:00, 12:00-14:00, and 17:00-24:00 on Monday."
        ),
    },
    {
        "title": "Timezones",
        "description": (
            "All schedule times are interpreted in your timezone.\n\n"
            "**Set your personal timezone:**\n"
            "`[p]noping timezone America/New_York`\n\n"
            "If you don't set a personal timezone, the server default is used.\n"
            "Use `none` to reset to the server default:\n"
            "`[p]noping timezone none`\n\n"
            "All times shown in status and schedule views use Discord's "
            "timestamp formatting, so they automatically display in your local time!"
        ),
    },
    {
        "title": "Server Settings (Admins)",
        "description": (
            "Server admins can configure:\n\n"
            "**Server Timezone** - Default timezone for all users.\n"
            "`[p]nopingset timezone <tz>`\n\n"
            "**User Access** - Toggle whether normal users can use noping.\n"
            "`[p]nopingset toggle`\n\n"
            "**Force Add/Remove** - Override a user's noping status.\n"
            "`[p]nopingset add @user` / `[p]nopingset remove @user`\n\n"
            "**View Users** - See who has noping enabled.\n"
            "`[p]nopingset view`\n\n"
            "**Prune** - Remove users no longer in the server.\n"
            "`[p]nopingset prune`\n\n"
            "AutoMod rules are managed automatically. You can further customize "
            "the rule's exempt roles and custom message through Discord's UI."
        ),
    },
]
