import discord
import orjson
from pydantic import VERSION, BaseModel, EmailStr


class Base(BaseModel):
    def model_dump(self):
        if VERSION >= "2.0.1":
            return super().model_dump(mode="json")
        return orjson.loads(super().json())

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)


class EmailAccount(Base):
    email: EmailStr
    password: str
    signature: str | None = None

    def __str__(self):
        return self.email


class GuildSettings(Base):
    accounts: list[EmailAccount] = []
    allowed_roles: list[int] = []


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
