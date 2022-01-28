import json
import aiohttp


class Calls:
    """XSAPI endpoints that xbox-webapi doesn't have"""
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.headers = {
            'x-xbl-contract-version': '2',
            'Authorization': '',
            'Accept-Language': 'en-US',
        }

    async def add_friend(self, xuid: str, token: str) -> int:
        url = f"https://social.xboxlive.com/users/me/people/xuid({xuid})"
        self.headers["Authorization"] = token
        async with self.session.put(url=url, headers=self.headers) as res:
            return res.status

    async def remove_friend(self, xuid: str, token: str) -> int:
        url = f"https://social.xboxlive.com/users/me/people/xuid({xuid})"
        self.headers["Authorization"] = token
        async with self.session.delete(url=url, headers=self.headers) as res:
            return res.status

    async def block_player(self, xuid: int, token: str) -> int:
        url = f"https://privacy.xboxlive.com/users/me/people/never"
        self.headers["Authorization"] = token
        payload = {"xuid": xuid}
        payload = json.dumps(payload)
        async with self.session.put(url=url, headers=self.headers, data=payload) as res:
            return res.status

    async def unblock_player(self, xuid: int, token: str) -> int:
        url = f"https://privacy.xboxlive.com/users/me/people/never"
        self.headers["Authorization"] = token
        payload = {"xuid": xuid}
        payload = json.dumps(payload)
        async with self.session.delete(url=url, headers=self.headers, data=payload) as res:
            return res.status

    async def get_followers_own(self, token: str) -> dict:
        url = "https://peoplehub.xboxlive.com/users/me/people/followers/decoration/details"
        self.headers["Authorization"] = token
        async with self.session.get(url=url, headers=self.headers) as res:
            return await res.json()
