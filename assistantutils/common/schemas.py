import re

import matplotlib.font_manager as fm
from matplotlib.ft2font import FT2Font

FONT_NOISE = re.compile(
    r"^(cm[a-z]+\d|STIX(?:Size|NonUni)|Wingdings|Webdings|Symbol|Marlett|MT Extra)",
    re.IGNORECASE,
)
FONT_CAP = 40


def available_svg_fonts() -> str:
    try:
        paths = fm.findSystemFonts()
        families: set[str] = set()
        for path in paths:
            try:
                name = FT2Font(path).family_name
                if not FONT_NOISE.match(name):
                    families.add(name)
            except Exception:
                pass
        capped = sorted(families)[:FONT_CAP]
        return ", ".join(f"'{n}'" for n in capped)
    except Exception:
        return "'DejaVu Sans', 'DejaVu Serif', 'DejaVu Sans Mono', 'STIXGeneral'"


SVG_FONTS = available_svg_fonts()


GET_CHANNEL_LIST = {
    "name": "get_channel_list",
    "description": "Get the Discord channels the current user can see, including ID, mention, type, parent, and topic when available.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
GET_CHANNEL_INFO = {
    "name": "get_channel_info",
    "description": "Get detailed info for a channel, including IDs, position, overwrites, and channel-specific settings.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel you want to get info about",
            }
        },
        "required": ["channel_name_or_id"],
    },
}
GET_USER_INFO = {
    "name": "get_user_info",
    "description": "Get detailed info for a user, including ID, username, creation date, and roles.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_name_or_id": {
                "type": "string",
                "description": "The name, nickname, or ID of the user you want to get info about,",
            }
        },
        "required": ["user_name_or_id"],
    },
}
FETCH_CHANNEL_HISTORY = {
    "name": "fetch_channel_history",
    "description": "Fetch recent messages from a Discord channel by limit or time delta.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to fetch history from (defaults to the current channel if not provided)",
            },
            "limit": {
                "type": "integer",
                "description": "The number of messages to fetch from the channel, starting from the most recent. Defaults to 50 if neither limit nor delta is provided.",
            },
            "delta": {
                "type": "string",
                "description": "The time delta to filter messages by, in the format 'XdXhXmXs' (e.g., '1d2h30m' for 1 day, 2 hours, and 30 minutes). If omitted, no time-based cutoff is applied.",
            },
        },
    },
}
CONVERT_DATETIME_TIMESTAMP = {
    "name": "convert_datetime_timestamp",
    "description": "Convert a datetime string to a timestamp, or a timestamp to a datetime string.",
    "parameters": {
        "type": "object",
        "properties": {
            "date_or_timestamp": {
                "type": "string",
                "description": "The date in 'YYYY-MM-DD HH:MM:SS' format or a timestamp to convert",
            },
        },
        "required": ["date_or_timestamp"],
    },
}
GET_DISCORD_TIMESTAMP_FORMAT = {
    "name": "get_discord_timestamp_format",
    "description": "Format a date or timestamp as a Discord timestamp string.",
    "parameters": {
        "type": "object",
        "properties": {
            "date_or_timestamp": {
                "type": "string",
                "description": "The date to convert to Discord timestamp format (e.g., '2023-10-01 12:00:00' or '1696156800')",
            },
            "timestamp_format": {
                "type": "string",
                "description": "The format of the timestamp, can be 'R' for relative time, 'd' for shord date, 'D' for long date, 't' for short time, 'T' for long time, 'f' for short datetime, or 'F' for long datetime",
                "default": "F",
            },
        },
        "required": ["date_or_timestamp"],
    },
}
GET_ROLE_INFO = {
    "name": "get_role_info",
    "description": "Get detailed info for a Discord role, including ID, color, permissions, position, and member count.",
    "parameters": {
        "type": "object",
        "properties": {
            "role_name_or_id": {
                "type": "string",
                "description": "The name or ID of the role you want to get info about",
            }
        },
        "required": ["role_name_or_id"],
    },
}
GET_SERVER_INFO = {
    "name": "get_server_info",
    "description": "Get detailed info for the current server, including members, channels, boost level, and features.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
FETCH_URL = {
    "name": "fetch_url",
    "description": "Fetch a URL and return its text content.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
        },
        "required": ["url"],
    },
}
CREATE_AND_SEND_FILE = {
    "name": "create_and_send_file",
    "description": "Create a file from provided content and send it to the current channel.",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The name of the file including extension (e.g. 'script.py', 'data.json')",
            },
            "content": {
                "type": "string",
                "description": "The complete content to include in the file",
            },
            "comment": {
                "type": "string",
                "description": "Optional comment to include when sending the file",
                "default": "",
            },
        },
        "required": ["filename", "content"],
    },
}
ADD_REACTION = {
    "name": "add_reaction",
    "description": "Add an emoji reaction to a message in the current channel.",
    "parameters": {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The ID of the message to add a reaction to",
            },
            "emoji": {
                "type": "string",
                "description": "The emoji to add as a reaction (unicode emoji like '👍' or custom emoji format like '<:name:id>')",
            },
        },
        "required": ["message_id", "emoji"],
    },
}
SEARCH_MESSAGES = {
    "name": "search_messages",
    "description": "Search channel messages and embeds for text or a regex pattern.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (text to find or regex pattern if use_regex is true)",
            },
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to search in (defaults to current channel if not provided)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to search through (default: 50, max: 500)",
                "default": 50,
            },
            "use_regex": {
                "type": "boolean",
                "description": "Whether to treat the query as a regex pattern (default: false)",
                "default": False,
            },
        },
        "required": ["query"],
    },
}
RUN_COMMAND = {
    "name": "run_command",
    "description": "Run a bot command as the current user, using their permissions.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to run WITHOUT the prefix (e.g. 'help', 'ping', 'userinfo @user')",
            },
        },
        "required": ["command"],
    },
}
GET_MODLOG_CASES = {
    "name": "get_modlog_cases",
    "description": "Get modlog cases for a user, including action, moderator, reason, and date.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_name_or_id": {
                "type": "string",
                "description": "The username, display name, or user ID of the person to look up modlog cases for",
            },
        },
        "required": ["user_name_or_id"],
    },
}

