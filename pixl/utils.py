import asyncio
import contextlib
import logging
import random
from datetime import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

import discord
from aiocache import cached
from aiohttp import ClientSession, ClientTimeout
from PIL import Image
from rapidfuzz import fuzz
from redbot.core import VersionInfo, commands, version_info

log = logging.getLogger("red.vrt.pixl.generator")
dpy2 = True if version_info >= VersionInfo.from_str("3.5.0") else False


def is_valid_url(url: str) -> bool:
    """Basic URL validation"""
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception as e:
        log.error("Error parsing url", exc_info=e)
        return False


# Reduced cache time to avoid stale results
@cached(ttl=120)
async def get_content_from_url(url: str, timeout: Optional[int] = 60) -> Optional[bytes]:
    """
    Get content from a URL with improved headers and retry logic for 403/404 errors.

    Args:
        url: The URL to fetch content from
        timeout: Timeout in seconds

    Returns:
        Optional[bytes]: The content if successful, otherwise None
    """
    # First do basic URL validation
    if not is_valid_url(url):
        log.error(f"Invalid URL format: {url}")
        return None

    # More browser-like headers to avoid 403 errors
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }

    # Try up to 3 times with increasing delay
    max_retries = 3
    retry_delay = 1

    for attempt in range(1, max_retries + 1):
        try:
            async with ClientSession(timeout=ClientTimeout(total=timeout), headers=headers) as session:
                async with session.get(url, allow_redirects=True, ssl=False) as res:
                    if res.status != 200:
                        # Handle specific HTTP errors
                        if res.status == 404:
                            log.error(f"Resource not found (404): {url}")
                            return None  # Don't retry 404s - the resource doesn't exist
                        elif res.status in (403, 429) and attempt < max_retries:
                            retry_delay_with_jitter = retry_delay + random.uniform(0, 0.5)
                            log.warning(
                                f"Received {res.status} for {url}. Retrying in {retry_delay_with_jitter:.2f}s (attempt {attempt}/{max_retries})"
                            )
                            await asyncio.sleep(retry_delay_with_jitter)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            log.error(f"Failed to fetch content from url: HTTP {res.status}")
                            return None

                    content_type = res.headers.get("Content-Type", "")
                    if not content_type.startswith("image/"):
                        log.error(f"URL doesn't contain image data: {content_type}")
                        return None

                    image_data = await res.read()
                    # Simple check for minimal valid image data size
                    if len(image_data) < 100:
                        log.error(f"Image data too small ({len(image_data)} bytes): {url}")
                        return None

                    return image_data
        except Exception as e:
            if attempt < max_retries:
                log.warning(f"Error fetching {url}: {e}. Retrying... (attempt {attempt}/{max_retries})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                log.error(f"Failed to fetch content from url after {max_retries} attempts: {e}")
                return None


async def delete(message: discord.Message):
    with contextlib.suppress(discord.Forbidden, discord.NotFound, discord.HTTPException):
        await message.delete()


async def listener(ctx: commands.Context, data: dict):
    def check(message: discord.Message):
        return ctx.channel == message.channel and not message.author.bot

    while True:
        if not data["in_progress"]:
            return
        tasks = [asyncio.ensure_future(ctx.bot.wait_for("message", check=check))]
        done, pending = await asyncio.wait(tasks, timeout=60)
        [task.cancel() for task in pending]
        if len(done) == 0:
            continue
        res: discord.Message = done.pop().result()
        if not res.content.strip():
            continue
        data["responses"].append((res.author, res.content.strip().lower(), datetime.now().timestamp()))
        data["participants"].add(res.author)


class PixlGrids:
    """Slowly reveal blocks from an image while waiting for text response"""

    def __init__(
        self,
        ctx: commands.Context,
        image: Image.Image,
        answers: list,
        amount_to_reveal: int,
        time_limit: int,
        fuzzy_threshold: int = 92,
    ):
        self.ctx = ctx
        self.image = image
        self.answers = answers
        self.amount_to_reveal = amount_to_reveal
        self.time_limit = time_limit
        self.fuzzy_threshold = fuzzy_threshold
        # Game stuff
        self.start = datetime.now()
        self.time_left = f"<t:{round(self.start.timestamp() + self.time_limit)}:R>"
        self.winner = None
        self.data = {"in_progress": True, "responses": [], "participants": set()}
        self.to_chop = []
        self.task: asyncio.Task = None
        # Make solid blank canvas to paste image pieces on
        self.blank = Image.new("RGBA", image.size, (0, 0, 0, 256))

    def __aiter__(self):
        self.init()
        return self

    async def __anext__(self) -> discord.File:
        end_conditions = [
            len(self.to_chop) <= 0,  # Image is fully revealed
            self.have_winner(),  # Someone guessed it right
            (datetime.now() - self.start).total_seconds() > self.time_limit,  # Time is up
        ]
        if any(end_conditions):
            self.data["in_progress"] = False
            raise StopAsyncIteration
        pop = self.amount_to_reveal if self.amount_to_reveal <= len(self.to_chop) else len(self.to_chop)
        for _ in range(pop):
            bbox = self.to_chop.pop(random.randrange(len(self.to_chop)))
            cropped = await asyncio.to_thread(self.image.crop, bbox)
            await asyncio.to_thread(self.blank.paste, cropped, (bbox[0], bbox[1]))
        buffer = BytesIO()
        buffer.name = f"{random.randint(999, 9999999)}.webp"
        self.blank.save(buffer, format="WEBP", quality=100)
        buffer.seek(0)
        return discord.File(buffer, filename=buffer.name)

    async def __aexit__(self):
        if self.task:
            self.task.cancel()

    def init(self) -> None:
        # Add game starter to participants
        self.data["participants"].add(self.ctx.author)
        # Get box size to fit 192 boxes (16 by 12) or (12 by 16)
        horiz, vert = (16, 12) if self.image.width > self.image.height else (12, 16)
        w, h = (self.image.width / horiz, self.image.height / vert)
        # Get block locations to chop the image up and paste to the canvas iteratively
        for x in range(horiz):
            for y in range(vert):
                x1 = x * w
                y1 = y * h
                x2 = (x * w) + w
                y2 = (y * h) + h
                bbox = (round(x1), round(y1), round(x2), round(y2))
                self.to_chop.append(bbox)
        # Start the message listener
        self.task = asyncio.create_task(listener(self.ctx, self.data))

    async def get_result(self) -> discord.File:
        buffer = BytesIO()
        buffer.name = f"{random.randint(999, 9999999)}.webp"
        self.image.save(buffer, format="WEBP", quality=100)
        buffer.seek(0)
        return discord.File(buffer, filename=buffer.name)

    def have_winner(self) -> bool:
        responses = sorted(self.data["responses"].copy(), key=lambda x: x[2], reverse=False)
        self.data["responses"].clear()
        for author, answer, _ in responses:
            if not self.fuzzy_threshold:
                if answer in self.answers:
                    self.winner = author
                    return True
            elif any([fuzz.ratio(answer.lower(), a.lower()) > self.fuzzy_threshold for a in self.answers]):
                self.winner = author
                return True
        else:
            return False
