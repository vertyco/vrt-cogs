"""
LevelUp External API Server

This module provides a FastAPI server for offloading image generation to a dedicated service.
It can be run standalone as an external service for large bot deployments.

Usage (as external service):
    uvicorn levelup.generator.api:app --host 0.0.0.0 --port 8888 --workers 4

    Or directly:
    python -m levelup.generator.api --port 8888 --host 0.0.0.0

Environment variables (.env file supported):
    LEVELUP_PORT=8888
    LEVELUP_HOST=0.0.0.0
    LEVELUP_LOG_DIR=/path/to/logs
"""

import asyncio
import base64
import logging
import os
import typing as t
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Determine if running as standalone service or imported by cog
try:
    from . import imgtools
    from .levelalert import generate_level_img
    from .styles.default import generate_default_profile
    from .styles.gaming import generate_gaming_profile
    from .styles.minimal import generate_minimal_profile
    from .styles.runescape import generate_runescape_profile

    _RUNNING_AS_SERVICE = False
except ImportError:
    import imgtools
    from levelalert import generate_level_img
    from styles.default import generate_default_profile
    from styles.gaming import generate_gaming_profile
    from styles.minimal import generate_minimal_profile
    from styles.runescape import generate_runescape_profile

    _RUNNING_AS_SERVICE = True

load_dotenv()

# Setup logging
LOG_DIR = Path(os.environ.get("LEVELUP_LOG_DIR", Path.home() / "levelup-api-logs"))
if _RUNNING_AS_SERVICE:
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    _formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%m/%d %I:%M:%S %p")
    _file_handler = RotatingFileHandler(str(LOG_DIR / "api.log"), maxBytes=51200, backupCount=2)
    _file_handler.setFormatter(_formatter)
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(_formatter)
    log = logging.getLogger("levelup.api")
    log.setLevel(logging.INFO)
    log.addHandler(_file_handler)
    log.addHandler(_stream_handler)
else:
    log = logging.getLogger("red.vrt.levelup.api")


# ============================================================================
# Pydantic Models for API
# ============================================================================


class ProfileRequest(BaseModel):
    """Request model for profile generation."""

    style: str = "default"
    username: str = "User"
    status: str = "online"
    level: int = 1
    messages: int = 0
    voicetime: int = 0
    stars: int = 0
    prestige: int = 0
    position: int = 1
    balance: int = 0
    currency_name: str = "Credits"
    previous_xp: int = 0
    current_xp: int = 0
    next_xp: int = 100
    blur: bool = True
    render_gif: bool = False

    # Colors as RGB tuples or None
    base_color: t.Optional[t.Tuple[int, int, int]] = None
    user_color: t.Optional[t.Tuple[int, int, int]] = None
    stat_color: t.Optional[t.Tuple[int, int, int]] = None
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = None

    # Asset URLs (server will fetch)
    avatar_url: t.Optional[str] = None
    background_url: t.Optional[str] = None
    background_b64: t.Optional[str] = None  # Base64 encoded background, for backgrounds stored on the bot
    prestige_emoji_url: t.Optional[str] = None
    role_icon_url: t.Optional[str] = None

    # Font
    font_name: t.Optional[str] = None
    font_b64: t.Optional[str] = None  # Base64 encoded font bytes for custom fonts

    class Config:
        extra = "ignore"


class LevelUpRequest(BaseModel):
    """Request model for level-up image generation."""

    level: int = 1
    render_gif: bool = False
    color: t.Optional[t.Tuple[int, int, int]] = None
    avatar_url: t.Optional[str] = None
    background_url: t.Optional[str] = None
    background_b64: t.Optional[str] = None  # Base64 encoded background, for backgrounds stored on the bot
    font_name: t.Optional[str] = None
    font_b64: t.Optional[str] = None  # Base64 encoded font bytes for custom fonts

    class Config:
        extra = "ignore"


class ImageResponse(BaseModel):
    """Response model for generated images."""

    b64: str  # Base64 encoded image
    animated: bool
    format: str = "webp"


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="LevelUp Image Generation API",
    version="2.0.0",
    description="External API for generating LevelUp profile and level-up images.",
)


@app.get("/health")
async def health_check():
    """Health check endpoint for readiness probes."""
    return {"status": "ok"}


def _download_url(url: str) -> t.Optional[bytes]:
    """Download image from URL."""
    if not url:
        return None
    return imgtools.download_image(url)


def get_asset(url: t.Optional[str], b64: t.Optional[str] = None) -> t.Optional[bytes]:
    """Download an asset, or decode it from base64 if there's no URL or the download fails."""
    if url and (data := _download_url(url)):
        return data
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception as e:
            log.warning(f"Failed to decode base64 asset: {e}")
    return None


