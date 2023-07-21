# Check weather
import json

import aiohttp
from redbot.core.bot import Red


async def get_weather(
    bot: Red, location: str, temp_scale: str = "imperial", *args, **kwargs
) -> str:
    tokens = await bot.get_shared_api_tokens("openweathermap")
    if not tokens:
        return "No API key has been set!"
    api_key = tokens.get("key")
    if not api_key:
        return "Service exists but no API key has been set"
    base_url = "http://api.openweathermap.org/geo/1.0/direct"
    weather_url = "http://api.openweathermap.org/data/2.5/weather"

    location_url = f"{base_url}?q={location}&limit=1&appid={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(location_url) as response:
            if response.status == 200:
                location_data = await response.json()
                if location_data:
                    lat = location_data[0]["lat"]
                    lon = location_data[0]["lon"]
                else:
                    return "Location Not Found, the location parameter needs city name,state code,country code separated by a comma!"
            else:
                return "Failed to fetch location coords"

    # Get the weather using the coordinates
    complete_url = f"{weather_url}?lat={lat}&lon={lon}&units={temp_scale}&appid={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(complete_url) as response:
            if response.status == 200:
                weather_data = await response.json()
                return json.dumps(weather_data)
            else:
                return "Failed to get weather"


schema = {
    "name": "get_weather",
    "description": "Use this function to fetch the weather for a location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "city name,state code,country code separated by a comma",
            },
            "temp_scale": {
                "type": "string",
                "enum": ["imperial", "metric"],
                "description": "imperial for Farenheit, metric for Celcius",
            },
        },
        "required": ["location"],
    },
}
