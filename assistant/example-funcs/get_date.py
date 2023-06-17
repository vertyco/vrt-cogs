from datetime import datetime

import pytz


async def get_date(conf, *args, **kwargs) -> str:
    now = datetime.now().astimezone(pytz.timezone(conf.timezone))
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")


schema = {
    "name": "get_date",
    "description": "Get todays date (timezone aware)",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
