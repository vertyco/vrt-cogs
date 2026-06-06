from dataclasses import dataclass

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
    "gpt-5.2": 400000,
    "gpt-5.2-2025-12-11": 400000,
    "gpt-5.4": 1050000,
    "gpt-5.4-2026-03-05": 1050000,
    "gpt-5.4-mini": 400000,
    "gpt-5.4-mini-2026-03-17": 400000,
    "gpt-5.4-nano": 400000,
    "gpt-5.4-nano-2026-03-17": 400000,
    "gpt-5.5": 1050000,
    "gpt-5.5-2026-04-23": 1050000,
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
    "gpt-5.2",
    "gpt-5.2-2025-12-11",
    "gpt-5.4",
    "gpt-5.4-2026-03-05",
    "gpt-5.4-mini",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
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
    "gpt-5.2",
    "gpt-5.2-2025-12-11",
    "gpt-5.4",
    "gpt-5.4-2026-03-05",
    "gpt-5.4-mini",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
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
    "gpt-5.2",
    "gpt-5.2-2025-12-11",
    "gpt-5.4",
    "gpt-5.4-2026-03-05",
    "gpt-5.4-mini",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.4-nano",
    "gpt-5.4-nano-2026-03-17",
    "gpt-5.5",
    "gpt-5.5-2026-04-23",
]
OLD_TOOL_SCHEMA = [i for i in MODELS.keys() if i not in SUPPORTS_TOOLS]
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
    # Document types
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
    ".csv",
]
LOADING = "https://i.imgur.com/l3p6EMX.gif"
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
    "description": "Generate an image from a text prompt.",
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
                "description": "The quality of the image. For dall-e-3, use 'standard' or 'hd'. For gpt-image-1.5, use 'low', 'medium', or 'high'. Defaults to 'medium'.",
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
                "enum": ["dall-e-3", "gpt-image-1.5"],
                "description": "The model to use for image generation. dall-e-3 is the standard model, gpt-image-1.5 is a newer model with different pricing. Defaults to 'dall-e-3'",
            },
        },
        "required": ["prompt"],
    },
}
EDIT_IMAGE = {
    "name": "edit_image",
    "description": "Edit an existing image using the user's instructions.",
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
    "description": "Search the web for current information on a topic.",
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

THINK_AND_PLAN = {
    "name": "think_and_plan",
    "description": "Break a complex task into clear steps before doing it. Call this before multi-step work.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_summary": {
                "type": "string",
                "description": "A brief summary of the overall task or goal (1-2 sentences)",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "An ordered list of specific steps to complete the task. Each step should be actionable and clear.",
            },
            "considerations": {
                "type": "string",
                "description": "Any important considerations, edge cases, or potential issues to watch out for",
            },
        },
        "required": ["task_summary", "steps"],
    },
}
DO_NOT_RESPOND_SCHEMA = {
    "name": "do_not_respond",
    "description": "Use this when no response is needed.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
RESPOND_AND_CONTINUE = {
    "name": "respond_and_continue",
    "description": "Send a reply to the user and keep working afterward.",
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

CREATE_REMINDER = {
    "name": "create_reminder",
    "description": "Create a reminder for the user at a specified time.",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The reminder message to send to the user",
            },
            "remind_in": {
                "type": "string",
                "description": (
                    "When the reminder should fire. Accepts TWO formats ONLY:\n"
                    "1. Relative duration from now: '5 minutes', '2 hours', '1 day', '1d3h', '30m'\n"
                    "2. ISO 8601 datetime: '2025-08-04T15:00:00' (interpreted in the server's timezone)\n"
                    "IMPORTANT: Do NOT pass vague or relative day references like 'next Monday' or 'tomorrow'. "
                    "You know the current date and time from the system prompt - compute the exact date yourself "
                    "and pass it as an ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS). "
                    "For simple offsets (e.g. 'in 2 hours'), use a relative duration instead."
                ),
            },
            "dm": {
                "type": "boolean",
                "description": "Whether to send the reminder as a DM instead of pinging in the channel. Defaults to False.",
                "default": False,
            },
        },
        "required": ["message", "remind_in"],
    },
}

CANCEL_REMINDER = {
    "name": "cancel_reminder",
    "description": "Cancel a reminder by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "reminder_id": {
                "type": "string",
                "description": "The unique ID of the reminder to cancel",
            },
        },
        "required": ["reminder_id"],
    },
}

