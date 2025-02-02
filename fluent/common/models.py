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
        if message.content != self.original_content:
            log.debug(f"Content mismatch for {self}")
            return False
        if message.embeds and not self.original_embeds:
            log.debug(f"Embed mismatch for {self}, no original embeds")
            return False
        if not message.embeds and self.original_embeds:
            log.debug(f"Embed mismatch for {self}, no current embeds")
            return False
        if len(message.embeds) != len(self.original_embeds):
            log.debug(f"Embed mismatch for {self}, different embed count")
            return False
        for idx, embed in enumerate(message.embeds):
            if self.original_embeds is None:
                log.debug(f"Embed mismatch for {self}, no original embeds")
                return False
            if idx >= len(self.original_embeds):
                log.debug(f"Embed mismatch for {self}, different embed count")
                return False
            saved_embed = self.original_embeds[idx]
            if embed.author and not saved_embed.get("author"):
                log.debug(f"Embed mismatch for {self}, author mismatch for embed {idx}, saved has no author")
                return False
            if not embed.author and saved_embed.get("author"):
                log.debug(f"Embed mismatch for {self}, author mismatch for embed {idx}, current has no author")
                return False
            if embed.author and saved_embed.get("author"):
                if embed.author.name != saved_embed["author"].get("name"):
                    log.debug(f"Embed mismatch for {self}, author mismatch for embed {idx}, name mismatch")
                    return False
                if embed.author.url != saved_embed["author"].get("url"):
                    log.debug(f"Embed mismatch for {self}, author mismatch for embed {idx}, url mismatch")
                    return False
                if embed.author.icon_url != saved_embed["author"].get("icon_url"):
                    log.debug(f"Embed mismatch for {self}, author mismatch for embed {idx}, icon_url mismatch")
                    return False
            if embed.title != saved_embed.get("title"):
                log.debug(f"Embed mismatch for {self}, title mismatch for embed {idx}")
                return False
            if embed.description != saved_embed.get("description"):
                log.debug(f"Embed mismatch for {self}, description mismatch for embed {idx}")
                return False
            if embed.fields and not saved_embed.get("fields"):
                log.debug(f"Embed mismatch for {self}, fields mismatch for embed {idx}")
                return False
            if not embed.fields and saved_embed.get("fields"):
                log.debug(f"Embed mismatch for {self}, fields mismatch for embed {idx}")
                return False
            if len(embed.fields) != len(saved_embed.get("fields", [])):
                log.debug(f"Embed mismatch for {self}, fields mismatch for embed {idx}")
                return False
            saved_fields = saved_embed.get("fields", [])
            for field_idx, field in enumerate(embed.fields):
                if field_idx >= len(saved_fields):
                    log.debug(
                        f"Embed mismatch for {self}, fields mismatch for embed {idx} on field {field_idx}, index out of range"
                    )
                    return False
                saved_field = saved_fields[field_idx]
                if field.name != saved_field.get("name"):
                    log.debug(
                        f"Embed mismatch for {self}, fields mismatch for embed {idx} on field {field_idx}, name mismatch: {field.name} != {saved_field.get('name')}"
                    )
                    return False
                if field.value != saved_field.get("value"):
                    log.debug(
                        f"Embed mismatch for {self}, fields mismatch for embed {idx} on field {field_idx}, value mismatch: {field.value} != {saved_field.get('value')}"
                    )
                    return False
        return True

    def get_embeds(self) -> t.List[discord.Embed]:
        embeds = []
        if not self.translated_embeds:
            return embeds
        for embed_dict in self.translated_embeds:
            embeds.append(discord.Embed.from_dict(embed_dict))
        return embeds

    def __hash__(self):
        return hash((self.channel_id, self.message_id, self.target_lang))

    def __eq__(self, other):
        if not isinstance(other, TranslateButton):
            return False
        return (self.channel_id, self.message_id, self.target_lang) == (
            other.channel_id,
            other.message_id,
            other.target_lang,
        )

    def __str__(self) -> str:
        return f"{self.channel_id}/{self.message_id} -> {self.target_lang}"
