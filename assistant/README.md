# Assistant Help

Set up and configure an AI assistant (or chat) cog for your server with one of OpenAI's ChatGPT language models.<br/><br/>Features include configurable prompt injection, dynamic embeddings, custom function calling, and more!<br/><br/>- **[p]assistant**: base command for setting up the assistant<br/>- **[p]chat**: talk with the assistant<br/>- **[p]convostats**: view a user's token usage/conversation message count for the channel<br/>- **[p]clearconvo**: reset your conversation with the assistant in the channel

# chathelp

- Usage: `[p]chathelp`

Get help using assistant

# chat

- Usage: `[p]chat <question>`
- Aliases: `ask, escribir, razgovor, discuter, plaudern, 채팅, charlar, baterpapo, and sohbet`
- Cooldown: `1 per 6.0 seconds`
- Checks: `server_only`

Chat with [botname]!<br/><br/>Conversations are _Per_ user _Per_ channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/><br/>**Optional Arguments**<br/>`--outputfile <filename>` - uploads a file with the reply instead (no spaces)<br/>`--extract` - extracts code blocks from the reply<br/>`--last` - resends the last message of the conversation<br/><br/>**Example**<br/>`[p]chat write a python script that prints "Hello World!"`<br/>- Including `--outputfile hello.py` will output a file containing the whole response.<br/>- Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.<br/>- Including `--extract` will send the code separately from the reply

# convostats

- Usage: `[p]convostats [user]`
- Checks: `server_only`

Check the token and message count of yourself or another user's conversation for this channel<br/><br/>Conversations are _Per_ user _Per_ channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/><br/>Conversations are only stored in memory until the bot restarts or the cog reloads

# convoclear

- Usage: `[p]convoclear`
- Aliases: `clearconvo`
- Checks: `server_only`

Reset your conversation with the bot<br/><br/>This will clear all message history between you and the bot for this channel

# convopop

- Usage: `[p]convopop`
- Checks: `bot_has_server_permissions and server_only`

Pop the last message from your conversation

# convocopy

- Usage: `[p]convocopy <channel>`
- Checks: `bot_has_server_permissions and server_only`

Copy the conversation to another channel, thread, or forum

# convoprompt

- Usage: `[p]convoprompt [prompt]`
- Checks: `server_only`

Set a system prompt for this conversation!<br/><br/>This allows customization of assistant behavior on a per channel basis!<br/><br/>Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.

# convoshow

- Usage: `[p]convoshow [user=None] [channel=None]`
- Restricted to: `GUILD_OWNER`
- Aliases: `showconvo`
- Checks: `server_only`

View the current transcript of a conversation<br/><br/>This is mainly here for moderation purposes

# query

- Usage: `[p]query <query>`

Fetch related embeddings according to the current topn setting along with their scores<br/><br/>You can use this to fine-tune the minimum relatedness for your assistant

# assistant

- Usage: `[p]assistant`
- Restricted to: `ADMIN`
- Aliases: `assist`
- Checks: `server_only`

