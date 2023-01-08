# AutoDocs Help

Document your cogs with ease!<br/><br/>Easily create documentation for any cog in Markdown format.

# makedocs (Hybrid Command)

-
Usage: `[p]makedocs <cog_name> [replace_prefix=False] [replace_botname=False] [extended_info=False] [include_hidden=False] `
- Slash
  Usage: `/makedocs <cog_name> [replace_prefix=False] [replace_botname=False] [extended_info=False] [include_hidden=False] `
- Restricted to: `BOT_OWNER`

Create a Markdown docs page for a cog and send to discord<br/><br/>**Arguments**<br/>`cog_name:           `(str) The
name of the cog you want to make docs for (Case Sensitive)<br/>`replace_prefix:     `(bool) If True, replaces
the `prefix` placeholder with the bots prefix<br/>`replace_botname:    `(bool) If True, replaces the `botname`
placeholder with the bots name<br/>`extended_info:      `(bool) If True, include extra info like converters and their
docstrings<br/>`include_hidden:     `(bool) If True, includes hidden commands<br/><br/>**Note**<br/>If `all` is
specified for cog_name, all currently loaded non-core cogs will have docs generated for them and sent in a zip file

Extended Arg Info
> ### cog_name: str
> ```
> A single word, if not using slash and multiple words are necessary use a quote e.g "Hello world".
> ```
> ### replace_prefix: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
> ### replace_botname: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
> ### extended_info: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
> ### include_hidden: Optional[bool] = False
> ```
> Can be 1, 0, true, false, t, f
> ```
