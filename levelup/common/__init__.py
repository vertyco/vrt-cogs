import os
import typing as t
from pathlib import Path
from time import perf_counter

from pydantic import VERSION, BaseModel


class Base(BaseModel):
    @classmethod
    def load(cls, obj: t.Dict[str, t.Any]) -> t.Self:
        if VERSION >= "2.0.1":
            return cls.model_validate(obj)
        return cls.parse_obj(obj)

    @classmethod
    def from_file(cls, path: Path) -> t.Self:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if VERSION >= "2.0.1":
            return cls.model_validate_json(path.read_text())
        return cls.parse_file(path)

    def to_file(self, path: Path) -> None:
        if VERSION >= "2.0.1":
            dump = self.model_dump_json(indent=2, exclude_defaults=True)
        else:
            dump = self.json(exclude_defaults=True)
        # We want to write the file as safely as possible
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/core/_drivers/json.py#L224
        tmp_path = path.parent / f"{path.stem}-{round(perf_counter())}.tmp"
        with tmp_path.open(encoding="utf-8", mode="w") as fs:
            fs.write(dump)
            fs.flush()  # This does get closed on context exit, ...
            os.fsync(fs.fileno())  # but that needs to happen prior to this line

        tmp_path.replace(path)

        try:
            flag = os.O_DIRECTORY  # pylint: disable=no-member
        except AttributeError:
            pass
        else:
            fd = os.open(path.parent, flag)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
