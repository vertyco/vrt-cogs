# Assistant

Set up and configure an AI assistant (or chat) cog for your server with one of OpenAI's ChatGPT language models.<br/><br/>Features include configurable prompt injection, admin-curated grounded RAG embeddings, custom function calling, conversation compaction, and more!<br/><br/>- **[p]assistant**: base command for setting up the assistant<br/>- **[p]chat**: talk with the assistant<br/>- **[p]convostats**: view a user's token usage/conversation message count for the channel<br/>- **[p]convocontext**: view a detailed token breakdown of your conversation context<br/>- **[p]convocompact**: compact your conversation using LLM summarization<br/>- **[p]clearconvo**: reset your conversation with the assistant in the channel

## Assistant Command Groups

The `[p]assistant` command uses hierarchical groups to organize configuration. Use `[p]help assistant <group>` for detailed help on any group.

### Per-Guild Groups

- **`[p]assistant set`** (alias: `settings`) - General guild settings
  - `timezone` - Set the timezone for prompt placeholders
  - `channel` - Set the primary auto-response channel
  - `listen` - Toggle listen on the current channel
  - `sysoverride` - Allow per-conversation system prompts
  - `model` - Set the chat model
  - `maxrecursion` - Max function call recursion depth
  - `thinkprefix` - Set thinking block prefix
  - `thinksuffix` - Set thinking block suffix
  - `verbosity` - Switch gpt-5 response verbosity
  - `reasoningfiles` - Toggle reasoning file output
  - `planner` - Manage planner role/user access
  - `customvars` - View registered custom variables
  - `listenbots` - Toggle listening to other bots (owner)

- **`[p]assistant trigger`** - Trigger phrase system
  - `toggle` - Enable/disable trigger phrases
  - `phrase` - Add/remove trigger phrases (supports regex)
  - `prompt` - Set custom prompt for triggered messages
  - `ignore` - Ignore channels/categories for triggers
  - `list` - View configured trigger phrases

- **`[p]assistant prompt`** - Prompt and context management
  - `system` - Set the system prompt for the assistant
  - `defaultsystem` - Set global default system prompt (owner)
  - `initial` - Set the initial context prompt
  - `channel` - Set the primary auto-response channel
  - `channelcustom` - Set channel-specific system prompt
  - `channelshow` - Display a channel's system prompt

- **`[p]assistant features`** - Feature toggles
  - `enable` - Toggle assistant on/off
  - `draw` - Toggle image generation command
  - `mention` - Toggle user mention pings
  - `mention-respond` - Toggle mention responses
  - `functions` - Toggle function calling
  - `collaborative` - Toggle multi-user conversations
  - `question-mode` - Toggle question-only embedding sourcing
  - `persist` - Toggle conversation persistence (owner)

- **`[p]assistant filter`** - Content filtering
  - `question` - Toggle `?` requirement for triggering
  - `minlength` - Set minimum character length
  - `regex` - Add/remove regex blacklist patterns
  - `failblock` - Toggle blocking on regex failure
  - `blacklist` - Manage user/role/channel blacklist

- **`[p]assistant embed`** (alias: `embeddings`) - Embedding management
  - `topn` - Set RAG retrieval count
  - `relatedness` - Set minimum relatedness score
  - `model` - Set embedding model
  - `reset` - Wipe server embeddings
  - `resetglobal` - Wipe global embeddings (owner)
  - `refresh` - Re-embed entries with current model
  - `importcsv` - Import from CSV/Excel files
  - `importjson` - Import from JSON
  - `importexcel` - Import from Excel
  - `exportexcel` - Export to Excel
  - `exportcsv` - Export to CSV
  - `exportjson` - Export to JSON

- **`[p]assistant limits`** - Token and retention limits
  - `maxretention` - Max messages to retain
  - `maxtime` - Max retention time in seconds
  - `maxtokens` - Max total token limit
  - `maxresponse` - Max response token limit

- **`[p]assistant params`** - Model behavior parameters
  - `temperature` - Set temperature (0.0 - 2.0)
  - `frequency` - Set frequency penalty (-2.0 to 2.0)
  - `presence` - Set presence penalty (-2.0 to 2.0)
  - `resolution` - Set image resolution
  - `reasoning` - Set reasoning effort level
  - `seed` - Set random seed for reproducibility

