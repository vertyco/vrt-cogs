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
                "description": "The number of messages to fetch from the channel, starting from the most recent (default: 30)",
                "default": 30,
            },
            "delta": {
                "type": "string",
                "description": "The time delta to filter messages by, in the format 'XdXhXmXs' (e.g., '1d2h30m' for 1 day, 2 hours, and 30 minutes. MAX 2d). If this is provided, it will use the delta instead of the limit. If not provided, the default `limit` will be used",
                "default": "",
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