LIST_REMINDERS = {
    "name": "list_reminders",
    "description": "List the user's pending reminders.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

SCHEDULE_TASK = {
    "name": "schedule_task",
    "description": (
        "Schedule an autonomous task for later in this channel. "
        "Use this for follow-ups, periodic checks, or delayed actions the user requests."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": (
                    "The detailed instruction for what to do when the task fires. "
                    "Be specific - include what to check, what to report, and any context needed. "
                    "This will be your prompt when the task executes."
                ),
            },
            "execute_in": {
                "type": "string",
                "description": (
                    "When the task should execute. Accepts TWO formats ONLY:\n"
                    "1. Relative duration from now: '30 minutes', '1 hour', '2 days', '1w2d3h'\n"
                    "2. ISO 8601 datetime: '2025-08-04T15:00:00' (interpreted in the server's timezone)\n"
                    "IMPORTANT: Do NOT pass vague or relative day references like 'next Monday' or 'tomorrow'. "
                    "You know the current date and time from the system prompt - compute the exact date yourself "
                    "and pass it as an ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS). "
                    "For simple offsets (e.g. 'in 2 hours'), use a relative duration instead."
                ),
            },
            "context": {
                "type": "string",
                "description": "Optional context about why this task was scheduled, for your own reference when it fires.",
            },
        },
        "required": ["instruction", "execute_in"],
    },
}

CANCEL_SCHEDULED_TASK = {
    "name": "cancel_scheduled_task",
    "description": "Cancel a scheduled task by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The unique ID of the scheduled task to cancel",
            },
        },
        "required": ["task_id"],
    },
}

LIST_SCHEDULED_TASKS = {
    "name": "list_scheduled_tasks",
    "description": "List the user's pending scheduled tasks in this server.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

# ---- Tool result pruning constants (two-tier: soft-trim → hard-clear) ----
# Number of recent messages whose tool results are never pruned
TOOL_RESULT_PROTECT_RECENT = 6
# Soft-trim: keep head + tail of oversized tool results
TOOL_RESULT_SOFT_TRIM_HEAD = 1500  # chars to keep from the start
TOOL_RESULT_SOFT_TRIM_TAIL = 1500  # chars to keep from the end
TOOL_RESULT_SOFT_TRIM_MAX = 4000  # total chars after soft-trim
TOOL_RESULT_SOFT_MIN_CHARS = 500  # results smaller than this are never soft-trimmed
# Hard-clear: replace entire old tool result with a placeholder
TOOL_RESULT_HARD_CLEAR_PLACEHOLDER = "[Old tool result cleared to save context space]"
# Context fill ratios that trigger each tier (fraction of max_tokens)
TOOL_RESULT_SOFT_RATIO = 0.3  # soft-trim when context > 30% full
TOOL_RESULT_HARD_RATIO = 0.5  # hard-clear when context > 50% full
# Max fraction of context window a single tool result may consume
TOOL_RESULT_MAX_CONTEXT_SHARE = 0.15

# ---- Image retention ----
# Number of assistant response turns after which old images are evicted from history.
# Images are enormously expensive (thousands of tokens each); once the model has
# responded to them a few times they add very little value.
IMAGE_RETAIN_TURNS = 3

# ---- Compaction (LLM-based summarization) ----
# Minimum number of messages to keep verbatim after compaction (the "tail")
COMPACTION_KEEP_RECENT = 6
# Role used for the compaction summary injected into conversation
COMPACTION_SUMMARY_ROLE = "developer"
# System prompt sent to the compaction model
COMPACTION_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Condense the following conversation into a concise summary "
    "that preserves all key facts, decisions, user preferences, action items, and any tool results "
    "that are still relevant. Write in third person. Keep the summary under 500 words. "
    "Do NOT include greetings, filler, or redundant exchanges."
)

