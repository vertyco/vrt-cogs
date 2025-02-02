import logging
import typing as t

import discord
import orjson
from pydantic import VERSION, BaseModel

log = logging.getLogger("red.vrt.fluent.models")


class _Base(BaseModel):
    @classmethod
    def model_validate(cls, obj: t.Any, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = True):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults))


class TranslateButton(_Base):
    channel_id: int
    message_id: int

    target_lang: str
    button_text: str

    original_content: t.Optional[str] = None  # original text
    translated_content: t.Optional[str] = None  # translated text

    original_embeds: t.Optional[t.List[dict]] = None  # original embeds
    translated_embeds: t.Optional[t.List[dict]] = None  # translated embeds

    def up_to_date(self, message: discord.Message) -> bool:
        # Ensure the source message is still the same
        if message.content and not message.embeds:
            return message.content == self.original_content
        matches = [message.content == self.original_content]
        for embed in message.embeds:
            if self.original_embeds is None:
                self.original_embeds = []
            matches.append(embed.to_dict() in self.original_embeds)
        return all(matches)

    def get_embeds(self) -> t.List[discord.Embed]:
        embeds = []
        if not self.translated_embeds:
            return embeds
        for embed_dict in self.translated_embeds:
            embeds.append(discord.Embed.from_dict(embed_dict))
        return embeds

    def __hash__(self):
        uid = f"{self.channel_id}-{self.message_id}-{self.target_lang}"
        return hash(uid)

    def __str__(self) -> str:
        return f"{self.channel_id}/{self.message_id} -> {self.target_lang}"
