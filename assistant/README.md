# Assistant Help

Set up a helpful assistant for your Discord server, powered by the ChatGPT API

# chat
 - Usage: `[p]chat <question> `
 - Cooldown: `1 per 6.0 seconds`
 - Checks: `server_only`

Ask [botname] a question!

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
 - Restricted to: `ADMIN`
 - Aliases: `ass`
 - Checks: `server_only`

Setup the assistant<br/><br/>You will need an api key to use the assistant. https://platform.openai.com/account/api-keys

## assistant mention
 - Usage: `[p]assistant mention `

Toggle whether to ping the user on replies

## assistant system
 - Usage: `[p]assistant system [system_prompt] `
 - Aliases: `sys`

Set the system prompt for GPT to use<br/><br/>**Note**<br/>The current GPT-3.5-Turbo model doesn't really listen to the system prompt very well.<br/><br/>**Tips**<br/>You can use the following placeholders in your prompt for real-time info<br/>To use a place holder simply format your prompt as "some {placeholder} with text"<br/>botname - The bots display name<br/>timestamp - the current time in Discord's timestamp format<br/>day - the current day of the week<br/>date - todays date (Month, Day, Year)<br/>time - current time in 12hr format (HH:MM AM/PM Timezone)<br/>members - current member count of the server<br/>user - the current user asking the question<br/>roles - the names of the user's roles<br/>avatar - the user's avatar url<br/>owner - the owner of the server<br/>servercreated - the create date/time of the server<br/>server - the name of the server<br/>messages - count of messages between the user and bot<br/>tokens - the token count of the current conversation<br/>retention - max retention number<br/>retentiontime - max retention time seconds

## assistant resetembeddings
 - Usage: `[p]assistant resetembeddings <yes_or_no> `

Wipe saved embeddings for the assistant<br/><br/>This will delete any and all saved embedding training data for the assistant.

## assistant channel
 - Usage: `[p]assistant channel <channel> `

Set the channel for the assistant

## assistant relatedness
 - Usage: `[p]assistant relatedness <mimimum_relatedness> `

Set the minimum relatedness an embedding must be to include with the prompt<br/><br/>Relatedness threshold between 0 and 1 to include in embeddings during chat<br/><br/>Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison<br/><br/>**Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be *too* strict or there wont be any results.

## assistant maxretention
 - Usage: `[p]assistant maxretention <max_retention> `

Set the max messages for a conversation<br/><br/>Conversation retention is cached and gets reset when the bot restarts or the cog reloads.<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to disable conversation retention

## assistant openaikey
 - Usage: `[p]assistant openaikey `
 - Aliases: `key`

Set your OpenAI key

## assistant prompt
 - Usage: `[p]assistant prompt [prompt] `
 - Aliases: `pre`

Set the initial prompt for GPT to use<br/><br/>**Tips**<br/>You can use the following placeholders in your prompt for real-time info<br/>To use a place holder simply format your prompt as "some {placeholder} with text"<br/>botname - The bots display name<br/>timestamp - the current time in Discord's timestamp format<br/>day - the current day of the week<br/>date - todays date (Month, Day, Year)<br/>time - current time in 12hr format (HH:MM AM/PM Timezone)<br/>members - current member count of the server<br/>user - the current user asking the question<br/>roles - the names of the user's roles<br/>avatar - the user's avatar url<br/>owner - the owner of the server<br/>servercreated - the create date/time of the server<br/>server - the name of the server<br/>messages - count of messages between the user and bot<br/>tokens - the token count of the current conversation<br/>retention - max retention number<br/>retentiontime - max retention time seconds

## assistant maxtime
 - Usage: `[p]assistant maxtime <retention_time> `

Set the conversation expiration time<br/><br/>Regardless of this number, the initial prompt and internal system message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded

## assistant maxtokens
 - Usage: `[p]assistant maxtokens <max_tokens> `

Set the max tokens the model can use at once<br/><br/>For GPT3.5 use 4000 or less.<br/>For GPT4 user 8000 or less (if 8k version).<br/><br/>Using more than the model can handle will raise exceptions.

## assistant dynamicembedding
 - Usage: `[p]assistant dynamicembedding `

Toggle whether embeddings are dynamic<br/><br/>Dynamic embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.<br/>When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly<br/><br/>Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings.<br/>Turning this off will instead append the embedding context in front of the user's question, thus retaining all pulled embeddings during the conversation.

## assistant questionmark
 - Usage: `[p]assistant questionmark `

Toggle whether questions need to end with **__?__**

## assistant toggle
 - Usage: `[p]assistant toggle `

Toggle the assistant on or off

## assistant minlength
 - Usage: `[p]assistant minlength <min_question_length> `

set min character length for questions<br/><br/>Set to 0 to respond to anything

## assistant model
 - Usage: `[p]assistant model <model> `

Set the GPT model to use<br/><br/>Valid models are gpt-3.5-turbo, gpt-4, and gpt-4-32k

## assistant topn
 - Usage: `[p]assistant topn <top_n> `

Set the embedding inclusion about<br/><br/>Top N is the amount of embeddings to include with the initial prompt

## assistant embeddingtest
 - Usage: `[p]assistant embeddingtest <question> `
 - Aliases: `etest`

Fetch related embeddings according to the current settings along with their scores<br/><br/>You can use this to fine-tune the minimum relatedness for your assistant

## assistant train
 - Usage: `[p]assistant train <channels> `

Automatically create embedding data to train your assistant<br/><br/>**How to Use**<br/>Include channels that give helpful info about your server, NOT normal chat channels.<br/>The bot will scan all pinned messages in addition to the most recent 50 messages.<br/>The idea is to have the bot compile the information, condense it and provide a usable training embeddings for your Q&A channel.<br/><br/>**Note:** This just meant to get you headed in the right direction, creating quality training data takes trial and error.

## assistant embeddings
 - Usage: `[p]assistant embeddings `
 - Aliases: `embed`

Manage embeddings for training<br/><br/>Embeddings are used to optimize training of the assistant and minimize token usage.<br/><br/>By using this the bot can store vast amounts of contextual information without going over the token limit.

## assistant view
 - Usage: `[p]assistant view [private=True] `

View current settings<br/><br/>To send in current channel, use [p]assistant view false

