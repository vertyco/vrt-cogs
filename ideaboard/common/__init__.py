import orjson
from pydantic import VERSION, BaseModel


class Base(BaseModel):
    @classmethod
    def load(cls, obj):
        if VERSION >= "2.0.1":
            return super().model_validate(obj)
        return super().parse_obj(obj)

    def dump(self):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json", exclude_defaults=True)
        return orjson.loads(super().json(exclude_defaults=True))
