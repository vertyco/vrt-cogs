import time

import requests


api_key = '8cgooossows0880s00kks48wcosw4c04ksk'
url = 'https://xbl.io/api/v2/friends/search?gt={}'
symbols = ['Itz0Alex', 'vertyco', 'vertyco1', 'vertyco2', 'vertyco3', 'vertyco4', 'vertyco pve']
results = []

start = time.time()
for symbol in symbols:
    print('Working on symbol {}'.format(symbol))
    response = requests.get(url.format(symbol, api_key))
    results.append(response.json())
end = time.time()
total_time = end - start
print("it took {} seconds to make {} API calls".format(total_time, len(symbols)))
print('you did it!')