# Adding Functions to the Assistant

Some GPT models are trained in a way that allows us to specify certain functions available to them, and enable them to call those functions at any time.

Only these two models can use function calls as of now:

- gpt-3.5-turbo-0613
- gpt-3.5-turbo-16k-0613
- gpt-4-0613
- gpt-4-32k-0613

This guide will help you understand how to integrate your cog with the Assistant.

## Prerequisites

- Familiarity with Python and Discord bot development
- Understanding of JSON schema (see [JSON Schema Reference](https://json-schema.org/understanding-json-schema/))
- Knowledge of OpenAI's function call feature (see [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling) and [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb))

## Function Registration

To register a function, use the `register_function` method. This method allows 3rd party cogs to register their functions for the model to use.

The method takes three arguments:

- `cog`: the cog registering its commands
- `schema`: JSON schema representation of the command
- `function`: either the raw code string or the actual callable function

The function returns `True` if the function was successfully registered.

## Function Unregistration

To unregister a function or a cog, use the `unregister_function` or `unregister_cog` methods respectively.

## Event Listeners

The Assistant cog uses event listeners to handle the addition and removal of cogs.

- `on_cog_add`: This event is triggered when a new cog is added. It schedules the custom listeners of the added cog.
- `on_cog_remove`: This event is triggered when a cog is removed. It unregisters the removed cog.

## Function Example

Here is an example of a function that gets a member's VC balance by name:

```python
import discord
from redbot.core import bank
async def get_member_balance(guild: discord.Guild, name: str, *args, **kwargs) -> str:
    user = guild.get_member_named(name)
    if not user:
        return "Could not find that user"
    bal = await bank.get_balance(user)
    return f"{bal} VC"
```

## JSON Schema Example

Here is an example of a JSON schema for the `get_member_balance` function (note how the `guild` object from the function above isnt included):

```json
{
  "name": "get_member_balance",
  "description": "Get a member's VC balance by name",
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

### The following objects are passed by default as keyword arguments and do not need to be included in the schema.

- **user**: the user currently chatting with the bot (discord.Member)
- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)
- **guild**: current guild (discord.Guild)
- **bot**: the bot object (Red)
- **conf**: the config model for Assistant (GuildSettings)

## 3rd Party Cog Support

3rd party cogs can register their own functions easily by using a custom listener. The Assistant cog will automatically unregister cogs when they are unloaded. If a cog tries to register a function whose name already exists, an error will be logged and the function will not register.

All functions **MUST** take `*args, **kwargs` as parameters. When importing functions as strings, make sure to include any imports. The function name in your schema must match the function name itself exactly.

### Tips:

- The string returned by the function is not seen by the user, it is read by GPT and summarrized by the model so it can be condensed or json, although natural language tends to give more favorable resutls.
- function description and parameter description matter for how accurately the functions are used.
- a good system/initial prompt also matters for how/when/why functions will be used.
- getting things to work how you want is an art, tinker with it as you go, make it as a custom function first before adding it to your cog's listener for easiser testing.