- **`[p]assistant override`** - Role-based overrides
  - `model` - Set model override for a role
  - `maxtokens` - Max tokens override per role
  - `maxresponsetokens` - Max response tokens per role
  - `maxretention` - Max retention per role
  - `maxtime` - Max retention time per role
  - `reasoning` - Reasoning effort per role

- **`[p]assistant compaction`** - Conversation compaction
  - `toggle` - Enable/disable compaction
  - `model` - Set compaction-specific model
  - `threshold` - Set token threshold for compaction

- **`[p]assistant autoanswer`** - Auto-answer system
  - `toggle` - Enable/disable auto-answer
  - `threshold` - Set confidence threshold
  - `ignore` - Ignore channels for auto-answer
  - `model` - Set model for auto-answer

- **`[p]assistant scheduler`** (alias: `tasks`) - Scheduled task management
  - `list` - View scheduled tasks
  - `cancel` - Cancel a task by ID
  - `clear` - Clear all tasks

### Owner-Only Groups

- **`[p]assistant api`** - API keys and authentication
  - `openai` - Set server OpenAI API key
  - `brave` - Set Brave Search API key
  - `endpoint` - Set endpoint override API key
  - `override` - Configure custom OpenAI-compatible endpoint

- **`[p]assistant admin`** - Dangerous maintenance operations
  - `resetusage` - Reset token usage stats
  - `resetconversations` - Wipe server conversations
  - `resetglobalconversations` - Wipe all conversations
  - `probe` - Probe custom endpoint profile
  - `wipe` - Wipe all cog data
  - `backup` - Backup cog to JSON file
  - `restore` - Restore cog from backup

### Standalone Commands

- **`[p]assistant view`** (alias: `v`) - View current configuration
- **`[p]assistant usage`** - View token usage stats

## /draw (Slash Command)

Generate an image with AI<br/>

 - Usage: `/draw <prompt> [size] [quality] [style] [model]`
 - `prompt:` (Required) What would you like to draw?
 - `size:` (Optional) The size of the image to generate
 - `quality:` (Optional) The quality of the image to generate
 - `style:` (Optional) The style of the image to generate
 - `model:` (Optional) The model to use for image generation

 - Checks: `Server Only`

## /tldr (Slash Command)

Summarize whats been happening in a channel<br/>

 - Usage: `/tldr [timeframe] [question] [channel] [member] [private]`
 - `timeframe:` (Optional) The number of messages to scan
 - `question:` (Optional) Ask for specific info about the conversation
 - `channel:` (Optional) The channel to summarize messages from
 - `member:` (Optional) Target a specific member
 - `private:` (Optional) Only you can see the response

 - Checks: `Server Only`

## [p]chathelp

Get help using assistant<br/>

 - Usage: `[p]chathelp`

## [p]chat

Chat with [botname]!<br/>

Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/>

**Optional Arguments**<br/>
`--outputfile <filename>` - uploads a file with the reply instead (no spaces)<br/>
`--extract` - extracts code blocks from the reply<br/>
`--last` - resends the last message of the conversation<br/>

**Example**<br/>
`[p]chat write a python script that prints "Hello World!"`<br/>
- Including `--outputfile hello.py` will output a file containing the whole response.<br/>
- Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.<br/>
- Including `--extract` will send the code separately from the reply<br/>

 - Usage: `[p]chat <question>`
 - Aliases: `ask, escribir, razgovor, discuter, plaudern, 채팅, charlar, baterpapo, and sohbet`
 - Cooldown: `1 per 6.0 seconds`
 - Checks: `guild_only`

## [p]convostats

Check the token and message count of yourself or another user's conversation for this channel<br/>

Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel<br/>

Conversations are only stored in memory until the bot restarts or the cog reloads<br/>

 - Usage: `[p]convostats [user]`
 - Checks: `guild_only`

## [p]convocontext

Show a detailed token breakdown for your conversation context<br/>

Displays max context, fill percentage, model, token breakdown (system prompt, initial prompt, channel prompt, function schemas, conversation), message breakdown by role, and compaction count.<br/>

 - Usage: `[p]convocontext [user]`
 - Aliases: `contextinfo`
 - Checks: `guild_only`

## [p]convocompact

Compact your conversation using LLM summarization<br/>

This summarizes older messages instead of deleting them, preserving context while freeing up token space. Optionally provide a focus phrase to guide what the summary emphasizes.<br/>

