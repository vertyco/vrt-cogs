import argparse
import asyncio
import os
import webbrowser

from aiohttp import ClientSession, web

from xbox.webapi.api.client import XboxLiveClient
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse
from xbox.webapi.scripts import REDIRECT_URI, TOKENS_FILE


CLIENT_ID = "f67ee5e7-0cda-442e-8af6-fcf01a6fee61"
CLIENT_SECRET = "oZM7Q~.LTV4YVq.6~V7W-owDdizVUXu4.U~f."

