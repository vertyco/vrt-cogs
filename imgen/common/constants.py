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
