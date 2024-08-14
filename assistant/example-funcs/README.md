# Adding Functions to the Assistant

Some GPT models are trained in a way that allows us to specify certain functions available to them, and enable them to call those functions at any time.

This guide will help you understand how to integrate your cog with the Assistant, or add custom functions to extend functinality.

## Prerequisites

- Familiarity with Python and Discord bot development
- Understanding of JSON schema (see [JSON Schema Reference](https://json-schema.org/understanding-json-schema/))
- Knowledge of OpenAI's function call feature (see [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling) and [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb))

# Function Registration

There are two ways the Assistant can use functions.

1. Custom Functions: The bot owner can create custom functions via the `[p]customfunc` menu
2. Registry Functions: Other 3rd party cogs can register their functions

The following objects are passed by default as keyword arguments and do not need to be included in the schema.

- **user**: the user currently chatting with the bot (discord.Member)
- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)
- **guild**: current guild (discord.Guild)
- **bot**: the bot object (Red)
- **conf**: the config model for Assistant (GuildSettings)

All functions **MUST** take `*args, **kwargs` as end parameters to handle excess objects being passed

## Custom Functions

Here is an example of a function that gets a member's credit balance by name:

```python
import discord
from redbot.core import bank
async def get_member_balance(guild: discord.Guild, name: str, *args, **kwargs) -> str:
    user = guild.get_member_named(name)
    if not user:
        return "Could not find that user"
    bal = await bank.get_balance(user)
    return f"{bal} credits"
```

Here is an example of a JSON schema for the `get_member_balance` function (note how the `guild` object from the function above isnt included):

```json
{
  "name": "get_member_balance",
  "description": "Get a member's credit balance by name",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "the name of the member"
      }
    },
    "required": ["name"]
  }
}
```

## 3rd Party Cog Support (Registry Functions)

3rd party cogs can register their own functions easily by using a custom listener. The Assistant cog will automatically unregister cogs when they are unloaded. If a cog tries to register a function whose name already exists, an error will be logged and the function will not register.

To register a function, use the `register_function` method. This method allows 3rd party cogs to register their functions for the model to use.

The method takes three arguments:

- `cog_name`: the name of the cog registering its commands
- `schema`: [JSON Schema](https://json-schema.org/understanding-json-schema/) representation of the command

The function returns `True` if it was successfully registered. Additionally, you can use `register_functions` and supply a list of schemas to register multiple functions at once

## Function Registration

```python
async def register_function(self, cog_name: str, schema: dict) -> bool:
    ...

async def register_functions(self, cog_name: str, schemas: List[dict]) -> None:
    # Register multiple functions at once
    ...
```

## Function Removal

To unregister a function or a cog, use the `unregister_function` or `unregister_cog` methods respectively.

```python
async def unregister_function(cog_name: str, function_name: str) -> None:
    ...

async def unregister_cog(cog_name: str) -> None:
    # This is automatically called when the cog is unloaded
    ...
```

## Event Listeners

The Assistant cog uses event listeners to handle the addition and removal of cogs.

- `on_cog_add`: This event is triggered when a new cog is added. It schedules the custom listeners of the added cog.
- `on_cog_remove`: This event is triggered when a cog is removed. It unregisters the removed cog.

### Example implementation

The exmaple below is how my Fluent cog registers its translate function

```python
@commands.Cog.listener()
async def on_assistant_cog_add(self, cog: commands.Cog):
    """Registers a command with Assistant enabling it to access translations"""
    schema = {
        "name": "get_translation",
        "description": "Translate text to another language",
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
    await cog.register_function(cog_name="Fluent", schema=schema)

async def get_translation(self, message: str, to_language: str, *args, **kwargs) -> str:
    lang = await self.converter(to_language)
    if not lang:
        return "Invalid target language"
    try:
        translation = await self.translate(message, lang)
        return f"{translation.text}\n({translation.src} -> {lang})"
    except Exception as e:
        return f"Error: {e}"
```

By adding this custom listener, the cog can detect when Assistant is loaded and register its function with it to allow OpenAI's LLM to call it when needed.

## Tips

- The function name in the schema needs to match the function name you wish to call in your cog exactly.
- The string returned by the function is not seen by the user, it is read by GPT and summarrized by the model so it can be condensed or json, although natural language tends to give more favorable results.
- function description and parameter description matter for how accurately the functions are used.
- a good system/initial prompt also matters for how/when/why functions will be used.
- getting things to work how you want is an art, tinker with it as you go, make it as a custom function first before adding it to your cog's listener for easiser testing.
