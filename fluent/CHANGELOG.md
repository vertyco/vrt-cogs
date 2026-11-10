# Fluent Changelog

## v2.8.0

- **Feature**: Translate buttons now work on Components V2 messages. A click replies with a copy of the message whose text blocks are translated; pictures, separators and other buttons are kept.
- **Fix**: A bot restart or cog reload no longer wipes the body of a Components V2 message that has translate buttons. Fluent only edits such a message when its buttons need to change, and keeps the rest of it.
- **Change**: Translate buttons have fixed ids, so they keep working after a restart.
- **Change**: Requires Red 3.5.21 or newer.

## v2.7.1

- **Change**: OpenAI translations now use the gpt-6-luna model instead of gpt-5-nano.
