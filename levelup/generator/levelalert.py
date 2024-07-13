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
import math
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence, UnidentifiedImageError
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
    if avatar_bytes:
        pfp = Image.open(BytesIO(avatar_bytes))
    else:
        pfp = imgtools.DEFAULT_PFP

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
    if pfp_animated and not bg_animated:
        # Render an animated pfp on a static background
        if not card.mode == "RGBA":
            card = card.convert("RGBA")
        card = imgtools.fit_aspect_ratio(card, desired_card_size)
        avg_duration = imgtools.get_avg_duration(pfp)
        log.debug(f"Average frame duration: {avg_duration}")
        frames: t.List[Image.Image] = []
        for frame in range(pfp.n_frames):
            pfp_frame = ImageSequence.Iterator(pfp)[frame]
            card_frame = card.copy()
            if not pfp_frame.mode == "RGBA":
                pfp_frame = pfp_frame.convert("RGBA")

            pfp_frame = pfp_frame.resize((card.height, card.height), Image.Resampling.LANCZOS)
            pfp_frame = imgtools.make_profile_circle(pfp_frame)

            card_frame.paste(text_layer, (0, 0), text_layer)
            card_frame.paste(pfp_frame, (0, 0), pfp_frame)
            card_frame = imgtools.round_image_corners(card_frame, card_frame.height)
            card_frame = imgtools.clean_gif_frame(card_frame)
            frames.append(card_frame)
        buffer = BytesIO()
        frames[0].save(
            buffer,
            save_all=True,
            append_images=frames[1:],
            format="GIF",
            duration=avg_duration,
            loop=0,
            quality=75,
            optimize=True,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True
    if bg_animated and not pfp_animated:
        # Render a static pfp on an animated background
        if not pfp.mode == "RGBA":
            pfp = pfp.convert("RGBA")
        pfp = pfp.resize((desired_card_size[1], desired_card_size[1]), Image.Resampling.LANCZOS)
        pfp = imgtools.make_profile_circle(pfp)
        avg_duration = imgtools.get_avg_duration(card)
        log.debug(f"Average frame duration: {avg_duration}")
        frames: t.List[Image.Image] = []
        for frame in range(card.n_frames):
            bg_frame = ImageSequence.Iterator(card)[frame]
            card_frame = bg_frame.copy()
            if not card_frame.mode == "RGBA":
                card_frame = card_frame.convert("RGBA")
            card_frame = imgtools.fit_aspect_ratio(card_frame, desired_card_size)
            card_frame = imgtools.round_image_corners(card_frame, card_frame.height)
            card_frame = imgtools.clean_gif_frame(card_frame)
            card_frame.paste(text_layer, (0, 0), text_layer)
            card_frame.paste(pfp, (0, 0), pfp)
            frames.append(card_frame)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            save_all=True,
            append_images=frames[1:],
            format="GIF",
            duration=avg_duration,
            loop=0,
            quality=75,
            optimize=True,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True

    # If we're here, both the pfp and the background are animated
    card_duration = imgtools.get_avg_duration(card)
    pfp_duration = imgtools.get_avg_duration(pfp)
    log.debug(f"Card duration: {card_duration}, PFP duration: {pfp_duration}")
    # Round to the nearest 10ms
    card_duration = round(card_duration, -1)
    pfp_duration = round(pfp_duration, -1)
    # Get the least common multiple of the two durations
    combined_duration = math.lcm(card_duration, pfp_duration)
    # Soft cap it
    max_duration = max(card_duration, pfp_duration)
    if combined_duration > max_duration * 1.2:
        combined_duration = max_duration * 1.2

    total_pfp_duration = pfp.n_frames * pfp_duration
    total_card_duration = card.n_frames * card_duration
    total_duration_lcm = math.lcm(total_pfp_duration, total_card_duration)

    # Get the number of frames to render
    num_frames = total_duration_lcm // combined_duration
    # Also soft cap max amount of frames so we dont get a huge gif
    max_frame_count = max(pfp.n_frames, card.n_frames) * 1.2
    max_frame_count = min(round(max_frame_count), num_frames)
    log.debug(f"Max frame count: {max_frame_count}")

    frames: t.List[Image.Image] = []
    for frame_num in range(max_frame_count):
        time = frame_num * combined_duration

        card_frame_index = (time // card_duration) % card.n_frames
        pfp_frame_index = (time // pfp_duration) % pfp.n_frames

        card_frame: Image.Image = ImageSequence.Iterator(card)[int(card_frame_index)]
        pfp_frame: Image.Image = ImageSequence.Iterator(pfp)[int(pfp_frame_index)]

        card_frame = imgtools.fit_aspect_ratio(card_frame, desired_card_size)
        pfp_frame = pfp_frame.resize((card_frame.height, card_frame.height), Image.Resampling.LANCZOS)
        pfp_frame = imgtools.make_profile_circle(pfp_frame)
        if not card_frame.mode == "RGBA":
            card_frame = card_frame.convert("RGBA")
        if not pfp_frame.mode == "RGBA":
            pfp_frame = pfp_frame.convert("RGBA")

        card_frame = imgtools.round_image_corners(card_frame, card_frame.height)
        card_frame = imgtools.clean_gif_frame(card_frame)
        card_frame.paste(text_layer, (0, 0), text_layer)
        card_frame.paste(pfp_frame, (0, 0), pfp_frame)
        frames.append(card_frame)
    buffer = BytesIO()
    frames[0].save(
        buffer,
        save_all=True,
        append_images=frames[1:],
        format="GIF",
        duration=combined_duration,
        loop=0,
        quality=75,
        optimize=True,
    )
    buffer.seek(0)
    if debug:
        Image.open(buffer).show()
    return buffer.getvalue(), True


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
