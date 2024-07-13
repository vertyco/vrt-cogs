"""
Generate a full profile image with customizable parameters.

Args:
    avatar_bytes (t.Optional[bytes], optional): The avatar image as bytes. Defaults to None.
    status (t.Optional[str], optional): The status. Defaults to "online".
    level (t.Optional[int], optional): The level. Defaults to 1.
    messages (t.Optional[int], optional): The number of messages. Defaults to 0.
    voicetime (t.Optional[int], optional): The voicetime. Defaults to 3600.
    prestige (t.Optional[int], optional): The prestige level. Defaults to 0.
    prestige_emoji (t.Optional[bytes], optional): The prestige emoji as bytes. Defaults to None.
    balance (t.Optional[int], optional): The balance. Defaults to 0.
    previous_xp (t.Optional[int], optional): The previous XP. Defaults to 0.
    current_xp (t.Optional[int], optional): The current XP. Defaults to 4.
    next_xp (t.Optional[int], optional): The next XP. Defaults to 10.
    position (t.Optional[int], optional): The position. Defaults to 1.
    stat_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the stats. Defaults to (0, 255, 68).
    render_gif (t.Optional[bool], optional): Whether to render as gif. Defaults to False.
    debug (t.Optional[bool], optional): Whether to show the generated image. Defaults to False.

Returns:
    bytes: The generated full profile image as bytes.
"""

import logging
import typing as t
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

try:
    from .. import imgtools
except ImportError:
    import imgtools

log = logging.getLogger("red.vrt.levelup.generator.styles.default")