Setup the assistant<br/><br/>You will need an **[api key](https://platform.openai.com/account/api-keys)** from OpenAI to use ChatGPT and their other models.

## assistant timezone

- Usage: `[p]assistant timezone <timezone>`

Set the timezone used for prompt placeholders

## assistant relatedness

- Usage: `[p]assistant relatedness <mimimum_relatedness>`

Set the minimum relatedness an embedding must be to include with the prompt<br/><br/>Relatedness threshold between 0 and 1 to include in embeddings during chat<br/><br/>Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison<br/><br/>**Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be _too_ strict or there wont be any results.

## assistant exportexcel

- Usage: `[p]assistant exportexcel`

Export embeddings to an .xlsx file<br/><br/>**Note:** csv exports do not include the embedding values

## assistant regexblacklist

- Usage: `[p]assistant regexblacklist <regex>`

Remove certain words/phrases in the bot's responses

## assistant questionmark

- Usage: `[p]assistant questionmark`

Toggle whether questions need to end with ****?****

## assistant exportjson

- Usage: `[p]assistant exportjson`

Export embeddings to a json file

## assistant restorecog

- Usage: `[p]assistant restorecog`
- Restricted to: `BOT_OWNER`

Restore the cog from a backup

## assistant topn

- Usage: `[p]assistant topn <top_n>`

Set the embedding inclusion amout<br/><br/>Top N is the amount of embeddings to include with the initial prompt

## assistant collab

- Usage: `[p]assistant collab`

Toggle collaborative conversations<br/><br/>Multiple people speaking in a channel will be treated as a single conversation.

## assistant system

- Usage: `[p]assistant system [system_prompt]`
- Aliases: `sys`

Set the system prompt for GPT to use<br/><br/>Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/><br/>**Placeholders**<br/>- **botname**: [botname]<br/>- **timestamp**: discord timestamp<br/>- **day**: Mon-Sun<br/>- **date**: MM-DD-YYYY<br/>- **time**: HH:MM AM/PM<br/>- **timetz**: HH:MM AM/PM Timezone<br/>- **members**: server member count<br/>- **username**: user's name<br/>- **displayname**: user's display name<br/>- **roles**: the names of the user's roles<br/>- **rolementions**: the mentions of the user's roles<br/>- **avatar**: the user's avatar url<br/>- **owner**: the owner of the server<br/>- **servercreated**: the create date/time of the server<br/>- **server**: the name of the server<br/>- **py**: python version<br/>- **dpy**: discord.py version<br/>- **red**: red version<br/>- **cogs**: list of currently loaded cogs<br/>- **channelname**: name of the channel the conversation is taking place in<br/>- **channelmention**: current channel mention<br/>- **topic**: topic of current channel (if not forum or thread)<br/>- **banktype**: whether the bank is global or not<br/>- **currency**: currency name<br/>- **bank**: bank name<br/>- **balance**: the user's current balance

## assistant mentionrespond

- Usage: `[p]assistant mentionrespond`

Toggle whether the bot responds to mentions in any channel

## assistant frequency

- Usage: `[p]assistant frequency <frequency_penalty>`

Set the frequency penalty for the model (-2.0 to 2.0)<br/>- Defaults is 0<br/><br/>Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.

## assistant listentobots

- Usage: `[p]assistant listentobots`
- Restricted to: `BOT_OWNER`
- Aliases: `botlisten and ignorebots`

Toggle whether the assistant listens to other bots<br/><br/>**NOT RECOMMENDED FOR PUBLIC BOTS!**

## assistant channel

- Usage: `[p]assistant channel [channel=None]`

Set the channel for the assistant

## assistant sysoverride

- Usage: `[p]assistant sysoverride`

Toggle allowing per-conversation system prompt overriding

## assistant seed

- Usage: `[p]assistant seed [seed=None]`

Make the model more deterministic by setting a seed for the model.<br/>- Default is None<br/><br/>If specified, the system will make a best effort to sample deterministically, such that repeated requests with the same seed and parameters should return the same result.

## assistant persist

- Usage: `[p]assistant persist`
- Restricted to: `BOT_OWNER`

Toggle persistent conversations

## assistant maxtime

- Usage: `[p]assistant maxtime <retention_seconds>`

Set the conversation expiration time<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded

## assistant functioncalls

- Usage: `[p]assistant functioncalls`
- Aliases: `usefunctions`

Toggle whether GPT can call functions<br/><br/>Only the following models can call functions at the moment (With OpenAI key only)<br/>- gpt-3.5-turbo<br/>- gpt-3.5-turbo-16k<br/>- gpt-4<br/>- gpt-4-32k

## assistant embedmodel

- Usage: `[p]assistant embedmodel [model=None]`

Set the OpenAI Embedding model to use

## assistant regexfailblock

- Usage: `[p]assistant regexfailblock`

Toggle whether failed regex blocks the assistant's reply<br/><br/>Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)<br/>The bot can safely handle if this happens and will either continue on, or block the response.

## assistant resetusage

- Usage: `[p]assistant resetusage`

Reset the token usage stats for this server

## assistant maxretention

- Usage: `[p]assistant maxretention <max_retention>`

Set the max messages for a conversation<br/><br/>Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to disable conversation retention<br/><br/>**Note:** _actual message count may exceed the max retention during an API call_

## assistant maxrecursion

- Usage: `[p]assistant maxrecursion <recursion>`

Set the maximum function calls allowed in a row<br/><br/>This sets how many times the model can call functions in a row<br/><br/>Only the following models can call functions at the moment<br/>- gpt-3.5-turbo<br/>- gpt-3.5-turbo-16k<br/>- gpt-4<br/>- gpt-4-32k

## assistant model

- Usage: `[p]assistant model [model=None]`

Set the OpenAI model to use<br/><br/>**NOTE**<br/>Specifying a model without it's identifier (like `gpt-3.5-turbo` instead of `gpt-3.5-turbo-0125`)<br/>will sometimes lose the ability to call functions in parallel for some reason, this is an OpenAI issue.

## assistant override

- Usage: `[p]assistant override`

Override settings for specific roles<br/><br/>**NOTE**<br/>If a user has two roles with override settings, override associated with the higher role will be used.

### assistant override model

- Usage: `[p]assistant override model <model> <role>`

Assign a role to use a model<br/><br/>_Specify same role and model to remove the override_

### assistant override maxretention

- Usage: `[p]assistant override maxretention <max_retention> <role>`

Assign a max message retention override to a role<br/><br/>_Specify same role and retention amount to remove the override_

### assistant override maxtime

- Usage: `[p]assistant override maxtime <retention_seconds> <role>`

Assign a max retention time override to a role<br/><br/>_Specify same role and time to remove the override_

### assistant override maxtokens

- Usage: `[p]assistant override maxtokens <max_tokens> <role>`

Assign a max token override to a role<br/><br/>_Specify same role and token count to remove the override_

### assistant override maxresponsetokens

- Usage: `[p]assistant override maxresponsetokens <max_tokens> <role>`

Assign a max response token override to a role<br/><br/>Set to 0 for response tokens to be dynamic<br/><br/>_Specify same role and token count to remove the override_

## assistant wipecog

- Usage: `[p]assistant wipecog <confirm>`
- Restricted to: `BOT_OWNER`

Wipe all settings and data for entire cog

## assistant backupcog

- Usage: `[p]assistant backupcog`
- Restricted to: `BOT_OWNER`

Take a backup of the cog<br/><br/>- This does not backup conversation data

## assistant importexcel

- Usage: `[p]assistant importexcel <overwrite>`

Import embeddings from an .xlsx file<br/><br/>Args:<br/> overwrite (bool): overwrite embeddings with existing entry names

## assistant exportcsv

- Usage: `[p]assistant exportcsv`

Export embeddings to a .csv file<br/><br/>**Note:** csv exports do not include the embedding values

## assistant embedmethod

- Usage: `[p]assistant embedmethod`

Cycle between embedding methods<br/><br/>**Dynamic** embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.<br/>When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly<br/><br/>**Static** embeddings are applied in front of each user message and get stored with the conversation instead of being replaced with each question.<br/><br/>**Hybrid** embeddings are a combination, with the first embedding being stored in the conversation and the rest being dynamic, this saves a bit on token usage.<br/><br/>**User** embeddings are injected into the beginning of the prompt as the first user message.<br/><br/>Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings. The hybrid method is a good middle ground

## assistant openaikey

- Usage: `[p]assistant openaikey`
- Aliases: `key`

Set your OpenAI key

## assistant view

- Usage: `[p]assistant view [private=False]`
- Aliases: `v`

View current settings<br/><br/>To send in current channel, use `[p]assistant view false`

## assistant temperature

- Usage: `[p]assistant temperature <temperature>`

Set the temperature for the model (0.0 - 2.0)<br/>- Defaults is 1<br/><br/>Closer to 0 is more concise and accurate while closer to 2 is more imaginative

## assistant refreshembeds

- Usage: `[p]assistant refreshembeds`
- Aliases: `refreshembeddings, syncembeds, and syncembeddings`

Refresh embedding weights<br/><br/>_This command can be used when changing the embedding model_<br/><br/>Embeddings that were created using OpenAI cannot be use with the self-hosted model and vice versa

## assistant resetglobalconversations

- Usage: `[p]assistant resetglobalconversations <yes_or_no>`
- Restricted to: `BOT_OWNER`

Wipe saved conversations for the assistant in all servers<br/><br/>This will delete any and all saved conversations for the assistant.

## assistant maxresponsetokens

- Usage: `[p]assistant maxresponsetokens <max_tokens>`

Set the max response tokens the model can respond with<br/><br/>Set to 0 for response tokens to be dynamic

## assistant mention

- Usage: `[p]assistant mention`

Toggle whether to ping the user on replies

## assistant usage

- Usage: `[p]assistant usage`

View the token usage stats for this server

## assistant questionmode

- Usage: `[p]assistant questionmode`

Toggle question mode<br/><br/>If question mode is on, embeddings will only be sourced during the first message of a conversation and messages that end in **?**

## assistant importcsv

- Usage: `[p]assistant importcsv <overwrite>`

Import embeddings to use with the assistant<br/><br/>Args:<br/> overwrite (bool): overwrite embeddings with existing entry names<br/><br/>This will read excel files too

## assistant tutor

- Usage: `[p]assistant tutor <role_or_member>`
- Aliases: `tutors`

Add/Remove items from the tutor list.<br/><br/>If using OpenAI's function calling and talking to a tutor, the AI is able to create its own embeddings to remember later<br/><br/>`role_or_member` can be a member or role

## assistant resetembeddings

- Usage: `[p]assistant resetembeddings <yes_or_no>`

Wipe saved embeddings for the assistant<br/><br/>This will delete any and all saved embedding training data for the assistant.

## assistant presence

- Usage: `[p]assistant presence <presence_penalty>`

Set the presence penalty for the model (-2.0 to 2.0)<br/>- Defaults is 0<br/><br/>Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.

## assistant maxtokens

- Usage: `[p]assistant maxtokens <max_tokens>`

Set the max tokens that the bot will send to the model<br/><br/>**Tips**<br/>- Max tokens are a soft cap, sometimes messages can be a little over<br/>- If you set max tokens too high the cog will auto-adjust to 100 less than the models natural cap<br/>- Ideally set max to 500 less than that models maximum, to allow adequate responses<br/><br/>Using more than the model can handle will raise exceptions.

## assistant importjson

- Usage: `[p]assistant importjson <overwrite>`

Import embeddings to use with the assistant<br/><br/>Args:<br/> overwrite (bool): overwrite embeddings with existing entry names

## assistant blacklist

- Usage: `[p]assistant blacklist <channel_role_member>`

Add/Remove items from the blacklist<br/><br/>`channel_role_member` can be a member, role, channel, or category channel

## assistant prompt

- Usage: `[p]assistant prompt [prompt]`
- Aliases: `pre`

Set the initial prompt for GPT to use<br/><br/>Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/><br/>**Placeholders**<br/>- **botname**: [botname]<br/>- **timestamp**: discord timestamp<br/>- **day**: Mon-Sun<br/>- **date**: MM-DD-YYYY<br/>- **time**: HH:MM AM/PM<br/>- **timetz**: HH:MM AM/PM Timezone<br/>- **members**: server member count<br/>- **username**: user's name<br/>- **displayname**: user's display name<br/>- **roles**: the names of the user's roles<br/>- **rolementions**: the mentions of the user's roles<br/>- **avatar**: the user's avatar url<br/>- **owner**: the owner of the server<br/>- **servercreated**: the create date/time of the server<br/>- **server**: the name of the server<br/>- **py**: python version<br/>- **dpy**: discord.py version<br/>- **red**: red version<br/>- **cogs**: list of currently loaded cogs<br/>- **channelname**: name of the channel the conversation is taking place in<br/>- **channelmention**: current channel mention<br/>- **topic**: topic of current channel (if not forum or thread)<br/>- **banktype**: whether the bank is global or not<br/>- **currency**: currency name<br/>- **bank**: bank name<br/>- **balance**: the user's current balance

## assistant resolution

- Usage: `[p]assistant resolution`

Switch vision resolution between high and low for relevant GPT-4-Turbo models

## assistant resetconversations

- Usage: `[p]assistant resetconversations <yes_or_no>`

Wipe saved conversations for the assistant in this server<br/><br/>This will delete any and all saved conversations for the assistant.

## assistant resetglobalembeddings

- Usage: `[p]assistant resetglobalembeddings <yes_or_no>`
- Restricted to: `BOT_OWNER`

Wipe saved embeddings for all servers<br/><br/>This will delete any and all saved embedding training data for the assistant.

## assistant toggle

- Usage: `[p]assistant toggle`

Toggle the assistant on or off

## assistant minlength

- Usage: `[p]assistant minlength <min_question_length>`

set min character length for questions<br/><br/>Set to 0 to respond to anything

# embeddings (Hybrid Command)

- Usage: `[p]embeddings [query]`
- Slash Usage: `/embeddings [query]`
- Restricted to: `ADMIN`
- Aliases: `emenu`
- Checks: `server_only`

Manage embeddings for training<br/><br/>Embeddings are used to optimize training of the assistant and minimize token usage.<br/><br/>By using this the bot can store vast amounts of contextual information without going over the token limit.<br/><br/>**Note**<br/>You can enter a search query with this command to bring up the menu and go directly to that embedding selection.

# customfunctions (Hybrid Command)

- Usage: `[p]customfunctions [function_name=None]`
- Slash Usage: `/customfunctions [function_name=None]`
- Aliases: `customfunction and customfunc`
- Checks: `server_only`

Add custom function calls for Assistant to use<br/><br/>**READ**<br/>- [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)<br/>- [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)<br/>- [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)<br/><br/>Only these models can use function calls as of now:<br/>- gpt-3.5-turbo<br/>- gpt-3.5-turbo-16k<br/>- gpt-4<br/>- gpt-4-32k<br/><br/>The following objects are passed by default as keyword arguments.<br/>- **user**: the user currently chatting with the bot (discord.Member)<br/>- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)<br/>- **server**: current server (discord.Guild)<br/>- **bot**: the bot object (Red)<br/>- **conf**: the config model for Assistant (GuildSettings)<br/>- All functions **MUST** include `*args, **kwargs` in the params and return a string<br/>`python<br/># Can be either sync or async<br/>async def func(*args, **kwargs) -> str:<br/>`<br/>Only bot owner can manage this, server owners can see descriptions but not code
