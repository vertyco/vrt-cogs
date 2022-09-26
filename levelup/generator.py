import logging
import os
import random
from io import BytesIO
from math import sqrt
from typing import Union

import colorgram
import requests
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from redbot.core.data_manager import bundled_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

log = logging.getLogger("red.vrt.levelup.generator")
_ = Translator("LevelUp", __file__)
ASPECT_RATIO = (21, 9)


class Generator:
    def __init__(self):
        self.star = os.path.join(bundled_data_path(self), 'star.png')
        self.default_lvlup = os.path.join(bundled_data_path(self), 'lvlup.png')
        self.default_bg = os.path.join(bundled_data_path(self), 'card.png')
        self.default_pfp = os.path.join(bundled_data_path(self), 'defaultpfp.png')

        self.status = {
            "online": os.path.join(bundled_data_path(self), 'online.png'),
            "offline": os.path.join(bundled_data_path(self), 'offline.png'),
            "idle": os.path.join(bundled_data_path(self), 'idle.png'),
            "dnd": os.path.join(bundled_data_path(self), 'dnd.png'),
            "streaming": os.path.join(bundled_data_path(self), 'streaming.png')
        }

        self.font = os.path.join(bundled_data_path(self), 'font.ttf')

    def generate_profile(
            self,
            bg_image: str = None,
            profile_image: str = "https://i.imgur.com/sUYWCve.png",
            level: int = 1,
            current_xp: int = 0,
            user_xp: int = 0,
            next_xp: int = 100,
            user_position: str = "1",
            user_name: str = 'Unknown#0117',
            user_status: str = 'online',
            colors: dict = None,
            messages: str = "0",
            voice: str = "None",
            prestige: int = 0,
            emoji: str = None,
            stars: str = "0",
            balance: int = 0,
            currency: str = "credits",
            role_icon: str = None
    ):
        # Colors
        if colors:
            base = colors["base"]
            namecolor = colors["name"] if colors["name"] else self.rand_rgb()
            statcolor = colors["stat"] if colors["stat"] else self.rand_rgb()
            lvlbarcolor = colors["levelbar"] if colors["levelbar"] else base
        else:
            base = self.rand_rgb()
            namecolor = self.rand_rgb()
            statcolor = self.rand_rgb()
            lvlbarcolor = self.rand_rgb()
        default_fill = (0, 0, 0)

        # Set canvas
        if bg_image and bg_image != "random":
            bg_bytes = self.get_image_content_from_url(bg_image)
            try:
                card = Image.open(BytesIO(bg_bytes))
            except UnidentifiedImageError:
                card = self.get_random_background()
        else:
            card = self.get_random_background()
        card = self.force_aspect_ratio(card).convert("RGBA").resize((1050, 450), Image.Resampling.LANCZOS)

        # Coord setup
        name_y = 40
        stats_y = 160
        bar_start = 450
        bar_end = 1030
        bar_top = 380
        bar_bottom = 420
        circle_x = 60
        circle_y = 75

        stroke_width = 2

        # x1, y1, x2, y2
        # Sample name box colors and make sure they're not too similar with the background
        namebox = (bar_start, name_y, bar_start + 50, name_y + 100)
        namesection = self.get_sample_section(card, namebox)
        namebg = self.get_img_color(namesection)
        namefill = default_fill
        while self.distance(namecolor, namebg) < 240:
            namecolor = self.rand_rgb()
        if self.distance(namefill, namecolor) < 230:
            namefill = self.inv_rgb(namefill)

        # Sample stat box colors and make sure they're not too similar with the background
        statbox = (bar_start, stats_y, bar_start + 400, bar_top)
        statsection = self.get_sample_section(card, statbox)
        statbg = self.get_img_color(statsection)
        statstxtfil = default_fill
        while self.distance(statcolor, statbg) < 240:
            statcolor = self.rand_rgb()
        if self.distance(statstxtfil, statcolor) < 230:
            statstxtfil = self.inv_rgb(statstxtfil)

        # get profile pic
        pfp_image = self.get_image_content_from_url(str(profile_image))
        if pfp_image:
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)
        profile = profile.convert('RGBA').resize((300, 300), Image.Resampling.LANCZOS)

        # pfp border - draw at 4x and resample down to 1x for nice smooth circles
        circle_img = Image.new("RGBA", (1600, 1600))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 1596, 1596], fill=(255, 255, 255, 0), outline=base, width=20)
        circle_img = circle_img.resize((330, 330), Image.Resampling.LANCZOS)
        card.paste(circle_img, (circle_x - 15, circle_y - 15), circle_img)

        # Mask to crop profile pic image to a circle
        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse(
            [circle_x * 4, circle_y * 4, (300 + circle_x) * 4, (300 + circle_y) * 4], fill=(255, 255, 255, 255)
        )
        mask = mask.resize(card.size, Image.Resampling.LANCZOS)

        # make a new Image to set up card-sized image for pfp layer and the circle mask for it
        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))
        # paste on square profile pic in appropriate spot
        profile_pic_holder.paste(profile, (circle_x, circle_y))
        # make a new Image at card size to crop pfp with transparency to the circle mask
        pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        pfp_composite_holder = Image.composite(profile_pic_holder, pfp_composite_holder, mask)

        # Profile image is on the background tile now
        final = Image.alpha_composite(card, pfp_composite_holder)

        # Place semi-transparent box over right side
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        transparent_box = Image.new("RGBA", card.size, (0, 0, 0, 100))
        blank.paste(transparent_box, (bar_start - 20, 0))
        final = Image.alpha_composite(final, blank)

        # Make the level progress bar
        progress_bar = Image.new("RGBA", (card.size[0] * 4, card.size[1] * 4), (255, 255, 255, 0))
        progress_bar_draw = ImageDraw.Draw(progress_bar)
        # Calculate data for level bar
        xpneed = next_xp - current_xp
        xphave = user_xp - current_xp
        xp_ratio = xphave / xpneed
        end_of_inner_bar = ((bar_end - bar_start) * xp_ratio) + 400
        # Rectangle 0:left x, 1:top y, 2:right x, 3:bottom y
        # Draw level bar outline
        progress_bar_draw.rounded_rectangle(
            (bar_start * 4, bar_top * 4, bar_end * 4, bar_bottom * 4),
            fill=(255, 255, 255, 0),
            outline=lvlbarcolor,
            width=8,
            radius=90
        )
        # Draw inner level bar 1 pixel smaller on each side
        if end_of_inner_bar > bar_start + 10:
            progress_bar_draw.rounded_rectangle(
                (bar_start * 4 + 1, bar_top * 4 + 2, end_of_inner_bar * 4 - 1, bar_bottom * 4 - 2),
                fill=lvlbarcolor,
                radius=89
            )
        progress_bar = progress_bar.resize(card.size, Image.Resampling.LANCZOS)
        # Image with level bar and pfp on background
        final = Image.alpha_composite(final, progress_bar)

        # Get status and star image and paste to profile
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))

        status = self.status[user_status] if user_status in self.status else self.status["offline"]
        status_img = Image.open(status)
        status = status_img.convert("RGBA").resize((60, 60), Image.Resampling.LANCZOS)
        star = Image.open(self.star).resize((50, 50), Image.Resampling.LANCZOS)
        # Role icon
        role_bytes = self.get_image_content_from_url(role_icon) if role_icon else None
        if role_bytes:
            role_bytes = BytesIO(role_bytes)
            role_icon_img = Image.open(role_bytes).resize((40, 40), Image.Resampling.LANCZOS)
            blank.paste(
                role_icon_img, (bar_start - 50, name_y + 10)
            )
        # Prestige icon
        prestige_bytes = self.get_image_content_from_url(emoji) if prestige else None
        if prestige_bytes:
            prestige_bytes = BytesIO(prestige_bytes)
            prestige_img = Image.open(prestige_bytes).resize((40, 40), Image.Resampling.LANCZOS)
            blank.paste(prestige_img, (bar_start - 50, bar_top))

        # Paste star and status to profile
        blank.paste(status, (circle_x + 230, circle_y + 240))
        blank.paste(star, (900, 50))

        # New final
        final = Image.alpha_composite(final, blank)

        # Add stats text
        draw = ImageDraw.Draw(final)
        name_size = 50
        name_font = ImageFont.truetype(self.font, name_size)

        stats_size = 35
        stat_offset = stats_size + 5
        stats_font = ImageFont.truetype(self.font, stats_size)

        # Stat strings
        rank = _(f"Rank: #") + str(user_position)
        leveltxt = _(f"Level: ") + str(level)
        exp = _("Exp: ") + f"{humanize_number(user_xp)}/{humanize_number(next_xp)}"
        message_count = _(f"Messages: ") + messages
        voice = _(f"Voice: ") + voice
        name = f"{user_name}"
        stars = str(stars)
        bal = _("Balance: ") + f"{humanize_number(balance)} {currency}"
        prestige_str = _(f"Prestige ") + str(prestige)

        # Name text
        draw.text((bar_start + 10, name_y), name, namecolor,
                  font=name_font, stroke_width=stroke_width, stroke_fill=namefill)
        # Prestige
        if prestige:
            draw.text((bar_start + 10, name_y + 55), prestige_str, statcolor,
                      font=stats_font, stroke_width=stroke_width, stroke_fill=namefill)
        # Stats text
        # Rank
        draw.text((bar_start + 10, stats_y), rank, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)
        # Level
        draw.text((bar_start + 10, stats_y + stat_offset), leveltxt, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)
        # Messages
        draw.text((bar_start + 210 + 10, stats_y), message_count, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)
        # Voice
        draw.text((bar_start + 210 + 10, stats_y + stat_offset), voice, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)
        # Balance
        draw.text((bar_start + 10, bar_top - 110), bal, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)
        # Exp
        draw.text((bar_start + 10, bar_top - 60), exp, statcolor,
                  font=stats_font, stroke_width=stroke_width, stroke_fill=statstxtfil)

        # Stars
        starfont = name_font if len(stars) < 3 else stats_font
        startop = 42 if len(stars) < 3 else 52
        draw.text((960, startop), stars, namecolor,
                  font=starfont, stroke_width=stroke_width, stroke_fill=namefill)

        return final

    def generate_slim_profile(
            self,
            bg_image: str = None,
            profile_image: str = "https://i.imgur.com/sUYWCve.png",
            level: int = 1,
            current_xp: int = 0,
            user_xp: int = 0,
            next_xp: int = 100,
            user_position: str = "1",
            user_name: str = 'Unknown#0117',
            user_status: str = 'online',
            colors: dict = None,
            messages: str = "0",
            voice: str = "None",
            prestige: int = 0,
            emoji: str = None,
            stars: str = "0",
            balance: int = 0,
            currency: str = "credits",
            role_icon: str = None
    ):
        # Colors
        if colors:
            base = colors["base"]
            namecolor = colors["name"] if colors["name"] else self.rand_rgb()
            statcolor = colors["stat"] if colors["stat"] else self.rand_rgb()
            lvlbarcolor = colors["levelbar"] if colors["levelbar"] else base
        else:
            base = self.rand_rgb()
            namecolor = self.rand_rgb()
            statcolor = self.rand_rgb()
            lvlbarcolor = self.rand_rgb()
        outlinecolor = (0, 0, 0)
        text_bg = (0, 0, 0)

        # Set canvas
        if bg_image and bg_image != "random":
            bg_bytes = self.get_image_content_from_url(bg_image)
            try:
                card = Image.open(BytesIO(bg_bytes)).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)
            except UnidentifiedImageError:
                card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)
            bg_bytes = BytesIO(self.get_image_content_from_url(bg_image))
            try:
                bgcolor = self.get_img_color(bg_bytes)
            except Exception as e:
                log.warning(f"Failed to get profile image color: {e}")
                bgcolor = base
        else:
            card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)
            try:
                bgcolor = self.get_img_color(self.default_bg)
            except Exception as e:
                log.warning(f"Failed to get default image color: {e}")
                bgcolor = base

        # Compare text colors to BG
        while self.distance(namecolor, bgcolor) < 45:
            namecolor = self.rand_rgb()
        while self.distance(statcolor, bgcolor) < 45:
            statcolor = self.rand_rgb()
        while self.distance(lvlbarcolor, bgcolor) < 45:
            lvlbarcolor = self.rand_rgb()
        while self.distance(outlinecolor, bgcolor) < 50:
            outlinecolor = self.rand_rgb()

        # Draw
        draw = ImageDraw.Draw(card)

        # Editing stuff here
        # ======== Fonts to use =============
        font_normal = ImageFont.truetype(self.font, 40)
        font_small = ImageFont.truetype(self.font, 25)

        def get_str(xp):
            return "{:,}".format(xp)

        rank = _(f"Rank: #{user_position}")
        level = _(f"Level: {level}")
        exp = f"Exp: {get_str(user_xp)}/{get_str(next_xp)}"
        messages = _(f"Messages: {messages}")
        voice = _(f"Voice Time: {voice}")
        name = f"{user_name}"
        if prestige:
            name += _(f" - Prestige {prestige}")
        stars = str(stars)

        # stat text
        draw.text((245, 22), name, namecolor, font=font_normal, stroke_width=1, stroke_fill=text_bg)
        draw.text((245, 95), rank, statcolor, font=font_small, stroke_width=1, stroke_fill=text_bg)
        draw.text((245, 125), level, statcolor, font=font_small, stroke_width=1, stroke_fill=text_bg)
        draw.text((245, 160), exp, statcolor, font=font_small, stroke_width=1, stroke_fill=text_bg)
        draw.text((450, 95), messages, statcolor, font=font_small, stroke_width=1, stroke_fill=text_bg)
        draw.text((450, 125), voice, statcolor, font=font_small, stroke_width=1, stroke_fill=text_bg)

        # STAR TEXT
        if len(str(stars)) < 3:
            star_font = ImageFont.truetype(self.font, 35)
            draw.text((825, 25), stars, statcolor, font=star_font, stroke_width=1, stroke_fill=text_bg)
        else:
            star_font = ImageFont.truetype(self.font, 30)
            draw.text((825, 28), stars, statcolor, font=star_font, stroke_width=1, stroke_fill=text_bg)

        # Adding another blank layer for the progress bar
        progress_bar = Image.new("RGBA", card.size, (255, 255, 255, 0))
        progress_bar_draw = ImageDraw.Draw(progress_bar)
        # rectangle 0:x, 1:top y, 2:length, 3:bottom y
        progress_bar_draw.rectangle((246, 200, 741, 215), fill=(255, 255, 255, 0), outline=lvlbarcolor)

        xpneed = next_xp - current_xp
        xphave = user_xp - current_xp

        current_percentage = (xphave / xpneed) * 100
        length_of_bar = (current_percentage * 4.9) + 248

        progress_bar_draw.rectangle((248, 203, length_of_bar, 212), fill=statcolor)

        # pfp border - draw at 4x and resample down to 1x for nice smooth circles
        circle_img = Image.new("RGBA", (800, 800))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 796, 796], fill=(255, 255, 255, 0), outline=base, width=12)
        circle_img = circle_img.resize((200, 200), Image.Resampling.LANCZOS)
        card.paste(circle_img, (19, 19), circle_img)

        # get profile pic
        pfp_image = self.get_image_content_from_url(str(profile_image))
        if pfp_image:
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)

        profile = profile.convert('RGBA').resize((180, 180), Image.Resampling.LANCZOS)

        # Mask to crop profile pic image to a circle
        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((116, 116, 836, 836), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.Resampling.LANCZOS)

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
        status = status_img.convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)
        rep_icon = Image.open(self.star)
        rep_icon = rep_icon.convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)

        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (500, 50))

        # Status badge
        # Another blank
        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (169, 169))
        # Add rep star
        blank.paste(rep_icon, (780, 29))

        final = Image.alpha_composite(pre, blank)
        return final

    def generate_levelup(
            self,
            bg_image: str = None,
            profile_image: str = None,
            level: int = 1,
            color: tuple = (0, 0, 0),
    ):
        if bg_image and bg_image != "random":
            bg_bytes = self.get_image_content_from_url(bg_image)
            try:
                card = Image.open(BytesIO(bg_bytes))
            except UnidentifiedImageError:
                card = self.get_random_background()
        else:
            card = self.get_random_background()
        fillcolor = (0, 0, 0)
        txtcolor = color

        card_size = (180, 60)
        aspect_ratio = (18, 6)
        card = self.force_aspect_ratio(card, aspect_ratio).convert("RGBA").resize(card_size, Image.Resampling.LANCZOS)

        # Draw rounded rectangle at 4x size and scale down to crop card to
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (0, 0, card.size[0] * 4, card.size[1] * 4),
            fill=fillcolor,
            width=2,
            radius=120
        )
        mask = mask.resize(card.size, Image.Resampling.LANCZOS)

        # Make new Image to create composite
        composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        card = Image.composite(card, composite_holder, mask)

        # Prep profile to paste
        pfp_image = self.get_image_content_from_url(str(profile_image))
        if pfp_image:
            profile_bytes = BytesIO(pfp_image)
            profile = Image.open(profile_bytes)
        else:
            profile = Image.open(self.default_pfp)
        profile = profile.convert('RGBA').resize((60, 60), Image.Resampling.LANCZOS)

        # Create mask for profile image crop
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 60 * 4, 60 * 4), fill=fillcolor)
        mask = mask.resize(card.size, Image.Resampling.LANCZOS)

        pfp_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))
        pfp_holder.paste(profile, (0, 0))

        pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        pfp_composite_holder = Image.composite(pfp_holder, pfp_composite_holder, mask)

        final = Image.alpha_composite(card, pfp_composite_holder)

        string = _("Level ") + str(level)
        fontsize = 24
        if len(str(level)) > 2:
            fontsize = 19

        # Draw
        draw = ImageDraw.Draw(final)

        if len(str(level)) > 2:
            size = 19
        else:
            size = 24
        font = ImageFont.truetype(self.font, size)

        # Filling text
        text_x = 65
        text_y = int((card.size[1] / 2) - (fontsize / 1.4))
        draw.text((text_x, text_y), string, txtcolor, font=font, stroke_width=1, stroke_fill=fillcolor)
        return final

    @staticmethod
    def get_image_content_from_url(url: str) -> Union[bytes, None]:
        try:
            res = requests.get(url)
            return res.content
        except Exception as e:
            log.error(f"Failed to get image from url: {url}\nError: {e}", exc_info=True)
            return None

    @staticmethod
    def get_img_color(img: Union[Image.Image, str, bytes, BytesIO]) -> tuple:
        try:
            colors = colorgram.extract(img, 1)
            return colors[0].rgb
        except Exception as e:
            log.warning(f"Failed to get image color: {e}")
            return 0, 0, 0

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
        return sqrt(dx ** 2 + dy ** 2 + dz ** 2)

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
    def get_sample_section(image: Image, box: tuple) -> Image:
        # x1, y1, x2, y2
        return image.crop((box[0], box[1], box[2], box[3]))

    @staticmethod
    def force_aspect_ratio(image: Image, aspect_ratio: tuple = ASPECT_RATIO) -> Image:
        x, y = aspect_ratio
        w, h = image.size
        new_res = []
        for i in range(1, 10000):
            nw = i * x
            nh = i * y
            if not new_res:
                new_res = [nw, nh]
            elif nw <= w and nh <= h:
                new_res = [nw, nh]
            else:
                break
        x_split = int((w - new_res[0]) / 2)
        x1 = x_split
        x2 = w - x_split
        y_split = int((h - new_res[1]) / 2)
        y1 = y_split
        y2 = h - y_split
        box = (x1, y1, x2, y2)
        cropped = image.crop(box)
        return cropped

    def get_random_background(self) -> Image:
        bg_dir = os.path.join(bundled_data_path(self), "backgrounds")
        choice = random.choice(os.listdir(bg_dir))
        bg_file = os.path.join(bg_dir, choice)
        return Image.open(bg_file)
