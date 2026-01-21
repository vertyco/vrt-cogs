"""
Bot Arena - Bot Sprite Renderer

Single source of truth for rendering bot sprites with plating and weapon.
Used by both battle renderer (video frames) and garage preview (static images).

Note: Chassis images are not rendered because plating always covers them completely.
"""

import io
import math
import typing as t

from PIL import Image

from .image_utils import load_image

if t.TYPE_CHECKING:
    from .models import PartsRegistry


def _rotate_around_pivot(
    img: Image.Image, angle: float, pivot_x: float, pivot_y: float
) -> tuple[Image.Image, tuple[int, int]]:
    """Rotate an image around a custom pivot point.

    Args:
        img: The image to rotate
        angle: Rotation angle in degrees (positive = counter-clockwise)
        pivot_x: X offset of pivot from image center (positive = right)
        pivot_y: Y offset of pivot from image center (positive = down)

    Returns:
        (rotated_image, (offset_x, offset_y)) - The rotated image and the offset
        to apply when positioning so the pivot stays at the same world position.
    """
    if pivot_x == 0.0 and pivot_y == 0.0:
        rotated = img.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
        return rotated, (0, 0)

    cx, cy = img.width / 2, img.height / 2
    pivot_img_x = cx + pivot_x
    pivot_img_y = cy + pivot_y

    diag = int(math.sqrt(img.width**2 + img.height**2))
    canvas_size = diag + abs(int(pivot_x)) * 2 + abs(int(pivot_y)) * 2

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    paste_x = (canvas_size - img.width) // 2
    paste_y = (canvas_size - img.height) // 2
    canvas.paste(img, (paste_x, paste_y), img)

    canvas_pivot_x = paste_x + pivot_img_x
    canvas_pivot_y = paste_y + pivot_img_y

    rotated_canvas = canvas.rotate(
        -angle, expand=False, center=(canvas_pivot_x, canvas_pivot_y), resample=Image.Resampling.BICUBIC
    )

    bbox = rotated_canvas.getbbox()
    if bbox:
        rotated_canvas = rotated_canvas.crop(bbox)
        crop_offset_x = bbox[0]
        crop_offset_y = bbox[1]

        new_cx = rotated_canvas.width / 2
        new_cy = rotated_canvas.height / 2
        pivot_in_crop_x = canvas_pivot_x - crop_offset_x
        pivot_in_crop_y = canvas_pivot_y - crop_offset_y

        offset_x = int(new_cx - pivot_in_crop_x)
        offset_y = int(new_cy - pivot_in_crop_y)

        return rotated_canvas, (offset_x, offset_y)

    return rotated_canvas, (0, 0)


def _apply_tint(img: Image.Image, tint_color: tuple[int, int, int], intensity: float) -> Image.Image:
    """Apply a color tint to an image."""
    r, g, b, a = img.split()
    tint_r = r.point(lambda p: int(p * (1 - intensity) + tint_color[0] * intensity))
    tint_g = g.point(lambda p: int(p * (1 - intensity) + tint_color[1] * intensity))
    tint_b = b.point(lambda p: int(p * (1 - intensity) + tint_color[2] * intensity))
    return Image.merge("RGBA", (tint_r, tint_g, tint_b, a))


