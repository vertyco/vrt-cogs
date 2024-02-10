async def search_internet(bot, query: str, num_results: int = 2, *args, **kwargs) -> str:
    """Search via you.com API https://documentation.you.com/quickstart"""
    from io import StringIO

    import aiohttp

    tokens = await bot.get_shared_api_tokens("you")
    if not tokens:
        return "No API key has been set!"
    api_key = tokens.get("key")
    if not api_key:
        return "Service exists but no API key has been set"
    base_url = "https://api.ydc-index.io/search"
    headers = {"X-API-KEY": api_key}
    params = {"query": query, "num_web_results": min(19, num_results), "safesearch": "off"}
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, headers=headers, params=params) as response:
            if response.status == 200:
                buffer = StringIO()
                data = await response.json()
                for hit in data["hits"]:
                    snippets = "\n".join(hit["snippets"])
                    buffer.write(f"# {hit['title']}\n- Source: {hit['url']}\n{snippets}\n\n")
                return buffer.getvalue()
            else:
                return f"Failed to search the internet with status {response.status}"


schema = {
    "name": "search_internet",
    "description": "Get search results from the internet",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return",
            },
        },
        "required": ["query"],
    },
}
