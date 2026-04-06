# Assistant Changelog

## v7.7.0

### Conversation compaction

Conversations that exceed the token limit are now intelligently summarized using an LLM instead of blindly dropping old messages. This preserves important context while freeing up token space.

- LLM-based summarization replaces blind message truncation when context overflows
- Tool-call/result pairs are kept together during degradation to prevent orphaned messages
- Pre-compaction memory flush extracts user facts before summarizing, storing them as persistent memories
- Configurable compaction model (use a cheaper model for summarization)
- Configurable token threshold to trigger compaction before hitting the model's max context
- Compaction can be toggled on/off per server (`[p]assistant compaction`)

### New user commands

- `[p]convocontext` - detailed token breakdown showing context fill %, token usage by category, message counts by role, compaction history, and stored facts
- `[p]convocompact` - manually compact a conversation with optional focus phrase to guide the summary

### Admin commands

- `[p]assistant compaction` - toggle LLM compaction on/off
- `[p]assistant compactionmodel` - set the model used for compaction
- `[p]assistant compactionthreshold` - set the token threshold for proactive compaction
- `[p]assistant memoryflush` - toggle pre-compaction memory flush

## v7.0.0

### Embeddings moved to persistent storage

Embeddings are now stored on disk separately from the config file instead of being saved in JSON. This reduces config file size and improves performance.

- Embeddings are stored in ChromaDB at `<cog_data>/chromadb/`
- Existing embeddings are automatically migrated on first load
- No action required from users; migration happens in the background

### Per-tool permission requirements

Functions registered by third-party cogs can now declare required Discord permissions. Users must have these permissions to use the function.

### Reminder system

The assistant can now set reminders for users via function calling.

- Create, cancel, and list reminders through natural conversation
- Reminders persist across bot restarts and are rescheduled on cog load
- Supports DM or channel reminders
- Past-due reminders fire immediately on startup

### User memory

The assistant can remember facts about users across conversations.

- Remembers, recalls, and forgets facts about individual users per-guild
- Memory is injected into the system prompt for personalized responses
- Users can ask to forget specific facts

### Bug fixes and improvements

- Improved memory tool responsiveness (search_memories, edit_memory, list_memories)
- Auto-answer now uses the new embedding system