# ---------------------------------------------------------------------------
# Minimum prompt token counts required for provider-side prompt caching.
# ---------------------------------------------------------------------------
# Each entry is (model_prefix, min_tokens). The prefix is matched
# case-insensitively against the start of the model string. Entries are
# checked in order; the first match wins.
# Sources: OpenRouter docs (openrouter.ai/docs/guides/features/prompt-caching)
MIN_CACHE_TOKENS: list[tuple[str, int]] = [
    # Anthropic (via OpenRouter): explicit cache_control breakpoints required.
    # Match the dated snapshot slugs returned by providers, e.g.
    # ``anthropic/claude-4.5-haiku-20251001``.
    ("anthropic/claude-4.7-opus", 4096),
    ("anthropic/claude-4.6-opus", 4096),
    ("anthropic/claude-4.5-opus", 4096),
    ("anthropic/claude-4.6-sonnet", 2048),
    ("anthropic/claude-4.5-haiku", 4096),
    ("anthropic/claude-3.5-haiku", 2048),
    ("anthropic/claude-4.5-sonnet", 1024),
    ("anthropic/claude-4.1-opus", 1024),
    ("anthropic/claude-4-opus", 1024),
    ("anthropic/claude-4-sonnet", 1024),
    ("anthropic/claude-3.7-sonnet", 1024),
    ("anthropic/claude", 1024),
    # Google Gemini: implicit (auto) + explicit cache_control. 2.5 Flash is
    # 1,024; 2.5 Pro is 4,096. Default conservative.
    ("google/gemini-2.5-pro", 4096),
    ("google/gemini-2.5-flash", 1024),
    ("google/gemini", 4096),
    # OpenAI / Grok / DeepSeek / Groq / Moonshot: automatic, min 1,024.
    ("openai/", 1024),
    ("gpt-", 1024),
    ("o1", 1024),
    ("o3", 1024),
    ("grok", 1024),
    ("deepseek/", 1024),
    ("groq/", 1024),
    ("moonshot/", 1024),
    # Qwen: explicit cache_control required, 1,024 minimum.
    ("qwen/", 1024),
]


def get_min_cache_tokens(model: str) -> int:
    """Return the minimum prompt token count required for cache eligibility.

    If the model does not match any known prefix, returns 0 (unknown).
    """
    model_lower = model.lower()
    for prefix, min_tokens in MIN_CACHE_TOKENS:
        if model_lower.startswith(prefix.lower()):
            return min_tokens
    return 0


# OpenRouter model slug suffixes for provider routing shortcuts.
# Stripping these before profile lookups lets admins store model IDs like
# "anthropic/claude-3.5-sonnet:nitro" without triggering the auto fallback.
OR_SUFFIXES: tuple[str, ...] = (":nitro", ":floor", ":extended")


# ---------------------------------------------------------------------------
# Smartmod (AI moderation)
# ---------------------------------------------------------------------------
# Default per-category score thresholds (0.0 - 1.0) for OpenAI's
# omni-moderation-latest endpoint. A message is flagged for LLM review when a
# category's score meets or exceeds its threshold. Categories not listed fall
# back to a threshold of 1.1 (never flags) so new OpenAI categories stay
# inert until an admin opts in. Keys mirror the moderation API category names.
MOD_CATEGORY_DEFAULTS: dict[str, float] = {
    "harassment": 0.5,
    "harassment/threatening": 0.3,
    "hate": 0.5,
    "hate/threatening": 0.3,
    "illicit": 0.5,
    "illicit/violent": 0.4,
    "self-harm": 0.4,
    "self-harm/intent": 0.3,
    "self-harm/instructions": 0.3,
    "sexual": 0.6,
    "sexual/minors": 0.2,
    "violence": 0.6,
    "violence/graphic": 0.5,
}

# Special moderation system prompt, injected after the guild's normal system
# prompt for the smartmod review pass. {flagged_categories} is filled at runtime.
DEFAULT_MOD_PROMPT = """You are acting as an impartial moderation reviewer for this Discord server.

A message tripped the automated content filter for: {flagged_categories}

This prompt supports the same placeholder variables as the main system prompt (server name, channel name, display name, custom variables from other cogs, etc.).

Your job is to decide, IN CONTEXT, whether the flagged message actually warrants moderator action.

Guidelines:
- Read the surrounding conversation. Banter, sarcasm, quoting, song lyrics, and venting are often NOT violations.
- Weigh intent, target, and severity. A heated insult is not the same as a credible threat or slur directed at someone.
- Use the server rules, your grounded knowledge/embeddings, and any tools available to you to inform the decision.
- Be conservative: when in doubt, prefer no action or the lightest reasonable action. Humans make the final call.
- Do NOT message the channel or address users directly. This is a silent background review.

You MUST finish by calling exactly one of these two tools:
- `no_action_needed` - the content does not warrant action in context.
- `propose_mod_action` - the content warrants action; this sends an interactive panel to the staff team for confirmation (it does NOT take the action itself).

Pick the lightest action that fits the violation. Give staff a clear, specific analysis in `reason`, and put a short self-contained statement of what the user did and which rule it broke in `user_reason` (it becomes the actual reason recorded for whatever action staff confirms)."""


