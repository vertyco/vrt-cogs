import logging

import orjson
from pydantic import VERSION, BaseModel

log = logging.getLogger("red.vrt.setools.common")


class Base(BaseModel):
    def model_dump(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(*args, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, **kwargs))
        return super().dict(*args, **kwargs)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        for key in obj.keys():
            if key not in cls.__annotations__:
                log.error(f"Unknown key {key} in payload for {cls.__name__}")
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)
