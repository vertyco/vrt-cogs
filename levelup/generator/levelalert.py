"""Generate LevelUp Image

Args:
    background_bytes (t.Optional[bytes], optional): The background image as bytes. Defaults to None.
    avatar_bytes (t.Optional[bytes], optional): The avatar image as bytes. Defaults to None.
    level (t.Optional[int], optional): The level number. Defaults to 1.
    color (t.Optional[t.Tuple[int, int, int]], optional): The color of the level text as a tuple of RGB values. Defaults to None.
    font (t.Optional[t.Union[str, Path]], optional): The path to the font file or the name of the font. Defaults to None.
    render_gif (t.Optional[bool], optional): Whether to render the image as a GIF. Defaults to False.
    debug (t.Optional[bool], optional): Whether to show the generated image for debugging purposes. Defaults to False.

Returns:
    bytes: The generated image as bytes.
"""

import logging
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from redbot.core.i18n import Translator

try:
    from . import imgtools
except ImportError:
    import imgtools

log = logging.getLogger("red.vrt.levelup.generator.levelalert")
_ = Translator("LevelUp", __file__)


def generate_level_img(
    background_bytes: t.Optional[t.Union[bytes, str]] = None,
    avatar_bytes: t.Optional[t.Union[bytes, str]] = None,
    level: int = 1,
    color: t.Optional[t.Tuple[int, int, int]] = None,
    font_path: t.Optional[t.Union[str, Path]] = None,
    render_gif: bool = False,
    debug: bool = False,
    **kwargs,
) -> t.Tuple[bytes, bool]:
    if isinstance(background_bytes, str) and background_bytes.startswith("http"):
        log.debug("Background image is a URL, attempting to download")
        background_bytes = imgtools.download_image(background_bytes)

    if isinstance(avatar_bytes, str) and avatar_bytes.startswith("http"):
        log.debug("Avatar image is a URL, attempting to download")
        avatar_bytes = imgtools.download_image(avatar_bytes)

    if background_bytes:
        try:
            card = Image.open(BytesIO(background_bytes))
        except UnidentifiedImageError as e:
            log.error("Error opening background image", exc_info=e)
            card = imgtools.get_random_background()
    else:
        card = imgtools.get_random_background()
    pfp = imgtools.open_avatar(avatar_bytes)

    pfp_animated = getattr(pfp, "is_animated", False)
    bg_animated = getattr(card, "is_animated", False)
    log.debug(f"PFP animated: {pfp_animated}, BG animated: {bg_animated}")

    desired_card_size = (200, 70)
    # 3 layers: card, profile, text

    # PREPARE THE TEXT LAYER
    text_layer = Image.new("RGBA", desired_card_size, (0, 0, 0, 0))
    tw, th = text_layer.size
    fontsize = 30
    font_path = font_path or imgtools.DEFAULT_FONT
    if isinstance(font_path, str):
        font_path = Path(font_path)
    if not font_path.exists():  # Hosted api specified a font that doesn't exist on the server
        if (imgtools.DEFAULT_FONTS / font_path.name).exists():
            font_path = imgtools.DEFAULT_FONTS / font_path.name
        else:
            font_path = imgtools.DEFAULT_FONT
    font_path = str(font_path)
    font = ImageFont.truetype(font_path, fontsize)
    text = _("Level {}").format(level)
    placement_area_center_x = th + ((tw - th) / 2)
    while font.getlength(text) > (tw - th) - 10:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw = ImageDraw.Draw(text_layer)
    draw.text(
        xy=(placement_area_center_x, int(th / 2)),
        text=text,
        fill=color or imgtools.rand_rgb(),
        font=font,
        anchor="mm",
        stroke_width=3,
        stroke_fill=(0, 0, 0),
    )
    # FINALIZE IMAGE
    if not render_gif or (not pfp_animated and not bg_animated):
        # Render a static pfp on a static background
        if not card.mode == "RGBA":
            card = card.convert("RGBA")
        if not pfp.mode == "RGBA":
            pfp = pfp.convert("RGBA")
        card = imgtools.fit_aspect_ratio(card, desired_card_size)
        pfp = pfp.resize((card.height, card.height), Image.Resampling.LANCZOS)
        pfp = imgtools.make_profile_circle(pfp)
        card.paste(text_layer, (0, 0), text_layer)
        card.paste(pfp, (0, 0), pfp)
        card = imgtools.round_image_corners(card, card.height)
        if debug:
            card.show(title="LevelUp Image")
        buffer = BytesIO()
        card.save(buffer, format="WEBP")
        card.close()
        return buffer.getvalue(), False

    # Each source frame is prepared once, then the layers are lined up so both play at their own speed
    def prepare_card(frame: Image.Image) -> Image.Image:
        frame = imgtools.fit_aspect_ratio(frame, desired_card_size)
        return imgtools.round_image_corners(frame, frame.height)

    def prepare_pfp(frame: Image.Image) -> Image.Image:
        frame = frame.resize((desired_card_size[1], desired_card_size[1]), Image.Resampling.LANCZOS)
        return imgtools.make_profile_circle(frame)

    card_layer = imgtools.AnimationLayer(card, prepare_card)
    pfp_layer = imgtools.AnimationLayer(pfp, prepare_pfp)

    def render_frame(indexes: t.Tuple[int, int]) -> Image.Image:
        card_frame = card_layer.get(indexes[0]).copy()
        card_frame.paste(text_layer, (0, 0), text_layer)
        pfp_frame = pfp_layer.get(indexes[1])
        card_frame.paste(pfp_frame, (0, 0), pfp_frame)
        return card_frame

    result = imgtools.render_animation([card_layer, pfp_layer], render_frame)
    if debug:
        Image.open(BytesIO(result)).show()
    return result, True


if __name__ == "__main__":
    # Setup console logging
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("PIL").setLevel(logging.INFO)
    test_banner = (imgtools.ASSETS / "tests" / "banner3.gif").read_bytes()
    test_avatar = (imgtools.ASSETS / "tests" / "tree.gif").read_bytes()
    res, animated = generate_level_img(
        background_bytes=test_banner,
        avatar_bytes=test_avatar,
        level=10,
        debug=True,
        render_gif=True,
    )
    result_path = imgtools.ASSETS / "tests" / "level.gif"
    result_path.write_bytes(res)