PROPOSE_MOD_ACTION = {
    "name": "propose_mod_action",
    "description": (
        "Propose a moderation action against the flagged user for staff review. Call this ONLY when the "
        "flagged content warrants action in context. This sends an interactive panel to the staff channel "
        "for a human to confirm; it does NOT perform the action automatically."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["warn", "timeout", "kick", "tempban", "ban", "delete", "ark_ban", "ark_tempban", "note"],
                "description": (
                    "The recommended action; pick the lightest that fits. "
                    "'warn' issues a tracked warning (or DMs the user); 'timeout' temporarily mutes the member; "
                    "'kick' removes them; 'tempban' bans then auto-unbans after a duration; 'ban' permanently bans; "
                    "'delete' only removes the message; 'note' records a private moderator note; "
                    "'ark_ban'/'ark_tempban' ban the user's linked in-game ARK player. "
                    "ONLY the actions present in this enum are available on this server - do not pick others."
                ),
            },
            "reason": {
                "type": "string",
                "description": (
                    "Your analysis for staff: what happened, the context, relevant history, and why the "
                    "suggested action fits. Shown only on the staff review panel."
                ),
            },
            "user_reason": {
                "type": "string",
                "description": (
                    "Short, self-contained reason (1-2 sentences) stating what the user did and which rule it "
                    "violated, e.g. 'Slur directed at another member in #general (Rule 1.1 Hate Speech)'. This "
                    "is used as the actual reason for whatever action staff confirms (audit log, warn DM), so "
                    "keep it action-agnostic - staff may pick a different action than the one you suggest. Do "
                    "NOT include escalation rationale, history, or meta commentary here."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "How severe the violation is, in context.",
            },
            "duration_minutes": {
                "type": "integer",
                "description": (
                    "Duration in minutes. Required for 'timeout' (max 40320 = 28 days), 'tempban', and "
                    "'ark_tempban'. Ignored for other actions."
                ),
            },
            "delete_message": {
                "type": "boolean",
                "description": "Whether the flagged message should also be deleted when the action is taken.",
                "default": False,
            },
        },
        "required": ["action", "reason", "user_reason", "severity"],
    },
}

NO_ACTION_NEEDED = {
    "name": "no_action_needed",
    "description": (
        "Conclude the review with no moderation action. Call this when the flagged content does not actually "
        "violate the rules in context (false positive, banter, quoting, venting, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "One or two short sentences on why no action is warranted. Do not restate the rules, "
                    "list everything you reviewed, or explain your reasoning step by step — just the conclusion."
                ),
            },
        },
        "required": ["reason"],
    },
}


@dataclass(frozen=True)
class ModAction:
    """A moderation action offered on the smartmod panel."""

    name: str
    label: str
    emoji: str
    perm: str  # discord guild permission required to click ("" => any staff / manage_messages)
    needs_duration: bool = False


# Built-in actions, always available. Ordered lightest -> heaviest.
BUILTIN_MOD_ACTIONS: list[ModAction] = [
    ModAction("warn", "Warn", "📣", "manage_messages"),
    ModAction("timeout", "Timeout", "⏳", "moderate_members", needs_duration=True),
    ModAction("kick", "Kick", "👢", "kick_members"),
    ModAction("tempban", "Temp ban", "⏲️", "ban_members", needs_duration=True),
    ModAction("ban", "Ban", "🔨", "ban_members"),
    ModAction("delete", "Delete message", "🗑️", "manage_messages"),
]

# Optional actions, surfaced only when the backing cog is loaded (and, for Ark, the flagged
# member has a linked in-game player). Assembled by SmartMod.available_mod_actions.
ARK_BAN_ACTION = ModAction("ark_ban", "Ark ban", "🦖", "ban_members")
ARK_TEMPBAN_ACTION = ModAction("ark_tempban", "Ark temp ban", "🦖", "ban_members", needs_duration=True)
NOTE_ACTION = ModAction("note", "Add note", "📝", "manage_messages")
MOD_ACTIONS_BY_NAME: dict[str, ModAction] = {
    a.name: a for a in [*BUILTIN_MOD_ACTIONS, ARK_BAN_ACTION, ARK_TEMPBAN_ACTION, NOTE_ACTION]
}
