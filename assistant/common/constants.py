MODELS = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-0125": 16385,
    # "gpt-3.5-turbo-16k": 16384, - Depricated
    # "gpt-3.5-turbo-16k-0301": 16384, - Depricated
    # "gpt-3.5-turbo-16k-0613": 16384 - Depricated
    # "gpt-3.5-turbo-instruct": 8192, - Depricated
    "gpt-4": 8192,
    # "gpt-4-32k": 32768, - Depricated
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    # "gpt-4-vision-preview": 128000, - Depricated
    "gpt-4-turbo-2024-04-09": 128000,
    "gpt-4o": 128000,
    "gpt-4o-2024-05-13": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o-mini-2024-07-18": 128000,
    "gpt-4o-2024-08-06": 128000,
    "gpt-4o-2024-11-20": 128000,
    "chatgpt-4o-latest": 128000,
    "gpt-4.1": 1047576,
    "gpt-4.1-2025-04-14": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-mini-2025-04-14": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-4.1-nano-2025-04-14": 1047576,
    "o1": 128000,
    "o1-2024-12-17": 200000,
    "o1-preview": 128000,
    "o1-preview-2024-09-12": 128000,
    "o1-mini": 128000,
    "o1-mini-2024-09-12": 128000,
    "o3": 200000,
    "o3-2025-04-16": 200000,
    "o3-mini": 200000,
    "o3-mini-2025-01-31": 200000,
    "gpt-5": 400000,
    "gpt-5-2025-08-07": 400000,
    "gpt-5-mini": 400000,
    "gpt-5-mini-2025-08-07": 400000,
    "gpt-5-nano": 400000,
    "gpt-5-nano-2025-08-07": 400000,
    "gpt-5.1": 400000,
    "gpt-5.1-2025-11-13": 400000,
}
PRICES = {  # Price per 1k tokens
    "gpt-3.5-turbo": [0.001, 0.0015],
    "gpt-3.5-turbo-0301": [0.0015, 0.002],
    "gpt-3.5-turbo-0613": [0.0015, 0.002],
    "gpt-3.5-turbo-1106": [0.001, 0.002],
    "gpt-3.5-turbo-0125": [0.0005, 0.0015],
    "gpt-3.5-turbo-16k": [0.003, 0.004],
    "gpt-3.5-turbo-16k-0301": [0.003, 0.004],
    "gpt-3.5-turbo-16k-0613": [0.003, 0.004],
    "gpt-3.5-turbo-instruct": [0.0015, 0.002],
    "gpt-3.5-turbo-instruct-0914": [0.0015, 0.002],
    "gpt-4": [0.03, 0.06],
    "gpt-4-0301": [0.03, 0.06],
    "gpt-4-0613": [0.03, 0.06],
    "gpt-4-turbo": [0.01, 0.03],
    "gpt-4-turbo-preview": [0.01, 0.03],
    "gpt-4-1106-preview": [0.01, 0.03],
    "gpt-4-0125-preview": [0.01, 0.03],
    "gpt-4-vision-preview": [0.01, 0.03],
    "gpt-4-1106-vision-preview": [0.01, 0.03],
    "gpt-4-turbo-2024-04-09": [0.01, 0.03],
    "gpt-4-32k": [0.06, 0.12],
    "gpt-4-32k-0301": [0.06, 0.12],
    "gpt-4o": [0.005, 0.015],
    "gpt-4o-2024-05-13": [0.005, 0.015],
    "gpt-4o-2024-08-06": [0.0025, 0.01],
    "gpt-4o-2024-11-20": [0.0025, 0.01],
    "chatgpt-4o-latest": [0.0025, 0.01],
    "gpt-4o-mini": [0.00015, 0.0006],
    "gpt-4o-mini-2024-07-18": [0.00015, 0.0006],
    "gpt-4.1": [0.002, 0.008],
    "gpt-4.1-2025-04-14": [0.002, 0.008],
    "gpt-4.1-mini": [0.0004, 0.0016],
    "gpt-4.1-mini-2025-04-14": [0.0004, 0.0016],
    "gpt-4.1-nano": [0.0001, 0.0004],
    "gpt-4.1-nano-2025-04-14": [0.0001, 0.0004],
    "gpt-5": [0.00125, 0.010],
    "gpt-5-2025-08-07": [0.00125, 0.010],
    "gpt-5-mini": [0.00025, 0.002],
    "gpt-5-mini-2025-08-07": [0.00025, 0.002],
    "gpt-5-nano": [0.00005, 0.0004],
    "gpt-5-nano-2025-08-07": [0.00005, 0.0004],
    "gpt-5.1": [0.00125, 0.010],
    "gpt-5.1-2025-11-13": [0.00125, 0.010],
    "o1": [0.015, 0.06],
    "o1-2024-12-17": [0.015, 0.06],
    "o1-preview": [0.015, 0.06],
    "o1-preview-2024-09-12": [0.015, 0.06],
    "o1-mini": [0.003, 0.012],
    "o1-mini-2024-09-12": [0.003, 0.012],
    "o3": [0.002, 0.008],
    "o3-mini": [0.0011, 0.0044],
    "o3-mini-2025-01-31": [0.0011, 0.0044],
    "text-ada-001": [0.0004, 0.0016],
    "text-babbage-001": [0.0006, 0.0024],
    "text-curie-001": [0.003, 0.012],
    "text-davinci-002": [0.03, 0.12],
    "text-davinci-003": [0.03, 0.12],
    "code-davinci-002": [0.03, 0.12],
    "text-embedding-ada-002": [0.0001, 0.0001],
    "text-embedding-ada-002-v2": [0.0001, 0.0001],
    "text-embedding-3-small": [0.00002, 0.00002],
    "text-embedding-3-large": [0.00013, 0.00013],
}
VISION_COSTS = {
    "gpt-4o": [85, 170],  # 85 base tokens, 170 per (32x32) pixel tile in the image
    "gpt-4o-2024-05-13": [85, 170],
    "gpt-4o-2024-08-06": [85, 170],
    "gpt-4o-2024-11-20": [85, 170],
    "gpt-4o-mini": [2833, 5667],  # 2833 base tokens, 5667 per (32x32) pixel tile in the image
    "gpt-4o-mini-2024-07-18": [2833, 5667],
    "gpt-4.1": [85, 170],  # 85 base tokens, 170 per (32x32) pixel tile in the image
    "gpt-4.1-2025-04-14": [85, 170],
    "o1": [75, 150],  # 75 base tokens, 150 per (32x32) pixel tile in the image
    "o1-2024-12-17": [75, 150],
    # 75 base tokens, 150 per (32x32) pixel tile in the image
}
IMAGE_COSTS = {
    "standard1024x1024": 0.04,
    "standard1792x1024": 0.08,
    "standard1024x1792": 0.08,
    "hd1024x1024": 0.08,
    "hd1792x1024": 0.12,
    "hd1024x1792": 0.12,
    "low1024x1024": 0.011,
    "low1024x1536": 0.016,
    "low1536x1024": 0.016,
    "medium1024x1024": 0.042,
    "medium1024x1536": 0.063,
    "medium1536x1024": 0.063,
    "high1024x1024": 0.167,
    "high1024x1536": 0.25,
    "high1536x1024": 0.25,
}
SUPPORTS_SEED = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    "gpt-4-1106-preview",
    "gpt-4-vision-preview",
    "gpt-4-1106-vision-preview",
    "gpt-4-turbo-preview",
    "gpt-4-0125-preview",
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-08-06",
    "chatgpt-4o-latest",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    "gpt-5",
    "gpt-5-2025-08-07",
    "gpt-5-mini",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano",
    "gpt-5-nano-2025-08-07",
    "gpt-5.1",
    "gpt-5.1-2025-11-13",
]
NO_DEVELOPER_ROLE = [  # Also doesnt support system messages
    "o1-mini",
    "o1-mini-2024-09-12",
    "o1-preview",
    "o1-preview-2024-09-12",
    "deepseek",
]
SUPPORTS_VISION = [
    "gpt-4-vision-preview",
    "gpt-4-1106-vision-preview",
    "gpt-4-turbo-2024-04-09",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-08-06",
    "chatgpt-4o-latest",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    "o1",
    "o1-2024-12-17",
    # "o3-mini",
    # "o3-mini-2025-01-31",
    "o3",
    "o3-2025-04-16",
    "gpt-5",
    "gpt-5-2025-08-07",
    "gpt-5-mini",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano",
    "gpt-5-nano-2025-08-07",
    "gpt-5.1",
    "gpt-5.1-2025-11-13",
]
SUPPORTS_TOOLS = [
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4-0125-preview",
    "gpt-4-1106-preview",
    "gpt-4o",
    "gpt-4o-2024-05-13",
    "gpt-4o-2024-08-06",
    "gpt-4o-2024-11-20",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-08-06",
    "chatgpt-4o-latest",
    "gpt-4.1",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano",
    "gpt-4.1-nano-2025-04-14",
    "o1",
    "o1-2024-12-17",
    "o3-mini",
    "o3-mini-2025-01-31",
    "o3",
    "o3-2025-04-16",
    "gpt-5",
    "gpt-5-2025-08-07",
    "gpt-5-mini",
    "gpt-5-mini-2025-08-07",
    "gpt-5-nano",
    "gpt-5-nano-2025-08-07",
    "gpt-5.1",
    "gpt-5.1-2025-11-13",
]
READ_EXTENSIONS = [
    ".txt",
    ".py",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".html",
    ".ini",
    ".css",
    ".toml",
    ".md",
    ".ini",
    ".conf",
    ".config",
    ".cfg",
    ".go",
    ".java",
    ".c",
    ".php",
    ".swift",
    ".vb",
    ".xhtml",
    ".rss",
    ".css",
    ".asp",
    ".js",
    ".ts",
    ".cs",
    ".c++",
    ".cpp",
    ".cbp",
    ".h",
    ".cc",
    ".ps1",
    ".bat",
    ".batch",
    ".shell",
    ".env",
    ".sh",
    ".bat",
    ".pde",
    ".spec",
    ".sql",
    ".log",
]
LOADING = "https://i.imgur.com/l3p6EMX.gif"
REACT_SUMMARY_MESSAGE = """
Ignore previous instructions. You will be given a snippet of text, your job is to create a "memory" for the given text to provide context for future conversations.

# RULES
- Output a summary of the text in your own words.
- This is a contextual memory about a topic, do not include irrelevant information like names of who is speaking.
- Do not include the original text in your response.
"""
TLDR_PROMPT = """
Write a TLDR based on the messages provided.

The messages you are reviewing will be formatted as follows:
[<t:Discord Timestamp:t>](Message ID) Author Name: Message Content

TLDR tips:
- Include details like names and info that might be relevant to a Discord moderation team
- To create a jump URL for a message, format it as "https://discord.com/channels/<guild_id>/<channel_id/<message_id>"
- When you reference a message directly, make sure to include [<t:Discord Timestamp:t>](jump url)
- Separate topics with bullet points
"""

