"""
Bot Arena - Battle Renderer

Renders battle frames to images and compiles them into a video file.
Uses Pillow for drawing and ffmpeg for video encoding.

Frames are drawn in order, because the renderer remembers things between frames:
effects spawned by battle events (see effects.py), scorch marks burned into the floor,
draining health bars, wrecks and the kill feed. reset() starts a fresh battle.
"""

import itertools
import logging
import math
import shutil
import subprocess
import sys
import tempfile
import typing as t
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .bot_sprite import SpriteCache, render_bot_sprite_to_bytes
from .effects import AIR, GROUND, SCORCH_COLOR, BattleEffects, paste_centered
from .image_utils import SPRITE_SCALE

try:
    import av
except ImportError:
    av = None

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

if t.TYPE_CHECKING:
    from .models import PartsRegistry

log = logging.getLogger("red.vrt.botarena.renderer")

Font = t.Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]

# Colors
ARENA_BG = (30, 30, 35)
GRID_COLOR = (45, 45, 50)
DEFAULT_TEAM1_COLOR = (66, 135, 245)  # Blue
DEFAULT_TEAM2_COLOR = (245, 66, 66)  # Red
TEXT_COLOR = (235, 235, 240)
MUTED_TEXT = (170, 172, 180)
OUTLINE_COLOR = (12, 12, 16)
PANEL_COLOR = (12, 14, 20)
DEAD_COLOR = (150, 150, 150)
HEALTH_HIGH = (80, 220, 90)
HEALTH_MID = (240, 205, 60)
HEALTH_LOW = (230, 60, 50)
HEALTH_CHIP = (255, 240, 205)  # Damage just taken, draining away

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

