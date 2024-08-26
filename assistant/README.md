# Assistant Help

Set up and configure an AI assistant (or chat) cog for your server with one of OpenAI's ChatGPT language models.<br/><br/>Features include configurable prompt injection, dynamic embeddings, custom function calling, and more!<br/><br/>- **[p]assistant**: base command for setting up the assistant<br/>- **[p]chat**: talk with the assistant<br/>- **[p]convostats**: view a user's token usage/conversation message count for the channel<br/>- **[p]clearconvo**: reset your conversation with the assistant in the channel

# /draw (Slash Command)
Generate an image with Dalle-3<br/>
 - Usage: `/draw <prompt> [size] [quality] [style]`
 - `prompt:` (Required) What would you like to draw?
 - `size:` (Optional) The size of the image to generate
 - `quality:` (Optional) The quality of the image to generate
 - `style:` (Optional) The style of the image to generate

 - Checks: `Server Only`
# .chathelp
Get help using assistant<br/>
 - Usage: `.chathelp`
# .chat
Chat with Autto!<br/>

Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/>

**Optional Arguments**<br/>
`--outputfile <filename>` - uploads a file with the reply instead (no spaces)<br/>
`--extract` - extracts code blocks from the reply<br/>
`--last` - resends the last message of the conversation<br/>

**Example**<br/>
`.chat write a python script that prints "Hello World!"`<br/>
- Including `--outputfile hello.py` will output a file containing the whole response.<br/>
- Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.<br/>
- Including `--extract` will send the code separately from the reply<br/>
 - Usage: `.chat <question>`
 - Aliases: `ask, escribir, razgovor, discuter, plaudern, 채팅, charlar, baterpapo, and sohbet`
 - Cooldown: `1 per 6.0 seconds`
 - Checks: `server_only`
# .convostats
Check the token and message count of yourself or another user's conversation for this channel<br/>

Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/>

Conversations are only stored in memory until the bot restarts or the cog reloads<br/>
 - Usage: `.convostats [user]`
 - Checks: `server_only`
# .convoclear
Reset your conversation with the bot<br/>

This will clear all message history between you and the bot for this channel<br/>
 - Usage: `.convoclear`
 - Aliases: `clearconvo`
 - Checks: `server_only`
# .convopop
Pop the last message from your conversation<br/>
 - Usage: `.convopop`
 - Checks: `bot_has_server_permissions and server_only`
# .convocopy
Copy the conversation to another channel, thread, or forum<br/>
 - Usage: `.convocopy <channel>`
 - Checks: `bot_has_server_permissions and server_only`
# .convoprompt
Set a system prompt for this conversation!<br/>

This allows customization of assistant behavior on a per channel basis!<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>
 - Usage: `.convoprompt [prompt]`
 - Checks: `server_only`
# .convoshow
View the current transcript of a conversation<br/>

This is mainly here for moderation purposes<br/>
 - Usage: `.convoshow [user=None] [channel=None]`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `showconvo`
 - Checks: `server_only`
# .query
Fetch related embeddings according to the current topn setting along with their scores<br/>

You can use this to fine-tune the minimum relatedness for your assistant<br/>
 - Usage: `.query <query>`
# .assistant
Setup the assistant<br/>