GENERATE_IMAGE = {
    "name": "generate_image",
    "description": "Use this to generate an image from a text prompt.",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A sentence or phrase that describes what you want to visualize, must be less than 1000 characters",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd", "low", "medium", "high"],
                "description": "The quality of the image. For dall-e-3, use 'standard' or 'hd'. For gpt-image-1, use 'low', 'medium', or 'high'. Defaults to 'medium'.",
            },
            "style": {
                "type": "string",
                "enum": ["natural", "vivid"],
                "description": "Vivid leans toward more hyper-real and dramatic images. Natural creates more natural, less hyper-real looking images. Only applies to dall-e-3. Defaults to 'vivid'",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1792x1024", "1024x1792", "1024x1536", "1536x1024"],
                "description": "The size of the image, defaults to 1024x1024",
            },
            "model": {
                "type": "string",
                "enum": ["dall-e-3", "gpt-image-1"],
                "description": "The model to use for image generation. dall-e-3 is the standard model, gpt-image-1 is a newer model with different pricing. Defaults to 'dall-e-3'",
            },
        },
        "required": ["prompt"],
    },
}
EDIT_IMAGE = {
    "name": "edit_image",
    "description": "Use this to edit an existing image for a user. (Use this is the user tells you to do something to an image!)",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Pass the user's prompt directly as this argument and make sure it includes to keep the image exactly the same except for the changes they want to make.",
            },
        },
        "required": ["prompt"],
    },
}


