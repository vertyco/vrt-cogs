"""
Bot Arena - Bot Sprite Renderer

Single source of truth for rendering bot sprites with plating and weapon.
Used by both battle renderer (video frames) and garage preview (static images).

Note: Chassis images are not rendered because plating always covers them completely.
"""

import io
import math
import typing as t

from PIL import Image, ImageFilter, ImageOps

from .image_utils import load_image

if t.TYPE_CHECKING:
    from .models import Component, PartsRegistry, Plating


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


def scale_image(img: Image.Image, scale: float) -> Image.Image:
    """Resize a part image by a scale factor (the same image at 1.0)."""
    if scale == 1.0:
        return img
    return img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)


def barrel_length(weapon_name: str, mount_x: float) -> t.Optional[float]:
    """How far the barrel tip reaches in front of the weapon's mount point, in source image pixels.

    The tip is the frontmost solid column of the weapon image (weapons face right at 0 degrees).
    Returns None if the weapon has no image.
    """
    img = load_image("weapons", weapon_name)
    if img is None:
        return None
    bbox = img.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()
    if bbox is None:
        return None
    return bbox[2] - (img.width / 2 + mount_x)


def rotate_plating(img: Image.Image, plating: "Plating", orientation: float, scale: float) -> Image.Image:
    """Turn a scaled plating image around its pivot."""
    rotated, _ = _rotate_around_pivot(img, orientation, plating.center_x * scale, plating.center_y * scale)
    return rotated


def rotate_weapon(
    img: Image.Image, component: "Component", weapon_orientation: float, scale: float
) -> tuple[Image.Image, tuple[int, int]]:
    """Turn a scaled weapon image around its mount point.

    Also returns the offset that keeps the mount point in place when the turned image is positioned.
    """
    return _rotate_around_pivot(img, weapon_orientation, component.mount_x * scale, component.mount_y * scale)


def mount_offset(plating: "Plating", orientation: float, scale: float) -> tuple[int, int]:
    """Where the weapon mounts, measured from the plating's center once the plating has turned.

    The mount point is a spot on the plating, so it turns with the chassis.
    """
    rad = math.radians(orientation)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    mx, my = plating.weapon_mount_x * scale, plating.weapon_mount_y * scale
    return round(mx * cos_a - my * sin_a), round(mx * sin_a + my * cos_a)


