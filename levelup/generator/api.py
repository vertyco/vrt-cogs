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


def _resolve_font(font_name: t.Optional[str], font_b64: t.Optional[str] = None) -> t.Optional[str]:
    """Resolve font name to path, or decode font_b64 to temp file."""
    # First try to resolve by name from bundled fonts
    if font_name:
        font_path = imgtools.DEFAULT_FONTS / font_name
        if font_path.exists():
            return str(font_path)

    # If font_b64 provided, write to temp file
    if font_b64:
        try:
            import tempfile

            font_bytes = base64.b64decode(font_b64)
            fd, temp_path = tempfile.mkstemp(suffix=".ttf")
            with os.fdopen(fd, "wb") as f:
                f.write(font_bytes)
            log.debug(f"Wrote custom font to temp file: {temp_path}")
            return temp_path
        except Exception as e:
            log.warning(f"Failed to decode font_b64: {e}")

    return None


@app.post("/profile", response_model=ImageResponse)
async def generate_profile(request: ProfileRequest) -> ImageResponse:
    """Generate a profile image (new JSON API)."""
    log.info(f"Generating {request.style} profile for {request.username}")

    # Fetch assets
    avatar_bytes = await asyncio.to_thread(_download_url, request.avatar_url)
    background_bytes = (
        await asyncio.to_thread(_download_url, request.background_url) if request.style != "runescape" else None
    )
    prestige_emoji = (
        await asyncio.to_thread(_download_url, request.prestige_emoji_url) if request.style != "runescape" else None
    )
    role_icon = await asyncio.to_thread(_download_url, request.role_icon_url) if request.style != "runescape" else None

    # Resolve font (supports both bundled fonts by name and custom fonts via base64)
    font_path = _resolve_font(request.font_name, request.font_b64)

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

    try:
        img_bytes, animated = await asyncio.to_thread(generator, **kwargs)
    except Exception as e:
        log.exception(f"Profile generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    background_bytes = await asyncio.to_thread(_download_url, request.background_url)

    # Resolve font (supports both bundled fonts by name and custom fonts via base64)
    font_path = _resolve_font(request.font_name, request.font_b64)

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

    try:
        img_bytes, animated = await asyncio.to_thread(generate_level_img, **kwargs)
    except Exception as e:
        log.exception(f"Level-up generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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


def _parse_form_data(form_data: dict) -> dict:
    """Parse FormData into kwargs dict."""
    kwargs = {}
    for k, v in form_data.items():
        if hasattr(v, "file"):
            kwargs[k] = v.file.read()
        elif isinstance(v, str) and v.isdigit():
            kwargs[k] = int(v)
        elif isinstance(v, str) and v.lower() in ("true", "false"):
            kwargs[k] = v.lower() == "true"
        else:
            try:
                kwargs[k] = int(float(v))
            except (ValueError, TypeError):
                kwargs[k] = v

    # Parse color strings
    for color_key in ["base_color", "user_color", "stat_color", "level_bar_color", "color"]:
        if form_data.get(color_key):
            kwargs[color_key] = _parse_color(str(form_data.get(color_key)))

    return kwargs


@app.post("/fullprofile")
async def legacy_fullprofile(request: Request):
    """Legacy endpoint for full profile (FormData) - backward compatible."""
    form_data = await request.form()
    kwargs = _parse_form_data(dict(form_data))
    log.info(f"[Legacy] Generating full profile for {kwargs.get('username', 'unknown')}")

    try:
        img_bytes, animated = await asyncio.to_thread(generate_default_profile, **kwargs)
    except Exception as e:
        log.exception(f"Profile generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"b64": base64.b64encode(img_bytes).decode("utf-8"), "animated": animated}


@app.post("/runescape")
async def legacy_runescape(request: Request):
    """Legacy endpoint for runescape profile (FormData) - backward compatible."""
    form_data = await request.form()
    kwargs = _parse_form_data(dict(form_data))
    log.info(f"[Legacy] Generating runescape profile for {kwargs.get('username', 'unknown')}")

    try:
        img_bytes, animated = await asyncio.to_thread(generate_runescape_profile, **kwargs)
    except Exception as e:
        log.exception(f"Profile generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
