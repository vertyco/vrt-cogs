# Assistant Help

Simple discord assistant using ChatGPT

# assistant

- Usage: `[p]assistant `
- Restricted to: `GUILD_OWNER`
- Aliases: `ass`

Setup the assistant

## assistant openaikey

- Usage: `[p]assistant openaikey `
- Aliases: `key`

Set your OpenAI key

## assistant view

- Usage: `[p]assistant view `

View current settings

## assistant prompt

- Usage: `[p]assistant prompt [prompt] `
- Aliases: `pre`

Set the initial prompt for GPT to use

## assistant channel

- Usage: `[p]assistant channel <channel> `

Set the channel for the assistant

## assistant questionmark

- Usage: `[p]assistant questionmark `

Toggle whether questions need to end with a question mark to be answered

## assistant maxretention

- Usage: `[p]assistant maxretention <max_retention> `

Set the max messages for a conversation<br/><br/>Regardless of this number, the initial prompt and internal system
message are always included,<br/>this only applies to any conversation between the user and bot after that.<br/><br/>Set
to 0 to disable conversation retention