def _resolve_font(
    font_name: t.Optional[str], font_bytes: t.Optional[bytes] = None
) -> t.Tuple[t.Optional[str], t.Optional[str]]:
    """Resolve a font name to a bundled font, or write custom font bytes to a temp file.

    Returns:
        (font path, temp file path to delete once rendered)
    """
    # First try to resolve by name from bundled fonts
    if font_name:
        font_path = imgtools.DEFAULT_FONTS / Path(font_name).name
        if font_path.exists():
            return str(font_path), None

    if font_bytes:
        try:
            import tempfile

            fd, temp_path = tempfile.mkstemp(suffix=".ttf")
            with os.fdopen(fd, "wb") as f:
                f.write(font_bytes)
            log.debug(f"Wrote custom font to temp file: {temp_path}")
            return temp_path, temp_path
        except Exception as e:
            log.warning(f"Failed to write custom font: {e}")

    return None, None


def decode_font(font_b64: t.Optional[str]) -> t.Optional[bytes]:
    if not font_b64:
        return None
    try:
        return base64.b64decode(font_b64)
    except Exception as e:
        log.warning(f"Failed to decode font_b64: {e}")
        return None


async def render(generator: t.Callable, kwargs: dict, temp_font: t.Optional[str] = None) -> t.Tuple[bytes, bool]:
    """Run a generator in a thread, cleaning up any temp font file afterwards."""
    try:
        return await asyncio.to_thread(generator, **kwargs)
    except Exception as e:
        log.exception(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_font:
            Path(temp_font).unlink(missing_ok=True)


@app.post("/profile", response_model=ImageResponse)
async def generate_profile(request: ProfileRequest) -> ImageResponse:
    """Generate a profile image (new JSON API)."""
    log.info(f"Generating {request.style} profile for {request.username}")

    # Fetch assets
    avatar_bytes = await asyncio.to_thread(_download_url, request.avatar_url)
    background_bytes = (
        await asyncio.to_thread(get_asset, request.background_url, request.background_b64)
        if request.style != "runescape"
        else None
    )
    prestige_emoji = (
        await asyncio.to_thread(_download_url, request.prestige_emoji_url) if request.style != "runescape" else None
    )
    role_icon = await asyncio.to_thread(_download_url, request.role_icon_url) if request.style != "runescape" else None

    # Resolve font (supports both bundled fonts by name and custom fonts via base64)
    font_path, temp_font = _resolve_font(request.font_name, decode_font(request.font_b64))

    # Build kwargs
    kwargs = {
        "avatar_bytes": avatar_bytes,
        "username": request.username,
        "status": request.status,
        "level": request.level,
        "messages": request.messages,
        "voicetime": request.voicetime,
        "stars": request.stars,
        "prestige": request.prestige,
        "position": request.position,
        "balance": request.balance,
        "currency_name": request.currency_name,
        "previous_xp": request.previous_xp,
        "current_xp": request.current_xp,
        "next_xp": request.next_xp,
        "blur": request.blur,
        "render_gif": request.render_gif,
    }

    if request.base_color:
        kwargs["base_color"] = request.base_color
    if request.user_color:
        kwargs["user_color"] = request.user_color
    if request.stat_color:
        kwargs["stat_color"] = request.stat_color
    if request.level_bar_color:
        kwargs["level_bar_color"] = request.level_bar_color
    if font_path:
        kwargs["font_path"] = font_path

    if request.style != "runescape":
        kwargs["background_bytes"] = background_bytes
        kwargs["prestige_emoji"] = prestige_emoji
        kwargs["role_icon"] = role_icon

    # Select generator
    generators = {
        "default": generate_default_profile,
        "minimal": generate_minimal_profile,
        "gaming": generate_gaming_profile,
        "runescape": generate_runescape_profile,
    }
    generator = generators.get(request.style, generate_default_profile)
    img_bytes, animated = await render(generator, kwargs, temp_font)

    return ImageResponse(
        b64=base64.b64encode(img_bytes).decode("utf-8"),
        animated=animated,
        format="gif" if animated else "webp",
    )


@app.post("/levelup", response_model=ImageResponse)
async def generate_levelup_image(request: LevelUpRequest) -> ImageResponse:
    """Generate a level-up alert image (new JSON API)."""
    log.info(f"Generating level-up image for level {request.level}")

    # Fetch assets
    avatar_bytes = await asyncio.to_thread(_download_url, request.avatar_url)
    background_bytes = await asyncio.to_thread(get_asset, request.background_url, request.background_b64)

    # Resolve font (supports both bundled fonts by name and custom fonts via base64)
    font_path, temp_font = _resolve_font(request.font_name, decode_font(request.font_b64))

    kwargs = {
        "avatar_bytes": avatar_bytes,
        "background_bytes": background_bytes,
        "level": request.level,
        "render_gif": request.render_gif,
    }

    if request.color:
        kwargs["color"] = request.color
    if font_path:
        kwargs["font_path"] = font_path

    img_bytes, animated = await render(generate_level_img, kwargs, temp_font)

    return ImageResponse(
        b64=base64.b64encode(img_bytes).decode("utf-8"),
        animated=animated,
        format="gif" if animated else "webp",
    )


# ============================================================================
# Legacy endpoints for backward compatibility with existing external deployments
# ============================================================================


def _parse_color(color_str: str) -> t.Tuple[int, int, int] | None:
    """Parse color string like '(255, 255, 255)' to tuple."""
    if not color_str or not isinstance(color_str, str) or color_str == "None":
        return None
    try:
        parts = [int(x) for x in color_str.strip("()").split(", ")]
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
        return None
    except (ValueError, TypeError):
        return None


INT_FIELDS = {
    "level",
    "messages",
    "voicetime",
    "stars",
    "prestige",
    "balance",
    "previous_xp",
    "current_xp",
    "next_xp",
    "position",
}
BOOL_FIELDS = {"blur", "render_gif", "square"}
# Form field names some cog versions send, mapped to the generator argument names
FIELD_ALIASES = {"prestige_emoji_bytes": "prestige_emoji", "role_icon_bytes": "role_icon"}


def _parse_form_data(form_data: dict) -> t.Tuple[dict, t.Optional[str]]:
    """Parse FormData into generator kwargs.

    Only known numeric and boolean fields get converted, so text like a username of "12345" stays text.

    Returns:
        (kwargs, temp font file path to delete once rendered)
    """
    kwargs = {}
    for k, v in form_data.items():
        k = FIELD_ALIASES.get(k, k)
        if hasattr(v, "file"):
            kwargs[k] = v.file.read()
        elif k in INT_FIELDS:
            try:
                kwargs[k] = int(float(v))
            except (ValueError, TypeError, OverflowError):
                log.warning(f"Ignoring invalid {k} value: {v}")
        elif k in BOOL_FIELDS:
            kwargs[k] = str(v).lower() == "true"
        else:
            kwargs[k] = v

    # Parse color strings
    for color_key in ["base_color", "user_color", "stat_color", "level_bar_color", "color"]:
        if form_data.get(color_key):
            kwargs[color_key] = _parse_color(str(form_data.get(color_key)))

    # Fonts arrive by name (bundled) or as file bytes (custom)
    temp_font = None
    font_name = kwargs.pop("font_name", None)
    font_bytes = kwargs.pop("font_bytes", None)
    if font_name or font_bytes:
        font_path, temp_font = _resolve_font(font_name, font_bytes if isinstance(font_bytes, bytes) else None)
        if font_path:
            kwargs["font_path"] = font_path

    return kwargs, temp_font


@app.post("/fullprofile")
async def legacy_fullprofile(request: Request):
    """Legacy endpoint for full profile (FormData) - backward compatible."""
    form_data = await request.form()
    kwargs, temp_font = _parse_form_data(dict(form_data))
    style = kwargs.pop("style", "default")
    log.info(f"[Legacy] Generating {style} profile for {kwargs.get('username', 'unknown')}")
    generators = {
        "default": generate_default_profile,
        "minimal": generate_minimal_profile,
        "gaming": generate_gaming_profile,
        "runescape": generate_runescape_profile,
    }
    img_bytes, animated = await render(generators.get(style, generate_default_profile), kwargs, temp_font)
    return {"b64": base64.b64encode(img_bytes).decode("utf-8"), "animated": animated}


@app.post("/runescape")
async def legacy_runescape(request: Request):
    """Legacy endpoint for runescape profile (FormData) - backward compatible."""
    form_data = await request.form()
    kwargs, temp_font = _parse_form_data(dict(form_data))
    kwargs.pop("style", None)
    log.info(f"[Legacy] Generating runescape profile for {kwargs.get('username', 'unknown')}")
    img_bytes, animated = await render(generate_runescape_profile, kwargs, temp_font)
    return {"b64": base64.b64encode(img_bytes).decode("utf-8"), "animated": animated}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0"}


# ============================================================================
# CLI Entry Point for running as external service
# ============================================================================

if __name__ == "__main__":
    import argparse

    try:
        from decouple import config as decouple_config
    except ImportError:

        def decouple_config(key, default, cast=str):
            return cast(os.environ.get(key, default))

    parser = argparse.ArgumentParser(description="Run LevelUp API server")
    parser.add_argument("--port", type=int, default=decouple_config("LEVELUP_PORT", 8888, cast=int))
    parser.add_argument("--host", default=decouple_config("LEVELUP_HOST", "0.0.0.0", cast=str))
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    import uvicorn

    log.info(f"Starting LevelUp API on {args.host}:{args.port} with {args.workers} workers")
    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        app_dir=str(Path(__file__).parent),
    )
