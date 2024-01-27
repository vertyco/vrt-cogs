MODELS = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-0301": 4096,
    "gpt-3.5-turbo-0613": 4096,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-0125": 16385,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-3.5-turbo-16k-0301": 16384,
    "gpt-3.5-turbo-16k-0613": 16384,
    "gpt-3.5-turbo-instruct": 8192,
    "gpt-3.5-turbo-instruct-0914": 8192,
    "gpt-4": 8192,
    "gpt-4-0301": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-32k-0301": 32768,
    "gpt-4-32k-0613": 32768,
    "gpt-4-turbo-preview": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-vision-preview": 128000,
    "gpt-4-1106-vision-preview": 128000,
    "code-davinci-002": 8001,
    "text-davinci-003": 4097,
    "text-davinci-002": 4097,
    "text-curie-001": 2049,
    "text-babbage-001": 2049,
    "text-ada-001": 2049,
    "text-embedding-ada-002": 8191,
    "text-embedding-ada-002-v2": 8191,
}
PRICES = {
    "gpt-3.5-turbo": [0.0015, 0.002],
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
    "gpt-4-turbo-preview": [0.01, 0.03],
    "gpt-4-1106-preview": [0.01, 0.03],
    "gpt-4-0125-preview": [0.01, 0.03],
    "gpt-4-vision-preview": [0.01, 0.03],
    "gpt-4-1106-vision-preview": [0.01, 0.03],
    "gpt-4-32k": [0.06, 0.12],
    "gpt-4-32k-0301": [0.06, 0.12],
    "gpt-4-32k-0613": [0.06, 0.12],
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
SUPPORTS_SEED = [
    "gpt-3.5-turbo-1106",
    "gpt-4-1106-preview",
    "gpt-4-vision-preview",
    "gpt-4-1106-vision-preview",
    "gpt-4-turbo-preview",
    "gpt-4-0125-preview",
]
SUPPORTS_VISION = [
    "gpt-4-vision-preview",
    "gpt-4-1106-vision-preview",
]
SUPPORTS_TOOLS = [
    "gpt-3.5-turbo-1106",
    "gpt-4-1106-preview",
    "gpt-4-0125-preview",
    "gpt-4-turbo-preview",
]
SUPPORTS_FUNCTIONS = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0613",
    "gpt-4-1106-preview",
]
CHAT = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0301",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0301",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0301",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0301",
    "gpt-4-32k-0613",
    "gpt-4-1106-preview",
    "gpt-4-vision-preview",
    "gpt-4-1106-vision-preview",
    "code-davinci-002",
]
COMPLETION = [
    "text-davinci-003",
    "text-davinci-002",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",
    "gpt-3.5-turbo-instruct",
    "gpt-3.5-turbo-instruct-0914",
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
    ".go",
    ".cfg",
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
]
REACT_SUMMARY_MESSAGE = """
You are SummaryGPT, an AI creates memories from conversations.

You will be given a snippet of text to summarize based on a larger conversation.
This text will be stored as your "Memory" and will be used to provide context for future conversations.

# RULES
- OUTPUT ONLY THE SUMMARY WITHOUT THE ORIGINAL TEXT OR EXTRA DIALOGUE FROM YOU.
- KEEP THE SUMMARY SHORT AND TO THE POINT.
"""
REACT_NAME_MESSAGE = """
You are NameGPT, an AI that creates names for things.

You will read a snippet of text, and come up with a short name for it based on the text.
For example, given a text snippet about the winter olympics, you might come up with the name "Winter Olympics".

# RULES
- OUTPUT ONLY THE NAME WITHOUT THE ORIGINAL TEXT OR EXTRA DIALOGUE FROM YOU.
- KEEP THE NAME LESS THAN 40 CHARACTERS OR 3 WORDS TOPS.
"""

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
                "description": "the keyword or query you want to find information about",
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
