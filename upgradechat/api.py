import asyncio
import json.decoder
import logging
from datetime import datetime

import aiohttp

log = logging.getLogger("red.vrt.upgradechatapi")


class API:
    @staticmethod
    async def get_auth(client_id: str, client_secret: str):
        header = {"accept": "application/json"}
        url = "https://api.upgrade.chat/oauth/token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, headers=header, data=data) as res:
                status = res.status
                if status != 200:
                    return None
                results = await res.json()
                return results["access_token"]

    async def get_product(self, conf: dict, uuid: str) -> tuple:
        update_token = None
        token = conf["bearer_token"]
        cid = conf["id"]
        secret = conf["secret"]
        lr = conf["last_refreshed"]

        if token is None:
            token = await self.get_auth(cid, secret)
            update_token = token
        elif lr is None:
            token = await self.get_auth(cid, secret)
            update_token = token
        elif (datetime.now() - datetime.fromisoformat(lr)).total_seconds() > 3600:
            token = await self.get_auth(cid, secret)
            update_token = token

        tries = 0
        while tries < 3:
            tries += 1
            header = {"accept": "application/json", "Authorization": f"Bearer {token}"}
            url = f"https://api.upgrade.chat/v1/products/{uuid}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url=url, headers=header) as res:
                    status = res.status
                    if status == 401:
                        token = await self.get_auth(cid, secret)
                        if token:
                            update_token = token
                        continue
                    results = await res.json()
                    return status, results, update_token

        return 404, None, None

    async def get_user_purchases(self, conf: dict, user_id: int) -> tuple:
        update_token = None
        token = conf["bearer_token"]
        cid = conf["id"]
        secret = conf["secret"]
        offset = 0
        purchases = []
        tries = 0
        while True:
            if tries == 3:
                return 404, None, None
            if token is None:
                token = await self.get_auth(cid, secret)
                update_token = token
            header = {"accept": "application/json", "Authorization": f"Bearer {token}"}
            url = f"https://api.upgrade.chat/v1/orders?offset={offset}&userDiscordId={user_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url=url, headers=header, ssl=False) as res:
                    status = res.status
                    if status == 429:
                        try:
                            data = await res.json(content_type=None)
                            wait = data.get("Retry-After", 15)
                            log.warning(f"We are being rate-limited, waiting {wait} seconds...")
                        except json.decoder.JSONDecodeError:
                            wait = 15
                        await asyncio.sleep(wait)
                        tries += 1
                        continue
                    if status == 401:
                        token = await self.get_auth(cid, secret)
                        if token:
                            update_token = token
                        tries += 1
                        continue
                    if status == 404:
                        return 404, None, None
                    if status != 200:
                        log.error(f"Error calling API ({status}) - {res.text}")
                        await asyncio.sleep(5)
                        tries += 1
                        continue
                    results = await res.json()
                    purchases.extend(results["data"])
                    if not results["has_more"]:
                        break
                    offset += 100
        return status, purchases, update_token
