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
GET_SEARCH_URL = {
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
