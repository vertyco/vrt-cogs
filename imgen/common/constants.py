VALID_SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536"]
VALID_QUALITIES = ["auto", "low", "medium", "high"]
VALID_FORMATS = ["png", "jpeg", "webp"]
VALID_MODELS = ["gpt-image-1.5", "gpt-image-1-mini"]

MODEL_ORDER = ["gpt-image-1.5", "gpt-image-1-mini"]
SIZE_ORDER = ["auto", "1024x1024", "1536x1024", "1024x1536"]
QUALITY_ORDER = ["auto", "low", "medium", "high"]

MODEL_LABELS = {
    "gpt-image-1.5": "GPT Image 1.5",
    "gpt-image-1-mini": "GPT Image 1 Mini",
}

SIZE_LABELS = {
    "auto": "Auto",
    "1024x1024": "1024x1024 (Square)",
    "1536x1024": "1536x1024 (Landscape)",
    "1024x1536": "1024x1536 (Portrait)",
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
PRICING: dict[str, dict[str, dict[str, float]]] = {
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
    "gpt-image-1-mini": {
        "low": {
            "auto": 0.005,
            "1024x1024": 0.005,
            "1536x1024": 0.006,
            "1024x1536": 0.006,
        },
        "medium": {
            "auto": 0.011,
            "1024x1024": 0.011,
            "1536x1024": 0.015,
            "1024x1536": 0.015,
        },
        "high": {
            "auto": 0.036,
            "1024x1024": 0.036,
            "1536x1024": 0.052,
            "1024x1536": 0.052,
        },
        # Auto quality defaults to medium pricing
        "auto": {
            "auto": 0.011,
            "1024x1024": 0.011,
            "1536x1024": 0.015,
            "1024x1536": 0.015,
        },
    },
}


def get_generation_cost(model: str, quality: str, size: str) -> float:
    """Calculate the cost for a generation based on model, quality, and size."""
    model_pricing = PRICING.get(model)
    if not model_pricing:
        return 0.0
    quality_pricing = model_pricing.get(quality, model_pricing.get("auto", {}))
    return quality_pricing.get(size, quality_pricing.get("auto", 0.0))


def format_cost(cost: float) -> str:
    """Format a cost value as a string with appropriate precision."""
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.3f}"


# Subscription tier presets for easy configuration
# Each tier defines: models, qualities, sizes, and cooldown
class TierPreset:
    """Subscription tier preset configuration."""

    def __init__(
        self,
        name: str,
        description: str,
        models: list[str],
        qualities: list[str],
        sizes: list[str],
        cooldown_seconds: int,
        emoji: str = "🎨",
    ):
        self.name = name
        self.description = description
        self.models = models
        self.qualities = qualities
        self.sizes = sizes
        self.cooldown_seconds = cooldown_seconds
        self.emoji = emoji

    def get_cost_range(self) -> tuple[float, float]:
        """Get the min and max cost for this tier's options."""
        costs: list[float] = []
        for model in self.models:
            for quality in self.qualities:
                for size in self.sizes:
                    cost = get_generation_cost(model, quality, size)
                    if cost > 0:
                        costs.append(cost)
        if not costs:
            return (0.0, 0.0)
        return (min(costs), max(costs))


# Predefined subscription tiers
TIER_PRESETS: dict[str, TierPreset] = {
    "free": TierPreset(
        name="Free",
        description="Basic access with mini model and low quality",
        models=["gpt-image-1-mini"],
        qualities=["low"],
        sizes=["1024x1024"],
        cooldown_seconds=300,  # 5 minutes
        emoji="🆓",
    ),
    "basic": TierPreset(
        name="Basic",
        description="Mini model with low/medium quality and all sizes",
        models=["gpt-image-1-mini"],
        qualities=["low", "medium"],
        sizes=["1024x1024", "1536x1024", "1024x1536"],
        cooldown_seconds=120,  # 2 minutes
        emoji="🥉",
    ),
    "standard": TierPreset(
        name="Standard",
        description="All models with low/medium quality",
        models=["gpt-image-1.5", "gpt-image-1-mini"],
        qualities=["low", "medium"],
        sizes=["1024x1024", "1536x1024", "1024x1536"],
        cooldown_seconds=60,  # 1 minute
        emoji="🥈",
    ),
    "premium": TierPreset(
        name="Premium",
        description="Full access to all models, qualities, and sizes",
        models=["gpt-image-1.5", "gpt-image-1-mini"],
        qualities=["low", "medium", "high"],
        sizes=["1024x1024", "1536x1024", "1024x1536"],
        cooldown_seconds=30,  # 30 seconds
        emoji="🥇",
    ),
}
