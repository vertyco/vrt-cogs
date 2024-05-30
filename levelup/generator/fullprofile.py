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
    hollow_bar (t.Optional[bool], optional): Whether the level bar is hollow. Defaults to True.
    font_path (t.Optional[t.Union[str, Path], optional): The path to the font file. Defaults to None.
    render_gif (t.Optional[bool], optional): Whether to render as gif if profile or background is one. Defaults to False.
    debug (t.Optional[bool], optional): Whether to raise any errors rather than suppressing. Defaults to False.

Returns:
    t.Tuple[bytes, bool]: The generated full profile image as bytes, and whether the image is animated.
"""

import logging
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

try:
    from . import imgtools
    from .pilmojisrc.core import Pilmoji
except ImportError:
    import imgtools
    from pilmojisrc.core import Pilmoji

log = logging.getLogger("red.vrt.levelup.generator.fullprofile")
_ = Translator("LevelUp", __file__)


def generate_full_profile(
    background_bytes: t.Optional[bytes] = None,
    avatar_bytes: t.Optional[bytes] = None,
    username: t.Optional[str] = "Spartan117",
    status: t.Optional[str] = "online",
    level: t.Optional[int] = 3,
    messages: t.Optional[int] = 420,
    voicetime: t.Optional[str] = "None",
    stars: t.Optional[int] = 69,
    prestige: t.Optional[int] = 0,
    prestige_emoji: t.Optional[bytes] = None,
    balance: t.Optional[int] = 0,
    currency_name: t.Optional[str] = "Credits",
    previous_xp: t.Optional[int] = 100,
    current_xp: t.Optional[int] = 125,
    next_xp: t.Optional[int] = 200,
    position: t.Optional[int] = 3,
    role_icon: t.Optional[bytes] = None,
    blur: t.Optional[bool] = False,
    base_color: t.Optional[t.Tuple[int, int, int]] = (255, 255, 255),
    user_color: t.Optional[t.Tuple[int, int, int]] = (255, 255, 255),
    stat_color: t.Optional[t.Tuple[int, int, int]] = (255, 255, 255),
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = (255, 255, 255),
    hollow_bar: t.Optional[bool] = True,
    font_path: t.Optional[t.Union[str, Path]] = None,
    render_gif: t.Optional[bool] = False,
    debug: t.Optional[bool] = False,
) -> t.Tuple[bytes, bool]:
    if background_bytes:
        card = Image.open(BytesIO(background_bytes))
    else:
        card = imgtools.get_random_background()
    if avatar_bytes:
        pfp = Image.open(BytesIO(avatar_bytes))
    else:
        pfp = imgtools.DEFAULT_PFP

    pfp_animated = getattr(pfp, "is_animated", False)
    log.debug(f"PFP animated: {pfp_animated}")

    # This will stop the image from being animated
    if card.mode != "RGBA":
        log.debug(f"Converting card mode '{card.mode}' to RGBA")
        card = card.convert("RGBA")

    # Ensure the card is the correct size and aspect ratio
    desired_card_size = (1050, 450)
    aspect_ratio = imgtools.calc_aspect_ratio(*desired_card_size)
    card = imgtools.fit_aspect_ratio(card, aspect_ratio)
    card = card.resize(desired_card_size, Image.Resampling.LANCZOS)
    # Round edges of the card if its not animated
    if not pfp_animated or not render_gif:
        card = imgtools.round_image_corners(card, 45)

    # Setup
    default_fill = (0, 0, 0)  # Default fill color for text
    stroke_width = 2  # Width of the stroke around text
    name_y = 35  # Upper bound of username placement
    stats_y = 160  # Upper bound of stats texts
    blur_edge = 450  # Left bound of blur edge
    bar_width = 550  # Length of level bar
    bar_height = 40  # Height of level bar
    bar_start = 475  # Left bound of level bar
    bar_top = 380  # Top bound of level bar
    stat_bottom = bar_top - 10  # Bottom bound of all stats
    stat_start = bar_start + 10  # Left bound of all stats
    stat_split = stat_start + 210  # Split between left and right stats
    stat_end = 990  # Right bound of all stats
    stat_offset = 45  # Offset between stats
    circle_x = 60  # Left bound of profile circle
    circle_y = 60  # Top bound of profile circle
    star_text_x = 910  # Left bound of star text
    star_text_y = 35  # Top bound of star text
    star_icon_x = 850  # Left bound of star icon
    star_icon_y = 35  # Top bound of star icon

    # Create a new transparent layer for the stat text
    stats = Image.new("RGBA", desired_card_size, (0, 0, 0, 0))
    # Add blur to the stats box
    if blur:
        # Apply gaussian blur to the card to create a blur effect for the stats box area
        blurred = card.filter(ImageFilter.GaussianBlur(3))
        blur_box = blurred.crop((blur_edge, 0, card.width, card.height))
        # Darken the image
        blur_box = ImageEnhance.Brightness(blur_box).enhance(0.6)
        # Paste onto the stats
        stats.paste(blur_box, (blur_edge, 0), blur_box)
    else:
        # Apply semi-transparent grey box to the stats area
        box = Image.new("RGBA", (card.width - blur_edge, card.height), (0, 0, 0, 150))
        stats.paste(box, (blur_edge, 0), box)

    # Setup progress bar
    progress = (current_xp - previous_xp) / (next_xp - previous_xp)
    level_bar = imgtools.make_progress_bar(
        bar_width,
        bar_height,
        progress,
        level_bar_color,
        hollow=hollow_bar,
    )
    stats.paste(level_bar, (bar_start, bar_top), level_bar)

    # Start drawing text
    font_path = str(font_path) if font_path else str(imgtools.DEFAULT_FONT)
    draw = ImageDraw.Draw(stats)
    # ---------------- Username text ----------------
    fontsize = 60
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass star_icon_x
    while font.getlength(username) + stat_start > star_icon_x:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    with Pilmoji(stats) as pilmoji:
        pilmoji.text(
            xy=(stat_start, name_y),
            text=username,
            fill=user_color,
            stroke_width=stroke_width,
            stroke_fill=default_fill,
            font=font,
        )
    # ---------------- Prestige text ----------------
    if prestige:
        text = _("(Prestige {})").format(f"{humanize_number(prestige)}")
        fontsize = 40
        font = ImageFont.truetype(font_path, fontsize)
        # Ensure text doesnt pass stat_end
        while font.getlength(text) + stat_start > stat_end:
            fontsize -= 1
            font = ImageFont.truetype(font_path, fontsize)
        draw.text(
            xy=(stat_start, name_y + 70),
            text=text,
            fill=stat_color,
            stroke_width=stroke_width,
            stroke_fill=default_fill,
            font=font,
        )
        if prestige_emoji:
            prestige_icon = Image.open(BytesIO(prestige_emoji)).resize((50, 50), Image.Resampling.LANCZOS)
            placement = (round(stat_start + font.getlength(text) + 10), name_y + 65)
            stats.paste(prestige_icon, placement, prestige_icon)
    # ---------------- Stars text ----------------
    text = humanize_number(stars)
    fontsize = 60
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass stat_end
    while font.getlength(text) + star_text_x > stat_end:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(star_text_x, star_text_y),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    stats.paste(imgtools.STAR, (star_icon_x, star_icon_y), imgtools.STAR)
    # ---------------- Rank text ----------------
    text = _("Rank: {}").format(f"#{humanize_number(position)}")
    fontsize = 40
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass stat_split point
    while font.getlength(text) + stat_start > stat_split - 5:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(stat_start, stats_y),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    # ---------------- Level text ----------------
    text = _("Level: {}").format(humanize_number(level))
    fontsize = 40
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass the stat_split point
    while font.getlength(text) + stat_start > stat_split - 5:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(stat_start, stats_y + stat_offset),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    # ---------------- Messages text ----------------
    text = _("Messages: {}").format(humanize_number(messages))
    fontsize = 40
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass the stat_end
    while font.getlength(text) + stat_split > stat_end:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(stat_split, stats_y),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    # ---------------- Voice text ----------------
    text = _("Voice: {}").format(voicetime)
    fontsize = 40
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass the stat_end
    while font.getlength(text) + stat_split > stat_end:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(stat_split, stats_y + stat_offset),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    # ---------------- Balance text ----------------
    if balance:
        text = _("Balance: {}").format(f"{humanize_number(balance)} {currency_name}")
        fontsize = 40
        emoji_scale = 1.4
        emoji_y_offset = 50
        font = ImageFont.truetype(font_path, fontsize)
        # Ensure text doesnt pass the stat_end
        while font.getlength(text) + stat_start > stat_end and fontsize > 5:
            fontsize -= 1
            emoji_scale -= 0.1
            emoji_y_offset -= 0.2
            font = ImageFont.truetype(font_path, fontsize)
        with Pilmoji(stats) as pilmoji:
            text_bbox = font.getbbox(text)
            text_emoji_y = text_bbox[3] - round(emoji_y_offset)
            placement = (stat_start, stat_bottom - stat_offset * 2)
            print(f"textbbox: {text_bbox}, text_emoji_y: {text_emoji_y}, placement: {placement}, fontsize: {fontsize} ")
            pilmoji.text(
                xy=placement,
                text=text,
                fill=stat_color,
                stroke_width=stroke_width,
                stroke_fill=default_fill,
                font=font,
                emoji_scale_factor=max(0.3, emoji_scale),
                emoji_position_offset=(0, text_emoji_y),
            )
    # ---------------- Experience text ----------------
    current = current_xp - previous_xp
    goal = next_xp - previous_xp
    text = _("Exp: {} ({} total)").format(
        f"{humanize_number(current)}/{humanize_number(goal)}", humanize_number(current_xp)
    )
    fontsize = 40
    font = ImageFont.truetype(font_path, fontsize)
    # Ensure text doesnt pass the stat_end
    while font.getlength(text) + stat_start > stat_end:
        fontsize -= 1
        font = ImageFont.truetype(font_path, fontsize)
    draw.text(
        xy=(stat_start, stat_bottom - stat_offset),
        text=text,
        fill=stat_color,
        stroke_width=stroke_width,
        stroke_fill=default_fill,
        font=font,
    )
    # ---------------- Profile Accents ----------------
    # Draw a circle outline around where the avatar is
    # Calculate the circle outline's placement around the avatar
    circle = imgtools.make_circle_outline(thickness=5, color=user_color)
    outline_size = (380, 380)
    circle = circle.resize(outline_size, Image.Resampling.LANCZOS)
    placement = (circle_x - 25, circle_y - 25)
    stats.paste(circle, placement, circle)
    # Place status icon
    status_icon = imgtools.STATUS[status]
    stats.paste(status_icon, (circle_x + 273, circle_y + 273), status_icon)
    # Paste role icon on top left of profile circle
    if role_icon:
        role_icon_img = Image.open(BytesIO(role_icon)).resize((70, 70), Image.Resampling.LANCZOS)
        stats.paste(role_icon_img, (10, 10), role_icon_img)
    # ---------------- Start finalizing the image ----------------
    # Resize the profile image
    desired_pfp_size = (330, 330)
    if pfp_animated and render_gif:
        avg_duration = imgtools.get_avg_duration(pfp)
        log.debug(f"Rendering pfp as gif with avg duration of {avg_duration}ms")
        frames: t.List[Image.Image] = []
        for frame in range(pfp.n_frames):
            pfp.seek(frame)
            # Prepare copies of the card, stats, and pfp
            card_frame = card.copy()
            pfp_frame = pfp.copy()
            if pfp_frame.mode != "RGBA":
                pfp_frame = pfp_frame.convert("RGBA")
            # Resize the profile image for each frame
            pfp_frame = pfp_frame.resize(desired_pfp_size, Image.Resampling.NEAREST)
            # Crop the profile image into a circle
            pfp_frame = imgtools.make_profile_circle(pfp_frame)
            # Paste items onto the card
            card_frame.paste(stats, (0, 0), stats)
            card_frame.paste(pfp_frame, (circle_x, circle_y), pfp_frame)
            frames.append(card_frame)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=avg_duration,
            loop=0,
            optimize=True,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True

    else:
        if pfp.mode != "RGBA":
            log.debug(f"Converting pfp mode '{pfp.mode}' to RGBA")
            pfp = pfp.convert("RGBA")
        pfp = pfp.resize(desired_pfp_size, Image.Resampling.LANCZOS)
        # Crop the profile image into a circle
        pfp = imgtools.make_profile_circle(pfp)

        # Paste the items onto the card
        card.paste(stats, (0, 0), stats)
        card.paste(pfp, (circle_x, circle_y), pfp)
        if debug:
            card.show()
        buffer = BytesIO()
        card.save(buffer, format="WEBP")
        card.close()
        return buffer.getvalue(), False


if __name__ == "__main__":
    # Setup console logging
    logging.basicConfig(level=logging.DEBUG)

    test_banner = (imgtools.ASSETS / "tests" / "banner.gif").read_bytes()
    test_avatar = (imgtools.ASSETS / "tests" / "tree.gif").read_bytes()
    test_icon = (imgtools.ASSETS / "tests" / "icon.png").read_bytes()
    font_path = imgtools.ASSETS / "fonts" / "BebasNeue.ttf"
    res, animated = generate_full_profile(
        background_bytes=test_banner,
        avatar_bytes=test_avatar,
        username="Vertyco",
        status="online",
        level=999,
        messages=420,
        voicetime="99d 11h 55m",
        stars=693333,
        prestige=2,
        prestige_emoji=test_icon,
        balance=1000000,
        currency_name="Coinz 💰",
        previous_xp=1000,
        current_xp=1258,
        next_xp=5000,
        role_icon=test_icon,
        blur=True,
        font_path=font_path,
        render_gif=False,
        debug=True,
    )
    result_path = imgtools.ASSETS / "tests" / "result.gif"
    result_path.write_bytes(res)
