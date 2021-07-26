from rcon import Client
import rcon
import asyncio


settings = {"clusters": {
          "pvp": {
            "joinchannel": 739270285450018927,
            "leavechannel": 851819367439400960,
            "adminlogchannel": 848933429164507156,
            "globalchatchannel": 841118994399494164,
            "servers": {
              "rag": {
                "ip": "192.168.1.201",
                "port": 27020,
                "password": "ferox",
                "chatchannel": 770891102601084928
              },
              "val": {
                "ip": "192.168.1.203",
                "port": 27024,
                "password": "ferox",
                "chatchannel": 770891102601084928
              },
              "island": {
                "ip": "192.168.1.205",
                "port": 27021,
                "password": "ferox",
                "chatchannel": 770891102601084928
              }
            }
          },
          "pve": {
            "joinchannel": 739270285450018927,
            "leavechannel": 851819367439400960,
            "adminlogchannel": 848933429164507156,
            "globalchatchannel": 841118994399494164,
            "servers": {
              "rag": {
                "ip": "192.168.1.202",
                "port": 27022,
                "password": "ferox",
                "chatchannel": 770891102601084928
              },
              "val": {
                "ip": "192.168.1.204",
                "port": 27023,
                "password": "ferox",
                "chatchannel": 770891102601084928
              },
              "island": {
                "ip": "192.168.1.206",
                "port": 27025,
                "password": "ferox",
                "chatchannel": 770891102601084928
              }
            }
          }
        },
        "fullaccessrole": 780468596236222483,
        "modroles": [
          748058661951242310
        ]
      }






# async def main():
#     command = "listplayers"
#     for cluster in settings["clusters"]:
#         for server in settings["clusters"][cluster]["servers"]:
#             for k, v in settings["clusters"][cluster]["servers"][server].items():
#                 if k == "ip":
#                     ip = str(v)
#                 if k == "port":
#                     prt = int(v)
#                 if k == "password":
#                     pw = str(v)
#                     res = await rcon.asyncio.rcon(
#                         command=command,
#                         host=ip,
#                         port=prt,
#                         passwd=pw
#                     )
#                     print(res)
#
# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# asyncio.run(main())







# async def main():
#
#     cmd = await rcon.asyncio.rcon(
#         command='listplayers',
#         host='192.168.1.202',
#         port=27022,
#         passwd='ferox'
#     )
#     print(cmd)
# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# asyncio.run(main())





