Document your cogs with ease!<br/><br/>Easily create documentation for any cog in Markdown format.

# [p]makedocs (Hybrid Command)
Create a Markdown docs page for a cog and send to discord<br/>

**Arguments**<br/>
`cog_name:            `(str) The name of the cog you want to make docs for (Case Sensitive)<br/>
`replace_prefix:      `(bool) If True, replaces the `prefix` placeholder with the bots prefix<br/>
`replace_botname:     `(bool) If True, replaces the `botname` placeholder with the bots name<br/>
`extended_info:       `(bool) If True, include extra info like converters and their docstrings<br/>
`include_hidden:      `(bool) If True, includes hidden commands<br/>
`include_help:        `(bool) If True, includes the cog help text at the top of the docs<br/>
`max_privilege_level: `(str) Hide commands above specified privilege level<br/>
`min_privilage_level: `(str) Hide commands below specified privilege level<br/>
- (user, mod, admin, serverowner, botowner)<br/>
`csv_export:          `(bool) Include a csv with each command isolated per row for use as embeddings<br/>

**Note** If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for<br/>
them and sent in a zip file<br/>
 - Usage: `[p]makedocs <cog_name> [replace_prefix=False] [replace_botname=False] [extended_info=False] [include_hidden=False] [include_help=True] [max_privilege_level=botowner] [min_privilage_level=user] [csv_export=False]`
 - Slash Usage: `/makedocs <cog_name> [replace_prefix=False] [replace_botname=False] [extended_info=False] [include_hidden=False] [include_help=True] [max_privilege_level=botowner] [min_privilage_level=user] [csv_export=False]`
 - Restricted to: `BOT_OWNER`
 - Checks: `server_only`
