VALID_SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536", "2048x2048", "3840x2160", "2160x3840"]
VALID_QUALITIES = ["auto", "low", "medium", "high"]
VALID_FORMATS = ["png", "jpeg", "webp"]
VALID_BACKGROUNDS = ["auto", "transparent", "opaque"]
# gpt-image-1.5 is kept (until its Dec 1, 2026 shutdown) because gpt-image-2
# doesn't currently support transparent backgrounds
VALID_MODELS = ["gpt-image-2", "gpt-image-1.5"]

MODEL_ORDER = ["gpt-image-2", "gpt-image-1.5"]
SIZE_ORDER = ["auto", "1024x1024", "1536x1024", "1024x1536", "2048x2048", "3840x2160", "2160x3840"]
QUALITY_ORDER = ["auto", "low", "medium", "high"]

MODEL_LABELS = {
    "gpt-image-2": "GPT Image 2",
    "gpt-image-1.5": "GPT Image 1.5 (transparency)",
}

# Sizes each model accepts ("auto" always allowed)
MODEL_SIZES = {
    "gpt-image-2": ["auto", "1024x1024", "1536x1024", "1024x1536", "2048x2048", "3840x2160", "2160x3840"],
    "gpt-image-1.5": ["auto", "1024x1024", "1536x1024", "1024x1536"],
}

# Models that support background="transparent"
TRANSPARENCY_MODELS = {"gpt-image-1.5"}

# Deprecated model names mapped to their replacement.
# OpenAI shuts down gpt-image-1 on Oct 23, 2026 and gpt-image-1.5 / gpt-image-1-mini on Dec 1, 2026.
LEGACY_MODEL_MAP = {
    "gpt-image-1": "gpt-image-2",
    "gpt-image-1-mini": "gpt-image-2",
}

SIZE_LABELS = {
    "auto": "Auto",
    "1024x1024": "1024x1024 (Square)",
    "1536x1024": "1536x1024 (Landscape)",
    "1024x1536": "1024x1536 (Portrait)",
    "2048x2048": "2048x2048 (Large Square)",
    "3840x2160": "3840x2160 (4K Landscape)",
    "2160x3840": "2160x3840 (4K Portrait)",
}