def render_bot_sprite(
    plating_name: str,
    registry: "PartsRegistry",
    weapon_name: t.Optional[str] = None,
    orientation: float = 0,
    weapon_orientation: t.Optional[float] = None,
    scale: float = 1.0,
    tint_color: t.Optional[tuple[int, int, int]] = None,
    tint_intensity: float = 0.4,
) -> t.Optional[Image.Image]:
    """Render a complete bot sprite with plating and weapon.

    This is the SINGLE SOURCE OF TRUTH for bot rendering. Both battle frames
    and garage previews use this function to ensure visual consistency.

    Note: Chassis is not rendered because plating always covers it completely.

    Args:
        plating_name: Name of the plating to render (required, serves as the base layer)
        registry: PartsRegistry for looking up pivot points
        weapon_name: Name of weapon to attach (optional)
        orientation: Rotation angle of the bot in degrees (0 = facing right)
        weapon_orientation: Rotation angle of weapon turret (defaults to orientation)
        scale: Scale multiplier for output (1.0 = native size, 0.5 = half size)
        tint_color: RGB tuple for team color tint (optional)
        tint_intensity: How strongly to apply tint (0.0-1.0)

    Returns:
        RGBA PIL Image of the rendered bot, or None if plating not found.
        The image is sized to fit the content with transparent background.
    """
    if weapon_orientation is None:
        weapon_orientation = orientation

    # Load plating image (this is the base layer)
    plating_img = load_image("plating", plating_name)
    if not plating_img:
        return None

    # Apply scale to plating
    if scale != 1.0:
        new_size = (int(plating_img.width * scale), int(plating_img.height * scale))
        plating_img = plating_img.resize(new_size, Image.Resampling.LANCZOS)

    # Get plating center pivot from registry
    plating = registry.get_plating(plating_name)
    plating_center_x = plating.center_x * scale
    plating_center_y = plating.center_y * scale

    # Rotate plating around its pivot
    rotated_plating, _ = _rotate_around_pivot(plating_img, orientation, plating_center_x, plating_center_y)

    # Apply team tint if specified
    if tint_color:
        rotated_plating = _apply_tint(rotated_plating, tint_color, tint_intensity)

    # Load and position weapon if specified
    if weapon_name:
        weapon_img = load_image("weapons", weapon_name)
        if weapon_img:
            # Scale weapon
            if scale != 1.0:
                new_size = (int(weapon_img.width * scale), int(weapon_img.height * scale))
                weapon_img = weapon_img.resize(new_size, Image.Resampling.LANCZOS)

            # Get weapon mount point from component
            component = registry.get_component(weapon_name)
            weapon_mount_x = component.mount_x * scale
            weapon_mount_y = component.mount_y * scale

            # Rotate weapon around its mount point
            rotated_weapon, weapon_offset = _rotate_around_pivot(
                weapon_img, weapon_orientation, weapon_mount_x, weapon_mount_y
            )

            # Determine the attachment point on the plating
            # Use the plating's weapon mount point relative to its center
            attachment_point_x = rotated_plating.width // 2 + int(plating.weapon_mount_x * scale)
            attachment_point_y = rotated_plating.height // 2 + int(plating.weapon_mount_y * scale)

            # Calculate where weapon should be placed so its mount aligns with attachment point
            # weapon_offset tells us how to adjust so the mount point stays at target position
            weapon_paste_x = attachment_point_x - rotated_weapon.width // 2 + weapon_offset[0]
            weapon_paste_y = attachment_point_y - rotated_weapon.height // 2 + weapon_offset[1]

            # Determine canvas size needed to fit both
            min_x = min(0, weapon_paste_x)
            min_y = min(0, weapon_paste_y)
            max_x = max(rotated_plating.width, weapon_paste_x + rotated_weapon.width)
            max_y = max(rotated_plating.height, weapon_paste_y + rotated_weapon.height)

            canvas_width = max_x - min_x
            canvas_height = max_y - min_y

            # Create final canvas
            final = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

            # Adjust positions for canvas offset
            plating_paste_x = -min_x
            plating_paste_y = -min_y
            weapon_paste_x = weapon_paste_x - min_x
            weapon_paste_y = weapon_paste_y - min_y

            # Paste plating first, then weapon on top
            final.paste(rotated_plating, (plating_paste_x, plating_paste_y), rotated_plating)
            final.paste(rotated_weapon, (weapon_paste_x, weapon_paste_y), rotated_weapon)

            return final

    return rotated_plating


def render_bot_sprite_to_bytes(
    plating_name: str,
    registry: "PartsRegistry",
    weapon_name: t.Optional[str] = None,
    orientation: float = 0,
    weapon_orientation: t.Optional[float] = None,
    scale: float = 1.0,
    tint_color: t.Optional[tuple[int, int, int]] = None,
    tint_intensity: float = 0.4,
    output_size: t.Optional[tuple[int, int]] = None,
) -> bytes:
    """Render a bot sprite and return as WEBP bytes.

    This is a convenience wrapper around render_bot_sprite() that handles
    output sizing and WEBP encoding.

    Args:
        plating_name: Name of the plating to render (required)
        registry: PartsRegistry for pivot point lookups
        weapon_name: Name of weapon to attach (optional)
        orientation: Rotation angle of the bot in degrees
        weapon_orientation: Rotation angle of weapon turret
        scale: Scale multiplier for rendering
        tint_color: RGB tuple for team color tint
        tint_intensity: How strongly to apply tint
        output_size: If specified, resize final image to this (width, height)

    Returns:
        WEBP image bytes, or empty bytes if rendering failed.
    """
    img = render_bot_sprite(
        plating_name=plating_name,
        registry=registry,
        weapon_name=weapon_name,
        orientation=orientation,
        weapon_orientation=weapon_orientation,
        scale=scale,
        tint_color=tint_color,
        tint_intensity=tint_intensity,
    )

    if img is None:
        return b""

    # Resize to output size if specified
    if output_size:
        # Fit image into output size while maintaining aspect ratio, then center
        img.thumbnail(output_size, Image.Resampling.LANCZOS)

        # Create canvas of exact output size and paste centered
        canvas = Image.new("RGBA", output_size, (0, 0, 0, 0))
        paste_x = (output_size[0] - img.width) // 2
        paste_y = (output_size[1] - img.height) // 2
        canvas.paste(img, (paste_x, paste_y), img)
        img = canvas

    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=90)
    return buffer.getvalue()
