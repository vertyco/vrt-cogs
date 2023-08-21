MODELS = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-0301": 4096,
    "gpt-3.5-turbo-0613": 4096,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-3.5-turbo-16k-0301": 16384,
    "gpt-3.5-turbo-16k-0613": 16384,
    "gpt-4": 8192,
    "gpt-4-0301": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-32k-0301": 32768,
    "gpt-4-32k-0613": 32768,
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
    "gpt-3.5-turbo-16k": [0.003, 0.004],
    "gpt-3.5-turbo-16k-0613": [0.003, 0.004],
    "gpt-4": [0.03, 0.06],
    "gpt-4-0301": [0.03, 0.06],
    "gpt-4-0613": [0.03, 0.06],
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
}
SUPPORTS_FUNCTIONS = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0613",
]
CHAT = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0301",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0301",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0301",
    "gpt-4-32k-0613",
    "code-davinci-002",
]
COMPLETION = [
    "text-davinci-003",
    "text-davinci-002",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",
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
    ".cc",
    ".ps1",
    ".bat",
    ".batch",
    ".shell",
    ".env",
]
REACT_SUMMARY_MESSAGE = """
Your job is to summarize text to use as embeddings. Respond only with the summary of the text.
"""
REACT_NAME_MESSAGE = """
Your job is to read a snippet of text and come up with a short descriptive name for it. Only respond with the name of the summary.
"""

CREATE_MEMORY = {
    "name": "create_memory",
    "description": "Use this when someone corrects you, tells you something new, or tells you to remember something.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_name": {
                "type": "string",
                "description": "A short name to describe the memory, perferrably less than 50 characters or 3 words tops",
            },
            "memory_text": {
                "type": "string",
                "description": "The information to remember, write as if you are informing yourself of the thing to remember.",
            },
        },
        "required": ["memory_name", "memory_text"],
    },
}
SEARCH_MEMORIES = {
    "name": "search_memories",
    "description": "Use this to find information about something, always use this if you are unsure about the answer to a question",
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
    "description": "Use this to edit existing memories, useful for correcting inaccurate memories after making them",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_name": {
                "type": "string",
                "description": "The name of the memory entry, case sensitive",
            },
            "memory_text": {
                "type": "string",
                "description": "The new text that will replace the current content of the memory",
            },
        },
        "required": ["memory_name", "memory_text"],
    },
}
