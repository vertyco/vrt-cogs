import orjson
from pydantic import VERSION, BaseModel


class Base(BaseModel):
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, exclude_defaults: bool = True, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=exclude_defaults, **kwargs)
        return orjson.loads(super().json(exclude_defaults=exclude_defaults, **kwargs))
