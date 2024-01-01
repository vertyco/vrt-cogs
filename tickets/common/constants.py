DEFAULT_GUILD = {
    # Settings
    "support_roles": [],  # Role ids that have access to all tickets
    "blacklist": [],  # User ids that cannot open any tickets
    "max_tickets": 1,  # Max amount of tickets a user can have open at a time of any kind
    "inactive": 0,  # Auto close tickets with X hours of inactivity (0 = disabled)
    "overview_channel": 0,  # Overview of open tickets across panels
    "overview_msg": 0,  # Message id of the overview info
    "overview_mention": False,  # Whether the channel names are displayed or the name
    # Ticket data
    "opened": {},  # All opened tickets
    "panels": {},  # All ticket panels
    # Toggles
    "dm": False,  # Whether to DM the user when their ticket is closed
    "user_can_rename": False,  # Ticket opener can rename their ticket channel
    "user_can_close": True,  # Ticket opener can close their own ticket
    "user_can_manage": False,  # Ticket opener can add other users to their ticket
    "transcript": False,  # Save a transcript of the ticket conversation on close
    "detailed_transcript": False,  # Save transcript to interactive html file
    "auto_add": False,  # Auto-add support/subroles to thread tickets
    "thread_close": True,  # Whether to close/lock the thread instead of deleting it
}

TICKET_PANEL_SCHEMA = {  # "panel_name" will be the key for the schema
    # Panel settings
    "category_id": 0,  # <Required>
    "channel_id": 0,  # <Required>
    "message_id": 0,  # <Required>
    "disabled": False,  # Whether panel is disabled
    "alt_channel": 0,  # (Optional) Open tickets from another channel/category
    "required_roles": [],  # (Optional) list of role IDs, empty list if anyone can open
    "close_reason": True,  # Throw a modal for closing reason on the ticket close button
    # Button settings
    "button_text": "Open a Ticket",  # (Optional)
    "button_color": "blue",  # (Optional)
    "button_emoji": None,  # (Optional) Either None or an emoji for the button
    "priority": 1,  # (Optional) Button order
    "row": None,  # Row for the button to be placed
    # Ticket settings
    "ticket_messages": [],  # (Optional) A list of messages to be sent
    "ticket_name": None,  # (Optional) Name format for the ticket channel
    "log_channel": 0,  # (Optional) Log open/closed tickets
    "modal": {},  # (Optional) Modal fields to fill out before ticket is opened
    "modal_title": "",  # (Optional) Modal title
    "threads": False,  # Whether this panel makes a thread or channel
    "roles": [],  # Sub-support roles
    "max_claims": 0,  # How many cooks in the kitchen (default infinite if 0)
    # Ticker
    "ticket_num": 1,
}
# v1.3.10 schema update (Modals)
MODAL_SCHEMA = {
    "label": "",  # <Required>
    "style": "short",  # <Required>
    "placeholder": None,  # (Optional)
    "default": None,  # (Optional)
    "required": True,  # (Optional)
    "min_length": None,  # (Optional)
    "max_length": None,  # (Optional)
    "answer": None,  # (Optional)
}