SEARCH_INTERNET = {
    "name": "search_web_brave",
    "description": "Search the web for current information on a topic using the Brave Search API.",
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

CREATE_MEMORY = {
    "name": "create_memory",
    "description": "Use this to remember information that you normally wouldnt have access to. Useful when someone corrects you, tells you something new, or tells you to remember something. Use the search_memories function first to ensure no duplicates are created.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_name": {
                "type": "string",
                "description": "A short name to describe the memory, perferrably less than 50 characters or 3 words tops",
            },
            "memory_text": {
                "type": "string",
                "description": "The information to remember, write as if you are informing yourself of the thing to remember, Make sure to include the context of the conversation as well as the answer or important information to be retained",
            },
        },
        "required": ["memory_name", "memory_text"],
    },
}
SEARCH_MEMORIES = {
    "name": "search_memories",
    "description": "Use this to find information about something, always use this if you are unsure about the answer to a question.",
    "parameters": {
        "type": "object",
        "properties": {
            "search_query": {
                "type": "string",
                "description": "a sentence or phrase that describes what you are looking for, this should be as specific as possible, it will be tokenized to find the best match with related embeddings.",
            },
            "amount": {
                "type": "integer",
                "description": "Max amount of memories to fetch. Defaults to 2",
            },
        },
        "required": ["search_query"],
    },
}
EDIT_MEMORY = {
    "name": "edit_memory",
    "description": "Use this to edit existing memories, useful for correcting inaccurate memories after making them. Use search_memories first if the memory you need to edit is not in the conversation.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_name": {
                "type": "string",
                "description": "The name of the memory entry, case sensitive",
            },
            "memory_text": {
                "type": "string",
                "description": "The new text that will replace the current content of the memory, this should reflect the old memory with the corrections",
            },
        },
        "required": ["memory_name", "memory_text"],
    },
}
LIST_MEMORIES = {
    "name": "list_memories",
    "description": "Get a list of all your available memories",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
DO_NOT_RESPOND_SCHEMA = {
    "name": "do_not_respond",
    "description": "Call this function if you do not want to or do not need to respond to the user.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
RESPOND_AND_CONTINUE = {
    "name": "respond_and_continue",
    "description": "Call this function if you want to respond to the user but also continue working on the task at hand.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The message to send to the user, this can be something like 'I will continue working on this task, please wait.' or 'I will get back to you shortly.'",
            },
        },
        "required": ["content"],
    },
}
