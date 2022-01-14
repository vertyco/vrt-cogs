from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import asyncio
import logging
import os

from redbot.core.data_manager import bundled_data_path


log = logging.getLogger("red.vrt.levelup.generator")


# Yoinked from disrank and modified to suit this cog's needs

class Generator:
    def __init__(self):
        self.star = os.path.join(bundled_data_path(self), 'star.png')
        self.default_lvlup = os.path.join(bundled_data_path(self), 'lvlup.png')
        self.default_bg = os.path.join(bundled_data_path(self), 'card.png')
        self.online = os.path.join(bundled_data_path(self), 'online.png')
        self.offline = os.path.join(bundled_data_path(self), 'offline.png')
        self.idle = os.path.join(bundled_data_path(self), 'idle.png')
        self.dnd = os.path.join(bundled_data_path(self), 'dnd.png')
        self.streaming = os.path.join(bundled_data_path(self), 'streaming.png')
        self.font1 = os.path.join(bundled_data_path(self), 'font.ttf')
        self.font2 = os.path.join(bundled_data_path(self), 'font2.ttf')

    # Not used atm still suck at pillow
    @staticmethod
    def add_corners(im, rad):
        circle = Image.new('L', (rad * 2, rad * 2), 0)
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
        alpha = Image.new('L', im.size, 255)
        w, h = im.size
        alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
        alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
        alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
        alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
        im.putalpha(alpha)
        return im

    async def generate_profile(
            self,
            bg_image: str = None,
            profile_image: str = None,
            level: int = 1,
            current_xp: int = 0,
            user_xp: int = 20,
            next_xp: int = 100,
            user_position: int = 1,
            user_name: str = 'NotSpeified#0117',
            user_status: str = 'online',
            color: tuple = (0, 0, 0),
            messages: int = 0,
            voice: int = 0,
            prestige: int = 0,
            stars: int = 0,
    ):
        # Set canvas
        if not bg_image:
            card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.ANTIALIAS)
        else:
            bg_bytes = BytesIO(await self.get_image_content_from_url(bg_image))
            if bg_bytes:
                card = Image.open(bg_bytes).convert("RGBA").resize((900, 240), Image.ANTIALIAS)
            else:
                card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.ANTIALIAS)

        # Set canvas
        bg_color = (255, 255, 255, 0)
        result = Image.new("RGBA", (340, 390), bg_color)
        process = Image.new("RGBA", (340, 390), bg_color)

        # Put in background
        result.paste(card, (0,0))

        # Draw
        draw = ImageDraw.Draw(card)

        # PfP image
        profile_bytes = BytesIO(await self.get_image_content_from_url(str(profile_image)))
        profile = Image.open(profile_bytes)
        profile = profile.convert('RGBA').resize((180, 180), Image.ANTIALIAS)

        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))

        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((116, 116, 836, 836), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.ANTIALIAS)

        # Editing stuff here
        # ======== Fonts to use =============
        font_normal = ImageFont.truetype(self.font1, 40)
        font_small = ImageFont.truetype(self.font1, 25)
        # ======== Colors ========================
        MAINCOLOR = color
        BORDER = (0, 0, 0)

        def get_str(xp):
            return "{:,}".format(xp)

        rank = f"Rank: #{user_position}"
        level = f"Level: {level}"
        exp = f"Exp: {get_str(user_xp)}/{get_str(next_xp)}"
        messages = f"Messages: {messages}"
        voice = f"Voice Minutes: {voice}"
        name = f"{user_name}"
        if prestige:
            name += f" - Prestige {prestige}"
        stars = str(stars)

        # Drawing borders
        draw.text((245, 22), name, BORDER, font=font_normal, stroke_width=1)
        draw.text((245, 95), rank, BORDER, font=font_small, stroke_width=1)
        draw.text((245, 125), level, BORDER, font=font_small, stroke_width=1)
        draw.text((245, 160), exp, BORDER, font=font_small, stroke_width=1)
        # Borders for 2nd column
        draw.text((450, 95), messages, BORDER, font=font_small, stroke_width=1)
        draw.text((450, 125), voice, BORDER, font=font_small, stroke_width=1)
        # Filling text
        draw.text((245, 22), name, MAINCOLOR, font=font_normal)
        draw.text((245, 95), rank, MAINCOLOR, font=font_small)
        draw.text((245, 125), level, MAINCOLOR, font=font_small)
        draw.text((245, 160), exp, MAINCOLOR, font=font_small)
        # Filling text for 2nd column
        draw.text((450, 95), messages, MAINCOLOR, font=font_small)
        draw.text((450, 125), voice, MAINCOLOR, font=font_small)

        draw.text((747, 15), stars, BORDER, font=font_normal, stroke_width=1)
        draw.text((747, 15), stars, MAINCOLOR, font=font_normal)

        # Adding another blank layer for the progress bar
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        blank_draw = ImageDraw.Draw(blank)
        # rectangle 0:x, 1:top y, 2:length, 3:bottom y
        blank_draw.rectangle((240, 200, 750, 215), fill=(255, 255, 255, 0), outline=BORDER)

        xpneed = next_xp - current_xp
        xphave = user_xp - current_xp

        current_percentage = (xphave / xpneed) * 100
        length_of_bar = (current_percentage * 4.9) + 248

        blank_draw.rectangle((248, 203, length_of_bar, 212), fill=MAINCOLOR)

        # Pfp border
        # draw at 4x and resample down to 1x for nice smooth circles
        circle_img = Image.new("RGBA", (800, 800))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 796, 796], fill=(255, 255, 255, 0), outline=MAINCOLOR, width=12)
        circle_img = circle_img.resize((200, 200), Image.ANTIALIAS)
        card.paste(circle_img, (19, 19), circle_img)

        profile_pic_holder.paste(profile, (29, 29, 209, 209))

        pre = Image.composite(profile_pic_holder, card, mask)
        pre = Image.alpha_composite(pre, blank)

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
        status = status.convert("RGBA").resize((40, 40), Image.ANTIALIAS)
        rep_icon = Image.open(self.star)
        rep_icon = rep_icon.convert("RGBA").resize((40, 40), Image.ANTIALIAS)

        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (500, 50))

        # Status badge
        # Another blank
        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (169, 169))
        # Add rep star
        blank.paste(rep_icon, (700, 22))

        final = Image.alpha_composite(pre, blank)
        final_bytes = BytesIO()
        final.save(final_bytes, 'WEBP')
        final_bytes.seek(0)
        return final_bytes

    async def generate_profile_old(
            self,
            bg_image: str = None,
            profile_image: str = None,
            level: int = 1,
            current_xp: int = 0,
            user_xp: int = 20,
            next_xp: int = 100,
            user_position: int = 1,
            user_name: str = 'NotSpeified#0117',
            user_status: str = 'online',
            color: tuple = (0, 0, 0),
            messages: int = 0,
            voice: int = 0,
            prestige: int = 0,
            stars: int = 0,
    ):
        # Set canvas
        if not bg_image:
            card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.ANTIALIAS)
        else:
            bg_bytes = BytesIO(await self.get_image_content_from_url(bg_image))
            if bg_bytes:
                card = Image.open(bg_bytes).convert("RGBA").resize((900, 240), Image.ANTIALIAS)
            else:
                card = Image.open(self.default_bg).convert("RGBA").resize((900, 240), Image.ANTIALIAS)

        # Draw
        draw = ImageDraw.Draw(card)

        # PfP image
        profile_bytes = BytesIO(await self.get_image_content_from_url(str(profile_image)))
        profile = Image.open(profile_bytes)
        profile = profile.convert('RGBA').resize((180, 180), Image.ANTIALIAS)

        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))

        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((116, 116, 836, 836), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.ANTIALIAS)

        # Editing stuff here
        # ======== Fonts to use =============
        font_normal = ImageFont.truetype(self.font1, 40)
        font_small = ImageFont.truetype(self.font1, 25)
        # ======== Colors ========================
        MAINCOLOR = color
        BORDER = (0, 0, 0)

        def get_str(xp):
            return "{:,}".format(xp)

        rank = f"Rank: #{user_position}"
        level = f"Level: {level}"
        exp = f"Exp: {get_str(user_xp)}/{get_str(next_xp)}"
        messages = f"Messages: {messages}"
        voice = f"Voice Minutes: {voice}"
        name = f"{user_name}"
        if prestige:
            name += f" - Prestige {prestige}"
        stars = str(stars)

        # Drawing borders
        draw.text((245, 22), name, BORDER, font=font_normal, stroke_width=1)
        draw.text((245, 95), rank, BORDER, font=font_small, stroke_width=1)
        draw.text((245, 125), level, BORDER, font=font_small, stroke_width=1)
        draw.text((245, 160), exp, BORDER, font=font_small, stroke_width=1)
        # Borders for 2nd column
        draw.text((450, 95), messages, BORDER, font=font_small, stroke_width=1)
        draw.text((450, 125), voice, BORDER, font=font_small, stroke_width=1)
        # Filling text
        draw.text((245, 22), name, MAINCOLOR, font=font_normal)
        draw.text((245, 95), rank, MAINCOLOR, font=font_small)
        draw.text((245, 125), level, MAINCOLOR, font=font_small)
        draw.text((245, 160), exp, MAINCOLOR, font=font_small)
        # Filling text for 2nd column
        draw.text((450, 95), messages, MAINCOLOR, font=font_small)
        draw.text((450, 125), voice, MAINCOLOR, font=font_small)

        draw.text((747, 15), stars, BORDER, font=font_normal, stroke_width=1)
        draw.text((747, 15), stars, MAINCOLOR, font=font_normal)

        # Adding another blank layer for the progress bar
        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        blank_draw = ImageDraw.Draw(blank)
        # rectangle 0:x, 1:top y, 2:length, 3:bottom y
        blank_draw.rectangle((240, 200, 750, 215), fill=(255, 255, 255, 0), outline=BORDER)

        xpneed = next_xp - current_xp
        xphave = user_xp - current_xp

        current_percentage = (xphave / xpneed) * 100
        length_of_bar = (current_percentage * 4.9) + 248

        blank_draw.rectangle((248, 203, length_of_bar, 212), fill=MAINCOLOR)

        # Pfp border
        # draw at 4x and resample down to 1x for nice smooth circles
        circle_img = Image.new("RGBA", (800, 800))
        pfp_border = ImageDraw.Draw(circle_img)
        pfp_border.ellipse([4, 4, 796, 796], fill=(255, 255, 255, 0), outline=MAINCOLOR, width=12)
        circle_img = circle_img.resize((200, 200), Image.ANTIALIAS)
        card.paste(circle_img, (19, 19), circle_img)

        profile_pic_holder.paste(profile, (29, 29, 209, 209))

        pre = Image.composite(profile_pic_holder, card, mask)
        pre = Image.alpha_composite(pre, blank)

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
        status = status.convert("RGBA").resize((40, 40), Image.ANTIALIAS)
        rep_icon = Image.open(self.star)
        rep_icon = rep_icon.convert("RGBA").resize((40, 40), Image.ANTIALIAS)

        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (500, 50))

        # Status badge
        # Another blank
        blank = Image.new("RGBA", pre.size, (255, 255, 255, 0))
        blank.paste(status, (169, 169))
        # Add rep star
        blank.paste(rep_icon, (700, 22))

        final = Image.alpha_composite(pre, blank)
        final_bytes = BytesIO()
        final.save(final_bytes, 'WEBP')
        final_bytes.seek(0)
        return final_bytes

    async def generate_levelup(
            self,
            bg_image: str = None,
            profile_image: str = None,
            level: int = 1,
            color: tuple = (0, 0, 0),
    ):
        if not bg_image:
            card = Image.open(self.default_lvlup).convert("RGBA").resize((180, 70), Image.ANTIALIAS)
        else:
            bg_bytes = BytesIO(await self.get_image_content_from_url(bg_image))
            if bg_bytes:
                card = Image.open(bg_bytes).convert("RGBA").resize((180, 70), Image.ANTIALIAS)
            else:
                card = Image.open(self.default_lvlup).convert("RGBA").resize((180, 70), Image.ANTIALIAS)

        profile_bytes = BytesIO(await self.get_image_content_from_url(str(profile_image)))
        profile = Image.open(profile_bytes)
        profile = profile.convert('RGBA').resize((60, 60), Image.ANTIALIAS)

        # Is used as a blank image for mask
        profile_pic_holder = Image.new("RGBA", card.size, (255, 255, 255, 0))

        # Mask to crop profile image
        # draw at 4x size and resample down to 1x for a nice smooth circle
        mask = Image.new("RGBA", ((card.size[0] * 4), (card.size[1] * 4)), 0)
        mask_draw = ImageDraw.Draw(mask)
        # Profile pic border at 4x
        mask_draw.ellipse((36, 36, 240, 240), fill=(255, 255, 255, 255))
        mask = mask.resize(card.size, Image.ANTIALIAS)

        if len(str(level)) > 2:
            size = 19
        else:
            size = 24
        font_normal = ImageFont.truetype(self.font1, size)

        MAINCOLOR = color
        BORDER = (0, 0, 0)

        draw = ImageDraw.Draw(card)
        level = f"Level {level}"

        # Drawing borders
        draw.text((73, 16), level, BORDER, font=font_normal, stroke_width=1)
        # Filling text
        draw.text((73, 16), level, MAINCOLOR, font=font_normal)

        blank = Image.new("RGBA", card.size, (255, 255, 255, 0))
        profile_pic_holder.paste(profile, (5, 5))

        pre = Image.composite(profile_pic_holder, card, mask)
        pre = Image.alpha_composite(pre, blank)

        final = Image.alpha_composite(pre, blank)
        final_bytes = BytesIO()
        final.save(final_bytes, 'WEBP')
        final_bytes.seek(0)
        return final_bytes

    async def get_image_content_from_url(self, url: str):
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
        except Exception:
            log.error(f"General failure accessing image at url:\n\t{url}", exc_info=True)
            return None