FETCH_CATEGORY_CHANNELS = {
    "name": "fetch_category_channels",
    "description": "List the channels in a category, including name, ID, type, and topic.",
    "parameters": {
        "type": "object",
        "properties": {
            "category_name_or_id": {
                "type": "string",
                "description": "The name or ID of the category to list channels for",
            },
        },
        "required": ["category_name_or_id"],
    },
}

SEND_MESSAGE_TO_CHANNEL = {
    "name": "send_message_to_channel",
    "description": (
        "Send a bot message to a specific Discord channel. "
        "Use this for announcements, staff updates, relays, or escalations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to send the message to",
            },
            "message_content": {
                "type": "string",
                "description": "The message text to send. Supports Discord markdown formatting.",
            },
        },
        "required": ["channel_name_or_id", "message_content"],
    },
}

GET_PINNED_MESSAGES = {
    "name": "get_pinned_messages",
    "description": "Fetch pinned messages from a Discord channel.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to fetch pinned messages from (defaults to the current channel if not provided)",
            },
        },
    },
}

EDIT_BOT_MESSAGE = {
    "name": "edit_bot_message",
    "description": "Edit a bot message in the current channel.",
    "parameters": {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "The ID of the bot's message to edit",
            },
            "new_content": {
                "type": "string",
                "description": "The new message content to replace the existing text with. Supports Discord markdown.",
            },
        },
        "required": ["message_id", "new_content"],
    },
}

