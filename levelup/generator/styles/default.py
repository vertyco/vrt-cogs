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
    voicetime (t.Optional[int], optional): The voicetime. Defaults to 3600.
    stars (t.Optional[int], optional): The number of stars. Defaults to 0.
    prestige (t.Optional[int], optional): The prestige level. Defaults to 0.
    prestige_emoji (t.Optional[bytes], optional): The prestige emoji as bytes. Defaults to None.
    balance (t.Optional[int], optional): The balance. Defaults to 0.
    currency_name (t.Optional[str], optional): The name of the currency. Defaults to "Credits".
    previous_xp (t.Optional[int], optional): The previous XP. Defaults to 0.
    current_xp (t.Optional[int], optional): The current XP. Defaults to 0.
    next_xp (t.Optional[int], optional): The next XP. Defaults to 0.
    position (t.Optional[int], optional): The position. Defaults to 0.
    role_icon (t.Optional[bytes, str], optional): The role icon as bytes or url. Defaults to None.
    blur (t.Optional[bool], optional): Whether to blur the box behind the stats. Defaults to False.
    user_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the user. Defaults to None.
    base_color (t.Optional[t.Tuple[int, int, int]], optional): The base color. Defaults to None.
    stat_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the stats. Defaults to None.
    level_bar_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the level bar. Defaults to None.
    font_path (t.Optional[t.Union[str, Path], optional): The path to the font file. Defaults to None.
    render_gif (t.Optional[bool], optional): Whether to render as gif if profile or background is one. Defaults to False.
    debug (t.Optional[bool], optional): Whether to raise any errors rather than suppressing. Defaults to False.

Returns:
    t.Tuple[bytes, bool]: The generated full profile image as bytes, and whether the image is animated.
"""

import logging
import math
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence, UnidentifiedImageError
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

try:
    from .. import imgtools
    from ..pilmojisrc.core import Pilmoji
except ImportError:
    import imgtools
    from pilmojisrc.core import Pilmoji

log = logging.getLogger("red.vrt.levelup.generator.styles.default")
_ = Translator("LevelUp", __file__)


def generate_default_profile(
    background_bytes: t.Optional[t.Union[bytes, str]] = None,
    avatar_bytes: t.Optional[t.Union[bytes, str]] = None,
    username: str = "Spartan117",
    status: str = "online",
    level: int = 3,
    messages: int = 420,
    voicetime: int = 3600,
    stars: int = 69,
    prestige: int = 0,
    prestige_emoji: t.Optional[t.Union[bytes, str]] = None,
    balance: int = 0,
    currency_name: str = "Credits",
    previous_xp: int = 100,
    current_xp: int = 125,
    next_xp: int = 200,
    position: int = 3,
    role_icon: t.Optional[t.Union[bytes, str]] = None,
    blur: bool = False,
    base_color: t.Tuple[int, int, int] = (255, 255, 255),
    user_color: t.Optional[t.Tuple[int, int, int]] = None,
    stat_color: t.Optional[t.Tuple[int, int, int]] = None,
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = None,
    font_path: t.Optional[t.Union[str, Path]] = None,
    render_gif: bool = False,
    debug: bool = False,
    reraise: bool = False,
    **kwargs,
) -> t.Tuple[bytes, bool]:
    user_color = user_color or base_color
    stat_color = stat_color or base_color
    level_bar_color = level_bar_color or base_color

    if isinstance(background_bytes, str) and background_bytes.startswith("http"):
        log.debug("Background image is a URL, attempting to download")
        background_bytes = imgtools.download_image(background_bytes)

    if isinstance(avatar_bytes, str) and avatar_bytes.startswith("http"):
        log.debug("Avatar image is a URL, attempting to download")
        avatar_bytes = imgtools.download_image(avatar_bytes)

    if isinstance(prestige_emoji, str) and prestige_emoji.startswith("http"):
        log.debug("Prestige emoji is a URL, attempting to download")
        prestige_emoji = imgtools.download_image(prestige_emoji)

    if isinstance(role_icon, str) and role_icon.startswith("http"):
        log.debug("Role icon is a URL, attempting to download")
        role_icon_bytes = imgtools.download_image(role_icon)
    else:
        role_icon_bytes = role_icon

    if background_bytes:
        try:
            card = Image.open(BytesIO(background_bytes))
        except UnidentifiedImageError as e:
            if reraise:
                raise e
            log.error(
                f"Failed to open background image ({type(background_bytes)} - {len(background_bytes)})", exc_info=e
            )
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

    # Ensure the card is the correct size and aspect ratio
    desired_card_size = (1050, 450)
    # aspect_ratio = imgtools.calc_aspect_ratio(*desired_card_size)
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

    # Establish layer for all text and accents
    stats = Image.new("RGBA", desired_card_size, (0, 0, 0, 0))

    # Setup progress bar
    progress = (current_xp - previous_xp) / (next_xp - previous_xp)
    level_bar = imgtools.make_progress_bar(
        bar_width,
        bar_height,
        progress,
        level_bar_color,
    )
    stats.paste(level_bar, (bar_start, bar_top), level_bar)

    # Establish font
    font_path = font_path or imgtools.DEFAULT_FONT
    if isinstance(font_path, str):
        font_path = Path(font_path)
    if not font_path.exists():
        # Hosted api on another server? Check if we have it
        if (imgtools.DEFAULT_FONTS / font_path.name).exists():
            font_path = imgtools.DEFAULT_FONTS / font_path.name
        else:
            font_path = imgtools.DEFAULT_FONT
    # Convert back to string
    font_path = str(font_path)

    draw = ImageDraw.Draw(stats)
    # ---------------- Username text ----------------
    fontsize = 60
    font = ImageFont.truetype(font_path, fontsize)
    with Pilmoji(stats) as pilmoji:
        # Ensure text doesnt pass star_icon_x
        while pilmoji.getsize(username, font)[0] + stat_start > star_icon_x - 10:
            fontsize -= 1
            font = ImageFont.truetype(font_path, fontsize)
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
            if prestige_icon.mode != "RGBA":
                prestige_icon = prestige_icon.convert("RGBA")
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
    text = _("Voice: {}").format(imgtools.abbreviate_time(voicetime))
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
        font = ImageFont.truetype(font_path, 40)
        with Pilmoji(stats) as pilmoji:
            # Ensure text doesnt pass the stat_end
            while pilmoji.getsize(text, font)[0] + stat_start > stat_end:
                fontsize -= 1
                font = ImageFont.truetype(font_path, fontsize)
            placement = (stat_start, stat_bottom - stat_offset * 2)
            pilmoji.text(
                xy=placement,
                text=text,
                fill=stat_color,
                stroke_width=stroke_width,
                stroke_fill=default_fill,
                font=font,
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
    status_icon = imgtools.STATUS[status].resize((75, 75), Image.Resampling.LANCZOS)
    stats.paste(status_icon, (circle_x + 260, circle_y + 260), status_icon)
    # Paste role icon on top left of profile circle
    if role_icon_bytes:
        try:
            role_icon_img = Image.open(BytesIO(role_icon_bytes)).resize((70, 70), Image.Resampling.LANCZOS)
            stats.paste(role_icon_img, (10, 10), role_icon_img)
        except ValueError as e:
            if reraise:
                raise e
            err = (
                f"Failed to paste role icon image for {username}"
                if isinstance(role_icon, bytes)
                else f"Failed to paste role icon image for {username}: {role_icon}"
            )
            log.error(err, exc_info=e)

    # ---------------- Start finalizing the image ----------------
    # Resize the profile image
    desired_pfp_size = (330, 330)
    if not render_gif or (not pfp_animated and not bg_animated):
        if card.mode != "RGBA":
            log.debug(f"Converting card mode '{card.mode}' to RGBA")
            card = card.convert("RGBA")
        if pfp.mode != "RGBA":
            log.debug(f"Converting pfp mode '{pfp.mode}' to RGBA")
            pfp = pfp.convert("RGBA")
        card = imgtools.fit_aspect_ratio(card, desired_card_size)
        if blur:
            blur_section = imgtools.blur_section(card, (blur_edge, 0, card.width, card.height))
            # Paste onto the stats
            card.paste(blur_section, (blur_edge, 0), blur_section)
        card = imgtools.round_image_corners(card, 45)
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

    if pfp_animated and not bg_animated:
        if card.mode != "RGBA":
            log.debug(f"Converting card mode '{card.mode}' to RGBA")
            card = card.convert("RGBA")
        card = imgtools.fit_aspect_ratio(card, desired_card_size)
        if blur:
            blur_section = imgtools.blur_section(card, (blur_edge, 0, card.width, card.height))
            # Paste onto the stats
            card.paste(blur_section, (blur_edge, 0), blur_section)

        card.paste(stats, (0, 0), stats)

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
            pfp_frame = imgtools.make_profile_circle(pfp_frame, method=Image.Resampling.NEAREST)
            # Paste the profile image onto the card
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
            quality=75,
            optimize=True,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True
    elif bg_animated and not pfp_animated:
        avg_duration = imgtools.get_avg_duration(card)
        log.debug(f"Rendering card as gif with avg duration of {avg_duration}ms")
        frames: t.List[Image.Image] = []

        if pfp.mode != "RGBA":
            log.debug(f"Converting pfp mode '{pfp.mode}' to RGBA")
            pfp = pfp.convert("RGBA")
        pfp = pfp.resize(desired_pfp_size, Image.Resampling.LANCZOS)
        # Crop the profile image into a circle
        pfp = imgtools.make_profile_circle(pfp)
        for frame in range(card.n_frames):
            card.seek(frame)
            # Prepare copies of the card and stats
            card_frame = card.copy()
            card_frame = imgtools.fit_aspect_ratio(card_frame, desired_card_size)
            if card_frame.mode != "RGBA":
                card_frame = card_frame.convert("RGBA")

            # Paste items onto the card
            if blur:
                blur_section = imgtools.blur_section(card_frame, (blur_edge, 0, card_frame.width, card_frame.height))
                card_frame.paste(blur_section, (blur_edge, 0), blur_section)

            card_frame.paste(pfp, (circle_x, circle_y), pfp)
            card_frame.paste(stats, (0, 0), stats)

            frames.append(card_frame)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=avg_duration,
            loop=0,
            quality=75,
            optimize=True,
        )
        buffer.seek(0)
        if debug:
            Image.open(buffer).show()
        return buffer.getvalue(), True

    # If we're here, both the avatar and background are gifs
    # Figure out how to merge the two frame counts and durations together
    # Calculate frame durations based on the LCM
    pfp_duration = imgtools.get_avg_duration(pfp)  # example: 50ms
    card_duration = imgtools.get_avg_duration(card)  # example: 100ms
    log.debug(f"PFP duration: {pfp_duration}ms, Card duration: {card_duration}ms")
    # Figure out how to round the durations
    # Favor the card's duration time over the pfp
    # Round both durations to the nearest X ms based on what will get the closest to the LCM
    pfp_duration = round(card_duration, -1)  # Round to the nearest 10ms
    card_duration = round(card_duration, -1)  # Round to the nearest 10ms

    log.debug(f"Modified PFP duration: {pfp_duration}ms, Card duration: {card_duration}ms")
    combined_duration = math.lcm(pfp_duration, card_duration)  # example: 100ms would be the LCM of 50 and 100
    log.debug(f"Combined duration: {combined_duration}ms")
    # The combined duration should be no more than 20% offset from the image with the highest duration
    max_duration = max(pfp_duration, card_duration)
    if combined_duration > max_duration * 1.2:
        log.debug(f"Combined duration is more than 20% offset from the max duration ({max_duration}ms)")
        combined_duration = max_duration

    total_pfp_duration = pfp.n_frames * pfp_duration  # example: 2250ms
    total_card_duration = card.n_frames * card_duration  # example: 3300ms
    # Total duration for the combined animation cycle (LCM of 2250 and 3300)
    total_duration = math.lcm(total_pfp_duration, total_card_duration)  # example: 9900ms
    num_combined_frames = total_duration // combined_duration

    # The maximum frame count should be no more than 20% offset from the image with the highest frame count to avoid filesize bloat
    max_frame_count = max(pfp.n_frames, card.n_frames) * 1.2
    max_frame_count = min(round(max_frame_count), num_combined_frames)
    log.debug(f"Max frame count: {max_frame_count}")
    # Create a list to store the combined frames
    combined_frames = []
    for frame_num in range(max_frame_count):
        time = frame_num * combined_duration

        # Calculate the frame index for both the card and pfp
        card_frame_index = (time // card_duration) % card.n_frames
        pfp_frame_index = (time // pfp_duration) % pfp.n_frames

        # Get the frames for the card and pfp
        card_frame = ImageSequence.Iterator(card)[card_frame_index]
        pfp_frame = ImageSequence.Iterator(pfp)[pfp_frame_index]

        card_frame = imgtools.fit_aspect_ratio(card_frame, desired_card_size)
        if card_frame.mode != "RGBA":
            card_frame = card_frame.convert("RGBA")

        if blur:
            blur_section = imgtools.blur_section(card_frame, (blur_edge, 0, card_frame.width, card_frame.height))
            # Paste onto the stats
            card_frame.paste(blur_section, (blur_edge, 0), blur_section)
        if pfp_frame.mode != "RGBA":
            pfp_frame = pfp_frame.convert("RGBA")

        pfp_frame = pfp_frame.resize(desired_pfp_size, Image.Resampling.NEAREST)
        pfp_frame = imgtools.make_profile_circle(pfp_frame, method=Image.Resampling.NEAREST)

        card_frame.paste(pfp_frame, (circle_x, circle_y), pfp_frame)
        card_frame.paste(stats, (0, 0), stats)

        combined_frames.append(card_frame)

    buffer = BytesIO()
    combined_frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=combined_frames[1:],
        loop=0,
        duration=combined_duration,
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
    test_icon = (imgtools.ASSETS / "tests" / "icon.png").read_bytes()
    font_path = imgtools.ASSETS / "fonts" / "BebasNeue.ttf"
    res, animated = generate_default_profile(
        background_bytes=test_banner,
        avatar_bytes=test_avatar,
        username="Vertyco",
        status="online",
        level=999,
        messages=420,
        voicetime=399815,
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
        render_gif=True,
        debug=True,
    )
    result_path = imgtools.ASSETS / "tests" / "result.gif"
    result_path.write_bytes(res)
