async def query_database(
    host: str,
    port: int,
    password: str,
    sql_query: str,
    database: str = "postgres",
    user: str = "postgres",
    *args,
    **kwargs,
) -> str:
    try:
        import asyncpg
    except ImportError:
        return "Error: asyncpg is not installed"
    try:
        conn = await asyncpg.connect(
            user=user,
            password=password,
            database=database,
            host=host,
            port=port,
        )
        result = await conn.fetch(sql_query)
        await conn.close()
        # Must return result as a string
        return str(result)
    except Exception as e:
        return f"Error: {e}"


schema = {
    "name": "query_database",
    "description": "Query a database for information",
    "parameters": {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "password": {"type": "string"},
            "sql_query": {"type": "string", "description": "The SQL query to run"},
            "user": {"type": "string", "description": "The user to connect as, defaults to 'postgres'"},
            "database": {"type": "string", "description": "The database to connect to, defaults to 'postgres'"},
        },
        "required": ["host", "port", "password", "sql_query"],
    },
}
