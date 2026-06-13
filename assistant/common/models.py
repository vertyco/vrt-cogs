import logging
import typing as t
from datetime import datetime, timezone

import discord
import orjson
from pydantic import VERSION, BaseModel, Field, field_validator
from redbot.core.bot import Red

from .constants import DEFAULT_MOD_PROMPT, MOD_CATEGORY_DEFAULTS, SKILL_INDEX_HEADER

log = logging.getLogger("red.vrt.assistant.models")

DEFAULT_THINK_TAG_PREFIX = "<think>"
DEFAULT_THINK_TAG_SUFFIX = "</think>"
DEFAULT_SYSTEM_PROMPT = "You are a discord bot named {botname}, and are chatting with {username}."
DEFAULT_GUILD_MODEL = "gpt-5.4"
UNCATEGORIZED = "uncategorized"


def normalize_tool_category(category: t.Optional[str]) -> str:
    if category is None:
        return UNCATEGORIZED
    normalized = str(category).strip().lower()
    return normalized or UNCATEGORIZED


def render_tool_category(category: t.Optional[str]) -> str:
    return normalize_tool_category(category).replace("_", " ").title()


def get_category_state(
    function_names: t.Iterable[str], function_statuses: t.Mapping[str, bool]
) -> t.Literal["off", "mixed", "on"]:
    names = list(function_names)
    if not names:
        return "off"
    enabled = sum(function_statuses.get(name, False) for name in names)
    if enabled == 0:
        return "off"
    if enabled == len(names):
        return "on"
    return "mixed"


class AssistantBaseModel(BaseModel):
    @classmethod
    def model_validate(cls, obj: t.Any, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = True, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults, **kwargs)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults, **kwargs))


class Embedding(AssistantBaseModel):
    text: str
    embedding: t.List[float]
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    modified: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    model: str = "text-embedding-3-small"

    def created_at(self, relative: bool = False):
        t_type = "R" if relative else "F"
        return f"<t:{int(self.created.timestamp())}:{t_type}>"

    def modified_at(self, relative: bool = False):
        t_type = "R" if relative else "F"
        return f"<t:{int(self.modified.timestamp())}:{t_type}>"

    def update(self):
        self.modified = datetime.now(tz=timezone.utc)

    def __str__(self) -> str:
        return self.text


