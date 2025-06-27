GET_CHANNEL_ID = {
    "name": "get_channel_name_from_id",
    "description": "Get the name of a given channel ID",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "integer",
                "description": "ID of the channel",
            },
        },
        "required": ["channel_id"],
    },
}
GET_CHANNEL_NAMED = {
    "name": "get_channel_id_from_name",
    "description": "Get the ID for a channel name",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name": {
                "type": "string",
                "description": "Name of the channel",
            },
        },
        "required": ["channel_name"],
    },
}
GET_CHANNEL_MENTION = {
    "name": "get_channel_mention",
    "description": "Get the proper discord mention format for a channel",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel you want to mention",
            },
        },
        "required": ["channel_name_or_id"],
    },
}
GET_CHANNEL_LIST = {
    "name": "get_channel_list",
    "description": "Get a list of all the available channels the user can see",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
GET_CHANNEL_TOPIC = {
    "name": "get_channel_topic",
    "description": "Get the topic of a given text channel",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel",
            },
        },
        "required": ["channel_name_or_id"],
    },
}
GET_SEARCH_URL = {
    "name": "make_search_url",
    "description": "Generate a link to search google or youtube, use this if you arent sure of the answer to help the user find it themselves.",
    "parameters": {
        "type": "object",
        "properties": {
            "site": {
                "type": "string",
                "description": "the website to search, can be 'youtube' or 'google'",
            },
            "search_query": {
                "type": "string",
                "description": "what to search for",
            },
        },
        "required": ["site", "search_query"],
    },
}
GET_USERNAME_FROM_ID = {
    "name": "get_user_from_id",
    "description": "Get a discord member's name from their ID",
    "parameters": {
        "type": "object",
        "properties": {
            "discord_id": {
                "type": "integer",
                "description": "Discord user's ID",
            },
        },
        "required": ["discord_id"],
    },
}
GET_ID_FROM_USERNAME = {
    "name": "get_id_from_username",
    "description": "Get a discord member's ID from their username or nickname",
    "parameters": {
        "type": "object",
        "properties": {
            "username": {
                "type": "string",
                "description": "Discord user's username or nickname",
            },
        },
        "required": ["username"],
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
    "description": "Fetch the last X messages from a channel to see their content.",
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name_or_id": {
                "type": "string",
                "description": "The name or ID of the channel to fetch history from",
            },
            "limit": {
                "type": "integer",
                "description": "The number of messages to fetch from the channel, starting from the most recent (default: 30)",
                "default": 30,
            },
        },
        "required": ["channel_name_or_id"],
    },
}
GET_DATE_FROM_TIMESTAMP = {
    "name": "get_date_from_timestamp",
    "description": "Get a human-readable date from a timestamp",
    "parameters": {
        "type": "object",
        "properties": {
            "timestamp": {
                "type": "integer",
                "description": "The timestamp to convert to a date",
            },
        },
        "required": ["timestamp"],
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
