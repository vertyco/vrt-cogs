from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Set, Type, TypeVar
from uuid import uuid4

import typing_extensions
from pydantic import VERSION, BaseModel
from pydantic.deprecated.parse import Protocol as DeprecatedParseProtocol
from pydantic_core import PydanticUndefined

Model = TypeVar("Model", bound="BaseModel")
IncEx: typing_extensions.TypeAlias = "Set[int] | Set[str] | Dict[int, Any] | Dict[str, Any] | None"
log = logging.getLogger("red.vrt.cookiecutter")


class Base(BaseModel):
    @classmethod
    def model_validate(
        cls: Type[Model],
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
    ) -> Model:
        if VERSION >= "2.0.1":
            return super().model_validate(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
            )
        return super().parse_obj(obj)

    @classmethod
    def model_validate_json(
        cls: Type[Model],
        json_data: str | bytes | bytearray,
        *,
        # >= 2.0.1
        strict: bool | None = None,
        context: dict[str, Any] | None = None,
        # < 2.0.1
        content_type: str | None = None,
        encoding: str = "utf8",
        proto: DeprecatedParseProtocol | None = None,
        allow_pickle: bool = False,
    ):
        if VERSION >= "2.0.1":
            return super().model_validate_json(
                json_data,
                strict=strict,
                context=context,
            )
        return super().parse_raw(
            json_data,
            content_type=content_type,
            encoding=encoding,
            proto=proto,
            allow_pickle=allow_pickle,
        )

    def model_dump(
        self,
        *,
        mode: Literal["json", "python"] | str = "python",
        include: IncEx = None,
        exclude: IncEx = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = True,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: bool = True,
    ):
        if VERSION >= "2.0.1":
            return super().model_dump(
                mode=mode,
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
            )
        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def model_dump_json(
        self,
        *,
        indent: int | None = None,
        include: IncEx = None,
        exclude: IncEx = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = True,
        exclude_none: bool = False,
        # >= 2.0.1
        round_trip: bool = False,
        warnings: bool = True,
        # < 2.0.1
        encoder: Callable[[Any], Any] | None = PydanticUndefined,
        models_as_dict: bool = PydanticUndefined,
        **dumps_kwargs: Any,
    ):
        if VERSION >= "2.0.1":
            return super().model_dump_json(
                indent=indent,
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
            )
        return super().json(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            encoder=encoder,
            models_as_dict=models_as_dict,
            **dumps_kwargs,
        )

    @classmethod
    def from_file(cls, path: Path) -> Base:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise IsADirectoryError(f"Path is not a file: {path}")
        if VERSION >= "2.0.1":
            return cls.model_validate_json(path.read_bytes())
        return cls.parse_file(path)

    def to_file(self, path: Path) -> None:
        dump = self.model_dump_json(exclude_defaults=True)
        # We want to write the file as safely as possible
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/_drivers/json.py#L224
        tmp_path = path.parent / f"{path.stem}-{uuid4().fields[0]}.tmp"
        with tmp_path.open(encoding="utf-8", mode="w") as fs:
            fs.write(dump)
            fs.flush()  # This does get closed on context exit, ...
            os.fsync(fs.fileno())  # but that needs to happen prior to this line

        # Replace the original file with the new content
        try:
            tmp_path.replace(path)
        except FileNotFoundError as e:
            log.error(f"Failed to rename {tmp_path} to {path}", exc_info=e)

        # Ensure directory fsync for better durability
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