class CustomFunction(AssistantBaseModel):
    """Functions added by bot owner via string"""

    code: str
    jsonschema: dict
    permission_level: str = "user"  # user, mod, admin, owner
    required_permissions: t.List[str] = []  # Discord permission names (e.g. ["manage_messages"])
    category: str = UNCATEGORIZED
    requires_user_approval: bool = False

    @field_validator("required_permissions")
    @classmethod
    def validate_permissions(cls, v: t.List[str]) -> t.List[str]:
        valid_flags = set(discord.Permissions.VALID_FLAGS)
        invalid = [p for p in v if p not in valid_flags]
        if invalid:
            raise ValueError(f"Invalid Discord permission names: {', '.join(invalid)}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return normalize_tool_category(v)

    def prep(self) -> t.Callable:
        """Prep function for execution"""
        exec(self.code, globals())
        return globals()[self.jsonschema["name"]]


class Skill(AssistantBaseModel):
    """A named text procedure the model loads on demand (progressive disclosure).

    Skills are markdown-only - they orchestrate existing tools, they never
    execute code themselves.
    """

    description: str  # One line stating WHEN to use this skill (shown in the index)
    body: str  # The full procedure, returned by the load_skill tool
    enabled: bool = True
    status: str = "active"  # "draft" (pending staff approval) or "active"
    permission_level: str = "user"  # user, mod, admin, owner
    source: str = "manual"  # "manual" (command) or "correction" (proposed by the model)
    author_id: int = 0  # who triggered creation (staff member or proposing user)
    approver_id: int = 0  # staff member who approved/baked it
    source_message: str = ""  # jump URL of the conversation that spawned it
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    modified: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_used: t.Optional[datetime] = None
    use_count: int = 0

    def touch(self):
        self.modified = datetime.now(tz=timezone.utc)

    def mark_used(self):
        self.last_used = datetime.now(tz=timezone.utc)
        self.use_count += 1


async def member_meets_level(bot: Red, member: t.Optional[discord.Member], level: str) -> bool:
    """Same permission ladder as prep_functions: user < mod < admin < owner."""
    if level == "user":
        return True
    if member is None or not isinstance(member, discord.Member):
        return False
    if level == "mod":
        return member.guild_permissions.manage_messages or await bot.is_mod(member)
    if level == "admin":
        return member.guild_permissions.administrator or await bot.is_admin(member)
    if level == "owner":
        return await bot.is_owner(member)
    return False


def build_skill_index(skills: t.Dict[str, Skill], allowed: t.Iterable[str]) -> str:
    """Render the Skills index appended to the system prompt.

    Only active, enabled skills whose name is in ``allowed`` (the caller's
    permission-filtered list) appear. Sorted by name so the rendered block is
    byte-identical across requests (prompt-cache stability).
    """
    allowed_set = set(allowed)
    lines = [
        f"- {name}: {skill.description}"
        for name, skill in sorted(skills.items())
        if name in allowed_set and skill.enabled and skill.status == "active"
    ]
    if not lines:
        return ""
    return SKILL_INDEX_HEADER + "\n".join(lines)


class EndpointModelProfile(AssistantBaseModel):
    id: str
    kind: str = "llm"
    loaded: bool = False
    max_context_length: int = 0
    supports_vision: t.Optional[bool] = None
    supports_reasoning: t.Optional[bool] = None
    supports_tools: t.Optional[bool] = None


class EndpointProfile(AssistantBaseModel):
    base_url: str = ""
    provider: str = "unknown"
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    available_models: t.List[str] = []
    chat_models: t.Dict[str, EndpointModelProfile] = {}
    embedding_models: t.Dict[str, EndpointModelProfile] = {}
    active_chat_model: str = ""
    active_embedding_model: str = ""
    active_embedding_dimensions: int = 0


class SmartModSettings(AssistantBaseModel):
    """AI moderation (smartmod) per-guild configuration."""

    enabled: bool = False
    # Stage-1 scan uses OpenAI's free /moderations endpoint, which is OpenAI-only.
    # If the guild's chat endpoint is not OpenAI, set this override key so the scan
    # can still authenticate against api.openai.com directly.
    openai_key: t.Optional[str] = None
    # Review model (stage-2). Empty = use the guild's main chat model.
    review_model: str = ""
    mod_prompt: str = DEFAULT_MOD_PROMPT
    report_channel: t.Optional[int] = None
    staff_ping_roles: t.List[int] = []  # Roles to ping when an action is proposed
    # Per-category score overrides (0.0-1.0), merged over MOD_CATEGORY_DEFAULTS.
    thresholds: t.Dict[str, float] = {}
    # How many messages of context to pull around the flagged message.
    context_before: int = 10
    context_after: int = 5
    # Ignore these channel/category/role/user IDs.
    blacklist: t.List[int] = []
    # Only moderate these channel/category/role/user IDs (used only if blacklist is empty).
    whitelist: t.List[int] = []
    # Skip authors who have ban/kick/manage-messages permissions.
    exempt_staff: bool = True
    # Staff-defined trigger phrases that fire the review pipeline directly, in place of the
    # OpenAI moderation scan (and without needing an OpenAI key). Only '*' acts as a wildcard
    # (any run of characters); everything else is escaped, so patterns can never inject
    # catastrophic regex and lock the bot up on a public instance. A phrase with no leading/
    # trailing '*' matches on word boundaries.
    triggers: t.List[str] = []
    # Seconds the action panel buttons stay active before timing out.
    action_timeout: int = 3600
    # On panel timeout, execute the LLM's proposed action instead of just disabling buttons.
    auto_action_on_timeout: bool = False

    def effective_thresholds(self) -> t.Dict[str, float]:
        """Defaults merged with admin overrides; categories absent here never flag."""
        merged = dict(MOD_CATEGORY_DEFAULTS)
        merged.update(self.thresholds)
        return merged


class RolePrompt(BaseModel):
    text: str = ""
    replace: bool = False  # True = replace resolved base; False = append to it


class GuildSettings(AssistantBaseModel):
    system_prompt: t.Optional[str] = DEFAULT_SYSTEM_PROMPT
    prompt: str = ""
    channel_prompts: t.Dict[int, str] = {}
    allow_sys_prompt_override: bool = False  # Per convo system prompt
    embeddings: t.Dict[str, Embedding] = {}
    blacklist: t.List[int] = []  # Channel/Role/User IDs
    top_n: int = 3
    min_relatedness: float = 0.78
    question_mode: bool = False  # If True, only the first message and messages that end with ? will have emebddings
    channel_id: t.Optional[int] = 0  # The main auto-response channel ID
    listen_channels: t.List[int] = []  # Channels to listen to for auto-reply
    api_key: t.Optional[str] = None
    endswith_questionmark: bool = False
    min_length: int = 7
    max_retention: int = 0
    max_retention_time: int = 0
    max_response_tokens: int = 0
    max_tokens: int = 4000
    mention: bool = False
    mention_respond: bool = False
    enabled: bool = True  # Auto-reply channel
    model: str = DEFAULT_GUILD_MODEL
    embed_model: str = "text-embedding-3-small"  # Or text-embedding-3-large, text-embedding-ada-002
    collab_convos: bool = False
    reasoning_effort: str = "low"  # none, minimal, low, medium, high, xhigh (model-dependent)
    verbosity: str = "low"  # low, medium, high (gpt-5 only)
    think_tag_prefix: str = DEFAULT_THINK_TAG_PREFIX
    think_tag_suffix: str = DEFAULT_THINK_TAG_SUFFIX

    # Planner roles - users with these roles can use the think_and_plan tool
    planners: t.List[int] = []  # Role or user IDs who can use planning tools

    # Auto-answer
    auto_answer: bool = False  # Answer questions anywhere if one is detected and embedding is found for it
    auto_answer_threshold: float = 0.7  # 0.0 - 1.0  # Confidence threshold for auto-answer
    auto_answer_ignored_channels: t.List[int] = []  # Channel IDs to ignore auto-answer
    auto_answer_model: str = "gpt-5.4"  # Model to use for auto-answer

    # Trigger words - reply to messages containing specific keywords/regex patterns
    trigger_enabled: bool = False  # Whether trigger word feature is enabled
    trigger_phrases: t.List[str] = []  # List of regex patterns to match
    trigger_prompt: str = ""  # Custom prompt to use when triggered
    trigger_ignore_channels: t.List[int] = []  # Channels to ignore trigger words

    image_command: bool = True  # Allow image commands

    timezone: str = "UTC"
    temperature: float = 0.0  # 0.0 - 2.0
    frequency_penalty: float = 0.0  # -2.0 - 2.0
    presence_penalty: float = 0.0  # -2.0 - 2.0
    seed: t.Union[int, None] = None

    regex_blacklist: t.List[str] = [r"^As an AI language model,"]
    block_failed_regex: bool = False

    max_response_token_override: t.Dict[int, int] = {}
    max_token_role_override: t.Dict[int, int] = {}
    max_retention_role_override: t.Dict[int, int] = {}
    role_overrides: t.Dict[int, str] = {}  # Role overrides for model selection
    max_time_role_override: t.Dict[int, int] = {}
    reasoning_effort_role_override: t.Dict[int, str] = {}  # Role overrides for reasoning effort
    role_prompts: t.Dict[int, RolePrompt] = {}  # Per-role system prompt layers
    role_prompts_stack: bool = True  # Stack all matched role prompts vs highest-only

    vision_detail: str = "auto"  # high, low, auto

    # Per-guild endpoint overrides
    endpoint_override: t.Optional[str] = None
    endpoint_profile: t.Optional[EndpointProfile] = None

    # Compaction (LLM-based context summarization)
    compaction_enabled: bool = True  # Enable automatic LLM compaction before blind degradation
    compaction_model: str = ""  # Model to use for compaction (empty = use same model as chat)
    compaction_threshold: int = 0  # Token threshold to trigger compaction (0 = use max_tokens)

    use_function_calls: bool = False
    max_function_calls: int = 100  # Max calls in a row
    max_scheduled_tasks: int = 25  # Max pending scheduled tasks per user in this guild
    function_statuses: t.Dict[str, bool] = {}  # {"function_name": True/False for enabled/disabled}

    # ------------------------------------------------------------------
    # Trailing-context-block inclusion toggles.
    #
    # Maps a variable key to bool - True means "include in the trailing
    # ``[Current Context]`` user-context message". Keys can be:
    #   - ``var:<name>`` - individual variable inclusion (highest priority)
    #   - a builtin category key (e.g. ``time``, ``user_info``, ``bot``,
    #     ``channel``) - category-wide override for any variable in that
    #     category not explicitly set via ``var:<name>``
    #   - ``custom:<CogName>`` - override for an entire 3rd-party context
    #     variable source cog
    # When neither a per-var nor per-category key is present, the default
    # is **off** - fresh installs start with a blank slate so the admin
    # picks exactly which variables to surface in the trailing block.
    # ------------------------------------------------------------------
    context_block_var_statuses: t.Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Prompt caching: OpenRouter cache controls.
    # ------------------------------------------------------------------
    # Mode A - OpenRouter response caching (X-OpenRouter-Cache header).
    # Caches the entire response at the OpenRouter network layer.
    openrouter_cache_enabled: bool = True
    openrouter_cache_ttl: int = 300  # 1..86400 seconds
    # Mode B - Provider-level prompt cache via cache_control.
    # One of "off", "5m", "1h". Anthropic uses top-level cache_control;
    # Gemini / Qwen use explicit content-block breakpoints in the last
    # system message.
    openrouter_prompt_cache_ttl: str = "5m"

    # ------------------------------------------------------------------
    # OpenRouter provider routing preferences.
    # Sent as extra_body["provider"] on every OpenRouter request.
    # ------------------------------------------------------------------
    # Guild-wide model slug suffix (e.g. ":nitro", ":floor", ":extended").
    # Applied after model resolution; replaces any per-model suffix on conf.model.
    openrouter_model_suffix: t.Optional[str] = None
    # Ordered list of provider slugs to try (e.g. ["Fireworks", "Together"]).
    # Set allow_fallbacks=False to hard-pin to only these providers.
    openrouter_provider_order: t.List[str] = []
    # Whether to allow fallback providers when pinned ones are unavailable.
    # None = use OpenRouter default (True).
    openrouter_allow_fallbacks: t.Optional[bool] = None

    # Smartmod (AI moderation)
    smartmod: SmartModSettings = Field(default_factory=SmartModSettings)

    # Skills (on-demand procedure packs, see common/functions.py load_skill/propose_skill)
    skills: t.Dict[str, Skill] = {}
    skills_enabled: bool = False
    skill_propose_users: bool = False  # allow the model to propose skills from normal-user chats
    skill_admin_mode: str = "propose"  # off | propose | auto (auto = admin-triggered skills bake instantly)
    skill_channel: t.Optional[int] = None  # proposal review channel
    skill_ping_roles: t.List[int] = []  # roles pinged on new proposals
    max_skills: int = 50

    def get_user_model(self, member: t.Optional[discord.Member] = None) -> str:
        if not member or not self.role_overrides:
            return self.model
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.role_overrides:
                return self.role_overrides[role.id]
        return self.model

    def get_role_prompt_layers(
        self, member: t.Optional[discord.Member] = None
    ) -> t.Tuple[t.Optional[str], t.List[str]]:
        """Resolve role prompts for a member.

        Returns (replacement_base, append_texts):
          - replacement_base: text that replaces the resolved base, or None to keep it
          - append_texts: prompt texts appended after the (possibly replaced) base
        Texts are raw; the caller runs format_template on them.
        """
        if not member or not self.role_prompts:
            return None, []
        matched = [
            self.role_prompts[role.id]
            for role in sorted(member.roles, reverse=True)
            if role.id in self.role_prompts and self.role_prompts[role.id].text.strip()
        ]
        if not matched:
            return None, []
        if not self.role_prompts_stack:
            top = matched[0]
            return (top.text, []) if top.replace else (None, [top.text])
        replacement = next((rp.text for rp in matched if rp.replace), None)
        appends = [rp.text for rp in reversed(matched) if not rp.replace]
        return replacement, appends

    def get_user_max_tokens(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_token_role_override:
            return self.max_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_token_role_override:
                return self.max_token_role_override[role.id]
        return self.max_tokens

    def get_user_max_response_tokens(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_response_token_override:
            return self.max_response_tokens
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_response_token_override:
                return self.max_response_token_override[role.id]
        return self.max_response_tokens

    def get_user_max_retention(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_retention_role_override:
            return self.max_retention
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_retention_role_override:
                return self.max_retention_role_override[role.id]
        return self.max_retention

    def get_user_max_time(self, member: t.Optional[discord.Member] = None) -> int:
        if not member or not self.max_time_role_override:
            return self.max_retention_time
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.max_time_role_override:
                return self.max_time_role_override[role.id]
        return self.max_retention_time

    def get_user_reasoning_effort(self, member: t.Optional[discord.Member] = None) -> str:
        if not member or not self.reasoning_effort_role_override:
            return self.reasoning_effort
        sorted_roles = sorted(member.roles, reverse=True)
        for role in sorted_roles:
            if role.id in self.reasoning_effort_role_override:
                return self.reasoning_effort_role_override[role.id]
        return self.reasoning_effort


class Reminder(AssistantBaseModel):
    id: str  # unique identifier
    guild_id: int
    channel_id: int
    user_id: int
    message: str
    created_at: datetime
    remind_at: datetime
    dm: bool = False  # Whether to DM instead of channel ping


class ScheduledTask(AssistantBaseModel):
    """A deferred autonomous action the AI schedules for future execution."""

    id: str  # unique identifier
    guild_id: int
    channel_id: int
    user_id: int  # user who triggered the original conversation
    instruction: str  # the prompt/instruction the AI will execute
    context: str = ""  # optional context about why this task was scheduled
    created_at: datetime
    execute_at: datetime


class Conversation(AssistantBaseModel):
    messages: t.List[dict] = []
    last_updated: float = 0.0
    system_prompt_override: t.Optional[str] = None
    compaction_count: int = 0  # How many times this conversation has been compacted
    approved_tool_names: t.List[str] = []

    def get_images(self) -> t.List[str]:
        """Get all image b64 strings in the conversation
        Each string looks like "data:image/jpeg;base64,..." so we need to extract the base64 part

        """
        images = []
        for message in self.messages:
            if isinstance(message.get("content"), list):
                for item in message["content"]:
                    if item.get("type") == "image_url":
                        images.append(item["image_url"]["url"])
        if images:
            log.info(f"Found {len(images)} images in conversation.")
        return images

    def function_count(self) -> int:
        if not self.messages:
            return 0
        return sum(i["role"] in ["function", "tool"] for i in self.messages)

    def is_expired(self, conf: GuildSettings, member: t.Optional[discord.Member] = None):
        if not conf.get_user_max_time(member):
            return False
        return (datetime.now().timestamp() - self.last_updated) > conf.get_user_max_time(member)

    def cleanup(self, conf: GuildSettings, member: t.Optional[discord.Member] = None):
        if self.is_expired(conf, member):
            self.messages.clear()
            self.approved_tool_names.clear()
            return

        user_retention = conf.get_user_max_retention(member)
        if user_retention == 0:
            # Unlimited messages, only expire by time
            return

        # Turn-based retention: count user→assistant exchange *turns* rather
        # than raw messages.  A single turn may include a user message, several
        # tool calls/results, and an assistant reply.  This prevents heavy
        # tool-use sessions from being prematurely truncated.
        turn_count = 0
        keep_from = 0
        for idx in range(len(self.messages) - 1, -1, -1):
            if self.messages[idx].get("role") == "user":
                turn_count += 1
                if turn_count >= user_retention:
                    keep_from = idx
                    break
        if keep_from > 0:
            self.messages = self.messages[keep_from:]

    def reset(self):
        self.refresh()
        self.messages.clear()
        self.approved_tool_names.clear()

    def refresh(self):
        self.last_updated = datetime.now().timestamp()

    def overwrite(self, messages: t.List[dict]):
        self.refresh()
        self.messages = [i for i in messages if i["role"] not in ["system", "developer"]]

    def update_messages(
        self,
        message: str,
        role: str,
        name: str = None,
        tool_id: str = None,
        position: int = None,
    ) -> None:
        """Update conversation cache

        Args:
            message (str): the message
            role (str): 'system', 'user' or 'assistant'
            name (str): the name of the bot or user
            position (int): the index to place the message in
        """
        message: dict = {"role": role, "content": message}
        if name and role == "user":
            message["name"] = name
        if tool_id:
            message["tool_call_id"] = tool_id
        if position:
            self.messages.insert(position, message)
        else:
            self.messages.append(message)
        self.refresh()

    def prepare_chat(
        self,
        user_message: str,
        initial_prompt: str,
        system_prompt: str,
        name: str = None,
        images: t.List[str] = None,
        resolution: str = "auto",
        transient_user_context: str = "",
    ) -> t.List[dict]:
        """Pre-appends the prompts before the user's messages without modifying them.

        ``transient_user_context`` is sent as a payload-only trailing message
        after the user's clean turn, and it is NOT stored in conversation
        history. This preserves the clean conversation transcript while also
        allowing provider-side prompt caches to reuse the latest real user turn
        on the next request.
        """
        prepared = []
        if system_prompt.strip():
            prepared.append({"role": "developer", "content": system_prompt})
        if initial_prompt.strip():
            prepared.append({"role": "user", "content": initial_prompt})
        for stored_message in self.messages:
            copied = stored_message.copy()
            if copied.get("role") != "user":
                copied.pop("name", None)
            prepared.append(copied)

        if images:
            content: list = [{"type": "text", "text": user_message}]
            for img in images:
                if img.lower().startswith("http"):
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img, "detail": resolution},
                        }
                    )
                else:
                    if img.startswith("data:image/"):
                        image_string = img
                    else:
                        image_string = f"data:image/png;base64,{img}"
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image_string, "detail": resolution},
                        }
                    )
        else:
            content = user_message

        # Store the clean message (no transient context) in conversation history.
        history_payload = {"role": "user", "content": content}
        if name:
            history_payload["name"] = name
        self.messages.append(history_payload)

        # Send the clean user turn to the API so it can become part of the
        # reusable cached prefix on the next request.
        api_payload = {"role": "user", "content": content}
        if name:
            api_payload["name"] = name
        prepared.append(api_payload)

        if transient_user_context.strip():
            prepared.append(
                {
                    "role": "user",
                    "content": f"Additional context for the previous user message:\n\n{transient_user_context}",
                }
            )

        self.refresh()
        return prepared


