"""
Bot Arena - Battle Effects

Purely visual extras the renderer layers over each battle frame: anti-aliased projectile
sprites, muzzle flashes, impact sparks, explosions, smoke and burning wrecks.
None of this feeds back into the battle engine; it only reads frame data and events.

All sprites are drawn large and shrunk (or blurred) so their edges are smooth, then cached,
so after the first few frames of a battle almost every effect is a single paste.
"""

import math
import random
import typing as t
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SUPERSAMPLE = 4  # Hand-drawn sprites are drawn this many times larger, then shrunk for smooth edges
ALPHA_LEVELS = 12  # Fading sprites are cached at this many opacity steps
ANGLE_STEP = 3  # Oriented sprites are cached per this many degrees
MAX_PARTICLES = 600  # Oldest particles are dropped past this (keeps huge brawls fast to render)

GROUND = 0  # Drawn under the bots
AIR = 1  # Drawn over the bots

Color = tuple[int, int, int]

# Radial falloff for each kind of soft blob: distance from center (0-1) -> opacity (0-1)
BLOB_PROFILES: dict[str, t.Callable[[float], float]] = {
    "glow": lambda d: max(0.0, 1.0 - d) ** 2.2,
    "hot": lambda d: max(0.0, 1.0 - d) ** 1.4,
    # Solid in the middle with a soft edge, so flames read even on bright arena floors
    "fire": lambda d: min(1.0, 2.2 * max(0.0, 1.0 - d)) ** 1.3,
    "smoke": lambda d: 0.5 + 0.5 * math.cos(math.pi * min(1.0, d)),
    "scorch": lambda d: (0.5 + 0.5 * math.cos(math.pi * min(1.0, d))) ** 0.7,
}

# How each projectile type looks in flight
TRACERS: dict[str, dict] = {
    # (length, width, core color, glow color, glow size) in arena units
    "bullet": {"length": 20, "width": 4, "core": (255, 250, 215), "glow": (255, 165, 50), "blur": 4},
    "laser": {"length": 34, "width": 5, "core": (255, 240, 230), "glow": (255, 45, 35), "blur": 6},
    "cannon": {"length": 26, "width": 12, "core": (225, 240, 255), "glow": (60, 150, 255), "blur": 8},
    "missile": {"length": 22, "width": 8, "core": (255, 245, 200), "glow": (255, 110, 10), "blur": 6},
    "heal": {"length": 24, "width": 9, "core": (225, 255, 235), "glow": (40, 230, 110), "blur": 7},
}

# Muzzle flash, impact and spark colors per projectile type
FLASH_COLORS: dict[str, Color] = {
    "bullet": (255, 200, 90),
    "laser": (255, 80, 60),
    "cannon": (110, 180, 255),
    "missile": (255, 140, 40),
    "heal": (80, 255, 150),
    "shockwave": (255, 180, 80),
}
SMOKE_COLOR: Color = (120, 118, 116)
DARK_SMOKE_COLOR: Color = (52, 50, 50)
FIRE_COLOR: Color = (255, 120, 30)
SCORCH_COLOR: Color = (22, 18, 16)


def quantize_alpha(alpha: float) -> int:
    return max(0, min(ALPHA_LEVELS, round(alpha * ALPHA_LEVELS)))


def quantize_angle(angle: float) -> int:
    return int(round(angle / ANGLE_STEP) * ANGLE_STEP) % 360