MANAGE_CHANNEL = {
    "name": "manage_channel",
    "description": (
        "Create, edit, move, or delete Discord channels. "
        "Use category_name_or_id='none' to remove a category. Set dry_run=true to preview changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do: create, edit, move, or delete.",
                "enum": ["create", "edit", "move", "delete"],
            },
            "channel_name_or_id": {
                "type": "string",
                "description": "The target channel to edit, move, or delete. Not needed when creating a new channel.",
            },
            "channel_type": {
                "type": "string",
                "description": "Channel type for create actions.",
                "enum": ["text", "voice", "stage", "forum", "category"],
            },
            "name": {
                "type": "string",
                "description": "Name for a new channel, or the new name when renaming an existing channel.",
            },
            "category_name_or_id": {
                "type": "string",
                "description": "Parent category name or ID. Pass 'none' to remove the current category.",
            },
            "position": {
                "type": "integer",
                "description": "New channel position within its current bucket.",
            },
            "topic": {
                "type": "string",
                "description": "Topic for text, forum, or stage channels.",
            },
            "news": {
                "type": "boolean",
                "description": "Whether a text channel should be a news/announcement channel. Requires the community feature.",
            },
            "nsfw": {
                "type": "boolean",
                "description": "Whether the channel should be marked NSFW.",
            },
            "slowmode_delay": {
                "type": "integer",
                "description": "Slowmode delay in seconds for supported channel types.",
            },
            "default_auto_archive_duration": {
                "type": "integer",
                "description": "Default auto archive duration for text/forum channels in minutes.",
            },
            "default_thread_slowmode_delay": {
                "type": "integer",
                "description": "Default thread slowmode delay for text/forum channels in seconds.",
            },
            "user_limit": {
                "type": "integer",
                "description": "User limit for supported voice-based channels.",
            },
            "bitrate": {
                "type": "integer",
                "description": "Bitrate for supported voice-based channels.",
            },
            "rtc_region": {
                "type": "string",
                "description": "Optional RTC region override for voice or stage channels. Use 'auto' for automatic.",
            },
            "video_quality_mode": {
                "type": "string",
                "description": "Video quality mode for voice or stage channels.",
                "enum": ["auto", "full"],
            },
            "media": {
                "type": "boolean",
                "description": "When creating a forum channel, whether it should be a media forum.",
            },
            "default_reaction_emoji": {
                "type": "string",
                "description": "Default forum reaction emoji. Supports unicode or custom emoji syntax.",
            },
            "default_sort_order": {
                "type": "string",
                "description": "Default sort order for forum channels.",
                "enum": ["latest_activity", "creation_date"],
            },
            "default_layout": {
                "type": "string",
                "description": "Default layout for forum channels.",
                "enum": ["list_view", "gallery_view", "not_set"],
            },
            "available_tags": {
                "type": "array",
                "description": "Forum tags to define on a forum channel. Replaces the full tag list when editing.",
                "items": {"type": "string"},
            },
            "sync_permissions": {
                "type": "boolean",
                "description": "Whether to sync permissions with the assigned category when moving or editing a channel.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested changes without applying them.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

SET_CHANNEL_PERMISSIONS = {
    "name": "set_channel_permissions",
    "description": (
        "Create or update channel permission overwrites for a role or member. Use discord.py permission flag names."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The channel whose permission overwrites should be updated.",
            },
            "target_type": {
                "type": "string",
                "description": "Whether the overwrite target is a role or member.",
                "enum": ["role", "member"],
            },
            "target_name_or_id": {
                "type": "string",
                "description": "The role or member to update overwrites for.",
            },
            "allow_permissions": {
                "type": "array",
                "description": "Permission names to explicitly allow.",
                "items": {"type": "string"},
            },
            "deny_permissions": {
                "type": "array",
                "description": "Permission names to explicitly deny.",
                "items": {"type": "string"},
            },
            "clear_permissions": {
                "type": "array",
                "description": "Permission names to reset back to neutral.",
                "items": {"type": "string"},
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the overwrite change without applying it.",
                "default": False,
            },
        },
        "required": ["channel_name_or_id", "target_type", "target_name_or_id"],
    },
}

