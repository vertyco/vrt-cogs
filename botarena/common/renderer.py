"""
Bot Arena - Battle Renderer

Renders battle frames to images and compiles them into a video file.
Uses Pillow for drawing and ffmpeg for video encoding.
"""

import logging
import math
import sys
import tempfile
import typing as t
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .bot_sprite import render_bot_sprite

if t.TYPE_CHECKING:
    from .models import PartsRegistry

log = logging.getLogger("red.vrt.botarena.renderer")

# Colors
ARENA_BG = (30, 30, 35)
GRID_COLOR = (45, 45, 50)
DEFAULT_TEAM1_COLOR = (66, 135, 245)  # Blue
DEFAULT_TEAM2_COLOR = (245, 66, 66)  # Red
TEAM1_HEALTH = (100, 200, 100)  # Green
TEAM2_HEALTH = (100, 200, 100)
PROJECTILE_COLOR = (255, 255, 100)  # Yellow (default fallback)
HEAL_COLOR = (100, 255, 100)  # Green
TEXT_COLOR = (220, 220, 220)
DEAD_COLOR = (80, 80, 80)

# Projectile style definitions for different weapon types
# These are designed to match the visual feel of Bot Arena 3 weapons
PROJECTILE_STYLES = {
    # LASER - Thin, bright beams (Zintek, Devenge, Cerebus)
    # Fast energy weapons with high accuracy
    "laser": {
        "color": (255, 60, 40),  # Bright red-orange core
        "radius": 2,
        "length": 30,  # Longer for that "pew pew" feel
        "is_beam": True,
        "glow_color": (255, 180, 100),  # Warm glow
        "glow_radius": 4,
    },
    # CANNON - Large, heavy projectiles (Porantis)
    # Slow-moving but powerful impact rounds
    "cannon": {
        "color": (80, 160, 255),  # Bright blue plasma core
        "radius": 8,  # Bigger, chunkier projectiles
        "is_beam": False,
        "outline_color": (200, 230, 255),  # Light blue outline
        "has_glow": True,
        "glow_color": (100, 180, 255),
    },
    # MISSILE - Elongated with trails (Circes, Scream Shard)
    # Plasma/energy missiles with visible exhaust
    "missile": {
        "color": (255, 120, 0),  # Orange plasma core
        "radius": 5,
        "length": 14,  # Elongated shape
        "is_beam": False,
        "has_trail": True,
        "trail_color": (255, 200, 50),  # Yellow-orange exhaust
        "trail_length": 3,
    },
    # BULLET - Standard rapid-fire rounds (Kedron, Raptor, Torrika, Darsik, etc.)
    # Most common projectile type - quick and numerous
    "bullet": {
        "color": (255, 240, 180),  # Warm white/yellow tracer
        "radius": 3,
        "is_beam": False,
        "outline_color": (255, 200, 100),  # Slight orange tint
    },
    # HEAL - Restorative energy beam (Zeni PRS, Zeni PRZ-2)
    # Distinct green healing pulses
    "heal": {
        "color": (50, 255, 120),  # Bright green core
        "radius": 5,
        "length": 18,
        "is_beam": True,
        "glow_color": (100, 255, 180),  # Cyan-green glow
        "glow_radius": 6,
    },
    # SHOCKWAVE - Close-range hydraulic burst (Torrika KJ-557)
    # Short-range expanding ring effect
    "shockwave": {
        "color": (255, 200, 100),  # Orange-yellow core
        "radius": 12,  # Large initial radius
        "is_beam": False,
        "is_shockwave": True,  # Special rendering flag
        "ring_color": (255, 160, 60),  # Orange ring
        "ring_width": 3,
        "glow_color": (255, 120, 40),  # Orange glow
    },
}

# Team color options (same as models.py TEAM_COLORS)
TEAM_COLORS = {
    "blue": (0, 120, 255),  # Bright blue
    "red": (255, 60, 60),  # Bright red
    "green": (60, 200, 60),  # Bright green
    "yellow": (255, 220, 0),  # Yellow
    "purple": (180, 60, 255),  # Purple
    "orange": (255, 140, 0),  # Orange
    "cyan": (0, 220, 220),  # Cyan
    "pink": (255, 105, 180),  # Pink
}

