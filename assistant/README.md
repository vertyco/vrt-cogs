# Assistant Help

Set up and configure an AI assistant (or chat) cog for your server with one of OpenAI's ChatGPT language models.<br/><br/>Features include configurable prompt injection, dynamic embeddings, custom function calling, and more!<br/><br/>- **[p]assistant**: base command for setting up the assistant<br/>- **[p]chat**: talk with the assistant<br/>- **[p]convostats**: view a user's token usage/conversation message count for the channel<br/>- **[p]clearconvo**: reset your conversation with the assistant in the channel<br/><br/>**Support for Local Models**<br/><br/>**Default QA/Tokenizing Model**: `deepset/roberta-large-squad2`<br/>- Download size: 1.42GB<br/>- RAM usage: around 1.64-2.0 GB<br/>**Default Embedding Model**: `all-MiniLM-L12-v2`.<br/>- Download size: 120 MB<br/>- RAM usage: 650-750 MB<br/><br/>_The local model can only be used as Q&A, it doesn't support any message retention or memory_

# chat

- Usage: `[p]chat <question> `
- Aliases: `ask`
- Cooldown: `1 per 6.0 seconds`
- Checks: `server_only`

Chat with [botname]!<br/><br/>Conversations are _Per_ user _Per_ channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/><br/>**Optional Arguments**<br/>`--outputfile <filename>` - uploads a file with the reply instead (no spaces)<br/>`--extract` - extracts code blocks from the reply<br/><br/>**Example**<br/>`[p]chat write a python script that prints "Hello World!"`<br/>- Including `--outputfile hello.py` will output a file containing the whole response.<br/>- Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.<br/>- Including `--extract` will send the code separately from the reply

# convostats

- Usage: `[p]convostats [user] `
- Checks: `server_only`

Check the token and message count of yourself or another user's conversation for this channel<br/><br/>Conversations are _Per_ user _Per_ channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/><br/>Conversations are only stored in memory until the bot restarts or the cog reloads

# clearconvo

- Usage: `[p]clearconvo `
- Checks: `server_only`

Reset your conversation with the bot<br/><br/>This will clear all message history between you and the bot for this channel

# query

- Usage: `[p]query <query> `

Fetch related embeddings according to the current settings along with their scores<br/><br/>You can use this to fine-tune the minimum relatedness for your assistant

# assistant

- Usage: `[p]assistant `
- Restricted to: `ADMIN`
- Aliases: `assist`
- Checks: `server_only`

