import logging
import os
import random
from abc import ABC
from io import BytesIO
from math import ceil, sqrt
from pathlib import Path
from typing import List, Union

import colorgram
import requests
from perftracker import perf
from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..utils.core import Pilmoji

log = logging.getLogger("red.vrt.levelup.generator")
_ = Translator("LevelUp", __file__)
ASPECT_RATIO = (21, 9)


@cog_i18n(_)
class Generator(MixinMeta, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Included Assets
        maindir = bundled_data_path(self)
        self.star = maindir / "star.png"
        self.default_pfp = maindir / "defaultpfp.png"
        self.status = {
            "online": maindir / "online.png",
            "offline": maindir / "offline.png",
            "idle": maindir / "idle.png",
            "dnd": maindir / "dnd.png",
            "streaming": maindir / "streaming.png",
        }
        self.font = str(maindir / "font.ttf")
        self.fonts = maindir / "fonts"
        self.backgrounds = maindir / "backgrounds"

        # Saved Assets
        savedir = cog_data_path(self)
        self.saved_bgs = savedir / "backgrounds"
        self.saved_bgs.mkdir(exist_ok=True)
        self.saved_fonts = savedir / "fonts"
        self.saved_fonts.mkdir(exist_ok=True)

        # Cleanup old files from conversion to webp
        delete: List[Path] = []
        for file in self.backgrounds.iterdir():
            if file.name.endswith(".py") or file.is_dir():
                continue
            if not file.name.endswith(".webp"):
                delete.append(file)
        for i in delete:
            i.unlink(missing_ok=True)

    @perf(max_entries=1000)
    def generate_profile(
        self,
        bg_image: str = None,
        profile_image: str = "https://i.imgur.com/sUYWCve.png",
        level: int = 1,
        prev_xp: int = 0,
        user_xp: int = 0,
        next_xp: int = 100,
        user_position: str = "1",
        user_name: str = "Unknown#0117",
        user_status: str = "online",
        colors: dict = None,
        messages: str = "0",
        voice: str = "None",
        prestige: int = 0,
        emoji: str = None,
        stars: str = "0",
        balance: int = 0,
        currency: str = "credits",
        role_icon: str = None,
        font_name: str = None,
        render_gifs: bool = False,
        blur: bool = False,
    ):
        # get profile pic
        if profile_image:
            pfp_image = self.get_image_content_from_url(str(profile_image))
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)
        # Get background
        available = list(self.backgrounds.iterdir()) + list(self.saved_bgs.iterdir())
        card = None
        if bg_image and str(bg_image) != "random":
            if not bg_image.lower().startswith("http"):
                for file in available:
                    if bg_image.lower() in file.name.lower():
                        try:
                            card = Image.open(file)
                            break
                        except OSError:
                            log.info(f"Failed to load {bg_image}")

            if not card and bg_image.lower().startswith("http"):
                try:
                    bg_bytes = self.get_image_content_from_url(bg_image)
                    card = Image.open(BytesIO(bg_bytes))
                except UnidentifiedImageError:
                    pass

        if not card:
            card = self.get_random_background()

        card = self.force_aspect_ratio(card).convert("RGBA").resize((1050, 450), Image.Resampling.NEAREST)

        # Colors
        # Sample colors from profile pic to use for default colors
        rgbs = self.get_img_colors(profile, 8)
        base = random.choice(rgbs)
        namecolor = random.choice(rgbs)
        statcolor = random.choice(rgbs)
        lvlbarcolor = random.choice(rgbs)
        # Color distancing is more strict if user hasn't defined color
        namedistance = 200
        statdistance = 200
        lvldistance = 100
        # Will always have colors dict unless testing
        if colors:
            # Relax distance for colors that are defined
            if colors["base"] != (0, 0, 0):
                base = colors["base"]
            if colors["name"]:
                namecolor = colors["name"]
                namedistance = 10
            if colors["stat"]:
                statcolor = colors["stat"]
                statdistance = 10
            if colors["levelbar"]:
                lvlbarcolor = colors["levelbar"]
                lvldistance = 10
            else:
                lvlbarcolor = base

        default_fill = (0, 0, 0)

        # Coord setup
        name_y = 35
        stats_y = 160
        bar_start = 450
        bar_end = 1030
        bar_top = 380
        bar_bottom = 420
        circle_x = 60
        circle_y = 75

        star_text_x = 960
        star_text_y = 35
        star_icon_x = 900
        star_icon_y = 30

        stroke_width = 2

        iters = 0

        # x1, y1, x2, y2
        # Sample name box colors and make sure they're not too similar with the background
        namebox = (bar_start, name_y, bar_start + 50, name_y + 100)
        namesection = self.get_sample_section(card, namebox)
        namebg = self.get_img_color(namesection)
        namefill = default_fill
        while self.distance(namecolor, namebg) < namedistance:
            namecolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break
        if self.distance(namefill, namecolor) < namedistance - 50:
            namefill = self.inv_rgb(namefill)

        # Sample stat box colors and make sure they're not too similar with the background
        statbox = (bar_start, stats_y, bar_start + 400, bar_top)
        statsection = self.get_sample_section(card, statbox)
        statbg = self.get_img_color(statsection)
        statstxtfill = default_fill
        while self.distance(statcolor, statbg) < statdistance:
            statcolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break
        if self.distance(statstxtfill, statcolor) < statdistance - 50:
            statstxtfill = self.inv_rgb(statstxtfill)

        lvlbox = (bar_start, bar_top, bar_end, bar_bottom)
        lvlsection = self.get_sample_section(card, lvlbox)
        lvlbg = self.get_img_color(lvlsection)
        while self.distance(lvlbarcolor, lvlbg) < lvldistance:
            lvlbarcolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                # iters = 0
                break

        # Place semi-transparent box over right side
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        transparent_box = Image.new("RGBA", card.size, (0, 0, 0, 100))
        blank.paste(transparent_box, (bar_start - 20, 0))

        # Make the semi-transparent box area blurry
        if blur:
            blurred = card.filter(ImageFilter.GaussianBlur(3))
            blurred = blurred.crop(((bar_start - 20), 0, card.size[0], card.size[1]))
            card.paste(blurred, (bar_start - 20, 0), blurred)
        final = Image.alpha_composite(card, blank)

        # Make the level progress bar
        progress_bar = Image.new("RGBA", (card.size[0] * 4, card.size[1] * 4), (255, 255, 255, 0))
        progress_bar_draw = ImageDraw.Draw(progress_bar)
        # Calculate data for level bar
        user_xp_progress = user_xp - prev_xp
        next_xp_diff = next_xp - prev_xp
        xp_ratio = user_xp_progress / next_xp_diff
        end_of_inner_bar = ((bar_end - bar_start) * xp_ratio) + bar_start
        # Rectangle 0:left x, 1:top y, 2:right x, 3:bottom y
        # Draw level bar outline
        thickness = 8
        progress_bar_draw.rounded_rectangle(
            (bar_start * 4, bar_top * 4, bar_end * 4, bar_bottom * 4),
            fill=(255, 255, 255, 0),
            outline=lvlbarcolor,
            width=thickness,
            radius=90,
        )
        # Draw inner level bar 1 pixel smaller on each side
        if end_of_inner_bar > bar_start + 10:
            progress_bar_draw.rounded_rectangle(
                (
                    bar_start * 4 + thickness,
                    bar_top * 4 + thickness,
                    end_of_inner_bar * 4 - thickness,
                    bar_bottom * 4 - thickness,
                ),
                fill=lvlbarcolor,
                radius=89,
            )
        progress_bar = progress_bar.resize(card.size, Image.Resampling.NEAREST)
        # Image with level bar and pfp on background
        final = Image.alpha_composite(final, progress_bar)

        # Stat strings
        rank = _("Rank: #") + str(user_position)
        leveltxt = _("Level: ") + str(level)
        exp = (
            _("Exp: ")
            + f"{humanize_number(user_xp_progress)}/{humanize_number(next_xp_diff)} ({humanize_number(user_xp)} total)"
        )
        message_count = _("Messages: ") + messages
        voice = _("Voice: ") + voice
        stars = str(stars)
        bal = _("Balance: ") + f"{humanize_number(balance)} {currency}"
        prestige_str = _("Prestige ") + str(prestige)

        # Get base font
        base_font = self.font
        if font_name:
            fontfile = os.path.join(self.fonts, font_name)
            if os.path.exists(fontfile):
                base_font = fontfile
        # base_font = self.get_random_font()
        # Setup font sizes
        name_size = 60
        name_font = ImageFont.truetype(base_font, name_size)
        while (name_font.getlength(user_name) + bar_start + 20) > 900:
            name_size -= 1
            name_font = ImageFont.truetype(base_font, name_size)
            name_y += 0.1
        name_y = round(name_y)
        nameht = name_font.getbbox(user_name)
        name_y = name_y - int(nameht[1] * 0.6)

        emoji_scale = 1.2
        stats_size = 35
        stat_offset = stats_size + 5
        stats_font = ImageFont.truetype(base_font, stats_size)
        while (stats_font.getlength(leveltxt) + bar_start + 10) > bar_start + 210:
            stats_size -= 1
            emoji_scale += 0.1
            stats_font = ImageFont.truetype(base_font, stats_size)
        # Also check message box
        while (stats_font.getlength(message_count) + bar_start + 220) > final.width - 10:
            stats_size -= 1
            emoji_scale += 0.1
            stats_font = ImageFont.truetype(base_font, stats_size)
        # And rank box
        while (stats_font.getlength(rank) + bar_start + 10) > bar_start + 210:
            stats_size -= 1
            emoji_scale += 0.1
            stats_font = ImageFont.truetype(base_font, stats_size)
        # And exp text
        while (stats_font.getlength(exp) + bar_start + 10) > final.width - 10:
            stats_size -= 1
            stats_font = ImageFont.truetype(base_font, stats_size)

        star_fontsize = 60
        star_font = ImageFont.truetype(base_font, star_fontsize)
        while (star_font.getlength(stars) + star_text_x) > final.width - 10:
            star_fontsize -= 1
            star_font = ImageFont.truetype(base_font, star_fontsize)

        # Get status and star image and paste to profile
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        status = self.status[user_status] if user_status in self.status else self.status["offline"]
        status_img = Image.open(status)
        status = status_img.convert("RGBA").resize((60, 60), Image.Resampling.NEAREST)
        star = Image.open(self.star).resize((50, 50), Image.Resampling.NEAREST)
        # Role icon
        role_bytes = self.get_image_content_from_url(role_icon) if role_icon else None
        if role_bytes:
            role_bytes = BytesIO(role_bytes)
            role_icon_img = Image.open(role_bytes).resize((50, 50), Image.Resampling.NEAREST)
            blank.paste(role_icon_img, (10, 10))
        # Prestige icon
        prestige_bytes = self.get_image_content_from_url(emoji) if prestige else None
        if prestige_bytes:
            prestige_bytes = BytesIO(prestige_bytes)
            prestige_img = Image.open(prestige_bytes).resize((stats_size, stats_size), Image.Resampling.NEAREST)
            # Adjust prestige icon placement
            p_bbox = stats_font.getbbox(prestige_str)
            # Middle of stat text
            pmiddle = stats_y - stats_size - 10 + int(p_bbox[3] / 2)
            # Paste prestige image appropriately
            pr_x = p_bbox[2] + bar_start + 20
            pr_y = pmiddle - int(stats_size / 2)
            blank.paste(prestige_img, (pr_x, pr_y))

        # Paste star icon
        blank.paste(star, (star_icon_x, star_icon_y))
        # New final
        final = Image.alpha_composite(final, blank)

        # Add stats text
        # Render name and credits text through pilmoji in case there are emojis
        with Pilmoji(final) as pilmoji:
            # Name text
            name_bbox = name_font.getbbox(user_name)
            name_emoji_y = name_bbox[3] - name_size
            pilmoji.text(
                (bar_start + 10, name_y),
                user_name,
                namecolor,
                font=name_font,
                # anchor="lt",
                stroke_width=stroke_width,
                stroke_fill=namefill,
                emoji_scale_factor=emoji_scale,
                emoji_position_offset=(0, name_emoji_y),
            )
            # Balance
            if balance:
                bal_bbox = stats_font.getbbox(bal)
                bal_emoji_y = bal_bbox[3] - int(stats_size * emoji_scale)
                pilmoji.text(
                    (bar_start + 10, bar_top - 110),
                    bal,
                    statcolor,
                    font=stats_font,
                    stroke_width=stroke_width,
                    stroke_fill=statstxtfill,
                    emoji_scale_factor=emoji_scale,
                    emoji_position_offset=(0, bal_emoji_y),
                )

        draw = ImageDraw.Draw(final)
        # Prestige
        if prestige:
            draw.text(
                (bar_start + 10, stats_y - stats_size - 10),
                prestige_str,
                statcolor,
                font=stats_font,
                stroke_width=stroke_width,
                stroke_fill=statstxtfill,
            )
        # Stats text
        # Rank
        draw.text(
            (bar_start + 10, stats_y),
            rank,
            statcolor,
            font=stats_font,
            stroke_width=stroke_width,
            stroke_fill=statstxtfill,
        )
        # Level
        draw.text(
            (bar_start + 10, stats_y + stat_offset),
            leveltxt,
            statcolor,
            font=stats_font,
            stroke_width=stroke_width,
            stroke_fill=statstxtfill,
        )
        # Messages
        draw.text(
            (bar_start + 220, stats_y),
            message_count,
            statcolor,
            font=stats_font,
            stroke_width=stroke_width,
            stroke_fill=statstxtfill,
        )
        # Voice
        draw.text(
            (bar_start + 220, stats_y + stat_offset),
            voice,
            statcolor,
            font=stats_font,
            stroke_width=stroke_width,
            stroke_fill=statstxtfill,
        )

        # Exp
        draw.text(
            (bar_start + 10, bar_top - 60),
            exp,
            statcolor,
            font=stats_font,
            stroke_width=stroke_width,
            stroke_fill=statstxtfill,
        )

        # Stars
        draw.text(
            (star_text_x, star_text_y),
            stars,
            namecolor,
            font=star_font,
            anchor="lt",
            stroke_width=stroke_width,
            stroke_fill=namefill,
        )

        # pfp border - draw at 4x and resample down to 1x for nice smooth circles then paste to the image
        circle_img = Image.new("RGBA", (1600, 1600))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 1596, 1596], fill=(255, 255, 255, 0), outline=base, width=20)
        circle_img = circle_img.resize((330, 330), Image.Resampling.NEAREST)
        final.paste(circle_img, (circle_x - 15, circle_y - 15), circle_img)

        # Handle profile pic image to paste to card
        # If animated and render gifs enabled, render as a gif
        is_animated = getattr(profile, "is_animated", False)
        if is_animated and render_gifs:
            duration = self.get_avg_duration(profile)
            frames = []
            for i in range(profile.n_frames):
                profile.seek(i)
                prof_img = profile.convert("RGBA").resize((300, 300), Image.Resampling.NEAREST)
                # Mask to crop profile pic image to a circle
                # draw at 4x size and resample down to 1x for a nice smooth circle
                mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse(
                    [
                        circle_x * 4,
                        circle_y * 4,
                        (300 + circle_x) * 4,
                        (300 + circle_y) * 4,
                    ],
                    fill=(255, 255, 255, 255),
                )
                mask = mask.resize(card.size, Image.Resampling.NEAREST)
                # make a new Image to set up card-sized image for pfp layer and the circle mask for it
                profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))
                # paste on square profile pic in appropriate spot
                profile_pic_holder.paste(prof_img, (circle_x, circle_y))
                # make a new Image at card size to crop pfp with transparency to the circle mask
                pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
                pfp_composite_holder = Image.composite(profile_pic_holder, pfp_composite_holder, mask)
                # Profile image is on the background tile now
                pre = Image.alpha_composite(final, pfp_composite_holder)
                # Paste status over profile ring
                blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
                blank.paste(status, (circle_x + 230, circle_y + 240))
                pre = Image.alpha_composite(pre, blank)
                frames.append(pre)

            tmp = BytesIO()
            frames[0].save(
                tmp,
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                format="GIF",
                loop=0,
                quality=25,
            )
            tmp.seek(0)
            final = Image.open(tmp)

        else:
            profile = profile.convert("RGBA").resize((300, 300), Image.Resampling.NEAREST)
            # Mask to crop profile pic image to a circle
            # draw at 4x size and resample down to 1x for a nice smooth circle
            mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse(
                [
                    circle_x * 4,
                    circle_y * 4,
                    (300 + circle_x) * 4,
                    (300 + circle_y) * 4,
                ],
                fill=(255, 255, 255, 255),
            )
            mask = mask.resize(card.size, Image.Resampling.NEAREST)
            # make a new Image to set up card-sized image for pfp layer and the circle mask for it
            profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))
            # paste on square profile pic in appropriate spot
            profile_pic_holder.paste(profile, (circle_x, circle_y))
            # make a new Image at card size to crop pfp with transparency to the circle mask
            pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
            pfp_composite_holder = Image.composite(profile_pic_holder, pfp_composite_holder, mask)
            # Profile image is on the background tile now
            final = Image.alpha_composite(final, pfp_composite_holder)
            # Paste status over profile ring
            blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
            blank.paste(status, (circle_x + 230, circle_y + 240))
            final = Image.alpha_composite(final, blank)

        return final

    @perf(max_entries=1000)
    def generate_slim_profile(
        self,
        bg_image: str = None,
        profile_image: str = "https://i.imgur.com/sUYWCve.png",
        level: int = 1,
        prev_xp: int = 0,
        user_xp: int = 0,
        next_xp: int = 100,
        user_position: str = "1",
        user_name: str = "Unknown#0117",
        user_status: str = "online",
        colors: dict = None,
        messages: str = "0",
        voice: str = "None",
        prestige: int = 0,
        emoji: str = None,
        stars: str = "0",
        balance: int = 0,
        currency: str = "credits",
        role_icon: str = None,
        font_name: str = None,
        render_gifs: bool = False,
        blur: bool = False,
    ):
        # Colors
        base = self.rand_rgb()
        namecolor = self.rand_rgb()
        statcolor = self.rand_rgb()
        lvlbarcolor = self.rand_rgb()
        # Color distancing is more strict if user hasn't defined color
        namedistance = 240
        statdistance = 240
        lvldistance = 240
        if colors:
            # Relax distance for colors that are defined
            base = colors["base"]
            if colors["name"]:
                namecolor = colors["name"]
                namedistance = 10
            if colors["stat"]:
                statcolor = colors["stat"]
                statdistance = 10
            if colors["levelbar"]:
                lvlbarcolor = colors["levelbar"]
                lvldistance = 10
            else:
                lvlbarcolor = base

        outlinecolor = (0, 0, 0)
        text_bg = (0, 0, 0)

        # Set canvas
        aspect_ratio = (27, 7)

        # Get background
        available = list(self.backgrounds.iterdir()) + list(self.saved_bgs.iterdir())
        card = None
        if bg_image and str(bg_image) != "random":
            if not bg_image.lower().startswith("http"):
                for file in available:
                    if bg_image.lower() in file.name.lower():
                        try:
                            card = Image.open(file)
                            break
                        except OSError:
                            log.info(f"Failed to load {bg_image}")

            if not card and bg_image.lower().startswith("http"):
                try:
                    bg_bytes = self.get_image_content_from_url(bg_image)
                    card = Image.open(BytesIO(bg_bytes))
                except UnidentifiedImageError:
                    pass

        if not card:
            card = self.get_random_background()

        card = self.force_aspect_ratio(card, aspect_ratio)
        card = card.convert("RGBA").resize((900, 240), Image.Resampling.NEAREST)
        try:
            bgcolor = self.get_img_color(card)
        except Exception as e:
            log.error(f"Failed to get slim profile BG color: {e}")
            bgcolor = base

        # Compare text colors to BG
        iters = 0
        while self.distance(namecolor, bgcolor) < namedistance:
            namecolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break
        while self.distance(statcolor, bgcolor) < statdistance:
            statcolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break
        while self.distance(lvlbarcolor, bgcolor) < lvldistance:
            lvlbarcolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break
        while self.distance(outlinecolor, bgcolor) < 50:
            outlinecolor = self.rand_rgb()
            iters += 1
            if iters > 20:
                iters = 0
                break

        # Place semi-transparent box over right side
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        transparent_box = Image.new("RGBA", card.size, (0, 0, 0, 100))
        blank.paste(transparent_box, (240, 0))

        # Make the semi-transparent box area blurry
        if blur:
            blurred = card.filter(ImageFilter.GaussianBlur(3))
            blurred = blurred.crop((240, 0, card.size[0], card.size[1]))
            card.paste(blurred, (240, 0), blurred)
        card = Image.alpha_composite(card, blank)

        # Draw
        draw = ImageDraw.Draw(card)

        user_xp_progress = user_xp - prev_xp
        next_xp_diff = next_xp - prev_xp

        # Editing stuff here
        # ======== Fonts to use =============
        def get_str(xp):
            return "{:,}".format(xp)

        rank = _("Rank: #") + str(user_position)
        level = _("Level: ") + str(level)
        exp = f"Exp: {get_str(user_xp_progress)}/{get_str(next_xp_diff)} ({get_str(user_xp)} total)"
        messages = _("Messages: ") + str(messages)
        voice = _("Voice Time: ") + str(voice)
        name = user_name
        if prestige:
            name += _(" - Prestige ") + str(prestige)
        stars = str(stars)

        base_font = self.font
        if font_name:
            fontfile = os.path.join(self.fonts, font_name)
            if os.path.exists(fontfile):
                base_font = fontfile
        namesize = 45
        statsize = 30
        starsize = 45
        namefont = ImageFont.truetype(base_font, namesize)
        statfont = ImageFont.truetype(base_font, statsize)
        starfont = ImageFont.truetype(base_font, starsize)

        while (namefont.getlength(name) + 260) > 770:
            namesize -= 1
            namefont = ImageFont.truetype(base_font, namesize)
        while (statfont.getlength(messages) + 465) > 890:
            statsize -= 1
            statfont = ImageFont.truetype(base_font, statsize)
        while (statfont.getlength(level) + 260) > 455:
            statsize -= 1
            statfont = ImageFont.truetype(base_font, statsize)
        while (starfont.getlength(stars) + 825) > 890:
            starsize -= 1
            starfont = ImageFont.truetype(base_font, starsize)

        # Stat text
        draw.text(
            (260, 20),
            name,
            namecolor,
            font=namefont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (260, 95),
            rank,
            statcolor,
            font=statfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (260, 125),
            level,
            statcolor,
            font=statfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (260, 160),
            exp,
            statcolor,
            font=statfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (465, 95),
            messages,
            statcolor,
            font=statfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (465, 125),
            voice,
            statcolor,
            font=statfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )
        draw.text(
            (825, 28),
            stars,
            statcolor,
            font=starfont,
            stroke_width=1,
            stroke_fill=text_bg,
        )

        # Adding another blank layer for the progress bar
        progress_bar = Image.new("RGBA", card.size, (255, 255, 255, 0))
        progress_bar_draw = ImageDraw.Draw(progress_bar)
        bar_start = 260
        bar_end = 740
        # rectangle 0:x, 1:top y, 2:length, 3:bottom y
        progress_bar_draw.rectangle(
            (bar_start, 200, bar_end, 215),
            fill=(255, 255, 255, 0),
            outline=lvlbarcolor,
        )

        xp_ratio = user_xp_progress / next_xp_diff
        end_of_inner_bar = ((bar_end - bar_start) * xp_ratio) + bar_start
        barx, barlength = bar_start + 2, end_of_inner_bar - 2
        if barlength > barx:
            progress_bar_draw.rectangle((barx, 203, barlength, 212), fill=statcolor)

        # pfp border - draw at 4x and resample down to 1x for nice smooth circles
        circle_img = Image.new("RGBA", (800, 800))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 796, 796], fill=(255, 255, 255, 0), outline=base, width=12)
        circle_img = circle_img.resize((200, 200), Image.Resampling.NEAREST)
        card.paste(circle_img, (19, 19), circle_img)

        # get profile pic
        if profile_image:
            pfp_image = self.get_image_content_from_url(str(profile_image))
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)

        profile = profile.convert("RGBA").resize((180, 180), Image.Resampling.NEAREST)

        # Mask to crop profile pic image to a circle
        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((116, 116, 836, 836), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.Resampling.NEAREST)

        # make a new Image to set up card-sized image for pfp layer and the circle mask for it
        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))

        # paste on square profile pic in appropriate spot
        profile_pic_holder.paste(profile, (29, 29, 209, 209))

        # make a new Image at card size to crop pfp with transparency to the circle mask
        pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        pfp_composite_holder = Image.composite(profile_pic_holder, pfp_composite_holder, mask)

        # layer the pfp_composite_holder onto the card
        pre = Image.alpha_composite(card, pfp_composite_holder)
        # layer on the progress bar
        pre = Image.alpha_composite(pre, progress_bar)

        status = self.status[user_status] if user_status in self.status else self.status["offline"]
        status_img = Image.open(status)
        status = status_img.convert("RGBA").resize((40, 40), Image.Resampling.NEAREST)
        rep_icon = Image.open(self.star)
        rep_icon = rep_icon.convert("RGBA").resize((40, 40), Image.Resampling.NEAREST)

        # Status badge
        # Another blank
        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (169, 169))
        # Add rep star
        blank.paste(rep_icon, (780, 29))

        final = Image.alpha_composite(pre, blank)
        return final

    @perf(max_entries=1000)
    def generate_levelup(
        self,
        bg_image: str = None,
        profile_image: str = None,
        level: int = 1,
        color: tuple = (0, 0, 0),
        font_name: str = None,
    ):
        available = list(self.backgrounds.iterdir()) + list(self.saved_bgs.iterdir())
        card = None
        if bg_image and str(bg_image) != "random":
            if not bg_image.lower().startswith("http"):
                for file in available:
                    if bg_image.lower() in file.name.lower():
                        try:
                            card = Image.open(file)
                            break
                        except OSError:
                            log.info(f"Failed to load {bg_image}")

            if not card and bg_image.lower().startswith("http"):
                try:
                    bg_bytes = self.get_image_content_from_url(bg_image)
                    card = Image.open(BytesIO(bg_bytes))
                except UnidentifiedImageError:
                    pass

        if not card:
            card = self.get_random_background()

        # Get coords and fonts setup
        card_size = (180, 60)
        aspect_ratio = (18, 6)
        card: Image = self.force_aspect_ratio(card, aspect_ratio).convert("RGBA")
        fillcolor = (0, 0, 0)
        txtcolor = color

        pfpsize = (card.height, card.height)
        fontsize = int(card.height / 2.5)
        string = _("Level ") + str(level)
        base_font = self.font
        if font_name:
            fontfile = os.path.join(self.fonts, font_name)
            if os.path.exists(fontfile):
                base_font = fontfile
        # base_font = self.get_random_font()
        font = ImageFont.truetype(base_font, fontsize)
        while font.getlength(string) + int(card.height * 1.2) > card.width - (int(card.height * 1.2) - card.height):
            fontsize -= 1
            font = ImageFont.truetype(base_font, fontsize)

        # Draw rounded rectangle at 4x size and scale down to crop card to
        mask = Image.new("RGBA", ((card.size[0]), (card.size[1])), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (10, 0, card.width, card.height),
            fill=fillcolor,
            width=5,
            radius=card.height,
        )

        # Make new Image to create composite
        composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        final = Image.composite(card, composite_holder, mask)

        # Prep profile to paste
        pfp_image = self.get_image_content_from_url(str(profile_image))
        if pfp_image:
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)
        profile = profile.convert("RGBA").resize(pfpsize, Image.Resampling.LANCZOS)

        # Create mask for profile image crop
        mask = Image.new("RGBA", ((card.size[0]), (card.size[1])), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, pfpsize[0], pfpsize[1]), fill=(255, 255, 255, 255))
        # mask = mask.resize(card.size, Image.Resampling.NEAREST)

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
            string,
            txtcolor,
            font=font,
            anchor="lm",
            stroke_width=3,
            stroke_fill=fillcolor,
        )
        # Finally resize the image
        final = final.resize(card_size, Image.Resampling.LANCZOS)
        return final

    @perf(max_entries=1000)
    def get_all_fonts(self) -> Image.Image:
        fonts = [i for i in os.listdir(self.fonts)]
        count = len(fonts)
        fontsize = 50
        res = (650, fontsize * count + (count * 15))
        img = Image.new("RGBA", res, 0)
        color = (255, 255, 255)
        draw = ImageDraw.Draw(img)
        for index, i in enumerate(fonts):
            fontname = i.replace(".ttf", "")
            font = ImageFont.truetype(os.path.join(self.fonts, i), fontsize)
            draw.text((5, index * (fontsize + 15)), fontname, color, font=font, stroke_width=1, stroke_fill=(0, 0, 0))
        return img

    @perf(max_entries=1000)
    def get_all_backgrounds(self):
        available: List[Path] = list(self.saved_bgs.iterdir()) + list(self.backgrounds.iterdir())
        imgs = []
        for file in available:
            if file.is_dir() or file.suffix == ".py":
                continue
            try:
                img = self.force_aspect_ratio(Image.open(file))
                img = img.convert("RGBA").resize((1050, 450), Image.Resampling.NEAREST)
                draw = ImageDraw.Draw(img)
                ext_replace = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
                txt = file.name
                for ext in ext_replace:
                    txt = txt.replace(ext, "")
                # Add a black outline to the text
                draw.text(
                    (10, 10),
                    txt,
                    font=ImageFont.truetype(self.font, 100),
                    fill=(255, 255, 255),
                    stroke_width=5,
                    stroke_fill="#000000",
                )
                if not img:
                    log.error(f"Failed to load image for default background '{file}`")
                    continue
                imgs.append((img, file.name))
            except Exception as e:
                log.warning(f"Failed to prep background image: {file}", exc_info=e)

        # Sort by name
        imgs = sorted(imgs, key=lambda key: key[1])

        # Make grid 4 wide by however many tall
        rowcount = ceil(len(imgs) / 4)
        # Make a bunch of rows of 4
        rows = []
        index = 0
        for __ in range(rowcount):
            final = None
            for __ in range(4):
                if index >= len(imgs):
                    continue

                img_obj = imgs[index][0]
                index += 1

                if final is None:
                    final = img_obj
                else:
                    final = self.concat_img_h(final, img_obj)

            if final:
                rows.append(final)

        # Now concat the rows vertically
        final = None
        for row_img_obj in rows:
            if final is None:
                final = row_img_obj
            else:
                final = self.concat_img_v(final, row_img_obj)

        return final

    @staticmethod
    @perf(max_entries=1000)
    def concat_img_v(im1: Image, im2: Image) -> Image:
        new = Image.new("RGBA", (im1.width, im1.height + im2.height))
        new.paste(im1, (0, 0))
        new.paste(im2, (0, im1.height))
        return new

    @staticmethod
    @perf(max_entries=1000)
    def concat_img_h(im1: Image, im2: Image) -> Image:
        new = Image.new("RGBA", (im1.width + im2.width, im1.height))
        new.paste(im1, (0, 0))
        new.paste(im2, (im1.width, 0))
        return new

    @staticmethod
    @perf(max_entries=1000)
    def get_image_content_from_url(url: str) -> Union[bytes, None]:
        if url is None:
            return None
        if str(url) == "None":
            return None
        try:
            res = requests.get(url)
            return res.content
        except Exception as e:
            log.error(
                f"Failed to get image from url: {url}\nError: {e}",
                exc_info=True,
            )
            return None

    @staticmethod
    @perf(max_entries=1000)
    def get_img_color(img: Union[Image.Image, str, bytes, BytesIO]) -> tuple:
        try:
            colors = colorgram.extract(img, 1)
            return colors[0].rgb
        except Exception as e:
            log.warning(f"Failed to get image color: {e}")
            return 0, 0, 0

    @staticmethod
    @perf(max_entries=1000)
    def get_img_colors(img: Union[Image.Image, str, bytes, BytesIO], amount: int) -> list:
        try:
            colors = colorgram.extract(img, amount)
            extracted = [color.rgb for color in colors]
            return extracted
        except Exception as e:
            log.warning(f"Failed to extract image colors: {e}")
            extracted = [(0, 0, 0) for _ in range(amount)]
            return extracted

    @staticmethod
    def distance(color: tuple, background_color: tuple) -> float:
        # Values
        x1, y1, z1 = color
        x2, y2, z2 = background_color

        # Distances
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2

        # Final distance
        return sqrt(dx**2 + dy**2 + dz**2)

    @staticmethod
    def inv_rgb(rgb: tuple) -> tuple:
        new_rgb = (255 - rgb[0], 255 - rgb[1], 255 - rgb[2])
        return new_rgb

    @staticmethod
    def rand_rgb() -> tuple:
        r = random.randint(0, 256)
        g = random.randint(0, 256)
        b = random.randint(0, 256)
        return r, g, b

    @staticmethod
    @perf(max_entries=1000)
    def get_sample_section(image: Image, box: tuple) -> Image:
        # x1, y1, x2, y2
        return image.crop((box[0], box[1], box[2], box[3]))

    @staticmethod
    @perf(max_entries=1000)
    def force_aspect_ratio(image: Image.Image, aspect_ratio: tuple = ASPECT_RATIO) -> Image:
        x, y = aspect_ratio
        w, h = image.size

        counter = 1
        while True:
            nw, nh = counter * x, counter * y
            if (counter + 1) * x > w or (counter + 1) * y > h:
                break
            counter += 1

        x_split = int((w - nw) / 2)
        x1 = x_split
        x2 = w - x_split

        y_split = int((h - nh) / 2)
        y1 = y_split
        y2 = h - y_split

        box = (x1, y1, x2, y2)
        cropped = image.crop(box)
        return cropped

    @perf(max_entries=1000)
    def get_random_background(self) -> Image:
        available = list(self.backgrounds.iterdir()) + list(self.saved_bgs.iterdir())
        random.shuffle(available)
        for path in available:
            try:
                return Image.open(path)
            except UnidentifiedImageError:
                pass
        return Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))

    def get_random_font(self) -> str:
        available = list(self.fonts.iterdir()) + list(self.saved_fonts.iterdir())
        return random.choice(available)

    @staticmethod
    def has_emoji(text: str) -> Union[str, bool]:
        if text.count(":") < 2:
            return False
        if "<" in text:
            return "custom"
        else:
            return "unicode"

    @staticmethod
    @perf(max_entries=1000)
    def get_avg_duration(image: Image) -> Union[int, None]:
        """Get average duration sequence of gif frames"""
        if not getattr(image, "is_animated"):
            return None
        times = []
        for i in range(1, image.n_frames):
            image.seek(i)
            times.append(image.info["duration"])
        if not times:
            return None
        return int(sum(times) / len(times))

    @staticmethod
    @perf(max_entries=1000)
    def get_durations(image: Image) -> Union[tuple, None]:
        if not image.is_animated:
            return None
        times = []
        for i in range(image.n_frames):
            image.seek(i)
            times.append(image.info["duration"])
        if not times:
            return None
        return tuple(times)
