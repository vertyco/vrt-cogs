import logging
import math
import random
import typing as t
from io import BytesIO
from pathlib import Path
from typing import Union

import colorgram
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageSequence
from redbot.core.i18n import Translator

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "data"
DEFAULT_BACKGROUNDS = ASSETS / "backgrounds"
DEFAULT_FONTS = ASSETS / "fonts"
DEFAULT_FONT = DEFAULT_FONTS / "BebasNeue.ttf"
STOCK = ASSETS / "stock"
STAR = Image.open(STOCK / "star.webp")
DEFAULT_PFP = Image.open(STOCK / "defaultpfp.webp")
RS_TEMPLATE = Image.open(STOCK / "runescapeui_nogold.webp")
RS_TEMPLATE_BALANCE = Image.open(STOCK / "runescapeui_withgold.webp")
COLORTABLE = STOCK / "colortable.webp"
STATUS = {
    "online": Image.open(STOCK / "online.webp"),
    "offline": Image.open(STOCK / "offline.webp"),
    "idle": Image.open(STOCK / "idle.webp"),
    "dnd": Image.open(STOCK / "dnd.webp"),
    "streaming": Image.open(STOCK / "streaming.webp"),
}

log = logging.getLogger("red.vrt.levelup.imagetools")
_ = Translator("LevelUp", __file__)


def download_image(url: str) -> t.Union[bytes, None]:
    """Get an image from a URL"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content
    except requests.HTTPError as e:
        log.warning(f"Failed to download image URL: {url}\n{e}")
        return None
    except Exception as e:
        log.error(f"Failed to download image URL: {url}", exc_info=e)
        return None


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


def make_profile_circle(
    pfp: Image.Image,
    method: Image.Resampling = Image.Resampling.LANCZOS,
) -> Image.Image:
    """Crop an image into a circle"""
    # Create a mask at 4x size (So we can scale down to smooth the edges later)
    mask = Image.new("L", (pfp.width * 4, pfp.height * 4), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, mask.width, mask.height), fill=255)
    # Resize the mask to the image size
    mask = mask.resize(pfp.size, method)
    # Apply the mask
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


def clean_gif_frame(image: Image.Image) -> Image.Image:
    """Clean up a GIF frame"""
    alpha = image.getchannel("A")
    mask = Image.eval(alpha, lambda a: 255 if a > 128 else 0)
    image.putalpha(mask)
    return image


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


def get_avg_duration(image: Image.Image) -> int:
    """Get the average duration of a GIF"""
    if not getattr(image, "is_animated", False):
        log.warning("Image is not animated")
        return 0

    try:
        durations = [frame.info["duration"] for frame in ImageSequence.Iterator(image)]
        # durations = []
        # for frame in range(1, image.n_frames):
        #     image.seek(frame)
        #     durations.append(image.info.get("duration", 0))
        return sum(durations) // len(durations)
    except Exception as e:
        log.error("Failed to get average duration of GIF", exc_info=e)
        return 0


if __name__ == "__main__":
    print(calc_aspect_ratio(200, 70))
