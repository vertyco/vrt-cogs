# Third Party Assistant Integration

Goal:

- let other cogs register tools
- let other cogs register prompt context variables
- show exact runtime behavior
- make integration predictable

## Entry Point

Assistant dispatches `assistant_cog_add` when it loads.

Use listener:

```py
from redbot.core import commands


class MyCog(commands.Cog):
    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog):
        ...
```

`cog` = live Assistant cog instance.

Use this listener to register:

- tools
- context variables

## What Assistant Supports

Two systems:

1. Tools
2. Context variables

Tools:

- model sees callable function schema
- model may call tool during chat
- tool can be enabled or disabled in UI
- tool can be grouped by category
- tool can require interactive approval

Context variables:

- prompt placeholder like `{available_tickets}`
- resolved before prompt formatting
- not shown as callable tools
- only fetched if placeholder exists in active prompt text

## Tool Registration

Single tool:

```py
await cog.register_function(
    cog_name=self.qualified_name,
    schema=schema,
    permission_level="user",
    required_permissions=None,
    category="utility",
    requires_user_approval=False,
)
```

Many tools:

```py
await cog.register_functions(
    cog_name=self.qualified_name,
    schemas=schemas,
    category="utility",
    requires_user_approval=False,
)
```

### `register_function(...)`

Args:

- `cog_name: str`
- `schema: dict`
- `permission_level: Literal["user", "mod", "admin", "owner"]`
- `required_permissions: list[str] | None`
- `category: str | None`
- `requires_user_approval: bool`

Returns:

- `bool`

### Tool Schema Rules

Minimum shape:

```py
schema = {
    "name": "get_status",
    "description": "Get current status info.",
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "What to inspect.",
            }
        },
        "required": ["target"],
    },
}
```

Rules:

- `schema["name"]` must match a real method on your cog
- tool name must be unique across all cogs
- schema must pass Assistant validation
- keep description short
- keep parameter descriptions short

### Tool Method Signature

Safest pattern:

```py
async def get_status(self, target: str, *args, **kwargs) -> str:
    ...
```

Why:

- Assistant does not filter tool kwargs
- tool handlers receive schema args plus injected kwargs
- strict signatures can break unless they accept all injected keys

### Injected Tool Kwargs

Current injected kwargs for tools:

- `user: discord.Member | None`
- `channel: discord.TextChannel | discord.Thread | discord.ForumChannel | None`
- `guild: discord.Guild`
- `bot: Red`
- `conf: [GuildSettings](common/models.py)`
- `conversation: [Conversation](common/models.py)`
- `messages: list[dict]`
- `message_obj: discord.Message | None`
- `banktype: str`
- `currency: str`
- `bank: str`
- `balance: str`

Internal Assistant model links:

- [GuildSettings](common/models.py)
- [Conversation](common/models.py)
- [DB](common/models.py)

Use explicit schema args first.
Use `*args, **kwargs` after.

## Tool Return Shapes

Assistant supports more than plain strings.

Tool handlers can return:

- `str`
- `bytes`
- `discord.Embed`
- `discord.File`
- `dict`

### `str`

- becomes tool result text
- fed back into conversation
- trimmed by token limits if too large

### `bytes`

- decoded with `.decode()`
- then treated like string output

### `discord.Embed`

- sent to channel immediately
- tool result text becomes embed description or `Result sent!`

### `discord.File`

- attached to final reply when possible
- fallback behavior depends on reply flow

### `dict`

Supported keys:

- `content: str | None`
- `result_text: str | None`
- `return_null: bool`
- `defer_files: list[discord.File]`
- `embed: discord.Embed`
- `file: discord.File`
- `embeds: list[discord.Embed]`
- `files: list[discord.File]`

Behavior:

- `result_text` wins first for textual tool result
- else `content` used
- `embed` / `file` / `embeds` / `files` are sent to Discord immediately
- `defer_files` are held for final reply attachment
- `return_null=True` stops normal assistant reply after tool side effects

Good pattern:

```py
return {
    "content": "Created report.",
    "file": discord.File(buffer, filename="report.txt"),
}
```

Side effect only pattern:

```py
return {
    "content": "Posted update.",
    "return_null": True,
}
```