# Path to data directory with part images
DATA_DIR = Path(__file__).parent.parent / "data"


class BattleRenderer:
    """Renders battle frames to video"""

    def __init__(
        self,
        width: int = 1000,
        height: int = 1000,
        scale: float = 0.5,
        fps: int = 30,
        team1_color: str = "blue",
        team2_color: str = "red",
        parts_registry: t.Optional["PartsRegistry"] = None,
        chapter: t.Optional[int] = None,
    ):
        """
        Initialize the renderer.

        Args:
            width: Arena width in pixels
            height: Arena height in pixels
            scale: Scale factor for output (0.5 = 500x500 output)
            fps: Frames per second
            team1_color: Color name for team 1 (player's team)
            team2_color: Color name for team 2 (enemy team)
            parts_registry: Optional registry for looking up component render offsets
            chapter: Campaign chapter number (1-5) for chapter-specific arena backgrounds
        """
        self.arena_width = width
        self.arena_height = height
        self.scale = scale
        self.output_width = int(width * scale)
        self.output_height = int(height * scale)
        self.fps = fps
        self.parts_registry = parts_registry
        self.chapter = chapter

        # Set team colors from color names
        self.team1_color = TEAM_COLORS.get(team1_color, DEFAULT_TEAM1_COLOR)
        self.team2_color = TEAM_COLORS.get(team2_color, DEFAULT_TEAM2_COLOR)

        # Load arena background if available
        self._arena_background: t.Optional[Image.Image] = None
        self._load_arena_background()

        # Try to load a font, fall back to default
        # Font sizes scaled for visibility - larger for better readability
        main_font_size = int(32 * scale)  # Bot names
        small_font_size = int(24 * scale)  # Health/stats
        self.font = None
        self.small_font = None
        try:
            self.font = ImageFont.truetype("arial.ttf", main_font_size)
            self.small_font = ImageFont.truetype("arial.ttf", small_font_size)
        except OSError:
            try:
                self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", main_font_size)
                self.small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", small_font_size)
            except OSError:
                self.font = ImageFont.load_default()
                self.small_font = ImageFont.load_default()

    def _load_arena_background(self):
        """Load and scale the arena background image if available.

        If a chapter is specified, tries to load chapter-specific arena first,
        then falls back to legacy arena_background.
        """
        # Build list of filenames to try (chapter-specific first, then fallback)
        filenames_to_try = []
        if self.chapter:
            filenames_to_try.append(f"arena_chapter_{self.chapter}")
        filenames_to_try.append("arena_background")  # Legacy fallback

        # Try each filename with webp first, then png
        for filename in filenames_to_try:
            for ext in ("webp", "png"):
                path = DATA_DIR / f"{filename}.{ext}"
                if path.exists():
                    try:
                        img = Image.open(path).convert("RGB")
                        # Scale to output size
                        img = img.resize((self.output_width, self.output_height), Image.Resampling.LANCZOS)
                        self._arena_background = img
                        return
                    except Exception as e:
                        log.warning("Failed to load arena background from %s", path, exc_info=e)
                        continue  # Try next file

    def _scale_pos(self, x: float, y: float) -> tuple[int, int]:
        """Scale position from arena coords to output coords"""
        return int(x * self.scale), int(y * self.scale)

    def _scale_size(self, size: float) -> int:
        """Scale a size value"""
        return max(1, int(size * self.scale))

    def render_frame(self, frame_data: dict, battle_info: dict) -> Image.Image:
        """
        Render a single frame.

        Args:
            frame_data: Frame data dict with bots, projectiles, events
            battle_info: Battle metadata (arena size, teams, etc.)

        Returns:
            PIL Image of the rendered frame
        """
        # Use arena background if available, otherwise solid color
        if self._arena_background:
            img = self._arena_background.copy().convert("RGBA")
        else:
            img = Image.new("RGBA", (self.output_width, self.output_height), ARENA_BG)
        draw = ImageDraw.Draw(img)

        # Draw grid (only if no background image, or make it subtle overlay)
        if not self._arena_background:
            self._draw_grid(draw)

        # Draw bots - dead bots first (underneath), then alive bots on top
        bots = frame_data.get("bots", [])
        dead_bots = [b for b in bots if not b.get("is_alive", True)]
        alive_bots = [b for b in bots if b.get("is_alive", True)]

        for bot_data in dead_bots:
            self._draw_bot(img, draw, bot_data)
        for bot_data in alive_bots:
            self._draw_bot(img, draw, bot_data)

        # Draw projectiles
        for proj_data in frame_data.get("projectiles", []):
            self._draw_projectile(draw, proj_data)

        # Draw HUD
        self._draw_hud(draw, frame_data, battle_info)

        return img.convert("RGB")

    def _draw_grid(self, draw: ImageDraw.ImageDraw):
        """Draw arena grid lines"""
        grid_spacing = 100
        for x in range(0, self.arena_width + 1, grid_spacing):
            sx = int(x * self.scale)
            draw.line([(sx, 0), (sx, self.output_height)], fill=GRID_COLOR, width=1)
        for y in range(0, self.arena_height + 1, grid_spacing):
            sy = int(y * self.scale)
            draw.line([(0, sy), (self.output_width, sy)], fill=GRID_COLOR, width=1)

    def _draw_bot(self, img: Image.Image, draw: ImageDraw.ImageDraw, bot_data: dict):
        """Draw a single bot with separate body facing and weapon turret.

        Uses render_bot_sprite() for consistent rendering between battle and garage.
        """
        x, y = self._scale_pos(bot_data["x"], bot_data["y"])
        team = bot_data.get("team", 1)
        is_alive = bot_data.get("is_alive", True)

        plating_name = bot_data.get("plating", "") or None
        weapon_name = bot_data.get("component", "") or None

        # Get orientations
        orientation = bot_data.get("orientation", 0)
        weapon_orientation = bot_data.get("weapon_orientation", orientation)

        radius = self._scale_size(32)

        if is_alive and plating_name:
            # Use the unified bot sprite renderer (no tint - team color shown via name text)
            # Scale factor: base image scale * 1.3 for visibility
            sprite_scale = self.scale * 1.3

            bot_sprite = render_bot_sprite(
                plating_name=plating_name,
                weapon_name=weapon_name,
                orientation=orientation,
                weapon_orientation=weapon_orientation,
                scale=sprite_scale,
                registry=self.parts_registry,
            )

            if not bot_sprite:
                raise RuntimeError(f"Failed to render bot sprite for plating '{plating_name}', weapon '{weapon_name}'")

            # Paste sprite centered on position
            paste_x = x - bot_sprite.width // 2
            paste_y = y - bot_sprite.height // 2
            img.paste(bot_sprite, (paste_x, paste_y), bot_sprite)
        else:
            # Dead or no plating - draw simple shape (this is intentional, not a fallback)
            color = DEAD_COLOR if not is_alive else (self.team1_color if team == 1 else self.team2_color)
            self._draw_bot_shape_with_turret(draw, x, y, radius, orientation, weapon_orientation, color, is_alive)

        if is_alive:
            # Health bar
            health = bot_data.get("health", 0)
            max_health = bot_data.get("max_health", 100)
            health_ratio = health / max_health if max_health > 0 else 0

            bar_width = self._scale_size(50)
            bar_height = self._scale_size(8)
            bar_x = x - bar_width // 2
            bar_y = y - radius - self._scale_size(18)

            # Background
            draw.rectangle(
                [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
                fill=(60, 60, 60),
                outline=(100, 100, 100),
            )

            # Health fill
            health_width = int(bar_width * health_ratio)
            if health_width > 0:
                health_color = TEAM1_HEALTH if team == 1 else TEAM2_HEALTH
                if health_ratio < 0.3:
                    health_color = (200, 50, 50)
                elif health_ratio < 0.6:
                    health_color = (200, 200, 50)
                draw.rectangle(
                    [(bar_x, bar_y), (bar_x + health_width, bar_y + bar_height)],
                    fill=health_color,
                )

        # Bot name (colored by team)
        name = bot_data.get("name", "Bot")[:8]
        text_bbox = draw.textbbox((0, 0), name, font=self.small_font)
        text_width = text_bbox[2] - text_bbox[0]
        if is_alive:
            name_color = self.team1_color if team == 1 else self.team2_color
        else:
            name_color = DEAD_COLOR
        draw.text(
            (x - text_width // 2, y + radius + self._scale_size(8)),
            name,
            fill=name_color,
            font=self.small_font,
        )

    def _draw_bot_shape_with_turret(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        radius: int,
        orientation: float,
        weapon_orientation: float,
        color: tuple,
        is_alive: bool,
    ):
        """Draw a simple shape for dead bots or bots without plating."""
        self._draw_bot_shape(draw, x, y, radius, orientation, color, is_alive)

        if is_alive:
            # Draw weapon turret line
            weapon_rad = math.radians(weapon_orientation)
            turret_length = self._scale_size(35)
            tx = x + int(math.cos(weapon_rad) * turret_length)
            ty = y + int(math.sin(weapon_rad) * turret_length)
            draw.line([(x, y), (tx, ty)], fill=(255, 200, 100), width=self._scale_size(5))

    def _draw_bot_shape(
        self, draw: ImageDraw.ImageDraw, x: int, y: int, radius: int, orientation: float, color: tuple, is_alive: bool
    ):
        """Draw a bot as a directional polygon"""
        # Create points for a pointed shape (like an arrow)
        # Base shape points at 0 degrees (pointing right)
        points = [
            (radius, 0),  # Front point
            (radius * 0.3, -radius * 0.7),  # Top front
            (-radius * 0.8, -radius * 0.5),  # Top back
            (-radius, 0),  # Back center
            (-radius * 0.8, radius * 0.5),  # Bottom back
            (radius * 0.3, radius * 0.7),  # Bottom front
        ]

        # Rotate points
        rad = math.radians(orientation)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = []
        for px, py in points:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            rotated.append((x + rx, y + ry))

        # Draw bot
        draw.polygon(rotated, fill=color, outline=(255, 255, 255) if is_alive else DEAD_COLOR)

    def _draw_projectile(self, draw: ImageDraw.ImageDraw, proj_data: dict):
        """Draw a projectile with style based on weapon type, oriented along velocity vector"""
        x, y = self._scale_pos(proj_data["x"], proj_data["y"])
        vx = proj_data.get("vx", 1)  # Default to moving right if no velocity
        vy = proj_data.get("vy", 0)
        is_heal = proj_data.get("is_heal", False)
        projectile_type = proj_data.get("projectile_type", "heal" if is_heal else "bullet")

        # Calculate rotation angle from velocity vector (in radians)
        # atan2 gives angle from positive x-axis
        angle_rad = math.atan2(vy, vx)
        angle_deg = math.degrees(angle_rad)

        # Get style for this projectile type
        style = PROJECTILE_STYLES.get(projectile_type, PROJECTILE_STYLES["bullet"])

        # Override to heal style if is_heal flag is set
        if is_heal and projectile_type != "heal":
            style = PROJECTILE_STYLES["heal"]

        color = style["color"]
        radius = self._scale_size(style["radius"])
        is_beam = style.get("is_beam", False)
        has_trail = style.get("has_trail", False)
        has_glow = style.get("has_glow", False)
        is_shockwave = style.get("is_shockwave", False)

        if is_shockwave:
            # Draw shockwave as expanding ring burst effect
            # The shockwave "expands" based on distance traveled from shooter
            ring_color = style.get("ring_color", (255, 160, 60))
            ring_width = self._scale_size(style.get("ring_width", 3))
            glow_color = style.get("glow_color", (255, 120, 40))

            # Draw outer glow ring
            outer_radius = radius + self._scale_size(4)
            draw.ellipse(
                [(x - outer_radius, y - outer_radius), (x + outer_radius, y + outer_radius)],
                outline=glow_color,
                width=max(1, int(ring_width * 1.5)),
            )

            # Draw main shockwave ring
            draw.ellipse(
                [(x - radius, y - radius), (x + radius, y + radius)],
                outline=ring_color,
                width=max(1, int(ring_width)),
            )

            # Draw inner bright core
            core_radius = max(2, radius // 3)
            draw.ellipse(
                [(x - core_radius, y - core_radius), (x + core_radius, y + core_radius)],
                fill=color,
            )

        elif is_beam:
            # Draw as a beam/line - rotated along velocity
            beam_length = self._scale_size(style.get("length", 20))
            self._draw_oriented_ellipse(draw, x, y, beam_length, radius * 2, angle_deg, color, style.get("glow_color"))

        elif has_trail:
            # Draw missile with trail effect - rotated along velocity
            trail_color = style.get("trail_color", (255, 200, 100))
            trail_length = style.get("trail_length", 3)
            proj_length = self._scale_size(style.get("length", 10))

            # Draw trail (fading circles behind) - opposite direction of velocity
            trail_dx = -math.cos(angle_rad)
            trail_dy = -math.sin(angle_rad)
            for i in range(trail_length):
                trail_offset = (i + 1) * (proj_length // 3)
                trail_x = x + trail_dx * trail_offset
                trail_y = y + trail_dy * trail_offset
                trail_radius = max(1, radius - i)
                # Fade trail color progressively
                fade = 1.0 - (i * 0.25)
                faded_color = tuple(int(c * fade) for c in trail_color)
                draw.ellipse(
                    [
                        (trail_x - trail_radius, trail_y - trail_radius),
                        (trail_x + trail_radius, trail_y + trail_radius),
                    ],
                    fill=faded_color,
                )

            # Draw missile body (elongated ellipse oriented along velocity)
            self._draw_oriented_ellipse(draw, x, y, radius * 3, radius * 2, angle_deg, color, None)

        else:
            # Standard round projectile - these stay circular (no rotation needed)
            # Draw glow effect for cannons
            if has_glow and "glow_color" in style:
                glow_radius = radius + self._scale_size(3)
                draw.ellipse(
                    [(x - glow_radius, y - glow_radius), (x + glow_radius, y + glow_radius)],
                    fill=style["glow_color"],
                )

            # Draw outline if specified
            if "outline_color" in style:
                outline_radius = radius + 1
                draw.ellipse(
                    [(x - outline_radius, y - outline_radius), (x + outline_radius, y + outline_radius)],
                    fill=style["outline_color"],
                )

            draw.ellipse(
                [(x - radius, y - radius), (x + radius, y + radius)],
                fill=color,
            )

    def _draw_oriented_ellipse(
        self,
        draw: ImageDraw.ImageDraw,
        cx: float,
        cy: float,
        width: float,
        height: float,
        angle_deg: float,
        color,
        glow_color=None,
    ):
        """Draw an ellipse rotated by angle_deg degrees.

        Uses polygon approximation since PIL doesn't support rotated ellipses directly.
        """
        # Number of points to approximate the ellipse
        num_points = 24

        # Generate ellipse points rotated by angle
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Draw glow first (larger ellipse)
        if glow_color:
            glow_points = []
            glow_width = width + 4
            glow_height = height + 4
            for i in range(num_points):
                theta = 2 * math.pi * i / num_points
                # Point on unrotated ellipse
                ex = (glow_width / 2) * math.cos(theta)
                ey = (glow_height / 2) * math.sin(theta)
                # Rotate point
                rx = ex * cos_a - ey * sin_a
                ry = ex * sin_a + ey * cos_a
                glow_points.append((cx + rx, cy + ry))
            draw.polygon(glow_points, fill=glow_color)

        # Draw main ellipse
        points = []
        for i in range(num_points):
            theta = 2 * math.pi * i / num_points
            # Point on unrotated ellipse
            ex = (width / 2) * math.cos(theta)
            ey = (height / 2) * math.sin(theta)
            # Rotate point
            rx = ex * cos_a - ey * sin_a
            ry = ex * sin_a + ey * cos_a
            points.append((cx + rx, cy + ry))

        draw.polygon(points, fill=color)

    def _draw_hud(self, draw: ImageDraw.ImageDraw, frame_data: dict, battle_info: dict):
        """Draw heads-up display with team info"""
        # Time display
        time_str = f"Time: {frame_data.get('time', 0):.1f}s"
        draw.text((10, 10), time_str, fill=TEXT_COLOR, font=self.font)

        # Team scores/counts
        bots = frame_data.get("bots", [])
        team1_alive = sum(1 for b in bots if b.get("team") == 1 and b.get("is_alive"))
        team2_alive = sum(1 for b in bots if b.get("team") == 2 and b.get("is_alive"))
        team1_total = sum(1 for b in bots if b.get("team") == 1)
        team2_total = sum(1 for b in bots if b.get("team") == 2)

        # Player (left side)
        team1_text = f"Player: {team1_alive}/{team1_total}"
        draw.text((10, self.output_height - 30), team1_text, fill=self.team1_color, font=self.font)

        # Opponent (right side)
        team2_text = f"Opponent: {team2_alive}/{team2_total}"
        text_bbox = draw.textbbox((0, 0), team2_text, font=self.font)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text(
            (self.output_width - text_width - 10, self.output_height - 30),
            team2_text,
            fill=self.team2_color,
            font=self.font,
        )

    def render_to_video(
        self,
        battle_result: dict,
        output_path: t.Union[str, Path],
        show_progress: bool = False,
        freeze_duration: float = 3.0,
    ) -> Path:
        """
        Render all frames to a video file.

        Uses PyAV directly for H.264 encoding (Discord compatible).
        Falls back to ffmpeg subprocess, then GIF if neither available.

        Args:
            battle_result: Complete battle result dict with frames
            output_path: Path to save the video
            show_progress: Print progress updates
            freeze_duration: Duration in seconds to freeze on the final frame (default 3s)

        Returns:
            Path to the created video file
        """
        output_path = Path(output_path)
        frames = battle_result.get("frames", [])

        if not frames:
            raise ValueError("No frames to render")

        battle_info = {
            "arena_width": battle_result.get("arena_width", self.arena_width),
            "arena_height": battle_result.get("arena_height", self.arena_height),
        }

        # Render all frames to PIL Images
        rendered_frames = []
        for i, frame in enumerate(frames):
            if show_progress and i % 30 == 0:
                print(f"Rendering frame {i}/{len(frames)}", file=sys.stderr)

            img = self.render_frame(frame, battle_info)
            rendered_frames.append(img)

        # Add freeze frames at the end to show final state
        if rendered_frames and freeze_duration > 0:
            freeze_frame_count = int(freeze_duration * self.fps)
            last_frame = rendered_frames[-1]
            if show_progress:
                print(f"Adding {freeze_frame_count} freeze frames ({freeze_duration}s)...", file=sys.stderr)
            rendered_frames.extend([last_frame] * freeze_frame_count)

        if show_progress:
            print(f"Writing video with {len(rendered_frames)} frames...", file=sys.stderr)

        # Try PyAV directly first (best Discord compatibility)
        try:
            self._write_video_pyav(rendered_frames, output_path)
            return output_path
        except Exception as e:
            if show_progress:
                print(f"PyAV failed: {e}, trying ffmpeg subprocess...", file=sys.stderr)

        # Try ffmpeg subprocess
        try:
            self._write_video_ffmpeg(rendered_frames, output_path)
            return output_path
        except Exception as e:
            if show_progress:
                print(f"ffmpeg failed: {e}, falling back to GIF...", file=sys.stderr)

        # Final fallback: convert to GIF
        gif_path = output_path.with_suffix(".gif")
        self.render_to_gif(battle_result, gif_path, frame_skip=2, show_progress=show_progress)
        return gif_path

    def _write_video_pyav(self, frames: list[Image.Image], output_path: Path):
        """Write video using PyAV directly with Discord-compatible settings."""
        import av

        container = av.open(str(output_path), mode="w")
        stream = container.add_stream("libx264", rate=self.fps)
        stream.width = frames[0].width
        stream.height = frames[0].height
        stream.pix_fmt = "yuv420p"  # Required for Discord
        # H.264 encoding options for maximum compatibility
        stream.options = {
            "profile": "baseline",
            "level": "3.0",
            "movflags": "+faststart",
            "crf": "23",  # Quality (lower = better, 23 is default)
        }

        for img in frames:
            # Convert PIL Image to av.VideoFrame
            frame = av.VideoFrame.from_image(img)
            frame = frame.reformat(format="yuv420p")
            for packet in stream.encode(frame):
                container.mux(packet)

        # Flush encoder
        for packet in stream.encode():
            container.mux(packet)

        container.close()

    def _write_video_ffmpeg(self, frames: list[Image.Image], output_path: Path):
        """Write video using ffmpeg subprocess with Discord-compatible settings."""
        import shutil
        import subprocess

        # Check if ffmpeg is available - try imageio-ffmpeg first, then system ffmpeg
        ffmpeg_path = None
        try:
            import imageio_ffmpeg

            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

        if not ffmpeg_path:
            ffmpeg_path = shutil.which("ffmpeg")

        if not ffmpeg_path:
            raise RuntimeError("ffmpeg not found - install imageio-ffmpeg or system ffmpeg")

        # Create temp directory for frames
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Save frames as images
            for i, img in enumerate(frames):
                img.save(tmpdir / f"frame_{i:06d}.png")

            # Run ffmpeg
            cmd = [
                ffmpeg_path,
                "-y",  # Overwrite output
                "-framerate",
                str(self.fps),
                "-i",
                str(tmpdir / "frame_%06d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "baseline",
                "-level",
                "3.0",
                "-movflags",
                "+faststart",
                "-crf",
                "23",
                str(output_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

    def render_to_gif(
        self,
        battle_result: dict,
        output_path: t.Union[str, Path],
        frame_skip: int = 2,
        show_progress: bool = False,
    ) -> Path:
        """
        Render all frames to a GIF file.

        Args:
            battle_result: Complete battle result dict with frames
            output_path: Path to save the GIF
            frame_skip: Skip every N frames to reduce size
            show_progress: Print progress updates

        Returns:
            Path to the created GIF file
        """
        output_path = Path(output_path)
        frames = battle_result.get("frames", [])

        if not frames:
            raise ValueError("No frames to render")

        battle_info = {
            "arena_width": battle_result.get("arena_width", self.arena_width),
            "arena_height": battle_result.get("arena_height", self.arena_height),
        }

        # Render frames (skipping some for GIF size)
        images = []
        for i, frame in enumerate(frames):
            if i % frame_skip != 0:
                continue

            if show_progress and i % 30 == 0:
                print(f"Rendering frame {i}/{len(frames)}", file=sys.stderr)

            img = self.render_frame(frame, battle_info)
            images.append(img)

        if not images:
            raise ValueError("No frames rendered")

        # Calculate duration per frame in ms
        duration = int(1000 / self.fps * frame_skip)

        # Save as GIF
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            duration=duration,
            loop=0,
            optimize=True,
        )

        return output_path

    def render_to_bytes(
        self,
        battle_result: dict,
        format: str = "gif",
        frame_skip: int = 2,
    ) -> bytes:
        """
        Render battle to bytes (for direct Discord upload).

        Args:
            battle_result: Complete battle result dict
            format: "gif" or "mp4"
            frame_skip: For GIF, skip every N frames

        Returns:
            Bytes of the rendered video/gif
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            if format == "gif":
                output = tmpdir / "battle.gif"
                self.render_to_gif(battle_result, output, frame_skip=frame_skip)
            else:
                output = tmpdir / "battle.mp4"
                self.render_to_video(battle_result, output)

            return output.read_bytes()

    def render_bot_image(
        self,
        plating_name: str,
        weapon_name: t.Optional[str] = None,
        orientation: int = 0,
    ) -> bytes:
        """Render a static image of a bot with its parts.

        This is a convenience method that delegates to render_bot_sprite_to_bytes()
        for consistent rendering between battle and garage views.

        Args:
            plating_name: Name of equipped plating (required)
            weapon_name: Name of equipped weapon (optional)
            orientation: Orientation angle in degrees (0 = facing right)

        Returns:
            PNG image bytes
        """
        from .bot_sprite import render_bot_sprite_to_bytes

        # Use scale * 1.3 to match battle rendering
        return render_bot_sprite_to_bytes(
            plating_name=plating_name,
            weapon_name=weapon_name,
            orientation=orientation,
            weapon_orientation=orientation,
            scale=self.scale * 1.3,
            registry=self.parts_registry,
            output_size=(65, 65),
        )
