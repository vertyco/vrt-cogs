import sqlite3

from piccolo.engine import sqlite


### MONKEYPATCHING ###
# This is a workaround for a bug in Piccolo's SQLite engine where it doesn't handle integers correctly.
@sqlite.decode_to_string
def convert_int_out(value: str) -> int:
    return int(value)


sqlite.CONVERTERS["INTEGER"] = convert_int_out
sqlite3.register_converter("INTEGER", convert_int_out)
### END MONKEYPATCHING ###
