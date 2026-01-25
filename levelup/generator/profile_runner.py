#!/usr/bin/env python
"""
LevelUp Profile Runner - Standalone image generator for subprocess execution.

This script is designed to be called as a subprocess to isolate heavy PIL/Pillow
image processing from the main Discord bot process.

Usage:
    python profile_runner.py <input_json_path> <output_image_path>

Input JSON format (ProfileRequest or LevelUpRequest schema):
{
    "request_type": "profile",  // or "levelup"
    "style": "default",
    "username": "Spartan117",
    "avatar_url": "https://...",
    ...
}

Output:
- Creates image file at output_image_path
- Prints JSON result to stdout (ImageResponse schema)

Exit codes:
- 0: Success
- 1: Error (details in stdout JSON)
"""

import argparse
import base64
import json
import logging
import os
import sys
from pathlib import Path

# Setup logging to stderr so it doesn't interfere with JSON stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("levelup.profile_runner")

# Add parent directories to path for imports when run as subprocess
_THIS_DIR = Path(__file__).parent
_COG_DIR = _THIS_DIR.parent
_COGS_DIR = _COG_DIR.parent
for p in [str(_THIS_DIR), str(_COG_DIR), str(_COGS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)


def download_image(url: str) -> bytes | None:
    """Download image from URL using requests (sync for subprocess)."""
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content
    except Exception as e:
        log.warning(f"Failed to download image from {url}: {e}")
        return None


def get_asset_bytes(url: str | None, b64: str | None) -> bytes | None:
    """Get asset bytes from URL or base64, preferring URL."""
    if url:
        if data := download_image(url):
            return data
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception as e:
            log.warning(f"Failed to decode base64: {e}")
    return None


def generate_profile(input_data: dict, output_path: Path) -> dict:
    """Generate a profile image from input data."""
    # Import here to avoid loading PIL until needed
    from levelup.generator import imgtools
    from levelup.generator.styles.default import generate_default_profile
    from levelup.generator.styles.gaming import generate_gaming_profile
    from levelup.generator.styles.minimal import generate_minimal_profile
    from levelup.generator.styles.runescape import generate_runescape_profile

    style = input_data.get("style", "default")

    # Resolve assets
    avatar_bytes = get_asset_bytes(input_data.get("avatar_url"), input_data.get("avatar_b64"))
    background_bytes = get_asset_bytes(input_data.get("background_url"), input_data.get("background_b64"))
    prestige_emoji_bytes = get_asset_bytes(input_data.get("prestige_emoji_url"), input_data.get("prestige_emoji_b64"))
    role_icon_bytes = get_asset_bytes(input_data.get("role_icon_url"), input_data.get("role_icon_b64"))

    # Resolve font path
    font_path = None
    if font_name := input_data.get("font_name"):
        # Check default fonts first, then custom fonts path if provided
        default_fonts = imgtools.DEFAULT_FONTS
        if (default_fonts / font_name).exists():
            font_path = str(default_fonts / font_name)
        elif custom_fonts_dir := input_data.get("custom_fonts_dir"):
            custom_path = Path(custom_fonts_dir) / font_name
            if custom_path.exists():
                font_path = str(custom_path)

    # If font_b64 is provided (custom font), write to temp file
    if not font_path and (font_b64 := input_data.get("font_b64")):
        try:
            import tempfile

            font_bytes = base64.b64decode(font_b64)
            # Create temp file with .ttf extension
            fd, temp_font_path = tempfile.mkstemp(suffix=".ttf")
            with os.fdopen(fd, "wb") as f:
                f.write(font_bytes)
            font_path = temp_font_path
            log.debug(f"Wrote custom font to temp file: {temp_font_path}")
        except Exception as e:
            log.warning(f"Failed to decode font_b64: {e}")

    # Build kwargs for generator
    kwargs = {
        "avatar_bytes": avatar_bytes,
        "username": input_data.get("username", "User"),
        "status": input_data.get("status", "online"),
        "level": input_data.get("level", 1),
        "messages": input_data.get("messages", 0),
        "voicetime": input_data.get("voicetime", 0),
        "stars": input_data.get("stars", 0),
        "prestige": input_data.get("prestige", 0),
        "position": input_data.get("position", 1),
        "balance": input_data.get("balance", 0),
        "currency_name": input_data.get("currency_name", "Credits"),
        "previous_xp": input_data.get("previous_xp", 0),
        "current_xp": input_data.get("current_xp", 0),
        "next_xp": input_data.get("next_xp", 100),
        "blur": input_data.get("blur", True),
        "render_gif": input_data.get("render_gif", False),
    }

    # Add optional styling
    if base_color := input_data.get("base_color"):
        kwargs["base_color"] = tuple(base_color) if isinstance(base_color, list) else base_color
    if user_color := input_data.get("user_color"):
        kwargs["user_color"] = tuple(user_color) if isinstance(user_color, list) else user_color
    if stat_color := input_data.get("stat_color"):
        kwargs["stat_color"] = tuple(stat_color) if isinstance(stat_color, list) else stat_color
    if level_bar_color := input_data.get("level_bar_color"):
        kwargs["level_bar_color"] = tuple(level_bar_color) if isinstance(level_bar_color, list) else level_bar_color
    if font_path:
        kwargs["font_path"] = font_path

    # Add style-specific assets
    if style != "runescape":
        kwargs["background_bytes"] = background_bytes
        kwargs["prestige_emoji"] = prestige_emoji_bytes
        kwargs["role_icon"] = role_icon_bytes

    # Select generator based on style
    generators = {
        "default": generate_default_profile,
        "minimal": generate_minimal_profile,
        "gaming": generate_gaming_profile,
        "runescape": generate_runescape_profile,
    }

    generator_func = generators.get(style, generate_default_profile)

    # Generate image
    img_bytes, animated = generator_func(**kwargs)

    # Write output file
    output_path.write_bytes(img_bytes)

    return {
        "success": True,
        "output_path": str(output_path),
        "animated": animated,
        "format": "gif" if animated else "webp",
        "size": len(img_bytes),
    }


def generate_levelup(input_data: dict, output_path: Path) -> dict:
    """Generate a level-up alert image from input data."""
    from levelup.generator import imgtools
    from levelup.generator.levelalert import generate_level_img

    # Resolve assets
    avatar_bytes = get_asset_bytes(input_data.get("avatar_url"), input_data.get("avatar_b64"))
    background_bytes = get_asset_bytes(input_data.get("background_url"), input_data.get("background_b64"))

    # Resolve font path
    font_path = None
    if font_name := input_data.get("font_name"):
        default_fonts = imgtools.DEFAULT_FONTS
        if (default_fonts / font_name).exists():
            font_path = str(default_fonts / font_name)
        elif custom_fonts_dir := input_data.get("custom_fonts_dir"):
            custom_path = Path(custom_fonts_dir) / font_name
            if custom_path.exists():
                font_path = str(custom_path)

    # If font_b64 is provided (custom font), write to temp file
    if not font_path and (font_b64 := input_data.get("font_b64")):
        try:
            import tempfile

            font_bytes = base64.b64decode(font_b64)
            fd, temp_font_path = tempfile.mkstemp(suffix=".ttf")
            with os.fdopen(fd, "wb") as f:
                f.write(font_bytes)
            font_path = temp_font_path
            log.debug(f"Wrote custom font to temp file: {temp_font_path}")
        except Exception as e:
            log.warning(f"Failed to decode font_b64: {e}")

    # Build kwargs
    kwargs = {
        "avatar_bytes": avatar_bytes,
        "background_bytes": background_bytes,
        "level": input_data.get("level", 1),
        "render_gif": input_data.get("render_gif", False),
    }

    if color := input_data.get("color"):
        kwargs["color"] = tuple(color) if isinstance(color, list) else color
    if font_path:
        kwargs["font_path"] = font_path

    # Generate image
    img_bytes, animated = generate_level_img(**kwargs)

    # Write output file
    output_path.write_bytes(img_bytes)

    return {
        "success": True,
        "output_path": str(output_path),
        "animated": animated,
        "format": "gif" if animated else "webp",
        "size": len(img_bytes),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate LevelUp profile or level-up images")
    parser.add_argument("input", help="Path to input JSON file")
    parser.add_argument("output", help="Path to output image file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    # Validate input file exists
    if not input_path.exists():
        result = {"success": False, "error": f"Input file not found: {args.input}"}
        print(json.dumps(result))
        sys.exit(1)

    # Parse input JSON
    try:
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        result = {"success": False, "error": f"Invalid JSON: {e}"}
        print(json.dumps(result))
        sys.exit(1)

    # Determine request type and generate
    try:
        request_type = input_data.get("request_type", "profile")

        if request_type == "levelup":
            result = generate_levelup(input_data, output_path)
        else:
            result = generate_profile(input_data, output_path)

        print(json.dumps(result))

    except Exception as e:
        log.exception(f"Generation failed: {e}")
        result = {"success": False, "error": str(e)}
        print(json.dumps(result))
        sys.exit(1)


if __name__ == "__main__":
    main()
