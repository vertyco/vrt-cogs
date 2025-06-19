import asyncio
import logging
import typing as t

import deepl
import googletrans
import openai
from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)
from httpx import ReadTimeout
from pydantic import BaseModel
from rapidfuzz import fuzz

from .constants import deepl_langs, google_langs

log = logging.getLogger("red.vrt.fluent.api")


class Result:
    def __init__(self, text: str, src: str, dest: str):
        self.text = text
        self.src = src
        self.dest = dest

    def __str__(self):
        return f"Result: {self.text}, source: {self.src}, target: {self.dest}"


class OpenAITranslateResponse(BaseModel):
    translated_text: str
    detected_source_language: str


class TranslateManager:
    def __init__(
        self,
        deepl_key: t.Optional[str] = None,
        openai_key: t.Optional[str] = None,
    ):
        self.deepl_key = deepl_key
        self.openai_key = openai_key

    async def translate(
        self,
        text: str,
        target_lang: str,
        formality: t.Optional[str] = None,
        force: bool = False,
    ) -> t.Optional[Result]:
        """Translate given text to another language

        Args:
            text (str): the text to be translated
            target_lang (str): the target language
            formality (t.Optional[str], optional): whether the translation should be formal. Defaults to None.
            force (bool, optional): If False, force res back to None if result is same as source text. Defaults to False.

        Returns:
            t.Optional[Result]: Result object containing source/target lang and translated text
        """
        target_lang = target_lang.lower()
        res = None
        log.debug(f"Translate {target_lang}")
        if self.openai_key:
            log.debug("Using openai")
            res = await self.openaitranslate(text, target_lang)
            if res is None or (res.text == text and not force):
                log.warning(f"OpenAI failed to translate to {target_lang}")
                res = None

        if self.deepl_key and res is None:
            if lang := await self.fuzzy_deepl_lang(target_lang.lower()):
                log.debug("Using deepl")
                res = await self.deepl(text, lang, formality)
                if res is None or (res.text == text and not force):
                    log.warning(f"Deepl failed to translate to {target_lang}")
                    res = None

        if res is None:
            if lang := await self.fuzzy_google_flowery_lang(target_lang.lower()):
                res = await self.google(text, lang)
                if res is None or (res.text == text and not force):
                    log.info("Google failed. Calling flowery as fallback")
                    res = await self.flowery(text, lang)
                    if res is None:
                        log.info("Flowery returned None as well")
        return res

    async def get_lang(self, target: str) -> t.Optional[str]:
        return await self.fuzzy_deepl_lang(target.lower()) or await self.fuzzy_google_flowery_lang(target.lower())

    async def fuzzy_deepl_lang(self, target: str) -> t.Optional[str]:
        def _fuzzy_deepl_lang():
            if len(target) == 2 or "-" in target:
                for i in deepl_langs:
                    if i["language"].lower() == target:
                        return i["language"]
                return None

            scores = [(i["language"], fuzz.ratio(i["name"].lower(), target)) for i in deepl_langs]
            lang = max(scores, key=lambda x: x[1])
            if lang[1] > 80:
                return lang[0]

        return await asyncio.to_thread(_fuzzy_deepl_lang)

    async def fuzzy_google_flowery_lang(self, target: str) -> t.Optional[str]:
        def _fuzzy_google_flowery_lang():
            if len(target) == 2 or "-" in target:
                for i in google_langs:
                    if i["language"].lower() == target:
                        return i["language"]
                return None

            scores = [(i["language"], fuzz.ratio(i["name"].lower(), target)) for i in google_langs]
            lang = max(scores, key=lambda x: x[1])
            if lang[1] > 80:
                return lang[0]

        return await asyncio.to_thread(_fuzzy_google_flowery_lang)

    async def openaitranslate(
        self,
        text: str,
        target_lang: str,
    ):
        client = openai.AsyncClient(api_key=self.openai_key)
        try:
            response = await client.beta.chat.completions.parse(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "developer", "content": f"Translate the given text to {target_lang}"},
                    {"role": "user", "content": text},
                ],
                response_format=OpenAITranslateResponse,
            )
            result = response.choices[0].message.parsed
            return Result(text=result.translated_text, src=result.detected_source_language, dest=target_lang)
        except Exception as e:
            log.error(f"Failed to make openai translation to {target_lang}", exc_info=e)

    async def deepl(
        self,
        text: str,
        target_lang: str,
        formality: t.Optional[str] = None,
    ) -> t.Optional[Result]:
        log.debug(f"Deepl: {target_lang}")
        translator = deepl.Translator(self.deepl_key, send_platform_info=False)
        usage = await asyncio.to_thread(translator.get_usage)
        if usage.any_limit_reached:
            log.warning("Deepl usage limit reached!")
            return None
        try:
            res = await asyncio.to_thread(
                translator.translate_text, text=text, target_lang=target_lang, formality=formality
            )
            return Result(text=res.text, src=res.detected_source_lang, dest=target_lang)
        except deepl.exceptions.DeepLException as e:
            log.error(f"Failed to make deepl translation to {target_lang}", exc_info=e)

    async def google(self, text: str, target_lang: str) -> t.Optional[Result]:
        log.debug(f"Google: {target_lang}")
        translator = googletrans.Translator()
        try:
            res = await asyncio.to_thread(translator.translate, text, target_lang)
            return Result(text=res.text, src=res.src, dest=res.dest)
        except (AttributeError, TypeError, ReadTimeout):
            return None

    @staticmethod
    async def flowery(text: str, target_lang: str) -> t.Optional[Result]:
        log.debug(f"Flowery: {target_lang}")
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
