from __future__ import annotations

import typing as t

import orjson
from pydantic import VERSION, BaseModel


class Base(BaseModel):
    def model_dump(self, *args, **kwargs) -> t.Dict[str, t.Any]:
        if VERSION >= "2.0.1":
            return super().model_dump(*args, exclude_defaults=True, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, exclude_defaults=True, **kwargs))
        return super().dict(*args, **kwargs)

    def model_dump_json(self, *args, **kwargs) -> str:
        if VERSION >= "2.0.1":
            return super().model_dump_json(*args, exclude_defaults=True, **kwargs)
        return super().json(*args, exclude_defaults=True, **kwargs)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs) -> t.Self:
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_copy(self, *args, **kwargs) -> t.Self:
        if VERSION >= "2.0.1":
            return super().model_copy(*args, **kwargs)
        return super().copy(*args, **kwargs)
