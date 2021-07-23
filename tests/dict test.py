


test = {"clusters": {"pvp": {"joinchannel": 739270285450018927, "leavechannel": 851819367439400960, "adminlogchannel": 848933429164507156, "globalchatchannel": 841118994399494164, "servers": {"rag": {"ip": "192.168.1.201", "port": 27020, "password": "ferox", "chatchannel": 770891102601084928}, "val": {"ip": "192.168.1.203", "port": 27024, "password": "ferox", "chatchannel": 770891102601084928}, "island": {"ip": "192.168.1.205", "port": 27021, "password": "ferox", "chatchannel": 770891102601084928}}}, "pve": {"joinchannel": 739270285450018927, "leavechannel": 851819367439400960, "adminlogchannel": 848933429164507156, "globalchatchannel": 841118994399494164, "servers": {"rag": {"ip": "192.168.1.202", "port": 27022, "password": "ferox", "chatchannel": 770891102601084928}, "val": {"ip": "192.168.1.204", "port": 27023, "password": "ferox", "chatchannel": 770891102601084928}, "island": {"ip": "192.168.1.206", "port": 27025, "password": "ferox", "chatchannel": 770891102601084928}}}}, "modcommands": ["listplayers"], "modroles": [780468596236222483], "fullaccessrole": 780468596236222483}

#Method 1 - One at a time
for pv in test["clusters"]:
    print(f'\n{pv.upper()} Cluster\n')
    for server in test["clusters"][pv]["servers"]:
        print(f'map: {server}')
        for k, v in test["clusters"][pv]["servers"][server].items():
            print(f'{k}: {v}')
        print()

#Method 1.2 - all at once
serversettings = ""
for pv in test["clusters"]:
   serversettings += f"**{pv.upper()} Cluster**\n"
   for server in test["clusters"][pv]["servers"]:
      serversettings += f"**map:** `{server}`\n"
      for k, v in test["clusters"][pv]["servers"][server].items():
         if k != "chatchannel":
            serversettings += f"**{k}:** `{v}`\n"
         else:
            serversettings += f"**{k}:** <#{v}>\n"
      serversettings += "\n"
print(serversettings)

#Method 2 - all at once
print_all = []
for pv in test["clusters"]:
    print_all.append(f'\n{pv.upper()} Cluster\n')
    for server in test["clusters"][pv]["servers"]:
        print_all.append(f'map: {server}')
        for k, v in test["clusters"][pv]["servers"][server].items():
            print_all.append(f'{k}: {v}')
        print_all.append('')
print_all = '\n'.join(print_all) # a single string
print(print_all)