MODELS = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-0613": 4096,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-3.5-turbo-16k-0613": 16384,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-32k-0613": 32768,
    "code-davinci-002": 8001,
    "text-davinci-003": 4097,
    "text-davinci-002": 4097,
    "text-curie-001": 2049,
    "text-babbage-001": 2049,
    "text-ada-001": 2049,
    "distilbert-base-uncased-distilled-squad": 2000,
}
SUPPORTS_FUNCTIONS = ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4-32k"]
CHAT = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-16k-0613",
    "gpt-4",
    "gpt-4-0613",
    "gpt-4-32k",
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
LOCAL_MODELS = {
    "deepset/tinyroberta-squad2": {
        "name": "Tiny Roberta",
        "size": 0.326,
        "ram": 0.8,
    },
    "deepset/roberta-base-squad2": {
        "name": "Roberta Base",
        "size": 0.496,
        "ram": 0.73,
    },
    "deepset/roberta-large-squad2": {
        "name": "Roberta Large",
        "size": 1.42,
        "ram": 1.64,
    },
}
LOCAL_GPT_MODELS = {
    "nous-hermes-13b.ggmlv3.q4_0.bin": {
        "name": "Hermes",
        "size": 6.82,
        "ram": 16,
        "params": "13 billion",
    },
    # "ggml-model-gpt4all-falcon-q4_0.bin": {
    #     "name": "GPT4ALL Falcon",
    #     "size": 4.06,
    #     "ram": 8,
    #     "params": "7 billion",
    # },
    "ggml-gpt4all-j-v1.3-groovy.bin": {
        "name": "Groovy",
        "size": 3.53,
        "ram": 8,
        "params": "7 billion",
    },
    "GPT4All-13B-snoozy.ggmlv3.q4_0.bin": {
        "name": "Snoozy",
        "size": 7.58,
        "ram": 16,
        "params": "13 billion",
    },
    "ggml-mpt-7b-chat.bin": {
        "name": "MPT Chat",
        "size": 4.52,
        "ram": 8,
        "params": "7 billion",
    },
    "orca-mini-7b.ggmlv3.q4_0.binn": {
        "name": "Orca",
        "size": 3.53,
        "ram": 8,
        "params": "7 billion",
    },
    "orca-mini-3b.ggmlv3.q4_0.bin": {
        "name": "Orca (Small)",
        "size": 1.8,
        "ram": 4,
        "params": "3 billion",
    },
    "orca-mini-13b.ggmlv3.q4_0.bin": {
        "name": "Orca (Large)",
        "size": 6.82,
        "ram": 16,
        "params": "13 billion",
    },
    "ggml-vicuna-7b-1.1-q4_2.bin": {
        "name": "Vicuna",
        "size": 3.92,
        "ram": 8,
        "params": "7 billion",
    },
    "ggml-vicuna-13b-1.1-q4_2.bin": {
        "name": "Vicuna (Large)",
        "size": 7.58,
        "ram": 16,
        "params": "13 billion",
    },
    "ggml-wizardLM-7B.q4_2.bin": {
        "name": "Wizard",
        "size": 3.92,
        "ram": 8,
        "params": "7 billion",
    },
    "wizardLM-13B-Uncensored.ggmlv3.q4_0.bin": {
        "name": "Wizard Uncensored",
        "size": 7.58,
        "ram": 16,
        "params": "13 billion",
    },
}
LOCAL_EMBED_MODELS = [
    "all-MiniLM-L6-v2",  # 80MB download, 350MB RAM
    "all-MiniLM-L12-v2",  # 120MB download, 650MB RAM (RECOMMENDED)
    "all-mpnet-base-v2",  # 420MB download, 750MB RAM
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
]