def layer_positions(
    rotated_plating: Image.Image,
    plating: "Plating",
    rotated_weapon: Image.Image,
    weapon_offset: tuple[int, int],
    scale: float,
    orientation: float = 0.0,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Lay out the plating and weapon on one combined sprite.

    Returns (sprite size, plating position, weapon position), positions measured from the sprite's top-left.
    """
    # The weapon mounts on the plating's mount point, measured from the turned plating's center
    mount_x, mount_y = mount_offset(plating, orientation, scale)
    attachment_x = rotated_plating.width // 2 + mount_x
    attachment_y = rotated_plating.height // 2 + mount_y
    weapon_x = attachment_x - rotated_weapon.width // 2 + weapon_offset[0]
    weapon_y = attachment_y - rotated_weapon.height // 2 + weapon_offset[1]

    # The sprite grows to fit both layers
    min_x = min(0, weapon_x)
    min_y = min(0, weapon_y)
    max_x = max(rotated_plating.width, weapon_x + rotated_weapon.width)
    max_y = max(rotated_plating.height, weapon_y + rotated_weapon.height)
    return (max_x - min_x, max_y - min_y), (-min_x, -min_y), (weapon_x - min_x, weapon_y - min_y)


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

    plating = registry.get_plating(plating_name)
    rotated_plating = rotate_plating(scale_image(plating_img, scale), plating, orientation, scale)

    # Apply team tint if specified
    if tint_color:
        rotated_plating = _apply_tint(rotated_plating, tint_color, tint_intensity)

    weapon_img = load_image("weapons", weapon_name) if weapon_name else None
    if not weapon_img:
        return rotated_plating

    component = registry.get_component(weapon_name)
    rotated_weapon, weapon_offset = rotate_weapon(scale_image(weapon_img, scale), component, weapon_orientation, scale)
    size, plating_pos, weapon_pos = layer_positions(
        rotated_plating, plating, rotated_weapon, weapon_offset, scale, orientation
    )

    # Paste plating first, then weapon on top
    final = Image.new("RGBA", size, (0, 0, 0, 0))
    final.paste(rotated_plating, plating_pos, rotated_plating)
    final.paste(rotated_weapon, weapon_pos, rotated_weapon)
    return final


class SpriteCache:
    """Draws bots onto battle frames, reusing work across frames.

    Each part image is loaded and scaled once, and each turn angle is made once per whole
    degree (a fraction of a degree is invisible at battle sprite size). The plating is
    centered on the bot's position (where its hitbox is) and the weapon sits on the
    plating's mount point, exactly like render_bot_sprite() lays them out.
    """

    def __init__(self, registry: "PartsRegistry", scale: float):
        self.registry = registry
        self.scale = scale
        self.images: dict[tuple[str, str], t.Optional[Image.Image]] = {}
        self.platings: dict[tuple[str, int], t.Optional[Image.Image]] = {}
        self.weapons: dict[tuple[str, int], t.Optional[tuple[Image.Image, tuple[int, int]]]] = {}
        self.shadows: dict[int, tuple[Image.Image, int]] = {}
        self.flashes: dict[tuple[int, int], Image.Image] = {}

    def scaled_image(self, folder: str, name: str) -> t.Optional[Image.Image]:
        key = (folder, name)
        if key not in self.images:
            img = load_image(folder, name)
            self.images[key] = scale_image(img, self.scale) if img else None
        return self.images[key]

    def plating(self, name: str, orientation: float) -> t.Optional[Image.Image]:
        """The plating turned to the nearest whole degree, or None if it has no image."""
        key = (name, round(orientation) % 360)
        if key not in self.platings:
            img = self.scaled_image("plating", name)
            self.platings[key] = (
                rotate_plating(img, self.registry.get_plating(name), key[1], self.scale) if img else None
            )
        return self.platings[key]

    def weapon(self, name: str, orientation: float) -> t.Optional[tuple[Image.Image, tuple[int, int]]]:
        """The weapon turned to the nearest whole degree with its mount offset, or None if it has no image."""
        key = (name, round(orientation) % 360)
        if key not in self.weapons:
            img = self.scaled_image("weapons", name)
            component = self.registry.get_component(name)
            self.weapons[key] = rotate_weapon(img, component, key[1], self.scale) if img else None
        return self.weapons[key]

    def layers(
        self,
        x: int,
        y: int,
        plating_name: str,
        weapon_name: t.Optional[str],
        orientation: float,
        weapon_orientation: float,
    ) -> list[tuple[Image.Image, tuple[int, int]]]:
        """The bot's turned part images and their top-left frame positions, bottom layer first.

        Empty if the plating has no image.
        """
        rotated_plating = self.plating(plating_name, orientation)
        if rotated_plating is None:
            return []
        left = x - rotated_plating.width // 2
        top = y - rotated_plating.height // 2
        layers = [(rotated_plating, (left, top))]

        weapon = self.weapon(weapon_name, weapon_orientation) if weapon_name else None
        if weapon is not None:
            rotated_weapon, (offset_x, offset_y) = weapon
            mount_x, mount_y = mount_offset(self.registry.get_plating(plating_name), orientation, self.scale)
            # Center the turned weapon so its own mount point lands on the plating's mount point
            weapon_left = x + mount_x - rotated_weapon.width // 2 + offset_x
            weapon_top = y + mount_y - rotated_weapon.height // 2 + offset_y
            layers.append((rotated_weapon, (weapon_left, weapon_top)))
        return layers

    def draw(
        self,
        frame: Image.Image,
        x: int,
        y: int,
        plating_name: str,
        weapon_name: t.Optional[str],
        orientation: float,
        weapon_orientation: float,
    ) -> bool:
        """Paste a bot centered on (x, y). Returns False if the plating has no image."""
        layers = self.layers(x, y, plating_name, weapon_name, orientation, weapon_orientation)
        for image, position in layers:
            frame.paste(image, position, image)
        return bool(layers)

    def shadow(self, image: Image.Image, blur: int = 2) -> tuple[Image.Image, int]:
        """A soft drop shadow mask for a turned part image, and how far it spills past each edge."""
        key = id(image)
        if key not in self.shadows:
            pad = blur * 2
            mask = Image.new("L", (image.width + pad * 2, image.height + pad * 2), 0)
            mask.paste(image.getchannel("A"), (pad, pad))
            mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda a: a * 105 // 255)
            # Keyed by the part image itself, which the caches above keep alive for the whole battle
            self.shadows[key] = (mask, pad)
        return self.shadows[key]

    def flash(self, image: Image.Image, strength: float) -> Image.Image:
        """A white-out mask in the part's shape (hit flash), at one of a few strengths."""
        level = max(1, min(4, round(strength * 4)))
        key = (id(image), level)
        if key not in self.flashes:
            self.flashes[key] = image.getchannel("A").point(lambda a: a * level * 150 // (4 * 255))
        return self.flashes[key]

    def wreck(
        self,
        plating_name: str,
        weapon_name: t.Optional[str],
        orientation: float,
        weapon_orientation: float,
    ) -> t.Optional[tuple[Image.Image, tuple[int, int]]]:
        """A burnt-out copy of the bot as one image, and where its top-left sits relative to the bot's center."""
        layers = self.layers(0, 0, plating_name, weapon_name, orientation, weapon_orientation)
        if not layers:
            return None
        left = min(pos[0] for _, pos in layers)
        top = min(pos[1] for _, pos in layers)
        right = max(pos[0] + img.width for img, pos in layers)
        bottom = max(pos[1] + img.height for img, pos in layers)
        combined = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        for img, pos in layers:
            combined.alpha_composite(img, (pos[0] - left, pos[1] - top))
        # Scorched metal: drop the paint, keep the shading, darken toward soot
        charred = ImageOps.colorize(ImageOps.grayscale(combined), black=(14, 12, 11), white=(118, 104, 92))
        charred.putalpha(combined.getchannel("A"))
        return charred, (left, top)


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