MANAGE_THREAD = {
    "name": "manage_thread",
    "description": ("Create, edit, or delete Discord threads and forum posts. Set dry_run=true to preview changes."),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do: create, edit, or delete.",
                "enum": ["create", "edit", "delete"],
            },
            "parent_channel_name_or_id": {
                "type": "string",
                "description": "Text or forum channel where a new thread should be created.",
            },
            "thread_name_or_id": {
                "type": "string",
                "description": "Existing thread to edit or delete.",
            },
            "name": {
                "type": "string",
                "description": "Name for a new thread, or the new thread name when editing.",
            },
            "starter_message_id": {
                "type": "string",
                "description": "Optional starter message ID when creating a thread from an existing text-channel message.",
            },
            "private_thread": {
                "type": "boolean",
                "description": "When creating a text-channel thread without a starter message, whether it should be private.",
            },
            "auto_archive_duration": {
                "type": "integer",
                "description": "Thread auto archive duration in minutes.",
            },
            "slowmode_delay": {
                "type": "integer",
                "description": "Thread slowmode delay in seconds.",
            },
            "invitable": {
                "type": "boolean",
                "description": "Whether non-moderators can invite others to a private thread.",
            },
            "archived": {
                "type": "boolean",
                "description": "Whether the thread should be archived.",
            },
            "locked": {
                "type": "boolean",
                "description": "Whether the thread should be locked.",
            },
            "pinned": {
                "type": "boolean",
                "description": "Whether the forum post should be pinned.",
            },
            "applied_tags": {
                "type": "array",
                "description": "Forum tags to apply by name or ID.",
                "items": {"type": "string"},
            },
            "message_content": {
                "type": "string",
                "description": "Starter message content when creating a forum post.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested thread change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_ROLE = {
    "name": "manage_role",
    "description": (
        "Create, edit, move, or delete Discord roles. "
        "Provided permissions replace the full role permission set. Set dry_run=true to preview changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do: create, edit, move, or delete.",
                "enum": ["create", "edit", "move", "delete"],
            },
            "role_name_or_id": {
                "type": "string",
                "description": "Existing role to edit, move, or delete.",
            },
            "name": {
                "type": "string",
                "description": "Role name for create, or the new role name when editing.",
            },
            "permissions": {
                "type": "array",
                "description": "Full list of permission names the role should have.",
                "items": {"type": "string"},
            },
            "color": {
                "type": ["string", "integer"],
                "description": "Role color as a 6-digit hex string like '#5865F2' or an integer.",
            },
            "hoist": {
                "type": "boolean",
                "description": "Whether the role should be shown separately in the member list.",
            },
            "mentionable": {
                "type": "boolean",
                "description": "Whether the role should be mentionable by everyone.",
            },
            "display_icon": {
                "type": "string",
                "description": "Optional role icon as either a unicode emoji or an image URL. Use 'none' to clear it when editing.",
            },
            "position": {
                "type": "integer",
                "description": "Absolute role position for edit or move actions.",
            },
            "above_role_name_or_id": {
                "type": "string",
                "description": "Move this role above another role.",
            },
            "below_role_name_or_id": {
                "type": "string",
                "description": "Move this role below another role.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested role change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_SERVER = {
    "name": "manage_server",
    "description": "Update supported Discord server settings. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "New server name.",
            },
            "description": {
                "type": "string",
                "description": "New server description.",
            },
            "verification_level": {
                "type": "string",
                "enum": ["none", "low", "medium", "high", "highest"],
                "description": "Server verification level.",
            },
            "explicit_content_filter": {
                "type": "string",
                "enum": ["disabled", "no_role", "all_members"],
                "description": "Explicit content filter level.",
            },
            "default_notifications": {
                "type": "string",
                "enum": ["all_messages", "only_mentions"],
                "description": "Default notification level.",
            },
            "preferred_locale": {
                "type": "string",
                "description": "discord.py Locale enum member name, such as 'american_english' or 'german'.",
            },
            "afk_timeout": {
                "type": "integer",
                "description": "AFK timeout in seconds.",
            },
            "afk_channel_name_or_id": {
                "type": "string",
                "description": "Voice channel for AFK moves. Use 'none' to clear.",
            },
            "system_channel_name_or_id": {
                "type": "string",
                "description": "System text channel. Use 'none' to clear.",
            },
            "rules_channel_name_or_id": {
                "type": "string",
                "description": "Rules text channel. Use 'none' to clear.",
            },
            "public_updates_channel_name_or_id": {
                "type": "string",
                "description": "Public updates text channel. Use 'none' to clear.",
            },
            "widget_enabled": {
                "type": "boolean",
                "description": "Whether the server widget should be enabled.",
            },
            "widget_channel_name_or_id": {
                "type": "string",
                "description": "Widget text channel. Use 'none' to clear.",
            },
            "system_channel_flags": {
                "type": "array",
                "description": "System channel flags to suppress/disable, using discord.py flag names.",
                "items": {"type": "string"},
            },
            "premium_progress_bar_enabled": {
                "type": "boolean",
                "description": "Whether the boost progress bar should be shown.",
            },
            "community": {
                "type": "boolean",
                "description": "Whether community mode should be enabled.",
            },
            "invites_disabled": {
                "type": "boolean",
                "description": "Whether invites should be paused.",
            },
            "discoverable": {
                "type": "boolean",
                "description": "Whether server discovery should be enabled.",
            },
            "raid_alerts_disabled": {
                "type": "boolean",
                "description": "Whether raid protection alerts should be disabled.",
            },
            "safety_alerts_channel_name_or_id": {
                "type": "string",
                "description": "Safety alerts text channel. Use 'none' to clear.",
            },
            "welcome_screen_enabled": {
                "type": "boolean",
                "description": "Whether the community welcome screen should be enabled.",
            },
            "welcome_screen_description": {
                "type": "string",
                "description": "Welcome screen description text.",
            },
            "welcome_channels": {
                "type": "array",
                "description": "Welcome screen channels. Replaces the full list when provided.",
                "items": {
                    "type": "object",
                    "properties": {
                        "channel_name_or_id": {
                            "type": "string",
                            "description": "The text channel to show on the welcome screen.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description shown under that welcome channel.",
                        },
                        "emoji": {
                            "type": "string",
                            "description": "Optional unicode or custom emoji for the welcome channel.",
                        },
                    },
                    "required": ["channel_name_or_id", "description"],
                },
            },
            "icon_url": {
                "type": "string",
                "description": "Image URL for the server icon. Use 'none' to clear it.",
            },
            "banner_url": {
                "type": "string",
                "description": "Image URL for the server banner. Use 'none' to clear it.",
            },
            "splash_url": {
                "type": "string",
                "description": "Image URL for the invite splash. Use 'none' to clear it.",
            },
            "discovery_splash_url": {
                "type": "string",
                "description": "Image URL for the discovery splash. Use 'none' to clear it.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested server change without applying it.",
                "default": False,
            },
        },
    },
}