class EffectSprites:
    """Builds effect sprites on first use and keeps them for the rest of the battle."""

    def __init__(self, scale: float):
        self.scale = scale  # Arena units -> output pixels
        self.cache: dict[tuple, Image.Image] = {}
        self.gradients: dict[str, Image.Image] = {}

    def px(self, arena_units: float) -> float:
        return arena_units * self.scale

    def gradient(self, kind: str) -> Image.Image:
        """A 256px opacity mask for a blob kind (full size, shrunk per sprite)."""
        if kind not in self.gradients:
            profile = BLOB_PROFILES[kind]
            # radial_gradient is 0 at the center, 181 on the inscribed circle and 255 in the corners
            self.gradients[kind] = Image.radial_gradient("L").point(lambda v: int(255 * profile(min(1.0, v / 181))))
        return self.gradients[kind]

    def blob(self, kind: str, radius: float, color: Color, alpha: float) -> t.Optional[Image.Image]:
        """A soft round sprite `radius` output pixels across its glow, or None when invisible."""
        radius = max(1, round(radius))
        level = quantize_alpha(alpha)
        if level == 0:
            return None
        key = ("blob", kind, radius, color, level)
        sprite = self.cache.get(key)
        if sprite is None:
            size = radius * 2 + 1
            mask = self.gradient(kind).resize((size, size), Image.Resampling.LANCZOS)
            if level < ALPHA_LEVELS:
                mask = mask.point(lambda v: v * level // ALPHA_LEVELS)
            sprite = Image.new("RGBA", (size, size), color + (0,))
            if kind in ("hot", "fire"):
                # White-hot center fading out to the color
                core = self.gradient("glow").resize((size, size), Image.Resampling.LANCZOS)
                sprite = Image.composite(Image.new("RGBA", (size, size), (255, 255, 240, 0)), sprite, core)
            sprite.putalpha(mask)
            self.cache[key] = sprite
        return sprite

    def ring(self, radius: float, width: float, color: Color, alpha: float) -> t.Optional[Image.Image]:
        """An anti-aliased circle outline, softly glowing."""
        radius = max(2, round(radius))
        width = max(1, round(width))
        level = quantize_alpha(alpha)
        if level == 0:
            return None
        key = ("ring", radius, width, color, level)
        sprite = self.cache.get(key)
        if sprite is None:
            pad = width + 2
            size = (radius + pad) * 2 + 1
            big = Image.new("L", (size * SUPERSAMPLE, size * SUPERSAMPLE), 0)
            c = size * SUPERSAMPLE / 2
            r = radius * SUPERSAMPLE
            ImageDraw.Draw(big).ellipse((c - r, c - r, c + r, c + r), outline=255, width=width * SUPERSAMPLE)
            big = big.filter(ImageFilter.GaussianBlur(SUPERSAMPLE * 0.8))
            mask = big.resize((size, size), Image.Resampling.LANCZOS)
            mask = mask.point(lambda v: v * level // ALPHA_LEVELS)
            sprite = Image.new("RGBA", (size, size), color + (0,))
            sprite.putalpha(mask)
            self.cache[key] = sprite
        return sprite

    def tracer(self, kind: str, angle: float) -> Image.Image:
        """A glowing streak for a projectile in flight, centered on its head and trailing behind it."""
        key = ("tracer", kind, quantize_angle(angle))
        sprite = self.cache.get(key)
        if sprite is None:
            base = self.cache.get(("tracer", kind))
            if base is None:
                base = self._streak(**TRACERS[kind])
                self.cache[("tracer", kind)] = base
            sprite = base.rotate(-key[2], resample=Image.Resampling.BICUBIC, expand=True)
            self.cache[key] = sprite
        return sprite

    def _streak(self, length: float, width: float, core: Color, glow: Color, blur: float) -> Image.Image:
        """A streak pointing right whose head sits on the image center, fading out toward its tail."""
        ss = SUPERSAMPLE
        length, width, blur = self.px(length), max(1.5, self.px(width)), self.px(blur)
        size = math.ceil(length + blur * 2 + 2) * 2
        full = (size * ss, size * ss)
        c = size * ss / 2
        tail_x = c - length * ss

        # Soft glow around the whole streak, and a bright core rounded at both ends
        halo = Image.new("L", full, 0)
        ImageDraw.Draw(halo).ellipse(
            (tail_x, c - (width + blur) * ss / 2, c + blur * ss / 2, c + (width + blur) * ss / 2), fill=150
        )
        halo = halo.filter(ImageFilter.GaussianBlur(blur * ss / 2))
        core_mask = Image.new("L", full, 0)
        ImageDraw.Draw(core_mask).ellipse(
            (tail_x, c - width * ss / 2, c + width * ss / 4, c + width * ss / 2), fill=255
        )

        # Fade toward the tail: full strength at the head, nothing at the far end
        ramp = Image.linear_gradient("L").rotate(90).resize((max(1, int(length * ss)), full[1]))
        fade = Image.new("L", full, 0)
        fade.paste(ramp.point(lambda v: int(255 * (v / 255) ** 0.6)), (int(tail_x), 0))
        fade.paste(255, (int(c), 0, full[0], full[1]))

        sprite = Image.new("RGBA", full, glow + (0,))
        sprite.putalpha(ImageChops.multiply(halo, fade))
        core_layer = Image.new("RGBA", full, core + (0,))
        core_layer.putalpha(ImageChops.multiply(core_mask, fade))
        sprite = Image.alpha_composite(sprite, core_layer)
        return sprite.resize((size, size), Image.Resampling.LANCZOS)

    def muzzle_flash(self, kind: str, angle: float, size: float) -> Image.Image:
        """A forward-pointing burst of flame centered on the barrel tip."""
        key = ("muzzle", kind, quantize_angle(angle), round(size))
        sprite = self.cache.get(key)
        if sprite is None:
            base_key = ("muzzle", kind, round(size))
            base = self.cache.get(base_key)
            if base is None:
                base = self._flash_cone(FLASH_COLORS.get(kind, FLASH_COLORS["bullet"]), self.px(size))
                self.cache[base_key] = base
            sprite = base.rotate(-key[2], resample=Image.Resampling.BICUBIC, expand=True)
            self.cache[key] = sprite
        return sprite

    def _flash_cone(self, color: Color, length: float) -> Image.Image:
        ss = SUPERSAMPLE
        half = math.ceil(length * 1.3) + 2
        size = half * 2
        c = size * ss / 2
        L = length * ss
        mask = Image.new("L", (size * ss, size * ss), 0)
        d = ImageDraw.Draw(mask)
        # Main cone forward, two small side spikes, round puff at the barrel
        d.polygon([(c, c - L * 0.22), (c + L, c), (c, c + L * 0.22)], fill=255)
        d.polygon([(c, c - L * 0.1), (c + L * 0.45, c - L * 0.42), (c + L * 0.12, c)], fill=200)
        d.polygon([(c, c + L * 0.1), (c + L * 0.45, c + L * 0.42), (c + L * 0.12, c)], fill=200)
        d.ellipse((c - L * 0.25, c - L * 0.25, c + L * 0.25, c + L * 0.25), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(ss * 0.9))
        glow = mask.filter(ImageFilter.GaussianBlur(L * 0.15))
        sprite = Image.new("RGBA", mask.size, color + (0,))
        sprite.putalpha(glow.point(lambda v: min(255, v * 2)))
        core = Image.new("RGBA", mask.size, (255, 255, 235, 0))
        core.putalpha(mask.point(lambda v: v * 3 // 4))
        sprite = Image.alpha_composite(sprite, core)
        return sprite.resize((size, size), Image.Resampling.LANCZOS)

    def crescent(self, radius: float, color: Color, alpha: float, angle: float) -> t.Optional[Image.Image]:
        """A pressure wave arc facing `angle` (the jackhammer's shockwave)."""
        radius = max(3, round(radius))
        level = quantize_alpha(alpha)
        if level == 0:
            return None
        key = ("crescent", radius, color, level, quantize_angle(angle))
        sprite = self.cache.get(key)
        if sprite is None:
            base_key = key[:4]
            base = self.cache.get(base_key)
            if base is None:
                ss = SUPERSAMPLE
                size = radius * 2 + 8
                c = size * ss / 2
                r = radius * ss
                mask = Image.new("L", (size * ss, size * ss), 0)
                ImageDraw.Draw(mask).arc((c - r, c - r, c + r, c + r), -55, 55, fill=255, width=max(ss, r // 3))
                mask = mask.filter(ImageFilter.GaussianBlur(ss * 1.2)).resize((size, size), Image.Resampling.LANCZOS)
                base = Image.new("RGBA", (size, size), color + (0,))
                base.putalpha(mask.point(lambda v: v * level // ALPHA_LEVELS))
                self.cache[base_key] = base
            sprite = base.rotate(-key[4], resample=Image.Resampling.BICUBIC)
            self.cache[key] = sprite
        return sprite

    def plus(self, size: float, color: Color, alpha: float) -> t.Optional[Image.Image]:
        """A small glowing '+' (healing)."""
        size = max(3, round(size))
        level = quantize_alpha(alpha)
        if level == 0:
            return None
        key = ("plus", size, color, level)
        sprite = self.cache.get(key)
        if sprite is None:
            ss = SUPERSAMPLE
            full = (size + 4) * ss
            c = full / 2
            arm, thick = size * ss / 2, max(ss, size * ss / 4)
            mask = Image.new("L", (full, full), 0)
            d = ImageDraw.Draw(mask)
            d.rectangle((c - arm, c - thick / 2, c + arm, c + thick / 2), fill=255)
            d.rectangle((c - thick / 2, c - arm, c + thick / 2, c + arm), fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(ss * 0.6)).resize(
                (size + 4, size + 4), Image.Resampling.LANCZOS
            )
            sprite = Image.new("RGBA", mask.size, color + (0,))
            sprite.putalpha(mask.point(lambda v: v * level // ALPHA_LEVELS))
            self.cache[key] = sprite
        return sprite


def paste_centered(frame: Image.Image, sprite: t.Optional[Image.Image], x: float, y: float):
    """Paste an RGBA sprite so its center lands on (x, y), blending with its alpha."""
    if sprite is None:
        return
    frame.paste(sprite, (int(round(x - sprite.width / 2)), int(round(y - sprite.height / 2))), sprite)


@dataclass
class Particle:
    """One short-lived blob, ring, spark or chunk of debris (positions and speeds in output pixels)."""

    kind: str  # glow, hot, smoke, scorch, ring, spark, debris, plus
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    life: float = 0.3
    size: tuple[float, float] = (2.0, 2.0)  # Radius at birth and at death
    alpha: tuple[float, float] = (1.0, 0.0)  # Opacity at birth and at death
    color: Color = (255, 255, 255)
    drag: float = 0.0  # Share of speed lost per second
    layer: int = AIR
    delay: float = 0.0  # Seconds before it appears (staggers explosions)
    fade: float = 1.0  # Opacity curve: above 1 it stays strong longer, then drops off quickly
    angle: float = 0.0  # Facing, for oriented sprites (muzzle flashes)
    variant: str = ""  # Projectile type, for muzzle flashes
    age: float = 0.0

    @property
    def progress(self) -> float:
        return min(1.0, self.age / self.life) if self.life > 0 else 1.0

    def current(self, pair: tuple[float, float]) -> float:
        return pair[0] + (pair[1] - pair[0]) * self.progress

    @property
    def opacity(self) -> float:
        return self.alpha[0] + (self.alpha[1] - self.alpha[0]) * self.progress**self.fade


class BattleEffects:
    """Spawns, moves and draws every particle effect for one battle."""

    def __init__(self, scale: float, fps: int, seed: int = 0):
        self.scale = scale
        self.dt = 1.0 / fps
        self.rng = random.Random(seed)
        self.sprites = EffectSprites(scale)
        self.particles: list[Particle] = []
        # Smoke drifts the same way all battle, like a light breeze across the arena
        self.wind = (self.px(14), self.px(-22))

    def px(self, arena_units: float) -> float:
        return arena_units * self.scale

    def add(self, particle: Particle):
        self.particles.append(particle)

    def update(self):
        """Age and move every particle by one frame, dropping the ones that burned out."""
        dt = self.dt
        alive = []
        for p in self.particles:
            if p.delay > 0:
                p.delay -= dt
                alive.append(p)
                continue
            p.age += dt
            if p.age >= p.life:
                continue
            if p.drag:
                keep = max(0.0, 1.0 - p.drag * dt)
                p.vx *= keep
                p.vy *= keep
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        if len(alive) > MAX_PARTICLES:
            alive = alive[-MAX_PARTICLES:]
        self.particles = alive

    def draw(self, frame: Image.Image, draw: ImageDraw.ImageDraw, layer: int):
        """Draw every live particle on one layer (sparks and debris as lines, the rest as sprites)."""
        sprites = self.sprites
        for p in self.particles:
            if p.layer != layer or p.delay > 0:
                continue
            alpha = p.opacity
            if alpha <= 0.01:
                continue
            if p.kind == "spark":
                tail = 0.035
                draw.line(
                    [(p.x, p.y), (p.x - p.vx * tail, p.y - p.vy * tail)],
                    fill=p.color + (int(255 * alpha),),
                    width=max(1, round(p.current(p.size))),
                )
            elif p.kind == "debris":
                r = max(1.0, p.current(p.size))
                draw.rectangle((p.x - r, p.y - r, p.x + r, p.y + r), fill=p.color + (int(255 * alpha),))
            elif p.kind == "ring":
                paste_centered(frame, sprites.ring(p.current(p.size), self.px(5), p.color, alpha), p.x, p.y)
            elif p.kind == "muzzle":
                paste_centered(frame, sprites.muzzle_flash(p.variant, p.angle, p.size[0]), p.x, p.y)
            elif p.kind == "plus":
                paste_centered(frame, sprites.plus(p.current(p.size), p.color, alpha), p.x, p.y)
            else:
                paste_centered(frame, sprites.blob(p.kind, p.current(p.size), p.color, alpha), p.x, p.y)

    # ── Effect recipes (positions in output pixels, sizes in arena units) ────────

    def muzzle_flash(self, x: float, y: float, angle: float, kind: str):
        """Flame (or glow) at the barrel tip for a couple of frames, with a puff of smoke for big guns."""
        color = FLASH_COLORS.get(kind, FLASH_COLORS["bullet"])
        if kind == "heal":
            self.add(Particle("glow", x, y, life=0.12, size=(self.px(16), self.px(22)), alpha=(0.8, 0), color=color))
            return
        if kind == "shockwave":
            self.add(Particle("glow", x, y, life=0.1, size=(self.px(18), self.px(26)), alpha=(0.7, 0), color=color))
            return
        size = {"bullet": 16, "laser": 18, "cannon": 30, "missile": 26}.get(kind, 16)
        # The cone is a fixed sprite shown for two frames; a glow under it fades a little slower
        self.add(
            Particle("glow", x, y, life=0.1, size=(self.px(size), self.px(size * 1.2)), alpha=(0.6, 0), color=color)
        )
        self.add(Particle("muzzle", x, y, life=0.067, size=(size, size), alpha=(1.0, 1.0), angle=angle, variant=kind))
        if kind in ("cannon", "missile"):
            rad = math.radians(angle)
            for _ in range(2):
                spread = self.rng.uniform(-0.6, 0.6)
                speed = self.px(self.rng.uniform(30, 70))
                self.add(
                    Particle(
                        "smoke",
                        x,
                        y,
                        vx=math.cos(rad + spread) * speed,
                        vy=math.sin(rad + spread) * speed,
                        life=self.rng.uniform(0.4, 0.7),
                        size=(self.px(5), self.px(14)),
                        alpha=(0.35, 0),
                        color=SMOKE_COLOR,
                        drag=3.0,
                    )
                )

    def impact(self, x: float, y: float, kind: str, damage: int, blocked: bool = False):
        """A flash and a spray of sparks where a shot struck a hull."""
        color = (230, 230, 230) if blocked else FLASH_COLORS.get(kind, FLASH_COLORS["bullet"])
        heavy = kind in ("cannon", "shockwave") or damage >= 150
        flash = 22 if heavy else 12
        self.add(
            Particle("glow", x, y, life=0.12, size=(self.px(flash * 1.6), self.px(flash)), alpha=(0.6, 0), color=color)
        )
        self.add(
            Particle(
                "fire", x, y, life=0.1, size=(self.px(flash * 0.6), self.px(flash * 0.3)), alpha=(1.0, 0), color=color
            )
        )
        if kind == "shockwave":
            self.add(Particle("ring", x, y, life=0.2, size=(self.px(10), self.px(42)), alpha=(0.8, 0), color=color))
        elif heavy:
            self.add(Particle("ring", x, y, life=0.18, size=(self.px(8), self.px(30)), alpha=(0.6, 0), color=color))
        for _ in range(7 if heavy else 4):
            heading = self.rng.uniform(0, math.tau)
            speed = self.px(self.rng.uniform(160, 420))
            self.add(
                Particle(
                    "spark",
                    x,
                    y,
                    vx=math.cos(heading) * speed,
                    vy=math.sin(heading) * speed,
                    life=self.rng.uniform(0.12, 0.28),
                    size=(1, 1),
                    alpha=(1.0, 0.0),
                    color=(255, 235, 170) if not blocked else (235, 235, 235),
                    drag=7.0,
                )
            )
        if heavy:
            self.add(
                Particle(
                    "smoke",
                    x,
                    y,
                    vx=self.wind[0],
                    vy=self.wind[1],
                    life=0.6,
                    size=(self.px(6), self.px(18)),
                    alpha=(0.3, 0),
                    color=SMOKE_COLOR,
                )
            )

    def heal_burst(self, x: float, y: float):
        """Green glow and a few '+' signs floating up off the healed bot."""
        color = FLASH_COLORS["heal"]
        self.add(Particle("glow", x, y, life=0.25, size=(self.px(14), self.px(30)), alpha=(0.6, 0), color=color))
        for _ in range(2):
            self.add(
                Particle(
                    "plus",
                    x + self.px(self.rng.uniform(-22, 22)),
                    y + self.px(self.rng.uniform(-14, 14)),
                    vy=-self.px(self.rng.uniform(40, 70)),
                    life=self.rng.uniform(0.5, 0.8),
                    size=(self.px(10), self.px(8)),
                    alpha=(1.0, 0.0),
                    color=(150, 255, 180),
                )
            )

    def explosion(self, x: float, y: float, radius: float, big: bool = False):
        """A fireball with a shock ring, sparks and rolling smoke. `radius` is in arena units."""
        r = self.px(radius)
        rng = self.rng
        # Blinding flash, then a shock ring racing outward
        self.add(Particle("glow", x, y, life=0.18, size=(r * 1.3, r * 1.5), alpha=(0.7, 0), color=(255, 230, 170)))
        self.add(Particle("fire", x, y, life=0.1, size=(r * 0.55, r * 0.8), alpha=(1.0, 0.3), color=(255, 245, 215)))
        self.add(Particle("ring", x, y, life=0.28, size=(r * 0.4, r * 1.3), alpha=(0.8, 0), color=(255, 215, 150)))
        # Billowing fireball: overlapping blobs that swell, cool from yellow to red, then vanish
        palette = [(255, 185, 60), (255, 130, 30), (240, 80, 20)]
        # A missile's blast is kept a little tighter than a bot blowing up (some guns fire four a second)
        swell = 1.0 if big else 0.75
        for i in range(10 if big else 5):
            heading = rng.uniform(0, math.tau)
            dist = rng.uniform(0, r * 0.35)
            speed = rng.uniform(r * 0.6, r * 1.5)
            self.add(
                Particle(
                    "fire",
                    x + math.cos(heading) * dist,
                    y + math.sin(heading) * dist,
                    vx=math.cos(heading) * speed,
                    vy=math.sin(heading) * speed,
                    life=rng.uniform(0.32, 0.55) * (1.2 if big else 1.0),
                    size=(r * swell * rng.uniform(0.28, 0.4), r * swell * rng.uniform(0.5, 0.68)),
                    alpha=(1.0, 0.0),
                    fade=2.2,
                    color=palette[i % len(palette)],
                    drag=5.0,
                    delay=rng.uniform(0, 0.05),
                )
            )
        # Smoke rolls out behind the fire: thick and black when a bot blows up, a light haze for a missile
        for _ in range(8 if big else 2):
            heading = rng.uniform(0, math.tau)
            speed = rng.uniform(r * 0.3, r * 0.8)
            self.add(
                Particle(
                    "smoke",
                    x + math.cos(heading) * r * 0.3,
                    y + math.sin(heading) * r * 0.3,
                    vx=math.cos(heading) * speed + self.wind[0],
                    vy=math.sin(heading) * speed + self.wind[1],
                    life=rng.uniform(1.3, 2.2) if big else rng.uniform(0.6, 0.9),
                    size=(r * 0.4, r * rng.uniform(0.85, 1.15)),
                    alpha=(0.6, 0.0) if big else (0.3, 0.0),
                    color=DARK_SMOKE_COLOR if big else SMOKE_COLOR,
                    drag=1.5,
                    delay=rng.uniform(0.1, 0.22),
                )
            )
        for _ in range(16 if big else 8):
            heading = rng.uniform(0, math.tau)
            speed = rng.uniform(r * 3, r * 7)
            self.add(
                Particle(
                    "spark",
                    x,
                    y,
                    vx=math.cos(heading) * speed,
                    vy=math.sin(heading) * speed,
                    life=rng.uniform(0.2, 0.45),
                    size=(1, 1),
                    alpha=(1.0, 0.0),
                    color=(255, 220, 140),
                    drag=4.0,
                )
            )
        if big:
            # Chunks of hull flung out across the floor
            for _ in range(12):
                heading = rng.uniform(0, math.tau)
                speed = rng.uniform(r * 1.5, r * 4)
                shade = rng.randint(35, 80)
                self.add(
                    Particle(
                        "debris",
                        x,
                        y,
                        vx=math.cos(heading) * speed,
                        vy=math.sin(heading) * speed,
                        life=rng.uniform(0.6, 1.1),
                        size=(rng.uniform(1.0, 1.8), 0.8),
                        alpha=(1.0, 0.0),
                        fade=3.0,
                        color=(shade, shade - 5, shade - 10),
                        drag=5.0,
                        layer=GROUND,
                    )
                )

    def missile_trail(self, x: float, y: float, vx: float, vy: float):
        """Exhaust smoke behind a missile (called once per frame per missile, velocity in output px/s).

        Two puffs per frame, spread over the ground covered since the last frame, keep the trail unbroken.
        """
        speed = math.hypot(vx, vy) or 1.0
        tail = self.px(12)
        tail_x, tail_y = x - vx / speed * tail, y - vy / speed * tail
        for back in (0.0, 0.5):
            self.add(
                Particle(
                    "smoke",
                    tail_x - vx * self.dt * back + self.rng.uniform(-0.6, 0.6),
                    tail_y - vy * self.dt * back + self.rng.uniform(-0.6, 0.6),
                    vx=self.wind[0] * 0.5,
                    vy=self.wind[1] * 0.5,
                    life=self.rng.uniform(0.45, 0.7),
                    size=(self.px(5), self.px(14)),
                    alpha=(0.32, 0.0),
                    color=SMOKE_COLOR,
                    drag=1.0,
                    layer=GROUND,
                )
            )

    def wreck_smoke(self, x: float, y: float, burning: bool):
        """Smoke (and while it's still burning, embers) rising off a destroyed bot."""
        rng = self.rng
        self.add(
            Particle(
                "smoke",
                x + self.px(rng.uniform(-14, 14)),
                y + self.px(rng.uniform(-14, 14)),
                vx=self.wind[0] + self.px(rng.uniform(-8, 8)),
                vy=self.wind[1] + self.px(rng.uniform(-8, 8)),
                life=rng.uniform(1.2, 2.0),
                size=(self.px(8), self.px(rng.uniform(22, 32))),
                alpha=(0.45 if burning else 0.3, 0.0),
                color=DARK_SMOKE_COLOR,
                drag=0.5,
            )
        )
        if not burning:
            return
        # Licks of flame across the hull, and the odd ember carried off on the breeze
        for _ in range(2):
            self.add(
                Particle(
                    "hot",
                    x + self.px(rng.uniform(-18, 18)),
                    y + self.px(rng.uniform(-18, 18)),
                    vx=self.wind[0] * 0.6,
                    vy=self.wind[1] * 0.6,
                    life=rng.uniform(0.2, 0.35),
                    size=(self.px(rng.uniform(6, 9)), self.px(2.5)),
                    alpha=(0.85, 0.0),
                    color=FIRE_COLOR,
                )
            )
        if rng.random() < 0.5:
            self.add(
                Particle(
                    "glow",
                    x + self.px(rng.uniform(-16, 16)),
                    y + self.px(rng.uniform(-16, 16)),
                    vx=self.wind[0] * 1.5,
                    vy=self.wind[1] * 1.5,
                    life=rng.uniform(0.4, 0.7),
                    size=(self.px(3), self.px(1.5)),
                    alpha=(1.0, 0.0),
                    color=(255, 170, 60),
                )
            )

    def draw_projectile(self, frame: Image.Image, proj: dict, x: float, y: float):
        """Draw one projectile in flight at output position (x, y)."""
        kind = proj.get("projectile_type") or "bullet"
        if proj.get("is_heal"):
            kind = "heal"
        angle = math.degrees(math.atan2(proj.get("vy", 0.0), proj.get("vx", 1.0)))
        if kind == "shockwave":
            # The pressure wave widens and thins out as it travels
            age = proj.get("age", 0.0)
            radius = self.px(16 + age * 260)
            alpha = max(0.0, 0.95 - age * 5)
            paste_centered(frame, self.sprites.crescent(radius, FLASH_COLORS["shockwave"], alpha, angle), x, y)
            return
        if kind not in TRACERS:
            kind = "bullet"
        paste_centered(frame, self.sprites.tracer(kind, angle), x, y)
        if kind in ("cannon", "heal"):
            # A round glowing orb at the head
            orb = 9 if kind == "cannon" else 7
            paste_centered(frame, self.sprites.blob("hot", self.px(orb), TRACERS[kind]["glow"], 1.0), x, y)
        elif kind == "missile":
            # Flickering exhaust flame behind the warhead
            rad = math.radians(angle)
            flame = self.px(self.rng.uniform(7, 11))
            paste_centered(
                frame,
                self.sprites.blob("hot", flame, FIRE_COLOR, 0.9),
                x - math.cos(rad) * self.px(12),
                y - math.sin(rad) * self.px(12),
            )
