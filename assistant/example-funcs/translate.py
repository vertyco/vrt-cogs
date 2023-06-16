from redbot.core.bot import Red


async def get_translation(bot: Red, message: str, to_language: str, *args, **kwargs) -> str:
    cog = bot.get_cog("Fluent")
    if not cog:
        return "Cog not loaded!"
    lang = await cog.converter(to_language)
    if not lang:
        return "Invalid target language"
    try:
        translation = await cog.translate(message, lang)
        return f"{translation.text}\n({translation.src} -> {lang})"
    except Exception as e:
        return f"Error: {e}"


func = {
    "name": "get_translation",
    "description": "Use this function to translate text",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "the text to translate"},
            "to_language": {
                "type": "string",
                "description": "the target language to translate to",
            },
        },
        "required": ["message", "to_language"],
    },
}
