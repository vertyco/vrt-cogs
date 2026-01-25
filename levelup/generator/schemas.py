"""
Pydantic schemas for LevelUp image generation API.

These schemas define the contracts for:
- Subprocess communication (JSON file I/O)
- External API HTTP requests/responses
"""

import typing as t

from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    """Request schema for profile image generation."""

    # Profile style
    style: str = Field(
        default="default",
        description="Profile style: 'default', 'minimal', 'gaming', or 'runescape'",
    )

    # User data
    username: str = Field(default="User", description="Username to display")
    status: str = Field(default="online", description="User status: online, idle, dnd, offline, streaming")
    level: int = Field(default=1, description="User's current level")
    messages: int = Field(default=0, description="Total message count")
    voicetime: int = Field(default=0, description="Voice time in seconds")
    stars: int = Field(default=0, description="Star count")
    prestige: int = Field(default=0, description="Prestige level")
    position: int = Field(default=1, description="Leaderboard position")
    balance: int = Field(default=0, description="Economy balance")
    currency_name: str = Field(default="Credits", description="Currency name")

    # XP data
    previous_xp: int = Field(default=0, description="XP required for current level")
    current_xp: int = Field(default=0, description="Current XP amount")
    next_xp: int = Field(default=100, description="XP required for next level")

    # Asset URLs (preferred - API will fetch)
    avatar_url: t.Optional[str] = Field(default=None, description="URL to avatar image")
    background_url: t.Optional[str] = Field(default=None, description="URL to background image")
    prestige_emoji_url: t.Optional[str] = Field(default=None, description="URL to prestige emoji")
    role_icon_url: t.Optional[str] = Field(default=None, description="URL to role icon")

    # Asset bytes (base64 encoded, fallback if URLs fail)
    avatar_b64: t.Optional[str] = Field(default=None, description="Base64 encoded avatar bytes")
    background_b64: t.Optional[str] = Field(default=None, description="Base64 encoded background bytes")
    prestige_emoji_b64: t.Optional[str] = Field(default=None, description="Base64 encoded prestige emoji")
    role_icon_b64: t.Optional[str] = Field(default=None, description="Base64 encoded role icon")

    # Styling options
    blur: bool = Field(default=True, description="Blur background behind stats")
    base_color: t.Optional[t.Tuple[int, int, int]] = Field(default=None, description="Base RGB color from user's role")
    user_color: t.Optional[t.Tuple[int, int, int]] = Field(default=None, description="Username RGB color")
    stat_color: t.Optional[t.Tuple[int, int, int]] = Field(default=None, description="Stats text RGB color")
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = Field(default=None, description="Level bar RGB color")
    font_name: t.Optional[str] = Field(default=None, description="Font filename to use")
    font_b64: t.Optional[str] = Field(default=None, description="Base64 encoded font bytes (for custom fonts)")

    # Rendering options
    render_gif: bool = Field(default=False, description="Render animated GIF if avatar/background is animated")

    class Config:
        extra = "ignore"  # Ignore extra fields for forward compatibility


class LevelUpRequest(BaseModel):
    """Request schema for level-up alert image generation."""

    level: int = Field(default=1, description="New level achieved")

    # Asset URLs
    avatar_url: t.Optional[str] = Field(default=None, description="URL to avatar image")
    background_url: t.Optional[str] = Field(default=None, description="URL to background image")

    # Asset bytes (base64 encoded)
    avatar_b64: t.Optional[str] = Field(default=None, description="Base64 encoded avatar bytes")
    background_b64: t.Optional[str] = Field(default=None, description="Base64 encoded background bytes")

    # Styling
    color: t.Optional[t.Tuple[int, int, int]] = Field(default=None, description="Level text RGB color")
    font_name: t.Optional[str] = Field(default=None, description="Font filename to use")
    font_b64: t.Optional[str] = Field(default=None, description="Base64 encoded font bytes (for custom fonts)")

    # Rendering options
    render_gif: bool = Field(default=False, description="Render animated GIF if avatar/background is animated")

    class Config:
        extra = "ignore"


class ImageResponse(BaseModel):
    """Response schema for generated images."""

    success: bool = Field(default=True, description="Whether generation succeeded")
    error: t.Optional[str] = Field(default=None, description="Error message if failed")

    # For subprocess mode - path to generated file
    output_path: t.Optional[str] = Field(default=None, description="Path to generated image file")

    # For HTTP API mode - base64 encoded image
    image_b64: t.Optional[str] = Field(default=None, description="Base64 encoded image bytes")

    # Metadata
    animated: bool = Field(default=False, description="Whether the image is animated (GIF)")
    format: str = Field(default="webp", description="Image format: 'webp' or 'gif'")
    size: int = Field(default=0, description="Image size in bytes")
