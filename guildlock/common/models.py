import orjson
from pydantic import VERSION, BaseModel


class FriendlyBase(BaseModel):
    def model_dump(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(*args, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, **kwargs))
        return super().dict(*args, **kwargs)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)


class DB(FriendlyBase):
    limit: int = 0
    log_channel: int = 0
    log_guild: int = 0
    min_members: int = 0
    bot_ratio: int = 0
    whitelist: list[int] = []
    blacklist: list[int] = []