class DB(AssistantBaseModel):
    configs: t.Dict[int, GuildSettings] = {}
    conversations: t.Dict[str, Conversation] = {}
    persistent_conversations: bool = False
    functions: t.Dict[str, CustomFunction] = {}
    listen_to_bots: bool = False
    reasoning_as_files: bool = True
    brave_api_key: t.Optional[str] = None
    default_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    default_model: str = ""  # Global fallback chat model for guilds that haven't set their own
    endpoint_override: t.Optional[str] = None
    endpoint_api_key: t.Optional[str] = None
    endpoint_profile: t.Optional[EndpointProfile] = None
    reminders: t.Dict[str, Reminder] = {}  # reminder_id -> Reminder
    scheduled_tasks: t.Dict[str, ScheduledTask] = {}  # task_id -> ScheduledTask

    def get_effective_system_prompt(self, conf: GuildSettings) -> str:
        if not conf.system_prompt or conf.system_prompt == DEFAULT_SYSTEM_PROMPT:
            return self.default_system_prompt
        return conf.system_prompt

    def get_effective_model(self, conf: GuildSettings, member: t.Optional[discord.Member] = None) -> str:
        """Guild's chosen model, falling back to the global default_model when it's untouched."""
        model = conf.get_user_model(member)
        if self.default_model and model == DEFAULT_GUILD_MODEL:
            return self.default_model
        return model

    def get_conf(self, guild: t.Union[discord.Guild, int]) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        if gid not in self.configs:
            self.configs[gid] = GuildSettings()
        return self.configs[gid]

    def get_conversation(
        self,
        member_id: int,
        channel_id: int,
        guild_id: int,
    ) -> Conversation:
        key = f"{member_id}-{channel_id}-{guild_id}"
        return self.conversations.setdefault(key, Conversation())

    def get_function_catalog(self, bot: Red, registry: t.Dict[str, t.Dict[str, dict]]) -> t.List[dict]:
        catalog: t.List[dict] = []

        for function_name, function_data in self.functions.items():
            catalog.append(
                {
                    "name": function_name,
                    "source": "Custom",
                    "category": normalize_tool_category(function_data.category),
                    "permission_level": function_data.permission_level,
                    "required_permissions": list(function_data.required_permissions),
                    "requires_user_approval": function_data.requires_user_approval,
                    "schema": function_data.jsonschema,
                }
            )

        for cog_name, function_schemas in registry.items():
            cog = bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, data in function_schemas.items():
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    continue
                catalog.append(
                    {
                        "name": function_name,
                        "source": cog_name,
                        "category": normalize_tool_category(data.get("category")),
                        "permission_level": data["permission_level"],
                        "required_permissions": list(data.get("required_permissions", [])),
                        "requires_user_approval": data.get("requires_user_approval", False),
                        "schema": data["schema"],
                    }
                )

        return catalog

    def get_function_callable(
        self,
        bot: Red,
        registry: t.Dict[str, t.Dict[str, dict]],
        function_name: str,
        source: str,
    ) -> t.Optional[t.Callable]:
        if source == "Custom":
            custom_function = self.functions.get(function_name)
            if custom_function is not None:
                return custom_function.prep()
            return None

        function_schemas = registry.get(source)
        if not function_schemas or function_name not in function_schemas:
            return None

        cog = bot.get_cog(source)
        if not cog:
            return None

        function_obj = getattr(cog, function_name, None)
        if function_obj is not None:
            return function_obj

        return None

    def get_functions_by_category(
        self, bot: Red, registry: t.Dict[str, t.Dict[str, dict]]
    ) -> t.Dict[str, t.List[dict]]:
        grouped: t.Dict[str, t.List[dict]] = {}
        for entry in self.get_function_catalog(bot, registry):
            grouped.setdefault(entry["category"], []).append(entry)
        return grouped

    def get_context_variable_catalog(self, bot: Red, registry: t.Dict[str, t.Dict[str, dict]]) -> t.List[dict]:
        catalog: t.List[dict] = []
        for cog_name, variables in registry.items():
            cog = bot.get_cog(cog_name)
            if not cog:
                continue
            for variable_name, data in variables.items():
                fetch_method = data.get("fetch_method", variable_name)
                fetch_obj = getattr(cog, fetch_method, None)
                if fetch_obj is None:
                    continue
                catalog.append(
                    {
                        "name": variable_name,
                        "source": cog_name,
                        "description": data["description"],
                        "permission_level": data["permission_level"],
                        "required_permissions": list(data.get("required_permissions", [])),
                        "fetch_method": fetch_method,
                        # cache_safe = the *cog* declares this variable as dynamic
                        # (cache_safe=True → dynamic, default) versus stable
                        # (cache_safe=False → always inlined into prompts).
                        # Admins control floating-block inclusion separately via
                        # the `[p]floatingcontext` view.
                        "cache_safe": bool(data.get("cache_safe", True)),
                    }
                )
        return catalog

    def get_context_variable_callable(
        self,
        bot: Red,
        registry: t.Dict[str, t.Dict[str, dict]],
        variable_name: str,
        source: str,
    ) -> t.Optional[t.Callable]:
        variable_entries = registry.get(source)
        if not variable_entries or variable_name not in variable_entries:
            return None

        cog = bot.get_cog(source)
        if not cog:
            return None

        fetch_method = variable_entries[variable_name].get("fetch_method", variable_name)
        callable_obj = getattr(cog, fetch_method, None)
        if callable_obj is not None:
            return callable_obj
        return None

    async def prep_context_variables(
        self,
        bot: Red,
        registry: t.Dict[str, t.Dict[str, dict]],
        requested_names: t.Optional[t.Iterable[str]] = None,
        member: discord.Member = None,
        showall: bool = False,
    ) -> t.Dict[str, dict]:
        async def can_use(perm_level: str) -> bool:
            if perm_level == "user":
                return True
            if member is None:
                return False
            if perm_level == "mod":
                perms = [
                    member.guild_permissions.manage_messages,
                    await bot.is_mod(member),
                ]
                return any(perms)
            if perm_level == "admin":
                perms = [
                    member.guild_permissions.administrator,
                    await bot.is_admin(member),
                ]
                return any(perms)
            if perm_level == "owner":
                return await bot.is_owner(member)
            return False

        def has_discord_perms(required_permissions: t.List[str]) -> bool:
            if not required_permissions:
                return True
            if member is None:
                return False
            guild_perms = member.guild_permissions
            return all(getattr(guild_perms, perm, False) for perm in required_permissions)

        target_names = set(requested_names) if requested_names is not None else None
        prepared: t.Dict[str, dict] = {}

        for entry in self.get_context_variable_catalog(bot, registry):
            variable_name = entry["name"]
            if target_names is not None and variable_name not in target_names:
                continue
            if variable_name in prepared:
                continue
            if not await can_use(entry["permission_level"]) and not showall:
                continue
            if not has_discord_perms(entry["required_permissions"]) and not showall:
                continue
            callable_obj = self.get_context_variable_callable(bot, registry, variable_name, entry["source"])
            if callable_obj is None:
                continue
            prepared[variable_name] = {"entry": entry, "callable": callable_obj}

        return prepared

    async def prep_functions(
        self,
        bot: Red,
        conf: GuildSettings,
        registry: t.Dict[str, t.Dict[str, dict]],
        member: discord.Member = None,
        showall: bool = False,
    ) -> t.Tuple[t.List[dict], t.Dict[str, t.Callable]]:
        """Prep custom and registry functions for use with the API

        Args:
            bot (Red): Red instance
            conf (GuildSettings): current guild settings
            registry (t.Dict[str, t.Dict[str, dict]]): 3rd party cog registry dict

        Returns:
            t.Tuple[t.List[dict], t.Dict[str, t.Callable]]: t.List of json function schemas and a dict mapping to their callables
        """

        async def can_use(perm_level: str) -> bool:
            if perm_level == "user":
                return True
            if member is None:
                return False
            if perm_level == "mod":
                perms = [
                    member.guild_permissions.manage_messages,
                    await bot.is_mod(member),
                ]
                return any(perms)
            if perm_level == "admin":
                perms = [
                    member.guild_permissions.administrator,
                    await bot.is_admin(member),
                ]
                return any(perms)
            if perm_level == "owner":
                return await bot.is_owner(member)
            return False

        def has_discord_perms(required_permissions: t.List[str]) -> bool:
            if not required_permissions:
                return True
            if member is None:
                return False
            guild_perms = member.guild_permissions
            return all(getattr(guild_perms, perm, False) for perm in required_permissions)

        function_calls = []
        function_map = {}

        for entry in self.get_function_catalog(bot, registry):
            function_name = entry["name"]
            if not conf.function_statuses.get(function_name, False):
                continue
            if function_name in function_map:
                continue
            if not await can_use(entry["permission_level"]) and not showall:
                if member is not None:
                    log.debug(
                        f"{member.name} cannot use {function_name} with {entry['permission_level']} permission level."
                    )
                continue
            if not has_discord_perms(entry["required_permissions"]) and not showall:
                if member is not None:
                    log.debug(
                        f"{member.name} lacks required discord permissions for {function_name}: "
                        f"{entry['required_permissions']}"
                    )
                continue
            callable_obj = self.get_function_callable(bot, registry, function_name, entry["source"])
            if callable_obj is None:
                continue
            function_calls.append(entry["schema"])
            function_map[function_name] = callable_obj

        # Sort tools deterministically by name so the cached prompt prefix
        # stays stable across requests even if registry iteration order
        # differs (Tool Stabilization).
        function_calls.sort(key=lambda schema: schema.get("name", ""))

        log.debug(f"Prepped: {function_map.keys()}")
        return function_calls, function_map


class NoAPIKey(Exception):
    """Model API key not set"""


class EmbeddingEntryExists(Exception):
    """Entry name for embedding exits"""