You will need an **[api key](https://platform.openai.com/account/api-keys)** from OpenAI to use ChatGPT and their other models.<br/>
 - Usage: `.assistant`
 - Restricted to: `ADMIN`
 - Aliases: `assist`
 - Checks: `server_only`
## .assistant resolution
Switch vision resolution between high and low for relevant GPT-4-Turbo models<br/>
 - Usage: `.assistant resolution`
## .assistant topn
Set the embedding inclusion amout<br/>

Top N is the amount of embeddings to include with the initial prompt<br/>
 - Usage: `.assistant topn <top_n>`
## .assistant importexcel
Import embeddings from an .xlsx file<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>
 - Usage: `.assistant importexcel <overwrite>`
## .assistant presence
Set the presence penalty for the model (-2.0 to 2.0)<br/>
- Defaults is 0<br/>

Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.<br/>
 - Usage: `.assistant presence <presence_penalty>`
## .assistant toggle
Toggle the assistant on or off<br/>
 - Usage: `.assistant toggle`
## .assistant maxtime
Set the conversation expiration time<br/>

Regardless of this number, the initial prompt and internal system message are always included,<br/>
this only applies to any conversation between the user and bot after that.<br/>

Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded<br/>
 - Usage: `.assistant maxtime <retention_seconds>`
## .assistant frequency
Set the frequency penalty for the model (-2.0 to 2.0)<br/>
- Defaults is 0<br/>

Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.<br/>
 - Usage: `.assistant frequency <frequency_penalty>`
## .assistant braveapikey
Enables use of the `search_internet` function<br/>

Get your API key **[Here](https://brave.com/search/api/)**<br/>
 - Usage: `.assistant braveapikey`
 - Restricted to: `BOT_OWNER`
 - Aliases: `brave`
## .assistant functioncalls
Toggle whether GPT can call functions<br/>
 - Usage: `.assistant functioncalls`
 - Aliases: `usefunctions`
## .assistant model
Set the OpenAI model to use<br/>

**NOTE**<br/>
Specifying a model without it's identifier (like `gpt-3.5-turbo` instead of `gpt-3.5-turbo-0125`)<br/>
will sometimes lose the ability to call functions in parallel for some reason, this is an OpenAI issue.<br/>
 - Usage: `.assistant model [model=None]`
## .assistant restorecog
Restore the cog from a backup<br/>
 - Usage: `.assistant restorecog`
 - Restricted to: `BOT_OWNER`
## .assistant prompt
Set the initial prompt for GPT to use<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>

**Placeholders**<br/>
- **botname**: Autto<br/>
- **timestamp**: discord timestamp<br/>
- **day**: Mon-Sun<br/>
- **date**: MM-DD-YYYY<br/>
- **time**: HH:MM AM/PM<br/>
- **timetz**: HH:MM AM/PM Timezone<br/>
- **members**: server member count<br/>
- **username**: user's name<br/>
- **displayname**: user's display name<br/>
- **roles**: the names of the user's roles<br/>
- **rolementions**: the mentions of the user's roles<br/>
- **avatar**: the user's avatar url<br/>
- **owner**: the owner of the server<br/>
- **servercreated**: the create date/time of the server<br/>
- **server**: the name of the server<br/>
- **py**: python version<br/>
- **dpy**: discord.py version<br/>
- **red**: red version<br/>
- **cogs**: list of currently loaded cogs<br/>
- **channelname**: name of the channel the conversation is taking place in<br/>
- **channelmention**: current channel mention<br/>
- **topic**: topic of current channel (if not forum or thread)<br/>
- **banktype**: whether the bank is global or not<br/>
- **currency**: currency name<br/>
- **bank**: bank name<br/>
- **balance**: the user's current balance<br/>
 - Usage: `.assistant prompt [prompt]`
 - Aliases: `pre`
## .assistant temperature
Set the temperature for the model (0.0 - 2.0)<br/>
- Defaults is 1<br/>

Closer to 0 is more concise and accurate while closer to 2 is more imaginative<br/>
 - Usage: `.assistant temperature <temperature>`
## .assistant maxresponsetokens
Set the max response tokens the model can respond with<br/>

Set to 0 for response tokens to be dynamic<br/>
 - Usage: `.assistant maxresponsetokens <max_tokens>`
## .assistant importjson
Import embeddings to use with the assistant<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>
 - Usage: `.assistant importjson <overwrite>`
## .assistant channelprompt
Set a channel specific system prompt<br/>
 - Usage: `.assistant channelprompt [channel=None] [system_prompt]`
## .assistant toggledraw
Toggle the draw command on or off<br/>
 - Usage: `.assistant toggledraw`
 - Aliases: `drawtoggle`
## .assistant embedmodel
Set the OpenAI Embedding model to use<br/>
 - Usage: `.assistant embedmodel [model=None]`
## .assistant regexfailblock
Toggle whether failed regex blocks the assistant's reply<br/>

Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)<br/>
The bot can safely handle if this happens and will either continue on, or block the response.<br/>
 - Usage: `.assistant regexfailblock`
## .assistant collab
Toggle collaborative conversations<br/>

Multiple people speaking in a channel will be treated as a single conversation.<br/>
 - Usage: `.assistant collab`
## .assistant exportexcel
Export embeddings to an .xlsx file<br/>

**Note:** csv exports do not include the embedding values<br/>
 - Usage: `.assistant exportexcel`
## .assistant exportcsv
Export embeddings to a .csv file<br/>

**Note:** csv exports do not include the embedding values<br/>
 - Usage: `.assistant exportcsv`
## .assistant persist
Toggle persistent conversations<br/>
 - Usage: `.assistant persist`
 - Restricted to: `BOT_OWNER`
## .assistant resetusage
Reset the token usage stats for this server<br/>
 - Usage: `.assistant resetusage`
## .assistant refreshembeds
Refresh embedding weights<br/>

*This command can be used when changing the embedding model*<br/>

Embeddings that were created using OpenAI cannot be use with the self-hosted model and vice versa<br/>
 - Usage: `.assistant refreshembeds`
 - Aliases: `refreshembeddings, syncembeds, and syncembeddings`
## .assistant tutor
Add/Remove items from the tutor list.<br/>

If using OpenAI's function calling and talking to a tutor, the AI is able to create its own embeddings to remember later<br/>

`role_or_member` can be a member or role<br/>
 - Usage: `.assistant tutor <role_or_member>`
 - Aliases: `tutors`
## .assistant timezone
Set the timezone used for prompt placeholders<br/>
 - Usage: `.assistant timezone <timezone>`
## .assistant maxrecursion
Set the maximum function calls allowed in a row<br/>

This sets how many times the model can call functions in a row<br/>

Only the following models can call functions at the moment<br/>
- gpt-3.5-turbo<br/>
- gpt-3.5-turbo-16k<br/>
- gpt-4<br/>
- gpt-4-32k<br/>
 - Usage: `.assistant maxrecursion <recursion>`
## .assistant resetglobalembeddings
Wipe saved embeddings for all servers<br/>

This will delete any and all saved embedding training data for the assistant.<br/>
 - Usage: `.assistant resetglobalembeddings <yes_or_no>`
 - Restricted to: `BOT_OWNER`
## .assistant wipecog
Wipe all settings and data for entire cog<br/>
 - Usage: `.assistant wipecog <confirm>`
 - Restricted to: `BOT_OWNER`
## .assistant resetglobalconversations
Wipe saved conversations for the assistant in all servers<br/>

This will delete any and all saved conversations for the assistant.<br/>
 - Usage: `.assistant resetglobalconversations <yes_or_no>`
 - Restricted to: `BOT_OWNER`
## .assistant maxretention
Set the max messages for a conversation<br/>

Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/>

Regardless of this number, the initial prompt and internal system message are always included,<br/>
this only applies to any conversation between the user and bot after that.<br/>

Set to 0 to disable conversation retention<br/>

**Note:** *actual message count may exceed the max retention during an API call*<br/>
 - Usage: `.assistant maxretention <max_retention>`
## .assistant resetembeddings
Wipe saved embeddings for the assistant<br/>

This will delete any and all saved embedding training data for the assistant.<br/>
 - Usage: `.assistant resetembeddings <yes_or_no>`
## .assistant questionmode
Toggle question mode<br/>

If question mode is on, embeddings will only be sourced during the first message of a conversation and messages that end in **?**<br/>
 - Usage: `.assistant questionmode`
## .assistant sysoverride
Toggle allowing per-conversation system prompt overriding<br/>
 - Usage: `.assistant sysoverride`
## .assistant questionmark
Toggle whether questions need to end with **__?__**<br/>
 - Usage: `.assistant questionmark`
## .assistant resetconversations
Wipe saved conversations for the assistant in this server<br/>

This will delete any and all saved conversations for the assistant.<br/>
 - Usage: `.assistant resetconversations <yes_or_no>`
## .assistant importcsv
Import embeddings to use with the assistant<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>

This will read excel files too<br/>
 - Usage: `.assistant importcsv <overwrite>`
## .assistant mentionrespond
Toggle whether the bot responds to mentions in any channel<br/>
 - Usage: `.assistant mentionrespond`
## .assistant relatedness
Set the minimum relatedness an embedding must be to include with the prompt<br/>

Relatedness threshold between 0 and 1 to include in embeddings during chat<br/>

Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison<br/>

**Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be *too* strict or there wont be any results.<br/>
 - Usage: `.assistant relatedness <mimimum_relatedness>`
## .assistant maxtokens
Set the max tokens that the bot will send to the model<br/>

**Tips**<br/>
- Max tokens are a soft cap, sometimes messages can be a little over<br/>
- If you set max tokens too high the cog will auto-adjust to 100 less than the models natural cap<br/>
- Ideally set max to 500 less than that models maximum, to allow adequate responses<br/>

Using more than the model can handle will raise exceptions.<br/>
 - Usage: `.assistant maxtokens <max_tokens>`
## .assistant listentobots
Toggle whether the assistant listens to other bots<br/>

**NOT RECOMMENDED FOR PUBLIC BOTS!**<br/>
 - Usage: `.assistant listentobots`
 - Restricted to: `BOT_OWNER`
 - Aliases: `botlisten and ignorebots`
## .assistant channel
Set the channel for the assistant<br/>
 - Usage: `.assistant channel [channel=None]`
## .assistant view
View current settings<br/>

To send in current channel, use `.assistant view false`<br/>
 - Usage: `.assistant view [private=False]`
 - Aliases: `v`
## .assistant openaikey
Set your OpenAI key<br/>
 - Usage: `.assistant openaikey`
 - Aliases: `key`
## .assistant blacklist
Add/Remove items from the blacklist<br/>

`channel_role_member` can be a member, role, channel, or category channel<br/>
 - Usage: `.assistant blacklist <channel_role_member>`
## .assistant system
Set the system prompt for GPT to use<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>

**Placeholders**<br/>
- **botname**: Autto<br/>
- **timestamp**: discord timestamp<br/>
- **day**: Mon-Sun<br/>
- **date**: MM-DD-YYYY<br/>
- **time**: HH:MM AM/PM<br/>
- **timetz**: HH:MM AM/PM Timezone<br/>
- **members**: server member count<br/>
- **username**: user's name<br/>
- **displayname**: user's display name<br/>
- **roles**: the names of the user's roles<br/>
- **rolementions**: the mentions of the user's roles<br/>
- **avatar**: the user's avatar url<br/>
- **owner**: the owner of the server<br/>
- **servercreated**: the create date/time of the server<br/>
- **server**: the name of the server<br/>
- **py**: python version<br/>
- **dpy**: discord.py version<br/>
- **red**: red version<br/>
- **cogs**: list of currently loaded cogs<br/>
- **channelname**: name of the channel the conversation is taking place in<br/>
- **channelmention**: current channel mention<br/>
- **topic**: topic of current channel (if not forum or thread)<br/>
- **banktype**: whether the bank is global or not<br/>
- **currency**: currency name<br/>
- **bank**: bank name<br/>
- **balance**: the user's current balance<br/>
 - Usage: `.assistant system [system_prompt]`
 - Aliases: `sys`
## .assistant channelpromptshow
Show the channel specific system prompt<br/>
 - Usage: `.assistant channelpromptshow [channel=None]`
## .assistant regexblacklist
Remove certain words/phrases in the bot's responses<br/>
 - Usage: `.assistant regexblacklist <regex>`
## .assistant exportjson
Export embeddings to a json file<br/>
 - Usage: `.assistant exportjson`
## .assistant override
Override settings for specific roles<br/>

**NOTE**<br/>
If a user has two roles with override settings, override associated with the higher role will be used.<br/>
 - Usage: `.assistant override`
### .assistant override maxtime
Assign a max retention time override to a role<br/>

*Specify same role and time to remove the override*<br/>
 - Usage: `.assistant override maxtime <retention_seconds> <role>`
### .assistant override maxtokens
Assign a max token override to a role<br/>

*Specify same role and token count to remove the override*<br/>
 - Usage: `.assistant override maxtokens <max_tokens> <role>`
### .assistant override model
Assign a role to use a model<br/>

*Specify same role and model to remove the override*<br/>
 - Usage: `.assistant override model <model> <role>`
### .assistant override maxresponsetokens
Assign a max response token override to a role<br/>

Set to 0 for response tokens to be dynamic<br/>

*Specify same role and token count to remove the override*<br/>
 - Usage: `.assistant override maxresponsetokens <max_tokens> <role>`
### .assistant override maxretention
Assign a max message retention override to a role<br/>

*Specify same role and retention amount to remove the override*<br/>
 - Usage: `.assistant override maxretention <max_retention> <role>`
## .assistant embedmethod
Cycle between embedding methods<br/>

**Dynamic** embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.<br/>
When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly<br/>

**Static** embeddings are applied in front of each user message and get stored with the conversation instead of being replaced with each question.<br/>

**Hybrid** embeddings are a combination, with the first embedding being stored in the conversation and the rest being dynamic, this saves a bit on token usage.<br/>

**User** embeddings are injected into the beginning of the prompt as the first user message.<br/>

Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings. The hybrid method is a good middle ground<br/>
 - Usage: `.assistant embedmethod`
## .assistant backupcog
Take a backup of the cog<br/>

- This does not backup conversation data<br/>
 - Usage: `.assistant backupcog`
 - Restricted to: `BOT_OWNER`
## .assistant usage
View the token usage stats for this server<br/>
 - Usage: `.assistant usage`
## .assistant seed
Make the model more deterministic by setting a seed for the model.<br/>
- Default is None<br/>

If specified, the system will make a best effort to sample deterministically, such that repeated requests with the same seed and parameters should return the same result.<br/>
 - Usage: `.assistant seed [seed=None]`
## .assistant mention
Toggle whether to ping the user on replies<br/>
 - Usage: `.assistant mention`
## .assistant minlength
set min character length for questions<br/>

Set to 0 to respond to anything<br/>
 - Usage: `.assistant minlength <min_question_length>`
# .embeddings (Hybrid Command)
Manage embeddings for training<br/>

Embeddings are used to optimize training of the assistant and minimize token usage.<br/>

By using this the bot can store vast amounts of contextual information without going over the token limit.<br/>

**Note**<br/>
You can enter a search query with this command to bring up the menu and go directly to that embedding selection.<br/>
 - Usage: `.embeddings [query]`
 - Slash Usage: `/embeddings [query]`
 - Restricted to: `ADMIN`
 - Aliases: `emenu`
 - Checks: `server_only`
# .customfunctions (Hybrid Command)
Add custom function calls for Assistant to use<br/>

**READ**<br/>
- [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)<br/>
- [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)<br/>
- [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)<br/>

The following objects are passed by default as keyword arguments.<br/>
- **user**: the user currently chatting with the bot (discord.Member)<br/>
- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)<br/>
- **server**: current server (discord.Guild)<br/>
- **bot**: the bot object (Red)<br/>
- **conf**: the config model for Assistant (GuildSettings)<br/>
- All functions **MUST** include `*args, **kwargs` in the params and return a string<br/>
```python
# Can be either sync or async
async def func(*args, **kwargs) -> str:
```
Only bot owner can manage this, server owners can see descriptions but not code<br/>
 - Usage: `.customfunctions [function_name=None]`
 - Slash Usage: `/customfunctions [function_name=None]`
 - Aliases: `customfunction and customfunc`
 - Checks: `server_only`
