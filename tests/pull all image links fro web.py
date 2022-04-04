import os
import urllib.request
import re
from bs4 import BeautifulSoup, SoupStrainer
import requests

url = "https://vertyco.imgur.com"
page = requests.get(url)
data = page.text
soup = BeautifulSoup(data, features="html.parser")
dinolist = []
for link in soup.find_all('a'):
    urls = link.get('href')
    print(urls)
#     if "/taming/" in urls:
#         regex = r'/taming/(.+)'
#         dinos = re.findall(regex, urls)
#         dinolist.append(dinos)
# for dino in dinolist:
#     print(dino[0])