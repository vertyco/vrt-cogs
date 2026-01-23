"""
Bot Arena - Pixel-Perfect Collision Detection

This module provides collision detection based on actual bot plating images rather
than simple circular hitboxes. Projectiles only register hits when they touch
non-transparent pixels of the target bot's plating.

Note: Weapons are NOT included in collision detection because they rotate
independently from the chassis (weapon_orientation vs bot orientation).
"""

import typing as t
from functools import lru_cache

import numpy as np
from PIL import Image

from .image_utils import load_image


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

        # Load plating-only mask
        self._base_mask: t.Optional[np.ndarray] = None
        self._base_size: tuple[int, int] = (0, 0)
        self._load_mask()

        # Cache of rotated masks (angle -> mask array)
        # We quantize angles to 5-degree increments for performance
        self._rotated_cache: dict[int, np.ndarray] = {}

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

        try:
            # Extract alpha channel as numpy array
            alpha = np.array(plating_img.split()[-1])

            # Create binary mask: 1 where alpha > threshold (128), 0 elsewhere
            self._base_mask = (alpha > 128).astype(np.uint8)
            self._base_size = plating_img.size

        except (OSError, ValueError, IndexError):
            # OSError: image file issues
            # ValueError: invalid image mode
            # IndexError: image has no alpha channel
            self._base_mask = None

    def _quantize_angle(self, angle: float) -> int:
        """Quantize angle to nearest 5 degrees for caching."""
        return int(round(angle / 5) * 5) % 360

    def _get_rotated_mask(self, angle: float) -> t.Optional[np.ndarray]:
        """Get the collision mask rotated to the given angle (degrees)."""
        if self._base_mask is None:
            return None

        quantized = self._quantize_angle(angle)

        if quantized in self._rotated_cache:
            return self._rotated_cache[quantized]

        # Rotate the mask using PIL (it handles the expansion properly)
        mask_img = Image.fromarray(self._base_mask * 255, mode="L")
        rotated_img = mask_img.rotate(-angle, expand=True, resample=Image.Resampling.NEAREST)
        rotated_mask = (np.array(rotated_img) > 128).astype(np.uint8)

        self._rotated_cache[quantized] = rotated_mask
        return rotated_mask

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
        if self._base_mask is None:
            return False

        # Get the rotated mask
        rotated_mask = self._get_rotated_mask(bot_angle)
        if rotated_mask is None:
            return False

        mask_h, mask_w = rotated_mask.shape
        mask_cx, mask_cy = mask_w / 2, mask_h / 2

        # Convert world coordinates to mask coordinates
        # The mask center should be at (bot_x, bot_y) in world space
        dx = (point_x - bot_x) / scale
        dy = (point_y - bot_y) / scale

        # Convert to mask pixel coordinates (center of mask is at mask_cx, mask_cy)
        px = int(mask_cx + dx)
        py = int(mask_cy + dy)

        # Bounds check
        if px < 0 or px >= mask_w or py < 0 or py >= mask_h:
            return False

        # Check if the pixel is solid
        return rotated_mask[py, px] > 0


class CollisionManager:
    """
    Manages collision masks for all bots in a battle.

    Provides an efficient way to check projectile-bot collisions using
    pixel-perfect collision detection.
    """

    def __init__(self):
        self._masks: dict[str, CollisionMask] = {}
        # Scale factor from source image pixels to arena coordinates
        # Chassis images are 64x64, and they should occupy ~64 pixels in the 1000x1000 arena
        self._scale: float = 1.0

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


# Module-level cache for collision masks (shared across battles)
@lru_cache(maxsize=64)
def get_collision_mask(plating_name: str, weapon_name: t.Optional[str] = None) -> CollisionMask:
    """Get a cached collision mask for the given plating.

    Note: weapon_name is kept for API compatibility but not used for collision.
    """
    return CollisionMask(plating_name, weapon_name)
