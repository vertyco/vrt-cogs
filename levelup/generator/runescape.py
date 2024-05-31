"""
Generate a full profile image with customizable parameters.
If the avatar is animated and not the background, the avatar will be rendered as a gif.
If the background is animated and not the avatar, the background will be rendered as a gif.
If both are animated, the avatar will be rendered as a gif and the background will be rendered as a static image.
To optimize performance, the profile will be generated in 3 layers, the background, the avatar, and the stats.
The stats layer will be generated as a separate image and then pasted onto the background.

Args:
    background (t.Optional[bytes], optional): The background image as bytes. Defaults to None.
    avatar (t.Optional[bytes], optional): The avatar image as bytes. Defaults to None.
    username (t.Optional[str], optional): The username. Defaults to "Spartan117".
    status (t.Optional[str], optional): The status. Defaults to "online".
    level (t.Optional[int], optional): The level. Defaults to 1.
    messages (t.Optional[int], optional): The number of messages. Defaults to 0.
    voicetime (t.Optional[str], optional): The voicetime. Defaults to "None".
    stars (t.Optional[int], optional): The number of stars. Defaults to 0.
    prestige (t.Optional[int], optional): The prestige level. Defaults to 0.
    prestige_emoji (t.Optional[bytes], optional): The prestige emoji as bytes. Defaults to None.
    balance (t.Optional[int], optional): The balance. Defaults to 0.
    currency_name (t.Optional[str], optional): The name of the currency. Defaults to "Credits".
    previous_xp (t.Optional[int], optional): The previous XP. Defaults to 0.
    current_xp (t.Optional[int], optional): The current XP. Defaults to 0.
    next_xp (t.Optional[int], optional): The next XP. Defaults to 0.
    position (t.Optional[int], optional): The position. Defaults to 0.
    role_icon (t.Optional[bytes], optional): The role icon as bytes. Defaults to None.
    blur (t.Optional[bool], optional): Whether to blur the box behind the stats. Defaults to False.
    user_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the user. Defaults to None.
    base_color (t.Optional[t.Tuple[int, int, int]], optional): The base color. Defaults to None.
    stat_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the stats. Defaults to None.
    level_bar_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the level bar. Defaults to None.
    render_gif (t.Optional[bool], optional): Whether to render as gif if profile or background is one. Defaults to False.
    debug (t.Optional[bool], optional): Whether to raise any errors rather than suppressing. Defaults to False.

Returns:
    t.Tuple[bytes, bool]: The generated full profile image as bytes, and whether the image is animated.
"""

import logging
import typing as t
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from redbot.core.i18n import Translator

try:
    from . import imgtools
except ImportError:
    import imgtools

log = logging.getLogger("red.vrt.levelup.generator.runescape")
_ = Translator("LevelUp", __file__)


def generate_runescape_profile(
    avatar_bytes: t.Optional[bytes] = None,
    username: t.Optional[str] = "Username",
    status: t.Optional[str] = "online",
    level: t.Optional[int] = 100,
    messages: t.Optional[int] = 52_000,
    voicetime: t.Optional[int] = 3600,
    prestige: t.Optional[int] = 0,
    prestige_emoji: t.Optional[bytes] = None,
    balance: t.Optional[int] = 1_000_000,
    previous_xp: t.Optional[int] = 100,
    current_xp: t.Optional[int] = 125,
    next_xp: t.Optional[int] = 200,
    position: t.Optional[int] = 3,
    role_icon: t.Optional[bytes] = None,
    base_color: t.Optional[t.Tuple[int, int, int]] = (255, 255, 255),
    user_color: t.Optional[t.Tuple[int, int, int]] = (230, 104, 25),
    stat_color: t.Optional[t.Tuple[int, int, int]] = (0, 255, 68),
    render_gif: t.Optional[bool] = False,
    debug: t.Optional[bool] = False,
    **kwargs,
):
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
    template = imgtools.RS_TEMPLATE_BALANCE if balance else imgtools.RS_TEMPLATE

    # Paste profile circle at 75, 50
    if pfp.mode != "RGBA":
        pfp = pfp.convert("RGBA")
    pfp = imgtools.make_profile_circle(pfp)
    pfp = pfp.resize((145, 145), Image.Resampling.LANCZOS)
    # Place status icon
    status_icon = imgtools.STATUS[status].resize((25, 25), Image.Resampling.LANCZOS)
    card.paste(status_icon, (196, -2), status_icon)
    # Place pfp
    card.paste(pfp, (65, 9), pfp)
    # Place template on top
    card.paste(template, (0, 0), template)

    draw = ImageDraw.Draw(card)
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

    # Finalize image
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
    generate_runescape_profile(
        avatar_bytes=test_avatar,
        username="vertyco",
        debug=True,
        status="idle",
    )
