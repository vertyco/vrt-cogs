"""
Bot Arena - Image Utilities

Shared image loading and path resolution utilities.
This module centralizes all image file discovery to avoid code duplication.
"""

import typing as t
from pathlib import Path

import discord
from PIL import Image

# Path to data directory with part images
DATA_DIR = Path(__file__).parent.parent / "data"


def find_image_path(folder: str, name: str) -> t.Optional[Path]:
    """Find an image file, trying different name normalizations and extensions.

    This is the SINGLE SOURCE OF TRUTH for finding part images.
    It normalizes the part name to lowercase with underscores and tries
    both webp and png extensions.

    Args:
        folder: Subfolder in data directory (e.g., "chassis", "plating", "weapons")
        name: Part name to find (e.g., "DLZ-100", "Zintek")

    Returns:
        Path to the image file, or None if not found.
    """
    base_name = name.lower().replace(" ", "_")

    for ext in ("webp", "png"):
        # Try with original hyphens converted to underscores
        path = DATA_DIR / folder / f"{base_name}.{ext}"
        if path.exists():
            return path

        # Try converting any remaining hyphens to underscores
        path = DATA_DIR / folder / f"{base_name.replace('-', '_')}.{ext}"
        if path.exists():
            return path

    return None


def load_image(folder: str, name: str) -> t.Optional[Image.Image]:
    """Load an image from the data directory as RGBA.

    Args:
        folder: Subfolder in data directory (e.g., "chassis", "plating", "weapons")
        name: Part name to load

    Returns:
        PIL Image in RGBA mode, or None if not found/failed to load.
    """
    path = find_image_path(folder, name)
    if path:
        try:
            return Image.open(path).convert("RGBA")
        except (OSError, ValueError):
            # OSError: file not found, permission denied, corrupted image
            # ValueError: invalid image mode conversion
            pass
    return None


def load_image_bytes(folder: str, name: str, scale: int = 1) -> t.Optional[bytes]:
    """Load an image and return as PNG bytes.

    Args:
        folder: Subfolder in data directory
        name: Part name to load
        scale: Scale multiplier (e.g., 2 for 2x size)

    Returns:
        PNG image bytes, or None if not found.
    """
    import io

    img = load_image(folder, name)
    if not img:
        return None

    try:
        if scale != 1:
            new_size = (img.width * scale, img.height * scale)
            img = img.resize(new_size, Image.Resampling.NEAREST)

        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=90)
        return buffer.getvalue()
    except (OSError, ValueError):
        # OSError: I/O error during save
        # ValueError: invalid parameters
        return None


def get_part_image_file(part_type: str, part_name: str, filename: str) -> t.Optional[discord.File]:
    """Get a discord.File for a specific part image.

    Args:
        part_type: Type of part ("chassis", "plating", "component", "weapon")
        part_name: Name of the part
        filename: Filename to use for the discord.File attachment

    Returns:
        discord.File object, or None if image not found.
    """
    folder_map = {"chassis": "chassis", "plating": "plating", "component": "weapons", "weapon": "weapons"}
    folder = folder_map.get(part_type, part_type)

    path = find_image_path(folder, part_name)
    if path and path.exists():
        return discord.File(path, filename=filename)
    return None
