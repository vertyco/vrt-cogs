# THANKS TRUSTY!
# This converter/api is a modified snippet of the notsobot cog from TrustyJAID.
# https://github.com/TrustyJAID/Trusty-cogs/blob/b2842005c88451f4670bc25f5c000ce6aed79c8c/notsobot/converter.py
"""MIT License

Copyright (c) 2017-present TrustyJAID

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

from __future__ import annotations

import re
import typing as t
from dataclasses import dataclass

import aiohttp
from red_commons.logging import getLogger
from redbot.core import commands

IMAGE_LINKS: t.Pattern = re.compile(
    r"(https?:\/\/[^\"\'\s]*\.(?P<extension>png|jpg|jpeg|gif)"
    r"(?P<extras>\?(?:ex=(?P<expires>\w+)&)(?:is=(?P<issued>\w+)&)(?:hm=(?P<token>\w+)&))?)",  # Discord CDN info
    flags=re.I,
)
TENOR_REGEX: t.Pattern[str] = re.compile(r"https:\/\/tenor\.com\/view\/(?P<image_slug>[a-zA-Z0-9-]+-(?P<image_id>\d+))")
EMOJI_REGEX: t.Pattern = re.compile(r"(<(?P<animated>a)?:[a-zA-Z0-9\_]+:([0-9]+)>)")
MENTION_REGEX: t.Pattern = re.compile(r"<@!?([0-9]+)>")
ID_REGEX: t.Pattern = re.compile(r"[0-9]{17,}")

VALID_CONTENT_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/gif")

log = getLogger("red.trusty-cogs.NotSoBot")


class TenorError(Exception):
    pass


@dataclass
class TenorMedia:
    url: str
    duration: int
    preview: str
    dims: t.List[int]
    size: int

    @classmethod
    def from_json(cls, data: dict) -> TenorMedia:
        return cls(**data)


@dataclass
class TenorPost:
    id: str
    title: str
    media_formats: t.Dict[str, TenorMedia]
    created: float
    content_description: str
    itemurl: str
    url: str
    tags: t.List[str]
    flags: t.List[str]
    hasaudio: bool

    @classmethod
    def from_json(cls, data: dict) -> TenorPost:
        media = {k: TenorMedia.from_json(v) for k, v in data.pop("media_formats", {}).items()}
        return cls(**data, media_formats=media)


class TenorAPI:
    def __init__(self, token: str, client: str):
        self._token = token
        self._client = client
        self.session = aiohttp.ClientSession(base_url="https://tenor.googleapis.com")

    async def posts(self, ids: t.List[str]):
        params = {"key": self._token, "ids": ",".join(i for i in ids), "client_key": self._client}
        async with self.session.get("/v2/posts", params=params) as resp:
            data = await resp.json()
            if "error" in data:
                raise TenorError(data)
        return [TenorPost.from_json(i) for i in data.get("results", [])]


async def sanitize_url(url: str, ctx: commands.Context) -> str:
    match = IMAGE_LINKS.match(url)
    if match:
        return match.group(1)
    tenor = TENOR_REGEX.match(url)
    if not tenor:
        return url
    api = ctx.cog.tenor
    if not api:
        return url
    try:
        posts = await api.posts([tenor.group("image_id")])
        for post in posts:
            if "gif" in post.media_formats:
                return post.media_formats["gif"].url
    except TenorError as e:
        log.error("Error getting tenor image information. %s", e)
    except Exception as e:
        log.error("Unknown Error getting tenor image information. %s", e)
    return url
