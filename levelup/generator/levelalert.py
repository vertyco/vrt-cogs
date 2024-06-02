"""Generate LevelUp Image

Args:
    background (t.Optional[bytes], optional): The background image as bytes. Defaults to None.
    avatar (t.Optional[bytes], optional): The avatar image as bytes. Defaults to None.
    level (t.Optional[int], optional): The level number. Defaults to 1.
    color (t.Optional[t.Tuple[int, int, int]], optional): The color of the level text as a tuple of RGB values. Defaults to None.
    font (t.Optional[t.Union[str, Path]], optional): The path to the font file or the name of the font. Defaults to None.
    debug (t.Optional[bool], optional): Whether to show the generated image for debugging purposes. Defaults to False.

Returns:
    bytes: The generated image as bytes.
"""

import logging
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from redbot.core.i18n import Translator

try:
    from . import imgtools
except ImportError:
    import imgtools

log = logging.getLogger("red.vrt.levelup.generator.levelalert")
_ = Translator("LevelUp", __file__)


def generate_level_img(
    background: t.Optional[bytes] = None,
    avatar: t.Optional[bytes] = None,
    level: t.Optional[int] = 1,
    color: t.Optional[t.Tuple[int, int, int]] = None,
    font_path: t.Optional[t.Union[str, Path]] = None,
    debug: t.Optional[bool] = False,
) -> bytes:
    if background:
        card = Image.open(BytesIO(background))
    else:
        card = imgtools.get_random_background()
    if avatar:
        pfp = Image.open(BytesIO(avatar))
    else:
        pfp = Image.open(imgtools.STOCK / "defaultpfp.png")

    desired_card_size = (200, 70)
    card = imgtools.fit_aspect_ratio(card, desired_card_size)

    # Shrink the font size if the text is too long
    fontsize = round(card.height / 2.5)
    font_path = str(font_path) if font_path else str(imgtools.DEFAULT_FONT)
    font = ImageFont.truetype(font_path, fontsize)
    text = _("Level {}").format(level)
    while font.getlength(text) + int(card.height * 1.2) > card.width - (int(card.height * 1.2) - card.height):
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)

    # Draw rounded rectangle at 4x size and scale down to crop card to
    mask = Image.new("RGBA", ((card.size[0]), (card.size[1])), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        (10, 0, card.width, card.height),
        fill=(0, 0, 0),
        width=5,
        radius=card.height,
    )

    # Make new Image to create composite
    composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
    final = Image.composite(card, composite_holder, mask)

    # Prep profile to paste
    pfpsize = (card.height, card.height)
    profile = pfp.convert("RGBA").resize(pfpsize, Image.Resampling.LANCZOS)

    # Create mask for profile image crop
    mask = Image.new("RGBA", ((card.size[0]), (card.size[1])), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, pfpsize[0], pfpsize[1]), fill=(255, 255, 255, 255))

    pfp_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))
    pfp_holder.paste(profile, (0, 0))
    pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
    pfp_composite_holder = Image.composite(pfp_holder, pfp_composite_holder, mask)

    final = Image.alpha_composite(final, pfp_composite_holder)
    # Draw
    draw = ImageDraw.Draw(final)
    # Filling text
    text_x = int(final.height * 1.2)
    text_y = int(final.height / 2)
    textpos = (text_x, text_y)
    draw.text(
        textpos,
        text,
        color or imgtools.rand_rgb(),
        font=font,
        anchor="lm",
        stroke_width=3,
        stroke_fill=(0, 0, 0),
    )
    # Finally resize the image
    final = final.resize(desired_card_size, Image.Resampling.LANCZOS)
    if debug:
        final.show(title="LevelUp Image")
    buffer = BytesIO()
    final.save(buffer, format="WEBP")
    final.close()
    return buffer.getvalue()


if __name__ == "__main__":
    assert isinstance(generate_level_img(debug=True), bytes)
