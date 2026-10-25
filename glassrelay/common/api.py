import logging
import typing as t
from datetime import datetime

import aiohttp

log = logging.getLogger("red.vrt.glassrelay.api")

BASE_URL = "https://glassrelay.com/v1/"
PAGE_SIZE = 200  # the most GlassRelay returns per page


class APIError(Exception):
    """GlassRelay answered with an error status"""

    def __init__(self, status: int, retry_after: int = 0):
        super().__init__(f"GlassRelay returned status {status}")
        self.status = status
        self.retry_after = retry_after


class Client:
    """Calls to one store's GlassRelay API, made with that store's key"""

    def __init__(self, session: aiohttp.ClientSession, api_key: str):
        self.session = session
        self.headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with self.session.get(BASE_URL + path, headers=self.headers, params=params) as res:
            if res.status != 200:
                raise APIError(res.status, int(res.headers.get("Retry-After", 0)))
            return await res.json()

    async def get_storefront(self) -> dict:
        """The key's own store"""
        data = await self.get("storefronts/")
        if not data["results"]:
            raise APIError(404)
        return data["results"][0]

    async def check_customers_scope(self) -> None:
        """Raises APIError 403 if the key was made without the customers permission"""
        await self.get("customers/", {"limit": 1})

    async def iter_pages(self, path: str, params: dict | None = None) -> t.AsyncGenerator[dict, None]:
        """Every row of a list endpoint, one page at a time"""
        offset = 0
        while True:
            data = await self.get(path, {**(params or {}), "limit": PAGE_SIZE, "offset": offset})
            for row in data["results"]:
                yield row
            if not data["next"]:
                return
            offset += PAGE_SIZE

    def iter_products(self) -> t.AsyncGenerator[dict, None]:
        """Every product on the store, in the order the store shows them"""
        return self.iter_pages("products/")

    def iter_payments(self) -> t.AsyncGenerator[dict, None]:
        """Every payment on the store, newest first.

        Each row's `discord_uid` is the Discord account the buyer's login is linked to right now, null for a guest.
        """
        return self.iter_pages("payments/")

    def iter_buyer_payments(self, user_id: int) -> t.AsyncGenerator[dict, None]:
        """One Discord user's completed payments, newest first.

        GlassRelay finds them through the Discord account the buyer's login is linked to right now.
        """
        return self.iter_pages(f"customers/discord/{user_id}/payments/", {"status": "completed"})


def parse_time(value: str) -> int:
    """Unix seconds from a GlassRelay time, which is UTC ISO 8601 ending in Z"""
    # Python 3.10's fromisoformat can't read the Z
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