FONT_FILES = {
    False: ("arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"),
    True: ("arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
}

DEATH_BLAST_RADIUS = 75  # Arena units
WRECK_BURN_TIME = 3.0  # Seconds a wreck burns before it only smolders
KILL_FEED_TIME = 4.0  # Seconds a kill stays in the feed
BANNER_FADE_TIME = 0.35


def load_font(size: int, bold: bool = False) -> Font:
    """The first available TrueType font at this size (Arial, then DejaVu), else Pillow's default."""
    for candidate in FONT_FILES[bold] + FONT_FILES[False]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1 has no sized default font
        return ImageFont.load_default()


def blend(a: tuple, b: tuple, amount: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def health_color(ratio: float) -> tuple[int, int, int]:
    """Green when healthy, through yellow, to red when nearly destroyed."""
    if ratio >= 0.5:
        return blend(HEALTH_MID, HEALTH_HIGH, (ratio - 0.5) * 2)
    return blend(HEALTH_LOW, HEALTH_MID, ratio * 2)


def format_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


@dataclass
class BotVisual:
    """What the renderer remembers about a bot between frames."""

    shown_health: float  # Lags behind real health after a hit, drawing the draining damage chip
    flash: float = 0.0  # Hit flash strength (1 right after a hit, fading out)
    death_time: t.Optional[float] = None
    wreck: t.Optional[tuple[Image.Image, tuple[int, int]]] = None
    next_smoke: float = 0.0


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
        mission_id: t.Optional[str] = None,
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
            mission_id: Mission ID for mission-specific arena backgrounds (e.g., "1-1")
        """
        self.arena_width = width
        self.arena_height = height
        self.scale = scale
        self.output_width = int(width * scale)
        self.output_height = int(height * scale)
        self.fps = fps
        self.parts_registry = parts_registry
        self.chapter = chapter
        self.mission_id = mission_id

        # Set team colors from color names. Both teams can pick the same color (a red player
        # against the red default enemy, or two PvP players), so the enemy gets another one.
        self.team1_color = TEAM_COLORS.get(team1_color, DEFAULT_TEAM1_COLOR)
        self.team2_color = TEAM_COLORS.get(team2_color, DEFAULT_TEAM2_COLOR)
        if self.team2_color == self.team1_color:
            self.team2_color = TEAM_COLORS["blue"] if team1_color == "red" else TEAM_COLORS["red"]

        # Bot sprites drawn at base image scale * SPRITE_SCALE for visibility
        # (shared with collision.py so the hitbox matches the visuals)
        self.sprites = SpriteCache(parts_registry, scale * SPRITE_SCALE)
        # (text, font, color) -> (outlined text sprite, bounding box), so each label is drawn once per battle
        self.text_sprites: dict[tuple[str, Font, tuple], tuple[Image.Image, tuple[int, int, int, int]]] = {}
        self.text_boxes: dict[tuple[str, Font], tuple[tuple[int, int, int, int], int]] = {}

        # Load arena background if available
        self._arena_background: t.Optional[Image.Image] = None
        self._load_arena_background()

        # Interface sizes are tuned for the default 500px video and grow with the output
        self.ui = self.output_width / 500
        self.font = load_font(round(15 * self.ui), bold=True)  # HUD
        self.small_font = load_font(round(11 * self.ui), bold=True)  # Bot names, kill feed
        self.tiny_font = load_font(round(10 * self.ui))
        self.banner_font = load_font(round(38 * self.ui), bold=True)

        self.team_rings = {1: self._team_ring(self.team1_color), 2: self._team_ring(self.team2_color)}

        # Per-battle state, set up by reset() before the first frame
        self.floor: t.Optional[Image.Image] = None
        self.effects: t.Optional[BattleEffects] = None
        self.visuals: dict[str, BotVisual] = {}
        self.kill_feed: list[tuple[float, dict, dict]] = []
        self.now = 0.0  # Effects clock (keeps running while the video holds on the final frame)

    def _load_arena_background(self):
        """Load and scale the arena background image if available.

        Tries to load arena backgrounds in this order:
        1. Mission-specific: arena_mission_{mission_id} (e.g., arena_mission_1-1.webp)
        2. Chapter-specific: arena_chapter_{chapter} (e.g., arena_chapter_1.webp)
        3. Legacy fallback: arena_background
        """
        # Build list of filenames to try (most specific first, then fallbacks)
        filenames_to_try = []
        if self.mission_id:
            filenames_to_try.append(f"arena_mission_{self.mission_id}")
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
                        self._arena_background = img.resize(
                            (self.output_width, self.output_height), Image.Resampling.LANCZOS
                        )
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

    def _team_ring(self, color: tuple[int, int, int]) -> Image.Image:
        """A thin team-colored ring with a faint fill, drawn on the floor under each bot."""
        ss = 4
        radius = 48 * self.scale  # Just outside the plating
        size = math.ceil(radius * 2 + 6)
        c, r = size * ss / 2, radius * ss
        mask = Image.new("L", (size * ss, size * ss), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((c - r, c - r, c + r, c + r), fill=34)
        draw.ellipse((c - r, c - r, c + r, c + r), outline=200, width=round(2 * self.ui * ss))
        ring = Image.new("RGBA", (size, size), color + (0,))
        ring.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
        return ring

    # ── Per-battle state ─────────────────────────────────────────────────────

    def reset(self, seed: int = 0):
        """Start a fresh battle: clean floor, no effects, no remembered bots."""
        if self._arena_background:
            self.floor = self._arena_background.copy()
        else:
            self.floor = Image.new("RGB", (self.output_width, self.output_height), ARENA_BG)
            self._draw_grid(ImageDraw.Draw(self.floor))
        self.effects = BattleEffects(self.scale, self.fps, seed)
        self.visuals = {}
        self.kill_feed = []
        self.now = 0.0

    def advance(self, frame_data: dict):
        """Feed one simulation frame into the effects: spawn what its events caused, then step everything."""
        if self.effects is None:
            self.reset()
        fx = self.effects
        now = self.now = frame_data.get("time", 0.0)
        bots = {b["id"]: b for b in frame_data.get("bots", []) if "id" in b}
        for bot in bots.values():
            if bot["id"] not in self.visuals:
                self.visuals[bot["id"]] = BotVisual(shown_health=bot.get("health", 0))

        for event in frame_data.get("events", []):
            kind = event.get("type")
            if "x" not in event:
                continue
            x, y = event["x"] * self.scale, event["y"] * self.scale
            if kind == "shot":
                fx.muzzle_flash(x, y, event.get("angle", 0.0), event.get("projectile_type", "bullet"))
            elif kind == "hit":
                if not event.get("splash"):
                    fx.impact(x, y, event.get("projectile_type", "bullet"), event.get("damage", 0))
                if event.get("damage", 0) > 0 and event.get("target_id") in self.visuals:
                    self.visuals[event["target_id"]].flash = 1.0
            elif kind == "blocked":
                fx.impact(x, y, "bullet", event.get("damage", 0), blocked=True)
                if event.get("blocker_id") in self.visuals:
                    self.visuals[event["blocker_id"]].flash = 1.0
            elif kind == "heal":
                if event.get("amount", 0) > 0:
                    fx.heal_burst(x, y)
            elif kind == "splash":
                # No scorch mark: rapid-fire missiles would burn a trail along a moving target's path
                fx.explosion(x, y, event.get("radius", 40))
            elif kind == "kill":
                fx.explosion(x, y, DEATH_BLAST_RADIUS, big=True)
                self._scorch(x, y, DEATH_BLAST_RADIUS * 0.8)
                killer, victim = bots.get(event.get("killer_id")), bots.get(event.get("victim_id"))
                if killer and victim:
                    self.kill_feed.append((now, killer, victim))

        for proj in frame_data.get("projectiles", []):
            if proj.get("projectile_type") == "missile":
                fx.missile_trail(
                    proj["x"] * self.scale,
                    proj["y"] * self.scale,
                    proj.get("vx", 0.0) * self.scale,
                    proj.get("vy", 0.0) * self.scale,
                )

        dt = 1.0 / self.fps
        for bot_id, bot in bots.items():
            visual = self.visuals[bot_id]
            health = bot.get("health", 0)
            # Damage drains away over about a quarter second; healing shows at once
            if health < visual.shown_health:
                visual.shown_health = max(health, visual.shown_health - max(1.0, visual.shown_health - health) * dt * 5)
            else:
                visual.shown_health = health
            visual.flash = max(0.0, visual.flash - dt / 0.12)

            if not bot.get("is_alive", True):
                if visual.death_time is None:
                    visual.death_time = now
                    visual.wreck = self.sprites.wreck(
                        bot.get("plating") or "",
                        bot.get("component") or None,
                        bot.get("orientation", 0),
                        bot.get("weapon_orientation", 0),
                    )
                burning = now - visual.death_time < WRECK_BURN_TIME
                if now >= visual.next_smoke:
                    fx.wreck_smoke(bot["x"] * self.scale, bot["y"] * self.scale, burning)
                    visual.next_smoke = now + (0.1 if burning else 0.4)

        self.kill_feed = [entry for entry in self.kill_feed if now - entry[0] < KILL_FEED_TIME]
        fx.update()

    def _scorch(self, x: float, y: float, radius: float):
        """Burn a dark mark into the arena floor (it stays for the rest of the battle)."""
        paste_centered(self.floor, self.effects.sprites.blob("scorch", radius * self.scale, SCORCH_COLOR, 0.55), x, y)

    # ── Frame drawing ────────────────────────────────────────────────────────

    def render_frame(self, frame_data: dict, battle_info: dict) -> Image.Image:
        """
        Advance the effects by one frame and render it.

        Frames must be rendered in order; call reset() before the first frame of a battle.

        Args:
            frame_data: Frame data dict with bots, projectiles, events
            battle_info: Battle metadata (arena size, teams, etc.)

        Returns:
            PIL Image of the rendered frame
        """
        self.advance(frame_data)
        return self.compose(frame_data)

    def compose(self, frame_data: dict, banner: t.Optional[tuple[int, float, float]] = None) -> Image.Image:
        """Draw the current state of the battle (call advance() for this frame first).

        banner: (winning team, battle duration, fade-in 0-1) to show the result over the arena.
        """
        img = self.floor.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        self.effects.draw(img, draw, GROUND)

        # Wrecks first (underneath), then living bots on top
        bots = frame_data.get("bots", [])
        alive_bots = [b for b in bots if b.get("is_alive", True)]
        for bot_data in bots:
            if not bot_data.get("is_alive", True):
                self._draw_wreck(img, bot_data)
        for bot_data in alive_bots:
            self._draw_bot(img, draw, bot_data)

        for proj_data in frame_data.get("projectiles", []):
            x, y = proj_data["x"] * self.scale, proj_data["y"] * self.scale
            self.effects.draw_projectile(img, proj_data, x, y)

        self.effects.draw(img, draw, AIR)

        # Labels go over the smoke so they stay readable
        for bot_data in bots:
            self._draw_bot_labels(img, draw, bot_data)

        self._draw_hud(img, draw, frame_data)
        if banner:
            self._draw_banner(img, draw, *banner)
        return img

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
        """Draw a living bot: shadow, team ring, plating, turret, and a white flash when it's hit."""
        x, y = self._scale_pos(bot_data["x"], bot_data["y"])
        team = bot_data.get("team", 1)
        plating_name = bot_data.get("plating", "") or None
        weapon_name = bot_data.get("component", "") or None
        orientation = bot_data.get("orientation", 0)
        weapon_orientation = bot_data.get("weapon_orientation", orientation)

        if not plating_name:
            # No plating - draw simple shape (this is intentional, not a fallback)
            color = self.team1_color if team == 1 else self.team2_color
            self._draw_bot_shape_with_turret(draw, x, y, self._scale_size(32), orientation, weapon_orientation, color)
            return

        layers = self.sprites.layers(x, y, plating_name, weapon_name, orientation, weapon_orientation)
        if not layers:
            raise RuntimeError(f"Failed to render bot sprite for plating '{plating_name}', weapon '{weapon_name}'")

        # Light comes from the top-left, so shadows fall down-right
        shadow_dx, shadow_dy = round(7 * self.scale), round(10 * self.scale)
        for image, (left, top) in layers:
            shadow, pad = self.sprites.shadow(image)
            img.paste((0, 0, 0), (left - pad + shadow_dx, top - pad + shadow_dy), shadow)
        paste_centered(img, self.team_rings[team], x, y)

        visual = self.visuals.get(bot_data.get("id"))
        for image, position in layers:
            img.paste(image, position, image)
            if visual and visual.flash > 0:
                img.paste((255, 255, 255), position, self.sprites.flash(image, visual.flash))

    def _draw_wreck(self, img: Image.Image, bot_data: dict):
        """Draw a destroyed bot as a scorched hulk, glowing while it still burns."""
        x, y = self._scale_pos(bot_data["x"], bot_data["y"])
        visual = self.visuals.get(bot_data.get("id"))
        if not visual or not visual.wreck:
            orientation = bot_data.get("orientation", 0)
            self._draw_bot_shape(ImageDraw.Draw(img), x, y, self._scale_size(32), orientation, (80, 80, 80), False)
            return
        wreck, (dx, dy) = visual.wreck
        shadow, pad = self.sprites.shadow(wreck)
        img.paste((0, 0, 0), (x + dx - pad + round(4 * self.scale), y + dy - pad + round(6 * self.scale)), shadow)
        img.paste(wreck, (x + dx, y + dy), wreck)

    def _draw_bot_labels(self, img: Image.Image, draw: ImageDraw.ImageDraw, bot_data: dict):
        """Health bar above a living bot, and its name (in its team's color) below it."""
        x, y = self._scale_pos(bot_data["x"], bot_data["y"])
        team = bot_data.get("team", 1)
        is_alive = bot_data.get("is_alive", True)

        if is_alive:
            max_health = bot_data.get("max_health", 100)
            ratio = bot_data.get("health", 0) / max_health if max_health > 0 else 0
            visual = self.visuals.get(bot_data.get("id"))
            shown = visual.shown_health / max_health if visual and max_health > 0 else ratio

            width = round(60 * self.scale)
            height = max(3, round(9 * self.scale))
            left = x - width // 2
            top = y - round(66 * self.scale)
            draw.rectangle((left - 1, top - 1, left + width, top + height), fill=PANEL_COLOR + (210,))
            if shown > ratio:
                chip_right = left + max(1, round(width * shown)) - 1
                draw.rectangle((left, top, chip_right, top + height - 1), fill=HEALTH_CHIP + (235,))
            if ratio > 0:
                fill_right = left + max(1, round(width * ratio)) - 1
                draw.rectangle((left, top, fill_right, top + height - 1), fill=health_color(ratio))
                # A lighter top edge gives the bar a little depth
                draw.line((left, top, fill_right, top), fill=(255, 255, 255, 70))

        # A wreck keeps its name while it burns, then the name fades (the kill feed has the record)
        opacity = 1.0
        if not is_alive:
            visual = self.visuals.get(bot_data.get("id"))
            if visual and visual.death_time is not None:
                opacity = min(1.0, (WRECK_BURN_TIME - (self.now - visual.death_time)) / 0.5)
            if opacity <= 0:
                return

        name = bot_data.get("name", "Bot")[:10]
        color = (self.team1_color if team == 1 else self.team2_color) if is_alive else DEAD_COLOR
        text_width = self.text_width(name, self.small_font)
        self.draw_text(
            img, (x - text_width // 2, y + round(52 * self.scale)), name, self.small_font, color, opacity=opacity
        )

    def _draw_hud(self, img: Image.Image, draw: ImageDraw.ImageDraw, frame_data: dict):
        """Scoreboard along the top (each team either side of the clock), recent kills under it on the right."""
        ui = self.ui
        width = self.output_width
        center = width // 2
        top = round(3 * ui)
        strip_h = round(24 * ui)
        clock_w = round(54 * ui)
        side_w = round(132 * ui)
        gap = round(3 * ui)
        pad = round(7 * ui)
        radius = round(5 * ui)

        clock = format_clock(frame_data.get("time", 0))
        draw.rounded_rectangle(
            (center - clock_w // 2, top, center + clock_w // 2, top + strip_h), radius=radius, fill=PANEL_COLOR + (205,)
        )
        clock_w_text = self.text_width(clock, self.font)
        self.draw_text(img, (center - clock_w_text // 2, top + round(4 * ui)), clock, self.font, TEXT_COLOR)

        # Each team's side: name, bots still standing, and a bar of the team's combined health
        bots = frame_data.get("bots", [])
        for team, label, color in ((1, "PLAYER", self.team1_color), (2, "OPPONENT", self.team2_color)):
            members = [b for b in bots if b.get("team") == team]
            alive = sum(1 for b in members if b.get("is_alive"))
            health = sum(b.get("health", 0) for b in members)
            max_health = sum(b.get("max_health", 0) for b in members) or 1
            if team == 1:
                left = center - clock_w // 2 - gap - side_w
            else:
                left = center + clock_w // 2 + gap
            right = left + side_w
            draw.rounded_rectangle((left, top, right, top + strip_h), radius=radius, fill=PANEL_COLOR + (175,))

            count = f"{alive}/{len(members)}"
            label_w = self.text_width(label, self.small_font)
            count_w = self.text_width(count, self.small_font)
            text_y = top + round(3 * ui)
            # Mirrored around the clock: names on the outside, counts next to the clock
            label_x = left + pad if team == 1 else right - pad - label_w
            count_x = right - pad - count_w if team == 1 else left + pad
            self.draw_text(img, (label_x, text_y), label, self.small_font, color)
            self.draw_text(img, (count_x, text_y), count, self.small_font, TEXT_COLOR)

            bar_h = max(2, round(4 * ui))
            bar_top = top + strip_h - bar_h - round(4 * ui)
            bar_left, bar_right = left + pad, right - pad
            draw.rectangle((bar_left, bar_top, bar_right, bar_top + bar_h), fill=(255, 255, 255, 45))
            fill_w = round((bar_right - bar_left) * health / max_health)
            if fill_w > 0:
                # Bars drain toward the clock
                if team == 1:
                    draw.rectangle((bar_left, bar_top, bar_left + fill_w, bar_top + bar_h), fill=color)
                else:
                    draw.rectangle((bar_right - fill_w, bar_top, bar_right, bar_top + bar_h), fill=color)

        # Kill feed under the scoreboard on the right, newest at the bottom
        line_h = round(18 * ui)
        line_top = top + strip_h + round(5 * ui)
        for killed_at, killer, victim in self.kill_feed[-4:]:
            parts = [
                (killer.get("name", "Bot")[:10], self.team1_color if killer.get("team") == 1 else self.team2_color),
                ("  »  ", MUTED_TEXT),
                (victim.get("name", "Bot")[:10], self.team1_color if victim.get("team") == 1 else self.team2_color),
            ]
            line_w = sum(self.text_width(text, self.small_font) for text, _ in parts) + pad * 2
            left = width - line_w - round(6 * ui)
            fade = max(0.0, min(1.0, (KILL_FEED_TIME - (self.now - killed_at)) / 0.5))
            draw.rounded_rectangle(
                (left, line_top, left + line_w, line_top + line_h - round(3 * ui)),
                radius=round(4 * ui),
                fill=PANEL_COLOR + (int(175 * fade),),
            )
            cursor = left + pad
            for text, color in parts:
                self.draw_text(img, (cursor, line_top + round(1 * ui)), text, self.small_font, color, opacity=fade)
                cursor += self.text_width(text, self.small_font)
            line_top += line_h

    def _draw_banner(self, img: Image.Image, draw: ImageDraw.ImageDraw, winner: int, duration: float, fade: float):
        """The result across the middle of the arena, shown while the video holds on the final frame."""
        if winner == 1:
            title, color = "PLAYER WINS", self.team1_color
        elif winner == 2:
            title, color = "OPPONENT WINS", self.team2_color
        else:
            title, color = "DRAW", TEXT_COLOR
        band_h = round(86 * self.ui)
        band_top = (self.output_height - band_h) // 2
        draw.rectangle((0, band_top, self.output_width, band_top + band_h), fill=PANEL_COLOR + (int(185 * fade),))
        accent = max(2, round(3 * self.ui))
        draw.rectangle((0, band_top, self.output_width, band_top + accent), fill=color + (int(230 * fade),))
        draw.rectangle(
            (0, band_top + band_h - accent, self.output_width, band_top + band_h), fill=color + (int(230 * fade),)
        )
        title_w = self.text_width(title, self.banner_font)
        self.draw_text(
            img,
            ((self.output_width - title_w) // 2, band_top + round(12 * self.ui)),
            title,
            self.banner_font,
            color,
            opacity=fade,
        )
        subtitle = f"Battle time {format_clock(duration)}"
        sub_w = self.text_width(subtitle, self.tiny_font)
        self.draw_text(
            img,
            ((self.output_width - sub_w) // 2, band_top + band_h - round(24 * self.ui)),
            subtitle,
            self.tiny_font,
            MUTED_TEXT,
            opacity=fade,
        )

    # ── Text ─────────────────────────────────────────────────────────────────

    def text_box(self, text: str, font: Font) -> tuple[tuple[int, int, int, int], int]:
        """The outlined string's bounding box and outline width (0 for bitmap fonts, which can't be outlined)."""
        key = (text, font)
        if key not in self.text_boxes:
            stroke = max(1, round(self.ui))
            try:
                box = tuple(int(v) for v in font.getbbox(text, stroke_width=stroke))
            except TypeError:
                stroke = 0
                box = tuple(int(v) for v in font.getbbox(text))
            self.text_boxes[key] = (box, stroke)
        return self.text_boxes[key]

    def text_sprite(self, text: str, font: Font, fill: tuple) -> tuple[Image.Image, tuple[int, int, int, int]]:
        """The string drawn once with a dark outline (readable on any arena), and its bounding box."""
        key = (text, font, fill)
        if key not in self.text_sprites:
            (left, top, right, bottom), stroke = self.text_box(text, font)
            sprite = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)), fill + (0,))
            text_draw = ImageDraw.Draw(sprite)
            if stroke:
                text_draw.text(
                    (-left, -top), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=OUTLINE_COLOR
                )
            else:
                text_draw.text((-left, -top), text, font=font, fill=fill)
            self.text_sprites[key] = (sprite, (left, top, right, bottom))
        return self.text_sprites[key]

    def text_width(self, text: str, font: Font) -> int:
        box = self.text_box(text, font)[0]
        return box[2] - box[0]

    def draw_text(
        self, img: Image.Image, xy: tuple[int, int], text: str, font: Font, fill: tuple, opacity: float = 1.0
    ):
        """Paste an outlined label with its top-left at xy, optionally faded."""
        sprite, bbox = self.text_sprite(text, font, tuple(fill))
        mask = sprite if opacity >= 1.0 else sprite.getchannel("A").point(lambda a: int(a * opacity))
        img.paste(sprite, (xy[0] + bbox[0], xy[1] + bbox[1]), mask)

    # ── Fallback shapes ──────────────────────────────────────────────────────

    def _draw_bot_shape_with_turret(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        radius: int,
        orientation: float,
        weapon_orientation: float,
        color: tuple,
    ):
        """Draw a simple shape for bots without plating."""
        self._draw_bot_shape(draw, x, y, radius, orientation, color, True)
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

        # Frames are rendered lazily and streamed to the encoder one at a time
        # (a fresh generator is created per encoder attempt so fallbacks re-render)
        # Try PyAV directly first (best Discord compatibility)
        try:
            frame_gen = self._iter_rendered_frames(battle_result, freeze_duration, show_progress)
            self._write_video_pyav(frame_gen, output_path)
            return output_path
        except Exception as e:
            if show_progress:
                print(f"PyAV failed: {e}, trying ffmpeg subprocess...", file=sys.stderr)

        # Try ffmpeg subprocess
        try:
            frame_gen = self._iter_rendered_frames(battle_result, freeze_duration, show_progress)
            self._write_video_ffmpeg(frame_gen, output_path)
            return output_path
        except Exception as e:
            if show_progress:
                print(f"ffmpeg failed: {e}, falling back to GIF...", file=sys.stderr)

        # Final fallback: convert to GIF
        gif_path = output_path.with_suffix(".gif")
        self.render_to_gif(battle_result, gif_path, frame_skip=2, show_progress=show_progress)
        return gif_path

    def _iter_rendered_frames(
        self,
        battle_result: dict,
        freeze_duration: float,
        show_progress: bool,
        frame_skip: int = 1,
    ) -> t.Iterator[Image.Image]:
        """Yield rendered frames one at a time, then hold on the final state with the result banner.

        Every simulation frame advances the effects, even frames a GIF skips, so explosions and
        smoke play out the same at any frame rate. While the video holds on the end, the last
        explosions and smoke keep playing out under the banner.

        Streaming frames to the encoder avoids materializing the whole battle
        (potentially thousands of images) in memory at once.
        """
        frames = battle_result.get("frames", [])
        self.reset(battle_result.get("seed") or 0)
        for i, frame in enumerate(frames):
            if show_progress and i % 30 == 0:
                print(f"Rendering frame {i}/{len(frames)}", file=sys.stderr)
            self.advance(frame)
            if i % frame_skip == 0:
                yield self.compose(frame)

        if not frames or freeze_duration <= 0:
            return
        hold_count = int(freeze_duration * self.fps)
        if show_progress:
            print(f"Adding {hold_count} freeze frames ({freeze_duration}s)...", file=sys.stderr)
        final = {**frames[-1], "events": [], "projectiles": []}
        end_time = final.get("time", 0.0)
        winner = battle_result.get("winner_team", 0)
        duration = battle_result.get("duration", end_time)
        for i in range(hold_count):
            # The clock stays frozen on screen while the effects keep running
            self.advance({**final, "time": end_time + (i + 1) / self.fps})
            if i % frame_skip == 0:
                fade = min(1.0, (i + 1) / (BANNER_FADE_TIME * self.fps))
                yield self.compose(final, banner=(winner, duration, fade))

    def _write_video_pyav(self, frames: t.Iterable[Image.Image], output_path: Path):
        """Write video using PyAV directly with Discord-compatible settings."""
        if av is None:
            raise RuntimeError("PyAV not installed")

        frame_iter = iter(frames)
        first_img = next(frame_iter)

        container = av.open(str(output_path), mode="w")
        stream = container.add_stream("libx264", rate=self.fps)
        stream.width = first_img.width
        stream.height = first_img.height
        stream.pix_fmt = "yuv420p"  # Required for Discord
        # H.264 encoding options for maximum compatibility
        stream.options = {
            "profile": "baseline",
            "level": "3.0",
            "movflags": "+faststart",
            "crf": "23",  # Quality (lower = better, 23 is default)
        }

        for img in itertools.chain([first_img], frame_iter):
            # Convert PIL Image to av.VideoFrame
            frame = av.VideoFrame.from_image(img)
            frame = frame.reformat(format="yuv420p")
            for packet in stream.encode(frame):
                container.mux(packet)

        # Flush encoder
        for packet in stream.encode():
            container.mux(packet)

        container.close()

    def _write_video_ffmpeg(self, frames: t.Iterable[Image.Image], output_path: Path):
        """Write video using ffmpeg subprocess with Discord-compatible settings."""
        # Check if ffmpeg is available - try imageio-ffmpeg first, then system ffmpeg
        ffmpeg_path = None
        if imageio_ffmpeg is not None:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

        if not ffmpeg_path:
            ffmpeg_path = shutil.which("ffmpeg")

        if not ffmpeg_path:
            raise RuntimeError("ffmpeg not found - install imageio-ffmpeg or system ffmpeg")

        # Create temp directory for frames
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Save frames as images one at a time (streamed, never held in a list)
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

        # Render frames (skipping some for GIF size), holding on the result for two seconds
        images = list(self._iter_rendered_frames(battle_result, 2.0, show_progress, frame_skip=frame_skip))

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
        # Use scale * SPRITE_SCALE to match battle rendering
        return render_bot_sprite_to_bytes(
            plating_name=plating_name,
            weapon_name=weapon_name,
            orientation=orientation,
            weapon_orientation=orientation,
            scale=self.scale * SPRITE_SCALE,
            registry=self.parts_registry,
            output_size=(65, 65),
        )
