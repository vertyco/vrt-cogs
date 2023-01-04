# AutoDocs Help

Document your cogs with ease!

Easily create documentation for any cog in Markdown format.

# makedocs (Hybrid Command)
 - Usage: `[p]makedocs <cog_name> [replace_prefix=False] [include_hidden=False]`
 - Slash Usage: `/makedocs <cog_name> [replace_prefix] [include_hidden]`
 - `cog_name:` (Required) The name of the cog you want to make docs for (Case Sensitive)
 - `replace_prefix:` (Optional) Replace prefix placeholder with the bots prefix
 - `include_hidden:` (Optional) Include hidden commands


Create a Markdown docs page for a cog and send to discord

**Arguments**
`cog_name:`(str) The name of the cog you want to make docs for (Case Sensitive)
`replace_prefix:`(bool) If True, replaces the prefix placeholder [] with the bots prefix
`include_hidden:`(bool) If True, includes hidden commands

**Warning**
If `all` is specified for cog_name, and you have a lot of cogs loaded, prepare for a spammed channel

