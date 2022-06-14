import asyncio
import logging
import os
import random
from io import BytesIO
from math import sqrt

import aiohttp
import colorgram
import discord
from PIL import Image, ImageDraw, ImageFont
from redbot.core.data_manager import bundled_data_path

log = logging.getLogger("red.vrt.levelup.generator")


# Yoinked from disrank and modified to suit this cog's needs

class Generator:
    def __init__(self):
        self.star = os.path.join(bundled_data_path(self), 'star.png')
        self.default_lvlup = os.path.join(bundled_data_path(self), 'lvlup.png')
        self.default_bg = os.path.join(bundled_data_path(self), 'card.png')
        self.default_pfp = os.path.join(bundled_data_path(self), 'defaultpfp.png')
        self.online = os.path.join(bundled_data_path(self), 'online.png')
        self.offline = os.path.join(bundled_data_path(self), 'offline.png')
        self.idle = os.path.join(bundled_data_path(self), 'idle.png')
        self.dnd = os.path.join(bundled_data_path(self), 'dnd.png')
        self.streaming = os.path.join(bundled_data_path(self), 'streaming.png')
        self.font1 = os.path.join(bundled_data_path(self), 'font.ttf')

    async def generate_profile(
            self,
            bg_image: str = None,
            profile_image: str = "https://imgur.com/qvFlyiZ",
            level: int = 1,
            current_xp: int = 0,
            user_xp: int = 0,
            next_xp: int = 100,
            user_position: str = "1",
            user_name: str = 'NotSpeified#0117',
            user_status: str = 'online',
            colors: dict = None,
            messages: str = "0",
            voice: str = "None",
            prestige: int = 0,
            stars: str = "0",
    ):
        # Colors
        if colors:
            namecolor = colors["name"]
            statcolor = colors["stat"]
            circlecolor = colors["circle"]
        else:
            namecolor = (0, 0, 0)
            statcolor = (0, 0, 0)
            circlecolor = (0, 0, 0)

        bordercolor = (0, 0, 0)

        # Set canvas
        if not bg_image:
            card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)
            bgcolor = await self.get_img_color(self.default_bg)
        else:
            bg_bytes = BytesIO(await self.get_image_content_from_url(bg_image))
            bgcolor = await self.get_img_color(bg_bytes)
            if bg_bytes:
                card = Image.open(bg_bytes).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)
            else:
                card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.Resampling.LANCZOS)

        # Compare text colors to BG
        if self.distance(namecolor, bgcolor) < 45:
            namecolor = self.inv_rgb(namecolor)
        if self.distance(statcolor, bgcolor) < 45:
            statcolor = self.inv_rgb(statcolor)

        # Compare level bar border to background color
        if self.distance(bordercolor, bgcolor) < 50:
            lvlbarcolor = self.inv_rgb(bordercolor)
        else:
            lvlbarcolor = bordercolor

        # Draw
        draw = ImageDraw.Draw(card)

        # Editing stuff here
        # ======== Fonts to use =============
        font_normal = ImageFont.truetype(self.font1, 40)
        font_small = ImageFont.truetype(self.font1, 25)

        def get_str(xp):
            return "{:,}".format(xp)

        rank = f"Rank: #{user_position}"
        level = f"Level: {level}"
        exp = f"Exp: {get_str(user_xp)}/{get_str(next_xp)}"
        messages = f"Messages: {messages}"
        voice = f"Voice Time: {voice}"
        name = f"{user_name}"
        if prestige:
            name += f" - Prestige {prestige}"
        stars = str(stars)

        # Drawing borders
        draw.text((245, 22), name, bordercolor, font=font_normal, stroke_width=1)
        draw.text((245, 95), rank, bordercolor, font=font_small, stroke_width=1)
        draw.text((245, 125), level, bordercolor, font=font_small, stroke_width=1)
        draw.text((245, 160), exp, bordercolor, font=font_small, stroke_width=1)
        # Borders for 2nd column
        draw.text((450, 95), messages, bordercolor, font=font_small, stroke_width=1)
        draw.text((450, 125), voice, bordercolor, font=font_small, stroke_width=1)
        # Filling text
        draw.text((245, 22), name, namecolor, font=font_normal)
        draw.text((245, 95), rank, statcolor, font=font_small)
        draw.text((245, 125), level, statcolor, font=font_small)
        draw.text((245, 160), exp, statcolor, font=font_small)
        # Filling text for 2nd column
        draw.text((450, 95), messages, statcolor, font=font_small)
        draw.text((450, 125), voice, statcolor, font=font_small)

        # STAR TEXT
        if len(str(stars)) < 3:
            star_font = ImageFont.truetype(self.font1, 35)
            draw.text((825, 25), stars, bordercolor, font=star_font, stroke_width=1)
            draw.text((825, 25), stars, statcolor, font=star_font)
        else:
            star_font = ImageFont.truetype(self.font1, 30)
            draw.text((825, 28), stars, bordercolor, font=star_font, stroke_width=1)
            draw.text((825, 28), stars, statcolor, font=star_font)

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
        pfp_border.ellipse([4, 4, 796, 796], fill=(255, 255, 255, 0), outline=circlecolor, width=12)
        circle_img = circle_img.resize((200, 200), Image.Resampling.LANCZOS)
        card.paste(circle_img, (19, 19), circle_img)

        # get profile pic
        pfp_image = await self.get_image_content_from_url(str(profile_image))
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

        if user_status == 'online':
            status = Image.open(self.online)
        elif user_status == 'offline':
            status = Image.open(self.offline)
        elif user_status == 'idle':
            status = Image.open(self.idle)
        elif user_status == 'streaming':
            status = Image.open(self.streaming)
        elif user_status == 'dnd':
            status = Image.open(self.dnd)
        else:  # Eh just make it offline then
            status = Image.open(self.offline)
        status = status.convert("RGBA").resize((40, 40), Image.Resampling.LANCZOS)
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
        final_bytes = BytesIO()
        final.save(final_bytes, 'WEBP', quality=100)
        final_bytes.seek(0)
        # file = discord.File(fp=final_bytes, filename=f"image_{random.randint(1000, 99999)}.webp")
        # return file
        return final_bytes

    async def generate_levelup(
            self,
            bg_image: str = None,
            profile_image: str = None,
            level: int = 1,
            color: tuple = (0, 0, 0),
    ):
        if not bg_image:
            card = Image.open(self.default_lvlup).convert("RGBA").resize((180, 70), Image.Resampling.LANCZOS)
        else:
            bg_bytes = BytesIO(await self.get_image_content_from_url(bg_image))
            if bg_bytes:
                card = Image.open(bg_bytes).convert("RGBA").resize((180, 70), Image.Resampling.LANCZOS)
            else:
                card = Image.open(self.default_lvlup).convert("RGBA").resize((180, 70), Image.Resampling.LANCZOS)

        # Draw
        draw = ImageDraw.Draw(card)

        if len(str(level)) > 2:
            size = 19
        else:
            size = 24
        font_normal = ImageFont.truetype(self.font1, size)

        MAINCOLOR = color
        BORDER = (0, 0, 0)
        level = f"Level {level}"

        # Drawing borders
        draw.text((73, 16), level, BORDER, font=font_normal, stroke_width=1)
        # Filling text
        draw.text((73, 16), level, MAINCOLOR, font=font_normal)

        # get profile pic
        profile_bytes = BytesIO(await self.get_image_content_from_url(str(profile_image)))
        profile = Image.open(profile_bytes)
        profile = profile.convert('RGBA').resize((60, 60), Image.Resampling.LANCZOS)

        # Mask to crop profile image
        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        # Profile pic border at 4x
        mask_draw.ellipse((36, 36, 240, 240), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.Resampling.LANCZOS)

        # Is used as a blank image for mask
        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))

        # paste on square profile pic in appropriate spot
        profile_pic_holder.paste(profile, (5, 5))

        # make a new Image at card size to crop pfp with transparency to the circle mask
        pfp_composite_holder = Image.new("RGBA", card.size, (0, 0, 0, 0))
        pfp_composite_holder = Image.composite(profile_pic_holder, pfp_composite_holder, mask)

        # layer the pfp_composite_holder onto the card
        pre = Image.alpha_composite(card, pfp_composite_holder)

        final = Image.alpha_composite(pre, pfp_composite_holder)
        final_bytes = BytesIO()
        final.save(final_bytes, 'WEBP')
        final_bytes.seek(0)
        # file = discord.File(fp=final_bytes, filename=f"image_{random.randint(1000, 99999)}.webp")
        # return file
        return final_bytes

    @staticmethod
    async def get_image_content_from_url(url: str):
        headers = {'User-Agent': 'Python/3.8'}
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as r:
                    image = await r.content.read()
                    return image
        except aiohttp.client_exceptions.ClientConnectorError:
            log.error(f"aiohttp failure accessing image at url:\n\t{url}", exc_info=True)
            return None
        except asyncio.TimeoutError:
            log.error(f"asyncio timeout while accessing image at url:\n\t{url}", exc_info=True)
            return None
        except Exception as e:
            log.error(f"General failure accessing image at url:\n\t{url}\nError: {e}", exc_info=True)
            return None

    @staticmethod
    async def get_img_color(img) -> tuple:
        colors = colorgram.extract(img, 1)
        return colors[0].rgb

    @staticmethod
    def distance(color: tuple, background_color: tuple):
        # Values
        x1, y1, z1 = color
        x2, y2, z2 = background_color

        # Distances
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2

        # Final distance
        return int(sqrt(dx ** 2 + dy ** 2 + dz ** 2))

    @staticmethod
    def inv_rgb(rgb: tuple) -> tuple:
        new_rgb = (255 - rgb[0], 255 - rgb[1], 255 - rgb[2])
        return new_rgb
