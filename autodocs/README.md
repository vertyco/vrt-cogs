# AutoDocs Help

Document your cogs with ease!<br/><br/>Easily create documentation for any cog in Markdown format.

# makedocs
 - Usage: `[p]makedocs <cog_name> [replace_prefix=False] [include_hidden=False] [advanced_docs=False] [include_docstrings=False]`

Create a Markdown docs page for a cog and send to discord<br/><br/>**Arguments**<br/>`cog_name:`(str) The name of the cog you want to make docs for (Case Sensitive)<br/>`replace_prefix:`(bool) If True, replaces the prefix placeholder [] with the bots prefix<br/>`include_hidden:`(bool) If True, includes hidden commands<br/><br/>**Warning**<br/>If `all` is specified for cog_name, all currently loaded non-core cogs will have docs generated for them and sent in a zip file

