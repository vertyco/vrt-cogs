from pyq3serverlist import PrincipalServer, Server
from pyq3serverlist.exceptions import PyQ3SLError, PyQ3SLTimeoutError

principal = PrincipalServer('34.116.104.140', 29070)

try:
    servers = principal.get_servers()
    print(servers)
except (PyQ3SLError, PyQ3SLTimeoutError) as e:
    print(e)


server = Server('34.116.104.140', 29070)
try:
    info = server.get_status()
    print(info)
except (PyQ3SLError, PyQ3SLTimeoutError) as e:
    print(e)