# Assistant Changelog

## v8.18.2

- **Fix**: `[p]assistant backup` no longer wipes live conversations. It excluded conversation data by clearing `self.db.conversations` on the real in-memory store; with per-file persistence that also caused the on-disk files to be overwritten on next use. Now excludes conversations from the dump non-destructively via `model_dump_json(exclude=...)`.

## v8.18.1

- **Fix**: `save_conversation` crashed with `TypeError: model_dump() got multiple values for keyword argument 'mode'` because `AssistantBaseModel.model_dump` already forces `mode="json"`. Dropped the redundant arg so per-turn conversation saves work.

## v8.18.0

- **New**: Conversations now persist as one JSON file per conversation on disk (`<cog_data_path>/conversations/<key>.json`) instead of inside the single Config `db` blob. This eliminates the multi-second event-loop freeze that occurred on every save as the conversation store grew. Legacy in-blob conversations are backed up to `conversations_backup_<ts>.json` and dropped from the blob on first load after updating.

## v8.17.1

- **Fix**: Tool-result debug logging now prints `images: N image(s)` for the `images` key instead of dumping the full list of attachment URLs.

## v8.17.0

- **New**: Tool results that return an `images` list are now injected as a user vision message after the tool batch, so functions (e.g. `fetch_channel_history`) can show the model screenshots. Injected into the in-flight payload only, not persisted to conversation history (Discord CDN URLs expire). Added `build_tool_image_message` helper.

## v8.16.1

- **Fix**: `[p]convostats` rendered misaligned rows: the `Expired` field showed the model, `Model` showed the retention cap, and `Model`/`Context` collapsed onto one line. Realigned the `.format()` args and added the missing newline so `Messages`, `Expired`, and `Model` each show their own value.

## v8.16.0

- **New**: Role Prompts. Bind a system prompt to a Discord role via `[p]assistant override roleprompt`. Per-role append or replace mode (`rolepromptreplace`), and a global stack vs highest-role-only toggle (`rolepromptstack`). Role prompts support variable placeholders and are included in the cache-safe dynamic-variable warning. View them with `rolepromptshow`.
- **Fix**: Bound the regex-guard multiprocessing pool (`processes=2`, `maxtasksperchild=100`) so worker RSS no longer ratchets on large regex inputs, and force-terminate it on cog unload so a wedged regex can't block reload.

## v8.15.0

- **New**: `[p]convostats` now renders a colored-square context-window map (🟩 prompts, 🟦 function schemas, 🟨 skills index, 🟥 conversation, ⬛ free) like a `/context` view, with a token legend. Native emoji squares so it renders on desktop and mobile without ANSI.
- **Change**: merged `[p]convocontext` into `[p]convostats`. `convostats` shows the compact stats + bar; `convostats full` (or the `convocontext`/`contextinfo` aliases) adds the detailed token + message breakdown. Append a member to view theirs (e.g. `convostats full @user`).
- **New**: both views account for the Skills index appended to the system prompt - its tokens are folded into the context total/overhead and shown with a permission-filtered skill count. Previously the skill index was live context but invisible in the breakdown.
- **Change**: `MAX_SKILL_BODY` lowered from 8000 to 4000 chars. This matches the skill edit modal's TextInput cap and the Components V2 displayable-text cap (both 4000 and not raisable), so every skill body now stays fully editable in the modal and renderable in a single Components V2 message. Bodies over 4000 were previously creatable but silently truncated when edited.

## v8.14.0

- **New**: RPC handlers for skill management over Red's localhost JSON-RPC, mirroring the existing prompt/embedding handlers: `rpc_list_skills`, `rpc_add_skill` (create or overwrite an active skill via the same `bake_skill` path as the add command), and `rpc_delete_skill`. Lets ops tooling curate a guild's skills out of band without a Discord command.

## v8.13.0

- **New**: Skills system. Named procedure packs the model loads on demand via a `load_skill` tool, with a lightweight name+description index appended to the end of the system prompt (cache-stable; full bodies only enter context as tool results, so the prompt prefix stays byte-identical for provider prompt caching).
- **New**: The model can propose new skills, or fixes to existing ones, via a `propose_skill` tool when staff corrects it. Proposals post to an optional dedicated review channel (`[p]assistant skills channel`), falling back to the current chat channel when none is set, with optional role pings (`[p]assistant skills pingrole`) and an Approve / Edit & Approve / Reject components-v2 panel.
- **New**: Per-guild controls: master toggle (`[p]assistant skills toggle`), proposals from normal-user chats (`[p]assistant skills proposeusers`), and an admin conversation mode (`[p]assistant skills adminmode off|propose|auto`) where `auto` bakes admin-taught skills with no approval panel.
- **New**: Skills carry permission levels (user/mod/admin/owner) that filter both index visibility and loading, plus created/modified/last-used/use-count metadata. A fuzzy description match forces an update-an-existing proposal instead of a near-duplicate new skill, capped per guild (`max_skills`, default 50) and per body size (8000 chars).
- **New**: Management commands `[p]assistant skills list/add/delete/menu` (the menu is an interactive components-v2 browser) and `[p]assistant skills audit [name]`, an LLM pass that flags overlapping, stale, conflicting, or low-quality skills.