INSPECT_SERVER_SETUP = {
    "name": "inspect_server_setup",
    "description": "Inspect the current Discord server setup and highlight important gaps for smooth admin setup.",
    "parameters": {
        "type": "object",
        "properties": {
            "focus": {
                "type": "string",
                "description": "Optional area to emphasize in the report.",
                "enum": ["overview", "channels", "roles", "community", "moderation", "assets"],
            },
        },
    },
}

MANAGE_MEMBER = {
    "name": "manage_member",
    "description": (
        "Inspect or manage a server member, including nickname, roles, timeout, kick, and voice state changes. "
        "Set dry_run=true to preview changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with the member.",
                "enum": [
                    "inspect",
                    "set_nickname",
                    "add_roles",
                    "remove_roles",
                    "set_roles",
                    "timeout",
                    "clear_timeout",
                    "kick",
                    "move_voice",
                    "disconnect",
                    "mute",
                    "unmute",
                    "deafen",
                    "undeafen",
                ],
            },
            "member_name_or_id": {
                "type": "string",
                "description": "The target member by username, display name, mention, or ID.",
            },
            "nickname": {
                "type": "string",
                "description": "New nickname for set_nickname. Use 'none' to clear it.",
            },
            "role_names_or_ids": {
                "type": "array",
                "description": "Roles to add, remove, or set on the member.",
                "items": {"type": "string"},
            },
            "timeout_minutes": {
                "type": "integer",
                "description": "Timeout length in minutes for timeout actions. Max 40320 (28 days).",
            },
            "voice_channel_name_or_id": {
                "type": "string",
                "description": "Target voice or stage channel for move_voice.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested member change without applying it.",
                "default": False,
            },
        },
        "required": ["action", "member_name_or_id"],
    },
}

