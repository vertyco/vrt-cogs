from piccolo.columns import Serial, Text
from piccolo.table import Table


class MyTable(Table):
    id = Serial
    name = Text(default="Example", help_text="This would show up in piccolo admin")
