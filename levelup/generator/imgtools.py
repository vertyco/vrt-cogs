import bisect
import functools
import logging
import math
import random
import typing as t
from io import BytesIO
from pathlib import Path
from typing import Union

import colorgram
import requests
from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageSequence,
    ImageStat,
    UnidentifiedImageError,
)
from redbot.core.i18n import Translator

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "data"
DEFAULT_BACKGROUNDS = ASSETS / "backgrounds"
DEFAULT_FONTS = ASSETS / "fonts"
DEFAULT_FONT = DEFAULT_FONTS / "BebasNeue.ttf"
STOCK = ASSETS / "stock"


def _load_stock(name: str) -> Image.Image:
    # Decode up front, Pillow's lazy loading on first use isn't safe when renders run in parallel threads
    image = Image.open(STOCK / name)
    image.load()
    return image


STAR = _load_stock("star.webp")
DEFAULT_PFP = _load_stock("defaultpfp.webp")
RS_TEMPLATE = _load_stock("runescapeui_nogold.webp")
RS_TEMPLATE_BALANCE = _load_stock("runescapeui_withgold.webp")
COLORTABLE = STOCK / "colortable.webp"
STATUS = {
    "online": _load_stock("online.webp"),
    "offline": _load_stock("offline.webp"),
    "idle": _load_stock("idle.webp"),
    "dnd": _load_stock("dnd.webp"),
    "streaming": _load_stock("streaming.webp"),
}

# GIF frame delays are stored in 10ms steps, and browsers (so Discord too) play any delay of 10ms or less at 100ms
GIF_MIN_FRAME_MS = 20
GIF_SLOW_FRAME_MS = 100
# Most frames an animation can have, faster frames get merged past this to keep the file size sane
MAX_ANIMATION_FRAMES = 120
MIN_ANIMATION_FRAMES = 12
# Animations bigger than this get re-rendered with fewer frames
MAX_GIF_BYTES = 8 * 1024 * 1024
# How much each animation may be sped up or slowed down so two animations can loop together seamlessly
MAX_SYNC_STRETCH = 0.05
# Longest loop to consider when lining up two animations of different lengths
MAX_ANIMATION_LOOP_MS = 10_000
# Memory budget per layer for caching prepared animation frames
LAYER_CACHE_BYTES = 64 * 1024 * 1024
# Frames where less than this much of the area changed reuse the previous frame's palette
MAX_PARTIAL_FRAME_AREA = 0.5
_ALPHA_LUT = [255 if a >= 128 else 0 for a in range(256)]

log = logging.getLogger("red.vrt.levelup.imagetools")
_ = Translator("LevelUp", __file__)


