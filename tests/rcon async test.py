import rcon
import asyncio

# serverlist = [{'name': 'rag', 'ip': '192.168.1.201', 'port': 27020, 'password': 'ferox', 'chatchannel': 770891102601084928}, {'name': 'val', 'ip': '192.168.1.203', 'port': 27024, 'password': 'ferox', 'chatchannel': 770891102601084928}, {'name': 'island', 'ip': '192.168.1.205', 'port': 27021, 'password': 'ferox', 'chatchannel': 770891102601084928}, {'name': 'rag', 'ip': '192.168.1.202', 'port': 27022, 'password': 'ferox', 'chatchannel': 770891102601084928}, {'name': 'val', 'ip': '192.168.1.204', 'port': 27023, 'password': 'ferox', 'chatchannel': 770891102601084928}, {'name': 'island', 'ip': '192.168.1.206', 'port': 27025, 'password': 'ferox', 'chatchannel': 770891102601084928}]
#
# async def main():
#     for server in serverlist:
#
#         res = await rcon.asyncio.rcon(
#             command="listplayers",
#             host=server['ip'],
#             port=server['port'],
#             passwd=server['password']
#         )
#         print(server['name'])
#         print(res)
#
# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# asyncio.run(main())




async def factorial(name, number):
    f = 1
    for i in range(2, number + 1):
        print(f"Task {name}: Compute factorial({number}), currently i={i}...")
        await asyncio.sleep(1)
        f *= i
    print(f"Task {name}: factorial({number}) = {f}")
    return f

async def main():
    # Schedule three calls *concurrently*:
    L = await asyncio.gather(
        factorial("A", 2),
        factorial("B", 3),
        factorial("C", 4),
    )
    print(L)

asyncio.run(main())

# Expected output:
#
#     Task A: Compute factorial(2), currently i=2...
#     Task B: Compute factorial(3), currently i=2...
#     Task C: Compute factorial(4), currently i=2...
#     Task A: factorial(2) = 2
#     Task B: Compute factorial(3), currently i=3...
#     Task C: Compute factorial(4), currently i=3...
#     Task B: factorial(3) = 6
#     Task C: Compute factorial(4), currently i=4...
#     Task C: factorial(4) = 24
#     [2, 6, 24]