**Examples**<br/>
- `[p]compact` - compact with default summarization<br/>
- `[p]compact coding decisions` - focus on coding decisions<br/>

 - Usage: `[p]convocompact [focus]`
 - Aliases: `compact`
 - Checks: `guild_only`

## [p]convoclear

Reset your conversation with the bot<br/>

This will clear all message history between you and the bot for this channel<br/>

 - Usage: `[p]convoclear`
 - Aliases: `clearconvo`
 - Checks: `guild_only`

## [p]convopop

Pop the last message from your conversation<br/>

 - Usage: `[p]convopop`
 - Checks: `bot_has_guild_permissions and guild_only`

## [p]convocopy

Copy the conversation to another channel, thread, or forum<br/>

 - Usage: `[p]convocopy <channel>`
 - Checks: `bot_has_guild_permissions and guild_only`

## [p]convoprompt

Set a system prompt for this conversation!<br/>

This allows customization of assistant behavior on a per channel basis!<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>

 - Usage: `[p]convoprompt [prompt]`
 - Checks: `guild_only`

## [p]convoshow

View the current transcript of a conversation<br/>

This is mainly here for moderation purposes<br/>

 - Usage: `[p]convoshow [user=None] [channel=operator.attrgetter('channel')]`
 - Restricted to: `GUILD_OWNER`
 - Aliases: `showconvo`
 - Checks: `guild_only`

## [p]importconvo

Import a conversation from a file<br/>

 - Usage: `[p]importconvo`
 - Restricted to: `GUILD_OWNER`
 - Checks: `guild_only`

## [p]query

Fetch related embeddings according to the current topn setting along with their scores<br/>

You can use this to fine-tune the minimum relatedness for your assistant<br/>

 - Usage: `[p]query <query>`

## [p]assistant

Setup the assistant<br/>

You will need an **[api key](https://platform.openai.com/account/api-keys)** from OpenAI to use ChatGPT and their other models.<br/>

 - Usage: `[p]assistant`
 - Restricted to: `ADMIN`
 - Aliases: `assist`
 - Checks: `guild_only`

### [p]assistant autoanswermodel

Set the model used for auto-answer<br/>

 - Usage: `[p]assistant autoanswermodel <model>`

### [p]assistant reasoning

Switch reasoning effort for o1 model between low, medium, and high<br/>

 - Usage: `[p]assistant reasoning`

### [p]assistant questionmark

Toggle whether questions need to end with **__?__**<br/>

 - Usage: `[p]assistant questionmark`

### [p]assistant functioncalls

Toggle whether GPT can call functions<br/>

 - Usage: `[p]assistant functioncalls`
 - Aliases: `usefunctions`

### [p]assistant maxretention

Set the max messages for a conversation<br/>

Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/>

Regardless of this number, the initial prompt and internal system message are always included,<br/>
this only applies to any conversation between the user and bot after that.<br/>

Set to 0 to disable conversation retention<br/>

**Note:** *actual message count may exceed the max retention during an API call*<br/>

 - Usage: `[p]assistant maxretention <max_retention>`

### [p]assistant temperature

Set the temperature for the model (0.0 - 2.0)<br/>
- Defaults is 1<br/>

Closer to 0 is more concise and accurate while closer to 2 is more imaginative<br/>

 - Usage: `[p]assistant temperature <temperature>`

### [p]assistant regexfailblock

Toggle whether failed regex blocks the assistant's reply<br/>

Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)<br/>
The bot can safely handle if this happens and will either continue on, or block the response.<br/>

 - Usage: `[p]assistant regexfailblock`

### [p]assistant prompt

Set the initial prompt for GPT to use<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>

**Placeholders**<br/>
- **botname**: [botname]<br/>
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
- **activities**: the user's current Discord activities<br/>
- **userjoindate**: the user's join date for the server<br/>
- **userjointime**: the user's join time for the server<br/>
- **uptime**: the bot's uptime<br/>
- **datetime**: full Python `datetime` string<br/>
- **modelinfo**: a multi-line summary of the active chat/embed model settings<br/>
- **prefix**: the bot's primary prefix in this guild<br/>
- **prefixes**: humanized list of all valid prefixes<br/>
- **botowner**: humanized list of bot-owner display names<br/>
- **last_interaction**: time since the user's previous message in the conversation (e.g. `5 hours, 23 minutes ago`)<br/>

 - Usage: `[p]assistant prompt [prompt]`
 - Aliases: `pre`

