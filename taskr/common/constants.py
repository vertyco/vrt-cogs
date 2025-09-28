LEFT = "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}"
LEFT10 = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}"
RIGHT = "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}"
RIGHT10 = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}"
CLOSE = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"
PLUS = "\N{HEAVY PLUS SIGN}"  # Create new task
TRASH = "\N{WASTEBASKET}\N{VARIATION SELECTOR-16}"  # Delete task
MAG = "\N{LEFT-POINTING MAGNIFYING GLASS}"  # Search for a task
QUESTION = "\N{BLACK QUESTION MARK ORNAMENT}"  # Help
WAND = "\N{MAGIC WAND}"  # AI helper
PLAY = "\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16}"  # Run task
COPY = "\N{CLIPBOARD}"  # Duplicate task

SYSTEM_PROMPT = (
    "# INSTRUCTIONS\n"
    "Your task is to take the user input and convert it into a valid cron expression.\n"
    "Example 1: 'First Friday of every 3 months at 3:30PM starting on January':\n"
    "- hour: 15\n"
    "- minute: 30\n"
    "- days_of_month: 1st fri\n"
    "- months_of_year: 1-12/3\n"
    "Example 2: 'Every odd hour at the 30 minute mark from 5am to 8pm':\n"
    "- minute: 30\n"
    "- hour: 5-20/2\n"
    "Example 3: 'Run on the 15th of each month at 3pm':\n"
    "- hour: 15\n"
    "- days_of_month: 15\n"
    "# RULES\n"
    "- USE EITHER CRON RELATED EXPRESSIONS OR INTERVALS, NOT BOTH.\n"
    "- If using intervals, leave cron expressions blank.\n"
    "- If using cron expressions, leave intervals blank.\n"
    "- When using between times and intervals at the same time, the interval using can only be minutes or hours.\n"
)