Avoid returning random objects.
Unknown types become error text.

## Tool Permissions

`permission_level` gates by Assistant user level:

- `user` -> everyone
- `mod` -> mods
- `admin` -> admins
- `owner` -> bot owners

`required_permissions` gates by Discord permission flags.

Example:

```py
await cog.register_function(
    self.qualified_name,
    schema,
    permission_level="mod",
    required_permissions=["manage_messages"],
    category="moderation",
)
```

Both checks must pass.

## Tool Categories

Categories are free-form.

Example:

- `documentation`
- `support`
- `moderation`
- `discord_info`

Behavior:

- saved normalized to lower-case
- rendered title case in UI
- shown in tool lists
- bulk-toggled in `[p]aitools`

## Tool Approval Gate

Set `requires_user_approval=True` for risky tools.

Good fit:

- admin actions
- destructive actions
- cross-channel posting
- permission edits

User sees:

- `Approve Once`
- `Allow This Session`
- `Skip`

Notes:

- approval only matters when tool actually gets called
- session approval is in-memory conversation state
- `clearconvo` clears session approval state

### What `dry_run=True` Means

`dry_run` is not an Assistant-level setting.

It is just a normal tool parameter.
Some tools define it in their own schema.

Current main use:

- AssistantUtils admin tools
- preview actions without applying them

Examples there:

- channel edits
- role edits
- thread edits
- server edits
- overwrite changes

Assistant special case:

- if tool call args contain `dry_run=True`
- approval gate skips interactive approval

Reason:

- preview actions should be cheap and low risk

If your tool does not define `dry_run`, this does nothing.

## Context Variable Registration

Single variable:

```py
await cog.register_context_variable(
    cog_name=self.qualified_name,
    variable_name="available_tickets",
    description="Support ticket panels this user can open.",
    permission_level="user",
    required_permissions=None,
    fetch_method="get_ticket_types",
)
```

Many variables:

```py
await cog.register_context_variables(
    cog_name=self.qualified_name,
    variables=[
        {
            "name": "available_tickets",
            "description": "Support ticket panels this user can open.",
            "fetch_method": "get_ticket_types",
        },
        {
            "name": "open_tickets",
            "description": "Current user's open tickets.",
        },
    ],
)
```

### `register_context_variable(...)`

Args:

- `cog_name: str`
- `variable_name: str`
- `description: str`
- `permission_level: Literal["user", "mod", "admin", "owner"]`
- `required_permissions: list[str] | None`
- `fetch_method: str | None`

Returns:

- `bool`

### Variable Naming Rules

Rules:

- unique across all cogs
- alphanumeric, `_`, and `-` only
- max 64 chars effectively
- use lower-case snake_case unless strong reason not to

Use in prompts like:

```txt
Available ticket panels:
{available_tickets}
```

Do not include braces when registering.
Only include braces in prompt text.

### Fetch Method Rules

Fetcher can be sync or async.

Good:

```py
async def available_tickets(self, user: discord.Member) -> str:
    ...
```

Also good:

```py
async def get_ticket_types(self, user: discord.Member, **kwargs) -> str:
    ...
```

Assistant filters kwargs for context variable fetchers.
So fetchers can accept only what they need.
Or accept `**kwargs` if preferred.

### Injected Context Variable Kwargs

Current injected kwargs for context variable fetchers:

- `user: discord.Member | None`
- `channel: discord.TextChannel | discord.Thread | discord.ForumChannel | None`
- `guild: discord.Guild`
- `bot: Red`
- `conf: [GuildSettings](common/models.py)`
- `conversation: [Conversation](common/models.py)`
- `now: datetime`
- `banktype: str`
- `currency: str`
- `bank: str`
- `balance: str`

Only matching parameter names are passed.

## Context Variable Runtime

Assistant scans active prompt text first.

Current scan targets:

- active system prompt
- main prompt
- trigger prompt

If `{your_variable}` not present:

- fetcher is not called
- no CPU wasted

If present:

- permission gate runs
- discord permission gate runs
- fetcher runs
- return value injected into prompt params

## Context Variable Return Shapes

Recommended return type:

- `str`

Also supported:

- `dict`
- `list`
- `None`

Behavior:

- `str` -> inserted as-is
- `dict` / `list` -> pretty JSON string
- `None` -> empty string

Failure behavior:

- unauthorized or unavailable -> `Unavailable`
- exception -> `[Error resolving <name>]`

Name collision behavior:

- built-in prompt param wins
- custom variable skipped

## Full Example

```py
from redbot.core import commands


class MyCog(commands.Cog):
    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog):
        schema = {
            "name": "get_project_status",
            "description": "Get current project status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Project to inspect.",
                    }
                },
                "required": ["project_name"],
            },
        }

        await cog.register_function(
            cog_name=self.qualified_name,
            schema=schema,
            permission_level="user",
            category="projects",
        )

        await cog.register_context_variable(
            cog_name=self.qualified_name,
            variable_name="project_overview",
            description="Small project overview for current user.",
            fetch_method="get_project_overview",
        )

    async def get_project_status(self, project_name: str, *args, **kwargs) -> str:
        return f"Status for {project_name}: healthy"

    async def get_project_overview(self, user: discord.Member, guild: discord.Guild) -> str:
        return f"User: {user.display_name}\nServer: {guild.name}"
```

## Batch Example

```py
@commands.Cog.listener()
async def on_assistant_cog_add(self, cog):
    schemas = [
        {
            "name": "get_foo",
            "description": "Get foo.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_bar",
            "description": "Get bar.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]

    await cog.register_functions(
        cog_name=self.qualified_name,
        schemas=schemas,
        category="utility",
    )

    await cog.register_context_variables(
        cog_name=self.qualified_name,
        variables=[
            {
                "name": "foo_summary",
                "description": "Summary of foo.",
            },
            {
                "name": "bar_summary",
                "description": "Summary of bar.",
                "fetch_method": "build_bar_summary",
            },
        ],
    )
```

## Unregistering

Optional cleanup methods:

- `unregister_function(cog_name, function_name)`
- `unregister_context_variable(cog_name, variable_name)`
- `unregister_cog(cog_name)`

Manual cleanup is optional in most cases.
Assistant removes stale cogs and stale methods during cleanup.

If you want manual cleanup:

```py
assistant = self.bot.get_cog("Assistant")
if assistant:
    await assistant.unregister_cog(self.qualified_name)
```

## Admin Surface

Useful commands:

- `[p]assist listfunctions`
- `[p]assist listcategories`
- `[p]assist togglefunctions`
- `[p]assist togglecategories`
- `[p]aitools`
- `[p]assist customvariables`

What admins see:

- tool names
- categories
- enable state
- context variable catalog

## Failure Cases

Tool registration fails if:

- Assistant cannot find your cog
- schema invalid
- schema name duplicates another cog's tool
- your cog does not have a method matching schema name
- `required_permissions` contains invalid permission flags

Context variable registration fails if:

- Assistant cannot find your cog
- variable name empty
- variable name invalid
- variable name duplicates another cog's variable
- description empty
- fetch method missing
- `required_permissions` contains invalid permission flags

Check logs if registration returns `False`.

## Best Practices

- keep names stable
- keep descriptions short
- keep categories broad
- use `requires_user_approval=True` for destructive admin tools
- only use `dry_run` if your tool schema actually defines it
- return plain text unless richer output helps
- use dict returns for embeds, files, and side effects
- keep context variables cheap
- only register context variables that give strong value without a tool call
- prefer context variables for small facts the model should already know
- prefer tools for actions, optional lookups, or expensive work

## Good Uses For Context Variables

Good:

- available ticket panels
- current user's open tickets
- average response time
- working-hours availability
- active dashboard panels
- current alert summary

Bad:

- huge exports
- expensive network calls on every prompt
- destructive actions
- data user rarely needs
- content already covered by normal prompt params

## Short Checklist

Tool checklist:

- add `on_assistant_cog_add`
- build valid schema
- create matching method
- accept `*args, **kwargs`
- register with category
- set permissions

Context variable checklist:

- choose short variable name
- create fetch method
- return string or small structured data
- register variable
- add `{variable_name}` to Assistant prompt text
- verify with `[p]assist customvariables`

## Summary

Tools = model can call code.

Context variables = prompt gets pre-fetched data.

Use tools for actions.
Use context variables for small context the model should already know.