### [p]assistant channel

Set the main auto-response channel for the assistant<br/>

 - Usage: `[p]assistant channel [channel=None]`

### [p]assistant triggerignore

Ignore a channel or category for trigger phrases<br/>

 - Usage: `[p]assistant triggerignore <channel>`

### [p]assistant mention

Toggle whether to ping the user on replies<br/>

 - Usage: `[p]assistant mention`

### [p]assistant presence

Set the presence penalty for the model (-2.0 to 2.0)<br/>
- Defaults is 0<br/>

Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.<br/>

 - Usage: `[p]assistant presence <presence_penalty>`

### [p]assistant resetconversations

Wipe saved conversations for the assistant in this server<br/>

This will delete any and all saved conversations for the assistant.<br/>

 - Usage: `[p]assistant resetconversations <yes_or_no>`

### [p]assistant exportcsv

Export embeddings to a .csv file<br/>

**Note:** csv exports do not include the embedding values<br/>

 - Usage: `[p]assistant exportcsv`

### [p]assistant restorecog

Restore the cog from a backup<br/>

 - Usage: `[p]assistant restorecog`
 - Restricted to: `BOT_OWNER`

### [p]assistant triggerlist

View configured trigger phrases<br/>

 - Usage: `[p]assistant triggerlist`

### [p]assistant relatedness

Set the minimum relatedness an embedding must be to include with the prompt<br/>

Relatedness threshold between 0 and 1 to include in embeddings during chat<br/>

Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison<br/>

**Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be *too* strict or there wont be any results.<br/>

 - Usage: `[p]assistant relatedness <mimimum_relatedness>`

### [p]assistant resetglobalembeddings

Wipe saved embeddings for all servers<br/>

This will delete any and all saved embedding training data for the assistant.<br/>

 - Usage: `[p]assistant resetglobalembeddings <yes_or_no>`
 - Restricted to: `BOT_OWNER`

### [p]assistant view

View current settings<br/>

To send in current channel, use `[p]assistant view false`<br/>

 - Usage: `[p]assistant view [private=False]`
 - Aliases: `v`

### [p]assistant exportexcel

Export embeddings to an .xlsx file<br/>

**Note:** csv exports do not include the embedding values<br/>

 - Usage: `[p]assistant exportexcel`

### [p]assistant blacklist

Add/Remove items from the blacklist<br/>

`channel_role_member` can be a member, role, channel, or category channel<br/>

 - Usage: `[p]assistant blacklist <channel_role_member>`

### [p]assistant channelpromptshow

Show the channel specific system prompt<br/>

 - Usage: `[p]assistant channelpromptshow [channel=operator.attrgetter('channel')]`

### [p]assistant listen

Toggle this channel as an auto-response channel<br/>

 - Usage: `[p]assistant listen`

### [p]assistant listentobots

Toggle whether the assistant listens to other bots<br/>

**NOT RECOMMENDED FOR PUBLIC BOTS!**<br/>

 - Usage: `[p]assistant listentobots`
 - Restricted to: `BOT_OWNER`
 - Aliases: `botlisten and ignorebots`

### [p]assistant maxresponsetokens

Set the max response tokens the model can respond with<br/>

Set to 0 for response tokens to be dynamic<br/>

 - Usage: `[p]assistant maxresponsetokens <max_tokens>`

### [p]assistant maxtokens

Set maximum tokens a convo can consume<br/>

Set to 0 for dynamic token usage<br/>

**Tips**<br/>
- Max tokens are a soft cap, sometimes messages can be a little over<br/>
- If you set max tokens too high the cog will auto-adjust to 100 less than the models natural cap<br/>
- Ideally set max to 500 less than that models maximum, to allow adequate responses<br/>

Using more than the model can handle will raise exceptions.<br/>

 - Usage: `[p]assistant maxtokens <max_tokens>`

### [p]assistant importcsv

Import embeddings to use with the assistant<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>

This will read excel files too<br/>

 - Usage: `[p]assistant importcsv <overwrite>`

### [p]assistant verbosity

Switch verbosity level for gpt-5 model between low, medium, and high<br/>

This setting is exclusive to the gpt-5 model and affects how detailed the model's responses are.<br/>

 - Usage: `[p]assistant verbosity`

### [p]assistant usage

View the token usage stats for this server<br/>

 - Usage: `[p]assistant usage`

### [p]assistant trigger

