import asyncio
import typing as t

import deepl
import googletrans
from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)
from httpx import ReadTimeout


class Result:
    def __init__(self, text: str, src: str, dest: str):
        self.text = text
        self.src = src
        self.dest = dest

    def __str__(self):
        return f"Result: {self.text}, source: {self.src}, target: {self.dest}"


class TranslateManager:
    def __init__(self, deepl_key: t.Optional[str] = None):
        self.deepl_key = deepl_key

    async def translate(
        self,
        text: str,
        target_lang: str,
        formality: t.Optional[str] = None,
    ) -> t.Optional[Result]:
        lang = await asyncio.to_thread(self.convert, target_lang)
        if not lang:
            return
        res = None
        if self.deepl_key:
            res = await self.deepl(text, lang, formality)
        if res is None:
            res = await self.google(text, lang)
            if res is None or res.text == text:
                res = await self.flowery(text, lang)
        return res

    def convert(self, language: str) -> t.Optional[str]:
        language = language.strip().lower()
        if language == "chinese":
            language = "chinese (simplified)"
        elif language == "pt":
            language = "PT-PT"
        elif language == "portuguese":
            language = "PT-PT"

        if self.deepl_key:
            translator = deepl.Translator(self.deepl_key, send_platform_info=False)
            for lang_obj in translator.get_target_languages():
                if language == lang_obj.name.lower() or language == lang_obj.code.lower():
                    return lang_obj.code

        for key, value in googletrans.LANGUAGES.items():
            if language == value.lower() or language == key.lower():
                return key

    async def deepl(
        self,
        text: str,
        target_lang: str,
        formality: t.Optional[str] = None,
    ) -> t.Optional[Result]:
        translator = deepl.Translator(self.deepl_key, send_platform_info=False)
        usage = await asyncio.to_thread(translator.get_usage)
        if usage.any_limit_reached:
            return None
        res = await asyncio.to_thread(
            translator.translate_text,
            text=text,
            target_lang=target_lang,
            formality=formality,
            preserve_formatting=True,
        )
        return Result(
            text=res.text,
            src=res.detected_source_lang,
            dest=target_lang,
        )

    async def google(self, text: str, target_lang: str) -> t.Optional[Result]:
        translator = googletrans.Translator()
        try:
            res = await asyncio.to_thread(translator.translate, text, target_lang)
            return Result(text=res.text, src=res.src, dest=res.dest)
        except (AttributeError, TypeError, ReadTimeout):
            return None

    @staticmethod
    async def flowery(text: str, target_lang: str) -> t.Optional[Result]:
        endpoint = "https://api.flowery.pw/v1/translation/translate"
        params = {"text": text, "result_language_code": target_lang}
        timeout = ClientTimeout(total=10)
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url=endpoint, params=params) as res:
                    if res.status == 200:
                        data = await res.json()
                        return Result(
                            text=data["text"],
                            src=data["language"]["original"],
                            dest=data["language"]["result"],
                        )
        except (ClientResponseError, ClientConnectorError):
            return None