def download_image(url: str) -> t.Union[bytes, None]:
    """Get an image from a URL"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        content = response.content
        # A 200 does not guarantee an image: Discord's CDN can return an HTML/text body
        # for expired or unavailable assets. Shipping that downstream produces a broken
        # image (Discord rejects it with HTTP 415 "failed to get asset"), so validate here.
        try:
            Image.open(BytesIO(content)).verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as e:
            log.warning(f"URL returned non-image content ({len(content)} bytes): {url} ({e})")
            return None
        return content
    except requests.HTTPError as e:
        log.warning(f"Failed to download image URL: {url}\n{e}")
        return None
    except Exception as e:
        log.error(f"Failed to download image URL: {url}", exc_info=e)
        return None


def open_avatar(avatar_bytes: t.Union[bytes, str, None]) -> Image.Image:
    """Open avatar bytes (or a URL) as a PIL image, falling back to the default pfp on missing/invalid data.

    Guards every profile/levelup style against avatars that are absent or not a real image
    (expired CDN response, truncated download). Without this a non-image avatar would raise
    or be shipped to Discord as a broken asset (HTTP 415 "failed to get asset").
    """
    if isinstance(avatar_bytes, str):
        avatar_bytes = download_image(avatar_bytes) if avatar_bytes.startswith("http") else None
    if avatar_bytes:
        try:
            pfp = Image.open(BytesIO(avatar_bytes))
            pfp.load()  # force-decode now so bad bytes fail here, not deep in the render
            return pfp
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, TypeError) as e:
            log.warning(f"Avatar was not a valid image ({len(avatar_bytes)} bytes); using default pfp: {e}")
    return DEFAULT_PFP.copy()


def abbreviate_number(number: int) -> str:
    """Abbreviate a number"""
    abbreviations = [(1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")]
    for num, abbrev in abbreviations:
        if number >= num:
            return f"{number // num}{abbrev}"
    return str(number)


def abbreviate_time(delta: int, short: bool = False) -> str:
    """Format time in seconds into an extra short human readable string"""
    s = int(delta)
    m, s = divmod(delta, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    y, d = divmod(d, 365)

    if not any([s, m, h, d, y]):
        return _("None")
    if not any([m, h, d, y]):
        if short:
            return f"{int(s)}S"
        return f"{int(s)}s"
    if not any([h, d, y]):
        if short:
            return f"{int(m)}M"
        return f"{int(m)}m {int(s)}s"
    if not any([d, y]):
        if short:
            return f"{int(h)}H"
        return f"{int(h)}h {int(m)}m"
    if not y:
        if short:
            return f"{int(d)}D"
        return f"{int(d)}d {int(h)}h"
    if short:
        return f"{int(y)}Y"
    return f"{int(y)}y {int(d)}d"


def make_circle_outline(thickness: int, color: tuple) -> Image.Image:
    """Make a transparent circle"""
    size = (1080, 1080)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size[0], size[1]), outline=color, width=thickness * 3)
    return img


@functools.lru_cache(maxsize=16)
def _circle_mask(size: t.Tuple[int, int], method: Image.Resampling) -> Image.Image:
    # Draw the mask at 4x size so scaling it down smooths the edges
    mask = Image.new("L", (size[0] * 4, size[1] * 4), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, mask.width, mask.height), fill=255)
    return mask.resize(size, method)


def make_profile_circle(
    pfp: Image.Image,
    method: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    """Crop an image into a circle"""
    mask = _circle_mask(pfp.size, method)
    if pfp.mode == "RGBA":
        # Keep any transparency the avatar already has
        mask = ImageChops.multiply(pfp.getchannel("A"), mask)
    pfp.putalpha(mask)
    return pfp


def get_rounded_corner_mask(image: Image.Image, radius: int) -> Image.Image:
    """Get a mask for rounded corners"""
    mask = Image.new("L", (image.width * 4, image.height * 4), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, mask.width, mask.height),
        fill=255,
        radius=radius * 4,
    )
    mask = mask.resize(image.size, Image.Resampling.LANCZOS)
    return mask


def round_image_corners(image: Image.Image, radius: int) -> Image.Image:
    mask = get_rounded_corner_mask(image, radius)
    image.putalpha(mask)
    return image


def blur_section(image: Image.Image, bbox: t.Tuple[int, int, int, int]) -> Image.Image:
    """Blur a section of an image"""
    section = image.crop(bbox)
    section = section.filter(ImageFilter.GaussianBlur(3))
    # Darken the image
    section = ImageEnhance.Brightness(section).enhance(0.8)
    return section


def make_progress_bar(
    width: int,
    height: int,
    progress: float,  # 0.0 - 1.0
    color: t.Tuple[int, int, int] = None,
    background_color: t.Tuple[int, int, int] = None,
) -> Image.Image:
    """Make a pretty rounded progress bar."""
    if not color:
        # White
        color = (255, 255, 255)
    if not background_color:
        # Dark grey
        background_color = (100, 100, 100)
    # Ensure progress is within 0.0 - 1.0
    progress = max(0.0, min(1.0, progress))
    scale = 4
    scaled_width = width * scale
    scaled_height = height * scale
    radius = scaled_height // 2
    img = Image.new("RGBA", (scaled_width, scaled_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Draw the progress
    if progress > 0:
        # Length of progress bar
        bar_length = int(scaled_width * progress)
        # Draw the rounded rectangle for the progress
        draw.rounded_rectangle([(0, 0), (max(bar_length, scaled_height), scaled_height)], radius, fill=color)

    # Draw the background (empty bar)
    placement = [(0, 0), (scaled_width, scaled_height)]
    draw.rounded_rectangle(placement, radius, outline=background_color, width=scale * 4)

    # Scale down to smooth edges
    img = img.resize((width, height), resample=Image.Resampling.LANCZOS)
    return img


def format_fonts(filepaths: t.List[str]) -> Image.Image:
    """Format fonts into an image"""
    filepaths.sort(key=lambda x: Path(x).stem)
    count = len(filepaths)
    fontsize = 50
    img = Image.new("RGBA", (650, fontsize * count + (count * 15)), 0)
    color = (255, 255, 255)
    draw = ImageDraw.Draw(img)
    for idx, path in enumerate(filepaths):
        font = ImageFont.truetype(path, fontsize)
        draw.text((5, idx * (fontsize + 15)), Path(path).stem, color, font=font, stroke_width=1, stroke_fill=(0, 0, 0))
    return img


def format_backgrounds(filepaths: t.List[str]) -> Image.Image:
    """Format backgrounds into an image"""
    filepaths.sort(key=lambda x: Path(x).stem)
    images: t.List[t.Tuple[Image.Image, str]] = []
    for path in filepaths:
        if Path(path).suffix.endswith(("py", "pyc")):
            continue
        if Path(path).is_dir():
            continue
        try:
            img = Image.open(path)
            img = fit_aspect_ratio(img, (1050, 450))
            # Resize so all images are the same width
            new_w, new_h = 1000, int(img.height / img.width * 1000)
            img = img.resize((new_w, new_h), Image.Resampling.NEAREST)
            draw = ImageDraw.Draw(img)
            name = Path(path).stem
            draw.text(
                (10, 10),
                name,
                font=ImageFont.truetype(str(DEFAULT_FONT), 100),
                fill=(255, 255, 255),
                stroke_width=5,
                stroke_fill="#000000",
            )
            if not img:
                log.error(f"Failed to load image for default background '{path}`")
                continue
            images.append((img, Path(path).name))
        except Exception as e:
            log.warning(f"Failed to prep background image: {path}", exc_info=e)

    # Merge the images into a single image and try to make it even
    # It can be a little taller than wide
    rowcount = math.ceil(len(images) ** 0.35)
    colcount = math.ceil(len(images) / rowcount)
    max_height = max(images, key=lambda x: x[0].height)[0].height
    width = 1000 * rowcount
    height = max_height * colcount
    new = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for idx, (img, name) in enumerate(images):
        x = 1000 * (idx % rowcount)
        y = max_height * (idx // rowcount)
        new.paste(img, (x, y))
    return new


def concat_img_v(im1: Image, im2: Image) -> Image.Image:
    """Merge two images vertically"""
    new = Image.new("RGBA", (im1.width, im1.height + im2.height))
    new.paste(im1, (0, 0))
    new.paste(im2, (0, im1.height))
    return new


def concat_img_h(im1: Image, im2: Image) -> Image.Image:
    """Merge two images horizontally"""
    new = Image.new("RGBA", (im1.width + im2.width, im1.height))
    new.paste(im1, (0, 0))
    new.paste(im2, (im1.width, 0))
    return new


def get_img_colors(
    img: Union[Image.Image, str, bytes, BytesIO],
    amount: int,
) -> t.List[t.Tuple[int, int, int]]:
    """Extract colors from an image using colorgram.py"""
    try:
        colors = colorgram.extract(img, amount)
        extracted = [color.rgb for color in colors]
        return extracted
    except Exception as e:
        log.error("Failed to extract image colors", exc_info=e)
        extracted: t.List[t.Tuple[int, int, int]] = [(0, 0, 0) for _ in range(amount)]
        return extracted


def distance(color1: t.Tuple[int, int, int], color2: t.Tuple[int, int, int]) -> float:
    """Calculate the Euclidean distance between two RGB colors"""
    # Values
    x1, y1, z1 = color1
    x2, y2, z2 = color2
    # Distances
    dx = x1 - x2
    dy = y1 - y2
    dz = z1 - z2
    # Final distance
    return math.sqrt(dx**2 + dy**2 + dz**2)


def inv_rgb(rgb: t.Tuple[int, int, int]) -> t.Tuple[int, int, int]:
    """Invert an RGB color tuple"""
    return 255 - rgb[0], 255 - rgb[1], 255 - rgb[2]


def rand_rgb() -> t.Tuple[int, int, int]:
    """Generate a random RGB color tuple"""
    r = random.randint(0, 256)
    g = random.randint(0, 256)
    b = random.randint(0, 256)
    return r, g, b


def calc_aspect_ratio(width: int, height: int) -> t.Tuple[int, int]:
    """Calculate the aspect ratio of an image"""
    divisor = math.gcd(width, height)
    return width // divisor, height // divisor


def fit_aspect_ratio(
    image: Image.Image,
    desired_size: t.Tuple[int, int],  # (1050, 450)
    preserve: bool = False,
    method: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    """
    Crop image to fit aspect ratio

    We will either need to chop off the sides or chop off the top and bottom (or add transparent space)

    Args:
        image (Image): Image to fit
        aspect_ratio (t.Tuple[int, int], optional): Fit the image to the aspect ratio. Defaults to (21, 9).
        preserve (bool, optional): Rather than cropping, add transparent space. Defaults to False.

    Returns:
        Image
    """
    # If the image is already the correct size, return it
    if image.size == desired_size:
        return image

    if preserve:
        # Rather than cropping, add transparent space
        new = Image.new("RGBA", desired_size, (0, 0, 0, 0))
        x = (desired_size[0] - image.width) // 2
        y = (desired_size[1] - image.height) // 2
        new.paste(image, (x, y))
        return new
    else:
        # Crop the image to fit the aspect ratio
        aspect_ratio = calc_aspect_ratio(*desired_size)
        if image.width / image.height > aspect_ratio[0] / aspect_ratio[1]:
            # Image is wider than desired aspect ratio
            new_width = image.height * aspect_ratio[0] // aspect_ratio[1]
            x = (image.width - new_width) // 2
            y = 0
            image = image.crop((x, y, x + new_width, image.height))
        else:
            # Image is taller than desired aspect ratio
            new_height = image.width * aspect_ratio[1] // aspect_ratio[0]
            x = 0
            y = (image.height - new_height) // 2
            image = image.crop((x, y, image.width, y + new_height))
        return image.resize(desired_size, method)


def get_random_background() -> Image.Image:
    """Get a random background image"""
    files = list(DEFAULT_BACKGROUNDS.glob("*.webp"))
    if not files:
        raise FileNotFoundError("No background images found")
    return Image.open(random.choice(files))


def get_frame_durations(image: Image.Image) -> t.List[int]:
    """Get how long each frame of an animated image shows for, in milliseconds.

    Delays of 10ms or less are counted as 100ms, since that is how browsers (and Discord) play them.
    """
    durations: t.List[int] = []
    for frame in ImageSequence.Iterator(image):
        duration = round(frame.info.get("duration") or 0)
        durations.append(duration if duration > 10 else GIF_SLOW_FRAME_MS)
    image.seek(0)
    return durations


def sync_animations(
    *layers: t.Optional[t.Sequence[int]],
    max_frames: t.Optional[int] = None,
) -> t.List[t.Tuple[int, t.Tuple[int, ...]]]:
    """Line up the frames of one or more animated layers on a single timeline.

    Each layer keeps its own frame timing, and every layer plays a whole number of loops per output loop
    so the result loops seamlessly. When the loop lengths don't divide evenly, each layer gets sped up or
    slowed down a little to make them fit: by at most MAX_SYNC_STRETCH, unless that would need a loop too
    long for the frame budget, in which case the closest fit within budget is used.

    Args:
        *layers: Frame durations (ms) of each layer, or None for a static layer.
        max_frames: Most frames to output, defaults to MAX_ANIMATION_FRAMES. Past this, frame changes
            that land close together get merged, lowering the frame rate but keeping the speed.

    Returns:
        A list of (duration_ms, frame index of each layer) for every output frame.
    """
    max_frames = max_frames or MAX_ANIMATION_FRAMES
    animated = {i: list(durations) for i, durations in enumerate(layers) if durations}
    if not animated:
        return [(GIF_SLOW_FRAME_MS, (0,) * len(layers))]
    loops = {i: sum(durations) for i, durations in animated.items()}

    # Find the shortest loop that every layer can repeat a whole number of times within. Longer loops
    # line up better but cost more frames, so stop looking once a loop would blow the frame budget.
    longest = max(loops.values())
    best: t.Optional[t.Tuple[float, t.Dict[int, int], float]] = None
    reps = 1
    while reps == 1 or longest * reps <= MAX_ANIMATION_LOOP_MS:
        counts = {i: max(1, round(longest * reps / loop)) for i, loop in loops.items()}
        if reps > 1 and sum(counts[i] * len(animated[i]) for i in animated) > max_frames:
            break
        spans = [counts[i] * loop for i, loop in loops.items()]
        average = sum(spans) / len(spans)
        stretch = max(abs(span / average - 1) for span in spans)
        if best is None or stretch < best[0]:
            best = (stretch, counts, average)
        if stretch <= MAX_SYNC_STRETCH:
            break
        reps += 1
    stretch, counts, average = best
    total_ms = max(GIF_MIN_FRAME_MS, round(average / 10) * 10)

    # When each layer's frames start on the output clock
    starts: t.Dict[int, t.List[float]] = {}
    for i, durations in animated.items():
        scale = total_ms / (counts[i] * loops[i])
        layer_starts: t.List[float] = []
        elapsed = 0
        for _ in range(counts[i]):
            for duration in durations:
                layer_starts.append(elapsed * scale)
                elapsed += duration
        starts[i] = layer_starts

    # Output a frame whenever any layer changes, snapped to the 10ms steps GIF delays use
    cuts = sorted({round(start / 10) * 10 for layer_starts in starts.values() for start in layer_starts})
    min_gap = GIF_MIN_FRAME_MS
    if len(animated) > 1:
        # Layers changing less than half a frame apart can share an output frame without looking off
        fastest = min(sorted(durations)[len(durations) // 2] for durations in animated.values())
        min_gap = max(min_gap, fastest // 20 * 10)
    while True:
        bounds = [0]
        for cut in cuts:
            if cut - bounds[-1] >= min_gap and total_ms - cut >= min_gap:
                bounds.append(cut)
        if len(bounds) <= max_frames:
            break
        # Too many frames, merge changes that land close together
        min_gap += 10
    bounds.append(total_ms)

    # Show whichever frame each layer is on halfway through every output frame
    timeline: t.List[t.Tuple[int, t.Tuple[int, ...]]] = []
    for start, end in zip(bounds, bounds[1:]):
        middle = (start + end) / 2
        indexes = tuple(
            (bisect.bisect_right(starts[i], middle) - 1) % len(animated[i]) if i in animated else 0
            for i in range(len(layers))
        )
        if timeline and timeline[-1][1] == indexes:
            timeline[-1] = (timeline[-1][0] + end - start, indexes)
        else:
            timeline.append((end - start, indexes))

    log.debug(
        f"Synced layer loops {list(loops.values())}ms x {list(counts.values())} into {total_ms}ms "
        f"({stretch:.1%} stretch), {len(timeline)} frames"
    )
    return timeline


class AnimationLayer:
    """A layer of an animated render (background, avatar...) that prepares each source frame on demand.

    Prepared frames are cached within a memory budget, so a layer that loops several times in the
    output, or stays on one frame while another layer animates, is only processed once per frame.
    """

    def __init__(self, image: Image.Image, prepare: t.Callable[[Image.Image], Image.Image]):
        self.image = image
        self.prepare = prepare
        self.animated = bool(getattr(image, "is_animated", False))
        self.durations = get_frame_durations(image) if self.animated else None
        self._cache: t.Dict[int, Image.Image] = {}
        self._cache_bytes = 0
        self._last: t.Optional[t.Tuple[int, Image.Image]] = None

    def get(self, index: int) -> Image.Image:
        """Get the prepared frame at an index, the returned image must not be modified"""
        index = index if self.animated else 0
        if index in self._cache:
            return self._cache[index]
        if self._last and self._last[0] == index:
            return self._last[1]
        if self.animated:
            self.image.seek(index)
        frame = self.prepare(self.image.convert("RGBA"))
        size = frame.width * frame.height * len(frame.getbands())
        if self._cache_bytes + size <= LAYER_CACHE_BYTES:
            self._cache[index] = frame
            self._cache_bytes += size
        self._last = (index, frame)
        return frame


def _color_error(image: Image.Image, other: Image.Image) -> float:
    """Average difference per color channel (0-255) between two RGB images"""
    channels = ImageStat.Stat(ImageChops.difference(image, other)).mean
    return sum(channels) / len(channels)


class _PaletteReuse:
    """Redraws part of a GIF frame with the palette of the last fully quantized (key) frame"""

    def __init__(self, source: Image.Image, keyframe: Image.Image):
        self.source = source.convert("RGB")
        self.keyframe = keyframe
        self.transparency: t.Optional[int] = keyframe.info.get("transparency")
        colors = keyframe.palette.colors if keyframe.palette else {}
        # Look colors up among the opaque entries only, so black never lands on the transparent slot
        opaque = [index for index in colors.values() if index != self.transparency]
        rgb = keyframe.getpalette("RGB") or []
        self.lookup = Image.new("P", (1, 1))
        self.lookup.putpalette([c for index in opaque for c in rgb[index * 3 : index * 3 + 3]])
        self.to_index = opaque + [0] * (256 - len(opaque))

    def patch(
        self,
        base: Image.Image,
        frame: Image.Image,
        alpha: Image.Image,
        bbox: t.Tuple[int, int, int, int],
    ) -> t.Optional[Image.Image]:
        """Copy base (a frame on this palette) with the bbox redrawn from frame, or None if the palette is a poor fit"""
        region_alpha = alpha.crop(bbox)
        clear = region_alpha.getextrema()[0] == 0
        if clear and self.transparency is None:
            return None
        region = frame.crop(bbox).convert("RGB")
        mapped = region.quantize(palette=self.lookup, dither=Image.Dither.NONE)
        # New colors may have shown up that the palette doesn't cover, so allow a bit more error
        # than the palette had for this same area of the frame it was made for, but no more
        baseline = _color_error(self.source.crop(bbox), self.keyframe.crop(bbox).convert("RGB"))
        if _color_error(region, mapped.convert("RGB")) > baseline * 1.25 + 1:
            return None
        patch = mapped.point(self.to_index)
        if clear:
            patch.paste(self.transparency, mask=ImageOps.invert(region_alpha))
        result = base.copy()
        result.paste(patch, bbox[:2])
        return result


def save_gif(frames: t.Iterable[Image.Image], durations: t.Sequence[int]) -> bytes:
    """Encode frames as a looping GIF.

    Frames are converted to a palette as they come in, so pass a generator to avoid holding every
    full color frame in memory at once.
    """
    palette_frames: t.List[Image.Image] = []
    first_alpha: t.Optional[bytes] = None
    steady = True
    previous: t.Optional[Image.Image] = None
    reuse: t.Optional[_PaletteReuse] = None
    for frame in frames:
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")
        # GIF transparency is all or nothing, so make every pixel fully opaque or fully clear
        alpha = frame.getchannel("A").point(_ALPHA_LUT)
        frame = Image.composite(frame, Image.new("RGBA", frame.size), alpha)
        frame.putalpha(alpha)

        palette_frame = None
        if previous is not None and reuse is not None:
            bbox = ImageChops.difference(frame, previous).getbbox(alpha_only=False)
            if bbox is None:
                palette_frame = palette_frames[-1]
            elif (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) <= frame.width * frame.height * MAX_PARTIAL_FRAME_AREA:
                # Only part of the frame changed (like just the avatar), so redraw that part with the last
                # palette. A fresh palette would shift colors all over the frame and they'd all need storing.
                palette_frame = reuse.patch(palette_frames[-1], frame, alpha, bbox)
        if palette_frame is None:
            # A fast octree palette per frame keeps files far smaller than median cut for similar quality.
            # One slot is left free so unchanged pixels can be marked transparent even if nothing else is.
            palette_frame = frame.quantize(colors=255, method=Image.Quantize.FASTOCTREE)
            for color, index in palette_frame.palette.colors.items():
                if len(color) == 4 and color[3] == 0:
                    palette_frame.info["transparency"] = index
                    break
            reuse = _PaletteReuse(frame, palette_frame)
        previous = frame

        alpha_bytes = alpha.tobytes()
        if first_alpha is None:
            first_alpha = alpha_bytes
        elif alpha_bytes != first_alpha:
            steady = False
        palette_frames.append(palette_frame)

    # Pixels that match the previous frame get stored as transparent so each frame only holds what changed.
    # That relies on transparent areas staying put, if they move each frame must clear the last one instead.
    buffer = BytesIO()
    palette_frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=[max(GIF_MIN_FRAME_MS, round(d / 10) * 10) for d in durations],
        loop=0,
        optimize=True,
        disposal=1 if steady else 2,
    )
    return buffer.getvalue()


def render_animation(
    layers: t.Sequence["AnimationLayer"],
    render_frame: t.Callable[[t.Tuple[int, ...]], Image.Image],
    max_bytes: int = MAX_GIF_BYTES,
) -> bytes:
    """Play animated layers together and encode the result as a looping GIF.

    Args:
        layers: The layers that make up each frame, static ones included.
        render_frame: Composites one output frame from the frame index of each layer.
        max_bytes: Size to stay under, frames get merged and the GIF re-rendered if it comes out bigger.
    """
    max_frames = MAX_ANIMATION_FRAMES
    for _ in range(3):
        timeline = sync_animations(*[layer.durations for layer in layers], max_frames=max_frames)
        frames = (render_frame(indexes) for _, indexes in timeline)
        data = save_gif(frames, [duration for duration, _ in timeline])
        if len(data) <= max_bytes or len(timeline) <= MIN_ANIMATION_FRAMES:
            break
        # Size grows about linearly with the frame count
        max_frames = max(MIN_ANIMATION_FRAMES, int(len(timeline) * max_bytes / len(data) * 0.9))
        log.debug(f"Animation came out {len(data)} bytes with {len(timeline)} frames, retrying with {max_frames}")
    return data


def shrink_animation(image: Image.Image, max_bytes: int, scale: float, frame_step: int) -> t.Optional[bytes]:
    """Try to shrink an animated image under a target byte size."""
    if not getattr(image, "is_animated", False):
        return None

    source_durations = get_frame_durations(image)
    frames: t.List[Image.Image] = []
    durations: t.List[int] = []

    for start in range(0, len(source_durations), frame_step):
        image.seek(start)
        frame = image.convert("RGBA")
        if scale != 1.0:
            width = max(1, round(frame.width * scale))
            height = max(1, round(frame.height * scale))
            frame = frame.resize((width, height), Image.Resampling.LANCZOS)
        frames.append(frame)
        # Dropped frames hand their time to the frame before them so the speed stays the same
        durations.append(sum(source_durations[start : start + frame_step]))

    if len(frames) < 2:
        return None

    data = save_gif(frames, durations)
    if len(data) <= max_bytes:
        return data
    return None


def make_static_image(image: Image.Image, max_bytes: int) -> t.Optional[bytes]:
    """Convert the first frame into a smaller static WEBP if needed."""
    image.seek(0)
    base = image.convert("RGBA")
    scales = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4)
    qualities = (95, 90, 85, 80, 75, 70, 65)

    for scale in scales:
        frame = base
        if scale != 1.0:
            width = max(1, round(base.width * scale))
            height = max(1, round(base.height * scale))
            frame = base.resize((width, height), Image.Resampling.LANCZOS)

        for quality in qualities:
            buffer = BytesIO()
            frame.save(buffer, format="WEBP", quality=quality, method=6)
            data = buffer.getvalue()
            if len(data) <= max_bytes:
                return data

    return None


def fit_discord_upload_limit(image_bytes: bytes, file_size_limit: int) -> t.Tuple[bytes, bool, str]:
    """Shrink oversized animated images, then fall back to a static WEBP if needed."""
    if not image_bytes:
        return image_bytes, False, "webp"

    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception as e:
        log.warning("Failed to inspect generated image size", exc_info=e)
        return image_bytes, False, "webp"

    animated = bool(getattr(image, "is_animated", False))
    ext = "gif" if animated else "webp"
    if not file_size_limit or file_size_limit <= 0:
        return image_bytes, animated, ext

    safety_margin = min(16 * 1024, max(1024, file_size_limit // 50))
    max_bytes = max(1, file_size_limit - safety_margin)
    if len(image_bytes) <= max_bytes or not animated:
        return image_bytes, animated, ext

    scales = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4)
    frame_steps = (1, 2, 3, 4, 5)
    # File size roughly follows pixel count and frame count, so skip attempts that clearly can't fit
    # rather than re-encoding the whole animation for each one
    needed = max_bytes / len(image_bytes)

    for frame_step in frame_steps:
        for scale in scales:
            if scale * scale / frame_step > needed * 1.5:
                continue
            if shrunk := shrink_animation(image, max_bytes, scale, frame_step):
                return shrunk, True, "gif"

    if static_image := make_static_image(image, max_bytes):
        return static_image, False, "webp"

    return image_bytes, animated, ext


if __name__ == "__main__":
    print(calc_aspect_ratio(200, 70))
