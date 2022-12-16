import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import googletrans
from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)
from redbot.core.bot import Red


class Result:
    def __init__(self, text: str, src: str, dest: str):
        self.text = text
        self.src = src
        self.dest = dest

    def __str__(self):
        return f"Result: {self.text}, source: {self.src}, target: {self.dest}"


class TranslateManager:
    def __init__(self, bot: Red):
        self.bot = bot
        self.threadpool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fluent")

    async def translate(self, text: str, target_lang: str) -> Optional[Result]:
        res = await self.google(text, target_lang)
        if res is None or res.text == text:
            res = await self.flowery(text, target_lang)
        return res

    async def google(self, text: str, target_lang: str) -> Optional[Result]:
        translator = googletrans.Translator()
        try:
            res = await self.bot.loop.run_in_executor(
                self.threadpool,
                functools.partial(translator.translate, text, target_lang),
            )
            result = Result(text=res.text, src=res.src, dest=res.dest)
            return result
        except AttributeError:
            return None

    @staticmethod
    async def flowery(text: str, target_lang: str) -> Optional[Result]:
        endpoint = "https://api.flowery.pw/v1/translation/translate"
        params = {"text": text, "result_language_code": target_lang}
        timeout = ClientTimeout(total=6)
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url=endpoint, params=params) as res:
                    if res.status == 200:
                        data = await res.json()
                        result = Result(
                            text=data["text"],
                            src=data["language"]["original"],
                            dest=data["language"]["result"],
                        )
                        return result
        except (ClientResponseError, ClientConnectorError):
            return None