## v8.11.0

- **Fix/New**: Smartmod now asks the reviewer for a separate `user_reason` alongside its staff analysis: a short, action-agnostic statement of what the user did and which rule it broke. That text (instead of the full staff-facing analysis, which previously read as nonsense when staff picked a different action than suggested) is what pre-fills the action's reason modal, falls back on blank submit, and is recorded for the action itself (audit log, warn DM, modnote). The panel shows an `Action reason:` line whenever it differs from the analysis.
- **New**: A mod panel that times out with no staff action is now stamped `⏱️ Panel expired with no staff action.` instead of silently greying out its buttons.
- **Fix**: Panel context excerpts no longer start mid-word; the partial first line left by the tail slice is dropped.

## v8.10.1

- **Fix**: third-party/RPC `add_embedding` crashed with `EmbeddingStore.add() takes 6 positional arguments but 7 were given` — it still passed the vestigial `ai_created` flag dropped from the store in the chromadb refactor. The parameter stays in `add_embedding`'s signature for API compatibility but is no longer forwarded.

## v8.10.0

- **New**: Localhost RPC handlers for prompt/embedding management (requires Red's `--rpc` launch flag; no effect otherwise). JSON-RPC methods `ASSISTANT__RPC_GET_SYSTEM_PROMPT`, `ASSISTANT__RPC_SET_SYSTEM_PROMPT`, `ASSISTANT__RPC_LIST_EMBEDDINGS`, `ASSISTANT__RPC_UPSERT_EMBEDDING` (re-embeds via the configured API), `ASSISTANT__RPC_DELETE_EMBEDDING`. Intended for external tooling to keep the system prompt and RAG entries in sync programmatically. RPC binds 127.0.0.1 only; box access is the auth boundary.

## v8.9.0

- **New**: Smartmod trigger phrases. Staff can set keyword triggers that fire the moderation review pipeline **in place of** the OpenAI moderation scan, so smartmod works even with no OpenAI key. Manage them with `[p]assistant smartmod trigger <phrase>` (re-run to remove) and `[p]assistant smartmod triggers` (list). Only `*` acts as a wildcard (any run of characters); everything else is escaped, so pasting real regex is safe and can never lock the bot up with catastrophic backtracking — no multiprocessing timeout guard is needed. A phrase with no leading/trailing `*` matches on word boundaries (`idiot` hits "idiot" but not "idiotic"); add `*` for prefix/suffix/substring matching. A keyword match runs the review alongside any category hits. `smartmod test` / `smartmod simulate` now report trigger matches and run key-free when triggers are configured.

## v8.8.4

- **Fix**: Final wire-gate sanitation in `request_chat_completion_raw`. A reasoning-only assistant turn (null `content`, no `tool_calls`) could reach the provider and trigger `400 Provider returned error` on strict endpoints (e.g. `qwen/qwen3.6-plus` via OpenRouter). Such messages now have their reasoning salvaged into `content` (or a stub) immediately before the API call, regardless of upstream cleaning.

## v8.8.3

- **Fix**: OpenRouter `404 No endpoints found that support the provided 'tool_choice' value` (raised when the routed provider for a model — e.g. `qwen/qwen3.6-plus` — doesn't accept a forced `tool_choice`) no longer crashes the response. `request_chat_completion_raw` now retries the request once without `tool_choice` on that error. Body parsing handles both the inner error dict and full envelope shapes.

## v8.8.2

- **Fix**: Reasoning-only continuation retry no longer 400s on strict providers. When a reasoning model (e.g. Xiaomi/MiMo v2.5 via OpenRouter) returned reasoning with no content/tool call, the in-flight retry payload carried an assistant message with `content: null` and only `reasoning_details`/`reasoning` — which Xiaomi rejects (`assistant must provide content, reasoning_content or tool_calls`). The reasoning is now also mirrored into `reasoning_content` so the continuation request is accepted.

## v8.8.1

- **Fix**: Sentry SDK bug — when OpenRouter returns HTTP 200 with `choices: null` (e.g. model temporarily unavailable), Sentry's OpenAI integration crashed with a `TypeError` that surfaced as an unhandled exception. Now caught in `request_chat_completion_raw` with a descriptive `RuntimeError`, and handled in `handle_message` with a user-facing message instead of the generic "something went wrong" fallback.

## v8.8.0

- **Fix**: `resolve_chat_model()` now recognises OpenRouter model slug suffixes (`:nitro`, `:floor`, `:extended`) — models stored as e.g. `xiaomi/mimo-v2.5-pro:nitro` no longer fall back to `openrouter/auto`. The "not in discovered model list" warning is also suppressed for suffix models whose base is in the profile.
- **New**: OpenRouter provider routing preferences — `[p]assistant orprovider providers <p1> [p2 ...]` sets an ordered provider list; `[p]assistant orprovider fallbacks false` hard-pins to those providers; `[p]assistant orprovider suffix :nitro` applies a guild-wide model slug suffix to every request; `[p]assistant orprovider settings` shows current config.
- **New**: Model picker search — Search 🔍 button filters the model list by query; Suffix 🏷️ button sets/clears the `:nitro`/`:floor`/`:extended` suffix on the currently selected model inline; Clear ✖️ resets the search.

## v8.7.2

- Smartmod review now passes each surrounding-context message's image attachments to the moderator model when the review endpoint supports vision (each image is included as an `image_url` content block inline with the chronological transcript). Text-only fallback still notes attachment counts for non-vision endpoints.
- `MixinMeta` (abc): added `execute_mod_action` and `smartmod_unban` declarations and fixed `smartmod_score` signature to include `image_urls`.

## v8.7.1

- Smartmod review prompt now substitutes the same placeholder variables as the main system prompt ({servername}, {channelname}, {displayname}, custom cog-registered variables, etc.) in both the base system prompt and the per-guild `mod_prompt`. The dynamic floating context block (time, last interaction, opted-in variables via `[p]floatingcontext`) is also injected into the review call so the moderator model sees the same situational context as the regular chat path. `{flagged_categories}` continues to work.

## v8.7.0

- New `[p]assistant api globalmodel <model>` (owner): a global default chat model that any guild which hasn't picked its own falls back to — pairs with the global endpoint override. For example set it to `openrouter/free` so fresh servers route to OpenRouter's Free Models Router instead of the built-in `gpt-5.4` default (which otherwise resolves to `openrouter/auto` and can be blocked by OpenRouter allow-list / data-policy rules). Guilds that chose their own model are unaffected.

## v8.6.1

- OpenRouter sticky-routing `session_id` now uses readable names (`guild_channel_user`, per-channel for collaborative conversations) instead of numeric IDs.

## v8.6.0

- `[p]assistant smartmod model` with no argument now opens the interactive model picker (endpoint-discovered models when a custom endpoint is set, otherwise the built-in OpenAI list), targeting the smartmod review model.
- `[p]assistant smartmod key` now collects the OpenAI key through a secure modal (matching the cog's other key commands) instead of taking it as a command argument.

## v8.5.0

- `[p]assistant smartmod defaultprompt` returns the built-in default moderation prompt as a file to copy and customize. `[p]assistant smartmod prompt` with no text now shows the current prompt (as a file) instead of silently resetting it; `[p]assistant smartmod resetprompt` restores the default.

## v8.4.0

- Tool-approval prompt (`requires_user_approval` tools like `run_eval`) gained a 4th button, **Skip With Feedback**, which opens a modal to optionally explain *why* you're skipping. The feedback is appended to the skip message fed back to the model so it can course-correct. Submitting blank behaves like a normal Skip.

## v8.3.0

- Smartmod now scans **images**: image attachments are sent to `omni-moderation-latest` alongside any text, and image-only messages (previously skipped) are now screened. A message is flagged if any part (text or any image) trips a threshold — the per-category score is the max across all parts. The review prompt labels image-only messages as `[image attachment]`.

## v8.2.3

- `[p]assistant smartmod threshold` with no arguments now lists every moderation category and its current threshold (instead of an argument error).

## v8.2.2

- Smartmod action panel now shows the flagged message's channel right under the jump-to-message link.

## v8.2.1

- Fix `[p]assistant smartmod` (alias `automod`) sending the help text twice when invoked without a subcommand (the group body called `ctx.send_help()` on top of Red's automatic group help). Added `view` as an alias for `[p]assistant smartmod status`.

## v8.2.0

### Smartmod — more actions + cog integrations

- New built-in panel actions: **warn** (records a warning via Red's `Warnings` cog, falling back to a DM) and **tempban** (Discord ban with a scheduled auto-unban).
- The panel action set is now dynamic: the suggested action is a highlighted button alongside a dropdown of every action available on the server. `propose_mod_action`'s `action` enum is constrained to the actually-available actions, and `timeout_minutes` is now `duration_minutes` (covers timeout / tempban / ark_tempban).
- **ArkTools integration** (when the cog is loaded): if the flagged member has a linked in-game player, **Ark ban** / **Ark temp ban** actions are offered, calling `ban_unban_player` (RCON + banlist) directly.
- **ModNotes integration** (JojoCogs, when loaded): an **Add note** action records a moderator note via the cog's `api.create_note`.
- Action execution moved onto the cog (`execute_mod_action`); the panel only gates permissions and delegates. The reviewer never acts autonomously — staff confirm every action.

## v8.1.1

- `[p]assistant smartmod` (alias `automod`) with no subcommand now shows the help/subcommand list instead of the config summary. The config summary moved to `[p]assistant smartmod status` (aliases `settings`, `show`).

## v8.1.0

### Smartmod (AI moderation)

- New `[p]assistant smartmod` feature: every eligible message is screened by OpenAI's free `/moderations` endpoint (`omni-moderation-latest`), gated by admin-configurable per-category thresholds.
- When a category trips its threshold, a configured LLM reviews the surrounding conversation (pulled on demand via `channel.history`), grounded RAG knowledge, and the server's rules, then must call one of two terminal tools: `no_action_needed` or `propose_mod_action`. The reviewer may also call the bot's other enabled tools, scoped to what the bot itself is permitted to use (owner-only tools are never exposed).
- A proposed action posts an interactive `LayoutView` panel to a staff channel showing a jump link, flagged categories/scores, the context excerpt, and the LLM's reasoning. Staff click an action button (suggested action highlighted, plus alternatives and "No action"); ban/kick/timeout open a reason modal pre-filled with the LLM's reason (editable, or left blank to use it).
- Panel buttons are permission-gated (ban→ban_members, kick→kick_members, timeout→moderate_members, delete→manage_messages, or a configured staff role). On timeout the buttons disable with no action by default; `autoaction` can opt into auto-executing the suggestion instead.
- Per-guild config: report channel, review model, moderation prompt, category thresholds, channel/category/role/member blacklist & whitelist, staff ping roles, context window size, panel timeout, staff exemption, and an OpenAI key override (`smartmod key`) so guilds on a custom/non-OpenAI chat endpoint (OpenRouter, LM Studio, etc.) can still run the OpenAI moderation scan.
- `[p]assistant smartmod test <content>` runs the moderation scan on sample text and prints every category's score against its threshold, so admins can tune thresholds before enabling.
- `[p]assistant smartmod simulate <content>` (alias `dryrun`) dry-runs the whole pipeline end to end: real scan → real review model (tools, embeddings, channel context, with the admin as the simulated offender) → the actual action panel posted to the current channel, but its buttons are no-ops so nobody is actually punished. The review only runs when a category trips its threshold, mirroring production.
- If the review model can't reach a decision (loop exhausted, or an endpoint without tool-calling support), Smartmod posts a "manual review needed" notice to the report channel instead of silently dropping the flagged message.
- Fixed `MixinMeta.request_response` in `abc.py` missing the `tool_choice` parameter that `chat.py` and the new review loop pass (the shared-method contract was out of sync with the implementation).

## v8.0.1

- Fix `OpenAIError: Missing credentials` when using a local OpenAI-compatible endpoint (e.g. koboldcpp, llama.cpp) without an API key configured. `get_api_key` now returns a `not-needed` placeholder when an endpoint override is active but no key is set, so the OpenAI SDK constructor accepts the request. Local endpoints ignore the auth header.

## v8.0.0

This release is a cache-aware end-to-end refactor: stable parts of every request are kept byte-for-byte identical across turns so provider-side prompt caching (OpenAI automatic caching, Anthropic / Gemini / Qwen `cache_control`, OpenRouter response caching) can actually hit. It also serializes overlapping conversation traffic, adds per-guild endpoint overrides, and reorganizes the admin command tree. There is no v7.18.0 release - the prompt-caching work originally drafted under that label ships here.

### Prompt-cache stability

- `transient_user_context` (RAG retrieval, runtime context) now rides in a trailing payload-only user message after the clean user turn instead of being mixed into the system/initial prompt, so changing per-request context no longer invalidates the cached prefix
- Tool schema membership is kept stable across requests instead of pruning helper tools per turn ([OpenAI prompt caching docs](https://developers.openai.com/api/docs/guides/prompt-caching) require the prompt prefix - including the advertised tool set - to be byte-identical to hit cache); `prep_functions()` and the chat handler both sort registered tools alphabetically before each API call
- `think_and_plan` planner gating moved from "strip from tool list when caller isn't a planner" to per-call enforcement inside the tool body, so non-planners see the same schema everyone else does and the cached prefix stays stable
- `edit_image` already returned a graceful "no images to edit" message when the conversation had no attachments, so it likewise stays advertised every turn
- Reasoning-only recovery for `gpt-oss-120b` now preserves reasoning state on retry and can force one required tool-call retry when the model thinks but fails to emit the call. Reasoning state is held in the in-flight payload only - it does not pollute persisted conversation history
- Reasoning-only responses no longer bump the `conf.functions_called` counter (that field was removed entirely - usage tracking has been retired)

### Floating context block (`[p]floatingcontext`)

The cog now ships a dedicated mechanism for surfacing per-request values to the model without busting the cached prefix.

- Internal variable generation split into stable / cache-safe (`get_base_params` - bot info, server, channel, bank, user profile, system runtime) and dynamic / per-request (`get_dynamic_params` - time, balance, activities, session, `last_interaction`)
- New `[p]floatingcontext` (aliases: `floatcontext`, `fctx`) LayoutView lets admins toggle which variables - builtin stable, builtin dynamic, or 3rd-party - get appended to a trailing `[Current Context]` payload-only user message after conversation history
- Because that message rides after the cached prefix, dynamic values placed there do not invalidate cache reuse
- Each enabled variable is rendered as a self-encapsulated sentence (e.g. `"The current date is May 16, 2026."`), so admins do not need to author prompts that reference the variable - toggling it on is enough
- **Default: OFF for every variable** - fresh installs start with a blank slate
- Prompt-template substitution is unchanged - every variable still substitutes inline whenever its `{placeholder}` appears in a prompt template; the menu is independent of substitution
- New `{last_interaction}` variable reports time since the user's previous message in the active conversation (e.g. `"5 hours, 23 minutes ago"`, rounded to the nearest minute), falling back to `"first message in this conversation"` for fresh conversations
- `[p]assistant view` gained a ⚠️ Cache Warning embed field that lists prompts containing dynamic-variable placeholders so admins can spot prompt-prefix cache busters at a glance
- 3rd-party `register_context_variable()` gains a `cache_safe: bool = True` parameter. `True` (default) marks the variable as dynamic / per-request; `False` marks it as stable. Informational only - it shapes the floating-context UI labels and the cache warning, but substitution behavior is identical for both

### OpenRouter caching

- New `[p]assistant openroutercache` group: `enable`, `disable`, `ttl <seconds>`, `promptcache <off|5m|1h>`
- Mode A: response caching via `X-OpenRouter-Cache` / `X-OpenRouter-Cache-TTL` headers (default **on**, 5-minute TTL)
- Mode B: provider prompt caching via `cache_control` - top-level breakpoint for Anthropic models; explicit content-block breakpoints in the last system / developer message for Gemini, Qwen, and DeepSeek
- Qwen snapshot endpoints (date-suffixed model names, e.g. `qwen2.5-vl-72b-instruct-2024-09-19`) are auto-skipped with a trailing `-(YYYY-)MM-DD` regex since they reject `cache_control`
- Sticky-routing `session_id` derived from the conversation key, so retries land on the same provider that warmed the cache

### OpenAI direct caching

- `prompt_cache_key="guild-<id>"` is now sent on every direct OpenAI request, improving routing stickiness per guild

### Cache metrics (`[p]cacheinfo`)

- OpenAI-shaped (`usage.prompt_tokens_details.cached_tokens` / `cache_write_tokens`) **and** Anthropic-shaped (`usage.cache_read_input_tokens` / `cache_creation_input_tokens`) cache counters are both read into `cog.last_cache_stats` after every API call
- New `[p]cacheinfo` command shows the cache hit stats from the most recent request, including the model-specific minimum cacheable prompt threshold and an explicit warning when the last call wrote cache tokens without reading any back

### Conversation serialization

- Live listener traffic and `[p]chat` now share a single FIFO queue above `handle_message()`, keeping the LLM/tool loop unchanged while preventing overlap races
- Collaborative conversations queue against the real shared conversation key, so one channel-wide conversation no longer spawns conflicting in-flight workers
- Removed the debounce/coalesce config field (`message_coalesce_delay`), admin command, settings display, docs references, and locale/template strings
- `[p]clearconvo` now purges queued follow-up requests for the current conversation when it resets history
- New `[p]unchat` command cancels the active worker for the current conversation and drops still-queued follow-ups without resetting the conversation itself
- `cog_unload` cleanly cancels every in-flight worker on reload

### Misc / cleanup

- Removed the `Usage` model and per-guild `usage` dict (legacy token accounting); old configs load fine via Pydantic's default `extra=ignore`
- Removed the `functions_called` counter
- Removed hard-coded `PRICES` and `IMAGE_COSTS` tables and the image cost footer in `/draw` (custom endpoints don't match OpenAI pricing); `VISION_COSTS` is retained because vision-token math still uses it
- `assistant.last_cache_stats: Dict[str, object]` exposed on the cog for external introspection

### Command Structure Reorganization

Major restructuring of the `[p]assistant` admin command hierarchy from 60+ flat commands into logical command groups, improving discoverability and reducing cognitive load for server admins.

#### New Command Groups

The following `@assistant.group()` hierarchies are now available (14 total):

Per-guild groups:
- **`[p]assistant set`** (alias: `settings`) - General guild settings
  - `timezone`, `channel`, `listen`, `sysoverride`, `model`, `maxrecursion`, `thinkprefix`, `thinksuffix`, `verbosity`, `reasoningfiles`, `planner`, `customvars`, `listenbots`
- **`[p]assistant trigger`** - Trigger phrase management
  - `toggle`, `phrase`, `prompt`, `ignore`, `list`
- **`[p]assistant prompt`** - Prompt and context management
  - `system`, `defaultsystem`, `initial`, `channel`, `channelcustom`, `channelshow`
- **`[p]assistant features`** - Feature toggles
  - `enable`, `draw`, `mention`, `mention-respond`, `functions`, `collaborative`, `question-mode`, `persist`
- **`[p]assistant filter`** - Content filtering
  - `question`, `minlength`, `regex`, `failblock`, `blacklist`
- **`[p]assistant embed`** (alias: `embeddings`) - Embedding data management
  - `topn`, `relatedness`, `model`, `reset`, `resetglobal`, `refresh`, `importcsv`, `importjson`, `importexcel`, `exportexcel`, `exportcsv`, `exportjson`
- **`[p]assistant limits`** - Token and retention limits
  - `maxretention`, `maxtime`, `maxtokens`, `maxresponse`
- **`[p]assistant params`** - Model behavior parameters
  - `temperature`, `frequency`, `presence`, `resolution`, `reasoning`, `seed`
- **`[p]assistant override`** - Role-based overrides
  - `model`, `maxtokens`, `maxresponsetokens`, `maxretention`, `maxtime`, `reasoning`
- **`[p]assistant compaction`** - Conversation compaction
  - `toggle`, `model`, `threshold`
- **`[p]assistant autoanswer`** - Auto-answer system
  - `toggle`, `threshold`, `ignore`, `model`
- **`[p]assistant scheduler`** (alias: `tasks`) - Scheduled task management
  - `list`, `cancel`, `clear`

Owner-only groups:
- **`[p]assistant api`** - API keys and endpoint URLs
  - `key`, `brave`, `globalendpoint`, `globalkey`
  - `guild endpoint`, `guild view`, `guild clear`
- **`[p]assistant admin`** - Dangerous maintenance operations
  - `resetconversations`, `resetglobalconversations`, `probe`, `wipe`, `backup`, `restore`

Two commands intentionally remain flat: `[p]assistant view` and `[p]assistant usage`

New group-style examples:
```
[p]assistant set model gpt-4o
[p]assistant embed topn 5
[p]assistant filter regex "bad_pattern"
[p]assistant trigger phrase "hello world"
[p]assistant api key
[p]assistant admin backup
```

#### Migration Guide

| Old Flat Command | New Grouped Command |
|------------------|---------------------|
| `[p]assistant backupcog` | `[p]assistant admin backup` |
| `[p]assistant blacklist` | `[p]assistant filter blacklist` |
| `[p]assistant braveapikey` / `brave` | `[p]assistant api brave` |
| `[p]assistant canceltask` | `[p]assistant scheduler cancel` |
| `[p]assistant channel` | `[p]assistant set channel` |
| `[p]assistant channelprompt` | `[p]assistant prompt channelcustom` |
| `[p]assistant channelpromptshow` | `[p]assistant prompt channelshow` |
| `[p]assistant cleartasks` | `[p]assistant scheduler clear` |
| `[p]assistant collab` | `[p]assistant features collaborative` |
| `[p]assistant compaction` | `[p]assistant compaction toggle` |
| `[p]assistant compactionmodel` | `[p]assistant compaction model` |
| `[p]assistant compactionthreshold` | `[p]assistant compaction threshold` |
| `[p]assistant customvariables` / `customvars` | `[p]assistant set customvars` |
| `[p]assistant defaultsystem` | `[p]assistant prompt defaultsystem` |
| `[p]assistant drawtoggle` / `toggledraw` | `[p]assistant features draw` |
| `[p]assistant embedmodel` | `[p]assistant embed model` |
| `[p]assistant endpointapikey` / `endpointkey` | `[p]assistant api globalkey` |
| `[p]assistant endpointoverride` | `[p]assistant api globalendpoint` |
| `[p]assistant endpointprobe` | `[p]assistant admin probe` |
| `[p]assistant exportcsv` | `[p]assistant embed exportcsv` |
| `[p]assistant exportexcel` | `[p]assistant embed exportexcel` |
| `[p]assistant exportjson` | `[p]assistant embed exportjson` |
| `[p]assistant frequency` | `[p]assistant params frequency` |
| `[p]assistant functioncalls` / `usefunctions` | `[p]assistant features functions` |
| `[p]assistant importcsv` | `[p]assistant embed importcsv` |
| `[p]assistant importexcel` | `[p]assistant embed importexcel` |
| `[p]assistant importjson` | `[p]assistant embed importjson` |
| `[p]assistant listen` | `[p]assistant set listen` |
| `[p]assistant listentobots` / `botlisten` / `ignorebots` | `[p]assistant set listenbots` |
| `[p]assistant maxrecursion` | `[p]assistant set maxrecursion` |
| `[p]assistant maxresponsetokens` | `[p]assistant limits response` |
| `[p]assistant maxretention` | `[p]assistant limits retention` |
| `[p]assistant maxtime` | `[p]assistant limits time` |
| `[p]assistant maxtokens` | `[p]assistant limits tokens` |
| `[p]assistant mention` | `[p]assistant features mention` |
| `[p]assistant mentionrespond` | `[p]assistant features mention-respond` |
| `[p]assistant minlength` | `[p]assistant filter minlength` |
| `[p]assistant model` | `[p]assistant set model` |
| `[p]assistant openaikey` / `key` | `[p]assistant api key` |
| `[p]assistant persist` | `[p]assistant features persist` |
| `[p]assistant planner` | `[p]assistant set planner` |
| `[p]assistant presence` | `[p]assistant params presence` |
| `[p]assistant prompt` / `pre` | `[p]assistant prompt initial` |
| `[p]assistant questionmark` | `[p]assistant filter question` |
| `[p]assistant questionmode` | `[p]assistant features question-mode` |
| `[p]assistant reasoning` | `[p]assistant params reasoning` |
| `[p]assistant reasoningfiles` | `[p]assistant set reasoningfiles` |
| `[p]assistant refreshembeds` | `[p]assistant embed refresh` |
| `[p]assistant regexblacklist` | `[p]assistant filter regex` |
| `[p]assistant regexfailblock` | `[p]assistant filter failblock` |
| `[p]assistant relatedness` | `[p]assistant embed relatedness` |
| `[p]assistant resetconversations` | `[p]assistant admin resetconversations` |
| `[p]assistant resetembeddings` | `[p]assistant embed reset` |
| `[p]assistant resetglobalembeddings` | `[p]assistant embed resetglobal` |
| `[p]assistant resetglobalconversations` | `[p]assistant admin resetglobalconversations` |
| `[p]assistant resolution` | `[p]assistant params resolution` |
| `[p]assistant restorecog` | `[p]assistant admin restore` |
| `[p]assistant scheduledtasks` / `listtasks` | `[p]assistant scheduler list` |
| `[p]assistant seed` | `[p]assistant params seed` |
| `[p]assistant sysoverride` | `[p]assistant set sysoverride` |
| `[p]assistant system` / `sys` | `[p]assistant prompt system` |
| `[p]assistant temperature` | `[p]assistant params temperature` |
| `[p]assistant thinkprefix` | `[p]assistant set thinkprefix` |
| `[p]assistant thinksuffix` | `[p]assistant set thinksuffix` |
| `[p]assistant toggle` | `[p]assistant features enable` |
| `[p]assistant topn` | `[p]assistant embed topn` |
| `[p]assistant trigger` | `[p]assistant trigger toggle` |
| `[p]assistant triggerignore` | `[p]assistant trigger ignore` |
| `[p]assistant triggerlist` | `[p]assistant trigger list` |
| `[p]assistant triggerphrase` | `[p]assistant trigger phrase` |
| `[p]assistant triggerprompt` | `[p]assistant trigger prompt` |
| `[p]assistant verbosity` | `[p]assistant set verbosity` |
| `[p]assistant wipecog` | `[p]assistant admin wipe` |
| `[p]assistant autoanswer` | `[p]assistant autoanswer toggle` |
| `[p]assistant autoanswerignore` | `[p]assistant autoanswer ignore` |
| `[p]assistant autoanswermodel` | `[p]assistant autoanswer model` |
| `[p]assistant autoanswerthreshold` | `[p]assistant autoanswer threshold` |

#### Benefits

- **Improved discoverability** - `[p]help assistant trigger` shows all trigger-related commands together
- **Cleaner namespace** - Removes ambiguous command names (e.g. `toggle` now clearly under `features`)
- **Easier documentation** - Grouped commands are easier to learn and reference
- **Future-proof** - Hierarchical structure supports future subgroup nesting if needed

### Per-Guild Endpoint Overrides

Servers can now configure their own API endpoint and key, independent of the global endpoint override. This enables multi-tenant setups where one guild uses OpenRouter, another uses a local LLM, and a third uses OpenAI directly.

**Exactly 4 credential slots - 1 global + 1 guild for each of URL and key:**

| Scope  | URL command                          | Key command                   |
|--------|--------------------------------------|-------------------------------|
| Global | `[p]assistant api globalendpoint`   | `[p]assistant api globalkey`  |
| Guild  | `[p]assistant api guild endpoint`   | `[p]assistant api key`        |

Both chat and embedding requests use the same endpoint and key for a given scope - there is no separate embedding endpoint.

**Resolution (independent fallback per slot):**
- Endpoint URL: guild override → global override → OpenAI direct
- API key: guild key → global key → empty

**Commands under `[p]assistant api guild`:**
- `endpoint <url>` - Set a per-guild endpoint override (use `none` to remove)
- `view` - Show current guild endpoint and API key status
- `clear` - Remove the guild endpoint override

**Switching endpoints:**
- After setting a new endpoint, the bot probes it and warns if your current `embed_model` is not available on the new endpoint
- Run `[p]assistant set embedmodel` (no args) to open an interactive picker and choose a compatible model

**Model setting improvements:**
- `[p]assistant set model` now accepts any model name when a guild or global endpoint is configured
- Model validation against the hardcoded `MODELS` list is skipped when an endpoint override is active
- Discovered models from the endpoint are shown when running `[p]assistant set model` without arguments

## v7.15.1

### Curated embedding cleanup

The assistant's active embedding pool is now admin-curated only.

- Removed the brain-reaction memory writer so message reactions no longer create embeddings
- Removed stale tutor documentation tied to self-created embeddings
- Current retrieval, exports, menu views, and resync only operate on admin-curated embeddings
- Restored the public `add_embedding` API and removed `ai_created` metadata tracking

## v7.15.0

### Grounded RAG injection

Embedding injection now follows a single grounded 2026-style RAG layout instead of the older dynamic/static/hybrid/user modes.

- Retrieved embeddings are injected as structured XML in an ephemeral user message immediately before the live user query
- Grounding rules stay in the developer/system prompt instead of mixing retrieval into high-authority instructions
- Retrieved chunks now include source ids plus creation/update metadata so the model can cite what it used

## v7.7.0

### Conversation compaction

Conversations that exceed the token limit are now intelligently summarized using an LLM instead of blindly dropping old messages. This preserves important context while freeing up token space.

- LLM-based summarization replaces blind message truncation when context overflows
- Tool-call/result pairs are kept together during degradation to prevent orphaned messages
- Configurable compaction model (use a cheaper model for summarization)
- Configurable token threshold to trigger compaction before hitting the model's max context
- Compaction can be toggled on/off per server (`[p]assistant compaction`)

### New user commands

- `[p]convocontext` - detailed token breakdown showing context fill %, token usage by category, message counts by role, and compaction history
- `[p]convocompact` - manually compact a conversation with optional focus phrase to guide the summary

### Admin commands

- `[p]assistant compaction` - toggle LLM compaction on/off
- `[p]assistant compactionmodel` - set the model used for compaction
- `[p]assistant compactionthreshold` - set the token threshold for proactive compaction

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

### Bug fixes and improvements

- Auto-answer now uses the new embedding system
