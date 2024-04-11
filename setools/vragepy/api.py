import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from urllib.parse import urlencode

import aiohttp

from . import responses

log = logging.getLogger("vragepy")


class VRageClient:
    def __init__(self, base_url: str, token: str, timeout: int = 10) -> None:
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        self.status_code = None

    def _build_headers(self, endpoint: str) -> None:
        """
        Prepares the headers required to query the Space Engineers VRage API.

        Source: https://www.spaceengineersgame.com/dedicated-servers/
        """
        nonce = uuid.uuid4().hex + uuid.uuid1().hex
        date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S")
        pre_hash_str = f"""{endpoint}\r\n{nonce}\r\n{date}\r\n"""
        hmac_obj = hmac.new(base64.b64decode(self.token), pre_hash_str.encode("utf-8"), hashlib.sha1)
        hmac_encoded = base64.b64encode(hmac_obj.digest()).decode()
        self.headers.update({"Date": date, "Authorization": f"{nonce}:{hmac_encoded}"})

    async def _request(self, method: str, endpoint: str, data: str | None = None) -> dict:
        """Make a request to the VRage API."""
        self._build_headers(endpoint=endpoint)
        url = self.base_url + endpoint
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
            async with session.request(method, url, json=data) as response:
                log.debug(f"{method} ({response.status}): {url}")
                self.status_code = response.status
                response.raise_for_status()
                return await response.json()

    async def get_endpoints(self, raw: bool = False) -> responses.EndpointsResponse | dict:
        """Fetch all available endpoints."""
        resp = await self._request("GET", "/vrageremote/api")
        if raw:
            return resp
        return responses.EndpointsResponse.model_validate(resp)

    async def get_server_info(self, raw: bool = False) -> responses.ServerResponse | dict:
        """Gets server information and health status."""
        resp = await self._request("GET", "/vrageremote/v1/server")
        if raw:
            return resp
        return responses.ServerResponse.model_validate(resp)

    async def get_server_ping(self, raw: bool = False) -> responses.PingResponse | dict:
        """Get server ping"""
        resp = await self._request("GET", "/vrageremote/v1/server/ping")
        if raw:
            return resp
        return responses.PingResponse.model_validate(resp)

    async def get_players(self, raw: bool = False) -> responses.PlayersResponse | dict:
        """Gets currently connected players."""
        resp = await self._request("GET", "/vrageremote/v1/session/players")
        if raw:
            return resp
        return responses.PlayersResponse.model_validate(resp)

    async def get_cheaters(self, raw: bool = False) -> responses.CheatersResponse | dict:
        """Gets list of cheating players records on the server."""
        resp = await self._request("GET", "/vrageremote/v1/admin/cheaters")
        if raw:
            return resp
        return responses.CheatersResponse.model_validate(resp)

    async def ban_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Ban player."""
        resp = await self._request("POST", f"/vrageremote/v1/admin/bannedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def unban_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Unban player."""
        resp = await self._request("DELETE", f"/vrageremote/v1/admin/bannedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def get_banned_players(self, raw: bool = False) -> responses.BannedPlayersResponse | dict:
        """Gets all banned players on the server."""
        resp = await self._request("GET", "/vrageremote/v1/admin/bannedPlayers")
        if raw:
            return resp
        return responses.BannedPlayersResponse.model_validate(resp)

    async def kick_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Removes player from kick list."""
        resp = await self._request("POST", f"/vrageremote/v1/admin/kickedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def unkick_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Unkicks player from the server."""
        resp = await self._request("DELETE", f"/vrageremote/v1/admin/kickedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def get_kicked_players(self, raw: bool = False) -> responses.KickedPlayersResponse | dict:
        """Gets kicked players on the server."""
        resp = await self._request("GET", "/vrageremote/v1/admin/kickedPlayers")
        if raw:
            return resp
        return responses.KickedPlayersResponse.model_validate(resp)

    async def promote_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Promote player."""
        resp = await self._request("POST", f"/vrageremote/v1/admin/promotedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def demote_player(self, steam_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Demote player."""
        resp = await self._request("DELETE", f"/vrageremote/v1/admin/promotedPlayers/{steam_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def get_characters(self, raw: bool = False) -> responses.CharactersResponse | dict:
        """Get characters of players currently on the server."""
        resp = await self._request("GET", "/vrageremote/v1/session/characters")
        return responses.CharactersResponse.model_validate(resp)

    async def stop_character(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Stops the character movement."""
        resp = await self._request("PATCH", f"/vrageremote/v1/session/characters/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def get_asteroids(self, raw: bool = False) -> responses.AsteroidsResponse | dict:
        """Gets all existing asteroids in the world."""
        resp = await self._request("GET", "/vrageremote/v1/session/asteroids")
        if raw:
            return resp
        return responses.AsteroidsResponse.model_validate(resp)

    async def get_floating_objects(self, raw: bool = False) -> responses.FloatingObjectsResponse | dict:
        """Gets all floating objects in the world."""
        resp = await self._request("GET", "/vrageremote/v1/session/floatingObjects")
        if raw:
            return resp
        return responses.FloatingObjectsResponse.model_validate(resp)

    async def get_grids(self, raw: bool = False) -> responses.GridsResponse | dict:
        """Gets all grids in the world."""
        resp = await self._request("GET", "/vrageremote/v1/session/grids")
        if raw:
            return resp
        return responses.GridsResponse.model_validate(resp)

    async def get_planets(self, raw: bool = False) -> responses.PlanetsResponse | dict:
        """Gets all planets in the world."""
        resp = await self._request("GET", "/vrageremote/v1/session/planets")
        if raw:
            return resp
        return responses.PlanetsResponse.model_validate(resp)

    async def get_chat(
        self, message_count: int | None = None, date: str | None = None, raw: bool = False
    ) -> responses.MessagesResponse | dict:
        """
        Gets global chat messages. You can specify MessageCount and Date in query string.

        The date is some weird timestamp-like integer, no clue what it is.
        Date example: '638457071427146845'
        """
        params = {}
        if message_count:
            params["MessageCount"] = message_count
        if date:
            params["Date"] = date
        url = "/vrageremote/v1/session/chat"
        if params:
            url = f"/vrageremote/v1/session/chat?{urlencode(params)}"
        resp = await self._request("GET", url)
        if raw:
            return resp
        return responses.MessagesResponse.model_validate(resp)

    async def send_chat(self, message: str, raw: bool = False) -> responses.GenericResponse | dict:
        """Send message to global chat."""
        resp = await self._request("POST", "/vrageremote/v1/session/chat", data=message)
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def delete_asteroid(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Deletes existing asteroid."""
        resp = await self._request("DELETE", f"/vrageremote/v1/session/asteroids/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def delete_floating_object(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Deletes floating object."""
        resp = await self._request("DELETE", f"/vrageremote/v1/session/floatingObjects/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def delete_grid(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Deletes grid."""
        resp = await self._request("DELETE", f"/vrageremote/v1/session/grids/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def delete_planet(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Deletes planet."""
        resp = await self._request("DELETE", f"/vrageremote/v1/session/planets/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def stop_grid(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Stops grids movement."""
        resp = await self._request("PATCH", f"/vrageremote/v1/session/grids/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def stop_floating_object(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Stops floating objects movement."""
        resp = await self._request("PATCH", f"/vrageremote/v1/session/floatingObjects/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def power_down_powered_grid(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Turns off power on the grid."""
        resp = await self._request("DELETE", f"/vrageremote/v1/session/poweredGrids/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def power_up_powered_grid(self, entity_id: int, raw: bool = False) -> responses.GenericResponse | dict:
        """Turns on power on the grid."""
        resp = await self._request("POST", f"/vrageremote/v1/session/poweredGrids/{entity_id}")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def save_server(self, raw: bool = False) -> responses.GenericResponse | dict:
        """Saves the server."""
        resp = await self._request("PATCH", "/vrageremote/v1/session")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def stop_server(self, raw: bool = False) -> responses.GenericResponse | dict:
        """Stops the server."""
        resp = await self._request("DELETE", "/vrageremote/v1/server")
        if raw:
            return resp
        return responses.GenericResponse.model_validate(resp)

    async def get_economy_summary(self, raw: bool = False) -> responses.EconomyResponse | dict:
        """Gets summary of state and changes in economy (currency) during last period"""
        resp = await self._request("GET", "/vrageremote/v1/session/economyAnalysis")
        if raw:
            return resp
        return responses.EconomyResponse.model_validate(resp)