MANAGE_INVITE = {
    "name": "manage_invite",
    "description": "List, create, or revoke Discord invites. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with invites.",
                "enum": ["list", "create", "revoke"],
            },
            "channel_name_or_id": {
                "type": "string",
                "description": "Target channel for create, or optional channel filter for list.",
            },
            "invite_code_or_url": {
                "type": "string",
                "description": "Invite code or full invite URL to revoke.",
            },
            "max_age": {
                "type": "integer",
                "description": "Invite lifetime in seconds. Use 0 for no expiry.",
                "default": 0,
            },
            "max_uses": {
                "type": "integer",
                "description": "Maximum number of uses. Use 0 for unlimited.",
                "default": 0,
            },
            "temporary": {
                "type": "boolean",
                "description": "Whether the invite grants temporary membership.",
                "default": False,
            },
            "unique": {
                "type": "boolean",
                "description": "Whether to force a unique invite code.",
                "default": True,
            },
            "target_type": {
                "type": "string",
                "description": "Optional special invite target type.",
                "enum": ["stream", "embedded_application"],
            },
            "target_user_name_or_id": {
                "type": "string",
                "description": "Target streaming user when target_type is stream.",
            },
            "target_application_id": {
                "type": "integer",
                "description": "Embedded application ID when target_type is embedded_application.",
            },
            "guest": {
                "type": "boolean",
                "description": "Whether to create a guest invite.",
                "default": False,
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested invite change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_WEBHOOK = {
    "name": "manage_webhook",
    "description": "List, create, edit, delete, or send a test message with Discord webhooks. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with webhooks.",
                "enum": ["list", "create", "edit", "delete", "send_test"],
            },
            "channel_name_or_id": {
                "type": "string",
                "description": "Target channel for create, optional list filter, or destination channel for edit moves.",
            },
            "webhook_name_or_id": {
                "type": "string",
                "description": "Existing webhook name or ID for edit, delete, or send_test.",
            },
            "name": {
                "type": "string",
                "description": "Webhook name for create or edit.",
            },
            "avatar_url": {
                "type": "string",
                "description": "Optional webhook avatar image URL. Use 'none' to clear on edit.",
            },
            "test_message": {
                "type": "string",
                "description": "Message content for send_test.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested webhook change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_EVENT = {
    "name": "manage_event",
    "description": "List, create, edit, or delete scheduled events. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with scheduled events.",
                "enum": ["list", "create", "edit", "delete"],
            },
            "event_name_or_id": {
                "type": "string",
                "description": "Existing event name or ID for edit or delete.",
            },
            "name": {
                "type": "string",
                "description": "Event name for create or edit.",
            },
            "description": {
                "type": "string",
                "description": "Event description.",
            },
            "channel_name_or_id": {
                "type": "string",
                "description": "Voice or stage channel for channel-based events.",
            },
            "location": {
                "type": "string",
                "description": "Location text for external events.",
            },
            "start_time": {
                "type": "string",
                "description": "Event start time as a parseable datetime string with timezone when possible.",
            },
            "end_time": {
                "type": "string",
                "description": "Optional event end time as a parseable datetime string.",
            },
            "status": {
                "type": "string",
                "description": "Optional status for edit actions.",
                "enum": ["scheduled", "active", "completed", "canceled", "cancelled", "ended"],
            },
            "image_url": {
                "type": "string",
                "description": "Optional event cover image URL. Use 'none' to clear on edit.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested event change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_EMOJI = {
    "name": "manage_emoji",
    "description": "List, create, edit, or delete custom server emojis. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with custom emojis.",
                "enum": ["list", "create", "edit", "delete"],
            },
            "emoji_name_or_id": {
                "type": "string",
                "description": "Existing emoji name or ID for edit or delete.",
            },
            "name": {
                "type": "string",
                "description": "Emoji name for create or edit.",
            },
            "image_url": {
                "type": "string",
                "description": "Image URL for create. Use 'none' only where clearing is supported.",
            },
            "role_names_or_ids": {
                "type": "array",
                "description": "Optional role restrictions for the emoji.",
                "items": {"type": "string"},
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested emoji change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_STICKER = {
    "name": "manage_sticker",
    "description": "List, create, edit, or delete server stickers. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with stickers.",
                "enum": ["list", "create", "edit", "delete"],
            },
            "sticker_name_or_id": {
                "type": "string",
                "description": "Existing sticker name or ID for edit or delete.",
            },
            "name": {
                "type": "string",
                "description": "Sticker name for create or edit.",
            },
            "description": {
                "type": "string",
                "description": "Sticker description for create or edit.",
            },
            "emoji": {
                "type": "string",
                "description": "Unicode emoji that represents the sticker expression.",
            },
            "image_url": {
                "type": "string",
                "description": "Sticker image URL for create.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested sticker change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_SOUNDBOARD = {
    "name": "manage_soundboard",
    "description": "List, create, edit, or delete custom soundboard sounds. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with soundboard sounds.",
                "enum": ["list", "create", "edit", "delete"],
            },
            "sound_name_or_id": {
                "type": "string",
                "description": "Existing soundboard sound name or ID for edit or delete.",
            },
            "name": {
                "type": "string",
                "description": "Soundboard sound name for create or edit.",
            },
            "audio_url": {
                "type": "string",
                "description": "Audio file URL for sound creation.",
            },
            "volume": {
                "type": "number",
                "description": "Sound volume from 0.0 to 1.0.",
            },
            "emoji": {
                "type": "string",
                "description": "Optional unicode or custom emoji for the sound.",
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested soundboard change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

MANAGE_ONBOARDING = {
    "name": "manage_onboarding",
    "description": "Inspect or update server onboarding defaults and prompts. Set dry_run=true to preview changes.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "What to do with onboarding.",
                "enum": ["inspect", "set_defaults", "upsert_prompt", "delete_prompt"],
            },
            "prompt_name_or_id": {
                "type": "string",
                "description": "Existing onboarding prompt title or ID for update or delete.",
            },
            "title": {
                "type": "string",
                "description": "Prompt title when creating or updating a prompt.",
            },
            "prompt_type": {
                "type": "string",
                "description": "Onboarding prompt type.",
                "enum": ["multiple_choice", "dropdown"],
            },
            "single_select": {
                "type": "boolean",
                "description": "Whether users can pick only one option from the prompt.",
            },
            "required": {
                "type": "boolean",
                "description": "Whether the prompt is required.",
            },
            "in_onboarding": {
                "type": "boolean",
                "description": "Whether the prompt is shown in onboarding.",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether onboarding is enabled.",
            },
            "mode": {
                "type": "string",
                "description": "Onboarding mode.",
                "enum": ["default", "advanced"],
            },
            "default_channel_names_or_ids": {
                "type": "array",
                "description": "Default channels granted to new members.",
                "items": {"type": "string"},
            },
            "options": {
                "type": "array",
                "description": "Prompt options. Replaces the full option list when provided.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Option title.",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional option description.",
                        },
                        "emoji": {
                            "type": "string",
                            "description": "Optional unicode or custom emoji.",
                        },
                        "channel_names_or_ids": {
                            "type": "array",
                            "description": "Channels granted by this option.",
                            "items": {"type": "string"},
                        },
                        "role_names_or_ids": {
                            "type": "array",
                            "description": "Roles granted by this option.",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title"],
                },
            },
            "reason": {
                "type": "string",
                "description": "Optional audit log reason.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview the requested onboarding change without applying it.",
                "default": False,
            },
        },
        "required": ["action"],
    },
}

