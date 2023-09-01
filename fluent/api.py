import asyncio
import logging
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

log = logging.getLogger("red.vrt.fluent.api")


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
        lang = await self.convert(target_lang)
        if not lang:
            log.info("Failed to fetch target language")
            return
        res = None
        if self.deepl_key:
            res = await self.deepl(text, lang, formality)
        if res is None:
            log.debug("Calling google translate")
            res = await self.google(text, lang)
            if res is None:
                log.debug("Calling flowery as fallback")
                res = await self.flowery(text, lang)
        return res

    async def convert(self, language: str) -> t.Optional[str]:
        lang = await self.get_deepl_lang(language)
        if not lang:
            lang = await self.get_lang(language)
        return lang

    async def get_lang(self, target_language: str) -> t.Optional[str]:
        language = target_language.strip().lower()
        for key, value in googletrans.LANGUAGES.items():
            if language == value.lower() or language == key.lower():
                return key

    async def get_deepl_lang(self, target_language: str) -> t.Optional[str]:
        if not self.deepl_key:
            return
        language = target_language.strip().lower()
        if language in ["pt", "portuguese"]:
            language = "portuguese (brazilian)"
        elif language in ["en", "english"]:
            language = "english (american)"
        elif language in ["chinese", "zh"]:
            language = "chinese (simplified)"

        translator = deepl.Translator(self.deepl_key, send_platform_info=False)
        languages = await asyncio.to_thread(translator.get_target_languages)
        for lang_obj in languages:
            if language == lang_obj.name.lower() or language == lang_obj.code.lower():
                return lang_obj

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
            translator.translate_text, text=text, target_lang=target_lang, formality=formality
        )
        return Result(text=res.text, src=res.detected_source_lang, dest=target_lang)

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
