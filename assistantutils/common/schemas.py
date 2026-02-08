GET_CHANNEL_LIST = {
    "name": "get_channel_list",
    "description": "Get a list of all the Discord channels that the person you are talking to can see, including their name and ID along with the topic.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
GET_CHANNEL_INFO = {
    "name": "get_channel_info",
    "description": "Get a detailed breakdown of info about a channel including its ID, name, creation date and topic as well as channel type specific info.",
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
    "description": "Get a detailed breakdown of info about a user including their ID, username, creation date, and roles.",
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
SEARCH_INTERNET = {
    "name": "search_web_duckduckgo",
    "description": "Search the web for current information on a topic using the DuckDuckGo Search API.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, can be a question or topic",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}
FETCH_CHANNEL_HISTORY = {
    "name": "fetch_channel_history",
    "description": "Fetch messages from a Discord channel over a specified limit or time delta.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to fetch history from (defaults to the current channel if not provided)",
            },
            "limit": {
                "type": "integer",
                "description": "The number of messages to fetch from the channel, starting from the most recent. If not provided, uses delta instead.",
            },
            "delta": {
                "type": "string",
                "description": "The time delta to filter messages by, in the format 'XdXhXmXs' (e.g., '1d2h30m' for 1 day, 2 hours, and 30 minutes). Defaults to '1h' if neither limit nor delta is provided.",
                "default": "1h",
            },
        },
    },
}
CONVERT_DATETIME_TIMESTAMP = {
    "name": "convert_datetime_timestamp",
    "description": "Convert between a datetime string and a timestamp. If a datetime string is provided, it will return the corresponding timestamp. If a timestamp is provided, it will return the corresponding datetime string.",
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
    "description": "Get the Discord timestamp format for a given date, returned a formatted string that can be used in Discord messages. (e.g. <t:1696156800:R> for a timestamp)",
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
    "description": "Get detailed information about a Discord role including its ID, color, permissions, position, and member count.",
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
    "description": "Get detailed information about the current Discord server including member count, channel counts, boost level, and features.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
FETCH_URL = {
    "name": "fetch_url",
    "description": "Fetch the content of a URL and return the text. Useful for reading documentation, articles, or any web page content.",
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
    "description": "Create a file with the provided content and send it to the current Discord channel.",
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
    "description": "Add a reaction emoji to a message in the current channel.",
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
    "description": "Search for messages containing specific text or matching a regex pattern in a channel.",
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
    "description": "Run a bot command on behalf of the user. The command will be executed with the user's permissions.",
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
