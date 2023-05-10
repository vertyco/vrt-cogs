# Assistant Help

Set up a helpful assistant for your Discord server, powered by the ChatGPT API

# chat
 - Usage: `[p]chat <question> `
 - Cooldown: `1 per 6.0 seconds`
 - Checks: `server_only`

Ask Autto a question!

# convostats
 - Usage: `[p]convostats [user] `
 - Checks: `server_only`

Check the token and message count of yourself or another user's conversation

# clearconvo
 - Usage: `[p]clearconvo `
 - Checks: `server_only`

Reset your conversation

# assistant
 - Usage: `[p]assistant `
 - Restricted to: `GUILD_OWNER`
 - Aliases: `ass`
 - Checks: `server_only`

Setup the assistant<br/><br/>You will need an api key to use the assistant. https://platform.openai.com/account/api-keys

## assistant channel
 - Usage: `[p]assistant channel <channel> `

Set the channel for the assistant

## assistant maxretention
 - Usage: `[p]assistant maxretention <max_retention> `

Set the max messages for a conversation<br/><br/>Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to disable conversation retention

## assistant maxtokens
 - Usage: `[p]assistant maxtokens <max_tokens> `

Set the max tokens the model can use at once<br/><br/>For GPT3.5 use 4000 or less.<br/>For GPT4 user 8000 or less (if 8k version).<br/><br/>Using more than the model can handle will raise exceptions.

## assistant model
 - Usage: `[p]assistant model <model> `

Set the GPT model to use<br/><br/>Valid models are gpt-3.5-turbo, gpt-4, and gpt-4-32k

## assistant train
 - Usage: `[p]assistant train <channels> `

Automatically create a training prompt for your server<br/><br/>**How to Use**<br/>Include channels that give helpful info about your server, NOT normal chat channels.<br/>The bot will scan all pinned messages in addition to the most recent 50 messages.<br/>The idea is to have the bot compile the information, condense it and provide a usable training prompt for your Q&A channel.<br/><br/>**Note:** This just meant to get you headed in the right direction, creating a perfect training prompt takes trial and error.

## assistant toggle
 - Usage: `[p]assistant toggle `

Toggle the assistant on or off

## assistant mention
 - Usage: `[p]assistant mention `

Toggle whether to ping the user on replies

## assistant maxtime
 - Usage: `[p]assistant maxtime <retention_time> `

Set the conversation expiration time<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded

## assistant view
 - Usage: `[p]assistant view [private=True] `

View current settings<br/><br/>To send in current channel, use [p]assistant view false

## assistant prompt
 - Usage: `[p]assistant prompt [prompt] `
 - Aliases: `pre`

Set the initial prompt for GPT to use<br/><br/>**Tips**<br/>You can use the following placeholders in your prompt for real-time info<br/>To use a place holder simply format your prompt as "some {placeholder} with text"<br/>botname - The bots display name<br/>timestamp - the current time in Discord's timestamp format<br/>date - todays date (Month, Day, Year)<br/>time - current time in 12hr format (HH:MM AM/PM Timezone)<br/>members - current member count of the server<br/>user - the current user asking the question<br/>roles - the names of the user's roles<br/>avatar - the user's avatar url<br/>owner - the owner of the server<br/>servercreated - the create date/time of the server<br/>server - the name of the server<br/>messages - count of messages between the user and bot<br/>tokens - the token count of the current conversation<br/>retention - max retention number<br/>retentiontime - max retention time seconds

## assistant questionmark
 - Usage: `[p]assistant questionmark `

Toggle whether questions need to end with **__?__**

## assistant openaikey
 - Usage: `[p]assistant openaikey `
 - Aliases: `key`

Set your OpenAI key

## assistant system
 - Usage: `[p]assistant system [system_prompt] `
 - Aliases: `sys`

Set the system prompt for GPT to use<br/><br/>**Note**<br/>The current GPT-3.5-Turbo model doesn't really listen to the system prompt very well.<br/><br/>**Tips**<br/>You can use the following placeholders in your prompt for real-time info<br/>To use a place holder simply format your prompt as "some {placeholder} with text"<br/>botname - The bots display name<br/>timestamp - the current time in Discord's timestamp format<br/>date - todays date (Month, Day, Year)<br/>time - current time in 12hr format (HH:MM AM/PM Timezone)<br/>members - current member count of the server<br/>user - the current user asking the question<br/>roles - the names of the user's roles<br/>avatar - the user's avatar url<br/>owner - the owner of the server<br/>servercreated - the create date/time of the server<br/>server - the name of the server<br/>messages - count of messages between the user and bot<br/>tokens - the token count of the current conversation<br/>retention - max retention number<br/>retentiontime - max retention time seconds

## assistant minlength
 - Usage: `[p]assistant minlength <min_question_length> `

set min character length for questions<br/><br/>Set to 0 to respond to anything