Setup the assistant<br/><br/>You will need an **[api key](https://platform.openai.com/account/api-keys)** from OpenAI to use ChatGPT and their other models.<br/><br/>This cog comes with a pre-trained **[self-hosted model](https://huggingface.co/deepset/roberta-base-squad2)** (Q&A Only)

## assistant openaikey

- Usage: `[p]assistant openaikey `
- Aliases: `key`

Set your OpenAI key

## assistant localembedder

- Usage: `[p]assistant localembedder `
- Aliases: `localembed and le`

Toggle whether the local model should be used for creating embeddings<br/><br/>**Resources**<br/>- [About Semantic Search](https://huggingface.co/spaces/sentence-transformers/embeddings-semantic-search)<br/>- [OpenAI Embedding Intro](https://platform.openai.com/docs/guides/embeddings/what-are-embeddings)

## assistant importcsv

- Usage: `[p]assistant importcsv <overwrite> `

Import embeddings to use with the assistant<br/><br/>Args:<br/> overwrite (bool): overwrite embeddings with existing entry names<br/><br/>This will read excel files too

## assistant system

- Usage: `[p]assistant system [system_prompt] `
- Aliases: `sys`

Set the system prompt for GPT to use<br/><br/>**Placeholders**<br/>- **botname**: [botname]<br/>- **timestamp**: discord timestamp<br/>- **day**: Mon-Sun<br/>- **date**: MM-DD-YYYY<br/>- **time**: HH:MM AM/PM<br/>- **timetz**: HH:MM AM/PM Timezone<br/>- **members**: server member count<br/>- **username**: user's name<br/>- **displayname**: user's display name<br/>- **roles**: the names of the user's roles<br/>- **rolementions**: the mentions of the user's roles<br/>- **avatar**: the user's avatar url<br/>- **owner**: the owner of the server<br/>- **servercreated**: the create date/time of the server<br/>- **server**: the name of the server<br/>- **py**: python version<br/>- **dpy**: discord.py version<br/>- **red**: red version<br/>- **cogs**: list of currently loaded cogs<br/>- **channelname**: name of the channel the conversation is taking place in<br/>- **channelmention**: current channel mention<br/>- **topic**: topic of current channel (if not forum or thread)<br/>- **banktype**: whether the bank is global or not<br/>- **currency**: currency name<br/>- **bank**: bank name<br/>- **balance**: the user's current balance

## assistant topn

- Usage: `[p]assistant topn <top_n> `

Set the embedding inclusion amout<br/><br/>Top N is the amount of embeddings to include with the initial prompt

## assistant regexblacklist

- Usage: `[p]assistant regexblacklist <regex> `

Remove certain words/phrases in the bot's responses

## assistant channel

- Usage: `[p]assistant channel <channel> `

Set the channel for the assistant

## assistant selfhosted

- Usage: `[p]assistant selfhosted `
- Restricted to: `BOT_OWNER`

Toggle the self hosted model

## assistant resetglobalconversations

- Usage: `[p]assistant resetglobalconversations <yes_or_no> `
- Restricted to: `BOT_OWNER`

Wipe saved conversations for the assistant in all servers<br/><br/>This will delete any and all saved conversations for the assistant.

## assistant blacklist

- Usage: `[p]assistant blacklist <channel_role_member> `

Add/Remove items from the blacklist<br/><br/>`channel_role_member` can be a member, role, channel, or category channel

## assistant temperature

- Usage: `[p]assistant temperature <temperature> `

Set the temperature for the model (0.0 - 1.0)<br/><br/>Closer to 0 is more concise and accurate while closer to 1 is more imaginative

## assistant resetconversations

- Usage: `[p]assistant resetconversations <yes_or_no> `

Wipe saved conversations for the assistant in this server<br/><br/>This will delete any and all saved conversations for the assistant.

## assistant timezone

- Usage: `[p]assistant timezone <timezone> `

Set the timezone used for prompt placeholders

## assistant maxtokens

- Usage: `[p]assistant maxtokens <max_tokens> `

Set the max tokens the model can use at once<br/><br/>**Tips**<br/>- Max tokens are a soft cap, sometimes messages can be a little over<br/>- If you set max tokens too high the cog will auto-adjust to 100 less than the models natural cap<br/>- Ideally set max to 500 less than that models maximum, to allow adequate responses<br/><br/>Using more than the model can handle will raise exceptions.

## assistant relatedness

- Usage: `[p]assistant relatedness <mimimum_relatedness> `

Set the minimum relatedness an embedding must be to include with the prompt<br/><br/>Relatedness threshold between 0 and 1 to include in embeddings during chat<br/><br/>Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison<br/><br/>**Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be _too_ strict or there wont be any results.

## assistant maxretention

- Usage: `[p]assistant maxretention <max_retention> `

Set the max messages for a conversation<br/><br/>Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to disable conversation retention<br/><br/>**Note:** _actual message count may exceed the max retention during an API call_

## assistant localmodel

- Usage: `[p]assistant localmodel `
- Aliases: `lm`

Toggle whether the local model should be used for responses<br/><br/>**Note**<br/>- This can only be used if the bot owner has enabled it<br/>- This model will NOT work without embedding data, and functions very differently from OpenAI's model<br/>- This model is lightweight and therefor much less accurate than OpenAI's models<br/><br/>**Tips**<br/>- Using the local model with OpenAI embeddings may give pretty decent results<br/>- The quality of your embedding data will be key for getting desirable responses<br/>- The relatedness and scoring of embeddings are much different than OpenAI settings so you'll want to play with it

## assistant refreshembeds

- Usage: `[p]assistant refreshembeds `
- Aliases: `refreshembeddings`

Refresh embedding weights<br/><br/>_This command is only for switching between OpenAI embeddings and the local model_<br/><br/>Embeddings that were created using OpenAI cannot be used with the local model and vice versa

## assistant embedmethod

- Usage: `[p]assistant embedmethod `

Cycle between embedding methods<br/><br/>**Dynamic** embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.<br/>When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly<br/><br/>**Static** embeddings are applied in front of each user message and get stored with the conversation instead of being replaced with each question.<br/><br/>**Hybrid** embeddings are a combination, with the first embedding being stored in the conversation and the rest being dynamic, this saves a bit on token usage<br/><br/>Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings. The hybrid method is a good middle ground

## assistant functioncalls

- Usage: `[p]assistant functioncalls `

Toggle whether GPT can call functions<br/><br/>Only the following models can call functions at the moment<br/>- gpt-3.5-turbo-0613<br/>- gpt-3.5-turbo-16k-0613<br/>- gpt-4-0613<br/>- gpt-4-32k-0613

## assistant wipecog

- Usage: `[p]assistant wipecog <confirm> `
- Restricted to: `BOT_OWNER`

Wipe all settings and data for entire cog

## assistant persist

- Usage: `[p]assistant persist `
- Restricted to: `BOT_OWNER`

Toggle persistent conversations

## assistant resetembeddings

- Usage: `[p]assistant resetembeddings <yes_or_no> `

Wipe saved embeddings for the assistant<br/><br/>This will delete any and all saved embedding training data for the assistant.

## assistant exportcsv

- Usage: `[p]assistant exportcsv `

Export embeddings to a .csv file<br/><br/>**Note:** csv exports do not include the embedding values

## assistant setlocalembedder

- Usage: `[p]assistant setlocalembedder [model=None] `
- Restricted to: `BOT_OWNER`

Set the local embedding model<br/><br/>Valid models:<br/>- all-MiniLM-L12-v2 (120MB download, 650MB RAM)<br/>- all-MiniLM-L6-v2 (80MB download, 350MB RAM)

## assistant prompt

- Usage: `[p]assistant prompt [prompt] `
- Aliases: `pre`

Set the initial prompt for GPT to use<br/><br/>**Placeholders**<br/>- **botname**: [botname]<br/>- **timestamp**: discord timestamp<br/>- **day**: Mon-Sun<br/>- **date**: MM-DD-YYYY<br/>- **time**: HH:MM AM/PM<br/>- **timetz**: HH:MM AM/PM Timezone<br/>- **members**: server member count<br/>- **username**: user's name<br/>- **displayname**: user's display name<br/>- **roles**: the names of the user's roles<br/>- **rolementions**: the mentions of the user's roles<br/>- **avatar**: the user's avatar url<br/>- **owner**: the owner of the server<br/>- **servercreated**: the create date/time of the server<br/>- **server**: the name of the server<br/>- **py**: python version<br/>- **dpy**: discord.py version<br/>- **red**: red version<br/>- **cogs**: list of currently loaded cogs<br/>- **channelname**: name of the channel the conversation is taking place in<br/>- **channelmention**: current channel mention<br/>- **topic**: topic of current channel (if not forum or thread)<br/>- **banktype**: whether the bank is global or not<br/>- **currency**: currency name<br/>- **bank**: bank name<br/>- **balance**: the user's current balance

## assistant override

- Usage: `[p]assistant override `

Override settings for specific roles

### assistant override maxretention

- Usage: `[p]assistant override maxretention <max_retention> <role> `

Assign a max message retention override to a role<br/><br/>_Specify same role and retention amount to remove the override_

### assistant override model

- Usage: `[p]assistant override model <model> <role> `

Assign a role to use a model<br/><br/>_Specify same role and model to remove the override_

### assistant override maxtime

- Usage: `[p]assistant override maxtime <retention_seconds> <role> `

Assign a max retention time override to a role<br/><br/>_Specify same role and time to remove the override_

### assistant override maxtokens

- Usage: `[p]assistant override maxtokens <max_tokens> <role> `

Assign a max token override to a role<br/><br/>_Specify same role and token count to remove the override_

## assistant toggle

- Usage: `[p]assistant toggle `

Toggle the assistant on or off

## assistant regexfailblock

- Usage: `[p]assistant regexfailblock `
- Restricted to: `BOT_OWNER`

Toggle whether failed regex blocks the assistant's reply<br/><br/>Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)<br/>The bot can safely handle if this happens and will either continue on, or block the response.

## assistant setlocalmodel

- Usage: `[p]assistant setlocalmodel [model=None] `
- Restricted to: `BOT_OWNER`

Set the local LLM<br/><br/>Valid models:<br/>- deepset/roberta-large-squad2 (1.42GB download, 1.6-2.1GB RAM)<br/>- deepset/roberta-base-squad2 (496MB download, 730MB-1.1GB RAM)<br/>- deepset/tinyroberta-squad2 (326MB download, 600-800MB RAM)

## assistant model

- Usage: `[p]assistant model [model=None] `

Set the OpenAI model to use<br/><br/>Valid models and their context info:<br/>- Model-Name: MaxTokens, ModelType<br/>- gpt-3.5-turbo: 4096, chat<br/>- gpt-3.5-turbo-16k: 16384, chat<br/>- gpt-4: 8192, chat<br/>- gpt-4-32k: 32768, chat<br/>- code-davinci-002: 8001, chat<br/>- text-davinci-003: 4097, completion<br/>- text-davinci-002: 4097, completion<br/>- text-curie-001: 2049, completion<br/>- text-babbage-001: 2049, completion<br/>- text-ada-001: 2049, completion<br/><br/>Other sub-models are also included

## assistant view

- Usage: `[p]assistant view [private=True] `

View current settings<br/><br/>To send in current channel, use `[p]assistant view false`

## assistant maxrecursion

- Usage: `[p]assistant maxrecursion <recursion> `

Set the maximum function calls allowed in a row<br/><br/>This sets how many times the model can call functions in a row<br/><br/>Only the following models can call functions at the moment<br/>- gpt-3.5-turbo-0613<br/>- gpt-3.5-turbo-16k-0613<br/>- gpt-4-0613

## assistant resetglobalembeddings

- Usage: `[p]assistant resetglobalembeddings <yes_or_no> `
- Restricted to: `BOT_OWNER`

Wipe saved embeddings for all servers<br/><br/>This will delete any and all saved embedding training data for the assistant.

## assistant maxtime

- Usage: `[p]assistant maxtime <retention_seconds> `

Set the conversation expiration time<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded

## assistant mention

- Usage: `[p]assistant mention `

Toggle whether to ping the user on replies

## assistant confidence

- Usage: `[p]assistant confidence <confidence> `

Set the confidence for the local model if used (0.0 - 1.0)<br/><br/>Closer to 1 is more concise and accurate while closer to 0 is less so.<br/><br/>If the models reponse confidence is under this value, it will not return results

## assistant questionmark

- Usage: `[p]assistant questionmark `

Toggle whether questions need to end with \***\*?\*\***

## assistant exportjson

- Usage: `[p]assistant exportjson `

Export embeddings to a json file

## assistant minlength

- Usage: `[p]assistant minlength <min_question_length> `

set min character length for questions<br/><br/>Set to 0 to respond to anything

## assistant importjson

- Usage: `[p]assistant importjson <overwrite> `

Import embeddings to use with the assistant<br/><br/>Args:<br/> overwrite (bool): overwrite embeddings with existing entry names

# embeddings (Hybrid Command)

- Usage: `[p]embeddings [query] `
- Slash Usage: `/embeddings [query] `
- Restricted to: `ADMIN`
- Aliases: `emenu`
- Checks: `server_only`

Manage embeddings for training<br/><br/>Embeddings are used to optimize training of the assistant and minimize token usage.<br/><br/>By using this the bot can store vast amounts of contextual information without going over the token limit.<br/><br/>**Note**<br/>You can enter a search query with this command to bring up the menu and go directly to that embedding selection.

# customfunctions (Hybrid Command)

- Usage: `[p]customfunctions [function_name=None] `
- Slash Usage: `/customfunctions [function_name=None] `
- Aliases: `customfunction and customfunc`
- Checks: `server_only`

Add custom function calls for Assistant to use<br/><br/>**READ**<br/>- [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)<br/>- [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)<br/>- [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)<br/><br/>Only these two models can use function calls as of now:<br/>- gpt-3.5-turbo<br/>- gpt-3.5-turbo-16k<br/>- gpt-4<br/>- gpt-4-32k<br/><br/>The following objects are passed by default as keyword arguments.<br/>- **user**: the user currently chatting with the bot (discord.Member)<br/>- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)<br/>- **server**: current server (discord.Guild)<br/>- **bot**: the bot object (Red)<br/>- **conf**: the config model for Assistant (GuildSettings)<br/>- All functions **MUST** include `*args, **kwargs` in the params and return a string<br/>

```python
# Can be either sync or async
async def func(*args, **kwargs) -> str:
```

Only bot owner can manage this, server owners can see descriptions but not code
