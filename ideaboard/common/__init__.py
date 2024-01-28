import orjson
from pydantic import VERSION, BaseModel


class Base(BaseModel):
    def model_dump_json(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump_json(*args, **kwargs)
        return super().json(*args, **kwargs)

    def model_dump(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(*args, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, **kwargs))
        return super().dict(*args, **kwargs)

    @classmethod
    def model_validate_json(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate_json(obj, *args, **kwargs)
        return super().parse_raw(obj, *args, **kwargs)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)
