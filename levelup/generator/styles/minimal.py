"""
Minimal/Clean Profile Style

A modern, minimalist card with a focus on readability and clean design.
Features:
- Dark semi-transparent overlay for readability
- Large avatar with subtle border
- Typography-focused with generous spacing
- Subtle accent colors
- Modern aesthetic inspired by Discord/Spotify cards
"""

import logging
import typing as t
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

try:
    from .. import imgtools
    from ..pilmojisrc.core import Pilmoji
except ImportError:
    import sys

    parent_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(parent_dir))
    import imgtools
    from pilmojisrc.core import Pilmoji

log = logging.getLogger("red.vrt.levelup.generator.styles.minimal")
_ = Translator("LevelUp", __file__)


def generate_minimal_profile(
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
    blur: bool = False,  # Ignored in minimal - we always use overlay
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
    """
    Generate a minimal/clean profile card.

    Features a dark overlay for readability, large avatar, and clean typography.
    """
    # Color setup - minimal uses softer colors
    user_color = user_color or base_color
    stat_color = stat_color or (200, 200, 200)  # Slightly dimmer for stats
    level_bar_color = level_bar_color or base_color

    # Download images if URLs
    if isinstance(background_bytes, str) and background_bytes.startswith("http"):
        background_bytes = imgtools.download_image(background_bytes)

    if isinstance(avatar_bytes, str) and avatar_bytes.startswith("http"):
        avatar_bytes = imgtools.download_image(avatar_bytes)

    if isinstance(prestige_emoji, str) and prestige_emoji.startswith("http"):
        prestige_emoji = imgtools.download_image(prestige_emoji)

    if isinstance(role_icon, str) and role_icon.startswith("http"):
        role_icon = imgtools.download_image(role_icon)

    # Load background
    if background_bytes:
        try:
            bg = Image.open(BytesIO(background_bytes))
        except UnidentifiedImageError as e:
            if reraise:
                raise e
            log.error("Failed to open background image", exc_info=e)
            bg = imgtools.get_random_background()
    else:
        bg = imgtools.get_random_background()

    # Load avatar
    if avatar_bytes:
        pfp = Image.open(BytesIO(avatar_bytes))
    else:
        pfp = imgtools.DEFAULT_PFP.copy()

    pfp_animated = getattr(pfp, "is_animated", False)
    bg_animated = getattr(bg, "is_animated", False)

    # Card dimensions - slightly narrower than default for a modern feel
    card_width = 900
    card_height = 400
    card_size = (card_width, card_height)

    # Layout constants
    padding = 30
    avatar_size = 180
    avatar_x = padding + 20
    avatar_y = (card_height - avatar_size) // 2

    # Content area starts after avatar
    content_x = avatar_x + avatar_size + 40
    content_width = card_width - content_x - padding

    # Establish font
    font_path = font_path or imgtools.DEFAULT_FONT
    if isinstance(font_path, str):
        font_path = Path(font_path)
    if not font_path.exists():
        if (imgtools.DEFAULT_FONTS / font_path.name).exists():
            font_path = imgtools.DEFAULT_FONTS / font_path.name
        else:
            font_path = imgtools.DEFAULT_FONT
    font_path = str(font_path)

    def create_stats_layer() -> Image.Image:
        """Create the stats overlay layer"""
        stats = Image.new("RGBA", card_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(stats)

        # --- Username ---
        username_fontsize = 48
        username_font = ImageFont.truetype(font_path, username_fontsize)
        username_y = avatar_y + 10

        with Pilmoji(stats) as pilmoji:
            # Shrink if needed
            max_width = content_width - 100  # Leave room for stars
            while pilmoji.getsize(username, username_font)[0] > max_width and username_fontsize > 20:
                username_fontsize -= 2
                username_font = ImageFont.truetype(font_path, username_fontsize)

            pilmoji.text(
                xy=(content_x, username_y),
                text=username,
                fill=user_color,
                font=username_font,
            )

        # --- Stars (top right of content area) ---
        stars_text = humanize_number(stars)
        stars_fontsize = 32
        stars_font = ImageFont.truetype(font_path, stars_fontsize)
        stars_width = stars_font.getlength(stars_text) + 35  # Icon + text
        stars_x = card_width - padding - int(stars_width)

        # Star icon (smaller)
        star_icon = imgtools.STAR.resize((28, 28), Image.Resampling.LANCZOS)
        stats.paste(star_icon, (stars_x, username_y + 8), star_icon)
        draw.text(
            xy=(stars_x + 32, username_y + 5),
            text=stars_text,
            fill=stat_color,
            font=stars_font,
        )

        # --- Prestige badge (if any) ---
        prestige_y = username_y + username_fontsize + 5
        if prestige:
            prestige_text = _("Prestige {}").format(prestige)
            prestige_fontsize = 22
            prestige_font = ImageFont.truetype(font_path, prestige_fontsize)

            # Draw prestige badge background
            badge_padding = 8
            text_width = prestige_font.getlength(prestige_text)
            badge_width = int(text_width) + badge_padding * 2
            badge_height = prestige_fontsize + badge_padding

            if prestige_emoji:
                badge_width += 28  # Room for emoji

            # Rounded badge background
            badge_img = Image.new("RGBA", (badge_width, badge_height), (0, 0, 0, 0))
            badge_draw = ImageDraw.Draw(badge_img)
            badge_draw.rounded_rectangle(
                [(0, 0), (badge_width, badge_height)],
                radius=badge_height // 2,
                fill=(*level_bar_color, 40),  # Semi-transparent accent
                outline=(*level_bar_color, 100),
                width=1,
            )

            # Prestige emoji
            text_x = badge_padding
            if prestige_emoji:
                try:
                    p_icon = Image.open(BytesIO(prestige_emoji)).resize((22, 22), Image.Resampling.LANCZOS)
                    if p_icon.mode != "RGBA":
                        p_icon = p_icon.convert("RGBA")
                    badge_img.paste(p_icon, (badge_padding, (badge_height - 22) // 2), p_icon)
                    text_x += 26
                except Exception:
                    pass

            badge_draw.text(
                xy=(text_x, badge_padding // 2),
                text=prestige_text,
                fill=user_color,
                font=prestige_font,
            )
            stats.paste(badge_img, (content_x, prestige_y), badge_img)
            prestige_y += badge_height + 10

        # --- Stats row ---
        stats_y = prestige_y + 15 if prestige else username_y + username_fontsize + 25
        stat_fontsize = 24
        stat_font = ImageFont.truetype(font_path, stat_fontsize)
        label_fontsize = 16
        label_font = ImageFont.truetype(font_path, label_fontsize)

        # Define stats to show
        stat_items = [
            (_("RANK"), f"#{humanize_number(position)}"),
            (_("LEVEL"), humanize_number(level)),
            (_("MESSAGES"), humanize_number(messages)),
            (_("VOICE"), imgtools.abbreviate_time(voicetime)),
        ]

        # Calculate spacing
        stat_spacing = content_width // len(stat_items)

        for i, (label, value) in enumerate(stat_items):
            x = content_x + (i * stat_spacing)

            # Label (smaller, dimmer)
            draw.text(
                xy=(x, stats_y),
                text=label,
                fill=(*stat_color[:3],) if len(stat_color) == 3 else stat_color,
                font=label_font,
            )

            # Value (larger, brighter)
            draw.text(
                xy=(x, stats_y + label_fontsize + 4),
                text=value,
                fill=user_color,
                font=stat_font,
            )

        # --- Balance (if any) ---
        if balance:
            balance_y = stats_y + label_fontsize + stat_fontsize + 20
            balance_text = f"{humanize_number(balance)} {currency_name}"
            balance_fontsize = 20
            balance_font = ImageFont.truetype(font_path, balance_fontsize)

            with Pilmoji(stats) as pilmoji:
                pilmoji.text(
                    xy=(content_x, balance_y),
                    text=balance_text,
                    fill=stat_color,
                    font=balance_font,
                )

        # --- Progress bar ---
        bar_y = card_height - padding - 50
        bar_width = content_width
        bar_height = 20

        progress = (current_xp - previous_xp) / (next_xp - previous_xp) if next_xp > previous_xp else 0
        progress = max(0.0, min(1.0, progress))

        # Bar background (dark, rounded)
        bar_bg_color = (40, 40, 40, 200)
        draw.rounded_rectangle(
            [(content_x, bar_y), (content_x + bar_width, bar_y + bar_height)],
            radius=bar_height // 2,
            fill=bar_bg_color,
        )

        # Bar fill
        if progress > 0:
            fill_width = max(bar_height, int(bar_width * progress))  # Min width = height for rounded look
            draw.rounded_rectangle(
                [(content_x, bar_y), (content_x + fill_width, bar_y + bar_height)],
                radius=bar_height // 2,
                fill=(*level_bar_color, 255),
            )

        # XP text below bar
        current = current_xp - previous_xp
        goal = next_xp - previous_xp
        xp_text = f"{humanize_number(current)} / {humanize_number(goal)} XP"
        xp_fontsize = 16
        xp_font = ImageFont.truetype(font_path, xp_fontsize)
        draw.text(
            xy=(content_x, bar_y + bar_height + 6),
            text=xp_text,
            fill=stat_color,
            font=xp_font,
        )

        # Percentage on right side
        percent_text = f"{int(progress * 100)}%"
        percent_width = xp_font.getlength(percent_text)
        draw.text(
            xy=(content_x + bar_width - percent_width, bar_y + bar_height + 6),
            text=percent_text,
            fill=user_color,
            font=xp_font,
        )

        # --- Role icon (top left corner if present) ---
        if role_icon:
            try:
                r_icon = Image.open(BytesIO(role_icon)).resize((32, 32), Image.Resampling.LANCZOS)
                if r_icon.mode != "RGBA":
                    r_icon = r_icon.convert("RGBA")
                stats.paste(r_icon, (padding, padding), r_icon)
            except Exception as e:
                if reraise:
                    raise e
                log.debug(f"Failed to paste role icon: {e}")

        return stats

    def create_avatar_layer(pfp_frame: Image.Image) -> Image.Image:
        """Create the avatar with border"""
        layer = Image.new("RGBA", card_size, (0, 0, 0, 0))

        if pfp_frame.mode != "RGBA":
            pfp_frame = pfp_frame.convert("RGBA")

        pfp_frame = pfp_frame.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
        pfp_frame = imgtools.make_profile_circle(pfp_frame)

        # Create a subtle border ring
        border_size = avatar_size + 8
        border = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border)
        border_draw.ellipse(
            [(0, 0), (border_size - 1, border_size - 1)],
            fill=(*level_bar_color, 60),
            outline=(*level_bar_color, 150),
            width=2,
        )

        # Paste border then avatar
        border_x = avatar_x - 4
        border_y = avatar_y - 4
        layer.paste(border, (border_x, border_y), border)
        layer.paste(pfp_frame, (avatar_x, avatar_y), pfp_frame)

        # Status indicator
        status_size = 36
        status_icon = imgtools.STATUS[status].resize((status_size, status_size), Image.Resampling.LANCZOS)
        status_x = avatar_x + avatar_size - status_size + 5
        status_y = avatar_y + avatar_size - status_size + 5
        layer.paste(status_icon, (status_x, status_y), status_icon)

        return layer

    def prepare_background(bg_frame: Image.Image) -> Image.Image:
        """Prepare background with overlay"""
        if bg_frame.mode != "RGBA":
            bg_frame = bg_frame.convert("RGBA")

        bg_frame = imgtools.fit_aspect_ratio(bg_frame, card_size)

        # Apply slight blur for depth
        bg_frame = bg_frame.filter(ImageFilter.GaussianBlur(2))

        # Dark overlay for readability
        overlay = Image.new("RGBA", card_size, (0, 0, 0, 140))
        bg_frame = Image.alpha_composite(bg_frame, overlay)

        # Round corners
        bg_frame = imgtools.round_image_corners(bg_frame, 30)

        return bg_frame

    # --- Static render ---
    if not render_gif or (not pfp_animated and not bg_animated):
        card = prepare_background(bg.copy())
        stats_layer = create_stats_layer()
        avatar_layer = create_avatar_layer(pfp.copy())

        card = Image.alpha_composite(card, stats_layer)
        card = Image.alpha_composite(card, avatar_layer)

        if debug:
            card.show()

        buffer = BytesIO()
        card.save(buffer, format="WEBP", quality=90)
        return buffer.getvalue(), False

    # --- Animated render (avatar animated, bg static) ---
    if pfp_animated and not bg_animated:
        card_base = prepare_background(bg.copy())
        stats_layer = create_stats_layer()
        card_base = Image.alpha_composite(card_base, stats_layer)

        avg_duration = imgtools.get_avg_duration(pfp)
        frames: t.List[Image.Image] = []

        for frame_num in range(pfp.n_frames):
            pfp.seek(frame_num)
            frame = card_base.copy()
            avatar_layer = create_avatar_layer(pfp.copy())
            frame = Image.alpha_composite(frame, avatar_layer)
            frames.append(frame)

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

    # --- Animated render (bg animated, avatar static) ---
    if bg_animated and not pfp_animated:
        stats_layer = create_stats_layer()
        avatar_layer = create_avatar_layer(pfp.copy())

        avg_duration = imgtools.get_avg_duration(bg)
        frames: t.List[Image.Image] = []

        for frame_num in range(bg.n_frames):
            bg.seek(frame_num)
            frame = prepare_background(bg.copy())
            frame = Image.alpha_composite(frame, stats_layer)
            frame = Image.alpha_composite(frame, avatar_layer)
            frames.append(frame)

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

    # --- Both animated (favor avatar timing) ---
    stats_layer = create_stats_layer()
    pfp_duration = imgtools.get_avg_duration(pfp)
    bg_duration = imgtools.get_avg_duration(bg)

    pfp_frames = pfp.n_frames
    bg_frames = bg.n_frames

    # Use avatar frame count, cycle background
    frames: t.List[Image.Image] = []
    for frame_num in range(pfp_frames):
        pfp.seek(frame_num)
        bg_frame_idx = (frame_num * bg_duration // pfp_duration) % bg_frames
        bg.seek(bg_frame_idx)

        frame = prepare_background(bg.copy())
        frame = Image.alpha_composite(frame, stats_layer)
        avatar_layer = create_avatar_layer(pfp.copy())
        frame = Image.alpha_composite(frame, avatar_layer)
        frames.append(frame)

    buffer = BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=pfp_duration,
        loop=0,
        optimize=True,
    )
    buffer.seek(0)

    if debug:
        Image.open(buffer).show()

    return buffer.getvalue(), True


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("PIL").setLevel(logging.INFO)

    test_banner = (imgtools.ASSETS / "tests" / "banner3.gif").read_bytes()
    test_avatar = (imgtools.ASSETS / "tests" / "tree.gif").read_bytes()
    test_icon = (imgtools.ASSETS / "tests" / "icon.png").read_bytes()

    res, animated = generate_minimal_profile(
        background_bytes=test_banner,
        avatar_bytes=test_avatar,
        username="Vertyco",
        status="online",
        level=999,
        messages=420691337,
        voicetime=399815,
        stars=69333,
        prestige=5,
        prestige_emoji=test_icon,
        balance=1000000,
        currency_name="Coins 💰",
        previous_xp=1000,
        current_xp=3500,
        next_xp=5000,
        role_icon=test_icon,
        render_gif=True,
        debug=True,
    )

    ext = "gif" if animated else "webp"
    result_path = imgtools.ASSETS / "tests" / f"minimal_result.{ext}"
    result_path.write_bytes(res)
    print(f"Saved to {result_path}")