def generate_runescape_profile(
    avatar_bytes: t.Optional[bytes] = None,
    status: str = "online",
    level: int = 1,
    messages: int = 0,
    voicetime: int = 3600,
    prestige: int = 0,
    balance: int = 0,
    previous_xp: int = 0,
    current_xp: int = 4,
    next_xp: int = 10,
    position: int = 1,
    stat_color: t.Tuple[int, int, int] = (0, 255, 68),  # Green
    render_gif: bool = False,
    debug: bool = False,
    **kwargs,
):
    if isinstance(avatar_bytes, str) and avatar_bytes.startswith("http"):
        log.debug("Avatar image is a URL, attempting to download")
        avatar_bytes = imgtools.download_image(avatar_bytes)

    if avatar_bytes:
        pfp = Image.open(BytesIO(avatar_bytes))
    else:
        pfp = imgtools.DEFAULT_PFP

    pfp_animated = getattr(pfp, "is_animated", False)
    log.debug(f"PFP animated: {pfp_animated}")

    profile_size = (219, 192)
    # Create blank transparent image at 219 x 192 to put everything on
    card = Image.new("RGBA", profile_size, (0, 0, 0, 0))
    # Template also at 219 x 192
    template = imgtools.RS_TEMPLATE_BALANCE.copy() if balance else imgtools.RS_TEMPLATE.copy()
    # Place status icon
    status_icon = imgtools.STATUS[status].resize((25, 25), Image.Resampling.LANCZOS)
    card.paste(status_icon, (197, -2), status_icon)

    draw = ImageDraw.Draw(template)
    # Draw stats
    font_path = imgtools.ASSETS / "fonts" / "Runescape.ttf"
    # Draw balance
    if balance:
        balance_text = f"{imgtools.abbreviate_number(balance)}"
        balance_size = 20
        balance_font = ImageFont.truetype(str(font_path), balance_size)
        draw.text(
            xy=(44, 23),
            text=balance_text,
            font=balance_font,
            fill=stat_color,
            anchor="mm",
        )
    # Draw prestige
    if prestige:
        prestige_text = f"{imgtools.abbreviate_number(prestige)}"
        prestige_size = 35
        prestige_font = ImageFont.truetype(str(font_path), prestige_size)
        draw.text(
            xy=(197, 149),
            text=prestige_text,
            font=prestige_font,
            fill=stat_color,
            anchor="mm",
            stroke_width=1,
        )

    # Draw level
    level_text = f"{imgtools.abbreviate_number(level)}"
    level_size = 20
    level_font = ImageFont.truetype(str(font_path), level_size)
    draw.text(
        xy=(20, 58),
        text=level_text,
        font=level_font,
        fill=stat_color,
        align="center",
        anchor="mm",
    )
    # Draw rank
    rank_text = f"#{imgtools.abbreviate_number(position)}"
    rank_size = 20
    rank_font = ImageFont.truetype(str(font_path), rank_size)
    lb, rb = 2, 32
    while rank_font.getlength(rank_text) > rb - lb:
        rank_size -= 1
        rank_font = ImageFont.truetype(str(font_path), rank_size)
    draw.text(
        xy=(17, 93),
        text=rank_text,
        font=rank_font,
        fill=stat_color,
        anchor="mm",
    )
    # Draw messages
    messages_text = f"{imgtools.abbreviate_number(messages)}"
    messages_size = 20
    messages_font = ImageFont.truetype(str(font_path), messages_size)
    draw.text(
        xy=(27, 127),
        text=messages_text,
        font=messages_font,
        fill=stat_color,
        align="center",
        anchor="mm",
    )
    # Draw voicetime
    voicetime_text = f"{imgtools.abbreviate_time(voicetime, short=True)}"
    voicetime_size = 20
    voicetime_font = ImageFont.truetype(str(font_path), voicetime_size)
    lb, rb = 30, 65
    while voicetime_font.getlength(voicetime_text) > rb - lb:
        voicetime_size -= 1
        voicetime_font = ImageFont.truetype(str(font_path), voicetime_size)
    draw.text(
        xy=(46, 155),
        text=voicetime_text,
        font=voicetime_font,
        fill=stat_color,
        align="center",
        anchor="mm",
    )
    # Draw xp
    current = imgtools.abbreviate_number(current_xp - previous_xp)
    goal = imgtools.abbreviate_number(next_xp - previous_xp)
    percent = round((current_xp - previous_xp) / (next_xp - previous_xp) * 100)
    xp_text = f"{current}/{goal} ({percent}%)"
    xp_size = 20
    xp_font = ImageFont.truetype(str(font_path), xp_size)
    draw.text(
        xy=(105, 182),
        text=xp_text,
        font=xp_font,
        fill=stat_color,
        align="center",
        anchor="mm",
    )
    # ---------------- Start finalizing the image ----------------
    if pfp_animated and render_gif:
        avg_duration = imgtools.get_avg_duration(pfp)
        frames: t.List[Image.Image] = []
        for frame in range(pfp.n_frames):
            pfp.seek(frame)
            # Prep each frame
            card_frame = card.copy()
            pfp_frame = pfp.copy()
            if pfp_frame.mode != "RGBA":
                pfp_frame = pfp_frame.convert("RGBA")
            pfp_frame = pfp_frame.resize((145, 145), Image.Resampling.NEAREST)
            pfp_frame = imgtools.make_profile_circle(pfp_frame, Image.Resampling.NEAREST)
            # Place the pfp
            card_frame.paste(pfp_frame, (65, 9), pfp_frame)
            # Place the template
            card_frame.paste(template, (0, 0), template)
            frames.append(card_frame)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=avg_duration,
            loop=0,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True

    # Place the pfp
    if pfp.mode != "RGBA":
        pfp = pfp.convert("RGBA")
    pfp = pfp.resize((145, 145), Image.Resampling.LANCZOS)
    pfp = imgtools.make_profile_circle(pfp)
    card.paste(pfp, (65, 9), pfp)
    # Place the template
    card.paste(template, (0, 0), template)
    if debug:
        card.show()
    buffer = BytesIO()
    card.save(buffer, format="WEBP")
    return buffer.getvalue(), False


if __name__ == "__main__":
    # Setup console logging
    logging.basicConfig(level=logging.DEBUG)
    test_avatar = (imgtools.ASSETS / "tests" / "tree.gif").read_bytes()
    test_icon = (imgtools.ASSETS / "tests" / "icon.png").read_bytes()
    font_path = imgtools.ASSETS / "fonts" / "Runescape.ttf"
    res, animated = generate_runescape_profile(
        avatar_bytes=test_avatar,
        prestige=2,
        username="vertyco",
        level=0,
        debug=True,
        balance=1000000,
        status="dnd",
        position=100000,
        render_gif=True,
        role_icon=test_icon,
    )
    result_path = imgtools.ASSETS / "tests" / "result.gif"
    result_path.write_bytes(res)