Toggle the trigger word feature on or off<br/>

 - Usage: `[p]assistant trigger`

### [p]assistant resetembeddings

Wipe saved embeddings for the assistant<br/>

This will delete any and all saved embedding training data for the assistant.<br/>

 - Usage: `[p]assistant resetembeddings <yes_or_no>`

### [p]assistant autoanswerthreshold

Set the auto-answer threshold for the bot<br/>

 - Usage: `[p]assistant autoanswerthreshold <threshold>`

### [p]assistant openaikey

Set your OpenAI key<br/>

 - Usage: `[p]assistant openaikey`
 - Aliases: `key`

### [p]assistant embedmodel

Set the OpenAI Embedding model to use<br/>

 - Usage: `[p]assistant embedmodel [model=None]`

### [p]assistant braveapikey

Enables use of the `search_web_brave` function<br/>

Get your API key **[Here](https://brave.com/search/api/)**<br/>

 - Usage: `[p]assistant braveapikey`
 - Restricted to: `BOT_OWNER`
 - Aliases: `brave`

### [p]assistant timezone

Set the timezone used for prompt placeholders<br/>

 - Usage: `[p]assistant timezone <timezone>`

### [p]assistant model

Set the OpenAI model to use<br/>

 - Usage: `[p]assistant model [model=None]`

### [p]assistant importexcel

Import embeddings from an .xlsx file<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>

 - Usage: `[p]assistant importexcel <overwrite>`

### [p]assistant refreshembeds

Refresh embedding weights<br/>

*This command can be used when changing the embedding model*<br/>

Embeddings that were created using OpenAI cannot be use with the self-hosted model and vice versa<br/>

 - Usage: `[p]assistant refreshembeds`
 - Aliases: `refreshembeddings, syncembeds, and syncembeddings`

### [p]assistant exportjson

Export embeddings to a json file<br/>

 - Usage: `[p]assistant exportjson`

### [p]assistant planner

Add/Remove items from the planner list, or view current planners.<br/>

Users/roles in the planner list can use the `think_and_plan` tool for complex task breakdown.<br/>

If the planner list is empty, everyone can use the planning tool.<br/>
If the planner list has entries, only those users/roles can use it.<br/>

`role_or_member` can be a member or role. Omit to view the current list.<br/>

 - Usage: `[p]assistant planner [role_or_member]`
 - Aliases: `planners`

### [p]assistant triggerphrase

Add or remove a trigger phrase (supports regex)<br/>

The bot will respond to messages containing this phrase.<br/>
Phrases are case-insensitive regex patterns.<br/>

**Examples**<br/>
- `hello` - matches messages containing "hello"<br/>
- `\bhelp\b` - matches the word "help" (word boundary)<br/>
- `bad.*word` - matches "bad" followed by any characters then "word"<br/>

 - Usage: `[p]assistant triggerphrase <phrase>`

### [p]assistant collab

Toggle collaborative conversations<br/>

Multiple people speaking in a channel will be treated as a single conversation.<br/>

 - Usage: `[p]assistant collab`

### [p]assistant questionmode

Toggle question mode<br/>

If question mode is on, embeddings will only be sourced during the first message of a conversation and messages that end in **?**<br/>

 - Usage: `[p]assistant questionmode`

### [p]assistant regexblacklist

Remove certain words/phrases in the bot's responses<br/>

 - Usage: `[p]assistant regexblacklist <regex>`

### [p]assistant wipecog

Wipe all settings and data for entire cog<br/>

 - Usage: `[p]assistant wipecog <confirm>`
 - Restricted to: `BOT_OWNER`

### [p]assistant resolution

Switch vision resolution between high and low for relevant GPT-4-Turbo models<br/>

 - Usage: `[p]assistant resolution`

### [p]assistant resetglobalconversations

Wipe saved conversations for the assistant in all servers<br/>

This will delete any and all saved conversations for the assistant.<br/>

 - Usage: `[p]assistant resetglobalconversations <yes_or_no>`
 - Restricted to: `BOT_OWNER`

### [p]assistant channelprompt

Set a channel specific system prompt<br/>

 - Usage: `[p]assistant channelprompt [channel=operator.attrgetter('channel')] [system_prompt]`

### [p]assistant toggledraw

Toggle the draw command on or off<br/>

 - Usage: `[p]assistant toggledraw`
 - Aliases: `drawtoggle`

### [p]assistant autoanswerignore

Ignore a channel for auto-answer<br/>

 - Usage: `[p]assistant autoanswerignore <channel>`

### [p]assistant autoanswer

Toggle the auto-answer feature on or off<br/>

 - Usage: `[p]assistant autoanswer`

### [p]assistant resetusage

Reset the token usage stats for this server<br/>

 - Usage: `[p]assistant resetusage`

### [p]assistant toggle

Toggle the assistant on or off<br/>

 - Usage: `[p]assistant toggle`

### [p]assistant system

Set the system prompt for GPT to use<br/>

Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.<br/>

**Placeholders**<br/>
- **botname**: [botname]<br/>
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
- **activities**: the user's current Discord activities<br/>
- **userjoindate**: the user's join date for the server<br/>
- **userjointime**: the user's join time for the server<br/>
- **uptime**: the bot's uptime<br/>
- **datetime**: full Python `datetime` string<br/>
- **modelinfo**: a multi-line summary of the active chat/embed model settings<br/>
- **prefix**: the bot's primary prefix in this guild<br/>
- **prefixes**: humanized list of all valid prefixes<br/>
- **botowner**: humanized list of bot-owner display names<br/>
- **last_interaction**: time since the user's previous message in the conversation (e.g. `5 hours, 23 minutes ago`)<br/>

 - Usage: `[p]assistant system [system_prompt]`
 - Aliases: `sys`

### [p]assistant seed

Make the model more deterministic by setting a seed for the model.<br/>
- Default is None<br/>

If specified, the system will make a best effort to sample deterministically, such that repeated requests with the same seed and parameters should return the same result.<br/>

 - Usage: `[p]assistant seed [seed=None]`

### [p]assistant mentionrespond

Toggle whether the bot responds to mentions in any channel<br/>

 - Usage: `[p]assistant mentionrespond`

### [p]assistant persist

Toggle persistent conversations<br/>

 - Usage: `[p]assistant persist`
 - Restricted to: `BOT_OWNER`

### [p]assistant endpointoverride

Override the OpenAI endpoint<br/>

**Notes**<br/>
- Using a custom endpoint is not supported!<br/>
- Using an endpoing override will negate model settings like temperature and custom functions<br/>

 - Usage: `[p]assistant endpointoverride [endpoint=None]`
 - Restricted to: `BOT_OWNER`

### [p]assistant maxtime

Set the conversation expiration time<br/>

Regardless of this number, the initial prompt and internal system message are always included,<br/>
this only applies to any conversation between the user and bot after that.<br/>

Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded<br/>

 - Usage: `[p]assistant maxtime <retention_seconds>`

### [p]assistant maxrecursion

Set the maximum function calls allowed in a row<br/>

This sets how many times the model can call functions in a row<br/>

 - Usage: `[p]assistant maxrecursion <recursion>`

### [p]assistant frequency

Set the frequency penalty for the model (-2.0 to 2.0)<br/>
- Defaults is 0<br/>

Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.<br/>

 - Usage: `[p]assistant frequency <frequency_penalty>`

### [p]assistant override

Override settings for specific roles<br/>

**NOTE**<br/>
If a user has two roles with override settings, override associated with the higher role will be used.<br/>

 - Usage: `[p]assistant override`

#### [p]assistant override model

Assign a role to use a model<br/>

*Specify same role and model to remove the override*<br/>

 - Usage: `[p]assistant override model <model> <role>`

#### [p]assistant override maxretention

Assign a max message retention override to a role<br/>

*Specify same role and retention amount to remove the override*<br/>

 - Usage: `[p]assistant override maxretention <max_retention> <role>`

#### [p]assistant override maxresponsetokens

Assign a max response token override to a role<br/>

Set to 0 for response tokens to be dynamic<br/>

*Specify same role and token count to remove the override*<br/>

 - Usage: `[p]assistant override maxresponsetokens <max_tokens> <role>`

#### [p]assistant override maxtokens

Assign a max token override to a role<br/>

*Specify same role and token count to remove the override*<br/>

 - Usage: `[p]assistant override maxtokens <max_tokens> <role>`

#### [p]assistant override maxtime

Assign a max retention time override to a role<br/>

*Specify same role and time to remove the override*<br/>

 - Usage: `[p]assistant override maxtime <retention_seconds> <role>`

### [p]assistant minlength

set min character length for questions<br/>

Set to 0 to respond to anything<br/>

 - Usage: `[p]assistant minlength <min_question_length>`

### [p]assistant topn

Set the embedding inclusion amout<br/>

Top N is the amount of retrieved embeddings to include in the grounded RAG context block before the live user query<br/>

 - Usage: `[p]assistant topn <top_n>`

### [p]assistant backupcog

Take a backup of the cog<br/>

- This does not backup conversation data<br/>

 - Usage: `[p]assistant backupcog`
 - Restricted to: `BOT_OWNER`

### [p]assistant importjson

Import embeddings to use with the assistant<br/>

Args:<br/>
    overwrite (bool): overwrite embeddings with existing entry names<br/>

 - Usage: `[p]assistant importjson <overwrite>`

### [p]assistant triggerprompt

Set the prompt to use when a trigger phrase is matched<br/>

This prompt will be appended to the initial prompt when the bot responds to a triggered message.<br/>

**Placeholders**<br/>
- **botname**: [botname]<br/>
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
- **activities**: the user's current Discord activities<br/>
- **userjoindate**: the user's join date for the server<br/>
- **userjointime**: the user's join time for the server<br/>
- **uptime**: the bot's uptime<br/>
- **datetime**: full Python `datetime` string<br/>
- **modelinfo**: a multi-line summary of the active chat/embed model settings<br/>
- **prefix**: the bot's primary prefix in this guild<br/>
- **prefixes**: humanized list of all valid prefixes<br/>
- **botowner**: humanized list of bot-owner display names<br/>
- **last_interaction**: time since the user's previous message in the conversation (e.g. `5 hours, 23 minutes ago`)<br/>

 - Usage: `[p]assistant triggerprompt [prompt]`

### [p]assistant sysoverride

Toggle allowing per-conversation system prompt overriding<br/>

 - Usage: `[p]assistant sysoverride`

### [p]assistant compaction

Toggle LLM-based conversation compaction on or off<br/>

When enabled, conversations that exceed the token limit are summarized using an LLM instead of blindly dropping old messages.<br/>

 - Usage: `[p]assistant compaction`

### [p]assistant compactionmodel

Set the model used for compaction (leave blank to use the chat model)<br/>

 - Usage: `[p]assistant compactionmodel [model]`

### [p]assistant compactionthreshold

Set the token threshold at which compaction triggers<br/>

When set, the bot will proactively compact conversations once they exceed this many tokens, even if the model's context window is larger.<br/>

Set to **0** to only compact when hitting the model's max token limit.<br/>

 - Usage: `[p]assistant compactionthreshold [token_limit]`

### [p]assistant openroutercache

Configure OpenRouter response & prompt caching.<br/>

Only takes effect when an OpenRouter endpoint override is configured.<br/>

 - Usage: `[p]assistant openroutercache`
 - Aliases: `orcache`
 - Restricted to: `ADMIN`

### [p]assistant openroutercache enable

Enable OpenRouter response caching (Mode A - caches the entire response at the OpenRouter network layer).<br/>

 - Usage: `[p]assistant openroutercache enable`

### [p]assistant openroutercache disable

Disable OpenRouter response caching.<br/>

 - Usage: `[p]assistant openroutercache disable`

### [p]assistant openroutercache ttl

Set the OpenRouter response cache TTL in seconds (1–86400).<br/>

 - Usage: `[p]assistant openroutercache ttl <seconds>`

### [p]assistant openroutercache promptcache

Set the OpenRouter provider prompt cache TTL.<br/>

Choices: `off`, `5m`, `1h`. Applies to Anthropic / Gemini / Qwen models routed via OpenRouter.<br/>

 - Usage: `[p]assistant openroutercache promptcache <mode>`

## [p]floatingcontext (Hybrid Command)

Open the floating context block manager.<br/>

Lets admins toggle which variables are appended to the trailing `[Current Context]` payload-only user message that the bot sends after conversation history. Because that message rides after the cached prefix, putting dynamic (per-request) values here keeps the prompt prefix stable across requests so provider-side prompt caching can hit. **Default: OFF for everything - fresh installs start with a blank slate so the admin picks exactly which variables to surface.**<br/>

Prompt-template substitution is unchanged - every variable (stable or dynamic) still substitutes inline whenever its `{placeholder}` appears in a prompt template. The floating context menu is independent of substitution: it controls only what appears in the floating block.<br/>

Each included variable is rendered as a self-encapsulated sentence in the floating block (e.g. `"The current date is May 16, 2026."`), so admins do **not** need to author prompts that reference the variable - toggling it on in the menu is enough for the model to receive its value.<br/>

Categories include: **Dynamic - Time & Date / Balance / Activities / Session**, **Stable - Bot / Server / Channel / Bank / User Info / System**, and one **Custom - &lt;CogName&gt;** category per 3rd-party context-variable provider.<br/>

The "Dynamic" vs "Stable" labelling is purely informational: **stable variables are cache-safe** (unchanging per-request, e.g. user profile, bot info) while **dynamic variables are cache-unsafe** (per-request or per-user, e.g. current time, balance). If you want to maximize prompt-prefix cache hits, avoid including dynamic-variable placeholders in your prompt templates; the ⚠️ Cache Warning embed field in `[p]assistant view` lists which prompt templates use dynamic placeholders.<br/>

 - Usage: `[p]floatingcontext`
 - Slash Usage: `/floatingcontext`
 - Aliases: `floatcontext`, `fctx`
 - Restricted to: `ADMIN`
 - Checks: `guild_only`

## [p]cacheinfo (Hybrid Command)

Show prompt-cache stats from the most recent API call.<br/>

Reports cached / total prompt tokens, cache-write tokens, and the model that served the request.<br/>

Works with OpenAI direct (automatic caching), OpenRouter response caching (Mode A), and OpenRouter provider prompt caching (Mode B for Anthropic / Gemini / Qwen).<br/>

 - Usage: `[p]cacheinfo`
 - Slash Usage: `/cacheinfo`
 - Restricted to: `ADMIN`
 - Checks: `guild_only`

## [p]embeddings (Hybrid Command)

Manage embeddings for training<br/>

Embeddings are admin-curated reference entries used to optimize training of the assistant and minimize token usage.<br/>

By using this the bot can store vast amounts of contextual information without going over the token limit.<br/>

**Note**<br/>
You can enter a search query with this command to bring up the menu and go directly to that embedding selection.<br/>

 - Usage: `[p]embeddings [query]`
 - Slash Usage: `/embeddings [query]`
 - Restricted to: `ADMIN`
 - Aliases: `emenu`
 - Checks: `guild_only`

## [p]customfunctions (Hybrid Command)

Add custom function calls for Assistant to use<br/>

**READ**<br/>
- [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)<br/>
- [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)<br/>
- [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)<br/>

The following objects are passed by default as keyword arguments.<br/>
- **user**: the user currently chatting with the bot (discord.Member)<br/>
- **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)<br/>
- **guild**: current guild (discord.Guild)<br/>
- **bot**: the bot object (Red)<br/>
- **conf**: the config model for Assistant (GuildSettings)<br/>
- All functions **MUST** include `*args, **kwargs` in the params and return a string<br/>
```python
# Can be either sync or async
async def func(*args, **kwargs) -> str:
```
Only bot owner can manage this, guild owners can see descriptions but not code<br/>

 - Usage: `[p]customfunctions [function_name=None]`
 - Slash Usage: `/customfunctions [function_name=None]`
 - Aliases: `customfunction and customfunc`
 - Checks: `guild_only`

## [p]listfunctions (Hybrid Command)

List all available functions and their enabled/disabled status<br/>

This provides a quick overview of all custom functions and 3rd party<br/>
registered functions without having to navigate through the full menu.<br/>

 - Usage: `[p]listfunctions`
 - Slash Usage: `/listfunctions`
 - Restricted to: `ADMIN`
 - Aliases: `listfuncs and funclist`
 - Checks: `guild_only`

## [p]togglefunctions (Hybrid Command)

Enable or disable multiple functions at once<br/>

**Arguments**<br/>
- `enable`: True to enable, False to disable. Omit to toggle current state.<br/>
- `functions`: Comma-separated list of function names, or "all" to affect all functions<br/>

**Examples**<br/>
- `[p]togglefunctions get_time, get_weather` - Toggle these functions<br/>
- `[p]togglefunctions True all` - Enable all functions<br/>
- `[p]togglefunctions False get_time, get_weather` - Disable specific functions<br/>

 - Usage: `[p]togglefunctions <enable> <functions>`
 - Slash Usage: `/togglefunctions <enable> <functions>`
 - Restricted to: `ADMIN`
 - Aliases: `togglefuncs`
 - Checks: `guild_only`

