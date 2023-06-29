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
LOCAL_MODELS = [
    "distilbert-base-uncased-distilled-squad",  # 256MB download, 500MB RAM
    "deepset/tinyroberta-squad2",  # 326MB download, 600-800MB RAM
    "deepset/roberta-base-squad2",  # 496MB download, 730MB RAM (RECOMMENDED)
    "deepset/roberta-large-squad2",  # 1.42GB download, 1.64GB RAM
]
LOCAL_EMBED_MODELS = [
    "all-mpnet-base-v2",  # 420MB download, 750MB RAM
    "all-MiniLM-L12-v2",  # 120MB download, 650MB RAM (RECOMMENDED)
    "all-MiniLM-L6-v2",  # 80MB download, 350MB RAM
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
