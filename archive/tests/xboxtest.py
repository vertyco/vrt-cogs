import aiohttp
import asyncio
async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://xbl.io/api/v2/friends/search?gt=Itz0Alex', headers={"X-Authorization":"8cgooossows0880s00kks48wcosw4c04ksk"}) as response:
            print("Status:", response.status)
            print("Content-type:", response.headers['content-type'])
            print(await response.json())
            data = await response.json()
            for user in data["profileUsers"]:
                print(f"XUID: {user['id']}")
                for setting in user["settings"]:
                    if setting["id"] == "Gamerscore":
                        print(f"Gamerscore: {setting['value']}")
                    if setting["id"] == "Gamertag":
                        print(f"Gamertag: {setting['value']}")
                    if setting["id"] == "AccountTier":
                        print(f"AccountTier: {setting['value']}")
                    if setting["id"] == "XboxOneRep":
                        print(f"XboxOneRep: {setting['value']}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())