import aiohttp


class API:
    @staticmethod
    async def get_product(token: str, uuid: str):
        header = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        url = f"https://api.upgrade.chat/v1/products/{uuid}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url, headers=header) as res:
                status = res.status
                results = await res.json()
                return status, results

    @staticmethod
    async def get_user_purchases(token: str, user_id: int):
        header = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        offset = 0
        purchases = []
        while True:
            url = f"https://api.upgrade.chat/v1/orders?offset={offset}&userDiscordId={user_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url=url, headers=header) as res:
                    status = res.status
                    results = await res.json()
                    if status != 200:
                        break
                    purchases.extend(results["data"])
                    if not results["has_more"]:
                        break
                    offset += 100
        return status, purchases
