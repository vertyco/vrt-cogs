import aiohttp
import asyncio
import json
import xmltojson

cheader = {'Authorization': f'Bearer DTdDxAgF8UXY7RFegGOBPtwoy5qm0C82fv2SGz4sOOE2FXKFeZsyaD72OkBa-M4LWwnOnERl0OOZCJ71UmWIo0W7asdBABx6Mbb9'}
aheader = {'Authorization': f'Bearer 4-8mCSRvu5QTpNzYbBuf3NbR9qBFgqpMlngsGAnCFSUhwx42QZQBT4Dg_eMPoLn2ZK8g5peVoVg8kNzIJfSkI42N-k1oKtneJkCS'}

services = "https://api.nitrado.net/services"


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(services, headers=aheader) as service:
            service_data = await service.text()
            service_data = json.loads(service_data)
            print(service_data)
            service_id = service_data["data"]["services"][0]["id"]

            #GET
            info_req = f"https://api.nitrado.net/services/{service_id}:id/gameservers"
            listplayers = f"https://api.nitrado.net/services/{service_id}:id/gameservers/games/players"
            whitelist = f"https://api.nitrado.net/services/{service_id}:id/gameservers/games/whitelist"
            availablelists = f"https://api.nitrado.net/services/{service_id}:id/gameservers/games/players/lists"
            adminlist = f"https://api.nitrado.net/services/{service_id}:id/gameservers/games/adminlist"
            banlist = f"https://api.nitrado.net/services/{service_id}:id/gameservers/games/banlist"

            #POST
            restart = f"https://api.nitrado.net/services/{service_id}:id/gameservers/restart"
            stop = f"https://api.nitrado.net/services/{service_id}:id/gameservers/stop"
            command = f"https://api.nitrado.net/services/{service_id}:id/gameservers/app_server/command?command=userlist"


            async with session.post(command, headers=aheader) as info:
                info_data = await info.text()
                # info_data = json.loads(info_data)
                print(info_data)




loop = asyncio.get_event_loop()
loop.run_until_complete(main())
