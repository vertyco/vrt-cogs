import asyncio
import logging
import shutil
import socket
import threading
from pathlib import Path

from aiohttp import web
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from activityhub.common.server import HUB_WEB_DIR, HubServer
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID

log = logging.getLogger("red.vrt.activityhub.tests.browser")

# The address Discord gives an Activity, minus the parts the hub doesn't read
DISCORD_QUERY = f"?frame_id=f&instance_id=i-1&guild_id={GUILD_ID}&channel_id=77&platform=desktop"

# Stands in for Discord's toolkit: every call answers at once, and window.fakeDiscord counts them.
# Its state is private, like a real class's, so a method called on anything but the toolkit itself throws.
# With &silent=1 in the address, ready() waits until the test calls window.answerDiscord(), like a page
# opened outside Discord. window.fakeDiscordBus plays Discord's events to the subscribed listeners.
FAKE_SDK = """export class DiscordSDK {
  #listeners = new Map();
  #answered = new URLSearchParams(location.search).has("silent")
    ? new Promise((resolve) => { window.answerDiscord = resolve; })
    : Promise.resolve();

  constructor(clientId) {
    const calls = (window.fakeDiscord = window.fakeDiscord || { created: 0, authorize: 0, authenticate: 0 });
    calls.created += 1;
    window.fakeDiscordBus = {
      emit: (event, data) => (this.#listeners.get(event) || []).forEach((listener) => listener(data)),
      count: (event) => (this.#listeners.get(event) || []).length,
    };
    this.clientId = clientId;
    this.instanceId = new URLSearchParams(location.search).get("instance_id");
    this.commands = {
      authorize: async () => {
        // Real Discord refuses a second authorize in the same frame; tests switch this on to match
        if (calls.failAuthorize) {
          throw new Error("Already authenticated");
        }
        calls.authorize += 1;
        return { code: `code-${calls.authorize}` };
      },
      authenticate: async ({ access_token }) => {
        calls.authenticate += 1;
        return { access_token };
      },
      getInstanceConnectedParticipants: async () => ({ participants: [] }),
    };
  }

  async ready() {
    await this.#answered;
  }

  async subscribe(event, listener) {
    this.#listeners.set(event, [...(this.#listeners.get(event) || []), listener]);
  }

  async unsubscribe(event, listener) {
    this.#listeners.set(event, (this.#listeners.get(event) || []).filter((known) => known !== listener));
  }
}
"""

# A bare page that runs host.js, for testing the login and the game frame without the menu
TEST_HOST_PAGE = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Test host</title></head>
  <body>
    <script type="module">
      import { startHost } from "./host.js";
      const host = startHost({
        onGameClosed: () => { document.body.dataset.closed = "1"; },
        onSessionExpired: () => { document.body.dataset.expired = "1"; },
      });
      window.testHost = host;
      host.ready.then(
        (login) => { document.body.dataset.login = login ? "online" : "offline"; },
        (e) => { document.body.dataset.login = `failed: ${e.message}`; },
      );
    </script>
  </body>
</html>
"""


def hub_web_copy(tmp_path: Path, index: str | None = None) -> Path:
    """The hub's real web files with the fake Discord toolkit, and optionally a different index.html"""
    target = tmp_path / "hubweb-live"
    shutil.copytree(HUB_WEB_DIR, target)
    (target / "vendor" / "discord-sdk.js").write_text(FAKE_SDK, encoding="utf-8")
    if index is not None:
        (target / "index.html").write_text(index, encoding="utf-8")
    return target


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_chrome():
    """Headless Chrome, or None when it can't start on this machine"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,800")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as e:
        log.warning("Chrome couldn't start, skipping browser tests: %s", e.msg)
        return None


def fresh(driver, live: "LiveHub") -> None:
    """Start each test on a blank page of the test server, with nothing left in the console from the last one"""
    driver.get(f"{live.url}/hub/api/ping")
    console_lines(driver)


def console_lines(driver) -> list[str]:
    """The warnings and errors every frame wrote to the browser console since the last call"""
    return [entry["message"] for entry in driver.get_log("browser")]


def wait_for_console(driver, text: str, timeout: float = 10) -> list[str]:
    """Wait until a console warning or error holds the text, and return every line seen"""
    seen = []

    def found(d) -> bool:
        seen.extend(console_lines(d))
        return any(text in line for line in seen)

    WebDriverWait(driver, timeout).until(found)
    return seen


def wait_for(driver, script: str, timeout: float = 10):
    """Wait until the JavaScript expression is truthy, and return its value"""
    return WebDriverWait(driver, timeout).until(lambda d: d.execute_script(f"return {script}"))


class LiveHub:
    """The hub's web server on a background thread, so the browser can load it while the test drives it"""

    def __init__(self, hub, web_dir: Path):
        self.hub = hub
        self.server = HubServer(hub, web_dir=web_dir)
        self.server.exchange_code = self.exchange_code
        self.server.locate = self.locate
        self.user_id = MEMBER_ID
        self.location = {"guild_id": GUILD_ID, "channel_id": 77}
        self.port = free_port()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.runner: web.AppRunner | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def exchange_code(self, code: str):
        return "access-token", self.user_id

    async def locate(self, instance_id: str):
        return {**self.location, "users": [str(self.user_id)]}

    async def serve(self) -> None:
        self.runner = web.AppRunner(self.server.make_app())
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", self.port).start()

    def start(self) -> None:
        self.thread.start()
        asyncio.run_coroutine_threadsafe(self.serve(), self.loop).result(10)

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(15)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
