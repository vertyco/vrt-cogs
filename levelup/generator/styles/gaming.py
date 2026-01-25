"""
Gaming/HUD Profile Style

A video game HUD-inspired profile card.
Features:
- Corner brackets/frames like targeting HUD
- Health/XP bar styled like game UI
- Stats displayed like RPG character sheet
- Futuristic game overlay aesthetic
- Optional "damage" indicators for low stats
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

log = logging.getLogger("red.vrt.levelup.generator.styles.gaming")
_ = Translator("LevelUp", __file__)


def draw_corner_brackets(
    draw: ImageDraw.ImageDraw,
    bbox: t.Tuple[int, int, int, int],
    color: t.Tuple[int, int, int],
    length: int = 30,
    thickness: int = 3,
    gap: int = 5,
):
    """Draw HUD-style corner brackets"""
    x1, y1, x2, y2 = bbox

    # Top-left corner
    draw.line([(x1, y1 + gap), (x1, y1), (x1 + length, y1)], fill=color, width=thickness)
    # Top-right corner
    draw.line([(x2 - length, y1), (x2, y1), (x2, y1 + gap)], fill=color, width=thickness)
    # Bottom-left corner
    draw.line([(x1, y2 - gap), (x1, y2), (x1 + length, y2)], fill=color, width=thickness)
    # Bottom-right corner
    draw.line([(x2 - length, y2), (x2, y2), (x2, y2 - gap)], fill=color, width=thickness)


def draw_hud_bar(
    img: Image.Image,
    position: t.Tuple[int, int],
    size: t.Tuple[int, int],
    progress: float,
    fill_color: t.Tuple[int, int, int],
    bg_color: t.Tuple[int, int, int] = (30, 30, 40),
    border_color: t.Tuple[int, int, int] = (100, 100, 120),
    segmented: bool = True,
    segment_count: int = 20,
) -> None:
    """Draw a gaming-style segmented progress bar"""
    draw = ImageDraw.Draw(img)
    x, y = position
    width, height = size

    # Background
    draw.rectangle([(x, y), (x + width, y + height)], fill=(*bg_color, 200))

    # Border
    draw.rectangle([(x, y), (x + width, y + height)], outline=border_color, width=1)

    # Fill
    fill_width = int(width * max(0, min(1, progress)))
    if fill_width > 0:
        if segmented:
            segment_width = width // segment_count
            gap = 2
            filled_segments = int(progress * segment_count)
            for i in range(filled_segments):
                seg_x = x + (i * segment_width) + gap
                seg_width = segment_width - gap * 2
                if seg_x + seg_width <= x + width:
                    # Gradient effect - brighter towards the end of fill
                    brightness = 0.7 + (0.3 * (i / max(1, filled_segments - 1))) if filled_segments > 1 else 1.0
                    seg_color = tuple(int(c * brightness) for c in fill_color)
                    draw.rectangle(
                        [(seg_x, y + 2), (seg_x + seg_width, y + height - 2)],
                        fill=(*seg_color, 255),
                    )
        else:
            draw.rectangle([(x + 2, y + 2), (x + fill_width - 2, y + height - 2)], fill=(*fill_color, 255))

    # Shine effect on top
    shine = Image.new("RGBA", (width, height // 3), (255, 255, 255, 30))
    img.paste(shine, (x, y), shine)


def generate_gaming_profile(
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
    base_color: t.Tuple[int, int, int] = (50, 205, 50),  # Green (like health bar)
    user_color: t.Optional[t.Tuple[int, int, int]] = None,
    stat_color: t.Optional[t.Tuple[int, int, int]] = None,
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = None,
    font_path: t.Optional[t.Union[str, Path]] = None,
    render_gif: bool = False,
    debug: bool = False,
    reraise: bool = False,
    **kwargs,
) -> t.Tuple[bytes, bool]:
    """Generate a gaming/HUD style profile card."""
    # Gaming color scheme
    user_color = user_color or (255, 255, 255)
    stat_color = stat_color or (180, 180, 200)
    level_bar_color = level_bar_color or base_color

    # HUD accent colors
    hud_primary = base_color  # Main HUD color
    hud_secondary = (255, 200, 50)  # Gold/yellow for highlights
    hud_danger = (255, 60, 60)  # Red for warnings

    # Download images if URLs
    if isinstance(background_bytes, str) and background_bytes.startswith("http"):
        background_bytes = imgtools.download_image(background_bytes)
    if isinstance(avatar_bytes, str) and avatar_bytes.startswith("http"):
        avatar_bytes = imgtools.download_image(avatar_bytes)
    if isinstance(prestige_emoji, str) and prestige_emoji.startswith("http"):
        prestige_emoji = imgtools.download_image(prestige_emoji)
    if isinstance(role_icon, str) and role_icon.startswith("http"):
        role_icon = imgtools.download_image(role_icon)

    # Load images
    if background_bytes:
        try:
            bg = Image.open(BytesIO(background_bytes))
        except UnidentifiedImageError as e:
            if reraise:
                raise e
            bg = imgtools.get_random_background()
    else:
        bg = imgtools.get_random_background()

    if avatar_bytes:
        pfp = Image.open(BytesIO(avatar_bytes))
    else:
        pfp = imgtools.DEFAULT_PFP.copy()

    pfp_animated = getattr(pfp, "is_animated", False)
    bg_animated = getattr(bg, "is_animated", False)

    # Card dimensions
    card_width = 950
    card_height = 450
    card_size = (card_width, card_height)

    # Layout
    padding = 25
    avatar_size = 160
    avatar_x = padding + 40
    avatar_y = padding + 60

    # Stats panel on right side
    stats_x = avatar_x + avatar_size + 60
    stats_width = card_width - stats_x - padding - 20

    # Fixed font for this style (ignore font_path parameter)
    font_path = str(imgtools.DEFAULT_FONT)  # BebasNeue

    def create_stats_layer() -> Image.Image:
        """Create the HUD stats overlay"""
        stats = Image.new("RGBA", card_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(stats)

        # --- Main HUD frame ---
        frame_padding = 15
        draw_corner_brackets(
            draw,
            (frame_padding, frame_padding, card_width - frame_padding, card_height - frame_padding),
            hud_primary,
            length=50,
            thickness=3,
        )

        # --- Header bar ---
        header_height = 45
        header_y = padding + 5
        draw.rectangle(
            [(padding + 30, header_y), (card_width - padding - 30, header_y + header_height)],
            fill=(20, 20, 30, 180),
            outline=hud_primary,
            width=1,
        )

        # Username in header
        username_fontsize = 32
        username_font = ImageFont.truetype(font_path, username_fontsize)

        with Pilmoji(stats) as pilmoji:
            max_name_width = card_width - 300
            while pilmoji.getsize(username, username_font)[0] > max_name_width and username_fontsize > 18:
                username_fontsize -= 2
                username_font = ImageFont.truetype(font_path, username_fontsize)

            name_width = pilmoji.getsize(username, username_font)[0]
            name_x = (card_width - name_width) // 2
            pilmoji.text(
                xy=(name_x, header_y + (header_height - username_fontsize) // 2),
                text=username,
                fill=user_color,
                font=username_font,
            )

        # Rank badge on left of header
        rank_text = f"#{position}"
        rank_fontsize = 22
        rank_font = ImageFont.truetype(font_path, rank_fontsize)
        draw.text(
            xy=(padding + 45, header_y + (header_height - rank_fontsize) // 2),
            text=rank_text,
            fill=hud_secondary,
            font=rank_font,
        )

        # Level badge on right of header (with optional prestige emoji)
        level_text = f"LV.{level}"
        level_fontsize = 22
        level_font = ImageFont.truetype(font_path, level_fontsize)
        level_width = level_font.getlength(level_text)

        # Calculate right edge position for level + optional prestige emoji
        right_edge = card_width - padding - 45
        prestige_icon_size = 24

        # If we have a prestige emoji, make room for it
        if prestige and prestige_emoji:
            try:
                p_icon = Image.open(BytesIO(prestige_emoji)).resize(
                    (prestige_icon_size, prestige_icon_size), Image.Resampling.LANCZOS
                )
                if p_icon.mode != "RGBA":
                    p_icon = p_icon.convert("RGBA")
                # Place prestige emoji at right edge
                emoji_y = header_y + (header_height - prestige_icon_size) // 2
                stats.paste(p_icon, (right_edge - prestige_icon_size, emoji_y), p_icon)
                # Level text goes to the left of the emoji
                right_edge -= prestige_icon_size + 8
            except Exception:
                pass

        draw.text(
            xy=(right_edge - level_width, header_y + (header_height - level_fontsize) // 2),
            text=level_text,
            fill=hud_secondary,
            font=level_font,
        )

        # --- Avatar frame with corner brackets ---
        avatar_frame_padding = 15
        draw_corner_brackets(
            draw,
            (
                avatar_x - avatar_frame_padding,
                avatar_y - avatar_frame_padding,
                avatar_x + avatar_size + avatar_frame_padding,
                avatar_y + avatar_size + avatar_frame_padding,
            ),
            hud_primary,
            length=25,
            thickness=2,
        )

        # --- Stats panel ---
        panel_y = avatar_y - 10  # Shift panel up slightly
        panel_height = avatar_size + 40

        # Semi-transparent panel background
        panel_bg = Image.new("RGBA", (stats_width, panel_height), (15, 15, 25, 180))
        stats.paste(panel_bg, (stats_x, panel_y), panel_bg)

        # Panel border
        draw.rectangle(
            [(stats_x, panel_y), (stats_x + stats_width, panel_y + panel_height)],
            outline=(*hud_primary, 150),
            width=1,
        )

        # --- Stats inside panel ---
        stat_items = [
            ("MESSAGES", humanize_number(messages), None),
            ("VOICE TIME", imgtools.abbreviate_time(voicetime), None),
            ("STARS", humanize_number(stars), hud_secondary),
        ]

        if balance:
            stat_items.append((currency_name.upper(), humanize_number(balance), hud_secondary))

        if prestige:
            stat_items.insert(0, ("PRESTIGE", str(prestige), hud_danger))

        label_fontsize = 12
        value_fontsize = 24
        label_font = ImageFont.truetype(font_path, label_fontsize)
        value_font = ImageFont.truetype(font_path, value_fontsize)

        stat_y = panel_y + 8  # Tighter top padding
        stat_spacing = (panel_height - 20) // len(stat_items)

        for i, (label, value, special_color) in enumerate(stat_items):
            y = stat_y + (i * stat_spacing)

            # Label
            draw.text(xy=(stats_x + 15, y), text=label, fill=stat_color, font=label_font)

            # Value (right-aligned)
            value_color = special_color or user_color
            with Pilmoji(stats) as pilmoji:
                value_width = pilmoji.getsize(value, value_font)[0]
                pilmoji.text(
                    xy=(stats_x + stats_width - 15 - value_width, y + label_fontsize - 10),
                    text=value,
                    fill=value_color,
                    font=value_font,
                )

            # Separator line (except for last item)
            if i < len(stat_items) - 1:
                line_y = y + stat_spacing - 5
                draw.line(
                    [(stats_x + 10, line_y), (stats_x + stats_width - 10, line_y)],
                    fill=(*hud_primary, 50),
                    width=1,
                )

        # --- XP Bar (bottom) ---
        bar_y = card_height - padding - 55
        bar_width = card_width - padding * 2 - 80
        bar_height = 25
        bar_x = padding + 40

        progress = (current_xp - previous_xp) / (next_xp - previous_xp) if next_xp > previous_xp else 0
        progress = max(0.0, min(1.0, progress))

        # XP label
        xp_label_font = ImageFont.truetype(font_path, 14)
        draw.text(xy=(bar_x, bar_y - 18), text="EXPERIENCE", fill=stat_color, font=xp_label_font)

        # Draw the bar
        draw_hud_bar(
            stats,
            (bar_x, bar_y),
            (bar_width, bar_height),
            progress,
            level_bar_color,
            segmented=True,
            segment_count=25,
        )

        # XP values
        current = current_xp - previous_xp
        goal = next_xp - previous_xp
        xp_text = f"{humanize_number(current)} / {humanize_number(goal)}"
        xp_font = ImageFont.truetype(font_path, 16)
        xp_width = xp_font.getlength(xp_text)
        draw.text(
            xy=(bar_x + bar_width - xp_width, bar_y + bar_height + 5),
            text=xp_text,
            fill=stat_color,
            font=xp_font,
        )

        # Percentage
        pct_text = f"{int(progress * 100)}%"
        draw.text(xy=(bar_x, bar_y + bar_height + 5), text=pct_text, fill=hud_secondary, font=xp_font)

        # --- Role icon (bottom right corner, near XP bar) ---
        if role_icon:
            try:
                r_icon = Image.open(BytesIO(role_icon)).resize((28, 28), Image.Resampling.LANCZOS)
                if r_icon.mode != "RGBA":
                    r_icon = r_icon.convert("RGBA")
                # Place in bottom right, aligned with XP bar area
                stats.paste(r_icon, (bar_x + bar_width + 15, bar_y - 2), r_icon)
            except Exception:
                pass

        return stats

    def create_avatar_layer(pfp_frame: Image.Image) -> Image.Image:
        """Create avatar"""
        layer = Image.new("RGBA", card_size, (0, 0, 0, 0))

        if pfp_frame.mode != "RGBA":
            pfp_frame = pfp_frame.convert("RGBA")

        pfp_frame = pfp_frame.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

        # Keep square for gaming aesthetic (no circle crop)
        layer.paste(pfp_frame, (avatar_x, avatar_y), pfp_frame)

        # Status indicator
        status_size = 35
        status_icon = imgtools.STATUS[status].resize((status_size, status_size), Image.Resampling.LANCZOS)
        status_x = avatar_x + avatar_size - status_size + 5
        status_y = avatar_y + avatar_size - status_size + 5

        # Status background
        status_bg = Image.new("RGBA", (status_size + 6, status_size + 6), (20, 20, 30, 200))
        layer.paste(status_bg, (status_x - 3, status_y - 3), status_bg)
        layer.paste(status_icon, (status_x, status_y), status_icon)

        return layer

    def prepare_background(bg_frame: Image.Image) -> Image.Image:
        """Prepare gaming-style background"""
        if bg_frame.mode != "RGBA":
            bg_frame = bg_frame.convert("RGBA")

        bg_frame = imgtools.fit_aspect_ratio(bg_frame, card_size)

        if blur:
            bg_frame = bg_frame.filter(ImageFilter.GaussianBlur(2))

        # Darken
        from PIL import ImageEnhance

        bg_frame = ImageEnhance.Brightness(bg_frame).enhance(0.4)

        # Subtle color overlay
        overlay = Image.new("RGBA", card_size, (10, 15, 25, 100))
        bg_frame = Image.alpha_composite(bg_frame, overlay)

        # Vignette effect
        vignette = Image.new("RGBA", card_size, (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        for i in range(50):
            alpha = int(80 * (i / 50))
            vignette_draw.rectangle(
                [(i, i), (card_width - i, card_height - i)],
                outline=(0, 0, 0, alpha),
            )
        bg_frame = Image.alpha_composite(bg_frame, vignette)

        bg_frame = imgtools.round_image_corners(bg_frame, 15)

        return bg_frame

    # --- Rendering ---
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

    # Animated renders
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
            buffer, format="GIF", save_all=True, append_images=frames[1:], duration=avg_duration, loop=0, optimize=True
        )
        buffer.seek(0)

        if debug:
            Image.open(buffer).show()

        return buffer.getvalue(), True

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
            buffer, format="GIF", save_all=True, append_images=frames[1:], duration=avg_duration, loop=0, optimize=True
        )
        buffer.seek(0)

        if debug:
            Image.open(buffer).show()

        return buffer.getvalue(), True

    # Both animated
    stats_layer = create_stats_layer()
    pfp_duration = imgtools.get_avg_duration(pfp)
    bg_duration = imgtools.get_avg_duration(bg)
    pfp_frames = pfp.n_frames
    bg_frames = bg.n_frames

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
        buffer, format="GIF", save_all=True, append_images=frames[1:], duration=pfp_duration, loop=0, optimize=True
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

    res, animated = generate_gaming_profile(
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
        currency_name="Gold",
        previous_xp=1000,
        current_xp=3500,
        next_xp=5000,
        role_icon=test_icon,
        base_color=(50, 205, 50),  # Green
        render_gif=True,
        debug=True,
    )

    ext = "gif" if animated else "webp"
    result_path = imgtools.ASSETS / "tests" / f"gaming_result.{ext}"
    result_path.write_bytes(res)
    print(f"Saved to {result_path}")
