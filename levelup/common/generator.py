import logging
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from redbot.core.i18n import Translator

from . import const, imgtools

log = logging.getLogger("red.vrt.levelup.generator")
_ = Translator("LevelUp", __file__)


def generate_levelup(
    background: t.Optional[bytes] = None,
    avatar: t.Optional[bytes] = None,
    level: int = 1,
    color: t.Optional[t.Tuple[int, int, int]] = None,
    font: t.Optional[t.Union[str, Path]] = None,
):
    """Generate LevelUp Image"""
    if background:
        card = Image.open(BytesIO(background))
    else:
        card = imgtools.get_random_background()

    if avatar:
        pfp = Image.open(BytesIO(avatar))
    else:
        pfp = Image.open(const.STOCK / "defaultpfp.png")

    desired_card_size = (200, 70)
    aspect_ratio = imgtools.calc_aspect_ratio(*desired_card_size)
    card = imgtools.fit_aspect_ratio(card, aspect_ratio)

    # Shrink the font size if the text is too long
    fontsize = round(card.height / 2.5)
    fontpath = str(font) if font else str(const.DEFAULT_FONT)
    font = ImageFont.truetype(fontpath, fontsize)
    text = _("Level {}").format(level)
    while font.getlength(text) + int(card.height * 1.2) > card.width - (int(card.height * 1.2) - card.height):
        fontsize -= 1
        font = ImageFont.truetype(fontpath, fontsize)

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
    return final