QUALITY_LABELS = {
    "auto": "Auto",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

# Pricing per generation in USD
# Format: PRICING[model][quality][size] = cost
# "auto" size uses 1024x1024 pricing as default
# gpt-image-2 is token-billed; 1024-class values come from OpenAI's cost table,
# 2048x2048 and 4K values are estimates (actual cost is computed from response usage when available)
PRICING: dict[str, dict[str, dict[str, float]]] = {
    "gpt-image-2": {
        "low": {
            "auto": 0.006,
            "1024x1024": 0.006,
            "1536x1024": 0.005,
            "1024x1536": 0.005,
            "2048x2048": 0.011,
            "3840x2160": 0.014,
            "2160x3840": 0.014,
        },
        "medium": {
            "auto": 0.053,
            "1024x1024": 0.053,
            "1536x1024": 0.041,
            "1024x1536": 0.041,
            "2048x2048": 0.09,
            "3840x2160": 0.12,
            "2160x3840": 0.12,
        },
        "high": {
            "auto": 0.211,
            "1024x1024": 0.211,
            "1536x1024": 0.165,
            "1024x1536": 0.165,
            "2048x2048": 0.32,
            "3840x2160": 0.41,
            "2160x3840": 0.41,
        },
        # Auto quality defaults to medium pricing
        "auto": {
            "auto": 0.053,
            "1024x1024": 0.053,
            "1536x1024": 0.041,
            "1024x1536": 0.041,
            "2048x2048": 0.09,
            "3840x2160": 0.12,
            "2160x3840": 0.12,
        },
    },
    "gpt-image-1.5": {
        "low": {
            "auto": 0.009,
            "1024x1024": 0.009,
            "1536x1024": 0.013,
            "1024x1536": 0.013,
        },
        "medium": {
            "auto": 0.034,
            "1024x1024": 0.034,
            "1536x1024": 0.05,
            "1024x1536": 0.05,
        },
        "high": {
            "auto": 0.133,
            "1024x1024": 0.133,
            "1536x1024": 0.20,
            "1024x1536": 0.20,
        },
        # Auto quality defaults to medium pricing
        "auto": {
            "auto": 0.034,
            "1024x1024": 0.034,
            "1536x1024": 0.05,
            "1024x1536": 0.05,
        },
    },
}

# Token pricing per 1M tokens (input, output) for exact cost from API usage
TOKEN_PRICING: dict[str, tuple[float, float]] = {
    "gpt-image-2": (8.0, 30.0),
    "gpt-image-1.5": (8.0, 32.0),
}


def normalize_option(raw: str | None, valid: list[str], labels: dict[str, str]) -> str | None:
    """Map a raw user-submitted option to its canonical value.

    editimage/makeimage expose model/size/quality via autocomplete, which does not restrict
    input, so Discord can submit free text (e.g. the display label "GPT Image 2" or wrong casing
    "High"). Match against the exact value, case-insensitively, or a display label before validation
    so a typed label resolves instead of being rejected. Unresolved input is returned unchanged so
    the caller's VALID_* check still surfaces a clear error.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if stripped in valid:
        return stripped
    lowered = stripped.lower()
    for value in valid:
        if value.lower() == lowered:
            return value
    for value, label in labels.items():
        if label.lower() == lowered:
            return value
    return stripped


def get_generation_cost(model: str, quality: str, size: str) -> float:
    """Calculate the cost for a generation based on model, quality, and size."""
    model_pricing = PRICING.get(model)
    if not model_pricing:
        return 0.0
    quality_pricing = model_pricing.get(quality, model_pricing.get("auto", {}))
    return quality_pricing.get(size, quality_pricing.get("auto", 0.0))


def get_actual_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the exact cost from API-reported token usage."""
    rates = TOKEN_PRICING.get(model)
    if not rates:
        return 0.0
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def format_cost(cost: float) -> str:
    """Format a cost value as a string with appropriate precision."""
    if cost < 0.01:
        return f"~${cost:.4f}"
    return f"~${cost:.3f}"


# Subscription tier presets for easy configuration
# Each tier defines: models, qualities, sizes, quota, and quota interval
class TierPreset:
    """Subscription tier preset configuration."""

    def __init__(
        self,
        name: str,
        description: str,
        models: list[str],
        qualities: list[str],
        sizes: list[str],
        quota: int,
        quota_interval: str = "daily",
        emoji: str = "🎨",
    ):
        self.name = name
        self.description = description
        self.models = models
        self.qualities = qualities
        self.sizes = sizes
        self.quota = quota
        self.quota_interval = quota_interval
        self.emoji = emoji

    def get_cost_range(self) -> tuple[float, float]:
        """Get the min and max cost for this tier's options."""
        costs: list[float] = []
        for model in self.models:
            model_sizes = MODEL_SIZES.get(model, VALID_SIZES)
            for quality in self.qualities:
                for size in self.sizes:
                    if size not in model_sizes:
                        continue
                    cost = get_generation_cost(model, quality, size)
                    if cost > 0:
                        costs.append(cost)
        if not costs:
            return (0.0, 0.0)
        return (min(costs), max(costs))


def format_quota(quota: int, interval: str) -> str:
    """Format a quota value for display."""
    if quota == 0:
        return "Unlimited"
    return f"{quota}/{interval}"


# Predefined subscription tiers
TIER_PRESETS: dict[str, TierPreset] = {
    "free": TierPreset(
        name="Free",
        description="Basic access with low quality square images",
        models=["gpt-image-2"],
        qualities=["low"],
        sizes=["1024x1024"],
        quota=5,
        quota_interval="daily",
        emoji="🆓",
    ),
    "basic": TierPreset(
        name="Basic",
        description="Low/medium quality with standard sizes",
        models=["gpt-image-2"],
        qualities=["low", "medium"],
        sizes=["1024x1024", "1536x1024", "1024x1536"],
        quota=15,
        quota_interval="daily",
        emoji="🥉",
    ),
    "standard": TierPreset(
        name="Standard",
        description="All models with low/medium quality and all sizes",
        models=["gpt-image-2", "gpt-image-1.5"],
        qualities=["low", "medium"],
        sizes=["1024x1024", "1536x1024", "1024x1536", "2048x2048", "3840x2160", "2160x3840"],
        quota=30,
        quota_interval="daily",
        emoji="🥈",
    ),
    "premium": TierPreset(
        name="Premium",
        description="Full access to all models, qualities, and sizes",
        models=["gpt-image-2", "gpt-image-1.5"],
        qualities=["low", "medium", "high"],
        sizes=["1024x1024", "1536x1024", "1024x1536", "2048x2048", "3840x2160", "2160x3840"],
        quota=0,  # Unlimited
        quota_interval="daily",
        emoji="🥇",
    ),
}
