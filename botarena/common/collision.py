"""
Bot Arena - Pixel-Perfect Collision Detection

This module provides collision detection based on actual bot plating images rather
than simple circular hitboxes. Projectiles only register hits when they touch
non-transparent pixels of the target bot's plating.

Masks are plain Pillow images read back as bytes, so hitboxes are identical on every
install (no optional numpy dependency deciding between pixel masks and circles).

Note: Weapons are NOT included in collision detection because they rotate
independently from the chassis (weapon_orientation vs bot orientation).
"""

import math
import typing as t

from PIL import Image

from .image_utils import SPRITE_SCALE, load_image

# Rotated masks are cached per this many degrees (a few source pixels at most at the plating's edge)
ANGLE_STEP = 5


class CollisionMask:
    """
    A collision mask for a bot, based on the plating image only.

    The mask stores which pixels are "solid" (non-transparent) and can be
    queried at any rotation angle. We use plating-only because:
    1. Weapons rotate independently from the chassis (different orientation)
    2. Weapons are mounted at an offset, not centered
    3. User expectation: hitbox = plating shape
    """

    def __init__(self, plating_name: str, weapon_name: t.Optional[str] = None):
        """
        Create a collision mask for a bot with the given plating.

        Args:
            plating_name: Name of the plating (e.g., "Zintek")
            weapon_name: Ignored (kept for API compatibility)
        """
        self.plating_name = plating_name
        self.weapon_name = weapon_name  # Stored but not used for collision

        # Solid pixels are 255, everything else 0
        self._base_mask: t.Optional[Image.Image] = None
        # Farthest solid pixel from the image center, in source pixels (for cheap broad-phase rejects)
        self.radius: float = 0.0
        # Typical distance from the center to the hull's edge, in source pixels (how close bots can touch)
        self.hull_radius: float = 0.0
        self._load_mask()

        # Cache of rotated masks: quantized angle -> (pixel bytes, width, height)
        self._rotated_cache: dict[int, tuple[bytes, int, int]] = {}

    def _load_mask(self):
        """Load the plating image and create a collision mask.

        Note: Weapon is NOT included in the collision mask because:
        - Weapon rotates independently (weapon_orientation vs chassis orientation)
        - Weapon is positioned at a mount point offset, not centered
        - This would require passing weapon_orientation to each collision check

        The plating-only mask correctly represents the bot's "body" hitbox.
        """
        plating_img = load_image("plating", self.plating_name)
        if not plating_img:
            return

        mask = plating_img.getchannel("A").point(lambda a: 255 if a > 128 else 0)
        bbox = mask.getbbox()
        if bbox is None:
            return
        self._base_mask = mask
        cx, cy = mask.width / 2, mask.height / 2
        self.radius = max(math.hypot(x - cx, y - cy) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3]))

        # Walk out from the center in every direction and average where the hull ends
        data, width, height = mask.tobytes(), mask.width, mask.height
        reaches = []
        for step in range(36):
            heading = math.radians(step * 10)
            reach = 0
            for dist in range(1, int(self.radius) + 1):
                x, y = int(cx + math.cos(heading) * dist), int(cy + math.sin(heading) * dist)
                if 0 <= x < width and 0 <= y < height and data[y * width + x]:
                    reach = dist
            reaches.append(reach)
        self.hull_radius = sum(reaches) / len(reaches)

    def _get_rotated_mask(self, angle: float) -> t.Optional[tuple[bytes, int, int]]:
        """Get the collision mask rotated to the given angle (degrees), quantized for caching."""
        if self._base_mask is None:
            return None

        quantized = int(round(angle / ANGLE_STEP) * ANGLE_STEP) % 360
        cached = self._rotated_cache.get(quantized)
        if cached is None:
            rotated = self._base_mask.rotate(-quantized, expand=True, resample=Image.Resampling.NEAREST)
            cached = (rotated.tobytes(), rotated.width, rotated.height)
            self._rotated_cache[quantized] = cached
        return cached

    def check_point_collision(
        self,
        point_x: float,
        point_y: float,
        bot_x: float,
        bot_y: float,
        bot_angle: float,
        scale: float = 1.0,
    ) -> bool:
        """
        Check if a point (e.g., projectile position) collides with the bot.

        Args:
            point_x: World X coordinate of the point
            point_y: World Y coordinate of the point
            bot_x: World X coordinate of the bot's center
            bot_y: World Y coordinate of the bot's center
            bot_angle: Bot's rotation angle in degrees
            scale: Scale factor from source pixels to world coordinates

        Returns:
            True if the point is inside a non-transparent pixel of the bot
        """
        rotated = self._get_rotated_mask(bot_angle)
        if rotated is None:
            return False
        data, mask_w, mask_h = rotated

        # The mask center sits on (bot_x, bot_y) in world space
        px = int(mask_w / 2 + (point_x - bot_x) / scale)
        py = int(mask_h / 2 + (point_y - bot_y) / scale)

        if px < 0 or px >= mask_w or py < 0 or py >= mask_h:
            return False
        return data[py * mask_w + px] > 0


class CollisionManager:
    """
    Manages collision masks for all bots in a battle.

    Provides an efficient way to check projectile-bot collisions using
    pixel-perfect collision detection.
    """

    def __init__(self):
        self._masks: dict[str, CollisionMask] = {}
        # Scale factor from source image pixels to arena coordinates.
        # The renderer draws battle sprites at SPRITE_SCALE (1.3x) for visibility,
        # so the collision mask must use the same factor to match the visuals.
        self._scale: float = SPRITE_SCALE

    def register_bot(
        self,
        bot_id: str,
        plating_name: str,
        weapon_name: t.Optional[str] = None,
    ):
        """
        Register a bot's collision mask.

        Args:
            bot_id: Unique identifier for the bot
            plating_name: Name of the bot's plating
            weapon_name: Name of the bot's weapon (optional)
        """
        self._masks[bot_id] = CollisionMask(plating_name, weapon_name)

    def bounding_radius(self, bot_id: str) -> t.Optional[float]:
        """How far the bot's hull reaches from its center in arena units, or None without a mask."""
        mask = self._masks.get(bot_id)
        if mask is None or mask._base_mask is None:
            return None
        return mask.radius * self._scale

    def hull_radius(self, bot_id: str) -> t.Optional[float]:
        """Typical distance from the bot's center to the edge of its hull in arena units, or None without a mask."""
        mask = self._masks.get(bot_id)
        if mask is None or mask._base_mask is None:
            return None
        return mask.hull_radius * self._scale

    def check_collision(
        self,
        proj_x: float,
        proj_y: float,
        bot_id: str,
        bot_x: float,
        bot_y: float,
        bot_angle: float,
    ) -> t.Optional[bool]:
        """
        Check if a projectile at (proj_x, proj_y) collides with the given bot.

        Args:
            proj_x: Projectile X position in arena coordinates
            proj_y: Projectile Y position in arena coordinates
            bot_id: ID of the bot to check against
            bot_x: Bot's X position in arena coordinates
            bot_y: Bot's Y position in arena coordinates
            bot_angle: Bot's rotation angle in degrees

        Returns:
            True if the projectile collides with a non-transparent pixel of the bot
            False if the projectile does not collide
            None if no collision mask is available (caller should use fallback collision)
        """
        mask = self._masks.get(bot_id)
        if mask is None or mask._base_mask is None:
            return None  # Signal caller to use fallback collision

        return mask.check_point_collision(proj_x, proj_y, bot_x, bot_y, bot_angle, self._scale)

    def clear(self):
        """Clear all registered collision masks."""
        self._masks.clear()
