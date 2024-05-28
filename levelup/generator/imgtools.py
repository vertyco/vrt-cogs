import logging
import math
import random
import typing as t
from io import BytesIO
from pathlib import Path
from typing import Union

import colorgram
from PIL import Image, ImageDraw, ImageFont
from redbot.core.i18n import Translator

ASSETS = Path(__file__).parent.parent / "data"
DEFAULT_BACKGROUNDS = ASSETS / "backgrounds"
DEFAULT_FONTS = ASSETS / "fonts"
DEFAULT_FONT = DEFAULT_FONTS / "BebasNeue.ttf"
STOCK = ASSETS / "stock"


log = logging.getLogger("red.vrt.levelup.imagetools")
_ = Translator("LevelUp", __file__)


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
            img = fit_aspect_ratio(img)
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
    image: Image,
    aspect_ratio: t.Tuple[int, int] = (21, 9),
    preserve: bool = False,
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
    width, height = image.size
    new_aspect_x, new_aspect_y = aspect_ratio

    if preserve:
        # Rather than cropping, add transparent space
        if width / new_aspect_x < height / new_aspect_y:
            # Image is too tall, add space to left and right
            new_width = int(height * new_aspect_x / new_aspect_y)
            left_bound = (new_width - width) // 2
            right_bound = left_bound + width
            new_image = Image.new("RGBA", (new_width, height), (0, 0, 0, 0))
            new_image.paste(image, (left_bound, 0))
            return new_image
        else:
            # Image is too wide, add space to top and bottom
            new_height = int(width * new_aspect_y / new_aspect_x)
            upper_bound = (new_height - height) // 2
            lower_bound = upper_bound + height
            new_image = Image.new("RGBA", (width, new_height), (0, 0, 0, 0))
            new_image.paste(image, (0, upper_bound))
            return new_image

    # We need to chop off either the top and bottom or the sides
    if width / new_aspect_x < height / new_aspect_y:
        # Image is too tall, chop off the top and bottom evenly
        new_height = int(width * new_aspect_y / new_aspect_x)
        upper_bound = (height - new_height) // 2
        lower_bound = upper_bound + new_height
        return image.crop((0, upper_bound, width, lower_bound))
    else:
        # Image is too wide, chop off the sides evenly
        new_width = int(height * new_aspect_x / new_aspect_y)
        left_bound = (width - new_width) // 2
        right_bound = left_bound + new_width
        return image.crop((left_bound, 0, right_bound, height))


def get_random_background() -> Image.Image:
    """Get a random background image"""
    files = list(DEFAULT_BACKGROUNDS.glob("*.webp"))
    if not files:
        raise FileNotFoundError("No background images found")
    return Image.open(random.choice(files))


if __name__ == "__main__":
    print(calc_aspect_ratio(200, 70))