RENDER_SVG = {
    "name": "render_svg",
    "description": "Render SVG markup into a PNG and send it to the current channel.",
    "parameters": {
        "type": "object",
        "properties": {
            "svg_content": {
                "type": "string",
                "description": (
                    "Complete SVG markup with an <svg> root that has explicit width and height attributes."
                    f" Available font families: {SVG_FONTS}."
                    " Tip: prefer named families over generic CSS families (sans-serif etc.) for consistent results."
                    " Keep in mind that Discord mention formatting doesn't render in SVGs so just use plain text."
                    " IMPORTANT: never place differently colored inline <text>/<tspan> fragments on the same line"
                    " unless x positions are explicitly calculated to prevent overlap. Prefer full single-color"
                    " lines, separate <text> elements per line, or padded blocks. Readability over decoration."
                ),
            },
            "filename": {
                "type": "string",
                "description": "Output filename (default: 'rendering.png').",
                "default": "rendering.png",
            },
            "background": {
                "type": "string",
                "description": "Optional background hex color.",
                "default": "",
            },
        },
        "required": ["svg_content"],
    },
}

DISCORD_INFO_TOOLS = (
    GET_CHANNEL_LIST,
    GET_CHANNEL_INFO,
    GET_USER_INFO,
    GET_ROLE_INFO,
    GET_SERVER_INFO,
    FETCH_CATEGORY_CHANNELS,
)

DISCORD_SEARCH_TOOLS = (
    FETCH_CHANNEL_HISTORY,
    SEARCH_MESSAGES,
    GET_PINNED_MESSAGES,
)

DISCORD_MESSAGE_TOOLS_USER = (
    ADD_REACTION,
    EDIT_BOT_MESSAGE,
)

DISCORD_MESSAGE_TOOLS_MOD = (SEND_MESSAGE_TO_CHANNEL,)

DISCORD_ADMIN_TOOLS = (
    INSPECT_SERVER_SETUP,
    MANAGE_MEMBER,
    MANAGE_INVITE,
    MANAGE_WEBHOOK,
    MANAGE_EVENT,
    MANAGE_EMOJI,
    MANAGE_STICKER,
    MANAGE_SOUNDBOARD,
    MANAGE_ONBOARDING,
    MANAGE_CHANNEL,
    SET_CHANNEL_PERMISSIONS,
    MANAGE_THREAD,
    MANAGE_ROLE,
    MANAGE_SERVER,
)
