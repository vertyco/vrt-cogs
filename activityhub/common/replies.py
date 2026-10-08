import functools
import html
import json
import logging
from string import Template

from aiohttp import web

log = logging.getLogger("red.vrt.activityhub.replies")

MAX_BODY = 1024 * 1024
NO_CACHE = {"Cache-Control": "no-cache"}
# NaN and Infinity aren't JSON: browsers can't read a reply that has them
STRICT_DUMPS = functools.partial(json.dumps, allow_nan=False)

BAD_REQUEST = "Bad request."
SESSION_EXPIRED = "Your session expired. Go back to the menu to log in again."
TURNED_OFF = "This activity is turned off in this server."
NOT_SET_UP = "The bot owner hasn't finished setting up Activities yet."
LOGIN_FAILED = "Discord login failed. Try opening the activity again."
INSTANCE_FAILED = "Discord couldn't confirm where this activity is running. Try opening it again."
NOT_IN_SERVER = "You're not a member of the server this activity is running in."
NO_SUCH_ACTION = "That action doesn't exist: {name}."
NOT_ALLOWED = "You can't change these settings."
SOMETHING_WRONG = "Something went wrong."
NOT_INSTALLED = "This activity isn't installed on this bot anymore."
PAGE_MISSING = "This page isn't part of the game."

# Shown inside the game frame, so the menu link is a button that calls the SDK's backToMenu instead of a link
NOTICE_PAGE = Template("""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Unavailable</title>
    <style>
      body {
        margin: 0;
        padding: 48px 16px;
        text-align: center;
        background: #2b2d31;
        color: #dbdee1;
        font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
      }
      button {
        color: #8ea1e1;
        background: none;
        border: 0;
        padding: 0;
        font: inherit;
        text-decoration: underline;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <p>$message</p>
    <p><button id="back" type="button">Back to the menu</button></p>
    <script type="module">
      import { backToMenu } from "activityhub";
      document.getElementById("back").addEventListener("click", backToMenu);
    </script>
  </body>
</html>
""")


def notice_page(message: str) -> str:
    """A page for the game frame that says why the game can't open, with a button back to the menu"""
    return NOTICE_PAGE.substitute(message=html.escape(message))


def error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def read_object(request: web.Request) -> dict | None:
    """The JSON body if it is an object, else None. A body over MAX_BODY raises aiohttp's own 413"""
    try:
        data = await request.json()
    except ValueError as e:
        log.debug("Ignored a request body that isn't JSON: %s", e)
        return None
    return data if isinstance(data, dict) else None
